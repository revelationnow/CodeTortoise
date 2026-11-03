import { useState } from "react";
import { api, ApiError, errorText } from "../api";
import { useAi } from "../lib/ai";
import { callTitle, jobFor } from "../lib/aiState";
import { useMenu } from "../lib/useMenu";
import { partSource, rewriteItems } from "../reading/design";
import type { ReadingDesign } from "../reading/types";
import { useViewer } from "../viewer";
import { useWs } from "./context";

const REFUSED = /AI calls|AI budget/;
const MAX_INSTRUCTION = 300;                     // as the server takes it

/** Rewrite ▾ (spec 2026-11-02 §10, §12.3): the AI menu of one part of the design overview, in Explain ▾'s shape.
 * Rewrite asks the strong model for the part again, after a confirmation; Rewrite with an instruction… opens a box whose
 * words go into the prompt (Ask sends them, Ctrl+Enter too; Escape shuts it). The review's owner pins the words, so later
 * runs of the design stage keep them, or unpins them. A rewrite is one AI call, shown to everyone once it lands; a pinned
 * part is not rewritten. A refusal or a failure shows beside the menu. */
export default function RewriteMenu({ part, what }: { part: string; what: string }) {
  const ai = useAi(), ws = useWs(), me = useViewer();
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const [words, setWords] = useState("");
  const [error, setError] = useState<{ text: string; refused: boolean } | null>(null);
  const { button, menu } = useMenu<HTMLSpanElement>(open, () => setOpen(false));
  const d = ws.data.reading?.design;
  if (!ai?.view?.strong || !d) return null;
  const view = ai.view, items = rewriteItems(d, part, !!me?.is_owner);
  const job = jobFor(view, "design", part), running = job?.status === "running";
  const failed = error ?? (job && (job.status === "failed" || job.status === "refused")
    ? { text: job.error ?? "the AI call failed", refused: job.status === "refused" || REFUSED.test(job.error ?? "") } : null);
  const shut = () => { setAsking(false); button.current?.focus(); };
  const rewrite = (instruction: string) => {
    setError(null);
    api.rewriteDesign(ws.data.id, part, instruction)
      .then(() => { if (instruction) { setWords(""); shut(); } })
      .catch((e) => setError({ text: errorText(e, "The rewrite could not be started."),
                               refused: e instanceof ApiError && e.status === 429 }))
      .finally(() => ai.refresh());
  };
  const pin = (on: boolean) => {
    setOpen(false);
    setError(null);
    api.pinDesign(ws.data.id, part, on).then(() => ws.data.loadReading())
      .catch((e) => setError({ text: errorText(e, on ? "The words could not be pinned." : "The words could not be unpinned."),
                               refused: false }));
  };
  // title="": nothing here is the AI's text; an empty title keeps the hover of whatever surrounds these controls off them
  return (
    <span className="ai-ask dz-rewrite" title="" onClick={(e) => e.stopPropagation()}>
      <span className="ai-menuwrap">
        <button ref={button} className="ai-btn" aria-haspopup="menu" aria-expanded={open}
                title={`Ask the AI to write the ${what} again`} onClick={() => setOpen(!open)}>
          {running ? "Rewriting…" : "Rewrite"}<span aria-hidden> ▾</span></button>
        {open && (
          <span className="ai-menu" role="menu" aria-label="Rewrite" ref={menu}>
            <button role="menuitem" disabled={running || !items.rewrite} title={items.why || callTitle(view)}
                    onClick={() => {
                      setOpen(false);
                      button.current?.focus();
                      if (window.confirm(`Replace the ${what}? It costs 1 AI call.`)) rewrite("");
                    }}>Rewrite</button>
            <button role="menuitem" disabled={running || !items.rewrite} title={items.why || callTitle(view)}
                    onClick={() => { setOpen(false); setAsking(true); }}>Rewrite with an instruction…</button>
            {items.pin && (
              <button role="menuitem" disabled={running} onClick={() => pin(items.pin === "pin")}>
                {items.pin === "pin" ? "Pin this text" : "Unpin"}</button>
            )}
          </span>
        )}
      </span>
      {asking && (
        <span className="ai-askq">
          <textarea aria-label="How should the AI rewrite it?" rows={2} value={words} autoFocus maxLength={MAX_INSTRUCTION}
                    placeholder="Shorter, or say what it leaves out…" onChange={(e) => setWords(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && words.trim() && !running) rewrite(words.trim());
                      else if (e.key === "Escape") { e.preventDefault(); shut(); }
                    }} />
          <button className="ai-btn" disabled={!words.trim() || running} title={callTitle(view)}
                  onClick={() => rewrite(words.trim())}>Ask</button>
        </span>
      )}
      {failed && !running && (
        <span className="ai-err" role="alert">
          {failed.text}
          {failed.refused && view.is_owner && <button className="link small" onClick={() => ai.setUsageOpen(true)}>Raise budget</button>}
        </span>
      )}
    </span>
  );
}

/** A part's source line and its AI menu (§3.1 item 2, §12.3), on one row: the menu at the row's end. */
export function SourceRow({ d, part, what }: { d: ReadingDesign; part: string; what: string }) {
  return (
    <div className="dz-srcrow">
      <p className="dz-src">{partSource(d, part)}</p>
      <RewriteMenu part={part} what={what} />
    </div>
  );
}
