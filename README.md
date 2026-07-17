# devicemap

Real-time graphical view of a computer's ports and devices (USB-A/USB-C,
HDMI/DP, audio jack, built-ins, power), eventually drawn at their physical
locations on the chassis. Linux only for now. See `PLAN.md` for the roadmap.

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m devicemap          # http://127.0.0.1:8808/
```

Runs unprivileged. Audio-jack state additionally needs read access to
`/dev/input` (the `input` group); it degrades to "state unavailable"
otherwise.
