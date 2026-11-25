// "He Pressed Approve Just to Make It Stop": shot timeline for the MFA-fatigue awareness short (16:9, 30 fps).
// Every shot is <= 90 frames, the camera angle changes on every shot, every hold creeps (no static frame), and each
// visual beat lands 0-3 frames before its word (word timings: ~/shorts/project/work/phrases.json, Kokoro am_michael).
import type { Pose, Who } from "./stick";
import { arms } from "./stick";
import type { PhoneState, MonitorState } from "./screens";

export const FPS = 30;
export const TOTAL = 1890;
export type V3 = [number, number, number];
export type SetName = "city" | "den" | "home" | "office" | "door";
export type Light = "day" | "golden" | "night";

// ---------------- set layout (world.ts builds these, story places cameras/actors against them) ----------------
export const O: Record<SetName, V3> = { city: [0, 0, 0], den: [200, 0, 0], home: [400, 0, 0], office: [600, 0, 0], door: [800, 0, 0] };
const at = (s: SetName, x: number, y: number, z: number): V3 => [O[s][0] + x, O[s][1] + y, O[s][2] + z];
export const L = {
  city: { door: at("city", 0, 0, -14), lock: at("city", 0, 1.35, -13.72) },
  den: { mon: at("den", 0, 1.2, -2.45), seat: at("den", 0, 0, -1.25), calendar: at("den", -1.7, 1.75, -2.97) },
  home: { seat: at("home", 0, 0, -2.3), phone: at("home", 0.42, 0.775, -1.36), laptop: at("home", -0.25, 0.77, -1.6), micro: at("home", 3.55, 0.92, -1.2), stand: at("home", 2.55, 0, -0.95) },
  office: { mira: at("office", -1.5, 0, -2.2), david: at("office", 1.5, 0, -2.2), ravi: at("office", -5.5, 0, -3.15), soc: at("office", -5.5, 1.85, -6.85), chatMon: at("office", 4.0, 1.12, -3.0) },
  door: { door: at("door", 0, 0, -2.2) },
};

// ---------------- helpers ----------------
export const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
export const smooth = (x: number) => { const u = clamp01(x); return u * u * (3 - 2 * u); };
const glide = (u: number) => { const x = clamp01(u); return x * x * x * (x * (6 * x - 15) + 10); };
/** camera ease that never stops: half linear creep + half smootherstep, so no frame is static */
const creep = (u: number) => 0.45 * clamp01(u) + 0.55 * glide(u);
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const lerp3 = (a: V3, b: V3, k: number): V3 => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];

export type Cam = { pos: V3; look: V3; fov: number; roll: number };
type CamKey = { pos: V3; look: V3; fov?: number; roll?: number };
/** move from key A to key B over the shot with the creep ease */
const move = (A: CamKey, B: CamKey, ease = creep) => (u: number): Cam => {
  const k = ease(u);
  return { pos: lerp3(A.pos, B.pos, k), look: lerp3(A.look, B.look, k), fov: lerp(A.fov ?? 40, B.fov ?? A.fov ?? 40, k), roll: lerp(A.roll ?? 0, B.roll ?? 0, k) };
};
/** a push-in toward the look point by `amt` (fraction of the distance) plus optional roll (deg) */
const push = (pos: V3, look: V3, fov: number, amt = 0.12, roll0 = 0, roll1 = 0) =>
  move({ pos, look, fov, roll: roll0 * Math.PI / 180 }, { pos: lerp3(pos, look, amt), look, fov, roll: roll1 * Math.PI / 180 });

export type Actor = { who: Who; pos: V3; pose: Pose; scale?: number };
export type Shot = {
  id: number; a: number; b: number; set: SetName; light: Light;
  cam: (u: number, lf: number) => Cam;
  cast?: (lf: number, f: number) => Actor[];
  phone?: (lf: number) => PhoneState;          // home desk phone screen
  den?: (lf: number) => MonitorState;           // den centre monitor
  chatMon?: (lf: number) => MonitorState;       // office chat monitor
  soc?: (lf: number) => MonitorState;
  door?: (lf: number) => number;                // door open 0..1
  micro?: (lf: number) => boolean;              // microwave display on
  buzz?: (lf: number) => number;                // phone vibration 0..1 (shake + buzz lines)
  knock?: (lf: number) => number;               // knock lines 0..1
  dof?: number;                                  // lens blur cInf (px at 1080 short side)
};

// walking: position along a path, step phase from distance (0.8 m per step, 2 steps per cycle)
const walk = (from: V3, to: V3, lf: number, dur: number, t0 = 0) => {
  const k = clamp01((lf - t0) / dur), p = lerp3(from, to, k);
  const d = Math.hypot(to[0] - from[0], to[2] - from[2]) * k;
  return { p, step: (d / 1.6) % 1 };
};
const tapPulse = (lf: number, at: number, len = 8) => clamp01((lf - at) / len);
const typing = (lf: number) => ({ armL: arms.type("L", lf / FPS, 0), armR: arms.type("R", lf / FPS, 1) });

// ---------------- shots (frames from the word timings) ----------------
export const SHOTS: Shot[] = [
  // 1. Hook: low wide, crane up the tower; staff walking in
  { id: 1, a: 0, b: 66, set: "city", light: "day", dof: 0,
    cam: move({ pos: at("city", 2.4, 1.2, 11.5), look: at("city", 0, 3.2, -14), fov: 50 }, { pos: at("city", 2.1, 2.0, 10.2), look: at("city", 0, 11, -14), fov: 50 }),
    cast: (lf) => {
      const m = walk(at("city", -1.5, 0, 4), at("city", -0.6, 0, -6), lf, 160), d = walk(at("city", 1.6, 0, 6), at("city", 0.8, 0, -4), lf, 170);
      return [{ who: "mira", pos: m.p, pose: { face: "left", expr: "neutral", step: m.step } }, { who: "david", pos: d.p, pose: { face: "left", expr: "happy", step: d.step } }];
    } },
  // 2. Scammer strolls past the locked front door
  { id: 2, a: 66, b: 134, set: "city", light: "day", dof: 10,
    cam: push(at("city", 0.4, 1.55, -8.6), at("city", -0.2, 1.35, -13.2), 34, 0.1),
    cast: (lf) => { const w = walk(at("city", -3.2, 0, -12.3), at("city", 1.4, 0, -12.3), lf, 68); return [{ who: "scammer", pos: w.p, pose: { face: "right", expr: "smirk", step: w.step, armL: arms.pocket("L"), armR: arms.pocket("R") } }]; } },
  // 3. "He just kept asking." reaction close-up, push-in + roll
  { id: 3, a: 134, b: 188, set: "city", light: "day", dof: 14,
    cam: push(at("city", 1.9, 1.62, -10.3), at("city", 1.4, 1.62, -12.3), 30, 0.22, 0, 4),
    cast: (lf) => [{ who: "scammer", pos: at("city", 1.4, 0, -12.3), pose: { face: "front", expr: lf > 20 ? "sly" : "smirk", armL: arms.pocket("L"), armR: arms.pocket("R") } }] },
  // 4. September 2022: bird's eye over the den, slow rotate
  { id: 4, a: 188, b: 242, set: "den", light: "night", dof: 0,
    cam: (u) => { const a = lerp(-0.5, -0.15, creep(u)); return { pos: add(L.den.seat, [Math.sin(a) * 2.6, 4.6, 1.6 + Math.cos(a) * 1.2]), look: add(L.den.seat, [0, 0.6, -0.7]), fov: 46, roll: 0 }; },
    den: (lf) => ({ kind: "code", seed: Math.floor(lf / 6) }),
    cast: (lf) => [{ who: "scammer", pos: L.den.seat, pose: { face: "front", expr: "smirk", sit: true, ...typing(lf) } }] },
  // 5. password: over-the-shoulder, dots fill
  { id: 5, a: 242, b: 312, set: "den", light: "night", dof: 11,
    cam: move({ pos: add(L.den.seat, [1.55, 1.6, 1.5]), look: add(L.den.mon, [-0.15, -0.1, 0]), fov: 38 }, { pos: add(L.den.seat, [1.4, 1.55, 1.2]), look: add(L.den.mon, [-0.15, -0.1, 0]), fov: 38 }),
    den: (lf) => ({ kind: "login", fill: clamp01((lf - 4) / 40) }),
    cast: (lf) => [{ who: "scammer", pos: L.den.seat, pose: { face: "left", expr: "smirk", sit: true, ...typing(lf) } }] },
  // 6. bought online from stolen data: insert on the monitor
  { id: 6, a: 312, b: 382, set: "den", light: "night", dof: 0,
    cam: push(add(L.den.mon, [0.18, 0.02, 0.95]), L.den.mon, 34, 0.15),
    den: (lf) => ({ kind: "market", pick: clamp01((lf - 18) / 30) }) },
  // 7. only one thing stands in his way: low-angle two-shot (him + the screen)
  { id: 7, a: 382, b: 434, set: "den", light: "night", dof: 8,
    cam: push(add(L.den.seat, [1.45, 0.6, 1.5]), add(L.den.seat, [-0.2, 1.15, -0.6]), 38, 0.1, 0, -3),
    den: () => ({ kind: "phonelock" }),
    cast: (lf) => [{ who: "scammer", pos: L.den.seat, pose: { face: "right", expr: lf > 22 ? "annoyed" : "neutral", sit: true, armR: arms.point("R", 0.3), armL: arms.rest("L") } }] },
  // 8. the contractor's phone: wide reveal of the home office (crossfade in)
  { id: 8, a: 434, b: 520, set: "home", light: "day", dof: 0,
    cam: move({ pos: at("home", 1.1, 1.55, 2.2), look: at("home", 0.1, 0.95, -1.6), fov: 46 }, { pos: at("home", 0.8, 1.4, 1.0), look: at("home", 0.2, 0.9, -1.6), fov: 44 }),
    phone: () => ({ kind: "home" }),
    cast: (lf) => [{ who: "aiman", pos: L.home.seat, pose: { face: "front", expr: "neutral", sit: true, look: [0.4, 0.6], armL: arms.type("L", lf / FPS * 0.6, 0), armR: arms.type("R", lf / FPS * 0.6, 1) } }] },
  // 9. so he signs in. Buzz. (den MCU)
  { id: 9, a: 520, b: 559, set: "den", light: "night", dof: 12,
    cam: push(add(L.den.seat, [-0.75, 1.45, 0.9]), add(L.den.seat, [0, 1.2, 0]), 32, 0.12),
    den: (lf) => ({ kind: "signing", n: 0 }),
    cast: (lf) => [{ who: "scammer", pos: L.den.seat, pose: { face: "right", expr: "smirk", sit: true, armR: { hand: [420, 520 - (lf > 8 && lf < 14 ? -20 : 0)], bend: -1 }, armL: arms.rest("L") } }] },
  // 10. Approve this login? insert, top-down on the phone
  { id: 10, a: 559, b: 591, set: "home", light: "day", dof: 0,
    cam: push(add(L.home.phone, [0.0, 0.34, 0.12]), L.home.phone, 34, 0.14),
    phone: () => ({ kind: "prompt" }), buzz: (lf) => (lf < 14 ? 1 : 0) },
  // 11. the contractor taps deny (MCU)
  { id: 11, a: 591, b: 631, set: "home", light: "day", dof: 12,
    cam: push(at("home", 0.55, 1.35, -0.6), add(L.home.seat, [0, 1.25, 0]), 34, 0.1),
    phone: (lf) => ({ kind: "prompt", press: lf > 12 ? "deny" : null, t: tapPulse(lf, 12) }),
    cast: (lf) => [{ who: "aiman", pos: L.home.seat, pose: { face: "front", expr: "worried", sit: true, look: [0.5, 0.8], armL: arms.phone("L"), armR: arms.tap("R", clamp01((lf - 8) / 6)), prop: { kind: "phone", side: "L" } } }] },
  // 12. he signs in again. Buzz. (den low angle)
  { id: 12, a: 631, b: 675, set: "den", light: "night", dof: 10,
    cam: push(add(L.den.seat, [0.35, 0.55, 1.6]), add(L.den.seat, [0, 1.35, 0]), 36, 0.12, 0, 2),
    den: () => ({ kind: "signing", n: 1 }),
    cast: (lf) => [{ who: "scammer", pos: L.den.seat, pose: { face: "left", expr: "sly", sit: true, ...typing(lf) } }] },
  // 13. Deny. Again. And again. (over the shoulder, quick push)
  { id: 13, a: 675, b: 722, set: "home", light: "day", dof: 12,
    cam: push(at("home", -1.05, 1.5, -0.2), add(L.home.seat, [0.1, 1.15, 0]), 38, 0.16),
    phone: (lf) => ({ kind: "prompt", stack: 1 + Math.floor(lf / 11), press: "deny", t: (lf % 11) / 11 }), buzz: () => 1,
    cast: (lf) => [{ who: "aiman", pos: L.home.seat, pose: { face: "front", expr: "annoyed", sit: true, look: [0.5, 0.8], armL: arms.phone("L"), armR: arms.tap("R", (lf % 11) / 6), prop: { kind: "phone", side: "L" } } }] },
  // 14. the phone won't stop: bird's eye on the desk, phone buzzing across it
  { id: 14, a: 722, b: 780, set: "home", light: "day", dof: 0,
    cam: (u) => ({ pos: add(L.home.phone, [-0.05 + 0.1 * creep(u), 0.95 - 0.15 * creep(u), 0.02]), look: L.home.phone, fov: 40, roll: lerp(0, 0.06, creep(u)) }),
    phone: (lf) => ({ kind: "prompt", stack: 4 + Math.floor(lf / 12) }), buzz: () => 1 },
  // 15. like a microwave that keeps beeping: kitchen two-shot
  { id: 15, a: 780, b: 855, set: "home", light: "day", dof: 6,
    cam: move({ pos: at("home", 0.9, 1.45, 1.4), look: at("home", 3.0, 1.15, -1.05), fov: 40 }, { pos: at("home", 1.3, 1.4, 1.0), look: at("home", 3.0, 1.15, -1.05), fov: 38 }),
    micro: (lf) => Math.floor(lf / 8) % 2 === 0,
    cast: (lf) => [{ who: "aiman", pos: L.home.stand, pose: { face: lf < 26 ? "right" : "front", expr: lf < 26 ? "neutral" : "annoyed", armL: lf < 26 ? undefined : arms.ears("L"), armR: lf < 26 ? undefined : arms.ears("R") } }] },
  // 16. a message pops up on WhatsApp: insert
  { id: 16, a: 855, b: 907, set: "home", light: "day", dof: 0,
    cam: push(add(L.home.phone, [0.03, 0.36, 0.14]), L.home.phone, 34, 0.12, 0, 0),
    phone: (lf) => ({ kind: "chat", shown: 0, typing: lf > 8 }) },
  // 17. Hi, this is IT support. scammer in a fake headset, sweet smile
  { id: 17, a: 907, b: 956, set: "den", light: "night", dof: 13,
    cam: push(add(L.den.seat, [0.15, 1.55, 1.15]), add(L.den.seat, [0, 1.45, 0]), 30, 0.14, 0, -3),
    den: (lf) => ({ kind: "chatdesk", chars: Math.floor(lf * 1.6) }),
    cast: (lf) => [{ who: "scammer", pos: L.den.seat, pose: { face: "front", expr: "sweet", sit: true, headset: true, ...typing(lf) } }] },
  // 18. Those alerts will only stop once you accept one. (over the shoulder: Aiman reads)
  { id: 18, a: 956, b: 1042, set: "home", light: "day", dof: 12,
    cam: move({ pos: at("home", 0.75, 1.25, -1.2), look: add(L.home.seat, [-0.05, 1.2, 0]), fov: 36 }, { pos: at("home", 0.6, 1.3, -1.45), look: add(L.home.seat, [-0.05, 1.22, 0]), fov: 36 }),
    phone: (lf) => ({ kind: "chat", shown: lf > 6 ? 2 : 1 }),
    cast: (lf) => [{ who: "aiman", pos: L.home.seat, pose: { face: "front", expr: lf > 40 ? "surprised" : "neutral", sit: true, look: [0.4, 0.7], armL: arms.phone("L"), armR: arms.rest("R"), prop: { kind: "phone", side: "L", glow: "#e7f7e4" } } }] },
  // 19. It sounds helpful. CU relieved
  { id: 19, a: 1042, b: 1069, set: "home", light: "day", dof: 14,
    cam: push(at("home", -0.35, 1.5, -1.0), add(L.home.seat, [0, 1.45, 0]), 30, 0.14),
    cast: () => [{ who: "aiman", pos: L.home.seat, pose: { face: "front", expr: "relieved", sit: true, armL: arms.phone("L"), armR: arms.rest("R"), prop: { kind: "phone", side: "L", glow: "#e7f7e4" } } }] },
  // 20. It sounds official. insert on the chat header, roll
  { id: 20, a: 1069, b: 1103, set: "home", light: "day", dof: 0,
    cam: push(add(L.home.phone, [0.0, 0.22, -0.02]), add(L.home.phone, [0, 0, -0.06]), 30, 0.12, 0, 4),
    phone: () => ({ kind: "chat", shown: 2 }) },
  // 21. And honestly, the contractor just wants: golden, wide, he slumps
  { id: 21, a: 1103, b: 1160, set: "home", light: "golden", dof: 6,
    cam: push(at("home", -1.6, 1.3, 1.4), add(L.home.seat, [0, 0.95, 0]), 42, 0.12),
    phone: (lf) => ({ kind: "prompt", stack: 6 }), buzz: (lf) => (Math.floor(lf / 10) % 2 ? 0.6 : 0),
    cast: () => [{ who: "aiman", pos: L.home.seat, pose: { face: "front", expr: "tired", sit: true, armL: arms.slump("L"), armR: arms.slump("R"), lean: 0.05 } }] },
  // 22. some peace and quiet: low angle, eyes close
  { id: 22, a: 1160, b: 1210, set: "home", light: "golden", dof: 12,
    cam: push(at("home", 0.45, 0.95, -0.9), add(L.home.seat, [0, 1.4, 0]), 34, 0.1, 0, -2),
    cast: (lf) => [{ who: "aiman", pos: L.home.seat, pose: { face: "front", expr: "tired", blink: lf > 14, sit: true, armL: arms.slump("L"), armR: arms.slump("R"), lean: 0.04 } }] },
  // 23. He taps approve. ECU push-in on the phone
  { id: 23, a: 1210, b: 1264, set: "home", light: "golden", dof: 0,
    cam: push(add(L.home.phone, [0.0, 0.3, 0.1]), add(L.home.phone, [0.02, 0, 0.03]), 34, 0.35),
    phone: (lf) => (lf < 34 ? { kind: "prompt", press: lf > 16 ? "approve" : null, t: tapPulse(lf, 16, 14) } : { kind: "approved" }) },
  // 24. wandering through internal systems: environment move along the server corridor
  { id: 24, a: 1264, b: 1340, set: "office", light: "night", dof: 6,
    cam: move({ pos: at("office", 7.0, 1.5, 6.5), look: at("office", 7.0, 1.2, 0), fov: 44 }, { pos: at("office", 7.0, 1.6, 4.2), look: at("office", 7.0, 1.2, -3), fov: 44 }),
    cast: (lf) => { const w = walk(at("office", 7.0, 0, 3.6), at("office", 7.0, 0, -0.8), lf, 76); return [{ who: "scammer", pos: w.p, pose: { face: Math.floor(lf / 30) % 2 ? "left" : "right", expr: "smirk", step: w.step, armL: arms.pocket("L"), armR: arms.pocket("R") } }]; } },
  // 25. and even announces himself: insert on the staff chat monitor
  { id: 25, a: 1340, b: 1395, set: "office", light: "night", dof: 0,
    cam: push(add(L.office.chatMon, [-0.15, 0.04, 1.0]), L.office.chatMon, 34, 0.14),
    chatMon: (lf) => ({ kind: "staffchat", shown: lf > 10 ? 3 : 2 }) },
  // 26. in the staff chat: day office, Mira + David shocked
  { id: 26, a: 1395, b: 1438, set: "office", light: "day", dof: 4,
    cam: push(at("office", 0.2, 2.25, 1.6), at("office", 0, 1.25, -2.2), 42, 0.1),
    cast: (lf) => [
      { who: "mira", pos: L.office.mira, pose: { face: "front", expr: lf > 6 ? "shock" : "neutral", sit: true, armL: arms.rest("L"), armR: arms.rest("R") } },
      { who: "david", pos: L.office.david, pose: { face: "front", expr: lf > 9 ? "surprised" : "neutral", sit: true, armL: arms.rest("L"), armR: lf > 9 ? arms.ears("R") : arms.rest("R") } }] },
  // 27. You see, that prompt isn't a nuisance. SOC, Ravi turns to camera (crossfade in)
  { id: 27, a: 1438, b: 1489, set: "office", light: "night", dof: 12,
    cam: push(add(L.office.ravi, [0.5, 1.5, 2.2]), add(L.office.ravi, [0, 1.35, 0]), 34, 0.16),
    soc: (lf) => ({ kind: "soc", alert: false, seed: lf / 10 }),
    cast: (lf) => [{ who: "ravi", pos: L.office.ravi, pose: { face: lf < 10 ? "left" : "front", expr: "determined" } }] },
  // 28. It's a door, and approve hands over the key: two-shot at the Approve door
  { id: 28, a: 1489, b: 1555, set: "door", light: "night", dof: 6,
    cam: move({ pos: at("door", 0.2, 1.4, 3.4), look: at("door", 0, 1.2, -1.2), fov: 40 }, { pos: at("door", 0.0, 1.35, 2.7), look: at("door", 0, 1.2, -1.2), fov: 40 }),
    door: () => 0,
    cast: (lf) => {
      const give = clamp01((lf - 26) / 16);
      return [
        { who: "aiman", pos: at("door", -0.95, 0, -1.0), pose: { face: "right", expr: "tired", armR: give < 1 ? arms.offer("R") : arms.hang("R"), prop: give < 1 ? { kind: "key", side: "R" } : null } },
        { who: "scammer", pos: at("door", 0.95, 0, -1.0), pose: { face: "left", expr: "sly", armL: give > 0.5 ? arms.offer("L") : arms.pocket("L"), armR: arms.pocket("R"), prop: give >= 1 ? { kind: "key", side: "L" } : null } }];
    } },
  // 29. Real IT will never ask you to accept a login you didn't start: SOC low-angle wide, Ravi wags a finger
  { id: 29, a: 1555, b: 1638, set: "office", light: "night", dof: 4,
    cam: push(add(L.office.ravi, [-1.1, 0.7, 2.6]), add(L.office.ravi, [0.2, 1.65, -0.8]), 44, 0.1, 0, 2),
    soc: (lf) => ({ kind: "soc", alert: true, seed: lf / 10 }),
    cast: (lf) => [{ who: "ravi", pos: L.office.ravi, pose: { face: "front", expr: "determined", armR: lf > 30 ? arms.wag("R", lf / FPS) : arms.hang("R") } }] },
  // 30. If one shows up, deny it: CU phone + hand
  { id: 30, a: 1638, b: 1690, set: "home", light: "day", dof: 0,
    cam: push(add(L.home.phone, [-0.04, 0.33, 0.15]), L.home.phone, 34, 0.12),
    phone: (lf) => ({ kind: "prompt", press: lf > 20 ? "deny" : null, t: tapPulse(lf, 20) }), buzz: (lf) => (lf < 16 ? 0.8 : 0) },
  // 31. and report it straight away: two-shot, Aiman calls Ravi, thumbs up
  { id: 31, a: 1690, b: 1738, set: "office", light: "day", dof: 6,
    cam: push(add(L.office.ravi, [1.4, 1.45, 3.0]), add(L.office.ravi, [0.9, 1.2, 0]), 38, 0.1),
    soc: (lf) => ({ kind: "soc", alert: false, seed: lf / 10 }),
    cast: (lf) => [
      { who: "aiman", pos: add(L.office.ravi, [1.8, 0, 0.3]), pose: { face: "left", expr: "determined", armL: arms.phone("L"), prop: { kind: "phone", side: "L" } } },
      { who: "ravi", pos: L.office.ravi, pose: { face: "right", expr: lf > 16 ? "happy" : "neutral", armR: lf > 16 ? arms.thumb("R") : arms.hang("R") } }] },
  // 32. The hacker never picked the lock: over the shoulder at the closed door, unused picks
  { id: 32, a: 1738, b: 1783, set: "door", light: "night", dof: 10,
    cam: push(at("door", 2.3, 1.7, 1.7), at("door", 0, 1.25, -2.2), 36, 0.12),
    door: () => 0,
    cast: (lf) => [{ who: "scammer", pos: at("door", 0.75, 0, -1.2), pose: { face: "left", expr: "annoyed", armL: { hand: [190 + Math.sin(lf / 4) * 10, 440], bend: 1 }, prop: { kind: "picks", side: "L" } } }] },
  // 33. Someone just got tired of the knocking: low angle, knock knock
  { id: 33, a: 1783, b: 1830, set: "door", light: "night", dof: 6,
    cam: push(at("door", -1.2, 0.6, 1.2), at("door", 0.2, 1.6, -2.1), 40, 0.1, 0, -2),
    door: () => 0, knock: (lf) => (lf % 16) < 6 ? 1 : 0,
    cast: (lf) => [{ who: "scammer", pos: at("door", 0.5, 0, -1.55), pose: { face: "left", expr: "smirk", armL: arms.knock("L", (lf % 16) / 16) } }] },
  // 34. and opened the door. push-in + roll, music stops
  { id: 34, a: 1830, b: TOTAL, set: "door", light: "night", dof: 8,
    cam: push(at("door", 0.6, 1.45, 2.4), at("door", -0.1, 1.35, -2.4), 38, 0.25, 0, 4),
    door: (lf) => smooth((lf - 4) / 22),
    cast: (lf) => [
      { who: "scammer", pos: at("door", 0.75, 0, -1.4), pose: { face: "left", expr: lf > 20 ? "sly" : "surprised" } },
      { who: "aiman", pos: at("door", -0.15, 0, -2.75), pose: { face: "front", expr: "tired", armL: arms.hang("L"), armR: arms.hang("R") } }] },
];

/** crossfades at big place changes; a white flash after the hook (time jump to September 2022) */
export const XFADE: Record<number, number> = { 8: 8, 27: 8 };
export const FLASH_AT = 188;
export const shotAt = (f: number) => SHOTS.find((s) => f >= s.a && f < s.b) ?? SHOTS[SHOTS.length - 1];
export const layersAt = (f: number): { id: number; alpha: number }[] => {
  for (const s of SHOTS) {
    const x = XFADE[s.id];
    if (x && f >= s.a - x / 2 && f < s.a + x / 2) return [{ id: s.id - 1, alpha: 1 }, { id: s.id, alpha: (f - (s.a - x / 2) + 1) / (x + 1) }];
  }
  return [{ id: shotAt(f).id, alpha: 1 }];
};
