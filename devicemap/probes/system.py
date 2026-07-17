"""Core system info: CPU model, memory size, GPUs."""

from __future__ import annotations

import math
import re
import shutil
import subprocess


def _gpus() -> list[str]:
    lspci = shutil.which("lspci")
    if not lspci:
        return []
    try:
        out = subprocess.run(
            [lspci, "-mm"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for line in out.splitlines():
        fields = re.findall(r'"([^"]*)"', line)
        if len(fields) >= 3 and re.search(
            r"VGA|3D|Display", fields[0], re.I
        ):
            vendor = re.sub(r" (Corporation|Corp\.?|Inc\.?|Ltd\.?).*", "", fields[1])
            gpus.append(f"{vendor} {fields[2]}")
    return gpus


def probe() -> dict:
    cpu = None
    sockets: set[str] = set()
    cores: set[tuple[str, str]] = set()
    threads = 0
    phys, core = "0", "0"
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if ":" not in line:
                    continue
                key, value = (s.strip() for s in line.split(":", 1))
                if key == "model name" and not cpu:
                    cpu = re.sub(r"\((R|TM|r|tm)\)", "", value)
                    cpu = re.sub(r"\s*(CPU\s*)?@.*$", "", cpu)
                    cpu = re.sub(r"\s+", " ", cpu).strip()
                elif key == "processor":
                    threads += 1
                elif key == "physical id":
                    phys = value
                    sockets.add(value)
                elif key == "core id":
                    core = value
                    cores.add((phys, core))
    except OSError:
        pass
    mem_gib = mem_installed = None
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_gib = round(int(line.split()[1]) * 1024 / 2**30, 1)
                    # MemTotal excludes firmware/iGPU reservations; round
                    # up to the next even GiB to get the installed size
                    mem_installed = math.ceil(mem_gib / 2) * 2
                    break
    except OSError:
        pass
    return {
        "cpu": cpu,
        "cores": len(cores) or None,
        "threads": threads or None,
        "memory_gib": mem_gib,
        "memory_installed_gb": mem_installed,
        "gpus": _gpus(),
    }
