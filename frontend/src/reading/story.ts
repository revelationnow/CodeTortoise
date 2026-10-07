/** A story page's tiles (spec 2026-10-07-review-reading §6): its place in its thread, Where, call paths and code order. */
import { letter } from "./checks";
import type { CallPath, ContractRow, Reading, WhereFile, WhereFn } from "./types";

/** ‹ › on a story page: the story `by` places away in reading order, wrapping; a story not in it stays put. */
export function stepIn(order: string[], sid: string, by: number): string {
  const at = order.indexOf(sid);
  return at < 0 ? sid : order[(at + by + order.length) % order.length];
}

/** "Thread A › name · story 1 of 3" for the header; null for a story in no thread (tests). */
export function threadCrumb(r: Reading, sid: string): { letter: string; name: string; id: string; text: string } | null {
  const i = r.threads.findIndex((t) => t.stories.includes(sid));
  if (i < 0) return null;
  const t = r.threads[i];
  return { letter: letter(i, t.id), name: t.name, id: t.id, text: `story ${t.stories.indexOf(sid) + 1} of ${t.stories.length}` };
}

/** "CL 11 · 14 functions": each CL's changed functions in the story, by CL. */
export function clCounts(where: WhereFile[]): { cl: number; functions: number }[] {
  const n = new Map<number, number>();
  for (const f of where.flatMap((w) => w.functions)) if (f.cl !== null) n.set(f.cl, (n.get(f.cl) ?? 0) + 1);
  return [...n.entries()].sort((a, b) => a[0] - b[0]).map(([cl, functions]) => ({ cl, functions }));
}

/** Folder › file › functions, folders in Where's order; a function's CL shows only where its file was edited in
 * several CLs. */
export function whereTree(where: WhereFile[]): { dir: string; files: { name: string; file: WhereFile; showCl: boolean }[] }[] {
  const dirs = new Map<string, { name: string; file: WhereFile; showCl: boolean }[]>();
  for (const w of where) {
    const cut = w.path.lastIndexOf("/"), dir = cut < 0 ? "." : w.path.slice(0, cut);
    const showCl = new Set(w.functions.map((f) => f.cl)).size > 1;
    dirs.set(dir, [...(dirs.get(dir) ?? []), { name: w.path.slice(cut + 1), file: w, showCl }]);
  }
  return [...dirs.entries()].map(([dir, files]) => ({ dir, files }));
}

/** The paths under the function they start from, in rank order; `entry` when that is an entry point. */
export function byEntry(paths: CallPath[]): { label: string; entry: boolean; paths: CallPath[] }[] {
  const groups = new Map<string, { label: string; entry: boolean; paths: CallPath[] }>();
  for (const p of paths) {
    const key = p.steps[0] ?? "";
    if (!groups.has(key)) groups.set(key, { label: p.labels[0] ?? "", entry: !!p.entry, paths: [] });
    groups.get(key)!.paths.push(p);
  }
  return [...groups.values()];
}

/** A path's steps, the folded middle of a long one as a single "N more" step until it is opened. */
export function foldPath(p: CallPath, open: boolean): ({ label: string } | { more: number })[] {
  const steps = p.labels.map((label) => ({ label }));
  if (open || !p.hidden.length) return steps;
  const from = p.steps.indexOf(p.hidden[0]);
  return [...steps.slice(0, from), { more: p.hidden.length }, ...steps.slice(from + p.hidden.length)];
}

/** The story's changed functions for its Code section: those whose contract changed first (definitions before their
 * users), then the rest in Where's order. */
export function codeOrder(where: WhereFile[], rows: ContractRow[]): WhereFn[] {
  const fns = where.flatMap((w) => w.functions);
  const first = new Set(rows.filter((r) => r.kind !== "body").flatMap((r) => r.nodes));
  return [...fns.filter((f) => first.has(f.node)), ...fns.filter((f) => !first.has(f.node))];
}
