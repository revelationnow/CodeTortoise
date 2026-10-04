# Change Stories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every review opens on a list of at most 15 stories (what the change does, riskiest first). A repeated edit is one story with a count and a list of its sites. A story opens on its steps, with a graph of at most 12 annotated nodes one tab away and today's boards one link away.

**Architecture:** After the boards, the board stage runs `stories.build_stories` on the same board context. It finds repeated edits by token substitution, seeds behaviour stories from flow-causing functions, and joins the rest of the changed code to the nearest seed. Code no seed reaches is grouped as clusters are. `boardstore` stores the `stories` and `story:S<n>` blobs with the boards, new endpoints serve them, and the AI pass retells the top stories. The frontend adds a story list, a story page (Steps, Graph, sites) and routes around today's boards.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, SQLite, libclang, pytest, ruff; React 19, TypeScript (strict), Vite, vitest, Playwright. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-04-change-stories-design.md`

**Base:** `main` (the spec is its latest commit).

**Provenance:** every code block was run before this plan was written, and the stories were checked on three real libgit2 changes (lab README, "Change stories"). The tasks were then replayed in order on a fresh tree from `main`. Each task's tests failed before its implementation and passed after it, and the suite stayed green after every task. The replayed tree is byte-identical to the validated one. New files are given in full. Changes to existing files are unified diffs against the previous task's state (apply with `git apply`, or by hand).

## Global Constraints

- **Limits:** `analysis.max_stories: 15` entries on the list (the "N more behaviour stories" row counts as one); `analysis.story_graph_nodes: 12` nodes in a story graph before expansion; `llm.upfront_stories: 3`.
- **Nothing lost:** every changed function, flow and finding is in exactly one story. A function with a repeated edit and other edits belongs to its behaviour story and is listed by the repeated edit's story.
- **Labels:** no story title, summary, node label or field label contains an absolute path.
- **Old reviews:** a review without stories (run before them, or whose story building failed) opens `/r/:id` on today's board or overview.
- **Messages:** "this review has no stories: re-run it" (404), "That story no longer exists after the re-run." (404), "stories failed: <error>" (degraded board stage).
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).

## Review Focus

The conditions the spec implies that are most likely to bite a real user, most likely first. A test in the task that owns the code pins each one.

1. **A vendored library swapped** (libgit2 #7278 replaces pcre with pcre2: 247 changed functions and no flow) must give "Other changes" stories no bigger than a board, named by relative directories. Pinned by `test_unreached_code_over_the_board_budget_is_split_as_boards_are` and `test_other_changes_spread_over_the_workspace_are_named_by_their_main_directories` (Task 2).
2. **A function defined twice in one file under `#ifdef`** must be read at the definition that changed, not reported as "+0 −0". Pinned by `test_a_function_defined_twice_in_one_file_is_read_at_the_definition_that_changed` (Task 2).
3. **A repeated edit in headers and macros** (outside any function) must count as sites, with their files' depot paths. Pinned by `test_sites_outside_functions_count_with_the_edit` (Task 2).
4. **A review run before stories, or a story bookmarked before a re-run**, must give a clear message and the board, not a blank page. Pinned by `test_story_endpoints_serve_the_list_and_each_story` (Task 3) and the e2e test "a review without stories (run before them) opens on its board" (Task 5).
5. **More behaviour stories than the list holds** must never merge. Those past the cap collapse into one row, and the list still has at most 15 entries. Pinned by `test_behaviour_stories_are_never_merged_but_collapse_past_the_limit` (Task 2) and `test_a_large_change_is_told_in_at_most_15_stories_with_small_graphs` (Task 3).

## Spec Coverage

| Spec | Where |
|---|---|
| §2.1 mechanical stories (substitutions, sites, also in, effects) | Task 2 |
| §2.2 behaviour stories (seeds, joining, Other changes, findings, titles) | Task 2 |
| §2.3 tests, §2.4 the list (summary, order, cap, ids) | Task 2 |
| §2.5 labels | Task 1 |
| §3 the story page (data: steps, graph, sites) | Task 2 |
| §3 the story page (interface) | Task 5 |
| §4 blobs, endpoints, locate | Task 3 |
| §4 AI (explain `story`, up-front pass, configuration) | Task 4 |
| §5 interface (routes, citations, findings, phone) | Task 5 |
| §6 limits and failures | Tasks 2, 3, 5 |
| §7 lab check | Task 3 (README), Finish (by hand) |
| §8 testing | every task |

## Decisions the spec left open (or that differ from it)

- **A story graph shows at most 4 unchanged neighbours** (`stories.NEIGHBOURS`) beside its own code, so the 12 nodes go to the story's own code first.
- **Field lines go to the struct node.** Fields are listed inside their struct's node, and selecting that node shows its lines. Highlighting one field's line (§3.1) is left out.
- **Unreached code is grouped at the board budget** (`cluster_change(max_nodes=analysis.board_max_nodes)`), so a vendored-library swap gives several "Other changes" stories, not one of 247 functions.
- **"Other changes" stories in the same directory** are told apart by their first function: "Other changes in `src/libgit2` (`git_index__fill`)". Spread over the workspace, they name the two main directories "and N more directories".
- **Very large mechanical stories** come in one response; past 200 sites (`OPEN_SITES`) their files start collapsed. There is no per-file loading endpoint (§6).
- **The change panel** is on a story's Graph tab, closed at first. The story list shows the change's intent under the summary line instead of the full panel.
- **A story graph opens fitted to the canvas** (`fitZoom`, between 0.5 and 1). Desktop boards use zoom only for story graphs.
- **The mechanical e2e test serves a story through a mocked API**, because neither e2e fixture has a repeated edit. The real data path is covered by `test_stories.py` and the lab check.
- **Sites are counted as substituted line pairs.** On #6896 that gives 152 sites in 52 files (47 in tests), plus `git_vector_free_deep` at 28 sites as a second story. The spec's 181 sites in 65 files counted every changed line in git's diff.
- **`/r/:id/files`** (the old files page) redirects to `/r/:id/board`.

---

### Task 1: Anonymous structs named by their typedef, member or place

Spec §2.5. libclang spells an anonymous record "struct (unnamed at /abs/path.c:3:9)", which then shows on boards,
flows and findings. `aliasflow.record_name(cursor)` names a field's record as people do: its own name (libclang already
gives a typedef'd anonymous struct its typedef's name, `vec_t`); an anonymous record nested in a named one by the
outer record and the member holding it (`outer.frame`, `outer.frame.inner`, `u.half`); else
`anonymous struct (<file>:<line>)` / `anonymous union (…)`. Every `FieldAccess.record` the analyzer writes goes through
it. The facts stage then calls `facts.model.relative_records(facts, root)`, which makes those places
workspace-relative (`anonymous struct (src/a.c:3)`) so no label holds an absolute path. Reviews stored before keep
their labels.

**Files:**
- Modify: `backend/codetortoise/facts/aliasflow.py`
- Modify: `backend/codetortoise/facts/model.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/tests/test_aliasflow.py`

**Interfaces:**
- Consumes: nothing new (libclang cursors, `paths.canon`).
- Produces: `facts.aliasflow.record_name(rec: Cursor | None) -> str`;
  `facts.model.relative_records(facts: list[Facts], root: str) -> None` (in place), called in `pipeline.run_review`'s
  facts stage before the facts are stored.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_aliasflow.py`:

```diff
diff --git a/backend/tests/test_aliasflow.py b/backend/tests/test_aliasflow.py
index 7dabe56..f410607 100644
--- a/backend/tests/test_aliasflow.py
+++ b/backend/tests/test_aliasflow.py
@@ -128,3 +128,33 @@ def test_writes_to_freshly_allocated_objects_are_local(tmp_path):
     roots = {(a.line, a.path, a.root_kind) for a in fields if a.mode != "read"}
     assert (7, "e.n", "local") in roots and (8, "e.sig[]", "local") in roots
     assert (10, "?.n", "unknown") in roots  # object from a getter may be shared
+
+
+ANON_C = """typedef struct { int size; } vec_t;
+struct outer { struct { int size; struct { int depth; } inner; } frame; int n; };
+static struct { int count; } stats;
+union u { struct { int lo; } half; };
+void f(vec_t *v, struct outer *o, union u *x) { v->size = 1; o->frame.size = 2; o->frame.inner.depth = 3; stats.count = 4;
+  x->half.lo = 5; }
+"""
+
+
+def test_anonymous_records_are_named_by_typedef_member_or_place(tmp_path):
+    fields, _, _ = writes(tmp_path, "anon.c", ANON_C, ["-xc"], "f")
+    records = {a.field_name: a.record for a in fields if a.mode == "write"}
+    here = str(tmp_path / "anon.c")
+    assert records["size"] in ("vec_t", "outer.frame")
+    assert {a.record for a in fields if a.field_name == "size"} == {"vec_t", "outer.frame"}
+    assert records["depth"] == "outer.frame.inner" and records["lo"] == "u.half"
+    assert records["count"] == f"anonymous struct ({here}:3)"
+    assert not any("unnamed" in a.record for a in fields)
+
+
+def test_the_facts_stage_makes_anonymous_record_places_workspace_relative():
+    from codetortoise.facts.model import Facts, FieldAccess, TuInfo, relative_records
+    acc = FieldAccess(fn="f", field="c:@S@x@FI@n", field_name="n", record="anonymous struct (/ws/src/a.c:3)", file="/ws/src/a.c",
+                      line=4, path="s.n", root_kind="global", mode="write")
+    named = acc.model_copy(update={"record": "outer.frame"})
+    fx = [Facts(tu=TuInfo(file="/ws/src/a.c", variant="after"), fields=[acc, named])]
+    relative_records(fx, "/ws/")
+    assert [a.record for a in fx[0].fields] == ["anonymous struct (src/a.c:3)", "outer.frame"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_aliasflow.py -q`
Expected: FAIL — `2 failed, 5 passed` (`AssertionError: assert 'struct (unnamed at …/anon.c:2:16)' in ('vec_t', 'outer.frame')` and `ImportError: cannot import name 'relative_records' from 'codetortoise.facts.model'`)

- [ ] **Step 3: Implement**

`backend/codetortoise/facts/aliasflow.py`:

```diff
diff --git a/backend/codetortoise/facts/aliasflow.py b/backend/codetortoise/facts/aliasflow.py
index f803a31..3a0f23a 100644
--- a/backend/codetortoise/facts/aliasflow.py
+++ b/backend/codetortoise/facts/aliasflow.py
@@ -70,6 +70,28 @@ class AP:
         return (self.root_kind, self.root, self.steps)
 
 
+_RECORDS = (K.STRUCT_DECL, K.UNION_DECL, K.CLASS_DECL)
+
+
+def record_name(rec: ci.Cursor | None) -> str:
+    """A field's record as people name it (spec 2026-10-04-change-stories §2.5): its name; an anonymous record by the
+    named record and member holding it ("filesystem_iterator_frame.entries"); else "anonymous struct (<file>:<line>)"
+    (the facts stage makes the file workspace-relative). libclang names a typedef'd anonymous struct by its typedef."""
+    if rec is None:
+        return ""
+    if not rec.is_anonymous():
+        return rec.spelling
+    outer = rec.semantic_parent
+    if outer is not None and outer.kind in _RECORDS:
+        member = next((m for m in outer.get_children() if m.kind == K.FIELD_DECL
+                       and m.type.get_canonical().get_declaration() == rec), None)
+        if member is not None:
+            return f"{record_name(outer)}.{member.spelling}"
+    what = "union" if rec.kind == K.UNION_DECL else "struct"
+    loc = rec.location
+    return f"anonymous {what} ({canon(loc.file.name) if loc.file else '?'}:{loc.line})"
+
+
 def _strip(c: ci.Cursor) -> tuple[ci.Cursor, bool]:
     may = False
     while True:
@@ -272,7 +294,7 @@ class FunctionAnalyzer:
         elif s.kind == K.MEMBER_REF_EXPR and s.referenced is not None and s.referenced.kind == K.FIELD_DECL:
             f = s.referenced
             self._field_file(f)
-            step = (f.get_usr(), f.spelling, f.semantic_parent.spelling if f.semantic_parent else "")
+            step = (f.get_usr(), f.spelling, record_name(f.semantic_parent))
             kids = [k for k in s.get_children() if k.kind.is_expression()]
             if not kids:
                 bases = {AP("this", "this")}
@@ -414,7 +436,7 @@ class FunctionAnalyzer:
                     f = s.referenced
                     fields.append(FieldAccess(
                         fn=self.fn_usr, field=f.get_usr(), field_name=f.spelling,
-                        record=f.semantic_parent.spelling if f.semantic_parent else "",
+                        record=record_name(f.semantic_parent),
                         record_file=self._field_file(f),
                         decl_line=f.location.line, path="?." + f.spelling, root_kind="unknown", mode=mode,
                         via=[extra_via] if extra_via else [], file=file, line=line, confidence="may"))
@@ -456,7 +478,7 @@ class FunctionAnalyzer:
                 root = next(iter(sorted(a.root_kind for a in aps)), "unknown")
                 fields.append(FieldAccess(
                     fn=self.fn_usr, field=f.get_usr(), field_name=f.spelling,
-                    record=f.semantic_parent.spelling if f.semantic_parent else "",
+                    record=record_name(f.semantic_parent),
                     record_file=self._field_file(f),
                     decl_line=f.location.line, path=path, root_kind=root, mode="read", file=file, line=c.location.line,
                     confidence="precise" if aps else "may"))
```

`backend/codetortoise/facts/model.py`:

```diff
diff --git a/backend/codetortoise/facts/model.py b/backend/codetortoise/facts/model.py
index e3dc797..118cabc 100644
--- a/backend/codetortoise/facts/model.py
+++ b/backend/codetortoise/facts/model.py
@@ -87,3 +87,13 @@ class Facts(BaseModel):
     calls: list[CallEdge] = Field(default_factory=list)
     fields: list[FieldAccess] = Field(default_factory=list)
     globals: list[GlobalAccess] = Field(default_factory=list)
+
+
+def relative_records(facts: list[Facts], root: str) -> None:
+    """Anonymous records are named by their place ("anonymous struct (/ws/src/a.c:3)"): make it workspace-relative
+    (spec 2026-10-04-change-stories §2.5), in place."""
+    prefix = f"({root.rstrip('/')}/"
+    for fx in facts:
+        for a in fx.fields:
+            if prefix in a.record:
+                a.record = a.record.replace(prefix, "(")
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 6b9b59f..d7cd707 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -13,7 +13,7 @@ from codetortoise import boardstore
 from codetortoise.board import BoardContext, build_boards
 from codetortoise.detectors.base import DetectorContext, run_detectors
 from codetortoise.diffmap import map_changes
-from codetortoise.facts.model import Facts
+from codetortoise.facts.model import Facts, relative_records
 from codetortoise.facts.runner import build_requests, parse_summary, run_extraction
 from codetortoise.impact import ImpactModel, build_impact
 from codetortoise.llm.storyboard import build_storyboard
@@ -190,6 +190,7 @@ def run_review(rid: int, svc: Services) -> None:
             ctx["sel"].hops.update({p: 1 for p in extra})
             store.put_blob(rid, "selection", ctx["sel"])
             note = f"; {len(extra)} follow-up TU(s) for fields written by the change"
+        relative_records(before + after, canon(str(cfg.workspace.root)))
         ctx["before"], ctx["after"] = before, after
         store.put_blob(rid, "facts_before", before)
         store.put_blob(rid, "facts_after", after)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_aliasflow.py -q`
Expected: `7 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `386 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/facts/aliasflow.py backend/codetortoise/facts/model.py backend/codetortoise/pipeline.py backend/tests/test_aliasflow.py
git commit -m "feat(facts): name anonymous structs by their typedef, member or place"
```

---

### Task 2: Substitutions and the stories of a change

Spec §2, §3 (data). **Substitutions** (`substitutions.py`): lines are split into C tokens (identifiers, numbers,
literals, operators; whitespace and comments ignored); two lines are a substitution when a token SequenceMatcher finds
exactly one `replace` run (`git_vector_free` → `git_vector_dispose`). `changed_pairs(before, after)` pairs the lines of
each difflib hunk with as many removed as added lines and returns the substituted pairs and the count of changed lines
left unexplained; `explained()` returns the sites only when every changed line is one.

**Stories** (`stories.build_stories(ctx, home)`), built from the board context after the boards:
- **Mechanical:** a substitution that explains at least 2 changed functions (modified or signature changed; added and
  removed functions never) is one story; changed lines outside functions with the same substitution are sites too; a
  function explained by two substitutions joins the one with more sites; a function with the edit and other edits
  stays in its behaviour story and is listed in `also_in`. Title "`old` → `new` at N sites in M files (K in tests)".
- **Behaviour:** one seed per changed function outside mechanical stories that causes a flow, plus one per mechanical
  story whose functions cause flows ("What `old` → `new` changes: …"). Other changed code joins the nearest seed by
  breadth-first search over calls and field accesses the change added or removed; a tie goes to the riskier seed.
  Titles from the seed's first flow ("`uart_send` now writes `Uart::errors`; `uart_errors` reads it").
- **Other changes:** code no seed reaches is grouped with `cluster_change(max_nodes=board_max_nodes)`, so no "Other"
  story is bigger than a board; named "Other changes in `<dir>`" (relative to the change's root, the main function in
  brackets to tell same-named ones apart; spread out: the two main directories "and N more directories"), never an
  absolute path.
- **Tests:** changed test code outside mechanical stories is one "Tests" story; each function names the changed code it
  calls.
- **The list:** behaviour by risk, then Other, then mechanical by sites, then Tests; ids `S1…`. Past
  `analysis.max_stories` (15) Other stories merge by directory, then mechanical stories fold into "N more repeated
  edits", then behaviour stories past the cap are `collapsed` (the "N more behaviour stories" row counts as one
  entry). A summary line: "Mostly mechanical: X of Y changed lines are …" when repeated edits are at least half the
  changed lines, else counts ("2 behaviour stories, 1 repeated edit, 4 other changed functions, 3 test changes.").
- **Story graph:** at most `analysis.story_graph_nodes` (12) nodes: the cause, the flows' paths, the story's other
  changed functions, then up to 4 unchanged neighbours; the fields of one struct are one `struct` node listing them
  (edges go to it); a story with more changed code than fits gets a `more` node ("+N more changed functions"). Each
  node has a one-line `note` ("now writes tx, errors", "`git_vector_dispose` instead of `git_vector_free`", "+3 −1").
  A function defined twice in a file (`#ifdef`) is read at the definition that changed.
- Every changed function, flow and finding is in exactly one story (`node_story`, `flow_story`, `finding_story`).

`board.py` gains `BoardNode.note`, `.fields` (`StructField`), node kinds `struct` and `more`, `BoardSet.stories` /
`.story_details`, and `about_for()` (the change summary narrowed to some files and findings, shared with cluster
boards).

**Files:**
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/board.py`
- Create: `backend/codetortoise/substitutions.py`
- Create: `backend/codetortoise/stories.py`
- Test: `backend/tests/test_substitutions.py`
- Test: `backend/tests/test_stories.py`

**Interfaces:**
- Consumes: `board.BoardContext`, `build_flows`, `build_impacts`, `is_test_path`; `clusters.cluster_change`,
  `altered_access`; `facts.aliasflow.record_name` labels (Task 1).
- Produces: `substitutions.tokens(line)`, `Sub(old, new)`, `Site(sub, before_line, after_line, before, after)`,
  `substitution(old, new) -> Sub | None`, `changed_pairs(before, after) -> (list[Site], int)`,
  `explained(before, after) -> list[Site] | None`;
  `stories.Story(id, kind, title, summary, text_source, risk, counts, nodes, flows, findings, board, sub, subs,
  collapsed)`, `StoryFunction(node, label, note, on_flow, also, calls)`, `StorySite(path, line, function, node, before,
  after, test, effect, other_edits)`, `StoryRef(node, label, story)`, `StoryDetail(story, board, graph, functions,
  sites, also_in)`, `StorySet(summary, stories, node_story, flow_story, finding_story)`,
  `build_stories(ctx, home=None) -> (StorySet, dict[str, StoryDetail])`; config `analysis.max_stories = 15`,
  `analysis.story_graph_nodes = 12`; `board.StructField(id, label)`, `BoardNode.note`, `BoardNode.fields`,
  `BoardSet.stories`, `BoardSet.story_details`, `board.about_for(about, files, mine, findings) -> About`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_substitutions.py`:

```python
"""Repeated edits: line pairs whose only difference is one run of tokens (spec 2026-10-04-change-stories §2.1)."""
from codetortoise.substitutions import Site, Sub, changed_pairs, explained, substitution, tokens


def test_tokens_skip_comments_and_whitespace():
    assert tokens('  x->size = f(a, "s, t"); // note') == ["x", "->", "size", "=", "f", "(", "a", ",", '"s, t"', ")", ";"]
    assert tokens("a /* gone */ + b") == ["a", "+", "b"]


def test_a_substitution_is_one_run_of_tokens_that_differs():
    assert substitution("\tgit_vector_free(&v);", "\tgit_vector_dispose(&v);") == Sub("git_vector_free", "git_vector_dispose")
    assert substitution("return -1;", "return GIT_EINVALID;") == Sub("- 1", "GIT_EINVALID")
    assert substitution("int n = len(x);", "size_t n = len(x);") == Sub("int", "size_t")


def test_lines_differing_in_two_places_or_by_an_insertion_are_not_substitutions():
    assert substitution("f(a, b);", "g(a, c);") is None
    assert substitution("f(a);", "f(a, b);") is None             # a token inserted
    assert substitution("f(a);", "  f(a);  // same") is None      # no token differs


def test_a_function_is_explained_only_when_every_changed_line_is_a_substitution():
    before = ["void f(void) {", "  git_vector_free(&a);", "  x = 1;", "  git_vector_free(&b);", "}"]
    after = ["void f(void) {", "  git_vector_dispose(&a);", "  x = 1;", "  git_vector_dispose(&b);", "}"]
    sites = explained(before, after)
    assert [(s.sub, s.before_line, s.after_line) for s in sites] == [
        (Sub("git_vector_free", "git_vector_dispose"), 2, 2), (Sub("git_vector_free", "git_vector_dispose"), 4, 4)]
    assert sites[0].before == "git_vector_free(&a);" and sites[0].after == "git_vector_dispose(&a);"
    other = after[:3] + ["  y = 2;"] + after[3:]                  # one more line added: not explained
    assert explained(before, other) is None
    sites, unexplained = changed_pairs(before, other)
    assert len(sites) == 1 and unexplained == 3        # the unequal hunk's lines


def test_unequal_hunks_and_whitespace_only_changes():
    assert explained(["a;", "b;"], ["c;"]) is None
    assert explained(["  f(x);"], ["\tf(x);"]) is None            # nothing substituted: not a repeated edit
    assert explained(["  f(x);", "g(1);"], ["\tf(x);", "g(2);"]) == [Site(Sub("1", "2"), 2, 2, "g(1);", "g(2);")]
```

`backend/tests/test_stories.py`:

```python
"""Change stories (spec 2026-10-04-change-stories §2–§3): a review told as a few stories."""
from test_board import _ctx, _synthetic

from codetortoise.board import BoardContext
from codetortoise.config import AnalysisConfig
from codetortoise.diffmap import DiffMap, FunctionChange
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function, TuInfo
from codetortoise.impact import Edge, ImpactModel, Node
from codetortoise.stories import build_stories
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange

W = "/w"


def _fn(name, file, start, end):
    return Function(usr=f"c:@F@{name}", qualname=name, name=name, signature=f"void {name}(void)", return_type="void",
                    file=file, start_line=start, end_line=end)


def _body(name, lines):
    return [f"void {name}(void)", "{", *(f"\t{x}" for x in lines), "}"]


def _world(fns, calls=(), fields=(), cfg=None):
    """fns: (name, path relative to W, body lines before | None, body lines after | None). Functions are laid out in
    order, one file per path; a function whose body differs (or that is added or removed) is changed. calls: (caller,
    callee). fields: (function, record, field, mode, status) with status "added" for an access the change added."""
    texts: dict[str, tuple[list[str], list[str]]] = {}
    before, after, nodes, dm, changed = [], [], {}, [], []
    for i, (name, rel, b, a) in enumerate(fns, 1):
        path = f"{W}/{rel}"
        tb, ta = texts.setdefault(path, ([], []))
        nid = f"N{i}"
        status = "added" if b is None else "removed" if a is None else "changed" if b != a else "unchanged"
        nodes[nid] = Node(id=nid, key=f"c:@F@{name}", label=name, file=path, line=len(ta) + 1, status=status, layer=1)
        br = ar = None
        if b is not None:
            br = (len(tb) + 1, len(tb) + len(b) + 3)
            before.append(_fn(name, path, *br))
            tb += _body(name, b)
        if a is not None:
            ar = (len(ta) + 1, len(ta) + len(a) + 3)
            after.append(_fn(name, path, *ar))
            ta += _body(name, a)
        if status != "unchanged":
            changed.append(nid)
            kind = {"added": "added", "removed": "removed"}.get(status, "body_modified")
            dm.append(FunctionChange(file=path, depot="//d" + path, qualname=name, name=name, kind=kind,
                                     before_lines=br, after_lines=ar))
    by = {n.label: n.id for n in nodes.values()}
    edges = [Edge(id=f"E{i}", src=by[s], dst=by[d], kind="call") for i, (s, d) in enumerate(calls, 1)]
    accs = []
    for fn, rec, field, mode, st in fields:
        fid = f"field:c:@S@{rec}@FI@{field}"
        if fid not in {n.key for n in nodes.values()}:
            nid = f"N{len(nodes) + 1}"
            nodes[nid] = Node(id=nid, key=fid, kind="field", label=f"{rec}::{field}", layer=1)
        fnode = next(n.id for n in nodes.values() if n.key == fid)
        edges.append(Edge(id=f"E{len(edges) + 1}", src=by[fn], dst=fnode, kind="writes" if mode == "write" else "reads",
                          status=st))
        f = next(x for x in after if x.name == fn)
        accs.append(FieldAccess(fn=f.usr, field=f"c:@S@{rec}@FI@{field}", field_name=field, record=rec,
                                record_file=f"{W}/r.h", decl_line=1, path=f"r->{field}", root_kind="param", mode=mode,
                                file=f.file, line=f.start_line + 2))
    call_facts = [CallEdge(caller=f"c:@F@{s}", callee=f"c:@F@{d}", callee_name=d,
                           file=nodes[by[s]].file, line=nodes[by[s]].line + 2) for s, d in calls]
    files = [FileChange(depot="//d" + p, local=p, action="edit", before="\n".join(b) + "\n", after="\n".join(a) + "\n")
             for p, (b, a) in texts.items()]
    im = ImpactModel(nodes=nodes, edges=edges, changed=changed, blast=[])
    return BoardContext(ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=files), DiffMap(functions=dm),
                        [Facts(tu=TuInfo(file=f"{W}/a.c", variant="before"), functions=before)],
                        [Facts(tu=TuInfo(file=f"{W}/a.c", variant="after"), functions=after, calls=call_facts,
                               fields=accs)],
                        im, [], None, cfg or AnalysisConfig(), lambda ps: {p: "//d" + p for p in ps}, root=W)


def _mech(name, rel, var="a"):
    return (name, rel, ["x = 1;", f"git_vector_free(&{var});"], ["x = 1;", f"git_vector_dispose(&{var});"])


def _edit(name, rel):
    """A change that is not a substitution (a line added)."""
    return (name, rel, ["a = 0;"], ["a = 0;", f"{name}_more();"])


def _same(name, rel):
    """An unchanged function."""
    return (name, rel, ["b = 0;"], ["b = 0;"])


def _by_kind(ss, kind):
    return [s for s in ss.stories if s.kind == kind]


# ---- 1. repeated edits
def test_one_substitution_in_two_functions_is_a_mechanical_story_with_its_sites():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c", var="b"),
                ("lonely", "src/c.c", ["y = 1;"], ["y = 2;"])])           # `1` → `2` once: not a repeated edit
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.title == "`git_vector_free` → `git_vector_dispose` at 2 sites in 2 files"
    assert m.sub == ["git_vector_free", "git_vector_dispose"] and m.counts["sites"] == 2
    d = det[m.id]
    assert [(s.path, s.line, s.function, s.before, s.after) for s in d.sites] == [
        ("//d/w/src/a.c", 4, "free_a", "git_vector_free(&a);", "git_vector_dispose(&a);"),
        ("//d/w/src/b.c", 4, "free_b", "git_vector_free(&b);", "git_vector_dispose(&b);")]
    assert {f.note for f in d.functions} == {"`git_vector_dispose` instead of `git_vector_free`"}
    assert d.graph is None
    assert ss.node_story["N1"] == ss.node_story["N2"] == m.id and ss.node_story["N3"] != m.id


def test_a_function_with_the_edit_and_another_change_stays_out_and_is_listed_as_also_in():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c"),
                ("busy", "src/c.c", ["q(1);", "x = 1;", "git_vector_free(&a);"],
                 ["q(1, 2);", "x = 1;", "git_vector_dispose(&a);"])])
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.nodes == ["N1", "N2"] and m.counts["sites"] == 3
    d = det[m.id]
    assert [(r.label, r.story) for r in d.also_in] == [("busy", ss.node_story["N3"])]
    (site,) = [s for s in d.sites if s.function == "busy"]
    assert site.other_edits == ss.node_story["N3"] != m.id
    (other,) = _by_kind(ss, "other")
    (fn,) = det[other.id].functions
    assert fn.also == [m.id] and "also `git_vector_free` → `git_vector_dispose`" in fn.note


def test_test_sites_are_counted_and_test_code_without_the_edit_is_the_tests_story():
    c = _world([_mech("free_a", "src/a.c"), _mech("test_free", "tests/t.c"),
                ("test_other", "tests/u.c", ["check(1);"], ["check(2);", "check(3);"])])
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.counts["test_sites"] == 1 and m.title.endswith("(1 in tests)")
    assert [s.test for s in det[m.id].sites] == [False, True]
    (t,) = _by_kind(ss, "tests")
    assert t.title == "Tests" and t.nodes == ["N3"] and t.summary == "1 test function changed in 1 file."


def test_added_and_removed_functions_are_never_mechanical():
    c = _world([("old_api", "src/v.c", ["free(p);"], None), ("new_api", "src/v.c", None, ["dispose(p);"]),
                _mech("free_a", "src/a.c"), _mech("free_b", "src/b.c")])
    ss, det = build_stories(c)
    assert [s.kind for s in ss.stories] == ["other", "other", "mechanical"]
    assert {s.summary for s in _by_kind(ss, "other")} == {"New: `new_api`.", "Removed: `old_api`."}
    notes = {f.label: f.note for s in _by_kind(ss, "other") for f in det[s.id].functions}
    assert notes == {"old_api": "removed", "new_api": "new function"}


def test_a_function_defined_twice_in_one_file_is_read_at_the_definition_that_changed():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c")])
    # free_b also has an earlier, unchanged definition (under #ifdef): the facts list that one first
    first = _fn("free_b", f"{W}/src/b.c", 1, 5)
    fc = next(f for f in c.cs.files if f.local.endswith("b.c"))
    pad = "\n".join(_body("free_b", ["y = 0;", "y = 1;"])) + "\n"
    fc.before, fc.after = pad + fc.before, pad + fc.after
    for fx in (c.before[0], c.after[0]):
        for f in fx.functions:
            if f.name == "free_b":
                f.start_line, f.end_line = f.start_line + 5, f.end_line + 5
        fx.functions.insert(0, first)
    (d,) = [d for d in c.dm.functions if d.name == "free_b"]
    d.before_lines, d.after_lines = (6, 10), (6, 10)
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.nodes == ["N1", "N2"] and [s.line for s in det[m.id].sites] == [4, 9]


def test_the_summary_says_mostly_mechanical_when_repeated_edits_are_half_the_changed_lines():
    ss, _ = build_stories(_world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c"),
                                  ("f", "src/c.c", ["y = 1;"], ["y = 2;"])]))
    assert ss.summary == "Mostly mechanical: 2 of 3 changed lines are one edit (`git_vector_free` → `git_vector_dispose`)."
    ss, _ = build_stories(_world([_edit("f", "src/c.c"), _edit("test_f", "tests/t.c")]))
    assert ss.summary == "1 other changed function, 1 test change."
    ss, _ = build_stories(_world([_same("f", "src/c.c")]))
    assert ss.summary == "No changed functions." and ss.stories == []


# ---- 2. behaviour, joining, other changes
def test_a_flow_causing_function_is_a_behaviour_story_titled_from_its_flows():
    ctx, _ = _synthetic(callers=("api",))
    ss, det = build_stories(ctx)
    (b,) = ss.stories
    assert b.kind == "behaviour" and b.nodes == ["N1"]
    assert b.title == "`set` now writes `R::v`; `peek` reads it (1 more effect)"
    assert set(b.flows) == {fl.id for fl in det[b.id].board.flows} and len(b.flows) == 2
    assert ss.flow_story == {f: b.id for f in b.flows}
    g = det[b.id].graph
    assert g is not None and len(g.nodes) <= 12
    assert {n.kind for n in g.nodes} >= {"function", "struct"}
    (rec,) = [n for n in g.nodes if n.kind == "struct"]
    assert rec.label == "R" and [f.label for f in rec.fields] == ["v"]


def _joined():
    """`set` newly writes R::v and `peek` reads it (a flow); `helper` (changed) is called by `set`; `far` is called by
    `helper`; `lonely` is changed and connected to nothing; `test_x` is changed test code."""
    return _world([_edit("set", "src/a.c"), _same("peek", "src/b.c"), _edit("helper", "src/a.c"),
                   _edit("far", "src/d.c"), _edit("lonely", "lib/x/l.c"), _edit("test_x", "tests/t.c")],
                  calls=[("set", "helper"), ("helper", "far")],
                  fields=[("set", "R", "v", "write", "added"), ("peek", "R", "v", "read", "unchanged")])


def test_changed_code_joins_the_nearest_seed_and_the_rest_is_other_changes_and_tests():
    ss, det = build_stories(_joined())
    kinds = [(s.kind, s.title) for s in ss.stories]
    assert kinds == [("behaviour", "`set` now writes `R::v`; `peek` reads it"),
                     ("other", "Other changes in `lib/x`"), ("tests", "Tests")]
    b = ss.stories[0]
    assert b.nodes == ["N1", "N3", "N4"]                     # set, then helper (1 hop) and far (2 hops)
    assert ss.stories[1].nodes == ["N5"] and ss.stories[2].nodes == ["N6"]
    assert {ss.node_story[n] for n in ("N1", "N3", "N4")} == {b.id}


def test_other_changes_in_one_directory_are_told_apart_by_their_first_function():
    c = _world([_edit("a1", "src/a.c"), _edit("a2", "src/b.c")])
    ss, _ = build_stories(c)
    assert sorted(s.title for s in ss.stories) == ["Other changes in `src` (`a1`)", "Other changes in `src` (`a2`)"]


def test_findings_go_to_the_story_holding_their_node():
    from codetortoise.detectors.base import Finding
    c = _joined()
    c.findings = [Finding(id="F1", kind="field_mutation", severity="medium", title="t", summary="s", nodes=["N5"]),
                  Finding(id="F2", kind="field_mutation", severity="info", title="t", summary="s", nodes=["N4"])]
    ss, _ = build_stories(c)
    by = {s.kind: s for s in ss.stories}
    assert ss.finding_story["F1"] == by["other"].id and ss.finding_story["F2"] == by["behaviour"].id
    assert by["other"].risk == "medium"


# ---- 3. the list's limit
def test_past_the_limit_other_changes_merge_then_repeated_edits_fold():
    fns = [_edit(f"o{i}", f"src/d{i}/f.c") for i in range(4)]
    fns += [(f"m{i}{j}", f"src/m/f{i}.c", [f"old{i}(p);"], [f"new{i}(p);"]) for i in range(3) for j in range(2)]
    ss, det = build_stories(_world(fns, cfg=AnalysisConfig(max_stories=4)))
    assert [s.kind for s in ss.stories] == ["other", "mechanical", "mechanical", "mechanical"]
    (o,) = _by_kind(ss, "other")
    assert sorted(o.nodes) == ["N1", "N2", "N3", "N4"] and o.title == "Other changes in `src`"
    ss, det = build_stories(_world(fns, cfg=AnalysisConfig(max_stories=3)))
    assert [(s.kind, s.title) for s in ss.stories] == [
        ("other", "Other changes in `src`"), ("mechanical", "`old0` → `new0` at 2 sites in 1 file"),
        ("mechanical", "2 more repeated edits: 4 sites")]
    folded = ss.stories[2]
    assert folded.subs == [["old1", "new1"], ["old2", "new2"]] and len(det[folded.id].sites) == 4
    assert ss.node_story["N7"] == ss.node_story["N10"] == folded.id


def test_behaviour_stories_are_never_merged_but_collapse_past_the_limit():
    fns, fields = [], []
    for i in range(4):
        fns += [_edit(f"w{i}", f"src/w{i}.c"), _same(f"r{i}", f"src/r{i}.c")]
        fields += [(f"w{i}", f"R{i}", "v", "write", "added"), (f"r{i}", f"R{i}", "v", "read", "unchanged")]
    ss, _ = build_stories(_world(fns, fields=fields, cfg=AnalysisConfig(max_stories=2)))
    assert [s.kind for s in ss.stories] == ["behaviour"] * 4
    assert [s.collapsed for s in ss.stories] == [False, True, True, True]     # 1 shown + "3 more behaviour stories"


# ---- 4. graphs
def test_a_story_graph_has_at_most_the_configured_nodes_and_a_more_node_for_the_rest():
    fns = [_edit("set", "src/a.c"), _same("peek", "src/b.c")]
    fns += [_edit(f"h{i}", "src/a.c") for i in range(8)]
    calls = [("set", f"h{i}") for i in range(8)]
    ss, det = build_stories(_world(fns, calls=calls, fields=[("set", "R", "v", "write", "added"),
                                                              ("peek", "R", "v", "read", "unchanged")],
                                   cfg=AnalysisConfig(story_graph_nodes=6)))
    (b,) = ss.stories
    g = det[b.id].graph
    assert len(g.nodes) == 6
    (more,) = [n for n in g.nodes if n.kind == "more"]
    assert more.label == f"+{8 - 2} more changed functions"
    assert {n.label for n in g.nodes} >= {"set", "R", "peek"}
    assert len(det[b.id].board.nodes) == 11                    # the story's board keeps every node it mentions


def test_fields_of_one_struct_are_one_node_listing_them_and_edges_follow():
    fns = [_edit("set", "src/a.c"), _same("peek", "src/b.c")]
    ss, det = build_stories(_world(fns, fields=[("set", "R", "v", "write", "added"), ("set", "R", "w", "write", "added"),
                                                ("peek", "R", "v", "read", "unchanged")]))
    g = det[ss.stories[0].id].graph
    (rec,) = [n for n in g.nodes if n.kind == "struct"]
    assert sorted(f.label for f in rec.fields) == ["v", "w"]
    ids = {n.id for n in g.nodes}
    assert all(e.src in ids and e.dst in ids for e in g.edges)
    assert all(n in ids for fl in g.flows for n in fl.path)


def test_story_nodes_carry_a_one_line_note():
    ss, det = build_stories(_joined())
    notes = {n.label: n.note for n in det[ss.stories[0].id].graph.nodes}
    assert notes["set"] == "now writes v"
    assert notes["helper"] == "+1 −0 lines"
    assert notes["peek"].startswith("⚠ reads R::v")


# ---- 5. the uart fixture
def test_the_fixture_tells_two_behaviour_stories(analysed, fx_source):
    ss, det = build_stories(_ctx(analysed, fx_source))
    assert ss.summary == "2 behaviour stories."
    assert [(s.kind, s.risk, s.title) for s in ss.stories] == [
        ("behaviour", "high", "`uart_send` now writes `Uart::errors`; `uart_errors` reads it (1 more effect)"),
        ("behaviour", "medium", "`hal_write`'s signature changed; `uart_init` calls it")]
    for s in ss.stories:
        g = det[s.id].graph
        assert len(g.nodes) <= 12 and not any(n.label.startswith("/") or "(/" in n.label for n in g.nodes)
    assert {n.label: n.note for n in det["S2"].graph.nodes}["hal_write"] == "signature changed"


# ---- spec §8 cases
def test_a_function_explained_by_two_substitutions_joins_the_bigger_edit():
    two = ("both", "src/c.c", ["x = 1;", "git_vector_free(&a);", "f(OLD);"], ["x = 1;", "git_vector_dispose(&a);", "f(NEW);"])
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c"), two,
                ("g", "src/d.c", ["f(OLD);"], ["f(NEW);"])])
    ss, det = build_stories(c)
    big, small = _by_kind(ss, "mechanical")
    assert big.sub == ["git_vector_free", "git_vector_dispose"] and big.nodes == ["N1", "N2", "N3"]
    assert small.sub == ["OLD", "NEW"] and small.nodes == ["N4"] and small.counts["sites"] == 2   # both's site too


def test_sites_outside_functions_count_with_the_edit():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c")])
    c.cs.files.append(FileChange(depot="//d/w/src/v.h", local=f"{W}/src/v.h", action="edit",     # a header: no functions
                                 before="#define FREE(v) git_vector_free(&v)\n", after="#define FREE(v) git_vector_dispose(&v)\n"))
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.counts["sites"] == 3 and m.counts["files"] == 3
    (macro,) = [s for s in det[m.id].sites if s.function is None]
    assert macro.after == "#define FREE(v) git_vector_dispose(&v)" and macro.line == 1 and macro.path == "//d/w/src/v.h"


def test_code_as_near_to_two_seeds_joins_the_riskier():
    from codetortoise.detectors.base import Finding
    c = _world([_edit("w1", "src/a.c"), _same("r1", "src/b.c"), _edit("w2", "src/c.c"), _same("r2", "src/d.c"),
                _edit("mid", "src/e.c")],
               calls=[("w1", "mid"), ("w2", "mid")],
               fields=[("w1", "R1", "v", "write", "added"), ("r1", "R1", "v", "read", "unchanged"),
                       ("w2", "R2", "v", "write", "added"), ("r2", "R2", "v", "read", "unchanged")])
    c.findings = [Finding(id="F1", kind="field_mutation", severity="high", title="t", summary="s", nodes=["N3"])]
    ss, _ = build_stories(c)
    risky = next(s for s in ss.stories if "N3" in s.nodes)
    assert ss.stories[0] is risky and "N5" in risky.nodes


def test_every_changed_function_flow_and_finding_is_in_exactly_one_story():
    from codetortoise.detectors.base import Finding
    c = _joined()
    c.findings = [Finding(id=f"F{i}", kind="k", severity="low", title="t", summary="s", nodes=[n])
                  for i, n in enumerate(["N1", "N3", "N5", "N6", "N2"], 1)]
    ss, det = build_stories(c)
    homes = [n for s in ss.stories for n in s.nodes]
    assert sorted(homes) == sorted(c.impact.changed) and len(homes) == len(set(homes))
    flows = [f for s in ss.stories for f in s.flows]
    assert len(flows) == len(set(flows)) and set(flows) == set(ss.flow_story)
    found = [f for s in ss.stories for f in s.findings]
    assert sorted(found) == ["F1", "F2", "F3", "F4", "F5"]


def test_other_changes_spread_over_the_workspace_are_named_by_their_main_directories():
    c = _world([_edit("a1", "deps/pcre/a.c"), _edit("a2", "deps/pcre/b.c"), _edit("b1", "src/util/c.c"),
                _edit("top", "main.c")], calls=[("a1", "a2"), ("a2", "b1"), ("b1", "top")])
    ss, _ = build_stories(c)
    (o,) = ss.stories
    assert o.title == "Other changes in `deps/pcre`, `src/util` and 1 more directory"
    assert "/w" not in o.title
    c = _world([_edit("top", "main.c"), _edit("top2", "main2.c")], calls=[("top", "top2")])
    assert build_stories(c)[0].stories[0].title == "Other changes in `the workspace root`"


def test_unreached_code_over_the_board_budget_is_split_as_boards_are():
    fns = [_edit(f"p{i}", f"deps/p/f{i % 3}.c") for i in range(6)] + [_edit(f"q{i}", f"src/q/f{i}.c") for i in range(3)]
    calls = [(f"p{i}", f"p{i + 1}") for i in range(5)] + [("p5", "q0"), ("q0", "q1"), ("q1", "q2")]
    ss, _ = build_stories(_world(fns, calls=calls, cfg=AnalysisConfig(board_max_nodes=4)))
    assert len(ss.stories) > 1 and all(len(s.nodes) <= 4 for s in ss.stories)
    assert all(s.title.startswith("Other changes in `") for s in ss.stories)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_substitutions.py tests/test_stories.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.substitutions'` and `No module named 'codetortoise.stories'` (collection stops: `2 errors`)

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index 89775b9..a5c6749 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -92,6 +92,8 @@ class AnalysisConfig(BaseModel):
     cluster_min_changed: int = 3   # clusters with fewer changed functions merge with one in the same directory
     overview_max_clusters: int = 60  # more clusters than this: the smallest merge further
     expand_step: int = 10          # "+N callers / callees": neighbours added per expansion
+    max_stories: int = 15          # entries on a review's story list (spec 2026-10-04 §2.4)
+    story_graph_nodes: int = 12    # nodes a story's graph shows before the reader expands it
     entrypoint_patterns: list[str] = Field(
         default_factory=lambda: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"])
 
```

`backend/codetortoise/board.py`:

```diff
diff --git a/backend/codetortoise/board.py b/backend/codetortoise/board.py
index 7c4b0bd..266e29e 100644
--- a/backend/codetortoise/board.py
+++ b/backend/codetortoise/board.py
@@ -13,7 +13,7 @@ from collections import defaultdict, deque
 from collections.abc import Callable, Collection
 from dataclasses import dataclass
 from dataclasses import field as dfield
-from typing import Literal
+from typing import Any, Literal
 
 from pydantic import BaseModel, Field, model_validator
 
@@ -57,11 +57,16 @@ class NodeChange(BaseModel):
     rem: int = 0
 
 
+class StructField(BaseModel):
+    id: str
+    label: str
+
+
 class BoardNode(BaseModel):
     id: str
     key: str
     label: str
-    kind: Literal["function", "field"] = "function"
+    kind: Literal["function", "field", "struct", "more"] = "function"
     layer: int | None = None
     path: str | None = None          # depot path of the defining file
     local: str | None = None
@@ -73,6 +78,8 @@ class BoardNode(BaseModel):
     home: str | None = None          # a visitor: the cluster this node belongs to (spec 2026-10-03-large §3)
     more_callers: int = 0            # callers / callees not on the board, for "+N callers" (expansion)
     more_callees: int = 0
+    note: str | None = None          # a story graph: what changed here, in a few words (spec 2026-10-04 §3.1)
+    fields: list[StructField] = Field(default_factory=list)   # a struct node: the fields it stands for
 
 
 class BoardEdge(BaseModel):
@@ -253,6 +260,8 @@ class BoardSet:
     clusters: dict[str, Board] = dfield(default_factory=dict)
     home: dict[str, str] = dfield(default_factory=dict)     # node id -> cluster id
     note: str | None = None                                # why the review fell back to one board
+    stories: Any = None                                    # stories.StorySet (spec 2026-10-04), when built
+    story_details: dict[str, Any] = dfield(default_factory=dict)   # story id -> stories.StoryDetail
 
 
 @dataclass
@@ -783,18 +792,23 @@ def _split(c: BoardContext, x: _Ctx, impacts: list[Impact], flows: list[Flow]) -
     for cl in res.clusters:
         cf, chosen, hidden = picks[cl.id]
         files = {depots.get(x.local(m)) for m in (cl.members or [cl.of]) if x.local(m)} - {None}   # its own code
-        mine = set(cl.findings)
-        part = about.model_copy(deep=True)
-        part.tree = [AboutDir(dir=d.dir, files=[f for f in d.files if f.path in files]) for d in part.tree]
-        part.tree = [d for d in part.tree if d.files]
-        part.why = [w for w in part.why if w.finding in mine] or [AboutWhy(severity=f.severity, text=f.title, finding=f.id)
-                                                                   for f in c.findings if f.id in mine][:4]
-        part.drift = [d for d in part.drift if set(d.files or []) & files]
+        part = about_for(about, files, set(cl.findings), c.findings)
         boards[cl.id] = _render(x, impacts, cf, chosen, depots, hidden=hidden, about=part,
                                 cluster=ClusterRef(id=cl.id, name=cl.name), home=res.home)
     return BoardSet(overview=_overview(x, res, about, depots, flows), clusters=boards, home=res.home)
 
 
+def about_for(about: About, files: set[str], mine: set[str], findings: list[Finding]) -> About:
+    """The change summary narrowed to part of the change: its files (depot paths) and its findings."""
+    part = about.model_copy(deep=True)
+    part.tree = [AboutDir(dir=d.dir, files=[f for f in d.files if f.path in files]) for d in part.tree]
+    part.tree = [d for d in part.tree if d.files]
+    part.why = [w for w in part.why if w.finding in mine] or [AboutWhy(severity=f.severity, text=f.title, finding=f.id)
+                                                               for f in findings if f.id in mine][:4]
+    part.drift = [d for d in part.drift if set(d.files or []) & files]
+    return part
+
+
 def _overview(x: _Ctx, res, about: About, depots: dict[str, str], flows: list[Flow]) -> Overview:
     infos = []
     for cl in res.clusters:
```

`backend/codetortoise/substitutions.py`:

```python
"""Repeated edits (spec 2026-10-04-change-stories §2.1): changed lines whose only difference is one run of tokens.

A pair of lines (one removed, one added, in the same hunk) is a substitution when, split into C tokens, they differ in
exactly one run of consecutive tokens: `git_vector_free` → `git_vector_dispose`. A function is explained by
substitutions when every changed line in it is part of such a pair.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

_TOKEN = re.compile(r"""
    "(?:\\.|[^"\\])*"            # string literal
  | '(?:\\.|[^'\\])*'            # character literal
  | [A-Za-z_]\w*                 # identifier or keyword
  | \d[\w.]*                     # number
  | ->|\+\+|--|<<=|>>=|<<|>>|<=|>=|==|!=|&&|\|\||[-+*/%&|^]=|::|\.\.\.
  | \S                           # any other punctuation
""", re.X)
_COMMENT = re.compile(r"//.*$|/\*.*?\*/", re.S)


def tokens(line: str) -> list[str]:
    """C tokens of one line, comments and whitespace left out (a comment opened on the line runs to its end)."""
    code = _COMMENT.sub(" ", line)
    if "/*" in code:
        code = code[:code.index("/*")]
    return _TOKEN.findall(code)


@dataclass(frozen=True)
class Sub:
    old: str
    new: str


@dataclass(frozen=True)
class Site:
    """One substituted line pair: lines are 1-based in the before and after text."""
    sub: Sub
    before_line: int
    after_line: int
    before: str
    after: str


def substitution(old: str, new: str) -> Sub | None:
    """The one run of tokens that differs between two lines, or None (equal, or different in more than one place)."""
    a, b = tokens(old), tokens(new)
    ops = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    if len(ops) != 1 or ops[0][0] != "replace":    # equal, different in two places, or a token inserted or deleted
        return None
    _, i1, i2, j1, j2 = ops[0]
    return Sub(" ".join(a[i1:i2]), " ".join(b[j1:j2]))


def changed_pairs(before: list[str], after: list[str]) -> tuple[list[Site], int]:
    """Substituted line pairs between two texts (lists of lines), and how many changed lines were left unexplained."""
    sites, unexplained = [], 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "replace" or i2 - i1 != j2 - j1:
            unexplained += (i2 - i1) + (j2 - j1)
            continue
        for k in range(i2 - i1):
            s = substitution(before[i1 + k], after[j1 + k])
            if s is None:
                if tokens(before[i1 + k]) != tokens(after[j1 + k]):     # a whitespace-only change explains itself
                    unexplained += 2
                continue
            sites.append(Site(s, i1 + k + 1, j1 + k + 1, before[i1 + k].strip(), after[j1 + k].strip()))
    return sites, unexplained


def explained(before: list[str], after: list[str]) -> list[Site] | None:
    """The function's substitutions when every changed line is part of one, else None."""
    sites, unexplained = changed_pairs(before, after)
    return sites if sites and not unexplained else None
```

`backend/codetortoise/stories.py`:

```python
"""A review told as a few stories (spec 2026-10-04-change-stories §2–§3).

Mechanical stories are repeated edits (one substitution in at least two functions). Behaviour stories start from the
changed functions that cause flows (and from the flows of a repeated edit); the rest of the changed code joins the
nearest of them, or forms "Other changes" by connection. Changed test code forms one Tests story. Each story keeps a
board of every node it mentions (for its steps and code) and a graph of at most `story_graph_nodes` nodes.
"""
from __future__ import annotations

import posixpath
from collections import Counter, defaultdict, deque
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import (
    About,
    Board,
    BoardContext,
    BoardNode,
    Flow,
    Impact,
    StructField,
    _count,
    _Ctx,
    _neighbours,
    _render,
    about_for,
    build_about,
    build_flows,
    build_impacts,
)
from codetortoise.clusters import _shared, altered_access, cluster_change
from codetortoise.detectors.base import SEVERITY_RANK
from codetortoise.impact import ImpactModel
from codetortoise.substitutions import Site, Sub, changed_pairs

Kind = Literal["behaviour", "other", "mechanical", "tests"]
RISK = {3: "high", 2: "medium", 1: "low"}
NEIGHBOURS = 4                                               # unchanged code a story graph shows beside its own


class StoryRef(BaseModel):
    node: str
    label: str
    story: str | None = None


class StoryFunction(BaseModel):
    """A changed function of a story: what changed, in a few words, and how it relates to other stories."""
    node: str
    label: str
    note: str
    on_flow: bool = False
    also: list[str] = Field(default_factory=list)          # mechanical stories whose edit it also has
    calls: list[StoryRef] = Field(default_factory=list)    # a test: the changed code it calls


class StorySite(BaseModel):
    """One line of a repeated edit."""
    path: str | None                  # depot path
    line: int                         # new side
    function: str | None = None       # its function's label (None: outside functions)
    node: str | None = None
    before: str
    after: str
    test: bool = False
    effect: str | None = None         # the story of the flows its function causes
    other_edits: str | None = None    # its function has other edits too: the story it belongs to


class Story(BaseModel):
    id: str
    kind: Kind
    title: str
    summary: str
    text_source: Literal["template", "llm"] = "template"
    risk: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    nodes: list[str] = Field(default_factory=list)          # changed code whose home is this story
    flows: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    board: str | None = None                                # the cluster board holding its cause (None: one board)
    sub: list[str] | None = None                            # a mechanical story: [old, new]
    subs: list[list[str]] = Field(default_factory=list)     # "N more repeated edits": each substitution
    collapsed: bool = False                                 # a behaviour story past the list's limit


class StoryDetail(BaseModel):
    story: Story
    board: Board                                            # every node the story mentions, for steps and code
    graph: Board | None = None                              # at most story_graph_nodes nodes
    functions: list[StoryFunction] = Field(default_factory=list)
    sites: list[StorySite] = Field(default_factory=list)
    also_in: list[StoryRef] = Field(default_factory=list)   # a mechanical story: functions with other edits too


class StorySet(BaseModel):
    summary: str
    stories: list[Story] = Field(default_factory=list)
    node_story: dict[str, str] = Field(default_factory=dict)
    flow_story: dict[str, str] = Field(default_factory=dict)
    finding_story: dict[str, str] = Field(default_factory=dict)


def _q(s: str) -> str:
    return f"`{s}`"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


class _Draft:
    """A story while it is being built."""

    def __init__(self, kind: Kind, members: list[str] | None = None, flows: list[Flow] | None = None,
                 sub: Sub | None = None, cause: str | None = None):
        self.kind, self.members, self.flows, self.sub, self.cause = kind, list(members or []), list(flows or []), sub, cause
        self.findings: list[str] = []
        self.sites: list[tuple[Site, str, str | None]] = []   # (site, local file, node)
        self.subs: list[Sub] = []
        self.name = ""
        self.collapsed = False

    def rank(self, sev: dict[str, str]) -> tuple:
        f = max((SEVERITY_RANK.get(sev.get(i, "info"), 0) for i in self.findings), default=0)
        fl = max((SEVERITY_RANK.get(x.severity, 0) for x in self.flows), default=0)
        return (-f, -fl, -len(self.flows), -len(self.members))

    def risk(self, sev: dict[str, str]) -> str | None:
        top = max([SEVERITY_RANK.get(sev.get(i, "info"), 0) for i in self.findings]
                  + [SEVERITY_RANK.get(x.severity, 0) for x in self.flows], default=0)
        return RISK.get(top)


def build_stories(c: BoardContext, home: dict[str, str] | None = None) -> tuple[StorySet, dict[str, StoryDetail]]:
    """The review's stories and each story's detail. `home` maps nodes to the cluster boards holding them."""
    x = _Ctx(c)
    impacts = build_impacts(x)
    flows = build_flows(x, impacts)
    im, cfg = x.im, c.cfg
    sev = {f.id: f.severity for f in c.findings}
    changed = [n for n in im.changed if n in im.nodes]
    is_test = x.is_test_path

    # 1. substitutions: in each changed function, and outside functions
    fn_sites: dict[str, list[Site]] = {}
    fn_explained: dict[str, bool] = {}
    for nid in changed:
        if im.nodes[nid].kind != "function":
            continue
        spans = _spans(x, nid)
        if not spans:
            continue
        all_sites, unexplained = [], 0
        for fc, (b0, b1), (a0, a1) in spans:
            sites, u = changed_pairs(fc.before.splitlines()[b0 - 1:b1], fc.after.splitlines()[a0 - 1:a1])
            all_sites += [Site(s.sub, s.before_line + b0 - 1, s.after_line + a0 - 1, s.before, s.after) for s in sites]
            unexplained += u
        fn_sites[nid] = all_sites
        fn_explained[nid] = bool(all_sites) and not unexplained
    outside: list[tuple[Site, str]] = []
    for fc in c.cs.files:
        if fc.action != "edit":
            continue
        inside_a = [(f.start_line, f.end_line) for fx in c.after for f in fx.functions if f.file == fc.local]
        inside_b = [(f.start_line, f.end_line) for fx in c.before for f in fx.functions if f.file == fc.local]
        sites, _ = changed_pairs(fc.before.splitlines(), fc.after.splitlines())
        for s in sites:
            if not any(lo <= s.after_line <= hi for lo, hi in inside_a) and not any(lo <= s.before_line <= hi
                                                                                   for lo, hi in inside_b):
                outside.append((s, fc.local))

    fns_of: dict[Sub, set[str]] = defaultdict(set)
    for nid, sites in fn_sites.items():
        if fn_explained[nid]:
            for s in sites:
                fns_of[s.sub].add(nid)
    count: Counter[Sub] = Counter(s.sub for sites in fn_sites.values() for s in sites)
    count.update(s.sub for s, _ in outside)
    mech_subs = {s for s, fns in fns_of.items() if len(fns) >= 2}
    mech_of: dict[str, Sub] = {}                              # mechanical function -> its story's substitution
    for nid, sites in fn_sites.items():
        subs = {s.sub for s in sites}
        if fn_explained[nid] and subs <= mech_subs:
            mech_of[nid] = max(subs, key=lambda s: (count[s], s.old, s.new))

    mech = {s: _Draft("mechanical", sub=s) for s in sorted(mech_subs, key=lambda s: (-count[s], s.old, s.new))}
    for nid, s in mech_of.items():
        mech[s].members.append(nid)
    for nid, sites in fn_sites.items():
        for s in sites:
            if s.sub in mech:
                mech[s.sub].sites.append((s, x.local(nid) or "", nid))
    for s, local in outside:
        if s.sub in mech:
            mech[s.sub].sites.append((s, local, None))

    # 2. behaviour seeds: a flow-causing function's flows; a repeated edit's flows
    seeds: dict[object, _Draft] = {}
    for fl in flows:
        cause = fl.cause or fl.path[-1]
        key = ("mech", mech_of[cause]) if cause in mech_of else ("cause", cause)
        if key not in seeds:
            seeds[key] = (_Draft("behaviour", sub=key[1]) if key[0] == "mech"
                          else _Draft("behaviour", members=[cause], cause=cause))
        seeds[key].flows.append(fl)
        if key[0] == "mech" and cause not in seeds[key].members:
            seeds[key].members.append(cause)
    for d in seeds.values():
        d.findings = sorted({f for fl in d.flows for f in fl.findings})

    # 3. join the rest of the changed code to the nearest seed; "Other changes" for what no seed reaches
    tests = [n for n in changed if is_test(n) and n not in mech_of]
    seeded = {d.cause for d in seeds.values() if d.cause}
    rest = [n for n in changed if n not in mech_of and n not in seeded and n not in tests]
    walk = set(rest) | seeded
    adj: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if e.kind in ("call", "virtual") and e.src in walk and e.dst in walk:
            adj[e.src].add(e.dst)
            adj[e.dst].add(e.src)
    by_field: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if altered_access(e) and e.src in walk:
            by_field[e.dst].add(e.src)
    for fns in by_field.values():
        for a in fns:
            adj[a] |= fns - {a}
    seed_list = sorted((d for d in seeds.values() if d.cause), key=lambda d: d.rank(sev))
    best: dict[str, tuple[int, int]] = {}                   # node -> (hops, seed index)
    queue = deque()
    for i, d in enumerate(seed_list):
        best[d.cause] = (0, i)
        queue.append(d.cause)
    while queue:
        n = queue.popleft()
        hops, i = best[n]
        for m in sorted(adj[n]):
            if m not in best or (hops + 1, i) < best[m]:
                if m not in best:
                    queue.append(m)
                best[m] = (hops + 1, i)
    for n in rest:
        if n in best:
            seed_list[best[n][1]].members.append(n)
    unreached = [n for n in rest if n not in best]
    others: list[_Draft] = []
    if unreached:
        sub_im = ImpactModel(nodes=im.nodes, edges=im.edges, changed=unreached, blast=[])
        res = cluster_change(sub_im, [], [], is_test=lambda _: False, module_of=x.module_of, max_nodes=cfg.board_max_nodes,
                             min_changed=cfg.cluster_min_changed, max_clusters=10 ** 6)     # split as boards are
        for cl in res.clusters:
            others.append(_Draft("other", members=list(cl.members)))
    test_story = _Draft("tests", members=tests) if tests else None

    behaviour = list(seeds.values())
    drafts = behaviour + others + list(mech.values()) + ([test_story] if test_story else [])
    node_draft: dict[str, _Draft] = {n: d for d in drafts if d.kind != "behaviour" or d.cause for n in d.members}
    for nid, s in mech_of.items():
        node_draft[nid] = mech[s]

    # 4. findings: the story of their flow, else of their first node with a story
    flow_draft = {fl.id: d for d in behaviour for fl in d.flows}
    taken = {f for d in behaviour for f in d.findings}
    for f in c.findings:
        if f.id in taken:
            continue
        d = next((flow_draft[fl.id] for fl in flows if f.id in fl.findings and fl.id in flow_draft), None)
        for n in f.nodes:
            if d is not None:
                break
            if n in node_draft:
                d = node_draft[n]
            elif n in im.nodes and im.nodes[n].kind == "field":
                d = next((node_draft[e.src] for e in im.edges if e.dst == n and altered_access(e) and e.src in node_draft),
                         None)
        d = d or (drafts[0] if drafts else None)
        if d is not None:
            d.findings.append(f.id)

    # 5. order and the list's limit
    behaviour.sort(key=lambda d: d.rank(sev))
    others.sort(key=lambda d: d.rank(sev))
    mechs = list(mech.values())
    cap = cfg.max_stories

    def total() -> int:
        return len(behaviour) + len(others) + len(mechs) + (1 if test_story else 0)

    def home_dir(d: _Draft) -> str:
        return Counter(posixpath.dirname(x.local(m) or "") for m in d.members).most_common(1)[0][0]

    while total() > cap and len(others) > 1:                 # the least risky "Other changes" merge by directory
        small = others.pop()
        into = max(others, key=lambda o: (len(_shared(home_dir(o), home_dir(small))), -others.index(o)))
        into.members += small.members
        into.findings += small.findings
    if total() > cap and len(mechs) > 1:                     # the smallest repeated edits fold into one story
        keep = max(1, len(mechs) - (total() - cap) - 1)
        folded = _Draft("mechanical")
        for d in mechs[keep:]:
            folded.members += d.members
            folded.sites += d.sites
            folded.findings += d.findings
            folded.subs.append(d.sub)
        mechs = mechs[:keep] + [folded]
    if total() > cap:                                        # behaviour stories are never merged: collapse the rest
        room = max(0, cap - (total() - len(behaviour)) - 1)  # "N more behaviour stories" is one entry too
        for d in behaviour[room:]:
            d.collapsed = True

    for d in others:                                         # "in <directory>"; alike ones add their first function
        d.name = _dir_name(x, d.members, c.root)
    alike = Counter(d.name for d in others)
    for d in others:
        if alike[d.name] > 1:
            d.name += f" ({_q(x.label(d.members[0]))})"
    ordered = behaviour + others + mechs + ([test_story] if test_story else [])
    ids = {id(d): f"S{i + 1}" for i, d in enumerate(ordered)}

    # 6. the stories, their boards and graphs
    all_locals = set()
    for d in ordered:
        all_locals |= ({x.local(n) for n in _mentioned(d)} | {i.path for i in impacts if i.node in _mentioned(d)}
                       | {loc for _, loc, _ in d.sites})                # a repeated edit's sites outside functions too
    depots = c.depots_for(sorted(p for p in all_locals if p))
    about = build_about(c)
    node_story: dict[str, str] = {}
    for d in ordered:
        for n in d.members:
            node_story.setdefault(n, ids[id(d)])
    for nid, s in mech_of.items():
        node_story[nid] = ids[id(next(d for d in mechs if s == d.sub or s in d.subs))]
    for d in behaviour:
        for fl in d.flows:
            for n in fl.path:
                node_story.setdefault(n, ids[id(d)])
    effect_of = {d.sub: ids[id(d)] for d in behaviour if d.sub is not None}
    for d in behaviour:
        for fl in d.flows:
            if fl.cause in mech_of:
                effect_of.setdefault(fl.cause, ids[id(d)])

    stories, details = [], {}
    changed_lines = sum(_count(f.before, f.after)[0] for f in c.cs.files if f.action == "edit")
    for d in ordered:
        sid = ids[id(d)]
        st = _story(x, d, sid, sev, home, depots, is_test, effect_of)
        stories.append(st)
        details[sid] = _detail(x, d, st, impacts, depots, about, cfg.story_graph_nodes, node_story, mech_of, ids, mechs,
                               fn_sites, effect_of, is_test)
    summary = _summary(mechs, behaviour, others, test_story, changed_lines)
    flow_story = {fl.id: ids[id(d)] for d in behaviour for fl in d.flows}
    finding_story = {f: ids[id(d)] for d in ordered for f in d.findings}
    return StorySet(summary=summary, stories=stories, node_story=node_story, flow_story=flow_story,
                    finding_story=finding_story), details


def _spans(x: _Ctx, nid: str) -> list[tuple]:
    """A changed function's (file, before lines, after lines), from the diff map: a function defined twice in one file
    (under #ifdef) is the definition that changed, not the first the facts list."""
    n = x.im.nodes[nid]
    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
    if fb is None or fa is None:
        return []
    texts = {f.local: f for f in x.c.cs.files}
    out = [(texts[d.file], d.before_lines, d.after_lines) for d in x.c.dm.functions
           if d.qualname == fa.qualname and d.file in (fa.file, fb.file) and d.before_lines and d.after_lines
           and d.file in texts]
    if not out and fa.file in texts:
        out = [(texts[fa.file], (fb.start_line, fb.end_line), (fa.start_line, fa.end_line))]
    return out


def _mentioned(d: _Draft) -> list[str]:
    out = dict.fromkeys(d.members)
    for fl in d.flows:
        out.update(dict.fromkeys(fl.path))
    return list(out)


def _dir_name(x: _Ctx, members: list[str], root: str) -> str:
    """Their common directory, workspace-relative; code spread over the workspace is named by its main directories."""
    r = root.rstrip("/") + "/"
    dirs = [posixpath.dirname(x.local(m) or "") for m in members]
    rel = [(d + "/")[len(r):].rstrip("/") for d in dirs if (d + "/").startswith(r)]
    common = posixpath.commonpath(rel) if rel and len(rel) == len(dirs) and all(rel) else ""
    if rel and len(rel) == len(dirs) and not any(rel):
        return _q("the workspace root")
    if common:
        return _q(common)
    top = [d or "the workspace root" for d, _ in Counter(rel).most_common()]     # never an absolute path
    if not top:
        return "the workspace"
    return ", ".join(_q(d) for d in top[:2]) + (f" and {_plural(len(top) - 2, 'more directory', 'more directories')}"
                                                if len(top) > 2 else "")


def _labels(x: _Ctx, ids: list[str], most: int = 2) -> str:
    names = [_q(x.label(i)) for i in ids[:most]]
    return ", ".join(names) + (f" and {len(ids) - most} more" if len(ids) > most else "")


def _story(x: _Ctx, d: _Draft, sid: str, sev: dict[str, str], home: dict[str, str] | None, depots: dict[str, str],
           is_test, effect_of) -> Story:
    files = {depots.get(x.local(n)) or x.local(n) for n in d.members} | {depots.get(loc) or loc for _, loc, _ in d.sites}
    counts = {"flows": len(d.flows), "findings": len(d.findings), "functions": len(d.members), "files": len(files - {None, ""})}
    key = d.cause or (d.members[0] if d.members else None)
    board = (home or {}).get(key) if key else None
    if d.kind == "mechanical":
        n_sites = len(d.sites)
        tests = sum(1 for s, loc, nid in d.sites if (is_test(nid) if nid else "/test" in loc))
        counts.update(sites=n_sites, test_sites=tests)
        in_tests = f" ({tests} in tests)" if tests else ""
        if d.sub is None:
            title = f"{_plural(len(d.subs), 'more repeated edit')}: {n_sites} sites"
            summary = "Each is one token change repeated across functions: " + "; ".join(
                f"{_q(s.old)} → {_q(s.new)}" for s in d.subs[:4]) + ("…" if len(d.subs) > 4 else "") + ". Skim them."
        else:
            title = f"{_q(d.sub.old)} → {_q(d.sub.new)} at {n_sites} sites in {_plural(counts['files'], 'file')}{in_tests}"
            summary = (f"Every changed line in these {_plural(len(d.members), 'function')} is this one edit. Skim them"
                       + (f"; what it changes is in {effect_of[d.sub]}." if d.sub in effect_of else "."))
        return Story(id=sid, kind="mechanical", title=title, summary=summary, risk=d.risk(sev), counts=counts,
                     nodes=d.members, findings=d.findings, board=board,
                     sub=[d.sub.old, d.sub.new] if d.sub else None, subs=[[s.old, s.new] for s in d.subs])
    if d.kind == "tests":
        title = "Tests"
        summary = f"{_plural(len(d.members), 'test function')} changed in {_plural(counts['files'], 'file')}."
    elif d.kind == "other":
        title = f"Other changes in {d.name}"
        summary = _other_summary(x, d.members)
    else:
        title, summary = _behaviour_text(x, d)
    return Story(id=sid, kind=d.kind, title=title, summary=summary, risk=d.risk(sev), counts=counts, nodes=d.members,
                 flows=[fl.id for fl in d.flows], findings=d.findings, board=board, collapsed=d.collapsed)


def _other_summary(x: _Ctx, members: list[str]) -> str:
    """"New: `a`, `b`. Removed: `c`. Changed: `d` and 2 more." """
    groups: dict[str, list[str]] = {"New": [], "Removed": [], "Changed": []}
    for n in members:
        fb, fa = x.fb.get(x.im.nodes[n].key), x.fa.get(x.im.nodes[n].key)
        groups["New" if fb is None and fa is not None else "Removed" if fa is None and fb is not None else "Changed"].append(n)
    return " ".join(f"{k}: {_labels(x, v, 3)}." for k, v in groups.items() if v)


def _effect(fl: Flow) -> str:
    """state, signature, ignored or unhandled (from the flow's text, as board.build_flows writes it)."""
    if fl.tag == "state":
        return "state"
    tail = fl.text.rsplit("⟶", 1)[-1].strip()
    return "signature" if tail == "signature changed" else "ignored" if tail.endswith(" ignored") else "unhandled"


def _behaviour_text(x: _Ctx, d: _Draft) -> tuple[str, str]:
    first = d.flows[0]
    kind = _effect(first)
    same = [fl for fl in d.flows if _effect(fl) == kind]
    lands = list(dict.fromkeys(x.label(fl.lands) for fl in same))
    who = _q(lands[0]) + (f" and {len(lands) - 1} more" if len(lands) > 1 else "")
    extra = len(d.flows) - len(same)
    tail = f" ({_plural(extra, 'more effect')})" if extra else ""
    cause = _q(x.label(d.cause)) if d.cause else ""
    if d.sub is not None:
        lands = list(dict.fromkeys(x.label(fl.lands) for fl in d.flows))
        who = _q(lands[0]) + (f" and {len(lands) - 1} more" if len(lands) > 1 else "")
        title = f"What {_q(d.sub.old)} → {_q(d.sub.new)} changes: {who} see{'s' if len(lands) == 1 else ''} new values"
    elif kind == "state":
        field = next((x.label(n) for n in first.path if x.im.nodes[n].kind == "field"), "a field")
        title = f"{cause} now writes {_q(field)}; {who} read{'s' if len(lands) == 1 else ''} it{tail}"
    elif kind == "signature":
        title = f"{cause}'s signature changed; {who} call{'s' if len(lands) == 1 else ''} it{tail}"
    else:
        vals = first.text.rsplit("⟶", 1)[-1].strip().rsplit(" ", 1)[0]
        verb = "ignore" if kind == "ignored" else "don't handle"
        verb = (verb + "s" if kind == "ignored" else "doesn't handle") if len(lands) == 1 else verb
        title = f"{cause} can now return {vals}; {who} {verb} it{tail}"
    summary = first.what + (f" {_plural(len(d.flows) - 1, 'more flow')} in this story." if len(d.flows) > 1 else "")
    return title, summary


def _summary(mechs: list[_Draft], behaviour: list[_Draft], others: list[_Draft], tests: _Draft | None,
             changed_lines: int) -> str:
    sites = sum(len(d.sites) for d in mechs)
    if mechs and changed_lines and sites * 2 >= changed_lines:
        top = mechs[0]
        what = f" ({_q(top.sub.old)} → {_q(top.sub.new)})" if top.sub else ""
        edits = "one edit" if len(mechs) == 1 and top.sub else _plural(len(mechs), "repeated edit")
        return f"Mostly mechanical: {sites} of {changed_lines} changed lines are {edits}{what}."
    n_tests = len(tests.members) if tests else 0
    parts = [_plural(len(behaviour), "behaviour story", "behaviour stories") if behaviour else "",
             _plural(len(mechs), "repeated edit") if mechs else "",
             _plural(sum(len(d.members) for d in others), "other changed function") if others else "",
             _plural(n_tests, "test change") if n_tests else ""]
    return (", ".join(p for p in parts if p) or "No changed functions") + "."


def _note(x: _Ctx, nid: str, mech_of: dict[str, Sub], fn_sites: dict[str, list[Site]], mech_subs: set) -> str:
    """What changed in a node, in a few words."""
    n = x.im.nodes[nid]
    if nid not in x.changed:
        return ""
    if nid in mech_of:
        s = mech_of[nid]
        return f"{_q(s.new)} instead of {_q(s.old)}"
    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
    parts = []
    if fb is None and fa is not None:
        parts.append("new function")
    elif fa is None and fb is not None:
        parts.append("removed")
    else:
        ch = next((d for d in x.c.dm.functions if fa and d.file == fa.file and d.qualname == fa.qualname), None)
        if ch is not None and ch.kind == "signature_changed":
            parts.append("signature changed")
    for status, verb in (("added", "now writes"), ("removed", "no longer writes")):
        fields = [x.label(e.dst).split("::")[-1] for e in x.im.edges if e.src == nid and e.kind == "writes"
                  and e.status == status and e.dst in x.im.nodes]
        if fields:
            parts.append(f"{verb} {', '.join(dict.fromkeys(fields[:3]))}" + (f" +{len(fields) - 3}" if len(fields) > 3 else ""))
    also = sorted({s.sub for s in fn_sites.get(nid, []) if s.sub in mech_subs}, key=lambda s: s.old)
    if also:
        parts.append("also " + ", ".join(f"{_q(s.old)} → {_q(s.new)}" for s in also[:2]))
    if not parts:
        add = rem = 0
        for fc, _, (a0, a1) in _spans(x, nid):
            a, r = _count(fc.before, fc.after, a0, a1)
            add, rem = add + a, rem + r
        parts.append(f"+{add} −{rem} lines" if add or rem else "layout only")
    return "; ".join(parts)


def _landing_note(impacts: list[Impact], nid: str) -> str:
    i = next((i for i in impacts if i.node == nid and i.landing), None)
    if i is None:
        return ""
    text = i.text if len(i.text) <= 60 else i.text[:57] + "…"
    return f"⚠ {text}"


def _detail(x: _Ctx, d: _Draft, st: Story, impacts: list[Impact], depots: dict[str, str], about: About, cap: int,
            node_story: dict[str, str], mech_of: dict[str, Sub], ids: dict[int, str], mechs: list[_Draft],
            fn_sites: dict[str, list[Site]], effect_of: dict, is_test) -> StoryDetail:
    mech_subs = {m.sub for m in mechs if m.sub is not None} | {s for m in mechs for s in m.subs}
    mention = [n for n in _mentioned(d) if n in x.im.nodes]
    files = {depots.get(x.local(n)) for n in d.members if x.local(n)} - {None}
    part = about_for(about, files, set(d.findings), x.c.findings)
    board = _render(x, impacts, d.flows, mention, depots, hidden=0, about=part)
    on_flow = {n for fl in d.flows for n in fl.path}
    for bn in board.nodes:
        bn.note = _note(x, bn.id, mech_of, fn_sites, mech_subs) or (_landing_note(impacts, bn.id) if bn.id in on_flow
                                                                     else "") or None
    mech_story = {s: ids[id(m)] for m in mechs for s in ([m.sub] if m.sub else m.subs)}
    functions = []
    for n in d.members:
        if x.im.nodes[n].kind != "function":
            continue
        also = sorted({mech_story[s.sub] for s in fn_sites.get(n, []) if s.sub in mech_story and n not in mech_of})
        calls = ([StoryRef(node=m, label=x.label(m), story=node_story.get(m)) for m in sorted(x.callees.get(n, ()))
                  if m in x.changed and not is_test(m)] if d.kind == "tests" else [])
        functions.append(StoryFunction(node=n, label=x.label(n), note=_note(x, n, mech_of, fn_sites, mech_subs),
                                       on_flow=n in on_flow, also=also, calls=calls))
    detail = StoryDetail(story=st, board=board, functions=functions)
    if d.kind == "mechanical":
        own = {d.sub} if d.sub else set(d.subs)
        for s, local, nid in sorted(d.sites, key=lambda t: (t[1], t[0].after_line)):
            other = node_story.get(nid) if nid and nid not in mech_of else None
            detail.sites.append(StorySite(
                path=depots.get(local), line=s.after_line, function=x.label(nid) if nid else None, node=nid,
                before=s.before, after=s.after, test=is_test(nid) if nid else "/test" in local,
                effect=effect_of.get(nid) if nid else None, other_edits=other))
        partial = sorted({nid for s, _, nid in d.sites if nid and nid not in mech_of and s.sub in own})
        detail.also_in = [StoryRef(node=n, label=x.label(n), story=node_story.get(n)) for n in partial]
    elif d.kind in ("behaviour", "other"):
        detail.graph = _graph(x, d, impacts, depots, part, cap, board)
    return detail


def _record(x: _Ctx, nid: str) -> str | None:
    """A field's struct, by name: two anonymous structs named alike (a macro's, in two places) are drawn as one."""
    n = x.im.nodes[nid]
    return n.label.rsplit("::", 1)[0] if n.kind == "field" and "::" in n.label else None


def _graph(x: _Ctx, d: _Draft, impacts: list[Impact], depots: dict[str, str], about: About, cap: int,
           full: Board) -> Board:
    """At most `cap` nodes: the cause, the flows' paths, the story's other changed code, then neighbours; the fields of
    one struct count once (by its name); up to NEIGHBOURS unchanged neighbours; a story with more shows "+N more
    changed functions"."""
    order: dict[str, None] = {}
    if d.cause:
        order[d.cause] = None
    for fl in d.flows:
        order.update(dict.fromkeys(n for n in fl.path if n in x.im.nodes))
    order.update(dict.fromkeys(n for n in d.members if n in x.im.nodes))
    required = list(order)
    slot = lambda n: _record(x, n) or n                      # noqa: E731
    first = set(d.flows[0].path) if d.flows else set()
    slots: set[str] = set()
    chosen: list[str] = []
    over = len({slot(n) for n in required}) > cap
    for n in required:
        if slot(n) in slots or n in first or n == d.cause:
            pass
        elif len(slots) >= (cap - 1 if over else cap):
            continue
        chosen.append(n)
        slots.add(slot(n))
    more = [n for n in d.members if n not in set(chosen) and x.im.nodes[n].kind == "function"]
    if not over:
        room = min(cap, len(slots) + NEIGHBOURS)
        for n in _neighbours(x, impacts, set(d.members)):
            if len(slots) >= room:
                break
            if n not in set(chosen) and (slot(n) in slots or len(slots) < room):
                chosen.append(n)
                slots.add(slot(n))
    sel = set(chosen)
    shown = [fl.model_copy(deep=True) for fl in d.flows if set(fl.path) <= sel]
    g = _render(x, impacts, shown, chosen, depots, hidden=0, about=about)
    notes = {bn.id: bn.note for bn in full.nodes}
    for bn in g.nodes:
        bn.note = notes.get(bn.id)
    # one node per struct: its fields listed inside it
    rep: dict[str, str] = {}
    to: dict[str, str] = {}
    keep = []
    for bn in g.nodes:
        rec = _record(x, bn.id) if bn.kind == "field" else None
        if rec is None:
            keep.append(bn)
            continue
        if rec not in rep:
            rep[rec] = bn.id
            head = bn.model_copy(update={"kind": "struct", "label": bn.label.rsplit("::", 1)[0], "fields": [], "note": None})
            keep.append(head)
        head = next(k for k in keep if k.id == rep[rec])
        to[bn.id] = head.id
        if all(f.label != bn.label.rsplit("::", 1)[-1] for f in head.fields):
            head.fields.append(StructField(id=bn.id, label=bn.label.rsplit("::", 1)[-1]))
    g.nodes = keep
    seen, edges = set(), []
    for e in g.edges:
        e2 = e.model_copy(update={"src": to.get(e.src, e.src), "dst": to.get(e.dst, e.dst)})
        k = (e2.src, e2.dst, e2.kind)
        if e2.src != e2.dst and k not in seen:
            seen.add(k)
            edges.append(e2)
    g.edges = edges
    for fl in g.flows:
        path = [to.get(n, n) for n in fl.path]
        fl.path = [n for i, n in enumerate(path) if i == 0 or n != path[i - 1]]
        fl.lands, fl.fx_at = to.get(fl.lands, fl.lands), to.get(fl.fx_at, fl.fx_at) if fl.fx_at else None
    for i in g.impacts:
        i.node = to.get(i.node, i.node)
    if more:
        g.nodes.append(BoardNode(id="more", key="more", label=f"+{_plural(len(more), 'more changed function')}",
                                 kind="more", layer=min((n.layer or 0) for n in g.nodes) if g.nodes else 0))
    return g
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_substitutions.py tests/test_stories.py -q`
Expected: `27 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `413 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/board.py backend/codetortoise/substitutions.py backend/codetortoise/stories.py backend/tests/test_substitutions.py backend/tests/test_stories.py
git commit -m "feat(stories): tell a change as stories — repeated edits, behaviour, other changes, tests — with small graphs"
```

---

### Task 3: Stories stored with the boards and served over HTTP

Spec §4, §6, §7. The board stage builds the stories right after the boards; if that raises, the review keeps its
boards and the stage notes "stories failed: <error>". `boardstore.save` writes the blobs `stories` and `story:S<n>` in
the same transaction as the boards and deletes stale `story:` blobs (a re-run with fewer stories, or none).
`put_story` rewrites one story and its entry in the list (the AI pass in Task 4 uses it).

`GET /api/reviews/{rid}/stories` returns the list; a review without stories answers 404 "this review has no stories:
re-run it". `GET …/stories/{sid}` returns the story with its board and graph tagged with files and layer names;
`?expand=N12:callers` grows the graph as boards grow; an unknown story is 404 "That story no longer exists after the
re-run.". `GET …/locate` now returns `{"cluster", "story"}`; on a review shown as one board a node no board holds
gives `{"cluster": null, "story": null}`. The lab README records the stories of three libgit2 changes.

**Files:**
- Modify: `backend/codetortoise/boardstore.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/web/app.py`
- Modify: `lab/README.md`
- Modify: `backend/tests/test_boardstore.py`
- Modify: `backend/tests/test_web.py`
- Modify: `backend/tests/test_large_change.py`

**Interfaces:**
- Consumes: `stories.StorySet`, `StoryDetail`, `build_stories`, `BoardSet.stories`, `.story_details` (Task 2).
- Produces: `boardstore.STORY = "story:"`, `stories(store, rid) -> StorySet | None`,
  `story(store, rid, sid) -> StoryDetail | None`, `put_story(store, rid, d)`; HTTP `GET …/stories`,
  `GET …/stories/{sid}?expand=`, `GET …/locate` → `{cluster, story}`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_boardstore.py`:

```diff
diff --git a/backend/tests/test_boardstore.py b/backend/tests/test_boardstore.py
index a7c2cb2..af09b65 100644
--- a/backend/tests/test_boardstore.py
+++ b/backend/tests/test_boardstore.py
@@ -45,3 +45,36 @@ def test_a_save_that_fails_part_way_keeps_the_earlier_boards(tmp_path):
     bs = boardstore.boards(store, rid)
     assert set(bs) == {"C1", "C2"} and {b.about.intent for b in bs.values()} == {"old"}
     assert boardstore.overview(store, rid).about.intent == "old"
+
+
+def _with_stories(n: int) -> BoardSet:
+    from codetortoise.stories import Story, StoryDetail, StorySet
+    bs = BoardSet(board=Board(about=About(intent="i")))
+    sts = [Story(id=f"S{i}", kind="other", title=f"t{i}", summary="s") for i in range(1, n + 1)]
+    bs.stories = StorySet(summary="x", stories=sts)
+    b = Board(about=About(intent="i"))
+    bs.story_details = {s.id: StoryDetail(story=s, board=b, graph=b) for s in sts}
+    return bs
+
+
+def test_stories_are_saved_with_the_boards_and_a_rerun_leaves_no_stale_story(tmp_path):
+    store = Store(tmp_path / "s.db")
+    rid = store.create_review("t", "owner", [1])
+    boardstore.save(store, rid, _with_stories(3), {})
+    assert [s.id for s in boardstore.stories(store, rid).stories] == ["S1", "S2", "S3"]
+    assert boardstore.story(store, rid, "S3").story.title == "t3"
+    boardstore.save(store, rid, _with_stories(2), {})
+    assert boardstore.story(store, rid, "S3") is None and store.blob_keys(rid, boardstore.STORY) == ["story:S1", "story:S2"]
+    boardstore.save(store, rid, BoardSet(board=Board(about=About(intent="i"))), {})     # stories failed this run
+    assert boardstore.stories(store, rid) is None and store.blob_keys(rid, boardstore.STORY) == []
+
+
+def test_put_story_rewrites_the_story_and_its_entry_in_the_list(tmp_path):
+    store = Store(tmp_path / "s.db")
+    rid = store.create_review("t", "owner", [1])
+    boardstore.save(store, rid, _with_stories(2), {})
+    d = boardstore.story(store, rid, "S2")
+    d.story.title, d.story.text_source = "better", "llm"
+    boardstore.put_story(store, rid, d)
+    assert [s.title for s in boardstore.stories(store, rid).stories] == ["t1", "better"]
+    assert boardstore.story(store, rid, "S2").story.text_source == "llm"
```

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index a822e97..f9ce17a 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -2,6 +2,7 @@ import pytest
 from fastapi.testclient import TestClient
 from helpers import make_services
 
+from codetortoise import boardstore
 from codetortoise.pipeline import JobRunner, run_review
 from codetortoise.web.app import create_app, make_authenticator
 
@@ -287,3 +288,39 @@ def test_session_cookie_is_secure_only_when_https_is_configured(fx, tmp_path):
     tls = TestClient(create_app(svc, InlineRunner(svc), make_authenticator(svc)))
     r = tls.post("/api/login", json={"user": "anoop", "password": "x"})
     assert "secure" in r.headers["set-cookie"].lower()
+
+
+def test_story_endpoints_serve_the_list_and_each_story(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    assert TestClient(app).get(f"/api/reviews/{rid}/stories").status_code == 401
+    assert TestClient(app).get(f"/api/reviews/{rid}/stories/S1").status_code == 401
+    ss = owner.get(f"/api/reviews/{rid}/stories").json()
+    assert ss["summary"] == "2 behaviour stories." and [s["id"] for s in ss["stories"]] == ["S1", "S2"]
+    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()
+    assert s1["story"]["title"].startswith("`uart_send` now writes `Uart::errors`")
+    assert len(s1["graph"]["nodes"]) <= 12 and s1["board"]["flows"]
+    assert all(n["path"] is None or n["path"].startswith("//") for n in s1["graph"]["nodes"])
+    send = next(n["id"] for n in s1["graph"]["nodes"] if n["label"] == "uart_send")
+    grown = owner.get(f"/api/reviews/{rid}/stories/S1", params={"expand": f"{send}:callers"}).json()
+    assert len(grown["graph"]["nodes"]) >= len(s1["graph"]["nodes"])
+    r = owner.get(f"/api/reviews/{rid}/stories/S9")
+    assert r.status_code == 404 and r.json()["detail"] == "That story no longer exists after the re-run."
+    svc.store.replace_blobs(rid, ["stories"], [boardstore.STORY], {})     # a review run before stories
+    for url in (f"/api/reviews/{rid}/stories", f"/api/reviews/{rid}/stories/S1"):
+        r = owner.get(url)
+        assert r.status_code == 404 and r.json()["detail"] == "this review has no stories: re-run it"
+
+
+def test_locate_names_the_story_of_a_node_flow_or_finding(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    ss = owner.get(f"/api/reviews/{rid}/stories").json()
+    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()
+    send = next(n["id"] for n in s1["board"]["nodes"] if n["label"] == "uart_send")
+    assert owner.get(f"/api/reviews/{rid}/locate", params={"node": send}).json() == {"cluster": None, "story": "S1"}
+    fl = ss["stories"][1]["flows"][0]
+    assert owner.get(f"/api/reviews/{rid}/locate", params={"flow": fl}).json() == {"cluster": None, "story": "S2"}
+    fid = ss["stories"][0]["findings"][0]
+    assert owner.get(f"/api/reviews/{rid}/locate", params={"finding": fid}).json()["story"] == "S1"
+    assert owner.get(f"/api/reviews/{rid}/locate", params={"node": "N999"}).json() == {"cluster": None, "story": None}
```

`backend/tests/test_large_change.py`:

```diff
diff --git a/backend/tests/test_large_change.py b/backend/tests/test_large_change.py
index 2c6f221..6ddc802 100644
--- a/backend/tests/test_large_change.py
+++ b/backend/tests/test_large_change.py
@@ -103,7 +103,7 @@ def test_the_small_fixture_has_no_overview(fx, tmp_path):
     rid = client.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
     assert client.get(f"/api/reviews/{rid}/board").status_code == 200
     assert client.get(f"/api/reviews/{rid}/overview").status_code == 404
-    assert client.get(f"/api/reviews/{rid}/locate", params={"node": "N1"}).json() == {"cluster": None}
+    assert client.get(f"/api/reviews/{rid}/locate", params={"node": "N1"}).json()["cluster"] is None
 
 
 def test_expanding_adds_callers_past_the_budget_and_counts_what_is_left(api):
@@ -133,10 +133,12 @@ def test_locate_finds_the_cluster_of_a_node_a_flow_and_a_finding(api):
     ov = owner.get(f"/api/reviews/{rid}/overview").json()
     c = ov["clusters"][1]
     loc = lambda **q: owner.get(f"/api/reviews/{rid}/locate", params=q)          # noqa: E731
-    assert loc(node=c["nodes"][0]).json() == {"cluster": c["id"]}
-    assert loc(finding=c["finding_ids"][0]).json() == {"cluster": c["id"]}
+    ss = owner.get(f"/api/reviews/{rid}/stories").json()
+    assert loc(node=c["nodes"][0]).json() == {"cluster": c["id"], "story": ss["node_story"][c["nodes"][0]]}
+    fid = c["finding_ids"][0]
+    assert loc(finding=fid).json() == {"cluster": c["id"], "story": ss["finding_story"][fid]}
     flow = owner.get(f"/api/reviews/{rid}/board", params={"cluster": c["id"]}).json()["flows"][0]["id"]
-    assert loc(flow=flow).json() == {"cluster": c["id"]}
+    assert loc(flow=flow).json() == {"cluster": c["id"], "story": ss["flow_story"][flow]}
     assert loc(node="N99999").status_code == 404
 
 
@@ -180,3 +182,16 @@ def test_the_overview_board_and_locate_need_a_signed_in_user(api):
     for path, params in ((f"/api/reviews/{rid}/overview", {}), (f"/api/reviews/{rid}/board", {"cluster": "C1"}),
                          (f"/api/reviews/{rid}/locate", {"node": "N1"})):
         assert anon.get(path, params=params).status_code == 401, path
+
+
+def test_a_large_change_is_told_in_at_most_15_stories_with_small_graphs(api):
+    svc, owner, rid = api
+    ss = owner.get(f"/api/reviews/{rid}/stories").json()
+    shown = [s for s in ss["stories"] if not s["collapsed"]]
+    collapsed_row = len(shown) < len(ss["stories"])           # "N more behaviour stories" is one entry
+    assert 1 <= len(shown) + collapsed_row <= svc.cfg.analysis.max_stories
+    for s in ss["stories"]:
+        d = owner.get(f"/api/reviews/{rid}/stories/{s['id']}").json()
+        assert d["graph"] is None or len(d["graph"]["nodes"]) <= svc.cfg.analysis.story_graph_nodes
+        assert not any(n["label"].startswith("/") or "(/" in n["label"] for n in d["board"]["nodes"])
+    assert set(ss["node_story"].values()) <= {s["id"] for s in ss["stories"]}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_boardstore.py tests/test_web.py tests/test_large_change.py -q`
Expected: FAIL — `6 failed, 32 passed` (`module 'codetortoise.boardstore' has no attribute 'stories'`, `assert 404 == 401` for `GET …/stories`, `KeyError: 'node_story'`, `KeyError: 'stories'`)

- [ ] **Step 3: Implement**

`backend/codetortoise/boardstore.py`:

```diff
diff --git a/backend/codetortoise/boardstore.py b/backend/codetortoise/boardstore.py
index 852ab43..25b6a7a 100644
--- a/backend/codetortoise/boardstore.py
+++ b/backend/codetortoise/boardstore.py
@@ -1,7 +1,8 @@
 """Where a review's boards live (spec 2026-10-03-large-change-boards §4).
 
 A review that fits on one board has the blob `board`. A split review has `overview`, one `board:C<n>` per cluster and
-`node_cluster` (node id -> cluster id). Everything that reads or rewrites boards (the pipeline's AI pass, on-demand
+`node_cluster` (node id -> cluster id). Every review run since change stories (spec 2026-10-04) also has `stories` and
+one `story:S<n>` per story. Everything that reads or rewrites boards (the pipeline's AI pass, on-demand
 explanations, the API) goes through here.
 """
 from __future__ import annotations
@@ -9,8 +10,10 @@ from __future__ import annotations
 from codetortoise.board import Board, BoardSet, Files, Overview
 from codetortoise.provenance import tag_board
 from codetortoise.store import Store
+from codetortoise.stories import StoryDetail, StorySet
 
 PREFIX = "board:"
+STORY = "story:"
 
 
 def save(store: Store, rid: int, bs: BoardSet, finding_files: dict[str, Files]) -> None:
@@ -20,7 +23,33 @@ def save(store: Store, rid: int, bs: BoardSet, finding_files: dict[str, Files])
     else:
         puts = {"overview": bs.overview, "node_cluster": bs.home}
         puts |= {PREFIX + cid: tag_board(b, finding_files) for cid, b in bs.clusters.items()}
-    store.replace_blobs(rid, ["board", "overview", "node_cluster"], [PREFIX], puts)
+    if bs.stories is not None:
+        puts["stories"] = bs.stories
+        for sid, d in bs.story_details.items():
+            tag_board(d.board, finding_files)
+            if d.graph is not None:
+                tag_board(d.graph, finding_files)
+            puts[STORY + sid] = d
+    store.replace_blobs(rid, ["board", "overview", "node_cluster", "stories"], [PREFIX, STORY], puts)
+
+
+def stories(store: Store, rid: int) -> StorySet | None:
+    raw = store.get_blob(rid, "stories")
+    return StorySet.model_validate(raw) if raw else None
+
+
+def story(store: Store, rid: int, sid: str) -> StoryDetail | None:
+    raw = store.get_blob(rid, STORY + sid)
+    return StoryDetail.model_validate(raw) if raw else None
+
+
+def put_story(store: Store, rid: int, d: StoryDetail) -> None:
+    """Store a story's detail and its entry in the list (an AI rewrite of its title and summary)."""
+    ss = stories(store, rid)
+    if ss is not None:
+        ss.stories = [d.story if s.id == d.story.id else s for s in ss.stories]
+        store.replace_blobs(rid, [], [], {"stories": ss, STORY + d.story.id: d})
+
 
 def overview(store: Store, rid: int) -> Overview | None:
     o = store.get_blob(rid, "overview")
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index d7cd707..0b7cd39 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -20,6 +20,7 @@ from codetortoise.llm.storyboard import build_storyboard
 from codetortoise.paths import canon
 from codetortoise.provenance import finding_files, impact_node_files, local_files
 from codetortoise.services import Services
+from codetortoise.stories import build_stories
 from codetortoise.swarm import SwarmError
 from codetortoise.tu_select import TuSelection, field_follow_up, select_tus
 from codetortoise.vcs.model import ChangeSet
@@ -218,8 +219,13 @@ def run_review(rid: int, svc: Services) -> None:
     def board():
         notes: list[str] = []
         resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
-        bs = build_boards(BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
-                                       ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root))))
+        bctx = BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
+                            ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root)))
+        bs = build_boards(bctx)
+        try:                                   # change stories (spec 2026-10-04); the boards stand without them
+            bs.stories, bs.story_details = build_stories(bctx, bs.home or None)
+        except Exception as e:
+            notes.append(f"stories failed: {type(e).__name__}: {e}")
         # file tags (spec §14.3): every graph node and finding, from one more lookup of the files not yet resolved
         findings, im = ctx["findings"], ctx["impact"]
         decl = {f"field:{a.field}": a.record_file for fx in ctx["before"] + ctx["after"] for a in fx.fields if a.record_file}
```

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index 009cae0..cde743b 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -223,6 +223,38 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         named(out.get("layers", []))
         return out
 
+    NO_STORIES = "this review has no stories: re-run it"
+
+    @app.get("/api/reviews/{rid}/stories")
+    def stories(rid: int, _: str = Depends(user_of)):
+        """The review told as stories (spec 2026-10-04-change-stories §2); 404 for a review run before them."""
+        review_or_404(rid)
+        ss = boardstore.stories(store, rid)
+        if ss is None:
+            raise HTTPException(404, NO_STORIES)
+        return ss.model_dump()
+
+    @app.get("/api/reviews/{rid}/stories/{sid}")
+    def story(rid: int, sid: str, expand: str | None = None, _: str = Depends(user_of)):
+        """One story: its board (every node it mentions) and its graph, grown by `expand` as boards are."""
+        review_or_404(rid)
+        d = boardstore.story(store, rid, sid)
+        if d is None:
+            if boardstore.stories(store, rid) is None:
+                raise HTTPException(404, NO_STORIES)
+            raise HTTPException(404, "That story no longer exists after the re-run.")
+        tags = {f.id: f.files for f in store.list_findings(rid)}
+        d.board = tag_board(d.board, tags)
+        if d.graph is not None:
+            d.graph = tag_board(d.graph, tags)
+            if expand:
+                d.graph = tag_board(expanded(rid, d.graph, expand), tags)
+        out = d.model_dump()
+        named(out["board"].get("layers", []))
+        if out["graph"]:
+            named(out["graph"].get("layers", []))
+        return out
+
     def expanded(rid: int, b: Board, expand: str) -> Board:
         """`expand` is "N12:callers,N9:callees": up to `analysis.expand_step` neighbours each, in order."""
         parts = expand.split(",")
@@ -254,26 +286,33 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
     @app.get("/api/reviews/{rid}/locate")
     def locate(rid: int, node: str | None = None, flow: str | None = None, finding: str | None = None,
                _: str = Depends(user_of)):
-        """The cluster to open for a node, flow or finding; null for a review shown as one board."""
+        """The cluster to open for a node, flow or finding (null for a review shown as one board), and its story."""
         review_or_404(rid)
+        ss = boardstore.stories(store, rid)
+        sid = None
+        if ss is not None:
+            sid = (ss.flow_story.get(flow) if flow else ss.finding_story.get(finding) if finding
+                   else ss.node_story.get(node) if node else None)
         ov = boardstore.overview(store, rid)
         if ov is None:
-            return {"cluster": None}
+            return {"cluster": None, "story": sid}
         if flow:
             held = boardstore.with_flow(store, rid, flow)
             if held:
-                return {"cluster": held[0]}
+                return {"cluster": held[0], "story": sid}
         elif finding:
             c = next((c for c in ov.clusters if finding in c.finding_ids), None)
             if c:
-                return {"cluster": c.id}
+                return {"cluster": c.id, "story": sid}
         elif node:
             home = (store.get_blob(rid, "node_cluster") or {}).get(node)
             if home:
-                return {"cluster": home}
+                return {"cluster": home, "story": sid}
             for cid, b in boardstore.boards(store, rid).items():
                 if any(n.id == node for n in b.nodes):
-                    return {"cluster": cid}
+                    return {"cluster": cid, "story": sid}
+        if sid:
+            return {"cluster": None, "story": sid}
         raise HTTPException(404, "not on any board of this review")
 
     @app.get("/api/reviews/{rid}/source")
```

`lab/README.md`:

````diff
diff --git a/lab/README.md b/lab/README.md
index 7532c87..4b12727 100644
--- a/lab/README.md
+++ b/lab/README.md
@@ -95,3 +95,27 @@ headless without an LLM, every board has at most 30 nodes:
 | 17 (shelved) | #7261 sha256 | 179 | 85 | 15 clusters |
 
 Each review takes 30–80 s. Facts are "degraded" on the older CLs: the workspace and its compile commands are at head.
+
+### Change stories
+
+A review opens on its change stories (spec `docs/superpowers/specs/2026-10-04-change-stories-design.md`): at most 15
+per review, each story graph at most 12 nodes. The second and third changes below come from a second import, kept small
+so its workspace and compile commands sit right after them (`--root` starts a `p4d` on a new port, here 1668):
+
+```bash
+lab/p4-import.py --repo $LAB/upstream --base 5ead0bdfb^1 --commits 5ead0bdfb d3b3049a6 --exclude tests/resources \
+    --port 127.0.0.1:1668 --root $LAB/big2-p4root --depot //depot/libgit2-big --workspace $LAB/big2-ws \
+    --client big2-ws --out $LAB/big2-cls.tsv
+WS=$LAB/big2-ws BUILD=$LAB/big2-build lab/build.sh
+```
+
+`$LAB/tortoise-big2.yaml` is `tortoise-big.yaml` with `p4port: 127.0.0.1:1668`, `client: big2-ws`, its own `root`,
+`compile_commands`, `data_dir` and port. Reviewed headless without an LLM:
+
+| Change | Stories | What the list shows |
+|---|---|---|
+| #6896 vector (libgit2-big CL 2) | 4 | 1 behaviour story (what `git_vector_free` → `git_vector_dispose` changes: `filesystem_iterator_clear` and 4 more see new values), Other changes in `src/util` (4 functions), and two repeated edits: `git_vector_free` → `git_vector_dispose` at 152 sites in 52 files (47 in tests), `git_vector_free_deep` → `git_vector_dispose_deep` at 28 sites in 19 files. The summary: 180 of 187 changed lines are 2 repeated edits |
+| #6897 hashmap (big2 CL 2) | 14 | 8 behaviour stories (the first joins 53 functions), 4 Other stories (56 functions), 1 repeated edit (`git__mwindow_mutex` → `git_mwindow__mutex`, 23 sites) and Tests (37 test functions) |
+| #7278 pcre → pcre2 (big2 CL 4) | 15 | 247 changed functions with no flow, in 15 Other stories under `deps/pcre`, `deps/pcre2` and `src/util`: a vendored library swapped, which the stories don't yet tell as one |
+
+No story title or summary shows an absolute path.
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_boardstore.py tests/test_web.py tests/test_large_change.py -q`
Expected: `38 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `418 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/boardstore.py backend/codetortoise/pipeline.py backend/codetortoise/web/app.py lab/README.md backend/tests/test_boardstore.py backend/tests/test_web.py backend/tests/test_large_change.py
git commit -m "feat(api): store a review's stories and serve the list, each story and the story holding a node"
```

---

### Task 4: The AI retells stories

Spec §4 (AI). `storyboard.story_job(ctx, story_detail)` asks the model to "Retell this change story" from its flows,
findings and diffs and returns a title and summary held to the same style and citation rules as flow narratives;
accepted text sets `text_source: "llm"`. When a review runs, the up-front pass (`build_storyboard(…, stories=…,
upfront_stories=…)`) retells the top `llm.upfront_stories` (3) non-collapsed behaviour stories within the AI budget
(purpose "story"); the pipeline then copies the retold titles into the list. `POST …/explain` accepts
`kind: "story"`: on demand, one story is retold, counted against the budget, and stored with `put_story`. The e2e AI
server answers the new prompt and sets `upfront_stories: 0` so its budget counts stay as they were.

**Files:**
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `backend/codetortoise/llm/ondemand.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/web/app.py`
- Modify: `backend/tests/test_storyboard.py`
- Modify: `backend/tests/test_ondemand.py`
- Modify: `backend/tests/test_pipeline.py`
- Modify: `backend/tests/test_tortoise.py`
- Modify: `frontend/e2e/fake_llm.py`
- Modify: `frontend/e2e/serve-ai.sh`

**Interfaces:**
- Consumes: `StoryDetail`, `Story.text_source` (Task 2); `boardstore.story`, `put_story` (Task 3).
- Produces: config `llm.upfront_stories = 3`; `storyboard.story_job(ctx, d: StoryDetail) -> Job`;
  `build_storyboard(…, stories: list[StoryDetail] | None = None, upfront_stories: int = 3)`; `ondemand.KINDS` with
  `"story"`; `ExplainIn.kind` `"story"`; usage purpose `"story"`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_storyboard.py`:

```diff
diff --git a/backend/tests/test_storyboard.py b/backend/tests/test_storyboard.py
index 6ab8132..191d040 100644
--- a/backend/tests/test_storyboard.py
+++ b/backend/tests/test_storyboard.py
@@ -263,3 +263,44 @@ def test_a_flow_title_that_breaks_the_headline_rules_keeps_the_template_title():
                    "cites": ["N3"]})), board=board)
     assert board.flows[0].what == "logger_flush drops -2." and board.flows[0].title == "template title"
     assert sb.style_dropped == 1
+
+
+def _story_details(n=2):
+    from codetortoise.stories import Story, StoryDetail
+    out = []
+    for i in range(1, n + 1):
+        st = Story(id=f"S{i}", kind="behaviour", title=f"template {i}", summary="template summary", nodes=["N3"],
+                   flows=["FL1"], findings=["F1"])
+        out.append(StoryDetail(story=st, board=_board(1)))
+    return out
+
+
+def test_the_upfront_pass_retells_the_top_stories_only():
+    im, findings, layers = model()
+    details = _story_details(3)
+    asked = []
+
+    def respond(system, user):
+        asked.append(user)
+        if "Retell this change story" in user:
+            return {"title": "logger_flush drops -2", "summary": "uart_send can now return -2 and logger_flush drops it.",
+                    "cites": ["N3"]}
+        return _respond(lambda u: {"what": "w", "cites": []})(system, user)
+    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(0), stories=details, upfront_stories=2)
+    assert [d.story.text_source for d in details] == ["llm", "llm", "template"]
+    assert details[0].story.title == "logger_flush drops -2"
+    assert details[0].story.summary == "uart_send can now return -2 and logger_flush drops it."
+    prompt = next(u for u in asked if "Retell this change story" in u)
+    assert "template 1" in prompt and "logger_flush → uart_send" in prompt and "F1" in prompt
+
+
+def test_a_story_answer_that_cites_nothing_of_the_story_keeps_the_template():
+    im, findings, layers = model()
+    details = _story_details(1)
+
+    def respond(system, user):
+        if "Retell this change story" in user:
+            return {"title": "made up", "summary": "Something else entirely.", "cites": ["N99"]}
+        return _respond(lambda u: {"what": "w", "cites": []})(system, user)
+    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(0), stories=details, upfront_stories=3)
+    assert details[0].story.text_source == "template" and details[0].story.title == "template 1"
```

`backend/tests/test_ondemand.py`:

```diff
diff --git a/backend/tests/test_ondemand.py b/backend/tests/test_ondemand.py
index 838e67d..b3bb35e 100644
--- a/backend/tests/test_ondemand.py
+++ b/backend/tests/test_ondemand.py
@@ -19,6 +19,9 @@ def _reply(user: str) -> dict:
                 "hypotheses": [{"text": "uart_errors may count twice.", "cites": ["N9"]}]}
     if "Describe this call flow" in user:
         return {"what": "main reaches uart_send through logger_flush.", "title": "flush drops -2", "cites": CITES}
+    if "Retell this change story" in user:
+        return {"title": "hal_write's new signature reaches uart_init", "summary": "uart_init calls hal_write.",
+                "cites": CITES}
     if "Summarise this file" in user:
         return {"summary": "uart.c now counts errors through an alias.", "check": ["Check uart_errors readers."],
                 "cites": ["N9"]}
@@ -40,6 +43,7 @@ def ai(fx, tmp_path):
     svc = make_services(fx, tmp_path, llm=llm)
     svc.cfg.llm.base_url = "http://llm/v1"
     svc.cfg.llm.upfront_flows = 1                                      # the fixture has 3 flows: leave 2 for later
+    svc.cfg.llm.upfront_stories = 1                                    # and 2 stories: leave 1
     app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
     owner = login(app, "owner")
     rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
@@ -74,15 +78,28 @@ def test_explaining_a_finding_and_summarising_a_file(ai):
     assert "uart_send" in prompt and "+" in prompt                    # the diff and the functions' facts
 
 
+def test_explaining_a_story_retells_its_title_and_summary_for_everyone(ai):
+    svc, app, owner, rid, seen = ai
+    ss = owner.get(f"/api/reviews/{rid}/stories").json()
+    assert [s["text_source"] for s in ss["stories"]] == ["llm", "template"]     # the up-front pass did the first
+    bob = login(app, "bob")
+    assert bob.post(f"/api/reviews/{rid}/explain", json={"kind": "story", "target": "S2"}).status_code == 202
+    s2 = owner.get(f"/api/reviews/{rid}/stories").json()["stories"][1]
+    assert s2["title"] == "hal_write's new signature reaches uart_init" and s2["text_source"] == "llm"
+    assert owner.get(f"/api/reviews/{rid}/stories/S2").json()["story"]["summary"] == "uart_init calls hal_write."
+    r = owner.post(f"/api/reviews/{rid}/explain", json={"kind": "story", "target": "S9"})
+    assert r.status_code == 404 and "S9" in r.json()["detail"]
+
+
 def test_explain_is_refused_over_the_budget_and_the_owner_raises_it(ai):
     svc, app, owner, rid, _ = ai
     bob = login(app, "bob")
     used = owner.get(f"/api/reviews/{rid}/ai").json()["used"]
-    assert used == 2                                                   # the up-front pass: 1 flow + the summary
+    assert used == 3                                                   # the up-front pass: 1 flow, 1 story, the summary
     assert bob.put(f"/api/reviews/{rid}/ai/budget", json={"budget": 10}).status_code == 403
     assert owner.put(f"/api/reviews/{rid}/ai/budget", json={"budget": used}).json()["budget"] == used
     r = bob.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": "F1"})
-    assert r.status_code == 429 and "this review has used its 2 AI calls" in r.json()["detail"]
+    assert r.status_code == 429 and "this review has used its 3 AI calls" in r.json()["detail"]
     owner.put(f"/api/reviews/{rid}/ai/budget", json={"budget": used + 5})
     assert bob.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": "F1"}).status_code == 202
 
@@ -106,10 +123,10 @@ def test_the_ai_view_reports_limits_and_calls(ai):
     assert (u["budget"], u["me_limit"], u["per_mention"], u["llm"]) == (200, 100, 6, True)
     assert "calls" not in u                                            # polled often: the list is fetched apart
     calls = owner.get(f"/api/reviews/{rid}/ai/calls").json()
-    assert [c["purpose"] for c in calls] == ["flow", "summary"]
+    assert [c["purpose"] for c in calls] == ["flow", "story", "summary"]
     assert all(c["prompt_tokens"] == 1000 for c in calls)
     h = owner.get("/api/health").json()                               # + layer naming, once per index
-    assert h["ai"]["calls_today"] == 3 and h["ai"]["limits"] == {"per_review": 200, "per_person_daily": 100,
+    assert h["ai"]["calls_today"] == 4 and h["ai"]["limits"] == {"per_review": 200, "per_person_daily": 100,
                                                                  "per_mention": 6}
 
 
```

`backend/tests/test_pipeline.py`:

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 6b373cf..5ceff03 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -158,10 +158,12 @@ def test_llm_text_stored_by_a_review_records_its_prompt_files(fx, tmp_path):
     assert board["about"]["intent_source"] == "llm" and board["about"]["intent_files"] is None
     llm_flows = [f for f in board["flows"] if f["what_source"] == "llm"]
     assert llm_flows and all(f["what_files"] and set(f["files"]) <= set(f["what_files"]) for f in llm_flows)
-    # the up-front pass: the summary and the top 3 flows; findings are explained on demand (spec 2026-10-03 §3)
+    # the up-front pass: the summary, the top 3 flows and the top behaviour stories (the fixture has 2); findings are
+    # explained on demand (spec 2026-10-03 §3, 2026-10-04 §4)
     assert len(llm_flows) == 3 and all(f.explanation is None for f in svc.store.list_findings(rid))
     usage = svc.ledger.usage(rid)
-    assert usage["used"] == 4 and usage["by_purpose"] == {"flow": 3, "summary": 1} and usage["by_person"] == {"pipeline": 4}
+    assert usage["used"] == 6 and usage["by_purpose"] == {"flow": 3, "story": 2, "summary": 1}
+    assert usage["by_person"] == {"pipeline": 6}
 
 
 def test_the_llm_stage_reports_text_dropped_for_breaking_the_style(fx, tmp_path):
```

`backend/tests/test_tortoise.py`:

```diff
diff --git a/backend/tests/test_tortoise.py b/backend/tests/test_tortoise.py
index db26672..a3c8ac2 100644
--- a/backend/tests/test_tortoise.py
+++ b/backend/tests/test_tortoise.py
@@ -24,7 +24,8 @@ class Script:
         user = json.loads(req.content)["messages"][1]["content"]
         if "Give each level" in user:                                                  # layer naming
             return self._reply({"layers": []})
-        if "Summarize the whole change" in user or "Describe this call flow" in user:   # the up-front pass
+        if any(k in user for k in ("Summarize the whole change", "Describe this call flow",
+                                   "Retell this change story")):                       # the up-front pass
             return self._reply({"summary": "s", "risk": "high", "cites": []} if "Summarize" in user
                                else {"what": "w", "cites": []})
         self.prompts.append(user)
```

`frontend/e2e/fake_llm.py`:

```diff
diff --git a/frontend/e2e/fake_llm.py b/frontend/e2e/fake_llm.py
index b013846..bb807b3 100644
--- a/frontend/e2e/fake_llm.py
+++ b/frontend/e2e/fake_llm.py
@@ -15,6 +15,9 @@ def answer(system: str, user: str) -> dict:
     if "Describe this call flow" in user:
         return {"what": "The new -2 from uart_send reaches logger_flush, which drops it.", "title": "Flush drops the new error",
                 "cites": CITES}
+    if "Retell this change story" in user:
+        return {"title": "uart_send's new error count reaches uart_errors",
+                "summary": "uart_send now counts errors in Uart::errors, which uart_errors reports.", "cites": CITES}
     if "Explain the risk" in user:
         return {"explanation": "uart_send can now return -2, and logger_flush drops it.",
                 "verify_steps": ["Check how logger_flush handles -2."], "hypotheses": []}
```

`frontend/e2e/serve-ai.sh`:

```diff
diff --git a/frontend/e2e/serve-ai.sh b/frontend/e2e/serve-ai.sh
index 636767b..1633a34 100644
--- a/frontend/e2e/serve-ai.sh
+++ b/frontend/e2e/serve-ai.sh
@@ -9,6 +9,7 @@ llm:
   base_url: http://127.0.0.1:8797/v1
   model: fake
   upfront_flows: 1
+  upfront_stories: 0
 YAML
 export TORTOISE_LLM_KEY=fake
 exec $CMD serve --config "$DIR/tortoise.yaml"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_storyboard.py tests/test_ondemand.py tests/test_pipeline.py tests/test_tortoise.py -q`
Expected: FAIL — `3 failed, 46 passed, 14 errors` (`build_storyboard() got an unexpected keyword argument 'stories'`, `assert (4 == 6)` for the AI calls of a review, and `"LlmConfig" object has no field "upfront_stories"` in `test_ondemand.py`'s setup)

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index a5c6749..fd9f776 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -68,6 +68,7 @@ class LlmConfig(BaseModel):
     timeout_s: float = 120.0
     concurrency: int = 4           # parallel LLM calls (finding explanations, chapter and flow narratives)
     upfront_flows: int = 3         # flow narratives written when a review runs (the rest on demand)
+    upfront_stories: int = 3       # behaviour stories whose title and summary the AI writes when a review runs
     budget: LlmBudget = Field(default_factory=LlmBudget)
 
 
```

`backend/codetortoise/llm/storyboard.py`:

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index 1407490..d4c9126 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -16,6 +16,7 @@ from codetortoise.llm.client import LlmClient, LlmError
 from codetortoise.llm.ledger import Ledger, Refused
 from codetortoise.llm.style import MODES, STYLE, check_style
 from codetortoise.provenance import merge
+from codetortoise.stories import StoryDetail
 
 SYSTEM = ("You are a senior C/C++ code reviewer. You are given facts extracted by static analysis "
           "for a set of changes. Use ONLY these facts. Refer to functions/fields by their node id (e.g. N3) "
@@ -70,6 +71,12 @@ class _FlowOut(BaseModel):
     cites: list[str] = Field(default_factory=list)
 
 
+class _StoryOut(BaseModel):
+    title: str = ""
+    summary: str = ""
+    cites: list[str] = Field(default_factory=list)
+
+
 class _LayerName(BaseModel):
     level: int
     name: str
@@ -259,6 +266,34 @@ def flow_job(ctx: AiContext, fl: Flow) -> Job:
     return Job("flow", fl.id, _flow_prompt(fl, ctx.impact, ctx.findings, ctx.snippets, ctx.per_call), _FlowOut, apply)
 
 
+def story_job(ctx: AiContext, d: StoryDetail) -> Job:
+    """A change story's title and summary (spec 2026-10-04-change-stories §4), from its flows, functions and findings.
+    Kept only when it cites the story's code or findings and keeps the house style."""
+    st, impact = d.story, ctx.impact
+    flows = [fl for fl in d.board.flows if fl.id in st.flows] or d.board.flows
+    mentioned = list(dict.fromkeys(st.nodes + [n for fl in flows for n in fl.path]))
+    nodes = [n for n in mentioned if n in impact.nodes]
+    notes = "\n".join(f"{f.node} {f.label}: {f.note}" for f in d.functions)
+    parts = [f"STORY {st.id} ({st.kind}): {st.title}\ndraft summary: {st.summary}\nchanged functions:\n{notes or 'none'}",
+             "FLOWS:\n" + "\n".join(f"{fl.id} {fl.text}: {fl.what}" for fl in flows),
+             "FINDINGS:\n" + "\n\n".join(_finding_text(f) for f in ctx.findings if f.id in st.findings),
+             "GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes)]
+    parts += [f"CODE {n}:\n{ctx.snippets[n]}" for n in nodes if n in ctx.snippets]
+
+    def apply(out: _StoryOut) -> int:
+        title, summary = out.title.strip(), out.summary.strip()
+        if not (title and summary and set(out.cites) & (set(mentioned) | set(st.findings))):
+            return 0
+        if not (0 < len(title) <= 80 and _styled(title, "headline") and _styled(summary, "explanation")):
+            return 1
+        st.title, st.summary, st.text_source = title, summary, "llm"
+        return 0
+    prompt = ("Retell this change story for a reviewer: a title of at most 10 words saying what changed and who is "
+              "affected, and a summary of 1-2 sentences. Cite the node and finding ids you rely on.\n"
+              f"Title: {MODES['headline']} Summary: {MODES['explanation']}\n\n" + budget(parts, ctx.per_call))
+    return Job("story", st.id, prompt, _StoryOut, apply)
+
+
 def summary_job(ctx: AiContext, sb: Storyboard, board: Board | None) -> Job:
     overview = [f"CHAPTER {c.name}: {c.narrative} (cites {c.cites})" for c in sb.chapters]
     overview += [_finding_text(f) for f in ctx.findings[:30]]
@@ -296,9 +331,11 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
                      snippets: dict[str, str], llm: LlmClient | None, max_tokens: int = 64000, *,
                      board: Board | None = None, concurrency: int = 1, upfront_flows: int = 3,
                      node_files: dict[str, list[str] | None] | None = None, ledger: Ledger | None = None,
-                     rid: int | None = None) -> Storyboard:
+                     rid: int | None = None, stories: list[StoryDetail] | None = None,
+                     upfront_stories: int = 3) -> Storyboard:
     """The deterministic storyboard, then (with an LLM) the up-front pass of spec 2026-10-03 §3: narratives for the
-    first `upfront_flows` flows (concurrently), then the change summary. Everything else is explained on demand.
+    first `upfront_flows` flows and titles for the first `upfront_stories` stories given (concurrently), then the
+    change summary. Everything else is explained on demand.
 
     Every call goes through `ledger` when given (as the pipeline). A refused or failed call stops the pass and leaves
     the deterministic text for whatever wasn't written; `llm_error` says why."""
@@ -307,6 +344,7 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
         return sb
     ctx = AiContext(impact, findings, snippets, max_tokens, node_files)
     jobs = [flow_job(ctx, fl) for fl in (board.flows[:upfront_flows] if board else [])]
+    jobs += [story_job(ctx, d) for d in (stories or [])[:upfront_stories]]
     pool = ThreadPoolExecutor(max(1, concurrency), thread_name_prefix="tortoise-llm")
     try:
         for dropped in pool.map(lambda j: run_job(llm, j, ledger, rid), jobs):
```

`backend/codetortoise/llm/ondemand.py`:

```diff
diff --git a/backend/codetortoise/llm/ondemand.py b/backend/codetortoise/llm/ondemand.py
index 3541362..6e9a5bb 100644
--- a/backend/codetortoise/llm/ondemand.py
+++ b/backend/codetortoise/llm/ondemand.py
@@ -1,4 +1,4 @@
-"""On-demand AI (spec 2026-10-03 §4): explain one flow, finding or file when someone asks, once, for everyone.
+"""On-demand AI (spec 2026-10-03 §4): explain one flow, finding, file or story when someone asks, once, for everyone.
 
 Each explanation is one job (storyboard.Job) run through the ledger as the person who asked. Its context is rebuilt
 from what the review stored; the result is stored with the review (the board, the findings, the file summaries).
@@ -18,13 +18,22 @@ from codetortoise.board import Board
 from codetortoise.detectors.base import Finding
 from codetortoise.facts.model import Facts
 from codetortoise.impact import ImpactModel
-from codetortoise.llm.storyboard import AiContext, Job, _facts_for_nodes, budget, finding_job, flow_job, run_job
+from codetortoise.llm.storyboard import (
+    AiContext,
+    Job,
+    _facts_for_nodes,
+    budget,
+    finding_job,
+    flow_job,
+    run_job,
+    story_job,
+)
 from codetortoise.llm.style import MODES, check_style
 from codetortoise.provenance import merge, tag_board
 from codetortoise.services import Services
 from codetortoise.vcs.model import ChangeSet
 
-KINDS = ("flow", "finding", "file")
+KINDS = ("flow", "finding", "file", "story")
 _locks: dict[int, threading.Lock] = {}
 _locks_guard = threading.Lock()
 
@@ -138,6 +147,22 @@ def explain(svc: Services, rid: int, user: str, kind: str, target: str) -> None:
             for k in ("explanation", "verify_steps", "hypotheses", "explain_files"):
                 setattr(now, k, getattr(trial, k))
             svc.store.put_findings(rid, findings)
+    elif kind == "story":
+        d = boardstore.story(svc.store, rid, target)
+        if d is None:
+            raise NotFound(f"story {target} not found")
+        trial = d.model_copy(deep=True)
+        trial.story.text_source = "template"
+        run_job(svc.llm, story_job(ctx, trial), svc.ledger, rid, user)
+        if trial.story.text_source != "llm":
+            raise Unchecked(UNCHECKED)
+        with _lock(rid):
+            _same(svc, rid, seen)
+            now = boardstore.story(svc.store, rid, target)                # as stored now
+            if now is None or now.story.nodes != d.story.nodes or now.story.flows != d.story.flows:
+                raise Changed(CHANGED)
+            now.story.title, now.story.summary, now.story.text_source = trial.story.title, trial.story.summary, "llm"
+            boardstore.put_story(svc.store, rid, now)
     elif kind == "file":
         fresh: dict = {}
         run_job(svc.llm, file_job(ctx, board, cs, target, fresh, user), svc.ledger, rid, user)
@@ -169,6 +194,9 @@ def check_target(svc: Services, rid: int, kind: str, target: str) -> None:
     elif kind == "finding":
         if not any(f.id == target for f in svc.store.list_findings(rid)):
             raise NotFound(f"finding {target} not found")
+    elif kind == "story":
+        if boardstore.story(svc.store, rid, target) is None:
+            raise NotFound(f"story {target} not found")
     elif kind == "file":
         cs = svc.store.get_blob(rid, "changeset") or {}
         if not any(f.get("depot") == target for f in cs.get("files", [])):
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 0b7cd39..5c6219a 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -255,9 +255,14 @@ def run_review(rid: int, svc: Services) -> None:
         snippets = collect_snippets(ctx["impact"], ctx["cs"], ctx["after"])
         bs = ctx.get("boards")
         b = None if bs is None else bs.board or boardstore.merge(list(bs.clusters.values()), bs.overview.about)
+        top = [] if bs is None or bs.stories is None else [   # the riskiest behaviour stories get AI titles up front
+            bs.story_details[s.id] for s in bs.stories.stories if s.kind == "behaviour" and not s.collapsed]
         sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens,
                               board=b, concurrency=cfg.llm.concurrency, upfront_flows=cfg.llm.upfront_flows,
-                              node_files=ctx.get("node_files"), ledger=svc.ledger, rid=rid)
+                              node_files=ctx.get("node_files"), ledger=svc.ledger, rid=rid, stories=top,
+                              upfront_stories=cfg.llm.upfront_stories)
+        if bs is not None and bs.stories is not None:          # the list shows the retold titles too
+            bs.stories.stories = [bs.story_details[s.id].story for s in bs.stories.stories]
         store.put_findings(rid, findings)
         store.put_blob(rid, "storyboard", sb)
         if bs is not None:                     # the AI pass rewrote flows and the summary on the stored boards' objects
```

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index cde743b..30b8ff0 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -48,7 +48,7 @@ class FindingStateIn(BaseModel):
 
 
 class ExplainIn(BaseModel):
-    kind: Literal["flow", "finding", "file"]
+    kind: Literal["flow", "finding", "file", "story"]
     target: str = Field(min_length=1, max_length=2000)
 
 
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_storyboard.py tests/test_ondemand.py tests/test_pipeline.py tests/test_tortoise.py -q`
Expected: `63 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `421 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/llm/storyboard.py backend/codetortoise/llm/ondemand.py backend/codetortoise/pipeline.py backend/codetortoise/web/app.py backend/tests/test_storyboard.py backend/tests/test_ondemand.py backend/tests/test_pipeline.py backend/tests/test_tortoise.py frontend/e2e/fake_llm.py frontend/e2e/serve-ai.sh
git commit -m "feat(ai): retell the riskiest stories up front and any story on demand"
```

---

### Task 5: A review opens on its stories: list, steps, graph, repeated edits — desktop and phone

Spec §3, §5. **Routes:** `/r/:id` shows the story list (or today's board or overview when the review has no stories;
"Loading…" while the list loads); `/r/:id/s/:sid` a story (`?tab=graph`, `?node=`); `/r/:id/board` and
`/r/:id/overview` the boards; `/r/:id/files` redirects to `/board`; the header has Stories and Boards. `?node=` on
`/r/:id` opens the story holding the node (else the board). **List:** the summary line, sections "What behaves
differently", "Other changes", "Repeated edits" (compact, marked "skim"), "Tests"; each entry has its id, risk, title
(backticks as code), summary and counts; collapsed behaviour stories sit under "N more behaviour stories".
**Story page:** title, risk, summary, counts, ✦ Explain, ‹ › between stories, Steps and Graph tabs, "Whole graph ›" to
the board holding its cause. Steps: each flow as numbered steps with notes, code opening inline, a flow switcher, then
"Also changed in this story" and the findings. Graph: the board component with no lens, the change panel closed,
opened fitted to the canvas (`fitZoom`), struct nodes listing fields, notes on nodes, field lines and off-flow calls only
for the selected node, a "+N more changed functions" node that opens the steps. **Mechanical page:** sites by
directory → file, before/after lines, "has an effect ›", "Hide tests", "Also in N functions with other edits"; files
start collapsed past 200 sites. **Tests page:** test functions by file with their code and the stories of what they
call. **Findings** are grouped by story. **Phone:** the list first; a story's tabs are Steps · Graph · Files ·
Summary; the ☰ menu lists All stories, every story and Boards. e2e helpers now click "Boards ›" to reach the board.

**Files:**
- Modify: `frontend/src/board/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/board/zoom.ts`
- Modify: `frontend/src/board/layout.ts`
- Modify: `frontend/src/board/phone/flowSteps.ts`
- Modify: `frontend/src/board/FlowBar.tsx`
- Modify: `frontend/src/board/CardLayer.tsx`
- Modify: `frontend/src/board/Canvas.tsx`
- Modify: `frontend/src/board/Board.tsx`
- Modify: `frontend/src/board/phone/PhoneBoard.tsx`
- Modify: `frontend/src/board/ClusterBoard.tsx`
- Modify: `frontend/src/board/board.css`
- Create: `frontend/src/stories/stories.ts`
- Create: `frontend/src/stories/StoryList.tsx`
- Create: `frontend/src/stories/StorySteps.tsx`
- Create: `frontend/src/stories/StoryBodies.tsx`
- Create: `frontend/src/stories/StoryPage.tsx`
- Create: `frontend/src/stories/stories.css`
- Modify: `frontend/src/components/Findings.tsx`
- Modify: `frontend/src/pages/Review.tsx`
- Test: `frontend/src/stories/stories.test.ts`
- Modify: `frontend/src/board/zoom.test.ts`
- Modify: `frontend/e2e/helpers.ts`
- Test: `frontend/e2e/stories.spec.ts`
- Modify: `frontend/e2e/ai.spec.ts`
- Modify: `frontend/e2e/board.spec.ts`
- Modify: `frontend/e2e/landing.spec.ts`
- Modify: `frontend/e2e/large.spec.ts`
- Modify: `frontend/e2e/panel-diff.spec.ts`
- Modify: `frontend/e2e/phone.spec.ts`

**Interfaces:**
- Consumes: HTTP `…/stories`, `…/stories/{sid}`, `…/locate` (Task 3); `…/explain` `kind: "story"` (Task 4).
- Produces: `types.ts` `Story`, `StoryKind`, `StoryRef`, `StoryFunction`, `StorySite`, `StoryDetail`, `StorySet`,
  `BoardNode.kind` `struct`/`more`, `.note`, `.fields`; `api.stories(id)`, `api.story(id, sid, expand?)`, `AiKind`
  `"story"`; `zoom.fitZoom(nodes, vp)`; `stories/stories.ts` `sections`, `stepStory`, `countLine`, `groupSites`,
  `OPEN_SITES = 200`, `wholeGraph`; components `StoryList` (and `Ticks`), `StoryPage`, `StorySteps`,
  `MechanicalStory`, `TestsStory`; `Board` prop `story`; `Canvas` props `quiet`, `onMore`; `PhoneBoard` props `steps`,
  `stories`, `showSteps`; `Findings` `groups` as `{id, name, finding_ids}[]`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/stories/stories.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Story, StorySet, StorySite } from "../board/types";
import { countLine, groupSites, sections, stepStory, wholeGraph } from "./stories";

const story = (id: string, kind: Story["kind"], extra: Partial<Story> = {}): Story => ({
  id, kind, title: id, summary: "", text_source: "template", risk: null, counts: {}, nodes: [], flows: [], findings: [],
  board: null, sub: null, subs: [], collapsed: false, ...extra,
});
const set = (stories: Story[]): StorySet => ({ summary: "", stories, node_story: {}, flow_story: {}, finding_story: {} });
const site = (path: string, line: number, test = false): StorySite => ({
  path, line, function: "f", node: null, before: "a", after: "b", test, effect: null, other_edits: null,
});

describe("stories", () => {
  it("splits the list into sections, collapsed behaviour stories apart", () => {
    const s = sections(set([story("S1", "behaviour"), story("S2", "behaviour", { collapsed: true }), story("S3", "other"),
                            story("S4", "mechanical"), story("S5", "tests")]));
    expect(s.behaviour.map((x) => x.id)).toEqual(["S1"]);
    expect(s.collapsed.map((x) => x.id)).toEqual(["S2"]);
    expect([s.other, s.mechanical, s.tests].map((xs) => xs.map((x) => x.id))).toEqual([["S3"], ["S4"], ["S5"]]);
  });

  it("steps between stories in list order, wrapping around", () => {
    const ss = set([story("S1", "behaviour"), story("S2", "other"), story("S3", "tests")]);
    expect(stepStory(ss, "S1", 1)).toBe("S2");
    expect(stepStory(ss, "S1", -1)).toBe("S3");
    expect(stepStory(ss, "S3", 1)).toBe("S1");
  });

  it("counts what a story holds, leaving zeros out", () => {
    expect(countLine(story("S1", "behaviour", { counts: { flows: 2, findings: 1, functions: 4, files: 0 } })))
      .toBe("2 flows · 1 finding · 4 functions");
    expect(countLine(story("S2", "mechanical", { counts: { sites: 152, files: 52, test_sites: 47 } })))
      .toBe("152 sites · 52 files · 47 in tests");
  });

  it("groups sites by directory then file in line order, and hides tests on request", () => {
    const sites = [site("//d/src/b.c", 9), site("//d/src/b.c", 3), site("//d/src/a.c", 1), site("//d/tests/t.c", 2, true)];
    const g = groupSites(sites, false);
    expect(g.map((d) => [d.dir, d.count])).toEqual([["//d/src", 3], ["//d/tests", 1]]);
    expect(g[0].files.map((f) => [f.name, f.sites.map((s) => s.line)])).toEqual([["a.c", [1]], ["b.c", [3, 9]]]);
    expect(groupSites(sites, true).map((d) => d.dir)).toEqual(["//d/src"]);
  });

  it("opens the whole graph on the board holding the story's first node", () => {
    expect(wholeGraph(3, story("S1", "behaviour", { nodes: ["N9"] }))).toBe("/r/3/board?node=N9");
    expect(wholeGraph(3, story("S1", "behaviour", { nodes: ["N9"], board: "C2" }))).toBe("/r/3/c/C2?node=N9");
  });
});
```

`frontend/src/board/zoom.test.ts`:

```diff
diff --git a/frontend/src/board/zoom.test.ts b/frontend/src/board/zoom.test.ts
index 5a41d1a..9231527 100644
--- a/frontend/src/board/zoom.test.ts
+++ b/frontend/src/board/zoom.test.ts
@@ -1,6 +1,6 @@
 import { describe, expect, it } from "vitest";
 import { makeLens } from "./lens";
-import { pinchZoom, zoomLens } from "./zoom";
+import { fitZoom, pinchZoom, zoomLens } from "./zoom";
 
 const vp = { W: 400, H: 700 };
 const lens = makeLens({ panX: 200, panY: 0, lens: 0 }, vp, [-500, 500]);
@@ -46,3 +46,16 @@ describe("pinch keeps the point under the fingers", () => {
     expect([Math.round(p.x), Math.round(p.y)]).toEqual([260, 380]);
   });
 });
+
+describe("fitZoom", () => {
+  const nodes = (pts: [number, number][]) => pts.map(([x, y], i) => ({ id: `N${i}`, x, y }));
+  it("shrinks a graph wider or taller than the canvas until it fits, never below ZOOM_MIN", () => {
+    expect(fitZoom(nodes([[0, 0], [1000, 0]]), { W: 700, H: 800 })).toBeCloseTo(700 / 1260);
+    expect(fitZoom(nodes([[0, 0], [0, 840]]), { W: 1200, H: 500 })).toBeCloseTo(500 / 960);
+    expect(fitZoom(nodes([[0, 0], [9000, 0]]), { W: 400, H: 800 })).toBe(0.5);
+  });
+  it("never enlarges a graph that already fits", () => {
+    expect(fitZoom(nodes([[0, 0], [100, 210]]), { W: 1200, H: 800 })).toBe(1);
+    expect(fitZoom([], { W: 1200, H: 800 })).toBe(1);
+  });
+});
```

`frontend/e2e/helpers.ts`:

```diff
diff --git a/frontend/e2e/helpers.ts b/frontend/e2e/helpers.ts
index 5a80d18..d83b031 100644
--- a/frontend/e2e/helpers.ts
+++ b/frontend/e2e/helpers.ts
@@ -7,11 +7,18 @@ export async function login(page: Page, user = "demo") {
   await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
 }
 
-/** Log in as the demo owner, review fixture CLs 101+102 from the landing page and wait for the board. */
-export async function startReview(page: Page) {
+/** Log in as the demo owner, review fixture CLs 101+102 from the landing page and wait for the story list. */
+export async function startStories(page: Page) {
   await login(page);
   await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
   await page.getByRole("button", { name: "Start review" }).click();
+  await expect(page.locator(".st-entry").first()).toBeVisible({ timeout: 60_000 });
+}
+
+/** As startStories, then open the board ("Boards ›" on the story list). */
+export async function startReview(page: Page) {
+  await startStories(page);
+  await page.getByRole("link", { name: "Boards ›" }).click();
   // desktop shows the canvas; phones open on the flow reader (spec §13)
   await expect(page.locator(".bd-node, .ph-step").first()).toBeVisible({ timeout: 60_000 });
 }
```

`frontend/e2e/stories.spec.ts`:

```ts
import { devices, expect, type Page, test } from "@playwright/test";
import { startStories } from "./helpers";

/** Change stories (spec 2026-10-04-change-stories §8): list → story steps → graph → whole graph, citations, ‹ ›. */

const rid = (page: Page) => page.url().match(/\/r\/(\d+)/)![1];

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a review opens on its stories; a story's steps, its graph, the whole graph and back", async ({ page }) => {
    await startStories(page);
    await expect(page.locator(".st-lead")).toContainText("2 behaviour stories.");
    const entries = page.locator(".st-entry");
    await expect(entries).toHaveCount(2);
    await expect(entries.first()).toContainText("uart_send now writes Uart::errors; uart_errors reads it");
    await expect(entries.first().locator(".st-counts")).toHaveText(/2 flows · \d+ findings? · 1 function/);

    await entries.first().click();
    await expect(page).toHaveURL(/\/s\/S1$/);
    await expect(page.locator(".st-head h2")).toContainText("uart_send now writes Uart::errors");
    const send = page.locator(".ph-step").filter({ has: page.locator(".ph-text b", { hasText: /^uart_send$/ }) });
    await expect(send).toHaveCount(1);
    await expect(send.locator(".ph-reason")).toContainText("now writes");                 // the step's note
    await send.locator(".ph-head").click();
    await expect(page.locator(".ph-step.open .bd-code, .ph-step.open .bd-note").first()).toBeVisible();
    await page.getByRole("button", { name: "Next flow" }).click();
    await expect(page.locator(".st-flowbar")).toContainText("flow 2 of 2");
    await expect(page.locator(".st-findings li").first()).toBeVisible();

    await page.getByRole("tab", { name: "Graph" }).click();
    await expect(page).toHaveURL(/\/s\/S1\?tab=graph$/);
    const nodes = page.locator(".bd-node");
    await expect(nodes.first()).toBeVisible();
    expect(await nodes.count()).toBeLessThanOrEqual(12);
    await expect(page.locator(".bd-node.field .fields").first()).toContainText(".errors");   // one node per struct
    await expect(page.locator(".bd-node", { has: page.locator(".lbl", { hasText: /^uart_send$/ }) }).locator(".note"))
      .toHaveText("now writes tx, errors");
    await expect(page.getByRole("button", { name: "4×" })).toHaveCount(0);                     // no lens

    await page.getByRole("link", { name: "Whole graph ›" }).click();
    await expect(page).toHaveURL(new RegExp(`/r/${rid(page)}/board\\?node=N\\d+$`));
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/s\/S1\?tab=graph$/);
    await page.getByRole("link", { name: "Stories", exact: true }).first().click();
    await expect(page.locator(".st-entry")).toHaveCount(2);
  });

  test("‹ › step between stories and a citation opens the story holding it", async ({ page }) => {
    await startStories(page);
    await page.locator(".st-entry").first().click();
    await page.getByRole("button", { name: "Next story" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await expect(page.locator(".st-head h2")).toContainText("hal_write's signature changed");
    await page.getByRole("button", { name: "Previous story" }).click();
    await expect(page).toHaveURL(/\/s\/S1$/);

    const ss = await (await page.request.get(`/api/reviews/${rid(page)}/stories`)).json();
    const [node, sid] = Object.entries(ss.node_story as Record<string, string>).find(([, s]) => s === "S2")!;
    await page.goto(`/r/${rid(page)}?node=${node}`);
    await expect(page).toHaveURL(new RegExp(`/s/${sid}\\?node=${node}$`));
    await expect(page.locator(".ph-step.open, .st-also li.open")).toHaveCount(1);
  });

  test("a review without stories (run before them) opens on its board", async ({ page }) => {
    await startStories(page);
    await page.route(`**/api/reviews/${rid(page)}/stories`, (r) =>
      r.fulfill({ status: 404, json: { detail: "this review has no stories: re-run it" } }));
    await page.reload();
    await expect(page.getByRole("tablist", { name: "Call flows" })).toBeVisible();
    await expect(page.locator(".st-entry")).toHaveCount(0);
  });

  test("findings are grouped by story", async ({ page }) => {
    await startStories(page);
    await page.getByRole("link", { name: /Findings/ }).first().click();
    await expect(page.locator(".fg .fg-id").first()).toHaveText("S1");
    await expect(page.getByRole("region", { name: /^Findings in uart_send now writes/ })).toBeVisible();
  });

  test("a repeated edit lists its sites by file, hides tests and links its effects", async ({ page }) => {
    await startStories(page);
    const id = rid(page);
    // neither e2e fixture has a repeated edit: this story is served as the API would for one
    const site = (path: string, line: number, test = false, effect: string | null = null) => ({
      path, line, function: test ? "test_free" : "free_it", node: null, before: "git_vector_free(&v);",
      after: "git_vector_dispose(&v);", test, effect, other_edits: null });
    const story = { id: "S3", kind: "mechanical", title: "`git_vector_free` → `git_vector_dispose` at 3 sites in 2 files (1 in tests)",
      summary: "Every changed line in these 2 functions is this one edit.", text_source: "template", risk: null,
      counts: { sites: 3, files: 2, test_sites: 1 }, nodes: [], flows: [], findings: [], board: null,
      sub: ["git_vector_free", "git_vector_dispose"], subs: [], collapsed: false };
    const real = await (await page.request.get(`/api/reviews/${id}/stories`)).json();
    await page.route(`**/api/reviews/${id}/stories`, (r) => r.fulfill({ json: { ...real, stories: [...real.stories, story] } }));
    await page.route(`**/api/reviews/${id}/stories/S3`, (r) => r.fulfill({ json: {
      story, board: { nodes: [], edges: [], flows: [], impacts: [], layers: [], about: real.about ?? { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] }, hidden_nodes: 0 },
      graph: null, functions: [], also_in: [{ node: "N7", label: "busy", story: "S2" }],
      sites: [site("//fixture/driver/uart.c", 12, false, "S1"), site("//fixture/driver/uart.c", 30), site("//fixture/tests/t.c", 4, true)] } }));
    await page.reload();
    await page.locator(".st-entry", { hasText: "git_vector_dispose" }).click();
    await expect(page.locator(".st-entry.compact, .st-sites li")).not.toHaveCount(0);
    await expect(page.locator(".st-sites li")).toHaveCount(3);
    await expect(page.locator(".st-dir h3").first()).toContainText("//fixture/driver");
    await expect(page.locator(".st-sites li").first()).toContainText("free_it · line 12");
    await page.getByLabel(/Hide tests/).check();
    await expect(page.locator(".st-sites li")).toHaveCount(2);
    await page.getByRole("link", { name: "busy (S2)" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await page.goBack();
    await page.getByRole("link", { name: "has an effect ›" }).click();
    await expect(page).toHaveURL(/\/s\/S1$/);
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });
  const tab = (page: Page, name: string) => page.locator(".ph-tabs").getByRole("tab", { name });

  test("the story list first; a story's Steps and Graph tabs; the menu lists the stories", async ({ page }) => {
    await startStories(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await page.locator(".st-entry").first().click();
    await expect(tab(page, "Steps")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".st-head h2")).toContainText("uart_send now writes Uart::errors");
    await expect(page.locator(".ph-step").first()).toBeVisible();
    await tab(page, "Graph").click();
    await expect(page.locator(".bd-node").first()).toBeVisible();
    expect(await page.locator(".bd-node").count()).toBeLessThanOrEqual(12);
    await page.getByRole("button", { name: "Review menu" }).click();
    const menu = page.locator(".ph-menu");
    await expect(menu.getByRole("link", { name: /^S2 · / })).toBeVisible();
    await menu.getByRole("link", { name: "Boards" }).click();
    await expect(page).toHaveURL(/\/board$/);
    await expect(page.locator(".bd-node, .ph-step").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
```

`frontend/e2e/ai.spec.ts`:

```diff
diff --git a/frontend/e2e/ai.spec.ts b/frontend/e2e/ai.spec.ts
index 1b277f0..a7ffd7b 100644
--- a/frontend/e2e/ai.spec.ts
+++ b/frontend/e2e/ai.spec.ts
@@ -1,5 +1,5 @@
 import { expect, test } from "@playwright/test";
-import { login, startReview } from "./helpers";
+import { login, startReview, startStories } from "./helpers";
 
 const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py
 
@@ -21,6 +21,19 @@ test.describe("with an AI", () => {
     await expect(ask).toHaveText("✦ Explain again");
   });
 
+  test("✦ Explain retells a story's title and summary, on the story and in the list", async ({ page }) => {
+    await startStories(page);
+    await page.locator(".st-entry").first().click();
+    const head = page.locator(".st-head");
+    await expect(head.locator(".ai-label")).toHaveCount(0);                  // this server's up-front pass skips stories
+    await head.getByRole("button", { name: "✦ Explain" }).click();
+    await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
+    await expect(head.locator(".ai-label")).toBeVisible();
+    await expect(head.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
+    await page.getByRole("link", { name: "Stories", exact: true }).first().click();
+    await expect(page.locator(".st-entry").first()).toContainText("uart_send's new error count reaches uart_errors");
+  });
+
   test("the owner raises the budget from the AI pill; a reviewer sees the usage without the control", async ({ page, browser }) => {
     await startReview(page);
     const pill = page.getByRole("button", { name: /^AI \d+\/200$/ });
```

`frontend/e2e/board.spec.ts`:

```diff
diff --git a/frontend/e2e/board.spec.ts b/frontend/e2e/board.spec.ts
index e162f3b..61ab854 100644
--- a/frontend/e2e/board.spec.ts
+++ b/frontend/e2e/board.spec.ts
@@ -101,7 +101,7 @@ test("a cited node opens once; closing it sticks when the canvas resizes", async
   const rid = page.url().match(/\/r\/(\d+)/)![1];
   const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
   const target = board.nodes.find((n: { label: string }) => n.label === "uart_errors");
-  await page.goto(`/r/${rid}?node=${target.id}`);
+  await page.goto(`/r/${rid}/board?node=${target.id}`);
   // by the card's title: other cards' notes can mention uart_errors once their code loads
   const card = page.locator(".bd-card").filter({ has: page.locator(".hd b", { hasText: /^uart_errors$/ }) });
   await expect(card).toBeVisible();
@@ -217,8 +217,8 @@ test("a single board gets +N callees too, and Reset takes them away", async ({ p
 
 test("a cluster address on a review shown as one board links to that board", async ({ page }) => {
   await startReview(page);
-  const board = page.url().replace(/[?#].*$/, "");
-  await page.goto(`${board}/c/C1`);
+  const rid = page.url().match(/\/r\/(\d+)/)![1];
+  await page.goto(`/r/${rid}/c/C1`);
   await expect(page.getByText("This review is shown as one board.")).toBeVisible();
   await page.getByRole("link", { name: "Open the board" }).click();
   await expect(page.getByRole("tablist", { name: "Call flows" })).toBeVisible();
```

`frontend/e2e/landing.spec.ts`:

```diff
diff --git a/frontend/e2e/landing.spec.ts b/frontend/e2e/landing.spec.ts
index 8d6b1fd..1b8d701 100644
--- a/frontend/e2e/landing.spec.ts
+++ b/frontend/e2e/landing.spec.ts
@@ -12,7 +12,7 @@ test.describe("desktop", () => {
     await page.getByLabel("Changelists (shelved or submitted)").fill("102");
     await page.getByLabel("Title (optional)").fill(title);
     await page.getByRole("button", { name: "Start review" }).click();
-    await expect(page.locator(".bd-node").first()).toBeVisible({ timeout: 60_000 });
+    await expect(page.locator(".st-entry").first()).toBeVisible({ timeout: 60_000 });      // a review opens on its stories
     await page.getByRole("link", { name: "Reviews" }).first().click();
 
     const rows = page.locator(".rv-list .rv-row");
```

`frontend/e2e/large.spec.ts`:

```diff
diff --git a/frontend/e2e/large.spec.ts b/frontend/e2e/large.spec.ts
index fa636a6..82667ed 100644
--- a/frontend/e2e/large.spec.ts
+++ b/frontend/e2e/large.spec.ts
@@ -8,6 +8,7 @@ async function startLarge(page: Page) {
   await login(page);
   await page.getByLabel("Changelists (shelved or submitted)").fill("201 202");
   await page.getByRole("button", { name: "Start review" }).click();
+  await page.getByRole("link", { name: "Boards ›" }).click({ timeout: 60_000 });
   await expect(page.locator(".ov-block").first()).toBeVisible({ timeout: 60_000 });
 }
 
@@ -110,12 +111,15 @@ test.describe("a large change", () => {
     await expect(reset).toHaveCount(0);
   });
 
-  test("a citation opens the cluster that holds the node", async ({ page }) => {
+  test("a citation opens the story holding the node; on the boards, the cluster holding it", async ({ page }) => {
     await startLarge(page);
     const rid = page.url().match(/\/r\/(\d+)/)![1];
     const ov = await (await page.request.get(`/api/reviews/${rid}/overview`)).json();
     const regs = ov.clusters.find((c: { name: string }) => c.name === "hal/regs");
+    const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
     await page.goto(`/r/${rid}?node=${regs.nodes[0]}`);
+    await expect(page).toHaveURL(new RegExp(`/s/${ss.node_story[regs.nodes[0]]}\\?node=${regs.nodes[0]}$`));
+    await page.goto(`/r/${rid}/overview?node=${regs.nodes[0]}`);
     await expect(page).toHaveURL(new RegExp(`/c/${regs.id}\\?node=${regs.nodes[0]}`));
     await expect(page.locator(".bd-crumb")).toContainText("hal/regs");
   });
@@ -134,12 +138,14 @@ test.describe("a large change", () => {
     await expect(page.locator(".bd-crumb")).toContainText(other.name);
   });
 
-  test("findings are grouped by cluster", async ({ page }) => {
+  test("findings are grouped by story", async ({ page }) => {
     await startLarge(page);
     await page.getByRole("link", { name: /Findings/ }).click();
-    await expect(page.getByRole("region", { name: "Findings in hal/regs" })).toBeVisible();
+    const first = page.locator(".fg").first();
+    await expect(first.locator(".fg-id")).toHaveText(/^S\d+$/);
+    const sid = (await first.locator(".fg-id").textContent())!;
     const of = page.getByLabel("Findings of");
-    await of.selectOption({ label: (await of.locator("option", { hasText: "hal/regs" }).textContent())! });
+    await of.selectOption({ label: (await of.locator("option", { hasText: new RegExp(`^${sid} · `) }).textContent())! });
     await expect(page.locator(".fg")).toHaveCount(1);
   });
 });
```

`frontend/e2e/panel-diff.spec.ts`:

```diff
diff --git a/frontend/e2e/panel-diff.spec.ts b/frontend/e2e/panel-diff.spec.ts
index eecaa9e..f65c5fe 100644
--- a/frontend/e2e/panel-diff.spec.ts
+++ b/frontend/e2e/panel-diff.spec.ts
@@ -82,6 +82,6 @@ test("the old files page opens the board", async ({ page }) => {
   const id = page.url().match(/\/r\/(\d+)/)![1];
   await expect(page.getByRole("link", { name: /^Files/ })).toHaveCount(0);
   await page.goto(`/r/${id}/files`);
-  await expect(page).toHaveURL(new RegExp(`/r/${id}$`));
+  await expect(page).toHaveURL(new RegExp(`/r/${id}/board$`));
   await expect(page.locator(".bd-node").first()).toBeVisible();
 });
```

`frontend/e2e/phone.spec.ts`:

```diff
diff --git a/frontend/e2e/phone.spec.ts b/frontend/e2e/phone.spec.ts
index 1c3a691..e6be6a2 100644
--- a/frontend/e2e/phone.spec.ts
+++ b/frontend/e2e/phone.spec.ts
@@ -130,7 +130,7 @@ test("a cited function opens on the phone map with its code", async ({ page }) =
   const rid = page.url().match(/\/r\/(\d+)/)![1];
   const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
   const target = board.nodes.find((n: { label: string }) => n.label === "uart_errors");
-  await page.goto(`/r/${rid}?node=${target.id}`);
+  await page.goto(`/r/${rid}/board?node=${target.id}`);
   await expect(tab(page, "Map")).toHaveAttribute("aria-selected", "true");
   await expect(page.locator(".ph-sheet .ph-sheet-head")).toContainText("uart_errors");
   const inside = async () => {                                                     // once the eased pan has settled
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/stories src/board/zoom.test.ts && npx tsc --noEmit && npm run build && npx playwright test e2e/stories.spec.ts`
Expected: FAIL — `Error: Cannot find module './stories'` and `TypeError: fitZoom is not a function` (`Test Files  2 failed (2)`; the command stops there)

- [ ] **Step 3: Implement**

`frontend/src/board/types.ts`:

```diff
diff --git a/frontend/src/board/types.ts b/frontend/src/board/types.ts
index 52d219c..90717b5 100644
--- a/frontend/src/board/types.ts
+++ b/frontend/src/board/types.ts
@@ -1,12 +1,16 @@
 /** Review board model, as served by GET /api/reviews/{id}/board (backend codetortoise/board.py). */
 export interface NodeChange { kind: "modified" | "signature" | "added" | "removed"; add: number; rem: number }
 export interface BoardNode {
-  id: string; key: string; label: string; kind: "function" | "field"; layer: number | null;
+  id: string; key: string; label: string; kind: "function" | "field" | "struct" | "more"; layer: number | null;
   path: string | null; local: string | null; range: [number, number] | null; change: NodeChange | null; x: number; warn: number;
   /** A visitor: the cluster this node belongs to (spec 2026-10-03-large-change-boards §3). */
   home?: string | null;
   /** Callers / callees not on the board, for "+N callers" (absent on boards stored before clusters). */
   more_callers?: number; more_callees?: number;
+  /** A story graph's node (spec 2026-10-04-change-stories §3.1): what changed in it, in a few words. */
+  note?: string | null;
+  /** A story graph's struct node: the fields its story touches. */
+  fields?: { id: string; label: string }[];
 }
 export interface BoardEdge {
   src: string; dst: string; kind: "call" | "virtual" | "writes" | "reads"; status: string; confidence: string;
@@ -47,3 +51,25 @@ export interface Overview {
   merged_over_limit: number;
 }
 export interface SourceText { path: string; depot: string; rev: string; text: string; changed: boolean }
+
+/** Change stories (spec 2026-10-04-change-stories), as served by GET /api/reviews/{id}/stories[/{sid}]. */
+export type StoryKind = "behaviour" | "other" | "mechanical" | "tests";
+export interface Story {
+  id: string; kind: StoryKind; title: string; summary: string; text_source: "template" | "llm"; risk: string | null;
+  counts: Partial<Record<"flows" | "findings" | "functions" | "files" | "sites" | "test_sites", number>>;
+  nodes: string[]; flows: string[]; findings: string[]; board: string | null;
+  sub: [string, string] | null; subs: [string, string][]; collapsed: boolean;
+}
+export interface StoryRef { node: string; label: string; story: string | null }
+export interface StoryFunction { node: string; label: string; note: string; on_flow: boolean; also: string[]; calls: StoryRef[] }
+export interface StorySite {
+  path: string | null; line: number; function: string | null; node: string | null; before: string; after: string;
+  test: boolean; effect: string | null; other_edits: string | null;
+}
+export interface StoryDetail {
+  story: Story; board: Board; graph: Board | null; functions: StoryFunction[]; sites: StorySite[]; also_in: StoryRef[];
+}
+export interface StorySet {
+  summary: string; stories: Story[];
+  node_story: Record<string, string>; flow_story: Record<string, string>; finding_story: Record<string, string>;
+}
```

`frontend/src/api.ts`:

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index 4f11fa8..f9c8a23 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -27,7 +27,7 @@ export interface Comment {
 }
 /** A tortoise reply's state (spec 2026-10-03 §5). */
 export interface AiMeta { pending: boolean; round?: number; of?: number; read: string[]; files: string[]; calls: number; error: string | null }
-export type AiKind = "flow" | "finding" | "file";
+export type AiKind = "flow" | "finding" | "file" | "story";
 export interface AiJob { id: number; user: string; kind: string; target: string; status: "running" | "done" | "failed" | "refused"; error: string | null }
 export interface AiCall { id: number; user: string; purpose: string; target: string | null; started_at: string; finished_at: string | null;
   prompt_tokens: number | null; completion_tokens: number | null; outcome: "ok" | "failed" | "refused" | "running" | null; error: string | null }
@@ -42,8 +42,8 @@ export interface Health { checks: HealthCheck[]; ready: boolean; index_generatio
   p4_sources: Record<string, string>;
   ai: { limits?: { per_review: number; per_person_daily: number; per_mention: number }; calls_today?: number } }
 
-export type { Board, Overview, SourceText } from "./board/types";
-import type { Board, Overview, SourceText } from "./board/types";
+export type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
+import type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
 
 export class ApiError extends Error {
   constructor(public status: number, message: string) { super(message); }
@@ -81,8 +81,11 @@ export const api = {
     return call<Board>("GET", `/api/reviews/${id}/board${q.size ? `?${q}` : ""}`);
   },
   overview: (id: number) => call<Overview>("GET", `/api/reviews/${id}/overview`),
+  stories: (id: number) => call<StorySet>("GET", `/api/reviews/${id}/stories`),
+  story: (id: number, sid: string, expand?: string[]) =>
+    call<StoryDetail>("GET", `/api/reviews/${id}/stories/${sid}${expand?.length ? `?${new URLSearchParams({ expand: expand.join(",") })}` : ""}`),
   locate: (id: number, q: { node?: string; flow?: string; finding?: string }) =>
-    call<{ cluster: string | null }>("GET", `/api/reviews/${id}/locate?${new URLSearchParams(q)}`),
+    call<{ cluster: string | null; story?: string | null }>("GET", `/api/reviews/${id}/locate?${new URLSearchParams(q)}`),
   source: (id: number, path: string, side: "before" | "after" = "after") =>
     call<SourceText>("GET", `/api/reviews/${id}/source?${new URLSearchParams({ path, side })}`),
   findings: (id: number) => call<Finding[]>("GET", `/api/reviews/${id}/findings`),
```

`frontend/src/board/zoom.ts`:

```diff
diff --git a/frontend/src/board/zoom.ts b/frontend/src/board/zoom.ts
index c5d74aa..528891e 100644
--- a/frontend/src/board/zoom.ts
+++ b/frontend/src/board/zoom.ts
@@ -19,6 +19,16 @@ export function zoomLens(lens: Lens, z: number, vp: Viewport): Lens {
   };
 }
 
+const FIT_W = 260, FIT_H = 120;                  // room around the outermost node centres for labels and badges
+
+/** The zoom at which every node fits the canvas (a story's graph opens whole); 1 when it already fits. */
+export function fitZoom(nodes: { x: number; y: number }[], vp: Viewport): number {
+  if (!nodes.length) return 1;
+  const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
+  const w = Math.max(...xs) - Math.min(...xs) + FIT_W, h = Math.max(...ys) - Math.min(...ys) + FIT_H;
+  return Math.max(ZOOM_MIN, Math.min(1, vp.W / w, vp.H / h));
+}
+
 /** The zoom after one pinch update: fingers d0 → d1 apart, clamped to [ZOOM_MIN, ZOOM_MAX]. */
 export const pinchZoom = (z0: number, d0: number, d1: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z0 * (d1 / Math.max(1, d0))));
 
```

`frontend/src/board/layout.ts`:

```diff
diff --git a/frontend/src/board/layout.ts b/frontend/src/board/layout.ts
index fcc7502..1130b65 100644
--- a/frontend/src/board/layout.ts
+++ b/frontend/src/board/layout.ts
@@ -21,7 +21,7 @@ export const worldY = (row: number) => row * BAND + BAND / 2;
  * nearest caller; functions reachable only through cycles start from the changed functions (then any unplaced
  * node); a field sits one row below its deepest writer (or reader when nothing writes it). */
 export function callDepth(board: Board): Map<string, number> {
-  const fns = board.nodes.filter((n) => n.kind === "function");
+  const fns = board.nodes.filter((n) => n.kind === "function" || n.kind === "more");
   const calls = board.edges.filter((e) => e.kind === "call" || e.kind === "virtual");
   const isFn = new Set(fns.map((n) => n.id)), callers = new Map<string, number>();
   for (const e of calls) callers.set(e.dst, (callers.get(e.dst) ?? 0) + 1);
@@ -41,7 +41,7 @@ export function callDepth(board: Board): Map<string, number> {
   walk(fns.filter((n) => !callers.get(n.id)).map((n) => n.id));
   walk(fns.filter((n) => n.change).map((n) => n.id));
   for (const n of fns) walk([n.id]);
-  for (const f of board.nodes.filter((n) => n.kind === "field")) {
+  for (const f of board.nodes.filter((n) => n.kind === "field" || n.kind === "struct")) {
     const by = (kind: string) => board.edges.filter((e) => e.dst === f.id && e.kind === kind && depth.has(e.src))
       .map((e) => depth.get(e.src)!);
     const users = by("writes").length ? by("writes") : by("reads");
```

`frontend/src/board/phone/flowSteps.ts`:

```diff
diff --git a/frontend/src/board/phone/flowSteps.ts b/frontend/src/board/phone/flowSteps.ts
index b3f3e6f..e7b5b86 100644
--- a/frontend/src/board/phone/flowSteps.ts
+++ b/frontend/src/board/phone/flowSteps.ts
@@ -15,7 +15,7 @@ export function flowSteps(board: Board, flow: BoardFlow): Step[] {
       return { ...base, kind: "landing", marker: "!", reason: firstAnn(n.id, true)?.text ?? flow.effect };
     if (n.change)
       return { ...base, kind: "chg", marker: "Δ", reason: `Δ ${n.change.kind} +${n.change.add} −${n.change.rem}` };
-    if (n.kind === "field") {
+    if (n.kind === "field" || n.kind === "struct") {
       const a = firstAnn(n.id);
       return { ...base, kind: "field", marker: "f", reason: a ? `field · ${a.text}` : "field" };
     }
```

`frontend/src/board/FlowBar.tsx`:

```diff
diff --git a/frontend/src/board/FlowBar.tsx b/frontend/src/board/FlowBar.tsx
index 618cc55..e2351b1 100644
--- a/frontend/src/board/FlowBar.tsx
+++ b/frontend/src/board/FlowBar.tsx
@@ -56,7 +56,7 @@ export default function FlowBar({ board, state, layerOf, onFlow, onStep, onStepO
               {flow.path.map((id, i) => {
                 const n = byId.get(id);
                 if (!n) return null;
-                const kind = n.change ? "chg" : n.kind === "field" ? "field" : id === flow.lands || id === flow.fx_at ? "fx" : "";
+                const kind = n.change ? "chg" : n.kind === "field" || n.kind === "struct" ? "field" : id === flow.lands || id === flow.fx_at ? "fx" : "";
                 const open = state.cards[id] && !state.cards[id].collapsed;
                 const code = !!(n.path && n.range);
                 return (
```

`frontend/src/board/CardLayer.tsx`:

```diff
diff --git a/frontend/src/board/CardLayer.tsx b/frontend/src/board/CardLayer.tsx
index 70a47e6..c9c3e8e 100644
--- a/frontend/src/board/CardLayer.tsx
+++ b/frontend/src/board/CardLayer.tsx
@@ -112,7 +112,7 @@ function Card({ node, rect, at, z, front, register, state, dispatch, narrow, onO
            onDoubleClick={(e) => { if (!(e.target as HTMLElement).closest("button")) dispatch({ t: "card.unpin", id }); }}>
         <b>{node.label}</b>
         <span className="file">{node.path?.split("/").slice(-2).join("/")}</span>
-        <span className={`bd-badge ${changed ? "chg" : "ctx"}`}>{changed ? "Δ changed" : node.kind === "field" ? "field" : "context"}</span>
+        <span className={`bd-badge ${changed ? "chg" : "ctx"}`}>{changed ? "Δ changed" : node.kind === "field" || node.kind === "struct" ? "field" : "context"}</span>
         <span className="sp" />
         <button className="bd-ibtn restore" title="Expand card" onClick={(e) => { e.stopPropagation(); dispatch({ t: "card.expand", id }); }}>⤢</button>
         <button className="bd-ibtn expand" title="Open full file" onClick={(e) => { e.stopPropagation(); onOpenFile(id); }}>⤢ Full file</button>
@@ -130,7 +130,7 @@ export type BodyProps = Pick<Props, "reviewId" | "board" | "sources" | "comments
 export function CardBody({ node, reviewId, board, sources, comments, onComments }: BodyProps) {
   const src = useEnsureSource(node.path, sources);
   const [lo, hi] = node.range ?? [0, 0];
-  const pad = node.kind === "field" ? 4 : 0;
+  const pad = node.kind === "field" || node.kind === "struct" ? 4 : 0;
   const lines = useMemo(() => {
     if (isChange(src)) return sliceRange(lineDiff(src.before, src.after), lo - pad, hi + pad);
     if (src && "status" in src && src.status === "ok") return sliceRange(plainLines(src.file.text), lo - pad, hi + pad);
```

`frontend/src/board/Canvas.tsx`:

```diff
diff --git a/frontend/src/board/Canvas.tsx b/frontend/src/board/Canvas.tsx
index c310c23..46dbc39 100644
--- a/frontend/src/board/Canvas.tsx
+++ b/frontend/src/board/Canvas.tsx
@@ -21,6 +21,10 @@ interface Props {
   onHome?: (cluster: string, id: string) => void;
   /** A cluster id's name, for the visitor link. */
   homeName?: (cluster: string) => string;
+  /** A story graph (spec 2026-10-04-change-stories §3.1): field lines and calls off the selected flow show only for
+   * the selected node; "+N more changed functions" calls `onMore`. */
+  quiet?: boolean;
+  onMore?: () => void;
   /** Phone Map (spec §13.4): two-finger pinch, tap opens the code sheet, long-press before a node moves. */
   touch?: {
     onPinchStart: (mid: { x: number; y: number }) => void;
@@ -35,7 +39,7 @@ const KIND = { modified: "Δ modified", added: "Δ added", removed: "Δ removed"
 
 /** Layer bands, edges and nodes, all drawn through the lens; pans on drag, moves a node sideways when dragged by it. */
 export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, panBy, onOpenFile, onInteract, touch, onExpand,
-  onHome, homeName }: Props) {
+  onHome, homeName, quiet, onMore }: Props) {
   const root = useRef<HTMLDivElement>(null);
   const down = useRef<{ x: number; y: number; px: number; py: number; id: number; node: string | null; go: boolean; act: string | null;
                         dragging: boolean; ox: number; oy: number; armed: boolean; timer: number } | null>(null);
@@ -148,6 +152,7 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
         end();
         if (!d || d.dragging || !d.node) return;
         const n = byId.get(d.node);
+        if (n?.kind === "more") { onInteract(); onMore?.(); return; }
         if (d.act) {                                         // a badge or a visitor's home link, not the card
           onInteract();
           if (d.act === "home" && n?.home) onHome?.(n.home, d.node);
@@ -190,6 +195,7 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
           const data = e.kind === "writes" || e.kind === "reads";
           const fx = e.kind === "reads" && landings.has(e.src) && (graph || onPath.has(e.dst));
           const inFlow = pairs.has(`${e.src}>${e.dst}`) || pairs.has(`${e.dst}>${e.src}`);
+          if (quiet && !inFlow && e.src !== front && e.dst !== front && (data || !graph)) return null;
           const my = (p1.y + p2.y) / 2;
           return <path key={i} d={`M${p1.x} ${p1.y} C ${p1.x} ${my}, ${p2.x} ${my}, ${p2.x} ${p2.y}`}
             className={`bd-edge${fx ? " fx" : data ? " data" : ""}${inFlow ? " flow" : ""}${!inFlow && !data && !graph ? " dim" : ""}`} />;
@@ -199,7 +205,8 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
         const p = pos.get(n.id);
         if (!p) return null;
         const card = state.cards[n.id], on = onPath.has(n.id);
-        const cls = ["bd-node", n.change ? "chg" : "", n.kind === "field" ? "field" : "", on ? "onflow" : "", n.home ? "visitor" : "",
+        const cls = ["bd-node", n.change ? "chg" : "", n.kind === "field" || n.kind === "struct" ? "field" : "", n.kind === "more" ? "more" : "",
+          n.note ? "noted" : "", on ? "onflow" : "", n.home ? "visitor" : "",
           !graph && !on && !n.change && !card ? "dim" : "", state.moved[state.layout][n.id] !== undefined ? "moved" : "",
           card ? "has-card" : "", n.id === front ? "front" : "", grab === n.id ? "grab" : ""].filter(Boolean).join(" ");
         const fx = badge.get(n.id);
@@ -209,10 +216,12 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
                         ["--hit" as string]: `${40 / Math.max(p.s, 0.1)}px` }}>
             {n.change && <span className="kind">{KIND[n.change.kind]}</span>}
             <span className="lbl">{n.label}</span>
+            {n.note && <span className="note">{n.note.replace(/`/g, "")}</span>}
+            {!!n.fields?.length && <span className="fields">{n.fields.map((f) => <span key={f.id}>.{f.label}</span>)}</span>}
             {n.change && <span className="stat"><b className="p">+{n.change.add}</b><b className="m">−{n.change.rem}</b></span>}
             {!n.change && n.warn > 0 && <span className="warn-dot">{n.warn}</span>}
             {n.path && n.range && <button className="bd-go" title="Open full file" aria-label={`Open ${n.label} in the file viewer`}>⤢</button>}
-            {fx && landings.has(n.id) && <div className="fxbadge">⚠ {fx}</div>}
+            {fx && landings.has(n.id) && !n.note && <div className="fxbadge">⚠ {fx}</div>}
             {n.home && onHome && <span className="bd-home" data-act="home" role="button" title={`Open ${n.home}'s board`}>
               · {homeName?.(n.home) ?? n.home} ›</span>}
             {onExpand && (!!n.more_callers || !!n.more_callees) && (
```

`frontend/src/board/Board.tsx`:

```diff
diff --git a/frontend/src/board/Board.tsx b/frontend/src/board/Board.tsx
index 50146d6..76a1216 100644
--- a/frontend/src/board/Board.tsx
+++ b/frontend/src/board/Board.tsx
@@ -14,7 +14,7 @@ import { type Action, initialState, reduce } from "./reducer";
 import type { Board as BoardModel } from "./types";
 import PhoneBoard from "./phone/PhoneBoard";
 import PhoneMap from "./phone/PhoneMap";
-import { pinchView, pinchZoom, zoomLens } from "./zoom";
+import { fitZoom, pinchView, pinchZoom, zoomLens } from "./zoom";
 import { useSources } from "./useSources";
 
 interface Props {
@@ -42,6 +42,20 @@ interface Props {
     /** Every cluster, for the phone menu. */
     list: { id: string; name: string }[];
   };
+  /** A story's graph (spec 2026-10-04-change-stories §3.1): no lens, quiet field lines, notes on nodes. */
+  story?: {
+    prefKey: string;
+    /** Story title, ‹ › and tabs, shown in the header. */
+    nav: ReactNode;
+    /** "+N more changed functions": the story's list of them. */
+    onMore: () => void;
+    /** Phone: the Steps tab's content (desktop shows steps on the story page). */
+    steps: ReactNode;
+    /** Phone menu: every story. */
+    list: { id: string; title: string }[];
+    /** Bumped to show the phone's Steps tab ("+N more changed functions"). */
+    showSteps: number;
+  };
   /** A file to open in the viewer on arrival (the overview's file tree). */
   openPath?: string | null;
   /** "+N callers / +N callees"; with `onReset` when the reader has expanded the board. */
@@ -55,7 +69,7 @@ const wideScreen = () => window.innerWidth > 1100;
 const PHONE = "(max-width: 640px)";
 
 /** True while the window is phone-sized (spec §13); follows rotation and resizing. */
-function usePhone() {
+export function usePhone() {
   const [phone, setPhone] = useState(() => window.matchMedia(PHONE).matches);
   useEffect(() => {
     const mq = window.matchMedia(PHONE), on = () => setPhone(mq.matches);
@@ -67,12 +81,15 @@ function usePhone() {
 
 /** The review board (spec §2–§4): flow bar, lensed canvas with cards, file viewer and change panel. */
 export default function Board({ reviewId, board, files, comments, onComments, risk, focus, head: reviewHead, cluster, expansion,
-  openPath }: Props) {
-  const prefKey = cluster?.prefKey ?? reviewId;
-  const head = useCallback((extra: ReactNode) => reviewHead(<>{cluster?.nav}{extra}</>), [reviewHead, cluster?.nav]);
+  openPath, story }: Props) {
+  const prefKey = cluster?.prefKey ?? story?.prefKey ?? reviewId;
+  const nav = cluster?.nav ?? story?.nav;
+  const head = useCallback((extra: ReactNode) => reviewHead(<>{nav}{extra}</>), [reviewHead, nav]);
   const [state, dispatch] = useReducer(reduce, undefined, () => {
-    const s = { ...initialState(loadLens(), loadMovedAll(prefKey), loadLayout(prefKey) ?? (preferDepth(board) ? "depth" : "layers")),
-                about: loadAboutOpen() ?? wideScreen() };        // change panel: remembered, else open on wide screens
+    const lensAt = story ? 0 : loadLens();                // a story graph is small enough to show at full size
+    const s = { ...initialState(lensAt, loadMovedAll(prefKey), loadLayout(prefKey) ?? (preferDepth(board) ? "depth" : "layers")),
+                about: story ? false : loadAboutOpen() ?? wideScreen() };   // change panel: remembered, else open on wide screens
+                                                                             // (a story graph opens with the room for itself)
     return board.flows.length ? s : { ...s, mode: "graph" as const };
   });
   const stateRef = useRef(state);
@@ -85,12 +102,13 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const [hint, setHint] = useState(true);
   const [stage, setStage] = useState<HTMLDivElement | null>(null);   // the canvas element; on phones it mounts with the Map tab
   const phone = usePhone();
-  const [zoom, setZoom] = useState(1);                // phone Map only (spec §13.4)
+  const [zoom, setZoom] = useState(1);                // phone Map, and a story's graph fitted to the canvas (spec §13.4)
   const [sheet, setSheet] = useState<string | null>(null);
   const anim = useRef(0);
 
   useEffect(() => save(keys.moved(prefKey), state.moved), [prefKey, state.moved]);
-  useEffect(() => save(keys.lens, state.view.lens), [state.view.lens]);
+  const quiet = !!story;
+  useEffect(() => { if (!quiet) save(keys.lens, state.view.lens); }, [quiet, state.view.lens]);
   useEffect(() => { const t = window.setTimeout(() => setHint(false), 7000); return () => window.clearTimeout(t); }, []);
   const interact = useCallback(() => setHint(false), []);
 
@@ -98,7 +116,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const bands = useMemo(() => bandsFor(board, state.layout), [board, state.layout]);
   const world = useMemo(() => worldNodes(board, state.layout, state.moved[state.layout]), [board, state.layout, state.moved]);
   const baseLens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
-  const lens = useMemo(() => (phone ? zoomLens(baseLens, zoom, vp) : baseLens), [phone, baseLens, zoom, vp]);
+  const lens = useMemo(() => (phone || story ? zoomLens(baseLens, zoom, vp) : baseLens), [phone, story, baseLens, zoom, vp]);
   const pos = useMemo(() => new Map([...world.values()].map((n) => [n.id, lens.project(n.x, n.y)])), [world, lens]);
 
   const vpRef = useRef(vp);
@@ -138,9 +156,10 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
       if (first && W) {
         first = false;
         const s = stateRef.current, f = board.flows[s.flow];
-        const ids = s.mode === "flows" && f ? f.path : board.nodes.map((n) => n.id);
+        const ids = s.mode === "flows" && f && !story ? f.path : board.nodes.map((n) => n.id);
         const t = centrePan(ids, worldRef.current, W, H);
         if (t) dispatch({ t: "pan", ...t });
+        if (story) { setZoom(fitZoom([...worldRef.current.values()], { W, H })); return; }   // a story's graph opens whole
         const firstChanged = (f?.path ?? []).find((id) => board.nodes.find((n) => n.id === id)?.change)
           ?? board.nodes.find((n) => n.change && n.path && n.range)?.id;
         if (firstChanged && window.innerWidth > 640) dispatch({ t: "card.open", id: firstChanged });
@@ -148,7 +167,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
     });
     ro.observe(el);
     return () => ro.disconnect();
-  }, [stage, board, panBy]);
+  }, [stage, board, panBy, story]);
 
   const act = useCallback((a: Action) => { setHint(false); dispatch(a); }, []);
   const toggleAbout = () => { save(keys.about, !state.about); act({ t: "about.toggle" }); };
@@ -222,7 +241,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const canvas = vp.W > 0 && <>
     <Canvas board={board} lens={lens} pos={pos} vp={vp} bands={bands} state={state} dispatch={act}
             panBy={panBy} onOpenFile={openFile} onInteract={interact} onExpand={expansion?.onExpand}
-            onHome={cluster?.onHome} homeName={cluster?.homeName}
+            onHome={cluster?.onHome} homeName={cluster?.homeName} quiet={quiet} onMore={story?.onMore}
             touch={phone ? { onPinchStart, onPinch, onTap: setSheet } : undefined} />
     {!phone && <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
                           comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />}
@@ -230,6 +249,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   if (phone)
     return (
       <PhoneBoard reviewId={reviewId} board={board} state={state} act={act} sources={sources} comments={comments} clusters={cluster?.list}
+                  steps={story?.steps} stories={story?.list} showSteps={story?.showSteps}
                   onComments={onComments} risk={risk} sideEffects={sideEffects} head={head} onOpenFile={openFile}
                   showMap={showMap}
                   map={
@@ -266,14 +286,16 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
               </span>
               {Object.keys(state.moved[state.layout]).length > 0 &&
                 <button className="bd-ibtn float" onClick={() => act({ t: "layout.reset" })}>Reset layout</button>}
-              <span className="lbl">Lens</span>
-              <span className="bd-seg">
-                {([0, 2, 4] as const).map((m) => (
-                  <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} onClick={() => act({ t: "lens", lens: m })}>
-                    {m ? `${m}×` : "Off"}
-                  </button>
-                ))}
-              </span>
+              {!quiet && <>
+                <span className="lbl">Lens</span>
+                <span className="bd-seg">
+                  {([0, 2, 4] as const).map((m) => (
+                    <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} onClick={() => act({ t: "lens", lens: m })}>
+                      {m ? `${m}×` : "Off"}
+                    </button>
+                  ))}
+                </span>
+              </>}
               {cardCount >= 2 && <button className="bd-ibtn float" onClick={() => act({ t: "card.closeAll" })}>Close all cards</button>}
               {expansion?.onReset && (
                 <button className="bd-ibtn float over" title="Back to the board as built (you added callers or callees)"
```

`frontend/src/board/phone/PhoneBoard.tsx`:

```diff
diff --git a/frontend/src/board/phone/PhoneBoard.tsx b/frontend/src/board/phone/PhoneBoard.tsx
index 7a1b824..e35339d 100644
--- a/frontend/src/board/phone/PhoneBoard.tsx
+++ b/frontend/src/board/phone/PhoneBoard.tsx
@@ -31,23 +31,31 @@ interface Props {
   showMap: number;
   /** A split review's clusters: the menu lists the overview and each cluster's board. */
   clusters?: { id: string; name: string }[];
+  /** A story (spec 2026-10-04-change-stories §5): the first tab shows its steps, the second its graph. */
+  steps?: ReactNode;
+  /** The review's stories, for the menu. */
+  stories?: { id: string; title: string }[];
+  /** Bumped to show the Steps tab. */
+  showSteps?: number;
 }
 
 const TABS: [PhoneTab, string, string][] = [["flows", "☰", "Flows"], ["map", "◎", "Map"], ["files", "▤", "Files"], ["summary", "✦", "Summary"]];
+const STORY_TABS: Record<string, string> = { flows: "Steps", map: "Graph" };
 
 /** The board on a phone (spec §13.2): compact header, one tab at a time, tab bar at the bottom. */
 export default function PhoneBoard(p: Props) {
   const { reviewId, board, state, act } = p;
-  const [tab, setTab] = useState<PhoneTab>(() => loadTab(reviewId) ?? (board.flows.length ? "flows" : "map"));
+  const [tab, setTab] = useState<PhoneTab>(() => (p.steps ? "flows" : loadTab(reviewId) ?? (board.flows.length ? "flows" : "map")));
   const [menu, setMenu] = useState(false);
   const ai = useAi();
-  const choose = (t: PhoneTab) => { setTab(t); save(keys.tab(reviewId), t); };
+  const choose = (t: PhoneTab) => { setTab(t); if (!p.steps) save(keys.tab(reviewId), t); };
   const seen = useRef(state.viewer.reveal?.seq ?? 0);
   useEffect(() => {                                    // opening any file (⤢, picker, summary) shows it in Files
     const seq = state.viewer.reveal?.seq ?? 0;
     if (seq !== seen.current) { seen.current = seq; setTab("files"); }
   }, [state.viewer.reveal]);
   useEffect(() => { if (p.showMap) setTab("map"); }, [p.showMap]);
+  useEffect(() => { if (p.showSteps) setTab("flows"); }, [p.showSteps]);
   const open = (path: string, line: number | null = null) => act({ t: "viewer.open", path, line, wide: false });
 
   return (
@@ -56,9 +64,12 @@ export default function PhoneBoard(p: Props) {
       {menu && (
         <nav className="ph-menu" onClick={() => setMenu(false)}>
           <NavLink to="/">All reviews</NavLink>
+          {p.stories && <NavLink end to={`/r/${reviewId}`}>All stories</NavLink>}
+          {p.stories?.map((s) => <NavLink key={s.id} to={`/r/${reviewId}/s/${s.id}`}>{s.id} · {s.title.replace(/`/g, "")}</NavLink>)}
+          {p.stories && <NavLink to={`/r/${reviewId}/board`}>Boards</NavLink>}
           <NavLink to={`/r/${reviewId}/findings`}>Findings</NavLink>
           <NavLink to={`/r/${reviewId}/cls`}>CLs &amp; Swarm</NavLink>
-          {p.clusters && <NavLink end to={`/r/${reviewId}`}>Overview</NavLink>}
+          {p.clusters && <NavLink end to={`/r/${reviewId}/overview`}>Overview</NavLink>}
           {p.clusters?.map((c) => <NavLink key={c.id} to={`/r/${reviewId}/c/${c.id}`}>{c.id} · {c.name}</NavLink>)}
           {ai?.view?.llm && <button className="link" onClick={() => ai.setUsageOpen(true)}>AI usage</button>}
           <span onClick={(e) => e.stopPropagation()}><ThemeSwitch /></span>
@@ -66,7 +77,8 @@ export default function PhoneBoard(p: Props) {
         </nav>
       )}
       <div className={`ph-body ph-${tab}`}>
-        {tab === "flows" && <FlowReader reviewId={reviewId} board={board} state={state} act={act} sources={p.sources}
+        {tab === "flows" && p.steps}
+        {tab === "flows" && !p.steps && <FlowReader reviewId={reviewId} board={board} state={state} act={act} sources={p.sources}
                                         comments={p.comments} onComments={p.onComments} onOpenFile={p.onOpenFile} />}
         {tab === "map" && p.map}
         {tab === "files" && (state.viewer.files.length ? (
@@ -94,7 +106,7 @@ export default function PhoneBoard(p: Props) {
       <nav className="ph-tabs" role="tablist">
         {TABS.map(([t, icon, label]) => (
           <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => choose(t)}>
-            <i aria-hidden="true">{icon}</i>{label}
+            <i aria-hidden="true">{icon}</i>{(p.steps && STORY_TABS[t]) || label}
           </button>
         ))}
       </nav>
```

`frontend/src/board/ClusterBoard.tsx`:

```diff
diff --git a/frontend/src/board/ClusterBoard.tsx b/frontend/src/board/ClusterBoard.tsx
index ad783cd..f4a0273 100644
--- a/frontend/src/board/ClusterBoard.tsx
+++ b/frontend/src/board/ClusterBoard.tsx
@@ -48,7 +48,7 @@ export default function ClusterBoard({ reviewId, ov, cid, files, comments, onCom
   const go = (to: string) => navigate(`/r/${reviewId}/c/${to}`);
   const nav = (
     <span className="bd-crumb">
-      <Link to={`/r/${reviewId}`}>Overview</Link><span className="sep"> › </span><b>{info?.name ?? cid}</b>
+      <Link to={`/r/${reviewId}/overview`}>Overview</Link><span className="sep"> › </span><b>{info?.name ?? cid}</b>
       <button className="bd-ibtn" aria-label="Previous cluster" onClick={() => go(stepCluster(ov, cid, -1))}>‹</button>
       <span className="pos">{cid} of {ov.clusters.length}</span>
       <button className="bd-ibtn" aria-label="Next cluster" onClick={() => go(stepCluster(ov, cid, 1))}>›</button>
@@ -57,7 +57,7 @@ export default function ClusterBoard({ reviewId, ov, cid, files, comments, onCom
   );
   const cluster = {
     prefKey, nav, homeName: name,
-    onWhole: () => navigate(`/r/${reviewId}`),
+    onWhole: () => navigate(`/r/${reviewId}/overview`),
     onHome: (c: string, node: string) => navigate(`/r/${reviewId}/c/${c}?node=${encodeURIComponent(node)}`),
     list: ov.clusters.map((c) => ({ id: c.id, name: c.name })),
   };
@@ -65,7 +65,7 @@ export default function ClusterBoard({ reviewId, ov, cid, files, comments, onCom
     return (
       <main className="page">
         <div className="banner warn">{error} {expansion.onReset && <button className="link" onClick={expansion.onReset}>Reset</button>}
-          {" "}<Link to={`/r/${reviewId}`}>Back to the overview</Link></div>
+          {" "}<Link to={`/r/${reviewId}/overview`}>Back to the overview</Link></div>
       </main>
     );
   if (!board) return <main className="page muted">Loading {info?.name ?? cid}…</main>;
```

`frontend/src/board/board.css`:

```diff
diff --git a/frontend/src/board/board.css b/frontend/src/board/board.css
index 8f58ff4..06273ce 100644
--- a/frontend/src/board/board.css
+++ b/frontend/src/board/board.css
@@ -401,3 +401,11 @@ details.bd-drift.info { background: var(--bd-sunken); border-left-color: var(--b
   .bd-crumb b { max-width: 34vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
 }
 .bd-about .tree .file .ctag { margin-left: 6px; font-size: 11px; color: var(--bd-muted); border: 1px solid var(--bd-line); border-radius: 99px; padding: 0 6px; }
+
+/* story graphs (spec 2026-10-04-change-stories §3.1): a note under the name, a struct's fields, "+N more" */
+.bd-node .note { display: block; max-width: 260px; overflow: hidden; text-overflow: ellipsis; margin-top: 3px;
+  font: 500 10.5px/1.25 var(--bd-sans); font-style: normal; opacity: .85; }
+.bd-node.chg .note { color: #4a2c00; }
+.bd-node .fields { display: flex; flex-direction: column; margin-top: 4px; font-size: 11px; font-style: normal; opacity: .9; }
+.bd-node.more { border-style: dashed; background: transparent; color: var(--bd-muted); font: 600 12px var(--bd-sans); }
+.bd-node.more:hover { color: var(--bd-ink); }
```

`frontend/src/stories/stories.ts`:

```ts
/** Change stories (spec 2026-10-04-change-stories §3, §5): the list's sections, ‹ › order and a repeated edit's sites. */
import type { Story, StorySet, StorySite } from "../board/types";

export interface Sections {
  behaviour: Story[];
  /** Behaviour stories past the list's limit, listed under "N more behaviour stories". */
  collapsed: Story[];
  other: Story[];
  mechanical: Story[];
  tests: Story[];
}

export function sections(ss: StorySet): Sections {
  const of = (k: Story["kind"]) => ss.stories.filter((s) => s.kind === k);
  return {
    behaviour: of("behaviour").filter((s) => !s.collapsed), collapsed: of("behaviour").filter((s) => s.collapsed),
    other: of("other"), mechanical: of("mechanical"), tests: of("tests"),
  };
}

/** The story `by` places from `sid` in list order, wrapping around. */
export function stepStory(ss: StorySet, sid: string, by: number): string {
  const ids = ss.stories.map((s) => s.id), i = ids.indexOf(sid);
  return ids[(((i < 0 ? 0 : i) + by) % ids.length + ids.length) % ids.length];
}

/** "2 flows · 1 finding · 4 functions" (zero counts left out). */
export function countLine(s: Story): string {
  const c = s.counts, part = (n: number | undefined, one: string, many = `${one}s`) => (n ? `${n} ${n === 1 ? one : many}` : "");
  const parts = s.kind === "mechanical"
    ? [part(c.sites, "site"), part(c.files, "file"), part(c.test_sites, "in tests", "in tests")]
    : [part(c.flows, "flow"), part(c.findings, "finding"), part(c.functions, "function"), part(c.files, "file")];
  return parts.filter(Boolean).join(" · ");
}

export interface SiteFile { path: string; name: string; sites: StorySite[] }
export interface SiteDir { dir: string; files: SiteFile[]; count: number }

/** A repeated edit's sites by directory, then file (in line order); `hideTests` leaves test sites out. */
export function groupSites(sites: StorySite[], hideTests: boolean): SiteDir[] {
  const dirs = new Map<string, Map<string, StorySite[]>>();
  for (const s of sites) {
    if (hideTests && s.test) continue;
    const path = s.path ?? "(unknown file)", cut = path.lastIndexOf("/");
    const dir = cut > 0 ? path.slice(0, cut) : "";
    const files = dirs.get(dir) ?? new Map<string, StorySite[]>();
    files.set(path, [...(files.get(path) ?? []), s]);
    dirs.set(dir, files);
  }
  return [...dirs.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([dir, files]) => {
    const fs = [...files.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([path, ss]) => ({ path, name: path.slice(path.lastIndexOf("/") + 1), sites: [...ss].sort((a, b) => a.line - b.line) }));
    return { dir, files: fs, count: fs.reduce((n, f) => n + f.sites.length, 0) };
  });
}

/** Sites past which files start closed (a very large repeated edit lists files with a count, spec §6). */
export const OPEN_SITES = 200;

/** Where "Whole graph ›" goes: the board holding the story's first node, focused on it. */
export function wholeGraph(reviewId: number, s: Story): string {
  const node = s.nodes[0] ? `?node=${encodeURIComponent(s.nodes[0])}` : "";
  return s.board ? `/r/${reviewId}/c/${s.board}${node}` : `/r/${reviewId}/board${node}`;
}
```

`frontend/src/stories/StoryList.tsx`:

```tsx
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Story, StorySet } from "../board/types";
import { countLine, sections } from "./stories";
import "./stories.css";

/** `code` spans for the backticked names in a story's title or summary. */
export function Ticks({ text }: { text: string }) {
  return <>{text.split("`").map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part))}</>;
}

interface Props {
  reviewId: number;
  stories: StorySet;
  /** The whole change's summary (the boards' "What's this change?"). */
  intent: string | null;
  head: (extra?: ReactNode) => ReactNode;
}

/** `/r/:id` (spec 2026-10-04-change-stories §2.4, §5): the review told as at most 15 stories. */
export default function StoryList({ reviewId, stories, intent, head }: Props) {
  const s = sections(stories);
  const entry = (st: Story, compact = false) => (
    <li key={st.id}>
      <Link to={`/r/${reviewId}/s/${st.id}`} className={`st-entry ${st.kind}${compact ? " compact" : ""}`}>
        <span className="st-top">
          <span className="st-id">{st.id}</span>
          {st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
          {st.kind === "mechanical" && <span className="st-skim">skim</span>}
          <span className="st-title">{st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></span>
        </span>
        {!compact && <span className="st-summary"><Ticks text={st.summary} /></span>}
        <span className="st-counts">{countLine(st)}</span>
      </Link>
    </li>
  );
  return (
    <main className="review stories bd">
      {head()}
      <div className="review-body st-list">
        <p className="st-lead"><Ticks text={stories.summary} /> <Link to={`/r/${reviewId}/board`} className="st-boards">Boards ›</Link></p>
        {intent && <p className="muted st-intent">{intent}</p>}
        {(s.behaviour.length > 0 || s.collapsed.length > 0) && (
          <section aria-label="Behaviour stories">
            <h2>What behaves differently</h2>
            <ol>{s.behaviour.map((st) => entry(st))}</ol>
            {s.collapsed.length > 0 && (
              <details className="st-collapsed">
                <summary>{s.collapsed.length} more behaviour stor{s.collapsed.length === 1 ? "y" : "ies"}</summary>
                <ol>{s.collapsed.map((st) => entry(st))}</ol>
              </details>
            )}
          </section>
        )}
        {s.other.length > 0 && <section aria-label="Other changes"><h2>Other changes</h2><ol>{s.other.map((st) => entry(st))}</ol></section>}
        {s.mechanical.length > 0 && (
          <section aria-label="Repeated edits"><h2>Repeated edits</h2><ol>{s.mechanical.map((st) => entry(st, true))}</ol></section>
        )}
        {s.tests.length > 0 && <section aria-label="Tests"><h2>Tests</h2><ol>{s.tests.map((st) => entry(st))}</ol></section>}
        {!stories.stories.length && <p className="muted">No changed functions. <Link to={`/r/${reviewId}/board`}>Open the board</Link></p>}
      </div>
    </main>
  );
}
```

`frontend/src/stories/StorySteps.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { Comment, Finding } from "../api";
import { CardBody } from "../board/CardLayer";
import { flowSteps } from "../board/phone/flowSteps";
import type { BoardNode, StoryDetail } from "../board/types";
import type { useSources } from "../board/useSources";
import Explain from "../components/Explain";
import { Ticks } from "./StoryList";
import { SeverityBadge } from "../components/Badges";
import "../board/phone/phone.css";

interface Props {
  reviewId: number;
  detail: StoryDetail;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
  findings: Finding[];
  onCite: (id: string) => void;
  /** A node to open (a citation): its step, or its entry under "Also changed". */
  focus: string | null;
}

/** A story's Steps tab (spec 2026-10-04-change-stories §3.1): each flow as numbered steps, then its other changed
 * functions and its findings. Tapping a step or function opens its code inline. */
export default function StorySteps({ reviewId, detail, sources, comments, onComments, findings, onCite, focus }: Props) {
  const { story, board } = detail;
  const flows = useMemo(() => board.flows.filter((f) => story.flows.includes(f.id)), [board, story]);
  const startFlow = Math.max(0, flows.findIndex((f) => focus && f.path.includes(focus)));
  const [fi, setFi] = useState(startFlow);
  const [open, setOpen] = useState<string | null>(focus);
  const refs = useRef(new Map<string, HTMLElement>());
  useEffect(() => {
    if (!focus) return;
    setOpen(focus);
    const i = flows.findIndex((f) => f.path.includes(focus));
    if (i >= 0) setFi(i);
    window.setTimeout(() => refs.current.get(focus)?.scrollIntoView({ block: "center" }), 0);
  }, [focus, flows]);
  const nodes = useMemo(() => new Map(board.nodes.map((n) => [n.id, n])), [board]);
  const flow = flows[Math.min(fi, flows.length - 1)];
  const steps = flow ? flowSteps(board, flow) : [];
  const lands = flow ? nodes.get(flow.lands) : undefined;
  const others = detail.functions.filter((f) => !f.on_flow || !flow);
  const mine = findings.filter((f) => story.findings.includes(f.id));
  const code = (node: BoardNode) => (
    <div className="ph-code">
      <CardBody node={node} reviewId={reviewId} board={board} sources={sources} comments={comments} onComments={onComments} />
    </div>
  );
  const keep = (id: string) => (el: HTMLElement | null) => { if (el) refs.current.set(id, el); };

  return (
    <div className="st-steps">
      {flow && (
        <section aria-label="Flow steps">
          <div className="st-flowbar">
            <b>{flow.title}</b>
            <span className="st-flownav">
              <span className={`bd-tag ${flow.tag}`}>{flow.tag}</span>
              {flows.length > 1 && <button className="bd-ibtn" aria-label="Previous flow" onClick={() => setFi((fi + flows.length - 1) % flows.length)}>‹</button>}
              {flows.length > 1 && <span className="muted">flow {fi + 1} of {flows.length}</span>}
              {flows.length > 1 && <button className="bd-ibtn" aria-label="Next flow" onClick={() => setFi((fi + 1) % flows.length)}>›</button>}
            </span>
          </div>
          {!story.summary.startsWith(flow.what) && (                  // the story's summary already tells its first flow
            <p className="ph-what">{flow.what_source === "llm" && <span className="ai-label">AI</span>}{flow.what}{" "}
              <Explain kind="flow" target={flow.id} has={flow.what_source === "llm"} /></p>
          )}
          <ol className="ph-steps">
            {steps.map((s) => (
              <li key={s.id} ref={keep(s.id)} className={`ph-step ${s.kind}${open === s.id ? " open" : ""}`}>
                <div className="ph-head" onClick={() => s.hasCode && setOpen(open === s.id ? null : s.id)}>
                  <span className="ph-marker">{s.marker}</span>
                  <div className="ph-text"><b>{s.label}</b><span className="ph-reason"><Ticks text={s.node.note || s.reason} /></span></div>
                  {s.hasCode && <span className="ph-caret">{open === s.id ? "▾" : "▸"}</span>}
                </div>
                {open === s.id && code(s.node)}
              </li>
            ))}
          </ol>
          <div className="ph-landing">
            <span className="k">⚠ Side effect lands on {lands?.label}</span>
            {flow.effect}
            <div className="chk">{flow.check}</div>
          </div>
        </section>
      )}
      {others.length > 0 && (
        <section aria-label="Also changed in this story" className="st-also">
          <h3>{flow ? "Also changed in this story" : "Changed in this story"}</h3>
          <ul>
            {others.map((f) => {
              const n = nodes.get(f.node);
              return (
                <li key={f.node} ref={keep(f.node)} className={open === f.node ? "open" : ""}>
                  <div className="ph-head" onClick={() => n?.path && setOpen(open === f.node ? null : f.node)}>
                    <div className="ph-text"><b>{f.label}</b><span className="ph-reason"><Ticks text={f.note} /></span></div>
                    {f.also.map((sid) => (
                      <Link key={sid} className="bd-pill ghost" to={`/r/${reviewId}/s/${sid}`} onClick={(e) => e.stopPropagation()}>
                        also in {sid} ›</Link>
                    ))}
                    {n?.path && <span className="ph-caret">{open === f.node ? "▾" : "▸"}</span>}
                  </div>
                  {open === f.node && n && code(n)}
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {mine.length > 0 && (
        <section aria-label="Findings in this story" className="st-findings">
          <h3>Findings</h3>
          <ul>
            {mine.map((f) => (
              <li key={f.id}><SeverityBadge severity={f.severity} />{" "}
                <button className="link" onClick={() => onCite(f.id)}>{f.id}: {f.title}</button></li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
```

`frontend/src/stories/StoryBodies.tsx`:

```tsx
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Comment } from "../api";
import { CardBody } from "../board/CardLayer";
import type { StoryDetail } from "../board/types";
import type { useSources } from "../board/useSources";
import { Ticks } from "./StoryList";
import { groupSites, OPEN_SITES } from "./stories";

/** A repeated edit (spec 2026-10-04-change-stories §3.2): its sites by directory and file, a "Hide tests" filter and
 * the functions that have other edits too. */
export function MechanicalStory({ reviewId, detail }: { reviewId: number; detail: StoryDetail }) {
  const [hide, setHide] = useState(false);
  const dirs = useMemo(() => groupSites(detail.sites, hide), [detail.sites, hide]);
  const tests = detail.sites.filter((s) => s.test).length;
  const openAll = detail.sites.length <= OPEN_SITES;
  return (
    <div className="st-mech">
      <div className="st-tools">
        {tests > 0 && <label><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> Hide tests ({tests})</label>}
        {detail.also_in.length > 0 && (
          <span>Also in {detail.also_in.length} function{detail.also_in.length === 1 ? "" : "s"} with other edits:{" "}
            {detail.also_in.map((r, i) => (
              <span key={r.node}>{i > 0 && ", "}{r.story ? <Link to={`/r/${reviewId}/s/${r.story}`}>{r.label} ({r.story})</Link> : r.label}</span>
            ))}</span>
        )}
      </div>
      {dirs.map((d) => (
        <section key={d.dir} className="st-dir" aria-label={`Sites in ${d.dir || "the root"}`}>
          <h3>{d.dir || "/"} <span className="muted small">{d.count}</span></h3>
          {d.files.map((f) => (
            <details key={f.path} open={openAll}>
              <summary><b>{f.name}</b> <span className="muted small">{f.sites.length} site{f.sites.length === 1 ? "" : "s"}</span></summary>
              <ul className="st-sites">
                {f.sites.map((s) => (
                  <li key={`${s.line}`}>
                    <span className="st-where">{s.function ?? "outside functions"} · line {s.line}{s.test && <span className="bd-pill ghost">test</span>}</span>
                    <code className="del">− {s.before}</code>
                    <code className="add">+ {s.after}</code>
                    {s.effect && <Link to={`/r/${reviewId}/s/${s.effect}`}>has an effect ›</Link>}
                    {s.other_edits && <Link to={`/r/${reviewId}/s/${s.other_edits}`}>other edits in {s.other_edits} ›</Link>}
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </section>
      ))}
    </div>
  );
}

interface TestsProps {
  reviewId: number;
  detail: StoryDetail;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
}

/** The Tests story (spec §3.3): test functions by file with their diffs; each names the changed code it calls. */
export function TestsStory({ reviewId, detail, sources, comments, onComments }: TestsProps) {
  const [open, setOpen] = useState<string | null>(null);
  const nodes = useMemo(() => new Map(detail.board.nodes.map((n) => [n.id, n])), [detail.board]);
  const byFile = new Map<string, typeof detail.functions>();
  for (const f of detail.functions) {
    const path = nodes.get(f.node)?.path ?? "(unknown file)";
    byFile.set(path, [...(byFile.get(path) ?? []), f]);
  }
  return (
    <div className="st-tests">
      {[...byFile.entries()].map(([path, fns]) => (
        <section key={path} aria-label={`Tests in ${path}`}>
          <h3>{path}</h3>
          <ul>
            {fns.map((f) => {
              const n = nodes.get(f.node);
              return (
                <li key={f.node} className={open === f.node ? "open" : ""}>
                  <div className="ph-head" onClick={() => n?.path && setOpen(open === f.node ? null : f.node)}>
                    <div className="ph-text"><b>{f.label}</b><span className="ph-reason"><Ticks text={f.note} /></span></div>
                    {n?.path && <span className="ph-caret">{open === f.node ? "▾" : "▸"}</span>}
                  </div>
                  {f.calls.length > 0 && (
                    <div className="st-calls">calls {f.calls.map((c, i) => (
                      <span key={c.node}>{i > 0 && ", "}{c.story ? <Link to={`/r/${reviewId}/s/${c.story}?node=${c.node}`}>{c.label} ({c.story})</Link> : c.label}</span>
                    ))}</div>
                  )}
                  {open === f.node && n && (
                    <div className="ph-code">
                      <CardBody node={n} reviewId={reviewId} board={detail.board} sources={sources} comments={comments} onComments={onComments} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
```

`frontend/src/stories/StoryPage.tsx`:

```tsx
import { type ReactNode, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type Comment, type FileChange, type Finding } from "../api";
import Board, { usePhone } from "../board/Board";
import { useExpansion } from "../board/ClusterBoard";
import type { StoryDetail, StorySet } from "../board/types";
import { useSources } from "../board/useSources";
import Explain from "../components/Explain";
import { MechanicalStory, TestsStory } from "./StoryBodies";
import { Ticks } from "./StoryList";
import StorySteps from "./StorySteps";
import { countLine, stepStory, wholeGraph } from "./stories";
import "./stories.css";

interface Props {
  reviewId: number;
  stories: StorySet;
  sid: string;
  files: FileChange[];
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  head: (extra?: ReactNode) => ReactNode;
  findings: Finding[];
  onCite: (id: string) => void;
  /** Bumped when an AI explanation finished: the story is fetched again. */
  reload: number;
}

/** `/r/:id/s/:sid` (spec 2026-10-04-change-stories §3, §5): one story, its Steps first and its graph on a tab;
 * ‹ › to the neighbouring stories. */
export default function StoryPage({ reviewId, stories, sid, files, comments, onComments, risk, head, findings, onCite,
  reload }: Props) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const prefKey = `${reviewId}.${sid}`;
  const { expand, expansion } = useExpansion(prefKey);
  const [detail, setDetail] = useState<StoryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [moreTick, setMoreTick] = useState(0);
  const phone = usePhone();
  const sources = useSources(reviewId, files);
  useEffect(() => {
    let live = true;
    api.story(reviewId, sid, expand).then((d) => { if (live) { setDetail(d); setError(null); } })
      .catch((e) => { if (live) setError(e instanceof ApiError && e.status === 404 ? e.message : String(e.message ?? e)); });
    return () => { live = false; };
  }, [reviewId, sid, expand, reload]);
  const focus = params.get("node");
  useEffect(() => {                                         // a node this story doesn't hold: open the story that does
    if (!detail || !focus || detail.board.nodes.some((n) => n.id === focus)) return;
    const there = stories.node_story[focus];
    if (there && there !== sid) navigate(`/r/${reviewId}/s/${there}?node=${encodeURIComponent(focus)}`, { replace: true });
  }, [detail, focus, stories, reviewId, sid, navigate]);

  const st = detail?.story ?? stories.stories.find((s) => s.id === sid);
  const hasGraph = !!detail?.graph && (st?.kind === "behaviour" || st?.kind === "other");
  const tab = hasGraph && params.get("tab") === "graph" ? "graph" : "steps";
  const setTab = (t: "steps" | "graph") => {
    const q = new URLSearchParams(params);
    if (t === "graph") q.set("tab", "graph"); else q.delete("tab");
    setParams(q, { replace: true });
  };
  const go = (by: number) => navigate(`/r/${reviewId}/s/${stepStory(stories, sid, by)}`);
  const at = stories.stories.findIndex((s) => s.id === sid);
  const nav = (
    <span className="bd-crumb st-crumb">
      <Link to={`/r/${reviewId}`}>Stories</Link><span className="sep"> › </span><b>{sid}</b>
      <button className="bd-ibtn" aria-label="Previous story" onClick={() => go(-1)}>‹</button>
      <span className="pos">{at + 1} of {stories.stories.length}</span>
      <button className="bd-ibtn" aria-label="Next story" onClick={() => go(1)}>›</button>
      {hasGraph && !phone && (
        <span className="bd-seg" role="tablist">
          <button role="tab" aria-selected={tab === "steps"} className={`bd-ibtn${tab === "steps" ? " on" : ""}`} onClick={() => setTab("steps")}>Steps</button>
          <button role="tab" aria-selected={tab === "graph"} className={`bd-ibtn${tab === "graph" ? " on" : ""}`} onClick={() => setTab("graph")}>Graph</button>
        </span>
      )}
      {st && st.kind !== "mechanical" && <Link className="st-whole" to={wholeGraph(reviewId, st)}>Whole graph ›</Link>}
    </span>
  );
  if (error)
    return (
      <main className="review stories bd">{head(nav)}
        <div className="review-body"><div className="banner warn">{error} <Link to={`/r/${reviewId}`}>All stories</Link>
          {expansion.onReset && <> <button className="link" onClick={expansion.onReset}>Reset</button></>}</div></div>
      </main>
    );
  if (!detail || !st) return <main className="page muted">Loading {sid}…</main>;
  const header = (
    <div className="st-head">
      <h2>{st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
        {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
      <p><Ticks text={st.summary} /> {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} />}</p>
      <p className="st-counts">{countLine(st)}</p>
    </div>
  );
  const steps = <StorySteps reviewId={reviewId} detail={detail} sources={sources} comments={comments} onComments={onComments}
                            findings={findings} onCite={onCite} focus={focus} />;
  if (hasGraph && detail.graph && (phone || tab === "graph"))
    return (
      <main className="review board">
        <Board key={sid} reviewId={reviewId} board={detail.graph} files={files} comments={comments} onComments={onComments}
               risk={risk} focus={tab === "graph" ? focus : null} head={head} expansion={expansion}
               story={{ prefKey, nav, steps: <div className="st-phone">{header}{steps}</div>, showSteps: moreTick,
                        onMore: () => { setMoreTick((k) => k + 1); setTab("steps"); },
                        list: stories.stories.map((s) => ({ id: s.id, title: s.title })) }} />
      </main>
    );
  return (
    <main className="review stories bd">
      {head(nav)}
      <div className="review-body st-page">
        {header}
        {st.kind === "mechanical" ? <MechanicalStory reviewId={reviewId} detail={detail} />
          : st.kind === "tests" ? <TestsStory reviewId={reviewId} detail={detail} sources={sources} comments={comments} onComments={onComments} />
          : steps}
      </div>
    </main>
  );
}
```

`frontend/src/stories/stories.css`:

```css
/* Change stories (spec 2026-10-04-change-stories §3, §5); pages carry .bd for the board's colour tokens */
.st-list, .st-page { max-width: 980px; }
.st-lead { font-size: 15px; font-weight: 600; margin: 0 0 6px; }
.st-boards { margin-left: 10px; font-weight: 500; font-size: 13px; }
.st-intent { margin: 0 0 12px; }
.st-list h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .08em; color: var(--bd-muted, #777); margin: 20px 0 8px; }
.st-list ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.st-entry { display: flex; flex-direction: column; gap: 4px; padding: 10px 14px;
  border: 1px solid var(--bd-line, #ddd); border-radius: 12px; background: var(--bd-surface, #fff); color: inherit; text-decoration: none; }
.st-entry:hover { border-color: var(--bd-strong, #333); }
.st-entry .st-id { font: 700 12px var(--bd-mono, monospace); color: var(--bd-muted, #777); }
.st-entry .st-top { display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
.st-entry .st-title { flex: 1 1 320px; font-weight: 600; }
.st-entry .st-summary, .st-entry .st-counts { font-size: 13px; color: var(--bd-muted, #666); }
.st-skim { font: 700 10px var(--bd-sans); letter-spacing: .08em; text-transform: uppercase; color: var(--bd-muted, #666);
  border: 1px solid var(--bd-line, #ddd); border-radius: 999px; padding: 1px 8px; }
.st-entry.compact { padding: 7px 14px; }
.st-entry.compact .st-title { font-weight: 500; }
.st-entry code, .st-head code, .st-lead code, .ph-reason code { font-size: .88em; font-weight: 600; }
.st-collapsed summary { cursor: pointer; margin: 8px 0; color: var(--bd-muted, #666); }
.st-crumb .st-whole { margin-left: 8px; }
.st-head h2 { font-size: 18px; margin: 0 0 6px; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.st-head p { margin: 0 0 6px; }
.st-head .st-counts { color: var(--bd-muted, #666); font-size: 13px; }
.st-steps section { margin-top: 14px; }
.st-flowbar { display: flex; gap: 6px 12px; align-items: center; flex-wrap: wrap; }
.st-flownav { display: inline-flex; gap: 8px; align-items: center; }
.st-also ul, .st-findings ul, .st-tests ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.st-also .ph-head .bd-pill { white-space: nowrap; }
.st-also .ph-code, .st-tests .ph-code, .st-steps .ph-code { margin-top: 6px; }
.st-tools { display: flex; gap: 18px; flex-wrap: wrap; align-items: center; margin: 10px 0; font-size: 13px; }
.st-tools label { display: inline-flex; gap: 6px; align-items: center; margin: 0; }
.st-tools input[type="checkbox"] { width: auto; margin: 0; }
.st-dir h3 { font: 600 13px var(--bd-mono, monospace); margin: 16px 0 6px; }
.st-dir details { margin: 0 0 6px 8px; }
.st-dir summary { cursor: pointer; }
.st-sites { list-style: none; margin: 6px 0 10px; padding: 0 0 0 12px; display: flex; flex-direction: column; gap: 8px; }
.st-sites li { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.st-sites code { display: block; white-space: pre-wrap; word-break: break-all; padding: 2px 6px; border-radius: 4px; }
.st-sites code.del { background: var(--del, #fde8e8); }
.st-sites code.add { background: var(--add, #e6f6e6); }
.st-where { color: var(--bd-muted, #666); }
.st-calls { font-size: 12px; color: var(--bd-muted, #666); margin: 4px 0 0 4px; }
.st-tests h3 { font: 600 13px var(--bd-mono, monospace); margin: 16px 0 6px; }
.st-phone { padding: 10px 12px 24px; overflow: auto; }
@media (max-width: 640px) {
  .st-list, .st-page { padding: 12px 16px; }
  .st-entry .st-title { flex-basis: 100%; }
  .st-head h2 { font-size: 16px; }
}
```

`frontend/src/components/Findings.tsx`:

```diff
diff --git a/frontend/src/components/Findings.tsx b/frontend/src/components/Findings.tsx
index 8bcab80..3e20995 100644
--- a/frontend/src/components/Findings.tsx
+++ b/frontend/src/components/Findings.tsx
@@ -1,6 +1,5 @@
 import { useEffect, useRef, useState } from "react";
 import { api, type Comment, type Finding } from "../api";
-import type { ClusterInfo } from "../board/types";
 import { useMe } from "../App";
 import { SeverityBadge } from "./Badges";
 import CiteText, { CiteList } from "./CiteText";
@@ -15,8 +14,9 @@ interface Props {
   onComments: () => void;
   onFindings: () => void;
   onCite: (id: string) => void;
-  /** A split review's clusters: findings are grouped under them (spec 2026-10-03-large-change-boards §5). */
-  groups?: ClusterInfo[];
+  /** Findings are grouped under a review's stories (spec 2026-10-04-change-stories §5), else a split review's clusters
+   * (spec 2026-10-03-large-change-boards §5). */
+  groups?: { id: string; name: string; finding_ids: string[] }[];
 }
 
 export default function Findings({ reviewId, findings, focus, comments, onComments, onFindings, onCite, groups }: Props) {
```

`frontend/src/pages/Review.tsx`:

```diff
diff --git a/frontend/src/pages/Review.tsx b/frontend/src/pages/Review.tsx
index a696606..09cf165 100644
--- a/frontend/src/pages/Review.tsx
+++ b/frontend/src/pages/Review.tsx
@@ -1,6 +1,7 @@
 import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
 import { Link, Navigate, NavLink, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
-import { api, ApiError, type AiJob, type Board as BoardModel, type Comment, type FileChange, type Finding, type Overview, type ReviewDetail } from "../api";
+import { api, ApiError, type AiJob, type Board as BoardModel, type Comment, type FileChange, type Finding, type Overview, type ReviewDetail,
+  type StorySet } from "../api";
 import { useMe } from "../App";
 import Board from "../board/Board";
 import ClusterBoard, { useExpansion } from "../board/ClusterBoard";
@@ -11,6 +12,8 @@ import ClsPanel from "../components/ClsPanel";
 import Findings from "../components/Findings";
 import Stages from "../components/Stages";
 import { AiProvider, useAiState } from "../lib/ai";
+import StoryList from "../stories/StoryList";
+import StoryPage from "../stories/StoryPage";
 
 const TERMINAL = new Set(["done", "degraded", "failed"]);
 
@@ -22,6 +25,7 @@ export default function Review() {
   const [detail, setDetail] = useState<ReviewDetail | null>(null);
   const [board, setBoard] = useState<BoardModel | null | undefined>(undefined);   // null: no board for this review
   const [overview, setOverview] = useState<Overview | null | undefined>(undefined);  // a split review's (null: one board)
+  const [stories, setStories] = useState<StorySet | null | undefined>(undefined);    // null: a review run before stories
   const [reload, setReload] = useState(0);              // cluster boards fetch again after an AI explanation
   const [findings, setFindings] = useState<Finding[]>([]);
   const [files, setFiles] = useState<FileChange[]>([]);
@@ -32,14 +36,16 @@ export default function Review() {
   const loadDetail = useCallback(() => api.review(id).then(setDetail).catch((e) => setError(String(e.message ?? e))), [id]);
   const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
   const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
+  const loadStories = useCallback(() => api.stories(id).then(setStories)
+    .catch((e) => { if (e instanceof ApiError && e.status === 404) setStories(null); else throw e; }), [id]);
   const loadResults = useCallback(() => Promise.all([
     api.overview(id).then((ov) => { setOverview(ov); setBoard(null); }).catch((e) => {
       if (!(e instanceof ApiError && e.status === 404)) throw e;
       setOverview(null);
       return api.board(id).then(setBoard).catch((e2) => { if (e2 instanceof ApiError && e2.status === 404) setBoard(null); else throw e2; });
     }),
-    loadFindings(), api.files(id).then(setFiles), loadComments(),
-  ]).catch((e) => setError(String(e.message ?? e))), [id, loadFindings, loadComments]);
+    loadStories(), loadFindings(), api.files(id).then(setFiles), loadComments(),
+  ]).catch((e) => setError(String(e.message ?? e))), [id, loadFindings, loadComments, loadStories]);
 
   useEffect(() => { loadDetail(); }, [loadDetail]);
 
@@ -66,7 +72,8 @@ export default function Review() {
       else api.board(id).then(setBoard).catch(() => {});
     }
     if (jobs.some((j) => j.kind === "finding")) loadFindings();
-  }, [id, loadFindings, overview]);
+    if (jobs.some((j) => j.kind === "story")) { loadStories(); setReload((k) => k + 1); }
+  }, [id, loadFindings, loadStories, overview]);
   const ai = useAiState(id, ready, people, comments.some((c) => c.ai_meta?.pending), onAiDone, loadComments);
 
   const onCite = useCallback((cite: string) => {
@@ -89,7 +96,10 @@ export default function Review() {
       {board && <span className="bd-pill ghost">{board.flows.length} flows · {findings.length} findings</span>}
       {ready && <AiPill />}
       <nav aria-label="Review sections">
-        <NavLink end to={`/r/${id}`} className={({ isActive }) => (isActive ? "on" : "")}>Board</NavLink>
+        {stories ? <>
+          <NavLink end to={`/r/${id}`} className={({ isActive }) => (isActive ? "on" : "")}>Stories</NavLink>
+          <NavLink to={`/r/${id}/${overview ? "overview" : "board"}`} className={({ isActive }) => (isActive ? "on" : "")}>Boards</NavLink>
+        </> : <NavLink end to={`/r/${id}`} className={({ isActive }) => (isActive ? "on" : "")}>Board</NavLink>}
         <NavLink to={`/r/${id}/findings`} className={({ isActive }) => (isActive ? "on" : "")}>Findings ({findings.length})</NavLink>
         <NavLink to={`/r/${id}/cls`} className={({ isActive }) => (isActive ? "on" : "")}>CLs &amp; Swarm</NavLink>
       </nav>
@@ -110,10 +120,7 @@ export default function Review() {
 
   if (!ready)
     return page(<><Stages stages={detail.stages} /><p className="muted">Analysis in progress…</p></>);
-  return (
-    <AiProvider value={ai}>
-    <Routes>
-      <Route index element={overview ? (
+  const boardsEl = overview ? (
         params.get("node") ? <Locate reviewId={id} node={params.get("node")!} /> : (
           <main className="review board">
             <OverviewPage reviewId={id} ov={overview} comments={comments} onComments={loadComments} risk={r.risk} head={head}
@@ -129,17 +136,33 @@ export default function Review() {
           {me?.is_owner ? " Re-run it to build one." : " The owner can re-run it to build one."} Findings and CLs are still available.
           {me?.is_owner && <> <button onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button></>}
         </div>
-      ))} />
+      ));
+  return (
+    <AiProvider value={ai}>
+    <Routes>
+      <Route index element={stories ? (params.get("node") ? <StoryLocate reviewId={id} node={params.get("node")!} stories={stories} /> : (
+        <StoryList reviewId={id} stories={stories} intent={(board ?? overview)?.about.intent ?? null} head={head} />
+      )) : stories === undefined ? page(<p className="muted">Loading…</p>) : boardsEl} />
+      <Route path="board" element={boardsEl} />
+      <Route path="overview" element={boardsEl} />
+      <Route path="s/:sid" element={stories ? (
+        <StoryRoute reviewId={id} stories={stories} files={files} comments={comments} onComments={loadComments} risk={r.risk}
+                    head={head} findings={findings} onCite={onCite} reload={reload} />
+      ) : page(stories === null
+        ? <p className="muted">This review has no stories: re-run it. <Link to={`/r/${id}`}>Open the board</Link></p>
+        : <p className="muted">Loading…</p>)} />
       <Route path="c/:cid" element={overview ? (
         <ClusterRoute reviewId={id} ov={overview} files={files} comments={comments} onComments={loadComments} risk={r.risk}
                       head={head} reload={reload} />
       ) : page(overview === null
-        ? <p className="muted">This review is shown as one board. <Link to={`/r/${id}`}>Open the board</Link></p>
+        ? <p className="muted">This review is shown as one board. <Link to={`/r/${id}/board`}>Open the board</Link></p>
         : <p className="muted">Loading…</p>)} />
       <Route path="findings" element={page(
-        <Findings reviewId={id} findings={findings} focus={focus} comments={comments} groups={overview?.clusters}
+        <Findings reviewId={id} findings={findings} focus={focus} comments={comments}
+                  groups={stories ? stories.stories.map((st) => ({ id: st.id, name: st.title.replace(/`/g, ""), finding_ids: st.findings }))
+                    : overview?.clusters}
                   onComments={loadComments} onFindings={loadFindings} onCite={onCite} />)} />
-      <Route path="files" element={<Navigate to={`/r/${id}`} replace />} />
+      <Route path="files" element={<Navigate to={`/r/${id}/board`} replace />} />
       <Route path="cls" element={page(<ClsPanel reviewId={id} cls={detail.cls} onChange={loadDetail} />)} />
     </Routes>
     </AiProvider>
@@ -159,6 +182,18 @@ function Locate({ reviewId, node }: { reviewId: number; node: string }) {
   return <main className="page muted">{missing ? `${node} isn't on any board of this review.` : `Finding ${node}…`}</main>;
 }
 
+/** `/r/:id?node=N12` on a review with stories: open the story holding the node (spec 2026-10-04-change-stories §5). */
+function StoryLocate({ reviewId, node, stories }: { reviewId: number; node: string; stories: StorySet }) {
+  const sid = stories.node_story[node];
+  if (sid) return <Navigate replace to={`/r/${reviewId}/s/${sid}?node=${encodeURIComponent(node)}`} />;
+  return <Navigate replace to={`/r/${reviewId}/board?node=${encodeURIComponent(node)}`} />;
+}
+
+function StoryRoute(p: Omit<Parameters<typeof StoryPage>[0], "sid">) {
+  const sid = useParams().sid!;
+  return <StoryPage key={sid} {...p} sid={sid} />;
+}
+
 /** A review shown as one board; "+N callers" fetches it again with the expansions (spec §3). */
 function SingleBoard({ board, ...p }: Omit<Parameters<typeof Board>[0], "expansion">) {
   const { expand, expansion } = useExpansion(p.reviewId);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/stories src/board/zoom.test.ts && npx tsc --noEmit && npm run build && npx playwright test e2e/stories.spec.ts`
Expected: `Tests  11 passed (11)` and `✓ built in …` and `6 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx playwright test`
Expected: `Tests  102 passed (102)`, no `tsc` output, `✓ built in …` and `54 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/types.ts frontend/src/api.ts frontend/src/board/zoom.ts frontend/src/board/layout.ts frontend/src/board/phone/flowSteps.ts frontend/src/board/FlowBar.tsx frontend/src/board/CardLayer.tsx frontend/src/board/Canvas.tsx frontend/src/board/Board.tsx frontend/src/board/phone/PhoneBoard.tsx frontend/src/board/ClusterBoard.tsx frontend/src/board/board.css frontend/src/stories/stories.ts frontend/src/stories/StoryList.tsx frontend/src/stories/StorySteps.tsx frontend/src/stories/StoryBodies.tsx frontend/src/stories/StoryPage.tsx frontend/src/stories/stories.css frontend/src/components/Findings.tsx frontend/src/pages/Review.tsx frontend/src/stories/stories.test.ts frontend/src/board/zoom.test.ts frontend/e2e/helpers.ts frontend/e2e/stories.spec.ts frontend/e2e/ai.spec.ts frontend/e2e/board.spec.ts frontend/e2e/landing.spec.ts frontend/e2e/large.spec.ts frontend/e2e/panel-diff.spec.ts frontend/e2e/phone.spec.ts
git commit -m "feat(ui): a review opens on its stories — list, steps, a 12-node graph, repeated edits by file — desktop and phone"
```

---

## Finish

- [ ] Run everything: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q` (expected `421 passed, 1 skipped`), and
  `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx playwright test` (expected `Tests  102 passed (102)` and `54 passed`).
- [ ] At size, by hand (lab README, "Change stories"): review libgit2-big CL 2 (#6896) and open the review page. Expected: 4 stories, the summary "Mostly mechanical: 180 of 187 changed lines are 2 repeated edits". S3 is `git_vector_free` → `git_vector_dispose` at 152 sites in 52 files (47 in tests). Every story graph has at most 12 nodes, and no label holds an absolute path. On a phone, the list comes first, and a story's Graph tab opens with the whole graph in view.
