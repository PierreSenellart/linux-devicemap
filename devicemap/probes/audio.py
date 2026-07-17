"""Built-in audio endpoints (speakers, internal microphones) from
/proc/asound, which is world-readable."""

from __future__ import annotations

import glob
import os
import re


def _pcm_info(path: str) -> dict:
    info = {}
    try:
        with open(f"{path}/info") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = v.strip()
    except OSError:
        pass
    return info


# SoundWire codec driver → endpoint role (Realtek parts cover most
# SoundWire laptops; HDA machines carry codec names in the PCM id instead)
_SDW_ROLES = {
    "rt711": "headset",
    "rt712": "headset",
    "rt713": "headset",
    "rt722": "headset",
    "rt1308": "speaker",
    "rt1316": "speaker",
    "rt1318": "speaker",
    "rt714": "microphone",
    "rt715": "microphone",
}


def _soundwire_codecs() -> dict[str, list[str]]:
    """role → codec chip names, e.g. {'speaker': ['Realtek RT1308']}."""
    roles: dict[str, list[str]] = {}
    for path in sorted(glob.glob("/sys/bus/soundwire/devices/sdw:*")):
        try:
            driver = os.path.basename(os.readlink(f"{path}/driver"))
        except OSError:
            continue
        role = _SDW_ROLES.get(driver)
        if role:
            chip = f"Realtek {driver.upper()}"
            if chip not in roles.setdefault(role, []):
                roles[role].append(chip)
    return roles


def probe() -> list[dict]:
    endpoints = []
    codecs = _soundwire_codecs()
    for card_path in sorted(glob.glob("/proc/asound/card[0-9]*")):
        card = os.path.basename(card_path)
        # USB sound cards are already represented under their USB device
        if "/usb" in os.path.realpath(f"/sys/class/sound/{card}"):
            continue
        for pcm in sorted(glob.glob(f"{card_path}/pcm*")):
            info = _pcm_info(pcm)
            pcm_id = re.sub(r"\s*\(\*\)$", "", info.get("id", ""))
            stream = info.get("stream", "")
            # jack streams belong to the audio-jack port, HDMI/DP audio to
            # the display connector
            if re.search(r"jack|hdmi|dp|deepbuffer", pcm_id, re.I):
                continue
            if stream == "PLAYBACK" and re.search(r"speaker", pcm_id, re.I):
                name = ", ".join(codecs.get("speaker", [])) or pcm_id
                endpoints.append({"kind": "speaker", "name": name})
            elif stream == "CAPTURE":
                name = ", ".join(codecs.get("microphone", [])) or pcm_id
                endpoints.append({"kind": "microphone", "name": name})
    return endpoints
