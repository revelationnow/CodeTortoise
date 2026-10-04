import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { Comment, Finding } from "../api";
import { CardBody } from "../board/CardLayer";
import { flowSteps } from "../board/phone/flowSteps";
import type { BoardNode, StoryDetail } from "../board/types";
import type { useSources } from "../board/useSources";
import Explain from "../components/Explain";
import { Ticks } from "./StoryList";
import { SeverityBadge } from "../components/Badges";
import "../board/phone/phone.css";

interface Props {
  reviewId: number;
  detail: StoryDetail;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
  findings: Finding[];
  onCite: (id: string) => void;
  /** A node to open (a citation): its step, or its entry under "Also changed". */
  focus: string | null;
}

/** A story's Steps tab (spec 2026-10-04-change-stories §3.1): each flow as numbered steps, then its other changed
 * functions and its findings. Tapping a step or function opens its code inline. */
export default function StorySteps({ reviewId, detail, sources, comments, onComments, findings, onCite, focus }: Props) {
  const { story, board } = detail;
  const flows = useMemo(() => board.flows.filter((f) => story.flows.includes(f.id)), [board, story]);
  const startFlow = Math.max(0, flows.findIndex((f) => focus && f.path.includes(focus)));
  const [fi, setFi] = useState(startFlow);
  const [open, setOpen] = useState<string | null>(focus);
  const refs = useRef(new Map<string, HTMLElement>());
  useEffect(() => {
    if (!focus) return;
    setOpen(focus);
    const i = flows.findIndex((f) => f.path.includes(focus));
    if (i >= 0) setFi(i);
    window.setTimeout(() => refs.current.get(focus)?.scrollIntoView({ block: "center" }), 0);
  }, [focus, flows]);
  const nodes = useMemo(() => new Map(board.nodes.map((n) => [n.id, n])), [board]);
  const flow = flows[Math.min(fi, flows.length - 1)];
  const steps = flow ? flowSteps(board, flow) : [];
  const lands = flow ? nodes.get(flow.lands) : undefined;
  const others = detail.functions.filter((f) => !f.on_flow || !flow);
  const mine = findings.filter((f) => story.findings.includes(f.id));
  const code = (node: BoardNode) => (
    <div className="ph-code">
      <CardBody node={node} reviewId={reviewId} board={board} sources={sources} comments={comments} onComments={onComments} />
    </div>
  );
  const keep = (id: string) => (el: HTMLElement | null) => { if (el) refs.current.set(id, el); };

  return (
    <div className="st-steps">
      {flow && (
        <section aria-label="Flow steps">
          <div className="st-flowbar">
            <b>{flow.title}</b>
            <span className="st-flownav">
              <span className={`bd-tag ${flow.tag}`}>{flow.tag}</span>
              {flows.length > 1 && <button className="bd-ibtn" aria-label="Previous flow" onClick={() => setFi((fi + flows.length - 1) % flows.length)}>‹</button>}
              {flows.length > 1 && <span className="muted">flow {fi + 1} of {flows.length}</span>}
              {flows.length > 1 && <button className="bd-ibtn" aria-label="Next flow" onClick={() => setFi((fi + 1) % flows.length)}>›</button>}
            </span>
          </div>
          {!story.summary.startsWith(flow.what) && (                  // the story's summary already tells its first flow
            <p className="ph-what">{flow.what_source === "llm" && <span className="ai-label">AI</span>}{flow.what}{" "}
              <Explain kind="flow" target={flow.id} has={flow.what_source === "llm"} /></p>
          )}
          <ol className="ph-steps">
            {steps.map((s) => (
              <li key={s.id} ref={keep(s.id)} className={`ph-step ${s.kind}${open === s.id ? " open" : ""}`}>
                <div className="ph-head" onClick={() => s.hasCode && setOpen(open === s.id ? null : s.id)}>
                  <span className="ph-marker">{s.marker}</span>
                  <div className="ph-text"><b>{s.label}</b><span className="ph-reason"><Ticks text={s.node.note || s.reason} /></span></div>
                  {s.hasCode && <span className="ph-caret">{open === s.id ? "▾" : "▸"}</span>}
                </div>
                {open === s.id && code(s.node)}
              </li>
            ))}
          </ol>
          <div className="ph-landing">
            <span className="k">⚠ Side effect lands on {lands?.label}</span>
            {flow.effect}
            <div className="chk">{flow.check}</div>
          </div>
        </section>
      )}
      {others.length > 0 && (
        <section aria-label="Also changed in this story" className="st-also">
          <h3>{flow ? "Also changed in this story" : "Changed in this story"}</h3>
          <ul>
            {others.map((f) => {
              const n = nodes.get(f.node);
              return (
                <li key={f.node} ref={keep(f.node)} className={open === f.node ? "open" : ""}>
                  <div className="ph-head" onClick={() => n?.path && setOpen(open === f.node ? null : f.node)}>
                    <div className="ph-text"><b>{f.label}</b><span className="ph-reason"><Ticks text={f.note} /></span></div>
                    {f.also.map((sid) => (
                      <Link key={sid} className="bd-pill ghost" to={`/r/${reviewId}/s/${sid}`} onClick={(e) => e.stopPropagation()}>
                        also in {sid} ›</Link>
                    ))}
                    {n?.path && <span className="ph-caret">{open === f.node ? "▾" : "▸"}</span>}
                  </div>
                  {open === f.node && n && code(n)}
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {mine.length > 0 && (
        <section aria-label="Findings in this story" className="st-findings">
          <h3>Findings</h3>
          <ul>
            {mine.map((f) => (
              <li key={f.id}><SeverityBadge severity={f.severity} />{" "}
                <button className="link" onClick={() => onCite(f.id)}>{f.id}: {f.title}</button></li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
