"""USB Type-C ports: roles, negotiated mode, partner, PD contracts."""

from __future__ import annotations

import glob
import os

from ..sysfs import listdir, read

TYPEC = "/sys/class/typec"


def _bracketed(value: str | None) -> str | None:
    """Parse '[source] sink' → 'source'."""
    if not value:
        return None
    if "[" in value:
        return value.split("[", 1)[1].split("]", 1)[0]
    return value


def _pd_capabilities(base: str) -> list[dict]:
    """Flatten a {source,sink}-capabilities directory into PDO dicts."""
    pdos = []
    for entry in listdir(base):
        if ":" not in entry:
            continue
        d = f"{base}/{entry}"
        pdo = {"type": entry.split(":", 1)[1]}
        for attr in (
            "voltage",
            "maximum_voltage",
            "minimum_voltage",
            "operational_current",
            "maximum_current",
        ):
            v = read(f"{d}/{attr}")
            if v is not None:
                pdo[attr] = v
        pdos.append(pdo)
    return pdos


def probe() -> dict:
    """Return {typec port name → info}."""
    ports = {}
    for path in sorted(glob.glob(f"{TYPEC}/port[0-9]*")):
        name = os.path.basename(path)
        if "-" in name:  # skip portN-partner, portN-cable
            continue
        partner_path = f"{path}-partner"
        partner = None
        if os.path.isdir(partner_path):
            partner = {
                "accessory_mode": read(f"{partner_path}/accessory_mode"),
                "usb_pd": read(f"{partner_path}/supports_usb_power_delivery"),
                "source_pdos": _pd(f"{partner_path}/usb_power_delivery", "source"),
            }
        ports[name] = {
            "power_role": _bracketed(read(f"{path}/power_role")),
            "data_role": _bracketed(read(f"{path}/data_role")),
            "mode": read(f"{path}/power_operation_mode"),
            "partner": partner,
            "sink_pdos": _pd(f"{path}/usb_power_delivery", "sink"),
        }
    return ports


def _pd(pd_link: str, direction: str) -> list[dict] | None:
    """PDOs from a usb_power_delivery link (on a port or a partner)."""
    caps = f"{pd_link}/{direction}-capabilities"
    if not os.path.isdir(caps):
        return None
    return _pd_capabilities(caps)
