/** Review board model, as served by GET /api/reviews/{id}/board (backend codetortoise/board.py). */
import type { StoryReading } from "../reading/types";
export interface NodeChange { kind: "modified" | "signature" | "added" | "removed"; add: number; rem: number }
export interface BoardNode {
  id: string; key: string; label: string; kind: "function" | "field" | "struct" | "more"; layer: number | null;
  path: string | null; local: string | null; range: [number, number] | null; change: NodeChange | null; x: number; warn: number;
  /** A visitor: the cluster this node belongs to (spec 2026-10-03-large-change-boards §3). */
  home?: string | null;
  /** Callers / callees not on the board, for "+N callers" (absent on boards stored before clusters). */
  more_callers?: number; more_callees?: number;
  /** A story graph's node (spec 2026-10-04-change-stories §3.1): what changed in it, in a few words. */
  note?: string | null;
  /** A story graph's struct node: the fields its story touches. */
  fields?: { id: string; label: string }[];
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
  /** The changed node the flow comes from. */
  cause?: string | null;
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

/** Change stories (spec 2026-10-04-change-stories), as served by GET /api/reviews/{id}/stories[/{sid}]. */
export type StoryKind = "behaviour" | "other" | "mechanical" | "tests" | "unsorted";
/** Why a piece is in its story (spec 2026-10-05-two-tier-stories §4.3): a reason word, the pieces and CLs it relies on,
 * quotes from CL descriptions; in the Unsorted story, `reason` is the check that failed. */
export interface Placement { piece: string; reason: string; evidence: string[]; quote: string[] }
export interface StoryPiece { id: string; kind: string; cl: number | null; files: string[]; names: string[] }
export interface Story {
  id: string; kind: StoryKind; title: string; summary: string; text_source: "template" | "llm"; risk: string | null;
  /** AI text: the files whose code was in its prompt (null: unknown). */
  text_files?: string[] | null;
  counts: Partial<Record<"flows" | "findings" | "functions" | "files" | "sites" | "test_sites", number>>;
  nodes: string[]; flows: string[]; findings: string[]; board: string | null;
  /** The changelists of the files holding its code (review workspace §4.1; [] for stories stored before them). */
  cls: number[];
  sub: [string, string] | null; subs: [string, string][]; collapsed: boolean;
  /** Two-tier stories (absent on stories stored before them): build targets, pieces and why each is here, and — when the
   * strong model formed it — what it is for, what to check, open questions and related stories' ids. */
  targets?: string[]; pieces?: string[]; placements?: Placement[]; purpose?: string; check?: string[]; questions?: string[];
  related?: string[]; source?: "tier1" | "rules";
}
export interface StoryRef { node: string; label: string; story: string | null }
export interface StoryFunction { node: string; label: string; note: string; on_flow: boolean; also: string[]; calls: StoryRef[] }
export interface StorySite {
  path: string | null; line: number; function: string | null; node: string | null; before: string; after: string;
  test: boolean; effect: string | null; other_edits: string | null;
}
export interface StoryDetail {
  story: Story; board: Board; graph: Board | null; functions: StoryFunction[]; sites: StorySite[]; also_in: StoryRef[];
  pieces?: StoryPiece[];
  /** The story's tiles (spec 2026-10-07-review-reading §6); null: run before the reading existed. */
  reading?: StoryReading | null;
}
export interface StorySet {
  summary: string; stories: Story[];
  node_story: Record<string, string>; flow_story: Record<string, string>; finding_story: Record<string, string>;
}
