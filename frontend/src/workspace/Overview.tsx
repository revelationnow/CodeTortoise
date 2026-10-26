import { Link } from "react-router-dom";
import SinkMark from "../components/SinkMark";
import AiText, { AiName } from "../components/AiText";
import { aiTitle } from "../lib/aiMarks";
import { setShowSinks, showSinks, sinkLine } from "../lib/sinks";
import { causeOpen, shown } from "../reading/causes";
import { letter } from "../reading/checks";
import { cardText, connectionRows, testsLine } from "../reading/overview";
import type { Reading, SinkHit, Thread } from "../reading/types";
import { useWs } from "./context";
import { short } from "./crumbs";
import { plainNames } from "./names";
import { Ticks } from "./NameText";
import { Discussion } from "./WholePage";

/** How the threads connect (spec 2026-10-16-outline-and-causes §3): a sentence per shown connection. */
function Connections({ r }: { r: Reading }) {
  if (!r.threads.length) return null;
  return (
    <section aria-labelledby="ov-conn">
      <h2 id="ov-conn">How the threads connect</h2>
      {r.threads.length === 1 ? <p className="muted">One thread: all stories are connected by calls or shared data.</p>
        : <ul className="ov-conn-rows">{connectionRows(r.threads, r.connections).map((row) => (
            <li key={row.text} className={row.bundled ? "bundled" : ""}><Ticks text={row.text} /></li>
          ))}</ul>}
    </section>
  );
}

/** A thread (§3): its letter and name, its introduction, how far the reader is and what is open, and a way in. */
function ThreadBlock({ t, i, r }: { t: Thread; i: number; r: Reading }) {
  const ws = useWs(), read = new Set(ws.data.ticks?.stories ?? []);
  const L = letter(i, t.id), done = t.stories.filter((s) => read.has(s)).length;
  const unread = t.stories.find((s) => !read.has(s)), to = unread ?? t.stories[0];
  const open = shown(r.causes ?? [], ws.hidden).filter((c) => c.thread === t.id && causeOpen(c, r.marks)).length;
  const meta = `${t.stories.length} stor${t.stories.length === 1 ? "y" : "ies"} · ${done} read${r.causes ? ` · ${open} cause${open === 1 ? "" : "s"} open` : ""}`;
  const full = cardText(t).map((p) => plainNames(p.text, ws.data.names)).join("\n").replaceAll("`", "");
  return (
    <article className="ov-thread" id={`thread-${t.id}`} aria-label={`Thread ${L}`}>
      <header>
        <span className="ov-letter">{L}</span>
        <h3><AiName ai={t.text_source === "llm"}><Ticks text={t.name} /></AiName></h3>
      </header>
      <div className="ov-intro" title={full}>{cardText(t).map((p) => (
        <AiText key={p.text} className="ov-purpose" ai={p.ai} title={p.ai ? `${aiTitle()}\n${full}` : undefined}>
          <Ticks text={p.text} /></AiText>
      ))}</div>
      <p className="ov-meta">{meta}</p>
      {to && <Link to={ws.link(ws.item({ kind: "story", sid: to, view: "steps" }))}
                   aria-label={`Go to thread ${L}'s ${unread ? "first unread" : "first"} story`}>
        {unread ? "First unread story ›" : "First story ›"}</Link>}
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

/** The overview (§3): the change as a whole and where to start reading, a block per thread, how they connect, then
 * what the change does to the build and what the analysis could not cover. */
export default function Overview({ r }: { r: Reading }) {
  const ws = useWs(), ss = ws.data.stories, read = new Set(ws.data.ticks?.stories ?? []);
  const next = r.order.find((s) => !read.has(s)) ?? null, started = r.order.some((s) => read.has(s));
  const tests = r.tests?.stories[0], testsStory = tests ? ss?.stories.find((s) => s.id === tests) : null;
  return (
    <div className="ws-page"><div className="ws-text ws-whole ov3">
      <section aria-labelledby="ov-whole" className="ov-top">
        <h2 id="ov-whole">The change as a whole</h2>
        <AiText className="ws-lead" ai={r.whole_source === "llm"}><Ticks text={r.whole} /></AiText>
        {next ? <Link className="ov-start" to={ws.link(ws.item({ kind: "story", sid: next, view: "steps" }))}>{started ? "Continue ›" : "Start here ›"}</Link>
          : r.order.length > 0 && <p className="muted">You've read every story.</p>}
      </section>
      {r.threads.length > 0 && (
        <section aria-labelledby="ov-threads">
          <h2 id="ov-threads">Threads</h2>
          {r.threads.map((t, i) => <ThreadBlock key={t.id} t={t} i={i} r={r} />)}
          {r.tests && (
            <p className="ov-tests">{testsStory
              ? <Link to={ws.link(ws.item({ kind: "story", sid: testsStory.id, view: "steps" }))}
                      title={`Go to story ${testsStory.id}: ${short(testsStory.title)}`}>{testsLine(r.tests, r.threads)}</Link>
              : testsLine(r.tests, r.threads)}</p>
          )}
        </section>
      )}
      <Connections r={r} />
      {r.build_impact.length > 0 && (
        <section aria-labelledby="ov-build">
          <h2 id="ov-build">Build impact</h2>
          <ul className="ov-lines">{r.build_impact.map((b) => (
            <li key={b.header}><Ticks text={b.text} />{b.note && <span className="muted"> {b.note}</span>}</li>
          ))}</ul>
        </section>
      )}
      {(r.coverage.length > 0 || (r.sinks?.length ?? 0) > 0 || r.rules_only) && (
        <section aria-labelledby="ov-cover">
          <h2 id="ov-cover">Coverage</h2>
          <ul className="ov-lines">
            {r.rules_only && <li>Risks judged by rules only.</li>}
            {r.coverage.map((c) => <li key={c}><Ticks text={c} /></li>)}
            {(r.sinks?.length ?? 0) > 0 && <SinksLine hits={r.sinks!} />}
          </ul>
        </section>
      )}
      <Discussion />
    </div></div>
  );
}
