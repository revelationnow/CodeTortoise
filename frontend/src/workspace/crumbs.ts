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
  /** With a reading: a story's thread ("Thread A", "Tests"); CLs, files, checks and the map then live in the Index. */
  threadOf?: (sid: string) => string | null;
}

export const INDEX_LABEL = { cls: "CLs", files: "Files", checks: "Checks", map: "Map" } as const;

/** `text` without backticks, cut at a word to fit `n` characters with its ellipsis. */
export function short(text: string, n = 46): string {
  const t = text.replace(/`/g, "").trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n).lastIndexOf(" ");
  return `${t.slice(0, cut > 0 ? cut : n - 1)}…`;
}

const missing = (): Crumb => ({ label: "Not found", to: null });

export function crumbs(place: Place, c: CrumbContext): Crumb[] {
  const home = { label: c.title, to: c.base };
  if (place.kind === "whole") return place.view === "graph" ? [home, { label: "Graph", to: null }] : [{ label: c.title, to: null }];
  const reading = !!c.threadOf;
  const tab = (t: keyof typeof INDEX_LABEL): Crumb => ({ label: INDEX_LABEL[t], to: `${c.base}/i/${t}` });
  const section = (label: string, anchor: string): Crumb => (
    reading && anchor === "findings" ? tab("checks") : reading && anchor === "changeset" ? tab("cls")
      : reading && anchor === "map" ? tab("map") : { label, to: `${c.base}#${anchor}` });
  switch (place.kind) {
    case "story": {
      const st = c.stories.find((s) => s.id === place.sid);
      const up = c.threadOf?.(place.sid);
      const parent = up ? { label: up, to: c.base } : section("Stories", "stories");
      if (!st) return [home, parent, missing()];
      const graph = place.view === "graph";
      const me: Crumb = { label: short(st.title), handle: st.id,
                          to: graph ? href(c.base, { place: { ...place, view: "steps" }, flow: null, open: null, tab: "diff" }) : null };
      return [home, parent, me, ...(graph ? [{ label: "Graph", to: null }] : [])];
    }
    case "finding": {
      const f = c.findings.find((x) => x.id === place.fid);
      return [home, section("Findings", "findings"), f ? { label: short(f.title), handle: f.id, to: null } : missing()];
    }
    case "cl": {
      const cl = c.cls.find((x) => x.cl === place.cl);
      const first = cl?.description?.trim().split("\n")[0];
      return [home, section("Change set", "changeset"),
              cl ? { label: short(`CL ${cl.cl}${first ? ` · ${first}` : ""}`), to: null } : missing()];
    }
    case "cluster": {
      const k = c.clusters.find((x) => x.id === place.cid);
      return [home, section("Map", "map"), k ? { label: short(k.name), to: null } : missing()];
    }
    case "index":
      return [home, { label: INDEX_LABEL[place.tab], to: null }];
    case "unknown":
      return [home, missing()];
  }
}
