"""Chassis layouts (per-model port geometry) and machine profiles
(locally calibrated bindings and position edits overriding the layout).

`layouts/` is the community registry (inert JSON keyed by DMI slug).
When a machine has no entry, a *skeleton* layout is derived from the
kernel's own port list so the editor and calibration wizard can build a
real layout from scratch."""

from __future__ import annotations

import json
import os
import re

BASE = os.path.dirname(os.path.dirname(__file__))
LAYOUTS = os.path.join(BASE, "layouts")
PROFILES = os.path.join(BASE, "profiles")

# slot types with no kernel-visible state (nothing to bind or calibrate)
PASSIVE_TYPES = {"sim", "lock", "smartcard"}

_SKELETON_KINDS = ("usb-c", "usb-a", "hdmi", "dp", "vga", "dvi", "sd", "audio-jack")

# default faces per form factor: laptops carry ports on the two side
# edges, desktops on 2D panels (the rear I/O panel holds nearly all of
# them). The frontend owns the drawn geometry; these are just the names a
# skeleton spreads slots across.
_FACES = {"laptop": ("left", "right"), "desktop": ("rear", "front", "top")}
_SKELETON_COLS = 4  # rear-panel grid width for a desktop skeleton


def _xy(pos) -> dict:
    """Normalize a slot position to {x, y}. Layouts written before
    positions were 2D carry a bare scalar: that was the coordinate along a
    side edge, i.e. y."""
    if isinstance(pos, dict):
        return {"x": float(pos.get("x") or 0.0), "y": float(pos.get("y") or 0.0)}
    return {"x": 0.0, "y": float(pos or 0.0)}


def _clamp(v: float) -> float:
    return round(max(0.0, min(0.95, v)), 3)


def _spread(i: int, n: int, lo: float = 0.03, hi: float = 0.93) -> float:
    """`i` of `n` evenly spread across a face, so a skeleton never places
    slots off the face however many ports the machine has."""
    if n <= 1:
        return round((lo + hi) / 2, 3)
    return round(lo + i * (hi - lo) / (n - 1), 3)


def dmi_key(machine: dict) -> str:
    slug = f"{machine.get('vendor') or ''}-{machine.get('product') or ''}".lower()
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")


def _load_json(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _profile_path(machine: dict) -> str:
    return f"{PROFILES}/{dmi_key(machine)}.json"


def _save_profile(machine: dict, profile: dict) -> None:
    os.makedirs(PROFILES, exist_ok=True)
    with open(_profile_path(machine), "w") as f:
        json.dump(profile, f, indent=1)
        f.write("\n")


def save_binding(machine: dict, slot_id: str, binding: dict) -> None:
    profile = _load_json(_profile_path(machine)) or {}
    profile.setdefault("bindings", {})[slot_id] = binding
    _save_profile(machine, profile)


def reset_slots(machine: dict) -> None:
    """Drop local position/side overrides, restoring registry geometry.
    Calibration bindings are kept."""
    profile = _load_json(_profile_path(machine)) or {}
    profile.pop("slots", None)
    _save_profile(machine, profile)


def save_slot(machine: dict, slot_id: str, side: str | None, x: float, y: float) -> None:
    profile = _load_json(_profile_path(machine)) or {}
    entry = profile.setdefault("slots", {}).setdefault(slot_id, {})
    if side:
        entry["side"] = side
    entry["pos"] = {"x": _clamp(x), "y": _clamp(y)}
    _save_profile(machine, profile)


def skeleton(snap: dict) -> dict:
    """Derive a draft layout from the kernel's port list alone: correct
    slots and bindings, made-up geometry (evenly spread, to be dragged
    into place by the user)."""
    machine = snap.get("machine", {})
    slots = []
    for port in snap.get("ports", []):
        if port.get("kind") not in _SKELETON_KINDS:
            continue
        slots.append(
            {
                "id": port["id"],
                "type": port["kind"],
                "label": f"{port['kind']} ({port['id']})",
                "pos": {"x": 0.0, "y": 0.0},
                "binding": binding_for_port(port),
            }
        )
    if machine.get("form_factor") == "desktop":
        # everything starts on the rear panel, laid out in a grid; the
        # other faces stay empty until the user drags slots onto them
        rows = max(1, -(-len(slots) // _SKELETON_COLS))
        for i, slot in enumerate(slots):
            slot["pos"] = {
                "x": _spread(i % _SKELETON_COLS, _SKELETON_COLS),
                "y": _spread(i // _SKELETON_COLS, rows),
            }
        sides = {face: [] for face in _FACES["desktop"]}
        sides["rear"] = slots
    else:
        half = max(1, (len(slots) + 1) // 2)
        for i, slot in enumerate(slots):
            slot["pos"] = {"x": 0.0, "y": _spread(i % half, half)}
        left, right = _FACES["laptop"]
        sides = {left: slots[:half], right: slots[half:]}
    return {
        "dmi": {"vendor": machine.get("vendor"), "product": machine.get("product")},
        "status": "skeleton",
        "hidden": [],
        "sides": sides,
    }


def load(machine: dict, snap: dict | None = None) -> dict | None:
    """Layout for this machine (registry entry, or skeleton if `snap` is
    given), with profile bindings and slot overrides merged in."""
    key = dmi_key(machine)
    lay = _load_json(f"{LAYOUTS}/{key}.json")
    if not lay:
        if snap is None:
            return None
        lay = skeleton(snap)
    profile = _load_json(f"{PROFILES}/{key}.json") or {}
    bindings = profile.get("bindings", {})
    overrides = profile.get("slots", {})
    new_sides: dict[str, list] = {side: [] for side in lay.get("sides", {})}
    for side, slots in lay.get("sides", {}).items():
        for slot in slots:
            if slot["id"] in bindings:
                slot["binding"] = bindings[slot["id"]]
            override = overrides.get(slot["id"])
            if override:
                slot["pos"] = _xy(override.get("pos", slot.get("pos")))
                side_final = override.get("side", side)
            else:
                slot["pos"] = _xy(slot.get("pos"))
                side_final = side
            new_sides.setdefault(side_final, []).append(slot)
    # reading order within a face: rows top→bottom, then left→right
    lay["sides"] = {
        s: sorted(slots, key=lambda x: (x["pos"]["y"], x["pos"]["x"]))
        for s, slots in new_sides.items()
    }
    lay["key"] = key
    lay["edited"] = bool(overrides)
    return lay


def export(snap: dict) -> dict:
    """Shareable registry entry: current layout with local bindings and
    position edits promoted in, computed/local-only fields stripped."""
    lay = load(snap["machine"], snap) or {}
    sides = {}
    for side, slots in lay.get("sides", {}).items():
        sides[side] = [
            {k: v for k, v in slot.items() if k != "port_id"} for slot in slots
        ]
    return {
        "dmi": lay.get("dmi")
        or {
            "vendor": snap["machine"].get("vendor"),
            "product": snap["machine"].get("product"),
        },
        "status": "draft" if lay.get("status") == "skeleton" else lay.get("status"),
        "hidden": lay.get("hidden", []),
        "source": lay.get("source"),
        "sides": sides,
    }


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
    lay = load(snap["machine"], snap)
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
        "edited": lay.get("edited", False),
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
