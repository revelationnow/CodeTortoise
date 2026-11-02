/** The design overview's rules (spec 2026-11-02-design-overview §5, §7): Where the change sits' bands and blocks, and the
 * condition fold's title and lines. Pure, so the rules are tested apart from React. */
import { counted } from "../lib/tidy";
import { letter } from "./checks";
import { listed } from "./overview";
import type { Cause, Component, Gate, GatedLine, Ownership, ReadingDesign, Thread } from "./types";

/** Where the change sits shows only with two components or more (§14). */
export const showsWhere = (d: Pick<ReadingDesign, "components"> | null | undefined): boolean => (d?.components.length ?? 0) >= 2;

export interface Band { band: string; level: number | null; components: Component[] }

/** The components in their layers' bands (§5): the highest layer first, the bands without a level last; in a band, the
 * design's order. */
export function componentBands(cs: Component[]): Band[] {
  const out: Band[] = [];
  for (const c of cs) {
    const b = out.find((x) => x.band === c.band);
    if (b) b.components.push(c);
    else out.push({ band: c.band, level: c.level, components: [c] });
  }
  return out.sort((a, b) => (b.level ?? -1) - (a.level ?? -1));
}

/** A block's count line (§5): the threads that change it, by letter, and its changed files. */
export function blockLine(c: Pick<Component, "threads" | "files">, threads: Pick<Thread, "id">[]): string {
  const letters = c.threads.flatMap((id) => {
    const i = threads.findIndex((t) => t.id === id);
    return i < 0 ? [] : [letter(i, id)];
  });
  return [letters.length ? `Thread${letters.length === 1 ? "" : "s"} ${listed(letters)}` : "", counted(c.files.length, "changed file")]
    .filter(Boolean).join(" · ");
}

/** A block's `.also` line (§5): what changed in it, by its stories' titles, two at most. */
export function alsoLine(stories: string[], title: (sid: string) => string | undefined): string {
  const named = stories.flatMap((s) => {
    const t = title(s);
    return t ? [t] : [];
  });
  const more = named.length - 2;
  return named.slice(0, 2).join("; ") + (more > 0 ? `; and ${more} more` : "");
}

/** The condition the fold is about (§7): the strongest, which the design lists first, when it has lines to sort. */
export const foldGate = (d: Pick<ReadingDesign, "gates"> | null | undefined): Gate | null => (d?.gates[0]?.lines.length ? d.gates[0] : null);

/** The fold's title (§7): the false case in words (the model's, from phase 2; until then "When `test` is false") and how
 * many changes still run then. */
export function conditionTitle(g: Pick<Gate, "false_case" | "test" | "runs">): string {
  const n = g.runs;
  return `${g.false_case || `When \`${g.test.replaceAll("`", "'")}\` is false`} · ${n} change${n === 1 ? "" : "s"} still run${n === 1 ? "s" : ""}`;
}

/** The fold's lines: those that still run when the condition is false, then those that don't. */
export function gateGroups(g: Pick<Gate, "lines">): { runs: GatedLine[]; stops: GatedLine[] } {
  return { runs: g.lines.filter((l) => l.runs), stops: g.lines.filter((l) => !l.runs) };
}

/** The verdict's chips (spec 2026-11-02 §3.1): the causes it names that the review has, in its order. */
export function verdictCauses(d: Pick<ReadingDesign, "verdict_causes">, causes: Cause[] | null | undefined): Cause[] {
  const by = new Map((causes ?? []).map((c) => [c.id, c]));
  return d.verdict_causes.flatMap((id) => by.get(id) ?? []);
}

/** An ownership line's tag as the check tags draw it (§6.2): a questionable line looks like a `confirm` tag. */
export const OWNER_TAG: Record<Ownership["tag"], string> = { right: "right", questionable: "confirm", shortfall: "shortfall", note: "note" };

/** The ownership fold's title (§3.1 item 8): how many lines are questionable and how many are shortfalls. */
export function ownershipTitle(lines: Pick<Ownership, "tag">[]): string {
  const q = lines.filter((l) => l.tag === "questionable").length, s = lines.filter((l) => l.tag === "shortfall").length;
  const said = [q ? `${q} questionable` : "", counted(s, "shortfall")].filter(Boolean);
  return `Is the design right? · ${said.length ? said.join(" · ") : "nothing questionable"}`;
}

/** Where a concern is done (§6.1): the letters of its stories' threads, each once, then its stories. */
export function concernWhere(stories: string[], threads: Pick<Thread, "id" | "stories">[]): { letters: string[]; stories: string[] } {
  const letters: string[] = [];
  for (const s of stories) {
    const i = threads.findIndex((t) => t.stories.includes(s));
    const L = i < 0 ? null : letter(i, threads[i].id);
    if (L && !letters.includes(L)) letters.push(L);
  }
  return { letters, stories };
}

/** The concerns a story answers (§3.2), numbered from 1 as the overview's table numbers them: its crumb cites them. */
export const storyConcerns = (d: Pick<ReadingDesign, "concerns"> | null | undefined, sid: string): number[] =>
  (d?.concerns ?? []).flatMap((c, i) => (c.stories.includes(sid) ? [i + 1] : []));

/** Whether the model wrote a part — `verdict`, `concerns`, `ownership`, `walk:W1`, `gate:G1` — as the design's sources
 * say (§9); a pinned part is the model's words kept (phase 4). */
export const byModel = (d: Pick<ReadingDesign, "sources"> | null | undefined, part: string): boolean =>
  d?.sources[part] === "llm" || d?.sources[part] === "pinned";

/** An ownership line's cite as the reader sees it (§6.2): a function's or field's name for its id; a story id or a path
 * as cited. */
export const citeName = (d: Pick<ReadingDesign, "nodes">, cite: string): string => d.nodes[cite]?.label ?? cite;
