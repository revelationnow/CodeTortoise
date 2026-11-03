import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import AiText, { AiName } from "../components/AiText";
import { placeOpen } from "../reading/causes";
import { byModel } from "../reading/design";
import { openSteps, type StepRef, stepKeys, stepRef, stepSentence, threadName, walkOpen, walkThreads } from "../reading/walks";
import { at } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import NameText, { Ticks } from "./NameText";
import { bare } from "./names";
import { SourceRow } from "./RewriteMenu";
import useMarks from "./useMarks";
import useRowKeys from "./useRowKeys";
import WalkDrawing from "./WalkDrawing";

/** A walk-through (spec 2026-11-02-design-overview §3.2): a story's header (its title; a crumb of its threads, its steps,
 * the stories it is built from and its open count; the lead; how it was built), then its steps as rows that open in place,
 * each saying where it comes from. A flow's step has that flow's tick box, which marks its checks fine for everyone as the
 * Flows tab's does (§4.3). `step=N` opens row N. Then the review's other walk-throughs. J, K, F and Enter step through the
 * rows as on the Flows tab. */
export default function WalkPage({ wid }: { wid: string }) {
  const ws = useWs(), d = ws.data, r = d.reading!, design = r.design!, w = design.walks.find((x) => x.id === wid)!;
  const { nodes } = design, { names } = d, marks = r.marks;
  const label = useMemo(() => (n: string) => nodes[n]?.label ?? names[n]?.label ?? "a function", [nodes, names]);
  const checks = useMemo(() => new Map(r.checks.map((k) => [k.key, k])), [r.checks]);
  const order = useMemo(() => w.steps.map((_, i) => i + 1), [w.steps]);
  const leftAt = (n: number) => stepKeys(w.steps[n - 1], checks, ws.hidden).filter((k) => placeOpen(k, marks));
  const lit = ws.addr.step && ws.addr.step <= w.steps.length ? ws.addr.step : null;   // a step it does not have opens none
  const [open, setOpen] = useState<number | null>(lit);
  const { busy, error, fine, reopen } = useMarks();
  const { setCur, move, focusRow, said } = useRowKeys({ order, busy, leftAt, fine, start: lit, prefix: "step" });
  // the address's step opens and comes into view once each time it changes, as the Flows tab's flow does
  const named = useRef<number | null | undefined>(undefined);
  const show = (n: number) => { setOpen(n); setCur(n); document.getElementById(`step-${n}`)?.scrollIntoView({ block: "start" }); };
  useEffect(() => {
    if (lit && lit !== named.current) show(lit);
    named.current = lit;
  }, [lit]);                                                                   // eslint-disable-line react-hooks/exhaustive-deps
  const nextStep = (n: number) => {
    const to = order[order.indexOf(n) + 1];
    setOpen(to ?? null);
    move(to ?? n);
  };
  const drawn = ws.screen !== "phone";                                         // a phone has the rows only (§4.4)
  const threads = walkThreads(w).flatMap((tid) => {
    const name = threadName(r.threads, tid);
    return name ? [name] : [];
  });
  const titleOf = (sid: string) => d.stories?.stories.find((s) => s.id === sid)?.title ?? sid;
  const refTo = (l: NonNullable<StepRef["link"]>) =>
    ws.link(at({ kind: "story", sid: l.story, view: "steps" }, { flow: l.flow, ...(l.sec ? { sec: l.sec } : {}) }));
  const openN = walkOpen(w, checks, ws.hidden, marks), others = design.walks.filter((x) => x.id !== w.id);
  return (
    <div className="ws-page"><div className="st-page dz-walk">
      <header className="ws-story-head st-head">
        <h2><AiName ai={w.title_source === "llm"}><Ticks text={w.title} /></AiName></h2>
        <p className="st-crumb">
          {threads.map((name, i) => (
            <Fragment key={name}>{i > 0 && " with "}
              <Link to={ws.link(at({ kind: "whole" }))} state={{ page: true }} title={`Go to ${name.replace("Thread", "thread")} on the overview`}
                    aria-label={`Go to ${name.replace("Thread", "thread")} on the overview`}>{name}</Link></Fragment>
          ))}
          {threads.length > 0 && " · "}{w.steps.length} step{w.steps.length === 1 ? "" : "s"}
          {w.stories.length > 0 && <> · over {w.stories.map((sid, i) => (
            <Fragment key={sid}>{i > 0 && ", "}
              <Link to={ws.link(ws.item({ kind: "story", sid, view: "steps" }))} title={bare(titleOf(sid))}
                    aria-label={`Go to story ${sid}: ${short(titleOf(sid))}`}>{sid}</Link></Fragment>
          ))}</>}
          {openN > 0 && <> · {openN} open</>}
        </p>
        <div className="st-summary">
          {w.lead && <AiText ai={w.title_source === "llm"}><NameText text={w.lead} /></AiText>}
          {byModel(design, `walk:${w.id}`) && <SourceRow d={design} part={`walk:${w.id}`} what="title and lead" />}
          <p className="dz-note">Built from the stories' call paths and flows{drawn ? "; the arrows are calls (solid) and returns (dashed)" : ""}.
            Its checks are the stories' checks: marking a step fine marks that flow fine.</p>
        </div>
      </header>
      {drawn && <WalkDrawing walk={w} label={label} component={(n) => nodes[n]?.component ?? null}
                             open={openSteps(w, checks, ws.hidden, marks)} onPick={(n) => { show(n); focusRow(n); }} />}
      <div className="st-flows dz-steps" aria-busy={busy}>
        <div className="vh" aria-live="polite">{said}</div>
        {error && <div className="banner warn" role="alert">{error}</div>}
        <ol className="fl-rows">{w.steps.map((st, i) => {
          const n = i + 1, keys = stepKeys(st, checks, ws.hidden), left = keys.filter((k) => placeOpen(k, marks));
          const done = keys.length > 0 && !left.length, on = open === n, sentence = stepSentence(st, label), ref = stepRef(st, label);
          return (
            <li key={n} id={`step-${n}`} className={`fl-row dz-step ${st.status}${on ? " on" : ""}`} onFocus={() => setCur(n)}>
              <div className="fl-head">
                {keys.length > 0 ? <label className="fl-tickbox"><input type="checkbox" className="fl-tick" checked={done}
                                           aria-label={`Looks fine: step ${n}, ${bare(sentence)}`}
                                           onChange={() => { setCur(n); if (done) reopen(keys); else fine(left); }} /></label>
                  : <span className="fl-tickbox" aria-hidden />}{/* its room kept: every step's number lines up */}
                <button className="fl-toggle" aria-expanded={on} title={bare(sentence)} aria-label={`Step ${n}: ${bare(sentence)}`}
                        onClick={() => { setOpen(on ? null : n); setCur(n); }}>
                  <span className="fl-n">{n}</span><span className="fl-one"><Ticks text={sentence} /></span>
                </button>
                <span className="dz-ref">{ref.link
                  ? <Link to={refTo(ref.link)} title={`Go to ${bare(ref.text)}`} aria-label={`Go to ${bare(ref.text)}`}><Ticks text={ref.text} /> ›</Link>
                  : <Ticks text={ref.text} />}</span>
              </div>
              {on && (
                <div className="fl-body" role="region" aria-label={`Step ${n}: ${bare(sentence)}`}>
                  {st.path && <p className="fl-path mono">{st.path}{st.line ? `:${st.line}` : ""}{st.cl !== null && <> · <Link
                    to={ws.link(ws.item({ kind: "cl", cl: st.cl }))} title={`Open CL ${st.cl}`} aria-label={`Open CL ${st.cl}`}>CL {st.cl}</Link></>}</p>}
                  {st.loop && <p className="dz-loop">Inside <code>{st.loop}</code></p>}
                  {keys.map((k) => <p key={k} className="fl-check"><NameText text={checks.get(k)!.text} /></p>)}
                  <div className="fl-acts">
                    {left.length > 0 && <button onClick={() => { fine(left); focusRow(n); }} disabled={busy}>Looks fine</button>}
                    {done && <button className="link" onClick={() => { reopen(keys); focusRow(n); }} disabled={busy}>Reopen</button>}
                    <button className="link" onClick={() => nextStep(n)}>Next step ›</button>
                  </div>
                </div>
              )}
            </li>
          );
        })}</ol>
      </div>
      {others.length > 0 && (
        <section className="st-other" aria-label="Other walk-throughs"><h3>Other walk-throughs</h3>
          <ul className="st-chips">{others.map((o) => (
            <li key={o.id}><Link className="st-chip walk" to={ws.link(ws.item({ kind: "walk", wid: o.id }))}
                                 title={`Walk through: ${bare(o.title)}`} aria-label={`Walk through: ${bare(o.title)}`}>
              <span aria-hidden>▶ </span><Ticks text={o.title} /></Link></li>
          ))}</ul>
        </section>
      )}
    </div></div>
  );
}
