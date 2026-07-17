"""Display connectors (HDMI, DisplayPort, eDP...) from the DRM class."""

from __future__ import annotations

import glob
import os
import re

from ..sysfs import read

DRM = "/sys/class/drm"

_KINDS = {
    "HDMI-A": "hdmi",
    "HDMI-B": "hdmi",
    "DP": "dp",
    "eDP": "edp",
    "LVDS": "lvds",
    "VGA": "vga",
    "DVI-I": "dvi",
    "DVI-D": "dvi",
    "DSI": "dsi",
}


def probe() -> dict:
    """Return {'external': [...], 'internal': [...]} display connectors."""
    external, internal = [], []
    for path in sorted(glob.glob(f"{DRM}/card[0-9]*-*")):
        name = os.path.basename(path)
        m = re.fullmatch(r"card\d+-(.+)-(\d+)", name)
        if not m or m.group(1) == "Writeback":
            continue
        conn_type = m.group(1)
        kind = _KINDS.get(conn_type, conn_type.lower())
        info = {
            "id": f"{m.group(1)}-{m.group(2)}",
            "kind": kind,
            "status": read(f"{path}/status"),
            "enabled": read(f"{path}/enabled"),
        }
        (internal if kind in ("edp", "lvds", "dsi") else external).append(info)
    return {"external": external, "internal": internal}
