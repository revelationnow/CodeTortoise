# Design overview, phase 1 (rules only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1 of the design overview (spec §16): components and "Where the change sits", walk-throughs with fixed
titles (their page, drawing, outline rows, crumb links and step links) and the condition fold, all built by rules from
data the pipeline already holds, with no model call and no design context.

**Architecture:** A new pipeline stage `design` runs after `reading` and before `finalize`. It builds a `ReadingDesign`
from the reading, the story details and the analysis: `components.py` (components and the edges that cross between
them), `gates.py` (the conditions the change adds and which changed lines still run when one is false) and `walks.py`
(walk-throughs strung from the stories' call paths, change lines and flows). It stores blob `reading_design`, which
GET `/reading` serves as `design`; a failed or disabled stage stores none and the overview is today's. The frontend reads
it through pure rules (`reading/walks.ts`, `reading/design.ts`) into a new place, `/walk/W1`, and into the overview, the
outline, the story page's crumb and the Flows tab. Marks on a walk-through's steps are the flows' check marks, through the
existing routes.

**Tech Stack:** Python 3.12, Pydantic, tree-sitter 0.25 (C and C++ grammars), FastAPI, SQLite; React 19, TypeScript,
Vite, Vitest (node), Playwright 1.63.

**Spec:** `docs/superpowers/specs/2026-11-02-design-overview-design.md` (§18 holds the notes made against the code while
planning; where §1–§17 and §18 differ, §18 holds).

## Global Constraints

- Public repo: no owner's proprietary names in code, tests, docs or commits; the bundled fixture's names (`uart_send`,
  `hal_write`, `logger_init`…) are fine. No absolute local paths in committed files.
- Phase 1 is rules only (§16): no model call, no design context, no new routes. `false_case` stays "" (R17); titles
  are templates and leads empty.
- The design stage never blocks a review: off (`analysis.design: false`) or failing, it stores no `reading_design`, and
  the overview, outline and story pages are exactly as before (§9).
- No new state: a step's tick box posts that flow's check keys to the existing `/checks/marks` and `/checks/unmarks` (§4.3).
- The head's progress line ("X of N stories read · K checks open") is unchanged (§3.2, §18.6).
- Styles: app variables only, in `dz-*` classes in `workspace.css` (§12.2); unchanged arrows `--bd-muted` (§18.7).
- Each part shows only with something to show (§14): Where the change sits with two components or more, the condition
  fold with a condition, walk-throughs with call paths.
- Commits: `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`, messages ending in the
  `Co-Authored-By` and `Claude-Session` lines shown in each task. Stage files by name; never stage
  `frontend/e2e/strong-review.txt`.
- Tests: backend `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider …`
  and `.venv/bin/ruff check codetortoise tests`; frontend `npx vitest run …`, `npm run build`; e2e from `frontend/`
  after `npm run build`: `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test … --retries=0; rm -rf ../.pwtmp`.

## Review Focus

1. **A tangled `#if` or a lone `\r` in a changed file:** a condition's and a gated line's line numbers must stay the
   parser's and clang's, or the fold points at the wrong lines (Task 2's tests pin both).
2. **C++ conditions:** the C++ grammar wraps an `if`'s test in a `condition_clause`, not a `parenthesized_expression`;
   a condition in a `.cpp` or a header must be found and its test read (Task 2).
3. **Hidden check kinds:** a step whose only checks are of a hidden kind has no tick box and adds nothing to a
   walk-through's open count; showing the kind brings both back (Task 6's `stepKeys`/`walkOpen` tests).
4. **A walk-through or a step the review does not have:** `/walk/W9` says "This walk-through isn't in this review",
   and `?step=99`, `?step=0` or `?step=x` opens no row without breaking the page (Task 7's unit and e2e tests).
5. **No stale design:** a re-run that builds no reading, a disabled stage and a failing one each leave no
   `reading_design` behind, and the review still loads (Task 5's pipeline tests).

Also: nothing scrolls sideways on a phone, where the walk-through has no drawing (Task 8's phone test), and on the
overview with its new bands (the phone overview test in `workspace-reading.spec.ts`, Task 9).

## Rulings made while planning

Each is a decision the spec left open or a place where the code said otherwise; the executor holds to them and ledgers
any change.

| # | Ruling |
|---|---|
| R1 | A step's address is `?step=N` (`?at=` is the cause stepper's; §18.5). |
| R2 | Walk-throughs are listed by condition (true side before false), then by the open causes they cover, then by their story's place in the reading; numbered in that order (§18.1). |
| R3 | One walk-through per story, changed function and case. |
| R4 | `ReadingDesign.nodes` names every node a walk-through or condition cites, in the blob (`/names` doesn't). |
| R5 | The fields §18.10 adds to the §9 models. |
| R6 | A flow step's keys are `flowGroups.flowPlaces`' rule ported to Python, every kind; the browser leaves out hidden kinds. |
| R7 | A walk-through's open count is the number of distinct open causes among its steps' shown keys. |
| R8 | A walk-through crosses into another thread (and is anchored on their connection) when a step comes from that thread's story or a flow lands in a file that thread's stories change. |
| R9 | Unchanged arrows are `--bd-muted` (§18.7). |
| R10 | Which events of a changed function become change steps: its new branch, its writes on changed lines and the return it takes. |
| R11 | A step's label is capped at 60 characters. |
| R12 | A line's status: matched to a removed line at a 0.6 similarity ratio; whitespace-only edits skipped; at most 400 pairs compared. |
| R13 | Unchanged calls more than `walk_depth` from a changed function fold into one step. |
| R14 | At most 20 conditions; only the strongest (G1) lists its lines, at most 200. |
| R15 | Components: config rules first (first match wins), else the folder of the changed file, banded by `layers.py`. |
| R16 | The stage: skipped without a reading, "off" when disabled, a failure stores nothing. |
| R17 | `false_case` stays "" in phase 1; the fold says "When `test` is false". |
| R18 | No walk-throughs for mechanical or tests stories, nor for removed functions. |
| R19 | At most 4 landings and 40 steps per walk-through. |
| R20 | Conditions skip added functions and test paths. |
| R21 | Trivial lines (braces, blank, comments) are neither counted nor listed. |
| R22 | Condition kinds: a new `if`, `else if` or `case`, a changed test, a new return under a test. |
| R23 | Conditions rank by the new or changed lines they guard; ties to the earliest story. |
| R24 | Lines are classed under, outside or elsewhere, and sorted by file and line. |
| R25 | The CL that wrote a line comes from `sequence.py`'s per-line record. |
| R26 | A component's crossing sentences group edges by pair ("`a`, `b` call `c`"). |
| R27 | The outline's walk row shows its open count and "N steps · with Thread B". |
| R28 | Walk lines go under a thread's stories; a connection's link at the end of its line; `SectionLink` gains `a`/`b`. |
| R29 | State flows use writes that run; follow-on reads use marked writes. |
| R30 | The fold rule counts distance in calls from the nearest important step. |
| R31 | A contract flow's checks sit on the walk: a result row on the return, other rows on the call. |
| R32 | A changed function's own signature is a self step when the signature changed. |
| R33 | No drawing on a phone; `useRowKeys` gains `start` (and a row id `prefix`). |
| R34 | One `Sources` object reads each file once for conditions and walk-throughs. |
| R35 | `find_gates` returns `dataclasses.replace` copies, so cached shapes are never mutated. |
| R36 | A condition's test line always runs. |
| R37 | A state flow with no field isn't drawn. |
| R38 | An unwinding return's label is the callee's single distinct returned expression, else "", with that line's mark. |
| R39 | "No reading to describe" is an ok stage message (the reading already degrades the review). |
| R40 | The stage's time is measured by wrapping `build_design` in the `large` fixture (stage timestamps are seconds). |
| R41 | The `demo` fixture (CLs 101–105) belongs to Task 2. |
| R42 | `reading/design.ts` holds the overview's rules; `reading/walks.ts` the walk-throughs' (and the drawing's layout, §12.1). |
| R43 | In the drawing a write is a loop on its writer, a read a loop on its reader, a fold a dotted arrow. |
| R44 | A flow step needs no keys: without keys it has no tick box. |
| R45 | A landing unwinds to the deepest frame that reaches its reader (at most 6 hops); an unreachable reader stands alone. |
| R46 | The taken-return result rule uses only the result flow landing at the spine's caller. |
| R47 | Call events dedupe by (line, callee), writes by (line, field). |
| R48 | pytest's TMPDIR is `.superpowers/pytmp` (git-ignored), not the system `/tmp`. |
| R49 | A step's reference that names a story is a link ending in " ›" (the mockup has none): to the Call paths tab, the Code tab or the flow's row. |
| R50 | Every walk-through anchored on a thread gets a line under its stories; a connection gets one link, to its first walk-through. |
| R51 | The condition fold lists only the strongest condition's lines, as "Still runs" then "Stops". |
| R52 | A step of the code between the stories is plain text: there is no depot path to open. |
| R53 | `useMarks` is factored out of the Flows tab; the Flows tab and the walk-through page share it. |
| R54 | Where the change sits' blocks are not links: a component's stories are its threads'. |
| R55 | A quiet component stays in its layer's band, dashed. |
| R56 | A story's crumb names at most two walk-throughs, then "and N more walk-throughs". |
| R57 | The Flows tab's "▶ step N" marks flow steps only (`ref: "flow"`), not the call path leading to one. |
| R58 | A walk-through with no thread has crumbs [review, the walk-through]. |
| R59 | The e2e review with no threads also drops `design`, so its first fold still follows the change. |
| R60 | Step numbers read as runs of three or more ("1–5, 8"); a pair stays a list ("2, 3"). |

## File map

| File | Task | What |
|---|---|---|
| `backend/codetortoise/config.py` | 1 | `ComponentRule`; `AnalysisConfig.components`, `walk_depth`, `max_walks`, `design` |
| `backend/codetortoise/design.py` | 1, 5 | the models (§9 + §18.10); `build_design`, `design_nodes` |
| `backend/codetortoise/gates.py` | 2 | conditions, the lines they guard, the shared `Sources` |
| `backend/codetortoise/components.py` | 3 | components, bands and crossing edges |
| `backend/codetortoise/walks.py` | 4 | candidates, joining, folding and keeping walk-throughs |
| `backend/codetortoise/pipeline.py` | 5 | the `design` stage and blob `reading_design` |
| `backend/codetortoise/web/app.py` | 5 | `/reading` serves `design` |
| `backend/tests/conftest.py` | 2 | `_analyse`, the session fixture `demo` |
| `backend/tests/test_design.py`, `test_gates.py`, `test_components.py`, `test_walks.py` | 1–5 | unit tests |
| `backend/tests/test_pipeline.py`, `test_web.py`, `test_large_change.py` | 5 | the stage, the route, the time |
| `README.md` | 1, 11 | the `analysis:` keys; the overview's account |
| `frontend/src/reading/types.ts` | 6 | the design types; `Reading.design` |
| `frontend/src/reading/walks.ts` (+ test) | 6, 8 | walk-through rules; the drawing's layout |
| `frontend/src/reading/design.ts` (+ test) | 6 | Where the change sits' and the condition fold's rules |
| `frontend/src/workspace/address.ts`, `memory.ts`, `crumbs.ts` (+ tests) | 7 | the place `/walk/W1`, `?step=N`, its crumbs |
| `frontend/src/workspace/useMarks.ts` | 7 | marks, shared by the Flows tab and the walk-through |
| `frontend/src/workspace/useRowKeys.ts`, `FlowsTab.tsx` | 7, 10 | `start`/`prefix`; the Flows row's step |
| `frontend/src/workspace/WalkPage.tsx` | 7, 8 | the walk-through's page |
| `frontend/src/workspace/WalkDrawing.tsx` | 8 | the sequence drawing |
| `frontend/src/workspace/Workspace.tsx` | 7, 10 | routing the place; the walk's thread |
| `frontend/src/reading/overview.ts` (+ test), `workspace/Overview.tsx` | 9 | Where the change sits, walk lines and links, the condition fold |
| `frontend/src/workspace/Outline.tsx`, `StoryPage.tsx` | 10 | the outline's walk rows; the story's crumb |
| `frontend/src/workspace/workspace.css` | 7–10 | `dz-*` styles |
| `frontend/e2e/walk-throughs.spec.ts` | 7–10 | the walk-throughs end to end |
| `frontend/e2e/helpers.ts` and five specs | 9 | `openFold`'s new name; the overview's new rows in exact lists |

---

### Task 1: Config keys, the design models and the README

**Files:**
- Modify: `backend/codetortoise/config.py` (after `TargetRule`, and the end of `AnalysisConfig`)
- Create: `backend/codetortoise/design.py`
- Modify: `README.md` (the `analysis:` block of the config example)
- Test: `backend/tests/test_design.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `config.ComponentRule(name: str, globs: list[str])`; `AnalysisConfig.components: list[ComponentRule] = []`,
    `walk_depth: int = 2`, `max_walks: int = 6`, `design: bool = True`.
  - `design.py` models: `DesignNode`, `WalkStep`, `Walk`, `Component`, `Concern`, `Ownership`, `GatedLine`, `Gate`,
    `ReadingDesign` exactly as below (spec §9 plus §18.10). Later tasks build them; the frontend types mirror them.

- [ ] **Step 1: Write the failing test**

```python
# path: backend/tests/test_design.py
"""The design overview's models and builder (spec 2026-11-02 §9, §18.10)."""
from codetortoise.config import AnalysisConfig, ComponentRule
from codetortoise.design import ReadingDesign, Walk, WalkStep


def test_the_design_keys_default_to_layers_two_calls_six_walks_and_on():
    a = AnalysisConfig()
    assert (a.components, a.walk_depth, a.max_walks, a.design) == ([], 2, 6, True)
    b = AnalysisConfig.model_validate({"components": [{"name": "HAL", "globs": ["hal/**", "include/hal/**"]}],
                                       "walk_depth": 1, "max_walks": 2, "design": False})
    assert b.components == [ComponentRule(name="HAL", globs=["hal/**", "include/hal/**"])]
    assert (b.walk_depth, b.max_walks, b.design) == (1, 2, False)


def test_a_reading_design_survives_its_json_round_trip():
    step = WalkStep(kind="return", src="N10", dst="N3", label="-2", status="new", ref="flow", story="S1", flow="FL1",
                    flow_n=1, keys=["result|service/logger.c|logger_flush|uart_send"], path="driver/uart.c", line=18)
    d = ReadingDesign(walks=[Walk(id="W1", title="When `len > 64`", connection=("T1", "T2"), condition="G1", case=True,
                                  parts=["N7", "N3", "N10"], stories=["S1"], steps=[step])])
    back = ReadingDesign.model_validate(d.model_dump(mode="json"))
    assert back == d and back.walks[0].connection == ("T1", "T2")
    assert ReadingDesign().model_dump()["walks"] == [] and ReadingDesign().nodes == {}
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd backend && mkdir -p ../.superpowers/pytmp && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design.py`
Expected: FAIL at collection: `ImportError: cannot import name 'ComponentRule' from 'codetortoise.config'`.

- [ ] **Step 3: Add the config keys**

In `backend/codetortoise/config.py`, after `class TargetRule` (its two fields), add:

```python
class ComponentRule(BaseModel):
    """A component of the design overview (spec 2026-11-02 §13): a name and the files it holds."""
    name: str
    globs: list[str]                 # fnmatch on workspace-relative paths, as TargetRule.match; the first rule a file
                                     # matches names its component
```

In `class AnalysisConfig`, after `sink_fields: list[str] = Field(default_factory=list)   # fnmatch patterns …` and
before `_own_sinks`, add:

```python
    components: list[ComponentRule] = Field(default_factory=list)   # the design overview's components; empty: the
                                                                     # modules layers.py finds (spec 2026-11-02 §5)
    walk_depth: int = 2             # unchanged calls a walk-through keeps either side of a changed function (§4.2)
    max_walks: int = 6              # walk-throughs per review (§4.2)
    design: bool = True             # false: no design stage, the overview as before it (§13)
```

- [ ] **Step 4: Create the models**

```python
# path: backend/codetortoise/design.py
"""A review's design overview (spec 2026-11-02): where the change sits, its walk-throughs and its conditions.

The `design` stage builds it from the reading, by rules only in phase 1 (§16). It is stored as blob `reading_design` and
served inside GET /reading as `design`. The models are spec §9's with the fields §18.10 adds, each commented."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DesignNode(BaseModel):
    """A node the design cites. /names only names the nodes on boards and stories, so the design names its own (§18.8)."""
    label: str
    kind: Literal["function", "field"] = "function"
    component: str | None = None
    path: str = ""                    # workspace-relative: a function's file, a field's record header
    line: int | None = None           # a function's first line (after side), a field's declaration


class WalkStep(BaseModel):
    kind: Literal["call", "return", "self", "write", "read", "fold"]
    src: str                          # node id
    dst: str                          # node id; == src for "self"
    label: str                        # from the code: the call, the returned value, the assignment
    status: Literal["new", "changed", "same"]
    ref: Literal["path", "change", "flow", "code"] = "code"    # what it comes from (§18.10): a story's call path, its
                                      # changed lines, a flow's landing, or unchanged code
    story: str | None = None          # S1
    flow: str | None = None           # a flow id of that story
    flow_n: int | None = None         # that flow's 1-based place in the story's Flows tab (its `?flow=N`)
    cause: str | None = None          # the cause of its first key
    keys: list[str] = Field(default_factory=list)   # a flow step's check keys: what "Looks fine" on it marks
    edge: str | None = None           # impact edge id, for a call between two functions
    loop: str | None = None           # the loop this step sits in, as written: "for (i = 0; i < len; i++)"
    path: str = ""                    # where its code is, workspace-relative
    line: int | None = None
    cl: int | None = None             # the CL that wrote that line, for a new or changed one
    folded: int = 0                   # a "fold" step: how many steps it stands for


class Walk(BaseModel):
    id: str                           # W1; cited, never shown
    title: str
    title_source: Literal["template", "llm"] = "template"
    lead: str = ""
    thread: str | None = None         # anchored on a thread …
    connection: tuple[str, str] | None = None   # … or on the connection between two
    condition: str | None = None      # the gate id, when this is one side of it
    case: bool | None = None          # which side of it: true, false; None without a condition (§18.10)
    parts: list[str]                  # function node ids, left to right
    stories: list[str] = Field(default_factory=list)   # the stories its steps come from, in order (§18.10)
    steps: list[WalkStep]


class Component(BaseModel):
    name: str
    level: int | None                 # layers.py level: the highest of its changed files'
    band: str = ""                    # the band it sits in: its layer's name, "other" without one
    globs: list[str] = Field(default_factory=list)
    threads: list[str] = Field(default_factory=list)   # the threads whose stories change it
    stories: list[str] = Field(default_factory=list)   # those stories, in reading order
    files: list[str] = Field(default_factory=list)     # its changed files, workspace-relative
    crossing: list[str] = Field(default_factory=list)  # sentences from the impact edges that cross into or out of it
    quiet: bool = False               # shares no edge with the rest


class Concern(BaseModel):            # phase 2 (§6.1)
    text: str
    how: str
    stories: list[str]
    assessment: Literal["right", "note", "confirm", "ask"]
    note: str = ""
    causes: list[str] = Field(default_factory=list)


class Ownership(BaseModel):          # phase 2 (§6.2)
    tag: Literal["right", "questionable", "shortfall", "note"]
    text: str
    cites: list[str]                  # node ids, paths or story ids


class GatedLine(BaseModel):
    story: str | None = None          # none for a line no story holds, such as a header's (§18.10)
    cl: int | None = None
    text: str
    runs: bool                        # when the condition is false
    where: Literal["under", "outside", "elsewhere"] = "elsewhere"
    path: str = ""                    # workspace-relative
    line: int | None = None
    function: str | None = None       # the function holding it, by label


class Gate(BaseModel):
    id: str
    node: str                         # the function holding it
    test: str                         # "len > 64"
    false_case: str = ""              # the model names it in phase 2; until then the fold says "When `test` is false"
    lines: list[GatedLine] = Field(default_factory=list)   # the strongest condition's only (§7)
    source: Literal["code", "context"] = "code"
    story: str | None = None
    path: str = ""
    line: int | None = None           # the test's line
    guarded: list[int] = Field(default_factory=list)       # [first, last] line of the block it guards
    runs: int = 0                     # changed lines that still run when it is false
    stops: int = 0                    # changed lines that don't


class ReadingDesign(BaseModel):
    verdict: str = ""
    verdict_causes: list[str] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    concerns: list[Concern] = Field(default_factory=list)
    ownership: list[Ownership] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)
    walks: list[Walk] = Field(default_factory=list)
    nodes: dict[str, DesignNode] = Field(default_factory=dict)
    sources: dict[str, Literal["template", "llm", "pinned"]] = Field(default_factory=dict)   # per part
    context_hash: str | None = None
```

- [ ] **Step 5: Document the keys**

In `README.md`, in the config example's `analysis:` block, after the `sink_fields:` line, add:

```yaml
  components:                       # the overview's "Where the change sits" blocks; first match names a file's
    - { name: Driver, globs: ["driver/**"] }   #   (fnmatch on workspace-relative paths; empty: layers.py's modules)
    - { name: HAL, globs: ["hal/**", "include/hal/**"] }
  walk_depth: 2                     # unchanged calls a walk-through shows either side of a changed function
  max_walks: 6                      # walk-throughs per review
  design: true                      # false: no design overview (no walk-throughs, no condition fold)
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design.py tests/test_config.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/design.py backend/tests/test_design.py README.md
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the design overview's config keys and models

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 2: gates.py — conditions and the lines that still run

**Files:**
- Create: `backend/codetortoise/gates.py`
- Modify: `backend/tests/conftest.py` (factor `_analyse`; add the session fixture `demo`)
- Test: `backend/tests/test_gates.py`

**Interfaces:**
- Consumes: `design.Gate`, `design.GatedLine` (Task 1); `board._Ctx` attributes `fa`, `fb`, `im`, `id_of`, `changed`,
  `texts`, `calls_after`, `label`, `is_test_path`, `c.cs`; `reading.rel_path`; `cparse._parser_for`, `_txt`,
  `_line_starts`, `_at`, `_COND`, `flatten_preproc`, `norm_ws`; `linediff.lines`, `linediff.opcodes`.
- Produces (walks.py and design.py use these):
  - `trivial(text) -> bool`; `line_marks(before, after) -> dict[int, "new" | "changed"]`.
  - dataclasses `Loop(text, first, last)`, `Branch(node, path, line, test, first, last, body, own, returns, alt, kind,
    strength, id)`, `FnShape(node, path, first, last, branches, loops, returns: list[(line, expr)])`.
  - `class Sources(x, read_text=None)` with `text(path, side="after")`, `rows(path)`, `line(path, n)`,
    `marks(path)`, `tree(path, side="after") -> (tree, src bytes, starts)`, `nodes_at(path, line, type)`,
    `shape(nid, side="after") -> FnShape | None`.
  - `node_stories(ss) -> {nid: sid}`; `line_cl(x, path, n, lines=None) -> int | None`.
  - `find_gates(x, src, story_of, order) -> list[Branch]` (copies, ranked); `classify(g, x, src, story_of, path_story,
    order, lines=None) -> (list[GatedLine], runs, stops)`; `build_gates(x, ss, r, per, src, lines=None) ->
    (list[Gate], list[Branch])` (the Branch list carries `id` `G1…`, in rank order, at most `MAX_GATES`).
  - conftest session fixture `demo`: `SimpleNamespace(c, a, x, ss, det, r, per, lines, read_text, src)` for CLs
    101–105.

- [ ] **Step 1: Add the demo fixture**

In `backend/tests/conftest.py`, replace the body of `analysed` with a call to a factored helper, and add `demo`:

```python
def _analyse(fx, fx_source, tmp, cls):
    """The given CLs run through diffmap, TU selection, clang facts and the impact model."""
    cfg = AnalysisConfig(module_min_files=1)
    cs = fx_source.load(cls)
    dm = map_changes(cs)
    idx = SymbolIndex(tmp / "s.db")
    idx.build(fx.root)
    cdb = CompileDb.load(fx.compile_commands)
    tc = Toolchain(ToolchainConfig(), cdb, tmp / "tc")
    tc.prepare()
    sel = select_tus(dm, idx, cdb, cfg)
    layers = infer_layers(idx, str(fx.root), 1)
    before = run_extraction(build_requests(sel, cs, tc, "before"), None, 1)
    after = run_extraction(build_requests(sel, cs, tc, "after"), None, 1)
    im = build_impact(before, after, cs, sel, idx, layers, cfg)
    return SimpleNamespace(cfg=cfg, cs=cs, dm=dm, sel=sel, layers=layers, before=before, after=after, impact=im)


@pytest.fixture(scope="session")
def analysed(fx, fx_source, tmp_path_factory):
    """CLs 101+102 run through diffmap, TU selection, clang facts and the impact model."""
    return _analyse(fx, fx_source, tmp_path_factory.mktemp("impact"), [101, 102])


def _disk(path: str) -> str | None:
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return None


@pytest.fixture(scope="session")
def demo(fx, fx_source, tmp_path_factory):
    """CLs 101–105, the design overview's demo (spec 2026-11-02): the reading and what the design stage builds on."""
    from codetortoise.board import BoardContext, analyse
    from codetortoise.detectors.base import DetectorContext, run_detectors
    from codetortoise.gates import Sources
    from codetortoise.paths import canon
    from codetortoise.reading import build_reading
    from codetortoise.sequence import file_lines
    from codetortoise.stories import build_stories
    a = _analyse(fx, fx_source, tmp_path_factory.mktemp("demo"), [101, 102, 103, 104, 105])
    findings = run_detectors(DetectorContext(a.before, a.after, a.dm, a.impact, a.cfg))
    c = BoardContext(a.cs, a.dm, a.before, a.after, a.impact, findings, a.layers, a.cfg, fx_source.depots_for,
                     root=canon(str(fx.root)))
    an = analyse(c)
    ss, det = build_stories(c, analysis=an)
    lines = file_lines(a.cs)
    r, per = build_reading(ss, c, details=det, analysis=an, read_text=_disk, lines=lines)
    return SimpleNamespace(c=c, a=an, x=an.x, ss=ss, det=det, r=r, per=per, lines=lines, read_text=_disk,
                           src=Sources(an.x, _disk))
```

Add `from pathlib import Path` to the imports at the top of conftest.py.

- [ ] **Step 2: Write the failing tests**

```python
# path: backend/tests/test_gates.py
"""The conditions a change adds and the lines that still run when one is false (spec 2026-11-02 §7)."""
from test_stories import _world

from codetortoise.board import _Ctx
from codetortoise.gates import Sources, build_gates, classify, find_gates, line_marks, trivial


def _found(c):
    x = _Ctx(c)
    return x, find_gates(x, Sources(x), {}, [])


def _gate(b):
    return (b.kind, b.test, b.line, sorted(b.body))


def test_line_marks_tell_new_lines_from_changed_ones_and_skip_whitespace_edits():
    before = "x = 1;\nif (len > 32) {\n\tsend();\n}\n"
    after = "x  =  1;\nif (len > 64) {\n\tsend();\n}\ndone();\n"
    assert line_marks(before, after) == {2: "changed", 5: "new"}


def test_a_line_of_braces_or_a_comment_says_nothing_alone():
    assert all(trivial(t) for t in ["}", "\t{", "  );", "", "// note", " * more", "/* x */"])
    assert not any(trivial(t) for t in ["\t} else {", "break;", "x++;"])


def test_a_new_if_with_an_early_return_outranks_a_changed_condition():
    c = _world([("check", "drv/u.c", ["if (len > 32) {", "\tgo();", "}"], ["if (len > 64) {", "\tgo();", "}"]),
                ("send", "drv/u.c", ["x = 1;", "go();"],
                 ["x = 1;", "if (len > 64) {", "\terr++;", "\treturn -2;", "}", "go();"]),
                ("go", "drv/u.c", ["y = 1;"], ["y = 1;"])])
    x, found = _found(c)
    assert [(x.label(b.node), b.kind, b.test, b.strength) for b in found] == [
        ("send", "if", "len > 64", 2), ("check", "changed", "len > 64", 0)]
    send = found[0]
    assert (send.line, send.first, send.last, sorted(send.body), sorted(send.own), send.returns) == (
        10, 10, 13, [11, 12], [10, 13], [12])


def test_a_new_else_if_is_a_condition_of_its_own_and_a_plain_else_its_other_side():
    c = _world([("pick", "drv/p.c", ["if (m == 1) {", "\ta();", "} else {", "\tc();", "}"],
                 ["if (m == 1) {", "\ta();", "} else if (m == 2) {", "\tb();", "} else {", "\tc();", "}"])])
    x, found = _found(c)
    assert [_gate(b) for b in found] == [("else if", "m == 2", 5, [6])]
    assert found[0].alt == (7, 9)


def test_a_new_case_is_a_condition_on_the_switch_subject():
    c = _world([("on", "drv/s.c", ["switch (m) {", "case 1:", "\ta();", "\tbreak;", "}"],
                 ["switch (m) {", "case 1:", "\ta();", "\tbreak;", "case 2:", "\tb();", "\tbreak;", "}"])])
    x, found = _found(c)
    assert [_gate(b) for b in found] == [("case", "m == 2", 7, [8, 9])]


def test_a_new_return_under_an_existing_condition_makes_it_one():
    c = _world([("use", "drv/r.c", ["if (!p) {", "\tlog();", "}", "go(p);"],
                 ["if (!p) {", "\tlog();", "\treturn;", "}", "go(p);"])])
    x, found = _found(c)
    assert [(b.kind, b.test, b.line, b.returns) for b in found] == [("return", "!p", 3, [5])]


def test_a_cpp_file_reads_its_condition_from_the_condition_clause():
    c = _world([("send", "drv/u.cpp", ["go();"], ["if (len > 64) {", "\treturn;", "}", "go();"])])
    x, found = _found(c)
    assert [(b.kind, b.test) for b in found] == [("if", "len > 64")]


def test_a_condition_tangled_in_an_ifdef_is_found_on_the_branch_the_parse_keeps():
    c = _world([("send", "drv/t.c", ["go();"],
                 ["#ifdef FAST", "if (n > 1) {", "#else", "if (n > 2) {", "#endif", "\tgo();", "}"])])
    x, found = _found(c)
    assert [(b.test, b.line, sorted(b.body)) for b in found] == [("n > 1", 4, [8])]


def test_lines_count_a_lone_carriage_return_as_clang_does():
    c = _world([("send", "drv/cr.c", ["x = 1; // a\r// b", "go();"],
                 ["x = 1; // a\r// b", "if (len > 64) {", "\treturn;", "}", "go();"])])
    x, found = _found(c)
    assert [(b.test, b.line, sorted(b.body)) for b in found] == [("len > 64", 5, [6])]


def test_an_added_function_has_no_condition_to_meet():
    c = _world([("fresh", "drv/n.c", None, ["if (x) {", "\treturn;", "}"])])
    assert _found(c)[1] == []


def test_a_function_called_only_under_the_condition_stops_with_it_and_one_called_elsewhere_runs():
    c = _world([("send", "drv/u.c", ["both();"], ["if (len > 64) {", "\tonly();", "\treturn -2;", "}", "both();"]),
                ("only", "drv/u.c", ["a = 1;"], ["a = 2;"]),
                ("both", "drv/u.c", ["b = 1;"], ["b = 2;"]),
                ("other", "drv/u.c", ["both();"], ["both();"])],
               calls=[("send", "only"), ("send", "both"), ("other", "both")])
    c.after[0].calls[0].line, c.after[0].calls[1].line = 4, 7          # inside the new block, and after it
    x, found = _found(c)
    lines, runs, stops = classify(found[0], x, Sources(x), {}, {}, [])
    assert [(g.where, g.function, g.line, g.runs) for g in lines] == [
        ("under", "send", 4, False), ("under", "send", 5, False), ("elsewhere", "only", 11, False),
        ("elsewhere", "both", 15, True)]
    assert (runs, stops) == (1, 3)


def test_the_demo_has_one_condition_and_its_false_case_still_runs_the_other_changes(demo):
    gates, branches = build_gates(demo.x, demo.ss, demo.r, demo.per, demo.src, demo.lines)
    assert [(g.id, demo.x.label(g.node), g.test, g.story, g.path, g.line, g.guarded) for g in gates] == [
        ("G1", "uart_send", "len > 64", "S1", "driver/uart.c", 16, [16, 19])]
    assert [b.id for b in branches] == ["G1"]
    g = gates[0]
    assert [(k.path, k.line) for k in g.lines if k.where == "under"] == [("driver/uart.c", 17), ("driver/uart.c", 18)]
    assert [(k.line, k.runs) for k in g.lines if k.where == "outside"] == [(14, True), (15, True), (20, True), (22, True)]
    elsewhere = {(k.path, k.line): k.runs for k in g.lines if k.where == "elsewhere"}
    assert {("hal/regs.c", 10), ("service/logger.c", 7), ("cpp/engine.cpp", 21)} <= set(elsewhere)
    assert all(elsewhere.values())
    tx = next(k for k in g.lines if (k.path, k.line) == ("driver/uart.c", 22))
    assert (tx.story, tx.cl, tx.text, tx.function) == ("S1", 101, "st->tx++;", "uart_send")
    assert (g.stops, g.runs) == (2, len(g.lines) - 2)
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gates.py`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'codetortoise.gates'`.

- [ ] **Step 4: Write gates.py**

```python
# path: backend/codetortoise/gates.py
"""The conditions a change adds, and which of its changed lines still run when one is false (spec 2026-11-02 §7).

Rules only. A tree-sitter walk of each changed function, after and before, finds its ifs, else-ifs, cases, loops and
returns; `line_marks` finds its new and changed lines. `Sources` reads, parses and diffs each file once, for the
conditions here and the walk-throughs (walks.py) alike. Lines are numbered as clang numbers them (`linediff.lines`)."""
from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from codetortoise import linediff
from codetortoise.cparse import _COND, _at, _line_starts, _parser_for, _txt, flatten_preproc, norm_ws
from codetortoise.design import Gate, GatedLine
from codetortoise.reading import rel_path

MAX_GATES = 20            # conditions kept per review (§14)
MAX_LINES = 200           # lines the strongest condition lists
SIMILAR = 0.6             # an added line this like one its block replaced is "changed", not "new"
PAIRS = 400               # a replaced block bigger than this (old lines × new lines) is all "changed", unpaired
_TRIVIAL = re.compile(r"[{}();,\s]*")
_LOOPS = {"for_statement", "while_statement", "do_statement", "for_range_loop"}
_INDEXED = ("call_expression", "field_expression")


def trivial(text: str) -> bool:
    """A line that says nothing alone: braces and punctuation, a blank, a comment."""
    t = text.strip()
    return bool(_TRIVIAL.fullmatch(t)) or t.startswith(("//", "/*", "*"))


def line_marks(before: str, after: str) -> dict[int, str]:
    """The after side's added lines (1-based), each "new" or "changed": changed when it is at least SIMILAR to a line
    its block replaced (R12). A line whose text, whitespace folded, is one its block removed is a whitespace edit."""
    a, b = linediff.lines(before), linediff.lines(after)
    out: dict[int, str] = {}
    for tag, i1, i2, j1, j2 in linediff.opcodes(before, after):
        if tag not in ("insert", "replace"):
            continue
        old = [norm_ws(t) for t in a[i1:i2]]
        same, big = set(old), len(old) * (j2 - j1) > PAIRS
        for j in range(j1, j2):
            t = norm_ws(b[j])
            if t in same:
                continue
            like = big or any(difflib.SequenceMatcher(None, o, t, autojunk=False).ratio() >= SIMILAR for o in old)
            out[j + 1] = "changed" if old and like else "new"
    return out


@dataclass
class Loop:
    text: str                         # its header as written: "for (i = 0; i < len; i++)"
    first: int
    last: int


@dataclass
class Branch:
    """One if, else if or case of a function and what it guards."""
    node: str                         # the function's node id
    path: str                         # its file (canonical)
    line: int                         # the test's line
    test: str                         # the test, whitespace folded
    first: int                        # the guarded block's first and last line
    last: int
    body: set[int]                    # the lines its statements take up
    own: set[int]                     # the test's lines and the block's braces, statements left out
    returns: list[int] = field(default_factory=list)      # return lines in the body
    alt: tuple[int, int] | None = None                    # a plain else's lines (an else-if is a branch of its own)
    kind: str = "if"                  # if | else if | case; as a gate also changed (its test) or return (a new one)
    strength: int = 0                 # new or changed lines it guards
    id: str = ""


@dataclass
class FnShape:
    node: str
    path: str
    first: int
    last: int
    branches: list[Branch]
    loops: list[Loop]
    returns: list[tuple[int, str]]    # (line, the returned expression as written; "" for a bare return)


def _cond_text(src: bytes, cond) -> str:
    """An if's or switch's test: inside its parentheses (C) or its condition_clause's value (C++)."""
    if cond is None:
        return ""
    inner = cond
    if cond.type == "condition_clause":
        inner = cond.child_by_field_name("value") or next((c for c in cond.named_children if c.type != "comment"), None)
    elif cond.type == "parenthesized_expression":
        inner = next((c for c in cond.named_children if c.type != "comment"), None)
    return norm_ws(_txt(src, inner))


def _stmts(node) -> list:
    if node is None:
        return []
    if node.type == "compound_statement":
        return [c for c in node.named_children if c.type != "comment"]
    return [node]


def _span(ln, nodes) -> set[int]:
    out: set[int] = set()
    for n in nodes:
        out.update(range(ln(n.start_point), ln(n.end_point) + 1))
    return out


def _if_branch(node, src: bytes, ln, nid: str, path: str) -> Branch | None:
    cond, cons = node.child_by_field_name("condition"), node.child_by_field_name("consequence")
    if cond is None or cons is None:
        return None
    body = _span(ln, _stmts(cons))
    own = (set(range(ln(node.start_point), ln(cond.end_point) + 1)) | {ln(cons.start_point), ln(cons.end_point)}) - body
    alt = None
    other = node.child_by_field_name("alternative")
    if other is not None:
        inner = next((c for c in other.named_children if c.type != "comment"), None)
        if inner is not None and inner.type != "if_statement":
            alt = (ln(other.start_point), ln(other.end_point))
    kind = "else if" if node.parent is not None and node.parent.type == "else_clause" else "if"
    return Branch(nid, path, ln(node.start_point), _cond_text(src, cond), ln(cons.start_point), ln(cons.end_point),
                  body, own, alt=alt, kind=kind)


def _case_branch(node, src: bytes, ln, nid: str, path: str) -> Branch | None:
    value = node.child_by_field_name("value")
    if value is None:                                      # default: no condition of its own
        return None
    sw = node.parent.parent if node.parent is not None else None
    subject = _cond_text(src, sw.child_by_field_name("condition")) if sw is not None and sw.type == "switch_statement" else ""
    v = norm_ws(_txt(src, value))
    body = _span(ln, [c for c in node.named_children if c.id != value.id and c.type != "comment"])
    line = ln(node.start_point)
    return Branch(nid, path, line, f"{subject} == {v}" if subject else v, line, ln(node.end_point), body, {line} - body,
                  kind="case")


def _loop_text(node, src: bytes) -> str:
    """A loop's header as written: `for (i = 0; i < len; i++)`, `while (n)`, `do … while (n)`."""
    if node.type == "do_statement":
        return f"do … while {norm_ws(_txt(src, node.child_by_field_name('condition')))}"
    body = node.child_by_field_name("body")
    return norm_ws(src[node.start_byte:body.start_byte if body is not None else node.end_byte].decode("utf-8", "replace"))


class Sources:
    """Each file's text, parse and changed lines, read once and shared by the conditions and the walk-throughs (R34). A
    changed file's text is the change set's; any other file's is read with `read_text`, the same on both sides."""

    def __init__(self, x, read_text: Callable[[str], str | None] | None = None):
        self.x = x
        self.read_text = read_text
        self._text: dict[tuple[str, str], str] = {}
        self._rows: dict[str, list[str]] = {}
        self._marks: dict[str, dict[int, str]] = {}
        self._trees: dict[tuple[str, str], tuple] = {}
        self._index: dict[str, dict[str, dict[int, list]]] = {}
        self._shapes: dict[tuple[str, str], FnShape | None] = {}

    def text(self, path: str, side: str = "after") -> str:
        key = (path, side)
        if key not in self._text:
            fc = self.x.texts.get(path)
            if fc is not None:
                self._text[key] = fc.after if side == "after" else fc.before
            else:
                self._text[key] = (self.read_text(path) if self.read_text else None) or ""
        return self._text[key]

    def rows(self, path: str) -> list[str]:
        if path not in self._rows:
            self._rows[path] = linediff.lines(self.text(path))
        return self._rows[path]

    def line(self, path: str, n: int) -> str:
        rows = self.rows(path)
        return rows[n - 1] if 0 < n <= len(rows) else ""

    def marks(self, path: str) -> dict[int, str]:
        """The file's new and changed lines; none for a file the change leaves alone."""
        if path not in self._marks:
            fc = self.x.texts.get(path)
            self._marks[path] = line_marks(fc.before, fc.after) if fc is not None else {}
        return self._marks[path]

    def tree(self, path: str, side: str = "after") -> tuple:
        """(tree, source bytes, row starts). A parse an `#if` tangles is redone on `flatten_preproc`'s text, which keeps
        every kept line's number and bytes."""
        key = (path, side)
        if key not in self._trees:
            text = self.text(path, side)
            parser = _parser_for(path)
            src = text.encode("utf-8", errors="replace")
            tree = parser.parse(src)
            if tree.root_node.has_error and any(_COND.match(t) for t in text.split("\n")):
                src = flatten_preproc(text).encode("utf-8", errors="replace")
                tree = parser.parse(src)
            self._trees[key] = (tree, src, _line_starts(text))
        return self._trees[key]

    def nodes_at(self, path: str, line: int, kind: str) -> list:
        """The after side's calls or field accesses that start on a line."""
        if path not in self._index:
            tree, _, starts = self.tree(path)
            idx: dict[str, dict[int, list]] = {k: {} for k in _INDEXED}
            stack = [tree.root_node]
            while stack:
                n = stack.pop()
                if n.type in idx:
                    idx[n.type].setdefault(_at(starts, n.start_point[0] + 1), []).append(n)
                stack.extend(n.children)
            for by in idx.values():
                for ns in by.values():
                    ns.sort(key=lambda n: n.start_byte)
            self._index[path] = idx
        return self._index[path].get(kind, {}).get(line, [])

    def shape(self, nid: str, side: str = "after") -> FnShape | None:
        key = (nid, side)
        if key not in self._shapes:
            self._shapes[key] = self._shape(nid, side)
        return self._shapes[key]

    def _shape(self, nid: str, side: str) -> FnShape | None:
        n = self.x.im.nodes[nid]
        fn = (self.x.fa if side == "after" else self.x.fb).get(n.key)
        if fn is None:
            return None
        tree, src, starts = self.tree(fn.file, side)

        def ln(p) -> int:
            return _at(starts, p[0] + 1)
        out = FnShape(nid, fn.file, fn.start_line, fn.end_line, [], [], [])
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if ln(node.end_point) < fn.start_line or ln(node.start_point) > fn.end_line:
                continue
            t = node.type
            b = None
            if t == "if_statement":
                b = _if_branch(node, src, ln, nid, fn.file)
            elif t == "case_statement":
                b = _case_branch(node, src, ln, nid, fn.file)
            elif t in _LOOPS:
                out.loops.append(Loop(_loop_text(node, src), ln(node.start_point), ln(node.end_point)))
            elif t == "return_statement":
                val = next((c for c in node.named_children if c.type != "comment"), None)
                out.returns.append((ln(node.start_point), norm_ws(_txt(src, val))))
            if b is not None:
                out.branches.append(b)
            stack.extend(node.children)
        out.branches.sort(key=lambda b: (b.line, b.first))
        out.loops.sort(key=lambda lp: (lp.first, -lp.last))
        out.returns.sort()
        for b in out.branches:
            b.returns = [r for r, _ in out.returns if r in b.body]
        return out


def node_stories(ss) -> dict[str, str]:
    """Each changed node's story: the first that holds it."""
    out: dict[str, str] = {}
    for s in ss.stories:
        for n in s.nodes:
            out.setdefault(n, s.id)
    return out


def line_cl(x, path: str, n: int, lines=None) -> int | None:
    """The CL that wrote line n of a changed file's final text (R25): sequence.py's per-line record for a file several
    CLs edit, else the file's one CL."""
    fc = x.texts.get(path)
    if fc is None:
        return None
    fl = (lines or {}).get(fc.depot)
    if fl is not None and 0 < n <= len(fl.wrote):
        return fl.wrote[n - 1]
    if len(fc.per_cl) == 1:
        return fc.per_cl[0].cl
    if not fc.per_cl and x.c.cs.cls:
        return x.c.cs.cls[0].cl
    return None


def find_gates(x, src: Sources, story_of: dict[str, str], order: list[str]) -> list[Branch]:
    """The conditions the change adds (§7, R20–R23): a new if, else if or case; a changed test; a new return under an
    existing one. Only functions that existed before, outside tests. Strongest first: the most new or changed lines it
    guards, then the earliest story, file and line."""
    pos = {s: i for i, s in enumerate(order)}
    out: list[Branch] = []
    for nid in sorted(x.changed, key=lambda n: (len(n), n)):
        n = x.im.nodes[nid]
        if n.kind != "function" or n.key not in x.fa or n.key not in x.fb or x.is_test_path(nid):
            continue
        after = src.shape(nid)
        if after is None:
            continue
        before = src.shape(nid, "before")
        had = {b.test for b in before.branches} if before is not None else set()
        marks = src.marks(after.path)
        for b in after.branches:
            strength = sum(1 for k in b.body if k in marks and not trivial(src.line(after.path, k)))
            if b.line in marks and b.test not in had:
                kind = "changed" if marks[b.line] == "changed" else b.kind
            elif any(r in marks for r in b.returns):
                kind = "return"
            else:
                continue
            out.append(replace(b, kind=kind, strength=strength))
    out.sort(key=lambda b: (-b.strength, pos.get(story_of.get(b.node, ""), len(pos)), b.path, b.line))
    return out


def _only_guarded(x, g: Branch) -> set[str]:
    """Functions reached only through the guarded block: every call to them sits in its body, or in a function already
    reached only through it."""
    usr = x.im.nodes[g.node].key
    sites: dict[str, list] = {}
    for e in x.calls_after:
        sites.setdefault(e.callee, []).append(e)
    inside: set[str] = set()
    grew = True
    while grew:
        grew = False
        for callee, es in sites.items():
            if callee in inside or callee == usr:
                continue
            if all((e.caller == usr and e.line in g.body) or e.caller in inside for e in es):
                inside.add(callee)
                grew = True
    return {x.id_of[k] for k in inside if k in x.id_of}


def _holder(spans: list[tuple[int, int, str]], n: int) -> str | None:
    """The innermost function holding line n."""
    best = None
    for a, b, nid in spans:
        if a <= n <= b and (best is None or b - a < best[1] - best[0]):
            best = (a, b, nid)
    return best[2] if best else None


def classify(g: Branch, x, src: Sources, story_of: dict[str, str], path_story: dict[str, str], order: list[str],
             lines=None) -> tuple[list[GatedLine], int, int]:
    """Every new or changed line of the review against the strongest condition (§7, R24): under it (it doesn't run when
    the condition is false), outside it (it still runs), or elsewhere (another function: it runs unless that function is
    reached only through the guarded block). The test's own lines and lines that say nothing alone are left out."""
    pos = {s: i for i, s in enumerate(order)}
    guarded = _only_guarded(x, g)
    spans: dict[str, list[tuple[int, int, str]]] = {}
    for key, fn in x.fa.items():
        if key in x.id_of:
            spans.setdefault(fn.file, []).append((fn.start_line, fn.end_line, x.id_of[key]))
    rows: list[tuple] = []
    for fc in x.c.cs.files:
        path = fc.local
        for n in sorted(src.marks(path)):
            text = src.line(path, n)
            if trivial(text):
                continue
            nid = _holder(spans.get(path, []), n)
            if nid == g.node:
                if n in g.own:
                    continue
                where, runs = ("under", False) if n in g.body else ("outside", True)
            else:
                where, runs = "elsewhere", nid not in guarded
            story = story_of.get(nid) if nid else path_story.get(rel_path(x, path))
            rows.append((where, story, path, n, text, runs, nid))
    rank = {"under": 0, "outside": 1, "elsewhere": 2}
    rows.sort(key=lambda r: (rank[r[0]], pos.get(r[1], len(pos)), r[2], r[3]))
    out = [GatedLine(story=s, cl=line_cl(x, p, n, lines), text=norm_ws(t), runs=run, where=w, path=rel_path(x, p), line=n,
                     function=x.label(nid) if nid else None)
           for w, s, p, n, t, run, nid in rows[:MAX_LINES]]
    return out, sum(1 for r in rows if r[5]), sum(1 for r in rows if not r[5])


def build_gates(x, ss, r, per, src: Sources, lines=None) -> tuple[list[Gate], list[Branch]]:
    """The review's conditions, strongest first, at most MAX_GATES; only the first lists its lines (R14)."""
    story_of = node_stories(ss)
    path_story: dict[str, str] = {}
    for sid in r.order:
        sr = per.get(sid)
        for w in sr.where if sr is not None else []:
            path_story.setdefault(w.path, sid)
    branches = find_gates(x, src, story_of, r.order)[:MAX_GATES]
    gates: list[Gate] = []
    for i, b in enumerate(branches, 1):
        b.id = f"G{i}"
        g = Gate(id=b.id, node=b.node, test=b.test, story=story_of.get(b.node), path=rel_path(x, b.path), line=b.line,
                 guarded=[b.first, b.last])
        if i == 1:
            g.lines, g.runs, g.stops = classify(b, x, src, story_of, path_story, r.order, lines)
        gates.append(g)
    return gates, branches
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gates.py tests/test_reading.py tests/test_board.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass (the conftest refactor keeps `analysed` the same); `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/gates.py backend/tests/test_gates.py backend/tests/conftest.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the conditions a change adds and the changed lines that still run when one is false

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 3: components.py — where the change sits

**Files:**
- Create: `backend/codetortoise/components.py`
- Test: `backend/tests/test_components.py`

**Interfaces:**
- Consumes: `design.Component`; `config.ComponentRule`; `board._layer_name`; `reading.rel_path`; `_Ctx.local`,
  `_Ctx.label`, `_Ctx.im`, `_Ctx.changed`, `_Ctx.c.layers` (`module_of`, `level_of`), `_Ctx.c.cs.files`,
  `_Ctx.c.cfg.components`; `Reading.order`, `Reading.threads`; `StoryReading.where`.
- Produces: `component_of(x, path, rules) -> str | None`;
  `build_components(x, ss, r, per, rules=None) -> (list[Component], dict[nid, component name])`.

- [ ] **Step 1: Write the failing tests**

```python
# path: backend/tests/test_components.py
"""Where the change sits (spec 2026-11-02 §5): components, their bands and the edges that cross between them."""
from test_stories import _world

from codetortoise.board import _Ctx
from codetortoise.components import build_components, component_of
from codetortoise.config import ComponentRule


def test_the_demo_sits_in_five_components_banded_by_layer(demo):
    comps, node_comp = build_components(demo.x, demo.ss, demo.r, demo.per, rules=[])
    assert [(c.name, c.level, c.band, c.threads, c.quiet) for c in comps] == [
        ("service", 3, "service", ["T2"], False), ("driver", 2, "driver", ["T1"], False),
        ("hal", 1, "hal", ["T1"], False), ("cpp", 0, "cpp, include/hal", ["T3"], True),
        ("include/hal", 0, "cpp, include/hal", [], False)]
    by = {c.name: c for c in comps}
    assert by["service"].crossing == ["`logger_flush`, `logger_write` call `uart_send`", "`main` calls `logger_init`"]
    assert by["driver"].crossing == ["`uart_init`, `uart_send` call `hal_write`"]
    assert by["hal"].crossing == ["`hal_write` writes `Regs::ctrl`, `Regs::status`"]
    assert by["cpp"].crossing == [] and by["include/hal"].crossing == []
    assert (by["driver"].files, by["driver"].globs, by["driver"].stories) == (
        ["driver/uart.c", "driver/uart.h"], ["driver/*"], ["S1"])
    named = {demo.x.label(n): c for n, c in node_comp.items()}
    assert (named["main"], named["uart_send"], named["Regs::ctrl"]) == ("app", "driver", "include/hal")


def test_components_from_config_take_the_first_rule_a_file_matches(demo):
    rules = [ComponentRule(name="Driver", globs=["driver/*"]), ComponentRule(name="HAL", globs=["hal/*", "include/hal/*"]),
             ComponentRule(name="Everything", globs=["*"])]
    comps, _ = build_components(demo.x, demo.ss, demo.r, demo.per, rules=rules)
    assert [(c.name, c.level, c.globs) for c in comps] == [
        ("Everything", 3, ["*"]), ("Driver", 2, ["driver/*"]), ("HAL", 1, ["hal/*", "include/hal/*"])]
    assert comps[0].files == ["cpp/engine.cpp", "service/logger.c", "service/logger.h"]


def test_a_file_outside_the_workspace_has_no_component_and_one_at_its_root_is_top_level():
    x = _Ctx(_world([("a", "x/y/a.c", ["a = 1;"], ["a = 2;"])]))
    assert component_of(x, "/w/top.c", []) == "top level"
    assert component_of(x, "/elsewhere/sys.h", []) is None
    assert component_of(x, "/w/x/y/a.c", []) == "x/y"
    assert component_of(x, "/w/x/y/a.c", [ComponentRule(name="X", globs=["x/*"])]) == "X"


def test_a_change_inside_one_folder_is_one_component():
    c = _world([("a", "x/a.c", ["a = 1;"], ["a = 2;"]), ("b", "x/b.c", ["b = 1;"], ["b = 2;"])], calls=[("a", "b")])
    x = _Ctx(c)

    class R:
        order, threads = [], []
    comps, _ = build_components(x, None, R, {}, rules=[])
    assert [(c.name, c.level, c.band, c.quiet) for c in comps] == [("x", None, "other", True)]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_components.py`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'codetortoise.components'`.

- [ ] **Step 3: Write components.py**

```python
# path: backend/codetortoise/components.py
"""Where the change sits (spec 2026-11-02 §5): the components the change touches, banded by layer, each with the
threads that change it and the impact edges that cross into or out of it. Rules only (R15, R26)."""
from __future__ import annotations

import posixpath
from fnmatch import fnmatch

from codetortoise.board import _layer_name
from codetortoise.design import Component
from codetortoise.reading import rel_path

MAX_CROSSING = 3          # sentences per block
NAMES = 3                 # names in a sentence before "and N more"
TOP = "top level"
_CROSSING_KINDS = ("call", "virtual", "reads", "writes")


def component_of(x, path: str | None, rules) -> str | None:
    """A file's component: the first rule with a glob matching its workspace-relative path, else its module
    (layers.py), else its folder; None for a file outside the workspace."""
    if not path:
        return None
    rel = rel_path(x, path)
    if rel.startswith("/"):
        return None
    for rule in rules:
        if any(fnmatch(rel, g) for g in rule.globs):
            return rule.name
    m = x.c.layers.module_of(path) if x.c.layers is not None else posixpath.dirname(rel)
    return TOP if m in ("", ".") else m


def _names(x, nids) -> str:
    names = sorted({x.label(n) for n in nids})
    head = ", ".join(f"`{n}`" for n in names[:NAMES])
    return head + (f" and {len(names) - NAMES} more" if len(names) > NAMES else "")


def build_components(x, ss, r, per, rules=None) -> tuple[list[Component], dict[str, str]]:
    """The components holding the change's files, highest layer first, and every node's component. An edge crosses
    when its ends sit in two components and one end is changed code; its sentence goes on its source's block when that
    holds changed files, else on its destination's. A component no crossing edge touches is quiet."""
    rules = x.c.cfg.components if rules is None else rules
    files: dict[str, list[str]] = {}
    levels: dict[str, list[int]] = {}
    for fc in x.c.cs.files:
        name = component_of(x, fc.local, rules)
        if name is None:
            continue
        files.setdefault(name, []).append(rel_path(x, fc.local))
        lv = x.c.layers.level_of(fc.local) if x.c.layers is not None else None
        if lv is not None:
            levels.setdefault(name, []).append(lv)
    node_comp: dict[str, str] = {}
    for nid in x.im.nodes:
        comp = component_of(x, x.local(nid), rules)
        if comp is not None:
            node_comp[nid] = comp
    groups: dict[tuple[str, str, str], set[str]] = {}       # (kind, block, the shared end) -> the other ends
    counted: set[str] = set()
    for e in x.im.edges:
        if e.status == "removed" or e.kind not in _CROSSING_KINDS or (e.src not in x.changed and e.dst not in x.changed):
            continue
        a, b = node_comp.get(e.src), node_comp.get(e.dst)
        if a is None or b is None or a == b:
            continue
        counted.update((a, b))
        home = a if a in files else b if b in files else None
        if home is None:
            continue
        if e.kind in ("call", "virtual"):
            groups.setdefault(("call", home, e.dst), set()).add(e.src)
        else:
            groups.setdefault((e.kind, home, e.src), set()).add(e.dst)
    said: dict[str, list[tuple[int, str]]] = {}
    for (kind, home, end), others in groups.items():
        if kind == "call":
            verb = "calls" if len({x.label(n) for n in others}) == 1 else "call"
            text = f"{_names(x, others)} {verb} `{x.label(end)}`"
        else:
            text = f"`{x.label(end)}` {kind} {_names(x, others)}"
        said.setdefault(home, []).append((len(others), text))
    thread_of = {sid: t.id for t in r.threads for sid in t.stories}
    comp_of_rel = {f: name for name, fs in files.items() for f in fs}
    holders: dict[str, list[str]] = {}
    for sid in r.order:
        sr = per.get(sid)
        for w in sr.where if sr is not None else []:
            name = comp_of_rel.get(w.path)
            if name is not None and sid not in holders.setdefault(name, []):
                holders[name].append(sid)
    out: list[Component] = []
    for name, fs in files.items():
        lv = max(levels[name]) if name in levels else None
        sids = holders.get(name, [])
        threads = [t.id for t in r.threads if any(thread_of.get(s) == t.id for s in sids)]
        rule = next((rr for rr in rules if rr.name == name), None)
        globs = list(rule.globs) if rule is not None else (["*"] if name == TOP else [f"{name}/*"])
        crossing = [t for _, t in sorted(said.get(name, []), key=lambda p: (-p[0], p[1]))[:MAX_CROSSING]]
        out.append(Component(name=name, level=lv, band=_layer_name(x, lv) if lv is not None else "other", globs=globs,
                             threads=threads, stories=sids, files=sorted(fs), crossing=crossing,
                             quiet=name not in counted))
    out.sort(key=lambda c: (c.level is None, -(c.level or 0), c.name))
    return out, node_comp
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_components.py && .venv/bin/ruff check codetortoise tests`
Expected: 4 passed; `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/components.py backend/tests/test_components.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the components a change sits in and the impact edges that cross between them

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 4: walks.py — the walk-throughs

**Files:**
- Create: `backend/codetortoise/walks.py`
- Test: `backend/tests/test_walks.py`

**Interfaces:**
- Consumes: `design.Walk`, `design.WalkStep`; `gates.Sources`, `gates.Branch`, `gates.FnShape`, `gates.line_cl`,
  `gates.node_stories`, `gates.build_gates` (tests); `cparse._negate`, `_txt`, `norm_ws`; `reading.rel_path`;
  `StoryDetail.board.flows`; `Reading.order/threads/connections/checks`; `StoryReading.paths/where`;
  `Function.signature/returns/return_lines/start_line/end_line`; `CallEdge`, `FieldAccess`.
- Produces: `build_walks(x, ss, details, r, per, src, branches, lines=None, *, depth=None, max_walks=None) ->
  list[Walk]`; `flow_keys(f, checks, x) -> list[str]`; `fold(steps, important, depth) -> list[WalkStep]`;
  `statement`, `call_text`, `access_text`.

- [ ] **Step 1: Write the failing tests**

```python
# path: backend/tests/test_walks.py
"""Walk-throughs (spec 2026-11-02 §4, §18.2–§18.4): the demo's four, step by step."""
from codetortoise.design import WalkStep
from codetortoise.gates import build_gates
from codetortoise.walks import build_walks, fold


def _walks(demo, **kw):
    _, branches = build_gates(demo.x, demo.ss, demo.r, demo.per, demo.src, demo.lines)
    return build_walks(demo.x, demo.ss, demo.det, demo.r, demo.per, demo.src, branches, demo.lines, **kw)


def _rows(x, w):
    return [(s.kind, x.label(s.src), x.label(s.dst), s.label, s.status, s.ref, s.story, s.flow, s.flow_n) for s in w.steps]


def test_the_demo_has_four_walk_throughs_listed_by_condition_then_causes(demo):
    assert [(w.id, w.title, w.thread, w.connection, w.condition, w.case, w.stories) for w in _walks(demo)] == [
        ("W1", "When `len > 64`", "T1", ("T1", "T2"), "G1", True, ["S1"]),
        ("W2", "When `len > 64` is false", "T1", None, "G1", False, ["S1", "S2"]),
        ("W3", "From `main` through `hal_write`", "T1", None, None, None, ["S2"]),
        ("W4", "From `main` through `logger_init`", "T2", None, None, None, ["S5", "S3"])]


def test_w1_takes_the_new_branch_returns_minus_2_to_logger_flush_and_reaches_the_reader(demo):
    x, w = demo.x, _walks(demo)[0]
    assert _rows(x, w) == [
        ("call", "main", "logger_flush", "logger_flush(&g_log)", "same", "path", "S1", "FL1", 1),
        ("call", "logger_flush", "uart_send", 'uart_send(lg->uart, "\\n", 1)', "same", "path", "S1", "FL1", 1),
        ("self", "uart_send", "uart_send", "len > 64", "new", "change", "S1", None, None),
        ("write", "uart_send", "Uart::errors", "*err += 1", "new", "change", "S1", None, None),
        ("return", "uart_send", "logger_flush", "-2", "new", "flow", "S1", "FL1", 1),
        ("return", "logger_flush", "main", "", "same", "code", None, None, None),
        ("call", "main", "uart_errors", "uart_errors(&g_uart)", "same", "code", None, None, None),
        ("read", "Uart::errors", "uart_errors", "u->errors", "same", "flow", "S1", "FL3", 2),
        ("return", "uart_errors", "main", "u->errors", "same", "code", None, None, None)]
    cause = {k.key: k.cause for k in demo.r.checks}
    assert (w.steps[4].keys, w.steps[4].cause) == (["result|service/logger.c|logger_flush|uart_send"],
                                                   cause["result|service/logger.c|logger_flush|uart_send"])
    assert (w.steps[7].keys, w.steps[7].cause) == (["reader|driver/uart.c|uart_errors|uart_send"],
                                                   cause["reader|driver/uart.c|uart_errors|uart_send"])
    assert [x.label(n) for n in w.parts] == ["main", "logger_flush", "uart_send", "uart_errors"]
    assert (w.steps[2].path, w.steps[2].line, w.steps[2].cl) == ("driver/uart.c", 16, 101)


def test_w2_is_the_false_side_through_the_loop_into_hal_write(demo):
    x, w = demo.x, _walks(demo)[1]
    assert [r[:7] for r in _rows(x, w)] == [
        ("call", "main", "logger_flush", "logger_flush(&g_log)", "same", "path", "S1"),
        ("call", "logger_flush", "uart_send", 'uart_send(lg->uart, "\\n", 1)', "same", "path", "S1"),
        ("self", "uart_send", "uart_send", "!(len > 64)", "new", "change", "S1"),
        ("call", "uart_send", "hal_write", "hal_write(u->regs, REG_STATUS, buf[i])", "same", "code", None),
        ("self", "hal_write", "hal_write", "int hal_write(struct Regs *r, unsigned reg, int value)", "changed", "change",
         "S2"),
        ("return", "hal_write", "uart_send", "0", "same", "code", None),
        ("write", "uart_send", "Stats::tx", "st->tx++", "new", "change", "S1"),
        ("return", "uart_send", "logger_flush", "0", "same", "code", None),
        ("return", "logger_flush", "main", "", "same", "code", None)]
    assert [s.loop for s in w.steps] == [None, None, None] + ["for (i = 0; i < len; i++)"] * 4 + [None, None]


def test_w3_follows_the_signature_change_to_the_caller_that_was_not_updated(demo):
    x, w = demo.x, _walks(demo)[2]
    assert _rows(x, w) == [
        ("call", "main", "uart_init", "uart_init(&g_uart, &g_regs, 115200)", "same", "path", "S2", "FL2", 1),
        ("call", "uart_init", "hal_write", "hal_write(regs, REG_CTRL, baud)", "same", "flow", "S2", "FL2", 1),
        ("self", "hal_write", "hal_write", "int hal_write(struct Regs *r, unsigned reg, int value)", "changed", "change",
         "S2", None, None),
        ("return", "hal_write", "uart_init", "0", "same", "code", None, None, None),
        ("return", "uart_init", "main", "hal_write(regs, REG_CTRL, baud)", "same", "code", None, None, None)]
    assert w.steps[1].keys == ["caller|driver/uart.c|uart_init|hal_write"]


def test_w4_writes_the_level_and_the_new_reader_in_another_story_reads_it(demo):
    x, w = demo.x, _walks(demo)[3]
    assert _rows(x, w) == [
        ("call", "main", "logger_init", "logger_init(&g_log, &g_uart)", "same", "path", "S5", None, None),
        ("write", "logger_init", "Logger::level", "lg->level = 2", "new", "change", "S5", None, None),
        ("return", "logger_init", "main", "0", "same", "code", None, None, None),
        ("read", "Logger::level", "logger_level", "lg->level", "new", "change", "S3", None, None)]
    assert [x.label(n) for n in w.parts] == ["main", "logger_init", "logger_level"]


def test_every_steps_story_flow_and_keys_exist_and_max_walks_holds(demo):
    keys = {k.key: k for k in demo.r.checks}
    stories = {s.id for s in demo.ss.stories}
    flows = {f.id for s in demo.ss.stories for f in demo.det[s.id].board.flows if f.id in s.flows}
    for w in _walks(demo):
        for s in w.steps:
            assert s.story is None or s.story in stories
            assert s.flow is None or s.flow in flows
            assert all(k in keys for k in s.keys)
            assert s.cause is None or s.cause in {keys[k].cause for k in s.keys}
    assert [w.id for w in _walks(demo, max_walks=2)] == ["W1", "W2"]


def test_unchanged_calls_more_than_walk_depth_from_the_change_fold_into_one_step():
    def call(a, b, ref="path"):
        return WalkStep(kind="call", src=a, dst=b, label=f"{b}()", status="same", ref=ref)
    steps = [call("N1", "N2"), call("N2", "N3"), call("N3", "N4"), call("N4", "N5"), call("N5", "N6"),
             WalkStep(kind="self", src="N6", dst="N6", label="x > 1", status="new", ref="change")]
    assert [(s.kind, s.src, s.dst, s.label, s.folded) for s in fold(steps, {"N6"}, 2)] == [
        ("fold", "N1", "N4", "… 3 calls", 3), ("call", "N4", "N5", "N5()", 0), ("call", "N5", "N6", "N6()", 0),
        ("self", "N6", "N6", "x > 1", 0)]
    assert len(fold(steps, {"N6"}, 4)) == 6                      # one far call alone never folds
    flowed = [call("N1", "N2", "flow")] + steps[1:]
    assert [s.kind for s in fold(flowed, {"N6"}, 2)] == ["call", "call", "call", "call", "call", "self"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_walks.py`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'codetortoise.walks'`.

- [ ] **Step 3: Write walks.py**

```python
# path: backend/codetortoise/walks.py
"""Walk-throughs (spec 2026-11-02 §4): a story's call path down to its changed function, what that function now does,
and where it lands, chained in calling order and drawn as a sequence. Rules only. Every step points back to the call
path, change, flow or code it comes from; a flow's step carries the flow's check keys, so marking it marks the flow.

One walk-through per story, changed function and case (R3): a function with a condition (gates.py) is walked once each
way. They are listed by condition, those covering the most causes first, and kept when they cover a cause or two
stories that no other walk-through already covers (§4.2, R2)."""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass

from codetortoise.cparse import _negate, _txt, norm_ws
from codetortoise.design import Walk, WalkStep
from codetortoise.gates import Branch, FnShape, Sources, line_cl, node_stories
from codetortoise.reading import rel_path

LABEL = 60            # a step's label, in characters (R11)
TITLE = 40            # a condition's test, in a title
MAX_STEPS = 40        # steps per walk-through, after folding (R19)
MAX_LANDINGS = 4      # flows and follow-on reads per walk-through (R19)
REACH = 6             # calls searched down from a frame to a reader
SKIP = {"mechanical", "tests"}          # stories with no walk-through (R18)
CONTRACT_KINDS = ("caller", "result", "target", "unanalysed")
_LAST = re.compile(r"[\w~]+$")


def _cap(text: str, n: int = LABEL) -> str:
    text = norm_ws(text)
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _code(name: str) -> str:
    """A name in code style for a title: a backtick inside it would flip code and text (frontend Ticks)."""
    return "`" + name.replace("`", "'") + "`"


def statement(src: Sources, path: str, line: int) -> str:
    """A line's code without its trailing comment, `;` or `{`."""
    return _cap(src.line(path, line).split("//", 1)[0].strip().rstrip(";{ \t"))


def call_text(src: Sources, path: str, line: int, callee: str) -> str:
    """The call as written on that line, `uart_send(lg->uart, "\\n", 1)`; else `callee(…)`."""
    want = callee.split("::")[-1]
    s = src.tree(path)[1]
    for node in src.nodes_at(path, line, "call_expression"):
        m = _LAST.search(norm_ws(_txt(s, node.child_by_field_name("function"))))
        if m and m.group(0) == want:
            return _cap(_txt(s, node))
    return f"{want}(…)"


def access_text(src: Sources, path: str, line: int, field: str) -> str:
    """The field access on that line, `u->errors`; else the line's code."""
    s = src.tree(path)[1]
    for node in src.nodes_at(path, line, "field_expression"):
        f = node.child_by_field_name("field")
        if f is not None and _txt(s, f) == field:
            return _cap(_txt(s, node))
    return statement(src, path, line)


def field_of(f) -> str | None:
    """A state flow's field: the node before its landing, when that is not the writer (frontend flowGroups.fieldOf)."""
    if f.tag != "state" or len(f.path) < 2 or not f.cause:
        return None
    return None if f.path[-2] == f.cause else f.path[-2]


def flow_keys(f, checks, x) -> list[str]:
    """A flow's check keys, every kind (R6): frontend flowGroups.flowPlaces, whose hidden kinds the browser leaves out
    itself."""
    if not f.cause:
        return []
    fld = field_of(f)
    name = x.label(fld) if fld else None
    return [k.key for k in checks if k.related == f.cause and k.node == f.lands
            and ((k.kind == "reader" and (name is None or k.field == name)) if f.tag == "state" else k.kind in CONTRACT_KINDS)]


def _raising(x, nid: str) -> int | None:
    """The first line returning a value the function did not return before (clang's literal returns)."""
    key = x.im.nodes[nid].key
    fa, fb = x.fa.get(key), x.fb.get(key)
    if fa is None:
        return None
    new = [fa.return_lines[v] for v in fa.returns if (fb is None or v not in fb.returns) and v in fa.return_lines]
    return min(new) if new else None


def _runs(g: Branch | None, case: bool | None, line: int) -> bool:
    """Whether a line of the gated function runs on this side of its condition."""
    if g is None or case is None or line == g.line:
        return True
    inside = g.first <= line <= g.last
    if not case:
        return not inside
    if inside or line < g.line:
        return True
    if g.alt is not None and g.alt[0] <= line <= g.alt[1]:
        return False
    return not g.returns                         # after the block: only when it does not return


def _loop_at(shape: FnShape | None, line: int) -> str | None:
    """The innermost loop holding a line."""
    best = None
    for lp in shape.loops if shape is not None else []:
        if lp.first <= line <= lp.last and (best is None or lp.last - lp.first < best.last - best.first):
            best = lp
    return best.text if best is not None else None


def fold(steps: list[WalkStep], important: set[str], depth: int) -> list[WalkStep]:
    """Unchanged calls (or returns) far from what matters fold into one step (§4.2, R13, R30): a run of two or more of
    one kind, each from a call path or unchanged code, both of whose ends are at least `depth` calls from a changed
    function, a landing or a reader. Distances run over the walk's own calls and returns; an end not measured is 0."""
    adj: dict[str, set[str]] = defaultdict(set)
    for s in steps:
        if s.kind in ("call", "return") and s.src != s.dst:
            adj[s.src].add(s.dst)
            adj[s.dst].add(s.src)
    dist = {n: 0 for n in important}
    q = deque(important)
    while q:
        n = q.popleft()
        for m in adj[n]:
            if m not in dist:
                dist[m] = dist[n] + 1
                q.append(m)

    def far(s: WalkStep) -> bool:
        return s.kind in ("call", "return") and s.ref in ("path", "code") and \
            min(dist.get(s.src, 0), dist.get(s.dst, 0)) >= depth
    out: list[WalkStep] = []
    i = 0
    while i < len(steps):
        s, j = steps[i], i
        while j < len(steps) and far(steps[j]) and steps[j].kind == s.kind:
            j += 1
        if j - i >= 2:
            word = "calls" if s.kind == "call" else "returns"
            out.append(WalkStep(kind="fold", src=s.src, dst=steps[j - 1].dst, label=f"… {j - i} {word}", status="same",
                                ref="code", folded=j - i))
            i = j
        else:
            out.append(s)
            i += 1
    return out


@dataclass
class _Cand:
    walk: Walk
    causes: set[str]
    cover: set[str]
    group: str                        # its condition, else story:function
    pos: int                          # its story's place in the reading


def _keep(cands: list[_Cand], max_walks: int) -> list[Walk]:
    """Kept: a cause or two stories, not covered by another (§4.2). Listed by condition, the most causes first, then
    the story's place, the true side before the false (R2); numbered in that order (§18.1)."""
    cands = [c for c in cands if c.causes or len(c.walk.stories) >= 2]
    most: dict[str, int] = defaultdict(int)
    first: dict[str, int] = {}
    for c in cands:
        most[c.group] = max(most[c.group], len(c.causes))
        first[c.group] = min(first.get(c.group, c.pos), c.pos)
    side = {True: 0, False: 1, None: 2}
    cands.sort(key=lambda c: (-most[c.group], first[c.group], c.group, side[c.walk.case]))
    kept: list[_Cand] = []
    for c in cands:
        if any(c.cover < o.cover for o in cands) or any(c.cover == o.cover for o in kept):
            continue
        kept.append(c)
    out = [c.walk for c in kept[:max(max_walks, 0)]]
    for i, w in enumerate(out, 1):
        w.id = f"W{i}"
    return out


class _Walker:
    """What every walk-through of a review looks things up in."""

    def __init__(self, x, ss, details, r, per, src: Sources, branches: list[Branch], lines, depth: int):
        self.x, self.r, self.per, self.src, self.lines, self.depth = x, r, per, src, lines, depth
        self.story_of = node_stories(ss)
        self.thread_of = {sid: t.id for t in r.threads for sid in t.stories}
        self.thread_pos = {t.id: i for i, t in enumerate(r.threads)}
        self.pos = {sid: i for i, sid in enumerate(r.order)}
        self.flows: dict[str, list] = {}
        for s in ss.stories:
            d = (details or {}).get(s.id)
            self.flows[s.id] = [f for f in (d.board.flows if d is not None else []) if f.id in s.flows]
        self.flow_n = {(sid, f.id): i for sid, fs in self.flows.items() for i, f in enumerate(fs, 1)}
        self.flow_story = {f.id: sid for sid, fs in self.flows.items() for f in fs}
        self.flow_by_id = {f.id: f for fs in self.flows.values() for f in fs}
        self.check = {k.key: k for k in r.checks}
        self.gate_of: dict[str, Branch] = {}
        for b in branches:
            self.gate_of.setdefault(b.node, b)
        self.calls: dict[tuple[str, str], list] = defaultdict(list)
        self.calls_from: dict[str, list] = defaultdict(list)
        for e in sorted(x.calls_after, key=lambda e: (e.file, e.line)):
            self.calls[(e.caller, e.callee)].append(e)
            self.calls_from[e.caller].append(e)
        down: dict[str, set[str]] = defaultdict(set)
        for e in x.im.edges:
            if e.kind in ("call", "virtual") and e.status != "removed" and not x.is_test_path(e.src):
                down[e.src].add(e.dst)
        self.down = {k: sorted(v, key=lambda n: (x.label(n), n)) for k, v in down.items()}
        self.edge = {(e.src, e.dst, e.kind): e.id for e in x.im.edges}
        self.access: dict[str, list] = defaultdict(list)
        for a in sorted(x.fields_after, key=lambda a: (a.line, a.field)):
            self.access[a.fn].append(a)
        self.file_threads: dict[str, set[str]] = defaultdict(set)
        for sid, sr in per.items():
            t = self.thread_of.get(sid)
            for w in sr.where if t else []:
                self.file_threads[w.path].add(t)

    # ---------------------------------------------------------------- steps
    def _step(self, kind, a, b, label, status, path=None, line=None, **kw) -> WalkStep:
        cl = line_cl(self.x, path, line, self.lines) if path and line and status != "same" else None
        return WalkStep(kind=kind, src=a, dst=b, label=label, status=status, path=rel_path(self.x, path) if path else "",
                        line=line, cl=cl, **kw)

    def _call(self, a: str, b: str, e=None) -> WalkStep:
        """A call from a to b as written at its first call site (after side)."""
        x = self.x
        if e is None:
            es = self.calls.get((x.im.nodes[a].key, x.im.nodes[b].key))
            e = es[0] if es else None
        edge = self.edge.get((a, b, "call")) or self.edge.get((a, b, "virtual"))
        if e is None:
            return self._step("call", a, b, f"{x.label(b).split('::')[-1]}(…)", "same", edge=edge)
        return self._step("call", a, b, call_text(self.src, e.file, e.line, x.label(b)),
                          self.src.marks(e.file).get(e.line, "same"), e.file, e.line, edge=edge)

    def _sig(self, fn) -> tuple[str, int]:
        """A function's signature as written: the first of its lines that names it."""
        for k in range(fn.start_line, min(fn.start_line + 3, fn.end_line) + 1):
            t = statement(self.src, fn.file, k)
            if fn.name in t:
                return t, k
        return _cap(fn.signature), fn.start_line

    def _single_return(self, nid: str) -> tuple[str, int | None, str | None]:
        """A function's one returned expression, its first line and file; "" when it returns several or none."""
        shape = self.src.shape(nid)
        if shape is None or not shape.returns:
            return "", None, None
        vals = {v for _, v in shape.returns}
        if len(vals) != 1:
            return "", None, shape.path
        return _cap(vals.pop()), shape.returns[0][0], shape.path

    def _back(self, callee: str, caller: str) -> WalkStep:
        label, at, path = self._single_return(callee)
        return self._step("return", callee, caller, label, self.src.marks(path).get(at, "same") if at else "same",
                          path if at else None, at)

    def _flow_ref(self, st: WalkStep, fl) -> None:
        sid = self.flow_story.get(fl.id)
        keys = flow_keys(fl, self.r.checks, self.x)
        st.ref, st.story, st.flow, st.flow_n, st.keys = "flow", sid, fl.id, self.flow_n.get((sid, fl.id)), keys
        st.cause = next((self.check[k].cause for k in keys if k in self.check and self.check[k].cause), None)

    def _attach(self, fl) -> str:
        """Where a contract flow's checks sit on the walk (R31): a result row on the return, other rows on the call."""
        kinds = {self.check[k].kind for k in flow_keys(fl, self.r.checks, self.x) if k in self.check}
        if "result" in kinds:
            return "return"
        if kinds:
            return "call"
        return "call" if fl.text.endswith("signature changed") else "return"

    def _read(self, fld: str, reader: str) -> WalkStep:
        x = self.x
        fkey = x.im.nodes[fld].key
        acc = next((a for a in self.access.get(x.im.nodes[reader].key, [])
                    if f"field:{a.field}" == fkey and a.mode == "read"), None)
        if acc is None:
            return self._step("read", fld, reader, x.label(fld).split("::")[-1], "same")
        return self._step("read", fld, reader, access_text(self.src, acc.file, acc.line, acc.field_name),
                          self.src.marks(acc.file).get(acc.line, "same"), acc.file, acc.line)

    # ---------------------------------------------------------------- the path through
    def _spine(self, sid: str, F: str) -> tuple:
        """The calls from an entry down to F (R3): the story's first flow through F, else its first call path ending at
        F, else F alone; and the flow, when one gave it."""
        for fl in self.flows.get(sid, []):
            if fl.cause == F and F in fl.path:
                return fl, list(fl.path[:fl.path.index(F) + 1])
        sr = self.per.get(sid)
        for p in sr.paths if sr is not None else []:
            if p.steps and p.steps[-1] == F:
                return None, list(p.steps)
        return None, [F]

    def _result_flow(self, sid: str, F: str, caller: str | None):
        """The story's contract flow from F whose checks sit on the return to the caller."""
        if caller is None:
            return None
        return next((fl for fl in self.flows.get(sid, []) if fl.tag == "contract" and fl.cause == F and
                     fl.lands == caller and self._attach(fl) == "return"), None)

    def _taken(self, F: str, shape: FnShape | None, gate: Branch | None, case: bool | None, result) -> int | None:
        """The return F takes on this side: the first one its condition guards, when it holds; else the line raising a
        new value a result flow carries back, when it runs; else the last return that runs."""
        if shape is None:
            return None
        if case is True and gate is not None and gate.returns:
            return gate.returns[0]
        rise = _raising(self.x, F)
        if result is not None and rise is not None and _runs(gate, case, rise):
            return rise
        runs = [k for k, _ in shape.returns if _runs(gate, case, k)]
        return runs[-1] if runs else None

    def _writes(self, F: str, fld: str, gate, case, taken) -> bool:
        """Whether F writes the field on a line that runs before its return (marked or not, R29)."""
        fkey = self.x.im.nodes[fld].key
        return any(f"field:{a.field}" == fkey and a.mode != "read" and _runs(gate, case, a.line) and
                   (taken is None or a.line <= taken) for a in self.access.get(self.x.im.nodes[F].key, []))

    def _readers(self, fid: str, F: str, sid: str) -> list[str]:
        """Changed functions of other stories that read a field F wrote."""
        x, fkey = self.x, self.x.im.nodes[fid].key
        out = []
        for n in sorted(x.changed, key=lambda n: (len(n), n)):
            s, k = self.story_of.get(n), x.im.nodes[n].key
            if n == F or s is None or s == sid or k not in x.fa:
                continue
            if any(f"field:{a.field}" == fkey and a.mode == "read" for a in self.access.get(k, [])):
                out.append(n)
        return out

    def _reach(self, a: str, target: str) -> list[str] | None:
        """A shortest chain of live calls from a down to target, at most REACH long."""
        if a == target:
            return [a]
        prev: dict[str, str | None] = {a: None}
        q = deque([(a, 0)])
        while q:
            n, d = q.popleft()
            if d >= REACH:
                continue
            for m in self.down.get(n, []):
                if m in prev:
                    continue
                prev[m] = n
                if m == target:
                    out = [m]
                    while prev[out[-1]] is not None:
                        out.append(prev[out[-1]])
                    return out[::-1]
                q.append((m, d + 1))
        return None

    def _land(self, steps: list[WalkStep], stack: list[str], target: str) -> list[str]:
        """Return to the deepest frame that calls down to target, then call down to it; the new stack. A target no
        frame reaches is read where the walk stands."""
        for i in range(len(stack) - 1, -1, -1):
            path = self._reach(stack[i], target)
            if path is None:
                continue
            while len(stack) > i + 1:
                steps.append(self._back(stack[-1], stack[-2]))
                stack = stack[:-1]
            for a, b in zip(path, path[1:], strict=False):
                steps.append(self._call(a, b))
            return stack + path[1:]
        return stack

    def _call_into(self, F: str, e, sid: str, marks: dict[int, str], loop: str | None) -> list[WalkStep]:
        """A call F makes on a changed line or into changed code, and what changed in the callee: its signature, its
        writes on changed lines, and its return (R10)."""
        x, src = self.x, self.src
        callee = x.id_of[e.callee]
        st = self._call(F, callee, e)
        st.loop = loop
        if e.line in marks:
            st.ref, st.story = "change", sid
        out = [st]
        key = x.im.nodes[callee].key
        cfa, cfb = x.fa.get(key), x.fb.get(key)
        csid = self.story_of.get(callee)
        if cfa is not None and cfb is not None and cfa.signature != cfb.signature:
            label, at = self._sig(cfa)
            out.append(self._step("self", callee, callee, label, "changed", cfa.file, at, ref="change", story=csid,
                                  loop=loop))
        if cfa is not None:
            cm, seen = src.marks(cfa.file), set()
            for acc in self.access.get(key, []):
                fid = x.id_of.get(f"field:{acc.field}")
                if acc.mode == "read" or acc.line not in cm or (acc.line, acc.field) in seen or fid is None:
                    continue
                seen.add((acc.line, acc.field))
                out.append(self._step("write", callee, fid, statement(src, acc.file, acc.line), cm[acc.line], acc.file,
                                      acc.line, ref="change", story=csid, loop=loop))
        back = self._back(callee, F)
        back.loop = loop
        out.append(back)
        return out

    # ---------------------------------------------------------------- one walk-through
    def walk(self, sid: str, F: str, gate: Branch | None, case: bool | None) -> _Cand | None:
        x, src = self.x, self.src
        key = x.im.nodes[F].key
        fa, fb = x.fa[key], x.fb.get(key)
        shape = src.shape(F)
        marks = src.marks(fa.file)
        flow, spine = self._spine(sid, F)
        caller = spine[-2] if len(spine) >= 2 else None
        steps: list[WalkStep] = []

        # 1. down the call path; a contract flow whose checks sit on the call marks the last call
        on_call = flow is not None and flow.tag == "contract" and flow.lands == caller and self._attach(flow) == "call"
        for a, b in zip(spine, spine[1:], strict=False):
            st = self._call(a, b)
            st.ref, st.story = "path", sid
            if flow is not None:
                st.flow, st.flow_n = flow.id, self.flow_n.get((sid, flow.id))
            if b == F and on_call:
                self._flow_ref(st, flow)
            steps.append(st)

        # 2. what F now does, in line order, up to the return it takes (R10, R32)
        result = self._result_flow(sid, F, caller)
        taken = self._taken(F, shape, gate, case, result)
        events: list[tuple[int, int, str, object]] = []
        if fb is not None and fb.signature != fa.signature:
            events.append((fa.start_line, 0, "sig", fa))
        if gate is not None:
            events.append((gate.line, 1, "gate", gate))
        seen: set = set()
        for e in self.calls_from.get(key, []):
            callee = x.id_of.get(e.callee)
            if callee is None or (e.line, callee) in seen or not _runs(gate, case, e.line):
                continue
            if e.line in marks or callee in x.changed:
                seen.add((e.line, callee))
                events.append((e.line, 2, "call", e))
        for acc in self.access.get(key, []):
            if acc.mode == "read" or acc.line not in marks or not _runs(gate, case, acc.line) or (acc.line, acc.field) in seen:
                continue
            seen.add((acc.line, acc.field))
            events.append((acc.line, 3, "write", acc))
        events.sort(key=lambda ev: (ev[0], ev[1]))
        wrote: list[str] = []
        for line, _, kind, obj in events:
            if taken is not None and line > taken:
                break
            loop = _loop_at(shape, line)
            if kind == "sig":
                label, at = self._sig(fa)
                steps.append(self._step("self", F, F, label, "changed", fa.file, at, ref="change", story=sid, loop=loop))
            elif kind == "gate":
                test = obj.test if case is not False else _negate(obj.test)
                steps.append(self._step("self", F, F, _cap(test), marks.get(obj.line, "same"), fa.file, obj.line,
                                        ref="change", story=sid, loop=loop))
            elif kind == "call":
                steps += self._call_into(F, obj, sid, marks, loop)
            else:
                fid = x.id_of.get(f"field:{obj.field}")
                if fid is None:
                    continue
                steps.append(self._step("write", F, fid, statement(src, obj.file, obj.line), marks[obj.line], obj.file,
                                        obj.line, ref="change", story=sid, loop=loop))
                if fid not in wrote:
                    wrote.append(fid)

        # 3. back to the caller, carrying a result flow's checks when this return raises its value
        stack = list(spine)
        if caller is not None:
            label = next((v for k, v in (shape.returns if shape is not None else []) if k == taken), "")
            st = self._step("return", F, caller, _cap(label), marks.get(taken, "same") if taken else "same",
                            fa.file if taken else None, taken)
            if result is not None and taken is not None and taken == _raising(x, F):
                self._flow_ref(st, result)
            elif taken is not None and taken in marks:
                st.ref, st.story = "change", sid
            steps.append(st)
            stack.pop()

        # 4. where its state flows land; 5. changed readers, in other stories, of what it wrote
        landings = 0
        for fl in self.flows.get(sid, []):
            fld = field_of(fl)
            if landings >= MAX_LANDINGS or fl.tag != "state" or fl.cause != F or fld is None:
                continue
            if not self._writes(F, fld, gate, case, taken):
                continue
            stack = self._land(steps, stack, fl.lands)
            st = self._read(fld, fl.lands)
            self._flow_ref(st, fl)
            steps.append(st)
            landings += 1
        for fid in wrote:
            for reader in self._readers(fid, F, sid):
                if landings >= MAX_LANDINGS:
                    break
                stack = self._land(steps, stack, reader)
                st = self._read(fid, reader)
                st.ref, st.story = "change", self.story_of.get(reader)
                steps.append(st)
                landings += 1

        # 6. back up to the entry
        while len(stack) >= 2:
            steps.append(self._back(stack[-1], stack[-2]))
            stack.pop()
        if not steps:
            return None
        return self._finish(sid, F, gate, case, spine, steps)

    def _finish(self, sid, F, gate, case, spine, steps) -> _Cand:
        x = self.x
        important = {n for s in steps for n in (s.src, s.dst) if n in x.changed}
        important |= {s.dst for s in steps if s.kind == "read"}
        important |= {self.flow_by_id[s.flow].lands for s in steps if s.ref == "flow" and s.flow in self.flow_by_id}
        steps = fold(steps, important, self.depth)[:MAX_STEPS]
        parts: list[str] = []
        stories: list[str] = []
        for s in steps:
            for n in (s.src, s.dst):
                if x.im.nodes[n].kind == "function" and n not in parts:
                    parts.append(n)
            if s.story and s.story not in stories:
                stories.append(s.story)
        causes = {self.check[k].cause for s in steps if s.ref == "flow" for k in s.keys
                  if k in self.check and self.check[k].cause}
        thread, connection = self._anchor(sid, steps)
        w = Walk(id="", title=self._title(gate, case, spine, F), thread=thread, connection=connection,
                 condition=gate.id if gate is not None else None, case=case, parts=parts, stories=stories, steps=steps)
        cover = set(stories) | {f"flow:{s.flow}" for s in steps if s.ref == "flow" and s.flow}
        group = gate.id if gate is not None else f"{sid}:{F}"
        return _Cand(w, causes, cover, group, self.pos.get(sid, len(self.pos)))

    def _anchor(self, sid: str, steps: list[WalkStep]) -> tuple[str | None, tuple[str, str] | None]:
        """Its thread, and the connection it crosses (§2, R8): a step from another thread's story, or a flow landing in
        a file another thread's stories change."""
        thread = self.thread_of.get(sid)
        for s in steps:
            other: set[str] = set()
            if s.story and self.thread_of.get(s.story) not in (None, thread):
                other = {self.thread_of[s.story]}
            elif s.ref == "flow" and s.flow in self.flow_by_id:
                loc = self.x.local(self.flow_by_id[s.flow].lands)
                other = (self.file_threads.get(rel_path(self.x, loc), set()) - {thread}) if loc else set()
            if other and thread:
                t = min(other, key=lambda t: self.thread_pos.get(t, len(self.thread_pos)))
                k = next((k for k in self.r.connections if {k.a, k.b} == {thread, t}), None)
                if k is not None:
                    return thread, (k.a, k.b)
        return thread, None

    def _title(self, gate, case, spine, F) -> str:
        """The fixed title (§4.2): the condition's side, else the entry and the changed function."""
        if gate is not None and case is not None:
            t = _code(_cap(gate.test, TITLE))
            return f"When {t}" if case else f"When {t} is false"
        if spine[0] == F:
            return f"In {_code(self.x.label(F))}"
        return f"From {_code(self.x.label(spine[0]))} through {_code(self.x.label(F))}"


def build_walks(x, ss, details, r, per, src: Sources, branches: list[Branch], lines=None, *, depth: int | None = None,
                max_walks: int | None = None) -> list[Walk]:
    """The review's walk-throughs (§4.2): for each story in reading order (not mechanical or tests ones), each changed
    function that exists after the change, each side of its strongest condition."""
    cfg = x.c.cfg
    w = _Walker(x, ss, details, r, per, src, branches, lines, cfg.walk_depth if depth is None else depth)
    story = {s.id: s for s in ss.stories}
    cands: list[_Cand] = []
    for sid in r.order:
        s = story.get(sid)
        if s is None or s.kind in SKIP:
            continue
        for F in s.nodes:
            n = x.im.nodes.get(F)
            if n is None or n.kind != "function" or n.key not in x.fa:
                continue
            gate = w.gate_of.get(F)
            for case in ((True, False) if gate is not None else (None,)):
                c = w.walk(sid, F, gate, case)
                if c is not None:
                    cands.append(c)
    return _keep(cands, cfg.max_walks if max_walks is None else max_walks)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_walks.py tests/test_gates.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/walks.py backend/tests/test_walks.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: walk-throughs: a story's call path, what its change does and where it lands, in calling order

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 5: The design stage, serving it, and its limits at scale

**Files:**
- Modify: `backend/codetortoise/design.py` (append `build_design`, `design_nodes`)
- Modify: `backend/codetortoise/pipeline.py` (STAGES, DEPS, `stage()`, `drop_reading`, `read()`, a `design` stage, the
  loop, an import)
- Modify: `backend/codetortoise/web/app.py` (the `/reading` route)
- Test: `backend/tests/test_design.py`, `backend/tests/test_pipeline.py`, `backend/tests/test_web.py`,
  `backend/tests/test_large_change.py`

**Interfaces:**
- Consumes: `components.build_components`, `gates.Sources`, `gates.build_gates`, `walks.build_walks`.
- Produces: `design.build_design(x, ss, details, r, per, *, lines=None, read_text=None) -> ReadingDesign`;
  `design.design_nodes(x, walks, gates, node_comp) -> dict[str, DesignNode]`; stage `design` (after `reading`, before
  `finalize`) storing blob `reading_design`; GET `/api/reviews/{rid}/reading` gains `design` (the blob or `null`).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_design.py`:

```python
def test_the_demo_design_names_every_node_it_cites(demo):
    from codetortoise.design import build_design
    d = build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    assert (len(d.components), len(d.walks), len(d.gates)) == (5, 4, 1)
    cited = {n for w in d.walks for s in w.steps for n in (s.src, s.dst)} | {g.node for g in d.gates}
    assert cited <= set(d.nodes)
    by = {n.label: n for n in d.nodes.values()}
    assert (by["uart_send"].kind, by["uart_send"].component, by["uart_send"].path, by["uart_send"].line) == (
        "function", "driver", "driver/uart.c", 11)
    assert (by["Uart::errors"].kind, by["Uart::errors"].component, by["Uart::errors"].path) == (
        "field", "driver", "driver/uart.h")
```

In `backend/tests/test_pipeline.py`, `test_full_review_without_llm_or_swarm`: add `"design": "ok"` to the stage dict
between `"reading": "ok"` and `"finalize": "ok"`, and after the `msgs["reading"]` assertion add:

```python
    assert msgs["design"] == "3 component(s), 3 walk-through(s), 1 condition(s)"
    design = svc.store.get_blob(rid, "reading_design")
    assert [w["title"] for w in design["walks"]] == ["When `len > 64`", "When `len > 64` is false",
                                                     "From `main` through `hal_write`"]
```

In `test_a_rerun_that_builds_no_reading_leaves_none_behind`, after each of the two `get_blob(rid, "reading") is None`
assertions, add `assert svc.store.get_blob(rid, "reading_design") is None`, and after the first `run_review(rid, svc)`
add `assert svc.store.get_blob(rid, "reading_design")`.

Append to `backend/tests/test_pipeline.py`:

```python
def test_the_design_stage_can_be_turned_off_and_a_failed_one_leaves_the_reading_and_no_design(fx, tmp_path, monkeypatch):
    from codetortoise import pipeline
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    assert svc.store.get_blob(rid, "reading_design")["walks"]

    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(pipeline, "build_design", boom)
    run_review(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert (st["design"]["status"], st["design"]["message"]) == ("failed", "RuntimeError: broken")
    assert svc.store.get_blob(rid, "reading") and svc.store.get_blob(rid, "reading_design") is None
    monkeypatch.undo()
    svc.cfg.analysis.design = False
    run_review(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert (st["design"]["status"], st["design"]["message"]) == ("ok", "off (analysis.design: false)")
    assert svc.store.get_blob(rid, "reading_design") is None and svc.store.get_review(rid)["status"] == "degraded"
```

In `backend/tests/test_web.py`: in `test_owner_creates_review_others_view_and_comment` change `len(detail["stages"]) == 16`
to `== 17`; in `test_the_reading_endpoint_serves_threads_checks_and_marks_and_the_story_its_tiles` add after the
headline assertion:

```python
    assert [w["id"] for w in r["design"]["walks"]] == ["W1", "W2", "W3"] and r["design"]["gates"][0]["test"] == "len > 64"
```

In `backend/tests/test_large_change.py`, time the stage inside the module fixture and add a test:

```python
DESIGN_SECONDS: list[float] = []


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    import time

    from codetortoise import pipeline
    d = tmp_path_factory.mktemp("large")
    fx = build_large_fixture(d)
    svc = make_services(fx, d / "data")
    svc.build_index()
    rid = svc.store.create_review("large", "owner", fx.cls)
    real = pipeline.build_design

    def timed(*a, **k):
        t = time.perf_counter()
        try:
            return real(*a, **k)
        finally:
            DESIGN_SECONDS.append(time.perf_counter() - t)
    pipeline.build_design = timed
    try:
        run_review(rid, svc)
    finally:
        pipeline.build_design = real
    return svc, rid


def test_the_design_stage_holds_its_limits_on_a_large_change(large):
    svc, rid = large
    st = next(s for s in svc.store.list_stages(rid) if s["name"] == "design")
    d = svc.store.get_blob(rid, "reading_design")
    assert st["status"] == "ok" and DESIGN_SECONDS and max(DESIGN_SECONDS) < 1.0
    assert len(d["walks"]) <= 6 and len(d["gates"]) <= 20 and all(len(w["steps"]) <= 40 for w in d["walks"])
    assert all(len(g["lines"]) <= 200 for g in d["gates"])
```

(Replace the existing `large` fixture with the one above; it keeps returning `svc, rid`.)

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design.py tests/test_pipeline.py tests/test_web.py tests/test_large_change.py`
Expected: FAIL — `ImportError: cannot import name 'build_design'`, the stage dicts lack `design`, `KeyError: 'design'`,
and `AttributeError: module 'codetortoise.pipeline' has no attribute 'build_design'`.

- [ ] **Step 3: Append the builder to design.py**

```python
# append: backend/codetortoise/design.py


def build_design(x, ss, details, r, per, *, lines=None, read_text=None) -> ReadingDesign:
    """The design overview by rules (phase 1): the components, the conditions and the walk-throughs, and every node
    they cite. `x` is the analysis's `_Ctx`; `details` the story details; `r`, `per` the reading and its stories'."""
    from codetortoise.components import build_components
    from codetortoise.gates import Sources, build_gates
    from codetortoise.walks import build_walks
    src = Sources(x, read_text)
    components, node_comp = build_components(x, ss, r, per)
    gates, branches = build_gates(x, ss, r, per, src, lines)
    walks = build_walks(x, ss, details, r, per, src, branches, lines)
    return ReadingDesign(components=components, gates=gates, walks=walks,
                         nodes=design_nodes(x, walks, gates, node_comp))


def design_nodes(x, walks: list[Walk], gates: list[Gate], node_comp: dict[str, str]) -> dict[str, DesignNode]:
    """Label, kind, component, file and line of each node the walk-throughs and conditions cite (R4)."""
    from codetortoise.reading import rel_path
    ids = {g.node for g in gates} | {n for w in walks for n in w.parts}
    ids |= {n for w in walks for s in w.steps for n in (s.src, s.dst)}
    out: dict[str, DesignNode] = {}
    for nid in sorted(ids, key=lambda n: (len(n), n)):
        n = x.im.nodes.get(nid)
        if n is None:
            continue
        fn = x.fa.get(n.key) or x.fb.get(n.key)
        loc = x.local(nid)
        out[nid] = DesignNode(label=n.label, kind=n.kind, component=node_comp.get(nid),
                              path=rel_path(x, loc) if loc else "",
                              line=fn.start_line if fn is not None else x.decl_line.get(n.key))
    return out
```

- [ ] **Step 4: Wire the stage into the pipeline**

In `backend/codetortoise/pipeline.py`:

1. Imports: add `from codetortoise.design import build_design` (in sorted place, after `from codetortoise.config …`
   imports / before `from codetortoise.detectors …`; let `ruff check --fix` order it).
2. `STAGES`: `"reading", "finalize"]` → `"reading", "design", "finalize"]`.
3. `DEPS`: add `"design": ["reading"]` after `"reading": ["board"]`.
4. In `stage()`, the skipped branch:

```python
            if name == "reading":
                drop_reading()
            elif name == "design":
                drop_design()
```

5. `drop_reading()`: `["reading", "reading_head", "lines"]` → `["reading", "reading_head", "lines", "reading_design"]`.
6. In `read()`, the `store.replace_blobs(rid, ["reading", "reading_head", "lines"], …)` keys likewise gain
   `"reading_design"` (a stale design never pairs with a new reading), and after `ctx["reading_stored"] = True` add:

```python
        ctx["reading"], ctx["story_readings"], ctx["lines"], ctx["read_text"] = r, per, lines, read_text
```

7. After `def reading():` (its whole body), add:

```python
    def drop_design() -> None:
        """A run that builds no design leaves none: the overview is then exactly as before the design (spec 2026-11-02
        §9)."""
        store.replace_blobs(rid, ["reading_design"], [], {})

    def design():
        """The design overview (spec 2026-11-02 §4, §5, §7): components, walk-throughs and conditions, by rules (R16)."""
        if not cfg.analysis.design:
            drop_design()
            return "off (analysis.design: false)"
        bs, r, per = ctx.get("boards"), ctx.get("reading"), ctx.get("story_readings")
        if bs is None or bs.analysis is None or r is None or per is None:
            drop_design()
            return "no reading to describe"
        try:
            d = build_design(bs.analysis.x, bs.stories, bs.story_details, r, per, lines=ctx.get("lines"),
                             read_text=ctx.get("read_text"))
        except Exception:
            drop_design()
            raise
        store.replace_blobs(rid, ["reading_design"], [], {"reading_design": d})
        return f"{len(d.components)} component(s), {len(d.walks)} walk-through(s), {len(d.gates)} condition(s)"
```

8. The loop list: `("reading", reading),` … `("finalize", finalize)]` → `("reading", reading), ("design", design),
   ("finalize", finalize)]`.

- [ ] **Step 5: Serve it**

In `backend/codetortoise/web/app.py`, the `reading` route:

```python
        view = reading_view(rid)
        if view is None:
            raise HTTPException(404, NO_READING)
        view["design"] = store.get_blob(rid, "reading_design")       # spec 2026-11-02 §11; null without one
        return view
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design.py tests/test_pipeline.py tests/test_web.py tests/test_large_change.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; `All checks passed!`

- [ ] **Step 7: Run the whole backend suite**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider -x > ../.superpowers/pytmp/full.txt 2>&1; tail -5 ../.superpowers/pytmp/full.txt`
Expected: `N passed` with no failures (other tests that list every stage, if any, gain `design`).

- [ ] **Step 8: Commit**

```bash
git add backend/codetortoise/design.py backend/codetortoise/pipeline.py backend/codetortoise/web/app.py \
  backend/tests/test_design.py backend/tests/test_pipeline.py backend/tests/test_web.py backend/tests/test_large_change.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the design stage stores the design overview and the reading serves it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 6: The design types and the pure walk-through and design rules

**Files:**
- Modify: `frontend/src/reading/types.ts` (append the design types; `Reading` gains `design`)
- Create: `frontend/src/reading/walks.ts`, `frontend/src/reading/design.ts`
- Test: `frontend/src/reading/walks.test.ts`, `frontend/src/reading/design.test.ts`

**Interfaces:**
- Consumes: the JSON of Task 1's models as GET `/api/reviews/{id}/reading` serves them under `design` (Task 5);
  `placeOpen` (`reading/causes.ts`); `letter` (`reading/checks.ts`); `listed` (`reading/overview.ts`); `counted`
  (`lib/tidy.ts`).
- Produces (`reading/types.ts`): `StepKind`, `WalkStep`, `Walk`, `Component`, `GatedLine`, `Gate`, `DesignNode`,
  `Concern`, `Ownership`, `ReadingDesign`; `Reading.design?: ReadingDesign | null`.
- Produces (`reading/walks.ts`): `threadName(threads, tid) -> string | null`; `walkThreads(w) -> string[]`;
  `walkScope(w, threads) -> string`; `stepKeys(st, checks: ReadonlyMap<string, Check>, hidden) -> string[]`;
  `walkOpen(w, checks, hidden, marks) -> number`; `openSteps(w, checks, hidden, marks) -> Set<number>`;
  `walksForThread(design, tid) -> { walk: Walk; other: string | null }[]`; `connectionWalk(design, a, b) -> Walk | null`;
  `storyWalks(design, sid) -> { walk: Walk; steps: number[] }[]`; `stepList(ns) -> string`;
  `flowSteps(design, sid, flow) -> { walk: Walk; n: number }[]`; `stepSentence(st, label) -> string`;
  `StepRef`, `stepRef(st, label) -> StepRef`.
- Produces (`reading/design.ts`): `showsWhere(d) -> boolean`; `Band`, `componentBands(cs) -> Band[]`;
  `blockLine(c, threads) -> string`; `alsoLine(stories, title) -> string`; `foldGate(d) -> Gate | null`;
  `conditionTitle(g) -> string`; `gateGroups(g) -> { runs; stops }`.

- [ ] **Step 1: Write the failing tests**

```ts
// path: frontend/src/reading/walks.test.ts
import { describe, expect, it } from "vitest";
import type { Check, CheckKind, Mark, ReadingDesign, Walk, WalkStep } from "./types";
import { connectionWalk, flowSteps, openSteps, stepKeys, stepList, stepRef, stepSentence, storyWalks, threadName, walkOpen,
         walkScope, walksForThread, walkThreads } from "./walks";

const step = (o: Partial<WalkStep>): WalkStep => ({
  kind: "call", src: "N1", dst: "N2", label: "", status: "same", ref: "code", story: null, flow: null, flow_n: null, cause: null,
  keys: [], edge: null, loop: null, path: "", line: null, cl: null, folded: 0, ...o });
const walk = (o: Partial<Walk>): Walk => ({
  id: "W1", title: "When `len > 64`", title_source: "template", lead: "", thread: "T1", connection: null, condition: null,
  case: null, parts: [], stories: [], steps: [], ...o });
const check = (key: string, kind: CheckKind, cause: string | null): Check => ({
  key, kind, story: "S1", thread: "T1", path: "driver/uart.c", depot: null, line: 1, function: null, node: null, text: "",
  source_line: "", finding: null, cites: [], cause });
const mark = (key: string, changed = false): Mark => ({ key, user: "demo", at: "", source_line: "", changed });
const T = [{ id: "T1" }, { id: "T2" }, { id: "T3" }];
const names: Record<string, string> = { N1: "main", N2: "logger_flush", N3: "uart_send", N4: "uart_errors", F1: "Uart::errors" };
const label = (n: string) => names[n] ?? "a function";

describe("a walk-through's threads (spec 2026-11-02 §3.2)", () => {
  it("names its own thread first, then the other end of its connection", () => {
    expect(walkScope(walk({ thread: "T1", connection: ["T1", "T2"] }), T)).toBe("Thread A with Thread B");
    expect(walkScope(walk({ thread: "T2", connection: ["T1", "T2"] }), T)).toBe("Thread B with Thread A");
    expect(walkScope(walk({ thread: "T3" }), T)).toBe("Thread C");
    expect(walkScope(walk({ thread: null }), T)).toBe("");
    expect(walkScope(walk({ thread: "T9", connection: ["T9", "T2"] }), T)).toBe("Thread B");   // a thread the reading no longer has
    expect(walkThreads(walk({ thread: "T2", connection: ["T1", "T2"] }))).toEqual(["T2", "T1"]);
    expect(threadName(T, "T9")).toBeNull();
  });
});

describe("a walk-through's checks (§4.3)", () => {
  const checks = new Map([check("result|a.c|f|g", "result", "c1"), check("caller|b.c|h|g", "caller", "c1"),
                          check("reader|a.c|r|g", "reader", "c2"), check("confirm|a.c|f|", "confirm", "c3")].map((k) => [k.key, k]));
  const w = walk({ steps: [step({ keys: ["result|a.c|f|g", "caller|b.c|h|g"] }), step({}), step({ keys: ["reader|a.c|r|g", "gone|x.c|y|z"] }),
                           step({ keys: ["confirm|a.c|f|"] })] });
  const hidden = new Set<CheckKind>(["confirm"]);

  it("ticks only the keys the reading still holds, of the kinds shown", () => {
    expect(stepKeys(w.steps[2], checks, hidden)).toEqual(["reader|a.c|r|g"]);
    expect(stepKeys(w.steps[3], checks, hidden)).toEqual([]);
    expect(stepKeys(w.steps[3], checks, new Set())).toEqual(["confirm|a.c|f|"]);
  });

  it("counts the distinct causes still open among its steps", () => {
    expect(walkOpen(w, checks, hidden, {})).toBe(2);                                   // c1 (at two places) and c2
    expect(walkOpen(w, checks, hidden, { "result|a.c|f|g": mark("result|a.c|f|g") })).toBe(2);   // c1 is still open at its caller row
    expect(walkOpen(w, checks, hidden, { "result|a.c|f|g": mark("result|a.c|f|g"), "caller|b.c|h|g": mark("caller|b.c|h|g") })).toBe(1);
    expect(walkOpen(w, checks, hidden, { "reader|a.c|r|g": mark("reader|a.c|r|g", true) })).toBe(2);   // its line changed since: open
    expect(walkOpen(w, checks, new Set(), {})).toBe(3);                                // Confirm shown: c3 counts too
  });

  it("knows which steps have a check still open", () => {
    expect([...openSteps(w, checks, hidden, { "reader|a.c|r|g": mark("reader|a.c|r|g") })]).toEqual([1]);
    expect([...openSteps(w, checks, hidden, {})]).toEqual([1, 3]);
  });
});

describe("where the walk-throughs are listed and linked", () => {
  const d: Pick<ReadingDesign, "walks"> = { walks: [
    walk({ id: "W1", thread: "T1", connection: ["T1", "T2"], steps: [
      step({ ref: "path", story: "S1", flow: "FL1", flow_n: 1 }), step({ ref: "change", story: "S1" }),
      step({ ref: "flow", story: "S1", flow: "FL1", flow_n: 1 }), step({}), step({ ref: "flow", story: "S2", flow: "FL3", flow_n: 1 })] }),
    walk({ id: "W2", thread: "T1", steps: [step({ ref: "path", story: "S1", flow: "FL1", flow_n: 1 }),
                                           step({ ref: "flow", story: "S1", flow: "FL1", flow_n: 1 })] }),
    walk({ id: "W3", thread: "T2", steps: [step({ ref: "change", story: "S2" })] })] };

  it("lists under a thread its own walk-throughs and those on a connection to it, naming the other end", () => {
    expect(walksForThread(d, "T1").map((x) => [x.walk.id, x.other])).toEqual([["W1", "T2"], ["W2", null]]);
    expect(walksForThread(d, "T2").map((x) => [x.walk.id, x.other])).toEqual([["W1", "T1"], ["W3", null]]);
    expect(walksForThread(d, "T3")).toEqual([]);
    expect(connectionWalk(d, "T2", "T1")?.id).toBe("W1");
    expect(connectionWalk(d, "T1", "T3")).toBeNull();
    expect(connectionWalk(null, "T1", "T2")).toBeNull();
  });

  it("finds a story's steps on each walk-through, and a flow's steps (a flow step only)", () => {
    expect(storyWalks(d, "S1").map((x) => [x.walk.id, x.steps])).toEqual([["W1", [1, 2, 3]], ["W2", [1, 2]]]);
    expect(storyWalks(d, "S9")).toEqual([]);
    expect(flowSteps(d, "S1", "FL1").map((x) => [x.walk.id, x.n])).toEqual([["W1", 3], ["W2", 2]]);   // W2's step 1 is its call path
    expect(flowSteps(d, "S1", "FL3")).toEqual([]);                                     // FL3 is S2's
  });

  it("writes step numbers as runs, three or more joined", () => {
    expect(stepList([1, 2, 3, 4, 5, 8])).toBe("1–5, 8");
    expect(stepList([2, 3])).toBe("2, 3");
    expect(stepList([4])).toBe("4");
    expect(stepList([1, 3, 4, 5, 7, 8])).toBe("1, 3–5, 7, 8");
  });
});

describe("a step's line and where it comes from (§3.3)", () => {
  it("says each kind of step in the code's own words", () => {
    expect(stepSentence(step({ src: "N1", dst: "N2", label: "logger_flush(&g_log)" }), label)).toBe("`main` calls `logger_flush(&g_log)`");
    expect(stepSentence(step({ src: "N1", dst: "N2", label: "(*fp)(x)" }), label)).toBe("`main` calls `logger_flush`: `(*fp)(x)`");
    expect(stepSentence(step({ src: "N1", dst: "N2" }), label)).toBe("`main` calls `logger_flush`");
    expect(stepSentence(step({ kind: "return", src: "N3", dst: "N2", label: "-2" }), label)).toBe("`uart_send` returns `-2` to `logger_flush`");
    expect(stepSentence(step({ kind: "return", src: "N2", dst: "N1" }), label)).toBe("`logger_flush` returns to `main`");
    expect(stepSentence(step({ kind: "self", src: "N3", dst: "N3", label: "len > 64" }), label)).toBe("`uart_send`: `len > 64`");
    expect(stepSentence(step({ kind: "write", src: "N3", dst: "F1", label: "*err += 1" }), label))
      .toBe("`uart_send` writes `Uart::errors`: `*err += 1`");
    expect(stepSentence(step({ kind: "read", src: "F1", dst: "N4", label: "u->errors" }), label))
      .toBe("`uart_errors` reads `Uart::errors`: `u->errors`");
    expect(stepSentence(step({ kind: "fold", src: "N1", dst: "N3", folded: 3 }), label)).toBe("… 3 calls, `main` to `uart_send`");
    expect(stepSentence(step({ kind: "self", src: "N3", dst: "N3", label: "a `b` c" }), label)).toBe("`uart_send`: `a 'b' c`");
  });

  it("links a step to the story tab it comes from; a step of the code between them names its function", () => {
    expect(stepRef(step({ ref: "path", story: "S1", flow: "FL1", flow_n: 1 }), label))
      .toEqual({ text: "call path of S1 flow 1", link: { story: "S1", sec: "paths", flow: null } });
    expect(stepRef(step({ ref: "path", story: "S5" }), label).text).toBe("call path of S5");
    expect(stepRef(step({ ref: "change", story: "S1" }), label))
      .toEqual({ text: "S1 · the change", link: { story: "S1", sec: "code", flow: null } });
    expect(stepRef(step({ ref: "flow", story: "S1", flow: "FL3", flow_n: 2 }), label))
      .toEqual({ text: "S1 flow 2", link: { story: "S1", sec: null, flow: 2 } });
    expect(stepRef(step({ kind: "return", src: "N2", dst: "N1" }), label)).toEqual({ text: "`logger_flush`, unchanged", link: null });
    expect(stepRef(step({ kind: "read", src: "F1", dst: "N4" }), label).text).toBe("`uart_errors`, unchanged");
    expect(stepRef(step({ src: "N3", dst: "N2", status: "changed" }), label).text).toBe("`uart_send`, changed");
    expect(stepRef(step({ kind: "fold", src: "N1", dst: "N3", folded: 2 }), label)).toEqual({ text: "unchanged", link: null });
  });
});
```

```ts
// path: frontend/src/reading/design.test.ts
import { describe, expect, it } from "vitest";
import { alsoLine, blockLine, componentBands, conditionTitle, foldGate, gateGroups, showsWhere } from "./design";
import type { Component, Gate, GatedLine } from "./types";

const comp = (o: Partial<Component>): Component => ({
  name: "x", level: null, band: "other", globs: [], threads: [], stories: [], files: [], crossing: [], quiet: false, ...o });
const line = (runs: boolean, o: Partial<GatedLine> = {}): GatedLine => ({
  story: "S1", cl: 101, text: "st->tx++;", runs, where: runs ? "outside" : "under", path: "driver/uart.c", line: 22,
  function: "uart_send", ...o });
const gate = (o: Partial<Gate>): Gate => ({
  id: "G1", node: "N3", test: "len > 64", false_case: "", lines: [], source: "code", story: "S1", path: "driver/uart.c", line: 16,
  guarded: [16, 19], runs: 0, stops: 0, ...o });
const T = [{ id: "T1" }, { id: "T2" }];

describe("Where the change sits (spec 2026-11-02 §5)", () => {
  it("shows with two components or more", () => {
    expect(showsWhere(null)).toBe(false);
    expect(showsWhere({ components: [comp({})] })).toBe(false);
    expect(showsWhere({ components: [comp({}), comp({ name: "y" })] })).toBe(true);
  });

  it("bands the components by layer, the highest first and those without a level last, each band in the design's order", () => {
    const cs = [comp({ name: "x" }), comp({ name: "service", level: 3, band: "service" }),
                comp({ name: "cpp", level: 0, band: "cpp, include/hal" }), comp({ name: "include/hal", level: 0, band: "cpp, include/hal" }),
                comp({ name: "driver", level: 2, band: "driver" })];
    expect(componentBands(cs).map((b) => [b.band, b.level, b.components.map((c) => c.name)])).toEqual([
      ["service", 3, ["service"]], ["driver", 2, ["driver"]], ["cpp, include/hal", 0, ["cpp", "include/hal"]], ["other", null, ["x"]]]);
  });

  it("counts a block's threads by letter and its changed files, and names two of its stories", () => {
    expect(blockLine(comp({ threads: ["T1"], files: ["driver/uart.c", "driver/uart.h"] }), T)).toBe("Thread A · 2 changed files");
    expect(blockLine(comp({ threads: ["T2", "T1", "T9"], files: ["a.c"] }), T)).toBe("Threads B and A · 1 changed file");
    expect(blockLine(comp({}), T)).toBe("");
    const titles: Record<string, string> = { S1: "`uart_send` drops long writes", S2: "`hal_write` takes an int", S3: "levels" };
    const title = (s: string) => titles[s];
    expect(alsoLine(["S1", "S9", "S2", "S3"], title)).toBe("`uart_send` drops long writes; `hal_write` takes an int; and 1 more");
    expect(alsoLine(["S1"], title)).toBe("`uart_send` drops long writes");
    expect(alsoLine([], title)).toBe("");
  });
});

describe("the condition fold (§7)", () => {
  it("is about the strongest condition, when it has lines", () => {
    const g = gate({ lines: [line(true)] });
    expect(foldGate(null)).toBeNull();
    expect(foldGate({ gates: [] })).toBeNull();
    expect(foldGate({ gates: [gate({})] })).toBeNull();
    expect(foldGate({ gates: [g, gate({ id: "G2" })] })).toBe(g);
  });

  it("is titled by the false case and the changes that still run, and lists those, then the ones that stop", () => {
    expect(conditionTitle({ false_case: "", test: "len > 64", runs: 9 })).toBe("When `len > 64` is false · 9 changes still run");
    expect(conditionTitle({ false_case: "Writes that fit (64 bytes or less)", test: "len > 64", runs: 1 }))
      .toBe("Writes that fit (64 bytes or less) · 1 change still runs");
    expect(conditionTitle({ false_case: "", test: "a `b`", runs: 0 })).toBe("When `a 'b'` is false · 0 changes still run");
    const runs = [line(true, { line: 14 }), line(true, { line: 22 })], stops = [line(false, { line: 17 })];
    expect(gateGroups(gate({ lines: [runs[0], stops[0], runs[1]] }))).toEqual({ runs, stops });
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/reading/walks.test.ts src/reading/design.test.ts`
Expected: FAIL: `Failed to resolve import "./walks"` and `Failed to resolve import "./design"`.

- [ ] **Step 3: Add the types**

Append to `frontend/src/reading/types.ts`:

```ts
/** The design overview (spec 2026-11-02-design-overview §9, §18.10): design.py's models as the browser gets them. */
export type StepKind = "call" | "return" | "self" | "write" | "read" | "fold";
/** One step of a walk-through (§4.1): node ids (`src`, `dst`; a field for a write's `dst` and a read's `src`), the code's own
 * words, and what it comes from (`ref`): a story's call path, its change, one of its flows, or the code between them.
 * `keys` are a flow step's check keys, what its tick box marks; `flow_n` is that flow's `?flow=N` on its story. */
export interface WalkStep {
  kind: StepKind; src: string; dst: string; label: string; status: "new" | "changed" | "same";
  ref: "path" | "change" | "flow" | "code"; story: string | null; flow: string | null; flow_n: number | null;
  cause: string | null; keys: string[]; edge: string | null;
  /** The loop it sits in, as written: "for (i = 0; i < len; i++)". */
  loop: string | null;
  path: string; line: number | null; cl: number | null;
  /** A fold step: how many steps it stands for. */
  folded: number;
}
/** A path through the changed code a reviewer would trace by hand (§4); `id` is cited, never shown. Anchored on a thread,
 * or on the connection between two; one side (`case`) of a condition (`condition`, a gate id) or of none. */
export interface Walk {
  id: string; title: string; title_source: "template" | "llm"; lead: string; thread: string | null;
  connection: [string, string] | null; condition: string | null; case: boolean | null;
  /** Function node ids, left to right. */
  parts: string[];
  /** The stories its steps come from, in order. */
  stories: string[]; steps: WalkStep[];
}
/** A block of Where the change sits (§5): a component, the band (layer) it sits in, the threads and stories that change it,
 * its changed files, the edges that cross into or out of it as sentences; `quiet`: it shares none with the rest. */
export interface Component {
  name: string; level: number | null; band: string; globs: string[]; threads: string[]; stories: string[]; files: string[];
  crossing: string[]; quiet: boolean;
}
/** A changed line and whether it still runs when the condition is false (§7); `story` is null for a line no story holds. */
export interface GatedLine {
  story: string | null; cl: number | null; text: string; runs: boolean; where: "under" | "outside" | "elsewhere"; path: string;
  line: number | null; function: string | null;
}
/** A condition the change adds (§7); `false_case` is the model's words for its false side (phase 2), "" until then. */
export interface Gate {
  id: string; node: string; test: string; false_case: string; lines: GatedLine[]; source: "code" | "context"; story: string | null;
  path: string; line: number | null; guarded: number[]; runs: number; stops: number;
}
/** A node a walk-through or a condition cites: `/names` names only the nodes on boards and stories (§18.8). */
export interface DesignNode { label: string; kind: "function" | "field"; component: string | null; path: string; line: number | null }
export interface Concern {
  text: string; how: string; stories: string[]; assessment: "right" | "note" | "confirm" | "ask"; note: string; causes: string[];
}
export interface Ownership { tag: "right" | "questionable" | "shortfall" | "note"; text: string; cites: string[] }
export interface ReadingDesign {
  verdict: string; verdict_causes: string[]; components: Component[]; concerns: Concern[]; ownership: Ownership[]; gates: Gate[];
  walks: Walk[]; nodes: Record<string, DesignNode>; sources: Record<string, "template" | "llm" | "pinned">; context_hash: string | null;
}
```

In the `Reading` interface, after `route?: RouteStep[]; route_source?: "template" | "llm";`, add:

```ts
  /** The design overview (spec 2026-11-02): null when the design stage is off or broke; absent from a server before it. */
  design?: ReadingDesign | null;
```

- [ ] **Step 4: Write walks.ts**

```ts
// path: frontend/src/reading/walks.ts
/** Walk-throughs (spec 2026-11-02-design-overview §4): their threads and open counts, the links a story page, its Flows tab,
 * the outline and the overview make to them, and each step's line and where it comes from. Pure, so the rules are tested
 * apart from React. Names come back in backticks, for `Ticks`. */
import { placeOpen } from "./causes";
import { letter } from "./checks";
import type { Check, CheckKind, Mark, ReadingDesign, Thread, Walk, WalkStep } from "./types";

type Label = (id: string) => string;
type Walks = Pick<ReadingDesign, "walks"> | null | undefined;

/** A name in code style; a backtick inside it becomes a quote, as the Flows tab's names do (`Ticks` pairs them by position). */
const code = (s: string) => `\`${s.replaceAll("`", "'")}\``;

/** "Thread B", lettered as the outline letters it; null for a thread the reading no longer has. */
export function threadName(threads: Pick<Thread, "id">[], tid: string): string | null {
  const i = threads.findIndex((t) => t.id === tid);
  return i < 0 ? null : `Thread ${letter(i, tid)}`;
}

/** A walk-through's threads: its own, then the other end of the connection it is anchored on. */
export function walkThreads(w: Pick<Walk, "thread" | "connection">): string[] {
  return [w.thread, ...(w.connection ?? [])].filter((id, i, all): id is string => !!id && all.indexOf(id) === i);
}

/** "Thread A with Thread B" (§3.2): its threads by name; "" when the reading has none of them. */
export function walkScope(w: Pick<Walk, "thread" | "connection">, threads: Pick<Thread, "id">[]): string {
  return walkThreads(w).map((t) => threadName(threads, t)).filter((n): n is string => !!n).join(" with ");
}

/** A step's check keys that the reading still holds, of the kinds shown: what its tick box marks. */
export function stepKeys(st: Pick<WalkStep, "keys">, checks: ReadonlyMap<string, Check>, hidden: ReadonlySet<CheckKind>): string[] {
  return st.keys.filter((k) => {
    const c = checks.get(k);
    return !!c && !hidden.has(c.kind);
  });
}

/** A walk-through's open count (§4.3): the distinct causes among its steps' shown checks that are still open. */
export function walkOpen(w: Pick<Walk, "steps">, checks: ReadonlyMap<string, Check>, hidden: ReadonlySet<CheckKind>,
                         marks: Record<string, Mark>): number {
  const open = new Set<string>();
  for (const st of w.steps)
    for (const k of stepKeys(st, checks, hidden)) if (placeOpen(k, marks)) open.add(checks.get(k)!.cause ?? k);
  return open.size;
}

/** The steps (1-based) with a shown check still open: the drawing puts their numbers on red. */
export function openSteps(w: Pick<Walk, "steps">, checks: ReadonlyMap<string, Check>, hidden: ReadonlySet<CheckKind>,
                          marks: Record<string, Mark>): Set<number> {
  return new Set(w.steps.flatMap((st, i) => (stepKeys(st, checks, hidden).some((k) => placeOpen(k, marks)) ? [i + 1] : [])));
}

/** The walk-throughs a thread's outline bar lists (§3.2): its own and those on a connection to it, in the design's order;
 * `other` is the connection's other thread. */
export function walksForThread(design: Walks, tid: string): { walk: Walk; other: string | null }[] {
  return (design?.walks ?? []).filter((w) => w.thread === tid || !!w.connection?.includes(tid))
    .map((w) => ({ walk: w, other: w.connection?.find((t) => t !== tid) ?? null }));
}

/** The first walk-through on the connection between threads `a` and `b` (§3.1): its line on the overview links to it. */
export function connectionWalk(design: Walks, a: string, b: string): Walk | null {
  return design?.walks.find((w) => !!w.connection && w.connection.includes(a) && w.connection.includes(b)) ?? null;
}

/** The walk-throughs a story's steps are on, with those steps' numbers (1-based), for its header (§3.2). */
export function storyWalks(design: Walks, sid: string): { walk: Walk; steps: number[] }[] {
  return (design?.walks ?? []).map((walk) => ({ walk, steps: walk.steps.flatMap((s, i) => (s.story === sid ? [i + 1] : [])) }))
    .filter((x) => x.steps.length > 0);
}

/** "1–5, 8": step numbers, a run of three or more as its ends. */
export function stepList(ns: number[]): string {
  const out: string[] = [];
  for (let i = 0; i < ns.length;) {
    let j = i;
    while (j + 1 < ns.length && ns[j + 1] === ns[j] + 1) j++;
    out.push(...(j - i >= 2 ? [`${ns[i]}–${ns[j]}`] : ns.slice(i, j + 1).map(String)));
    i = j + 1;
  }
  return out.join(", ");
}

/** The steps that are a story's flow (a flow step, not the call path that leads to it), for its Flows row (§3.2). */
export function flowSteps(design: Walks, sid: string, flow: string): { walk: Walk; n: number }[] {
  return (design?.walks ?? []).flatMap((walk) => walk.steps.flatMap((s, i) => (
    s.ref === "flow" && s.story === sid && s.flow === flow ? [{ walk, n: i + 1 }] : [])));
}

/** A step's one line (§4.1): who calls, returns to, writes or reads what, in the code's own words. */
export function stepSentence(st: WalkStep, label: Label): string {
  const a = label(st.src), b = label(st.dst), says = st.label ? code(st.label) : "";
  switch (st.kind) {
    case "call":
      return says && st.label.startsWith(b) ? `${code(a)} calls ${says}` : `${code(a)} calls ${code(b)}${says ? `: ${says}` : ""}`;
    case "return": return says ? `${code(a)} returns ${says} to ${code(b)}` : `${code(a)} returns to ${code(b)}`;
    case "write": return `${code(a)} writes ${code(b)}${says ? `: ${says}` : ""}`;
    case "read": return `${code(b)} reads ${code(a)}${says ? `: ${says}` : ""}`;
    case "fold": return `… ${st.folded} call${st.folded === 1 ? "" : "s"}, ${code(a)} to ${code(b)}`;
    default: return `${code(a)}${says ? `: ${says}` : ""}`;
  }
}

/** Where a step comes from (§3.3) and the story tab that shows it: a call path's ("call path of S1 flow 1", the Call paths
 * tab), the change's ("S1 · the change", the Code tab), a flow's ("S1 flow 1", that row of the first tab). A step of the
 * code between them names the function its code is in, and links nowhere: there is no depot path to open. */
export interface StepRef { text: string; link: { story: string; sec: "paths" | "code" | null; flow: number | null } | null }

export function stepRef(st: WalkStep, label: Label): StepRef {
  if (st.ref === "path" && st.story)
    return { text: `call path of ${st.story}${st.flow_n ? ` flow ${st.flow_n}` : ""}`, link: { story: st.story, sec: "paths", flow: null } };
  if (st.ref === "change" && st.story) return { text: `${st.story} · the change`, link: { story: st.story, sec: "code", flow: null } };
  if (st.ref === "flow" && st.story)
    return { text: st.flow_n ? `${st.story} flow ${st.flow_n}` : `${st.story}'s flows`, link: { story: st.story, sec: null, flow: st.flow_n } };
  if (st.kind === "fold") return { text: "unchanged", link: null };
  return { text: `${code(label(st.kind === "read" ? st.dst : st.src))}, ${st.status === "same" ? "unchanged" : st.status}`, link: null };
}
```

- [ ] **Step 5: Write design.ts**

```ts
// path: frontend/src/reading/design.ts
/** The design overview's rules (spec 2026-11-02-design-overview §5, §7): Where the change sits' bands and blocks, and the
 * condition fold's title and lines. Pure, so the rules are tested apart from React. */
import { counted } from "../lib/tidy";
import { letter } from "./checks";
import { listed } from "./overview";
import type { Component, Gate, GatedLine, ReadingDesign, Thread } from "./types";

/** Where the change sits shows only with two components or more (§14). */
export const showsWhere = (d: Pick<ReadingDesign, "components"> | null | undefined): boolean => (d?.components.length ?? 0) >= 2;

export interface Band { band: string; level: number | null; components: Component[] }

/** The components in their layers' bands (§5): the highest layer first, the bands without a level last; in a band, the
 * design's order. */
export function componentBands(cs: Component[]): Band[] {
  const out: Band[] = [];
  for (const c of cs) {
    const b = out.find((x) => x.band === c.band);
    if (b) b.components.push(c);
    else out.push({ band: c.band, level: c.level, components: [c] });
  }
  return out.sort((a, b) => (b.level ?? -1) - (a.level ?? -1));
}

/** A block's count line (§5): the threads that change it, by letter, and its changed files. */
export function blockLine(c: Pick<Component, "threads" | "files">, threads: Pick<Thread, "id">[]): string {
  const letters = c.threads.flatMap((id) => {
    const i = threads.findIndex((t) => t.id === id);
    return i < 0 ? [] : [letter(i, id)];
  });
  return [letters.length ? `Thread${letters.length === 1 ? "" : "s"} ${listed(letters)}` : "", counted(c.files.length, "changed file")]
    .filter(Boolean).join(" · ");
}

/** A block's `.also` line (§5): what changed in it, by its stories' titles, two at most. */
export function alsoLine(stories: string[], title: (sid: string) => string | undefined): string {
  const named = stories.flatMap((s) => {
    const t = title(s);
    return t ? [t] : [];
  });
  const more = named.length - 2;
  return named.slice(0, 2).join("; ") + (more > 0 ? `; and ${more} more` : "");
}

/** The condition the fold is about (§7): the strongest, which the design lists first, when it has lines to sort. */
export const foldGate = (d: Pick<ReadingDesign, "gates"> | null | undefined): Gate | null => (d?.gates[0]?.lines.length ? d.gates[0] : null);

/** The fold's title (§7): the false case in words (the model's, from phase 2; until then "When `test` is false") and how
 * many changes still run then. */
export function conditionTitle(g: Pick<Gate, "false_case" | "test" | "runs">): string {
  const n = g.runs;
  return `${g.false_case || `When \`${g.test.replaceAll("`", "'")}\` is false`} · ${n} change${n === 1 ? "" : "s"} still run${n === 1 ? "s" : ""}`;
}

/** The fold's lines: those that still run when the condition is false, then those that don't. */
export function gateGroups(g: Pick<Gate, "lines">): { runs: GatedLine[]; stops: GatedLine[] } {
  return { runs: g.lines.filter((l) => l.runs), stops: g.lines.filter((l) => !l.runs) };
}
```

- [ ] **Step 6: Run them to see them pass, and the type check**

Run: `cd frontend && npx vitest run src/reading/walks.test.ts src/reading/design.test.ts && npx tsc --noEmit`
Expected: PASS (2 files, 14 tests); tsc prints nothing.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/reading/types.ts frontend/src/reading/walks.ts frontend/src/reading/walks.test.ts frontend/src/reading/design.ts frontend/src/reading/design.test.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the design overview's types and the walk-through and design rules, pure

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 7: The walk-through's place and page

**Files:**
- Modify: `frontend/src/workspace/address.ts`, `frontend/src/workspace/memory.ts`, `frontend/src/workspace/crumbs.ts`,
  `frontend/src/workspace/Workspace.tsx`, `frontend/src/workspace/useRowKeys.ts`, `frontend/src/workspace/FlowsTab.tsx`,
  `frontend/src/workspace/workspace.css`
- Create: `frontend/src/workspace/useMarks.ts`, `frontend/src/workspace/WalkPage.tsx`, `frontend/e2e/walk-throughs.spec.ts`
- Test: `frontend/src/workspace/address.test.ts`, `frontend/src/workspace/memory.test.ts`, `frontend/src/workspace/crumbs.test.ts`,
  `frontend/e2e/walk-throughs.spec.ts`

**Interfaces:**
- Consumes: Task 6's `walkScope`, `walkThreads`, `threadName`, `stepKeys`, `walkOpen`, `stepSentence`, `stepRef`; the
  types `Walk`, `WalkStep`, `ReadingDesign`; `api.markChecks(id, keys)` and `api.unmarkChecks(id, keys)`;
  `ReviewData.loadReading()`, `.loadTicks()`.
- Produces: `Place` gains `{ kind: "walk"; wid: string }` at `/walk/W1`; `Address.step?: number` (`?step=N`, a walk
  place only); `placeKey` `"w:W1"`; `CrumbContext.walks?: { id: string; title: string; scope: string }[]`;
  `useMarks() -> { busy, error, fine(keys) -> Promise<boolean>, reopen(keys) -> Promise<boolean> }`;
  `useRowKeys({ order, busy, leftAt, fine, start?, prefix? })`; `WalkPage({ wid })`, its rows `li#step-N.fl-row`
  with `.fl-toggle`, `.fl-tick`, `.dz-ref`; `e2e/walk-throughs.spec.ts` with `FOUR` and `steps(page)`.

- [ ] **Step 1: Write the failing unit tests**

Append to `frontend/src/workspace/address.test.ts`:

```ts
describe("a walk-through", () => {
  it("is a place of its own, with the step it opens at", () => {
    const a = readAddress("/walk/W1", q("step=4"));
    expect([a.place, a.step]).toEqual([{ kind: "walk", wid: "W1" }, 4]);
    expect(href("/r/7", a)).toBe("/r/7/walk/W1?step=4");
    const [path, query] = href("/r/7", a).slice("/r/7".length).split("?");
    expect(readAddress(path, q(query)).step).toBe(4);
    for (const bad of ["step=0", "step=2.5", "step=x", "step=-1"]) expect(readAddress("/walk/W1", q(bad)).step).toBeUndefined();
    expect(readAddress("/s/S1", q("step=4")).step).toBeUndefined();                  // only a walk-through has steps
    expect(href("/r/7", at({ kind: "story", sid: "S1", view: "steps" }, { step: 4 }))).toBe("/r/7/s/S1");
    expect(readAddress("/walk/W1/x", q("")).place).toEqual({ kind: "unknown", path: "/walk/W1/x" });
    expect(placeKey({ kind: "walk", wid: "W1" })).toBe("w:W1");
  });
});
```

Append to `frontend/src/workspace/memory.test.ts`:

```ts
describe("a walk-through", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is remembered at its step; a stored step that is not one is dropped", () => {
    const w: Address = { place: { kind: "walk", wid: "W1" }, flow: null, open: null, tab: "diff", step: 3 };
    expect(recall(remember({}, w), { kind: "walk", wid: "W1" })).toEqual(w);
    const items: Record<string, string> = {
      "ct.ws.7.memory": JSON.stringify({ "w:W1": w, "w:W2": { ...w, place: { kind: "walk", wid: "W2" }, step: 0 } }) };
    vi.stubGlobal("window", { sessionStorage: { getItem: (k: string) => items[k] ?? null, setItem: () => {} } });
    expect(loadMemory(7)).toEqual({ "w:W1": w });
  });
});
```

Append inside `describe("the breadcrumb", …)` in `frontend/src/workspace/crumbs.test.ts`:

```ts
  it("puts a walk-through under its threads, and says so when the review does not have it", () => {
    const walks = [{ id: "W1", title: "When `len > 64`", scope: "Thread A with Thread B" },
                   { id: "W2", title: "From `main` through `hal_write`", scope: "" }];
    expect(crumbs({ kind: "walk", wid: "W1" }, { ...ctx, walks })).toEqual([
      { label: "Review 7", to: "/r/7" }, { label: "Thread A with Thread B", to: "/r/7" }, { label: "Walk through: When len > 64", to: null }]);
    expect(crumbs({ kind: "walk", wid: "W2" }, { ...ctx, walks })).toEqual([
      { label: "Review 7", to: "/r/7" }, { label: "Walk through: From main through hal_write", to: null }]);
    expect(crumbs({ kind: "walk", wid: "W9" }, { ...ctx, walks }).at(-1)).toEqual({ label: "Not found", to: null });
    expect(crumbs({ kind: "walk", wid: "W1" }, ctx).at(-1)).toEqual({ label: "Not found", to: null });   // a reading with no design
  });
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/workspace/address.test.ts src/workspace/memory.test.ts src/workspace/crumbs.test.ts`
Expected: FAIL: the walk place reads as `{ kind: "unknown", path: "/walk/W1" }`; the memory test's `loadMemory` returns
`{}`; the crumbs test gets `undefined` for its walk case.

- [ ] **Step 3: Add the place, its step, its memory and its crumbs**

In `frontend/src/workspace/address.ts`:

- the `Place` union gains `| { kind: "walk"; wid: string }` after the cluster line;
- `Address` gains, after `sec?: StorySec;`:

```ts
  /** A walk-through's step to open (1-based; spec 2026-11-02 §18.5): `?step=N`. */
  step?: number;
```

- `readPlace` gains, before the `c` line: `if (kind === "walk") return { kind: "walk", wid: id };`
- `readAddress` reads it: after `const flow = Number(q.get("flow"));` add `const step = Number(q.get("step"));`, and
  after the `sec` spread add
  `...(place.kind === "walk" && Number.isInteger(step) && step > 0 ? { step } : {}),`
- `placePath` gains `case "walk": return \`/walk/${p.wid}\`;` and `placeKey` gains `case "walk": return \`w:${p.wid}\`;`
- `href` writes it after `sec`: `if (a.step && a.place.kind === "walk") q.set("step", String(a.step));`

In `frontend/src/workspace/memory.ts`: `isPlace` gains `case "walk": return str(p.wid);`, and `isAddressAt` gains, after
its `sec` test:

```ts
  && (a.step === undefined || (Number.isInteger(a.step) && (a.step as number) > 0))
```

In `frontend/src/workspace/crumbs.ts`, `CrumbContext` gains:

```ts
  /** With a design overview: its walk-throughs, each with its threads by name ("Thread A with Thread B"; spec 2026-11-02 §3.2). */
  walks?: { id: string; title: string; scope: string }[];
```

and `crumbs` gains, before `case "index":`:

```ts
    case "walk": {
      const w = c.walks?.find((x) => x.id === place.wid);
      if (!w) return [home, missing()];
      return [home, ...(w.scope ? [{ label: w.scope, to: c.base }] : []), { ...named(`Walk through: ${w.title}`), to: null }];
    }
```

- [ ] **Step 4: Run them to see them pass**

Run: `cd frontend && npx vitest run src/workspace/address.test.ts src/workspace/memory.test.ts src/workspace/crumbs.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing e2e test**

```ts
// path: frontend/e2e/walk-throughs.spec.ts
import { expect, type Page } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview, test } from "./helpers";

/** The design overview's walk-throughs (spec 2026-11-02 §3, §4, §18). CLs 101–104 have four: W1 takes `len > 64` from `main`
 * through `logger_flush` into `uart_send`, returns -2 to `logger_flush` (S1's flow 1) and reaches the reader `uart_errors`
 * (S1's flow 2), on the connection between Thread A and Thread B. */
const FOUR = "101 102 103 104";
const STEP5 = "Looks fine: step 5, uart_send returns -2 to logger_flush";

const steps = (page: Page) => page.locator(".dz-walk ol.fl-rows > li.fl-row");

test.describe("a walk-through's page", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("reads as a story does: its crumbs and head, then its steps, each saying where it comes from", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1`);
    await expect(page.locator(".ws-crumbs")).toHaveText(/ › Thread A with Thread B › Walk through: When len > 64$/);
    const head = page.locator(".dz-walk .st-head");
    await expect(head.locator("h2")).toHaveText("When len > 64");
    await expect(head.locator(".st-crumb")).toHaveText("Thread A with Thread B · 9 steps · over S1 · 2 open");
    await expect(head.locator(".dz-note")).toHaveText(/^Built from the stories' call paths and flows; the arrows are calls/);
    await expect(steps(page)).toHaveCount(9);
    await expect(steps(page).locator(".fl-one")).toHaveText([
      "main calls logger_flush(&g_log)", 'logger_flush calls uart_send(lg->uart, "\\n", 1)', "uart_send: len > 64",
      "uart_send writes Uart::errors: *err += 1", "uart_send returns -2 to logger_flush", "logger_flush returns to main",
      "main calls uart_errors(&g_uart)", "uart_errors reads Uart::errors: u->errors", "uart_errors returns u->errors to main"]);
    await expect(steps(page).locator(".dz-ref")).toHaveText([
      "call path of S1 flow 1 ›", "call path of S1 flow 1 ›", "S1 · the change ›", "S1 · the change ›", "S1 flow 1 ›",
      "logger_flush, unchanged", "main, unchanged", "S1 flow 2 ›", "uart_errors, unchanged"]);
    await expect(steps(page).locator(".fl-tick")).toHaveCount(2);                     // steps 5 and 8, the flows
    await expect(page.getByRole("region", { name: "Other walk-throughs" }).locator(".st-chip")).toHaveText([
      "▶ When len > 64 is false", "▶ From main through hal_write", "▶ From main through logger_init"]);
    await expectNoNodeIds(page);
    await expectNamed(page);
    await page.getByRole("link", { name: "Go to call path of S1 flow 1" }).first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?sec=paths$`));
  });

  test("marking a step fine marks its flow fine everywhere: the story's row, the walk-through's count and the head's", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1`);
    const progress = page.locator(".ws-progress"), crumb = page.locator(".dz-walk .st-crumb");
    await expect(progress).toHaveText("0 of 5 stories read · 4 checks open");
    await page.getByRole("checkbox", { name: STEP5 }).check();
    await expect(progress).toHaveText("0 of 5 stories read · 3 checks open");
    await expect(crumb).toHaveText(/ · 1 open$/);
    await page.getByRole("link", { name: "Go to S1 flow 1" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?flow=1$`));
    await expect(page.locator("#flow-1 .fl-tick")).toBeChecked();
    await page.goBack();
    await page.getByRole("checkbox", { name: STEP5 }).uncheck();
    await expect(progress).toHaveText("0 of 5 stories read · 4 checks open");
    await expect(crumb).toHaveText(/ · 2 open$/);
  });

  test("?step=N opens that step; a step or a walk-through the review does not have is no error", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1?step=8`);
    const row = page.locator("#step-8");
    await expect(row.locator(".fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(row.locator(".fl-path")).toHaveText(/^driver\/uart\.c:\d+$/);
    await expect(row.locator(".fl-check")).toHaveCount(1);                            // the reader row's check
    await page.goto(`${base}/walk/W1?step=99`);
    await expect(steps(page)).toHaveCount(9);
    await expect(page.locator(".dz-walk .fl-toggle[aria-expanded='true']")).toHaveCount(0);
    await page.goto(`${base}/walk/W9`);
    await expect(page.locator(".ws-centre .banner.warn")).toHaveText("This walk-through isn't in this review. Whole change");
  });

  test("J and K step through the steps and F marks the one with focus fine, then moves to the next still open", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1?step=4`);
    await expect(page.locator("#step-4 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await page.locator("#step-4 .fl-toggle").focus();
    await page.keyboard.press("j");
    await expect(page.locator("#step-5 .fl-toggle")).toBeFocused();
    await page.keyboard.press("f");
    await expect(page.locator("#step-5 .fl-tick")).toBeChecked();
    await expect(page.locator("#step-8 .fl-toggle")).toBeFocused();
    await page.keyboard.press("k");
    await expect(page.locator("#step-7 .fl-toggle")).toBeFocused();
  });
});
```

- [ ] **Step 6: Run it to see it fail**

Run (from `frontend/`): `npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/walk-throughs.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: FAIL, 4 of 4: the crumbs read "… › Not found" and the centre shows "This page isn't in this review."

- [ ] **Step 7: Factor the marks out of the Flows tab, and give the row keys a start and a row id**

```ts
// path: frontend/src/workspace/useMarks.ts
import { useState } from "react";
import { api, errorText } from "../api";
import { useWs } from "./context";

/** Marking checks fine for everyone and reopening them (spec 2026-10-25-review-ui-redesign §7.3), as a Flows row's tick
 * box and a walk-through step's do (spec 2026-11-02 §4.3): one at a time, each reloading the reading and the reader's ticks.
 * Each settles to whether the change landed and never rejects, so F says "Marked fine" only for a mark that did; a refusal's
 * words are in `error`, and one that comes without words says what the reader was doing. */
export default function useMarks() {
  const d = useWs().data;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = (act: () => Promise<unknown>, failed: string): Promise<boolean> => {
    if (busy) return Promise.resolve(false);                                   // one mark at a time; the tick boxes stay enabled, so they keep their focus
    setBusy(true);
    setError(null);
    return act().then(() => Promise.all([d.loadReading(), d.loadTicks().catch(() => {})])).then(() => true)
      .catch((e) => { setError(errorText(e, failed)); return false; }).finally(() => setBusy(false));
  };
  const fine = (keys: string[]) => run(() => api.markChecks(d.id, keys), "The server did not accept the mark.");
  const reopen = (keys: string[]) => run(() => api.unmarkChecks(d.id, keys),   // all of them or none, so a refusal leaves the row as it was
                                         "The server did not reopen these checks.");
  return { busy, error, fine, reopen };
}
```

In `frontend/src/workspace/FlowsTab.tsx`: delete the lines from `const [busy, setBusy] = useState(false);` through the
`reopen` definition (the comment above `run` goes with them), put `const { busy, error, fine, reopen } = useMarks();` in
their place, add `import useMarks from "./useMarks";`, and drop `import { api, errorText } from "../api";`.

In `frontend/src/workspace/useRowKeys.ts`: delete the module-level `focusRow` and its comment; the hook's signature and
first lines become:

```ts
export default function useRowKeys({ order, busy, leftAt, fine, start, prefix = "flow" }: {
  order: number[]; busy: boolean; leftAt: (n: number) => string[]; fine: (keys: string[]) => Promise<boolean>;
  /** The row J, K and F start from; the address's flow unless given. */
  start?: number | null;
  /** The rows' id before their number: "flow" for `#flow-3` (the Flows tab), "step" for `#step-3` (a walk-through). */
  prefix?: string;
}) {
  const ws = useWs();
  const [cur, setCur] = useState<number | null>(start === undefined ? ws.addr.flow : start);
  /** Puts focus on row `n`'s toggle, the button that opens it. */
  const focusRow = (n: number) => document.querySelector<HTMLElement>(`#${prefix}-${n} .fl-toggle`)?.focus();
```

and the doc comment above it says "The Flows tab's and a walk-through's row keys" where it said "The Flows tab's row
keys".

- [ ] **Step 8: Write the page**

```tsx
// path: frontend/src/workspace/WalkPage.tsx
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import AiText, { AiName } from "../components/AiText";
import { placeOpen } from "../reading/causes";
import { type StepRef, stepKeys, stepRef, stepSentence, threadName, walkOpen, walkThreads } from "../reading/walks";
import { at } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import NameText, { Ticks } from "./NameText";
import { bare } from "./names";
import useMarks from "./useMarks";
import useRowKeys from "./useRowKeys";

/** A walk-through (spec 2026-11-02-design-overview §3.2): a story's header (its title; a crumb of its threads, its steps,
 * the stories it is built from and its open count; the lead; how it was built), then its steps as rows that open in place,
 * each saying where it comes from. A flow's step has that flow's tick box, which marks its checks fine for everyone as the
 * Flows tab's does (§4.3). `step=N` opens row N. Then the review's other walk-throughs. J, K, F and Enter step through the
 * rows as on the Flows tab. */
export default function WalkPage({ wid }: { wid: string }) {
  const ws = useWs(), d = ws.data, r = d.reading!, design = r.design!, w = design.walks.find((x) => x.id === wid)!;
  const { nodes } = design, { names } = d, marks = r.marks;
  const label = useMemo(() => (n: string) => nodes[n]?.label ?? names[n]?.label ?? "a function", [nodes, names]);
  const checks = useMemo(() => new Map(r.checks.map((k) => [k.key, k])), [r.checks]);
  const order = useMemo(() => w.steps.map((_, i) => i + 1), [w.steps]);
  const leftAt = (n: number) => stepKeys(w.steps[n - 1], checks, ws.hidden).filter((k) => placeOpen(k, marks));
  const lit = ws.addr.step && ws.addr.step <= w.steps.length ? ws.addr.step : null;   // a step it does not have opens none
  const [open, setOpen] = useState<number | null>(lit);
  const { busy, error, fine, reopen } = useMarks();
  const { setCur, move, focusRow, said } = useRowKeys({ order, busy, leftAt, fine, start: lit, prefix: "step" });
  // the address's step opens and comes into view once each time it changes, as the Flows tab's flow does
  const named = useRef<number | null | undefined>(undefined);
  const show = (n: number) => { setOpen(n); setCur(n); document.getElementById(`step-${n}`)?.scrollIntoView({ block: "start" }); };
  useEffect(() => {
    if (lit && lit !== named.current) show(lit);
    named.current = lit;
  }, [lit]);                                                                   // eslint-disable-line react-hooks/exhaustive-deps
  const nextStep = (n: number) => {
    const to = order[order.indexOf(n) + 1];
    setOpen(to ?? null);
    move(to ?? n);
  };
  const drawn = ws.screen !== "phone";                                         // a phone has the rows only (§4.4)
  const threads = walkThreads(w).flatMap((tid) => {
    const name = threadName(r.threads, tid);
    return name ? [name] : [];
  });
  const titleOf = (sid: string) => d.stories?.stories.find((s) => s.id === sid)?.title ?? sid;
  const refTo = (l: NonNullable<StepRef["link"]>) =>
    ws.link(at({ kind: "story", sid: l.story, view: "steps" }, { flow: l.flow, ...(l.sec ? { sec: l.sec } : {}) }));
  const openN = walkOpen(w, checks, ws.hidden, marks), others = design.walks.filter((x) => x.id !== w.id);
  return (
    <div className="ws-page"><div className="st-page dz-walk">
      <header className="ws-story-head st-head">
        <h2><AiName ai={w.title_source === "llm"}><Ticks text={w.title} /></AiName></h2>
        <p className="st-crumb">
          {threads.map((name, i) => (
            <Fragment key={name}>{i > 0 && " with "}
              <Link to={ws.link(at({ kind: "whole" }))} state={{ page: true }} title={`Go to ${name.replace("Thread", "thread")} on the overview`}
                    aria-label={`Go to ${name.replace("Thread", "thread")} on the overview`}>{name}</Link></Fragment>
          ))}
          {threads.length > 0 && " · "}{w.steps.length} step{w.steps.length === 1 ? "" : "s"}
          {w.stories.length > 0 && <> · over {w.stories.map((sid, i) => (
            <Fragment key={sid}>{i > 0 && ", "}
              <Link to={ws.link(ws.item({ kind: "story", sid, view: "steps" }))} title={bare(titleOf(sid))}
                    aria-label={`Go to story ${sid}: ${short(titleOf(sid))}`}>{sid}</Link></Fragment>
          ))}</>}
          {openN > 0 && <> · {openN} open</>}
        </p>
        <div className="st-summary">
          {w.lead && <AiText ai={w.title_source === "llm"}><NameText text={w.lead} /></AiText>}
          <p className="dz-note">Built from the stories' call paths and flows{drawn ? "; the arrows are calls (solid) and returns (dashed)" : ""}.
            Its checks are the stories' checks: marking a step fine marks that flow fine.</p>
        </div>
      </header>
      <div className="st-flows dz-steps" aria-busy={busy}>
        <div className="vh" aria-live="polite">{said}</div>
        {error && <div className="banner warn" role="alert">{error}</div>}
        <ol className="fl-rows">{w.steps.map((st, i) => {
          const n = i + 1, keys = stepKeys(st, checks, ws.hidden), left = keys.filter((k) => placeOpen(k, marks));
          const done = keys.length > 0 && !left.length, on = open === n, sentence = stepSentence(st, label), ref = stepRef(st, label);
          return (
            <li key={n} id={`step-${n}`} className={`fl-row dz-step ${st.status}${on ? " on" : ""}`} onFocus={() => setCur(n)}>
              <div className="fl-head">
                {keys.length > 0 && <label className="fl-tickbox"><input type="checkbox" className="fl-tick" checked={done}
                                           aria-label={`Looks fine: step ${n}, ${bare(sentence)}`}
                                           onChange={() => { setCur(n); if (done) reopen(keys); else fine(left); }} /></label>}
                <button className="fl-toggle" aria-expanded={on} title={bare(sentence)} aria-label={`Step ${n}: ${bare(sentence)}`}
                        onClick={() => { setOpen(on ? null : n); setCur(n); }}>
                  <span className="fl-n">{n}</span><span className="fl-one"><Ticks text={sentence} /></span>
                </button>
                <span className="dz-ref">{ref.link
                  ? <Link to={refTo(ref.link)} title={`Go to ${bare(ref.text)}`} aria-label={`Go to ${bare(ref.text)}`}><Ticks text={ref.text} /> ›</Link>
                  : <Ticks text={ref.text} />}</span>
              </div>
              {on && (
                <div className="fl-body" role="region" aria-label={`Step ${n}: ${bare(sentence)}`}>
                  {st.path && <p className="fl-path mono">{st.path}{st.line ? `:${st.line}` : ""}{st.cl !== null && <> · <Link
                    to={ws.link(ws.item({ kind: "cl", cl: st.cl }))} title={`Open CL ${st.cl}`} aria-label={`Open CL ${st.cl}`}>CL {st.cl}</Link></>}</p>}
                  {st.loop && <p className="dz-loop">Inside <code>{st.loop}</code></p>}
                  {keys.map((k) => <p key={k} className="fl-check"><NameText text={checks.get(k)!.text} /></p>)}
                  <div className="fl-acts">
                    {left.length > 0 && <button onClick={() => { fine(left); focusRow(n); }} disabled={busy}>Looks fine</button>}
                    {done && <button className="link" onClick={() => { reopen(keys); focusRow(n); }} disabled={busy}>Reopen</button>}
                    <button className="link" onClick={() => nextStep(n)}>Next step ›</button>
                  </div>
                </div>
              )}
            </li>
          );
        })}</ol>
      </div>
      {others.length > 0 && (
        <section className="st-other" aria-label="Other walk-throughs"><h3>Other walk-throughs</h3>
          <ul className="st-chips">{others.map((o) => (
            <li key={o.id}><Link className="st-chip walk" to={ws.link(ws.item({ kind: "walk", wid: o.id }))}
                                 title={`Walk through: ${bare(o.title)}`} aria-label={`Walk through: ${bare(o.title)}`}>
              <span aria-hidden>▶ </span><Ticks text={o.title} /></Link></li>
          ))}</ul>
        </section>
      )}
    </div></div>
  );
}
```

Note: `.fl-path`'s text in the e2e test is `driver/uart.c:N` only when the step has no CL; step 8 (the reader, unchanged)
has none. A step with a CL reads `driver/uart.c:16 · CL 101`.

- [ ] **Step 9: Route the place in the workspace**

In `frontend/src/workspace/Workspace.tsx`:

- import `WalkPage from "./WalkPage"` and `{ walkScope } from "../reading/walks"`;
- after the `threadOf` line add
  `const walks = useMemo(() => r?.design?.walks.map((w) => ({ id: w.id, title: w.title, scope: walkScope(w, r.threads) })), [r]);`
  and pass `walks` in the `crumbs(…)` context (after `threadOf`), adding `walks` to that memo's dependencies;
- in `Centre`, the `exists` test gains `|| (p.kind === "walk" && !!r?.design?.walks.some((w) => w.id === p.wid))`, and
  after the story line add `if (p.kind === "walk") return <WalkPage key={p.wid} wid={p.wid} />;`
- `loadedFor` gains, first: `if (p.kind === "walk") return d.stories !== undefined;   // its crumb and chips name stories`
- `Missing` names it: `… : what.kind === "walk" ? "This walk-through" : "This page"`.

- [ ] **Step 10: Style it**

Append to `frontend/src/workspace/workspace.css`:

```css
/* a walk-through's page (spec 2026-11-02-design-overview §3.2): a story's header and the Flows tab's rows, each row ending in
   where its step comes from */
.dz-note { margin: 6px 0 0; font-size: 13px; color: var(--muted); }
.dz-ref { flex: none; max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 8px;
  font-size: 12.5px; color: var(--muted); }
.dz-ref a { text-decoration: none; }
.dz-loop { font-size: 13px; color: var(--muted); }
.dz-loop code { overflow-wrap: anywhere; }
@media (max-width: 640px) {
  /* a phone's row: where the step comes from goes under its line, so the line keeps the width */
  .dz-step .fl-head { flex-wrap: wrap; }
  .dz-ref { max-width: none; flex-basis: 100%; padding: 0 0 6px 40px; }
}
```

- [ ] **Step 11: Run the unit tests, the type check and the e2e test**

Run: `cd frontend && npx vitest run && npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/walk-throughs.spec.ts e2e/flow-groups.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: vitest all pass; the build is clean; Playwright passes the 4 walk-through tests and every Flows tab test
(`flow-groups.spec.ts`: the marks and keys now come through `useMarks` and the reworked `useRowKeys`).

- [ ] **Step 12: Commit**

```bash
git add frontend/src/workspace/address.ts frontend/src/workspace/address.test.ts frontend/src/workspace/memory.ts frontend/src/workspace/memory.test.ts frontend/src/workspace/crumbs.ts frontend/src/workspace/crumbs.test.ts frontend/src/workspace/Workspace.tsx frontend/src/workspace/useRowKeys.ts frontend/src/workspace/FlowsTab.tsx frontend/src/workspace/useMarks.ts frontend/src/workspace/WalkPage.tsx frontend/src/workspace/workspace.css frontend/e2e/walk-throughs.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: a walk-through's page at /walk/W1: its crumbs, head and steps, each step's tick box marking its flow fine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 8: The sequence drawing

**Files:**
- Modify: `frontend/src/reading/walks.ts` (append the layout), `frontend/src/workspace/WalkPage.tsx`,
  `frontend/src/workspace/workspace.css`, `frontend/e2e/walk-throughs.spec.ts`
- Create: `frontend/src/workspace/WalkDrawing.tsx`
- Test: `frontend/src/reading/walks.test.ts`, `frontend/e2e/walk-throughs.spec.ts`

**Interfaces:**
- Consumes: Task 6's `openSteps`, `Walk`, `WalkStep`, `DesignNode.component`; Task 7's `WalkPage` (`drawn`, `show`,
  `focusRow`, `label`, `checks`, `marks`).
- Produces: `COL, LEFT, TOP, ROW, PAD, FRAME, CH`; `DrawCol`, `DrawRow`, `DrawFrame`, `WalkLayout`;
  `walkLayout(w, label, component) -> WalkLayout`; `WalkDrawing({ walk, label, component, open, onPick })` as
  `figure.dz-draw` > `.dz-scroll` > `svg[role=img]` with `.dz-fn`, `.dz-comp`, `g.dz-row.<status>.<line>`, `.dz-num(.open)`,
  and `.dz-legend .dz-key`.

- [ ] **Step 1: Write the failing unit test**

Append to `frontend/src/reading/walks.test.ts` (and add `CH, COL, FRAME, LEFT, PAD, ROW, TOP, walkLayout` to its import from
`./walks`):

```ts
describe("the drawing's layout (§4.4)", () => {
  const loop = "for (i = 0; i < len; i++)";
  const w = walk({ parts: ["N1", "N2", "N3"], steps: [
    step({ src: "N1", dst: "N2", label: "logger_flush(&g_log)" }),
    step({ kind: "self", src: "N3", dst: "N3", label: "len > 64", status: "new", loop }),
    step({ kind: "write", src: "N3", dst: "F1", label: "*err += 1", status: "new", loop }),
    step({ kind: "return", src: "N3", dst: "N2", label: "-2", status: "new" }),
    step({ kind: "read", src: "F1", dst: "N4", label: "u->errors" }),
    step({ kind: "fold", src: "N1", dst: "N3", folded: 3 }),
    step({ src: "N2", dst: "N2", label: "flush_again()", status: "changed" })] });
  const lay = walkLayout(w, label, (n) => (n === "N1" ? "app" : n === "N4" ? null : "driver"));

  it("gives each function a column, left to right, and one a step names that the parts miss a column at the end", () => {
    expect(lay.cols.map((c) => [c.label, c.component, c.x])).toEqual([
      ["main", "app", 143], ["logger_flush", "driver", 333], ["uart_send", "driver", 523], ["uart_errors", "", 713]]);
    expect(lay.width).toBe(LEFT + 4 * COL + COL / 2);
    expect(lay.height).toBe(TOP + 7 * ROW + FRAME + PAD);                              // one frame's label takes a band of its own
  });

  it("draws calls solid, returns dashed and folds dotted, and a step inside one function as a loop on its column", () => {
    expect(lay.rows.map((r) => [r.n, r.x1, r.x2, r.loop, r.line, r.status])).toEqual([
      [1, 143, 333, false, "solid", "same"], [2, 523, 523, true, "solid", "new"], [3, 523, 523, true, "solid", "new"],
      [4, 523, 333, false, "dashed", "new"], [5, 713, 713, true, "solid", "same"], [6, 143, 523, false, "dotted", "same"],
      [7, 333, 333, true, "solid", "changed"]]);
    expect(lay.rows.map((r) => r.y)).toEqual([74, 128, 164, 200, 236, 272, 308]);
    expect(lay.rows.map((r) => r.text)).toEqual(["logger_flush(&g_log)", "len > 64", "*err += 1", "-2", "u->errors", "… 3 calls",
                                                 "flush_again()"]);
  });

  it("frames the steps inside one loop of the code, and cuts what does not fit, keeping the whole for its title", () => {
    expect(lay.frames.map((f) => [f.x1, f.x2, f.y1, f.y2, f.full])).toEqual([[438, 608, 90, 176, loop]]);
    expect(lay.frames[0].text).toBe("loop · for (i = 0; i…");
    const long = walkLayout(walk({ parts: ["N1", "N2"], steps: [step({ src: "N1", dst: "N2", label: "x".repeat(80) })] }), label, () => null);
    expect(long.rows[0].text).toHaveLength(Math.floor((COL - 16) / CH));
    expect(long.rows[0].text.endsWith("…")).toBe(true);
    expect(long.rows[0].full).toBe("x".repeat(80));
    expect(long.frames).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx vitest run src/reading/walks.test.ts`
Expected: FAIL: `walkLayout is not a function` (and the constants undefined).

- [ ] **Step 3: Write the layout**

Append to `frontend/src/reading/walks.ts`:

```ts
/** The drawing's measures in px (§4.4): a column's width, the room left of the first column for the step numbers, the
 * header's height, a step's row, the margin under the last row, the band a loop's frame takes for its label, and a
 * character's width at the drawing's 12px monospace. */
export const COL = 190, LEFT = 48, TOP = 52, ROW = 36, PAD = 20, FRAME = 18, CH = 7.2;

export interface DrawCol { node: string; x: number; label: string; full: string; component: string }
/** A step's arrow from `x1` to `x2` at `y`, or a loop on `x1` (`x2` the same); `text` is its label cut to fit, `full` the whole. */
export interface DrawRow {
  n: number; y: number; x1: number; x2: number; loop: boolean; line: "solid" | "dashed" | "dotted"; status: WalkStep["status"];
  text: string; full: string;
}
/** A frame around the steps inside one loop of the code, its label in a band above its first step. */
export interface DrawFrame { x1: number; x2: number; y1: number; y2: number; text: string; full: string }
export interface WalkLayout { width: number; height: number; cols: DrawCol[]; rows: DrawRow[]; frames: DrawFrame[] }

const cut = (text: string, n: number) => (text.length <= n ? text : `${text.slice(0, Math.max(1, n - 1))}…`);

/** A step's ends in the drawing: a write sits on its writer and a read on its reader, for a field is no column. */
const ends = (st: WalkStep): [string, string] =>
  st.kind === "write" ? [st.src, st.src] : st.kind === "read" ? [st.dst, st.dst] : [st.src, st.dst];

/** The sequence drawing's layout (§4.4): a column per function, left to right as `parts` lists them (one a step names that
 * `parts` misses goes last), labelled with its component; a row per step. A call is solid, a return dashed and a fold
 * dotted, from one function's column to the other's; a step inside one function (a self step, a write, a read, a call to
 * itself) is a loop on its column. The runs of steps inside one loop of the code are framed. */
export function walkLayout(w: Pick<Walk, "parts" | "steps">, label: Label, component: (n: string) => string | null): WalkLayout {
  const cols: string[] = [...w.parts];
  for (const st of w.steps) for (const n of ends(st)) if (!cols.includes(n)) cols.push(n);
  const x = (n: string) => LEFT + cols.indexOf(n) * COL + COL / 2;
  const width = LEFT + cols.length * COL + COL / 2;                            // half a column more, for a loop's label on the last column
  const rows: DrawRow[] = [], frames: DrawFrame[] = [];
  let y = TOP, open: { first: number; top: number; loop: string } | null = null;
  const close = (bottom: number) => {
    if (!open) return;
    const xs = rows.slice(open.first).flatMap((r) => [r.x1, r.x2]);
    const x1 = Math.max(4, Math.min(...xs) - COL / 2 + 10), x2 = Math.min(width - 4, Math.max(...xs) + COL / 2 - 10);
    frames.push({ x1, x2, y1: open.top + 2, y2: bottom - 2, text: cut(`loop · ${open.loop}`, Math.floor((x2 - x1 - 12) / CH)), full: open.loop });
    open = null;
  };
  w.steps.forEach((st, i) => {
    if (open && st.loop !== open.loop) close(y);
    if (st.loop && !open) { open = { first: i, top: y, loop: st.loop }; y += FRAME; }
    const [a, b] = ends(st), loop = a === b, x1 = x(a), x2 = x(b);
    const said = st.kind === "fold" ? `… ${st.folded} call${st.folded === 1 ? "" : "s"}` : st.label;
    const room = Math.floor(((loop ? COL - 24 : Math.abs(x2 - x1)) - 16) / CH);
    rows.push({ n: i + 1, y: y + ROW / 2 + 4, x1, x2, loop, status: st.status, text: cut(said, room), full: said,
                line: st.kind === "return" ? "dashed" : st.kind === "fold" ? "dotted" : "solid" });
    y += ROW;
  });
  close(y);
  return { width, height: y + PAD, rows, frames,
           cols: cols.map((n) => ({ node: n, x: x(n), label: cut(label(n), Math.floor((COL - 12) / CH)), full: label(n),
                                    component: component(n) ?? "" })) };
}
```

- [ ] **Step 4: Run it to see it pass**

Run: `cd frontend && npx vitest run src/reading/walks.test.ts`
Expected: PASS (12 tests).

- [ ] **Step 5: Write the failing e2e tests**

In `frontend/e2e/walk-throughs.spec.ts`, import `devices` from `@playwright/test` and `sideways` from `./helpers`, and
append:

```ts
test.describe("a walk-through's drawing", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("draws a column per function under its component and a row per step; clicking a step opens its row", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1`);
    const draw = page.locator(".dz-draw svg");
    await expect(draw).toHaveAttribute("role", "img");
    await expect(draw.locator(".dz-fn")).toHaveText(["main", "logger_flush", "uart_send", "uart_errors"]);
    await expect(draw.locator(".dz-comp")).toHaveText(["app", "service", "driver", "driver"]);
    await expect(draw.locator(".dz-row")).toHaveCount(9);
    await expect(draw.locator(".dz-row.new")).toHaveCount(3);                         // len > 64, *err += 1, return -2
    await expect(draw.locator(".dz-row.dashed")).toHaveCount(3);                      // the returns
    await expect(draw.locator(".dz-num.open")).toHaveCount(2);                        // steps 5 and 8
    await expect(page.locator(".dz-legend .dz-key")).toHaveText(["new in the change", "changed", "unchanged", "a step with an open check"]);
    await draw.locator(".dz-row").nth(7).click();
    await expect(page.locator("#step-8 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#step-8 .fl-toggle")).toBeFocused();
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});

test.describe("a walk-through on a phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
             deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("is its steps, with no drawing, and nothing scrolls sideways", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1`);
    await expect(page.locator(".ws-phonebar")).toHaveText(/^‹ Thread A with Thread B\s*·\s*Walk through: When len > 64$/);
    await expect(steps(page)).toHaveCount(9);
    await expect(page.locator(".dz-draw")).toHaveCount(0);
    await expect(page.locator(".dz-note")).toHaveText(/^Built from the stories' call paths and flows\. Its checks/);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});
```

- [ ] **Step 6: Run them to see them fail**

Run (from `frontend/`): `npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/walk-throughs.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: the drawing test FAILS (no `.dz-draw svg`); the phone test passes already (Task 7 drew nothing anywhere), and
the four Task 7 tests pass.

- [ ] **Step 7: Write the drawing and put it on the page**

```tsx
// path: frontend/src/workspace/WalkDrawing.tsx
import type { Walk } from "../reading/types";
import { PAD, ROW, TOP, walkLayout } from "../reading/walks";

/** An arrow's head: a triangle with its point at (x, y), pointing right (`dir` 1) or left (-1). */
const head = (x: number, y: number, dir: 1 | -1) => `${x},${y} ${x - 7 * dir},${y - 4} ${x - 7 * dir},${y + 4}`;

/** A walk-through's sequence drawing (spec 2026-11-02-design-overview §4.4): an SVG in the board's colours, a column per
 * function under its component and a numbered row per step, in its own box that scrolls sideways when it is wider than the
 * page. The rows under it are the walk-through for the keyboard and for screen readers, so to them it is one image; a click
 * on a step opens its row. */
export default function WalkDrawing({ walk, label, component, open, onPick }: {
  walk: Walk; label: (n: string) => string; component: (n: string) => string | null; open: ReadonlySet<number>;
  onPick: (n: number) => void;
}) {
  const lay = walkLayout(walk, label, component);
  return (
    <figure className="dz-draw">
      <div className="dz-scroll">
        <svg role="img" aria-label={`The ${walk.steps.length} steps drawn in sequence; they are listed below`}
             width={lay.width} height={lay.height} viewBox={`0 0 ${lay.width} ${lay.height}`}>
          {lay.frames.map((f) => (
            <g key={f.y1} className="dz-frame">
              <rect x={f.x1} y={f.y1} width={f.x2 - f.x1} height={f.y2 - f.y1} rx={6} />
              <text x={f.x1 + 6} y={f.y1 + 12}>{f.text}<title>{f.full}</title></text>
            </g>
          ))}
          {lay.cols.map((c) => (
            <g key={c.node} className="dz-col">
              <text className="dz-fn" x={c.x} y={20} textAnchor="middle">{c.label}<title>{c.full}</title></text>
              {c.component && <text className="dz-comp" x={c.x} y={36} textAnchor="middle">{c.component}</text>}
              <line x1={c.x} y1={TOP - 8} x2={c.x} y2={lay.height - PAD / 2} />
            </g>
          ))}
          {lay.rows.map((r) => {
            const dir = r.x2 >= r.x1 ? 1 : -1, said = <>{r.text}{r.text !== r.full && <title>{r.full}</title>}</>;
            return (
              <g key={r.n} className={`dz-row ${r.status} ${r.line}`} onClick={() => onPick(r.n)}>
                <rect className="dz-hit" x={0} y={r.y - ROW / 2 - 4} width={lay.width} height={ROW} />
                <circle className={`dz-num${open.has(r.n) ? " open" : ""}`} cx={22} cy={r.y} r={10} />
                <text className="dz-numt" x={22} y={r.y + 4} textAnchor="middle">{r.n}</text>
                {r.loop ? <>
                  <path className="dz-line" d={`M ${r.x1} ${r.y - 6} h 26 v 12 h -18`} />
                  <polygon className="dz-head" points={head(r.x1 + 1, r.y + 6, -1)} />
                  <text className="dz-say" x={r.x1 + 32} y={r.y + 4}>{said}</text>
                </> : <>
                  <line className="dz-line" x1={r.x1} y1={r.y} x2={r.x2 - 6 * dir} y2={r.y} />
                  <polygon className="dz-head" points={head(r.x2, r.y, dir)} />
                  <text className="dz-say" x={(r.x1 + r.x2) / 2} y={r.y - 6} textAnchor="middle">{said}</text>
                </>}
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="dz-legend">
        <span className="dz-key new">new in the change</span>
        <span className="dz-key changed">changed</span>
        <span className="dz-key same">unchanged</span>
        <span className="dz-key open">a step with an open check</span>
      </figcaption>
    </figure>
  );
}
```

In `frontend/src/workspace/WalkPage.tsx`: import `WalkDrawing from "./WalkDrawing"` and add `openSteps` to the import from
`../reading/walks`; between `</header>` and `<div className="st-flows dz-steps" …>` put:

```tsx
      {drawn && <WalkDrawing walk={w} label={label} component={(n) => nodes[n]?.component ?? null}
                             open={openSteps(w, checks, ws.hidden, marks)} onPick={(n) => { show(n); focusRow(n); }} />}
```

- [ ] **Step 8: Style it**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the walk-through's drawing (spec 2026-11-02-design-overview §4.4): the board's colours, in both themes; it scrolls sideways
   in its own box. Unchanged lines are --bd-muted, not --bd-arrow, which is about 2:1 on white (§18.7). */
.dz-draw { margin: 14px 0 10px; }
.dz-scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--bd-surface); }
.dz-scroll svg { display: block; font: 12px var(--bd-mono); }
.dz-fn { font-weight: 700; fill: var(--bd-ink); }
.dz-comp { font: 11px var(--bd-sans); fill: var(--bd-muted); }
.dz-col line { stroke: var(--bd-line); stroke-dasharray: 3 4; }
.dz-row { cursor: pointer; }
.dz-hit { fill: transparent; }
.dz-row:hover .dz-hit { fill: var(--bd-hover); }
.dz-line { fill: none; stroke-width: 1.6; }
.dz-row.dashed .dz-line { stroke-dasharray: 6 4; }
.dz-row.dotted .dz-line { stroke-dasharray: 1.5 4; }
.dz-row.new .dz-line { stroke: var(--add-ink); }
.dz-row.new .dz-head { fill: var(--add-ink); }
.dz-row.changed .dz-line { stroke: var(--chg-deep); }
.dz-row.changed .dz-head { fill: var(--chg-deep); }
.dz-row.same .dz-line { stroke: var(--bd-muted); }
.dz-row.same .dz-head { fill: var(--bd-muted); }
.dz-say { fill: var(--bd-ink); }
.dz-num { fill: var(--bd-surface); stroke: var(--bd-muted); }
.dz-num.open { fill: var(--fx-deep); stroke: var(--fx-deep); }
.dz-numt { font: 600 11px var(--bd-sans); fill: var(--bd-ink); pointer-events: none; }
.dz-num.open + .dz-numt { fill: #fff; }
.dz-frame rect { fill: none; stroke: var(--bd-muted); stroke-dasharray: 4 3; }
.dz-frame text { font: 600 11px var(--bd-sans); fill: var(--bd-muted); }
.dz-legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 6px; font-size: 12px; color: var(--muted); }
.dz-key::before { content: ""; display: inline-block; width: 18px; margin-right: 6px; vertical-align: middle; border-top: 2px solid; }
.dz-key.new::before { border-color: var(--add-ink); }
.dz-key.changed::before { border-color: var(--chg-deep); }
.dz-key.same::before { border-color: var(--bd-muted); }
.dz-key.open::before { width: 10px; height: 10px; border: 0; border-radius: 50%; background: var(--fx-deep); }
```

- [ ] **Step 9: Run the unit tests and the e2e tests**

Run (from `frontend/`): `npx vitest run && npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/walk-throughs.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: vitest all pass; Playwright 6 passed.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/reading/walks.ts frontend/src/reading/walks.test.ts frontend/src/workspace/WalkDrawing.tsx frontend/src/workspace/WalkPage.tsx frontend/src/workspace/workspace.css frontend/e2e/walk-throughs.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: a walk-through's sequence drawing, a click on a step opening its row; none on a phone

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 9: The overview: Where the change sits, the walk lines and links, the condition fold

**Files:**
- Modify: `frontend/src/reading/overview.ts`, `frontend/src/workspace/Overview.tsx`, `frontend/src/workspace/workspace.css`,
  `frontend/e2e/helpers.ts`, `frontend/e2e/workspace.spec.ts`, `frontend/e2e/workspace-reading.spec.ts`,
  `frontend/e2e/outline-causes.spec.ts`, `frontend/e2e/thread-sections.spec.ts`, `frontend/e2e/workspace-pages.spec.ts`,
  `frontend/e2e/walk-throughs.spec.ts`
- Test: `frontend/src/reading/overview.test.ts`, `frontend/e2e/walk-throughs.spec.ts`

**Interfaces:**
- Consumes: Task 6's `showsWhere`, `componentBands`, `blockLine`, `alsoLine`, `foldGate`, `conditionTitle`, `gateGroups`,
  `connectionWalk`; Task 7's walk place.
- Produces: `SectionLink` gains `a` (the earlier thread's id) and `b` (the later one's); on the overview
  `section.dz-where` (named "Where the change sits") with `.ov-band` > `.dz-block(.quiet)` > `.nm`, `.ct`, `.ln`, `.also`;
  `ul.dz-walks` in a thread's section; `a.dz-cwalk` at the end of a connection line; a `Fold` named "When the condition is
  false" holding `h3` "Still runs (N)" / "Stops (M)" and `ul.dz-gated`; `openFold` accepts that name.

- [ ] **Step 1: Write the failing unit test**

In `frontend/src/reading/overview.test.ts`, the rows of the first two tests of
`describe("how the threads connect, under the later thread (§5.2)", …)` name their two threads. The first test's
expectation becomes:

```ts
    expect([...rows.entries()]).toEqual([
      ["T2", [{ before: "With Thread A: ", text: "both run inside `main`", after: "", ai: false, bundled: false, a: "T1", b: "T2" }]],
      ["T4", [{ before: "With Thread B: ", text: "nothing besides arriving in CL 104", after: " — ask the author", ai: false, bundled: true,
                a: "T2", b: "T4" }]],
      ["T3", [{ before: "With Thread A: ", text: "both use `hal_write`", after: "", ai: false, bundled: false, a: "T1", b: "T3" }]],
    ]);
```

and the second's:

```ts
    expect([...rows.entries()]).toEqual([
      ["T4", [{ before: "With Thread B: ", text: "nothing besides arriving in CL 104", after: " — ask the author", ai: false, bundled: true,
                a: "T2", b: "T4" },
              { before: "With Thread C: ", text: "both use `hal_write`", after: "", ai: false, bundled: false, a: "T3", b: "T4" }]],
      ["T3", [{ before: "With Thread A: ", text: "both run inside `main`", after: "", ai: false, bundled: false, a: "T1", b: "T3" }]],
    ]);
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx vitest run src/reading/overview.test.ts`
Expected: FAIL, 2 tests: the rows have no `a` or `b`.

- [ ] **Step 3: Name the threads of a connection line**

In `frontend/src/reading/overview.ts`, `SectionLink` becomes:

```ts
/** One line of how the threads connect: the connection's `text` between what the app adds around it (`before` names the
 * earlier thread, `after` says a bundled pair is the author's to explain). `ai`: the strong model reworded the text, and only
 * the text is its words. `a` and `b` are the earlier and the later thread's ids: a walk-through on their connection is linked
 * at the line's end (spec 2026-11-02 §3.1). */
export interface SectionLink { before: string; text: string; after: string; ai: boolean; bundled: boolean; a: string; b: string }
```

and in `sectionConnections` the row gains them: `ai: k.text_source === "llm", bundled, a: threads[early].id, b: late };`

Run: `cd frontend && npx vitest run src/reading/overview.test.ts`
Expected: PASS.

- [ ] **Step 4: Write the failing e2e tests, and the overview's new rows in the specs that list them**

Append to `frontend/e2e/walk-throughs.spec.ts` (add `openFold` to its import from `./helpers`):

```ts
test.describe("the overview", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("says where the change sits, layer by layer; a component that shares nothing with the rest is dashed", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(base);
    const where = page.getByRole("region", { name: "Where the change sits" });
    await expect(where.locator(".ov-band h3")).toHaveText(["service", "driver", "hal", "cpp, include/hal"]);
    await expect(where.locator(".dz-block .nm")).toHaveText(["service", "driver", "hal", "cpp", "include/hal"]);
    const driver = where.locator(".dz-block").filter({ has: page.locator(".nm", { hasText: /^driver$/ }) });
    await expect(driver.locator(".ct")).toHaveText("Thread A · 2 changed files");
    await expect(driver.locator(".ln")).toHaveText(["uart_init, uart_send call hal_write"]);
    await expect(where.locator(".dz-block.quiet .nm")).toHaveText(["cpp"]);
    await expect(where.locator(".dz-block.quiet .ln")).toHaveText("No calls or fields shared with the rest");
    await expectNoNodeIds(page);
  });

  test("lists a thread's walk-throughs under its stories, and links the one on a connection at the end of its line", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(base);
    const secs = page.locator("section.ov-sec");
    await expect(secs.nth(0).locator(".dz-walks li")).toHaveText(["▶ Walk through: When len > 64 ›",
      "▶ Walk through: When len > 64 is false ›", "▶ Walk through: From main through hal_write ›"]);
    await expect(secs.nth(1).locator(".dz-walks li")).toHaveText(["▶ Walk through: From main through logger_init ›"]);
    await expect(secs.nth(2).locator(".dz-walks")).toHaveCount(0);
    await expect(secs.nth(1).locator(".ov-links li")).toHaveText(["With Thread A: both run inside main · ▶ Walk through ›"]);
    await expect(secs.nth(2).locator(".ov-links li")).toHaveText(["With Thread B: nothing besides arriving in CL 104 — ask the author"]);
    await secs.nth(1).locator(".ov-links").getByRole("link", { name: "Walk through: When len > 64" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/walk/W1$`));
    await page.goBack();
    await secs.nth(1).locator(".dz-walks").getByRole("link", { name: "Walk through: From main through logger_init" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/walk/W4$`));
    await expectNamed(page);
  });

  test("folds the changes that still run when the condition is false, and those that stop", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(base);
    const region = page.getByRole("region", { name: "When the condition is false", exact: true });
    await expect(region.locator("h2")).toHaveText(/^When len > 64 is false · \d+ changes still run$/);
    await expect(region.getByText("Stops (2)")).toBeHidden();
    await openFold(page, "When the condition is false");
    await expect(region.locator("h3")).toHaveText([/^Still runs \(\d+\)$/, "Stops (2)"]);
    await expect(region.locator(".dz-gated").last().locator("li")).toHaveText([
      /^S1 .+ · driver\/uart\.c:17 in uart_send$/, /^S1 .+ · driver\/uart\.c:18 in uart_send$/]);
    await expect(region.locator(".dz-gated").first()).toContainText("st->tx++;");
    await expectNamed(page);
  });
});
```

In `frontend/e2e/helpers.ts`, `openFold`'s `name` becomes
`"When the condition is false" | "Build impact" | "Coverage" | "Discussion"`.

The overview's headings now hold Where the change sits after the first and the condition fold before Build impact (the
default review, CLs 101+102, has three components and one condition). In each list below, insert
`"Where the change sits"` after the first heading and `/^When len > 64 is false · \d+ changes? still runs?$/` before
`"Build impact · up to 4 files rebuild"`:

- `e2e/workspace.spec.ts` (the `ov.locator("h2")` list, "1 thread");
- `e2e/workspace-reading.spec.ts` (the first `.ov3 h2` list, "3 threads");
- `e2e/outline-causes.spec.ts` (the `.ov3 h2` list, "3 threads");
- `e2e/thread-sections.spec.ts` (the `.ov3 h2` list of "Build impact, Coverage and Discussion are folded rows…", "1 thread").

The connection between Thread A and Thread B now ends in its walk-through's link. Change
`"With Thread A: both run inside main"` to `"With Thread A: both run inside main · ▶ Walk through ›"` in:

- `e2e/workspace-reading.spec.ts` (both `.ov-links li` lists);
- `e2e/outline-causes.spec.ts` (the `.ov-links li` list);
- `e2e/thread-sections.spec.ts` (`secs.nth(1)`'s list), and in its reworded-connection test
  `await expect(line(1)).toHaveText("With Thread A: Written by AI. both run inside main");` becomes
  `… "With Thread A: Written by AI. both run inside main · ▶ Walk through ›");`

In `e2e/thread-sections.spec.ts`, the review with no threads drops the design too, so the first fold still follows the
change: `patchReading(page, (r) => { r.threads = []; r.connections = []; r.design = null; });`

In `e2e/workspace-pages.spec.ts`, "the overview keeps its own spacing": the folds are four
(`toHaveCount(4)`, its comment `// the condition, Build impact, Coverage, Discussion`) and the gaps `[6, 6, 6]`.

- [ ] **Step 5: Run them to see them fail**

Run (from `frontend/`): `npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/walk-throughs.spec.ts e2e/workspace.spec.ts e2e/workspace-reading.spec.ts e2e/outline-causes.spec.ts e2e/thread-sections.spec.ts e2e/workspace-pages.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: FAIL: the three new overview tests, and each edited list (no "Where the change sits", no condition fold, no
"· ▶ Walk through ›", three folds). Every other test passes.

- [ ] **Step 6: Write the overview's new parts**

In `frontend/src/workspace/Overview.tsx`:

- imports: `{ alsoLine, blockLine, componentBands, conditionTitle, foldGate, gateGroups, showsWhere } from "../reading/design"`,
  `{ connectionWalk } from "../reading/walks"`, and `Gate`, `GatedLine`, `ReadingDesign` with the types from
  `../reading/types`;
- `Fold`'s heading reads backticks as code: `<summary><h2><Ticks text={title} /></h2></summary>`;
- `ThreadSection` takes `design: ReadingDesign | null` beside its other props
  (`{ t, i, r, links, read, stories, design }`, typed `design: ReadingDesign | null;`) and, after `const more = …`,
  `const walks = design?.walks.filter((w) => w.thread === t.id) ?? [];`. Between the "Show the other … stories" button and the
  `.ov-links` list it renders:

```tsx
      {walks.length > 0 && <ul className="dz-walks">{walks.map((w) => (
        <li key={w.id}><Link to={ws.link(ws.item({ kind: "walk", wid: w.id }))} title={`Walk through: ${plain(w.title)}`}
                             aria-label={`Walk through: ${plain(w.title)}`}>
          <span aria-hidden>▶ </span>Walk through: <Ticks text={w.title} /> ›</Link></li>
      ))}</ul>}
```

  and each `.ov-links` item ends in the walk-through on its connection:

```tsx
      {links.length > 0 && <ul className="ov-links">{links.map((k) => {
        const cw = connectionWalk(design, k.a, k.b);
        return (
          <li key={k.before + k.text} className={k.bundled ? "bundled" : undefined}>
            {k.before}<AiText as="span" ai={k.ai}><Ticks text={k.text} /></AiText>{k.after}
            {cw && <> · <Link className="dz-cwalk" to={ws.link(ws.item({ kind: "walk", wid: cw.id }))} title={`Walk through: ${plain(cw.title)}`}
                              aria-label={`Walk through: ${plain(cw.title)}`}><span aria-hidden>▶ </span>Walk through ›</Link></>}
          </li>
        );
      })}</ul>}
```

- add the two new parts before `Fold`:

```tsx
/** Where the change sits (spec 2026-11-02 §5): the map's layer bands with components for blocks, each naming the threads
 * that change it and its changed files, the calls and fields that cross into it from another component, and what changed
 * in it. A component that shares no edge with the rest is dashed. It opens nothing: its stories are a thread's. */
function WhereItSits({ d, r }: { d: ReadingDesign; r: Reading }) {
  const ws = useWs(), titles = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st.title]));
  return (
    <section className="dz-where" aria-labelledby="dz-where">
      <h2 id="dz-where">Where the change sits</h2>
      {componentBands(d.components).map((b) => (
        <section key={b.band} className={`ov-band lv${b.level === null ? "x" : b.level % 4}`} aria-label={`Layer ${b.band}`}>
          <h3>{b.band}</h3>
          <div className="ov-blocks">{b.components.map((c) => {
            const also = alsoLine(c.stories, (s) => titles.get(s));
            return (
              <div key={c.name} className={`ov-block dz-block${c.quiet ? " quiet" : ""}`}>
                <div className="nm">{c.name}</div>
                <div className="ct">{blockLine(c, r.threads)}</div>
                {c.quiet ? <div className="ln">No calls or fields shared with the rest</div>
                  : c.crossing.map((l) => <div key={l} className="ln"><Ticks text={l} /></div>)}
                {also && <div className="also"><Ticks text={also} /></div>}
              </div>
            );
          })}</div>
        </section>
      ))}
    </section>
  );
}

/** The condition fold's lines (§7): those that still run when the condition is false, then those that stop, each with its
 * story, its code and where it is. */
function ConditionLines({ g }: { g: Gate }) {
  const ws = useWs(), { runs, stops } = gateGroups(g), titles = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st.title]));
  const row = (l: GatedLine, i: number) => {
    const title = l.story ? titles.get(l.story) ?? l.story : "";
    return (
      <li key={i}>
        {l.story ? <Link className="ws-handle link" to={storyTo(ws, l.story)} title={bare(title)}
                         aria-label={`Go to story ${l.story}: ${short(title)}`}>{l.story}</Link>
          : <span className="ws-handle">no story</span>}
        {" "}<code>{l.text}</code>
        <span className="muted"> · {l.path}{l.line ? `:${l.line}` : ""}{l.function && <> in <code>{l.function}</code></>}</span>
      </li>
    );
  };
  return <>
    <p className="muted">The condition is <code>{g.test}</code>, in {g.path}{g.line ? `:${g.line}` : ""}.</p>
    {runs.length > 0 && <><h3>Still runs ({runs.length})</h3><ul className="ov-lines dz-gated">{runs.map(row)}</ul></>}
    {stops.length > 0 && <><h3>Stops ({stops.length})</h3><ul className="ov-lines dz-gated">{stops.map(row)}</ul></>}
  </>;
}
```

- in `Overview`: after `const tests = …` add `const design = r.design ?? null, gate = foldGate(design);`; after the
  `.ov-top` section add `{design && showsWhere(design) && <WhereItSits d={design} r={r} />}`; pass `design={design}` to each
  `ThreadSection`; and before the Build impact fold add

```tsx
      {gate && <Fold name="When the condition is false" title={conditionTitle(gate)}><ConditionLines g={gate} /></Fold>}
```

  The overview's doc comment gains: "…where to start, where the change sits (spec 2026-11-02 §5), a section per thread
  with its walk-throughs …, the tests, then what still runs when the change's condition is false (§7), Build impact,
  Coverage and Discussion folded."

- [ ] **Step 7: Style it**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the design overview on the overview (spec 2026-11-02-design-overview §3.1): Where the change sits is the map's bands with
   components that open nothing for blocks; a thread's walk-throughs sit under its stories; the condition fold's lines */
.ov-block.dz-block { cursor: default; }
.ov-block.dz-block:hover { border-color: var(--bd-node-line); }
.ov-block.dz-block .nm { margin-right: 0; }
.ov-block.dz-block.quiet { border-style: dashed; }
.ov-block.dz-block code { overflow-wrap: anywhere; }
.ov3 .dz-walks { list-style: none; margin: 0 14px 10px; padding: 0; font-size: 13.5px; }
.ov3 .dz-walks li { padding: 2px 0; overflow-wrap: anywhere; }
.ov3 .dz-walks a, .ov3 .dz-cwalk { text-decoration: none; font-weight: 600; }
.ov3 .ov-fold h3 { margin: 10px 0 4px; font-size: 13px; }
.dz-gated li { overflow-wrap: anywhere; }
```

- [ ] **Step 8: Run the unit tests and the e2e tests**

Run (from `frontend/`): `npx vitest run && npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/walk-throughs.spec.ts e2e/workspace.spec.ts e2e/workspace-reading.spec.ts e2e/outline-causes.spec.ts e2e/thread-sections.spec.ts e2e/workspace-pages.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: vitest all pass; Playwright all pass (the phone overview test in `workspace-reading.spec.ts` checks nothing
scrolls sideways with the new bands).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/reading/overview.ts frontend/src/reading/overview.test.ts frontend/src/workspace/Overview.tsx frontend/src/workspace/workspace.css frontend/e2e/helpers.ts frontend/e2e/walk-throughs.spec.ts frontend/e2e/workspace.spec.ts frontend/e2e/workspace-reading.spec.ts frontend/e2e/outline-causes.spec.ts frontend/e2e/thread-sections.spec.ts frontend/e2e/workspace-pages.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the overview says where the change sits, lists each thread's walk-throughs and folds what still runs when its condition is false

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 10: The outline's walk rows, the story's crumb and the Flows tab's step

**Files:**
- Modify: `frontend/src/workspace/Outline.tsx`, `frontend/src/workspace/Workspace.tsx`, `frontend/src/workspace/StoryPage.tsx`,
  `frontend/src/workspace/FlowsTab.tsx`, `frontend/src/workspace/workspace.css`, `frontend/e2e/walk-throughs.spec.ts`
- Test: `frontend/e2e/walk-throughs.spec.ts`

**Interfaces:**
- Consumes: Task 6's `walksForThread`, `walkOpen`, `threadName`, `storyWalks`, `stepList`, `flowSteps`; Task 7's walk
  place and `?step=N`.
- Produces: `useStoryThread(rid, r, sid, wid = null)`; outline rows `a.ws-row.walk` (aria-label
  "Walk through: <title>, N steps[, with Thread X][, N open]") after a thread's stories; the story crumb's
  " · in <title> (steps …)" links (two at most, then "and N more walk-throughs"); a Flows row's `span.dz-mark`
  ("▶ step N") and its body's `p.dz-on` link.

- [ ] **Step 1: Write the failing e2e tests**

Append to `frontend/e2e/walk-throughs.spec.ts`:

```ts
test.describe("the links to a walk-through", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("an open thread bar lists its walk-throughs after its stories, one on a connection under both threads", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const rail = page.locator("aside.ws-outline"), walks = rail.locator(".ws-bar-list .ws-row.walk");
    await expect(walks).toHaveCount(3);
    await expect(walks.first()).toHaveAttribute("aria-label", "Walk through: When len > 64, 9 steps, with Thread B, 2 open");
    await expect(walks.first().locator(".ws-row-sub")).toHaveText("9 steps · with Thread B");
    await expect(walks.first().locator(".ck-count")).toHaveText("2");
    await rail.getByRole("button", { name: /^Thread B:/ }).click();
    await expect(walks).toHaveCount(2);
    await expect(walks.first()).toHaveAttribute("aria-label", "Walk through: When len > 64, 9 steps, with Thread A, 2 open");
    await expect(walks.nth(1)).toHaveAttribute("aria-label", /^Walk through: From main through logger_init, \d+ steps$/);
    await walks.first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/walk/W1$`));
    await expect(rail.locator(".ws-bar.on > button")).toHaveAttribute("aria-label", /^Thread A:/);   // the walk-through's own thread
    await expect(rail.locator(".ws-row.walk[aria-current='page']")).toHaveCount(1);
  });

  test("a story's head names the walk-throughs it is on, and a flow on one says its step", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const crumb = page.locator(".st-head .st-crumb");
    await expect(crumb).toContainText("in When len > 64 (steps 1–5, 8)");
    await expect(crumb.getByRole("link", { name: /^Walk through: / })).toHaveCount(2);
    await expect(page.locator("#flow-1 .dz-mark")).toHaveText("▶ step 5");
    await expect(page.locator("#flow-2 .dz-mark")).toHaveText("▶ step 8");
    await page.locator("#flow-1 .fl-toggle").click();
    await page.getByRole("link", { name: "Go to step 5 of the walk-through When len > 64" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/walk/W1\\?step=5$`));
    await expect(page.locator("#step-5 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await page.goBack();
    await crumb.getByRole("link", { name: "Walk through: When len > 64, from step 1" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/walk/W1\\?step=1$`));
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run (from `frontend/`): `npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/walk-throughs.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: the two new tests FAIL (no `.ws-row.walk`, no "in When len > 64"); the earlier ones pass.

- [ ] **Step 3: The outline's rows, and the thread a walk-through opens**

In `frontend/src/workspace/Outline.tsx`:

- imports: `{ threadName, walkOpen, walksForThread } from "../reading/walks"` and `Walk` with the types from
  `../reading/types`;
- `useStoryThread` becomes:

```ts
/** Going to a story, or to a walk-through, makes its thread the one last opened in this review (spec 2026-10-25-review-ui-redesign
 * §6; a walk-through's own thread, spec 2026-11-02 §3.2), for each one, not only when the thread changes, or a bar clicked since
 * would stay the last opened. The workspace keeps it, since on a phone the outline is not there while a story shows; the outline
 * reads it when it mounts. */
export function useStoryThread(rid: number, r: Reading | null | undefined, sid: string | null, wid: string | null = null) {
  const holding = !r ? null : sid ? r.threads.find((t) => t.stories.includes(sid))?.id ?? null
    : wid ? r.design?.walks.find((w) => w.id === wid)?.thread ?? null : null;
  useEffect(() => { if (holding) saveThread(rid, holding); }, [rid, sid, wid, holding]);
}
```

- in `StoriesView`, after `const here = …`:

```ts
  const hereWalk = ws.addr.place.kind === "walk" ? ws.addr.place.wid : null;
  const spot = here ?? (hereWalk ? `walk:${hereWalk}` : null);                 // where the reader is: a bar clicked there is for there only
```

  `useEffect(() => { setChosen(null); }, [here]);` becomes `…, [spot]);`; `holding` becomes

```ts
  const holding = here ? r.threads.find((t) => t.stories.includes(here))?.id ?? null
    : hereWalk ? r.design?.walks.find((w) => w.id === hereWalk)?.thread ?? null : null;
```

  its effect's dependencies `[here, holding]` become `[spot, holding]`; `on` becomes
  `const on = chosen && chosen.here === spot ? chosen.id : openThread(r.threads, here, holding ?? last);` and `toggle`'s
  `setChosen({ here, id: next })` becomes `setChosen({ here: spot, id: next })`;
- after the `story` function add:

```tsx
  const checks = useMemo(() => new Map(r.checks.map((k) => [k.key, k])), [r.checks]);
  /** A walk-through's row (spec 2026-11-02 §3.2): "▶ Walk through · title", its steps and the thread at the other end of its
   * connection, and its open count. */
  const walkRow = (w: Walk, other: string | null) => {
    const n = walkOpen(w, checks, ws.hidden, r.marks), steps = `${w.steps.length} step${w.steps.length === 1 ? "" : "s"}`;
    const also = other ? threadName(r.threads, other) : null;
    return (
      <li key={`walk:${w.id}`}>
        <Link to={ws.link(ws.item({ kind: "walk", wid: w.id }))} className="ws-row walk" aria-current={hereWalk === w.id ? "page" : undefined}
              title={`Walk through: ${bare(w.title)}`} onClick={onPick}
              aria-label={`Walk through: ${short(w.title)}, ${steps}${also ? `, with ${also}` : ""}${n ? `, ${n} open` : ""}`}>
          <span className="ws-row-top">
            <span className="ws-num" aria-hidden>▶</span>
            {read && <span className="ws-read" aria-hidden />}
            <span className="ws-one">Walk through · <Ticks text={w.title} /></span>
            {n > 0 && <span className="ck-count" aria-hidden>{n}</span>}
          </span>
          <span className="ws-row-sub">{steps}{also && ` · with ${also}`}</span>
        </Link>
      </li>
    );
  };
```

  (the `useMemo` sits above any return: `StoriesView` has none before its JSX);
- the open bar's list ends in its walk-throughs:

```tsx
          {isOn && <ul className="ws-bar-list" style={pinned}>{t.stories.map((sid, k) => {
            const st = byId.get(sid);
            return st ? story(st, r.reasons[sid], k + 1) : null;
          })}{walksForThread(r.design, t.id).map(({ walk, other }) => walkRow(walk, other))}</ul>}
```

In `frontend/src/workspace/Workspace.tsx`, the `useStoryThread` call passes the walk:
`useStoryThread(id, r, addr.place.kind === "story" ? addr.place.sid : null, addr.place.kind === "walk" ? addr.place.wid : null);`

- [ ] **Step 4: The story's crumb**

In `frontend/src/workspace/StoryPage.tsx`: import `Fragment` from `react` and `{ stepList, storyWalks } from "../reading/walks"`;
after `const nb = …` add `const onWalks = r ? storyWalks(r.design, sid) : [];`; after the `feeds:` line of the reading
header's `st-crumb` add:

```tsx
        {onWalks.slice(0, 2).map(({ walk, steps }) => (
          <Fragment key={walk.id}> · in <Link className="st-nb" to={ws.link(addressAt({ kind: "walk", wid: walk.id }, { step: steps[0] }))}
                                              title={`Walk through: ${bare(walk.title)}`}
                                              aria-label={`Walk through: ${bare(walk.title)}, from step ${steps[0]}`}><Ticks text={walk.title} /></Link>
            {" "}({steps.length === 1 ? "step" : "steps"} {stepList(steps)})</Fragment>
        ))}
        {onWalks.length > 2 && <> · and {onWalks.length - 2} more walk-through{onWalks.length === 3 ? "" : "s"}</>}
```

- [ ] **Step 5: The Flows tab's step**

In `frontend/src/workspace/FlowsTab.tsx`: import `Link` from `react-router-dom`, `{ at } from "./address"` and
`{ flowSteps } from "../reading/walks"`; after `const parts = …` add `const design = d.reading?.design, sid = detail.story.id;`;
in each row, after `const done = …, field = fieldOf(flow);` add `const onWalk = flowSteps(design, sid, flow.id);`; after the
row's `fl-toggle` button add

```tsx
                    {onWalk.length > 0 && <span className="dz-mark" title={`Step ${onWalk[0].n} of the walk-through ${bare(onWalk[0].walk.title)}`}>
                      ▶ step {onWalk[0].n}</span>}
```

and in its body, after the `fl-check` line and the chips:

```tsx
                      {onWalk.map(({ walk, n: step }) => (
                        <p key={walk.id} className="dz-on"><Link to={ws.link(at({ kind: "walk", wid: walk.id }, { step }))}
                            aria-label={`Go to step ${step} of the walk-through ${bare(walk.title)}`}>
                          On the walk-through: step {step} of <Ticks text={walk.title} /> ›</Link></p>
                      ))}
```

- [ ] **Step 6: Style it**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the links to a walk-through (spec 2026-11-02 §3.2): its outline row after its thread's stories, and a flow's step on the
   story's Flows row */
.ws-row.walk .ws-num { color: var(--accent); }
.dz-mark { flex: none; padding: 0 8px; font-size: 12px; color: var(--muted); white-space: nowrap; }
.dz-on { font-size: 13px; }
.dz-on a { text-decoration: none; }
```

- [ ] **Step 7: Run the e2e tests, the outline's and the Flows tab's**

Run (from `frontend/`): `npx vitest run && npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/walk-throughs.spec.ts e2e/thread-sections.spec.ts e2e/flow-groups.spec.ts e2e/outline-causes.spec.ts e2e/workspace-story.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: all pass (the outline's focus test in `thread-sections.spec.ts` walks the new rows too, clear of the bars).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/workspace/Outline.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/StoryPage.tsx frontend/src/workspace/FlowsTab.tsx frontend/src/workspace/workspace.css frontend/e2e/walk-throughs.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: walk-throughs in the outline's thread bars, a story's crumb and its Flows rows

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

### Task 11: The README, and every suite

**Files:**
- Modify: `README.md` (its opening description)

**Interfaces:**
- Consumes: everything above.
- Produces: the README's account of the design overview; every suite green.

- [ ] **Step 1: Say it in the README**

In `README.md`, after the paragraph that begins "A review opens on an overview of the change." add:

```markdown
The overview also says **where the change sits**: its components, layer by layer, each with the threads that change it and
the calls and fields that cross into it from another (the `analysis:` setting `components` names them; without it, the
folders do). A thread's **walk-throughs** follow a changed path from where it starts, through the functions it passes, to
where what changed lands, as a drawing and as steps. Each step links to the story it comes from, and a step that is one of
the story's flows has that flow's tick box. When the change adds a condition, a folded row lists the changed lines that
still run when the condition is false, and those that don't. All of it comes from the code alone; `design: false` turns it
off.
```

- [ ] **Step 2: Run every suite**

Run:

```bash
cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider > ../.superpowers/pytest.log 2>&1; tail -3 ../.superpowers/pytest.log; .venv/bin/ruff check codetortoise tests
cd ../frontend && npm run build > /dev/null && npx vitest run 2>&1 | tail -4
mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test --retries=0 > ../.superpowers/e2e.log 2>&1; tail -5 ../.superpowers/e2e.log; rm -rf ../.pwtmp
```

Expected: pytest all pass; ruff "All checks passed!"; the build clean; vitest all pass; Playwright all pass. A failure
here is a finding about this branch: debug it (superpowers:systematic-debugging), fix it under a failing test, and ledger
the ruling.

- [ ] **Step 3: Commit**

```bash
git add README.md
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "docs: the README tells of where the change sits, walk-throughs and the condition fold

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```
