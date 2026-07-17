"""Hotplug event stream based on `udevadm monitor` (works unprivileged,
no libudev binding required)."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

SUBSYSTEMS = {
    "usb",
    "typec",
    "drm",
    "power_supply",
    "input",
    "sound",
    "video4linux",
    "bluetooth",
}

_LINE = re.compile(r"^UDEV\s+\[[\d.]+\]\s+(\S+)\s+(\S+)\s+\((\S+)\)")


def start_rtnetlink_watcher(loop, on_event) -> list:
    """Watch link state changes (ethernet cable, wifi association) via an
    rtnetlink socket; carrier changes produce no udev events."""
    import socket

    RTMGRP_LINK = 1
    try:
        sock = socket.socket(
            socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE
        )
        sock.bind((0, RTMGRP_LINK))
    except OSError:
        return []
    sock.setblocking(False)

    def ready():
        try:
            while sock.recv(65535):
                pass
        except (BlockingIOError, OSError):
            pass
        on_event({"action": "change", "devpath": "link", "subsystem": "net"})

    loop.add_reader(sock.fileno(), ready)
    return [lambda: (loop.remove_reader(sock.fileno()), sock.close())]


def start_jack_watchers(loop, on_event) -> list:
    """Watch jack switch input devices for plug/unplug events (jack
    insertion produces evdev events, not udev events). Feature-detected:
    devices we cannot open are skipped. Returns closers."""
    import os

    from .probes import inputs

    closers = []
    for jack in inputs.probe()["jacks"]:
        if not jack.get("readable") or not jack.get("event"):
            continue
        try:
            f = open(f"/dev/input/{jack['event']}", "rb", buffering=0)
        except OSError:
            continue
        os.set_blocking(f.fileno(), False)

        def ready(f=f, name=jack["id"]):
            try:
                while f.read(4096):
                    pass
            except OSError:
                pass
            on_event({"action": "change", "devpath": name, "subsystem": "sound"})

        loop.add_reader(f.fileno(), ready)
        closers.append(lambda f=f: (loop.remove_reader(f.fileno()), f.close()))
    return closers


async def events() -> AsyncIterator[dict]:
    """Yield {'action', 'devpath', 'subsystem'} for relevant udev events.

    Restarts udevadm if it dies (e.g. after suspend/resume)."""
    while True:
        proc = await asyncio.create_subprocess_exec(
            "udevadm",
            "monitor",
            "--udev",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdout is not None
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                m = _LINE.match(line.decode(errors="replace"))
                if not m:
                    continue
                action, devpath, subsystem = m.groups()
                if subsystem in SUBSYSTEMS:
                    yield {
                        "action": action,
                        "devpath": devpath,
                        "subsystem": subsystem,
                    }
        finally:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            await proc.wait()
        await asyncio.sleep(2)  # udevadm exited; retry
