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
CACHE = os.path.join(BASE, "layouts-cache")
REGISTRY_RAW = (
    "https://raw.githubusercontent.com/PierreSenellart/linux-devicemap/main/layouts"
)

# slot types with no kernel-visible state (nothing to bind or calibrate)
PASSIVE_TYPES = {"sim", "lock", "smartcard"}

_SKELETON_KINDS = ("usb-c", "usb-a", "hdmi", "dp", "vga", "dvi", "sd", "audio-jack")


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


def save_label(machine: dict, slot_id: str, label: str) -> None:
    profile = _load_json(_profile_path(machine)) or {}
    profile.setdefault("slots", {}).setdefault(slot_id, {})["label"] = label
    _save_profile(machine, profile)


def set_hidden(machine: dict, port_id: str, hidden: bool) -> None:
    """Locally hide/unhide a connector, on top of the layout's own list."""
    profile = _load_json(_profile_path(machine)) or {}
    h = profile.setdefault("hidden", {"add": [], "remove": []})
    for lst, member in (("add", hidden), ("remove", not hidden)):
        entries = h.setdefault(lst, [])
        if member and port_id not in entries:
            entries.append(port_id)
        if not member and port_id in entries:
            entries.remove(port_id)
    _save_profile(machine, profile)


def add_slot(machine: dict, port: dict) -> None:
    """Promote an unplaced port to a locally-added slot (draggable like
    any other; export bakes it into the shared layout)."""
    profile = _load_json(_profile_path(machine)) or {}
    profile.setdefault("extra_slots", {})[port["id"]] = {
        "id": port["id"],
        "type": port["kind"],
        "label": f"{port['kind']} ({port['id']})",
        "side": "left",
        "pos": 0.9,
        "binding": binding_for_port(port),
    }
    _save_profile(machine, profile)


def remove_extra_slot(machine: dict, slot_id: str) -> bool:
    profile = _load_json(_profile_path(machine)) or {}
    removed = profile.get("extra_slots", {}).pop(slot_id, None) is not None
    profile.get("slots", {}).pop(slot_id, None)  # drop its drag overrides too
    _save_profile(machine, profile)
    return removed


def refresh_from_registry(machine: dict) -> bool:
    """Fetch this machine's layout from the online registry (the repo's
    main branch) into the local cache. Explicit user action only."""
    import urllib.request

    key = dmi_key(machine)
    try:
        with urllib.request.urlopen(f"{REGISTRY_RAW}/{key}.json", timeout=10) as r:
            data = r.read()
        json.loads(data)  # validate before caching
    except Exception:
        return False
    os.makedirs(CACHE, exist_ok=True)
    with open(f"{CACHE}/{key}.json", "wb") as f:
        f.write(data)
    return True


def reset_slots(machine: dict) -> None:
    """Drop local position/side overrides, restoring registry geometry.
    Calibration bindings are kept."""
    profile = _load_json(_profile_path(machine)) or {}
    profile.pop("slots", None)
    _save_profile(machine, profile)


def save_slot(machine: dict, slot_id: str, side: str | None, pos: float) -> None:
    profile = _load_json(_profile_path(machine)) or {}
    entry = profile.setdefault("slots", {}).setdefault(slot_id, {})
    if side:
        entry["side"] = side
    entry["pos"] = round(max(0.0, min(0.95, pos)), 3)
    _save_profile(machine, profile)


def skeleton(snap: dict) -> dict:
    """Derive a draft layout from the kernel's port list alone: correct
    slots and bindings, made-up geometry (all evenly spread, to be
    dragged into place by the user)."""
    slots = []
    for port in snap.get("ports", []):
        if port.get("kind") not in _SKELETON_KINDS:
            continue
        binding = binding_for_port(port)
        slots.append(
            {
                "id": port["id"],
                "type": port["kind"],
                "label": f"{port['kind']} ({port['id']})",
                "pos": 0.0,
                "binding": binding,
            }
        )
    half = (len(slots) + 1) // 2
    for i, slot in enumerate(slots):
        slot["pos"] = round(0.05 + (i if i < half else i - half) * 0.12, 2)
    return {
        "dmi": {
            "vendor": snap.get("machine", {}).get("vendor"),
            "product": snap.get("machine", {}).get("product"),
        },
        "status": "skeleton",
        "hidden": [],
        "sides": {"left": slots[:half], "right": slots[half:]},
    }


def load(machine: dict, snap: dict | None = None) -> dict | None:
    """Layout for this machine (registry entry, or skeleton if `snap` is
    given), with profile bindings and slot overrides merged in."""
    key = dmi_key(machine)
    lay = _load_json(f"{LAYOUTS}/{key}.json") or _load_json(f"{CACHE}/{key}.json")
    if not lay:
        if snap is None:
            return None
        lay = skeleton(snap)
    profile = _load_json(f"{PROFILES}/{key}.json") or {}
    bindings = profile.get("bindings", {})
    overrides = profile.get("slots", {})
    hidden_edits = profile.get("hidden", {})
    lay["hidden"] = [
        h
        for h in dict.fromkeys(lay.get("hidden", []) + hidden_edits.get("add", []))
        if h not in hidden_edits.get("remove", [])
    ]
    new_sides: dict[str, list] = {side: [] for side in lay.get("sides", {})}
    for side, slots in lay.get("sides", {}).items():
        for slot in slots:
            if slot["id"] in bindings:
                slot["binding"] = bindings[slot["id"]]
            override = overrides.get(slot["id"])
            if override:
                slot["pos"] = override.get("pos", slot["pos"])
                slot["label"] = override.get("label", slot.get("label"))
                side_final = override.get("side", side)
            else:
                side_final = side
            new_sides.setdefault(side_final, []).append(slot)
    for sid, extra in profile.get("extra_slots", {}).items():
        slot = {k: v for k, v in extra.items() if k != "side"}
        slot["extra"] = True
        side_final = extra.get("side", "left")
        override = overrides.get(sid)
        if override:
            slot["pos"] = override.get("pos", slot["pos"])
            slot["label"] = override.get("label", slot.get("label"))
            side_final = override.get("side", side_final)
        new_sides.setdefault(side_final, []).append(slot)
    lay["sides"] = {
        s: sorted(slots, key=lambda x: x["pos"]) for s, slots in new_sides.items()
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
            {k: v for k, v in slot.items() if k not in ("port_id", "extra")}
            for slot in slots
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
