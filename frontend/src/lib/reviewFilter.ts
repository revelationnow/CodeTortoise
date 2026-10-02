/** Landing-page review search and filter chips (pure). */
import type { ReviewRow } from "../api";

export type Chip = "all" | "high" | "running" | "mine";
const RUNNING = new Set(["queued", "running"]);

const words = (q: string) => q.toLowerCase().split(/\s+/).filter(Boolean);
const haystack = (r: ReviewRow) =>
  [r.title, r.created_by, r.status, ...r.cls.map((c) => `${c} cl ${c} cl${c}`)].join(" ").toLowerCase();

function chipOk(r: ReviewRow, chip: Chip, user: string | null) {
  return chip === "all" || (chip === "high" && r.risk === "high") || (chip === "running" && RUNNING.has(r.status))
    || (chip === "mine" && r.created_by === user);
}

/** Rows matching every word of the query (title, CL number, author, status) and the chip. */
export function filterReviews(rows: ReviewRow[], query: string, chip: Chip, user: string | null): ReviewRow[] {
  const ws = words(query.replace(/\bcl\s+(\d+)/gi, "cl$1"));
  return rows.filter((r) => chipOk(r, chip, user) && ws.every((w) => haystack(r).includes(w)));
}

export function chipCounts(rows: ReviewRow[], user: string | null): Record<Chip, number> {
  const n = (c: Chip) => rows.filter((r) => chipOk(r, c, user)).length;
  return { all: n("all"), high: n("high"), running: n("running"), mine: n("mine") };
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
