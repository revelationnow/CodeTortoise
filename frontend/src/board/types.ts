/** Review board model, as served by GET /api/reviews/{id}/board (backend codetortoise/board.py). */
export interface NodeChange { kind: "modified" | "signature" | "added" | "removed"; add: number; rem: number }
export interface BoardNode {
  id: string; key: string; label: string; kind: "function" | "field"; layer: number | null;
  path: string | null; local: string | null; range: [number, number] | null; change: NodeChange | null; x: number; warn: number;
  /** A visitor: the cluster this node belongs to (spec 2026-10-03-large-change-boards §3). */
  home?: string | null;
  /** Callers / callees not on the board, for "+N callers" (absent on boards stored before clusters). */
  more_callers?: number; more_callees?: number;
}
export interface BoardEdge {
  src: string; dst: string; kind: "call" | "virtual" | "writes" | "reads"; status: string; confidence: string;
}
export interface Annotation {
  node: string; path: string | null; line: number; side: "new" | "old"; severity: "warn" | "info" | "ok";
  channel: "contract" | "state" | "signature"; title: string; text: string; finding: string | null;
  cause: string | null; landing: boolean;
}
export interface BoardFlow {
  id: string; path: string[]; tag: "state" | "contract"; lands: string; fx_at: string | null; severity: string;
  findings: string[]; text: string; title: string; what: string; effect: string; check: string;
  what_source: "template" | "llm";
}
export interface AboutFile { path: string; name: string; action: string; cls: number[]; add: number; rem: number }
export interface About {
  intent: string; intent_source: "template" | "llm";
  why: { severity: string; text: string; finding: string }[];
  cls: { cl: number; user: string; description: string; file_count: number }[];
  tree: { dir: string; files: AboutFile[] }[];
  drift: { text: string; kind?: "ahead" | "behind" | "missing" | "unknown"; severity?: "warn" | "info" }[];
}
export interface Board {
  nodes: BoardNode[]; edges: BoardEdge[]; flows: BoardFlow[]; impacts: Annotation[];
  layers: { level: number; name: string }[]; about: About; hidden_nodes: number;
  /** A cluster's board in a split review. */
  cluster?: { id: string; name: string } | null;
}
/** A split review's overview, as served by GET /api/reviews/{id}/overview. */
export interface ClusterInfo {
  id: string; name: string; level: number | null; also: number[]; risk: string | null; test: boolean; files: string[];
  changed: number; flows: number; findings: number; finding_ids: string[]; nodes: string[];
}
export interface ClusterLink { src: string; dst: string; calls: number; fields: number }
export interface Overview {
  about: About; clusters: ClusterInfo[]; links: ClusterLink[]; layers: { level: number; name: string }[];
  totals: { files: number; clusters: number; flows: number; findings: number; changed: number };
  merged_over_limit: number;
}
export interface SourceText { path: string; depot: string; rev: string; text: string; changed: boolean }
