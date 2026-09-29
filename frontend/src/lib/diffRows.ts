import { diffLines } from "diff";

export type RowKind = "ctx" | "add" | "del" | "gap";
export interface Row { kind: RowKind; oldNo: number | null; newNo: number | null; text: string }

function splitLines(value: string): string[] {
  const lines = value.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** Unified diff rows with line numbers; unchanged runs longer than 2*context collapse into a "gap" row. */
export function diffRows(before: string, after: string, context = 3): Row[] {
  const rows: Row[] = [];
  let o = 1;
  let n = 1;
  for (const part of diffLines(before, after)) {
    const lines = splitLines(part.value);
    if (part.added) {
      for (const t of lines) rows.push({ kind: "add", oldNo: null, newNo: n++, text: t });
    } else if (part.removed) {
      for (const t of lines) rows.push({ kind: "del", oldNo: o++, newNo: null, text: t });
    } else {
      lines.forEach((t) => rows.push({ kind: "ctx", oldNo: o++, newNo: n++, text: t }));
    }
  }
  const keep = new Array(rows.length).fill(false);
  rows.forEach((r, i) => {
    if (r.kind !== "ctx") for (let j = Math.max(0, i - context); j <= Math.min(rows.length - 1, i + context); j++) keep[j] = true;
  });
  const out: Row[] = [];
  let hidden = 0;
  rows.forEach((r, i) => {
    if (keep[i]) {
      if (hidden) out.push({ kind: "gap", oldNo: null, newNo: null, text: `${hidden} unchanged line(s)` });
      hidden = 0;
      out.push(r);
    } else hidden++;
  });
  if (hidden && out.length) out.push({ kind: "gap", oldNo: null, newNo: null, text: `${hidden} unchanged line(s)` });
  return out;
}
