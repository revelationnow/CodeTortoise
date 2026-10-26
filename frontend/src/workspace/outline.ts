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

/** What the pinned bars take of the scroll box while the thread at `open` is open (of n bars): the stacked height of those
 * pinned at the top and of those pinned at the bottom, read off `barPin`. The open thread's rows keep that much clear of the
 * box's edges when focus scrolls them into view, so none comes to rest under a bar (WCAG 2.2, 2.4.11). */
export function pinnedSpace(open: number, n: number): { top: number; bottom: number } {
  let top = 0, bottom = 0;
  for (let i = 0; i < n; i++) {
    const pin = barPin(i, open, n);
    if (pin && "top" in pin) top = Math.max(top, pin.top + BAR);
    else if (pin) bottom = Math.max(bottom, pin.bottom + BAR);
  }
  return { top, bottom };
}
