# linux-devicemap

Real-time graphical view of a Linux computer's ports and devices
("devicemap" for short): USB-A/USB-C with power delivery, HDMI/DP, audio
jack, SD slots, built-in components (camera, keyboard, speakers…),
network interfaces, drives and Bluetooth peers — drawn at their physical
locations on the chassis, updated live on hotplug.

Laptops are drawn as a top-down schematic with their two side edges
unfolded; desktops as a tower with its rear I/O, front and top panels laid
out as 2D fields, since a tower's ports sit in a grid rather than along a
line.

Per-model chassis layouts live in `layouts/` (this directory is the
community registry, hwdb-style); binding a layout to your machine takes a
two-minute in-app calibration wizard.

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m devicemap          # http://127.0.0.1:8808/
```

Runs unprivileged; everything is probed from sysfs/procfs, udev events,
and BlueZ over D-Bus.

### Optional device access

- **Audio-jack state** needs read access to the jack's input device. The
  narrowest grant is a udev rule (matches only jack switch devices, not
  keyboards), e.g.:

  ```
  # /etc/udev/rules.d/99-devicemap.rules
  SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="*Headset Jack*", MODE="0660", GROUP="<your group>"
  ```

  then `udevadm control --reload && udevadm trigger
  --subsystem-match=input --action=change`.
- **RGB vs. IR camera labeling** needs read access to `/dev/video*`
  (typically the `video` group).

## License

MIT — see `LICENSE`.
