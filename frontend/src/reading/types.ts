/** How a review reads (spec 2026-10-07-review-reading §10.1): the backend's reading.py models as the browser gets them. */

export type CheckKind = "hazard" | "confirm" | "caller" | "result" | "reader" | "target" | "untested" | "unanalysed" | "ask"
  | "cleared";
export type ConnKind = "caller" | "vocabulary" | "condition" | "place" | "bundled";

export interface Thread {
  id: string; name: string; purpose: string; text_source: "template" | "llm";
  /** In reading order. */
  stories: string[]; cls: number[]; open_checks: number;
  /** 3–5 sentences (spec 2026-10-09-review-introduction §3); absent on a reading stored before the introduction. */
  intro?: string; intro_source?: "template" | "llm";
  /** Its key files and directories, workspace-relative. */
  files?: string[]; modules?: string[]; files_source?: "template" | "llm";
}
/** One step of Where to start: a thread and why to read it then. */
export interface RouteStep { thread: string; reason: string; skim: boolean }
export interface Connection {
  a: string; b: string; kind: ConnKind; text: string; facts: string[]; shown: boolean;
  /** "llm": the strong model reworded `text`; absent on a reading stored before it, which reads as the rules' own. */
  text_source?: "template" | "llm";
}
export interface Check {
  /** kind|file|function|related changed function: no line numbers, so a mark survives a re-run. */
  key: string; kind: CheckKind; story: string | null; thread: string | null;
  /** Workspace-relative; `depot` is the file the side panel opens. */
  path: string; depot: string | null; line: number | null; function: string | null; node: string | null;
  text: string; source_line: string; finding: string | null; cites: string[];
  /** Its cause's id (spec 2026-10-16-outline-and-causes §4.1); null on a found-no-hazard row, absent before causes. */
  cause?: string | null;
  /** A reader row's field (the owner may mark it a shared sink). */
  field?: string | null;
  /** The changed function that raised it, a node id (spec 2026-10-25-review-ui-redesign §8): a flow's places are the
   * checks its `cause` raised at its landing. Absent on a reading stored before it, and null on a row with no changed
   * function behind it (a header target, an ask row, a finding without a function): either way it ties to no flow. */
  related?: string | null;
}
/** One changed line of a cause's change; `line` is in the after text ("+", " ") or the before text ("-"). */
export interface ChangeLine { sign: "+" | "-" | " "; text: string; line: number | null }
/** The 2–6 changed lines that raised a cause (spec 2026-10-16 §4.8). */
export interface CauseChange { path: string; depot: string | null; function: string | null; lines: ChangeLine[] }
/** One change and every place it asks the reviewer to look at (spec 2026-10-16 §4.1); `places` are check keys. */
export interface Cause {
  id: string; kind: CheckKind; thread: string | null; story: string | null; text: string; places: string[];
  /** Flow ids of its story that it touches. */
  flows: string[]; finding: string | null; change: CauseChange | null;
}
/** A shared sink the change writes (spec 2026-10-09 §5.1): hidden unless the viewer shows them. */
export interface SinkHit { field: string; label: string; users: number; why: "marked" | "listed" | "threshold"; writers: string[] }
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
  /** Later CLs replacing lines earlier ones added, and CLs outside the review in between (phase 2 §4.3). */
  rewrites?: Rewrite[]; gaps?: Gap[];
  /** Checks by cause, in reading order; null (the review's reading) or absent (a story's) on a reading stored before
   * causes. */
  causes?: Cause[] | null;
  /** Shared sinks the change writes; absent on a reading stored before them. */
  sinks?: SinkHit[];
  /** Every thread once, in the order to read them; absent on a reading stored before the introduction. */
  route?: RouteStep[]; route_source?: "template" | "llm";
}

export interface ContractRow {
  kind: "signature" | "returns" | "fields" | "repeated" | "body" | "declaration"; text: string; node: string | null;
  before: string; after: string;
  /** [start, end) of the part of `after` that differs. */
  mark: number[]; added: string[]; removed: string[]; nodes: string[];
}
export interface WhereFn { node: string; label: string; add: number; rem: number; cl: number | null; line: number | null }
export interface WhereDecl { name: string; line: number | null }
export interface WhereFile {
  path: string; depot: string | null; functions: WhereFn[];
  /** The story's CLs that edit the file, in order (phase 2 §5.3); absent on a reading stored before phase 2. */
  cls?: number[];
  /** A declarations-only story's changed declarations (types, prototypes, macros); absent on a reading stored before them. */
  decls?: WhereDecl[];
}
export interface CallPath {
  /** Node ids, entry first; `hidden` are the folded middle steps of a long path. */
  steps: string[]; labels: string[]; kind: "contract" | "state" | "call"; entry: string | null; hidden: string[];
  text: string; flow: string | null;
}
/** One section of a behaviour story's account (spec 2026-10-12-story-account-and-panels §1). */
export interface AccountPart { kind: "purpose" | "flow" | "effects"; heading: string; text: string; cites: string[] }

export interface StoryReading {
  story: string; contracts: ContractRow[]; where: WhereFile[]; paths: CallPath[]; checks: Check[];
  /** Its place in its thread: "Uses what story 1 adds." */
  place_text: string; thread: string | null; position: number | null;
  /** The order to read the story's CLs in, and the rewrites inside its code (phase 2 §4.4); absent before phase 2. */
  cl_order?: number[]; rewrites?: Rewrite[];
  /** Checks by cause, in reading order; null (the review's reading) or absent (a story's) on a reading stored before
   * causes. */
  causes?: Cause[] | null;
  /** The weak model's account, section by section (spec 2026-10-12 §1); absent or empty: the short text stands. */
  account?: AccountPart[]; account_files?: string[] | null;
}

/** Who wrote each line of a file several CLs edit (phase 2 §4.3); JSON keys of `rewritten` are strings. */
export interface FileLines {
  depot: string; local: string;
  /** Per line of the final text: the CL that wrote it, and the earlier CL whose lines it replaced. */
  wrote: (number | null)[]; over: (number | null)[];
  /** Per line of the base text: the CL that removed it. */
  removed: (number | null)[];
  /** rewritten[cl a][its after-text line] = the later CL that replaced it. */
  rewritten: Record<string, Record<string, number>>;
  replaced: [number, number, number, number | null][]; gaps: Gap[];
  /** Per replaced row: its final line, or the line just above a pure deletion (absent before it existed). */
  near?: (number | null)[];
}
/** A CL outside the review changed `file` between review CLs `after_cl` and `before_cl`; `same_base`: `before_cl` was
 * made against the base, not on top of `after_cl`. */
export interface Gap { file: string; after_cl: number; before_cl: number; same_base?: boolean }

/** CL `by` replaced or deleted `lines` lines CL `of` added to `file` (a depot path); `line` is the first final line in
 * their place and `function` the function holding it. */
export interface Rewrite { by: number; of: number; file: string; function: string | null; lines: number; line: number | null }
