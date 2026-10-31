/** Landing-page review search and filter chips (pure). */
import type { ReviewRow } from "../api";

export type Chip = "all" | "high" | "running" | "mine";
/** The session's user on each Perforce server it is signed in to (spec 2026-10-31 §7). */
export type Who = Record<string, string>;
const RUNNING = new Set(["queued", "running"]);

const words = (q: string) => q.toLowerCase().split(/\s+/).filter(Boolean);
const haystack = (r: ReviewRow) =>
  [r.title, r.created_by, r.status, ...r.cls.map((c) => `${c} cl ${c} cl${c}`)].join(" ").toLowerCase();
/** Made by the session's sign-in on the review's own server: the same name on another server is someone else. */
const mine = (r: ReviewRow, who: Who) => !!r.workspace && who[r.workspace.server] === r.created_by;

function chipOk(r: ReviewRow, chip: Chip, who: Who) {
  return chip === "all" || (chip === "high" && r.risk === "high") || (chip === "running" && RUNNING.has(r.status))
    || (chip === "mine" && mine(r, who));
}

/** Rows matching every word of the query (title, CL number, author, status), the chip, and the workspace chip (null: any). */
export function filterReviews(rows: ReviewRow[], query: string, chip: Chip, who: Who, ws: number | null = null): ReviewRow[] {
  const qs = words(query.replace(/\bcl\s+(\d+)/gi, "cl$1"));
  return rows.filter((r) => (ws === null || r.workspace?.id === ws) && chipOk(r, chip, who) && qs.every((w) => haystack(r).includes(w)));
}

/** Each chip's count among the rows of the workspace chip pressed (null: all rows). */
export function chipCounts(rows: ReviewRow[], who: Who, ws: number | null = null): Record<Chip, number> {
  const pool = ws === null ? rows : rows.filter((r) => r.workspace?.id === ws);
  const n = (c: Chip) => pool.filter((r) => chipOk(r, c, who)).length;
  return { all: n("all"), high: n("high"), running: n("running"), mine: n("mine") };
}

/** A chip per workspace the rows come from, by name, with its count (spec 2026-10-31 §9); none when they all come from one. */
export function workspaceChips(rows: ReviewRow[]): { id: number; name: string; count: number }[] {
  const by = new Map<number, { id: number; name: string; count: number }>();
  for (const r of rows) {
    if (!r.workspace) continue;
    const c = by.get(r.workspace.id) ?? { id: r.workspace.id, name: r.workspace.name, count: 0 };
    c.count++;
    by.set(c.id, c);
  }
  return by.size > 1 ? [...by.values()].sort((a, b) => a.name.localeCompare(b.name)) : [];
}

/** New review's workspaces (spec 2026-10-31 §9): the last used first, then by name. */
export function pickOrder<T extends { id: number; name: string }>(owned: T[], last: number | null): T[] {
  return [...owned].sort((a, b) => Number(b.id === last) - Number(a.id === last) || a.name.localeCompare(b.name));
}

/** Title split into parts, marking every case-insensitive occurrence of any query word. */
export function highlight(text: string, query: string): { text: string; hit: boolean }[] {
  const ws = words(query).sort((a, b) => b.length - a.length);
  if (!ws.length) return [{ text, hit: false }];
  const re = new RegExp(`(${ws.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(re).filter(Boolean).map((t) => ({ text: t, hit: ws.includes(t.toLowerCase()) }));
}

export function parseCls(text: string): number[] {
  return [...new Set(text.split(/[\s,]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n) && n > 0))];
}

/** "just now", "5m", "3h", "2d" — compact age for review rows. */
export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, (now - Date.parse(iso)) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
