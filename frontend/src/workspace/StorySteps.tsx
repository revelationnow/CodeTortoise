import { Link } from "react-router-dom";
import { flowSteps } from "../board/phone/flowSteps";
import type { BoardFlow, StoryDetail } from "../board/types";
import { SeverityBadge } from "../components/Badges";
import { tidy } from "../lib/tidy";
import { useWs } from "./context";
import { short } from "./crumbs";
import NameText from "./NameText";

/** A story's Steps view (spec 2026-10-04-review-workspace §3.2; change stories §3.1): the flow's numbered steps, its
 * other changed functions and its findings. A step opens its code in the detail panel and is marked while open. */
export default function StorySteps({ detail, flow }: { detail: StoryDetail; flow: BoardFlow | undefined }) {
  const ws = useWs(), d = ws.data, { story, board } = detail;
  const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
  const nodes = new Map(board.nodes.map((n) => [n.id, n]));
  const steps = flow ? flowSteps(board, flow) : [];
  const others = detail.functions.filter((f) => !f.on_flow || !flow);
  const mine = d.findings.filter((f) => story.findings.includes(f.id));
  const code = (id: string) => ws.link(ws.opened(open === id ? null : { node: id }));
  return (
    <div className="ws-steps">
      {flow && (
        <ol className="ws-steplist" aria-label="Flow steps">
          {steps.map((s) => (
            <li key={s.id} className={`${s.kind}${open === s.id ? " open" : ""}`}>
              <Link to={code(s.id)} aria-current={open === s.id ? "true" : undefined}
                    title={open === s.id ? `Close ${s.label}'s code` : `Open ${s.label}'s code`}
                    aria-label={open === s.id ? `Close ${s.label}'s code` : `Open ${s.label}'s code`}>
                <span className="ws-marker" aria-hidden>{s.marker}</span>
                <span className="ws-step-text"><b className="mono">{s.label}</b><span className="muted"><NameText text={s.node.note || s.reason} /></span></span>
              </Link>
            </li>
          ))}
        </ol>
      )}
      {others.length > 0 && (
        <section aria-labelledby="ws-also">
          <h3 id="ws-also">{flow ? "Also changed in this story" : "Changed in this story"}</h3>
          <ul className="ws-steplist plain">{others.map((f) => (
            <li key={f.node} className={open === f.node ? "open" : ""}>
              <Link to={code(f.node)} aria-current={open === f.node ? "true" : undefined}
                    title={`Open ${f.label}'s code`} aria-label={`Open ${f.label}'s code`}>
                <span className="ws-step-text"><b className="mono">{f.label}</b><span className="muted"><NameText text={f.note} /></span></span>
              </Link>
              {f.also.map((sid) => {
                const st = d.stories?.stories.find((s) => s.id === sid);
                return <Link key={sid} className="ws-also" to={ws.link(ws.item({ kind: "story", sid, view: "steps" }))}
                             title={`Go to story ${sid}${st ? `: ${short(st.title)}` : ""}`}
                             aria-label={`Go to story ${sid}${st ? `: ${short(st.title)}` : ""}`}>also in <span className="ws-handle">{sid}</span></Link>;
              })}
              {!nodes.get(f.node)?.path && <span className="muted small"> no code in this review</span>}
            </li>
          ))}</ul>
        </section>
      )}
      {mine.length > 0 && (
        <section aria-labelledby="ws-sf">
          <h3 id="ws-sf">Findings</h3>
          <ul className="ws-findings">{mine.map((f) => (
            <li key={f.id}><SeverityBadge severity={f.severity} />{" "}
              <Link to={ws.link(ws.item({ kind: "finding", fid: f.id }))} title={`Go to finding ${f.id}: ${short(tidy(f.title))}`}
                    aria-label={`Go to finding ${f.id}: ${short(tidy(f.title))}`}>{tidy(f.title)}</Link><span className="ws-handle">{f.id}</span></li>
          ))}</ul>
        </section>
      )}
    </div>
  );
}
