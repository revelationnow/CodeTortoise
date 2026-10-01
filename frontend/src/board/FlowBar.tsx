import { useState } from "react";
import type { BoardState } from "./reducer";
import type { Board } from "./types";

interface Props {
  board: Board;
  state: BoardState;
  layerOf: (id: string) => string;
  onFlow: (i: number) => void;
  onStep: (id: string) => void;
  onStepOpen: (id: string) => void;
}

/** Numbered flow chips and the selected flow's summary (spec §2), or graph totals in Whole graph mode. */
export default function FlowBar({ board, state, layerOf, onFlow, onStep, onStepOpen }: Props) {
  const [details, setDetails] = useState(() => typeof window === "undefined" || window.innerWidth > 640);
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const graph = state.mode === "graph" || !board.flows.length;
  const flow = board.flows[state.flow];
  return (
    <div className="bd-flowbar">
      {board.flows.length > 0 && (
        <div className="bd-flows" role="tablist" aria-label="Call flows">
          {board.flows.map((f, i) => (
            <button key={f.id} role="tab" aria-selected={!graph && i === state.flow}
                    className={`bd-chip${!graph && i === state.flow ? " on" : ""}`} onClick={() => onFlow(i)}>
              <span className="num">{i + 1}</span><span className="path">{f.text}</span>
              <span className={`bd-tag ${f.tag}`}>{f.tag}</span>
            </button>
          ))}
        </div>
      )}
      {graph ? (
        <div className="bd-flowinfo whole">
          <div className="what">
            <b>Whole graph</b> — {board.nodes.length} functions and fields across {board.layers.length} layers;{" "}
            {board.nodes.filter((n) => n.change).length} changed, {new Set(board.flows.map((f) => f.lands)).size} where side effects land.
            {board.hidden_nodes > 0 && <> +{board.hidden_nodes} more functions not shown.</>}
            {" "}Drag a function anywhere to rearrange the graph; your layout is kept for this review.
            {board.flows.length > 0 ? " Pick a flow above to trace one path." : " No flows: the analysis found no side effect to trace."}
          </div>
        </div>
      ) : flow && (
        <div className={`bd-flowinfo${details ? "" : " brief"}`}>
          <div className="fnum">{state.flow + 1}</div>
          <div>
            <div className="what">{flow.what}</div>
            <div className="steps">
              {flow.path.map((id, i) => {
                const n = byId.get(id);
                if (!n) return null;
                const kind = n.change ? "chg" : n.kind === "field" ? "field" : id === flow.lands || id === flow.fx_at ? "fx" : "";
                const open = state.cards[id] && !state.cards[id].collapsed;
                const code = !!(n.path && n.range);
                return (
                  <span key={id} className="bd-stepwrap">
                    {i > 0 && <span className="arrow">→</span>}
                    <span className={`step ${kind}${open ? " open" : ""}`} title={code ? "Show / hide the code" : undefined}
                          onClick={() => code && onStep(id)}>
                      {n.label}
                      {code && <span className="sgo" title="Open in full view" role="button" aria-label={`Open ${n.label} in full view`}
                                     onClick={(e) => { e.stopPropagation(); onStepOpen(id); }}>⤢</span>}
                    </span>
                  </span>
                );
              })}
              <span className="arrow count">· {flow.path.length} steps · {new Set(flow.path.map((id) => byId.get(id)?.layer)).size} layers</span>
              <button className="bd-more" onClick={() => setDetails(!details)}>{details ? "Less" : "Details"}</button>
            </div>
          </div>
          <div className="landing">
            <span className="k">⚠ Side effect lands on {byId.get(flow.lands)?.label} ({layerOf(flow.lands)})</span>
            {flow.effect}
            <div className="chk">{flow.check}</div>
          </div>
        </div>
      )}
    </div>
  );
}
