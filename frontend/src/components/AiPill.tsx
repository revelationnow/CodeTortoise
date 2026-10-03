import { useEffect, useState } from "react";
import { api } from "../api";
import { useAi } from "../lib/ai";

/** The review header's AI pill and its usage view; the owner can raise the review's budget (spec 2026-10-03 §6). */
export default function AiPill() {
  const ai = useAi();
  const v = ai?.view;
  if (!ai || !v || !v.llm) return null;
  const low = v.used >= v.budget * 0.9;
  return (
    <span className="ai-pillwrap">
      <button className={`bd-pill ai-pill${low ? " high" : " ghost"}`} aria-expanded={ai.usageOpen}
              title="AI calls used on this review" onClick={() => ai.setUsageOpen(!ai.usageOpen)}>
        AI {v.used}/{v.budget}
      </button>
      {ai.usageOpen && <Usage onClose={() => ai.setUsageOpen(false)} />}
    </span>
  );
}

function Usage({ onClose }: { onClose: () => void }) {
  const ai = useAi()!;
  const v = ai.view!;
  const [total, setTotal] = useState(String(v.budget + 100));
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const counts = (m: Record<string, number>) => Object.entries(m).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([k, n]) => `${k} ${n}`).join(" · ") || "none";
  return (
    <div className="ai-usage" role="dialog" aria-label="AI usage">
      <div className="row"><b>AI calls</b><span className="sp" /><button className="link small" onClick={onClose}>Close</button></div>
      <p>This review: <b>{v.used}</b> of {v.budget}. You today: <b>{v.me_today}</b> of {v.me_limit}.</p>
      <p className="muted small">By purpose: {counts(v.by_purpose)}<br />By person: {counts(v.by_person)}</p>
      {v.is_owner && (
        <form className="ai-raise" onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          api.raiseBudget(ai.reviewId, Number(total)).then(ai.refresh).catch((x) => setError(String(x.message ?? x)));
        }}>
          <label>Raise budget to <input type="number" min={1} value={total} aria-label="New budget"
                                        onChange={(e) => setTotal(e.target.value)} /></label>
          <button disabled={!(Number(total) > 0)}>Raise budget</button>
          {error && <span className="ai-err">{error}</span>}
        </form>
      )}
      <details>
        <summary>All calls ({v.calls.length})</summary>
        <table className="ai-calls">
          <thead><tr><th>Time</th><th>Who</th><th>What</th><th>Tokens</th><th>Outcome</th></tr></thead>
          <tbody>
            {[...v.calls].reverse().map((c) => (
              <tr key={c.id} className={c.outcome ?? ""}>
                <td>{c.started_at.replace("T", " ").slice(5, 16)}</td><td>{c.user}</td>
                <td>{c.purpose}{c.target ? ` ${c.target}` : ""}</td>
                <td>{c.prompt_tokens == null ? "–" : `${c.prompt_tokens} + ${c.completion_tokens ?? 0}`}</td>
                <td title={c.error ?? undefined}>{c.outcome ?? "running"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
