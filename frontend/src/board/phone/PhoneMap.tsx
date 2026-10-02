import { type ReactNode, useRef, useState } from "react";
import type { Comment } from "../../api";
import { CardBody } from "../CardLayer";
import type { LensStrength } from "../lens";
import type { Action, BoardState } from "../reducer";
import type { Board } from "../types";
import type { useSources } from "../useSources";

interface Props {
  children: ReactNode;                                  // the canvas stage
  reviewId: number;
  board: Board;
  state: BoardState;
  act: (a: Action) => void;
  setLayout: (l: "layers" | "depth") => void;
  onFlow: (i: number) => void;
  sheet: string | null;
  onCloseSheet: () => void;
  onOpenFile: (id: string) => void;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
}

/** Phone Map tab (spec §13.4): the touch canvas, one floating pill (flow picker + ⋯ options) and a code sheet. */
export default function PhoneMap(p: Props) {
  const { board, state, act } = p;
  const [more, setMore] = useState(false);
  const [full, setFull] = useState(false);
  const grip = useRef<number | null>(null);
  const node = board.nodes.find((n) => n.id === p.sheet);
  const value = state.mode === "graph" ? "graph" : String(state.flow);
  return (
    <div className="ph-mapwrap">
      {p.children}
      <div className="ph-pill">
        <select aria-label="Flow" value={value} onChange={(e) => {
          if (e.target.value === "graph") act({ t: "mode", mode: "graph" }); else p.onFlow(Number(e.target.value));
        }}>
          {board.flows.map((f, i) => <option key={f.id} value={i}>{i + 1} · {f.title}</option>)}
          <option value="graph">Whole graph</option>
        </select>
        <button className="bd-ibtn" aria-label="Map options" aria-expanded={more} onClick={() => setMore(!more)}>⋯</button>
      </div>
      {more && (
        <div className="ph-more">
          <span className="bd-seg">
            {(["layers", "depth"] as const).map((l) => (
              <button key={l} className={`bd-ibtn${state.layout === l ? " on" : ""}`} onClick={() => p.setLayout(l)}>
                {l === "layers" ? "Layers" : "Call depth"}
              </button>
            ))}
          </span>
          <span className="bd-seg">
            {([0, 2, 4] as LensStrength[]).map((m) => (
              <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} onClick={() => act({ t: "lens", lens: m })}>
                {m ? `${m}×` : "Off"}
              </button>
            ))}
          </span>
          {Object.keys(state.moved[state.layout]).length > 0 &&
            <button className="bd-ibtn" onClick={() => act({ t: "layout.reset" })}>Reset layout</button>}
          <span className="ph-tip">Pinch to zoom · drag to pan · long-press a function to move it</span>
        </div>
      )}
      {node && (
        <div className={`ph-sheet${full ? " full" : ""}`}>
          <div className="ph-grip"
               onPointerDown={(e) => { grip.current = e.clientY; e.currentTarget.setPointerCapture(e.pointerId); }}
               onPointerUp={(e) => {                     // drag up: full height; down: half, then away
                 const from = grip.current;
                 grip.current = null;
                 if (from === null) return;
                 const dy = e.clientY - from;
                 if (dy < -40) setFull(true);
                 else if (dy > 60) { if (full) setFull(false); else p.onCloseSheet(); }
               }} />
          <div className="ph-sheet-head">
            <b>{node.label}</b>
            <span className="sp" />
            <button className="bd-ibtn" aria-label={`Open ${node.label} in Files`} onClick={() => p.onOpenFile(node.id)}>⤢</button>
            <button className="bd-ibtn" aria-label="Close code" onClick={() => { setFull(false); p.onCloseSheet(); }}>✕</button>
          </div>
          <div className="ph-sheet-body">
            <CardBody node={node} reviewId={p.reviewId} board={board} sources={p.sources} comments={p.comments} onComments={p.onComments} />
          </div>
        </div>
      )}
    </div>
  );
}
