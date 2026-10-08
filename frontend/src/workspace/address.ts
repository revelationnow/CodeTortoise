/** Workspace addresses (spec 2026-10-04-review-workspace §2.3): every place has one, so reload, shared links and Back
 * work. Ids appear here and nowhere in visible text. */

export type Place =
  | { kind: "whole"; view?: "graph" }
  | { kind: "story"; sid: string; view: "steps" | "graph" }
  | { kind: "finding"; fid: string }
  | { kind: "cl"; cl: number }
  | { kind: "cluster"; cid: string }
  | { kind: "index"; tab: IndexTab }
  | { kind: "unknown"; path: string };

/** The Index's tabs (spec 2026-10-07-review-reading §11): what the rail no longer lists. */
export const INDEX_TABS = ["cls", "files", "checks", "map"] as const;
export type IndexTab = typeof INDEX_TABS[number];

/** What the detail panel shows: a node's code, or a file's diff (at a line). */
/** `all`: the file in all CLs, whatever CL the page is about (phase 2 §5.4: a rewrite's line is a final-text line). */
export type Open = { node: string } | { file: string; line: number | null; all?: true } | null;
export type Tab = "diff" | "neighbours";

export interface Address {
  place: Place;
  /** The selected flow, 1-based (null: the first). */
  flow: number | null;
  open: Open;
  tab: Tab;
  /** A story lit on a map (the whole graph or a part's), from its "Show on the map". */
  story?: string | null;
  /** The finding whose To check row is lit: where an old finding address leads. */
  check?: string | null;
  /** A finding's own page, from its row's Details, rather than its story. */
  details?: boolean;
}

function readPlace(path: string, q: URLSearchParams): Place {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length) return q.get("view") === "graph" ? { kind: "whole", view: "graph" } : { kind: "whole" };
  const [kind, id, ...rest] = parts;
  if (!id || rest.length) return { kind: "unknown", path };
  if (kind === "s") return { kind: "story", sid: id, view: q.get("view") === "graph" ? "graph" : "steps" };
  if (kind === "f") return { kind: "finding", fid: id };
  if (kind === "cl" && /^\d+$/.test(id)) return { kind: "cl", cl: Number(id) };
  if (kind === "c") return { kind: "cluster", cid: id };
  if (kind === "i" && (INDEX_TABS as readonly string[]).includes(id)) return { kind: "index", tab: id as IndexTab };
  return { kind: "unknown", path };
}

function readOpen(raw: string | null): Open {
  if (!raw) return null;
  if (!raw.startsWith("file:")) return { node: raw };
  const m = /^(.+?)(?::(\d+))?$/.exec(raw.slice(5));
  return m ? { file: m[1], line: m[2] && Number(m[2]) > 0 ? Number(m[2]) : null } : null;
}

function withAll(open: Open, all: boolean): Open {
  return all && open && "file" in open ? { ...open, all: true } : open;
}

/** The address of `path` (what follows `/r/:id`) and its query. */
export function readAddress(path: string, q: URLSearchParams): Address {
  const flow = Number(q.get("flow"));
  return {
    place: readPlace(path, q),
    flow: Number.isInteger(flow) && flow > 0 ? flow : null,
    open: withAll(readOpen(q.get("open")), q.get("cl") === "all"),
    tab: q.get("tab") === "neighbours" ? "neighbours" : "diff",
    ...(q.get("story") ? { story: q.get("story") } : {}),
    ...(q.get("check") ? { check: q.get("check") } : {}),
    ...(q.get("details") === "1" ? { details: true } : {}),
  };
}

function placePath(p: Place): string {
  switch (p.kind) {
    case "whole": return "";
    case "story": return `/s/${p.sid}`;
    case "finding": return `/f/${p.fid}`;
    case "cl": return `/cl/${p.cl}`;
    case "cluster": return `/c/${p.cid}`;
    case "index": return `/i/${p.tab}`;
    case "unknown": return p.path;
  }
}

/** The link to `a` under `base` ("/r/7"), defaults left out. */
export function href(base: string, a: Address): string {
  const q = new URLSearchParams();
  if ((a.place.kind === "story" || a.place.kind === "whole") && a.place.view === "graph") q.set("view", "graph");
  if (a.story && (a.place.kind === "whole" || a.place.kind === "cluster")) q.set("story", a.story);
  if (a.flow) q.set("flow", String(a.flow));
  if (a.open) q.set("open", "node" in a.open ? a.open.node : `file:${a.open.file}${a.open.line ? `:${a.open.line}` : ""}`);
  if (a.open && "file" in a.open && a.open.all) q.set("cl", "all");
  if (a.tab !== "diff") q.set("tab", a.tab);
  if (a.check) q.set("check", a.check);
  if (a.details && a.place.kind === "finding") q.set("details", "1");
  return `${base}${placePath(a.place)}${q.size ? `?${q}` : ""}`;
}

/** One key per item, whatever its view: "s:S1", "f:F2", "whole". */
export function placeKey(p: Place): string {
  switch (p.kind) {
    case "whole": return "whole";
    case "story": return `s:${p.sid}`;
    case "finding": return `f:${p.fid}`;
    case "cl": return `cl:${p.cl}`;
    case "cluster": return `c:${p.cid}`;
    case "index": return `i:${p.tab}`;
    case "unknown": return `?:${p.path}`;
  }
}

export const samePlace = (a: Place, b: Place) => placeKey(a) === placeKey(b);

export const at = (place: Place, rest: Partial<Omit<Address, "place">> = {}): Address =>
  ({ place, flow: null, open: null, tab: "diff", ...rest });
