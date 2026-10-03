import type { AiKind } from "../api";
import { useAi } from "../lib/ai";
import { callTitle, jobFor } from "../lib/aiState";

const REFUSED = /AI calls|AI budget/;

interface Props {
  kind: AiKind;
  target: string;
  /** The item already has an AI result: asking again replaces it, after a confirmation. */
  has: boolean;
  label?: string;
}

/** ✦ Explain / ✦ Summarise (spec 2026-10-03 §4): one AI call, shown to everyone; a refusal or failure shows here. */
export default function Explain({ kind, target, has, label = "Explain" }: Props) {
  const ai = useAi();
  if (!ai?.view?.llm) return null;
  const job = jobFor(ai.view, kind, target);
  const running = job?.status === "running";
  const asked = ai.asked[`${kind}:${target}`];
  const failed = asked ?? (job && (job.status === "failed" || job.status === "refused")
    ? { error: job.error ?? "the AI call failed", refused: job.status === "refused" || REFUSED.test(job.error ?? "") } : null);
  const what = kind === "file" ? "summary" : "explanation";
  return (
    <span className="ai-ask" onClick={(e) => e.stopPropagation()}>
      <button className="ai-btn" disabled={running} title={callTitle(ai.view)}
              onClick={() => (!has || window.confirm(`Replace the current ${what}? It costs 1 AI call.`)) && ai.explain(kind, target)}>
        ✦ {running ? `${label === "Explain" ? "Explaining" : "Summarising"}…` : has ? `${label} again` : label}
      </button>
      {failed && !running && (
        <span className="ai-err" role="alert">
          {failed.error}
          {failed.refused && ai.view.is_owner && (
            <button className="link small" onClick={() => ai.setUsageOpen(true)}>Raise budget</button>
          )}
        </span>
      )}
    </span>
  );
}

/** A file's AI summary, above its code. */
export function FileSummaryView({ path }: { path: string }) {
  const s = useAi()?.view?.file_summaries[path];
  if (!s || !s.summary) return null;
  return (
    <div className="ai-summary">
      <div className="ai-tag"><span className="ai-label">AI</span> summary by {s.by}</div>
      <p>{s.summary}</p>
      {s.check.length > 0 && <><b>Check</b><ol>{s.check.map((c, i) => <li key={i}>{c}</li>)}</ol></>}
    </div>
  );
}
