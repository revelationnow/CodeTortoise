import { useState } from "react";
import { type AiKind, type AnchorKind, api } from "../api";
import { useAi } from "../lib/ai";
import { aiAvailability, callTitle, jobFor } from "../lib/aiState";
import { useMenu } from "../lib/useMenu";
import AiText from "./AiText";

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

/** Explain ▾ (spec 2026-10-25-review-ui-redesign §4.1): a small menu of Explain — or the caller's label, "again" once
 * the item has a result — and Ask a question…; one AI call, shown to everyone. An item the strong model wrote allows
 * only Ask… (two-tier stories §8). A refusal or failure, and the sent note, show beside it. */
export default function Explain({ kind, target, has, label = "Explain", ask, askOnly = false }: Props) {
  const ai = useAi();
  const [asking, setAsking] = useState(false);
  const [question, setQuestion] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const { button, menu } = useMenu<HTMLSpanElement>(open, () => setOpen(false));
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
  const doing = `${label === "Explain" ? "Explaining" : "Summarising"}…`;
  const run = () => {
    setOpen(false);
    button.current?.focus();
    if (!has || window.confirm(`Replace the current ${what}? It costs 1 AI call.`)) ai.explain(kind, target);
  };
  return (
    <span className="ai-ask" onClick={(e) => e.stopPropagation()}>
      {askOnly ? ask && (
        <button className="ai-btn" aria-expanded={asking} title="Ask the AI something specific about this; it answers in a thread"
                onClick={() => setAsking(!asking)}>Ask…</button>
      ) : (
        <span className="ai-menuwrap">
          <button ref={button} className="ai-btn" aria-haspopup="menu" aria-expanded={open} title="Ask the AI about this"
                  onClick={() => setOpen(!open)}>{running ? doing : label}<span aria-hidden> ▾</span></button>
          {open && (
            <span className="ai-menu" role="menu" aria-label={label} ref={menu}>
              <button role="menuitem" disabled={running} title={callTitle(ai.view)} onClick={run}>
                {running ? doing : has ? `${label} again` : label}</button>
              {ask && <button role="menuitem" onClick={() => { setOpen(false); setAsking(true); }}>Ask a question…</button>}
            </span>
          )}
        </span>
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

/** A file's AI summary, above its code (spec 2026-10-25-review-ui-redesign §4): the edge, and its model on hover. */
export function FileSummaryView({ path }: { path: string }) {
  const s = useAi()?.view?.file_summaries[path];
  if (!s || !s.summary) return null;
  return (
    <AiText as="div" by={s.by} className="ai-summary">
      <h4>Summary</h4>
      <p>{s.summary}</p>
      {s.check.length > 0 && <><b>Check</b><ol>{s.check.map((c, i) => <li key={i}>{c}</li>)}</ol></>}
    </AiText>
  );
}
