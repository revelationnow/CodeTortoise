# Review Workspace: One Place to Read a Review — Design

Date: 2026-10-04. Status: draft for review. Step 6 of the production-readiness work; follows change stories
(`2026-10-04-change-stories-design.md`).

## 1. Why

A review today is four tabs that do not know about each other: Stories, Boards, Findings, and CLs & Swarm. Using the
lab review of libgit2 #6896, the owner found:

- **Nowhere to stand.** No page says where the reader is or how to go up a level; the browser's back button is the
  only way out of a story or a finding. Switching tabs and coming back starts the tab over. On a phone it is worse.
- **Disconnected tabs.** A finding has no link to its story or board; the CLs tab links to nothing; the boards never
  mention stories.
- **Raw ids.** `N4279` appears in finding text, cite chips and even an AI-written story title.
- **Stories layout.** Text bunched to one side; the flow ‹ › buttons move with the width of each title; the
  Steps/Graph switch is hard to find; the graph's flow bar runs off the right edge, hiding the other flows.
- **Boards interactions.** Clicking a file refilters the graph to a near-complete graph of its directory; clicking a
  node again does not close its code; "+N callers" grows the board in place and cannot be undone except by Reset; the
  change panel shows the file tree before what the change does and why it is risky.
- **Findings.** No AI analysis until someone asks, even for high-risk findings; code shown as a bare list; links
  without labels; some names open a diff, others a graph with no sign of where the reader is.
- **CLs & Swarm.** A plain table, linked to nothing.

The stories carry the right information; the problem is the frame around them. This step replaces the four tabs with
one workspace: a rail that lists everything in the review, derived visibly from its changelists; a centre that shows
the item picked; and a detail panel for code that opens on demand.

## 2. The workspace

### 2.1 Layout

- **Desktop (over 1100 px).** A thin header (logo, review title, risk, status, AI pill, Re-run, stage notes). Below
  it three columns: the **rail** (280 px, resizable, collapsible), the **centre**, and the **detail panel** when open
  (resizable, about 45% of the width by default). Text pages (Whole change, a story's Steps, a finding, a CL) are
  centred in the centre column at a readable maximum width (about 880 px); graphs use the whole centre.
- **Tablet (641–1100 px).** The rail becomes a drawer behind a ☰ button; the detail panel slides over the centre.
- **Phone (640 px and under).** Three levels. The rail is the home screen. An item opens as a page whose top bar
  names where it came from and what it is ("‹ Stories · S1 frame_pop writes…"). The detail panel opens as a
  full-screen sheet whose top bar names its item ("‹ S1 · frame_pop").

### 2.2 The rail

One scrolling column of collapsible sections, in this order:

1. **⌂ Whole change** — the review's home, with its risk.
2. **Change set** — each CL: number, author, first line of the description, file count. Clicking a CL opens its
   page. Its filter dot highlights the stories drawn from it and dims the rest; clicking the dot again clears it.
   The section title says how many CLs the stories come from ("Stories (from 2 CLs)" heads the next section).
3. **Stories** — the existing sections (what behaves differently, other changes, repeated edits, tests), as compact
   rows: risk pill, title, and a chip for each CL the story draws from (`[CL 2] [CL 3]`). Collapsed behaviour stories
   stay under "N more behaviour stories".
4. **Findings** — grouped by severity (high, medium, low, info); each row a severity dot, the title, and the handle
   of its story.
5. **Files** — the change's tree with +/− counts and CL tags. A file opens its diff in the detail panel and highlights
   that file's functions on the graph in the centre, if one is shown. It never refilters the graph.

The open item is highlighted wherever it appears. Section open/closed state, rail scroll position and rail width are
kept in the browser (per review for scroll, global for the rest).

### 2.3 Addresses

Every place has an address, so reload, shared links and the browser's back button work:

| Address | Centre |
|---|---|
| `/r/:id` | Whole change |
| `/r/:id/s/:sid` (`?view=graph` for the graph) | a story |
| `/r/:id/f/:fid` | a finding |
| `/r/:id/cl/:cl` | a changelist |
| `/r/:id/c/:cid` | a cluster's graph (split reviews) |

Parameters valid on any of them:

- `flow=<n>` — the selected flow, 1-based.
- `open=<node id>` or `open=file:<depot path>[:<line>]` — what the detail panel shows; absent means closed.
- `tab=diff|neighbours` — the detail panel's tab (default `diff`).

Ids appear only in addresses, never in visible text. The old addresses (`/r/:id/board`, `/r/:id/overview`,
`/r/:id/findings`, `/r/:id/cls`, `?node=`) redirect to their new places (`?node=N12` opens the item holding the node,
as `locate` does today, with `open=N12`).

### 2.4 Getting around

- **Up.** The centre header carries a breadcrumb, e.g. `Review 7 › Stories › S1 frame_pop writes… › Graph`; every
  part is a link.
- **Back.** Opening an item or opening the detail panel on something new pushes a history entry; switching flow,
  view or detail tab replaces the current one.
- **Returning to an item.** Each item remembers, for the session, its last view, flow and detail content. Clicking
  S1 in the rail after visiting a finding returns to S1's Graph at the same flow with the same node open.
- **Names, not ids.** Functions and fields show their names everywhere. Stories and findings show their titles first,
  with `S1`/`F2` as a small grey handle. Node ids in AI or template text (`N4279`) are shown as the node's name,
  linked to its code.
- **Labelled links.** Every link and icon button has an accessible name and a tooltip saying where it goes ("Open
  frame_pop's diff", "Go to story S1: frame_pop writes…", "Open CL 2").

## 3. The pages

### 3.1 Whole change (`/r/:id`)

Top to bottom:

1. **What this change is trying to do** — the intent (marked AI when the AI wrote it).
2. **Why it is risky** — the review's reasons, each linking to its finding.
3. **The summary line** — the stories' summary ("Mostly mechanical: 180 of 187 changed lines are 2 repeated edits").
4. **The map** — a split review's clusters in their layer bands with risk, counts and links (today's overview);
   clicking a cluster opens `/c/:cid`. A review shown as one board shows its graph here, with "Open full graph".
5. **Files with side effects** — each opens its diff at the affected line.
6. **Workspace drift** — only when present.
7. **Discussion** — review comments and layer threads.

### 3.2 Story (`/r/:id/s/:sid`)

- **Header**: risk, title, summary, counts, CL chips; a **Steps | Graph** switch, large and beside the title (behaviour
  and "Other changes" stories); `‹ S1 of 4 ›` in a fixed-width group; Explain.
- **Steps view**: the flow strip (§3.6); numbered steps — clicking one opens its diff in the detail panel and marks
  the step; where the side effect lands; other functions changed in the story; the story's findings, linking to their
  pages. Repeated-edit and tests stories keep their current bodies (sites by directory and file; tests by file),
  with their links moved to workspace addresses and their code opening in the detail panel.
- **Graph view**: the flow strip, the story's graph, and Layers / Call depth / Reset layout. Clicking a node opens its
  diff in the detail panel; clicking the same node again closes it. "+N callers / +N callees" on a node opens its
  Neighbours tab.

### 3.3 Finding (`/r/:id/f/:fid`)

- **Header**: severity, title, kind; state (open / acknowledged / dismissed; the owner can change it);
  `‹ F2 of 10 ›`.
- **Where it lives**: links to its story, to the graph centred on its first node (the story's graph, else the
  cluster's or the review's), and to the CLs of its files.
- **AI analysis** first: written in the review run for high-severity findings (§4.4); others offer Explain.
- **Evidence**: each line with a file and line opens the diff at that line.
- **Verify**, **possible side effects**, **comments**.

### 3.4 Changelist (`/r/:id/cl/:cl`)

- **Header**: CL number, author, status (pending or submitted), the description's first line as title and the rest
  below.
- **Swarm card**: the Swarm review link, state and votes; for the owner, buttons for Refresh, Create review (pending
  CLs without one) and Post summary link (with the existing "post again?" confirmation).
- **Files in this CL**: each opens its diff in the detail panel filtered to this CL.
- **Stories drawn from this CL** and **findings in its files**, as links.

### 3.5 Cluster (`/r/:id/c/:cid`)

Name, layer, risk, counts, `‹ ›` between clusters, the stories it holds, then its graph with the flow strip. Visitor
nodes keep their link to their own cluster.

### 3.6 The flow strip

Shared by the story Steps view, the story graph and cluster graphs. One row: fixed-width `‹` `flow 2 of 5` `›`, the
flow's tag, and its title truncated to the remaining width with the full title in a tooltip; a ▾ menu lists every flow
by title. Below it, the selected flow's text ("what", the steps in the graph views, where the side effect lands and
what to check), collapsible. The controls never move between flows and the strip never overflows sideways.

### 3.7 Detail panel

- **Header**: the node's or file's name, its file and lines, a changed / context / field badge, the story it belongs
  to (a link), and ✕.
- **Diff tab**: for a node, its code slice with its effects and function comments, and a switch to the full file
  with the CL picker; for a file, its whole diff (changes only or full file, CL picker, Summarise). Rendering is
  today's `CodeView`: split or unified, notes inline, line comments, folding.
- **Neighbours tab**: three columns — callers, the node, callees. Each row: name, file, a changed badge and a story
  chip. Clicking a row moves the panel to that node (a history entry, so Back returns). Columns show 20 rows with
  "Show all N". Test callers are listed after the others, marked "test".

## 4. Backend

### 4.1 Story CLs

`Story` gains `cls: list[int]`: the CLs of the files holding the story's nodes, sites or test functions (from the
change files' per-CL history, as `About.tree` files carry today), sorted. Computed in `build_stories`, stored with the
story; stories stored before this field load with `cls = []` and the UI shows no chips for them.

### 4.2 Name index

`GET /api/reviews/{rid}/names` returns `{ "<node id>": { "label", "kind", "path", "line", "story" } }` for every node
the UI can show: nodes on any stored board or story graph, finding nodes and evidence nodes, and nodes cited in flow,
story and finding text. `path` is the depot path (null when unknown), `story` the story holding the node (null when
none). Served from the stored impact model, node files and stories; no new blob.

### 4.3 Neighbours

`GET /api/reviews/{rid}/nodes/{nid}/neighbours?limit=20` returns `{ node, callers: {total, items}, callees: {total,
items} }`, where `node` and each item are `{ id, label, kind, path, line, changed, story, test }`. Callers and callees
come from the impact model's call and virtual edges, the most affected first (blast score), test code last. `limit`
caps `items`; `total` is the full count. 404 for an unknown node.

### 4.4 AI analysis of high-risk findings up front

`llm.upfront_findings` (default 5): the review run's AI pass also explains the first N findings of severity `high`,
in finding order, with the existing finding job, inside the review's AI budget (they count like any call). A finding
explained this way is shown exactly like one explained on demand.

### 4.5 No ids in AI titles

An AI story title (and a flow title) containing a node or finding id (`N\d+`, `F\d+`) is rejected by the style check,
keeping the template title, and counted as a style drop.

### 4.6 Removed

The board `expand` parameter and `expand_board` with its tests go (the Neighbours tab replaces growing the board),
together with the frontend's `useExpansion`, the `expand` address parameter and its saved preference.

## 5. Frontend elements

Each existing element was reviewed and given one decision.

**Kept as is**: `api.ts`, `board/types.ts`; the diff engine (`codeRows`, `fold`, `highlight`); the graph maths
(`lens`, `layout`, `zoom`, `overview.ts`); `drift`, `sideEffects`, `useSources`, `lib/anchors`, `lib/aiState`,
`lib/ai.tsx`, `board/phone/flowSteps`, `stories/stories.ts`; `CodeView`; `Comments`, `Explain`, `AiPill`, `Badges`,
`ThemeSwitch`, `Stages`, `Resizer`, `Logo`, `InsecureBanner`.

**Kept, trimmed**:

- `Canvas` — a node click selects it (toggling the detail panel); ties to card state removed; caller/callee badges
  open Neighbours.
- `StorySteps` — its own flow nav replaced by the flow strip; a step opens the detail panel instead of inline code.
- `MechanicalStory`, `TestsStory` — links to workspace addresses; code in the detail panel.
- `CardBody` → `FunctionCode` — a function's slice, effects and comments, used by the Diff tab.
- `reducer` — keeps view, pan, lens, mode, flow, layout and moved nodes; cards, the stacked viewer and the change
  panel's state removed (selection lives in the address).
- `prefs` — card, viewer, phone-tab and panel-tab keys removed; rail and panel widths added.

**Rebuilt**:

- `pages/Review.tsx` → the workspace shell; its data loading, progress events and AI provider move into a
  `useReview` hook.
- `Board.tsx` → `GraphView`: canvas, flow strip and toolbar only.
- `FlowBar` → `FlowStrip` (§3.6).
- `FileViewer` → the Diff tab's file view (one file at a time; per-CL picker, changes/full and folding carried over).
- `ChangePanel` → split: intent, risk, side effects and discussion to the Whole change page; the tree to the rail's
  Files; CLs to the rail's Change set and the CL page.
- `OverviewPage` → the Whole change page's map; `ClusterBoard` → the cluster page.
- `StoryList` → the rail's Stories section; `StoryPage` → the story page.
- `Findings` → the rail's Findings section and the finding page.
- `CiteText` → `NameText` (ids shown as names, with labelled links).
- `ClsPanel` → the CL page.
- `board.css`, `styles.css`, `stories.css`, `phone.css` → one `workspace.css` on the existing colour tokens, with
  the code and diff styles kept.

**Deleted**: `CardLayer` (floating cards), `PhoneBoard`, `PhoneMap`, `FlowReader`, the board growth on "+N callers".

## 6. Building it

The workspace is built on a separate address, `/w/:id`, while `/r/:id` keeps today's UI and its e2e tests. When the
workspace is complete, `/r/` switches to it and the old code is deleted; no code bridges the two.

1. **Backend** — story CLs, name index, neighbours, up-front findings, the title check.
2. **Shell** — header, rail, centre frame, breadcrumb, addresses and per-item memory, phone levels, `NameText`, the
   Whole change page.
3. **Detail panel** — Diff (node and file) and Neighbours.
4. **Story page** — Steps and Graph, `FlowStrip`, `GraphView`, trimmed `Canvas`, `StorySteps` and reducer.
5. **Finding, CL and cluster pages.**
6. **Switch and delete** — `/r/` becomes the workspace and old addresses redirect; deleted elements go; CSS
   consolidated; `expand` removed from frontend and backend; old e2e tests ported or removed.

## 7. Limits and failures

- A review still running: the centre shows its stages; the rail fills in when it finishes.
- A review without stories (run before them): the rail leaves out Stories; everything else works.
- An address to something that does not exist (`S9`, `F99`, an unknown node): the centre or panel says so, with a link
  to the Whole change.
- A failed source fetch: the detail panel says so, with Retry.
- No AI configured or reachable: the finding page says "AI analysis unavailable"; the rest works.
- Neighbours of a node with hundreds of callers: 20 shown, "Show all N" loads the rest.

## 8. Testing

- **Backend (pytest)**: story CLs (single and multiple CLs, stories stored without them); the name index (labels,
  stories, depot paths, unknown files); neighbours (ordering, tests last, limit and total, 404); up-front findings
  (only `high`, the cap, inside the budget); titles with ids rejected; `expand` removed.
- **Frontend logic (vitest)**: reading and building addresses; per-item memory; the breadcrumb for each kind of
  place; `NameText`; the rail's derived data (CL chips, the CL filter, findings by severity); the trimmed reducer.
- **Journeys (Playwright, desktop and phone)**: the Whole change page in order (intent, risk, then the rest); a story's
  graph — a node click opens the detail panel and a second click closes it, Neighbours, a row, Back; a finding to its
  story and back; leaving a story for a CL and returning to the same view, flow and open node; going up with the
  breadcrumb; old addresses redirecting; on a phone, rail → story → detail sheet with each top bar naming the place.
- **On every page**: no visible text matching `\bN\d+\b`; every link and button has an accessible name; the flow
  strip's buttons keep their position across flows; the flow strip's `scrollWidth` never exceeds its width.
- **Lab check**: libgit2 #6896 on desktop and phone, with screenshots for the owner.

## 9. Out of scope

- New analysis: stories, flows and findings are computed as today.
- Swarm features beyond what the CLs tab does today (refresh, create, post a summary link).
- Viewer tickets, SSO and other IT hardening (staged security rollout: owner-hosted proof of concept first).
