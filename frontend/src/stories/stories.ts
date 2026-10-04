/** Change stories (spec 2026-10-04-change-stories §3, §5): the list's sections, ‹ › order and a repeated edit's sites. */
import type { Board, Story, StorySet, StorySite } from "../board/types";

export interface Sections {
  behaviour: Story[];
  /** Behaviour stories past the list's limit, listed under "N more behaviour stories". */
  collapsed: Story[];
  other: Story[];
  mechanical: Story[];
  tests: Story[];
}

export function sections(ss: StorySet): Sections {
  const of = (k: Story["kind"]) => ss.stories.filter((s) => s.kind === k);
  return {
    behaviour: of("behaviour").filter((s) => !s.collapsed), collapsed: of("behaviour").filter((s) => s.collapsed),
    other: of("other"), mechanical: of("mechanical"), tests: of("tests"),
  };
}

/** The story `by` places from `sid` in list order, wrapping around. */
export function stepStory(ss: StorySet, sid: string, by: number): string {
  const ids = ss.stories.map((s) => s.id), i = ids.indexOf(sid);
  return ids[(((i < 0 ? 0 : i) + by) % ids.length + ids.length) % ids.length];
}

/** "2 flows · 1 finding · 4 functions" (zero counts left out). */
export function countLine(s: Story): string {
  const c = s.counts, part = (n: number | undefined, one: string, many = `${one}s`) => (n ? `${n} ${n === 1 ? one : many}` : "");
  const parts = s.kind === "mechanical"
    ? [part(c.sites, "site"), part(c.files, "file"), part(c.test_sites, "in tests", "in tests")]
    : [part(c.flows, "flow"), part(c.findings, "finding"), part(c.functions, "function"), part(c.files, "file")];
  return parts.filter(Boolean).join(" · ");
}

export interface SiteFile { path: string; name: string; sites: StorySite[] }
export interface SiteDir { dir: string; files: SiteFile[]; count: number }

/** A repeated edit's sites by directory, then file (in line order); `hideTests` leaves test sites out. */
export function groupSites(sites: StorySite[], hideTests: boolean): SiteDir[] {
  const dirs = new Map<string, Map<string, StorySite[]>>();
  for (const s of sites) {
    if (hideTests && s.test) continue;
    const path = s.path ?? "(unknown file)", cut = path.lastIndexOf("/");
    const dir = cut > 0 ? path.slice(0, cut) : "";
    const files = dirs.get(dir) ?? new Map<string, StorySite[]>();
    files.set(path, [...(files.get(path) ?? []), s]);
    dirs.set(dir, files);
  }
  return [...dirs.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([dir, files]) => {
    const fs = [...files.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([path, ss]) => ({ path, name: path.slice(path.lastIndexOf("/") + 1), sites: [...ss].sort((a, b) => a.line - b.line) }));
    return { dir, files: fs, count: fs.reduce((n, f) => n + f.sites.length, 0) };
  });
}

/** Sites past which files start closed (a very large repeated edit lists files with a count, spec §6). */
export const OPEN_SITES = 200;

/** Where "Whole graph ›" goes: the board holding the story's first node, focused on it; a story without code of its
 * own (a repeated edit's flows) focuses on `cause`, its first flow's. */
export function wholeGraph(reviewId: number, s: Story, cause?: string | null): string {
  const at = s.nodes[0] ?? cause;
  const node = at ? `?node=${encodeURIComponent(at)}` : "";
  return s.board ? `/r/${reviewId}/c/${s.board}${node}` : `/r/${reviewId}/board${node}`;
}

/** The story graph's node to focus for `?node=`: a field folded into a struct focuses the struct's node. */
export function graphFocus(graph: Board | null, node: string | null): string | null {
  if (!node || !graph) return node;
  return graph.nodes.find((n) => n.fields?.some((f) => f.id === node))?.id ?? node;
}
