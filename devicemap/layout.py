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
CARDS = os.path.join(LAYOUTS, "cards")
PROFILES = os.path.join(BASE, "profiles")
CACHE = os.path.join(BASE, "layouts-cache")
REGISTRY_RAW = (
    "https://raw.githubusercontent.com/PierreSenellart/linux-devicemap/main/layouts"
)

# slot types with no kernel-visible state (nothing to bind or calibrate)
PASSIVE_TYPES = {"sim", "lock", "smartcard"}

_SKELETON_KINDS = ("usb-c", "usb-a", "hdmi", "dp", "vga", "dvi", "sd", "audio-jack")

# faces per form factor: laptops carry ports on the two side edges;
# desktops on the rear I/O shield, the front panel, and the PCIe bracket
# strip (populated per-unit from the card registry, not the machine
# layout). The frontend owns the drawn geometry; these are just the names.
_FACES = {"laptop": ("left", "right"), "desktop": ("rear", "front", "pcie")}
_SKELETON_COLS = 4  # rear-panel grid width for a desktop skeleton

# display kinds that a graphics card exposes on a PCIe bracket
_DISPLAY_KINDS = ("dp", "hdmi", "vga", "dvi")


def _faces(machine: dict) -> tuple[str, ...]:
    return _FACES.get(machine.get("form_factor") or "", _FACES["laptop"])


def _default_face(machine: dict) -> str:
    """Where a slot goes when nothing says otherwise: a laptop's left
    edge, a desktop's rear panel."""
    return _faces(machine)[0]


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
        "side": _default_face(machine),
        "pos": {"x": 0.5, "y": 0.9},
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


def save_slot(machine: dict, slot_id: str, side: str | None, x: float, y: float) -> None:
    profile = _load_json(_profile_path(machine)) or {}
    entry = profile.setdefault("slots", {}).setdefault(slot_id, {})
    if side:
        entry["side"] = side
    entry["pos"] = {"x": _clamp(x), "y": _clamp(y)}
    _save_profile(machine, profile)


def _card_slots(snap: dict, bound_drm: set) -> list:
    """Slots for discrete-GPU outputs, placed on the PCIe bracket face.
    Positions and labels come from the card registry (keyed by PCI id);
    an unknown card still gets one slot per output, evenly spread. These
    are per-unit — never written to the shared machine layout — so each
    machine renders its own card without a model-specific entry.

    Cards are ordered by PCI address (bus order); with the usual single
    card that is simply "the card". Each card gets a horizontal band on
    the face, so a second card stacks below the first."""
    discrete = [
        p
        for p in snap.get("ports", [])
        if p.get("discrete")
        and p.get("kind") in _DISPLAY_KINDS
        and p["id"] not in bound_drm
    ]
    by_card: dict[str, list] = {}
    for p in discrete:
        by_card.setdefault(p["pci"] or "", []).append(p)
    slots = []
    n = len(by_card) or 1
    for ci, (_pci, conns) in enumerate(sorted(by_card.items())):
        conns.sort(key=lambda p: p["id"])
        card = None
        ids = conns[0].get("pci_ids")
        if ids:
            card = _load_json(f"{CARDS}/{ids.replace(':', '-')}.json")
        outputs = (card or {}).get("outputs") or []
        band_lo, band_h = ci / n, 1 / n
        for oi, conn in enumerate(conns):
            out = outputs[oi] if oi < len(outputs) else {}
            ox = out.get("pos", {}).get("x")
            oy = out.get("pos", {}).get("y", 0.5)
            slots.append(
                {
                    "id": f"card-{conn['id']}",
                    "type": conn["kind"],
                    "label": out.get("label")
                    or (f"{card['name']}" if card else f"{conn['kind'].upper()} (card)"),
                    "pos": {
                        "x": _spread(oi, len(conns)) if ox is None else ox,
                        "y": round(band_lo + oy * band_h, 3),
                    },
                    "binding": {"drm": conn["id"]},
                    "card": True,
                }
            )
    return slots


def skeleton(snap: dict) -> dict:
    """Derive a draft layout from the kernel's port list alone: correct
    slots and bindings, made-up geometry (evenly spread, to be dragged
    into place by the user)."""
    machine = snap.get("machine", {})
    slots = []
    for port in snap.get("ports", []):
        if port.get("kind") not in _SKELETON_KINDS:
            continue
        # discrete-GPU outputs are placed on the PCIe face from the card
        # registry, not spread with the board ports
        if port.get("discrete") and port.get("kind") in _DISPLAY_KINDS:
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
                slot["pos"] = _xy(override.get("pos", slot.get("pos")))
                slot["label"] = override.get("label", slot.get("label"))
                side_final = override.get("side", side)
            else:
                slot["pos"] = _xy(slot.get("pos"))
                side_final = side
            new_sides.setdefault(side_final, []).append(slot)
    for sid, extra in profile.get("extra_slots", {}).items():
        slot = {k: v for k, v in extra.items() if k != "side"}
        slot["extra"] = True
        side_final = extra.get("side", _default_face(machine))
        override = overrides.get(sid)
        if override:
            slot["pos"] = _xy(override.get("pos", slot.get("pos")))
            slot["label"] = override.get("label", slot.get("label"))
            side_final = override.get("side", side_final)
        else:
            slot["pos"] = _xy(slot.get("pos"))
        # a slot added before this machine's faces were known (or on
        # another form factor) would hang off a face that is never drawn
        if side_final not in _faces(machine):
            side_final = _default_face(machine)
        new_sides.setdefault(side_final, []).append(slot)
    # PCIe-card outputs, generated per-unit from the card registry (only
    # for a machine whose faces include a bracket strip, i.e. desktops).
    # A card connector already bound by the machine layout is left to it.
    if snap is not None and "pcie" in _faces(machine):
        bound_drm = {
            (s.get("binding") or {}).get("drm")
            for slots in new_sides.values()
            for s in slots
        }
        for slot in _card_slots(snap, bound_drm):
            override = overrides.get(slot["id"])
            if override:
                slot["pos"] = _xy(override.get("pos", slot["pos"]))
                slot["label"] = override.get("label", slot["label"])
                new_sides.setdefault(override.get("side", "pcie"), []).append(slot)
            else:
                new_sides.setdefault("pcie", []).append(slot)
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
        kept = [
            {k: v for k, v in slot.items() if k not in ("port_id", "extra", "card")}
            for slot in slots
            if not slot.get("card")  # card outputs are per-unit, not shared
        ]
        if kept:
            sides[side] = kept
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
