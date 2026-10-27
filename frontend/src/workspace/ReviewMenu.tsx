import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../api";
import { useMe } from "../App";
import { driftSummary } from "../board/drift";
import { useAi } from "../lib/ai";
import { holdsFocus } from "../lib/focus";
import { useMenu } from "../lib/useMenu";
import { useWs } from "./context";
import HowToRead from "./HowToRead";
import { menuAttention, type MenuId, menuItems, type MenuState } from "./reviewMenu";
import { setShortcutsOn, shortcutsOn } from "./shortcuts";

const FRESH = "Ask the strong model for new stories instead of reusing the ones it formed for this change";

/** What a stage note says after the stage's name: ": the message", or nothing for a stage with nothing to say (a degraded
 * one can come without a word), so its name is not left with a colon after it. */
const said = (message: string) => (message.trim() ? `: ${message}` : "");

/** The header's ⋯ menu (spec 2026-10-25-review-ui-redesign §2.2): drift, stage notes, AI usage, the help, the single-key
 * shortcuts switch and the owner's re-runs, with an amber dot when the workspace drifted or a stage failed. The switch is a
 * checkbox item kept in this browser (`shortcuts.ts`): a pick flips it, closes the menu and gives focus back to ⋯. The menu
 * and its panels are fixed under the header's right end (`under()`), since the header itself scrolls; a re-run the server
 * refuses is told in a panel of its own, whose message is an alert and which takes focus only from ⋯ or the page (the answer
 * may come when the reader is writing a comment). Escape gives focus back to ⋯ only while the panel holds it. */
export default function ReviewMenu({ under }: { under: () => number }) {
  const ws = useWs(), d = ws.data, me = useMe(), ai = useAi();
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"drift" | "notes" | "help" | "rerun" | null>(null);
  const [failed, setFailed] = useState("");                  // why the last re-run did not start
  const [keysOn, setKeysOn] = useState(shortcutsOn);          // the single-key shortcuts switch, read again each time the menu opens
  const [top, setTop] = useState(56);
  const { button, menu } = useMenu<HTMLUListElement>(open, () => setOpen(false));
  const box = useRef<HTMLDivElement>(null);
  const drift = driftSummary(d.about?.drift ?? []).warn;
  const notes = d.detail!.stages.filter((s) => s.status === "failed" || s.status === "degraded");
  const v = ai?.view;
  const state: MenuState = {
    drift: drift.length, notes: { failed: notes.filter((s) => s.status === "failed").length,
                                  degraded: notes.filter((s) => s.status === "degraded").length },
    ai: v?.llm ? { used: v.used, budget: v.budget } : null, reading: !!d.reading, keys: keysOn,
    owner: !!me?.is_owner, ready: d.ready, strong: !!v?.strong };
  const items = menuItems(state), why = menuAttention(state);
  const at = { top, maxHeight: `calc(100dvh - ${top + 16}px)` };   // the menu or a panel scrolls inside itself rather than run past 16px above the window's bottom; dvh is the window a phone's browser bars leave
  useEffect(() => {                           // an open panel takes focus, follows the header when the window resizes, and closes on Escape or a press outside
    if (!panel) return;
    const focused = document.activeElement;  // one that opens late (a failed re-run) leaves focus where the reader has gone on to
    if (!focused || focused === document.body || focused === button.current) box.current?.querySelector<HTMLElement>('[role="dialog"]')?.focus();
    const place = () => setTop(under());
    const esc = (e: KeyboardEvent) => {      // back to ⋯ only from inside the panel: a reader who has gone on keeps focus where it is
      if (e.key !== "Escape") return;
      const held = holdsFocus(box.current);
      setPanel(null);
      if (held) button.current?.focus();
    };
    const away = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!box.current?.contains(t) && !button.current?.contains(t)) setPanel(null);
    };
    window.addEventListener("resize", place);
    document.addEventListener("keydown", esc);
    document.addEventListener("pointerdown", away, true);   // before the page's own handlers, which may stop it on its way
    return () => { window.removeEventListener("resize", place); document.removeEventListener("keydown", esc);
                   document.removeEventListener("pointerdown", away, true); };
  }, [panel, under, button]);
  if (!items.length) return null;
  const pick = (id: MenuId) => {
    setOpen(false);
    if (id === "drift" || id === "notes" || id === "help") { setPanel(id); return; }
    button.current?.focus();
    if (id === "keys") { setShortcutsOn(!keysOn); setKeysOn(shortcutsOn()); }   // shows what the keys will do, which blocked storage keeps on
    else if (id === "ai") ai?.setUsageOpen(true);
    else api.rerun(d.id, id === "fresh").then(d.loadDetail).catch((e) => {
      setFailed(errorText(e, "The server did not accept the re-run."));
      setPanel("rerun");
    });
  };
  return (
    <div className="rm">
      <button ref={button} className="rm-btn" aria-label={why ? `Review menu (${why})` : "Review menu"} title="Review menu"
              aria-haspopup="menu" aria-expanded={open}
              onClick={() => { setTop(under()); setPanel(null); setKeysOn(shortcutsOn()); setOpen(!open); }}>
        ⋯{why && <span className="rm-dot" aria-hidden />}
      </button>
      {open && (
        <ul className="rm-menu" role="menu" aria-label="Review menu" ref={menu} style={at}>
          {items.map((it) => (
            <li key={it.id} role="none">
              <button role={it.checked === undefined ? "menuitem" : "menuitemcheckbox"} aria-checked={it.checked}
                      title={it.id === "fresh" ? FRESH : undefined} onClick={() => pick(it.id)}>
                {(it.id === "drift" || (it.id === "notes" && state.notes.failed > 0)) && <span className="rm-amber" aria-hidden />}
                {it.label}
                {it.checked !== undefined && <span className="rm-check" aria-hidden>{it.checked ? "✓" : ""}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div ref={box}>
        {panel === "drift" && (
          <div className="rm-panel" role="dialog" aria-label="Workspace drift" tabIndex={-1} style={at}>
            <h2>Workspace drift</h2>
            <p className="muted small">The workspace differs from the change in these files; what the review says about them may be off.</p>
            <ul className="mono small">{drift.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
        )}
        {panel === "notes" && (
          <div className="rm-panel" role="dialog" aria-label="Stage notes" tabIndex={-1} style={at}>
            <h2>Stage notes</h2>
            {notes.map((s) => <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>{said(s.message)}</div>)}
          </div>
        )}
        {panel === "rerun" && (
          <div className="rm-panel" role="dialog" aria-label="Re-run failed" tabIndex={-1} style={at}>
            <h2>Re-run failed</h2>
            <div className="banner error" role="alert">{failed}</div>
          </div>
        )}
        {panel === "help" && <HowToRead top={top} />}
      </div>
    </div>
  );
}
