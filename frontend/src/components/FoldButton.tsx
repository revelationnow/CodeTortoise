/** What a fold control does: grow upward or downward from the edge it sits on (the bar is that edge), open every hidden
 * line, run to the file's top or bottom, or list the rest of a column. */
export type Fold = "up" | "down" | "all" | "top" | "bottom" | "more";

const PATHS: Record<Fold, string[]> = {
  up: ["M3 13.5h10", "M8 11V3", "M4.5 6.5 8 3l3.5 3.5"],
  down: ["M3 2.5h10", "M8 5v8", "M4.5 9.5 8 13l3.5-3.5"],
  all: ["M8 1.5v4.5", "M5.5 4 8 1.5 10.5 4", "M8 14.5V10", "M5.5 12 8 14.5 10.5 12", "M2.5 8h11"],
  top: ["M3 2.5h10", "M4.5 9 8 5.5 11.5 9", "M4.5 13 8 9.5 11.5 13"],
  bottom: ["M3 13.5h10", "M4.5 3 8 6.5 11.5 3", "M4.5 7 8 10.5 11.5 7"],
  more: ["M4.5 3.5 8 7l3.5-3.5", "M4.5 8.5 8 12l3.5-3.5"],
};

/** An icon-only fold control; `label` is its tooltip and its accessible name. */
export default function FoldButton({ icon, label, onClick }: { icon: Fold; label: string; onClick: () => void }) {
  return (
    <button type="button" className="fold-btn" title={label} aria-label={label} onClick={onClick}>
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.7"
           strokeLinecap="round" strokeLinejoin="round">
        {PATHS[icon].map((d, i) => <path key={i} d={d} strokeDasharray={icon === "all" && i === 4 ? "1.5 2.2" : undefined} />)}
      </svg>
    </button>
  );
}
