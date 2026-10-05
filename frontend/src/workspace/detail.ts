import type { Board, BoardNode } from "../board/types";

/** The node to show for `nid` and the board it is drawn on: the first board giving its code, else any that has it; a
 * field folded into a story graph's struct is shown as the struct. */
export function locateNode(nid: string, boards: (Board | null | undefined)[]): { node: BoardNode; board: Board } | null {
  let plain: { node: BoardNode; board: Board } | null = null;
  for (const b of boards) {
    if (!b) continue;
    const n = b.nodes.find((x) => x.id === nid) ?? b.nodes.find((x) => x.fields?.some((f) => f.id === nid));
    if (!n) continue;
    if (n.path && n.range) return { node: n, board: b };
    plain ??= { node: n, board: b };
  }
  return plain;
}
