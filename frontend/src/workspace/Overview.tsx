import { useState } from "react";
import { Link } from "react-router-dom";
import SinkMark from "../components/SinkMark";
import { setShowSinks, showSinks, sinkLine } from "../lib/sinks";
import { byThread, letter } from "../reading/checks";
import { arcLayout, cardText, connectionRows, introOpen, routeRows, setIntroOpen, testsLine } from "../reading/overview";
import { overviewProgress, progress, threadRead } from "../reading/plan";
import type { Reading, SinkHit, Thread } from "../reading/types";
import CheckTile, { Cleared } from "./CheckList";
import { useWs } from "./context";
import { short } from "./crumbs";
import { Ticks } from "./NameText";
import { Discussion } from "./WholePage";

const ROW = 56;                       // one thread box and the room around it in the connections tile

/** How the threads connect (spec 2026-10-07-review-reading §5.1): the threads stacked as boxes, an arc for each shown
 * connection with its text beside it, dashed for threads joined only by their bundle; pointing at an arc lights both
 * threads. One thread says so instead; a phone gets one sentence per connection. */
function Connections({ r }: { r: Reading }) {
  const ws = useWs();
  const [hot, setHot] = useState<[string, string] | null>(null);
  if (!r.threads.length) return null;
  const head = <h2 id="ov-conn">How the threads connect</h2>;
  if (r.threads.length === 1)
    return <section aria-labelledby="ov-conn">{head}<p className="muted">One thread: all stories are connected by calls or shared data.</p></section>;
  if (ws.screen === "phone")
    return (
      <section aria-labelledby="ov-conn">{head}
        <ul className="ov-conn-rows">{connectionRows(r.threads, r.connections).map((row) => (
          <li key={row.text} className={row.bundled ? "bundled" : ""}><Ticks text={row.text} /></li>
        ))}</ul>
      </section>
    );
  const { arcs, height, reach } = arcLayout(r.threads, r.connections, ROW);
  const lit = (a: { a: string; b: string }) => !!hot && hot[0] === a.a && hot[1] === a.b;
  return (
    <section aria-labelledby="ov-conn">{head}
      <div className="ov-conn" style={{ height, ["--reach" as string]: `${reach}px` }}>
        {r.threads.map((t, i) => (
          <button key={t.id} className={`ov-box${hot?.includes(t.id) ? " hot" : ""}`} style={{ top: i * ROW + 6, height: ROW - 12 }}
                  onClick={() => document.getElementById(`thread-${t.id}`)?.scrollIntoView({ block: "start" })}
                  aria-label={`Go to thread ${letter(i, t.id)}: ${short(t.name.replaceAll("`", ""))}`}>
            <span className="ov-letter">{letter(i, t.id)}</span>
            <span className="ov-box-name"><Ticks text={t.name} /></span>
            {t.open_checks > 0 && <span className="ck-count">{t.open_checks}</span>}
          </button>
        ))}
        <svg className="ov-arcs" width={reach + 4} height={height} aria-hidden>
          {arcs.map((a) => (
            <path key={`${a.a}-${a.b}`} d={a.d} className={`ov-arc${a.dashed ? " dashed" : ""}${lit(a) ? " hot" : ""}`}
                  onMouseEnter={() => setHot([a.a, a.b])} onMouseLeave={() => setHot(null)} />
          ))}
        </svg>
        {arcs.map((a) => (
          <div key={`${a.a}-${a.b}`} className={`ov-arc-label${a.dashed ? " dashed" : ""}${lit(a) ? " hot" : ""}`} style={{ top: a.labelY }}
               onMouseEnter={() => setHot([a.a, a.b])} onMouseLeave={() => setHot(null)}>
            <Ticks text={a.text} />{a.dashed && <span className="ov-ask"> — ask the author</span>}
          </div>
        ))}
      </div>
    </section>
  );
}

/** What the page's parts are, for a reader new to CodeTortoise (spec 2026-10-09-review-introduction §5.1): open on a
 * first visit; once closed it stays closed in this browser. */
function HowToRead() {
  const [open, setOpen] = useState(introOpen);
  const toggled = (now: boolean) => { if (now !== open) { setOpen(now); setIntroOpen(now); } };
  return (
    <details className="ov-howto" open={open} onToggle={(e) => toggled(e.currentTarget.open)}>
      <summary><h2 id="ov-howto">How to read this page</h2></summary>
      <ul>
        <li><b>Threads</b> group the change's stories that are joined by calls or shared data. Each has a letter (A, B…)
          used across the page.</li>
        <li><b>Stories</b> are the steps of a thread, one change and its effects each. A story has a <b>Steps</b> view
          (what it does, before → after, call paths, its code) and a <b>Graph</b> view.</li>
        <li><b>Arcs</b> between threads show what else ties them: a shared caller, names or types, a build condition or a
          folder. A dashed arc means they only arrived in the same review — ask the author why. On a phone each arc is a
          sentence.</li>
        <li><b>To check</b> lists what needs a reviewer's eye. <b>Looks fine</b> clears a row, <b>Read</b> ticks it for
          you alone, <b>Comment</b> starts a thread, <b>Open</b> shows the code.</li>
        <li><b>Progress</b> counts the stories and checks you have read.</li>
        <li><b>The side panel</b> shows code beside the page; ⤢ on a story's code opens it there.</li>
      </ul>
    </details>
  );
}

/** Where to start (§5.2): every thread in the suggested order with why, threads worth only a skim muted. The letter and
 * name go to the thread's card below, as the connections' boxes do; "first story" opens its first story. */
function WhereToStart({ r }: { r: Reading }) {
  const ws = useWs();
  const rows = routeRows(r);
  if (!rows.length) return null;
  return (
    <section aria-labelledby="ov-start">
      <h2 id="ov-start">{r.route_source === "llm" && <span className="ai-label">AI</span>}Where to start</h2>
      <ol className="ov-route">{rows.map((row) => (
        <li key={row.id} className={row.skim ? "skim" : ""}>
          <button className="link" onClick={() => document.getElementById(`thread-${row.id}`)?.scrollIntoView({ block: "start" })}
                  aria-label={`Go to thread ${row.letter}: ${short(row.name.replaceAll("`", ""))}`}>
            <span className="ov-letter">{row.letter}</span> <Ticks text={row.name} />
          </button>
          {" — "}<Ticks text={row.reason} />
          {row.skim && <span className="ov-skim">skim</span>}
          {row.first && <> · <Link to={ws.link(ws.item({ kind: "story", sid: row.first, view: "steps" }))}
                                 aria-label={`Open the first story of thread ${row.letter}`}>first story</Link></>}
        </li>
      ))}</ol>
    </section>
  );
}

/** A thread: name, CLs, open checks, its purpose and intro (`cardText`), then its stories in reading order with why each
 * follows (§5.1). */
function ThreadCard({ t, i, r }: { t: Thread; i: number; r: Reading }) {
  const ws = useWs(), ss = ws.data.stories;
  return (
    <article className="ov-thread" id={`thread-${t.id}`} aria-label={`Thread ${letter(i, t.id)}`}>
      <header>
        <span className="ov-letter">{letter(i, t.id)}</span>
        <h3>{t.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={t.name} /></h3>
        {t.cls.map((c) => (
          <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
        ))}
        {t.open_checks > 0 && <span className="ck-count">{t.open_checks} open</span>}
        {ws.data.ticks && <span className="ov-read">{threadRead(t.stories, new Set(ws.data.ticks.stories))} read</span>}
      </header>
      {cardText(t).map((p) => (
        <p key={p.text} className="ov-purpose">{p.ai && <span className="ai-label">AI</span>}<Ticks text={p.text} /></p>
      ))}
      <ol className="ov-stories">{t.stories.map((sid) => {
        const st = ss?.stories.find((s) => s.id === sid);
        const label = `Go to story ${sid}${st ? `: ${short(st.title)}` : ""}`;
        return (
          <li key={sid}>
            <Link to={ws.link(ws.item({ kind: "story", sid, view: "steps" }))} title={label} aria-label={label}>
              <Ticks text={st?.title ?? sid} /></Link>
            {r.reasons[sid] && <span className="ov-reason">{r.reasons[sid]}</span>}
          </li>
        );
      })}</ol>
    </article>
  );
}

/** The shared sinks the review hid (spec 2026-10-09 §5.2), with the viewer's Show/Hide and the owner's unmark. Show is
 * kept in the browser; the page reloads so every board, story and finding list follows it. */
function SinksLine({ hits }: { hits: SinkHit[] }) {
  const shown = showSinks();
  const flip = () => { setShowSinks(!shown); window.location.reload(); };
  return (
    <li className="ov-sinks">
      <Ticks text={sinkLine(hits, shown)} /> · <button className="link" onClick={flip} aria-pressed={shown}>{shown ? "Hide" : "Show"}</button>
      {hits.filter((h) => h.why === "marked").map((h) => <span key={h.label}> · <SinkMark label={h.label} on /></span>)}
    </li>
  );
}

/** The overview in layout B (spec 2026-10-07-review-reading §5): the introduction (how to read the page, the change as a
 * whole, where to start), how its threads connect and the threads on the left; To check, Build impact and Coverage
 * pinned on the right. */
export default function Overview({ r }: { r: Reading }) {
  const ws = useWs(), ss = ws.data.stories;
  const tests = r.tests?.stories[0], testsStory = tests ? ss?.stories.find((s) => s.id === tests) : null;
  const p = ws.data.ticks ? progress(r, ws.data.ticks) : null;          // the reader's progress (phase 2 §6.2, §6.4)
  return (
    <div className="ws-page"><div className="ov2">
      <div className="ov2-left ws-whole">
        {p && <p className={`ov-progress${p.all ? " done" : ""}`}>{overviewProgress(p)}</p>}
        <HowToRead />
        <section aria-labelledby="ov-whole">
          <h2 id="ov-whole">The change as a whole</h2>
          <p className="ws-lead">{r.whole_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={r.whole} /></p>
        </section>
        <WhereToStart r={r} />
        <Connections r={r} />
        {r.threads.length > 0 && (
          <section aria-labelledby="ov-threads">
            <h2 id="ov-threads">Threads</h2>
            {r.threads.map((t, i) => <ThreadCard key={t.id} t={t} i={i} r={r} />)}
            {r.tests && (
              <p className="ov-tests">{testsStory
                ? <Link to={ws.link(ws.item({ kind: "story", sid: testsStory.id, view: "steps" }))}
                        title={`Go to story ${testsStory.id}: ${short(testsStory.title)}`}>{testsLine(r.tests, r.threads)}</Link>
                : testsLine(r.tests, r.threads)}</p>
            )}
          </section>
        )}
        <Discussion />
      </div>
      <aside className="ov2-right" aria-label="What to check">
        <CheckTile id="checks" groups={byThread(r)} ofTotal={false} footer={<>
          {r.rules_only && <p className="muted small">Risks judged by rules only.</p>}
          <Cleared checks={r.cleared} />
        </>} />
        {r.build_impact.length > 0 && (
          <section className="ws-tile" aria-label="Build impact">
            <h3>Build impact</h3>
            <ul className="ov-lines">{r.build_impact.map((b) => (
              <li key={b.header}><Ticks text={b.text} />{b.note && <span className="muted"> {b.note}</span>}</li>
            ))}</ul>
          </section>
        )}
        {(r.coverage.length > 0 || (r.sinks?.length ?? 0) > 0) && (
          <section className="ws-tile" aria-label="Coverage">
            <h3>Coverage</h3>
            <ul className="ov-lines">
              {r.coverage.map((c) => <li key={c}><Ticks text={c} /></li>)}
              {(r.sinks?.length ?? 0) > 0 && <SinksLine hits={r.sinks!} />}
            </ul>
          </section>
        )}
      </aside>
    </div></div>
  );
}
