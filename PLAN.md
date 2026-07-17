# linux-devicemap – implementation plan

("devicemap" as UI shorthand; the package and repository are named
`linux-devicemap`.)

Real-time graphical view of a computer's ports and devices, drawn at their
physical locations on the chassis — laptops (side edges) and desktops (rear
I/O, front and top panels).

## Architecture (decided)

Web UI + local daemon:

- **Daemon** (Python, stdlib + FastAPI/uvicorn): probes sysfs/procfs,
  subscribes to udev events (`udevadm monitor` subprocess; no libudev
  binding needed), normalizes everything into a JSON snapshot, serves it
  over HTTP + WebSocket along with the static frontend.
- **Frontend** (vanilla JS + SVG, no build step): renders the machine and
  its ports, applies live snapshots pushed over the WebSocket.
- **Layouts** (later milestones): per-model JSON documents keyed by DMI
  identity (vendor/product/SKU), giving each physical port a side and
  coordinates, plus bindings to kernel identities. Obtained from an online
  registry / manufacturer-spec bootstrap, made trustworthy by a local
  calibration wizard.

## Ground truth from the reference machine (Dell Latitude 9510)

What probing established, and the design consequences:

| Fact | Consequence |
|---|---|
| USB port nodes expose `connect_type` (`hotplug`/`hardwired`/`not used`) | user-facing ports vs. built-ins (webcam, BT) classified automatically |
| `peer` symlinks pair the USB2/USB3 sides of one connector; `connector` symlinks tie them to `/sys/class/typec/portN` | one *logical port* per physical connector |
| ACPI `_PLD` (`physical_location/`) is present but firmware fills it with identical junk | positions must come from layouts + calibration; `_PLD` is a hint only |
| Chargers are power-only Type-C partners, invisible to `lsusb` | typec class, not USB devices, is the source of truth for USB-C |
| `power_role`, `power_operation_mode`, `usb_power_delivery` PDOs, `ucsi-source-psy-*` are all readable | per-port power direction + contract can be rendered live |
| Battery-side numbers (`BAT0`) are reliable; UCSI voltage readings are not | battery gauge is the headline power number |
| `udevadm monitor --udev` works unprivileged | no elevated privileges needed for hotplug events |
| jack state needs `/dev/input` access (evdev `EVIOCGSW`) | feature-detect; degrade to "state unknown" without permissions |

## Milestones

### M1 – live daemon + abstract view (this repository, now)
- Probes: DMI identity; USB port topology (root-hub ports, peering,
  connect_type, device trees incl. hubs); typec ports (roles, mode,
  partner); DRM connectors; power supplies (AC, battery, UCSI); input
  built-ins (keyboard, touchpad, jack switch device); cameras; bluetooth.
- Event loop: `udevadm monitor` → debounce → re-probe → broadcast full
  snapshot + event-log entries over WebSocket; slow poll (10 s) for
  battery drift.
- Frontend: schematic chassis (screen, camera, keyboard, touchpad,
  battery) + an *uncalibrated* port strip grouped by connector kind;
  occupancy, device labels, power direction arrows, PD/current mode,
  event log. No physical positions yet.
- Feature detection surfaced in the UI (e.g. jack state unavailable).
- Added along the way: hub halves merged (USB2+USB3 faces of one hub) with
  full device trees in the UI; network interfaces (ethernet + wifi) joined
  to their USB parent or listed as built-ins, wifi SSID/signal via `iw`,
  live link changes via an rtnetlink socket (carrier changes emit no udev
  events); live jack watcher on evdev; inline SVG icons from Lucide (ISC),
  see `frontend/icons.js`.

### M2 – layouts + calibration wizard (implemented; positions editable only in JSON so far)
- Layout JSON schema: image/outline + per-port `{id, type, side, pos,
  binding}`; hand-authored layout for Latitude 9510 as the first entry.
  (`pos` was a scalar along the side edge; it became `{x, y}` in M4.5, with
  the scalar still accepted.)
- Wizard: "plug something into the leftmost left-side port" → bind the
  kernel port that fires; AC plug/unplug binds barrel jacks on machines
  that have them; promote/demote built-ins (SD readers are `hardwired`
  but user-facing).
- Persist machine profile; render ports at their true positions
  (top-down chassis with unfolded edge strips, Dell-diagram style).
- Status: done — layout engine (`devicemap/layout.py`, layouts keyed by
  DMI slug, profile overrides in `profiles/`), draft 9510 layout with
  auto-bound HDMI/USB-A/jack/microSD (an RTS525A `mmc0` slot, live via
  udev `mmc` events), calibration API (`POST /api/calibrate/<slot>`),
  wizard + positioned side strips in the UI. Remaining: drag-to-adjust
  positions, verifying the draft side assignments against the physical
  machine (wizard binds ports; positions are still hand-set), barrel-jack
  calibration on machines that have one.

### M2.5 – power polish (done)
- Flow arrows in/out per port, net battery wattage, contract badges,
  "slow charger" warning by comparing against the machine's own sink
  PDOs (`pd0`/`pd1`).
- Status: done — per-port `watts_in` estimate (PD source PDOs, or the
  Type-C current mode at 5 V) and `watts_max_in` (own sink PDOs, 90 W on
  the 9510); animated flow triangles on the chassis; friendly contract
  labels; "slow charger" badge below 50% of max input.

### M3 – Bluetooth (done)
- Source: BlueZ over the system D-Bus, via `busctl -j call org.bluez /
  org.freedesktop.DBus.ObjectManager GetManagedObjects` (verified to work
  unprivileged; JSON output, no new dependencies). Gives adapters
  (`Adapter1`: name, powered) and devices (`Device1`: name, icon, class,
  paired, connected, address; `Battery1`: percentage).
- Real-time: udev `bluetooth` subsystem events fire on connect/disconnect
  (already subscribed); subscribe to `PropertiesChanged` D-Bus signals for
  battery/connection changes that produce no udev event.
- UI: the radio stays a built-in on the chassis; connected devices render
  as a *wireless halo* of satellite badges around the laptop (they have no
  physical port), icon from BlueZ `Icon`, battery percentage when exposed;
  paired-but-disconnected devices collapsed/dimmed.
- Degradation: without bluetoothd, show sysfs adapter presence only.
- Out of scope: pairing/connecting management (view-only tool).
- Status: done — `probes/bt.py` (busctl GetManagedObjects), wireless list
  (connected first, paired dimmed, battery % when exposed), halo badges
  under the chassis hover-linked to the list, adapter builtin enriched
  with alias + connected count. Connection changes arrive via udev
  `bluetooth` events; battery/property drift via the 10 s poll (a
  PropertiesChanged D-Bus subscription would make those instant — noted
  as optional polish).

### M4 – layout contributions (no LLM, no service: `layouts/` IS the registry) — core done
- `layouts/` in this repo is the registry, hwdb-style: inert JSON keyed
  by DMI slug, contributed via ordinary PRs, reviewed and versioned with
  the schema, shipped with the software → lookup is a local file read.
- Contribution flow in the app: after calibration + human position
  fixes, export the layout (calibrated bindings promoted in, local-only
  data stripped) ready for a PR.
- In-app editor for sides/order/positions (today JSON-only), so a
  contributor never touches a file by hand; kernel-derived skeleton
  (slot list, types, auto-bindings are already fully local) + wizard
  cover the rest.
- Optional freshness helper: "refresh layouts" fetches raw JSON from
  the repo's main branch into a local cache, for new models between
  releases. Off by default; still static files, no service.
- Layout *authoring* from manufacturer docs is a maintainer workflow
  outside the runtime (any tools welcome there). No LLM or extraction
  logic embedded in the software.
- Status: core done — kernel-derived skeleton for machines without a
  registry entry (status "skeleton", auto-bindings included), drag
  position/side editor in the UI ("edit layout", overrides persisted in
  the profile), export endpoint (`GET /api/layout/export`) producing a
  clean registry entry with local edits promoted. Remaining: the
  optional between-releases "refresh layouts" fetch; in-app editing of
  the `hidden` list and slot labels (today JSON-side); a "reset to
  registry layout" action (drop the profile's `slots` overrides) and a
  visible hint when local position edits shadow the shipped layout.

### M4.5 – desktops (done)
Everything above assumed a laptop: a lid/keyboard/touchpad schematic, ports
on two side *edges*, and a single scalar position along each edge. A tower
has none of that — its ports sit on a **rear I/O panel** (a 2D field: board
I/O block above, PCIe card brackets below), a **front** panel and sometimes
a **top**. So:

- **Positions are 2D**: `pos` is `{x, y}` normalized within a face. A bare
  scalar (every layout written before this) is read as `{x: 0, y: scalar}`,
  so the 9510 entry and existing profiles keep working untouched; writers
  emit 2D.
- **Faces have a kind**: `edge` (laptop left/right — narrow, only `y`
  matters, drawn and dragged exactly as before) and `panel` (desktop
  rear/front/top — 2D, both axes). `layouts/` stays pure slot lists; the
  drawn geometry lives in the frontend's `FACES` table, keyed by form
  factor.
- **`form_factor`** now distinguishes `desktop` (SMBIOS chassis 3–7, 15–17,
  23, 24) from `laptop`/`other`, and selects the schematic, the skeleton's
  faces, and the power chip's no-battery wording.

Ground truth from the reference desktop (Dell Precision 3660), and what it
forced:

| Fact | Consequence |
|---|---|
| No `Mains` power supply exists at all — `ac_online` stays `None`, not `False` | a battery-less desktop reads as "AC power"; only an explicit `False` is real doubt |
| No USB port node carries a `connector` symlink, unlike the 9510 | the 3 Type-C ports were invisible: `snapshot` now emits typec ports no USB connector claimed (`device_unlinked`), power state without a device tree |
| A Type-C partner with no linkable device is *not* necessarily a charger (port0 is `source`, feeding 3 A out) | "power adapter" is claimed only when power actually flows in; otherwise "partner attached" |
| 6 i915 + 3 nvidia DRM connectors, only some physical | the GPU split is kernel-readable (card1 i915 = board, card2 = PCIe bracket); which connectors are phantom is not — left to calibration |

### M5 – polish
- Docks/hubs as satellite boxes with their subtree; camera/mic in-use
  indicators; EDID monitor names on outputs; vendor plugins (e.g. Dell
  adapter wattage); Tauri wrapper if a desktop app shell is wanted.

## Audio-jack access

Jack state is evdev switch state (`EVIOCGSW`) plus live evdev events on
the jack's `/dev/input/eventN`; a live watcher is implemented and
feature-detected at daemon startup. `/dev/input` is `root:input 0660`,
so by default *no* ordinary user (not just the sandbox) can read it;
options, best first:

1. udev rule granting just the jack switch device to a group, e.g.
   `/etc/udev/rules.d/99-devicemap.rules`:
   `SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="*Headset Jack*",
   MODE="0660", GROUP="devshare"`
   then reload (`udevadm control --reload && udevadm trigger
   --subsystem-match=input --action=change`). Minimal exposure: the rule
   matches only jack switch devices, not keyboards.
2. ALSA fallback (planned, M2): when the daemon runs in a desktop
   session, logind's uaccess ACL already grants `/dev/snd/control*`;
   jack state is then readable as ALSA jack kcontrols and `alsactl
   monitor` provides events. Lets a session-run daemon work with zero
   configuration.
3. Adding the daemon user to the `input` group works but grants read
   access to all input devices including keyboards (keylogging surface);
   not recommended.

## Repository layout

```
devicemap/            Python package (daemon)
  __main__.py         python -m devicemap [--port N]
  sysfs.py            small sysfs read helpers
  probes/             one module per subsystem → plain dicts
  snapshot.py         assembles the full normalized snapshot
  monitor.py          udevadm-based event stream, jack watcher
  server.py           FastAPI app, WebSocket broadcast, static files
frontend/             index.html + app.js + style.css (no build step)
layouts/              per-model layout JSONs (M2)
PLAN.md, README.md, requirements.txt
```

## Non-goals for now
- Windows/macOS backends (the probe layer is deliberately isolated so
  they can be added behind the same snapshot schema).
- Root privileges: everything runs as an ordinary user; features needing
  device-node access are feature-detected.
