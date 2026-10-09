import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { keys, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import type { StoryDetail } from "../board/types";
import Comments from "../components/Comments";
import { byEntry, codeOrder, foldPath, readOrder, rewriteText, whereByCl, whereTree } from "../reading/story";
import type { CallPath, ContractRow, StoryReading, WhereFile } from "../reading/types";
import CheckTile, { Cleared } from "./CheckList";
import { useWs } from "./context";
import FunctionCode from "./FunctionCode";
import NameText, { Ticks } from "./NameText";
import { MechanicalStory, TestsStory } from "./StoryBodies";
import { CHECK_W, checkMax, loadCheckW } from "./layout";
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
                                      aria-label={label}>{f.label}</Link> : <span className="mono">{f.label}</span>}
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

/** Before → after beside Where (§6.1). */
function ContractAndWhere({ sr }: { sr: StoryReading }) {
  const ws = useWs();
  const order = readOrder(sr.cl_order), grouped = (sr.cl_order?.length ?? 0) > 1;    // phase 2 §5.3
  return (
    <div className="st-pair">
      {sr.contracts.length > 0 && (
        <section className="ws-tile" aria-label="Before → after">
          <h3>Before → after</h3>
          <ul className="st-contracts">{sr.contracts.map((r, i) => <Contract key={i} row={r} />)}</ul>
        </section>
      )}
      {sr.where.length > 0 && (
        <section className="ws-tile" aria-label="Where">
          <h3>Where</h3>
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
              return (
                <li key={i}>{t.lead}{" "}
                  <Link className="mono" to={ws.link(ws.opened({ file: r.file, line: r.line }))} title={label} aria-label={label}>{t.name}</Link></li>
              );
            })}</ul>
          )}
        </section>
      )}
    </div>
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

/** A story in layout B (spec 2026-10-07-review-reading §6): what it does, Before → after beside Where and its call
 * paths on the left, its To check pinned on the right; its code and questions below. */
export default function StoryTiles({ detail, sr }: { detail: StoryDetail; sr: StoryReading }) {
  const ws = useWs(), d = ws.data, st = detail.story;
  const suggested = st.check ?? [], questions = st.questions ?? [];
  const page = useRef<HTMLDivElement>(null);
  const [checkW, setCheckW] = useState(loadCheckW);
  return (
    <div className="ov2 st-tiles" ref={page} style={{ ["--cw" as string]: `${checkW}px` }}>
      <div className="ov2-left">
        <section aria-labelledby="st-what">
          <h3 id="st-what">What it does</h3>
          <p>{st.text_source === "llm" && <span className="ai-label">AI</span>}<NameText text={st.purpose || st.summary} />
            {sr.place_text && <span className="st-place"> {sr.place_text}</span>}</p>
          {st.kind === "unsorted" && <StoryWhy detail={detail} />}
        </section>
        {st.kind === "mechanical" ? <MechanicalStory detail={detail} /> : st.kind === "tests" ? <TestsStory detail={detail} /> : <>
          <ContractAndWhere sr={sr} />
          <CallPaths sr={sr} detail={detail} />
          <Code sr={sr} detail={detail} />
        </>}
        <section aria-labelledby="ws-talk" className="ws-talk">
          <h3 id="ws-talk">Questions and comments</h3>
          {questions.length > 0 && <ul className="st-questions">{questions.map((q, k) => (
            <li key={k}><span className="ai-label">AI</span><NameText text={q} /></li>))}</ul>}
          <Comments reviewId={d.id} comments={d.comments} kind="story" anchor={{ id: st.id }} onChange={d.loadComments} compact />
        </section>
      </div>
      <div className="st-check">
        <Resizer size={checkW} edge="left" min={CHECK_W.min} max={() => checkMax(page.current?.clientWidth ?? 0)}
                 onSize={setCheckW} onDone={(w) => save(keys.checkW, w)}
                 onReset={() => { setCheckW(CHECK_W.def); save(keys.checkW, CHECK_W.def); }} />
        <aside className="ov2-right" aria-label="What to check in this story">
          <CheckTile groups={[{ label: null, checks: sr.checks }]} ofTotal footer={<>
            {suggested.length > 0 && (
              <div className="st-suggested"><h4><span className="ai-label">AI</span>The strong model also suggests</h4>
                <ul>{suggested.map((c, k) => <li key={k}><NameText text={c} /></li>)}</ul></div>
            )}
            <Cleared checks={(d.reading?.cleared ?? []).filter((k) => k.story === st.id)} />
          </>} />
        </aside>
      </div>
    </div>
  );
}
