/** Workspace addresses (spec 2026-10-04-review-workspace §2.3): every place has one, so reload, shared links and Back
 * work. Ids appear here and nowhere in visible text. */

export type Place =
  | { kind: "whole" }
  | { kind: "story"; sid: string; view: "steps" | "graph" }
  | { kind: "finding"; fid: string }
  | { kind: "cl"; cl: number }
  | { kind: "cluster"; cid: string }
  | { kind: "unknown"; path: string };

/** What the detail panel shows: a node's code, or a file's diff (at a line). */
export type Open = { node: string } | { file: string; line: number | null } | null;
export type Tab = "diff" | "neighbours";

export interface Address {
  place: Place;
  /** The selected flow, 1-based (null: the first). */
  flow: number | null;
  open: Open;
  tab: Tab;
}

function readPlace(path: string, q: URLSearchParams): Place {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length) return { kind: "whole" };
  const [kind, id, ...rest] = parts;
  if (!id || rest.length) return { kind: "unknown", path };
  if (kind === "s") return { kind: "story", sid: id, view: q.get("view") === "graph" ? "graph" : "steps" };
  if (kind === "f") return { kind: "finding", fid: id };
  if (kind === "cl" && /^\d+$/.test(id)) return { kind: "cl", cl: Number(id) };
  if (kind === "c") return { kind: "cluster", cid: id };
  return { kind: "unknown", path };
}

function readOpen(raw: string | null): Open {
  if (!raw) return null;
  if (!raw.startsWith("file:")) return { node: raw };
  const m = /^(.+?)(?::(\d+))?$/.exec(raw.slice(5));
  return m ? { file: m[1], line: m[2] ? Number(m[2]) : null } : null;
}

/** The address of `path` (what follows `/r/:id`) and its query. */
export function readAddress(path: string, q: URLSearchParams): Address {
  const flow = Number(q.get("flow"));
  return {
    place: readPlace(path, q),
    flow: Number.isInteger(flow) && flow > 0 ? flow : null,
    open: readOpen(q.get("open")),
    tab: q.get("tab") === "neighbours" ? "neighbours" : "diff",
  };
}

const placePath = (p: Place): string =>
  p.kind === "story" ? `/s/${p.sid}` : p.kind === "finding" ? `/f/${p.fid}` : p.kind === "cl" ? `/cl/${p.cl}`
    : p.kind === "cluster" ? `/c/${p.cid}` : p.kind === "unknown" ? p.path : "";

/** The link to `a` under `base` ("/r/7"), defaults left out. */
export function href(base: string, a: Address): string {
  const q = new URLSearchParams();
  if (a.place.kind === "story" && a.place.view === "graph") q.set("view", "graph");
  if (a.flow) q.set("flow", String(a.flow));
  if (a.open) q.set("open", "node" in a.open ? a.open.node : `file:${a.open.file}${a.open.line ? `:${a.open.line}` : ""}`);
  if (a.tab !== "diff") q.set("tab", a.tab);
  return `${base}${placePath(a.place)}${q.size ? `?${q}` : ""}`;
}

/** One key per item, whatever its view: "s:S1", "f:F2", "whole". */
export const placeKey = (p: Place): string =>
  p.kind === "story" ? `s:${p.sid}` : p.kind === "finding" ? `f:${p.fid}` : p.kind === "cl" ? `cl:${p.cl}`
    : p.kind === "cluster" ? `c:${p.cid}` : p.kind === "unknown" ? `?:${p.path}` : "whole";

export const samePlace = (a: Place, b: Place) => placeKey(a) === placeKey(b);

export const at = (place: Place, rest: Partial<Omit<Address, "place">> = {}): Address =>
  ({ place, flow: null, open: null, tab: "diff", ...rest });
