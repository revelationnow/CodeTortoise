# Outline Layout and Checks by Cause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rail and the To check column with an outline (Stories | Checks), group checks by the change that raised them and walk each group with a stepper that shows the change above every place, hide Confirm by default, turn the story page's sections into tabs and calm the overview.

**Architecture:** The reading stage keeps every check row apart (no merge by place), groups rows into `Cause`s (id from kind, function and subject; text; places; flows touched; the 2–6 changed lines) in a new `causes.py`, and stores them on the reading and each story's reading. The frontend gets a pure `reading/causes.ts` (hidden kinds, open places, order, next open), a fourth panel item `{cause, at}` rendered by `CauseStepper`, an `Outline` replacing `Rail` for reviews with a reading, tabs on the story page, and a rebuilt overview; `CheckColumns` and the To check tiles go.

**Tech Stack:** FastAPI / pydantic v2 / SQLite backend (pytest, ruff); React 19 + TypeScript + Vite (vitest, Playwright e2e with fixture servers).

**Spec:** `docs/superpowers/specs/2026-10-16-outline-and-causes-design.md` (approved 2026-10-16, commit 5bd4ab9).

## Global Constraints

- The repo is public: never use the owner's proprietary identifiers in code, tests, docs or commits; examples use the fixture names (`uart_send`, `logger_flush`, `dev->status`, `stats_b1`…).
- Commit with `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`; every message ends with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH`.
- Backend tests: from `backend/`, `env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests`; lint `../../../backend/.venv/bin/ruff check codetortoise tests`. Never use `uv`.
- Frontend: from `frontend/`, `npx vitest run`, `npx tsc -b --noEmit`, `npm run build` (the e2e servers serve `frontend/dist`: rebuild before every e2e run).
- e2e: `TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=<worktree>/backend /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test …` (create `.pwtmp` first, delete it when done).
- Storage keys (spec): `ct.ws.outline` (`"stories"` | `"checks"`, default `"stories"`), `ct.ws.hiddenKinds` (list of kinds, default `["confirm"]`), `ct.ws.railFolded` (kept). Removed: `ct.ws.checkFolded`, `ct.ws.checkW`. Every storage read and write in try/catch (`board/prefs.ts` `load`/`save` already are).
- Addresses (spec): `?open=cause:<id>&at=<n>` (1-based), story section `?sec=` (`contracts`, `where`, `paths`, `code`, `talk`; `flows` is the default and left out), the Graph tab is the existing `?view=graph`.
- Cause id: `"c" + sha1("<kind>|<qualified function name>|<subject>").hexdigest()[:10]`.
- Cause text (spec §4.2) with one refinement: a reader cause of several places names its writer ("5 places read \`UartDev::errors\`, which \`uart_a1\` now writes"), because the large fixture has ten writers of one field, each its own cause, and ten identical lines would be useless.
- `READING_VERSION` goes from 2 to 3.
- Long-text rules: one-line labels end in an ellipsis with the whole text on hover (`title`); sentences wrap.
- No node id (`N<digits>`) is ever shown: cause lines, check texts, `also:` lines and "found no hazard" reasons render through `NameText`.

## Review Focus

1. A review stored before this change (reading without `causes`): every page must still load; the outline's Checks view says "Re-run the review to group its checks" and the story shows no chips (Task 7, Task 10 tests).
2. A cause whose places are all marked, then one place's line changes (mark `changed`): the cause reopens and Next open check finds it (Task 5 unit test).
3. Every shown cause is done or every kind is hidden: Next open check is not shown and no chip strip appears (Task 5, Task 9, Task 10 tests).
4. A place whose file text isn't available (unchanged file not yet fetched, or fetch fails): the stepper says "No code for this place" and keeps its actions (Task 8 e2e).
5. J/K/F typed while writing a comment in the stepper must type letters, not step (Task 8 e2e).

---

## File Structure

Backend:
- `backend/codetortoise/reading.py` — `Check` loses `also`, gains `cause` (+ excluded `cause_fn`, `cause_subject`); `Reason` and `_merge` removed; new models `ChangeLine`, `CauseChange`, `Cause`; `Reading.causes`, `StoryReading.causes`; `build_reading` calls `build_causes`; `READING_VERSION = 3`.
- `backend/codetortoise/causes.py` (new) — grouping, ids, text, flows, order (`build_causes`), the change's lines (`change_for`).
- `backend/codetortoise/web/app.py` — `POST /api/reviews/{rid}/checks/marks`.
- Tests: `backend/tests/test_reading.py` (merge test replaced), `backend/tests/test_causes.py` (new), `backend/tests/test_web.py` (batch marks).

Frontend:
- `frontend/src/reading/types.ts` — `Cause`, `CauseChange`, `ChangeLine`; `Check.cause`; `Reading.causes?`, `StoryReading.causes?`; `Reason`/`also` removed.
- `frontend/src/reading/causes.ts` (new) + `causes.test.ts` — hidden kinds, open places, counts, order helpers, next open, stepping.
- `frontend/src/api.ts` — `markChecks`.
- `frontend/src/board/prefs.ts` — keys `outline`, `hiddenKinds`; `checkW`, `checkFolded` removed.
- `frontend/src/workspace/address.ts` (+ test) — `Open` `{cause, at}`, `Address.sec`, `StorySec`, `INDEX_TABS` without `checks`.
- `frontend/src/workspace/memory.ts` (+ test), `tabs.ts` (+ test) — the cause item.
- `frontend/src/workspace/CauseStepper.tsx` (new) — the stepper; `Detail.tsx` renders it.
- `frontend/src/workspace/Outline.tsx` (new) — Stories and Checks views; `Workspace.tsx` uses it when there is a reading; `context.ts` folds without `check`.
- `frontend/src/workspace/Workspace.tsx` `Head` — Next open check, the **?** help.
- `frontend/src/workspace/HowToRead.tsx` (new, moved out of `Overview.tsx`).
- `frontend/src/workspace/StoryTabs.tsx` (new) — the tabbed story body; replaces `StoryTiles.tsx`; `StoryPage.tsx` header rewritten.
- `frontend/src/workspace/Overview.tsx` — rebuilt.
- Removed: `CheckColumns.tsx`, `StoryTiles.tsx`, `CheckList.tsx`'s `CheckTile`/`CheckRow` (its `Cleared` moves into `Outline.tsx`), Index › Checks.
- `frontend/src/workspace/workspace.css` — outline, stepper, tabs, overview styles; To check column styles removed.
- e2e: `frontend/e2e/helpers.ts`, the specs listed in Task 13, new `frontend/e2e/outline-causes.spec.ts`.

---
### Task 1: Check rows stay apart and carry what makes their cause

**Files:**
- Modify: `backend/codetortoise/reading.py` (`Reason`, `Check`, `build_checks`, `_merge`)
- Test: `backend/tests/test_reading.py` (replace `test_two_kinds_at_one_place_merge_into_one_row_listing_both_reasons`)

**Interfaces:**
- Produces: `Check.cause: str | None = None` (set in Task 2); `Check.cause_fn: str | None` (node id of the changed function behind the row, excluded from dumps); `Check.cause_subject: str` (excluded from dumps). `Check.also` and `Reason` no longer exist. `build_checks(...)` returns `(rows, cleared)` with every row its own place, sorted by kind order, path, line.

- [ ] **Step 1: Replace the merge test with the new rule**

In `backend/tests/test_reading.py`, replace the whole `test_two_kinds_at_one_place_merge_into_one_row_listing_both_reasons` function with:

```python
def test_two_kinds_at_one_place_stay_two_rows_each_knowing_what_raised_it():
    c, ss = _caller_world(returns=(["0"], ["0", "-2"]))
    next(e for e in c.after[0].calls if e.caller == "c:@F@flush").result_used = False
    open_, _ = _checks(c, ss)
    assert [(k.kind, k.function) for k in open_] == [("caller", "flush"), ("result", "flush")]
    assert [(k.cause_fn, k.cause_subject) for k in open_] == [("N1", ""), ("N1", "-2")]
    assert "also" not in open_[0].model_dump() and "cause_fn" not in open_[0].model_dump()


def test_each_kind_records_the_subject_that_makes_two_rows_one_cause():
    c = _world([_edit("config", "drv/cfg.c"), _same("report", "svc/rep.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged")])
    ss = _set(["N1"])
    ss.finding_story = {"F1": "S1"}
    c.findings = [_f("F1", verdict="hazard", reason="drops data", source="tier1")]
    open_, _ = _checks(c, ss)
    assert {(k.kind, k.cause_fn, k.cause_subject) for k in open_} == {
        ("hazard", "N1", "contract:contract F1"), ("reader", "N1", "Uart::errors")}
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_reading.py -k "stay_two_rows or records_the_subject"`
Expected: FAIL (`AttributeError` / `ValueError` on `cause_fn`, or one merged row).

- [ ] **Step 3: Implement**

In `backend/codetortoise/reading.py`:

1. Delete `class Reason`.
2. In `class Check`, replace the `also` line with:

```python
    cause: str | None = None          # its cause's id (spec 2026-10-16-outline-and-causes §4.1); none on a cleared row
    cause_fn: str | None = Field(default=None, exclude=True)   # the changed function that raised it (node id)
    cause_subject: str = Field(default="", exclude=True)       # what makes two rows of its kind one cause
```

3. In `build_checks`, make `add` record the function behind every row: change the `rows.append(Check(...))` call so it passes `cause_fn=related` (keep every other argument; `**kw` may carry `cause_subject`):

```python
        rows.append(Check(key=f"{kind}|{rel_path(x, path)}|{func or ''}|{_qual(x, related) if related else kw.pop('rel', '')}",
                          kind=kind, story=story, thread=thread_of.get(story) if story else kw.pop("thread", None),
                          path=rel_path(x, path), line=line, function=func, node=place, text=tidy(text),
                          source_line=_source(x, path, line, read_text), cause_fn=related, **kw))
```

4. Subjects, in the same function:
   - findings: `common = dict(story=story, finding=f.id, cites=f.verdict_cites, cause_subject=f"{f.kind}:{f.title}")`
   - the two `add("result", ...)` calls: add `cause_subject=",".join(sorted(new))`
   - the call-site `add("target", n, caller, ...)`: add `cause_subject=", ".join(sorted(where_))`
   - the reader `add("reader", ...)`: add `cause_subject=x.label(w.dst)` (beside `field=`)
   - the header `add("target", None, None, files[0], None, ...)`: add `cause_subject=rel_path(x, h)`
5. Replace `_merge` with an order that keeps every row:

```python
def _order(rows: list[Check]) -> list[Check]:
    """Kind order, then place; every row stays its own place under its own cause (spec 2026-10-16 §4.1)."""
    rank = {k: i for i, k in enumerate(CHECK_ORDER)}
    return sorted(rows, key=lambda k: (rank[k.kind], k.path, k.line or 0))
```

and change `build_checks`'s return to `return _unique(_order(rows)), _unique(cleared)`.

- [ ] **Step 4: Run the reading and web tests**

Run: `cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_reading.py tests/test_web.py`
Expected: PASS. If another test asserted a merged row (search `also` in `tests/`), update it to expect the two rows.

- [ ] **Step 5: Lint and commit**

```bash
cd backend && ../../../backend/.venv/bin/ruff check codetortoise tests
git add backend/codetortoise/reading.py backend/tests/test_reading.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): check rows stay apart and record the change that raised them

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 2: Causes — grouping, ids, text, flows, order, stored on the reading

**Files:**
- Create: `backend/codetortoise/causes.py`
- Modify: `backend/codetortoise/reading.py` (models `ChangeLine`, `CauseChange`, `Cause`; `Reading.causes`; `StoryReading.causes`; `build_reading`; `READING_VERSION = 3`)
- Test: `backend/tests/test_causes.py` (new)

**Interfaces:**
- Consumes: `Check.cause_fn`, `Check.cause_subject` (Task 1).
- Produces:
  - `reading.ChangeLine(sign: Literal["+", "-", " "], text: str, line: int | None = None)`
  - `reading.CauseChange(path: str, depot: str | None = None, function: str | None = None, lines: list[ChangeLine])`
  - `reading.Cause(id, kind, thread, story, text, places: list[str], flows: list[str], finding: str | None, change: CauseChange | None)`
  - `causes.cause_id(kind: str, qual: str, subject: str) -> str`
  - `causes.build_causes(rows: list[Check], x: _Ctx, threads: list[Thread], order: list[str], flows_of: dict[str, list[Flow]]) -> list[Cause]` — sets `row.cause` on every row; returns causes in reading order.
  - `Reading.causes: list[Cause]`, `StoryReading.causes: list[Cause]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_causes.py`:

```python
"""Checks grouped by cause (spec 2026-10-16-outline-and-causes §4)."""
import hashlib

from test_reading import _caller_world, _checks, _f, _set, _x
from test_stories import _edit, _same, _world

from codetortoise.board import Flow
from codetortoise.causes import build_causes, cause_id
from codetortoise.reading import Thread, build_reading


def _readers(*readers, writer="config", field="errors"):
    fns = [_edit(writer, "drv/cfg.c"), *(_same(r, f"svc/{r}.c") for r in readers)]
    fields = [(writer, "Uart", field, "write", "added"), *((r, "Uart", field, "read", "unchanged") for r in readers)]
    return _world(fns, fields=fields)


def _causes(c, ss, flows_of=None, threads=None):
    threads = threads or [Thread(id="T1", name="t", purpose="", stories=[s.id for s in ss.stories])]
    rows, _ = _checks(c, ss, threads=threads)
    return rows, build_causes(rows, _x(c), threads, [s for t in threads for s in t.stories], flows_of or {})


def test_readers_of_one_field_written_by_one_function_are_one_cause_with_every_place():
    c = _readers("report", "dump")
    rows, causes = _causes(c, _set(["N1"]))
    (cause,) = causes
    assert cause.kind == "reader" and cause.story == "S1" and cause.thread == "T1"
    assert cause.text == "2 places read `Uart::errors`, which `config` now writes"
    assert cause.places == sorted(k.key for k in rows)
    assert all(k.cause == cause.id for k in rows)
    assert cause.id == "c" + hashlib.sha1(b"reader|config|Uart::errors").hexdigest()[:10] == cause_id("reader", "config", "Uart::errors")


def test_one_place_keeps_its_own_text_and_another_field_is_another_cause():
    c = _world([_edit("config", "drv/cfg.c"), _same("report", "svc/rep.c"), _same("dump", "svc/dump.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("config", "Uart", "last", "write", "added"),
                       ("report", "Uart", "errors", "read", "unchanged"), ("dump", "Uart", "last", "read", "unchanged")])
    _, causes = _causes(c, _set(["N1"]))
    assert sorted(z.text for z in causes) == ["`dump` reads `Uart::last`, which `config` now writes",
                                              "`report` reads `Uart::errors`, which `config` now writes"]


def test_callers_of_one_changed_signature_and_results_by_new_values_group_apart():
    c, ss = _caller_world(returns=(["0"], ["0", "-2"]))
    next(e for e in c.after[0].calls if e.caller == "c:@F@flush").result_used = False
    _, causes = _causes(c, ss)
    assert [(z.kind, z.text) for z in causes] == [
        ("caller", "`flush` calls `send` and was not updated for its new signature"),
        ("result", "`flush` ignores the result of `send`, which can now return -2")]
    assert causes[0].id == cause_id("caller", "send", "") and causes[1].id == cause_id("result", "send", "-2")


def test_each_finding_is_its_own_cause_and_its_id_survives_renumbering():
    c = _world([_edit("send", "drv/uart.c")])
    ss = _set(["N1"])
    ss.finding_story = {"F1": "S1", "F2": "S1"}
    c.findings = [_f("F1", verdict="hazard", reason="drops data", source="tier1", title="lock"),
                  _f("F2", verdict="needs_review", reason="check it", source="tier1", title="order")]
    _, first = _causes(c, ss)
    assert [(z.kind, z.finding, z.text) for z in first] == [("hazard", "F1", "drops data"), ("confirm", "F2", "check it")]
    c.findings[0].id, c.findings[1].id = "F2", "F1"
    ss.finding_story = {"F1": "S1", "F2": "S1"}
    _, again = _causes(c, ss)
    assert [z.id for z in again] == [z.id for z in first]


def test_untested_functions_of_a_story_are_one_cause():
    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _edit("recv", "drv/recv.c"),
                ("test_it", "tests/t.c", ["x;"], ["init_hw();"])])
    ss = _set(["N1", "N3"], ["N2"], ["N4"], kinds={"S3": "tests"})
    threads = [Thread(id="T1", name="t", purpose="", stories=["S1", "S2"])]
    rows, _ = _checks(c, ss, threads=threads, has_tests=True,
                      test_callers=lambda name: {"/w/tests/u.c"} if name == "init" else set())
    (cause,) = build_causes(rows, _x(c), threads, ["S1", "S2"], {})
    assert cause.text == "2 functions no test calls" and cause.id == cause_id("untested", "recv,send", "")
    assert cause.story == "S1" and len(cause.places) == 2


def test_a_cause_touches_the_flows_of_its_story_whose_path_holds_its_function_or_a_place():
    c = _readers("report")
    fl = Flow(id="FL1", path=["N2", "N1"], tag="state", lands="N1", severity="low", text="report → config", what="",
              effect="", check="")
    other = fl.model_copy(update={"id": "FL2", "path": ["N9"]})
    _, causes = _causes(c, _set(["N1"]), flows_of={"S1": [other, fl]})
    assert causes[0].flows == ["FL1"]


def test_causes_follow_thread_then_story_then_flow_then_kind_order():
    c = _world([_edit("config", "drv/cfg.c"), _edit("send", "drv/uart.c"), _same("report", "svc/rep.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged")])
    ss = _set(["N1"], ["N2"])
    ss.finding_story = {"F1": "S2"}
    c.findings = [_f("F1", nodes=("N2",), verdict="hazard", reason="drops data", source="tier1")]
    threads = [Thread(id="T1", name="b", purpose="", stories=["S2"]), Thread(id="T2", name="a", purpose="", stories=["S1"])]
    _, causes = _causes(c, ss, threads=threads)
    assert [(z.thread, z.story, z.kind) for z in causes] == [("T1", "S2", "hazard"), ("T2", "S1", "reader")]


def test_the_reading_and_each_storys_reading_hold_their_causes():
    c = _readers("report", "dump")
    ss = _set(["N1"])
    reading, per = build_reading(ss, c)
    assert [z.text for z in reading.causes] == ["2 places read `Uart::errors`, which `config` now writes"]
    assert per["S1"].causes == reading.causes
    assert all(k.cause == reading.causes[0].id for k in reading.checks)
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_causes.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'codetortoise.causes'`.

- [ ] **Step 3: Add the models to `reading.py`**

After `class Check`, add:

```python
class ChangeLine(BaseModel):
    sign: Literal["+", "-", " "]
    text: str
    line: int | None = None          # in the after text ("+", " ") or the before text ("-")


class CauseChange(BaseModel):
    """The 2–6 changed lines that raised a cause (spec 2026-10-16 §4.8)."""
    path: str                        # workspace-relative
    depot: str | None = None         # the file the panel opens
    function: str | None = None      # its label
    lines: list[ChangeLine] = Field(default_factory=list)


class Cause(BaseModel):
    """One change and every place it asks the reviewer to look at (spec 2026-10-16 §4.1)."""
    id: str
    kind: CheckKind
    thread: str | None = None
    story: str | None = None
    text: str
    places: list[str] = Field(default_factory=list)     # check keys, by path then line
    flows: list[str] = Field(default_factory=list)      # flow ids of its story that it touches
    finding: str | None = None
    change: CauseChange | None = None
```

Add `causes: list[Cause] = Field(default_factory=list)` to `StoryReading` (after `checks`) and to `Reading` (after `cleared`, comment `# checks by cause, in reading order (spec 2026-10-16 §4)`). Set `READING_VERSION = 3`.

- [ ] **Step 4: Create `backend/codetortoise/causes.py`**

```python
"""Checks grouped by the change that raised them (spec 2026-10-16-outline-and-causes §4)."""
from __future__ import annotations

import hashlib
from collections import defaultdict

from codetortoise.board import Flow, _Ctx
from codetortoise.reading import CHECK_ORDER, Cause, Check, Thread, _qual

_ALONE = {"unanalysed", "ask"}       # a row of these kinds is its own cause


def cause_id(kind: str, qual: str, subject: str) -> str:
    """Stable across re-runs: kind, the function's qualified name and the subject only."""
    return "c" + hashlib.sha1(f"{kind}|{qual}|{subject}".encode()).hexdigest()[:10]


def _group(k: Check, x: _Ctx) -> tuple[str, str, str]:
    if k.kind == "untested":
        return k.kind, f"story:{k.story or ''}", ""
    if k.kind in _ALONE:
        return k.kind, "", k.key
    return k.kind, _qual(x, k.cause_fn) if k.cause_fn else "", k.cause_subject


def _text(kind: str, rows: list[Check], fn: str) -> str:
    n = len(rows)
    if n == 1 or kind in ("hazard", "confirm") or kind in _ALONE:
        return rows[0].text
    if kind == "reader":
        return f"{n} places read `{rows[0].field}`, which `{fn}` now writes"
    if kind == "caller":
        return f"{n} callers not updated for `{fn}`'s new signature"
    if kind == "result":
        return f"{n} callers handle `{fn}`'s result the old way"
    if kind == "target":
        return f"{n} calls to `{fn}` from other build targets" if fn else rows[0].text
    return f"{n} functions no test calls"          # untested


def build_causes(rows: list[Check], x: _Ctx, threads: list[Thread], order: list[str],
                 flows_of: dict[str, list[Flow]]) -> list[Cause]:
    """Every row's cause, in reading order (§4.5): thread, the story's reading order, the first flow it touches, kind
    order, text. Sets each row's `cause`."""
    groups: dict[tuple[str, str, str], list[Check]] = defaultdict(list)
    for k in rows:
        groups[_group(k, x)].append(k)
    causes: list[Cause] = []
    for (kind, qual, subject), members in groups.items():
        if kind == "untested":
            qual = ",".join(sorted({_qual(x, k.cause_fn) for k in members if k.cause_fn}))
        members.sort(key=lambda k: (k.path, k.line or 0, k.key))
        lead = members[0]
        fn = x.label(lead.cause_fn) if lead.cause_fn else ""
        story = lead.story
        touched = {lead.cause_fn} | {k.node for k in members}
        flows = [fl.id for fl in flows_of.get(story or "", []) if touched & set(fl.path)]
        cid = cause_id(kind, qual, subject)
        if causes and any(z.id == cid for z in causes):   # two groups with one id are one cause
            z = next(z for z in causes if z.id == cid)
            z.places += [k.key for k in members]
            for k in members:
                k.cause = cid
            continue
        for k in members:
            k.cause = cid
        causes.append(Cause(id=cid, kind=kind, thread=lead.thread, story=story, text=_text(kind, members, fn),
                            places=[k.key for k in members], flows=flows, finding=lead.finding))
    thread_at = {t.id: i for i, t in enumerate(threads)}
    story_at = {s: i for i, s in enumerate(order)}
    rank = {k: i for i, k in enumerate(CHECK_ORDER)}

    def first_flow(z: Cause) -> int:
        ids = [fl.id for fl in flows_of.get(z.story or "", [])]
        return min((ids.index(f) for f in z.flows), default=len(ids) + 1)
    causes.sort(key=lambda z: (thread_at.get(z.thread or "", len(threads)), story_at.get(z.story or "", len(order)),
                               first_flow(z), rank[z.kind], z.text))
    return causes
```

- [ ] **Step 5: Wire it into `build_reading`**

In `reading.py` `build_reading`, after `_set_depots(c, rows + cleared)`, move the `strong = …` and `order = …` lines above it if needed so `order` exists, then add:

```python
    from codetortoise.causes import build_causes     # causes.py imports this module
    flows_of = {s.id: [fl for fl in (details[s.id].board.flows if details and s.id in details else a.flows)
                       if fl.id in s.flows] for s in ss.stories}
    causes = build_causes(rows, x, threads, order, flows_of)
```

Pass `causes=causes` to `Reading(...)`, and `causes=[z for z in causes if z.story == s.id]` to each `StoryReading(...)`.

- [ ] **Step 6: Run the cause, reading and web tests**

Run: `cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_causes.py tests/test_reading.py tests/test_web.py tests/test_pipeline.py`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```bash
cd backend && ../../../backend/.venv/bin/ruff check codetortoise tests
git add backend/codetortoise/causes.py backend/codetortoise/reading.py backend/tests/test_causes.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): checks grouped by the change that raised them

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 3: The change's lines for each cause

**Files:**
- Modify: `backend/codetortoise/causes.py` (`change_for`, `_block`, `_cap`; `build_causes` sets `change`)
- Modify: `backend/codetortoise/reading.py` (`build_reading` sets the change's depot)
- Test: `backend/tests/test_causes.py`

**Interfaces:**
- Consumes: `Cause`, `CauseChange`, `ChangeLine` (Task 2); `board._opcodes(before, after)`; `_Ctx.texts` (local path → `FileChange` with `before`/`after`), `_Ctx.fa`/`fb` (key → `Function` with `file`, `start_line`, `end_line`, `signature`, `returns`, `return_lines`), `_Ctx.fields_after` (`FieldAccess` with `fn`, `field`, `mode`, `file`, `line`).
- Produces: `causes.change_for(kind: str, rows: list[Check], x: _Ctx) -> CauseChange | None` (at most 6 lines). `Cause.change` filled by `build_causes`; `Cause.change.depot` filled in `build_reading`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_causes.py`:

```python
from codetortoise.causes import change_for


def _lines(ch):
    return [(ln.sign, ln.text.strip(), ln.line) for ln in ch.lines]


def test_a_reader_cause_shows_the_new_write_with_a_line_around_it():
    c = _world([("config", "drv/cfg.c", ["a = 0;"], ["a = 0;", "r->errors = 1;"]), _same("report", "svc/rep.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged")])
    next(a for a in c.after[0].fields if a.fn == "c:@F@config").line = 4
    rows, (cause,) = _causes(c, _set(["N1"]))
    assert cause.change.path == "drv/cfg.c" and cause.change.function == "config"
    assert _lines(cause.change) == [(" ", "a = 0;", 3), ("+", "r->errors = 1;", 4), (" ", "}", 5)]


def test_a_caller_cause_shows_the_signature_before_and_after():
    c, ss = _caller_world()
    _, (cause,) = _causes(c, ss)
    assert _lines(cause.change) == [("-", "int send(int len)", 1), ("+", "int send(unsigned len)", 1)]


def test_a_result_cause_shows_the_new_return():
    c = _world([("send", "drv/uart.c", ["a = 0;"], ["a = 0;", "if (full) return -2;", "a = 1;"]), _same("a", "x/a.c")],
               calls=[("a", "send")])
    from test_reading import _sig
    _sig(c, "send", returns=(["0"], ["0", "-2"]))
    next(f for f in c.after[0].functions if f.name == "send").return_lines = {"-2": 4}
    next(e for e in c.after[0].calls if e.caller == "c:@F@a").result_used = False
    _, (cause,) = _causes(c, _set(["N1"]))
    assert ("+", "if (full) return -2;", 4) in _lines(cause.change) and len(cause.change.lines) <= 6


def test_without_its_own_line_a_cause_shows_the_functions_first_changed_block_and_never_more_than_six_lines():
    body_b = ["a = 0;"]
    body_a = ["a = 0;", *(f"x{i} = {i};" for i in range(9))]
    c = _world([("send", "drv/uart.c", body_b, body_a)])
    c.impact.capped = {"send": 90}
    rows, (cause,) = _causes(c, _set(["N1"]))
    assert cause.kind == "unanalysed" and len(cause.change.lines) == 6
    assert all(ln.sign == "+" for ln in cause.change.lines)


def test_a_cause_without_a_changed_function_has_no_change():
    from codetortoise.reading import Check
    c = _world([_edit("a", "x/a.c")])
    ask = Check(key="ask|||a", kind="ask", text="Ask the author")
    assert change_for("ask", [ask], _x(c)) is None


def test_the_change_names_its_depot_file():
    c = _readers("report")
    reading, _ = build_reading(_set(["N1"]), c)
    assert reading.causes[0].change.depot == "//d/w/drv/cfg.c"
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_causes.py`
Expected: FAIL (`ImportError: cannot import name 'change_for'`).

- [ ] **Step 3: Implement `change_for`**

In `causes.py` add imports `from codetortoise.board import Flow, _Ctx, _opcodes` and `from codetortoise.reading import CHECK_ORDER, Cause, CauseChange, ChangeLine, Check, Thread, _qual, rel_path`, then:

```python
MAX_LINES = 6


def _cap(lines: list[ChangeLine], focus: set[int]) -> list[ChangeLine]:
    """At most six: context goes first, then removed lines, then added lines farthest from the focus."""
    if len(lines) <= MAX_LINES:
        return lines
    lines = [ln for ln in lines if ln.sign != " "]
    while len(lines) > MAX_LINES:
        minus = [i for i, ln in enumerate(lines) if ln.sign == "-"]
        if minus:
            lines.pop(minus[0])
            continue
        if focus:
            far = max(range(len(lines)), key=lambda i: min(abs((lines[i].line or 0) - f) for f in focus))
        else:
            far = len(lines) - 1
        lines.pop(far)
    return lines


def _block(x: _Ctx, local: str, lo: int | None, hi: int | None, focus: set[int]) -> list[ChangeLine]:
    """The changed block of `local` within after-lines [lo, hi] holding a focus line (any block when `focus` is empty),
    with a line of context each side."""
    fc = x.texts.get(local)
    if fc is None:
        return []
    b, a = fc.before.splitlines(), fc.after.splitlines()
    blocks = [op for op in _opcodes(fc.before, fc.after) if op[0] != "equal"
              and (lo is None or (op[3] + 1 <= hi and max(op[4], op[3] + 1) >= lo))]
    pick = next((op for op in blocks if any(op[3] < f <= max(op[4], op[3] + 1) for f in focus)), None) if focus \
        else (blocks[0] if blocks else None)
    if pick is None:
        return []
    _, i1, i2, j1, j2 = pick
    out = [ChangeLine(sign=" ", text=a[j1 - 1], line=j1)] if j1 > 0 else []
    out += [ChangeLine(sign="-", text=b[i], line=i + 1) for i in range(i1, i2)]
    out += [ChangeLine(sign="+", text=a[j], line=j + 1) for j in range(j1, j2)]
    if j2 < len(a):
        out.append(ChangeLine(sign=" ", text=a[j2], line=j2 + 1))
    return _cap(out, focus)


def change_for(kind: str, rows: list[Check], x: _Ctx) -> CauseChange | None:
    """The 2–6 changed lines that raised a cause of `kind` made of `rows` (spec 2026-10-16 §4.8)."""
    lead = rows[0]
    if kind == "target" and lead.cause_fn is None:          # a changed header included by another target's files
        local = next((p for p in x.texts if rel_path(x, p) == lead.cause_subject), None)
        lines = _block(x, local, None, None, set()) if local else []
        return CauseChange(path=lead.cause_subject, lines=lines) if lines else None
    n = lead.cause_fn
    if n is None or n not in x.im.nodes:
        return None
    key = x.im.nodes[n].key
    fb, fa = x.fb.get(key), x.fa.get(key)
    if fa is None:
        return None
    label = x.label(n)

    def made(lines: list[ChangeLine]) -> CauseChange | None:
        return CauseChange(path=rel_path(x, fa.file), function=label, lines=lines) if lines else None
    if kind == "caller" and fb is not None and fb.signature != fa.signature:
        return made([ChangeLine(sign="-", text=fb.signature, line=fb.start_line),
                     ChangeLine(sign="+", text=fa.signature, line=fa.start_line)])
    focus: set[int] = set()
    local = fa.file
    if kind == "reader":
        focus = {a.line for a in x.fields_after if a.fn == key and a.mode in ("write", "may_write")
                 and x.im.nodes.get(x.id_of.get(f"field:{a.field}", ""), None) is not None
                 and x.label(x.id_of[f"field:{a.field}"]) == lead.field}
    elif kind == "result" and fb is not None:
        focus = {fa.return_lines[v] for v in fa.returns if v not in fb.returns and v in fa.return_lines}
    elif kind in ("hazard", "confirm"):
        f = next((f for f in x.c.findings if f.id == lead.finding), None)
        ev = [e for e in (f.evidence if f else []) if e.file and e.line]
        if ev:
            local = ev[0].file
            focus = {e.line for e in ev if e.file == local}
    lo, hi = (fa.start_line, fa.end_line) if local == fa.file else (None, None)
    lines = _block(x, local, lo, hi, focus) if focus else []
    if not lines:                                            # the kind's own rule found nothing: the first block
        local = fa.file
        lines = _block(x, local, fa.start_line, fa.end_line, set())
    return CauseChange(path=rel_path(x, local), function=label, lines=lines) if lines else None
```

In `build_causes`, pass `change=change_for(kind, members, x)` to `Cause(...)`.

- [ ] **Step 4: Set the change's depot in `build_reading`**

After `causes = build_causes(...)`:

```python
    root = c.root.rstrip("/")
    paths = {z.change.path: z.change.path if z.change.path.startswith("/") or not root else f"{root}/{z.change.path}"
             for z in causes if z.change}
    found = c.depots_for(sorted(set(paths.values()))) if paths else {}
    for z in causes:
        if z.change:
            z.change.depot = found.get(paths[z.change.path])
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_causes.py tests/test_reading.py`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
cd backend && ../../../backend/.venv/bin/ruff check codetortoise tests
git add backend/codetortoise/causes.py backend/codetortoise/reading.py backend/tests/test_causes.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): each cause carries the changed lines that raised it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 4: Mark many places in one request

**Files:**
- Modify: `backend/codetortoise/web/app.py` (route before `/api/reviews/{rid}/checks/{key:path}/mark`)
- Modify: `frontend/src/api.ts`
- Test: `backend/tests/test_web.py`

**Interfaces:**
- Produces: `POST /api/reviews/{rid}/checks/marks` body `{"keys": [str]}` → `{"marked": [Mark…]}`; any signed-in user; an unknown key → 404 and nothing marked. Frontend `api.markChecks(id: number, keys: string[]): Promise<{ marked: Mark[] }>`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_web.py`:

```python
def test_all_look_fine_marks_every_place_of_a_cause_in_one_request_or_none(env):
    svc, app, _ = env
    owner, rid = _review(app)
    bob = login(app, "bob")
    r = owner.get(f"/api/reviews/{rid}/reading").json()
    keys = [k["key"] for k in r["checks"]][:2]
    assert TestClient(app).post(f"/api/reviews/{rid}/checks/marks", json={"keys": keys}).status_code == 401
    assert bob.post(f"/api/reviews/{rid}/checks/marks", json={"keys": [*keys, "nope"]}).status_code == 404
    assert owner.get(f"/api/reviews/{rid}/reading").json()["marks"] == {}
    out = bob.post(f"/api/reviews/{rid}/checks/marks", json={"keys": keys}).json()
    assert [m["user"] for m in out["marked"]] == ["bob", "bob"]
    assert set(owner.get(f"/api/reviews/{rid}/reading").json()["marks"]) == set(keys)
    assert set(bob.get(f"/api/reviews/{rid}/ticks").json()["checks"]) >= set(keys)
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web.py -k all_look_fine`
Expected: FAIL (404 or 405 on the first good request, since the path matches the single-mark route's `{key:path}` or no route).

- [ ] **Step 3: Implement**

In `app.py`, add a model next to the other request models (`class KeysIn(BaseModel): keys: list[str]`) and register this route **before** the `@app.post("/api/reviews/{rid}/checks/{key:path}/mark")` route:

```python
    @app.post("/api/reviews/{rid}/checks/marks")
    def mark_checks(rid: int, body: KeysIn, user: str = Depends(user_of)):
        """All look fine (spec 2026-10-16 §4.3): every key or none."""
        review_or_404(rid)
        found = [check_or_404(rid, key) for key in body.keys]
        out = []
        for k in found:
            store.set_tick(rid, user, "check", k.key)
            out.append(store.set_mark(rid, k.key, user, k.source_line))
        return {"marked": out}
```

In `frontend/src/api.ts`, after `unmarkCheck`:

```ts
  /** All look fine: every place of a cause at once (spec 2026-10-16 §4.3). */
  markChecks: (id: number, keys: string[]) => call<{ marked: Mark[] }>("POST", `/api/reviews/${id}/checks/marks`, { keys }),
```

(Check `call`'s signature in `api.ts`: if it takes the body as a third argument under another name, follow it.)

- [ ] **Step 4: Run the web tests and the frontend type check**

Run: `cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web.py` then `cd ../frontend && npx tsc -b --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/web/app.py backend/tests/test_web.py frontend/src/api.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(api): mark every place of a cause in one request

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 5: Frontend types and the causes library

**Files:**
- Modify: `frontend/src/reading/types.ts`
- Modify: `frontend/src/board/prefs.ts` (keys `outline`, `hiddenKinds`)
- Modify: `frontend/src/workspace/names.ts` (`plainNames`)
- Modify: `frontend/src/workspace/CheckList.tsx` (drop `also`)
- Create: `frontend/src/reading/causes.ts`
- Test: `frontend/src/reading/causes.test.ts` (new), `frontend/src/workspace/names.test.ts`

**Interfaces:**
- Consumes: the reading's `causes` (Tasks 2–3), `Check.cause`.
- Produces (all in `reading/causes.ts`):
  - `type OutlineView = "stories" | "checks"`; `loadOutline(): OutlineView`; `saveOutline(v: OutlineView): void`
  - `HIDDEN_DEFAULT: CheckKind[]` (`["confirm"]`); `loadHidden(): Set<CheckKind>`; `saveHidden(h: ReadonlySet<CheckKind>): void`
  - `placeOpen(key: string, marks: Record<string, Mark>): boolean`
  - `openPlaces(c: Cause, marks): string[]`; `causeOpen(c, marks): boolean`; `doneCount(c, marks): number`
  - `shown(causes: Cause[], hidden: ReadonlySet<CheckKind>): Cause[]`
  - `openCount(causes, hidden, marks): number` (open shown causes)
  - `firstOpenAt(c, marks): number` (1-based; 1 when none is open)
  - `nextOpenAt(c, marks, at: number, by: 1 | -1): number | null` (the next open place other than `at`, wrapping; null when none)
  - `nextOpen(causes, hidden, marks, from: { cause?: string | null; story?: string | null; order: string[] }): { cause: string; at: number } | null`
  - `causeOfCheck(causes, key: string): { cause: Cause; at: number } | null` (by check key, else by finding id)
  - `alsoAt(causes, checks: Map<string, Check>, cause: Cause, key: string): { cause: Cause; at: number }[]`
  - `hiddenLabel(hidden: ReadonlySet<CheckKind>, causes: Cause[]): string`
  - `progressLine(read: number, stories: number, open: number, total: number): string`
- `names.ts`: `plainNames(text: string, names: Names): string` — node ids become their labels, backticks kept (for link text, `title` and tab labels).
- `prefs.ts` `keys.outline = "ct.ws.outline"`, `keys.hiddenKinds = "ct.ws.hiddenKinds"`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/reading/causes.test.ts`:

```ts
import { afterEach, describe, expect, it } from "vitest";
import { alsoAt, causeOfCheck, causeOpen, doneCount, firstOpenAt, hiddenLabel, loadHidden, loadOutline, nextOpen,
  nextOpenAt, openCount, openPlaces, progressLine, saveHidden, saveOutline, shown } from "./causes";
import type { Cause, Check, CheckKind, Mark } from "./types";

const cause = (id: string, kind: CheckKind, story: string | null, places: string[], extra: Partial<Cause> = {}): Cause =>
  ({ id, kind, thread: "T1", story, text: `${id} text`, places, flows: [], finding: null, change: null, ...extra });
const mark = (key: string, changed = false): Mark => ({ key, user: "ana", at: "2026-10-16T10:00:00Z", source_line: "", changed });
const marks = (...keys: string[]) => Object.fromEntries(keys.map((k) => [k, mark(k)]));
const check = (key: string, path: string, line: number): Check =>
  ({ key, kind: "reader", story: "S1", thread: "T1", path, depot: null, line, function: null, node: null, text: key,
     source_line: "", finding: null, cites: [], cause: null });

afterEach(() => window.localStorage.clear());

describe("open places", () => {
  const c = cause("c1", "reader", "S1", ["a", "b", "c"]);
  it("a place is open until marked, and open again when its line changed", () => {
    expect(openPlaces(c, { a: mark("a"), b: mark("b", true) })).toEqual(["b", "c"]);
    expect(doneCount(c, { a: mark("a"), b: mark("b", true) })).toBe(1);
    expect(causeOpen(c, marks("a", "b", "c"))).toBe(false);
    expect(causeOpen(c, { ...marks("a", "c"), b: mark("b", true) })).toBe(true);
  });
  it("the first open place, 1-based; 1 when all are done", () => {
    expect(firstOpenAt(c, marks("a"))).toBe(2);
    expect(firstOpenAt(c, marks("a", "b", "c"))).toBe(1);
  });
  it("Skip and Back step over done places, wrapping, and find none when this is the only open one", () => {
    expect(nextOpenAt(c, marks("b"), 1, 1)).toBe(3);
    expect(nextOpenAt(c, marks("b"), 3, 1)).toBe(1);
    expect(nextOpenAt(c, marks("b"), 1, -1)).toBe(3);
    expect(nextOpenAt(c, marks("a", "b"), 3, 1)).toBeNull();
  });
});

describe("hidden kinds", () => {
  const all = [cause("c1", "confirm", "S1", ["a"]), cause("c2", "reader", "S1", ["b"]), cause("c3", "caller", "S2", ["c"])];
  it("hide Confirm by default and remember another choice", () => {
    expect([...loadHidden()]).toEqual(["confirm"]);
    saveHidden(new Set<CheckKind>(["reader", "caller"]));
    expect([...loadHidden()].sort()).toEqual(["caller", "reader"]);
    window.localStorage.setItem("ct.ws.hiddenKinds", JSON.stringify(["nonsense", 3]));
    expect([...loadHidden()]).toEqual([]);
    window.localStorage.setItem("ct.ws.hiddenKinds", "{not json");
    expect([...loadHidden()]).toEqual(["confirm"]);
  });
  it("leave hidden causes out of what is shown and counted", () => {
    expect(shown(all, new Set(["confirm"])).map((c) => c.id)).toEqual(["c2", "c3"]);
    expect(openCount(all, new Set(["confirm"]), marks("c"))).toBe(1);
  });
  it("name what they hide", () => {
    expect(hiddenLabel(new Set(), all)).toBe("Showing all");
    expect(hiddenLabel(new Set(["confirm"]), all)).toBe("Showing: all but Confirm · 1 hidden");
    expect(hiddenLabel(new Set(["confirm", "caller"]), all)).toBe("Showing: all but Confirm, Caller not updated · 2 hidden");
  });
});

describe("the outline's view", () => {
  it("is Stories unless the reader chose Checks", () => {
    expect(loadOutline()).toBe("stories");
    saveOutline("checks");
    expect(loadOutline()).toBe("checks");
    window.localStorage.setItem("ct.ws.outline", JSON.stringify("sideways"));
    expect(loadOutline()).toBe("stories");
  });
});

describe("Next open check", () => {
  const order = ["S2", "S1", "S3"];
  const all = [cause("c1", "caller", "S2", ["a"]), cause("c2", "confirm", "S2", ["b"]), cause("c3", "result", "S1", ["c", "d"]),
               cause("c4", "ask", null, ["e"])];
  const hidden = new Set<CheckKind>(["confirm"]);
  it("goes to the first open shown cause after the one in the panel, at its first open place, wrapping", () => {
    expect(nextOpen(all, hidden, marks("c"), { cause: "c1", order })).toEqual({ cause: "c3", at: 2 });
    expect(nextOpen(all, hidden, {}, { cause: "c4", order })).toEqual({ cause: "c1", at: 1 });
    expect(nextOpen(all, hidden, marks("a"), { cause: "c3", order })).toEqual({ cause: "c4", at: 1 });
  });
  it("without a cause in the panel starts at the current story, else at the start", () => {
    expect(nextOpen(all, hidden, {}, { story: "S1", order })).toEqual({ cause: "c3", at: 1 });
    expect(nextOpen(all, hidden, marks("c", "d"), { story: "S1", order })).toEqual({ cause: "c4", at: 1 });
    expect(nextOpen(all, hidden, {}, { order })).toEqual({ cause: "c1", at: 1 });
  });
  it("finds a done cause again once a marked line changed", () => {
    expect(nextOpen(all, hidden, { a: mark("a", true), ...marks("c", "d", "e") }, { order })).toEqual({ cause: "c1", at: 1 });
  });
  it("finds nothing when every shown cause is done or hidden", () => {
    expect(nextOpen(all, hidden, marks("a", "c", "d", "e"), { order })).toBeNull();
    expect(nextOpen(all, new Set(["caller", "confirm", "result", "ask"]), {}, { order })).toBeNull();
  });
});

describe("a check's cause", () => {
  const all = [cause("c1", "reader", "S1", ["a", "b"]), cause("c2", "confirm", "S1", ["x"], { finding: "F4" }),
               cause("c3", "result", "S1", ["z"])];
  it("is found by the check's key or by its finding", () => {
    expect(causeOfCheck(all, "b")).toEqual({ cause: all[0], at: 2 });
    expect(causeOfCheck(all, "F4")).toEqual({ cause: all[1], at: 1 });
    expect(causeOfCheck(all, "nope")).toBeNull();
  });
  it("other causes at the same place are listed with where that place is in them", () => {
    const checks = new Map([["a", check("a", "x.c", 3)], ["b", check("b", "y.c", 9)], ["x", check("x", "y.c", 9)],
                            ["z", check("z", "x.c", 4)]]);
    expect(alsoAt(all, checks, all[0], "b")).toEqual([{ cause: all[1], at: 1 }]);
    expect(alsoAt(all, checks, all[0], "a")).toEqual([]);
  });
});

describe("the header's progress", () => {
  it("counts stories read and the open causes", () => {
    expect(progressLine(3, 9, 12, 20)).toBe("3 of 9 stories read · 12 causes open");
    expect(progressLine(3, 9, 1, 20)).toBe("3 of 9 stories read · 1 cause open");
    expect(progressLine(9, 9, 0, 20)).toBe("9 of 9 stories read · every check done");
    expect(progressLine(0, 2, 0, 0)).toBe("0 of 2 stories read");
  });
});
```

Append to `frontend/src/workspace/names.test.ts`:

```ts
describe("plainNames", () => {
  it("names node ids and keeps backticks for the caller to render", () => {
    const names = { N9: { label: "uart_send", kind: "function", path: null, line: null, story: null } };
    expect(plainNames("`N9` drops F2 data N7", names)).toBe("`uart_send` drops F2 data a function");
  });
});
```

(add `plainNames` to that file's import from `./names`, and `describe`/`it`/`expect` if not imported).

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/reading/causes.test.ts src/workspace/names.test.ts`
Expected: FAIL (`Failed to resolve import "./causes"`; `plainNames is not a function`).

- [ ] **Step 3: Types**

In `frontend/src/reading/types.ts`: delete `export interface Reason …`; in `Check` replace the `also` lines with

```ts
  /** Its cause's id (spec 2026-10-16-outline-and-causes §4.1); null on a found-no-hazard row, absent before causes. */
  cause?: string | null;
```

and add after `Check`:

```ts
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
```

Add `causes?: Cause[];` (comment: `/** Checks by cause, in reading order; absent on a reading stored before causes. */`) to `Reading` and to `StoryReading`.

In `frontend/src/workspace/CheckList.tsx` `CheckRow`, replace the `[{ kind: k.kind, text: k.text }, ...k.also].map(…)` block with the one row:

```tsx
      <div className="ck-top"><span className={`ck-tag ${k.kind}`}>{KIND_LABEL[k.kind]}</span>
        <span className="ck-text"><NameText text={k.text} /></span></div>
```

(import `NameText` from `./NameText` beside `Ticks`; this file goes in Task 12, the change only keeps it compiling and fixes item 1 meanwhile).

- [ ] **Step 4: `plainNames` and the storage keys**

Append to `frontend/src/workspace/names.ts`:

```ts
/** Text with node ids as their names and backticks kept: for a link's text (no links inside links), a `title` or a
 * panel tab's label (spec 2026-10-16 §4.7). */
export function plainNames(text: string, names: Names): string {
  return nameParts(text, names, []).map((p) => ("text" in p ? p.text : "code" in p ? `\`${p.code}\`` : "node" in p ? p.label
    : p.finding)).join("");
}
```

In `frontend/src/board/prefs.ts` `keys`, after `checkFolded`:

```ts
  /** The outline's view and the check kinds the reader hides (spec 2026-10-16-outline-and-causes §1.2, §4.6). */
  outline: "ct.ws.outline",
  hiddenKinds: "ct.ws.hiddenKinds",
```

- [ ] **Step 5: Create `frontend/src/reading/causes.ts`**

```ts
/** Checks by cause (spec 2026-10-16-outline-and-causes §4): which places are open, which kinds are hidden, the order
 * of Next open check and the stepper's moves. Pure, so the rules are tested apart from React. */
import { keys, load, save } from "../board/prefs";
import { CHECK_ORDER, KIND_LABEL } from "./checks";
import type { Cause, Check, CheckKind, Mark } from "./types";

export type OutlineView = "stories" | "checks";

export const loadOutline = (): OutlineView => (load<unknown>(keys.outline, "stories") === "checks" ? "checks" : "stories");
export const saveOutline = (v: OutlineView) => save(keys.outline, v);

export const HIDDEN_DEFAULT: CheckKind[] = ["confirm"];

/** The kinds the reader hides; a stored value of the wrong shape keeps only real kinds, unreadable storage the default. */
export function loadHidden(): Set<CheckKind> {
  const v = load<unknown>(keys.hiddenKinds, HIDDEN_DEFAULT);
  return new Set(Array.isArray(v) ? v.filter((k): k is CheckKind => (CHECK_ORDER as unknown[]).includes(k)) : HIDDEN_DEFAULT);
}
export const saveHidden = (h: ReadonlySet<CheckKind>) => save(keys.hiddenKinds, CHECK_ORDER.filter((k) => h.has(k)));

/** Open unless someone marked it and its line has not changed since. */
export const placeOpen = (key: string, marks: Record<string, Mark>) => !marks[key] || marks[key].changed;
export const openPlaces = (c: Cause, marks: Record<string, Mark>) => c.places.filter((k) => placeOpen(k, marks));
export const causeOpen = (c: Cause, marks: Record<string, Mark>) => c.places.some((k) => placeOpen(k, marks));
export const doneCount = (c: Cause, marks: Record<string, Mark>) => c.places.length - openPlaces(c, marks).length;

export const shown = (causes: Cause[], hidden: ReadonlySet<CheckKind>) => causes.filter((c) => !hidden.has(c.kind));
export const openCount = (causes: Cause[], hidden: ReadonlySet<CheckKind>, marks: Record<string, Mark>) =>
  shown(causes, hidden).filter((c) => causeOpen(c, marks)).length;

/** Where the stepper opens a cause: its first open place (1-based), else its first. */
export function firstOpenAt(c: Cause, marks: Record<string, Mark>): number {
  const i = c.places.findIndex((k) => placeOpen(k, marks));
  return i < 0 ? 1 : i + 1;
}

/** Skip ›, ‹ Back and Looks fine & next: the next open place other than `at` going `by`, wrapping; null when none. */
export function nextOpenAt(c: Cause, marks: Record<string, Mark>, at: number, by: 1 | -1): number | null {
  const n = c.places.length;
  for (let i = 1; i < n; i++) {
    const j = (((at - 1 + by * i) % n) + n) % n;
    if (placeOpen(c.places[j], marks)) return j + 1;
  }
  return null;
}

/** Next open check › (§4.5): the first open, shown cause after the one in the panel, else from the current story's
 * place in reading order (its own causes first), else from the start; wrapping. */
export function nextOpen(causes: Cause[], hidden: ReadonlySet<CheckKind>, marks: Record<string, Mark>,
                         from: { cause?: string | null; story?: string | null; order: string[] }): { cause: string; at: number } | null {
  const n = causes.length;
  let start = 0;
  const here = from.cause ? causes.findIndex((c) => c.id === from.cause) : -1;
  if (here >= 0) start = here + 1;
  else if (from.story && from.order.includes(from.story)) {
    const pos = (s: string | null) => (s && from.order.includes(s) ? from.order.indexOf(s) : from.order.length);
    const i = causes.findIndex((c) => pos(c.story) >= pos(from.story!));
    start = i < 0 ? 0 : i;
  }
  for (let i = 0; i < n; i++) {
    const c = causes[(start + i) % n];
    if (!hidden.has(c.kind) && causeOpen(c, marks)) return { cause: c.id, at: firstOpenAt(c, marks) };
  }
  return null;
}

/** The cause holding check `key` (an old `?check=` address holds a check key or a finding id) and the place's number. */
export function causeOfCheck(causes: Cause[], key: string): { cause: Cause; at: number } | null {
  for (const c of causes) {
    const i = c.places.indexOf(key);
    if (i >= 0) return { cause: c, at: i + 1 };
  }
  const c = causes.find((x) => x.finding === key);
  return c ? { cause: c, at: 1 } : null;
}

/** The stepper's `also:` (§4.3): other causes with a check at the same file and line as place `key` of `cause`. */
export function alsoAt(causes: Cause[], checks: Map<string, Check>, cause: Cause, key: string): { cause: Cause; at: number }[] {
  const me = checks.get(key);
  if (!me || !me.path || me.line === null) return [];
  return causes.filter((c) => c.id !== cause.id).flatMap((c) => {
    const i = c.places.findIndex((k) => { const o = checks.get(k); return !!o && o.path === me.path && o.line === me.line; });
    return i < 0 ? [] : [{ cause: c, at: i + 1 }];
  });
}

/** The hidden-kinds control's summary (§4.6). */
export function hiddenLabel(hidden: ReadonlySet<CheckKind>, causes: Cause[]): string {
  const kinds = CHECK_ORDER.filter((k) => hidden.has(k));
  if (!kinds.length) return "Showing all";
  const n = causes.filter((c) => hidden.has(c.kind)).length;
  return `Showing: all but ${kinds.map((k) => KIND_LABEL[k]).join(", ")} · ${n} hidden`;
}

/** The top bar's one progress line (§1.1); `total`: the shown causes. */
export function progressLine(read: number, stories: number, open: number, total: number): string {
  const head = `${read} of ${stories} stories read`;
  if (!total) return head;
  return `${head} · ${open ? `${open} cause${open === 1 ? "" : "s"} open` : "every check done"}`;
}
```

- [ ] **Step 6: Run the unit tests and the type check**

Run: `cd frontend && npx vitest run && npx tsc -b --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/reading/types.ts frontend/src/reading/causes.ts frontend/src/reading/causes.test.ts frontend/src/board/prefs.ts frontend/src/workspace/names.ts frontend/src/workspace/names.test.ts frontend/src/workspace/CheckList.tsx
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): causes in the browser: open places, hidden kinds, next open check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 6: Addresses, memory and panel tabs for a cause and a story's tab

**Files:**
- Modify: `frontend/src/workspace/address.ts`, `frontend/src/workspace/memory.ts`, `frontend/src/workspace/tabs.ts`, `frontend/src/workspace/Detail.tsx` (the `tabLabel` call)
- Test: `frontend/src/workspace/address.test.ts`, `frontend/src/workspace/memory.test.ts`, `frontend/src/workspace/tabs.test.ts`

**Interfaces:**
- Produces:
  - `Open` gains `{ cause: string; at: number }` (`at` 1-based). Address text `?open=cause:<id>&at=<n>` (`at` always written for a cause).
  - `STORY_SECS = ["flows", "changes", "contracts", "where", "paths", "code", "talk"] as const`; `type StorySec`; `Address.sec?: StorySec` (story pages only; absent = the story's first tab). `?sec=graph` reads as the story's Graph view (`view: "graph"`); `href` never writes `sec` with the Graph view.
  - `openKey({cause})` = `c:<id>`; `addTab` keeps a cause's tab in place and takes its new `at`.
  - `tabLabel(o: Item, names: Names, causes?: Cause[]): string` — a cause's tab reads its line, plain and shortened (`short(plainNames(text))`), else "Check".
  - Memory keeps `sec` and a cause item.

- [ ] **Step 1: Write the failing tests**

Append inside `describe("readAddress", …)` in `address.test.ts`:

```ts
  it("reads a cause and its place, a story's tab, and an old Graph tab", () => {
    expect(readAddress("/s/S1", q("open=cause:c0123456789&at=3")).open).toEqual({ cause: "c0123456789", at: 3 });
    expect(readAddress("", q("open=cause:c01&at=0")).open).toEqual({ cause: "c01", at: 1 });
    expect(readAddress("", q("open=cause:")).open).toBeNull();
    expect(readAddress("/s/S1", q("sec=where")).sec).toBe("where");
    expect(readAddress("/s/S1", q("sec=nowhere")).sec).toBeUndefined();
    expect(readAddress("", q("sec=where")).sec).toBeUndefined();          // only a story has tabs
    expect(readAddress("/s/S1", q("sec=graph")).place).toEqual({ kind: "story", sid: "S1", view: "graph" });
  });
```

and inside the `href` tests (or a new `describe("href", …)` if none fits):

```ts
  it("writes a cause and a story's tab, and round-trips them", () => {
    const a = at({ kind: "story", sid: "S1", view: "steps" }, { open: { cause: "c01", at: 3 }, sec: "paths" });
    expect(href("/r/7", a)).toBe("/r/7/s/S1?open=cause%3Ac01&at=3&sec=paths");
    const back = readAddress("/s/S1", new URLSearchParams(href("/r/7", a).split("?")[1]));
    expect([back.open, back.sec]).toEqual([{ cause: "c01", at: 3 }, "paths"]);
    expect(href("/r/7", at({ kind: "story", sid: "S1", view: "graph" }, { sec: "paths" }))).toBe("/r/7/s/S1?view=graph");
  });
```

Append to `memory.test.ts` (inside its top-level `describe`, following its storage-stub pattern):

```ts
  it("keeps a story's tab and a cause in the panel", () => {
    const a = at({ kind: "story", sid: "S1", view: "steps" }, { open: { cause: "c01", at: 2 }, sec: "code" });
    saveMemory(9, remember({}, a));
    expect(recall(loadMemory(9), a.place)).toEqual(a);
    window.sessionStorage.setItem("ct.ws.9.memory", JSON.stringify({ "s:S1": { ...a, open: { cause: "c01", at: 0 } } }));
    expect(loadMemory(9)).toEqual({});
  });
```

(import `at` from `./address` and `loadMemory`, `recall`, `remember`, `saveMemory` from `./memory` if the file does not already.)

Append to `tabs.test.ts`:

```ts
describe("a cause's tab", () => {
  const c = { id: "c01", kind: "reader" as const, thread: null, story: null, text: "5 places read `UartDev::errors`, which `N9` now writes",
              places: ["a"], flows: [], finding: null, change: null };
  it("is one tab whatever place it is at, named by its line without node ids", () => {
    const t = addTab(addTab([], { cause: "c01", at: 1 }), { cause: "c01", at: 4 });
    expect(t).toEqual([{ cause: "c01", at: 4 }]);
    expect(openKey(t[0])).toBe("c:c01");
    const names = { N9: { label: "uart_a1", kind: "function", path: null, line: null, story: null } };
    expect(tabLabel(t[0], names, [c])).toBe("5 places read UartDev::errors, which…");
    expect(tabLabel({ cause: "gone", at: 1 }, names, [c])).toBe("Check");
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/workspace/address.test.ts src/workspace/memory.test.ts src/workspace/tabs.test.ts`
Expected: FAIL (the cause reads as `{ node: "cause:…" }`, `sec` undefined, tab label wrong).

- [ ] **Step 3: Implement `address.ts`**

- `Open`: `export type Open = { node: string } | { file: string; line: number | null; all?: true; cl?: number } | { finding: string } | { cause: string; at: number } | null;`
- After `INDEX_TABS`:

```ts
/** A story page's tabs (spec 2026-10-16-outline-and-causes §2.2); the Graph tab is the story's `view: "graph"`. */
export const STORY_SECS = ["flows", "changes", "contracts", "where", "paths", "code", "talk"] as const;
export type StorySec = typeof STORY_SECS[number];
```

- `Address` gains `/** A story's tab (absent: its first). */ sec?: StorySec;`
- `readPlace`: for `kind === "s"`, the view is graph when `q.get("view") === "graph" || q.get("sec") === "graph"`.
- `readOpen(raw, at)`: first line `if (raw?.startsWith("cause:")) { const n = Number(at); return raw.length > 6 ? { cause: raw.slice(6), at: Number.isInteger(n) && n > 0 ? n : 1 } : null; }`; the call becomes `readOpen(q.get("open"), q.get("at"))`.
- `readAddress` adds `...(place.kind === "story" && (STORY_SECS as readonly string[]).includes(q.get("sec") ?? "") ? { sec: q.get("sec") as StorySec } : {}),`
- `href`: the `open` value gains the cause case and `at`:

```ts
  if (a.open) q.set("open", "node" in a.open ? a.open.node : "finding" in a.open ? `finding:${a.open.finding}`
    : "cause" in a.open ? `cause:${a.open.cause}` : `file:${a.open.file}${a.open.line ? `:${a.open.line}` : ""}`);
  if (a.open && "cause" in a.open) q.set("at", String(a.open.at));
```

  and after the `tab` line: `if (a.sec && a.place.kind === "story" && a.place.view !== "graph") q.set("sec", a.sec);`

- [ ] **Step 4: Implement `memory.ts` and `tabs.ts`**

`memory.ts` `isOpen`: add before the `file` case `if ("cause" in o) return str(o.cause) && Number.isInteger(o.at) && (o.at as number) > 0;`; `isAddressAt` adds `&& (a.sec === undefined || (STORY_SECS as readonly unknown[]).includes(a.sec))` (import `STORY_SECS`).

`tabs.ts`:

```ts
export const openKey = (o: Item): string => ("finding" in o ? `f:${o.finding}` : "node" in o ? `n:${o.node}`
  : "cause" in o ? `c:${o.cause}` : `d:${o.file}`);
```

and `tabLabel`:

```ts
/** A tab's name: the finding's id, the file's name, the function's name or the check's line, shortened. */
export function tabLabel(o: Item, names: Names, causes: Cause[] = []): string {
  if ("finding" in o) return o.finding;
  if ("cause" in o) { const c = causes.find((x) => x.id === o.cause); return c ? short(plainNames(c.text, names), 40) : "Check"; }
  if ("file" in o) return o.file.slice(o.file.lastIndexOf("/") + 1);
  return names[o.node]?.label ?? "function";
}
```

(imports: `type Cause` from `../reading/types`, `short` from `./crumbs`, `plainNames` from `./names`.)

In `Detail.tsx` the tab strip calls `tabLabel(t, d.names, d.reading?.causes)`.

- [ ] **Step 5: Run the unit tests and the type check**

Run: `cd frontend && npx vitest run && npx tsc -b --noEmit`
Expected: PASS. (`Detail` does not yet render a cause: Task 8.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/workspace/address.ts frontend/src/workspace/address.test.ts frontend/src/workspace/memory.ts frontend/src/workspace/memory.test.ts frontend/src/workspace/tabs.ts frontend/src/workspace/tabs.test.ts frontend/src/workspace/Detail.tsx
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): addresses for a check's cause and a story's tab

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 7: The outline — Stories and Checks, hidden kinds, Focus folds it alone

**Files:**
- Create: `frontend/src/workspace/Outline.tsx`
- Modify: `frontend/src/reading/causes.ts` (+ test) — `causeGroups`
- Modify: `frontend/src/reading/story.ts` (+ `story.test.ts`) — `flowLabel`
- Modify: `frontend/src/workspace/context.ts`, `frontend/src/workspace/Workspace.tsx`, `frontend/src/workspace/Detail.tsx` (Focus wording)
- Modify: `frontend/src/workspace/workspace.css`
- Create: `frontend/e2e/outline-causes.spec.ts`

**Interfaces:**
- Consumes: Task 5 (`loadOutline`, `saveOutline`, `loadHidden`, `saveHidden`, `shown`, `causeOpen`, `doneCount`, `firstOpenAt`, `hiddenLabel`, `plainNames`), Task 6 (`{cause, at}` addresses).
- Produces:
  - `Ws.outline: OutlineView`, `Ws.setOutline(v: OutlineView): void` (saved per browser), `Ws.hidden: ReadonlySet<CheckKind>`, `Ws.setHidden(h: ReadonlySet<CheckKind>): void` (saved per browser).
  - `causeGroups(r: Pick<Reading, "threads">, list: Cause[]): { thread: string | null; label: string; stories: { story: string | null; causes: Cause[] }[] }[]`
  - `flowLabel(f: { path: string[] }, label: (id: string) => string | undefined): string` — `"main → logger_flush → uart_send"`, unknown steps "a function".
  - Accessible names: `aside.ws-rail.ws-outline` "Review contents"; switch buttons "Stories" / "Checks" (`aria-pressed`); story links `Go to story S2: <title>[ (read)][, n open]`; flow links `Go to flow N: <label>`; cause links `Open check: <line without backticks>`; the hidden-kinds `<details>` summary `hiddenLabel(...)`; Index links `Open the Index: <tab>` inside a `<details>` whose summary is "Index".
  - Focus folds the outline only (`folds.check` is left as the reader set it until Task 12 removes it).

- [ ] **Step 1: Write the failing unit tests**

Append to `frontend/src/reading/causes.test.ts` (add `causeGroups` to the import):

```ts
describe("the Checks view's groups", () => {
  const threads = [{ id: "T1", name: "`hal_write` in hal", stories: ["S2", "S1"] }, { id: "T3", name: "cpp", stories: ["S4"] }];
  it("are threads, then stories in reading order, then causes of no story; no thread goes last", () => {
    const list = [cause("c1", "caller", "S2", ["a"]), cause("c2", "result", "S1", ["b"]),
                  cause("c3", "ask", null, ["c"], { thread: "T3" }), cause("c4", "target", null, ["d"], { thread: null })];
    expect(causeGroups({ threads } as never, list).map((g) => [g.label, g.stories.map((s) => [s.story, s.causes.map((c) => c.id)])]))
      .toEqual([["A · `hal_write` in hal", [["S2", ["c1"]], ["S1", ["c2"]]]], ["B · cpp", [[null, ["c3"]]]],
                ["Across the change", [[null, ["c4"]]]]]);
  });
});
```

Append to `frontend/src/reading/story.test.ts` (add `flowLabel` to its import from `./story`):

```ts
describe("flowLabel", () => {
  it("names each step of the flow's path", () => {
    const names: Record<string, string> = { N1: "main", N2: "logger_flush" };
    expect(flowLabel({ path: ["N1", "N2", "N3"] }, (n) => names[n])).toBe("main → logger_flush → a function");
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/reading/causes.test.ts src/reading/story.test.ts`
Expected: FAIL (`causeGroups` / `flowLabel` is not a function).

- [ ] **Step 3: Implement the helpers**

Append to `frontend/src/reading/causes.ts` (import `letter` from `./checks` and `type Reading` from `./types`):

```ts
export interface CauseGroup { thread: string | null; label: string; stories: { story: string | null; causes: Cause[] }[] }

/** The outline's Checks view (§4.4): a group per thread, then per story in reading order, then the thread's causes of no
 * story; causes of no known thread under "Across the change". Causes keep their reading order. */
export function causeGroups(r: Pick<Reading, "threads">, list: Cause[]): CauseGroup[] {
  const known = new Set(r.threads.map((t) => t.id));
  const groups = [...r.threads.map((t, i) => ({ thread: t.id as string | null, label: `${letter(i, t.id)} · ${t.name}`, order: t.stories })),
                  { thread: null, label: "Across the change", order: [] as string[] }];
  return groups.map((g) => {
    const mine = list.filter((c) => (g.thread ? c.thread === g.thread : !c.thread || !known.has(c.thread)));
    const stories = [...g.order, null].map((s) => ({
      story: s, causes: mine.filter((c) => (s === null ? !c.story || !g.order.includes(c.story) : c.story === s)) }));
    return { thread: g.thread, label: g.label, stories: stories.filter((x) => x.causes.length) };
  }).filter((g) => g.stories.length);
}
```

Append to `frontend/src/reading/story.ts`:

```ts
/** A flow's one line, its path's names: "main → logger_flush → uart_send" (spec 2026-10-16-outline-and-causes §1.2). */
export function flowLabel(f: { path: string[] }, label: (id: string) => string | undefined): string {
  return f.path.map((n) => label(n) ?? "a function").join(" → ");
}
```

Run: `cd frontend && npx vitest run src/reading/causes.test.ts src/reading/story.test.ts` — Expected: PASS.

- [ ] **Step 4: Context and workspace state**

`frontend/src/workspace/context.ts`: import `type CheckKind` from `../reading/types` and `type OutlineView` from `../reading/causes`; add to `Ws` after `toggleFocus`:

```ts
  /** The outline's view, Stories or Checks, kept per browser (spec 2026-10-16-outline-and-causes §1.2). */
  outline: OutlineView;
  setOutline: (v: OutlineView) => void;
  /** The check kinds hidden from the outline, chips, counts and Next open check, kept per browser (§4.6). */
  hidden: ReadonlySet<CheckKind>;
  setHidden: (h: ReadonlySet<CheckKind>) => void;
```

and change the `focus` comment to `/** Focus: the outline folded and the panel widened, until pressed again or the panel closes. */`.

`frontend/src/workspace/Workspace.tsx`:

```tsx
  const [outline, setOutlineState] = useState<OutlineView>(loadOutline);
  const setOutline = useCallback((v: OutlineView) => { setOutlineState(v); saveOutline(v); }, []);
  const [hidden, setHiddenState] = useState<ReadonlySet<CheckKind>>(loadHidden);
  const setHidden = useCallback((h: ReadonlySet<CheckKind>) => { setHiddenState(h); saveHidden(h); }, []);
```

`shown` becomes `useMemo(() => (focus ? { ...folds, rail: true } : folds), [focus, folds])` (Focus folds the outline only). Add `outline, setOutline, hidden, setHidden` to the `ws` object and its dependency list. In the body, the left column becomes:

```tsx
            {(screen !== "phone" || level === "rail") && (r
              ? <Outline onPick={() => setDrawer(false)} hidden={screen === "tablet" && !drawer} />
              : <Rail show={hash} onPick={() => setDrawer(false)} hidden={screen === "tablet" && !drawer} />)}
```

(imports: `Outline` from `./Outline`; `loadHidden`, `loadOutline`, `type OutlineView`, `saveHidden`, `saveOutline` from `../reading/causes`; `type CheckKind` from `../reading/types`.)

`frontend/src/workspace/Detail.tsx` Focus button title: `focused ? "Bring back the contents" : "Fold the contents and widen this panel"`.

- [ ] **Step 5: Create `frontend/src/workspace/Outline.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { Story, StoryDetail } from "../board/types";
import { keys, load, loadWidth, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import HeadlinePill from "../components/HeadlinePill";
import { CHECK_ORDER, KIND_LABEL, letter, placeOf } from "../reading/checks";
import { causeGroups, causeOpen, doneCount, firstOpenAt, hiddenLabel, shown } from "../reading/causes";
import { threadRead } from "../reading/plan";
import { flowLabel } from "../reading/story";
import type { Cause, Check, CheckKind, Reading } from "../reading/types";
import { INDEX_TABS, type Place } from "./address";
import { useWs } from "./context";
import { INDEX_LABEL, short } from "./crumbs";
import NameText, { Ticks } from "./NameText";
import { plainNames } from "./names";
import Strip, { FoldButton } from "./Strip";

const scrollKey = (rid: number) => `ct.ws.${rid}.railScroll`;
const bare = (s: string) => s.replaceAll("`", "");

type Props = { onPick: () => void; hidden?: boolean };

/** The outline (spec 2026-10-16-outline-and-causes §1.2), for a review with a reading: Stories or Checks, its width
 * handle, its fold to a strip on a desktop and its scroll position per review, as the rail had. Folded, it is hidden,
 * not unmounted, so what the reader set in it survives. */
export default function Outline(props: Props) {
  const ws = useWs(), folded = ws.screen === "desktop" && ws.folds.rail;
  return <>
    {folded && <aside className="ws-rail folded" aria-label="Review contents">
      <Strip name="Contents" label="the contents" side="left" onUnfold={() => ws.setFold("rail", false)} /></aside>}
    <OutlineBody {...props} folded={folded} />
  </>;
}

function OutlineBody({ onPick, hidden = false, folded }: Props & { folded: boolean }) {
  const ws = useWs(), d = ws.data, r = d.reading!;
  const [width, setWidth] = useState(() => Math.min(600, Math.max(200, loadWidth(keys.railW, 280))));
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {                                        // the scroll position, per review and view
    const el = box.current, k = `${scrollKey(d.id)}.${ws.outline}`;
    if (!el) return;
    el.scrollTop = load<number>(k, 0);
    const on = () => save(k, el.scrollTop);
    el.addEventListener("scroll", on, { passive: true });
    return () => el.removeEventListener("scroll", on);
  }, [d.id, folded, ws.outline]);
  return (
    <aside className="ws-rail ws-outline" style={{ ["--w" as string]: `${width}px` }} aria-label="Review contents" inert={hidden} hidden={folded}>
      <Resizer size={width} edge="right" min={200} max={() => 600} onSize={setWidth} onDone={(w) => save(keys.railW, w)} />
      {ws.screen === "desktop" && <FoldButton label="the contents" side="left" onFold={() => ws.setFold("rail", true)} />}
      <div className="ws-outline-switch bd-seg" role="group" aria-label="Show in the outline">
        {(["stories", "checks"] as const).map((v) => (
          <button key={v} className={`bd-ibtn${ws.outline === v ? " on" : ""}`} aria-pressed={ws.outline === v}
                  onClick={() => ws.setOutline(v)}>{v === "stories" ? "Stories" : "Checks"}</button>
        ))}
      </div>
      <div className="ws-rail-scroll" ref={box}>
        {ws.outline === "stories" ? <StoriesView r={r} onPick={onPick} /> : <ChecksView r={r} onPick={onPick} />}
      </div>
    </aside>
  );
}

/** Stories (§1.2): the overview, each thread with its stories in reading order, the current story's flows, the tests,
 * and the Index folded at the bottom. */
function StoriesView({ r, onPick }: { r: Reading; onPick: () => void }) {
  const ws = useWs(), d = ws.data, ss = d.stories;
  const byId = new Map((ss?.stories ?? []).map((st) => [st.id, st]));
  const list = shown(r.causes ?? [], ws.hidden);
  const open = (pick: (c: Cause) => boolean) => list.filter((c) => pick(c) && causeOpen(c, r.marks)).length;
  const read = d.ticks ? new Set(d.ticks.stories) : null;
  const here = ws.addr.place.kind === "story" ? ws.addr.place.sid : null;
  const tests = (ss?.stories ?? []).filter((st) => st.kind === "tests");
  const story = (st: Story, why?: string) => {
    const n = open((c) => c.story === st.id), reason = st.kind === "unsorted" ? "Needs a person to place it" : why;
    const label = `Go to story ${st.id}: ${short(st.title)}${read?.has(st.id) ? " (read)" : ""}${n ? `, ${n} open` : ""}`;
    const place: Place = { kind: "story", sid: st.id, view: "steps" };
    return (
      <li key={st.id}>
        <Link to={ws.link(ws.item(place))} className="ws-row story" aria-current={here === st.id ? "page" : undefined}
              title={bare(st.title)} aria-label={label} onClick={onPick}
              onMouseEnter={() => ws.setHover(st.id)} onMouseLeave={() => ws.setHover(null)}
              onFocus={() => ws.setHover(st.id)} onBlur={() => ws.setHover(null)}>
          <span className="ws-row-top">
            {read && <span className="ws-read" aria-hidden>{read.has(st.id) ? "✓" : ""}</span>}
            <span className="ws-one"><Ticks text={st.title} /></span>
            {n > 0 && <span className="ck-count" aria-hidden>{n}</span>}
          </span>
          {reason && <span className="ws-row-sub">{reason}</span>}
        </Link>
        {here === st.id && <StoryFlows sid={st.id} onPick={onPick} />}
      </li>
    );
  };
  return <>
    <Link to={ws.base} state={{ page: true }} className="ws-row ws-home" aria-current={ws.addr.place.kind === "whole" ? "page" : undefined}
          title="Go to the overview" aria-label="Go to the overview" onClick={onPick}>
      <span aria-hidden>⌂</span> Overview <HeadlinePill h={r.headline} />
    </Link>
    {r.threads.map((t, i) => {
      const n = open((c) => c.thread === t.id);
      return (
        <div key={t.id} className="ws-group ws-thread">
          <h3><span className="ov-letter">{letter(i, t.id)}</span> <Ticks text={t.name} />
            {n > 0 && <span className="ck-count"><span className="vh">, </span>{n}<span className="vh"> open</span></span>}
            {read && <span className="ws-thread-read"><span className="vh">, </span>{threadRead(t.stories, read)}<span className="vh"> read</span></span>}</h3>
          <ul>{t.stories.map((sid) => (byId.get(sid) ? story(byId.get(sid)!, r.reasons[sid]) : null))}</ul>
        </div>
      );
    })}
    {tests.length > 0 && <div className="ws-group"><h3>Tests</h3><ul>{tests.map((st) => story(st))}</ul></div>}
    {!r.threads.length && !tests.length && <p className="muted small ws-pad">No changed functions.</p>}
    <details className="ws-index">
      <summary>Index</summary>
      <ul>{INDEX_TABS.filter((t) => t !== "checks").map((t) => (
        <li key={t}><Link to={ws.link(ws.item({ kind: "index", tab: t }))} className="ws-row ws-index-row"
                          aria-label={`Open the Index: ${INDEX_LABEL[t]}`} title={`Open the Index: ${INDEX_LABEL[t]}`} onClick={onPick}>
          <span className="ws-row-top">{INDEX_LABEL[t]}</span></Link></li>
      ))}</ul>
    </details>
  </>;
}

/** The current story's flows, numbered, one line each; a line opens the story's Flows tab at that flow's card. */
function StoryFlows({ sid, onPick }: { sid: string; onPick: () => void }) {
  const ws = useWs(), d = ws.data, storyOf = d.story;
  const [held, setHeld] = useState<{ sid: string; detail: StoryDetail } | null>(null);
  useEffect(() => {
    let live = true;
    storyOf(sid).then((x) => { if (live) setHeld({ sid, detail: x }); }).catch(() => { /* the page says why */ });
    return () => { live = false; };
  }, [sid, storyOf]);
  const det = held?.sid === sid ? held.detail : null;
  if (!det) return null;
  const flows = det.board.flows.filter((f) => det.story.flows.includes(f.id));
  if (!flows.length) return null;
  const labels = new Map(det.board.nodes.map((n) => [n.id, n.label]));
  const place: Place = { kind: "story", sid, view: "steps" };
  return (
    <ol className="ws-flows">{flows.map((f, i) => {
      const label = flowLabel(f, (n) => labels.get(n) ?? d.names[n]?.label);
      return (
        <li key={f.id}>
          <Link className="ws-row flow" to={ws.link({ ...ws.item(place), place, sec: undefined, flow: i + 1 })}
                aria-current={ws.addr.flow === i + 1 ? "true" : undefined}
                aria-label={`Go to flow ${i + 1}: ${label}`} title={label} onClick={onPick}>
            <span className="ws-row-top"><span className="muted">{i + 1}</span><span className="ws-one mono">{label}</span></span>
          </Link>
        </li>
      );
    })}</ol>
  );
}

/** Checks (§4.4): what is hidden, then each thread's causes by story, each one line with its done count; the checks
 * found no hazard folded at the bottom. */
function ChecksView({ r, onPick }: { r: Reading; onPick: () => void }) {
  const ws = useWs(), d = ws.data;
  if (!r.causes) return <p className="muted small ws-pad">Re-run the review to group its checks.</p>;
  const all = r.causes, list = shown(all, ws.hidden);
  const titles = new Map((d.stories?.stories ?? []).map((st) => [st.id, st.title]));
  const lit = ws.addr.open && "cause" in ws.addr.open ? ws.addr.open.cause : null;
  const flip = (k: CheckKind) => { const h = new Set(ws.hidden); if (!h.delete(k)) h.add(k); ws.setHidden(h); };
  const row = (c: Cause) => {
    const line = bare(plainNames(c.text, d.names)), done = !causeOpen(c, r.marks);
    return (
      <li key={c.id}>
        <Link className={`ws-row cause${done ? " finished" : ""}`} aria-current={lit === c.id ? "true" : undefined}
              to={ws.link(ws.opened({ cause: c.id, at: firstOpenAt(c, r.marks) }))} title={line}
              aria-label={`Open check: ${line}`} onClick={onPick}>
          <span className="ws-row-top"><span className={`ck-tag ${c.kind}`}>{KIND_LABEL[c.kind]}</span>
            <span className="ws-one"><Ticks text={plainNames(c.text, d.names)} /></span>
            <span className="ws-cdone">{done ? "✓" : `${doneCount(c, r.marks)}/${c.places.length}`}</span></span>
        </Link>
      </li>
    );
  };
  return <>
    <details className="ws-hidden">
      <summary>{hiddenLabel(ws.hidden, all)}</summary>
      <ul>{CHECK_ORDER.map((k) => (
        <li key={k}><label><input type="checkbox" checked={!ws.hidden.has(k)} onChange={() => flip(k)} /> {KIND_LABEL[k]}
          <span className="muted small"> {all.filter((c) => c.kind === k).length}</span></label></li>
      ))}</ul>
    </details>
    {causeGroups(r, list).map((g) => (
      <div key={g.thread ?? ""} className="ws-group ws-thread">
        <h3><Ticks text={g.label} /></h3>
        {g.stories.map((s) => (
          <div key={s.story ?? ""} className="ws-cgroup">
            {s.story && <h4 className="ws-one" title={bare(titles.get(s.story) ?? s.story)}><Ticks text={titles.get(s.story) ?? s.story} /></h4>}
            <ul>{s.causes.map(row)}</ul>
          </div>
        ))}
      </div>
    ))}
    {!list.length && <p className="muted small ws-pad">{all.length ? "Every check is of a hidden kind." : "Nothing to check."}</p>}
    <Cleared checks={r.cleared} />
  </>;
}

/** The findings the strong model judged no hazard, folded under their count with their reasons (names, never ids). */
function Cleared({ checks }: { checks: Check[] }) {
  if (!checks.length) return null;
  return (
    <details className="ck-cleared ws-pad">
      <summary>{checks.length} check{checks.length === 1 ? "" : "s"} found no hazard</summary>
      <ul>{checks.map((k) => (
        <li key={k.key}><NameText text={k.text} />{placeOf(k) && <span className="mono small"> · <Ticks text={placeOf(k)} /></span>}</li>
      ))}</ul>
    </details>
  );
}
```

- [ ] **Step 6: Styles**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the outline (spec 2026-10-16-outline-and-causes §1.2) */
.ws-outline-switch { display: flex; margin: 8px 14px 4px; }
.ws-outline-switch .bd-ibtn { flex: 1; }
.ws-one { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-pad { padding: 4px 14px; }
.ws-flows { list-style: none; margin: 0 0 4px; padding: 0 0 0 18px; }
.ws-row.flow { padding-top: 3px; padding-bottom: 3px; font-size: 12.5px; }
.ws-row.flow .muted { flex: none; width: 1.4em; text-align: right; }
.ws-cgroup h4 { margin: 6px 14px 2px; font-size: 12px; font-weight: 600; color: var(--muted); }
.ws-row.cause .ck-tag { flex: none; }
.ws-row.cause.finished { color: var(--muted); }
.ws-cdone { flex: none; font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.ws-hidden { margin: 4px 14px 8px; font-size: 13px; }
.ws-hidden summary { cursor: pointer; color: var(--muted); }
.ws-hidden ul { list-style: none; margin: 6px 0 0; padding: 0; }
.ws-hidden label { display: flex; align-items: center; gap: 6px; padding: 2px 0; }
.ws-index { margin: 12px 0 8px; }
.ws-index > summary { padding: 4px 14px; cursor: pointer; font-weight: 600; font-size: 13px; }
```

- [ ] **Step 7: Write the e2e test**

Create `frontend/e2e/outline-causes.spec.ts`:

```ts
import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

/** The outline and checks by cause (spec 2026-10-16-outline-and-causes): fixture CLs 101–104 make three threads; with
 * Confirm hidden their causes are a caller, a result and a reader in thread A and an ask in thread C. */
const FOUR = "101 102 103 104";

/** The reading as a review stored before causes: no `causes`, no `cause` on its checks. */
async function withoutCauses(page: Page) {
  const strip = async (route: import("@playwright/test").Route) => {
    const res = await route.fetch();
    const j = await res.json();
    const r = j.reading ?? j;
    if (r && typeof r === "object") { delete r.causes; for (const k of r.checks ?? []) delete k.cause; }
    await route.fulfill({ response: res, json: j });
  };
  await page.route("**/api/reviews/*/reading", strip);
  await page.route("**/api/reviews/*/stories/*", strip);
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the outline's Stories: threads with open causes, the current story's flows", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await expect(outline.getByRole("button", { name: "Stories" })).toHaveAttribute("aria-pressed", "true");
    await expect(outline.locator(".ws-thread h3")).toHaveText(["A hal_write in hal, 3 open, 0 of 2 read",
      "B logger_init in service, 0 of 2 read", "C svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
    await outline.getByRole("link", { name: /^Go to story S1/ }).click();
    const flows = outline.getByRole("link", { name: /^Go to flow / });
    await expect(flows.first()).toBeVisible();
    await flows.first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?flow=1$`));
    await expect(outline.locator("details.ws-index")).not.toHaveAttribute("open");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("the outline's Checks: causes by thread and story, Confirm hidden until shown, both remembered", async ({ page }) => {
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline.locator(".ws-thread h3")).toHaveText(["A · hal_write in hal", "C · svc::Engine::step in cpp"]);
    const rows = outline.locator(".ws-row.cause");
    expect((await rows.locator(".ck-tag").allInnerTexts()).sort())
      .toEqual(["Ask the author", "Caller not updated", "Result handled the old way", "Unchanged reader"]);
    await expect(rows.first().locator(".ws-cdone")).toHaveText("0/1");
    const hide = outline.locator("details.ws-hidden");
    await expect(hide.locator("summary")).toHaveText("Showing: all but Confirm · 2 hidden");
    await hide.locator("summary").click();
    await hide.getByLabel("Confirm").check();
    await expect(rows).toHaveCount(6);
    await expect(hide.locator("summary")).toHaveText("Showing all");
    await page.reload();
    await expect(outline.getByRole("button", { name: "Checks" })).toHaveAttribute("aria-pressed", "true");
    await expect(rows).toHaveCount(6);
    await outline.locator("details.ws-hidden summary").click();
    await outline.locator("details.ws-hidden").getByLabel("Confirm").uncheck();
    await expect(rows).toHaveCount(4);
    await rows.filter({ hasText: "uart_init calls hal_write" }).click();
    await expect(page).toHaveURL(/open=cause%3Ac[0-9a-f]{10}&at=1/);
    await expectNoNodeIds(page);
  });

  test("a review stored before causes still loads and says to re-run for its checks", async ({ page }) => {
    await withoutCauses(page);
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await expect(outline.locator(".ws-thread h3").first()).toHaveText("A hal_write in hal, 0 of 2 read");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline).toContainText("Re-run the review to group its checks.");
  });
});
```

- [ ] **Step 8: Build and run the e2e test**

Run: `cd frontend && npx tsc -b --noEmit && npm run build && mkdir -p /media/anoop/ssd_1/Work/CodeTortoise/.pwtmp && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts`
Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/workspace/Outline.tsx frontend/src/workspace/context.ts frontend/src/workspace/Workspace.tsx frontend/src/workspace/Detail.tsx frontend/src/workspace/workspace.css frontend/src/reading/causes.ts frontend/src/reading/causes.test.ts frontend/src/reading/story.ts frontend/src/reading/story.test.ts frontend/e2e/outline-causes.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): the outline: stories with their flows, checks by cause, hidden kinds

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 8: The stepper — the change above each place

**Files:**
- Create: `frontend/src/workspace/CauseStepper.tsx`
- Modify: `frontend/src/reading/causes.ts` (+ test) — `around`
- Modify: `frontend/src/workspace/Detail.tsx`, `frontend/src/workspace/Workspace.tsx` (the panel's key)
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/outline-causes.spec.ts`

**Interfaces:**
- Consumes: Task 4 `api.markChecks`, Task 5 (`openPlaces`, `doneCount`, `nextOpenAt`, `placeOpen`, `alsoAt`, `plainNames`), Task 6 (`{cause, at}`), Task 7 (`ws.setOutline`).
- Produces:
  - `around(text: string, line: number, n?: number): { line: number; text: string; at: boolean }[]` — lines `line-n … line+n` that exist (n = 3).
  - `CauseStepper({ cause, at })`; the panel's accessible name `Check: <line without backticks>`; buttons "Previous place", "Next place", "All look fine", "Looks fine & next" (or "Reopen" on a marked place), "Comment", "‹ Back", "Skip ›"; regions "The change", "The place"; links "Open the whole diff", "Open <path> at line <n>", `also:` links `Open check: <line>`, "Details" for a finding's cause (`Finding F4's details`).
  - Keys J (Skip), K (Back), F (Looks fine & next) when focus is not in a text field and no modifier is held.
  - A missing cause id: "This check isn't in this review." and a "Show the checks" button that switches the outline to Checks.

- [ ] **Step 1: Write the failing unit test**

Append to `frontend/src/reading/causes.test.ts` (add `around` to the import):

```ts
describe("around", () => {
  it("gives the place's line with three lines each side, as far as the file goes", () => {
    const text = ["a", "b", "c", "d", "e", "f", "g", "h"].join("\n");
    expect(around(text, 5).map((l) => [l.line, l.text, l.at])).toEqual([[2, "b", false], [3, "c", false], [4, "d", false],
      [5, "e", true], [6, "f", false], [7, "g", false], [8, "h", false]]);
    expect(around(text, 1).map((l) => l.line)).toEqual([1, 2, 3, 4]);
    expect(around(text, 40)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx vitest run src/reading/causes.test.ts`
Expected: FAIL (`around is not a function`).

- [ ] **Step 3: Implement `around`**

Append to `frontend/src/reading/causes.ts`:

```ts
/** The place's code in the stepper (§4.3): its line (1-based) with `n` lines each side, as far as the file goes. */
export function around(text: string, line: number, n = 3): { line: number; text: string; at: boolean }[] {
  const lines = text.split("\n");
  if (line < 1 || line > lines.length) return [];
  const out = [];
  for (let i = Math.max(1, line - n); i <= Math.min(lines.length, line + n); i++) out.push({ line: i, text: lines[i - 1], at: i === line });
  return out;
}
```

Run: `cd frontend && npx vitest run src/reading/causes.test.ts` — Expected: PASS.

- [ ] **Step 4: Create `frontend/src/workspace/CauseStepper.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { isChange, useEnsureSource } from "../board/useSources";
import Comments from "../components/Comments";
import SinkMark from "../components/SinkMark";
import { KIND_LABEL, markLine } from "../reading/checks";
import { alsoAt, around, doneCount, nextOpenAt, openPlaces, placeOpen } from "../reading/causes";
import type { Cause, Check, Mark } from "../reading/types";
import { useWs } from "./context";
import NameText, { Ticks } from "./NameText";
import { plainNames } from "./names";

const bare = (s: string) => s.replaceAll("`", "");
/** J, K and F are letters while the reader types (Review Focus 5). */
const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));

/** About seven lines around the place, from the after text of a changed file or the fetched text of another. */
function PlaceCode({ k }: { k: Check | null }) {
  const ws = useWs();
  const state = useEnsureSource(k?.depot ?? null, ws.sources);
  if (!k?.depot || k.line === null) return <p className="muted small">No code for this place.</p>;
  if (state === undefined || ("status" in state && state.status === "loading")) return <p className="muted small">Fetching the code…</p>;
  const text = isChange(state) ? state.after : "status" in state && state.status === "ok" ? state.file.text : null;
  const lines = text === null ? [] : around(text, k.line);
  if (!lines.length) return <p className="muted small">No code for this place.</p>;
  return (
    <pre className="cs-code">{lines.map((l) => (
      <div key={l.line} className={l.at ? "at" : undefined}><span className="cs-ln" aria-hidden>{l.line}</span>{l.text}</div>
    ))}</pre>
  );
}

/** The cause stepper (spec 2026-10-16-outline-and-causes §4.3): the cause's line and where the reader is among its
 * places; the change that raised it, always; the place with a few lines of code; Looks fine & next, Comment, Back and
 * Skip. Stepping onto a place ticks it read for this reader. */
export default function CauseStepper({ cause, at }: { cause: Cause; at: number }) {
  const ws = useWs(), d = ws.data, r = d.reading!, marks = r.marks;
  const checks = useMemo(() => new Map(r.checks.map((k) => [k.key, k])), [r.checks]);
  const n = cause.places.length, i = Math.min(Math.max(at, 1), n), key = cause.places[i - 1];
  const k = checks.get(key) ?? null, m = marks[key], open = placeOpen(key, marks);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [talk, setTalk] = useState(false);
  const { ticks, tick } = d;
  useEffect(() => {                                       // a new place: its comment box closed, its tick set
    setTalk(false);
    if (ticks && !ticks.checks.includes(key)) tick("check", key, true).catch(() => { /* the tick is a courtesy */ });
  }, [key]);                                              // eslint-disable-line react-hooks/exhaustive-deps
  const go = (to: number) => ws.go({ ...ws.addr, open: { cause: cause.id, at: to } }, true);
  const left = openPlaces(cause, marks), done = doneCount(cause, marks);
  const ahead = nextOpenAt(cause, marks, i, 1), behind = nextOpenAt(cause, marks, i, -1);
  const run = (act: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    act().catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
  };
  const reload = () => Promise.all([d.loadReading(), d.loadTicks().catch(() => {})]).then(() => {});
  const fineNext = () => run(async () => {
    await api.markCheck(d.id, key);
    await reload();
    const now: Record<string, Mark> = { ...marks, [key]: { key, user: "", at: "", source_line: "", changed: false } };
    const to = nextOpenAt(cause, now, i, 1);
    if (to !== null) go(to);
  });
  const reopen = () => run(async () => { await api.unmarkCheck(d.id, key); await reload(); });
  const allFine = () => run(async () => { await api.markChecks(d.id, left); await reload(); });
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
      if (e.key === "j" && ahead !== null) { e.preventDefault(); go(ahead); }
      else if (e.key === "k" && behind !== null) { e.preventDefault(); go(behind); }
      else if (e.key === "f" && open && !busy) { e.preventDefault(); fineNext(); }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });
  const ch = cause.change, first = ch?.lines.find((l) => l.sign === "+")?.line ?? ch?.lines[0]?.line ?? null;
  const place = k ? `${k.path}${k.line ? `:${k.line}` : ""}` : "";
  const also = k ? alsoAt(r.causes ?? [], checks, cause, key) : [];
  const talks = d.comments.filter((c) => c.parent_id === null && c.anchor_kind === "check" && c.anchor.key === key).length;
  return (
    <div className="cs">
      <div className="cs-head">
        <p className="cs-line"><span className={`ck-tag ${cause.kind}`}>{KIND_LABEL[cause.kind]}</span> <NameText text={cause.text} /></p>
        <div className="cs-nav">
          <button className="bd-ibtn" aria-label="Previous place" title="Previous place" disabled={i <= 1} onClick={() => go(i - 1)}>‹</button>
          <span className="cs-pos">{i} / {n}</span>
          <button className="bd-ibtn" aria-label="Next place" title="Next place" disabled={i >= n} onClick={() => go(i + 1)}>›</button>
          <span className="muted small cs-donecount">{done} done</span>
          <button className="cs-all" onClick={allFine} disabled={busy || !left.length}>All look fine</button>
        </div>
      </div>
      {ch && ch.lines.length > 0 && (
        <section className="cs-change" aria-label="The change">
          <h3>The change{ch.function && <> · <span className="mono">{ch.function}</span></>} · <span className="mono">{ch.path}{first ? `:${first}` : ""}</span></h3>
          <pre className="cs-diff">{ch.lines.map((l, j) => (
            <div key={j} className={l.sign === "+" ? "add" : l.sign === "-" ? "del" : undefined}><span className="cs-sign" aria-hidden>{l.sign}</span>{l.text}</div>
          ))}</pre>
          {ch.depot && <Link className="small" to={ws.link(ws.opened({ file: ch.depot, line: first }))}>Open the whole diff</Link>}
        </section>
      )}
      <section className="cs-place" aria-label="The place">
        <h3>Place {i} / {n}{k?.function && <> · <span className="mono">{k.function}</span></>}{place && <> · <span className="mono">{place}</span></>}</h3>
        {k && n > 1 && <p className="cs-row-text"><NameText text={k.text} /></p>}
        <PlaceCode k={k} />
        {k?.depot && <Link className="small" to={ws.link(ws.opened({ file: k.depot, line: k.line }))}
                           aria-label={`Open ${k.path}${k.line ? ` at line ${k.line}` : ""}`}>Open the file</Link>}
        {also.length > 0 && <p className="cs-also">also: {also.map((o, j) => {
          const line = plainNames(o.cause.text, d.names);
          return <span key={o.cause.id}>{j > 0 && " · "}<Link to={ws.link(ws.opened({ cause: o.cause.id, at: o.at }))}
                                                             aria-label={`Open check: ${bare(line)}`}><Ticks text={line} /></Link></span>;
        })}</p>}
        {m && <div className={`ck-mark${m.changed ? " changed" : ""}`}>{markLine(m)}</div>}
      </section>
      <div className="cs-acts">
        {open ? <button onClick={fineNext} disabled={busy}>Looks fine &amp; next</button>
          : <button className="link" onClick={reopen} disabled={busy}>Reopen</button>}
        <button className="link" onClick={() => setTalk(!talk)} aria-expanded={talk}>Comment{talks ? ` (${talks})` : ""}</button>
        <button className="link" onClick={() => behind !== null && go(behind)} disabled={behind === null}>‹ Back</button>
        <button className="link" onClick={() => ahead !== null && go(ahead)} disabled={ahead === null}>Skip ›</button>
        {cause.finding && <Link to={ws.link(ws.opened({ finding: cause.finding }))} title={`Finding ${cause.finding}'s details`}
                                aria-label={`Finding ${cause.finding}'s details`}>Details</Link>}
        {k?.kind === "reader" && k.field && <SinkMark label={k.field} />}
      </div>
      {!left.length && <p className="cs-done">{n === 1 ? "Its place is done" : `All ${n} places done`}</p>}
      {error && <div className="banner warn">{error}</div>}
      {talk && <Comments reviewId={d.id} comments={d.comments} kind="check" anchor={{ key }} onChange={d.loadComments} autoFocus />}
    </div>
  );
}
```

- [ ] **Step 5: Show it in the panel**

`frontend/src/workspace/Detail.tsx`:

```tsx
  const cid = "cause" in open ? open.cause : null;
  const cause = cid ? d.reading?.causes?.find((c) => c.id === cid) ?? null : null;
  const causeLine = cause ? plainNames(cause.text, d.names).replaceAll("`", "") : null;
```

- `label`: `cid ? (causeLine ? short(causeLine, 40) : null) : fid ? …` (the rest as today).
- `closeLabel`: `cid ? "Close the check" : fid ? "Close the finding" : "Close the code"`.
- The `<aside aria-label>`: `cid ? \`Check: ${causeLine ?? "not found"}\` : fid ? …`.
- `body()` starts with:

```tsx
    if (cid) return cause ? <CauseStepper cause={cause} at={(open as { at: number }).at} />
      : <div className="banner warn">This check isn't in this review.{" "}
          <button className="link" onClick={() => ws.setOutline("checks")}>Show the checks</button></div>;
```

- The name line's `<b className="mono">` becomes `<b className={cid ? undefined : "mono"}>`.

(imports: `CauseStepper` from `./CauseStepper`, `plainNames` from `./names`; `short` is already imported.)

`frontend/src/workspace/Workspace.tsx`: keep one panel per cause while its places change, so the reader's place in the page and the panel's width hold:

```tsx
            {addr.open && d && data.ready && (screen !== "phone" || level === "detail") &&
              <Detail key={"cause" in addr.open ? `c:${addr.open.cause}` : JSON.stringify(addr.open)} />}
```

- [ ] **Step 6: Styles**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the cause stepper (spec 2026-10-16-outline-and-causes §4.3) */
.cs { display: flex; flex-direction: column; gap: 12px; }
.cs-line { margin: 0; overflow-wrap: anywhere; }
.cs-nav { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.cs-pos { font-variant-numeric: tabular-nums; min-width: 4.5em; text-align: center; }
.cs-all { margin-left: auto; }
.cs-change, .cs-place { border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: var(--surface); }
.cs-change h3, .cs-place h3 { margin: 0 0 6px; font-size: 12.5px; font-weight: 600; color: var(--muted); overflow-wrap: anywhere; }
.cs-diff, .cs-code { margin: 0 0 6px; font-family: var(--mono); font-size: 12.5px; white-space: pre; overflow-x: auto; }
.cs-diff .add { background: color-mix(in srgb, var(--ok) 14%, transparent); color: var(--add-ink); }
.cs-diff .del { background: color-mix(in srgb, var(--bad) 14%, transparent); color: var(--del-ink); }
.cs-sign { display: inline-block; width: 1.4em; color: var(--muted); user-select: none; }
.cs-code .at { background: color-mix(in srgb, var(--accent) 14%, transparent); }
.cs-ln { display: inline-block; min-width: 3.2em; padding-right: 8px; text-align: right; color: var(--muted); user-select: none; }
.cs-also, .cs-row-text { margin: 6px 0 0; font-size: 13px; overflow-wrap: anywhere; }
.cs-acts { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.cs-done { margin: 0; color: var(--ok); font-weight: 600; }
```

- [ ] **Step 7: Write the e2e tests**

Append to `frontend/e2e/outline-causes.spec.ts`:

```ts
/** The large fixture (CLs 201 202): ten functions write each `…Dev::errors`, so each writer's readers are a cause of
 * five places in one unchanged file, whose text comes from the source API. */
const READERS = "5 places read UartDev::errors, which uart_a1 now writes";

test.describe("a cause of many places", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  async function openReaders(page: Page) {
    await startReview(page, "201 202");
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: `Open check: ${READERS}` }).click();
    return page.getByRole("complementary", { name: `Check: ${READERS}` });
  }

  test("the stepper shows the change above each place; J, K and F step, and All look fine finishes it", async ({ page }) => {
    const panel = await openReaders(page);
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    const change = panel.getByRole("region", { name: "The change" });
    await expect(change.locator("h3")).toContainText("uart_a1");
    await expect(change.locator(".cs-diff .add").first()).toContainText("errors");
    const place = panel.getByRole("region", { name: "The place" });
    await expect(place.locator("h3")).toContainText("uart_d1");
    await expect(place.locator(".cs-code .at")).toContainText("errors");
    await page.keyboard.press("j");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await expect(place.locator("h3")).toContainText("uart_d2");
    await page.keyboard.press("k");
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    await page.keyboard.press("f");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await expect(panel.locator(".cs-donecount")).toHaveText("1 done");
    const row = page.locator("aside.ws-outline").getByRole("link", { name: `Open check: ${READERS}` });
    await expect(row.locator(".ws-cdone")).toHaveText("1/5");
    await panel.getByRole("button", { name: "Comment" }).click();
    const box = panel.getByPlaceholder("Leave a comment…");
    await box.pressSequentially("jkf");                                   // letters while typing, not steps
    await expect(box).toHaveValue("jkf");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await panel.getByRole("button", { name: "All look fine" }).click();
    await expect(panel.locator(".cs-done")).toHaveText("All 5 places done");
    await expect(row.locator(".ws-cdone")).toHaveText("✓");
    await expect(page).toHaveURL(/open=cause%3Ac[0-9a-f]{10}&at=2/);
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("a place whose file text cannot be fetched says so and keeps its actions", async ({ page }) => {
    await page.route("**/api/reviews/*/source**", (route) => route.abort());
    const panel = await openReaders(page);
    await expect(panel.getByRole("region", { name: "The place" })).toContainText("No code for this place.");
    await expect(panel.getByRole("button", { name: "Looks fine & next" })).toBeEnabled();
    await expect(panel.getByRole("region", { name: "The change" })).toBeVisible();
  });
});

test.describe("an unknown check", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("an address naming a check the review lacks says so and leads to the checks", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}?open=cause:cffffffffff&at=1`);
    const panel = page.getByRole("complementary", { name: "Check: not found" });
    await expect(panel).toContainText("This check isn't in this review.");
    await panel.getByRole("button", { name: "Show the checks" }).click();
    await expect(page.locator("aside.ws-outline").getByRole("button", { name: "Checks" })).toHaveAttribute("aria-pressed", "true");
  });
});
```

- [ ] **Step 8: Build and run**

Run: `cd frontend && npx vitest run && npx tsc -b --noEmit && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts`
Expected: all pass (6 tests).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/workspace/CauseStepper.tsx frontend/src/workspace/Detail.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/workspace.css frontend/src/reading/causes.ts frontend/src/reading/causes.test.ts frontend/e2e/outline-causes.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): step through a cause's places with its change always in view

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 9: The top bar — one progress line, Next open check, the ? help

**Files:**
- Create: `frontend/src/workspace/HowToRead.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx` (`Head`)
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/outline-causes.spec.ts`

**Interfaces:**
- Consumes: Task 5 (`progressLine`, `openCount`, `shown`, `nextOpen`, `plainNames`), Task 7 (`ws.hidden`).
- Produces: the top bar's `.ws-progress` (`3 of 9 stories read · 12 causes open`; a reading without causes keeps today's `progressText`); a link "Next open check" (title `Next open check: <line>`), absent when nothing shown is open; a button "How to read this page" (`aria-expanded`) opening a dialog of the same name, closed by Escape, a press outside or the button.

- [ ] **Step 1: Write the failing e2e tests**

Append to `frontend/e2e/outline-causes.spec.ts`:

```ts
test.describe("the top bar", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Next open check walks the open causes in reading order and wraps; the progress line counts them", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const r = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/reading`)).json() as { causes: { kind: string; text: string }[] };
    const lines = r.causes.filter((c) => c.kind !== "confirm").map((c) => c.text.replaceAll("`", ""));
    expect(lines).toHaveLength(4);
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · 4 causes open");
    const next = page.getByRole("link", { name: "Next open check" });
    for (const line of [...lines, lines[0]]) {
      await next.click();
      await expect(page.getByRole("complementary", { name: `Check: ${line}` })).toBeVisible();
    }
    await page.getByRole("button", { name: "Looks fine & next" }).click();
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · 3 causes open");
    for (let i = 0; i < 3; i++) {
      await next.click();
      await page.getByRole("button", { name: "All look fine" }).click();
      await expect(page.locator(".cs-done")).toBeVisible();
    }
    await expect(next).toHaveCount(0);
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · every check done");
  });

  test("with every kind hidden there is no Next open check and nothing counted open", async ({ page }) => {
    await startReview(page, FOUR);
    await page.evaluate(() => window.localStorage.setItem("ct.ws.hiddenKinds", JSON.stringify(
      ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask"])));
    await page.reload();
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read");
    await expect(page.getByRole("link", { name: "Next open check" })).toHaveCount(0);
  });

  test("? opens how to read the page; Escape closes it", async ({ page }) => {
    await startReview(page, FOUR);
    const help = page.getByRole("button", { name: "How to read this page" });
    await help.click();
    const dialog = page.getByRole("dialog", { name: "How to read this page" });
    await expect(dialog).toContainText("J next, K back, F looks fine & next");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(help).toHaveAttribute("aria-expanded", "false");
  });
});
```

- [ ] **Step 2: Build and run them to see them fail**

Run: `cd frontend && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts -g "top bar"`
Expected: FAIL (the progress line reads `… · 0 of 6 checks`; no "Next open check"; no help button).

- [ ] **Step 3: Create `frontend/src/workspace/HowToRead.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";

/** How to read a review (spec 2026-10-16-outline-and-causes §1.1): behind the top bar's ?, for a reader new to
 * CodeTortoise; Escape, a press outside or the button closes it. */
export default function HowToRead() {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <span className="ws-help" ref={box}>
      <button className="bd-ibtn" aria-label="How to read this page" title="How to read this page" aria-expanded={open}
              onClick={() => setOpen(!open)}>?</button>
      {open && (
        <div className="ws-help-pop" role="dialog" aria-label="How to read this page">
          <h2>How to read this page</h2>
          <ul>
            <li><b>The outline</b> on the left lists the change's threads — stories joined by calls or shared data, lettered
              A, B… — and each thread's stories in reading order; the story you are on shows its flows.</li>
            <li><b>Checks</b> at the top of the outline lists what needs a reviewer's eye, grouped by the change that raised
              it. <b>Showing</b> hides kinds of check; Confirm is hidden until you show it.</li>
            <li><b>A check</b> opens beside the page: the change that raised it above each place it asks you to look at.
              <b> Looks fine &amp; next</b> clears a place for everyone, <b>All look fine</b> clears them all, <b>Comment</b>
              starts a thread. Keys: J next, K back, F looks fine &amp; next.</li>
            <li><b>Next open check ›</b> goes to the next place still open, in reading order.</li>
            <li><b>A story</b> has tabs: Flows (each path through the change, with its checks), Before → after, Where, Call
              paths, Code, Graph and Talk.</li>
            <li><b>Mark as read</b> ticks a story for you alone; the top bar counts the stories you have read and the checks
              still open.</li>
            <li><b>The side panel</b> keeps a tab per thing you open; <b>Focus</b> folds the outline to give it room.</li>
          </ul>
        </div>
      )}
    </span>
  );
}
```

- [ ] **Step 4: The top bar**

In `Head` (`frontend/src/workspace/Workspace.tsx`), replace the `ws-progress` line with:

```tsx
        {r && d.ticks && <span className="ws-progress">{line}</span>}
        {next && <Link className="ws-next" to={ws.link(ws.opened({ cause: next.cause, at: next.at }))} aria-label="Next open check"
                       title={`Next open check: ${nextLine}`}>Next open check ›</Link>}
        {r && <HowToRead />}
```

with, above the `return`:

```tsx
  const r = d.reading, causes = r?.causes;
  const p = r && d.ticks ? progress(r, d.ticks) : null;
  const line = !r || !p ? "" : causes
    ? progressLine(p.stories, p.storyCount, openCount(causes, ws.hidden, r.marks), shown(causes, ws.hidden).length)
    : progressText(p);
  const next = r && causes ? nextOpen(causes, ws.hidden, r.marks, {
    cause: ws.addr.open && "cause" in ws.addr.open ? ws.addr.open.cause : null,
    story: ws.addr.place.kind === "story" ? ws.addr.place.sid : null, order: r.order }) : null;
  const nextLine = next ? plainNames(causes!.find((c) => c.id === next.cause)!.text, d.names).replaceAll("`", "") : "";
```

(`d.reading` was used inline before; keep its other uses as they are. Imports: `HowToRead` from `./HowToRead`; `nextOpen`, `openCount`, `progressLine`, `shown` from `../reading/causes`; `plainNames` from `./names`.)

- [ ] **Step 5: Styles**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the top bar's Next open check and ? (spec 2026-10-16-outline-and-causes §1.1) */
.ws-next { white-space: nowrap; font-weight: 600; }
.ws-help { position: relative; }
.ws-help-pop { position: absolute; right: 0; top: calc(100% + 6px); z-index: 30; width: min(440px, calc(100vw - 32px));
  padding: 12px 16px; background: var(--surface); border: 1px solid var(--line); border-radius: 8px;
  box-shadow: 0 6px 24px rgb(0 0 0 / .18); font-size: 13.5px; line-height: 1.45; }
.ws-help-pop h2 { margin: 0 0 6px; font-size: 15px; }
.ws-help-pop ul { margin: 0; padding-left: 18px; }
.ws-help-pop li + li { margin-top: 6px; }
```

- [ ] **Step 6: Build and run**

Run: `cd frontend && npx tsc -b --noEmit && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/workspace/HowToRead.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/workspace.css frontend/e2e/outline-causes.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): the top bar counts open causes, goes to the next and explains the page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 10: The story page — header, summary and tabs

**Files:**
- Rename: `frontend/src/workspace/StoryTiles.tsx` → `frontend/src/workspace/StoryTabs.tsx` (`git mv`; its section components stay, its default export is replaced)
- Modify: `frontend/src/workspace/StoryPage.tsx`
- Modify: `frontend/src/reading/story.ts` (+ `story.test.ts`) — `storyTabs`, `storyNeighbours`
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/outline-causes.spec.ts`

**Interfaces:**
- Consumes: Task 5 (`shown`, `causeOpen`, `firstOpenAt`, `plainNames`), Task 6 (`Address.sec`, `STORY_SECS`), Task 7 (`flowLabel`, `ws.hidden`).
- Produces:
  - `type TabSec = "flows" | "changes" | "contracts" | "where" | "paths" | "code" | "graph" | "talk"`; `interface TabSpec { sec: TabSec; label: string; count: number | null }`
  - `storyTabs(kind: StoryKind, n: { flows: number; contracts: number; where: number; paths: number; code: number; talk: number }, graph: boolean): TabSpec[]` — mechanical, tests and unsorted start with Changes; behaviour with Flows always; other with Flows when it has flows; then Before → after, Where, Call paths, Code when they hold something; Graph when the story has one; Talk always (its composer).
  - `storyNeighbours(r: Pick<Reading, "threads">, sid: string): { after: string | null; feeds: string | null }` — the stories before and after it in its thread.
  - `StoryTabNav({ tabs, active, sid })`: `nav` "Story sections", a link per tab named `<label>[ <count>]` with `aria-current="page"` on the open one; switching pushes (Back returns to the tab before).
  - `tabsFor(detail, sr, flows: number, graph: boolean, comments: Comment[]): TabSpec[]` and default `StoryTabs({ detail, sr, flows, tabs })`.
  - Flow cards: `section` `Flow N: <label>` with `id="flow-N"`, lit when the address's `flow` is N and scrolled to; chips are links `Open check: <line>`; "Other checks in this story" region.
  - Header line `.st-crumb`: `Thread A · story 1 of 2[ · after: <title>][ · feeds: <title>]` (tests: `Tests`).

- [ ] **Step 1: Write the failing unit tests**

Append to `frontend/src/reading/story.test.ts` (import `storyNeighbours`, `storyTabs`):

```ts
describe("storyTabs", () => {
  const n = { flows: 2, contracts: 1, where: 3, paths: 0, code: 4, talk: 0 };
  it("a behaviour story starts with its flows, leaves out empty tabs and always offers Talk", () => {
    expect(storyTabs("behaviour", n, true).map((t) => `${t.label}${t.count ? ` ${t.count}` : ""}`))
      .toEqual(["Flows 2", "Before → after 1", "Where 3", "Code 4", "Graph", "Talk"]);
    expect(storyTabs("behaviour", { ...n, flows: 0 }, false)[0]).toEqual({ sec: "flows", label: "Flows", count: 0 });
  });
  it("a repeated edit, tests and unsorted start with their Changes; another story shows Flows only when it has some", () => {
    expect(storyTabs("mechanical", n, false).map((t) => t.sec)).toEqual(["changes", "contracts", "where", "code", "talk"]);
    expect(storyTabs("other", { ...n, flows: 0 }, true).map((t) => t.sec)).toEqual(["contracts", "where", "code", "graph", "talk"]);
  });
});

describe("storyNeighbours", () => {
  it("are the stories before and after it in its thread", () => {
    const threads = [{ id: "T1", stories: ["S2", "S1", "S5"] }] as never;
    expect(storyNeighbours({ threads }, "S1")).toEqual({ after: "S2", feeds: "S5" });
    expect(storyNeighbours({ threads }, "S2")).toEqual({ after: null, feeds: "S1" });
    expect(storyNeighbours({ threads }, "S9")).toEqual({ after: null, feeds: null });
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/reading/story.test.ts`
Expected: FAIL (`storyTabs is not a function`).

- [ ] **Step 3: Implement the helpers**

Append to `frontend/src/reading/story.ts` (import `type StoryKind` from `../board/types`):

```ts
/** A story page's tabs (spec 2026-10-16-outline-and-causes §2.2). */
export type TabSec = "flows" | "changes" | "contracts" | "where" | "paths" | "code" | "graph" | "talk";
export interface TabSpec { sec: TabSec; label: string; count: number | null }

/** The tabs a story shows, first the one it opens on: Changes for a repeated edit, tests or unsorted pieces; Flows for a
 * behaviour story (always) or another story with flows. Empty sections are left out; Talk always has its composer. */
export function storyTabs(kind: StoryKind, n: { flows: number; contracts: number; where: number; paths: number; code: number; talk: number },
                          graph: boolean): TabSpec[] {
  const first: TabSpec[] = kind === "mechanical" || kind === "tests" || kind === "unsorted" ? [{ sec: "changes", label: "Changes", count: null }]
    : kind === "behaviour" || n.flows ? [{ sec: "flows", label: "Flows", count: n.flows }] : [];
  const rest: TabSpec[] = [{ sec: "contracts", label: "Before → after", count: n.contracts }, { sec: "where", label: "Where", count: n.where },
                           { sec: "paths", label: "Call paths", count: n.paths }, { sec: "code", label: "Code", count: n.code }];
  return [...first, ...rest.filter((t) => t.count), ...(graph ? [{ sec: "graph" as const, label: "Graph", count: null }] : []),
          { sec: "talk", label: "Talk", count: n.talk }];
}

/** The header's "after:" and "feeds:": the stories before and after `sid` in its thread. */
export function storyNeighbours(r: Pick<Reading, "threads">, sid: string): { after: string | null; feeds: string | null } {
  const t = r.threads.find((x) => x.stories.includes(sid));
  if (!t) return { after: null, feeds: null };
  const i = t.stories.indexOf(sid);
  return { after: t.stories[i - 1] ?? null, feeds: t.stories[i + 1] ?? null };
}
```

Run: `cd frontend && npx vitest run src/reading/story.test.ts` — Expected: PASS.

- [ ] **Step 4: `StoryTabs.tsx`**

Run `git mv frontend/src/workspace/StoryTiles.tsx frontend/src/workspace/StoryTabs.tsx`. In it:

1. Keep `Contract`, `WhereDirs`, `PathRow`, `CallPaths`, `Code` as they are.
2. Split `ContractAndWhere` into two tab bodies (same markup as today's tiles, without the `st-pair` wrapper):

```tsx
function Contracts({ sr }: { sr: StoryReading }) {
  return (
    <section aria-label="Before → after">
      <ul className="st-contracts">{sr.contracts.map((r, i) => <Contract key={i} row={r} />)}</ul>
    </section>
  );
}

function Where({ sr }: { sr: StoryReading }) {
  const ws = useWs();
  const order = readOrder(sr.cl_order), grouped = (sr.cl_order?.length ?? 0) > 1;    // phase 2 §5.3
  return (
    <section aria-label="Where">
      {order && <p className="st-order">{order}</p>}
      {grouped ? whereByCl(sr.where, sr.cl_order!).map((g) => (
        <div key={g.cl ?? "none"} className="st-clgroup" role="group" aria-label={g.cl === null ? "Other files" : `CL ${g.cl}`}>
          <h4>{g.cl === null ? "Other" : `CL ${g.cl}`} · {g.files.length} file{g.files.length === 1 ? "" : "s"}</h4>
          <WhereDirs files={g.files} />
        </div>
      )) : <WhereDirs files={sr.where} />}
      {(sr.rewrites ?? []).length > 0 && (
        <ul className="st-rewrites">{sr.rewrites!.map((r, i) => {
          const t = rewriteText(r), label = `Open ${t.name}${r.line ? ` at line ${r.line}` : ""}, in all CLs`;
          return <li key={i}>{t.lead}{" "}<Link className="mono" to={ws.link(ws.opened({ file: r.file, line: r.line }))} title={label} aria-label={label}>{t.name}</Link></li>;
        })}</ul>
      )}
    </section>
  );
}
```

3. Delete `StoryAccount` and the old default export `StoryTiles`, and the `CheckTile`/`Cleared`/`CheckColumns` imports. Add:

```tsx
const bare = (s: string) => s.replaceAll("`", "");

/** A flow card's or the story's check chips (§2.3): one per shown cause, done ones muted with ✓; a chip opens the
 * stepper at the cause's first open place. */
function Chips({ causes }: { causes: Cause[] }) {
  const ws = useWs(), d = ws.data, marks = d.reading?.marks ?? {};
  if (!causes.length) return null;
  return (
    <ul className="st-chips">{causes.map((c) => {
      const line = plainNames(c.text, d.names), done = !causeOpen(c, marks);
      return (
        <li key={c.id}><Link className={`st-chip ${c.kind}${done ? " done" : ""}`} to={ws.link(ws.opened({ cause: c.id, at: firstOpenAt(c, marks) }))}
                             title={bare(line)} aria-label={`Open check: ${bare(line)}`}>{done && <span aria-hidden>✓ </span>}<Ticks text={line} /></Link></li>
      );
    })}</ul>
  );
}

/** Flows (§2.3): a numbered card per flow with the account's section for it (else the flow's text) and its checks;
 * then the story's checks that touch no flow, then what it means for the rest. */
function Flows({ detail, sr, flows }: { detail: StoryDetail; sr: StoryReading; flows: BoardFlow[] }) {
  const ws = useWs(), d = ws.data, lit = ws.addr.flow;
  const parts = sr.account ?? [], perFlow = parts.filter((p) => p.kind === "flow"), effects = parts.find((p) => p.kind === "effects");
  const causes = shown(sr.causes ?? [], ws.hidden);
  const labels = new Map(detail.board.nodes.map((n) => [n.id, n.label]));
  useEffect(() => { if (lit) document.getElementById(`flow-${lit}`)?.scrollIntoView({ block: "start" }); }, [lit]);
  const ids = new Set(flows.map((f) => f.id)), loose = causes.filter((c) => !c.flows.some((f) => ids.has(f)));
  return (
    <div className="st-flows">
      {flows.map((f, i) => {
        const label = flowLabel(f, (n) => labels.get(n) ?? d.names[n]?.label), part = perFlow[i];
        return (
          <section key={f.id} id={`flow-${i + 1}`} className={`st-flow${lit === i + 1 ? " lit" : ""}`} aria-label={`Flow ${i + 1}: ${label}`}>
            <h3><span className="st-flow-n">{i + 1}</span> <span className="mono">{label}</span></h3>
            {part ? <p><span className="ai-label">AI</span><NameText text={part.text} /></p>
              : <p>{f.what_source === "llm" && <span className="ai-label">AI</span>}<NameText text={f.what} /></p>}
            <Chips causes={causes.filter((c) => c.flows.includes(f.id))} />
          </section>
        );
      })}
      {!flows.length && <p className="muted">No flows in this story.</p>}
      {loose.length > 0 && <section className="st-other" aria-label="Other checks in this story"><h3>Other checks in this story</h3><Chips causes={loose} /></section>}
      {effects && <section className="st-effects" aria-label={effects.heading}><h3>{effects.heading}</h3>
        <p><span className="ai-label">AI</span><NameText text={effects.text} /></p></section>}
    </div>
  );
}

/** Talk (§2.4): the strong model's questions and suggested checks, then the story's comment thread. */
function Talk({ detail }: { detail: StoryDetail }) {
  const d = useWs().data, st = detail.story, questions = st.questions ?? [], suggested = st.check ?? [];
  return (
    <section aria-labelledby="ws-talk" className="ws-talk">
      <h3 id="ws-talk">Questions and comments</h3>
      {questions.length > 0 && <ul className="st-questions">{questions.map((q, k) => <li key={k}><span className="ai-label">AI</span><NameText text={q} /></li>)}</ul>}
      {suggested.length > 0 && <div className="st-suggested"><h4><span className="ai-label">AI</span>The strong model also suggests</h4>
        <ul>{suggested.map((c, k) => <li key={k}><NameText text={c} /></li>)}</ul></div>}
      <Comments reviewId={d.id} comments={d.comments} kind="story" anchor={{ id: st.id }} onChange={d.loadComments} compact />
    </section>
  );
}

/** The story's tabs and their counts. */
export function tabsFor(detail: StoryDetail, sr: StoryReading, flows: number, graph: boolean, comments: Comment[]): TabSpec[] {
  const st = detail.story;
  const talk = (st.questions?.length ?? 0) + comments.filter((c) => c.parent_id === null && c.anchor_kind === "story" && c.anchor.id === st.id).length;
  return storyTabs(st.kind, { flows, contracts: sr.contracts.length, where: sr.where.length, paths: sr.paths.length,
                              code: codeOrder(sr.where, sr.contracts).length, talk }, graph);
}

/** The tab row (§2.2): a link per tab with its count; switching is a step Back returns from. */
export function StoryTabNav({ tabs, active, sid }: { tabs: TabSpec[]; active: TabSec; sid: string }) {
  const ws = useWs();
  return (
    <nav className="st-tabs" aria-label="Story sections">{tabs.map((t) => {
      const to: Address = t.sec === "graph" ? { ...ws.addr, place: { kind: "story", sid, view: "graph" }, sec: undefined }
        : { ...ws.addr, place: { kind: "story", sid, view: "steps" }, sec: t.sec === tabs[0].sec ? undefined : t.sec,
            flow: t.sec === "flows" ? ws.addr.flow : null };
      return (
        <Link key={t.sec} to={ws.link(to)} className={active === t.sec ? "on" : undefined} aria-current={active === t.sec ? "page" : undefined}>
          {t.label}{t.count ? <span className="st-tabn"> {t.count}</span> : null}</Link>
      );
    })}</nav>
  );
}

/** A story with a reading (spec 2026-10-16-outline-and-causes §2): its tabs and the open one's body. */
export default function StoryTabs({ detail, sr, flows, tabs }: { detail: StoryDetail; sr: StoryReading; flows: BoardFlow[]; tabs: TabSpec[] }) {
  const ws = useWs(), st = detail.story;
  const active = tabs.find((t) => t.sec !== "graph" && t.sec === ws.addr.sec)?.sec ?? tabs[0].sec;
  return <>
    <StoryTabNav tabs={tabs} active={active} sid={st.id} />
    <div className="st-panel">
      {active === "flows" && <Flows detail={detail} sr={sr} flows={flows} />}
      {active === "changes" && (st.kind === "mechanical" ? <MechanicalStory detail={detail} />
        : st.kind === "tests" ? <TestsStory detail={detail} /> : <StoryWhy detail={detail} />)}
      {active === "contracts" && <Contracts sr={sr} />}
      {active === "where" && <Where sr={sr} />}
      {active === "paths" && <CallPaths sr={sr} detail={detail} />}
      {active === "code" && <Code sr={sr} detail={detail} />}
      {active === "talk" && <Talk detail={detail} />}
    </div>
  </>;
}
```

Imports for the file: `useEffect, useState` from react; `Link`; `type Comment` from `../api`; `type BoardFlow, type StoryDetail` from `../board/types`; `Comments`; `causeOpen, firstOpenAt, shown` from `../reading/causes`; `byEntry, codeOrder, flowLabel, foldPath, readOrder, rewriteText, storyTabs, type TabSec, type TabSpec, whereByCl, whereTree` from `../reading/story`; `type CallPath, type Cause, type ContractRow, type StoryReading, type WhereFile` from `../reading/types`; `type Address` from `./address`; `useWs`; `FunctionCode`; `NameText, { Ticks }`; `plainNames` from `./names`; `MechanicalStory, TestsStory` from `./StoryBodies`; `StoryWhy` from `./StoryPlan`.

- [ ] **Step 5: `StoryPage.tsx` for a review with a reading**

Rename today's `const header = (…)` to `const oldHeader = (…)` (kept as it is for a review without a reading) and add after it:

```tsx
  const nb = r ? storyNeighbours(r, sid) : { after: null, feeds: null };
  const titleOf = (id: string) => ss.stories.find((s) => s.id === id)?.title ?? id;
  const storyLink = (id: string) => (
    <Link className="st-nb" to={ws.link(ws.item({ kind: "story", sid: id, view: "steps" }))} title={titleOf(id).replaceAll("`", "")}
          aria-label={`Go to story ${id}: ${short(titleOf(id))}`}><Ticks text={titleOf(id)} /></Link>
  );
  const purpose = sr?.account?.find((p) => p.kind === "purpose");
  const readingHeader = r && (
    <header className="ws-story-head st-head">
      <h2>{hazards > 0 && <span className="ct-headline hazard">{hazards} hazard{hazards === 1 ? "" : "s"}</span>}
        {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
      <p className="st-crumb">
        {crumb ? <><Link to={ws.link(addressAt({ kind: "whole" }))} state={{ page: true }} title={`Go to thread ${crumb.letter} on the overview`}
                         aria-label={`Go to thread ${crumb.letter} on the overview`}>Thread {crumb.letter}</Link> · {crumb.text}</> : "Tests"}
        {nb.after && <> · after: {storyLink(nb.after)}</>}
        {nb.feeds && <> · feeds: {storyLink(nb.feeds)}</>}
      </p>
      <div className="st-tools">
        <span className="ws-pos">{step(-1)}{step(1)}</span>
        {d.ticks && <MarkRead sid={sid} order={r.order} />}
        <span className="ws-story-meta">
          {(sr ? clCounts(sr.where) : st.cls.map((cl) => ({ cl, functions: 0 }))).map(({ cl: c, functions: n }) => (
            <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>
              CL {c}{n > 0 && ` · ${n} function${n === 1 ? "" : "s"}`}</Link>
          ))}
          {targets.map((t) => <span key={t} className="ws-chip target" title={`Build target ${t}`}>⌖ {t}</span>)}
          {map && <Link className="ws-chip ws-onmap" to={ws.link(map)} title={`Show ${st.id} on the map`} aria-label={`Show ${st.id} on the map`}>◎ On the map</Link>}
        </span>
      </div>
      <div className="st-summary">
        {purpose ? <p><span className="ai-label">AI</span><NameText text={purpose.text} /></p>
          : <p>{st.text_source === "llm" && <span className="ai-label">AI</span>}<NameText text={st.purpose || st.summary} /></p>}
        {sr?.place_text && <p className="st-place">{sr.place_text}</p>}
        {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} askOnly={st.source === "tier1"}
                                              ask={{ kind: "story", anchor: { id: st.id }, onAsked: d.loadComments }} />}
      </div>
    </header>
  );
  const header = readingHeader || oldHeader;
```

Then, before today's `if (shown === "graph" && detail.graph)` branch, add the reading's branches:

```tsx
  if (r && sr) {
    const tabs = tabsFor(detail, sr, flows.length, hasGraph, d.comments);
    if (shown === "graph" && detail.graph)
      return (
        <div className="ws-page graph">
          <div className="ws-story-bar">{header}<StoryTabNav tabs={tabs} active="graph" sid={sid} /></div>
          <GraphView key={sid} board={detail.graph} prefKey={`${d.id}.${sid}`} flowIndex={index} onFlow={onFlow} quiet flows={flows}
                     stepsHref={ws.link({ ...ws.addr, place: { kind: "story", sid, view: "steps" } })}
                     onMore={() => ws.go({ ...ws.addr, place: { kind: "story", sid, view: "steps" } }, true)} />
        </div>
      );
    return <div className="ws-page"><div className="st-page">{header}<StoryTabs detail={detail} sr={sr} flows={flows} tabs={tabs} /></div></div>;
  }
```

and delete today's `if (r && sr) return …<StoryTiles…/>` line. Imports: `StoryTabs, { StoryTabNav, tabsFor }` from `./StoryTabs`; `storyNeighbours` from `../reading/story`. The Steps | Graph switch stays only in `oldHeader`.

- [ ] **Step 6: Styles**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the story page's header and tabs (spec 2026-10-16-outline-and-causes §2) */
.st-head h2 { margin: 0 0 4px; overflow-wrap: anywhere; }
.st-head .st-crumb { display: flex; flex-wrap: wrap; gap: 0 4px; align-items: baseline; margin: 0 0 6px; color: var(--muted); }
.st-nb { display: inline-block; max-width: 28ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.st-tools { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.st-tools .ws-story-meta { margin: 0; display: flex; flex-wrap: wrap; gap: 4px; font-size: 12px; }
.st-summary { margin-top: 10px; }
.st-summary p { margin: 0 0 6px; }
.st-tabs { display: flex; flex-wrap: wrap; gap: 2px 14px; margin: 14px 0 12px; border-bottom: 1px solid var(--line); }
.st-tabs a { padding: 6px 0; color: var(--muted); text-decoration: none; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.st-tabs a.on { color: var(--ink); border-bottom-color: var(--accent); font-weight: 600; }
.st-tabn { font-size: 12px; color: var(--muted); }
.st-flow { border: 1px solid var(--line); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; scroll-margin-top: 12px; }
.st-flow.lit { border-color: var(--accent); }
.st-flow h3 { margin: 0 0 6px; font-size: 14px; overflow-wrap: anywhere; }
.st-flow-n { display: inline-block; min-width: 1.6em; color: var(--muted); }
.st-chips { list-style: none; display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 0; padding: 0; }
.st-chip { display: inline-block; max-width: 100%; padding: 2px 10px; border: 1px solid var(--line); border-radius: 999px;
  font-size: 12.5px; text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.st-chip.done { color: var(--muted); opacity: .8; }
.st-other h3, .st-effects h3 { font-size: 14px; margin: 16px 0 6px; }
```

- [ ] **Step 7: Write the e2e tests**

Append to `frontend/e2e/outline-causes.spec.ts`:

```ts
test.describe("a story's tabs", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a header with its thread and neighbours, tabs in the address that Back returns through, chips that open checks", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S2`);
    await expect(page.locator(".st-crumb")).toHaveText(/^Thread A · story 1 of 2 · feeds: /);
    const tabs = page.getByRole("navigation", { name: "Story sections" });
    await expect(tabs.getByRole("link", { name: /^Flows/ })).toHaveAttribute("aria-current", "page");
    await tabs.getByRole("link", { name: /^Where/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?sec=where$`));
    await expect(page.getByRole("region", { name: "Where" })).toBeVisible();
    await tabs.getByRole("link", { name: /^Call paths/ }).click();
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?sec=where$`));
    await tabs.getByRole("link", { name: "Graph" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?view=graph$`));
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await page.goto(`${base}/s/S1`);
    const cards = page.getByRole("region", { name: /^Flow \d+:/ });
    await expect(cards.first()).toBeVisible();
    const chips = page.locator(".st-chip");
    expect(await chips.count()).toBeGreaterThan(0);
    const name = (await chips.first().getAttribute("aria-label"))!;
    await chips.first().click();
    await expect(page.getByRole("complementary", { name: name.replace("Open check: ", "Check: ") })).toBeVisible();
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("an outline flow line opens its card; a story remembers its tab; an old ?view=graph opens Graph", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("link", { name: /^Go to story S1/ }).click();
    await outline.getByRole("link", { name: /^Go to flow 1:/ }).click();
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toHaveClass(/\blit\b/);
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeInViewport();
    await page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: /^Code/ }).click();
    await outline.getByRole("link", { name: /^Go to story S2/ }).click();
    await outline.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(/\/s\/S1\?sec=code/);
    await page.goto(`${base}/s/S2?view=graph`);
    await expect(page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: "Graph" })).toHaveAttribute("aria-current", "page");
  });

  test("with every kind hidden a story shows no chips", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.evaluate(() => window.localStorage.setItem("ct.ws.hiddenKinds", JSON.stringify(
      ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask"])));
    await page.goto(`${base}/s/S1`);
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeVisible();
    await expect(page.locator(".st-chip")).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Other checks in this story" })).toHaveCount(0);
  });

  test("a story stored before causes shows no chips", async ({ page }) => {
    await withoutCauses(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeVisible();
    await expect(page.locator(".st-chip")).toHaveCount(0);
  });
});
```

- [ ] **Step 8: Build and run**

Run: `cd frontend && npx vitest run && npx tsc -b --noEmit && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts`
Expected: all pass. (`workspace-reading.spec.ts` and other old specs fail until Task 13.)

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src/workspace/StoryTabs.tsx frontend/src/workspace/StoryTiles.tsx frontend/src/workspace/StoryPage.tsx frontend/src/reading/story.ts frontend/src/reading/story.test.ts frontend/src/workspace/workspace.css frontend/e2e/outline-causes.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(story): a header that places the story, its sections as tabs, its flows with their checks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 11: The overview — Start here, thread blocks, connections

**Files:**
- Modify: `frontend/src/workspace/Overview.tsx` (rebuilt)
- Modify: `frontend/src/reading/overview.ts` (+ `overview.test.ts`) — `arcLayout`, `routeRows`, `introOpen`, `setIntroOpen` removed
- Modify: `frontend/src/board/prefs.ts` (`introOpen` key removed)
- Modify: `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/outline-causes.spec.ts`

**Interfaces:**
- Consumes: Task 5 (`shown`, `causeOpen`), Task 7 (`ws.hidden`).
- Produces: the overview's sections, each a region named by its heading: "The change as a whole" (with a link "Start here ›" or "Continue ›", or "You've read every story."), "Threads" (an `article` "Thread A" per thread: name, intro clamped to three lines, `2 stories · 0 read · 3 causes open`, a link `Go to thread A's first unread story` / `Go to thread A's first story`), "How the threads connect" (sentences), "Build impact", "Coverage" (with "Risks judged by rules only." when so, and the sinks line), "Discussion". Gone: How to read this page, Where to start, the progress line, the To check column, the threads' story lists, the arcs.

- [ ] **Step 1: Write the failing e2e test**

Append to `frontend/e2e/outline-causes.spec.ts`:

```ts
test.describe("the overview", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the change, Start here then Continue, a block per thread and how they connect; nothing pinned beside it", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(base);
    await expect(page.locator(".ov3 h2")).toHaveText(["The change as a whole", "Threads", "How the threads connect", "Build impact",
                                                 "Coverage", "Discussion"]);
    await expect(page.locator(".ov-thread").first().locator(".ov-meta")).toHaveText("2 stories · 0 read · 3 causes open");
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("Risks judged by rules only.");
    await expect(page.locator(".ov-howto, .ck-tile, .ov-progress, .ov-route, .ov2-check")).toHaveCount(0);
    await page.getByRole("link", { name: "Start here ›" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2`));
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1`));
    await page.goto(base);
    await expect(page.locator(".ov-thread").first().locator(".ov-meta")).toHaveText("2 stories · 1 read · 3 causes open");
    await page.getByRole("link", { name: "Continue ›" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1`));
    await page.goto(base);
    await page.getByRole("link", { name: "Go to thread B's first unread story" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S3`));
    await expectNoNodeIds(page);
    await expectNamed(page);
  });
});
```

- [ ] **Step 2: Build and run it to see it fail**

Run: `cd frontend && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts -g "the overview"`
Expected: FAIL (the headings start with "How to read this page").

- [ ] **Step 3: Rebuild `frontend/src/workspace/Overview.tsx`**

Keep `SinksLine` as it is. Replace the rest of the file with:

```tsx
import { Link } from "react-router-dom";
import SinkMark from "../components/SinkMark";
import { setShowSinks, showSinks, sinkLine } from "../lib/sinks";
import { causeOpen, shown } from "../reading/causes";
import { letter } from "../reading/checks";
import { cardText, connectionRows, testsLine } from "../reading/overview";
import type { Reading, SinkHit, Thread } from "../reading/types";
import { useWs } from "./context";
import { short } from "./crumbs";
import { Ticks } from "./NameText";
import { Discussion } from "./WholePage";

/** How the threads connect (spec 2026-10-16-outline-and-causes §3): a sentence per shown connection. */
function Connections({ r }: { r: Reading }) {
  if (!r.threads.length) return null;
  return (
    <section aria-labelledby="ov-conn">
      <h2 id="ov-conn">How the threads connect</h2>
      {r.threads.length === 1 ? <p className="muted">One thread: all stories are connected by calls or shared data.</p>
        : <ul className="ov-conn-rows">{connectionRows(r.threads, r.connections).map((row) => (
            <li key={row.text} className={row.bundled ? "bundled" : ""}><Ticks text={row.text} /></li>
          ))}</ul>}
    </section>
  );
}

/** A thread (§3): its letter and name, its introduction, how far the reader is and what is open, and a way in. */
function ThreadBlock({ t, i, r }: { t: Thread; i: number; r: Reading }) {
  const ws = useWs(), read = new Set(ws.data.ticks?.stories ?? []);
  const L = letter(i, t.id), done = t.stories.filter((s) => read.has(s)).length;
  const unread = t.stories.find((s) => !read.has(s)), to = unread ?? t.stories[0];
  const open = shown(r.causes ?? [], ws.hidden).filter((c) => c.thread === t.id && causeOpen(c, r.marks)).length;
  const meta = `${t.stories.length} stor${t.stories.length === 1 ? "y" : "ies"} · ${done} read${r.causes ? ` · ${open} cause${open === 1 ? "" : "s"} open` : ""}`;
  return (
    <article className="ov-thread" id={`thread-${t.id}`} aria-label={`Thread ${L}`}>
      <header>
        <span className="ov-letter">{L}</span>
        <h3>{t.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={t.name} /></h3>
      </header>
      <div className="ov-intro">{cardText(t).map((p) => (
        <p key={p.text} className="ov-purpose">{p.ai && <span className="ai-label">AI</span>}<Ticks text={p.text} /></p>
      ))}</div>
      <p className="ov-meta">{meta}</p>
      {to && <Link to={ws.link(ws.item({ kind: "story", sid: to, view: "steps" }))}
                   aria-label={`Go to thread ${L}'s ${unread ? "first unread" : "first"} story`}>
        {unread ? "First unread story ›" : "First story ›"}</Link>}
    </article>
  );
}

/** The overview (§3): the change as a whole and where to start reading, a block per thread, how they connect, then
 * what the change does to the build and what the analysis could not cover. */
export default function Overview({ r }: { r: Reading }) {
  const ws = useWs(), ss = ws.data.stories, read = new Set(ws.data.ticks?.stories ?? []);
  const next = r.order.find((s) => !read.has(s)) ?? null, started = r.order.some((s) => read.has(s));
  const tests = r.tests?.stories[0], testsStory = tests ? ss?.stories.find((s) => s.id === tests) : null;
  return (
    <div className="ws-page"><div className="ws-text ws-whole ov3">
      <section aria-labelledby="ov-whole" className="ov-top">
        <h2 id="ov-whole">The change as a whole</h2>
        <p className="ws-lead">{r.whole_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={r.whole} /></p>
        {next ? <Link className="ov-start" to={ws.link(ws.item({ kind: "story", sid: next, view: "steps" }))}>{started ? "Continue ›" : "Start here ›"}</Link>
          : r.order.length > 0 && <p className="muted">You've read every story.</p>}
      </section>
      {r.threads.length > 0 && (
        <section aria-labelledby="ov-threads">
          <h2 id="ov-threads">Threads</h2>
          {r.threads.map((t, i) => <ThreadBlock key={t.id} t={t} i={i} r={r} />)}
          {r.tests && (
            <p className="ov-tests">{testsStory
              ? <Link to={ws.link(ws.item({ kind: "story", sid: testsStory.id, view: "steps" }))}
                      title={`Go to story ${testsStory.id}: ${short(testsStory.title)}`}>{testsLine(r.tests, r.threads)}</Link>
              : testsLine(r.tests, r.threads)}</p>
          )}
        </section>
      )}
      <Connections r={r} />
      {r.build_impact.length > 0 && (
        <section aria-labelledby="ov-build">
          <h2 id="ov-build">Build impact</h2>
          <ul className="ov-lines">{r.build_impact.map((b) => (
            <li key={b.header}><Ticks text={b.text} />{b.note && <span className="muted"> {b.note}</span>}</li>
          ))}</ul>
        </section>
      )}
      {(r.coverage.length > 0 || (r.sinks?.length ?? 0) > 0 || r.rules_only) && (
        <section aria-labelledby="ov-cover">
          <h2 id="ov-cover">Coverage</h2>
          <ul className="ov-lines">
            {r.rules_only && <li>Risks judged by rules only.</li>}
            {r.coverage.map((c) => <li key={c}><Ticks text={c} /></li>)}
            {(r.sinks?.length ?? 0) > 0 && <SinksLine hits={r.sinks!} />}
          </ul>
        </section>
      )}
      <Discussion />
    </div></div>
  );
}
```

(`SinksLine` keeps its body; its imports `SinkMark`, `setShowSinks`, `showSinks`, `sinkLine`, `type SinkHit` are listed above. Check `Discussion` renders an `h2` "Discussion"; it does today.)

- [ ] **Step 4: Remove what the overview no longer uses**

In `frontend/src/reading/overview.ts` delete `arcLayout` (and its `Arc` type), `routeRows` (and `RouteRow`), `introOpen`, `setIntroOpen` and imports they alone used; in `overview.test.ts` delete their tests (the `arcLayout` describe, the `routeRows` cases, the `introOpen` describe). In `frontend/src/board/prefs.ts` delete the `introOpen` key and its comment. Run `grep -rn "arcLayout\|routeRows\|introOpen\|ov-howto\|ov-route" frontend/src` — Expected: no output.

- [ ] **Step 5: Styles**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the overview (spec 2026-10-16-outline-and-causes §3) */
.ov3 .ov-top .ov-start { display: inline-block; margin-top: 6px; padding: 6px 14px; border-radius: 6px; background: var(--accent);
  color: var(--surface); font-weight: 600; text-decoration: none; }
.ov3 .ov-thread { border: 1px solid var(--line); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; }
.ov3 .ov-thread header { display: flex; align-items: baseline; gap: 8px; }
.ov3 .ov-thread h3 { margin: 0; overflow-wrap: anywhere; }
.ov3 .ov-intro { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; margin: 6px 0; }
.ov3 .ov-intro p { margin: 0 0 4px; }
.ov3 .ov-meta { margin: 0 0 4px; color: var(--muted); font-size: 13px; }
```

- [ ] **Step 6: Build and run**

Run: `cd frontend && npx vitest run && npx tsc -b --noEmit && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/workspace/Overview.tsx frontend/src/reading/overview.ts frontend/src/reading/overview.test.ts frontend/src/board/prefs.ts frontend/src/workspace/workspace.css frontend/e2e/outline-causes.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(overview): the change, where to start reading, a block per thread; nothing pinned beside it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 12: Remove the To check column and Index › Checks; old links lead to causes

**Files:**
- Delete: `frontend/src/workspace/CheckColumns.tsx`, `frontend/src/workspace/CheckList.tsx`
- Modify: `frontend/src/workspace/address.ts` (+ test), `frontend/src/workspace/crumbs.ts` (+ test), `frontend/src/workspace/legacy.ts` (+ `legacy.test.ts`), `frontend/src/workspace/IndexPage.tsx`, `frontend/src/workspace/Outline.tsx`, `frontend/src/workspace/Rail.tsx`, `frontend/src/workspace/Workspace.tsx`, `frontend/src/workspace/context.ts`, `frontend/src/workspace/layout.ts` (+ `layout.test.ts`), `frontend/src/board/prefs.ts`, `frontend/src/reading/checks.ts` (+ `checks.test.ts`), `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/outline-causes.spec.ts`

**Interfaces:**
- Consumes: Task 5 `causeOfCheck`, Task 7 `ws.setOutline`.
- Produces:
  - `INDEX_TABS = ["cls", "files", "findings", "map"]`; `INDEX_LABEL` without `checks`.
  - `legacy(path, q, c)` returns `{ to: string; outline?: "checks" }` for `/i/checks` (`{ to: base, outline: "checks" }`); `#findings` leads to Index › Findings.
  - `?check=<check key or finding id>` is replaced (not pushed) by the stepper at that check's cause and place; without causes the address is left alone.
  - `Folds = { rail: boolean }`; keys `checkW`, `checkFolded` gone.

- [ ] **Step 1: Write the failing tests**

`frontend/src/workspace/legacy.test.ts` — add:

```ts
  it("Index › Checks, gone, opens the overview with the outline on Checks; #findings opens Index › Findings", () => {
    expect(legacy("/i/checks", new URLSearchParams(), ctx)).toEqual({ to: "/r/7", outline: "checks" });
    expect(indexFor("findings")).toEqual({ kind: "index", tab: "findings" });
  });
```

(use the file's existing context object — named `ctx` here; if it is named otherwise, use that name and its `base`.)

Append to `frontend/e2e/outline-causes.spec.ts`:

```ts
test.describe("old links", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("?check= and an old finding address open the stepper at that check; /i/checks the outline's Checks", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const id = base.split("/")[2];
    const r = await (await page.request.get(`/api/reviews/${id}/reading`)).json() as
      { checks: { key: string; text: string; finding: string | null }[] };
    const caller = r.checks.find((k) => k.text.startsWith("`uart_init` calls"))!;
    await page.goto(`${base}/s/S2?check=${encodeURIComponent(caller.key)}`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=cause%3Ac[0-9a-f]{10}&at=1$`));
    await expect(page.getByRole("complementary", { name: /^Check: uart_init calls hal_write/ })).toBeVisible();
    const sig = r.checks.find((k) => k.text === "hal_write: signature changed")!;
    await page.goto(`${base}/f/${sig.finding}`);
    await expect(page.getByRole("complementary", { name: "Check: hal_write: signature changed" })).toBeVisible();
    await page.goto(`${base}/i/checks`);
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.locator("aside.ws-outline").getByRole("button", { name: "Checks" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".ws-rail .ck-tile, .ov2-check, .ws-strip.right")).toHaveCount(0);
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/workspace/legacy.test.ts` — Expected: FAIL (`/i/checks` is current; `#findings` gives the checks tab).

- [ ] **Step 3: Index › Checks out; old links in**

- `address.ts`: `INDEX_TABS = ["cls", "files", "findings", "map"] as const`.
- `crumbs.ts`: `INDEX_LABEL = { cls: "CLs", files: "Files", findings: "Findings", map: "Map" }`; in `section()`, `anchor === "findings"` maps to `tab("findings")`. Update `crumbs.test.ts` cases that expected the Checks crumb to expect "Findings".
- `legacy.ts`: return type `{ to: string; outline?: "checks" } | { locate: string } | null`; first line of `legacy`: `if (path === "/i/checks") return { to: c.base, outline: "checks" };`; `ANCHORS.findings = { kind: "index", tab: "findings" }`.
- `IndexPage.tsx`: delete the `checks` count, the `tab === "checks"` block and the imports only it used (`CHECK_ORDER`, `KIND_LABEL`, `placeOf`, `CheckTile`, `Ticks`).
- `Outline.tsx`: the Index list maps `INDEX_TABS` directly (drop the `.filter((t) => t !== "checks")`).
- `Workspace.tsx`, in the legacy effect: `if ("to" in old) { if (old.outline) setOutline(old.outline); navigate(old.to, { replace: true }); return; }` (add `setOutline` to its dependencies). Add after it:

```tsx
  // an old `?check=` (a check key, or a finding id from an old finding address) opens the stepper there (§5.2)
  useEffect(() => {
    if (!addr.check || !r?.causes) return;
    const hit = causeOfCheck(r.causes, addr.check);
    go({ ...addr, check: null, ...(hit ? { open: { cause: hit.cause.id, at: hit.at } } : {}) }, true);
  }, [addr, r, go]);
```

(`r` is `data.reading`, declared above the effects; move its declaration up if it is below. Import `causeOfCheck` from `../reading/causes`.)

- [ ] **Step 4: The To check column out**

- `git rm frontend/src/workspace/CheckColumns.tsx frontend/src/workspace/CheckList.tsx`.
- `context.ts`: `export interface Folds { rail: boolean }`.
- `Workspace.tsx`: `useState<Folds>(() => ({ rail: load<unknown>(keys.railFolded, false) === true }))`; `setFold` saves `keys.railFolded`; `shown = focus ? { rail: true } : folds`.
- `layout.ts`: delete `CHECK_W`, `checkMax`, `loadCheckW`; `layout.test.ts`: delete their tests.
- `prefs.ts`: delete `checkW` and `checkFolded` and their comment lines (keep `headH`, reworded: `/** The review header's height, once dragged. */`).
- `reading/checks.ts`: delete `splitChecks`, `openCount`, `byThread` (no longer used; `grep -rn` to confirm) and their tests in `checks.test.ts`.
- `Rail.tsx`: delete the `if (r && ss) { … }` reading branch (the outline shows reviews with a reading) and the imports only it used; the rail is now only for reviews without a reading.
- `Detail.tsx`: no change beyond Task 7's Focus wording.
- CSS: list the classes no component uses any more and delete their rules:

```bash
cd frontend && for c in $(grep -oE '^\.[a-z0-9-]+' src/workspace/workspace.css | sort -u | tr -d .); do
  grep -rqE "[\"' ]$c[\"' ]|\"$c\"|$c\b" src --include=*.tsx --include=*.ts || echo $c; done
```

  Expected candidates include `ov2`, `ov2-left`, `ov2-right`, `ov2-check`, `ov2-cols`, `check-folded`, `ck-tile`, `ck-head`, `ck-list`, `ck-group`, `ck-row`, `ck-top`, `ck-text`, `ck-place`, `ck-dir`, `ck-file`, `ck-src`, `ck-acts`, `ck-read`, `ck-all`, `ck-all-p`, `st-tiles`, `st-pair`, `ov-howto`, `ov-route`, `ov-route-go`, `ov-skim`, `ov-conn`, `ov-box`, `ov-arcs`, `ov-arc`, `ov-arc-label`, `ov-ask`, `ov-progress`, `ws-missed`. Delete each listed class's rules (and media-query copies); keep any the script lists that a component still builds from a template string (check with `grep -rn "<class>" src` before deleting). Keep `ck-tag`, `ck-count`, `ck-mark`, `ck-cleared`.

- [ ] **Step 5: Run everything that builds**

Run: `cd frontend && npx vitest run && npx tsc -b --noEmit && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts`
Expected: vitest and tsc pass; `outline-causes.spec.ts` all pass.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src
git add frontend/e2e/outline-causes.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "refactor(workspace): no To check column or Index › Checks; old check links open the stepper

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 13: Move the existing e2e specs onto the new layout

**Files:**
- Modify: `frontend/e2e/helpers.ts` (`openIndex`)
- Modify: `frontend/e2e/workspace-reading.spec.ts`, `workspace.spec.ts`, `workspace-detail.spec.ts`, `workspace-layout.spec.ts`, `workspace-panels.spec.ts`, `workspace-plan.spec.ts`, `workspace-story.spec.ts`, `workspace-tier1.spec.ts`, `workspace-sinks.spec.ts`, `workspace-legacy.spec.ts`, `workspace-pages.spec.ts`, `long-text.spec.ts`, `ai.spec.ts`, `mention.spec.ts`

**Interfaces:**
- Consumes: every accessible name listed in Tasks 7–12.
- Produces: `openIndex(page: Page, tab: "CLs" | "Files" | "Findings" | "Map"): Promise<void>` in `helpers.ts`.

The old UI and what replaces it in the specs:

| Old | New |
|---|---|
| `page.locator(".ws-rail").getByRole("link", { name: "Open the Index: X" }).click()` | `await openIndex(page, "X")` |
| `getByRole("region", { name: "To check" })` rows, `.ck-row`, `.ck-tile` | the outline's Checks view (`aside.ws-outline` → button "Checks" → `.ws-row.cause` / link `Open check: …`) and the stepper (`complementary` `Check: …`) |
| a row's "Looks fine" / "Reopen" | the stepper's "Looks fine & next" / "Reopen" |
| a row's "Comment" | the stepper's "Comment" (placeholder "Leave a comment…") |
| a row's "Open" (`Open <path> at line <n>`) | the stepper's "Open the file" (same accessible name `Open <path> at line <n>`) |
| a row's "Details" (`Finding F's details`) | the stepper's "Details" for a finding's cause (same name) |
| a row's Read checkbox | gone: stepping onto a place ticks it (check `/api/reviews/{id}/ticks`) |
| `.ck-count` "N open" on the rail / tile | the outline thread's `.ck-count` (open causes) or the top bar's `.ws-progress` |
| "Possibly missed" link | the outline's "Checks" button |
| `.ov2-left` | `.ov3` |
| `.ov-howto`, "Where to start", `.ov-route`, `.ov-conn` arcs, `.ov-progress`, `.ov-reason` | gone (help: the top bar's "How to read this page"; connections: `.ov-conn-rows li`) |
| `getByRole("tab", { name: "Steps" / "Graph" })` on a review with a reading | `getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: /^Flows/ })` / `{ name: "Graph" }` |
| regions "Before → after", "Where", `/^Call paths/`, "Code", "Questions and comments" | the same regions, after clicking that tab in "Story sections" (Talk for questions and comments) |
| region "What it does" | `.st-summary` (purpose), the flow cards `Flow N: …` (account per flow), the effects region named by its heading |
| `.st-crumb` "Thread A › name · story 1 of 2" | "Thread A · story 1 of 2 · feeds: …" (`toHaveText(/^Thread A · story 1 of 2/)`) |
| "Fold To check", "Unfold To check", `.ws-strip.right`, `ct.ws.checkW` | gone |
| `/i/checks` | the overview with the outline on Checks |

- [ ] **Step 1: Add the helper**

Append to `frontend/e2e/helpers.ts`:

```ts
/** Open a tab of the Index from the outline, unfolding its Index first (spec 2026-10-16-outline-and-causes §1.2). */
export async function openIndex(page: Page, tab: "CLs" | "Files" | "Findings" | "Map") {
  const index = page.locator(".ws-rail details.ws-index");
  if (!(await index.evaluate((el) => (el as HTMLDetailsElement).open))) await index.locator("summary").click();
  await index.getByRole("link", { name: `Open the Index: ${tab}` }).click();
}
```

Then replace every `page.locator(".ws-rail").getByRole("link", { name: "Open the Index: …" }).click()` in `e2e/` with `openIndex(page, "…")` (files: `workspace.spec.ts` 161, 196; `workspace-detail.spec.ts` 11, 69, 81, 97, 116; `workspace-sinks.spec.ts` 52; `workspace-story.spec.ts` 75; `workspace-pages.spec.ts` 127; `mention.spec.ts` 8; `ai.spec.ts` 112; `workspace-reading.spec.ts` rail test) and import `openIndex`. Where a test only asserts the Index link is visible (`workspace-panels.spec.ts` 112), open the `details.ws-index` first.

- [ ] **Step 2: `workspace-reading.spec.ts`**

Replace the desktop tests named below with these (keep `FOUR`, `rerun`, imports; add `openIndex`):

```ts
  test("the overview tells the change as threads, how they connect and what to check", async ({ page }) => {
    await startReview(page, FOUR);
    await expect(page.locator(".ov3 h2")).toHaveText(["The change as a whole", "Threads", "How the threads connect", "Build impact",
                                                      "Coverage", "Discussion"]);
    await expect(page.locator(".ov3 .ws-lead")).toHaveText("3 threads: A and B: both run inside main; B and C: nothing besides arriving in CL 104.");
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
    const threads = page.locator(".ov-thread");
    await expect(threads.locator("h3")).toHaveText(["hal_write in hal", "logger_init in service", "svc::Engine::step in cpp"]);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline.locator(".ws-thread h3")).toHaveText(["A · hal_write in hal", "C · svc::Engine::step in cpp"]);
    await outline.locator("details.ws-hidden summary").click();
    await outline.locator("details.ws-hidden").getByLabel("Confirm").check();
    expect((await outline.locator(".ws-row.cause .ck-tag").allInnerTexts()).sort()).toEqual(["Ask the author", "Caller not updated",
      "Confirm", "Confirm", "Result handled the old way", "Unchanged reader"]);
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("Risks judged by rules only.");
    await expect(page.getByRole("region", { name: "Build impact" })).toContainText("include/hal/regs.h declaration change → 4 files rebuild");
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("No test code found in the workspace");
    await expectNoNodeIds(page);
    await expectNamed(page);
    await threads.first().getByRole("link", { name: "Go to thread A's first unread story" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
  });

  test("the overview gives each thread its intro and a way into its first unread story", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const card = page.locator(".ov-thread").first();
    await expect(card.locator(".ov-purpose")).toHaveCount(2);                            // its purpose, then the fixed intro
    await expect(card.locator(".ov-purpose").last()).toContainText("Starts with “hal_write's signature changed");
    await expect(card.locator(".ov-purpose .ai-label")).toHaveCount(0);
    await card.getByRole("link", { name: "Go to thread A's first unread story" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2$`));
    await expectNamed(page);
  });

  test("Looks fine marks a check's place for everyone and survives a re-run", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    const row = outline.getByRole("link", { name: /^Open check: uart_init calls hal_write/ });
    await row.click();
    const panel = page.getByRole("complementary", { name: /^Check: uart_init calls hal_write/ });
    await panel.getByRole("button", { name: "Looks fine & next" }).click();
    await expect(panel.locator(".ck-mark")).toHaveText("Looks fine · demo · just now");
    await expect(row.locator(".ws-cdone")).toHaveText("✓");
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · 3 causes open");
    await rerun(page, base);
    await page.reload();                                                             // the cause keeps its id across the re-run
    await expect(row.locator(".ws-cdone")).toHaveText("✓");
    await panel.getByRole("button", { name: "Reopen" }).click();
    await expect(row.locator(".ws-cdone")).toHaveText("0/1");
  });

  test("a check's place takes a comment thread of its own", async ({ page }) => {
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: /^Open check: logger_flush ignores the result/ }).click();
    const panel = page.getByRole("complementary", { name: /^Check: logger_flush ignores the result/ });
    await panel.getByRole("button", { name: "Comment" }).click();
    await panel.getByPlaceholder("Leave a comment…").fill("flush should retry");
    await panel.locator(".comments").getByRole("button", { name: "Comment" }).click();
    await expect(panel.locator(".comments")).toContainText("flush should retry");
    await expect(panel.getByRole("button", { name: "Comment (1)" })).toBeVisible();
  });

  test("a story: its thread, what it does, its tabs, its call paths and the checks on its flows", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S2`);
    const head = page.locator(".ws-story-head");
    await expect(head.locator(".st-crumb")).toHaveText(/^Thread A · story 1 of 2 · feeds: /);
    await expect(head.locator(".ws-story-meta .ws-chip").first()).toHaveText("CL 102 · 1 function");
    const tabs = page.getByRole("navigation", { name: "Story sections" });
    await tabs.getByRole("link", { name: /^Before → after/ }).click();
    const contract = page.getByRole("region", { name: "Before → after" });
    await expect(contract).toContainText("hal_write: gained unsigned");
    await expect(contract.locator("mark")).toHaveText("unsigned");
    await tabs.getByRole("link", { name: /^Call paths/ }).click();
    const paths = page.getByRole("region", { name: /^Call paths/ });
    await expect(paths.locator(".st-steps")).toHaveText(["contractmain→uart_init→hal_write",
      "callmain→logger_flush→uart_send→hal_write", "callmain→logger_write→uart_send→hal_write"]);
    await tabs.getByRole("link", { name: /^Where/ }).click();
    await page.getByRole("region", { name: "Where" }).getByRole("link", { name: "Open hal_write in hal/regs.c at line 10" }).click();
    await expect(page.getByRole("complementary", { name: "Code: regs.c" })).toBeVisible();
    await head.getByRole("link", { name: /^Next story: S1/ }).click();
    await expect(head.locator(".st-crumb")).toHaveText(/^Thread A · story 2 of 2 · after: /);
    await expect(page.locator(".st-place")).toHaveText("Uses what story 1 adds.");
    await expect(page.locator(".st-chip").first()).toBeVisible();
    await tabs.getByRole("link", { name: /^Call paths/ }).click();
    await expect(paths.locator(".st-steps").nth(1)).toHaveText("statemain→… 2 more→Uart::errors→uart_errors");
    await paths.getByRole("button", { name: "Show the 2 folded steps" }).click();
    await expect(paths.locator(".st-steps").nth(1)).toHaveText("statemain→logger_write→uart_send→Uart::errors→uart_errors");
    await expectNoNodeIds(page);
    await expectNamed(page);
    await paths.getByRole("link", { name: /On the graph/ }).first().click();
    await expect(page).toHaveURL(/\/s\/S1\?view=graph&flow=1/);
    await expect(page.locator(".bd-node").first()).toBeVisible();
  });

  test("the outline: the overview, each thread with its stories in reading order, its checks and the Index", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await expect(outline.getByRole("link", { name: "Go to the overview" })).toContainText("Medium risk · rules only");
    await expect(outline.locator(".ws-thread h3")).toHaveText(["A hal_write in hal, 3 open, 0 of 2 read", "B logger_init in service, 0 of 2 read",
                                                               "C svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
    await expect(outline.locator(".ws-thread").first().getByRole("link", { name: /^Go to story/ })).toHaveCount(2);
    await expect(outline.locator(".ws-thread").first().getByRole("link", { name: /^Go to story/ }).nth(1)).toHaveAccessibleName(/^Go to story S1/);
    await outline.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Thread A");
    await openIndex(page, "Files");
    await expect(page).toHaveURL(new RegExp(`${base}/i/files$`));
    await expect(page.getByRole("tab", { name: /^Files/ })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("link", { name: "Open logger.c's diff" }).click();
    await expect(page.getByRole("complementary", { name: "Code: logger.c" })).toBeVisible();
    await page.getByRole("tab", { name: /^CLs/ }).click();
    await page.getByRole("link", { name: "Open CL 104" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/cl/104$`));
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline.locator(".ws-row.cause")).toHaveCount(4);
    await expectNamed(page);
  });

  test("old addresses: a finding opens the stepper on its story, its Details the finding, #map the Index's map", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const findings = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as { id: string; title: string; severity: string }[];
    const sig = findings.find((f) => f.title === "hal_write: signature changed")!;
    await page.goto(`${base}/f/${sig.id}`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=cause%3Ac[0-9a-f]{10}&at=1$`));
    const panel = page.getByRole("complementary", { name: "Check: hal_write: signature changed" });
    await panel.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=finding%3A${sig.id}$`));
    await expect(page.locator(".ws-detail .ws-finding h2")).toContainText("hal_write: signature changed");
    const info = findings.find((f) => f.severity === "info")!;
    await page.goto(`${base}/f/${info.id}`);
    await expect(page.locator(".ws-finding h2")).toBeVisible();
    await page.goto(`${base}#map`);
    await expect(page).toHaveURL(new RegExp(`${base}/i/map$`));
    await expect(page.getByRole("region", { name: "The map" })).toBeVisible();
  });
```

and replace the two phone tests with:

```ts
  test("the overview's connections are sentences and nothing scrolls sideways", async ({ page }) => {
    await startReview(page, FOUR);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });

  test("a story's tabs wrap on a phone", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    await expect(page.getByRole("navigation", { name: "Story sections" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
```

- [ ] **Step 3: The other specs**

Make these edits, each following the table above:

- `workspace.spec.ts` 34–39: the overview's headings become `page.locator(".ov3 h2")` with `["The change as a whole", "Threads", "How the threads connect", "Build impact", "Coverage", "Discussion"]` (drop "Build impact" or "Coverage" if the 101 102 fixture has none — the old list shows which sections it had); the five To check rows become: switch the outline to Checks, then `expect(page.locator(".ws-row.cause")).toHaveCount(n)` where `n` is `causes.filter((c) => c.kind !== "confirm").length` from `GET /api/reviews/{id}/reading`.
- `workspace-detail.spec.ts` 152–155 ("a To check row opens its file at its line"): open the outline's Checks, the cause `Open check: uart_init calls hal_write…`, then the stepper's link `Open driver/uart.c at line 8`; the rest of the test stays.
- `workspace-layout.spec.ts`: delete "the story fills the centre and a divider sets the To check column's width…" (27) and "the overview fills the centre and shares the story's To check divider" (82); replace "a check row's actions wrap inside the To check column at its narrowest" (73) with:

```ts
test("the stepper's actions wrap inside the side panel at its narrowest", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addInitScript(() => window.localStorage.setItem("ct.ws.detailW", "320"));
  await startReview(page);
  await page.getByRole("link", { name: "Next open check" }).click();
  const acts = page.locator(".cs-acts");
  await expect(acts).toBeVisible();
  expect(await acts.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
});

test("the overview fills the centre", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1000 });
  await startReview(page);
  const centre = page.getByRole("region", { name: "Centre" });
  expect(await width(page.locator(".ws-page > .ov3"))).toBeGreaterThan(Math.min(900, (await width(centre)) - 80));
  await expect(page.locator(".ov2-check")).toHaveCount(0);
});
```

  (`.ws-text` may cap the overview's width as it caps other text pages: if the existing CSS gives `.ws-text` a max width, the `Math.min(900, …)` floor holds.)
- `workspace-panels.spec.ts`:
  - 13 ("a check's Details opens its finding…"): go to `${base}/f/${sig.id}` (opens the stepper on S2), click the stepper's `Finding ${sig.id}'s details`, expect the finding panel and `getByRole("navigation", { name: "Story sections" })` visible (the story stays); `page.goBack()` shows the stepper again (`Check: hal_write: signature changed`).
  - 34 (the panel's tabs): open the finding through the stepper as above instead of the row's Details; expect a tab named after the cause (`hal_write: signature changed`) beside the finding's.
  - 53 (folds and Focus): drop every To check step; the outline folds to `.ws-strip.left`, stays folded after a reload, and Focus folds it and widens the panel until pressed again; open the panel with `openIndex(page, "Files")` and a file's diff link instead of the To check row's Open.
  - 97 (storage blocked): drop the To check fold steps.
  - 109 (Index › Findings): replace lines 112–114 with `await openIndex(page, "Findings")`.
- `workspace-plan.spec.ts`:
  - 27: the header line reads `toHaveText(/^\d+ of \d+ stories read( · (\d+ causes? open|every check done))?$/)`; replace the `.ov-progress` assertions with `.ov-thread .ov-meta` (`/ · (\d+) read/`) and, once every story is read, `page.getByText("You've read every story.")`.
  - 90 ("a check's Read box is the reader's own…") becomes:

```ts
  test("stepping onto a place ticks it read for that reader alone; Looks fine marks it for everyone", async ({ page, browser }) => {
    const base = await startReview(page, FOUR);
    const id = base.split("/")[2];
    await page.getByRole("link", { name: "Next open check" }).click();
    const key = await (async () => {
      const r = await (await page.request.get(`/api/reviews/${id}/reading`)).json() as { causes: { kind: string; places: string[] }[] };
      return r.causes.filter((c) => c.kind !== "confirm")[0].places[0];
    })();
    await expect.poll(async () => (await (await page.request.get(`/api/reviews/${id}/ticks`)).json()).checks).toContain(key);
    const other = await browser.newPage();
    await login(other, "bob");
    expect((await (await other.request.get(`/api/reviews/${id}/ticks`)).json()).checks).not.toContain(key);
    await page.getByRole("button", { name: "Looks fine & next" }).click();
    await expect.poll(async () => Object.keys((await (await other.request.get(`/api/reviews/${id}/reading`)).json()).marks)).toContain(key);
    await other.close();
  });
```

  (import `login` from `./helpers`.)
  - 118 ("the overview carries the progress the header leaves out…"): the progress lives in the top bar only now; keep the Mark as read fit check, drop `.ov-progress`.
- `workspace-story.spec.ts`:
  - 11 ("Where opens a function's diff…"): replace `getByRole("tab", { name: "Steps" })` with the Flows link of "Story sections" having `aria-current="page"`; click the Where tab before its link and the Code tab before its summary.
  - 45–59: `tab "Steps"` → the Flows link of "Story sections"; `region "To check"` visible → "Story sections" visible.
  - 115 becomes "the outline's Checks ends with the checks the strong model found no hazard in": keep the route that adds the two cleared rows (drop `also: []` from `row`), go to `${base}/s/S1`, switch the outline to Checks, click `2 checks found no hazard` and expect `aside.ws-outline .ck-cleared li` to have texts `[/uart_send callers all handle -2/, /elsewhere/]`.
  - 128 and 260: on a story without a graph, "Story sections" has no "Graph" link and its first link (Flows) is current; the Call paths region shows after clicking its tab.
  - 179 ("the Steps | Graph switch and ‹ › are in place from the first paint"): for the reading's story keep the ‹ › assertions (they are in the header from the first paint) and drop the switch's; the old review (no reading) keeps the switch.
- `workspace-tier1.spec.ts`:
  - 21–24: `await expect(page.locator(".st-chip.hazard").first()).toBeVisible()`; click "Story sections" › Talk, then expect the region "Questions and comments" to contain "Does any caller retry a send after -2?" and `.st-suggested` "Check that logger_flush handles the new -2.".
  - 31–33: delete (Where to start is gone); 37: `.ov2-left .ws-lead` → `.ov3 .ws-lead`.
- `workspace-sinks.spec.ts` 33–45 and 66: the reader is a cause now: switch the outline to Checks and open `Open check: <READER without backticks>`; the shared-sink mark is the stepper's `SinkMark` button; after the re-run, expect `aside.ws-outline .ws-row.cause` with that text to have count 0, and 1 again after unmarking.
- `workspace-legacy.spec.ts` 14: `["/findings", "/i/checks"]` → `["/findings", "/i/findings"]`; 59: `region "To check"` → `getByRole("navigation", { name: "Story sections" })`.
- `long-text.spec.ts` 47 and 75: delete the `ct.ws.checkW` line; 49: drop `"/i/checks"` from the list (Task 14 adds the outline, a stepper and the story tabs).
- `ai.spec.ts` 157–… ("a story's What it does is the weak model's account…"): the purpose is `.st-summary` (AI label, the account's purpose text); each flow section is the flow card `Flow N: …` (its paragraph has the AI label); "What it means for the rest" is the region named by that heading. Keep the texts the test asserts today.
- `mention.spec.ts` 63: click "Story sections" › Talk before reading the region "Questions and comments".

- [ ] **Step 4: Run every e2e spec**

Run: `cd frontend && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test --workers=4 > /home/anoop/.claude/jobs/86383166/tmp/e2e.txt 2>&1; tail -40 /home/anoop/.claude/jobs/86383166/tmp/e2e.txt`
Expected: all pass. A `startReview` timeout under load that passes when the one spec is run again alone is the known flake; anything else is a real failure to fix.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "test(e2e): the workspace specs read the outline, the stepper and the story tabs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 14: Long names, node ids, tablet and phone; the whole suite

**Files:**
- Modify: `frontend/e2e/outline-causes.spec.ts`, `frontend/e2e/long-text.spec.ts`
- Modify (only if a check below fails): `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the tests**

Append to `frontend/e2e/outline-causes.spec.ts`:

```ts
test.describe("tablet", () => {
  test.use({ viewport: { width: 900, height: 1100 } });

  test("the outline is the drawer, with its switch", async ({ page }) => {
    await startReview(page, FOUR);
    await page.getByRole("button", { name: "Review contents" }).click();
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: /^Open check: uart_init calls hal_write/ }).click();
    await expect(page.getByRole("complementary", { name: /^Check: uart_init calls hal_write/ })).toBeVisible();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the stepper is a full-screen sheet that steps and marks; nothing scrolls sideways", async ({ page }) => {
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: /^Open check: logger_flush ignores the result/ }).click();
    const sheet = page.getByRole("complementary", { name: /^Check: logger_flush ignores the result/ });
    await expect(sheet.getByRole("region", { name: "The place" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await sheet.getByRole("button", { name: "Looks fine & next" }).click();
    await expect(sheet.locator(".cs-done")).toHaveText("Its place is done");
    await sheet.getByRole("link", { name: "Close the check" }).click();
    await expect(sheet).toHaveCount(0);
  });
});

test.describe("names, never node ids", () => {
  test.use({ baseURL: "http://127.0.0.1:8795", viewport: { width: 1440, height: 900 } });

  test("a hazard whose AI reason cites nodes reads their names in the outline, the chips and the stepper", async ({ page }) => {
    const base = await startReview(page);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expectNoNodeIds(page);
    await outline.locator(".ws-row.cause", { has: page.locator(".ck-tag.hazard") }).first().click();
    await expect(page.locator(".cs")).toBeVisible();
    await expectNoNodeIds(page);
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".st-chip.hazard").first()).toBeVisible();
    await expectNoNodeIds(page);
  });
});
```

In `frontend/e2e/long-text.spec.ts`, inside "long names stay inside their boxes on every page…", after the loop over paths, add visits of the outline's Checks, a stepper and every story tab:

```ts
  await page.goto(`${base}/s/S1`);
  const outline = page.locator("aside.ws-outline");
  await outline.getByRole("button", { name: "Checks" }).click();
  expect(await problems(page)).toEqual([]);
  await outline.locator(".ws-row.cause").first().click();
  await expect(page.locator(".cs")).toBeVisible();
  expect(await problems(page)).toEqual([]);
  const tabs = page.getByRole("navigation", { name: "Story sections" });
  for (const name of await tabs.getByRole("link").allInnerTexts()) {
    await tabs.getByRole("link", { name: name.trim() }).click();
    if (name.startsWith("Graph")) continue;                          // the graph has its own checks
    expect(await problems(page), `tab ${name}`).toEqual([]);
  }
  await outline.getByRole("button", { name: "Stories" }).click();
```

(`base` is the review address the test already holds; if it names it otherwise, use that name. `problems` also scans `.ws-detail` because it is inside `main`.)

- [ ] **Step 2: Build and run the new and long-text specs**

Run: `cd frontend && npm run build && TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/outline-causes.spec.ts e2e/long-text.spec.ts`
Expected: all pass. A failure from `problems` names the element that sticks out or is cut without a hover text: give it the one-line rule (`overflow: hidden; text-overflow: ellipsis; white-space: nowrap` plus a `title` on it or an ancestor) or let it wrap (`overflow-wrap: anywhere`), in `workspace.css`, and run again.

- [ ] **Step 3: The whole suite**

Run:

```bash
cd backend && env PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests > /home/anoop/.claude/jobs/86383166/tmp/py.txt 2>&1; tail -3 /home/anoop/.claude/jobs/86383166/tmp/py.txt
../../../backend/.venv/bin/ruff check codetortoise tests
cd ../frontend && npx vitest run && npx tsc -b --noEmit && npx eslint src e2e && npm run build
TMPDIR=/media/anoop/ssd_1/Work/CodeTortoise/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test --workers=4 > /home/anoop/.claude/jobs/86383166/tmp/e2e.txt 2>&1; tail -20 /home/anoop/.claude/jobs/86383166/tmp/e2e.txt
rm -rf /media/anoop/ssd_1/Work/CodeTortoise/.pwtmp
```

Expected: pytest all pass; ruff clean; vitest, tsc, eslint clean; Playwright all pass (re-run alone any spec that timed out in `startReview` under load before calling it a failure). If `npx eslint` is not configured for `e2e`, run `npx eslint src`.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e frontend/src/workspace/workspace.css
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "test(e2e): the outline, stepper and story tabs keep long names in their boxes and show no node ids

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```
