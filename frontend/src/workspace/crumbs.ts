/** The centre's breadcrumb (spec 2026-10-04-review-workspace §2.4): every part but the current one is a link up. */
import type { Finding } from "../api";
import type { Story } from "../board/types";
import { href, type Place } from "./address";

export interface Crumb { label: string; to: string | null; handle?: string }
export interface CrumbContext {
  base: string;
  title: string;
  stories: Pick<Story, "id" | "title">[];
  findings: Pick<Finding, "id" | "title">[];
  cls: { cl: number; description: string | null }[];
  clusters: { id: string; name: string }[];
}

/** `text` without backticks, cut at a word to fit `n` characters with its ellipsis. */
export function short(text: string, n = 46): string {
  const t = text.replace(/`/g, "").trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n).lastIndexOf(" ");
  return `${t.slice(0, cut > 0 ? cut : n - 1)}…`;
}

const MISSING: Crumb = { label: "Not found", to: null };

export function crumbs(place: Place, c: CrumbContext): Crumb[] {
  const home = { label: c.title, to: c.base };
  if (place.kind === "whole") return place.view === "graph" ? [home, { label: "Graph", to: null }] : [{ label: c.title, to: null }];
  const section = (label: string, anchor: string): Crumb => ({ label, to: `${c.base}#${anchor}` });
  switch (place.kind) {
    case "story": {
      const st = c.stories.find((s) => s.id === place.sid);
      if (!st) return [home, section("Stories", "stories"), MISSING];
      const graph = place.view === "graph";
      const me: Crumb = { label: short(st.title), handle: st.id,
                          to: graph ? href(c.base, { place: { ...place, view: "steps" }, flow: null, open: null, tab: "diff" }) : null };
      return [home, section("Stories", "stories"), me, ...(graph ? [{ label: "Graph", to: null }] : [])];
    }
    case "finding": {
      const f = c.findings.find((x) => x.id === place.fid);
      return [home, section("Findings", "findings"), f ? { label: short(f.title), handle: f.id, to: null } : MISSING];
    }
    case "cl": {
      const cl = c.cls.find((x) => x.cl === place.cl);
      const first = cl?.description?.trim().split("\n")[0];
      return [home, section("Change set", "changeset"),
              cl ? { label: short(`CL ${cl.cl}${first ? ` · ${first}` : ""}`), to: null } : MISSING];
    }
    case "cluster": {
      const k = c.clusters.find((x) => x.id === place.cid);
      return [home, section("Map", "map"), k ? { label: short(k.name), to: null } : MISSING];
    }
    case "unknown":
      return [home, MISSING];
  }
}
