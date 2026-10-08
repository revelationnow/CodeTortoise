import { useState } from "react";
import { Link } from "react-router-dom";
import { byThread, letter } from "../reading/checks";
import { arcLayout, connectionRows, testsLine } from "../reading/overview";
import { progress, progressText, threadRead } from "../reading/plan";
import type { Reading, Thread } from "../reading/types";
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

/** A thread: name, CLs, open checks and purpose, then its stories in reading order with why each follows (§5.1). */
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
      {t.purpose && <p className="ov-purpose"><Ticks text={t.purpose} /></p>}
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

/** The overview in layout B (spec 2026-10-07-review-reading §5): the change as a whole, how its threads connect and the
 * threads on the left; To check, Build impact and Coverage pinned on the right. */
export default function Overview({ r }: { r: Reading }) {
  const ws = useWs(), ss = ws.data.stories;
  const tests = r.tests?.stories[0], testsStory = tests ? ss?.stories.find((s) => s.id === tests) : null;
  const p = ws.data.ticks ? progress(r, ws.data.ticks) : null;          // the reader's progress (phase 2 §6.2, §6.4)
  return (
    <div className="ws-page"><div className="ov2">
      <div className="ov2-left ws-whole">
        {p && <p className={`ov-progress${p.all ? " done" : ""}`}>{p.all ? "You've read every story" : progressText(p)}</p>}
        <section aria-labelledby="ov-whole">
          <h2 id="ov-whole">The change as a whole</h2>
          <p className="ws-lead">{r.whole_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={r.whole} /></p>
        </section>
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
        {r.coverage.length > 0 && (
          <section className="ws-tile" aria-label="Coverage">
            <h3>Coverage</h3>
            <ul className="ov-lines">{r.coverage.map((c) => <li key={c}><Ticks text={c} /></li>)}</ul>
          </section>
        )}
      </aside>
    </div></div>
  );
}
