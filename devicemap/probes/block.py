"""Block devices: USB storage (media presence, capacity, mounts) and
internal drives (NVMe/SATA, with capacity and mount points)."""

from __future__ import annotations

import glob
import os
import re

from ..sysfs import read, read_int

_SKIP = re.compile(r"^(loop|ram|zram|dm-|md|mmcblk)")  # mmc has its own probe


def _mounts() -> dict[str, str]:
    """block device name (e.g. 'nvme0n1p2') → mount point. Mounts on
    device-mapper targets (LUKS, LVM) are attributed to their underlying
    partitions via /sys/block/dm-*/slaves."""
    out: dict[str, str] = {}
    mapper: dict[str, str] = {}  # /dev/mapper name → dm-N
    for dm in glob.glob("/sys/block/dm-*"):
        name = read(f"{dm}/dm/name")
        if name:
            mapper[f"mapper/{name}"] = os.path.basename(dm)
    try:
        with open("/proc/mounts") as f:
            for line in f:
                dev, mnt = line.split()[:2]
                if not dev.startswith("/dev/"):
                    continue
                name = dev[5:]
                mnt = mnt.replace("\\040", " ")
                name = mapper.get(name, name)
                # walk dm devices down to their physical slaves
                seen = set()
                while name.startswith("dm-") and name not in seen:
                    seen.add(name)
                    slaves = os.listdir(f"/sys/block/{name}/slaves")
                    if not slaves:
                        break
                    name = slaves[0]
                out.setdefault(name, mnt)
    except OSError:
        pass
    return out


def _size_gb(path: str) -> float | None:
    sectors = read_int(f"{path}/size") or 0
    return round(sectors * 512 / 1e9, 1) if sectors else None


def _mount_list(path: str, name: str, mounts: dict) -> list[dict]:
    """Mounted filesystems on this disk (whole-disk or partitions)."""
    out = []
    if name in mounts:
        out.append({"dev": name, "mountpoint": mounts[name]})
    for part in sorted(glob.glob(f"{path}/{name}*")):
        pname = os.path.basename(part)
        if pname in mounts:
            out.append({"dev": pname, "mountpoint": mounts[pname]})
    return out


def probe() -> dict:
    """Return {'usb': {usb sysname: [devices]}, 'internal': [drives]}."""
    usb: dict[str, list[dict]] = {}
    internal: list[dict] = []
    mounts = _mounts()
    for path in sorted(glob.glob("/sys/block/*")):
        name = os.path.basename(path)
        if _SKIP.match(name) or not os.path.isdir(f"{path}/device"):
            continue
        real = os.path.realpath(path)
        entry = {
            "dev": name,
            "removable": bool(read_int(f"{path}/removable")),
            "media": (read_int(f"{path}/size") or 0) > 0,
            "size_gb": _size_gb(path),
            "mounts": _mount_list(path, name, mounts),
        }
        if "/usb" in real:
            parents = re.findall(r"/(\d+-[\d.]+)(?=/|$)", real)
            if parents:
                usb.setdefault(parents[-1], []).append(entry)
        else:
            model = read(f"{path}/device/model")
            # SCSI peripheral type 5 is CD/DVD/BD; Linux always names those
            # sr[0-9]. Present as a front optical bay, not an internal disk.
            optical = read_int(f"{path}/device/type") == 5 or bool(
                re.match(r"sr\d", name)
            )
            internal.append(
                {
                    "kind": "optical" if optical else "disk",
                    "name": (model or name).strip(),
                    "optical": optical,
                    **entry,
                }
            )
    return {"usb": usb, "internal": internal}
