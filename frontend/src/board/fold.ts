/** The changes view of a diff: changed lines with a little context, the rest folded into gaps that open on request. */
import type { Line } from "./codeRows";

export const CONTEXT = 3;      // unchanged lines shown around each change
export const STEP = 15;        // lines a gap opens by per click
const MIN_GAP = 4;             // shorter runs aren't worth folding

export type Run = { kind: "show" | "gap"; start: number; end: number };   // indices into the lines, end exclusive
export type Range = [number, number];

/** Runs of shown and folded lines: changes and `keep` (indices of lines with notes or comments) ± CONTEXT, and every
 * `shown` range, are shown. */
export function foldRuns(lines: Line[], shown: Range[], keep: Set<number> = new Set()): Run[] {
  const n = lines.length;
  const vis = new Array<boolean>(n).fill(false);
  lines.forEach((l, i) => {
    if (l.t !== "=" || keep.has(i))
      for (let j = Math.max(0, i - CONTEXT); j <= Math.min(n - 1, i + CONTEXT); j++) vis[j] = true;
  });
  for (const [a, b] of shown) for (let j = Math.max(0, a); j < Math.min(n, b); j++) vis[j] = true;
  const runs: Run[] = [];
  let i = 0;
  while (i < n) {
    let j = i;
    while (j < n && vis[j] === vis[i]) j++;
    const kind = vis[i] || (j - i < MIN_GAP && (keep.size > 0 || lines.some((l) => l.t !== "="))) ? "show" : "gap";
    const last = runs[runs.length - 1];
    if (last && last.kind === kind) last.end = j;
    else runs.push({ kind, start: i, end: j });
    i = j;
  }
  return runs;
}

/** The lines a gap's control opens: "up" the STEP lines just above what follows it, "down" the STEP lines just
 * below what precedes it, "all" the whole gap. */
export function expandRange(gap: Run, how: "up" | "down" | "all"): Range {
  if (how === "all") return [gap.start, gap.end];
  return how === "up" ? [Math.max(gap.start, gap.end - STEP), gap.end] : [gap.start, Math.min(gap.end, gap.start + STEP)];
}

/** The range that shows new-side line `n` with STEP lines around it, or null if the file has no such line. */
export function revealRange(lines: Line[], n: number): Range | null {
  const i = lines.findIndex((l) => l.n === n);
  return i < 0 ? null : [i - STEP, i + STEP + 1];
}

/** A function's code in the detail panel: new-side lines `lo`–`hi` grown by `more` lines past each end. A changed
 * function folds like the changes view, keeping its first line; lines brought in from past its ends are always shown.
 * `above` and `below` count the file's lines still outside. */
export function functionView(lines: Line[], lo: number, hi: number, more: { above: number; below: number }, shown: Range[],
                             change: boolean): { lines: Line[]; runs: Run[] | null; above: number; below: number } {
  let cur = 0;
  const at = lines.map((l) => (l.n !== null ? (cur = l.n) : cur + 1));
  const from = lo - more.above, to = hi + more.below;
  const start = at.findIndex((a) => a >= from), stop = start < 0 ? -1 : lastIndex(at, (a) => a <= to);
  if (start < 0 || stop < start) return { lines: [], runs: change ? [] : null, above: lines.length, below: 0 };
  const slice = lines.slice(start, stop + 1);
  const head = at.slice(start, stop + 1).findIndex((a) => a >= lo);
  const tail = lastIndex(at.slice(start, stop + 1), (a) => a <= hi);
  const outside: Range[] = [[0, Math.max(0, head)], [tail + 1, slice.length]];
  return { lines: slice, runs: change ? foldRuns(slice, [...outside, ...shown], new Set(head >= 0 ? [head] : [])) : null,
           above: start, below: lines.length - stop - 1 };
}

function lastIndex<T>(xs: T[], ok: (x: T) => boolean): number {
  for (let i = xs.length - 1; i >= 0; i--) if (ok(xs[i])) return i;
  return -1;
}
