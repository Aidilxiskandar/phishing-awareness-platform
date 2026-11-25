// "He Pressed Approve Just to Make It Stop": MFA-fatigue awareness short, 1920x1080 @ 30 fps.
// Engine: three.js inside Remotion, adapted from mromidev/claude-animated-shorts (MIT, see engine/LICENSE-*).
// Post chain (engine order): InkPass -> lens blur pre + main -> bloom (emissive only) -> NEUTRAL tone map -> grade, MSAA 4.
// Pixel-sized post parameters scale with the frame's short side / 1080, so --scale stills match the final.
import React, { useEffect, useMemo } from "react";
import * as THREE from "three";
import { AbsoluteFill, getInputProps, useCurrentFrame } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { useThree } from "@react-three/fiber";
import { EffectComposer } from "@react-three/postprocessing";
import { BlendFunction, BloomEffect, ToneMappingEffect, ToneMappingMode } from "postprocessing";
import { World } from "./world";
import { InkPass, noInkFallback } from "./engine/ink";
import { LensBlur } from "./engine/lensblur";
import { GradeEffect, GRADES, GRADE_STRENGTH, gradeFor } from "./engine/grade";
import { TOTAL, FLASH_AT, SHOTS, layersAt } from "./story";

export const MFA_FRAMES = TOTAL;
type PostToggles = { ink: boolean; lens: boolean; bloom: boolean; grade: boolean };
const toggles = (): PostToggles => ({ ink: true, lens: true, bloom: true, grade: true, ...((getInputProps() as { post?: Partial<PostToggles> }).post ?? {}) });

const makeBloom = () => {
  const b = new BloomEffect({ blendFunction: BlendFunction.ADD, intensity: 0.5, luminanceThreshold: 1.0, luminanceSmoothing: 0.2, mipmapBlur: true, levels: 6, radius: 0.6 });
  const mip = b.mipmapBlurPass, setSize = mip.setSize.bind(mip);
  mip.setSize = (w: number, h: number) => setSize(Math.round((1080 * w) / Math.max(h, 1)), 1080); // glow size fixed relative to the frame
  return b;
};

const Inner: React.FC<{ id: number }> = ({ id }) => {
  const f = useCurrentFrame();
  const { camera, scene } = useThree();
  const world = useMemo(() => new World(), []);
  const on = useMemo(toggles, []);
  const fx = useMemo(() => ({
    ink: new InkPass(scene, camera as THREE.PerspectiveCamera),
    lens: new LensBlur({ maxCoC: 24, nearScale: 1.2 }),
    bloom: makeBloom(),
    tone: new ToneMappingEffect({ mode: ToneMappingMode.NEUTRAL }),
    grade: new GradeEffect(GRADES.day, GRADE_STRENGTH.day),
  }), [camera, scene]);
  useEffect(() => () => InkPass.prototype.dispose.call(fx.ink), [fx]); // r3f writes dispose={null} onto the object
  const post = useMemo(() => (
    <EffectComposer multisampling={4}>
      {on.ink ? <primitive object={fx.ink} dispose={null} /> : <></>}
      {on.lens ? <primitive object={fx.lens.pre} dispose={null} /> : <></>}
      {on.lens ? <primitive object={fx.lens.main} dispose={null} /> : <></>}
      {on.bloom ? <primitive object={fx.bloom} dispose={null} /> : <></>}
      <primitive object={fx.tone} dispose={null} />
      {on.grade ? <primitive object={fx.grade} dispose={null} /> : <></>}
    </EffectComposer>
  ), [fx, on]);
  const cam = camera as THREE.PerspectiveCamera;
  const target = world.update(id, f, cam, scene);
  noInkFallback(world.root);
  const fwd = new THREE.Vector3(); cam.getWorldDirection(fwd);
  fx.lens.focus = Math.max(0.1, target.clone().sub(cam.position).dot(fwd));
  fx.lens.cInf = SHOTS[id - 1].dof ?? 0;
  gradeFor(fx.grade, SHOTS[id - 1].light);
  return (<><primitive object={world.root} dispose={null} />{post}</>);
};

const dprOverride = () => (getInputProps() as { post?: { dpr?: number } }).post?.dpr;
const ShotView: React.FC<{ id: number; alpha: number }> = ({ id, alpha }) => (
  <AbsoluteFill style={{ opacity: alpha }}>
    <ThreeCanvas width={1920} height={1080} {...(dprOverride() ? { dpr: dprOverride() } : {})} shadows
      gl={{ antialias: false, stencil: false, powerPreference: "high-performance", toneMappingExposure: 1.0 }}
      camera={{ fov: 40, near: 0.05, far: 1200 }}>
      <Inner id={id} />
    </ThreeCanvas>
  </AbsoluteFill>
);

export const MfaShort: React.FC = () => {
  const f = useCurrentFrame();
  const flash = f >= FLASH_AT && f < FLASH_AT + 6 ? [1, 0.85, 0.6, 0.4, 0.2, 0.08][f - FLASH_AT] : 0;
  return (
    <AbsoluteFill style={{ background: "#141415" }}>
      {layersAt(f).map((l, i) => <ShotView key={i ? "over" : "base"} id={l.id} alpha={l.alpha} />)}
      {flash > 0 && <AbsoluteFill style={{ background: "#ffffff", opacity: flash }} />}
    </AbsoluteFill>
  );
};
