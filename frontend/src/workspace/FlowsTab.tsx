import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigationType } from "react-router-dom";
import { api, errorText } from "../api";
import type { BoardFlow, StoryDetail } from "../board/types";
import AiText from "../components/AiText";
import { shown } from "../reading/causes";
import { FOLD_AT, fieldOf, type FlowGroup, flowGroups, groupCauses, groupLine, groupTitle, openFlows, openKeys, placesOf,
         rowSentence } from "../reading/flowGroups";
import { flowPart } from "../reading/story";
import type { StoryReading } from "../reading/types";
import Chips from "./Chips";
import { useWs } from "./context";
import NameText, { Ticks } from "./NameText";
import { bare } from "./names";
import useRowKeys from "./useRowKeys";

const ALSO = "also";                                                           // the end line's key in `more`; a group's is "kind:node"

/** The Flows tab (spec 2026-10-25-review-ui-redesign §7): the story's flows in groups by what changed, a line each;
 * a row opens in place, and its box marks its places fine for everyone. Then the checks no group takes and what the
 * change means for the rest. One row is open at a time; `flow=N` opens row N and unfolds its group. J, K, F and Enter
 * step through the rows (§7.3). */
export default function FlowsTab({ detail, sr, flows }: { detail: StoryDetail; sr: StoryReading; flows: BoardFlow[] }) {
  const ws = useWs(), d = ws.data, lit = ws.addr.flow, marks = d.reading?.marks ?? {};
  // What the rows are made of is worked out again only when its inputs change, not on a J or a K, which change this tab's own state.
  const { nodes } = detail.board, reviewNames = d.names;
  const label = useMemo(() => {
    const names = new Map(nodes.map((n) => [n.id, n.label]));
    return (n: string) => names.get(n) ?? reviewNames[n]?.label ?? "a function";
  }, [nodes, reviewNames]);
  const groups = useMemo(() => flowGroups(flows), [flows]);
  const places = useMemo(() => placesOf(flows, sr.checks, ws.hidden, label), [flows, sr.checks, ws.hidden, label]);
  const causes = useMemo(() => shown(sr.causes ?? [], ws.hidden), [sr.causes, ws.hidden]);
  const { byGroup, rest } = useMemo(() => groupCauses(groups, causes, sr.checks, label), [groups, causes, sr.checks, label]);
  const order = useMemo(() => groups.flatMap((g) => g.rows.map((r) => r.n)), [groups]);   // the rows as they read, group by group
  const parts = sr.account ?? [], effects = parts.find((p) => p.kind === "effects");
  const [open, setOpen] = useState<number | null>(lit);
  const [more, setMore] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // settles to whether the change landed (never rejects): F says "Marked fine" only for a mark that did
  const run = (act: () => Promise<unknown>): Promise<boolean> => {
    if (busy) return Promise.resolve(false);                                   // one mark at a time; the tick boxes stay enabled, so they keep their focus
    setBusy(true);
    setError(null);
    return act().then(() => Promise.all([d.loadReading(), d.loadTicks().catch(() => {})])).then(() => true)
      .catch((e) => { setError(errorText(e, "The server did not accept the mark.")); return false; }).finally(() => setBusy(false));
  };
  const fine = (keys: string[]) => run(() => api.markChecks(d.id, keys));
  const reopen = (keys: string[]) => run(() => api.unmarkChecks(d.id, keys));  // all of them or none, so a refusal leaves the row as it was
  const leftAt = (n: number) => openKeys(places.get(flows[n - 1]?.id ?? "") ?? [], marks);
  const { cur, setCur, move, focusRow, said } = useRowKeys({ order, busy, leftAt, fine });
  // An address that names a row opens it and brings it into view, once. An outline group line names its first row even when the address
  // already holds it: `lit` then stays as it was, so the line says in its navigation state (`showFlow`) that it was clicked. Back and
  // Forward land on an entry that still carries that state and are no click; any other step that keeps the flow carries none.
  const loc = useLocation(), nav = useNavigationType();
  const show = (n: number) => { setOpen(n); setCur(n); document.getElementById(`flow-${n}`)?.scrollIntoView({ block: "start" }); };
  const named = useRef<number | null | undefined>(undefined);                  // the row the address named when last looked at
  useEffect(() => {
    const changed = lit !== named.current, clicked = nav !== "POP" && !!(loc.state as { showFlow?: boolean } | null)?.showFlow;
    named.current = lit;
    if (lit && (changed || clicked)) show(lit);                                // a click that also moves the address is one scroll, not two
  }, [lit, loc.key]);                                                          // eslint-disable-line react-hooks/exhaustive-deps
  // The buttons a click disables, replaces or removes (Looks fine, Reopen, Next flow ›, Show N more) hand their focus to a
  // row's toggle, so the keyboard is never left on the page. Next flow › opens the next row; on the last it closes its own.
  const nextFlow = (n: number) => {
    const to = order[order.indexOf(n) + 1];
    setOpen(to ?? null);
    move(to ?? n);
  };
  // only a hidden row an address, Next flow › or a key opens or reaches unfolds its group, and a group once unfolded stays so
  const unfolded = (g: FlowGroup) => g.rows.length <= FOLD_AT || more.has(g.key)
    || g.rows.slice(FOLD_AT).some((r) => r.n === lit || r.n === open || r.n === cur);
  const revealed = groups.filter((g) => g.rows.length > FOLD_AT && !more.has(g.key) && unfolded(g)).map((g) => g.key);
  if (revealed.length) setMore(new Set([...more, ...revealed]));          // remembered here, in the render that unfolds it
  // the end line folds as a group does; its Show N more hands focus to the first chip it shows, before the next paint
  const also = useRef<HTMLElement>(null), toChip = useRef(false), alsoShown = more.has(ALSO) ? rest : rest.slice(0, FOLD_AT);
  useLayoutEffect(() => {
    if (toChip.current && more.has(ALSO)) { toChip.current = false; also.current?.querySelectorAll<HTMLElement>(".st-chip")[FOLD_AT]?.focus(); }
  }, [more]);
  return (
    <div className="st-flows" aria-busy={busy}>
      <div className="vh" aria-live="polite">{said}</div>
      {error && <div className="banner warn" role="alert">{error}</div>}
      {groups.map((g) => {
        const title = groupTitle(g, label), rows = unfolded(g) ? g.rows : g.rows.slice(0, FOLD_AT);
        return (
          <section key={g.key} className="fl-group" aria-label={bare(title)}>
            <h3><Ticks text={title} /></h3>
            <p className="fl-line"><Ticks text={groupLine(g, label, openFlows(g, places, marks))} /></p>
            <Chips causes={byGroup.get(g.key) ?? []} />
            <ol className="fl-rows">{rows.map(({ flow, n }) => {
              const sentence = rowSentence(flow, label), mine = places.get(flow.id) ?? [], left = openKeys(mine, marks);
              const done = mine.length > 0 && !left.length, on = open === n, part = flowPart(parts, flow), field = fieldOf(flow);
              return (
                <li key={flow.id} id={`flow-${n}`} className={`fl-row${on ? " on" : ""}`} onFocus={() => setCur(n)}>
                  <div className="fl-head">
                    {mine.length > 0 && <label className="fl-tickbox"><input type="checkbox" className="fl-tick" checked={done}
                                               aria-label={`Looks fine: ${bare(sentence)}`}
                                               onChange={() => { setCur(n); if (done) reopen(mine.map((k) => k.key)); else fine(left); }} /></label>}
                    <button className="fl-toggle" aria-expanded={on} title={bare(sentence)} aria-label={`Flow ${n}: ${bare(sentence)}`}
                            onClick={() => { setOpen(on ? null : n); setCur(n); }}>
                      <span className="fl-n">{n}</span><span className="fl-one"><Ticks text={sentence} /></span>
                    </button>
                  </div>
                  {on && (
                    <div className="fl-body" role="region" aria-label={`Flow ${n}: ${bare(sentence)}`}>
                      <p className="fl-path mono">{flow.path.map((p, i) => (
                        <span key={i}>{i > 0 && " → "}{p === field ? <mark>{label(p)}</mark> : label(p)}</span>
                      ))}</p>
                      {part ? <AiText><NameText text={part.text} /></AiText>
                        : <AiText ai={flow.what_source === "llm"}><NameText text={flow.what} /></AiText>}
                      <p className="fl-check"><NameText text={`Check ${flow.check}`} /></p>
                      {!mine.length && <Chips causes={causes.filter((c) => c.flows.includes(flow.id))} />}
                      <div className="fl-acts">
                        {left.length > 0 && <button onClick={() => { fine(left); focusRow(n); }} disabled={busy}>Looks fine</button>}
                        {done && <button className="link" onClick={() => { reopen(mine.map((k) => k.key)); focusRow(n); }} disabled={busy}>Reopen</button>}
                        <button className="link" onClick={() => nextFlow(n)}>Next flow ›</button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}</ol>
            {rows.length < g.rows.length && (
              <button className="link fl-more" onClick={() => { setMore(new Set([...more, g.key])); move(g.rows[rows.length].n); }}>
                Show {g.rows.length - rows.length} more</button>
            )}
          </section>
        );
      })}
      {!flows.length && <p className="muted">No flows in this story.</p>}
      {rest.length > 0 && (
        <section className="st-other fl-also" aria-label="Also in this story" ref={also}><span>Also in this story:</span><Chips causes={alsoShown} />
          {alsoShown.length < rest.length && (
            <button className="link" onClick={() => { toChip.current = true; setMore(new Set([...more, ALSO])); }}>
              Show {rest.length - alsoShown.length} more</button>
          )}
        </section>
      )}
      {effects && <section className="st-effects" aria-label={effects.heading}><h3>{effects.heading}</h3>
        <AiText><NameText text={effects.text} /></AiText></section>}
    </div>
  );
}
