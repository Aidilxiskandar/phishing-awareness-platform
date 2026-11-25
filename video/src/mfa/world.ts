// The five sets of the MFA short (city, den, home, office, door) built from three.js primitives with painted canvas
// textures, all shaded with the engine's stylised two-tone light (shade.ts) and inked by its outline pass. Characters
// are lit yaw-billboard cards (cardShade) drawn every frame by stick.ts; screens are canvas textures from screens.ts.
// Rooms have no ceilings and their walls cast no shadows, so the camera-relative "sun" still models the furniture.
import * as THREE from "three";
import { twoTone, TONE, CHAR, untone } from "./engine/shade";
import { cardShade, blobMaterial, CARD_K } from "./engine/cardshade";
import { LIGHTS, LOOK } from "./engine/lights";
import { NOINK } from "./engine/ink";
import { ctex, rep, rng, planksHD, stoneHD, brick, facadeHD, jit } from "./engine/paint";
import { drawStick, blinkAt, idle, W as CW, H as CH, Who } from "./stick";
import { phoneTex, monitorTex, calendarTex, towerLogoTex, microwaveTex, doorSignTex, buzzTex, knockTex, blobTex } from "./screens";
import { SHOTS, O, L, V3, SetName, Shot, Cam, FPS } from "./story";

const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const SU = 0.00185; // metres per design unit: soles-to-canvas-top 975 units = 1.80 m

// ---------------- materials ----------------
const mats = new Map<string, THREE.Material>();
const lam = (key: string, p: THREE.MeshLambertMaterialParameters) => {
  let m = mats.get(key);
  if (!m) { m = twoTone(new THREE.MeshLambertMaterial(p)); mats.set(key, m); }
  return m;
};
const col = (hex: string) => lam("c" + hex, { color: hex });
const basic = (key: string, p: THREE.MeshBasicMaterialParameters) => {
  let m = mats.get(key);
  if (!m) { m = new THREE.MeshBasicMaterial(p); mats.set(key, m); }
  return m;
};

// painted textures specific to these sets
const plaster = (key: string, base: string) => ctex("plaster" + key, 512, 512, (g, r) => {
  g.fillStyle = base; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 260; i++) { g.fillStyle = jit(r, base, 0.05, 3, 0.1); g.globalAlpha = 0.35; g.beginPath(); g.arc(r() * 512, r() * 512, 10 + r() * 40, 0, Math.PI * 2); g.fill(); }
  g.globalAlpha = 1;
});
const carpet = (key: string, base: string) => ctex("carpet" + key, 512, 512, (g, r) => {
  g.fillStyle = base; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 4000; i++) { g.fillStyle = jit(r, base, 0.12, 4, 0.2); g.fillRect(r() * 512, r() * 512, 2, 2); }
});
const glass = () => ctex("glassTower", 1024, 2048, (g, r) => {
  const gr = g.createLinearGradient(0, 0, 0, 2048); gr.addColorStop(0, "#9cc8ef"); gr.addColorStop(1, "#4f86c4");
  g.fillStyle = gr; g.fillRect(0, 0, 1024, 2048);
  for (let y = 0; y < 2048; y += 64) for (let x = 0; x < 1024; x += 128) {
    g.fillStyle = r() < 0.15 ? "rgba(255,240,200,0.45)" : `rgba(255,255,255,${0.08 + r() * 0.12})`; g.fillRect(x + 6, y + 6, 116, 52);
  }
  g.strokeStyle = "#dfe8f2"; g.lineWidth = 6;
  for (let y = 0; y <= 2048; y += 64) { g.beginPath(); g.moveTo(0, y); g.lineTo(1024, y); g.stroke(); }
  for (let x = 0; x <= 1024; x += 128) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, 2048); g.stroke(); }
});
const racks = (on: number) => ctex("rack" + on, 256, 512, (g, r) => {
  g.fillStyle = "#2b2f3a"; g.fillRect(0, 0, 256, 512);
  for (let y = 12; y < 500; y += 34) {
    g.fillStyle = "#3a404e"; g.fillRect(12, y, 232, 26);
    for (let i = 0; i < 6; i++) { const lit = r() < 0.5 !== (on === 1 && i % 2 === 0); g.fillStyle = lit ? (i % 3 ? "#4cff7a" : "#57b8ff") : "#203028"; g.fillRect(170 + i * 12, y + 9, 7, 7); }
  }
});
const windowView = () => ctex("windowView", 1024, 640, (g, r) => {
  const gr = g.createLinearGradient(0, 0, 0, 640); gr.addColorStop(0, "#5f98dc"); gr.addColorStop(0.7, "#bcd6f0"); g.fillStyle = gr; g.fillRect(0, 0, 1024, 640);
  for (let i = 0; i < 9; i++) { g.fillStyle = jit(r, "#5d9b5a", 0.15); const x = i * 120 + r() * 40, s = 80 + r() * 60; g.beginPath(); g.arc(x, 560 - s * 0.4, s, 0, Math.PI * 2); g.fill(); }
  g.fillStyle = "#8fc27c"; g.fillRect(0, 560, 1024, 80);
});

// ---------------- geometry helpers ----------------
const box = (parent: THREE.Object3D, min: V3, max: V3, m: THREE.Material, cast = true, receive = true) => {
  const g = new THREE.BoxGeometry(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
  const mesh = new THREE.Mesh(g, m);
  mesh.position.set((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2);
  mesh.castShadow = cast; mesh.receiveShadow = receive;
  parent.add(mesh);
  return mesh;
};
const plane = (parent: THREE.Object3D, w: number, h: number, m: THREE.Material, pos: V3, rotY = 0, rotX = 0, layer?: number) => {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), m);
  mesh.position.set(...pos); mesh.rotation.set(rotX, rotY, 0, "YXZ"); mesh.receiveShadow = true;
  if (layer != null) mesh.layers.set(layer);
  parent.add(mesh);
  return mesh;
};
const tree = (parent: THREE.Object3D, x: number, z: number, s = 1, y = 0) => {
  box(parent, [x - 0.12 * s, y, z - 0.12 * s], [x + 0.12 * s, y + 1.8 * s, z + 0.12 * s], col("#7a5236"));
  const c = new THREE.Mesh(new THREE.IcosahedronGeometry(1.25 * s, 1), col("#5f9e4f")); c.position.set(x, y + 2.6 * s, z); c.castShadow = true; c.receiveShadow = true; parent.add(c);
};
const plant = (parent: THREE.Object3D, x: number, z: number, y = 0) => {
  box(parent, [x - 0.18, y, z - 0.18], [x + 0.18, y + 0.42, z + 0.18], col("#c96f4a"));
  const c = new THREE.Mesh(new THREE.IcosahedronGeometry(0.34, 1), col("#4f9a52")); c.position.set(x, y + 0.75, z); c.castShadow = true; parent.add(c);
};
/** monitor on a stand; returns the screen mesh (its material map is swapped per frame) */
const monitor = (parent: THREE.Object3D, c: V3, w: number, yaw = 0) => {
  const g = new THREE.Group(); g.position.set(...c); g.rotation.y = yaw; parent.add(g);
  const h = w * 0.625;
  box(g, [-w / 2 - 0.025, -h / 2 - 0.025, -0.05], [w / 2 + 0.025, h / 2 + 0.025, -0.01], col("#24262e"));
  box(g, [-0.03, -h / 2 - 0.3, -0.07], [0.03, -h / 2, -0.03], col("#24262e"));
  box(g, [-0.16, -h / 2 - 0.32, -0.15], [0.16, -h / 2 - 0.3, 0.05], col("#24262e"));
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: monitorTex({ kind: "off" }) }));
  screen.position.z = -0.005; g.add(screen);
  return screen;
};
const desk = (parent: THREE.Object3D, min: V3, max: V3, top = "#e9e2d4") => {
  box(parent, [min[0], max[1] - 0.04, min[2]], [max[0], max[1], max[2]], col(top));
  for (const x of [min[0] + 0.05, max[0] - 0.09]) for (const z of [min[2] + 0.05, max[2] - 0.09]) box(parent, [x, 0, z], [x + 0.04, max[1] - 0.04, z + 0.04], col("#6c6f78"));
};
const chair = (parent: THREE.Object3D, x: number, z: number, facing = 1, back = true) => {
  box(parent, [x - 0.26, 0.42, z - 0.26], [x + 0.26, 0.5, z + 0.26], col("#2f3542"));
  if (back) box(parent, [x - 0.26, 0.5, z - 0.3 * facing - 0.04], [x + 0.26, 1.15, z - 0.3 * facing + 0.04], col("#2f3542"));
  box(parent, [x - 0.03, 0, z - 0.03], [x + 0.03, 0.42, z + 0.03], col("#6c6f78"));
};

// ---------------- characters ----------------
class Card {
  mesh: THREE.Mesh; blob: THREE.Mesh; cv: HTMLCanvasElement; tex: THREE.CanvasTexture; mat: THREE.MeshLambertMaterial; dmat: THREE.MeshDepthMaterial;
  static K = 1.3;
  constructor(parent: THREE.Object3D) {
    this.cv = document.createElement("canvas"); this.cv.width = CW * Card.K; this.cv.height = CH * Card.K;
    this.tex = new THREE.CanvasTexture(this.cv); this.tex.colorSpace = THREE.SRGBColorSpace; this.tex.anisotropy = 8;
    this.mat = cardShade(new THREE.MeshLambertMaterial({ map: this.tex, alphaTest: 0.5, side: THREE.DoubleSide }));
    this.dmat = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, map: this.tex, alphaTest: 0.5, side: THREE.DoubleSide });
    const geo = new THREE.PlaneGeometry(CW * SU, CH * SU); geo.translate(0, (975 - 500) * SU, 0);
    this.mesh = new THREE.Mesh(geo, this.mat); this.mesh.customDepthMaterial = this.dmat;
    this.mesh.onBeforeRender = (r) => { const rt = r.getRenderTarget(); CARD_K.uPx.value = (rt ? rt.height : r.domElement.height) / 1080; };
    this.mesh.receiveShadow = true; this.mesh.renderOrder = 1; this.mesh.layers.set(NOINK); this.mesh.visible = false;
    const bg = new THREE.PlaneGeometry(1, 1); bg.rotateX(-Math.PI / 2);
    this.blob = new THREE.Mesh(bg, blobMaterial(blobTex())); this.blob.layers.set(NOINK); this.blob.renderOrder = 0.5; this.blob.visible = false;
    parent.add(this.mesh, this.blob);
  }
}

// ---------------- the world ----------------
export class World {
  root = new THREE.Group();
  private sets = {} as Record<SetName, THREE.Group>;
  private sun = new THREE.DirectionalLight("#ffffff", 2.5);
  private hemi = new THREE.HemisphereLight("#cfe6ff", "#6c5c8c", 0.5);
  private fog = new THREE.Fog("#b8d0ec", 25, 300);
  private sky: THREE.Mesh; private skyMat: THREE.ShaderMaterial;
  private cards: Card[] = [];
  private screens: { phone: THREE.Mesh; phoneG: THREE.Group; den: THREE.Mesh; denSide: THREE.Mesh[]; chat: THREE.Mesh; soc: THREE.Mesh; office: THREE.Mesh[]; micro: THREE.Mesh; laptop: THREE.Mesh };
  private door!: THREE.Group;
  private rackMeshes: THREE.Mesh[] = [];
  private buzz: THREE.Mesh; private knock: THREE.Mesh;
  private sunCache = new Map<number, THREE.Vector3>();

  constructor() {
    const R = this.root;
    // sky dome (5 stops by elevation, tone-map-inverted), no ink
    this.skyMat = new THREE.ShaderMaterial({
      uniforms: { c0: { value: new THREE.Color() }, c1: { value: new THREE.Color() }, c2: { value: new THREE.Color() }, c3: { value: new THREE.Color() }, c4: { value: new THREE.Color() }, e: { value: new THREE.Vector4() } },
      vertexShader: "varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      fragmentShader: `uniform vec3 c0, c1, c2, c3, c4; uniform vec4 e; varying vec3 vP;
        void main(){ float el = asin(clamp(normalize(vP).y, -1.0, 1.0));
          vec3 c = mix(c0, c1, smoothstep(0.0, e.x, el)); c = mix(c, c2, smoothstep(e.x, e.y, el));
          c = mix(c, c3, smoothstep(e.y, e.z, el)); c = mix(c, c4, smoothstep(e.z, e.w, el)); gl_FragColor = vec4(c, 1.0); }`,
      side: THREE.BackSide, depthWrite: false, fog: false,
    });
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(900, 48, 24), this.skyMat);
    this.sky.renderOrder = -1; this.sky.frustumCulled = false; this.sky.layers.set(NOINK); R.add(this.sky);
    this.sun.castShadow = true; this.sun.shadow.mapSize.set(4096, 4096);
    R.add(this.sun, this.sun.target, this.hemi);
    for (const s of Object.keys(O) as SetName[]) { const g = new THREE.Group(); g.position.set(...O[s]); this.sets[s] = g; R.add(g); }
    const sc: Partial<World["screens"]> = {};

    // ===== CITY: glass tower + front door, plaza, road, neighbours, trees =====
    {
      const g = this.sets.city;
      box(g, [-60, -0.1, -60], [60, 0, 40], lam("pave", { map: rep(stoneHD("paveHD", ["#d8d2c6", "#cfc8bb", "#e0dacf", "#c8c0b2"], "#a8a094"), 30, 25) }), false, true);
      box(g, [-60, 0, 10], [60, 0.02, 18], col("#4a4d57"), false, true);
      for (let x = -56; x < 60; x += 6) box(g, [x, 0.02, 13.9], [x + 3, 0.03, 14.1], col("#f2f2ea"), false, true);
      box(g, [-8, 0, -30], [8, 44, -14], lam("glass", { map: rep(glass(), 1, 2) }));
      box(g, [-8.4, 0, -14.4], [8.4, 3.4, -13.9], col("#e9edf2"));                         // podium band
      const logo = plane(g, 7, 1.75, basic("logo", { map: towerLogoTex(), transparent: true, depthWrite: false }), [0, 30, -13.88], 0, 0, NOINK);
      void logo;
      box(g, [-1.25, 0, -14.0], [1.25, 2.85, -13.84], col("#2e3a4c"));                       // doors (closed)
      box(g, [-0.03, 0.2, -13.85], [0.03, 2.7, -13.8], col("#9fb3c8"));
      // padlock + chain across the handles
      box(g, [-0.32, 1.12, -13.8], [0.32, 1.5, -13.62], col("#c9a227"));
      const sh = new THREE.Mesh(new THREE.TorusGeometry(0.22, 0.05, 10, 24, Math.PI), col("#9aa0ad")); sh.position.set(0, 1.5, -13.71); g.add(sh);
      box(g, [-0.9, 1.3, -13.8], [0.9, 1.36, -13.74], col("#9aa0ad"));
      for (const [x0, x1, h, wall] of [[-36, -12, 18, "#e8d6b8"], [12, 30, 24, "#d9c7e4"], [-30, -20, 9, "#c9dfc6"], [32, 46, 14, "#f0d3b8"]] as [number, number, number, string][]) {
        const m = lam("fac" + wall, { map: facadeHD("fac" + wall, x1 - x0, h, { wall, shutter: "#5a6f8a" }) });
        box(g, [x0, 0, -26], [x1, h, -16], m);
      }
      for (const x of [-6, -3.2, 3.2, 6]) tree(g, x * 1.6, 3 + Math.abs(x) * 0.2, 0.75);
      for (const x of [-4.5, 4.5]) { box(g, [x - 0.06, 0, 4], [x + 0.06, 4, 4.12], col("#3c404a")); box(g, [x - 0.25, 3.9, 3.9], [x + 0.25, 4.05, 4.3], col("#3c404a")); }
    }

    // ===== DEN: dark room, desk with three monitors, calendar =====
    {
      const g = this.sets.den;
      box(g, [-3, -0.05, -3], [3, 0, 3], lam("denFloor", { map: rep(carpet("den", "#3a3f55"), 4, 4) }), false, true);
      box(g, [-3, 0, -3.1], [3, 3, -3], lam("denWall", { map: rep(plaster("den", "#4b5170"), 3, 1.5) }), false, true);
      box(g, [-3.1, 0, -3], [-3, 3, 3], lam("denWall", {}), false, true);
      box(g, [3, 0, -3], [3.1, 3, 3], lam("denWall", {}), false, true);
      desk(g, [-1.15, 0, -2.75], [1.15, 0.76, -1.85], "#3d3f4a");
      chair(g, 0, -1.1, -1, false); // stool: a backrest would sit between him and every front camera
      sc.den = monitor(g, [0, 1.2, -2.45], 0.92);
      sc.denSide = [monitor(g, [-0.98, 1.16, -2.32], 0.7, 0.5), monitor(g, [0.98, 1.16, -2.32], 0.7, -0.5)];
      box(g, [-0.45, 0.76, -2.05], [0.45, 0.79, -1.88], col("#1b1c22"));                    // keyboard
      plane(g, 0.42, 0.5, basic("cal", { map: calendarTex() }), [-1.7, 1.75, -2.98]);
      box(g, [1.9, 0, -2.9], [2.8, 1.9, -2.3], col("#2b2e3a"));                             // shelf
      for (let i = 0; i < 4; i++) box(g, [2.0 + i * 0.18, 1.2, -2.8], [2.14 + i * 0.18, 1.55, -2.45], col(["#a3485a", "#4a78a3", "#c99a3c", "#5a9a6a"][i]));
      box(g, [-2.6, 0, -0.4], [-1.9, 0.5, 0.6], col("#2d3142"));                            // crates
    }

    // ===== HOME: home office (desk facing camera, window behind) + kitchen corner =====
    {
      const g = this.sets.home;
      box(g, [-4.2, -0.05, -3.6], [4.2, 0, 3.2], lam("homeFloor", { map: rep(planksHD(), 3, 3) }), false, true);
      const wallM = lam("homeWall", { map: rep(plaster("home", "#efe3cf"), 3, 1.2) });
      // back wall with a window opening (x -1.2..1.2, y 1.0..2.4)
      box(g, [-4.2, 0, -3.6], [-1.2, 3, -3.5], wallM, false, true); box(g, [1.2, 0, -3.6], [4.2, 3, -3.5], wallM, false, true);
      box(g, [-1.2, 0, -3.6], [1.2, 1.0, -3.5], wallM, false, true); box(g, [-1.2, 2.4, -3.6], [1.2, 3, -3.5], wallM, false, true);
      box(g, [-1.25, 0.95, -3.48], [1.25, 1.02, -3.3], col("#ffffff")); box(g, [-0.02, 1.0, -3.56], [0.02, 2.4, -3.54], col("#ffffff"));
      plane(g, 4.5, 2.8, basic("winView", { map: windowView() }), [0, 1.7, -4.4]);
      box(g, [-4.3, 0, -3.6], [-4.2, 3, 3.2], wallM, false, true); box(g, [4.2, 0, -3.6], [4.3, 3, 3.2], wallM, false, true);
      desk(g, [-0.95, 0, -1.95], [0.95, 0.76, -1.1], "#d9b98e");
      chair(g, 0, -2.45, 1);
      // laptop: screen faces Aiman (-z side), its back to the camera
      box(g, [-0.45, 0.76, -1.78], [-0.05, 0.775, -1.5], col("#b9bdc6"));
      const lid = box(g, [-0.45, 0.775, -1.79], [-0.05, 1.03, -1.775], col("#b9bdc6")); lid.rotation.x = -0.15;
      sc.laptop = plane(g, 0.36, 0.22, new THREE.MeshBasicMaterial({ map: monitorTex({ kind: "office", seed: 2 }) }), [-0.25, 0.9, -1.795], Math.PI);
      // the phone lying on the desk (cartoon-oversized so inserts read): screen up, long axis along z
      const pg = new THREE.Group(); pg.position.set(0.42, 0.775, -1.36); g.add(pg);
      box(pg, [-0.065, -0.004, -0.13], [0.065, 0.012, 0.13], col("#22242e"));
      sc.phone = plane(pg, 0.115, 0.235, new THREE.MeshBasicMaterial({ map: phoneTex({ kind: "home" }) }), [0, 0.0125, 0], 0, -Math.PI / 2);
      sc.phoneG = pg;
      box(g, [0.55, 0.76, -1.85], [0.7, 0.88, -1.7], col("#e05a4f"));                     // mug
      plant(g, -3.4, -2.9); box(g, [-4.15, 0, -1.6], [-3.6, 1.9, 0.4], col("#9a6b47"));      // plant + bookshelf
      for (let i = 0; i < 5; i++) box(g, [-3.7, 1.0 + (i % 2) * 0.45, -1.4 + i * 0.32], [-3.62, 1.32 + (i % 2) * 0.45, -1.2 + i * 0.32], col(["#c0504d", "#4f81bd", "#9bbb59", "#f2c14e", "#8064a2"][i]));
      // kitchen corner: counter along the right wall + microwave facing the room
      box(g, [3.3, 0, -3.4], [4.15, 0.92, 0.6], col("#f4f1ea")); box(g, [3.28, 0.88, -3.42], [4.17, 0.94, 0.62], col("#8a8f99"));
      box(g, [3.35, 0.94, -1.5], [3.8, 1.26, -0.9], col("#d7dbe2"));
      sc.micro = plane(g, 0.16, 0.06, new THREE.MeshBasicMaterial({ map: microwaveTex(false) }), [3.345, 1.17, -0.98], -Math.PI / 2);
      box(g, [3.34, 0.98, -1.45], [3.346, 1.22, -1.05], col("#2a2f38"));                   // microwave door glass
      box(g, [3.6, 0.94, 0.1], [3.9, 1.3, 0.4], col("#c0504d"));                            // kettle-ish
    }

    // ===== OFFICE: open plan (day desks), SOC wall, server corridor, chat monitor =====
    {
      const g = this.sets.office;
      box(g, [-9, -0.05, -7], [9, 0, 7], lam("offFloor", { map: rep(carpet("off", "#8792a6"), 8, 6) }), false, true);
      const wm = lam("offWall", { map: rep(plaster("off", "#e4e8ee"), 4, 1.2) });
      box(g, [-9, 0, -7.1], [9, 3.2, -7], wm, false, true); box(g, [-9.1, 0, -7], [-9, 3.2, 7], wm, false, true); box(g, [9, 0, -7], [9.1, 3.2, 7], wm, false, true);
      sc.office = [];
      for (const x of [-1.5, 1.5]) { desk(g, [x - 0.7, 0, -1.85], [x + 0.7, 0.76, -1.15]); chair(g, x, -2.55, 1); sc.office.push(monitor(g, [x, 1.15, -1.45], 0.6, Math.PI)); }
      box(g, [-3, 0, -3.15], [3, 1.4, -3.05], col("#5aa3a0"));                               // partition
      plant(g, -2.6, -1.4); plant(g, 2.7, -1.2);
      // SOC wall of screens
      box(g, [-8.3, 0.6, -6.98], [-2.7, 3.0, -6.9], col("#1b1e26"));
      sc.soc = plane(g, 5.4, 2.25, new THREE.MeshBasicMaterial({ map: monitorTex({ kind: "soc", alert: false, seed: 0 }) }), [-5.5, 1.8, -6.885]);
      desk(g, [-7, 0, -4.4], [-4, 0.76, -3.7], "#cfd5df");
      // server corridor: two rack rows along z
      for (const x of [5.6, 8.4]) for (let z = -6; z < 4; z += 0.9) {
        const m = box(g, [x - 0.4, 0, z], [x + 0.4, 2.2, z + 0.82], lam("rack0", { map: racks(0) }));
        this.rackMeshes.push(m);
      }
      // chat monitor facing the camera
      desk(g, [3.4, 0, -3.4], [4.6, 0.76, -2.7], "#cfd5df");
      sc.chat = monitor(g, [4.0, 1.12, -3.0], 0.8);
    }

    // ===== DOOR: night wall with the Approve door; warm room behind =====
    {
      const g = this.sets.door;
      box(g, [-30, -0.05, -30], [30, 0, 20], lam("street", { map: rep(stoneHD("doorPave", ["#7d7a86", "#74717d", "#86838f", "#6c6976"], "#55525e"), 20, 16) }), false, true);
      const bm = lam("brick", { map: rep(brick(), 4, 2) });
      box(g, [-7, 0, -2.4], [-0.62, 4.2, -2.2], bm, false, true); box(g, [0.62, 0, -2.4], [7, 4.2, -2.2], bm, false, true);
      box(g, [-0.62, 2.32, -2.4], [0.62, 4.2, -2.2], bm, false, true);
      box(g, [-0.72, 0, -2.18], [-0.62, 2.42, -2.12], col("#4a3426")); box(g, [0.62, 0, -2.18], [0.72, 2.42, -2.12], col("#4a3426")); box(g, [-0.72, 2.32, -2.18], [0.72, 2.42, -2.12], col("#4a3426"));
      // warm room behind the doorway (unlit, bright: blooms a little)
      const warm = basic("warm", { color: new THREE.Color(1.25, 0.82, 0.45) });
      box(g, [-1.6, 0, -4.6], [1.6, 3, -4.5], warm, false, false); box(g, [-1.6, 0, -4.6], [-1.5, 3, -2.4], warm, false, false); box(g, [1.5, 0, -4.6], [1.6, 3, -2.4], warm, false, false);
      box(g, [-1.6, -0.04, -4.6], [1.6, 0.0, -2.4], basic("warmFloor", { color: new THREE.Color(0.9, 0.6, 0.35) }), false, false);
      // door leaf on a hinge at x = -0.6, with the green Approve plaque and a knob
      this.door = new THREE.Group(); this.door.position.set(-0.6, 0, -2.3); g.add(this.door);
      box(this.door, [0, 0, -0.04], [1.2, 2.3, 0.04], lam("doorWood", { map: rep(planksHD(), 0.6, 1.1) }));
      plane(this.door, 0.7, 0.35, basic("doorSign", { map: doorSignTex(), transparent: true }), [0.6, 1.55, 0.045]);
      const knob = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 8), col("#d9b44a")); knob.position.set(1.05, 1.05, 0.08); this.door.add(knob);
      box(g, [-0.18, 2.55, -2.2], [0.18, 2.75, -1.95], col("#2b2e3a"));
      const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 8), basic("lampGlow", { color: new THREE.Color(2.2, 1.8, 1.1) })); lamp.position.set(0, 2.5, -1.95); g.add(lamp);
      box(g, [3.2, 0, -2.2], [3.8, 0.9, -1.6], col("#3a3d48")); // bin
    }
    this.screens = sc as World["screens"];

    // fx cards (unlit, never inked)
    this.buzz = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: buzzTex(), transparent: true, depthWrite: false }));
    this.knock = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: knockTex(), transparent: true, depthWrite: false }));
    for (const m of [this.buzz, this.knock]) { m.layers.set(NOINK); m.visible = false; m.renderOrder = 3; R.add(m); }
    for (let i = 0; i < 3; i++) this.cards.push(new Card(R));
  }

  /** camera-relative sun frozen per shot (az from the shot camera's forward axis, el elevation) */
  private shotSun(s: Shot) {
    let d = this.sunCache.get(s.id);
    if (!d) {
      const L0 = LIGHTS[s.light], c = s.cam(0, 0);
      const fwd = V(c.look[0] - c.pos[0], 0, c.look[2] - c.pos[2]).normalize();
      const az = THREE.MathUtils.degToRad(L0.az), el = THREE.MathUtils.degToRad(L0.el);
      // az 0 = sun straight ahead (backlight), +90 = screen right, 180 = behind the camera
      const right = V(-fwd.z, 0, fwd.x);
      const h = fwd.clone().multiplyScalar(Math.cos(az)).addScaledVector(right, Math.sin(az)).normalize();
      d = h.multiplyScalar(Math.cos(el)).add(V(0, Math.sin(el), 0)).normalize();
      this.sunCache.set(s.id, d);
    }
    return d;
  }

  update(id: number, f: number, cam: THREE.PerspectiveCamera, scene: THREE.Scene) {
    const s = SHOTS[id - 1], lf = f - s.a, u = (f - s.a) / Math.max(1, s.b - s.a), Lp = LIGHTS[s.light], K = LOOK[s.light];
    // ---- camera ----
    const c: Cam = s.cam(u, lf);
    cam.position.set(...c.pos); cam.up.set(0, 1, 0); cam.lookAt(...c.look); cam.rotateZ(c.roll);
    cam.fov = c.fov; cam.near = 0.05; cam.far = 1200; cam.updateProjectionMatrix(); cam.updateMatrixWorld();
    cam.layers.enable(NOINK);
    const focus = V(...c.look), dist = cam.position.distanceTo(focus);
    // ---- sets ----
    for (const k of Object.keys(this.sets) as SetName[]) this.sets[k].visible = k === s.set;
    // ---- light rig ----
    const sunDir = this.shotSun(s);
    this.hemi.color.set(Lp.sky); this.hemi.groundColor.set(Lp.ground); this.hemi.intensity = Lp.hemiI;
    this.sun.color.set(Lp.sunCol); this.sun.intensity = Lp.sunI;
    const Rr = THREE.MathUtils.clamp(dist * 1.3 + 3, 4, 60);
    this.sun.position.copy(focus).addScaledVector(sunDir, 80); this.sun.target.position.copy(focus);
    const shc = this.sun.shadow.camera;
    shc.left = -Rr; shc.right = Rr; shc.top = Rr; shc.bottom = -Rr; shc.near = 1; shc.far = 200; shc.updateProjectionMatrix();
    this.sun.shadow.bias = Lp.bias; this.sun.shadow.normalBias = Lp.normalBias * Math.max(1, Rr / 12);
    TONE.uLitCol.value.set(...Lp.lit); TONE.uShadeCol.value.set(...Lp.shade); TONE.uShadeLift.value.set(...Lp.lift);
    TONE.uLambert.value = Lp.lambert; TONE.uSideK.value = Lp.sideK; TONE.uTerm.value = Lp.term; TONE.uBounce.value.set(...K.bounce); TONE.uSat.value = K.sat;
    CHAR.uCharTint.value.set(...Lp.charTint); CHAR.uCharShade.value = Lp.charShade; CHAR.uGrad.value = Lp.charGrad;
    CHAR.uBodyGrad.value = Lp.bodyGrad; CHAR.uSideTint.value.set(...Lp.sideTint);
    const su = this.skyMat.uniforms;
    K.sky.c.forEach((h, i) => untone(h, su["c" + i].value));
    const e = K.sky.e.map((deg) => THREE.MathUtils.degToRad(deg)); su.e.value.set(e[1], e[2], e[3], e[4]);
    this.sky.position.copy(cam.position);
    untone(Lp.fog, this.fog.color); this.fog.near = Lp.fogNear; this.fog.far = Lp.fogFar;
    scene.fog = this.fog; scene.background = null;

    // ---- screens / props ----
    const S = this.screens, setMap = (m: THREE.Mesh, t: THREE.Texture) => { const mm = m.material as THREE.MeshBasicMaterial; if (mm.map !== t) { mm.map = t; mm.needsUpdate = true; } };
    if (s.set === "home") {
      setMap(S.phone, phoneTex(s.phone ? s.phone(lf) : { kind: "home" }));
      setMap(S.micro, microwaveTex(s.micro ? s.micro(lf) : false));
      const b = s.buzz ? s.buzz(lf) : 0;
      S.phoneG.position.set(0.42 + Math.sin(f * 2.7) * 0.004 * b, 0.775, -1.36 + Math.cos(f * 3.1) * 0.003 * b);
      S.phoneG.rotation.y = Math.sin(f * 1.9) * 0.05 * b;
      if (b > 0) {
        this.buzz.visible = true; this.buzz.material = this.buzz.material as THREE.Material;
        this.buzz.position.set(L.home.phone[0], L.home.phone[1] + 0.02, L.home.phone[2]); this.buzz.rotation.set(-Math.PI / 2, 0, 0);
        const k = 0.42 + 0.04 * Math.sin(f * 1.3); this.buzz.scale.set(k, k, 1);
      } else this.buzz.visible = false;
    } else this.buzz.visible = false;
    if (s.set === "den") {
      setMap(S.den, monitorTex(s.den ? s.den(lf) : { kind: "code", seed: Math.floor(f / 6) }));
      S.denSide.forEach((m, i) => setMap(m, monitorTex({ kind: "code", seed: Math.floor(f / 7) + i * 3 })));
    }
    if (s.set === "office") {
      setMap(S.chat, monitorTex(s.chatMon ? s.chatMon(lf) : { kind: "staffchat", shown: 2 }));
      setMap(S.soc, monitorTex(s.soc ? s.soc(lf) : { kind: "soc", alert: false, seed: f / 10 }));
      S.office.forEach((m, i) => setMap(m, monitorTex({ kind: "office", seed: i })));
      const rm = lam("rack0", {}) as THREE.MeshLambertMaterial, on = Math.floor(f / 9) % 2;
      const want = racks(on); if (rm.map !== want) { rm.map = want; rm.needsUpdate = true; }
    }
    if (s.set === "door") this.door.rotation.y = (s.door ? s.door(lf) : 0) * 1.55;
    const kn = s.knock ? s.knock(lf) : 0;
    this.knock.visible = kn > 0;
    if (kn > 0) { this.knock.position.set(O.door[0] + 0.15, 1.45, -2.05); this.knock.quaternion.copy(cam.quaternion); this.knock.scale.set(0.6, 0.6, 1); }

    // ---- cast: lit billboards with contact blobs ----
    const cast = s.cast ? s.cast(lf, f) : [];
    this.cards.forEach((cd, i) => {
      const a = cast[i];
      cd.mesh.visible = cd.blob.visible = !!a;
      if (!a) return;
      const seed = ({ aiman: 1, scammer: 2, ravi: 3, mira: 4, david: 5 } as Record<Who, number>)[a.who];
      const id0 = idle(f, seed);
      const pose = { ...a.pose, blink: a.pose.blink ?? blinkAt(f, seed), bob: (a.pose.bob ?? 0) + (a.pose.step == null ? id0.bob : 0), lean: (a.pose.lean ?? 0) + (a.pose.step == null ? id0.lean : 0) };
      const g2 = cd.cv.getContext("2d")!;
      g2.setTransform(1, 0, 0, 1, 0, 0); g2.clearRect(0, 0, cd.cv.width, cd.cv.height); g2.setTransform(Card.K, 0, 0, Card.K, 0, 0);
      drawStick(g2, a.who, pose);
      cd.tex.needsUpdate = true;
      cd.mesh.position.set(...a.pos);
      cd.mesh.rotation.set(0, Math.atan2(cam.position.x - a.pos[0], cam.position.z - a.pos[2]), 0);
      const sc2 = a.scale ?? 1; cd.mesh.scale.set(sc2, sc2, 1);
      cd.blob.position.set(a.pos[0], a.pos[1] + 0.006, a.pos[2]); cd.blob.scale.set(0.9 * sc2, 1, 0.45 * sc2);
      cd.blob.visible = !a.pose.sit;
      const bm = cd.blob.material as THREE.MeshBasicMaterial; bm.color.setRGB(...Lp.blob).multiplyScalar(1 / Math.max(...Lp.blob));
    });
    return focus;
  }
}

export { FPS, rng };
