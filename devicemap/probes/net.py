"""Physical network interfaces (ethernet, wifi), joined to their USB or
platform parent; wifi link details via `iw` when available."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess

from ..sysfs import read, read_int

NET = "/sys/class/net"

_IW = shutil.which("iw")


def wifi_link(ifname: str) -> dict | None:
    if not _IW:
        return None
    try:
        out = subprocess.run(
            [_IW, "dev", ifname, "link"],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    if "Connected to" not in out:
        return {"connected": False}
    def grab(pattern):
        m = re.search(pattern, out, re.M)
        return m.group(1) if m else None
    return {
        "connected": True,
        "ssid": grab(r"^\s*SSID: (.*)$"),
        "signal_dbm": grab(r"^\s*signal: (-?\d+) dBm"),
        "freq_mhz": grab(r"^\s*freq: ([\d.]+)"),
        "rx_bitrate": grab(r"^\s*rx bitrate: ([\d.]+ \S+)"),
        "tx_bitrate": grab(r"^\s*tx bitrate: ([\d.]+ \S+)"),
    }


def probe() -> list[dict]:
    """One entry per physical interface. `usb_parent` is the sysname of
    the USB device it belongs to (e.g. '4-2.1'), None for built-ins."""
    interfaces = []
    for path in sorted(glob.glob(f"{NET}/*")):
        ifname = os.path.basename(path)
        try:
            devpath = os.path.realpath(f"{path}/device")
        except OSError:
            continue
        if not os.path.isdir(f"{path}/device"):
            continue  # virtual interface (lo, bridges, ...)
        wireless = os.path.isdir(f"{path}/phy80211")
        usb_matches = re.findall(r"/(\d+-[\d.]+)(?=/|$)", devpath)
        carrier = read_int(f"{path}/carrier")  # unreadable while iface down
        info = {
            "ifname": ifname,
            "kind": "wifi" if wireless else "ethernet",
            "operstate": read(f"{path}/operstate"),
            "carrier": None if carrier is None else bool(carrier),
            "speed_mbps": read_int(f"{path}/speed"),
            "mac": read(f"{path}/address"),
            "usb_parent": usb_matches[-1] if usb_matches else None,
        }
        if info["speed_mbps"] is not None and info["speed_mbps"] < 0:
            info["speed_mbps"] = None
        if wireless:
            info["wifi"] = wifi_link(ifname)
        interfaces.append(info)
    return interfaces
