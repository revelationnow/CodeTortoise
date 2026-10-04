# Large Changes: an Overview and One Board per Cluster — Design

Date: 2026-10-03. Status: draft for review. Step 4 of the production-readiness work.

## 1. Why

A 33-file production change produced an impact graph of about 3000 nodes and 60,000 connections. The board draws
the first 150 nodes and 12 flows and says "+N more functions not shown", so most of a large change is silently
missing, and even 150 nodes is too dense to read.

Goals (agreed 2026-10-03):
- **No board has more than 30 nodes** unless the reader asks for more.
- A large change is split into **clusters** of connected code; one board per cluster; an **overview** shows the
  clusters in the architecture layers with their risk, counts and links.
- Nothing is dropped silently: every changed function and every flow is on exactly one board.
- Small changes (a board of 30 nodes or fewer) look exactly as today.

## 2. Clusters

**When.** The board stage first works out what one board for the whole change would have to show: every changed
function and field, the fields whose access the change added or removed, and every node on every flow. If that is 30 nodes or
fewer, the review keeps one board, as today. Otherwise it is split.

**Grouping** (changed code only; the impact graph's unchanged nodes never join clusters):
1. **Join** two changed functions when one calls the other, or both have an access the change added or removed to the
   same field. Unchanged functions they share (a logger everyone calls) and fields they use as before don't join them.
2. **Tests.** Changed test code (`is_test`) forms its own cluster(s).
3. **Split** a cluster whose required nodes (its changed functions, the fields whose access they changed, every node
   on its flows, visitors included) exceed 30: by module (the layer model's modules), then by directory, then by file.
   Parts under the same directory share a board while they fit (two top directories of the change never do). A single
   file still too big is cut into runs of functions in source order; a single function still too big is split by its
   flows into groups of at most 30 nodes, named "… (1 of 2)". Fields don't count for that last split: a board whose
   changed code and flows leave no room shows the fields that fit and counts the rest as hidden.
4. **Merge** clusters with fewer than 3 changed functions into the cluster in the nearest directory below the change's
   common prefix (the same directory first, then its parent's, …), when the result stays within 30 required nodes.
5. **Name.** The deepest directory the cluster's files share, relative to the change's common prefix
   (`driver/uart`); a cluster spanning several top directories is named by each one's (`deps/reftable +
   src/libgit2`); clusters with the same name get their main function appended (`driver/uart · uart_send`); split
   groups get "(1 of 2)".
6. **Order and ids.** Riskiest first: highest finding severity, then number of flows, then changed functions, then
   name. Ids `C1`, `C2`, … in that order.
7. **Many clusters.** Over 60 clusters, the smallest in each directory are merged further (only then may a merged
   cluster exceed 30 required nodes); the overview says how many were merged this way.

**Flows.** Impacts and flows are computed once for the whole change (as today), then each flow is assigned to the
cluster of its changed function (`cause`). Flow ids stay unique across the review (`FL1`…`FLn`, ranked across the
whole change as today). The 12-flow cap (`analysis.max_flows`) no longer applies: the 30-node budget bounds flows.

**Findings.** Each finding belongs to the cluster of its first node that is in a cluster (else the overview).

**Placement.** Each cluster sits in the layer holding most of its changed functions; other layers it touches are
listed as "also in …".

**Links.** For each ordered pair of clusters: calls from one's changed functions into the other's, and fields shared
(written by one, read or written by the other).

## 3. Boards

Each cluster gets a board in today's shape, built by the existing board code restricted to the cluster:
- **Required nodes** (always shown): the cluster's changed functions and fields, the fields whose access they added or
  removed, every node on its flows. Nodes on its flows that belong to another cluster are **visitors**: drawn dashed, with their home
  cluster and a link to it; their code cards work as usual.
- **Neighbours** fill the room left up to 30: what its impacts annotate, the fields its changed code uses as before,
  then callers, callees and the most affected nodes, ranked by blast radius as today.
- **Badges.** A node with callers or callees not on the board shows "+N callers" / "+N callees". Expanding adds up to
  10 at a time (most affected first) and may take the board past 30 nodes; the board then shows "N nodes · Reset".
  Expansions belong to the viewer (page address and browser storage); Reset clears them.
- `hidden_nodes` counts neighbours left out.

A single-board review is the same board without visitors; the badges apply to it too.

## 4. Data and API

**Stored per review** (board stage; a re-run rewrites them all):
- `board` — the single board, unchanged, for reviews that fit (and for every review made before this change).
- `overview` — only for split reviews: the change summary (today's `about`: intent, why, CLs, tree, drift); the
  clusters (`id`, `name`, `level`, `also` levels, `risk`, `files`, `changed`, `flows`, `findings`, file list, node
  ids); the links; totals; and how many clusters were merged past the limit.
- `board:C<n>` — one per cluster: today's board plus `cluster {id, name}`, on each node `home` (its cluster, set for
  visitors), `more_callers`, `more_callees`.
- `node_cluster` — node id → home cluster, for citations.

**Endpoints:**
- `GET /api/reviews/{id}/overview` → the overview, or 404 for a single-board review.
- `GET /api/reviews/{id}/board?cluster=C3` → that cluster's board; without `cluster`, the single board (today's call).
  An unknown cluster is 404 with "That cluster no longer exists after the re-run."
- `GET /api/reviews/{id}/board?cluster=C3&expand=N12:callers,N9:callees` → the board with those neighbours added
  (up to 10 per expansion) and laid out again. Works without `cluster` on a single board.
- `GET /api/reviews/{id}/locate?node=N12` (or `flow=FL3`, `finding=F2`) → `{cluster}`: the node's home cluster, else
  the first board showing it; null for a single-board review.

**Existing features:**
- **✦ Explain on a flow** finds the board holding that flow (each flow is on exactly one board) and updates it.
- **The up-front AI pass** is unchanged: the summary plus the top `llm.upfront_flows` flows across the whole change.
- **File tags** are applied to each cluster board as to today's board.
- **Comments** keep their anchors; a thread shows on every board that shows its code; review-level comments show on
  the overview.

**Configuration** (`analysis`): `board_max_nodes: 30` (was 150), `cluster_min_changed: 3`, `overview_max_clusters:
60`, `expand_step: 10`. `max_flows` is accepted and ignored.

## 5. Interface

**Routes.** `/r/:id` shows the overview for a split review, else today's board. `/r/:id/c/C3` shows a cluster's board.
`?node=N12` on either asks `locate` and opens the right cluster.

**Overview (desktop)** — the approved mockup:
- Header as today plus totals ("33 files · 6 clusters · 41 flows · 9 findings").
- Layer bands with one block per cluster: name, risk, files, changed functions, flows, findings, links in words
  ("→ service/logger: 22 calls, 3 shared fields"), "also in …". Clicking a block selects it and outlines the
  clusters it links to; **Open ›** or a double click opens its board.
- The "What's changed" panel on the right covers the whole change; each file in its tree shows its cluster, and
  clicking a file opens that cluster's board with the file in the viewer.
- The AI pill and review-level comments.

**Cluster board (desktop):** today's board for the cluster, plus:
- the breadcrumb "Overview › driver/uart" and ‹ › to the previous and next cluster in risk order;
- the change panel shows the cluster's files and findings, with a "Whole change" link to the overview;
- visitors dashed, with "· service/logger ›" to their home board;
- "+N callers / +N callees" badges, and "N nodes · Reset" past 30;
- layout, moved nodes and the panel tab saved per cluster (`ct.board.<id>.<cluster>.…`); single boards keep today's
  keys.

**Findings page:** grouped by cluster (a heading per cluster and a filter); citations open the right cluster.

**Phone:** the overview as stacked bands with full-width blocks (the approved phone mockup); tapping one opens the
cluster in today's phone layout; the ☰ menu gains "Overview" and the cluster list; a cluster's header shows
"‹ C2 of 6 ›".

## 6. Limits and failures

- Clustering looks at changed code and the links among it (hundreds of items, not the whole graph). Impacts and
  flows are computed once. Each board is laid out with at most 30 nodes (expansion: about 40).
- If clustering fails, the review falls back to one board of the 30 most important nodes and the board stage is
  degraded: "shown as one board (clustering failed: …)".
- Old reviews have no overview and show their single board.

## 7. Realistic lab: large libgit2 changes

`lab/p4-import.py` (in the repo; run by hand, never as a service) builds a Perforce history from a GitHub project for
manual testing at size:
- Arguments: a git URL (or local clone), a base commit, the commits to import as exact changelists (default: every
  first-parent commit touching at least 30 C/C++ files outside tests in the range), a depot path, paths to leave out.
- Starts a local `p4d` under a given root if none is running at the given port (setting the first user's password, as
  `lab/setup.sh` does); creates the depot path and a client. It refuses a depot path that already has files.
- Imports the base snapshot, then for each chosen commit: one **catch-up** changelist with everything between the
  previous point and the commit's first parent ("catch-up to <sha>"), then the commit itself as one changelist titled
  with its subject and short sha. Adds, deletes, renames, binary files and executable bits are handled; `p4`
  operations are batched.
- Optionally shelves chosen commits as pending changelists on top of head (`--shelve`), for shelved-review testing.
- Writes `cls.tsv`: changelist, kind (catch-up or commit), sha, subject, C files, directories.

For libgit2 (base `1de5a32dd^1`, just before #6896 on 2024-10-01), the default picks the large merges: #6896 vector
(48 files, 6 directories), #6897 hashmap (57), a merge of main into the ssh branch (102), #6975 sha256 simplification
(41), #6994 cmake (39), #7117 reftables (52), #7278 pcre2 (68), #7292 docs update (69) and #7261 sha256 (47). They go under a new depot path (`//depot/libgit2-big/...`), leaving the
current lab untouched. A lab README section says how to build compile commands for it and review the CLs.

## 8. Testing

- **Unit** (synthetic impact graphs): joining by calls and by fields whose access changed, not by common helpers or
  fields used as before; tests apart; splitting over 30 by module, directory, file, then flow groups; parts under one
  directory sharing a board, top directories never; merging small clusters into the nearest directory within 30; a
  function touching too many fields; a board leaving out fields past 30, never changed code or flow nodes; the 60-cluster
  limit; names, order, ids, placement, links; every changed function and flow on exactly one board; required nodes
  never cut; neighbours fill to 30; badge counts.
- **Pipeline:** today's fixture stays one board (regression). A generated large fixture produces an overview and
  cluster boards, each at most 30 nodes before expansion.
- **API:** overview, cluster boards, expansion, `locate`, ✦ Explain on a flow in a cluster, 404 for a single-board
  overview and a stale cluster.
- **Large fixture:** `codetortoise fixture-demo --large` generates about 30 C files in 6 directories with call chains,
  shared fields and two CLs (a git fixture, like today's), for the pipeline and e2e tests.
- **e2e:** the overview (selection, links, open), breadcrumb and ‹ ›, a visitor to its home cluster, "+N callers"
  then Reset, a citation opening the right cluster, the Findings grouping, the phone overview, small reviews unchanged.
- **Lab script:** a test imports a small generated git repo (a base and two commits, one large) into a throwaway
  `p4d` when `p4d` is available (skipped otherwise), and checks the changelists, the catch-up, `cls.tsv` and a
  shelve.

- **Real code** (by hand, §7): every libgit2-big changelist reviews to boards of at most 30 nodes. Measured while
  writing the plan: #6896 (139 changed functions) went from 38 clusters under the first rules to 8.

## 9. Out of scope

Choosing clusters by hand, saving expansions for everyone, one node per struct instead of one per field (would take
reftables' 45 clusters to about 25; a later step), cluster-level AI summaries (on-demand ✦ per cluster could
come later), and changing how impacts and flows are computed.
