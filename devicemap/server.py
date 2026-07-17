"""HTTP + WebSocket server: serves the frontend, the current snapshot,
and pushes live updates."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import monitor, snapshot

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

DEBOUNCE_S = 0.4
BATTERY_POLL_S = 10


class Hub:
    """Holds the current snapshot and broadcasts updates to clients."""

    def __init__(self) -> None:
        self.snapshot: dict = {}
        self.clients: set[WebSocket] = set()

    async def broadcast(self, message: dict) -> None:
        data = json.dumps(message)
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                self.clients.discard(ws)

    async def refresh(self, reason: list[dict] | None = None) -> bool:
        new = await asyncio.to_thread(snapshot.build)
        old, self.snapshot = self.snapshot, new
        changed = _strip_ts(old) != _strip_ts(new)
        if changed:
            await self.broadcast(
                {"type": "snapshot", "data": new, "events": reason or []}
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


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    hub.snapshot = await asyncio.to_thread(snapshot.build)
    tasks = [asyncio.create_task(_event_loop()), asyncio.create_task(_battery_poll())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(lifespan=_lifespan)


@app.get("/api/state")
async def state() -> JSONResponse:
    return JSONResponse(hub.snapshot)


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
