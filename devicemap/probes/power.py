"""Power: AC adapter, battery, and per-Type-C-port UCSI source supplies."""

from __future__ import annotations

import glob
import os
import re

from ..sysfs import read, read_int

PSY = "/sys/class/power_supply"


def _battery(path: str) -> dict:
    watts = None
    power_now = read_int(f"{path}/power_now")
    if power_now is not None:
        watts = power_now / 1e6
    else:
        v = read_int(f"{path}/voltage_now")
        c = read_int(f"{path}/current_now")
        if v is not None and c is not None:
            watts = v * c / 1e12
    return {
        "name": os.path.basename(path),
        "status": read(f"{path}/status"),
        "capacity_pct": read_int(f"{path}/capacity"),
        "watts": round(watts, 2) if watts is not None else None,
        "model": read(f"{path}/model_name"),
    }


def probe() -> dict:
    """Return {'ac_online', 'batteries', 'ucsi': {typec port → online}}."""
    ac_online = None
    batteries = []
    ucsi = {}
    for path in sorted(glob.glob(f"{PSY}/*")):
        name = os.path.basename(path)
        typ = read(f"{path}/type")
        if typ == "Mains":
            online = read_int(f"{path}/online")
            if online is not None:
                ac_online = bool(ac_online) or bool(online)
        elif typ == "Battery":
            batteries.append(_battery(path))
        elif name.startswith("ucsi-source-psy-"):
            # ucsi-source-psy-USBC000:00K maps to typec portK-1
            m = re.search(r":(\d+)$", name)
            if m:
                ucsi[f"port{int(m.group(1)) - 1}"] = bool(read_int(f"{path}/online"))
    return {"ac_online": ac_online, "batteries": batteries, "ucsi": ucsi}
