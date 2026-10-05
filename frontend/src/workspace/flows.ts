import type { BoardFlow } from "../board/types";

/** The flow to show (0-based): the address's `flow=` (1-based), else the first through the open node, else the first. */
export function pickFlow(flows: Pick<BoardFlow, "path">[], flow: number | null, node: string | null): number {
  if (!flows.length) return 0;
  if (flow) return Math.min(flow, flows.length) - 1;
  return Math.max(0, flows.findIndex((f) => !!node && f.path.includes(node)));
}

/** Where a story's flow `flows[index]` is among its graph's flows, matched by id: -1 when the graph leaves it out (its
 * path is too long to draw). The address's `flow=` numbers the story's flows, so both views mean the same one. */
export function drawnIndex(flows: Pick<BoardFlow, "id">[], index: number, drawn: Pick<BoardFlow, "id">[]): number {
  const id = flows[index]?.id;
  return id ? drawn.findIndex((f) => f.id === id) : -1;
}

export const wrap = (i: number, by: number, n: number) => (n ? (((i + by) % n) + n) % n : 0);
