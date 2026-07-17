"""Cameras (video4linux) and bluetooth adapters."""

from __future__ import annotations

import glob
import os

from ..sysfs import read, read_int


def cameras() -> list[dict]:
    """One entry per capture device (index 0 of each parent), so a webcam
    with several /dev/video* nodes counts once."""
    cams = []
    for path in sorted(glob.glob("/sys/class/video4linux/video*")):
        if read_int(f"{path}/index") != 0:
            continue
        cams.append(
            {
                "kind": "camera",
                "node": os.path.basename(path),
                "name": read(f"{path}/name"),
            }
        )
    return cams


def bluetooth() -> list[dict]:
    return [
        {"kind": "bluetooth", "name": os.path.basename(p)}
        for p in sorted(glob.glob("/sys/class/bluetooth/hci*"))
        if "/" not in os.path.relpath(p, "/sys/class/bluetooth")
    ]
