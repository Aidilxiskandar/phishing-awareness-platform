import { Composition } from "remotion";
import { SpottingPhishing } from "./SpottingPhishing";
import { PhishingStory, STORY_DURATION } from "./PhishingStory";
import { CastSheet } from "./mfa/CastSheet";
import { MfaShort, MFA_FRAMES } from "./mfa/Mfa";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* Character-animated phishing story (stick figure) */}
      <Composition
        id="phishing-story"
        component={PhishingStory}
        durationInFrames={STORY_DURATION}
        fps={30}
        width={1920}
        height={1080}
      />
      {/* Motion-graphics version (kept for reference) */}
      <Composition
        id="spotting-phishing"
        component={SpottingPhishing}
        durationInFrames={1830}
        fps={30}
        width={1920}
        height={1080}
      />
      {/* MFA fatigue short (three.js toon world) */}
      <Composition id="mfa-fatigue" component={MfaShort} durationInFrames={MFA_FRAMES} fps={30} width={1920} height={1080} />
      {/* MFA fatigue short: character test sheet */}
      <Composition id="mfa-cast" component={CastSheet} durationInFrames={1} fps={30} width={3200} height={2400} />
    </>
  );
};
