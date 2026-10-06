/** Change stories (spec 2026-10-04-change-stories §3, §5): the list's sections, ‹ › order and a repeated edit's sites. */
import type { Story, StorySet, StorySite } from "../board/types";

export interface Sections {
  behaviour: Story[];
  /** Behaviour stories past the list's limit, listed under "N more behaviour stories". */
  collapsed: Story[];
  other: Story[];
  mechanical: Story[];
  tests: Story[];
  /** Pieces the strong model could not place, or whose placement failed a check: listed last. */
  unsorted: Story[];
}

export function sections(ss: StorySet): Sections {
  const of = (k: Story["kind"]) => ss.stories.filter((s) => s.kind === k);
  return {
    behaviour: of("behaviour").filter((s) => !s.collapsed), collapsed: of("behaviour").filter((s) => s.collapsed),
    other: of("other"), mechanical: of("mechanical"), tests: of("tests"), unsorted: of("unsorted"),
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

/** A placement's reason in words (spec 2026-10-05-two-tier-stories §4.2, §6); in the Unsorted story the reason is the
 * check that failed, shown as it is. */
const REASONS: Record<string, string> = {
  starts_purpose: "starts the story", same_feature: "same feature", caller_of_new_code: "calls the new code",
  same_fix: "same fix", same_refactor: "same refactor", shared_code: "code shared with another target",
  declaration_used: "declares what the story uses", split_too_big: "split from a larger story",
  linked: "calls or shares data with the rest", tests: "tests of this target", repeated: "the same edit repeated",
};
export function reasonText(reason: string): string {
  return REASONS[reason] ?? reason;
}

/** Every build target the review's stories hold, sorted. */
export function reviewTargets(ss: StorySet): string[] {
  return [...new Set(ss.stories.flatMap((s) => s.targets ?? []))].sort();
}

/** "S4 · modem": a related story, with its targets. */
export function relatedLabel(ss: StorySet, sid: string): string {
  const t = ss.stories.find((s) => s.id === sid)?.targets ?? [];
  return t.length ? `${sid} · ${t.join(", ")}` : sid;
}

/** A verdict's citation: a node id, or a file and line (as the prepared facts show them). */
export function citeTarget(cite: string): { node: string } | { file: string; line: number } | null {
  if (/^N\d+$/.test(cite)) return { node: cite };
  const m = /^(.+):(\d+)$/.exec(cite);
  return m ? { file: m[1], line: Number(m[2]) } : null;
}
