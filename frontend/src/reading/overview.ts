/** The overview's rules (spec 2026-10-25-review-ui-redesign §5): its heading and start button, each thread section's
 * counts, action and connections, the Tests row, the thread intro and the folded rows after the threads. */
import { openCount } from "./causes";
import { letter } from "./checks";
import type { Cause, CheckKind, Connection, Mark, Reading, TestsRow, Thread } from "./types";

/** "A", "A and B", "A, B and C". */
export function listed(xs: string[]): string {
  return xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
}

/** "Tests: 6 cover threads A and B · nothing tests C". */
export function testsLine(t: TestsRow, threads: Thread[]): string {
  const name = new Map(threads.map((th, i) => [th.id, letter(i, th.id)]));
  const of = (ids: string[]) => listed(ids.map((id) => name.get(id) ?? id));
  return `Tests: ${t.functions}${t.covers.length ? ` cover thread${t.covers.length === 1 ? "" : "s"} ${of(t.covers)}` : ""}`
    + (t.untested.length ? ` · nothing tests ${of(t.untested)}` : "");
}

/** A thread card's paragraphs: the strong model's intro alone (it says what the thread does), else the purpose above the
 * fixed intro, so a card never loses the sentence that says what its thread does. */
export function cardText(t: Thread): { text: string; ai: boolean }[] {
  if (t.intro && t.intro_source === "llm") return [{ text: t.intro, ai: true }];
  return [...(t.purpose ? [{ text: t.purpose, ai: t.text_source === "llm" }] : []), ...(t.intro ? [{ text: t.intro, ai: false }] : [])];
}

/** "5 threads", "1 thread"; "The change" when there are none (§5.1). */
export const overviewHeading = (n: number): string => (n === 0 ? "The change" : n === 1 ? "1 thread" : `${n} threads`);

/** The start button (§5.1): the first unread story in reading order, named by its thread until the reader starts. */
export function startButton(r: Pick<Reading, "order" | "threads">, read: ReadonlySet<string>): { sid: string; label: string } | null {
  const sid = r.order.find((s) => !read.has(s));
  if (!sid) return null;
  if (r.order.some((s) => read.has(s))) return { sid, label: "Continue ›" };
  const i = r.threads.findIndex((t) => t.stories.includes(sid));
  return { sid, label: i < 0 ? "Start here ›" : `Start with Thread ${letter(i, r.threads[i].id)} ›` };
}

/** A thread section's one action (§5.2): Start at its first story, Continue at its first unread one, or all read. */
export type ThreadAction = { kind: "start" | "continue"; sid: string } | { kind: "done" };

export function threadAction(stories: string[], read: ReadonlySet<string>): ThreadAction | null {
  if (!stories.length) return null;
  const unread = stories.find((s) => !read.has(s));
  if (!unread) return { kind: "done" };
  return { kind: stories.some((s) => read.has(s)) ? "continue" : "start", sid: unread };
}

/** A thread section's counts (§5.2): its stories, its shown causes still open (null on a reading without causes), and
 * how many of its stories the reader has read. */
export function threadCounts(t: Thread, causes: Cause[] | null | undefined, hidden: ReadonlySet<CheckKind>,
                             marks: Record<string, Mark>, read: ReadonlySet<string>): { stories: number; open: number | null; read: number } {
  return {
    stories: t.stories.length,
    open: causes ? openCount(causes.filter((c) => c.thread === t.id), hidden, marks) : null,
    read: t.stories.filter((s) => read.has(s)).length,
  };
}

/** One line of how the threads connect: the connection's `text` between what the app adds around it (`before` names the
 * earlier thread, `after` says a bundled pair is the author's to explain). `ai`: the strong model reworded the text, and only
 * the text is its words. */
export interface SectionLink { before: string; text: string; after: string; ai: boolean; bundled: boolean }

/** How the threads connect (§5.2): each shown connection under the later of its threads, as "With Thread A: …". */
export function sectionConnections(threads: Thread[], conns: Connection[]): Map<string, SectionLink[]> {
  const at = new Map(threads.map((t, i) => [t.id, i]));
  const out = new Map<string, SectionLink[]>();
  for (const k of conns) {
    const a = at.get(k.a), b = at.get(k.b);
    if (!k.shown || a === undefined || b === undefined || a === b) continue;
    const early = Math.min(a, b), late = threads[Math.max(a, b)].id, bundled = k.kind === "bundled";
    const row = { before: `With Thread ${letter(early, threads[early].id)}: `, text: k.text, after: bundled ? " — ask the author" : "",
                  ai: k.text_source === "llm", bundled };
    out.set(late, [...(out.get(late) ?? []), row]);
  }
  return out;
}

/** The folded rows after the threads (§5.3): Build impact and Coverage only when they have something to say. */
export function foldTitles(r: Pick<Reading, "build_impact" | "coverage" | "rules_only" | "sinks">,
                           comments: { parent_id: number | null; anchor_kind: string }[]):
  { build: string | null; coverage: string | null; discussion: string } {
  const most = Math.max(0, ...r.build_impact.map((b) => b.files));
  const notes = r.coverage.length + (r.rules_only ? 1 : 0) + ((r.sinks?.length ?? 0) > 0 ? 1 : 0);
  const talk = comments.filter((c) => c.parent_id === null && (c.anchor_kind === "review" || c.anchor_kind === "chapter")).length;
  return {
    build: !r.build_impact.length ? null
      : most === 0 ? "Build impact" : `Build impact · up to ${most} ${most === 1 ? "file rebuilds" : "files rebuild"}`,
    coverage: notes ? `Coverage · ${notes} note${notes === 1 ? "" : "s"}` : null,
    discussion: talk ? `Discussion · ${talk} comment${talk === 1 ? "" : "s"}` : "Discussion · no comments yet",
  };
}
