# CodeTortoise — Review Board Design Spec (M1.5)

Date: 2026-10-01
Status: Draft for review
Builds on: `docs/superpowers/specs/2026-09-29-codetortoise-design.md` (M1; §14–15 record later decisions)
Visual reference: `docs/design/board-prototype.html` (interactive prototype v14 — open it in a browser; it is the source of truth
for look and interaction)

## 1. Purpose

M1 presents a review as separate tabs (Storyboard, Call flows, Blast radius, Findings, Files, CLs). In use this felt
disconnected: the call graph, the code, the side effects and the discussion lived in different places. The Review Board
makes the change a single, zoomable, literal board:

- a layered map of the functions involved, with the changed ones impossible to miss;
- an enumerated list of **call flows** — *entry → change → where the side effect lands* — each with a plain-language summary;
- code (diffs for changed functions, the relevant lines for others) opening in place, annotated with how each function
  is impacted, with inline comments;
- a multi-file viewer and a "What's this change?" panel beside the board, never replacing it.

The blast radius becomes **impact annotations** on each affected function; no separate blast-radius view.

### Success criteria

- On the uart fixture (CLs 101+102) the board shows exactly the three flows of the prototype, with the annotations of §5.3.
- On the libgit2 lab (planted CLs 28+29, 30) the board shows flows and annotations for every planted side effect.
- Every interaction in the prototype works in the product, on desktop and on a phone, with the prototype's state rules (§4.3).
- A review with an LLM configured finishes several times faster than M1 on the same local model (parallel LLM calls).

### Non-goals (this milestone)

Server-side saved layouts; a separate blast-radius view; flows for header fan-out; M2 detectors (shared state,
concurrency, ABI/virtual); real-time multi-user cursors.

## 2. Page structure

The review page (`/r/:id`) becomes:

- **Header** — title, risk pill, CL pills, counts (flows, findings), `✦ What's this change?` button. Secondary tabs
  `Findings`, `Files`, `CLs & Swarm` (unchanged M1 components) are reachable from the header; the Board is the default.
  The M1 `Storyboard`, `Call flows` and `Blast radius` tabs are removed.
- **Flow bar** — numbered flow chips (path text + tag `STATE|CONTRACT`; signature flows are `CONTRACT`), and below them the **flow summary**:
  what the flow does, its steps as chips (changed = amber, field = teal, landing = coral; tap toggles that function's card,
  a small ⤢ badge opens it in the viewer), step/layer counts, and a "Side effect lands on …" box with the effect and
  what to check. In *Whole graph* mode the summary shows graph totals and the drag hint instead.
- **Main row** (flex): `Board canvas | File viewer (optional) | Change panel (optional)`. Viewer and change panel push the
  canvas; both are resizable by dragging their left edge. Below 1100 px they become full-screen sheets (viewer above panel).

## 3. The canvas

### 3.1 Lens (pure functions, `lens.ts`)

Coordinates: nodes have world `x` (per-viewer adjustable) and a layer index; world `y = layer * BAND + BAND/2`
(`BAND = 210`). The canvas focus is its visible centre; when the visible width/height changes (panels open/close/resize),
pan is adjusted by half the delta so the focused world point stays centred.

- **Horizontal:** within `FLAT = 0.55` of the half-width around the focus, 1:1. Beyond it, each side folds in the content on
  *that* side: `Rw = max(sideExtent − F, R · FOLD[lens])`, `k = Rw/R − 1`, `g(t) = (k+1)t/(kt+1)` for `t = (|w|−F)/Rw`
  clamped to 1 — slope 1 at the seam (no kink). `FOLD = {2: 1.8, 4: 3.4}`; lens `0` = off.
  Local scale `1/(kt+1)²`, floor 0.34.
- **Vertical:** none inside the flat zone (layers parallel, sizes constant when panning up/down); beyond it, `y` is pulled
  towards the canvas centre line by `vSqueeze(nd)` (smoothstep from 1 at `nd = FLAT` to `vmin` at the rim;
  `vmin = 0.7` for 2×, `0.55` for 4×). Layers converge without meeting.
- **Node scale** = `max(0.36, min(1, kx) · (0.45 + 0.55 v))`.
- `unprojectX(screenX)` inverts the horizontal mapping by bisection (monotonic) — used for dragging nodes.
- Bands are drawn as SVG paths sampled every 16 px; layer labels sit at the right edge.

### 3.2 Nodes

- Changed function: amber gradient tile, thick border, slow pulse, micro-label `Δ MODIFIED|ADDED|REMOVED|SIGNATURE`, `+a −d`.
- Context function: white tile; red count dot = number of `warn` impact annotations.
- Field: teal tag shape.
- Side-effect badge (coral) under landing nodes: shown for the selected flow's landing; all shown in Whole graph mode.
- Every node with code has a ⤢ button (bottom-right; always visible on changed nodes and nodes with open cards,
  on hover otherwise) → opens its file in the viewer, scrolled to the function, line marked.
- Drag a node (> 6 px) → moves it horizontally within its layer (both modes); ↔ marker on moved nodes; `Reset layout`.

### 3.3 Modes, flows, edges

- `Flows` (default): selected flow's path glows; off-path, unchanged nodes dim; call edges not on the path dim; data edges
  (teal dashed) and effect edges (coral dashed) always visible.
- `Whole graph`: nothing dims; re-centres on the whole graph. Selecting a flow chip returns to `Flows` and centres on it.

### 3.4 Cards (floating code)

- Changed function card: header (name, path, `Δ changed`, `⤢ Full file`, ✕), effects strip, function-scoped diff (unified),
  inline annotations under their lines, comment threads, `＋ comment` on hover of any line.
- Context card: header (`context` / `field`), a "fetched on demand · `p4 print …`" line naming what it touches,
  the function's lines only, inline annotations, comments.
- Placement: next to the node (right, left, above variants, then canvas corners; least overlap wins), scaled by the lens at
  the node (floor 0.55), dotted tether line to its node; the front card and its node get a dark outline.
- Drag by header → card keeps that offset from its node while panning; double-click header → back to automatic placement.
- Phone (≤ 640 px): cards are bottom sheets.

### 3.5 File viewer

Stacked collapsible sections, newest on top; per-section ✕; header toggle collapses; global `Stacked | Side by side`,
`Expand all`, `Collapse all`, `Close all`; side-by-side rows aligned with wrapping; reopening a file moves it to the top,
expands and flashes it; opening with a line scrolls to it and marks it. Full-file annotations and comments render as in cards.
Unchanged files open without diff controls.

### 3.6 Change panel ("What's this change?")

Resizable right panel; stays open while files are opened from it. Order: **Files in this change** (collapsible directory tree,
action, CL, `+a −d`, open files highlighted; click → viewer) · **Intent** · **Why it's high risk** (top 4 findings) ·
**Changelists** (number, author, file count, description).

### 3.7 Interaction rules

- Dragging the canvas or a node never selects text (selection disabled during drags; existing selection cleared).
- Clicking a node opens its card or brings it to the front; it never closes it. ✕ (or `Close all cards`, shown with ≥ 2
  cards) is the only way to close a card. Flow-summary step chips toggle (open ↔ close).
- Opening the viewer collapses every card to a pill under its node (snapshot kept); closing the viewer restores the
  snapshot exactly. Clicking a pill expands that card.

## 4. Frontend architecture

### 4.1 Components (`frontend/src/board/`)

`Board.tsx` (page composition, data loading) · `lens.ts` (§3.1, pure) · `layout.ts` (barycentre fallback + world x helpers,
pure) · `reducer.ts` (§4.3, pure) · `Canvas.tsx` (bands, edges, nodes, tethers; pointer handling) · `CardLayer.tsx` ·
`FileViewer.tsx` · `ChangePanel.tsx` · `FlowBar.tsx` · `CodeView.tsx` (shared: diff rows unified/side-by-side, plain source,
annotations, comment threads; reuses `diffRows`) · `highlight.ts` (C/C++ token highlighter from the prototype) ·
`resizer.ts` (panel edge drag). Custom DOM + SVG rendering (no Cytoscape on the board — the lens must apply uniformly to
bands, nodes, edges and cards). Cytoscape stays only if a remaining tab still needs it (none planned).

### 4.2 Data loading

`GET /api/reviews/{id}/board` (one blob, §5) on mount after the review is terminal; comments via the existing endpoints;
source for context cards / unchanged files via `GET /api/reviews/{id}/source` (§5.4), cached in memory per session.

### 4.3 State (single `useReducer`)

```
cards:   Map<nodeId, { collapsed: boolean, offset?: {x,y} }>
z:       nodeId[]                                // stacking, last = front
viewer:  { files: path[] (newest first), collapsed: Set<path>, mode: 'unified'|'split', snapshot?: Map<nodeId, collapsed> }
view:    { panX, panY, lens: 0|2|4 }
mode:    'flows'|'graph';  flow: number;  about: boolean;  moved: Map<nodeId, worldX>
```

Actions (each a pure transition, unit-tested): `card.open`, `card.front`, `card.expand`, `card.move`, `card.unpin`,
`card.close`, `card.closeAll`, `viewer.open{path,line?}`, `viewer.toggle`, `viewer.expandAll`, `viewer.collapseAll`,
`viewer.mode`, `viewer.close`, `viewer.closeAll`, `flow`, `mode`, `lens`, `node.move`, `layout.reset`, `about.toggle`,
`pan`. Rules of §3.7 are properties of this reducer.

### 4.4 Per-viewer preferences

`localStorage` (wrapped in try/catch; absence is fine): `ct.board.<reviewId>.moved`, `ct.panel.viewerW`, `ct.panel.aboutW`,
`ct.lens`. Nothing about layout goes to the server.

### 4.5 Comments

Line anchors become `{path, side: 'old'|'new', line}` (path = depot path) everywhere (cards, viewer, Files tab); the
M1 `line` anchor shape `{depot, cl, side, line}` stays readable (`cl` optional). Function anchors `{key}` unchanged.

## 5. Backend

### 5.1 Pipeline

New stage `board` after `detectors`, before `llm`: builds and stores the `board` blob (§5.2). The `llm` stage additionally
fills flow narratives (§5.5) and re-stores the blob. `finalize` unchanged. Stage deps: `board` ← `impact`, `detectors`.

### 5.2 Board model (`codetortoise/board.py`)

```
BoardNode  { id, key, label, kind: function|field, layer: int|null, path: str|null (depot), local: str|null,
             range: [start,end]|null (new-side lines; old-side for removed), change: {kind, add, del}|null,
             x: float (initial world x), warn: int }
BoardEdge  { src, dst, kind: call|virtual|writes|reads, status, confidence }
Flow       { id, path: [nodeId], tag: state|contract, lands: nodeId, fx_at: nodeId|null, severity,
             findings: [id], text (path label), what (html-safe plain text with node labels), effect, check,
             what_source: template|llm }
Impact     { node, path, line, side: new|old, severity: warn|info|ok, channel: contract|state|signature,
             title, text, finding: id|null }
Board      { nodes, edges, flows, impacts, layers: [{level, name}], about: {intent, why: [{severity, text, finding}],
             cls: [{cl, user, description, files}], tree: [{dir, files: [{path, action, cls, add, del}]}]} }
```

**Node selection:** changed functions ∪ nodes on any flow ∪ top 60 blast items ∪ fields written/read by changed functions,
capped at 150 nodes (lowest-score blast items dropped first). Edges: those of the impact model among selected nodes.

**Initial x:** per layer, order by 4 barycentre sweeps (down, up, down, up) over call/data edges, then space by 220 world px,
centred on 0; fields sit in the layer of their record's header module (or their writer's layer if unknown).

### 5.3 Impact annotations

Built from facts + findings (deterministic):

| Channel | Where | Text (template) | Severity |
|---|---|---|---|
| contract | each caller's call line of a function with new return values | ignores result → "result ignored — `f` can now return V"; `==`-only miss → "checks X — does not handle V"; covered → "checks X — covers V" | warn / warn / ok |
| signature | each caller's call line | "calls `f`, whose signature changed: `old` → `new`" | warn (precise) / info (heuristic) |
| state | each *other* function's read/write line of a field a changed function newly writes | "reads/writes `R::f` — now also written by `g` (line n)" | warn |
| state | field declaration line (header) | "new writer `g` · readers: a, b" | warn |
| on the changed function | its new write lines and new return lines | "writes `R::f` through alias `v`"; "new return value V" | warn |

Requires two fact additions: `Function.return_lines: {value: line}` and `FieldAccess.decl_line` (FieldDecl line in
`record_file`). Node `warn` = count of `warn` impacts on that node.

### 5.4 Source on demand

`GET /api/reviews/{rid}/source?path=<depot path>&side=before|after` →
`{path, depot, rev, text, changed}`:

- If `path` is in the change set → its before/after text.
- Else → `Source.read(depot)`: `P4Source` runs `p4 fstat` (have rev) + `p4 print -q depot#have`; `GitFixtureSource`
  reads the workspace file. Result cached in the review's blobs as `source:<depot>`.
- Allowed only for depot paths that map into the workspace (`p4 where` / `canon()` under `workspace.root`); anything else
  → 403. Binary files → 415. Size cap 2 MB → 413.
- `Source` protocol gains `read(depot: str) -> SourceFile{depot, local, rev, text}`.

### 5.5 Flows

1. **Landings** from findings: contract (caller that ignores/mishandles → landing = caller, `fx_at` = caller);
   field mutation (other function reading/writing the field → landing = reader; path goes through the field node);
   signature change (each caller → landing = caller). Header fan-out yields no flows.
2. **Path:** shortest reverse call path from the changed function to an **entry** (a node with no incoming call edges
   among board nodes, a match of `analysis.entrypoint_patterns`, or a node in the top layer); then forward to the landing
   (`contract`/`signature`: entry → … → landing → changed; `state`: entry → … → changed → field → landing).
3. De-duplicate by (changed, landing); rank by severity, then path length; cap `board.max_flows = 12`.
4. **Text:** `text` = `a → b → … ⟶ effect-summary`; `effect` and `check` from templates per channel; `what` from a template;
   the `llm` stage rewrites `what` for the top `llm.max_flow_narratives = 6` flows (grounded: must cite node/finding ids;
   uncited → keep template).

### 5.6 LLM concurrency

`llm.concurrency` (default 4) — finding explanations, chapter/flow narratives run on a thread pool; results merged in a
fixed order so output is deterministic given the same responses. Summary call runs last.

### 5.7 API

- `GET /api/reviews/{rid}/board` → Board (404 until the `board` stage has run).
- `GET /api/reviews/{rid}/source` (§5.4).
- Existing endpoints unchanged; `impact`/`storyboard` remain for the secondary tabs and Swarm summary.

## 6. Error handling

- Board stage failure → review degraded; the page falls back to the M1 tabs with a banner.
- Source fetch failure on a context card → card shows the error and a retry; board stays usable.
- LLM failures → flows keep template text (`what_source: template`).
- Large graphs → node cap (§5.2) with a "+N more functions not shown" note in the Whole graph summary.

## 7. Testing

- **Backend (pytest):** board golden on the uart fixture — exactly the three prototype flows and the §1 annotations
  (`service/logger.c:21` warn, `service/logger.c:12` ok, `driver/uart.c:29` warn, `driver/uart.h:15` warn,
  `driver/uart.c:17`/`:18` on the changed function); barycentre ordering has no crossings on the fixture; node cap;
  `/source` changed/unchanged/outside-workspace (403)/binary/size; `P4Source.read` via the fake runner; LLM concurrency
  (N parallel calls observed), grounded flow narratives, cap respected.
- **Frontend (vitest):** lens (flat-zone identity, symmetry, monotonicity, unproject∘project ≈ id, vertical squeeze);
  reducer (every §3.7 transition, snapshot/restore); layout helper; CodeView annotation/thread placement.
- **E2E (Playwright, desktop + phone):** select a flow; toggle a step's card; ⤢ from a node opens the viewer at the
  function; stack two files, collapse/expand all; comment on a line in a card; resize the change panel; drag a node in
  Whole graph and reset; no text selected after dragging across a card.
- **Lab:** `lab/README.md` gains a check of the board blob for planted CLs 28+29 and 30 (expected flows/impacts listed).

## 8. Decisions from validation (fixture + libgit2 lab)

The implementation plan was built and run end to end before it was written down (uart fixture, then the libgit2 lab's
planted CLs 30 and 28+29). These decisions refine §3–§7; where they differ, this section wins.

**Model**
- Change counts are `{kind, add, rem}` (`del` is a Python keyword); `AboutFile` likewise.
- `Impact` gains `cause` (the changed node it comes from) and `landing` (a flow may land here: an ignoring or
  mishandling caller, a field reader, a signature caller).
- Depot paths are resolved once per board, only for the files of shown nodes and annotations, through
  `BoardContext.depots_for(locals) -> {local: depot}`. The pipeline never sends paths outside the workspace root
  (system headers made `p4 where` fail the whole batch in the lab); a failed lookup degrades the `board` stage and leaves
  context nodes without a depot path; changed files always keep theirs.

**State annotations (§5.3)**
- One annotation per (function, line): a line that reads and writes the field says "reads and writes `R::f`".
- Only readers are landings; pure co-writers are annotated but get no flow.
- Field declaration text: "new writer: `g` · readers: a, b · other writers: c"; with no readers or writers it is `info`.

**Flows (§5.5)**
- De-duplicate by (changed, landing, `state`|`contract`): one function can be both a contract and a state landing.
- Test code (`tests/`, `test/`, `testing/`, `fuzzers/` in the path) is never walked as a caller, never an entry, never
  a blast node on the board. A state flow's walk to an entry never passes through its own landing.
- Among equally short entry paths, prefer callers with fewer warnings (the fixture's state flow goes through
  `logger_write`, not `logger_flush`, which is the contract landing).
- When the entry is the node itself, the text starts with it: "`g` now writes …" / "`h` (layer) calls `g` and …".

**Change panel**: the tree strips everything above the deepest directory the changed files share, so a one-directory
change shows that directory (not ".").

**`/source`**: changed files return `rev` = the base revision for `before` and `changed` for `after`.

**LLM (§5.6)**: one thread pool runs finding explanations, chapter narratives and flow narratives; results apply in
submission order; the first failure stops applying (earlier results stay) and skips the summary. The summary also sets
`about.intent` (`intent_source: llm`).

**Frontend**
- Reducer state uses plain records/arrays (not Map/Set). Extra actions: `card.toggle` (step chips), `card.move` carries
  the offset from the node, `viewer.open` carries `wide` (first-open mode), and `viewer.reveal {path, line, seq}` drives
  scroll-and-flash. Backend x is always set, so there is no frontend barycentre fallback.
- Extra modules: `codeRows.ts` (pure line/annotation/thread placement, unit-tested), `useSources.ts` (session cache for
  `/source`), `Resizer.tsx`, `lib/anchors.ts` (line anchors, M1 shape still matched).
- Every board class is `bd-` prefixed or nested under `.bd`: M1's global `.graph`/`.side`/`.card` rules otherwise leak in.
- The board keeps its light palette in dark mode. On phones the flow summary collapses to its steps (a `Details`
  toggle shows the text and the landing box) and the header hides the CL/count pills, so the canvas keeps its space.

## 9. Call-depth layout and free node moves (2026-10-01)

- **Layout switch** `Layers | Call depth` in the canvas toolbar, remembered per review (`ct.board.<id>.layout`). With no
  saved choice the board opens in Call depth when the layers say little: one layer, or one layer holding ≥ 70% of the
  nodes.
- **Call depth** (computed in the browser from the board's edges): row = distance from the entry points (functions with
  no caller on the board) along call edges; nodes reachable only through cycles start from the changed functions; a
  field sits one row below its deepest writer (reader if nothing writes it). Rows are `BAND` apart and labelled
  `depth 0 · entry`, `depth N`; within a row, barycentre sweeps order the nodes and labels are packed by estimated width
  (40 px gaps, at least 220 apart).
- **Moves are 2-D in both layouts** (`lens.unprojectY` inverts the vertical squeeze at the node's screen x; the grab point
  stays under the pointer). In Layers a node may leave its band; the band does not change. Moves are kept per layout
  (`ct.board.<id>.moved = {layers, depth}`; the earlier x-only shape loads as Layers moves); `Reset layout` resets the
  current layout only.
- `GET /board` re-validates the stored blob through the `Board` model, so boards stored by an older version get the
  current defaults instead of breaking the page.

## 10. Panels: change panel on the left, resizable flow bar (2026-10-01)

- The change panel ("What this change is trying to do") sits left of the canvas and is open by default on screens wider
  than 1100 px. Its toggle is at its top-left; collapsed, it is a 36 px bar with the toggle and a vertical
  "What's this change?" label (the whole bar opens it). Below 1100 px it starts collapsed and opens as the full-screen
  sheet. The viewer's choice is remembered (`ct.panel.about`) and wins over the default. Its resize grip is on its right
  edge. The header no longer carries a "What's this change?" button.
- The flow bar has a bottom-edge grip: height from the chips row up to half the window (`ct.panel.flowH`); the flow
  summary scrolls inside a shorter bar; double-click the grip returns to automatic height.
