/** The side panel's tabs (spec 2026-10-12-story-account-and-panels §2.2): every item opened this visit, oldest first,
 * at most MAX_TABS. Pure, so the rules are tested apart from React. */
import type { Names } from "../api";
import type { Cause } from "../reading/types";
import type { Item } from "./address";
import { short } from "./crumbs";
import { plainNames } from "./names";

export const MAX_TABS = 8;

/** One key per item: a file's tab is the file's, whatever line it opened at. */
export const openKey = (o: Item): string => ("finding" in o ? `f:${o.finding}` : "node" in o ? `n:${o.node}`
  : "cause" in o ? `c:${o.cause}` : `d:${o.file}`);

/** The tabs with `o` opened: an item already there keeps its place and takes the new line; a new one goes last, and
 * past the cap the oldest goes (never `o`, the active one). */
export function addTab(tabs: Item[], o: Item): Item[] {
  const i = tabs.findIndex((t) => openKey(t) === openKey(o));
  if (i >= 0) return JSON.stringify(tabs[i]) === JSON.stringify(o) ? tabs : tabs.map((t, k) => (k === i ? o : t));
  const next = [...tabs, o];
  return next.length > MAX_TABS ? next.slice(next.length - MAX_TABS) : next;
}

/** The tabs without `o`, and what the panel shows next: undefined (no change) when `o` was not active; else its left
 * neighbour, the right one when it was first, or null (the panel closes) when it was the last tab. */
export function closeTab(tabs: Item[], o: Item, active: Item | null): { tabs: Item[]; next: Item | null | undefined } {
  const i = tabs.findIndex((t) => openKey(t) === openKey(o));
  if (i < 0) return { tabs, next: undefined };
  const rest = tabs.filter((_, k) => k !== i);
  if (!active || openKey(active) !== openKey(o)) return { tabs: rest, next: undefined };
  return { tabs: rest, next: rest.length ? rest[Math.max(0, i - 1)] : null };
}

/** A tab's name: the finding's id, the file's name, the function's name or the check's line, shortened. */
export function tabLabel(o: Item, names: Names, causes: Cause[] = []): string {
  if ("finding" in o) return o.finding;
  if ("cause" in o) { const c = causes.find((x) => x.id === o.cause); return c ? short(plainNames(c.text, names), 40) : "Check"; }
  if ("file" in o) return o.file.slice(o.file.lastIndexOf("/") + 1);
  return names[o.node]?.label ?? "function";
}
