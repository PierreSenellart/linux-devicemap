"""Machine identity from DMI."""

from __future__ import annotations

from ..sysfs import read

DMI = "/sys/class/dmi/id"

# SMBIOS chassis types that mean "portable computer with a lid"
_LAPTOP_CHASSIS = {"8", "9", "10", "14", "31", "32"}
# stationary machines whose ports sit on a rear I/O panel: desktop, low
# profile, pizza box, mini tower, tower, space-saving, lunch box, main
# server chassis, rack mount, sealed-case PC
_DESKTOP_CHASSIS = {"3", "4", "5", "6", "7", "15", "16", "17", "23", "24"}


def _form_factor(chassis: str) -> str:
    if chassis in _LAPTOP_CHASSIS:
        return "laptop"
    if chassis in _DESKTOP_CHASSIS:
        return "desktop"
    return "other"


def probe() -> dict:
    chassis = read(f"{DMI}/chassis_type") or ""
    return {
        "vendor": read(f"{DMI}/sys_vendor"),
        "product": read(f"{DMI}/product_name"),
        "family": read(f"{DMI}/product_family"),
        "sku": read(f"{DMI}/product_sku"),
        "form_factor": _form_factor(chassis),
    }
