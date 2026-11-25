// PhishGuard cast as flat hand-drawn stickmen, drawn on a canvas and shown as lit billboard cards.
// Style (Kill List "Cyber Awareness Video Automation" master prompt + model sheets): big imperfect PURE WHITE head,
// thick navy-black marker outline, round white eyes with black dot pupils, bold brows, NO nose, small mouth,
// a flat-colour outfit blob for the torso, thin black stick arms/legs, round black dot hands, no feet detail.
// Design space 600 x 1000 units, soles at y = 975 (same card contract as the engine's cast.ts).
export const INK = "#1c1a2e";
export const W = 600, H = 1000, SOLE = 975;

export type Who = "aiman" | "scammer" | "ravi" | "mira" | "david";
export type Face = "front" | "left" | "right";
export type Expr = "neutral" | "happy" | "surprised" | "shock" | "worried" | "angry" | "smirk" | "sly" | "tired"
  | "relieved" | "determined" | "sweet" | "annoyed";
type P = [number, number];
export type Arm = { hand: P; bend?: 1 | -1; finger?: "point" | "thumb" | "up" | null };
export type Pose = {
  face: Face; expr: Expr; blink?: boolean; look?: P;
  step?: number | null;      // walk phase 0..1 (two steps per cycle); null = standing
  sit?: boolean; lean?: number; bob?: number;
  armL?: Arm; armR?: Arm;    // L/R = screen left/right
  prop?: { kind: "phone" | "key" | "picks" | "fist"; side: "L" | "R"; glow?: string } | null;
  headset?: boolean;         // the scammer's fake IT headset
};

const rnd = (seed: number, k: number) => { const x = Math.sin(seed * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
const SEED: Record<Who, number> = { aiman: 3, scammer: 7, ravi: 11, mira: 5, david: 9 };

// ---------- pen helpers: slightly uneven marker strokes ----------
const stroke = (g: CanvasRenderingContext2D, w = 9, col = INK) => { g.lineWidth = w; g.strokeStyle = col; g.lineCap = "round"; g.lineJoin = "round"; g.stroke(); };
const fill = (g: CanvasRenderingContext2D, col: string) => { g.fillStyle = col; g.fill(); };
const line = (g: CanvasRenderingContext2D, pts: P[], w = 9, col = INK) => {
  g.beginPath(); g.moveTo(...pts[0]); for (const p of pts.slice(1)) g.lineTo(...p); stroke(g, w, col);
};
/** wobbly closed blob (hand-drawn circle/ellipse) */
const blob = (g: CanvasRenderingContext2D, cx: number, cy: number, rx: number, ry: number, seed: number, wob = 0.025, n = 48) => {
  g.beginPath();
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2;
    const k = 1 + wob * (Math.sin(a * 3 + seed) * 0.6 + Math.sin(a * 5 + seed * 2.3) * 0.4);
    const x = cx + Math.cos(a) * rx * k, y = cy + Math.sin(a) * ry * k;
    i ? g.lineTo(x, y) : g.moveTo(x, y);
  }
  g.closePath();
};
/** egg torso (narrower top) */
const egg = (g: CanvasRenderingContext2D, cx: number, top: number, bot: number, wTop: number, wBot: number, seed: number) => {
  const n = 48, cy = (top + bot) / 2, ry = (bot - top) / 2;
  g.beginPath();
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2, s = Math.sin(a);
    const rx = s < 0 ? wTop + (wBot - wTop) * (1 + s) * 0.35 : wBot;
    const k = 1 + 0.02 * Math.sin(a * 4 + seed);
    const x = cx + Math.cos(a) * rx * k, y = cy + s * ry * k;
    i ? g.lineTo(x, y) : g.moveTo(x, y);
  }
  g.closePath();
};
/** two-segment stick limb from a to c bending outward by `bend` */
const limb = (g: CanvasRenderingContext2D, a: P, c: P, len: number, bend: number, w = 8) => {
  const dx = c[0] - a[0], dy = c[1] - a[1], d = Math.hypot(dx, dy) || 1;
  const reach = Math.min(d, 2 * len * 0.999);
  const h = Math.sqrt(Math.max(0, len * len - (reach / 2) ** 2));
  const mx = a[0] + dx / 2, my = a[1] + dy / 2;
  const elbow: P = [mx - (dy / d) * h * bend, my + (dx / d) * h * bend];
  g.beginPath(); g.moveTo(...a); g.lineTo(...elbow); g.lineTo(...c); stroke(g, w);
};
const dot = (g: CanvasRenderingContext2D, p: P, r = 13) => { g.beginPath(); g.arc(p[0], p[1], r, 0, Math.PI * 2); fill(g, INK); };

// ---------- outfits ----------
type Look = { torso: string; collar?: string; badge?: "lanyard" | "shield" | null; suit?: boolean; hoodie?: boolean };
const LOOKS: Record<Who, Look> = {
  aiman: { torso: "#a3d69a", collar: "#ffffff", badge: "lanyard" },
  scammer: { torso: "#1f1f26", hoodie: true },
  ravi: { torso: "#283a78", collar: "#ffffff", badge: "shield" },
  mira: { torso: "#3e9f9c", badge: "lanyard" },
  david: { torso: "#6d6d73", suit: true },
};

// ---------- head + face ----------
const HEAD: P = [300, 250]; const HR = 150;
const DY = 52; // arm targets were authored for the old layout: shift them down with the torso
function face(g: CanvasRenderingContext2D, who: Who, p: Pose, cx: number, cy: number) {
  const side = p.face === "front" ? 0 : p.face === "left" ? -1 : 1;
  const ex = side === 0 ? 46 : 0, ox = side * 58; // eye spacing / side shift
  const eyeY = cy - 6, look = p.look ?? [0, 0];
  const eyes: P[] = side === 0 ? [[cx - ex, eyeY], [cx + ex, eyeY]] : [[cx + ox, eyeY]];
  const e = p.expr, scam = who === "scammer";
  const lid = e === "tired" || e === "smirk" || e === "sly" || scam && e !== "shock" && e !== "surprised" && e !== "angry";
  const happyEyes = e === "happy" || e === "sweet" || e === "relieved";
  const er = e === "shock" || e === "surprised" ? 27 : 23;
  for (const [x, y] of eyes) {
    if (p.blink || happyEyes) {
      g.beginPath();
      if (happyEyes && !p.blink) g.arc(x, y + 6, 16, Math.PI * 1.1, Math.PI * 1.9); else { g.moveTo(x - 16, y); g.lineTo(x + 16, y); }
      stroke(g, 8);
      continue;
    }
    g.beginPath(); g.arc(x, y, er, 0, Math.PI * 2); fill(g, "#ffffff"); stroke(g, 7);
    const pr = e === "shock" ? 6 : 8.5;
    g.beginPath(); g.arc(x + look[0] * 9 + side * 6, y + look[1] * 7 + (lid ? 6 : 0), pr, 0, Math.PI * 2); fill(g, INK);
    if (lid) { // heavy upper lid: a line across the top half, filled above
      g.beginPath(); g.arc(x, y, er, Math.PI, Math.PI * 2); g.closePath(); fill(g, "#ffffff");
      g.beginPath(); g.moveTo(x - er - 2, y + 1); g.lineTo(x + er + 2, y - 1); stroke(g, 8);
      g.beginPath(); g.arc(x, y, er, 0, Math.PI * 2); stroke(g, 7);
    }
  }
  // brows: angle carries the emotion
  const browY = eyeY - 40 - (e === "surprised" || e === "shock" ? 14 : 0);
  for (const [x] of eyes) {
    const s = side !== 0 ? -side : x < cx ? -1 : 1; // +1: brow's outer end on the right
    let inner = 0, outer = 0;
    if (e === "angry" || e === "determined") { inner = e === "angry" ? 14 : 8; outer = -6; }
    else if (e === "worried" || e === "tired") { inner = -12; outer = 6; }
    else if (e === "annoyed") { inner = 8; outer = -2; }
    else if (scam && (e === "smirk" || e === "sly" || e === "sweet")) { inner = x < cx ? 8 : -6; outer = x < cx ? -6 : -10; }
    const xi = x - 26 * s, xo = x + 26 * s;
    g.beginPath(); g.moveTo(xi, browY + inner); g.quadraticCurveTo(x, browY - 8 + (inner + outer) / 2, xo, browY + outer); stroke(g, 10);
  }
  // mouth (no nose, ever)
  const mx = cx + side * 42, my = cy + 62;
  g.beginPath();
  switch (e) {
    case "happy": case "sweet":
      g.moveTo(mx - 34, my - 6); g.quadraticCurveTo(mx, my + 42, mx + 34, my - 6); g.closePath();
      fill(g, "#ffffff"); stroke(g, 8);
      g.beginPath(); g.moveTo(mx - 30, my); g.lineTo(mx + 30, my); stroke(g, 5);
      break;
    case "surprised": g.ellipse(mx, my + 4, 12, 15, 0, 0, Math.PI * 2); fill(g, "#ffffff"); stroke(g, 7); break;
    case "shock": g.ellipse(mx, my + 6, 18, 24, 0, 0, Math.PI * 2); fill(g, INK); break;
    case "worried": g.moveTo(mx - 26, my + 6); g.bezierCurveTo(mx - 10, my - 8, mx + 8, my + 14, mx + 26, my); stroke(g, 8); break;
    case "angry": case "annoyed": g.moveTo(mx - 24, my + 10); g.quadraticCurveTo(mx, my - 8, mx + 24, my + 10); stroke(g, 8); break;
    case "tired": g.moveTo(mx - 18, my + 4); g.lineTo(mx + 18, my + 2); stroke(g, 8); break;
    case "smirk": case "sly":
      g.moveTo(mx - 34, my + 2); g.quadraticCurveTo(mx + 2, my + 22, mx + 36, my - 10); stroke(g, 8);
      if (e === "sly") { g.beginPath(); g.moveTo(mx - 20, my + 8); g.quadraticCurveTo(mx + 4, my + 18, mx + 28, my); stroke(g, 4); }
      break;
    case "relieved": case "determined": g.moveTo(mx - 26, my); g.quadraticCurveTo(mx, my + 20, mx + 26, my); stroke(g, 8); break;
    default: g.moveTo(mx - 20, my + 4); g.quadraticCurveTo(mx, my + 12, mx + 20, my + 4); stroke(g, 8);
  }
}

function hairBack(g: CanvasRenderingContext2D, who: Who, side: number, cx: number, cy: number, sd: number) {
  if (who === "scammer") { blob(g, cx - side * 12, cy + 18, HR * 1.28, HR * 1.3, sd, 0.03); fill(g, "#17171c"); stroke(g, 9); }
  if (who === "mira") { // bob: falls to the chin
    g.beginPath(); g.moveTo(cx - HR * 1.08, cy + 70); g.quadraticCurveTo(cx - HR * 1.15, cy - HR * 1.15, cx, cy - HR * 1.08);
    g.quadraticCurveTo(cx + HR * 1.15, cy - HR * 1.15, cx + HR * 1.08, cy + 70); g.lineTo(cx + HR * 0.7, cy + 78); g.lineTo(cx - HR * 0.7, cy + 78); g.closePath();
    fill(g, INK);
  }
}
function hairFront(g: CanvasRenderingContext2D, who: Who, side: number, cx: number, cy: number, sd: number, headset: boolean) {
  const top = cy - HR;
  g.save();
  // clip to the head so hair caps sit on it
  if (who === "aiman" || who === "ravi" || who === "david") {
    g.save(); blob(g, cx, cy, HR + 4, HR + 4, sd, 0.025); g.clip();
    g.beginPath();
    const capY = who === "david" ? cy - HR * 0.42 : cy - HR * 0.46;
    if (side === 0) {
      g.moveTo(cx - HR * 1.1, capY + 30); g.quadraticCurveTo(cx - HR * 0.4, capY - 20, cx, capY);
      g.quadraticCurveTo(cx + HR * 0.5, capY - 26, cx + HR * 1.1, capY + 30);
      if (who === "david") { g.lineTo(cx + HR * 1.1, capY + 40); g.lineTo(cx + HR * 0.2, capY - 6); }
    } else { // side: cap over the top, mass down the back half (the side away from the facing direction)
      const b = -side;
      g.moveTo(cx + side * HR * 1.2, capY + 18); g.quadraticCurveTo(cx + side * HR * 0.3, capY - 14, cx - side * HR * 0.05, capY + 6);
      g.quadraticCurveTo(cx + b * HR * 0.1, cy + HR * 0.1, cx + b * HR * 0.25, cy + HR * 0.45); g.lineTo(cx + b * HR * 1.3, cy + HR * 0.6);
      g.lineTo(cx + b * HR * 1.3, top - 40); g.lineTo(cx + side * HR * 1.3, top - 40); // back-top, then front-top: never self-crossing
    }
    if (side === 0) { g.lineTo(cx + HR * 1.3, top - 40); g.lineTo(cx - HR * 1.3, top - 40); }
    g.closePath(); fill(g, INK);
    g.restore();
    if (who === "ravi") for (let i = 0; i < 9; i++) { // curls along the hairline
      const a = Math.PI * (1.08 + (i / 8) * 0.84); blob(g, cx + Math.cos(a) * HR * 0.98, cy + Math.sin(a) * HR * 0.98, 22, 20, sd + i, 0.1, 16); fill(g, INK);
    }
    if (who === "aiman") for (let i = 0; i < 3; i++) { // messy tufts on top
      g.beginPath(); const x = cx - 26 + i * 26; g.moveTo(x - 14, top + 8); g.quadraticCurveTo(x + (i - 1) * 8, top - 28 - (i % 2) * 8, x + 14, top + 8); fill(g, INK);
    }
  }
  if (who === "mira") { // fringe with a side part
    g.save(); blob(g, cx, cy, HR + 3, HR + 3, sd, 0.025); g.clip();
    g.beginPath(); g.moveTo(cx - HR * 1.2, cy - 10); g.quadraticCurveTo(cx - HR * 0.6, cy - HR * 0.75, cx + HR * 0.1, cy - HR * 0.62);
    g.quadraticCurveTo(cx + HR * 0.7, cy - HR * 0.7, cx + HR * 1.2, cy - 10); g.lineTo(cx + HR * 1.3, top - 30); g.lineTo(cx - HR * 1.3, top - 30); g.closePath(); fill(g, INK);
    g.restore();
  }
  if (who === "scammer") { // hood rim around the face
    blob(g, cx, cy + 2, HR * 1.0, HR * 1.02, sd, 0.02); stroke(g, 14, "#2a2a33"); stroke(g, 6);
  }
  if (who === "ravi" || headset) { // headset band, ear cup, mic boom
    g.beginPath(); g.arc(cx, cy + 4, HR * 1.12, Math.PI * 1.05, Math.PI * 1.95); stroke(g, 12, "#1e2a52"); stroke(g, 4);
    const cupX = side === 0 ? cx - HR * 1.06 : cx - side * 6;
    blob(g, cupX, cy + 14, 24, 32, sd, 0.05, 20); fill(g, "#1e2a52"); stroke(g, 6);
    g.beginPath(); g.moveTo(cupX, cy + 40); g.quadraticCurveTo(cupX + (side >= 0 ? 30 : -30), cy + 96, cx + (side === 0 ? -10 : side * 40), cy + 82);
    stroke(g, 6); dot(g, [cx + (side === 0 ? -10 : side * 40), cy + 82], 9);
  }
  g.restore();
}

// ---------- body ----------
function torso(g: CanvasRenderingContext2D, who: Who, side: number, cx: number, top: number, bot: number, sd: number) {
  const L = LOOKS[who];
  if (L.suit) {
    g.beginPath(); const w = side === 0 ? 92 : 70;
    g.moveTo(cx - w * 0.82, top + 8); g.lineTo(cx + w * 0.82, top + 8); g.lineTo(cx + w, bot); g.lineTo(cx - w, bot); g.closePath();
  } else if (L.hoodie) egg(g, cx, top - 6, bot + 6, side === 0 ? 100 : 80, side === 0 ? 118 : 92, sd);
  else egg(g, cx, top, bot, side === 0 ? 82 : 66, side === 0 ? 108 : 84, sd);
  fill(g, L.torso); stroke(g, 9);
  const nx = cx + side * 26;
  if (L.collar) { // white collar points
    g.beginPath(); g.moveTo(nx - 30, top + 2); g.lineTo(nx - 4, top + 26); g.lineTo(nx - 2, top + 2); g.closePath(); fill(g, L.collar); stroke(g, 5);
    g.beginPath(); g.moveTo(nx + 30, top + 2); g.lineTo(nx + 4, top + 26); g.lineTo(nx + 2, top + 2); g.closePath(); fill(g, L.collar); stroke(g, 5);
  }
  if (L.suit) { // shirt V + red tie + lapel line
    g.beginPath(); g.moveTo(nx - 30, top + 8); g.lineTo(nx, top + 70); g.lineTo(nx + 30, top + 8); g.closePath(); fill(g, "#ffffff"); stroke(g, 5);
    g.beginPath(); g.moveTo(nx - 9, top + 14); g.lineTo(nx + 9, top + 14); g.lineTo(nx + 6, top + 74); g.lineTo(nx, top + 86); g.lineTo(nx - 6, top + 74); g.closePath(); fill(g, "#c42b30"); stroke(g, 4);
    line(g, [[nx, top + 86], [nx, bot - 6]], 4);
  }
  if (L.hoodie) { // kangaroo pocket + drawstrings
    g.beginPath(); g.moveTo(cx - 52, bot - 70); g.lineTo(cx + 52, bot - 70); g.lineTo(cx + 66, bot - 10); g.lineTo(cx - 66, bot - 10); g.closePath(); stroke(g, 5, "#3a3a46");
    line(g, [[nx - 14, top + 10], [nx - 16, top + 64]], 4, "#d8d8de"); line(g, [[nx + 14, top + 10], [nx + 16, top + 64]], 4, "#d8d8de");
  }
  if (L.badge === "lanyard") {
    const bx = cx + side * 30;
    line(g, [[nx - 26, top + 4], [bx, top + 92], [nx + 26, top + 4]], 4);
    g.beginPath(); g.rect(bx - 15, top + 90, 30, 40); fill(g, "#ffffff"); stroke(g, 4);
    g.beginPath(); g.rect(bx - 8, top + 98, 16, 12); fill(g, who === "aiman" ? "#6fbf6a" : "#2f7f7d");
  }
  if (L.badge === "shield") {
    const bx = cx + (side === 0 ? 40 : side * 36), by = top + 70;
    g.beginPath(); g.moveTo(bx - 15, by - 16); g.lineTo(bx + 15, by - 16); g.lineTo(bx + 15, by); g.quadraticCurveTo(bx + 12, by + 14, bx, by + 20); g.quadraticCurveTo(bx - 12, by + 14, bx - 15, by); g.closePath();
    fill(g, "#f2c230"); stroke(g, 4);
  }
}

/** default arms for a stance */
export const arms = {
  hang: (side: "L" | "R", sw = 0): Arm => ({ hand: [side === "L" ? 196 - sw * 20 : 404 + sw * 20, 640 + Math.abs(sw) * -10], bend: side === "L" ? 1 : -1 }),
  swing: (side: "L" | "R", ph: number, face: Face): Arm => {
    const s = Math.sin(ph * Math.PI * 2) * (side === "L" ? 1 : -1), fx = face === "left" ? -1 : face === "right" ? 1 : 0;
    return { hand: [300 + (side === "L" ? -40 : 40) * (fx === 0 ? 2.6 : 0.5) + s * 70 * (fx || 0.3), 640 - Math.abs(s) * 30], bend: fx >= 0 ? -1 : 1 };
  },
  phone: (side: "L" | "R"): Arm => ({ hand: [side === "L" ? 250 : 350, 470], bend: side === "L" ? 1 : -1 }),
  tap: (side: "L" | "R", t: number): Arm => ({ hand: [side === "L" ? 285 : 315, 455 - Math.max(0, Math.sin(t * Math.PI)) * 18], bend: side === "L" ? 1 : -1, finger: "point" }),
  type: (side: "L" | "R", t: number, seed = 0): Arm => ({ hand: [side === "L" ? 240 : 360, 548 - Math.abs(Math.sin(t * 9 + seed + (side === "L" ? 0 : 1.7))) * 16], bend: side === "L" ? 1 : -1 }),
  ears: (side: "L" | "R"): Arm => ({ hand: [side === "L" ? 150 : 450, 200], bend: side === "L" ? -1 : 1 }),
  point: (side: "L" | "R", up = 0): Arm => ({ hand: [side === "L" ? 90 : 510, 400 - up * 120], bend: side === "L" ? -1 : 1, finger: "point" }),
  knock: (side: "L" | "R", t: number): Arm => ({ hand: [side === "L" ? 140 - Math.max(0, Math.sin(t * Math.PI * 2)) * 30 : 460 + Math.max(0, Math.sin(t * Math.PI * 2)) * 30, 360], bend: side === "L" ? -1 : 1 }),
  thumb: (side: "L" | "R"): Arm => ({ hand: [side === "L" ? 170 : 430, 330], bend: side === "L" ? -1 : 1, finger: "thumb" }),
  wag: (side: "L" | "R", t: number): Arm => ({ hand: [(side === "L" ? 165 : 435) + Math.sin(t * 14) * 14, 300], bend: side === "L" ? -1 : 1, finger: "up" }),
  offer: (side: "L" | "R"): Arm => ({ hand: [side === "L" ? 110 : 490, 480], bend: side === "L" ? 1 : -1 }),
  pocket: (side: "L" | "R"): Arm => ({ hand: [side === "L" ? 262 : 338, 590], bend: side === "L" ? 1 : -1 }),
  slump: (side: "L" | "R"): Arm => ({ hand: [side === "L" ? 205 : 395, 700], bend: side === "L" ? 1 : -1 }),
  rest: (side: "L" | "R"): Arm => ({ hand: [side === "L" ? 220 : 380, 560], bend: side === "L" ? 1 : -1 }),
};

function hand(g: CanvasRenderingContext2D, a: Arm, who: Who) {
  const r = who === "scammer" ? 17 : 13;
  dot(g, a.hand, r);
  if (a.finger === "point" || a.finger === "up") {
    const d: P = a.finger === "up" ? [0, -1] : [a.hand[0] < 300 ? -0.4 : 0.4, -0.9];
    line(g, [a.hand, [a.hand[0] + d[0] * 30, a.hand[1] + d[1] * 30]], 8);
  }
  if (a.finger === "thumb") line(g, [a.hand, [a.hand[0], a.hand[1] - 32]], 9);
}

function prop(g: CanvasRenderingContext2D, pr: NonNullable<Pose["prop"]>, at: P) {
  const [x, y] = at;
  if (pr.kind === "phone") {
    g.save(); g.translate(x, y - 34); g.rotate(pr.side === "L" ? -0.12 : 0.12);
    g.beginPath(); g.roundRect(-24, -40, 48, 84, 9); fill(g, "#22242e"); stroke(g, 5);
    g.beginPath(); g.roundRect(-18, -33, 36, 68, 5); fill(g, pr.glow ?? "#bfe3ff");
    g.restore();
  } else if (pr.kind === "key") {
    g.save(); g.translate(x, y); g.rotate(pr.side === "L" ? -0.5 : 0.5);
    g.beginPath(); g.arc(0, -70, 34, 0, Math.PI * 2); g.arc(0, -70, 14, 0, Math.PI * 2, true); fill(g, "#f0c23a"); stroke(g, 6);
    g.beginPath(); g.rect(-9, -40, 18, 120); fill(g, "#f0c23a"); stroke(g, 6);
    g.beginPath(); g.rect(9, 50, 22, 12); g.rect(9, 68, 16, 10); fill(g, "#f0c23a"); stroke(g, 5);
    g.restore();
  } else if (pr.kind === "picks") {
    line(g, [[x, y], [x + 50, y - 50]], 5, "#9aa0ad"); line(g, [[x + 6, y + 4], [x + 60, y - 38]], 5, "#9aa0ad");
  }
}

/** draw one character pose into the 600x1000 design space */
export function drawStick(g: CanvasRenderingContext2D, who: Who, p: Pose) {
  const sd = SEED[who], side = p.face === "front" ? 0 : p.face === "left" ? -1 : 1;
  const walking = p.step != null && !p.sit;
  const bobY = (p.bob ?? 0) + (walking ? -Math.abs(Math.sin(p.step! * Math.PI * 2)) * 14 : 0);
  g.save();
  g.translate(0, bobY);
  if (p.lean) { g.translate(300, SOLE); g.rotate(p.lean); g.translate(-300, -SOLE); }
  const hipY = p.sit ? 700 : 680, cx = 300;
  // legs: thin black sticks, no feet
  if (p.sit) {
    if (side === 0) { limb(g, [cx - 30, hipY], [cx - 46, 940], 136, 1, 9); limb(g, [cx + 30, hipY], [cx + 46, 940], 136, -1, 9); }
    else { line(g, [[cx, hipY], [cx + side * 140, hipY + 10], [cx + side * 150, 960]], 9); line(g, [[cx - side * 12, hipY], [cx + side * 122, hipY + 16], [cx + side * 128, 960]], 9); }
  } else if (walking) {
    const ph = p.step! * Math.PI * 2, f = side === 0 ? 0.4 : side;
    for (const k of [0, 1]) {
      const s = Math.sin(ph + k * Math.PI);
      const foot: P = [cx + (k ? 16 : -16) * (side === 0 ? 1 : 0.4) + s * 70 * f, SOLE - Math.max(0, Math.cos(ph + k * Math.PI)) * 34];
      limb(g, [cx + (k ? 18 : -18) * (side === 0 ? 1 : 0.3), hipY], foot, 152, side >= 0 ? -1 : 1, 9);
    }
  } else {
    line(g, [[cx - 30, hipY], [cx - 36, SOLE]], 9); line(g, [[cx + 30, hipY], [cx + 36, SOLE]], 9);
  }
  // arms behind the torso (the far arm in side view)
  const L = p.armL ?? (walking ? arms.swing("L", p.step!, p.face) : arms.hang("L"));
  const R = p.armR ?? (walking ? arms.swing("R", p.step!, p.face) : arms.hang("R"));
  const shL: P = [cx - (side === 0 ? 84 : 24), 446], shR: P = [cx + (side === 0 ? 84 : 24), 446];
  const far = side === 0 ? null : side > 0 ? "L" : "R";
  const drawArm = (k: "L" | "R") => { const a0 = k === "L" ? L : R; const a = { ...a0, hand: [a0.hand[0], a0.hand[1] + DY] as P }; limb(g, k === "L" ? shL : shR, a.hand, 128, a.bend ?? 1, 8); hand(g, a, who); };
  if (far) drawArm(far);
  // head behind-parts (hood, bob), torso, head, face
  const hx = HEAD[0] + side * 10, hy = HEAD[1];
  hairBack(g, who, side, hx, hy, sd);
  torso(g, who, side, cx, 404, p.sit ? 712 : 694, sd);
  blob(g, hx, hy, HR, HR * 0.98, sd, 0.03); fill(g, "#ffffff"); stroke(g, 10);
  hairFront(g, who, side, hx, hy, sd, !!p.headset);
  face(g, who, p, hx, hy);
  // near arm(s) over the torso, then the held prop
  if (far) drawArm(far === "L" ? "R" : "L"); else { drawArm("L"); drawArm("R"); }
  if (p.prop) { const h = (p.prop.side === "L" ? L : R).hand; prop(g, p.prop, [h[0], h[1] + DY]); }
  g.restore();
}

/** blink schedule: ~4-frame blinks every 0.5-2.3 s, deterministic per character */
export const blinkAt = (f: number, seed: number) => {
  let t = 0, k = 0;
  while (t < f + 200) { const gap = 15 + Math.floor(rnd(seed, k++) * 54); t += gap; if (f >= t && f < t + 4) return true; }
  return false;
};
/** idle life: breathing bob + tiny sway */
export const idle = (f: number, seed: number) => ({ bob: Math.sin(f / 19 + seed) * 4, lean: Math.sin(f / 31 + seed * 2) * 0.012 });
