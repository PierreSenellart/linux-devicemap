"""Built-in input devices (keyboard, touchpad) and audio jack state.

Jack state is read via the evdev EVIOCGSW ioctl on the jack's input
device node, which requires read access to /dev/input (typically the
`input` group). We feature-detect and report state as unknown otherwise.
"""

from __future__ import annotations

import array
import fcntl
import re

# switch event codes (linux/input-event-codes.h)
SW_HEADPHONE_INSERT = 0x02
SW_MICROPHONE_INSERT = 0x04
SW_LINEOUT_INSERT = 0x06

_EVIOCGSW_LEN = 8  # bytes: covers SW_MAX


def _eviocgsw(fd: int) -> int:
    """Return the switch-state bitmap of an evdev device."""
    # _IOC(_IOC_READ, 'E', 0x1b, len)
    request = (2 << 30) | (_EVIOCGSW_LEN << 16) | (ord("E") << 8) | 0x1B
    buf = array.array("B", [0] * _EVIOCGSW_LEN)
    fcntl.ioctl(fd, request, buf)
    return int.from_bytes(buf.tobytes(), "little")


def _parse_proc_input() -> list[dict]:
    devices = []
    try:
        with open("/proc/bus/input/devices") as f:
            blocks = f.read().split("\n\n")
    except OSError:
        return devices
    for block in blocks:
        name_m = re.search(r'^N: Name="(.*)"$', block, re.M)
        handlers_m = re.search(r"^H: Handlers=(.*)$", block, re.M)
        if not name_m:
            continue
        handlers = (handlers_m.group(1) if handlers_m else "").split()
        event = next((h for h in handlers if h.startswith("event")), None)
        devices.append({"name": name_m.group(1), "event": event})
    return devices


def jack_state(event: str | None) -> dict:
    state = {"readable": False, "headphone": None, "microphone": None}
    if not event:
        return state
    try:
        with open(f"/dev/input/{event}", "rb") as f:
            bits = _eviocgsw(f.fileno())
    except OSError:
        return state
    state["readable"] = True
    state["headphone"] = bool(bits >> SW_HEADPHONE_INSERT & 1)
    state["microphone"] = bool(bits >> SW_MICROPHONE_INSERT & 1)
    state["lineout"] = bool(bits >> SW_LINEOUT_INSERT & 1)
    return state


def probe() -> dict:
    """Return {'builtins': [...], 'jacks': [...]}."""
    builtins, jacks = [], []
    for dev in _parse_proc_input():
        name, lower = dev["name"], dev["name"].lower()
        if "jack" in lower and ("headset" in lower or "headphone" in lower or "mic" in lower):
            jacks.append(
                {
                    "id": name,
                    "kind": "audio-jack",
                    "event": dev["event"],
                    **jack_state(dev["event"]),
                }
            )
        elif "keyboard" in lower and "translated" in lower:
            builtins.append({"kind": "keyboard", "name": name})
        elif "touchpad" in lower:
            builtins.append({"kind": "touchpad", "name": name})
    return {"builtins": builtins, "jacks": jacks}
