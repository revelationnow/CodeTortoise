import { type ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Comments from "../components/Comments";
import { isOpen, KIND_LABEL, markLine, openCount, placeOf, splitChecks } from "../reading/checks";
import type { Check } from "../reading/types";
import { at } from "./address";
import { useWs } from "./context";
import { Ticks } from "./NameText";

/** One To check row (spec 2026-10-07-review-reading §7.2): kind, one line, the place and its source line; Looks fine,
 * Comment and Open. A row someone marked shows who and when, greyed; a changed line reopens it. */
function CheckRow({ k, lit }: { k: Check; lit: boolean }) {
  const ws = useWs(), d = ws.data, m = d.reading?.marks[k.key];
  const [talk, setTalk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const marked = !!m && !m.changed;
  const toggle = () => {
    setBusy(true);
    setError(null);
    (marked ? api.unmarkCheck(d.id, k.key) : api.markCheck(d.id, k.key)).then(d.loadReading)
      .catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
  };
  const li = useRef<HTMLLIElement>(null);
  useEffect(() => { if (lit) li.current?.scrollIntoView({ block: "center" }); }, [lit]);
  const talks = d.comments.filter((c) => c.parent_id === null && c.anchor_kind === "check" && c.anchor.key === k.key).length;
  const where = placeOf(k), place = `${k.path}${k.line ? ` at line ${k.line}` : ""}`;
  return (
    <li ref={li} className={`ck-row${marked ? " marked" : ""}${lit ? " lit" : ""}`} data-key={k.key} data-finding={k.finding ?? undefined}>
      {[{ kind: k.kind, text: k.text }, ...k.also].map((r, i) => (
        <div key={i} className="ck-top"><span className={`ck-tag ${r.kind}`}>{KIND_LABEL[r.kind]}</span>
          <span className="ck-text"><Ticks text={r.text} /></span></div>
      ))}
      {where && <div className="ck-place mono"><Ticks text={where} /></div>}
      {k.source_line && <code className="ck-src">{k.source_line}</code>}
      {m && <div className={`ck-mark${m.changed ? " changed" : ""}`}>{markLine(m)}</div>}
      <div className="ck-acts">
        <button className="link" onClick={toggle} disabled={busy} aria-pressed={marked}>{marked ? "Reopen" : "Looks fine"}</button>
        <button className="link" onClick={() => setTalk(!talk)} aria-expanded={talk}>Comment{talks ? ` (${talks})` : ""}</button>
        {k.depot && <Link to={ws.link(ws.opened({ file: k.depot, line: k.line }))} title={`Open ${place}`} aria-label={`Open ${place}`}>Open</Link>}
        {k.finding && <Link to={ws.link(at({ kind: "finding", fid: k.finding }, { details: true }))} title={`Finding ${k.finding}'s details`}
                            aria-label={`Finding ${k.finding}'s details`}>Details</Link>}
      </div>
      {error && <div className="banner warn">{error}</div>}
      {talk && <Comments reviewId={d.id} comments={d.comments} kind="check" anchor={{ key: k.key }} onChange={d.loadComments} autoFocus />}
    </li>
  );
}

export interface CheckGroup { label: string | null; checks: Check[] }

/** A To check tile: open rows first, marked ones below; the overview's grouped by thread with "5 open" (§5.2), a story's
 * with "3 of 5 open" (§6.2). On a phone it comes first, folded to its count, unless it holds the finding an old
 * address leads to: that row is lit. */
/** The findings the strong model judged no hazard (§7.1), folded under their count with their reasons. */
export function Cleared({ checks }: { checks: Check[] }) {
  if (!checks.length) return null;
  return (
    <details className="ck-cleared">
      <summary>{checks.length} check{checks.length === 1 ? "" : "s"} found no hazard</summary>
      <ul>{checks.map((k) => (
        <li key={k.key}><Ticks text={k.text} />{placeOf(k) && <span className="mono small"> · <Ticks text={placeOf(k)} /></span>}</li>
      ))}</ul>
    </details>
  );
}

export default function CheckTile({ groups, ofTotal, footer, id }:
  { groups: CheckGroup[]; ofTotal: boolean; footer?: ReactNode; id?: string }) {
  const ws = useWs(), marks = ws.data.reading?.marks ?? {}, lit = ws.addr.check ?? null;
  const all = groups.flatMap((g) => g.checks);
  const count = openCount(all.filter((k) => isOpen(k, marks)).length, all.length, ofTotal);
  const head = <>To check{count && <span className="ck-count">{count}</span>}</>;
  const body = <>
    {all.length === 0 && <p className="muted small">Nothing to check.</p>}
    {groups.map((g) => {
      const { open, marked } = splitChecks(g.checks, marks);
      return (
        <div key={g.label ?? ""} className="ck-group">
          {g.label && <h4><Ticks text={g.label} /></h4>}
          <ul className="ck-list">{[...open, ...marked].map((k) => <CheckRow key={k.key} k={k} lit={!!lit && k.finding === lit} />)}</ul>
        </div>
      );
    })}
    {footer}
  </>;
  return ws.screen === "phone"
    ? <details className="ws-tile ck-tile" aria-label="To check" id={id} open={!!lit || undefined}><summary><h3>{head}</h3></summary>{body}</details>
    : <section className="ws-tile ck-tile" aria-label="To check" id={id}><h3>{head}</h3>{body}</section>;
}
