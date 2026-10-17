/** Checks by cause (spec 2026-10-16-outline-and-causes §4): which places are open, which kinds are hidden, the order
 * of Next open check and the stepper's moves. Pure, so the rules are tested apart from React. */
import { keys, load, save } from "../board/prefs";
import { CHECK_ORDER, KIND_LABEL, letter } from "./checks";
import type { Cause, Check, CheckKind, Mark, Reading } from "./types";

export type OutlineView = "stories" | "checks";

export const loadOutline = (): OutlineView => (load<unknown>(keys.outline, "stories") === "checks" ? "checks" : "stories");
export const saveOutline = (v: OutlineView) => save(keys.outline, v);

export const HIDDEN_DEFAULT: CheckKind[] = ["confirm"];

/** The kinds the reader hides; a stored value of the wrong shape keeps only real kinds, unreadable storage the default. */
export function loadHidden(): Set<CheckKind> {
  const v = load<unknown>(keys.hiddenKinds, HIDDEN_DEFAULT);
  return new Set(Array.isArray(v) ? v.filter((k): k is CheckKind => (CHECK_ORDER as unknown[]).includes(k)) : HIDDEN_DEFAULT);
}
export const saveHidden = (h: ReadonlySet<CheckKind>) => save(keys.hiddenKinds, CHECK_ORDER.filter((k) => h.has(k)));

/** Open unless someone marked it and its line has not changed since. */
export const placeOpen = (key: string, marks: Record<string, Mark>) => !marks[key] || marks[key].changed;
export const openPlaces = (c: Cause, marks: Record<string, Mark>) => c.places.filter((k) => placeOpen(k, marks));
export const causeOpen = (c: Cause, marks: Record<string, Mark>) => c.places.some((k) => placeOpen(k, marks));
export const doneCount = (c: Cause, marks: Record<string, Mark>) => c.places.length - openPlaces(c, marks).length;

export const shown = (causes: Cause[], hidden: ReadonlySet<CheckKind>) => causes.filter((c) => !hidden.has(c.kind));
export const openCount = (causes: Cause[], hidden: ReadonlySet<CheckKind>, marks: Record<string, Mark>) =>
  shown(causes, hidden).filter((c) => causeOpen(c, marks)).length;

/** Where the stepper opens a cause: its first open place (1-based), else its first. */
export function firstOpenAt(c: Cause, marks: Record<string, Mark>): number {
  const i = c.places.findIndex((k) => placeOpen(k, marks));
  return i < 0 ? 1 : i + 1;
}

/** Skip ›, ‹ Back and Looks fine & next: the next open place other than `at` going `by`, wrapping; null when none. */
export function nextOpenAt(c: Cause, marks: Record<string, Mark>, at: number, by: 1 | -1): number | null {
  const n = c.places.length;
  for (let i = 1; i < n; i++) {
    const j = (((at - 1 + by * i) % n) + n) % n;
    if (placeOpen(c.places[j], marks)) return j + 1;
  }
  return null;
}

/** Next open check › (§4.5): the first open, shown cause after the one in the panel, else from the current story's
 * place in reading order (its own causes first), else from the start; wrapping. */
export function nextOpen(causes: Cause[], hidden: ReadonlySet<CheckKind>, marks: Record<string, Mark>,
                         from: { cause?: string | null; story?: string | null; order: string[] }): { cause: string; at: number } | null {
  const n = causes.length;
  let start = 0;
  const here = from.cause ? causes.findIndex((c) => c.id === from.cause) : -1;
  if (here >= 0) start = here + 1;
  else if (from.story && from.order.includes(from.story)) {
    const pos = (s: string | null) => (s && from.order.includes(s) ? from.order.indexOf(s) : from.order.length);
    const i = causes.findIndex((c) => pos(c.story) >= pos(from.story!));
    start = i < 0 ? 0 : i;
  }
  for (let i = 0; i < n; i++) {
    const c = causes[(start + i) % n];
    if (!hidden.has(c.kind) && causeOpen(c, marks)) return { cause: c.id, at: firstOpenAt(c, marks) };
  }
  return null;
}

/** The cause holding check `key` (an old `?check=` address holds a check key or a finding id) and the place's number. */
export function causeOfCheck(causes: Cause[], key: string): { cause: Cause; at: number } | null {
  for (const c of causes) {
    const i = c.places.indexOf(key);
    if (i >= 0) return { cause: c, at: i + 1 };
  }
  const c = causes.find((x) => x.finding === key);
  return c ? { cause: c, at: 1 } : null;
}

/** The stepper's `also:` (§4.3): other causes with a check at the same file and line as place `key` of `cause`. */
export function alsoAt(causes: Cause[], checks: Map<string, Check>, cause: Cause, key: string): { cause: Cause; at: number }[] {
  const me = checks.get(key);
  if (!me || !me.path || me.line === null) return [];
  return causes.filter((c) => c.id !== cause.id).flatMap((c) => {
    const i = c.places.findIndex((k) => { const o = checks.get(k); return !!o && o.path === me.path && o.line === me.line; });
    return i < 0 ? [] : [{ cause: c, at: i + 1 }];
  });
}

/** The hidden-kinds control's summary (§4.6). */
export function hiddenLabel(hidden: ReadonlySet<CheckKind>, causes: Cause[]): string {
  const kinds = CHECK_ORDER.filter((k) => hidden.has(k));
  if (!kinds.length) return "Showing all";
  const n = causes.filter((c) => hidden.has(c.kind)).length;
  return `Showing: all but ${kinds.map((k) => KIND_LABEL[k]).join(", ")} · ${n} hidden`;
}

/** The top bar's one progress line (§1.1); `total`: the shown causes. */
export function progressLine(read: number, stories: number, open: number, total: number): string {
  const head = `${read} of ${stories} stories read`;
  if (!total) return head;
  return `${head} · ${open ? `${open} cause${open === 1 ? "" : "s"} open` : "every check done"}`;
}

export interface CauseGroup { thread: string | null; label: string; stories: { story: string | null; causes: Cause[] }[] }

/** The outline's Checks view (§4.4): a group per thread, then per story in reading order, then the thread's causes of no
 * story; causes of no known thread under "Across the change". Causes keep their reading order. */
export function causeGroups(r: Pick<Reading, "threads">, list: Cause[]): CauseGroup[] {
  const known = new Set(r.threads.map((t) => t.id));
  const groups = [...r.threads.map((t, i) => ({ thread: t.id as string | null, label: `${letter(i, t.id)} · ${t.name}`, order: t.stories })),
                  { thread: null, label: "Across the change", order: [] as string[] }];
  return groups.map((g) => {
    const mine = list.filter((c) => (g.thread ? c.thread === g.thread : !c.thread || !known.has(c.thread)));
    const stories = [...g.order, null].map((s) => ({
      story: s, causes: mine.filter((c) => (s === null ? !c.story || !g.order.includes(c.story) : c.story === s)) }));
    return { thread: g.thread, label: g.label, stories: stories.filter((x) => x.causes.length) };
  }).filter((g) => g.stories.length);
}

/** The place's code in the stepper (§4.3): its line (1-based) with `n` lines each side, as far as the file goes. */
export function around(text: string, line: number, n = 3): { line: number; text: string; at: boolean }[] {
  const lines = text.split("\n");
  if (line < 1 || line > lines.length) return [];
  const out = [];
  for (let i = Math.max(1, line - n); i <= Math.min(lines.length, line + n); i++) out.push({ line: i, text: lines[i - 1], at: i === line });
  return out;
}
