# Change Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A review marks exactly the functions a change edits — no unchanged function shown as added, no changed source dropped
by the TU budget, no story left empty because it holds only declarations.

**Architecture:** Four faults, fixed where they start. (1) TU selection ranks changed sources first and hands the ones over the
budget to tree-sitter instead of dropping them. (2) The impact model decides "changed / added / removed" from each parsed
function's own lines against the file's line diff (clang's spans where clang parsed the file) instead of stamping the diff
map's tree-sitter guess on whatever overlaps it. (3) The diff map re-finds functions on a text with one branch per `#if` when a
conditional tangles tree-sitter's parse, and drops changes no edit touches. (4) Declaration changes carry their texts, a story of
declarations only shows them, and a declaration joins the story that defines what it declares.

**Tech Stack:** Python 3.12 (tree-sitter, libclang, pydantic, pytest, ruff), React + TypeScript (vitest, Playwright).

**Spec:** none written. The design is the evaluation agreed in chat on 2026-10-27; its substance is restated under Context.

## Context (the agreed evaluation, restated)

- Tree-sitter parses raw text with no preprocessor. A function whose braces an `#if`/`#else` splits can vanish from its parse
  (or swallow its neighbours), so the diff map calls an unchanged function "added"/"removed", or misses an edited one.
- `impact.build_impact` step 1 stamps the diff map's kind on every parsed function overlapping the diff map's line range, never
  checking that the function's own lines changed; when nothing overlaps it marks a same-named function in any file.
- `tu_select.select_tus` puts changed sources and header-includer samples both at hop 0 and ranks by `(hop, -refs, path)`; a
  file included by several changed headers outranks a changed `.c`; the cut at `tu_budget` drops changed sources silently.
- Declaration pieces have no function nodes, so a story holding only them has empty "Before → after" and "Where".
- Fix order agreed: TU selection first; then attribution from parsed spans (status from the parse, not the diff map); then
  flattening for boundaries (a line scanner, not tree-sitter's `preproc_spans`; hash the original text; `#if 0` false and its
  `#else` kept) with sanity checks; then declaration stories and "prefer the definition".

## Global Constraints

- The repo is public. Never use any identifier, file, function, macro, struct, story or thread name, workspace name or path from
  the owner's screenshots — in code, tests, comments, commit messages or docs. Use only generic names: `alpha`, `beta`, `gamma`,
  `delta`, `first`, `pick`, `g0`…`g5`, `Widget`, `Mode`, `LIMIT`, `OPT_A`…`OPT_D`, `NEVER_SET`, `caller_one`, `caller_two`, and
  the demo fixture's existing names (`uart_send`, `hal_write`, …).
- No absolute local paths in committed files.
- Back end: run everything from `backend/` with `.venv/bin/python -m pytest …` and `.venv/bin/ruff check codetortoise tests`.
  Never use `uv`. Line length 132.
- Front end: run tools only from `frontend/`: `npx vitest run`, `npx tsc --noEmit`, `npx tsc -p e2e --noEmit`, `npm run build`.
  E2e: `npm run build` first, then
  `TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test <spec> --retries=2`
  (create `../.pwtmp` first, delete it afterwards).
- Never stage, read, move or delete `frontend/e2e/strong-review.txt` (untracked, not ours).
- Commit with `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`; every message ends with the lines
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH`. Stage files by name (never `git add -A`).
- Never `git stash` (bare), `git clean -fdx`, `--force`, or push. Kill only processes you started, by PID.
- Match the surrounding code: its docstring voice (plain sentences), comment density, naming. Stage messages are short plain
  sentences for the review menu; keep the wording of messages you do not change.
- Blobs stored before this branch (selection, diff map, impact, story readings) must still load: every new field has a default.

## Review Focus

1. A file moved or renamed in the change (a `move/delete` and a `move/add` with different paths): a non-static function in it
   reads changed only when its text changed — never added plus removed, never changed for a pure move. (Task 2 test.)
2. CRLF line endings and non-ASCII bytes in a file the parser flattens: every function both parses find keeps the same span and
   hash. (Task 3 test.)
3. A story that has changed functions and also holds a declarations piece keeps its Before → after and Where to its functions;
   declaration rows are only for stories without functions. (Task 4 test.)
4. A changed file with thousands of functions and edits: its edit spans are worked out once per file and side, not once per
   function. (Task 2 test.)
5. Blobs stored before this branch — a selection without `ts_only`, a diff map without `flattened`/`misread`/declaration texts, a
   story reading without `decls` — still load. (Task 4 test.)

## Files

| File | Responsibility | Tasks |
|---|---|---|
| `backend/codetortoise/tu_select.py` | ranking, `ts_only`, follow-up from the changed set | 1, 2 |
| `backend/codetortoise/pipeline.py` | tu_select / facts / impact / diffmap stage messages and wiring | 1, 2, 3 |
| `backend/codetortoise/linediff.py` (new) | a file's line diff and the lines each edit takes up | 2 |
| `backend/codetortoise/attribution.py` (new) | which parsed functions a change edits; mapped changes no parse covers | 2 |
| `backend/codetortoise/impact.py` | step 1 from attribution; takes the change set | 2 |
| `backend/codetortoise/board.py` | `_opcodes` from linediff; about count; node change kind | 2 |
| `backend/codetortoise/cparse.py` | `flatten_preproc`, `parse_source(flatten=…)`, type fields | 3, 4 |
| `backend/codetortoise/diffmap.py` | symmetric flattening, touch filter, `misread`, declaration texts | 3, 4 |
| `backend/codetortoise/facts/treesitter_extractor.py` | tree-sitter facts flatten when tangled | 3 |
| `backend/codetortoise/reading.py` | declaration rows and Where entries | 4 |
| `frontend/src/reading/types.ts`, `frontend/src/workspace/StoryTabs.tsx` | show them | 4 |
| `backend/codetortoise/pieces.py`, `grouping.py`, `llm/stories.py` | the `defines` link and its use | 5 |

---

### Task 1: Changed sources first; the ones over the TU budget read by tree-sitter

**Files:**
- Modify: `backend/codetortoise/tu_select.py` (`TuSelection`, end of `select_tus`)
- Modify: `backend/codetortoise/pipeline.py` (imports; `tu_select()` and `facts()` stage functions)
- Test: `backend/tests/test_tu_select_layers.py`, `backend/tests/test_pipeline.py`

**Interfaces:**
- Produces: `TuSelection.ts_only: list[str]` — changed source files (local paths) that did not fit `tu_budget`, in rank order.
  Later tasks do not change it.

- [ ] **Step 1: Write the failing selection tests** — append to `backend/tests/test_tu_select_layers.py`:

```python
class _Index:
    """A symbol index stub: who includes each header; no callers, no member references."""
    def __init__(self, includers):
        self._inc = includers

    def transitive_includers(self, path):
        return set(self._inc.get(path, ()))

    def callers_of(self, name):
        return []

    def member_refs(self, name):
        return []


class _Cdb:
    def __init__(self, files):
        self._files = files

    def files(self):
        return list(self._files)


def test_changed_sources_come_before_header_includers_however_many_changed_headers_they_include():
    from codetortoise.diffmap import DiffMap, FunctionChange
    one, a, b = "/w/src/one.c", "/w/src/a.c", "/w/src/b.c"
    h1, h2 = "/w/inc/x.h", "/w/inc/y.h"
    dm = DiffMap(changed_files=[h1, h2, one],
                 functions=[FunctionChange(file=one, depot="//d/src/one.c", qualname="alpha", name="alpha",
                                           kind="body_modified", before_lines=(1, 3), after_lines=(1, 3))])
    sel = select_tus(dm, _Index({h1: [a, b], h2: [a, b]}), _Cdb([one, a, b]), AnalysisConfig(tu_budget=2))
    assert sel.selected == [one, a]          # a and b count once per changed header; the changed one.c still comes first
    assert sel.ts_only == [] and sel.over_budget == 1


def test_changed_sources_over_the_budget_go_to_tree_sitter_those_with_mapped_changes_kept_first():
    from codetortoise.diffmap import DiffMap, FunctionChange
    z, a = "/w/src/z.c", "/w/src/a.c"
    dm = DiffMap(changed_files=[a, z],
                 functions=[FunctionChange(file=z, depot="//d/src/z.c", qualname="beta", name="beta",
                                           kind="body_modified", before_lines=(1, 3), after_lines=(1, 3))])
    sel = select_tus(dm, _Index({}), _Cdb([a, z]), AnalysisConfig(tu_budget=1))
    assert sel.selected == [z] and sel.ts_only == [a] and sel.over_budget == 1
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_tu_select_layers.py -q -k "header_includers or tree_sitter"`
Expected: FAIL — the first with `[a, b]` selected, the second with `AttributeError` on `ts_only`.

- [ ] **Step 3: Implement the ranking and `ts_only`** in `backend/codetortoise/tu_select.py`.

Add the field (last in `TuSelection`):

```python
    over_budget: int = 0
    ts_only: list[str] = Field(default_factory=list)   # changed sources over the budget: read by tree-sitter only
```

In `select_tus`, collect the changed sources where they are forced in:

```python
    sel = TuSelection()
    changed: set[str] = set()
    for f in dm.changed_files:
        if f in tus or not is_header(f):
            # changed sources without a compile-DB entry (other variants, new files) still get parsed,
            # borrowing flags from the nearest entry (Toolchain.args_for)
            add(f, 0, force=True)
            changed.add(f)
        else:
```

and replace the ranking at the end:

```python
    # changed sources first (those the diff map found changes in before the rest), then by hop and references
    edited = {c.file for c in dm.functions} | {t.file for t in dm.types}
    ranked = sorted(hop, key=lambda p: (p not in changed, p not in edited, hop[p], -refs[p], p))
    sel.selected = ranked[: cfg.tu_budget]
    sel.hops = {p: hop[p] for p in sel.selected}
    sel.over_budget = max(0, len(ranked) - cfg.tu_budget)
    sel.ts_only = [p for p in ranked[cfg.tu_budget:] if p in changed]
    return sel
```

- [ ] **Step 4: Run the selection tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_tu_select_layers.py -q`
Expected: PASS (the existing `test_budget_caps_selection_changed_first` still passes: its dropped TUs are not changed sources).

- [ ] **Step 5: Write the failing pipeline test** — append to `backend/tests/test_pipeline.py`:

```python
def test_changed_sources_over_the_tu_budget_are_read_by_tree_sitter_and_the_stage_says_so(fx, tmp_path):
    from helpers import make_config

    from codetortoise.services import build_services
    svc = build_services(make_config(fx, tmp_path, analysis={"module_min_files": 1, "workers": 1, "tu_budget": 1}))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = stages(svc, rid)
    assert st["tu_select"] == "degraded" and st["facts"] == "degraded" and st["impact"] == "ok"
    msg = next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "tu_select")
    assert "1 changed source file(s) over the TU budget, read by tree-sitter only: //fixture/" in msg
    im = svc.store.get_blob(rid, "impact")
    assert sorted(im["nodes"][n]["label"] for n in im["changed"]) == ["hal_write", "uart_send"]
```

- [ ] **Step 6: Run it to see it fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pipeline.py -q -k over_the_tu_budget`
Expected: FAIL — `tu_select` is "ok" and one of the two changed functions is missing from `changed`.

- [ ] **Step 7: Wire the stages** in `backend/codetortoise/pipeline.py`.

Import: `from codetortoise.facts.treesitter_extractor import extract_tu_treesitter`.

`tu_select()` becomes:

```python
    def tu_select():
        if svc.index.generation() == 0:
            svc.build_index()
        sel = select_tus(ctx["dm"], svc.index, svc.cdb, cfg.analysis)
        ctx["sel"] = sel
        store.put_blob(rid, "selection", sel)
        msg = f"{len(sel.selected)} TU(s) selected, {sel.over_budget} over budget"
        if sel.ts_only:
            depot = {f.local: f.depot for f in ctx["cs"].files}
            names = ", ".join(depot.get(p, p) for p in sel.ts_only[:5])
            more = f" (+{len(sel.ts_only) - 5} more)" if len(sel.ts_only) > 5 else ""
            raise Degraded(f"{msg}; {len(sel.ts_only)} changed source file(s) over the TU budget, read by tree-sitter "
                           f"only: {names}{more}")
        return msg
```

In `facts()`, right after the line `after = extract(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "after"))`, add:

```python
        if ctx["sel"].ts_only:      # changed sources over the budget: tree-sitter, so their functions still count
            parsed = {f.tu.file for f in before + after}
            over = TuSelection(selected=ctx["sel"].ts_only)
            for variant, out in (("before", before), ("after", after)):
                out += [extract_tu_treesitter(r, reason="over the TU budget")
                        for r in build_requests(over, ctx["cs"], svc.toolchain, variant) if r.file not in parsed]
```

- [ ] **Step 8: Run the pipeline tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pipeline.py tests/test_tu_select_layers.py -q`
Expected: PASS.

- [ ] **Step 9: Full back-end suite and lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check codetortoise tests`
Expected: all pass, "All checks passed!".

- [ ] **Step 10: Commit**

```bash
git add backend/codetortoise/tu_select.py backend/codetortoise/pipeline.py backend/tests/test_tu_select_layers.py backend/tests/test_pipeline.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "fix(tu-select): changed sources come first, and those over the budget are read by tree-sitter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 2: A function is changed when an edit touches its own lines

**Files:**
- Create: `backend/codetortoise/linediff.py`, `backend/codetortoise/attribution.py`, `backend/tests/test_attribution.py`
- Modify: `backend/codetortoise/board.py` (`_opcodes` at ~305, the node-change block at ~766, `build_about` at ~938)
- Modify: `backend/codetortoise/impact.py` (`build_impact` signature and step 1; delete `_overlaps`)
- Modify: `backend/codetortoise/tu_select.py` (`field_follow_up`)
- Modify: `backend/codetortoise/pipeline.py` (`facts()`, `impact()`)
- Test: `backend/tests/conftest.py`, `test_impact.py`, `test_detectors.py`, `test_tu_select_layers.py`, `test_board.py`,
  `test_pipeline.py`

**Interfaces:**
- Consumes: `TuSelection.ts_only` (Task 1; the facts stage already extracts those files).
- Produces:
  - `codetortoise.linediff.opcodes(before: str, after: str) -> tuple` (cached; board re-exports it as `_opcodes`)
  - `codetortoise.linediff.edits(before: str, after: str, side: Literal["before", "after"]) -> tuple[tuple[int, int], ...]`
  - `codetortoise.linediff.touches(spans, lo: int, hi: int) -> bool`
  - `codetortoise.attribution.changed_functions(before: list[Facts], after: list[Facts], cs: ChangeSet) -> dict[str, str]`
    (usr → "changed" | "added" | "removed")
  - `codetortoise.attribution.unparsed(dm: DiffMap, before: list[Facts], after: list[Facts]) -> list[FunctionChange]`
  - `build_impact(before, after, cs: ChangeSet, sel, index, layers, cfg, marked=())` — the third argument is now the change
    set (it was the diff map).
  - `field_follow_up(changed: Collection[str], after, index, cdb, sel, cfg)` — the first argument is now the changed usrs.
  - `board._change_kind(status: str, ch: FunctionChange | None) -> str`

- [ ] **Step 1: Write the failing attribution tests** — create `backend/tests/test_attribution.py`:

```python
"""Which functions a change edits (change attribution): each parsed function's own lines against its file's line diff."""
from codetortoise.attribution import changed_functions, unparsed
from codetortoise.diffmap import DiffMap, FunctionChange
from codetortoise.facts.model import Facts, Function, TuInfo
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange

A, B = "/w/a.c", "/w/b.c"
THREE = ["int alpha(void)", "{", "  return 1;", "}", "int beta(void)", "{", "  int x = 2;", "  return x;", "}",
         "int gamma(void)", "{", "  return 3;", "}"]          # alpha 1-4, beta 5-9, gamma 10-13


def text(lines):
    return "\n".join(lines) + "\n"


def fn(name, start, end, file=A, usr=None):
    return Function(usr=usr or f"c:@F@{name}", qualname=name, name=name, signature=f"int {name}(void)",
                    return_type="int", file=file, start_line=start, end_line=end)


def facts(variant, *fns, file=A):
    return [Facts(tu=TuInfo(file=file, variant=variant), functions=list(fns))]


def three(variant):
    return facts(variant, fn("alpha", 1, 4), fn("beta", 5, 9), fn("gamma", 10, 13))


def change(before, after, local=A):
    return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                     files=[FileChange(depot="//d" + local, local=local, action="edit", before=before, after=after)])


def test_an_edit_marks_only_the_function_whose_own_lines_it_touches():
    after = list(THREE)
    after[7] = "  return x + 1;"
    assert changed_functions(three("before"), three("after"), change(text(THREE), text(after))) == {"c:@F@beta": "changed"}


def test_a_whitespace_only_edit_changes_nothing():
    after = list(THREE)
    after[7] = "    return   x;"
    assert changed_functions(three("before"), three("after"), change(text(THREE), text(after))) == {}


def test_a_pure_deletion_inside_a_function_changes_it():
    after = THREE[:6] + THREE[7:]                       # beta's "int x = 2;" deleted: beta is 5-8 after
    a = facts("after", fn("alpha", 1, 4), fn("beta", 5, 8), fn("gamma", 9, 12))
    assert changed_functions(three("before"), a, change(text(THREE), text(after))) == {"c:@F@beta": "changed"}


def test_a_new_function_is_added_and_a_dropped_one_removed():
    after = THREE[:9] + ["int delta(void)", "{", "  return 4;", "}"]   # gamma replaced by delta
    a = facts("after", fn("alpha", 1, 4), fn("beta", 5, 9), fn("delta", 10, 13))
    assert changed_functions(three("before"), a, change(text(THREE), text(after))) == {"c:@F@delta": "added",
                                                                                         "c:@F@gamma": "removed"}


def test_a_same_named_function_in_an_unchanged_file_is_never_changed():
    after = list(THREE)
    after[7] = "  return x + 1;"
    other = fn("beta", 1, 5, file=B, usr="c:b.c@F@beta")
    got = changed_functions(three("before") + facts("before", other, file=B), three("after") + facts("after", other, file=B),
                            change(text(THREE), text(after)))
    assert got == {"c:@F@beta": "changed"}


def test_a_tree_sitter_version_and_a_clang_version_of_one_function_are_one_function():
    after = list(THREE)
    after[7] = "  return x + 1;"
    b = facts("before", fn("alpha", 1, 4, usr="ts:/w/a.c#alpha"), fn("beta", 5, 9, usr="ts:/w/a.c#beta"),
              fn("gamma", 10, 13, usr="ts:/w/a.c#gamma"))
    assert changed_functions(b, three("after"), change(text(THREE), text(after))) == {"c:@F@beta": "changed"}


def test_a_function_moved_to_another_file_is_changed_only_if_its_text_changed():
    old, new = "/w/old.c", "/w/new.c"
    body = ["int alpha(void)", "{", "  return 1;", "}"]
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/old.c", local=old, action="move/delete", before=text(body), after=""),
        FileChange(depot="//d/new.c", local=new, action="move/add", before="", after=text(body))])
    b, a = facts("before", fn("alpha", 1, 4, file=old), file=old), facts("after", fn("alpha", 1, 4, file=new), file=new)
    assert changed_functions(b, a, cs) == {}
    edited = list(body)
    edited[2] = "  return 2;"
    cs.files[1].after = text(edited)
    assert changed_functions(b, a, cs) == {"c:@F@alpha": "changed"}


def test_a_files_edits_are_worked_out_once_however_many_functions_it_has(monkeypatch):
    import codetortoise.attribution as attribution
    from codetortoise.linediff import edits
    calls = []
    monkeypatch.setattr(attribution, "edits", lambda b, a, side: calls.append(side) or edits(b, a, side))
    n = 500
    before = [f"int f{i}(void) {{ return {i}; }}" for i in range(n)]
    after = [f"int f{i}(void) {{ return {i + 1}; }}" if i % 2 else before[i] for i in range(n)]
    fns = [fn(f"f{i}", i + 1, i + 1) for i in range(n)]
    got = changed_functions(facts("before", *fns), facts("after", *fns), change(text(before), text(after)))
    assert len(got) == n // 2 and sorted(calls) == ["after", "before"]


def test_a_mapped_change_no_parsed_function_covers_is_unparsed():
    dm = DiffMap(functions=[
        FunctionChange(file=A, depot="//d/a.c", qualname="beta", name="beta", kind="body_modified",
                       before_lines=(5, 9), after_lines=(5, 9)),
        FunctionChange(file=A, depot="//d/a.c", qualname="hidden", name="hidden", kind="body_modified",
                       before_lines=(20, 24), after_lines=(20, 24)),
        FunctionChange(file=A, depot="//d/a.c", qualname="gone", name="gone", kind="removed", before_lines=(10, 13))])
    assert [c.qualname for c in unparsed(dm, three("before"), three("after"))] == ["hidden"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_attribution.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.attribution'`.

- [ ] **Step 3: Create `backend/codetortoise/linediff.py`**

```python
"""A file's line diff and the lines each edit takes up: what decides which code a change touched."""
from __future__ import annotations

import bisect
import difflib
import functools
from typing import Literal


@functools.lru_cache(maxsize=128)
def opcodes(before: str, after: str) -> tuple:
    """A file's line diff, once: every function of the file is counted against it."""
    return tuple(difflib.SequenceMatcher(None, before.splitlines(), after.splitlines(), autojunk=False).get_opcodes())


@functools.lru_cache(maxsize=256)
def edits(before: str, after: str, side: Literal["before", "after"]) -> tuple[tuple[int, int], ...]:
    """The lines each edit takes up on one side (1-based, inclusive), in order. A pure insertion (seen from the before side)
    or deletion (from the after side) takes up the line after its position, so one just inside a function touches it."""
    out = []
    for tag, i1, i2, j1, j2 in opcodes(before, after):
        if tag != "equal":
            s, e = (i1, i2) if side == "before" else (j1, j2)
            out.append((s + 1, max(e, s + 1)))
    return tuple(out)


def touches(spans: tuple[tuple[int, int], ...], lo: int, hi: int) -> bool:
    """Whether any of `spans` (from `edits`, so in order) overlaps lines lo..hi."""
    k = bisect.bisect_left(spans, lo, key=lambda s: s[1])     # the first edit ending at or after lo
    return k < len(spans) and spans[k][0] <= hi
```

In `backend/codetortoise/board.py`, delete the `_opcodes` function (the `@functools.lru_cache(maxsize=128)` block around line
305) and add `from codetortoise.linediff import opcodes as _opcodes` to the imports (keep it sorted with the other
`codetortoise` imports). `causes.py` and `pieces.py` keep importing `_opcodes` from `board`. Remove `import difflib` from
board.py if nothing else there uses it (ruff will say).

- [ ] **Step 4: Create `backend/codetortoise/attribution.py`**

```python
"""Which functions a change edits: each parsed function's own lines (clang's where clang parsed its file, tree-sitter's
elsewhere) against its file's line diff, never the diff map's guess."""
from __future__ import annotations

from codetortoise.cparse import norm_ws
from codetortoise.diffmap import DiffMap, FunctionChange
from codetortoise.facts.model import Facts, Function
from codetortoise.linediff import edits, touches
from codetortoise.vcs.model import ChangeSet


def _text(text: str, fn: Function) -> str:
    return norm_ws("\n".join(text.splitlines()[fn.start_line - 1:fn.end_line]))


def _by_name(fns: dict[str, Function]) -> dict[tuple[str, str], Function | None]:
    """(file, qualified name) -> the one function of that name in that file; None when there are several."""
    out: dict[tuple[str, str], Function | None] = {}
    for f in fns.values():
        k = (f.file, f.qualname)
        out[k] = None if k in out else f
    return out


def changed_functions(before: list[Facts], after: list[Facts], cs: ChangeSet) -> dict[str, str]:
    """usr -> "changed", "added" or "removed", for each parsed function of a changed file whose own lines an edit touches.
    A function's other version is the one with its usr, else the only function of its file and qualified name (clang on
    one side, tree-sitter on the other); one with no other version is added or removed; one whose text, whitespace aside,
    is the same in both versions is left out."""
    texts = {fc.local: (fc.before, fc.after) for fc in cs.files}
    fb = {f.usr: f for facts in before for f in facts.functions}
    fa = {f.usr: f for facts in after for f in facts.functions}
    named_b, named_a = _by_name(fb), _by_name(fa)
    pairs: list[tuple[Function | None, Function | None]] = []
    paired: set[str] = set()
    for u, f in fa.items():
        g = fb.get(u)
        if g is None and named_a.get((f.file, f.qualname)) is f:
            g = named_b.get((f.file, f.qualname))
        if g is not None:
            paired.add(g.usr)
        pairs.append((g, f))
    pairs += [(f, None) for u, f in fb.items() if u not in paired]

    spans: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {}   # (file, side) -> its edits, worked out once

    def hit(fn: Function | None, side: str) -> bool:
        if fn is None or fn.file not in texts:
            return False
        if (fn.file, side) not in spans:
            spans[(fn.file, side)] = edits(*texts[fn.file], side)
        return touches(spans[(fn.file, side)], fn.start_line, fn.end_line)

    out: dict[str, str] = {}
    for b, a in pairs:
        if not (hit(b, "before") or hit(a, "after")):
            continue
        if b is None:
            out[a.usr] = "added"
        elif a is None:
            out[b.usr] = "removed"
        elif _text(texts.get(b.file, ("", ""))[0], b) != _text(texts.get(a.file, ("", ""))[1], a):
            out[a.usr] = "changed"
    return out


def unparsed(dm: DiffMap, before: list[Facts], after: list[Facts]) -> list[FunctionChange]:
    """The diff map's function changes that no parsed function covers on their side: code this configuration's #ifs leave
    out, or a file no parse reached. Their edits reach no node of the impact model."""
    def spans(facts: list[Facts]) -> dict[str, list[tuple[int, int]]]:
        out: dict[str, list[tuple[int, int]]] = {}
        for fx in facts:
            for f in fx.functions:
                out.setdefault(f.file, []).append((f.start_line, f.end_line))
        return out
    sb, sa = spans(before), spans(after)

    def covered(file: str, lines: tuple[int, int], got: dict[str, list[tuple[int, int]]]) -> bool:
        return any(s <= lines[1] and lines[0] <= e for s, e in got.get(file, ()))
    return [c for c in dm.functions
            if not (covered(c.file, c.after_lines, sa) if c.after_lines else
                    c.before_lines is not None and covered(c.file, c.before_lines, sb))]
```

- [ ] **Step 5: Run the attribution tests, and the tests of `_opcodes`' users**

Run: `cd backend && .venv/bin/python -m pytest tests/test_attribution.py tests/test_board.py tests/test_pieces.py tests/test_causes.py -q`
Expected: PASS.

- [ ] **Step 6: Write the failing impact tests, and move every `build_impact` caller to the change set.**

Append to `backend/tests/test_impact.py`:

```python
SPLIT_C = """int first(void) { return 1; }
int alpha(int v)
{
#ifdef OPT_A
  if (v == 1) { return 2; }
  else
  {
#endif
    v++;
    return 0;
#ifdef OPT_A
  }
#endif
}
""" + "".join(f"int g{i}(int v) {{ if (v) {{ return v + {i}; }} return {i}; }}\n" for i in range(6))


def test_an_edit_inside_a_function_whose_braces_an_ifdef_splits_marks_that_function_and_no_other(tmp_path):
    from codetortoise.config import AnalysisConfig
    from codetortoise.facts.clang_extractor import TuRequest, extract_tu
    from codetortoise.impact import build_impact
    from codetortoise.tu_select import TuSelection
    from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange

    c = tmp_path / "a.c"
    c.write_text(SPLIT_C)
    p = str(c.resolve())
    after = SPLIT_C.replace("v++;", "v += 2;")
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                   files=[FileChange(depot="//d/a.c", local=p, action="edit", before=SPLIT_C, after=after)])
    before_f = [extract_tu(TuRequest(file=p, args=["-xc"], variant="before", unsaved={p: SPLIT_C}))]
    after_f = [extract_tu(TuRequest(file=p, args=["-xc"], variant="after", unsaved={p: after}))]
    im = build_impact(before_f, after_f, cs, TuSelection(selected=[p]), None, None, AnalysisConfig(module_min_files=1))
    assert [(im.nodes[n].label, im.nodes[n].status) for n in im.changed] == [("alpha", "changed")]


def test_an_edit_in_a_file_no_parse_reached_marks_no_same_named_function_elsewhere():
    from codetortoise.config import AnalysisConfig
    from codetortoise.facts.model import Facts, TuInfo
    from codetortoise.impact import build_impact
    from codetortoise.tu_select import TuSelection
    from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange

    beta = _fn("c:b.c@F@beta", "beta", "/w/b.c", 1, is_static=True)
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/a.c", local="/w/a.c", action="edit", before="int beta(void) { return 1; }\n",
                   after="int beta(void) { return 2; }\n")])
    im = build_impact([Facts(tu=TuInfo(file="/w/b.c", variant="before"), functions=[beta])],
                      [Facts(tu=TuInfo(file="/w/b.c", variant="after"), functions=[beta])], cs,
                      TuSelection(selected=["/w/b.c"]), None, None, AnalysisConfig(module_min_files=1))
    assert im.changed == []            # a.c's beta was never parsed, and b.c's beta is another function
```

Move the callers (the third argument becomes the change set):
- `backend/tests/conftest.py` (`analysed`): `im = build_impact(before, after, cs, sel, idx, layers, cfg)`.
- `backend/tests/test_impact.py`: in `test_heuristic_fan_in_is_capped` both calls pass `a.cs` instead of `a.dm`; in
  `test_the_impact_model_names_its_shared_sinks_and_the_blast_radius_skips_them` both calls pass `a.cs`; in
  `test_name_matches_over_the_cap_count_each_function_once` pass `a.cs`; in
  `test_calls_known_only_by_name_reach_the_function_of_that_name` replace the `dm = DiffMap(...)` value with
  `ChangeSet(cls=[], files=[])` (import `ChangeSet` from `codetortoise.vcs.model`; drop the now-unused `DiffMap` and
  `FunctionChange` imports) — that test checks call-edge resolution only.
- `backend/tests/test_detectors.py`: both `build_impact(before, after, dm, …)` calls pass `cs` (each test has `cs` in scope);
  `DetectorContext(…, dm, …)` stays as it is.

- [ ] **Step 7: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_impact.py -q`
Expected: FAIL — `AttributeError: 'ChangeSet' object has no attribute 'functions'`.

- [ ] **Step 8: Take step 1 of the impact model from attribution** in `backend/codetortoise/impact.py`:

```python
def build_impact(before: list[Facts], after: list[Facts], cs: ChangeSet, sel: TuSelection,
                 index: SymbolIndex | None, layers: LayerModel | None, cfg: AnalysisConfig,
                 marked: Collection[str] = ()) -> ImpactModel:
    fb = {f.usr: f for facts in before for f in facts.functions}
    fa = {f.usr: f for facts in after for f in facts.functions}
    resolve = _name_resolver({**fb, **fa})
    b = _Builder()

    # 1. changed functions: each parsed function whose own lines the change edits (attribution.py)
    changed_status = changed_functions(before, after, cs)
```

Delete the old step-1 loop, the `_overlaps` helper and the `DiffMap` import; import `changed_functions` from
`codetortoise.attribution` and `ChangeSet` from `codetortoise.vcs.model`. Nothing else in the file changes.

- [ ] **Step 9: Run the impact, detector and board tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_impact.py tests/test_detectors.py tests/test_board.py tests/test_stories.py tests/test_reading.py -q`
Expected: PASS.

- [ ] **Step 10: The follow-up round takes the changed set.**

In `backend/tests/test_tu_select_layers.py`, `test_follow_up_selects_tus_touching_fields_written_through_aliases`, change the
last line to:

```python
    assert field_follow_up({"c:@F@bump"}, facts_after, idx, cdb, sel, AnalysisConfig()) == [f"{root}/user.c"]
```

In `backend/codetortoise/tu_select.py`, `field_follow_up` becomes (import `Collection` from `collections.abc`):

```python
def field_follow_up(changed: Collection[str], after: list[Facts], index: SymbolIndex, cdb: CompileDb, sel: TuSelection,
                    cfg: AnalysisConfig) -> list[str]:
    """Second selection round, after clang facts exist for the changed TUs.

    Tree-sitter only sees `x->f = ...` writes; clang also sees writes through local aliases. For every field a
    changed function (a usr in `changed`, from attribution.changed_functions) writes, add not-yet-parsed TUs that
    reference a same-named member and can see the record's declaration, so its readers get precise facts. Bounded by
    the remaining TU budget.
    """
    written: dict[str, str] = {}
    for facts in after:
        for a in facts.fields:
            if a.fn in changed and a.mode != "read" and a.root_kind != "local":
                written.setdefault(a.field_name, a.record_file)
```

(the rest of the function, from `tus, have = …`, is unchanged).

In `backend/codetortoise/pipeline.py` `facts()`, replace the `extra = field_follow_up(ctx["dm"], …)` line with:

```python
        changed = changed_functions(before, after, ctx["cs"])
        extra = field_follow_up(set(changed), after, svc.index, svc.cdb, ctx["sel"], cfg.analysis)
```

and import `changed_functions` (and `unparsed`, used next) from `codetortoise.attribution`.

- [ ] **Step 11: The board counts and labels from the impact model.** Append to `backend/tests/test_board.py`:

```python
def test_the_about_line_counts_the_functions_the_impact_model_changed_not_the_diff_maps_guesses():
    from test_stories import _edit, _world

    from codetortoise.board import build_about
    from codetortoise.diffmap import FunctionChange
    c = _world([_edit("alpha", "src/a.c"), _edit("beta", "src/b.c")])
    c.dm.functions.append(FunctionChange(file="/w/src/a.c", depot="//d/w/src/a.c", qualname="ghost", name="ghost",
                                         kind="added", after_lines=(1, 9)))
    assert build_about(c).intent.startswith("2 function(s) changed in 2 file(s).")


def test_a_node_the_diff_map_thought_added_but_present_in_both_versions_is_modified():
    from codetortoise.board import _change_kind
    from codetortoise.diffmap import FunctionChange
    ch = FunctionChange(file="/w/a.c", depot="//d/a.c", qualname="alpha", name="alpha", kind="added", after_lines=(1, 9))
    assert _change_kind("changed", ch) == "modified"
    assert _change_kind("changed", ch.model_copy(update={"kind": "signature_changed"})) == "signature"
    assert _change_kind("added", None) == "added" and _change_kind("removed", ch) == "removed"
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_board.py -q -k "about_line or thought_added"` — Expected: FAIL.

Then in `backend/codetortoise/board.py`: in `build_about`, `fn_count = len(c.impact.changed)`; add near `_count`:

```python
def _change_kind(status: str, ch: FunctionChange | None) -> str:
    """A changed node's kind: added or removed as the impact model found it, else the diff map's signature change."""
    if status in ("added", "removed"):
        return status
    return "signature" if ch is not None and ch.kind == "signature_changed" else "modified"
```

and in the node block (`change = NodeChange(kind=kind_of.get(…), …)`, ~line 771) use
`change = NodeChange(kind=_change_kind(n.status, ch), add=add, rem=rem)`; delete `kind_of` if nothing else uses it; import
`FunctionChange` beside `DiffMap`. Re-run the two tests — Expected: PASS.

- [ ] **Step 12: The impact stage names mapped changes no parse covers.** Append to `backend/tests/test_pipeline.py`:

```python
class IfdefEdit:
    """One edit, inside a function an #ifdef this configuration never takes holds."""
    def __init__(self, path):
        self.path = path

    def load(self, cls):
        before = "int alpha(void) { return 1; }\n#ifdef NEVER_SET\nint beta(void) { return 2; }\n#endif\n"
        return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                         files=[FileChange(depot="//fixture/driver/uart.c", local=self.path, action="edit",
                                           before=before, after=before.replace("return 2;", "return 3;"))])


def test_a_changed_function_no_parse_covers_degrades_the_impact_stage_and_is_named(fx, tmp_path):
    svc = make_services(fx, tmp_path, source=IfdefEdit(str((fx.root / "driver" / "uart.c").resolve())))
    rid = svc.store.create_review("t", "owner", [1])
    run_review(rid, svc)
    assert stages(svc, rid)["impact"] == "degraded"
    msg = next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "impact")
    assert "1 changed function(s) in no parse" in msg and msg.endswith(": beta")
```

Run it — Expected: FAIL (`impact` is "ok"). Then `impact()` in `backend/codetortoise/pipeline.py` becomes:

```python
    def impact():
        im = build_impact(ctx["before"], ctx["after"], ctx["cs"], ctx["sel"], svc.index, ctx.get("layers"), cfg.analysis,
                          marked=sink_marks(store))
        ctx["impact"] = im
        store.put_blob(rid, "impact", im)
        msg = (f"{len(im.nodes)} node(s), {len(im.edges)} edge(s), blast {len(im.blast)}"
               + (f", {len(im.sinks)} shared sink(s)" if im.sinks else ""))
        missed = unparsed(ctx["dm"], ctx["before"], ctx["after"])
        if missed:
            names = ", ".join(c.qualname for c in missed[:5]) + (f" (+{len(missed) - 5} more)" if len(missed) > 5 else "")
            raise Degraded(f"{msg}; {len(missed)} changed function(s) in no parse (an #if this configuration leaves out, "
                           f"or a file no parse reached): {names}")
        return msg
```

Re-run — Expected: PASS.

- [ ] **Step 13: Full back-end suite and lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check codetortoise tests`
Expected: all pass (`test_full_review_without_llm_or_swarm` still sees `impact` "ok"), "All checks passed!".

- [ ] **Step 14: Commit**

```bash
git add backend/codetortoise/linediff.py backend/codetortoise/attribution.py backend/codetortoise/board.py \
        backend/codetortoise/impact.py backend/codetortoise/tu_select.py backend/codetortoise/pipeline.py \
        backend/tests/test_attribution.py backend/tests/conftest.py backend/tests/test_impact.py \
        backend/tests/test_detectors.py backend/tests/test_tu_select_layers.py backend/tests/test_board.py \
        backend/tests/test_pipeline.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "fix(impact): a function is changed when an edit touches its own parsed lines, not when the diff map's range overlaps it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 3: Find functions whose braces an `#if` splits; drop changes no edit touches

**Files:**
- Modify: `backend/codetortoise/cparse.py` (imports, `ParsedFile`, `parse_source` split into `parse_source` + `_collect`, new
  helpers before `_GUARD`)
- Modify: `backend/codetortoise/diffmap.py` (`FunctionChange.misread`, `DiffMap.flattened`, `_definitions`, `map_changes`)
- Modify: `backend/codetortoise/facts/treesitter_extractor.py` (one line)
- Modify: `backend/codetortoise/pipeline.py` (`diffmap()`)
- Test: `backend/tests/test_cparse.py`, `backend/tests/test_diffmap.py`, `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `linediff.edits`, `linediff.touches` (Task 2).
- Produces:
  - `cparse.flatten_preproc(text: str) -> str`
  - `cparse.parse_source(path: str, text: str, flatten: Literal["never", "auto", "always"] = "never") -> ParsedFile`
    (default unchanged: the symbol index keeps calling it without `flatten`)
  - `ParsedFile.flattened: bool`; `FunctionChange.misread: bool`; `DiffMap.flattened: list[str]`
  - `cparse._collect(tree, src, orig=None) -> ParsedFile` (the old walk; Task 4 edits its type branch)

- [ ] **Step 1: Write the failing parser tests** — append to `backend/tests/test_cparse.py` (import `flatten_preproc` beside
  `parse_source`; `HEAD`, `SPLIT` and `tail` are shared with test_diffmap.py and test_pipeline.py):

```python
HEAD = "int first(void) { return 1; }\n"
SPLIT = """int alpha(int v)
{
#ifdef OPT_A
  if (v == 1) { return 2; }
  else
  {
#endif
    v++;
    return 0;
#ifdef OPT_A
  }
#endif
}
"""


def tail(n):
    return "".join(f"int g{i}(int v) {{ if (v) {{ return v + {i}; }} return {i}; }}\n" for i in range(n))


def _spans(pf):
    return [(f.name, f.start_line, f.end_line) for f in pf.functions]


def test_flatten_keeps_one_consistent_branch_of_each_conditional_and_every_line_number():
    text = "\n".join(["a", "#ifdef A", "b", "#else", "c", "#endif", "#ifndef A", "d", "#else", "e", "#endif",
                      "#if 0", "x", "#else", "y", "#endif", "#if defined(B) && C", "z", "#elif 1", "w", "#endif",
                      "#define M \\", "  1", "#if X \\", "  > 2", "q", "#endif", "end"])
    assert flatten_preproc(text) == "\n".join(["a", "", "b", "", "", "", "", "", "", "e", "", "", "", "", "y", "", "",
                                               "z", "", "", "", "#define M \\", "  1", "", "", "q", "", "end"])


def test_a_function_whose_braces_an_ifdef_splits_is_found_on_the_flattened_text():
    text = HEAD + SPLIT + tail(6)
    assert "alpha" not in [f.name for f in parse_source("a.c", text).functions]     # the raw parse loses it
    pf = parse_source("a.c", text, flatten="auto")
    assert ("alpha", 2, 14) in _spans(pf) and pf.flattened


def test_a_flattened_function_is_hashed_on_the_original_text_so_an_edit_in_a_dropped_branch_counts():
    text = HEAD + SPLIT.replace("#ifdef OPT_A\n  }\n#endif", "#ifdef OPT_A\n  }\n#else\n    v = 0;\n#endif") + tail(6)
    a, b = parse_source("a.c", text, flatten="auto"), parse_source("a.c", text.replace("v = 0;", "v = 1;"), flatten="auto")
    ha, hb = {f.name: f.text_hash for f in a.functions}, {f.name: f.text_hash for f in b.functions}
    assert ha["alpha"] != hb["alpha"] and ha["g0"] == hb["g0"]


def test_complementary_conditions_are_read_one_way():
    text = "#ifdef OPT_B\nint beta(int v, int w)\n{\n#endif\n#ifndef OPT_B\nint beta(int v)\n{\n#endif\n  return v;\n}\n" + tail(6)
    assert ("beta", 2, 10) in _spans(parse_source("a.c", text, flatten="auto"))


def test_a_function_only_the_raw_parse_read_in_a_dropped_branch_is_kept():
    text = HEAD + SPLIT + tail(6) + "#ifdef OPT_C\nint gamma(void) { return 1; }\n#else\nint delta(void) { return 2; }\n#endif\n"
    names = [f.name for f in parse_source("a.c", text, flatten="auto").functions]
    assert {"alpha", "gamma", "delta"} <= set(names)


def test_a_statement_parsed_as_a_function_is_dropped():
    text = ("int pick(int v)\n{\n  if (v == 1) {\n    v = 2;\n  }\n#ifndef OPT_D\n  else if (v == 3) {\n    v = 4;\n  }\n"
            "#endif\n  return v;\n}\n")
    assert [f.name for f in parse_source("a.c", text).functions] == ["pick", "if"]
    pf = parse_source("a.c", text, flatten="auto")
    assert _spans(pf) == [("pick", 1, 12)] and pf.flattened


def test_an_untangled_file_is_not_flattened():
    text = "int first(void) { return 1; }\n#ifdef OPT_A\nint beta(void) { return 2; }\n#endif\n"
    pf = parse_source("a.c", text, flatten="auto")
    assert not pf.flattened and _spans(pf) == [("first", 1, 1), ("beta", 3, 3)]


def test_a_flattened_parse_of_crlf_and_non_ascii_text_keeps_spans_and_hashes():
    text = "int first(void) { return 1; } /* é */\r\n" + SPLIT.replace("\n", "\r\n") + tail(6).replace("\n", "\r\n")
    raw, flat = parse_source("a.c", text), parse_source("a.c", text, flatten="always")
    assert ("alpha", 2, 14) in _spans(flat)
    same = {f.name: f for f in raw.functions}
    assert len(same) == 7
    assert all((same[f.name].start_line, same[f.name].end_line, same[f.name].text_hash) ==
               (f.start_line, f.end_line, f.text_hash) for f in flat.functions if f.name in same)


def test_tree_sitter_facts_find_a_function_whose_braces_an_ifdef_splits():
    from codetortoise.facts.clang_extractor import TuRequest
    from codetortoise.facts.treesitter_extractor import extract_tu_treesitter
    text = HEAD + SPLIT + tail(6)
    facts = extract_tu_treesitter(TuRequest(file="/w/a.c", args=[], variant="after", unsaved={"/w/a.c": text}))
    assert ("alpha", 2, 14) in [(f.name, f.start_line, f.end_line) for f in facts.functions]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cparse.py -q`
Expected: FAIL — `ImportError: cannot import name 'flatten_preproc'`.

- [ ] **Step 3: Implement flattening in `backend/codetortoise/cparse.py`.**

Imports become:

```python
import bisect
import hashlib
import itertools
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Literal
```

`ParsedFile` gains, last: `flattened: bool = False     # functions found on flatten_preproc's text (parse_source)`.

Replace the head of `parse_source` (its signature and first four lines, down to `out = ParsedFile()`) with the block below; the
walk that followed (`stack = [(tree.root_node, (), None)]` … `return out`) becomes the body of `_collect`, unchanged except two
lines: the `TypeDef(…, norm_ws(_txt(src, node)))` text becomes `norm_ws(whole(node))`, and `full = norm_ws(_txt(src, node))`
becomes `full = norm_ws(whole(node))`.

```python
_STATEMENTS = frozenset({"if", "else", "for", "while", "do", "switch", "case", "return", "sizeof", "goto"})


def parse_source(path: str, text: str, flatten: Literal["never", "auto", "always"] = "never") -> ParsedFile:
    """Functions, declarations, types, macros, calls, includes and member references of one file.

    `flatten`: "auto" finds the functions (with their calls and member references) again on flatten_preproc's text
    when a preprocessor conditional tangles the parse (a "function" named like a statement, or an error on or across a
    conditional's line), and "always" does so regardless. Line numbers stay; a function's hash still comes from the
    original text, so an edit inside a dropped branch still changes it; a function the first parse read cleanly that
    the flattened text dropped (one in a branch not kept) stays; statement-named "functions" go."""
    parser = _parser_for(path)
    src = text.encode("utf-8", errors="replace")
    tree = parser.parse(src)
    out = _collect(tree, src)
    if flatten == "never" or (flatten == "auto" and not _tangled(tree, text, out)):
        return out
    flat_src = flatten_preproc(text).encode("utf-8", errors="replace")
    flat = _collect(parser.parse(flat_src), flat_src, src.split(b"\n"))
    fns = sorted((f for f in flat.functions if f.name not in _STATEMENTS), key=lambda f: (f.start_line, f.end_line))
    starts = [f.start_line for f in fns]
    reach = list(itertools.accumulate((f.end_line for f in fns), max))
    broken = {(n.start_point.row + 1, n.end_point.row + 1) for n in _nodes(tree)
              if n.type == "function_definition" and n.has_error}

    def covered(f: FuncDef) -> bool:
        k = bisect.bisect_right(starts, f.end_line) - 1      # the flattened functions starting before f ends,
        return k >= 0 and reach[k] >= f.start_line            # and whether one of them reaches f
    lost: dict[str, list[FuncDef]] = defaultdict(list)
    for f in out.functions:
        if (f.start_line, f.end_line) not in broken and f.name not in _STATEMENTS and not covered(f):
            lost[f.qualname].append(f)

    def kept(fn: str | None, line: int) -> bool:
        return any(f.start_line <= line <= f.end_line for f in lost.get(fn or "", ()))
    out.functions = sorted(fns + [f for fs in lost.values() for f in fs], key=lambda f: (f.start_line, f.end_line))
    out.calls = flat.calls + [c for c in out.calls if kept(c.caller, c.line)]
    out.members = flat.members + [m for m in out.members if kept(m.fn, m.line)]
    out.flattened = True
    return out


def _nodes(tree: ts.Tree):
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(n.children)


def _orig_text(lines: list[bytes], node: ts.Node) -> str:
    """A node's text in the original file, by its start and end points: a flattened text keeps every kept line's number
    and bytes, so the points match."""
    (r0, c0), (r1, c1) = node.start_point, node.end_point
    part = lines[r0][c0:c1] if r0 == r1 else b"\n".join([lines[r0][c0:], *lines[r0 + 1:r1], lines[r1][:c1]])
    return part.decode("utf-8", errors="replace")


def _collect(tree: ts.Tree, src: bytes, orig: list[bytes] | None = None) -> ParsedFile:
    """One walk of a parse. `orig`: the original file's lines, when `src` is a flattened text (function hashes and type
    texts come from it)."""
    def whole(node: ts.Node) -> str:
        return _orig_text(orig, node) if orig is not None else _txt(src, node)
    out = ParsedFile()
    # … the existing walk, from `stack = [(tree.root_node, (), None)]` to `return out` …
```

Add before `_GUARD = re.compile(…)`:

```python
_COND = re.compile(r"[ \t]*#[ \t]*(if|ifdef|ifndef|elif|elifdef|elifndef|else|endif)\b(.*)")
_DEFINE = re.compile(r"[ \t]*#[ \t]*(define|undef)[ \t]+(\w+)")
_DEFINED = re.compile(r"(!?)[ \t]*defined[ \t]*\(?[ \t]*(\w+)[ \t]*\)?")


def _tangled(tree: ts.Tree, text: str, pf: ParsedFile) -> bool:
    """Whether a preprocessor conditional tangles a parse: a "function" named like a statement, or a parse error or
    missing token on a conditional directive's line or spanning one."""
    if any(f.name in _STATEMENTS for f in pf.functions):
        return True
    rows = [i for i, line in enumerate(text.split("\n")) if _COND.match(line)]
    if not rows or not tree.root_node.has_error:
        return False
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "ERROR" or n.is_missing:
            k = bisect.bisect_left(rows, n.start_point.row)
            if k < len(rows) and rows[k] <= n.end_point.row:
                return True
        stack.extend(ch for ch in n.children if ch.has_error or ch.is_missing)
    return False


def _cond(expr: str, assumed: dict[str, bool]) -> bool:
    """One reading of an `#if`/`#elif` condition: literally 0 is false; `defined(X)` and `!defined(X)` read X the way
    an earlier test or `#define` settled it, and settle it when nothing has; anything else is true."""
    expr = expr.split("//")[0].split("/*")[0].strip()
    if expr == "0":
        return False
    m = _DEFINED.fullmatch(expr)
    if m is None:
        return True
    neg = m.group(1) == "!"
    return assumed.setdefault(m.group(2), not neg) != neg


def flatten_preproc(text: str) -> str:
    """The text as one consistent preprocessor reading leaves it, to find function boundaries in: each conditional
    keeps one branch (the first whose condition is not literally 0, a macro tested again, or `#define`d or `#undef`d on
    the way, reading the same way) and its other branches and its directives, continuation lines too, become empty
    lines. Other directives stay. The line count is unchanged, so every kept line keeps its number and its bytes."""
    assumed: dict[str, bool] = {}
    stack: list[list[bool]] = []          # per open conditional: [this branch kept, some branch kept]
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        active = all(f[0] for f in stack)
        m = _COND.match(lines[i])
        if m is None:
            d = _DEFINE.match(lines[i]) if active else None
            if d:
                assumed[d.group(2)] = d.group(1) == "define"
            out.append(lines[i] if active else "")
            i += 1
            continue
        kw, rest, n = m.group(1), m.group(2), 1
        while lines[i + n - 1].endswith("\\") and i + n < len(lines):
            rest += " " + lines[i + n]
            n += 1
        rest = rest.replace("\\", " ")
        name = rest.split()[0] if rest.split() else ""
        if kw in ("elifdef", "elifndef"):
            kw, rest = "elif", f"{'!' if kw == 'elifndef' else ''}defined({name})"
        if kw in ("if", "ifdef", "ifndef"):
            if not active:
                keep = False
            elif kw == "if":
                keep = _cond(rest, assumed)
            else:
                keep = assumed.setdefault(name, kw == "ifdef") == (kw == "ifdef")
            stack.append([keep, keep])
        elif kw in ("elif", "else") and stack:
            top = stack[-1]
            top[0] = all(f[0] for f in stack[:-1]) and not top[1] and (kw == "else" or _cond(rest, assumed))
            top[1] = top[1] or top[0]
        elif kw == "endif" and stack:
            stack.pop()
        out += [""] * n
        i += n
    return "\n".join(out)
```

In `backend/codetortoise/facts/treesitter_extractor.py`: `pf = parse_source(file, text, flatten="auto")`.

- [ ] **Step 4: Run the parser tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cparse.py tests/test_symbols.py tests/test_index_scale.py -q`
Expected: PASS (the index still parses with the default, unflattened).

- [ ] **Step 5: Write the failing diff-map tests** — add `from test_cparse import HEAD, SPLIT, tail` to the imports at the top
  of `backend/tests/test_diffmap.py` (ruff rejects a mid-file import), then append:

```python
def _cs(before, after, local="/w/a.c"):
    return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                     files=[FileChange(depot="//d/a.c", local=local, action="edit", before=before, after=after)])


def _raw_parser(monkeypatch):
    """The diff map with no flattening: what tree-sitter alone makes of each version."""
    from codetortoise import cparse, diffmap
    monkeypatch.setattr(diffmap, "parse_source", lambda path, text, flatten="never": cparse.parse_source(path, text))


def test_an_edit_inside_a_function_whose_braces_an_ifdef_splits_is_mapped_to_it():
    before = HEAD + SPLIT + tail(6)
    dm = map_changes(_cs(before, before.replace("v++;", "v += 2;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("alpha", "body_modified")] and dm.flattened == ["/w/a.c"]


def test_an_edit_inside_a_dropped_branch_still_changes_its_function():
    before = HEAD + SPLIT.replace("#ifdef OPT_A\n  }\n#endif", "#ifdef OPT_A\n  }\n#else\n    v = 0;\n#endif") + tail(6)
    dm = map_changes(_cs(before, before.replace("v = 0;", "v = 1;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("alpha", "body_modified")]


def test_a_function_the_parser_loses_in_one_version_with_no_edit_in_it_is_not_a_change(monkeypatch):
    from codetortoise import cparse
    before, after = HEAD + SPLIT + tail(5), HEAD + SPLIT + tail(6)
    assert "alpha" in {f.name for f in cparse.parse_source("a.c", before).functions}          # found here …
    assert "alpha" not in {f.name for f in cparse.parse_source("a.c", after).functions}       # … lost here
    _raw_parser(monkeypatch)
    assert [(f.qualname, f.kind) for f in map_changes(_cs(before, after)).functions] == [("g5", "added")]


def test_an_added_function_the_old_text_defines_where_the_parser_found_none_is_marked_misread(monkeypatch):
    before = HEAD + SPLIT + tail(6)
    after = HEAD + SPLIT.replace("v++;", "v += 2;") + tail(5)
    _raw_parser(monkeypatch)
    dm = map_changes(_cs(before, after))
    assert [(f.qualname, f.kind, f.misread) for f in dm.functions] == [("alpha", "added", True), ("g5", "removed", False)]


def test_a_genuinely_added_function_is_not_misread_even_beside_its_old_prototype():
    before = "int first(void) { return 1; }\nstatic int alpha(int a,\n                 int b);\n"
    added = before + "static int alpha(int a,\n                 int b)\n{\n  return a + b;\n}\n"
    dm = map_changes(_cs(before, added))
    assert [(f.qualname, f.kind, f.misread) for f in dm.functions] == [("alpha", "added", False)]
```

- [ ] **Step 6: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_diffmap.py -q`
Expected: FAIL — `alpha` is not mapped, `flattened` / `misread` do not exist, `alpha` is "removed" in the lost case.

- [ ] **Step 7: Implement in `backend/codetortoise/diffmap.py`.**

Imports: add `import re`, and `from codetortoise.linediff import edits, touches`.

```python
class FunctionChange(BaseModel):
    …
    written_members: list[str] = Field(default_factory=list)
    misread: bool = False     # added or removed, yet the other version's text defines it where the parser found nothing


class DiffMap(BaseModel):
    functions: list[FunctionChange] = Field(default_factory=list)
    types: list[TypeChange] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    flattened: list[str] = Field(default_factory=list)   # files whose functions were found on one branch of each #if
```

```python
_TO_BODY = re.compile(r"[;{]")


def _definitions(text: str, name: str) -> int:
    """How many times the text defines `name` at the left margin: a type (or nothing) then the name and "(" at the start
    of a line, then "{" before any ";" (a call is indented; a prototype reaches ";" first)."""
    pat = re.compile(rf"^(?:[A-Za-z_][\w \t*&:<>,]*[ \t*&])?{re.escape(name)}[ \t]*\(", re.M)
    n = 0
    for m in pat.finditer(text):
        nxt = _TO_BODY.search(text, m.end())
        n += nxt is not None and nxt.group() == "{"
    return n
```

In `map_changes`, the start of the per-file loop becomes:

```python
        dm.changed_files.append(fc.local)
        b = parse_source(fc.local, fc.before, flatten="auto")
        a = parse_source(fc.local, fc.after, flatten="auto")
        if b.flattened != a.flattened:             # read both versions the same way
            b = b if b.flattened else parse_source(fc.local, fc.before, flatten="always")
            a = a if a.flattened else parse_source(fc.local, fc.after, flatten="always")
        if a.flattened:
            dm.flattened.append(fc.local)
        bf, af = _keyed(b.functions), _keyed(a.functions)
        eb, ea = edits(fc.before, fc.after, "before"), edits(fc.before, fc.after, "after")
        for key in sorted(set(bf) | set(af)):
            fb, fa = bf.get(key), af.get(key)
            if fb is not None and fa is not None and fb.text_hash == fa.text_hash:
                continue
            if not ((fb is not None and touches(eb, fb.start_line, fb.end_line))
                    or (fa is not None and touches(ea, fa.start_line, fa.end_line))):
                continue                           # no edit in its own lines: the parser read the versions differently
```

and, after `ref = fa or fb`:

```python
            misread = False
            if fb is None or fa is None:
                other, parsed = (fc.before, b) if fb is None else (fc.after, a)
                misread = _definitions(other, ref.name) > sum(1 for f in parsed.functions if f.name == ref.name)
```

passing `misread=misread` to the `FunctionChange(…)`. The rest of `map_changes` is unchanged.

- [ ] **Step 8: Run the diff-map tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_diffmap.py tests/test_tu_select_layers.py -q`
Expected: PASS.

- [ ] **Step 9: The diff-map stage says what it did and names suspect changes.** Append to `backend/tests/test_pipeline.py`:

```python
class SplitEdit:
    """A change whose old version tree-sitter cannot read one function of (an #ifdef splits its braces)."""
    def __init__(self, path):
        self.path = path

    def load(self, cls):
        from test_cparse import HEAD, SPLIT, tail
        return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                         files=[FileChange(depot="//fixture/driver/uart.c", local=self.path, action="edit",
                                           before=HEAD + SPLIT + tail(6),
                                           after=HEAD + SPLIT.replace("v++;", "v += 2;") + tail(5))])


def test_the_diffmap_stage_says_which_files_it_flattened_and_names_functions_it_may_have_misread(fx, tmp_path, monkeypatch):
    from codetortoise import cparse, diffmap
    path = str((fx.root / "driver" / "uart.c").resolve())
    svc = make_services(fx, tmp_path, source=SplitEdit(path))
    rid = svc.store.create_review("t", "owner", [1])
    run_review(rid, svc)
    msg = next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "diffmap")
    assert stages(svc, rid)["diffmap"] == "ok" and msg.endswith("; 1 file(s) read with one branch of each #if to find their functions")
    monkeypatch.setattr(diffmap, "parse_source", lambda path, text, flatten="never": cparse.parse_source(path, text))
    rid = svc.store.create_review("t", "owner", [1])
    run_review(rid, svc)
    msg = next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "diffmap")
    assert stages(svc, rid)["diffmap"] == "degraded"
    assert msg.endswith("; 1 function(s) the parser may have misread, shown as added or removed: alpha")
```

Run it — Expected: FAIL. Then `diffmap()` in `backend/codetortoise/pipeline.py` becomes:

```python
    def diffmap():
        dm = map_changes(ctx["cs"])
        ctx["dm"] = dm
        store.put_blob(rid, "diffmap", dm)
        msg = f"{len(dm.functions)} function change(s), {len(dm.types)} type/macro/decl change(s)"
        if dm.flattened:
            msg += f"; {len(dm.flattened)} file(s) read with one branch of each #if to find their functions"
        misread = [c for c in dm.functions if c.misread]
        if misread:
            names = ", ".join(c.qualname for c in misread[:5]) + (f" (+{len(misread) - 5} more)" if len(misread) > 5 else "")
            raise Degraded(f"{msg}; {len(misread)} function(s) the parser may have misread, shown as added or removed: "
                           f"{names}")
        return msg
```

Re-run — Expected: PASS.

- [ ] **Step 10: Full back-end suite and lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check codetortoise tests`
Expected: all pass, "All checks passed!".

- [ ] **Step 11: Commit**

```bash
git add backend/codetortoise/cparse.py backend/codetortoise/diffmap.py backend/codetortoise/facts/treesitter_extractor.py \
        backend/codetortoise/pipeline.py backend/tests/test_cparse.py backend/tests/test_diffmap.py backend/tests/test_pipeline.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "fix(diffmap): find functions whose braces an #if splits, and drop changes no edit touches

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 4: A story of declarations only shows them

**Files:**
- Modify: `backend/codetortoise/cparse.py` (`TypeDef.fields`, `_declared`, `_members`, the type branch of `_collect`)
- Modify: `backend/codetortoise/diffmap.py` (`TypeChange` fields; `_named` replaces `_diff_named`)
- Modify: `backend/codetortoise/reading.py` (`ContractRow.kind`, `WhereDecl`, `WhereFile.decls`, `_decl_changes`, `_decl_row`,
  `contract_rows`, `where`, `build_reading`)
- Modify: `frontend/src/reading/types.ts`, `frontend/src/workspace/StoryTabs.tsx` (`WhereDirs`)
- Create: `frontend/e2e/declaration-stories.spec.ts`
- Test: `backend/tests/test_cparse.py`, `backend/tests/test_diffmap.py`, `backend/tests/test_reading.py`

**Interfaces:**
- Consumes: `_collect` (Task 3), `map_changes`' loop (Task 3).
- Produces: `TypeDef.fields: tuple[str, ...]`; `TypeChange.line: int | None`, `.before: str`, `.after: str`,
  `.fields_added: list[str]`, `.fields_removed: list[str]`; `ContractRow.kind` gains `"declaration"`;
  `WhereDecl(name: str, line: int | None)`; `WhereFile.decls: list[WhereDecl]`;
  `contract_rows(story, x, pieces: PieceSet | None = None)`, `where(story, x, pieces: PieceSet | None = None)`.
- Ruling carried in this task: declaration rows and Where entries appear only for a story with no function nodes (a story
  that has functions keeps reading as it does now).

- [ ] **Step 1: Write the failing back-end tests.**

`backend/tests/test_cparse.py`:

```python
def test_types_list_their_fields_and_enums_their_enumerators():
    pf = parse_source("t.c", "struct Widget { int a, b; char *name; void (*cb)(int); unsigned flag : 1; };\n"
                             "enum Mode { MODE_OFF, MODE_ON = 2 };\n")
    assert {t.name: t.fields for t in pf.types} == {"Widget": ("a", "b", "name", "cb", "flag"),
                                                    "Mode": ("MODE_OFF", "MODE_ON")}
```

`backend/tests/test_diffmap.py`:

```python
def test_type_decl_and_macro_changes_carry_both_texts_their_line_and_field_changes():
    before = "#define LIMIT 4\nstruct Widget { int a; int b; };\nint alpha(void);\n"
    after = "#define LIMIT 8\n\nstruct Widget { int a; int c; };\nint alpha(int v);\n"
    got = {t.name: t for t in map_changes(_cs(before, after, local="/w/w.h")).types}
    w = got["Widget"]
    assert (w.kind, w.line, w.fields_added, w.fields_removed) == ("type_changed", 3, ["c"], ["b"])
    assert (w.before, w.after) == ("struct Widget { int a; int b; }", "struct Widget { int a; int c; }")
    assert (got["alpha"].kind, got["alpha"].before, got["alpha"].after) == ("decl_changed", "int alpha(void);",
                                                                             "int alpha(int v);")
    assert (got["LIMIT"].kind, got["LIMIT"].line, got["LIMIT"].after) == ("macro_changed", 1, "#define LIMIT 8")
```

`backend/tests/test_reading.py` (add `FileChange` from `codetortoise.vcs.model`, `TypeChange` from `codetortoise.diffmap`,
`Piece, PieceSet` from `codetortoise.pieces` to the imports):

```python
def _declarations(c):
    """inc/w.h's changed LIMIT and Widget, one declarations piece P1 holding them."""
    h = f"{W}/inc/w.h"
    c.cs.files.append(FileChange(depot="//d" + h, local=h, action="edit", before="struct Widget { int a; int b; };\n",
                                 after="#define LIMIT 8\n\nstruct Widget { int a; int c; };\n"))
    c.dm.types += [TypeChange(file=h, depot="//d" + h, name="Widget", kind="type_changed", line=3,
                              before="struct Widget { int a; int b; }", after="struct Widget { int a; int c; }",
                              fields_added=["c"], fields_removed=["b"]),
                   TypeChange(file=h, depot="//d" + h, name="LIMIT", kind="macro_added", line=1, after="#define LIMIT 8")]
    return PieceSet(pieces=[Piece(id="P1", kind="declarations", targets=["unknown"], files=[h], names=["LIMIT", "Widget"])])


def test_a_story_of_declarations_only_shows_them_under_before_after_and_where():
    c = _world([_edit("alpha", "src/a.c")])
    ps = _declarations(c)
    story = Story(id="S1", kind="other", title="t", summary="s", nodes=[], pieces=["P1"], cls=[1])
    x = _x(c)
    assert [(r.kind, r.text, r.before, r.after, r.added, r.removed) for r in contract_rows(story, x, ps)] == [
        ("declaration", "`LIMIT` macro added", "", "#define LIMIT 8", [], []),
        ("declaration", "`Widget` now has `c`; no longer has `b`", "struct Widget { int a; int b; }",
         "struct Widget { int a; int c; }", ["c"], ["b"])]
    (wf,) = where(story, x, ps)
    assert (wf.path, wf.depot, wf.functions, [(d.name, d.line) for d in wf.decls]) == (
        "inc/w.h", "//d/w/inc/w.h", [], [("LIMIT", 1), ("Widget", 3)])


def test_a_story_with_functions_keeps_declaration_pieces_out_of_before_after_and_where():
    c = _world([_edit("alpha", "src/a.c")])
    ps = _declarations(c)
    story = Story(id="S1", kind="other", title="t", summary="s", nodes=["N1"], pieces=["P1"], cls=[1])
    x = _x(c)
    assert all(r.kind != "declaration" for r in contract_rows(story, x, ps))
    assert [(f.path, f.decls) for f in where(story, x, ps)] == [("src/a.c", [])]


def test_blobs_stored_before_this_change_still_load():
    from codetortoise.diffmap import DiffMap
    from codetortoise.tu_select import TuSelection
    dm = DiffMap.model_validate({"functions": [{"file": "/w/a.c", "depot": "//d/a.c", "qualname": "a", "name": "a",
                                                "kind": "added"}],
                                 "types": [{"file": "/w/a.h", "depot": "//d/a.h", "name": "W", "kind": "type_changed"}],
                                 "changed_files": ["/w/a.c"]})
    assert dm.flattened == [] and not dm.functions[0].misread
    assert (dm.types[0].line, dm.types[0].before, dm.types[0].after, dm.types[0].fields_added) == (None, "", "", [])
    assert TuSelection.model_validate({"selected": ["/w/a.c"]}).ts_only == []
    assert WhereFile.model_validate({"path": "a.c", "functions": []}).decls == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cparse.py tests/test_diffmap.py tests/test_reading.py -q -k "fields or texts or declaration or before_this_change"`
Expected: FAIL (no `fields`, no `line`/`before`/`after` on `TypeChange`, `contract_rows` takes 2 arguments).

- [ ] **Step 3: Type fields in `backend/codetortoise/cparse.py`.** `TypeDef` gains, last: `fields: tuple[str, ...] = ()`. Add:

```python
def _declared(node: ts.Node | None) -> ts.Node | None:
    """The identifier a declarator names, through pointers, arrays, functions and parentheses."""
    while node is not None and node.type not in ("field_identifier", "identifier"):
        inner = node.child_by_field_name("declarator")
        if inner is None and node.type == "parenthesized_declarator":
            inner = next(iter(node.named_children), None)
        node = inner
    return node


def _members(src: bytes, body: ts.Node) -> tuple[str, ...]:
    """The names a type's body declares: an enum's enumerators, or a struct's, union's or class's fields (not methods)."""
    if body.type == "enumerator_list":
        return tuple(_txt(src, ch.child_by_field_name("name")) for ch in body.children if ch.type == "enumerator")
    out = []
    for ch in body.children:
        if ch.type != "field_declaration":
            continue
        for d in ch.children_by_field_name("declarator"):
            inner = d.child_by_field_name("declarator") if d.type == "function_declarator" else None
            if inner is not None and inner.type in ("field_identifier", "identifier"):
                continue                       # a method's declaration
            n = _declared(d)
            if n is not None:
                out.append(_txt(src, n))
    return tuple(out)
```

and in `_collect`'s type branch pass `_members(src, body)` as the `TypeDef`'s last argument.

- [ ] **Step 4: Declaration texts in `backend/codetortoise/diffmap.py`.** `TypeChange` gains:

```python
class TypeChange(BaseModel):
    file: str
    depot: str
    name: str
    kind: TypeChangeKind
    line: int | None = None           # new side (old side for a removed one)
    before: str = ""                  # its text in each version, whitespace collapsed ("" where it does not exist)
    after: str = ""
    fields_added: list[str] = Field(default_factory=list)     # a changed type's fields or enumerators
    fields_removed: list[str] = Field(default_factory=list)
```

Replace `_diff_named` with:

```python
def _named(before: dict[str, tuple[int, str, tuple[str, ...]]], after: dict[str, tuple[int, str, tuple[str, ...]]],
           prefix: str, fc: FileChange) -> list[TypeChange]:
    """Added, removed and changed names of one kind (types, declarations or macros): name -> (line, text, fields)."""
    out = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if b is not None and a is not None and b[1] == a[1]:
            continue
        kind = f"{prefix}_added" if b is None else f"{prefix}_removed" if a is None else f"{prefix}_changed"
        both = a is not None and b is not None
        out.append(TypeChange(file=fc.local, depot=fc.depot, name=name, kind=kind, line=(a or b)[0],
                              before=b[1] if b else "", after=a[1] if a else "",
                              fields_added=[f for f in a[2] if f not in b[2]] if both else [],
                              fields_removed=[f for f in b[2] if f not in a[2]] if both else []))
    return out
```

and the end of `map_changes`' loop becomes (import `FileChange` beside `ChangeSet`):

```python
        dm.types += _named({t.name: (t.start_line, t.text, t.fields) for t in b.types if t.name},
                           {t.name: (t.start_line, t.text, t.fields) for t in a.types if t.name}, "type", fc)
        dm.types += _named({d.qualname: (d.line, d.text, ()) for d in b.decls},
                           {d.qualname: (d.line, d.text, ()) for d in a.decls}, "decl", fc)
        dm.types += _named({m.name: (m.line, m.text, ()) for m in b.macros},
                           {m.name: (m.line, m.text, ()) for m in a.macros}, "macro", fc)
```

- [ ] **Step 5: Declaration rows and Where entries in `backend/codetortoise/reading.py`.**

`ContractRow.kind` becomes `Literal["signature", "returns", "fields", "repeated", "body", "declaration"]`. Add beside
`WhereFn`:

```python
class WhereDecl(BaseModel):
    name: str
    line: int | None = None           # new side (old side for a removed one)
```

and to `WhereFile`, last: `decls: list[WhereDecl] = Field(default_factory=list)   # a declarations-only story's declarations`.

Add after `_story_fns` (import `TypeChange` from `codetortoise.diffmap`):

```python
_SHORT = 300                          # a declaration's texts are shown when both are at most this long
_DECL_NOUN = {"type": "", "decl": " declaration", "macro": " macro"}


def _decl_changes(story: Story, x: _Ctx, pieces: PieceSet | None) -> list[TypeChange]:
    """The changed declarations of a story with no function nodes, from its declaration pieces, by file and line."""
    if pieces is None or _story_fns(story, x):
        return []
    by_id = {p.id: p for p in pieces.pieces}
    want = {(f, n) for pid in story.pieces if (p := by_id.get(pid)) is not None and p.kind == "declarations"
            for f in p.files for n in p.names}
    return sorted((t for t in x.c.dm.types if (t.file, t.name) in want), key=lambda t: (t.file, t.line or 0, t.name))


def _decl_row(t: TypeChange) -> ContractRow:
    what, how = t.kind.split("_")
    if what == "type" and how == "changed" and (t.fields_added or t.fields_removed):
        parts = ([f"now has {', '.join(f'`{f}`' for f in t.fields_added)}"] if t.fields_added else []) + \
                ([f"no longer has {', '.join(f'`{f}`' for f in t.fields_removed)}"] if t.fields_removed else [])
        text = f"`{t.name}` " + "; ".join(parts)
    else:
        text = f"`{t.name}`{_DECL_NOUN[what]} {how}"
    before, after = (t.before, t.after) if max(len(t.before), len(t.after)) <= _SHORT else ("", "")
    mark = list(_differ(before, after)[2:]) if before and after else []
    return ContractRow(kind="declaration", text=text, before=before, after=after, mark=mark,
                       added=list(t.fields_added), removed=list(t.fields_removed))
```

`contract_rows` gains the `pieces` parameter and starts:

```python
def contract_rows(story: Story, x: _Ctx, pieces: PieceSet | None = None) -> list[ContractRow]:
    """Signatures (one row per repeated signature edit), return values, field writes, a mechanical story's repeated
    edit, then the functions changed only inside their body; a story with no functions, its changed declarations."""
    decls = _decl_changes(story, x, pieces)
    if decls:
        return [_decl_row(t) for t in decls]
    fns = _story_fns(story, x)
    # … the rest of the function as it is …
```

`where(story: Story, x: _Ctx, pieces: PieceSet | None = None)`: before the final sort, add

```python
    for t in _decl_changes(story, x, pieces):
        fc = x.texts.get(t.file)
        files.setdefault(t.file, WhereFile(path=rel_path(x, t.file), depot=fc.depot if fc else None)).decls.append(
            WhereDecl(name=t.name, line=t.line))
```

In `build_reading`, call `where(s, x, pieces)` and `contract_rows(s, x, pieces)`.

- [ ] **Step 6: Run the back-end tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cparse.py tests/test_diffmap.py tests/test_reading.py tests/test_pieces.py -q`
Expected: PASS.

- [ ] **Step 7: Write the failing e2e test** — create `frontend/e2e/declaration-stories.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

/** A story made only of declarations (a changed header no changed function defines or calls) shows them under Before → after
 * and Where instead of two empty sections. The server's story S1 is rewritten into such a story. */
test("a declarations-only story lists its declarations under Before → after and Where", async ({ page }) => {
  await page.route("**/api/reviews/*/stories/S1", async (route) => {
    let res: import("@playwright/test").APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    j.reading.contracts = [{ kind: "declaration", text: "`Widget` now has `c`; no longer has `b`", node: null,
                             before: "struct Widget { int a; int b; }", after: "struct Widget { int a; int c; }",
                             mark: [23, 24], added: ["c"], removed: ["b"], nodes: [] }];
    j.reading.where = [{ path: "inc/w.h", depot: "//fixture/inc/w.h", functions: [], decls: [{ name: "Widget", line: 3 }],
                         cls: [101] }];
    await route.fulfill({ response: res, json: j });
  });
  const base = await startReview(page);
  await page.goto(`${base}/s/S1?sec=contracts`);
  const contracts = page.getByRole("region", { name: "Before → after" });
  await expect(contracts).toContainText("Widget now has c; no longer has b");
  await expect(contracts).toContainText("struct Widget { int a; int c; }");
  await page.goto(`${base}/s/S1?sec=where`);
  await expect(page.getByRole("link", { name: "Open Widget in inc/w.h at line 3" })).toBeVisible();
});
```

Run (from `frontend/`): `npm run build && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/declaration-stories.spec.ts --retries=2`
Expected: FAIL — no "Open Widget …" link (Where lists functions only).

- [ ] **Step 8: Show them.** In `frontend/src/reading/types.ts`: `ContractRow.kind` gains `| "declaration"`; add

```ts
export interface WhereDecl { name: string; line: number | null }
```

and to `WhereFile`:

```ts
  /** A declarations-only story's changed declarations (types, prototypes, macros); absent on a reading stored before them. */
  decls?: WhereDecl[];
```

In `frontend/src/workspace/StoryTabs.tsx`, `WhereDirs`' list becomes the functions followed by the declarations:

```tsx
            <ul>{file.functions.map((f) => {
              const label = `Open ${f.label} in ${file.path}${f.line ? ` at line ${f.line}` : ""}`;
              return (
                <li key={f.node}>
                  {file.depot ? <Link className="mono" to={ws.link(ws.opened({ file: file.depot, line: f.line }))} title={label}
                                      aria-label={label}>{f.label}</Link> : <span className="mono" title={f.label}>{f.label}</span>}
                  <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
                  {showCl && f.cl !== null && <span className="ws-chip">CL {f.cl}</span>}
                </li>
              );
            })}{(file.decls ?? []).map((d) => {
              const label = `Open ${d.name} in ${file.path}${d.line ? ` at line ${d.line}` : ""}`;
              return (
                <li key={`decl:${d.name}`}>
                  {file.depot ? <Link className="mono" to={ws.link(ws.opened({ file: file.depot, line: d.line }))} title={label}
                                      aria-label={label}>{d.name}</Link> : <span className="mono" title={d.name}>{d.name}</span>}
                </li>
              );
            })}</ul>
```

Check every other reader of `WhereFile.functions` in `frontend/src` (`grep -rn "\.functions" frontend/src`) copes with a file
whose `functions` is empty (no `functions[0]` without a guard); fix any that does not.

- [ ] **Step 9: Run the front-end checks and the e2e test**

Run (from `frontend/`): `npx vitest run && npx tsc --noEmit && npx tsc -p e2e --noEmit && npm run build && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/declaration-stories.spec.ts e2e/long-text.spec.ts --retries=2; rm -rf ../.pwtmp`
Expected: all pass.

- [ ] **Step 10: Full back-end suite and lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check codetortoise tests`
Expected: all pass, "All checks passed!".

- [ ] **Step 11: Commit**

```bash
git add backend/codetortoise/cparse.py backend/codetortoise/diffmap.py backend/codetortoise/reading.py \
        backend/tests/test_cparse.py backend/tests/test_diffmap.py backend/tests/test_reading.py \
        frontend/src/reading/types.ts frontend/src/workspace/StoryTabs.tsx frontend/e2e/declaration-stories.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): a story of declarations only shows them under Before → after and Where

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 5: A declaration goes with the story that defines what it declares

**Files:**
- Modify: `backend/codetortoise/pieces.py` (`LinkType`, `_links`)
- Modify: `backend/codetortoise/grouping.py` (`rules_plan`)
- Modify: `backend/codetortoise/llm/stories.py` (`STORY_RULES_VERSION`, `JOINING`, `RULES` step 3)
- Test: `backend/tests/test_pieces.py`, `backend/tests/test_stories.py`

**Interfaces:**
- Consumes: declaration pieces (`Piece.kind == "declarations"`, `.names`, `.files`) — unchanged by earlier tasks.
- Produces: `LinkType` value `"defines"` — a declarations piece to a code piece holding a changed function whose qualified name
  the piece declares; count = such functions.

- [ ] **Step 1: Write the failing tests.**

`backend/tests/test_pieces.py`:

```python
def test_a_declarations_piece_is_linked_to_the_piece_defining_its_function_apart_from_those_calling_it():
    c = _world([("alpha", "src/alpha.c", ["a = 0;"], ["a = 1;"]),
                ("caller_one", "src/use/one.c", ["alpha();"], ["alpha(); x();"]),
                ("caller_two", "src/use/two.c", ["alpha();"], ["alpha(); y();"])],
               calls=[("caller_one", "caller_two")])
    h = f"{W}/inc/alpha.h"
    c.cs.files.append(FileChange(depot="//d" + h, local=h, action="edit", before="int alpha(void);\n",
                                 after="int alpha(int v);\n"))
    c.dm.types.append(TypeChange(file=h, depot="//d" + h, name="alpha", kind="decl_changed"))
    ps = _pieces(c)
    (d,) = [p for p in ps.pieces if p.kind == "declarations"]

    def piece_of(label):
        return ps.node_piece[next(n for n, x in c.impact.nodes.items() if x.label == label)]
    assert ("defines", 1) in {(lk.type, lk.count) for lk in ps.links if {lk.a, lk.b} == {d.id, piece_of("alpha")}}
    assert not [lk for lk in ps.links if lk.type == "defines" and piece_of("caller_one") in (lk.a, lk.b)]
```

`backend/tests/test_stories.py`:

```python
def test_a_header_declaring_a_function_joins_the_story_defining_it_even_when_another_uses_it_more():
    from codetortoise.diffmap import TypeChange
    c = _world([("alpha", "src/alpha.c", ["a = 0;"], ["a = 1;"]),
                ("caller_one", "src/use/one.c", ["alpha();"], ["alpha(); x();"]),
                ("caller_two", "src/use/two.c", ["alpha();"], ["alpha(); y();"])],
               calls=[("caller_one", "caller_two")])
    h = f"{W}/inc/alpha.h"
    c.cs.files.append(FileChange(depot="//d" + h, local=h, action="edit", before="int alpha(void);\n",
                                 after="int alpha(int v);\n"))
    c.dm.types.append(TypeChange(file=h, depot="//d" + h, name="alpha", kind="decl_changed"))
    ss, _ = build_stories(c)
    home = next(s for s in ss.stories if "N1" in s.nodes)        # alpha's story
    assert len(home.pieces) == 2 and home.placements[-1].reason == "declaration_used"
    assert all(len(s.pieces) == 1 for s in ss.stories if s.id != home.id)
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pieces.py tests/test_stories.py -q -k "defining"`
Expected: FAIL — no `defines` link; the declaration joins the callers' story (it uses `alpha` in two functions, alpha's piece in
one).

- [ ] **Step 3: Implement.**

`backend/codetortoise/pieces.py`: `LinkType = Literal["call", "field", "sub", "uses", "defines", "name"]`; in `_links`, the
declarations loop becomes:

```python
    for d in (p for p in pieces if p.kind == "declarations"):
        words = [re.compile(rf"\b{re.escape(n.split()[-1])}\b") for n in d.names]
        declared = set(d.names)
        inc = includers(d.files[0]) if includers else None
        for p in pieces:
            if p.kind == "declarations" or (inc is not None and not (set(p.files) & inc) and d.files[0] not in p.files):
                continue
            link(d.id, p.id, "uses", sum(1 for n in p.nodes if any(w.search(texts[n]) for w in words)))
            link(d.id, p.id, "defines", sum(1 for n in p.nodes if im.nodes[n].kind == "function" and x.label(n) in declared))
```

`backend/codetortoise/grouping.py`, `rules_plan` — the declarations loop becomes (docstring: "a declaration piece joins the
group defining what it declares, else the group using its changes most"):

```python
    for d in (p for p in pieces if p.kind == "declarations"):
        weight: dict[str, dict[str, int]] = {"defines": defaultdict(int), "uses": defaultdict(int)}
        for lk in ps.links_of(d.id):
            other = lk.b if lk.a == d.id else lk.a
            if lk.type in weight and other in by_id and by_id[other].kind in code:
                weight[lk.type][find(other)] += lk.count
        typ = "defines" if weight["defines"] else "uses"
        got = weight[typ]
        if got:
            into = max(got, key=lambda g: (got[g], -rank[g]))
            groups[into].append(d.id)
            user = max((o for o in groups[into] if o in by_id and by_id[o].kind in code),
                       key=lambda o: (sum(lk.count for lk in ps.links_of(d.id) if lk.type == typ and o in (lk.a, lk.b)),
                                      -rank[o]))
            why[d.id] = ("declaration_used", [user])
        else:
            groups[d.id].append(d.id)
```

`backend/codetortoise/llm/stories.py`: `STORY_RULES_VERSION = 3`; `JOINING = ("call", "field", "sub", "uses", "defines")`;
`RULES` step 3's last sentence becomes "A declaration piece goes with the story that defines what it declares (a `defines`
link), else with the story that uses its changes most." (keep the line-continuation style of the string).

- [ ] **Step 4: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pieces.py tests/test_stories.py tests/test_tier1_stories.py tests/test_tier1_review.py -q`
Expected: PASS.

- [ ] **Step 5: Full back-end suite and lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check codetortoise tests`
Expected: all pass, "All checks passed!".

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/pieces.py backend/codetortoise/grouping.py backend/codetortoise/llm/stories.py \
        backend/tests/test_pieces.py backend/tests/test_stories.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(stories): a declaration goes with the story that defines what it declares

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

## Out of scope (noted, not fixed here)

- Anonymous `typedef struct { … } name_t;` types have no name in the parse, so their changes make no declaration piece.
- Calls inside a dropped `#else` branch of a flattened function are not in tree-sitter's facts (clang sees one configuration
  too).
