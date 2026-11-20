import { Composition } from "remotion";
import { SpottingPhishing } from "./SpottingPhishing";
import { PhishingStory, STORY_DURATION } from "./PhishingStory";

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
    </>
  );
};
