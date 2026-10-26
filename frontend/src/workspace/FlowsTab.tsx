import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { BoardFlow, StoryDetail } from "../board/types";
import AiText from "../components/AiText";
import { shown } from "../reading/causes";
import { FOLD_AT, fieldOf, type FlowGroup, flowGroups, groupCauses, groupLine, groupTitle, openFlows, openKeys, placesOf,
         rowSentence } from "../reading/flowGroups";
import { flowPart } from "../reading/story";
import type { StoryReading } from "../reading/types";
import Chips from "./Chips";
import { useWs } from "./context";
import { typing } from "./keys";
import NameText, { Ticks } from "./NameText";

const bare = (s: string) => s.replaceAll("`", "");

/** The Flows tab (spec 2026-10-25-review-ui-redesign §7): the story's flows in groups by what changed, a line each;
 * a row opens in place, and its box marks its places fine for everyone. Then the checks no group takes and what the
 * change means for the rest. One row is open at a time; `flow=N` opens row N and unfolds its group. J, K, F and Enter
 * step through the rows (§7.3). */
export default function FlowsTab({ detail, sr, flows }: { detail: StoryDetail; sr: StoryReading; flows: BoardFlow[] }) {
  const ws = useWs(), d = ws.data, lit = ws.addr.flow, marks = d.reading?.marks ?? {};
  const names = new Map(detail.board.nodes.map((n) => [n.id, n.label]));
  const label = (n: string) => names.get(n) ?? d.names[n]?.label ?? "a function";
  const groups = flowGroups(flows), places = placesOf(flows, sr.checks, ws.hidden, label);
  const causes = shown(sr.causes ?? [], ws.hidden), { byGroup, rest } = groupCauses(groups, causes, sr.checks, label);
  const parts = sr.account ?? [], effects = parts.find((p) => p.kind === "effects");
  const [open, setOpen] = useState<number | null>(lit);
  const [more, setMore] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cur, setCur] = useState<number | null>(lit);                         // the row J, K and F act on
  useEffect(() => { if (lit) { setOpen(lit); setCur(lit); } }, [lit]);
  useEffect(() => { if (lit) document.getElementById(`flow-${lit}`)?.scrollIntoView({ block: "start" }); }, [lit]);
  const order = groups.flatMap((g) => g.rows.map((r) => r.n));                  // the rows as they read, group by group
  const run = (act: () => Promise<unknown>) => {
    if (busy) return;                                                          // one mark at a time; the tick boxes stay enabled, so they keep their focus
    setBusy(true);
    setError(null);
    act().then(() => Promise.all([d.loadReading(), d.loadTicks().catch(() => {})]))
      .catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
  };
  const fine = (keys: string[]) => run(() => api.markChecks(d.id, keys));
  const reopen = (keys: string[]) => run(async () => { for (const k of keys) await api.unmarkCheck(d.id, k); });
  // J, K and F (§7.3), read from a ref set in the render as the stepper's are: they wait while a mark is on its way and
  // stay the stepper's while a cause is open beside the page. Enter is the focused row's own button.
  const byN = new Map(flows.map((f, i) => [i + 1, f]));
  const leftAt = (n: number) => openKeys(places.get(byN.get(n)?.id ?? "") ?? [], marks);
  const focusRow = (n: number) => document.querySelector<HTMLElement>(`#flow-${n} .fl-toggle`)?.focus();
  const focusTo = useRef<number | null>(null);
  const move = (to: number | undefined) => {
    if (to === undefined) return;
    if (to === cur) focusRow(to);
    else { focusTo.current = to; setCur(to); }                               // focused once its group has unfolded
  };
  useEffect(() => {
    if (cur !== null && focusTo.current === cur) { focusTo.current = null; focusRow(cur); }
  }, [cur]);                                                                   // eslint-disable-line react-hooks/exhaustive-deps
  // The buttons a click disables, replaces or removes (Looks fine, Reopen, Next flow ›, Show N more) hand their focus to a
  // row's toggle, so the keyboard is never left on the page. Next flow › opens the next row; on the last it closes its own.
  const nextFlow = (n: number) => {
    const to = order[order.indexOf(n) + 1];
    setOpen(to ?? null);
    move(to ?? n);
  };
  const onKey = useRef<(e: KeyboardEvent) => void>(() => {});
  onKey.current = (e) => {
    const stepper = !!ws.addr.open && "cause" in ws.addr.open;
    if (busy || stepper || e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || !order.length) return;
    const at = cur === null ? -1 : order.indexOf(cur);
    if (e.key === "j") { e.preventDefault(); move(order[at + 1]); }
    else if (e.key === "k") { e.preventDefault(); move(order[Math.max(at, 1) - 1]); }
    else if (e.key === "f" && cur !== null && at >= 0) {
      e.preventDefault();
      const left = leftAt(cur), next = [...order.slice(at + 1), ...order.slice(0, at)].find((n) => leftAt(n).length > 0);
      if (left.length) fine(left);
      move(next ?? cur);                                                     // none left: stay on this row, not on a button its mark takes away
    }
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => onKey.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
  // only a hidden row an address, Next flow › or a key opens or reaches unfolds its group, and a group once unfolded stays so
  const unfolded = (g: FlowGroup) => g.rows.length <= FOLD_AT || more.has(g.key)
    || g.rows.slice(FOLD_AT).some((r) => r.n === lit || r.n === open || r.n === cur);
  const revealed = groups.filter((g) => g.rows.length > FOLD_AT && !more.has(g.key) && unfolded(g)).map((g) => g.key);
  if (revealed.length) setMore(new Set([...more, ...revealed]));          // remembered here, in the render that unfolds it
  return (
    <div className="st-flows" aria-busy={busy}>
      {error && <div className="banner warn">{error}</div>}
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
                <li key={flow.id} id={`flow-${n}`} className={`fl-row${on ? " on" : ""}`}>
                  <div className="fl-head">
                    {mine.length > 0 && <input type="checkbox" className="fl-tick" checked={done}
                                               aria-label={`Looks fine: ${bare(sentence)}`}
                                               onChange={() => (done ? reopen(mine.map((k) => k.key)) : fine(left))} />}
                    <button className="fl-toggle" aria-expanded={on} title={bare(sentence)} aria-label={`Flow ${n}: ${bare(sentence)}`}
                            onClick={() => setOpen(on ? null : n)} onFocus={() => setCur(n)}>
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
      {rest.length > 0 && <section className="st-other fl-also" aria-label="Also in this story"><span>Also in this story:</span><Chips causes={rest} /></section>}
      {effects && <section className="st-effects" aria-label={effects.heading}><h3>{effects.heading}</h3>
        <AiText><NameText text={effects.text} /></AiText></section>}
    </div>
  );
}
