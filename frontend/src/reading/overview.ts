/** The overview's connections tile and Tests row (spec 2026-10-07-review-reading §5.1). */
import { letter } from "./checks";
import type { Connection, ConnKind, TestsRow, Thread } from "./types";

export const STEP = 28;               // how much further right each level of nesting reaches
const GAP = 20;                       // the least room between two arc labels

export interface Arc {
  a: string; b: string; kind: ConnKind; text: string; dashed: boolean;
  /** 1 for an arc spanning no other; an arc around others sits one level outside them. */
  depth: number; y1: number; y2: number;
  /** The SVG path, from the right edge of one thread's box (x 0) to the other's. */
  d: string; labelY: number;
}

/** Each shown connection as an arc between the thread boxes stacked `row` px apart, nested so arcs never cross a
 * label, with its label at its middle height pushed down clear of the label above. */
export function arcLayout(threads: Thread[], conns: Connection[], row = 56): { arcs: Arc[]; height: number; reach: number } {
  const at = new Map(threads.map((t, i) => [t.id, i]));
  const spans = conns.filter((k) => k.shown && k.a !== k.b && at.has(k.a) && at.has(k.b))
    .map((k) => ({ k, lo: Math.min(at.get(k.a)!, at.get(k.b)!), hi: Math.max(at.get(k.a)!, at.get(k.b)!) }))
    .sort((x, y) => x.hi - x.lo - (y.hi - y.lo) || x.lo - y.lo);
  const placed: { lo: number; hi: number; depth: number }[] = [];
  const arcs = spans.map(({ k, lo, hi }) => {
    const depth = 1 + Math.max(0, ...placed.filter((p) => p.lo < hi && lo < p.hi).map((p) => p.depth));
    placed.push({ lo, hi, depth });
    const y1 = lo * row + row / 2, y2 = hi * row + row / 2, r = depth * STEP;
    return { a: k.a, b: k.b, kind: k.kind, text: k.text, dashed: k.kind === "bundled", depth, y1, y2,
             d: `M 0 ${y1} C ${r} ${y1}, ${r} ${y2}, 0 ${y2}`, labelY: (y1 + y2) / 2 };
  });
  let last = -Infinity;
  for (const arc of [...arcs].sort((x, y) => x.labelY - y.labelY)) {
    arc.labelY = Math.max(arc.labelY, last + GAP);
    last = arc.labelY;
  }
  return { arcs, height: Math.max(threads.length * row, last + row / 2), reach: Math.max(0, ...arcs.map((a) => a.depth)) * STEP };
}

/** "A and B: both run inside `main`", one per shown connection: the tile on a phone, where arcs do not fit. */
export function connectionRows(threads: Thread[], conns: Connection[]): { text: string; bundled: boolean }[] {
  const name = new Map(threads.map((t, i) => [t.id, letter(i, t.id)]));
  return conns.filter((k) => k.shown && name.has(k.a) && name.has(k.b)).map((k) => ({
    text: `${name.get(k.a)} and ${name.get(k.b)}: ${k.text}${k.kind === "bundled" ? " — ask the author" : ""}`,
    bundled: k.kind === "bundled",
  }));
}

/** "A", "A and B", "A, B and C". */
export function listed(xs: string[]): string {
  return xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
}

/** "Tests: 6 cover threads A and B · nothing tests C". */
export function testsLine(t: TestsRow, threads: Thread[]): string {
  const name = new Map(threads.map((th, i) => [th.id, letter(i, th.id)]));
  const of = (ids: string[]) => listed(ids.map((id) => name.get(id) ?? id));
  return `Tests: ${t.functions}${t.covers.length ? ` cover thread${t.covers.length === 1 ? "" : "s"} ${of(t.covers)}` : ""}`
    + (t.untested.length ? ` · nothing tests ${of(t.untested)}` : "");
}
