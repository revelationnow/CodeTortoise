import { Link } from "react-router-dom";
import { api } from "../api";
import { useMe } from "../App";
import { SeverityBadge } from "../components/Badges";
import Comments from "../components/Comments";
import Explain from "../components/Explain";
import { useAi } from "../lib/ai";
import { tidy } from "../lib/tidy";
import { citeTarget } from "../stories/stories";
import type { Address } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { depotFor } from "./evidence";
import NameText from "./NameText";

const STATE = { open: "open", ack: "acknowledged", dismissed: "dismissed" } as const;
const VERDICT = { hazard: "hazard", needs_review: "needs review", no_hazard: "no hazard" } as const;

/** A finding (spec 2026-10-04-review-workspace §3.3): where it lives, the AI analysis first, then the evidence, each
 * line opening the diff at that line. */
export default function FindingPage({ fid }: { fid: string }) {
  const ws = useWs(), d = ws.data, me = useMe(), ai = useAi();
  const i = d.findings.findIndex((x) => x.id === fid), f = d.findings[i];
  const n = d.findings.length;
  const sid = d.stories?.finding_story[fid] ?? null, st = sid ? d.stories!.stories.find((s) => s.id === sid) : null;
  const first = f.nodes.find((x) => d.names[x]) ?? f.nodes[0] ?? null;
  const cluster = d.overview?.clusters.find((c) => c.finding_ids.includes(fid)) ?? null;
  const graph: Address | null = !first ? null
    : st && (st.kind === "behaviour" || st.kind === "other") ? { ...ws.item({ kind: "story", sid: st.id, view: "graph" }), place: { kind: "story", sid: st.id, view: "graph" }, open: { node: first }, tab: "diff" }
    : cluster ? { ...ws.item({ kind: "cluster", cid: cluster.id }), open: { node: first }, tab: "diff" }
    : d.board ? { place: { kind: "whole", view: "graph" }, flow: null, open: { node: first }, tab: "diff" } : null;
  const tree = d.about?.tree.flatMap((t) => t.files) ?? [];
  const cls = [...new Set(tree.filter((t) => f.files?.includes(t.path)).flatMap((t) => t.cls))].sort((a, b) => a - b);
  const depots = [...(f.files ?? []), ...d.files.map((x) => x.depot), ...Object.values(d.names).flatMap((x) => (x.path ? [x.path] : []))];
  const step = (by: number) => {
    const to = d.findings[((i + by) % n + n) % n];
    const label = `${by < 0 ? "Previous" : "Next"} finding: ${to.id} ${short(tidy(to.title))}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link({ ...ws.item({ kind: "finding", fid: to.id }), details: true })} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };
  const name = (nid: string) => {
    const label = d.names[nid]?.label ?? "a function";
    return <Link key={nid} className="ws-name" to={ws.link(ws.opened({ node: nid }))} title={`Open ${label}'s code`}
                 aria-label={`Open ${label}'s code`}>{label}</Link>;
  };
  const talk = { kind: "finding" as const, anchor: { kind: f.kind, title: f.title }, onAsked: d.loadComments };
  return (
    <div className="ws-page"><div className="ws-text ws-finding">
      <header className="ws-story-head">
        <div className="ws-story-title">
          <h2><SeverityBadge severity={f.severity} /> {tidy(f.title)}</h2>
          <span className="ws-pos">{step(-1)}<span>{f.id} of {n}</span>{step(1)}</span>
        </div>
        <p className="ws-story-meta">
          <span className="muted">{f.kind.replace(/_/g, " ")}</span>
          <span className={`ws-badge state-${f.state}`}>{STATE[f.state]}</span>
          {me?.is_owner && (["open", "ack", "dismissed"] as const).filter((s) => s !== f.state).map((s) => (
            <button key={s} className="link small" onClick={() => api.setFindingState(d.id, f.id, s).then(d.loadFindings)}>
              mark {STATE[s]}</button>
          ))}
        </p>
        {f.verdict_source === "tier1" && f.verdict ? (
          <p className={`ws-verdict ${f.verdict}`}>
            <span className="ai-label">AI</span>AI review: {VERDICT[f.verdict]} — <NameText text={f.verdict_reason ?? ""} />
            {(f.verdict_cites ?? []).length > 0 && <span className="ws-cites"> · cites {(f.verdict_cites ?? []).map((c, k) => {
              const t = citeTarget(c), depot = t && "file" in t ? depotFor(t.file, depots) : null;
              const link = t && "node" in t && d.names[c] ? <Link to={ws.link(ws.opened({ node: c }))} title={`Open ${d.names[c].label}'s code`}>{d.names[c].label}</Link>
                : t && "file" in t && depot ? <Link className="mono" to={ws.link(ws.opened({ file: depot, line: t.line }))} title={`Open ${c}`}>{c}</Link>
                : <span className="mono">{c}</span>;
              return <span key={c}>{k > 0 && ", "}{link}</span>;
            })}</span>}
          </p>
        ) : f.side_effect && (
          <p className={`ws-verdict${f.verdict === "hazard" ? " hazard" : ""}`}>
            {f.verdict === "hazard" ? <><span className="ai-label">AI</span>AI: hazard — <NameText text={f.verdict_reason ?? ""} /></>
              : f.verdict === "no_hazard" ? <><span className="ai-label">AI</span>AI: no clear hazard — <NameText text={f.verdict_reason ?? ""} /></>
              : <>Side effect · not yet assessed. Side effects are normal; ✦ Explain asks the AI whether this one is a hazard.</>}
          </p>
        )}
      </header>
      <section aria-labelledby="ws-where" className="ws-where">
        <h3 id="ws-where">Where it lives</h3>
        <ul>
          {st && <li>Story: <Link to={ws.link(ws.item({ kind: "story", sid: st.id, view: "steps" }))} title={`Go to story ${st.id}: ${short(st.title)}`}
                                  aria-label={`Go to story ${st.id}: ${short(st.title)}`}>{short(st.title, 70)}</Link><span className="ws-handle">{st.id}</span></li>}
          {graph && <li><Link to={ws.link(graph)} title="Show it on the graph" aria-label="Show it on the graph">On the graph</Link>
            {cluster && !st && <span className="muted"> · {cluster.name}</span>}</li>}
          {cls.length > 0 && <li>Changelists: {cls.map((c) => (
            <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
          ))}</li>}
          {f.nodes.length > 0 && <li>Functions: {f.nodes.map((x, k) => <span key={x}>{k > 0 && ", "}{name(x)}</span>)}</li>}
        </ul>
      </section>
      <section aria-labelledby="ws-ai">
        <h3 id="ws-ai">AI analysis</h3>
        {f.explanation ? <p><span className="ai-label">AI</span><NameText text={f.explanation} /> <Explain kind="finding" target={f.id} has ask={talk} /></p>
          : !ai?.view ? <p className="muted">Checking for AI analysis…</p>
          : !ai.view.llm ? <p className="muted">AI analysis unavailable.</p>
          : <p className="muted">Not written yet. <Explain kind="finding" target={f.id} has={false} ask={talk} /></p>}
      </section>
      <section aria-labelledby="ws-ev">
        <h3 id="ws-ev">Evidence</h3>
        <p><NameText text={tidy(f.summary)} /></p>
        <ul className="ws-evidence">{f.evidence.map((e, k) => {
          const depot = e.file ? depotFor(e.file, depots) : null, file = depot ?? e.file;
          const fileTail = file ? file.split("/").slice(-2).join("/") : null;
          return (
            <li key={k} className={`sev-${e.severity}`}><NameText text={tidy(e.text)} />
              {depot ? <> <Link className="mono small" to={ws.link(ws.opened({ file: depot, line: e.line }))}
                                title={`Open ${fileTail}${e.line ? ` at line ${e.line}` : ""}`}
                                aria-label={`Open ${fileTail}${e.line ? ` at line ${e.line}` : ""}`}>{fileTail}{e.line ? `:${e.line}` : ""}</Link></>
                : fileTail && <span className="mono small muted"> {fileTail}{e.line ? `:${e.line}` : ""}</span>}
            </li>
          );
        })}</ul>
      </section>
      {f.verify_steps.length > 0 && (
        <section aria-labelledby="ws-verify"><h3 id="ws-verify">Verify</h3>
          <ol>{f.verify_steps.map((s, k) => <li key={k}><NameText text={s} /></li>)}</ol></section>
      )}
      {f.hypotheses.length > 0 && (
        <section aria-labelledby="ws-hyp"><h3 id="ws-hyp">Possible side effects</h3>
          <ul>{f.hypotheses.map((h, k) => (
            <li key={k}><span className="ai-label">AI</span><NameText text={h.text} />
              {h.cites.filter((c) => c.startsWith("N")).length > 0 && <span className="muted"> — {h.cites.filter((c) => c.startsWith("N")).map((c, j) => <span key={c}>{j > 0 && ", "}{name(c)}</span>)}</span>}</li>
          ))}</ul></section>
      )}
      <section aria-labelledby="ws-fc"><h3 id="ws-fc">Comments</h3>
        <Comments reviewId={d.id} comments={d.comments} kind="finding" anchor={{ kind: f.kind, title: f.title }} onChange={d.loadComments} compact />
      </section>
    </div></div>
  );
}
