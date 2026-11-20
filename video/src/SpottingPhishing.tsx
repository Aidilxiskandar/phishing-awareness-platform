import React from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/* ============================================================================
   SCRIPT — "Spotting a phishing email"  (~61s @ 30fps)

   00:00  Intro      PhishGuard · "Spotting a Phishing Email"
   00:04  Hook       "Every day, fake emails try to trick you. Learn the 5 signs."
   00:08  Flag 1     Urgency & threats  — "verify within 24 hours or you're locked out"
   00:16  Flag 2     Lookalike sender   — it-support@micros0ft.com (the 0, not an o)
   00:24  Flag 3     Mismatched links   — the text says one thing, the link goes elsewhere
   00:32  Flag 4     Asks for secrets   — password, MFA code, or payment details
   00:40  Flag 5     Off details        — generic greeting, spelling & grammar slips
   00:48  Golden rule  STOP · CHECK · REPORT
   00:56  Outro      "When in doubt, report it." · PhishGuard
   ========================================================================== */

const C = {
  bg: "#0a0f1c",
  bg2: "#0c1324",
  surface: "#111a2e",
  line: "#1e2b45",
  ink: "#eaf0fb",
  muted: "#8a9bbb",
  brand: "#6366f1",
  brand2: "#818cf8",
  red: "#fb7185",
  green: "#34d399",
  amber: "#fbbf24",
  blue: "#38bdf8",
};

const FONT =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif';

// --- helpers ---------------------------------------------------------------

const useEnter = (delay = 0, damping = 200) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping } });
};

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 200], [0, 30]);
  return (
    <AbsoluteFill style={{ backgroundColor: C.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(60% 50% at ${50 + drift / 6}% 0%, rgba(99,102,241,0.18), transparent 60%),
                       radial-gradient(50% 40% at 100% 100%, rgba(56,189,248,0.10), transparent 60%)`,
        }}
      />
      {/* faint grid */}
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px)`,
          backgroundSize: "64px 64px",
          opacity: 0.12,
          maskImage: "radial-gradient(70% 70% at 50% 50%, #000 40%, transparent 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

const ShieldLogo: React.FC<{ size?: number }> = ({ size = 64 }) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: size * 0.3,
      background: `linear-gradient(135deg, ${C.brand}, ${C.brand2})`,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      boxShadow: `0 20px 50px -18px ${C.brand}`,
    }}
  >
    <svg width={size * 0.58} height={size * 0.58} viewBox="0 0 24 24" fill="none"
      stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V5l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  </div>
);

// --- scenes ----------------------------------------------------------------

const Intro: React.FC = () => {
  const s = useEnter(4);
  const frame = useCurrentFrame();
  const lift = interpolate(s, [0, 1], [40, 0]);
  const titleIn = interpolate(frame, [18, 42], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 28 }}>
      <div style={{ transform: `translateY(${lift}px) scale(${0.8 + s * 0.2})`, opacity: s }}>
        <ShieldLogo size={110} />
      </div>
      <div style={{ opacity: titleIn, transform: `translateY(${(1 - titleIn) * 24}px)`, textAlign: "center" }}>
        <div style={{ color: C.muted, fontSize: 30, letterSpacing: 8, textTransform: "uppercase", fontWeight: 700 }}>
          PhishGuard Awareness
        </div>
        <div style={{ color: C.ink, fontSize: 86, fontWeight: 800, letterSpacing: -2, marginTop: 10 }}>
          Spotting a Phishing Email
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const a = interpolate(frame, [0, 24], [0, 1], { extrapolateRight: "clamp" });
  const b = interpolate(frame, [30, 54], [0, 1], { extrapolateRight: "clamp" });
  const five = useEnter(54, 12);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 20, padding: 160 }}>
      <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)`, color: C.ink, fontSize: 60, fontWeight: 700, textAlign: "center", lineHeight: 1.2 }}>
        Every day, fake emails try to trick you.
      </div>
      <div style={{ opacity: b, color: C.muted, fontSize: 44, fontWeight: 500, textAlign: "center" }}>
        Here are the{" "}
        <span style={{ display: "inline-block", transform: `scale(${0.6 + five * 0.4})`, color: C.amber, fontWeight: 800 }}>
          5 signs
        </span>{" "}
        that give them away.
      </div>
    </AbsoluteFill>
  );
};

const FlagScene: React.FC<{
  index: number;
  accent: string;
  title: string;
  children: React.ReactNode;
}> = ({ index, accent, title, children }) => {
  const card = useEnter(6, 16);
  const frame = useCurrentFrame();
  const num = useEnter(0, 10);
  const titleIn = interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 1360, display: "flex", flexDirection: "column", gap: 34 }}>
        {/* header: big number + title */}
        <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <div
            style={{
              width: 108,
              height: 108,
              borderRadius: 26,
              background: `${accent}22`,
              border: `2px solid ${accent}`,
              color: accent,
              fontSize: 60,
              fontWeight: 800,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transform: `scale(${0.5 + num * 0.5})`,
              opacity: num,
            }}
          >
            {index}
          </div>
          <div style={{ opacity: titleIn, transform: `translateX(${(1 - titleIn) * 30}px)` }}>
            <div style={{ color: C.muted, fontSize: 26, fontWeight: 700, letterSpacing: 4, textTransform: "uppercase" }}>
              Red flag {index} of 5
            </div>
            <div style={{ color: C.ink, fontSize: 64, fontWeight: 800, letterSpacing: -1.5, marginTop: 4 }}>
              {title}
            </div>
          </div>
        </div>
        {/* body card */}
        <div
          style={{
            background: C.surface,
            border: `1px solid ${C.line}`,
            borderLeft: `6px solid ${accent}`,
            borderRadius: 24,
            padding: "46px 52px",
            transform: `translateY(${(1 - card) * 40}px)`,
            opacity: card,
            boxShadow: "0 40px 80px -40px rgba(0,0,0,0.7)",
          }}
        >
          {children}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Flag1: React.FC = () => {
  const frame = useCurrentFrame();
  const pulse = 1 + Math.sin(frame / 7) * 0.03;
  return (
    <FlagScene index={1} accent={C.red} title="Urgency & threats">
      <div style={{ color: C.ink, fontSize: 46, lineHeight: 1.4 }}>
        <span
          style={{
            display: "inline-block",
            background: `${C.red}22`,
            color: C.red,
            fontWeight: 800,
            padding: "6px 18px",
            borderRadius: 12,
            transform: `scale(${pulse})`,
          }}
        >
          “Verify within 24 hours or your account is suspended.”
        </span>
        <div style={{ color: C.muted, fontSize: 38, marginTop: 28 }}>
          Real teams don’t threaten you into clicking. Panic is the trick — slow down.
        </div>
      </div>
    </FlagScene>
  );
};

const Flag2: React.FC = () => {
  const frame = useCurrentFrame();
  const ring = interpolate(frame, [30, 50], [0, 1], { extrapolateRight: "clamp" });
  return (
    <FlagScene index={2} accent={C.amber} title="A sender that’s almost right">
      <div style={{ color: C.ink, fontSize: 52, fontWeight: 700, fontFamily: "ui-monospace, Menlo, monospace" }}>
        it-support@micros
        <span style={{ position: "relative", color: C.amber }}>
          0
          <span
            style={{
              position: "absolute",
              inset: "-14px -10px",
              border: `3px solid ${C.amber}`,
              borderRadius: "50%",
              opacity: ring,
              transform: `scale(${0.6 + ring * 0.4})`,
            }}
          />
        </span>
        ft.com
      </div>
      <div style={{ color: C.muted, fontSize: 38, marginTop: 30 }}>
        A zero instead of an “o”. Lookalike domains imitate brands you trust —
        read the address character by character.
      </div>
    </FlagScene>
  );
};

const Flag3: React.FC = () => {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [36, 60], [0, 1], { extrapolateRight: "clamp" });
  return (
    <FlagScene index={3} accent={C.blue} title="Links that don’t match">
      <div style={{ display: "flex", alignItems: "center", gap: 20, fontSize: 44 }}>
        <span
          style={{
            background: `linear-gradient(180deg, ${C.brand2}, ${C.brand})`,
            color: "#fff",
            padding: "14px 26px",
            borderRadius: 12,
            fontWeight: 700,
          }}
        >
          Click to verify
        </span>
        <span style={{ color: C.muted, fontSize: 40 }}>→</span>
        <span
          style={{
            fontFamily: "ui-monospace, Menlo, monospace",
            color: C.red,
            fontSize: 38,
            opacity: reveal,
            transform: `translateX(${(1 - reveal) * -20}px)`,
            background: `${C.red}18`,
            padding: "10px 18px",
            borderRadius: 10,
          }}
        >
          http://secure-login.ru/pay
        </span>
      </div>
      <div style={{ color: C.muted, fontSize: 38, marginTop: 30 }}>
        Hover before you click. If the real destination isn’t where the text says —
        don’t go there.
      </div>
    </FlagScene>
  );
};

const Flag4: React.FC = () => (
  <FlagScene index={4} accent={C.red} title="Asking for secrets">
    <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
      {["Your password", "Your MFA code", "Payment details"].map((t) => (
        <div
          key={t}
          style={{
            background: `${C.red}14`,
            border: `1px solid ${C.red}55`,
            color: C.ink,
            fontSize: 40,
            fontWeight: 700,
            padding: "18px 30px",
            borderRadius: 16,
          }}
        >
          🚫 {t}
        </div>
      ))}
    </div>
    <div style={{ color: C.muted, fontSize: 38, marginTop: 30 }}>
      IT and your bank will never ask for these by email. If an email does — it’s phishing.
    </div>
  </FlagScene>
);

const Flag5: React.FC = () => (
  <FlagScene index={5} accent={C.green} title="Small details feel off">
    <div style={{ color: C.ink, fontSize: 46, lineHeight: 1.5 }}>
      “<span style={{ color: C.amber }}>Dear Valued Customer</span>, we has detected a
      problem with you’re account…”
    </div>
    <div style={{ color: C.muted, fontSize: 38, marginTop: 28 }}>
      Generic greetings, odd grammar and spelling slips. Trust your gut when something
      reads wrong.
    </div>
  </FlagScene>
);

const GoldenRule: React.FC = () => {
  const frame = useCurrentFrame();
  const words = ["STOP", "CHECK", "REPORT"];
  const colors = [C.red, C.amber, C.green];
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 46 }}>
      <div style={{ color: C.muted, fontSize: 34, letterSpacing: 6, textTransform: "uppercase", fontWeight: 700 }}>
        The golden rule
      </div>
      <div style={{ display: "flex", gap: 28, alignItems: "center" }}>
        {words.map((w, i) => {
          const d = 10 + i * 18;
          const a = interpolate(frame, [d, d + 18], [0, 1], { extrapolateRight: "clamp" });
          return (
            <React.Fragment key={w}>
              <span
                style={{
                  color: colors[i],
                  fontSize: 104,
                  fontWeight: 900,
                  letterSpacing: -2,
                  opacity: a,
                  transform: `translateY(${(1 - a) * 40}px)`,
                }}
              >
                {w}
              </span>
              {i < 2 && <span style={{ color: C.line, fontSize: 80, opacity: a }}>·</span>}
            </React.Fragment>
          );
        })}
      </div>
      <div
        style={{
          color: C.ink,
          fontSize: 44,
          marginTop: 10,
          opacity: interpolate(frame, [70, 95], [0, 1], { extrapolateRight: "clamp" }),
        }}
      >
        When in doubt, don’t click — <span style={{ color: C.green, fontWeight: 800 }}>report it.</span>
      </div>
    </AbsoluteFill>
  );
};

const Outro: React.FC = () => {
  const s = useEnter(4);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 24 }}>
      <div style={{ opacity: s, transform: `scale(${0.85 + s * 0.15})` }}>
        <ShieldLogo size={96} />
      </div>
      <div style={{ opacity: s, color: C.ink, fontSize: 58, fontWeight: 800, letterSpacing: -1 }}>
        PhishGuard
      </div>
      <div style={{ opacity: s, color: C.muted, fontSize: 34 }}>
        Security Awareness · Authorised use only
      </div>
    </AbsoluteFill>
  );
};

// --- timeline --------------------------------------------------------------

const SCENES: { c: React.FC; d: number }[] = [
  { c: Intro, d: 120 },
  { c: Hook, d: 120 },
  { c: Flag1, d: 240 },
  { c: Flag2, d: 240 },
  { c: Flag3, d: 240 },
  { c: Flag4, d: 240 },
  { c: Flag5, d: 240 },
  { c: GoldenRule, d: 240 },
  { c: Outro, d: 150 },
];

export const SpottingPhishing: React.FC = () => {
  let at = 0;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, backgroundColor: C.bg }}>
      <Background />
      {SCENES.map(({ c: Scene, d }, i) => {
        const from = at;
        at += d;
        return (
          <Sequence key={i} from={from} durationInFrames={d}>
            <Scene />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
