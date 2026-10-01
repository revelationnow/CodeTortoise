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

export interface Node {
  id: string; key: string; kind: "function" | "field"; label: string; file: string | null; line: number | null;
  status: "added" | "removed" | "changed" | "unchanged"; layer: number | null; confidence: "precise" | "heuristic";
}
export interface Edge {
  id: string; src: string; dst: string; kind: "call" | "virtual" | "writes" | "reads";
  status: "added" | "removed" | "unchanged"; confidence: "precise" | "may" | "heuristic"; file: string | null; line: number | null;
}
export interface Flow { root: string; nodes: string[]; edges: string[] }
export interface BlastItem { node: string; hop: number; score: number; via: "call" | "data"; path: string[] }
export interface FanOut { header: string; total_tus: number; by_layer: Record<string, number> }
export interface Impact { nodes: Record<string, Node>; edges: Edge[]; changed: string[]; flows: Flow[]; blast: BlastItem[]; fanout: FanOut[] }

export interface Evidence { text: string; file: string | null; line: number | null; severity: Severity }
export interface Cited { text: string; cites: string[]; verified: boolean }
export interface Finding {
  id: string; kind: string; severity: Severity; title: string; nodes: string[]; evidence: Evidence[]; summary: string;
  explanation: string | null; verify_steps: string[]; hypotheses: Cited[]; state: "open" | "ack" | "dismissed";
}
export interface Chapter {
  level: number | null; name: string; narrative: string; cites: string[]; verified: boolean;
  cross_layer_effects: Cited[]; nodes: string[]; findings: string[];
}
export interface Storyboard {
  summary: string; risk: "low" | "medium" | "high"; review_order: string[]; verified: boolean;
  chapters: Chapter[]; llm_used: boolean; llm_error: string | null;
}
export interface Drift { depot: string; local: string; expected: string; actual: string }
export interface StoryboardResponse { storyboard: Storyboard | null; drift: Drift[] }
export interface PerCl { cl: number; before: string; after: string }
export interface FileChange { depot: string; local: string; action: string; before: string; after: string; base_rev: string | null; per_cl: PerCl[] }
export type AnchorKind = "line" | "function" | "finding" | "chapter" | "review";
export interface Comment {
  id: number; review_id: number; parent_id: number | null; author: string; body: string;
  anchor_kind: AnchorKind; anchor: Record<string, unknown>; resolved: boolean; created_at: string; edited_at: string | null;
}
export interface HealthCheck { name: string; ok: boolean; hard: boolean; detail: string }
export interface Health { checks: HealthCheck[]; ready: boolean; index_generation: number; libclang: string | null; strip_flags: string[]; index_building: boolean }

export type { Board, SourceText } from "./board/types";
import type { Board, SourceText } from "./board/types";

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
  storyboard: (id: number) => call<StoryboardResponse>("GET", `/api/reviews/${id}/storyboard`),
  impact: (id: number) => call<Impact | null>("GET", `/api/reviews/${id}/impact`),
  board: (id: number) => call<Board>("GET", `/api/reviews/${id}/board`),
  source: (id: number, path: string, side: "before" | "after" = "after") =>
    call<SourceText>("GET", `/api/reviews/${id}/source?${new URLSearchParams({ path, side })}`),
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
  renameLayer: (level: number, name: string) => call("PUT", `/api/layers/${level}`, { name }),
};
