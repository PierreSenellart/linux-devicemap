"""Block devices on USB storage: media presence and capacity."""

from __future__ import annotations

import glob
import os
import re

from ..sysfs import read_int


def probe() -> dict[str, list[dict]]:
    """usb device sysname → its block devices (media state, size)."""
    out: dict[str, list[dict]] = {}
    for path in sorted(glob.glob("/sys/block/*")):
        real = os.path.realpath(path)
        if "/usb" not in real:
            continue
        parents = re.findall(r"/(\d+-[\d.]+)(?=/|$)", real)
        if not parents:
            continue
        sectors = read_int(f"{path}/size") or 0
        out.setdefault(parents[-1], []).append(
            {
                "dev": os.path.basename(path),
                "removable": bool(read_int(f"{path}/removable")),
                "media": sectors > 0,
                "size_gb": round(sectors * 512 / 1e9, 1) if sectors else None,
            }
        )
    return out
