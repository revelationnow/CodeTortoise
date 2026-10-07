/** How a review reads (spec 2026-10-07-review-reading §10.1): the backend's reading.py models as the browser gets them. */

export type CheckKind = "hazard" | "confirm" | "caller" | "result" | "reader" | "target" | "untested" | "unanalysed" | "ask"
  | "cleared";
export type ConnKind = "caller" | "vocabulary" | "condition" | "place" | "bundled";

export interface Thread {
  id: string; name: string; purpose: string; text_source: "template" | "llm";
  /** In reading order. */
  stories: string[]; cls: number[]; open_checks: number;
}
export interface Connection { a: string; b: string; kind: ConnKind; text: string; facts: string[]; shown: boolean }
export interface Reason { kind: CheckKind; text: string }
export interface Check {
  /** kind|file|function|related changed function: no line numbers, so a mark survives a re-run. */
  key: string; kind: CheckKind; story: string | null; thread: string | null;
  /** Workspace-relative; `depot` is the file the side panel opens. */
  path: string; depot: string | null; line: number | null; function: string | null; node: string | null;
  text: string; source_line: string; finding: string | null; cites: string[];
  /** Other kinds at the same place. */
  also: Reason[];
}
/** "Looks fine", shared by everyone viewing the review; `changed`: the line is no longer the one marked, so it is open. */
export interface Mark { key: string; user: string; at: string; source_line: string; changed: boolean }
export interface Headline { text: string; tone: "hazard" | "confirm" | "none"; rules_only: boolean }
export interface BuildImpact { header: string; text: string; files: number; finding: string | null; note: string }
export interface TestsRow { stories: string[]; functions: number; covers: string[]; untested: string[] }
export interface Reading {
  whole: string; whole_source: "template" | "llm"; threads: Thread[]; connections: Connection[];
  /** Story ids, tests last. */
  order: string[]; reasons: Record<string, string>; checks: Check[];
  /** Findings judged no hazard, with their reasons. */
  cleared: Check[]; build_impact: BuildImpact[]; coverage: string[]; headline: Headline; rules_only: boolean;
  tests: TestsRow | null; marks: Record<string, Mark>;
}

export interface ContractRow {
  kind: "signature" | "returns" | "fields" | "repeated" | "body"; text: string; node: string | null;
  before: string; after: string;
  /** [start, end) of the part of `after` that differs. */
  mark: number[]; added: string[]; removed: string[]; nodes: string[];
}
export interface WhereFn { node: string; label: string; add: number; rem: number; cl: number | null; line: number | null }
export interface WhereFile { path: string; depot: string | null; functions: WhereFn[] }
export interface CallPath {
  /** Node ids, entry first; `hidden` are the folded middle steps of a long path. */
  steps: string[]; labels: string[]; kind: "contract" | "state" | "call"; entry: string | null; hidden: string[];
  text: string; flow: string | null;
}
export interface StoryReading {
  story: string; contracts: ContractRow[]; where: WhereFile[]; paths: CallPath[]; checks: Check[];
  /** Its place in its thread: "Uses what story 1 adds." */
  place_text: string; thread: string | null; position: number | null;
}
