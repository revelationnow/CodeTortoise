import { type ReactNode, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import type { Story } from "../board/types";
import AiText, { AiName } from "../components/AiText";
import SinkMark from "../components/SinkMark";
import { aiTitle } from "../lib/aiMarks";
import { setShowSinks, showSinks, sinkLine } from "../lib/sinks";
import { openCount } from "../reading/causes";
import { letter } from "../reading/checks";
import { cardText, foldTitles, overviewHeading, sectionConnections, startButton, testsLine, threadAction,
  threadCounts } from "../reading/overview";
import type { Reading, SinkHit, Thread } from "../reading/types";
import { useWs, type Ws } from "./context";
import { short } from "./crumbs";
import { plainNames } from "./names";
import { Ticks } from "./NameText";
import { DiscussionThreads } from "./WholePage";

/** A thread's stories shown before "Show the other N stories" (spec 2026-10-25-review-ui-redesign §5.2). */
const SHOWN = 4;

/** Where a story's link on the overview goes: the story as the reader last left it this session (spec
 * 2026-10-04-review-workspace §2.4), else its steps. */
const storyTo = (ws: Ws, sid: string) => ws.link(ws.item({ kind: "story", sid, view: "steps" }));

/** One count in a thread's header bar (§5.2): the number under its column label; its word shows only on a phone, where
 * the counts wrap under the name. A screen reader hears ", 2 stories, 3 open, 0 read". */
function Count({ n, word, sep = false }: { n: number | string; word: string; sep?: boolean }) {
  return <>
    {sep && <span className="ov-sep" aria-hidden> · </span>}
    <span className="ov-n"><span className="vh">, </span>{n}<span className="ov-w"> {word}</span></span>
  </>;
}

/** A thread (§5.2): a header bar with its letter, name, counts and one action; its intro; its first stories, the rest a
 * click away; how it connects to the threads before it. `read` (the stories the reader has read) and `stories` (every
 * story by id) are worked out once by the overview for all its sections. */
function ThreadSection({ t, i, r, links, read, stories }: {
  t: Thread; i: number; r: Reading; links: { text: string; bundled: boolean }[];
  read: ReadonlySet<string>; stories: ReadonlyMap<string, Story>;
}) {
  const ws = useWs();
  const [all, setAll] = useState(false);
  const plain = (s: string) => plainNames(s, ws.data.names).replaceAll("`", "");
  const L = letter(i, t.id), name = plain(t.name);
  const n = threadCounts(t, r.causes, ws.hidden, r.marks, read), act = threadAction(t.stories, read);
  const paras = cardText(t), full = paras.map((p) => plain(p.text)).join("\n");
  const more = t.stories.length - SHOWN;
  return (
    <section className="ov-sec" id={`thread-${t.id}`} aria-label={`Thread ${L}: ${name}`}>
      <div className="ov-sec-head">
        <h3 className="ov-sec-t">
          <span className="ov-letter" aria-hidden>{L}</span>
          <b className="ov-sec-l">Thread {L}</b><span className="vh">: </span>
          <span className="ov-sec-name" title={name}>
            <AiName ai={t.text_source === "llm"} title={`${aiTitle()}\n${name}`}><Ticks text={t.name} /></AiName>
          </span>
        </h3>
        <span className="ov-counts">
          <Count n={n.stories} word={n.stories === 1 ? "story" : "stories"} />
          <Count n={n.open ?? "—"} word="open" sep />
          <Count n={n.read} word="read" sep />
        </span>
        <span className="ov-act">
          {act?.kind === "done" ? <span className="ov-done">All read ✓</span>
            : act && <Link to={storyTo(ws, act.sid)} aria-label={`${act.kind === "start" ? "Start" : "Continue"} thread ${L}`}>
                {act.kind === "start" ? "Start ›" : "Continue ›"}</Link>}
        </span>
      </div>
      <div className="ov-intro" title={full}>{paras.map((p) => (
        <AiText key={p.text} className="ov-purpose" ai={p.ai} title={p.ai ? `${aiTitle()}\n${full}` : undefined}>
          <Ticks text={p.text} /></AiText>
      ))}</div>
      {t.stories.length > 0 && <ol className="ov-stories">{(all ? t.stories : t.stories.slice(0, SHOWN)).map((sid) => {
        const st = stories.get(sid), open = openCount((r.causes ?? []).filter((c) => c.story === sid), ws.hidden, r.marks);
        return (
          <li key={sid}>
            <Link to={storyTo(ws, sid)} title={st ? plain(st.title) : undefined}>{st ? <Ticks text={st.title} /> : `Story ${sid}`}</Link>
            {open > 0 && <span className="ov-open"><span className="vh">, </span>{open} open</span>}
            {read.has(sid) && <span className="ov-read"><span aria-hidden>✓</span><span className="vh">, read</span></span>}
          </li>
        );
      })}</ol>}
      {more > 0 && <button className="link ov-more" aria-expanded={all} onClick={() => setAll(!all)}>
        {all ? "Show fewer ▴" : `Show the other ${more === 1 ? "story" : `${more} stories`} ▸`}</button>}
      {links.length > 0 && <ul className="ov-links">{links.map((k) => (
        <li key={k.text} className={k.bundled ? "bundled" : undefined}><Ticks text={k.text} /></li>
      ))}</ul>}
    </section>
  );
}

/** The shared sinks the review hid (spec 2026-10-09 §5.2), with the viewer's Show/Hide and the owner's unmark. Show is
 * kept in the browser; the page reloads so every board, story and finding list follows it. The reload starts the page
 * over with Coverage shut, so the press leaves a note in the history entry's state, which a reload keeps (the phone's
 * `page` relies on the same), and the overview opens Coverage from it. */
function SinksLine({ hits }: { hits: SinkHit[] }) {
  const shown = showSinks(), loc = useLocation(), navigate = useNavigate();
  const flip = () => {
    setShowSinks(!shown);
    navigate(loc, { replace: true, state: { ...loc.state, coverage: true } });
    window.location.reload();
  };
  return (
    <li className="ov-sinks">
      <Ticks text={sinkLine(hits, shown)} /> · <button className="link" onClick={flip} aria-pressed={shown}>{shown ? "Hide" : "Show"}</button>
      {hits.filter((h) => h.why === "marked").map((h) => <span key={h.label}> · <SinkMark label={h.label} on /></span>)}
    </li>
  );
}

/** A folded row after the threads (§5.3): its summary a heading that says what is inside. It starts open when `open`;
 * after that the reader's clicks are its own. */
function Fold({ name, title, open, children }: { name: string; title: string; open?: boolean; children: ReactNode }) {
  return (
    <section aria-label={name}>
      <details className="ov-fold" open={open}>
        <summary><h2>{title}</h2></summary>
        {children}
      </details>
    </section>
  );
}

/** The overview (§5): how many threads and the change as a whole (no paragraph when the rules have nothing to add to the
 * heading), where to start, a section per thread with its counts under one row of column labels, the tests, then Build
 * impact, Coverage and Discussion folded. */
export default function Overview({ r }: { r: Reading }) {
  const ws = useWs(), loc = useLocation(), read = new Set(ws.data.ticks?.stories ?? []);
  const [coverageOpen] = useState(() => (loc.state as { coverage?: boolean } | null)?.coverage === true);   // read once: it only sets how Coverage starts
  const stories = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st]));
  const start = startButton(r, read), folds = foldTitles(r, ws.data.comments), links = sectionConnections(r.threads, r.connections);
  const tests = r.tests?.stories[0], testsStory = tests ? stories.get(tests) : undefined;
  return (
    <div className="ws-page"><div className="ws-text ws-whole ov3">
      <section aria-labelledby="ov-whole" className="ov-top">
        <h2 id="ov-whole">{overviewHeading(r.threads.length)}</h2>
        {r.whole && <AiText className="ws-lead" ai={r.whole_source === "llm"}><Ticks text={r.whole} /></AiText>}
        {start ? <Link className="ov-start" to={storyTo(ws, start.sid)}>{start.label}</Link>
          : r.order.length > 0 && <p className="muted">You've read every story.</p>}
      </section>
      {r.threads.length > 0 && <>
        <div className="ov-cols" aria-hidden><span /><span>Stories</span><span>Open</span><span>Read</span><span /></div>
        {r.threads.map((t, i) => <ThreadSection key={t.id} t={t} i={i} r={r} links={links.get(t.id) ?? []} read={read} stories={stories} />)}
        {r.tests && (
          <p className="ov-tests">{testsStory
            ? <Link to={storyTo(ws, testsStory.id)}
                    title={`Go to story ${testsStory.id}: ${short(testsStory.title)}`}>{testsLine(r.tests, r.threads)}</Link>
            : testsLine(r.tests, r.threads)}</p>
        )}
      </>}
      {folds.build && <Fold name="Build impact" title={folds.build}>
        <ul className="ov-lines">{r.build_impact.map((b) => (
          <li key={b.header}><Ticks text={b.text} />{b.note && <span className="muted"> {b.note}</span>}</li>
        ))}</ul>
      </Fold>}
      {folds.coverage && <Fold name="Coverage" title={folds.coverage} open={coverageOpen}>
        <ul className="ov-lines">
          {r.rules_only && <li>Risks judged by rules only.</li>}
          {r.coverage.map((c) => <li key={c}><Ticks text={c} /></li>)}
          {(r.sinks?.length ?? 0) > 0 && <SinksLine hits={r.sinks!} />}
        </ul>
      </Fold>}
      <Fold name="Discussion" title={folds.discussion}><DiscussionThreads /></Fold>
    </div></div>
  );
}
