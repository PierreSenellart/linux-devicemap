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
}

_LINE = re.compile(r"^UDEV\s+\[[\d.]+\]\s+(\S+)\s+(\S+)\s+\((\S+)\)")


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
