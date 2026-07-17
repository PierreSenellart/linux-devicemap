"use strict";

const $ = (id) => document.getElementById(id);

const KIND_LABEL = {
  "usb-a": "USB-A",
  "usb-c": "USB-C",
  hdmi: "HDMI",
  dp: "DP",
  vga: "VGA",
  dvi: "DVI",
  "audio-jack": "JACK",
  sd: "SD",
};

const SLOT_ICON = {
  "usb-a": "usb",
  "usb-c": "usb",
  hdmi: "monitor",
  dp: "monitor",
  "audio-jack": "headphones",
  sd: "memory-stick",
  sim: "smartphone",
  lock: "lock",
  smartcard: "credit-card",
  barrel: "zap",
};
const PASSIVE_SLOTS = new Set(["sim", "lock", "smartcard"]);

// Drawn geometry of each chassis face, per form factor. `edge` faces are
// the narrow strips down a laptop's sides: only pos.y is meaningful.
// `panel` faces are the 2D port fields of a desktop (the rear I/O panel
// is a grid: board I/O block on top, PCIe card brackets below), where
// pos.x and pos.y both place the slot. `inward` points from the face
// toward the machine's body, for power-flow arrows.
const FACES = {
  laptop: {
    left: { kind: "edge", x: 18, y: 38, h: 296, label: "left side", inward: 1 },
    right: { kind: "edge", x: 588, y: 38, h: 296, label: "right side", inward: -1 },
  },
  desktop: {
    rear: { kind: "panel", x: 32, y: 44, w: 576, h: 210, label: "rear I/O", inward: 1 },
    front: { kind: "panel", x: 32, y: 290, w: 576, h: 58, label: "front", inward: 1 },
    top: { kind: "panel", x: 32, y: 376, w: 576, h: 40, label: "top", inward: 1 },
  },
};

// height of the drawn machine: a tower's stacked panels need more than a
// laptop's. Satellites and the wireless halo hang off the bottom of it.
const CONTENT_H = { laptop: 380, desktop: 470 };
// the wireless halo's lane, kept clear of the body/panels above it
const HALO_Y = { laptop: 356, desktop: 436 };

const SLOT_W = 26;
const SLOT_H = 22;
const LABEL_H = 13; // room kept under a panel marker for its device label

function formOf(snap) {
  const f = (snap.machine || {}).form_factor;
  return FACES[f] ? f : "laptop"; // unknown/other: the laptop schematic
}

function faceGeom(form, name) {
  return FACES[form][name];
}

// how far a marker's top-left may travel down a face. Panels keep a
// label's worth of room at the bottom so the text stays inside the face.
function faceSpanY(face) {
  return face.kind === "edge" ? face.h : face.h - SLOT_H - LABEL_H;
}

// top-left corner of a slot marker placed at `pos` on `face`
function slotXY(face, pos) {
  const p = pos || { x: 0, y: 0 };
  return face.kind === "edge"
    ? { x: face.x + 4, y: face.y + p.y * face.h }
    : {
        x: face.x + p.x * (face.w - SLOT_W),
        y: face.y + p.y * faceSpanY(face),
      };
}

const BUILTIN_LABEL = {
  keyboard: "Keyboard",
  touchpad: "Touchpad",
  camera: "Camera",
  bluetooth: "Bluetooth",
  display: "Built-in display",
  "usb-internal": "Internal USB",
  wifi: "WiFi",
  ethernet: "Ethernet",
  speaker: "Speakers",
  microphone: "Microphone",
  disk: "Drive",
};

const PORT_ICON = {
  "usb-a": "usb",
  "usb-c": "usb",
  hdmi: "monitor",
  dp: "monitor",
  vga: "monitor",
  dvi: "monitor",
  "audio-jack": "headphones",
  sd: "memory-stick",
};

const BUILTIN_ICON = {
  keyboard: "keyboard",
  touchpad: "touchpad",
  camera: "webcam",
  bluetooth: "bluetooth",
  display: "monitor",
  wifi: "wifi",
  ethernet: "ethernet-port",
  speaker: "speaker",
  microphone: "mic",
  disk: "hard-drive",
};

function mountsLabel(mounts, max = 3) {
  if (!mounts || !mounts.length) return "";
  const pts = mounts.map((m) => m.mountpoint);
  const shown = pts.slice(0, max).join(" ");
  return pts.length > max ? `${shown} +${pts.length - max}` : shown;
}

function icon(name) {
  return (typeof ICONS !== "undefined" && ICONS[name]) || "";
}

function deviceIcon(dev) {
  const cls = dev.classes || [];
  const prod = (dev.product || "").toLowerCase();
  if (cls.includes("hub")) return "network";
  if (dev.net && dev.net.length)
    return dev.net[0].kind === "wifi" ? "wifi" : "ethernet-port";
  if (cls.includes("communications") || cls.includes("CDC data"))
    return "ethernet-port";
  if (cls.includes("mass storage"))
    return /card/.test(prod) ? "memory-stick" : "hard-drive";
  if (cls.includes("video")) return "webcam";
  if (cls.includes("imaging"))
    return /android|phone|galaxy|pixel/.test(prod) ? "smartphone" : "camera";
  if (cls.includes("audio") || cls.includes("audio/video")) return "speaker";
  if (cls.includes("wireless")) return "bluetooth";
  if (cls.includes("HID"))
    return /mouse|receiver|touchpad/.test(prod) ? "mouse" : "keyboard";
  return "plug";
}

function storageHtml(dev) {
  if (!dev.storage || !dev.storage.length) return "";
  return dev.storage
    .map((s) => {
      let state = s.media
        ? `${s.size_gb} GB`
        : s.removable
          ? "empty (no media)"
          : "no media";
      const mts = mountsLabel(s.mounts);
      if (mts) state += ` · ${mts}`;
      return `<div class="sub net">${icon("hard-drive")} ${esc(s.dev)} · ${esc(state)}</div>`;
    })
    .join("");
}

function inputsHtml(dev) {
  if (!dev.hid_inputs || !dev.hid_inputs.length) return "";
  return dev.hid_inputs
    .map((n) => {
      const ic = /mouse|trackball|pointer/i.test(n)
        ? "mouse"
        : /keyboard|keypad/i.test(n)
          ? "keyboard"
          : "plug";
      return `<div class="sub net">${icon(ic)} ${esc(n)}</div>`;
    })
    .join("");
}

function netHtml(dev) {
  if (!dev.net || !dev.net.length) return "";
  return dev.net
    .map((n) => {
      let s;
      if (n.kind === "wifi") {
        const w = n.wifi || {};
        s = w.connected
          ? `${w.ssid} · ${w.signal_dbm} dBm · ${w.tx_bitrate || ""}`
          : "not associated";
      } else {
        s = n.carrier
          ? `link up${n.speed_mbps ? ` · ${n.speed_mbps} Mb/s` : ""}`
          : "no link";
      }
      return `<div class="sub net">${icon(n.kind === "wifi" ? "wifi" : "ethernet-port")} ${esc(n.ifname)} · ${esc(s)}</div>`;
    })
    .join("");
}

let prevConnected = {}; // port id → bool, to pulse on change
let editMode = false;
let drag = null; // {slotId, g, baseX, baseY} while dragging
let pendingSnap = null; // snapshot deferred during a drag
let lastSnap = null;

let batteryActive = false; // charging, or discharging while on AC

function render(snap) {
  lastSnap = snap;
  const bat = ((snap.power || {}).batteries || [])[0];
  batteryActive =
    !!bat &&
    (bat.status === "Charging" ||
      (bat.status === "Discharging" && (snap.power || {}).ac_online));
  const m = snap.machine || {};
  const cpu = m.cpu
    ? m.cpu + (m.cores ? ` (${m.cores}c/${m.threads}t)` : "")
    : null;
  const mem = m.memory_installed_gb ? `${m.memory_installed_gb} GB RAM` : null;
  const vendor = (m.vendor || "").replace(
    /[\s,]+(Inc\.?|Corp\.?|Corporation|Ltd\.?|Co\.|GmbH|S\.A\.)$/i,
    ""
  );
  $("machine").textContent = [
    [vendor, m.product].filter(Boolean).join(" "),
    cpu,
    mem,
    ...(m.gpus || []),
  ]
    .filter(Boolean)
    .join(" · ");
  renderPower(snap.power || {}, formOf(snap));
  const lay = snap.layout || {};
  $("ports-note").textContent = !lay.available
    ? "no layout for this machine — positions unknown"
    : lay.status === "skeleton"
      ? "no registry layout — skeleton derived from the kernel; drag ports into place (edit layout)"
      : lay.unbound && lay.unbound.length
        ? `${lay.unbound.length} port(s) not calibrated`
        : lay.status === "draft"
          ? "layout: draft"
          : "";
  if (lay.available && lay.edited)
    $("ports-note").textContent += (
      $("ports-note").textContent ? " · " : ""
    ) + "locally edited positions";
  renderPorts(snap.ports || [], lay, formOf(snap));
  renderBuiltins(snap.builtins || []);
  renderWireless(snap.bluetooth);
  renderChassis(snap);
  renderWizard(snap);
  renderTools(snap);
}

function renderTools(snap) {
  const t = $("tools");
  const lay = snap.layout || {};
  if (!lay.available) {
    t.replaceChildren();
    return;
  }
  t.innerHTML =
    `<button id="editbtn">${editMode ? "done editing" : "edit layout"}</button>` +
    (editMode
      ? ` <a id="exportlink" class="chip" href="/api/layout/export" download>export layout</a>` +
        ` <button id="refreshbtn">refresh from registry</button>` +
        (lay.edited
          ? ` <button id="resetbtn">reset positions</button>`
          : "")
      : "");
  $("editbtn").onclick = () => {
    editMode = !editMode;
    if (lastSnap) render(lastSnap);
  };
  const refreshBtn = $("refreshbtn");
  if (refreshBtn)
    refreshBtn.onclick = async () => {
      const r = await fetch("/api/layouts/refresh", { method: "POST" });
      const j = await r.json();
      if (!j.updated)
        alert("No layout found in the online registry for this machine.");
    };
  const resetBtn = $("resetbtn");
  if (resetBtn)
    resetBtn.onclick = async () => {
      const base =
        lay.status === "skeleton" ? "the kernel-derived skeleton" : "the registry layout";
      if (confirm(`Discard local position edits and restore ${base}?`))
        await fetch("/api/layout/reset", { method: "POST" });
    };
}

function slotOfPort(lay, portId) {
  for (const [side, slots] of Object.entries(lay.sides || {})) {
    const slot = slots.find((s) => s.port_id === portId);
    if (slot) return { side, slot };
  }
  return null;
}

function renderPower(power, form) {
  const bat = (power.batteries || [])[0];
  const chip = $("powerchip");
  if (!bat) {
    // a machine with no battery on mains is the desktop norm, and many
    // towers expose no "Mains" power supply at all — leaving ac_online
    // unknown rather than false. Only an explicit false is a real doubt.
    const ac = power.ac_online || (form === "desktop" && power.ac_online == null);
    chip.textContent = ac ? "AC power" : "power: ?";
    chip.className = "chip" + (ac ? " ok" : "");
    return;
  }
  const flow =
    bat.status === "Charging" ? "▲" : bat.status === "Discharging" ? "▼" : "";
  const watts = bat.watts != null ? ` ${bat.watts} W` : "";
  chip.textContent = `battery ${bat.capacity_pct}% ${flow}${watts}` +
    (power.ac_online ? " · AC" : "");
  chip.className = "chip " + (power.ac_online ? "ok" : "");
}

function describeDevice(dev) {
  if (!dev) return null;
  const name =
    [dev.manufacturer, dev.product].filter(Boolean).join(" ") ||
    `${dev.vid}:${dev.pid}`;
  const bits = [];
  if (dev.classes && dev.classes.length) bits.push(dev.classes.join(", "));
  if (dev.speed_mbps) bits.push(`${dev.speed_mbps} Mb/s`);
  return { name, sub: bits.join(" · ") };
}

function treeHtml(children) {
  if (!children || !children.length) return "";
  const items = children.map((c) => {
    const d = describeDevice(c);
    return (
      `<li>${icon(deviceIcon(c))}<span class="name">${esc(d.name)}</span>` +
      ` <span class="sub">${esc(d.sub)}</span>${netHtml(c)}${storageHtml(c)}${inputsHtml(c)}${treeHtml(c.children)}</li>`
    );
  });
  return `<ul class="devtree">${items.join("")}</ul>`;
}

function modeLabel(p) {
  const m = p.mode;
  if (m === "usb_power_delivery") return "USB PD";
  if (m === "3.0A") return "5 V · 3 A";
  if (m === "1.5A") return "5 V · 1.5 A";
  if (m === "default") return "USB default";
  return m || "";
}

function slowCharger(p) {
  // only warn when the battery actually wants power: charging, or
  // draining while plugged in (firmware source attribution is unreliable)
  return (
    p &&
    p.charging_in &&
    batteryActive &&
    p.watts_in &&
    p.watts_max_in &&
    p.watts_in < 0.5 * p.watts_max_in
  );
}

function powerHtml(p) {
  if (!p) return "";
  const parts = [];
  if (p.role === "sink" && p.charging_in) {
    const w = p.watts_in ? ` ≈${p.watts_in} W` : "";
    parts.push(
      `<span class="in" title="active source as reported by firmware (can be stale after replugging)">⚡ in${w}</span>`
    );
  } else if (p.role === "sink" && p.partner_present) {
    parts.push(`<span class="idle">source idle</span>`);
  }
  if (p.role === "source" && p.partner_present)
    parts.push(`<span class="out">⚡ out</span>`);
  if (p.mode && p.partner_present) parts.push(esc(modeLabel(p)));
  if (slowCharger(p))
    parts.push(
      `<span class="slowwarn" title="this machine accepts up to ${esc(p.watts_max_in)} W">slow charger</span>`
    );
  return parts.join("<br>");
}

function esc(s) {
  const d = document.createElement("span");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

// a partner drawing power from us, or one we cannot see into, is not a
// charger: only power actually coming in makes it one
function isCharger(port) {
  const p = port.power;
  if (!p || !p.partner_present) return false;
  if (p.role === "sink" && p.charging_in) return true;
  return !port.device_unlinked;
}

function shortDeviceLabel(port) {
  if (!port || !port.connected) return "";
  const dev = port.device;
  if (dev) {
    const n = dev.product || dev.manufacturer || `${dev.vid}:${dev.pid}`;
    const extra = dev.children && dev.children.length ? ` +${dev.children.length}` : "";
    return (n.length > 14 ? n.slice(0, 13) + "…" : n) + extra;
  }
  if (port.power && port.power.partner_present)
    return isCharger(port) ? "charger" : "attached";
  if (port.card) return port.card.name || "card";
  if (port.kind === "hdmi" || port.kind === "dp") return "display";
  if (port.kind === "audio-jack") return "plugged";
  return "";
}

function renderPorts(ports, lay, form) {
  const box = $("ports");
  box.replaceChildren();
  const nowConnected = {};
  // physical order first: layout faces, slots in reading order
  const ordered = [];
  const used = new Set();
  for (const [side, slots] of Object.entries(lay.sides || {})) {
    const face = faceGeom(form, side);
    for (const s of [...slots].sort(
      (a, b) => a.pos.y - b.pos.y || a.pos.x - b.pos.x
    )) {
      const p = s.port_id && ports.find((x) => x.id === s.port_id);
      if (p) {
        ordered.push({ port: p, group: face ? face.label : side });
        used.add(p.id);
      }
    }
  }
  const hidden = new Set(lay.hidden || []);
  for (const p of ports.filter((x) => !used.has(x.id))) {
    if (hidden.has(p.id) && !p.connected && !editMode) continue;
    ordered.push({ port: p, group: lay.available ? "unplaced" : "" });
  }
  let lastGroup = null;
  for (const { port, group } of ordered) {
    if (group !== lastGroup && group) {
      const h = document.createElement("div");
      h.className = "side-h";
      h.textContent = group;
      box.appendChild(h);
    }
    lastGroup = group;
    nowConnected[port.id] = !!port.connected;
    const el = document.createElement("div");
    el.dataset.port = port.id;
    el.className = "port" + (port.connected ? " connected" : "");
    el.addEventListener("mouseenter", () => hlSlot(port.id, true));
    el.addEventListener("mouseleave", () => hlSlot(port.id, false));
    if (
      port.id in prevConnected &&
      prevConnected[port.id] !== !!port.connected
    )
      el.classList.add("pulse");

    let what;
    const dev = describeDevice(port.device);
    const loc = slotOfPort(lay, port.id);
    const locTxt = loc ? `${loc.side} · ` : "";
    const portId = `<span class="portid">${esc(locTxt)}${esc(port.id)}</span>`;
    if (dev) {
      what =
        `<div class="name">${icon(deviceIcon(port.device))}${esc(dev.name)}${portId}</div>` +
        `<div class="sub">${esc(dev.sub)}</div>` +
        netHtml(port.device) +
        storageHtml(port.device) +
        inputsHtml(port.device) +
        treeHtml(port.device.children);
    } else if (port.kind === "audio-jack") {
      const j = port.jack || {};
      what = j.readable
        ? `<div class="name">${port.connected ? "plugged" : "empty"}</div>` +
          `<div class="sub">headphone: ${j.headphone ? "yes" : "no"} · mic: ${j.microphone ? "yes" : "no"}</div>`
        : `<div class="name">state unavailable</div><div class="sub">needs /dev/input access</div>`;
    } else if (port.connected && port.power && port.power.partner_present && !port.device) {
      what = isCharger(port)
        ? `<div class="name">power adapter</div><div class="sub">power-only partner</div>`
        : `<div class="name">partner attached</div>` +
          `<div class="sub">firmware links no USB port to this connector, so the device is not visible</div>`;
    } else if (port.kind === "sd") {
      const c = port.card;
      what = c
        ? `<div class="name">${esc(c.name || "card")}${c.size_gb ? ` · ${c.size_gb} GB` : ""}</div>`
        : `<div class="name">empty</div>`;
    } else if (port.kind === "hdmi" || port.kind === "dp") {
      what = `<div class="name">${
        port.connected ? esc(port.monitor || "display connected") : "empty"
      }</div>`;
    } else {
      what = `<div class="name">empty</div>`;
    }
    if (!dev) what = what.replace("</div>", `${portId}</div>`);

    const isHidden = hidden.has(port.id);
    let editExtra = "";
    if (editMode && !loc) {
      editExtra =
        (isHidden ? `<span class="chip">hidden</span> ` : "") +
        `<button class="hidebtn">${isHidden ? "unhide" : "hide"}</button> ` +
        `<button class="placebtn">place on chassis</button>`;
    } else if (editMode && loc && loc.slot.extra) {
      editExtra = `<button class="placebtn unplace">unplace</button>`;
    }
    el.innerHTML =
      `<div class="glyph">${icon(PORT_ICON[port.kind] || "plug")}` +
      `<div>${esc(KIND_LABEL[port.kind] || port.kind)}</div></div>` +
      `<div class="what">${what}</div>` +
      `<div class="power">${powerHtml(port.power)}${editExtra}</div>`;
    const hideBtn = el.querySelector(".hidebtn");
    if (hideBtn)
      hideBtn.onclick = () =>
        fetch(`/api/port/${encodeURIComponent(port.id)}/hidden`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hidden: !isHidden }),
        });
    const placeBtn = el.querySelector(".placebtn");
    if (placeBtn)
      placeBtn.onclick = () =>
        placeBtn.classList.contains("unplace")
          ? fetch(`/api/slot/${encodeURIComponent(loc.slot.id)}/unplace`, {
              method: "POST",
            })
          : fetch(`/api/port/${encodeURIComponent(port.id)}/place`, {
              method: "POST",
            });
    box.appendChild(el);
  }
  prevConnected = nowConnected;
}

const BT_ICON = {
  "input-keyboard": "keyboard",
  "input-mouse": "mouse",
  "input-tablet": "touchpad",
  "audio-headset": "headphones",
  "audio-headphones": "headphones",
  "audio-card": "speaker",
  phone: "smartphone",
  computer: "monitor",
};

function btIcon(dev) {
  return BT_ICON[dev.icon] || "bluetooth";
}

function hlBt(address, on) {
  document
    .querySelectorAll(
      `#chassis g[data-bt="${CSS.escape(address)}"], #wireless li[data-bt="${CSS.escape(address)}"]`
    )
    .forEach((el) => el.classList.toggle("hl", on));
}

function renderWireless(btInfo) {
  const ul = $("wireless");
  const h = $("wireless-h");
  ul.replaceChildren();
  if (!btInfo || !btInfo.available || !btInfo.devices.length) {
    h.hidden = true;
    return;
  }
  h.hidden = false;
  const devices = [...btInfo.devices].sort(
    (a, b) => b.connected - a.connected || (a.name || "").localeCompare(b.name || "")
  );
  for (const d of devices) {
    const li = document.createElement("li");
    li.dataset.bt = d.address;
    if (!d.connected) li.className = "dim";
    li.addEventListener("mouseenter", () => hlBt(d.address, true));
    li.addEventListener("mouseleave", () => hlBt(d.address, false));
    const state = d.connected
      ? "connected" + (d.battery != null ? ` · ${d.battery}%` : "")
      : d.paired
        ? "paired"
        : "seen";
    li.innerHTML =
      `<span class="k">${icon(btIcon(d))}${esc(d.name || d.address)}</span>` +
      `<span>${esc(state)}</span>`;
    ul.appendChild(li);
  }
}

function renderBuiltins(builtins) {
  const ul = $("builtins");
  ul.replaceChildren();
  for (const b of builtins) {
    const li = document.createElement("li");
    li.dataset.builtin = b.kind;
    li.addEventListener("mouseenter", () => hlBuiltin(b.kind, true));
    li.addEventListener("mouseleave", () => hlBuiltin(b.kind, false));
    let value = esc(b.name || "");
    if (b.status) value += " · " + esc(b.status);
    if (b.kind === "camera" && b.node) value += ` · ${esc(b.node)}`;
    if (b.kind === "disk") {
      value = esc(b.name);
      if (b.size_gb) value += ` · ${b.size_gb} GB`;
      const mts = mountsLabel(b.mounts);
      if (mts) value += ` · ${esc(mts)}`;
    }
    if (b.kind === "display" && b.monitor)
      value = `${esc(b.name)} · ${esc(b.monitor)}`;
    if (b.in_use === true) value += ` <span class="inuse">● in use</span>`;
    let label = BUILTIN_LABEL[b.kind] || b.kind;
    if (b.kind === "camera" && b.infrared === true) label = "IR camera";
    if (b.kind === "camera" && b.infrared === false) label = "RGB camera";
    if (b.kind === "wifi") {
      const w = b.wifi || {};
      value = w.connected
        ? `${esc(b.name)} · ${esc(w.ssid)} · ${esc(w.signal_dbm)} dBm`
        : `${esc(b.name)} · not associated`;
    } else if (b.kind === "ethernet") {
      value = `${esc(b.name)} · ${b.carrier ? "link up" : "no link"}`;
    }
    li.innerHTML =
      `<span class="k">${icon(BUILTIN_ICON[b.kind] || "plug")}` +
      `${esc(label)}</span><span>${value}</span>`;
    ul.appendChild(li);
  }
}

function hlBuiltin(kind, on) {
  document
    .querySelectorAll(
      `#chassis g[data-builtin="${CSS.escape(kind)}"], #builtins li[data-builtin="${CSS.escape(kind)}"]`
    )
    .forEach((el) => el.classList.toggle("hl", on));
}

function hlSlot(portId, on) {
  document
    .querySelectorAll(`#chassis g[data-portid="${CSS.escape(portId)}"]`)
    .forEach((g) => g.classList.toggle("hl", on));
}

function hlCard(portId, on) {
  const card = document.querySelector(`.port[data-port="${CSS.escape(portId)}"]`);
  if (card) card.classList.toggle("hl", on);
}

function iconAt(name, x, y, size) {
  const svg = icon(name);
  if (!svg) return "";
  return svg
    .replace("<svg", `<svg x="${x}" y="${y}"`)
    .replace('width="24"', `width="${size}"`)
    .replace('height="24"', `height="${size}"`);
}

function laptopBody(snap) {
  const cams = (snap.builtins || []).filter((b) => b.kind === "camera");
  // top-down schematic: screen half (with camera dot) + base half
  return `
    <rect class="body" x="140" y="12" width="360" height="150" rx="10"/>
    <g data-builtin="display">
      <rect class="body" x="155" y="27" width="330" height="120" rx="4"/>
      <text x="320" y="92" text-anchor="middle">display</text>
    </g>
    <g data-builtin="camera">
      <circle cx="320" cy="20" r="3.5" class="${cams.length ? "active" : ""}${
        cams.some((c) => c.in_use) ? " camuse" : ""
      }"/>
    </g>
    <rect class="body" x="140" y="172" width="360" height="190" rx="10"/>
    <g data-builtin="keyboard">
      <rect class="body" x="165" y="187" width="310" height="85" rx="4"/>
      <text x="320" y="235" text-anchor="middle">keyboard</text>
    </g>
    <g data-builtin="touchpad">
      <rect class="body" x="260" y="288" width="120" height="58" rx="6"/>
      <text x="320" y="322" text-anchor="middle">touchpad</text>
    </g>`;
}

function desktopBody() {
  // a tower has no lid, keyboard or touchpad: draw the case with its
  // port-bearing faces unfolded as labelled 2D panels
  let s = `<rect class="body" x="12" y="10" width="616" height="420" rx="10"/>`;
  for (const f of Object.values(FACES.desktop)) {
    s +=
      `<rect class="strip" x="${f.x}" y="${f.y}" width="${f.w}" height="${f.h}" rx="8"/>` +
      `<text x="${f.x + f.w / 2}" y="${f.y - 6}" text-anchor="middle">${esc(f.label)}</text>`;
  }
  return s;
}

function chassisBody(form, snap) {
  return form === "desktop" ? desktopBody() : laptopBody(snap);
}

function slotSvg(snap, lay, form, faceName, s) {
  const face = faceGeom(form, faceName);
  if (!face) return ""; // face this layout names isn't drawn for this form
  const { x, y } = slotXY(face, s.pos);
  const port = (snap.ports || []).find((p) => p.id === s.port_id);
  const unbound = !s.binding && !PASSIVE_SLOTS.has(s.type);
  const armed = lay.calibration && lay.calibration.slot === s.id ? " armed" : "";
  const cls =
    "slot" +
    (port && port.connected ? " on" : "") +
    (unbound ? " unbound" : "") +
    armed;
  const status = unbound
    ? "not calibrated — click to bind"
    : port
      ? port.connected
        ? "connected"
        : "empty"
      : "";
  // power flow triangle: pointing toward the machine = power in
  let arrow = "";
  const pw = port && port.power;
  if (
    pw &&
    pw.partner_present &&
    ((pw.role === "sink" && pw.charging_in) || pw.role === "source")
  ) {
    const isIn = pw.role === "sink";
    const acls = isIn ? "pwr-in" : "pwr-out";
    // on an edge the arrow sits beside the marker and points at the body;
    // on a panel it sits to the right and points back at the port
    const dir = face.kind === "edge" ? (isIn ? face.inward : -face.inward) : isIn ? -1 : 1;
    const bx =
      face.kind === "edge"
        ? face.inward === 1
          ? x + 34
          : x - 12
        : x + SLOT_W + 8;
    arrow =
      `<path class="${acls}" d="M ${bx - dir * 4} ${y + 5} L ${bx + dir * 5} ${y + 11} ` +
      `L ${bx - dir * 4} ${y + 17} Z"><title>power ${isIn ? "in" : "out"}</title></path>`;
  }
  // only connected ports carry a label; everything else is on the tooltip
  // and the linked ports list
  let label = shortDeviceLabel(port);
  let labelSvg = "";
  if (label) {
    if (face.kind === "panel") {
      // panel columns are far narrower than an edge's free margin, so the
      // label is cut harder to keep neighbouring ports legible
      if (label.length > 11) label = label.slice(0, 10) + "…";
      labelSvg =
        `<text class="slotlabel" x="${x + SLOT_W / 2}" y="${y + SLOT_H + 11}" ` +
        `text-anchor="middle">${esc(label)}</text>`;
    } else if (face.inward === 1) {
      labelSvg = `<text class="slotlabel" x="${x + 40 + (arrow ? 6 : 0)}" y="${y + 15}">${esc(label)}</text>`;
    } else {
      labelSvg =
        `<text class="slotlabel" x="${x - 12 - (arrow ? 10 : 0)}" y="${y + 15}" ` +
        `text-anchor="end">${esc(label)}</text>`;
    }
  }
  return (
    `<g class="${cls}${editMode ? " editable" : ""}" data-slot="${esc(s.id)}" ` +
    `data-portid="${esc(s.port_id || "")}" data-basex="${x}" data-basey="${y}" ` +
    `data-label="${esc(s.label || "")}">` +
    `<rect class="marker" x="${x}" y="${y}" width="${SLOT_W}" height="${SLOT_H}" rx="4"/>` +
    iconAt(SLOT_ICON[s.type] || "plug", x + 5, y + 3, 16) +
    arrow +
    labelSvg +
    `<title>${esc(s.label)}${status ? " — " + status : ""}</title></g>`
  );
}

function renderChassis(snap) {
  const lay = snap.layout || {};
  const form = formOf(snap);
  const svg = $("chassis");
  svg.setAttribute("aria-label", `${form} schematic`);
  let inner = chassisBody(form, snap);
  const satellites = [];
  if (lay.available) {
    if (form !== "desktop")
      for (const [name, f] of Object.entries(FACES[form]))
        if (f.kind === "edge")
          inner +=
            `<rect class="strip" x="${f.x}" y="30" width="34" height="330" rx="8"/>` +
            `<text x="${f.x + 17}" y="24" text-anchor="middle">${esc(name)}</text>`;
    for (const [faceName, slots] of Object.entries(lay.sides || {}))
      for (const s of slots) {
        inner += slotSvg(snap, lay, form, faceName, s);
        const face = faceGeom(form, faceName);
        const port = (snap.ports || []).find((p) => p.id === s.port_id);
        if (face && port && port.device && (port.device.children || []).length)
          satellites.push({ port, face, ...slotXY(face, s.pos) });
      }
  } else {
    inner += `<text x="320" y="374" text-anchor="middle">no layout for this machine</text>`;
  }
  // wireless halo: connected bluetooth devices as badges under the chassis
  const btDevs = ((snap.bluetooth || {}).devices || []).filter((d) => d.connected);
  const haloY = HALO_Y[form];
  if (btDevs.length) {
    const widths = btDevs.map((d) =>
      Math.min(120, 30 + ((d.name || d.address).length > 10 ? 10 : (d.name || d.address).length) * 6.6)
    );
    let bx = 320 - (widths.reduce((a, b) => a + b + 8, 0) - 8) / 2;
    btDevs.forEach((d, i) => {
      const w = widths[i];
      const name = (d.name || d.address).slice(0, 10);
      const title =
        `${d.name || d.address} — connected` +
        (d.battery != null ? ` · battery ${d.battery}%` : "");
      inner +=
        `<g class="btbadge" data-bt="${esc(d.address)}">` +
        `<rect class="marker" x="${bx}" y="${haloY}" width="${w}" height="22" rx="11"/>` +
        iconAt(btIcon(d), bx + 6, haloY + 3, 15) +
        `<text class="slotlabel" x="${bx + 24}" y="${haloY + 15}">${esc(name)}</text>` +
        `<title>${esc(title)}</title></g>`;
      bx += w + 8;
    });
  }
  // hubs/docks as satellite boxes below the chassis
  const H = CONTENT_H[form];
  let viewH = H;
  if (satellites.length) {
    viewH = H + 90;
    const W = 160;
    const GAP = 14;
    let bx = 320 - (satellites.length * (W + GAP) - GAP) / 2;
    for (const s of satellites) {
      const d = s.port.device;
      const title = d.product || "hub";
      const edgeFace = s.face.kind === "edge";
      let icons = "";
      (d.children || [])
        .slice(0, 7)
        .forEach((c, i) => (icons += iconAt(deviceIcon(c), bx + 10 + i * 20, H + 32, 15)));
      // route down the outside of the machine so the link never crosses
      // other ports: an edge slot leaves sideways, a panel slot drops to
      // the lane under its own face first
      const left = edgeFace ? s.face.inward === 1 : s.x + SLOT_W / 2 < 320;
      const edge = left ? 10 : 630;
      const exitX = edgeFace ? (left ? s.x : s.x + SLOT_W) : s.x + SLOT_W / 2;
      const lane = edgeFace ? s.y + 11 : s.face.y + s.face.h + 6;
      inner +=
        `<path class="satlink" d="M ${exitX} ${edgeFace ? s.y + 11 : s.y + SLOT_H} ` +
        (edgeFace ? "" : `L ${exitX} ${lane} `) +
        `L ${edge} ${lane} L ${edge} ${H + 4} L ${bx + W / 2} ${H + 4} ` +
        `L ${bx + W / 2} ${H + 12}"/>` +
        `<g class="satellite" data-portid="${esc(s.port.id)}">` +
        `<rect class="marker" x="${bx}" y="${H + 12}" width="${W}" height="44" rx="8"/>` +
        `<text class="slotlabel" x="${bx + 10}" y="${H + 26}">${esc(title.slice(0, 22))}</text>` +
        icons +
        `<title>${esc(title)} — ${(d.children || []).length} device(s)</title></g>`;
      bx += W + GAP;
    }
  }
  svg.setAttribute("viewBox", `0 0 640 ${viewH}`);
  svg.innerHTML = inner;
  svg.querySelectorAll("g.satellite").forEach((g) => {
    const pid = g.dataset.portid;
    g.addEventListener("mouseenter", () => hlCard(pid, true));
    g.addEventListener("mouseleave", () => hlCard(pid, false));
    g.addEventListener("click", () => {
      const card = document.querySelector(`.port[data-port="${CSS.escape(pid)}"]`);
      if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });
  svg.querySelectorAll("g[data-bt]").forEach((g) => {
    g.addEventListener("mouseenter", () => hlBt(g.dataset.bt, true));
    g.addEventListener("mouseleave", () => hlBt(g.dataset.bt, false));
  });
  svg.querySelectorAll("g[data-builtin]").forEach((g) => {
    g.addEventListener("mouseenter", () => hlBuiltin(g.dataset.builtin, true));
    g.addEventListener("mouseleave", () => hlBuiltin(g.dataset.builtin, false));
  });
  svg.querySelectorAll("g[data-slot]").forEach((g) => {
    if (editMode) {
      g.addEventListener("pointerdown", (evt) => {
        evt.preventDefault();
        drag = {
          slotId: g.dataset.slot,
          g,
          form: formOf(snap),
          baseX: parseFloat(g.dataset.basex),
          baseY: parseFloat(g.dataset.basey),
        };
      });
      g.addEventListener("dblclick", async () => {
        const label = prompt("Slot label:", g.dataset.label || "");
        if (label !== null && label.trim() !== "")
          await fetch(`/api/slot/${encodeURIComponent(g.dataset.slot)}/label`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label: label.trim() }),
          });
      });
      return;
    }
    if (g.classList.contains("unbound"))
      g.addEventListener("click", () => armSlot(g.dataset.slot));
    const pid = g.dataset.portid;
    if (pid) {
      g.addEventListener("mouseenter", () => hlCard(pid, true));
      g.addEventListener("mouseleave", () => hlCard(pid, false));
      g.addEventListener("click", () => {
        const card = document.querySelector(`.port[data-port="${CSS.escape(pid)}"]`);
        if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }
  });
}

let wizardActive = false;

async function armSlot(slotId) {
  await fetch(`/api/calibrate/${encodeURIComponent(slotId)}`, { method: "POST" });
}

function renderWizard(snap) {
  const w = $("wizard");
  const lay = snap.layout || {};
  if (!lay.available) {
    w.replaceChildren();
    return;
  }
  if (lay.calibration) {
    const found = Object.values(lay.sides || {})
      .flat()
      .find((s) => s.id === lay.calibration.slot);
    w.innerHTML =
      `<span class="chip warn">plug something into: ${esc(found ? found.label : lay.calibration.slot)} (if occupied, unplug &amp; replug)</span> ` +
      `<button id="calcancel">cancel</button>`;
    $("calcancel").onclick = async () => {
      wizardActive = false;
      await fetch("/api/calibrate", { method: "DELETE" });
    };
  } else if (lay.unbound && lay.unbound.length) {
    w.innerHTML = `<button id="calbtn">calibrate ${lay.unbound.length} port(s)</button>`;
    $("calbtn").onclick = () => {
      wizardActive = true;
      armSlot(lay.unbound[0]);
    };
    if (wizardActive) armSlot(lay.unbound[0]);
  } else {
    w.replaceChildren();
    wizardActive = false;
  }
}

function logEvents(events) {
  if (!events || !events.length) return;
  const ul = $("events");
  const ts = new Date().toLocaleTimeString();
  for (const ev of events) {
    if (ev.subsystem === "input" || ev.action === "poll") continue;
    const li = document.createElement("li");
    const leaf = (ev.devpath || "").split("/").pop();
    li.textContent = `${ts} ${ev.action} ${ev.subsystem} ${leaf}`;
    ul.prepend(li);
  }
  while (ul.children.length > 100) ul.removeChild(ul.lastChild);
}

function svgPos(evt) {
  const svg = $("chassis");
  const pt = new DOMPoint(evt.clientX, evt.clientY);
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

// the droppable rectangle of a face: an edge's is its whole strip
function faceRect(face) {
  return face.kind === "edge"
    ? { x: face.x, y: 30, w: 34, h: 330 }
    : { x: face.x, y: face.y, w: face.w, h: face.h };
}

// face under the cursor, else the nearest one — so a slot dropped just
// outside a face still lands somewhere sensible instead of snapping back
function faceAt(form, p) {
  let best = null;
  for (const [name, face] of Object.entries(FACES[form])) {
    const r = faceRect(face);
    if (p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h)
      return { name, face };
    const dx = Math.max(r.x - p.x, 0, p.x - (r.x + r.w));
    const dy = Math.max(r.y - p.y, 0, p.y - (r.y + r.h));
    const d = dx * dx + dy * dy;
    if (!best || d < best.d) best = { name, face, d };
  }
  return best;
}

const clamp01 = (v) => Math.max(0, Math.min(0.95, v));

// inverse of slotXY: cursor → normalized position, marker centred on it
function posInFace(face, p) {
  const y = clamp01((p.y - SLOT_H / 2 - face.y) / faceSpanY(face));
  const x =
    face.kind === "edge" ? 0 : clamp01((p.x - SLOT_W / 2 - face.x) / (face.w - SLOT_W));
  return { x, y };
}

document.addEventListener("pointermove", (evt) => {
  if (!drag) return;
  const p = svgPos(evt);
  const hit = faceAt(drag.form, p);
  if (!hit) return;
  drag.side = hit.name;
  drag.pos = posInFace(hit.face, p);
  const t = slotXY(hit.face, drag.pos);
  drag.g.setAttribute(
    "transform",
    `translate(${t.x - drag.baseX},${t.y - drag.baseY})`
  );
});

document.addEventListener("pointerup", async () => {
  if (!drag) return;
  const d = drag;
  drag = null;
  if (d.side !== undefined) {
    await fetch(`/api/slot/${encodeURIComponent(d.slotId)}/position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ side: d.side, x: d.pos.x, y: d.pos.y }),
    });
  }
  if (pendingSnap) {
    const s = pendingSnap;
    pendingSnap = null;
    render(s);
  }
});

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  const conn = $("connstate");
  let ping;
  ws.onopen = () => {
    conn.textContent = "live";
    conn.className = "chip ok";
    ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 20000);
  };
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.type === "snapshot") {
      if (drag) {
        pendingSnap = data.data; // don't re-render under the user's cursor
      } else {
        render(data.data);
      }
      logEvents(data.events);
    }
  };
  ws.onclose = () => {
    conn.textContent = "reconnecting…";
    conn.className = "chip warn";
    clearInterval(ping);
    setTimeout(connect, 2000);
  };
}

connect();
