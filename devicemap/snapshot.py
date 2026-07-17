"""Assemble the normalized machine snapshot from all probes."""

from __future__ import annotations

import time

from .probes import audio, dmi, drm, inputs, media, net, power, typec, usb


def _attach_net(device: dict | None, by_parent: dict) -> None:
    """Recursively attach network-interface info to USB device nodes."""
    if not device:
        return
    ifaces = by_parent.get(device["sysname"])
    if not ifaces:
        # merged hub halves keep their original sysnames in 'halves'
        ifaces = [
            i for h in device.get("halves", []) for i in by_parent.get(h, [])
        ]
    if ifaces:
        device["net"] = ifaces
    for child in device.get("children", []):
        _attach_net(child, by_parent)


def build() -> dict:
    usb_info = usb.probe()
    typec_info = typec.probe()
    drm_info = drm.probe()
    power_info = power.probe()
    input_info = inputs.probe()
    net_info = net.probe()

    net_by_parent: dict[str, list] = {}
    for iface in net_info:
        if iface["usb_parent"]:
            net_by_parent.setdefault(iface["usb_parent"], []).append(iface)

    ports = []

    # USB connectors, with power facet merged in from typec + ucsi
    for conn in usb_info["connectors"]:
        port = dict(conn)
        tc = typec_info.get(conn["typec"]) if conn["typec"] else None
        if tc:
            charging_in = power_info["ucsi"].get(conn["typec"], False)
            port["power"] = {
                "role": tc["power_role"],
                "mode": tc["mode"],
                "partner_present": tc["partner"] is not None,
                "charging_in": charging_in,
                "source_pdos": (tc["partner"] or {}).get("source_pdos"),
                "sink_pdos": tc["sink_pdos"],
            }
            # a power-only partner (charger) occupies the port even though
            # no USB device enumerates
            port["connected"] = port["device"] is not None or tc["partner"] is not None
        else:
            port["power"] = None
            port["connected"] = port["device"] is not None
        _attach_net(port["device"], net_by_parent)
        ports.append(port)

    # display connectors
    for d in drm_info["external"]:
        ports.append(
            {
                "id": d["id"],
                "kind": d["kind"],
                "connected": d["status"] == "connected",
                "device": None,
                "power": None,
                "status": d["status"],
            }
        )

    # audio jacks
    for j in input_info["jacks"]:
        connected = j["headphone"] or j["microphone"] if j["readable"] else None
        ports.append(
            {
                "id": j["id"],
                "kind": "audio-jack",
                "connected": connected,
                "device": None,
                "power": None,
                "jack": j,
            }
        )

    cams, bts = media.cameras(), media.bluetooth()
    builtins = list(input_info["builtins"]) + cams + bts + audio.probe()
    for iface in net_info:
        if not iface["usb_parent"]:
            builtins.append({"kind": iface["kind"], "name": iface["ifname"], **iface})
    # internal USB devices already represented by a class device (camera,
    # bluetooth) are not listed a second time
    claimed = {b["usb_parent"] for b in cams + bts if b.get("usb_parent")}
    for hw in usb_info["hardwired"]:
        dev = hw["device"]
        if dev["sysname"] in claimed:
            continue
        builtins.append(
            {
                "kind": "usb-internal",
                "name": dev.get("product") or f"USB {dev['vid']}:{dev['pid']}",
                "classes": dev["classes"],
                "port": hw["port"],
            }
        )
    for d in drm_info["internal"]:
        builtins.append({"kind": "display", "name": d["id"], "status": d["status"]})

    return {
        "ts": time.time(),
        "machine": dmi.probe(),
        "ports": ports,
        "builtins": builtins,
        "power": {
            "ac_online": power_info["ac_online"],
            "batteries": power_info["batteries"],
        },
        "capabilities": {
            "jack_state": any(j["readable"] for j in input_info["jacks"]) or None,
        },
    }
