"""Cameras (video4linux) and bluetooth adapters."""

from __future__ import annotations

import fcntl
import glob
import os
import re
import struct

from ..sysfs import read, read_int

# VIDIOC_ENUM_FMT: _IOWR('V', 2, struct v4l2_fmtdesc[64 bytes])
_VIDIOC_ENUM_FMT = (3 << 30) | (64 << 16) | (ord("V") << 8) | 2
_V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
# greyscale/depth fourccs: a camera offering only these is an IR sensor
_GREY_FOURCC = {"GREY", "Y8  ", "Y10 ", "Y12 ", "Y16 ", "Y8I ", "Z16 "}


# per-node open counts, maintained by the server's inotify watcher on
# /dev/video*; used to attribute module-level streaming to one camera
VIDEO_OPEN_COUNTS: dict[str, int] = {}


def _camera_in_use(node: str, module_active: bool | None) -> bool | None:
    """The USB power state says the *module* streams; open counts (when
    we have observed any) say which node is actually held open."""
    if not module_active:
        return module_active  # False, or None when undetectable
    counts = VIDEO_OPEN_COUNTS
    if not counts or all(v == 0 for v in counts.values()):
        return True  # no open-tracking data: module-level fallback
    return counts.get(node, 0) > 0


_formats_cache: dict[str, list[str] | None] = {}


def _pixel_formats(node: str) -> list[str] | None:
    """Fourcc list of a video device, None if the node is unreadable.
    Cached after the first successful read: opening the node resumes the
    (runtime-suspended) camera, so we must not do it on every probe."""
    if node in _formats_cache and _formats_cache[node] is not None:
        return _formats_cache[node]
    try:
        f = open(f"/dev/{node}", "rb", buffering=0)
    except OSError:
        _formats_cache[node] = None
        return None
    formats = []
    with f:
        for index in range(32):
            buf = bytearray(64)
            struct.pack_into("II", buf, 0, index, _V4L2_BUF_TYPE_VIDEO_CAPTURE)
            try:
                fcntl.ioctl(f.fileno(), _VIDIOC_ENUM_FMT, buf)
            except OSError:  # EINVAL: past the last format
                break
            formats.append(buf[44:48].decode("ascii", "replace"))
    _formats_cache[node] = formats
    return formats


def _usb_parent(path: str) -> str | None:
    """Sysname of the USB device (e.g. '1-7') this class device sits on."""
    matches = re.findall(r"/(\d+-[\d.]+)(?=/|$)", os.path.realpath(path))
    return matches[-1] if matches else None


def cameras() -> list[dict]:
    """One entry per capture device (index 0 of each parent), so a webcam
    with several /dev/video* nodes counts once."""
    cams = []
    for path in sorted(glob.glob("/sys/class/video4linux/video*")):
        if read_int(f"{path}/index") != 0:
            continue
        iface = re.search(r"/(\d+-[\d.]+:\d+\.\d+)(?=/|$)", os.path.realpath(path))
        node = os.path.basename(path)
        usb_parent = _usb_parent(path)
        # read BEFORE probing formats: our own open would resume the device
        module_active = None
        if usb_parent:
            status = read(f"/sys/bus/usb/devices/{usb_parent}/power/runtime_status")
            if status:
                module_active = status == "active"
        in_use = _camera_in_use(node, module_active)
        # the USB product string is cleaner than the 31-char-truncated
        # v4l2 name
        name = None
        if usb_parent:
            name = read(f"/sys/bus/usb/devices/{usb_parent}/product")
        if name:
            name = name.replace("_", " ").strip()
        formats = _pixel_formats(node)
        infrared = None
        if formats:
            infrared = all(f in _GREY_FOURCC for f in formats)
        cams.append(
            {
                "kind": "camera",
                "node": node,
                "name": name or read(f"{path}/name"),
                "usb_parent": usb_parent,
                "usb_interface": iface.group(1) if iface else None,
                "formats": formats,
                "infrared": infrared,
                "in_use": in_use,
            }
        )
    return cams


def bluetooth() -> list[dict]:
    return [
        {
            "kind": "bluetooth",
            "name": os.path.basename(p),
            "usb_parent": _usb_parent(p),
        }
        for p in sorted(glob.glob("/sys/class/bluetooth/hci*"))
        # hciN only: hciN:M entries are ACL connection handles (M3 will
        # use them for live connection state)
        if ":" not in os.path.basename(p)
    ]
