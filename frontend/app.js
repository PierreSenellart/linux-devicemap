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
};

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
      const state = s.media
        ? `${s.size_gb} GB`
        : s.removable
          ? "empty (no media)"
          : "no media";
      return `<div class="sub net">${icon("hard-drive")} ${esc(s.dev)} · ${esc(state)}</div>`;
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

function render(snap) {
  const m = snap.machine || {};
  $("machine").textContent = [m.vendor, m.product].filter(Boolean).join(" ");
  renderPower(snap.power || {});
  const lay = snap.layout || {};
  $("ports-note").textContent = !lay.available
    ? "no layout for this machine — positions unknown"
    : lay.unbound && lay.unbound.length
      ? `${lay.unbound.length} port(s) not calibrated`
      : lay.status === "draft"
        ? "layout: draft"
        : "";
  renderPorts(snap.ports || [], lay);
  renderBuiltins(snap.builtins || []);
  renderChassis(snap);
  renderWizard(snap);
}

function slotOfPort(lay, portId) {
  for (const [side, slots] of Object.entries(lay.sides || {})) {
    const slot = slots.find((s) => s.port_id === portId);
    if (slot) return { side, slot };
  }
  return null;
}

function renderPower(power) {
  const bat = (power.batteries || [])[0];
  const chip = $("powerchip");
  if (!bat) {
    chip.textContent = power.ac_online ? "AC power" : "power: ?";
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
      ` <span class="sub">${esc(d.sub)}</span>${netHtml(c)}${storageHtml(c)}${treeHtml(c.children)}</li>`
    );
  });
  return `<ul class="devtree">${items.join("")}</ul>`;
}

function powerHtml(p) {
  if (!p) return "";
  const parts = [];
  if (p.role === "sink" && (p.charging_in || p.partner_present))
    parts.push(`<span class="in">⚡ in</span>`);
  if (p.role === "source" && p.partner_present)
    parts.push(`<span class="out">⚡ out</span>`);
  if (p.mode && p.partner_present) parts.push(esc(p.mode));
  return parts.join("<br>");
}

function esc(s) {
  const d = document.createElement("span");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function shortDeviceLabel(port) {
  if (!port || !port.connected) return "";
  const dev = port.device;
  if (dev) {
    const n = dev.product || dev.manufacturer || `${dev.vid}:${dev.pid}`;
    const extra = dev.children && dev.children.length ? ` +${dev.children.length}` : "";
    return (n.length > 14 ? n.slice(0, 13) + "…" : n) + extra;
  }
  if (port.power && port.power.partner_present) return "charger";
  if (port.card) return port.card.name || "card";
  if (port.kind === "hdmi" || port.kind === "dp") return "display";
  if (port.kind === "audio-jack") return "plugged";
  return "";
}

function renderPorts(ports, lay) {
  const box = $("ports");
  box.replaceChildren();
  const nowConnected = {};
  // physical order first: layout sides, slots sorted rear→front
  const ordered = [];
  const used = new Set();
  for (const [side, slots] of Object.entries(lay.sides || {})) {
    for (const s of [...slots].sort((a, b) => a.pos - b.pos)) {
      const p = s.port_id && ports.find((x) => x.id === s.port_id);
      if (p) {
        ordered.push({ port: p, group: `${side} side` });
        used.add(p.id);
      }
    }
  }
  const hidden = new Set(lay.hidden || []);
  for (const p of ports.filter((x) => !used.has(x.id))) {
    if (hidden.has(p.id) && !p.connected) continue;
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
        treeHtml(port.device.children);
    } else if (port.kind === "audio-jack") {
      const j = port.jack || {};
      what = j.readable
        ? `<div class="name">${port.connected ? "plugged" : "empty"}</div>` +
          `<div class="sub">headphone: ${j.headphone ? "yes" : "no"} · mic: ${j.microphone ? "yes" : "no"}</div>`
        : `<div class="name">state unavailable</div><div class="sub">needs /dev/input access</div>`;
    } else if (port.connected && port.power && port.power.partner_present && !port.device) {
      what = `<div class="name">power adapter</div><div class="sub">power-only partner</div>`;
    } else if (port.kind === "sd") {
      const c = port.card;
      what = c
        ? `<div class="name">${esc(c.name || "card")}${c.size_gb ? ` · ${c.size_gb} GB` : ""}</div>`
        : `<div class="name">empty</div>`;
    } else if (port.kind === "hdmi" || port.kind === "dp") {
      what = `<div class="name">${port.connected ? "display connected" : "empty"}</div>`;
    } else {
      what = `<div class="name">empty</div>`;
    }
    if (!dev) what = what.replace("</div>", `${portId}</div>`);

    el.innerHTML =
      `<div class="glyph">${icon(PORT_ICON[port.kind] || "plug")}` +
      `<div>${esc(KIND_LABEL[port.kind] || port.kind)}</div></div>` +
      `<div class="what">${what}</div>` +
      `<div class="power">${powerHtml(port.power)}</div>`;
    box.appendChild(el);
  }
  prevConnected = nowConnected;
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

function renderChassis(snap) {
  const cams = (snap.builtins || []).filter((b) => b.kind === "camera");
  const lay = snap.layout || {};
  const svg = $("chassis");
  // top-down schematic: screen half (with camera dot) + base half
  let inner = `
    <rect class="body" x="140" y="12" width="360" height="150" rx="10"/>
    <g data-builtin="display">
      <rect class="body" x="155" y="27" width="330" height="120" rx="4"/>
      <text x="320" y="92" text-anchor="middle">display</text>
    </g>
    <g data-builtin="camera">
      <circle cx="320" cy="20" r="3.5" class="${cams.length ? "active" : ""}"/>
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
  if (lay.available) {
    const STRIP = { left: 18, right: 588 };
    for (const [side, slots] of Object.entries(lay.sides || {})) {
      const x = STRIP[side];
      if (x === undefined) continue;
      inner += `<rect class="strip" x="${x}" y="30" width="34" height="330" rx="8"/>`;
      inner += `<text x="${x + 17}" y="24" text-anchor="middle">${esc(side)}</text>`;
      for (const s of slots) {
        const y = 38 + s.pos * 296;
        const port = (snap.ports || []).find((p) => p.id === s.port_id);
        const unbound = !s.binding && !PASSIVE_SLOTS.has(s.type);
        const armed =
          lay.calibration && lay.calibration.slot === s.id ? " armed" : "";
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
        const label = shortDeviceLabel(port);
        const labelSvg = label
          ? side === "left"
            ? `<text class="slotlabel" x="${x + 44}" y="${y + 15}">${esc(label)}</text>`
            : `<text class="slotlabel" x="${x - 8}" y="${y + 15}" text-anchor="end">${esc(label)}</text>`
          : "";
        inner +=
          `<g class="${cls}" data-slot="${esc(s.id)}" data-portid="${esc(s.port_id || "")}">` +
          `<rect class="marker" x="${x + 4}" y="${y}" width="26" height="22" rx="4"/>` +
          iconAt(SLOT_ICON[s.type] || "plug", x + 9, y + 3, 16) +
          labelSvg +
          `<title>${esc(s.label)}${status ? " — " + status : ""}</title></g>`;
      }
    }
  } else {
    inner += `<text x="320" y="374" text-anchor="middle">no layout for this machine</text>`;
  }
  svg.innerHTML = inner;
  svg.querySelectorAll("g[data-builtin]").forEach((g) => {
    g.addEventListener("mouseenter", () => hlBuiltin(g.dataset.builtin, true));
    g.addEventListener("mouseleave", () => hlBuiltin(g.dataset.builtin, false));
  });
  svg.querySelectorAll("g[data-slot]").forEach((g) => {
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
      render(data.data);
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
