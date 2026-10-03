import { useEffect, useRef, useState } from "react";
import type { Comment } from "../../api";
import Explain from "../../components/Explain";
import { CardBody } from "../CardLayer";
import type { Action, BoardState } from "../reducer";
import type { Board } from "../types";
import type { useSources } from "../useSources";
import { flowSteps } from "./flowSteps";

interface Props {
  reviewId: number;
  board: Board;
  state: BoardState;
  act: (a: Action) => void;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
  onOpenFile: (nodeId: string) => void;
}

/** Phone Flows tab (spec §13.3): one flow at a time as a list of steps; swipe or ‹ › between flows. */
export default function FlowReader({ reviewId, board, state, act, sources, comments, onComments, onOpenFile }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const down = useRef<{ x: number; y: number } | null>(null);
  const n = board.flows.length, i = Math.min(state.flow, n - 1), flow = board.flows[i];
  useEffect(() => setOpen(null), [i]);
  if (!flow) return <div className="ph-empty">No flows: the analysis found no side effect to trace. The Map tab shows the whole graph.</div>;
  const go = (k: number) => act({ t: "flow", i: (k + n) % n });
  const steps = flowSteps(board, flow);
  const lands = board.nodes.find((x) => x.id === flow.lands);
  const layer = board.layers.find((l) => l.level === lands?.layer)?.name ?? "unlayered";

  return (
    <div className="ph-reader"
         onPointerDown={(e) => { down.current = (e.target as HTMLElement).closest(".bd-code, textarea, input") ? null : { x: e.clientX, y: e.clientY }; }}
         onPointerUp={(e) => {                         // horizontal swipe between flows (not inside code, which scrolls sideways)
           const d = down.current;
           down.current = null;
           if (!d || n < 2) return;
           const dx = e.clientX - d.x, dy = e.clientY - d.y;
           if (Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) go(dx < 0 ? i + 1 : i - 1);
         }}>
      <div className="ph-pager">
        <button className="ph-nav" aria-label="Previous flow" onClick={() => go(i - 1)} disabled={n < 2}>‹</button>
        <span className="ph-num">{i + 1}</span>
        <span className="ph-title">{flow.title}</span>
        <span className={`bd-tag ${flow.tag}`}>{flow.tag}</span>
        <span className="ph-count">{i + 1}/{n}</span>
        <button className="ph-nav" aria-label="Next flow" onClick={() => go(i + 1)} disabled={n < 2}>›</button>
      </div>
      <div className="ph-what">{flow.what_source === "llm" && <span className="ai-label">AI</span>}{flow.what}{" "}
        <Explain kind="flow" target={flow.id} has={flow.what_source === "llm"} /></div>
      <ol className="ph-steps">
        {steps.map((s) => (
          <li key={s.id} className={`ph-step ${s.kind}${open === s.id ? " open" : ""}`}>
            <div className="ph-head" onClick={() => s.hasCode && setOpen(open === s.id ? null : s.id)}>
              <span className="ph-marker">{s.marker}</span>
              <div className="ph-text"><b>{s.label}</b><span className="ph-reason">{s.reason}</span></div>
              {s.hasCode && <span className="ph-caret">{open === s.id ? "▾" : "▸"}</span>}
            </div>
            {open === s.id && (
              <div className="ph-code">
                <CardBody node={s.node} reviewId={reviewId} board={board} sources={sources} comments={comments} onComments={onComments} />
                <button className="bd-ibtn ph-go" aria-label={`Open ${s.label} in Files`} onClick={() => onOpenFile(s.id)}>⤢ Full file</button>
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="ph-landing">
        <span className="k">⚠ Side effect lands on {lands?.label} ({layer})</span>
        {flow.effect}
        <div className="chk">{flow.check}</div>
      </div>
    </div>
  );
}
