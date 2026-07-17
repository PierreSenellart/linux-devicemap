"""Small helpers for reading sysfs/procfs."""

from __future__ import annotations

import os


def read(path: str) -> str | None:
    """Read a sysfs attribute, stripped; None if absent or unreadable."""
    try:
        with open(path, "rb") as f:
            return f.read().decode(errors="replace").strip()
    except OSError:
        return None


def read_int(path: str) -> int | None:
    v = read(path)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def link_base(path: str) -> str | None:
    """Basename of a symlink target; None if not a symlink."""
    try:
        return os.path.basename(os.readlink(path))
    except OSError:
        return None


def listdir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []
