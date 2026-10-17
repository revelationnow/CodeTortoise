/** A story page's tiles (spec 2026-10-07-review-reading §6): its place in its thread, Where, call paths and code order. */
import { letter } from "./checks";
import type { StoryKind } from "../board/types";
import type { CallPath, ContractRow, Gap, Reading, Rewrite, WhereFile, WhereFn } from "./types";

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
export function whereTree<W extends WhereFile>(where: W[]): { dir: string; files: { name: string; file: W; showCl: boolean }[] }[] {
  const dirs = new Map<string, { name: string; file: W; showCl: boolean }[]>();
  for (const w of where) {
    const cut = w.path.lastIndexOf("/"), dir = cut < 0 ? "." : w.path.slice(0, cut);
    const showCl = new Set(w.functions.map((f) => f.cl)).size > 1;
    dirs.set(dir, [...(dirs.get(dir) ?? []), { name: w.path.slice(cut + 1), file: w, showCl }]);
  }
  return [...dirs.entries()].map(([dir, files]) => ({ dir, files }));
}

/** Where's files under the first of the story's CLs that edits them, in reading order (phase 2 §5.3); `also` names
 * its other CLs. Files no CL is known for come last, under `null`. */
export function whereByCl(where: WhereFile[], order: number[]): { cl: number | null; files: (WhereFile & { also: number[] })[] }[] {
  const groups = new Map<number | null, (WhereFile & { also: number[] })[]>([...order.map((c) => [c, []] as [number, []]), [null, []]]);
  for (const w of where) {
    const [first = null, ...also] = w.cls ?? [];
    if (!groups.has(first)) groups.set(first, []);
    groups.get(first)!.push({ ...w, also });
  }
  const out = [...groups.entries()].filter(([, files]) => files.length).map(([cl, files]) => ({ cl, files }));
  return [...out.filter((g) => g.cl !== null), ...out.filter((g) => g.cl === null)];
}

/** "Read CL 101, then CL 103" for a story with several CLs; null otherwise. */
export function readOrder(order: number[] | undefined): string | null {
  return order && order.length > 1 ? `Read ${order.map((c) => `CL ${c}`).join(", then ")}` : null;
}

/** A rewrite's sentence, ending in the function (or else the file) it happened in. */
export function rewriteText(r: Rewrite): { lead: string; name: string } {
  return { lead: `CL ${r.by} rewrites ${r.lines} line${r.lines === 1 ? "" : "s"} CL ${r.of} added in`,
           name: r.function ?? r.file.slice(r.file.lastIndexOf("/") + 1) };
}

/** What came between two CLs editing a file (phase 2 §5.4): a CL outside the review, or the same base under both. */
export function gapText(g: Gap): string {
  const name = g.file.slice(g.file.lastIndexOf("/") + 1);
  return g.same_base ? `${name}: CL ${g.after_cl} and CL ${g.before_cl} were each made against the same base, not one on top of the other`
    : `${name}: a CL outside this review changed it between CL ${g.after_cl} and CL ${g.before_cl}`;
}

/** A CL's rewrites in both directions (phase 2 §5.4): those it made, and those later CLs made of its lines. */
export function clRewrites(all: Rewrite[] | undefined, cl: number): { rewrites: Rewrite[]; rewrittenBy: Rewrite[] } {
  return { rewrites: (all ?? []).filter((r) => r.by === cl), rewrittenBy: (all ?? []).filter((r) => r.of === cl) };
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

/** A flow's one line, its path's names: "main → logger_flush → uart_send" (spec 2026-10-16-outline-and-causes §1.2). */
export function flowLabel(f: { path: string[] }, label: (id: string) => string | undefined): string {
  return f.path.map((n) => label(n) ?? "a function").join(" → ");
}

/** A story page's tabs (spec 2026-10-16-outline-and-causes §2.2). */
export type TabSec = "flows" | "changes" | "contracts" | "where" | "paths" | "code" | "graph" | "talk";
export interface TabSpec { sec: TabSec; label: string; count: number | null }

/** The tabs a story shows, first the one it opens on: Changes for a repeated edit, tests or unsorted pieces; Flows for a
 * behaviour story (always) or another story with flows. Empty sections are left out; Talk always has its composer. */
export function storyTabs(kind: StoryKind, n: { flows: number; contracts: number; where: number; paths: number; code: number; talk: number },
                          graph: boolean): TabSpec[] {
  const first: TabSpec[] = kind === "mechanical" || kind === "tests" || kind === "unsorted" ? [{ sec: "changes", label: "Changes", count: null }]
    : kind === "behaviour" || n.flows ? [{ sec: "flows", label: "Flows", count: n.flows }] : [];
  const rest: TabSpec[] = [{ sec: "contracts", label: "Before → after", count: n.contracts }, { sec: "where", label: "Where", count: n.where },
                           { sec: "paths", label: "Call paths", count: n.paths }, { sec: "code", label: "Code", count: n.code }];
  return [...first, ...rest.filter((t) => t.count), ...(graph ? [{ sec: "graph" as const, label: "Graph", count: null }] : []),
          { sec: "talk", label: "Talk", count: n.talk }];
}

/** The header's "after:" and "feeds:": the stories before and after `sid` in its thread. */
export function storyNeighbours(r: Pick<Reading, "threads">, sid: string): { after: string | null; feeds: string | null } {
  const t = r.threads.find((x) => x.stories.includes(sid));
  if (!t) return { after: null, feeds: null };
  const i = t.stories.indexOf(sid);
  return { after: t.stories[i - 1] ?? null, feeds: t.stories[i + 1] ?? null };
}
