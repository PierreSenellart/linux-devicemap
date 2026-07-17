"""Bluetooth adapters and devices via BlueZ over the system D-Bus,
queried with `busctl -j` (works unprivileged, no extra dependencies)."""

from __future__ import annotations

import json
import shutil
import subprocess

_BUSCTL = shutil.which("busctl")


def _prop(iface: dict, name: str):
    p = iface.get(name)
    return p.get("data") if isinstance(p, dict) else None


def probe() -> dict:
    empty = {"available": False, "adapters": [], "devices": []}
    if not _BUSCTL:
        return empty
    try:
        r = subprocess.run(
            [
                _BUSCTL,
                "-j",
                "call",
                "org.bluez",
                "/",
                "org.freedesktop.DBus.ObjectManager",
                "GetManagedObjects",
            ],
            capture_output=True,
            timeout=5,
        )
        objects = json.loads(r.stdout)["data"][0]
    except (OSError, subprocess.TimeoutExpired, ValueError, LookupError):
        return empty
    adapters, devices = [], []
    for path, ifaces in sorted(objects.items()):
        if "org.bluez.Adapter1" in ifaces:
            a = ifaces["org.bluez.Adapter1"]
            adapters.append(
                {
                    "id": path.rsplit("/", 1)[-1],
                    "alias": _prop(a, "Alias"),
                    "powered": bool(_prop(a, "Powered")),
                }
            )
        if "org.bluez.Device1" in ifaces:
            d = ifaces["org.bluez.Device1"]
            devices.append(
                {
                    "address": _prop(d, "Address"),
                    "name": _prop(d, "Alias") or _prop(d, "Name"),
                    "icon": _prop(d, "Icon"),
                    "connected": bool(_prop(d, "Connected")),
                    "paired": bool(_prop(d, "Paired")),
                    "battery": _prop(ifaces.get("org.bluez.Battery1", {}), "Percentage"),
                }
            )
    return {"available": True, "adapters": adapters, "devices": devices}
