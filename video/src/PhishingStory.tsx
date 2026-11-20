import React from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Pose, Stickman, lerpPose } from "./stickman";

/* ============================================================================
   "Don't take the bait" — a stick-figure phishing story (~34s @30fps)
   walk in → email drops on a fishing hook → almost clicks → STOP → inspects
   the fake sender → reports it → win.
   ========================================================================== */

const C = {
  bg: "#0a0f1c", surface: "#111a2e", line: "#1e2b45", ink: "#eaf0fb",
  muted: "#8a9bbb", brand: "#6366f1", brand2: "#818cf8",
  red: "#fb7185", green: "#34d399", amber: "#fbbf24", blue: "#38bdf8",
};
const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif';
const GROUND = 792;

// --- shared poses ----------------------------------------------------------
const STAND: Pose = { x: 760, y: 648, lean: 3, legL: [95, 93], legR: [85, 87], armL: [102, 110], armR: [78, 70], mouth: "neutral" };
const LOOKUP: Pose = { ...STAND, headTilt: 10, mouth: "open" };
const REACH: Pose = { ...STAND, lean: 12, armR: [-38, -18], headTilt: 8, mouth: "open" };
const RECOIL: Pose = { ...STAND, x: 715, lean: -16, armL: [-125, -150], armR: [-55, -80], headTilt: -10, mouth: "worried" };
const INSPECT: Pose = { ...STAND, lean: 14, armR: [15, 2], headTilt: 10, mouth: "neutral" };
const CHEER: Pose = { ...STAND, armL: [-130, -150], armR: [-50, -30], legL: [98, 96], legR: [82, 84], mouth: "smile" };
const THUMBS: Pose = { ...STAND, armR: [-70, -95], armL: [108, 120], mouth: "smile" };

const walkPose = (x: number, phase: number): Pose => {
  const a = Math.sin(phase * 2 * Math.PI);
  const b = Math.cos(phase * 2 * Math.PI);
  return {
    x, y: 648 - Math.abs(a) * 5, lean: 5,
    legL: [96 + a * 22, 96 + a * 22 + Math.max(0, a) * 24],
    legR: [84 - a * 22, 84 - a * 22 + Math.max(0, -a) * 24],
    armL: [100 + b * 16, 112 + b * 8],
    armR: [80 - b * 16, 68 - b * 8],
    mouth: "smile",
  };
};

// --- reusable bits ---------------------------------------------------------
const Background: React.FC = () => {
  const f = useCurrentFrame();
  const drift = interpolate(f, [0, 300], [0, 24]);
  return (
    <AbsoluteFill style={{ backgroundColor: C.bg }}>
      <AbsoluteFill style={{ background: `radial-gradient(60% 50% at ${50 + drift / 8}% -5%, rgba(99,102,241,0.18), transparent 60%)` }} />
      <AbsoluteFill style={{
        backgroundImage: `linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px)`,
        backgroundSize: "70px 70px", opacity: 0.1,
        maskImage: "radial-gradient(75% 70% at 50% 45%, #000 40%, transparent 100%)",
      }} />
    </AbsoluteFill>
  );
};

const Stage: React.FC<{ children: React.ReactNode; shadowX?: number }> = ({ children, shadowX = 760 }) => (
  <svg viewBox="0 0 1920 1080" width="100%" height="100%" style={{ position: "absolute", inset: 0 }}>
    <line x1={120} y1={GROUND} x2={1800} y2={GROUND} stroke={C.line} strokeWidth={3} />
    <ellipse cx={shadowX} cy={GROUND + 6} rx={90} ry={14} fill="#000" opacity={0.35} />
    {children}
  </svg>
);

const Caption: React.FC<{ text: React.ReactNode; color?: string; top?: string }> = ({ text, color = C.ink, top = "16%" }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [4, 20], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-start" }}>
      <div style={{ marginTop: top, opacity: o, color, fontSize: 52, fontWeight: 800, letterSpacing: -1, textAlign: "center", maxWidth: 1400, textShadow: "0 4px 24px rgba(0,0,0,.5)" }}>
        {text}
      </div>
    </AbsoluteFill>
  );
};

const HookedEmail: React.FC<{ x: number; y: number; wobble?: number }> = ({ x, y, wobble = 0 }) => (
  <g transform={`translate(${x},${y}) rotate(${wobble})`}>
    <line x1={0} y1={-900} x2={0} y2={-70} stroke={C.muted} strokeWidth={3} strokeDasharray="2 7" />
    <path d={`M0,-70 q 2,26 -16,28 q -18,2 -12,-16`} fill="none" stroke={C.muted} strokeWidth={5} strokeLinecap="round" />
    <rect x={-100} y={-34} width={200} height={132} rx={12} fill={C.surface} stroke={C.red} strokeWidth={3.5} />
    <path d="M-100,-34 L0,46 L100,-34" fill="none" stroke={C.red} strokeWidth={3.5} />
    <text x={0} y={86} textAnchor="middle" fill={C.red} fontSize={26} fontWeight={800} fontFamily={FONT}>URGENT</text>
  </g>
);

// --- scenes ----------------------------------------------------------------

const S1Walk: React.FC = () => {
  const f = useCurrentFrame();
  const x = interpolate(f, [0, 115], [-180, 760], { extrapolateRight: "clamp" });
  const pose = f < 115 ? walkPose(x, f / 15) : STAND;
  return (
    <AbsoluteFill>
      <Stage shadowX={pose.x}><Stickman {...pose} /></Stage>
      <Caption text={<>Meet <span style={{ color: C.brand2 }}>Sam</span> — just checking email.</>} />
    </AbsoluteFill>
  );
};

const S2Drop: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const drop = spring({ frame: f, fps, config: { damping: 9, mass: 0.8 } });
  const ey = interpolate(drop, [0, 1], [-260, 300]);
  const wob = Math.sin(f / 9) * (f > 40 ? 2.5 : 0);
  const pose: Pose = f > 30 ? LOOKUP : STAND;
  return (
    <AbsoluteFill>
      <Stage shadowX={760}>
        <HookedEmail x={1230} y={ey} wobble={wob} />
        <Stickman {...pose} />
      </Stage>
      <Caption text={<>A new email drops in… <span style={{ color: C.red }}>“Verify now!”</span></>} />
    </AbsoluteFill>
  );
};

const S3AlmostClick: React.FC = () => {
  const f = useCurrentFrame();
  const reach = interpolate(f, [0, 45], [0, 1], { extrapolateRight: "clamp" });
  const stopAt = 95;
  const recoil = interpolate(f, [stopAt, stopAt + 18], [0, 1], { extrapolateRight: "clamp" });
  let pose = lerpPose(STAND, REACH, reach);
  pose = lerpPose(pose, RECOIL, recoil);
  const wob = Math.sin(f / 9) * 2.5;
  const showStop = f >= stopAt - 4;
  const stopScale = spring({ frame: f - (stopAt - 4), fps: 30, config: { damping: 7 } });
  return (
    <AbsoluteFill>
      <Stage shadowX={pose.x}>
        <HookedEmail x={1230} y={300} wobble={wob} />
        <Stickman {...pose} />
      </Stage>
      {f < stopAt && <Caption text={<>“Looks official… better click?”</>} color={C.muted} />}
      {showStop && (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
          <div style={{ transform: `scale(${0.4 + stopScale * 0.6})`, color: "#fff", background: C.red, fontSize: 150, fontWeight: 900, padding: "10px 70px", borderRadius: 28, letterSpacing: 2, boxShadow: `0 30px 80px -20px ${C.red}` }}>
            STOP
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

const S4Inspect: React.FC = () => {
  const f = useCurrentFrame();
  const t = interpolate(f, [0, 35], [0, 1], { extrapolateRight: "clamp" });
  const pose = lerpPose(RECOIL, INSPECT, t);
  const magO = interpolate(f, [30, 48], [0, 1], { extrapolateRight: "clamp" });
  const ring = interpolate(f, [55, 75], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <Stage shadowX={pose.x}>
        <Stickman {...pose} />
        {/* the sender under scrutiny */}
        <g opacity={magO} transform="translate(1180,470)">
          <rect x={-310} y={-54} width={620} height={108} rx={16} fill={C.surface} stroke={C.line} strokeWidth={2} />
          <text x={-280} y={14} fill={C.ink} fontSize={46} fontWeight={700} fontFamily="ui-monospace, Menlo, monospace">
            it-support@micros<tspan fill={C.amber}>0</tspan>ft.com
          </text>
          {/* magnifier over the 0 */}
          <g transform="translate(150,0)">
            <circle r={52} fill="rgba(56,189,248,0.08)" stroke={C.blue} strokeWidth={7} />
            <line x1={37} y1={37} x2={78} y2={78} stroke={C.blue} strokeWidth={11} strokeLinecap="round" />
            <circle r={26} fill="none" stroke={C.amber} strokeWidth={4} opacity={ring} />
          </g>
        </g>
      </Stage>
      <Caption text={<>Wait — that’s a <span style={{ color: C.amber }}>zero</span>, not an “o”.</>} top="9%" />
    </AbsoluteFill>
  );
};

const S5Report: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fly = interpolate(f, [0, 40], [0, 1], { extrapolateRight: "clamp" });
  const ex = interpolate(fly, [0, 1], [1230, 1560]);
  const ey = interpolate(fly, [0, 1], [300, 560]);
  const eScale = interpolate(fly, [0, 1], [1, 0.4]);
  const cheer = spring({ frame: f - 42, fps, config: { damping: 10 } });
  const pose = lerpPose(INSPECT, CHEER, cheer);
  const check = spring({ frame: f - 46, fps, config: { damping: 8 } });
  return (
    <AbsoluteFill>
      <Stage shadowX={pose.x}>
        {/* report bin */}
        <g transform="translate(1560,500)">
          <rect x={-70} y={0} width={140} height={120} rx={14} fill={C.surface} stroke={C.green} strokeWidth={4} />
          <rect x={-86} y={-24} width={172} height={22} rx={8} fill={C.green} />
          <text x={0} y={180} textAnchor="middle" fill={C.green} fontSize={30} fontWeight={800} fontFamily={FONT}>REPORT</text>
        </g>
        <g transform={`translate(${ex},${ey}) scale(${eScale})`} opacity={1 - fly * 0.2}>
          <rect x={-100} y={-34} width={200} height={132} rx={12} fill={C.surface} stroke={C.red} strokeWidth={3.5} />
          <path d="M-100,-34 L0,46 L100,-34" fill="none" stroke={C.red} strokeWidth={3.5} />
        </g>
        <Stickman {...pose} />
        {/* green check */}
        <g transform="translate(760,360)" opacity={check} >
          <circle r={56 * check} fill="none" stroke={C.green} strokeWidth={9} />
          <path d={`M -26,2 L -6,24 L 30,-20`} fill="none" stroke={C.green} strokeWidth={11} strokeLinecap="round" strokeLinejoin="round" transform={`scale(${check})`} />
        </g>
      </Stage>
      <Caption text={<>Reported it. <span style={{ color: C.green }}>Nice catch, Sam!</span></>} />
    </AbsoluteFill>
  );
};

const S6Outro: React.FC = () => {
  const f = useCurrentFrame();
  const words = ["STOP", "CHECK", "REPORT"];
  const cols = [C.red, C.amber, C.green];
  const thumbs = spring({ frame: f - 6, fps: 30, config: { damping: 12 } });
  return (
    <AbsoluteFill>
      <Stage shadowX={420}><Stickman {...lerpPose(THUMBS, THUMBS, 1)} x={420} /></Stage>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", paddingLeft: 260 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 24, alignItems: "flex-start", opacity: thumbs }}>
          <div style={{ display: "flex", gap: 22, alignItems: "center" }}>
            {words.map((w, i) => {
              const a = interpolate(f, [10 + i * 12, 28 + i * 12], [0, 1], { extrapolateRight: "clamp" });
              return (
                <React.Fragment key={w}>
                  <span style={{ color: cols[i], fontSize: 96, fontWeight: 900, opacity: a, transform: `translateY(${(1 - a) * 30}px)` }}>{w}</span>
                  {i < 2 && <span style={{ color: C.line, fontSize: 70, opacity: a }}>·</span>}
                </React.Fragment>
              );
            })}
          </div>
          <div style={{ color: C.muted, fontSize: 40, fontWeight: 600 }}>Don’t take the bait. · <span style={{ color: C.brand2, fontWeight: 800 }}>PhishGuard</span></div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// --- timeline --------------------------------------------------------------
const SCENES: { c: React.FC; d: number }[] = [
  { c: S1Walk, d: 150 },
  { c: S2Drop, d: 165 },
  { c: S3AlmostClick, d: 200 },
  { c: S4Inspect, d: 185 },
  { c: S5Report, d: 185 },
  { c: S6Outro, d: 135 },
];
export const STORY_DURATION = SCENES.reduce((s, x) => s + x.d, 0); // 1020

export const PhishingStory: React.FC = () => {
  let at = 0;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, backgroundColor: C.bg }}>
      <Background />
      {SCENES.map(({ c: Scene, d }, i) => {
        const from = at; at += d;
        return (
          <Sequence key={i} from={from} durationInFrames={d}>
            <Scene />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
