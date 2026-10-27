import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AiCall, errorText } from "../api";
import { useAi } from "../lib/ai";
import { nearLimit } from "../lib/aiState";
import { holdsFocus } from "../lib/focus";
import { hasRequests, requestLogHref } from "./requestLog";

/** The review header's AI pill, shown only near the review's budget (spec 2026-10-25-review-ui-redesign §2.1); it
 * opens the usage panel, as the ⋯ menu's "AI calls used" does. */
export default function AiPill() {
  const ai = useAi();
  const v = ai?.view;
  if (!ai || !v || !nearLimit(v)) return null;
  return (
    <button className="bd-pill ai-pill high" aria-expanded={ai.usageOpen} title="AI calls used on this review"
            onClick={() => ai.setUsageOpen(!ai.usageOpen)}>AI {v.used}/{v.budget}</button>
  );
}

/** The AI usage panel (spec 2026-10-03 §6): this review's and the viewer's calls; the owner raises the budget. It sits
 * under the header's right end at `top`, whoever opened it (spec 2026-10-25-review-ui-redesign §2.2), scrolling inside
 * itself rather than running past 16px above the window's bottom. Opening takes focus (so the page's J, K and F stay off
 * the page behind it); Escape or Close hands focus back to what had it then: ⋯ or the pill (or ⋯, if that has left). Escape
 * does so only while the panel holds focus: from elsewhere in the page it only closes the panel. */
export function Usage({ onClose, top }: { onClose: () => void; top: number }) {
  const ai = useAi()!;
  const v = ai.view!;
  const box = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [total, setTotal] = useState(String(v.budget + 100));
  const [rounds, setRounds] = useState(String(v.per_mention));
  const [error, setError] = useState<string | null>(null);
  const [calls, setCalls] = useState<AiCall[] | null>(null);              // loaded when the list is opened
  useEffect(() => {                           // once, when it opens; a strict-mode second run finds the opener remembered
    opener.current ??= document.activeElement as HTMLElement | null;
    box.current?.focus();
  }, []);
  const back = useCallback(() => {            // the pill is gone once a raised budget is far from its limit: then ⋯ takes focus
    onClose();
    (opener.current?.isConnected ? opener.current : document.querySelector<HTMLElement>(".rm-btn"))?.focus();
  }, [onClose]);
  useEffect(() => {                           // Escape or a press outside closes it; the pill toggles it itself
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { if (holdsFocus(box.current)) back(); else onClose(); } };
    const away = (e: PointerEvent) => {
      const t = e.target as Element;
      if (!box.current?.contains(t) && !t.closest?.(".ai-pill")) onClose();
    };
    window.addEventListener("keydown", esc);
    document.addEventListener("pointerdown", away, true);   // before the page's own handlers, which may stop it on its way
    return () => { window.removeEventListener("keydown", esc); document.removeEventListener("pointerdown", away, true); };
  }, [onClose, back]);
  const counts = (m: Record<string, number>) => Object.entries(m).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([k, n]) => `${k} ${n}`).join(" · ") || "none";
  return (
    <div className="ai-usage" role="dialog" aria-label="AI usage" tabIndex={-1} ref={box}
         style={{ top, maxHeight: `min(70vh, calc(100dvh - ${top + 16}px))` }}>
      <div className="row"><b>AI calls</b><span className="sp" /><button className="link small" onClick={back}>Close</button></div>
      <p>This review: <b>{v.used}</b> of {v.budget}. You today: <b>{v.me_today}</b> of {v.me_limit}.</p>
      {v.strong && v.tier1 && <p>Strong model ({v.strong}): <b>{v.tier1.used}</b> of {v.tier1.budget} calls for stories and
        their risk review.</p>}
      <p className="muted small">By purpose: {counts(v.by_purpose)}<br />By person: {counts(v.by_person)}</p>
      <p className="muted small">One @tortoise answer is 1 AI call of up to {v.per_mention} rounds.</p>
      {v.is_owner && (
        <form className="ai-raise" onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          api.raiseBudget(ai.reviewId, Number(total)).then(ai.refresh).catch((x) => setError(errorText(x, "The budget could not be saved.")));
        }}>
          <label>Raise budget to <input type="number" min={1} value={total} aria-label="New budget"
                                        onChange={(e) => setTotal(e.target.value)} /></label>
          <button disabled={!(Number(total) > 0)}>Raise budget</button>
        </form>
      )}
      {v.is_owner && (
        <form className="ai-raise" onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          api.setRounds(ai.reviewId, Number(rounds)).then(ai.refresh).catch((x) => setError(errorText(x, "The rounds could not be saved.")));
        }}>
          <label>Rounds per answer <input type="number" min={1} max={50} value={rounds} aria-label="Rounds per @tortoise answer"
                                          onChange={(e) => setRounds(e.target.value)} /></label>
          <button disabled={!(Number(rounds) >= 1 && Number(rounds) <= 50)}>Set rounds</button>
        </form>
      )}
      {error && <span className="ai-err">{error}</span>}
      <details onToggle={(e) => {
        if ((e.currentTarget as HTMLDetailsElement).open) api.aiCalls(ai.reviewId).then(setCalls).catch(() => setCalls([]));
      }}>
        <summary>All calls</summary>
        {calls === null && <p className="muted small">Loading…</p>}
        {hasRequests(calls) && <p className="small"><a href={requestLogHref(ai.reviewId)} download>Download request log</a></p>}
        <table className="ai-calls">
          <thead><tr><th>Time</th><th>Who</th><th>What</th><th>Model</th><th>Tokens</th><th>Outcome</th></tr></thead>
          <tbody>
            {[...(calls ?? [])].reverse().map((c) => (
              <tr key={c.id} className={c.outcome ?? ""}>
                <td>{c.started_at.replace("T", " ").slice(5, 16)}</td><td>{c.user}</td>
                <td>{c.purpose}{c.target ? ` ${c.target}` : ""}</td>
                <td>{c.model ?? "–"}</td>
                <td>{c.prompt_tokens == null ? "–" : `${c.prompt_tokens} + ${c.completion_tokens ?? 0}`}</td>
                <td title={c.error ?? undefined}>{c.outcome ?? "running"}
                  {c.requests > 0 && <> · <a href={requestLogHref(ai.reviewId, c.id)} download
                                             aria-label={`Requests of call ${c.id}`}>requests</a></>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
