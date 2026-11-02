/** Walk-throughs (spec 2026-11-02-design-overview §4): their threads and open counts, the links a story page, its Flows tab,
 * the outline and the overview make to them, and each step's line and where it comes from. Pure, so the rules are tested
 * apart from React. Names come back in backticks, for `Ticks`. */
import { placeOpen } from "./causes";
import { letter } from "./checks";
import type { Check, CheckKind, Mark, ReadingDesign, Thread, Walk, WalkStep } from "./types";

type Label = (id: string) => string;
type Walks = Pick<ReadingDesign, "walks"> | null | undefined;

/** A name in code style; a backtick inside it becomes a quote, as the Flows tab's names do (`Ticks` pairs them by position). */
const code = (s: string) => `\`${s.replaceAll("`", "'")}\``;

/** "Thread B", lettered as the outline letters it; null for a thread the reading no longer has. */
export function threadName(threads: Pick<Thread, "id">[], tid: string): string | null {
  const i = threads.findIndex((t) => t.id === tid);
  return i < 0 ? null : `Thread ${letter(i, tid)}`;
}

/** A walk-through's threads: its own, then the other end of the connection it is anchored on. */
export function walkThreads(w: Pick<Walk, "thread" | "connection">): string[] {
  return [w.thread, ...(w.connection ?? [])].filter((id, i, all): id is string => !!id && all.indexOf(id) === i);
}

/** "Thread A with Thread B" (§3.2): its threads by name; "" when the reading has none of them. */
export function walkScope(w: Pick<Walk, "thread" | "connection">, threads: Pick<Thread, "id">[]): string {
  return walkThreads(w).map((t) => threadName(threads, t)).filter((n): n is string => !!n).join(" with ");
}

/** A step's check keys that the reading still holds, of the kinds shown: what its tick box marks. */
export function stepKeys(st: Pick<WalkStep, "keys">, checks: ReadonlyMap<string, Check>, hidden: ReadonlySet<CheckKind>): string[] {
  return st.keys.filter((k) => {
    const c = checks.get(k);
    return !!c && !hidden.has(c.kind);
  });
}

/** A walk-through's open count (§4.3): the distinct causes among its steps' shown checks that are still open. */
export function walkOpen(w: Pick<Walk, "steps">, checks: ReadonlyMap<string, Check>, hidden: ReadonlySet<CheckKind>,
                         marks: Record<string, Mark>): number {
  const open = new Set<string>();
  for (const st of w.steps)
    for (const k of stepKeys(st, checks, hidden)) if (placeOpen(k, marks)) open.add(checks.get(k)!.cause ?? k);
  return open.size;
}

/** The steps (1-based) with a shown check still open: the drawing puts their numbers on red. */
export function openSteps(w: Pick<Walk, "steps">, checks: ReadonlyMap<string, Check>, hidden: ReadonlySet<CheckKind>,
                          marks: Record<string, Mark>): Set<number> {
  return new Set(w.steps.flatMap((st, i) => (stepKeys(st, checks, hidden).some((k) => placeOpen(k, marks)) ? [i + 1] : [])));
}

/** The walk-throughs a thread's outline bar lists (§3.2): its own and those on a connection to it, in the design's order;
 * `other` is the connection's other thread. */
export function walksForThread(design: Walks, tid: string): { walk: Walk; other: string | null }[] {
  return (design?.walks ?? []).filter((w) => w.thread === tid || !!w.connection?.includes(tid))
    .map((w) => ({ walk: w, other: w.connection?.find((t) => t !== tid) ?? null }));
}

/** The first walk-through on the connection between threads `a` and `b` (§3.1): its line on the overview links to it. */
export function connectionWalk(design: Walks, a: string, b: string): Walk | null {
  return design?.walks.find((w) => !!w.connection && w.connection.includes(a) && w.connection.includes(b)) ?? null;
}

/** The walk-throughs a story's steps are on, with those steps' numbers (1-based), for its header (§3.2). */
export function storyWalks(design: Walks, sid: string): { walk: Walk; steps: number[] }[] {
  return (design?.walks ?? []).map((walk) => ({ walk, steps: walk.steps.flatMap((s, i) => (s.story === sid ? [i + 1] : [])) }))
    .filter((x) => x.steps.length > 0);
}

/** "1–5, 8": step numbers, a run of three or more as its ends. */
export function stepList(ns: number[]): string {
  const out: string[] = [];
  for (let i = 0; i < ns.length;) {
    let j = i;
    while (j + 1 < ns.length && ns[j + 1] === ns[j] + 1) j++;
    out.push(...(j - i >= 2 ? [`${ns[i]}–${ns[j]}`] : ns.slice(i, j + 1).map(String)));
    i = j + 1;
  }
  return out.join(", ");
}

/** The steps that are a story's flow (a flow step, not the call path that leads to it), for its Flows row (§3.2). */
export function flowSteps(design: Walks, sid: string, flow: string): { walk: Walk; n: number }[] {
  return (design?.walks ?? []).flatMap((walk) => walk.steps.flatMap((s, i) => (
    s.ref === "flow" && s.story === sid && s.flow === flow ? [{ walk, n: i + 1 }] : [])));
}

/** A step's one line (§4.1): who calls, returns to, writes or reads what, in the code's own words. */
export function stepSentence(st: WalkStep, label: Label): string {
  const a = label(st.src), b = label(st.dst), says = st.label ? code(st.label) : "";
  switch (st.kind) {
    case "call":
      return says && st.label.startsWith(b) ? `${code(a)} calls ${says}` : `${code(a)} calls ${code(b)}${says ? `: ${says}` : ""}`;
    case "return": return says ? `${code(a)} returns ${says} to ${code(b)}` : `${code(a)} returns to ${code(b)}`;
    case "write": return `${code(a)} writes ${code(b)}${says ? `: ${says}` : ""}`;
    case "read": return `${code(b)} reads ${code(a)}${says ? `: ${says}` : ""}`;
    case "fold": return `… ${st.folded} call${st.folded === 1 ? "" : "s"}, ${code(a)} to ${code(b)}`;
    default: return `${code(a)}${says ? `: ${says}` : ""}`;
  }
}

/** Where a step comes from (§3.3) and the story tab that shows it: a call path's ("call path of S1 flow 1", the Call paths
 * tab), the change's ("S1 · the change", the Code tab), a flow's ("S1 flow 1", that row of the first tab). A step of the
 * code between them names the function its code is in, and links nowhere: there is no depot path to open. */
export interface StepRef { text: string; link: { story: string; sec: "paths" | "code" | null; flow: number | null } | null }

export function stepRef(st: WalkStep, label: Label): StepRef {
  if (st.ref === "path" && st.story)
    return { text: `call path of ${st.story}${st.flow_n ? ` flow ${st.flow_n}` : ""}`, link: { story: st.story, sec: "paths", flow: null } };
  if (st.ref === "change" && st.story) return { text: `${st.story} · the change`, link: { story: st.story, sec: "code", flow: null } };
  if (st.ref === "flow" && st.story)
    return { text: st.flow_n ? `${st.story} flow ${st.flow_n}` : `${st.story}'s flows`, link: { story: st.story, sec: null, flow: st.flow_n } };
  if (st.kind === "fold") return { text: "unchanged", link: null };
  return { text: `${code(label(st.kind === "read" ? st.dst : st.src))}, ${st.status === "same" ? "unchanged" : st.status}`, link: null };
}
