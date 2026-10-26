import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Comment } from "../api";
import type { BoardFlow, StoryDetail } from "../board/types";
import Comments from "../components/Comments";
import AiText from "../components/AiText";
import { useAi } from "../lib/ai";
import { storyModel } from "../lib/aiMarks";
import { causeOpen, firstOpenAt, shown } from "../reading/causes";
import { byEntry, codeOrder, flowLabel, flowPart, foldPath, readOrder, rewriteText, storyTabs, type TabSec, type TabSpec, whereByCl, whereTree } from "../reading/story";
import type { CallPath, Cause, ContractRow, StoryReading, WhereFile } from "../reading/types";
import type { Address } from "./address";
import { useWs } from "./context";
import FunctionCode from "./FunctionCode";
import NameText, { Ticks } from "./NameText";
import { plainNames } from "./names";
import { MechanicalStory, TestsStory } from "./StoryBodies";
import { StoryWhy } from "./StoryPlan";

/** A contract row (§8.1): its sentence; a signature with the part that differs marked; repeated and body-only edits
 * name their functions on "show N". */
function Contract({ row }: { row: ContractRow }) {
  const names = useWs().data.names;
  const [open, setOpen] = useState(false);
  const many = (row.kind === "repeated" || row.kind === "body") && row.nodes.length > 1;
  const [a, b] = row.mark.length === 2 ? row.mark : [0, 0];
  return (
    <li className={`st-contract ${row.kind}`}>
      <Ticks text={row.text} />
      {many && <button className="link small" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "hide" : `show ${row.nodes.length}`}</button>}
      {row.before && row.after && (
        <div className="st-sig mono">
          <div className="del">{row.before}</div>
          <div className="add">{row.after.slice(0, a)}<mark>{row.after.slice(a, b)}</mark>{row.after.slice(b)}</div>
        </div>
      )}
      {open && <ul className="st-names">{row.nodes.map((n) => <li key={n} className="mono">{names[n]?.label ?? "a function"}</li>)}</ul>}
    </li>
  );
}

/** Where's files by folder, then file, then function; `also` names a file's later CLs in the story (phase 2 §5.3). */
function WhereDirs({ files }: { files: (WhereFile & { also?: number[] })[] }) {
  const ws = useWs();
  return (
    <>{whereTree(files).map((d) => (
      <div key={d.dir} className="st-dir">
        <div className="st-dir-name mono">{d.dir}/</div>
        {d.files.map(({ name, file, showCl }) => (
          <div key={file.path} className="st-file">
            <div className="mono">{name}{(file.also ?? []).map((c) => <span key={c} className="ws-chip">also CL {c}</span>)}</div>
            <ul>{file.functions.map((f) => {
              const label = `Open ${f.label} in ${file.path}${f.line ? ` at line ${f.line}` : ""}`;
              return (
                <li key={f.node}>
                  {file.depot ? <Link className="mono" to={ws.link(ws.opened({ file: file.depot, line: f.line }))} title={label}
                                      aria-label={label}>{f.label}</Link> : <span className="mono" title={f.label}>{f.label}</span>}
                  <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
                  {showCl && f.cl !== null && <span className="ws-chip">CL {f.cl}</span>}
                </li>
              );
            })}</ul>
          </div>
        ))}
      </div>
    ))}</>
  );
}

/** Before → after (§6.1). */
function Contracts({ sr }: { sr: StoryReading }) {
  return (
    <section aria-label="Before → after">
      <ul className="st-contracts">{sr.contracts.map((r, i) => <Contract key={i} row={r} />)}</ul>
    </section>
  );
}

function Where({ sr }: { sr: StoryReading }) {
  const ws = useWs();
  const order = readOrder(sr.cl_order), grouped = (sr.cl_order?.length ?? 0) > 1;    // phase 2 §5.3
  return (
    <section aria-label="Where">
      {order && <p className="st-order">{order}</p>}
      {grouped ? whereByCl(sr.where, sr.cl_order!).map((g) => (
        <div key={g.cl ?? "none"} className="st-clgroup" role="group" aria-label={g.cl === null ? "Other files" : `CL ${g.cl}`}>
          <h4>{g.cl === null ? "Other" : `CL ${g.cl}`} · {g.files.length} file{g.files.length === 1 ? "" : "s"}</h4>
          <WhereDirs files={g.files} />
        </div>
      )) : <WhereDirs files={sr.where} />}
      {(sr.rewrites ?? []).length > 0 && (
        <ul className="st-rewrites">{sr.rewrites!.map((r, i) => {
          const t = rewriteText(r), label = `Open ${t.name}${r.line ? ` at line ${r.line}` : ""}, in all CLs`;
          return <li key={i}>{t.lead}{" "}<Link className="mono" to={ws.link(ws.opened({ file: r.file, line: r.line }))} title={label} aria-label={label}>{t.name}</Link></li>;
        })}</ul>
      )}
    </section>
  );
}

function PathRow({ p, graph }: { p: CallPath; graph: string | null }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="st-path">
      <div className="st-steps mono">
        <span className={`bd-tag ${p.kind}`}>{p.kind}</span>
        {foldPath(p, open).map((s, i) => (
          <span key={i}>{i > 0 && <span className="sep" aria-hidden>→</span>}
            {"label" in s ? s.label : <button className="link small" onClick={() => setOpen(true)}
                                              aria-label={`Show the ${s.more} folded steps`}>… {s.more} more</button>}</span>
        ))}
      </div>
      {p.text && <div className="st-path-text"><NameText text={p.text} /></div>}
      {graph && <Link className="small" to={graph} title="Show this path on the story's graph">On the graph ›</Link>}
    </li>
  );
}

/** Every call path the analysis found (§8.2), under the function it starts from, with what changes for whoever runs
 * it; a path drawn as a flow links to it on the graph. */
function CallPaths({ sr, detail }: { sr: StoryReading; detail: StoryDetail }) {
  const ws = useWs(), st = detail.story;
  if (!sr.paths.length) return null;
  const groups = byEntry(sr.paths);
  const graph = (p: CallPath) => {
    const i = p.flow ? st.flows.indexOf(p.flow) : -1;
    return i < 0 || !detail.graph ? null
      : ws.link({ ...ws.addr, place: { kind: "story", sid: st.id, view: "graph" }, flow: i + 1 });
  };
  return (
    <section aria-labelledby="st-paths">
      <h3 id="st-paths">Call paths <span className="muted small">{sr.paths.length}</span></h3>
      {groups.map((g, i) => (
        <details key={g.label + i} className="st-entry" open={i === 0 || sr.paths.length <= 8}>
          <summary>{g.entry ? "From the entry point " : "From "}<b className="mono">{g.label}</b>
            <span className="muted small"> {g.paths.length} path{g.paths.length === 1 ? "" : "s"}</span></summary>
          <ul className="st-paths">{g.paths.map((p, j) => <PathRow key={j} p={p} graph={graph(p)} />)}</ul>
        </details>
      ))}
    </section>
  );
}

/** Each changed function's code, definitions first (§6.3); opened one at a time. */
function Code({ sr, detail }: { sr: StoryReading; detail: StoryDetail }) {
  const ws = useWs();
  const [open, setOpen] = useState<Set<string>>(new Set());
  const nodes = new Map(detail.board.nodes.map((n) => [n.id, n]));
  const fns = codeOrder(sr.where, sr.contracts);
  if (!fns.length) return null;
  const toggle = (id: string, on: boolean) => setOpen((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n; });
  return (
    <section aria-labelledby="st-code">
      <h3 id="st-code">Code</h3>
      {fns.map((f) => {
        const node = nodes.get(f.node), file = sr.where.find((w) => w.functions.includes(f));
        return (
          <details key={f.node} className="st-fn" onToggle={(e) => toggle(f.node, (e.target as HTMLDetailsElement).open)}>
            <summary><b className="mono">{f.label}</b> <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
              {f.cl !== null && <span className="ws-chip">CL {f.cl}</span>}{file && <span className="muted small mono"> {file.path}</span>}
              {/* the bigger panel: Function | Full file, annotations, comments; the row itself stays as it is */}
              <Link className="bd-ibtn st-side" to={ws.link(ws.opened({ node: f.node }))} onClick={(e) => e.stopPropagation()}
                    title="Open in the side panel" aria-label={`Open ${f.label} in the side panel`}>⤢</Link></summary>
            {open.has(f.node) && (node?.path && node.range ? <FunctionCode node={node} board={detail.board} />
              : file?.depot ? <Link to={ws.link(ws.opened({ file: file.depot, line: f.line }))}>Open {file.path}</Link>
                : <p className="muted small">No code for {f.label} in this review.</p>)}
          </details>
        );
      })}
    </section>
  );
}

const bare = (s: string) => s.replaceAll("`", "");

/** A flow card's or the story's check chips (§2.3): one per shown cause, done ones muted with ✓; a chip opens the
 * stepper at the cause's first open place. */
function Chips({ causes }: { causes: Cause[] }) {
  const ws = useWs(), d = ws.data, marks = d.reading?.marks ?? {};
  if (!causes.length) return null;
  return (
    <ul className="st-chips">{causes.map((c) => {
      const line = plainNames(c.text, d.names), done = !causeOpen(c, marks);
      return (
        <li key={c.id}><Link className={`st-chip ${c.kind}${done ? " done" : ""}`} to={ws.link(ws.opened({ cause: c.id, at: firstOpenAt(c, marks) }))}
                             title={bare(line)} aria-label={`Open check: ${bare(line)}`}>{done && <span aria-hidden>✓ </span>}<Ticks text={line} /></Link></li>
      );
    })}</ul>
  );
}

/** The checks of a story with no Flows tab (§2.3), at the end of its first tab. */
function StoryCauses({ sr }: { sr: StoryReading }) {
  const causes = shown(sr.causes ?? [], useWs().hidden);
  if (!causes.length) return null;
  return <section className="st-other" aria-label="Checks in this story"><h3>Checks in this story</h3><Chips causes={causes} /></section>;
}

/** Flows (§2.3): a numbered card per flow with the account's section for it (else the flow's text) and its checks;
 * then the story's checks that touch no flow, then what it means for the rest. */
function Flows({ detail, sr, flows }: { detail: StoryDetail; sr: StoryReading; flows: BoardFlow[] }) {
  const ws = useWs(), d = ws.data, lit = ws.addr.flow;
  const parts = sr.account ?? [], effects = parts.find((p) => p.kind === "effects");
  const causes = shown(sr.causes ?? [], ws.hidden);
  const labels = new Map(detail.board.nodes.map((n) => [n.id, n.label]));
  useEffect(() => { if (lit) document.getElementById(`flow-${lit}`)?.scrollIntoView({ block: "start" }); }, [lit]);
  const ids = new Set(flows.map((f) => f.id)), loose = causes.filter((c) => !c.flows.some((f) => ids.has(f)));
  return (
    <div className="st-flows">
      {flows.map((f, i) => {
        const label = flowLabel(f, (n) => labels.get(n) ?? d.names[n]?.label), part = flowPart(parts, f);
        return (
          <section key={f.id} id={`flow-${i + 1}`} className={`st-flow${lit === i + 1 ? " lit" : ""}`} aria-label={`Flow ${i + 1}: ${label}`}>
            <h3><span className="st-flow-n">{i + 1}</span> <span className="mono">{label}</span></h3>
            {part ? <AiText><NameText text={part.text} /></AiText>
              : <AiText ai={f.what_source === "llm"}><NameText text={f.what} /></AiText>}
            <Chips causes={causes.filter((c) => c.flows.includes(f.id))} />
          </section>
        );
      })}
      {!flows.length && <p className="muted">No flows in this story.</p>}
      {loose.length > 0 && <section className="st-other" aria-label="Other checks in this story"><h3>Other checks in this story</h3><Chips causes={loose} /></section>}
      {effects && <section className="st-effects" aria-label={effects.heading}><h3>{effects.heading}</h3>
        <AiText><NameText text={effects.text} /></AiText></section>}
    </div>
  );
}

/** Talk (§2.4): the strong model's questions and suggested checks, then the story's comment thread. */
function Talk({ detail }: { detail: StoryDetail }) {
  const d = useWs().data, ai = useAi(), st = detail.story, questions = st.questions ?? [], suggested = st.check ?? [];
  const model = storyModel(st, ai?.view);
  return (
    <section aria-labelledby="ws-talk" className="ws-talk">
      <h3 id="ws-talk">Questions and comments</h3>
      {questions.length > 0 && <ul className="st-questions">{questions.map((q, k) => (
        <AiText key={k} as="li" by={model}><NameText text={q} /></AiText>
      ))}</ul>}
      {suggested.length > 0 && <div className="st-suggested"><h4>Also worth checking</h4>
        <AiText as="div" by={model}><ul>{suggested.map((c, k) => <li key={k}><NameText text={c} /></li>)}</ul></AiText></div>}
      <Comments reviewId={d.id} comments={d.comments} kind="story" anchor={{ id: st.id }} onChange={d.loadComments} compact />
    </section>
  );
}

/** The story's tabs and their counts. */
export function tabsFor(detail: StoryDetail, sr: StoryReading, flows: number, graph: boolean, comments: Comment[]): TabSpec[] {
  const st = detail.story;
  const talk = (st.questions?.length ?? 0) + comments.filter((c) => c.parent_id === null && c.anchor_kind === "story" && c.anchor.id === st.id).length;
  return storyTabs(st.kind, { flows, contracts: sr.contracts.length, where: sr.where.length, paths: sr.paths.length,
                              code: codeOrder(sr.where, sr.contracts).length, talk }, graph);
}

/** The tab row (§2.2): a link per tab with its count; switching is a step Back returns from. */
export function StoryTabNav({ tabs, active, sid }: { tabs: TabSpec[]; active: TabSec; sid: string }) {
  const ws = useWs();
  return (
    <nav className="st-tabs" aria-label="Story sections">{tabs.map((t) => {
      const to: Address = t.sec === "graph" ? { ...ws.addr, place: { kind: "story", sid, view: "graph" }, sec: undefined }
        : { ...ws.addr, place: { kind: "story", sid, view: "steps" }, sec: t.sec === tabs[0].sec ? undefined : t.sec,
            flow: t.sec === "flows" ? ws.addr.flow : null };
      return (
        <Link key={t.sec} to={ws.link(to)} className={active === t.sec ? "on" : undefined} aria-current={active === t.sec ? "page" : undefined}>
          {t.label}{t.count ? <span className="st-tabn"> {t.count}</span> : null}</Link>
      );
    })}</nav>
  );
}

/** A story with a reading (spec 2026-10-16-outline-and-causes §2): its tabs and the open one's body. */
export default function StoryTabs({ detail, sr, flows, tabs }: { detail: StoryDetail; sr: StoryReading; flows: BoardFlow[]; tabs: TabSpec[] }) {
  const ws = useWs(), st = detail.story;
  const active = tabs.find((t) => t.sec !== "graph" && t.sec === ws.addr.sec)?.sec ?? tabs[0].sec;
  const causesAt = tabs.some((t) => t.sec === "flows") ? null : (tabs.find((t) => t.sec === "changes") ?? tabs[0]).sec;   // Flows holds them otherwise
  return <>
    <StoryTabNav tabs={tabs} active={active} sid={st.id} />
    <div className="st-panel">
      {active === "flows" && <Flows detail={detail} sr={sr} flows={flows} />}
      {active === "changes" && (st.kind === "mechanical" ? <MechanicalStory detail={detail} />
        : st.kind === "tests" ? <TestsStory detail={detail} /> : <StoryWhy detail={detail} />)}
      {active === "contracts" && <Contracts sr={sr} />}
      {active === "where" && <Where sr={sr} />}
      {active === "paths" && <CallPaths sr={sr} detail={detail} />}
      {active === "code" && <Code sr={sr} detail={detail} />}
      {active === "talk" && <Talk detail={detail} />}
      {causesAt === active && <StoryCauses sr={sr} />}
    </div>
  </>;
}
