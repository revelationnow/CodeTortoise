/** What a code view renders, in order: lines (or side-by-side pairs), the annotations under each line, and the
 * comment thread slot after them. Pure, so placement is unit-tested; CodeView only draws it. */
import { diffLines } from "diff";
import type { Annotation } from "./types";

export interface Line { t: "=" | "+" | "-"; o: number | null; n: number | null; text: string }
export type Side = "new" | "old";
export type Item =
  | { kind: "line"; line: Line; hot: boolean; side: Side; no: number }
  | { kind: "pair"; l: Line | null; r: Line | null; hot: boolean; side: Side; no: number }
  | { kind: "ann"; ann: Annotation }
  | { kind: "thread"; side: Side; no: number };

const split = (v: string) => {
  const lines = v.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines;
};

export function lineDiff(before: string, after: string): Line[] {
  const out: Line[] = [];
  let o = 1, n = 1;
  for (const part of diffLines(before, after)) {
    for (const text of split(part.value)) {
      if (part.added) out.push({ t: "+", o: null, n: n++, text });
      else if (part.removed) out.push({ t: "-", o: o++, n: null, text });
      else out.push({ t: "=", o: o++, n: n++, text });
    }
  }
  return out;
}

export const plainLines = (text: string): Line[] => split(text).map((t, i) => ({ t: "=", o: i + 1, n: i + 1, text: t }));

/** Lines whose new-side position is within [lo, hi]; deleted lines count at the position they were removed from. */
export function sliceRange(lines: Line[], lo: number, hi: number): Line[] {
  let cur = 0;
  return lines.filter((l) => {
    if (l.n !== null) cur = l.n;
    const at = l.n ?? cur + 1;
    return at >= lo && at <= hi;
  });
}

const where = (l: Line): [Side, number] => (l.n !== null ? ["new", l.n] : ["old", l.o!]);
export const lineKey = (side: Side, no: number) => `${side}:${no}`;

export function codeItems(lines: Line[], mode: "unified" | "split", anns: Annotation[], threads: Set<string>): Item[] {
  const at = (side: Side, no: number) => anns.filter((a) => a.side === side && a.line === no);
  const out: Item[] = [];
  const tail = (side: Side, no: number) => {
    for (const ann of at(side, no)) out.push({ kind: "ann", ann });
    if (threads.has(lineKey(side, no))) out.push({ kind: "thread", side, no });
  };
  const isHot = (l: Line | null) => !!l && l.t === "=" && at(...where(l)).some((a) => a.severity === "warn");
  if (mode === "unified") {
    for (const line of lines) {
      const [side, no] = where(line);
      out.push({ kind: "line", line, hot: isHot(line), side, no });
      tail(side, no);
    }
    return out;
  }
  let k = 0;
  while (k < lines.length) {
    const pairs: [Line | null, Line | null][] = [];
    if (lines[k].t === "=") pairs.push([lines[k], lines[k++]]);
    else {
      const dels: Line[] = [], adds: Line[] = [];
      while (k < lines.length && lines[k].t === "-") dels.push(lines[k++]);
      while (k < lines.length && lines[k].t === "+") adds.push(lines[k++]);
      for (let q = 0; q < Math.max(dels.length, adds.length); q++) pairs.push([dels[q] ?? null, adds[q] ?? null]);
    }
    for (const [l, r] of pairs) {
      const [side, no] = where((r ?? l)!);
      out.push({ kind: "pair", l, r, hot: isHot(r), side, no });
      tail(side, no);
    }
  }
  return out;
}
