/** Sizes the reader drags (owner feedback 2026-10-08, sub-project C): the review header.
 * Each is kept per browser; storage that is missing, throws or holds the wrong shape gives the default. */
import { keys, load } from "../board/prefs";

/** The header is at least one line and at most half the window; null is its natural height. */
export const HEAD_MIN = 40;
export const headMax = (viewport: number): number => Math.max(HEAD_MIN, Math.round(viewport * 0.5));
export function loadHeadH(): number | null {
  const v = load<unknown>(keys.headH, null);
  return typeof v === "number" && Number.isFinite(v) && v >= HEAD_MIN && v <= 8000 ? v : null;
}
