import type { Comment } from "../api";

/** Line comment anchor (spec §4.5): depot path, side of the diff, line number on that side. */
export const lineAnchor = (path: string, side: "new" | "old", line: number, cl?: number | null) =>
  cl == null ? { path, side, line } : { path, cl, side, line };

/** Does a root comment sit on this line? Reads both the current shape and M1's {depot, cl, side, line}
 * (M1 comments made on the cumulative diff have cl null). */
export function onLine(c: Comment, path: string, side: "new" | "old", line: number, cl: number | null = null): boolean {
  if (c.anchor_kind !== "line" || c.anchor.side !== side || c.anchor.line !== line) return false;
  const p = (c.anchor.path ?? c.anchor.depot) as string | undefined;
  return p === path && ((c.anchor.cl as number | null | undefined) ?? null) === cl;
}
