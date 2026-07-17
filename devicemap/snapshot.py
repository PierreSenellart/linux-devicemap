"""Assemble the normalized machine snapshot from all probes."""

from __future__ import annotations

import time

from .probes import dmi, drm, inputs, media, power, typec, usb


def build() -> dict:
    usb_info = usb.probe()
    typec_info = typec.probe()
    drm_info = drm.probe()
    power_info = power.probe()
    input_info = inputs.probe()

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

    builtins = list(input_info["builtins"]) + media.cameras() + media.bluetooth()
    for hw in usb_info["hardwired"]:
        builtins.append(
            {
                "kind": "usb-internal",
                "name": (hw["device"].get("product") or "internal USB device"),
                "classes": hw["device"]["classes"],
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
