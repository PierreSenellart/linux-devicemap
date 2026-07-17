"""USB topology: physical ports (with USB2/USB3 peering and Type-C
connector links) and the device trees attached to them."""

from __future__ import annotations

import glob
import os
import re

from ..sysfs import link_base, listdir, read

USB_DEVICES = "/sys/bus/usb/devices"

# bInterfaceClass → human-readable label
CLASS_NAMES = {
    0x01: "audio",
    0x02: "communications",
    0x03: "HID",
    0x05: "physical",
    0x06: "imaging",
    0x07: "printer",
    0x08: "mass storage",
    0x09: "hub",
    0x0A: "CDC data",
    0x0B: "smart card",
    0x0D: "content security",
    0x0E: "video",
    0x0F: "personal healthcare",
    0x10: "audio/video",
    0xDC: "diagnostic",
    0xE0: "wireless",
    0xEF: "miscellaneous",
    0xFE: "application specific",
    0xFF: "vendor specific",
}


def _hex(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(v, 16)
    except ValueError:
        return None


def device_info(dev: str) -> dict | None:
    """Describe the USB device at /sys/bus/usb/devices/<dev>, recursively
    including children for hubs."""
    base = f"{USB_DEVICES}/{dev}"
    if not os.path.isdir(base) or read(f"{base}/idVendor") is None:
        return None
    interfaces = []
    classes: set[str] = set()
    for entry in listdir(base):
        if not re.fullmatch(rf"{re.escape(dev)}:\d+\.\d+", entry):
            continue
        cls = _hex(read(f"{base}/{entry}/bInterfaceClass"))
        cls_name = CLASS_NAMES.get(cls, f"class 0x{cls:02x}" if cls is not None else "?")
        classes.add(cls_name)
        interfaces.append(
            {"id": entry, "class": cls_name, "driver": link_base(f"{base}/{entry}/driver")}
        )
    children = []
    for entry in listdir(base):
        if re.fullmatch(rf"{re.escape(dev)}\.\d+", entry):
            child = device_info(entry)
            if child:
                children.append(child)
    return {
        "sysname": dev,
        "vid": read(f"{base}/idVendor"),
        "pid": read(f"{base}/idProduct"),
        "manufacturer": read(f"{base}/manufacturer"),
        "product": read(f"{base}/product"),
        "serial": read(f"{base}/serial"),
        "speed_mbps": read(f"{base}/speed"),
        "classes": sorted(classes),
        "interfaces": interfaces,
        "children": children,
    }


def _root_hub_ports() -> list[dict]:
    """All port nodes of root hubs, with their attributes and links."""
    ports = []
    for node in glob.glob(f"{USB_DEVICES}/usb*/*/usb*-port*"):
        name = os.path.basename(node)  # e.g. usb1-port6
        m = re.fullmatch(r"usb(\d+)-port(\d+)", name)
        if not m:
            continue
        busnum, portnum = int(m.group(1)), int(m.group(2))
        ports.append(
            {
                "name": name,
                "busnum": busnum,
                "portnum": portnum,
                "connect_type": read(f"{node}/connect_type"),
                "peer": link_base(f"{node}/peer"),
                "connector": link_base(f"{node}/connector"),  # typec portN
                "device": f"{busnum}-{portnum}",  # sysname if something is attached
                "location": _physical_location(f"{USB_DEVICES}/{busnum}-{portnum}"),
            }
        )
    return sorted(ports, key=lambda p: (p["busnum"], p["portnum"]))


def _physical_location(devpath: str) -> dict | None:
    """ACPI _PLD data for an attached device, if any (hint only)."""
    base = f"{devpath}/physical_location"
    if not os.path.isdir(base):
        return None
    return {
        "panel": read(f"{base}/panel"),
        "horizontal": read(f"{base}/horizontal_position"),
        "vertical": read(f"{base}/vertical_position"),
        "lid": read(f"{base}/lid"),
        "dock": read(f"{base}/dock"),
    }


def probe() -> dict:
    """Return {'connectors': [...], 'hardwired': [...]}.

    A *connector* is one physical user-facing plug: the union of peered
    USB2/USB3 root-hub ports, plus the typec port they link to (if any).
    *hardwired* entries are internal USB devices (webcam, bluetooth, ...).
    """
    hardwired = []
    groups: dict[str, list[dict]] = {}  # group key → member port nodes

    for p in _root_hub_ports():
        has_device = os.path.isdir(f"{USB_DEVICES}/{p['device']}")
        # A typec connector link always marks a user-facing port. Otherwise
        # trust connect_type, except that "not used" with a device attached
        # means an internal device behind lying firmware (seen in the wild:
        # bluetooth on a "not used" port).
        if not p["connector"]:
            if p["connect_type"] == "hardwired" or (
                p["connect_type"] == "not used" and has_device
            ):
                dev = device_info(p["device"])
                if dev:
                    hardwired.append({"port": p["name"], "device": dev})
                continue
            if p["connect_type"] == "not used":
                continue
        # group by typec connector when present, else by peer pair
        if p["connector"]:
            key = f"typec:{p['connector']}"
        else:
            pair = sorted([p["name"], p["peer"]]) if p["peer"] else [p["name"]]
            key = "peer:" + "+".join(pair)
        groups.setdefault(key, []).append(p)

    connectors = []
    for key, members in groups.items():
        members.sort(key=lambda p: (p["busnum"], p["portnum"]))
        devices = [d for d in (device_info(p["device"]) for p in members) if d]
        typec = key.split(":", 1)[1] if key.startswith("typec:") else None
        connectors.append(
            {
                "id": typec or members[0]["name"],
                "kind": "usb-c" if typec else "usb-a",
                "usb_ports": [p["name"] for p in members],
                "typec": typec,
                "device": devices[0] if devices else None,
                "location_hint": next(
                    (p["location"] for p in members if p["location"]), None
                ),
            }
        )
    connectors.sort(key=lambda c: c["id"])
    return {"connectors": connectors, "hardwired": hardwired}
