"""Chassis layouts (per-model port geometry) and machine profiles
(locally calibrated bindings overriding the layout's defaults)."""

from __future__ import annotations

import json
import os
import re

BASE = os.path.dirname(os.path.dirname(__file__))
LAYOUTS = os.path.join(BASE, "layouts")
PROFILES = os.path.join(BASE, "profiles")

# slot types with no kernel-visible state (nothing to bind or calibrate)
PASSIVE_TYPES = {"sim", "lock", "smartcard"}


def dmi_key(machine: dict) -> str:
    slug = f"{machine.get('vendor') or ''}-{machine.get('product') or ''}".lower()
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")


def _load_json(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load(machine: dict) -> dict | None:
    """Layout for this machine, with profile bindings merged in."""
    key = dmi_key(machine)
    lay = _load_json(f"{LAYOUTS}/{key}.json")
    if not lay:
        return None
    profile = _load_json(f"{PROFILES}/{key}.json") or {}
    bindings = profile.get("bindings", {})
    for slots in lay.get("sides", {}).values():
        for slot in slots:
            if slot["id"] in bindings:
                slot["binding"] = bindings[slot["id"]]
    lay["key"] = key
    return lay


def save_binding(machine: dict, slot_id: str, binding: dict) -> None:
    os.makedirs(PROFILES, exist_ok=True)
    path = f"{PROFILES}/{dmi_key(machine)}.json"
    profile = _load_json(path) or {}
    profile.setdefault("bindings", {})[slot_id] = binding
    with open(path, "w") as f:
        json.dump(profile, f, indent=1)
        f.write("\n")


def _matches(binding: dict | None, port: dict) -> bool:
    if not binding:
        return False
    if "typec" in binding:
        return port.get("typec") == binding["typec"]
    if "usb_ports" in binding:
        return bool(set(binding["usb_ports"]) & set(port.get("usb_ports") or []))
    if "drm" in binding:
        return port["id"] == binding["drm"]
    if "mmc" in binding:
        return port.get("kind") == "sd" and port["id"] == binding["mmc"]
    if "jack" in binding:
        return port.get("kind") == "audio-jack"
    return False


def binding_for_port(port: dict) -> dict | None:
    """The binding to store when a calibration event lands on `port`."""
    if port.get("typec"):
        return {"typec": port["typec"]}
    if port.get("usb_ports"):
        return {"usb_ports": port["usb_ports"]}
    if port.get("kind") in ("hdmi", "dp", "vga", "dvi"):
        return {"drm": port["id"]}
    if port.get("kind") == "sd":
        return {"mmc": port["id"]}
    if port.get("kind") == "audio-jack":
        return {"jack": True}
    return None


def compose(snap: dict, calibration: dict | None) -> dict:
    """Layout section of the published state: slots resolved to ports."""
    lay = load(snap["machine"])
    if not lay:
        return {"available": False}
    out = {
        "available": True,
        "status": lay.get("status"),
        "key": lay["key"],
        "sides": {},
        "unbound": [],
        # connectors with no physical plug (phantom or alt-mode paths):
        # the UI hides them while disconnected
        "hidden": lay.get("hidden", []),
        "calibration": calibration,
    }
    for side, slots in lay.get("sides", {}).items():
        rendered = []
        for slot in slots:
            s = dict(slot)
            s["port_id"] = next(
                (p["id"] for p in snap["ports"] if _matches(slot.get("binding"), p)),
                None,
            )
            if not slot.get("binding") and slot.get("type") not in PASSIVE_TYPES:
                out["unbound"].append(slot["id"])
            rendered.append(s)
        out["sides"][side] = rendered
    return out
