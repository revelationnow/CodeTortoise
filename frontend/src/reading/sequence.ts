/** CLs as a sequence (spec 2026-10-07-review-reading-phase2 §5): which CL wrote each row of a diff, from the server's
 * walk of a file several CLs edit (backend/codetortoise/sequence.py). */
import { type Line, lineKey } from "../board/codeRows";
import type { FileLines } from "./types";

/** A row's CL: `chip` on the first row of a run (its label; `short` on a phone), `grey` for a line a later CL replaced;
 * clicking the chip shows CL `cl` alone. */
export interface Tag { cl: number; label: string; short: string; chip: boolean; grey: boolean }

/** The combined diff (base → final): a chip on the first row of each run of changed rows one CL wrote — "CL 103 ·
 * rewrites CL 101" when its lines replaced an earlier CL's. Rows no CL of the review wrote get none. */
export function chipsAll(rows: Line[], fl: FileLines): Map<string, Tag> {
  const out = new Map<string, Tag>();
  let prev: string | null = null;
  for (const l of rows) {
    const cl = l.t === "+" ? fl.wrote[l.n! - 1] : l.t === "-" ? fl.removed[l.o! - 1] : null;
    if (cl == null) { prev = null; continue; }
    const over = l.t === "+" ? fl.over[l.n! - 1] ?? null : null;
    const run = `${cl}|${over}`;                     // a − run and the + run replacing it, one CL: one chip
    if (run !== prev) {
      out.set(l.t === "+" ? lineKey("new", l.n!) : lineKey("old", l.o!), {
        cl, label: over ? `CL ${cl} · rewrites CL ${over}` : `CL ${cl}`, short: String(cl), chip: true, grey: false });
    }
    prev = run;
  }
  return out;
}

/** One CL's diff: its added lines a later CL replaced are greyed, the first of each run chipped "rewritten in CL 105". */
export function chipsOne(rows: Line[], fl: FileLines, cl: number): Map<string, Tag> {
  const out = new Map<string, Tag>();
  const later = fl.rewritten[String(cl)] ?? {};
  let prev: number | null = null;
  for (const l of rows) {
    const by = l.t === "+" ? later[String(l.n)] ?? null : null;
    if (by !== null) {
      out.set(lineKey("new", l.n!), { cl: by, label: `rewritten in CL ${by}`, short: `→${by}`, chip: by !== prev, grey: true });
    }
    prev = l.t === "=" ? null : by;
  }
  return out;
}
