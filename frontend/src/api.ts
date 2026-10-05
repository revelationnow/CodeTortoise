export type Severity = "info" | "low" | "medium" | "high";
export type StageStatus = "pending" | "running" | "ok" | "degraded" | "failed" | "skipped";

export interface Me { user: string; is_owner: boolean; swarm_ready: boolean }
export interface ReviewRow {
  id: number; title: string; created_by: string; created_at: string;
  status: string; risk: "low" | "medium" | "high" | null; cls: number[];
}
export interface Stage { name: string; status: StageStatus; message: string; started_at: string | null; finished_at: string | null }
export interface SwarmInfo { id: number; state: string; state_label?: string; url: string; votes: Record<string, number>; author?: string }
export interface ClRow { review_id: number; cl: number; status: string; user: string | null; description: string | null; swarm: SwarmInfo | null }
export interface ReviewDetail { review: ReviewRow; cls: ClRow[]; stages: Stage[] }

export interface Evidence { text: string; file: string | null; line: number | null; severity: Severity }
export interface Cited { text: string; cites: string[]; verified: boolean }
export interface Finding {
  id: string; kind: string; severity: Severity; title: string; nodes: string[]; evidence: Evidence[]; summary: string;
  explanation: string | null; verify_steps: string[]; hypotheses: Cited[]; state: "open" | "ack" | "dismissed";
  /** Depot paths behind the finding (null: unknown). */
  files: string[] | null;
}
/** A node's name for the workspace (review workspace §4.2): the reader sees names, never node ids. */
export interface NodeName { label: string; kind: string; path: string | null; line: number | null; story: string | null }
export type Names = Record<string, NodeName>;
export interface Neighbour extends NodeName { id: string; changed: boolean; test: boolean }
export interface Neighbours { node: Neighbour; callers: { total: number; items: Neighbour[] }; callees: { total: number; items: Neighbour[] } }
export interface PerCl { cl: number; before: string; after: string }
export interface FileChange { depot: string; local: string; action: string; before: string; after: string; base_rev: string | null; per_cl: PerCl[] }
export type AnchorKind = "line" | "function" | "finding" | "chapter" | "review" | "story" | "flow" | "file";
export interface Comment {
  id: number; review_id: number; parent_id: number | null; author: string; body: string;
  anchor_kind: AnchorKind; anchor: Record<string, unknown>; resolved: boolean; created_at: string; edited_at: string | null;
  ai_meta: AiMeta | null;
}
/** A tortoise reply's state (spec 2026-10-03 §5). */
export interface AiMeta { pending: boolean; round?: number; of?: number; read: string[]; files: string[]; calls: number; error: string | null }
export type AiKind = "flow" | "finding" | "file" | "story";
export interface AiJob { id: number; user: string; kind: string; target: string; status: "running" | "done" | "failed" | "refused"; error: string | null }
export interface AiCall { id: number; user: string; purpose: string; target: string | null; started_at: string; finished_at: string | null;
  prompt_tokens: number | null; completion_tokens: number | null; outcome: "ok" | "failed" | "refused" | "running" | null; error: string | null }
export interface FileSummary { summary: string; check: string[]; files: string[] | null; by: string; at: string }
export interface AiView {
  used: number; budget: number; by_person: Record<string, number>; by_purpose: Record<string, number>;
  llm: boolean; me_today: number; me_limit: number; per_mention: number; is_owner: boolean; jobs: AiJob[];
  file_summaries: Record<string, FileSummary>;
}
export interface HealthCheck { name: string; ok: boolean; hard: boolean; detail: string }
export interface Health { checks: HealthCheck[]; ready: boolean; index_generation: number; libclang: string | null; strip_flags: string[]; index_building: boolean;
  p4_sources: Record<string, string>;
  ai: { limits?: { per_review: number; per_person_daily: number; per_mention: number }; calls_today?: number } }

export type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
import type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail ?? msg; } catch { /* not json */ }
    throw new ApiError(res.status, typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json() as Promise<T>;
}

export const api = {
  me: () => call<Me>("GET", "/api/me"),
  login: (user: string, password: string) => call<{ user: string; is_owner: boolean }>("POST", "/api/login", { user, password }),
  logout: () => call("POST", "/api/logout"),
  health: () => call<Health>("GET", "/api/health"),
  rebuildIndex: () => call("POST", "/api/index/rebuild"),
  reviews: () => call<ReviewRow[]>("GET", "/api/reviews"),
  createReview: (cls: number[], title?: string) => call<ReviewRow>("POST", "/api/reviews", { cls, title }),
  review: (id: number) => call<ReviewDetail>("GET", `/api/reviews/${id}`),
  rerun: (id: number) => call("POST", `/api/reviews/${id}/rerun`),
  board: (id: number, cluster?: string | null) =>
    call<Board>("GET", `/api/reviews/${id}/board${cluster ? `?${new URLSearchParams({ cluster })}` : ""}`),
  overview: (id: number) => call<Overview>("GET", `/api/reviews/${id}/overview`),
  stories: (id: number) => call<StorySet>("GET", `/api/reviews/${id}/stories`),
  story: (id: number, sid: string) => call<StoryDetail>("GET", `/api/reviews/${id}/stories/${sid}`),
  locate: (id: number, q: { node?: string; flow?: string; finding?: string }) =>
    call<{ cluster: string | null; story?: string | null }>("GET", `/api/reviews/${id}/locate?${new URLSearchParams(q)}`),
  source: (id: number, path: string, side: "before" | "after" = "after") =>
    call<SourceText>("GET", `/api/reviews/${id}/source?${new URLSearchParams({ path, side })}`),
  names: (id: number) => call<Names>("GET", `/api/reviews/${id}/names`),
  /** At most `limit` callers and callees, or `more.callers`/`more.callees` of that side. */
  neighbours: (id: number, nid: string, limit = 20, more: { callers?: number; callees?: number } = {}) =>
    call<Neighbours>("GET", `/api/reviews/${id}/nodes/${encodeURIComponent(nid)}/neighbours?${new URLSearchParams({
      limit: String(limit), ...Object.fromEntries(Object.entries(more).map(([k, v]) => [k, String(v)])) })}`),
  findings: (id: number) => call<Finding[]>("GET", `/api/reviews/${id}/findings`),
  setFindingState: (id: number, fid: string, state: Finding["state"]) =>
    call("PATCH", `/api/reviews/${id}/findings/${fid}`, { state }),
  files: (id: number) => call<FileChange[]>("GET", `/api/reviews/${id}/files`),
  comments: (id: number) => call<Comment[]>("GET", `/api/reviews/${id}/comments`),
  addComment: (id: number, body: string, anchor_kind: AnchorKind, anchor: Record<string, unknown>, parent_id?: number) =>
    call<Comment>("POST", `/api/reviews/${id}/comments`, { body, anchor_kind, anchor, parent_id }),
  patchComment: (cid: number, patch: { body?: string; resolved?: boolean }) => call<Comment>("PATCH", `/api/comments/${cid}`, patch),
  deleteComment: (cid: number) => call("DELETE", `/api/comments/${cid}`),
  swarmRefresh: (id: number, cl: number) => call<SwarmInfo | null>("POST", `/api/reviews/${id}/cls/${cl}/swarm/refresh`),
  swarmCreate: (id: number, cl: number) => call<SwarmInfo>("POST", `/api/reviews/${id}/cls/${cl}/swarm/create`),
  swarmPost: (id: number, cl: number, confirm_repeat = false) =>
    call<{ comment_id: string }>("POST", `/api/reviews/${id}/cls/${cl}/swarm/post`, { confirm_repeat }),
  ai: (id: number) => call<AiView>("GET", `/api/reviews/${id}/ai`),
  aiCalls: (id: number) => call<AiCall[]>("GET", `/api/reviews/${id}/ai/calls`),
  explain: (id: number, kind: AiKind, target: string) => call<AiJob>("POST", `/api/reviews/${id}/explain`, { kind, target }),
  raiseBudget: (id: number, budget: number) => call<{ budget: number }>("PUT", `/api/reviews/${id}/ai/budget`, { budget }),
  setRounds: (id: number, rounds: number) => call<{ rounds: number }>("PUT", `/api/reviews/${id}/ai/rounds`, { rounds }),
  renameLayer: (level: number, name: string) => call("PUT", `/api/layers/${level}`, { name }),
};
