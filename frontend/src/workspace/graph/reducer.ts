/** A graph's view state (spec 2026-10-04-review-workspace §5: the board reducer, trimmed). Pure: every interaction is
 * one transition. The flow and the selected node live in the address, not here. */
import type { LayoutKind, Moved } from "../../board/layout";
import type { LensStrength, View } from "../../board/lens";

export interface GraphState {
  view: View;
  /** The selected flow highlighted, or the whole graph. */
  mode: "flows" | "graph";
  layout: LayoutKind;
  /** Per layout: node id -> world position chosen by this viewer. */
  moved: Record<LayoutKind, Moved>;
}

export type GraphAction =
  | { t: "mode"; mode: "flows" | "graph" }
  | { t: "lens"; lens: LensStrength }
  | { t: "node.move"; id: string; x: number; y: number }
  | { t: "layout"; layout: LayoutKind }
  | { t: "layout.reset" }
  | { t: "pan"; panX: number; panY: number };

export function initialGraph(lens: LensStrength = 2, moved: Record<LayoutKind, Moved> = { layers: {}, depth: {} },
                             layout: LayoutKind = "layers"): GraphState {
  return { view: { panX: 0, panY: 0, lens }, mode: "flows", layout, moved };
}

export function reduceGraph(s: GraphState, a: GraphAction): GraphState {
  switch (a.t) {
    case "mode":
      return { ...s, mode: a.mode };
    case "lens":
      return { ...s, view: { ...s.view, lens: a.lens } };
    case "node.move":
      return { ...s, moved: { ...s.moved, [s.layout]: { ...s.moved[s.layout], [a.id]: { x: a.x, y: a.y } } } };
    case "layout.reset":
      return { ...s, moved: { ...s.moved, [s.layout]: {} } };
    case "layout":
      return { ...s, layout: a.layout };
    case "pan":
      return { ...s, view: { ...s.view, panX: a.panX, panY: a.panY } };
  }
}
