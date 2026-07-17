"""SD/MMC card slots from /sys/class/mmc_host."""

from __future__ import annotations

import glob
import os

from ..sysfs import read, read_int


def probe() -> list[dict]:
    slots = []
    for host in sorted(glob.glob("/sys/class/mmc_host/mmc[0-9]*")):
        name = os.path.basename(host)
        card = None
        for card_path in glob.glob(f"{host}/{name}:*"):
            size_gb = None
            for size_path in glob.glob(f"{card_path}/block/*/size"):
                sectors = read_int(size_path)
                if sectors:
                    size_gb = round(sectors * 512 / 1e9, 1)
            card = {
                "name": read(f"{card_path}/name"),
                "type": read(f"{card_path}/type"),  # SD, SDIO, MMC
                "size_gb": size_gb,
            }
        slots.append({"id": name, "kind": "sd", "connected": card is not None, "card": card})
    return slots
