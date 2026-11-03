import { Fragment, type ReactNode, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import type { Story } from "../board/types";
import AiText, { AiName } from "../components/AiText";
import SinkMark from "../components/SinkMark";
import { aiTitle } from "../lib/aiMarks";
import { setShowSinks, showSinks, sinkLine } from "../lib/sinks";
import { openCount } from "../reading/causes";
import { letter } from "../reading/checks";
import { alsoLine, blockLine, byModel, citeName, componentBands, concernWhere, conditionTitle, foldGate, gateGroups,
  OWNER_TAG, ownershipTitle, showsWhere, verdictCauses } from "../reading/design";
import { cardText, foldTitles, overviewHeading, sectionConnections, startButton, testsLine, threadAction, threadCounts,
  type SectionLink } from "../reading/overview";
import type { Gate, GatedLine, Reading, ReadingDesign, SinkHit, Thread } from "../reading/types";
import { connectionWalk } from "../reading/walks";
import Chips from "./Chips";
import { useWs, type Ws } from "./context";
import { short } from "./crumbs";
import { bare, plainNames } from "./names";
import { Ticks } from "./NameText";
import { SourceRow } from "./RewriteMenu";
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
function ThreadSection({ t, i, r, links, read, stories, design }: {
  t: Thread; i: number; r: Reading; links: SectionLink[];
  read: ReadonlySet<string>; stories: ReadonlyMap<string, Story>; design: ReadingDesign | null;
}) {
  const ws = useWs();
  const [all, setAll] = useState(false);
  const plain = (s: string) => bare(plainNames(s, ws.data.names));
  const L = letter(i, t.id), name = plain(t.name);
  const n = threadCounts(t, r.causes, ws.hidden, r.marks, read), act = threadAction(t.stories, read);
  const paras = cardText(t), full = paras.map((p) => plain(p.text)).join("\n");
  const more = t.stories.length - SHOWN;
  const walks = design?.walks.filter((w) => w.thread === t.id) ?? [];
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
      {walks.length > 0 && <ul className="dz-walks">{walks.map((w) => (
        <li key={w.id}><Link to={ws.link(ws.item({ kind: "walk", wid: w.id }))} title={`Walk through: ${plain(w.title)}`}
                             aria-label={`Walk through: ${plain(w.title)}`}>
          <span aria-hidden>▶ </span>Walk through: <AiName ai={w.title_source === "llm"}><Ticks text={w.title} /></AiName> ›</Link></li>
      ))}</ul>}
      {links.length > 0 && <ul className="ov-links">{links.map((k) => {
        const cw = connectionWalk(design, k.a, k.b);
        return (
          <li key={k.before + k.text} className={k.bundled ? "bundled" : undefined}>
            {k.before}<AiText as="span" ai={k.ai}><Ticks text={k.text} /></AiText>{k.after}
            {cw && <> · <Link className="dz-cwalk" to={ws.link(ws.item({ kind: "walk", wid: cw.id }))} title={`Walk through: ${plain(cw.title)}`}
                              aria-label={`Walk through: ${plain(cw.title)}`}><span aria-hidden>▶ </span>Walk through ›</Link></>}
          </li>
        );
      })}</ul>}
    </section>
  );
}

/** The shared sinks the review hid (spec 2026-10-09 §5.2), with the viewer's Show/Hide and the owner's unmark. Show is
 * kept in the browser; the page reloads so every board, story and finding list follows it. The reload starts the page
 * over with Coverage shut, so the press leaves a note in the history entry's state, which a reload keeps (the phone's
 * `page` relies on the same), and the overview opens Coverage from it. Accepted: the note stays in that entry, so F5 or Back to
 * it reopens Coverage after the reader shut it; a visit of its own (a link, the Overview link) carries no note and finds it shut. */
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

/** The verdict (spec 2026-11-02 §3.1): two or three sentences ending in what to settle, the checks it names as chips (a
 * chip opens its check, as chips do elsewhere), and where it comes from: the stories, and the design context when the
 * model read one. */
function Verdict({ d, r }: { d: ReadingDesign; r: Reading }) {
  const ws = useWs();
  return (
    <div className="dz-verdict">
      <AiText><Ticks text={d.verdict} /></AiText>
      <Chips causes={verdictCauses(d, r.causes)} muted={ws.hidden} />
      <SourceRow d={d} part="verdict" what="verdict" />
    </div>
  );
}

const COLS = ["Concern", "How the change does it", "Where", "Assessment"];

/** What it must get right (§6.1): a row per thing the design must get right, numbered as a story's crumb cites it (§3.2),
 * how the change does it, where (its stories' thread letters and the stories), and the assessment with its note and the
 * checks it rests on. Nothing here is a new check: a chip is one the review already has. */
function Concerns({ d, r }: { d: ReadingDesign; r: Reading }) {
  const ws = useWs(), by = new Map((r.causes ?? []).map((c) => [c.id, c]));
  const titles = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st.title]));
  return (
    <section className="dz-concerns" aria-labelledby="dz-concerns">
      <h2 id="dz-concerns">What it must get right</h2>
      <SourceRow d={d} part="concerns" what="concerns" />
      <AiText as="div" className="dz-table">
        {/* the roles keep the table a table for screen readers when a narrow overview stacks its cells (phase 2 minor 4) */}
        <table role="table">
          <thead role="rowgroup"><tr role="row">{COLS.map((h) => <th key={h} role="columnheader">{h}</th>)}</tr></thead>
          <tbody role="rowgroup">{d.concerns.map((c, i) => {
            const where = concernWhere(c.stories, r.threads);
            return (
              <tr key={i} id={`concern-${i + 1}`} role="row">
                <td role="cell" className="dz-c-text"><span className="dz-c-n">{i + 1}</span> <Ticks text={c.text} /></td>
                <td role="cell" data-label={COLS[1]}><Ticks text={c.how} /></td>
                <td role="cell" data-label={COLS[2]} className="dz-c-where">
                  {where.letters.map((L) => <span key={L} className="ov-letter" title={`Thread ${L}`}>{L}</span>)}
                  {where.stories.map((s) => (
                    <Link key={s} className="ws-handle link" to={storyTo(ws, s)} title={bare(titles.get(s) ?? s)}
                          aria-label={`Go to story ${s}: ${short(titles.get(s) ?? s)}`}>{s}</Link>
                  ))}
                </td>
                <td role="cell" data-label={COLS[3]}>
                  <span className={`ck-tag ${c.assessment}`}>{c.assessment}</span>
                  {c.note && <span className="dz-c-note"> <Ticks text={c.note} /></span>}
                  <Chips causes={c.causes.flatMap((id) => by.get(id) ?? [])} muted={ws.hidden} />
                </td>
              </tr>
            );
          })}</tbody>
        </table>
      </AiText>
    </section>
  );
}

/** Is the design right? (§6.2): a line on which part owns each decision the change makes, or what it leaves undone, each
 * tagged and citing the story, the code or the file it rests on. Opinions, not checks: nothing here is counted. */
function OwnershipLines({ d }: { d: ReadingDesign }) {
  const ws = useWs(), titles = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st.title]));
  return (
    <ul className="ov-lines dz-owner">{d.ownership.map((o, i) => (
      <AiText as="li" key={i}>
        <span className={`ck-tag ${OWNER_TAG[o.tag]}`}>{o.tag}</span> <Ticks text={o.text} />
        <span className="dz-cites">{o.cites.map((c, k) => (
          <Fragment key={c}>{k > 0 && ", "}{titles.has(c)
            ? <Link className="ws-handle link" to={storyTo(ws, c)} title={bare(titles.get(c)!)}
                    aria-label={`Go to story ${c}: ${short(titles.get(c)!)}`}>{c}</Link>
            : <code>{citeName(d, c)}</code>}</Fragment>
        ))}</span>
      </AiText>
    ))}</ul>
  );
}

/** Where the change sits (spec 2026-11-02 §5): the map's layer bands with components for blocks, each naming the threads
 * that change it and its changed files, the calls and fields that cross into it from another component, and what changed
 * in it. A component that shares no edge with the rest is dashed. It opens nothing: its stories are a thread's. */
function WhereItSits({ d, r }: { d: ReadingDesign; r: Reading }) {
  const ws = useWs(), titles = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st.title]));
  return (
    <section className="dz-where" aria-labelledby="dz-where">
      <h2 id="dz-where">Where the change sits</h2>
      {componentBands(d.components).map((b) => (
        <section key={b.band} className={`ov-band lv${b.level === null ? "x" : b.level % 4}`} aria-label={`Layer ${b.band}`}>
          <h3>{b.band}</h3>
          <div className="ov-blocks">{b.components.map((c) => {
            const also = alsoLine(c.stories, (s) => titles.get(s));
            return (
              <div key={c.name} className={`ov-block dz-block${c.quiet ? " quiet" : ""}`}>
                <div className="nm">{c.name}</div>
                <div className="ct">{blockLine(c, r.threads)}</div>
                {c.quiet ? <div className="ln">No calls or fields shared with the rest</div>
                  : c.crossing.map((l) => <div key={l} className="ln"><Ticks text={l} /></div>)}
                {also && <div className="also"><Ticks text={also} /></div>}
              </div>
            );
          })}</div>
        </section>
      ))}
    </section>
  );
}

/** The condition fold's lines (§7): those that still run when the condition is false, then those that stop, each with its
 * story, its code and where it is. */
function ConditionLines({ g }: { g: Gate }) {
  const ws = useWs(), { runs, stops } = gateGroups(g), titles = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st.title]));
  const row = (l: GatedLine, i: number) => {
    const title = l.story ? titles.get(l.story) ?? l.story : "";
    return (
      <li key={i}>
        {l.story ? <Link className="ws-handle link" to={storyTo(ws, l.story)} title={bare(title)}
                         aria-label={`Go to story ${l.story}: ${short(title)}`}>{l.story}</Link>
          : <span className="ws-handle">no story</span>}
        {" "}<code>{l.text}</code>
        <span className="muted"> · {l.path}{l.line ? `:${l.line}` : ""}{l.function && <> in <code>{l.function}</code></>}</span>
      </li>
    );
  };
  return <>
    <p className="muted">The condition is <code>{g.test}</code>, in {g.path}{g.line ? `:${g.line}` : ""}.</p>
    {runs.length > 0 && <><h3>Still runs ({runs.length})</h3><ul className="ov-lines dz-gated">{runs.map(row)}</ul></>}
    {stops.length > 0 && <><h3>Stops ({stops.length})</h3><ul className="ov-lines dz-gated">{stops.map(row)}</ul></>}
  </>;
}

/** A folded row after the threads (§5.3): its summary a heading that says what is inside. It starts open when `open`;
 * after that the reader's clicks are its own. */
function Fold({ name, title, open, ai = false, children }: { name: string; title: string; open?: boolean; ai?: boolean; children: ReactNode }) {
  return (
    <section aria-label={name}>
      <details className="ov-fold" open={open}>
        <summary><h2><AiName ai={ai}><Ticks text={title} /></AiName></h2></summary>
        {children}
      </details>
    </section>
  );
}

/** The overview (§5): how many threads and the change as a whole (no paragraph when the rules have nothing to add to the
 * heading), the verdict (spec 2026-11-02 §3.1), where to start, where the change sits (§5), what it must get right (§6.1),
 * a section per thread with its counts under one row of column labels and its walk-throughs, the tests, then whether the
 * design is right (§6.2), what still runs when the change's condition is false (§7), Build impact, Coverage and Discussion
 * folded. A story crumb's concern number (§3.2) arrives with the concern in its navigation state, and the page brings that
 * row into view; Back and Forward land on an entry that still carries it and are no click. */
export default function Overview({ r }: { r: Reading }) {
  const ws = useWs(), loc = useLocation(), read = new Set(ws.data.ticks?.stories ?? []);
  const [coverageOpen] = useState(() => (loc.state as { coverage?: boolean } | null)?.coverage === true);   // read once: it only sets how Coverage starts
  const stories = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st]));
  const start = startButton(r, read), folds = foldTitles(r, ws.data.comments), links = sectionConnections(r.threads, r.connections);
  const tests = r.tests?.stories[0], testsStory = tests ? stories.get(tests) : undefined;
  const design = r.design ?? null, gate = foldGate(design);
  const nav = useNavigationType(), concern = (loc.state as { concern?: number } | null)?.concern;
  useEffect(() => {
    if (concern && nav !== "POP") document.getElementById(`concern-${concern}`)?.scrollIntoView({ block: "center" });
  }, [loc.key]);                                                               // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="ws-page"><div className="ws-text ws-whole ov3">
      <section aria-labelledby="ov-whole" className="ov-top">
        <h2 id="ov-whole">{overviewHeading(r.threads.length)}</h2>
        {r.whole && <AiText className="ws-lead" ai={r.whole_source === "llm"}><Ticks text={r.whole} /></AiText>}
        {design?.verdict && <Verdict d={design} r={r} />}
        {start ? <Link className="ov-start" to={storyTo(ws, start.sid)}>{start.label}</Link>
          : r.order.length > 0 && <p className="muted">You've read every story.</p>}
      </section>
      {design && showsWhere(design) && <WhereItSits d={design} r={r} />}
      {design && design.concerns.length > 0 && <Concerns d={design} r={r} />}
      {r.threads.length > 0 && <>
        <div className="ov-cols" aria-hidden><span /><span>Stories</span><span>Open</span><span>Read</span><span /></div>
        {r.threads.map((t, i) => <ThreadSection key={t.id} t={t} i={i} r={r} links={links.get(t.id) ?? []} read={read}
                                                stories={stories} design={design} />)}
        {r.tests && (
          <p className="ov-tests">{testsStory
            ? <Link to={storyTo(ws, testsStory.id)}
                    title={`Go to story ${testsStory.id}: ${short(testsStory.title)}`}>{testsLine(r.tests, r.threads)}</Link>
            : testsLine(r.tests, r.threads)}</p>
        )}
      </>}
      {design && design.ownership.length > 0 && (
        <Fold name="Is the design right?" title={ownershipTitle(design.ownership)}>
          {byModel(design, "ownership") && <SourceRow d={design} part="ownership" what="ownership lines" />}
          <OwnershipLines d={design} />
        </Fold>
      )}
      {gate && <Fold name="When the condition is false" title={conditionTitle(gate)} ai={byModel(design, `gate:${gate.id}`)}>
        {byModel(design, `gate:${gate.id}`) && <SourceRow d={design!} part={`gate:${gate.id}`} what="condition's name" />}
        <ConditionLines g={gate} /></Fold>}
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
