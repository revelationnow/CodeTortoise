/** A story's Flows tab (spec 2026-10-25-review-ui-redesign §7): its flows grouped by what changed, each group's title,
 * line and causes, each flow's one-line sentence and the checks it asks about. Pure, so the rules are tested apart from
 * React. Names come back in backticks, for `Ticks`. */
import type { BoardFlow } from "../board/types";
import { placeOpen } from "./causes";
import type { Cause, Check, CheckKind, Mark } from "./types";

export type Label = (id: string) => string;
export type GroupKind = "field" | "writer" | "function";
/** A flow and its 1-based position in the story's list (as `flow=N` addresses and the Graph tab number it). */
export interface FlowRow { flow: BoardFlow; n: number }
/** `node`: the field, the writer or the changed function; rows in the story's order. */
export interface FlowGroup { key: string; kind: GroupKind; node: string; rows: FlowRow[] }

/** A group shows this many rows before `Show N more` (§7.3). */
export const FOLD_AT = 8;
const CONTRACT_KINDS: readonly CheckKind[] = ["caller", "result", "target", "unanalysed"];
const code = (s: string) => `\`${s}\``;
export const flowsWord = (n: number) => `${n} flow${n === 1 ? "" : "s"}`;

/** The changed function a flow comes from: its `cause` (every flow of a story with a reading names it); a contract
 * path ends at it. */
export function changedOf(f: Pick<BoardFlow, "tag" | "path" | "cause">): string {
  return f.cause ?? (f.tag === "contract" ? f.path[f.path.length - 1] : "");
}

/** A state flow's field (§7.1): the node before its landing, when that node is not the writer (`board.py`
 * `build_flows` puts the field there); null for a contract flow or a state flow without one. */
export function fieldOf(f: Pick<BoardFlow, "tag" | "path" | "cause">): string | null {
  if (f.tag !== "state" || f.path.length < 2 || !f.cause) return null;
  const n = f.path[f.path.length - 2];
  return n === f.cause ? null : n;
}

/** The story's flows grouped (§7.1): a state flow by its field, else its writer; a contract flow by its changed
 * function. Groups in the order of their first flow. */
export function flowGroups(flows: BoardFlow[]): FlowGroup[] {
  const out: FlowGroup[] = [], byKey = new Map<string, FlowGroup>();
  flows.forEach((flow, i) => {
    const field = fieldOf(flow);
    const kind: GroupKind = flow.tag === "contract" ? "function" : field ? "field" : "writer";
    const node = field ?? changedOf(flow), key = `${kind}:${node}`;
    let g = byKey.get(key);
    if (!g) {
      g = { key, kind, node, rows: [] };
      byKey.set(key, g);
      out.push(g);
    }
    g.rows.push({ flow, n: i + 1 });
  });
  return out;
}

/** Names in code style, each once, in order; past `max`, "and N more" (§7.2). */
export function someNames(names: string[], max = 3): string {
  const u = [...new Set(names)], head = u.slice(0, max).map(code).join(", ");
  return u.length > max ? `${head} and ${u.length - max} more` : head;
}

/** A contract flow's ending, after the last ⟶ of its text: "signature changed", "-2 ignored", "-2 unhandled". */
export function tail(text: string): string {
  const i = text.lastIndexOf("⟶ ");
  return i < 0 ? "" : text.slice(i + 2);
}

/** A group's title (§7.2). */
export function groupTitle(g: FlowGroup, label: Label): string {
  const name = code(label(g.node));
  if (g.kind === "field") {
    const writers = [...new Set(g.rows.map((r) => label(changedOf(r.flow))))];
    return writers.length === 1 ? `${name} gets a new writer: ${code(writers[0])}` : `${name} gets new writers: ${someNames(writers)}`;
  }
  if (g.kind === "writer") return `New writes by ${name}`;
  const ends = g.rows.map((r) => tail(r.flow.text));
  if (ends.every((e) => e === "signature changed")) return `${name}'s signature changed`;
  if (ends.every((e) => e.endsWith(" ignored") || e.endsWith(" unhandled"))) return `${name} returns new values`;
  return `${name} changed`;
}

/** The line under a group's title (§7.2): who reads or calls, how many flows, and how many still have a place open. */
export function groupLine(g: FlowGroup, label: Label, open: number): string {
  const who = someNames(g.rows.map((r) => label(r.flow.lands)));
  return `${g.kind === "function" ? "called by" : "read by"} ${who} · ${flowsWord(g.rows.length)}${open ? ` · ${open} open` : ""}`;
}

/** A group's line in the outline (§7.6): its field, its writer's writes or its function. */
export function groupShort(g: FlowGroup, label: Label): string {
  return g.kind === "writer" ? `${code(label(g.node))}'s writes` : code(label(g.node));
}

/** A row's one line (§7.3): a state flow's reader, field and writer; a contract flow's title, its landing in code style. */
export function rowSentence(f: BoardFlow, label: Label): string {
  const reader = code(label(f.lands));
  if (f.tag === "state") {
    const field = fieldOf(f), writer = code(label(changedOf(f)));
    return field ? `${reader} sees a new writer of ${code(label(field))} · via ${writer}` : `${reader} sees new writes by ${writer}`;
  }
  const l = label(f.lands);
  return f.title.startsWith(l) ? `${reader}${f.title.slice(l.length)}` : f.title;
}

/** The checks a flow asks about (§7.5), hidden kinds left out: those its change raised at its landing — a reader of its
 * field, or a caller's, result's, target's or unanalysed row. None on a reading stored before `related`. */
export function flowPlaces(f: BoardFlow, checks: Check[], hidden: ReadonlySet<CheckKind>, label: Label): Check[] {
  if (!f.cause) return [];
  const field = fieldOf(f), name = field ? label(field) : null;
  return checks.filter((k) => !hidden.has(k.kind) && !!k.related && k.related === f.cause && k.node === f.lands
    && (f.tag === "state" ? k.kind === "reader" && (name === null || k.field === name) : CONTRACT_KINDS.includes(k.kind)));
}

/** Every flow's places, by flow id. */
export function placesOf(flows: BoardFlow[], checks: Check[], hidden: ReadonlySet<CheckKind>, label: Label): Map<string, Check[]> {
  return new Map(flows.map((f) => [f.id, flowPlaces(f, checks, hidden, label)]));
}

/** The keys of a flow's places still open. */
export function openKeys(places: Check[], marks: Record<string, Mark>): string[] {
  return places.filter((k) => placeOpen(k.key, marks)).map((k) => k.key);
}

/** How many of a group's flows have a place still open. */
export function openFlows(g: FlowGroup, places: Map<string, Check[]>, marks: Record<string, Mark>): number {
  return g.rows.filter((r) => openKeys(places.get(r.flow.id) ?? [], marks).length > 0).length;
}

/** The story's shown causes between its groups and the end line (§7.4), each keeping its order: a reader with its
 * field's group, a caller's kinds with their function's (on a reading stored before `related`, with the group holding
 * the cause's first flow), a hazard or confirm with the group of its finding's flow; the rest at the end. */
export function groupCauses(groups: FlowGroup[], causes: Cause[], checks: Check[], label: Label): { byGroup: Map<string, Cause[]>; rest: Cause[] } {
  const byKey = new Map(checks.map((k) => [k.key, k]));
  const holding = (id: string) => groups.find((g) => g.rows.some((r) => r.flow.id === id));
  const byGroup = new Map<string, Cause[]>(), rest: Cause[] = [];
  for (const c of causes) {
    const ks = c.places.flatMap((p) => byKey.get(p) ?? []), finding = c.finding;
    let g: FlowGroup | undefined;
    if (c.kind === "reader") {
      const fields = new Set(ks.map((k) => k.field));
      g = groups.find((x) => x.kind === "field" && fields.has(label(x.node)));
    } else if (CONTRACT_KINDS.includes(c.kind)) {
      const related = ks.find((k) => k.related)?.related;
      g = related ? groups.find((x) => x.kind === "function" && x.node === related) : c.flows.length ? holding(c.flows[0]) : undefined;
    } else if ((c.kind === "hazard" || c.kind === "confirm") && finding) {
      g = groups.find((x) => x.rows.some((r) => r.flow.findings.includes(finding)));
    }
    if (g) byGroup.set(g.key, [...(byGroup.get(g.key) ?? []), c]);
    else rest.push(c);
  }
  return { byGroup, rest };
}
