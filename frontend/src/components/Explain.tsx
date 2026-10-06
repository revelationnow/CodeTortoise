import { useState } from "react";
import { type AiKind, type AnchorKind, api } from "../api";
import { useAi } from "../lib/ai";
import { aiAvailability, callTitle, jobFor } from "../lib/aiState";

const REFUSED = /AI calls|AI budget/;

interface Props {
  kind: AiKind;
  target: string;
  /** The item already has an AI result: asking again replaces it, after a confirmation. */
  has: boolean;
  label?: string;
  /** Where a question typed into Ask… goes: an @tortoise thread on this item (spec: explain with a question). */
  ask?: { kind: AnchorKind; anchor: Record<string, unknown>; onAsked: () => void };
  /** Only Ask…: the item's text is the strong model's and tier 2 never rewrites it (two-tier stories §8). */
  askOnly?: boolean;
}

/** ✦ Explain / ✦ Summarise (spec 2026-10-03 §4): one AI call, shown to everyone; a refusal or failure shows here. */
export default function Explain({ kind, target, has, label = "Explain", ask, askOnly = false }: Props) {
  const ai = useAi();
  const [asking, setAsking] = useState(false);
  const [question, setQuestion] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  if (!ai?.view?.llm) return null;
  const can = aiAvailability(ai.view);
  const send = () => {
    const q = question.trim();
    if (!q || !ask) return;
    setSent(null);
    api.addComment(ai.reviewId, `@tortoise ${q}`, ask.kind, ask.anchor)
      .then(() => { setQuestion(""); setAsking(false); setSent("Asked: the answer comes in this item's thread."); ask.onAsked(); })
      .catch((x) => setSent(String(x.message ?? x)));
  };
  const job = jobFor(ai.view, kind, target);
  const running = job?.status === "running";
  const asked = ai.asked[`${kind}:${target}`];
  const failed = asked ?? (job && (job.status === "failed" || job.status === "refused")
    ? { error: job.error ?? "the AI call failed", refused: job.status === "refused" || REFUSED.test(job.error ?? "") } : null);
  const what = kind === "file" ? "summary" : "explanation";
  return (
    <span className="ai-ask" onClick={(e) => e.stopPropagation()}>
      {!askOnly && (
        <button className="ai-btn" disabled={running} title={callTitle(ai.view)}
                onClick={() => (!has || window.confirm(`Replace the current ${what}? It costs 1 AI call.`)) && ai.explain(kind, target)}>
          ✦ {running ? `${label === "Explain" ? "Explaining" : "Summarising"}…` : has ? `${label} again` : label}
        </button>
      )}
      {ask && (
        <button className="link small" aria-expanded={asking} title="Ask the AI something specific about this; it answers in a thread"
                onClick={() => setAsking(!asking)}>Ask…</button>
      )}
      {ask && asking && (
        <span className="ai-askq">
          <textarea aria-label="What should the AI explain?" rows={2} value={question} autoFocus
                    placeholder="What should it explain? @tortoise answers in a thread here."
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); }} />
          <button className="ai-btn" disabled={!question.trim() || !can.ok} title={can.detail} onClick={send}>Ask</button>
        </span>
      )}
      {sent && !asking && <span className="muted small" role="status">{sent}</span>}
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
