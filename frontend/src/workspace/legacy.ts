/** Addresses from before the workspace (spec 2026-10-04-review-workspace §2.3) and where they go now. */
import { at, href, type Place, readAddress } from "./address";

interface Ctx {
  base: string;
  nodeStory: Record<string, string>;
  /** The review is shown as one board (not split into parts). */
  oneBoard: boolean;
}

const TABS: Record<string, string> = { "/overview": "#map", "/findings": "#findings", "/cls": "#changeset", "/files": "#files" };

/** The new address of an old one; `locate` when only the server knows which part holds the node; null when current. */
export function legacy(path: string, q: URLSearchParams, c: Ctx): { to: string } | { locate: string } | null {
  const node = q.get("node");
  if (node) {
    const sid = c.nodeStory[node];
    if (sid) return { to: href(c.base, at({ kind: "story", sid, view: "steps" }, { open: { node } })) };
    const cluster = /^\/c\/([^/]+)$/.exec(path);
    if (cluster) return { to: href(c.base, at({ kind: "cluster", cid: cluster[1] }, { open: { node } })) };
    return c.oneBoard ? { to: href(c.base, at({ kind: "whole", view: "graph" }, { open: { node } })) } : { locate: node };
  }
  if (path === "/board") return { to: c.oneBoard ? href(c.base, at({ kind: "whole", view: "graph" })) : `${c.base}#map` };
  if (TABS[path]) return { to: `${c.base}${TABS[path]}` };
  if (q.get("tab") === "graph" && path.startsWith("/s/")) {
    const a = readAddress(path, q);
    return a.place.kind === "story" ? { to: href(c.base, { ...a, place: { ...a.place, view: "graph" } }) } : null;
  }
  const file = q.get("file");
  if (file || q.has("x")) {                                // `x`, the old board's expand state, is dropped: unread
    const a = readAddress(path, q);
    return { to: href(c.base, file ? { ...a, open: { file, line: null } } : a) };
  }
  return null;
}

const ANCHORS: Record<string, Place> = {
  map: { kind: "index", tab: "map" }, findings: { kind: "index", tab: "checks" }, changeset: { kind: "index", tab: "cls" },
  files: { kind: "index", tab: "files" },
};

/** Where an old section anchor (#map, #findings…) leads once the review has a reading: the Index's tab (spec
 * 2026-10-07-review-reading §11); null for anchors the rail still has. */
export function indexFor(hash: string): Place | null {
  return ANCHORS[hash] ?? null;
}
