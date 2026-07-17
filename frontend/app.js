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
  return { name, sub: bits.join(" · ") };
}

function treeHtml(children) {
  if (!children || !children.length) return "";
  const items = children.map((c) => {
    const d = describeDevice(c);
    return (
      `<li>${icon(deviceIcon(c))}<span class="name">${esc(d.name)}</span>` +
      ` <span class="sub">${esc(d.sub)}</span>${netHtml(c)}${treeHtml(c.children)}</li>`
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
    const portId = `<span class="portid">${esc(port.id)}</span>`;
    if (dev) {
      what =
        `<div class="name">${icon(deviceIcon(port.device))}${esc(dev.name)}${portId}</div>` +
        `<div class="sub">${esc(dev.sub)}</div>` +
        netHtml(port.device) +
        treeHtml(port.device.children);
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
