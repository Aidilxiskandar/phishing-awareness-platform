// In-world UI screens (phone, monitors, wall displays) drawn on canvases. Every screen state is a string key;
// identical keys share one texture, so a held state costs nothing per frame. Brands are fictional on purpose.
import * as THREE from "three";

type Draw = (g: CanvasRenderingContext2D, w: number, h: number) => void;
const cache = new Map<string, THREE.CanvasTexture>();
export const screenTex = (key: string, w: number, h: number, draw: Draw) => {
  const k = `${w}x${h}|${key}`;
  let t = cache.get(k);
  if (!t) {
    const cv = document.createElement("canvas"); cv.width = w; cv.height = h;
    const g = cv.getContext("2d")!;
    draw(g, w, h);
    t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
    cache.set(k, t);
    if (cache.size > 400) { const first = cache.keys().next().value as string; cache.get(first)!.dispose(); cache.delete(first); }
  }
  return t;
};

const FONT = (px: number, wt = 600) => `${wt} ${px}px -apple-system, "Helvetica Neue", Arial, sans-serif`;
const rr = (g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number, col: string) => { g.beginPath(); g.roundRect(x, y, w, h, r); g.fillStyle = col; g.fill(); };
const text = (g: CanvasRenderingContext2D, s: string, x: number, y: number, px: number, col: string, align: CanvasTextAlign = "left", wt = 600) => {
  g.font = FONT(px, wt); g.fillStyle = col; g.textAlign = align; g.textBaseline = "middle"; g.fillText(s, x, y);
};
const shield = (g: CanvasRenderingContext2D, x: number, y: number, s: number, col: string) => {
  g.beginPath(); g.moveTo(x - s, y - s); g.lineTo(x + s, y - s); g.lineTo(x + s, y); g.quadraticCurveTo(x + s * 0.8, y + s, x, y + s * 1.3);
  g.quadraticCurveTo(x - s * 0.8, y + s, x - s, y); g.closePath(); g.fillStyle = col; g.fill();
};

// ---------------- phone (portrait 512 x 1024) ----------------
export type PhoneState =
  | { kind: "home" }
  | { kind: "prompt"; press?: "deny" | "approve" | null; t?: number; stack?: number }
  | { kind: "chat"; shown: number; typing?: boolean }
  | { kind: "approved" };
const promptCard = (g: CanvasRenderingContext2D, y: number, w: number, press: "deny" | "approve" | null | undefined, t: number, dim = 1) => {
  g.globalAlpha = dim;
  rr(g, 28, y, w - 56, 330, 26, "#ffffff");
  shield(g, 82, y + 62, 20, "#2f6fd6");
  text(g, "Nimbus Secure Login", 120, y + 58, 26, "#1b2433");
  text(g, "now", w - 60, y + 58, 22, "#8a93a3", "right", 500);
  text(g, "Approve this login?", 56, y + 128, 36, "#111827", "left", 700);
  text(g, "Sign-in request · new device", 56, y + 172, 24, "#5b6576", "left", 500);
  const bw = (w - 56 - 72) / 2;
  const bx = [52, 52 + bw + 20];
  ([["Deny", "#fde8e8", "#c81e1e", "deny"], ["Approve", "#16a34a", "#ffffff", "approve"]] as const).forEach(([lab, bg, fg, id], i) => {
    const on = press === id;
    rr(g, bx[i], y + 222, bw, 78, 18, on ? (id === "deny" ? "#f8b4b4" : "#0e8a3c") : bg);
    text(g, lab, bx[i] + bw / 2, y + 262, 32, fg, "center", 700);
    if (on && t > 0) { // tap ripple
      g.beginPath(); g.arc(bx[i] + bw / 2, y + 262, 30 + t * 90, 0, Math.PI * 2);
      g.strokeStyle = id === "deny" ? `rgba(200,30,30,${1 - t})` : `rgba(255,255,255,${1 - t})`; g.lineWidth = 8; g.stroke();
    }
  });
  g.globalAlpha = 1;
};
export const phoneTex = (s: PhoneState) => {
  const key = JSON.stringify(s);
  return screenTex("phone" + key, 512, 1024, (g, w, h) => {
    const bg = g.createLinearGradient(0, 0, 0, h); bg.addColorStop(0, "#3b5ba8"); bg.addColorStop(1, "#1b2650");
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    text(g, "9:41", 40, 36, 24, "#ffffff", "left", 600);
    if (s.kind === "home") {
      text(g, "9:41", w / 2, 230, 120, "#ffffff", "center", 300);
      text(g, "Thursday 15 September", w / 2, 320, 28, "#dfe6ff", "center", 500);
    }
    if (s.kind === "prompt") {
      const n = Math.min(s.stack ?? 1, 6);
      for (let i = n - 1; i >= 0; i--) promptCard(g, 160 + i * 64, w, i === 0 ? s.press : null, s.t ?? 0, i === 0 ? 1 : 0.9 - i * 0.08);
    }
    if (s.kind === "approved") {
      g.beginPath(); g.arc(w / 2, 420, 110, 0, Math.PI * 2); g.fillStyle = "#16a34a"; g.fill();
      g.beginPath(); g.moveTo(w / 2 - 50, 420); g.lineTo(w / 2 - 12, 462); g.lineTo(w / 2 + 56, 380); g.strokeStyle = "#fff"; g.lineWidth = 22; g.lineCap = "round"; g.stroke();
      text(g, "Login approved", w / 2, 600, 40, "#ffffff", "center", 700);
    }
    if (s.kind === "chat") {
      g.fillStyle = "#ece5dd"; g.fillRect(0, 0, w, h);
      g.fillStyle = "#075e54"; g.fillRect(0, 0, w, 150);
      text(g, "9:42", 40, 36, 24, "#ffffff");
      g.beginPath(); g.arc(80, 102, 32, 0, Math.PI * 2); g.fillStyle = "#e9edf5"; g.fill();
      shield(g, 80, 98, 17, "#2f6fd6");
      text(g, "IT Support", 128, 92, 30, "#ffffff", "left", 700);
      text(g, s.typing ? "typing…" : "online", 128, 124, 22, "#cfe9e4", "left", 500);
      const msgs = ["Hi, this is IT support.", "Those alerts will only", "stop once you accept one."];
      let y = 210;
      if (s.shown >= 1) { rr(g, 28, y, 370, 78, 16, "#ffffff"); text(g, msgs[0], 50, y + 39, 27, "#111b21", "left", 500); y += 100; }
      if (s.shown >= 2) { rr(g, 28, y, 400, 120, 16, "#ffffff"); text(g, msgs[1], 50, y + 38, 27, "#111b21", "left", 500); text(g, msgs[2], 50, y + 80, 27, "#111b21", "left", 500); y += 140; }
      if (s.typing) { rr(g, 28, y, 110, 60, 16, "#ffffff"); for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(60 + i * 24, y + 30, 7, 0, Math.PI * 2); g.fillStyle = "#9aa4ab"; g.fill(); } }
    }
  });
};

// ---------------- monitors (16:10, 800 x 500) ----------------
export type MonitorState =
  | { kind: "login"; fill: number }
  | { kind: "market"; pick: number }
  | { kind: "phonelock" }
  | { kind: "signing"; n: number }
  | { kind: "chatdesk"; chars: number }
  | { kind: "staffchat"; shown: number }
  | { kind: "code"; seed: number }
  | { kind: "soc"; alert: boolean; seed: number }
  | { kind: "office"; seed: number }
  | { kind: "off" };
export const monitorTex = (s: MonitorState) => screenTex("mon" + JSON.stringify(s), 800, 500, (g, w, h) => {
  g.fillStyle = "#0b1220"; g.fillRect(0, 0, w, h);
  if (s.kind === "off") return;
  if (s.kind === "login") {
    g.fillStyle = "#e8eef8"; g.fillRect(0, 0, w, h);
    rr(g, 220, 60, 360, 380, 22, "#ffffff");
    shield(g, w / 2, 120, 22, "#2f6fd6");
    text(g, "Nimbus · Staff sign in", w / 2, 180, 26, "#1b2433", "center", 700);
    rr(g, 260, 220, 280, 48, 10, "#eef2f8"); text(g, "contractor@nimbus.example", 276, 244, 19, "#334155", "left", 500);
    rr(g, 260, 286, 280, 48, 10, "#eef2f8");
    const n = Math.round(s.fill * 10);
    text(g, "•".repeat(n), 278, 311, 34, "#111827", "left", 700);
    rr(g, 260, 360, 280, 52, 12, s.fill >= 1 ? "#2f6fd6" : "#9db7e6"); text(g, "Sign in", w / 2, 386, 22, "#ffffff", "center", 700);
  }
  if (s.kind === "market") {
    text(g, "▌stolen-logins // listings", 30, 36, 22, "#7CFC9A", "left", 600);
    const rows = ["contractor@nimbus · work login", "admin@shop-x · email", "staff@clinic-y · vpn", "hr@school-z · email", "dev@app-q · git"];
    rows.forEach((r, i) => {
      const y = 90 + i * 76, on = i === 0;
      rr(g, 24, y, w - 48, 62, 8, on && s.pick > 0 ? "#183b26" : "#121a2b");
      text(g, r, 44, y + 31, 22, on ? "#c6ffd4" : "#9fb0c8", "left", 500);
      rr(g, w - 170, y + 12, 120, 38, 8, on && s.pick > 0.5 ? "#2fbf6a" : "#26324a");
      text(g, on && s.pick > 0.5 ? "BOUGHT" : "BUY", w - 110, y + 31, 18, "#ffffff", "center", 700);
    });
  }
  if (s.kind === "phonelock") {
    rr(g, w / 2 - 80, 70, 160, 300, 26, "#e6ebf5"); rr(g, w / 2 - 66, 92, 132, 252, 14, "#2f6fd6");
    g.beginPath(); g.arc(w / 2, 200, 34, Math.PI, 0); g.strokeStyle = "#ffffff"; g.lineWidth = 12; g.stroke();
    rr(g, w / 2 - 46, 196, 92, 74, 10, "#ffffff");
    text(g, "Approval required", w / 2, 430, 30, "#ff6b6b", "center", 700);
  }
  if (s.kind === "signing") {
    g.fillStyle = "#e8eef8"; g.fillRect(0, 0, w, h);
    text(g, "Waiting for approval on phone…", w / 2, 180, 30, "#1b2433", "center", 700);
    for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(w / 2 - 50 + i * 50, 260, 14, 0, Math.PI * 2); g.fillStyle = i === s.n % 3 ? "#2f6fd6" : "#b9c8e6"; g.fill(); }
    text(g, `Request #${s.n + 1} sent`, w / 2, 340, 24, "#5b6576", "center", 500);
  }
  if (s.kind === "chatdesk") {
    g.fillStyle = "#ece5dd"; g.fillRect(0, 0, w, h); g.fillStyle = "#075e54"; g.fillRect(0, 0, w, 70);
    text(g, "To: Contractor", 30, 35, 24, "#ffffff", "left", 700);
    const msg = "Hi, this is IT support. Those alerts will only stop once you accept one.";
    rr(g, 30, h - 110, w - 60, 70, 14, "#ffffff");
    const shown = msg.slice(0, s.chars);
    text(g, shown.length > 46 ? "…" + shown.slice(-46) : shown, 50, h - 75, 22, "#111b21", "left", 500);
  }
  if (s.kind === "staffchat") {
    g.fillStyle = "#1a1d21"; g.fillRect(0, 0, w, h); g.fillStyle = "#3f0e40"; g.fillRect(0, 0, 170, h);
    text(g, "# general", 20, 36, 22, "#ffffff", "left", 700);
    ["# it-help", "# random", "# design"].forEach((c, i) => text(g, c, 20, 80 + i * 36, 18, "#cdb9ce", "left", 500));
    const msgs: [string, string, string][] = [["Mira", "morning all, standup in 5", "#36c5f0"], ["David", "on my way", "#2eb67d"], ["unknown_user", "I announce I am a hacker.", "#e01e5a"]];
    msgs.slice(0, s.shown).forEach(([who, m, c], i) => {
      const y = 70 + i * 120; rr(g, 196, y, 40, 40, 8, c);
      text(g, who, 250, y + 12, 20, i === 2 ? "#ff6b8a" : "#ffffff", "left", 700);
      text(g, m, 250, y + 44, i === 2 ? 26 : 20, "#e8e8e8", "left", i === 2 ? 700 : 500);
    });
  }
  if (s.kind === "code") {
    for (let i = 0; i < 16; i++) {
      const r = Math.sin((i + 1) * 12.9898 + s.seed * 78.233) * 43758.5453, u = r - Math.floor(r);
      g.fillStyle = i % 5 === 0 ? "#7CFC9A" : "#4fa3ff"; g.fillRect(24 + (i % 3) * 18, 24 + i * 28, 140 + u * 520, 12);
    }
  }
  if (s.kind === "soc") {
    for (let i = 0; i < 6; i++) {
      const x = 20 + (i % 3) * 258, y = 20 + Math.floor(i / 3) * 236;
      rr(g, x, y, 244, 222, 10, "#111c33");
      const r = Math.sin((i + 1) * 3.1 + s.seed) * 0.5 + 0.5;
      g.beginPath(); g.moveTo(x + 14, y + 180);
      for (let k = 0; k <= 10; k++) g.lineTo(x + 14 + k * 21.6, y + 180 - (Math.sin(k * 1.3 + i + s.seed * 0.2) * 0.5 + 0.5) * 120 * r);
      g.strokeStyle = "#4fa3ff"; g.lineWidth = 4; g.stroke();
    }
    if (s.alert) { rr(g, 120, 160, 560, 180, 16, "#c81e1e"); text(g, "Unexpected login approval", w / 2, 230, 30, "#ffffff", "center", 700); text(g, "contractor@nimbus · new device", w / 2, 280, 22, "#ffe0e0", "center", 500); }
  }
  if (s.kind === "office") {
    g.fillStyle = "#eef2f8"; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 6; i++) rr(g, 40, 50 + i * 70, 300 + ((i * 97 + s.seed * 31) % 380), 34, 8, i === 0 ? "#2f6fd6" : "#c9d4e8");
  }
});

// ---------------- signage / small displays ----------------
export const calendarTex = () => screenTex("calendar", 400, 480, (g, w, h) => {
  g.fillStyle = "#f6f1e7"; g.fillRect(0, 0, w, h); g.fillStyle = "#c0392b"; g.fillRect(0, 0, w, 110);
  text(g, "SEPTEMBER", w / 2, 42, 40, "#ffffff", "center", 800); text(g, "2022", w / 2, 88, 34, "#ffffff", "center", 700);
  for (let d = 0; d < 30; d++) {
    const x = 34 + (d % 7) * 52, y = 150 + Math.floor(d / 7) * 64;
    if (d === 14) { g.beginPath(); g.arc(x + 12, y, 24, 0, Math.PI * 2); g.strokeStyle = "#c0392b"; g.lineWidth = 5; g.stroke(); }
    text(g, String(d + 1), x + 12, y, 24, "#333", "center", 600);
  }
});
export const towerLogoTex = () => screenTex("towerlogo", 1024, 256, (g, w, h) => {
  g.clearRect(0, 0, w, h); shield(g, 110, 120, 60, "#ffffff"); text(g, "NIMBUS", 210, 130, 150, "#ffffff", "left", 800);
});
export const microwaveTex = (on: boolean) => screenTex("micro" + on, 256, 96, (g, w, h) => {
  g.fillStyle = "#08130c"; g.fillRect(0, 0, w, h); if (on) text(g, "0:00", w / 2, h / 2 + 2, 64, "#5dff8a", "center", 700);
});
export const doorSignTex = () => screenTex("doorsign", 512, 256, (g, w, h) => {
  rr(g, 0, 0, w, h, 40, "#16a34a"); text(g, "Approve", w / 2, h / 2 + 6, 110, "#ffffff", "center", 800);
});

// ---------------- fx sprites (unlit, NOINK) ----------------
export const buzzTex = () => screenTex("buzz", 512, 512, (g, w, h) => {
  g.strokeStyle = "#1c1a2e"; g.lineWidth = 14; g.lineCap = "round";
  for (const s of [-1, 1]) for (let i = 0; i < 3; i++) {
    g.beginPath(); g.arc(w / 2, h / 2, 150 + i * 46, -0.45 + (s < 0 ? Math.PI : 0), 0.45 + (s < 0 ? Math.PI : 0)); g.stroke();
  }
});
export const knockTex = () => screenTex("knock", 512, 512, (g, w, h) => {
  g.strokeStyle = "#ffffff"; g.lineWidth = 16; g.lineCap = "round";
  for (let i = 0; i < 5; i++) { const a = -Math.PI / 2 + (i - 2) * 0.42; g.beginPath(); g.moveTo(w / 2 + Math.cos(a) * 110, h / 2 + Math.sin(a) * 110); g.lineTo(w / 2 + Math.cos(a) * 210, h / 2 + Math.sin(a) * 210); g.stroke(); }
});
export const blobTex = () => screenTex("blob", 256, 128, (g, w, h) => {
  g.fillStyle = "#ffffff"; g.fillRect(0, 0, w, h);
  const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
  r.addColorStop(0, "rgba(90,80,100,0.75)"); r.addColorStop(1, "rgba(255,255,255,0)");
  g.save(); g.scale(1, h / w); g.fillStyle = r; g.fillRect(0, 0, w, w); g.restore();
});
