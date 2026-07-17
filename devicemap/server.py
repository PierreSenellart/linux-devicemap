"""HTTP + WebSocket server: serves the frontend, the current snapshot,
and pushes live updates."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import layout, monitor, snapshot
from .probes import activity

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

DEBOUNCE_S = 0.4
BATTERY_POLL_S = 10


def _sig(port: dict) -> tuple:
    """Per-port signature for calibration change detection: occupancy,
    device identity, power partner, inserted card."""
    dev = port.get("device") or {}
    power = port.get("power") or {}
    card = port.get("card") or {}
    return (
        bool(port.get("connected")),
        dev.get("vid"),
        dev.get("pid"),
        bool(power.get("partner_present")),
        card.get("name"),
    )


class Hub:
    """Holds the current state and broadcasts updates to clients."""

    def __init__(self) -> None:
        self.raw: dict = {"ports": []}  # last pure hardware snapshot
        self.snapshot: dict = {}  # published state (snapshot + layout)
        self.clients: set[WebSocket] = set()
        # while armed: {"slot", "baseline": {port_id: sig}, "seen": [ids]}
        self.calibration: dict | None = None
        self._lock = asyncio.Lock()

    async def broadcast(self, message: dict) -> None:
        data = json.dumps(message)
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                self.clients.discard(ws)

    def arm(self, slot_id: str) -> None:
        self.calibration = {
            "slot": slot_id,
            "baseline": {p["id"]: _sig(p) for p in self.raw.get("ports", [])},
            "seen": [],
        }

    def _calibrate_step(self, new: dict) -> None:
        """Bind the armed slot to the most recently changed, currently
        connected port. Any deviation from the arm-time baseline counts as
        a change, so occupied ports can be calibrated by replugging or by
        swapping what is plugged into them."""
        cal = self.calibration
        for port in new["ports"]:
            pid = port["id"]
            sig = _sig(port)
            if sig != cal["baseline"].get(pid):
                cal["baseline"][pid] = sig
                if pid in cal["seen"]:
                    cal["seen"].remove(pid)
                cal["seen"].append(pid)  # most recent change last
        for pid in reversed(cal["seen"]):
            port = next((p for p in new["ports"] if p["id"] == pid), None)
            if port and port.get("connected"):
                binding = layout.binding_for_port(port)
                if binding:
                    layout.save_binding(new["machine"], cal["slot"], binding)
                    self.calibration = None
                    return

    async def refresh(self, reason: list[dict] | None = None) -> bool:
        async with self._lock:
            new = await asyncio.to_thread(snapshot.build)
            self.raw = new
            if self.calibration:
                self._calibrate_step(new)
            state = dict(new)
            cal = {"slot": self.calibration["slot"]} if self.calibration else None
            state["layout"] = layout.compose(new, cal)
            old_state, self.snapshot = self.snapshot, state
            changed = _strip_ts(old_state) != _strip_ts(state)
        if changed:
            await self.broadcast(
                {"type": "snapshot", "data": state, "events": reason or []}
            )
        return changed


def _strip_ts(snap: dict) -> dict:
    return {k: v for k, v in snap.items() if k != "ts"}


hub = Hub()


async def _event_loop() -> None:
    """Debounce udev events, then re-probe and broadcast."""
    pending: list[dict] = []
    aiter = monitor.events()
    while True:
        ev = await anext(aiter)
        pending.append(ev)
        # keep absorbing events until quiet for DEBOUNCE_S
        while True:
            try:
                ev = await asyncio.wait_for(anext(aiter), timeout=DEBOUNCE_S)
                pending.append(ev)
                if len(pending) > 200:
                    break
            except TimeoutError:
                break
        await hub.refresh(reason=pending[-50:])
        pending = []


async def _battery_poll() -> None:
    while True:
        await asyncio.sleep(BATTERY_POLL_S)
        await hub.refresh(reason=[{"action": "poll", "subsystem": "power_supply"}])


ACTIVITY_POLL_S = 2


async def _activity_poll() -> None:
    """Camera/audio in-use changes emit no udev events: poll a cheap
    signature and re-probe on change."""
    last = None
    while True:
        await asyncio.sleep(ACTIVITY_POLL_S)
        sig = await asyncio.to_thread(activity.signature, hub.raw)
        if last is not None and sig != last:
            await hub.refresh(reason=[{"action": "activity", "subsystem": "media"}])
        last = sig


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    await hub.refresh()
    tasks = [
        asyncio.create_task(_event_loop()),
        asyncio.create_task(_battery_poll()),
        asyncio.create_task(_activity_poll()),
    ]
    loop = asyncio.get_running_loop()
    on_ev = lambda ev: asyncio.ensure_future(hub.refresh(reason=[ev]))
    closers = monitor.start_jack_watchers(loop, on_ev)
    closers += monitor.start_rtnetlink_watcher(loop, on_ev)
    closers += monitor.start_video_watchers(loop, on_ev)
    yield
    for t in tasks:
        t.cancel()
    for close in closers:
        close()


app = FastAPI(lifespan=_lifespan)


@app.get("/api/state")
async def state() -> JSONResponse:
    return JSONResponse(hub.snapshot)


@app.post("/api/calibrate/{slot_id}")
async def calibrate(slot_id: str) -> JSONResponse:
    hub.arm(slot_id)
    await hub.refresh(reason=[{"action": "calibrate", "subsystem": "layout"}])
    return JSONResponse({"armed": slot_id})


@app.delete("/api/calibrate")
async def calibrate_cancel() -> JSONResponse:
    hub.calibration = None
    await hub.refresh(reason=[{"action": "calibrate-cancel", "subsystem": "layout"}])
    return JSONResponse({"armed": None})


@app.post("/api/slot/{slot_id}/position")
async def slot_position(slot_id: str, payload: dict = Body(...)) -> JSONResponse:
    layout.save_slot(
        hub.raw["machine"],
        slot_id,
        payload.get("side"),
        float(payload.get("x") or 0.0),
        float(payload["y"]),
    )
    await hub.refresh(reason=[{"action": "move-slot", "subsystem": "layout"}])
    return JSONResponse({"ok": True})


@app.post("/api/slot/{slot_id}/label")
async def slot_label(slot_id: str, payload: dict = Body(...)) -> JSONResponse:
    layout.save_label(hub.raw["machine"], slot_id, str(payload["label"]))
    await hub.refresh(reason=[{"action": "rename-slot", "subsystem": "layout"}])
    return JSONResponse({"ok": True})


@app.post("/api/port/{port_id}/hidden")
async def port_hidden(port_id: str, payload: dict = Body(...)) -> JSONResponse:
    layout.set_hidden(hub.raw["machine"], port_id, bool(payload["hidden"]))
    await hub.refresh(reason=[{"action": "hide-port", "subsystem": "layout"}])
    return JSONResponse({"ok": True})


@app.post("/api/port/{port_id}/place")
async def port_place(port_id: str) -> JSONResponse:
    port = next((p for p in hub.raw.get("ports", []) if p["id"] == port_id), None)
    if not port:
        return JSONResponse({"ok": False}, status_code=404)
    layout.add_slot(hub.raw["machine"], port)
    # a placed port should be visible: clear any hidden flag on it
    layout.set_hidden(hub.raw["machine"], port_id, False)
    await hub.refresh(reason=[{"action": "place-port", "subsystem": "layout"}])
    return JSONResponse({"ok": True})


@app.post("/api/slot/{slot_id}/unplace")
async def slot_unplace(slot_id: str) -> JSONResponse:
    removed = layout.remove_extra_slot(hub.raw["machine"], slot_id)
    await hub.refresh(reason=[{"action": "unplace-slot", "subsystem": "layout"}])
    return JSONResponse({"ok": removed})


@app.post("/api/layouts/refresh")
async def layouts_refresh() -> JSONResponse:
    updated = await asyncio.to_thread(
        layout.refresh_from_registry, hub.raw["machine"]
    )
    if updated:
        await hub.refresh(reason=[{"action": "refresh-layouts", "subsystem": "layout"}])
    return JSONResponse({"updated": updated})


@app.post("/api/layout/reset")
async def layout_reset() -> JSONResponse:
    layout.reset_slots(hub.raw["machine"])
    await hub.refresh(reason=[{"action": "reset-layout", "subsystem": "layout"}])
    return JSONResponse({"ok": True})


@app.get("/api/layout/export")
async def layout_export() -> JSONResponse:
    key = layout.dmi_key(hub.raw.get("machine", {}))
    return JSONResponse(
        layout.export(hub.raw),
        headers={"Content-Disposition": f'attachment; filename="{key}.json"'},
    )


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    hub.clients.add(websocket)
    try:
        await websocket.send_text(
            json.dumps({"type": "snapshot", "data": hub.snapshot, "events": []})
        )
        while True:
            await websocket.receive_text()  # keepalive pings from the client
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(websocket)


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(prog="devicemap")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8808)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
