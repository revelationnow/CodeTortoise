/** World geometry helpers for the board (pure). The backend chooses initial x (barycentre ordering); the viewer may
 * move nodes within their layer. */
import { BAND, type Projected } from "./lens";
import type { Board, BoardFlow } from "./types";

/** Row index (0 = top band) for each layer level present on the board; unlayered nodes (-1) go last. */
export function layerRows(board: Board): Map<number, number> {
  const levels = [...new Set([...board.layers.map((l) => l.level), ...board.nodes.map((n) => n.layer ?? -1)])]
    .sort((a, b) => b - a);
  return new Map(levels.map((lv, i) => [lv, i]));
}

export const worldY = (row: number) => row * BAND + BAND / 2;

export interface WorldNode { id: string; x: number; y: number }
export function worldNodes(board: Board, moved: Record<string, number>): Map<string, WorldNode> {
  const rows = layerRows(board);
  return new Map(board.nodes.map((n) => [n.id, { id: n.id, x: moved[n.id] ?? n.x, y: worldY(rows.get(n.layer ?? -1) ?? 0) }]));
}

/** Pan that centres the bounding box of `ids` in a W×H canvas. */
export function centrePan(ids: string[], nodes: Map<string, WorldNode>, W: number, H: number) {
  const pts = ids.map((id) => nodes.get(id)).filter((n): n is WorldNode => !!n);
  if (!pts.length) return null;
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  return { panX: W / 2 - (Math.min(...xs) + Math.max(...xs)) / 2, panY: H / 2 - (Math.min(...ys) + Math.max(...ys)) / 2 };
}

/** Node ids and call edges ("a>b") on the selected flow; empty in whole-graph mode. */
export function flowSets(flow: BoardFlow | undefined, graph: boolean) {
  if (graph || !flow) return { onPath: new Set<string>(), pairs: new Set<string>() };
  return { onPath: new Set(flow.path), pairs: new Set(flow.path.slice(1).map((b, i) => `${flow.path[i]}>${b}`)) };
}

const NODE_HALF = 100;                             // about half a changed node's width, in screen px at scale 1

export interface Rect { x: number; y: number; w: number; h: number }
export interface CardBox { id: string; at: Projected; w: number; h: number; collapsed: boolean; offset?: { x: number; y: number } }

/** Screen rectangles for cards (spec §3.4): pills under their node; dragged cards follow their node at the chosen
 * offset; others go right/left/above of the node, then into canvas corners — first free spot, else least overlap. */
export function placeCards(cards: CardBox[], W: number, H: number): Map<string, Rect & { k: number }> {
  const placed: Rect[] = [], out = new Map<string, Rect & { k: number }>();
  const area = (a: Rect, b: Rect) =>
    Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
  const overlap = (r: Rect) => placed.reduce((s, q) => s + area(r, q), 0);
  for (const c of cards) {
    const p = c.at, k = c.collapsed ? 1 : Math.max(0.55, p.s), cw = c.w * k, ch = Math.min(c.h * k, H - 16);
    const cx = (x: number) => Math.max(8, Math.min(x, W - cw - 8)), cy = (y: number) => Math.max(8, Math.min(y, H - ch - 8));
    let r: Rect;
    if (c.collapsed) r = { x: cx(p.x - cw / 2), y: cy(p.y + 24 * p.s), w: cw, h: ch };
    else if (c.offset) r = { x: p.x + c.offset.x, y: p.y + c.offset.y, w: cw, h: ch };
    else {
      const gap = NODE_HALF * p.s;                 // clear of the node itself, so its ⤢ button stays reachable
      const cands = [[p.x + gap, p.y - 40], [p.x - gap - cw, p.y - 40], [p.x + gap, p.y - ch + 40],
        [p.x - gap - cw, p.y - ch + 40], [W - cw - 8, 8], [8, 8], [W - cw - 8, H - ch - 8], [8, H - ch - 8]]
        .map(([x, y]) => ({ x: cx(x), y: cy(y), w: cw, h: ch }));
      r = cands.find((t) => overlap(t) === 0) ?? cands.reduce((b, t) => (overlap(t) < overlap(b) ? t : b));
    }
    placed.push(r);
    out.set(c.id, { ...r, k });
  }
  return out;
}
