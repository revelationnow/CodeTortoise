import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import type { Board } from "../board/types";
import Comments from "../components/Comments";
import AiText from "../components/AiText";
import Explain from "../components/Explain";
import { useMenu } from "../lib/useMenu";
import { useWs } from "./context";
import { wrap } from "./flows";
import NameText from "./NameText";

interface Props {
  board: Board;
  /** The flows to step through (a story's, or every flow on the board). */
  flows: Board["flows"];
  index: number;
  onFlow: (i: number) => void;
  /** Graph views list the flow's steps too; the Steps view numbers them below. */
  steps: boolean;
  /** Leave the "what" out (the story's summary already tells it). */
  hideWhat?: boolean;
  /** Shown in place of the flow's text: a flow the graph leaves out. */
  note?: ReactNode;
}

/** The flow strip (spec 2026-10-04-review-workspace §3.6): fixed-width ‹ flow 2 of 5 ›, the tag, the title cut to the
 * width left, a ▾ menu of every flow; below it the flow's text, collapsible. Its controls never move between flows. */
export default function FlowStrip({ board, flows, index, onFlow, steps, hideWhat, note }: Props) {
  const ws = useWs();
  const [open, setOpen] = useState(false);
  const [shut, setShut] = useState(false);
  const { button, menu } = useMenu<HTMLUListElement>(open, () => setOpen(false));   // opens on the flow shown
  const flow = flows[index];
  if (!flow) return null;
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const n = flows.length;
  const warn = flow.severity === "high" || flow.severity === "medium";       // a side effect is red only once judged a hazard
  const why = ws.data.findings.find((f) => flow.findings.includes(f.id) && f.verdict === "hazard")?.verdict_reason;
  return (
    <section className="ws-flow" aria-label="Flow">
      <div className="ws-flow-row">
        <button className="bd-ibtn ws-flow-btn" aria-label="Previous flow" title="Previous flow" disabled={n < 2}
                onClick={() => onFlow(wrap(index, -1, n))}>‹</button>
        <span className="ws-flow-pos">flow {index + 1} of {n}</span>
        <button className="bd-ibtn ws-flow-btn" aria-label="Next flow" title="Next flow" disabled={n < 2}
                onClick={() => onFlow(wrap(index, 1, n))}>›</button>
        <span className={`bd-tag ${flow.tag}`}>{flow.tag}</span>
        <b className="ws-flow-title" title={flow.title}>{flow.title}</b>
        <span className="ws-flow-menu">
          <button ref={button} className="bd-ibtn" aria-label="Every flow" title="Every flow" aria-haspopup="menu" aria-expanded={open}
                  onClick={() => setOpen(!open)}>▾</button>
          {open && (
            <ul role="menu" aria-label="Every flow" ref={menu}>{flows.map((f, i) => (
              <li key={f.id} role="none"><button role="menuitemradio" aria-checked={i === index} tabIndex={-1}
                onClick={() => { setOpen(false); button.current?.focus(); onFlow(i); }}><span className="muted">{i + 1}</span> {f.title}</button></li>
            ))}</ul>
          )}
        </span>
        <button className="bd-ibtn ws-flow-btn" aria-expanded={!shut} aria-label={shut ? "Show the flow's text" : "Hide the flow's text"}
                title={shut ? "Show the flow's text" : "Hide the flow's text"} onClick={() => setShut(!shut)}>{shut ? "+" : "−"}</button>
      </div>
      {!shut && note && <div className="ws-flow-text"><p className="muted">{note}</p></div>}
      {!shut && !note && (
        <div className="ws-flow-text">
          {!hideWhat && <>
            <AiText ai={flow.what_source === "llm"}><NameText text={flow.what} /></AiText>
            <Explain kind="flow" target={flow.id} has={flow.what_source === "llm"} ask={{ kind: "flow", anchor: { id: flow.id }, onAsked: ws.data.loadComments }} />
          </>}
          {steps && (
            <p className="ws-flow-steps">{flow.path.map((id, i) => {
              const node = byId.get(id);
              if (!node) return null;
              return <span key={id}>{i > 0 && <span className="arrow" aria-hidden> → </span>}
                <Link className="ws-name" to={ws.link(ws.opened({ node: id }))} title={`Open ${node.label}'s code`}
                      aria-label={`Open ${node.label}'s code`}>{node.label}</Link></span>;
            })}</p>
          )}
          <p className={`ws-flow-lands${warn ? " warn" : ""}`}>
            <b>{warn ? "⚠ " : ""}Side effect lands on {byId.get(flow.lands)?.label ?? "a function off this graph"}.</b>{" "}
            <NameText text={flow.effect} />
            {why && <> <AiText as="span" className="ws-flow-why"><NameText text={why} /></AiText></>}</p>
          <p className="ws-flow-check"><NameText text={flow.check} /></p>
          <Comments reviewId={ws.data.id} comments={ws.data.comments} kind="flow" anchor={{ id: flow.id }} onChange={ws.data.loadComments} compact />
        </div>
      )}
    </section>
  );
}
