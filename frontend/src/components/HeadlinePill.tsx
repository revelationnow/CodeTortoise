import type { Headline } from "../reading/types";

/** What to act on (spec 2026-10-07-review-reading §5.4): red for open hazards, amber for checks to confirm, neutral
 * otherwise; "rules only" when the strong model did not judge the risks. */
export default function HeadlinePill({ h, className = "" }: { h: Headline; className?: string }) {
  return (
    <span className={`ct-headline ${h.tone} ${className}`.trim()}
          title={h.rules_only ? "Judged by the detectors' rules, without the strong model" : undefined}>
      {h.text}{h.rules_only && <span className="ct-rules"> · rules only</span>}
    </span>
  );
}
