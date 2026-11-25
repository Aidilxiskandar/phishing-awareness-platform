// Character test sheet (master prompt step 9): every cast member in front / side / walk + expressions.
import React, { useEffect, useRef } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { drawStick, arms, Who, Expr, Pose } from "./stick";

const ROWS: { who: Who; poses: Pose[] }[] = (["aiman", "scammer", "ravi", "mira", "david"] as Who[]).map((who) => ({
  who,
  poses: [
    { face: "front", expr: who === "scammer" ? "smirk" : "neutral" },
    { face: "left", expr: "neutral", step: 0.15 },
    { face: "right", expr: "neutral", step: 0.6 },
    ...(["happy", "surprised", "worried", "angry", "tired"] as Expr[]).map((e) => ({ face: "front" as const, expr: e })),
  ],
}));
const EXTRA: { who: Who; pose: Pose }[] = [
  { who: "aiman", pose: { face: "front", expr: "worried", armR: arms.tap("R", 0.5), armL: arms.phone("L"), prop: { kind: "phone", side: "L" } } },
  { who: "aiman", pose: { face: "front", expr: "annoyed", armL: arms.ears("L"), armR: arms.ears("R") } },
  { who: "aiman", pose: { face: "right", expr: "tired", sit: true, armL: arms.slump("L"), armR: arms.slump("R") } },
  { who: "scammer", pose: { face: "front", expr: "sweet", headset: true, armL: arms.type("L", 0), armR: arms.type("R", 0) } },
  { who: "scammer", pose: { face: "right", expr: "sly", armR: arms.knock("R", 0.25) } },
  { who: "ravi", pose: { face: "front", expr: "determined", armR: arms.wag("R", 0) } },
  { who: "ravi", pose: { face: "front", expr: "happy", armR: arms.thumb("R") } },
  { who: "aiman", pose: { face: "right", expr: "neutral", armR: arms.offer("R"), prop: { kind: "key", side: "R" } } },
];

export const CastSheet: React.FC = () => {
  useCurrentFrame();
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const g = ref.current!.getContext("2d")!;
    g.fillStyle = "#f4f1ea"; g.fillRect(0, 0, 3200, 2400);
    const cell = 360, k = cell / 1000;
    ROWS.forEach((r, ri) => r.poses.forEach((p, ci) => { g.save(); g.translate(20 + ci * 230, 20 + ri * 380); g.scale(k, k); drawStick(g, r.who, p); g.restore(); }));
    EXTRA.forEach((e, i) => { g.save(); g.translate(1900 + (i % 4) * 300, 20 + Math.floor(i / 4) * 560); g.scale(0.5, 0.5); drawStick(g, e.who, e.pose); g.restore(); });
  }, []);
  return <AbsoluteFill style={{ background: "#f4f1ea" }}><canvas ref={ref} width={3200} height={2400} style={{ width: "100%", height: "100%" }} /></AbsoluteFill>;
};
