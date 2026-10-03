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
