# Review Board (M1.5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the M1 storyboard, call-flow and blast-radius tabs with one review board: a zoomable, lensed map of the call graph by layer, where numbered flows trace entry → change → where the side effect lands, changed functions open as floating diffs with inline annotations and comments, any other function's code is fetched on demand, and a "What's this change?" panel summarises intent and files.

**Architecture:** The backend gains a deterministic `board` stage (after `detectors`) that turns facts, the impact model and findings into one `Board` blob: nodes with layers and initial x, flows, per-line impact annotations and a change summary; the LLM stage runs its calls in parallel and rewrites flow narratives and the intent when grounded. Two endpoints serve the board and any workspace file (`p4 print` at the have revision). The frontend draws the board with custom DOM + SVG through pure lens functions, with every interaction a transition of one reducer.

**Tech Stack:** Backend: Python ≥3.12, FastAPI, pydantic v2, libclang facts, `concurrent.futures` for LLM calls, pytest, ruff. Frontend: React 19, TypeScript 5.9 (strict), Vite 8, vitest 5 (node environment, `src/**/*.test.ts`), jsdiff, Playwright. No new dependencies; Cytoscape is removed.

**Spec:** `docs/superpowers/specs/2026-10-01-review-board-design.md` (§8 records decisions made while validating this plan; it overrides earlier sections where they differ). Design reference: `docs/design/board-prototype.html`.

**Provenance:** every code block in this plan was run before the plan was written, first on the uart fixture and then on the libgit2 lab's planted CLs. The tasks were then replayed in order on a fresh tree from `main`: each task's tests failed before its implementation and passed after it, and the backend suite with ruff (or the frontend unit tests with `tsc`) stayed green after every task. The replayed tree is byte-identical to the validated one. Expected outputs below come from that replay. New files are given in full; changes to existing files are given as unified diffs against the state the previous task left (apply with `git apply`, or by hand).

## Global Constraints

- **Paths:** relative to the repository root. Backend commands run in `backend/`, frontend commands in `frontend/`.
- **Dependencies:** none added. Task 11 removes `cytoscape` and `cytoscape-elk`. No fonts or scripts from a CDN: the app is self-hosted on internal networks.
- **Board model vocabulary:** flow tags `state|contract` (signature flows are `contract`); annotation channels `contract|state|signature`; annotation severities `warn|info|ok`; change counts `{kind, add, rem}`.
- **Config defaults:** `analysis.max_flows = 12`, `analysis.board_max_nodes = 150`, `analysis.board_blast_nodes = 60`, `llm.concurrency = 4`, `llm.max_flow_narratives = 6`.
- **Lens constants:** `BAND = 210` world px per layer, `FLAT = 0.55`, `FOLD = {2: 1.8, 4: 3.4}`, `PAD = 140`, local-scale floor 0.34, node scale `max(0.36, min(1, kx)·(0.45 + 0.55v))`, card scale floor 0.55, vertical squeeze to 0.7 (2×) / 0.55 (4×), `X_SPACING = 220`.
- **Gestures:** canvas drag starts after 6 px (pointer capture only once dragging), card-header drag after 4 px; dragging never selects text.
- **Source on demand:** only files inside the workspace (403 otherwise), never binary (415), at most 2 MiB (413); Perforce access stays read-only through `P4Runner` (`fstat`, `print`, `where`). Paths outside the workspace root are never sent to `p4 where`.
- **Per-viewer preferences:** `localStorage` keys `ct.board.<reviewId>.moved`, `ct.panel.viewerW`, `ct.panel.aboutW`, `ct.lens`; every access in try/catch; nothing about layout goes to the server.
- **Comments:** line anchors are `{path, side: "new"|"old", line}` with the depot path (`cl` added for per-CL diffs); M1 anchors `{depot, cl: null, side, line}` must still match.
- **CSS:** every board class is `bd-` prefixed or nested under `.bd`; the board keeps its light palette in dark mode.
- **Tests:** test code (`tests/`, `test/`, `testing/`, `fuzzers/`) is never a flow entry or a board blast node.
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).

## Review Focus

Inputs the spec implies but does not spell out that are most likely to bite a real user, most likely first. Each is pinned by a test in the task that owns the code.

1. **System and toolchain headers among a board's files** (`/usr/include/...`, vendor sysroots): one such path made the lab's whole `p4 where` batch fail. Only workspace paths may be sent; a failed lookup must degrade, not break, the board. Pinned by `test_depot_resolver_asks_the_source_only_about_workspace_files` and `test_depot_resolver_failure_keeps_changed_files_and_notes_why` (Task 4).
2. **Crafted `path` on `/source`** (`//fixture/../../etc/passwd`, another depot, a file not in the workspace): must be 403, never a read. Pinned by `test_source_endpoint_refuses_paths_outside_the_workspace` (Task 5) and `test_read_workspace_file_and_refuse_escapes` / `test_read_unchanged_file_at_have_revision` (Task 2).
3. **Functions whose only callers are tests:** common for library APIs; flows must start at the API, not at a test, and tests must not crowd the board. Pinned by `test_tests_are_neither_flow_entries_nor_blast_nodes` and `test_flows_start_at_a_real_caller_when_there_is_one` (Task 3).
4. **Browsers with blocked, full or corrupted storage** (private windows, locked-down machines): the board must open with defaults. Pinned by `prefs.test.ts` › "falls back when storage throws or holds junk" (Task 9).
5. **Existing M1 line comments** (made on the cumulative Files diff before this change): they must still show in the Files tab and on the board. Pinned by `anchors.test.ts` (Task 10) and the board check in `e2e/smoke.spec.ts` (Task 11).

---

### Task 1: Facts: return-value lines and field declaration lines

Board annotations need the line of each new return value (`return -2;`) and the line where a field is declared (so the
field's node can show its declaration and carry the "new writer" note). Both come from the clang extractor:
`Function.return_lines` maps each evaluated return constant to its first line; `FieldAccess.decl_line` is the
`FieldDecl` line inside `record_file`. The alias-flow pass is what builds `FieldAccess`, so it records `decl_line` next to
the `record_file` it already tracks.

**Files:**
- Modify: `backend/codetortoise/facts/model.py`
- Modify: `backend/codetortoise/facts/clang_extractor.py`
- Modify: `backend/codetortoise/facts/aliasflow.py`
- Modify: `backend/tests/test_clang_extractor.py`

**Interfaces:**
- Produces: `Function.return_lines: dict[str, int]` (value → first line, e.g. `{"-2": 18, "0": 24}` for `uart_send`);
  `FieldAccess.decl_line: int = 0` (line in `record_file`, `0` when unknown).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_clang_extractor.py`:

```diff
diff --git a/backend/tests/test_clang_extractor.py b/backend/tests/test_clang_extractor.py
index f46ee31..d18dfff 100644
--- a/backend/tests/test_clang_extractor.py
+++ b/backend/tests/test_clang_extractor.py
@@ -94,3 +94,12 @@ def test_load_failure_retries_with_safe_flag_subset(fx):
     assert {f.qualname for f in facts.functions} == {"hal_read", "hal_write"}
     assert "--target=vendorarch-none-elf" in facts.tu.stripped_flags
     assert all(not d.startswith("None") for d in facts.tu.diagnostics)
+
+
+def test_return_lines_and_field_declaration_lines(fx, fx_source):
+    uart = fx_source.load([101]).files[0]
+    facts = extract_tu(TuRequest(file=uart.local, args=args(fx), variant="after", unsaved={uart.local: uart.after}))
+    fn = {f.qualname: f for f in facts.functions}["uart_send"]
+    assert fn.return_lines == {"-2": 18, "0": 24}
+    errors = [a for a in facts.fields if a.field_name == "errors" and a.fn == fn.usr]
+    assert errors and all(a.decl_line == 14 and a.record_file.endswith("driver/uart.h") for a in errors)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_clang_extractor.py -q`
Expected: FAIL — `AttributeError: 'Function' object has no attribute 'return_lines'` — `1 failed, 8 passed`

- [ ] **Step 3: Implement**

`backend/codetortoise/facts/model.py`:

```diff
diff --git a/backend/codetortoise/facts/model.py b/backend/codetortoise/facts/model.py
index 61eee6b..e3dc797 100644
--- a/backend/codetortoise/facts/model.py
+++ b/backend/codetortoise/facts/model.py
@@ -30,6 +30,7 @@ class Function(BaseModel):
     is_static: bool = False
     returns: list[str] = Field(default_factory=list)
     return_names: dict[str, str] = Field(default_factory=dict)  # value -> macro/enum name, where known
+    return_lines: dict[str, int] = Field(default_factory=dict)  # value -> first line returning it
 
 
 class CallEdge(BaseModel):
@@ -51,6 +52,7 @@ class FieldAccess(BaseModel):
     field_name: str
     record: str
     record_file: str = ""  # file declaring the record (restricts heuristic name matches)
+    decl_line: int = 0     # line of the field's declaration in record_file
     path: str             # display access path, e.g. "u.stats.tx"
     root_kind: Literal["param", "this", "global", "local", "unknown"]
     mode: Literal["read", "write", "may_write"]
```

`backend/codetortoise/facts/clang_extractor.py`:

```diff
diff --git a/backend/codetortoise/facts/clang_extractor.py b/backend/codetortoise/facts/clang_extractor.py
index 69bbc98..3e61cc1 100644
--- a/backend/codetortoise/facts/clang_extractor.py
+++ b/backend/codetortoise/facts/clang_extractor.py
@@ -71,6 +71,7 @@ def function_fact(c: ci.Cursor) -> Function:
     usr = c.get_usr()
     returns: list[str] = []
     names: dict[str, str] = {}
+    lines: dict[str, int] = {}
     for r in c.walk_preorder():
         if r.kind == K.RETURN_STMT:
             kids = list(r.get_children())
@@ -78,13 +79,14 @@ def function_fact(c: ci.Cursor) -> Function:
                 lit = literal_text(kids[0])
                 if lit is not None and lit not in returns:
                     returns.append(lit)
+                    lines[lit] = r.location.line
                 if lit is not None and lit not in names and (name := constant_name(kids[0])):
                     names[lit] = name
     return Function(
         usr=usr, qualname=qual, name=c.spelling, signature=sig, return_type=rt, params=params,
         file=_norm(c.location.file.name), start_line=c.extent.start.line, end_line=c.extent.end.line,
         is_virtual=is_virtual, method_key=usr.split("@F@", 1)[-1] if is_virtual else None,
-        is_static=c.storage_class == ci.StorageClass.STATIC, returns=returns, return_names=names)
+        is_static=c.storage_class == ci.StorageClass.STATIC, returns=returns, return_names=names, return_lines=lines)
 
 
 _WRAP = {K.UNEXPOSED_EXPR, K.PAREN_EXPR}
```

`backend/codetortoise/facts/aliasflow.py`:

```diff
diff --git a/backend/codetortoise/facts/aliasflow.py b/backend/codetortoise/facts/aliasflow.py
index 05f9555..59e53f6 100644
--- a/backend/codetortoise/facts/aliasflow.py
+++ b/backend/codetortoise/facts/aliasflow.py
@@ -233,12 +233,14 @@ class FunctionAnalyzer:
             self.params[p.get_usr()] = (i, p)
         self.alias: dict[str, set[AP]] = {}
         self.field_files: dict[str, str] = {}  # FieldDecl USR -> canonical file declaring it
+        self.field_lines: dict[str, int] = {}  # FieldDecl USR -> declaration line
         self.fresh: set[str] = set()  # local pointers holding freshly allocated objects
 
     def _field_file(self, f: ci.Cursor) -> str:
         usr = f.get_usr()
         if usr not in self.field_files:
             self.field_files[usr] = canon(f.location.file.name) if f.location.file else ""
+            self.field_lines[usr] = f.location.line
         return self.field_files[usr]
 
     # ---- path resolution -------------------------------------------------
@@ -397,7 +399,8 @@ class FunctionAnalyzer:
                     via = list(a.via) + ([extra_via] if extra_via else [])
                     fields.append(FieldAccess(
                         fn=self.fn_usr, field=fstep[0], field_name=fstep[1], record=fstep[2],
-                        record_file=self.field_files.get(fstep[0], ""), path=a.display(), root_kind=a.root_kind, mode=mode, via=via,
+                        record_file=self.field_files.get(fstep[0], ""),
+                        decl_line=self.field_lines.get(fstep[0], 0), path=a.display(), root_kind=a.root_kind, mode=mode, via=via,
                         file=file, line=line, confidence="may" if (a.may or mode == "may_write") else "precise"))
                     emitted = True
                 elif not a.steps and a.root_kind == "global" and mode != "may_write":
@@ -412,7 +415,8 @@ class FunctionAnalyzer:
                     fields.append(FieldAccess(
                         fn=self.fn_usr, field=f.get_usr(), field_name=f.spelling,
                         record=f.semantic_parent.spelling if f.semantic_parent else "",
-                        record_file=self._field_file(f), path="?." + f.spelling, root_kind="unknown", mode=mode,
+                        record_file=self._field_file(f),
+                        decl_line=f.location.line, path="?." + f.spelling, root_kind="unknown", mode=mode,
                         via=[extra_via] if extra_via else [], file=file, line=line, confidence="may"))
 
         for c in self.fn.walk_preorder():
@@ -453,7 +457,8 @@ class FunctionAnalyzer:
                 fields.append(FieldAccess(
                     fn=self.fn_usr, field=f.get_usr(), field_name=f.spelling,
                     record=f.semantic_parent.spelling if f.semantic_parent else "",
-                    record_file=self._field_file(f), path=path, root_kind=root, mode="read", file=file, line=c.location.line,
+                    record_file=self._field_file(f),
+                    decl_line=f.location.line, path=path, root_kind=root, mode="read", file=file, line=c.location.line,
                     confidence="precise" if aps else "may"))
             elif (c.kind == K.DECL_REF_EXPR and c.referenced is not None and c.referenced.kind == K.VAR_DECL
                   and c.hash not in write_targets):
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_clang_extractor.py -q`
Expected: `9 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `139 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/facts/model.py backend/codetortoise/facts/clang_extractor.py backend/codetortoise/facts/aliasflow.py backend/tests/test_clang_extractor.py
git commit -m "feat(facts): record return-value lines and field declaration lines"
```

---

### Task 2: Source: read unchanged files and map local paths to depot paths

Context cards and the file viewer show functions in files the change does not touch, fetched on demand from the base
workspace (spec §5.4). The `Source` protocol gains `read(depot)` (text at the workspace's have revision) and
`depots_for(locals)` (depot path for each canonical local path, in one call). `P4Source` uses `p4 fstat` + `p4 print`
and one `p4 where`; `GitFixtureSource` (tests, fixture demo) maps `//fixture/<rel>` to the workspace. Both refuse
anything outside the workspace (`SourceNotAllowed`), binary files (`SourceBinary`) and files over 2 MiB
(`SourceTooLarge`).

**Files:**
- Modify: `backend/codetortoise/vcs/model.py`
- Modify: `backend/codetortoise/vcs/source.py`
- Modify: `backend/codetortoise/vcs/gitfixture.py`
- Modify: `backend/codetortoise/vcs/p4source.py`
- Modify: `backend/tests/test_gitfixture.py`
- Modify: `backend/tests/test_p4source.py`

**Interfaces:**
- Produces: `SourceFile{depot, local, rev, text}` in `codetortoise/vcs/model.py`; in `codetortoise/vcs/source.py`
  `MAX_SOURCE_BYTES = 2 * 1024 * 1024`, `SourceNotAllowed`, `SourceBinary`, `SourceTooLarge` (all `SourceError`), and on
  the `Source` protocol `depots_for(locals_: list[str]) -> dict[str, str]` and `read(depot: str) -> SourceFile`.
- `GitFixtureSource.DEPOT_PREFIX = "//fixture/"`; its `rev` is `"workspace"`. `P4Source.read` returns `rev="#<haveRev>"`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_gitfixture.py`:

```diff
diff --git a/backend/tests/test_gitfixture.py b/backend/tests/test_gitfixture.py
index deb38e2..6aa5a9a 100644
--- a/backend/tests/test_gitfixture.py
+++ b/backend/tests/test_gitfixture.py
@@ -31,3 +31,28 @@ def test_drift_when_workspace_differs(tmp_path, fx):
     (ws / "driver/uart.c").write_text("/* locally modified */\n")
     cs = GitFixtureSource(ws).load([101])
     assert [d.depot for d in cs.drift] == ["//fixture/driver/uart.c"]
+
+
+def test_read_workspace_file_and_refuse_escapes(fx, tmp_path):
+    from codetortoise.vcs.source import SourceBinary, SourceNotAllowed, SourceTooLarge
+    src = GitFixtureSource(fx.root)
+    f = src.read("//fixture/service/logger.c")
+    assert f.text.startswith('#include "service/logger.h"') and f.rev == "workspace"
+    assert f.local == str((fx.root / "service/logger.c").resolve())
+    for bad in ("//fixture/../../etc/passwd", "//elsewhere/x.c", "//fixture/does/not/exist.c"):
+        with pytest.raises(SourceNotAllowed):
+            src.read(bad)
+    ws = tmp_path / "ws"
+    shutil.copytree(fx.root, ws, symlinks=True)
+    (ws / "blob.bin").write_bytes(b"\x00\x01binary")
+    (ws / "big.c").write_text("x" * (2 * 1024 * 1024 + 1))
+    with pytest.raises(SourceBinary):
+        GitFixtureSource(ws).read("//fixture/blob.bin")
+    with pytest.raises(SourceTooLarge):
+        GitFixtureSource(ws).read("//fixture/big.c")
+
+
+def test_depots_for_workspace_paths(fx):
+    root = str(fx.root.resolve())
+    assert GitFixtureSource(fx.root).depots_for([f"{root}/driver/uart.c", "/elsewhere/x.c"]) == {
+        f"{root}/driver/uart.c": "//fixture/driver/uart.c"}
```

`backend/tests/test_p4source.py`:

```diff
diff --git a/backend/tests/test_p4source.py b/backend/tests/test_p4source.py
index 72bd961..4af8d0e 100644
--- a/backend/tests/test_p4source.py
+++ b/backend/tests/test_p4source.py
@@ -145,3 +145,45 @@ def test_login_check_can_request_host_unlocked_ticket(monkeypatch):
     assert seen[-1][-3:] == ["login", "-p", "-a"]
     r.login_check("bob", "pw")
     assert seen[-1][-2:] == ["login", "-p"]
+
+
+class FstatP4(FakeP4):
+    def __init__(self, fstat, files):
+        super().__init__(describe={}, files=files)
+        self.fstat = fstat
+
+    def run(self, command, *args):
+        if command == "fstat":
+            rec = self.fstat.get(args[-1])
+            return [rec] if rec else []
+        return super().run(command, *args)
+
+
+def test_read_unchanged_file_at_have_revision():
+    from codetortoise.vcs.source import SourceBinary, SourceNotAllowed
+    p4 = FstatP4({"//depot/a.c": {"depotFile": "//depot/a.c", "clientFile": "/ws/a.c", "haveRev": "7", "headType": "text"},
+                  "//depot/img.bin": {"depotFile": "//depot/img.bin", "clientFile": "/ws/img.bin", "haveRev": "1",
+                                      "headType": "binary"},
+                  "//depot/unsynced.c": {"depotFile": "//depot/unsynced.c", "clientFile": "/ws/unsynced.c", "headType": "text"}},
+                 files={"//depot/a.c#7": "int a;\n"})
+    src = P4Source(p4).read("//depot/a.c")
+    assert (src.depot, src.local, src.rev, src.text) == ("//depot/a.c", "/ws/a.c", "#7", "int a;\n")
+    with pytest.raises(SourceBinary):
+        P4Source(p4).read("//depot/img.bin")
+    with pytest.raises(SourceNotAllowed):
+        P4Source(p4).read("//depot/unsynced.c")      # not synced in the base workspace
+    with pytest.raises(SourceNotAllowed):
+        P4Source(p4).read("//other/x.c")             # not in the client view
+
+
+def test_depots_for_maps_local_paths_in_one_where_call():
+    class WhereP4(FakeP4):
+        def run(self, command, *args):
+            self.calls.append((command, *args))
+            assert command == "where"
+            return [{"depotFile": "//depot" + a[len("/ws"):], "path": a} for a in args if a.startswith("/ws/")]
+    p4 = WhereP4(describe={}, files={})
+    assert P4Source(p4).depots_for(["/ws/a.c", "/ws/b/c.h", "/elsewhere/x.c"]) == {
+        "/ws/a.c": "//depot/a.c", "/ws/b/c.h": "//depot/b/c.h"}
+    assert len(p4.calls) == 1
+    assert P4Source(p4).depots_for([]) == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_gitfixture.py tests/test_p4source.py -q`
Expected: FAIL — `4 failed, 11 passed` (`GitFixtureSource`/`P4Source` have no `read` or `depots_for`; `SourceFile` does not exist)

- [ ] **Step 3: Implement**

`backend/codetortoise/vcs/model.py`:

```diff
diff --git a/backend/codetortoise/vcs/model.py b/backend/codetortoise/vcs/model.py
index 84d99a8..2fa0649 100644
--- a/backend/codetortoise/vcs/model.py
+++ b/backend/codetortoise/vcs/model.py
@@ -36,6 +36,13 @@ class DriftItem(BaseModel):
     actual: str
 
 
+class SourceFile(BaseModel):
+    depot: str
+    local: str
+    rev: str       # p4: "#<have rev>"; git fixture: "workspace"
+    text: str
+
+
 class ChangeSet(BaseModel):
     cls: list[ClMeta]
     files: list[FileChange]
```

`backend/codetortoise/vcs/source.py` (replace the whole file):

```python
"""VCS source protocol."""
from __future__ import annotations

from typing import Protocol

from codetortoise.vcs.model import ChangeSet, SourceFile

MAX_SOURCE_BYTES = 2 * 1024 * 1024


class SourceError(RuntimeError):
    pass


class SourceNotAllowed(SourceError):
    """The path is not in the base workspace (outside the client view / root, not synced, or missing)."""


class SourceBinary(SourceError):
    pass


class SourceTooLarge(SourceError):
    pass


class Source(Protocol):
    def load(self, cls: list[int]) -> ChangeSet: ...

    def depots_for(self, locals_: list[str]) -> dict[str, str]:
        """Depot path for each canonical local path that is in the base workspace (others are omitted)."""
        ...

    def read(self, depot: str) -> SourceFile:
        """Content of an unchanged file as the base workspace has it (for context code on demand)."""
        ...
```

`backend/codetortoise/vcs/gitfixture.py`:

```diff
diff --git a/backend/codetortoise/vcs/gitfixture.py b/backend/codetortoise/vcs/gitfixture.py
index b68aea7..ffd3539 100644
--- a/backend/codetortoise/vcs/gitfixture.py
+++ b/backend/codetortoise/vcs/gitfixture.py
@@ -9,8 +9,10 @@ import subprocess
 from pathlib import Path
 
 from codetortoise.paths import canon
-from codetortoise.vcs.model import ChangeSet, ClMeta, DriftItem, FileChange, stack
-from codetortoise.vcs.source import SourceError
+from codetortoise.vcs.model import ChangeSet, ClMeta, DriftItem, FileChange, SourceFile, stack
+from codetortoise.vcs.source import MAX_SOURCE_BYTES, SourceBinary, SourceError, SourceNotAllowed, SourceTooLarge
+
+DEPOT_PREFIX = "//fixture/"
 
 _ACTIONS = {"A": "add", "M": "edit", "D": "delete"}
 
@@ -50,7 +52,7 @@ class GitFixtureSource:
                 status, _, path = line.partition("\t")
                 action = _ACTIONS.get(status[:1], "edit")
                 files.append(FileChange(
-                    depot=f"//fixture/{path}", local=canon(str(self.repo / path)), action=action,
+                    depot=f"{DEPOT_PREFIX}{path}", local=canon(str(self.repo / path)), action=action,
                     before="" if action == "add" else self._show(f"{sha}^", path),
                     after="" if action == "delete" else self._show(sha, path),
                     base_rev=f"{sha}^"))
@@ -58,6 +60,24 @@ class GitFixtureSource:
         files = stack(per_cl)
         return ChangeSet(cls=metas, files=files, drift=self._drift(files))
 
+    def depots_for(self, locals_: list[str]) -> dict[str, str]:
+        root = canon(str(self.repo))
+        return {p: DEPOT_PREFIX + p[len(root) + 1:] for p in locals_ if p.startswith(root + "/")}
+
+    def read(self, depot: str) -> SourceFile:
+        if not depot.startswith(DEPOT_PREFIX):
+            raise SourceNotAllowed(f"{depot}: not in this workspace")
+        root = canon(str(self.repo))
+        local = canon(str(self.repo / depot[len(DEPOT_PREFIX):]))
+        if not local.startswith(root + "/") or not Path(local).is_file():
+            raise SourceNotAllowed(f"{depot}: not in this workspace")
+        data = Path(local).read_bytes()
+        if len(data) > MAX_SOURCE_BYTES:
+            raise SourceTooLarge(f"{depot}: {len(data)} bytes")
+        if b"\0" in data:
+            raise SourceBinary(f"{depot}: binary file")
+        return SourceFile(depot=depot, local=local, rev="workspace", text=data.decode("utf-8", errors="replace"))
+
     def _drift(self, files: list[FileChange]) -> list[DriftItem]:
         out = []
         for f in files:
```

`backend/codetortoise/vcs/p4source.py`:

```diff
diff --git a/backend/codetortoise/vcs/p4source.py b/backend/codetortoise/vcs/p4source.py
index 23847e9..98d6092 100644
--- a/backend/codetortoise/vcs/p4source.py
+++ b/backend/codetortoise/vcs/p4source.py
@@ -2,9 +2,9 @@
 from __future__ import annotations
 
 from codetortoise.paths import canon
-from codetortoise.vcs.model import ChangeSet, ClMeta, DriftItem, FileChange, stack
+from codetortoise.vcs.model import ChangeSet, ClMeta, DriftItem, FileChange, SourceFile, stack
 from codetortoise.vcs.p4runner import P4Error, P4Runner
-from codetortoise.vcs.source import SourceError
+from codetortoise.vcs.source import MAX_SOURCE_BYTES, SourceBinary, SourceError, SourceNotAllowed, SourceTooLarge
 
 _NO_BEFORE = {"add", "branch", "move/add", "import"}
 _NO_AFTER = {"delete", "move/delete", "purge", "archive"}
@@ -86,6 +86,34 @@ class P4Source:
                 out.append(DriftItem(depot=f.depot, local=f.local, expected=f.base_rev, actual=actual))
         return out
 
+    def depots_for(self, locals_: list[str]) -> dict[str, str]:
+        if not locals_:
+            return {}
+        out = {}
+        for r in self.p4.run("where", *locals_):
+            if "unmap" not in r and r.get("path") and r.get("depotFile"):
+                out.setdefault(canon(r["path"]), r["depotFile"])
+        return {p: out[p] for p in locals_ if p in out}
+
+    def read(self, depot: str) -> SourceFile:
+        """Unchanged file at the base workspace's have revision; refuses anything outside the client view."""
+        try:
+            recs = self.p4.run("fstat", "-T", "depotFile,clientFile,haveRev,headType", depot)
+        except P4Error as e:
+            raise SourceNotAllowed(f"{depot}: {e}") from e
+        rec = recs[0] if recs else {}
+        if not rec.get("clientFile") or not rec.get("haveRev"):
+            raise SourceNotAllowed(f"{depot}: not synced in the base workspace")
+        if any(t in rec.get("headType", "") for t in ("binary", "apple", "resource")):
+            raise SourceBinary(f"{depot}: binary file")
+        try:
+            text = self.p4.print_text(f"{depot}#{rec['haveRev']}")
+        except P4Error as e:
+            raise SourceNotAllowed(f"{depot}: {e}") from e
+        if len(text.encode("utf-8", errors="replace")) > MAX_SOURCE_BYTES:
+            raise SourceTooLarge(f"{depot}: too large")
+        return SourceFile(depot=depot, local=canon(rec["clientFile"]), rev=f"#{rec['haveRev']}", text=text)
+
     def load(self, cls: list[int]) -> ChangeSet:
         per_cl, metas, warnings = [], [], []
         try:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_gitfixture.py tests/test_p4source.py -q`
Expected: `15 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `143 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/vcs/model.py backend/codetortoise/vcs/source.py backend/codetortoise/vcs/gitfixture.py backend/codetortoise/vcs/p4source.py backend/tests/test_gitfixture.py backend/tests/test_p4source.py
git commit -m "feat(vcs): read unchanged workspace files and map local paths to depot paths"
```

---

### Task 3: Board model: annotations, flows, layout, change summary

`codetortoise/board.py` turns the change set, facts, impact model and findings into the `Board` blob the page draws
(spec §5.2, §5.3, §5.5 and §8). It is deterministic and pure apart from one `depots_for` call.

- **Annotations** (`build_impacts`): contract (new return values at the changed function; each caller's call line:
  ignored → warn, `==`-only miss → warn, covered → ok, used unchecked → info), signature (each caller's call line), state
  (the changed function's new write lines; other functions' access lines — one per line, "reads", "writes" or "reads and
  writes"; the field's declaration line). `landing=True` marks where a flow can end; only readers are state landings.
- **Flows** (`build_flows`): one per (changed node, landing, state|contract); path = shortest caller chain from an entry
  (no non-test callers, an `entrypoint_patterns` match, or top layer) → … → changed (→ field → landing for state flows);
  callers with fewer warnings win ties; test code is never walked; ranked by severity, tag, length; capped at
  `analysis.max_flows`; template `text`/`what`/`effect`/`check`.
- **Nodes**: changed ∪ flow nodes ∪ fields the changed functions touch ∪ annotated nodes ∪ top non-test blast items, capped
  at `board_max_nodes` (`hidden_nodes` counts the rest). Fields sit in their record header's layer. Initial `x` from
  four barycentre sweeps, 220 apart, centred on 0.
- **About**: template intent, top-4 findings, CLs, and the changed-file tree under the deepest shared directory.

The uart fixture must produce exactly the prototype's three flows (spec §1).

**Files:**
- Modify: `backend/codetortoise/config.py`
- Create: `backend/codetortoise/board.py`
- Test: `backend/tests/test_board.py`

**Interfaces:**
- Consumes: `Function.return_lines`, `FieldAccess.decl_line` (Task 1); `Source.depots_for` (Task 2, passed as a callable);
  `ImpactModel`, `LayerModel`, `Finding`, `DiffMap`, `ChangeSet` (existing).
- Produces (`codetortoise/board.py`): models `NodeChange{kind, add, rem}`, `BoardNode{id, key, label, kind, layer, path,
  local, range, change, x, warn}`, `BoardEdge{src, dst, kind, status, confidence}`, `Impact{node, path, line, side,
  severity, channel, title, text, finding, cause, landing}`, `Flow{id, path, tag, lands, fx_at, severity, findings, text,
  what, effect, check, what_source}`, `BoardLayer{level, name}`, `About{intent, intent_source, why, cls, tree}`,
  `Board{nodes, edges, flows, impacts, layers, about, hidden_nodes}`;
  `BoardContext(cs, dm, before, after, impact, findings, layers, cfg, depots_for)`; `build_board(ctx) -> Board`;
  `barycentre_layout(layer_of, edges, sweeps=4) -> dict[str, float]`; helpers `_crossings`, `_common_dir`, `_tree_prefix`.
- Config (`codetortoise/config.py`): `AnalysisConfig.max_flows = 12`, `board_max_nodes = 150`, `board_blast_nodes = 60`;
  `LlmConfig.concurrency = 4`, `max_flow_narratives = 6` (used from Task 4).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_board.py`:

```python
import pytest

from codetortoise.board import BoardContext, _common_dir, _crossings, _tree_prefix, barycentre_layout, build_board
from codetortoise.config import AnalysisConfig
from codetortoise.detectors.base import DetectorContext, run_detectors
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function, TuInfo
from codetortoise.impact import BlastItem, Edge, ImpactModel, Node
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def _ctx(a, fx_source, **cfg):
    findings = run_detectors(DetectorContext(a.before, a.after, a.dm, a.impact, a.cfg))
    return BoardContext(a.cs, a.dm, a.before, a.after, a.impact, findings, a.layers,
                        a.cfg.model_copy(update=cfg), fx_source.depots_for)


@pytest.fixture(scope="module")
def board(analysed, fx_source):
    return build_board(_ctx(analysed, fx_source))


def _labels(board, ids):
    by = {n.id: n.label for n in board.nodes}
    return [by[i] for i in ids]


def test_fixture_board_has_the_three_prototype_flows(board):
    got = [(f.tag, _labels(board, f.path)) for f in board.flows]
    assert got == [
        ("state", ["main", "logger_write", "uart_send", "Uart::errors", "uart_errors"]),
        ("contract", ["main", "logger_flush", "uart_send"]),
        ("contract", ["main", "uart_init", "hal_write"]),
    ]
    state, ignored, sig = board.flows
    assert [f.id for f in board.flows] == ["FL1", "FL2", "FL3"]
    assert state.severity == "high" and state.fx_at is None
    assert ignored.text == "main → logger_flush → uart_send ⟶ -2 ignored"
    assert _labels(board, [ignored.fx_at]) == ["logger_flush"] and ignored.findings
    assert sig.text.endswith("⟶ signature changed")
    assert "uart_errors" in state.effect and "Uart::errors" in state.check


def test_fixture_board_annotates_where_the_effects_land(board):
    got = {(i.path.rsplit("/", 2)[-2] + "/" + i.path.rsplit("/", 1)[-1], i.line, i.severity, i.channel)
           for i in board.impacts}
    assert {
        ("service/logger.c", 21, "warn", "contract"),     # logger_flush ignores the result
        ("service/logger.c", 12, "ok", "contract"),       # logger_write checks != 0
        ("driver/uart.c", 29, "warn", "state"),           # uart_errors reads Uart::errors
        ("driver/uart.h", 15, "warn", "state"),           # the field declaration
        ("driver/uart.c", 17, "warn", "state"),           # uart_send writes errors through `err`
        ("driver/uart.c", 18, "warn", "contract"),        # uart_send's new return -2
        ("driver/uart.c", 8, "warn", "signature"),        # uart_init calls hal_write
    } <= got
    (decl,) = [i for i in board.impacts if i.line == 15 and i.path.endswith("uart.h")]
    assert decl.text == "new writer: uart_send · readers: uart_errors · other writers: uart_init"
    (tx,) = [i for i in board.impacts if i.path.endswith("uart.h") and i.line == 7]
    assert tx.severity == "info"                          # nobody else uses Stats::tx
    assert all(i.path.startswith("//fixture/") for i in board.impacts)


def test_co_writers_are_annotated_but_are_not_landings(board):
    (w,) = [i for i in board.impacts if i.path.endswith("uart.c") and i.line == 7]
    assert w.text.startswith("writes Uart::errors") and w.severity == "warn" and not w.landing
    landed = {_labels(board, [f.lands])[0] for f in board.flows}
    assert landed == {"uart_errors", "logger_flush", "uart_init"}


def test_board_nodes_carry_change_ranges_layers_and_warn_counts(board):
    by = {n.label: n for n in board.nodes}
    send = by["uart_send"]
    assert send.change.kind == "modified" and send.change.add > 0
    assert send.path == "//fixture/driver/uart.c" and send.range[0] <= 17 <= send.range[1]
    assert by["hal_write"].change.kind == "signature"
    assert by["uart_errors"].change is None and by["uart_errors"].warn == 1
    assert by["Uart::errors"].kind == "field" and by["Uart::errors"].range == [15, 15]
    assert by["Uart::errors"].layer == by["uart_send"].layer
    names = {l.level: l.name for l in board.layers}
    assert names[by["main"].layer] == "app" and names[by["hal_write"].layer] == "hal"
    assert [l.level for l in board.layers] == sorted(names, reverse=True)
    ids = {n.id for n in board.nodes}
    assert all(e.src in ids and e.dst in ids for e in board.edges)


def test_board_node_cap_keeps_changed_and_flow_nodes_first(analysed, fx_source):
    b = build_board(_ctx(analysed, fx_source, board_max_nodes=6))
    assert len(b.nodes) == 6 and b.hidden_nodes > 0
    labels = {n.label for n in b.nodes}
    assert {"uart_send", "hal_write"} <= labels
    assert all(i.node in {n.id for n in b.nodes} for i in b.impacts)


def test_about_groups_changed_files_by_directory(board):
    tree = {d.dir: [(f.name, f.cls) for f in d.files] for d in board.about.tree}
    assert tree == {"driver": [("uart.c", [101]), ("uart.h", [102])], "hal": [("regs.c", [102])],
                    "include/hal": [("regs.h", [102])]}
    assert [c.cl for c in board.about.cls] == [101, 102]
    assert board.about.intent.startswith("2 function(s) changed in 4 file(s).")
    assert board.about.why and board.about.intent_source == "template"


def test_tree_prefix_keeps_the_deepest_common_directory_visible():
    assert _tree_prefix(["//d/lib/src/a.c", "//d/lib/src/b.h"]) == "//d/lib"
    assert _tree_prefix(["//fixture/driver/uart.c", "//fixture/include/hal/regs.h"]) == "//fixture"


def test_common_dir_keeps_the_depot_prefix():
    assert _common_dir(["//depot/a/x.c", "//depot/a/b/y.c"]) == "//depot/a"
    assert _common_dir(["//depot/a/x.c"]) == "//depot/a"
    assert _common_dir(["//d1/x.c", "//d2/y.c"]) == "/"
    assert _common_dir([]) == ""


def test_barycentre_layout_untangles_crossed_layers():
    layer_of = {"a": 1, "b": 1, "c": 0, "d": 0}
    edges = [("a", "d"), ("b", "c")]                      # initial order a,b / c,d crosses
    xs = barycentre_layout(layer_of, edges)
    order = {lv: sorted([n for n in layer_of if layer_of[n] == lv], key=xs.get) for lv in (0, 1)}
    assert _crossings(order, edges, layer_of) == 0
    assert sorted(xs[n] for n in ("a", "b")) == [-110.0, 110.0]


def test_board_without_findings_has_no_flows(analysed, fx_source):
    c = _ctx(analysed, fx_source)
    c.findings = []
    b = build_board(c)
    assert b.flows == [] or all(f.findings == [] for f in b.flows)
    assert any(n.change for n in b.nodes)


# ---- synthetic facts: shapes seen on real code (libgit2 lab) that the uart fixture does not have
def _fn(usr, name, file, start, end, returns=("0",), lines=None):
    return Function(usr=usr, qualname=name, name=name, signature=f"int {name}(void)", return_type="int", file=file,
                    start_line=start, end_line=end, returns=list(returns), return_lines=lines or {})


def _acc(fn, mode, file, line):
    return FieldAccess(fn=fn, field="c:@S@R@FI@v", field_name="v", record="R", record_file="/w/r.h", decl_line=3,
                       path="r->v", root_kind="param", mode=mode, via=["p"] if fn == "c:@F@set" else [], file=file, line=line)


def _synthetic(callers=("test_set",)):
    """set() newly writes R::v through alias p and can now return -1; peek() reads and bumps R::v on one line and
    ignores set()'s result; set's only other caller is a test."""
    set_b = _fn("c:@F@set", "set", "/w/a.c", 1, 9)
    set_a = _fn("c:@F@set", "set", "/w/a.c", 1, 9, ("0", "-1"), {"-1": 6})
    peek = _fn("c:@F@peek", "peek", "/w/b.c", 20, 24)
    fns = {"test_set": _fn("c:@F@test_set", "test_set", "/w/tests/t.c", 1, 4),
           "api": _fn("c:@F@api", "api", "/w/api.c", 1, 4)}
    calls = [CallEdge(caller=f"c:@F@{c}", callee="c:@F@set", callee_name="set", file=fns[c].file, line=2) for c in callers]
    calls.append(CallEdge(caller="c:@F@peek", callee="c:@F@set", callee_name="set", file="/w/b.c", line=22,
                          result_used=False))
    after = [Facts(tu=TuInfo(file="/w/a.c", variant="after"), functions=[set_a, peek, *(fns[c] for c in callers)],
                   calls=calls, fields=[_acc("c:@F@set", "write", "/w/a.c", 5), _acc("c:@F@peek", "read", "/w/b.c", 21),
                                        _acc("c:@F@peek", "write", "/w/b.c", 21)])]
    before = [Facts(tu=TuInfo(file="/w/a.c", variant="before"), functions=[set_b, peek])]
    nodes = {"N1": Node(id="N1", key="c:@F@set", label="set", file="/w/a.c", line=1, status="changed", layer=1),
             "N2": Node(id="N2", key="field:c:@S@R@FI@v", kind="field", label="R::v", layer=1),
             "N3": Node(id="N3", key="c:@F@peek", label="peek", file="/w/b.c", line=20, layer=1),
             "N4": Node(id="N4", key="c:@F@test_set", label="test_set", file="/w/tests/t.c", line=1, layer=2),
             "N5": Node(id="N5", key="c:@F@api", label="api", file="/w/api.c", line=1, layer=2)}
    edges = [Edge(id="E1", src="N1", dst="N2", kind="writes"), Edge(id="E2", src="N3", dst="N2", kind="reads"),
             Edge(id="E3", src="N3", dst="N1", kind="call")]
    edges += [Edge(id=f"E{4 + i}", src={"test_set": "N4", "api": "N5"}[c], dst="N1", kind="call") for i, c in enumerate(callers)]
    im = ImpactModel(nodes=nodes, edges=edges, changed=["N1"],
                     blast=[BlastItem(node="N4", hop=1, score=1.0, via="call", path=["N1", "N4"])])
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                   files=[FileChange(depot="//d/lib/src/a.c", local="/w/a.c", action="edit", before="x\n", after="y\n")])
    asked = []

    def depots_for(locals_):
        asked.append(list(locals_))
        return {p: "//d/lib" + p[2:] for p in locals_}
    ctx = BoardContext(cs, DiffMap(), before, after, im, [], None, AnalysisConfig(), depots_for)
    return ctx, asked


def test_a_line_that_reads_and_writes_a_field_gets_one_annotation():
    b = build_board(_synthetic()[0])
    (imp,) = [i for i in b.impacts if i.node == "N3" and i.channel == "state"]
    assert imp.line == 21 and imp.landing
    assert imp.text == "reads and writes R::v — now also written by set (line 5)"


def test_tests_are_neither_flow_entries_nor_blast_nodes():
    b = build_board(_synthetic()[0])
    labels = {n.id: n.label for n in b.nodes}
    state, contract = sorted(b.flows, key=lambda f: f.tag, reverse=True)
    assert [labels[n] for n in state.path] == ["set", "R::v", "peek"]
    assert state.what.startswith("set now writes R::v. peek (unlayered) uses that field")
    assert [labels[n] for n in contract.path] == ["peek", "set"]
    assert contract.what.startswith("peek (unlayered) calls set and ignores the result.")
    assert "test_set" not in labels.values()


def test_flows_start_at_a_real_caller_when_there_is_one():
    b = build_board(_synthetic(callers=("test_set", "api"))[0])
    labels = {n.id: n.label for n in b.nodes}
    (state,) = [f for f in b.flows if f.tag == "state"]
    assert [labels[n] for n in state.path] == ["api", "set", "R::v", "peek"]


def test_depot_paths_are_resolved_once_for_what_the_board_shows():
    ctx, asked = _synthetic()
    b = build_board(ctx)
    assert len(asked) == 1
    assert set(asked[0]) <= {"/w/a.c", "/w/b.c", "/w/r.h"}
    assert {n.label: n.path for n in b.nodes}["peek"] == "//d/lib/b.c"
    assert {(i.path, i.line) for i in b.impacts} >= {("//d/lib/b.c", 21), ("//d/lib/r.h", 3), ("//d/lib/a.c", 6)}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_board.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.board'`

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index 35038e5..75b8e6b 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -41,6 +41,8 @@ class LlmConfig(BaseModel):
     model: str = "gpt-4o-mini"
     max_context_tokens: int = 64000
     timeout_s: float = 120.0
+    concurrency: int = 4           # parallel LLM calls (finding explanations, chapter and flow narratives)
+    max_flow_narratives: int = 6   # review board flows whose description the LLM rewrites
 
 
 class AuthConfig(BaseModel):
@@ -57,6 +59,9 @@ class AnalysisConfig(BaseModel):
     max_layers: int = 8
     workers: int = 4
     heuristic_fanin_cap: int = 50  # names with more out-of-TU callers/refs than this are not expanded heuristically
+    max_flows: int = 12            # review board: flows listed (entry -> change -> where the effect lands)
+    board_max_nodes: int = 150     # review board: functions/fields drawn
+    board_blast_nodes: int = 60    # review board: top blast-radius functions included
     entrypoint_patterns: list[str] = Field(
         default_factory=lambda: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"])
```

`backend/codetortoise/board.py`:

```python
"""Review Board model: nodes, flows (entry -> change -> where the effect lands), impact annotations, change summary.

Built deterministically from the change set, facts, impact model and findings. The LLM stage may later rewrite
flow narratives (`Flow.what`) and the change intent (`About.intent`).
"""
from __future__ import annotations

import difflib
import fnmatch
import posixpath
import re
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.config import AnalysisConfig
from codetortoise.detectors.base import SEVERITY_RANK, Finding
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function
from codetortoise.impact import ImpactModel
from codetortoise.layers import LayerModel
from codetortoise.vcs.model import ChangeSet

Channel = Literal["contract", "signature", "state"]
Sev = Literal["warn", "info", "ok"]
_RANGE_OPS = ("!=", "<", ">", "<=", ">=")
X_SPACING = 220.0
_TEST_PATH = re.compile(r"(^|/)(tests?|testing|fuzzers?)/")


class NodeChange(BaseModel):
    kind: Literal["modified", "signature", "added", "removed"]
    add: int = 0
    rem: int = 0


class BoardNode(BaseModel):
    id: str
    key: str
    label: str
    kind: Literal["function", "field"] = "function"
    layer: int | None = None
    path: str | None = None          # depot path of the defining file
    local: str | None = None
    range: list[int] | None = None   # [start, end] lines on the new side (old side for removed functions)
    change: NodeChange | None = None
    x: float = 0.0
    warn: int = 0


class BoardEdge(BaseModel):
    src: str
    dst: str
    kind: str
    status: str
    confidence: str


class Impact(BaseModel):
    node: str
    path: str | None
    line: int
    side: Literal["new", "old"] = "new"
    severity: Sev
    channel: Channel
    title: str
    text: str
    finding: str | None = None
    cause: str | None = None         # the changed node this impact comes from
    landing: bool = False            # a flow may land here (ignoring caller, field reader, signature caller)


class Flow(BaseModel):
    id: str
    path: list[str]
    tag: Literal["state", "contract"]
    lands: str
    fx_at: str | None = None
    severity: str
    findings: list[str] = Field(default_factory=list)
    text: str
    what: str
    effect: str
    check: str
    what_source: Literal["template", "llm"] = "template"


class BoardLayer(BaseModel):
    level: int
    name: str


class AboutFile(BaseModel):
    path: str
    name: str
    action: str
    cls: list[int]
    add: int
    rem: int


class AboutDir(BaseModel):
    dir: str
    files: list[AboutFile]


class AboutCl(BaseModel):
    cl: int
    user: str
    description: str
    files: int


class AboutWhy(BaseModel):
    severity: str
    text: str
    finding: str


class About(BaseModel):
    intent: str
    intent_source: Literal["template", "llm"] = "template"
    why: list[AboutWhy] = Field(default_factory=list)
    cls: list[AboutCl] = Field(default_factory=list)
    tree: list[AboutDir] = Field(default_factory=list)


class Board(BaseModel):
    nodes: list[BoardNode] = Field(default_factory=list)
    edges: list[BoardEdge] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    impacts: list[Impact] = Field(default_factory=list)
    layers: list[BoardLayer] = Field(default_factory=list)
    about: About
    hidden_nodes: int = 0


@dataclass
class BoardContext:
    cs: ChangeSet
    dm: DiffMap
    before: list[Facts]
    after: list[Facts]
    impact: ImpactModel
    findings: list[Finding]
    layers: LayerModel | None
    cfg: AnalysisConfig
    depots_for: Callable[[list[str]], dict[str, str]]   # canonical local paths -> depot paths (called once)


# ------------------------------------------------------------------ helpers
def _fns(facts: list[Facts]) -> dict[str, Function]:
    return {f.usr: f for fx in facts for f in fx.functions}


def _covered(compared: list[str], new_values: list[str]) -> bool:
    if any(c.startswith(_RANGE_OPS) for c in compared):
        return True
    return all(any(c == f"=={v}" for c in compared) for v in new_values)


def _val(v: str, names: dict[str, str]) -> str:
    return f"{names[v]} ({v})" if v in names else v


def _cmp(c: CallEdge) -> str:
    return ", ".join(f"{c.compared_names[x]} ({x})" if x in c.compared_names else x for x in c.compared)


def _count(before: str, after: str, lo: int | None = None, hi: int | None = None) -> tuple[int, int]:
    """(+added, -removed) lines, optionally only those whose new-side line (or nearest) is within [lo, hi]."""
    a, b = before.splitlines(), after.splitlines()
    add = rem = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if lo is not None and not (j1 + 1 <= hi and max(j2, j1 + 1) >= lo):
            continue
        add += j2 - j1
        rem += i2 - i1
    return add, rem


class _Ctx:
    """Shared lookups for the builders below."""

    def __init__(self, c: BoardContext):
        self.c = c
        self.fb, self.fa = _fns(c.before), _fns(c.after)
        self.im = c.impact
        self.id_of = {n.key: n.id for n in c.impact.nodes.values()}
        self.changed = set(c.impact.changed)
        self.changed_keys = {c.impact.nodes[n].key for n in self.changed}
        self.calls_after = [e for fx in c.after for e in fx.calls]
        self.fields_after = [a for fx in c.after for a in fx.fields]
        self.fields_before = [a for fx in c.before for a in fx.fields]
        self.finding_by = defaultdict(list)          # (kind, node id) -> finding ids
        for f in c.findings:
            for n in f.nodes:
                self.finding_by[(f.kind, n)].append(f.id)

    def is_test(self, nid: str) -> bool:
        """Test code (tests/, test/, testing/, fuzzers/) is never a flow entry nor shown as blast radius."""
        node = self.im.nodes[nid]
        return nid not in self.changed and bool(node.file and _TEST_PATH.search(node.file))

    def label(self, nid: str) -> str:
        return self.im.nodes[nid].label

    def finding(self, kind: str, nid: str) -> str | None:
        ids = self.finding_by.get((kind, nid))
        return ids[0] if ids else None


# ------------------------------------------------------------------ impacts
def _new_writes(x: _Ctx, usr: str) -> dict[str, list[FieldAccess]]:
    """field USR -> accesses newly writing it in `usr` (non-local roots), as the field_mutation detector sees them."""
    def writes(accs):
        out = defaultdict(list)
        for a in accs:
            if a.fn == usr and a.mode != "read" and a.root_kind != "local":
                out[(a.field, a.root_kind)].append(a)
        return out
    wb, wa = writes(x.fields_before), writes(x.fields_after)
    res: dict[str, list[FieldAccess]] = defaultdict(list)
    for key in set(wa) - set(wb):
        res[key[0]].extend(wa[key])
    return res


def build_impacts(x: _Ctx) -> list[Impact]:
    out: list[Impact] = []
    seen: set[tuple] = set()

    def add(node: str | None, local: str, line: int, sev: Sev, channel: Channel, title: str, text: str, finding=None,
            landing=False):
        if not node or not line:
            return
        k = (node, local, line, channel, text)
        if k in seen:
            return
        seen.add(k)
        out.append(Impact(node=node, path=local, line=line, severity=sev, channel=channel, title=title,
                          text=text, finding=finding, cause=cause, landing=landing and sev == "warn" and node != cause))

    for nid in sorted(x.changed, key=lambda s: int(s[1:])):
        node, cause = x.im.nodes[nid], nid
        before, after = x.fb.get(node.key), x.fa.get(node.key)
        if before is None or after is None:
            continue
        name = after.qualname
        names = {**before.return_names, **after.return_names}
        contract = x.finding("contract", nid)
        # contract: new return values, at the changed function and at each caller
        new_values = [r for r in after.returns if r not in before.returns]
        if new_values:
            vtext = ", ".join(_val(v, names) for v in new_values)
            for v in new_values:
                add(nid, after.file, after.return_lines.get(v, 0), "warn", "contract", "Contract",
                    f"new return value {_val(v, names)}", contract)
            for c in x.calls_after:
                if c.callee != node.key:
                    continue
                caller = x.id_of.get(c.caller)
                if not c.result_used:
                    add(caller, c.file, c.line, "warn", "contract", "Contract", f"result ignored — {name} can now return {vtext}",
                        contract, landing=True)
                elif c.compared and not _covered(c.compared, new_values):
                    add(caller, c.file, c.line, "warn", "contract", "Contract",
                        f"checks {_cmp(c)} — does not handle {vtext}", contract, landing=True)
                elif c.compared:
                    add(caller, c.file, c.line, "ok", "contract", "Handled", f"checks {_cmp(c)} — covers {vtext}", contract)
                else:
                    add(caller, c.file, c.line, "info", "contract", "Contract",
                        f"uses the result without checking it — {name} can now return {vtext}", contract)
        # signature changes: each caller's call line
        if before.signature != after.signature:
            text = f"calls {name}, whose signature changed: `{before.signature}` → `{after.signature}`"
            for c in x.calls_after:
                if c.callee == node.key:
                    add(x.id_of.get(c.caller), c.file, c.line, "warn", "signature", "Signature", text, contract,
                        landing=True)
            for e in x.im.edges_into(nid, {"call"}):
                if e.confidence == "heuristic" and e.file:
                    add(e.src, e.file, e.line or 0, "info", "signature", "Signature", text + " (name match)", contract)
        # state: fields this function newly writes
        for field, accs in sorted(_new_writes(x, node.key).items()):
            a0 = accs[0]
            fid = x.id_of.get(f"field:{field}")
            fm = x.finding("field_mutation", nid)
            label = f"{a0.record}::{a0.field_name}" if a0.record else a0.field_name
            for a in accs:
                alias = [v for v in a.via if not v.startswith("call:")]
                how = f" through alias `{alias[0]}`" if alias else (f" via {a.via[0][5:]}()" if a.via else "")
                add(nid, a.file, a.line, "warn", "state", "State", f"writes {label}{how}", fm)
            wline = a0.line
            modes: dict[tuple[str, str, int], set[str]] = defaultdict(set)   # one annotation per line: r, w or both
            for o in x.fields_after:
                if o.field == field and o.fn not in x.changed_keys:
                    modes[(o.fn, o.file, o.line)].add("read" if o.mode == "read" else "write")
            readers, writers = set(), set()
            for (fn, file, line), ms in sorted(modes.items()):
                oid = x.id_of.get(fn)
                if not oid:
                    continue
                if "read" in ms:
                    readers.add(x.label(oid))
                if "write" in ms:
                    writers.add(x.label(oid))
                verb = "reads and writes" if len(ms) == 2 else "reads" if "read" in ms else "writes"
                # the effect lands on readers: they observe the new values; pure co-writers are annotated only
                add(oid, file, line, "warn", "state", "State", f"{verb} {label} — now also written by {name} (line {wline})", fm,
                    landing="read" in ms)
            if fid:
                for e in x.im.edges:
                    if e.dst == fid and e.confidence == "heuristic" and e.file and e.src not in x.changed:
                        add(e.src, e.file, e.line or 0, "info", "state", "State",
                            f"may access {label} (name match) — now written by {name}", fm)
                if a0.record_file and a0.decl_line:
                    text = f"new writer: {name} · readers: {', '.join(sorted(readers)) or 'none in the parsed code'}"
                    if writers:
                        text += f" · other writers: {', '.join(sorted(writers))}"
                    add(fid, a0.record_file, a0.decl_line, "warn" if readers or writers else "info", "state", "State",
                        text, fm)
    return out


# ------------------------------------------------------------------ flows
def _entry_path(x: _Ctx, start: str, warn: dict[str, int], avoid: frozenset[str] = frozenset()) -> list[str]:
    """Shortest caller chain from an entry down to `start` (inclusive), via call/virtual edges.

    Among equally short chains, prefer callers with fewer warnings, so a flow does not detour through a caller that
    is itself the landing of another flow. Test code and nodes in `avoid` (a state flow's landing) are not walked."""
    incoming = defaultdict(list)
    for e in x.im.edges:
        if e.kind in ("call", "virtual") and not x.is_test(e.src) and e.src not in avoid:
            incoming[e.dst].append(e.src)
    top = max((n.layer for nid, n in x.im.nodes.items() if n.layer is not None and not x.is_test(nid)), default=None)
    pats = x.c.cfg.entrypoint_patterns

    def is_entry(n: str) -> bool:
        node = x.im.nodes[n]
        return (not incoming.get(n) or any(fnmatch.fnmatchcase(node.label.split("::")[-1], p) for p in pats)
                or (top is not None and node.layer == top))

    prev = {start: None}
    q = deque([start])
    while q:
        n = q.popleft()
        if is_entry(n):
            chain = [n]
            while prev[chain[-1]] is not None:
                chain.append(prev[chain[-1]])
            return chain                                  # entry ... start
        for src in sorted(incoming.get(n, []), key=lambda s: (warn.get(s, 0), int(s[1:]))):
            if src not in prev:
                prev[src] = n
                q.append(src)
    return [start]


def build_flows(x: _Ctx, impacts: list[Impact]) -> list[Flow]:
    sev_of = {f.id: f.severity for f in x.c.findings}
    warn: dict[str, int] = defaultdict(int)
    for i in impacts:
        if i.severity == "warn":
            warn[i.node] += 1
    by_key: dict[tuple[str, str, str], Impact] = {}   # one flow per (change, landing, state|contract)
    for imp in impacts:
        if imp.landing and imp.cause and imp.node not in x.changed:
            by_key.setdefault((imp.cause, imp.node, "state" if imp.channel == "state" else "contract"), imp)
    flows: list[Flow] = []
    for (cause, land, _), imp in by_key.items():
        F, L = x.label(cause), x.label(land)
        layer_name = _layer_name(x, x.im.nodes[land].layer)
        if imp.channel == "state":
            field_id = next((e.dst for e in x.im.edges if e.src == cause and e.kind == "writes"
                             and any(e2.dst == e.dst and e2.src == land for e2 in x.im.edges)), None)
            head = _entry_path(x, cause, warn, frozenset({land}))
            path = head + ([field_id] if field_id else []) + [land]
            fl = x.label(field_id) if field_id else "the field"
            text = " → ".join(x.label(n) for n in path)
            lead = f"{F} now writes" if head[0] == cause else f"{x.label(head[0])} reaches {F}, which now writes"
            what = f"{lead} {fl}. {L} ({layer_name}) uses that field, so it now observes values written by {F}."
            effect = f"{L} now sees {fl} changed by {F}; code that assumed the old writers may be surprised."
            check = f"whether {L} assumes {fl} only changes the way it did before"
            tag, fx_at = "state", None
        else:
            head = _entry_path(x, land, warn)
            path = head + [cause]
            who = f"{L} ({layer_name})" if head[0] == land else f"{x.label(head[0])} reaches {L} ({layer_name}), which"
            if imp.channel == "signature":
                what = f"{who} calls {F}. {imp.text[0].upper()}{imp.text[1:]}."
                effect = f"Arguments {L} passes to {F} are converted to the new parameter types."
                check = f"arguments {L} passes that could change meaning under the new types"
                tail = "signature changed"
            elif imp.text.startswith("result ignored"):
                vals = imp.text.split("can now return ", 1)[-1]
                what = f"{who} calls {F} and ignores the result. {F} can now return {vals}."
                effect = f"{L} silently drops the new {vals} result."
                check = f"whether {L} can hit the new {vals} path, and what it should do then"
                tail = f"{vals} ignored"
            else:
                vals = imp.text.split("does not handle ", 1)[-1]
                what = f"{who} calls {F} and {imp.text}."
                effect = f"{L} does not handle {vals}."
                check = f"how {L} should treat {vals}"
                tail = f"{vals} unhandled"
            text = " → ".join(x.label(n) for n in path) + f" ⟶ {tail}"
            tag, fx_at = "contract", land
        sev = sev_of.get(imp.finding or "", "medium")
        flows.append(Flow(id="", path=path, tag=tag, lands=land, fx_at=fx_at, severity=sev,
                          findings=[imp.finding] if imp.finding else [], text=text, what=what, effect=effect, check=check))
    flows.sort(key=lambda f: (-SEVERITY_RANK.get(f.severity, 0), 0 if f.tag == "state" else 1, len(f.path), f.text))
    flows = flows[: x.c.cfg.max_flows]
    for i, f in enumerate(flows):
        f.id = f"FL{i + 1}"
    return flows


def _layer_name(x: _Ctx, level: int | None) -> str:
    if level is None or x.c.layers is None:
        return "unlayered"
    layer = x.c.layers.layer(level)
    return layer.name.split(": ", 1)[-1] if layer else f"L{level}"


# ------------------------------------------------------------------ nodes, layout, about
def _crossings(order: dict[int, list[str]], edges: list[tuple[str, str]], layer_of: dict[str, int]) -> int:
    pos = {n: i for lst in order.values() for i, n in enumerate(lst)}
    levels = sorted(order, reverse=True)
    total = 0
    for up, down in zip(levels, levels[1:], strict=False):
        es = [(pos[a], pos[b]) if layer_of[a] == up else (pos[b], pos[a]) for a, b in edges
              if {layer_of.get(a), layer_of.get(b)} == {up, down}]
        total += sum(1 for i, (a1, b1) in enumerate(es) for a2, b2 in es[i + 1:] if (a1 - a2) * (b1 - b2) < 0)
    return total


def barycentre_layout(layer_of: dict[str, int], edges: list[tuple[str, str]], sweeps: int = 4) -> dict[str, float]:
    """World x per node: layers ordered by barycentre sweeps (top-down, bottom-up, ...), spaced X_SPACING apart."""
    order: dict[int, list[str]] = defaultdict(list)
    for n in sorted(layer_of, key=lambda s: (len(s), s)):
        order[layer_of[n]].append(n)
    nbrs = defaultdict(set)
    for a, b in edges:
        if a in layer_of and b in layer_of and layer_of[a] != layer_of[b]:
            nbrs[a].add(b)
            nbrs[b].add(a)
    levels = sorted(order, reverse=True)
    for s in range(sweeps):
        seq = levels if s % 2 == 0 else list(reversed(levels))
        for i, lv in enumerate(seq[1:], 1):
            ref = {n: j for j, n in enumerate(order[seq[i - 1]])}
            cur = order[lv]

            def bc(n, cur=cur, ref=ref):
                ps = [ref[m] for m in nbrs[n] if m in ref]
                return sum(ps) / len(ps) if ps else cur.index(n)
            order[lv] = sorted(cur, key=lambda n: (bc(n), cur.index(n)))
    xs = {}
    for lst in order.values():
        for i, n in enumerate(lst):
            xs[n] = (i - (len(lst) - 1) / 2) * X_SPACING
    return xs


def build_board(c: BoardContext) -> Board:
    x = _Ctx(c)
    impacts = build_impacts(x)
    flows = build_flows(x, impacts)
    im = c.impact
    # node selection: changed, flow nodes, fields around changed functions, then top blast items; capped
    chosen: list[str] = []

    def take(nid):
        if nid in im.nodes and nid not in chosen:
            chosen.append(nid)
    for n in im.changed:
        take(n)
    for f in flows:
        for n in f.path:
            take(n)
    for e in im.edges:
        if e.kind in ("writes", "reads") and e.src in x.changed:
            take(e.dst)
    for i in impacts:
        if not x.is_test(i.node):
            take(i.node)
    for b in [b for b in im.blast if not x.is_test(b.node)][: c.cfg.board_blast_nodes]:
        take(b.node)
    hidden = max(0, len(chosen) - c.cfg.board_max_nodes)
    chosen = chosen[: c.cfg.board_max_nodes]
    sel = set(chosen)
    # layers: fields sit in the layer of their record's module, else their writer's layer
    # after-side facts win: the node shows the new file
    record_file = {f"field:{a.field}": a.record_file for a in x.fields_before + x.fields_after if a.record_file}
    decl_line = {f"field:{a.field}": a.decl_line for a in x.fields_before + x.fields_after if a.decl_line}
    layer_of: dict[str, int] = {}
    for nid in chosen:
        n = im.nodes[nid]
        lv = n.layer
        if n.kind == "field":
            rf = record_file.get(n.key)
            lv = c.layers.level_of(rf) if (c.layers and rf) else None
            if lv is None:
                lv = next((im.nodes[e.src].layer for e in im.edges if e.dst == nid and e.kind == "writes"
                           and im.nodes[e.src].layer is not None), None)
        layer_of[nid] = lv if lv is not None else -1
    edges = [e for e in im.edges if e.src in sel and e.dst in sel]
    xs = barycentre_layout(layer_of, [(e.src, e.dst) for e in edges])
    # per-node details
    warn = defaultdict(int)
    for i in impacts:
        if i.severity == "warn":
            warn[i.node] += 1
    kind_of = {"body_modified": "modified", "signature_changed": "signature", "added": "added", "removed": "removed"}
    texts = {f.local: f for f in c.cs.files}
    shown = [i for i in impacts if i.node in sel]
    locals_of: dict[str, str | None] = {}
    for nid in chosen:
        n = im.nodes[nid]
        fn = x.fa.get(n.key) or x.fb.get(n.key)
        locals_of[nid] = (record_file.get(n.key) or None) if n.kind == "field" else (fn.file if fn else n.file)
    depots = c.depots_for(sorted({p for p in [*locals_of.values(), *(i.path for i in shown)] if p}))
    for i in shown:
        i.path = depots.get(i.path) if i.path else None
    nodes = []
    for nid in chosen:
        n = im.nodes[nid]
        fn = x.fa.get(n.key) or x.fb.get(n.key)
        local, rng, change = locals_of[nid], None, None
        if n.kind == "field":
            dl = decl_line.get(n.key)
            rng = [dl, dl] if dl else None
        elif fn is not None:
            rng = [fn.start_line, fn.end_line]
        if nid in x.changed and fn is not None:
            ch = next((d for d in c.dm.functions if d.file == fn.file and d.qualname == fn.qualname), None)
            fc = texts.get(fn.file)
            add = rem = 0
            if fc is not None:
                add, rem = _count(fc.before, fc.after, fn.start_line, fn.end_line)
            change = NodeChange(kind=kind_of.get(ch.kind if ch else "", "modified"), add=add, rem=rem)
        nodes.append(BoardNode(id=nid, key=n.key, label=n.label, kind=n.kind, layer=layer_of[nid],
                               path=depots.get(local) if local else None, local=local, range=rng, change=change,
                               x=xs.get(nid, 0.0), warn=warn[nid]))
    levels = sorted({lv for lv in layer_of.values()}, reverse=True)
    layers = [BoardLayer(level=lv, name=(_layer_name(x, lv) if lv >= 0 else "other")) for lv in levels]
    return Board(nodes=nodes, edges=[BoardEdge(src=e.src, dst=e.dst, kind=e.kind, status=e.status, confidence=e.confidence)
                                     for e in edges],
                 flows=flows, impacts=shown, layers=layers,
                 about=build_about(c), hidden_nodes=hidden)


def _tree_prefix(depots: list[str]) -> str:
    """Prefix stripped from the change tree: everything above the deepest directory the files share, so that
    directory itself stays visible (a change inside one directory shows that directory, not ".")."""
    return _common_dir([posixpath.dirname(d) for d in depots])


def _common_dir(paths: list[str]) -> str:
    """Longest common directory of depot paths, keeping the leading // (posixpath.commonpath would collapse it)."""
    if not paths:
        return ""
    parts = [p.split("/")[:-1] for p in paths]
    common = []
    for segs in zip(*parts, strict=False):
        if len(set(segs)) != 1:
            break
        common.append(segs[0])
    return "/".join(common)


def build_about(c: BoardContext) -> About:
    files = c.cs.files
    fn_count = len(c.dm.functions)
    descs = "; ".join(f"CL {m.cl}: {m.description}" for m in c.cs.cls if m.description)
    intent = (f"{fn_count} function(s) changed in {len(files)} file(s). " + (descs + "." if descs else "")).strip()
    why = [AboutWhy(severity=f.severity, text=f.title, finding=f.id) for f in c.findings[:4]]
    cls = [AboutCl(cl=m.cl, user=m.user, description=m.description,
                   files=sum(1 for f in files if any(p.cl == m.cl for p in f.per_cl))) for m in c.cs.cls]
    prefix = _tree_prefix([f.depot for f in files])
    dirs: dict[str, list[AboutFile]] = defaultdict(list)
    for f in sorted(files, key=lambda f: f.depot):
        rel = f.depot[len(prefix):].lstrip("/") if prefix else f.depot
        d = posixpath.dirname(rel) or "."
        add, rem = _count(f.before, f.after)
        dirs[d].append(AboutFile(path=f.depot, name=posixpath.basename(rel), action=f.action,
                                 cls=[p.cl for p in f.per_cl], add=add, rem=rem))
    tree = [AboutDir(dir=d, files=fs) for d, fs in sorted(dirs.items())]
    return About(intent=intent, why=why, cls=cls, tree=tree)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_board.py -q`
Expected: `14 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `157 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/board.py backend/tests/test_board.py
git commit -m "feat(board): board model — flows, impact annotations, layout, change summary"
```

---

### Task 4: Pipeline board stage; parallel, grounded LLM narratives

A new `board` stage runs after `detectors` (deps: `impact`, `detectors`) and stores the `board` blob. Depot paths come
from `depot_resolver`: changed files from the change set; other files under the workspace root from one
`source.depots_for` call; paths outside the workspace (system headers) are never sent — in the libgit2 lab they made
`p4 where` fail the whole batch. A failed lookup degrades the stage; the board is still stored.

The `llm` stage now runs finding explanations, chapter narratives and the top `llm.max_flow_narratives` flow narratives on
one thread pool of `llm.concurrency` workers, applies results in submission order, then runs the summary, which also
becomes `about.intent`. A flow narrative is kept only if it cites a node on that flow or one of its findings; otherwise
the template stays (`what_source: template`). The board blob is re-stored after the LLM stage.

**Files:**
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/tests/test_storyboard.py`
- Modify: `backend/tests/test_pipeline.py`
- Modify: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: `build_board`, `BoardContext`, `Board`, `Flow` (Task 3); `LlmConfig.concurrency`, `max_flow_narratives` (Task 3).
- Produces: `pipeline.STAGES` with `"board"` between `"detectors"` and `"llm"`; `pipeline.depot_resolver(source, cs, root,
  notes) -> Callable[[list[str]], dict[str, str]]`; `build_storyboard(impact, findings, layers, snippets, llm, max_tokens,
  *, board=None, concurrency=1, max_flow_narratives=6)`; blob `board` (JSON of `Board`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_storyboard.py`:

```diff
diff --git a/backend/tests/test_storyboard.py b/backend/tests/test_storyboard.py
index 6933285..b0aa0c1 100644
--- a/backend/tests/test_storyboard.py
+++ b/backend/tests/test_storyboard.py
@@ -123,3 +123,63 @@ def test_unexpected_llm_client_exception_keeps_skeleton():
 
     sb = build_storyboard(im, findings, layers, {}, Exploding())
     assert not sb.llm_used and "boom" in sb.llm_error and sb.chapters
+
+
+def _board(flows=2):
+    from codetortoise.board import About, Board, Flow
+    fl = [Flow(id=f"FL{i + 1}", path=["N3", "N2"], tag="contract", lands="N3", fx_at="N3", severity="medium",
+               findings=["F1"], text="logger_flush → uart_send ⟶ -2 ignored", what="template what", effect="e",
+               check="c") for i in range(flows)]
+    return Board(flows=fl, about=About(intent="template intent"))
+
+
+def _respond(flow_reply):
+    def respond(system, user):
+        if "Explain the risk" in user:
+            return {"explanation": "e"}
+        if "narrative for this architectural layer" in user:
+            return {"narrative": "n", "cites": ["N1"]}
+        if "Describe this call flow" in user:
+            return flow_reply(user)
+        return {"summary": "the change adds tx stats", "risk": "medium", "cites": ["F1"]}
+    return respond
+
+
+def test_llm_writes_grounded_flow_narratives_and_the_change_intent():
+    im, findings, layers = model()
+    board = _board(3)
+    replies = iter([{"what": "flush drops -2", "cites": ["N3", "F1"]},
+                    {"what": "uncited guess", "cites": ["N99"]},
+                    {"what": "not asked for", "cites": ["N3"]}])
+    sb = build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: next(replies))),
+                          board=board, max_flow_narratives=2)
+    assert sb.llm_used
+    assert [(f.what, f.what_source) for f in board.flows] == [
+        ("flush drops -2", "llm"), ("template what", "template"), ("template what", "template")]
+    assert board.about.intent == "the change adds tx stats" and board.about.intent_source == "llm"
+
+
+def test_llm_calls_run_concurrently():
+    import threading
+    im, findings, layers = model()
+    board = _board(2)
+    gate = threading.Barrier(4, timeout=5)   # 2 findings + 2 flows must be in flight together
+
+    def respond(system, user):
+        if "Explain the risk" in user or "Describe this call flow" in user:
+            gate.wait()
+        return _respond(lambda u: {"what": "w", "cites": ["N3"]})(system, user)
+
+    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond), board=board, concurrency=4)
+    assert sb.llm_used, sb.llm_error
+    assert [f.what_source for f in board.flows] == ["llm", "llm"]
+
+
+def test_llm_failure_keeps_template_flow_text():
+    im, findings, layers = model()
+    board = _board(1)
+    llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(500)),
+                    sleep=lambda s: None)
+    sb = build_storyboard(im, findings, layers, {}, llm, board=board, concurrency=4)
+    assert not sb.llm_used and sb.llm_error
+    assert board.flows[0].what == "template what" and board.about.intent_source == "template"
```

`backend/tests/test_pipeline.py`:

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 76994b3..0254946 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -2,7 +2,9 @@ from helpers import make_services
 
 from codetortoise.health import run_health
 from codetortoise.pipeline import run_review
+from codetortoise.vcs.gitfixture import GitFixtureSource
 from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange
+from codetortoise.vcs.p4runner import P4Error
 
 
 def stages(svc, rid):
@@ -14,7 +16,7 @@ def test_full_review_without_llm_or_swarm(fx, tmp_path):
     rid = svc.store.create_review("t", "owner", [101, 102])
     run_review(rid, svc)
     assert stages(svc, rid) == {"ingest": "ok", "swarm_read": "degraded", "diffmap": "ok", "tu_select": "ok",
-                                "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok",
+                                "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok", "board": "ok",
                                 "llm": "degraded", "finalize": "ok"}
     review = svc.store.get_review(rid)
     assert review["status"] == "degraded" and review["risk"] == "high"
@@ -23,6 +25,10 @@ def test_full_review_without_llm_or_swarm(fx, tmp_path):
     assert [c["name"] for c in sb["chapters"]][:3] == ["L0: cpp, include/hal", "L1: hal", "L2: driver"]
     assert [c["cl"] for c in svc.store.list_cls(rid)] == [101, 102]
     assert svc.store.list_cls(rid)[0]["description"].startswith("uart:")
+    board = svc.store.get_blob(rid, "board")
+    assert [f["tag"] for f in board["flows"]] == ["state", "contract", "contract"]
+    assert all(n["path"].startswith("//fixture/") for n in board["nodes"] if n["kind"] == "function")
+    assert board["about"]["intent_source"] == "template"
 
 
 def test_ingest_failure_skips_dependent_stages(fx, tmp_path):
@@ -50,6 +56,7 @@ def test_change_without_c_code_completes(fx, tmp_path):
     assert st["impact"] == "ok" and st["detectors"] == "ok"
     assert svc.store.list_findings(rid) == []
     assert svc.store.get_blob(rid, "storyboard")["risk"] == "low"
+    assert st["board"] == "ok" and svc.store.get_blob(rid, "board")["flows"] == []
 
 
 def test_health_ready_on_fixture_and_gates_on_empty_compile_db(fx, tmp_path):
@@ -187,3 +194,50 @@ def test_layer_cache_is_invalidated_by_algorithm_version(fx, tmp_path, monkeypat
     monkeypatch.setattr(layers_mod, "ALGORITHM_VERSION", layers_mod.ALGORITHM_VERSION + 1)
     fresh = make_services(fx, tmp_path)
     assert fresh.layers.get().module_level != {"x": 0}
+
+
+class NoWhere(GitFixtureSource):
+    def depots_for(self, locals_):
+        raise P4Error("p4 where: connect failed")
+
+
+def test_board_without_depot_paths_for_context_nodes_is_degraded(fx, tmp_path):
+    svc = make_services(fx, tmp_path, source=NoWhere(fx.root))
+    rid = svc.store.create_review("t", "owner", [101, 102])
+    run_review(rid, svc)
+    st = {s["name"]: s for s in svc.store.list_stages(rid)}
+    assert st["board"]["status"] == "degraded" and "connect failed" in st["board"]["message"]
+    board = svc.store.get_blob(rid, "board")
+    paths = {n["label"]: n["path"] for n in board["nodes"]}
+    assert paths["uart_send"] == "//fixture/driver/uart.c" and paths["main"] is None
+    assert len(board["flows"]) == 3
+
+
+def test_depot_resolver_asks_the_source_only_about_workspace_files():
+    from codetortoise.pipeline import depot_resolver
+    asked = []
+
+    class Src:
+        def depots_for(self, locals_):
+            asked.append(list(locals_))
+            return {p: "//d" + p[3:] for p in locals_}
+    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
+                   files=[FileChange(depot="//d/a.c", local="/ws/a.c", action="edit", before="", after="")])
+    notes: list[str] = []
+    resolve = depot_resolver(Src(), cs, "/ws", notes)
+    got = resolve(["/ws/a.c", "/ws/b/c.h", "/usr/include/stdio.h", "/wsx/d.c"])
+    assert got == {"/ws/a.c": "//d/a.c", "/ws/b/c.h": "//d/b/c.h"}
+    assert asked == [["/ws/b/c.h"]] and notes == []
+
+
+def test_depot_resolver_failure_keeps_changed_files_and_notes_why():
+    from codetortoise.pipeline import depot_resolver
+
+    class Src:
+        def depots_for(self, locals_):
+            raise P4Error("p4 where: connect failed")
+    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
+                   files=[FileChange(depot="//d/a.c", local="/ws/a.c", action="edit", before="", after="")])
+    notes: list[str] = []
+    assert depot_resolver(Src(), cs, "/ws", notes)(["/ws/a.c", "/ws/b.c"]) == {"/ws/a.c": "//d/a.c"}
+    assert notes == ["depot paths unavailable for context nodes: P4Error: p4 where: connect failed"]
```

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index c288db1..d00ba38 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -63,7 +63,7 @@ def test_owner_creates_review_others_view_and_comment(env):
     assert r.status_code == 200 and r.json()["title"] == "CLs 101, 102"
     rid = r.json()["id"]
     detail = bob.get(f"/api/reviews/{rid}").json()
-    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 10
+    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 11
     assert bob.get(f"/api/reviews/{rid}/storyboard").json()["storyboard"]["risk"] == "high"
     assert len(bob.get(f"/api/reviews/{rid}/impact").json()["nodes"]) > 5
     assert len(bob.get(f"/api/reviews/{rid}/findings").json()) == 6
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_storyboard.py tests/test_pipeline.py tests/test_web.py -q`
Expected: FAIL — `9 failed, 26 passed` (no `board` stage or blob, no `pipeline.depot_resolver`, `build_storyboard` takes no `board=`, 11 stages expected)

- [ ] **Step 3: Implement**

`backend/codetortoise/llm/storyboard.py`:

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index fae33ec..8c06edd 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -1,10 +1,13 @@
 """Storyboard: deterministic skeleton + optional grounded LLM narrative."""
 from __future__ import annotations
 
+from collections.abc import Callable
+from concurrent.futures import ThreadPoolExecutor
 from typing import Literal
 
 from pydantic import BaseModel, Field
 
+from codetortoise.board import Board, Flow
 from codetortoise.detectors.base import SEVERITY_RANK, Finding, Hypothesis
 from codetortoise.impact import ImpactModel
 from codetortoise.layers import LayerModel
@@ -62,6 +65,11 @@ class _SummaryOut(BaseModel):
     cites: list[str] = Field(default_factory=list)
 
 
+class _FlowOut(BaseModel):
+    what: str
+    cites: list[str] = Field(default_factory=list)
+
+
 class _LayerName(BaseModel):
     level: int
     name: str
@@ -155,38 +163,72 @@ def _finding_text(f: Finding) -> str:
     return f"{f.id} [{f.severity}] {f.kind}: {f.title}\n{f.summary}\nnodes: {f.nodes}\nevidence:\n{ev}"
 
 
+def _flow_prompt(fl: Flow, impact: ImpactModel, findings: list[Finding], snippets: dict[str, str], per_call: int) -> str:
+    steps = " → ".join(f"{n} {impact.nodes[n].label}" for n in fl.path if n in impact.nodes)
+    parts = [f"FLOW {fl.id} ({fl.tag}): {steps}\nlands on: {fl.lands}\ndraft: {fl.what}\neffect: {fl.effect}\n"
+             f"check: {fl.check}",
+             "FINDINGS:\n" + "\n\n".join(_finding_text(f) for f in findings if f.id in fl.findings),
+             "GRAPH FACTS:\n" + _facts_for_nodes(impact, [n for n in fl.path if n in impact.nodes])]
+    parts += [f"CODE {n}:\n{snippets[n]}" for n in fl.path if n in snippets]
+    return ("Describe this call flow for a reviewer in 2-3 sentences: how the entry reaches the change and what the "
+            "change does to the function where the effect lands. Cite the node and finding ids you rely on.\n\n" +
+            budget(parts, per_call))
+
+
 def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: LayerModel | None,
-                     snippets: dict[str, str], llm: LlmClient | None, max_tokens: int = 64000) -> Storyboard:
+                     snippets: dict[str, str], llm: LlmClient | None, max_tokens: int = 64000, *,
+                     board: Board | None = None, concurrency: int = 1, max_flow_narratives: int = 6) -> Storyboard:
+    """Skeleton storyboard, then (with an LLM) finding explanations, chapter and flow narratives on a thread pool.
+
+    Results are applied in a fixed order, so the output depends only on the replies; the summary call runs last.
+    Any LLM-side failure keeps the deterministic text for everything not yet applied."""
     sb = skeleton(impact, findings, layers)
     if llm is None:
         return sb
     known = set(impact.nodes) | {f.id for f in findings}
     per_call = max(2000, max_tokens // 2)
-    try:
-        for f in findings:
-            nodes = [n for n in f.nodes if n in impact.nodes]
-            neighbours = sorted({e.src for e in impact.edges if e.dst in nodes} |
-                                {e.dst for e in impact.edges if e.src in nodes})
-            parts = ["FINDING:\n" + _finding_text(f), "GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes + neighbours)]
-            parts += [f"CODE {n}:\n{snippets[n]}" for n in nodes + neighbours if n in snippets]
-            out = llm.complete_json(SYSTEM, "Explain the risk of this finding, list concrete verification steps, "
-                                    "and propose additional side-effect hypotheses (each citing ids).\n\n" +
-                                    budget(parts, per_call), _ExplainOut)
+    jobs: list[tuple[str, type[BaseModel], Callable]] = []
+
+    for f in findings:
+        nodes = [n for n in f.nodes if n in impact.nodes]
+        neighbours = sorted({e.src for e in impact.edges if e.dst in nodes} |
+                            {e.dst for e in impact.edges if e.src in nodes})
+        parts = ["FINDING:\n" + _finding_text(f), "GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes + neighbours)]
+        parts += [f"CODE {n}:\n{snippets[n]}" for n in nodes + neighbours if n in snippets]
+
+        def explain(out: _ExplainOut, f=f):
             f.explanation = out.explanation
             f.verify_steps = out.verify_steps
             f.hypotheses = [Hypothesis(text=h.text, cites=h.cites) for h in ground(out.hypotheses, known)]
-        for ch in sb.chapters:
-            parts = [f"LAYER: {ch.name}",
-                     "CHANGED NODES AND EDGES:\n" + _facts_for_nodes(impact, ch.nodes),
-                     "FINDINGS:\n" + "\n\n".join(_finding_text(f) for f in findings if f.id in ch.findings)]
-            parts += [f"CODE {n}:\n{snippets[n]}" for n in ch.nodes if n in snippets]
-            out = llm.complete_json(SYSTEM, "Write the narrative for this architectural layer: what changed, why it "
-                                    "matters, and effects on layers above/below (cross_layer_effects).\n\n" +
-                                    budget(parts, per_call), _ChapterOut)
+        jobs.append(("Explain the risk of this finding, list concrete verification steps, and propose additional "
+                     "side-effect hypotheses (each citing ids).\n\n" + budget(parts, per_call), _ExplainOut, explain))
+
+    for ch in sb.chapters:
+        parts = [f"LAYER: {ch.name}",
+                 "CHANGED NODES AND EDGES:\n" + _facts_for_nodes(impact, ch.nodes),
+                 "FINDINGS:\n" + "\n\n".join(_finding_text(f) for f in findings if f.id in ch.findings)]
+        parts += [f"CODE {n}:\n{snippets[n]}" for n in ch.nodes if n in snippets]
+
+        def narrate(out: _ChapterOut, ch=ch):
             ch.narrative = out.narrative
             ch.cites = [c for c in out.cites if c in known]
             ch.verified = bool(ch.cites)
             ch.cross_layer_effects = ground(out.cross_layer_effects, known)
+        jobs.append(("Write the narrative for this architectural layer: what changed, why it matters, and effects on "
+                     "layers above/below (cross_layer_effects).\n\n" + budget(parts, per_call), _ChapterOut, narrate))
+
+    for fl in (board.flows[:max_flow_narratives] if board else []):
+        def describe(out: _FlowOut, fl=fl):
+            # grounded: keep the LLM text only if it cites a node on this flow or one of its findings
+            if out.what.strip() and set(out.cites) & (set(fl.path) | set(fl.findings)):
+                fl.what, fl.what_source = out.what.strip(), "llm"
+        jobs.append((_flow_prompt(fl, impact, findings, snippets, per_call), _FlowOut, describe))
+
+    pool = ThreadPoolExecutor(max(1, concurrency), thread_name_prefix="tortoise-llm")
+    futures = [pool.submit(llm.complete_json, SYSTEM, prompt, schema) for prompt, schema, _ in jobs]
+    try:
+        for fut, (_, _, apply) in zip(futures, jobs, strict=True):
+            apply(fut.result())
         overview = [f"CHAPTER {c.name}: {c.narrative} (cites {c.cites})" for c in sb.chapters]
         overview += [_finding_text(f) for f in findings[:30]]
         out = llm.complete_json(SYSTEM, "Summarize the whole change for a reviewer in 3-6 sentences, give an overall "
@@ -199,8 +241,12 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
         sb.review_order = order or sb.review_order
         sb.verified = any(c in known for c in out.cites)
         sb.llm_used = True
+        if board is not None and out.summary.strip():
+            board.about.intent, board.about.intent_source = out.summary.strip(), "llm"
     except Exception as e:  # any LLM-side failure leaves the deterministic storyboard intact
         sb.llm_error = str(e) if isinstance(e, LlmError) else f"{type(e).__name__}: {e}"
+    finally:
+        pool.shutdown(wait=True, cancel_futures=True)
     return sb
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 04c7489..ad776bc 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -7,12 +7,14 @@ import threading
 import traceback
 from pathlib import Path
 
+from codetortoise.board import BoardContext, build_board
 from codetortoise.detectors.base import DetectorContext, run_detectors
 from codetortoise.diffmap import map_changes
 from codetortoise.facts.model import Facts
 from codetortoise.facts.runner import build_requests, run_extraction
 from codetortoise.impact import ImpactModel, build_impact
 from codetortoise.llm.storyboard import build_storyboard
+from codetortoise.paths import canon
 from codetortoise.services import Services
 from codetortoise.swarm import SwarmError
 from codetortoise.tu_select import TuSelection, field_follow_up, select_tus
@@ -20,9 +22,11 @@ from codetortoise.vcs.model import ChangeSet
 
 log = logging.getLogger(__name__)
 
-STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "llm", "finalize"]
+STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "board", "llm",
+          "finalize"]
 DEPS = {"swarm_read": ["ingest"], "diffmap": ["ingest"], "tu_select": ["diffmap"], "facts": ["tu_select"],
-        "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "llm": ["detectors"]}
+        "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "board": ["impact", "detectors"],
+        "llm": ["detectors"]}
 
 
 class Degraded(Exception):
@@ -52,6 +56,24 @@ def collect_snippets(impact: ImpactModel, cs: ChangeSet, after: list[Facts], lim
     return out
 
 
+def depot_resolver(source, cs: ChangeSet, root: str, notes: list[str]):
+    """Board depot-path lookup: changed files from the change set, other workspace files from the source in one
+    call. Paths outside the workspace (system headers, toolchain) are never sent; a failed lookup is noted and
+    leaves those nodes without a depot path (no context code on demand for them)."""
+    prefix = canon(str(root)).rstrip("/") + "/"
+
+    def resolve(locals_: list[str]) -> dict[str, str]:
+        known = {f.local: f.depot for f in cs.files}
+        rest = sorted({p for p in locals_ if p not in known and p.startswith(prefix)})
+        if rest:
+            try:
+                known.update(source.depots_for(rest))
+            except Exception as e:  # board still useful without depot paths for context nodes
+                notes.append(f"depot paths unavailable for context nodes: {type(e).__name__}: {e}")
+        return {p: known[p] for p in locals_ if p in known}
+    return resolve
+
+
 def run_review(rid: int, svc: Services) -> None:
     store, cfg = svc.store, svc.cfg
     store.reset_stages(rid, STAGES)
@@ -166,12 +188,28 @@ def run_review(rid: int, svc: Services) -> None:
         store.put_findings(rid, findings)
         return f"{len(findings)} finding(s)"
 
+    def board():
+        notes: list[str] = []
+        resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
+        b = build_board(BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
+                                     ctx.get("layers"), cfg.analysis, resolve))
+        ctx["board"] = b
+        store.put_blob(rid, "board", b)
+        if notes:
+            raise Degraded("; ".join(notes))
+        return f"{len(b.nodes)} node(s), {len(b.flows)} flow(s), {len(b.impacts)} annotation(s)"
+
     def llm():
         findings = store.list_findings(rid)
         snippets = collect_snippets(ctx["impact"], ctx["cs"], ctx["after"])
-        sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens)
+        b = ctx.get("board")
+        sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens,
+                              board=b, concurrency=cfg.llm.concurrency,
+                              max_flow_narratives=cfg.llm.max_flow_narratives)
         store.put_findings(rid, findings)
         store.put_blob(rid, "storyboard", sb)
+        if b is not None:
+            store.put_blob(rid, "board", b)
         ctx["storyboard"] = sb
         if svc.llm is None:
             raise Degraded("no LLM configured; deterministic storyboard only")
@@ -189,7 +227,7 @@ def run_review(rid: int, svc: Services) -> None:
 
     for name, fn in [("ingest", ingest), ("swarm_read", swarm_read), ("diffmap", diffmap), ("tu_select", tu_select),
                      ("layers", layers), ("facts", facts), ("impact", impact), ("detectors", detectors),
-                     ("llm", llm), ("finalize", finalize)]:
+                     ("board", board), ("llm", llm), ("finalize", finalize)]:
         stage(name, fn)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_storyboard.py tests/test_pipeline.py tests/test_web.py -q`
Expected: `35 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `163 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/llm/storyboard.py backend/codetortoise/pipeline.py backend/tests/test_storyboard.py backend/tests/test_pipeline.py backend/tests/test_web.py
git commit -m "feat(board): board pipeline stage; parallel LLM calls with grounded flow narratives"
```

---

### Task 5: API: board and on-demand source

`GET /api/reviews/{rid}/board` returns the board blob with layer renames applied (404 "board not built yet" until the
stage has stored it). `GET /api/reviews/{rid}/source?path=<depot>&side=before|after` returns `{path, depot, rev, text,
changed}`: changed files from the change set (`rev` = base revision for `before`, `changed` for `after`); any other file
through `Source.read`, cached in the review's blobs as `source:<depot>`. Errors: outside the workspace 403, binary 415,
over 2 MiB 413, Perforce failure 502. Any logged-in user may read (viewers need context code too).

**Files:**
- Modify: `backend/codetortoise/web/app.py`
- Modify: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: board blob (Task 4); `Source.read`, `SourceNotAllowed|SourceBinary|SourceTooLarge` (Task 2).
- Produces: the two endpoints above (used by the frontend in Tasks 10–11).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index d00ba38..f5473c4 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -178,3 +178,57 @@ def test_expired_p4_password_is_explained_but_other_failures_stay_generic(fx, tm
     assert r.status_code == 401 and "expired" in r.json()["detail"] and "p4 passwd" in r.json()["detail"]
     r = c.post("/api/login", json={"user": "carol", "password": "x"})
     assert r.status_code == 401 and r.json()["detail"] == "invalid credentials"
+
+
+def _review(app):
+    owner = login(app, "owner")
+    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
+    return owner, rid
+
+
+def test_board_endpoint_serves_the_board_with_layer_renames(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    assert owner.get("/api/reviews/999/board").status_code == 404
+    board = owner.get(f"/api/reviews/{rid}/board").json()
+    assert [f["id"] for f in board["flows"]] == ["FL1", "FL2", "FL3"]
+    level = next(l["level"] for l in board["layers"] if l["name"] == "driver")
+    owner.put(f"/api/layers/{level}", json={"name": "Drivers"})
+    names = {l["level"]: l["name"] for l in owner.get(f"/api/reviews/{rid}/board").json()["layers"]}
+    assert names[level] == "Drivers"
+    svc.store.put_blob(rid, "board", None)
+    r = owner.get(f"/api/reviews/{rid}/board")
+    assert r.status_code == 404 and "not built" in r.json()["detail"]
+
+
+def test_source_endpoint_serves_changed_and_unchanged_files(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    bob = login(app, "bob")
+    new = bob.get(f"/api/reviews/{rid}/source", params={"path": "//fixture/driver/uart.c", "side": "after"}).json()
+    old = bob.get(f"/api/reviews/{rid}/source", params={"path": "//fixture/driver/uart.c", "side": "before"}).json()
+    assert new["changed"] and "err" in new["text"] and new["text"] != old["text"]
+    ctx = bob.get(f"/api/reviews/{rid}/source", params={"path": "//fixture/service/logger.c"}).json()
+    assert not ctx["changed"] and ctx["rev"] == "workspace" and "logger_flush" in ctx["text"]
+    assert svc.store.get_blob(rid, "source://fixture/service/logger.c")["text"] == ctx["text"]
+
+
+@pytest.mark.parametrize("path,status", [("//fixture/../../etc/passwd", 403), ("//other/x.c", 403),
+                                         ("//fixture/nope.c", 403)])
+def test_source_endpoint_refuses_paths_outside_the_workspace(env, path, status):
+    _, app, _ = env
+    owner, rid = _review(app)
+    assert owner.get(f"/api/reviews/{rid}/source", params={"path": path}).status_code == status
+
+
+@pytest.mark.parametrize("exc,status", [("SourceBinary", 415), ("SourceTooLarge", 413)])
+def test_source_endpoint_maps_unreadable_files(env, monkeypatch, exc, status):
+    from codetortoise.vcs import source
+    svc, app, _ = env
+    owner, rid = _review(app)
+
+    def refuse(depot):
+        raise getattr(source, exc)(depot)
+    monkeypatch.setattr(svc.source, "read", refuse)
+    r = owner.get(f"/api/reviews/{rid}/source", params={"path": "//fixture/service/logger.c"})
+    assert r.status_code == status
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_web.py -q`
Expected: FAIL — `7 failed, 10 passed` (`/board` and `/source` are not routes yet)

- [ ] **Step 3: Implement**

`backend/codetortoise/web/app.py`:

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index c7c75c4..fa870a0 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -15,6 +15,7 @@ from codetortoise.pipeline import JobRunner
 from codetortoise.services import Services
 from codetortoise.swarm import SwarmError
 from codetortoise.vcs.p4runner import P4Error
+from codetortoise.vcs.source import SourceBinary, SourceNotAllowed, SourceTooLarge
 
 COOKIE = "ct_session"
 STATIC = Path(__file__).parent / "static"
@@ -173,6 +174,44 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
                 item["name"] = overrides[str(item["level"])]
         return {"storyboard": sb, "drift": cs.get("drift", []), "layers": layers}
 
+    @app.get("/api/reviews/{rid}/board")
+    def board(rid: int, _: str = Depends(user_of)):
+        review_or_404(rid)
+        b = store.get_blob(rid, "board")
+        if b is None:
+            raise HTTPException(404, "board not built yet")
+        overrides = store.kv_get("layer_overrides") or {}
+        for layer in b.get("layers", []):
+            if str(layer["level"]) in overrides:
+                layer["name"] = overrides[str(layer["level"])]
+        return b
+
+    @app.get("/api/reviews/{rid}/source")
+    def source(rid: int, path: str, side: Literal["before", "after"] = "after", _: str = Depends(user_of)):
+        """A file's text for the board: changed files from the change set, others from the base workspace."""
+        review_or_404(rid)
+        cs = store.get_blob(rid, "changeset") or {}
+        f = next((f for f in cs.get("files", []) if f["depot"] == path), None)
+        if f is not None:
+            rev = (f.get("base_rev") or "base") if side == "before" else "changed"
+            return {"path": path, "depot": path, "rev": rev, "text": f[side], "changed": True}
+        key = f"source:{path}"
+        cached = store.get_blob(rid, key)
+        if cached is None:
+            try:
+                sf = svc.source.read(path)
+            except SourceNotAllowed as e:
+                raise HTTPException(403, str(e)) from e
+            except SourceBinary as e:
+                raise HTTPException(415, str(e)) from e
+            except SourceTooLarge as e:
+                raise HTTPException(413, str(e)) from e
+            except P4Error as e:
+                raise HTTPException(502, f"Perforce: {e}") from e
+            cached = {"path": path, "depot": sf.depot, "rev": sf.rev, "text": sf.text, "changed": False}
+            store.put_blob(rid, key, cached)
+        return cached
+
     @app.get("/api/reviews/{rid}/impact")
     def impact(rid: int, _: str = Depends(user_of)):
         review_or_404(rid)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_web.py -q`
Expected: `17 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `170 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/web/app.py backend/tests/test_web.py
git commit -m "feat(api): board and on-demand source endpoints"
```

---

### Task 6: Frontend: cylindrical lens

Pure functions for the canvas mapping (spec §3.1). Horizontal: 1:1 within `FLAT = 0.55` of the half-width around the
canvas centre; beyond it each side folds the content on that side with a Sarkar–Brown curve whose slope is 1 at the seam
(no kink): `Rw = max(sideExtent − F, R·FOLD[lens])`, `k = Rw/R − 1`, `g(t) = (k+1)t/(kt+1)`. Vertical: no squeeze in the
flat zone (layers stay parallel); beyond it `y` is pulled to the centre line by a smoothstep down to 0.7 (2×) / 0.55 (4×).
`unprojectX` inverts x by bisection (used to drag nodes). Lens 0 is the identity plus pan.

**Files:**
- Create: `frontend/src/board/lens.ts`
- Test: `frontend/src/board/lens.test.ts`

**Interfaces:**
- Produces (`frontend/src/board/lens.ts`): `BAND = 210`, `FLAT = 0.55`, `PAD = 140`, `FOLD`, `type LensStrength = 0|2|4`,
  `View{panX, panY, lens}`, `Viewport{W, H}`, `Projected{x, y, v, s}`, `vSqueeze(nd, m)`,
  `makeLens(view, vp, worldXs) -> {project(wx, wy), bandY(screenX, worldY), unprojectX(screenX)}`.

- [ ] **Step 1: Write the failing test**

`frontend/src/board/lens.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { FLAT, makeLens, vSqueeze } from "./lens";

const vp = { W: 1000, H: 800 };
const xs = Array.from({ length: 41 }, (_, i) => -2000 + i * 100);   // nodes from -2000 to 2000

describe("lens", () => {
  it("is 1:1 inside the flat zone", () => {
    const lens = makeLens({ panX: 500, panY: 100, lens: 2 }, vp, xs);
    for (const wx of [-270, -100, 0, 150, 270]) {
      const p = lens.project(wx, 300);
      expect(p.x).toBeCloseTo(wx + 500);
      expect(p.y).toBeCloseTo(400);
      expect(p.s).toBeCloseTo(1);
    }
  });

  it("folds both sides symmetrically around the focus", () => {
    const lens = makeLens({ panX: 500, panY: 0, lens: 2 }, vp, xs);
    for (const d of [300, 600, 1200, 1900]) {
      const r = lens.project(d, 0).x - 500, l = lens.project(-d, 0).x - 500;
      expect(r).toBeCloseTo(-l);
      expect(Math.abs(r)).toBeLessThan(500);
    }
  });

  it("is monotonic and keeps every node on screen", () => {
    for (const m of [2, 4] as const) {
      const lens = makeLens({ panX: 300, panY: 0, lens: m }, vp, xs);
      let prev = -Infinity;
      for (const wx of xs) {
        const x = lens.project(wx, 0).x;
        expect(x).toBeGreaterThan(prev);
        expect(x).toBeGreaterThanOrEqual(0);
        expect(x).toBeLessThanOrEqual(vp.W);
        prev = x;
      }
    }
  });

  it("has no kink where the flat zone ends", () => {
    const lens = makeLens({ panX: 500, panY: 0, lens: 4 }, vp, xs);
    const F = FLAT * 500;
    const inside = lens.project(F - 1, 0).x - lens.project(F - 2, 0).x;
    const outside = lens.project(F + 2, 0).x - lens.project(F + 1, 0).x;
    expect(outside).toBeCloseTo(inside, 1);
  });

  it("unprojectX inverts the horizontal mapping", () => {
    const lens = makeLens({ panX: 420, panY: 0, lens: 2 }, vp, xs);
    for (const wx of [-1500, -300, 0, 77, 900, 1800]) expect(lens.unprojectX(lens.project(wx, 0).x)).toBeCloseTo(wx, 0);
  });

  it("squeezes y towards the centre line only beyond the flat zone", () => {
    expect(vSqueeze(0.3, 2)).toBe(1);
    expect(vSqueeze(FLAT, 2)).toBe(1);
    expect(vSqueeze(1, 2)).toBeCloseTo(0.7);
    expect(vSqueeze(1, 4)).toBeCloseTo(0.55);
    const lens = makeLens({ panX: 500, panY: 0, lens: 2 }, vp, xs);
    const rim = lens.project(1900, 100), mid = lens.project(0, 100);
    expect(mid.y).toBeCloseTo(100);
    expect(rim.y).toBeGreaterThan(100);          // pulled towards H/2 = 400
    expect(rim.y).toBeLessThan(400);
    expect(lens.bandY(500, 100)).toBeCloseTo(100);
  });

  it("is the identity (plus pan) when off", () => {
    const lens = makeLens({ panX: 10, panY: 20, lens: 0 }, vp, xs);
    expect(lens.project(1900, 700)).toEqual({ x: 1910, y: 720, v: 1, s: 1 });
    expect(lens.unprojectX(1910)).toBeCloseTo(1900, 0);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/board/lens.test.ts`
Expected: FAIL — `Error: Cannot find module './lens'`

- [ ] **Step 3: Implement**

`frontend/src/board/lens.ts`:

```ts
/** Cylindrical lens for the board (spec §3.1): 1:1 in the middle, Sarkar–Brown fold towards the left/right rims,
 * layers converge vertically near the rims. Pure functions — everything on the board goes through the same mapping. */

export const BAND = 210;                   // world height of a layer band
export const FLAT = 0.55;                  // fraction of the half-width that stays 1:1
export const PAD = 140;                    // world padding beyond the farthest node
export const FOLD: Record<number, number> = { 2: 1.8, 4: 3.4 };

export type LensStrength = 0 | 2 | 4;
export interface View { panX: number; panY: number; lens: LensStrength }
export interface Viewport { W: number; H: number }
export interface Projected { x: number; y: number; v: number; s: number }
export interface Lens {
  project(wx: number, wy: number): Projected;
  bandY(screenX: number, worldY: number): number;
  unprojectX(screenX: number): number;
}

/** Vertical squeeze factor at normalised horizontal distance nd (0 at the focus, 1 at the rim). */
export function vSqueeze(nd: number, m: LensStrength): number {
  if (nd <= FLAT) return 1;
  const vmin = m >= 4 ? 0.55 : 0.7;
  const t = Math.min(1, (nd - FLAT) / (1 - FLAT)), e = t * t * (3 - 2 * t);
  return 1 - (1 - vmin) * e;
}

export function makeLens(view: View, vp: Viewport, worldXs: number[]): Lens {
  const { W, H } = vp, m = view.lens, half = W / 2;
  const focusX = half - view.panX;                        // world x under the canvas centre
  const minX = worldXs.length ? Math.min(...worldXs) : focusX, maxX = worldXs.length ? Math.max(...worldXs) : focusX;
  const extent = (dir: number) => Math.max(0, dir > 0 ? maxX - focusX : focusX - minX) + PAD;

  function axis(w: number): [number, number] {           // world offset from the focus -> [screen x, local scale]
    if (!m) return [half + w, 1];
    const F = FLAT * half, R = half - F, a = Math.abs(w), dir = Math.sign(w) || 1;
    if (a <= F) return [half + w, 1];
    const Rw = Math.max(extent(dir) - F, R * FOLD[m]);   // world span folded into the remaining screen span R
    const k = Rw / R - 1, t = Math.min((a - F) / Rw, 1); // slope 1 at the seam: no kink
    const g = k > 0 ? ((k + 1) * t) / (k * t + 1) : t;
    return [half + dir * (F + R * g), Math.max(0.34, 1 / Math.pow(k * t + 1, 2))];
  }
  const squeeze = (sx: number) => (m ? vSqueeze(Math.min(1, Math.abs(sx - half) / half), m) : 1);

  function project(wx: number, wy: number): Projected {
    const [x, kx] = axis(wx + view.panX - half);
    const v = squeeze(x);
    const y = H / 2 + (wy + view.panY - H / 2) * v;
    return { x, y, v, s: m ? Math.max(0.36, Math.min(1, kx) * (0.45 + 0.55 * v)) : 1 };
  }
  function bandY(screenX: number, worldY: number): number {
    return H / 2 + (worldY + view.panY - H / 2) * squeeze(screenX);
  }
  function unprojectX(screenX: number): number {         // bisection: the horizontal mapping is monotonic
    let lo = focusX - 40000, hi = focusX + 40000;
    for (let i = 0; i < 64; i++) {
      const mid = (lo + hi) / 2;
      if (project(mid, 0).x < screenX) lo = mid; else hi = mid;
    }
    return (lo + hi) / 2;
  }
  return { project, bandY, unprojectX };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/board/lens.test.ts`
Expected: `Tests  7 passed (7)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  18 passed (18)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/lens.ts frontend/src/board/lens.test.ts
git commit -m "feat(board): cylindrical lens"
```

---

### Task 7: Frontend: board state machine

One reducer holds every board interaction (spec §3.7, §4.3, §8). Rules it enforces: clicking a node opens its card or
brings it to the front and never closes it; only ✕ / Close all close cards; flow-summary step chips toggle; opening the
viewer collapses every card to a pill and remembers how they were; closing the viewer restores that snapshot exactly;
files stack newest first, reopening moves a file to the top and expands it; selecting a flow returns to Flows mode.

**Files:**
- Create: `frontend/src/board/reducer.ts`
- Test: `frontend/src/board/reducer.test.ts`

**Interfaces:**
- Consumes: `LensStrength`, `View` (Task 6).
- Produces (`frontend/src/board/reducer.ts`): `CardState{collapsed, offset?}`, `Reveal{path, line, seq}`,
  `ViewerState{files, collapsed, mode, snapshot, reveal}`, `BoardState{cards, z, viewer, view, mode, flow, about, moved}`,
  `type Action` (`card.open|toggle|front|expand|move|unpin|close|closeAll`, `viewer.open{path, line?, wide}|toggle|
  expandAll|collapseAll|mode|close|closeAll`, `flow`, `mode`, `lens`, `node.move`, `layout.reset`, `about.toggle`, `pan`),
  `initialState(lens = 2, moved = {})`, `reduce(state, action)`.

- [ ] **Step 1: Write the failing test**

`frontend/src/board/reducer.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { type Action, type BoardState, initialState, reduce } from "./reducer";

const run = (...actions: Action[]) => actions.reduce(reduce, initialState());
const open = (path: string, line?: number): Action => ({ t: "viewer.open", path, line, wide: true });

describe("cards", () => {
  it("node click opens a card and brings it to the front, never closes it", () => {
    let s = run({ t: "card.open", id: "N1" }, { t: "card.open", id: "N2" });
    expect(s.z).toEqual(["N1", "N2"]);
    s = reduce(s, { t: "card.open", id: "N1" });
    expect(Object.keys(s.cards).sort()).toEqual(["N1", "N2"]);
    expect(s.z).toEqual(["N2", "N1"]);
  });

  it("only close removes a card; close all removes every card", () => {
    let s = run({ t: "card.open", id: "N1" }, { t: "card.open", id: "N2" }, { t: "card.close", id: "N1" });
    expect(s.cards).toEqual({ N2: { collapsed: false } });
    expect(s.z).toEqual(["N2"]);
    s = reduce(s, { t: "card.closeAll" });
    expect(s.cards).toEqual({});
    expect(s.z).toEqual([]);
  });

  it("step chips toggle a card open and closed", () => {
    let s = run({ t: "card.toggle", id: "N1" });
    expect(s.cards.N1).toEqual({ collapsed: false });
    s = reduce(s, { t: "card.toggle", id: "N1" });
    expect(s.cards.N1).toBeUndefined();
  });

  it("a dragged card keeps its offset until unpinned", () => {
    let s = run({ t: "card.open", id: "N1" }, { t: "card.move", id: "N1", offset: { x: 40, y: -10 } });
    expect(s.cards.N1.offset).toEqual({ x: 40, y: -10 });
    s = reduce(s, { t: "card.unpin", id: "N1" });
    expect(s.cards.N1).toEqual({ collapsed: false });
  });

  it("front and expand ignore cards that are not open", () => {
    const s = initialState();
    expect(reduce(s, { t: "card.front", id: "N9" })).toBe(s);
    expect(reduce(s, { t: "card.expand", id: "N9" })).toBe(s);
  });
});

describe("viewer", () => {
  it("opening the viewer collapses every card and closing it restores them exactly", () => {
    let s = run({ t: "card.open", id: "N1" }, { t: "card.open", id: "N2" });
    s = reduce(s, open("//d/a.c", 10));
    expect(s.cards.N1.collapsed && s.cards.N2.collapsed).toBe(true);
    s = reduce(s, { t: "card.expand", id: "N1" });       // a pill clicked while the viewer is open
    s = reduce(s, { t: "card.open", id: "N3" });         // a new card starts as a pill
    expect(s.cards.N3.collapsed).toBe(true);
    s = reduce(s, { t: "viewer.closeAll" });
    expect(s.cards).toEqual({ N1: { collapsed: false }, N2: { collapsed: false }, N3: { collapsed: true } });
    expect(s.viewer.files).toEqual([]);
    expect(s.viewer.snapshot).toBeNull();
  });

  it("closing a card while the viewer is open drops it from the snapshot", () => {
    let s = run({ t: "card.open", id: "N1" }, open("//d/a.c"), { t: "card.close", id: "N1" }, { t: "viewer.closeAll" });
    expect(s.cards).toEqual({});
    s = run({ t: "card.open", id: "N1" }, open("//d/a.c"), { t: "card.closeAll" }, { t: "card.open", id: "N2" },
            { t: "viewer.closeAll" });
    expect(s.cards).toEqual({ N2: { collapsed: true } });
  });

  it("files stack newest first; reopening moves a file to the top and expands it", () => {
    let s = run(open("//d/a.c"), open("//d/b.c"), { t: "viewer.toggle", path: "//d/a.c" });
    expect(s.viewer.files).toEqual(["//d/b.c", "//d/a.c"]);
    expect(s.viewer.collapsed).toEqual(["//d/a.c"]);
    s = reduce(s, open("//d/a.c", 7));
    expect(s.viewer.files).toEqual(["//d/a.c", "//d/b.c"]);
    expect(s.viewer.collapsed).toEqual([]);
    expect(s.viewer.reveal).toEqual({ path: "//d/a.c", line: 7, seq: 3 });
  });

  it("expand all, collapse all, mode and per-file close", () => {
    let s = run(open("//d/a.c"), open("//d/b.c"), { t: "viewer.collapseAll" });
    expect(s.viewer.collapsed.sort()).toEqual(["//d/a.c", "//d/b.c"]);
    s = reduce(s, { t: "viewer.expandAll" });
    expect(s.viewer.collapsed).toEqual([]);
    expect(s.viewer.mode).toBe("split");
    s = reduce(s, { t: "viewer.mode", mode: "unified" });
    s = reduce(s, { t: "viewer.close", path: "//d/b.c" });
    expect(s.viewer.files).toEqual(["//d/a.c"]);
    s = reduce(s, { t: "viewer.close", path: "//d/a.c" });
    expect(s.viewer.files).toEqual([]);
    expect(s.viewer.mode).toBe("unified");               // kept for the next open
  });

  it("narrow screens start stacked", () => {
    const s = reduce(initialState(), { t: "viewer.open", path: "//d/a.c", wide: false });
    expect(s.viewer.mode).toBe("unified");
  });
});

describe("board", () => {
  it("selecting a flow returns to flows mode", () => {
    const s = run({ t: "mode", mode: "graph" }, { t: "flow", i: 2 });
    expect([s.mode, s.flow]).toEqual(["flows", 2]);
  });

  it("node moves are remembered until reset", () => {
    let s: BoardState = run({ t: "node.move", id: "N1", x: 120 }, { t: "node.move", id: "N2", x: -40 });
    expect(s.moved).toEqual({ N1: 120, N2: -40 });
    s = reduce(s, { t: "layout.reset" });
    expect(s.moved).toEqual({});
  });

  it("lens, pan and the change panel", () => {
    const s = run({ t: "lens", lens: 4 }, { t: "pan", panX: 5, panY: 6 }, { t: "about.toggle" });
    expect(s.view).toEqual({ panX: 5, panY: 6, lens: 4 });
    expect(s.about).toBe(true);
    expect(reduce(s, { t: "about.toggle", open: false }).about).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/board/reducer.test.ts`
Expected: FAIL — `Error: Cannot find module './reducer'`

- [ ] **Step 3: Implement**

`frontend/src/board/reducer.ts`:

```ts
/** Board state machine (spec §3.7, §4.3). Pure: every interaction is one transition. */
import type { LensStrength, View } from "./lens";

export interface CardState { collapsed: boolean; offset?: { x: number; y: number } }
export interface Reveal { path: string; line: number | null; seq: number }
export interface ViewerState {
  files: string[];                          // newest first
  collapsed: string[];
  mode: "unified" | "split" | null;         // chosen on first open from the screen width
  snapshot: Record<string, boolean> | null; // card collapse state from before the viewer opened
  reveal: Reveal | null;                    // last file/line to scroll to (seq bumps on every open)
}
export interface BoardState {
  cards: Record<string, CardState>;
  z: string[];                              // stacking order, last = front
  viewer: ViewerState;
  view: View;
  mode: "flows" | "graph";
  flow: number;
  about: boolean;
  moved: Record<string, number>;            // node id -> world x chosen by this viewer
}

export type Action =
  | { t: "card.open"; id: string }
  | { t: "card.toggle"; id: string }
  | { t: "card.front"; id: string }
  | { t: "card.expand"; id: string }
  | { t: "card.move"; id: string; offset: { x: number; y: number } }
  | { t: "card.unpin"; id: string }
  | { t: "card.close"; id: string }
  | { t: "card.closeAll" }
  | { t: "viewer.open"; path: string; line?: number | null; wide: boolean }
  | { t: "viewer.toggle"; path: string }
  | { t: "viewer.expandAll" }
  | { t: "viewer.collapseAll" }
  | { t: "viewer.mode"; mode: "unified" | "split" }
  | { t: "viewer.close"; path: string }
  | { t: "viewer.closeAll" }
  | { t: "flow"; i: number }
  | { t: "mode"; mode: "flows" | "graph" }
  | { t: "lens"; lens: LensStrength }
  | { t: "node.move"; id: string; x: number }
  | { t: "layout.reset" }
  | { t: "about.toggle"; open?: boolean }
  | { t: "pan"; panX: number; panY: number };

export function initialState(lens: LensStrength = 2, moved: Record<string, number> = {}): BoardState {
  return {
    cards: {}, z: [], viewer: { files: [], collapsed: [], mode: null, snapshot: null, reveal: null },
    view: { panX: 0, panY: 0, lens }, mode: "flows", flow: 0, about: false, moved,
  };
}

const front = (z: string[], id: string) => [...z.filter((x) => x !== id), id];
const without = <T,>(rec: Record<string, T>, key: string) => {
  const { [key]: _, ...rest } = rec;
  return rest;
};

function closeViewer(s: BoardState): BoardState {
  const cards = { ...s.cards };
  for (const [id, collapsed] of Object.entries(s.viewer.snapshot ?? {}))
    if (cards[id]) cards[id] = { ...cards[id], collapsed };
  return { ...s, cards, viewer: { ...s.viewer, files: [], collapsed: [], snapshot: null } };
}

export function reduce(s: BoardState, a: Action): BoardState {
  const v = s.viewer;
  switch (a.t) {
    case "card.open": {                     // open, or expand / bring to front — never closes
      const c = s.cards[a.id];
      const next = c ? { ...c, collapsed: false } : { collapsed: v.files.length > 0 };
      return { ...s, cards: { ...s.cards, [a.id]: next }, z: front(s.z, a.id) };
    }
    case "card.toggle": {                   // flow-summary step chips: open <-> close
      const c = s.cards[a.id];
      return c && !c.collapsed ? reduce(s, { t: "card.close", id: a.id }) : reduce(s, { t: "card.open", id: a.id });
    }
    case "card.front":
      return s.cards[a.id] ? { ...s, z: front(s.z, a.id) } : s;
    case "card.expand":
      if (!s.cards[a.id]) return s;
      return { ...s, cards: { ...s.cards, [a.id]: { ...s.cards[a.id], collapsed: false } }, z: front(s.z, a.id) };
    case "card.move":
      if (!s.cards[a.id]) return s;
      return { ...s, cards: { ...s.cards, [a.id]: { ...s.cards[a.id], offset: a.offset } } };
    case "card.unpin": {
      const c = s.cards[a.id];
      if (!c) return s;
      return { ...s, cards: { ...s.cards, [a.id]: { collapsed: c.collapsed } } };
    }
    case "card.close": {
      const snapshot = v.snapshot && a.id in v.snapshot ? without(v.snapshot, a.id) : v.snapshot;
      return { ...s, cards: without(s.cards, a.id), z: s.z.filter((x) => x !== a.id), viewer: { ...v, snapshot } };
    }
    case "card.closeAll":
      return { ...s, cards: {}, z: [], viewer: { ...v, snapshot: v.snapshot ? {} : null } };
    case "viewer.open": {
      let cards = s.cards, snapshot = v.snapshot, mode = v.mode;
      if (!v.files.length) {                // first file: collapse every card to a pill, remember how they were
        snapshot = Object.fromEntries(Object.entries(s.cards).map(([id, c]) => [id, c.collapsed]));
        cards = Object.fromEntries(Object.entries(s.cards).map(([id, c]) => [id, { ...c, collapsed: true }]));
        mode = mode ?? (a.wide ? "split" : "unified");
      }
      const files = [a.path, ...v.files.filter((p) => p !== a.path)];
      const reveal = { path: a.path, line: a.line ?? null, seq: (v.reveal?.seq ?? 0) + 1 };
      return { ...s, cards, viewer: { files, collapsed: v.collapsed.filter((p) => p !== a.path), mode, snapshot, reveal } };
    }
    case "viewer.toggle": {
      const collapsed = v.collapsed.includes(a.path) ? v.collapsed.filter((p) => p !== a.path) : [...v.collapsed, a.path];
      return { ...s, viewer: { ...v, collapsed } };
    }
    case "viewer.expandAll":
      return { ...s, viewer: { ...v, collapsed: [] } };
    case "viewer.collapseAll":
      return { ...s, viewer: { ...v, collapsed: [...v.files] } };
    case "viewer.mode":
      return { ...s, viewer: { ...v, mode: a.mode } };
    case "viewer.close": {
      const files = v.files.filter((p) => p !== a.path);
      if (!files.length) return closeViewer(s);
      return { ...s, viewer: { ...v, files, collapsed: v.collapsed.filter((p) => p !== a.path) } };
    }
    case "viewer.closeAll":
      return v.files.length ? closeViewer(s) : s;
    case "flow":
      return { ...s, flow: a.i, mode: "flows" };
    case "mode":
      return { ...s, mode: a.mode };
    case "lens":
      return { ...s, view: { ...s.view, lens: a.lens } };
    case "node.move":
      return { ...s, moved: { ...s.moved, [a.id]: a.x } };
    case "layout.reset":
      return { ...s, moved: {} };
    case "about.toggle":
      return { ...s, about: a.open ?? !s.about };
    case "pan":
      return { ...s, view: { ...s.view, panX: a.panX, panY: a.panY } };
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/board/reducer.test.ts`
Expected: `Tests  13 passed (13)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  31 passed (31)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/reducer.ts frontend/src/board/reducer.test.ts
git commit -m "feat(board): board state machine"
```

---

### Task 8: Frontend: board types, world layout and card placement

TypeScript mirror of the board blob, and the pure geometry the canvas uses: which band each layer occupies (highest level
on top, unlayered last), world positions with the viewer's moved nodes, the pan that centres a set of nodes, the selected
flow's nodes and edges, and where cards go (spec §3.4): pills under their node, dragged cards at their offset from the
node, others to the right, left or above the node clear of it, then into canvas corners — first free spot, else least
overlap — scaled by the lens at the node (floor 0.55).

**Files:**
- Create: `frontend/src/board/types.ts`
- Create: `frontend/src/board/layout.ts`
- Test: `frontend/src/board/layout.test.ts`

**Interfaces:**
- Consumes: `BAND`, `Projected` (Task 6).
- Produces: `frontend/src/board/types.ts` (`Board`, `BoardNode`, `BoardEdge`, `Annotation`, `BoardFlow`, `About`,
  `AboutFile`, `NodeChange`, `SourceText`); `frontend/src/board/layout.ts`: `layerRows(board) -> Map<level, row>`,
  `worldY(row)`, `worldNodes(board, moved) -> Map<id, {id, x, y}>`, `centrePan(ids, nodes, W, H)`,
  `flowSets(flow, graph) -> {onPath, pairs}`, `placeCards(cards: CardBox[], W, H) -> Map<id, Rect & {k}>`.

- [ ] **Step 1: Write the failing test**

`frontend/src/board/layout.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { centrePan, flowSets, layerRows, placeCards, worldNodes } from "./layout";
import type { Board, BoardFlow } from "./types";

const node = (id: string, layer: number | null, x: number) => ({
  id, key: id, label: id, kind: "function" as const, layer, path: null, local: null, range: null, change: null, x, warn: 0,
});
const board = {
  nodes: [node("A", 3, 0), node("B", 1, -220), node("C", 1, 220), node("D", null, 0)],
  edges: [], flows: [], impacts: [], layers: [{ level: 3, name: "app" }, { level: 1, name: "hal" }],
  about: { intent: "", intent_source: "template", why: [], cls: [], tree: [] }, hidden_nodes: 0,
} as Board;

describe("layout", () => {
  it("puts higher layers on top and unlayered nodes last", () => {
    expect([...layerRows(board)]).toEqual([[3, 0], [1, 1], [-1, 2]]);
    const w = worldNodes(board, { C: 500 });
    expect(w.get("A")).toEqual({ id: "A", x: 0, y: 105 });
    expect(w.get("C")).toEqual({ id: "C", x: 500, y: 315 });
    expect(w.get("D")!.y).toBe(525);
  });

  it("centres a set of nodes", () => {
    const w = worldNodes(board, {});
    expect(centrePan(["B", "C"], w, 1000, 600)).toEqual({ panX: 500, panY: 300 - 315 });
    expect(centrePan(["nope"], w, 1000, 600)).toBeNull();
  });

  it("marks the selected flow's nodes and call pairs", () => {
    const f = { path: ["A", "B", "C"] } as BoardFlow;
    const s = flowSets(f, false);
    expect([...s.onPath]).toEqual(["A", "B", "C"]);
    expect([...s.pairs]).toEqual(["A>B", "B>C"]);
    expect(flowSets(f, true).onPath.size).toBe(0);
  });

  it("places cards beside their node without overlap and inside the canvas", () => {
    const at = { x: 500, y: 300, v: 1, s: 1 };
    const rects = placeCards([{ id: "1", at, w: 300, h: 200, collapsed: false },
                              { id: "2", at, w: 300, h: 200, collapsed: false }], 1200, 800);
    const a = rects.get("1")!, b = rects.get("2")!;
    expect(a.x).toBe(600);                                     // right of the node, clear of it
    expect(b.x + b.w).toBeLessThanOrEqual(450);                // then left of it
    for (const r of [a, b]) expect(r.x >= 8 && r.y >= 8 && r.x + r.w <= 1192 && r.y + r.h <= 792).toBe(true);
  });

  it("keeps dragged offsets, scales by the lens and puts pills under the node", () => {
    const rects = placeCards([
      { id: "d", at: { x: 400, y: 300, v: 1, s: 0.4 }, w: 300, h: 200, collapsed: false, offset: { x: 10, y: 20 } },
      { id: "p", at: { x: 600, y: 300, v: 1, s: 1 }, w: 100, h: 30, collapsed: true },
    ], 1200, 800);
    const d = rects.get("d")!;
    expect([d.x, d.y, Math.round(d.w), Math.round(d.h), d.k]).toEqual([410, 320, 165, 110, 0.55]);
    expect(rects.get("p")).toEqual({ x: 550, y: 324, w: 100, h: 30, k: 1 });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/board/layout.test.ts`
Expected: FAIL — `Error: Cannot find module './layout'`

- [ ] **Step 3: Implement**

`frontend/src/board/types.ts`:

```ts
/** Review board model, as served by GET /api/reviews/{id}/board (backend codetortoise/board.py). */
export interface NodeChange { kind: "modified" | "signature" | "added" | "removed"; add: number; rem: number }
export interface BoardNode {
  id: string; key: string; label: string; kind: "function" | "field"; layer: number | null;
  path: string | null; local: string | null; range: [number, number] | null; change: NodeChange | null; x: number; warn: number;
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
  findings: string[]; text: string; what: string; effect: string; check: string; what_source: "template" | "llm";
}
export interface AboutFile { path: string; name: string; action: string; cls: number[]; add: number; rem: number }
export interface About {
  intent: string; intent_source: "template" | "llm";
  why: { severity: string; text: string; finding: string }[];
  cls: { cl: number; user: string; description: string; files: number }[];
  tree: { dir: string; files: AboutFile[] }[];
}
export interface Board {
  nodes: BoardNode[]; edges: BoardEdge[]; flows: BoardFlow[]; impacts: Annotation[];
  layers: { level: number; name: string }[]; about: About; hidden_nodes: number;
}
export interface SourceText { path: string; depot: string; rev: string; text: string; changed: boolean }
```

`frontend/src/board/layout.ts`:

```ts
/** World geometry helpers for the board (pure). The backend chooses initial x (barycentre ordering); the viewer may
 * move nodes within their layer. */
import { BAND, type Projected } from "./lens";
import type { Board, BoardFlow } from "./types";

/** Row index (0 = top band) for each layer level present on the board; unlayered nodes (-1) go last. */
export function layerRows(board: Board): Map<number, number> {
  const levels = [...new Set([...board.layers.map((l) => l.level), ...board.nodes.map((n) => n.layer ?? -1)])]
    .sort((a, b) => b - a);
  return new Map(levels.map((lv, i) => [lv, i]));
}

export const worldY = (row: number) => row * BAND + BAND / 2;

export interface WorldNode { id: string; x: number; y: number }
export function worldNodes(board: Board, moved: Record<string, number>): Map<string, WorldNode> {
  const rows = layerRows(board);
  return new Map(board.nodes.map((n) => [n.id, { id: n.id, x: moved[n.id] ?? n.x, y: worldY(rows.get(n.layer ?? -1) ?? 0) }]));
}

/** Pan that centres the bounding box of `ids` in a W×H canvas. */
export function centrePan(ids: string[], nodes: Map<string, WorldNode>, W: number, H: number) {
  const pts = ids.map((id) => nodes.get(id)).filter((n): n is WorldNode => !!n);
  if (!pts.length) return null;
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  return { panX: W / 2 - (Math.min(...xs) + Math.max(...xs)) / 2, panY: H / 2 - (Math.min(...ys) + Math.max(...ys)) / 2 };
}

/** Node ids and call edges ("a>b") on the selected flow; empty in whole-graph mode. */
export function flowSets(flow: BoardFlow | undefined, graph: boolean) {
  if (graph || !flow) return { onPath: new Set<string>(), pairs: new Set<string>() };
  return { onPath: new Set(flow.path), pairs: new Set(flow.path.slice(1).map((b, i) => `${flow.path[i]}>${b}`)) };
}

const NODE_HALF = 100;                             // about half a changed node's width, in screen px at scale 1

export interface Rect { x: number; y: number; w: number; h: number }
export interface CardBox { id: string; at: Projected; w: number; h: number; collapsed: boolean; offset?: { x: number; y: number } }

/** Screen rectangles for cards (spec §3.4): pills under their node; dragged cards follow their node at the chosen
 * offset; others go right/left/above of the node, then into canvas corners — first free spot, else least overlap. */
export function placeCards(cards: CardBox[], W: number, H: number): Map<string, Rect & { k: number }> {
  const placed: Rect[] = [], out = new Map<string, Rect & { k: number }>();
  const area = (a: Rect, b: Rect) =>
    Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
  const overlap = (r: Rect) => placed.reduce((s, q) => s + area(r, q), 0);
  for (const c of cards) {
    const p = c.at, k = c.collapsed ? 1 : Math.max(0.55, p.s), cw = c.w * k, ch = Math.min(c.h * k, H - 16);
    const cx = (x: number) => Math.max(8, Math.min(x, W - cw - 8)), cy = (y: number) => Math.max(8, Math.min(y, H - ch - 8));
    let r: Rect;
    if (c.collapsed) r = { x: cx(p.x - cw / 2), y: cy(p.y + 24 * p.s), w: cw, h: ch };
    else if (c.offset) r = { x: p.x + c.offset.x, y: p.y + c.offset.y, w: cw, h: ch };
    else {
      const gap = NODE_HALF * p.s;                 // clear of the node itself, so its ⤢ button stays reachable
      const cands = [[p.x + gap, p.y - 40], [p.x - gap - cw, p.y - 40], [p.x + gap, p.y - ch + 40],
        [p.x - gap - cw, p.y - ch + 40], [W - cw - 8, 8], [8, 8], [W - cw - 8, H - ch - 8], [8, H - ch - 8]]
        .map(([x, y]) => ({ x: cx(x), y: cy(y), w: cw, h: ch }));
      r = cands.find((t) => overlap(t) === 0) ?? cands.reduce((b, t) => (overlap(t) < overlap(b) ? t : b));
    }
    placed.push(r);
    out.set(c.id, { ...r, k });
  }
  return out;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/board/layout.test.ts`
Expected: `Tests  5 passed (5)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  36 passed (36)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/types.ts frontend/src/board/layout.ts frontend/src/board/layout.test.ts
git commit -m "feat(board): board types, world layout and card placement"
```

---

### Task 9: Frontend: code rows, highlighter, per-viewer preferences

`codeRows.ts` decides what a code view shows, in order: numbered diff (or plain) lines — or side-by-side pairs — each
followed by its annotations and, when a comment exists or was just opened, its thread slot. Function cards slice a diff
to the function's range, keeping deletions made inside it. `highlight.ts` is the prototype's C/C++ token highlighter,
returning tokens (never HTML). `prefs.ts` wraps localStorage (spec §4.4): storage may be missing, throw or hold junk;
defaults apply then.

**Files:**
- Create: `frontend/src/board/codeRows.ts`
- Create: `frontend/src/board/highlight.ts`
- Create: `frontend/src/board/prefs.ts`
- Test: `frontend/src/board/codeRows.test.ts`
- Test: `frontend/src/board/highlight.test.ts`
- Test: `frontend/src/board/prefs.test.ts`

**Interfaces:**
- Consumes: `Annotation` (Task 8).
- Produces: `codeRows.ts`: `Line{t: "="|"+"|"-", o, n, text}`, `Side`, `Item`, `lineDiff(before, after)`,
  `plainLines(text)`, `sliceRange(lines, lo, hi)`, `lineKey(side, no)`, `codeItems(lines, mode, anns, threads)`;
  `highlight.ts`: `tokens(src) -> {cls, text}[]` (classes `kw ty num str cm fn mc pp`);
  `prefs.ts`: `load(key, fallback)`, `save(key, value)`, `keys.{moved(id), viewerW, aboutW, lens}`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/board/codeRows.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { codeItems, lineDiff, plainLines, sliceRange } from "./codeRows";
import type { Annotation } from "./types";

const before = "a\nb\nc\nd\n";
const after = "a\nB\nc\nx\nd\n";
const ann = (line: number, severity: Annotation["severity"] = "warn", side: Annotation["side"] = "new") =>
  ({ node: "N1", path: "//d/f.c", line, side, severity, channel: "state", title: "State", text: `at ${line}`,
     finding: null, cause: null, landing: false }) as Annotation;

describe("code rows", () => {
  it("numbers both sides of a diff", () => {
    expect(lineDiff(before, after).map((l) => `${l.t}${l.o ?? ""}/${l.n ?? ""}`))
      .toEqual(["=1/1", "-2/", "+/2", "=3/3", "+/4", "=4/5"]);
  });

  it("slices a function's range, keeping deletions made inside it", () => {
    const rows = sliceRange(lineDiff(before, after), 2, 3);
    expect(rows.map((l) => l.text)).toEqual(["b", "B", "c"]);
    expect(sliceRange(plainLines("1\n2\n3\n4"), 3, 9).map((l) => l.n)).toEqual([3, 4]);
  });

  it("puts annotations and the thread right under their line", () => {
    const items = codeItems(lineDiff(before, after), "unified", [ann(3), ann(2, "ok"), ann(2, "warn", "old")],
                            new Set(["new:3", "old:2"]));
    expect(items.map((i) => i.kind === "line" ? i.line.text : i.kind === "ann" ? `ann ${i.ann.side}${i.ann.line}`
                                                                              : i.kind === "thread" ? `thread ${i.side}${i.no}` : "?"))
      .toEqual(["a", "b", "ann old2", "thread old2", "B", "ann new2", "c", "ann new3", "thread new3", "x", "d"]);
    const c = items.find((i) => i.kind === "line" && i.line.text === "c");
    expect(c && c.kind === "line" && c.hot).toBe(true);           // warn on an unchanged line
  });

  it("pairs deletions with additions side by side", () => {
    const items = codeItems(lineDiff(before, after), "split", [ann(2)], new Set());
    const pairs = items.filter((i) => i.kind === "pair").map((i) => i.kind === "pair" ? `${i.l?.text ?? "_"}|${i.r?.text ?? "_"}` : "");
    expect(pairs).toEqual(["a|a", "b|B", "c|c", "_|x", "d|d"]);
    expect(items[2]).toMatchObject({ kind: "ann" });
  });
});
```

`frontend/src/board/highlight.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { tokens } from "./highlight";

describe("highlight", () => {
  it("classifies C tokens and keeps the text intact", () => {
    const src = '    if (len > 64) { *err += 1; return uart_send(u, "x\\n", REG_CTRL); } // overflow';
    const t = tokens(src);
    expect(t.map((x) => x.text).join("")).toBe(src);
    const cls = (text: string) => t.find((x) => x.text === text)?.cls;
    expect(cls("if")).toBe("kw");
    expect(cls("64")).toBe("num");
    expect(cls("uart_send")).toBe("fn");
    expect(cls('"x\\n"')).toBe("str");
    expect(cls("REG_CTRL")).toBe("mc");
    expect(cls("// overflow")).toBe("cm");
  });

  it("marks types and preprocessor lines", () => {
    expect(tokens("unsigned int x;").filter((x) => x.cls === "ty").map((x) => x.text)).toEqual(["unsigned", "int"]);
    expect(tokens("uint32_t v;")[0]).toEqual({ cls: "ty", text: "uint32_t" });
    expect(tokens('#include "a.h"')[0]).toEqual({ cls: "pp", text: "#include" });
  });
});
```

`frontend/src/board/prefs.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { keys, load, save } from "./prefs";

afterEach(() => vi.unstubAllGlobals());

describe("prefs", () => {
  it("round-trips through localStorage", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
    save(keys.moved(7), { N1: 40 });
    expect(load(keys.moved(7), {})).toEqual({ N1: 40 });
    expect(load(keys.lens, 2)).toBe(2);
  });

  it("falls back when storage throws or holds junk", () => {
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("quota"); } } });
    expect(load(keys.lens, 2)).toBe(2);
    expect(() => save(keys.lens, 4)).not.toThrow();
    vi.stubGlobal("window", { localStorage: { getItem: () => "{not json", setItem: () => {} } });
    expect(load(keys.aboutW, 360)).toBe(360);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/board/codeRows.test.ts src/board/highlight.test.ts src/board/prefs.test.ts`
Expected: FAIL — `Error: Cannot find module './codeRows'` (and `./highlight`, `./prefs`)

- [ ] **Step 3: Implement**

`frontend/src/board/codeRows.ts`:

```ts
/** What a code view renders, in order: lines (or side-by-side pairs), the annotations under each line, and the
 * comment thread slot after them. Pure, so placement is unit-tested; CodeView only draws it. */
import { diffLines } from "diff";
import type { Annotation } from "./types";

export interface Line { t: "=" | "+" | "-"; o: number | null; n: number | null; text: string }
export type Side = "new" | "old";
export type Item =
  | { kind: "line"; line: Line; hot: boolean; side: Side; no: number }
  | { kind: "pair"; l: Line | null; r: Line | null; hot: boolean; side: Side; no: number }
  | { kind: "ann"; ann: Annotation }
  | { kind: "thread"; side: Side; no: number };

const split = (v: string) => {
  const lines = v.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines;
};

export function lineDiff(before: string, after: string): Line[] {
  const out: Line[] = [];
  let o = 1, n = 1;
  for (const part of diffLines(before, after)) {
    for (const text of split(part.value)) {
      if (part.added) out.push({ t: "+", o: null, n: n++, text });
      else if (part.removed) out.push({ t: "-", o: o++, n: null, text });
      else out.push({ t: "=", o: o++, n: n++, text });
    }
  }
  return out;
}

export const plainLines = (text: string): Line[] => split(text).map((t, i) => ({ t: "=", o: i + 1, n: i + 1, text: t }));

/** Lines whose new-side position is within [lo, hi]; deleted lines count at the position they were removed from. */
export function sliceRange(lines: Line[], lo: number, hi: number): Line[] {
  let cur = 0;
  return lines.filter((l) => {
    if (l.n !== null) cur = l.n;
    const at = l.n ?? cur + 1;
    return at >= lo && at <= hi;
  });
}

const where = (l: Line): [Side, number] => (l.n !== null ? ["new", l.n] : ["old", l.o!]);
export const lineKey = (side: Side, no: number) => `${side}:${no}`;

export function codeItems(lines: Line[], mode: "unified" | "split", anns: Annotation[], threads: Set<string>): Item[] {
  const at = (side: Side, no: number) => anns.filter((a) => a.side === side && a.line === no);
  const out: Item[] = [];
  const tail = (side: Side, no: number) => {
    for (const ann of at(side, no)) out.push({ kind: "ann", ann });
    if (threads.has(lineKey(side, no))) out.push({ kind: "thread", side, no });
  };
  const isHot = (l: Line | null) => !!l && l.t === "=" && at(...where(l)).some((a) => a.severity === "warn");
  if (mode === "unified") {
    for (const line of lines) {
      const [side, no] = where(line);
      out.push({ kind: "line", line, hot: isHot(line), side, no });
      tail(side, no);
    }
    return out;
  }
  let k = 0;
  while (k < lines.length) {
    const pairs: [Line | null, Line | null][] = [];
    if (lines[k].t === "=") pairs.push([lines[k], lines[k++]]);
    else {
      const dels: Line[] = [], adds: Line[] = [];
      while (k < lines.length && lines[k].t === "-") dels.push(lines[k++]);
      while (k < lines.length && lines[k].t === "+") adds.push(lines[k++]);
      for (let q = 0; q < Math.max(dels.length, adds.length); q++) pairs.push([dels[q] ?? null, adds[q] ?? null]);
    }
    for (const [l, r] of pairs) {
      const [side, no] = where((r ?? l)!);
      out.push({ kind: "pair", l, r, hot: isHot(r), side, no });
      tail(side, no);
    }
  }
  return out;
}
```

`frontend/src/board/highlight.ts`:

```ts
/** Minimal C/C++ token highlighter (from the prototype). Returns tokens, never HTML. */
export interface Token { cls: string | null; text: string }

const TYPES = /^(int|unsigned|signed|char|void|bool|short|long|float|double|auto|size_t|ssize_t|[a-z0-9_]+_t)$/;
const RE = new RegExp([
  /(\/\*.*?\*\/|\/\/.*$)/.source,                                        // 1 comment
  /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/.source,                        // 2 string / char
  /(^\s*#\s*\w+)/.source,                                                // 3 preprocessor
  /\b(int|unsigned|signed|char|void|bool|short|long|float|double|auto|size_t|ssize_t|[a-z0-9_]+_t|const|struct|union|enum|class|namespace|template|typename|typedef|return|if|else|for|while|do|switch|case|default|break|continue|goto|static|extern|inline|volatile|virtual|override|public|private|protected|sizeof|new|delete|this|nullptr|true|false|NULL|constexpr|using|operator|static_cast|reinterpret_cast|const_cast|dynamic_cast)\b/.source, // 4 keyword
  /\b([A-Z_][A-Z0-9_]{2,})\b/.source,                                    // 5 macro-like
  /\b(0x[0-9a-fA-F]+|\d+(?:\.\d+)?[uUlLfF]*)\b/.source,                  // 6 number
  /\b([A-Za-z_]\w*)(?=\s*\()/.source,                                    // 7 call
].join("|"), "g");

export function tokens(src: string): Token[] {
  const out: Token[] = [];
  let last = 0;
  RE.lastIndex = 0;
  for (let m = RE.exec(src); m; m = RE.exec(src)) {
    if (m[0] === "") { RE.lastIndex++; continue; }
    if (m.index > last) out.push({ cls: null, text: src.slice(last, m.index) });
    const t = m[0];
    const cls = m[1] ? "cm" : m[2] ? "str" : m[3] ? "pp" : m[4] ? (TYPES.test(t) ? "ty" : "kw") : m[5] ? "mc" : m[6] ? "num" : "fn";
    out.push({ cls, text: t });
    last = m.index + t.length;
  }
  if (last < src.length) out.push({ cls: null, text: src.slice(last) });
  return out;
}
```

`frontend/src/board/prefs.ts`:

```ts
/** Per-viewer preferences in localStorage (spec §4.4). Storage may be missing or throw; defaults apply then. */
export function load<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function save(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode, quota, blocked storage: the preference just isn't kept */
  }
}

export const keys = {
  moved: (reviewId: number) => `ct.board.${reviewId}.moved`,
  viewerW: "ct.panel.viewerW",
  aboutW: "ct.panel.aboutW",
  lens: "ct.lens",
};
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/board/codeRows.test.ts src/board/highlight.test.ts src/board/prefs.test.ts`
Expected: `Tests  8 passed (8)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  44 passed (44)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/codeRows.ts frontend/src/board/highlight.ts frontend/src/board/prefs.ts frontend/src/board/codeRows.test.ts frontend/src/board/highlight.test.ts frontend/src/board/prefs.test.ts
git commit -m "feat(board): code rows, highlighter and per-viewer preferences"
```

---

### Task 10: Frontend: line comment anchors and board API calls

Line comments anchor to `{path, side, line}` with the depot path (spec §4.5) everywhere — cards, the file viewer and the
Files tab (`cl` added for per-CL diffs). M1 comments (`{depot, cl, side, line}`) made on the cumulative diff (`cl` null)
must keep showing. `Comments` gains an optional `match` predicate (which root comments belong to this anchor) and
`autoFocus`. `api.ts` gains `board(id)` and `source(id, path, side)`.

**Files:**
- Create: `frontend/src/lib/anchors.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/Comments.tsx`
- Modify: `frontend/src/components/DiffView.tsx`
- Test: `frontend/src/lib/anchors.test.ts`

**Interfaces:**
- Consumes: `Board`, `SourceText` (Task 8).
- Produces: `frontend/src/lib/anchors.ts`: `lineAnchor(path, side, line, cl?)`, `onLine(comment, path, side, line, cl = null)`;
  `Comments` props `match?: (c: Comment) => boolean`, `autoFocus?: boolean`; `api.board(id)`, `api.source(id, path, side)`.

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/anchors.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Comment } from "../api";
import { lineAnchor, onLine } from "./anchors";

const c = (anchor: Record<string, unknown>) => ({ id: 1, parent_id: null, anchor_kind: "line", anchor } as Comment);

describe("line anchors", () => {
  it("match the new shape and M1's cumulative-diff shape", () => {
    expect(onLine(c(lineAnchor("//d/a.c", "new", 3)), "//d/a.c", "new", 3)).toBe(true);
    expect(onLine(c({ depot: "//d/a.c", cl: null, side: "new", line: 3 }), "//d/a.c", "new", 3)).toBe(true);
    expect(onLine(c({ depot: "//d/a.c", cl: 101, side: "new", line: 3 }), "//d/a.c", "new", 3)).toBe(false);
    expect(onLine(c({ depot: "//d/a.c", cl: 101, side: "new", line: 3 }), "//d/a.c", "new", 3, 101)).toBe(true);
    expect(onLine(c(lineAnchor("//d/a.c", "old", 3)), "//d/a.c", "new", 3)).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/lib/anchors.test.ts && npx tsc --noEmit`
Expected: FAIL — `Error: Cannot find module './anchors'`

- [ ] **Step 3: Implement**

`frontend/src/lib/anchors.ts`:

```ts
import type { Comment } from "../api";

/** Line comment anchor (spec §4.5): depot path, side of the diff, line number on that side. */
export const lineAnchor = (path: string, side: "new" | "old", line: number, cl?: number | null) =>
  cl == null ? { path, side, line } : { path, cl, side, line };

/** Does a root comment sit on this line? Reads both the current shape and M1's {depot, cl, side, line}
 * (M1 comments made on the cumulative diff have cl null). */
export function onLine(c: Comment, path: string, side: "new" | "old", line: number, cl: number | null = null): boolean {
  if (c.anchor_kind !== "line" || c.anchor.side !== side || c.anchor.line !== line) return false;
  const p = (c.anchor.path ?? c.anchor.depot) as string | undefined;
  return p === path && ((c.anchor.cl as number | null | undefined) ?? null) === cl;
}
```

`frontend/src/api.ts`:

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index 151cd45..7281ae3 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -50,6 +50,9 @@ export interface Comment {
 export interface HealthCheck { name: string; ok: boolean; hard: boolean; detail: string }
 export interface Health { checks: HealthCheck[]; ready: boolean; index_generation: number; libclang: string | null; strip_flags: string[]; index_building: boolean }
 
+export type { Board, SourceText } from "./board/types";
+import type { Board, SourceText } from "./board/types";
+
 export class ApiError extends Error {
   constructor(public status: number, message: string) { super(message); }
 }
@@ -81,6 +84,9 @@ export const api = {
   rerun: (id: number) => call("POST", `/api/reviews/${id}/rerun`),
   storyboard: (id: number) => call<StoryboardResponse>("GET", `/api/reviews/${id}/storyboard`),
   impact: (id: number) => call<Impact | null>("GET", `/api/reviews/${id}/impact`),
+  board: (id: number) => call<Board>("GET", `/api/reviews/${id}/board`),
+  source: (id: number, path: string, side: "before" | "after" = "after") =>
+    call<SourceText>("GET", `/api/reviews/${id}/source?${new URLSearchParams({ path, side })}`),
   findings: (id: number) => call<Finding[]>("GET", `/api/reviews/${id}/findings`),
   setFindingState: (id: number, fid: string, state: Finding["state"]) =>
     call("PATCH", `/api/reviews/${id}/findings/${fid}`, { state }),
```

`frontend/src/components/Comments.tsx`:

```diff
diff --git a/frontend/src/components/Comments.tsx b/frontend/src/components/Comments.tsx
index 62b8113..e74565e 100644
--- a/frontend/src/components/Comments.tsx
+++ b/frontend/src/components/Comments.tsx
@@ -13,11 +13,14 @@ interface Props {
   anchor: Record<string, unknown>;
   onChange: () => void;
   compact?: boolean;
+  /** Which root comments belong here (default: same kind and anchor fields). */
+  match?: (c: Comment) => boolean;
+  autoFocus?: boolean;
 }
 
 /** All threads for one anchor plus a composer. */
-export default function Comments({ reviewId, comments, kind, anchor, onChange, compact }: Props) {
-  const roots = comments.filter((c) => c.parent_id === null && anchorMatches(c, kind, anchor));
+export default function Comments({ reviewId, comments, kind, anchor, onChange, compact, match, autoFocus }: Props) {
+  const roots = comments.filter((c) => c.parent_id === null && (match ? match(c) : anchorMatches(c, kind, anchor)));
   const [open, setOpen] = useState(!compact || roots.length > 0);
   if (!open)
     return <button className="link small" onClick={() => setOpen(true)}>+ comment</button>;
@@ -27,7 +30,7 @@ export default function Comments({ reviewId, comments, kind, anchor, onChange, c
         <Thread key={root.id} root={root} replies={comments.filter((c) => c.parent_id === root.id)}
                 reviewId={reviewId} onChange={onChange} />
       ))}
-      <Composer onSubmit={(body) => api.addComment(reviewId, body, kind, anchor).then(onChange)}
+      <Composer onSubmit={(body) => api.addComment(reviewId, body, kind, anchor).then(onChange)} autoFocus={autoFocus}
                 placeholder={roots.length ? "Start another thread…" : "Leave a comment…"} />
     </div>
   );
@@ -78,7 +81,8 @@ function CommentView({ c, onChange }: { c: Comment; onChange: () => void }) {
   );
 }
 
-function Composer({ onSubmit, placeholder, small }: { onSubmit: (body: string) => Promise<unknown>; placeholder: string; small?: boolean }) {
+function Composer({ onSubmit, placeholder, small, autoFocus }:
+  { onSubmit: (body: string) => Promise<unknown>; placeholder: string; small?: boolean; autoFocus?: boolean }) {
   const [body, setBody] = useState("");
   const [busy, setBusy] = useState(false);
   return (
@@ -88,7 +92,8 @@ function Composer({ onSubmit, placeholder, small }: { onSubmit: (body: string) =
       setBusy(true);
       onSubmit(body.trim()).then(() => setBody("")).finally(() => setBusy(false));
     }}>
-      <textarea rows={small ? 1 : 2} value={body} placeholder={placeholder} onChange={(e) => setBody(e.target.value)} />
+      <textarea rows={small ? 1 : 2} value={body} placeholder={placeholder} autoFocus={autoFocus}
+                onChange={(e) => setBody(e.target.value)} />
       <button disabled={busy || !body.trim()}>{small ? "Reply" : "Comment"}</button>
     </form>
   );
```

`frontend/src/components/DiffView.tsx`:

```diff
diff --git a/frontend/src/components/DiffView.tsx b/frontend/src/components/DiffView.tsx
index f1ca156..d6ad739 100644
--- a/frontend/src/components/DiffView.tsx
+++ b/frontend/src/components/DiffView.tsx
@@ -1,7 +1,8 @@
 import { Fragment, useState } from "react";
 import type { Comment } from "../api";
+import { lineAnchor, onLine } from "../lib/anchors";
 import { diffRows } from "../lib/diffRows";
-import Comments, { anchorMatches } from "./Comments";
+import Comments from "./Comments";
 
 interface Props {
   reviewId: number;
@@ -24,9 +25,10 @@ export default function DiffView({ reviewId, depot, cl, before, after, comments,
           if (r.kind === "gap") return <tr key={i} className="gap"><td colSpan={4}>⋯ {r.text}</td></tr>;
           const side = r.newNo !== null ? "new" : "old";
           const line = r.newNo ?? r.oldNo;
-          const anchor = { depot, cl, side, line };
+          const anchor = lineAnchor(depot, side, line!, cl);
           const key = `${side}:${line}`;
-          const has = comments.some((c) => c.parent_id === null && anchorMatches(c, "line", anchor));
+          const match = (c: Comment) => onLine(c, depot, side, line!, cl);
+          const has = comments.some((c) => c.parent_id === null && match(c));
           return (
             <Fragment key={i}>
               <tr className={r.kind}>
@@ -37,7 +39,7 @@ export default function DiffView({ reviewId, depot, cl, before, after, comments,
               </tr>
               {(has || openAt === key) && (
                 <tr className="comment-row"><td colSpan={3} /><td>
-                  <Comments reviewId={reviewId} comments={comments} kind="line" anchor={anchor} onChange={onComments} />
+                  <Comments reviewId={reviewId} comments={comments} kind="line" anchor={anchor} match={match} onChange={onComments} />
                 </td></tr>
               )}
             </Fragment>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/anchors.test.ts && npx tsc --noEmit`
Expected: `Tests  1 passed (1)` and no `tsc` output

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  45 passed (45)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/anchors.ts frontend/src/api.ts frontend/src/components/Comments.tsx frontend/src/components/DiffView.tsx frontend/src/lib/anchors.test.ts
git commit -m "feat(ui): depot-path line comment anchors; board API calls"
```

---

### Task 11: Frontend: the review board page

The page itself (spec §2–§4, §8): header (title, risk, CL pills, counts, `✦ What's this change?`, secondary tabs
`Findings`, `Files`, `CLs & Swarm`), flow bar with the flow summary, and a main row `canvas | file viewer | change panel`
where the panels push the canvas and resize from their left edge (full-screen sheets below 1100 px). The canvas draws
bands, edges and nodes through the lens, pans on drag/wheel and moves a node sideways when dragged by it; cards float
beside their node with a tether, drag by header, double-click to re-dock, become bottom sheets on phones. Context code is
fetched on demand through `/source` and cached for the session. The Board is the default route; the M1 Storyboard,
Call flows and Blast radius tabs and Cytoscape are removed. All board CSS is `bd-` prefixed or nested under `.bd` — M1's
global `.graph`, `.side`, `.card` rules otherwise leak in.

Components: `useSources.ts` (changed files from the change set, others via `/source`), `CodeView.tsx` (draws
`codeItems`; click a line to comment), `Resizer.tsx`, `Canvas.tsx`, `CardLayer.tsx` (placement via `placeCards`, sizes via
`ResizeObserver`), `FileViewer.tsx` (stacked sections, reveal scroll + flash), `ChangePanel.tsx`, `FlowBar.tsx`,
`Board.tsx` (reducer, lens, centring animation, keeps the focused point centred when the canvas resizes, per-viewer
prefs, `?node=` focus), `board.css` (from `docs/design/board-prototype.html`), `pages/Review.tsx`.

**Files:**
- Create: `frontend/src/board/useSources.ts`
- Create: `frontend/src/board/CodeView.tsx`
- Create: `frontend/src/board/Resizer.tsx`
- Create: `frontend/src/board/Canvas.tsx`
- Create: `frontend/src/board/CardLayer.tsx`
- Create: `frontend/src/board/FileViewer.tsx`
- Create: `frontend/src/board/ChangePanel.tsx`
- Create: `frontend/src/board/FlowBar.tsx`
- Create: `frontend/src/board/Board.tsx`
- Create: `frontend/src/board/board.css`
- Modify: `frontend/src/pages/Review.tsx`
- Modify: `frontend/src/styles.css`
- Delete: `frontend/src/components/Storyboard.tsx`
- Delete: `frontend/src/components/CallFlows.tsx`
- Delete: `frontend/src/components/BlastRadius.tsx`
- Delete: `frontend/src/lib/graph.ts`
- Delete: `frontend/src/lib/graph.test.ts`
- Delete: `frontend/src/types.d.ts`
- Test: `frontend/e2e/helpers.ts`
- Test: `frontend/e2e/board.spec.ts`
- Modify: `frontend/e2e/smoke.spec.ts`
- Modify: `frontend/e2e/mobile.spec.ts`
- Modify: `frontend/package.json`, `frontend/package-lock.json` (via `npm uninstall`)

**Interfaces:**
- Consumes: everything from Tasks 6–10; `GET /board`, `GET /source` (Task 5).
- Produces: `<Board reviewId board files comments onComments risk focus head />` (`frontend/src/board/Board.tsx`); review
  routes `/r/:id` (board), `/r/:id/findings`, `/r/:id/files`, `/r/:id/cls`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/helpers.ts`:

```ts
import { expect, type Page } from "@playwright/test";

/** Log in as the demo owner, review fixture CLs 101+102 and wait for the board. */
export async function startReview(page: Page) {
  await page.goto("/login");
  await page.getByLabel("P4 user").fill("demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
  await page.goto("/new");
  await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.locator(".bd-node").first()).toBeVisible({ timeout: 60_000 });
}
```

`frontend/e2e/board.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

test("flows, cards, comments, viewer, change panel and layout", async ({ page }) => {
  await startReview(page);
  await expect(page.getByRole("tab")).toHaveCount(3);
  await expect(page.locator(".bd-flowinfo .landing")).toContainText("Side effect lands on uart_errors");

  // select a flow; its summary names where the effect lands
  await page.getByRole("tab", { name: /logger_flush/ }).click();
  await expect(page.locator(".bd-flowinfo .landing")).toContainText("Side effect lands on logger_flush");

  // a step chip toggles that function's card; the card shows the annotation on the call line
  const step = page.locator(".bd-flowinfo .step", { hasText: "logger_flush" });
  const card = page.locator(".bd-card", { hasText: "logger_flush" });
  await step.click();
  await expect(card.locator(".bd-ann.warn")).toContainText("result ignored");
  await step.click();
  await expect(card).toHaveCount(0);

  // comment on a line inside a card
  await step.click();
  await card.locator(".bd-ln", { hasText: "uart_send(lg->uart" }).click();
  await card.getByPlaceholder("Leave a comment…").fill("flush drops -2 silently");
  await card.getByRole("button", { name: "Comment" }).click();
  await expect(card.getByText("flush drops -2 silently")).toBeVisible();

  // ⤢ on a node opens its file in the viewer, at the function; cards collapse to pills
  await page.locator(".bd-node", { hasText: /^main/ }).locator(".bd-go").click();
  const viewer = page.locator(".bd-viewer");
  await expect(viewer.locator('.fsec[data-path="//fixture/app/main.c"]')).toBeVisible();
  await expect(viewer.locator(".bd-ln.focus")).toContainText("int main");
  await expect(card).toHaveClass(/\bmin\b/);

  // stack a second file on top; collapse and expand all
  await page.locator(".bd-flowinfo .step", { hasText: "uart_send" }).locator(".sgo").click();
  await expect(viewer.locator(".fsec").first()).toHaveAttribute("data-path", "//fixture/driver/uart.c");
  await expect(viewer.locator(".fsec")).toHaveCount(2);
  await viewer.getByRole("button", { name: "Collapse all" }).click();
  await expect(viewer.locator(".fsec.collapsed")).toHaveCount(2);
  await viewer.getByRole("button", { name: "Expand all" }).click();
  await expect(viewer.locator(".fsec.collapsed")).toHaveCount(0);
  await viewer.getByRole("button", { name: "Close all" }).click();
  await expect(viewer).toHaveCount(0);
  await expect(card).not.toHaveClass(/\bmin\b/);           // restored exactly

  // the change panel opens beside the board and can be resized from its left edge
  await page.getByRole("button", { name: "✦ What's this change?" }).click();
  const panel = page.locator(".bd-about");
  await expect(panel.getByText("Files in this change")).toBeVisible();
  const before = (await panel.boundingBox())!;
  const grip = (await panel.locator(".bd-resizer").boundingBox())!;
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2);
  await page.mouse.down();
  await page.mouse.move(grip.x - 100, grip.y + grip.height / 2, { steps: 5 });
  await page.mouse.up();
  expect((await panel.boundingBox())!.width).toBeGreaterThan(before.width + 80);
  await panel.locator(".file", { hasText: "regs.c" }).click();      // opening a file keeps the panel open
  await expect(page.locator(".bd-viewer .fsec")).toHaveCount(1);
  await expect(panel).toBeVisible();
  await page.getByRole("button", { name: "Close change summary" }).click();
  await page.locator(".bd-viewer").getByRole("button", { name: "Close all" }).click();
});

test("whole graph: drag a node within its layer, reset; dragging never selects text", async ({ page }) => {
  await startReview(page);
  await page.getByRole("button", { name: "Close uart_send" }).click();   // the card opened on arrival
  await page.getByRole("button", { name: "Whole graph" }).click();
  await expect(page.locator(".bd-flowinfo.whole")).toContainText("Whole graph");
  const node = page.locator(".bd-node", { hasText: /^main/ });
  await page.waitForTimeout(500);                                   // centring animation
  const a = (await node.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 160, a.y + a.height / 2 + 40, { steps: 8 });
  await page.mouse.up();
  const b = (await node.boundingBox())!;
  expect(b.x).toBeGreaterThan(a.x + 60);
  expect(Math.abs(b.y - a.y)).toBeLessThan(4);                       // stays in its layer
  await expect(node).toHaveClass(/\bmoved\b/);
  await page.getByRole("button", { name: "Reset layout" }).click();
  await expect(node).not.toHaveClass(/\bmoved\b/);

  // pan across an open card: nothing gets selected
  await page.getByRole("tab", { name: /uart_errors/ }).click();
  await page.locator(".bd-flowinfo .step", { hasText: "uart_errors" }).click();
  const stage = (await page.locator(".bd-stage").boundingBox())!;
  await page.mouse.move(stage.x + stage.width - 30, stage.y + stage.height - 40);
  await page.mouse.down();
  await page.mouse.move(stage.x + 30, stage.y + 120, { steps: 12 });
  await page.mouse.up();
  expect(await page.evaluate(() => window.getSelection()?.toString() ?? "")).toBe("");
});
```

`frontend/e2e/smoke.spec.ts` (replace the whole file):

```ts
import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

test("owner reviews fixture CLs end to end", async ({ page }) => {
  await startReview(page);
  await expect(page.getByRole("tab")).toHaveCount(3);

  await page.getByRole("link", { name: /Findings/ }).click();
  await expect(page.getByText("uart_send now writes Uart::errors through a local alias")).toBeVisible();

  await page.getByRole("link", { name: /Files/ }).click();
  const row = page.locator("tr.add", { hasText: "return -2;" });
  await row.hover();
  await row.getByTitle("Comment on this line").click();
  await page.getByPlaceholder("Leave a comment…").fill("Does logger_flush handle -2?");
  await page.getByRole("button", { name: "Comment" }).click();
  await expect(page.getByText("Does logger_flush handle -2?")).toBeVisible();

  // the same line comment shows on the board, in the changed function's card
  await page.getByRole("link", { name: "Board" }).click();
  await expect(page.locator(".bd-card", { hasText: "uart_send" }).getByText("Does logger_flush handle -2?")).toBeVisible();
});
```

`frontend/e2e/mobile.spec.ts` (replace the whole file):

```ts
import { devices, expect, test } from "@playwright/test";
import { startReview } from "./helpers";

test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
  deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

test("the board is usable at phone width", async ({ page }) => {
  await startReview(page);
  const { width, height } = page.viewportSize()!;
  const fits = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  await fits();

  // header controls are on screen
  const about = (await page.getByRole("button", { name: "✦ What's this change?" }).boundingBox())!;
  expect(about.x + about.width).toBeLessThanOrEqual(width);

  // a card is a bottom sheet
  await page.locator(".bd-flowinfo .step", { hasText: "uart_errors" }).click();
  const sheet = (await page.locator(".bd-card.sheet").boundingBox())!;
  expect(sheet.width).toBeGreaterThan(width - 24);
  expect(sheet.y + sheet.height).toBeGreaterThan(height - 16);

  // the viewer is a full-screen sheet
  await page.locator(".bd-card.sheet").getByRole("button", { name: "⤢ Full file" }).click();
  const viewer = (await page.locator(".bd-viewer").boundingBox())!;
  expect(Math.round(viewer.width)).toBe(width);
  await page.locator(".bd-viewer").getByRole("button", { name: "Close all" }).click();
  await expect(page.locator(".bd-viewer")).toHaveCount(0);

  // secondary tabs still work and diff line numbers never wrap digit by digit
  await page.getByRole("link", { name: /Files/ }).click();
  const ln = page.locator("tr.add td.ln").nth(1);
  expect((await ln.boundingBox())!.height).toBeLessThan(30);
  await fits();
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test`
Expected: FAIL — `4 failed` — the review page has no `.bd-node` yet (it still shows the M1 storyboard)

- [ ] **Step 3: Implement**

Remove the graph library the old tabs used: `cd frontend && npm uninstall cytoscape cytoscape-elk`.

Delete the M1 tabs this page replaces:

```bash
git rm frontend/src/components/Storyboard.tsx frontend/src/components/CallFlows.tsx frontend/src/components/BlastRadius.tsx frontend/src/lib/graph.ts frontend/src/lib/graph.test.ts frontend/src/types.d.ts
```

`frontend/src/board/useSources.ts`:

```ts
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type FileChange } from "../api";
import type { SourceText } from "./types";

export type SourceState =
  | { status: "loading" }
  | { status: "ok"; file: SourceText }
  | { status: "error"; error: string };

/** Text of any file the board shows: changed files come from the change set; others are fetched on demand
 * (`GET /source`, i.e. p4 print at the workspace's have revision) and kept for the session. */
export function useSources(reviewId: number, files: FileChange[]) {
  const changed = useRef(new Map<string, FileChange>());
  changed.current = new Map(files.map((f) => [f.depot, f]));
  const [fetched, setFetched] = useState<Record<string, SourceState>>({});
  const inflight = useRef(new Set<string>());

  const load = useCallback((path: string) => {
    if (changed.current.has(path) || inflight.current.has(path)) return;
    inflight.current.add(path);
    setFetched((m) => ({ ...m, [path]: { status: "loading" } }));
    api.source(reviewId, path)
      .then((file) => setFetched((m) => ({ ...m, [path]: { status: "ok", file } })))
      .catch((e) => setFetched((m) => ({ ...m, [path]: { status: "error", error: String(e.message ?? e) } })))
      .finally(() => inflight.current.delete(path));
  }, [reviewId]);

  const reload = useCallback((path: string) => {
    setFetched((m) => {
      const { [path]: _, ...rest } = m;
      return rest;
    });
  }, []);

  const get = useCallback((path: string): SourceState | FileChange | undefined =>
    changed.current.get(path) ?? fetched[path], [fetched]);

  return useMemo(() => ({ get, load, reload }), [get, load, reload]);
}

export const isChange = (x: unknown): x is FileChange => !!x && typeof x === "object" && "before" in x && "after" in x;

/** Fetch `path` once it is shown (no-op for changed files and files already loaded). */
export function useEnsureSource(path: string | null, sources: ReturnType<typeof useSources>) {
  const state = path ? sources.get(path) : undefined;
  useEffect(() => {
    if (path && state === undefined) sources.load(path);
  }, [path, state, sources]);
  return state;
}
```

`frontend/src/board/CodeView.tsx`:

```tsx
import { Fragment, memo, useMemo, useState } from "react";
import type { Comment } from "../api";
import Comments from "../components/Comments";
import { lineAnchor, onLine } from "../lib/anchors";
import { codeItems, lineKey, type Line, type Side } from "./codeRows";
import { tokens } from "./highlight";
import type { Annotation } from "./types";

interface Props {
  reviewId: number;
  path: string;
  lines: Line[];
  mode: "unified" | "split";
  anns: Annotation[];
  comments: Comment[];
  onComments: () => void;
  focus?: number | null;
}

const ICON = { warn: "⚠ ", ok: "✓ ", info: "ⓘ " } as const;

function Src({ text }: { text: string }) {
  return <>{tokens(text).map((t, i) => (t.cls ? <span key={i} className={`hl-${t.cls}`}>{t.text}</span> : t.text))}</>;
}

/** Code lines (diff or plain) with inline annotations and line comment threads; click a line to comment. */
function CodeView({ reviewId, path, lines, mode, anns, comments, onComments, focus }: Props) {
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const mine = useMemo(() => anns.filter((a) => a.path === path), [anns, path]);
  const threads = useMemo(() => {
    const keys = new Set(opened);
    for (const c of comments) {
      if (c.parent_id !== null || c.anchor_kind !== "line") continue;
      const side = c.anchor.side as Side, line = c.anchor.line as number;
      if (onLine(c, path, side, line)) keys.add(lineKey(side, line));
    }
    return keys;
  }, [comments, opened, path]);
  const items = useMemo(() => codeItems(lines, mode, mine, threads), [lines, mode, mine, threads]);
  const open = (side: Side, no: number) => setOpened((s) => new Set(s).add(lineKey(side, no)));

  return (
    <div className="bd-code">
      {items.map((it, i) => {
        if (it.kind === "ann")
          return (
            <div key={i} className={`bd-ann ${it.ann.severity}`}>
              <span className="k">{ICON[it.ann.severity]}{it.ann.title}</span>{it.ann.text}
            </div>
          );
        if (it.kind === "thread")
          return (
            <div key={i} className="bd-thread" onPointerDown={(e) => e.stopPropagation()}>
              <Comments reviewId={reviewId} comments={comments} kind="line" anchor={lineAnchor(path, it.side, it.no)}
                        match={(c) => onLine(c, path, it.side, it.no)} onChange={onComments}
                        autoFocus={opened.has(lineKey(it.side, it.no))} />
            </div>
          );
        if (it.kind === "line") {
          const l = it.line;
          return (
            <div key={i} data-n={l.n ?? undefined} onClick={() => open(it.side, it.no)}
                 className={`bd-ln${l.t === "+" ? " a" : l.t === "-" ? " d" : ""}${it.hot ? " hot" : ""}${focus && l.n === focus ? " focus" : ""}`}>
              <span className="no">{l.n ?? l.o}</span><span className="sg">{l.t === "=" ? "" : l.t}</span>
              <span className="src"><Src text={l.text} /><span className="plus">＋ comment</span></span>
            </div>
          );
        }
        const { l, r } = it;
        return (
          <Fragment key={i}>
            <div data-n={r?.n ?? undefined} onClick={() => open(it.side, it.no)}
                 className={`bd-sbs${it.hot ? " hot" : ""}${focus && r?.n === focus ? " focus" : ""}`}>
              {l ? <><span className={`no l${l.t === "-" ? " d" : ""}`}>{l.o}</span><span className={`src l${l.t === "-" ? " d" : ""}`}><Src text={l.text} /></span></>
                 : <><span className="no empty" /><span className="src empty" /></>}
              {r ? <><span className={`no r${r.t === "+" ? " a" : ""}`}>{r.n}</span><span className={`src r${r.t === "+" ? " a" : ""}`}><Src text={r.text} /><span className="plus">＋ comment</span></span></>
                 : <><span className="no empty" /><span className="src empty"><span className="plus">＋ comment</span></span></>}
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}

export default memo(CodeView);
```

`frontend/src/board/Resizer.tsx`:

```tsx
/** Drag handle on a side panel's left edge (spec §2): width = start width + leftward drag, clamped. */
export default function Resizer({ width, min, maxFrac, onWidth, onDone }:
  { width: number; min: number; maxFrac: number; onWidth: (w: number) => void; onDone?: (w: number) => void }) {
  return (
    <div className="bd-resizer" title="Drag to resize" onPointerDown={(e) => {
      e.preventDefault();
      const el = e.currentTarget, startX = e.clientX;
      el.setPointerCapture(e.pointerId);
      document.body.classList.add("bd-resizing");
      let w = width;
      const move = (ev: PointerEvent) => {
        w = Math.round(Math.max(min, Math.min(window.innerWidth * maxFrac, width + (startX - ev.clientX))));
        onWidth(w);
      };
      const up = () => {
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        document.body.classList.remove("bd-resizing");
        onDone?.(w);
      };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
    }} />
  );
}
```

`frontend/src/board/Canvas.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { BAND, type Lens, type Projected, type Viewport } from "./lens";
import { flowSets } from "./layout";
import type { Action, BoardState } from "./reducer";
import type { Board } from "./types";

interface Props {
  board: Board;
  lens: Lens;
  pos: Map<string, Projected>;
  vp: Viewport;
  rows: Map<number, number>;
  state: BoardState;
  dispatch: (a: Action) => void;
  panBy: (dx: number, dy: number) => void;
  onOpenFile: (id: string) => void;
  onInteract: () => void;
}

const KIND = { modified: "Δ modified", added: "Δ added", removed: "Δ removed", signature: "Δ signature" } as const;

/** Layer bands, edges and nodes, all drawn through the lens; pans on drag, moves a node sideways when dragged by it. */
export default function Canvas({ board, lens, pos, vp, rows, state, dispatch, panBy, onOpenFile, onInteract }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const down = useRef<{ x: number; y: number; px: number; py: number; id: number; node: string | null; go: boolean; dragging: boolean } | null>(null);
  const [grab, setGrab] = useState<string | null>(null);   // node being dragged
  const [panning, setPanning] = useState(false);
  const { W } = vp;

  useEffect(() => {                                          // wheel / trackpad pans (non-passive so the page doesn't scroll)
    const el = root.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      panBy(-(e.deltaX + (e.shiftKey ? e.deltaY : 0)), e.shiftKey ? 0 : -e.deltaY);
      onInteract();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [panBy, onInteract]);

  const graph = state.mode === "graph";
  const flow = board.flows[state.flow];
  const { onPath, pairs } = flowSets(flow, graph);
  const landings = new Set(graph ? board.flows.map((f) => f.lands) : flow ? [flow.lands] : []);
  const front = state.z[state.z.length - 1];
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const badge = new Map<string, string>();
  for (const a of board.impacts) if (a.landing && !badge.has(a.node)) badge.set(a.node, a.text);

  // bands: sampled every 16 px so they follow the vertical squeeze
  const xs: number[] = [];
  for (let x = 0; x <= W + 16; x += 16) xs.push(Math.min(x, W));
  const line = (wy: number, rev = false) => (rev ? [...xs].reverse() : xs)
    .map((x, i) => `${i ? "L" : "M"}${x} ${lens.bandY(x, wy).toFixed(1)}`).join(" ");
  const levels = [...rows.entries()].sort((a, b) => a[1] - b[1]);
  const names = new Map(board.layers.map((l) => [l.level, l.name]));

  return (
    <div ref={root} className={`bd-canvas${panning ? " drag" : ""}`}
      onPointerDown={(e) => {
        const t = e.target as HTMLElement, n = t.closest<HTMLElement>(".bd-node");
        down.current = { x: e.clientX, y: e.clientY, px: state.view.panX, py: state.view.panY, id: e.pointerId,
                         node: n?.dataset.id ?? null, go: !!t.closest(".bd-go"), dragging: false };
        e.preventDefault();                                  // no text selection starting on the board
      }}
      onPointerMove={(e) => {
        const d = down.current;
        if (!d) return;
        if (!d.dragging) {
          if (Math.hypot(e.clientX - d.x, e.clientY - d.y) <= 6) return;
          d.dragging = true;
          root.current?.setPointerCapture(d.id);             // only once dragging: early capture swallows clicks
          document.body.classList.add("bd-dragging");
          window.getSelection()?.removeAllRanges();
          if (d.node) setGrab(d.node); else setPanning(true);
          onInteract();
        }
        if (d.node) {
          const r = root.current!.getBoundingClientRect();
          dispatch({ t: "node.move", id: d.node, x: Math.round(lens.unprojectX(e.clientX - r.left)) });
        } else dispatch({ t: "pan", panX: d.px + (e.clientX - d.x), panY: d.py + (e.clientY - d.y) });
      }}
      onPointerUp={() => {
        const d = down.current;
        down.current = null;
        document.body.classList.remove("bd-dragging");
        setGrab(null);
        setPanning(false);
        if (!d || d.dragging || !d.node) return;
        const n = byId.get(d.node);
        if (!n?.path || !n.range) return;
        onInteract();
        if (d.go) onOpenFile(d.node); else dispatch({ t: "card.open", id: d.node });
      }}
      onPointerCancel={() => {
        down.current = null;
        document.body.classList.remove("bd-dragging");
        setGrab(null);
        setPanning(false);
      }}>
      <svg className="bd-bands">
        {levels.map(([lv, i]) => (
          <g key={lv}>
            <path className={`fill${i % 2 ? " alt" : ""}`} d={`${line(i * BAND)} ${line((i + 1) * BAND, true).replace(/^M/, "L")} Z`} />
            <path className="rule" d={line(i * BAND)} />
          </g>
        ))}
        <path className="rule" d={line(levels.length * BAND)} />
      </svg>
      {levels.map(([lv, i]) => {
        const y = lens.bandY(12, i * BAND) + 6, k = Math.max(0.7, (lens.bandY(12, 1) - lens.bandY(12, 0)));
        return <div key={lv} className="bd-blabel" style={{ top: y, transform: `scale(${k})` }}>
          {lv >= 0 ? `L${lv} · ${names.get(lv) ?? ""}` : "other"}
        </div>;
      })}
      <svg className="bd-edges">
        {board.edges.map((e, i) => {
          const p1 = pos.get(e.src), p2 = pos.get(e.dst);
          if (!p1 || !p2) return null;
          const data = e.kind === "writes" || e.kind === "reads";
          const fx = e.kind === "reads" && landings.has(e.src) && (graph || onPath.has(e.dst));
          const inFlow = pairs.has(`${e.src}>${e.dst}`) || pairs.has(`${e.dst}>${e.src}`);
          const my = (p1.y + p2.y) / 2;
          return <path key={i} d={`M${p1.x} ${p1.y} C ${p1.x} ${my}, ${p2.x} ${my}, ${p2.x} ${p2.y}`}
            className={`bd-edge${fx ? " fx" : data ? " data" : ""}${inFlow ? " flow" : ""}${!inFlow && !data && !graph ? " dim" : ""}`} />;
        })}
      </svg>
      {board.nodes.map((n) => {
        const p = pos.get(n.id);
        if (!p) return null;
        const card = state.cards[n.id], on = onPath.has(n.id);
        const cls = ["bd-node", n.change ? "chg" : "", n.kind === "field" ? "field" : "", on ? "onflow" : "",
          !graph && !on && !n.change && !card ? "dim" : "", state.moved[n.id] !== undefined ? "moved" : "",
          card ? "has-card" : "", n.id === front ? "front" : "", grab === n.id ? "grab" : ""].filter(Boolean).join(" ");
        const fx = badge.get(n.id);
        return (
          <div key={n.id} data-id={n.id} className={cls} title={n.label}
               style={{ left: p.x, top: p.y, transform: `translate(-50%, -50%) scale(${p.s})`, zIndex: Math.round(p.s * 20) }}>
            {n.change && <span className="kind">{KIND[n.change.kind]}</span>}
            <span className="lbl">{n.label}</span>
            {n.change && <span className="stat"><b className="p">+{n.change.add}</b><b className="m">−{n.change.rem}</b></span>}
            {!n.change && n.warn > 0 && <span className="warn-dot">{n.warn}</span>}
            {n.path && n.range && <button className="bd-go" title="Open full file" aria-label={`Open ${n.label} in the file viewer`}>⤢</button>}
            {fx && landings.has(n.id) && <div className="fxbadge">⚠ {fx}</div>}
          </div>
        );
      })}
    </div>
  );
}
```

`frontend/src/board/CardLayer.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Comment } from "../api";
import CodeView from "./CodeView";
import { lineDiff, plainLines, sliceRange } from "./codeRows";
import { placeCards } from "./layout";
import type { Projected, Viewport } from "./lens";
import type { Action, BoardState } from "./reducer";
import type { Board, BoardNode } from "./types";
import { isChange, useEnsureSource, type useSources } from "./useSources";

type Sources = ReturnType<typeof useSources>;
interface Props {
  reviewId: number;
  board: Board;
  pos: Map<string, Projected>;
  vp: Viewport;
  state: BoardState;
  dispatch: (a: Action) => void;
  sources: Sources;
  comments: Comment[];
  onComments: () => void;
  onOpenFile: (id: string) => void;
  narrow: boolean;
}

/** Floating code cards: one per open node, placed next to it through the lens, tethered to it. */
export default function CardLayer(p: Props) {
  const { board, pos, vp, state, narrow } = p;
  const els = useRef(new Map<string, HTMLDivElement>());
  const ro = useRef<ResizeObserver | null>(null);
  const [sizes, setSizes] = useState<Record<string, { w: number; h: number }>>({});
  useEffect(() => () => ro.current?.disconnect(), []);
  const register = useCallback((id: string, el: HTMLDivElement | null) => {
    ro.current ??= new ResizeObserver((entries) => setSizes((prev) => {
      let next = prev;
      for (const e of entries) {
        const t = e.target as HTMLDivElement, key = t.dataset.id!, w = t.offsetWidth, h = t.offsetHeight;
        if (prev[key]?.w !== w || prev[key]?.h !== h) next = { ...next, [key]: { w, h } };
      }
      return next;
    }));
    const old = els.current.get(id);
    if (old && old !== el) ro.current.unobserve(old);
    if (el) { els.current.set(id, el); ro.current.observe(el); } else els.current.delete(id);
  }, []);

  const nodes = useMemo(() => new Map(board.nodes.map((n) => [n.id, n])), [board]);
  const ids = state.z.filter((id) => state.cards[id] && pos.get(id) && nodes.get(id));
  const rects = placeCards(ids.map((id) => {
    const c = state.cards[id];
    return { id, at: pos.get(id)!, w: sizes[id]?.w ?? (c.collapsed ? 140 : 460), h: sizes[id]?.h ?? (c.collapsed ? 34 : 320),
             collapsed: c.collapsed, offset: c.offset };
  }), vp.W, vp.H);
  const front = state.z[state.z.length - 1];

  return (
    <>
      <svg className="bd-tethers">
        {ids.map((id) => {
          const r = rects.get(id)!, at = pos.get(id)!;
          if (narrow && !state.cards[id].collapsed) return null;
          const tx = r.x + (r.x > at.x ? 0 : r.w), ty = Math.max(r.y + 14, Math.min(at.y, r.y + r.h - 14));
          return <path key={id} className={id === front ? "front" : ""} d={`M${at.x} ${at.y} L ${tx} ${ty}`} />;
        })}
      </svg>
      {ids.map((id, i) => (
        <Card key={id} {...p} node={nodes.get(id)!} rect={rects.get(id)!} at={pos.get(id)!} z={50 + i}
              front={id === front} register={register} />
      ))}
    </>
  );
}

interface CardProps extends Props {
  node: BoardNode;
  rect: { x: number; y: number; k: number };
  at: Projected;
  z: number;
  front: boolean;
  register: (id: string, el: HTMLDivElement | null) => void;
}

function Card({ node, rect, at, z, front, register, state, dispatch, narrow, onOpenFile, ...rest }: CardProps) {
  const id = node.id, collapsed = state.cards[id].collapsed;
  const drag = useRef<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  const sheet = narrow && !collapsed;
  const changed = !!node.change;
  return (
    <div ref={(el) => register(id, el)} data-id={id}
         className={`bd-card${changed ? "" : " ctx"}${collapsed ? " min" : ""}${front ? " front" : ""}${sheet ? " sheet" : ""}${dragging ? " dragged" : ""}`}
         style={sheet ? { zIndex: z } : { left: rect.x, top: rect.y, transform: `scale(${rect.k})`, zIndex: z }}
         onPointerDown={(e) => { e.stopPropagation(); dispatch({ t: "card.front", id }); }}
         onClick={() => { if (collapsed) dispatch({ t: "card.expand", id }); }}>
      <div className="hd"
           onPointerDown={(e) => {
             if ((e.target as HTMLElement).closest("button") || collapsed || narrow) return;
             drag.current = { x: e.clientX, y: e.clientY, left: rect.x, top: rect.y, moved: false };
             e.currentTarget.setPointerCapture(e.pointerId);
           }}
           onPointerMove={(e) => {
             const d = drag.current;
             if (!d) return;
             const dx = e.clientX - d.x, dy = e.clientY - d.y;
             if (!d.moved && Math.hypot(dx, dy) < 4) return;
             if (!d.moved) setDragging(true);
             d.moved = true;
             dispatch({ t: "card.move", id, offset: { x: d.left + dx - at.x, y: d.top + dy - at.y } });
           }}
           onPointerUp={() => { drag.current = null; setDragging(false); }}
           onDoubleClick={(e) => { if (!(e.target as HTMLElement).closest("button")) dispatch({ t: "card.unpin", id }); }}>
        <b>{node.label}</b>
        <span className="file">{node.path?.split("/").slice(-2).join("/")}</span>
        <span className={`bd-badge ${changed ? "chg" : "ctx"}`}>{changed ? "Δ changed" : node.kind === "field" ? "field" : "context"}</span>
        <span className="sp" />
        <button className="bd-ibtn restore" title="Expand card" onClick={(e) => { e.stopPropagation(); dispatch({ t: "card.expand", id }); }}>⤢</button>
        <button className="bd-ibtn expand" title="Open full file" onClick={(e) => { e.stopPropagation(); onOpenFile(id); }}>⤢ Full file</button>
        <button className="bd-ibtn x" title="Close" aria-label={`Close ${node.label}`}
                onClick={(e) => { e.stopPropagation(); dispatch({ t: "card.close", id }); }}>✕</button>
      </div>
      {!collapsed && <CardBody node={node} {...rest} />}
    </div>
  );
}

type BodyProps = Pick<Props, "reviewId" | "board" | "sources" | "comments" | "onComments"> & { node: BoardNode };

function CardBody({ node, reviewId, board, sources, comments, onComments }: BodyProps) {
  const src = useEnsureSource(node.path, sources);
  const [lo, hi] = node.range ?? [0, 0];
  const pad = node.kind === "field" ? 4 : 0;
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
    return e ? `${e.kind === "call" || e.kind === "virtual" ? "calls" : e.kind} ${changed.get(e.dst)} (Δ)` : "context";
  }, [board, node.id]);
  return (
    <>
      {node.change ? (
        effects.length > 0 && <div className="effects">{effects.map((a, i) => <div key={i}><span className="ico">⚠</span>{a.text}</div>)}</div>
      ) : (
        <div className="fetched">⤓ fetched on demand · <b>p4 print {node.path}{src && "status" in src && src.status === "ok" && src.file.rev.startsWith("#") ? src.file.rev : ""}</b> · {touches}</div>
      )}
      {lines ? (
        <CodeView reviewId={reviewId} path={node.path!} lines={lines} mode="unified" anns={board.impacts}
                  comments={comments} onComments={onComments} />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => sources.reload(node.path!)}>Retry</button></div>
      ) : (
        <div className="bd-note">Fetching {node.path}…</div>
      )}
    </>
  );
}
```

`frontend/src/board/FileViewer.tsx`:

```tsx
import { useEffect, useMemo, useRef } from "react";
import type { Comment } from "../api";
import CodeView from "./CodeView";
import { lineDiff, plainLines } from "./codeRows";
import type { Action, ViewerState } from "./reducer";
import Resizer from "./Resizer";
import type { Annotation } from "./types";
import { isChange, useEnsureSource, type useSources } from "./useSources";

type Sources = ReturnType<typeof useSources>;
interface Props {
  reviewId: number;
  viewer: ViewerState;
  dispatch: (a: Action) => void;
  sources: Sources;
  anns: Annotation[];
  comments: Comment[];
  onComments: () => void;
  width: number;
  onWidth: (w: number) => void;
  onWidthDone: (w: number) => void;
}

/** Stacked, collapsible full files (spec §3.5); newest on top, diff controls only for changed files. */
export default function FileViewer(p: Props) {
  const { viewer, dispatch } = p;
  const box = useRef<HTMLDivElement>(null);
  const reveal = viewer.reveal;
  useEffect(() => {                                     // scroll to the file / line just opened, flash its header
    if (!reveal || !box.current) return;
    const id = window.requestAnimationFrame(() => {
      const sec = box.current?.querySelector<HTMLElement>(`[data-path="${CSS.escape(reveal.path)}"]`);
      if (!sec) return;
      sec.classList.remove("flash");
      void sec.offsetWidth;
      sec.classList.add("flash");
      const target = (reveal.line && sec.querySelector<HTMLElement>(`[data-n="${reveal.line}"]`))
        || sec.querySelector<HTMLElement>(".bd-ln.a, .bd-ln.d, .bd-sbs .a, .bd-ann.warn") || sec;
      box.current!.scrollTop = target.getBoundingClientRect().top - box.current!.getBoundingClientRect().top + box.current!.scrollTop - 60;
    });
    return () => window.cancelAnimationFrame(id);
  }, [reveal]);
  return (
    <aside className="bd-viewer" style={{ ["--w" as string]: `${p.width}px` }}>
      <Resizer width={p.width} min={360} maxFrac={0.75} onWidth={p.onWidth} onDone={p.onWidthDone} />
      <div className="top">
        <b>Files</b><span className="muted">{viewer.files.length} open</span><span className="sp" />
        <span className="bd-seg">
          <button className={`bd-ibtn${viewer.mode === "unified" ? " on" : ""}`} onClick={() => dispatch({ t: "viewer.mode", mode: "unified" })}>Stacked</button>
          <button className={`bd-ibtn${viewer.mode === "split" ? " on" : ""}`} onClick={() => dispatch({ t: "viewer.mode", mode: "split" })}>Side by side</button>
        </span>
        <button className="bd-ibtn" onClick={() => dispatch({ t: "viewer.expandAll" })}>Expand all</button>
        <button className="bd-ibtn" onClick={() => dispatch({ t: "viewer.collapseAll" })}>Collapse all</button>
        <button className="bd-ibtn" onClick={() => dispatch({ t: "viewer.closeAll" })}>Close all</button>
      </div>
      <div className="files" ref={box}>
        {viewer.files.map((path) => (
          <FileSection key={path} {...p} path={path} collapsed={viewer.collapsed.includes(path)}
                       focus={reveal?.path === path ? reveal.line : null} />
        ))}
      </div>
    </aside>
  );
}

function FileSection({ path, collapsed, focus, viewer, dispatch, sources, reviewId, anns, comments, onComments }:
  Props & { path: string; collapsed: boolean; focus: number | null }) {
  const src = useEnsureSource(path, sources);
  const change = isChange(src) ? src : null;
  const lines = useMemo(() => {
    if (change) return lineDiff(change.before, change.after);
    if (src && "status" in src && src.status === "ok") return plainLines(src.file.text);
    return null;
  }, [src, change]);
  const counts = useMemo(() => lines && change ? [lines.filter((l) => l.t === "+").length, lines.filter((l) => l.t === "-").length] : null,
                         [lines, change]);
  const cls = change ? [...new Set(change.per_cl.map((c) => c.cl))] : [];
  return (
    <section className={`fsec${collapsed ? " collapsed" : ""}`} data-path={path}>
      <div className="hd" onClick={() => dispatch({ t: "viewer.toggle", path })}>
        <span className="chev">{collapsed ? "▸" : "▾"}</span><b>{path}</b>
        <span className="file">{change ? `CL ${cls.join(", ")}` : src && "status" in src && src.status === "ok"
          ? `unchanged · p4 print ${src.file.depot}${src.file.rev.startsWith("#") ? src.file.rev : ""}` : ""}</span>
        {counts && <span className="cnt"><span className="p">+{counts[0]}</span><span className="m">−{counts[1]}</span></span>}
        <span className="sp" />
        <button className="bd-ibtn x" title="Close file" aria-label={`Close ${path}`}
                onClick={(e) => { e.stopPropagation(); dispatch({ t: "viewer.close", path }); }}>✕</button>
      </div>
      {!collapsed && (lines ? (
        <CodeView reviewId={reviewId} path={path} lines={lines} mode={change && viewer.mode === "split" ? "split" : "unified"}
                  anns={anns} comments={comments} onComments={onComments} focus={focus} />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => sources.reload(path)}>Retry</button></div>
      ) : <div className="bd-note">Fetching {path}…</div>)}
    </section>
  );
}
```

`frontend/src/board/ChangePanel.tsx`:

```tsx
import { useState } from "react";
import type { Action } from "./reducer";
import Resizer from "./Resizer";
import type { About } from "./types";

interface Props {
  about: About;
  risk: string | null;
  openFiles: string[];
  dispatch: (a: Action) => void;
  wide: boolean;
  width: number;
  onWidth: (w: number) => void;
  onWidthDone: (w: number) => void;
}

/** "What's this change?" (spec §3.6): files tree first, then intent, why it's risky, changelists. Pushes the board. */
export default function ChangePanel({ about, risk, openFiles, dispatch, wide, width, onWidth, onWidthDone }: Props) {
  const [shut, setShut] = useState<Set<string>>(new Set());
  const nFiles = about.tree.reduce((n, d) => n + d.files.length, 0);
  return (
    <aside className="bd-about" style={{ ["--w" as string]: `${width}px` }}>
      <Resizer width={width} min={280} maxFrac={0.6} onWidth={onWidth} onDone={onWidthDone} />
      <div className="top">
        <button className="bd-ibtn close" title="Close" aria-label="Close change summary" onClick={() => dispatch({ t: "about.toggle", open: false })}>✕</button>
        {risk && <span className={`bd-pill ${risk}`}>{risk.toUpperCase()} RISK</span>}
        <h2>What this change is trying to do</h2>
        <p>{about.cls.map((c) => `CL ${c.cl}`).join(" · ")} · {nFiles} files · {about.intent_source === "llm"
          ? "summarised from the CL descriptions, the diff and the analysis" : "from the CL descriptions and the analysis"}</p>
      </div>
      <div className="body">
        <h3>Files in this change</h3>
        <div className="tree">
          {about.tree.map((d) => (
            <div key={d.dir}>
              <div className="dir" onClick={() => setShut((s) => { const n = new Set(s); if (n.has(d.dir)) n.delete(d.dir); else n.add(d.dir); return n; })}>
                <span className="caret">{shut.has(d.dir) ? "▸" : "▾"}</span>📁 {d.dir}/
              </div>
              {!shut.has(d.dir) && d.files.map((f) => (
                <div key={f.path} className={`file${openFiles.includes(f.path) ? " on" : ""}`}
                     onClick={() => dispatch({ t: "viewer.open", path: f.path, wide })}>
                  📄 {f.name}<span className="act">{f.action}</span>
                  {f.cls.length > 0 && <span className="clb">CL {f.cls.join(", ")}</span>}
                  <span className="cnt"><span className="p">+{f.add}</span><span className="m">−{f.rem}</span></span>
                </div>
              ))}
            </div>
          ))}
        </div>
        <h3>Intent</h3>
        <div className="intent">{about.intent}</div>
        {about.why.length > 0 && <>
          <h3>Why it's {risk ?? "flagged"} risk</h3>
          <ul className="why">{about.why.map((w) => <li key={w.finding}><span className={`sev ${w.severity}`}>{w.severity.toUpperCase()}</span>{w.text}</li>)}</ul>
        </>}
        <h3>Changelists</h3>
        {about.cls.map((c) => (
          <div key={c.cl} className="cl"><span className="n">CL {c.cl}</span> <span className="m">· {c.user} · {c.files} files</span>
            <div className="desc">{c.description}</div></div>
        ))}
      </div>
    </aside>
  );
}
```

`frontend/src/board/FlowBar.tsx`:

```tsx
import { useState } from "react";
import type { BoardState } from "./reducer";
import type { Board } from "./types";

interface Props {
  board: Board;
  state: BoardState;
  layerOf: (id: string) => string;
  onFlow: (i: number) => void;
  onStep: (id: string) => void;
  onStepOpen: (id: string) => void;
}

/** Numbered flow chips and the selected flow's summary (spec §2), or graph totals in Whole graph mode. */
export default function FlowBar({ board, state, layerOf, onFlow, onStep, onStepOpen }: Props) {
  const [details, setDetails] = useState(() => typeof window === "undefined" || window.innerWidth > 640);
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const graph = state.mode === "graph" || !board.flows.length;
  const flow = board.flows[state.flow];
  return (
    <div className="bd-flowbar">
      {board.flows.length > 0 && (
        <div className="bd-flows" role="tablist" aria-label="Call flows">
          {board.flows.map((f, i) => (
            <button key={f.id} role="tab" aria-selected={!graph && i === state.flow}
                    className={`bd-chip${!graph && i === state.flow ? " on" : ""}`} onClick={() => onFlow(i)}>
              <span className="num">{i + 1}</span><span className="path">{f.text}</span>
              <span className={`bd-tag ${f.tag}`}>{f.tag}</span>
            </button>
          ))}
        </div>
      )}
      {graph ? (
        <div className="bd-flowinfo whole">
          <div className="what">
            <b>Whole graph</b> — {board.nodes.length} functions and fields across {board.layers.length} layers;{" "}
            {board.nodes.filter((n) => n.change).length} changed, {new Set(board.flows.map((f) => f.lands)).size} where side effects land.
            {board.hidden_nodes > 0 && <> +{board.hidden_nodes} more functions not shown.</>}
            {" "}Drag a function sideways to rearrange its layer; your layout is kept for this review.
            {board.flows.length > 0 ? " Pick a flow above to trace one path." : " No flows: the analysis found no side effect to trace."}
          </div>
        </div>
      ) : flow && (
        <div className={`bd-flowinfo${details ? "" : " brief"}`}>
          <div className="fnum">{state.flow + 1}</div>
          <div>
            <div className="what">{flow.what}</div>
            <div className="steps">
              {flow.path.map((id, i) => {
                const n = byId.get(id);
                if (!n) return null;
                const kind = n.change ? "chg" : n.kind === "field" ? "field" : id === flow.lands || id === flow.fx_at ? "fx" : "";
                const open = state.cards[id] && !state.cards[id].collapsed;
                const code = !!(n.path && n.range);
                return (
                  <span key={id} className="bd-stepwrap">
                    {i > 0 && <span className="arrow">→</span>}
                    <span className={`step ${kind}${open ? " open" : ""}`} title={code ? "Show / hide the code" : undefined}
                          onClick={() => code && onStep(id)}>
                      {n.label}
                      {code && <span className="sgo" title="Open in full view" role="button" aria-label={`Open ${n.label} in full view`}
                                     onClick={(e) => { e.stopPropagation(); onStepOpen(id); }}>⤢</span>}
                    </span>
                  </span>
                );
              })}
              <span className="arrow count">· {flow.path.length} steps · {new Set(flow.path.map((id) => byId.get(id)?.layer)).size} layers</span>
              <button className="bd-more" onClick={() => setDetails(!details)}>{details ? "Less" : "Details"}</button>
            </div>
          </div>
          <div className="landing">
            <span className="k">⚠ Side effect lands on {byId.get(flow.lands)?.label} ({layerOf(flow.lands)})</span>
            {flow.effect}
            <div className="chk">{flow.check}</div>
          </div>
        </div>
      )}
    </div>
  );
}
```

`frontend/src/board/Board.tsx`:

```tsx
import { type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import type { Comment, FileChange } from "../api";
import "./board.css";
import CardLayer from "./CardLayer";
import Canvas from "./Canvas";
import ChangePanel from "./ChangePanel";
import FileViewer from "./FileViewer";
import FlowBar from "./FlowBar";
import { centrePan, layerRows, worldNodes } from "./layout";
import { type LensStrength, makeLens, type Viewport } from "./lens";
import { keys, load, save } from "./prefs";
import { type Action, initialState, reduce } from "./reducer";
import type { Board as BoardModel } from "./types";
import { useSources } from "./useSources";

interface Props {
  reviewId: number;
  board: BoardModel;
  files: FileChange[];
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  /** Node to show (e.g. a finding's cite): its card is opened and the canvas centred on it. */
  focus?: string | null;
  /** Renders the review header; receives the "What's this change?" button to place in it. */
  head: (aboutButton: ReactNode) => ReactNode;
}

const wideScreen = () => window.innerWidth > 1100;

/** The review board (spec §2–§4): flow bar, lensed canvas with cards, file viewer and change panel. */
export default function Board({ reviewId, board, files, comments, onComments, risk, focus, head }: Props) {
  const [state, dispatch] = useReducer(reduce, undefined, () => {
    const s = initialState(load<LensStrength>(keys.lens, 2), load<Record<string, number>>(keys.moved(reviewId), {}));
    return board.flows.length ? s : { ...s, mode: "graph" as const };
  });
  const stateRef = useRef(state);
  stateRef.current = state;
  const sources = useSources(reviewId, files);
  const [vp, setVp] = useState<Viewport>({ W: 0, H: 0 });
  const [viewerW, setViewerW] = useState(() => load(keys.viewerW, 0));
  const [aboutW, setAboutW] = useState(() => load(keys.aboutW, 360));
  const [hint, setHint] = useState(true);
  const stage = useRef<HTMLDivElement>(null);
  const anim = useRef(0);

  useEffect(() => save(keys.moved(reviewId), state.moved), [reviewId, state.moved]);
  useEffect(() => save(keys.lens, state.view.lens), [state.view.lens]);
  useEffect(() => { const t = window.setTimeout(() => setHint(false), 7000); return () => window.clearTimeout(t); }, []);
  const interact = useCallback(() => setHint(false), []);

  const rows = useMemo(() => layerRows(board), [board]);
  const world = useMemo(() => worldNodes(board, state.moved), [board, state.moved]);
  const lens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
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

  // canvas size: keep the focused world point centred when panels open, close or resize
  useLayoutEffect(() => {
    const el = stage.current;
    if (!el) return;
    let first = true;
    const ro = new ResizeObserver(() => {
      const W = el.clientWidth, H = el.clientHeight, prev = vpRef.current;
      if (prev.W && (W !== prev.W || H !== prev.H)) panBy((W - prev.W) / 2, (H - prev.H) / 2);
      vpRef.current = { W, H };
      setVp({ W, H });
      if (first && W) {
        first = false;
        const s = stateRef.current, f = board.flows[s.flow];
        const ids = s.mode === "flows" && f ? f.path : board.nodes.map((n) => n.id);
        const t = centrePan(ids, worldRef.current, W, H);
        if (t) dispatch({ t: "pan", ...t });
        const firstChanged = (f?.path ?? []).find((id) => board.nodes.find((n) => n.id === id)?.change)
          ?? board.nodes.find((n) => n.change && n.path && n.range)?.id;
        if (firstChanged && window.innerWidth > 640) dispatch({ t: "card.open", id: firstChanged });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [board, panBy]);

  const act = useCallback((a: Action) => { setHint(false); dispatch(a); }, []);
  const nodes = useMemo(() => new Map(board.nodes.map((n) => [n.id, n])), [board]);
  const openFile = useCallback((id: string) => {
    const n = nodes.get(id);
    if (n?.path) act({ t: "viewer.open", path: n.path, line: n.range?.[0] ?? null, wide: wideScreen() });
  }, [nodes, act]);
  useEffect(() => {
    if (!focus || !vp.W || !nodes.get(focus)?.path) return;
    act({ t: "card.open", id: focus });
    panTo([focus]);
  }, [focus, vp.W, nodes, act, panTo]);
  const selectFlow = useCallback((i: number) => { act({ t: "flow", i }); panTo(board.flows[i].path); }, [act, panTo, board]);
  const setMode = (mode: "flows" | "graph") => {
    act({ t: "mode", mode });
    panTo(mode === "graph" ? board.nodes.map((n) => n.id) : board.flows[state.flow]?.path ?? []);
  };
  const layerOf = useCallback((id: string) => {
    const lv = nodes.get(id)?.layer ?? -1;
    return board.layers.find((l) => l.level === lv)?.name ?? "unlayered";
  }, [nodes, board]);

  const narrow = typeof window !== "undefined" && window.innerWidth <= 640;
  const viewerOpen = state.viewer.files.length > 0;
  const cardCount = Object.keys(state.cards).length;
  return (
    <div className="bd">
      {head(<button className="bd-about-btn" onClick={() => act({ t: "about.toggle" })}>✦ What's this change?</button>)}
      <FlowBar board={board} state={state} layerOf={layerOf} onFlow={selectFlow}
               onStep={(id) => act({ t: "card.toggle", id })} onStepOpen={openFile} />
      <div className={`bd-main${state.about ? " with-about" : ""}`}>
        <div className="bd-stage" ref={stage}>
          {vp.W > 0 && <>
            <Canvas board={board} lens={lens} pos={pos} vp={vp} rows={rows} state={state} dispatch={act}
                    panBy={panBy} onOpenFile={openFile} onInteract={interact} />
            <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
                       comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />
          </>}
          <div className="bd-tools">
            <div className="bd-toolbar">
              <span className="bd-seg">
                <button className={`bd-ibtn${state.mode === "flows" ? " on" : ""}`} disabled={!board.flows.length}
                        onClick={() => setMode("flows")}>Flows</button>
                <button className={`bd-ibtn${state.mode === "graph" ? " on" : ""}`} onClick={() => setMode("graph")}>Whole graph</button>
              </span>
              {Object.keys(state.moved).length > 0 && <button className="bd-ibtn float" onClick={() => act({ t: "layout.reset" })}>Reset layout</button>}
              <span className="lbl">Lens</span>
              <span className="bd-seg">
                {([0, 2, 4] as const).map((m) => (
                  <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} onClick={() => act({ t: "lens", lens: m })}>
                    {m ? `${m}×` : "Off"}
                  </button>
                ))}
              </span>
              {cardCount >= 2 && <button className="bd-ibtn float" onClick={() => act({ t: "card.closeAll" })}>Close all cards</button>}
            </div>
            <div className="bd-legend">
              <span className="sw chg" />changed<span className="sw flow" />selected flow<span className="sw field" />field<span className="sw fx" />side effect
            </div>
          </div>
          {hint && <div className="bd-hint">Drag in any direction · tap a function for its card · drag a card by its header · ⤢ opens the full file</div>}
        </div>
        {viewerOpen && (
          <FileViewer reviewId={reviewId} viewer={state.viewer} dispatch={act} sources={sources} anns={board.impacts}
                      comments={comments} onComments={onComments}
                      width={viewerW || Math.min(window.innerWidth * 0.58, 980)} onWidth={setViewerW}
                      onWidthDone={(w) => save(keys.viewerW, w)} />
        )}
        {state.about && (
          <ChangePanel about={board.about} risk={risk} openFiles={state.viewer.files} dispatch={act} wide={wideScreen()}
                       width={aboutW} onWidth={setAboutW} onWidthDone={(w) => save(keys.aboutW, w)} />
        )}
      </div>
    </div>
  );
}
```

`frontend/src/board/board.css`:

```css
/* Review board (design reference: docs/design/board-prototype.html). Every class is bd-prefixed or nested under .bd
   so the M1 stylesheet (.card, .badge, .thread, …) never leaks in or out. The board keeps its light palette. */
.bd {
  --bd-bg: #f6f7fb; --bd-ink: #151a2d; --bd-muted: #6a7089; --bd-line: #e2e5ef; --bd-card: #ffffff;
  --flow: #6d4aff; --flow-glow: rgba(109, 74, 255, .28);
  --chg: #ffb020; --chg-deep: #c26a00; --fx: #ff4d6d; --fx-bg: #ffe4ea; --field: #00a6a6; --field-bg: #dcf7f5;
  --add: #e6f9ee; --add-ink: #1a9a4f; --del: #ffecef; --del-ink: #d63a5a;
  --warn: #ff4d6d; --warn-bg: #fff0f3; --info: #3b82f6; --info-bg: #eef5ff; --ok: #16a34a; --ok-bg: #ecfbf1;
  --bd-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --bd-sans: Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color-scheme: light; display: flex; flex-direction: column; height: 100%; min-height: 0;
  background: var(--bd-bg); color: var(--bd-ink); font: 14px/1.45 var(--bd-sans);
}
.bd button { font: inherit; color: inherit; }
body.bd-dragging, body.bd-dragging * { user-select: none !important; -webkit-user-select: none !important; }
body.bd-resizing, body.bd-resizing * { cursor: col-resize !important; user-select: none !important; }

/* header (rendered by the review page) */
.bd-head { display: flex; align-items: center; gap: 10px; padding: 10px 18px; background: linear-gradient(90deg, #151a2d, #2a2466);
  color: #fff; flex-wrap: wrap; }
.bd-head h1 { font-size: 16px; margin: 0; font-weight: 700; }
.bd-head a { color: #dfe0ff; }
.bd-head nav { display: flex; gap: 4px; flex-wrap: wrap; }
.bd-head nav a { font-size: 12.5px; padding: 3px 10px; border-radius: 99px; text-decoration: none; color: #dfe0ff; white-space: nowrap; }
.bd-head nav a.on, .bd-head nav a:hover { background: rgba(255,255,255,.14); color: #fff; }
.bd-head .rerun { color: #dfe0ff; }
.bd-pill { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 99px; letter-spacing: .03em; white-space: nowrap; }
.bd-pill.high { background: var(--fx); color: #fff; } .bd-pill.medium { background: #ffcf66; color: #5a3a00; }
.bd-pill.low { background: #b9f0cc; color: #13692f; } .bd-pill.ghost { background: rgba(255,255,255,.14); color: #dfe0ff; }
.bd-about-btn { margin-left: auto; border: 0 !important; cursor: pointer; font: 700 12.5px var(--bd-sans) !important; color: #151a2d !important;
  padding: 7px 14px !important; border-radius: 99px !important; background: linear-gradient(90deg, #ffd36b, #ffab1f) !important;
  box-shadow: 0 4px 14px rgba(255,176,32,.35); white-space: nowrap; }
.bd-about-btn:hover { filter: brightness(1.05); }
.bd-notes { font-size: 12px; color: #ffd36b; } .bd-notes summary { cursor: pointer; }
.bd-notes .banner { color: var(--bd-ink); }

/* flow bar */
.bd-flowbar { background: #fff; border-bottom: 1px solid var(--bd-line); flex: none; }
.bd-flows { display: flex; gap: 8px; padding: 10px 18px; overflow-x: auto; scrollbar-width: none; }
.bd-chip { flex: none; display: flex; align-items: center; gap: 8px; padding: 7px 12px 7px 7px !important; border-radius: 99px !important;
  background: #f1f2f8 !important; border: 1.5px solid transparent !important; cursor: pointer; font-size: 12.5px; transition: .15s; user-select: none; }
.bd-chip:hover { background: #e9e8ff !important; }
.bd-chip.on { background: #efeaff !important; border-color: var(--flow) !important; box-shadow: 0 0 0 4px var(--flow-glow); }
.bd-chip .num { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 11px; background: var(--flow); color: #fff; }
.bd-chip .path { font-family: var(--bd-mono); font-size: 11.5px; }
.bd-tag { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 6px; text-transform: uppercase; letter-spacing: .04em; }
.bd-tag.state { background: var(--field-bg); color: #007a7a; } .bd-tag.contract { background: var(--fx-bg); color: #c81d44; }
.bd-flowinfo { display: grid; grid-template-columns: auto 1fr auto; gap: 10px 16px; align-items: start; padding: 2px 18px 12px; font-size: 13px; }
.bd-flowinfo.whole { display: block; padding-top: 10px; }
.bd-flowinfo .fnum { width: 28px; height: 28px; border-radius: 9px; display: grid; place-items: center; font-weight: 800; background: var(--flow); color: #fff; }
.bd-flowinfo .what { line-height: 1.5; } .bd-flowinfo .what b { font-weight: 700; }
.bd-flowinfo .steps { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 6px; font: 11.5px var(--bd-mono); }
.bd-stepwrap { display: inline-flex; align-items: center; gap: 4px; }
.bd-flowinfo .step { position: relative; padding: 2px 7px; border-radius: 6px; background: #f1f2f8; cursor: pointer; }
.bd-flowinfo .step.chg { background: #ffe7b3; color: #7a4300; font-weight: 700; }
.bd-flowinfo .step.fx { background: var(--fx-bg); color: #b0163e; font-weight: 700; }
.bd-flowinfo .step.field { background: var(--field-bg); color: #006b6b; font-style: italic; }
.bd-flowinfo .step.open { outline: 2px solid #151a2d; outline-offset: 1px; }
.bd-flowinfo .step .sgo { display: inline-block; margin-left: 5px; width: 16px; height: 16px; border-radius: 50%; background: #151a2d; color: #fff;
  font: 700 9px/16px var(--bd-sans); text-align: center; vertical-align: 1px; cursor: pointer; }
.bd-flowinfo .arrow { color: #b3b8cc; }
.bd-more { display: none; border: 0 !important; background: none !important; padding: 0 4px !important; color: var(--flow) !important;
  font: 600 12px var(--bd-sans) !important; cursor: pointer; } .bd-flowinfo .count { margin-left: 6px; }
.bd-flowinfo .landing { min-width: 220px; max-width: 340px; border-left: 3px solid var(--fx); background: var(--warn-bg); border-radius: 0 10px 10px 0;
  padding: 6px 10px; font-size: 12px; }
.bd-flowinfo .landing .k { font: 800 9.5px var(--bd-sans); letter-spacing: .1em; text-transform: uppercase; color: #b0163e; display: block; margin-bottom: 2px; }
.bd-flowinfo .landing .chk { margin-top: 6px; color: #3d4260; } .bd-flowinfo .landing .chk::before { content: "Check · "; font-weight: 700; }

/* main row */
.bd-main { position: relative; display: flex; flex: 1; min-height: 0; }
.bd-stage { position: relative; flex: 1; min-width: 0; overflow: hidden; touch-action: none; }
.bd-canvas { position: absolute; inset: 0; cursor: grab; }
.bd-canvas.drag { cursor: grabbing; }
.bd-bands, .bd-edges, .bd-tethers { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
.bd-bands .fill { fill: rgba(109,74,255,.04); } .bd-bands .fill.alt { fill: rgba(255,255,255,0); }
.bd-bands .rule { fill: none; stroke: #dde1ee; stroke-width: 1; }
.bd-blabel { position: absolute; right: 12px; text-align: right; font-size: 10px; font-weight: 700; letter-spacing: .12em; color: #9aa0b8;
  text-transform: uppercase; transform-origin: 100% 0; pointer-events: none; white-space: nowrap; }
.bd-edge { fill: none; stroke: #c7cbdb; stroke-width: 1.6; transition: stroke .2s, opacity .2s; }
.bd-edge.flow { stroke: var(--flow); stroke-width: 3.2; filter: drop-shadow(0 0 5px var(--flow-glow)); }
.bd-edge.data { stroke-dasharray: 6 5; stroke: var(--field); }
.bd-edge.fx { stroke: var(--fx); stroke-width: 2.6; stroke-dasharray: 6 5; }
.bd-edge.dim { opacity: .25; }
.bd-tethers { z-index: 49; }
.bd-tethers path { stroke: #151a2d; stroke-width: 1.4; stroke-dasharray: 3 4; fill: none; opacity: .45; }
.bd-tethers path.front { opacity: .9; stroke-width: 2; }

/* nodes */
.bd-node { position: absolute; transform-origin: center; padding: 7px 12px; border-radius: 12px; background: #fff; border: 1.5px solid #d4d8e6;
  font: 500 12.5px var(--bd-mono); color: #4a5068; white-space: nowrap; box-shadow: 0 2px 6px rgba(21,26,45,.06); cursor: pointer;
  transition: opacity .2s, box-shadow .2s, border-color .2s; user-select: none; }
.bd-node .lbl { display: inline-block; max-width: 280px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
.bd-node:hover { box-shadow: 0 6px 18px rgba(21,26,45,.16); border-color: #9aa3c4; }
.bd-node.chg { background: linear-gradient(135deg, #ffd36b, #ffab1f); border: 2.5px solid var(--chg-deep); color: #2b1a00; font-weight: 700;
  padding: 9px 14px 8px; border-radius: 14px; animation: bd-pulse 2.4s ease-in-out infinite; }
@keyframes bd-pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(255,176,32,.55), 0 6px 16px rgba(194,106,0,.28); }
                      50% { box-shadow: 0 0 0 10px rgba(255,176,32,0), 0 6px 16px rgba(194,106,0,.28); } }
.bd-node.chg .kind { display: block; font: 800 9px/1 var(--bd-sans); letter-spacing: .12em; text-transform: uppercase; color: #7a4300; margin-bottom: 4px; }
.bd-node .stat { display: inline-flex; gap: 4px; margin-left: 8px; vertical-align: 1px; }
.bd-node .stat b { font: 700 10px var(--bd-mono); padding: 1px 5px; border-radius: 5px; background: #fff; }
.bd-node .stat .p { color: var(--add-ink); } .bd-node .stat .m { color: var(--del-ink); }
.bd-node .warn-dot { position: absolute; right: -7px; top: -7px; width: 16px; height: 16px; border-radius: 50%; background: var(--warn); color: #fff;
  font: 800 10px/16px var(--bd-sans); text-align: center; box-shadow: 0 2px 6px rgba(255,77,109,.45); }
.bd-node.field { border-radius: 4px 14px 14px 4px; background: var(--field-bg); border-color: var(--field); font-style: italic; color: #005f5f; }
.bd-node.onflow { border-color: var(--flow); box-shadow: 0 0 0 4px var(--flow-glow); color: var(--bd-ink); }
.bd-node.chg.onflow { box-shadow: 0 0 0 4px var(--flow-glow), 0 6px 16px rgba(194,106,0,.28); }
.bd-node.dim { opacity: .28; }
.bd-node.has-card { outline: 2px solid rgba(21,26,45,.55); outline-offset: 3px; }
.bd-node.front { outline: 3px solid #151a2d; }
.bd-node.moved::after { content: "↔"; position: absolute; left: -10px; bottom: -10px; font-size: 10px; color: var(--bd-muted); }
.bd-node.grab { cursor: ew-resize; box-shadow: 0 0 0 4px rgba(21,26,45,.18); }
.bd-node .fxbadge { position: absolute; left: 50%; top: calc(100% + 8px); transform: translateX(-50%); background: var(--fx); color: #fff;
  font: 600 10.5px/1.3 var(--bd-sans); font-style: normal; padding: 4px 8px; border-radius: 8px; white-space: nowrap; max-width: 360px;
  overflow: hidden; text-overflow: ellipsis; box-shadow: 0 4px 12px rgba(255,77,109,.35); pointer-events: none; }
.bd-go { position: absolute; right: -11px; bottom: -11px; width: 22px; height: 22px; border-radius: 50% !important; border: 0 !important; cursor: pointer;
  background: #151a2d !important; color: #fff !important; font: 700 11px/22px var(--bd-sans) !important; box-shadow: 0 2px 6px rgba(0,0,0,.28);
  padding: 0 !important; opacity: 0; transition: opacity .15s; }
.bd-node:hover .bd-go, .bd-node.chg .bd-go, .bd-node.has-card .bd-go { opacity: 1; }

/* toolbar, legend, hint */
.bd-tools { position: absolute; left: 12px; top: 12px; z-index: 45; display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
  max-width: calc(100% - 24px); pointer-events: none; }
.bd-tools > * { pointer-events: auto; }
.bd-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.bd-toolbar .bd-seg, .bd-toolbar .float { background: #fff !important; box-shadow: 0 4px 14px rgba(21,26,45,.1); }
.bd-toolbar .lbl { font: 700 10px var(--bd-sans); letter-spacing: .1em; text-transform: uppercase; color: var(--bd-muted); margin: 0 4px 0 8px; }
.bd-legend { background: #fff; border: 1px solid var(--bd-line); border-radius: 12px; padding: 8px 10px;
  font-size: 11px; box-shadow: 0 6px 18px rgba(21,26,45,.08); }
.bd-legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin: 0 4px 0 8px; vertical-align: -1px; }
.bd-legend .sw:first-child { margin-left: 0; }
.bd-legend .chg { background: linear-gradient(135deg, #ffd36b, #ffab1f); } .bd-legend .flow { background: var(--flow); }
.bd-legend .field { background: var(--field); } .bd-legend .fx { background: var(--fx); }
.bd-hint { position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%); background: rgba(21,26,45,.86); color: #fff; font-size: 12px;
  padding: 7px 14px; border-radius: 99px; z-index: 90; pointer-events: none; white-space: nowrap; }

/* buttons */
.bd-ibtn { border: 0 !important; background: #f1f2f8 !important; height: 28px; min-width: 28px; padding: 0 10px !important; border-radius: 8px !important;
  cursor: pointer; font: 600 12px var(--bd-sans) !important; color: var(--bd-ink) !important; white-space: nowrap; }
.bd-ibtn:hover { background: #e5e3ff !important; } .bd-ibtn:disabled { opacity: .45; cursor: default; }
.bd-seg { display: inline-flex; background: #f1f2f8; border-radius: 9px; padding: 2px; }
.bd-seg .bd-ibtn { background: transparent !important; }
.bd-seg .bd-ibtn.on { background: #fff !important; color: var(--flow) !important; box-shadow: 0 1px 3px rgba(0,0,0,.12); }

/* cards */
.bd-card { position: absolute; width: 460px; background: var(--bd-card); border-radius: 16px; box-shadow: 0 18px 48px rgba(21,26,45,.22);
  border: 1px solid var(--bd-line); overflow: hidden; z-index: 50; cursor: default; transform-origin: 0 0; transition: width .2s, box-shadow .2s; }
.bd-card.front { box-shadow: 0 22px 60px rgba(21,26,45,.32), 0 0 0 2px #151a2d; }
.bd-card.dragged { box-shadow: 0 22px 60px rgba(21,26,45,.3); }
.bd-card .hd, .bd-viewer .fsec > .hd { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: linear-gradient(90deg, #fff1cc, #fff);
  border-bottom: 1px solid var(--bd-line); flex-wrap: wrap; }
.bd-card .hd { cursor: move; touch-action: none; user-select: none; }
.bd-card.ctx .hd { background: linear-gradient(90deg, #eef1ff, #fff); }
.bd-card .hd b, .bd-viewer .hd b { font-family: var(--bd-mono); font-size: 13px; word-break: break-all; }
.bd-card .hd .file, .bd-viewer .hd .file { color: var(--bd-muted); font: 11px var(--bd-mono); }
.bd-card .hd .sp, .bd-viewer .sp { flex: 1; }
.bd-badge { font: 700 9.5px var(--bd-sans); letter-spacing: .08em; text-transform: uppercase; padding: 2px 7px; border-radius: 6px; }
.bd-badge.ctx { background: #e7ebff; color: #3b4bd8; } .bd-badge.chg { background: #ffe7b3; color: #7a4300; }
.bd-card .effects { padding: 8px 12px; background: #fff8fa; border-bottom: 1px solid var(--bd-line); font-size: 12px; }
.bd-card .effects div { margin: 3px 0; } .bd-card .effects .ico { color: var(--fx); font-weight: 700; margin-right: 4px; }
.bd-card .fetched { padding: 5px 12px; font: 11px var(--bd-mono); color: var(--bd-muted); background: #fafbfe; border-bottom: 1px solid var(--bd-line); }
.bd-card .fetched b { color: #3b4bd8; font-weight: 600; }
.bd-card .bd-code { max-height: 300px; }
.bd-card .hd .restore { display: none; }
.bd-card.min { width: auto; border-radius: 99px; box-shadow: 0 6px 16px rgba(21,26,45,.18); cursor: pointer; }
.bd-card.min .hd { border: 0; padding: 5px 6px 5px 12px; flex-wrap: nowrap; gap: 6px; background: #fff; cursor: pointer; }
.bd-card.min:not(.ctx) .hd { background: linear-gradient(90deg, #ffd36b, #ffab1f); }
.bd-card.min .hd .file, .bd-card.min .hd .bd-badge, .bd-card.min .hd .expand, .bd-card.min .hd .x, .bd-card.min .hd .sp { display: none; }
.bd-card.min .hd .restore { display: inline-block; height: 22px; min-width: 22px; padding: 0 6px !important; }
.bd-note { padding: 10px 12px; font-size: 12px; color: var(--bd-muted); } .bd-note.error { color: #b0163e; }

/* code */
.bd-code { font: 12px/1.65 var(--bd-mono); overflow: auto; }
.bd-ln { display: grid; grid-template-columns: 44px 18px 1fr; cursor: pointer; min-width: max-content; }
.bd-ln:hover, .bd-sbs:hover { background: #f5f3ff; }
.bd-ln .no, .bd-sbs .no { color: #a3a8bf; text-align: right; padding-right: 6px; user-select: none; }
.bd-ln .sg { color: #a3a8bf; text-align: center; user-select: none; }
.bd-ln.a { background: var(--add); } .bd-ln.a .sg { color: var(--add-ink); font-weight: 700; }
.bd-ln.d { background: var(--del); } .bd-ln.d .sg { color: var(--del-ink); font-weight: 700; }
.bd-ln.hot, .bd-sbs.hot { background: #fff4f6; } .bd-ln.hot .no { color: var(--warn); font-weight: 700; }
.bd-ln.focus, .bd-sbs.focus { box-shadow: inset 4px 0 0 var(--flow); }
.bd-code .src { white-space: pre; padding-right: 12px; }
.bd-code .plus { visibility: hidden; margin-left: 6px; color: var(--flow); font: 700 11px var(--bd-sans); }
.bd-ln:hover .plus, .bd-sbs:hover .plus { visibility: visible; }
.hl-kw { color: #d6336c; font-weight: 600; } .hl-ty { color: #6d4aff; } .hl-num { color: #e8590c; } .hl-str { color: #2b8a3e; }
.hl-cm { color: #8a90a8; font-style: italic; } .hl-fn { color: #1c7ed6; } .hl-mc { color: #0b7285; font-weight: 600; } .hl-pp { color: #ae3ec9; }
.bd-ann { margin: 2px 12px 6px 62px; padding: 6px 10px 6px 12px; border-radius: 10px; font: 12px/1.4 var(--bd-sans); border-left: 4px solid; white-space: normal; }
.bd-ann.warn { background: var(--warn-bg); border-color: var(--warn); color: #8a1230; }
.bd-ann.info { background: var(--info-bg); border-color: var(--info); color: #1d4ea0; }
.bd-ann.ok { background: var(--ok-bg); border-color: var(--ok); color: #13692f; }
.bd-ann .k { font-weight: 800; font-size: 10px; letter-spacing: .06em; text-transform: uppercase; margin-right: 6px; }
.bd-thread { margin: 4px 12px 8px 62px; padding: 2px 10px 8px; border-radius: 12px; background: #f5f3ff; border: 1px solid #e0d9ff;
  font: 12.5px var(--bd-sans); white-space: normal; cursor: auto; }
.bd-thread .thread { background: #fff; border-color: #e0d9ff; }
.bd-thread textarea { border: 1px solid #d4ccff; border-radius: 10px; font: 12.5px var(--bd-sans); background: #fff; color: var(--bd-ink); }
.bd-thread button:not(.link) { background: var(--flow); color: #fff; border: 0; border-radius: 9px; font: 600 12px var(--bd-sans); }
.bd-sbs { display: grid; grid-template-columns: 44px minmax(0, 1fr) 44px minmax(0, 1fr); cursor: pointer; }
.bd-sbs .src { white-space: pre-wrap; word-break: break-word; }
.bd-sbs > .src.l, .bd-sbs > .src.empty:nth-child(2) { border-right: 1px solid var(--bd-line); }
.bd-sbs .l.d { background: var(--del); } .bd-sbs .r.a { background: var(--add); }
.bd-sbs .no.l.d { color: var(--del-ink); font-weight: 700; } .bd-sbs .no.r.a { color: var(--add-ink); font-weight: 700; }
.bd-sbs .empty { background: repeating-linear-gradient(135deg, #fafbfd, #fafbfd 6px, #f1f2f8 6px, #f1f2f8 12px); }

/* side panels */
.bd-resizer { position: absolute; left: -5px; top: 0; bottom: 0; width: 10px; cursor: col-resize; z-index: 6; touch-action: none; }
.bd-resizer::after { content: ""; position: absolute; left: 4px; top: 50%; width: 2px; height: 36px; margin-top: -18px; border-radius: 2px; background: #c9cde0; }
.bd-resizer:hover::after, body.bd-resizing .bd-resizer::after { background: var(--flow); }
.bd-viewer { position: relative; display: flex; flex-direction: column; width: var(--w); flex: none; max-width: 75vw; background: #fff;
  border-left: 1px solid var(--bd-line); box-shadow: -12px 0 32px rgba(21,26,45,.08); z-index: 60; min-width: 0; }
.bd-viewer .top { flex: none; display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--bd-line);
  background: #fafbfe; flex-wrap: wrap; }
.bd-viewer .top b { font-size: 13px; } .bd-viewer .top .muted { color: var(--bd-muted); font-size: 12px; }
.bd-viewer .files { flex: 1; overflow: auto; }
.bd-viewer .fsec { border-bottom: 1px solid var(--bd-line); }
.bd-viewer .fsec > .hd { position: sticky; top: 0; z-index: 2; cursor: pointer; }
.bd-viewer .fsec .chev { width: 18px; color: var(--bd-muted); font-weight: 700; }
.bd-viewer .fsec .cnt { font: 11px var(--bd-mono); } .bd-viewer .fsec .cnt .p { color: var(--add-ink); }
.bd-viewer .fsec .cnt .m { color: var(--del-ink); margin-left: 4px; }
.bd-viewer .fsec.flash > .hd { animation: bd-flash 1s; } @keyframes bd-flash { 0% { background: #d9d0ff; } 100% { } }
.bd-about { position: relative; display: flex; flex-direction: column; width: var(--w); flex: none; max-width: 60vw; background: #fff;
  border-left: 1px solid var(--bd-line); z-index: 55; min-height: 0; }
.bd-about .top { position: relative; padding: 18px 20px 14px; background: linear-gradient(135deg, #151a2d, #2a2466); color: #fff; }
.bd-about .top .close { position: absolute; right: 12px; top: 12px; background: rgba(255,255,255,.16) !important; color: #fff !important; }
.bd-about .top h2 { margin: 6px 0 4px; font-size: 18px; } .bd-about .top p { margin: 0; color: #c9caff; font-size: 13px; }
.bd-about .body { overflow: auto; padding: 16px 20px 24px; }
.bd-about h3 { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--bd-muted); margin: 18px 0 8px; }
.bd-about h3:first-child { margin-top: 0; }
.bd-about .intent { font-size: 14px; line-height: 1.55; white-space: pre-wrap; }
.bd-about .why { padding-left: 18px; } .bd-about .why li { margin: 4px 0; }
.bd-about .sev { font: 800 9.5px var(--bd-sans); padding: 1px 6px; border-radius: 5px; margin-right: 6px; background: #e7ebff; color: #3b4bd8; }
.bd-about .sev.high { background: var(--fx); color: #fff; } .bd-about .sev.medium { background: #ffcf66; color: #5a3a00; }
.bd-about .cl { border: 1px solid var(--bd-line); border-radius: 12px; padding: 10px 12px; margin-bottom: 8px; }
.bd-about .cl .n { font: 700 12px var(--bd-mono); color: var(--flow); } .bd-about .cl .desc { margin-top: 2px; white-space: pre-wrap; }
.bd-about .cl .m { color: var(--bd-muted); font-size: 12px; }
.bd-about .tree { font: 13px var(--bd-mono); border: 1px solid var(--bd-line); border-radius: 12px; padding: 6px 0; }
.bd-about .tree .dir, .bd-about .tree .file { display: flex; align-items: center; gap: 8px; padding: 5px 12px; cursor: pointer; }
.bd-about .tree .file { padding-left: 34px; }
.bd-about .tree .dir:hover, .bd-about .tree .file:hover { background: #f5f3ff; }
.bd-about .tree .file.on { background: #efeaff; box-shadow: inset 3px 0 0 var(--flow); }
.bd-about .tree .dir { font-weight: 700; color: #3b4bd8; } .bd-about .tree .caret { width: 12px; color: var(--bd-muted); }
.bd-about .tree .act { font: 700 9.5px var(--bd-sans); text-transform: uppercase; padding: 1px 6px; border-radius: 5px; background: #fff1cc; color: #7a4300; }
.bd-about .tree .cnt { margin-left: auto; font-size: 11px; } .bd-about .tree .cnt .p { color: var(--add-ink); }
.bd-about .tree .cnt .m { color: var(--del-ink); margin-left: 4px; }
.bd-about .tree .clb { font: 600 10px var(--bd-sans); color: var(--flow); background: #efeaff; padding: 1px 6px; border-radius: 5px; }

@media (max-width: 1100px) {
  .bd-viewer { position: fixed; inset: 0; width: auto; max-width: none; border-left: 0; z-index: 70; }
  .bd-about { position: fixed; inset: 0; width: auto; max-width: none; border-left: 0; z-index: 65; }
  .bd-resizer { display: none; }
}
@media (max-width: 760px) {
  .bd-flowinfo { grid-template-columns: auto 1fr; }
  .bd-flowinfo .landing { grid-column: 1 / -1; max-width: none; }
}
@media (max-width: 640px) {
  .bd-card.sheet { position: fixed; left: 8px; right: 8px; width: auto; top: auto; bottom: 8px; max-height: 72vh; display: flex; flex-direction: column; }
  .bd-card.sheet .bd-code { max-height: 36vh; }
  .bd-legend { display: none; }
  .bd-chip .path { max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bd-hint { white-space: normal; width: calc(100% - 32px); text-align: center; bottom: auto; top: 54px; }
  .bd-about-btn { margin-left: 0; }
  .bd-head { padding: 8px 16px; gap: 6px 8px; }
  .bd-head h1 { font-size: 15px; }
  .bd-head .bd-pill.ghost, .bd-head .rerun { display: none; }
  .bd-head nav a { padding: 2px 8px; font-size: 12px; }
  .bd-about-btn { padding: 5px 12px !important; font-size: 12px !important; }
  .bd-more { display: inline; }
  .bd-flowinfo.brief .what, .bd-flowinfo.brief .landing { display: none; }
  .bd-flowinfo.brief .fnum { display: none; }
  .bd-flowinfo.brief { grid-template-columns: 1fr; }
  .bd-flows { padding: 8px 16px; } .bd-flowinfo { padding: 2px 16px 10px; }
}
```

`frontend/src/pages/Review.tsx` (replace the whole file):

```tsx
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, type Board as BoardModel, type Comment, type FileChange, type Finding, type ReviewDetail } from "../api";
import { useMe } from "../App";
import Board from "../board/Board";
import ClsPanel from "../components/ClsPanel";
import Files from "../components/Files";
import Findings from "../components/Findings";
import Stages from "../components/Stages";

const TERMINAL = new Set(["done", "degraded", "failed"]);

export default function Review() {
  const id = Number(useParams().id);
  const me = useMe();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [board, setBoard] = useState<BoardModel | null | undefined>(undefined);   // null: no board for this review
  const [findings, setFindings] = useState<Finding[]>([]);
  const [files, setFiles] = useState<FileChange[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [focus, setFocus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(() => api.review(id).then(setDetail).catch((e) => setError(String(e.message ?? e))), [id]);
  const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
  const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
  const loadResults = useCallback(() => Promise.all([
    api.board(id).then(setBoard).catch((e) => { if (e instanceof ApiError && e.status === 404) setBoard(null); else throw e; }),
    loadFindings(), api.files(id).then(setFiles), loadComments(),
  ]).catch((e) => setError(String(e.message ?? e))), [id, loadFindings, loadComments]);

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

  const onCite = useCallback((cite: string) => {
    if (cite.startsWith("F")) { setFocus(cite); navigate(`/r/${id}/findings`); }
    else navigate(`/r/${id}?node=${encodeURIComponent(cite)}`);
  }, [id, navigate]);

  if (error) return <main className="page error">{error}</main>;
  if (!detail) return <main className="page muted">Loading…</main>;
  const r = detail.review;
  const ready = TERMINAL.has(r.status);
  const notes = detail.stages.filter((s) => s.status === "failed" || s.status === "degraded");

  const head = (extra?: ReactNode) => (
    <div className="bd-head">
      <h1>{r.title}</h1>
      {r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
      {!ready && <span className="bd-pill ghost">{r.status}</span>}
      <span className="bd-pill ghost">{r.cls.map((c) => `CL ${c}`).join(" · ")}</span>
      {board && <span className="bd-pill ghost">{board.flows.length} flows · {findings.length} findings</span>}
      <nav aria-label="Review sections">
        <NavLink end to={`/r/${id}`} className={({ isActive }) => (isActive ? "on" : "")}>Board</NavLink>
        <NavLink to={`/r/${id}/findings`} className={({ isActive }) => (isActive ? "on" : "")}>Findings ({findings.length})</NavLink>
        <NavLink to={`/r/${id}/files`} className={({ isActive }) => (isActive ? "on" : "")}>Files ({files.length})</NavLink>
        <NavLink to={`/r/${id}/cls`} className={({ isActive }) => (isActive ? "on" : "")}>CLs &amp; Swarm</NavLink>
      </nav>
      {me?.is_owner && ready && <button className="link rerun" onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button>}
      {notes.length > 0 && (
        <details className="bd-notes">
          <summary>{notes.length} stage note(s)</summary>
          {notes.map((s) => <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>)}
        </details>
      )}
      {extra}
    </div>
  );
  const page = (body: ReactNode) => (
    <main className="review">{head()}<div className="review-body">{body}</div></main>
  );

  if (!ready)
    return page(<><Stages stages={detail.stages} /><p className="muted">Analysis in progress…</p></>);
  return (
    <Routes>
      <Route index element={board ? (
        <main className="review board">
          <Board reviewId={id} board={board} files={files} comments={comments} onComments={loadComments} risk={r.risk}
                 focus={params.get("node")} head={head} />
        </main>
      ) : page(board === undefined ? <p className="muted">Loading…</p> : (
        <div className="banner warn">No review board for this review (see the stage notes above). Findings, files and CLs are still available.</div>
      ))} />
      <Route path="findings" element={page(
        <Findings reviewId={id} findings={findings} focus={focus} comments={comments}
                  onComments={loadComments} onFindings={loadFindings} onCite={onCite} />)} />
      <Route path="files" element={page(<Files reviewId={id} files={files} comments={comments} onComments={loadComments} />)} />
      <Route path="cls" element={page(<ClsPanel reviewId={id} cls={detail.cls} onChange={loadDetail} />)} />
    </Routes>
  );
}
```

`frontend/src/styles.css`:

```diff
diff --git a/frontend/src/styles.css b/frontend/src/styles.css
index 0c9479a..45e893f 100644
--- a/frontend/src/styles.css
+++ b/frontend/src/styles.css
@@ -16,6 +16,12 @@
 }
 * { box-sizing: border-box; }
 body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 var(--sans); }
+#root { display: flex; flex-direction: column; height: 100vh; height: 100dvh; }
+#root > main { flex: 1; min-height: 0; overflow: auto; width: 100%; }
+#root > .topbar { flex: none; }
+.review { display: flex; flex-direction: column; overflow: hidden !important; }
+.review-body { flex: 1; min-height: 0; overflow: auto; padding: 16px 24px; }
+.review.board { overflow: hidden; }
 a, .link { color: var(--accent); }
 button { font: inherit; cursor: pointer; border: 1px solid var(--line); background: var(--surface); color: var(--ink);
   border-radius: 6px; padding: 5px 12px; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test`
Expected: `✓ built in …` and `4 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  37 passed (37)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/useSources.ts frontend/src/board/CodeView.tsx frontend/src/board/Resizer.tsx frontend/src/board/Canvas.tsx frontend/src/board/CardLayer.tsx frontend/src/board/FileViewer.tsx frontend/src/board/ChangePanel.tsx frontend/src/board/FlowBar.tsx frontend/src/board/Board.tsx frontend/src/board/board.css frontend/src/pages/Review.tsx frontend/src/styles.css frontend/e2e/helpers.ts frontend/e2e/board.spec.ts frontend/e2e/smoke.spec.ts frontend/e2e/mobile.spec.ts frontend/package.json frontend/package-lock.json
git commit -m "feat(ui): review board page replaces storyboard, call-flow and blast-radius tabs"
```

---

### Task 12: Lab: board check for the planted CLs

The libgit2 lab is the real-code check (spec §1 success criteria). Document what the board must show for the planted
CLs, then run it.

**Files:**
- Modify: `lab/README.md`

**Interfaces:**
- Consumes: the whole pipeline (Tasks 1–5) against the lab's Perforce workspace.

- [ ] **Step 1: Write it**

`lab/README.md`:

```diff
diff --git a/lab/README.md b/lab/README.md
index 4a68ff4..b3e16a3 100644
--- a/lab/README.md
+++ b/lab/README.md
@@ -32,6 +32,19 @@ $CT serve  --config $LAB/tortoise.yaml
 | 28 | `git_repository_head_detached()` resets `configmap_cache` through `intptr_t *cache = repo->configmap_cache` | **high field mutation** with readers `git_repository__configmap_lookup*` (precise via follow-up TU) |
 | 29 (stacked on 28) | new `git_repository::head_detached_cache` written through `int *detached` | **high header fan-out** (273 TUs, 6 layers) + **medium field mutation** |
 
+## Review board check
+
+After `$CT review … 30` and `$CT review … 28 29`, the `board` stage is `ok` and the board (`GET /api/reviews/<id>/board`,
+or the review page in a browser) shows:
+
+| Review | Flows | Annotations |
+|---|---|---|
+| 30 | 1 contract flow: `check_safecrlf → output_eol ⟶ -1 unhandled` | crlf.c:133 new return value `-1` (on `output_eol`); crlf.c:166 and :186 warn (`checks GIT_EOL_LF (==2)` / `GIT_EOL_CRLF (==1)` — does not handle -1); crlf.c:265 ok (`!=1` covers -1) |
+| 28+29 | 2 state flows: `git_repository_head_detached → git_repository::configmap_cache → git_repository__configmap_lookup` and `… → git_repository__configmap_lookup_cache_clear` | repository.c:3058 and :3071 (writes through aliases `cache`, `detached`); config_cache.c:114, :128, :139 warn (reads and writes `configmap_cache`); repository.h:172 warn (new writer, readers); repository.h:165 info (`head_detached_cache`: no readers in the parsed code) |
+
+No test function appears as a flow entry or as a board node; every function node has a depot path, so its code opens on
+demand (`p4 print` at the workspace's have revision).
+
 ## Results at the time of writing
 
 - Index: 1,190 files in 4.3 s. Headless review without LLM: 3–20 s (CL 20, 22 changed functions, 223 TU parses: ~20 s).
```

- [ ] **Step 2: Run the lab check**

With the lab up (`source $LAB/env.sh`; p4d and the workspace as in `lab/README.md`):

```bash
$CT review --config $LAB/tortoise.yaml 30
$CT review --config $LAB/tortoise.yaml 28 29
```

Expected: the `board` stage line reads `board       ok        9 node(s), 1 flow(s), 4 annotation(s)` for CL 30 and `board       ok        19 node(s), 2 flow(s), 7 annotation(s)` for 28+29, and the board in the browser matches the table above. (The `llm` stage is `ok` with an LLM configured and `degraded` without one; the board is the same.)

- [ ] **Step 3: Commit**

```bash
git add lab/README.md
git commit -m "docs(lab): review board check for the planted CLs"
```

---

## Spec Coverage

| Spec section | Where |
|---|---|
| §1 success criteria: fixture's three flows and annotations | Task 3 (`test_fixture_board_has_the_three_prototype_flows`, `test_fixture_board_annotates_where_the_effects_land`) |
| §1 success criteria: libgit2 planted CLs | Task 12 |
| §1 success criteria: every interaction, desktop and phone | Tasks 7 (rules), 11 (e2e desktop + phone) |
| §1 success criteria: faster LLM stage | Task 4 (`test_llm_calls_run_concurrently`) |
| §2 page structure, secondary tabs, M1 tabs removed | Task 11 |
| §3.1 lens | Task 6 |
| §3.2 nodes, §3.3 modes/flows/edges | Tasks 3 (data), 8 (flow sets), 11 (`Canvas.tsx`) |
| §3.4 cards | Tasks 8 (`placeCards`), 9 (code rows), 11 (`CardLayer.tsx`) |
| §3.5 file viewer | Tasks 7 (viewer transitions), 11 (`FileViewer.tsx`) |
| §3.6 change panel | Tasks 3 (`build_about`), 11 (`ChangePanel.tsx`) |
| §3.7 interaction rules | Task 7 (reducer tests), Task 11 (e2e) |
| §4.1–4.3 components, data loading, state | Tasks 6–11 |
| §4.4 per-viewer preferences | Tasks 9 (`prefs.ts`), 11 |
| §4.5 comments | Task 10 |
| §5.1 pipeline stage | Task 4 |
| §5.2 board model, node selection, initial x | Task 3 |
| §5.3 impact annotations (+ fact additions) | Tasks 1, 3 |
| §5.4 source on demand | Tasks 2, 5 |
| §5.5 flows | Task 3 (LLM narratives: Task 4) |
| §5.6 LLM concurrency | Task 4 |
| §5.7 API | Task 5 |
| §6 error handling | Tasks 4 (degraded board, LLM fallback), 5 (403/415/413/502), 11 (no-board banner, card retry) |
| §7 testing | every task |
| §8 validation decisions | Tasks 3, 4, 5, 7, 9, 10, 11 |

## Finish

- [ ] Run everything once more: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q` (expected `170 passed`),
  `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx playwright test` (expected `Tests  37 passed (37)`, `4 passed`).
- [ ] Look at it: `uv run codetortoise fixture-demo --dir /tmp/ct-demo --port 8811` then `uv run codetortoise serve --config /tmp/ct-demo/tortoise.yaml`,
  open `http://127.0.0.1:8811`, log in as `demo`, review CLs `101 102`, and walk the prototype's interactions on a desktop and a phone.
