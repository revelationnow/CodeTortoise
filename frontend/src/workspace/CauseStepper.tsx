import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { isChange, useEnsureSource } from "../board/useSources";
import Comments from "../components/Comments";
import SinkMark from "../components/SinkMark";
import { KIND_LABEL, markLine } from "../reading/checks";
import { alsoAt, around, doneCount, nextOpenAt, openPlaces, placeOpen } from "../reading/causes";
import type { Cause, Check, Mark } from "../reading/types";
import { useWs } from "./context";
import { inPopup, typing } from "./keys";
import NameText, { Ticks } from "./NameText";
import { bare, plainNames } from "./names";

/** About seven lines around the place, from the after text of a changed file or the fetched text of another. */
function PlaceCode({ k }: { k: Check | null }) {
  const ws = useWs();
  const state = useEnsureSource(k?.depot ?? null, ws.sources);
  if (!k?.depot || k.line === null) return <p className="muted small">No code for this place.</p>;
  if (state === undefined || ("status" in state && state.status === "loading")) return <p className="muted small">Fetching the code…</p>;
  const text = isChange(state) ? state.after : "status" in state && state.status === "ok" ? state.file.text : null;
  const lines = text === null ? [] : around(text, k.line);
  if (!lines.length) return <p className="muted small">No code for this place.</p>;
  return (
    <pre className="cs-code">{lines.map((l) => (
      <div key={l.line} className={l.at ? "at" : undefined}><span className="cs-ln" aria-hidden>{l.line}</span>{l.text}</div>
    ))}</pre>
  );
}

/** The cause stepper (spec 2026-10-16-outline-and-causes §4.3): the cause's line and where the reader is among its
 * places; the change that raised it, always; the place with a few lines of code; Looks fine & next, Comment, Back and
 * Skip. Stepping onto a place ticks it read for this reader. */
export default function CauseStepper({ cause, at }: { cause: Cause; at: number }) {
  const ws = useWs(), d = ws.data, r = d.reading!, marks = r.marks;
  const checks = useMemo(() => new Map(r.checks.map((k) => [k.key, k])), [r.checks]);
  const n = cause.places.length, i = Math.min(Math.max(at, 1), n), key = cause.places[i - 1];
  const k = checks.get(key) ?? null, m = marks[key], open = placeOpen(key, marks);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [talk, setTalk] = useState(false);
  const { ticks, tick } = d;
  useEffect(() => {                                       // a new place: its comment box closed, no banner, its tick set
    setTalk(false);
    setError(null);
    if (ticks && !ticks.checks.includes(key)) tick("check", key, true).catch(() => { /* the tick is a courtesy */ });
  }, [key]);                                              // eslint-disable-line react-hooks/exhaustive-deps
  const go = (to: number) => ws.go({ ...ws.addr, open: { cause: cause.id, at: to } }, true);
  const left = openPlaces(cause, marks), done = doneCount(cause, marks);
  const ahead = nextOpenAt(cause, marks, i, 1), behind = nextOpenAt(cause, marks, i, -1);
  const run = (act: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    act().catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
  };
  const reload = () => Promise.all([d.loadReading(), d.loadTicks().catch(() => {})]).then(() => {});
  const fineNext = () => run(async () => {
    await api.markCheck(d.id, key);
    await reload();
    const now: Record<string, Mark> = { ...marks, [key]: { key, user: "", at: "", source_line: "", changed: false } };
    const to = nextOpenAt(cause, now, i, 1);
    if (to !== null) go(to);
  });
  const reopen = () => run(async () => { await api.unmarkCheck(d.id, key); await reload(); });
  const allFine = () => run(async () => { await api.markChecks(d.id, left); await reload(); });
  // the handler is read from a ref set in the render, so a key pressed before React's effects flush meets this render
  const onKey = useRef<(e: KeyboardEvent) => void>(() => {});
  onKey.current = (e) => {
    // while a mark is on its way J, K and F wait: its "next" is worked out from the place it was made at; they are a menu's
    // or a dialog's while one has focus; and F acts once per press, as a held key's repeats would clear place after place
    if (busy || e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || inPopup(e.target)) return;
    if (e.key === "j" && ahead !== null) { e.preventDefault(); go(ahead); }
    else if (e.key === "k" && behind !== null) { e.preventDefault(); go(behind); }
    else if (e.key === "f" && !e.repeat && open) { e.preventDefault(); fineNext(); }
  };
  useLayoutEffect(() => {                                 // heard from the commit that shows the stepper, not from the next paint
    const on = (e: KeyboardEvent) => onKey.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
  const ch = cause.change, first = ch?.lines.find((l) => l.sign === "+")?.line ?? ch?.lines[0]?.line ?? null;
  const place = k ? `${k.path}${k.line ? `:${k.line}` : ""}` : "";
  const also = k ? alsoAt(r.causes ?? [], checks, cause, key) : [];
  const talks = d.comments.filter((c) => c.parent_id === null && c.anchor_kind === "check" && c.anchor.key === key).length;
  return (
    <div className="cs">
      <div className="cs-head">
        <p className="cs-line"><span className={`ck-tag ${cause.kind}`}>{KIND_LABEL[cause.kind]}</span> <NameText text={cause.text} /></p>
        <div className="cs-nav">
          <button className="bd-ibtn" aria-label="Previous place" title="Previous place" disabled={i <= 1} onClick={() => go(i - 1)}>‹</button>
          <span className="cs-pos">{i} / {n}</span>
          <button className="bd-ibtn" aria-label="Next place" title="Next place" disabled={i >= n} onClick={() => go(i + 1)}>›</button>
          <span className="muted small cs-donecount">{done} done</span>
          <button className="cs-all" onClick={allFine} disabled={busy || !left.length}>All look fine</button>
        </div>
      </div>
      {ch && ch.lines.length > 0 && (
        <section className="cs-change" aria-label="The change">
          <h3>The change{ch.function && <> · <span className="mono">{ch.function}</span></>} · <span className="mono">{ch.path}{first ? `:${first}` : ""}</span></h3>
          <pre className="cs-diff">{ch.lines.map((l, j) => (
            <div key={j} className={l.sign === "+" ? "add" : l.sign === "-" ? "del" : undefined}><span className="cs-sign" aria-hidden>{l.sign}</span>{l.text}</div>
          ))}</pre>
          {ch.depot && <Link className="small" to={ws.link(ws.opened({ file: ch.depot, line: first }))}>Open the whole diff</Link>}
        </section>
      )}
      <section className="cs-place" aria-label="The place">
        <h3>Place {i} / {n}{k?.function && <> · <span className="mono">{k.function}</span></>}{place && <> · <span className="mono">{place}</span></>}</h3>
        {k && n > 1 && <p className="cs-row-text"><NameText text={k.text} /></p>}
        <PlaceCode k={k} />
        {k?.depot && <Link className="small" to={ws.link(ws.opened({ file: k.depot, line: k.line }))}
                           aria-label={`Open ${k.path}${k.line ? ` at line ${k.line}` : ""}`}>Open the file</Link>}
        {also.length > 0 && <p className="cs-also">also: {also.map((o, j) => {
          const line = plainNames(o.cause.text, d.names);
          return <span key={o.cause.id}>{j > 0 && " · "}<Link to={ws.link(ws.opened({ cause: o.cause.id, at: o.at }))}
                                                             aria-label={`Open check: ${bare(line)}`}><Ticks text={line} /></Link></span>;
        })}</p>}
        {m && <div className={`ck-mark${m.changed ? " changed" : ""}`}>{markLine(m)}</div>}
      </section>
      <div className="cs-acts">
        {open ? <button onClick={fineNext} disabled={busy}>Looks fine &amp; next</button>
          : <button className="link" onClick={reopen} disabled={busy}>Reopen</button>}
        <button className="link" onClick={() => setTalk(!talk)} aria-expanded={talk}>Comment{talks ? ` (${talks})` : ""}</button>
        <button className="link" onClick={() => behind !== null && go(behind)} disabled={behind === null}>‹ Back</button>
        <button className="link" onClick={() => ahead !== null && go(ahead)} disabled={ahead === null}>Skip ›</button>
        {cause.finding && <Link to={ws.link(ws.opened({ finding: cause.finding }))} title={`Finding ${cause.finding}'s details`}
                                aria-label={`Finding ${cause.finding}'s details`}>Details</Link>}
        {k?.kind === "reader" && k.field && <SinkMark label={k.field} />}
      </div>
      {!left.length && <p className="cs-done">{n === 1 ? "Its place is done" : `All ${n} places done`}</p>}
      {error && <div className="banner warn">{error}</div>}
      {talk && <Comments reviewId={d.id} comments={d.comments} kind="check" anchor={{ key }} onChange={d.loadComments} autoFocus />}
    </div>
  );
}
