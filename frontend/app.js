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
};

const BUILTIN_LABEL = {
  keyboard: "Keyboard",
  touchpad: "Touchpad",
  camera: "Camera",
  bluetooth: "Bluetooth",
  display: "Built-in display",
  "usb-internal": "Internal USB",
};

let prevConnected = {}; // port id → bool, to pulse on change

function render(snap) {
  const m = snap.machine || {};
  $("machine").textContent = [m.vendor, m.product].filter(Boolean).join(" ");
  renderPower(snap.power || {});
  renderPorts(snap.ports || []);
  renderBuiltins(snap.builtins || []);
  renderChassis(snap);
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
  if (dev.children && dev.children.length)
    bits.push(`hub: ${dev.children.length} device(s)`);
  return { name, sub: bits.join(" · ") };
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

function renderPorts(ports) {
  const box = $("ports");
  box.replaceChildren();
  const nowConnected = {};
  for (const port of ports) {
    nowConnected[port.id] = !!port.connected;
    const el = document.createElement("div");
    el.className = "port" + (port.connected ? " connected" : "");
    if (
      port.id in prevConnected &&
      prevConnected[port.id] !== !!port.connected
    )
      el.classList.add("pulse");

    let what;
    const dev = describeDevice(port.device);
    if (dev) {
      what = `<div class="name">${esc(dev.name)}</div><div class="sub">${esc(dev.sub)}</div>`;
    } else if (port.kind === "audio-jack") {
      const j = port.jack || {};
      what = j.readable
        ? `<div class="name">${port.connected ? "plugged" : "empty"}</div>` +
          `<div class="sub">headphone: ${j.headphone ? "yes" : "no"} · mic: ${j.microphone ? "yes" : "no"}</div>`
        : `<div class="name">state unavailable</div><div class="sub">needs /dev/input access</div>`;
    } else if (port.connected && port.power && port.power.partner_present && !port.device) {
      what = `<div class="name">power adapter</div><div class="sub">power-only partner</div>`;
    } else if (port.kind === "hdmi" || port.kind === "dp") {
      what = `<div class="name">${port.connected ? "display connected" : "empty"}</div>`;
    } else {
      what = `<div class="name">empty</div>`;
    }

    el.innerHTML =
      `<div class="glyph">${esc(KIND_LABEL[port.kind] || port.kind)}</div>` +
      `<div class="what">${what}<div class="sub">${esc(port.id)}</div></div>` +
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
    li.innerHTML =
      `<span class="k">${esc(BUILTIN_LABEL[b.kind] || b.kind)}</span>` +
      `<span>${esc(b.name || "")}${b.status ? " · " + esc(b.status) : ""}</span>`;
    ul.appendChild(li);
  }
}

function renderChassis(snap) {
  const cams = (snap.builtins || []).filter((b) => b.kind === "camera");
  const svg = $("chassis");
  // top-down schematic: screen half (with camera dot) + base half
  svg.innerHTML = `
    <rect class="body" x="30" y="10" width="360" height="150" rx="10"/>
    <rect class="body" x="45" y="25" width="330" height="120" rx="4"/>
    <circle cx="210" cy="18" r="3.5" class="${cams.length ? "active" : ""}"/>
    <text x="210" y="90" text-anchor="middle">display</text>
    <rect class="body" x="30" y="170" width="360" height="160" rx="10"/>
    <rect class="body" x="55" y="185" width="310" height="75" rx="4"/>
    <text x="210" y="228" text-anchor="middle">keyboard</text>
    <rect class="body" x="150" y="272" width="120" height="48" rx="6"/>
    <text x="210" y="300" text-anchor="middle">touchpad</text>`;
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
