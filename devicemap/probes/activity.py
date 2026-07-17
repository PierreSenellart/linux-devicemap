"""Cheap activity signature for the fast in-use poll. Camera streaming
and audio capture/playback produce no udev events, so the server polls
this signature every couple of seconds and re-probes on change."""

from __future__ import annotations

import glob

from ..sysfs import read


def signature(state: dict) -> tuple:
    running = []
    for status in sorted(glob.glob("/proc/asound/card*/pcm*/sub*/status")):
        try:
            with open(status) as f:
                if "state: RUNNING" in f.read():
                    running.append(status)
        except OSError:
            pass
    cameras = []
    for builtin in state.get("builtins", []):
        if builtin.get("kind") == "camera" and builtin.get("usb_parent"):
            parent = builtin["usb_parent"]
            status = read(f"/sys/bus/usb/devices/{parent}/power/runtime_status")
            cameras.append(f"{parent}:{status}")
    return (tuple(running), tuple(sorted(set(cameras))))
