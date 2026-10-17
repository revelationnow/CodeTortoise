/** Workspace addresses (spec 2026-10-04-review-workspace §2.3): every place has one, so reload, shared links and Back
 * work. Ids appear here and nowhere in visible text. */
import type { Severity } from "../api";
import { FINDING_STATES, type FindingState, SEVERITIES } from "./findings";

export type Place =
  | { kind: "whole"; view?: "graph" }
  | { kind: "story"; sid: string; view: "steps" | "graph" }
  | { kind: "finding"; fid: string }
  | { kind: "cl"; cl: number }
  | { kind: "cluster"; cid: string }
  | { kind: "index"; tab: IndexTab }
  | { kind: "unknown"; path: string };

/** The Index's tabs (spec 2026-10-07-review-reading §11): what the rail no longer lists. */
export const INDEX_TABS = ["cls", "files", "checks", "findings", "map"] as const;
export type IndexTab = typeof INDEX_TABS[number];

/** What the detail panel shows: a node's code, a file's diff (at a line) or a finding (spec 2026-10-12 §2.1). */
/** `all`: the file in all CLs, whatever CL the page is about (phase 2 §5.4: a rewrite's line is a final-text line).
 * `cl`: the file in that CL, from a page about no CL (Index › CLs, spec 2026-10-12-story-account-and-panels §5). */
export type Open = { node: string } | { file: string; line: number | null; all?: true; cl?: number } | { finding: string } | { cause: string; at: number } | null;
/** One thing the panel can show. */
export type Item = Exclude<Open, null>;
/** A story page's tabs (spec 2026-10-16-outline-and-causes §2.2); the Graph tab is the story's `view: "graph"`. */
export const STORY_SECS = ["flows", "changes", "contracts", "where", "paths", "code", "talk"] as const;
export type StorySec = typeof STORY_SECS[number];

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
  /** Index › Findings' filters (spec 2026-10-12 §4); only on that tab. */
  sev?: Severity | null;
  status?: FindingState | null;
  /** A story's tab (absent: its first). */
  sec?: StorySec;
}

function readPlace(path: string, q: URLSearchParams): Place {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length) return q.get("view") === "graph" ? { kind: "whole", view: "graph" } : { kind: "whole" };
  const [kind, id, ...rest] = parts;
  if (!id || rest.length) return { kind: "unknown", path };
  if (kind === "s") return { kind: "story", sid: id, view: q.get("view") === "graph" || q.get("sec") === "graph" ? "graph" : "steps" };
  if (kind === "f") return { kind: "finding", fid: id };
  if (kind === "cl" && /^\d+$/.test(id)) return { kind: "cl", cl: Number(id) };
  if (kind === "c") return { kind: "cluster", cid: id };
  if (kind === "i" && (INDEX_TABS as readonly string[]).includes(id)) return { kind: "index", tab: id as IndexTab };
  return { kind: "unknown", path };
}

function readOpen(raw: string | null, at: string | null): Open {
  if (!raw) return null;
  if (raw.startsWith("cause:")) { const n = Number(at); return raw.length > 6 ? { cause: raw.slice(6), at: Number.isInteger(n) && n > 0 ? n : 1 } : null; }
  if (raw.startsWith("finding:")) return raw.length > 8 ? { finding: raw.slice(8) } : null;
  if (!raw.startsWith("file:")) return { node: raw };
  const m = /^(.+?)(?::(\d+))?$/.exec(raw.slice(5));
  return m ? { file: m[1], line: m[2] && Number(m[2]) > 0 ? Number(m[2]) : null } : null;
}

function withCl(open: Open, cl: string | null): Open {
  if (!open || !("file" in open)) return open;
  if (cl === "all") return { ...open, all: true };
  return cl && /^[1-9]\d*$/.test(cl) ? { ...open, cl: Number(cl) } : open;
}

/** The address of `path` (what follows `/r/:id`) and its query. */
export function readAddress(path: string, q: URLSearchParams): Address {
  const flow = Number(q.get("flow"));
  const place = readPlace(path, q), findings = place.kind === "index" && place.tab === "findings";
  return {
    place,
    flow: Number.isInteger(flow) && flow > 0 ? flow : null,
    open: withCl(readOpen(q.get("open"), q.get("at")), q.get("cl")),
    tab: q.get("tab") === "neighbours" ? "neighbours" : "diff",
    ...(place.kind === "story" && (STORY_SECS as readonly string[]).includes(q.get("sec") ?? "") ? { sec: q.get("sec") as StorySec } : {}),
    ...(q.get("story") ? { story: q.get("story") } : {}),
    ...(q.get("check") ? { check: q.get("check") } : {}),
    ...(q.get("details") === "1" ? { details: true } : {}),
    ...(findings && (SEVERITIES as string[]).includes(q.get("sev") ?? "") ? { sev: q.get("sev") as Severity } : {}),
    ...(findings && (FINDING_STATES as string[]).includes(q.get("status") ?? "") ? { status: q.get("status") as FindingState } : {}),
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
  if (a.open) q.set("open", "node" in a.open ? a.open.node : "finding" in a.open ? `finding:${a.open.finding}`
    : "cause" in a.open ? `cause:${a.open.cause}` : `file:${a.open.file}${a.open.line ? `:${a.open.line}` : ""}`);
  if (a.open && "cause" in a.open) q.set("at", String(a.open.at));
  if (a.open && "file" in a.open && (a.open.all || a.open.cl)) q.set("cl", a.open.all ? "all" : String(a.open.cl));
  if (a.tab !== "diff") q.set("tab", a.tab);
  if (a.sec && a.place.kind === "story" && a.place.view !== "graph") q.set("sec", a.sec);
  if (a.check) q.set("check", a.check);
  if (a.details && a.place.kind === "finding") q.set("details", "1");
  if (a.place.kind === "index" && a.place.tab === "findings") {
    if (a.sev) q.set("sev", a.sev);
    if (a.status) q.set("status", a.status);
  }
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
