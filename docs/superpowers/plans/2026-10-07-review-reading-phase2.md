# Review Reading (Phase 2): CLs as a Sequence and a Reading Plan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In a review whose CLs edit the same file, every changed line says which CL wrote it and when a later CL replaced an earlier one's lines; each story says the order to read its CLs in; and each reader keeps a private reading plan (Read ticks on stories and checks, with progress) that a re-run clears.

**Architecture:** A new backend module `sequence.py` walks each file several CLs of the review edit, CL by CL with `difflib.SequenceMatcher`, and records who wrote each final line, what it replaced, who removed each base line, which later CL rewrote an earlier one's lines, and gaps where a CL outside the review came between. The reading stage stores the result as a `lines` blob beside `reading`, adds the review's rewrites and gaps to `Reading`, and gives each story its CL order and rewrites. `GET /files` attaches each multi-CL file's lines; the browser only draws them: chips in the combined diff, greyed rows in one CL's diff, Where grouped by CL, Rewrites on the CL page. A new table `read_ticks` holds each reader's own ticks; Looks fine also ticks the check for the one who says it, and `run_review` clears every tick. The browser adds Mark as read, a Read box per To check row and progress in the header, rail and overview.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, SQLite, pytest, ruff; React 19, TypeScript (strict), react-router 7, Vite, vitest, Playwright. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-07-review-reading-phase2-design.md`

**Base:** branch `review-reading-2` at `5c26df8` (the spec is its latest commit; main's phase 1 is below it). Everything stays on `review-reading-2`; nothing reaches `main` until the owner decides.

**Provenance:** every code block below was run before this plan was written. The tasks were then replayed in order on a fresh tree from `5c26df8` by a script that applied each step's blocks and ran each step's command. Every Expected line is that run's output. Each task's tests failed before its implementation and passed after it, and the suite stayed green after every task. A second script built a tree from this document's blocks alone; that tree is byte-identical to the validated one. New files are given in full. Changes to existing files are unified diffs against the previous task's state; apply them with `git apply` or by hand. Under parallel load an end-to-end test may time out or lose its browser on its first run. If one does, rerun it alone with `--last-failed`; if it fails again, it is a real failure.

## Global Constraints

- **Rewrites are information, not checks (§2, owner's choice A):** a rewrite is shown in the diff, the story's Where tile and the CL page. It never adds a To check row and never raises the headline.
- **Filtering stays per file (§2, owner's choice A):** the existing per-file CL picker stays; a chip switches its file to that CL. No review-wide CL lens.
- **Ticks are private (§6.1, owner's choice A):** a tick belongs to one signed-in user and one review; nobody else sees it. "Looks fine" stays the shared verdict. Stories are ticked by hand.
- **A re-run clears every reader's ticks (§6.5, owner's choice C).**
- **The server works out who wrote each line, once per run (§2, owner's choice 1);** the browser only draws it.
- **The walk (§4.2):** Python `difflib.SequenceMatcher` on lines, `autojunk=False`; CLs in number order; a CL whose before is not the previous after is a gap, and the lines it brought carry no CL.
- **Who wrote each line (§4.3):** a `+` row at new line `n` looks up `wrote[n-1]`, a `−` row at old line `o` looks up `removed[o-1]`; a row whose lookup is None gets no tag. Only files more than one CL of the review touches are walked.
- **Store (§7.4):** table `read_ticks(review_id, user, kind, key, at)`, primary key `(review_id, user, kind, key)`, kind `story` or `check`, `CREATE TABLE IF NOT EXISTS`.
- **API (§7.5):** `GET /api/reviews/{rid}/ticks` → `{stories: [...], checks: [...]}` for the signed-in user (empty lists for a review without a reading); `PUT` and `DELETE /api/reviews/{rid}/ticks/{kind}/{key:path}` — an unknown key is 404 "That story or check is not in this review's reading.", a kind other than `story` or `check` is 422; `POST …/checks/{key}/mark` also sets the marking user's check tick; `GET …/files` gives each multi-CL file `lines`.
- **Words (§5, §6):** chips read "CL 102", "CL 103 · rewrites CL 101", "rewritten in CL 103"; on a phone "102". Where: "CL 101 · 2 files", "also CL 103", "Read CL 101, then CL 103", "CL 103 rewrites 5 lines CL 101 added in `uart_send`". CL page: "rewrites lines CL 101 added: `uart_send` (5 lines)", "lines it added are rewritten by CL 103: `uart_send` (5 lines)", "`logger.c`: a CL outside this review changed it between CL 103 and CL 105". Story: "Mark as read", "✓ Read · Mark unread". Progress: "7 of 12 stories read · 18 of 30 checks", a thread's "2 of 3", a thread card's "2 of 3 read", "You've read every story".
- **Not changed (§5.5):** To check, the headline, the overview's tiles and the rail's order.
- **Old reviews (§6.5):** a review without a reading has no reading plan: no buttons, boxes or counts. A reading stored before this plan has no `cl_order`, `rewrites`, `gaps` or `cls`; the browser treats them as absent.
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).
- **End-to-end runs:** build the frontend first (`npm run build` writes `backend/codetortoise/web/static`). Playwright starts the fixture servers itself: 8799 (rules only); 8798 with the fake model on 8797; 8796 for the large fixture; 8795 with the fake model as the strong model. If Chromium crashes ("Target crashed"), the browser's temp directory is full: point `TMPDIR` at a directory on disk.

## Review Focus

These are the conditions the spec implies that are most likely to bite a real user, most likely first. Each is pinned by a test in the task that owns the code.

1. **A CL outside the review changed the file between two review CLs.** The lines it brought must carry no chip, and the CL page must say so instead of crediting them to the later review CL. Pinned by `test_a_change_from_outside_the_review_between_two_cls_is_a_gap_and_its_lines_carry_no_cl` and the fixture test of a review of 103 and 105 (Tasks 1 and 3), and the e2e test "a CL page names its rewrites both ways, and a CL outside the review between two of its CLs" (Task 7).
2. **A reading stored before this plan** (no `lines` blob, no `cl_order`, `rewrites`, `gaps` or `cls`). Its files must open without chips, its Where must keep the old layout, its CL page must have no Rewrites section. The fields are optional in `reading/types.ts` and every reader of them falls back (`?? []`, `?.`) in Tasks 6–7; the existing phase-1 e2e suite, which runs in every frontend task's suite step, covers the pages.
3. **Two people reading the same review.** One reader's ticks must never show for another, while Looks fine (shared) does. Pinned by `test_read_ticks_are_each_readers_own_looks_fine_ticks_the_check_and_a_rerun_clears_them` (Task 5) and the e2e test "a check's Read box is the reader's own; Looks fine ticks it for the one who says it" (Task 8).
4. **Check keys hold `/`, `|` and `::`** (paths, the key separator, C++ names). Ticking one must reach the right check: the route is `{key:path}`, the browser encodes keys with `encodeURIComponent`, and the Task 5 API test ticks a real check key. Pinned by `test_read_ticks_are_each_readers_own_looks_fine_ticks_the_check_and_a_rerun_clears_them` (Task 5) and the Read-box e2e test (Task 8).
5. **Marking the last unread story.** Mark as read must not loop back to a read story; with every story read it goes to the overview, which says "You've read every story". Pinned by the `nextUnread` unit test (Task 8) and the e2e test "progress shows in the header, the rail and the overview; the last story read leads to the overview" (Task 9).

## Spec Coverage

| Spec | Where |
|---|---|
| §4.1 input, §4.2 the walk, §4.3 `FileLines` | Task 1 |
| §4.3 `Rewrite` rows | Task 2 |
| §8 fixture CL 105 | Task 3 |
| §4.4 a story's CL order, §7.2 models, §7.3 pipeline (`lines` blob), §7.5 `files` gains `lines` | Task 4 |
| §6.1 what is ticked, §6.5 re-run clears, §7.3 `run_review` clears, §7.4 store, §7.5 ticks API and mark ticks | Task 5 |
| §5.1 combined diff chips, §5.2 one CL's greyed rows, §5.5 phone chips | Task 6 |
| §5.3 Where tile, §5.4 CL page | Task 7 |
| §6.2 Mark as read, §6.3 Read box, §7.6 `plan.ts` and `useReview` ticks | Task 8 |
| §6.4 progress (header, rail, overview), §6.2 "You've read every story" | Task 9 |
| §8 testing: Python units (Tasks 1, 2, 4, 5), fixture (Task 3), vitest (Tasks 6–8), Playwright (Tasks 6–9) | all |
| §9 out of scope | nothing built |

## Decisions the spec left open (or that differ from it)

- **`FileLines` carries two more fields than §4.3 lists:** `local` (the file's workspace path, to find its functions in the after facts) and `replaced` — `(a, m, by, final line)` for each line CL `by` replaced, so a rewrite's `line` and `function` are those of the replacement each replaced line got. One CL replacing lines in two functions gives one `Rewrite` row per function.
- **A story's `cl_order` comes from the lines inside its changed functions, not from `Story.cls`** (§4.4 says `Story.cls`). `Story.cls` is file-level: in the fixture the `logger_level` story would read "Read CL 103, then CL 104, then CL 105" though only CL 104 wrote it. `cl_order` is the sorted CLs that wrote, replaced or removed a line inside the story's functions (falling back to `Story.cls` when no file was walked). Rewrites only go from an earlier CL to a later one, so CL-number order still never contradicts them.
- **`WhereFile` gains `cls`:** the story's CLs that edit the file, in order, so Where can group without a second lookup.
- **The `lines` blob is stored as dumped dicts** (`model_dump()`): the blob store is JSON.
- **`GET /ticks` for a review without a reading** answers empty lists rather than 404, so the browser loads ticks the same way for every review and shows nothing when there is no reading.
- **Where groups by CL only when the story has more than one CL.** A one-CL story keeps phase 1's Where (its header already names its CL).
- **A Read box is checked once the server has the tick** (no optimistic update): a failed tick shows its error and leaves the box as it was.
- **There is no way to "open" the header on a phone**, so the header's progress is hidden there and the overview's progress line (shown on every screen) carries it.
- **A read story's rail link adds " (read)" to its accessible name;** the ✓ itself is hidden from screen readers.

### Task 1: Who wrote each line

Spec §4.1–§4.3, §4.5. `walk` follows one file through its CLs in number order. Every line carries an origin (the base, or the CL and its line in that CL's after text) and `over`, the earlier review CL whose lines its insertion replaced. Before each CL, a before text that differs from the previous after is a gap: it is applied with no CL, so its lines carry none, and the gap is recorded. Then the CL's own diff moves the origins along: kept lines keep theirs, inserted lines get the CL's, a deleted line from an earlier review CL is a rewrite of it (also kept in `replaced` with where its replacement stands now), and a deleted base line is removed by the CL.

**Files:**
- Test: `backend/tests/test_sequence.py`
- Create: `backend/codetortoise/sequence.py`

**Interfaces:**
- Consumes: `vcs.model.FileChange` (`depot`, `local`, `before`, `after`, `per_cl: list[PerClText(cl, before, after)]`).
- Produces: `sequence.Gap(file: str, after_cl: int, before_cl: int)`;
  `sequence.FileLines(depot, local="", wrote: list[int|None], over: list[int|None], removed: list[int|None], rewritten: dict[int, dict[int, int]], replaced: list[tuple[int, int, int, int|None]], gaps: list[Gap])`;
  `sequence.walk(fc: FileChange) -> FileLines`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_sequence.py` (new file):

```python
"""Who wrote each line of a file several CLs edit (spec 2026-10-07-review-reading-phase2 §4)."""
from codetortoise.sequence import Gap, walk
from codetortoise.vcs.model import FileChange, PerClText


def _file(*texts, cls=None, gap=None):
    """texts: the base, then each CL's after text; CLs 101, 102, … unless `cls` names them. `gap`: (index, text) — that
    CL's before text differs from the previous CL's after (an outside CL changed the file in between)."""
    cls = cls or [101 + i for i in range(len(texts) - 1)]
    lines = ["\n".join(t) + "\n" if t else "" for t in texts]
    steps = []
    for i, cl in enumerate(cls):
        before = lines[i]
        if gap and gap[0] == i:
            before = "\n".join(gap[1]) + "\n"
        steps.append(PerClText(cl=cl, before=before, after=lines[i + 1]))
    return FileChange(depot="//d/f.c", local="/w/f.c", action="edit", before=lines[0], after=lines[-1], per_cl=steps)


def test_each_final_line_knows_the_cl_that_wrote_it_and_unchanged_lines_none():
    fl = walk(_file(["a", "b"], ["a", "x", "b"], ["a", "x", "b", "y"]))
    assert fl.wrote == [None, 101, None, 102]
    assert fl.over == [None, None, None, None] and fl.removed == [None, None]
    assert fl.rewritten == {} and fl.gaps == [] and fl.depot == "//d/f.c" and fl.local == "/w/f.c"


def test_a_later_cl_rewriting_an_earlier_cls_lines_records_the_rewrite_and_what_the_new_lines_replaced():
    fl = walk(_file(["a", "b"], ["a", "x1", "x2", "b"], ["a", "z", "b"]))
    assert fl.wrote == [None, 102, None]
    assert fl.over == [None, 101, None]                      # CL 102's `z` replaced CL 101's lines
    assert fl.rewritten == {101: {2: 102, 3: 102}}           # CL 101's after-text lines 2 and 3
    assert fl.replaced == [(101, 2, 102, 2), (101, 3, 102, 2)]   # each replaced line and where its replacement is now


def test_a_later_cl_deleting_an_earlier_cls_lines_is_a_rewrite_with_nothing_in_their_place():
    fl = walk(_file(["a", "b"], ["a", "x", "b"], ["a", "b"]))
    assert fl.wrote == [None, None] and fl.over == [None, None]
    assert fl.rewritten == {101: {2: 102}} and fl.replaced == [(101, 2, 102, None)]


def test_a_base_line_removed_records_the_cl_that_removed_it():
    fl = walk(_file(["a", "b", "c"], ["a", "c"], ["a", "c", "d"]))
    assert fl.removed == [None, 101, None] and fl.wrote == [None, None, 102] and fl.rewritten == {}


def test_a_change_from_outside_the_review_between_two_cls_is_a_gap_and_its_lines_carry_no_cl():
    # CL 101 adds x; an outside CL adds o; CL 103 adds y
    fl = walk(_file(["a"], ["a", "x"], ["a", "x", "o", "y"], cls=[101, 103], gap=(1, ["a", "x", "o"])))
    assert fl.wrote == [None, 101, None, 103]
    assert fl.gaps == [Gap(file="//d/f.c", after_cl=101, before_cl=103)]


def test_a_rewrite_of_a_rewrite_names_each_cl_it_replaced():
    fl = walk(_file(["a"], ["a", "x"], ["a", "y"], ["a", "z"]))
    assert fl.wrote == [None, 103] and fl.over == [None, 102]
    assert fl.rewritten == {101: {2: 102}, 102: {2: 103}}


def test_a_file_one_cl_touches_is_walked_the_same_way():
    fl = walk(_file(["a"], ["a", "x"]))
    assert fl.wrote == [None, 101] and fl.removed == [None]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_sequence.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.sequence'`

- [ ] **Step 3: Implement**

`backend/codetortoise/sequence.py` (new file):

```python
"""CLs as a sequence (spec 2026-10-07-review-reading-phase2 §4): for a file several CLs of a review edit, which CL wrote
each line of its final text, which CL removed each base line, and which later CL rewrote lines an earlier one added."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from codetortoise.vcs.model import FileChange


class Gap(BaseModel):
    """A CL outside the review changed `file` between review CLs `after_cl` and `before_cl`."""
    file: str
    after_cl: int
    before_cl: int


class FileLines(BaseModel):
    depot: str
    local: str = ""
    wrote: list[int | None] = Field(default_factory=list)      # per final line: the CL that wrote it
    over: list[int | None] = Field(default_factory=list)       # per final line: the earlier CL whose lines it replaced
    removed: list[int | None] = Field(default_factory=list)    # per base line: the CL that removed it
    rewritten: dict[int, dict[int, int]] = Field(default_factory=dict)  # [cl a][its after line m] = the CL replacing it
    replaced: list[tuple[int, int, int, int | None]] = Field(default_factory=list)  # (a, m, by, final line in its place)
    gaps: list[Gap] = Field(default_factory=list)


@dataclass
class _Line:
    id: int
    origin: tuple[int, int] | None      # (CL, line in that CL's after text); None: the base or outside the review
    over: int | None
    base: int | None                    # its line in the base text, while it is still the base's


def _split(text: str) -> list[str]:
    return text.splitlines()


def walk(fc: FileChange) -> FileLines:
    """Walk the file's CLs in order (§4.2): each CL's diff from its before to its after moves the lines' origins along;
    a CL whose before is not the previous after had an outside change first (a gap, whose lines carry no CL)."""
    cur = _split(fc.before)
    ids = iter(range(1 << 62))
    attrs = [_Line(next(ids), None, None, i) for i in range(len(cur))]
    removed: list[int | None] = [None] * len(cur)
    rewritten: dict[int, dict[int, int]] = defaultdict(dict)
    events: list[tuple[int, int, int, int | None]] = []      # (a, m, by, id of the first line put in their place)
    gaps: list[Gap] = []
    prev: int | None = None

    def apply(new: list[str], cl: int | None) -> None:
        nonlocal cur, attrs
        out: list[_Line] = []
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, cur, new, autojunk=False).get_opcodes():
            if tag == "equal":
                out += attrs[i1:i2]
                continue
            gone = attrs[i1:i2]
            put = [_Line(next(ids), (cl, j + 1) if cl is not None else None, None, None) for j in range(j1, j2)]
            if cl is not None:
                earlier = [g.origin[0] for g in gone if g.origin is not None]
                for p in put:
                    p.over = max(earlier) if earlier else None
                for g in gone:
                    if g.origin is not None:
                        rewritten[g.origin[0]][g.origin[1]] = cl
                        events.append((g.origin[0], g.origin[1], cl, put[0].id if put else None))
                    elif g.base is not None:
                        removed[g.base] = cl
            out += put
        cur, attrs = new, out

    for st in sorted(fc.per_cl, key=lambda s: s.cl):
        before = _split(st.before)
        if before != cur:
            if prev is not None:
                gaps.append(Gap(file=fc.depot, after_cl=prev, before_cl=st.cl))
            apply(before, None)
        apply(_split(st.after), st.cl)
        prev = st.cl
    at = {a.id: i + 1 for i, a in enumerate(attrs)}
    return FileLines(depot=fc.depot, local=fc.local, wrote=[a.origin[0] if a.origin else None for a in attrs],
                     over=[a.over for a in attrs], removed=removed, rewritten=dict(rewritten),
                     replaced=[(a, m, by, at.get(put) if put is not None else None) for a, m, by, put in events], gaps=gaps)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_sequence.py -q`
Expected: PASS: `7 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `629 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_sequence.py backend/codetortoise/sequence.py
git commit -m "feat(sequence): who wrote each line of a file several CLs edit — each final line's CL and what it replaced, each base line's remover, each CL's lines a later CL rewrote, and gaps from CLs outside the review"
```

### Task 2: The review's rewrites

Spec §4.3. `rewrites` turns every file's `replaced` events into one `Rewrite` row per file, CL pair and function: `lines` counts the earlier CL's lines replaced or deleted, `line` is the first final line written in their place, and `function` is the innermost after-facts function holding it (None when nothing stands there). `file_lines` walks only the files more than one CL of the change set touches.

**Files:**
- Test: `backend/tests/test_sequence.py`
- Modify: `backend/codetortoise/sequence.py`

**Interfaces:**
- Consumes: `walk`, `FileLines` (Task 1); `facts.model.Function` (`file`, `start_line`, `end_line`, `qualname`); `vcs.model.ChangeSet` (`files`).
- Produces: `sequence.Rewrite(by: int, of: int, file: str, function: str|None, lines: int, line: int|None)`;
  `sequence.rewrites(lines: dict[str, FileLines], fns: list[Function]) -> list[Rewrite]` (sorted by file, of, by, line, function);
  `sequence.file_lines(cs: ChangeSet) -> dict[str, FileLines]` (depot path → lines).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_sequence.py` (diff):

```diff
diff --git a/backend/tests/test_sequence.py b/backend/tests/test_sequence.py
index 0b9354a..4184efd 100644
--- a/backend/tests/test_sequence.py
+++ b/backend/tests/test_sequence.py
@@ -1,5 +1,6 @@
 """Who wrote each line of a file several CLs edit (spec 2026-10-07-review-reading-phase2 §4)."""
-from codetortoise.sequence import Gap, walk
+from codetortoise.facts.model import Function
+from codetortoise.sequence import Gap, Rewrite, rewrites, walk
 from codetortoise.vcs.model import FileChange, PerClText
 
 
@@ -59,3 +60,26 @@ def test_a_rewrite_of_a_rewrite_names_each_cl_it_replaced():
 def test_a_file_one_cl_touches_is_walked_the_same_way():
     fl = walk(_file(["a"], ["a", "x"]))
     assert fl.wrote == [None, 101] and fl.removed == [None]
+
+
+def _fn(name, start, end, file="/w/f.c"):
+    return Function(usr=f"c:@F@{name}", qualname=name, name=name, signature=f"void {name}(void)", return_type="void",
+                    file=file, start_line=start, end_line=end)
+
+
+def test_a_rewrite_row_counts_the_lines_names_the_function_its_replacement_is_in_and_where():
+    fl = walk(_file(["a", "b"], ["a", "x1", "x2", "b"], ["a", "z", "b"]))
+    assert rewrites({"//d/f.c": fl}, [_fn("outer", 1, 3), _fn("init", 2, 2)]) == [
+        Rewrite(by=102, of=101, file="//d/f.c", function="init", lines=2, line=2)]   # the innermost function
+
+
+def test_lines_deleted_with_nothing_in_their_place_are_a_rewrite_with_no_function():
+    fl = walk(_file(["a", "b"], ["a", "x", "b"], ["a", "b"]))
+    assert rewrites({"//d/f.c": fl}, [_fn("init", 1, 2)]) == [
+        Rewrite(by=102, of=101, file="//d/f.c", function=None, lines=1, line=None)]
+
+
+def test_one_rewrite_row_per_function_ordered_by_file_cl_and_line():
+    fl = walk(_file(["a", "b", "c", "d"], ["a", "x", "b", "c", "y", "d"], ["a", "X", "b", "c", "Y", "d"]))
+    rows = rewrites({"//d/f.c": fl}, [_fn("one", 1, 3), _fn("two", 4, 6)])
+    assert [(r.function, r.lines, r.line) for r in rows] == [("one", 1, 2), ("two", 1, 5)]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_sequence.py -q`
Expected: FAIL: `1 error`; the first error is `ImportError: cannot import name 'Rewrite' from 'codetortoise.sequence' (backend/codetortoise/sequence.py)`

- [ ] **Step 3: Implement**

`backend/codetortoise/sequence.py` (diff):

```diff
diff --git a/backend/codetortoise/sequence.py b/backend/codetortoise/sequence.py
index c271ef9..f9b55a9 100644
--- a/backend/codetortoise/sequence.py
+++ b/backend/codetortoise/sequence.py
@@ -8,6 +8,7 @@ from difflib import SequenceMatcher
 
 from pydantic import BaseModel, Field
 
+from codetortoise.facts.model import Function
 from codetortoise.vcs.model import FileChange
 
 
@@ -18,6 +19,17 @@ class Gap(BaseModel):
     before_cl: int
 
 
+class Rewrite(BaseModel):
+    """CL `by` replaced or deleted `lines` lines CL `of` added to `file` (a depot path); `line` is the first final line
+    written in their place and `function` the function holding it (None when nothing of `by` stands there)."""
+    by: int
+    of: int
+    file: str
+    function: str | None = None
+    lines: int
+    line: int | None = None
+
+
 class FileLines(BaseModel):
     depot: str
     local: str = ""
@@ -87,3 +99,24 @@ def walk(fc: FileChange) -> FileLines:
     return FileLines(depot=fc.depot, local=fc.local, wrote=[a.origin[0] if a.origin else None for a in attrs],
                      over=[a.over for a in attrs], removed=removed, rewritten=dict(rewritten),
                      replaced=[(a, m, by, at.get(put) if put is not None else None) for a, m, by, put in events], gaps=gaps)
+
+
+def _holding(fns: list[Function], local: str, line: int | None) -> str | None:
+    """The innermost function of `local` whose lines hold `line`."""
+    if line is None:
+        return None
+    inside = [f for f in fns if f.file == local and f.start_line <= line <= f.end_line]
+    return min(inside, key=lambda f: f.end_line - f.start_line).qualname if inside else None
+
+
+def rewrites(lines: dict[str, FileLines], fns: list[Function]) -> list[Rewrite]:
+    """The review's rewrites (§4.3), one per file, CL pair and function; `fns` are the after facts' functions."""
+    rows: dict[tuple[str, int, int, str | None], Rewrite] = {}
+    for depot, fl in lines.items():
+        for a, _, by, line in fl.replaced:
+            fn = _holding(fns, fl.local, line)
+            r = rows.setdefault((depot, by, a, fn), Rewrite(by=by, of=a, file=depot, function=fn, lines=0, line=line))
+            r.lines += 1
+            if line is not None and (r.line is None or line < r.line):
+                r.line = line
+    return sorted(rows.values(), key=lambda r: (r.file, r.of, r.by, r.line or 0, r.function or ""))
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_sequence.py -q`
Expected: PASS: `10 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `632 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_sequence.py backend/codetortoise/sequence.py
git commit -m "feat(sequence): a review's rewrites — one row per file, CL pair and function, counting the lines replaced and naming where their replacement stands"
```

### Task 3: Fixture CL 105

Spec §8 (fixture). CL 105 ("logger: start at log level 2") changes the line CL 103 added to `logger_init` (`lg->level = 1;` → `lg->level = 2;`). A review of CLs 103–105 then has a rewrite, and a review of 103 and 105 has a gap (CL 104 between them). Reviews of 101–104 are unchanged.

**Files:**
- Test: `backend/tests/test_sequence.py`
- Modify: `backend/codetortoise/fixture.py`
- Create: `backend/codetortoise/fixtures/cfixture/cl105/service/logger.c`

**Interfaces:**
- Consumes: `walk` (Task 1); the `fx_source` test fixture.
- Produces: fixture CL 105 (`backend/codetortoise/fixtures/cfixture/cl105/service/logger.c`, `fixture.CL_DESCRIPTIONS[105]`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_sequence.py` (diff):

```diff
diff --git a/backend/tests/test_sequence.py b/backend/tests/test_sequence.py
index 4184efd..4574c2d 100644
--- a/backend/tests/test_sequence.py
+++ b/backend/tests/test_sequence.py
@@ -83,3 +83,13 @@ def test_one_rewrite_row_per_function_ordered_by_file_cl_and_line():
     fl = walk(_file(["a", "b", "c", "d"], ["a", "x", "b", "c", "y", "d"], ["a", "X", "b", "c", "Y", "d"]))
     rows = rewrites({"//d/f.c": fl}, [_fn("one", 1, 3), _fn("two", 4, 6)])
     assert [(r.function, r.lines, r.line) for r in rows] == [("one", 1, 2), ("two", 1, 5)]
+
+
+def test_the_fixtures_cl_105_rewrites_the_line_cl_103_added_and_skipping_cl_104_leaves_a_gap(fx_source):
+    logger = "//fixture/service/logger.c"
+    fc = next(f for f in fx_source.load([103, 104, 105]).files if f.depot == logger)
+    fl = walk(fc)
+    assert fl.rewritten == {103: {7: 105}} and fl.gaps == []
+    assert fl.wrote[6] == 105 and fl.over[6] == 103 and fl.wrote.count(104) == 5
+    fc = next(f for f in fx_source.load([103, 105]).files if f.depot == logger)
+    assert walk(fc).gaps == [Gap(file=logger, after_cl=103, before_cl=105)]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_sequence.py -q`
Expected: FAIL: `1 failed, 10 passed`; the first error is `codetortoise.vcs.source.SourceError: CL 105 not found`

- [ ] **Step 3: Implement**

`backend/codetortoise/fixture.py` (diff):

```diff
diff --git a/backend/codetortoise/fixture.py b/backend/codetortoise/fixture.py
index d23044f..0692bbb 100644
--- a/backend/codetortoise/fixture.py
+++ b/backend/codetortoise/fixture.py
@@ -13,6 +13,7 @@ CL_DESCRIPTIONS = {
     102: "uart: add flags field; hal_write takes unsigned reg",
     103: "logger: start at log level 1",
     104: "logger: read the level back; engine: step by three",
+    105: "logger: start at log level 2",
 }
 
 
```

`backend/codetortoise/fixtures/cfixture/cl105/service/logger.c` (new file):

```
#include "service/logger.h"

int logger_init(struct Logger *lg, struct Uart *u)
{
    lg->uart = u;
    lg->dropped = 0;
    lg->level = 2;
    return 0;
}

int logger_write(struct Logger *lg, const char *msg, int len)
{
    if (uart_send(lg->uart, msg, len) != 0) {
        lg->dropped++;
        return -1;
    }
    return 0;
}

void logger_flush(struct Logger *lg)
{
    uart_send(lg->uart, "\n", 1);
}

int logger_level(const struct Logger *lg)
{
    return lg->level;
}
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_sequence.py -q`
Expected: PASS: `11 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `633 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_sequence.py backend/codetortoise/fixture.py backend/codetortoise/fixtures/cfixture/cl105/service/logger.c
git commit -m "test(fixture): CL 105 rewrites the line CL 103 added in logger_init, so a review of 103–105 has a rewrite and one of 103 and 105 a gap"
```

### Task 4: The reading carries the sequence

Spec §4.4, §7.2, §7.3, §7.5 (`files`). The reading stage walks the change set once (`file_lines`) and stores the result as the `lines` blob together with `reading` and `reading_head`; a run that builds no reading drops it with them. `Reading` gains the review's `rewrites` and `gaps`. Each story's `cl_order` is the CLs that wrote, replaced or removed a line inside its changed functions; each Where file gets the story's CLs that edit it (`cls`); each story gets the rewrites in its functions, or in its files when the rewrite has no function. `GET /files` gives each multi-CL file its `lines`.

**Files:**
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_web.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/reading.py`
- Modify: `backend/codetortoise/sequence.py`
- Modify: `backend/codetortoise/web/app.py`

**Interfaces:**
- Consumes: `file_lines`, `rewrites`, `FileLines`, `Rewrite`, `Gap` (Tasks 1–2); fixture CL 105 (Task 3).
- Produces: `reading.WhereFile.cls: list[int]`; `reading.StoryReading.cl_order: list[int]`, `.rewrites: list[Rewrite]`; `reading.Reading.rewrites: list[Rewrite]`, `.gaps: list[Gap]`;
  `build_reading(..., lines: dict[str, FileLines] | None = None)`; blob `lines` (depot path → `FileLines.model_dump()`);
  `GET /api/reviews/{rid}/files` items gain `lines` (multi-CL files only).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pipeline.py` (diff):

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 3b30deb..3cdbac8 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -549,3 +549,23 @@ def test_a_rerun_that_builds_no_reading_leaves_none_behind(fx, tmp_path, monkeyp
     run_review(rid, svc)
     assert stages(svc, rid)["reading"] == "skipped"
     assert svc.store.get_blob(rid, "reading") is None and svc.store.blob_keys(rid, "story_reading:") == []
+
+
+def test_a_later_cl_rewriting_an_earlier_ones_line_is_a_rewrite_and_each_story_reads_only_the_cls_in_its_code(fx, tmp_path):
+    """CL 105 rewrites the line CL 103 added in `logger_init`; CL 104 adds `logger_level` (phase 2 §4)."""
+    svc = make_services(fx, tmp_path)
+    logger = "//fixture/service/logger.c"
+    rid = svc.store.create_review("t", "owner", [103, 104, 105])
+    run_review(rid, svc)
+    r = svc.store.get_blob(rid, "reading")
+    rewrite = {"by": 105, "of": 103, "file": logger, "function": "logger_init", "lines": 1, "line": 7}
+    assert r["rewrites"] == [rewrite] and r["gaps"] == []
+    assert list(svc.store.get_blob(rid, "lines")) == [logger]                     # only files several CLs edit
+    titles = {s["title"]: s["id"] for s in svc.store.get_blob(rid, "stories")["stories"]}
+    init = svc.store.get_blob(rid, f"story_reading:{titles['Other changes in `service` (`logger_init`)']}")
+    level = svc.store.get_blob(rid, f"story_reading:{titles['Other changes in `service` (`logger_level`)']}")
+    assert (init["cl_order"], init["rewrites"], init["where"][0]["cls"]) == ([103, 105], [rewrite], [103, 105])
+    assert (level["cl_order"], level["rewrites"]) == ([104], [])
+    rid = svc.store.create_review("t", "owner", [103, 105])                       # CL 104 is outside this review
+    run_review(rid, svc)
+    assert svc.store.get_blob(rid, "reading")["gaps"] == [{"file": logger, "after_cl": 103, "before_cl": 105}]
```

`backend/tests/test_web.py` (diff):

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index bd298eb..4236fa7 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -462,3 +462,13 @@ def test_a_mark_on_a_check_judged_no_hazard_survives_a_rerun(env):
     assert owner.post(f"/api/reviews/{rid}/checks/{quote(cleared[0]['key'], safe='')}/mark").status_code == 200
     owner.post(f"/api/reviews/{rid}/rerun")
     assert set(owner.get(f"/api/reviews/{rid}/reading").json()["marks"]) == {cleared[0]["key"]}
+
+
+def test_a_file_several_cls_edit_comes_with_who_wrote_each_line(env):
+    svc, app, _ = env
+    owner = login(app, "owner")
+    rid = owner.post("/api/reviews", json={"cls": [103, 104, 105]}).json()["id"]
+    files = {f["depot"]: f for f in owner.get(f"/api/reviews/{rid}/files").json()}
+    logger = files["//fixture/service/logger.c"]["lines"]
+    assert logger["wrote"][6] == 105 and logger["over"][6] == 103 and logger["rewritten"] == {"103": {"7": 105}}
+    assert [d for d, f in files.items() if "lines" in f] == ["//fixture/service/logger.c"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_web.py -q`
Expected: FAIL: `2 failed, 57 passed`; the first error is `KeyError: 'rewrites'`

- [ ] **Step 3: Implement**

`backend/codetortoise/pipeline.py` (diff):

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 9992cf2..bff06f9 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -31,6 +31,7 @@ from codetortoise.pieces import build_pieces
 from codetortoise.provenance import finding_files, impact_node_files, local_files
 from codetortoise.reading import READING_VERSION, build_reading, headline_facts
 from codetortoise.repeated import find_repeated
+from codetortoise.sequence import file_lines
 from codetortoise.services import Services
 from codetortoise.stories import build_stories
 from codetortoise.swarm import SwarmError
@@ -417,7 +418,7 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
 
     def drop_reading() -> None:
         """A run that builds no reading leaves none: the last run's would read as this one's."""
-        store.replace_blobs(rid, ["reading", "reading_head"], ["story_reading:"], {})
+        store.replace_blobs(rid, ["reading", "reading_head", "lines"], ["story_reading:"], {})
 
     def reading():
         """How the review reads (spec 2026-10-07-review-reading): threads, connections, To check, each story's tiles."""
@@ -451,11 +452,12 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
             return texts[path]
         has_tests = any(is_test_path(rel(f)) for f in svc.index.files()) or \
             any(is_test_path(rel(f.local)) for f in ctx["cs"].files)
+        lines = file_lines(ctx["cs"])
         r, per = build_reading(bs.stories, x.c, details=bs.story_details, analysis=bs.analysis, pieces=ps,
                                targets=targets, has_tests=has_tests, includers=svc.index.transitive_includers,
                                test_callers=lambda name: {c.path for c in svc.index.callers_of(name)
                                                           if is_test_path(rel(c.path))},
-                               read_text=read_text)
+                               read_text=read_text, lines=lines)
         notes: list[str] = []
         strong = cfg.llm.strong
         if svc.strong is None or strong is None:
@@ -479,8 +481,9 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
                         "whole": r.whole, "whole_source": r.whole_source,
                         "connections": {f"{k.a}-{k.b}": k.text for k in r.connections}})
             told = f"thread text by {strong.model}"
-        store.replace_blobs(rid, ["reading", "reading_head"], ["story_reading:"],
+        store.replace_blobs(rid, ["reading", "reading_head", "lines"], ["story_reading:"],
                             {"reading": r, "reading_head": headline_facts(r, x.c.findings),
+                             "lines": {d: fl.model_dump() for d, fl in lines.items()},
                              **{f"story_reading:{sid}": sr for sid, sr in per.items()}})
         ctx["reading_stored"] = True
         store.prune_marks(rid, {k.key for k in r.checks + r.cleared})
```

`backend/codetortoise/reading.py` (diff):

```diff
diff --git a/backend/codetortoise/reading.py b/backend/codetortoise/reading.py
index 9a6b0ac..ca6f024 100644
--- a/backend/codetortoise/reading.py
+++ b/backend/codetortoise/reading.py
@@ -18,6 +18,7 @@ from codetortoise.board import BoardContext, Flow, _count, _covered, _Ctx, analy
 from codetortoise.cparse import is_header, preproc_spans
 from codetortoise.detectors.base import SEVERITY_RANK, Finding
 from codetortoise.pieces import PieceSet, node_cl
+from codetortoise.sequence import FileLines, Gap, Rewrite, file_lines, rewrites
 from codetortoise.stories import Story, StoryDetail, StorySet
 from codetortoise.targets import UNKNOWN
 from codetortoise.tidy import tidy
@@ -87,6 +88,7 @@ class WhereFile(BaseModel):
     path: str                         # workspace-relative
     depot: str | None = None
     functions: list[WhereFn] = Field(default_factory=list)
+    cls: list[int] = Field(default_factory=list)   # the story's CLs that edit the file, in order (phase 2 §5.3)
 
 
 class CallPath(BaseModel):
@@ -162,6 +164,8 @@ class StoryReading(BaseModel):
     place_text: str = ""              # its place in its thread: "Uses what story 1 adds."
     thread: str | None = None
     position: int | None = None       # 1-based, within its thread
+    cl_order: list[int] = Field(default_factory=list)           # the order to read its CLs in (phase 2 §4.4)
+    rewrites: list[Rewrite] = Field(default_factory=list)       # rewrites in its code
 
 
 class Reading(BaseModel):
@@ -179,6 +183,8 @@ class Reading(BaseModel):
     headline: Headline = Field(default_factory=lambda: Headline(text="No risks found", tone="none", rules_only=True))
     rules_only: bool = True
     tests: TestsRow | None = None
+    rewrites: list[Rewrite] = Field(default_factory=list)       # later CLs replacing earlier CLs' lines (phase 2 §4.3)
+    gaps: list[Gap] = Field(default_factory=list)               # CLs outside the review between two of its CLs
 
 
 def rel_path(x: _Ctx, path: str | None) -> str:
@@ -1084,9 +1090,11 @@ def _set_depots(c: BoardContext, checks: list[Check]) -> None:
 def build_reading(ss: StorySet, c: BoardContext, details: dict[str, StoryDetail] | None = None, analysis=None,
                   pieces: PieceSet | None = None, targets: dict[str, list[str]] | None = None, has_tests: bool = False,
                   test_callers: Callable[[str], set[str]] | None = None, includers: Callable[[str], set[str]] | None = None,
-                  read_text: Callable[[str], str | None] | None = None) -> tuple[Reading, dict[str, StoryReading]]:
-    """The review's reading (threads, connections, order, To check, build impact, coverage, headline) and each story's
-    tiles, with fixed text; llm/threads.py may reword the thread names, purposes and the whole."""
+                  read_text: Callable[[str], str | None] | None = None,
+                  lines: dict[str, FileLines] | None = None) -> tuple[Reading, dict[str, StoryReading]]:
+    """The review's reading (threads, connections, order, To check, build impact, coverage, headline, rewrites) and each
+    story's tiles, with fixed text; llm/threads.py may reword the thread names, purposes and the whole. `lines`: each
+    multi-CL file walked (phase 2 §4), computed from the change set when not given."""
     a = analysis or analyse(c)
     x = a.x
     links = story_links(ss, x)
@@ -1121,18 +1129,55 @@ def build_reading(ss: StorySet, c: BoardContext, details: dict[str, StoryDetail]
                       headline=headline(rows, set(), x.c.findings),
                       rules_only=not any(f.verdict_source == "tier1" for f in x.c.findings),
                       tests=_tests_row(ss, threads, x), whole=fixed_whole(threads, conns))
+    lines = file_lines(c.cs) if lines is None else lines
+    reading.rewrites = rewrites(lines, [f for fx in c.after for f in fx.functions])
+    reading.gaps = [g for fl in lines.values() for g in fl.gaps]
+    local_of = {d: fl.local for d, fl in lines.items()}
     thread_of = {s: t for t in threads for s in t.stories}
     per: dict[str, StoryReading] = {}
     for s in ss.stories:
         t = thread_of.get(s.id)
         flows = details[s.id].board.flows if details and s.id in details else a.flows
-        per[s.id] = StoryReading(story=s.id, contracts=contract_rows(s, x), where=where(s, x), paths=call_paths(s, x, flows),
+        files = where(s, x)
+        for wf in files:
+            wf.cls = sorted({c for f in wf.functions for c in _cls_of(x, f.node, lines)})
+        order_ = sorted({c for wf in files for c in wf.cls}) or sorted(s.cls)
+        per[s.id] = StoryReading(story=s.id, contracts=contract_rows(s, x), where=files, paths=call_paths(s, x, flows),
                                  checks=[k for k in rows if k.story == s.id],
                                  place_text=_place_text(s.id, t.stories, strong) if t else "",
-                                 thread=t.id if t else None, position=t.stories.index(s.id) + 1 if t else None)
+                                 thread=t.id if t else None, position=t.stories.index(s.id) + 1 if t else None,
+                                 cl_order=order_, rewrites=_story_rewrites(s, x, reading.rewrites, local_of))
     return reading, per
 
 
+def _cls_of(x: _Ctx, n: str, lines: dict[str, FileLines]) -> list[int]:
+    """The CLs whose edits fall inside a changed function (phase 2 §4.4): in a file several CLs edit, those that wrote
+    its final lines, removed its base lines or had lines inside it rewritten; else its file's CL."""
+    fc = x.texts.get(x.local(n) or "")
+    fl = lines.get(fc.depot) if fc else None
+    one = node_cl(x, n)
+    if fl is None:
+        return [one] if one is not None else []
+    key = x.im.nodes[n].key
+    fa, fb = x.fa.get(key), x.fb.get(key)
+    out: set[int] = set()
+    if fa is not None:
+        out |= {c for c in fl.wrote[fa.start_line - 1:fa.end_line] if c is not None}
+        out |= {c for a, _, by, line in fl.replaced if line is not None and fa.start_line <= line <= fa.end_line
+                for c in (a, by)}
+    if fb is not None:
+        out |= {c for c in fl.removed[fb.start_line - 1:fb.end_line] if c is not None}
+    return sorted(out) or ([one] if one is not None else [])
+
+
+def _story_rewrites(s: Story, x: _Ctx, rows: list[Rewrite], local_of: dict[str, str]) -> list[Rewrite]:
+    """The rewrites in a story's code (phase 2 §4.4): in one of its changed functions, or — when no function stands in
+    their place — in a file holding its code."""
+    fns = _story_fns(s, x)
+    quals, files = {_qual(x, n) for n in fns}, {x.local(n) for n in fns}
+    return [r for r in rows if r.function in quals or (r.function is None and local_of.get(r.file) in files)]
+
+
 def _marked(lines: dict[str, str], marks: dict[str, dict]) -> dict[str, dict]:
     """Each mark on a check still there, with `changed` when the source line at its place is no longer the line it was
     marked at (the check is open again)."""
```

`backend/codetortoise/sequence.py` (diff):

```diff
diff --git a/backend/codetortoise/sequence.py b/backend/codetortoise/sequence.py
index f9b55a9..62fc05a 100644
--- a/backend/codetortoise/sequence.py
+++ b/backend/codetortoise/sequence.py
@@ -9,7 +9,7 @@ from difflib import SequenceMatcher
 from pydantic import BaseModel, Field
 
 from codetortoise.facts.model import Function
-from codetortoise.vcs.model import FileChange
+from codetortoise.vcs.model import ChangeSet, FileChange
 
 
 class Gap(BaseModel):
@@ -120,3 +120,8 @@ def rewrites(lines: dict[str, FileLines], fns: list[Function]) -> list[Rewrite]:
             if line is not None and (r.line is None or line < r.line):
                 r.line = line
     return sorted(rows.values(), key=lambda r: (r.file, r.of, r.by, r.line or 0, r.function or ""))
+
+
+def file_lines(cs: ChangeSet) -> dict[str, FileLines]:
+    """Each file more than one CL of the change set touches, walked; a file one CL touches needs no walk (§4.1)."""
+    return {f.depot: walk(f) for f in cs.files if len({p.cl for p in f.per_cl}) > 1}
```

`backend/codetortoise/web/app.py` (diff):

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index 929339a..ce0458c 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -432,7 +432,8 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
     def files(rid: int, _: str = Depends(user_of)):
         review_or_404(rid)
         cs = store.get_blob(rid, "changeset") or {}
-        return cs.get("files", [])
+        lines = store.get_blob(rid, "lines") or {}        # who wrote each line of a multi-CL file (phase 2 §4)
+        return [{**f, "lines": lines[f["depot"]]} if f["depot"] in lines else f for f in cs.get("files", [])]
 
     # ---- layers ------------------------------------------------------------
     @app.put("/api/layers/{level}")
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_web.py -q`
Expected: PASS: `59 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `635 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_pipeline.py backend/tests/test_web.py backend/codetortoise/pipeline.py backend/codetortoise/reading.py backend/codetortoise/sequence.py backend/codetortoise/web/app.py
git commit -m "feat(reading): the reading says which later CLs rewrote earlier ones' lines and where a CL outside the review came between; each story reads only the CLs in its code, in order; a file several CLs edit comes with who wrote each line"
```

### Task 5: Read ticks

Spec §6.1, §6.5, §7.3, §7.4, §7.5 (ticks). A new table holds each reader's own ticks. `GET /ticks` answers the signed-in reader's ticks (empty lists for a review without a reading); `PUT` and `DELETE` set and clear one, checking that the key is a story of the reading's order or one of its checks. Looks fine (`POST …/mark`) also ticks the check for the one who says it; undoing the mark keeps the tick. `run_review` clears every reader's ticks when it starts.

**Files:**
- Test: `backend/tests/test_store.py`
- Test: `backend/tests/test_web.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/store.py`
- Modify: `backend/codetortoise/web/app.py`

**Interfaces:**
- Consumes: `Store.get_blob(rid, "reading")`; `user_of` (the signed-in user); `run_review` (pipeline).
- Produces: `Store.set_tick(rid, user, kind, key)`, `Store.clear_tick(rid, user, kind, key)`, `Store.list_ticks(rid, user) -> {"stories": [...], "checks": [...]}`, `Store.clear_ticks(rid)`;
  `GET /api/reviews/{rid}/ticks`; `PUT` / `DELETE /api/reviews/{rid}/ticks/{kind}/{key:path}` → `{"ok": true}`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_store.py` (diff):

```diff
diff --git a/backend/tests/test_store.py b/backend/tests/test_store.py
index 0ca311d..793446a 100644
--- a/backend/tests/test_store.py
+++ b/backend/tests/test_store.py
@@ -112,6 +112,20 @@ def test_check_marks_are_per_review_shared_and_pruned_to_the_keys_found_again(st
     assert store.list_marks(rid) == {} and store.list_marks(rid + 1) == {}
 
 
+
+def test_read_ticks_belong_to_one_reader_and_a_run_clears_them_all(store):
+    rid = store.create_review("t", "a", [1])
+    store.set_tick(rid, "ana", "story", "S1")
+    store.set_tick(rid, "ana", "check", "caller|a.c|f|g")
+    store.set_tick(rid, "ana", "story", "S1")                                  # ticking again changes nothing
+    store.set_tick(rid, "bob", "story", "S2")
+    assert store.list_ticks(rid, "ana") == {"stories": ["S1"], "checks": ["caller|a.c|f|g"]}
+    assert store.list_ticks(rid, "bob") == {"stories": ["S2"], "checks": []}
+    store.clear_tick(rid, "ana", "story", "S1")
+    assert store.list_ticks(rid, "ana") == {"stories": [], "checks": ["caller|a.c|f|g"]}
+    store.clear_ticks(rid)
+    assert store.list_ticks(rid, "ana") == store.list_ticks(rid, "bob") == {"stories": [], "checks": []}
+
 def test_comments_can_be_anchored_to_a_check(store):
     rid = store.create_review("t", "a", [1])
     c = store.add_comment(rid, "bob", "is this fine?", "check", {"key": "caller|a.c|f|g"})
```

`backend/tests/test_web.py` (diff):

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index 4236fa7..ce1f41a 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -472,3 +472,33 @@ def test_a_file_several_cls_edit_comes_with_who_wrote_each_line(env):
     logger = files["//fixture/service/logger.c"]["lines"]
     assert logger["wrote"][6] == 105 and logger["over"][6] == 103 and logger["rewritten"] == {"103": {"7": 105}}
     assert [d for d, f in files.items() if "lines" in f] == ["//fixture/service/logger.c"]
+
+
+def test_read_ticks_are_each_readers_own_looks_fine_ticks_the_check_and_a_rerun_clears_them(env):
+    from urllib.parse import quote
+    svc, app, _ = env
+    owner, rid = _review(app)
+    bob = login(app, "bob")
+    r = owner.get(f"/api/reviews/{rid}/reading").json()
+    story, check = r["order"][0], r["checks"][0]["key"]
+    assert TestClient(app).get(f"/api/reviews/{rid}/ticks").status_code == 401
+    assert owner.put(f"/api/reviews/{rid}/ticks/story/{story}").json() == {"ok": True}
+    assert owner.put(f"/api/reviews/{rid}/ticks/check/{quote(check, safe='')}").status_code == 200
+    assert owner.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [story], "checks": [check]}
+    assert bob.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": []}      # private to each reader
+    other = r["checks"][1]["key"]
+    bob.post(f"/api/reviews/{rid}/checks/{quote(other, safe='')}/mark")                    # Looks fine: read by bob
+    assert bob.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": [other]}
+    bob.delete(f"/api/reviews/{rid}/checks/{quote(other, safe='')}/mark")                  # undoing it keeps the tick
+    assert bob.get(f"/api/reviews/{rid}/ticks").json()["checks"] == [other]
+    assert owner.delete(f"/api/reviews/{rid}/ticks/story/{story}").json() == {"ok": True}
+    assert owner.get(f"/api/reviews/{rid}/ticks").json()["stories"] == []
+    bad = owner.put(f"/api/reviews/{rid}/ticks/story/S99")
+    assert bad.status_code == 404 and bad.json()["detail"] == "That story or check is not in this review's reading."
+    assert owner.put(f"/api/reviews/{rid}/ticks/flow/F1").status_code == 422
+    owner.post(f"/api/reviews/{rid}/rerun")
+    assert owner.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": []}
+    assert bob.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": []}
+    svc.store.replace_blobs(rid, ["reading", "reading_head"], ["story_reading:"], {})        # a review run before the reading
+    assert owner.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": []}
+    assert owner.put(f"/api/reviews/{rid}/ticks/story/{story}").status_code == 404
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_store.py tests/test_web.py -q`
Expected: FAIL: `2 failed, 40 passed`; the first error is `AttributeError: 'Store' object has no attribute 'set_tick'. Did you mean: 'set_mark'?`

- [ ] **Step 3: Implement**

`backend/codetortoise/pipeline.py` (diff):

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index bff06f9..f1b98c5 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -123,6 +123,7 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
     seen (no cached brief)."""
     store, cfg = svc.store, svc.cfg
     store.reset_stages(rid, STAGES)
+    store.clear_ticks(rid)                     # a re-run starts every reader's reading plan over
     store.set_review_status(rid, "running")
     status: dict[str, str] = {}
     ctx: dict = {}
```

`backend/codetortoise/store.py` (diff):

```diff
diff --git a/backend/codetortoise/store.py b/backend/codetortoise/store.py
index dd9eda3..3bff34c 100644
--- a/backend/codetortoise/store.py
+++ b/backend/codetortoise/store.py
@@ -42,6 +42,8 @@ CREATE TABLE IF NOT EXISTS briefs(review_id INTEGER PRIMARY KEY, cache_key TEXT,
 CREATE INDEX IF NOT EXISTS ix_briefs_key ON briefs(cache_key);
 CREATE TABLE IF NOT EXISTS check_marks(review_id INTEGER, key TEXT, user TEXT, at TEXT, source_line TEXT,
     PRIMARY KEY(review_id, key));
+CREATE TABLE IF NOT EXISTS read_ticks(review_id INTEGER, user TEXT, kind TEXT, key TEXT, at TEXT,
+    PRIMARY KEY(review_id, user, kind, key));
 """
 
 ANCHOR_KINDS = {"line", "function", "finding", "chapter", "review", "story", "flow", "file", "check"}
@@ -259,6 +261,24 @@ class Store:
         for key in set(self.list_marks(rid)) - keep:
             self.clear_mark(rid, key)
 
+    # ---- read ticks (spec 2026-10-07-review-reading-phase2 §6) -----------
+    def set_tick(self, rid: int, user: str, kind: str, key: str) -> None:
+        """`user` has read the story or check `key`; nobody else sees it."""
+        self._exec("INSERT OR IGNORE INTO read_ticks(review_id, user, kind, key, at) VALUES(?,?,?,?,?)",
+                   (rid, user, kind, key, _now()))
+
+    def clear_tick(self, rid: int, user: str, kind: str, key: str) -> None:
+        self._exec("DELETE FROM read_ticks WHERE review_id=? AND user=? AND kind=? AND key=?", (rid, user, kind, key))
+
+    def list_ticks(self, rid: int, user: str) -> dict[str, list[str]]:
+        rows = self._all("SELECT kind, key FROM read_ticks WHERE review_id=? AND user=? ORDER BY at, key", (rid, user))
+        return {"stories": [r["key"] for r in rows if r["kind"] == "story"],
+                "checks": [r["key"] for r in rows if r["kind"] == "check"]}
+
+    def clear_ticks(self, rid: int) -> None:
+        """A run starts every reader over (§6.5)."""
+        self._exec("DELETE FROM read_ticks WHERE review_id=?", (rid,))
+
     # ---- sessions --------------------------------------------------------
     def create_session(self, user: str, ttl_days: int = 7) -> str:
         token = secrets.token_urlsafe(32)
```

`backend/codetortoise/web/app.py` (diff):

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index ce0458c..b3d7613 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -307,6 +307,7 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
     def mark_check(rid: int, key: str, user: str = Depends(user_of)):
         review_or_404(rid)
         k = check_or_404(rid, key)
+        store.set_tick(rid, user, "check", k.key)          # Looks fine is also read, for the one who says it
         return store.set_mark(rid, k.key, user, k.source_line)
 
     @app.delete("/api/reviews/{rid}/checks/{key:path}/mark")
@@ -315,6 +316,34 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         store.clear_mark(rid, key)
         return {"ok": True}
 
+    # ---- the reading plan (spec 2026-10-07-review-reading-phase2 §6) --------
+    @app.get("/api/reviews/{rid}/ticks")
+    def ticks(rid: int, user: str = Depends(user_of)):
+        review_or_404(rid)
+        if not store.get_blob(rid, "reading"):
+            return {"stories": [], "checks": []}
+        return store.list_ticks(rid, user)
+
+    def tick_or_404(rid: int, kind: str, key: str) -> None:
+        raw = store.get_blob(rid, "reading")
+        r = Reading.model_validate(raw) if raw else None
+        known = (r.order if kind == "story" else [k.key for k in r.checks]) if r else []
+        if key not in known:
+            raise HTTPException(404, "That story or check is not in this review's reading.")
+
+    @app.put("/api/reviews/{rid}/ticks/{kind}/{key:path}")
+    def tick(rid: int, kind: Literal["story", "check"], key: str, user: str = Depends(user_of)):
+        review_or_404(rid)
+        tick_or_404(rid, kind, key)
+        store.set_tick(rid, user, kind, key)
+        return {"ok": True}
+
+    @app.delete("/api/reviews/{rid}/ticks/{kind}/{key:path}")
+    def untick(rid: int, kind: Literal["story", "check"], key: str, user: str = Depends(user_of)):
+        review_or_404(rid)
+        store.clear_tick(rid, user, kind, key)
+        return {"ok": True}
+
     @app.get("/api/reviews/{rid}/locate")
     def locate(rid: int, node: str | None = None, flow: str | None = None, finding: str | None = None,
                _: str = Depends(user_of)):
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_store.py tests/test_web.py -q`
Expected: PASS: `42 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `637 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_store.py backend/tests/test_web.py backend/codetortoise/pipeline.py backend/codetortoise/store.py backend/codetortoise/web/app.py
git commit -m "feat(plan): read ticks — each reader's own ticks on stories and checks, Looks fine ticking the check for the one who says it, and a run clearing every reader's ticks"
```

### Task 6: Chips in the diff

Spec §5.1, §5.2, §5.5. `chipsAll` tags each changed row of the combined diff with the CL that wrote (or removed) it, a chip on the first row of each run of one CL (and, for added rows, one `over`): "CL 102" or "CL 103 · rewrites CL 101". `chipsOne` greys, in one CL's diff, the added rows a later CL replaced, a chip "rewritten in CL 103" on the first of each run. `CodeView` draws the chip inside the row's source cell (on the side holding the row in side-by-side mode); a chip click switches the file's CL picker. On a phone the chip shows only the number.

**Files:**
- Test: `frontend/e2e/workspace-sequence.spec.ts`
- Test: `frontend/src/reading/sequence.test.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/board/CodeView.tsx`
- Create: `frontend/src/reading/sequence.ts`
- Modify: `frontend/src/reading/types.ts`
- Modify: `frontend/src/workspace/FileDiff.tsx`
- Modify: `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: `FileLines` from `GET /files` (Task 4); `board/codeRows` `Line`, `lineKey(side, n)`, `lineDiff`.
- Produces: `reading/types.ts` `FileLines`, `Gap`; `api.ts` `FileChange.lines?: FileLines`;
  `reading/sequence.ts` `Tag {cl, label, short, chip, grey}`, `chipsAll(rows: Line[], fl: FileLines): Map<string, Tag>`, `chipsOne(rows: Line[], fl: FileLines, cl: number): Map<string, Tag>` (keyed by `lineKey`);
  `CodeView` props `tags?: Map<string, Tag>`, `onTag?: (cl: number) => void`; CSS `.cl-chip` (`.long`, `.short`), row class `rw`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-sequence.spec.ts` (new file):

```ts
import { devices, expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

/** CLs as a sequence (spec 2026-10-07-review-reading-phase2): fixture CL 103 adds logger_init's `lg->level = 1;`,
 * CL 104 adds logger_level, CL 105 rewrites CL 103's line to `lg->level = 2;`. */
const STACK = "103 104 105";

async function openLogger(page: Page, base: string) {
  await page.goto(`${base}/i/files`);
  await page.getByRole("link", { name: "Open logger.c's diff" }).click();
  return page.getByRole("complementary", { name: "Code: logger.c" });
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the combined diff chips each run of rows with the CL that wrote it, and a chip shows that CL alone", async ({ page }) => {
    const code = await openLogger(page, await startReview(page, STACK));
    await expect(code.locator(".cl-chip .long")).toHaveText(["CL 105 · rewrites CL 103", "CL 104"]);
    await code.getByRole("button", { name: "CL 104: show CL 104 alone" }).click();
    await expect(code.getByLabel("Changelist")).toHaveValue("104");
    await expect(code.locator(".cl-chip")).toHaveCount(0);
  });

  test("an earlier CL's own diff greys the lines a later CL rewrote and says which", async ({ page }) => {
    const code = await openLogger(page, await startReview(page, STACK));
    await code.getByLabel("Changelist").selectOption("103");
    const row = code.locator(".bd-ln.rw");
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("lg->level = 1;");
    await expect(row.locator(".cl-chip .long")).toHaveText("rewritten in CL 105");
    await row.getByRole("button", { name: /show CL 105 alone/ }).click();
    await expect(code.getByLabel("Changelist")).toHaveValue("105");
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("chips shrink to the CL number", async ({ page }) => {
    const code = await openLogger(page, await startReview(page, STACK));
    await expect(code.locator(".cl-chip .short")).toHaveText(["105", "104"]);
    await expect(code.locator(".cl-chip .long").first()).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
```

`frontend/src/reading/sequence.test.ts` (new file):

```ts
import { describe, expect, it } from "vitest";
import { lineDiff } from "../board/codeRows";
import { chipsAll, chipsOne } from "./sequence";
import type { FileLines } from "./types";

/** Base a b; CL 101 adds x1 x2 after a; CL 102 replaces them with z and adds y at the end; CL 102 also removes b. */
const fl: FileLines = {
  depot: "//d/f.c", local: "/w/f.c",
  wrote: [null, 102, 102], over: [null, 101, null], removed: [null, 102],
  rewritten: { "101": { "2": 102, "3": 102 } }, replaced: [], gaps: [],
};

const shown = (tags: ReturnType<typeof chipsAll>) =>
  [...tags.entries()].map(([k, t]) => [k, t.chip ? t.label : null, t.short, t.grey, t.cl]);

describe("CL chips (spec 2026-10-07-review-reading-phase2 §5)", () => {
  it("in the combined diff, chip each run of rows one CL wrote, saying when it replaced an earlier CL's lines", () => {
    const rows = lineDiff("a\nb\n", "a\nz\ny\n");
    expect(shown(chipsAll(rows, fl))).toEqual([
      ["old:2", "CL 102", "102", false, 102],
      ["new:2", "CL 102 · rewrites CL 101", "102", false, 102],
      ["new:3", "CL 102", "102", false, 102],
    ]);
  });

  it("leaves rows no CL of the review wrote without a chip", () => {
    const outside: FileLines = { ...fl, wrote: [null, null, null], over: [null, null, null], removed: [null, null] };
    expect(chipsAll(lineDiff("a\nb\n", "a\nz\ny\n"), outside).size).toBe(0);
  });

  it("in one CL's diff, greys its lines a later CL replaced and chips the first of each run", () => {
    const rows = lineDiff("a\nb\n", "a\nx1\nx2\nb\n");                // CL 101's own diff
    expect(shown(chipsOne(rows, fl, 101))).toEqual([
      ["new:2", "rewritten in CL 102", "→102", true, 102],
      ["new:3", null, "→102", true, 102],
    ]);
    expect(chipsOne(rows, fl, 102).size).toBe(0);
  });
});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd frontend && npx vitest run src/reading/sequence.test.ts`
Expected: FAIL: `Tests no tests`; the first error is `Error: Cannot find module './sequence' imported from frontend/src/reading/sequence.test.ts`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-sequence.spec.ts`
Expected: FAIL: `npm run build fails with 2 type error(s)`; the first error is `src/reading/sequence.test.ts(3,36): error TS2307: Cannot find module './sequence' or its corresponding type declarations.`

- [ ] **Step 3: Implement**

`frontend/src/api.ts` (diff):

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index b476c8b..a1aa3d9 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -31,7 +31,11 @@ export type Names = Record<string, NodeName>;
 export interface Neighbour extends NodeName { id: string; changed: boolean; test: boolean }
 export interface Neighbours { node: Neighbour; callers: { total: number; items: Neighbour[] }; callees: { total: number; items: Neighbour[] } }
 export interface PerCl { cl: number; before: string; after: string }
-export interface FileChange { depot: string; local: string; action: string; before: string; after: string; base_rev: string | null; per_cl: PerCl[] }
+export interface FileChange {
+  depot: string; local: string; action: string; before: string; after: string; base_rev: string | null; per_cl: PerCl[];
+  /** Who wrote each line, for a file several CLs of the review edit (spec 2026-10-07-review-reading-phase2 §4). */
+  lines?: FileLines;
+}
 export type AnchorKind = "line" | "function" | "finding" | "chapter" | "review" | "story" | "flow" | "file" | "check";
 export interface Comment {
   id: number; review_id: number; parent_id: number | null; author: string; body: string;
@@ -59,7 +63,7 @@ export interface Health { checks: HealthCheck[]; ready: boolean; index_generatio
 
 export type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
 import type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
-import type { Headline, Mark, Reading } from "./reading/types";
+import type { FileLines, Headline, Mark, Reading } from "./reading/types";
 export type { Headline, Mark, Reading } from "./reading/types";
 
 export class ApiError extends Error {
```

`frontend/src/board/CodeView.tsx` (diff):

```diff
diff --git a/frontend/src/board/CodeView.tsx b/frontend/src/board/CodeView.tsx
index 662bd65..f0e730b 100644
--- a/frontend/src/board/CodeView.tsx
+++ b/frontend/src/board/CodeView.tsx
@@ -3,6 +3,7 @@ import type { Comment } from "../api";
 import Comments from "../components/Comments";
 import FoldButton from "../components/FoldButton";
 import { lineAnchor, onLine } from "../lib/anchors";
+import type { Tag } from "../reading/sequence";
 import { codeItems, lineKey, type Line, type Side, WINDOW, windowAround } from "./codeRows";
 import { type Run, STEP } from "./fold";
 import { tokens } from "./highlight";
@@ -24,6 +25,10 @@ interface Props {
   onExpand?: (run: Run, how: "up" | "down" | "all") => void;
   /** Comments made on one changelist's diff are anchored to it. */
   cl?: number | null;
+  /** Rows' CLs by lineKey (spec 2026-10-07-review-reading-phase2 §5): chips, and greyed lines a later CL replaced. */
+  tags?: Map<string, Tag>;
+  /** A chip was clicked: show that CL alone. */
+  onTag?: (cl: number) => void;
 }
 
 const ICON = { warn: "⚠ ", ok: "✓ ", info: "ⓘ " } as const;
@@ -32,8 +37,18 @@ function Src({ text }: { text: string }) {
   return <>{tokens(text).map((t, i) => (t.cls ? <span key={i} className={`hl-${t.cls}`}>{t.text}</span> : t.text))}</>;
 }
 
+function Chip({ tag, onTag }: { tag?: Tag; onTag?: (cl: number) => void }) {
+  if (!tag?.chip) return null;
+  return (
+    <button className="cl-chip" title={`Show CL ${tag.cl} alone`} aria-label={`${tag.label}: show CL ${tag.cl} alone`}
+            onClick={(e) => { e.stopPropagation(); onTag?.(tag.cl); }}>
+      <span className="long">{tag.label}</span><span className="short">{tag.short}</span>
+    </button>
+  );
+}
+
 /** Code lines (diff or plain) with inline annotations and line comment threads; click a line to comment. */
-function CodeView({ reviewId, path, lines, mode, anns, comments, onComments, focus, windowed, runs, onExpand, cl = null }: Props) {
+function CodeView({ reviewId, path, lines, mode, anns, comments, onComments, focus, windowed, runs, onExpand, cl = null, tags, onTag }: Props) {
   const [opened, setOpened] = useState<Set<string>>(new Set());
   const mine = useMemo(() => anns.filter((a) => a.path === path), [anns, path]);
   const threads = useMemo(() => {
@@ -90,23 +105,24 @@ function CodeView({ reviewId, path, lines, mode, anns, comments, onComments, foc
             </div>
           );
         if (it.kind === "line") {
-          const l = it.line;
+          const l = it.line, tag = tags?.get(lineKey(it.side, it.no));
           return (
             <div key={i} data-n={l.n ?? undefined} onClick={() => open(it.side, it.no)}
-                 className={`bd-ln${l.t === "+" ? " a" : l.t === "-" ? " d" : ""}${it.hot ? " hot" : ""}${focus && l.n === focus ? " focus" : ""}`}>
+                 className={`bd-ln${l.t === "+" ? " a" : l.t === "-" ? " d" : ""}${it.hot ? " hot" : ""}${focus && l.n === focus ? " focus" : ""}${tag?.grey ? " rw" : ""}`}>
               <span className="no">{l.n ?? l.o}</span><span className="sg">{l.t === "=" ? "" : l.t}</span>
-              <span className="src"><Src text={l.text} /><span className="plus">＋ comment</span></span>
+              <span className="src"><Src text={l.text} /><Chip tag={tag} onTag={onTag} /><span className="plus">＋ comment</span></span>
             </div>
           );
         }
         const { l, r } = it;
+        const lt = l?.t === "-" ? tags?.get(lineKey("old", l.o!)) : undefined, rt = r ? tags?.get(lineKey("new", r.n!)) : undefined;
         return (
           <Fragment key={i}>
             <div data-n={r?.n ?? undefined} onClick={() => open(it.side, it.no)}
-                 className={`bd-sbs${it.hot ? " hot" : ""}${focus && r?.n === focus ? " focus" : ""}`}>
-              {l ? <><span className={`no l${l.t === "-" ? " d" : ""}`}>{l.o}</span><span className={`src l${l.t === "-" ? " d" : ""}`}><Src text={l.text} /></span></>
+                 className={`bd-sbs${it.hot ? " hot" : ""}${focus && r?.n === focus ? " focus" : ""}${rt?.grey ? " rw" : ""}`}>
+              {l ? <><span className={`no l${l.t === "-" ? " d" : ""}`}>{l.o}</span><span className={`src l${l.t === "-" ? " d" : ""}`}><Src text={l.text} /><Chip tag={lt} onTag={onTag} /></span></>
                  : <><span className="no empty" /><span className="src empty" /></>}
-              {r ? <><span className={`no r${r.t === "+" ? " a" : ""}`}>{r.n}</span><span className={`src r${r.t === "+" ? " a" : ""}`}><Src text={r.text} /><span className="plus">＋ comment</span></span></>
+              {r ? <><span className={`no r${r.t === "+" ? " a" : ""}`}>{r.n}</span><span className={`src r${r.t === "+" ? " a" : ""}`}><Src text={r.text} /><Chip tag={rt} onTag={onTag} /><span className="plus">＋ comment</span></span></>
                  : <><span className="no empty" /><span className="src empty"><span className="plus">＋ comment</span></span></>}
             </div>
           </Fragment>
```

`frontend/src/reading/sequence.ts` (new file):

```ts
/** CLs as a sequence (spec 2026-10-07-review-reading-phase2 §5): which CL wrote each row of a diff, from the server's
 * walk of a file several CLs edit (backend/codetortoise/sequence.py). */
import { type Line, lineKey } from "../board/codeRows";
import type { FileLines } from "./types";

/** A row's CL: `chip` on the first row of a run (its label; `short` on a phone), `grey` for a line a later CL replaced;
 * clicking the chip shows CL `cl` alone. */
export interface Tag { cl: number; label: string; short: string; chip: boolean; grey: boolean }

/** The combined diff (base → final): a chip on the first row of each run of changed rows one CL wrote — "CL 103 ·
 * rewrites CL 101" when its lines replaced an earlier CL's. Rows no CL of the review wrote get none. */
export function chipsAll(rows: Line[], fl: FileLines): Map<string, Tag> {
  const out = new Map<string, Tag>();
  let prev: string | null = null;
  for (const l of rows) {
    const cl = l.t === "+" ? fl.wrote[l.n! - 1] : l.t === "-" ? fl.removed[l.o! - 1] : null;
    if (cl == null) { prev = null; continue; }
    const over = l.t === "+" ? fl.over[l.n! - 1] ?? null : null;
    const run = `${l.t}${cl}|${over}`;
    if (run !== prev) {
      out.set(l.t === "+" ? lineKey("new", l.n!) : lineKey("old", l.o!), {
        cl, label: over ? `CL ${cl} · rewrites CL ${over}` : `CL ${cl}`, short: String(cl), chip: true, grey: false });
    }
    prev = run;
  }
  return out;
}

/** One CL's diff: its added lines a later CL replaced are greyed, the first of each run chipped "rewritten in CL 105". */
export function chipsOne(rows: Line[], fl: FileLines, cl: number): Map<string, Tag> {
  const out = new Map<string, Tag>();
  const later = fl.rewritten[String(cl)] ?? {};
  let prev: number | null = null;
  for (const l of rows) {
    const by = l.t === "+" ? later[String(l.n)] ?? null : null;
    if (by !== null) {
      out.set(lineKey("new", l.n!), { cl: by, label: `rewritten in CL ${by}`, short: `→${by}`, chip: by !== prev, grey: true });
    }
    prev = l.t === "=" ? null : by;
  }
  return out;
}
```

`frontend/src/reading/types.ts` (diff):

```diff
diff --git a/frontend/src/reading/types.ts b/frontend/src/reading/types.ts
index 6745a41..98fe3ff 100644
--- a/frontend/src/reading/types.ts
+++ b/frontend/src/reading/types.ts
@@ -52,3 +52,18 @@ export interface StoryReading {
   /** Its place in its thread: "Uses what story 1 adds." */
   place_text: string; thread: string | null; position: number | null;
 }
+
+/** Who wrote each line of a file several CLs edit (phase 2 §4.3); JSON keys of `rewritten` are strings. */
+export interface FileLines {
+  depot: string; local: string;
+  /** Per line of the final text: the CL that wrote it, and the earlier CL whose lines it replaced. */
+  wrote: (number | null)[]; over: (number | null)[];
+  /** Per line of the base text: the CL that removed it. */
+  removed: (number | null)[];
+  /** rewritten[cl a][its after-text line] = the later CL that replaced it. */
+  rewritten: Record<string, Record<string, number>>;
+  replaced: [number, number, number, number | null][]; gaps: Gap[];
+}
+/** A CL outside the review changed `file` between review CLs `after_cl` and `before_cl`. */
+export interface Gap { file: string; after_cl: number; before_cl: number }
+
```

`frontend/src/workspace/FileDiff.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/FileDiff.tsx b/frontend/src/workspace/FileDiff.tsx
index c961ecc..29d9876 100644
--- a/frontend/src/workspace/FileDiff.tsx
+++ b/frontend/src/workspace/FileDiff.tsx
@@ -10,6 +10,7 @@ import Comments from "../components/Comments";
 import Explain, { FileSummaryView } from "../components/Explain";
 import { useAi } from "../lib/ai";
 import { onLine } from "../lib/anchors";
+import { chipsAll, chipsOne } from "../reading/sequence";
 import { useWs } from "./context";
 
 interface Props {
@@ -41,6 +42,10 @@ export default function FileDiff({ path, line, anns, cl: firstCl = null, wide }:
     if (src && "status" in src && src.status === "ok") return plainLines(src.file.text);
     return null;
   }, [src, change, step]);
+  const tags = useMemo(() => {                      // which CL wrote each row (spec 2026-10-07-review-reading-phase2 §5)
+    if (!lines || !change?.lines) return undefined;
+    return cl === null ? chipsAll(lines, change.lines) : chipsOne(lines, change.lines, cl);
+  }, [lines, change, cl]);
   const mine = useMemo(() => anns.filter((x) => x.path === path && x.side === "new"), [anns, path]);
   const keep = useMemo(() => {                      // lines with notes or comment threads stay in the changes view
     if (!lines) return new Set<number>();
@@ -100,7 +105,7 @@ export default function FileDiff({ path, line, anns, cl: firstCl = null, wide }:
       </div>
       {lines ? (
         <CodeView reviewId={d.id} path={path} lines={lines} mode={change ? mode : "unified"} anns={anns} comments={d.comments}
-                  onComments={d.loadComments} focus={line} windowed cl={cl} runs={runs}
+                  onComments={d.loadComments} focus={line} windowed cl={cl} runs={runs} tags={tags} onTag={setCl}
                   onExpand={(run, how) => setShown((s) => [...s, expandRange(run, how)])} />
       ) : src && "status" in src && src.status === "error" ? (
         <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => ws.sources.reload(path)}>Retry</button></div>
```

`frontend/src/workspace/workspace.css` (diff):

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index ba88e4b..89c523e 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -143,6 +143,13 @@ body.bd-resizing-v, body.bd-resizing-v * { cursor: row-resize !important; user-s
 .bd-code .src { white-space: pre; padding-right: 12px; }
 .bd-code .plus { visibility: hidden; margin-left: 6px; color: var(--flow); font: 700 11px var(--bd-sans); }
 .bd-ln:hover .plus, .bd-sbs:hover .plus { visibility: visible; }
+/* CLs as a sequence (spec 2026-10-07-review-reading-phase2 §5): which CL wrote a run of rows; lines a later CL replaced */
+.cl-chip { margin-left: 10px; padding: 0 7px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface);
+  color: var(--muted); font: 600 10.5px/1.6 var(--bd-sans); cursor: pointer; vertical-align: 1px; }
+.cl-chip:hover { color: var(--flow); border-color: var(--flow); }
+.cl-chip .short { display: none; }
+.bd-ln.rw .src, .bd-sbs.rw .src.r { opacity: .55; }
+@media (max-width: 640px) { .cl-chip .long { display: none; } .cl-chip .short { display: inline; } }
 .hl-kw { color: var(--hl-kw); font-weight: 600; } .hl-ty { color: var(--hl-ty); } .hl-num { color: var(--hl-num); } .hl-str { color: var(--hl-str); }
 .hl-cm { color: var(--hl-cm); font-style: italic; } .hl-fn { color: var(--hl-fn); } .hl-mc { color: var(--hl-mc); font-weight: 600; }
 .hl-pp { color: var(--hl-pp); }
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd frontend && npx vitest run src/reading/sequence.test.ts`
Expected: PASS: `Tests 3 passed (3)`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-sequence.spec.ts`
Expected: PASS: `3 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `637 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 176 passed (176)`; Playwright `2 failed, 105 passed` (in the replay, the first run's failures were timeouts under load; `npx playwright test --last-failed` then gave `2 passed`)

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-sequence.spec.ts frontend/src/reading/sequence.test.ts frontend/src/api.ts frontend/src/board/CodeView.tsx frontend/src/reading/sequence.ts frontend/src/reading/types.ts frontend/src/workspace/FileDiff.tsx frontend/src/workspace/workspace.css
git commit -m "feat(diff): a file several CLs edit chips each run of rows with the CL that wrote it, and one CL's diff greys its lines a later CL rewrote; a chip shows that CL alone"
```

### Task 7: Where by CL, and the CL page's Rewrites

Spec §5.3, §5.4. A story with more than one CL says "Read CL 103, then CL 105" and groups Where's files under the first of its CLs that edits each ("CL 103 · 1 file", "also CL 105"); below, each of its rewrites names the function (or the file) and opens it at its line in the combined diff. The CL page gains a Rewrites section with both directions and any gap next to the CL, and no section when there is nothing to say.

**Files:**
- Test: `frontend/e2e/workspace-sequence.spec.ts`
- Test: `frontend/src/reading/story.test.ts`
- Modify: `frontend/src/reading/story.ts`
- Modify: `frontend/src/reading/types.ts`
- Modify: `frontend/src/workspace/ClPage.tsx`
- Modify: `frontend/src/workspace/StoryTiles.tsx`
- Modify: `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: `StoryReading.cl_order`, `.rewrites`, `WhereFile.cls`, `Reading.rewrites`, `.gaps` (Task 4).
- Produces: `reading/types.ts` `Rewrite`, optional `WhereFile.cls`, `StoryReading.cl_order`/`rewrites`, `Reading.rewrites`/`gaps`;
  `reading/story.ts` `whereByCl(where: WhereFile[], order: number[]): {cl: number|null; files: (WhereFile & {also: number[]})[]}[]`, `readOrder(order?: number[]): string|null`, `rewriteText(r: Rewrite): {lead, name}`, `clRewrites(all: Rewrite[]|undefined, cl: number): {rewrites, rewrittenBy}`; `whereTree` becomes generic over `W extends WhereFile`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-sequence.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-sequence.spec.ts b/frontend/e2e/workspace-sequence.spec.ts
index dc2c967..f33494c 100644
--- a/frontend/e2e/workspace-sequence.spec.ts
+++ b/frontend/e2e/workspace-sequence.spec.ts
@@ -32,6 +32,37 @@ test.describe("desktop", () => {
     await row.getByRole("button", { name: /show CL 105 alone/ }).click();
     await expect(code.getByLabel("Changelist")).toHaveValue("105");
   });
+
+  test("a story's Where groups its files by CL in reading order, says the order, and names the rewrite", async ({ page }) => {
+    await startReview(page, STACK);
+    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S\d+: .*logger_init/ }).click();
+    const where = page.getByRole("region", { name: "Where" });
+    await expect(where.locator(".st-order")).toHaveText("Read CL 103, then CL 105");
+    await expect(where.locator(".st-clgroup h4")).toHaveText(["CL 103 · 1 file"]);
+    await expect(where.getByRole("group", { name: "CL 103" }).locator(".st-file .ws-chip")).toHaveText("also CL 105");
+    await expect(where.locator(".st-rewrites li")).toHaveText("CL 105 rewrites 1 line CL 103 added in logger_init");
+    await where.getByRole("link", { name: "Open logger_init at line 7, in all CLs" }).click();
+    const code = page.getByRole("complementary", { name: "Code: logger.c" });
+    await expect(code.getByLabel("Changelist")).toHaveValue("all");
+    await expect(code.locator(".bd-ln.focus")).toContainText("lg->level = 2;");
+  });
+
+  test("a CL page names its rewrites both ways, and a CL outside the review between two of its CLs", async ({ page }) => {
+    let base = await startReview(page, STACK);
+    await page.goto(`${base}/cl/105`);
+    const rw = page.getByRole("region", { name: "Rewrites" });
+    await expect(rw.locator("li")).toHaveText("rewrites lines CL 103 added: logger_init (1 line)");
+    await page.goto(`${base}/cl/103`);
+    await expect(rw.locator("li")).toHaveText("lines it added are rewritten by CL 105: logger_init (1 line)");
+    await page.goto(`${base}/cl/104`);
+    await expect(page.getByRole("heading", { name: "Stories drawn from this CL" })).toBeVisible();
+    await expect(rw).toHaveCount(0);
+    base = await startReview(page, "103 105");
+    await page.goto(`${base}/cl/105`);
+    await expect(rw.locator("li")).toHaveText([
+      "rewrites lines CL 103 added: logger_init (1 line)",
+      "logger.c: a CL outside this review changed it between CL 103 and CL 105"]);
+  });
 });
 
 test.describe("phone", () => {
```

`frontend/src/reading/story.test.ts` (diff):

```diff
diff --git a/frontend/src/reading/story.test.ts b/frontend/src/reading/story.test.ts
index 9be9b10..c135e56 100644
--- a/frontend/src/reading/story.test.ts
+++ b/frontend/src/reading/story.test.ts
@@ -1,6 +1,6 @@
 import { describe, expect, it } from "vitest";
-import { byEntry, clCounts, codeOrder, foldPath, stepIn, threadCrumb, whereTree } from "./story";
-import type { CallPath, ContractRow, Reading, WhereFile } from "./types";
+import { byEntry, clCounts, clRewrites, codeOrder, foldPath, readOrder, rewriteText, stepIn, threadCrumb, whereByCl, whereTree } from "./story";
+import type { CallPath, ContractRow, Reading, Rewrite, WhereFile } from "./types";
 
 const fn = (node: string, label: string, cl: number | null, extra = {}) => ({ node, label, add: 2, rem: 1, cl, line: 3, ...extra });
 const file = (path: string, functions: ReturnType<typeof fn>[]): WhereFile => ({ path, depot: `//d/${path}`, functions });
@@ -60,3 +60,32 @@ describe("Code", () => {
     expect(codeOrder(where, rows).map((f) => f.label)).toEqual(["callee", "caller", "other"]);
   });
 });
+
+describe("CLs as a sequence (spec 2026-10-07-review-reading-phase2 §5.3, §5.4)", () => {
+  const w = (path: string, cls: number[]) => ({ ...file(path, [fn(`n-${path}`, path, cls[0] ?? null)]), cls });
+  const rw = (by: number, of: number, fnName: string | null, lines: number, file = "//d/drv/uart.c"): Rewrite =>
+    ({ by, of, file, function: fnName, lines, line: lines ? 4 : null });
+
+  it("groups Where's files under the first of the story's CLs that edits them, in reading order, naming the others", () => {
+    const groups = whereByCl([w("a.c", [103]), w("b.c", [101, 103]), w("c.c", [101]), w("d.c", [])], [101, 103]);
+    expect(groups.map((g) => [g.cl, g.files.map((f) => [f.path, f.also])])).toEqual([
+      [101, [["b.c", [103]], ["c.c", []]]], [103, [["a.c", []]]], [null, [["d.c", []]]]]);
+  });
+
+  it("says the order to read a story's CLs in only when it has several", () => {
+    expect(readOrder([101, 103, 105])).toBe("Read CL 101, then CL 103, then CL 105");
+    expect(readOrder([104])).toBeNull();
+    expect(readOrder(undefined)).toBeNull();
+  });
+
+  it("says what a rewrite replaced and where, by function or else by file", () => {
+    expect(rewriteText(rw(103, 101, "uart_send", 5))).toEqual({ lead: "CL 103 rewrites 5 lines CL 101 added in", name: "uart_send" });
+    expect(rewriteText(rw(105, 103, null, 1))).toEqual({ lead: "CL 105 rewrites 1 line CL 103 added in", name: "uart.c" });
+  });
+
+  it("splits the review's rewrites into a CL's two directions", () => {
+    const all = [rw(103, 101, "send", 5), rw(105, 103, "init", 1), rw(104, 102, "x", 2)];
+    expect(clRewrites(all, 103)).toEqual({ rewrites: [all[0]], rewrittenBy: [all[1]] });
+    expect(clRewrites(undefined, 103)).toEqual({ rewrites: [], rewrittenBy: [] });
+  });
+});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd frontend && npx vitest run src/reading/story.test.ts`
Expected: FAIL: `Tests 4 failed | 7 passed (11)`; the first error is `TypeError: whereByCl is not a function`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-sequence.spec.ts`
Expected: FAIL: `npm run build fails with 7 type error(s)`; the first error is `src/reading/story.test.ts(2,29): error TS2305: Module '"./story"' has no exported member 'clRewrites'.`

- [ ] **Step 3: Implement**

`frontend/src/reading/story.ts` (diff):

```diff
diff --git a/frontend/src/reading/story.ts b/frontend/src/reading/story.ts
index d1faaf6..f31dc58 100644
--- a/frontend/src/reading/story.ts
+++ b/frontend/src/reading/story.ts
@@ -1,6 +1,6 @@
 /** A story page's tiles (spec 2026-10-07-review-reading §6): its place in its thread, Where, call paths and code order. */
 import { letter } from "./checks";
-import type { CallPath, ContractRow, Reading, WhereFile, WhereFn } from "./types";
+import type { CallPath, ContractRow, Reading, Rewrite, WhereFile, WhereFn } from "./types";
 
 /** ‹ › on a story page: the story `by` places away in reading order, wrapping; a story not in it stays put. */
 export function stepIn(order: string[], sid: string, by: number): string {
@@ -25,8 +25,8 @@ export function clCounts(where: WhereFile[]): { cl: number; functions: number }[
 
 /** Folder › file › functions, folders in Where's order; a function's CL shows only where its file was edited in
  * several CLs. */
-export function whereTree(where: WhereFile[]): { dir: string; files: { name: string; file: WhereFile; showCl: boolean }[] }[] {
-  const dirs = new Map<string, { name: string; file: WhereFile; showCl: boolean }[]>();
+export function whereTree<W extends WhereFile>(where: W[]): { dir: string; files: { name: string; file: W; showCl: boolean }[] }[] {
+  const dirs = new Map<string, { name: string; file: W; showCl: boolean }[]>();
   for (const w of where) {
     const cut = w.path.lastIndexOf("/"), dir = cut < 0 ? "." : w.path.slice(0, cut);
     const showCl = new Set(w.functions.map((f) => f.cl)).size > 1;
@@ -35,6 +35,35 @@ export function whereTree(where: WhereFile[]): { dir: string; files: { name: str
   return [...dirs.entries()].map(([dir, files]) => ({ dir, files }));
 }
 
+/** Where's files under the first of the story's CLs that edits them, in reading order (phase 2 §5.3); `also` names
+ * its other CLs. Files no CL is known for come last, under `null`. */
+export function whereByCl(where: WhereFile[], order: number[]): { cl: number | null; files: (WhereFile & { also: number[] })[] }[] {
+  const groups = new Map<number | null, (WhereFile & { also: number[] })[]>([...order.map((c) => [c, []] as [number, []]), [null, []]]);
+  for (const w of where) {
+    const [first = null, ...also] = w.cls ?? [];
+    if (!groups.has(first)) groups.set(first, []);
+    groups.get(first)!.push({ ...w, also });
+  }
+  const out = [...groups.entries()].filter(([, files]) => files.length).map(([cl, files]) => ({ cl, files }));
+  return [...out.filter((g) => g.cl !== null), ...out.filter((g) => g.cl === null)];
+}
+
+/** "Read CL 101, then CL 103" for a story with several CLs; null otherwise. */
+export function readOrder(order: number[] | undefined): string | null {
+  return order && order.length > 1 ? `Read ${order.map((c) => `CL ${c}`).join(", then ")}` : null;
+}
+
+/** A rewrite's sentence, ending in the function (or else the file) it happened in. */
+export function rewriteText(r: Rewrite): { lead: string; name: string } {
+  return { lead: `CL ${r.by} rewrites ${r.lines} line${r.lines === 1 ? "" : "s"} CL ${r.of} added in`,
+           name: r.function ?? r.file.slice(r.file.lastIndexOf("/") + 1) };
+}
+
+/** A CL's rewrites in both directions (phase 2 §5.4): those it made, and those later CLs made of its lines. */
+export function clRewrites(all: Rewrite[] | undefined, cl: number): { rewrites: Rewrite[]; rewrittenBy: Rewrite[] } {
+  return { rewrites: (all ?? []).filter((r) => r.by === cl), rewrittenBy: (all ?? []).filter((r) => r.of === cl) };
+}
+
 /** The paths under the function they start from, in rank order; `entry` when that is an entry point. */
 export function byEntry(paths: CallPath[]): { label: string; entry: boolean; paths: CallPath[] }[] {
   const groups = new Map<string, { label: string; entry: boolean; paths: CallPath[] }>();
```

`frontend/src/reading/types.ts` (diff):

```diff
diff --git a/frontend/src/reading/types.ts b/frontend/src/reading/types.ts
index 98fe3ff..5dbb693 100644
--- a/frontend/src/reading/types.ts
+++ b/frontend/src/reading/types.ts
@@ -32,6 +32,8 @@ export interface Reading {
   /** Findings judged no hazard, with their reasons. */
   cleared: Check[]; build_impact: BuildImpact[]; coverage: string[]; headline: Headline; rules_only: boolean;
   tests: TestsRow | null; marks: Record<string, Mark>;
+  /** Later CLs replacing lines earlier ones added, and CLs outside the review in between (phase 2 §4.3). */
+  rewrites?: Rewrite[]; gaps?: Gap[];
 }
 
 export interface ContractRow {
@@ -41,7 +43,11 @@ export interface ContractRow {
   mark: number[]; added: string[]; removed: string[]; nodes: string[];
 }
 export interface WhereFn { node: string; label: string; add: number; rem: number; cl: number | null; line: number | null }
-export interface WhereFile { path: string; depot: string | null; functions: WhereFn[] }
+export interface WhereFile {
+  path: string; depot: string | null; functions: WhereFn[];
+  /** The story's CLs that edit the file, in order (phase 2 §5.3); absent on a reading stored before phase 2. */
+  cls?: number[];
+}
 export interface CallPath {
   /** Node ids, entry first; `hidden` are the folded middle steps of a long path. */
   steps: string[]; labels: string[]; kind: "contract" | "state" | "call"; entry: string | null; hidden: string[];
@@ -51,6 +57,8 @@ export interface StoryReading {
   story: string; contracts: ContractRow[]; where: WhereFile[]; paths: CallPath[]; checks: Check[];
   /** Its place in its thread: "Uses what story 1 adds." */
   place_text: string; thread: string | null; position: number | null;
+  /** The order to read the story's CLs in, and the rewrites inside its code (phase 2 §4.4); absent before phase 2. */
+  cl_order?: number[]; rewrites?: Rewrite[];
 }
 
 /** Who wrote each line of a file several CLs edit (phase 2 §4.3); JSON keys of `rewritten` are strings. */
@@ -67,3 +75,6 @@ export interface FileLines {
 /** A CL outside the review changed `file` between review CLs `after_cl` and `before_cl`. */
 export interface Gap { file: string; after_cl: number; before_cl: number }
 
+/** CL `by` replaced or deleted `lines` lines CL `of` added to `file` (a depot path); `line` is the first final line in
+ * their place and `function` the function holding it. */
+export interface Rewrite { by: number; of: number; file: string; function: string | null; lines: number; line: number | null }
```

`frontend/src/workspace/ClPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/ClPage.tsx b/frontend/src/workspace/ClPage.tsx
index bf6a448..a813221 100644
--- a/frontend/src/workspace/ClPage.tsx
+++ b/frontend/src/workspace/ClPage.tsx
@@ -6,6 +6,8 @@ import { SeverityBadge } from "../components/Badges";
 import Markdown from "../components/Markdown";
 import { descriptionParts, plainTitle } from "../lib/markdown";
 import { tidy } from "../lib/tidy";
+import { clRewrites } from "../reading/story";
+import type { Rewrite } from "../reading/types";
 import { useWs } from "./context";
 import { short } from "./crumbs";
 import { Ticks } from "./NameText";
@@ -21,6 +23,14 @@ export default function ClPage({ cl }: { cl: number }) {
   const paths = new Set(files.map((f) => f.path));
   const stories = d.stories?.stories.filter((s) => s.cls.includes(cl)) ?? [];
   const findings = d.findings.filter((f) => f.files?.some((p) => paths.has(p)));
+  const { rewrites, rewrittenBy } = clRewrites(d.reading?.rewrites, cl);      // phase 2 §5.4
+  const gaps = (d.reading?.gaps ?? []).filter((g) => g.after_cl === cl || g.before_cl === cl);
+  const base = (p: string) => p.slice(p.lastIndexOf("/") + 1);
+  const at = (r: Rewrite) => {
+    const name = r.function ?? base(r.file), label = `Open ${name}${r.line ? ` at line ${r.line}` : ""}, in all CLs`;
+    return <><Link className="mono" to={ws.link(ws.opened({ file: r.file, line: r.line }))} title={label} aria-label={label}>{name}</Link>
+      {" "}({r.lines} line{r.lines === 1 ? "" : "s"})</>;
+  };
   const run = (act: () => Promise<unknown>, ok: string) => {           // a new press clears the last answer
     setMsg(null);
     act().then(() => { setMsg(ok); d.loadDetail(); }).catch((e) => setMsg(String(e.message ?? e)));
@@ -60,6 +70,15 @@ export default function ClPage({ cl }: { cl: number }) {
             <span className="muted small"> {f.action} <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span></span></li>
         ))}</ul> : <p className="muted">No files of this CL in the review's change summary.</p>}
       </section>
+      {(rewrites.length > 0 || rewrittenBy.length > 0 || gaps.length > 0) && (
+        <section aria-labelledby="ws-clrw"><h3 id="ws-clrw">Rewrites</h3>
+          <ul className="ws-fx">
+            {rewrites.map((r, i) => <li key={`r${i}`}>rewrites lines CL {r.of} added: {at(r)}</li>)}
+            {rewrittenBy.map((r, i) => <li key={`b${i}`}>lines it added are rewritten by CL {r.by}: {at(r)}</li>)}
+            {gaps.map((g, i) => <li key={`g${i}`}><span className="mono">{base(g.file)}</span>: a CL outside this review changed it
+              between CL {g.after_cl} and CL {g.before_cl}</li>)}
+          </ul></section>
+      )}
       {stories.length > 0 && (
         <section aria-labelledby="ws-cls"><h3 id="ws-cls">Stories drawn from this CL</h3>
           <ul className="ws-findings">{stories.map((s) => (
```

`frontend/src/workspace/StoryTiles.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/StoryTiles.tsx b/frontend/src/workspace/StoryTiles.tsx
index 1004caf..0c674fa 100644
--- a/frontend/src/workspace/StoryTiles.tsx
+++ b/frontend/src/workspace/StoryTiles.tsx
@@ -2,8 +2,8 @@ import { useState } from "react";
 import { Link } from "react-router-dom";
 import type { StoryDetail } from "../board/types";
 import Comments from "../components/Comments";
-import { byEntry, codeOrder, foldPath, whereTree } from "../reading/story";
-import type { CallPath, ContractRow, StoryReading } from "../reading/types";
+import { byEntry, codeOrder, foldPath, readOrder, rewriteText, whereByCl, whereTree } from "../reading/story";
+import type { CallPath, ContractRow, StoryReading, WhereFile } from "../reading/types";
 import CheckTile, { Cleared } from "./CheckList";
 import { useWs } from "./context";
 import FunctionCode from "./FunctionCode";
@@ -34,9 +34,38 @@ function Contract({ row }: { row: ContractRow }) {
   );
 }
 
+/** Where's files by folder, then file, then function; `also` names a file's later CLs in the story (phase 2 §5.3). */
+function WhereDirs({ files }: { files: (WhereFile & { also?: number[] })[] }) {
+  const ws = useWs();
+  return (
+    <>{whereTree(files).map((d) => (
+      <div key={d.dir} className="st-dir">
+        <div className="st-dir-name mono">{d.dir}/</div>
+        {d.files.map(({ name, file, showCl }) => (
+          <div key={file.path} className="st-file">
+            <div className="mono">{name}{(file.also ?? []).map((c) => <span key={c} className="ws-chip">also CL {c}</span>)}</div>
+            <ul>{file.functions.map((f) => {
+              const label = `Open ${f.label} in ${file.path}${f.line ? ` at line ${f.line}` : ""}`;
+              return (
+                <li key={f.node}>
+                  {file.depot ? <Link className="mono" to={ws.link(ws.opened({ file: file.depot, line: f.line }))} title={label}
+                                      aria-label={label}>{f.label}</Link> : <span className="mono">{f.label}</span>}
+                  <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
+                  {showCl && f.cl !== null && <span className="ws-chip">CL {f.cl}</span>}
+                </li>
+              );
+            })}</ul>
+          </div>
+        ))}
+      </div>
+    ))}</>
+  );
+}
+
 /** Before → after beside Where (§6.1). */
 function ContractAndWhere({ sr }: { sr: StoryReading }) {
   const ws = useWs();
+  const order = readOrder(sr.cl_order), grouped = (sr.cl_order?.length ?? 0) > 1;    // phase 2 §5.3
   return (
     <div className="st-pair">
       {sr.contracts.length > 0 && (
@@ -48,27 +77,22 @@ function ContractAndWhere({ sr }: { sr: StoryReading }) {
       {sr.where.length > 0 && (
         <section className="ws-tile" aria-label="Where">
           <h3>Where</h3>
-          {whereTree(sr.where).map((d) => (
-            <div key={d.dir} className="st-dir">
-              <div className="st-dir-name mono">{d.dir}/</div>
-              {d.files.map(({ name, file, showCl }) => (
-                <div key={file.path} className="st-file">
-                  <div className="mono">{name}</div>
-                  <ul>{file.functions.map((f) => {
-                    const label = `Open ${f.label} in ${file.path}${f.line ? ` at line ${f.line}` : ""}`;
-                    return (
-                      <li key={f.node}>
-                        {file.depot ? <Link className="mono" to={ws.link(ws.opened({ file: file.depot, line: f.line }))} title={label}
-                                            aria-label={label}>{f.label}</Link> : <span className="mono">{f.label}</span>}
-                        <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
-                        {showCl && f.cl !== null && <span className="ws-chip">CL {f.cl}</span>}
-                      </li>
-                    );
-                  })}</ul>
-                </div>
-              ))}
+          {order && <p className="st-order">{order}</p>}
+          {grouped ? whereByCl(sr.where, sr.cl_order!).map((g) => (
+            <div key={g.cl ?? "none"} className="st-clgroup" role="group" aria-label={g.cl === null ? "Other files" : `CL ${g.cl}`}>
+              <h4>{g.cl === null ? "Other" : `CL ${g.cl}`} · {g.files.length} file{g.files.length === 1 ? "" : "s"}</h4>
+              <WhereDirs files={g.files} />
             </div>
-          ))}
+          )) : <WhereDirs files={sr.where} />}
+          {(sr.rewrites ?? []).length > 0 && (
+            <ul className="st-rewrites">{sr.rewrites!.map((r, i) => {
+              const t = rewriteText(r), label = `Open ${t.name}${r.line ? ` at line ${r.line}` : ""}, in all CLs`;
+              return (
+                <li key={i}>{t.lead}{" "}
+                  <Link className="mono" to={ws.link(ws.opened({ file: r.file, line: r.line }))} title={label} aria-label={label}>{t.name}</Link></li>
+              );
+            })}</ul>
+          )}
         </section>
       )}
     </div>
```

`frontend/src/workspace/workspace.css` (diff):

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 89c523e..7d7c2b5 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -622,6 +622,13 @@ a.ws-chip { text-decoration: none; }
 .st-file { margin: 2px 0 0 12px; font-size: 13px; }
 .st-file ul { list-style: none; margin: 0; padding: 0 0 0 14px; }
 .st-file li { display: flex; gap: 8px; align-items: baseline; padding: 1px 0; }
+/* Where in reading order (spec 2026-10-07-review-reading-phase2 §5.3) */
+.st-order { margin: 0 0 6px; font-size: 13px; color: var(--ink); }
+.st-clgroup + .st-clgroup { margin-top: 10px; }
+.st-clgroup h4 { margin: 0 0 4px; font: 600 12px/1.4 var(--bd-sans); color: var(--muted); }
+.st-file .ws-chip { margin-left: 6px; }
+.st-rewrites { list-style: none; margin: 10px 0 0; padding: 8px 0 0; border-top: 1px solid var(--line); font-size: 13px; }
+.st-rewrites li + li { margin-top: 2px; }
 .st-file a { text-decoration: none; }
 .st-entry { margin: 0 0 8px; }
 .st-entry > summary { cursor: pointer; font-size: 13px; }
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd frontend && npx vitest run src/reading/story.test.ts`
Expected: PASS: `Tests 11 passed (11)`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-sequence.spec.ts`
Expected: PASS: `5 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `637 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 180 passed (180)`; Playwright `109 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-sequence.spec.ts frontend/src/reading/story.test.ts frontend/src/reading/story.ts frontend/src/reading/types.ts frontend/src/workspace/ClPage.tsx frontend/src/workspace/StoryTiles.tsx frontend/src/workspace/workspace.css
git commit -m "feat(story): Where groups a story's files by CL in reading order and names its rewrites; a CL page says which CLs rewrote its lines, which it rewrote, and where a CL outside the review came between"
```

### Task 8: Mark as read and the Read box

Spec §6.2, §6.3, §7.6. `plan.ts` holds the pure parts: the next unread story in reading order (wrapping; null when all are read), progress counts that ignore ticks the reading no longer holds, and a thread's "n of m". `useReview` loads the reader's ticks with the results and after each change. The story header gains Mark as read beside ‹ ›: it ticks the story and goes to the next unread story, or to the overview when none is left; a read story shows "✓ Read · Mark unread". Each To check row gains a Read box; Looks fine reloads the ticks too, since the server ticks the check for the marker. A read row is slightly dimmed for that reader.

**Files:**
- Test: `frontend/e2e/workspace-plan.spec.ts`
- Test: `frontend/src/reading/plan.test.ts`
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/reading/plan.ts`
- Modify: `frontend/src/workspace/CheckList.tsx`
- Modify: `frontend/src/workspace/StoryPage.tsx`
- Modify: `frontend/src/workspace/useReview.ts`
- Modify: `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: the ticks API (Task 5); `Reading.order`, `.checks`.
- Produces: `reading/plan.ts` `ReadTicks {stories: string[]; checks: string[]}`, `nextUnread(order, read: ReadonlySet<string>, from): string|null`, `Progress {stories, storyCount, checks, checkCount, all}`, `progress(r: Reading, t: ReadTicks): Progress`, `progressText(p): string`, `threadRead(stories, read): string`;
  `api.ticks(id)`, `api.tick(id, kind, key, on)`; `useReview` → `ticks: ReadTicks | null`, `loadTicks()`, `tick(kind, key, on)`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-plan.spec.ts` (new file):

```ts
import { expect, type Page, test } from "@playwright/test";
import { login, startReview } from "./helpers";

/** The reading plan (spec 2026-10-07-review-reading-phase2 §6): each reader's own ticks on stories and checks. */
const FOUR = "101 102 103 104";

async function readingOf(page: Page, base: string): Promise<{ order: string[]; checks: { key: string }[] }> {
  return (await page.request.get(`/api${base.replace("/r/", "/reviews/")}/reading`)).json();
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Mark as read ticks the story and goes to the next unread one; a read story offers Mark unread", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const { order } = await readingOf(page, base);
    await page.goto(`${base}/s/${order[1]}`);
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/${order[2]}$`));
    await page.goto(`${base}/s/${order[0]}`);
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/${order[2]}$`));      // order[1] is read already
    await page.goto(`${base}/s/${order[1]}`);
    await expect(page.locator(".st-read")).toHaveText("✓ Read · Mark unread");
    await page.getByRole("button", { name: "Mark unread" }).click();
    await expect(page.getByRole("button", { name: "Mark as read" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Mark as read" })).toBeVisible();
  });

  test("a check's Read box is the reader's own; Looks fine ticks it for the one who says it", async ({ page, browser }) => {
    const base = await startReview(page, FOUR);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    const rows = page.locator(".ck-tile .ck-row");
    const [a, b] = [await rows.nth(0).getAttribute("data-key"), await rows.nth(1).getAttribute("data-key")];
    const row = (p: Page, key: string | null) => p.locator(`.ck-tile .ck-row[data-key="${key}"]`);
    await row(page, a).getByRole("checkbox", { name: "Read" }).click();          // checked once the server has it
    await expect(row(page, a).getByRole("checkbox", { name: "Read" })).toBeChecked();
    await expect(row(page, a)).toHaveClass(/\bread\b/);
    await row(page, b).getByRole("button", { name: "Looks fine" }).click();
    await expect(row(page, b).getByRole("checkbox", { name: "Read" })).toBeChecked();
    await page.reload();
    await expect(row(page, a).getByRole("checkbox", { name: "Read" })).toBeChecked();

    const other = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    await login(other, "ana");
    await other.goto(`${base}`);
    await other.getByRole("link", { name: "Go to the overview" }).click();
    await expect(row(other, b).getByRole("button", { name: "Reopen" })).toBeVisible();     // the mark is shared…
    await expect(other.locator(".ck-tile").getByRole("checkbox", { name: "Read", checked: true })).toHaveCount(0);   // …the ticks are not
    await other.context().close();
  });
});
```

`frontend/src/reading/plan.test.ts` (new file):

```ts
import { describe, expect, it } from "vitest";
import { nextUnread, progress, progressText, threadRead } from "./plan";
import type { Check, Reading } from "./types";

const check = (key: string) => ({ key }) as Check;
const reading = { order: ["S2", "S1", "S3", "S4"], checks: [check("a"), check("b"), check("c")],
                  cleared: [check("z")] } as unknown as Reading;

describe("the reading plan (spec 2026-10-07-review-reading-phase2 §6)", () => {
  it("goes to the next story in reading order the reader has not read, wrapping, and nowhere when all are read", () => {
    expect(nextUnread(reading.order, new Set(["S2"]), "S2")).toBe("S1");
    expect(nextUnread(reading.order, new Set(["S2", "S1", "S4"]), "S4")).toBe("S3");
    expect(nextUnread(reading.order, new Set(["S2", "S1", "S3", "S4"]), "S1")).toBeNull();
  });

  it("counts read stories and checks, ignoring ticks the reading no longer holds", () => {
    const p = progress(reading, { stories: ["S1", "S9"], checks: ["a", "z", "gone"] });
    expect(p).toEqual({ stories: 1, storyCount: 4, checks: 1, checkCount: 3, all: false });
    expect(progressText(p)).toBe("1 of 4 stories read · 1 of 3 checks");
    expect(progressText(progress({ ...reading, checks: [] }, { stories: [], checks: [] }))).toBe("0 of 4 stories read");
    expect(progress(reading, { stories: ["S1", "S2", "S3", "S4"], checks: [] }).all).toBe(true);
  });

  it("says how much of a thread the reader has read", () => {
    expect(threadRead(["S2", "S1", "S3"], new Set(["S1", "S3"]))).toBe("2 of 3");
  });
});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd frontend && npx vitest run src/reading/plan.test.ts`
Expected: FAIL: `Tests no tests`; the first error is `Error: Cannot find module './plan' imported from frontend/src/reading/plan.test.ts`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-plan.spec.ts`
Expected: FAIL: `npm run build fails with 1 type error(s)`; the first error is `src/reading/plan.test.ts(2,64): error TS2307: Cannot find module './plan' or its corresponding type declarations.`

- [ ] **Step 3: Implement**

`frontend/src/api.ts` (diff):

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index a1aa3d9..d02c7fd 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -63,6 +63,7 @@ export interface Health { checks: HealthCheck[]; ready: boolean; index_generatio
 
 export type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
 import type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
+import type { ReadTicks } from "./reading/plan";
 import type { FileLines, Headline, Mark, Reading } from "./reading/types";
 export type { Headline, Mark, Reading } from "./reading/types";
 
@@ -104,6 +105,10 @@ export const api = {
   /** "Looks fine" on a To check row, for everyone viewing the review; its key holds "|", so it is encoded. */
   markCheck: (id: number, key: string) => call<Mark>("POST", `/api/reviews/${id}/checks/${encodeURIComponent(key)}/mark`),
   unmarkCheck: (id: number, key: string) => call("DELETE", `/api/reviews/${id}/checks/${encodeURIComponent(key)}/mark`),
+  /** The signed-in reader's own ticks (spec 2026-10-07-review-reading-phase2 §6). */
+  ticks: (id: number) => call<ReadTicks>("GET", `/api/reviews/${id}/ticks`),
+  tick: (id: number, kind: "story" | "check", key: string, on: boolean) =>
+    call(on ? "PUT" : "DELETE", `/api/reviews/${id}/ticks/${kind}/${encodeURIComponent(key)}`),
   locate: (id: number, q: { node?: string; flow?: string; finding?: string }) =>
     call<{ cluster: string | null; story?: string | null }>("GET", `/api/reviews/${id}/locate?${new URLSearchParams(q)}`),
   source: (id: number, path: string, side: "before" | "after" = "after") =>
```

`frontend/src/reading/plan.ts` (new file):

```ts
/** The reading plan (spec 2026-10-07-review-reading-phase2 §6): what each reader has ticked read, and how far along
 * they are. Ticks are the reader's own. */
import type { Reading } from "./types";

/** The signed-in reader's ticks on one review: story ids and To check keys. */
export interface ReadTicks { stories: string[]; checks: string[] }

/** The next story after `from` in reading order that the reader has not read, wrapping; null when every one is read. */
export function nextUnread(order: string[], read: ReadonlySet<string>, from: string): string | null {
  const at = order.indexOf(from);
  for (let i = 1; i <= order.length; i++) {
    const s = order[(at + i) % order.length];
    if (!read.has(s)) return s;
  }
  return null;
}

export interface Progress { stories: number; storyCount: number; checks: number; checkCount: number; all: boolean }

/** How many of the reading's stories and To check rows the reader has ticked; ticks it no longer holds don't count. */
export function progress(r: Reading, t: ReadTicks): Progress {
  const stories = new Set(t.stories), checks = new Set(t.checks);
  const read = r.order.filter((s) => stories.has(s)).length;
  return { stories: read, storyCount: r.order.length, checks: r.checks.filter((k) => checks.has(k.key)).length,
           checkCount: r.checks.length, all: r.order.length > 0 && read === r.order.length };
}

/** "7 of 12 stories read · 18 of 30 checks" (the checks part only when there are checks). */
export function progressText(p: Progress): string {
  return `${p.stories} of ${p.storyCount} stories read${p.checkCount ? ` · ${p.checks} of ${p.checkCount} checks` : ""}`;
}

/** A thread's "2 of 3": how many of its stories the reader has read. */
export function threadRead(stories: string[], read: ReadonlySet<string>): string {
  return `${stories.filter((s) => read.has(s)).length} of ${stories.length}`;
}
```

`frontend/src/workspace/CheckList.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/CheckList.tsx b/frontend/src/workspace/CheckList.tsx
index dcc36de..ed85b87 100644
--- a/frontend/src/workspace/CheckList.tsx
+++ b/frontend/src/workspace/CheckList.tsx
@@ -16,18 +16,20 @@ function CheckRow({ k, lit }: { k: Check; lit: boolean }) {
   const [busy, setBusy] = useState(false);
   const [error, setError] = useState<string | null>(null);
   const marked = !!m && !m.changed;
-  const toggle = () => {
+  const read = !!d.ticks?.checks.includes(k.key);          // this reader's own tick (phase 2 §6.3)
+  const run = (act: () => Promise<unknown>) => {
     setBusy(true);
     setError(null);
-    (marked ? api.unmarkCheck(d.id, k.key) : api.markCheck(d.id, k.key)).then(d.loadReading)
-      .catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
+    act().catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
   };
+  const toggle = () => run(() => (marked ? api.unmarkCheck(d.id, k.key) : api.markCheck(d.id, k.key))
+    .then(() => Promise.all([d.loadReading(), d.loadTicks()])));
   const li = useRef<HTMLLIElement>(null);
   useEffect(() => { if (lit) li.current?.scrollIntoView({ block: "center" }); }, [lit]);
   const talks = d.comments.filter((c) => c.parent_id === null && c.anchor_kind === "check" && c.anchor.key === k.key).length;
   const where = placeOf(k), place = `${k.path}${k.line ? ` at line ${k.line}` : ""}`;
   return (
-    <li ref={li} className={`ck-row${marked ? " marked" : ""}${lit ? " lit" : ""}`} data-key={k.key} data-finding={k.finding ?? undefined}>
+    <li ref={li} className={`ck-row${marked ? " marked" : ""}${read ? " read" : ""}${lit ? " lit" : ""}`} data-key={k.key} data-finding={k.finding ?? undefined}>
       {[{ kind: k.kind, text: k.text }, ...k.also].map((r, i) => (
         <div key={i} className="ck-top"><span className={`ck-tag ${r.kind}`}>{KIND_LABEL[r.kind]}</span>
           <span className="ck-text"><Ticks text={r.text} /></span></div>
@@ -37,6 +39,8 @@ function CheckRow({ k, lit }: { k: Check; lit: boolean }) {
       {m && <div className={`ck-mark${m.changed ? " changed" : ""}`}>{markLine(m)}</div>}
       <div className="ck-acts">
         <button className="link" onClick={toggle} disabled={busy} aria-pressed={marked}>{marked ? "Reopen" : "Looks fine"}</button>
+        {d.ticks && <label className="ck-read"><input type="checkbox" checked={read} disabled={busy}
+                                                      onChange={() => run(() => d.tick("check", k.key, !read))} /> Read</label>}
         <button className="link" onClick={() => setTalk(!talk)} aria-expanded={talk}>Comment{talks ? ` (${talks})` : ""}</button>
         {k.depot && <Link to={ws.link(ws.opened({ file: k.depot, line: k.line }))} title={`Open ${place}`} aria-label={`Open ${place}`}>Open</Link>}
         {k.finding && <Link to={ws.link(at({ kind: "finding", fid: k.finding }, { details: true }))} title={`Finding ${k.finding}'s details`}
```

`frontend/src/workspace/StoryPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/StoryPage.tsx b/frontend/src/workspace/StoryPage.tsx
index 5a5e968..94979ec 100644
--- a/frontend/src/workspace/StoryPage.tsx
+++ b/frontend/src/workspace/StoryPage.tsx
@@ -1,10 +1,11 @@
 import { useEffect, useState } from "react";
-import { Link } from "react-router-dom";
+import { Link, useNavigate } from "react-router-dom";
 import { ApiError } from "../api";
 import type { StoryDetail } from "../board/types";
 import Comments from "../components/Comments";
 import Explain from "../components/Explain";
 import { isOpen } from "../reading/checks";
+import { nextUnread } from "../reading/plan";
 import { clCounts, stepIn, threadCrumb } from "../reading/story";
 import { countLine, reviewTargets, stepStory } from "../stories/stories";
 import { type Address, at as addressAt } from "./address";
@@ -19,6 +20,32 @@ import { StoryChecks, StoryWhy } from "./StoryPlan";
 import StorySteps from "./StorySteps";
 import StoryTiles from "./StoryTiles";
 
+/** Mark as read beside ‹ › (spec 2026-10-07-review-reading-phase2 §6.2): ticks the story for this reader and goes to
+ * the next unread story in reading order, or to the overview once every story is read; a read story offers Mark unread. */
+function MarkRead({ sid, order }: { sid: string; order: string[] }) {
+  const ws = useWs(), d = ws.data, navigate = useNavigate();
+  const [busy, setBusy] = useState(false);
+  const [error, setError] = useState<string | null>(null);
+  const read = d.ticks!.stories.includes(sid);
+  const act = (on: boolean) => {
+    setBusy(true);
+    setError(null);
+    d.tick("story", sid, on).then(() => {
+      if (!on) return;
+      const next = nextUnread(order, new Set([...d.ticks!.stories, sid]), sid);
+      if (next) ws.go(ws.item({ kind: "story", sid: next, view: "steps" }));
+      else navigate(ws.link(addressAt({ kind: "whole" })), { state: { page: true } });
+    }).catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
+  };
+  return (
+    <span className="st-read">
+      {read ? <>✓ Read · <button className="link" onClick={() => act(false)} disabled={busy}>Mark unread</button></>
+        : <button onClick={() => act(true)} disabled={busy}>Mark as read</button>}
+      {error && <span className="banner warn">{error}</span>}
+    </span>
+  );
+}
+
 /** A story (spec 2026-10-04-review-workspace §3.2): header with the Steps | Graph switch beside the title and ‹ › in a
  * fixed-width group; its tiles (spec 2026-10-07-review-reading §6) or its graph with the flow strip. A review run before
  * the reading keeps ‹ S1 of 4 › and the steps with the flow strip. */
@@ -78,6 +105,7 @@ export default function StoryPage({ sid, view }: { sid: string; view: "steps" |
           </span>
         )}
         <span className="ws-pos">{step(-1)}<span>{r ? (crumb?.text ?? st.id) : `${st.id} of ${ss.stories.length}`}</span>{step(1)}</span>
+        {r && d.ticks && <MarkRead sid={sid} order={r.order} />}
       </div>
       <p>{!r && <NameText text={st.summary} />} {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} askOnly={st.source === "tier1"} ask={{ kind: "story", anchor: { id: st.id }, onAsked: d.loadComments }} />}</p>
       <p className="ws-story-meta">{!r && <span className="muted">{countLine(st)}</span>}
```

`frontend/src/workspace/useReview.ts` (diff):

```diff
diff --git a/frontend/src/workspace/useReview.ts b/frontend/src/workspace/useReview.ts
index 4f9bc0c..3e25a9d 100644
--- a/frontend/src/workspace/useReview.ts
+++ b/frontend/src/workspace/useReview.ts
@@ -4,6 +4,7 @@ import { useCallback, useEffect, useMemo, useRef, useState } from "react";
 import { api, ApiError, type AiJob, type Board, type Comment, type FileChange, type Finding, type Names, type Overview,
   type Reading, type ReviewDetail, type StoryDetail, type StorySet } from "../api";
 import { useAiState } from "../lib/ai";
+import type { ReadTicks } from "../reading/plan";
 
 const TERMINAL = new Set(["done", "degraded", "failed"]);
 const missing = <T,>(fallback: T) => (e: unknown): T => {
@@ -21,6 +22,7 @@ export function useReview(id: number) {
   const [comments, setComments] = useState<Comment[]>([]);
   const [names, setNames] = useState<Names>({});
   const [reading, setReading] = useState<Reading | null | undefined>(undefined);   // null: run before the reading existed
+  const [ticks, setTicks] = useState<ReadTicks | null>(null);                          // the reader's own (phase 2 §6)
   const [reload, setReload] = useState(0);                // story pages and cluster graphs fetch again: new results, AI text
   const [error, setError] = useState<string | null>(null);
 
@@ -31,12 +33,15 @@ export function useReview(id: number) {
   const loadStories = useCallback(() => api.stories(id).then(setStories, (e) => setStories(missing(null)(e))), [id]);
   const loadNames = useCallback(() => api.names(id).then(setNames).catch(() => { /* names fall back to "a function" */ }), [id]);
   const loadReading = useCallback(() => api.reading(id).then(setReading, (e) => setReading(missing(null)(e))), [id]);
+  const loadTicks = useCallback(() => api.ticks(id).then(setTicks, () => setTicks(null)), [id]);
+  /** Tick or untick a story or check for the reader, then show what the server holds. */
+  const tick = useCallback((kind: "story" | "check", key: string, on: boolean) => api.tick(id, kind, key, on).then(loadTicks), [id, loadTicks]);
   const loadBoard = useCallback(() => api.board(id).then(setBoard, (e) => setBoard(missing(null)(e))), [id]);
   const loadResults = useCallback(() => (setReload((k) => k + 1), Promise.all([
     api.overview(id).then((ov) => { setOverview(ov); setBoard(null); },
                           (e) => { setOverview(missing(null)(e)); return loadBoard(); }),
-    loadStories(), loadFindings(), api.files(id).then(setFiles), loadComments(), loadNames(), loadReading(),
-  ]).catch(fail)), [id, loadBoard, loadStories, loadFindings, loadComments, loadNames, loadReading, fail]);
+    loadStories(), loadFindings(), api.files(id).then(setFiles), loadComments(), loadNames(), loadReading(), loadTicks(),
+  ]).catch(fail)), [id, loadBoard, loadStories, loadFindings, loadComments, loadNames, loadReading, loadTicks, fail]);
 
   useEffect(() => { loadDetail(); }, [loadDetail]);
   const status = detail?.review.status;
@@ -79,10 +84,10 @@ export function useReview(id: number) {
   const ai = useAiState(id, ready, people, comments.some((c) => c.ai_meta?.pending), onAiDone, loadComments);
   const about = (board ?? overview)?.about ?? null;
 
-  return useMemo(() => ({ id, detail, board, overview, stories, findings, files, comments, names, reading, about, reload, error,
-                         ready, ai, story, loadDetail, loadComments, loadFindings, loadReading }),
-                 [id, detail, board, overview, stories, findings, files, comments, names, reading, about, reload, error, ready, ai,
-                  story, loadDetail, loadComments, loadFindings, loadReading]);
+  return useMemo(() => ({ id, detail, board, overview, stories, findings, files, comments, names, reading, ticks, about, reload, error,
+                         ready, ai, story, loadDetail, loadComments, loadFindings, loadReading, loadTicks, tick }),
+                 [id, detail, board, overview, stories, findings, files, comments, names, reading, ticks, about, reload, error, ready, ai,
+                  story, loadDetail, loadComments, loadFindings, loadReading, loadTicks, tick]);
 }
 
 export type ReviewData = ReturnType<typeof useReview>;
```

`frontend/src/workspace/workspace.css` (diff):

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 7d7c2b5..832933d 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -459,6 +459,11 @@ a.ws-nb:hover { border-color: var(--accent); }
 .ws-switch a.on { background: var(--accent); color: var(--surface); }
 .ws-pos { display: inline-flex; align-items: center; gap: 6px; flex: none; font-size: 12.5px; color: var(--muted); }
 .ws-pos > span { width: 5.5em; text-align: center; font-variant-numeric: tabular-nums; }
+/* The reading plan (spec 2026-10-07-review-reading-phase2 §6): Mark as read, a check's Read box */
+.st-read { display: inline-flex; align-items: center; gap: 6px; flex: none; font-size: 12.5px; color: var(--muted); }
+.st-read > button:not(.link) { padding: 2px 10px; font-size: 12.5px; }
+.ck-read { display: inline-flex; align-items: center; gap: 4px; font-size: 12.5px; color: var(--muted); cursor: pointer; }
+.ck-row.read:not(.marked) { opacity: .75; }
 .ws-step-btn { width: 30px; text-align: center; text-decoration: none; display: inline-block; }
 .ws-story-head p { margin: 8px 0 0; font-size: 14.5px; }
 .ws-story-meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd frontend && npx vitest run src/reading/plan.test.ts`
Expected: PASS: `Tests 3 passed (3)`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-plan.spec.ts`
Expected: PASS: `2 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `637 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 183 passed (183)`; Playwright `111 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-plan.spec.ts frontend/src/reading/plan.test.ts frontend/src/api.ts frontend/src/reading/plan.ts frontend/src/workspace/CheckList.tsx frontend/src/workspace/StoryPage.tsx frontend/src/workspace/useReview.ts frontend/src/workspace/workspace.css
git commit -m "feat(plan): Mark as read ticks a story for the reader and goes to the next unread one; each To check row has the reader's own Read box, and Looks fine ticks it"
```

### Task 9: Progress

Spec §6.2, §6.4. The header shows "7 of 12 stories read · 18 of 30 checks" beside the headline (hidden on a phone). The rail puts ✓ beside each read story and a thread's "2 of 3" in its heading. The overview gives each thread card "2 of 3 read" and opens with the reader's progress, or "You've read every story". The phase-1 rail test's thread headings gain the count.

**Files:**
- Test: `frontend/e2e/workspace-plan.spec.ts`
- Test: `frontend/e2e/workspace-reading.spec.ts`
- Modify: `frontend/src/workspace/Overview.tsx`
- Modify: `frontend/src/workspace/Rail.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: `progress`, `progressText`, `threadRead`, `useReview().ticks` (Task 8).
- Produces: CSS `.ws-progress`, `.ws-read`, `.ws-thread-read`, `.ov-read`, `.ov-progress` (`.done`).

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-plan.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-plan.spec.ts b/frontend/e2e/workspace-plan.spec.ts
index ad3af53..722efa2 100644
--- a/frontend/e2e/workspace-plan.spec.ts
+++ b/frontend/e2e/workspace-plan.spec.ts
@@ -1,4 +1,4 @@
-import { expect, type Page, test } from "@playwright/test";
+import { devices, expect, type Page, test } from "@playwright/test";
 import { login, startReview } from "./helpers";
 
 /** The reading plan (spec 2026-10-07-review-reading-phase2 §6): each reader's own ticks on stories and checks. */
@@ -8,9 +8,54 @@ async function readingOf(page: Page, base: string): Promise<{ order: string[]; c
   return (await page.request.get(`/api${base.replace("/r/", "/reviews/")}/reading`)).json();
 }
 
+/** Re-run the review and wait until the new run's reading is stored. */
+async function rerun(page: Page, base: string) {
+  const id = base.split("/")[2];
+  const finished = async () => {
+    const d = await (await page.request.get(`/api/reviews/${id}`)).json();
+    return { status: d.review.status as string, at: d.stages.find((s: { name: string }) => s.name === "reading")?.finished_at as string };
+  };
+  const before = (await finished()).at;
+  expect((await page.request.post(`/api/reviews/${id}/rerun`)).ok()).toBe(true);
+  await expect.poll(async () => { const f = await finished(); return f.at !== before && ["done", "degraded"].includes(f.status); },
+                    { timeout: 60_000 }).toBe(true);
+}
+
 test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
+  test("progress shows in the header, the rail and the overview; the last story read leads to the overview", async ({ page }) => {
+    const base = await startReview(page, FOUR);
+    const { order, checks } = await readingOf(page, base);
+    const head = page.locator(".ws-head .ws-progress");
+    await expect(head).toHaveText(`0 of ${order.length} stories read · 0 of ${checks.length} checks`);
+    for (const sid of order.slice(0, -1))
+      expect((await page.request.put(`/api${base.replace("/r/", "/reviews/")}/ticks/story/${sid}`)).ok()).toBe(true);
+    await page.goto(`${base}/s/${order.at(-1)}`);
+    await expect(head).toHaveText(`${order.length - 1} of ${order.length} stories read · 0 of ${checks.length} checks`);
+    const rail = page.locator(".ws-rail");
+    await expect(rail.locator(".ws-read")).toHaveCount(order.length - 1);
+    await expect(rail.getByRole("link", { name: new RegExp(`^Go to story ${order[0]}: .* \\(read\\)$`) })).toBeVisible();
+    await expect(rail.locator(".ws-thread .ws-thread-read").first()).toHaveText(/^\d+ of \d+$/);
+    await page.getByRole("button", { name: "Mark as read" }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}$`));
+    await expect(page.locator(".ov-progress")).toHaveText("You've read every story");
+    await expect(head).toHaveText(`${order.length} of ${order.length} stories read · 0 of ${checks.length} checks`);
+    await expect(page.locator(".ov-thread .ov-read").first()).toHaveText(/^(\d+) of \1 read$/);
+  });
+
+  test("a re-run clears every reader's ticks", async ({ page }) => {
+    const base = await startReview(page, FOUR);
+    const { order } = await readingOf(page, base);
+    await page.goto(`${base}/s/${order[0]}`);
+    await page.getByRole("button", { name: "Mark as read" }).click();
+    await expect(page.locator(".ws-head .ws-progress")).toContainText(`1 of ${order.length} stories read`);
+    await rerun(page, base);
+    await page.reload();
+    await expect(page.locator(".ws-head .ws-progress")).toContainText(`0 of ${order.length} stories read`);
+    await expect(page.locator(".ws-rail .ws-read")).toHaveCount(0);
+  });
+
   test("Mark as read ticks the story and goes to the next unread one; a read story offers Mark unread", async ({ page }) => {
     const base = await startReview(page, FOUR);
     const { order } = await readingOf(page, base);
@@ -51,3 +96,21 @@ test.describe("desktop", () => {
     await other.context().close();
   });
 });
+
+test.describe("phone", () => {
+  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
+    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });
+
+  test("the overview carries the progress the header leaves out, and Mark as read fits", async ({ page }) => {
+    const base = await startReview(page, FOUR);
+    const { order } = await readingOf(page, base);
+    await page.goto(`${base}/s/${order[0]}`);
+    await expect(page.locator(".ws-head .ws-progress")).toBeHidden();
+    await page.getByRole("button", { name: "Mark as read" }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}/s/${order[1]}$`));
+    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
+    await page.goto(base);
+    await page.getByRole("link", { name: "Go to the overview" }).click();
+    await expect(page.locator(".ov-progress")).toContainText(`1 of ${order.length} stories read`);
+  });
+});
```

`frontend/e2e/workspace-reading.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-reading.spec.ts b/frontend/e2e/workspace-reading.spec.ts
index 1de10fc..c8c291e 100644
--- a/frontend/e2e/workspace-reading.spec.ts
+++ b/frontend/e2e/workspace-reading.spec.ts
@@ -108,7 +108,8 @@ test.describe("desktop", () => {
     const base = await startReview(page, FOUR);
     const rail = page.locator(".ws-rail");
     await expect(rail.getByRole("link", { name: "Go to the overview" })).toContainText("Medium risk · rules only");
-    await expect(rail.locator(".ws-thread h3")).toHaveText(["A hal_write in hal5", "B logger_init in service", "C svc::Engine::step in cpp1"]);
+    await expect(rail.locator(".ws-thread h3")).toHaveText(["A hal_write in hal50 of 2", "B logger_init in service0 of 2",
+                                                        "C svc::Engine::step in cpp10 of 1"]);   // open checks, then stories read
     await expect(rail.locator(".ws-thread").first().getByRole("link", { name: /^Go to story/ })).toHaveCount(2);
     await expect(rail.locator(".ws-thread").first().getByRole("link").nth(1)).toHaveAccessibleName(/^Go to story S1/);
     await expect(rail.locator(".ws-missed .ck-count")).toHaveText("6 open");
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-plan.spec.ts e2e/workspace-reading.spec.ts`
Expected: FAIL: `4 failed, 9 passed`; the first error is `Error: expect(locator).toHaveText(expected) failed`

- [ ] **Step 3: Implement**

`frontend/src/workspace/Overview.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Overview.tsx b/frontend/src/workspace/Overview.tsx
index 6c603d7..1b5a602 100644
--- a/frontend/src/workspace/Overview.tsx
+++ b/frontend/src/workspace/Overview.tsx
@@ -2,6 +2,7 @@ import { useState } from "react";
 import { Link } from "react-router-dom";
 import { byThread, letter } from "../reading/checks";
 import { arcLayout, connectionRows, testsLine } from "../reading/overview";
+import { progress, progressText, threadRead } from "../reading/plan";
 import type { Reading, Thread } from "../reading/types";
 import CheckTile, { Cleared } from "./CheckList";
 import { useWs } from "./context";
@@ -72,6 +73,7 @@ function ThreadCard({ t, i, r }: { t: Thread; i: number; r: Reading }) {
           <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
         ))}
         {t.open_checks > 0 && <span className="ck-count">{t.open_checks} open</span>}
+        {ws.data.ticks && <span className="ov-read">{threadRead(t.stories, new Set(ws.data.ticks.stories))} read</span>}
       </header>
       {t.purpose && <p className="ov-purpose"><Ticks text={t.purpose} /></p>}
       <ol className="ov-stories">{t.stories.map((sid) => {
@@ -94,9 +96,11 @@ function ThreadCard({ t, i, r }: { t: Thread; i: number; r: Reading }) {
 export default function Overview({ r }: { r: Reading }) {
   const ws = useWs(), ss = ws.data.stories;
   const tests = r.tests?.stories[0], testsStory = tests ? ss?.stories.find((s) => s.id === tests) : null;
+  const p = ws.data.ticks ? progress(r, ws.data.ticks) : null;          // the reader's progress (phase 2 §6.2, §6.4)
   return (
     <div className="ws-page"><div className="ov2">
       <div className="ov2-left ws-whole">
+        {p && <p className={`ov-progress${p.all ? " done" : ""}`}>{p.all ? "You've read every story" : progressText(p)}</p>}
         <section aria-labelledby="ov-whole">
           <h2 id="ov-whole">The change as a whole</h2>
           <p className="ws-lead">{r.whole_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={r.whole} /></p>
```

`frontend/src/workspace/Rail.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Rail.tsx b/frontend/src/workspace/Rail.tsx
index 9ba59ee..fc4a82a 100644
--- a/frontend/src/workspace/Rail.tsx
+++ b/frontend/src/workspace/Rail.tsx
@@ -7,6 +7,7 @@ import HeadlinePill from "../components/HeadlinePill";
 import { plainTitle } from "../lib/markdown";
 import { tidy } from "../lib/tidy";
 import { isOpen, letter, openCount } from "../reading/checks";
+import { threadRead } from "../reading/plan";
 import { reviewTargets, sections } from "../stories/stories";
 import { INDEX_TABS, type Place, samePlace } from "./address";
 import { useWs } from "./context";
@@ -84,9 +85,11 @@ export default function Rail({ show, onPick, hidden = false }: { show: string |
     const byId = new Map(ss.stories.map((st) => [st.id, st]));
     const open = r.checks.filter((k) => isOpen(k, r.marks)).length;
     const tests = ss.stories.filter((st) => st.kind === "tests");
-    const storyRow = (st: Story, why?: string) => { const reason = st.kind === "unsorted" ? "Needs a person to place it" : why; return row({ kind: "story", sid: st.id, view: "steps" }, `Go to story ${st.id}: ${short(st.title)}`, <>
+    const read = d.ticks ? new Set(d.ticks.stories) : null;     // the reader's own ticks (phase 2 §6.4)
+    const storyRow = (st: Story, why?: string) => { const reason = st.kind === "unsorted" ? "Needs a person to place it" : why; return row({ kind: "story", sid: st.id, view: "steps" }, `Go to story ${st.id}: ${short(st.title)}${read?.has(st.id) ? " (read)" : ""}`, <>
       <span className="ws-row-top">
         <span className="ws-row-title"><Ticks text={st.title} /></span>
+        {read?.has(st.id) && <span className="ws-read" aria-hidden>✓</span>}
         <span className="ws-handle">{st.id}</span>
       </span>
       {(reason || (manyTargets && (st.targets ?? []).length > 0)) && <span className="ws-chips">
@@ -105,7 +108,8 @@ export default function Rail({ show, onPick, hidden = false }: { show: string |
           {r.threads.map((t, i) => (
             <div key={t.id} className="ws-group ws-thread">
               <h3><span className="ov-letter">{letter(i, t.id)}</span> <Ticks text={t.name} />
-                {t.open_checks > 0 && <span className="ck-count">{t.open_checks}</span>}</h3>
+                {t.open_checks > 0 && <span className="ck-count">{t.open_checks}</span>}
+                {read && <span className="ws-thread-read">{threadRead(t.stories, read)}</span>}</h3>
               <ul>{t.stories.map((sid) => byId.get(sid) && <li key={sid}>{storyRow(byId.get(sid)!, r.reasons[sid])}</li>)}</ul>
             </div>
           ))}
```

`frontend/src/workspace/Workspace.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index 2a9a976..61aa157 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -9,6 +9,7 @@ import { useSources } from "../board/useSources";
 import Stages from "../components/Stages";
 import { AiProvider, useAi } from "../lib/ai";
 import { threadLabel } from "../reading/checks";
+import { progress, progressText } from "../reading/plan";
 import { type Address, at, href, type Open, type Place, readAddress, type Tab } from "./address";
 import { useWs, type Ws, WsContext } from "./context";
 import Crumbs, { PhoneBar } from "./Crumbs";
@@ -133,6 +134,7 @@ function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
       <h1><Link to={ws.base} state={{ page: true }} title="Go to the whole change">{r.title}</Link></h1>
       {d.reading ? <HeadlinePill h={d.reading.headline} />
         : r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
+      {d.reading && d.ticks && <span className="ws-progress">{progressText(progress(d.reading, d.ticks))}</span>}
       {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
       {d.ready && <AiPill />}
       {me?.is_owner && d.ready && <button className="link rerun" onClick={() => api.rerun(d.id).then(d.loadDetail)}>Re-run</button>}
```

`frontend/src/workspace/workspace.css` (diff):

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 832933d..d86bbbc 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -464,6 +464,12 @@ a.ws-nb:hover { border-color: var(--accent); }
 .st-read > button:not(.link) { padding: 2px 10px; font-size: 12.5px; }
 .ck-read { display: inline-flex; align-items: center; gap: 4px; font-size: 12.5px; color: var(--muted); cursor: pointer; }
 .ck-row.read:not(.marked) { opacity: .75; }
+.ws-progress { font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums; }
+.ws-read { flex: none; color: var(--ok); font-size: 12px; }
+.ws-thread-read, .ov-read { margin-left: 6px; font-size: 11.5px; font-weight: 500; color: var(--muted); font-variant-numeric: tabular-nums; }
+.ov-progress { margin: 0 0 14px; font-size: 13px; color: var(--muted); }
+.ov-progress.done { color: var(--ink); font-weight: 600; }
+@media (max-width: 640px) { .ws-progress { display: none; } }
 .ws-step-btn { width: 30px; text-align: center; text-decoration: none; display: inline-block; }
 .ws-story-head p { margin: 8px 0 0; font-size: 14.5px; }
 .ws-story-meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-plan.spec.ts e2e/workspace-reading.spec.ts`
Expected: PASS: `13 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `637 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 183 passed (183)`; Playwright `1 failed, 113 passed` (in the replay, the first run's failures were timeouts under load; `npx playwright test --last-failed` then gave `1 passed`)

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-plan.spec.ts frontend/e2e/workspace-reading.spec.ts frontend/src/workspace/Overview.tsx frontend/src/workspace/Rail.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/workspace.css
git commit -m "feat(plan): each reader's progress — stories and checks read in the header, ✓ and a thread's "2 of 3" in the rail, each thread card's count and "You've read every story" on the overview"
```

## Finish

Every task's suite is green. The branch stays `review-reading-2`; merging it is the owner's decision. Use superpowers:finishing-a-development-branch.
