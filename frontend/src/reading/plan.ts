/** The reading plan (spec 2026-10-07-review-reading-phase2 §6): what each reader has ticked read, and how far along
 * they are. Ticks are the reader's own. */
import type { Reading } from "./types";

/** The signed-in reader's ticks on one review: story ids and To check keys. */
export interface ReadTicks { stories: string[]; checks: string[] }

/** The next story after `from` in reading order that the reader has not read, wrapping; null when every one is read. */
export function nextUnread(order: string[], read: ReadonlySet<string>, from: string): string | null {
  const at = order.indexOf(from);
  for (let i = 1; i <= order.length; i++) {
    const s = order[(at + i) % order.length];
    if (!read.has(s)) return s;
  }
  return null;
}

export interface Progress { stories: number; storyCount: number; checks: number; checkCount: number; all: boolean }

/** How many of the reading's stories and To check rows the reader has ticked; ticks it no longer holds don't count. */
export function progress(r: Reading, t: ReadTicks): Progress {
  const stories = new Set(t.stories), checks = new Set(t.checks);
  const read = r.order.filter((s) => stories.has(s)).length;
  return { stories: read, storyCount: r.order.length, checks: r.checks.filter((k) => checks.has(k.key)).length,
           checkCount: r.checks.length, all: r.order.length > 0 && read === r.order.length };
}

/** "7 of 12 stories read · 18 of 30 checks" (the checks part only when there are checks). */
export function progressText(p: Progress): string {
  return `${p.stories} of ${p.storyCount} stories read${p.checkCount ? ` · ${p.checks} of ${p.checkCount} checks` : ""}`;
}

/** The overview's opening line: the reader's progress, or "You've read every story" — with the checks still counted,
 * since on a phone the header's count is hidden. */
export function overviewProgress(p: Progress): string {
  return p.all ? `You've read every story${p.checkCount ? ` · ${p.checks} of ${p.checkCount} checks` : ""}` : progressText(p);
}

/** A thread's "2 of 3": how many of its stories the reader has read. */
export function threadRead(stories: string[], read: ReadonlySet<string>): string {
  return `${stories.filter((s) => read.has(s)).length} of ${stories.length}`;
}
