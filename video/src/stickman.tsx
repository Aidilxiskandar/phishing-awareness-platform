import React from "react";

/* Articulated stick figure drawn as an SVG <g>.
   Angles are in DEGREES, measured like screen-space math: 90 = straight down,
   0 = right, 180 = left, -90 = up. Each limb is two segments (upper + lower)
   so elbows and knees bend. */

const D2R = Math.PI / 180;
export const seg = (x: number, y: number, angleDeg: number, len: number) => ({
  x: x + Math.cos(angleDeg * D2R) * len,
  y: y + Math.sin(angleDeg * D2R) * len,
});

export type Mouth = "neutral" | "open" | "smile" | "worried";

export type Pose = {
  x: number;
  y: number; // hip position
  scale?: number;
  color?: string;
  lean?: number; // torso lean in degrees (+ = leaning right/forward)
  armL?: [number, number]; // [upperArm, forearm] angles
  armR?: [number, number];
  legL?: [number, number]; // [thigh, shin] angles
  legR?: [number, number];
  headTilt?: number;
  mouth?: Mouth;
  flip?: boolean; // face left instead of right
};

const Limb: React.FC<{ a: { x: number; y: number }; b: { x: number; y: number }; c?: { x: number; y: number }; color: string; w: number }>
  = ({ a, b, c, color, w }) => (
    <polyline
      points={c ? `${a.x},${a.y} ${b.x},${b.y} ${c.x},${c.y}` : `${a.x},${a.y} ${b.x},${b.y}`}
      fill="none"
      stroke={color}
      strokeWidth={w}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  );

export const Stickman: React.FC<Pose> = ({
  x, y, scale = 2.4, color = "#eaf0fb", lean = 0,
  armL = [100, 108], armR = [80, 72], legL = [96, 94], legR = [84, 86],
  headTilt = 0, mouth = "neutral", flip = false,
}) => {
  const SPINE = 52, NECK = 12, HEADR = 16, UARM = 24, FARM = 22, THIGH = 30, SHIN = 30, W = 7;

  const hip = { x: 0, y: 0 };
  const shoulder = seg(hip.x, hip.y, -90 + lean, SPINE);
  const neck = seg(shoulder.x, shoulder.y, -90 + lean, NECK);
  const head = seg(neck.x, neck.y, -90 + lean + headTilt, HEADR);

  const lElbow = seg(shoulder.x, shoulder.y, armL[0], UARM);
  const lHand = seg(lElbow.x, lElbow.y, armL[1], FARM);
  const rElbow = seg(shoulder.x, shoulder.y, armR[0], UARM);
  const rHand = seg(rElbow.x, rElbow.y, armR[1], FARM);

  const lKnee = seg(hip.x, hip.y, legL[0], THIGH);
  const lFoot = seg(lKnee.x, lKnee.y, legL[1], SHIN);
  const rKnee = seg(hip.x, hip.y, legR[0], THIGH);
  const rFoot = seg(rKnee.x, rKnee.y, legR[1], SHIN);

  // face: two eyes + a mouth, oriented to facing direction
  const dir = flip ? -1 : 1;
  const eyeY = head.y - 2;
  const mouthPath = {
    neutral: `M ${head.x - 5},${head.y + 7} L ${head.x + 5},${head.y + 7}`,
    open: "",
    smile: `M ${head.x - 6},${head.y + 5} Q ${head.x},${head.y + 11} ${head.x + 6},${head.y + 5}`,
    worried: `M ${head.x - 6},${head.y + 9} Q ${head.x},${head.y + 4} ${head.x + 6},${head.y + 9}`,
  }[mouth];

  return (
    <g transform={`translate(${x},${y}) scale(${scale})`}>
      {/* legs (behind) */}
      <Limb a={hip} b={lKnee} c={lFoot} color={color} w={W} />
      <Limb a={hip} b={rKnee} c={rFoot} color={color} w={W} />
      {/* spine */}
      <Limb a={hip} b={shoulder} color={color} w={W} />
      {/* arms */}
      <Limb a={shoulder} b={lElbow} c={lHand} color={color} w={W} />
      <Limb a={shoulder} b={rElbow} c={rHand} color={color} w={W} />
      {/* head */}
      <circle cx={head.x} cy={head.y} r={HEADR} fill="none" stroke={color} strokeWidth={W} />
      {/* eyes */}
      <circle cx={head.x + dir * 4} cy={eyeY} r={1.8} fill={color} />
      <circle cx={head.x - dir * 1} cy={eyeY} r={1.8} fill={color} />
      {mouth === "open" ? (
        <circle cx={head.x} cy={head.y + 7} r={3.5} fill={color} />
      ) : (
        <path d={mouthPath} stroke={color} strokeWidth={2.4} fill="none" strokeLinecap="round" />
      )}
    </g>
  );
};

// Interpolate smoothly between two poses (0..1). Positions + every angle pair.
export const lerpPose = (a: Pose, b: Pose, t: number): Pose => {
  const L = (p?: number, q?: number) => (p ?? 0) + ((q ?? 0) - (p ?? 0)) * t;
  const P = (p: [number, number] | undefined, q: [number, number] | undefined): [number, number] =>
    [L(p?.[0], q?.[0]), L(p?.[1], q?.[1])];
  return {
    x: L(a.x, b.x), y: L(a.y, b.y),
    scale: L(a.scale ?? 2.4, b.scale ?? 2.4),
    color: b.color ?? a.color,
    lean: L(a.lean, b.lean),
    armL: P(a.armL, b.armL), armR: P(a.armR, b.armR),
    legL: P(a.legL, b.legL), legR: P(a.legR, b.legR),
    headTilt: L(a.headTilt, b.headTilt),
    mouth: t < 0.5 ? a.mouth : b.mouth,
    flip: t < 0.5 ? a.flip : b.flip,
  };
};
