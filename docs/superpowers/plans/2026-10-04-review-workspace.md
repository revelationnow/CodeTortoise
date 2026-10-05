# Review Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One place to read a review. A rail derived from the change set (CLs, the stories drawn from them, findings, files) replaces the four tabs. The centre shows one item (the whole change, a story, a finding, a CL, a cluster), and a detail panel opens on demand with a function's code, a file's diff or a node's neighbours. Every place has an address, ids never show, and phones get three levels (rail, item, sheet).

**Architecture:** The backend adds each story's CLs, a name index (`/names`), a node's neighbours (`/nodes/{nid}/neighbours`), up-front AI analysis of high findings and an id check on AI titles; `expand` goes. The frontend builds the workspace under `frontend/src/workspace/` at `/w/:id` beside today's UI: pure modules first (addresses, memory, rail data, breadcrumb, names), then the shell, the detail panel, the flow strip and graphs, the story, finding, CL and cluster pages. Task 16 switches `/r/` to it, redirects the old addresses and deletes the old UI and its specs; Task 18 folds `board.css` into `workspace.css`.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, SQLite, pytest, ruff; React 19, TypeScript (strict), react-router 7, Vite, vitest, Playwright. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-04-review-workspace-design.md`

**Base:** `main` (the spec is its latest commit).

**Provenance:** every code block was run before this plan was written. The tasks were then replayed in order on a fresh tree from `main` by a script that read this document: it applied each step's blocks, ran each step's command and recorded its output. Each task's tests failed before its implementation and passed after it, and the suite stayed green after every task. The replayed tree is byte-identical to the validated one. Under parallel load a few end-to-end tests timed out or lost their browser on the first run and passed when rerun alone. Most were old-UI specs that Task 16 deletes. The Expected lines count the whole run. If a test fails with a timeout or a closed browser, rerun it alone with `--last-failed`. If it fails again, it is a real failure. If its error is the same on every first run, it is a race to fix, not noise. New files are given in full. Changes to existing files are unified diffs against the previous task's state (apply with `git apply`, or by hand).

## Global Constraints

- **Addresses (§2.3):** `/r/:id`, `/r/:id/s/:sid` (`?view=graph`), `/r/:id/f/:fid`, `/r/:id/cl/:cl`, `/r/:id/c/:cid`; on any of them `flow=<n>` (1-based), `open=<node id>` or `open=file:<depot path>[:<line>]`, `tab=diff|neighbours` (default `diff`). Defaults are left out of links. While it is built the workspace lives at `/w/:id` (Tasks 6–15); Task 16 moves it to `/r/:id`.
- **History (§2.4):** opening an item or opening the detail panel on something new pushes; switching flow, view or tab replaces.
- **Names, not ids (§2.4, §8):** no visible text matches `\bN\d+\b`. Node ids in text show as the node's name linked to its code; an id the index cannot name shows as "a function". Stories and findings show titles first with `S1`/`F2` as a small grey handle.
- **Labelled links (§2.4, §8):** every link and button has an accessible name and a tooltip saying where it goes ("Open uart.c's diff", "Go to story S1: …", "Open CL 101", "Close the code").
- **Layout (§2.1):** desktop over 1100 px (rail 280 px, resizable 200–600; detail panel about 45%, resizable); tablet 641–1100 px (rail is a drawer behind ☰); phone 640 px and under (rail is home, an item is a page, the detail panel a full-screen sheet).
- **Limits (§4, §7):** `llm.upfront_findings: 5` (high findings only, inside the review's AI budget); neighbours show 20 rows per column with "Show all N".
- **Messages (§7):** "Story S9 isn't in this review." (and the same for findings, CLs and parts) with a link to the whole change; "This function isn't in this review."; "AI analysis unavailable.".
- **Browser storage:** sessionStorage `ct.ws.<rid>.memory` (per-item memory); localStorage `ct.ws.railW`, `ct.ws.detailW`, `ct.ws.rail.open`, `ct.ws.<rid>.railScroll`. Every read and write is wrapped in try/catch.
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).
- **End-to-end runs:** build the frontend first (`npm run build` writes `backend/codetortoise/web/static`). Playwright starts the fixture servers itself (8799; 8798 with the fake model on 8797; 8796 for the large fixture). If Chromium crashes ("Target crashed") the browser's temp directory is full: point `TMPDIR` at a directory on disk.

## Review Focus

The conditions the spec implies that are most likely to bite a real user, most likely first. A test in the task that owns the code pins each one.

1. **Bookmarks and links from before the workspace** (`/r/7/board?node=N12`, `/r/7/files`, `/r/7/s/S1?tab=graph`, a `/w/` link, and on a split review a node outside every story) must land where that thing lives now, with the node open, not on a blank page or the whole change. Pinned by the vitest cases in `legacy.test.ts` and the e2e tests "the old tabs, the board, a cited node and /w/ go to where those things live now" and "a cited node outside every story opens the part holding it; one inside a story opens that story" (Task 16).
2. **An address saved before a re-run** that names a story, finding, CL or node the review no longer has must say so and link to the whole change. Pinned by "an address to something that does not exist says so" (Task 6) and "an unknown node says so" (Task 8).
3. **A node with no code of its own** (a field folded into a struct on a story graph, a node only the review board shows) opened by `open=` must show its struct's or board's code, not nothing. Pinned by `detail.test.ts` "finds a field folded into a struct as the struct" and "falls back to a node without code, then to nothing" (Task 8).
4. **Long flow titles and many flows** must not move the ‹ › controls or scroll the strip sideways, on the review's graph, a story's graph and a story's steps. Pinned by `flowStripHolds` in "the review's graph: open full graph, select and deselect a node, flows keep their controls" (Task 11) and "the graph: a node click opens and closes its code; ‹ › keep their place between stories" (Task 12).
5. **Code shown outside any graph** (the detail panel next to a text page) must keep its diff colours, syntax highlighting and annotation fills, and the head's pills must stay readable in both themes. Pinned by "the diff colours added lines, highlights code and fills annotations, outside any graph" and the AI pill's contrast check (Task 18).

## Spec Coverage

| Spec | Where |
|---|---|
| §2.1 layout (desktop, tablet drawer, phone levels) | Task 6 |
| §2.2 the rail (sections, CL filter, chips, findings by severity, files) | Tasks 5, 6 |
| §2.3 addresses | Task 4 (read and write), Task 16 (old addresses) |
| §2.4 getting around (breadcrumb, history, per-item memory, names, labelled links) | Tasks 4, 5, 6, 12 |
| §3.1 whole change | Tasks 7, 11 (its graph), 15 (the map of a split review) |
| §3.2 story | Task 12 |
| §3.3 finding | Task 13 |
| §3.4 changelist | Task 14 |
| §3.5 cluster | Task 15 |
| §3.6 the flow strip | Task 10 |
| §3.7 detail panel | Tasks 8 (Diff), 9 (Neighbours) |
| §4.1 story CLs | Task 1 |
| §4.2 name index, §4.3 neighbours | Task 2 |
| §4.4 up-front findings, §4.5 no ids in AI titles | Task 3 |
| §4.6 removed (`expand`) | Task 17 (and Task 16 for the frontend preference) |
| §5 frontend elements (kept, trimmed, rebuilt, deleted) | Tasks 6–16; CSS in Task 18 |
| §6 building it (`/w/` then the switch) | Tasks 6–15, then Task 16 |
| §7 limits and failures | Tasks 6, 8, 9, 13, 16 |
| §8 testing | every task; the lab check in Finish |

## Decisions the spec left open (or that differ from it)

- **The graph reducer has no `flow`.** The flow lives in the address (`flow=`), so it is not kept twice.
- **A review shown as one board has its full graph at `/r/:id?view=graph`** (§3.1 names no address for "Open full graph").
- **The detail panel finds a node's code** on the graph of the story holding it (the name index's `story`), else on the review's board; failing both it shows the node's file at its line.
- **Section crumbs** ("Stories", "Findings", "Change set", "Map") link to the review's home with a `#section` anchor that opens and scrolls that rail section (on a phone, the rail).
- **On a phone `/r/:id` is the rail**; the rail's "Whole change" row opens the same address with history state `{page: true}`, which shows the page.
- **Evidence lines carry workspace paths.** The finding page maps each to the depot path with the longest shared path tail among the finding's files, the changed files and named nodes' files, and leaves a tie unlinked. No backend change.
- **`styles.css` stays** the sheet for the app's other pages (tokens, top bar, landing, login, health), minus its dead rules; `board.css` folds into `workspace.css` (§5). The board's role tokens move from `.bd` (which wrapped only the graph) to `:root`, so code in the detail panel gets its colours; its `--info`, `--ok` and `--warn` become `--bd-*` because `styles.css` uses those names for other colours. Component classes keep their `bd-` prefix.
- **The AI e2e server explains one high finding up front** (`upfront_findings: 1` in `e2e/serve-ai.sh`) so the budget tests keep small, exact counts.
- **Tests no fixture can reach** are served through mocked routes: a repeated edit (neither fixture has one), a review without stories, and a large-fixture node outside every story.

---

### Task 1: Each story names its changelists

Spec §4.1. `Story` gains `cls: list[int]`: the CLs of the files holding the story's nodes, sites or test
functions, sorted, from the change files' per-CL history (the same history `About.tree` files carry). `build_stories`
fills it; stories stored before load with `cls = []`, and the UI shows no chips for them.

**Files:**
- Modify: `backend/codetortoise/stories.py`
- Test: `backend/tests/test_stories.py`

**Interfaces:**
- Consumes: `stories.build_stories` and its board context (`x.c.files`, each with `cls`).
- Produces: `stories.Story.cls: list[int]` (default `[]`), served by `GET /api/reviews/{rid}/stories` and `/stories/{sid}`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_stories.py`:

```diff
diff --git a/backend/tests/test_stories.py b/backend/tests/test_stories.py
index 76205b6..205227d 100644
--- a/backend/tests/test_stories.py
+++ b/backend/tests/test_stories.py
@@ -7,7 +7,7 @@ from codetortoise.diffmap import DiffMap, FunctionChange
 from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function, TuInfo
 from codetortoise.impact import Edge, ImpactModel, Node
 from codetortoise.stories import build_stories
-from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange
+from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange, PerClText
 
 W = "/w"
 
@@ -448,3 +448,15 @@ def test_unreached_code_over_the_board_budget_is_split_as_boards_are():
     ss, _ = build_stories(_world(fns, calls=calls, cfg=AnalysisConfig(board_max_nodes=4)))
     assert len(ss.stories) > 1 and all(len(s.nodes) <= 4 for s in ss.stories)
     assert all(s.title.startswith("Other changes in `") for s in ss.stories)
+
+
+def test_each_story_names_the_changelists_of_its_files():
+    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c", var="b"),
+                ("lonely", "src/c.c", ["y = 1;"], ["y = 2;"])])
+    per = {"/w/src/a.c": [1], "/w/src/b.c": [1, 2], "/w/src/c.c": [3]}
+    for f in c.cs.files:
+        f.per_cl = [PerClText(cl=n, before=f.before, after=f.after) for n in per[f.local]]
+    ss, _ = build_stories(c)
+    (m,) = _by_kind(ss, "mechanical")
+    (o,) = _by_kind(ss, "other")
+    assert m.cls == [1, 2] and o.cls == [3]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_stories.py -q`

Expected: FAIL — `1 failed, 29 passed` and `AttributeError: 'Story' object has no attribute 'cls'`

- [ ] **Step 3: Implement**

`backend/codetortoise/stories.py`:

```diff
diff --git a/backend/codetortoise/stories.py b/backend/codetortoise/stories.py
index 2b013af..dadf9bd 100644
--- a/backend/codetortoise/stories.py
+++ b/backend/codetortoise/stories.py
@@ -86,6 +86,7 @@ class Story(BaseModel):
     sub: list[str] | None = None                            # a mechanical story: [old, new]
     subs: list[list[str]] = Field(default_factory=list)     # "N more repeated edits": each substitution
     collapsed: bool = False                                 # a behaviour story past the list's limit
+    cls: list[int] = Field(default_factory=list)            # the changelists of the files holding its code
 
 
 class StoryDetail(BaseModel):
@@ -360,9 +361,13 @@ def build_stories(c: BoardContext, home: dict[str, str] | None = None,
 
     stories, details = [], {}
     changed_lines = sum(max(_count(f.before, f.after)) for f in c.cs.files)   # added and deleted files too
+    cls_of = {f.local: {p.cl for p in f.per_cl} for f in c.cs.files}
     for d in ordered:
         sid = ids[id(d)]
         st = _story(x, d, sid, sev, home, depots, is_test, effect_of)
+        files = {x.local(n) for n in d.members} | {x.local(fl.cause) for fl in d.flows if fl.cause} | {
+            loc for _, loc, _ in d.sites}
+        st.cls = sorted(set().union(*(cls_of.get(f, set()) for f in files if f)))
         stories.append(st)
         details[sid] = _detail(x, d, st, impacts, depots, about, cfg.story_graph_nodes, node_story, mech_of, ids, mechs,
                                fn_sites, effect_of, is_test)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_stories.py -q`

Expected: `30 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`

Expected: `All checks passed!` and `432 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/stories.py backend/tests/test_stories.py
git commit -m "feat(stories): each story names the changelists of its files"
```

---

### Task 2: Names and neighbours of graph nodes

Spec §4.2–§4.3. `names.py` serves two things the workspace needs so it never shows a node id.
`GET /api/reviews/{rid}/names` returns `{ "<node id>": { label, kind, path, line, story } }` for every node the UI can
show: nodes on any stored board or story graph, finding and evidence nodes, and nodes cited (`N12`) in flow, story and
finding text. `GET /api/reviews/{rid}/nodes/{nid}/neighbours?limit=20` returns the node and its callers and callees
(call and virtual edges), the most affected first by blast score, test code last, each list capped at `limit` with its
`total`; 404 for an unknown node. Both are served from the stored impact model, node files and stories; no new blob.

**Files:**
- Create: `backend/codetortoise/names.py`
- Modify: `backend/codetortoise/web/app.py`
- Test: `backend/tests/test_names.py` (new)
- Test: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: `boardstore` (boards, overview, stories), `store.list_findings`, the `impact` and `node_files` blobs, `board.is_test_path`.
- Produces: `names.cited(texts) -> set[str]`; `names.names(im, ids, depot_of, node_story) -> dict[str, dict]`;
  `names.neighbours(im, nid, depot_of, node_story, *, root, limit) -> dict | None`; the two endpoints above
  (`{label, kind, path, line, story}` per name; neighbours items add `id, changed, test`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_names.py`:

```python
"""Names and neighbours for the review workspace (spec 2026-10-04-review-workspace §4.2–§4.3)."""
from codetortoise.impact import BlastItem, Edge, ImpactModel, Node
from codetortoise.names import cited, names, neighbours


def _im():
    nodes = {
        "N1": Node(id="N1", key="c:@F@send", label="send", file="/w/src/send.c", line=10, status="changed"),
        "N2": Node(id="N2", key="c:@F@flush", label="flush", file="/w/src/log.c", line=3),
        "N3": Node(id="N3", key="c:@F@init", label="init", file="/w/src/init.c", line=7),
        "N4": Node(id="N4", key="c:@F@test_send", label="test_send", file="/w/tests/send_test.c", line=1),
        "N5": Node(id="N5", key="c:@F@hal_write", label="hal_write", file="/w/hal/hal.c", line=20),
        "N6": Node(id="N6", key="field:c:@S@Uart@FI@errors", kind="field", label="Uart::errors"),
    }
    edges = [Edge(id="E1", src="N2", dst="N1", kind="call"), Edge(id="E2", src="N3", dst="N1", kind="call"),
             Edge(id="E3", src="N4", dst="N1", kind="call"), Edge(id="E4", src="N1", dst="N5", kind="virtual"),
             Edge(id="E5", src="N1", dst="N6", kind="writes")]
    blast = [BlastItem(node="N3", hop=1, score=0.9, via="call", path=["N3", "N1"]),
             BlastItem(node="N2", hop=1, score=0.4, via="call", path=["N2", "N1"])]
    return ImpactModel(nodes=nodes, edges=edges, changed=["N1"], blast=blast)


DEPOTS = {"N1": ["//d/src/send.c"], "N2": ["//d/src/log.c"], "N3": ["//d/src/init.c"], "N4": ["//d/tests/send_test.c"],
          "N6": ["//d/src/send.c", "//d/include/uart.h"]}


def test_cited_finds_node_ids_in_text_but_not_finding_or_story_ids():
    assert cited(["`send` (N1) writes N6; see F2 and S1", None, "N12x is not an id, N12 is"]) == {"N1", "N6", "N12"}


def test_names_give_each_node_its_label_kind_depot_path_line_and_story():
    out = names(_im(), ["N1", "N6", "N99"], DEPOTS, {"N1": "S1"})
    assert out == {
        "N1": {"label": "send", "kind": "function", "path": "//d/src/send.c", "line": 10, "story": "S1"},
        "N6": {"label": "Uart::errors", "kind": "field", "path": None, "line": None, "story": None},
    }


def test_neighbours_list_callers_most_affected_first_tests_last_and_callees():
    out = neighbours(_im(), "N1", DEPOTS, {"N1": "S1", "N3": "S2"}, root="/w", limit=20)
    assert out["node"]["label"] == "send" and out["node"]["changed"] is True
    assert [i["label"] for i in out["callers"]["items"]] == ["init", "flush", "test_send"]
    assert out["callers"]["total"] == 3 and out["callers"]["items"][-1]["test"] is True
    assert out["callers"]["items"][0]["story"] == "S2" and out["callers"]["items"][0]["changed"] is False
    assert [i["label"] for i in out["callees"]["items"]] == ["hal_write"] and out["callees"]["items"][0]["path"] is None


def test_neighbours_are_capped_by_the_limit_and_count_them_all():
    out = neighbours(_im(), "N1", DEPOTS, {}, root="/w", limit=1)
    assert [i["label"] for i in out["callers"]["items"]] == ["init"] and out["callers"]["total"] == 3


def test_neighbours_of_an_unknown_node_are_none():
    assert neighbours(_im(), "N99", DEPOTS, {}, root="/w", limit=20) is None
```

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index f9ce17a..92cd9c2 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -324,3 +324,33 @@ def test_locate_names_the_story_of_a_node_flow_or_finding(env):
     fid = ss["stories"][0]["findings"][0]
     assert owner.get(f"/api/reviews/{rid}/locate", params={"finding": fid}).json()["story"] == "S1"
     assert owner.get(f"/api/reviews/{rid}/locate", params={"node": "N999"}).json() == {"cluster": None, "story": None}
+
+
+def test_names_give_the_ui_a_name_for_every_node_it_can_show(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    assert TestClient(app).get(f"/api/reviews/{rid}/names").status_code == 401
+    names = owner.get(f"/api/reviews/{rid}/names").json()
+    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()
+    send = next(n["id"] for n in s1["board"]["nodes"] if n["label"] == "uart_send")
+    assert names[send] == {"label": "uart_send", "kind": "function", "path": "//fixture/driver/uart.c",
+                           "line": names[send]["line"], "story": "S1"}
+    findings = owner.get(f"/api/reviews/{rid}/findings").json()
+    assert {n for f in findings for n in f["nodes"]} <= set(names)
+    assert all(n.startswith("N") for n in names) and len(names) < 200        # what the UI shows, not the whole graph
+
+
+def test_neighbours_list_a_nodes_callers_and_callees(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    names = owner.get(f"/api/reviews/{rid}/names").json()
+    send = next(k for k, v in names.items() if v["label"] == "uart_send")
+    assert TestClient(app).get(f"/api/reviews/{rid}/nodes/{send}/neighbours").status_code == 401
+    nb = owner.get(f"/api/reviews/{rid}/nodes/{send}/neighbours").json()
+    assert nb["node"]["label"] == "uart_send" and nb["node"]["changed"] is True
+    assert "logger_flush" in [i["label"] for i in nb["callers"]["items"]]
+    assert nb["callers"]["total"] >= len(nb["callers"]["items"])
+    one = owner.get(f"/api/reviews/{rid}/nodes/{send}/neighbours", params={"limit": 1}).json()
+    assert len(one["callers"]["items"]) == 1
+    r = owner.get(f"/api/reviews/{rid}/nodes/N99999/neighbours")
+    assert r.status_code == 404 and r.json()["detail"] == "no node N99999 in this review"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_names.py tests/test_web.py -q`

Expected: FAIL — `1 error` and `ModuleNotFoundError: No module named 'codetortoise.names'`

- [ ] **Step 3: Implement**

`backend/codetortoise/names.py`:

```python
"""Names and neighbours of graph nodes for the review workspace (spec 2026-10-04-review-workspace §4.2–§4.3): the
reader sees a function's name, never its node id."""
from __future__ import annotations

import re
from collections.abc import Iterable

from codetortoise.board import is_test_path
from codetortoise.impact import ImpactModel

CITE = re.compile(r"\bN\d+\b")


def cited(texts: Iterable[str | None]) -> set[str]:
    """Node ids (`N12`) named in text."""
    return {m for t in texts if t for m in CITE.findall(t)}


def _name(im: ImpactModel, nid: str, depot_of: dict[str, list[str] | None], node_story: dict[str, str]) -> dict:
    n = im.nodes[nid]
    files = depot_of.get(nid) or []
    return {"label": n.label, "kind": n.kind, "path": files[0] if n.file and files else None, "line": n.line,
            "story": node_story.get(nid)}


def names(im: ImpactModel, ids: Iterable[str], depot_of: dict[str, list[str] | None],
          node_story: dict[str, str]) -> dict[str, dict]:
    """Each known node's label, kind, depot path (None for a field, or when unknown), line and story."""
    return {nid: _name(im, nid, depot_of, node_story) for nid in sorted(set(ids)) if nid in im.nodes}


def neighbours(im: ImpactModel, nid: str, depot_of: dict[str, list[str] | None], node_story: dict[str, str], *,
               root: str, limit: int) -> dict | None:
    """A node's callers and callees (call and virtual edges): the most affected first, test code last; at most `limit`
    of each, with their totals. None for an unknown node."""
    if nid not in im.nodes:
        return None
    r = root.rstrip("/") + "/"
    changed = set(im.changed)
    score = {b.node: b.score for b in im.blast}

    def item(m: str) -> dict:
        f = im.nodes[m].file or ""
        test = is_test_path(f[len(r):] if f.startswith(r) else f) if f else False
        return {"id": m, **_name(im, m, depot_of, node_story), "changed": m in changed, "test": test}

    def side(ids: set[str]) -> dict:
        items = sorted((item(m) for m in ids if m in im.nodes),
                       key=lambda i: (i["test"], -score.get(i["id"], 0.0), i["label"], i["id"]))
        return {"total": len(items), "items": items[:limit]}

    calls = [e for e in im.edges if e.kind in ("call", "virtual")]
    return {"node": item(nid), "callers": side({e.src for e in calls if e.dst == nid and e.src != nid}),
            "callees": side({e.dst for e in calls if e.src == nid and e.dst != nid})}
```

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index 30b8ff0..69644d8 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -16,6 +16,7 @@ from codetortoise.facts.model import Facts
 from codetortoise.health import run_health
 from codetortoise.impact import ImpactModel
 from codetortoise.llm import ondemand, tortoise
+from codetortoise.names import cited, names, neighbours
 from codetortoise.paths import canon
 from codetortoise.pipeline import JobRunner
 from codetortoise.provenance import tag_board
@@ -315,6 +316,46 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
             return {"cluster": None, "story": sid}
         raise HTTPException(404, "not on any board of this review")
 
+    def shown(rid: int) -> tuple[ImpactModel, dict, dict[str, str]]:
+        """The review's graph, node files and node stories, for names and neighbours."""
+        im = ImpactModel.model_validate(store.get_blob(rid, "impact") or {})
+        ss = boardstore.stories(store, rid)
+        return im, store.get_blob(rid, "node_files") or {}, ss.node_story if ss else {}
+
+    @app.get("/api/reviews/{rid}/names")
+    def node_names(rid: int, _: str = Depends(user_of)):
+        """A name for every node the UI can show (spec 2026-10-04-review-workspace §4.2): changed code, nodes on any
+        board or story, findings' nodes and the nodes cited in flow, story, finding and summary text."""
+        review_or_404(rid)
+        im, depot_of, node_story = shown(rid)
+        ids, texts = set(im.changed), []
+        for b in boardstore.boards(store, rid).values():
+            ids |= {n.id for n in b.nodes} | {n for fl in b.flows for n in fl.path}
+            texts += [t for fl in b.flows for t in (fl.what, fl.title, fl.text, fl.effect, fl.check)]
+            texts += [b.about.intent, *(w.text for w in b.about.why)]
+        ss = boardstore.stories(store, rid)
+        for st in ss.stories if ss else []:
+            texts += [st.title, st.summary]
+            d = boardstore.story(store, rid, st.id)
+            if d is not None:
+                ids |= {n.id for n in d.board.nodes} | {n.id for n in (d.graph.nodes if d.graph else [])}
+                texts += [f.note for f in d.functions]
+        for f in store.list_findings(rid):
+            ids |= set(f.nodes) | {n for e in f.evidence for n in e.nodes or []}
+            ids |= {n for h in f.hypotheses for n in h.cites}
+            texts += [f.summary, f.explanation, *f.verify_steps, *(h.text for h in f.hypotheses), *(e.text for e in f.evidence)]
+        return names(im, ids | cited(texts), depot_of, node_story)
+
+    @app.get("/api/reviews/{rid}/nodes/{nid}/neighbours")
+    def node_neighbours(rid: int, nid: str, limit: int = 20, _: str = Depends(user_of)):
+        """A node's callers and callees, the most affected first (spec 2026-10-04-review-workspace §4.3)."""
+        review_or_404(rid)
+        im, depot_of, node_story = shown(rid)
+        out = neighbours(im, nid, depot_of, node_story, root=canon(str(cfg.workspace.root)), limit=max(1, limit))
+        if out is None:
+            raise HTTPException(404, f"no node {nid} in this review")
+        return out
+
     @app.get("/api/reviews/{rid}/source")
     def source(rid: int, path: str, side: Literal["before", "after"] = "after", _: str = Depends(user_of)):
         """A file's text for the board: changed files from the change set, others from the base workspace."""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_names.py tests/test_web.py -q`

Expected: `29 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`

Expected: `All checks passed!` and `439 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/names.py backend/codetortoise/web/app.py backend/tests/test_names.py backend/tests/test_web.py
git commit -m "feat(api): name every node the UI shows and list a node's callers and callees"
```

---

### Task 3: High findings explained up front; no ids in AI titles

Spec §4.4–§4.5. `llm.upfront_findings` (default 5): the review run's AI pass also explains the first N
findings of severity `high`, in finding order, with the existing finding job and inside the review's budget. An AI
story or flow title that names a node or finding id (`\b[NF]\d+\b`) fails the style check (`_titled`), keeps the
template title and counts as a style drop. The AI e2e server sets `upfront_findings: 1`, so its usage counts grow by
one finding call (the budget e2e tests are updated to match).

**Files:**
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `backend/codetortoise/pipeline.py`
- Test: `backend/tests/test_ondemand.py`
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_storyboard.py`
- Test: `backend/tests/test_tortoise.py`
- Test: `frontend/e2e/ai.spec.ts`
- Test: `frontend/e2e/mention.spec.ts`
- Test: `frontend/e2e/serve-ai.sh`

**Interfaces:**
- Consumes: `llm.storyboard.finding_job`, `_styled`.
- Produces: `config.LlmConfig.upfront_findings: int = 5`; `storyboard.build_storyboard(..., upfront_stories=3, upfront_findings=0)`
  (the pipeline passes `cfg.llm.upfront_findings`); `storyboard._titled(text) -> bool`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_ondemand.py`:

```diff
diff --git a/backend/tests/test_ondemand.py b/backend/tests/test_ondemand.py
index d8b6987..0e84726 100644
--- a/backend/tests/test_ondemand.py
+++ b/backend/tests/test_ondemand.py
@@ -44,6 +44,7 @@ def ai(fx, tmp_path):
     svc.cfg.llm.base_url = "http://llm/v1"
     svc.cfg.llm.upfront_flows = 1                                      # the fixture has 3 flows: leave 2 for later
     svc.cfg.llm.upfront_stories = 1                                    # and 2 stories: leave 1
+    svc.cfg.llm.upfront_findings = 1                                   # and several high findings: leave the rest
     app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
     owner = login(app, "owner")
     rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
@@ -96,11 +97,11 @@ def test_explain_is_refused_over_the_budget_and_the_owner_raises_it(ai):
     svc, app, owner, rid, _ = ai
     bob = login(app, "bob")
     used = owner.get(f"/api/reviews/{rid}/ai").json()["used"]
-    assert used == 3                                                   # the up-front pass: 1 flow, 1 story, the summary
+    assert used == 4                                                   # the up-front pass: 1 flow, 1 story, 1 finding, the summary
     assert bob.put(f"/api/reviews/{rid}/ai/budget", json={"budget": 10}).status_code == 403
     assert owner.put(f"/api/reviews/{rid}/ai/budget", json={"budget": used}).json()["budget"] == used
     r = bob.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": "F1"})
-    assert r.status_code == 429 and "this review has used its 3 AI calls" in r.json()["detail"]
+    assert r.status_code == 429 and "this review has used its 4 AI calls" in r.json()["detail"]
     owner.put(f"/api/reviews/{rid}/ai/budget", json={"budget": used + 5})
     assert bob.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": "F1"}).status_code == 202
 
@@ -124,10 +125,10 @@ def test_the_ai_view_reports_limits_and_calls(ai):
     assert (u["budget"], u["me_limit"], u["per_mention"], u["llm"]) == (200, 100, 6, True)
     assert "calls" not in u                                            # polled often: the list is fetched apart
     calls = owner.get(f"/api/reviews/{rid}/ai/calls").json()
-    assert [c["purpose"] for c in calls] == ["flow", "story", "summary"]
+    assert [c["purpose"] for c in calls] == ["flow", "story", "finding", "summary"]
     assert all(c["prompt_tokens"] == 1000 for c in calls)
     h = owner.get("/api/health").json()                               # + layer naming, once per index
-    assert h["ai"]["calls_today"] == 4 and h["ai"]["limits"] == {"per_review": 200, "per_person_daily": 100,
+    assert h["ai"]["calls_today"] == 5 and h["ai"]["limits"] == {"per_review": 200, "per_person_daily": 100,
                                                                  "per_mention": 6}
 
 
```

`backend/tests/test_pipeline.py`:

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 5ceff03..1ec99c2 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -158,12 +158,14 @@ def test_llm_text_stored_by_a_review_records_its_prompt_files(fx, tmp_path):
     assert board["about"]["intent_source"] == "llm" and board["about"]["intent_files"] is None
     llm_flows = [f for f in board["flows"] if f["what_source"] == "llm"]
     assert llm_flows and all(f["what_files"] and set(f["files"]) <= set(f["what_files"]) for f in llm_flows)
-    # the up-front pass: the summary, the top 3 flows and the top behaviour stories (the fixture has 2); findings are
-    # explained on demand (spec 2026-10-03 §3, 2026-10-04 §4)
-    assert len(llm_flows) == 3 and all(f.explanation is None for f in svc.store.list_findings(rid))
+    # the up-front pass: the summary, the top 3 flows, the top behaviour stories (the fixture has 2) and the high
+    # findings; the rest are explained on demand (spec 2026-10-03 §3, 2026-10-04 §4, review workspace §4.4)
+    found = svc.store.list_findings(rid)
+    assert len(llm_flows) == 3 and any(f.severity == "high" for f in found)
+    assert all((f.explanation is not None) == (f.severity == "high") for f in found)
     usage = svc.ledger.usage(rid)
-    assert usage["used"] == 6 and usage["by_purpose"] == {"flow": 3, "story": 2, "summary": 1}
-    assert usage["by_person"] == {"pipeline": 6}
+    assert usage["used"] == 9 and usage["by_purpose"] == {"flow": 3, "story": 2, "finding": 3, "summary": 1}
+    assert usage["by_person"] == {"pipeline": 9}                       # the fixture's 3 high findings, under the cap of 5
 
 
 def test_the_llm_stage_reports_text_dropped_for_breaking_the_style(fx, tmp_path):
```

`backend/tests/test_storyboard.py`:

```diff
diff --git a/backend/tests/test_storyboard.py b/backend/tests/test_storyboard.py
index cc96603..49437cc 100644
--- a/backend/tests/test_storyboard.py
+++ b/backend/tests/test_storyboard.py
@@ -321,3 +321,38 @@ def test_a_retold_story_records_the_files_behind_its_prompt():
                      node_files=node_files)
     assert details[0].story.text_files == ["//w/d/uart.c", "//w/svc/logger.c"]     # its code, its flow's and F1's
     assert details[1].story.text_source == "template" and details[1].story.text_files is None
+
+
+def test_the_upfront_pass_explains_high_findings_only_up_to_the_cap():
+    im, findings, layers = model()
+    findings.append(Finding(id="F3", kind="contract", severity="high", title="t", summary="s", nodes=["N1"]))
+    asked = []
+
+    def respond(system, user):
+        if "Explain the risk" in user:
+            asked.append(user)
+            return {"explanation": "uart_send can now return -2 and logger_flush drops it.", "verify_steps": [],
+                    "hypotheses": []}
+        return _respond(lambda u: {"what": "w", "cites": []})(system, user)
+    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(0), upfront_findings=1)
+    assert len(asked) == 1 and "regs.h" in asked[0]                                # F2: the first high finding
+    assert findings[1].explanation == "uart_send can now return -2 and logger_flush drops it."
+    assert findings[0].explanation is None and findings[2].explanation is None    # medium; past the cap
+
+
+def test_ai_titles_naming_node_or_finding_ids_keep_the_template_title():
+    im, findings, layers = model()
+    details = _story_details(1)
+    board = _board(1)
+
+    def respond(system, user):
+        if "Retell this change story" in user:
+            return {"title": "uart_send changes reach N3", "summary": "uart_send can now return -2 and logger_flush drops it.",
+                    "cites": ["N3"]}
+        if "Describe this call flow" in user:
+            return {"what": "logger_flush drops -2.", "title": "F1 drops the new result", "cites": ["N3"]}
+        return _respond(lambda u: {})(system, user)
+    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond), board=board, stories=details, upfront_stories=1)
+    assert details[0].story.title == "template 1" and details[0].story.text_source == "template"
+    assert board.flows[0].title == "template title"
+    assert sb.style_dropped == 2
```

`backend/tests/test_tortoise.py`:

```diff
diff --git a/backend/tests/test_tortoise.py b/backend/tests/test_tortoise.py
index a3c8ac2..1328a94 100644
--- a/backend/tests/test_tortoise.py
+++ b/backend/tests/test_tortoise.py
@@ -24,8 +24,10 @@ class Script:
         user = json.loads(req.content)["messages"][1]["content"]
         if "Give each level" in user:                                                  # layer naming
             return self._reply({"layers": []})
+        if "Explain the risk of this finding" in user:                                 # the up-front pass
+            return self._reply({"explanation": "e", "verify_steps": [], "hypotheses": []})
         if any(k in user for k in ("Summarize the whole change", "Describe this call flow",
-                                   "Retell this change story")):                       # the up-front pass
+                                   "Retell this change story")):
             return self._reply({"summary": "s", "risk": "high", "cites": []} if "Summarize" in user
                                else {"what": "w", "cites": []})
         self.prompts.append(user)
```

`frontend/e2e/ai.spec.ts`:

```diff
diff --git a/frontend/e2e/ai.spec.ts b/frontend/e2e/ai.spec.ts
index 6a64b36..9ed92fc 100644
--- a/frontend/e2e/ai.spec.ts
+++ b/frontend/e2e/ai.spec.ts
@@ -64,9 +64,9 @@ test.describe("with an AI", () => {
     const pill = page.getByRole("button", { name: /^AI \d+\/200$/ });
     await pill.click();
     const usage = page.getByRole("dialog", { name: "AI usage" });
-    await expect(usage).toContainText("By purpose: flow 1 · summary 1");
+    await expect(usage).toContainText("By purpose: finding 1 · flow 1 · summary 1");
     await usage.getByText(/^All calls/).click();                          // the call list loads when opened
-    await expect(usage.locator(".ai-calls tbody tr")).toHaveCount(2);
+    await expect(usage.locator(".ai-calls tbody tr")).toHaveCount(3);
     await usage.getByLabel("New budget").fill("300");
     await usage.getByRole("button", { name: "Raise budget" }).click();
     await expect(page.getByRole("button", { name: /^AI \d+\/300$/ })).toBeVisible();
```

`frontend/e2e/mention.spec.ts`:

```diff
diff --git a/frontend/e2e/mention.spec.ts b/frontend/e2e/mention.spec.ts
index b59e57d..3a2e5b1 100644
--- a/frontend/e2e/mention.spec.ts
+++ b/frontend/e2e/mention.spec.ts
@@ -46,15 +46,15 @@ test.describe("with an AI", () => {
     await startReview(page);
     await page.getByRole("button", { name: /^AI \d+\/200$/ }).click();
     const usage = page.getByRole("dialog", { name: "AI usage" });
-    await usage.getByLabel("New budget").fill("2");                      // the up-front pass used 2: summary and 1 flow
+    await usage.getByLabel("New budget").fill("3");                      // the up-front pass used 3: summary, 1 flow, 1 finding
     await usage.getByRole("button", { name: "Raise budget" }).click();
-    await expect(page.getByRole("button", { name: "AI 2/2" })).toBeVisible();
+    await expect(page.getByRole("button", { name: "AI 3/3" })).toBeVisible();
     await usage.getByRole("button", { name: "Close" }).click();
     const { viewer, box } = await commentOnReturn(page);
     await box.fill("@tortoise does this leak?");
     await viewer.getByRole("button", { name: "Comment", exact: true }).click();
     const reply = viewer.locator(".comment.ai");
-    await expect(reply).toContainText("I couldn't answer: this review has used its 2 AI calls; the owner can raise it.");
+    await expect(reply).toContainText("I couldn't answer: this review has used its 3 AI calls; the owner can raise it.");
     await reply.getByRole("button", { name: "Raise budget" }).click();
     await expect(page.getByRole("dialog", { name: "AI usage" })).toBeVisible();
   });
```

`frontend/e2e/serve-ai.sh`:

```diff
diff --git a/frontend/e2e/serve-ai.sh b/frontend/e2e/serve-ai.sh
index 1633a34..c0f3417 100644
--- a/frontend/e2e/serve-ai.sh
+++ b/frontend/e2e/serve-ai.sh
@@ -10,6 +10,7 @@ llm:
   model: fake
   upfront_flows: 1
   upfront_stories: 0
+  upfront_findings: 1
 YAML
 export TORTOISE_LLM_KEY=fake
 exec $CMD serve --config "$DIR/tortoise.yaml"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_storyboard.py tests/test_ondemand.py tests/test_pipeline.py tests/test_tortoise.py -q`
Run: `cd frontend && npm run build && npx playwright test e2e/ai.spec.ts e2e/mention.spec.ts`

Expected: FAIL — `3 failed, 49 passed, 14 errors` and `TypeError: build_storyboard() got an unexpected keyword argument 'upfront_f...` and `AssertionError: assert ('uart_send changes reach N3' == 'template 1'`; `✓ built in …` and `2 failed` and `6 passed` and (2 failing, first: with an AI › the owner raises the budget from the AI pill; a reviewer sees the usage without the control)

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index fd9f776..3194bf7 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -69,6 +69,7 @@ class LlmConfig(BaseModel):
     concurrency: int = 4           # parallel LLM calls (finding explanations, chapter and flow narratives)
     upfront_flows: int = 3         # flow narratives written when a review runs (the rest on demand)
     upfront_stories: int = 3       # behaviour stories whose title and summary the AI writes when a review runs
+    upfront_findings: int = 5      # high-severity findings the AI explains when a review runs, not on first open
     budget: LlmBudget = Field(default_factory=LlmBudget)
 
 
```

`backend/codetortoise/llm/storyboard.py`:

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index 28a6441..f3dd13b 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -1,6 +1,7 @@
 """Storyboard: deterministic skeleton + optional grounded LLM narrative."""
 from __future__ import annotations
 
+import re
 from collections.abc import Callable
 from concurrent.futures import ThreadPoolExecutor
 from dataclasses import dataclass
@@ -224,6 +225,15 @@ def _styled(text: str, mode: str) -> bool:
     return not check_style(text, mode)
 
 
+IDS = re.compile(r"\b[NF]\d+\b")
+
+
+def _titled(text: str) -> bool:
+    """A headline in the house style that names no node or finding id: titles are read without the ids' meaning
+    (spec 2026-10-04-review-workspace §4.5)."""
+    return _styled(text, "headline") and not IDS.search(text)
+
+
 def finding_job(ctx: AiContext, f: Finding) -> Job:
     impact = ctx.impact
     nodes = [n for n in f.nodes if n in impact.nodes]
@@ -259,7 +269,7 @@ def flow_job(ctx: AiContext, fl: Flow) -> Job:
             return 1
         fl.what, fl.what_source, fl.what_files = out.what.strip(), "llm", ctx.prompt_files(fl.path, fl.findings)
         if 0 < len(out.title.strip()) <= 80:
-            if not _styled(out.title.strip(), "headline"):
+            if not _titled(out.title.strip()):
                 return 1
             fl.title = out.title.strip()
         return 0
@@ -284,7 +294,7 @@ def story_job(ctx: AiContext, d: StoryDetail) -> Job:
         title, summary = out.title.strip(), out.summary.strip()
         if not (title and summary and set(out.cites) & (set(mentioned) | set(st.findings))):
             return 0
-        if not (0 < len(title) <= 80 and _styled(title, "headline") and _styled(summary, "explanation")):
+        if not (0 < len(title) <= 80 and _titled(title) and _styled(summary, "explanation")):
             return 1
         st.title, st.summary, st.text_source = title, summary, "llm"
         st.text_files = ctx.prompt_files(nodes, st.findings)
@@ -333,10 +343,10 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
                      board: Board | None = None, concurrency: int = 1, upfront_flows: int = 3,
                      node_files: dict[str, list[str] | None] | None = None, ledger: Ledger | None = None,
                      rid: int | None = None, stories: list[StoryDetail] | None = None,
-                     upfront_stories: int = 3) -> Storyboard:
+                     upfront_stories: int = 3, upfront_findings: int = 0) -> Storyboard:
     """The deterministic storyboard, then (with an LLM) the up-front pass of spec 2026-10-03 §3: narratives for the
-    first `upfront_flows` flows and titles for the first `upfront_stories` stories given (concurrently), then the
-    change summary. Everything else is explained on demand.
+    first `upfront_flows` flows, titles for the first `upfront_stories` stories given and explanations of the first
+    `upfront_findings` high-severity findings (concurrently), then the change summary. Everything else is explained on demand.
 
     Every call goes through `ledger` when given (as the pipeline). A refused or failed call stops the pass and leaves
     the deterministic text for whatever wasn't written; `llm_error` says why."""
@@ -346,6 +356,7 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
     ctx = AiContext(impact, findings, snippets, max_tokens, node_files)
     jobs = [flow_job(ctx, fl) for fl in (board.flows[:upfront_flows] if board else [])]
     jobs += [story_job(ctx, d) for d in (stories or [])[:upfront_stories]]
+    jobs += [finding_job(ctx, f) for f in [f for f in findings if f.severity == "high"][:upfront_findings]]
     pool = ThreadPoolExecutor(max(1, concurrency), thread_name_prefix="tortoise-llm")
     try:
         for dropped in pool.map(lambda j: run_job(llm, j, ledger, rid), jobs):
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 5ab9ab6..e5b9d6b 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -260,7 +260,8 @@ def run_review(rid: int, svc: Services) -> None:
         sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens,
                               board=b, concurrency=cfg.llm.concurrency, upfront_flows=cfg.llm.upfront_flows,
                               node_files=ctx.get("node_files"), ledger=svc.ledger, rid=rid, stories=top,
-                              upfront_stories=cfg.llm.upfront_stories)
+                              upfront_stories=cfg.llm.upfront_stories,
+                              upfront_findings=cfg.llm.upfront_findings)
         if bs is not None and bs.stories is not None:          # the list shows the retold titles too
             bs.stories.stories = [bs.story_details[s.id].story for s in bs.stories.stories]
         store.put_findings(rid, findings)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_storyboard.py tests/test_ondemand.py tests/test_pipeline.py tests/test_tortoise.py -q`
Run: `cd frontend && npm run build && npx playwright test e2e/ai.spec.ts e2e/mention.spec.ts`

Expected: `66 passed`; `✓ built in …` and `8 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `All checks passed!` and `441 passed, 1 skipped`; `Test Files  21 passed (21)` and `Tests  103 passed (103)` and `✓ built in …` and `55 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/llm/storyboard.py backend/codetortoise/pipeline.py backend/tests/test_ondemand.py backend/tests/test_pipeline.py backend/tests/test_storyboard.py backend/tests/test_tortoise.py frontend/e2e/ai.spec.ts frontend/e2e/mention.spec.ts frontend/e2e/serve-ai.sh
git commit -m "feat(ai): explain high findings up front; titles naming ids keep the template"
```

---

### Task 4: Workspace addresses and per-item memory

Spec §2.3–§2.4. `workspace/address.ts` reads an address (`readAddress(path, query)`: the place from the path,
`flow`, `open` and `tab` from the query, anything unreadable falling back to its default) and writes one back
(`href(base, address)`, defaults left out). `workspace/memory.ts` keeps, per review and for the session, each item's
last address so returning to an item restores its view, flow and detail content. The API client learns `names` and
`neighbours`, and `Story` its `cls`.

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/board/types.ts`
- Create: `frontend/src/workspace/address.ts`
- Create: `frontend/src/workspace/memory.ts`
- Test: `frontend/src/stories/stories.test.ts`
- Test: `frontend/src/workspace/address.test.ts` (new)
- Test: `frontend/src/workspace/memory.test.ts` (new)

**Interfaces:**
- Consumes: the endpoints of Task 2; `Story.cls` (Task 1).
- Produces: `type Place = {kind:"whole"} | {kind:"story"; sid; view:"steps"|"graph"} | {kind:"finding"; fid} | {kind:"cl"; cl:number} | {kind:"cluster"; cid} | {kind:"unknown"; path}`;
  `type Open = {node} | {file; line:number|null} | null`; `type Tab = "diff"|"neighbours"`; `interface Address {place; flow:number|null; open; tab}`;
  `readAddress(path, q): Address`, `href(base, a): string`, `placeKey(p)`, `samePlace(a, b)`, `at(place, rest?)`;
  `type Memory`, `remember(m, a)`, `recall(m, place)`, `loadMemory(rid)`, `saveMemory(rid, m)`;
  `api.names(id): Promise<Names>`, `api.neighbours(id, nid, limit=20): Promise<Neighbours>`; types `NodeName`, `Names`, `Neighbour`, `Neighbours`; `Story.cls: number[]`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/stories/stories.test.ts`:

```diff
diff --git a/frontend/src/stories/stories.test.ts b/frontend/src/stories/stories.test.ts
index 4131b42..4f1f35b 100644
--- a/frontend/src/stories/stories.test.ts
+++ b/frontend/src/stories/stories.test.ts
@@ -4,7 +4,7 @@ import { countLine, graphFocus, groupSites, sections, stepStory, wholeGraph } fr
 
 const story = (id: string, kind: Story["kind"], extra: Partial<Story> = {}): Story => ({
   id, kind, title: id, summary: "", text_source: "template", risk: null, counts: {}, nodes: [], flows: [], findings: [],
-  board: null, sub: null, subs: [], collapsed: false, ...extra,
+  board: null, cls: [], sub: null, subs: [], collapsed: false, ...extra,
 });
 const set = (stories: Story[]): StorySet => ({ summary: "", stories, node_story: {}, flow_story: {}, finding_story: {} });
 const site = (path: string, line: number, test = false): StorySite => ({
```

`frontend/src/workspace/address.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { type Address, href, placeKey, readAddress, samePlace } from "./address";

const q = (s: string) => new URLSearchParams(s);

describe("readAddress", () => {
  it("reads each kind of place", () => {
    expect(readAddress("", q("")).place).toEqual({ kind: "whole" });
    expect(readAddress("/s/S1", q("")).place).toEqual({ kind: "story", sid: "S1", view: "steps" });
    expect(readAddress("/s/S1", q("view=graph")).place).toEqual({ kind: "story", sid: "S1", view: "graph" });
    expect(readAddress("/f/F2", q("")).place).toEqual({ kind: "finding", fid: "F2" });
    expect(readAddress("/cl/101", q("")).place).toEqual({ kind: "cl", cl: 101 });
    expect(readAddress("/c/C3/", q("")).place).toEqual({ kind: "cluster", cid: "C3" });
  });

  it("reads the flow, what the detail panel shows and its tab", () => {
    const a = readAddress("/s/S1", q("view=graph&flow=2&open=N9&tab=neighbours"));
    expect([a.flow, a.open, a.tab]).toEqual([2, { node: "N9" }, "neighbours"]);
    expect(readAddress("", q("open=file://fixture/driver/uart.c:17")).open).toEqual({ file: "//fixture/driver/uart.c", line: 17 });
    expect(readAddress("", q("open=file://fixture/driver/uart.c")).open).toEqual({ file: "//fixture/driver/uart.c", line: null });
  });

  it("falls back on anything it cannot read", () => {
    const a = readAddress("/nowhere/x", q("flow=0&tab=sideways&view=map&open=file:"));
    expect(a).toEqual({ place: { kind: "unknown", path: "/nowhere/x" }, flow: null, open: null, tab: "diff" });
    expect(readAddress("/cl/abc", q("")).place).toEqual({ kind: "unknown", path: "/cl/abc" });
  });
});

describe("href", () => {
  it("writes an address back, leaving out defaults", () => {
    const a: Address = { place: { kind: "story", sid: "S1", view: "graph" }, flow: 2, open: { node: "N9" }, tab: "neighbours" };
    expect(href("/w/7", a)).toBe("/w/7/s/S1?view=graph&flow=2&open=N9&tab=neighbours");
    expect(href("/w/7", { place: { kind: "whole" }, flow: null, open: null, tab: "diff" })).toBe("/w/7");
    expect(href("/w/7", { place: { kind: "cl", cl: 101 }, flow: null, open: { file: "//d/a.c", line: 4 }, tab: "diff" }))
      .toBe("/w/7/cl/101?open=file%3A%2F%2Fd%2Fa.c%3A4");
  });

  it("round-trips every place", () => {
    for (const path of ["", "/s/S2", "/f/F1", "/cl/102", "/c/C1"]) {
      const a = readAddress(path, q("flow=3&open=file://d/x.h"));
      const [p, s] = href("/r/1", a).slice("/r/1".length).split("?");
      expect(readAddress(p, q(s ?? ""))).toEqual(a);
    }
  });
});

describe("places", () => {
  it("have a key per item and compare by item, not view", () => {
    expect(placeKey({ kind: "story", sid: "S1", view: "graph" })).toBe("s:S1");
    expect(placeKey({ kind: "whole" })).toBe("whole");
    expect(samePlace({ kind: "story", sid: "S1", view: "graph" }, { kind: "story", sid: "S1", view: "steps" })).toBe(true);
    expect(samePlace({ kind: "finding", fid: "F1" }, { kind: "finding", fid: "F2" })).toBe(false);
  });
});
```

`frontend/src/workspace/memory.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Address } from "./address";
import { recall, remember } from "./memory";

const story: Address = { place: { kind: "story", sid: "S1", view: "graph" }, flow: 2, open: { node: "N9" }, tab: "neighbours" };

describe("per-item memory", () => {
  it("returns to an item at its last view, flow and detail content", () => {
    const m = remember({}, story);
    expect(recall(m, { kind: "story", sid: "S1", view: "steps" })).toEqual(story);
  });

  it("opens an item it has not seen at its defaults", () => {
    expect(recall({}, { kind: "finding", fid: "F2" })).toEqual({ place: { kind: "finding", fid: "F2" }, flow: null, open: null, tab: "diff" });
  });

  it("keeps each item apart and the latest visit of each", () => {
    let m = remember({}, story);
    m = remember(m, { place: { kind: "finding", fid: "F2" }, flow: null, open: { file: "//d/a.c", line: 3 }, tab: "diff" });
    m = remember(m, { ...story, flow: 1, open: null });
    expect(recall(m, { kind: "story", sid: "S1", view: "steps" })).toEqual({ ...story, flow: 1, open: null });
    expect(recall(m, { kind: "finding", fid: "F2" }).open).toEqual({ file: "//d/a.c", line: 3 });
  });

  it("forgets nothing it was not told and ignores unknown places", () => {
    const m = remember({}, { place: { kind: "unknown", path: "/x" }, flow: 1, open: null, tab: "diff" });
    expect(m).toEqual({});
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/workspace src/stories`

Expected: FAIL — `Test Files  2 failed | 1 passed (3)` and `Tests  6 passed (6)` and `Cannot find module './address' imported from src/workspace/address.test.t` and `Cannot find module './memory' imported from src/workspace/memory.test.ts`

- [ ] **Step 3: Implement**

`frontend/src/api.ts`:

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index f9c8a23..bb12e0e 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -16,7 +16,14 @@ export interface Cited { text: string; cites: string[]; verified: boolean }
 export interface Finding {
   id: string; kind: string; severity: Severity; title: string; nodes: string[]; evidence: Evidence[]; summary: string;
   explanation: string | null; verify_steps: string[]; hypotheses: Cited[]; state: "open" | "ack" | "dismissed";
+  /** Depot paths behind the finding (null: unknown). */
+  files: string[] | null;
 }
+/** A node's name for the workspace (review workspace §4.2): the reader sees names, never node ids. */
+export interface NodeName { label: string; kind: string; path: string | null; line: number | null; story: string | null }
+export type Names = Record<string, NodeName>;
+export interface Neighbour extends NodeName { id: string; changed: boolean; test: boolean }
+export interface Neighbours { node: Neighbour; callers: { total: number; items: Neighbour[] }; callees: { total: number; items: Neighbour[] } }
 export interface PerCl { cl: number; before: string; after: string }
 export interface FileChange { depot: string; local: string; action: string; before: string; after: string; base_rev: string | null; per_cl: PerCl[] }
 export type AnchorKind = "line" | "function" | "finding" | "chapter" | "review";
@@ -88,6 +95,9 @@ export const api = {
     call<{ cluster: string | null; story?: string | null }>("GET", `/api/reviews/${id}/locate?${new URLSearchParams(q)}`),
   source: (id: number, path: string, side: "before" | "after" = "after") =>
     call<SourceText>("GET", `/api/reviews/${id}/source?${new URLSearchParams({ path, side })}`),
+  names: (id: number) => call<Names>("GET", `/api/reviews/${id}/names`),
+  neighbours: (id: number, nid: string, limit = 20) =>
+    call<Neighbours>("GET", `/api/reviews/${id}/nodes/${encodeURIComponent(nid)}/neighbours?limit=${limit}`),
   findings: (id: number) => call<Finding[]>("GET", `/api/reviews/${id}/findings`),
   setFindingState: (id: number, fid: string, state: Finding["state"]) =>
     call("PATCH", `/api/reviews/${id}/findings/${fid}`, { state }),
```

`frontend/src/board/types.ts`:

```diff
diff --git a/frontend/src/board/types.ts b/frontend/src/board/types.ts
index 39731e0..13ac94e 100644
--- a/frontend/src/board/types.ts
+++ b/frontend/src/board/types.ts
@@ -62,6 +62,8 @@ export interface Story {
   text_files?: string[] | null;
   counts: Partial<Record<"flows" | "findings" | "functions" | "files" | "sites" | "test_sites", number>>;
   nodes: string[]; flows: string[]; findings: string[]; board: string | null;
+  /** The changelists of the files holding its code (review workspace §4.1; [] for stories stored before them). */
+  cls: number[];
   sub: [string, string] | null; subs: [string, string][]; collapsed: boolean;
 }
 export interface StoryRef { node: string; label: string; story: string | null }
```

`frontend/src/workspace/address.ts`:

```ts
/** Workspace addresses (spec 2026-10-04-review-workspace §2.3): every place has one, so reload, shared links and Back
 * work. Ids appear here and nowhere in visible text. */

export type Place =
  | { kind: "whole" }
  | { kind: "story"; sid: string; view: "steps" | "graph" }
  | { kind: "finding"; fid: string }
  | { kind: "cl"; cl: number }
  | { kind: "cluster"; cid: string }
  | { kind: "unknown"; path: string };

/** What the detail panel shows: a node's code, or a file's diff (at a line). */
export type Open = { node: string } | { file: string; line: number | null } | null;
export type Tab = "diff" | "neighbours";

export interface Address {
  place: Place;
  /** The selected flow, 1-based (null: the first). */
  flow: number | null;
  open: Open;
  tab: Tab;
}

function readPlace(path: string, q: URLSearchParams): Place {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length) return { kind: "whole" };
  const [kind, id, ...rest] = parts;
  if (!id || rest.length) return { kind: "unknown", path };
  if (kind === "s") return { kind: "story", sid: id, view: q.get("view") === "graph" ? "graph" : "steps" };
  if (kind === "f") return { kind: "finding", fid: id };
  if (kind === "cl" && /^\d+$/.test(id)) return { kind: "cl", cl: Number(id) };
  if (kind === "c") return { kind: "cluster", cid: id };
  return { kind: "unknown", path };
}

function readOpen(raw: string | null): Open {
  if (!raw) return null;
  if (!raw.startsWith("file:")) return { node: raw };
  const m = /^(.+?)(?::(\d+))?$/.exec(raw.slice(5));
  return m ? { file: m[1], line: m[2] ? Number(m[2]) : null } : null;
}

/** The address of `path` (what follows `/r/:id`) and its query. */
export function readAddress(path: string, q: URLSearchParams): Address {
  const flow = Number(q.get("flow"));
  return {
    place: readPlace(path, q),
    flow: Number.isInteger(flow) && flow > 0 ? flow : null,
    open: readOpen(q.get("open")),
    tab: q.get("tab") === "neighbours" ? "neighbours" : "diff",
  };
}

const placePath = (p: Place): string =>
  p.kind === "story" ? `/s/${p.sid}` : p.kind === "finding" ? `/f/${p.fid}` : p.kind === "cl" ? `/cl/${p.cl}`
    : p.kind === "cluster" ? `/c/${p.cid}` : p.kind === "unknown" ? p.path : "";

/** The link to `a` under `base` ("/r/7"), defaults left out. */
export function href(base: string, a: Address): string {
  const q = new URLSearchParams();
  if (a.place.kind === "story" && a.place.view === "graph") q.set("view", "graph");
  if (a.flow) q.set("flow", String(a.flow));
  if (a.open) q.set("open", "node" in a.open ? a.open.node : `file:${a.open.file}${a.open.line ? `:${a.open.line}` : ""}`);
  if (a.tab !== "diff") q.set("tab", a.tab);
  return `${base}${placePath(a.place)}${q.size ? `?${q}` : ""}`;
}

/** One key per item, whatever its view: "s:S1", "f:F2", "whole". */
export const placeKey = (p: Place): string =>
  p.kind === "story" ? `s:${p.sid}` : p.kind === "finding" ? `f:${p.fid}` : p.kind === "cl" ? `cl:${p.cl}`
    : p.kind === "cluster" ? `c:${p.cid}` : p.kind === "unknown" ? `?:${p.path}` : "whole";

export const samePlace = (a: Place, b: Place) => placeKey(a) === placeKey(b);

export const at = (place: Place, rest: Partial<Omit<Address, "place">> = {}): Address =>
  ({ place, flow: null, open: null, tab: "diff", ...rest });
```

`frontend/src/workspace/memory.ts`:

```ts
/** Per-item memory for the session (spec 2026-10-04-review-workspace §2.4): each item remembers its last view, flow
 * and detail content, so going back to it from the rail returns to where the reader was. */
import { type Address, at, type Place, placeKey } from "./address";

export type Memory = Record<string, Address>;

export function remember(m: Memory, a: Address): Memory {
  return a.place.kind === "unknown" ? m : { ...m, [placeKey(a.place)]: a };
}

export function recall(m: Memory, place: Place): Address {
  return m[placeKey(place)] ?? at(place);
}

const key = (reviewId: number) => `ct.ws.${reviewId}.memory`;

/** Session storage may be missing or throw: the workspace then just forgets. */
export function loadMemory(reviewId: number): Memory {
  try {
    const v = JSON.parse(window.sessionStorage.getItem(key(reviewId)) ?? "{}");
    return v && typeof v === "object" && !Array.isArray(v) ? v as Memory : {};
  } catch {
    return {};
  }
}

export function saveMemory(reviewId: number, m: Memory): void {
  try {
    window.sessionStorage.setItem(key(reviewId), JSON.stringify(m));
  } catch {
    /* private mode or blocked storage: items open at their defaults */
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/workspace src/stories`

Expected: `Test Files  3 passed (3)` and `Tests  16 passed (16)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  23 passed (23)` and `Tests  113 passed (113)` and `✓ built in …` and `55 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.ts frontend/src/board/types.ts frontend/src/stories/stories.test.ts frontend/src/workspace/address.test.ts frontend/src/workspace/address.ts frontend/src/workspace/memory.test.ts frontend/src/workspace/memory.ts
git commit -m "feat(ui): workspace addresses and per-item memory; names and neighbours in the API client"
```

---

### Task 5: The rail's data, the breadcrumb and names in place of ids

Spec §2.2, §2.4. Three pure modules the shell uses. `rail.ts`: the CLs the stories come from, the stories a CL
filter lights (null when no filter), findings grouped by severity. `crumbs.ts`: the breadcrumb for each kind of place
(`Review › Stories › S1 … › Graph`; section crumbs link to `#stories`, `#findings`, `#changeset`, `#map`; "Not found"
for a missing item). `names.ts`: text split into parts so ids show as names (`N12` → its label, `F3` → a finding
link, backticks → code, an unknown id → "a function").

**Files:**
- Create: `frontend/src/workspace/crumbs.ts`
- Create: `frontend/src/workspace/names.ts`
- Create: `frontend/src/workspace/rail.ts`
- Test: `frontend/src/workspace/crumbs.test.ts` (new)
- Test: `frontend/src/workspace/names.test.ts` (new)
- Test: `frontend/src/workspace/rail.test.ts` (new)

**Interfaces:**
- Consumes: `StorySet`, `Finding`, `Names` (Task 4), `Place` (Task 4).
- Produces: `storyCls(ss): number[]`, `litStories(ss, cl): Set<string> | null`, `SEVERITIES`, `bySeverity(findings)`;
  `interface Crumb {label; to:string|null; handle?}`, `interface CrumbContext {base; title; stories; findings; cls; clusters}`, `short(text, n=46)`, `crumbs(place, ctx): Crumb[]`;
  `type Part = {text} | {code} | {node; label} | {finding}`, `nameParts(text, names): Part[]`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/workspace/crumbs.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Finding } from "../api";
import type { Story } from "../board/types";
import { type CrumbContext, crumbs, short } from "./crumbs";

const ctx: CrumbContext = {
  base: "/r/7", title: "Review 7",
  stories: [{ id: "S1", title: "`frame_pop` writes `pool->free` from two threads at once" } as Story],
  findings: [{ id: "F2", title: "uart_send: new return value(s) -2" } as Finding],
  cls: [{ cl: 101, description: "uart: count tx stats\n\nlonger text" }],
  clusters: [{ id: "C1", name: "driver/uart" }],
};

describe("the breadcrumb", () => {
  it("names the review alone at home", () => {
    expect(crumbs({ kind: "whole" }, ctx)).toEqual([{ label: "Review 7", to: null }]);
  });

  it("goes up from a story's graph to its steps, the stories and the review", () => {
    expect(crumbs({ kind: "story", sid: "S1", view: "graph" }, ctx)).toEqual([
      { label: "Review 7", to: "/r/7" },
      { label: "Stories", to: "/r/7#stories" },
      { label: "frame_pop writes pool->free from two threads…", handle: "S1", to: "/r/7/s/S1" },
      { label: "Graph", to: null },
    ]);
    expect(crumbs({ kind: "story", sid: "S1", view: "steps" }, ctx).at(-1)).toEqual(
      { label: "frame_pop writes pool->free from two threads…", handle: "S1", to: null });
  });

  it("names findings, changelists and clusters under their sections", () => {
    expect(crumbs({ kind: "finding", fid: "F2" }, ctx).slice(1)).toEqual([
      { label: "Findings", to: "/r/7#findings" }, { label: "uart_send: new return value(s) -2", handle: "F2", to: null }]);
    expect(crumbs({ kind: "cl", cl: 101 }, ctx).slice(1)).toEqual([
      { label: "Change set", to: "/r/7#changeset" }, { label: "CL 101 · uart: count tx stats", to: null }]);
    expect(crumbs({ kind: "cluster", cid: "C1" }, ctx).slice(1)).toEqual([
      { label: "Map", to: "/r/7#map" }, { label: "driver/uart", to: null }]);
  });

  it("says when the item does not exist", () => {
    expect(crumbs({ kind: "story", sid: "S9", view: "steps" }, ctx).at(-1)).toEqual({ label: "Not found", to: null });
    expect(crumbs({ kind: "unknown", path: "/x" }, ctx).at(-1)).toEqual({ label: "Not found", to: null });
  });
});

describe("short", () => {
  it("drops backticks and cuts long text at a word", () => {
    expect(short("`a` b")).toBe("a b");
    expect(short("one two three four", 10)).toBe("one two…");
  });
});
```

`frontend/src/workspace/names.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Names } from "../api";
import { nameParts } from "./names";

const names: Names = {
  N9: { label: "uart_send", kind: "function", path: "//fixture/driver/uart.c", line: 11, story: "S1" },
  N16: { label: "Uart::errors", kind: "field", path: null, line: null, story: null },
};

describe("nameParts", () => {
  it("shows node ids as their names and finding ids as findings", () => {
    expect(nameParts("N9 writes N16; see F2.", names)).toEqual([
      { node: "N9", label: "uart_send" }, { text: " writes " }, { node: "N16", label: "Uart::errors" }, { text: "; see " },
      { finding: "F2" }, { text: "." }]);
  });

  it("keeps backticked code, naming ids inside it too", () => {
    expect(nameParts("`uart_send` (N9) and `N16`", names)).toEqual([
      { code: "uart_send" }, { text: " (" }, { node: "N9", label: "uart_send" }, { text: ") and " }, { node: "N16", label: "Uart::errors" }]);
  });

  it("never shows an id it cannot name", () => {
    expect(nameParts("N404 is gone", names)).toEqual([{ node: "N404", label: "a function" }, { text: " is gone" }]);
  });

  it("leaves words that only look like ids alone", () => {
    expect(nameParts("N12x and FN9", names)).toEqual([{ text: "N12x and FN9" }]);
  });
});
```

`frontend/src/workspace/rail.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Finding } from "../api";
import type { Story, StorySet } from "../board/types";
import { bySeverity, litStories, storyCls } from "./rail";

const story = (id: string, cls: number[]): Story => ({
  id, kind: "behaviour", title: id, summary: "", text_source: "template", risk: null, counts: {}, nodes: [], flows: [],
  findings: [], board: null, cls, sub: null, subs: [], collapsed: false,
});
const set = (stories: Story[]): StorySet => ({ summary: "", stories, node_story: {}, flow_story: {}, finding_story: {} });
const finding = (id: string, severity: Finding["severity"]): Finding => ({
  id, kind: "contract", severity, title: id, nodes: [], evidence: [], summary: "", explanation: null, verify_steps: [],
  hypotheses: [], state: "open", files: null,
});

describe("the rail's change set", () => {
  it("counts the CLs the stories come from", () => {
    expect(storyCls(set([story("S1", [101]), story("S2", [102, 101]), story("S3", [])]))).toEqual([101, 102]);
  });

  it("lights the stories drawn from the filtered CL; no filter lights none apart", () => {
    const ss = set([story("S1", [101]), story("S2", [102, 101]), story("S3", [102])]);
    expect(litStories(ss, 101)).toEqual(new Set(["S1", "S2"]));
    expect(litStories(ss, null)).toBeNull();
    expect(litStories(ss, 999)).toEqual(new Set());
  });
});

describe("the rail's findings", () => {
  it("group by severity, highest first, leaving out empty groups", () => {
    const g = bySeverity([finding("F1", "low"), finding("F2", "high"), finding("F3", "low"), finding("F4", "info")]);
    expect(g.map((x) => [x.severity, x.findings.map((f) => f.id)])).toEqual([["high", ["F2"]], ["low", ["F1", "F3"]], ["info", ["F4"]]]);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/workspace`

Expected: FAIL — `Test Files  3 failed | 2 passed (5)` and `Tests  10 passed (10)` and `Cannot find module './crumbs' imported from src/workspace/crumbs.test.ts` and `Cannot find module './names' imported from src/workspace/names.test.ts`

- [ ] **Step 3: Implement**

`frontend/src/workspace/crumbs.ts`:

```ts
/** The centre's breadcrumb (spec 2026-10-04-review-workspace §2.4): every part but the current one is a link up. */
import type { Finding } from "../api";
import type { Story } from "../board/types";
import { href, type Place } from "./address";

export interface Crumb { label: string; to: string | null; handle?: string }
export interface CrumbContext {
  base: string;
  title: string;
  stories: Pick<Story, "id" | "title">[];
  findings: Pick<Finding, "id" | "title">[];
  cls: { cl: number; description: string | null }[];
  clusters: { id: string; name: string }[];
}

/** `text` without backticks, cut at a word to fit `n` characters with its ellipsis. */
export function short(text: string, n = 46): string {
  const t = text.replace(/`/g, "").trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n).lastIndexOf(" ");
  return `${t.slice(0, cut > 0 ? cut : n - 1)}…`;
}

const MISSING: Crumb = { label: "Not found", to: null };

export function crumbs(place: Place, c: CrumbContext): Crumb[] {
  if (place.kind === "whole") return [{ label: c.title, to: null }];
  const home = { label: c.title, to: c.base };
  const section = (label: string, anchor: string): Crumb => ({ label, to: `${c.base}#${anchor}` });
  switch (place.kind) {
    case "story": {
      const st = c.stories.find((s) => s.id === place.sid);
      if (!st) return [home, section("Stories", "stories"), MISSING];
      const graph = place.view === "graph";
      const me: Crumb = { label: short(st.title), handle: st.id,
                          to: graph ? href(c.base, { place: { ...place, view: "steps" }, flow: null, open: null, tab: "diff" }) : null };
      return [home, section("Stories", "stories"), me, ...(graph ? [{ label: "Graph", to: null }] : [])];
    }
    case "finding": {
      const f = c.findings.find((x) => x.id === place.fid);
      return [home, section("Findings", "findings"), f ? { label: short(f.title), handle: f.id, to: null } : MISSING];
    }
    case "cl": {
      const cl = c.cls.find((x) => x.cl === place.cl);
      const first = cl?.description?.trim().split("\n")[0];
      return [home, section("Change set", "changeset"),
              cl ? { label: short(`CL ${cl.cl}${first ? ` · ${first}` : ""}`), to: null } : MISSING];
    }
    case "cluster": {
      const k = c.clusters.find((x) => x.id === place.cid);
      return [home, section("Map", "map"), k ? { label: short(k.name), to: null } : MISSING];
    }
    case "unknown":
      return [home, MISSING];
  }
}
```

`frontend/src/workspace/names.ts`:

```ts
/** Text with node ids shown as names (spec 2026-10-04-review-workspace §2.4): AI and template text cite `N4279`; the
 * reader sees `frame_pop`, linked to its code. */
import type { Names } from "../api";

export type Part = { text: string } | { code: string } | { node: string; label: string } | { finding: string };

const ID = /\b([NF]\d+)\b/;

function ids(segment: string, names: Names, plain: (s: string) => Part): Part[] {
  return segment.split(ID).flatMap((p, i): Part[] => {
    if (i % 2 === 0) return p ? [plain(p)] : [];
    return p.startsWith("N") ? [{ node: p, label: names[p]?.label ?? "a function" }] : [{ finding: p }];
  });
}

export function nameParts(text: string, names: Names): Part[] {
  return text.split("`").flatMap((seg, i) => ids(seg, names, i % 2 ? (code) => ({ code }) : (t) => ({ text: t })));
}
```

`frontend/src/workspace/rail.ts`:

```ts
/** The rail's derived data (spec 2026-10-04-review-workspace §2.2): the stories shown as drawn from the change set. */
import type { Finding, Severity } from "../api";
import type { StorySet } from "../board/types";

/** The CLs the stories draw from, for "Stories (from N CLs)". */
export function storyCls(ss: StorySet): number[] {
  return [...new Set(ss.stories.flatMap((s) => s.cls))].sort((a, b) => a - b);
}

/** The stories a CL filter lights (the rest are dimmed); null when no filter is set. */
export function litStories(ss: StorySet, cl: number | null): Set<string> | null {
  return cl === null ? null : new Set(ss.stories.filter((s) => s.cls.includes(cl)).map((s) => s.id));
}

export const SEVERITIES: Severity[] = ["high", "medium", "low", "info"];

export function bySeverity(findings: Finding[]): { severity: Severity; findings: Finding[] }[] {
  return SEVERITIES.map((severity) => ({ severity, findings: findings.filter((f) => f.severity === severity) }))
    .filter((g) => g.findings.length);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/workspace`

Expected: `Test Files  5 passed (5)` and `Tests  22 passed (22)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  26 passed (26)` and `Tests  125 passed (125)` and `✓ built in …` and `55 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/workspace/crumbs.test.ts frontend/src/workspace/crumbs.ts frontend/src/workspace/names.test.ts frontend/src/workspace/names.ts frontend/src/workspace/rail.test.ts frontend/src/workspace/rail.ts
git commit -m "feat(ui): the rail's derived data, the breadcrumb and names in place of node ids"
```

---

### Task 6: The workspace shell at /w/:id

Spec §2.1–§2.4, §6. The workspace is built at `/w/:id` while `/r/:id` keeps today's UI. `useReview` (moved out
of `pages/Review.tsx`) loads the review's data, progress events and AI state. `Workspace` reads the address, records
per-item memory and lays out the head (title, risk, status, AI pill, Re-run, drift, stage notes, ☰), the `Rail`, the
centre with its breadcrumb (`Crumbs`; a `PhoneBar` on phones) and, from Task 8, the detail panel. The rail's sections
(Change set with CL filter dots, Stories with CL chips, Findings by severity, Files) collapse and remember their
state; the rail is resizable. `NameText` renders `nameParts` with labelled links. A missing item says so with a link
to the whole change. Tablet: the rail is a drawer; phone: three levels, the rail being home.

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/workspace/Crumbs.tsx`
- Create: `frontend/src/workspace/NameText.tsx`
- Create: `frontend/src/workspace/Rail.tsx`
- Create: `frontend/src/workspace/Workspace.tsx`
- Create: `frontend/src/workspace/context.ts`
- Create: `frontend/src/workspace/media.ts`
- Create: `frontend/src/workspace/useReview.ts`
- Create: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/helpers.ts`
- Test: `frontend/e2e/workspace.spec.ts` (new)

**Interfaces:**
- Consumes: Tasks 4–5; `board/useSources`, `Resizer`, `AiPill`, `Stages`, `lib/ai`.
- Produces: `useReview(id)` returning `{id, detail, board, overview, stories, findings, files, comments, names, about, reload, error, ready, ai, story(sid), loadDetail, loadComments, loadFindings}` and `type ReviewData`;
  `useScreen(): "phone"|"tablet"|"desktop"`; `interface Ws {base; data; addr; screen; sources; link(a); go(a, replace?); item(place); opened(open, tab?)}`, `WsContext`, `useWs()`;
  `NameText({text})`, `Ticks({text})`; `Crumbs({items})`, `PhoneBar({back, title, handle?})`; `Rail({show, onPick})`; `Workspace`, `base(id)`, `Missing({what})`;
  e2e helpers `startWorkspace(page): Promise<string>`, `expectNoNodeIds(page)`, `expectNamed(page)`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/helpers.ts`:

```diff
diff --git a/frontend/e2e/helpers.ts b/frontend/e2e/helpers.ts
index d83b031..e042e35 100644
--- a/frontend/e2e/helpers.ts
+++ b/frontend/e2e/helpers.ts
@@ -22,3 +22,26 @@ export async function startReview(page: Page) {
   // desktop shows the canvas; phones open on the flow reader (spec §13)
   await expect(page.locator(".bd-node, .ph-step").first()).toBeVisible({ timeout: 60_000 });
 }
+
+/** As startStories, then open the same review in the workspace (spec 2026-10-04-review-workspace; `/w/` while built). */
+export async function startWorkspace(page: Page): Promise<string> {
+  await startStories(page);
+  const id = page.url().match(/\/r\/(\d+)/)![1];
+  await page.goto(`/w/${id}`);
+  await expect(page.locator(".ws-rail")).toBeVisible({ timeout: 60_000 });
+  return `/w/${id}`;
+}
+
+/** No node id is ever shown (spec §8): visible text never matches N<digits>. */
+export async function expectNoNodeIds(page: Page) {
+  const text = await page.locator("main").innerText();
+  expect(text.match(/\bN\d+\b/g) ?? []).toEqual([]);
+}
+
+/** Every link and button on the page has an accessible name (spec §8). */
+export async function expectNamed(page: Page) {
+  const unnamed = await page.locator("main a, main button, main [role=button]").evaluateAll((els) =>
+    els.filter((e) => !(e.getAttribute("aria-label") || e.textContent?.trim() || e.getAttribute("title")))
+       .map((e) => e.outerHTML.slice(0, 120)));
+  expect(unnamed).toEqual([]);
+}
```

`frontend/e2e/workspace.spec.ts`:

```ts
import { devices, expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";

/** The workspace shell (spec 2026-10-04-review-workspace §2): rail, breadcrumb, addresses, phone levels. */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the rail lists the review, its CLs, the stories drawn from them, findings and files", async ({ page }) => {
    const base = await startWorkspace(page);
    const rail = page.locator(".ws-rail");
    await expect(rail.locator(".ws-sec h2")).toHaveText([/Change set \(2 CLs\)/, /Stories \(from 2 CLs\)/, /Findings \(6\)/, /Files \(4\)/]);
    await expect(rail.getByRole("link", { name: "Go to the whole change" })).toHaveAttribute("aria-current", "page");
    const home = (await rail.locator(".ws-home").boundingBox())!, first = (await rail.locator(".ws-sec-t").first().boundingBox())!;
    expect(first.y - (home.y + home.height)).toBeLessThan(12);               // sections follow on: the grip takes no room
    const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
    await expect(s1.locator(".ws-chip")).toHaveText(["CL 101"]);

    // the CL filter lights the stories drawn from it and dims the rest; again clears it
    await rail.getByRole("button", { name: "Highlight the stories drawn from CL 102" }).click();
    await expect(s1).toHaveClass(/\bdim\b/);
    await expect(rail.getByRole("link", { name: /^Go to story S2/ })).not.toHaveClass(/\bdim\b/);
    await rail.getByRole("button", { name: "Show every story" }).click();
    await expect(s1).not.toHaveClass(/\bdim\b/);

    await s1.click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expect(s1).toHaveAttribute("aria-current", "page");
    const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(crumbs).toContainText("Stories");
    await expect(crumbs.locator("[aria-current=page]")).toContainText("uart_send now writes Uart::errors");
    await crumbs.getByRole("link", { name: "Go to Stories" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}#stories$`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("an address to something that does not exist says so", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}/s/S9`);
    await expect(page.locator(".ws-centre .banner")).toContainText("Story S9 isn't in this review.");
    await page.getByRole("link", { name: "Whole change" }).last().click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
  });
});

test.describe("tablet", () => {
  test.use({ viewport: { width: 900, height: 1000 } });

  test("the rail is a drawer behind ☰", async ({ page }) => {
    await startWorkspace(page);
    const rail = page.locator(".ws-rail");
    await expect(rail).not.toBeInViewport();
    await page.getByRole("button", { name: "Review contents" }).click();
    await expect(rail).toBeInViewport();
    await rail.getByRole("link", { name: /^Go to story S2/ }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await expect(rail).not.toBeInViewport();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the rail is home; an item's top bar names where it came from", async ({ page }) => {
    const base = await startWorkspace(page);
    await expect(page.locator(".topbar")).toBeHidden();
    await expect(page.locator(".ws-centre")).toHaveCount(0);
    await page.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.locator(".ws-rail")).toHaveCount(0);
    const bar = page.locator(".ws-phonebar");
    await expect(bar).toContainText("‹ Stories");
    await expect(bar).toContainText("S1");
    await bar.getByRole("link", { name: "Back to Stories" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}#stories$`));
    await expect(page.locator(".ws-rail")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace.spec.ts`

Expected: FAIL — `✓ built in …` and `4 failed` and (4 failing, first: desktop › the rail lists the review, its CLs, the stories drawn from them, findings and files)

- [ ] **Step 3: Implement**

`frontend/src/App.tsx`:

```diff
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index d02b7ea..97f9b0a 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -8,6 +8,7 @@ import Health from "./pages/Health";
 import Login from "./pages/Login";
 import Review from "./pages/Review";
 import Reviews from "./pages/Reviews";
+import Workspace from "./workspace/Workspace";
 
 const MeContext = createContext<Me | null>(null);
 export const useMe = () => useContext(MeContext);
@@ -53,6 +54,7 @@ export default function App() {
         <Route path="/new" element={<Navigate to="/" replace />} />
         <Route path="/health" element={<Health />} />
         <Route path="/r/:id/*" element={<Review />} />
+        <Route path="/w/:id/*" element={<Workspace />} />
         <Route path="*" element={<Navigate to="/" replace />} />
       </Routes>
     </MeContext.Provider>
```

`frontend/src/workspace/Crumbs.tsx`:

```tsx
import { Fragment } from "react";
import { Link } from "react-router-dom";
import type { Crumb } from "./crumbs";

/** The centre's breadcrumb: `Review 7 › Stories › S1 frame_pop writes… › Graph`, every part above the current a link. */
export default function Crumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="ws-crumbs" aria-label="Breadcrumb">
      {items.map((c, i) => (
        <Fragment key={i}>
          {i > 0 && <span className="sep" aria-hidden> › </span>}
          {c.to ? <Link to={c.to} title={`Go to ${c.label}`} aria-label={`Go to ${c.label}`}>{c.label}{c.handle && <span className="ws-handle">{c.handle}</span>}</Link>
            : <span aria-current="page">{c.label}{c.handle && <span className="ws-handle">{c.handle}</span>}</span>}
        </Fragment>
      ))}
    </nav>
  );
}

/** A phone page's top bar (§2.1): where it came from and what it is, "‹ Stories · S1 frame_pop writes…". */
export function PhoneBar({ back, title, handle }: { back: Crumb; title: string; handle?: string }) {
  return (
    <div className="ws-phonebar">
      <Link to={back.to ?? "."} aria-label={`Back to ${back.label}`} title={`Back to ${back.label}`}>‹ {back.label}</Link>
      <span className="sep" aria-hidden>·</span>
      <b>{handle && <span className="ws-handle">{handle}</span>}{title}</b>
    </div>
  );
}
```

`frontend/src/workspace/NameText.tsx`:

```tsx
import { Fragment } from "react";
import { Link } from "react-router-dom";
import { useWs } from "./context";
import { short } from "./crumbs";
import { nameParts } from "./names";

/** Text with node ids shown as names linked to their code, and finding ids linked to their pages (spec §2.4). */
export default function NameText({ text }: { text: string }) {
  const ws = useWs();
  return (
    <>
      {nameParts(text, ws.data.names).map((p, i) => {
        if ("text" in p) return <Fragment key={i}>{p.text}</Fragment>;
        if ("code" in p) return <code key={i}>{p.code}</code>;
        if ("node" in p)
          return (
            <Link key={i} className="ws-name" to={ws.link(ws.opened({ node: p.node }))}
                  title={`Open ${p.label}'s code`} aria-label={`Open ${p.label}'s code`}>{p.label}</Link>
          );
        const f = ws.data.findings.find((x) => x.id === p.finding);
        const where = `Go to finding ${p.finding}${f ? `: ${short(f.title)}` : ""}`;
        return (
          <Link key={i} className="ws-handle link" to={ws.link(ws.item({ kind: "finding", fid: p.finding }))}
                title={where} aria-label={where}>{p.finding}</Link>
        );
      })}
    </>
  );
}

/** `code` spans for the backticked names in a title. */
export function Ticks({ text }: { text: string }) {
  return <>{text.split("`").map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part))}</>;
}
```

`frontend/src/workspace/Rail.tsx`:

```tsx
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { Story } from "../board/types";
import { load, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import { sections } from "../stories/stories";
import { type Place, samePlace } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { Ticks } from "./NameText";
import { bySeverity, litStories, storyCls } from "./rail";

export type Section = "changeset" | "stories" | "findings" | "files";
const OPEN_KEY = "ct.ws.rail.open", WIDTH_KEY = "ct.ws.railW";
const scrollKey = (rid: number) => `ct.ws.${rid}.railScroll`;

function loadOpen(): Record<Section, boolean> {
  const v = load<unknown>(OPEN_KEY, null), all = { changeset: true, stories: true, findings: true, files: false };
  return v && typeof v === "object" ? { ...all, ...(v as Partial<Record<Section, boolean>>) } : all;
}

/** The rail (spec 2026-10-04-review-workspace §2.2): everything in the review, the stories visibly drawn from the change
 * set. `show` names a section to open and scroll to (an address's #stories). */
export default function Rail({ show, onPick }: { show: string | null; onPick: () => void }) {
  const ws = useWs(), d = ws.data;
  const [open, setOpen] = useState(loadOpen);
  const [width, setWidth] = useState(() => { const w = load<unknown>(WIDTH_KEY, 280); return typeof w === "number" && w >= 200 && w <= 600 ? w : 280; });
  const [cl, setCl] = useState<number | null>(null);
  const box = useRef<HTMLElement>(null);
  const refs = useRef(new Map<string, HTMLElement>());
  const toggle = (s: Section, to = !open[s]) => setOpen((o) => { const n = { ...o, [s]: to }; save(OPEN_KEY, n); return n; });

  useEffect(() => {                                        // the rail's scroll position, per review
    const el = box.current, k = scrollKey(d.id);
    if (!el) return;
    el.scrollTop = load<number>(k, 0);
    const on = () => save(k, el.scrollTop);
    el.addEventListener("scroll", on, { passive: true });
    return () => el.removeEventListener("scroll", on);
  }, [d.id, d.ready]);
  useEffect(() => {
    if (!show || !(show in open)) return;
    toggle(show as Section, true);
    window.requestAnimationFrame(() => refs.current.get(show)?.scrollIntoView({ block: "start" }));
  }, [show]);                                              // eslint-disable-line react-hooks/exhaustive-deps

  const here = (p: Place) => (samePlace(p, ws.addr.place) ? "page" as const : undefined);
  const row = (place: Place, label: string, body: ReactNode, cls = "") => (
    <Link to={ws.link(ws.item(place))} className={`ws-row ${cls}`} aria-current={here(place)} title={label} aria-label={label}
          onClick={onPick}>{body}</Link>
  );
  const section = (s: Section, title: string, body: ReactNode) => (
    <section className="ws-sec" ref={(el) => { if (el) refs.current.set(s, el); }} aria-label={title}>
      <h2><button className="ws-sec-t" aria-expanded={open[s]} onClick={() => toggle(s)}>
        <span className="caret" aria-hidden>{open[s] ? "▾" : "▸"}</span>{title}</button></h2>
      {open[s] && body}
    </section>
  );
  const ss = d.stories, lit = ss ? litStories(ss, cl) : null;
  const story = (st: Story) => row({ kind: "story", sid: st.id, view: "steps" }, `Go to story ${st.id}: ${short(st.title)}`, <>
    <span className="ws-row-top">
      {st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
      <span className="ws-row-title"><Ticks text={st.title} /></span>
      <span className="ws-handle">{st.id}</span>
    </span>
    {st.cls.length > 0 && <span className="ws-chips">{st.cls.map((c) => <span key={c} className="ws-chip">CL {c}</span>)}</span>}
  </>, `story${lit && !lit.has(st.id) ? " dim" : ""}`);
  const group = (title: string, list: Story[]) => list.length > 0 && (
    <div className="ws-group"><h3>{title}</h3><ul>{list.map((st) => <li key={st.id}>{story(st)}</li>)}</ul></div>
  );
  const nFiles = d.about?.tree.reduce((n, t) => n + t.files.length, 0) ?? 0;
  const of = d.stories ? sections(d.stories) : null;
  const shown = ws.addr.open && "file" in ws.addr.open ? ws.addr.open.file : null;

  return (
    <aside className="ws-rail" ref={box} style={{ ["--w" as string]: `${width}px` }} aria-label="Review contents">
      <Resizer size={width} edge="right" min={200} max={() => 600} onSize={setWidth} onDone={(w) => save(WIDTH_KEY, w)} />
      <Link to={ws.base} state={{ page: true }} className="ws-row ws-home" aria-current={here({ kind: "whole" })}
            title="Go to the whole change" aria-label="Go to the whole change" onClick={onPick}>
        <span aria-hidden>⌂</span> Whole change {d.detail?.review.risk && <span className={`bd-pill ${d.detail.review.risk}`}>{d.detail.review.risk}</span>}
      </Link>
      {d.detail && section("changeset", `Change set (${d.detail.cls.length} CL${d.detail.cls.length === 1 ? "" : "s"})`, (
        <ul>{d.detail.cls.map((c) => {
          const first = (c.description ?? "").trim().split("\n")[0];
          const count = d.about?.cls.find((x) => x.cl === c.cl)?.file_count;
          const on = cl === c.cl;
          return (
            <li key={c.cl} className="ws-cl">
              {row({ kind: "cl", cl: c.cl }, `Open CL ${c.cl}`, <>
                <span className="ws-row-top"><b>CL {c.cl}</b><span className="muted">{c.user}</span>
                  {count !== undefined && <span className="muted small">{count} file{count === 1 ? "" : "s"}</span>}</span>
                <span className="ws-row-sub">{first}</span>
              </>)}
              {ss && <button className={`ws-dot${on ? " on" : ""}`} aria-pressed={on} onClick={() => setCl(on ? null : c.cl)}
                             title={on ? "Show every story" : `Highlight the stories drawn from CL ${c.cl}`}
                             aria-label={on ? "Show every story" : `Highlight the stories drawn from CL ${c.cl}`} />}
            </li>
          );
        })}</ul>
      ))}
      {ss && of && section("stories", `Stories (from ${storyCls(ss).length} CL${storyCls(ss).length === 1 ? "" : "s"})`, <>
        {group("What behaves differently", of.behaviour)}
        {of.collapsed.length > 0 && (
          <details className="ws-more"><summary>{of.collapsed.length} more behaviour stor{of.collapsed.length === 1 ? "y" : "ies"}</summary>
            <ul>{of.collapsed.map((st) => <li key={st.id}>{story(st)}</li>)}</ul></details>
        )}
        {group("Other changes", of.other)}
        {group("Repeated edits", of.mechanical)}
        {group("Tests", of.tests)}
        {!ss.stories.length && <p className="muted small">No changed functions.</p>}
      </>)}
      {d.ready && section("findings", `Findings (${d.findings.length})`, (
        bySeverity(d.findings).map((g) => (
          <div key={g.severity} className="ws-group"><h3>{g.severity}</h3><ul>{g.findings.map((f) => (
            <li key={f.id}>{row({ kind: "finding", fid: f.id }, `Go to finding ${f.id}: ${short(f.title)}`, <span className="ws-row-top">
              <span className={`ws-sev ${f.severity}`} aria-hidden />
              <span className="ws-row-title">{f.title}</span>
              <span className="ws-handle">{f.id}</span>
              {ss?.finding_story[f.id] && <span className="ws-handle">{ss.finding_story[f.id]}</span>}
            </span>, f.state !== "open" ? "done" : "")}</li>
          ))}</ul></div>
        ))
      ))}
      {d.about && section("files", `Files (${nFiles})`, (
        d.about.tree.map((t) => (
          <div key={t.dir} className="ws-group"><h3 className="mono">{t.dir}/</h3><ul>{t.files.map((f) => (
            <li key={f.path}>
              <Link to={ws.link(ws.opened({ file: f.path, line: null }, "diff"))} className="ws-row file" onClick={onPick}
                    aria-current={shown === f.path ? "true" : undefined} title={`Open ${f.name}'s diff`} aria-label={`Open ${f.name}'s diff`}>
                <span className="ws-row-top"><span className="mono">{f.name}</span><span className="muted small">{f.action}</span>
                  <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span></span>
                {f.cls.length > 0 && <span className="ws-chips">{f.cls.map((c) => <span key={c} className="ws-chip">CL {c}</span>)}</span>}
              </Link>
            </li>
          ))}</ul></div>
        ))
      ))}
    </aside>
  );
}
```

`frontend/src/workspace/Workspace.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useMe } from "../App";
import "../board/board.css";
import { driftSummary } from "../board/drift";
import AiPill from "../components/AiPill";
import Stages from "../components/Stages";
import { AiProvider } from "../lib/ai";
import { type Address, at, href, type Open, type Place, readAddress, type Tab } from "./address";
import { useWs as useWs, type Ws, WsContext } from "./context";
import Crumbs, { PhoneBar } from "./Crumbs";
import { type Crumb, crumbs } from "./crumbs";
import { useScreen } from "./media";
import { loadMemory, recall, remember, saveMemory } from "./memory";
import Rail from "./Rail";
import { useReview } from "./useReview";
import "./workspace.css";

/** Where the workspace lives (spec 2026-10-04-review-workspace §6: `/w/` while it is built, then `/r/`). */
export const base = (id: number) => `/w/${id}`;

/** The review workspace (spec 2026-10-04-review-workspace §2): header, rail, centre and the detail panel on demand. */
export default function Workspace() {
  const params = useParams();
  const id = Number(params.id);
  const [q] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const data = useReview(id);
  const screen = useScreen();
  const [drawer, setDrawer] = useState(false);
  const root = base(id);
  const addr = useMemo(() => readAddress(`/${params["*"] ?? ""}`, q), [params, q]);
  const [memory, setMemory] = useState(() => loadMemory(id));
  useEffect(() => setMemory((m) => { const n = remember(m, addr); saveMemory(id, n); return n; }), [id, addr]);

  const link = useCallback((a: Address) => href(root, a), [root]);
  const go = useCallback((a: Address, replace = false) => navigate(href(root, a), { replace }), [navigate, root]);
  const item = useCallback((p: Place) => recall(memory, p), [memory]);
  const opened = useCallback((open: Open, tab: Tab = "diff") => ({ ...addr, open, tab }), [addr]);
  const ws: Ws = useMemo(() => ({ base: root, data, addr, screen, link, go, item, opened }),
                         [root, data, addr, screen, link, go, item, opened]);

  const d = data.detail;
  const trail = useMemo(() => crumbs(addr.place, {
    base: root, title: d?.review.title ?? `Review ${id}`, stories: data.stories?.stories ?? [], findings: data.findings,
    cls: d?.cls ?? [], clusters: data.overview?.clusters ?? [],
  }), [addr.place, root, d, id, data.stories, data.findings, data.overview]);
  const hash = location.hash.slice(1) || null;
  const level = addr.open ? "detail" : addr.place.kind === "whole" && !(location.state as { page?: boolean } | null)?.page ? "rail" : "item";

  if (data.error) return <main className="page error">{data.error}</main>;
  if (!d) return <main className="page muted">Loading…</main>;
  return (
    <AiProvider value={data.ai}>
      <WsContext.Provider value={ws}>
        <main className={`ws ${screen} level-${level}${drawer ? " drawer" : ""}`}>
          <Head onMenu={() => setDrawer(!drawer)} drawer={drawer} />
          <div className={`ws-body${addr.open ? " with-detail" : ""}`}>
            {(screen !== "phone" || level === "rail") && <Rail show={hash} onPick={() => setDrawer(false)} />}
            {drawer && <div className="ws-scrim" onClick={() => setDrawer(false)} aria-hidden />}
            {(screen !== "phone" || level === "item") && (
              <section className="ws-centre" aria-label="Centre">
                {screen === "phone" ? <PhoneBar {...phoneBar(trail)} /> : <Crumbs items={trail} />}
                <Centre />
              </section>
            )}
          </div>
        </main>
      </WsContext.Provider>
    </AiProvider>
  );
}

/** "‹ Stories · S1 frame_pop writes…": back to the section, then the item. */
function phoneBar(trail: Crumb[]): { back: Crumb; title: string; handle?: string } {
  if (trail.length === 1) return { back: { label: "Contents", to: trail[0].to ?? "." }, title: "Whole change" };
  const [home, section, me] = trail;
  return me ? { back: section, title: me.label, handle: me.handle } : { back: home, title: section.label };
}

function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
  const ws = useWs(), me = useMe(), d = ws.data, r = d.detail!.review;
  const notes = d.detail!.stages.filter((s) => s.status === "failed" || s.status === "degraded");
  const drift = driftSummary(d.about?.drift ?? []).warn;
  return (
    <header className="ws-head">
      <button className="ws-menu" aria-label="Review contents" aria-expanded={drawer} title="Show the review's contents"
              onClick={onMenu}>☰</button>
      <h1><Link to={ws.base} state={{ page: true }} title="Go to the whole change">{r.title}</Link></h1>
      {r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
      {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
      {d.ready && <AiPill />}
      {me?.is_owner && d.ready && <button className="link rerun" onClick={() => api.rerun(d.id).then(d.loadDetail)}>Re-run</button>}
      {drift.length > 0 && <span className="bd-pill high" title={drift.join("\n")}>⚠ workspace drift ({drift.length})</span>}
      {notes.length > 0 && (
        <details className="bd-notes">
          <summary>{notes.length} stage note(s)</summary>
          {notes.map((s) => <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>)}
        </details>
      )}
    </header>
  );
}

/** What the address names, or what is missing (spec §7). */
function Centre() {
  const ws = useWs(), d = ws.data, p = ws.addr.place;
  if (!d.ready) return <div className="ws-page"><Stages stages={d.detail!.stages} /><p className="muted">Analysis in progress…</p></div>;
  const exists = p.kind === "whole" || (p.kind === "story" && !!d.stories?.stories.some((s) => s.id === p.sid))
    || (p.kind === "finding" && d.findings.some((f) => f.id === p.fid)) || (p.kind === "cl" && !!d.detail?.cls.some((c) => c.cl === p.cl))
    || (p.kind === "cluster" && !!d.overview?.clusters.some((c) => c.id === p.cid));
  if (!exists) return <Missing what={p} />;
  return <div className="ws-page"><p className="muted">This page is built in a later step.</p></div>;
}

export function Missing({ what }: { what: Place }) {
  const ws = useWs();
  const name = what.kind === "story" ? `Story ${what.sid}` : what.kind === "finding" ? `Finding ${what.fid}`
    : what.kind === "cl" ? `CL ${what.cl}` : what.kind === "cluster" ? `Part ${what.cid}` : "This page";
  return (
    <div className="ws-page">
      <div className="banner warn">{name} isn't in this review. <Link to={ws.link(at({ kind: "whole" }))} state={{ page: true }}>Whole change</Link></div>
    </div>
  );
}
```

`frontend/src/workspace/context.ts`:

```ts
import { createContext, useContext } from "react";
import type { Address, Open, Place, Tab } from "./address";
import type { Screen } from "./media";
import type { ReviewData } from "./useReview";

/** The workspace as every page and panel sees it: the review's data, the current address and ways to move. */
export interface Ws {
  base: string;
  data: ReviewData;
  addr: Address;
  screen: Screen;
  link: (a: Address) => string;
  /** Opening an item or the panel on something new pushes; switching flow, view or tab replaces (§2.4). */
  go: (a: Address, replace?: boolean) => void;
  /** An item as the reader left it this session (§2.4), for the rail and links between items. */
  item: (place: Place) => Address;
  /** The detail panel on `open` at the current place. */
  opened: (open: Open, tab?: Tab) => Address;
}

export const WsContext = createContext<Ws | null>(null);

export function useWs(): Ws {
  const ws = useContext(WsContext);
  if (!ws) throw new Error("useWs outside the workspace");
  return ws;
}
```

`frontend/src/workspace/media.ts`:

```ts
import { useEffect, useState } from "react";

/** The workspace's three layouts (spec 2026-10-04-review-workspace §2.1); follows rotation and resizing. */
export type Screen = "phone" | "tablet" | "desktop";
const PHONE = "(max-width: 640px)", TABLET = "(max-width: 1100px)";
const now = (): Screen => (window.matchMedia(PHONE).matches ? "phone" : window.matchMedia(TABLET).matches ? "tablet" : "desktop");

export function useScreen(): Screen {
  const [screen, setScreen] = useState(now);
  useEffect(() => {
    const qs = [window.matchMedia(PHONE), window.matchMedia(TABLET)], on = () => setScreen(now());
    qs.forEach((q) => q.addEventListener("change", on));
    return () => qs.forEach((q) => q.removeEventListener("change", on));
  }, []);
  return screen;
}
```

`frontend/src/workspace/useReview.ts`:

```ts
/** Everything the workspace shows about one review (spec 2026-10-04-review-workspace §5: Review.tsx's data loading,
 * progress events and AI state, moved into a hook). */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, type AiJob, type Board, type Comment, type FileChange, type Finding, type Names, type Overview,
  type ReviewDetail, type StorySet } from "../api";
import { useAiState } from "../lib/ai";

const TERMINAL = new Set(["done", "degraded", "failed"]);
const missing = <T,>(fallback: T) => (e: unknown): T => {
  if (e instanceof ApiError && e.status === 404) return fallback;
  throw e;
};

export function useReview(id: number) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [board, setBoard] = useState<Board | null | undefined>(undefined);          // null: a split review, or none
  const [overview, setOverview] = useState<Overview | null | undefined>(undefined); // null: shown as one board
  const [stories, setStories] = useState<StorySet | null | undefined>(undefined);   // null: run before stories
  const [findings, setFindings] = useState<Finding[]>([]);
  const [files, setFiles] = useState<FileChange[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [names, setNames] = useState<Names>({});
  const [reload, setReload] = useState(0);                // story pages and cluster graphs fetch again after AI text
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => setError(String((e as Error).message ?? e)), []);
  const loadDetail = useCallback(() => api.review(id).then(setDetail).catch(fail), [id, fail]);
  const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
  const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
  const loadStories = useCallback(() => api.stories(id).then(setStories, (e) => setStories(missing(null)(e))), [id]);
  const loadNames = useCallback(() => api.names(id).then(setNames).catch(() => { /* names fall back to "a function" */ }), [id]);
  const loadBoard = useCallback(() => api.board(id).then(setBoard, (e) => setBoard(missing(null)(e))), [id]);
  const loadResults = useCallback(() => Promise.all([
    api.overview(id).then((ov) => { setOverview(ov); setBoard(null); },
                          (e) => { setOverview(missing(null)(e)); return loadBoard(); }),
    loadStories(), loadFindings(), api.files(id).then(setFiles), loadComments(), loadNames(),
  ]).catch(fail), [id, loadBoard, loadStories, loadFindings, loadComments, loadNames, fail]);

  useEffect(() => { loadDetail(); }, [loadDetail]);
  const status = detail?.review.status;
  useEffect(() => {
    if (!status) return;
    if (TERMINAL.has(status)) { loadResults(); return; }
    const es = new EventSource(`/api/reviews/${id}/events`);
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setDetail((d) => (d ? { ...d, review: data.review, stages: data.stages } : d));
      if (TERMINAL.has(data.review.status)) { es.close(); loadDetail(); }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [id, status, loadResults, loadDetail]);

  const ready = !!status && TERMINAL.has(status);
  const people = useMemo(() => [...new Set([detail?.review.created_by ?? "", ...comments.map((c) => c.author)])].filter(Boolean),
                         [detail, comments]);
  const onAiDone = useCallback((jobs: AiJob[]) => {      // an explanation finished: show it
    if (jobs.some((j) => j.kind === "flow" || j.kind === "story")) {
      setReload((k) => k + 1);
      loadStories();
      loadNames();
      if (overview === null) loadBoard();
    }
    if (jobs.some((j) => j.kind === "finding")) { loadFindings(); loadNames(); }
  }, [loadStories, loadNames, loadBoard, loadFindings, overview]);
  const ai = useAiState(id, ready, people, comments.some((c) => c.ai_meta?.pending), onAiDone, loadComments);
  const about = (board ?? overview)?.about ?? null;

  return { id, detail, board, overview, stories, findings, files, comments, names, about, reload, error, ready, ai,
           loadDetail, loadComments, loadFindings };
}

export type ReviewData = ReturnType<typeof useReview>;
```

`frontend/src/workspace/workspace.css`:

```css
/* The review workspace (spec 2026-10-04-review-workspace §2.1): header, rail, centre, detail panel. */
.ws { display: flex; flex-direction: column; overflow: hidden !important; }
.ws-head { flex: none; display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; padding: 8px 16px;
  border-bottom: 1px solid var(--line); background: var(--surface); }
.ws-head h1 { font-size: 16px; margin: 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-head h1 a { color: var(--ink); text-decoration: none; }
.ws-head .rerun { margin-left: auto; }
.ws-menu { display: none; font-size: 17px; line-height: 1; padding: 3px 9px; }
.ws-body { flex: 1; min-height: 0; display: flex; position: relative; }

/* rail */
.ws-rail { position: relative; flex: none; width: var(--w, 280px); overflow-y: auto; overflow-x: hidden; border-right: 1px solid var(--line);
  background: var(--surface); padding: 8px 0 24px; font-size: 13px; }
/* the grip sticks to the rail's edge as it scrolls; the negative margin keeps its float from pushing the sections down */
.ws-rail .bd-resizer { position: sticky; float: right; top: 0; height: 100%; margin: 0 -1px -100vh 0; }
.ws-rail ul { list-style: none; margin: 0; padding: 0; }
.ws-sec { border-top: 1px solid var(--line); padding: 4px 0; }
.ws-sec h2 { margin: 0; }
.ws-sec-t { display: flex; align-items: center; gap: 6px; width: 100%; border: 0; background: none; border-radius: 0;
  padding: 7px 14px; font: 600 12px/1.3 var(--sans); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); text-align: left; }
.ws-sec-t .caret { width: 10px; }
.ws-group h3 { margin: 6px 14px 2px; font: 600 11px/1.3 var(--sans); color: var(--muted); text-transform: none; }
.ws-row { display: flex; flex-direction: column; gap: 3px; padding: 6px 14px; color: var(--ink); text-decoration: none;
  border-left: 3px solid transparent; }
.ws-row:hover { background: var(--gap-bg); }
.ws-row[aria-current] { background: color-mix(in srgb, var(--accent) 10%, var(--surface)); border-left-color: var(--accent); }
.ws-row.dim { opacity: .38; }
.ws-row.done .ws-row-title { color: var(--muted); text-decoration: line-through; }
.ws-row-top { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
.ws-row-title { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.ws-row-title code, .ws-centre code { font-family: var(--mono); font-size: .92em; }
.ws-row-sub { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-home { flex-direction: row; align-items: center; gap: 8px; font-weight: 600; padding: 8px 14px; }
.ws-handle { display: inline-block; margin-left: 5px; padding: 0 4px; border-radius: 4px; font: 500 10.5px/1.5 var(--mono);
  color: var(--muted); background: var(--gap-bg); vertical-align: 1px; white-space: nowrap; }
a.ws-handle { text-decoration: none; }
.ws-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.ws-chip { font: 500 10.5px/1.6 var(--mono); padding: 0 6px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
.ws-cl { position: relative; }
.ws-cl .ws-row { padding-right: 36px; }
.ws-dot { position: absolute; right: 12px; top: 9px; width: 14px; height: 14px; padding: 0; border-radius: 50%;
  border: 2px solid var(--accent); background: transparent; }
.ws-dot.on { background: var(--accent); }
.ws-sev { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--info); align-self: center; }
.ws-sev.high { background: var(--bad); } .ws-sev.medium { background: var(--warn); } .ws-sev.low { background: var(--ok); }
.ws-more summary { padding: 4px 14px; color: var(--muted); cursor: pointer; font-size: 12px; }
.ws-row .cnt { margin-left: auto; font: 11px var(--mono); } .ws-row .cnt .p { color: var(--ok); } .ws-row .cnt .m { color: var(--bad); }

/* centre */
.ws-centre { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
.ws-crumbs { flex: none; display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px; padding: 8px 20px; font-size: 13px;
  border-bottom: 1px solid var(--line); color: var(--muted); }
.ws-crumbs a { text-decoration: none; } .ws-crumbs a:hover { text-decoration: underline; }
.ws-crumbs [aria-current] { color: var(--ink); font-weight: 600; }
.ws-crumbs .sep { color: var(--muted); padding: 0 2px; }
.ws-page { flex: 1; min-height: 0; overflow: auto; padding: 18px 24px 48px; }
.ws-page > .ws-text { max-width: 880px; margin: 0 auto; }
.ws-page.graph { padding: 0; display: flex; flex-direction: column; overflow: hidden; }
.ws-name { font-family: var(--mono); font-size: .92em; text-decoration: none; border-bottom: 1px dotted var(--accent); }
.ws-phonebar { flex: none; display: flex; align-items: baseline; gap: 6px; padding: 10px 14px; border-bottom: 1px solid var(--line);
  background: var(--surface); font-size: 14px; min-width: 0; }
.ws-phonebar a { flex: none; text-decoration: none; font-weight: 600; }
.ws-phonebar b { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-scrim { display: none; }

/* tablet: the rail becomes a drawer behind ☰ */
@media (max-width: 1100px) {
  .ws-menu { display: inline-block; }
  .ws.tablet .ws-rail { position: absolute; z-index: 30; top: 0; bottom: 0; left: 0; transform: translateX(-100%);
    transition: transform .18s ease; box-shadow: 0 6px 28px rgba(0, 0, 0, .18); }
  .ws.tablet.drawer .ws-rail { transform: none; }
  .ws.tablet.drawer .ws-scrim { display: block; position: absolute; inset: 0; z-index: 29; background: rgba(0, 0, 0, .18); }
}
/* phone: three levels, one shown at a time */
@media (max-width: 640px) {
  #root:has(.ws) > .topbar { display: none; }
  .ws-menu { display: none; }
  .ws.phone .ws-rail { width: 100%; border-right: 0; }
  .ws.phone .ws-rail .bd-resizer { display: none; }
  .ws.phone .ws-row { padding: 9px 16px; }
  .ws-page { padding: 14px 16px 40px; }
  .ws-head { padding: 8px 12px; }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace.spec.ts`

Expected: `✓ built in …` and `4 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  26 passed (26)` and `Tests  125 passed (125)` and `✓ built in …` and `59 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/helpers.ts frontend/e2e/workspace.spec.ts frontend/src/App.tsx frontend/src/workspace/Crumbs.tsx frontend/src/workspace/NameText.tsx frontend/src/workspace/Rail.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/context.ts frontend/src/workspace/media.ts frontend/src/workspace/useReview.ts frontend/src/workspace/workspace.css
git commit -m "feat(ui): the review workspace shell at /w/:id — header, rail from the change set, breadcrumb, phone levels"
```

---

### Task 7: The whole change page

Spec §3.1. Top to bottom: the intent (marked AI when the AI wrote it), "Why it is {risk} risk" with each
reason linking to its finding, the stories' summary, the map (a split review's parts in their layer bands, each
linking to its part; Task 11 adds the graph of a review shown as one board), files with side effects (each opening its
diff at the line), workspace drift, and the discussion (review comments and layer threads).

**Files:**
- Create: `frontend/src/workspace/WholePage.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace.spec.ts`

**Interfaces:**
- Consumes: `useWs()` (Task 6), `sideEffects`, `drift`, `Comments`, `NameText`.
- Produces: `WholePage()`, rendered by `Workspace` for `{kind:"whole"}`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index 8a053b1..c4cf93b 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -1,5 +1,5 @@
 import { devices, expect, test } from "@playwright/test";
-import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";
+import { expectNamed, expectNoNodeIds, login, startWorkspace } from "./helpers";
 
 /** The workspace shell (spec 2026-10-04-review-workspace §2): rail, breadcrumb, addresses, phone levels. */
 
@@ -37,6 +37,21 @@ test.describe("desktop", () => {
     await expectNamed(page);
   });
 
+  test("the whole change: what it is for, why it is risky, then the rest", async ({ page }) => {
+    const base = await startWorkspace(page);
+    const page_ = page.locator(".ws-whole");
+    await expect(page_.locator("h2")).toHaveText(["What this change is trying to do", "Why it is high risk",
+                                                  "Files with side effects", "Discussion"]);
+    await expect(page_.locator(".ws-summary")).toContainText("2 behaviour stories.");
+    await page_.getByRole("link", { name: /^Go to finding F1:/ }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}/f/F1$`));
+    await page.goBack();
+    await page_.locator(".ws-fx").getByRole("link", { name: /^Open uart_errors at line/ }).click();
+    await expect(page).toHaveURL(/\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c%3A\d+$/);
+    await expectNoNodeIds(page);
+    await expectNamed(page);
+  });
+
   test("an address to something that does not exist says so", async ({ page }) => {
     const base = await startWorkspace(page);
     await page.goto(`${base}/s/S9`);
@@ -80,3 +95,22 @@ test.describe("phone", () => {
     expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
   });
 });
+
+test.describe("a large change", () => {
+  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });
+
+  test("the whole change maps its parts; a part opens its page", async ({ page }) => {
+    await login(page);
+    await page.getByLabel("Changelists (shelved or submitted)").fill("201 202");
+    await page.getByRole("button", { name: "Start review" }).click();
+    await expect(page.locator(".st-entry").first()).toBeVisible({ timeout: 60_000 });
+    const base = `/w/${page.url().match(/\/r\/(\d+)/)![1]}`;
+    await page.goto(base);
+    const map = page.getByRole("region", { name: "The map" });
+    await expect(map.locator(".ov-block")).toHaveCount(7);
+    await expect(map.getByRole("region", { name: "Layer drv" })).toContainText("drv/dma");
+    await map.getByRole("link", { name: "Open drv/uart" }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}/c/C\\d+$`));
+    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Map › drv/uart");
+  });
+});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace.spec.ts`

Expected: FAIL — `✓ built in …` and `2 failed` and `4 passed` and (2 failing, first: desktop › the whole change: what it is for, why it is risky, then the rest)

- [ ] **Step 3: Implement**

`frontend/src/workspace/WholePage.tsx`:

```tsx
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { driftSummary } from "../board/drift";
import { bandsOf, linkLines } from "../board/overview";
import { sideEffectFiles } from "../board/sideEffects";
import Comments from "../components/Comments";
import { useWs } from "./context";
import NameText from "./NameText";

/** The review's home (spec 2026-10-04-review-workspace §3.1): what the change is for and why it is risky first. */
export default function WholePage() {
  const ws = useWs(), d = ws.data, about = d.about, risk = d.detail!.review.risk;
  const sideEffects = useMemo(() => (d.board ? sideEffectFiles(d.board) : []), [d.board]);
  const drift = driftSummary(about?.drift ?? []);
  const ov = d.overview;
  const layerName = (level: number | null) => (d.board?.layers ?? ov?.layers ?? []).find((l) => l.level === level)?.name;
  return (
    <div className="ws-page"><div className="ws-text ws-whole">
      <section aria-labelledby="ws-intent">
        <h2 id="ws-intent">What this change is trying to do</h2>
        {about ? <p className="ws-lead">{about.intent_source === "llm" && <span className="ai-label">AI</span>}<NameText text={about.intent} /></p>
          : <p className="muted">No summary for this review (reviews made before the board existed have none).</p>}
      </section>
      {about && about.why.length > 0 && (
        <section aria-labelledby="ws-why">
          <h2 id="ws-why">Why it is {risk ?? "flagged"} risk</h2>
          <ul className="ws-why">{about.why.map((w) => (
            <li key={w.finding}><span className={`ws-sev ${w.severity}`} aria-hidden />
              <Link to={ws.link(ws.item({ kind: "finding", fid: w.finding }))} title={`Go to finding ${w.finding}`}
                    aria-label={`Go to finding ${w.finding}: ${w.text}`}>{w.text}</Link><span className="ws-handle">{w.finding}</span></li>
          ))}</ul>
        </section>
      )}
      {d.stories && <p className="ws-summary"><NameText text={d.stories.summary} /></p>}
      {ov && (
        <section aria-labelledby="ws-map" id="map">
          <h2 id="ws-map">The map</h2>
          <p className="muted">This change is split into {ov.totals.clusters} parts of connected code, riskiest first.
            {ov.merged_over_limit > 0 && ` ${ov.merged_over_limit} small parts were merged to keep the list short.`}</p>
          {bandsOf(ov).map((b) => (
            <section key={b.level} className={`ov-band lv${b.level < 0 ? "x" : b.level % 4}`} aria-label={`Layer ${b.name}`}>
              <h3>{b.name}</h3>
              <div className="ov-blocks">{b.clusters.map((c) => (
                <Link key={c.id} to={ws.link(ws.item({ kind: "cluster", cid: c.id }))} className={`ov-block ${c.risk ?? "none"}`}
                      title={`Open ${c.name}`} aria-label={`Open ${c.name}`}>
                  <div className="nm">{c.name} {c.risk && <span className={`sev ${c.risk}`}>{c.risk.toUpperCase()}</span>}</div>
                  <div className="ct">{c.files.length} files · {c.changed} changed · {c.flows} flows
                    {c.findings > 0 && ` · ${c.findings} finding${c.findings === 1 ? "" : "s"}`}</div>
                  {linkLines(ov, c.id, 3).map((l) => <div key={l} className="ln">{l}</div>)}
                  {c.also.length > 0 && <div className="also">also in {c.also.map((lv) => layerName(lv) ?? `L${lv}`).join(", ")}</div>}
                </Link>
              ))}</div>
            </section>
          ))}
        </section>
      )}
      {sideEffects.length > 0 && (
        <section aria-labelledby="ws-fx">
          <h2 id="ws-fx">Files with side effects</h2>
          <ul className="ws-fx">{sideEffects.flatMap((dir) => dir.files.map((f) => (
            <li key={f.path}>
              <Link to={ws.link(ws.opened({ file: f.path, line: f.fns[0]?.line ?? null }))} className="mono"
                    title={`Open ${f.name}'s diff`} aria-label={`Open ${f.name}'s diff`}>{dir.dir}/{f.name}</Link>
              {f.alsoChanged && <span className="muted small"> also changed</span>}
              <ul>{f.fns.map((fn) => (
                <li key={fn.node} className={fn.landing ? "landing" : fn.severity}>
                  <Link to={ws.link(ws.opened({ file: f.path, line: fn.line }))} title={`Open ${fn.label} at line ${fn.line}`}
                        aria-label={`Open ${fn.label} at line ${fn.line}`}><b>{fn.label}</b></Link> · {fn.text}
                </li>
              ))}</ul>
            </li>
          )))}</ul>
        </section>
      )}
      {(drift.warn.length > 0 || drift.info.length > 0) && (
        <section aria-labelledby="ws-drift">
          <h2 id="ws-drift">Workspace drift</h2>
          {drift.warn.length > 0 && <p className="banner warn">⚠ {drift.warn.length} file(s): workspace older than the change's base,
            or not synced. Context code fetched from the workspace may not match what was analysed. {drift.warn.join("; ")}</p>}
          {drift.info.length > 0 && <p className="muted">ⓘ {drift.info.length} file(s): workspace newer than the change (expected for
            submitted CLs). {drift.info.join("; ")}</p>}
        </section>
      )}
      <section aria-labelledby="ws-talk">
        <h2 id="ws-talk">Discussion</h2>
        <Comments reviewId={d.id} comments={d.comments} kind="review" anchor={{}} onChange={d.loadComments} />
        {[...new Set(d.comments.filter((c) => c.anchor_kind === "chapter" && c.parent_id === null).map((c) => c.anchor.level as number | null))]
          .map((level) => (
            <div key={String(level)} className="bd-layer-thread">
              <div className="m">Layer {layerName(level) ?? (level === null ? "unlayered" : `L${level}`)}</div>
              <Comments reviewId={d.id} comments={d.comments} kind="chapter" anchor={{ level }} onChange={d.loadComments} compact />
            </div>
          ))}
      </section>
    </div></div>
  );
}
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index aeaca8f..60dc2f9 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -15,6 +15,7 @@ import { useScreen } from "./media";
 import { loadMemory, recall, remember, saveMemory } from "./memory";
 import Rail from "./Rail";
 import { useReview } from "./useReview";
+import WholePage from "./WholePage";
 import "./workspace.css";
 
 /** Where the workspace lives (spec 2026-10-04-review-workspace §6: `/w/` while it is built, then `/r/`). */
@@ -112,6 +113,7 @@ function Centre() {
     || (p.kind === "finding" && d.findings.some((f) => f.id === p.fid)) || (p.kind === "cl" && !!d.detail?.cls.some((c) => c.cl === p.cl))
     || (p.kind === "cluster" && !!d.overview?.clusters.some((c) => c.id === p.cid));
   if (!exists) return <Missing what={p} />;
+  if (p.kind === "whole") return <WholePage />;
   return <div className="ws-page"><p className="muted">This page is built in a later step.</p></div>;
 }
 
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 7ba9bb6..f91cbc8 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -81,3 +81,16 @@ a.ws-handle { text-decoration: none; }
   .ws-page { padding: 14px 16px 40px; }
   .ws-head { padding: 8px 12px; }
 }
+
+/* whole change */
+.ws-whole section { margin: 0 0 26px; }
+.ws-whole h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 0 0 8px; }
+.ws-lead { font-size: 16px; line-height: 1.6; margin: 0; }
+.ws-summary { font-size: 14px; padding: 10px 14px; border-left: 3px solid var(--accent); background: var(--surface); margin: 0 0 26px; }
+.ws-why, .ws-fx { list-style: none; margin: 0; padding: 0; }
+.ws-why li { display: flex; align-items: baseline; gap: 8px; padding: 5px 0; }
+.ws-why .ws-sev { transform: translateY(-1px); }
+.ws-fx > li { padding: 6px 0; border-bottom: 1px solid var(--line); }
+.ws-fx ul { list-style: none; padding: 2px 0 0 14px; margin: 0; font-size: 13px; color: var(--muted); }
+.ws-fx li.landing b, .ws-fx li.warn b { color: var(--bad); }
+a.ov-block { display: block; color: var(--ink); text-decoration: none; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace.spec.ts`

Expected: `✓ built in …` and `6 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  26 passed (26)` and `Tests  125 passed (125)` and `✓ built in …` and `61 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace.spec.ts frontend/src/workspace/WholePage.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/workspace.css
git commit -m "feat(ui): the whole change page — intent, why it is risky, the stories' summary, the map, side effects, drift, discussion"
```

---

### Task 8: The detail panel: a function's code, the full file, a file's diff

Spec §3.7 (Diff tab), §7. `open=` opens the panel. For a node, `locateNode` finds its code on the graph of the
story holding it, else on the review's board (a field folded into a struct resolves to the struct); `FunctionCode`
shows the slice with its effects and function comments, with a switch to the full file. For a file, `FileDiff` shows
its whole diff: CL picker, changes only or full file, stacked or side by side, Summarise, folding, and the line from
the address opened and scrolled to. The header names the node or file with its badge and story; ✕ closes it. On a
phone the panel is a full-screen sheet with its own top bar. An unknown node says "This function isn't in this
review.".

**Files:**
- Create: `frontend/src/workspace/Detail.tsx`
- Create: `frontend/src/workspace/FileDiff.tsx`
- Create: `frontend/src/workspace/FunctionCode.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/context.ts`
- Create: `frontend/src/workspace/detail.ts`
- Modify: `frontend/src/workspace/useReview.ts`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace-detail.spec.ts` (new)
- Test: `frontend/src/workspace/detail.test.ts` (new)

**Interfaces:**
- Consumes: `useWs()`, `ws.data.story(sid)` (Task 6), `CodeView`, `codeRows`, `fold`, `Comments`, `useSources`.
- Produces: `locateNode(nid, boards): {node, board} | null`; `FunctionCode({node, board})`; `FileDiff({path, line, anns, cl?, wide})`; `Detail()` (an `aside` labelled "Code: <name>"; width kept in `ct.ws.detailW`).

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-detail.spec.ts`:

```ts
import { devices, expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";

/** The detail panel (spec 2026-10-04-review-workspace §3.7): a node's code or a file's diff, on demand. */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a file from the rail opens its diff; ✕ closes it", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    await expect(page).toHaveURL(/\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c$/);
    const panel = page.getByRole("complementary", { name: "Code: uart.c" });
    await expect(panel.locator(".ws-detail-path")).toHaveText("//fixture/driver/uart.c");
    await expect(panel.locator(".bd-code")).toBeVisible();
    await expect(panel.getByLabel("Changelist")).toHaveValue("all");
    await panel.getByRole("button", { name: "Full file" }).click();
    await expect(panel.locator(".bd-gap")).toHaveCount(0);
    await expectNamed(page);
    await panel.getByRole("link", { name: "Close the code" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.locator(".ws-detail")).toHaveCount(0);
  });

  test("a node opens its function, its story and the full file", async ({ page }) => {
    const base = await startWorkspace(page);
    const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
    const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
    await page.goto(`${base}?open=${send}`);
    const panel = page.getByRole("complementary", { name: "Code: uart_send" });
    await expect(panel.locator(".ws-badge")).toHaveText("changed");
    await expect(panel.locator(".ws-detail-path")).toContainText("//fixture/driver/uart.c · lines");
    await expect(panel.locator(".bd-code")).toBeVisible();
    await panel.getByRole("button", { name: "Full file" }).click();
    await expect(panel.getByLabel("Changelist")).toBeVisible();
    await panel.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expectNoNodeIds(page);
  });

  test("an unknown node says so", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}?open=N99999`);
    await expect(page.locator(".ws-detail .banner")).toContainText("This function isn't in this review.");
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the code opens as a full-screen sheet whose top bar names it", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c:17")}`);
    await expect(page.locator(".ws-rail, .ws-centre")).toHaveCount(0);
    const bar = page.locator(".ws-detail .ws-phonebar");
    await expect(bar).toContainText("uart.c");
    await bar.getByRole("link", { name: "Close the code" }).click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
```

`frontend/src/workspace/detail.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Board, BoardNode } from "../board/types";
import { locateNode } from "./detail";

const node = (id: string, extra: Partial<BoardNode> = {}): BoardNode => ({
  id, key: id, label: id, kind: "function", layer: null, path: null, local: null, range: null, change: null, x: 0, warn: 0, ...extra,
});
const board = (nodes: BoardNode[]): Board => ({ nodes, edges: [], flows: [], impacts: [], layers: [], hidden_nodes: 0,
  about: { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] } });

describe("locateNode", () => {
  it("finds a node with code on the first board that has it", () => {
    const a = board([node("N1")]), b = board([node("N1", { path: "//d/a.c", range: [3, 9] })]);
    expect(locateNode("N1", [undefined, a, b])).toEqual({ node: b.nodes[0], board: b });
  });

  it("finds a field folded into a struct as the struct", () => {
    const s = node("N5", { kind: "struct", path: "//d/a.h", range: [1, 4], fields: [{ id: "N6", label: "errors" }] });
    const b = board([s]);
    expect(locateNode("N6", [b])).toEqual({ node: s, board: b });
  });

  it("falls back to a node without code, then to nothing", () => {
    const a = board([node("N1")]);
    expect(locateNode("N1", [a])).toEqual({ node: a.nodes[0], board: a });
    expect(locateNode("N2", [a, null])).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/workspace/detail.test.ts && npm run build && npx playwright test e2e/workspace-detail.spec.ts`

Expected: FAIL — `Test Files  1 failed (1)` and `Tests  no tests` and `Cannot find module './detail' imported from src/workspace/detail.test.ts`

- [ ] **Step 3: Implement**

`frontend/src/workspace/Detail.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { load, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import type { StoryDetail } from "../board/types";
import { at } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { locateNode } from "./detail";
import FileDiff from "./FileDiff";
import FunctionCode from "./FunctionCode";

const WIDTH_KEY = "ct.ws.detailW";

/** The detail panel (spec 2026-10-04-review-workspace §3.7): a node's code or a file's diff, opened on demand; on a
 * phone a full-screen sheet whose top bar names its item. */
export default function Detail() {
  const ws = useWs(), d = ws.data, open = ws.addr.open!;
  const [width, setWidth] = useState(() => {
    const w = load<unknown>(WIDTH_KEY, 0);
    return typeof w === "number" && w >= 320 && w <= 4000 ? w : Math.round(window.innerWidth * 0.45);
  });
  const nid = "node" in open ? open.node : null, name = nid ? d.names[nid] : null;
  const [story, setStory] = useState<StoryDetail | null>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    if (!name?.story) return;
    let live = true;
    d.story(name.story).then((s) => { if (live) setStory(s); }).catch(() => {});
    return () => { live = false; };
  }, [name?.story, d]);
  const close = ws.link({ ...ws.addr, open: null, tab: "diff" });
  const found = nid ? locateNode(nid, [story?.graph, story?.board, d.board]) : null;
  const node = found?.node;
  const path = "file" in open ? open.file : node?.path ?? name?.path ?? null;
  const label = "file" in open ? path!.slice(path!.lastIndexOf("/") + 1) : node?.label ?? name?.label ?? null;
  const lines = node?.range ? `lines ${node.range[0]}–${node.range[1]}` : "file" in open && open.line ? `line ${open.line}`
    : name?.line ? `line ${name.line}` : null;
  const badge = !nid ? null : node?.kind === "field" || node?.kind === "struct" || name?.kind === "field" ? "field"
    : node?.change ? "changed" : "context";
  const sid = name?.story ?? null, st = sid ? d.stories?.stories.find((s) => s.id === sid) : null;
  const anns = found?.board.impacts ?? story?.board.impacts ?? d.board?.impacts ?? [];
  const wide = ws.screen === "desktop" && width > 900;

  const body = () => {
    if (nid && !name && !node)
      return <div className="banner warn">This function isn't in this review. <Link to={ws.link(at({ kind: "whole" }))}>Whole change</Link></div>;
    if (node?.path && node.range && !full) return <FunctionCode node={node} board={found!.board} />;
    if (!path) return <p className="muted">No code to show for {label}.</p>;
    const line = "file" in open ? open.line : node?.range?.[0] ?? name?.line ?? null;
    return <FileDiff key={path} path={path} line={line} anns={anns} wide={wide}
                     cl={ws.addr.place.kind === "cl" ? ws.addr.place.cl : null} />;
  };
  return (
    <aside className="ws-detail" style={{ ["--w" as string]: `${width}px` }} aria-label={`Code: ${label ?? "not found"}`}>
      {ws.screen === "desktop" && <Resizer size={width} edge="left" min={320} max={() => window.innerWidth * 0.75}
                                           onSize={setWidth} onDone={(w) => save(WIDTH_KEY, w)} />}
      {ws.screen === "phone" && (
        <div className="ws-phonebar">
          <Link to={close} aria-label="Close the code" title="Close the code">‹ {st ? st.id : "Back"}</Link>
          <span className="sep" aria-hidden>·</span><b>{label}</b>
        </div>
      )}
      <div className="ws-detail-head">
        <div className="ws-detail-name">
          <b className="mono">{label ?? "Not found"}</b>
          {badge && <span className={`ws-badge ${badge}`}>{badge}</span>}
          {st && <Link className="ws-detail-story" to={ws.link(ws.item({ kind: "story", sid: st.id, view: "steps" }))}
                       title={`Go to story ${st.id}: ${short(st.title)}`} aria-label={`Go to story ${st.id}: ${short(st.title)}`}>
            {short(st.title, 40)}<span className="ws-handle">{st.id}</span></Link>}
          {ws.screen !== "phone" && <Link className="ws-x" to={close} aria-label="Close the code" title="Close the code">✕</Link>}
        </div>
        {path && <div className="ws-detail-path mono">{path}{lines && <span className="muted"> · {lines}</span>}</div>}
        {node?.path && node.range && (
          <div className="ws-detail-tools">
            <span className="bd-seg">
              <button className={`bd-ibtn${!full ? " on" : ""}`} aria-pressed={!full} onClick={() => setFull(false)}>Function</button>
              <button className={`bd-ibtn${full ? " on" : ""}`} aria-pressed={full} onClick={() => setFull(true)}>Full file</button>
            </span>
          </div>
        )}
      </div>
      <div className="ws-detail-body">{body()}</div>
    </aside>
  );
}
```

`frontend/src/workspace/FileDiff.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { Comment } from "../api";
import CodeView from "../board/CodeView";
import { lineDiff, plainLines } from "../board/codeRows";
import { expandRange, foldRuns, type Range, revealRange } from "../board/fold";
import { keys, loadViewerView, save, type ViewerView } from "../board/prefs";
import type { Annotation } from "../board/types";
import { isChange, useEnsureSource } from "../board/useSources";
import Explain, { FileSummaryView } from "../components/Explain";
import { useAi } from "../lib/ai";
import { onLine } from "../lib/anchors";
import { useWs } from "./context";

interface Props {
  path: string;
  /** A line to show (and open if it is folded). */
  line: number | null;
  anns: Annotation[];
  /** The changelist to show first (a CL page's files); null: all together. */
  cl?: number | null;
  wide: boolean;
}

/** One file in the detail panel (spec 2026-10-04-review-workspace §3.7; was the stacked file viewer): its diff, changes
 * only or the full file, per changelist, with folding, notes and line comments. */
export default function FileDiff({ path, line, anns, cl: firstCl = null, wide }: Props) {
  const ws = useWs(), d = ws.data;
  const src = useEnsureSource(path, ws.sources);
  const change = isChange(src) ? src : null;
  const cls = change ? [...new Set(change.per_cl.map((c) => c.cl))] : [];
  const [cl, setCl] = useState<number | null>(firstCl !== null && cls.includes(firstCl) ? firstCl : null);
  const [view, setView] = useState<ViewerView>(loadViewerView);
  const [mode, setMode] = useState<"unified" | "split">(wide ? "split" : "unified");
  const [shown, setShown] = useState<Range[]>([]);
  const box = useRef<HTMLDivElement>(null);
  const step = change && cl !== null ? change.per_cl.find((x) => x.cl === cl) ?? null : null;
  const lines = useMemo(() => {
    if (change) return step ? lineDiff(step.before, step.after) : lineDiff(change.before, change.after);
    if (src && "status" in src && src.status === "ok") return plainLines(src.file.text);
    return null;
  }, [src, change, step]);
  const mine = useMemo(() => anns.filter((x) => x.path === path && x.side === "new"), [anns, path]);
  const keep = useMemo(() => {                      // lines with notes or comment threads stay in the changes view
    if (!lines) return new Set<number>();
    const ns = new Set<number>([...mine.map((x) => x.line), ...d.comments.filter((c) => threadOn(c, path, cl)).map((c) => c.anchor.line as number)]);
    return new Set(lines.flatMap((l, i) => (l.n !== null && ns.has(l.n) ? [i] : [])));
  }, [lines, mine, d.comments, path, cl]);
  useEffect(() => setShown([]), [cl]);
  useEffect(() => {                                 // a folded line asked for opens the lines around it
    if (line && lines) { const r = revealRange(lines, line); if (r) setShown((s) => [...s, r]); }
  }, [line, lines]);
  useEffect(() => {                                 // and is scrolled to once drawn
    if (!line || !lines) return;
    const id = window.requestAnimationFrame(() => box.current?.querySelector(`[data-n="${line}"]`)?.scrollIntoView({ block: "center" }));
    return () => window.cancelAnimationFrame(id);
  }, [line, lines, view]);
  const folding = !!change && view === "changes";
  const runs = useMemo(() => (folding && lines ? foldRuns(lines, shown, keep) : null), [folding, lines, shown, keep]);
  const counts = lines && change ? [lines.filter((l) => l.t === "+").length, lines.filter((l) => l.t === "-").length] : null;
  const summarised = useAi()?.view?.file_summaries[path]?.summary;
  return (
    <div className="ws-file" ref={box}>
      <div className="ws-file-tools">
        {change ? <span className="act">{change.action}</span> : src && "status" in src && src.status === "ok"
          ? <span className="muted small">unchanged · {src.file.depot}{src.file.rev.startsWith("#") ? src.file.rev : ""}</span> : null}
        {change?.base_rev && <span className="muted small">base {change.base_rev}</span>}
        {counts && <span className="cnt"><span className="p">+{counts[0]}</span> <span className="m">−{counts[1]}</span></span>}
        <span className="sp" />
        {change && <Explain kind="file" target={path} label="Summarise" has={!!summarised} />}
        {change && cls.length > 0 && (
          <select aria-label="Changelist" value={cl === null ? "all" : String(cl)}
                  onChange={(e) => setCl(e.target.value === "all" ? null : Number(e.target.value))}>
            <option value="all">All CLs</option>
            {cls.map((c) => <option key={c} value={String(c)}>CL {c}</option>)}
          </select>
        )}
        {change && (
          <span className="bd-seg">
            <button className={`bd-ibtn${view === "changes" ? " on" : ""}`} aria-pressed={view === "changes"}
                    onClick={() => { setView("changes"); save(keys.viewerView, "changes"); }}>Changes</button>
            <button className={`bd-ibtn${view === "full" ? " on" : ""}`} aria-pressed={view === "full"}
                    onClick={() => { setView("full"); save(keys.viewerView, "full"); }}>Full file</button>
          </span>
        )}
        {change && (
          <span className="bd-seg">
            <button className={`bd-ibtn${mode === "unified" ? " on" : ""}`} aria-pressed={mode === "unified"} onClick={() => setMode("unified")}>Stacked</button>
            <button className={`bd-ibtn${mode === "split" ? " on" : ""}`} aria-pressed={mode === "split"} onClick={() => setMode("split")}>Side by side</button>
          </span>
        )}
      </div>
      {change && <FileSummaryView path={path} />}
      {lines ? (
        <CodeView reviewId={d.id} path={path} lines={lines} mode={change ? mode : "unified"} anns={anns} comments={d.comments}
                  onComments={d.loadComments} focus={line} windowed cl={cl} runs={runs}
                  onExpand={(run, how) => setShown((s) => [...s, expandRange(run, how)])} />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => ws.sources.reload(path)}>Retry</button></div>
      ) : <div className="bd-note">Fetching {path}…</div>}
    </div>
  );
}

/** A root line comment on this file's new side, for the changelist in view. */
function threadOn(c: Comment, path: string, cl: number | null): boolean {
  return c.anchor_kind === "line" && c.parent_id === null && c.anchor.side === "new" && onLine(c, path, "new", c.anchor.line as number, cl);
}
```

`frontend/src/workspace/FunctionCode.tsx`:

```tsx
import { useMemo } from "react";
import CodeView from "../board/CodeView";
import { lineDiff, plainLines, sliceRange } from "../board/codeRows";
import type { Board, BoardNode } from "../board/types";
import { isChange, useEnsureSource } from "../board/useSources";
import Comments from "../components/Comments";
import { useWs } from "./context";

/** A function's code slice with its effects (changed) or what it touches (context), and its comments: the detail
 * panel's Diff tab for a node (spec 2026-10-04-review-workspace §3.7; was the floating card's body). */
export default function FunctionCode({ node, board }: { node: BoardNode; board: Board }) {
  const ws = useWs(), d = ws.data;
  const src = useEnsureSource(node.path, ws.sources);
  const [lo, hi] = node.range ?? [0, 0];
  const pad = node.kind === "field" || node.kind === "struct" ? 4 : 0;
  const lines = useMemo(() => {
    if (isChange(src)) return sliceRange(lineDiff(src.before, src.after), lo - pad, hi + pad);
    if (src && "status" in src && src.status === "ok") return sliceRange(plainLines(src.file.text), lo - pad, hi + pad);
    return null;
  }, [src, lo, hi, pad]);
  const effects = board.impacts.filter((a) => a.node === node.id && a.severity === "warn");
  const touches = useMemo(() => {
    const own = board.impacts.find((a) => a.node === node.id);
    if (own) return own.text;
    const changed = new Map(board.nodes.filter((n) => n.change).map((n) => [n.id, n.label]));
    const e = board.edges.find((e) => e.src === node.id && changed.has(e.dst));
    return e ? `${e.kind === "call" || e.kind === "virtual" ? "calls" : e.kind} ${changed.get(e.dst)} (changed)` : "context";
  }, [board, node.id]);
  return (
    <div className="ws-fn">
      {node.change ? (
        effects.length > 0 && <div className="effects">{effects.map((a, i) => <div key={i}><span className="ico">⚠</span>{a.text}</div>)}</div>
      ) : <div className="fetched">Unchanged · {touches}</div>}
      {lines ? (
        <CodeView reviewId={d.id} path={node.path!} lines={lines} mode="unified" anns={board.impacts} comments={d.comments}
                  onComments={d.loadComments} />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => ws.sources.reload(node.path!)}>Retry</button></div>
      ) : <div className="bd-note">Fetching {node.path}…</div>}
      <div className="bd-fn-comments">
        <Comments reviewId={d.id} comments={d.comments} kind="function" anchor={{ key: node.key }} onChange={d.loadComments} compact />
      </div>
    </div>
  );
}
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index 60dc2f9..850a070 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -5,11 +5,13 @@ import { useMe } from "../App";
 import "../board/board.css";
 import { driftSummary } from "../board/drift";
 import AiPill from "../components/AiPill";
+import { useSources } from "../board/useSources";
 import Stages from "../components/Stages";
 import { AiProvider } from "../lib/ai";
 import { type Address, at, href, type Open, type Place, readAddress, type Tab } from "./address";
 import { useWs as useWs, type Ws, WsContext } from "./context";
 import Crumbs, { PhoneBar } from "./Crumbs";
+import Detail from "./Detail";
 import { type Crumb, crumbs } from "./crumbs";
 import { useScreen } from "./media";
 import { loadMemory, recall, remember, saveMemory } from "./memory";
@@ -30,6 +32,7 @@ export default function Workspace() {
   const navigate = useNavigate();
   const data = useReview(id);
   const screen = useScreen();
+  const sources = useSources(id, data.files);
   const [drawer, setDrawer] = useState(false);
   const root = base(id);
   const addr = useMemo(() => readAddress(`/${params["*"] ?? ""}`, q), [params, q]);
@@ -40,8 +43,8 @@ export default function Workspace() {
   const go = useCallback((a: Address, replace = false) => navigate(href(root, a), { replace }), [navigate, root]);
   const item = useCallback((p: Place) => recall(memory, p), [memory]);
   const opened = useCallback((open: Open, tab: Tab = "diff") => ({ ...addr, open, tab }), [addr]);
-  const ws: Ws = useMemo(() => ({ base: root, data, addr, screen, link, go, item, opened }),
-                         [root, data, addr, screen, link, go, item, opened]);
+  const ws: Ws = useMemo(() => ({ base: root, data, addr, screen, sources, link, go, item, opened }),
+                         [root, data, addr, screen, sources, link, go, item, opened]);
 
   const d = data.detail;
   const trail = useMemo(() => crumbs(addr.place, {
@@ -67,6 +70,7 @@ export default function Workspace() {
                 <Centre />
               </section>
             )}
+            {addr.open && d && data.ready && (screen !== "phone" || level === "detail") && <Detail key={JSON.stringify(addr.open)} />}
           </div>
         </main>
       </WsContext.Provider>
```

`frontend/src/workspace/context.ts`:

```diff
diff --git a/frontend/src/workspace/context.ts b/frontend/src/workspace/context.ts
index ef19345..aefdf06 100644
--- a/frontend/src/workspace/context.ts
+++ b/frontend/src/workspace/context.ts
@@ -1,5 +1,6 @@
 import { createContext, useContext } from "react";
 import type { Address, Open, Place, Tab } from "./address";
+import type { useSources } from "../board/useSources";
 import type { Screen } from "./media";
 import type { ReviewData } from "./useReview";
 
@@ -9,6 +10,8 @@ export interface Ws {
   data: ReviewData;
   addr: Address;
   screen: Screen;
+  /** File text for the detail panel, fetched once per session. */
+  sources: ReturnType<typeof useSources>;
   link: (a: Address) => string;
   /** Opening an item or the panel on something new pushes; switching flow, view or tab replaces (§2.4). */
   go: (a: Address, replace?: boolean) => void;
```

`frontend/src/workspace/detail.ts`:

```ts
import type { Board, BoardNode } from "../board/types";

/** The node to show for `nid` and the board it is drawn on: the first board giving its code, else any that has it; a
 * field folded into a story graph's struct is shown as the struct. */
export function locateNode(nid: string, boards: (Board | null | undefined)[]): { node: BoardNode; board: Board } | null {
  let plain: { node: BoardNode; board: Board } | null = null;
  for (const b of boards) {
    if (!b) continue;
    const n = b.nodes.find((x) => x.id === nid) ?? b.nodes.find((x) => x.fields?.some((f) => f.id === nid));
    if (!n) continue;
    if (n.path && n.range) return { node: n, board: b };
    plain ??= { node: n, board: b };
  }
  return plain;
}
```

`frontend/src/workspace/useReview.ts`:

```diff
diff --git a/frontend/src/workspace/useReview.ts b/frontend/src/workspace/useReview.ts
index a98a42a..2746563 100644
--- a/frontend/src/workspace/useReview.ts
+++ b/frontend/src/workspace/useReview.ts
@@ -1,8 +1,8 @@
 /** Everything the workspace shows about one review (spec 2026-10-04-review-workspace §5: Review.tsx's data loading,
  * progress events and AI state, moved into a hook). */
-import { useCallback, useEffect, useMemo, useState } from "react";
+import { useCallback, useEffect, useMemo, useRef, useState } from "react";
 import { api, ApiError, type AiJob, type Board, type Comment, type FileChange, type Finding, type Names, type Overview,
-  type ReviewDetail, type StorySet } from "../api";
+  type ReviewDetail, type StoryDetail, type StorySet } from "../api";
 import { useAiState } from "../lib/ai";
 
 const TERMINAL = new Set(["done", "degraded", "failed"]);
@@ -63,10 +63,21 @@ export function useReview(id: number) {
     }
     if (jobs.some((j) => j.kind === "finding")) { loadFindings(); loadNames(); }
   }, [loadStories, loadNames, loadBoard, loadFindings, overview]);
+  const cache = useRef(new Map<string, Promise<StoryDetail>>());
+  /** A story's page data, fetched once and again after AI text changes it. */
+  const story = useCallback((sid: string) => {
+    let p = cache.current.get(`${reload}:${sid}`);
+    if (!p) {
+      p = api.story(id, sid);
+      p.catch(() => cache.current.delete(`${reload}:${sid}`));
+      cache.current.set(`${reload}:${sid}`, p);
+    }
+    return p;
+  }, [id, reload]);
   const ai = useAiState(id, ready, people, comments.some((c) => c.ai_meta?.pending), onAiDone, loadComments);
   const about = (board ?? overview)?.about ?? null;
 
-  return { id, detail, board, overview, stories, findings, files, comments, names, about, reload, error, ready, ai,
+  return { id, detail, board, overview, stories, findings, files, comments, names, about, reload, error, ready, ai, story,
            loadDetail, loadComments, loadFindings };
 }
 
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index f91cbc8..afc2ac4 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -94,3 +94,32 @@ a.ws-handle { text-decoration: none; }
 .ws-fx ul { list-style: none; padding: 2px 0 0 14px; margin: 0; font-size: 13px; color: var(--muted); }
 .ws-fx li.landing b, .ws-fx li.warn b { color: var(--bad); }
 a.ov-block { display: block; color: var(--ink); text-decoration: none; }
+
+/* detail panel */
+.ws-detail { position: relative; flex: none; width: var(--w); max-width: 75vw; display: flex; flex-direction: column;
+  border-left: 1px solid var(--line); background: var(--surface); min-width: 0; }
+.ws-detail > .bd-resizer { position: absolute; left: -3px; top: 0; bottom: 0; }
+.ws-detail-head { flex: none; padding: 10px 14px 8px; border-bottom: 1px solid var(--line); display: flex; flex-direction: column; gap: 4px; }
+.ws-detail-name { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
+.ws-detail-name b { font-size: 15px; }
+.ws-detail-path { font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
+.ws-detail-story { font-size: 12.5px; text-decoration: none; }
+.ws-detail-tools { display: flex; gap: 8px; align-items: center; }
+.ws-x { margin-left: auto; text-decoration: none; color: var(--muted); font-size: 16px; padding: 0 4px; }
+.ws-badge { font: 600 10.5px/1.6 var(--sans); padding: 0 7px; border-radius: 999px; border: 1px solid currentColor; color: var(--info); }
+.ws-badge.changed { color: var(--accent); } .ws-badge.field { color: #9b6a2f; }
+.ws-detail-body { flex: 1; min-height: 0; overflow: auto; padding: 10px 14px 40px; }
+.ws-file-tools { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; margin-bottom: 8px; }
+.ws-file-tools .sp { flex: 1; } .ws-file-tools select { width: auto; padding: 3px 6px; }
+.ws-file-tools .cnt { font: 12px var(--mono); } .ws-file-tools .cnt .p { color: var(--ok); } .ws-file-tools .cnt .m { color: var(--bad); }
+.ws-file-tools .act { font: 600 11px var(--sans); text-transform: uppercase; color: var(--muted); }
+.ws-fn .effects { margin-bottom: 8px; font-size: 13px; color: var(--bad); }
+.ws-fn .effects .ico { margin-right: 6px; }
+.ws-fn .fetched { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
+@media (max-width: 1100px) {
+  .ws.tablet .ws-detail { position: absolute; z-index: 20; right: 0; top: 0; bottom: 0; width: min(720px, 92vw); max-width: none;
+    box-shadow: -6px 0 28px rgba(0, 0, 0, .16); }
+}
+@media (max-width: 640px) {
+  .ws.phone .ws-detail { width: 100%; max-width: none; border-left: 0; }
+}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/workspace/detail.test.ts && npm run build && npx playwright test e2e/workspace-detail.spec.ts`

Expected: `Test Files  1 passed (1)` and `Tests  3 passed (3)` and `✓ built in …` and `4 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  27 passed (27)` and `Tests  128 passed (128)` and `✓ built in …` and `65 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-detail.spec.ts frontend/src/workspace/Detail.tsx frontend/src/workspace/FileDiff.tsx frontend/src/workspace/FunctionCode.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/context.ts frontend/src/workspace/detail.test.ts frontend/src/workspace/detail.ts frontend/src/workspace/useReview.ts frontend/src/workspace/workspace.css
git commit -m "feat(ui): the detail panel — a function's code, the full file and a file's diff, on demand"
```

---

### Task 9: The Neighbours tab

Spec §3.7 (Neighbours tab), §7. Three columns: callers, the function, callees. Each row names the function,
its file, a changed badge and a story chip, and moves the panel to that function (`tab=neighbours`, a history entry so
Back returns). Columns show 20 rows with "Show all N"; test callers come last, marked "test"; a failed fetch offers
Retry.

**Files:**
- Modify: `frontend/src/workspace/Detail.tsx`
- Create: `frontend/src/workspace/Neighbours.tsx`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace-detail.spec.ts`

**Interfaces:**
- Consumes: `api.neighbours` (Task 4), `Detail` (Task 8).
- Produces: `Neighbours({nid})`, the panel's second tab (`tab=neighbours`).

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-detail.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace-detail.spec.ts b/frontend/e2e/workspace-detail.spec.ts
index d918816..248ed31 100644
--- a/frontend/e2e/workspace-detail.spec.ts
+++ b/frontend/e2e/workspace-detail.spec.ts
@@ -61,3 +61,28 @@ test.describe("phone", () => {
     expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
   });
 });
+
+test.describe("neighbours", () => {
+  test.use({ viewport: { width: 1440, height: 900 } });
+
+  test("callers and callees; a row moves the panel and Back returns", async ({ page }) => {
+    const base = await startWorkspace(page);
+    const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
+    const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
+    await page.goto(`${base}?open=${send}`);
+    await page.getByRole("tab", { name: "Neighbours" }).click();
+    await expect(page).toHaveURL(new RegExp(`open=${send}&tab=neighbours$`));
+    const callers = page.getByRole("region", { name: "Callers" });
+    await expect(callers.getByRole("link", { name: "Open logger_flush's neighbours" })).toBeVisible();
+    await expect(page.getByRole("region", { name: "This function" })).toContainText("uart_send");
+    await callers.getByRole("link", { name: "Open logger_flush's neighbours" }).click();
+    await expect(page.getByRole("region", { name: "This function" })).toContainText("logger_flush");
+    await expect(page.getByRole("region", { name: "Callees" })).toContainText("uart_send");
+    await page.goBack();
+    await expect(page.getByRole("region", { name: "This function" })).toContainText("uart_send");
+    await page.getByRole("tab", { name: "Diff" }).click();
+    await expect(page.locator(".ws-detail .bd-code")).toBeVisible();
+    await expectNoNodeIds(page);
+    await expectNamed(page);
+  });
+});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-detail.spec.ts`

Expected: FAIL — `✓ built in …` and `1 failed` and `4 passed` and (1 failing, first: neighbours › callers and callees; a row moves the panel and Back returns)

- [ ] **Step 3: Implement**

`frontend/src/workspace/Detail.tsx`:

```diff
diff --git a/frontend/src/workspace/Detail.tsx b/frontend/src/workspace/Detail.tsx
index 8e57bf5..5440984 100644
--- a/frontend/src/workspace/Detail.tsx
+++ b/frontend/src/workspace/Detail.tsx
@@ -9,6 +9,7 @@ import { short } from "./crumbs";
 import { locateNode } from "./detail";
 import FileDiff from "./FileDiff";
 import FunctionCode from "./FunctionCode";
+import Neighbours from "./Neighbours";
 
 const WIDTH_KEY = "ct.ws.detailW";
 
@@ -71,7 +72,15 @@ export default function Detail() {
           {ws.screen !== "phone" && <Link className="ws-x" to={close} aria-label="Close the code" title="Close the code">✕</Link>}
         </div>
         {path && <div className="ws-detail-path mono">{path}{lines && <span className="muted"> · {lines}</span>}</div>}
-        {node?.path && node.range && (
+        {nid && (name || node) && (
+          <div className="ws-tabs" role="tablist" aria-label="Detail">
+            {(["diff", "neighbours"] as const).map((t) => (
+              <Link key={t} role="tab" aria-selected={ws.addr.tab === t} className={ws.addr.tab === t ? "on" : ""} replace
+                    to={ws.link({ ...ws.addr, tab: t })}>{t === "diff" ? "Diff" : "Neighbours"}</Link>
+            ))}
+          </div>
+        )}
+        {node?.path && node.range && ws.addr.tab === "diff" && (
           <div className="ws-detail-tools">
             <span className="bd-seg">
               <button className={`bd-ibtn${!full ? " on" : ""}`} aria-pressed={!full} onClick={() => setFull(false)}>Function</button>
@@ -80,7 +89,7 @@ export default function Detail() {
           </div>
         )}
       </div>
-      <div className="ws-detail-body">{body()}</div>
+      <div className="ws-detail-body">{nid && ws.addr.tab === "neighbours" && (name || node) ? <Neighbours nid={nid} /> : body()}</div>
     </aside>
   );
 }
```

`frontend/src/workspace/Neighbours.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Neighbour, type Neighbours as Model } from "../api";
import { useWs } from "./context";

const LIMIT = 20;

/** The Neighbours tab (spec 2026-10-04-review-workspace §3.7): callers, the node, callees; a row moves the panel to that
 * node (a history entry, so Back returns). Replaces growing the board on "+N callers". */
export default function Neighbours({ nid }: { nid: string }) {
  const ws = useWs(), d = ws.data;
  const [limit, setLimit] = useState(LIMIT);
  const [model, setModel] = useState<Model | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    api.neighbours(d.id, nid, limit).then((m) => { if (live) setModel(m); })
      .catch((e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [d.id, nid, limit, tick]);
  if (error) return <div className="bd-note error">{error} <button className="bd-ibtn" onClick={() => setTick((t) => t + 1)}>Retry</button></div>;
  if (!model) return <div className="bd-note">Finding callers and callees…</div>;
  const row = (n: Neighbour) => {
    const where = n.path ? n.path.slice(n.path.lastIndexOf("/") + 1) : null;
    return (
      <li key={n.id}>
        <Link to={ws.link(ws.opened({ node: n.id }, "neighbours"))} className={`ws-nb${n.test ? " test" : ""}`}
              title={`Open ${n.label}'s neighbours`} aria-label={`Open ${n.label}'s neighbours`}>
          <span className="ws-row-top"><b className="mono">{n.label}</b>
            {n.changed && <span className="ws-badge changed">changed</span>}
            {n.test && <span className="ws-badge">test</span>}
            {n.story && <span className="ws-handle">{n.story}</span>}</span>
          {where && <span className="ws-row-sub mono">{where}{n.line ? `:${n.line}` : ""}</span>}
        </Link>
      </li>
    );
  };
  const column = (title: string, side: Model["callers"]) => (
    <section className="ws-nb-col" aria-label={title}>
      <h3>{title} <span className="muted small">{side.total}</span></h3>
      {side.items.length ? <ul>{side.items.map(row)}</ul> : <p className="muted small">None.</p>}
      {side.total > side.items.length && (
        <button className="link small" onClick={() => setLimit(side.total)}>Show all {side.total}</button>
      )}
    </section>
  );
  return (
    <div className="ws-nbs">
      {column("Callers", model.callers)}
      <section className="ws-nb-col me" aria-label="This function">
        <h3>This function</h3>
        <div className="ws-nb on"><b className="mono">{model.node.label}</b>
          {model.node.changed && <span className="ws-badge changed">changed</span>}
          {model.node.path && <span className="ws-row-sub mono">{model.node.path.slice(model.node.path.lastIndexOf("/") + 1)}</span>}</div>
      </section>
      {column("Callees", model.callees)}
    </div>
  );
}
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index afc2ac4..de8a364 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -123,3 +123,16 @@ a.ov-block { display: block; color: var(--ink); text-decoration: none; }
 @media (max-width: 640px) {
   .ws.phone .ws-detail { width: 100%; max-width: none; border-left: 0; }
 }
+.ws-tabs { display: flex; gap: 2px; margin-top: 4px; }
+.ws-tabs a { padding: 4px 12px; border-radius: 6px 6px 0 0; text-decoration: none; color: var(--muted); border-bottom: 2px solid transparent; }
+.ws-tabs a.on { color: var(--ink); border-bottom-color: var(--accent); font-weight: 600; }
+.ws-nbs { display: grid; grid-template-columns: 1fr minmax(140px, .7fr) 1fr; gap: 12px; align-items: start; }
+.ws-nb-col h3 { margin: 0 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
+.ws-nb-col ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
+.ws-nb { display: flex; flex-direction: column; gap: 2px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px;
+  text-decoration: none; color: var(--ink); background: var(--bg); }
+a.ws-nb:hover { border-color: var(--accent); }
+.ws-nb.test { opacity: .75; }
+.ws-nb.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, var(--surface)); }
+.ws-nb-col.me { position: sticky; top: 0; }
+@media (max-width: 640px) { .ws-nbs { grid-template-columns: 1fr; } .ws-nb-col.me { position: static; order: -1; } }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-detail.spec.ts`

Expected: `✓ built in …` and `5 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  27 passed (27)` and `Tests  128 passed (128)` and `✓ built in …` and `66 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-detail.spec.ts frontend/src/workspace/Detail.tsx frontend/src/workspace/Neighbours.tsx frontend/src/workspace/workspace.css
git commit -m "feat(ui): the Neighbours tab — callers, the function, callees; a row moves the panel"
```

---

### Task 10: The flow strip

Spec §3.6. One row: fixed-width ‹ `flow 2 of 5` ›, the flow's tag and its title cut to the remaining width
(full title in a tooltip), a ▾ menu of every flow and a collapse toggle. Below it the flow's text: what it does (unless
the page already says it), its steps as named links in graph views, where the side effect lands and what to check.
`pickFlow` chooses the flow from the address, else the first flow through the open node, else the first.

**Files:**
- Create: `frontend/src/workspace/FlowStrip.tsx`
- Create: `frontend/src/workspace/flows.ts`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/src/workspace/flows.test.ts` (new)

**Interfaces:**
- Consumes: `NameText` (Task 6), `Explain`, `useWs()`.
- Produces: `pickFlow(flows, flow, node): number`, `wrap(i, by, n)`; `FlowStrip({board, flows, index, onFlow, steps, hideWhat?})` (a region labelled "Flow").

- [ ] **Step 1: Write the failing tests**

`frontend/src/workspace/flows.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { BoardFlow } from "../board/types";
import { pickFlow, wrap } from "./flows";

const flow = (id: string, path: string[]) => ({ id, path } as BoardFlow);
const flows = [flow("FL1", ["N1", "N2"]), flow("FL2", ["N3", "N4"]), flow("FL3", ["N5"])];

describe("the selected flow", () => {
  it("is the address's flow (1-based), kept in range", () => {
    expect(pickFlow(flows, 2, null)).toBe(1);
    expect(pickFlow(flows, 9, null)).toBe(2);
  });

  it("else the first flow through the open node, else the first", () => {
    expect(pickFlow(flows, null, "N4")).toBe(1);
    expect(pickFlow(flows, null, "N99")).toBe(0);
    expect(pickFlow([], null, null)).toBe(0);
  });

  it("steps wrap around", () => {
    expect(wrap(0, -1, 3)).toBe(2);
    expect(wrap(2, 1, 3)).toBe(0);
    expect(wrap(0, 1, 0)).toBe(0);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/workspace/flows.test.ts`

Expected: FAIL — `Test Files  1 failed (1)` and `Tests  no tests` and `Cannot find module './flows' imported from src/workspace/flows.test.ts`

- [ ] **Step 3: Implement**

`frontend/src/workspace/FlowStrip.tsx`:

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Board } from "../board/types";
import Explain from "../components/Explain";
import { useWs } from "./context";
import { wrap } from "./flows";
import NameText from "./NameText";

interface Props {
  board: Board;
  /** The flows to step through (a story's, or every flow on the board). */
  flows: Board["flows"];
  index: number;
  onFlow: (i: number) => void;
  /** Graph views list the flow's steps too; the Steps view numbers them below. */
  steps: boolean;
  /** Leave the "what" out (the story's summary already tells it). */
  hideWhat?: boolean;
}

/** The flow strip (spec 2026-10-04-review-workspace §3.6): fixed-width ‹ flow 2 of 5 ›, the tag, the title cut to the
 * width left, a ▾ menu of every flow; below it the flow's text, collapsible. Its controls never move between flows. */
export default function FlowStrip({ board, flows, index, onFlow, steps, hideWhat }: Props) {
  const ws = useWs();
  const [menu, setMenu] = useState(false);
  const [shut, setShut] = useState(false);
  const flow = flows[index];
  if (!flow) return null;
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const n = flows.length;
  return (
    <section className="ws-flow" aria-label="Flow">
      <div className="ws-flow-row">
        <button className="bd-ibtn ws-flow-btn" aria-label="Previous flow" title="Previous flow" disabled={n < 2}
                onClick={() => onFlow(wrap(index, -1, n))}>‹</button>
        <span className="ws-flow-pos">flow {index + 1} of {n}</span>
        <button className="bd-ibtn ws-flow-btn" aria-label="Next flow" title="Next flow" disabled={n < 2}
                onClick={() => onFlow(wrap(index, 1, n))}>›</button>
        <span className={`bd-tag ${flow.tag}`}>{flow.tag}</span>
        <b className="ws-flow-title" title={flow.title}>{flow.title}</b>
        <span className="ws-flow-menu">
          <button className="bd-ibtn" aria-label="Every flow" title="Every flow" aria-expanded={menu} onClick={() => setMenu(!menu)}>▾</button>
          {menu && (
            <ul role="menu">{flows.map((f, i) => (
              <li key={f.id} role="none"><button role="menuitemradio" aria-checked={i === index}
                onClick={() => { setMenu(false); onFlow(i); }}><span className="muted">{i + 1}</span> {f.title}</button></li>
            ))}</ul>
          )}
        </span>
        <button className="bd-ibtn ws-flow-btn" aria-expanded={!shut} aria-label={shut ? "Show the flow's text" : "Hide the flow's text"}
                title={shut ? "Show the flow's text" : "Hide the flow's text"} onClick={() => setShut(!shut)}>{shut ? "+" : "−"}</button>
      </div>
      {!shut && (
        <div className="ws-flow-text">
          {!hideWhat && <p>{flow.what_source === "llm" && <span className="ai-label">AI</span>}<NameText text={flow.what} />{" "}
            <Explain kind="flow" target={flow.id} has={flow.what_source === "llm"} /></p>}
          {steps && (
            <p className="ws-flow-steps">{flow.path.map((id, i) => {
              const node = byId.get(id);
              if (!node) return null;
              return <span key={id}>{i > 0 && <span className="arrow" aria-hidden> → </span>}
                <Link className="ws-name" to={ws.link(ws.opened({ node: id }))} title={`Open ${node.label}'s code`}
                      aria-label={`Open ${node.label}'s code`}>{node.label}</Link></span>;
            })}</p>
          )}
          <p className="ws-flow-lands"><b>⚠ Side effect lands on {byId.get(flow.lands)?.label ?? "a function off this graph"}.</b>{" "}
            <NameText text={flow.effect} /></p>
          <p className="ws-flow-check"><NameText text={flow.check} /></p>
        </div>
      )}
    </section>
  );
}
```

`frontend/src/workspace/flows.ts`:

```ts
import type { BoardFlow } from "../board/types";

/** The flow to show (0-based): the address's `flow=` (1-based), else the first through the open node, else the first. */
export function pickFlow(flows: Pick<BoardFlow, "path">[], flow: number | null, node: string | null): number {
  if (!flows.length) return 0;
  if (flow) return Math.min(flow, flows.length) - 1;
  return Math.max(0, flows.findIndex((f) => !!node && f.path.includes(node)));
}

export const wrap = (i: number, by: number, n: number) => (n ? (((i + by) % n) + n) % n : 0);
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index de8a364..78e49ab 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -136,3 +136,22 @@ a.ws-nb:hover { border-color: var(--accent); }
 .ws-nb.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, var(--surface)); }
 .ws-nb-col.me { position: sticky; top: 0; }
 @media (max-width: 640px) { .ws-nbs { grid-template-columns: 1fr; } .ws-nb-col.me { position: static; order: -1; } }
+
+/* flow strip: the controls keep their place and the row never scrolls sideways */
+.ws-flow { flex: none; border-bottom: 1px solid var(--line); background: var(--surface); min-width: 0; }
+.ws-flow-row { display: flex; align-items: center; gap: 8px; padding: 8px 14px; min-width: 0; }
+.ws-flow-btn { flex: none; width: 30px; padding: 2px 0 !important; text-align: center; }
+.ws-flow-pos { flex: none; width: 7.5em; text-align: center; font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums; }
+.ws-flow-row .bd-tag { flex: none; }
+.ws-flow-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
+.ws-flow-menu { position: relative; flex: none; }
+.ws-flow-menu ul { position: absolute; right: 0; top: 110%; z-index: 60; list-style: none; margin: 0; padding: 4px; min-width: 260px;
+  max-width: min(480px, 80vw); background: var(--surface); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 8px 24px rgba(0, 0, 0, .14); }
+.ws-flow-menu li button { display: block; width: 100%; text-align: left; border: 0; padding: 6px 8px; white-space: normal; }
+.ws-flow-menu li button[aria-checked=true] { background: var(--gap-bg); font-weight: 600; }
+.ws-flow-text { padding: 0 14px 10px; font-size: 13.5px; }
+.ws-flow-text p { margin: 4px 0; }
+.ws-flow-lands b { color: var(--bad); font-weight: 600; }
+.ws-flow-check { color: var(--muted); }
+.ws-flow-steps { line-height: 1.9; }
+.ws-flow-steps .arrow { color: var(--muted); }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/workspace/flows.test.ts`

Expected: `Test Files  1 passed (1)` and `Tests  3 passed (3)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  28 passed (28)` and `Tests  131 passed (131)` and `✓ built in …` and `66 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/workspace/FlowStrip.tsx frontend/src/workspace/flows.test.ts frontend/src/workspace/flows.ts frontend/src/workspace/workspace.css
git commit -m "feat(ui): the flow strip — fixed controls, the title cut to fit, a menu of every flow"
```

---

### Task 11: Graphs in the workspace

Spec §3.1, §3.2 (graph), §5. Trimmed copies of the board's reducer and canvas. The reducer keeps view, pan,
lens, mode, layout and moved nodes (the flow and the selection live in the address). The canvas's nodes are buttons
labelled "Open/Close X's code": a click toggles the detail panel; "+N callers / callees" opens the Neighbours tab.
`GraphView` puts the flow strip, the canvas and its toolbar (Flow / Whole graph, Layers / Call depth, Reset layout,
Lens) together. A review shown as one board shows its graph on the whole change page with "Open the full graph"
(`?view=graph`, the address gains `whole.view`). A rail file highlights its functions on the graph without
refiltering it.

**Files:**
- Modify: `frontend/src/workspace/WholePage.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/address.ts`
- Modify: `frontend/src/workspace/crumbs.ts`
- Create: `frontend/src/workspace/graph/Canvas.tsx`
- Create: `frontend/src/workspace/graph/GraphView.tsx`
- Create: `frontend/src/workspace/graph/reducer.ts`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace-graph.spec.ts` (new)
- Test: `frontend/e2e/workspace.spec.ts`
- Test: `frontend/src/workspace/address.test.ts`
- Test: `frontend/src/workspace/crumbs.test.ts`
- Test: `frontend/src/workspace/graph/reducer.test.ts` (new)

**Interfaces:**
- Consumes: `lens`, `layout`, `zoom`, `prefs` (`keys.moved`, `keys.layout`, `keys.lens`), `FlowStrip` (Task 10), `useWs()`.
- Produces: `GraphState`, `GraphAction`, `initialGraph(lens?, moved?, layout?)`, `reduceGraph(s, a)`; `Canvas(...)`;
  `GraphView({board, prefKey, flowIndex, onFlow, quiet?, onMore?, onHome?, homeName?})`; `ReviewGraph({board})`;
  `Place` `{kind:"whole"; view?:"graph"}` and its "Graph" crumb.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-graph.spec.ts`:

```ts
import { expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";

/** Graphs in the workspace (spec 2026-10-04-review-workspace §3.2, §3.6): a node click opens its code and a second
 * click closes it; "+N callers" opens Neighbours; the flow strip keeps its controls in place and never overflows. */

const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });

export async function flowStripHolds(page: Page) {
  const strip = page.getByRole("region", { name: "Flow" });
  const next = strip.getByRole("button", { name: "Next flow" });
  const at = (await next.boundingBox())!.x;
  const row = strip.locator(".ws-flow-row");
  for (let i = 0; i < 3; i++) {
    expect(await row.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    await next.click();
    expect((await next.boundingBox())!.x).toBe(at);
  }
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the review's graph: open full graph, select and deselect a node, flows keep their controls", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.getByRole("link", { name: "Open the full graph" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}\\?view=graph$`));
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Graph");
    await flowStripHolds(page);
    await expect(page).toHaveURL(/view=graph&flow=\d$/);

    await node(page, "uart_send").click();
    await expect(page).toHaveURL(/&open=N\d+$/);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await expect(node(page, "uart_send")).toHaveAttribute("aria-pressed", "true");
    await node(page, "uart_send").click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    await page.goBack();
    await expect(page.locator(".ws-detail")).toBeVisible();
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("a file from the rail highlights its functions on the graph and never refilters it", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}?view=graph`);
    await expect(page.locator(".bd-node").first()).toBeVisible();
    const count = await page.locator(".bd-node").count();
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    await expect(page.locator(".bd-node.lit").first()).toBeVisible();
    await expect(page.locator(".bd-node")).toHaveCount(count);
  });
});
```

`frontend/e2e/workspace.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index c4cf93b..0b0f711 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -41,7 +41,7 @@ test.describe("desktop", () => {
     const base = await startWorkspace(page);
     const page_ = page.locator(".ws-whole");
     await expect(page_.locator("h2")).toHaveText(["What this change is trying to do", "Why it is high risk",
-                                                  "Files with side effects", "Discussion"]);
+                                                  /^The map/, "Files with side effects", "Discussion"]);
     await expect(page_.locator(".ws-summary")).toContainText("2 behaviour stories.");
     await page_.getByRole("link", { name: /^Go to finding F1:/ }).click();
     await expect(page).toHaveURL(new RegExp(`${base}/f/F1$`));
```

`frontend/src/workspace/address.test.ts`:

```diff
diff --git a/frontend/src/workspace/address.test.ts b/frontend/src/workspace/address.test.ts
index ba21c61..9ab79cd 100644
--- a/frontend/src/workspace/address.test.ts
+++ b/frontend/src/workspace/address.test.ts
@@ -6,6 +6,7 @@ const q = (s: string) => new URLSearchParams(s);
 describe("readAddress", () => {
   it("reads each kind of place", () => {
     expect(readAddress("", q("")).place).toEqual({ kind: "whole" });
+    expect(readAddress("", q("view=graph")).place).toEqual({ kind: "whole", view: "graph" });
     expect(readAddress("/s/S1", q("")).place).toEqual({ kind: "story", sid: "S1", view: "steps" });
     expect(readAddress("/s/S1", q("view=graph")).place).toEqual({ kind: "story", sid: "S1", view: "graph" });
     expect(readAddress("/f/F2", q("")).place).toEqual({ kind: "finding", fid: "F2" });
@@ -37,8 +38,8 @@ describe("href", () => {
   });
 
   it("round-trips every place", () => {
-    for (const path of ["", "/s/S2", "/f/F1", "/cl/102", "/c/C1"]) {
-      const a = readAddress(path, q("flow=3&open=file://d/x.h"));
+    for (const [path, view] of [["", ""], ["", "graph"], ["/s/S2", "graph"], ["/f/F1", ""], ["/cl/102", ""], ["/c/C1", ""]]) {
+      const a = readAddress(path, q(`flow=3&open=file://d/x.h&view=${view}`));
       const [p, s] = href("/r/1", a).slice("/r/1".length).split("?");
       expect(readAddress(p, q(s ?? ""))).toEqual(a);
     }
@@ -49,6 +50,7 @@ describe("places", () => {
   it("have a key per item and compare by item, not view", () => {
     expect(placeKey({ kind: "story", sid: "S1", view: "graph" })).toBe("s:S1");
     expect(placeKey({ kind: "whole" })).toBe("whole");
+    expect(placeKey({ kind: "whole", view: "graph" })).toBe("whole");
     expect(samePlace({ kind: "story", sid: "S1", view: "graph" }, { kind: "story", sid: "S1", view: "steps" })).toBe(true);
     expect(samePlace({ kind: "finding", fid: "F1" }, { kind: "finding", fid: "F2" })).toBe(false);
   });
```

`frontend/src/workspace/crumbs.test.ts`:

```diff
diff --git a/frontend/src/workspace/crumbs.test.ts b/frontend/src/workspace/crumbs.test.ts
index 0e6b8e0..d2bf4bb 100644
--- a/frontend/src/workspace/crumbs.test.ts
+++ b/frontend/src/workspace/crumbs.test.ts
@@ -14,6 +14,7 @@ const ctx: CrumbContext = {
 describe("the breadcrumb", () => {
   it("names the review alone at home", () => {
     expect(crumbs({ kind: "whole" }, ctx)).toEqual([{ label: "Review 7", to: null }]);
+    expect(crumbs({ kind: "whole", view: "graph" }, ctx)).toEqual([{ label: "Review 7", to: "/r/7" }, { label: "Graph", to: null }]);
   });
 
   it("goes up from a story's graph to its steps, the stories and the review", () => {
```

`frontend/src/workspace/graph/reducer.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { type GraphAction, initialGraph, reduceGraph } from "./reducer";

const run = (...actions: GraphAction[]) => actions.reduce(reduceGraph, initialGraph());

describe("the graph's state", () => {
  it("node moves are 2-D, kept per layout and reset per layout", () => {
    let s = run({ t: "node.move", id: "N1", x: 10, y: 20 }, { t: "layout", layout: "depth" }, { t: "node.move", id: "N1", x: 5, y: 6 });
    expect(s.moved).toEqual({ layers: { N1: { x: 10, y: 20 } }, depth: { N1: { x: 5, y: 6 } } });
    s = reduceGraph(s, { t: "layout.reset" });
    expect(s.moved).toEqual({ layers: { N1: { x: 10, y: 20 } }, depth: {} });
  });

  it("lens, pan and mode", () => {
    const s = run({ t: "lens", lens: 4 }, { t: "pan", panX: 3, panY: -2 }, { t: "mode", mode: "graph" });
    expect(s.view).toEqual({ panX: 3, panY: -2, lens: 4 });
    expect(s.mode).toBe("graph");
  });

  it("starts on the flows at the given lens and layout", () => {
    expect(initialGraph(0, { layers: {}, depth: {} }, "depth")).toEqual(
      { view: { panX: 0, panY: 0, lens: 0 }, mode: "flows", layout: "depth", moved: { layers: {}, depth: {} } });
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/workspace && npm run build && npx playwright test e2e/workspace-graph.spec.ts e2e/workspace.spec.ts`

Expected: FAIL — `Test Files  3 failed | 5 passed (8)` and `Tests  2 failed | 26 passed (28)` and `Cannot find module './reducer' imported from src/workspace/graph/reducer.` and `expected { kind: 'whole' } to deeply equal { kind: 'whole', view: 'graph' }`

- [ ] **Step 3: Implement**

`frontend/src/workspace/WholePage.tsx`:

```diff
diff --git a/frontend/src/workspace/WholePage.tsx b/frontend/src/workspace/WholePage.tsx
index 8203acd..2004c19 100644
--- a/frontend/src/workspace/WholePage.tsx
+++ b/frontend/src/workspace/WholePage.tsx
@@ -4,9 +4,20 @@ import { driftSummary } from "../board/drift";
 import { bandsOf, linkLines } from "../board/overview";
 import { sideEffectFiles } from "../board/sideEffects";
 import Comments from "../components/Comments";
+import type { Board } from "../board/types";
 import { useWs } from "./context";
+import { pickFlow } from "./flows";
+import GraphView from "./graph/GraphView";
 import NameText from "./NameText";
 
+/** A review shown as one board: its graph, on the whole change page or filling the centre (`?view=graph`). */
+export function ReviewGraph({ board }: { board: Board }) {
+  const ws = useWs(), open = ws.addr.open;
+  const index = pickFlow(board.flows, ws.addr.flow, open && "node" in open ? open.node : null);
+  return <GraphView board={board} prefKey={String(ws.data.id)} flowIndex={index}
+                    onFlow={(i) => ws.go({ ...ws.addr, flow: i + 1 }, true)} />;
+}
+
 /** The review's home (spec 2026-10-04-review-workspace §3.1): what the change is for and why it is risky first. */
 export default function WholePage() {
   const ws = useWs(), d = ws.data, about = d.about, risk = d.detail!.review.risk;
@@ -54,6 +65,13 @@ export default function WholePage() {
           ))}
         </section>
       )}
+      {d.board && d.board.nodes.length > 0 && (
+        <section aria-labelledby="ws-map" id="map">
+          <h2 id="ws-map">The map <Link className="ws-open-full" to={ws.link({ ...ws.addr, place: { kind: "whole", view: "graph" } })}
+                                        title="Open the full graph" aria-label="Open the full graph">Open full graph ›</Link></h2>
+          <div className="ws-mapgraph"><ReviewGraph board={d.board} /></div>
+        </section>
+      )}
       {sideEffects.length > 0 && (
         <section aria-labelledby="ws-fx">
           <h2 id="ws-fx">Files with side effects</h2>
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index 850a070..7f0dd62 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -17,7 +17,7 @@ import { useScreen } from "./media";
 import { loadMemory, recall, remember, saveMemory } from "./memory";
 import Rail from "./Rail";
 import { useReview } from "./useReview";
-import WholePage from "./WholePage";
+import WholePage, { ReviewGraph } from "./WholePage";
 import "./workspace.css";
 
 /** Where the workspace lives (spec 2026-10-04-review-workspace §6: `/w/` while it is built, then `/r/`). */
@@ -52,7 +52,7 @@ export default function Workspace() {
     cls: d?.cls ?? [], clusters: data.overview?.clusters ?? [],
   }), [addr.place, root, d, id, data.stories, data.findings, data.overview]);
   const hash = location.hash.slice(1) || null;
-  const level = addr.open ? "detail" : addr.place.kind === "whole" && !(location.state as { page?: boolean } | null)?.page ? "rail" : "item";
+  const level = addr.open ? "detail" : addr.place.kind === "whole" && !addr.place.view && !(location.state as { page?: boolean } | null)?.page ? "rail" : "item";
 
   if (data.error) return <main className="page error">{data.error}</main>;
   if (!d) return <main className="page muted">Loading…</main>;
@@ -117,6 +117,8 @@ function Centre() {
     || (p.kind === "finding" && d.findings.some((f) => f.id === p.fid)) || (p.kind === "cl" && !!d.detail?.cls.some((c) => c.cl === p.cl))
     || (p.kind === "cluster" && !!d.overview?.clusters.some((c) => c.id === p.cid));
   if (!exists) return <Missing what={p} />;
+  if (p.kind === "whole" && p.view === "graph")
+    return d.board ? <div className="ws-page graph"><ReviewGraph board={d.board} /></div> : <Missing what={p} />;
   if (p.kind === "whole") return <WholePage />;
   return <div className="ws-page"><p className="muted">This page is built in a later step.</p></div>;
 }
```

`frontend/src/workspace/address.ts`:

```diff
diff --git a/frontend/src/workspace/address.ts b/frontend/src/workspace/address.ts
index 0b628b0..927ce3e 100644
--- a/frontend/src/workspace/address.ts
+++ b/frontend/src/workspace/address.ts
@@ -2,7 +2,7 @@
  * work. Ids appear here and nowhere in visible text. */
 
 export type Place =
-  | { kind: "whole" }
+  | { kind: "whole"; view?: "graph" }
   | { kind: "story"; sid: string; view: "steps" | "graph" }
   | { kind: "finding"; fid: string }
   | { kind: "cl"; cl: number }
@@ -23,7 +23,7 @@ export interface Address {
 
 function readPlace(path: string, q: URLSearchParams): Place {
   const parts = path.split("/").filter(Boolean);
-  if (!parts.length) return { kind: "whole" };
+  if (!parts.length) return q.get("view") === "graph" ? { kind: "whole", view: "graph" } : { kind: "whole" };
   const [kind, id, ...rest] = parts;
   if (!id || rest.length) return { kind: "unknown", path };
   if (kind === "s") return { kind: "story", sid: id, view: q.get("view") === "graph" ? "graph" : "steps" };
@@ -58,7 +58,7 @@ const placePath = (p: Place): string =>
 /** The link to `a` under `base` ("/r/7"), defaults left out. */
 export function href(base: string, a: Address): string {
   const q = new URLSearchParams();
-  if (a.place.kind === "story" && a.place.view === "graph") q.set("view", "graph");
+  if ((a.place.kind === "story" || a.place.kind === "whole") && a.place.view === "graph") q.set("view", "graph");
   if (a.flow) q.set("flow", String(a.flow));
   if (a.open) q.set("open", "node" in a.open ? a.open.node : `file:${a.open.file}${a.open.line ? `:${a.open.line}` : ""}`);
   if (a.tab !== "diff") q.set("tab", a.tab);
```

`frontend/src/workspace/crumbs.ts`:

```diff
diff --git a/frontend/src/workspace/crumbs.ts b/frontend/src/workspace/crumbs.ts
index 4b8d6ca..edfddde 100644
--- a/frontend/src/workspace/crumbs.ts
+++ b/frontend/src/workspace/crumbs.ts
@@ -24,8 +24,8 @@ export function short(text: string, n = 46): string {
 const MISSING: Crumb = { label: "Not found", to: null };
 
 export function crumbs(place: Place, c: CrumbContext): Crumb[] {
-  if (place.kind === "whole") return [{ label: c.title, to: null }];
   const home = { label: c.title, to: c.base };
+  if (place.kind === "whole") return place.view === "graph" ? [home, { label: "Graph", to: null }] : [{ label: c.title, to: null }];
   const section = (label: string, anchor: string): Crumb => ({ label, to: `${c.base}#${anchor}` });
   switch (place.kind) {
     case "story": {
```

`frontend/src/workspace/graph/Canvas.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { type Band, flowSets } from "../../board/layout";
import { BAND, type Lens, type Projected, type Viewport } from "../../board/lens";
import type { Board, BoardFlow } from "../../board/types";
import type { GraphAction, GraphState } from "./reducer";

interface Props {
  board: Board;
  lens: Lens;
  pos: Map<string, Projected>;
  vp: Viewport;
  bands: Band[];
  state: GraphState;
  dispatch: (a: GraphAction) => void;
  panBy: (dx: number, dy: number) => void;
  /** The flow to highlight (flows mode). */
  flow: BoardFlow | undefined;
  /** The node open in the detail panel, and the nodes of the file open there. */
  selected: string | null;
  lit: Set<string>;
  /** A node click: open its code, or close it when it is the one open (spec 2026-10-04-review-workspace §3.2). */
  onSelect: (id: string) => void;
  /** "+N callers / +N callees": its Neighbours tab. */
  onNeighbours?: (id: string) => void;
  /** A visitor's link to the board of the cluster it belongs to. */
  onHome?: (cluster: string, id: string) => void;
  /** A cluster id's name, for the visitor link. */
  homeName?: (cluster: string) => string;
  /** A story graph (spec 2026-10-04-change-stories §3.1): field lines and calls off the selected flow show only for
   * the selected node; "+N more changed functions" calls `onMore`. */
  quiet?: boolean;
  onMore?: () => void;
  /** Phones: two-finger pinch; a node moves only after a long press. */
  touch?: {
    onPinchStart: (mid: { x: number; y: number }) => void;
    onPinch: (d0: number, d1: number, mid: { x: number; y: number }) => void;
  };
}

const LONG_PRESS = 450;

const KIND = { modified: "Δ modified", added: "Δ added", removed: "Δ removed", signature: "Δ signature" } as const;

/** Layer bands, edges and nodes, all drawn through the lens; pans on drag, moves a node when dragged by it. */
export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, panBy, flow, selected, lit, onSelect, onNeighbours,
  touch, onHome, homeName, quiet, onMore }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const down = useRef<{ x: number; y: number; px: number; py: number; id: number; node: string | null; act: string | null;
                        dragging: boolean; ox: number; oy: number; armed: boolean; timer: number } | null>(null);
  const pts = useRef(new Map<number, { x: number; y: number }>());     // touch: active pointers
  const pinch = useRef<{ d: number } | null>(null);
  const spread = () => {
    const [a, b] = [...pts.current.values()];
    const r = root.current!.getBoundingClientRect();
    return { d: Math.hypot(a.x - b.x, a.y - b.y), mid: { x: (a.x + b.x) / 2 - r.left, y: (a.y + b.y) / 2 - r.top } };
  };
  const end = () => {
    if (down.current) window.clearTimeout(down.current.timer);
    down.current = null;
    document.body.classList.remove("bd-dragging");
    setGrab(null);
    setPanning(false);
  };
  const [grab, setGrab] = useState<string | null>(null);   // node being dragged
  const [panning, setPanning] = useState(false);
  const { W } = vp;

  useEffect(() => {                                          // wheel / trackpad pans (non-passive so the page doesn't scroll)
    const el = root.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      panBy(-(e.deltaX + (e.shiftKey ? e.deltaY : 0)), e.shiftKey ? 0 : -e.deltaY);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [panBy]);

  const graph = state.mode === "graph";
  const { onPath, pairs } = flowSets(flow, graph);
  const landings = new Set(graph ? board.flows.map((f) => f.lands) : flow ? [flow.lands] : []);
  const front = selected;
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const badge = new Map<string, string>();
  for (const a of board.impacts) if (a.landing && !badge.has(a.node)) badge.set(a.node, a.text);

  // bands: sampled every 16 px so they follow the vertical squeeze
  const xs: number[] = [];
  for (let x = 0; x <= W + 16; x += 16) xs.push(Math.min(x, W));
  const line = (wy: number, rev = false) => (rev ? [...xs].reverse() : xs)
    .map((x, i) => `${i ? "L" : "M"}${x} ${lens.bandY(x, wy).toFixed(1)}`).join(" ");

  return (
    <div ref={root} className={`bd-canvas${panning ? " drag" : ""}`}
      onPointerDown={(e) => {
        e.preventDefault();                                  // no text selection starting on the board
        if (touch) {
          pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
          if (pts.current.size === 2) {                      // a second finger: pinch, never a drag or a tap
            end();
            const s = spread();
            pinch.current = { d: s.d };
            touch.onPinchStart(s.mid);
            root.current?.setPointerCapture(e.pointerId);
            return;
          }
          if (pts.current.size > 2) return;
        }
        const t = e.target as HTMLElement, n = t.closest<HTMLElement>(".bd-node"), r = root.current!.getBoundingClientRect();
        const at = n?.dataset.id ? pos.get(n.dataset.id) : undefined;     // keep the grab point under the pointer
        const d = { x: e.clientX, y: e.clientY, px: state.view.panX, py: state.view.panY, id: e.pointerId,
                    node: n?.dataset.id ?? null, act: t.closest<HTMLElement>("[data-act]")?.dataset.act ?? null,
                    dragging: false,
                    ox: at ? at.x - (e.clientX - r.left) : 0, oy: at ? at.y - (e.clientY - r.top) : 0,
                    armed: !touch, timer: 0 };
        if (touch && d.node)                                 // touch: a node moves only after a long press
          d.timer = window.setTimeout(() => { if (down.current === d && !d.dragging) { d.armed = true; setGrab(d.node); } }, LONG_PRESS);
        down.current = d;
      }}
      onPointerMove={(e) => {
        if (touch && pts.current.has(e.pointerId)) pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (touch && pinch.current && pts.current.size === 2) {
          const { d, mid } = spread();
          touch.onPinch(pinch.current.d, d, mid);
          pinch.current.d = d;
          return;
        }
        const d = down.current;
        if (!d || d.id !== e.pointerId) return;
        if (!d.dragging) {
          if (Math.hypot(e.clientX - d.x, e.clientY - d.y) <= 6) return;
          d.dragging = true;
          window.clearTimeout(d.timer);
          if (!d.armed) d.node = null;                       // touch without a long press: pan, don't move the node
          root.current?.setPointerCapture(d.id);             // only once dragging: early capture swallows clicks
          document.body.classList.add("bd-dragging");
          window.getSelection()?.removeAllRanges();
          if (d.node) setGrab(d.node); else setPanning(true);
        }
        if (d.node) {
          const r = root.current!.getBoundingClientRect(), sx = e.clientX - r.left + d.ox, sy = e.clientY - r.top + d.oy;
          dispatch({ t: "node.move", id: d.node, x: Math.round(lens.unprojectX(sx)), y: Math.round(lens.unprojectY(sx, sy)) });
        } else dispatch({ t: "pan", panX: d.px + (e.clientX - d.x), panY: d.py + (e.clientY - d.y) });
      }}
      onPointerUp={(e) => {
        if (touch) {
          pts.current.delete(e.pointerId);
          if (pinch.current) { if (pts.current.size < 2) pinch.current = null; return; }
        }
        const d = down.current;
        if (d && d.id !== e.pointerId) return;
        end();
        if (!d || d.dragging || !d.node) return;
        const n = byId.get(d.node);
        if (n?.kind === "more") { onMore?.(); return; }
        if (d.act) {                                         // a badge or a visitor's home link, not the node
          if (d.act === "home" && n?.home) onHome?.(n.home, d.node);
          else if (d.act === "callers" || d.act === "callees") onNeighbours?.(d.node);
          return;
        }
        const id = d.node;                                   // after the tap's click, or it lands in the panel that opens under it
        if (touch) window.setTimeout(() => onSelect(id), 0); else onSelect(id);
      }}
      onPointerCancel={(e) => {
        pts.current.delete(e.pointerId);
        if (pts.current.size < 2) pinch.current = null;
        end();
      }}>
      <svg className="bd-bands">
        {bands.map(({ key, row: i }) => (
          <g key={key}>
            <path className={`fill${i % 2 ? " alt" : ""}`} d={`${line(i * BAND)} ${line((i + 1) * BAND, true).replace(/^M/, "L")} Z`} />
            <path className="rule" d={line(i * BAND)} />
          </g>
        ))}
        <path className="rule" d={line(bands.length * BAND)} />
      </svg>
      {bands.map(({ key, row: i, label }) => {
        const y = lens.bandY(12, i * BAND) + 6, k = Math.max(0.7, (lens.bandY(12, 1) - lens.bandY(12, 0)));
        return <div key={key} className="bd-blabel" style={{ top: y, transform: `scale(${k})` }}>
          {label}
        </div>;
      })}
      <svg className="bd-edges">
        {board.edges.map((e, i) => {
          const p1 = pos.get(e.src), p2 = pos.get(e.dst);
          if (!p1 || !p2) return null;
          const data = e.kind === "writes" || e.kind === "reads";
          const fx = e.kind === "reads" && landings.has(e.src) && (graph || onPath.has(e.dst));
          const inFlow = pairs.has(`${e.src}>${e.dst}`) || pairs.has(`${e.dst}>${e.src}`);
          if (quiet && !inFlow && e.src !== front && e.dst !== front && (data || !graph)) return null;
          const my = (p1.y + p2.y) / 2;
          return <path key={i} d={`M${p1.x} ${p1.y} C ${p1.x} ${my}, ${p2.x} ${my}, ${p2.x} ${p2.y}`}
            className={`bd-edge${fx ? " fx" : data ? " data" : ""}${inFlow ? " flow" : ""}${!inFlow && !data && !graph ? " dim" : ""}`} />;
        })}
      </svg>
      {board.nodes.map((n) => {
        const p = pos.get(n.id);
        if (!p) return null;
        const sel = n.id === selected, on = onPath.has(n.id);
        const cls = ["bd-node", n.change ? "chg" : "", n.kind === "field" || n.kind === "struct" ? "field" : "", n.kind === "more" ? "more" : "",
          n.note ? "noted" : "", on ? "onflow" : "", n.home ? "visitor" : "",
          !graph && !on && !n.change && !sel && !lit.has(n.id) ? "dim" : "", state.moved[state.layout][n.id] !== undefined ? "moved" : "",
          sel ? "has-card front" : "", lit.has(n.id) ? "lit" : "", grab === n.id ? "grab" : ""].filter(Boolean).join(" ");
        const fx = badge.get(n.id);
        return (
          <div key={n.id} data-id={n.id} className={cls} title={sel ? `Close ${n.label}'s code` : `Open ${n.label}'s code`}
               role="button" aria-label={sel ? `Close ${n.label}'s code` : `Open ${n.label}'s code`} aria-pressed={sel}
               style={{ left: p.x, top: p.y, transform: `translate(-50%, -50%) scale(${p.s})`, zIndex: Math.round(p.s * 20),
                        ["--hit" as string]: `${40 / Math.max(p.s, 0.1)}px` }}>
            {n.change && <span className="kind">{KIND[n.change.kind]}</span>}
            <span className="lbl">{n.label}</span>
            {n.note && <span className="note">{n.note.replace(/`/g, "")}</span>}
            {!!n.fields?.length && <span className="fields">{n.fields.map((f) => <span key={f.id}>.{f.label}</span>)}</span>}
            {n.change && <span className="stat"><b className="p">+{n.change.add}</b><b className="m">−{n.change.rem}</b></span>}
            {!n.change && n.warn > 0 && <span className="warn-dot">{n.warn}</span>}
            {fx && landings.has(n.id) && !n.note && <div className="fxbadge">⚠ {fx}</div>}
            {n.home && onHome && <span className="bd-home" data-act="home" role="button" title={`Go to ${homeName?.(n.home) ?? n.home}`}
                                       aria-label={`Go to ${homeName?.(n.home) ?? n.home}`}>
              · {homeName?.(n.home) ?? n.home} ›</span>}
            {onNeighbours && (!!n.more_callers || !!n.more_callees) && (
              <span className="bd-more-nb">
                {!!n.more_callers && <span data-act="callers" role="button" title={`Show ${n.label}'s callers`}
                                           aria-label={`Show ${n.label}'s callers`}>+{n.more_callers} callers</span>}
                {!!n.more_callees && <span data-act="callees" role="button" title={`Show ${n.label}'s callees`}
                                           aria-label={`Show ${n.label}'s callees`}>+{n.more_callees} callees</span>}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

`frontend/src/workspace/graph/GraphView.tsx`:

```tsx
import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import { bandsFor, centrePan, preferDepth, worldNodes } from "../../board/layout";
import { makeLens, type Viewport } from "../../board/lens";
import { keys, loadLayout, loadLens, loadMovedAll, save } from "../../board/prefs";
import type { Board } from "../../board/types";
import { fitZoom, pinchView, pinchZoom, zoomLens } from "../../board/zoom";
import { useWs } from "../context";
import FlowStrip from "../FlowStrip";
import Canvas from "./Canvas";
import { type GraphAction, initialGraph, reduceGraph } from "./reducer";

interface Props {
  board: Board;
  /** Whose saved layout and moves: "12.S1", "12.C3", "12". */
  prefKey: string;
  flowIndex: number;
  onFlow: (i: number) => void;
  /** A story graph (change stories §3.1): opens whole, no lens, quiet field lines; "+N more" calls `onMore`. */
  quiet?: boolean;
  onMore?: () => void;
  /** A cluster's visitors link to their own cluster. */
  onHome?: (cluster: string, id: string) => void;
  homeName?: (cluster: string) => string;
}

/** A graph in the centre (spec 2026-10-04-review-workspace §5: Board.tsx rebuilt as canvas, flow strip and toolbar).
 * A node click opens its code in the detail panel and a second click closes it; "+N callers" opens Neighbours. */
export default function GraphView({ board, prefKey, flowIndex, onFlow, quiet, onMore, onHome, homeName }: Props) {
  const ws = useWs(), phone = ws.screen === "phone";
  const [state, dispatch] = useReducer(reduceGraph, undefined, () => {
    const s = initialGraph(quiet ? 0 : loadLens(), loadMovedAll(prefKey), loadLayout(prefKey) ?? (preferDepth(board) ? "depth" : "layers"));
    return board.flows.length ? s : { ...s, mode: "graph" as const };
  });
  const stateRef = useRef(state);
  stateRef.current = state;
  const [vp, setVp] = useState<Viewport>({ W: 0, H: 0 });
  const [stage, setStage] = useState<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const anim = useRef(0);
  const open = ws.addr.open;
  const selected = open && "node" in open ? board.nodes.find((n) => n.id === open.node || n.fields?.some((f) => f.id === open.node))?.id ?? null : null;
  const lit = useMemo(() => new Set(open && "file" in open ? board.nodes.filter((n) => n.path === open.file).map((n) => n.id) : []),
                      [open, board]);

  useEffect(() => save(keys.moved(prefKey), state.moved), [prefKey, state.moved]);
  useEffect(() => { if (!quiet) save(keys.lens, state.view.lens); }, [quiet, state.view.lens]);
  const bands = useMemo(() => bandsFor(board, state.layout), [board, state.layout]);
  const world = useMemo(() => worldNodes(board, state.layout, state.moved[state.layout]), [board, state.layout, state.moved]);
  const baseLens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
  const lens = useMemo(() => (phone || quiet ? zoomLens(baseLens, zoom, vp) : baseLens), [phone, quiet, baseLens, zoom, vp]);
  const pos = useMemo(() => new Map([...world.values()].map((n) => [n.id, lens.project(n.x, n.y)])), [world, lens]);
  const vpRef = useRef(vp);
  vpRef.current = vp;
  const worldRef = useRef(world);
  worldRef.current = world;

  const panTo = useCallback((ids: string[]) => {          // eased pan that centres `ids`
    const { W, H } = vpRef.current, target = centrePan(ids, worldRef.current, W, H);
    if (!target || !W) return;
    window.cancelAnimationFrame(anim.current);
    const { panX: sx, panY: sy } = stateRef.current.view, t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 380), e = 1 - Math.pow(1 - k, 3);
      dispatch({ t: "pan", panX: sx + (target.panX - sx) * e, panY: sy + (target.panY - sy) * e });
      if (k < 1) anim.current = window.requestAnimationFrame(step);
    };
    anim.current = window.requestAnimationFrame(step);
  }, []);
  const panBy = useCallback((dx: number, dy: number) => {
    window.cancelAnimationFrame(anim.current);
    const v = stateRef.current.view;
    dispatch({ t: "pan", panX: v.panX + dx, panY: v.panY + dy });
  }, []);

  useLayoutEffect(() => {                                // canvas size: keep the middle where it was as panels open and close
    const el = stage;
    if (!el) return;
    let first = true;
    const ro = new ResizeObserver(() => {
      const W = el.clientWidth, H = el.clientHeight, prev = vpRef.current;
      if (prev.W && (W !== prev.W || H !== prev.H)) panBy((W - prev.W) / 2, (H - prev.H) / 2);
      vpRef.current = { W, H };
      setVp({ W, H });
      if (first && W) {
        first = false;
        const f = board.flows[flowIndex];
        const ids = stateRef.current.mode === "flows" && f && !quiet ? f.path : board.nodes.map((n) => n.id);
        const t = centrePan(ids, worldRef.current, W, H);
        if (t) dispatch({ t: "pan", ...t });
        if (quiet || phone) setZoom(fitZoom([...worldRef.current.values()], { W, H }));
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [stage, board, panBy, quiet, phone]);                // eslint-disable-line react-hooks/exhaustive-deps

  const shownFlow = useRef(flowIndex);                   // a new flow: pan to it
  useEffect(() => {
    if (shownFlow.current === flowIndex) return;
    shownFlow.current = flowIndex;
    if (board.flows[flowIndex]) { dispatch({ t: "mode", mode: "flows" }); panTo(board.flows[flowIndex].path); }
  }, [flowIndex, board, panTo]);
  const centred = useRef<string | null>(null);           // a node opened from elsewhere (a link, a finding): centre it once
  useEffect(() => {
    if (!selected || selected === centred.current || !vp.W) return;
    centred.current = selected;
    if (pos.get(selected) && (pos.get(selected)!.x < 0 || pos.get(selected)!.x > vp.W || pos.get(selected)!.y < 0 || pos.get(selected)!.y > vp.H))
      panTo([selected]);
  }, [selected, vp, pos, panTo]);
  const relaid = useRef(state.layout);
  useEffect(() => {
    if (relaid.current === state.layout) return;
    relaid.current = state.layout;
    panTo(state.mode === "graph" ? board.nodes.map((n) => n.id) : board.flows[flowIndex]?.path ?? []);
  }, [state.layout, state.mode, flowIndex, board, panTo]);

  const act = useCallback((a: GraphAction) => dispatch(a), []);
  const setLayout = (layout: "layers" | "depth") => { if (layout !== state.layout) { save(keys.layout(prefKey), layout); act({ t: "layout", layout }); } };
  const setMode = (mode: "flows" | "graph") => {
    act({ t: "mode", mode });
    panTo(mode === "graph" ? board.nodes.map((n) => n.id) : board.flows[flowIndex]?.path ?? []);
  };
  const onSelect = (id: string) => ws.go(ws.opened(id === selected ? null : { node: id }));
  const onNeighbours = (id: string) => ws.go(ws.opened({ node: id }, "neighbours"));

  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const anchor = useRef({ x: 0, y: 0 });
  const lensRef = useRef(lens);
  lensRef.current = lens;
  const onPinchStart = useCallback((mid: { x: number; y: number }) => {
    anchor.current = { x: lensRef.current.unprojectX(mid.x), y: lensRef.current.unprojectY(mid.x, mid.y) };
  }, []);
  const onPinch = useCallback((d0: number, d1: number, mid: { x: number; y: number }) => {
    const z1 = pinchZoom(zoomRef.current, d0, d1);
    const next = pinchView(stateRef.current.view, z1, anchor.current, mid, vpRef.current, [...worldRef.current.values()].map((n) => n.x));
    zoomRef.current = z1;
    setZoom(z1);
    window.cancelAnimationFrame(anim.current);
    stateRef.current = { ...stateRef.current, view: next };
    dispatch({ t: "pan", panX: next.panX, panY: next.panY });
  }, []);

  return (
    <div className="bd ws-graph">
      {board.flows.length > 0 && (
        <FlowStrip board={board} flows={board.flows} index={flowIndex} steps onFlow={(i) => { onFlow(i); }} />
      )}
      <div className="bd-stage" ref={setStage}>
        {vp.W > 0 && (
          <Canvas board={board} lens={lens} pos={pos} vp={vp} bands={bands} state={state} dispatch={act} panBy={panBy}
                  flow={state.mode === "flows" ? board.flows[flowIndex] : undefined} selected={selected} lit={lit}
                  onSelect={onSelect} onNeighbours={onNeighbours} onHome={onHome} homeName={homeName} quiet={quiet} onMore={onMore}
                  touch={phone ? { onPinchStart, onPinch } : undefined} />
        )}
        <div className="bd-tools">
          <div className="bd-toolbar">
            {board.flows.length > 0 && (
              <span className="bd-seg">
                <button className={`bd-ibtn${state.mode === "flows" ? " on" : ""}`} aria-pressed={state.mode === "flows"}
                        onClick={() => setMode("flows")}>Flow</button>
                <button className={`bd-ibtn${state.mode === "graph" ? " on" : ""}`} aria-pressed={state.mode === "graph"}
                        onClick={() => setMode("graph")}>Whole graph</button>
              </span>
            )}
            <span className="bd-seg">
              <button className={`bd-ibtn${state.layout === "layers" ? " on" : ""}`} aria-pressed={state.layout === "layers"}
                      onClick={() => setLayout("layers")}>Layers</button>
              <button className={`bd-ibtn${state.layout === "depth" ? " on" : ""}`} aria-pressed={state.layout === "depth"}
                      onClick={() => setLayout("depth")}>Call depth</button>
            </span>
            {Object.keys(state.moved[state.layout]).length > 0 &&
              <button className="bd-ibtn float" onClick={() => act({ t: "layout.reset" })}>Reset layout</button>}
            {!quiet && <>
              <span className="lbl">Lens</span>
              <span className="bd-seg">{([0, 2, 4] as const).map((m) => (
                <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} aria-pressed={state.view.lens === m}
                        onClick={() => act({ t: "lens", lens: m })}>{m ? `${m}×` : "Off"}</button>
              ))}</span>
            </>}
          </div>
          <div className="bd-legend">
            <span className="sw chg" />changed<span className="sw flow" />selected flow<span className="sw field" />field<span className="sw fx" />side effect
          </div>
        </div>
      </div>
    </div>
  );
}
```

`frontend/src/workspace/graph/reducer.ts`:

```ts
/** A graph's view state (spec 2026-10-04-review-workspace §5: the board reducer, trimmed). Pure: every interaction is
 * one transition. The flow and the selected node live in the address, not here. */
import type { LayoutKind, Moved } from "../../board/layout";
import type { LensStrength, View } from "../../board/lens";

export interface GraphState {
  view: View;
  /** The selected flow highlighted, or the whole graph. */
  mode: "flows" | "graph";
  layout: LayoutKind;
  /** Per layout: node id -> world position chosen by this viewer. */
  moved: Record<LayoutKind, Moved>;
}

export type GraphAction =
  | { t: "mode"; mode: "flows" | "graph" }
  | { t: "lens"; lens: LensStrength }
  | { t: "node.move"; id: string; x: number; y: number }
  | { t: "layout"; layout: LayoutKind }
  | { t: "layout.reset" }
  | { t: "pan"; panX: number; panY: number };

export function initialGraph(lens: LensStrength = 2, moved: Record<LayoutKind, Moved> = { layers: {}, depth: {} },
                             layout: LayoutKind = "layers"): GraphState {
  return { view: { panX: 0, panY: 0, lens }, mode: "flows", layout, moved };
}

export function reduceGraph(s: GraphState, a: GraphAction): GraphState {
  switch (a.t) {
    case "mode":
      return { ...s, mode: a.mode };
    case "lens":
      return { ...s, view: { ...s.view, lens: a.lens } };
    case "node.move":
      return { ...s, moved: { ...s.moved, [s.layout]: { ...s.moved[s.layout], [a.id]: { x: a.x, y: a.y } } } };
    case "layout.reset":
      return { ...s, moved: { ...s.moved, [s.layout]: {} } };
    case "layout":
      return { ...s, layout: a.layout };
    case "pan":
      return { ...s, view: { ...s.view, panX: a.panX, panY: a.panY } };
  }
}
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 78e49ab..09ea592 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -155,3 +155,11 @@ a.ws-nb:hover { border-color: var(--accent); }
 .ws-flow-check { color: var(--muted); }
 .ws-flow-steps { line-height: 1.9; }
 .ws-flow-steps .arrow { color: var(--muted); }
+
+/* graphs */
+.ws-graph { flex: 1; min-height: 0; display: flex; flex-direction: column; background: var(--bd-bg); }
+.ws-graph .ws-flow { background: var(--bd-surface); }
+.ws-graph .bd-stage { flex: 1; min-height: 0; position: relative; overflow: hidden; }
+.bd-node.lit { outline: 2px solid var(--accent); outline-offset: 2px; }
+.ws-mapgraph { height: 460px; display: flex; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
+.ws-open-full { float: right; text-transform: none; letter-spacing: 0; font-weight: 500; font-size: 13px; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/workspace && npm run build && npx playwright test e2e/workspace-graph.spec.ts e2e/workspace.spec.ts`

Expected: `Test Files  8 passed (8)` and `Tests  31 passed (31)` and `✓ built in …` and `8 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  29 passed (29)` and `Tests  134 passed (134)` and `✓ built in …` and `68 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-graph.spec.ts frontend/e2e/workspace.spec.ts frontend/src/workspace/WholePage.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/address.test.ts frontend/src/workspace/address.ts frontend/src/workspace/crumbs.test.ts frontend/src/workspace/crumbs.ts frontend/src/workspace/graph/Canvas.tsx frontend/src/workspace/graph/GraphView.tsx frontend/src/workspace/graph/reducer.test.ts frontend/src/workspace/graph/reducer.ts frontend/src/workspace/workspace.css
git commit -m "feat(ui): graphs in the workspace — trimmed reducer and canvas; a node click toggles its code; the review's graph on the whole change"
```

---

### Task 12: The story page

Spec §3.2. The header: risk, title, summary with Explain, counts and CL chips, the Steps | Graph switch beside
the title (behaviour and "Other changes" stories) and `‹ S1 of 4 ›` in a fixed-width group. Steps: the flow strip
(without the summary it repeats), numbered steps that open the detail panel and mark the step, "Also changed" and the
story's findings linking to their pages. Graph: the story's graph in `GraphView`. Repeated-edit and tests stories keep
their bodies (`StoryBodies`), their links moved to workspace addresses. Flow and view switches replace history.

**Files:**
- Create: `frontend/src/workspace/StoryBodies.tsx`
- Create: `frontend/src/workspace/StoryPage.tsx`
- Create: `frontend/src/workspace/StorySteps.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/helpers.ts`
- Test: `frontend/e2e/workspace-graph.spec.ts`
- Test: `frontend/e2e/workspace-story.spec.ts` (new)

**Interfaces:**
- Consumes: `GraphView`, `FlowStrip`, `pickFlow` (Tasks 10–11), `board/phone/flowSteps`, `stories/stories.ts`, `Badges`.
- Produces: `StorySteps({detail, flow})`, `MechanicalStory({detail})`, `TestsStory({detail})`, `StoryPage({sid, view})`;
  e2e helper `flowStripHolds(page)` moves to `helpers.ts`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/helpers.ts`:

```diff
diff --git a/frontend/e2e/helpers.ts b/frontend/e2e/helpers.ts
index e042e35..68400ca 100644
--- a/frontend/e2e/helpers.ts
+++ b/frontend/e2e/helpers.ts
@@ -45,3 +45,16 @@ export async function expectNamed(page: Page) {
        .map((e) => e.outerHTML.slice(0, 120)));
   expect(unnamed).toEqual([]);
 }
+
+/** The flow strip's ‹ › keep their place across flows and its row never scrolls sideways (spec §3.6, §8). */
+export async function flowStripHolds(page: Page) {
+  const strip = page.getByRole("region", { name: "Flow" });
+  const next = strip.getByRole("button", { name: "Next flow" });
+  const at = (await next.boundingBox())!.x;
+  const row = strip.locator(".ws-flow-row");
+  for (let i = 0; i < 3; i++) {
+    expect(await row.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
+    await next.click();
+    expect((await next.boundingBox())!.x).toBe(at);
+  }
+}
```

`frontend/e2e/workspace-graph.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace-graph.spec.ts b/frontend/e2e/workspace-graph.spec.ts
index 84664f9..9b5eb9f 100644
--- a/frontend/e2e/workspace-graph.spec.ts
+++ b/frontend/e2e/workspace-graph.spec.ts
@@ -1,23 +1,11 @@
 import { expect, type Page, test } from "@playwright/test";
-import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";
+import { expectNamed, expectNoNodeIds, flowStripHolds, startWorkspace } from "./helpers";
 
 /** Graphs in the workspace (spec 2026-10-04-review-workspace §3.2, §3.6): a node click opens its code and a second
  * click closes it; "+N callers" opens Neighbours; the flow strip keeps its controls in place and never overflows. */
 
 const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });
 
-export async function flowStripHolds(page: Page) {
-  const strip = page.getByRole("region", { name: "Flow" });
-  const next = strip.getByRole("button", { name: "Next flow" });
-  const at = (await next.boundingBox())!.x;
-  const row = strip.locator(".ws-flow-row");
-  for (let i = 0; i < 3; i++) {
-    expect(await row.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
-    await next.click();
-    expect((await next.boundingBox())!.x).toBe(at);
-  }
-}
-
 test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
```

`frontend/e2e/workspace-story.spec.ts`:

```ts
import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, flowStripHolds, startWorkspace } from "./helpers";

/** A story in the workspace (spec 2026-10-04-review-workspace §3.2, §2.4). */

const step = (page: Page, label: string) => page.getByRole("list", { name: "Flow steps" }).getByRole("link", { name: `Open ${label}'s code` });
const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("steps open the detail panel and mark the step; flows replace history; findings link to their pages", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.locator(".ws-story-head h2")).toContainText("uart_send now writes Uart::errors");
    await expect(page.getByRole("tab", { name: "Steps" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".ws-story-meta .ws-chip")).toHaveText(["CL 101"]);
    await step(page, "uart_send").click();
    await expect(page).toHaveURL(/\/s\/S1\?open=N\d+$/);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Close uart_send's code" })).toHaveAttribute("aria-current", "true");
    await page.getByRole("link", { name: "Close uart_send's code" }).click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);

    await flowStripHolds(page);
    await page.goBack();                                       // flows replaced the entry: Back undoes the close
    await expect(page.locator(".ws-detail")).toBeVisible();
    await page.goForward();
    await page.getByRole("link", { name: /^Go to finding F1:/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F1$`));
    await expectNoNodeIds(page);
  });

  test("the graph: a node click opens and closes its code; ‹ › keep their place between stories", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}/s/S1`);
    await page.getByRole("tab", { name: "Graph" }).click();
    await expect(page).toHaveURL(/\/s\/S1\?view=graph$/);
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Graph");
    await node(page, "uart_send").click();
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await node(page, "uart_send").click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    await flowStripHolds(page);
    await expectNamed(page);

    await page.getByRole("tab", { name: "Steps" }).click();
    await expect(page.getByRole("list", { name: "Flow steps" })).toBeVisible();     // measure in the Steps layout
    const next = page.getByRole("link", { name: /^Next story/ });
    const x = (await next.boundingBox())!.x;
    await next.click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await expect(page.locator(".ws-story-head h2")).toContainText("hal_write");
    expect((await page.getByRole("link", { name: /^Next story/ }).boundingBox())!.x).toBe(x);
  });

  test("leaving a story for a CL and coming back returns to the same view, flow and open node", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}/s/S1?view=graph`);
    await page.getByRole("button", { name: "Next flow" }).click();
    await node(page, "uart_send").click();
    await expect(page).toHaveURL(/view=graph&flow=2&open=N\d+$/);
    const there = page.url();
    await page.locator(".ws-rail").getByRole("link", { name: "Open CL 101" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/cl/101$`));
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(there);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await expect(page.locator(".ws-flow-pos")).toHaveText("flow 2 of 2");
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("rail → story → detail sheet, each top bar naming the place", async ({ page }) => {
    await startWorkspace(page);
    await page.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.locator(".ws-phonebar")).toContainText("‹ Stories");
    await step(page, "uart_send").click();
    const bar = page.locator(".ws-detail .ws-phonebar");
    await expect(bar).toContainText("‹ S1");
    await expect(bar).toContainText("uart_send");
    await bar.getByRole("link", { name: "Close the code" }).click();
    await expect(page.locator(".ws-centre .ws-phonebar")).toContainText("‹ Stories");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-story.spec.ts e2e/workspace-graph.spec.ts`

Expected: FAIL — `✓ built in …` and `4 failed` and `2 passed` and (4 failing, first: desktop › steps open the detail panel and mark the step; flows replace history; findings link to their pages)

- [ ] **Step 3: Implement**

`frontend/src/workspace/StoryBodies.tsx`:

```tsx
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { StoryDetail } from "../board/types";
import { groupSites, OPEN_SITES } from "../stories/stories";
import { useWs } from "./context";
import NameText from "./NameText";

/** A repeated edit (change stories §3.2): its sites by directory and file, "Hide tests", and the functions with other
 * edits too; a site opens its file at the line in the detail panel. */
export function MechanicalStory({ detail }: { detail: StoryDetail }) {
  const ws = useWs();
  const [hide, setHide] = useState(false);
  const dirs = useMemo(() => groupSites(detail.sites, hide), [detail.sites, hide]);
  const tests = detail.sites.filter((s) => s.test).length;
  const openAll = detail.sites.length <= OPEN_SITES;
  const story = (sid: string, label: string) => (
    <Link to={ws.link(ws.item({ kind: "story", sid, view: "steps" }))} title={`Go to story ${sid}`} aria-label={`Go to story ${sid}`}>
      {label}<span className="ws-handle">{sid}</span></Link>
  );
  return (
    <div className="ws-mech">
      <div className="ws-tools">
        {tests > 0 && <label><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> Hide tests ({tests})</label>}
        {detail.also_in.length > 0 && (
          <span>Also in {detail.also_in.length} function{detail.also_in.length === 1 ? "" : "s"} with other edits:{" "}
            {detail.also_in.map((r, i) => <span key={r.node}>{i > 0 && ", "}{r.story ? story(r.story, r.label) : <b className="mono">{r.label}</b>}</span>)}</span>
        )}
      </div>
      {dirs.map((dir) => (
        <section key={dir.dir} className="ws-dir" aria-label={`Sites in ${dir.dir || "the root"}`}>
          <h3 className="mono">{dir.dir || "/"} <span className="muted small">{dir.count}</span></h3>
          {dir.files.map((f) => (
            <details key={f.path} open={openAll}>
              <summary><b className="mono">{f.name}</b> <span className="muted small">{f.sites.length} site{f.sites.length === 1 ? "" : "s"}</span></summary>
              <ul className="ws-sites">{f.sites.map((s) => (
                <li key={s.line}>
                  <Link className="ws-where" to={ws.link(ws.opened(s.path ? { file: s.path, line: s.line } : null))}
                        title={`Open ${f.name} at line ${s.line}`} aria-label={`Open ${f.name} at line ${s.line}`}>
                    {s.function ?? "outside functions"} · line {s.line}</Link>
                  {s.test && <span className="ws-badge">test</span>}
                  <code className="del">− {s.before}</code>
                  <code className="add">+ {s.after}</code>
                  {s.effect && story(s.effect, "has an effect")}
                  {s.other_edits && story(s.other_edits, "other edits")}
                </li>
              ))}</ul>
            </details>
          ))}
        </section>
      ))}
    </div>
  );
}

/** The Tests story (change stories §3.3): test functions by file; each names the changed code it calls and opens its
 * code in the detail panel. */
export function TestsStory({ detail }: { detail: StoryDetail }) {
  const ws = useWs();
  const nodes = new Map(detail.board.nodes.map((n) => [n.id, n]));
  const byFile = new Map<string, typeof detail.functions>();
  for (const f of detail.functions) {
    const path = nodes.get(f.node)?.path ?? "(unknown file)";
    byFile.set(path, [...(byFile.get(path) ?? []), f]);
  }
  return (
    <div className="ws-tests">
      {[...byFile.entries()].map(([path, fns]) => (
        <section key={path} aria-label={`Tests in ${path}`}>
          <h3 className="mono">{path}</h3>
          <ul className="ws-steplist plain">{fns.map((f) => (
            <li key={f.node}>
              <Link to={ws.link(ws.opened({ node: f.node }))} title={`Open ${f.label}'s code`} aria-label={`Open ${f.label}'s code`}>
                <span className="ws-step-text"><b className="mono">{f.label}</b><span className="muted"><NameText text={f.note} /></span></span>
              </Link>
              {f.calls.length > 0 && (
                <div className="ws-calls">calls {f.calls.map((c, i) => (
                  <span key={c.node}>{i > 0 && ", "}<Link to={ws.link(c.story ? { ...ws.item({ kind: "story", sid: c.story, view: "steps" }), open: { node: c.node } }
                                                                        : ws.opened({ node: c.node }))}
                    className="ws-name" title={`Open ${c.label}'s code`} aria-label={`Open ${c.label}'s code`}>{c.label}</Link>
                    {c.story && <span className="ws-handle">{c.story}</span>}</span>
                ))}</div>
              )}
            </li>
          ))}</ul>
        </section>
      ))}
    </div>
  );
}
```

`frontend/src/workspace/StoryPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api";
import type { StoryDetail } from "../board/types";
import Explain from "../components/Explain";
import { countLine, stepStory } from "../stories/stories";
import { useWs } from "./context";
import { short } from "./crumbs";
import { pickFlow } from "./flows";
import FlowStrip from "./FlowStrip";
import GraphView from "./graph/GraphView";
import NameText, { Ticks } from "./NameText";
import { MechanicalStory, TestsStory } from "./StoryBodies";
import StorySteps from "./StorySteps";

/** A story (spec 2026-10-04-review-workspace §3.2): header with the Steps | Graph switch beside the title and ‹ S1 of 4 ›
 * in a fixed-width group; its steps or its graph, with the flow strip. */
export default function StoryPage({ sid, view }: { sid: string; view: "steps" | "graph" }) {
  const ws = useWs(), d = ws.data, ss = d.stories!;
  const [detail, setDetail] = useState<StoryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setDetail(null);
    d.story(sid).then((x) => { if (live) { setDetail(x); setError(null); } })
      .catch((e) => { if (live) setError(e instanceof ApiError && e.status === 404 ? e.message : String(e.message ?? e)); });
    return () => { live = false; };
  }, [d, sid]);
  const st = detail?.story ?? ss.stories.find((s) => s.id === sid)!;
  const at = ss.stories.findIndex((s) => s.id === sid);
  const hasGraph = !!detail?.graph && (st.kind === "behaviour" || st.kind === "other");
  const shown = hasGraph ? view : "steps";
  const flows = detail ? detail.board.flows.filter((f) => st.flows.includes(f.id)) : [];
  const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
  const index = pickFlow(flows, ws.addr.flow, open);
  const onFlow = (i: number) => ws.go({ ...ws.addr, flow: i + 1 }, true);
  const step = (by: number) => {
    const to = stepStory(ss, sid, by), other = ss.stories.find((s) => s.id === to);
    const label = `${by < 0 ? "Previous" : "Next"} story: ${to}${other ? ` ${short(other.title)}` : ""}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link(ws.item({ kind: "story", sid: to, view: "steps" }))} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };

  const header = (
    <header className="ws-story-head">
      <div className="ws-story-title">
        <h2>{st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
          {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
        {hasGraph && (
          <span className="ws-switch" role="tablist" aria-label="View">
            {(["steps", "graph"] as const).map((v) => (
              <Link key={v} role="tab" aria-selected={shown === v} className={shown === v ? "on" : ""} replace
                    to={ws.link({ ...ws.addr, place: { kind: "story", sid, view: v } })}>{v === "steps" ? "Steps" : "Graph"}</Link>
            ))}
          </span>
        )}
        <span className="ws-pos">{step(-1)}<span>{st.id} of {ss.stories.length}</span>{step(1)}</span>
      </div>
      <p><NameText text={st.summary} /> {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} />}</p>
      <p className="ws-story-meta"><span className="muted">{countLine(st)}</span>
        {st.cls.map((c) => (
          <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
        ))}</p>
    </header>
  );
  if (error) return <div className="ws-page"><div className="ws-text">{header}<div className="banner warn">{error}</div></div></div>;
  if (!detail) return <div className="ws-page"><div className="ws-text">{header}<p className="muted">Loading {st.id}…</p></div></div>;
  if (shown === "graph" && detail.graph)
    return (
      <div className="ws-page graph">
        <div className="ws-story-bar">{header}</div>
        <GraphView key={sid} board={detail.graph} prefKey={`${d.id}.${sid}`} flowIndex={index} onFlow={onFlow} quiet
                   onMore={() => ws.go({ ...ws.addr, place: { kind: "story", sid, view: "steps" } }, true)} />
      </div>
    );
  return (
    <div className="ws-page"><div className="ws-text">
      {header}
      {st.kind === "mechanical" ? <MechanicalStory detail={detail} /> : st.kind === "tests" ? <TestsStory detail={detail} /> : <>
        {flows.length > 0 && <FlowStrip board={detail.board} flows={flows} index={index} onFlow={onFlow} steps={false}
                                        hideWhat={!!flows[index] && st.summary.startsWith(flows[index].what)} />}
        <StorySteps detail={detail} flow={flows[index]} />
      </>}
      {at < 0 && <p className="muted">This story isn't in the list.</p>}
    </div></div>
  );
}
```

`frontend/src/workspace/StorySteps.tsx`:

```tsx
import { Link } from "react-router-dom";
import { flowSteps } from "../board/phone/flowSteps";
import type { BoardFlow, StoryDetail } from "../board/types";
import { SeverityBadge } from "../components/Badges";
import { useWs } from "./context";
import { short } from "./crumbs";
import NameText from "./NameText";

/** A story's Steps view (spec 2026-10-04-review-workspace §3.2; change stories §3.1): the flow's numbered steps, its
 * other changed functions and its findings. A step opens its code in the detail panel and is marked while open. */
export default function StorySteps({ detail, flow }: { detail: StoryDetail; flow: BoardFlow | undefined }) {
  const ws = useWs(), d = ws.data, { story, board } = detail;
  const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
  const nodes = new Map(board.nodes.map((n) => [n.id, n]));
  const steps = flow ? flowSteps(board, flow) : [];
  const others = detail.functions.filter((f) => !f.on_flow || !flow);
  const mine = d.findings.filter((f) => story.findings.includes(f.id));
  const code = (id: string) => ws.link(ws.opened(open === id ? null : { node: id }));
  return (
    <div className="ws-steps">
      {flow && (
        <ol className="ws-steplist" aria-label="Flow steps">
          {steps.map((s) => (
            <li key={s.id} className={`${s.kind}${open === s.id ? " open" : ""}`}>
              <Link to={code(s.id)} aria-current={open === s.id ? "true" : undefined}
                    title={open === s.id ? `Close ${s.label}'s code` : `Open ${s.label}'s code`}
                    aria-label={open === s.id ? `Close ${s.label}'s code` : `Open ${s.label}'s code`}>
                <span className="ws-marker" aria-hidden>{s.marker}</span>
                <span className="ws-step-text"><b className="mono">{s.label}</b><span className="muted"><NameText text={s.node.note || s.reason} /></span></span>
              </Link>
            </li>
          ))}
        </ol>
      )}
      {others.length > 0 && (
        <section aria-labelledby="ws-also">
          <h3 id="ws-also">{flow ? "Also changed in this story" : "Changed in this story"}</h3>
          <ul className="ws-steplist plain">{others.map((f) => (
            <li key={f.node} className={open === f.node ? "open" : ""}>
              <Link to={code(f.node)} aria-current={open === f.node ? "true" : undefined}
                    title={`Open ${f.label}'s code`} aria-label={`Open ${f.label}'s code`}>
                <span className="ws-step-text"><b className="mono">{f.label}</b><span className="muted"><NameText text={f.note} /></span></span>
              </Link>
              {f.also.map((sid) => {
                const st = d.stories?.stories.find((s) => s.id === sid);
                return <Link key={sid} className="ws-also" to={ws.link(ws.item({ kind: "story", sid, view: "steps" }))}
                             title={`Go to story ${sid}${st ? `: ${short(st.title)}` : ""}`}
                             aria-label={`Go to story ${sid}${st ? `: ${short(st.title)}` : ""}`}>also in <span className="ws-handle">{sid}</span></Link>;
              })}
              {!nodes.get(f.node)?.path && <span className="muted small"> no code in this review</span>}
            </li>
          ))}</ul>
        </section>
      )}
      {mine.length > 0 && (
        <section aria-labelledby="ws-sf">
          <h3 id="ws-sf">Findings</h3>
          <ul className="ws-findings">{mine.map((f) => (
            <li key={f.id}><SeverityBadge severity={f.severity} />{" "}
              <Link to={ws.link(ws.item({ kind: "finding", fid: f.id }))} title={`Go to finding ${f.id}: ${short(f.title)}`}
                    aria-label={`Go to finding ${f.id}: ${short(f.title)}`}>{f.title}</Link><span className="ws-handle">{f.id}</span></li>
          ))}</ul>
        </section>
      )}
    </div>
  );
}
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index 7f0dd62..cae1aa0 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -16,6 +16,7 @@ import { type Crumb, crumbs } from "./crumbs";
 import { useScreen } from "./media";
 import { loadMemory, recall, remember, saveMemory } from "./memory";
 import Rail from "./Rail";
+import StoryPage from "./StoryPage";
 import { useReview } from "./useReview";
 import WholePage, { ReviewGraph } from "./WholePage";
 import "./workspace.css";
@@ -120,6 +121,7 @@ function Centre() {
   if (p.kind === "whole" && p.view === "graph")
     return d.board ? <div className="ws-page graph"><ReviewGraph board={d.board} /></div> : <Missing what={p} />;
   if (p.kind === "whole") return <WholePage />;
+  if (p.kind === "story") return <StoryPage key={p.sid} sid={p.sid} view={p.view} />;
   return <div className="ws-page"><p className="muted">This page is built in a later step.</p></div>;
 }
 
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 09ea592..3729d02 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -163,3 +163,47 @@ a.ws-nb:hover { border-color: var(--accent); }
 .bd-node.lit { outline: 2px solid var(--accent); outline-offset: 2px; }
 .ws-mapgraph { height: 460px; display: flex; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
 .ws-open-full { float: right; text-transform: none; letter-spacing: 0; font-weight: 500; font-size: 13px; }
+
+/* story page */
+.ws-story-head { margin-bottom: 14px; }
+.ws-story-title { display: flex; align-items: center; gap: 10px 16px; flex-wrap: wrap; }
+.ws-story-title h2 { flex: 1 1 320px; font-size: 19px; line-height: 1.35; margin: 0; }
+.ws-story-title h2 .bd-pill { margin-right: 8px; vertical-align: 2px; }
+.ws-switch { display: inline-flex; border: 1px solid var(--line); border-radius: 9px; overflow: hidden; flex: none; }
+.ws-switch a { padding: 7px 18px; font-weight: 600; text-decoration: none; color: var(--muted); }
+.ws-switch a.on { background: var(--accent); color: var(--surface); }
+.ws-pos { display: inline-flex; align-items: center; gap: 6px; flex: none; font-size: 12.5px; color: var(--muted); }
+.ws-pos > span { width: 5.5em; text-align: center; font-variant-numeric: tabular-nums; }
+.ws-step-btn { width: 30px; text-align: center; text-decoration: none; display: inline-block; }
+.ws-story-head p { margin: 8px 0 0; font-size: 14.5px; }
+.ws-story-meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
+a.ws-chip { text-decoration: none; }
+.ws-story-bar { flex: none; padding: 12px 20px 2px; background: var(--surface); border-bottom: 1px solid var(--line); }
+.ws-story-bar .ws-story-head { margin-bottom: 8px; }
+.ws-steps h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 20px 0 6px; }
+.ws-steplist { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
+.ws-steplist > li { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
+.ws-steplist > li > a:first-child { flex: 1; min-width: 0; display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px;
+  border: 1px solid var(--line); border-radius: 9px; text-decoration: none; color: var(--ink); background: var(--surface); }
+.ws-steplist > li > a:first-child:hover { border-color: var(--accent); }
+.ws-steplist > li.open > a:first-child { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent); }
+.ws-marker { flex: none; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; font: 700 11px var(--sans);
+  background: var(--gap-bg); color: var(--muted); }
+.ws-steplist .chg .ws-marker { background: var(--accent); color: var(--surface); }
+.ws-steplist .landing .ws-marker { background: var(--bad); color: var(--surface); }
+.ws-steplist .field .ws-marker { background: #9b6a2f; color: var(--surface); }
+.ws-step-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
+.ws-step-text .muted { font-size: 13px; }
+.ws-also { font-size: 12px; text-decoration: none; }
+.ws-findings { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
+.ws-tools { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-bottom: 12px; font-size: 13px; }
+.ws-tools input { width: auto; }
+.ws-sites { list-style: none; margin: 6px 0 12px; padding: 0 0 0 10px; display: flex; flex-direction: column; gap: 8px; }
+.ws-sites li { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
+.ws-sites code { font: 12px var(--mono); padding: 1px 6px; border-radius: 4px; white-space: pre-wrap; overflow-wrap: anywhere; }
+.ws-sites code.del { background: var(--del-bg); } .ws-sites code.add { background: var(--add-bg); }
+.ws-calls { width: 100%; font-size: 12.5px; color: var(--muted); padding-left: 10px; }
+@media (max-width: 640px) {
+  .ws-story-title h2 { flex-basis: 100%; font-size: 17px; }
+  .ws-story-bar { padding: 10px 14px 2px; }
+}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-story.spec.ts e2e/workspace-graph.spec.ts`

Expected: `✓ built in …` and `6 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  29 passed (29)` and `Tests  134 passed (134)` and `✓ built in …` and `72 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/helpers.ts frontend/e2e/workspace-graph.spec.ts frontend/e2e/workspace-story.spec.ts frontend/src/workspace/StoryBodies.tsx frontend/src/workspace/StoryPage.tsx frontend/src/workspace/StorySteps.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/workspace.css
git commit -m "feat(ui): the story page — Steps | Graph beside the title, fixed ‹ ›, steps open the detail panel, CL chips"
```

---

### Task 13: The finding page

Spec §3.3, §7. The header: severity, title, kind, state buttons for the owner, `‹ F2 of 10 ›`. "Where it
lives": its story, "Show it on the graph" (the story's graph, else the part's or the review's, with the node open), the
CLs of its files and its functions. "AI analysis" first ("AI analysis unavailable." with no AI), then evidence (each
line with a file and line opens the diff there, its workspace path mapped to a depot path by `depotFor`), Verify,
possible side effects and comments.

**Files:**
- Create: `frontend/src/workspace/FindingPage.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Create: `frontend/src/workspace/evidence.ts`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace-pages.spec.ts` (new)
- Test: `frontend/src/workspace/evidence.test.ts` (new)

**Interfaces:**
- Consumes: `useWs()`, `Explain`, `Comments`, `NameText`, `api.setFindingState`.
- Produces: `depotFor(file, depots): string | null`; `FindingPage({fid})`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-pages.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";

/** Finding, CL and cluster pages (spec 2026-10-04-review-workspace §3.3–§3.5). */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a finding: to its story and back, on the graph, evidence opens the diff at its line", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}/f/F5`);
    await expect(page.locator(".ws-finding h2")).toContainText("uart_send: new return value(s) -2");
    await expect(page.getByRole("region", { name: "AI analysis" })).toContainText("AI analysis unavailable.");
    await page.getByRole("link", { name: /^Go to story S1/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F5$`));

    await page.getByRole("link", { name: "Open service/logger.c at line 12" }).first().click();
    await expect(page).toHaveURL(/open=file%3A%2F%2Ffixture%2Fservice%2Flogger\.c%3A12$/);
    await expect(page.getByRole("complementary", { name: "Code: logger.c" }).locator('[data-n="12"]').first()).toBeVisible();
    await page.goBack();

    await page.getByRole("link", { name: "Show it on the graph" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?view=graph&open=N\\d+$`));
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await page.goBack();

    await page.getByRole("link", { name: /^Next finding: F6/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F6$`));
    await page.getByRole("button", { name: "mark acknowledged" }).click();
    await expect(page.locator(".ws-finding .ws-badge")).toHaveText("acknowledged");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });
});
```

`frontend/src/workspace/evidence.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { depotFor } from "./evidence";

const depots = ["//fixture/driver/uart.c", "//fixture/driver/uart.h", "//fixture/service/logger.c", "//other/service/logger.c.bak"];

describe("depotFor", () => {
  it("names the depot file a workspace path is, by the longest shared tail", () => {
    expect(depotFor("/home/u/ws/service/logger.c", depots)).toBe("//fixture/service/logger.c");
    expect(depotFor("/home/u/ws/driver/uart.h", depots)).toBe("//fixture/driver/uart.h");
  });

  it("passes depot paths through and gives up without a matching file name", () => {
    expect(depotFor("//fixture/driver/uart.c", depots)).toBe("//fixture/driver/uart.c");
    expect(depotFor("/home/u/ws/hal/regs.c", depots)).toBeNull();
  });

  it("refuses a tie it cannot break", () => {
    expect(depotFor("/ws/x/a.c", ["//p/y/a.c", "//q/z/a.c"])).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/workspace/evidence.test.ts && npm run build && npx playwright test e2e/workspace-pages.spec.ts`

Expected: FAIL — `Test Files  1 failed (1)` and `Tests  no tests` and `Cannot find module './evidence' imported from src/workspace/evidence.test`

- [ ] **Step 3: Implement**

`frontend/src/workspace/FindingPage.tsx`:

```tsx
import { Link } from "react-router-dom";
import { api } from "../api";
import { useMe } from "../App";
import { SeverityBadge } from "../components/Badges";
import Comments from "../components/Comments";
import Explain from "../components/Explain";
import { useAi } from "../lib/ai";
import type { Address } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { depotFor } from "./evidence";
import NameText from "./NameText";

const STATE = { open: "open", ack: "acknowledged", dismissed: "dismissed" } as const;

/** A finding (spec 2026-10-04-review-workspace §3.3): where it lives, the AI analysis first, then the evidence, each
 * line opening the diff at that line. */
export default function FindingPage({ fid }: { fid: string }) {
  const ws = useWs(), d = ws.data, me = useMe(), ai = useAi();
  const i = d.findings.findIndex((x) => x.id === fid), f = d.findings[i];
  const n = d.findings.length;
  const sid = d.stories?.finding_story[fid] ?? null, st = sid ? d.stories!.stories.find((s) => s.id === sid) : null;
  const first = f.nodes.find((x) => d.names[x]) ?? f.nodes[0] ?? null;
  const cluster = d.overview?.clusters.find((c) => c.finding_ids.includes(fid)) ?? null;
  const graph: Address | null = !first ? null
    : st && (st.kind === "behaviour" || st.kind === "other") ? { ...ws.item({ kind: "story", sid: st.id, view: "graph" }), place: { kind: "story", sid: st.id, view: "graph" }, open: { node: first }, tab: "diff" }
    : cluster ? { ...ws.item({ kind: "cluster", cid: cluster.id }), open: { node: first }, tab: "diff" }
    : d.board ? { place: { kind: "whole", view: "graph" }, flow: null, open: { node: first }, tab: "diff" } : null;
  const tree = d.about?.tree.flatMap((t) => t.files) ?? [];
  const cls = [...new Set(tree.filter((t) => f.files?.includes(t.path)).flatMap((t) => t.cls))].sort((a, b) => a - b);
  const depots = [...(f.files ?? []), ...d.files.map((x) => x.depot), ...Object.values(d.names).flatMap((x) => (x.path ? [x.path] : []))];
  const step = (by: number) => {
    const to = d.findings[((i + by) % n + n) % n];
    const label = `${by < 0 ? "Previous" : "Next"} finding: ${to.id} ${short(to.title)}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link(ws.item({ kind: "finding", fid: to.id }))} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };
  const name = (nid: string) => {
    const label = d.names[nid]?.label ?? "a function";
    return <Link key={nid} className="ws-name" to={ws.link(ws.opened({ node: nid }))} title={`Open ${label}'s code`}
                 aria-label={`Open ${label}'s code`}>{label}</Link>;
  };
  return (
    <div className="ws-page"><div className="ws-text ws-finding">
      <header className="ws-story-head">
        <div className="ws-story-title">
          <h2><SeverityBadge severity={f.severity} /> {f.title}</h2>
          <span className="ws-pos">{step(-1)}<span>{f.id} of {n}</span>{step(1)}</span>
        </div>
        <p className="ws-story-meta">
          <span className="muted">{f.kind.replace(/_/g, " ")}</span>
          <span className={`ws-badge state-${f.state}`}>{STATE[f.state]}</span>
          {me?.is_owner && (["open", "ack", "dismissed"] as const).filter((s) => s !== f.state).map((s) => (
            <button key={s} className="link small" onClick={() => api.setFindingState(d.id, f.id, s).then(d.loadFindings)}>
              mark {STATE[s]}</button>
          ))}
        </p>
      </header>
      <section aria-labelledby="ws-where" className="ws-where">
        <h3 id="ws-where">Where it lives</h3>
        <ul>
          {st && <li>Story: <Link to={ws.link(ws.item({ kind: "story", sid: st.id, view: "steps" }))} title={`Go to story ${st.id}: ${short(st.title)}`}
                                  aria-label={`Go to story ${st.id}: ${short(st.title)}`}>{short(st.title, 70)}</Link><span className="ws-handle">{st.id}</span></li>}
          {graph && <li><Link to={ws.link(graph)} title="Show it on the graph" aria-label="Show it on the graph">On the graph</Link>
            {cluster && !st && <span className="muted"> · {cluster.name}</span>}</li>}
          {cls.length > 0 && <li>Changelists: {cls.map((c) => (
            <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
          ))}</li>}
          {f.nodes.length > 0 && <li>Functions: {f.nodes.map((x, k) => <span key={x}>{k > 0 && ", "}{name(x)}</span>)}</li>}
        </ul>
      </section>
      <section aria-labelledby="ws-ai">
        <h3 id="ws-ai">AI analysis</h3>
        {f.explanation ? <p><span className="ai-label">AI</span><NameText text={f.explanation} /> <Explain kind="finding" target={f.id} has /></p>
          : ai?.view && !ai.view.llm ? <p className="muted">AI analysis unavailable.</p>
          : <p className="muted">Not written yet. <Explain kind="finding" target={f.id} has={false} /></p>}
      </section>
      <section aria-labelledby="ws-ev">
        <h3 id="ws-ev">Evidence</h3>
        <p><NameText text={f.summary} /></p>
        <ul className="ws-evidence">{f.evidence.map((e, k) => {
          const depot = e.file ? depotFor(e.file, depots) : null, file = depot ?? e.file;
          const short_ = file ? file.split("/").slice(-2).join("/") : null;
          return (
            <li key={k} className={`sev-${e.severity}`}><NameText text={e.text} />
              {depot ? <> <Link className="mono small" to={ws.link(ws.opened({ file: depot, line: e.line }))}
                                title={`Open ${short_}${e.line ? ` at line ${e.line}` : ""}`}
                                aria-label={`Open ${short_}${e.line ? ` at line ${e.line}` : ""}`}>{short_}{e.line ? `:${e.line}` : ""}</Link></>
                : short_ && <span className="mono small muted"> {short_}{e.line ? `:${e.line}` : ""}</span>}
            </li>
          );
        })}</ul>
      </section>
      {f.verify_steps.length > 0 && (
        <section aria-labelledby="ws-verify"><h3 id="ws-verify">Verify</h3>
          <ol>{f.verify_steps.map((s, k) => <li key={k}><NameText text={s} /></li>)}</ol></section>
      )}
      {f.hypotheses.length > 0 && (
        <section aria-labelledby="ws-hyp"><h3 id="ws-hyp">Possible side effects</h3>
          <ul>{f.hypotheses.map((h, k) => (
            <li key={k}><span className="ai-label">AI</span><NameText text={h.text} />
              {h.cites.filter((c) => c.startsWith("N")).length > 0 && <span className="muted"> — {h.cites.filter((c) => c.startsWith("N")).map((c, j) => <span key={c}>{j > 0 && ", "}{name(c)}</span>)}</span>}</li>
          ))}</ul></section>
      )}
      <section aria-labelledby="ws-fc"><h3 id="ws-fc">Comments</h3>
        <Comments reviewId={d.id} comments={d.comments} kind="finding" anchor={{ kind: f.kind, title: f.title }} onChange={d.loadComments} compact />
      </section>
    </div></div>
  );
}
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index cae1aa0..e8e5567 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -15,6 +15,7 @@ import Detail from "./Detail";
 import { type Crumb, crumbs } from "./crumbs";
 import { useScreen } from "./media";
 import { loadMemory, recall, remember, saveMemory } from "./memory";
+import FindingPage from "./FindingPage";
 import Rail from "./Rail";
 import StoryPage from "./StoryPage";
 import { useReview } from "./useReview";
@@ -122,6 +123,7 @@ function Centre() {
     return d.board ? <div className="ws-page graph"><ReviewGraph board={d.board} /></div> : <Missing what={p} />;
   if (p.kind === "whole") return <WholePage />;
   if (p.kind === "story") return <StoryPage key={p.sid} sid={p.sid} view={p.view} />;
+  if (p.kind === "finding") return <FindingPage key={p.fid} fid={p.fid} />;
   return <div className="ws-page"><p className="muted">This page is built in a later step.</p></div>;
 }
 
```

`frontend/src/workspace/evidence.ts`:

```ts
/** Evidence lines name workspace files; the detail panel opens depot paths. The depot path of a workspace file is the
 * candidate sharing the longest tail of path segments with it (at least the file name), if exactly one does. */
export function depotFor(file: string, depots: Iterable<string>): string | null {
  if (file.startsWith("//")) return file;
  const mine = file.split("/").reverse();
  let best: string | null = null, bestN = 0, tie = false;
  for (const d of new Set(depots)) {
    const theirs = d.split("/").reverse();
    let n = 0;
    while (n < mine.length && n < theirs.length && mine[n] === theirs[n] && mine[n]) n++;
    if (n > bestN) { best = d; bestN = n; tie = false; } else if (n === bestN && n > 0) tie = true;
  }
  return bestN > 0 && !tie ? best : null;
}
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 3729d02..5627e60 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -207,3 +207,12 @@ a.ws-chip { text-decoration: none; }
   .ws-story-title h2 { flex-basis: 100%; font-size: 17px; }
   .ws-story-bar { padding: 10px 14px 2px; }
 }
+
+/* finding page */
+.ws-finding section { margin: 0 0 20px; }
+.ws-finding h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 0 0 6px; }
+.ws-where ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
+.ws-where li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
+.ws-evidence { padding-left: 18px; } .ws-evidence li { margin: 3px 0; }
+.ws-evidence .sev-high::marker, .ws-evidence .sev-medium::marker { color: var(--bad); }
+.ws-badge.state-ack { color: var(--warn); } .ws-badge.state-dismissed { color: var(--muted); }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/workspace/evidence.test.ts && npm run build && npx playwright test e2e/workspace-pages.spec.ts`

Expected: `Test Files  1 passed (1)` and `Tests  3 passed (3)` and `✓ built in …` and `1 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  30 passed (30)` and `Tests  137 passed (137)` and `✓ built in …` and `73 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-pages.spec.ts frontend/src/workspace/FindingPage.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/evidence.test.ts frontend/src/workspace/evidence.ts frontend/src/workspace/workspace.css
git commit -m "feat(ui): the finding page — where it lives, AI analysis first, evidence opening the diff at its line"
```

---

### Task 14: The changelist page

Spec §3.4. The header: CL number, author, status and the description (first line as title). The Swarm card:
review link, state and votes; for the owner Refresh, Create review and Post summary link (with the "post again?"
confirmation). The CL's files each open their diff in the detail panel filtered to the CL; then the stories drawn from
it and the findings in its files.

**Files:**
- Create: `frontend/src/workspace/ClPage.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace-pages.spec.ts`

**Interfaces:**
- Consumes: `useWs()`, the Swarm endpoints in `api.ts`, `FileDiff`'s `cl` (Task 8).
- Produces: `ClPage({cl})`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-pages.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace-pages.spec.ts b/frontend/e2e/workspace-pages.spec.ts
index 88a7688..5942cb7 100644
--- a/frontend/e2e/workspace-pages.spec.ts
+++ b/frontend/e2e/workspace-pages.spec.ts
@@ -33,4 +33,18 @@ test.describe("desktop", () => {
     await expectNoNodeIds(page);
     await expectNamed(page);
   });
+
+  test("a changelist: its Swarm card, its files filtered to it, the stories and findings drawn from it", async ({ page }) => {
+    const base = await startWorkspace(page);
+    await page.locator(".ws-rail").getByRole("link", { name: "Open CL 102" }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}/cl/102$`));
+    await expect(page.locator(".ws-finding h2")).toHaveText("CL 102 · uart: add flags field; hal_write takes unsigned reg");
+    await expect(page.getByRole("region", { name: "Swarm" })).toContainText("No Swarm review.");
+    await expect(page.getByRole("region", { name: "Swarm" }).getByRole("button", { name: "Refresh" })).toBeVisible();
+    await expect(page.getByRole("region", { name: "Stories drawn from this CL" })).toContainText("hal_write");
+    await page.getByRole("link", { name: "Open regs.c's diff in CL 102" }).click();
+    await expect(page.getByRole("complementary", { name: "Code: regs.c" }).getByLabel("Changelist")).toHaveValue("102");
+    await expectNoNodeIds(page);
+    await expectNamed(page);
+  });
 });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-pages.spec.ts`

Expected: FAIL — `✓ built in …` and `1 failed` and `1 passed` and (1 failing, first: desktop › a changelist: its Swarm card, its files filtered to it, the stories and findings drawn from it)

- [ ] **Step 3: Implement**

`frontend/src/workspace/ClPage.tsx`:

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useMe } from "../App";
import { SeverityBadge } from "../components/Badges";
import { useWs } from "./context";
import { short } from "./crumbs";
import { Ticks } from "./NameText";

/** A changelist (spec 2026-10-04-review-workspace §3.4): its description, its Swarm review, its files, and the stories
 * and findings drawn from it. */
export default function ClPage({ cl }: { cl: number }) {
  const ws = useWs(), d = ws.data, me = useMe();
  const [msg, setMsg] = useState<string | null>(null);
  const c = d.detail!.cls.find((x) => x.cl === cl)!;
  const [title, ...rest] = (c.description ?? "").trim().split("\n");
  const files = d.about?.tree.flatMap((t) => t.files).filter((f) => f.cls.includes(cl)) ?? [];
  const paths = new Set(files.map((f) => f.path));
  const stories = d.stories?.stories.filter((s) => s.cls.includes(cl)) ?? [];
  const findings = d.findings.filter((f) => f.files?.some((p) => paths.has(p)));
  const run = (p: Promise<unknown>, ok: string) => p.then(() => { setMsg(ok); d.loadDetail(); }).catch((e) => setMsg(String(e.message ?? e)));
  return (
    <div className="ws-page"><div className="ws-text ws-finding">
      <header className="ws-story-head">
        <div className="ws-story-title"><h2>CL {c.cl} · {title || "(no description)"}</h2></div>
        <p className="ws-story-meta"><span className="muted">{c.user}</span><span className="ws-badge">{c.status}</span></p>
        {rest.join("\n").trim() && <pre className="ws-desc">{rest.join("\n").trim()}</pre>}
      </header>
      <section aria-labelledby="ws-swarm" className="ws-swarm">
        <h3 id="ws-swarm">Swarm</h3>
        {msg && <div className="banner">{msg}</div>}
        {c.swarm ? (
          <p><a href={c.swarm.url} target="_blank" rel="noreferrer" title={`Open Swarm review ${c.swarm.id}`}>Review #{c.swarm.id}</a>{" "}
            <span className="ws-badge">{c.swarm.state_label ?? c.swarm.state}</span>
            {Object.keys(c.swarm.votes).length > 0 && <span className="muted small"> · votes {Object.entries(c.swarm.votes)
              .map(([u, v]) => `${u} ${v > 0 ? "+" : ""}${v}`).join(", ")}</span>}</p>
        ) : <p className="muted">No Swarm review.</p>}
        {me?.is_owner && (
          <p className="ws-tools">
            <button onClick={() => run(api.swarmRefresh(d.id, cl), "Swarm state refreshed")}>Refresh</button>
            {!c.swarm && c.status === "pending" && <button onClick={() => run(api.swarmCreate(d.id, cl), "Swarm review created")}>Create review</button>}
            {c.swarm && <button onClick={() => run(api.swarmPost(d.id, cl).catch((e) => {
              if (e.status === 409 && window.confirm("A summary was already posted. Post again?")) return api.swarmPost(d.id, cl, true);
              throw e;
            }), "Summary link posted to Swarm")}>Post summary link</button>}
          </p>
        )}
      </section>
      <section aria-labelledby="ws-clf">
        <h3 id="ws-clf">Files in this CL</h3>
        {files.length ? <ul className="ws-fx">{files.map((f) => (
          <li key={f.path}><Link className="mono" to={ws.link(ws.opened({ file: f.path, line: null }))} title={`Open ${f.name}'s diff in CL ${cl}`}
                                 aria-label={`Open ${f.name}'s diff in CL ${cl}`}>{f.path}</Link>
            <span className="muted small"> {f.action} <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span></span></li>
        ))}</ul> : <p className="muted">No files of this CL in the review's change summary.</p>}
      </section>
      {stories.length > 0 && (
        <section aria-labelledby="ws-cls"><h3 id="ws-cls">Stories drawn from this CL</h3>
          <ul className="ws-findings">{stories.map((s) => (
            <li key={s.id}>{s.risk && <span className={`bd-pill ${s.risk}`}>{s.risk}</span>}{" "}
              <Link to={ws.link(ws.item({ kind: "story", sid: s.id, view: "steps" }))} title={`Go to story ${s.id}: ${short(s.title)}`}
                    aria-label={`Go to story ${s.id}: ${short(s.title)}`}><Ticks text={s.title} /></Link><span className="ws-handle">{s.id}</span></li>
          ))}</ul></section>
      )}
      {findings.length > 0 && (
        <section aria-labelledby="ws-clfi"><h3 id="ws-clfi">Findings in its files</h3>
          <ul className="ws-findings">{findings.map((f) => (
            <li key={f.id}><SeverityBadge severity={f.severity} />{" "}
              <Link to={ws.link(ws.item({ kind: "finding", fid: f.id }))} title={`Go to finding ${f.id}: ${short(f.title)}`}
                    aria-label={`Go to finding ${f.id}: ${short(f.title)}`}>{f.title}</Link><span className="ws-handle">{f.id}</span></li>
          ))}</ul></section>
      )}
    </div></div>
  );
}
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index e8e5567..2689a2a 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -15,6 +15,7 @@ import Detail from "./Detail";
 import { type Crumb, crumbs } from "./crumbs";
 import { useScreen } from "./media";
 import { loadMemory, recall, remember, saveMemory } from "./memory";
+import ClPage from "./ClPage";
 import FindingPage from "./FindingPage";
 import Rail from "./Rail";
 import StoryPage from "./StoryPage";
@@ -124,6 +125,7 @@ function Centre() {
   if (p.kind === "whole") return <WholePage />;
   if (p.kind === "story") return <StoryPage key={p.sid} sid={p.sid} view={p.view} />;
   if (p.kind === "finding") return <FindingPage key={p.fid} fid={p.fid} />;
+  if (p.kind === "cl") return <ClPage key={p.cl} cl={p.cl} />;
   return <div className="ws-page"><p className="muted">This page is built in a later step.</p></div>;
 }
 
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 5627e60..c8611d8 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -216,3 +216,4 @@ a.ws-chip { text-decoration: none; }
 .ws-evidence { padding-left: 18px; } .ws-evidence li { margin: 3px 0; }
 .ws-evidence .sev-high::marker, .ws-evidence .sev-medium::marker { color: var(--bad); }
 .ws-badge.state-ack { color: var(--warn); } .ws-badge.state-dismissed { color: var(--muted); }
+.ws-desc { white-space: pre-wrap; font: 13px/1.5 var(--sans); color: var(--muted); margin: 8px 0 0; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-pages.spec.ts`

Expected: `✓ built in …` and `2 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  30 passed (30)` and `Tests  137 passed (137)` and `✓ built in …` and `74 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-pages.spec.ts frontend/src/workspace/ClPage.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/workspace.css
git commit -m "feat(ui): the changelist page — Swarm card, its files filtered to it, the stories and findings drawn from it"
```

---

### Task 15: The cluster page

Spec §3.5. A part of a split review: name, layer, risk, counts, `‹ ›` between parts, the stories it holds,
then its graph with the flow strip. Visitor nodes link to their own part, with the node open.

**Files:**
- Create: `frontend/src/workspace/ClusterPage.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Test: `frontend/e2e/workspace.spec.ts`

**Interfaces:**
- Consumes: `api.board(id, cid)`, `GraphView` (`onHome`, `homeName`) (Task 11).
- Produces: `ClusterPage({cid})`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index 0b0f711..b11ba8e 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -112,5 +112,18 @@ test.describe("a large change", () => {
     await map.getByRole("link", { name: "Open drv/uart" }).click();
     await expect(page).toHaveURL(new RegExp(`${base}/c/C\\d+$`));
     await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Map › drv/uart");
+    await expect(page.locator(".bd-node").first()).toBeVisible();
+    await expect(page.getByRole("region", { name: "Flow" })).toBeVisible();
+    let visitor = page.locator(".bd-home").first();
+    for (let i = 0; i < 7 && !(await visitor.count()); i++) {          // step through the parts to one with a visitor
+      await page.getByRole("link", { name: /^Next part:/ }).click();
+      await expect(page.locator(".bd-node").first()).toBeVisible();
+      visitor = page.locator(".bd-home").first();
+    }
+    const to = (await visitor.getAttribute("aria-label"))!.replace(/^Go to /, "");   // a visitor links to its own part
+    await visitor.dispatchEvent("pointerdown", { bubbles: true, pointerId: 1, button: 0 });
+    await visitor.dispatchEvent("pointerup", { bubbles: true, pointerId: 1, button: 0 });
+    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText(`Map › ${to}`);
+    await expect(page).toHaveURL(/open=N\d+$/);
   });
 });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace.spec.ts`

Expected: FAIL — `✓ built in …` and `1 failed` and `5 passed` and (1 failing, first: a large change › the whole change maps its parts; a part opens its page)

- [ ] **Step 3: Implement**

`frontend/src/workspace/ClusterPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type Board } from "../api";
import { stepCluster } from "../board/overview";
import { useWs } from "./context";
import { short } from "./crumbs";
import { pickFlow } from "./flows";
import GraphView from "./graph/GraphView";
import { Ticks } from "./NameText";

/** One part of a split review (spec 2026-10-04-review-workspace §3.5): name, layer, risk, counts, ‹ ›, the stories it
 * holds, then its graph with the flow strip. Visitors link to their own part. */
export default function ClusterPage({ cid }: { cid: string }) {
  const ws = useWs(), d = ws.data, ov = d.overview!;
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.board(d.id, cid).then((b) => { if (live) { setBoard(b); setError(null); } })
      .catch((e) => { if (live) setError(e instanceof ApiError && e.status === 404 ? e.message : String(e.message ?? e)); });
    return () => { live = false; };
  }, [d.id, cid, d.reload]);
  const c = ov.clusters.find((x) => x.id === cid)!;
  const at = ov.clusters.findIndex((x) => x.id === cid);
  const layer = ov.layers.find((l) => l.level === c.level)?.name;
  const stories = d.stories?.stories.filter((s) => s.board === cid) ?? [];
  const name = (id: string) => ov.clusters.find((x) => x.id === id)?.name ?? id;
  const step = (by: 1 | -1) => {
    const to = stepCluster(ov, cid, by), label = `${by < 0 ? "Previous" : "Next"} part: ${name(to)}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link(ws.item({ kind: "cluster", cid: to }))} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };
  const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
  return (
    <div className="ws-page graph">
      <div className="ws-story-bar">
        <header className="ws-story-head">
          <div className="ws-story-title">
            <h2>{c.risk && <span className={`bd-pill ${c.risk}`}>{c.risk}</span>}{c.name}</h2>
            <span className="ws-pos">{step(-1)}<span>{at + 1} of {ov.clusters.length}</span>{step(1)}</span>
          </div>
          <p className="ws-story-meta"><span className="muted">{layer ? `${layer} · ` : ""}{c.files.length} files · {c.changed} changed ·{" "}
            {c.flows} flows · {c.findings} finding{c.findings === 1 ? "" : "s"}</span>
            {stories.map((s) => (
              <Link key={s.id} className="ws-chip" to={ws.link(ws.item({ kind: "story", sid: s.id, view: "steps" }))}
                    title={`Go to story ${s.id}: ${short(s.title)}`} aria-label={`Go to story ${s.id}: ${short(s.title)}`}>
                <Ticks text={short(s.title, 32)} /> {s.id}</Link>
            ))}</p>
        </header>
      </div>
      {error ? <div className="ws-page"><div className="banner warn">{error}</div></div>
        : !board ? <p className="muted ws-page">Loading {c.name}…</p>
        : <GraphView key={cid} board={board} prefKey={`${d.id}.${cid}`} flowIndex={pickFlow(board.flows, ws.addr.flow, open)}
                     onFlow={(i) => ws.go({ ...ws.addr, flow: i + 1 }, true)} homeName={name}
                     onHome={(home, node) => ws.go({ ...ws.item({ kind: "cluster", cid: home }), open: { node }, tab: "diff" })} />}
    </div>
  );
}
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index 2689a2a..af87e76 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -16,6 +16,7 @@ import { type Crumb, crumbs } from "./crumbs";
 import { useScreen } from "./media";
 import { loadMemory, recall, remember, saveMemory } from "./memory";
 import ClPage from "./ClPage";
+import ClusterPage from "./ClusterPage";
 import FindingPage from "./FindingPage";
 import Rail from "./Rail";
 import StoryPage from "./StoryPage";
@@ -126,7 +127,8 @@ function Centre() {
   if (p.kind === "story") return <StoryPage key={p.sid} sid={p.sid} view={p.view} />;
   if (p.kind === "finding") return <FindingPage key={p.fid} fid={p.fid} />;
   if (p.kind === "cl") return <ClPage key={p.cl} cl={p.cl} />;
-  return <div className="ws-page"><p className="muted">This page is built in a later step.</p></div>;
+  if (p.kind === "cluster") return <ClusterPage key={p.cid} cid={p.cid} />;
+  return <Missing what={p} />;
 }
 
 export function Missing({ what }: { what: Place }) {
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace.spec.ts`

Expected: `✓ built in …` and `6 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  30 passed (30)` and `Tests  137 passed (137)` and `✓ built in …` and `74 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace.spec.ts frontend/src/workspace/ClusterPage.tsx frontend/src/workspace/Workspace.tsx
git commit -m "feat(ui): the cluster page — a part's risk, counts, stories and graph; visitors link to their own part"
```

---

### Task 16: /r/ is the workspace: redirects, deletions, ported journeys

Spec §2.3, §5, §6. `/r/:id/*` renders the workspace; `/w/:id/*` redirects to `/r/` keeping the rest of the
address. `legacy()` maps the old addresses: `?node=` to the story holding it (`open=`), else on `/c/C` to that part,
else on a review shown as one board to its graph, else the server's `locate`; `/board` to the graph or `#map`;
`/overview`, `/findings`, `/cls`, `/files` to `#map`, `#findings`, `#changeset`, `#files`; `/s/S?tab=graph` to
`view=graph`; `file=` to `open=file:`; `x=` is dropped. The old UI goes (`pages/Review.tsx`, cards, boards, the phone
board, the story list, `Findings`, `CiteText`, `ClsPanel`, their CSS and specs) with the helpers only it used; `prefs`
loses its card, viewer, phone-tab and panel keys and gains the rail and panel widths. The old specs' journeys are
ported onto the workspace, and the e2e helpers collapse to one `startReview(page, cls?)`.

**Files:**
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/board/Board.tsx`
- Delete: `frontend/src/board/Canvas.tsx`
- Delete: `frontend/src/board/CardLayer.tsx`
- Delete: `frontend/src/board/ChangePanel.tsx`
- Delete: `frontend/src/board/ClusterBoard.tsx`
- Delete: `frontend/src/board/FileViewer.tsx`
- Delete: `frontend/src/board/FlowBar.tsx`
- Delete: `frontend/src/board/OverviewPage.tsx`
- Modify: `frontend/src/board/layout.ts`
- Modify: `frontend/src/board/overview.ts`
- Delete: `frontend/src/board/phone/FlowReader.tsx`
- Delete: `frontend/src/board/phone/PhoneBoard.tsx`
- Delete: `frontend/src/board/phone/PhoneMap.tsx`
- Delete: `frontend/src/board/phone/phone.css`
- Modify: `frontend/src/board/prefs.ts`
- Delete: `frontend/src/board/reducer.ts`
- Delete: `frontend/src/components/CiteText.tsx`
- Delete: `frontend/src/components/ClsPanel.tsx`
- Delete: `frontend/src/components/Findings.tsx`
- Delete: `frontend/src/pages/Review.tsx`
- Delete: `frontend/src/stories/StoryBodies.tsx`
- Delete: `frontend/src/stories/StoryList.tsx`
- Delete: `frontend/src/stories/StoryPage.tsx`
- Delete: `frontend/src/stories/StorySteps.tsx`
- Delete: `frontend/src/stories/stories.css`
- Modify: `frontend/src/stories/stories.ts`
- Modify: `frontend/src/workspace/Detail.tsx`
- Modify: `frontend/src/workspace/Rail.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Create: `frontend/src/workspace/legacy.ts`
- Test: `frontend/e2e/ai.spec.ts`
- Test: `frontend/e2e/banner.spec.ts`
- Delete: `frontend/e2e/board.spec.ts`
- Test: `frontend/e2e/helpers.ts`
- Test: `frontend/e2e/landing.spec.ts`
- Delete: `frontend/e2e/large.spec.ts`
- Test: `frontend/e2e/mention.spec.ts`
- Delete: `frontend/e2e/panel-diff.spec.ts`
- Delete: `frontend/e2e/phone.spec.ts`
- Delete: `frontend/e2e/smoke.spec.ts`
- Delete: `frontend/e2e/stories.spec.ts`
- Test: `frontend/e2e/theme.spec.ts`
- Test: `frontend/e2e/workspace-detail.spec.ts`
- Test: `frontend/e2e/workspace-graph.spec.ts`
- Test: `frontend/e2e/workspace-legacy.spec.ts` (new)
- Test: `frontend/e2e/workspace-pages.spec.ts`
- Test: `frontend/e2e/workspace-story.spec.ts`
- Test: `frontend/e2e/workspace.spec.ts`
- Test: `frontend/src/board/layout.test.ts`
- Test: `frontend/src/board/overview.test.ts`
- Test: `frontend/src/board/prefs.test.ts`
- Delete: `frontend/src/board/reducer.test.ts`
- Test: `frontend/src/stories/stories.test.ts`
- Test: `frontend/src/workspace/legacy.test.ts` (new)

**Interfaces:**
- Consumes: everything above; `api.locate`.
- Produces: `legacy(path, q, {base, nodeStory, oneBoard}): {to} | {locate} | null`; `base(id) = /r/${id}`;
  `prefs.keys.railW`, `keys.detailW`, `keys.railOpen`; e2e `startReview(page, cls = "101 102"): Promise<string>` (replaces `startStories`, `startWorkspace` and the old `startReview`).

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/ai.spec.ts`:

```diff
diff --git a/frontend/e2e/ai.spec.ts b/frontend/e2e/ai.spec.ts
index 9ed92fc..7d099f4 100644
--- a/frontend/e2e/ai.spec.ts
+++ b/frontend/e2e/ai.spec.ts
@@ -1,5 +1,5 @@
 import { expect, test } from "@playwright/test";
-import { login, startReview, startStories } from "./helpers";
+import { login, startReview } from "./helpers";
 
 const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py
 
@@ -7,51 +7,48 @@ test.describe("with an AI", () => {
   test.use({ baseURL: AI });
 
   test("✦ Explain rewrites a flow that the up-front pass left", async ({ page }) => {
-    await startReview(page);
-    await page.getByRole("tablist", { name: "Call flows" }).getByRole("tab").nth(1).click();
-    const info = page.locator(".bd-flowinfo");
-    const ask = info.getByRole("button", { name: /Explain/ });
+    const base = await startReview(page);
+    await page.goto(`${base}?view=graph&flow=2`);
+    const what = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text p").first();
+    const ask = what.getByRole("button", { name: /Explain/ });
     await expect(ask).toHaveText("✦ Explain");
     await expect(ask).toHaveAttribute("title", /^1 AI call · \d+ left on this review$/);
-    await expect(info.locator(".what")).not.toContainText("reaches logger_flush, which drops it");
+    await expect(what).not.toContainText("reaches logger_flush, which drops it");
     await ask.click();
-    await expect(info.locator(".what")).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.",
-                                                      { timeout: 30_000 });
-    await expect(info.locator(".what .ai-label")).toBeVisible();
+    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
+    await expect(what.locator(".ai-label")).toBeVisible();
     await expect(ask).toHaveText("✦ Explain again");
   });
 
-  test("✦ Explain retells a story's title and summary, on the story and in the list", async ({ page }) => {
-    await startStories(page);
-    await page.locator(".st-entry").first().click();
-    const head = page.locator(".st-head");
+  test("✦ Explain retells a story's title and summary, on the story and in the rail", async ({ page }) => {
+    await startReview(page);
+    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
+    const head = page.locator(".ws-story-head");
     await expect(head.locator(".ai-label")).toHaveCount(0);                  // this server's up-front pass skips stories
     await head.getByRole("button", { name: "✦ Explain" }).click();
     await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
     await expect(head.locator(".ai-label")).toBeVisible();
     await expect(head.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
-    await page.getByRole("link", { name: "Stories", exact: true }).first().click();
-    await expect(page.locator(".st-entry").first()).toContainText("uart_send's new error count reaches uart_errors");
+    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }))
+      .toContainText("uart_send's new error count reaches uart_errors");
   });
 
   test("a story shows the flow narrative the up-front pass wrote, and ✦ Explain on another flow updates it", async ({ page }) => {
-    await startStories(page);
-    const rid = page.url().match(/\/r\/(\d+)/)![1];
+    const base = await startReview(page);
+    const rid = base.split("/")[2];
     const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
     const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
     const told = board.flows.find((f: { what_source: string }) => f.what_source === "llm");
     const sid = ss.flow_story[told.id];
     const s = ss.stories.find((x: { id: string }) => x.id === sid);
-    await page.goto(`/r/${rid}/s/${sid}`);
-    const what = page.locator(".ph-what");
-    for (let i = 0; i < s.flows.indexOf(told.id); i++) await page.getByRole("button", { name: "Next flow" }).click();
+    await page.goto(`${base}/s/${sid}?flow=${s.flows.indexOf(told.id) + 1}`);
+    const what = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text p").first();
     await expect(what.locator(".ai-label")).toBeVisible();                     // the board's narrative, on the story
     await expect(what.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
     const other = ss.stories.flatMap((x: { id: string; flows: string[] }) => x.flows.map((f) => [x.id, f]))
       .find(([, f]: string[]) => f !== told.id)!;
-    await page.goto(`/r/${rid}/s/${other[0]}`);
     const st = ss.stories.find((x: { id: string }) => x.id === other[0]);
-    for (let i = 0; i < st.flows.indexOf(other[1]); i++) await page.getByRole("button", { name: "Next flow" }).click();
+    await page.goto(`${base}/s/${other[0]}?flow=${st.flows.indexOf(other[1]) + 1}`);
     const ask = what.getByRole("button", { name: /Explain/ });
     await expect(ask).toHaveText("✦ Explain");
     await ask.click();
```

`frontend/e2e/banner.spec.ts`:

```diff
diff --git a/frontend/e2e/banner.spec.ts b/frontend/e2e/banner.spec.ts
index 8e418fc..2fb3769 100644
--- a/frontend/e2e/banner.spec.ts
+++ b/frontend/e2e/banner.spec.ts
@@ -26,11 +26,13 @@ test.describe("on a network host name", () => {
   test.describe("on a phone", () => {
     test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent, isMobile: true, hasTouch: true });
 
-    test("the banner and the phone board fit the screen together", async ({ page }) => {
+    test("the banner and the phone workspace fit the screen together", async ({ page }) => {
       await startReview(page);
       await expect(page.getByRole("alert")).toBeVisible();
-      const tabs = (await page.locator(".ph-tabs").boundingBox())!;
-      expect(tabs.y + tabs.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);   // the tab bar stays on screen
+      await page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first().click();
+      const bar = (await page.locator(".ws-phonebar").boundingBox())!;
+      expect(bar.y).toBeGreaterThanOrEqual(0);                                             // the back bar stays on screen
+      expect(bar.y + bar.height).toBeLessThanOrEqual(page.viewportSize()!.height);
       expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
     });
   });
```

`frontend/e2e/helpers.ts`:

```diff
diff --git a/frontend/e2e/helpers.ts b/frontend/e2e/helpers.ts
index 68400ca..d3f0a0e 100644
--- a/frontend/e2e/helpers.ts
+++ b/frontend/e2e/helpers.ts
@@ -7,29 +7,14 @@ export async function login(page: Page, user = "demo") {
   await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
 }
 
-/** Log in as the demo owner, review fixture CLs 101+102 from the landing page and wait for the story list. */
-export async function startStories(page: Page) {
+/** Log in as the demo owner, review fixture CLs 101+102 (the large fixture's are 201 202) from the landing page and
+ * wait for the rail's stories; returns the review's address ("/r/12"). */
+export async function startReview(page: Page, cls = "101 102"): Promise<string> {
   await login(page);
-  await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
+  await page.getByLabel("Changelists (shelved or submitted)").fill(cls);
   await page.getByRole("button", { name: "Start review" }).click();
-  await expect(page.locator(".st-entry").first()).toBeVisible({ timeout: 60_000 });
-}
-
-/** As startStories, then open the board ("Boards ›" on the story list). */
-export async function startReview(page: Page) {
-  await startStories(page);
-  await page.getByRole("link", { name: "Boards ›" }).click();
-  // desktop shows the canvas; phones open on the flow reader (spec §13)
-  await expect(page.locator(".bd-node, .ph-step").first()).toBeVisible({ timeout: 60_000 });
-}
-
-/** As startStories, then open the same review in the workspace (spec 2026-10-04-review-workspace; `/w/` while built). */
-export async function startWorkspace(page: Page): Promise<string> {
-  await startStories(page);
-  const id = page.url().match(/\/r\/(\d+)/)![1];
-  await page.goto(`/w/${id}`);
-  await expect(page.locator(".ws-rail")).toBeVisible({ timeout: 60_000 });
-  return `/w/${id}`;
+  await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first()).toBeVisible({ timeout: 60_000 });
+  return page.url().match(/\/r\/\d+/)![0];
 }
 
 /** No node id is ever shown (spec §8): visible text never matches N<digits>. */
```

`frontend/e2e/landing.spec.ts`:

```diff
diff --git a/frontend/e2e/landing.spec.ts b/frontend/e2e/landing.spec.ts
index 1b8d701..4aad404 100644
--- a/frontend/e2e/landing.spec.ts
+++ b/frontend/e2e/landing.spec.ts
@@ -12,7 +12,7 @@ test.describe("desktop", () => {
     await page.getByLabel("Changelists (shelved or submitted)").fill("102");
     await page.getByLabel("Title (optional)").fill(title);
     await page.getByRole("button", { name: "Start review" }).click();
-    await expect(page.locator(".st-entry").first()).toBeVisible({ timeout: 60_000 });      // a review opens on its stories
+    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first()).toBeVisible({ timeout: 60_000 }); // a review opens on its workspace
     await page.getByRole("link", { name: "Reviews" }).first().click();
 
     const rows = page.locator(".rv-list .rv-row");
```

`frontend/e2e/mention.spec.ts`:

```diff
diff --git a/frontend/e2e/mention.spec.ts b/frontend/e2e/mention.spec.ts
index 3a2e5b1..0120a66 100644
--- a/frontend/e2e/mention.spec.ts
+++ b/frontend/e2e/mention.spec.ts
@@ -3,10 +3,11 @@ import { startReview } from "./helpers";
 
 const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py
 
-/** Open uart.c in the file viewer and start a comment on its new `return -2;` line. */
+/** Open uart.c's diff in the detail panel and start a comment on its new `return -2;` line. */
 async function commentOnReturn(page: Page): Promise<{ viewer: Locator; box: Locator }> {
-  await page.locator(".bd-about .tree .file", { hasText: "uart.c" }).first().click();
-  const viewer = page.locator(".bd-viewer");
+  await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
+  await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+  const viewer = page.getByRole("complementary", { name: "Code: uart.c" });
   await viewer.getByRole("button", { name: "Stacked" }).click();
   await viewer.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
   return { viewer, box: viewer.getByPlaceholder("Leave a comment…") };
```

`frontend/e2e/theme.spec.ts`:

```diff
diff --git a/frontend/e2e/theme.spec.ts b/frontend/e2e/theme.spec.ts
index 8081be2..72cab82 100644
--- a/frontend/e2e/theme.spec.ts
+++ b/frontend/e2e/theme.spec.ts
@@ -6,7 +6,8 @@ test.use({ viewport: { width: 1440, height: 900 } });
 /** WCAG contrast ratio between an element's text colour and the first opaque background behind it. */
 async function contrast(page: Page, selector: string) {
   return page.locator(selector).first().evaluate((el) => {
-    const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).map(Number);
+    // rgb(0-255…) or, for color-mix() backgrounds, color(srgb 0-1…)
+    const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).map(Number).map((v, i) => c.startsWith("color(") && i < 3 ? v * 255 : v);
     const lum = ([r, g, b]: number[]) => {
       const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
       return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
@@ -22,22 +23,32 @@ async function contrast(page: Page, selector: string) {
   });
 }
 
+/** A changed function of story S1 (its first step), to open in the detail panel. */
+async function firstChanged(page: Page) {
+  const id = page.url().match(/\/r\/(\d+)/)![1];
+  const s1 = await (await page.request.get(`/api/reviews/${id}/stories/S1`)).json();
+  return s1.board.nodes.find((n: { change: unknown }) => n.change).id as string;
+}
+
 const CHECKS = [
-  ".bd-flowinfo .what",            // flow summary text
+  ".ws-flow-text p",               // flow summary text
   ".bd-node:not(.chg) .lbl",       // node label (changed nodes sit on a fixed amber gradient)
-  ".bd-card .bd-code .src",        // code in a card
+  ".ws-detail .bd-code .src",      // code in the detail panel
   ".bd-ann .k",                    // annotation label
-  ".bd-about .intent",             // change panel text
-  ".bd-toolbar .bd-ibtn",          // a board button
+  ".ws-row-title",                 // a rail row
+  ".ws-crumbs a",                  // a breadcrumb
+  ".bd-toolbar .bd-ibtn",          // a graph button
   ".topbar a",                     // app chrome link
 ];
 
 for (const theme of ["light", "dark"] as const) {
   test(`readable controls and text in ${theme} mode`, async ({ page }) => {
     await page.emulateMedia({ colorScheme: theme });
-    await startReview(page);
+    const base = await startReview(page);
     await expect(page.locator("html")).toHaveAttribute("data-theme", theme);      // follows the system by default
-    await expect(page.locator(".bd-card .bd-code .src").first()).toBeVisible();
+    await page.goto(`${base}/s/S1?view=graph&open=${await firstChanged(page)}`);
+    await expect(page.locator(".ws-detail .bd-code .src").first()).toBeVisible();
+    await expect(page.locator(".bd-node").first()).toBeVisible();
     for (const sel of CHECKS) expect(await contrast(page, sel), sel).toBeGreaterThanOrEqual(4.5);
     await page.goto("/");
     const input = page.getByRole("searchbox", { name: "Search reviews" });            // on the page surface
```

`frontend/e2e/workspace-detail.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace-detail.spec.ts b/frontend/e2e/workspace-detail.spec.ts
index 248ed31..7832ff0 100644
--- a/frontend/e2e/workspace-detail.spec.ts
+++ b/frontend/e2e/workspace-detail.spec.ts
@@ -1,5 +1,5 @@
 import { devices, expect, test } from "@playwright/test";
-import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";
+import { expectNamed, expectNoNodeIds, startReview } from "./helpers";
 
 /** The detail panel (spec 2026-10-04-review-workspace §3.7): a node's code or a file's diff, on demand. */
 
@@ -7,7 +7,7 @@ test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
   test("a file from the rail opens its diff; ✕ closes it", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
     await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
     await expect(page).toHaveURL(/\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c$/);
@@ -24,7 +24,7 @@ test.describe("desktop", () => {
   });
 
   test("a node opens its function, its story and the full file", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
     const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
     await page.goto(`${base}?open=${send}`);
@@ -39,8 +39,69 @@ test.describe("desktop", () => {
     await expectNoNodeIds(page);
   });
 
+  test("a line comment in a file's diff shows in that function's code", async ({ page }) => {
+    const base = await startReview(page);
+    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    const file = page.getByRole("complementary", { name: "Code: uart.c" });
+    await file.getByRole("button", { name: "Stacked" }).click();
+    await file.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
+    await file.getByPlaceholder("Leave a comment…").fill("Does logger_flush handle -2?");
+    await file.getByRole("button", { name: "Comment", exact: true }).click();
+    await expect(file.getByText("Does logger_flush handle -2?")).toBeVisible();
+    const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
+    const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
+    await page.goto(`${base}?open=${send}`);
+    await expect(page.getByRole("complementary", { name: "Code: uart_send" }).getByText("Does logger_flush handle -2?")).toBeVisible();
+  });
+
+  test("one changelist's diff keeps the comments made on it", async ({ page }) => {
+    await startReview(page);
+    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    const file = page.getByRole("complementary", { name: "Code: uart.c" });
+    await expect(file.locator(".act")).toContainText("edit");
+    await file.getByRole("button", { name: "Stacked" }).click();
+    await file.getByLabel("Changelist").selectOption("101");
+    await file.locator(".bd-ln.a").first().click();
+    await file.locator("textarea").fill("only in CL 101");
+    await file.getByRole("button", { name: "Comment", exact: true }).click();
+    await expect(file.getByText("only in CL 101")).toBeVisible();
+    await file.getByLabel("Changelist").selectOption("all");
+    await expect(file.getByText("only in CL 101")).toHaveCount(0);
+    await file.getByLabel("Changelist").selectOption("101");
+    await expect(file.getByText("only in CL 101")).toBeVisible();
+  });
+
+  test("a side effect on the whole change opens its file at a folded line, shown", async ({ page }) => {
+    await startReview(page);
+    await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).click();
+    await page.getByRole("link", { name: "Open uart_init at line 8" }).click();       // line 8: outside the hunks
+    await expect(page.getByRole("complementary", { name: "Code: uart.c" }).locator('.focus[data-n="8"]')).toBeVisible();
+  });
+
+  test("review, layer and function comments show where they belong", async ({ page }) => {
+    const base = await startReview(page);
+    const rid = base.split("/")[2];
+    const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
+    const send = board.nodes.find((n: { label: string }) => n.label === "uart_send");
+    const post = (body: string, anchor_kind: string, anchor: object) =>
+      page.request.post(`/api/reviews/${rid}/comments`, { data: { body, anchor_kind, anchor } });
+    await post("overall: please split the CLs", "review", {});
+    await post("driver layer looks risky", "chapter", { level: send.layer });
+    await post("why -2 and not -EINVAL?", "function", { key: send.key });
+    await page.goto(`${base}?open=${send.id}`);
+    await expect(page.getByRole("complementary", { name: "Code: uart_send" }).getByText("why -2 and not -EINVAL?")).toBeVisible();
+    const talk = page.locator("section", { has: page.getByRole("heading", { name: "Discussion" }) });
+    await expect(talk.getByText("overall: please split the CLs")).toBeVisible();
+    await expect(talk.getByText("driver layer looks risky")).toBeVisible();
+    await talk.getByPlaceholder("Start another thread…").first().fill("agreed");
+    await talk.getByRole("button", { name: "Comment" }).first().click();
+    await expect(talk.getByText("agreed")).toBeVisible();
+  });
+
   test("an unknown node says so", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.goto(`${base}?open=N99999`);
     await expect(page.locator(".ws-detail .banner")).toContainText("This function isn't in this review.");
   });
@@ -51,7 +112,7 @@ test.describe("phone", () => {
     deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });
 
   test("the code opens as a full-screen sheet whose top bar names it", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c:17")}`);
     await expect(page.locator(".ws-rail, .ws-centre")).toHaveCount(0);
     const bar = page.locator(".ws-detail .ws-phonebar");
@@ -66,7 +127,7 @@ test.describe("neighbours", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
   test("callers and callees; a row moves the panel and Back returns", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
     const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
     await page.goto(`${base}?open=${send}`);
```

`frontend/e2e/workspace-graph.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace-graph.spec.ts b/frontend/e2e/workspace-graph.spec.ts
index 9b5eb9f..19c2cf2 100644
--- a/frontend/e2e/workspace-graph.spec.ts
+++ b/frontend/e2e/workspace-graph.spec.ts
@@ -1,16 +1,26 @@
-import { expect, type Page, test } from "@playwright/test";
-import { expectNamed, expectNoNodeIds, flowStripHolds, startWorkspace } from "./helpers";
+import { devices, expect, type Page, test } from "@playwright/test";
+import { expectNamed, expectNoNodeIds, flowStripHolds, startReview } from "./helpers";
 
 /** Graphs in the workspace (spec 2026-10-04-review-workspace §3.2, §3.6): a node click opens its code and a second
  * click closes it; "+N callers" opens Neighbours; the flow strip keeps its controls in place and never overflows. */
 
+/** A node the pointer reaches at its centre (the whole graph can be panned past the stage's edges). */
+async function reachable(page: Page) {
+  const label = await page.locator(".bd-node").evaluateAll((els) => els.find((e) => {
+    const r = e.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
+    return hit && e.contains(hit) && !hit.closest("button:not(.bd-node)");
+  })?.querySelector(".lbl")?.textContent ?? null);
+  expect(label).not.toBeNull();
+  return node(page, label!);
+}
+
 const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });
 
 test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
   test("the review's graph: open full graph, select and deselect a node, flows keep their controls", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.getByRole("link", { name: "Open the full graph" }).click();
     await expect(page).toHaveURL(new RegExp(`${base}\\?view=graph$`));
     await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Graph");
@@ -30,7 +40,7 @@ test.describe("desktop", () => {
   });
 
   test("a file from the rail highlights its functions on the graph and never refilters it", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.goto(`${base}?view=graph`);
     await expect(page.locator(".bd-node").first()).toBeVisible();
     const count = await page.locator(".bd-node").count();
@@ -39,4 +49,85 @@ test.describe("desktop", () => {
     await expect(page.locator(".bd-node.lit").first()).toBeVisible();
     await expect(page.locator(".bd-node")).toHaveCount(count);
   });
+
+  test("drag a node anywhere, reset; moves are kept per layout; panning never selects text", async ({ page }) => {
+    const base = await startReview(page);
+    await page.goto(`${base}?view=graph`);
+    await page.getByRole("button", { name: "Whole graph" }).click();
+    await expect(page.locator(".bd-node").first()).toBeVisible();
+    await page.waitForTimeout(500);                                   // centring animation
+    let main = await reachable(page);
+    const drag = async (dx: number, dy: number) => {
+      const a = (await main.boundingBox())!;
+      await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
+      await page.mouse.down();
+      await page.mouse.move(a.x + a.width / 2 + dx, a.y + a.height / 2 + dy, { steps: 10 });
+      await page.mouse.up();
+      const b = (await main.boundingBox())!;
+      expect(b.x - a.x).toBeGreaterThan(60);
+      expect(b.y - a.y).toBeGreaterThan(20);                         // free to leave its band
+    };
+    await drag(160, 40);
+    await expect(page).not.toHaveURL(/open=/);                        // a drag is not a click
+    await expect(main).toHaveClass(/\bmoved\b/);
+    await page.getByRole("button", { name: "Reset layout" }).click();
+    await expect(main).not.toHaveClass(/\bmoved\b/);
+
+    await page.getByRole("button", { name: "Call depth" }).click();
+    await expect(page.locator(".bd-blabel", { hasText: "depth 0 · entry" })).toBeVisible();
+    await page.waitForTimeout(500);
+    main = await reachable(page);
+    await drag(120, 150);
+    await page.getByRole("button", { name: "Layers" }).click();
+    await expect(main).not.toHaveClass(/\bmoved\b/);
+    await page.getByRole("button", { name: "Call depth" }).click();
+    await expect(main).toHaveClass(/\bmoved\b/);
+
+    const stage = (await page.locator(".bd-stage").boundingBox())!;
+    await page.mouse.move(stage.x + stage.width - 30, stage.y + stage.height - 40);
+    await page.mouse.down();
+    await page.mouse.move(stage.x + 30, stage.y + 120, { steps: 12 });
+    await page.mouse.up();
+    expect(await page.evaluate(() => window.getSelection()?.toString() ?? "")).toBe("");
+  });
+});
+
+test.describe("phone", () => {
+  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
+    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });
+
+  test("pinch to zoom, tap a node for its code sheet, long-press to move it", async ({ page }) => {
+    const base = await startReview(page);
+    await page.goto(`${base}?view=graph`);
+    const send = page.locator(".bd-node.chg", { hasText: "uart_send" });
+    await expect(send).toBeVisible();
+    await page.waitForTimeout(500);
+    const cdp = await page.context().newCDPSession(page);
+    const touch = (type: string, pts: [number, number][]) =>
+      cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
+    const centre = async () => { const b = (await send.boundingBox())!; return [b.x + b.width / 2, b.y + b.height / 2, b.width] as const; };
+
+    const [x0, y0, w0] = await centre();                               // pinch out: it grows and stays under the fingers
+    await touch("touchStart", [[x0 - 30, y0], [x0 + 30, y0]]);
+    for (let k = 1; k <= 6; k++) await touch("touchMove", [[x0 - 30 - k * 12, y0], [x0 + 30 + k * 12, y0]]);
+    await touch("touchEnd", []);
+    const [x1, y1, w1] = await centre();
+    expect(w1).toBeGreaterThan(w0 * 1.5);
+    expect(Math.hypot(x1 - x0, y1 - y0)).toBeLessThan(40);
+
+    await send.tap();                                                  // tap: the code opens as a sheet
+    const sheet = page.getByRole("complementary", { name: "Code: uart_send" });
+    await expect(sheet.locator(".bd-ann").first()).toContainText("through alias");
+    await expect(sheet.locator("textarea")).toHaveCount(0);           // the tap's click must not land in the sheet
+    await page.goBack();
+    await expect(sheet).toHaveCount(0);
+
+    await expect(send).toBeVisible();
+    const [x2, y2] = await centre();                                   // long-press, then drag: the node moves
+    await touch("touchStart", [[x2, y2]]);
+    await page.waitForTimeout(600);
+    for (let k = 1; k <= 5; k++) await touch("touchMove", [[x2 + k * 14, y2 + k * 10]]);
+    await touch("touchEnd", []);
+    await expect(send).toHaveClass(/\bmoved\b/);
+  });
 });
```

`frontend/e2e/workspace-legacy.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

/** Addresses from before the workspace still land (spec 2026-10-04-review-workspace §2.3). */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the old tabs, the board, a cited node and /w/ go to where those things live now", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
    const [nid, sid] = Object.entries(ss.node_story as Record<string, string>)[0];
    for (const [old, now] of [["/files", "#files"], ["/findings", "#findings"], ["/cls", "#changeset"], ["/overview", "#map"],
                              ["/board", "?view=graph"]]) {
      await page.goto(`${base}${old}`);
      await expect(page).toHaveURL(new RegExp(`${base}${now.replace("?", "\\?")}$`));
    }
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await page.goto(`${base}/board?node=${nid}`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/${sid}\\?open=${nid}$`));
    await expect(page.locator(".ws-detail")).toBeVisible();
    await page.goto(`${base}/s/${sid}?tab=graph`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/${sid}\\?view=graph$`));
    await page.goto(`/w/${rid}/s/${sid}?flow=1`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/${sid}\\?flow=1$`));
  });
});

test.describe("a large change", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  test("a cited node outside every story opens the part holding it; one inside a story opens that story", async ({ page }) => {
    const base = await startReview(page, "201 202");
    const rid = base.split("/")[2];
    const ov = await (await page.request.get(`/api/reviews/${rid}/overview`)).json();
    const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
    const all: { id: string; name: string; nodes: string[] }[] = ov.clusters;
    const told = all.flatMap((c) => c.nodes).find((n) => ss.node_story[n])!;
    await page.goto(`${base}/overview?node=${told}`);
    await expect(page).toHaveURL(new RegExp(`/s/${ss.node_story[told]}\\?open=${told}$`));
    // only the server knows which part holds a node outside every story: serve the stories without this one's
    const part = all.find((c) => c.name === "hal/regs")!, nid = part.nodes[0];
    const { [nid]: _, ...rest } = ss.node_story;
    await page.route(`**/api/reviews/${rid}/stories`, (r) => r.fulfill({ json: { ...ss, node_story: rest } }));
    await page.goto(`${base}?node=${nid}`);
    await expect(page).toHaveURL(new RegExp(`/c/${part.id}\\?open=${nid}$`));
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText(part.name);
  });
});
```

`frontend/e2e/workspace-pages.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace-pages.spec.ts b/frontend/e2e/workspace-pages.spec.ts
index 5942cb7..5a28359 100644
--- a/frontend/e2e/workspace-pages.spec.ts
+++ b/frontend/e2e/workspace-pages.spec.ts
@@ -1,5 +1,5 @@
 import { expect, test } from "@playwright/test";
-import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";
+import { expectNamed, expectNoNodeIds, startReview } from "./helpers";
 
 /** Finding, CL and cluster pages (spec 2026-10-04-review-workspace §3.3–§3.5). */
 
@@ -7,7 +7,7 @@ test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
   test("a finding: to its story and back, on the graph, evidence opens the diff at its line", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.goto(`${base}/f/F5`);
     await expect(page.locator(".ws-finding h2")).toContainText("uart_send: new return value(s) -2");
     await expect(page.getByRole("region", { name: "AI analysis" })).toContainText("AI analysis unavailable.");
@@ -35,7 +35,7 @@ test.describe("desktop", () => {
   });
 
   test("a changelist: its Swarm card, its files filtered to it, the stories and findings drawn from it", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.locator(".ws-rail").getByRole("link", { name: "Open CL 102" }).click();
     await expect(page).toHaveURL(new RegExp(`${base}/cl/102$`));
     await expect(page.locator(".ws-finding h2")).toHaveText("CL 102 · uart: add flags field; hal_write takes unsigned reg");
```

`frontend/e2e/workspace-story.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace-story.spec.ts b/frontend/e2e/workspace-story.spec.ts
index 8f01178..414593f 100644
--- a/frontend/e2e/workspace-story.spec.ts
+++ b/frontend/e2e/workspace-story.spec.ts
@@ -1,5 +1,5 @@
 import { devices, expect, type Page, test } from "@playwright/test";
-import { expectNamed, expectNoNodeIds, flowStripHolds, startWorkspace } from "./helpers";
+import { expectNamed, expectNoNodeIds, flowStripHolds, startReview } from "./helpers";
 
 /** A story in the workspace (spec 2026-10-04-review-workspace §3.2, §2.4). */
 
@@ -10,7 +10,7 @@ test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
   test("steps open the detail panel and mark the step; flows replace history; findings link to their pages", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
     await expect(page.locator(".ws-story-head h2")).toContainText("uart_send now writes Uart::errors");
     await expect(page.getByRole("tab", { name: "Steps" })).toHaveAttribute("aria-selected", "true");
@@ -32,7 +32,7 @@ test.describe("desktop", () => {
   });
 
   test("the graph: a node click opens and closes its code; ‹ › keep their place between stories", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.goto(`${base}/s/S1`);
     await page.getByRole("tab", { name: "Graph" }).click();
     await expect(page).toHaveURL(/\/s\/S1\?view=graph$/);
@@ -55,7 +55,7 @@ test.describe("desktop", () => {
   });
 
   test("leaving a story for a CL and coming back returns to the same view, flow and open node", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.goto(`${base}/s/S1?view=graph`);
     await page.getByRole("button", { name: "Next flow" }).click();
     await node(page, "uart_send").click();
@@ -68,6 +68,49 @@ test.describe("desktop", () => {
     await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
     await expect(page.locator(".ws-flow-pos")).toHaveText("flow 2 of 2");
   });
+
+  test("a review without stories (run before them) leaves Stories out of the rail", async ({ page }) => {
+    const base = await startReview(page);
+    await page.route(`**/api/reviews/${base.split("/")[2]}/stories`, (r) =>
+      r.fulfill({ status: 404, json: { detail: "this review has no stories: re-run it" } }));
+    await page.reload();
+    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to finding/ }).first()).toBeAttached();
+    await expect(page.locator(".ws-rail").getByRole("button", { name: /^Stories/ })).toHaveCount(0);
+    await expect(page.getByRole("region", { name: "The map" })).toBeVisible();
+  });
+
+  test("a repeated edit lists its sites by file, hides tests and links its effects", async ({ page }) => {
+    const base = await startReview(page);
+    const id = base.split("/")[2];
+    // neither e2e fixture has a repeated edit: this story is served as the API would for one
+    const site = (path: string, line: number, test = false, effect: string | null = null) => ({
+      path, line, function: test ? "test_free" : "free_it", node: null, before: "git_vector_free(&v);",
+      after: "git_vector_dispose(&v);", test, effect, other_edits: null });
+    const story = { id: "S9", kind: "mechanical", title: "`git_vector_free` → `git_vector_dispose` at 3 sites in 2 files (1 in tests)",
+      summary: "Every changed line in these 2 functions is this one edit.", text_source: "template", risk: null,
+      counts: { sites: 3, files: 2, test_sites: 1 }, nodes: [], flows: [], findings: [], board: null, cls: [101],
+      sub: ["git_vector_free", "git_vector_dispose"], subs: [], collapsed: false };
+    const real = await (await page.request.get(`/api/reviews/${id}/stories`)).json();
+    await page.route(`**/api/reviews/${id}/stories`, (r) => r.fulfill({ json: { ...real, stories: [...real.stories, story] } }));
+    await page.route(`**/api/reviews/${id}/stories/S9`, (r) => r.fulfill({ json: {
+      story, board: { nodes: [], edges: [], flows: [], impacts: [], layers: [], about: real.about ?? { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] }, hidden_nodes: 0 },
+      graph: null, functions: [], also_in: [{ node: "N7", label: "busy", story: "S2" }],
+      sites: [site("//fixture/driver/uart.c", 12, false, "S1"), site("//fixture/driver/uart.c", 30), site("//fixture/tests/t.c", 4, true)] } }));
+    await page.goto(`${base}/s/S9`);
+    const sites = page.locator(".ws-sites li");
+    await expect(sites).toHaveCount(3);
+    await expect(page.locator(".ws-dir h3").first()).toContainText("//fixture/driver");
+    await expect(sites.first()).toContainText("free_it · line 12");
+    await page.getByLabel(/Hide tests/).check();
+    await expect(sites).toHaveCount(2);
+    await sites.first().getByRole("link", { name: "Open uart.c at line 12" }).click();
+    await expect(page.getByRole("complementary", { name: "Code: uart.c" })).toBeVisible();
+    await page.locator(".ws-mech").getByRole("link", { name: "Go to story S2" }).click();
+    await expect(page).toHaveURL(/\/s\/S2$/);
+    await page.goBack();
+    await sites.first().getByRole("link", { name: "Go to story S1" }).click();
+    await expect(page).toHaveURL(/\/s\/S1$/);
+  });
 });
 
 test.describe("phone", () => {
@@ -75,7 +118,7 @@ test.describe("phone", () => {
     deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });
 
   test("rail → story → detail sheet, each top bar naming the place", async ({ page }) => {
-    await startWorkspace(page);
+    await startReview(page);
     await page.getByRole("link", { name: /^Go to story S1/ }).click();
     await expect(page.locator(".ws-phonebar")).toContainText("‹ Stories");
     await step(page, "uart_send").click();
```

`frontend/e2e/workspace.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index b11ba8e..d713818 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -1,5 +1,5 @@
 import { devices, expect, test } from "@playwright/test";
-import { expectNamed, expectNoNodeIds, login, startWorkspace } from "./helpers";
+import { expectNamed, expectNoNodeIds, startReview } from "./helpers";
 
 /** The workspace shell (spec 2026-10-04-review-workspace §2): rail, breadcrumb, addresses, phone levels. */
 
@@ -7,7 +7,7 @@ test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
   test("the rail lists the review, its CLs, the stories drawn from them, findings and files", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     const rail = page.locator(".ws-rail");
     await expect(rail.locator(".ws-sec h2")).toHaveText([/Change set \(2 CLs\)/, /Stories \(from 2 CLs\)/, /Findings \(6\)/, /Files \(4\)/]);
     await expect(rail.getByRole("link", { name: "Go to the whole change" })).toHaveAttribute("aria-current", "page");
@@ -38,7 +38,7 @@ test.describe("desktop", () => {
   });
 
   test("the whole change: what it is for, why it is risky, then the rest", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     const page_ = page.locator(".ws-whole");
     await expect(page_.locator("h2")).toHaveText(["What this change is trying to do", "Why it is high risk",
                                                   /^The map/, "Files with side effects", "Discussion"]);
@@ -53,7 +53,7 @@ test.describe("desktop", () => {
   });
 
   test("an address to something that does not exist says so", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await page.goto(`${base}/s/S9`);
     await expect(page.locator(".ws-centre .banner")).toContainText("Story S9 isn't in this review.");
     await page.getByRole("link", { name: "Whole change" }).last().click();
@@ -65,7 +65,7 @@ test.describe("tablet", () => {
   test.use({ viewport: { width: 900, height: 1000 } });
 
   test("the rail is a drawer behind ☰", async ({ page }) => {
-    await startWorkspace(page);
+    await startReview(page);
     const rail = page.locator(".ws-rail");
     await expect(rail).not.toBeInViewport();
     await page.getByRole("button", { name: "Review contents" }).click();
@@ -81,7 +81,7 @@ test.describe("phone", () => {
     deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });
 
   test("the rail is home; an item's top bar names where it came from", async ({ page }) => {
-    const base = await startWorkspace(page);
+    const base = await startReview(page);
     await expect(page.locator(".topbar")).toBeHidden();
     await expect(page.locator(".ws-centre")).toHaveCount(0);
     await page.getByRole("link", { name: /^Go to story S1/ }).click();
@@ -100,12 +100,7 @@ test.describe("a large change", () => {
   test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });
 
   test("the whole change maps its parts; a part opens its page", async ({ page }) => {
-    await login(page);
-    await page.getByLabel("Changelists (shelved or submitted)").fill("201 202");
-    await page.getByRole("button", { name: "Start review" }).click();
-    await expect(page.locator(".st-entry").first()).toBeVisible({ timeout: 60_000 });
-    const base = `/w/${page.url().match(/\/r\/(\d+)/)![1]}`;
-    await page.goto(base);
+    const base = await startReview(page, "201 202");
     const map = page.getByRole("region", { name: "The map" });
     await expect(map.locator(".ov-block")).toHaveCount(7);
     await expect(map.getByRole("region", { name: "Layer drv" })).toContainText("drv/dma");
@@ -127,3 +122,22 @@ test.describe("a large change", () => {
     await expect(page).toHaveURL(/open=N\d+$/);
   });
 });
+
+test.describe("a large change on a phone", () => {
+  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
+
+  test("the map stacks the parts; a part opens with its place among them", async ({ page }) => {
+    await startReview(page, "201 202");
+    await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).click();
+    const first = page.locator(".ov-block").first(), second = page.locator(".ov-block").nth(1);
+    const a = (await first.boundingBox())!, b = (await second.boundingBox())!;
+    expect(b.y).toBeGreaterThan(a.y + a.height - 1);                      // stacked, not side by side
+    expect(a.width).toBeGreaterThan(300);
+    await expect(first).toHaveAttribute("aria-label", /^Open /);    // each part is a link to its page
+    await first.click();
+    await expect(page.locator(".bd-node").first()).toBeVisible();
+    await expect(page.getByRole("link", { name: /^Next part:/ })).toBeVisible();
+    await expect(page.getByRole("link", { name: /^Back to Map/ })).toBeVisible();
+    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
+  });
+});
```

`frontend/src/board/layout.test.ts`:

```diff
diff --git a/frontend/src/board/layout.test.ts b/frontend/src/board/layout.test.ts
index 5901d06..5f8c879 100644
--- a/frontend/src/board/layout.test.ts
+++ b/frontend/src/board/layout.test.ts
@@ -1,5 +1,5 @@
 import { describe, expect, it } from "vitest";
-import { centrePan, flowSets, layerRows, placeCards, worldNodes } from "./layout";
+import { centrePan, flowSets, layerRows, worldNodes } from "./layout";
 import type { Board, BoardEdge, BoardFlow, BoardNode } from "./types";
 
 const node = (id: string, layer: number | null, x: number) => ({
@@ -33,26 +33,6 @@ describe("layout", () => {
     expect([...s.pairs]).toEqual(["A>B", "B>C"]);
     expect(flowSets(f, true).onPath.size).toBe(0);
   });
-
-  it("places cards beside their node without overlap and inside the canvas", () => {
-    const at = { x: 500, y: 300, v: 1, s: 1 };
-    const rects = placeCards([{ id: "1", at, w: 300, h: 200, collapsed: false },
-                              { id: "2", at, w: 300, h: 200, collapsed: false }], 1200, 800);
-    const a = rects.get("1")!, b = rects.get("2")!;
-    expect(a.x).toBe(600);                                     // right of the node, clear of it
-    expect(b.x + b.w).toBeLessThanOrEqual(450);                // then left of it
-    for (const r of [a, b]) expect(r.x >= 8 && r.y >= 8 && r.x + r.w <= 1192 && r.y + r.h <= 792).toBe(true);
-  });
-
-  it("keeps dragged offsets, scales by the lens and puts pills under the node", () => {
-    const rects = placeCards([
-      { id: "d", at: { x: 400, y: 300, v: 1, s: 0.4 }, w: 300, h: 200, collapsed: false, offset: { x: 10, y: 20 } },
-      { id: "p", at: { x: 600, y: 300, v: 1, s: 1 }, w: 100, h: 30, collapsed: true },
-    ], 1200, 800);
-    const d = rects.get("d")!;
-    expect([d.x, d.y, Math.round(d.w), Math.round(d.h), d.k]).toEqual([410, 320, 165, 110, 0.55]);
-    expect(rects.get("p")).toEqual({ x: 550, y: 324, w: 100, h: 30, k: 1 });
-  });
 });
 
 const fn = (id: string, layer: number | null = 1, x = 0) => node(id, layer, x);
```

`frontend/src/board/overview.test.ts`:

```diff
diff --git a/frontend/src/board/overview.test.ts b/frontend/src/board/overview.test.ts
index 45b97de..3699c77 100644
--- a/frontend/src/board/overview.test.ts
+++ b/frontend/src/board/overview.test.ts
@@ -1,5 +1,5 @@
 import { describe, expect, it } from "vitest";
-import { addExpansion, bandsOf, clusterOfFile, linkLines, linkedTo, nearestCluster, stepCluster } from "./overview";
+import { bandsOf, linkLines, stepCluster } from "./overview";
 import type { Overview } from "./types";
 
 const c = (id: string, name: string, level: number | null, over: Partial<Overview["clusters"][0]> = {}) => ({
@@ -33,12 +33,6 @@ describe("linkLines", () => {
   });
 });
 
-describe("linkedTo", () => {
-  it("is every cluster linked either way", () => {
-    expect([...linkedTo(ov, "C2")].sort()).toEqual(["C1", "C4"]);
-  });
-});
-
 describe("stepCluster", () => {
   it("moves through the clusters in risk order, wrapping", () => {
     expect(stepCluster(ov, "C1", 1)).toBe("C2");
@@ -46,33 +40,3 @@ describe("stepCluster", () => {
     expect(stepCluster(ov, "C1", -1)).toBe("C4");
   });
 });
-
-describe("clusterOfFile", () => {
-  it("finds the cluster whose changed code is in a file", () => {
-    expect(clusterOfFile(ov, "//d/svc/logger.c")).toBe("C1");
-    expect(clusterOfFile(ov, "//d/none.c")).toBeNull();
-  });
-});
-
-describe("addExpansion", () => {
-  it("asks again for the same node: each ask adds the next neighbours", () => {
-    expect(addExpansion([], "N12", "callers")).toEqual(["N12:callers"]);
-    expect(addExpansion(["N12:callers"], "N12", "callers")).toEqual(["N12:callers", "N12:callers"]);
-    expect(addExpansion(["N12:callers"], "N9", "callees")).toEqual(["N12:callers", "N9:callees"]);
-  });
-});
-
-describe("nearestCluster", () => {
-  const two: Overview = { ...ov, clusters: [ov.clusters[0], { ...ov.clusters[1], files: ["//d/drv/uart/uart.c"] }, ...ov.clusters.slice(2)] };
-  it("is the file's own cluster when its changed code is in one", () => {
-    expect(nearestCluster(two, "//d/svc/logger.c")).toBe("C1");
-  });
-  it("is the cluster with code nearest the file when it has no changed function (a header of macros)", () => {
-    expect(nearestCluster(two, "//d/drv/uart/regs.h")).toBe("C2");
-    expect(nearestCluster(two, "//d/drv/dma.h")).toBe("C2");
-    expect(nearestCluster(two, "//d/svc/logger.h")).toBe("C1");
-  });
-  it("is the riskiest cluster when nothing is nearer", () => {
-    expect(nearestCluster(two, "//e/other.h")).toBe("C1");
-  });
-});
```

`frontend/src/board/prefs.test.ts`:

```diff
diff --git a/frontend/src/board/prefs.test.ts b/frontend/src/board/prefs.test.ts
index c20fa26..4fedf1c 100644
--- a/frontend/src/board/prefs.test.ts
+++ b/frontend/src/board/prefs.test.ts
@@ -17,7 +17,7 @@ describe("prefs", () => {
     expect(load(keys.lens, 2)).toBe(2);
     expect(() => save(keys.lens, 4)).not.toThrow();
     vi.stubGlobal("window", { localStorage: { getItem: () => "{not json", setItem: () => {} } });
-    expect(load(keys.aboutW, 360)).toBe(360);
+    expect(load(keys.detailW, 360)).toBe(360);
   });
 });
 
@@ -27,8 +27,8 @@ describe("typed prefs", () => {
 
   it("accept only well-formed values", async () => {
     const { loadLens, loadMovedAll, loadWidth } = await import("./prefs");
-    stub({ "ct.lens": "4", "ct.board.1.moved": '{"N1": 40, "N2": -3.5}', "ct.panel.aboutW": "420" });
-    expect([loadLens(), loadMovedAll(1), loadWidth(keys.aboutW, 360)])
+    stub({ "ct.lens": "4", "ct.board.1.moved": '{"N1": 40, "N2": -3.5}', "ct.ws.detailW": "420" });
+    expect([loadLens(), loadMovedAll(1), loadWidth(keys.detailW, 360)])
       .toEqual([4, { layers: { N1: { x: 40 }, N2: { x: -3.5 } }, depth: {} }, 420]);
   });
 
@@ -36,8 +36,8 @@ describe("typed prefs", () => {
     const { loadLens, loadMovedAll, loadWidth } = await import("./prefs");
     for (const [lens, moved, width] of [["3", "null", "null"], ['"2"', "[1,2]", '"wide"'], ["null", '{"N1": "x"}', "-5"],
                                         ["2.5", '{"N1": null}', "1e9"]]) {
-      stub({ "ct.lens": lens, "ct.board.1.moved": moved, "ct.panel.aboutW": width });
-      expect([loadLens(), loadMovedAll(1), loadWidth(keys.aboutW, 360)]).toEqual([2, { layers: {}, depth: {} }, 360]);
+      stub({ "ct.lens": lens, "ct.board.1.moved": moved, "ct.ws.detailW": width });
+      expect([loadLens(), loadMovedAll(1), loadWidth(keys.detailW, 360)]).toEqual([2, { layers: {}, depth: {} }, 360]);
     }
   });
 });
@@ -59,30 +59,3 @@ describe("layout prefs", () => {
     expect(loadLayout(1)).toBeNull();
   });
 });
-
-describe("panel prefs", () => {
-  const stub = (values: Record<string, string>) =>
-    vi.stubGlobal("window", { innerWidth: 1400, localStorage: { getItem: (k: string) => values[k] ?? null, setItem: () => {} } });
-
-  it("remember whether the change panel is open, and the flow bar height", async () => {
-    const { loadAboutOpen, loadSize } = await import("./prefs");
-    stub({ "ct.panel.about": "false", "ct.panel.flowH": "180" });
-    expect(loadAboutOpen()).toBe(false);
-    expect(loadSize(keys.flowH, 40, 4000)).toBe(180);
-    stub({ "ct.panel.about": '"yes"', "ct.panel.flowH": "12" });
-    expect(loadAboutOpen()).toBeNull();
-    expect(loadSize(keys.flowH, 40, 4000)).toBeNull();
-    stub({});
-    expect(loadAboutOpen()).toBeNull();
-    expect(loadSize(keys.flowH, 40, 4000)).toBeNull();
-  });
-});
-
-describe("phone tab pref", () => {
-  it("remembers the tab per review and ignores junk", async () => {
-    const { loadTab } = await import("./prefs");
-    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => (k === "ct.board.3.tab" ? '"map"' : '"other"'), setItem: () => {} } });
-    expect(loadTab(3)).toBe("map");
-    expect(loadTab(4)).toBeNull();
-  });
-});
```

`frontend/src/stories/stories.test.ts`:

```diff
diff --git a/frontend/src/stories/stories.test.ts b/frontend/src/stories/stories.test.ts
index 4f1f35b..7ddedde 100644
--- a/frontend/src/stories/stories.test.ts
+++ b/frontend/src/stories/stories.test.ts
@@ -1,6 +1,6 @@
 import { describe, expect, it } from "vitest";
-import type { Board, BoardNode, Story, StorySet, StorySite } from "../board/types";
-import { countLine, graphFocus, groupSites, sections, stepStory, wholeGraph } from "./stories";
+import type { Story, StorySet, StorySite } from "../board/types";
+import { countLine, groupSites, sections, stepStory } from "./stories";
 
 const story = (id: string, kind: Story["kind"], extra: Partial<Story> = {}): Story => ({
   id, kind, title: id, summary: "", text_source: "template", risk: null, counts: {}, nodes: [], flows: [], findings: [],
@@ -41,19 +41,4 @@ describe("stories", () => {
     expect(g[0].files.map((f) => [f.name, f.sites.map((s) => s.line)])).toEqual([["a.c", [1]], ["b.c", [3, 9]]]);
     expect(groupSites(sites, true).map((d) => d.dir)).toEqual(["//d/src"]);
   });
-
-  it("opens the whole graph on the board holding the story's first node", () => {
-    expect(wholeGraph(3, story("S1", "behaviour", { nodes: ["N9"] }))).toBe("/r/3/board?node=N9");
-    expect(wholeGraph(3, story("S1", "behaviour", { nodes: ["N9"], board: "C2" }))).toBe("/r/3/c/C2?node=N9");
-    expect(wholeGraph(3, story("S1", "behaviour"), "N4")).toBe("/r/3/board?node=N4");     // a repeated edit's flows
-    expect(wholeGraph(3, story("S1", "behaviour", { nodes: ["N9"] }), "N4")).toBe("/r/3/board?node=N9");
-  });
-  it("focuses a field folded into a struct on its struct node", () => {
-    const n = (id: string, fields?: { id: string; label: string }[]) => ({ id, fields }) as BoardNode;
-    const g = { nodes: [n("N1"), n("N2", [{ id: "N2", label: "a" }, { id: "N3", label: "b" }])] } as Board;
-    expect(graphFocus(g, "N3")).toBe("N2");
-    expect(graphFocus(g, "N1")).toBe("N1");
-    expect(graphFocus(g, "N9")).toBe("N9");
-    expect(graphFocus(g, null)).toBeNull();
-  });
 });
```

`frontend/src/workspace/legacy.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { legacy } from "./legacy";

const q = (s: string) => new URLSearchParams(s);
const ctx = { base: "/r/7", nodeStory: { N9: "S1" } as Record<string, string>, oneBoard: true };

describe("old addresses", () => {
  it("send the old tabs to their places", () => {
    expect(legacy("/board", q(""), ctx)).toEqual({ to: "/r/7?view=graph" });
    expect(legacy("/board", q(""), { ...ctx, oneBoard: false })).toEqual({ to: "/r/7#map" });
    expect(legacy("/overview", q(""), ctx)).toEqual({ to: "/r/7#map" });
    expect(legacy("/findings", q(""), ctx)).toEqual({ to: "/r/7#findings" });
    expect(legacy("/cls", q(""), ctx)).toEqual({ to: "/r/7#changeset" });
    expect(legacy("/files", q(""), ctx)).toEqual({ to: "/r/7#files" });
  });

  it("open the item holding ?node=, with the node open", () => {
    expect(legacy("", q("node=N9"), ctx)).toEqual({ to: "/r/7/s/S1?open=N9" });
    expect(legacy("/board", q("node=N9"), ctx)).toEqual({ to: "/r/7/s/S1?open=N9" });
    expect(legacy("/c/C2", q("node=N4&x=N4:callers"), ctx)).toEqual({ to: "/r/7/c/C2?open=N4" });
    expect(legacy("", q("node=N4"), ctx)).toEqual({ to: "/r/7?view=graph&open=N4" });
    expect(legacy("", q("node=N4"), { ...ctx, oneBoard: false })).toEqual({ locate: "N4" });
  });

  it("rename the old story tab and cluster file parameters", () => {
    expect(legacy("/s/S1", q("tab=graph"), ctx)).toEqual({ to: "/r/7/s/S1?view=graph" });
    expect(legacy("/c/C1", q("file=//d/a.c"), ctx)).toEqual({ to: "/r/7/c/C1?open=file%3A%2F%2Fd%2Fa.c" });
  });

  it("leave current addresses alone", () => {
    expect(legacy("/s/S1", q("view=graph&open=N9&tab=neighbours"), ctx)).toBeNull();
    expect(legacy("", q(""), ctx)).toBeNull();
  });
});
```

Delete the old specs:

```bash
git rm frontend/e2e/board.spec.ts
git rm frontend/e2e/large.spec.ts
git rm frontend/e2e/panel-diff.spec.ts
git rm frontend/e2e/phone.spec.ts
git rm frontend/e2e/smoke.spec.ts
git rm frontend/e2e/stories.spec.ts
git rm frontend/src/board/reducer.test.ts
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: FAIL — `Test Files  2 failed | 28 passed (30)` and `Tests  1 failed | 111 passed (112)` and `Cannot find module './legacy' imported from src/workspace/legacy.test.ts` and `expected [ 4, …(2) ] to deeply equal [ 4, …(2) ]`

- [ ] **Step 3: Implement**

`frontend/src/App.tsx`:

```diff
diff --git a/frontend/src/App.tsx b/frontend/src/App.tsx
index 97f9b0a..9e5cc4e 100644
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -1,15 +1,20 @@
 import { createContext, useContext, useEffect, useState } from "react";
-import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
+import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
 import { api, type Me } from "./api";
 import InsecureBanner from "./components/InsecureBanner";
 import Logo from "./components/Logo";
 import ThemeSwitch from "./components/ThemeSwitch";
 import Health from "./pages/Health";
 import Login from "./pages/Login";
-import Review from "./pages/Review";
 import Reviews from "./pages/Reviews";
 import Workspace from "./workspace/Workspace";
 
+/** `/w/` was the workspace's address while it was built; it is `/r/` now. */
+function ToReview() {
+  const { id, "*": rest } = useParams(), { search, hash } = useLocation();
+  return <Navigate to={`/r/${id}${rest ? `/${rest}` : ""}${search}${hash}`} replace />;
+}
+
 const MeContext = createContext<Me | null>(null);
 export const useMe = () => useContext(MeContext);
 
@@ -53,8 +58,8 @@ export default function App() {
         <Route path="/" element={<Reviews />} />
         <Route path="/new" element={<Navigate to="/" replace />} />
         <Route path="/health" element={<Health />} />
-        <Route path="/r/:id/*" element={<Review />} />
-        <Route path="/w/:id/*" element={<Workspace />} />
+        <Route path="/r/:id/*" element={<Workspace />} />
+        <Route path="/w/:id/*" element={<ToReview />} />
         <Route path="*" element={<Navigate to="/" replace />} />
       </Routes>
     </MeContext.Provider>
```

`frontend/src/board/layout.ts`:

```diff
diff --git a/frontend/src/board/layout.ts b/frontend/src/board/layout.ts
index 1130b65..8ff1ab0 100644
--- a/frontend/src/board/layout.ts
+++ b/frontend/src/board/layout.ts
@@ -1,7 +1,7 @@
 /** World geometry helpers for the board (pure). Two layouts: `layers` (bands by architectural layer, x from the
  * backend's barycentre ordering) and `depth` (rows by call depth from the entry points, ordered here). The viewer may
  * move any node anywhere; moves are kept per layout. */
-import { BAND, type Projected } from "./lens";
+import { BAND } from "./lens";
 import type { Board, BoardFlow, BoardNode } from "./types";
 
 export type LayoutKind = "layers" | "depth";
@@ -146,34 +146,3 @@ export function flowSets(flow: BoardFlow | undefined, graph: boolean) {
   if (graph || !flow) return { onPath: new Set<string>(), pairs: new Set<string>() };
   return { onPath: new Set(flow.path), pairs: new Set(flow.path.slice(1).map((b, i) => `${flow.path[i]}>${b}`)) };
 }
-
-const NODE_HALF = 100;                             // about half a changed node's width, in screen px at scale 1
-
-export interface Rect { x: number; y: number; w: number; h: number }
-export interface CardBox { id: string; at: Projected; w: number; h: number; collapsed: boolean; offset?: { x: number; y: number } }
-
-/** Screen rectangles for cards (spec §3.4): pills under their node; dragged cards follow their node at the chosen
- * offset; others go right/left/above of the node, then into canvas corners — first free spot, else least overlap. */
-export function placeCards(cards: CardBox[], W: number, H: number): Map<string, Rect & { k: number }> {
-  const placed: Rect[] = [], out = new Map<string, Rect & { k: number }>();
-  const area = (a: Rect, b: Rect) =>
-    Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
-  const overlap = (r: Rect) => placed.reduce((s, q) => s + area(r, q), 0);
-  for (const c of cards) {
-    const p = c.at, k = c.collapsed ? 1 : Math.max(0.55, p.s), cw = c.w * k, ch = Math.min(c.h * k, H - 16);
-    const cx = (x: number) => Math.max(8, Math.min(x, W - cw - 8)), cy = (y: number) => Math.max(8, Math.min(y, H - ch - 8));
-    let r: Rect;
-    if (c.collapsed) r = { x: cx(p.x - cw / 2), y: cy(p.y + 24 * p.s), w: cw, h: ch };
-    else if (c.offset) r = { x: p.x + c.offset.x, y: p.y + c.offset.y, w: cw, h: ch };
-    else {
-      const gap = NODE_HALF * p.s;                 // clear of the node itself, so its ⤢ button stays reachable
-      const cands = [[p.x + gap, p.y - 40], [p.x - gap - cw, p.y - 40], [p.x + gap, p.y - ch + 40],
-        [p.x - gap - cw, p.y - ch + 40], [W - cw - 8, 8], [8, 8], [W - cw - 8, H - ch - 8], [8, H - ch - 8]]
-        .map(([x, y]) => ({ x: cx(x), y: cy(y), w: cw, h: ch }));
-      r = cands.find((t) => overlap(t) === 0) ?? cands.reduce((b, t) => (overlap(t) < overlap(b) ? t : b));
-    }
-    placed.push(r);
-    out.set(c.id, { ...r, k });
-  }
-  return out;
-}
```

`frontend/src/board/overview.ts`:

```diff
diff --git a/frontend/src/board/overview.ts b/frontend/src/board/overview.ts
index f3f659f..baa5eb4 100644
--- a/frontend/src/board/overview.ts
+++ b/frontend/src/board/overview.ts
@@ -25,39 +25,8 @@ export function linkLines(ov: Overview, id: string, max = Infinity): string[] {
   return lines.sort((a, b) => b.w - a.w).slice(0, max).map((l) => l.text);
 }
 
-/** Clusters linked to `id` either way (outlined when it is selected). */
-export function linkedTo(ov: Overview, id: string): Set<string> {
-  return new Set(ov.links.flatMap((l) => (l.src === id ? [l.dst] : l.dst === id ? [l.src] : [])));
-}
-
 /** The previous or next cluster in risk order (‹ ›), wrapping around. */
 export function stepCluster(ov: Overview, id: string, dir: 1 | -1): string {
   const i = ov.clusters.findIndex((c) => c.id === id), n = ov.clusters.length;
   return ov.clusters[((i < 0 ? 0 : i) + dir + n) % n].id;
 }
-
-/** The cluster whose changed code is in this depot file, or null. */
-export function clusterOfFile(ov: Overview, path: string): string | null {
-  return ov.clusters.find((c) => c.files.includes(path))?.id ?? null;
-}
-
-/** The page address's expansions after one more "+N callers / callees": asking again adds the next neighbours. */
-export function addExpansion(list: string[], id: string, way: "callers" | "callees"): string[] {
-  return [...list, `${id}:${way}`];
-}
-
-/** The cluster to open for a file of the change: its own, or (a file with no changed function, such as a header of
- * macros) the one whose code shares the most directory with it, the riskiest on a tie. */
-export function nearestCluster(ov: Overview, path: string): string | null {
-  const own = clusterOfFile(ov, path);
-  if (own || !ov.clusters.length) return own;
-  const dir = (p: string) => p.split("/").slice(0, -1);
-  const shared = (a: string[], b: string[]) => { let i = 0; while (i < a.length && i < b.length && a[i] === b[i]) i++; return i; };
-  const mine = dir(path);
-  let best = ov.clusters[0].id, most = -1;
-  for (const c of ov.clusters) {
-    const n = Math.max(-1, ...c.files.map((f) => shared(mine, dir(f))));
-    if (n > most) { best = c.id; most = n; }
-  }
-  return best;
-}
```

`frontend/src/board/prefs.ts`:

```diff
diff --git a/frontend/src/board/prefs.ts b/frontend/src/board/prefs.ts
index ee20dd5..c010658 100644
--- a/frontend/src/board/prefs.ts
+++ b/frontend/src/board/prefs.ts
@@ -16,21 +16,18 @@ export function save(key: string, value: unknown): void {
   }
 }
 
-/** Whose saved state: a review's board, or one cluster's board in a split review ("12.C3"). */
+/** Whose saved state: a review's graph, a story's ("12.S1") or a cluster's ("12.C3"). */
 export type BoardKey = number | string;
 
 export const keys = {
   moved: (reviewId: BoardKey) => `ct.board.${reviewId}.moved`,
   layout: (reviewId: BoardKey) => `ct.board.${reviewId}.layout`,
-  about: "ct.panel.about",
-  flowH: "ct.panel.flowH",
-  tab: (reviewId: BoardKey) => `ct.board.${reviewId}.tab`,
-  panelTab: (reviewId: BoardKey) => `ct.board.${reviewId}.panelTab`,
-  expand: (reviewId: BoardKey) => `ct.board.${reviewId}.expand`,
   viewerView: "ct.viewer.view",
-  viewerW: "ct.panel.viewerW",
-  aboutW: "ct.panel.aboutW",
   lens: "ct.lens",
+  /** The workspace's rail and detail panel widths and which rail sections are open (review workspace §2.2). */
+  railW: "ct.ws.railW",
+  detailW: "ct.ws.detailW",
+  railOpen: "ct.ws.rail.open",
 };
 
 /* Typed readers: a value of the wrong shape (another app version, an extension, a manual edit) falls back to the
@@ -71,34 +68,7 @@ export function loadWidth(key: string, fallback: number): number {
   return typeof v === "number" && Number.isFinite(v) && v >= 120 && v <= 8000 ? v : fallback;
 }
 
-export function loadAboutOpen(): boolean | null {
-  const v = load<unknown>(keys.about, null);
-  return typeof v === "boolean" ? v : null;
-}
-
-export function loadSize(key: string, min: number, max: number): number | null {
-  const v = load<unknown>(key, null);
-  return typeof v === "number" && Number.isFinite(v) && v >= min && v <= max ? v : null;
-}
-
-export type PhoneTab = "flows" | "map" | "files" | "summary";
-export function loadTab(reviewId: BoardKey): PhoneTab | null {
-  const v = load<unknown>(keys.tab(reviewId), null);
-  return v === "flows" || v === "map" || v === "files" || v === "summary" ? v : null;
-}
-
-export type PanelTab = "summary" | "cls";
-export function loadPanelTab(reviewId: BoardKey): PanelTab {
-  return load<unknown>(keys.panelTab(reviewId), null) === "cls" ? "cls" : "summary";
-}
-
 export type ViewerView = "changes" | "full";
 export function loadViewerView(): ViewerView {
   return load<unknown>(keys.viewerView, null) === "full" ? "full" : "changes";
 }
-
-/** A cluster board's expansions ("N12:callers"), as this reader left them. */
-export function loadExpand(key: BoardKey): string[] {
-  const v = load<unknown>(keys.expand(key), []);
-  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && /^N\d+:(callers|callees)$/.test(x)) : [];
-}
```

`frontend/src/stories/stories.ts`:

```diff
diff --git a/frontend/src/stories/stories.ts b/frontend/src/stories/stories.ts
index 458cdff..dd09e1c 100644
--- a/frontend/src/stories/stories.ts
+++ b/frontend/src/stories/stories.ts
@@ -1,5 +1,5 @@
 /** Change stories (spec 2026-10-04-change-stories §3, §5): the list's sections, ‹ › order and a repeated edit's sites. */
-import type { Board, Story, StorySet, StorySite } from "../board/types";
+import type { Story, StorySet, StorySite } from "../board/types";
 
 export interface Sections {
   behaviour: Story[];
@@ -56,17 +56,3 @@ export function groupSites(sites: StorySite[], hideTests: boolean): SiteDir[] {
 
 /** Sites past which files start closed (a very large repeated edit lists files with a count, spec §6). */
 export const OPEN_SITES = 200;
-
-/** Where "Whole graph ›" goes: the board holding the story's first node, focused on it; a story without code of its
- * own (a repeated edit's flows) focuses on `cause`, its first flow's. */
-export function wholeGraph(reviewId: number, s: Story, cause?: string | null): string {
-  const at = s.nodes[0] ?? cause;
-  const node = at ? `?node=${encodeURIComponent(at)}` : "";
-  return s.board ? `/r/${reviewId}/c/${s.board}${node}` : `/r/${reviewId}/board${node}`;
-}
-
-/** The story graph's node to focus for `?node=`: a field folded into a struct focuses the struct's node. */
-export function graphFocus(graph: Board | null, node: string | null): string | null {
-  if (!node || !graph) return node;
-  return graph.nodes.find((n) => n.fields?.some((f) => f.id === node))?.id ?? node;
-}
```

`frontend/src/workspace/Detail.tsx`:

```diff
diff --git a/frontend/src/workspace/Detail.tsx b/frontend/src/workspace/Detail.tsx
index 5440984..8855d64 100644
--- a/frontend/src/workspace/Detail.tsx
+++ b/frontend/src/workspace/Detail.tsx
@@ -1,6 +1,6 @@
 import { useEffect, useState } from "react";
 import { Link } from "react-router-dom";
-import { load, save } from "../board/prefs";
+import { keys, loadWidth, save } from "../board/prefs";
 import Resizer from "../board/Resizer";
 import type { StoryDetail } from "../board/types";
 import { at } from "./address";
@@ -11,16 +11,11 @@ import FileDiff from "./FileDiff";
 import FunctionCode from "./FunctionCode";
 import Neighbours from "./Neighbours";
 
-const WIDTH_KEY = "ct.ws.detailW";
-
 /** The detail panel (spec 2026-10-04-review-workspace §3.7): a node's code or a file's diff, opened on demand; on a
  * phone a full-screen sheet whose top bar names its item. */
 export default function Detail() {
   const ws = useWs(), d = ws.data, open = ws.addr.open!;
-  const [width, setWidth] = useState(() => {
-    const w = load<unknown>(WIDTH_KEY, 0);
-    return typeof w === "number" && w >= 320 && w <= 4000 ? w : Math.round(window.innerWidth * 0.45);
-  });
+  const [width, setWidth] = useState(() => Math.max(320, loadWidth(keys.detailW, Math.round(window.innerWidth * 0.45))));
   const nid = "node" in open ? open.node : null, name = nid ? d.names[nid] : null;
   const [story, setStory] = useState<StoryDetail | null>(null);
   const [full, setFull] = useState(false);
@@ -55,7 +50,7 @@ export default function Detail() {
   return (
     <aside className="ws-detail" style={{ ["--w" as string]: `${width}px` }} aria-label={`Code: ${label ?? "not found"}`}>
       {ws.screen === "desktop" && <Resizer size={width} edge="left" min={320} max={() => window.innerWidth * 0.75}
-                                           onSize={setWidth} onDone={(w) => save(WIDTH_KEY, w)} />}
+                                           onSize={setWidth} onDone={(w) => save(keys.detailW, w)} />}
       {ws.screen === "phone" && (
         <div className="ws-phonebar">
           <Link to={close} aria-label="Close the code" title="Close the code">‹ {st ? st.id : "Back"}</Link>
```

`frontend/src/workspace/Rail.tsx`:

```diff
diff --git a/frontend/src/workspace/Rail.tsx b/frontend/src/workspace/Rail.tsx
index 6790700..be0ebfc 100644
--- a/frontend/src/workspace/Rail.tsx
+++ b/frontend/src/workspace/Rail.tsx
@@ -1,7 +1,7 @@
 import { type ReactNode, useEffect, useRef, useState } from "react";
 import { Link } from "react-router-dom";
 import type { Story } from "../board/types";
-import { load, save } from "../board/prefs";
+import { keys, load, loadWidth, save } from "../board/prefs";
 import Resizer from "../board/Resizer";
 import { sections } from "../stories/stories";
 import { type Place, samePlace } from "./address";
@@ -11,11 +11,10 @@ import { Ticks } from "./NameText";
 import { bySeverity, litStories, storyCls } from "./rail";
 
 export type Section = "changeset" | "stories" | "findings" | "files";
-const OPEN_KEY = "ct.ws.rail.open", WIDTH_KEY = "ct.ws.railW";
 const scrollKey = (rid: number) => `ct.ws.${rid}.railScroll`;
 
 function loadOpen(): Record<Section, boolean> {
-  const v = load<unknown>(OPEN_KEY, null), all = { changeset: true, stories: true, findings: true, files: false };
+  const v = load<unknown>(keys.railOpen, null), all = { changeset: true, stories: true, findings: true, files: false };
   return v && typeof v === "object" ? { ...all, ...(v as Partial<Record<Section, boolean>>) } : all;
 }
 
@@ -24,11 +23,11 @@ function loadOpen(): Record<Section, boolean> {
 export default function Rail({ show, onPick }: { show: string | null; onPick: () => void }) {
   const ws = useWs(), d = ws.data;
   const [open, setOpen] = useState(loadOpen);
-  const [width, setWidth] = useState(() => { const w = load<unknown>(WIDTH_KEY, 280); return typeof w === "number" && w >= 200 && w <= 600 ? w : 280; });
+  const [width, setWidth] = useState(() => Math.min(600, Math.max(200, loadWidth(keys.railW, 280))));
   const [cl, setCl] = useState<number | null>(null);
   const box = useRef<HTMLElement>(null);
   const refs = useRef(new Map<string, HTMLElement>());
-  const toggle = (s: Section, to = !open[s]) => setOpen((o) => { const n = { ...o, [s]: to }; save(OPEN_KEY, n); return n; });
+  const toggle = (s: Section, to = !open[s]) => setOpen((o) => { const n = { ...o, [s]: to }; save(keys.railOpen, n); return n; });
 
   useEffect(() => {                                        // the rail's scroll position, per review
     const el = box.current, k = scrollKey(d.id);
@@ -74,7 +73,7 @@ export default function Rail({ show, onPick }: { show: string | null; onPick: ()
 
   return (
     <aside className="ws-rail" ref={box} style={{ ["--w" as string]: `${width}px` }} aria-label="Review contents">
-      <Resizer size={width} edge="right" min={200} max={() => 600} onSize={setWidth} onDone={(w) => save(WIDTH_KEY, w)} />
+      <Resizer size={width} edge="right" min={200} max={() => 600} onSize={setWidth} onDone={(w) => save(keys.railW, w)} />
       <Link to={ws.base} state={{ page: true }} className="ws-row ws-home" aria-current={here({ kind: "whole" })}
             title="Go to the whole change" aria-label="Go to the whole change" onClick={onPick}>
         <span aria-hidden>⌂</span> Whole change {d.detail?.review.risk && <span className={`bd-pill ${d.detail.review.risk}`}>{d.detail.review.risk}</span>}
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index af87e76..ddeec7f 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -20,12 +20,13 @@ import ClusterPage from "./ClusterPage";
 import FindingPage from "./FindingPage";
 import Rail from "./Rail";
 import StoryPage from "./StoryPage";
+import { legacy } from "./legacy";
 import { useReview } from "./useReview";
 import WholePage, { ReviewGraph } from "./WholePage";
 import "./workspace.css";
 
-/** Where the workspace lives (spec 2026-10-04-review-workspace §6: `/w/` while it is built, then `/r/`). */
-export const base = (id: number) => `/w/${id}`;
+/** Where the workspace lives (spec 2026-10-04-review-workspace §6). */
+export const base = (id: number) => `/r/${id}`;
 
 /** The review workspace (spec 2026-10-04-review-workspace §2): header, rail, centre and the detail panel on demand. */
 export default function Workspace() {
@@ -56,10 +57,26 @@ export default function Workspace() {
     cls: d?.cls ?? [], clusters: data.overview?.clusters ?? [],
   }), [addr.place, root, d, id, data.stories, data.findings, data.overview]);
   const hash = location.hash.slice(1) || null;
+
+  // an address from before the workspace goes to where that thing lives now (§2.3)
+  const settled = data.ready && data.stories !== undefined && data.board !== undefined;
+  const old = useMemo(() => settled ? legacy(`/${params["*"] ?? ""}`, q, {
+    base: root, nodeStory: data.stories?.node_story ?? {}, oneBoard: !!data.board,
+  }) : null, [settled, params, q, root, data.stories, data.board]);
+  useEffect(() => {
+    if (!old) return;
+    if ("to" in old) { navigate(old.to, { replace: true }); return; }
+    api.locate(id, { node: old.locate }).then(
+      (r) => navigate(r.cluster ? href(root, at({ kind: "cluster", cid: r.cluster }, { open: { node: old.locate } })) : root, { replace: true }),
+      () => navigate(root, { replace: true }));
+  }, [old, id, root, navigate]);
+  useEffect(() => {
+    if (hash === "map" && d) document.getElementById("map")?.scrollIntoView({ block: "start" });
+  }, [hash, d]);
   const level = addr.open ? "detail" : addr.place.kind === "whole" && !addr.place.view && !(location.state as { page?: boolean } | null)?.page ? "rail" : "item";
 
   if (data.error) return <main className="page error">{data.error}</main>;
-  if (!d) return <main className="page muted">Loading…</main>;
+  if (!d || old) return <main className="page muted">Loading…</main>;
   return (
     <AiProvider value={data.ai}>
       <WsContext.Provider value={ws}>
```

`frontend/src/workspace/legacy.ts`:

```ts
/** Addresses from before the workspace (spec 2026-10-04-review-workspace §2.3) and where they go now. */
import { at, href, readAddress } from "./address";

interface Ctx {
  base: string;
  nodeStory: Record<string, string>;
  /** The review is shown as one board (not split into parts). */
  oneBoard: boolean;
}

const TABS: Record<string, string> = { "/overview": "#map", "/findings": "#findings", "/cls": "#changeset", "/files": "#files" };

/** The new address of an old one; `locate` when only the server knows which part holds the node; null when current. */
export function legacy(path: string, q: URLSearchParams, c: Ctx): { to: string } | { locate: string } | null {
  const node = q.get("node");
  if (node) {
    const sid = c.nodeStory[node];
    if (sid) return { to: href(c.base, at({ kind: "story", sid, view: "steps" }, { open: { node } })) };
    const cluster = /^\/c\/([^/]+)$/.exec(path);
    if (cluster) return { to: href(c.base, at({ kind: "cluster", cid: cluster[1] }, { open: { node } })) };
    return c.oneBoard ? { to: href(c.base, at({ kind: "whole", view: "graph" }, { open: { node } })) } : { locate: node };
  }
  if (path === "/board") return { to: c.oneBoard ? href(c.base, at({ kind: "whole", view: "graph" })) : `${c.base}#map` };
  if (TABS[path]) return { to: `${c.base}${TABS[path]}` };
  if (q.get("tab") === "graph" && path.startsWith("/s/")) {
    const a = readAddress(path, q);
    return a.place.kind === "story" ? { to: href(c.base, { ...a, place: { ...a.place, view: "graph" } }) } : null;
  }
  const file = q.get("file");
  if (file || q.has("x")) {
    const a = readAddress(path, q);
    return { to: href(c.base, file ? { ...a, open: { file, line: null } } : a) };
  }
  return null;
}
```

Delete the old UI:

```bash
git rm frontend/src/board/Board.tsx
git rm frontend/src/board/Canvas.tsx
git rm frontend/src/board/CardLayer.tsx
git rm frontend/src/board/ChangePanel.tsx
git rm frontend/src/board/ClusterBoard.tsx
git rm frontend/src/board/FileViewer.tsx
git rm frontend/src/board/FlowBar.tsx
git rm frontend/src/board/OverviewPage.tsx
git rm frontend/src/board/phone/FlowReader.tsx
git rm frontend/src/board/phone/PhoneBoard.tsx
git rm frontend/src/board/phone/PhoneMap.tsx
git rm frontend/src/board/phone/phone.css
git rm frontend/src/board/reducer.ts
git rm frontend/src/components/CiteText.tsx
git rm frontend/src/components/ClsPanel.tsx
git rm frontend/src/components/Findings.tsx
git rm frontend/src/pages/Review.tsx
git rm frontend/src/stories/StoryBodies.tsx
git rm frontend/src/stories/StoryList.tsx
git rm frontend/src/stories/StoryPage.tsx
git rm frontend/src/stories/StorySteps.tsx
git rm frontend/src/stories/stories.css
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  30 passed (30)` and `Tests  116 passed (116)` and `✓ built in …` and `49 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  30 passed (30)` and `Tests  116 passed (116)` and `✓ built in …` and `49 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/ai.spec.ts frontend/e2e/banner.spec.ts frontend/e2e/helpers.ts frontend/e2e/landing.spec.ts frontend/e2e/mention.spec.ts frontend/e2e/theme.spec.ts frontend/e2e/workspace-detail.spec.ts frontend/e2e/workspace-graph.spec.ts frontend/e2e/workspace-legacy.spec.ts frontend/e2e/workspace-pages.spec.ts frontend/e2e/workspace-story.spec.ts frontend/e2e/workspace.spec.ts frontend/src/App.tsx frontend/src/board/layout.test.ts frontend/src/board/layout.ts frontend/src/board/overview.test.ts frontend/src/board/overview.ts frontend/src/board/prefs.test.ts frontend/src/board/prefs.ts frontend/src/stories/stories.test.ts frontend/src/stories/stories.ts frontend/src/workspace/Detail.tsx frontend/src/workspace/Rail.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/legacy.test.ts frontend/src/workspace/legacy.ts
git commit -m "feat(ui): /r/ is the workspace — old addresses redirect; the four tabs, cards, phone board and their specs go"
```

---

### Task 17: Boards and story graphs no longer grow by expand

Spec §4.6. The Neighbours tab lists callers and callees, so the `expand` query parameter of the board and
story endpoints, `expand_board` and its tests, and `analysis.expand_step` go (configs that still set it load, since
unknown keys are ignored). The API client drops its `expand` arguments.

**Files:**
- Modify: `backend/codetortoise/board.py`
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/web/app.py`
- Modify: `frontend/src/api.ts`
- Test: `backend/tests/test_board.py`
- Test: `backend/tests/test_large_change.py`
- Test: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `GET /api/reviews/{rid}/board?cluster=` and `GET /api/reviews/{rid}/stories/{sid}` without `expand`; `api.board(id, cluster?)`, `api.story(id, sid)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_board.py`:

```diff
diff --git a/backend/tests/test_board.py b/backend/tests/test_board.py
index c5d662c..7a6c0b6 100644
--- a/backend/tests/test_board.py
+++ b/backend/tests/test_board.py
@@ -314,19 +314,6 @@ def test_a_split_review_that_fails_to_render_falls_back_to_one_board(monkeypatch
     assert bs.note == "shown as one board (clustering failed: RuntimeError: overview broke)"
 
 
-def test_expanding_treats_changed_test_code_as_a_caller_like_the_board_badge_does():
-    from codetortoise.board import About, Board, BoardNode, expand_board
-    ctx, _ = _synthetic(callers=("test_set", "api"))
-    ctx.impact.changed.append("N4")                       # test_set changed too: it lives on the tests board
-    b = Board(nodes=[BoardNode(id="N1", key="c:@F@set", label="set", layer=1, local="/w/a.c")], about=About(intent="i"))
-    grown = expand_board(b, ctx.impact, [("N1", "callers")], step=10, ranges={}, depot_of={},
-                         layer_name=lambda lv: f"L{lv}", root="/w")
-    assert {"N4", "N5"} <= {n.id for n in grown.nodes}    # the changed test caller is added like any caller
-    same = expand_board(b, ctx.impact, [("N9", "callers")], step=10, ranges={}, depot_of={},
-                        layer_name=lambda lv: f"L{lv}", root="/w")
-    assert next(n for n in same.nodes if n.id == "N1").more_callers == 3      # peek, api and the changed test
-
-
 def test_a_board_requires_the_fields_its_own_changed_code_altered_not_a_visitors():
     from codetortoise.board import Flow, _Ctx, _required
     ctx, _ = _synthetic()
@@ -338,27 +325,3 @@ def test_a_board_requires_the_fields_its_own_changed_code_altered_not_a_visitors
                 effect="e", check="c", cause="N1")
     req = _required(_Ctx(ctx), ["N1"], [flow])
     assert req == ["N1", "N3", "N2"]                      # set, the visitor on its flow, set's own altered field
-
-
-def test_expanding_a_story_graph_keeps_the_edges_to_fields_folded_into_a_struct():
-    from codetortoise.board import About, Board, BoardNode, StructField, expand_board
-    im = ImpactModel(changed=["N1"], nodes={
-        "N1": Node(id="N1", key="c:@F@f", kind="function", label="f", layer=1),
-        "N2": Node(id="N2", key="field:c:@S@R@FI@a", kind="field", label="R::a", layer=1),
-        "N3": Node(id="N3", key="field:c:@S@R@FI@b", kind="field", label="R::b", layer=1),
-        "N4": Node(id="N4", key="c:@F@g", kind="function", label="g", layer=2),
-        "N5": Node(id="N5", key="c:@F@h", kind="function", label="h", layer=1)},
-        edges=[Edge(id="E1", src="N1", dst="N3", kind="writes", status="added"),
-               Edge(id="E2", src="N5", dst="N2", kind="writes", status="unchanged"),
-               Edge(id="E3", src="N4", dst="N1", kind="call", status="unchanged"),
-               Edge(id="E4", src="N4", dst="N3", kind="writes", status="unchanged")])
-    b = Board(nodes=[BoardNode(id="N1", key="c:@F@f", label="f", layer=1),
-                     BoardNode(id="N5", key="c:@F@h", label="h", layer=1),
-                     BoardNode(id="N2", key="field:c:@S@R@FI@a", label="R", kind="struct", layer=1,
-                               fields=[StructField(id="N2", label="a"), StructField(id="N3", label="b")])],
-              about=About(intent="i"))
-    grown = expand_board(b, im, [("N1", "callers")], step=10, ranges={}, depot_of={},
-                         layer_name=lambda lv: f"L{lv}", root="/w")
-    edges = {(e.src, e.dst, e.kind) for e in grown.edges}
-    assert edges == {("N1", "N2", "writes"), ("N5", "N2", "writes"), ("N4", "N1", "call"), ("N4", "N2", "writes")}
-    assert [n.id for n in grown.nodes if n.kind == "field"] == []          # b stays inside R, not a node of its own
```

`backend/tests/test_large_change.py`:

```diff
diff --git a/backend/tests/test_large_change.py b/backend/tests/test_large_change.py
index 6ddc802..d1f5172 100644
--- a/backend/tests/test_large_change.py
+++ b/backend/tests/test_large_change.py
@@ -106,26 +106,15 @@ def test_the_small_fixture_has_no_overview(fx, tmp_path):
     assert client.get(f"/api/reviews/{rid}/locate", params={"node": "N1"}).json()["cluster"] is None
 
 
-def test_expanding_adds_callers_past_the_budget_and_counts_what_is_left(api):
+def test_a_board_no_longer_grows_by_expand_the_neighbours_tab_lists_them_instead(api):
     svc, owner, rid = api
     ov = owner.get(f"/api/reviews/{rid}/overview").json()
     boards = {c["id"]: owner.get(f"/api/reviews/{rid}/board", params={"cluster": c["id"]}).json() for c in ov["clusters"]}
     cid, node = next((cid, n) for cid, b in boards.items() for n in b["nodes"] if n["more_callers"] > 0)
-    before = boards[cid]
-    after = owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": f"{node['id']}:callers"}).json()
-    added = len(after["nodes"]) - len(before["nodes"])
-    assert added == min(node["more_callers"], svc.cfg.analysis.expand_step) and added > 0
-    grown = next(n for n in after["nodes"] if n["id"] == node["id"])
-    assert grown["more_callers"] == node["more_callers"] - added
-    new = [n for n in after["nodes"] if n["id"] not in {m["id"] for m in before["nodes"]}]
-    assert all(any(e["src"] == n["id"] and e["dst"] == node["id"] for e in after["edges"]) for n in new)
-    bad = owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": "N1:sideways"})
-    assert bad.status_code == 400
-    twice = ",".join([f"{node['id']}:callers"] * 2)                                    # asking again adds the next ones
-    again = owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": twice}).json()
-    assert len(again["nodes"]) - len(before["nodes"]) == min(node["more_callers"], 2 * svc.cfg.analysis.expand_step)
-    many = owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": ",".join([f"{node['id']}:callers"] * 51)})
-    assert many.status_code == 400 and "Reset" in many.json()["detail"]                 # never dropped silently
+    asked = owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": f"{node['id']}:callers"})
+    assert asked.status_code == 200 and asked.json() == boards[cid]
+    assert owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": "N1:sideways"}).status_code == 200
+    assert not hasattr(svc.cfg.analysis, "expand_step")
 
 
 def test_locate_finds_the_cluster_of_a_node_a_flow_and_a_finding(api):
```

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index 92cd9c2..d1305d5 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -302,8 +302,8 @@ def test_story_endpoints_serve_the_list_and_each_story(env):
     assert len(s1["graph"]["nodes"]) <= 12 and s1["board"]["flows"]
     assert all(n["path"] is None or n["path"].startswith("//") for n in s1["graph"]["nodes"])
     send = next(n["id"] for n in s1["graph"]["nodes"] if n["label"] == "uart_send")
-    grown = owner.get(f"/api/reviews/{rid}/stories/S1", params={"expand": f"{send}:callers"}).json()
-    assert len(grown["graph"]["nodes"]) >= len(s1["graph"]["nodes"])
+    asked = owner.get(f"/api/reviews/{rid}/stories/S1", params={"expand": f"{send}:callers"}).json()
+    assert asked["graph"] == s1["graph"]                                   # graphs no longer grow by `expand`
     r = owner.get(f"/api/reviews/{rid}/stories/S9")
     assert r.status_code == 404 and r.json()["detail"] == "That story no longer exists after the re-run."
     svc.store.replace_blobs(rid, ["stories"], [boardstore.STORY], {})     # a review run before stories
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_large_change.py tests/test_web.py tests/test_board.py -q`

Expected: FAIL — `2 failed, 68 passed` and `AssertionError: assert (200 == 200 and {'nodes': [{'....}, ...], ...} == {'...` and `AssertionError: assert {'nodes': [{'....}, ...], ...} == {'nodes': [{'....}...`

- [ ] **Step 3: Implement**

`backend/codetortoise/board.py`:

```diff
diff --git a/backend/codetortoise/board.py b/backend/codetortoise/board.py
index 1432b53..c0cab5f 100644
--- a/backend/codetortoise/board.py
+++ b/backend/codetortoise/board.py
@@ -876,59 +876,6 @@ def _overview(x: _Ctx, res, about: About, depots: dict[str, str], flows: list[Fl
                     merged_over_limit=res.merged_over_limit)
 
 
-def expand_board(b: Board, im: ImpactModel, asks: list[tuple[str, str]], *, step: int,
-                 ranges: dict[str, list[int]], depot_of: dict[str, Files], layer_name: Callable[[int], str],
-                 root: str, home: dict[str, str] | None = None) -> Board:
-    """`b` with up to `step` more callers or callees of each asked node ("+N callers"), most affected first, laid out
-    again. Asks are applied in order, so a node added by one can be expanded by the next. The board may pass its
-    node budget: the reader asked for it."""
-    out = b.model_copy(deep=True)
-    on = {n.id for n in out.nodes}
-    changed = set(im.changed)
-
-    def is_test(nid: str) -> bool:
-        return unchanged_test(im, root, nid, changed)
-    score = {x.node: x.score for x in im.blast}
-    callers: dict[str, set[str]] = defaultdict(set)
-    callees: dict[str, set[str]] = defaultdict(set)
-    for e in im.edges:
-        if e.kind in ("call", "virtual"):
-            callers[e.dst].add(e.src)
-            callees[e.src].add(e.dst)
-    for nid, way in asks:
-        if nid not in on:
-            continue
-        cands = [n for n in (callers if way == "callers" else callees)[nid] - on if n in im.nodes and not is_test(n)]
-        for n in sorted(cands, key=lambda n: (-score.get(n, 0.0), int(n[1:]) if n[1:].isdigit() else 0))[:step]:
-            node = im.nodes[n]
-            h = (home or {}).get(n)
-            files = depot_of.get(n) or []
-            out.nodes.append(BoardNode(id=n, key=node.key, label=node.label, kind=node.kind,
-                                       layer=node.layer if node.layer is not None else -1,
-                                       path=files[0] if node.file and files else None, local=node.file,
-                                       range=ranges.get(node.key), home=h if out.cluster and h and h != out.cluster.id
-                                       else None))
-            on.add(n)
-    to = {f.id: n.id for n in out.nodes for f in n.fields}         # a story graph's folded field -> its struct node
-    out.edges, seen = [], set()
-    for e in im.edges:
-        src, dst = to.get(e.src, e.src), to.get(e.dst, e.dst)
-        if src in on and dst in on and src != dst and (src, dst, e.kind) not in seen:
-            seen.add((src, dst, e.kind))
-            out.edges.append(BoardEdge(src=src, dst=dst, kind=e.kind, status=e.status, confidence=e.confidence))
-    xs = barycentre_layout({n.id: n.layer if n.layer is not None else -1 for n in out.nodes},
-                           [(e.src, e.dst) for e in out.edges])
-    for n in out.nodes:
-        n.x = xs.get(n.id, n.x)
-        n.more_callers = len({s_ for s_ in callers.get(n.id, ()) if s_ not in on and not is_test(s_)})
-        n.more_callees = len({d for d in callees.get(n.id, ()) if d not in on and not is_test(d)})
-    have = {lv.level for lv in out.layers}
-    for lv in sorted({n.layer for n in out.nodes if n.layer is not None} - have):
-        out.layers.append(BoardLayer(level=lv, name=layer_name(lv) if lv >= 0 else "other"))
-    out.layers.sort(key=lambda lv: -lv.level)
-    return out
-
-
 def _tree_prefix(depots: list[str]) -> str:
     """Prefix stripped from the change tree: everything above the deepest directory the files share, so that
     directory itself stays visible (a change inside one directory shows that directory, not ".")."""
```

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index 3194bf7..ed021f7 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -93,7 +93,6 @@ class AnalysisConfig(BaseModel):
     board_blast_nodes: int = 60    # accepted and ignored (neighbours fill a board's budget)
     cluster_min_changed: int = 3   # clusters with fewer changed functions merge with one in the same directory
     overview_max_clusters: int = 60  # more clusters than this: the smallest merge further
-    expand_step: int = 10          # "+N callers / callees": neighbours added per expansion
     max_stories: int = 15          # entries on a review's story list (spec 2026-10-04 §2.4)
     story_graph_nodes: int = 12    # nodes a story's graph shows before the reader expands it
     entrypoint_patterns: list[str] = Field(
```

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index 69644d8..01f5474 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -11,8 +11,6 @@ from fastapi.responses import FileResponse, StreamingResponse
 from pydantic import BaseModel, Field
 
 from codetortoise import boardstore
-from codetortoise.board import Board, expand_board
-from codetortoise.facts.model import Facts
 from codetortoise.health import run_health
 from codetortoise.impact import ImpactModel
 from codetortoise.llm import ondemand, tortoise
@@ -206,7 +204,7 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         return out
 
     @app.get("/api/reviews/{rid}/board")
-    def board(rid: int, cluster: str | None = None, expand: str | None = None, _: str = Depends(user_of)):
+    def board(rid: int, cluster: str | None = None, _: str = Depends(user_of)):
         review_or_404(rid)
         b = boardstore.board(store, rid, cluster)
         if b is None:
@@ -218,8 +216,6 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         # boards stored by an older version get current defaults and file tags (spec §14.3)
         tags = {f.id: f.files for f in store.list_findings(rid)}
         b = tag_board(b, tags)
-        if expand:
-            b = tag_board(expanded(rid, b, expand), tags)
         out = b.model_dump()
         named(out.get("layers", []))
         return out
@@ -236,8 +232,8 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         return ss.model_dump()
 
     @app.get("/api/reviews/{rid}/stories/{sid}")
-    def story(rid: int, sid: str, expand: str | None = None, _: str = Depends(user_of)):
-        """One story: its board (every node it mentions) and its graph, grown by `expand` as boards are."""
+    def story(rid: int, sid: str, _: str = Depends(user_of)):
+        """One story: its board (every node it mentions) and its graph."""
         review_or_404(rid)
         d = boardstore.story(store, rid, sid)
         if d is None:
@@ -248,42 +244,12 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         d.board = tag_board(d.board, tags)
         if d.graph is not None:
             d.graph = tag_board(d.graph, tags)
-            if expand:
-                d.graph = tag_board(expanded(rid, d.graph, expand), tags)
         out = d.model_dump()
         named(out["board"].get("layers", []))
         if out["graph"]:
             named(out["graph"].get("layers", []))
         return out
 
-    def expanded(rid: int, b: Board, expand: str) -> Board:
-        """`expand` is "N12:callers,N9:callees": up to `analysis.expand_step` neighbours each, in order."""
-        parts = expand.split(",")
-        if len(parts) > 50:
-            raise HTTPException(400, f"{len(parts)} expansions is too many (50 at most): press Reset and start again")
-        asks = []
-        for part in parts:
-            nid, _, way = part.strip().partition(":")
-            if way not in ("callers", "callees") or not nid:
-                raise HTTPException(400, f"bad expansion {part!r}: use <node>:callers or <node>:callees")
-            asks.append((nid, way))
-        im = ImpactModel.model_validate(store.get_blob(rid, "impact") or {})
-        ranges: dict[str, list[int]] = {}
-        for fx in store.get_blob(rid, "facts_after") or []:
-            facts = Facts.model_validate(fx)
-            ranges.update({f.usr: [f.start_line, f.end_line] for f in facts.functions})
-            ranges.update({f"field:{a.field}": [a.decl_line, a.decl_line] for a in facts.fields if a.decl_line})
-        lm = svc.layers.get()
-        root = canon(str(cfg.workspace.root)).rstrip("/") + "/"
-
-        def layer_name(lv: int) -> str:
-            layer = lm.layer(lv) if lm else None
-            return layer.name.split(": ", 1)[-1] if layer else f"L{lv}"
-
-        return expand_board(b, im, asks, step=cfg.analysis.expand_step, ranges=ranges,
-                            depot_of=store.get_blob(rid, "node_files") or {}, layer_name=layer_name, root=root,
-                            home=store.get_blob(rid, "node_cluster") or {})
-
     @app.get("/api/reviews/{rid}/locate")
     def locate(rid: int, node: str | None = None, flow: str | None = None, finding: str | None = None,
                _: str = Depends(user_of)):
```

`frontend/src/api.ts`:

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index bb12e0e..830f7b0 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -81,16 +81,11 @@ export const api = {
   createReview: (cls: number[], title?: string) => call<ReviewRow>("POST", "/api/reviews", { cls, title }),
   review: (id: number) => call<ReviewDetail>("GET", `/api/reviews/${id}`),
   rerun: (id: number) => call("POST", `/api/reviews/${id}/rerun`),
-  board: (id: number, cluster?: string | null, expand?: string[]) => {
-    const q = new URLSearchParams();
-    if (cluster) q.set("cluster", cluster);
-    if (expand?.length) q.set("expand", expand.join(","));
-    return call<Board>("GET", `/api/reviews/${id}/board${q.size ? `?${q}` : ""}`);
-  },
+  board: (id: number, cluster?: string | null) =>
+    call<Board>("GET", `/api/reviews/${id}/board${cluster ? `?${new URLSearchParams({ cluster })}` : ""}`),
   overview: (id: number) => call<Overview>("GET", `/api/reviews/${id}/overview`),
   stories: (id: number) => call<StorySet>("GET", `/api/reviews/${id}/stories`),
-  story: (id: number, sid: string, expand?: string[]) =>
-    call<StoryDetail>("GET", `/api/reviews/${id}/stories/${sid}${expand?.length ? `?${new URLSearchParams({ expand: expand.join(",") })}` : ""}`),
+  story: (id: number, sid: string) => call<StoryDetail>("GET", `/api/reviews/${id}/stories/${sid}`),
   locate: (id: number, q: { node?: string; flow?: string; finding?: string }) =>
     call<{ cluster: string | null; story?: string | null }>("GET", `/api/reviews/${id}/locate?${new URLSearchParams(q)}`),
   source: (id: number, path: string, side: "before" | "after" = "after") =>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_large_change.py tests/test_web.py tests/test_board.py -q`

Expected: `70 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Run: `cd frontend && npx vitest run && npm run build`

Expected: `All checks passed!` and `439 passed, 1 skipped`; `Test Files  30 passed (30)` and `Tests  116 passed (116)` and `✓ built in …`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/board.py backend/codetortoise/config.py backend/codetortoise/web/app.py backend/tests/test_board.py backend/tests/test_large_change.py backend/tests/test_web.py frontend/src/api.ts
git commit -m "refactor: boards and story graphs no longer grow by expand — the Neighbours tab lists callers and callees instead"
```

---

### Task 18: One workspace.css

Spec §5. `board.css` folds into `workspace.css`, first, so ties resolve as before; rules whose classes nothing
renders go from both it and `styles.css`. The board's role tokens move from `.bd` (which wrapped only the graph) to
`:root`, dark values under `:root[data-theme="dark"]`, so code and diffs in the detail panel get their colours; the
board's `--info`, `--ok` and `--warn` become `--bd-info`, `--bd-ok` and `--bd-warn`. `GraphView` drops the `bd`
wrapper class. The head's ghost pill and stage notes get colours for the light head (they were tuned for the old dark
board header). The contrast helper moves to `helpers.ts` so the AI spec can check the pill.

**Files:**
- Delete: `frontend/src/board/board.css`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/graph/GraphView.tsx`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/ai.spec.ts`
- Test: `frontend/e2e/helpers.ts`
- Test: `frontend/e2e/theme.spec.ts`
- Test: `frontend/e2e/workspace-detail.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `frontend/src/workspace/workspace.css` as the review's only sheet (with `styles.css` for the app); e2e `contrast(page, selector): Promise<number>` in `helpers.ts`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/ai.spec.ts`:

```diff
diff --git a/frontend/e2e/ai.spec.ts b/frontend/e2e/ai.spec.ts
index 7d099f4..6ee5801 100644
--- a/frontend/e2e/ai.spec.ts
+++ b/frontend/e2e/ai.spec.ts
@@ -1,5 +1,5 @@
 import { expect, test } from "@playwright/test";
-import { login, startReview } from "./helpers";
+import { contrast, login, startReview } from "./helpers";
 
 const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py
 
@@ -59,6 +59,7 @@ test.describe("with an AI", () => {
   test("the owner raises the budget from the AI pill; a reviewer sees the usage without the control", async ({ page, browser }) => {
     await startReview(page);
     const pill = page.getByRole("button", { name: /^AI \d+\/200$/ });
+    expect(await contrast(page, ".ws-head .ai-pill")).toBeGreaterThanOrEqual(4.5);   // readable on the light head
     await pill.click();
     const usage = page.getByRole("dialog", { name: "AI usage" });
     await expect(usage).toContainText("By purpose: finding 1 · flow 1 · summary 1");
```

`frontend/e2e/helpers.ts`:

```diff
diff --git a/frontend/e2e/helpers.ts b/frontend/e2e/helpers.ts
index d3f0a0e..c72a77e 100644
--- a/frontend/e2e/helpers.ts
+++ b/frontend/e2e/helpers.ts
@@ -43,3 +43,23 @@ export async function flowStripHolds(page: Page) {
     expect((await next.boundingBox())!.x).toBe(at);
   }
 }
+
+/** WCAG contrast ratio between an element's text colour and the first opaque background behind it. */
+export async function contrast(page: Page, selector: string) {
+  return page.locator(selector).first().evaluate((el) => {
+    // rgb(0-255…) or, for color-mix() backgrounds, color(srgb 0-1…)
+    const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).map(Number).map((v, i) => c.startsWith("color(") && i < 3 ? v * 255 : v);
+    const lum = ([r, g, b]: number[]) => {
+      const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
+      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
+    };
+    let bgEl: Element | null = el, bg = "";
+    while (bgEl) {
+      const c = getComputedStyle(bgEl).backgroundColor, a = rgb(c)[3];
+      if (c && c !== "transparent" && (a === undefined || a > 0.9)) { bg = c; break; }
+      bgEl = bgEl.parentElement;
+    }
+    const fg = lum(rgb(getComputedStyle(el).color)), b = lum(rgb(bg || "rgb(255,255,255)"));
+    return (Math.max(fg, b) + 0.05) / (Math.min(fg, b) + 0.05);
+  });
+}
```

`frontend/e2e/theme.spec.ts`:

```diff
diff --git a/frontend/e2e/theme.spec.ts b/frontend/e2e/theme.spec.ts
index 72cab82..af4c202 100644
--- a/frontend/e2e/theme.spec.ts
+++ b/frontend/e2e/theme.spec.ts
@@ -1,28 +1,8 @@
 import { expect, type Page, test } from "@playwright/test";
-import { startReview } from "./helpers";
+import { contrast, startReview } from "./helpers";
 
 test.use({ viewport: { width: 1440, height: 900 } });
 
-/** WCAG contrast ratio between an element's text colour and the first opaque background behind it. */
-async function contrast(page: Page, selector: string) {
-  return page.locator(selector).first().evaluate((el) => {
-    // rgb(0-255…) or, for color-mix() backgrounds, color(srgb 0-1…)
-    const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).map(Number).map((v, i) => c.startsWith("color(") && i < 3 ? v * 255 : v);
-    const lum = ([r, g, b]: number[]) => {
-      const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
-      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
-    };
-    let bgEl: Element | null = el, bg = "";
-    while (bgEl) {
-      const c = getComputedStyle(bgEl).backgroundColor, a = rgb(c)[3];
-      if (c && c !== "transparent" && (a === undefined || a > 0.9)) { bg = c; break; }
-      bgEl = bgEl.parentElement;
-    }
-    const fg = lum(rgb(getComputedStyle(el).color)), b = lum(rgb(bg || "rgb(255,255,255)"));
-    return (Math.max(fg, b) + 0.05) / (Math.min(fg, b) + 0.05);
-  });
-}
-
 /** A changed function of story S1 (its first step), to open in the detail panel. */
 async function firstChanged(page: Page) {
   const id = page.url().match(/\/r\/(\d+)/)![1];
```

`frontend/e2e/workspace-detail.spec.ts`:

```diff
diff --git a/frontend/e2e/workspace-detail.spec.ts b/frontend/e2e/workspace-detail.spec.ts
index 7832ff0..4a77926 100644
--- a/frontend/e2e/workspace-detail.spec.ts
+++ b/frontend/e2e/workspace-detail.spec.ts
@@ -39,6 +39,18 @@ test.describe("desktop", () => {
     await expectNoNodeIds(page);
   });
 
+  test("the diff colours added lines, highlights code and fills annotations, outside any graph", async ({ page }) => {
+    await startReview(page);
+    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    const file = page.getByRole("complementary", { name: "Code: uart.c" });
+    const css = (sel: string, prop: string) => file.locator(sel).first().evaluate((e, p) => getComputedStyle(e).getPropertyValue(p), prop);
+    const clear = "rgba(0, 0, 0, 0)";
+    expect(await css(".bd-ln.a", "background-color")).not.toBe(clear);
+    expect(await css(".bd-ann", "background-color")).not.toBe(clear);
+    expect(await css(".hl-kw", "color")).not.toBe(await css(".bd-ln", "color"));
+  });
+
   test("a line comment in a file's diff shows in that function's code", async ({ page }) => {
     const base = await startReview(page);
     await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-detail.spec.ts e2e/ai.spec.ts e2e/theme.spec.ts`

Expected: FAIL — `✓ built in …` and `2 failed` and `16 passed` and (2 failing, first: with an AI › the owner raises the budget from the AI pill; a reviewer sees the usage without the control)

- [ ] **Step 3: Implement**

`frontend/src/styles.css`:

```diff
diff --git a/frontend/src/styles.css b/frontend/src/styles.css
index e00d21a..b5bf6d4 100644
--- a/frontend/src/styles.css
+++ b/frontend/src/styles.css
@@ -20,7 +20,6 @@ body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 var(-
 #root > .insecure { flex: none; padding: 5px 16px; background: #f5b83d; color: #2b1a00; font: 600 12.5px/1.4 var(--sans);
   text-align: center; }
 .review { display: flex; flex-direction: column; overflow: hidden !important; }
-.review-body { flex: 1; min-height: 0; overflow: auto; padding: 16px 24px; }
 .review.board { overflow: hidden; }
 a, .link { color: var(--accent); }
 button { font: inherit; cursor: pointer; border: 1px solid var(--line); background: var(--surface); color: var(--ink);
@@ -45,7 +44,7 @@ h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: v
 .brand + .theme-switch { margin-left: auto; }          /* logged out: no nav between them */
 .menu-btn { display: none; margin-left: auto; font-size: 18px; line-height: 1; padding: 4px 10px; }
 .page { padding: 24px; max-width: 1200px; margin: 0 auto; }
-.page.narrow { max-width: 480px; } .page.wide { max-width: none; }
+.page.wide { max-width: none; }
 .stack { display: flex; flex-direction: column; gap: 12px; } .stack label { display: flex; flex-direction: column; gap: 4px; }
 .row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
 .card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 14px 18px; margin: 12px 0;
@@ -57,36 +56,26 @@ h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: v
   border: 1px solid currentColor; color: var(--info); text-transform: lowercase; }
 .badge.ok { color: var(--ok); } .badge.degraded, .badge.running, .badge.queued { color: var(--warn); } .badge.failed { color: var(--bad); }
 .badge.risk-high, .badge.sev-high { color: var(--bad); } .badge.risk-medium, .badge.sev-medium { color: var(--warn); }
-.badge.risk-low, .badge.sev-low { color: var(--ok); } .badge.via-data { color: #9b6a2f; }
+.badge.risk-low, .badge.sev-low { color: var(--ok); }
 .banner { border-radius: 8px; padding: 8px 12px; margin: 8px 0; background: var(--gap-bg); }
 .banner.warn { border-left: 4px solid var(--warn); } .banner.error { border-left: 4px solid var(--bad); }
-.review-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
-.review-head h1 { margin: 0; }
 .stages { display: flex; gap: 14px; list-style: none; padding: 0; margin: 12px 0; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
 .stage .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--line); margin-right: 5px; }
 .stage.ok .dot { background: var(--ok); } .stage.degraded .dot { background: var(--warn); } .stage.failed .dot { background: var(--bad); }
 .stage.running .dot { background: var(--accent); animation: pulse 1s infinite alternate; } .stage.skipped { text-decoration: line-through; }
 @keyframes pulse { from { opacity: .3; } to { opacity: 1; } }
-.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); margin: 12px 0 16px; overflow-x: auto;
-  scrollbar-width: none; }
-.tabs a { padding: 8px 14px; text-decoration: none; color: var(--muted); border-bottom: 2px solid transparent;
-  white-space: nowrap; flex: none; }
-.tabs a.on { color: var(--ink); border-color: var(--accent); }
 .cite { font: 11px var(--mono); padding: 0 5px; margin: 0 1px; border-radius: 4px; color: var(--accent); }
 .cites { white-space: nowrap; }
 .chips { display: flex; gap: 6px; flex-wrap: wrap; list-style: none; padding: 0; }
 .chip { font-family: var(--mono); font-size: 12px; }
-.chip.st-changed { border-color: var(--warn); } .chip.st-added { border-color: var(--ok); } .chip.st-removed { border-color: var(--bad); }
-.findings-mini { list-style: none; padding: 0; } .findings-mini li { margin: 4px 0; }
 .finding.dismissed { opacity: .55; } .finding.focus { outline: 2px solid var(--accent); }
-.finding h3 { margin: 0; } .finding .actions { margin-left: auto; }
+.finding h3 { margin: 0; }
 .evidence li.sev-high { color: var(--bad); } .evidence li.sev-medium { color: var(--warn); }
 .toolbar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
 .toolbar label { display: flex; gap: 6px; align-items: center; } .toolbar select:not([multiple]) { width: auto; }
 .toolbar input[type=checkbox] { width: auto; }
 .seg { display: inline-flex; } .seg button { border-radius: 0; } .seg button:first-child { border-radius: 6px 0 0 6px; }
 .seg button:last-child { border-radius: 0 6px 6px 0; } .seg button.on { background: var(--accent); color: var(--surface); border-color: var(--accent); }
-.flows-body { display: grid; grid-template-columns: 1fr 340px; gap: 12px; }
 .graph { height: 68vh; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
 .side { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 12px; overflow: auto; max-height: 68vh; }
 .side ul { padding-left: 16px; }
@@ -95,28 +84,22 @@ h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: v
 .diff { width: 100%; border-collapse: collapse; font: 12px/1.45 var(--mono); margin-top: 8px; }
 .diff td { padding: 0 6px; white-space: pre-wrap; word-break: break-all; }
 .diff .ln { width: 1%; color: var(--muted); text-align: right; user-select: none; white-space: nowrap; word-break: normal; }
-.diff .add-comment { width: 1%; } .diff .add-comment button { visibility: hidden; font-weight: 700; }
-.diff tr:hover .add-comment button { visibility: visible; }
 .diff tr.add { background: var(--add-bg); } .diff tr.del { background: var(--del-bg); }
 .diff tr.gap td { background: var(--gap-bg); color: var(--muted); text-align: center; }
 .diff .sign { color: var(--muted); margin-right: 6px; }
-.diff .comment-row td { font-family: var(--sans); padding: 6px 0; }
 .comments { margin-top: 8px; } .thread { border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; margin: 6px 0; background: var(--bg); }
 .thread.resolved { opacity: .6; } .comment + .comment { border-top: 1px dashed var(--line); margin-top: 6px; padding-top: 6px; }
 .comment-head { display: flex; gap: 8px; align-items: baseline; } .comment-body { white-space: pre-wrap; }
 .thread-actions { display: flex; gap: 8px; align-items: flex-start; margin-top: 6px; }
 .composer { display: flex; gap: 8px; align-items: flex-start; margin-top: 6px; flex: 1; } .composer textarea { flex: 1; }
-.table-wrap { overflow-x: auto; }
-@media (max-width: 860px) { .flows-body { grid-template-columns: 1fr; } .page { padding: 16px; } }
+@media (max-width: 860px) { .page { padding: 16px; } }
 @media (max-width: 600px) {
   .topbar { padding: 8px 16px; }
   .topbar nav { margin-left: 0; }
-  .opt { display: none; }
   .graph { height: 60vh; }
   .side { max-height: none; }
   .diff { font-size: 11px; }
   .diff td { padding: 0 3px; }
-  .review-head h1 { font-size: 19px; }
   select[multiple] { min-width: 0; width: 100%; }
 }
 
@@ -193,9 +176,6 @@ button.go:disabled { opacity: .55; }
 .hc-row .detail { font: 12px var(--mono); color: var(--muted); margin-top: 2px; word-break: break-word; }
 .hc-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 0 14px; }
 
-/* ---- review sub-pages: findings, files, CLs ---- */
-.review-body .card h3, .review-body .card h2 { margin-top: 0; }
-.review-body .badge { border: 0; padding: 2px 9px; background: var(--gap-bg); }
 
 @media (max-width: 760px) {
   .home-page { grid-template-columns: 1fr; }
```

`frontend/src/workspace/Workspace.tsx`:

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index ddeec7f..40fdec4 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -2,7 +2,6 @@ import { useCallback, useEffect, useMemo, useState } from "react";
 import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
 import { api } from "../api";
 import { useMe } from "../App";
-import "../board/board.css";
 import { driftSummary } from "../board/drift";
 import AiPill from "../components/AiPill";
 import { useSources } from "../board/useSources";
```

`frontend/src/workspace/graph/GraphView.tsx`:

```diff
diff --git a/frontend/src/workspace/graph/GraphView.tsx b/frontend/src/workspace/graph/GraphView.tsx
index e7c31a3..39e1d24 100644
--- a/frontend/src/workspace/graph/GraphView.tsx
+++ b/frontend/src/workspace/graph/GraphView.tsx
@@ -142,7 +142,7 @@ export default function GraphView({ board, prefKey, flowIndex, onFlow, quiet, on
   }, []);
 
   return (
-    <div className="bd ws-graph">
+    <div className="ws-graph">
       {board.flows.length > 0 && (
         <FlowStrip board={board} flows={board.flows} index={flowIndex} steps onFlow={(i) => { onFlow(i); }} />
       )}
```

`frontend/src/workspace/workspace.css`:

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index c8611d8..108ff53 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -1,3 +1,232 @@
+/* Graph, code and diff (was board.css), first so the workspace rules below win ties as before. The role tokens sit on :root with dark values under
+   :root[data-theme="dark"]; literal colours remain only on the amber changed-node fill, which reads the same in
+   both themes. The board's --info, --ok and --warn are --bd-* so they never shadow styles.css's. */
+:root {
+  --bd-bg: #f6f7fb; --bd-ink: #151a2d; --bd-muted: #6a7089; --bd-faint: #a3a8bf; --bd-line: #e2e5ef;
+  --bd-surface: #ffffff; --bd-card: #ffffff; --bd-subtle: #fafbfe; --bd-sunken: #f1f2f8; --bd-hover: #f5f3ff;
+  --bd-sel: #efeaff; --bd-btn-hover: #e5e3ff; --bd-strong: #151a2d; --bd-on-strong: #ffffff; --bd-shadow: 21, 26, 45;
+  --bd-node-ink: #4a5068; --bd-node-line: #d4d8e6; --bd-node-line-hover: #9aa3c4; --bd-edge: #c7cbdb; --bd-rule: #dde1ee;
+  --bd-band: rgba(109, 74, 255, .04); --bd-band-label: #9aa0b8; --bd-arrow: #b3b8cc; --bd-grip: #c9cde0;
+  --bd-thread-line: #e0d9ff; --bd-check-ink: #3d4260;
+  --flow: #6d4aff; --flow-glow: rgba(109, 74, 255, .28);
+  --chg: #ffb020; --chg-deep: #c26a00; --chg-bg: #ffe7b3; --chg-bg-soft: #fff1cc; --chg-ink: #7a4300;
+  --fx: #ff4d6d; --fx-bg: #ffe4ea; --fx-ink: #b0163e; --effects-bg: #fff8fa; --hot-bg: #fff4f6;
+  --field: #00a6a6; --field-bg: #dcf7f5; --field-ink: #006b6b;
+  --ctx-bg: #e7ebff; --ctx-bg-soft: #eef1ff; --ctx-ink: #3b4bd8;
+  --add: #e6f9ee; --add-ink: #1a9a4f; --del: #ffecef; --del-ink: #d63a5a;
+  --bd-warn: #ff4d6d; --warn-bg: #fff0f3; --warn-ink: #8a1230; --bd-info: #3b82f6; --info-bg: #eef5ff; --info-ink: #1d4ea0;
+  --bd-ok: #16a34a; --ok-bg: #ecfbf1; --ok-ink: #13692f;
+  --hl-kw: #d6336c; --hl-ty: #6d4aff; --hl-num: #e8590c; --hl-str: #2b8a3e; --hl-cm: #8a90a8; --hl-fn: #1c7ed6;
+  --hl-mc: #0b7285; --hl-pp: #ae3ec9;
+  --bd-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
+  --bd-sans: Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
+}
+.ws-graph { background: var(--bd-bg); color: var(--bd-ink); font: 14px/1.45 var(--bd-sans); }
+.ws-graph button { font: inherit; color: inherit; }
+:root[data-theme="dark"] {
+  --bd-bg: #12141c; --bd-ink: #e6e8f2; --bd-muted: #a0a6bf; --bd-faint: #6f7592; --bd-line: #2c3142;
+  --bd-surface: #1b1e2a; --bd-card: #1b1e2a; --bd-subtle: #20232f; --bd-sunken: #262a38; --bd-hover: #262540;
+  --bd-sel: #2f2a55; --bd-btn-hover: #34305e; --bd-strong: #e6e8f2; --bd-on-strong: #151a2d; --bd-shadow: 0, 0, 0;
+  --bd-node-ink: #c6cbe0; --bd-node-line: #3a3f55; --bd-node-line-hover: #6b7396; --bd-edge: #4b5170; --bd-rule: #272c3c;
+  --bd-band: rgba(150, 130, 255, .06); --bd-band-label: #7c829e; --bd-arrow: #5d637d; --bd-grip: #4a5068;
+  --bd-thread-line: #3d3866; --bd-check-ink: #b8bdd6;
+  --flow: #8f75ff; --flow-glow: rgba(143, 117, 255, .35);
+  --chg-bg: #4a3510; --chg-bg-soft: #33270f; --chg-ink: #ffcf7a;
+  --fx-bg: #45202c; --fx-ink: #ff94a8; --effects-bg: #2a1a21; --hot-bg: #33202a;
+  --field: #2cc9c4; --field-bg: #133a3a; --field-ink: #7de3df;
+  --ctx-bg: #26305a; --ctx-bg-soft: #1f2540; --ctx-ink: #a6b4ff;
+  --add: #173322; --add-ink: #6bd897; --del: #3d1c25; --del-ink: #ff8aa0;
+  --warn-bg: #3a1d26; --warn-ink: #ffb7c4; --bd-info: #6ea8ff; --info-bg: #172640; --info-ink: #b0cdff;
+  --bd-ok: #4ccb7a; --ok-bg: #15301f; --ok-ink: #97e3b4;
+  --hl-kw: #ff7ab2; --hl-ty: #b6a2ff; --hl-num: #ffa45c; --hl-str: #7ee08a; --hl-cm: #7d849c; --hl-fn: #7cc4ff;
+  --hl-mc: #5ad6dd; --hl-pp: #e7a0f8;
+}
+body.bd-dragging, body.bd-dragging * { user-select: none !important; -webkit-user-select: none !important; }
+body.bd-resizing, body.bd-resizing * { cursor: col-resize !important; user-select: none !important; }
+body.bd-resizing-v, body.bd-resizing-v * { cursor: row-resize !important; user-select: none !important; }
+
+/* pills and stage notes in the review head */
+.bd-pill { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 99px; letter-spacing: .03em; white-space: nowrap; }
+.bd-pill.high { background: var(--fx); color: #fff; } .bd-pill.medium { background: #ffcf66; color: #5a3a00; }
+.bd-pill.low { background: #b9f0cc; color: #13692f; } .bd-pill.ghost { background: var(--gap-bg); color: var(--muted); }
+.bd-notes { font-size: 12px; color: var(--warn); } .bd-notes summary { cursor: pointer; }
+.bd-notes .banner { color: var(--bd-ink); }
+
+/* flow tags */
+.bd-tag { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 6px; text-transform: uppercase; letter-spacing: .04em; }
+.bd-tag.state { background: var(--field-bg); color: var(--field-ink); } .bd-tag.contract { background: var(--fx-bg); color: var(--fx-ink); }
+
+/* stage */
+.bd-stage { position: relative; flex: 1; min-width: 0; overflow: hidden; touch-action: none; isolation: isolate; }
+.bd-canvas { position: absolute; inset: 0; cursor: grab; }
+.bd-canvas.drag { cursor: grabbing; }
+.bd-bands, .bd-edges { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
+.bd-bands .fill { fill: var(--bd-band); } .bd-bands .fill.alt { fill: rgba(255,255,255,0); }
+.bd-bands .rule { fill: none; stroke: var(--bd-rule); stroke-width: 1; }
+.bd-blabel { position: absolute; right: 12px; text-align: right; font-size: 10px; font-weight: 700; letter-spacing: .12em; color: var(--bd-band-label);
+  text-transform: uppercase; transform-origin: 100% 0; pointer-events: none; white-space: nowrap; }
+.bd-edge { fill: none; stroke: var(--bd-edge); stroke-width: 1.6; transition: stroke .2s, opacity .2s; }
+.bd-edge.flow { stroke: var(--flow); stroke-width: 3.2; filter: drop-shadow(0 0 5px var(--flow-glow)); }
+.bd-edge.data { stroke-dasharray: 6 5; stroke: var(--field); }
+.bd-edge.fx { stroke: var(--fx); stroke-width: 2.6; stroke-dasharray: 6 5; }
+.bd-edge.dim { opacity: .25; }
+
+/* nodes */
+.bd-node { position: absolute; transform-origin: center; padding: 7px 12px; border-radius: 12px; background: var(--bd-surface);
+  border: 1.5px solid var(--bd-node-line); font: 500 12.5px var(--bd-mono); color: var(--bd-node-ink); white-space: nowrap;
+  box-shadow: 0 2px 6px rgba(var(--bd-shadow), .06); cursor: pointer;
+  transition: opacity .2s, box-shadow .2s, border-color .2s; user-select: none; }
+.bd-node .lbl { display: inline-block; max-width: 280px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
+.bd-node:hover { box-shadow: 0 6px 18px rgba(var(--bd-shadow), .16); border-color: var(--bd-node-line-hover); }
+.bd-node.chg { background: linear-gradient(135deg, #ffd36b, #ffab1f); border: 2.5px solid var(--chg-deep); color: #2b1a00; font-weight: 700;
+  padding: 9px 14px 8px; border-radius: 14px; animation: bd-pulse 2.4s ease-in-out infinite; }
+@keyframes bd-pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(255,176,32,.55), 0 6px 16px rgba(194,106,0,.28); }
+                      50% { box-shadow: 0 0 0 10px rgba(255,176,32,0), 0 6px 16px rgba(194,106,0,.28); } }
+.bd-node.chg .kind { display: block; font: 800 9px/1 var(--bd-sans); letter-spacing: .12em; text-transform: uppercase; color: #7a4300; margin-bottom: 4px; }
+.bd-node .stat { display: inline-flex; gap: 4px; margin-left: 8px; vertical-align: 1px; }
+.bd-node .stat b { font: 700 10px var(--bd-mono); padding: 1px 5px; border-radius: 5px; background: #fff; }
+.bd-node .stat .p { color: var(--add-ink); } .bd-node .stat .m { color: var(--del-ink); }
+.bd-node .warn-dot { position: absolute; right: -7px; top: -7px; width: 16px; height: 16px; border-radius: 50%; background: var(--bd-warn); color: #fff;
+  font: 800 10px/16px var(--bd-sans); text-align: center; box-shadow: 0 2px 6px rgba(255,77,109,.45); }
+.bd-node.field { border-radius: 4px 14px 14px 4px; background: var(--field-bg); border-color: var(--field); font-style: italic; color: var(--field-ink); }
+.bd-node.onflow { border-color: var(--flow); box-shadow: 0 0 0 4px var(--flow-glow); color: var(--bd-ink); }
+.bd-node.chg.onflow { box-shadow: 0 0 0 4px var(--flow-glow), 0 6px 16px rgba(194,106,0,.28); color: #2b1a00; }
+.bd-node.dim { opacity: .28; }
+.bd-node.has-card { outline: 2px solid color-mix(in srgb, var(--bd-strong) 55%, transparent); outline-offset: 3px; }
+.bd-node.front { outline: 3px solid var(--bd-strong); }
+.bd-node.moved::after { content: "↔"; position: absolute; left: -10px; bottom: -10px; font-size: 10px; color: var(--bd-muted); }
+.bd-node.grab { cursor: grabbing; box-shadow: 0 0 0 4px color-mix(in srgb, var(--bd-strong) 18%, transparent); }
+.bd-node .fxbadge { position: absolute; left: 50%; top: calc(100% + 8px); transform: translateX(-50%); background: var(--fx); color: #fff;
+  font: 600 10.5px/1.3 var(--bd-sans); font-style: normal; padding: 4px 8px; border-radius: 8px; white-space: nowrap; max-width: 360px;
+  overflow: hidden; text-overflow: ellipsis; box-shadow: 0 4px 12px rgba(255,77,109,.35); pointer-events: none; }
+
+/* toolbar and legend */
+.bd-tools { position: absolute; left: 12px; top: 12px; z-index: 1000; display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
+  max-width: calc(100% - 24px); pointer-events: none; }
+.bd-tools > * { pointer-events: auto; }
+.bd-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
+.bd-toolbar .bd-seg, .bd-toolbar .float { background: var(--bd-surface) !important; box-shadow: 0 4px 14px rgba(var(--bd-shadow), .1); }
+.bd-toolbar .lbl { font: 700 10px var(--bd-sans); letter-spacing: .1em; text-transform: uppercase; color: var(--bd-muted); margin: 0 4px 0 8px; }
+.bd-legend { background: var(--bd-surface); border: 1px solid var(--bd-line); border-radius: 12px; padding: 8px 10px;
+  font-size: 11px; box-shadow: 0 6px 18px rgba(var(--bd-shadow), .08); }
+.bd-legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin: 0 4px 0 8px; vertical-align: -1px; }
+.bd-legend .sw:first-child { margin-left: 0; }
+.bd-legend .chg { background: linear-gradient(135deg, #ffd36b, #ffab1f); } .bd-legend .flow { background: var(--flow); }
+.bd-legend .field { background: var(--field); } .bd-legend .fx { background: var(--fx); }
+
+/* buttons */
+.bd-ibtn { border: 0 !important; background: var(--bd-sunken) !important; height: 28px; min-width: 28px; padding: 0 10px !important; border-radius: 8px !important;
+  cursor: pointer; font: 600 12px var(--bd-sans) !important; color: var(--bd-ink) !important; white-space: nowrap; }
+.bd-ibtn:hover { background: var(--bd-btn-hover) !important; } .bd-ibtn:disabled { opacity: .45; cursor: default; }
+.bd-seg { display: inline-flex; background: var(--bd-sunken); border-radius: 9px; padding: 2px; }
+.bd-seg .bd-ibtn { background: transparent !important; }
+.bd-seg .bd-ibtn.on { background: var(--bd-surface) !important; color: var(--flow) !important; box-shadow: 0 1px 3px rgba(0,0,0,.12); }
+
+/* a function's comments and notes */
+.bd-fn-comments { padding: 2px 12px 8px; border-top: 1px solid var(--bd-line); font-size: 12.5px; }
+.bd-more-lines { position: sticky; left: 0; padding: 4px 12px; background: var(--bd-sunken); color: var(--bd-muted); font: 11.5px var(--bd-sans); }
+.bd-more-lines button { margin-left: 8px; border: 0; background: none; color: var(--flow); font: 600 11.5px var(--bd-sans); cursor: pointer; padding: 0; }
+.bd-note { padding: 10px 12px; font-size: 12px; color: var(--bd-muted); } .bd-note.error { color: var(--fx-ink); }
+
+/* code */
+.bd-code { font: 12px/1.65 var(--bd-mono); overflow: auto; }
+.bd-ln { display: grid; grid-template-columns: 44px 18px 1fr; cursor: pointer; min-width: max-content; }
+.bd-ln:hover, .bd-sbs:hover { background: var(--bd-hover); }
+.bd-ln .no, .bd-sbs .no { color: var(--bd-faint); text-align: right; padding-right: 6px; user-select: none; }
+.bd-ln .sg { color: var(--bd-faint); text-align: center; user-select: none; }
+.bd-ln.a { background: var(--add); } .bd-ln.a .sg { color: var(--add-ink); font-weight: 700; }
+.bd-ln.d { background: var(--del); } .bd-ln.d .sg { color: var(--del-ink); font-weight: 700; }
+.bd-ln.hot, .bd-sbs.hot { background: var(--hot-bg); } .bd-ln.hot .no { color: var(--bd-warn); font-weight: 700; }
+.bd-ln.focus, .bd-sbs.focus { box-shadow: inset 4px 0 0 var(--flow); }
+.bd-code .src { white-space: pre; padding-right: 12px; }
+.bd-code .plus { visibility: hidden; margin-left: 6px; color: var(--flow); font: 700 11px var(--bd-sans); }
+.bd-ln:hover .plus, .bd-sbs:hover .plus { visibility: visible; }
+.hl-kw { color: var(--hl-kw); font-weight: 600; } .hl-ty { color: var(--hl-ty); } .hl-num { color: var(--hl-num); } .hl-str { color: var(--hl-str); }
+.hl-cm { color: var(--hl-cm); font-style: italic; } .hl-fn { color: var(--hl-fn); } .hl-mc { color: var(--hl-mc); font-weight: 600; }
+.hl-pp { color: var(--hl-pp); }
+.bd-ann { margin: 2px 12px 6px 62px; padding: 6px 10px 6px 12px; border-radius: 10px; font: 12px/1.4 var(--bd-sans); border-left: 4px solid; white-space: normal; }
+.bd-ann.warn { background: var(--warn-bg); border-color: var(--bd-warn); color: var(--warn-ink); }
+.bd-ann.info { background: var(--info-bg); border-color: var(--bd-info); color: var(--info-ink); }
+.bd-ann.ok { background: var(--ok-bg); border-color: var(--bd-ok); color: var(--ok-ink); }
+.bd-ann .k { font-weight: 800; font-size: 10px; letter-spacing: .06em; text-transform: uppercase; margin-right: 6px; }
+.bd-thread { margin: 4px 12px 8px 62px; padding: 2px 10px 8px; border-radius: 12px; background: var(--bd-hover); border: 1px solid var(--bd-thread-line);
+  font: 12.5px var(--bd-sans); white-space: normal; cursor: auto; }
+.bd-thread .thread { background: var(--bd-surface); border-color: var(--bd-thread-line); }
+.bd-thread textarea { border: 1px solid var(--bd-thread-line); border-radius: 10px; font: 12.5px var(--bd-sans); background: var(--bd-surface);
+  color: var(--bd-ink); }
+.bd-thread button:not(.link) { background: var(--flow); color: #fff; border: 0; border-radius: 9px; font: 600 12px var(--bd-sans); }
+.bd-sbs { display: grid; grid-template-columns: 44px minmax(0, 1fr) 44px minmax(0, 1fr); cursor: pointer; }
+.bd-sbs .src { white-space: pre-wrap; word-break: break-word; }
+.bd-sbs > .src.l, .bd-sbs > .src.empty:nth-child(2) { border-right: 1px solid var(--bd-line); }
+.bd-sbs .l.d { background: var(--del); } .bd-sbs .r.a { background: var(--add); }
+.bd-sbs .no.l.d { color: var(--del-ink); font-weight: 700; } .bd-sbs .no.r.a { color: var(--add-ink); font-weight: 700; }
+.bd-sbs .empty { background: repeating-linear-gradient(135deg, var(--bd-subtle), var(--bd-subtle) 6px, var(--bd-sunken) 6px, var(--bd-sunken) 12px); }
+
+/* resize grips */
+.bd-resizer { position: absolute; left: -5px; top: 0; bottom: 0; width: 10px; cursor: col-resize; z-index: 6; touch-action: none; }
+.bd-resizer::after { content: ""; position: absolute; left: 4px; top: 50%; width: 2px; height: 36px; margin-top: -18px; border-radius: 2px; background: var(--bd-grip); }
+.bd-resizer.right { left: auto; right: -5px; }
+.bd-resizer.bottom { left: 0; right: 0; top: auto; bottom: -5px; width: auto; height: 10px; cursor: row-resize; }
+.bd-resizer.bottom::after { left: 50%; top: 4px; width: 36px; height: 2px; margin: 0 0 0 -18px; }
+.bd-resizer:hover::after, body.bd-resizing .bd-resizer::after, body.bd-resizing-v .bd-resizer.bottom::after { background: var(--flow); }
+
+@media (max-width: 1100px) {
+  .bd-resizer { display: none; }
+}
+@media (max-width: 640px) {
+  .bd-legend { display: none; }
+}
+
+/* folded lines */
+.bd-gap { position: sticky; left: 0; display: flex; gap: 10px; align-items: center; padding: 3px 12px; background: var(--bd-sunken);
+  color: var(--bd-muted); font: 11.5px var(--bd-sans); border-top: 1px dashed var(--bd-line); border-bottom: 1px dashed var(--bd-line); }
+.bd-gap button { border: 0; background: none; color: var(--flow); font: 600 11.5px var(--bd-sans); cursor: pointer; padding: 2px 0; }
+.bd-gap button:hover { text-decoration: underline; }
+
+/* the map of a split review, and a part's visitors and +N (spec 2026-10-03-large-change-boards §5) */
+.ov-band { display: flex; gap: 10px; align-items: stretch; padding: 10px; border-radius: 10px; margin-bottom: 8px;
+  background: var(--bd-band); border: 1px solid var(--bd-rule); }
+.ov-band h3 { width: 92px; flex: none; margin: 4px 0 0; font: 700 11px var(--bd-sans); letter-spacing: .06em;
+  text-transform: uppercase; color: var(--bd-band-label); }
+.ov-blocks { display: flex; flex-wrap: wrap; gap: 10px; flex: 1; }
+.ov-block { flex: 1 1 240px; max-width: 360px; background: var(--bd-surface); border: 2px solid var(--bd-node-line); border-radius: 10px;
+  padding: 8px 10px; font: 12px var(--bd-sans); cursor: pointer; position: relative; }
+.ov-block:hover { border-color: var(--bd-node-line-hover); }
+.ov-block.high { border-color: var(--fx); } .ov-block.medium { border-color: var(--chg); }
+.ov-block.sel { box-shadow: 0 0 0 4px var(--flow-glow); }
+.ov-block.lit { outline: 2px dashed var(--flow); outline-offset: 2px; }
+.ov-block .nm { font: 700 13px var(--bd-mono); margin-right: 56px; }
+.ov-block .ct { color: var(--bd-muted); margin: 3px 0; }
+.ov-block .ln { color: var(--ctx-ink); }
+.ov-block .also { color: var(--chg-ink); font-style: italic; margin-top: 2px; }
+.ov-block .sev { font: 700 10px var(--bd-sans); padding: 1px 6px; border-radius: 4px; color: #fff; vertical-align: 1px; }
+.ov-block .sev.high { background: var(--fx); } .ov-block .sev.medium { background: var(--chg-deep); }
+.ov-block .sev.low { background: var(--bd-ok); } .ov-block .sev.info { background: var(--bd-info); }
+.bd-node.visitor { border-style: dashed; border-color: var(--flow); background: var(--bd-sel); }
+.bd-node.visitor.chg { border-style: dashed; border-color: var(--flow); }
+.bd-node .bd-home { margin-left: 6px; font: 600 10.5px var(--bd-sans); color: var(--flow); cursor: pointer; }
+.bd-node .bd-more-nb { position: absolute; left: 50%; top: 100%; transform: translateX(-50%); margin-top: 4px; display: flex; gap: 4px;
+  white-space: nowrap; }
+.bd-node .bd-more-nb span { font: 600 10px var(--bd-sans); color: var(--ctx-ink); background: var(--ctx-bg-soft);
+  border: 1px solid var(--ctx-bg); border-radius: 99px; padding: 0 6px; cursor: pointer; }
+.bd-node .bd-more-nb span:hover { background: var(--ctx-bg); }
+.bd-ibtn.over { border-color: var(--flow); color: var(--flow); }
+@media (max-width: 640px) {
+  .ov-band { flex-direction: column; gap: 6px; padding: 8px; }
+  .ov-band h3 { width: auto; margin: 0; }
+  .ov-blocks { flex-direction: column; }
+  .ov-block { max-width: none; flex: none; width: 100%; box-sizing: border-box; }
+  .ov-block .ln:nth-of-type(n+5) { display: none; }
+}
+
+/* story graphs (spec 2026-10-04-change-stories §3.1): a note under the name, a struct's fields, "+N more" */
+.bd-node .note { display: block; max-width: 260px; overflow: hidden; text-overflow: ellipsis; margin-top: 3px;
+  font: 500 10.5px/1.25 var(--bd-sans); font-style: normal; opacity: .85; }
+.bd-node.chg .note { color: #4a2c00; }
+.bd-node .fields { display: flex; flex-direction: column; margin-top: 4px; font-size: 11px; font-style: normal; opacity: .9; }
+.bd-node.more { border-style: dashed; background: transparent; color: var(--bd-muted); font: 600 12px var(--bd-sans); }
+.bd-node.more:hover { color: var(--bd-ink); }
+
 /* The review workspace (spec 2026-10-04-review-workspace §2.1): header, rail, centre, detail panel. */
 .ws { display: flex; flex-direction: column; overflow: hidden !important; }
 .ws-head { flex: none; display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; padding: 8px 16px;
```

Delete:

```bash
git rm frontend/src/board/board.css
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-detail.spec.ts e2e/ai.spec.ts e2e/theme.spec.ts`

Expected: `✓ built in …` and `18 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4`

Expected: `Test Files  30 passed (30)` and `Tests  116 passed (116)` and `✓ built in …` and `50 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/ai.spec.ts frontend/e2e/helpers.ts frontend/e2e/theme.spec.ts frontend/e2e/workspace-detail.spec.ts frontend/src/styles.css frontend/src/workspace/Workspace.tsx frontend/src/workspace/graph/GraphView.tsx frontend/src/workspace/workspace.css
git commit -m "style(ui): one workspace.css — board.css folds in on :root tokens, dead rules go; code in the detail panel gets its diff colours"
```

---

## Finish

- [ ] Run everything: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q` (expected `All checks passed!` and `439 passed, 1 skipped`) and `cd frontend && npx vitest run && npm run build && npx playwright test --workers=4` (expected `Test Files  30 passed (30)` and `Tests  116 passed (116)` and `✓ built in …` and `50 passed`).
- [ ] At size, by hand (lab README): review libgit2-big CL 2 (#6896) and open `/r/<id>` on a desktop and a phone, with screenshots for the owner. Expected: the rail lists the CLs, then 4 stories each with its CL chips; no visible `N<digits>` anywhere; a story's Graph opens beside its Steps with ‹ › in place; a node click opens the detail panel and a second click closes it; on the phone, rail → story → detail sheet, each top bar naming the place.
