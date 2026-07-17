"""Assemble the normalized machine snapshot from all probes."""

from __future__ import annotations

import re
import time

from .probes import (
    audio,
    block,
    bt,
    dmi,
    drm,
    inputs,
    media,
    mmc,
    net,
    power,
    system,
    typec,
    usb,
)


def _attach(device: dict | None, key: str, by_parent: dict) -> None:
    """Recursively attach per-USB-device info (net interfaces, block
    devices) to the device tree."""
    if not device:
        return
    found = by_parent.get(device["sysname"])
    if not found:
        # merged hub halves keep their original sysnames in 'halves'
        found = [
            i for h in device.get("halves", []) for i in by_parent.get(h, [])
        ]
    if found:
        device[key] = found
    for child in device.get("children", []):
        _attach(child, key, by_parent)


def _num(value: str | None) -> float | None:
    """'3000mA' → 3000.0"""
    if not value:
        return None
    m = re.match(r"(\d+)", value)
    return float(m.group(1)) if m else None


def _pdo_watts(pdos: list[dict] | None) -> float | None:
    """Highest wattage offered/accepted across a PDO list."""
    best = None
    for pdo in pdos or []:
        mv = _num(pdo.get("voltage")) or _num(pdo.get("maximum_voltage"))
        ma = _num(pdo.get("operational_current")) or _num(pdo.get("maximum_current"))
        if mv and ma:
            best = max(best or 0.0, mv * ma / 1e6)
    return round(best, 1) if best else None


# wattage implied by non-PD Type-C current modes (at 5 V)
_MODE_WATTS = {"3.0A": 15.0, "1.5A": 7.5, "default": 2.5}


def _prune_inputs(device: dict | None) -> None:
    """Drop input names that just repeat the USB device's own identity;
    what remains are genuinely distinct peripherals (e.g. devices paired
    behind a wireless receiver)."""
    if not device:
        return
    names = device.get("hid_inputs")
    if names:
        own = (device.get("product") or "").strip().lower()
        kept = [n for n in names if n.strip().lower() != own or not own]
        if kept:
            device["hid_inputs"] = kept
        else:
            device.pop("hid_inputs", None)
    for child in device.get("children", []):
        _prune_inputs(child)


def build() -> dict:
    usb_info = usb.probe()
    typec_info = typec.probe()
    drm_info = drm.probe()
    power_info = power.probe()
    input_info = inputs.probe()
    net_info = net.probe()

    net_by_parent: dict[str, list] = {}
    for iface in net_info:
        if iface["usb_parent"]:
            net_by_parent.setdefault(iface["usb_parent"], []).append(iface)
    block_info = block.probe()
    block_by_parent = block_info["usb"]
    inputs_by_parent = inputs.usb_inputs()

    ports = []

    # USB connectors, with power facet merged in from typec + ucsi
    for conn in usb_info["connectors"]:
        port = dict(conn)
        tc = typec_info.get(conn["typec"]) if conn["typec"] else None
        if tc:
            charging_in = power_info["ucsi"].get(conn["typec"], False)
            port["power"] = {
                "role": tc["power_role"],
                "mode": tc["mode"],
                "partner_present": tc["partner"] is not None,
                "charging_in": charging_in,
                "source_pdos": (tc["partner"] or {}).get("source_pdos"),
                "sink_pdos": tc["sink_pdos"],
            }
            pw = port["power"]
            pw["watts_max_in"] = _pdo_watts(tc["sink_pdos"])
            pw["watts_in"] = None
            if pw["role"] == "sink" and pw["partner_present"]:
                if pw["mode"] == "usb_power_delivery":
                    pw["watts_in"] = _pdo_watts(pw["source_pdos"])
                else:
                    pw["watts_in"] = _MODE_WATTS.get(pw["mode"])
            # a power-only partner (charger) occupies the port even though
            # no USB device enumerates
            port["connected"] = port["device"] is not None or tc["partner"] is not None
        else:
            port["power"] = None
            port["connected"] = port["device"] is not None
        _attach(port["device"], "net", net_by_parent)
        _attach(port["device"], "storage", block_by_parent)
        _attach(port["device"], "hid_inputs", inputs_by_parent)
        _prune_inputs(port["device"])
        ports.append(port)

    # display connectors
    for d in drm_info["external"]:
        ports.append(
            {
                "id": d["id"],
                "kind": d["kind"],
                "connected": d["status"] == "connected",
                "device": None,
                "power": None,
                "status": d["status"],
                "monitor": d.get("monitor"),
            }
        )

    # SD/MMC card slots
    for slot in mmc.probe():
        ports.append(
            {
                "id": slot["id"],
                "kind": "sd",
                "connected": slot["connected"],
                "device": None,
                "power": None,
                "card": slot["card"],
            }
        )

    # audio jacks
    for j in input_info["jacks"]:
        connected = j["headphone"] or j["microphone"] if j["readable"] else None
        ports.append(
            {
                "id": j["id"],
                "kind": "audio-jack",
                "connected": connected,
                "device": None,
                "power": None,
                "jack": j,
            }
        )

    cams, bts = media.cameras(), media.bluetooth()
    bt_info = bt.probe()
    if bt_info["available"]:
        aliases = {a["id"]: a for a in bt_info["adapters"]}
        n_connected = sum(1 for d in bt_info["devices"] if d["connected"])
        for b in bts:
            a = aliases.get(b["name"])
            if a:
                b["name"] = f"{a['alias'] or b['name']}"
                b["status"] = (
                    f"{n_connected} connected" if a["powered"] else "off"
                )
    builtins = (
        list(input_info["builtins"])
        + cams
        + bts
        + audio.probe()
        + block_info["internal"]
    )
    for iface in net_info:
        if not iface["usb_parent"]:
            builtins.append({"kind": iface["kind"], "name": iface["ifname"], **iface})
    # internal USB devices already represented by a class device (camera,
    # bluetooth) are not listed a second time
    claimed = {b["usb_parent"] for b in cams + bts if b.get("usb_parent")}
    for hw in usb_info["hardwired"]:
        dev = hw["device"]
        if dev["sysname"] in claimed:
            continue
        builtins.append(
            {
                "kind": "usb-internal",
                "name": dev.get("product") or f"USB {dev['vid']}:{dev['pid']}",
                "classes": dev["classes"],
                "port": hw["port"],
            }
        )
    for d in drm_info["internal"]:
        builtins.append(
            {
                "kind": "display",
                "name": d["id"],
                "status": d["status"],
                "monitor": d.get("monitor"),
            }
        )

    return {
        "ts": time.time(),
        "machine": {**dmi.probe(), **system.probe()},
        "ports": ports,
        "builtins": builtins,
        "bluetooth": bt_info,
        "power": {
            "ac_online": power_info["ac_online"],
            "batteries": power_info["batteries"],
        },
        "capabilities": {
            "jack_state": any(j["readable"] for j in input_info["jacks"]) or None,
        },
    }
