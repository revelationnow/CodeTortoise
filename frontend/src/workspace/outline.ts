/** The outline's threads as an accordion (spec 2026-10-25-review-ui-redesign §6): which one is open, where the closed
 * bars pin, and the thread the viewer last opened in a review. Pure, so the rules are tested apart from React. */
import { load, save } from "../board/prefs";

/** A thread bar's fixed height in px: pinned bars stack by it. */
export const BAR = 36;

const key = (rid: number) => `ct.ws.${rid}.thread`;

/** The thread the viewer last opened in this review; a stored value of the wrong shape counts as none. */
export function loadThread(rid: number): string | null {
  const v = load<unknown>(key(rid), null);
  return typeof v === "string" ? v : null;
}

export const saveThread = (rid: number, id: string | null) => save(key(rid), id);

/** The open thread: the one holding the current story; anywhere else the one last opened, if the reading still has it. */
export function openThread(threads: { id: string; stories: string[] }[], story: string | null, last: string | null): string | null {
  const holding = story ? threads.find((t) => t.stories.includes(story)) : undefined;
  if (holding) return holding.id;
  return last && threads.some((t) => t.id === last) ? last : null;
}

/** Where the i-th of n bars pins while the thread at index `open` is open: up to it at the top, stacked; after it at the
 * bottom, stacked from the last; nothing pins while none is open (`open` -1). */
export function barPin(i: number, open: number, n: number): { top: number } | { bottom: number } | null {
  if (open < 0) return null;
  return i <= open ? { top: i * BAR } : { bottom: (n - 1 - i) * BAR };
}
