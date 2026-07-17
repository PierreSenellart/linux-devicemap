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


def _edid_name(path: str) -> str | None:
    """Monitor model name from the EDID display-name descriptor."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if len(data) < 128:
        return None
    fallback = None
    for offset in (54, 72, 90, 108):
        block = data[offset : offset + 18]
        if block[:3] != b"\x00\x00\x00":
            continue
        text = block[5:18].split(b"\x0a")[0]
        text = bytes(c for c in text if 0x20 <= c < 0x7F).decode().strip()
        if block[3] == 0xFC and text:  # display product name
            return text
        if block[3] == 0xFE and text and not fallback:  # unspecified text
            fallback = text  # often the panel part number on laptops
    return fallback


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
        status = read(f"{path}/status")
        info = {
            "id": f"{m.group(1)}-{m.group(2)}",
            "kind": kind,
            "status": status,
            "enabled": read(f"{path}/enabled"),
            "monitor": _edid_name(f"{path}/edid") if status == "connected" else None,
        }
        (internal if kind in ("edp", "lvds", "dsi") else external).append(info)
    return {"external": external, "internal": internal}
