import type { BoardFlow } from "../board/types";

/** The flow to show (0-based): the address's `flow=` (1-based), else the first through the open node, else the first. */
export function pickFlow(flows: Pick<BoardFlow, "path">[], flow: number | null, node: string | null): number {
  if (!flows.length) return 0;
  if (flow) return Math.min(flow, flows.length) - 1;
  return Math.max(0, flows.findIndex((f) => !!node && f.path.includes(node)));
}

export const wrap = (i: number, by: number, n: number) => (n ? (((i + by) % n) + n) % n : 0);
