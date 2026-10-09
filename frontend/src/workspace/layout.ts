/** Sizes the reader drags (owner feedback 2026-10-08, sub-project C): the story's To check column and the review header.
 * Each is kept per browser; storage that is missing, throws or holds the wrong shape gives the default. */
import { keys, load } from "../board/prefs";

export const CHECK_W = { min: 260, def: 340 };
/** The To check column takes at most 60% of the story page. */
export const checkMax = (page: number): number => Math.max(CHECK_W.min, Math.round(page * 0.6));
export function loadCheckW(): number {
  const v = load<unknown>(keys.checkW, CHECK_W.def);
  return typeof v === "number" && Number.isFinite(v) && v >= CHECK_W.min && v <= 8000 ? v : CHECK_W.def;
}

/** The header is at least one line and at most half the window; null is its natural height. */
export const HEAD_MIN = 40;
export const headMax = (viewport: number): number => Math.max(HEAD_MIN, Math.round(viewport * 0.5));
export function loadHeadH(): number | null {
  const v = load<unknown>(keys.headH, null);
  return typeof v === "number" && Number.isFinite(v) && v >= HEAD_MIN && v <= 8000 ? v : null;
}
