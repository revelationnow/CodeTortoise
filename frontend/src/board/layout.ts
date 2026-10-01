/** World geometry helpers for the board (pure). Two layouts: `layers` (bands by architectural layer, x from the
 * backend's barycentre ordering) and `depth` (rows by call depth from the entry points, ordered here). The viewer may
 * move any node anywhere; moves are kept per layout. */
import { BAND, type Projected } from "./lens";
import type { Board, BoardFlow, BoardNode } from "./types";

export type LayoutKind = "layers" | "depth";
export type Moved = Record<string, { x: number; y?: number }>;
const X_SPACING = 220;

/** Row index (0 = top band) for each layer level present on the board; unlayered nodes (-1) go last. */
export function layerRows(board: Board): Map<number, number> {
  const levels = [...new Set([...board.layers.map((l) => l.level), ...board.nodes.map((n) => n.layer ?? -1)])]
    .sort((a, b) => b - a);
  return new Map(levels.map((lv, i) => [lv, i]));
}

export const worldY = (row: number) => row * BAND + BAND / 2;

/** Row per node by call depth: entry points (no caller on the board) on row 0, each callee one row below its
 * nearest caller; functions reachable only through cycles start from the changed functions (then any unplaced
 * node); a field sits one row below its deepest writer (or reader when nothing writes it). */
export function callDepth(board: Board): Map<string, number> {
  const fns = board.nodes.filter((n) => n.kind === "function");
  const calls = board.edges.filter((e) => e.kind === "call" || e.kind === "virtual");
  const isFn = new Set(fns.map((n) => n.id)), callers = new Map<string, number>();
  for (const e of calls) callers.set(e.dst, (callers.get(e.dst) ?? 0) + 1);
  const depth = new Map<string, number>();
  const walk = (seeds: string[]) => {
    const q = seeds.filter((id) => !depth.has(id));
    q.forEach((id) => depth.set(id, 0));
    while (q.length) {
      const id = q.shift()!;
      for (const e of calls) {
        if (e.src !== id || depth.has(e.dst) || !isFn.has(e.dst)) continue;
        depth.set(e.dst, depth.get(id)! + 1);
        q.push(e.dst);
      }
    }
  };
  walk(fns.filter((n) => !callers.get(n.id)).map((n) => n.id));
  walk(fns.filter((n) => n.change).map((n) => n.id));
  for (const n of fns) walk([n.id]);
  for (const f of board.nodes.filter((n) => n.kind === "field")) {
    const by = (kind: string) => board.edges.filter((e) => e.dst === f.id && e.kind === kind && depth.has(e.src))
      .map((e) => depth.get(e.src)!);
    const users = by("writes").length ? by("writes") : by("reads");
    depth.set(f.id, users.length ? Math.max(...users) + 1 : 0);
  }
  return depth;
}

/** World x per node: each row ordered by barycentre sweeps (down, up, down, up) to cut crossings, spaced
 * X_SPACING apart and centred on 0 — the same ordering the backend uses for layer bands. */
export function barycentreX(rowOf: Map<string, number>, edges: { src: string; dst: string }[], sweeps = 4,
                            width?: (id: string) => number): Map<string, number> {
  const order = new Map<number, string[]>();
  for (const id of [...rowOf.keys()].sort((a, b) => a.length - b.length || (a < b ? -1 : a > b ? 1 : 0)))
    order.set(rowOf.get(id)!, [...(order.get(rowOf.get(id)!) ?? []), id]);
  const nbrs = new Map<string, Set<string>>();
  for (const { src, dst } of edges) {
    if (!rowOf.has(src) || !rowOf.has(dst) || rowOf.get(src) === rowOf.get(dst)) continue;
    nbrs.set(src, (nbrs.get(src) ?? new Set()).add(dst));
    nbrs.set(dst, (nbrs.get(dst) ?? new Set()).add(src));
  }
  const rows = [...order.keys()].sort((a, b) => a - b);
  for (let s = 0; s < sweeps; s++) {
    const seq = s % 2 === 0 ? rows : [...rows].reverse();
    for (let i = 1; i < seq.length; i++) {
      const ref = new Map(order.get(seq[i - 1])!.map((id, j) => [id, j]));
      const cur = order.get(seq[i])!;
      const bc = (id: string) => {
        const ps = [...(nbrs.get(id) ?? [])].filter((m) => ref.has(m)).map((m) => ref.get(m)!);
        return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : cur.indexOf(id);
      };
      order.set(seq[i], [...cur].sort((a, b) => bc(a) - bc(b) || cur.indexOf(a) - cur.indexOf(b)));
    }
  }
  const xs = new Map<string, number>();
  for (const ids of order.values()) {
    if (!width) {
      ids.forEach((id, i) => xs.set(id, (i - (ids.length - 1) / 2) * X_SPACING));
      continue;
    }
    // packed by width: neighbours GAP apart edge to edge (at least X_SPACING centre to centre), row centred on 0
    const ws = ids.map(width), steps = ws.slice(1).map((w, i) => Math.max(X_SPACING, (ws[i] + w) / 2 + GAP));
    const total = steps.reduce((a, b) => a + b, 0);
    let x = -total / 2;
    ids.forEach((id, i) => { if (i) x += steps[i - 1]; xs.set(id, x); });
  }
  return xs;
}

const GAP = 40;
/** Estimated on-screen width of a node at scale 1 (monospace label; changed nodes carry the +a −d counts). */
export const nodeWidth = (n: BoardNode) => Math.max(120, n.label.length * 7.6 + 30 + (n.change ? 90 : 0));

export function depthPositions(board: Board): Map<string, number> {
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  return barycentreX(callDepth(board), board.edges, 4, (id) => nodeWidth(byId.get(id)!));
}

/** The layers say little: one layer, or one layer holding at least 70% of the nodes. */
export function preferDepth(board: Board): boolean {
  const count = new Map<number, number>();
  for (const n of board.nodes) count.set(n.layer ?? -1, (count.get(n.layer ?? -1) ?? 0) + 1);
  return count.size <= 1 || Math.max(...count.values()) >= 0.7 * board.nodes.length;
}

export interface Band { key: string; row: number; label: string }
export function bandsFor(board: Board, layout: LayoutKind): Band[] {
  if (layout === "depth") {
    const rows = Math.max(0, ...callDepth(board).values()) + 1;
    return Array.from({ length: board.nodes.length ? rows : 0 }, (_, i) => ({ key: `d${i}`, row: i, label: i ? `depth ${i}` : "depth 0 · entry" }));
  }
  const names = new Map(board.layers.map((l) => [l.level, l.name]));
  return [...layerRows(board)].map(([lv, row]) => ({ key: `l${lv}`, row, label: lv >= 0 ? `L${lv} · ${names.get(lv) ?? ""}` : "other" }));
}

export interface WorldNode { id: string; x: number; y: number }
export function worldNodes(board: Board, layout: LayoutKind, moved: Moved): Map<string, WorldNode> {
  let home: (id: string) => { x: number; y: number };
  if (layout === "depth") {
    const rows = callDepth(board), xs = depthPositions(board);
    home = (id) => ({ x: xs.get(id) ?? 0, y: worldY(rows.get(id) ?? 0) });
  } else {
    const rows = layerRows(board), byId = new Map(board.nodes.map((n) => [n.id, n]));
    home = (id) => ({ x: byId.get(id)!.x, y: worldY(rows.get(byId.get(id)!.layer ?? -1) ?? 0) });
  }
  return new Map(board.nodes.map((n) => {
    const h = home(n.id), m = moved[n.id];
    return [n.id, { id: n.id, x: m?.x ?? h.x, y: m?.y ?? h.y }];
  }));
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
