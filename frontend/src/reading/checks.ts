/** Check kinds, their labels and order, and how a check is named and placed (spec 2026-10-07-review-reading §7). */
import { ago } from "../lib/reviewFilter";
import type { Check, CheckKind, Mark } from "./types";

export const KIND_LABEL: Record<CheckKind, string> = {
  hazard: "Hazard", confirm: "Confirm", caller: "Caller not updated", result: "Result handled the old way",
  reader: "Unchanged reader", target: "Other build target", untested: "No test touched", unanalysed: "Not analysed",
  ask: "Ask the author", cleared: "No hazard",
};

/** The kinds in the order the list shows them (§7.1). */
export const CHECK_ORDER: CheckKind[] = ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask"];

/** Open unless someone marked it and its line has not changed since (§7.4). */
export const isOpen = (k: Check, marks: Record<string, Mark>) => !marks[k.key] || marks[k.key].changed;

/** "A" … "Z", then the thread's id. */
export const letter = (i: number, id = "") => (i < 26 ? String.fromCharCode(65 + i) : id);

/** A story's thread for its breadcrumb, lettered as the rail letters it ("Thread A", "Thread T27"); "Tests" outside. */
export function threadLabel(threads: { id: string; stories: string[] }[], sid: string): string {
  const i = threads.findIndex((t) => t.stories.includes(sid));
  return i >= 0 ? `Thread ${letter(i, threads[i].id)}` : "Tests";
}

/** "svc/flush.c:3 in `flush`". */
export function placeOf(k: Check): string {
  if (!k.path) return "";
  return `${k.path}${k.line ? `:${k.line}` : ""}${k.function ? ` in \`${k.function}\`` : ""}`;
}

/** "Looks fine · ana · 2h ago", or that the line changed since it was marked. */
export function markLine(m: Mark, now = Date.now()): string {
  return m.changed ? `Changed since marked by ${m.user}` : `Looks fine · ${m.user} · ${ago(m.at, now)}`;
}
