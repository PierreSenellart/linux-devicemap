"""Machine identity from DMI."""

from __future__ import annotations

from ..sysfs import read

DMI = "/sys/class/dmi/id"

# SMBIOS chassis types that mean "portable computer with a lid"
_LAPTOP_CHASSIS = {"8", "9", "10", "14", "31", "32"}


def probe() -> dict:
    chassis = read(f"{DMI}/chassis_type") or ""
    return {
        "vendor": read(f"{DMI}/sys_vendor"),
        "product": read(f"{DMI}/product_name"),
        "family": read(f"{DMI}/product_family"),
        "sku": read(f"{DMI}/product_sku"),
        "form_factor": "laptop" if chassis in _LAPTOP_CHASSIS else "other",
    }
