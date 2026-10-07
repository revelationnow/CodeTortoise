# Review Reading (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A large multi-CL review reads as one connected account. Stories join into threads by calls and shared data. The overview says what the change does as a whole and how its threads connect. Every story page answers the same questions in the same tiles. "To check" is the reviewer's list of hazards and of places the analysis thinks were missed, each with Looks fine and Comment.

**Architecture:** A new backend module `reading.py` computes everything from the analysis with no AI: story links, threads, thread connections, reading order, each story's contract rows, where its code lives and every call path to it, the To check rows with stable keys, build impact, coverage and the headline. `llm/threads.py` lets the strong model reword the thread names, purposes and the whole in one checked tier-1 call; anything unchecked keeps the fixed text. A new pipeline stage `reading` (after `llm`) stores the `reading` and `story_reading:<sid>` blobs; a new table holds marks shared by everyone viewing a review. The frontend reads it in layout B: the overview (threads with arcs between them, a pinned To check, build impact and coverage), the story page (what it does, before → after beside where, call paths, its own To check), a rail that follows the threads, and an Index holding CLs, files, checks and the map. A `tidy` rule set makes evidence read as people write it.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, SQLite, libclang, tree-sitter, pytest, ruff; React 19, TypeScript (strict), react-router 7, Vite, vitest, Playwright. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-07-review-reading-design.md` (phase 1: §3–§13)

**Base:** branch `review-reading` at `adbd9f8` (the spec is its latest commit). Everything stays on `review-reading`; nothing reaches `main` until the owner decides.

**Provenance:** every code block below was run before this plan was written. The tasks were then replayed in order on a fresh tree from `adbd9f8` by a script that applied each step's blocks and ran each step's command. Every Expected line is that run's output. Each task's tests failed before its implementation and passed after it, and the suite stayed green after every task. A second script built a tree from this document's blocks alone; that tree is byte-identical to the validated one. New files are given in full. Changes to existing files are unified diffs against the previous task's state; apply them with `git apply` or by hand. Under parallel load an end-to-end test may time out or lose its browser on its first run. If one does, rerun it alone with `--last-failed`; if it fails again, it is a real failure.

## Global Constraints

- **Vocabulary (§3):** the UI's words are story, thread, call path, check and possibly missed. "Parts", "pieces", "clusters", "chapters", "TU" and "layer" leave headings and labels. Code keeps its names.
- **No AI needed (§2):** everything in §4–§8 is computed by the analysis; the strong model only writes names and sentences over facts it is given, and every one of its answers is checked.
- **Story links (§4.1):** strong = calls or data, weak = same file or same CL; the story that changed the callee or writes the field **defines**, the other **uses**. Threads are connected components of strong links; tests stories never join a thread.
- **Thread connections (§4.3):** kinds in order `caller` (a common caller within `CALLER_HOPS = 3` reverse call hops, entry points preferred), `vocabulary`, `condition`, `place`, `bundled`. Shown: every pair of kinds 1–4 not already joined through shown pairs of the same or a stronger kind, plus one bundled arc for each thread with nothing else.
- **Reading order (§4.4):** within a thread, defines before uses (ties: more changed functions first); threads by open hazards, then open checks, then changed functions; Tests last. Each story after the first carries its reason ("← calls 1", "← uses 1").
- **Call paths (§8.2):** no cap on how many. Ranked contract, then state, then the rest; grouped by entry point; a path longer than four steps keeps its first step and its last two.
- **To check (§7):** kinds in order `hazard`, `confirm`, `caller`, `result`, `reader`, `target`, `untested`, `unanalysed`, `ask` (and `cleared` for findings judged no hazard). Key: `kind|workspace-relative file|function|related changed function's qualified name`; no line numbers. Two kinds at one place merge into one row. Rules only: high and medium findings (not header fan-out) are Confirm rows and the tile says "Risks judged by rules only".
- **Marks (§7.4, §10.3):** table `check_marks(review_id, key, user, at, source_line, PRIMARY KEY(review_id, key))`, shared by every viewer; a re-run keeps marks whose key is found again and drops the rest; a changed source line reopens the check ("Changed since marked"). Comments gain anchor kind `check` with anchor `{key}`.
- **Headline (§5.4):** open hazards → "N hazard(s)" (red); else open confirms → "N to confirm" (amber); else "No hazards found". Rules only: the top severity of the open findings, labelled "rules only". Build impact and parse problems never raise it. The Reviews list shows the same headline.
- **AI text (§9):** one tier-1 call per review, purpose `threads`, counted against `llm.budget.tier1_per_review`. Names at most 6 words (`NAME_WORDS = 6`); every cited id must be in the input; a reworded connection keeps its cited names and CLs. Without a strong model, or when the call fails: names from the defining story's main changed function and folder, purposes from its summary, the whole from the strongest connections. `READING_VERSION = 1` keys the cached thread text.
- **API (§10.4):** `GET /api/reviews/{id}/reading` → the reading plus the marks; `GET /api/reviews/{id}/stories/{sid}` adds `reading`; `POST` and `DELETE /api/reviews/{id}/checks/{key}/mark` for any signed-in viewer; Reviews list items gain `headline`.
- **Clean-up (§12):** paths workspace-relative, no Python reprs, an empty count is never shown, the AI label only on AI-written text.
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).
- **End-to-end runs:** build the frontend first (`npm run build` writes `backend/codetortoise/web/static`). Playwright starts the fixture servers itself: 8799 (rules only); 8798 with the fake model on 8797; 8796 for the large fixture; 8795 with the fake model as the strong model. If Chromium crashes ("Target crashed"), the browser's temp directory is full: point `TMPDIR` at a directory on disk.

## Review Focus

These are the conditions the spec implies that are most likely to bite a real user, most likely first. Each is pinned by a test in the task that owns the code.

1. **Reviews stored before this design** have no `reading` blob. They must open exactly as before: the old rail, the old whole-change page, the old story body, no errors. Pinned by the e2e test "a review without stories or a reading (run before them) keeps the old rail and page" (Task 12); the overview and story page fall back in Tasks 10 and 11.
2. **Code that changes after a reviewer said Looks fine.** On a re-run the same check (same key) at a different source line must reopen, a check that is gone must drop its mark, and everyone else's marks must stay. Pinned by `test_any_viewer_marks_a_check_and_a_rerun_keeps_drops_or_reopens_it` (Task 7) and the e2e test "Looks fine marks a check for everyone … and survives a re-run" (Task 10).
3. **The strong model fails or answers badly in the thread call** (down, refused by the budget, unknown ids, a name too long, a connection reworded without its fact). The review must finish with the fixed text and say why. Pinned by `test_a_failed_or_refused_call_keeps_every_fixed_text_and_says_why` and `test_answers_citing_unknown_ids_too_long_names_or_dropping_a_connections_fact_keep_the_fixed_text` (Task 6).
4. **Check keys hold `/`, `|` and `::`** (paths, the key separator, C++ names). Marking one must reach the right check through the URL. Pinned by `test_the_reading_endpoint_serves_threads_checks_and_marks_and_the_story_its_tiles` (Task 7, keys sent with `quote(key, safe='')`); the browser encodes them with `encodeURIComponent` (Task 9).
5. **A story reached by many call paths** must show every one (the owner asked for no cap), folded and grouped so the page stays readable. Pinned by `test_call_paths_are_not_capped` (Task 3) and the e2e test of the folded path on the story page (Task 11).

## Spec Coverage

| Spec | Where |
|---|---|
| §3 vocabulary | Tasks 10–12 (headings, rail, Index) |
| §4.1 story links, §4.2 threads, §4.4 reading order | Task 1 |
| §4.3 thread connections | Task 2 (with tree-sitter preprocessor spans in `cparse.py`) |
| §5.1 left column | Task 10 |
| §5.2 right column: To check (Task 4 rows, Task 10 tile), build impact and coverage (Task 5 data, Task 10 tiles) | Tasks 4, 5, 10 |
| §5.3 what leaves the home page | Task 10 (the map stays until Task 12 moves it to the Index) |
| §5.4 headline | Task 5 (computed), Task 9 (header, Reviews list) |
| §6 story page | Task 11 |
| §7.1 kinds, §7.2 rows, §7.3 where checks live | Task 4 (rows), Tasks 10–11 (tiles) |
| §7.4 keys and marks | Task 4 (keys), Task 7 (store, API, re-run), Task 10 (Looks fine, Comment) |
| §7.5 honest limits | Task 4 (Not analysed), Task 5 (Coverage) |
| §8.1 contract rows, §8.2 call paths | Task 3 (data), Task 11 (tiles) |
| §9 AI text | Task 6 (call and checks), Task 7 (stage and cache) |
| §10 data, pipeline, store, API | Tasks 5, 7, 9 |
| §11 rail, Index, old addresses, phone | Task 12 (phone To check first and connection rows in Tasks 10–11) |
| §12 clean-up rules | Task 13 |
| §13 testing: unit tests (every task), fixture (Task 8), Playwright (Tasks 9–13), lab (Task 14) | all |
| §14 phase 2, §15 out of scope | nothing built |

## Decisions the spec left open (or that differ from it)

- **The reading carries more than §10.1 lists.** `Reading` also has `links`, `checks`, `cleared`, `rules_only` and `tests` (the Tests row), so the overview needs one request; `StoryReading` has `thread` and `position`; `Check` has `depot`, the depot path the side panel's Open needs (the browser cannot map a workspace path to a depot file by itself).
- **Findings judged no hazard are `cleared` rows** kept apart from the open checks; the To check tile's footer opens them with their reasons.
- **The reading stage depends on `board`** and is Degraded with "no stories to read" when the board built none. The thread text is cached in the blob `thread_text`, keyed by the SHA-256 of `READING_VERSION`, the strong model's name and the prompt; Re-run stories (fresh) asks again. Marks are pruned to the keys of the open checks after each run.
- **The fixture gains CLs 103 and 104** (Task 8): a logger level added across two CLs, and an engine change tied to the rest only by arriving in CL 104 (the "only bundled" case). The bundled fixture has no test code, so No test touched is covered by unit tests (the spec says so).
- **A story's flows live in its graph view.** The story page shows Call paths; each path links "On the graph ›" to `?view=graph&flow=N`, where the flow strip stays.
- **The tier-1 "Why these belong together" and "Related" leave the story page** (§6.4: folded into What it does and To check). An Unsorted story keeps "Pieces to place", which shows the check each piece failed.
- **The map stays on the overview until Task 12** moves it to the Index's Map tab, so every task leaves the map reachable.
- **Old finding addresses** (`/f/F3`) open the story holding the finding's check row, with `?check=F3` lighting the row (the overview when the row has no story). A finding with no row (an info finding) opens its own page as before. A row's Details link opens the finding page with `?details=1`; the finding page's ‹ › keep it.
- **Reviews without a reading keep the old pages**: the old rail, the old whole-change page and the old story body.
- **The Index is four rail rows** (CLs, Files, Checks, Map) opening `/i/<tab>`; `#files`, `#findings`, `#changeset` and `#map` redirect there. Possibly missed opens the overview's To check (`#checks`).
- **The rail's home is "Overview"** ("Go to the overview") with the headline beside it. A story's breadcrumb (and the phone's back link) is its thread ("Thread A").
- **Unsorted stories stay in their thread** in the rail, marked "Needs a person to place it"; the rail no longer has its own Unsorted group.
- **The rail's CL filter goes** with the rail's CL list; a CL's page (from the Index) still lists the stories drawn from it.
- **Stored finding titles stay as the detectors wrote them**: comments and tier-1 verdicts are anchored on them, and the detectors are out of scope (§15). `tidy` rewrites text where it is read instead: check rows, tier-1 and tier-2 prompts, the findings API's summaries and evidence (with the workspace root removed), and the finding titles the browser shows (`frontend/src/lib/tidy.ts` keeps the same rules). "1 change(s) reach" becomes "1 change reaches" for a short list of verbs (reach, affect, call, use, need, read, write).
- **Pipeline stage messages keep their "(s)"**: they are operator notes, not text the reader acts on.

---

### Task 1: Story links, threads and reading order

Spec §4.1, §4.2, §4.4. `story_links` finds, for every pair of stories, the strongest link between their changed code: a call into a function the other story changed, then a read or write of a field the other now writes (both strong), then a shared file, then a shared CL (weak). Only a story's own changed code links it, not the unchanged code its flows pass through; a removed call is not a link. The direction says which story defines: the one whose callee or field it is (for a call, the story with more calls into it). `build_threads` takes the connected components of strong links, orders each thread's stories defines-before-uses (a cycle still orders every story), gives each later story its reason, orders the threads, and names each one from its defining story's main changed function and folder.

**Files:**
- Test: `backend/tests/test_reading.py`
- Create: `backend/codetortoise/reading.py`

**Interfaces:**
- Consumes: `StorySet`, `Story` (`stories.py`); `board._Ctx` (the analysis: impact graph, calls, field accesses, the diff map).
- Produces: `reading.StoryLink(a, b, strength, kind, defines, text, facts)`, `reading.Thread(id, name, purpose, text_source="template", stories, cls, open_checks=0)`;
  `reading.rel_path(x, path) -> str`; `reading.story_links(ss, x) -> list[StoryLink]`;
  `reading.build_threads(ss, links, x, open_counts: dict[str, tuple[int, int]] | None = None) -> tuple[list[Thread], dict[str, str]]` (threads in reading order, and story id → reason).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_reading.py` (new file):

```python
"""How a review reads (spec 2026-10-07-review-reading §4–§8): story links, threads, connections, reading order."""
from test_stories import _edit, _world

from codetortoise.board import analyse
from codetortoise.reading import build_threads, story_links
from codetortoise.stories import Story, StorySet


def _set(*groups, kinds=None, cls=None):
    """Stories S1… holding the given node ids; `kinds` and `cls` by story id."""
    stories = [Story(id=f"S{i}", kind=(kinds or {}).get(f"S{i}", "other"), title=f"story {i}", summary=f"does {i}",
                     nodes=list(g), cls=(cls or {}).get(f"S{i}", [1])) for i, g in enumerate(groups, 1)]
    return StorySet(summary="", stories=stories, node_story={n: s.id for s in stories for n in s.nodes})


def _x(c):
    return analyse(c).x


# ---- §4.1 story links
def test_a_call_into_another_storys_changed_function_is_a_strong_link_from_the_story_that_defines_it():
    c = _world([_edit("send", "drv/uart.c"), _edit("write", "svc/log.c")], calls=[("write", "send")])
    (lk,) = story_links(_set(["N1"], ["N2"]), _x(c))
    assert (lk.a, lk.b, lk.strength, lk.kind, lk.defines) == ("S1", "S2", "strong", "calls", "S1")
    assert lk.text == "calls `send`, changed in S1" and lk.facts == ["N2", "N1"]


def test_reading_or_writing_a_field_another_story_now_writes_is_a_data_link():
    c = _world([_edit("config", "drv/uart.c"), _edit("report", "svc/log.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged")])
    (lk,) = story_links(_set(["N1"], ["N2"]), _x(c))
    assert (lk.kind, lk.strength, lk.defines) == ("data", "strong", "S1")
    assert lk.text == "reads `Uart::errors`, which S1 now writes" and lk.facts == ["N1", "N3", "N2"]


def test_a_call_beats_data_and_the_story_with_more_calls_into_it_defines():
    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c"), _edit("b2", "y/c.c")],
               calls=[("a", "b"), ("b", "a"), ("b2", "a")],
               fields=[("a", "R", "v", "write", "added"), ("b", "R", "v", "read", "unchanged")])
    (lk,) = story_links(_set(["N1"], ["N2", "N3"]), _x(c))
    assert (lk.kind, lk.defines) == ("calls", "S1")
    assert lk.text == "calls `a`, changed in S1" and lk.facts == ["N2", "N1", "N3"]


def test_stories_sharing_only_a_file_or_a_cl_are_weakly_linked_without_direction():
    c = _world([_edit("p", "src/a.c"), _edit("q", "src/a.c"), _edit("r", "lib/r.c")])
    links = story_links(_set(["N1"], ["N2"], ["N3"]), _x(c))
    got = {(lk.a, lk.b): (lk.strength, lk.kind, lk.defines, lk.text, lk.facts) for lk in links}
    assert got == {("S1", "S2"): ("weak", "file", None, "both edit `src/a.c`", ["src/a.c"]),
                   ("S1", "S3"): ("weak", "cl", None, "both arrive in CL 1", ["CL 1"]),
                   ("S2", "S3"): ("weak", "cl", None, "both arrive in CL 1", ["CL 1"])}


def test_only_a_storys_own_changed_code_links_it_not_the_unchanged_code_its_flows_pass_through():
    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _edit("main", "app/main.c")],
               calls=[("main", "send")])
    ss = _set(["N1"], ["N2"])
    ss.node_story["N3"] = "S2"                       # `main` is on a flow of S2
    (lk,) = story_links(ss, _x(c))
    assert lk.kind == "cl"


def test_a_removed_call_is_not_a_link():
    c = _world([_edit("send", "drv/uart.c"), _edit("write", "svc/log.c")], calls=[("write", "send")])
    c.impact.edges[0].status = "removed"
    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
    assert story_links(ss, _x(c)) == []


# ---- §4.2 threads, §4.4 order within a thread
def _chain():
    """S1 `send` is called by S2 `write`, which writes Log::n that S3 `flush` reads; S4 is apart; S5 is tests."""
    c = _world([_edit("send", "drv/uart.c"), _edit("write", "svc/log.c"), _edit("flush", "svc/flush.c"),
                _edit("lonely", "app/x.c"), _edit("test_send", "tests/t.c")],
               calls=[("write", "send"), ("test_send", "send")],
               fields=[("write", "Log", "n", "write", "added"), ("flush", "Log", "n", "read", "unchanged")])
    return c, _set(["N3"], ["N2"], ["N1"], ["N4"], ["N5"], kinds={"S5": "tests"})


def test_strongly_linked_stories_form_a_thread_in_defines_before_uses_order_with_reasons():
    c, ss = _chain()
    threads, reasons = build_threads(ss, story_links(ss, _x(c)), _x(c))
    assert [(t.id, t.stories) for t in threads] == [("T1", ["S3", "S2", "S1"]), ("T2", ["S4"])]
    assert reasons == {"S2": "← calls 1", "S1": "← uses 2"}


def test_tests_stories_never_join_a_thread():
    c, ss = _chain()
    threads, _ = build_threads(ss, story_links(ss, _x(c)), _x(c))
    assert all("S5" not in t.stories for t in threads)


def test_threads_are_ordered_by_open_hazards_then_open_checks_then_size():
    c, ss = _chain()
    links, x = story_links(ss, _x(c)), _x(c)
    threads, _ = build_threads(ss, links, x, open_counts={"S4": (1, 1)})
    assert [t.stories for t in threads] == [["S4"], ["S3", "S2", "S1"]]
    threads, _ = build_threads(ss, links, x, open_counts={"S4": (0, 2), "S1": (0, 1)})
    assert [t.stories for t in threads] == [["S4"], ["S3", "S2", "S1"]]


def test_a_thread_gets_a_fixed_name_from_its_defining_storys_main_function_and_folder():
    c, ss = _chain()
    threads, _ = build_threads(ss, story_links(ss, _x(c)), _x(c))
    t = threads[0]
    assert (t.name, t.purpose, t.text_source, t.cls) == ("`send` in drv", "does 3", "template", [1])
    assert threads[1].name == "`lonely` in app"


def test_a_cycle_of_definitions_still_orders_every_story_and_prefers_the_link_a_story_uses():
    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c"), _edit("c", "z/c.c")], calls=[("a", "b"), ("b", "c"), ("c", "a")])
    ss = _set(["N1"], ["N2"], ["N3"])
    threads, reasons = build_threads(ss, story_links(ss, _x(c)), _x(c))
    assert [t.stories for t in threads] == [["S1", "S3", "S2"]]
    assert reasons == {"S3": "← calls 1", "S2": "← calls 2"}


def test_a_story_whose_only_links_are_to_later_stories_points_forward():
    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c"), _edit("c", "z/c.c")], calls=[("c", "a"), ("c", "b")])
    ss = _set(["N1"], ["N2"], ["N3"])
    _, reasons = build_threads(ss, story_links(ss, _x(c)), _x(c))
    assert reasons == {"S2": "→ called by 3", "S3": "← calls 1"}


def test_cl_links_name_each_shared_changelist():
    c = _world([_edit("p", "src/a.c"), _edit("q", "lib/b.c")])
    (lk,) = story_links(_set(["N1"], ["N2"], cls={"S1": [11, 12], "S2": [11, 12]}), _x(c))
    assert lk.text == "both arrive in CL 11 and CL 12" and lk.facts == ["CL 11", "CL 12"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.reading'`

- [ ] **Step 3: Implement**

`backend/codetortoise/reading.py` (new file):

```python
"""How a review reads (spec 2026-10-07-review-reading §4–§8): stories joined into threads by calls and shared data,
how the threads connect, the order to read them in, each story's contract rows and call paths, and the reviewer's
To check list. Everything here is computed from the analysis; the strong model only rewords it (llm/threads.py)."""
from __future__ import annotations

import posixpath
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import _Ctx
from codetortoise.stories import Story, StorySet

_KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}


class StoryLink(BaseModel):
    """The strongest link between two stories' changed code (§4.1). `a` comes before `b` in the story list."""
    a: str
    b: str
    strength: Literal["strong", "weak"]
    kind: Literal["calls", "data", "file", "cl"]
    defines: str | None = None        # strong links: the story that changed the callee or now writes the field
    text: str
    facts: list[str] = Field(default_factory=list)   # node ids, workspace-relative paths or "CL n"


class Thread(BaseModel):
    id: str
    name: str
    purpose: str
    text_source: Literal["template", "llm"] = "template"
    stories: list[str] = Field(default_factory=list)  # in reading order
    cls: list[int] = Field(default_factory=list)
    open_checks: int = 0


def rel_path(x: _Ctx, path: str | None) -> str:
    """A workspace-relative path (§12); paths outside the workspace stay as they are."""
    if not path:
        return ""
    root = x.c.root.rstrip("/") + "/"
    return path[len(root):] if x.c.root and path.startswith(root) else path


def _home(ss: StorySet) -> dict[str, str]:
    """Changed node -> its story (a story set's `node_story` also maps the unchanged code on its flows)."""
    return {n: s.id for s in ss.stories for n in s.nodes}


def _live(x: _Ctx, kinds: set[str]):
    return [e for e in x.im.edges if e.kind in kinds and e.status != "removed"]


def _cls(cls: list[int]) -> str:
    return " and ".join(f"CL {n}" for n in cls)


def story_links(ss: StorySet, x: _Ctx) -> list[StoryLink]:
    """Every linked pair of stories with its strongest link: calls, then data (strong), then a shared file, then a
    shared CL (weak)."""
    home = _home(ss)
    order = {s.id: i for i, s in enumerate(ss.stories)}
    calls: dict[tuple[str, str], list] = defaultdict(list)   # (defines, uses) -> call edges
    for e in _live(x, {"call", "virtual"}):
        d, u = home.get(e.dst), home.get(e.src)
        if d and u and d != u:
            calls[(d, u)].append(e)
    data: dict[tuple[str, str], list] = defaultdict(list)    # (defines, uses) -> (writer, field, user)
    new_writes = [e for e in _live(x, {"writes"}) if e.status == "added"]
    users = defaultdict(list)
    for e in _live(x, {"reads", "writes"}):
        users[e.dst].append(e)
    for w in new_writes:
        d = home.get(w.src)
        for e in users[w.dst]:
            u = home.get(e.src)
            if d and u and d != u:
                data[(d, u)].append((w, e))
    files = {s.id: {rel_path(x, x.local(n)) for n in s.nodes} - {""} for s in ss.stories}
    out: list[StoryLink] = []
    for i, sa in enumerate(ss.stories):
        for sb in ss.stories[i + 1:]:
            lk = (_calls_link(sa, sb, calls, x) or _data_link(sa, sb, data, x)
                  or _weak_link(sa, sb, files))
            if lk:
                out.append(lk)
    return sorted(out, key=lambda lk: (order[lk.a], order[lk.b]))


def _pick(a: str, b: str, found: dict) -> tuple[str, str, list] | None:
    """The direction with more evidence; a tie goes to the earlier story defining."""
    ab, ba = found.get((a, b), []), found.get((b, a), [])
    if not ab and not ba:
        return None
    return (a, b, ab) if len(ab) >= len(ba) else (b, a, ba)


def _calls_link(sa: Story, sb: Story, calls: dict, x: _Ctx) -> StoryLink | None:
    got = _pick(sa.id, sb.id, calls)
    if not got:
        return None
    d, _u, edges = got
    per = defaultdict(int)
    for e in edges:
        per[e.dst] += 1
    callees = sorted(per, key=lambda n: (-per[n], x.label(n)))
    edges = sorted(edges, key=lambda e: callees.index(e.dst))
    more = f" and {len(callees) - 1} more" if len(callees) > 1 else ""
    return StoryLink(a=sa.id, b=sb.id, strength="strong", kind="calls", defines=d,
                     text=f"calls `{x.label(callees[0])}`{more}, changed in {d}",
                     facts=list(dict.fromkeys(n for e in edges for n in (e.src, e.dst))))


def _data_link(sa: Story, sb: Story, data: dict, x: _Ctx) -> StoryLink | None:
    got = _pick(sa.id, sb.id, data)
    if not got:
        return None
    d, _u, pairs = got
    w, e = pairs[0]
    verb = "reads" if e.kind == "reads" else "writes"
    return StoryLink(a=sa.id, b=sb.id, strength="strong", kind="data", defines=d,
                     text=f"{verb} `{x.label(w.dst)}`, which {d} now writes",
                     facts=list(dict.fromkeys(n for w, e in pairs for n in (w.src, w.dst, e.src))))


def _weak_link(sa: Story, sb: Story, files: dict[str, set[str]]) -> StoryLink | None:
    shared = sorted(files[sa.id] & files[sb.id])
    if shared:
        return StoryLink(a=sa.id, b=sb.id, strength="weak", kind="file", text=f"both edit `{shared[0]}`", facts=shared)
    cls = sorted(set(sa.cls) & set(sb.cls))
    if cls:
        return StoryLink(a=sa.id, b=sb.id, strength="weak", kind="cl", text=f"both arrive in {_cls(cls)}",
                         facts=[f"CL {n}" for n in cls])
    return None


# ------------------------------------------------------------------ threads (§4.2) and reading order (§4.4)
def _components(ids: list[str], strong: list[StoryLink]) -> list[list[str]]:
    parent = {i: i for i in ids}

    def find(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for lk in strong:
        parent[find(lk.a)] = find(lk.b)
    groups: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return list(groups.values())


def _topo(members: list[str], strong: list[StoryLink], size: dict[str, int], pos: dict[str, int]) -> list[str]:
    """Defines before uses; ties (and cycles) by size, larger first, then story order."""
    mine = set(members)
    indeg = {m: 0 for m in members}
    uses = defaultdict(list)
    for lk in strong:
        if lk.a in mine and lk.b in mine:
            u = lk.b if lk.defines == lk.a else lk.a
            indeg[u] += 1
            uses[lk.defines].append(u)
    out: list[str] = []
    left = set(members)
    while left:
        low = min(indeg[m] for m in left)
        ready = [m for m in left if indeg[m] == low]
        m = min(ready, key=lambda m: (-size[m], pos[m]))
        out.append(m)
        left.discard(m)
        for u in uses[m]:
            indeg[u] -= 1
    return out


def _reason(sid: str, order: list[str], strong: list[StoryLink]) -> str | None:
    """Why a story sits where it does in its thread: its best link to an earlier story, else to a later one."""
    at = {s: i for i, s in enumerate(order)}
    mine = [lk for lk in strong if sid in (lk.a, lk.b) and (lk.b if lk.a == sid else lk.a) in at]
    if not mine:
        return None

    def other(lk):
        return lk.b if lk.a == sid else lk.a

    def key(lk):
        earlier = at[other(lk)] < at[sid]
        return (not earlier, lk.defines == sid, _KIND_RANK[lk.kind], at[other(lk)])
    lk = min(mine, key=key)
    o = other(lk)
    verb = {("calls", False): "calls", ("data", False): "uses",
            ("calls", True): "called by", ("data", True): "used by"}[(lk.kind, lk.defines == sid)]
    return f"{'←' if at[o] < at[sid] else '→'} {verb} {at[o] + 1}"


def _fixed_name(story: Story, strong: list[StoryLink], x: _Ctx) -> str:
    """`main function` in its folder: the defining story's function other stories cite most, else its first."""
    cited = defaultdict(int)
    for lk in strong:
        for n in lk.facts:
            cited[n] += 1
    fns = [n for n in story.nodes if n in x.im.nodes and x.im.nodes[n].kind == "function"] or story.nodes
    if not fns:
        return story.title
    main = min(fns, key=lambda n: (-cited[n], fns.index(n)))
    folder = posixpath.dirname(rel_path(x, x.local(main)))
    return f"`{x.label(main)}` in {folder}" if folder else f"`{x.label(main)}`"


def build_threads(ss: StorySet, links: list[StoryLink], x: _Ctx,
                  open_counts: dict[str, tuple[int, int]] | None = None) -> tuple[list[Thread], dict[str, str]]:
    """Threads in reading order (by open hazards, open checks, then changed functions), each with its stories in
    reading order, and each placed story's reason. `open_counts`: story id -> (open hazards, open checks). Tests
    stories stay out."""
    open_counts = open_counts or {}
    by = {s.id: s for s in ss.stories}
    pos = {s.id: i for i, s in enumerate(ss.stories)}
    ids = [s.id for s in ss.stories if s.kind != "tests"]
    strong = [lk for lk in links if lk.strength == "strong" and lk.a in by and lk.b in by
              and by[lk.a].kind != "tests" and by[lk.b].kind != "tests"]
    size = {i: len(by[i].nodes) for i in ids}
    drafts = []
    for members in _components(ids, strong):
        order = _topo(members, strong, size, pos)
        hz = sum(open_counts.get(s, (0, 0))[0] for s in order)
        ck = sum(open_counts.get(s, (0, 0))[1] for s in order)
        drafts.append(((-hz, -ck, -sum(size[s] for s in order), pos[order[0]]), order))
    threads, reasons = [], {}
    for n, (_, order) in enumerate(sorted(drafts), 1):
        first = by[order[0]]
        threads.append(Thread(id=f"T{n}", name=_fixed_name(first, strong, x), purpose=first.summary, stories=order,
                              cls=sorted({c for s in order for c in by[s].cls})))
        for s in order[1:]:
            r = _reason(s, order, strong)
            if r:
                reasons[s] = r
    return threads, reasons
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: PASS: `13 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `559 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_reading.py backend/codetortoise/reading.py
git commit -m "feat(reading): stories link by calls, data, file or CL; strong links make threads read defines before uses"
```

### Task 2: How the threads connect

Spec §4.3. `connections` finds the strongest connection of every pair of threads:
1. `caller`: a common caller within 3 reverse call hops of both threads' changed functions, an entry point preferred, else the nearest;
2. `vocabulary`: a struct both use, a changed header both include or edit, a changed macro both use;
3. `condition`: both built only for one target while the review spans several, or both changed under the same `#if` condition;
4. `place`: their files share a folder holding no other thread's files;
5. `bundled`: none of these; they share a CL, an author or only the review.

Each keeps its facts (node ids, paths, CLs). `cparse.preproc_spans` gives each preprocessor branch its condition (tree-sitter), skipping include guards and negating an `#ifndef` in its `#else`. A pair is shown unless shown pairs of the same or a stronger kind already join it; a thread with nothing but `bundled` gets one arc, to the thread nearest it by folder (ties: one sharing a CL, then an author).

**Files:**
- Test: `backend/tests/test_cparse.py`
- Test: `backend/tests/test_reading.py`
- Modify: `backend/codetortoise/cparse.py`
- Modify: `backend/codetortoise/reading.py`

**Interfaces:**
- Consumes: `Thread`, `build_threads` (Task 1); `PieceSet` (targets per file); `analysis.entrypoint_patterns`.
- Produces: `cparse.preproc_spans(path: str, text: str) -> list[tuple[int, int, str]]` (start line, end line, condition);
  `reading.CALLER_HOPS = 3`; `reading.Connection(a, b, kind, text, facts, shown=False)` with `kind` in `caller | vocabulary | condition | place | bundled`;
  `reading.connections(threads, ss, x, pieces: PieceSet | None = None) -> list[Connection]` (strongest first).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_cparse.py` (diff):

```diff
diff --git a/backend/tests/test_cparse.py b/backend/tests/test_cparse.py
index 38649b2..0c9fa4f 100644
--- a/backend/tests/test_cparse.py
+++ b/backend/tests/test_cparse.py
@@ -1,4 +1,4 @@
-from codetortoise.cparse import is_header, is_source, parse_source
+from codetortoise.cparse import is_header, is_source, parse_source, preproc_spans
 
 CPP = """
 #include "cpp/engine.h"
@@ -70,3 +70,29 @@ def test_large_files_parse_without_crashing(tmp_path):
     r = subprocess.run([sys.executable, "-c", code, str(tmp_path / "big.c")], capture_output=True, text=True)
     assert r.returncode == 0, r.stderr[-500:]
     assert r.stdout.split() == ["400", "3193", "3199"]
+
+
+GUARDED = """#ifndef UART_H
+#define UART_H
+#ifdef CONFIG_WIN
+int f(void) { return 1; }
+#elif defined(X)
+int g;
+#else
+int h;
+#endif
+#if FOO > 1
+int k;
+#endif
+#endif
+"""
+
+
+def test_preproc_spans_give_each_branch_its_condition_and_skip_include_guards():
+    assert preproc_spans("a.h", GUARDED) == [(3, 4, "defined(CONFIG_WIN)"), (5, 6, "defined(X)"), (7, 8, "!defined(X)"),
+                                             (10, 12, "FOO > 1")]
+
+
+def test_preproc_spans_negate_an_ifndef_in_its_else_branch():
+    text = "#ifndef NO_LOG\nint a;\n#else\nint b;\n#endif\n"
+    assert preproc_spans("a.c", text) == [(1, 2, "!defined(NO_LOG)"), (3, 4, "defined(NO_LOG)")]
```

`backend/tests/test_reading.py` (diff):

```diff
diff --git a/backend/tests/test_reading.py b/backend/tests/test_reading.py
index 46965fc..75f48c6 100644
--- a/backend/tests/test_reading.py
+++ b/backend/tests/test_reading.py
@@ -1,8 +1,8 @@
 """How a review reads (spec 2026-10-07-review-reading §4–§8): story links, threads, connections, reading order."""
-from test_stories import _edit, _world
+from test_stories import _edit, _in_cls, _same, _world
 
 from codetortoise.board import analyse
-from codetortoise.reading import build_threads, story_links
+from codetortoise.reading import Thread, build_threads, connections, story_links
 from codetortoise.stories import Story, StorySet
 
 
@@ -126,3 +126,113 @@ def test_cl_links_name_each_shared_changelist():
     c = _world([_edit("p", "src/a.c"), _edit("q", "lib/b.c")])
     (lk,) = story_links(_set(["N1"], ["N2"], cls={"S1": [11, 12], "S2": [11, 12]}), _x(c))
     assert lk.text == "both arrive in CL 11 and CL 12" and lk.facts == ["CL 11", "CL 12"]
+
+
+# ---- §4.3 thread connections
+def _threads(*groups):
+    """One thread per group of story ids."""
+    return [Thread(id=f"T{i}", name=f"t{i}", purpose="", stories=list(g)) for i, g in enumerate(groups, 1)]
+
+
+def _conn(conns, a, b):
+    return next(k for k in conns if {k.a, k.b} == {a, b})
+
+
+def test_threads_whose_changes_share_a_caller_within_three_hops_meet_there_preferring_an_entry_point():
+    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _same("helper", "app/h.c"),
+                _same("main", "app/main.c")],
+               calls=[("helper", "send"), ("helper", "init"), ("main", "helper")])
+    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
+    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
+    assert (k.kind, k.text, k.facts, k.shown) == ("caller", "both run inside `main`", ["N4", "N1", "N2"], True)
+    c.cfg.entrypoint_patterns = []
+    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
+    assert k.text == "both run inside `helper`"
+
+
+def test_a_caller_four_hops_away_is_not_shared():
+    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _same("a", "x/a.c"), _same("b", "x/b.c"),
+                _same("cc", "x/c.c"), _same("main", "app/main.c")],
+               calls=[("a", "send"), ("b", "a"), ("cc", "b"), ("main", "cc"), ("main", "init")])
+    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
+    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
+    assert k.kind != "caller"
+    c.impact.edges.append(c.impact.edges[0].model_copy(update={"id": "E9", "src": "N6", "dst": "N3"}))   # main → a too
+    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
+    assert (k.kind, k.facts) == ("caller", ["N6", "N1", "N2"])
+
+
+def test_threads_using_one_struct_share_vocabulary():
+    c = _world([_edit("cfg", "drv/a.c"), _edit("rep", "svc/b.c")],
+               fields=[("cfg", "Uart", "baud", "write", "unchanged"), ("rep", "Uart", "errors", "read", "unchanged")])
+    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
+    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
+    assert (k.kind, k.text, k.facts) == ("vocabulary", "both use `struct Uart`", ["N3", "N4"])
+
+
+def test_threads_using_a_changed_macro_or_including_a_changed_header_share_vocabulary():
+    from codetortoise.diffmap import TypeChange
+    from codetortoise.vcs.model import FileChange
+    c = _world([("cfg", "drv/a.c", ["a = 0;"], ["a = UART_MAX;"]), ("rep", "svc/b.c", ["b = 0;"], ["b = UART_MAX + 1;"])])
+    c.dm.types.append(TypeChange(file="/w/drv/uart.h", depot="//d/w/drv/uart.h", name="UART_MAX", kind="macro_changed"))
+    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
+    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
+    assert (k.kind, k.text, k.facts) == ("vocabulary", "both use `UART_MAX`", ["drv/uart.h"])
+    c = _world([_edit("cfg", "drv/a.c"), _edit("rep", "svc/b.c")])
+    for f in c.cs.files:
+        f.after = '#include "uart.h"\n' + f.after
+    c.cs.files.append(FileChange(depot="//d/w/drv/uart.h", local="/w/drv/uart.h", action="edit", before="\n",
+                                 after="#define UART_MAX 4\n"))
+    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
+    assert (k.kind, k.text, k.facts) == ("vocabulary", "both include `drv/uart.h`", ["drv/uart.h"])
+
+
+def test_threads_built_only_for_one_target_of_several_or_under_one_condition_share_it():
+    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c"), _edit("h", "z/h.c")])
+    ss = _set(["N1"], ["N2"], ["N3"], cls={"S1": [1], "S2": [2], "S3": [3]})
+    for s, t in zip(ss.stories, (["fw"], ["fw"], ["host"]), strict=True):
+        s.targets = t
+    conns = connections(_threads(["S1"], ["S2"], ["S3"]), ss, _x(c))
+    assert (_conn(conns, "T1", "T2").kind, _conn(conns, "T1", "T2").text) == ("condition", "both build only for `fw`")
+    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c")])
+    for f in c.cs.files:
+        f.after = "#ifdef CONFIG_WIN\n" + f.after + "#endif\n"
+    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
+    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
+    assert (k.kind, k.text, k.facts) == ("condition", "both sit under `#if defined(CONFIG_WIN)`", ["x/a.c", "y/b.c"])
+
+
+def test_threads_alone_in_a_folder_share_the_place_and_otherwise_only_their_bundle():
+    c = _world([_edit("a", "src/util/win32/a.c"), _edit("b", "src/util/win32/b.c"), _edit("c", "src/util/c.c"),
+                _edit("d", "lib/d.c")])
+    _in_cls(c, {"src/util/win32/a.c": 11, "src/util/win32/b.c": 11, "src/util/c.c": 11, "lib/d.c": 12})
+    c.cs.cls[1].user = c.cs.cls[0].user = "ana"
+    ss = _set(["N1"], ["N2"], ["N3"], ["N4"], cls={"S1": [11], "S2": [11], "S3": [11], "S4": [12]})
+    conns = connections(_threads(["S1"], ["S2"], ["S3"], ["S4"]), ss, _x(c))
+    assert (_conn(conns, "T1", "T2").kind, _conn(conns, "T1", "T2").text) == ("place", "both live under `src/util/win32`")
+    assert _conn(conns, "T1", "T3").text == "nothing besides arriving in CL 11"      # src/util holds T2's files too
+    assert (_conn(conns, "T1", "T4").kind, _conn(conns, "T1", "T4").text) == ("bundled", "nothing besides their author ana")
+    c.cs.cls[1].user = "bo"
+    conns = connections(_threads(["S1"], ["S2"], ["S3"], ["S4"]), ss, _x(c))
+    assert _conn(conns, "T1", "T4").text == "nothing besides arriving in this review"
+    ss.stories[3].cls = [11, 12]
+    conns = connections(_threads(["S1"], ["S2"], ["S3"], ["S4"]), ss, _x(c))
+    assert _conn(conns, "T1", "T4").text == "nothing besides arriving in CL 11"
+
+
+def test_a_lone_threads_arc_goes_to_a_thread_sharing_its_cl_when_folders_tie():
+    c = _world([_edit("a", "p/a.c"), _edit("b", "q/b.c"), _edit("c", "r/c.c")])
+    ss = _set(["N1"], ["N2"], ["N3"], cls={"S1": [1], "S2": [2], "S3": [2]})
+    conns = connections(_threads(["S1"], ["S2"], ["S3"]), ss, _x(c))
+    assert sorted((k.a, k.b) for k in conns if k.shown) == [("T1", "T2"), ("T2", "T3")]
+
+
+def test_only_pairs_not_already_joined_by_as_strong_a_connection_are_shown_and_a_lone_thread_gets_one_bundled_arc():
+    c = _world([_edit("a", "src/a.c"), _edit("b", "src/k/b.c"), _edit("c", "src/k/c.c"), _edit("d", "src/k/d/d.c"),
+                _same("main", "app/main.c")],
+               calls=[("main", "a"), ("main", "b"), ("main", "c")])
+    ss = _set(["N1"], ["N2"], ["N3"], ["N4"], cls={"S1": [1], "S2": [2], "S3": [3], "S4": [4]})
+    conns = connections(_threads(["S1"], ["S2"], ["S3"], ["S4"]), ss, _x(c))
+    shown = sorted((k.a, k.b, k.kind) for k in conns if k.shown)
+    assert shown == [("T1", "T2", "caller"), ("T1", "T3", "caller"), ("T2", "T4", "bundled")]
+    assert len(conns) == 6
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_cparse.py tests/test_reading.py -q`
Expected: FAIL: `2 errors`; the first error is `ImportError: cannot import name 'preproc_spans' from 'codetortoise.cparse' (backend/codetortoise/cparse.py)`

- [ ] **Step 3: Implement**

`backend/codetortoise/cparse.py` (diff):

```diff
diff --git a/backend/codetortoise/cparse.py b/backend/codetortoise/cparse.py
index 4431b38..aaa4a85 100644
--- a/backend/codetortoise/cparse.py
+++ b/backend/codetortoise/cparse.py
@@ -2,6 +2,7 @@
 from __future__ import annotations
 
 import hashlib
+import re
 from dataclasses import dataclass, field
 from pathlib import PurePath
 
@@ -198,3 +199,48 @@ def parse_source(path: str, text: str) -> ParsedFile:
         for ch in reversed(node.children):
             stack.append((ch, child_scope, child_fn))
     return out
+
+
+_GUARD = re.compile(r"(_H|_HH|_HPP|_HXX|_INCLUDED)_*$")
+
+
+def _negate(cond: str) -> str:
+    if cond.startswith("!defined(") and cond.endswith(")"):
+        return cond[1:]
+    if cond.startswith("defined(") and cond.endswith(")") and cond.count("(") == 1:
+        return "!" + cond
+    return f"!({cond})"
+
+
+def preproc_spans(path: str, text: str) -> list[tuple[int, int, str]]:
+    """(first line, last line, condition) for each branch of each `#if`/`#ifdef`/`#ifndef` (`#elif` and `#else`
+    included), in source order; include guards are left out. `#ifdef X` is `defined(X)`, `#ifndef X` is
+    `!defined(X)` and an `#else` negates the branch before it."""
+    src = text.encode("utf-8", errors="replace")
+    tree = _parser_for(path).parse(src)
+    out: list[tuple[int, int, str]] = []
+
+    def branch(node: ts.Node, cond: str) -> None:
+        alt = node.child_by_field_name("alternative")
+        end = alt.start_point.row if alt is not None else node.end_point.row + 1
+        out.append((node.start_point.row + 1, end, cond))
+        if alt is not None:
+            if alt.type == "preproc_elif":
+                c = alt.child_by_field_name("condition")
+                branch(alt, norm_ws(_txt(src, c)) if c is not None else "")
+            else:
+                out.append((alt.start_point.row + 1, alt.end_point.row + 1, _negate(cond)))
+
+    stack = [tree.root_node]
+    while stack:
+        node = stack.pop()
+        if node.type == "preproc_ifdef":
+            neg = any(ch.type == "#ifndef" for ch in node.children)
+            name = _txt(src, node.child_by_field_name("name"))
+            if not (neg and _GUARD.search(name)):
+                branch(node, f"{'!' if neg else ''}defined({name})")
+        elif node.type == "preproc_if":
+            c = node.child_by_field_name("condition")
+            branch(node, norm_ws(_txt(src, c)) if c is not None else "")
+        stack.extend(reversed(node.children))
+    return sorted(out)
```

`backend/codetortoise/reading.py` (diff):

```diff
diff --git a/backend/codetortoise/reading.py b/backend/codetortoise/reading.py
index 4cf377b..a1ecea8 100644
--- a/backend/codetortoise/reading.py
+++ b/backend/codetortoise/reading.py
@@ -3,16 +3,25 @@ how the threads connect, the order to read them in, each story's contract rows a
 To check list. Everything here is computed from the analysis; the strong model only rewords it (llm/threads.py)."""
 from __future__ import annotations
 
+import fnmatch
 import posixpath
+import re
 from collections import defaultdict
+from dataclasses import dataclass, field
 from typing import Literal
 
 from pydantic import BaseModel, Field
 
 from codetortoise.board import _Ctx
+from codetortoise.cparse import is_header, preproc_spans
+from codetortoise.pieces import PieceSet
 from codetortoise.stories import Story, StorySet
 
 _KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}
+ConnKind = Literal["caller", "vocabulary", "condition", "place", "bundled"]
+_CONN_RANK = {"caller": 1, "vocabulary": 2, "condition": 3, "place": 4, "bundled": 5}
+CALLER_HOPS = 3
+_INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.M)
 
 
 class StoryLink(BaseModel):
@@ -36,6 +45,16 @@ class Thread(BaseModel):
     open_checks: int = 0
 
 
+class Connection(BaseModel):
+    """The strongest connection between two threads (§4.3); `shown` pairs are drawn as arcs."""
+    a: str
+    b: str
+    kind: ConnKind
+    text: str
+    facts: list[str] = Field(default_factory=list)   # node ids, workspace-relative paths, targets, "CL n" or authors
+    shown: bool = False
+
+
 def rel_path(x: _Ctx, path: str | None) -> str:
     """A workspace-relative path (§12); paths outside the workspace stay as they are."""
     if not path:
@@ -238,3 +257,185 @@ def build_threads(ss: StorySet, links: list[StoryLink], x: _Ctx,
             if r:
                 reasons[s] = r
     return threads, reasons
+
+
+# ------------------------------------------------------------------ thread connections (§4.3)
+@dataclass
+class _Profile:
+    """What a thread's changed code touches, for comparing threads."""
+    nodes: set[str] = field(default_factory=set)
+    files: set[str] = field(default_factory=set)                  # workspace-relative
+    callers: dict[str, tuple[int, str]] = field(default_factory=dict)   # caller -> (hops, the changed node it reaches)
+    structs: dict[str, str] = field(default_factory=dict)          # record -> a field node of it the thread touches
+    names: set[str] = field(default_factory=set)                   # changed declarations it changes or uses
+    includes: set[str] = field(default_factory=set)                # changed headers its files include
+    targets: set[str] = field(default_factory=set)
+    conds: set[str] | None = None
+    cls: set[int] = field(default_factory=set)
+    authors: set[str] = field(default_factory=set)
+
+
+def _callers_within(x: _Ctx, start: set[str], hops: int) -> dict[str, tuple[int, str]]:
+    rev: dict[str, list[str]] = defaultdict(list)
+    for e in _live(x, {"call", "virtual"}):
+        rev[e.dst].append(e.src)
+    out: dict[str, tuple[int, str]] = {}
+    frontier = [(n, n) for n in sorted(start)]
+    for hop in range(1, hops + 1):
+        nxt = []
+        for n, origin in frontier:
+            for c in rev.get(n, []):
+                if c in start or c in out or x.is_test(c):
+                    continue
+                out[c] = (hop, origin)
+                nxt.append((c, origin))
+        frontier = nxt
+    return out
+
+
+def _profiles(threads: list[Thread], ss: StorySet, x: _Ctx, pieces: PieceSet | None) -> dict[str, _Profile]:
+    by = {s.id: s for s in ss.stories}
+    piece_files = {p.id: p.files for p in pieces.pieces} if pieces else {}
+    users = {m.cl: m.user for m in x.c.cs.cls if m.user}
+    headers = {rel_path(x, f.local) for f in x.c.cs.files if is_header(f.local)}
+    decls = [(t.name, rel_path(x, t.file)) for t in x.c.dm.types]
+    spans: dict[str, list[tuple[int, int, str]]] = {}
+    out: dict[str, _Profile] = {}
+    for t in threads:
+        p = _Profile()
+        for sid in t.stories:
+            s = by[sid]
+            p.nodes.update(s.nodes)
+            p.files.update(rel_path(x, x.local(n)) for n in s.nodes)
+            p.files.update(rel_path(x, f) for pid in s.pieces for f in piece_files.get(pid, []))
+            p.targets.update(tg for tg in s.targets if tg != "unknown")
+            p.cls.update(s.cls)
+        p.files.discard("")
+        p.authors = {users[c] for c in p.cls if c in users}
+        fns = sorted(n for n in p.nodes if n in x.im.nodes and x.im.nodes[n].kind == "function")
+        p.callers = _callers_within(x, set(fns), CALLER_HOPS)
+        for e in _live(x, {"reads", "writes"}):
+            if e.src in p.nodes:
+                rec = x.label(e.dst).rsplit("::", 1)[0]
+                p.structs.setdefault(rec, e.dst)
+        bodies, conds = [], None
+        for n in fns:
+            key = x.im.nodes[n].key
+            fn = x.fa.get(key) or x.fb.get(key)
+            fc = x.texts.get(fn.file) if fn else None
+            if not fn or not fc or fc.after is None:
+                conds = set()
+                continue
+            lines = fc.after.splitlines()
+            bodies.append("\n".join(lines[fn.start_line - 1:fn.end_line]))
+            if fn.file not in spans:
+                spans[fn.file] = preproc_spans(fn.file, fc.after)
+            here = {c for lo, hi, c in spans[fn.file] if lo <= fn.start_line <= hi}
+            conds = here if conds is None else conds & here
+        p.conds = conds or set()
+        body = "\n".join(bodies)
+        p.names = {nm for nm, f in decls if f in p.files or re.search(rf"\b{re.escape(nm)}\b", body)}
+        for f in p.files:
+            fc = x.texts.get(x.c.root.rstrip("/") + "/" + f)
+            for inc in _INCLUDE.findall(fc.after or "") if fc else []:
+                p.includes.update(h for h in headers if h == inc or h.endswith("/" + inc))
+        out[t.id] = p
+    return out
+
+
+def _is_entry(x: _Ctx, n: str) -> bool:
+    return any(fnmatch.fnmatchcase(x.label(n).split("::")[-1], pat) for pat in x.c.cfg.entrypoint_patterns)
+
+
+def _folder(files: set[str]) -> str:
+    dirs = [posixpath.dirname(f) for f in files]
+    if not dirs or any(not d for d in dirs):
+        return ""
+    common = posixpath.commonpath(dirs)
+    return "" if common in ("", ".", "/") else common
+
+
+def _connect(ta: str, tb: str, pa: _Profile, pb: _Profile, x: _Ctx, everyone: dict[str, _Profile],
+             multi_target: bool) -> Connection:
+    def conn(kind: ConnKind, text: str, facts: list[str]) -> Connection:
+        return Connection(a=ta, b=tb, kind=kind, text=text, facts=facts)
+    common = set(pa.callers) & set(pb.callers)
+    if common:
+        pool = [n for n in common if _is_entry(x, n)] or list(common)
+        c = min(pool, key=lambda n: (max(pa.callers[n][0], pb.callers[n][0]), pa.callers[n][0] + pb.callers[n][0],
+                                     x.label(n)))
+        return conn("caller", f"both run inside `{x.label(c)}`", [c, pa.callers[c][1], pb.callers[c][1]])
+    structs = sorted(set(pa.structs) & set(pb.structs))
+    if structs:
+        r = structs[0]
+        return conn("vocabulary", f"both use `struct {r}`", list(dict.fromkeys([pa.structs[r], pb.structs[r]])))
+    names = sorted(pa.names & pb.names)
+    if names:
+        f = next(f for nm, f in ((t.name, rel_path(x, t.file)) for t in x.c.dm.types) if nm == names[0])
+        return conn("vocabulary", f"both use `{names[0]}`", [f])
+    edited = sorted(f for f in pa.files & pb.files if is_header(f))
+    if edited:
+        return conn("vocabulary", f"both edit `{edited[0]}`", [edited[0]])
+    incs = sorted(pa.includes & pb.includes)
+    if incs:
+        return conn("vocabulary", f"both include `{incs[0]}`", [incs[0]])
+    if multi_target and len(pa.targets) == 1 and pa.targets == pb.targets:
+        (tg,) = pa.targets
+        return conn("condition", f"both build only for `{tg}`", [tg])
+    conds = sorted(pa.conds & pb.conds)
+    if conds:
+        return conn("condition", f"both sit under `#if {conds[0]}`", sorted(pa.files | pb.files))
+    folder = _folder(pa.files | pb.files)
+    if folder and not any(f.startswith(folder + "/") for t, p in everyone.items() if t not in (ta, tb) for f in p.files):
+        return conn("place", f"both live under `{folder}`", [folder])
+    cls = sorted(pa.cls & pb.cls)
+    if cls:
+        return conn("bundled", f"nothing besides arriving in {_cls(cls)}", [f"CL {n}" for n in cls])
+    authors = sorted(pa.authors & pb.authors)
+    if authors:
+        return conn("bundled", f"nothing besides their author {authors[0]}", authors[:1])
+    return conn("bundled", "nothing besides arriving in this review", [])
+
+
+def _depth(fa: set[str], fb: set[str]) -> int:
+    """How many leading folders the nearest pair of files shares."""
+    best = 0
+    for a in fa:
+        for b in fb:
+            da, db = posixpath.dirname(a).split("/"), posixpath.dirname(b).split("/")
+            n = 0
+            while n < min(len(da), len(db)) and da[n] == db[n] and da[n]:
+                n += 1
+            best = max(best, n)
+    return best
+
+
+def connections(threads: list[Thread], ss: StorySet, x: _Ctx, pieces: PieceSet | None = None) -> list[Connection]:
+    """The strongest connection of every pair of threads, strongest first. Shown: each pair of kinds 1–4 not already
+    joined through other shown pairs of the same or a stronger kind, and for each thread with nothing but "only
+    bundled", one arc to the thread nearest it by folder (ties: one sharing a CL, then an author, then the first)."""
+    prof = _profiles(threads, ss, x, pieces)
+    multi = len({tg for p in prof.values() for tg in p.targets}) > 1
+    pos = {t.id: i for i, t in enumerate(threads)}
+    out = [_connect(a.id, b.id, prof[a.id], prof[b.id], x, prof, multi)
+           for i, a in enumerate(threads) for b in threads[i + 1:]]
+    out.sort(key=lambda k: (_CONN_RANK[k.kind], pos[k.a], pos[k.b]))
+    parent = {t.id: t.id for t in threads}
+
+    def find(i: str) -> str:
+        while parent[i] != i:
+            i = parent[i]
+        return i
+    for k in out:
+        if k.kind != "bundled" and find(k.a) != find(k.b):
+            k.shown = True
+            parent[find(k.a)] = find(k.b)
+    joined = {t for k in out if k.kind != "bundled" for t in (k.a, k.b)}
+    for t in threads:
+        if t.id in joined or len(threads) < 2:
+            continue
+        mine = [k for k in out if t.id in (k.a, k.b)]
+        best = max(mine, key=lambda k: (_depth(prof[k.a].files, prof[k.b].files), bool(prof[k.a].cls & prof[k.b].cls),
+                                        bool(prof[k.a].authors & prof[k.b].authors), -pos[k.b if k.a == t.id else k.a]))
+        best.shown = True
+    return out
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_cparse.py tests/test_reading.py -q`
Expected: PASS: `29 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `569 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_cparse.py backend/tests/test_reading.py backend/codetortoise/cparse.py backend/codetortoise/reading.py
git commit -m "feat(reading): threads connect by a shared caller, vocabulary, condition or place, else only their bundle; arcs shown without repeats"
```

### Task 3: A story's contract rows, where its code lives, and every call path

Spec §8.1, §8.2, §6.1. `contract_rows` gives a story's Before → after: a signature row with the differing part marked (`mark` holds the character range), one repeated row when the same signature edit hits several functions, return values added and removed, fields now and no longer written, a mechanical story's repeated edit, and a count of body-only changes. `where` lists the story's files, workspace-relative and in path order, each with its changed functions, edit sizes and CL. `call_paths` lists every path ending at the story's changed functions, uncapped: its flows first (their effect text is the line), then each caller chain up to an entry point, a function nobody calls or `blast_hops` calls away; entry points first. A path longer than four steps keeps its first step and its last two, with the rest in `hidden`.

**Files:**
- Test: `backend/tests/test_reading.py`
- Modify: `backend/codetortoise/reading.py`

**Interfaces:**
- Consumes: `Story`, `Flow` (`board.py`), `board._Ctx`, `repeated.find_repeated`.
- Produces: `reading.ContractRow(kind, text, node, before, after, mark, added, removed, nodes)` with `kind` in `signature | returns | fields | repeated | body`;
  `reading.WhereFn(node, label, add, rem, cl, line)`, `reading.WhereFile(path, depot, functions)`;
  `reading.CallPath(steps, labels, kind, entry, hidden, text, flow)` with `kind` in `contract | state | call`;
  `reading.contract_rows(story, x) -> list[ContractRow]`, `reading.where(story, x) -> list[WhereFile]`, `reading.call_paths(story, x, flows) -> list[CallPath]`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_reading.py` (diff):

```diff
diff --git a/backend/tests/test_reading.py b/backend/tests/test_reading.py
index 75f48c6..6f5b595 100644
--- a/backend/tests/test_reading.py
+++ b/backend/tests/test_reading.py
@@ -2,7 +2,7 @@
 from test_stories import _edit, _in_cls, _same, _world
 
 from codetortoise.board import analyse
-from codetortoise.reading import Thread, build_threads, connections, story_links
+from codetortoise.reading import Thread, build_threads, call_paths, connections, contract_rows, story_links, where
 from codetortoise.stories import Story, StorySet
 
 
@@ -236,3 +236,100 @@ def test_only_pairs_not_already_joined_by_as_strong_a_connection_are_shown_and_a
     shown = sorted((k.a, k.b, k.kind) for k in conns if k.shown)
     assert shown == [("T1", "T2", "caller"), ("T1", "T3", "caller"), ("T2", "T4", "bundled")]
     assert len(conns) == 6
+
+
+# ---- §8.1 contract rows
+def _sig(c, name, before=None, after=None, returns=None, names=None):
+    """Give `name` a signature (before / after side) and, after, return values."""
+    for fx, sig in ((c.before[0], before), (c.after[0], after)):
+        f = next(f for f in fx.functions if f.name == name)
+        if sig:
+            f.signature = sig
+    if returns:
+        b, a = returns
+        next(f for f in c.before[0].functions if f.name == name).returns = b
+        fa = next(f for f in c.after[0].functions if f.name == name)
+        fa.returns, fa.return_names = a, names or {}
+
+
+def test_a_signature_row_marks_the_part_that_differs():
+    c = _world([_edit("send", "drv/uart.c")])
+    _sig(c, "send", "int send(int len)", "int send(unsigned len)")
+    (row,) = contract_rows(_set(["N1"]).stories[0], _x(c))
+    assert (row.kind, row.node, row.before, row.after, row.mark) == ("signature", "N1", "int send(int len)",
+                                                                     "int send(unsigned len)", [9, 17])
+    assert row.text == "`send`: `int` → `unsigned`"
+
+
+def test_the_same_signature_edit_in_two_functions_is_one_repeated_row():
+    c = _world([_edit("a", "x/a.c"), _edit("b", "x/b.c"), _edit("solo", "x/c.c")])
+    _sig(c, "a", "void a(int x)", "void a(int x, const opts *o)")
+    _sig(c, "b", "void b(char *s)", "void b(char *s, const opts *o)")
+    _sig(c, "solo", "void solo(void)", "int solo(void)")
+    rows = contract_rows(_set(["N1", "N2", "N3"]).stories[0], _x(c))
+    assert [(r.kind, r.text, r.nodes) for r in rows] == [
+        ("repeated", "2 signatures gained `const opts *o`", ["N1", "N2"]),
+        ("signature", "`solo`: `void` → `int`", ["N3"])]
+
+
+def test_return_values_fields_and_body_only_changes_each_get_a_row():
+    c = _world([_edit("send", "drv/uart.c"), _edit("config", "drv/cfg.c"), _edit("p", "x/p.c"), _edit("q", "x/q.c")],
+               fields=[("config", "Uart", "errors", "write", "added")])
+    _sig(c, "send", returns=(["0"], ["0", "-2"]), names={"-2": "UART_EBUSY"})
+    c.impact.edges.append(c.impact.edges[0].model_copy(update={"id": "E9", "status": "removed", "dst": "N6"}))
+    c.impact.nodes["N6"] = c.impact.nodes["N5"].model_copy(update={"id": "N6", "key": "field:c:@S@Uart@FI@old",
+                                                                    "label": "Uart::old"})
+    rows = contract_rows(_set(["N1", "N2", "N3", "N4"]).stories[0], _x(c))
+    assert [(r.kind, r.text, r.added, r.removed, r.nodes) for r in rows] == [
+        ("returns", "`send` can now return UART_EBUSY (-2)", ["UART_EBUSY (-2)"], [], ["N1"]),
+        ("fields", "`config` now writes `Uart::errors`; no longer writes `Uart::old`", ["Uart::errors"], ["Uart::old"],
+         ["N2"]),
+        ("body", "2 functions changed only inside the body", [], [], ["N3", "N4"])]
+
+
+def test_a_mechanical_story_is_one_repeated_row_and_added_or_removed_functions_say_so():
+    from test_stories import _mech
+
+    from codetortoise.stories import build_stories
+    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c", var="b"), ("fresh", "src/n.c", None, ["x = 1;"])])
+    ss, _ = build_stories(c)
+    m = next(s for s in ss.stories if s.kind == "mechanical")
+    assert [(r.kind, r.text, r.nodes) for r in contract_rows(m, _x(c))] == [
+        ("repeated", "`git_vector_free` → `git_vector_dispose` at 2 sites", ["N1", "N2"])]
+    (row,) = contract_rows(_set(["N3"]).stories[0], _x(c))
+    assert (row.kind, row.text, row.before, row.after) == ("signature", "`fresh` added", "", "void fresh(void)")
+
+
+# ---- §6.1 where
+def test_where_lists_each_file_and_its_functions_with_edit_size_and_cl():
+    c = _world([_edit("a", "drv/uart.c"), ("b", "drv/uart.c", ["x;"], ["y;", "z;"]), _edit("c", "svc/log.c")])
+    _in_cls(c, {"drv/uart.c": 11, "svc/log.c": 12})
+    got = where(_set(["N1", "N2", "N3"]).stories[0], _x(c))
+    assert [(f.path, f.depot, [(fn.label, fn.add, fn.rem, fn.cl, fn.line) for fn in f.functions]) for f in got] == [
+        ("drv/uart.c", "//d/w/drv/uart.c", [("a", 1, 0, 11, 1), ("b", 2, 1, 11, 6)]),
+        ("svc/log.c", "//d/w/svc/log.c", [("c", 1, 0, 12, 1)])]
+
+
+# ---- §8.2 call paths
+def test_every_caller_chain_up_to_an_entry_point_is_a_call_path_long_ones_folded_flows_first():
+    from codetortoise.board import Flow
+    c = _world([_edit("send", "drv/uart.c"), _same("low", "a/l.c"), _same("mid", "a/m.c"), _same("app", "a/a.c"),
+                _same("main", "a/main.c"), _same("other", "b/o.c")],
+               calls=[("low", "send"), ("mid", "low"), ("app", "mid"), ("main", "app"), ("other", "send")])
+    _sig(c, "send", "int send(int len)", "int send(unsigned len)")
+    fl = Flow(id="FL1", path=["N6", "N1"], tag="contract", lands="N6", severity="medium", text="", what="",
+              effect="Arguments other passes to send are converted.", check="")
+    story = _set(["N1"]).stories[0]
+    story.flows = ["FL1"]
+    paths = call_paths(story, _x(c), [fl])
+    assert [(p.steps, p.kind, p.entry, p.hidden, p.text, p.flow) for p in paths] == [
+        (["N6", "N1"], "contract", None, [], "Arguments other passes to send are converted.", "FL1"),
+        (["N5", "N4", "N3", "N2", "N1"], "call", "N5", ["N4", "N3"], "calls `send`, whose signature changed", None)]
+    assert paths[1].labels == ["main", "app", "mid", "low", "send"]
+
+
+def test_call_paths_are_not_capped():
+    fns = [_edit("send", "drv/uart.c")] + [_same(f"c{i}", f"k/c{i}.c") for i in range(30)]
+    c = _world(fns, calls=[(f"c{i}", "send") for i in range(30)])
+    paths = call_paths(_set(["N1"]).stories[0], _x(c), [])
+    assert len(paths) == 30 and paths[0].text == "calls `send`, whose body changed"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: FAIL: `1 error`; the first error is `ImportError: cannot import name 'call_paths' from 'codetortoise.reading' (backend/codetortoise/reading.py)`

- [ ] **Step 3: Implement**

`backend/codetortoise/reading.py` (diff):

```diff
diff --git a/backend/codetortoise/reading.py b/backend/codetortoise/reading.py
index a1ecea8..b207fdd 100644
--- a/backend/codetortoise/reading.py
+++ b/backend/codetortoise/reading.py
@@ -12,9 +12,9 @@ from typing import Literal
 
 from pydantic import BaseModel, Field
 
-from codetortoise.board import _Ctx
+from codetortoise.board import Flow, _count, _Ctx
 from codetortoise.cparse import is_header, preproc_spans
-from codetortoise.pieces import PieceSet
+from codetortoise.pieces import PieceSet, node_cl
 from codetortoise.stories import Story, StorySet
 
 _KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}
@@ -55,6 +55,45 @@ class Connection(BaseModel):
     shown: bool = False
 
 
+class ContractRow(BaseModel):
+    """One line of a story's Before → after (§8.1)."""
+    kind: Literal["signature", "returns", "fields", "repeated", "body"]
+    text: str
+    node: str | None = None
+    before: str = ""
+    after: str = ""
+    mark: list[int] = Field(default_factory=list)    # [start, end) of the part of `after` that differs
+    added: list[str] = Field(default_factory=list)   # return values now returned, fields now written
+    removed: list[str] = Field(default_factory=list)
+    nodes: list[str] = Field(default_factory=list)   # the functions it is about
+
+
+class WhereFn(BaseModel):
+    node: str
+    label: str
+    add: int = 0
+    rem: int = 0
+    cl: int | None = None
+    line: int | None = None           # new side (old side for a removed function)
+
+
+class WhereFile(BaseModel):
+    path: str                         # workspace-relative
+    depot: str | None = None
+    functions: list[WhereFn] = Field(default_factory=list)
+
+
+class CallPath(BaseModel):
+    """A caller chain ending at a story's changed code (§8.2): a flow's path, or calls up to an entry point."""
+    steps: list[str]                  # node ids, entry first
+    labels: list[str]
+    kind: Literal["contract", "state", "call"]
+    entry: str | None = None          # the first step, when it is an entry point
+    hidden: list[str] = Field(default_factory=list)   # folded steps (a path of more than four steps)
+    text: str
+    flow: str | None = None
+
+
 def rel_path(x: _Ctx, path: str | None) -> str:
     """A workspace-relative path (§12); paths outside the workspace stay as they are."""
     if not path:
@@ -439,3 +478,173 @@ def connections(threads: list[Thread], ss: StorySet, x: _Ctx, pieces: PieceSet |
                                         bool(prof[k.a].authors & prof[k.b].authors), -pos[k.b if k.a == t.id else k.a]))
         best.shown = True
     return out
+
+
+# ------------------------------------------------------------------ contract rows (§8.1), where (§6.1), paths (§8.2)
+_IDENT = re.compile(r"\w")
+
+
+def _differ(before: str, after: str) -> tuple[str, str, int, int]:
+    """The differing middle of two signatures, widened to whole words: (old part, new part, start, end in after)."""
+    i = 0
+    while i < min(len(before), len(after)) and before[i] == after[i]:
+        i += 1
+    j = 0
+    while j < min(len(before), len(after)) - i and before[-1 - j] == after[-1 - j]:
+        j += 1
+    while i > 0 and _IDENT.match(after[i - 1]) and (i < len(after) - j and _IDENT.match(after[i])
+                                                    or i < len(before) - j and _IDENT.match(before[i])):
+        i -= 1
+    while j > 0 and _IDENT.match(after[-j]) and (len(after) - j > i and _IDENT.match(after[-j - 1])
+                                                 or len(before) - j > i and _IDENT.match(before[-j - 1])):
+        j -= 1
+    return before[i:len(before) - j], after[i:len(after) - j], i, len(after) - j
+
+
+def _vals(fn, vals) -> list[str]:
+    return [f"{fn.return_names[v]} ({v})" if v in fn.return_names else v for v in vals]
+
+
+def _story_fns(story: Story, x: _Ctx) -> list[str]:
+    return [n for n in story.nodes if n in x.im.nodes and x.im.nodes[n].kind == "function"]
+
+
+def contract_rows(story: Story, x: _Ctx) -> list[ContractRow]:
+    """Signatures (one row per repeated signature edit), return values, field writes, a mechanical story's repeated
+    edit, then the functions changed only inside their body."""
+    fns = _story_fns(story, x)
+    if story.kind == "mechanical":
+        subs = [story.sub] if story.sub else story.subs
+        sites = story.counts.get("sites", 0)
+        return [ContractRow(kind="repeated", nodes=fns,
+                            text=f"`{old}` → `{new}`" + (f" at {sites} sites" if len(subs) == 1 and sites else ""))
+                for old, new in subs]
+    sigs, singles, rets, flds, body = defaultdict(list), [], [], [], []
+    for n in fns:
+        key, label = x.im.nodes[n].key, x.label(n)
+        fb, fa = x.fb.get(key), x.fa.get(key)
+        touched = False
+        if fb is None or fa is None:
+            singles.append(ContractRow(kind="signature", node=n, nodes=[n], before=fb.signature if fb else "",
+                                       after=fa.signature if fa else "", text=f"`{label}` {'added' if fb is None else 'removed'}"))
+            continue
+        if fb.signature != fa.signature:
+            old, new, i, j = _differ(fb.signature, fa.signature)
+            sigs[(old.strip(" ,;"), new.strip(" ,;"))].append((n, fb.signature, fa.signature, [i, j]))
+            touched = True
+        added, removed = [v for v in fa.returns if v not in fb.returns], [v for v in fb.returns if v not in fa.returns]
+        if added or removed:
+            parts = ([f"can now return {', '.join(_vals(fa, added))}"] if added else []) + \
+                    ([f"no longer returns {', '.join(_vals(fb, removed))}"] if removed else [])
+            rets.append(ContractRow(kind="returns", node=n, nodes=[n], added=_vals(fa, added), removed=_vals(fb, removed),
+                                    text=f"`{label}` " + "; ".join(parts)))
+            touched = True
+        writes = [e for e in x.im.edges if e.src == n and e.kind == "writes" and e.status in ("added", "removed")]
+        now = [x.label(e.dst) for e in writes if e.status == "added"]
+        gone = [x.label(e.dst) for e in writes if e.status == "removed"]
+        if now or gone:
+            parts = ([f"now writes {', '.join(f'`{f}`' for f in now)}"] if now else []) + \
+                    ([f"no longer writes {', '.join(f'`{f}`' for f in gone)}"] if gone else [])
+            flds.append(ContractRow(kind="fields", node=n, nodes=[n], added=now, removed=gone,
+                                    text=f"`{label}` " + "; ".join(parts)))
+            touched = True
+        if not touched:
+            body.append(n)
+    repeated = []
+    for (old, new), got in sigs.items():
+        if len(got) >= 2:
+            what = (f"gained `{new}`" if not old else f"lost `{old}`" if not new else f"changed `{old}` → `{new}`")
+            repeated.append(ContractRow(kind="repeated", nodes=[g[0] for g in got], text=f"{len(got)} signatures {what}"))
+        else:
+            n, b, a, mark = got[0]
+            singles.insert(0, ContractRow(kind="signature", node=n, nodes=[n], before=b, after=a, mark=mark,
+                                          text=f"`{x.label(n)}`: `{old}` → `{new}`"))
+    rows = repeated + singles + rets + flds
+    if body:
+        rows.append(ContractRow(kind="body", nodes=body, text=f"{len(body)} function{'s' if len(body) > 1 else ''} "
+                                                             "changed only inside the body"))
+    return rows
+
+
+def where(story: Story, x: _Ctx) -> list[WhereFile]:
+    """The story's files (workspace-relative, in path order), each with its changed functions, edit sizes and CL."""
+    files: dict[str, WhereFile] = {}
+    for n in _story_fns(story, x):
+        key = x.im.nodes[n].key
+        fb, fa = x.fb.get(key), x.fa.get(key)
+        fn = fa or fb
+        local = x.local(n)
+        if not fn or not local:
+            continue
+        fc = x.texts.get(local)
+        if fa is not None and fc is not None:
+            add, rem = _count(fc.before, fc.after, fa.start_line, fa.end_line)
+        else:
+            add, rem = 0, fn.end_line - fn.start_line + 1
+        wf = files.setdefault(local, WhereFile(path=rel_path(x, local), depot=fc.depot if fc else None))
+        wf.functions.append(WhereFn(node=n, label=x.label(n), add=add, rem=rem, cl=node_cl(x, n), line=fn.start_line))
+    for wf in files.values():
+        wf.functions.sort(key=lambda f: (f.line or 0, f.label))
+    return sorted(files.values(), key=lambda f: f.path)
+
+
+def _change_text(x: _Ctx, n: str) -> str:
+    """What changed in a function, as the end of "calls `f`, …"."""
+    key = x.im.nodes[n].key
+    fb, fa = x.fb.get(key), x.fa.get(key)
+    if fb is None:
+        return "which is new"
+    if fa is None:
+        return "which was removed"
+    if fb.signature != fa.signature:
+        return "whose signature changed"
+    added = [v for v in fa.returns if v not in fb.returns]
+    if added:
+        return f"which can now return {', '.join(_vals(fa, added))}"
+    now = [x.label(e.dst) for e in x.im.edges if e.src == n and e.kind == "writes" and e.status == "added"]
+    if now:
+        return f"which now writes `{now[0]}`"
+    return "whose body changed"
+
+
+def _path(steps: list[str], kind: str, x: _Ctx, text: str, flow: str | None = None) -> CallPath:
+    return CallPath(steps=steps, labels=[x.label(n) for n in steps], kind=kind,
+                    entry=steps[0] if _is_entry(x, steps[0]) else None,
+                    hidden=steps[1:-2] if len(steps) > 4 else [], text=text, flow=flow)
+
+
+def call_paths(story: Story, x: _Ctx, flows: list[Flow]) -> list[CallPath]:
+    """Every path ending at the story's changed functions, uncapped: its flows first (their effect is the line), then
+    each caller chain up to an entry point, a function nobody calls or `blast_hops` calls away, entry points first."""
+    mine = [f for f in flows if f.id in story.flows]
+    out = [_path(list(f.path), f.tag, x, f.effect, f.id) for f in mine]
+    seen = {tuple(p.steps) for p in out}
+    seeds = set(_story_fns(story, x))
+    rev: dict[str, list[str]] = defaultdict(list)
+    for e in _live(x, {"call", "virtual"}):
+        if not x.is_test(e.src):
+            rev[e.dst].append(e.src)
+    pred: dict[str, str] = {}
+    frontier, starts = sorted(seeds), []
+    for hop in range(1, x.c.cfg.blast_hops + 1):
+        nxt = []
+        for n in frontier:
+            for c in sorted(set(rev.get(n, [])), key=lambda m: x.label(m)):
+                if c in seeds or c in pred:
+                    continue
+                pred[c] = n
+                if _is_entry(x, c) or not rev.get(c) or hop == x.c.cfg.blast_hops:
+                    starts.append(c)
+                else:
+                    nxt.append(c)
+        frontier = nxt
+    calls = []
+    for s in starts:
+        steps = [s]
+        while steps[-1] in pred:
+            steps.append(pred[steps[-1]])
+        if tuple(steps) not in seen:
+            seen.add(tuple(steps))
+            calls.append(_path(steps, "call", x, f"calls `{x.label(steps[-1])}`, {_change_text(x, steps[-1])}"))
+    calls.sort(key=lambda p: (p.entry is None, len(p.steps), p.labels))
+    return out + calls
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: PASS: `28 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `576 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_reading.py backend/codetortoise/reading.py
git commit -m "feat(reading): a story's contract rows, where its code lives, and every call path to it, folded past four steps"
```

### Task 4: To check

Spec §7.1–§7.3, §7.5. `build_checks` makes the review's rows in kind order:
- Hazard and Confirm from tier-1 verdicts; without them, high and medium findings (not header fan-out) as Confirm rows with the detector's title; findings judged no hazard go to `cleared`;
- Caller not updated: an unchanged call site of a changed signature, with its source line; a call site built only for another target, or outside every compile database, says so;
- Result handled the old way: a caller ignoring a new return value, or comparing only with old values;
- Unchanged reader: a reader of a field the change now writes, in a function the change did not touch;
- Other build target: a header included only by files of another target (no story: "Across the change");
- No test touched: a changed function no test file calls or mentions, only when the workspace has test code;
- Not analysed: capped fan-in;
- Ask the author: a thread connected only by its bundle (it belongs to the thread).

Each row has its key, story, thread, workspace-relative place, function and source line. Two kinds at one place merge into one row listing both reasons.

**Files:**
- Test: `backend/tests/test_reading.py`
- Modify: `backend/codetortoise/reading.py`

**Interfaces:**
- Consumes: `Thread` (Task 1), `Connection` (Task 2), `Finding.verdict*` (two-tier stories), `targets` per local file, the symbol index's callers and includers.
- Produces: `reading.CHECK_ORDER`, `reading.Reason(kind, text)`, `reading.Check(key, kind, story, thread, path, line, function, node, text, source_line, finding, cites, also)`;
  `reading.build_checks(ss, threads, conns, x, targets=None, has_tests=False, test_callers=None, includers=None, read_text=None) -> tuple[list[Check], list[Check]]` (open rows, cleared rows).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_reading.py` (diff):

```diff
diff --git a/backend/tests/test_reading.py b/backend/tests/test_reading.py
index 6f5b595..72eae89 100644
--- a/backend/tests/test_reading.py
+++ b/backend/tests/test_reading.py
@@ -2,7 +2,17 @@
 from test_stories import _edit, _in_cls, _same, _world
 
 from codetortoise.board import analyse
-from codetortoise.reading import Thread, build_threads, call_paths, connections, contract_rows, story_links, where
+from codetortoise.reading import (
+    Connection,
+    Thread,
+    build_checks,
+    build_threads,
+    call_paths,
+    connections,
+    contract_rows,
+    story_links,
+    where,
+)
 from codetortoise.stories import Story, StorySet
 
 
@@ -333,3 +343,140 @@ def test_call_paths_are_not_capped():
     c = _world(fns, calls=[(f"c{i}", "send") for i in range(30)])
     paths = call_paths(_set(["N1"]).stories[0], _x(c), [])
     assert len(paths) == 30 and paths[0].text == "calls `send`, whose body changed"
+
+
+# ---- §7 To check
+def _f(fid, kind="contract", severity="medium", nodes=("N1",), verdict=None, reason=None, source=None, title=None):
+    from codetortoise.detectors.base import Finding
+    return Finding(id=fid, kind=kind, severity=severity, title=title or f"{kind} {fid}", summary="s", nodes=list(nodes),
+                   verdict=verdict, verdict_reason=reason, verdict_source=source)
+
+
+def _checks(c, ss, threads=None, conns=(), **kw):
+    threads = threads or [Thread(id="T1", name="t", purpose="", stories=[s.id for s in ss.stories])]
+    return build_checks(ss, threads, list(conns), _x(c), **kw)
+
+
+def _rows(checks):
+    return [(k.kind, k.story, k.path, k.line, k.function, k.text) for k in checks]
+
+
+def test_hazards_and_confirms_come_from_verdicts_and_no_hazard_findings_are_set_aside():
+    c = _world([_edit("send", "drv/uart.c")])
+    ss = _set(["N1"])
+    ss.finding_story = {"F1": "S1", "F2": "S1", "F3": "S1"}
+    c.findings = [_f("F1", verdict="hazard", reason="drops data", source="tier1"),
+                  _f("F2", verdict="needs_review", reason="check the lock", source="tier1"),
+                  _f("F3", verdict="no_hazard", reason="fine", source="tier1")]
+    open_, cleared = _checks(c, ss)
+    assert _rows(open_) == [("hazard", "S1", "drv/uart.c", 1, "send", "drops data"),
+                            ("confirm", "S1", "drv/uart.c", 1, "send", "check the lock")]
+    assert [(k.kind, k.text, k.finding) for k in cleared] == [("cleared", "fine", "F3")]
+    assert open_[0].key == "hazard|drv/uart.c|send|send" and open_[0].thread == "T1"
+
+
+def test_without_verdicts_high_and_medium_findings_are_confirm_rows_except_header_fan_out():
+    c = _world([_edit("send", "drv/uart.c")])
+    ss = _set(["N1"])
+    ss.finding_story = {"F1": "S1", "F2": "S1", "F3": "S1"}
+    c.findings = [_f("F1", severity="high", title="send: signature changed"), _f("F2", severity="low"),
+                  _f("F3", kind="header_fanout", severity="high")]
+    open_, _ = _checks(c, ss)
+    assert _rows(open_) == [("confirm", "S1", "drv/uart.c", 1, "send", "send: signature changed")]
+
+
+def _caller_world(**kw):
+    """`send` (S1) changed its signature; `log` and `flush` call it, `log` is changed too (S2)."""
+    c = _world([_edit("send", "drv/uart.c"), _edit("log", "svc/log.c"), _same("flush", "svc/flush.c")],
+               calls=[("log", "send"), ("flush", "send")])
+    _sig(c, "send", "int send(int len)", "int send(unsigned len)", **kw)
+    return c, _set(["N1"], ["N2"])
+
+
+def test_an_unchanged_caller_of_a_changed_signature_is_a_caller_not_updated_with_its_source_line():
+    c, ss = _caller_world()
+    open_, _ = _checks(c, ss)
+    assert _rows(open_) == [("caller", "S1", "svc/flush.c", 3, "flush",
+                             "`flush` calls `send` and was not updated for its new signature")]
+    assert open_[0].source_line == "b = 0;" and open_[0].node == "N3"
+    assert open_[0].key == "caller|svc/flush.c|flush|send"
+
+
+def test_a_call_site_built_only_for_another_target_or_outside_every_compile_database_says_so():
+    c, ss = _caller_world()
+    targets = {"/w/drv/uart.c": ["fw"], "/w/svc/log.c": ["fw"], "/w/svc/flush.c": ["host"]}
+    open_, _ = _checks(c, ss, targets=targets)
+    assert [(k.kind, k.text) for k in open_] == [("target", "`flush` calls `send` but is built only for `host`")]
+    del targets["/w/svc/flush.c"]
+    open_, _ = _checks(c, ss, targets=targets)
+    assert [(k.kind, k.text) for k in open_] == [
+        ("unanalysed", "`flush` calls `send` from a file outside every compile database")]
+
+
+def test_a_caller_ignoring_or_comparing_only_old_values_of_a_new_return_value_is_result_handled_the_old_way():
+    c = _world([_edit("send", "drv/uart.c"), _same("a", "x/a.c"), _same("b", "x/b.c"), _same("ok", "x/c.c")],
+               calls=[("a", "send"), ("b", "send"), ("ok", "send")])
+    _sig(c, "send", returns=(["0"], ["0", "-2"]))
+    calls = {e.caller: e for e in c.after[0].calls}
+    calls["c:@F@a"].result_used = False
+    calls["c:@F@b"].compared = ["==0"]
+    calls["c:@F@ok"].compared = ["!=0"]
+    open_, _ = _checks(c, _set(["N1"]))
+    assert [(k.kind, k.function, k.text) for k in open_] == [
+        ("result", "a", "`a` ignores the result of `send`, which can now return -2"),
+        ("result", "b", "`b` compares the result of `send` only with 0; it can now return -2")]
+
+
+def test_an_unchanged_reader_of_a_field_the_change_now_writes_is_listed_at_its_access():
+    c = _world([_edit("config", "drv/cfg.c"), _same("report", "svc/rep.c"), _edit("dump", "svc/dump.c")],
+               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged"),
+                       ("dump", "Uart", "errors", "read", "unchanged")])
+    open_, _ = _checks(c, _set(["N1"], ["N3"]))
+    assert _rows(open_) == [("reader", "S1", "svc/rep.c", 3, "report", "`report` reads `Uart::errors`, which `config` now writes")]
+    assert open_[0].key == "reader|svc/rep.c|report|config"
+
+
+def test_a_changed_function_no_test_calls_or_mentions_is_no_test_touched_only_when_the_workspace_has_tests():
+    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _edit("recv", "drv/recv.c"),
+                ("test_it", "tests/t.c", ["x;"], ["init_hw(); recv(1);"])])
+    ss = _set(["N1"], ["N2"], ["N3"], ["N4"], kinds={"S4": "tests"})
+    assert [k.kind for k in _checks(c, ss)[0]] == []
+    open_, _ = _checks(c, ss, has_tests=True, test_callers=lambda name: {"/w/tests/u.c"} if name == "init" else set())
+    assert [(k.kind, k.function, k.text) for k in open_] == [("untested", "send", "No test calls `send`")]
+
+
+def test_capped_fan_in_is_a_not_analysed_row():
+    c = _world([_edit("send", "drv/uart.c")])
+    c.impact.capped = {"send": 90}
+    (k,), _ = _checks(c, _set(["N1"]))
+    assert (k.kind, k.story, k.text) == ("unanalysed", "S1", "90 more callers of `send` found by name were not checked")
+
+
+def test_a_thread_connected_only_by_its_bundle_raises_ask_the_author_on_the_thread():
+    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c")])
+    ss = _set(["N1"], ["N2"])
+    threads = [Thread(id="T1", name="a", purpose="", stories=["S1"]), Thread(id="T2", name="b", purpose="", stories=["S2"])]
+    conns = [Connection(a="T1", b="T2", kind="bundled", text="nothing besides arriving in CL 1", shown=True)]
+    open_, _ = _checks(c, ss, threads=threads, conns=conns)
+    assert [(k.kind, k.story, k.thread, k.text) for k in open_] == [
+        ("ask", None, "T2", "Ask the author how this thread relates to the rest of the change: nothing besides arriving "
+                            "in CL 1")]
+    assert open_[0].key == "ask|||b"
+
+
+def test_two_kinds_at_one_place_merge_into_one_row_listing_both_reasons():
+    c, ss = _caller_world(returns=(["0"], ["0", "-2"]))
+    next(e for e in c.after[0].calls if e.caller == "c:@F@flush").result_used = False
+    (k,), _ = _checks(c, ss)
+    assert (k.kind, k.function) == ("caller", "flush")
+    assert [(r.kind, r.text) for r in k.also] == [("result", "`flush` ignores the result of `send`, which can now return -2")]
+
+
+def test_a_header_included_only_by_files_of_another_target_is_a_check_across_the_change():
+    from codetortoise.vcs.model import FileChange
+    c = _world([_edit("send", "drv/uart.c")])
+    c.cs.files.append(FileChange(depot="//d/w/drv/uart.h", local="/w/drv/uart.h", action="edit", before="\n",
+                                 after="#define X 1\n"))
+    targets = {"/w/drv/uart.c": ["fw"], "/w/drv/uart.h": ["fw"], "/w/host/a.c": ["host"], "/w/host/b.c": ["host"]}
+    open_, _ = _checks(c, _set(["N1"]), targets=targets, includers=lambda h: {"/w/host/a.c", "/w/host/b.c", "/w/drv/uart.c"})
+    assert _rows(open_) == [("target", None, "host/a.c", None, None, "`drv/uart.h` is included by 2 files built only for `host`")]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: FAIL: `1 error`; the first error is `ImportError: cannot import name 'build_checks' from 'codetortoise.reading' (backend/codetortoise/reading.py)`

- [ ] **Step 3: Implement**

`backend/codetortoise/reading.py` (diff):

```diff
diff --git a/backend/codetortoise/reading.py b/backend/codetortoise/reading.py
index b207fdd..0b55162 100644
--- a/backend/codetortoise/reading.py
+++ b/backend/codetortoise/reading.py
@@ -7,15 +7,17 @@ import fnmatch
 import posixpath
 import re
 from collections import defaultdict
+from collections.abc import Callable
 from dataclasses import dataclass, field
 from typing import Literal
 
 from pydantic import BaseModel, Field
 
-from codetortoise.board import Flow, _count, _Ctx
+from codetortoise.board import Flow, _count, _covered, _Ctx, is_test_path
 from codetortoise.cparse import is_header, preproc_spans
 from codetortoise.pieces import PieceSet, node_cl
 from codetortoise.stories import Story, StorySet
+from codetortoise.targets import UNKNOWN
 
 _KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}
 ConnKind = Literal["caller", "vocabulary", "condition", "place", "bundled"]
@@ -94,6 +96,32 @@ class CallPath(BaseModel):
     flow: str | None = None
 
 
+CheckKind = Literal["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask", "cleared"]
+CHECK_ORDER = ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask", "cleared"]
+
+
+class Reason(BaseModel):
+    kind: CheckKind
+    text: str
+
+
+class Check(BaseModel):
+    """One row of To check (§7): a place the reviewer should look at, and why."""
+    key: str                          # kind|file|function|related changed function's qualified name (no line numbers)
+    kind: CheckKind
+    story: str | None = None
+    thread: str | None = None
+    path: str = ""                    # workspace-relative
+    line: int | None = None
+    function: str | None = None
+    node: str | None = None           # the place's function
+    text: str
+    source_line: str = ""
+    finding: str | None = None
+    cites: list[str] = Field(default_factory=list)
+    also: list[Reason] = Field(default_factory=list)   # other kinds at the same place
+
+
 def rel_path(x: _Ctx, path: str | None) -> str:
     """A workspace-relative path (§12); paths outside the workspace stay as they are."""
     if not path:
@@ -648,3 +676,184 @@ def call_paths(story: Story, x: _Ctx, flows: list[Flow]) -> list[CallPath]:
             calls.append(_path(steps, "call", x, f"calls `{x.label(steps[-1])}`, {_change_text(x, steps[-1])}"))
     calls.sort(key=lambda p: (p.entry is None, len(p.steps), p.labels))
     return out + calls
+
+
+# ------------------------------------------------------------------ To check (§7)
+def _qual(x: _Ctx, n: str) -> str:
+    key = x.im.nodes[n].key
+    fn = x.fa.get(key) or x.fb.get(key)
+    return fn.qualname if fn else x.label(n)
+
+
+def _source(x: _Ctx, path: str | None, line: int | None, read_text: Callable[[str], str | None] | None) -> str:
+    if not path or not line:
+        return ""
+    fc = x.texts.get(path)
+    text = fc.after if fc else (read_text(path) if read_text else None) or ""
+    rows = text.splitlines()
+    return rows[line - 1].strip() if 0 < line <= len(rows) else ""
+
+
+def _def_place(x: _Ctx, n: str) -> tuple[str | None, int | None]:
+    key = x.im.nodes[n].key
+    fn = x.fa.get(key) or x.fb.get(key)
+    return (fn.file, fn.start_line) if fn else (x.local(n), x.im.nodes[n].line)
+
+
+def _cmp_text(c) -> str:
+    return ", ".join(c.compared_names.get(v[2:], v[2:]) if v.startswith("==") else v for v in c.compared)
+
+
+def build_checks(ss: StorySet, threads: list[Thread], conns: list[Connection], x: _Ctx,
+                 targets: dict[str, list[str]] | None = None, has_tests: bool = False,
+                 test_callers: Callable[[str], set[str]] | None = None,
+                 includers: Callable[[str], set[str]] | None = None,
+                 read_text: Callable[[str], str | None] | None = None) -> tuple[list[Check], list[Check]]:
+    """The review's To check rows in kind order (§7.1), rows at one place merged, and the findings judged no hazard.
+    `targets` maps local files to build targets (None: one target); `has_tests`: the workspace has test code;
+    `test_callers` gives the test files calling a name (the symbol index); `includers` the files including a header."""
+    findings = x.c.findings
+    thread_of = {s: t.id for t in threads for s in t.stories}
+    home = _home(ss)
+    rows: list[Check] = []
+
+    def add(kind: str, related: str | None, place: str | None, path: str | None, line: int | None, text: str,
+            story: str | None = None, **kw) -> None:
+        func = x.label(place) if place else None
+        story = story if story is not None else (home.get(related) if related else None)
+        rows.append(Check(key=f"{kind}|{rel_path(x, path)}|{func or ''}|{_qual(x, related) if related else kw.pop('rel', '')}",
+                          kind=kind, story=story, thread=thread_of.get(story) if story else kw.pop("thread", None),
+                          path=rel_path(x, path), line=line, function=func, node=place, text=text,
+                          source_line=_source(x, path, line, read_text), **kw))
+
+    # 1–2: the strong model's verdicts; without one, high and medium findings (not header fan-out) to confirm
+    cleared: list[Check] = []
+    for f in findings:
+        n = next((m for m in f.nodes if m in x.im.nodes and x.im.nodes[m].kind == "function"), None)
+        ev = next((e for e in f.evidence if e.file and e.line), None)
+        path, line = (ev.file, ev.line) if ev else (_def_place(x, n) if n else (None, None))
+        story = ss.finding_story.get(f.id)
+        common = dict(story=story, finding=f.id, cites=f.verdict_cites)
+        if f.verdict == "hazard":
+            add("hazard", n, n, path, line, f.verdict_reason or f.title, **common)
+        elif f.verdict == "needs_review":
+            add("confirm", n, n, path, line, f.verdict_reason or f.title, **common)
+        elif f.verdict == "no_hazard":
+            add("cleared", n, n, path, line, f.verdict_reason or f.title, **common)
+            cleared.append(rows.pop())
+        elif f.severity in ("high", "medium") and f.kind != "header_fanout":
+            add("confirm", n, n, path, line, f.title, **common)
+
+    def tg(path: str | None) -> set[str]:
+        return set((targets or {}).get(path or "", [])) or {UNKNOWN}
+
+    changed = [n for s in ss.stories for n in _story_fns(s, x)]
+    for n in changed:
+        key, callee = x.im.nodes[n].key, x.label(n)
+        fb, fa = x.fb.get(key), x.fa.get(key)
+        if not fb or not fa:
+            continue
+        sig = fb.signature != fa.signature
+        new = [v for v in fa.returns if v not in fb.returns]
+        mine = tg(fa.file)
+        for c in sorted((c for c in x.calls_after if c.callee == key), key=lambda c: (c.file, c.line)):
+            caller = x.id_of.get(c.caller)
+            if not caller or x.is_test_path(caller):
+                continue
+            who = x.label(caller)
+            if sig or new:
+                where_ = tg(c.file)
+                if targets is not None and where_ == {UNKNOWN} and mine != {UNKNOWN}:
+                    add("unanalysed", n, caller, c.file, c.line, f"`{who}` calls `{callee}` from a file outside every "
+                                                                  "compile database")
+                    continue
+                if targets is not None and UNKNOWN not in where_ | mine and not where_ & mine:
+                    add("target", n, caller, c.file, c.line,
+                        f"`{who}` calls `{callee}` but is built only for {', '.join(f'`{t}`' for t in sorted(where_))}")
+                    continue
+            if sig and caller not in x.changed:
+                add("caller", n, caller, c.file, c.line, f"`{who}` calls `{callee}` and was not updated for its new "
+                                                         "signature")
+            if new:
+                vals = ", ".join(_vals(fa, new))
+                if not c.result_used:
+                    add("result", n, caller, c.file, c.line, f"`{who}` ignores the result of `{callee}`, which can now "
+                                                             f"return {vals}")
+                elif c.compared and not _covered(c.compared, new):
+                    add("result", n, caller, c.file, c.line, f"`{who}` compares the result of `{callee}` only with "
+                                                             f"{_cmp_text(c)}; it can now return {vals}")
+    # 5: unchanged readers of fields the change now writes
+    for n in changed:
+        for w in (e for e in x.im.edges if e.src == n and e.kind == "writes" and e.status == "added"):
+            for r in sorted({e.src for e in _live(x, {"reads"}) if e.dst == w.dst}, key=lambda m: x.label(m)):
+                if r in x.changed or x.is_test_path(r):
+                    continue
+                acc = next((a for a in x.fields_after if f"field:{a.field}" == x.im.nodes[w.dst].key
+                            and a.fn == x.im.nodes[r].key and a.mode == "read"), None)
+                path, line = (acc.file, acc.line) if acc else _def_place(x, r)
+                add("reader", n, r, path, line, f"`{x.label(r)}` reads `{x.label(w.dst)}`, which `{x.label(n)}` now writes")
+    # 6: a changed header included only by files of another target
+    if targets is not None and includers is not None:
+        mine = {t for f in x.c.cs.files if not is_header(f.local) for t in targets.get(f.local, [])} - {UNKNOWN}
+        for h in sorted(f.local for f in x.c.cs.files if is_header(f.local)):
+            other: dict[str, list[str]] = defaultdict(list)
+            for inc in sorted(includers(h)):
+                where_ = set(targets.get(inc, [])) - {UNKNOWN}
+                if mine and where_ and not where_ & mine:
+                    other[", ".join(f"`{t}`" for t in sorted(where_))].append(inc)
+            for names, files in other.items():
+                add("target", None, None, files[0], None,
+                    f"`{rel_path(x, h)}` is included by {len(files)} file{'s' if len(files) > 1 else ''} built only for "
+                    f"{names}", rel=rel_path(x, h))
+    # 7: changed functions no test calls or mentions (only when the workspace has test code)
+    if has_tests:
+        mentions = "\n".join(f.after for f in x.c.cs.files if is_test_path(rel_path(x, f.local)))
+        for s in ss.stories:
+            if s.kind == "tests":
+                continue
+            for n in _story_fns(s, x):
+                if x.is_test_path(n) or n not in x.changed:
+                    continue
+                name = x.label(n).split("::")[-1]
+                by_test = any(x.is_test_path(e.src) for e in _live(x, {"call", "virtual"}) if e.dst == n)
+                if by_test or re.search(rf"\b{re.escape(name)}\b", mentions) or (test_callers and test_callers(name)):
+                    continue
+                add("untested", n, n, *_def_place(x, n), f"No test calls `{x.label(n)}`")
+    # 8: callers found by name over the fan-in cap
+    for name, skipped in sorted(x.im.capped.items()):
+        n = next((m for m in changed if x.label(m) == name or x.label(m).split("::")[-1] == name), None)
+        if n:
+            add("unanalysed", n, n, *_def_place(x, n), f"{skipped} more callers of `{x.label(n)}` found by name were not "
+                                                       "checked")
+    # 9: threads tied to the rest only by their bundle
+    lone = [t for t in threads if not any(k.kind != "bundled" and t.id in (k.a, k.b) for k in conns)]
+    by = {s.id: s for s in ss.stories}
+    for t in lone:
+        if t is threads[0] and len(lone) == len(threads):
+            continue
+        k = next((k for k in conns if k.shown and t.id in (k.a, k.b)), None) or \
+            next((k for k in conns if t.id in (k.a, k.b)), None)
+        fns = _story_fns(by[t.stories[0]], x)
+        add("ask", None, None, None, None, "Ask the author how this thread relates to the rest of the change"
+            + (f": {k.text}" if k else ""), thread=t.id, rel=_qual(x, fns[0]) if fns else t.name)
+    return _merge(rows), cleared
+
+
+def _merge(rows: list[Check]) -> list[Check]:
+    """One row per place: the first kind leads, the others become its `also`; then kind order, then place. Rows of
+    findings stay apart (each has its own verdict)."""
+    rank = {k: i for i, k in enumerate(CHECK_ORDER)}
+    rows = sorted(rows, key=lambda k: (rank[k.kind], k.path, k.line or 0))
+    out: list[Check] = []
+    at: dict[tuple, Check] = {}
+    for k in rows:
+        place = (k.path, k.line, k.function) if k.path and k.line and not k.finding else None
+        if place and place in at:
+            lead = at[place]
+            if all(r.text != k.text for r in lead.also) and lead.text != k.text:
+                lead.also.append(Reason(kind=k.kind, text=k.text))
+            continue
+        if place:
+            at[place] = k
+        out.append(k)
+    return out
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: PASS: `39 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `587 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_reading.py backend/codetortoise/reading.py
git commit -m "feat(reading): To check lists hazards, confirms and what the analysis thinks was missed, merged by place and keyed without lines"
```

### Task 5: The headline, build impact, coverage and one reading

Spec §5.2, §5.4, §10.1. `headline` says what to act on (open hazards, else checks to confirm, else none; rules only: the top severity of the open findings). `build_impact` turns header fan-out findings into rows ("`regs.h` declaration change → 4 files rebuild"). `coverage` lists what the analysis could not see fully (degraded parses and what tree-sitter added, capped fan-in, files outside the compile databases, drift, "No test code found in the workspace"), leaving out empty counts. `fixed_whole` writes the change as a whole from the strongest shown connections. `build_reading` puts it all together: links, threads in order (the open checks count toward it, Ask the author does not move a thread up), connections, To check, the Tests row, and each story's tiles (`StoryReading`).

**Files:**
- Test: `backend/tests/test_reading.py`
- Modify: `backend/codetortoise/reading.py`

**Interfaces:**
- Consumes: Tasks 1–4; `BoardContext`, `StoryDetail` (flows per story), `PieceSet`.
- Produces: `reading.Headline(text, tone, rules_only)`, `reading.BuildImpact(header, text, files, finding, note)`, `reading.TestsRow(stories, functions, covers, untested)`,
  `reading.StoryReading(story, contracts, where, paths, checks, place_text, thread, position)`,
  `reading.Reading(whole, whole_source, threads, connections, order, reasons, links, checks, cleared, build_impact, coverage, headline, rules_only, tests)`;
  `reading.headline(checks, marked: set[str], findings) -> Headline`, `reading.build_impact(x) -> list[BuildImpact]`, `reading.coverage(x, has_tests, outside=0) -> list[str]`, `reading.fixed_whole(threads, conns) -> str`;
  `reading.build_reading(ss, c, details=None, analysis=None, pieces=None, targets=None, has_tests=False, test_callers=None, includers=None, read_text=None) -> tuple[Reading, dict[str, StoryReading]]`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_reading.py` (diff):

```diff
diff --git a/backend/tests/test_reading.py b/backend/tests/test_reading.py
index 72eae89..a7a1aae 100644
--- a/backend/tests/test_reading.py
+++ b/backend/tests/test_reading.py
@@ -3,13 +3,18 @@ from test_stories import _edit, _in_cls, _same, _world
 
 from codetortoise.board import analyse
 from codetortoise.reading import (
+    Check,
     Connection,
     Thread,
     build_checks,
+    build_impact,
+    build_reading,
     build_threads,
     call_paths,
     connections,
     contract_rows,
+    coverage,
+    headline,
     story_links,
     where,
 )
@@ -269,6 +274,8 @@ def test_a_signature_row_marks_the_part_that_differs():
     assert (row.kind, row.node, row.before, row.after, row.mark) == ("signature", "N1", "int send(int len)",
                                                                      "int send(unsigned len)", [9, 17])
     assert row.text == "`send`: `int` → `unsigned`"
+    _sig(c, "send", "int send(int, int)", "int send(int, unsigned int)")
+    assert contract_rows(_set(["N1"]).stories[0], _x(c))[0].text == "`send`: gained `unsigned`"
 
 
 def test_the_same_signature_edit_in_two_functions_is_one_repeated_row():
@@ -449,7 +456,7 @@ def test_capped_fan_in_is_a_not_analysed_row():
     c = _world([_edit("send", "drv/uart.c")])
     c.impact.capped = {"send": 90}
     (k,), _ = _checks(c, _set(["N1"]))
-    assert (k.kind, k.story, k.text) == ("unanalysed", "S1", "90 more callers of `send` found by name were not checked")
+    assert (k.kind, k.story, k.text) == ("unanalysed", "S1", "90 callers of `send` found by name were not checked")
 
 
 def test_a_thread_connected_only_by_its_bundle_raises_ask_the_author_on_the_thread():
@@ -480,3 +487,104 @@ def test_a_header_included_only_by_files_of_another_target_is_a_check_across_the
     targets = {"/w/drv/uart.c": ["fw"], "/w/drv/uart.h": ["fw"], "/w/host/a.c": ["host"], "/w/host/b.c": ["host"]}
     open_, _ = _checks(c, _set(["N1"]), targets=targets, includers=lambda h: {"/w/host/a.c", "/w/host/b.c", "/w/drv/uart.c"})
     assert _rows(open_) == [("target", None, "host/a.c", None, None, "`drv/uart.h` is included by 2 files built only for `host`")]
+
+
+# ---- §5.4 headline, §5.2 build impact and coverage
+def _k(kind, key, finding=None):
+    return Check(key=key, kind=kind, text="t", finding=finding)
+
+
+def test_the_headline_says_what_to_act_on_open_hazards_then_confirms_then_none():
+    tier1 = [_f("F1", verdict="hazard", source="tier1")]
+    rows = [_k("hazard", "h1"), _k("hazard", "h2"), _k("confirm", "c1"), _k("caller", "x")]
+    assert headline(rows, set(), tier1).model_dump() == {"text": "2 hazards", "tone": "hazard", "rules_only": False}
+    assert headline(rows, {"h1"}, tier1).text == "1 hazard"
+    assert headline(rows, {"h1", "h2"}, tier1).model_dump() == {"text": "1 to confirm", "tone": "confirm",
+                                                                "rules_only": False}
+    assert headline(rows, {"h1", "h2", "c1"}, tier1).model_dump() == {"text": "No hazards found", "tone": "none",
+                                                                      "rules_only": False}
+
+
+def test_rules_only_the_headline_is_the_top_severity_of_open_findings_never_build_impact():
+    fs = [_f("F1", severity="high"), _f("F2", severity="medium"), _f("F3", kind="header_fanout", severity="high"),
+          _f("F4", severity="low")]
+    rows = [_k("confirm", "a", "F1"), _k("confirm", "b", "F2")]
+    assert headline(rows, set(), fs).model_dump() == {"text": "High risk", "tone": "hazard", "rules_only": True}
+    assert headline(rows, {"a"}, fs).model_dump() == {"text": "Medium risk", "tone": "confirm", "rules_only": True}
+    assert headline(rows, {"a", "b"}, fs).model_dump() == {"text": "Low risk", "tone": "none", "rules_only": True}
+    assert headline([], set(), []).text == "No risks found"
+
+
+def test_header_fan_out_findings_become_build_impact_rows():
+    from codetortoise.detectors.base import Evidence
+    from codetortoise.diffmap import TypeChange
+    from codetortoise.impact import FanOut
+    c = _world([_edit("send", "drv/uart.c")])
+    c.dm.types.append(TypeChange(file="/w/inc/common.h", depot="//d/w/inc/common.h", name="LIMIT", kind="macro_changed"))
+    c.impact.fanout = [FanOut(header="/w/inc/common.h", total_tus=713)]
+    f = _f("F1", kind="header_fanout", severity="high", nodes=())
+    f.evidence = [Evidence(text="macro changed: LIMIT", file="/w/inc/common.h")]
+    c.findings = [f]
+    (b,) = build_impact(_x(c))
+    assert (b.header, b.text, b.files, b.finding, b.note) == ("inc/common.h", "`inc/common.h` macro change → 713 files "
+                                                              "rebuild", 713, "F1", "")
+    f.verdict = "no_hazard"
+    assert build_impact(_x(c))[0].note == "No behaviour change found."
+
+
+def test_coverage_names_parse_problems_caps_files_outside_compile_databases_drift_and_missing_tests():
+    from codetortoise.vcs.model import DriftItem
+    c = _world([_edit("send", "drv/uart.c")])
+    c.after[0].tu.confidence, c.after[0].tu.supplemented = "degraded", 7
+    c.impact.capped = {"send": 140}
+    c.cs.drift = [DriftItem(depot="//d/w/drv/uart.c", local="/w/drv/uart.c", expected="#3", actual="#4")]
+    assert coverage(_x(c), has_tests=False, outside=2) == [
+        "1 file parsed with errors; tree-sitter added 7 calls or field accesses",
+        "140 callers of `send` found by name were not checked (more than 50)",
+        "2 files with callers are outside every compile database",
+        "1 file in the workspace differs from the CL base",
+        "No test code found in the workspace"]
+    c.after[0].tu.confidence, c.after[0].tu.extractor, c.after[0].tu.supplemented = "degraded", "treesitter", 0
+    c.impact.capped, c.cs.drift = {}, []
+    assert coverage(_x(c), has_tests=True) == ["1 file read by tree-sitter only"]
+
+
+# ---- the whole reading
+def test_the_reading_puts_threads_in_order_with_checks_counted_and_each_story_its_tiles():
+    c, ss = _chain()
+    c.findings = [_f("F1", nodes=("N4",), verdict="hazard", reason="loses it", source="tier1")]
+    ss.finding_story = {"F1": "S4"}
+    reading, per = build_reading(ss, c)
+    assert [(t.id, t.stories, t.open_checks) for t in reading.threads] == [("T1", ["S4"], 1),
+                                                                          ("T2", ["S3", "S2", "S1"], 1)]
+    assert reading.order == ["S4", "S3", "S2", "S1", "S5"]
+    assert reading.reasons == {"S2": "← calls 1", "S1": "← uses 2"}
+    assert reading.headline.text == "1 hazard" and not reading.rules_only
+    assert [(k.kind, k.thread) for k in reading.checks] == [("hazard", "T1"), ("ask", "T2")]
+    assert reading.tests.model_dump() == {"stories": ["S5"], "functions": 1, "covers": ["T2"], "untested": ["T1"]}
+    assert per["S2"].place_text == "Uses what story 1 adds; story 3 builds on this."
+    assert per["S3"].place_text == "Story 2 builds on this." and per["S4"].place_text == ""
+    assert [k.kind for k in per["S4"].checks] == ["hazard"] and per["S1"].where[0].path == "svc/flush.c"
+    assert reading.whole_source == "template"
+
+
+def test_ask_the_author_does_not_move_a_thread_up_the_reading_order():
+    c, ss = _chain()
+    reading, _ = build_reading(ss, c)
+    assert [t.stories for t in reading.threads] == [["S3", "S2", "S1"], ["S4"]]
+    assert [(k.kind, k.thread) for k in reading.checks] == [("ask", "T2")]
+
+
+def test_the_fixture_reads_as_threads_with_checks(fx, analysed, fx_source):
+    from test_board import _ctx
+
+    from codetortoise.paths import canon
+    from codetortoise.stories import build_stories
+    bctx = _ctx(analysed, fx_source)
+    bctx.root = canon(str(fx.root))
+    ss, det = build_stories(bctx)
+    reading, per = build_reading(ss, bctx, details=det)
+    assert sorted(s for t in reading.threads for s in t.stories) == sorted(s.id for s in ss.stories)
+    assert set(per) == {s.id for s in ss.stories}
+    assert all(not k.path.startswith("/") for k in reading.checks)
+    assert {k.kind for k in reading.checks} >= {"confirm"}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: FAIL: `1 error`; the first error is `ImportError: cannot import name 'build_impact' from 'codetortoise.reading' (backend/codetortoise/reading.py)`

- [ ] **Step 3: Implement**

`backend/codetortoise/reading.py` (diff):

```diff
diff --git a/backend/codetortoise/reading.py b/backend/codetortoise/reading.py
index 0b55162..5768269 100644
--- a/backend/codetortoise/reading.py
+++ b/backend/codetortoise/reading.py
@@ -13,10 +13,11 @@ from typing import Literal
 
 from pydantic import BaseModel, Field
 
-from codetortoise.board import Flow, _count, _covered, _Ctx, is_test_path
+from codetortoise.board import BoardContext, Flow, _count, _covered, _Ctx, analyse, is_test_path
 from codetortoise.cparse import is_header, preproc_spans
+from codetortoise.detectors.base import SEVERITY_RANK, Finding
 from codetortoise.pieces import PieceSet, node_cl
-from codetortoise.stories import Story, StorySet
+from codetortoise.stories import Story, StoryDetail, StorySet
 from codetortoise.targets import UNKNOWN
 
 _KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}
@@ -122,6 +123,56 @@ class Check(BaseModel):
     also: list[Reason] = Field(default_factory=list)   # other kinds at the same place
 
 
+class Headline(BaseModel):
+    text: str
+    tone: Literal["hazard", "confirm", "none"]
+    rules_only: bool = False
+
+
+class BuildImpact(BaseModel):
+    header: str                       # workspace-relative
+    text: str
+    files: int
+    finding: str | None = None
+    note: str = ""
+
+
+class TestsRow(BaseModel):
+    """The overview's Tests row (§5.1): which threads the change's tests exercise."""
+    stories: list[str] = Field(default_factory=list)
+    functions: int = 0
+    covers: list[str] = Field(default_factory=list)
+    untested: list[str] = Field(default_factory=list)
+
+
+class StoryReading(BaseModel):
+    story: str
+    contracts: list[ContractRow] = Field(default_factory=list)
+    where: list[WhereFile] = Field(default_factory=list)
+    paths: list[CallPath] = Field(default_factory=list)
+    checks: list[Check] = Field(default_factory=list)
+    place_text: str = ""              # its place in its thread: "Uses what story 1 adds."
+    thread: str | None = None
+    position: int | None = None       # 1-based, within its thread
+
+
+class Reading(BaseModel):
+    whole: str = ""
+    whole_source: Literal["template", "llm"] = "template"
+    threads: list[Thread] = Field(default_factory=list)
+    connections: list[Connection] = Field(default_factory=list)
+    order: list[str] = Field(default_factory=list)            # story ids, tests last
+    reasons: dict[str, str] = Field(default_factory=dict)
+    links: list[StoryLink] = Field(default_factory=list)
+    checks: list[Check] = Field(default_factory=list)
+    cleared: list[Check] = Field(default_factory=list)        # findings judged no hazard
+    build_impact: list[BuildImpact] = Field(default_factory=list)
+    coverage: list[str] = Field(default_factory=list)
+    headline: Headline = Field(default_factory=lambda: Headline(text="No risks found", tone="none", rules_only=True))
+    rules_only: bool = True
+    tests: TestsRow | None = None
+
+
 def rel_path(x: _Ctx, path: str | None) -> str:
     """A workspace-relative path (§12); paths outside the workspace stay as they are."""
     if not path:
@@ -580,13 +631,14 @@ def contract_rows(story: Story, x: _Ctx) -> list[ContractRow]:
             body.append(n)
     repeated = []
     for (old, new), got in sigs.items():
+        what = f"gained `{new}`" if not old else f"lost `{old}`" if not new else f"`{old}` → `{new}`"
         if len(got) >= 2:
-            what = (f"gained `{new}`" if not old else f"lost `{old}`" if not new else f"changed `{old}` → `{new}`")
-            repeated.append(ContractRow(kind="repeated", nodes=[g[0] for g in got], text=f"{len(got)} signatures {what}"))
+            repeated.append(ContractRow(kind="repeated", nodes=[g[0] for g in got],
+                                        text=f"{len(got)} signatures {'changed ' if old and new else ''}{what}"))
         else:
             n, b, a, mark = got[0]
             singles.insert(0, ContractRow(kind="signature", node=n, nodes=[n], before=b, after=a, mark=mark,
-                                          text=f"`{x.label(n)}`: `{old}` → `{new}`"))
+                                          text=f"`{x.label(n)}`: {what}"))
     rows = repeated + singles + rets + flds
     if body:
         rows.append(ContractRow(kind="body", nodes=body, text=f"{len(body)} function{'s' if len(body) > 1 else ''} "
@@ -823,8 +875,7 @@ def build_checks(ss: StorySet, threads: list[Thread], conns: list[Connection], x
     for name, skipped in sorted(x.im.capped.items()):
         n = next((m for m in changed if x.label(m) == name or x.label(m).split("::")[-1] == name), None)
         if n:
-            add("unanalysed", n, n, *_def_place(x, n), f"{skipped} more callers of `{x.label(n)}` found by name were not "
-                                                       "checked")
+            add("unanalysed", n, n, *_def_place(x, n), f"{skipped} callers of `{x.label(n)}` found by name were not checked")
     # 9: threads tied to the rest only by their bundle
     lone = [t for t in threads if not any(k.kind != "bundled" and t.id in (k.a, k.b) for k in conns)]
     by = {s.id: s for s in ss.stories}
@@ -857,3 +908,165 @@ def _merge(rows: list[Check]) -> list[Check]:
             at[place] = k
         out.append(k)
     return out
+
+
+# ------------------------------------------------------------------ headline (§5.4), build impact and coverage (§5.2)
+def _n(n: int, word: str, plural: str | None = None) -> str:
+    return f"{n} {word if n == 1 else plural or word + 's'}"
+
+
+def headline(checks: list[Check], marked: set[str], findings: list[Finding]) -> Headline:
+    """What to act on: open hazards, else open checks to confirm, else none. Without the strong model's verdicts, the
+    top severity of the findings not marked, labelled rules only. Build impact never raises it."""
+    rules_only = not any(f.verdict_source == "tier1" for f in findings)
+    open_ = [k for k in checks if k.key not in marked]
+    if not rules_only:
+        hz = sum(k.kind == "hazard" for k in open_)
+        cf = sum(k.kind == "confirm" for k in open_)
+        if hz:
+            return Headline(text=_n(hz, "hazard"), tone="hazard")
+        if cf:
+            return Headline(text=f"{cf} to confirm", tone="confirm")
+        return Headline(text="No hazards found", tone="none")
+    done = {k.finding for k in checks if k.finding and k.key in marked}
+    sev = [f.severity for f in findings if f.kind != "header_fanout" and f.id not in done]
+    top = max(sev, key=lambda v: SEVERITY_RANK.get(v, 0), default=None)
+    if top is None:
+        return Headline(text="No risks found", tone="none", rules_only=True)
+    tone = "hazard" if top == "high" else "confirm" if top == "medium" else "none"
+    return Headline(text=f"{top.capitalize()} risk", tone=tone, rules_only=True)
+
+
+def build_impact(x: _Ctx) -> list[BuildImpact]:
+    """Header fan-out findings as "`common.h` macro change → 713 files rebuild"."""
+    tus = {fo.header: fo.total_tus for fo in x.im.fanout}
+    out = []
+    for f in x.c.findings:
+        if f.kind != "header_fanout":
+            continue
+        header = next((e.file for e in f.evidence if e.file), None)
+        if not header:
+            continue
+        kinds = {t.kind.split("_")[0] for t in x.c.dm.types if t.file == header}
+        what = {"macro": "macro change", "type": "type change", "decl": "declaration change"}.get(
+            next(iter(kinds)), "change") if len(kinds) == 1 else "header change"
+        n = tus.get(header, 0)
+        out.append(BuildImpact(header=rel_path(x, header), files=n, finding=f.id,
+                               text=f"`{rel_path(x, header)}` {what} → {_n(n, 'file')} rebuild{'s' if n == 1 else ''}",
+                               note="No behaviour change found." if f.verdict == "no_hazard" else ""))
+    return sorted(out, key=lambda b: -b.files)
+
+
+def coverage(x: _Ctx, has_tests: bool, outside: int = 0) -> list[str]:
+    """What the analysis could not see fully (§5.2, §7.5); empty counts are left out."""
+    facts = x.c.before + x.c.after
+    degraded = {f.tu.file for f in facts if f.tu.confidence == "degraded" and f.tu.extractor == "clang"}
+    added = sum(f.tu.supplemented for f in facts)
+    fallback = {f.tu.file for f in facts if f.tu.extractor == "treesitter"}
+    out = []
+    if degraded:
+        out.append(f"{_n(len(degraded), 'file')} parsed with errors"
+                   + (f"; tree-sitter added {_n(added, 'call')} or field accesses" if added else ""))
+    if fallback:
+        out.append(f"{_n(len(fallback), 'file')} read by tree-sitter only")
+    for name, n in sorted(x.im.capped.items()):
+        out.append(f"{n} callers of `{name}` found by name were not checked (more than {x.c.cfg.heuristic_fanin_cap})")
+    if outside:
+        out.append(f"{_n(outside, 'file')} with callers {'is' if outside == 1 else 'are'} outside every compile database")
+    if x.c.cs.drift:
+        d = len(x.c.cs.drift)
+        out.append(f"{_n(d, 'file')} in the workspace {'differs' if d == 1 else 'differ'} from the CL base")
+    if not has_tests:
+        out.append("No test code found in the workspace")
+    return out
+
+
+# ------------------------------------------------------------------ the whole reading
+def _stories_text(ps: list[int]) -> str:
+    nums = [str(p) for p in ps]
+    return ("story " if len(nums) == 1 else "stories ") + (nums[0] if len(nums) == 1 else
+                                                          ", ".join(nums[:-1]) + " and " + nums[-1])
+
+
+def _place_text(sid: str, order: list[str], strong: list[StoryLink]) -> str:
+    at = {s: i + 1 for i, s in enumerate(order)}
+    uses = sorted({at[lk.defines] for lk in strong if sid in (lk.a, lk.b) and lk.defines != sid and lk.defines in at})
+    built = sorted({at[lk.b if lk.a == sid else lk.a] for lk in strong if lk.defines == sid
+                    and (lk.b if lk.a == sid else lk.a) in at})
+    parts = ([f"Uses what {_stories_text(uses)} adds"] if uses else []) + \
+            ([f"{_stories_text(built)} build{'s' if len(built) == 1 else ''} on this"] if built else [])
+    text = "; ".join(parts)
+    return (text[0].upper() + text[1:] + ".") if text else ""
+
+
+def fixed_whole(threads: list[Thread], conns: list[Connection]) -> str:
+    """The change as a whole without the strong model (§9): the threads and their strongest shown connections."""
+    if not threads:
+        return "No changed code to read."
+    if len(threads) == 1:
+        return f"One thread: {threads[0].name}."
+    letter = {t.id: chr(ord("A") + i) if i < 26 else t.id for i, t in enumerate(threads)}
+    parts = [f"{letter[k.a]} and {letter[k.b]}: {k.text}" for k in conns if k.shown]
+    return f"{len(threads)} threads" + (": " + "; ".join(parts) if parts else "") + "."
+
+
+def _tests_row(ss: StorySet, threads: list[Thread], x: _Ctx) -> TestsRow | None:
+    tests = [s for s in ss.stories if s.kind == "tests"]
+    if not tests:
+        return None
+    thread_of = {s: t.id for t in threads for s in t.stories}
+    nodes = {n for s in tests for n in s.nodes}
+    home = _home(ss)
+    covered = {thread_of[home[e.dst]] for e in _live(x, {"call", "virtual"})
+               if e.src in nodes and home.get(e.dst) in thread_of}
+    return TestsRow(stories=[s.id for s in tests], functions=len(nodes),
+                    covers=[t.id for t in threads if t.id in covered], untested=[t.id for t in threads if t.id not in covered])
+
+
+def build_reading(ss: StorySet, c: BoardContext, details: dict[str, StoryDetail] | None = None, analysis=None,
+                  pieces: PieceSet | None = None, targets: dict[str, list[str]] | None = None, has_tests: bool = False,
+                  test_callers: Callable[[str], set[str]] | None = None, includers: Callable[[str], set[str]] | None = None,
+                  read_text: Callable[[str], str | None] | None = None) -> tuple[Reading, dict[str, StoryReading]]:
+    """The review's reading (threads, connections, order, To check, build impact, coverage, headline) and each story's
+    tiles, with fixed text; llm/threads.py may reword the thread names, purposes and the whole."""
+    a = analysis or analyse(c)
+    x = a.x
+    links = story_links(ss, x)
+
+    def checks_for(threads):
+        conns = connections(threads, ss, x, pieces)
+        return conns, build_checks(ss, threads, conns, x, targets=targets, has_tests=has_tests, test_callers=test_callers,
+                                   includers=includers, read_text=read_text)
+    first, _ = build_threads(ss, links, x)
+    _, (rows, _) = checks_for(first)
+    lead = {t.id: t.stories[0] for t in first}
+    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
+    for k in rows:
+        sid = k.story or lead.get(k.thread or "")
+        if sid and k.kind != "ask":               # how a thread relates to the rest is no reason to read it sooner
+            counts[sid][0] += k.kind == "hazard"
+            counts[sid][1] += 1
+    threads, reasons = build_threads(ss, links, x, {s: (h, n) for s, (h, n) in counts.items()})
+    conns, (rows, cleared) = checks_for(threads)
+    for t in threads:
+        t.open_checks = sum(1 for k in rows if k.thread == t.id)
+    strong = [lk for lk in links if lk.strength == "strong"]
+    order = [s for t in threads for s in t.stories] + [s.id for s in ss.stories if s.kind == "tests"]
+    outside = 0
+    if targets is not None:
+        outside = len({cl.file for cl in x.calls_after if not targets.get(cl.file) and cl.file not in x.texts})
+    reading = Reading(threads=threads, connections=conns, order=order, reasons=reasons, links=links, checks=rows,
+                      cleared=cleared, build_impact=build_impact(x), coverage=coverage(x, has_tests, outside),
+                      headline=headline(rows, set(), x.c.findings),
+                      rules_only=not any(f.verdict_source == "tier1" for f in x.c.findings),
+                      tests=_tests_row(ss, threads, x), whole=fixed_whole(threads, conns))
+    thread_of = {s: t for t in threads for s in t.stories}
+    per: dict[str, StoryReading] = {}
+    for s in ss.stories:
+        t = thread_of.get(s.id)
+        flows = details[s.id].board.flows if details and s.id in details else a.flows
+        per[s.id] = StoryReading(story=s.id, contracts=contract_rows(s, x), where=where(s, x), paths=call_paths(s, x, flows),
+                                 checks=[k for k in rows if k.story == s.id],
+                                 place_text=_place_text(s.id, t.stories, strong) if t else "",
+                                 thread=t.id if t else None, position=t.stories.index(s.id) + 1 if t else None)
+    return reading, per
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: PASS: `46 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `594 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_reading.py backend/codetortoise/reading.py
git commit -m "feat(reading): the headline says what to act on; build impact, coverage, the Tests row and each story's tiles make one reading"
```

### Task 6: The strong model names the threads and tells the change as a whole

Spec §9. `llm/threads.py` sends one tier-1 prompt: the threads with their stories' titles and purposes, the connections with their facts, the CL descriptions marked as hints, and the open checks' counts. `write_threads` rewords the reading in place from the checked answer: a thread's name and purpose only when they cite ids from the input and the name has at most 6 words; the whole only when it cites a thread; a connection's text only when it keeps its cited names and CLs. A failed or refused call (the tier-1 budget, under purpose `threads`) keeps every fixed text, and the notes say why.

**Files:**
- Test: `backend/tests/test_llm_threads.py`
- Modify: `backend/codetortoise/llm/ledger.py`
- Create: `backend/codetortoise/llm/threads.py`

**Interfaces:**
- Consumes: `Reading`, `StorySet` (Task 5); `LlmClient`, `Ledger` (tier-1 purposes).
- Produces: `ledger.TIER1` gains `"threads"`; `llm.threads.NAME_WORDS = 6`, `llm.threads.prompt(reading, ss, cls: dict[int, str]) -> str`,
  `llm.threads.write_threads(strong, ledger, rid, reading, ss, cls) -> list[str]` (notes on what kept its fixed text; empty when all of it was accepted).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_llm_threads.py` (new file):

```python
"""Thread names, purposes and the change as a whole from the strong model (spec 2026-10-07-review-reading §9)."""
from scripted_llm import ScriptedLlm

from codetortoise.llm.ledger import TIER1, Refused
from codetortoise.llm.threads import write_threads
from codetortoise.reading import Connection, Reading, Thread
from codetortoise.stories import Story, StorySet


def _reading():
    ss = StorySet(summary="", stories=[
        Story(id="S1", kind="behaviour", title="Send gains a length type", summary="s1", purpose="Sends bytes", nodes=["N1"]),
        Story(id="S2", kind="behaviour", title="Init sets the baud", summary="s2", nodes=["N2"]),
        Story(id="S3", kind="other", title="Engine step", summary="s3", nodes=["N3"])])
    r = Reading(threads=[Thread(id="T1", name="`send` in drv", purpose="s1", stories=["S1"], cls=[11], open_checks=2),
                         Thread(id="T2", name="`init` in drv", purpose="s2", stories=["S2"], cls=[12]),
                         Thread(id="T3", name="`step` in cpp", purpose="s3", stories=["S3"], cls=[12])],
                connections=[Connection(a="T1", b="T2", kind="caller", text="both run inside `main`", facts=["N9", "N1", "N2"],
                                        shown=True),
                             Connection(a="T2", b="T3", kind="bundled", text="nothing besides arriving in CL 12",
                                        facts=["CL 12"], shown=True)],
                whole="3 threads.")
    return r, ss


GOOD = {"threads": [{"id": "T1", "name": "UART send takes unsigned lengths", "purpose": "Callers pass lengths as unsigned.",
                     "cites": ["S1", "N1"]},
                    {"id": "T2", "name": "UART init", "purpose": "Init programs the baud rate.", "cites": ["S2"]},
                    {"id": "T3", "name": "Engine step", "purpose": "The engine takes a new step.", "cites": ["S3", "CL12"]}],
        "whole": "The change makes UART lengths unsigned and sets the baud at init. The engine step arrives only with "
                 "CL 12.", "whole_cites": ["T1", "T2", "T3"],
        "connections": [{"a": "T1", "b": "T2", "text": "both run from `main` at start-up"},
                        {"a": "T2", "b": "T3", "text": "only bundled together in CL 12"}]}


def test_a_checked_answer_names_the_threads_writes_the_whole_and_rewords_connections():
    r, ss = _reading()
    llm = ScriptedLlm(lambda s, u: GOOD)
    assert write_threads(llm, None, None, r, ss, {11: "Make send unsigned", 12: "Init and engine"}) == []
    assert [(t.name, t.purpose, t.text_source) for t in r.threads] == [
        ("UART send takes unsigned lengths", "Callers pass lengths as unsigned.", "llm"),
        ("UART init", "Init programs the baud rate.", "llm"), ("Engine step", "The engine takes a new step.", "llm")]
    assert r.whole.startswith("The change makes UART") and r.whole_source == "llm"
    assert [k.text for k in r.connections] == ["both run from `main` at start-up", "only bundled together in CL 12"]
    prompt = llm.prompts[0]
    assert "CL 11 (a hint from its author, not the source of truth): Make send unsigned" in prompt
    assert "T1 | 2 open checks | CL 11 | S1 Send gains a length type: Sends bytes" in prompt
    assert "T1 | T2 | caller | both run inside `main` | N9 N1 N2" in prompt


def test_answers_citing_unknown_ids_too_long_names_or_dropping_a_connections_fact_keep_the_fixed_text():
    r, ss = _reading()
    bad = {"threads": [{"id": "T1", "name": "A", "purpose": "B.", "cites": ["S9"]},
                       {"id": "T2", "name": "one two three four five six seven", "purpose": "C.", "cites": ["S2"]},
                       {"id": "T3", "name": "Engine", "purpose": "D.", "cites": []}],
           "whole": "Whole. Text.", "whole_cites": ["T7"],
           "connections": [{"a": "T1", "b": "T2", "text": "both start up together"},
                           {"a": "T2", "b": "T3", "text": "they belong together"}]}
    notes = write_threads(ScriptedLlm(lambda s, u: bad), None, None, r, ss, {})
    assert [(t.name, t.text_source) for t in r.threads] == [("`send` in drv", "template"), ("`init` in drv", "template"),
                                                           ("`step` in cpp", "template")]
    assert (r.whole, r.whole_source) == ("3 threads.", "template")
    assert [k.text for k in r.connections] == ["both run inside `main`", "nothing besides arriving in CL 12"]
    assert notes == ["thread text: 3 thread(s), the whole and 2 connection(s) failed the checks; their fixed text stays"]


def test_a_failed_or_refused_call_keeps_every_fixed_text_and_says_why():
    r, ss = _reading()
    notes = write_threads(ScriptedLlm(lambda s, u: RuntimeError("down")), None, None, r, ss, {})
    assert notes == ["thread text: RuntimeError: down; the fixed text stays"] and r.whole_source == "template"

    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            assert (purpose, target) == ("threads", "threads")
            raise Refused("this review has used its 10 tier-1 AI calls")
    notes = write_threads(ScriptedLlm(lambda s, u: GOOD), Budget(), 1, r, ss, {})
    assert notes == ["thread text: AI budget: this review has used its 10 tier-1 AI calls; the fixed text stays"]


def test_the_thread_text_counts_against_the_tier_1_budget():
    assert "threads" in TIER1
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_llm_threads.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.llm.threads'`

- [ ] **Step 3: Implement**

`backend/codetortoise/llm/ledger.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/ledger.py b/backend/codetortoise/llm/ledger.py
index 9db62be..8007a17 100644
--- a/backend/codetortoise/llm/ledger.py
+++ b/backend/codetortoise/llm/ledger.py
@@ -17,7 +17,7 @@ from codetortoise.store import Store
 
 T = TypeVar("T")
 PIPELINE = "pipeline"
-TIER1 = ("stories", "stories_merge", "review")    # strong-model calls: their own budget (spec 2026-10-05 §9)
+TIER1 = ("stories", "stories_merge", "review", "threads")    # strong-model calls: their own budget (spec 2026-10-05 §9)
 _T1 = "(" + ",".join(f"'{p}'" for p in TIER1) + ")"
 
 
```

`backend/codetortoise/llm/threads.py` (new file):

```python
"""The strong model names the threads and tells the change as a whole (spec 2026-10-07-review-reading §9).

One tier-1 call per review, after the analysis. The model is given the threads with their stories, the connections
with their facts, the CL descriptions marked as hints and the open checks' counts. Every answer is checked: a thread's
text must cite ids from the input, a name has at most 6 words, a connection's rewording keeps its cited names and CLs;
anything that fails keeps the fixed text from reading.py.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import _styled, _titled
from codetortoise.llm.style import STYLE
from codetortoise.reading import Reading
from codetortoise.stories import StorySet

NAME_WORDS = 6
_TICKS = re.compile(r"`[^`]+`")
_CL = re.compile(r"\bCL ?\d+\b")
_SENT = re.compile(r"(?<=[.?!])\s+")

SYSTEM = ("You are a senior C/C++ reviewer explaining a change to other reviewers. Use only what you are given. Reply "
          'with one JSON object: {"threads": [{"id", "name", "purpose", "cites"}], "whole", "whole_cites", '
          '"connections": [{"a", "b", "text"}]}. ' + STYLE)

ASK = """Each thread is a group of stories joined by calls or shared data. For each thread write a name (at most 6 \
words, what it does) and a purpose (one sentence). Then write "whole": the change as a whole in 2 to 4 sentences, saying \
how the threads connect. You may reword each connection's text, but keep every name in backticks and every CL number it \
has. When the only tie between two threads is that they arrived together, say so plainly. Cite the ids (T1, S2, N4, \
CL12) that support each thread's text in "cites" and the whole's in "whole_cites"; cite nothing that is not listed."""


class _T(BaseModel):
    id: str
    name: str = ""
    purpose: str = ""
    cites: list[str] = Field(default_factory=list)


class _C(BaseModel):
    a: str
    b: str
    text: str = ""


class _Out(BaseModel):
    threads: list[_T] = Field(default_factory=list)
    whole: str = ""
    whole_cites: list[str] = Field(default_factory=list)
    connections: list[_C] = Field(default_factory=list)


def prompt(reading: Reading, ss: StorySet, cls: dict[int, str]) -> str:
    by = {s.id: s for s in ss.stories}
    lines = ["THREADS (id | open checks | CLs | stories: id title: purpose):"]
    for t in reading.threads:
        stories = "; ".join(f"{s} {by[s].title}" + (f": {by[s].purpose}" if by[s].purpose else "") for s in t.stories)
        lines.append(f"{t.id} | {t.open_checks} open checks | {', '.join(f'CL {c}' for c in t.cls) or '-'} | {stories}")
    lines.append("CONNECTIONS (a | b | kind | text | facts):")
    lines += [f"{k.a} | {k.b} | {k.kind} | {k.text} | {' '.join(k.facts) or '-'}" for k in reading.connections]
    used = sorted({c for t in reading.threads for c in t.cls})
    if used:
        lines.append("CL DESCRIPTIONS:")
        lines += [f"CL {c} (a hint from its author, not the source of truth): {cls.get(c, '').strip() or '(none)'}"
                  for c in used]
    return ASK + "\n\n" + "\n".join(lines)


def _ids(reading: Reading, ss: StorySet) -> set[str]:
    ids = {t.id for t in reading.threads} | {s.id for s in ss.stories} | {n for s in ss.stories for n in s.nodes}
    ids |= {f for k in reading.connections for f in k.facts if re.fullmatch(r"[NS]\d+", f)}
    ids |= {f"CL{c}" for t in reading.threads for c in t.cls}
    return ids


def _keeps(fixed: str, facts: list[str], text: str) -> bool:
    """A reworded connection keeps the fixed text's names in backticks and its CLs; one with neither says "only" or
    "nothing" (the only tie is the bundle)."""
    need = _TICKS.findall(fixed) + [f for f in facts if f.startswith("CL ")]
    if need:
        return all(n in text for n in need)
    return bool(re.search(r"\b(only|nothing)\b", text, re.I))


def write_threads(strong: LlmClient, ledger: Ledger | None, rid: int | None, reading: Reading, ss: StorySet,
                  cls: dict[int, str]) -> list[str]:
    """Reword `reading` in place from one checked tier-1 answer; returns notes on what kept its fixed text."""
    text = prompt(reading, ss, cls)

    def ask(llm: LlmClient) -> _Out:
        return llm.complete_json(SYSTEM, text, _Out)
    try:
        out = ledger.call(strong, rid, None, "threads", "threads", ask) if ledger is not None else ask(strong)
    except Refused as e:
        return [f"thread text: AI budget: {e.reason}; the fixed text stays"]
    except Exception as e:  # the fixed text stands
        return [f"thread text: {type(e).__name__}: {e}"[:300] + "; the fixed text stays"]
    ids = _ids(reading, ss)

    def cited(cites: list[str]) -> bool:
        cs = [c.replace(" ", "") for c in cites]
        return bool(cs) and all(c in ids for c in cs)
    got = {t.id: t for t in out.threads}
    bad_threads = 0
    for t in reading.threads:
        a = got.get(t.id)
        name, purpose = (a.name.strip(), a.purpose.strip()) if a else ("", "")
        if (a and cited(a.cites) and name and len(name.split()) <= NAME_WORDS and _titled(name) and purpose
                and len(_SENT.split(purpose)) == 1 and _styled(purpose, "explanation")):
            t.name, t.purpose, t.text_source = name, purpose, "llm"
        else:
            bad_threads += 1
    whole = out.whole.strip()
    bad_whole = not (whole and cited(out.whole_cites) and 2 <= len(_SENT.split(whole)) <= 4 and _styled(whole, "explanation"))
    if not bad_whole:
        reading.whole, reading.whole_source = whole, "llm"
    words = {frozenset((c.a, c.b)): c.text.strip() for c in out.connections}
    bad_conns = 0
    for k in reading.connections:
        new = words.get(frozenset((k.a, k.b)))
        if new is None:
            continue
        if new and _keeps(k.text, k.facts, new) and _styled(new, "explanation"):
            k.text = new
        else:
            bad_conns += 1
    if not (bad_threads or bad_whole or bad_conns):
        return []
    parts = ([f"{bad_threads} thread(s)"] if bad_threads else []) + (["the whole"] if bad_whole else []) + \
            ([f"{bad_conns} connection(s)"] if bad_conns else [])
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return [f"thread text: {joined} failed the checks; their fixed text stays"]
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_llm_threads.py -q`
Expected: PASS: `4 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `598 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_llm_threads.py backend/codetortoise/llm/ledger.py backend/codetortoise/llm/threads.py
git commit -m "feat(llm): one tier-1 call names the threads and tells the change as a whole; unchecked text keeps the fixed wording"
```

### Task 7: The reading stage, marks and the API

Spec §7.4, §10.2–§10.4. A `reading` stage runs after `llm` (depending on `board`): it builds the reading from the board's stories, lets the strong model reword it (cached in the blob `thread_text`, keyed by `READING_VERSION`, the model and the prompt; `fresh` asks again), stores `reading` and `story_reading:<sid>`, and prunes marks to the keys found again. The store gains `check_marks` and the comment anchor kind `check`. `with_marks` gives viewers the reading with each mark (`changed` when the source line at its place is no longer the marked one) and the headline and open counts without the marked checks. The API serves `GET /reading`, the story's `reading`, `POST`/`DELETE /checks/{key}/mark` and each review's `headline` in the Reviews list.

**Files:**
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_store.py`
- Test: `backend/tests/test_web.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/reading.py`
- Modify: `backend/codetortoise/store.py`
- Modify: `backend/codetortoise/web/app.py`

**Interfaces:**
- Consumes: `build_reading` (Task 5), `write_threads` and `prompt` (Task 6), `board.is_test_path`, `SymbolIndex.callers_of`/`transitive_includers`.
- Produces: pipeline stage `reading` (`STAGES`, `DEPS["reading"] = ["board"]`); `reading.READING_VERSION = 1`; `reading.with_marks(r, marks, findings) -> dict`;
  `Store.set_mark(rid, key, user, source_line) -> dict`, `Store.clear_mark(rid, key)`, `Store.list_marks(rid) -> dict[str, dict]`, `Store.prune_marks(rid, keep: set[str])`, `store.ANCHOR_KINDS` with `"check"`;
  `GET /api/reviews/{rid}/reading`, `POST`/`DELETE /api/reviews/{rid}/checks/{key:path}/mark` (404 for an unknown key), `StoryDetail` JSON with `reading`, Reviews list items with `headline`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pipeline.py` (diff):

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 8c09afc..d37ec76 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -18,11 +18,15 @@ def test_full_review_without_llm_or_swarm(fx, tmp_path):
     assert stages(svc, rid) == {"ingest": "ok", "swarm_read": "degraded", "diffmap": "ok", "tu_select": "ok",
                                 "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok", "pieces": "ok",
                                 "stories": "ok", "review": "ok", "verdicts": "ok", "board": "ok", "llm": "degraded",
-                                "finalize": "ok"}
+                                "reading": "ok", "finalize": "ok"}
     msgs = {s["name"]: s["message"] for s in svc.store.list_stages(rid)}
     assert msgs["pieces"].endswith("target(s): compile_commands")
     assert msgs["stories"].endswith("by the rules (no strong model configured)")
     assert msgs["review"] == "no strong model: 6 finding(s) left to the detectors and the AI's side-effect pass"
+    assert msgs["reading"] == "1 thread(s), 0 connection(s) shown, 5 check(s); fixed thread text (no strong model)"
+    reading = svc.store.get_blob(rid, "reading")
+    assert [t["stories"] for t in reading["threads"]] == [["S2", "S1"]] and reading["headline"]["rules_only"]
+    assert svc.store.get_blob(rid, "story_reading:S1")["thread"] == "T1"
     ss = svc.store.get_blob(rid, "stories")
     assert all(s["targets"] == ["compile_commands"] and s["pieces"] for s in ss["stories"])
     review = svc.store.get_review(rid)
@@ -405,6 +409,12 @@ def _one_story_per_cl(system, user):
                                                   "cites": [node]} for f in re.findall(r"^(F\d+) \[", user, re.M)]}
     if "STORIES (key | title" in user:
         return {"related": [], "merge": []}
+    if "THREADS (id" in user:
+        rows = re.findall(r"^(T\d+) \|.*?\| (S\d+)", user, re.M)
+        return {"threads": [{"id": t, "name": "UART driver changes", "purpose": "This changes the UART driver.",
+                             "cites": [sid]} for t, sid in rows],
+                "whole": "The change reworks the UART driver. Its callers see new results.", "whole_cites": ["T1"],
+                "connections": []}
     by_cl: dict[str, list[str]] = {}
     for pid, cl in re.findall(r"^(P\d+)  .*? · CL (\d+)", user, re.M):
         by_cl.setdefault(cl, []).append(pid)
@@ -481,3 +491,18 @@ def test_the_strong_model_reviews_each_story_s_findings_and_tier_2_leaves_them_a
     calls = len(llm.prompts)
     run_review(rid, svc)                                            # the brief brings its verdicts: no call at all
     assert len(llm.prompts) == calls and len(svc.store.get_brief(rid)["verdicts"]) == 6
+
+
+def test_the_strong_model_names_the_threads_once_and_a_rerun_reuses_the_text(fx, tmp_path):
+    svc = make_services(fx, tmp_path)
+    llm = _strong(svc, _one_story_per_cl)
+    rid = svc.store.create_review("t", "owner", [101, 102])
+    run_review(rid, svc)
+    reading = svc.store.get_blob(rid, "reading")
+    assert {t["name"] for t in reading["threads"]} == {"UART driver changes"} and reading["whole_source"] == "llm"
+    msg = next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "reading")
+    assert msg.endswith("thread text by big")
+    asked = sum("THREADS (id" in p for p in llm.prompts)
+    run_review(rid, svc)
+    assert sum("THREADS (id" in p for p in llm.prompts) == asked == 1
+    assert svc.store.get_blob(rid, "reading")["whole_source"] == "llm"
```

`backend/tests/test_store.py` (diff):

```diff
diff --git a/backend/tests/test_store.py b/backend/tests/test_store.py
index 791c8a8..0ca311d 100644
--- a/backend/tests/test_store.py
+++ b/backend/tests/test_store.py
@@ -96,3 +96,23 @@ def test_an_existing_database_gains_ai_meta(tmp_path):
     [c] = s.list_comments(rid)
     assert c["body"] == "a comment from before @tortoise" and c["ai_meta"] is None
     assert s.set_ai_reply(c["id"], "x", {"pending": False})["ai_meta"] == {"pending": False}
+
+
+def test_check_marks_are_per_review_shared_and_pruned_to_the_keys_found_again(store):
+    rid = store.create_review("t", "a", [1])
+    m = store.set_mark(rid, "caller|a.c|f|g", "bob", "g(1);")
+    assert (m["key"], m["user"], m["source_line"]) == ("caller|a.c|f|g", "bob", "g(1);") and m["at"]
+    store.set_mark(rid, "reader|b.c|r|w", "ana", "x = u->n;")
+    store.set_mark(rid, "caller|a.c|f|g", "ana", "g(2);")                      # marking again replaces the mark
+    assert {k: (v["user"], v["source_line"]) for k, v in store.list_marks(rid).items()} == {
+        "caller|a.c|f|g": ("ana", "g(2);"), "reader|b.c|r|w": ("ana", "x = u->n;")}
+    store.prune_marks(rid, {"reader|b.c|r|w", "new|c.c|h|h"})
+    assert list(store.list_marks(rid)) == ["reader|b.c|r|w"]
+    store.clear_mark(rid, "reader|b.c|r|w")
+    assert store.list_marks(rid) == {} and store.list_marks(rid + 1) == {}
+
+
+def test_comments_can_be_anchored_to_a_check(store):
+    rid = store.create_review("t", "a", [1])
+    c = store.add_comment(rid, "bob", "is this fine?", "check", {"key": "caller|a.c|f|g"})
+    assert c["anchor_kind"] == "check" and c["anchor"] == {"key": "caller|a.c|f|g"}
```

`backend/tests/test_web.py` (diff):

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index 4df1a1a..2928565 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -67,7 +67,7 @@ def test_owner_creates_review_others_view_and_comment(env):
     assert r.status_code == 200 and r.json()["title"] == "CLs 101, 102"
     rid = r.json()["id"]
     detail = bob.get(f"/api/reviews/{rid}").json()
-    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 15
+    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 16
     assert detail["review"]["risk"] == "high"
     # the raw storyboard and impact graph are not served: the board replaced them (spec §14.4)
     assert bob.get(f"/api/reviews/{rid}/storyboard").status_code == 404
@@ -372,3 +372,57 @@ def test_the_owner_reruns_stories_fresh_and_the_ai_view_shows_tier_1(env):
     ai = owner.get(f"/api/reviews/{rid}/ai").json()
     assert ai["strong"] == "big" and ai["tier1"]["budget"] == 40
     assert login(app, "bob").post(f"/api/reviews/{rid}/rerun?fresh=true").status_code == 403
+
+
+def test_the_reading_endpoint_serves_threads_checks_and_marks_and_the_story_its_tiles(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    assert TestClient(app).get(f"/api/reviews/{rid}/reading").status_code == 401
+    r = owner.get(f"/api/reviews/{rid}/reading").json()
+    assert [t["stories"] for t in r["threads"]] == [["S2", "S1"]] and r["marks"] == {}
+    assert r["headline"] == {"text": "Medium risk", "tone": "confirm", "rules_only": True}
+    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()
+    assert s1["reading"]["thread"] == "T1" and s1["reading"]["position"] == 2
+    assert {k["kind"] for k in s1["reading"]["checks"]} >= {"result", "reader"}
+
+
+def test_any_viewer_marks_a_check_and_a_rerun_keeps_drops_or_reopens_it(env):
+    from urllib.parse import quote
+    svc, app, _ = env
+    owner, rid = _review(app)
+    bob = login(app, "bob")
+    checks = owner.get(f"/api/reviews/{rid}/reading").json()["checks"]
+    caller = next(k for k in checks if k["kind"] == "caller")
+    reader = next(k for k in checks if k["kind"] == "reader")
+    for k in (caller, reader):
+        m = bob.post(f"/api/reviews/{rid}/checks/{quote(k['key'], safe='')}/mark").json()
+        assert m["user"] == "bob" and m["source_line"] == k["source_line"]
+    assert bob.post(f"/api/reviews/{rid}/checks/nope/mark").status_code == 404
+    r = owner.get(f"/api/reviews/{rid}/reading").json()
+    assert r["marks"][caller["key"]]["user"] == "bob" and not r["marks"][caller["key"]]["changed"]
+    t1 = r["threads"][0]
+    assert t1["open_checks"] == len(checks) - 2
+    svc.store.set_mark(rid, reader["key"], "bob", "an older line")             # the line changed since it was marked
+    svc.store.set_mark(rid, "caller|gone.c|f|g", "bob", "x")                   # a check the re-run will not find
+    owner.post(f"/api/reviews/{rid}/rerun")
+    r = owner.get(f"/api/reviews/{rid}/reading").json()
+    assert set(r["marks"]) == {caller["key"], reader["key"]}
+    assert r["marks"][reader["key"]]["changed"] and not r["marks"][caller["key"]]["changed"]
+    assert r["threads"][0]["open_checks"] == len(checks) - 1
+    assert bob.delete(f"/api/reviews/{rid}/checks/{quote(caller['key'], safe='')}/mark").json() == {"ok": True}
+    assert set(owner.get(f"/api/reviews/{rid}/reading").json()["marks"]) == {reader["key"]}
+    c = bob.post(f"/api/reviews/{rid}/comments", json={"body": "fine?", "anchor_kind": "check",
+                                                         "anchor": {"key": caller["key"]}})
+    assert c.status_code == 200 and c.json()["anchor"] == {"key": caller["key"]}
+
+
+def test_the_reviews_list_shows_each_reviews_headline(env):
+    svc, app, _ = env
+    owner, rid = _review(app)
+    (item,) = owner.get("/api/reviews").json()
+    assert item["headline"] == {"text": "Medium risk", "tone": "confirm", "rules_only": True}
+    svc.store.replace_blobs(rid, ["reading"], ["story_reading:"], {})        # a review run before the reading
+    assert owner.get("/api/reviews").json()[0]["headline"] is None
+    r = owner.get(f"/api/reviews/{rid}/reading")
+    assert r.status_code == 404 and r.json()["detail"] == "this review has no reading: re-run it"
+    assert owner.get(f"/api/reviews/{rid}/stories/S1").json()["reading"] is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_store.py tests/test_web.py -q`
Expected: FAIL: `8 failed, 54 passed`; the first error is `AssertionError: assert {'ingest': 'o...t': 'ok', ...} == {'ingest': 'o...t': 'ok', ...}`

- [ ] **Step 3: Implement**

`backend/codetortoise/pipeline.py` (diff):

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 7d6fc55..149bad4 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -1,6 +1,7 @@
 """Staged review pipeline and background job runner."""
 from __future__ import annotations
 
+import hashlib
 import logging
 import queue
 import threading
@@ -10,7 +11,7 @@ from concurrent.futures import ThreadPoolExecutor
 from pathlib import Path
 
 from codetortoise import boardstore
-from codetortoise.board import BoardContext, analyse, build_boards
+from codetortoise.board import BoardContext, analyse, build_boards, is_test_path
 from codetortoise.brief import Brief, cache_key
 from codetortoise.detectors.base import DetectorContext, renumber, run_detectors
 from codetortoise.diffmap import map_changes
@@ -23,9 +24,12 @@ from codetortoise.llm.brief_context import brief_context
 from codetortoise.llm.review import apply_verdicts, review_stories
 from codetortoise.llm.stories import STORY_RULES_VERSION, form_stories
 from codetortoise.llm.storyboard import AiContext, build_storyboard, judge_side_effects
+from codetortoise.llm.threads import prompt as threads_prompt
+from codetortoise.llm.threads import write_threads
 from codetortoise.paths import canon
 from codetortoise.pieces import build_pieces
 from codetortoise.provenance import finding_files, impact_node_files, local_files
+from codetortoise.reading import READING_VERSION, build_reading
 from codetortoise.repeated import find_repeated
 from codetortoise.services import Services
 from codetortoise.stories import build_stories
@@ -45,11 +49,11 @@ def _read_text(path: str) -> str | None:
         return None
 
 STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "pieces", "stories",
-          "review", "verdicts", "board", "llm", "finalize"]
+          "review", "verdicts", "board", "llm", "reading", "finalize"]
 DEPS = {"swarm_read": ["ingest"], "diffmap": ["ingest"], "tu_select": ["diffmap"], "facts": ["tu_select"],
         "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "pieces": ["impact", "detectors"],
         "stories": ["pieces"], "review": ["stories"], "verdicts": ["detectors"], "board": ["impact", "detectors"],
-        "llm": ["detectors"]}
+        "llm": ["detectors"], "reading": ["board"]}
 
 
 class Degraded(Exception):
@@ -409,6 +413,67 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
         if sb.style_dropped:
             return f"{sb.style_dropped} AI output(s) broke the house style and were dropped"
 
+    def reading():
+        """How the review reads (spec 2026-10-07-review-reading): threads, connections, To check, each story's tiles."""
+        bs = ctx.get("boards")
+        if bs is None or bs.stories is None or bs.analysis is None:
+            raise Degraded("no stories to read")
+        x = bs.analysis.x
+        root = x.c.root.rstrip("/") + "/"
+
+        def rel(p: str) -> str:
+            return p[len(root):] if p.startswith(root) else p
+        ps = ctx.get("pieces")
+        targets = dict(ps.targets) if ps is not None else {}
+        resolve = ctx.get("resolve_targets")
+        missing = sorted({c.file for c in x.calls_after if c.file not in targets})
+        if resolve is not None and missing:
+            targets.update(resolve(missing))
+        texts: dict[str, str | None] = {}
+
+        def read_text(path: str) -> str | None:
+            if path not in texts:
+                texts[path] = _read_text(path)
+            return texts[path]
+        has_tests = any(is_test_path(rel(f)) for f in svc.index.files()) or \
+            any(is_test_path(rel(f.local)) for f in ctx["cs"].files)
+        r, per = build_reading(bs.stories, x.c, details=bs.story_details, analysis=bs.analysis, pieces=ps,
+                               targets=targets, has_tests=has_tests, includers=svc.index.transitive_includers,
+                               test_callers=lambda name: {c.path for c in svc.index.callers_of(name)
+                                                          if is_test_path(rel(c.path))},
+                               read_text=read_text)
+        notes: list[str] = []
+        strong = cfg.llm.strong
+        if svc.strong is None or strong is None:
+            told = "fixed thread text (no strong model)"
+        else:
+            cls_text = {m.cl: m.description for m in ctx["cs"].cls}
+            key = hashlib.sha256(f"{READING_VERSION}|{strong.model}|{threads_prompt(r, bs.stories, cls_text)}"
+                                 .encode()).hexdigest()
+            cached = store.get_blob(rid, "thread_text")
+            if cached and cached.get("key") == key and not fresh:
+                for t in r.threads:
+                    t.name, t.purpose, t.text_source = cached["threads"].get(t.id, (t.name, t.purpose, t.text_source))
+                r.whole, r.whole_source = cached["whole"], cached["whole_source"]
+                for k in r.connections:
+                    k.text = cached["connections"].get(f"{k.a}-{k.b}", k.text)
+            else:
+                notes = write_threads(svc.strong, svc.ledger, rid, r, bs.stories, cls_text)
+                if not notes:
+                    store.put_blob(rid, "thread_text", {
+                        "key": key, "threads": {t.id: (t.name, t.purpose, t.text_source) for t in r.threads},
+                        "whole": r.whole, "whole_source": r.whole_source,
+                        "connections": {f"{k.a}-{k.b}": k.text for k in r.connections}})
+            told = f"thread text by {strong.model}"
+        store.replace_blobs(rid, ["reading"], ["story_reading:"],
+                            {"reading": r, **{f"story_reading:{sid}": sr for sid, sr in per.items()}})
+        store.prune_marks(rid, {k.key for k in r.checks})
+        msg = (f"{len(r.threads)} thread(s), {sum(k.shown for k in r.connections)} connection(s) shown, "
+               f"{len(r.checks)} check(s); {told}")
+        if notes:
+            raise Degraded(msg + "; " + "; ".join(notes))
+        return msg
+
     def finalize():
         sb = ctx.get("storyboard")
         if status.get("ingest") not in ("ok", "degraded"):
@@ -425,7 +490,7 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
         for name, fn in [("ingest", ingest), ("swarm_read", swarm_read), ("diffmap", diffmap), ("tu_select", tu_select),
                          ("layers", layers), ("facts", facts), ("impact", impact), ("detectors", detectors),
                          ("pieces", pieces), ("stories", stories), ("review", review),
-                         ("verdicts", verdicts), ("board", board), ("llm", llm),
+                         ("verdicts", verdicts), ("board", board), ("llm", llm), ("reading", reading),
                          ("finalize", finalize)]:
             stage(name, fn)
 
```

`backend/codetortoise/reading.py` (diff):

```diff
diff --git a/backend/codetortoise/reading.py b/backend/codetortoise/reading.py
index 5768269..136a528 100644
--- a/backend/codetortoise/reading.py
+++ b/backend/codetortoise/reading.py
@@ -20,6 +20,7 @@ from codetortoise.pieces import PieceSet, node_cl
 from codetortoise.stories import Story, StoryDetail, StorySet
 from codetortoise.targets import UNKNOWN
 
+READING_VERSION = 1                   # bump with every change to the thread text's prompt or checks (keys its cache)
 _KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}
 ConnKind = Literal["caller", "vocabulary", "condition", "place", "bundled"]
 _CONN_RANK = {"caller": 1, "vocabulary": 2, "condition": 3, "place": 4, "bundled": 5}
@@ -1070,3 +1071,19 @@ def build_reading(ss: StorySet, c: BoardContext, details: dict[str, StoryDetail]
                                  place_text=_place_text(s.id, t.stories, strong) if t else "",
                                  thread=t.id if t else None, position=t.stories.index(s.id) + 1 if t else None)
     return reading, per
+
+
+def with_marks(r: Reading, marks: dict[str, dict], findings: list[Finding]) -> dict:
+    """The reading as viewers see it (§7.4): each mark with `changed` when the source line at its place is no longer the
+    line it was marked at (the check is open again), and the headline and threads' open counts without the marked
+    checks."""
+    line = {k.key: k.source_line for k in r.checks + r.cleared}
+    view = {key: {**m, "changed": m["source_line"] != line.get(key, m["source_line"])}
+            for key, m in marks.items() if key in line}
+    marked = {key for key, m in view.items() if not m["changed"]}
+    out = r.model_dump()
+    out["marks"] = view
+    out["headline"] = headline(r.checks, marked, findings).model_dump()
+    for t in out["threads"]:
+        t["open_checks"] = sum(1 for k in r.checks if k.thread == t["id"] and k.key not in marked)
+    return out
```

`backend/codetortoise/store.py` (diff):

```diff
diff --git a/backend/codetortoise/store.py b/backend/codetortoise/store.py
index b19b5a9..dd9eda3 100644
--- a/backend/codetortoise/store.py
+++ b/backend/codetortoise/store.py
@@ -40,9 +40,11 @@ CREATE TABLE IF NOT EXISTS llm_budget(review_id INTEGER, budget INTEGER, set_by
 CREATE TABLE IF NOT EXISTS llm_rounds(review_id INTEGER, rounds INTEGER, set_by TEXT, set_at TEXT);
 CREATE TABLE IF NOT EXISTS briefs(review_id INTEGER PRIMARY KEY, cache_key TEXT, json TEXT, created_at TEXT);
 CREATE INDEX IF NOT EXISTS ix_briefs_key ON briefs(cache_key);
+CREATE TABLE IF NOT EXISTS check_marks(review_id INTEGER, key TEXT, user TEXT, at TEXT, source_line TEXT,
+    PRIMARY KEY(review_id, key));
 """
 
-ANCHOR_KINDS = {"line", "function", "finding", "chapter", "review", "story", "flow", "file"}
+ANCHOR_KINDS = {"line", "function", "finding", "chapter", "review", "story", "flow", "file", "check"}
 
 
 def _now() -> str:
@@ -237,6 +239,26 @@ class Store:
     def delete_comment(self, cid: int) -> None:
         self._exec("DELETE FROM comments WHERE id=? OR parent_id=?", (cid, cid))
 
+    # ---- To check marks (spec 2026-10-07-review-reading §7.4) -------------
+    def set_mark(self, rid: int, key: str, user: str, source_line: str) -> dict:
+        """Mark a check "looks fine" for everyone viewing the review; `source_line` is the line it was marked at."""
+        at = _now()
+        self._exec("INSERT OR REPLACE INTO check_marks(review_id, key, user, at, source_line) VALUES(?,?,?,?,?)",
+                   (rid, key, user, at, source_line))
+        return {"key": key, "user": user, "at": at, "source_line": source_line}
+
+    def clear_mark(self, rid: int, key: str) -> None:
+        self._exec("DELETE FROM check_marks WHERE review_id=? AND key=?", (rid, key))
+
+    def list_marks(self, rid: int) -> dict[str, dict]:
+        return {r["key"]: r for r in self._all("SELECT key, user, at, source_line FROM check_marks WHERE review_id=? "
+                                               "ORDER BY key", (rid,))}
+
+    def prune_marks(self, rid: int, keep: set[str]) -> None:
+        """A re-run drops the marks of checks it no longer finds."""
+        for key in set(self.list_marks(rid)) - keep:
+            self.clear_mark(rid, key)
+
     # ---- sessions --------------------------------------------------------
     def create_session(self, user: str, ttl_days: int = 7) -> str:
         token = secrets.token_urlsafe(32)
```

`backend/codetortoise/web/app.py` (diff):

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index 9aa6a9b..bcf49c0 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -18,6 +18,7 @@ from codetortoise.names import cited, names, neighbours
 from codetortoise.paths import canon
 from codetortoise.pipeline import JobRunner
 from codetortoise.provenance import tag_board
+from codetortoise.reading import Check, Reading, with_marks
 from codetortoise.services import Services
 from codetortoise.swarm import SwarmError
 from codetortoise.vcs.p4runner import P4Error
@@ -61,7 +62,7 @@ class RoundsIn(BaseModel):
 
 class CommentIn(BaseModel):
     body: str = Field(min_length=1, max_length=20000)
-    anchor_kind: Literal["line", "function", "finding", "chapter", "review", "story", "flow", "file"]
+    anchor_kind: Literal["line", "function", "finding", "chapter", "review", "story", "flow", "file", "check"]
     anchor: dict = Field(default_factory=dict)
     parent_id: int | None = None
 
@@ -150,9 +151,19 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         return {"queued": True}
 
     # ---- reviews ------------------------------------------------------------
+    def reading_view(rid: int) -> dict | None:
+        raw = store.get_blob(rid, "reading")
+        if not raw:
+            return None
+        return with_marks(Reading.model_validate(raw), store.list_marks(rid), store.list_findings(rid))
+
     @app.get("/api/reviews")
     def list_reviews(_: str = Depends(user_of)):
-        return store.list_reviews()
+        out = store.list_reviews()
+        for r in out:
+            view = reading_view(r["id"])
+            r["headline"] = view["headline"] if view else None
+        return out
 
     @app.post("/api/reviews")
     def create_review(body: ReviewIn, user: str = Depends(owner_of)):
@@ -253,8 +264,42 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         named(out["board"].get("layers", []))
         if out["graph"]:
             named(out["graph"].get("layers", []))
+        out["reading"] = store.get_blob(rid, f"story_reading:{sid}")
         return out
 
+    NO_READING = "this review has no reading: re-run it"
+
+    @app.get("/api/reviews/{rid}/reading")
+    def reading(rid: int, _: str = Depends(user_of)):
+        """Threads, connections, To check and the marks on it (spec 2026-10-07-review-reading §10.4)."""
+        review_or_404(rid)
+        view = reading_view(rid)
+        if view is None:
+            raise HTTPException(404, NO_READING)
+        return view
+
+    def check_or_404(rid: int, key: str) -> Check:
+        raw = store.get_blob(rid, "reading")
+        if not raw:
+            raise HTTPException(404, NO_READING)
+        r = Reading.model_validate(raw)
+        k = next((k for k in r.checks + r.cleared if k.key == key), None)
+        if k is None:
+            raise HTTPException(404, "That check no longer exists after the re-run.")
+        return k
+
+    @app.post("/api/reviews/{rid}/checks/{key:path}/mark")
+    def mark_check(rid: int, key: str, user: str = Depends(user_of)):
+        review_or_404(rid)
+        k = check_or_404(rid, key)
+        return store.set_mark(rid, k.key, user, k.source_line)
+
+    @app.delete("/api/reviews/{rid}/checks/{key:path}/mark")
+    def unmark_check(rid: int, key: str, _: str = Depends(user_of)):
+        review_or_404(rid)
+        store.clear_mark(rid, key)
+        return {"ok": True}
+
     @app.get("/api/reviews/{rid}/locate")
     def locate(rid: int, node: str | None = None, flow: str | None = None, finding: str | None = None,
                _: str = Depends(user_of)):
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_store.py tests/test_web.py -q`
Expected: PASS: `62 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `604 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_pipeline.py backend/tests/test_store.py backend/tests/test_web.py backend/codetortoise/pipeline.py backend/codetortoise/reading.py backend/codetortoise/store.py backend/codetortoise/web/app.py
git commit -m "feat(reading): a reading stage after llm stores threads, To check and story tiles; marks are shared, kept, dropped or reopened"
```

### Task 8: A fixture that reads as three connected threads

Spec §13 (fixture). CLs 103 and 104 join the C fixture: CL 103 adds a logger level (`logger_init` starts at level 1), CL 104 reads it back (`logger_level`) and steps an unrelated C++ engine by three. A review of CLs 101–104 reads as three threads: the hal/uart thread and the logger thread meet in `main`; the engine thread is tied to the rest only by arriving in CL 104 (an Ask the author check). The fake model names threads after their first story, so the e2e tests can tell its text from the fixed one.

**Files:**
- Test: `backend/tests/test_pipeline.py`
- Test: `frontend/e2e/fake_llm.py`
- Modify: `backend/codetortoise/fixture.py`
- Create: `backend/codetortoise/fixtures/cfixture/cl103/service/logger.c`
- Create: `backend/codetortoise/fixtures/cfixture/cl103/service/logger.h`
- Create: `backend/codetortoise/fixtures/cfixture/cl104/cpp/engine.cpp`
- Create: `backend/codetortoise/fixtures/cfixture/cl104/service/logger.c`

**Interfaces:**
- Consumes: the reading stage (Task 7).
- Produces: fixture CLs 103 and 104 (`fixture.py`, `fixtures/cfixture/cl103`, `cl104`); `fake_llm.threads(user)` answering the `THREADS (id` prompt.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pipeline.py` (diff):

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index d37ec76..f5c5709 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -506,3 +506,25 @@ def test_the_strong_model_names_the_threads_once_and_a_rerun_reuses_the_text(fx,
     run_review(rid, svc)
     assert sum("THREADS (id" in p for p in llm.prompts) == asked == 1
     assert svc.store.get_blob(rid, "reading")["whole_source"] == "llm"
+
+
+def test_a_four_cl_review_reads_as_three_connected_threads(fx, tmp_path):
+    """CLs 103–104 add a logger level across two CLs (one thread meeting the UART thread in `main`) and an engine
+    change tied to the rest only by CL 104 (spec 2026-10-07-review-reading §13)."""
+    svc = make_services(fx, tmp_path)
+    rid = svc.store.create_review("t", "owner", [101, 102, 103, 104])
+    run_review(rid, svc)
+    r = svc.store.get_blob(rid, "reading")
+    titles = {s["id"]: s["title"] for s in svc.store.get_blob(rid, "stories")["stories"]}
+    assert [[titles[s] for s in t["stories"]] for t in r["threads"]] == [
+        ["`hal_write`'s signature changed; `uart_init` calls it",
+         "`uart_send` can now return -2; `logger_flush` ignores it (1 more effect)"],
+        ["Other changes in `service` (`logger_init`)", "Other changes in `service` (`logger_level`)"],
+        ["Other changes in `cpp`"]]
+    assert [t["cls"] for t in r["threads"]] == [[101, 102], [103, 104], [104]]
+    assert [(k["a"], k["b"], k["kind"], k["text"]) for k in r["connections"] if k["shown"]] == [
+        ("T1", "T2", "caller", "both run inside `main`"), ("T2", "T3", "bundled", "nothing besides arriving in CL 104")]
+    assert [(k["kind"], k["thread"]) for k in r["checks"]] == [
+        ("confirm", "T1"), ("confirm", "T1"), ("caller", "T1"), ("result", "T1"), ("reader", "T1"), ("ask", "T3")]
+    assert r["whole"] == "3 threads: A and B: both run inside `main`; B and C: nothing besides arriving in CL 104."
+    assert "`service/logger.h` header change → 2 files rebuild" in [b["text"] for b in r["build_impact"]]
```

`frontend/e2e/fake_llm.py` (diff):

```diff
diff --git a/frontend/e2e/fake_llm.py b/frontend/e2e/fake_llm.py
index f52482a..10ea6b3 100644
--- a/frontend/e2e/fake_llm.py
+++ b/frontend/e2e/fake_llm.py
@@ -57,7 +57,18 @@ def tier1_review(user: str) -> dict:
     return {"action": "answer", "verdicts": verdicts}
 
 
+def threads(user: str) -> dict:
+    """Each thread named after its first story; the whole cites the first thread; connections keep their text."""
+    rows = re.findall(r"^(T\d+) \|.*?\| (S\d+) ", user, re.M)
+    return {"threads": [{"id": t, "name": f"Thread of {sid}", "purpose": f"This thread holds {sid} and what builds on it.",
+                         "cites": [sid]} for t, sid in rows],
+            "whole": "The change reworks the UART driver and what calls it. Each thread says what it adds.",
+            "whole_cites": [rows[0][0]] if rows else [], "connections": []}
+
+
 def answer(system: str, user: str) -> dict:
+    if "THREADS (id" in user:
+        return threads(user)
     if "forming the stories of a change" in system:
         return {"related": [], "merge": []} if "STORIES (key | title" in user else tier1_stories(user)
     if "judging the risks of one story" in system:
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py -q`
Expected: FAIL: `1 failed, 25 passed`; the first error is `TypeError: 'NoneType' object is not subscriptable`

- [ ] **Step 3: Implement**

`backend/codetortoise/fixture.py` (diff):

```diff
diff --git a/backend/codetortoise/fixture.py b/backend/codetortoise/fixture.py
index 59b24bc..afd99ad 100644
--- a/backend/codetortoise/fixture.py
+++ b/backend/codetortoise/fixture.py
@@ -11,6 +11,8 @@ FIXTURE_SRC = Path(__file__).parent / "fixtures" / "cfixture"
 CL_DESCRIPTIONS = {
     101: "uart: count tx stats and report overflow",
     102: "uart: add flags field; hal_write takes unsigned reg",
+    103: "logger: start at log level 1",
+    104: "logger: read the level back; engine: step by three",
 }
 
 
```

`backend/codetortoise/fixtures/cfixture/cl103/service/logger.c` (new file):

```
#include "service/logger.h"

int logger_init(struct Logger *lg, struct Uart *u)
{
    lg->uart = u;
    lg->dropped = 0;
    lg->level = 1;
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
```

`backend/codetortoise/fixtures/cfixture/cl103/service/logger.h` (new file):

```
#ifndef SERVICE_LOGGER_H
#define SERVICE_LOGGER_H

#include "driver/uart.h"

struct Logger {
    struct Uart *uart;
    int dropped;
    int level;
};

int logger_init(struct Logger *lg, struct Uart *u);
int logger_write(struct Logger *lg, const char *msg, int len);
void logger_flush(struct Logger *lg);
int logger_level(const struct Logger *lg);

#endif
```

`backend/codetortoise/fixtures/cfixture/cl104/cpp/engine.cpp` (new file):

```
#include "cpp/engine.h"

namespace svc {

Base::~Base() {}

int Base::base(State &s)
{
    return s.x;
}

int Engine::base(State &s)
{
    s.x = 1;
    return 1;
}

int Engine::step(State &st)
{
    auto &r = st.inner;
    r.n += 3;
    level = 3;
    return base(st) + 1;
}

}  // namespace svc
```

`backend/codetortoise/fixtures/cfixture/cl104/service/logger.c` (new file):

```
#include "service/logger.h"

int logger_init(struct Logger *lg, struct Uart *u)
{
    lg->uart = u;
    lg->dropped = 0;
    lg->level = 1;
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

Run: `cd backend && uv run pytest tests/test_pipeline.py -q`
Expected: PASS: `26 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `605 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 140 passed (140)`; Playwright `1 failed, 90 passed` (in the replay, the first run's failures were timeouts under load; `npx playwright test --last-failed` then gave `1 passed`)

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_pipeline.py frontend/e2e/fake_llm.py backend/codetortoise/fixture.py backend/codetortoise/fixtures/cfixture/cl103/service/logger.c backend/codetortoise/fixtures/cfixture/cl103/service/logger.h backend/codetortoise/fixtures/cfixture/cl104/cpp/engine.cpp backend/codetortoise/fixtures/cfixture/cl104/service/logger.c
git commit -m "test(fixture): CLs 103–104 add a logger level across two CLs and an engine change tied only by its CL; the fake model names threads"
```

### Task 9: The reading reaches the browser; the header and Reviews list say what to act on

Spec §5.4, §10.4. TypeScript mirrors of the reading's models (`reading/types.ts`); `reading/checks.ts` holds the To check logic the tiles share (kind labels, open or marked, counts, letters, grouping by thread, places, mark lines). `api.ts` gains `reading`, `markCheck` and `unmarkCheck` (keys encoded with `encodeURIComponent`) and the comment anchor kind `check`; `useReview` loads the reading (null on 404, for reviews stored before it). `HeadlinePill` shows the headline in the workspace header and in the Reviews list in place of the risk pill. On the backend, each check gains `depot`, the depot file the side panel opens.

**Files:**
- Test: `backend/tests/test_reading.py`
- Test: `frontend/e2e/landing.spec.ts`
- Test: `frontend/e2e/theme.spec.ts`
- Test: `frontend/e2e/workspace-tier1.spec.ts`
- Test: `frontend/e2e/workspace.spec.ts`
- Test: `frontend/src/reading/checks.test.ts`
- Modify: `backend/codetortoise/reading.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/board/types.ts`
- Create: `frontend/src/components/HeadlinePill.tsx`
- Modify: `frontend/src/pages/Reviews.tsx`
- Create: `frontend/src/reading/checks.ts`
- Create: `frontend/src/reading/types.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/useReview.ts`

**Interfaces:**
- Consumes: the API (Task 7).
- Produces: `Check.depot: str | None` (backend); TS types `CheckKind`, `ConnKind`, `Thread`, `Connection`, `Reason`, `Check`, `Mark`, `Headline`, `BuildImpact`, `TestsRow`, `Reading` (with `marks`), `ContractRow`, `WhereFn`, `WhereFile`, `CallPath`, `StoryReading`;
  `checks.ts`: `KIND_LABEL`, `isOpen(k, marks)`, `splitChecks(checks, marks)`, `openCount(open, total, ofTotal)`, `letter(i, id)`, `byThread(r)`, `placeOf(k)`, `markLine(m, now)`;
  `api.reading(id)`, `api.markCheck(id, key)`, `api.unmarkCheck(id, key)`, `ReviewRow.headline`, `StoryDetail.reading`; `useReview()`'s `reading` and `loadReading`; `components/HeadlinePill`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_reading.py` (diff):

```diff
diff --git a/backend/tests/test_reading.py b/backend/tests/test_reading.py
index a7a1aae..11a95bc 100644
--- a/backend/tests/test_reading.py
+++ b/backend/tests/test_reading.py
@@ -1,5 +1,5 @@
 """How a review reads (spec 2026-10-07-review-reading §4–§8): story links, threads, connections, reading order."""
-from test_stories import _edit, _in_cls, _same, _world
+from test_stories import W, _edit, _in_cls, _same, _world
 
 from codetortoise.board import analyse
 from codetortoise.reading import (
@@ -568,6 +568,12 @@ def test_the_reading_puts_threads_in_order_with_checks_counted_and_each_story_it
     assert reading.whole_source == "template"
 
 
+def test_each_check_names_the_depot_file_the_side_panel_opens():
+    c, ss = _caller_world()
+    reading, per = build_reading(ss, c)
+    assert [(k.kind, k.path, k.depot) for k in reading.checks] == [("caller", "svc/flush.c", f"//d{W}/svc/flush.c")]
+    assert per["S1"].checks[0].depot == f"//d{W}/svc/flush.c"
+
 def test_ask_the_author_does_not_move_a_thread_up_the_reading_order():
     c, ss = _chain()
     reading, _ = build_reading(ss, c)
@@ -587,4 +593,5 @@ def test_the_fixture_reads_as_threads_with_checks(fx, analysed, fx_source):
     assert sorted(s for t in reading.threads for s in t.stories) == sorted(s.id for s in ss.stories)
     assert set(per) == {s.id for s in ss.stories}
     assert all(not k.path.startswith("/") for k in reading.checks)
+    assert all(k.depot.startswith("//") for k in reading.checks if k.path)
     assert {k.kind for k in reading.checks} >= {"confirm"}
```

`frontend/e2e/landing.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/landing.spec.ts b/frontend/e2e/landing.spec.ts
index 4aad404..cc6d568 100644
--- a/frontend/e2e/landing.spec.ts
+++ b/frontend/e2e/landing.spec.ts
@@ -36,7 +36,8 @@ test.describe("desktop", () => {
     const n = Number((await high.locator("span").textContent())!.trim());
     await high.click();
     await expect(rows).toHaveCount(n);
-    for (const r of await rows.all()) await expect(r.locator(".rv-risk")).toHaveText("HIGH");
+    // each row says what to act on; without the strong model that is the rules' top severity (review reading §5.4)
+    for (const r of await rows.all()) await expect(r.locator(".rv-headline")).toHaveText(/ risk · rules only$/);
     await page.getByRole("button", { name: /^Mine/ }).click();
     await expect(rows).toHaveCount(total);                                            // every review here was started by demo
   });
```

`frontend/e2e/theme.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/theme.spec.ts b/frontend/e2e/theme.spec.ts
index 0c26d25..9720211 100644
--- a/frontend/e2e/theme.spec.ts
+++ b/frontend/e2e/theme.spec.ts
@@ -20,6 +20,7 @@ const CHECKS = [
   ".bd-toolbar .bd-ibtn",          // a graph button
   ".topbar a",                     // app chrome link
   ".ws-rail .bd-pill.high",        // a high-risk pill
+  ".ws-head .ct-headline",         // what to act on
 ];
 
 for (const theme of ["light", "dark"] as const) {
```

`frontend/e2e/workspace-tier1.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-tier1.spec.ts b/frontend/e2e/workspace-tier1.spec.ts
index 2b95de6..5c25383 100644
--- a/frontend/e2e/workspace-tier1.spec.ts
+++ b/frontend/e2e/workspace-tier1.spec.ts
@@ -30,6 +30,12 @@ test.describe("stories formed by a strong model", () => {
     await expectNamed(page);
   });
 
+  test("the header counts the open hazards the strong model found", async ({ page }) => {
+    await startReview(page);
+    await expect(page.locator(".ws-head .ct-headline")).toHaveText("1 hazard");
+    await expect(page.locator(".ws-head .ct-headline")).toHaveClass(/\bhazard\b/);
+  });
+
   test("the pieces it could not place are listed last, each with the check that failed", async ({ page }) => {
     const base = await startReview(page);
     const group = page.getByRole("region", { name: /^Stories/ }).locator(".ws-group").last();
```

`frontend/e2e/workspace.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index fd94ddf..8c59628 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -53,6 +53,13 @@ test.describe("desktop", () => {
     await expectNamed(page);
   });
 
+  test("the header says what to act on in place of the risk pill", async ({ page }) => {
+    await startReview(page);
+    const head = page.locator(".ws-head");
+    await expect(head.locator(".ct-headline")).toHaveText("Medium risk · rules only");   // header fan-out never raises it
+    await expect(head.locator(".bd-pill.high")).toHaveCount(0);
+  });
+
   test("an address to something that does not exist says so", async ({ page }) => {
     const base = await startReview(page);
     await page.goto(`${base}/s/S9`);
```

`frontend/src/reading/checks.test.ts` (new file):

```ts
import { describe, expect, it } from "vitest";
import { byThread, KIND_LABEL, letter, markLine, openCount, placeOf, splitChecks } from "./checks";
import type { Check, Mark, Reading, Thread } from "./types";

const check = (key: string, extra: Partial<Check> = {}): Check => ({
  key, kind: "caller", story: "S1", thread: "T1", path: "svc/flush.c", depot: "//d/svc/flush.c", line: 3, function: "flush",
  node: "N3", text: "`flush` calls `send` and was not updated for its new signature", source_line: "b = 0;", finding: null,
  cites: [], also: [], ...extra,
});
const mark = (key: string, changed = false): Mark => ({ key, user: "ana", at: "2026-10-07T10:00:00+00:00", source_line: "b = 0;", changed });
const thread = (id: string, name: string): Thread => ({ id, name, purpose: "", text_source: "template", stories: [], cls: [], open_checks: 0 });
const reading = (checks: Check[], threads: Thread[]): Reading => ({
  whole: "", whole_source: "template", threads, connections: [], order: [], reasons: {}, checks, cleared: [], build_impact: [],
  coverage: [], headline: { text: "No hazards found", tone: "none", rules_only: false }, rules_only: false, tests: null, marks: {},
});

describe("To check", () => {
  it("names every kind the way the reviewer reads it", () => {
    expect(KIND_LABEL.caller).toBe("Caller not updated");
    expect(KIND_LABEL.result).toBe("Result handled the old way");
    expect(KIND_LABEL.reader).toBe("Unchanged reader");
    expect(KIND_LABEL.ask).toBe("Ask the author");
  });

  it("puts open rows first and marked ones after, a mark on a changed line counting as open", () => {
    const rows = [check("a"), check("b"), check("c")];
    const { open, marked } = splitChecks(rows, { a: mark("a"), c: mark("c", true) });
    expect(open.map((k) => k.key)).toEqual(["b", "c"]);
    expect(marked.map((k) => k.key)).toEqual(["a"]);
  });

  it("counts open checks without ever showing an empty count", () => {
    expect(openCount(5, 5, false)).toBe("5 open");
    expect(openCount(3, 5, true)).toBe("3 of 5 open");
    expect(openCount(0, 2, true)).toBe("all 2 looked at");
    expect(openCount(0, 0, false)).toBe("");
  });

  it("groups checks by thread in reading order, checks with no thread last under Across the change", () => {
    const r = reading([check("x", { thread: null, story: null }), check("b", { thread: "T2" }), check("a")],
                      [thread("T1", "`send` in drv"), thread("T2", "`log` in svc")]);
    expect(byThread(r).map((g) => [g.label, g.checks.map((k) => k.key)])).toEqual([
      ["A · `send` in drv", ["a"]], ["B · `log` in svc", ["b"]], ["Across the change", ["x"]]]);
  });

  it("leaves out threads with nothing to check", () => {
    const r = reading([check("a")], [thread("T1", "one"), thread("T2", "two")]);
    expect(byThread(r).map((g) => g.label)).toEqual(["A · one"]);
  });

  it("letters threads A to Z, then by id", () => {
    expect([letter(0), letter(25), letter(26, "T27")]).toEqual(["A", "Z", "T27"]);
  });

  it("says where a check is, workspace-relative", () => {
    expect(placeOf(check("a"))).toBe("svc/flush.c:3 in `flush`");
    expect(placeOf(check("a", { line: null, function: null }))).toBe("svc/flush.c");
    expect(placeOf(check("a", { path: "", line: null, function: null }))).toBe("");
  });

  it("says who marked a check and when, or that its line changed since", () => {
    const now = Date.parse("2026-10-07T12:00:00+00:00");
    expect(markLine(mark("a"), now)).toBe("Looks fine · ana · 2h ago");
    expect(markLine(mark("a", true), now)).toBe("Changed since marked by ana");
  });
});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: FAIL: `2 failed, 45 passed`; the first error is `AttributeError: 'Check' object has no attribute 'depot'`

Run: `cd frontend && npx vitest run src/reading/checks.test.ts`
Expected: FAIL: `Tests no tests`; the first error is `Error: Cannot find module './checks' imported from frontend/src/reading/checks.test.ts`

Run: `cd frontend && npm run build && npx playwright test e2e/landing.spec.ts e2e/theme.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace.spec.ts`
Expected: FAIL: `npm run build fails with 7 type error(s)`; the first error is `src/reading/checks.test.ts(2,89): error TS2307: Cannot find module './checks' or its corresponding type declarations.`

- [ ] **Step 3: Implement**

`backend/codetortoise/reading.py` (diff):

```diff
diff --git a/backend/codetortoise/reading.py b/backend/codetortoise/reading.py
index 136a528..0ff0cbe 100644
--- a/backend/codetortoise/reading.py
+++ b/backend/codetortoise/reading.py
@@ -114,6 +114,7 @@ class Check(BaseModel):
     story: str | None = None
     thread: str | None = None
     path: str = ""                    # workspace-relative
+    depot: str | None = None          # the file the side panel opens
     line: int | None = None
     function: str | None = None
     node: str | None = None           # the place's function
@@ -1024,6 +1025,15 @@ def _tests_row(ss: StorySet, threads: list[Thread], x: _Ctx) -> TestsRow | None:
                     covers=[t.id for t in threads if t.id in covered], untested=[t.id for t in threads if t.id not in covered])
 
 
+def _set_depots(c: BoardContext, checks: list[Check]) -> None:
+    """Each check's depot file, which its Open button shows in the side panel (§7.2)."""
+    root = c.root.rstrip("/")
+    local = {k.path: k.path if k.path.startswith("/") or not root else f"{root}/{k.path}" for k in checks if k.path}
+    depots = c.depots_for(sorted(set(local.values()))) if local else {}
+    for k in checks:
+        k.depot = depots.get(local.get(k.path, ""))
+
+
 def build_reading(ss: StorySet, c: BoardContext, details: dict[str, StoryDetail] | None = None, analysis=None,
                   pieces: PieceSet | None = None, targets: dict[str, list[str]] | None = None, has_tests: bool = False,
                   test_callers: Callable[[str], set[str]] | None = None, includers: Callable[[str], set[str]] | None = None,
@@ -1051,6 +1061,7 @@ def build_reading(ss: StorySet, c: BoardContext, details: dict[str, StoryDetail]
     conns, (rows, cleared) = checks_for(threads)
     for t in threads:
         t.open_checks = sum(1 for k in rows if k.thread == t.id)
+    _set_depots(c, rows + cleared)
     strong = [lk for lk in links if lk.strength == "strong"]
     order = [s for t in threads for s in t.stories] + [s.id for s in ss.stories if s.kind == "tests"]
     outside = 0
```

`frontend/src/api.ts` (diff):

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index 3761973..b476c8b 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -5,6 +5,8 @@ export interface Me { user: string; is_owner: boolean; swarm_ready: boolean }
 export interface ReviewRow {
   id: number; title: string; created_by: string; created_at: string;
   status: string; risk: "low" | "medium" | "high" | null; cls: number[];
+  /** What to act on (spec 2026-10-07-review-reading §5.4); null: run before the reading existed. */
+  headline?: Headline | null;
 }
 export interface Stage { name: string; status: StageStatus; message: string; started_at: string | null; finished_at: string | null }
 export interface SwarmInfo { id: number; state: string; state_label?: string; url: string; votes: Record<string, number>; author?: string }
@@ -30,7 +32,7 @@ export interface Neighbour extends NodeName { id: string; changed: boolean; test
 export interface Neighbours { node: Neighbour; callers: { total: number; items: Neighbour[] }; callees: { total: number; items: Neighbour[] } }
 export interface PerCl { cl: number; before: string; after: string }
 export interface FileChange { depot: string; local: string; action: string; before: string; after: string; base_rev: string | null; per_cl: PerCl[] }
-export type AnchorKind = "line" | "function" | "finding" | "chapter" | "review" | "story" | "flow" | "file";
+export type AnchorKind = "line" | "function" | "finding" | "chapter" | "review" | "story" | "flow" | "file" | "check";
 export interface Comment {
   id: number; review_id: number; parent_id: number | null; author: string; body: string;
   anchor_kind: AnchorKind; anchor: Record<string, unknown>; resolved: boolean; created_at: string; edited_at: string | null;
@@ -57,6 +59,8 @@ export interface Health { checks: HealthCheck[]; ready: boolean; index_generatio
 
 export type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
 import type { Board, Overview, SourceText, StoryDetail, StorySet } from "./board/types";
+import type { Headline, Mark, Reading } from "./reading/types";
+export type { Headline, Mark, Reading } from "./reading/types";
 
 export class ApiError extends Error {
   constructor(public status: number, message: string) { super(message); }
@@ -92,6 +96,10 @@ export const api = {
   overview: (id: number) => call<Overview>("GET", `/api/reviews/${id}/overview`),
   stories: (id: number) => call<StorySet>("GET", `/api/reviews/${id}/stories`),
   story: (id: number, sid: string) => call<StoryDetail>("GET", `/api/reviews/${id}/stories/${sid}`),
+  reading: (id: number) => call<Reading>("GET", `/api/reviews/${id}/reading`),
+  /** "Looks fine" on a To check row, for everyone viewing the review; its key holds "|", so it is encoded. */
+  markCheck: (id: number, key: string) => call<Mark>("POST", `/api/reviews/${id}/checks/${encodeURIComponent(key)}/mark`),
+  unmarkCheck: (id: number, key: string) => call("DELETE", `/api/reviews/${id}/checks/${encodeURIComponent(key)}/mark`),
   locate: (id: number, q: { node?: string; flow?: string; finding?: string }) =>
     call<{ cluster: string | null; story?: string | null }>("GET", `/api/reviews/${id}/locate?${new URLSearchParams(q)}`),
   source: (id: number, path: string, side: "before" | "after" = "after") =>
```

`frontend/src/board/types.ts` (diff):

```diff
diff --git a/frontend/src/board/types.ts b/frontend/src/board/types.ts
index cb16afc..2b39a96 100644
--- a/frontend/src/board/types.ts
+++ b/frontend/src/board/types.ts
@@ -1,4 +1,5 @@
 /** Review board model, as served by GET /api/reviews/{id}/board (backend codetortoise/board.py). */
+import type { StoryReading } from "../reading/types";
 export interface NodeChange { kind: "modified" | "signature" | "added" | "removed"; add: number; rem: number }
 export interface BoardNode {
   id: string; key: string; label: string; kind: "function" | "field" | "struct" | "more"; layer: number | null;
@@ -83,6 +84,8 @@ export interface StorySite {
 export interface StoryDetail {
   story: Story; board: Board; graph: Board | null; functions: StoryFunction[]; sites: StorySite[]; also_in: StoryRef[];
   pieces?: StoryPiece[];
+  /** The story's tiles (spec 2026-10-07-review-reading §6); null: run before the reading existed. */
+  reading?: StoryReading | null;
 }
 export interface StorySet {
   summary: string; stories: Story[];
```

`frontend/src/components/HeadlinePill.tsx` (new file):

```tsx
import type { Headline } from "../reading/types";

/** What to act on (spec 2026-10-07-review-reading §5.4): red for open hazards, amber for checks to confirm, neutral
 * otherwise; "rules only" when the strong model did not judge the risks. */
export default function HeadlinePill({ h, className = "" }: { h: Headline; className?: string }) {
  return (
    <span className={`ct-headline ${h.tone} ${className}`.trim()}
          title={h.rules_only ? "Judged by the detectors' rules, without the strong model" : undefined}>
      {h.text}{h.rules_only && <span className="ct-rules"> · rules only</span>}
    </span>
  );
}
```

`frontend/src/pages/Reviews.tsx` (diff):

```diff
diff --git a/frontend/src/pages/Reviews.tsx b/frontend/src/pages/Reviews.tsx
index 684e352..a35be0c 100644
--- a/frontend/src/pages/Reviews.tsx
+++ b/frontend/src/pages/Reviews.tsx
@@ -2,6 +2,7 @@ import { type FormEvent, useEffect, useMemo, useState } from "react";
 import { Link, useNavigate } from "react-router-dom";
 import { api, type ReviewRow } from "../api";
 import { useMe } from "../App";
+import HeadlinePill from "../components/HeadlinePill";
 import Logo from "../components/Logo";
 import { ago, type Chip, chipCounts, filterReviews, highlight, parseCls } from "../lib/reviewFilter";
 
@@ -71,7 +72,8 @@ export default function Reviews() {
               <b>{highlight(r.title, query).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</b>
               <span className="cls">{r.cls.map((c) => <span key={c} className="cl">{c}</span>)}</span>
               <span className="sp" />
-              {r.risk && <span className={`rv-risk ${r.risk}`}>{r.risk.toUpperCase()}</span>}
+              {r.headline ? <HeadlinePill h={r.headline} className="rv-headline" />
+                : r.risk && <span className={`rv-risk ${r.risk}`}>{r.risk.toUpperCase()}</span>}
               <span className={`rv-status ${r.status}`}>{LIVE.has(r.status) ? `${r.status}…` : r.status}</span>
               <span className="when">{ago(r.created_at)} · {r.created_by}</span>
             </Link>
```

`frontend/src/reading/checks.ts` (new file):

```ts
/** The To check list (spec 2026-10-07-review-reading §7): kinds, open and marked rows, counts and groups. */
import { ago } from "../lib/reviewFilter";
import type { Check, CheckKind, Mark, Reading } from "./types";

export const KIND_LABEL: Record<CheckKind, string> = {
  hazard: "Hazard", confirm: "Confirm", caller: "Caller not updated", result: "Result handled the old way",
  reader: "Unchanged reader", target: "Other build target", untested: "No test touched", unanalysed: "Not analysed",
  ask: "Ask the author", cleared: "No hazard",
};

/** Open unless someone marked it and its line has not changed since (§7.4). */
export const isOpen = (k: Check, marks: Record<string, Mark>) => !marks[k.key] || marks[k.key].changed;

/** Open rows first, in their own order, then the marked ones (§7.2). */
export function splitChecks(checks: Check[], marks: Record<string, Mark>): { open: Check[]; marked: Check[] } {
  return { open: checks.filter((k) => isOpen(k, marks)), marked: checks.filter((k) => !isOpen(k, marks)) };
}

/** The tile header's count: "5 open" on the overview, "3 of 5 open" on a story; nothing when there is nothing to check. */
export function openCount(open: number, total: number, ofTotal: boolean): string {
  if (!total) return "";
  if (!open) return `all ${total} looked at`;
  return ofTotal ? `${open} of ${total} open` : `${open} open`;
}

/** "A" … "Z", then the thread's id. */
export const letter = (i: number, id = "") => (i < 26 ? String.fromCharCode(65 + i) : id);

/** Checks by thread in reading order, then those with no thread under "Across the change" (§7.3); empty groups left out. */
export function byThread(r: Reading): { id: string | null; label: string; checks: Check[] }[] {
  const groups = r.threads.map((t, i) => ({ id: t.id as string | null, label: `${letter(i, t.id)} · ${t.name}`,
                                            checks: r.checks.filter((k) => k.thread === t.id) }));
  const known = new Set(r.threads.map((t) => t.id));
  groups.push({ id: null, label: "Across the change", checks: r.checks.filter((k) => !k.thread || !known.has(k.thread)) });
  return groups.filter((g) => g.checks.length);
}

/** "svc/flush.c:3 in `flush`". */
export function placeOf(k: Check): string {
  if (!k.path) return "";
  return `${k.path}${k.line ? `:${k.line}` : ""}${k.function ? ` in \`${k.function}\`` : ""}`;
}

/** "Looks fine · ana · 2h ago", or that the line changed since it was marked. */
export function markLine(m: Mark, now = Date.now()): string {
  return m.changed ? `Changed since marked by ${m.user}` : `Looks fine · ${m.user} · ${ago(m.at, now)}`;
}
```

`frontend/src/reading/types.ts` (new file):

```ts
/** How a review reads (spec 2026-10-07-review-reading §10.1): the backend's reading.py models as the browser gets them. */

export type CheckKind = "hazard" | "confirm" | "caller" | "result" | "reader" | "target" | "untested" | "unanalysed" | "ask"
  | "cleared";
export type ConnKind = "caller" | "vocabulary" | "condition" | "place" | "bundled";

export interface Thread {
  id: string; name: string; purpose: string; text_source: "template" | "llm";
  /** In reading order. */
  stories: string[]; cls: number[]; open_checks: number;
}
export interface Connection { a: string; b: string; kind: ConnKind; text: string; facts: string[]; shown: boolean }
export interface Reason { kind: CheckKind; text: string }
export interface Check {
  /** kind|file|function|related changed function: no line numbers, so a mark survives a re-run. */
  key: string; kind: CheckKind; story: string | null; thread: string | null;
  /** Workspace-relative; `depot` is the file the side panel opens. */
  path: string; depot: string | null; line: number | null; function: string | null; node: string | null;
  text: string; source_line: string; finding: string | null; cites: string[];
  /** Other kinds at the same place. */
  also: Reason[];
}
/** "Looks fine", shared by everyone viewing the review; `changed`: the line is no longer the one marked, so it is open. */
export interface Mark { key: string; user: string; at: string; source_line: string; changed: boolean }
export interface Headline { text: string; tone: "hazard" | "confirm" | "none"; rules_only: boolean }
export interface BuildImpact { header: string; text: string; files: number; finding: string | null; note: string }
export interface TestsRow { stories: string[]; functions: number; covers: string[]; untested: string[] }
export interface Reading {
  whole: string; whole_source: "template" | "llm"; threads: Thread[]; connections: Connection[];
  /** Story ids, tests last. */
  order: string[]; reasons: Record<string, string>; checks: Check[];
  /** Findings judged no hazard, with their reasons. */
  cleared: Check[]; build_impact: BuildImpact[]; coverage: string[]; headline: Headline; rules_only: boolean;
  tests: TestsRow | null; marks: Record<string, Mark>;
}

export interface ContractRow {
  kind: "signature" | "returns" | "fields" | "repeated" | "body"; text: string; node: string | null;
  before: string; after: string;
  /** [start, end) of the part of `after` that differs. */
  mark: number[]; added: string[]; removed: string[]; nodes: string[];
}
export interface WhereFn { node: string; label: string; add: number; rem: number; cl: number | null; line: number | null }
export interface WhereFile { path: string; depot: string | null; functions: WhereFn[] }
export interface CallPath {
  /** Node ids, entry first; `hidden` are the folded middle steps of a long path. */
  steps: string[]; labels: string[]; kind: "contract" | "state" | "call"; entry: string | null; hidden: string[];
  text: string; flow: string | null;
}
export interface StoryReading {
  story: string; contracts: ContractRow[]; where: WhereFile[]; paths: CallPath[]; checks: Check[];
  /** Its place in its thread: "Uses what story 1 adds." */
  place_text: string; thread: string | null; position: number | null;
}
```

`frontend/src/styles.css` (diff):

```diff
diff --git a/frontend/src/styles.css b/frontend/src/styles.css
index b1a266f..1e2ab79 100644
--- a/frontend/src/styles.css
+++ b/frontend/src/styles.css
@@ -147,6 +147,11 @@ button.go:disabled { opacity: .55; }
 .rv-risk { font: 700 10.5px var(--sans); padding: 2px 9px; border-radius: 99px; letter-spacing: .03em; }
 .rv-risk.high { background: #ff4d6d; color: #ffffff; } .rv-risk.medium { background: #ffcf66; color: #5a3a00; }
 .rv-risk.low { background: #b9f0cc; color: #13692f; }
+.ct-headline { font: 600 11px/1.6 var(--sans); padding: 1px 9px; border-radius: 99px; white-space: nowrap;
+  background: var(--gap-bg); color: var(--muted); }
+.ct-headline.hazard { background: color-mix(in srgb, var(--bad) 14%, var(--surface)); color: var(--bad); }
+.ct-headline.confirm { background: color-mix(in srgb, var(--warn) 10%, var(--surface)); color: var(--warn); }
+.ct-headline .ct-rules { font-weight: 400; }
 .rv-status { font-size: 11.5px; font-weight: 600; padding: 2px 9px; border-radius: 99px; color: var(--muted); background: var(--gap-bg); }
 .rv-status.done { color: var(--ok); } .rv-status.degraded { color: var(--warn); } .rv-status.failed { color: var(--bad); }
 .rv-status.running, .rv-status.queued { color: var(--accent); }
```

`frontend/src/workspace/Workspace.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index ae63a60..b01e9fc 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -4,6 +4,7 @@ import { api } from "../api";
 import { useMe } from "../App";
 import { driftSummary } from "../board/drift";
 import AiPill from "../components/AiPill";
+import HeadlinePill from "../components/HeadlinePill";
 import { useSources } from "../board/useSources";
 import Stages from "../components/Stages";
 import { AiProvider, useAi } from "../lib/ai";
@@ -123,7 +124,8 @@ function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
       <button className="ws-menu" aria-label="Review contents" aria-expanded={drawer} title="Show the review's contents"
               onClick={onMenu}>☰</button>
       <h1><Link to={ws.base} state={{ page: true }} title="Go to the whole change">{r.title}</Link></h1>
-      {r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
+      {d.reading ? <HeadlinePill h={d.reading.headline} />
+        : r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
       {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
       {d.ready && <AiPill />}
       {me?.is_owner && d.ready && <button className="link rerun" onClick={() => api.rerun(d.id).then(d.loadDetail)}>Re-run</button>}
```

`frontend/src/workspace/useReview.ts` (diff):

```diff
diff --git a/frontend/src/workspace/useReview.ts b/frontend/src/workspace/useReview.ts
index 3a1c4ad..4f9bc0c 100644
--- a/frontend/src/workspace/useReview.ts
+++ b/frontend/src/workspace/useReview.ts
@@ -2,7 +2,7 @@
  * progress events and AI state, moved into a hook). */
 import { useCallback, useEffect, useMemo, useRef, useState } from "react";
 import { api, ApiError, type AiJob, type Board, type Comment, type FileChange, type Finding, type Names, type Overview,
-  type ReviewDetail, type StoryDetail, type StorySet } from "../api";
+  type Reading, type ReviewDetail, type StoryDetail, type StorySet } from "../api";
 import { useAiState } from "../lib/ai";
 
 const TERMINAL = new Set(["done", "degraded", "failed"]);
@@ -20,6 +20,7 @@ export function useReview(id: number) {
   const [files, setFiles] = useState<FileChange[]>([]);
   const [comments, setComments] = useState<Comment[]>([]);
   const [names, setNames] = useState<Names>({});
+  const [reading, setReading] = useState<Reading | null | undefined>(undefined);   // null: run before the reading existed
   const [reload, setReload] = useState(0);                // story pages and cluster graphs fetch again: new results, AI text
   const [error, setError] = useState<string | null>(null);
 
@@ -29,12 +30,13 @@ export function useReview(id: number) {
   const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
   const loadStories = useCallback(() => api.stories(id).then(setStories, (e) => setStories(missing(null)(e))), [id]);
   const loadNames = useCallback(() => api.names(id).then(setNames).catch(() => { /* names fall back to "a function" */ }), [id]);
+  const loadReading = useCallback(() => api.reading(id).then(setReading, (e) => setReading(missing(null)(e))), [id]);
   const loadBoard = useCallback(() => api.board(id).then(setBoard, (e) => setBoard(missing(null)(e))), [id]);
   const loadResults = useCallback(() => (setReload((k) => k + 1), Promise.all([
     api.overview(id).then((ov) => { setOverview(ov); setBoard(null); },
                           (e) => { setOverview(missing(null)(e)); return loadBoard(); }),
-    loadStories(), loadFindings(), api.files(id).then(setFiles), loadComments(), loadNames(),
-  ]).catch(fail)), [id, loadBoard, loadStories, loadFindings, loadComments, loadNames, fail]);
+    loadStories(), loadFindings(), api.files(id).then(setFiles), loadComments(), loadNames(), loadReading(),
+  ]).catch(fail)), [id, loadBoard, loadStories, loadFindings, loadComments, loadNames, loadReading, fail]);
 
   useEffect(() => { loadDetail(); }, [loadDetail]);
   const status = detail?.review.status;
@@ -77,10 +79,10 @@ export function useReview(id: number) {
   const ai = useAiState(id, ready, people, comments.some((c) => c.ai_meta?.pending), onAiDone, loadComments);
   const about = (board ?? overview)?.about ?? null;
 
-  return useMemo(() => ({ id, detail, board, overview, stories, findings, files, comments, names, about, reload, error, ready,
-                         ai, story, loadDetail, loadComments, loadFindings }),
-                 [id, detail, board, overview, stories, findings, files, comments, names, about, reload, error, ready, ai, story,
-                  loadDetail, loadComments, loadFindings]);
+  return useMemo(() => ({ id, detail, board, overview, stories, findings, files, comments, names, reading, about, reload, error,
+                         ready, ai, story, loadDetail, loadComments, loadFindings, loadReading }),
+                 [id, detail, board, overview, stories, findings, files, comments, names, reading, about, reload, error, ready, ai,
+                  story, loadDetail, loadComments, loadFindings, loadReading]);
 }
 
 export type ReviewData = ReturnType<typeof useReview>;
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_reading.py -q`
Expected: PASS: `47 passed`

Run: `cd frontend && npx vitest run src/reading/checks.test.ts`
Expected: PASS: `Tests 8 passed (8)`

Run: `cd frontend && npm run build && npx playwright test e2e/landing.spec.ts e2e/theme.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace.spec.ts`
Expected: PASS: `27 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `606 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 148 passed (148)`; Playwright `93 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_reading.py frontend/e2e/landing.spec.ts frontend/e2e/theme.spec.ts frontend/e2e/workspace-tier1.spec.ts frontend/e2e/workspace.spec.ts frontend/src/reading/checks.test.ts backend/codetortoise/reading.py frontend/src/api.ts frontend/src/board/types.ts frontend/src/components/HeadlinePill.tsx frontend/src/pages/Reviews.tsx frontend/src/reading/checks.ts frontend/src/reading/types.ts frontend/src/styles.css frontend/src/workspace/Workspace.tsx frontend/src/workspace/useReview.ts
git commit -m "feat(ui): the reading reaches the browser; the header and the Reviews list say what to act on; checks name the file Open shows"
```

### Task 10: The overview

Spec §5, §7.2, §11 (phone). With a reading, the whole-change page becomes the overview in layout B. Left: the change as a whole; how the threads connect (thread boxes down the left, an SVG arc for each shown pair with its text, dashed for "only bundled — ask the author", pointing at an arc lights both threads; one thread: a sentence instead); the threads (letter, name, CLs, open count, purpose, stories in reading order with their reasons) and the Tests line; the map (until Task 12); the discussion. Right, pinned: To check grouped by thread (each row: tags, place, source line, mark line, Looks fine/Reopen, Comment with its thread, Open), build impact, coverage. On a phone To check comes first, folded to its count, and the arcs become one sentence per connection. A review without a reading keeps the old page.

**Files:**
- Test: `frontend/e2e/workspace-detail.spec.ts`
- Test: `frontend/e2e/workspace-reading.spec.ts`
- Test: `frontend/e2e/workspace.spec.ts`
- Test: `frontend/src/reading/overview.test.ts`
- Create: `frontend/src/reading/overview.ts`
- Create: `frontend/src/workspace/CheckList.tsx`
- Create: `frontend/src/workspace/Overview.tsx`
- Modify: `frontend/src/workspace/WholePage.tsx`
- Modify: `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: Task 9's types, `checks.ts`, `api.markCheck`/`unmarkCheck`, `Comments` with kind `check`.
- Produces: `reading/overview.ts`: `STEP`, `Arc`, `arcLayout(threads, conns, row = 56) -> { arcs, height, reach }`, `connectionRows(threads, conns)`, `listed(xs)`, `testsLine(...)`;
  `workspace/CheckList.tsx`: `CheckGroup`, default `CheckTile({ groups, ofTotal, footer, lit })`; `workspace/Overview.tsx`; `WholePage.tsx`'s exported `MapSection` and `Discussion`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/workspace-detail.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-detail.spec.ts b/frontend/e2e/workspace-detail.spec.ts
index 8258c75..897cb19 100644
--- a/frontend/e2e/workspace-detail.spec.ts
+++ b/frontend/e2e/workspace-detail.spec.ts
@@ -149,10 +149,10 @@ test.describe("desktop", () => {
     await expect(panel.locator(".ws-file")).toHaveCount(0);
   });
 
-  test("a side effect on the whole change opens its file at a folded line, shown", async ({ page }) => {
+  test("a To check row opens its file at its line, folded away or not", async ({ page }) => {
     await startReview(page);
     await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).click();
-    await page.getByRole("link", { name: "Open uart_init at line 8" }).click();       // line 8: outside the hunks
+    await page.getByRole("region", { name: "To check" }).getByRole("link", { name: "Open driver/uart.c at line 8" }).click();   // outside the hunks
     await expect(page.getByRole("complementary", { name: "Code: uart.c" }).locator('.focus[data-n="8"]')).toBeVisible();
   });
 
```

`frontend/e2e/workspace-reading.spec.ts` (new file):

```ts
import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

/** A review read as threads (spec 2026-10-07-review-reading §5, §7, §13): fixture CLs 101–104 make three threads, the
 * first two joined by a shared caller, the third only by arriving in CL 104. */
const FOUR = "101 102 103 104";

/** Re-run the review and wait until the new run's reading is stored. */
async function rerun(page: Page, base: string) {
  const id = base.split("/")[2];
  const finished = async () => {
    const d = await (await page.request.get(`/api/reviews/${id}`)).json();
    return { status: d.review.status as string, at: d.stages.find((s: { name: string }) => s.name === "reading")?.finished_at as string };
  };
  const before = (await finished()).at;
  expect((await page.request.post(`/api/reviews/${id}/rerun`)).ok()).toBe(true);
  await expect.poll(async () => { const f = await finished(); return f.at !== before && ["done", "degraded"].includes(f.status); },
                    { timeout: 60_000 }).toBe(true);
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the overview tells the change as threads, how they connect and what to check", async ({ page }) => {
    await startReview(page, FOUR);
    const left = page.locator(".ov2-left");
    await expect(left.locator("h2")).toHaveText(["The change as a whole", "How the threads connect", "Threads", /^The map/, "Discussion"]);
    await expect(left.locator(".ws-lead")).toHaveText("3 threads: A and B: both run inside main; B and C: nothing besides arriving in CL 104.");
    const conn = page.locator(".ov-conn");
    await expect(conn.locator(".ov-box")).toHaveCount(3);
    await expect(conn.locator(".ov-arc")).toHaveCount(2);
    await expect(conn.locator(".ov-arc.dashed")).toHaveCount(1);                        // only bundled: dashed, ask the author
    await expect(conn.locator(".ov-arc-label")).toHaveText(["both run inside main", "nothing besides arriving in CL 104 — ask the author"]);
    await conn.locator(".ov-arc-label").first().hover();                                 // pointing at an arc lights both threads
    await expect(conn.locator(".ov-box.hot")).toHaveCount(2);
    await expect(conn.locator(".ov-box").nth(2)).not.toHaveClass(/\bhot\b/);
    const threads = left.locator(".ov-thread");
    await expect(threads.locator("h3")).toHaveText(["hal_write in hal", "logger_init in service", "svc::Engine::step in cpp"]);
    await expect(threads.first().locator(".ov-reason")).toHaveText(["← calls 1"]);
    const check = page.getByRole("region", { name: "To check" });
    await expect(check.locator("h3 .ck-count")).toHaveText("6 open");
    await expect(check.locator(".ck-group h4")).toHaveText(["A · hal_write in hal", "C · svc::Engine::step in cpp"]);
    await expect(check.locator(".ck-row > .ck-top .ck-tag")).toHaveText(["Confirm", "Confirm", "Caller not updated",
                                                                         "Result handled the old way", "Unchanged reader", "Ask the author"]);
    await expect(check).toContainText("Risks judged by rules only.");
    await expect(page.getByRole("region", { name: "Build impact" })).toContainText("include/hal/regs.h declaration change → 4 files rebuild");
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("No test code found in the workspace");
    await expectNoNodeIds(page);
    await expectNamed(page);
    await threads.first().getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(/\/s\/S1$/);
  });

  test("Looks fine marks a check for everyone, greys it below the open ones and survives a re-run", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const check = page.getByRole("region", { name: "To check" });
    const row = check.locator(".ck-row", { hasText: "uart_init calls hal_write" });
    await row.getByRole("button", { name: "Looks fine" }).click();
    await expect(row).toHaveClass(/\bmarked\b/);
    await expect(row.locator(".ck-mark")).toHaveText("Looks fine · demo · just now");
    await expect(check.locator("h3 .ck-count")).toHaveText("5 open");
    await expect(check.locator(".ck-group").first().locator(".ck-row").last()).toHaveClass(/\bmarked\b/);   // below the open rows
    await rerun(page, base);
    await page.reload();
    await expect(check.locator(".ck-row", { hasText: "uart_init calls hal_write" })).toHaveClass(/\bmarked\b/);
    await expect(check.locator("h3 .ck-count")).toHaveText("5 open");
    await check.locator(".ck-row", { hasText: "uart_init calls hal_write" }).getByRole("button", { name: "Reopen" }).click();
    await expect(check.locator("h3 .ck-count")).toHaveText("6 open");
  });

  test("a check takes a comment thread of its own", async ({ page }) => {
    await startReview(page, FOUR);
    const row = page.getByRole("region", { name: "To check" }).locator(".ck-row", { hasText: "logger_flush ignores the result" });
    await row.getByRole("button", { name: "Comment" }).click();
    await row.getByPlaceholder("Leave a comment…").fill("flush should retry");
    await row.locator(".comments").getByRole("button", { name: "Comment" }).click();
    await expect(row.locator(".comments")).toContainText("flush should retry");
    await expect(row.getByRole("button", { name: "Comment (1)" })).toBeVisible();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("To check comes first, folded to its count, and the connections are sentences", async ({ page }) => {
    await startReview(page, FOUR);
    await page.getByRole("link", { name: "Go to the whole change" }).click();
    const check = page.locator("details.ck-tile");
    await expect(check).not.toHaveAttribute("open");
    await expect(check.locator("summary .ck-count")).toHaveText("6 open");
    const tile = (await check.boundingBox())!, whole = (await page.getByRole("heading", { name: "The change as a whole" }).boundingBox())!;
    expect(tile.y).toBeLessThan(whole.y);
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
    await check.locator("summary").click();
    await expect(check.locator(".ck-row")).toHaveCount(6);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
```

`frontend/e2e/workspace.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index 8c59628..4d399fe 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -38,17 +38,13 @@ test.describe("desktop", () => {
     await expectNamed(page);
   });
 
-  test("the whole change: what it is for, why it is risky, then the rest", async ({ page }) => {
-    const base = await startReview(page);
-    const page_ = page.locator(".ws-whole");
-    await expect(page_.locator("h2")).toHaveText(["What this change is trying to do", "Why it is high risk",
-                                                  /^The map/, "Files with side effects", "Discussion"]);
-    await expect(page_.locator(".ws-summary")).toContainText("2 behaviour stories.");
-    await page_.getByRole("link", { name: /^Go to finding F1:/ }).click();
-    await expect(page).toHaveURL(new RegExp(`${base}/f/F1$`));
-    await page.goBack();
-    await page_.locator(".ws-fx").getByRole("link", { name: /^Open uart_errors at line/ }).click();
-    await expect(page).toHaveURL(/\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c%3A\d+$/);
+  test("the overview: the change as a whole, its one thread and what to check", async ({ page }) => {
+    await startReview(page);
+    const left = page.locator(".ov2-left");
+    await expect(left.locator("h2")).toHaveText(["The change as a whole", "How the threads connect", "Threads", /^The map/, "Discussion"]);
+    await expect(left.locator(".ws-lead")).toHaveText("One thread: hal_write in hal.");
+    await expect(left).toContainText("One thread: all stories are connected by calls or shared data.");
+    await expect(page.getByRole("region", { name: "To check" }).locator(".ck-row")).toHaveCount(5);
     await expectNoNodeIds(page);
     await expectNamed(page);
   });
```

`frontend/src/reading/overview.test.ts` (new file):

```ts
import { describe, expect, it } from "vitest";
import { arcLayout, connectionRows, testsLine } from "./overview";
import type { Connection, TestsRow, Thread } from "./types";

const thread = (id: string, name = id): Thread => ({ id, name, purpose: "", text_source: "template", stories: [], cls: [], open_checks: 0 });
const conn = (a: string, b: string, kind: Connection["kind"] = "caller", shown = true, text = `${a}–${b}`): Connection =>
  ({ a, b, kind, text, facts: [], shown });
const T = ["T1", "T2", "T3", "T4"].map((id) => thread(id));

describe("how the threads connect", () => {
  it("draws only the shown connections, each from one thread box to the other", () => {
    const { arcs, height } = arcLayout(T, [conn("T1", "T2"), conn("T1", "T3", "place", false)], 60);
    expect(arcs.map((a) => [a.a, a.b, a.y1, a.y2])).toEqual([["T1", "T2", 30, 90]]);
    expect(height).toBe(240);
  });

  it("nests an arc around the arcs it spans, and arcs that only touch share a depth", () => {
    const { arcs, reach } = arcLayout(T, [conn("T1", "T3"), conn("T1", "T2"), conn("T2", "T3")], 60);
    const depth = Object.fromEntries(arcs.map((a) => [`${a.a}${a.b}`, a.depth]));
    expect(depth).toEqual({ T1T2: 1, T2T3: 1, T1T3: 2 });
    expect(reach).toBe(2 * 28);
    const outer = arcs.find((a) => a.depth === 2)!;
    expect(outer.d).toBe("M 0 30 C 56 30, 56 150, 0 150");
  });

  it("dashes the arc of threads joined only by their bundle", () => {
    const { arcs } = arcLayout(T, [conn("T2", "T4", "bundled")], 60);
    expect(arcs[0].dashed).toBe(true);
  });

  it("keeps the labels apart when two arcs meet at the same height", () => {
    const { arcs } = arcLayout(T, [conn("T1", "T4"), conn("T2", "T3")], 60);
    expect(arcs.map((a) => (a.y1 + a.y2) / 2)).toEqual([120, 120]);
    const ys = arcs.map((a) => a.labelY).sort((x, y) => x - y);
    expect(ys[1] - ys[0]).toBeGreaterThanOrEqual(20);
  });

  it("says each shown connection as a sentence row, for phones", () => {
    const rows = connectionRows(T, [conn("T1", "T2", "caller", true, "both run inside `main`"),
                                    conn("T2", "T4", "bundled", true, "nothing besides arriving in CL 104"),
                                    conn("T1", "T3", "place", false)]);
    expect(rows).toEqual([{ text: "A and B: both run inside `main`", bundled: false },
                          { text: "B and D: nothing besides arriving in CL 104 — ask the author", bundled: true }]);
  });
});

describe("the Tests row", () => {
  const tests = (covers: string[], untested: string[]): TestsRow => ({ stories: ["S9"], functions: 6, covers, untested });
  it("says which threads the tests cover and which nothing tests", () => {
    expect(testsLine(tests(["T1", "T2"], ["T3"]), T)).toBe("Tests: 6 cover threads A and B · nothing tests C");
    expect(testsLine(tests(["T1"], []), T)).toBe("Tests: 6 cover thread A");
    expect(testsLine(tests([], ["T1", "T2", "T3"]), T)).toBe("Tests: 6 · nothing tests A, B and C");
  });
});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd frontend && npx vitest run src/reading/overview.test.ts`
Expected: FAIL: `Tests no tests`; the first error is `Error: Cannot find module './overview' imported from frontend/src/reading/overview.test.ts`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-detail.spec.ts e2e/workspace-reading.spec.ts e2e/workspace.spec.ts`
Expected: FAIL: `npm run build fails with 8 type error(s)`; the first error is `src/reading/overview.test.ts(2,54): error TS2307: Cannot find module './overview' or its corresponding type declarations.`

- [ ] **Step 3: Implement**

`frontend/src/reading/overview.ts` (new file):

```ts
/** The overview's connections tile and Tests row (spec 2026-10-07-review-reading §5.1). */
import { letter } from "./checks";
import type { Connection, ConnKind, TestsRow, Thread } from "./types";

export const STEP = 28;               // how much further right each level of nesting reaches
const GAP = 20;                       // the least room between two arc labels

export interface Arc {
  a: string; b: string; kind: ConnKind; text: string; dashed: boolean;
  /** 1 for an arc spanning no other; an arc around others sits one level outside them. */
  depth: number; y1: number; y2: number;
  /** The SVG path, from the right edge of one thread's box (x 0) to the other's. */
  d: string; labelY: number;
}

/** Each shown connection as an arc between the thread boxes stacked `row` px apart, nested so arcs never cross a
 * label, with its label at its middle height pushed down clear of the label above. */
export function arcLayout(threads: Thread[], conns: Connection[], row = 56): { arcs: Arc[]; height: number; reach: number } {
  const at = new Map(threads.map((t, i) => [t.id, i]));
  const spans = conns.filter((k) => k.shown && k.a !== k.b && at.has(k.a) && at.has(k.b))
    .map((k) => ({ k, lo: Math.min(at.get(k.a)!, at.get(k.b)!), hi: Math.max(at.get(k.a)!, at.get(k.b)!) }))
    .sort((x, y) => x.hi - x.lo - (y.hi - y.lo) || x.lo - y.lo);
  const placed: { lo: number; hi: number; depth: number }[] = [];
  const arcs = spans.map(({ k, lo, hi }) => {
    const depth = 1 + Math.max(0, ...placed.filter((p) => p.lo < hi && lo < p.hi).map((p) => p.depth));
    placed.push({ lo, hi, depth });
    const y1 = lo * row + row / 2, y2 = hi * row + row / 2, r = depth * STEP;
    return { a: k.a, b: k.b, kind: k.kind, text: k.text, dashed: k.kind === "bundled", depth, y1, y2,
             d: `M 0 ${y1} C ${r} ${y1}, ${r} ${y2}, 0 ${y2}`, labelY: (y1 + y2) / 2 };
  });
  let last = -Infinity;
  for (const arc of [...arcs].sort((x, y) => x.labelY - y.labelY)) {
    arc.labelY = Math.max(arc.labelY, last + GAP);
    last = arc.labelY;
  }
  return { arcs, height: Math.max(threads.length * row, last + row / 2), reach: Math.max(0, ...arcs.map((a) => a.depth)) * STEP };
}

/** "A and B: both run inside `main`", one per shown connection: the tile on a phone, where arcs do not fit. */
export function connectionRows(threads: Thread[], conns: Connection[]): { text: string; bundled: boolean }[] {
  const name = new Map(threads.map((t, i) => [t.id, letter(i, t.id)]));
  return conns.filter((k) => k.shown && name.has(k.a) && name.has(k.b)).map((k) => ({
    text: `${name.get(k.a)} and ${name.get(k.b)}: ${k.text}${k.kind === "bundled" ? " — ask the author" : ""}`,
    bundled: k.kind === "bundled",
  }));
}

/** "A", "A and B", "A, B and C". */
export function listed(xs: string[]): string {
  return xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
}

/** "Tests: 6 cover threads A and B · nothing tests C". */
export function testsLine(t: TestsRow, threads: Thread[]): string {
  const name = new Map(threads.map((th, i) => [th.id, letter(i, th.id)]));
  const of = (ids: string[]) => listed(ids.map((id) => name.get(id) ?? id));
  return `Tests: ${t.functions}${t.covers.length ? ` cover thread${t.covers.length === 1 ? "" : "s"} ${of(t.covers)}` : ""}`
    + (t.untested.length ? ` · nothing tests ${of(t.untested)}` : "");
}
```

`frontend/src/workspace/CheckList.tsx` (new file):

```tsx
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Comments from "../components/Comments";
import { isOpen, KIND_LABEL, markLine, openCount, placeOf, splitChecks } from "../reading/checks";
import type { Check } from "../reading/types";
import { useWs } from "./context";
import { Ticks } from "./NameText";

/** One To check row (spec 2026-10-07-review-reading §7.2): kind, one line, the place and its source line; Looks fine,
 * Comment and Open. A row someone marked shows who and when, greyed; a changed line reopens it. */
function CheckRow({ k, lit }: { k: Check; lit: boolean }) {
  const ws = useWs(), d = ws.data, m = d.reading?.marks[k.key];
  const [talk, setTalk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const marked = !!m && !m.changed;
  const toggle = () => {
    setBusy(true);
    setError(null);
    (marked ? api.unmarkCheck(d.id, k.key) : api.markCheck(d.id, k.key)).then(d.loadReading)
      .catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
  };
  const talks = d.comments.filter((c) => c.parent_id === null && c.anchor_kind === "check" && c.anchor.key === k.key).length;
  const where = placeOf(k), at = `${k.path}${k.line ? ` at line ${k.line}` : ""}`;
  return (
    <li className={`ck-row${marked ? " marked" : ""}${lit ? " lit" : ""}`} data-key={k.key} data-finding={k.finding ?? undefined}>
      {[{ kind: k.kind, text: k.text }, ...k.also].map((r, i) => (
        <div key={i} className="ck-top"><span className={`ck-tag ${r.kind}`}>{KIND_LABEL[r.kind]}</span>
          <span className="ck-text"><Ticks text={r.text} /></span></div>
      ))}
      {where && <div className="ck-place mono"><Ticks text={where} /></div>}
      {k.source_line && <code className="ck-src">{k.source_line}</code>}
      {m && <div className={`ck-mark${m.changed ? " changed" : ""}`}>{markLine(m)}</div>}
      <div className="ck-acts">
        <button className="link" onClick={toggle} disabled={busy} aria-pressed={marked}>{marked ? "Reopen" : "Looks fine"}</button>
        <button className="link" onClick={() => setTalk(!talk)} aria-expanded={talk}>Comment{talks ? ` (${talks})` : ""}</button>
        {k.depot && <Link to={ws.link(ws.opened({ file: k.depot, line: k.line }))} title={`Open ${at}`} aria-label={`Open ${at}`}>Open</Link>}
      </div>
      {error && <div className="banner warn">{error}</div>}
      {talk && <Comments reviewId={d.id} comments={d.comments} kind="check" anchor={{ key: k.key }} onChange={d.loadComments} autoFocus />}
    </li>
  );
}

export interface CheckGroup { label: string | null; checks: Check[] }

/** A To check tile: open rows first, marked ones below; the overview's grouped by thread with "5 open" (§5.2), a story's
 * with "3 of 5 open" (§6.2). On a phone it comes first, folded to its count. `lit` highlights the rows of a finding. */
export default function CheckTile({ groups, ofTotal, footer, lit = null }:
  { groups: CheckGroup[]; ofTotal: boolean; footer?: ReactNode; lit?: string | null }) {
  const ws = useWs(), marks = ws.data.reading?.marks ?? {};
  const all = groups.flatMap((g) => g.checks);
  const count = openCount(all.filter((k) => isOpen(k, marks)).length, all.length, ofTotal);
  const head = <>To check{count && <span className="ck-count">{count}</span>}</>;
  const body = <>
    {all.length === 0 && <p className="muted small">Nothing to check.</p>}
    {groups.map((g) => {
      const { open, marked } = splitChecks(g.checks, marks);
      return (
        <div key={g.label ?? ""} className="ck-group">
          {g.label && <h4><Ticks text={g.label} /></h4>}
          <ul className="ck-list">{[...open, ...marked].map((k) => <CheckRow key={k.key} k={k} lit={!!lit && k.finding === lit} />)}</ul>
        </div>
      );
    })}
    {footer}
  </>;
  return ws.screen === "phone"
    ? <details className="ws-tile ck-tile" aria-label="To check"><summary><h3>{head}</h3></summary>{body}</details>
    : <section className="ws-tile ck-tile" aria-label="To check"><h3>{head}</h3>{body}</section>;
}
```

`frontend/src/workspace/Overview.tsx` (new file):

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { byThread, letter, placeOf } from "../reading/checks";
import { arcLayout, connectionRows, testsLine } from "../reading/overview";
import type { Reading, Thread } from "../reading/types";
import CheckTile from "./CheckList";
import { useWs } from "./context";
import { short } from "./crumbs";
import { Ticks } from "./NameText";
import { Discussion, MapSection } from "./WholePage";

const ROW = 56;                       // one thread box and the room around it in the connections tile

/** How the threads connect (spec 2026-10-07-review-reading §5.1): the threads stacked as boxes, an arc for each shown
 * connection with its text beside it, dashed for threads joined only by their bundle; pointing at an arc lights both
 * threads. One thread says so instead; a phone gets one sentence per connection. */
function Connections({ r }: { r: Reading }) {
  const ws = useWs();
  const [hot, setHot] = useState<[string, string] | null>(null);
  if (!r.threads.length) return null;
  const head = <h2 id="ov-conn">How the threads connect</h2>;
  if (r.threads.length === 1)
    return <section aria-labelledby="ov-conn">{head}<p className="muted">One thread: all stories are connected by calls or shared data.</p></section>;
  if (ws.screen === "phone")
    return (
      <section aria-labelledby="ov-conn">{head}
        <ul className="ov-conn-rows">{connectionRows(r.threads, r.connections).map((row) => (
          <li key={row.text} className={row.bundled ? "bundled" : ""}><Ticks text={row.text} /></li>
        ))}</ul>
      </section>
    );
  const { arcs, height, reach } = arcLayout(r.threads, r.connections, ROW);
  const lit = (a: { a: string; b: string }) => !!hot && hot[0] === a.a && hot[1] === a.b;
  return (
    <section aria-labelledby="ov-conn">{head}
      <div className="ov-conn" style={{ height, ["--reach" as string]: `${reach}px` }}>
        {r.threads.map((t, i) => (
          <button key={t.id} className={`ov-box${hot?.includes(t.id) ? " hot" : ""}`} style={{ top: i * ROW + 6, height: ROW - 12 }}
                  onClick={() => document.getElementById(`thread-${t.id}`)?.scrollIntoView({ block: "start" })}
                  aria-label={`Go to thread ${letter(i, t.id)}: ${short(t.name.replaceAll("`", ""))}`}>
            <span className="ov-letter">{letter(i, t.id)}</span>
            <span className="ov-box-name"><Ticks text={t.name} /></span>
            {t.open_checks > 0 && <span className="ck-count">{t.open_checks}</span>}
          </button>
        ))}
        <svg className="ov-arcs" width={reach + 4} height={height} aria-hidden>
          {arcs.map((a) => (
            <path key={`${a.a}-${a.b}`} d={a.d} className={`ov-arc${a.dashed ? " dashed" : ""}${lit(a) ? " hot" : ""}`}
                  onMouseEnter={() => setHot([a.a, a.b])} onMouseLeave={() => setHot(null)} />
          ))}
        </svg>
        {arcs.map((a) => (
          <div key={`${a.a}-${a.b}`} className={`ov-arc-label${a.dashed ? " dashed" : ""}${lit(a) ? " hot" : ""}`} style={{ top: a.labelY }}
               onMouseEnter={() => setHot([a.a, a.b])} onMouseLeave={() => setHot(null)}>
            <Ticks text={a.text} />{a.dashed && <span className="ov-ask"> — ask the author</span>}
          </div>
        ))}
      </div>
    </section>
  );
}

/** A thread: name, CLs, open checks and purpose, then its stories in reading order with why each follows (§5.1). */
function ThreadCard({ t, i, r }: { t: Thread; i: number; r: Reading }) {
  const ws = useWs(), ss = ws.data.stories;
  return (
    <article className="ov-thread" id={`thread-${t.id}`} aria-label={`Thread ${letter(i, t.id)}`}>
      <header>
        <span className="ov-letter">{letter(i, t.id)}</span>
        <h3>{t.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={t.name} /></h3>
        {t.cls.map((c) => (
          <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
        ))}
        {t.open_checks > 0 && <span className="ck-count">{t.open_checks} open</span>}
      </header>
      {t.purpose && <p className="ov-purpose"><Ticks text={t.purpose} /></p>}
      <ol className="ov-stories">{t.stories.map((sid) => {
        const st = ss?.stories.find((s) => s.id === sid);
        const label = `Go to story ${sid}${st ? `: ${short(st.title)}` : ""}`;
        return (
          <li key={sid}>
            <Link to={ws.link(ws.item({ kind: "story", sid, view: "steps" }))} title={label} aria-label={label}>
              <Ticks text={st?.title ?? sid} /></Link>
            {r.reasons[sid] && <span className="ov-reason">{r.reasons[sid]}</span>}
          </li>
        );
      })}</ol>
    </article>
  );
}

/** The overview in layout B (spec 2026-10-07-review-reading §5): the change as a whole, how its threads connect and the
 * threads on the left; To check, Build impact and Coverage pinned on the right. */
export default function Overview({ r }: { r: Reading }) {
  const ws = useWs(), ss = ws.data.stories;
  const tests = r.tests?.stories[0], testsStory = tests ? ss?.stories.find((s) => s.id === tests) : null;
  return (
    <div className="ws-page"><div className="ov2">
      <div className="ov2-left ws-whole">
        <section aria-labelledby="ov-whole">
          <h2 id="ov-whole">The change as a whole</h2>
          <p className="ws-lead">{r.whole_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={r.whole} /></p>
        </section>
        <Connections r={r} />
        {r.threads.length > 0 && (
          <section aria-labelledby="ov-threads">
            <h2 id="ov-threads">Threads</h2>
            {r.threads.map((t, i) => <ThreadCard key={t.id} t={t} i={i} r={r} />)}
            {r.tests && (
              <p className="ov-tests">{testsStory
                ? <Link to={ws.link(ws.item({ kind: "story", sid: testsStory.id, view: "steps" }))}
                        title={`Go to story ${testsStory.id}: ${short(testsStory.title)}`}>{testsLine(r.tests, r.threads)}</Link>
                : testsLine(r.tests, r.threads)}</p>
            )}
          </section>
        )}
        <MapSection />
        <Discussion />
      </div>
      <aside className="ov2-right" aria-label="What to check">
        <CheckTile groups={byThread(r)} ofTotal={false} footer={<>
          {r.rules_only && <p className="muted small">Risks judged by rules only.</p>}
          {r.cleared.length > 0 && (
            <details className="ck-cleared">
              <summary>{r.cleared.length} check{r.cleared.length === 1 ? "" : "s"} found no hazard</summary>
              <ul>{r.cleared.map((k) => (
                <li key={k.key}><Ticks text={k.text} />{placeOf(k) && <span className="mono small"> · <Ticks text={placeOf(k)} /></span>}</li>
              ))}</ul>
            </details>
          )}
        </>} />
        {r.build_impact.length > 0 && (
          <section className="ws-tile" aria-label="Build impact">
            <h3>Build impact</h3>
            <ul className="ov-lines">{r.build_impact.map((b) => (
              <li key={b.header}><Ticks text={b.text} />{b.note && <span className="muted"> {b.note}</span>}</li>
            ))}</ul>
          </section>
        )}
        {r.coverage.length > 0 && (
          <section className="ws-tile" aria-label="Coverage">
            <h3>Coverage</h3>
            <ul className="ov-lines">{r.coverage.map((c) => <li key={c}><Ticks text={c} /></li>)}</ul>
          </section>
        )}
      </aside>
    </div></div>
  );
}
```

`frontend/src/workspace/WholePage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/WholePage.tsx b/frontend/src/workspace/WholePage.tsx
index 407b52b..fd29eae 100644
--- a/frontend/src/workspace/WholePage.tsx
+++ b/frontend/src/workspace/WholePage.tsx
@@ -9,6 +9,7 @@ import { useWs } from "./context";
 import { pickFlow } from "./flows";
 import GraphView from "./graph/GraphView";
 import NameText from "./NameText";
+import Overview from "./Overview";
 
 /** A review shown as one board: its graph, on the whole change page or filling the centre (`?view=graph`). */
 export function ReviewGraph({ board, embedded }: { board: Board; embedded?: boolean }) {
@@ -18,13 +19,79 @@ export function ReviewGraph({ board, embedded }: { board: Board; embedded?: bool
                     onFlow={(i) => ws.go({ ...ws.addr, flow: i + 1 }, true)} embedded={embedded} storyOf={ws.data.stories?.node_story} />;
 }
 
-/** The review's home (spec 2026-10-04-review-workspace §3.1): what the change is for and why it is risky first. */
+/** The review's home: the reading's overview (spec 2026-10-07-review-reading §5); a review run before the reading
+ * existed keeps the page it had. */
 export default function WholePage() {
+  const r = useWs().data.reading;
+  if (r) return <Overview r={r} />;
+  if (r === undefined) return <div className="ws-page"><p className="muted">Loading…</p></div>;
+  return <OldWhole />;
+}
+
+const layerOf = (d: ReturnType<typeof useWs>["data"]) => (level: number | null) =>
+  (d.board?.layers ?? d.overview?.layers ?? []).find((l) => l.level === level)?.name;
+
+/** The review's parts by layer, or its one graph (spec 2026-10-04-review-workspace §3.1). */
+export function MapSection() {
+  const ws = useWs(), d = ws.data, ov = d.overview, layerName = layerOf(d);
+  return <>
+    {ov && (
+      <section aria-labelledby="ws-map" id="map">
+        <h2 id="ws-map">The map</h2>
+        <p className="muted">This change is split into {ov.totals.clusters} parts of connected code, riskiest first.
+          {ov.merged_over_limit > 0 && ` ${ov.merged_over_limit} small parts were merged to keep the list short.`}</p>
+        {bandsOf(ov).map((b) => (
+          <section key={b.level} className={`ov-band lv${b.level < 0 ? "x" : b.level % 4}`} aria-label={`Layer ${b.name}`}>
+            <h3>{b.name}</h3>
+            <div className="ov-blocks">{b.clusters.map((c) => (
+              <Link key={c.id} to={ws.link(ws.item({ kind: "cluster", cid: c.id }))} className={`ov-block ${c.risk ?? "none"}`}
+                    title={`Open ${c.name}`} aria-label={`Open ${c.name}`}>
+                <div className="nm">{c.name} {c.risk && <span className={`sev ${c.risk}`}>{c.risk.toUpperCase()}</span>}</div>
+                <div className="ct">{c.files.length} files · {c.changed} changed · {c.flows} flows
+                  {c.findings > 0 && ` · ${c.findings} finding${c.findings === 1 ? "" : "s"}`}</div>
+                {linkLines(ov, c.id, 3).map((l) => <div key={l} className="ln">{l}</div>)}
+                {c.also.length > 0 && <div className="also">also in {c.also.map((lv) => layerName(lv) ?? `L${lv}`).join(", ")}</div>}
+              </Link>
+            ))}</div>
+          </section>
+        ))}
+      </section>
+    )}
+    {d.board && d.board.nodes.length > 0 && (
+      <section aria-labelledby="ws-map" id="map">
+        <h2 id="ws-map">The map <Link className="ws-open-full" to={ws.link({ ...ws.addr, place: { kind: "whole", view: "graph" } })}
+                                      title="Open the full graph" aria-label="Open the full graph">Open full graph ›</Link></h2>
+        <div className="ws-mapgraph"><ReviewGraph board={d.board} embedded /></div>
+      </section>
+    )}
+  </>;
+}
+
+/** The review's and its layers' comment threads. */
+export function Discussion() {
+  const d = useWs().data, layerName = layerOf(d);
+  return (
+    <section aria-labelledby="ws-talk">
+      <h2 id="ws-talk">Discussion</h2>
+      <Comments reviewId={d.id} comments={d.comments} kind="review" anchor={{}} onChange={d.loadComments} />
+      {[...new Set(d.comments.filter((c) => c.anchor_kind === "chapter" && c.parent_id === null)
+        .map((c) => (typeof c.anchor.level === "number" ? c.anchor.level : null)))]
+        .map((level) => (
+          <div key={String(level)} className="bd-layer-thread">
+            <div className="m">Layer {layerName(level) ?? (level === null ? "unlayered" : `L${level}`)}</div>
+            <Comments reviewId={d.id} comments={d.comments} kind="chapter" anchor={{ level }} onChange={d.loadComments} compact />
+          </div>
+        ))}
+    </section>
+  );
+}
+
+/** The home of a review run before the reading (spec 2026-10-04-review-workspace §3.1): what the change is for and
+ * why it is risky first. */
+function OldWhole() {
   const ws = useWs(), d = ws.data, about = d.about, risk = d.detail!.review.risk;
   const sideEffects = useMemo(() => (d.board ? sideEffectFiles(d.board) : []), [d.board]);
   const drift = driftSummary(about?.drift ?? []);
-  const ov = d.overview;
-  const layerName = (level: number | null) => (d.board?.layers ?? ov?.layers ?? []).find((l) => l.level === level)?.name;
   return (
     <div className="ws-page"><div className="ws-text ws-whole">
       <section aria-labelledby="ws-intent">
@@ -43,35 +110,7 @@ export default function WholePage() {
         </section>
       )}
       {d.stories && <p className="ws-summary"><NameText text={d.stories.summary} /></p>}
-      {ov && (
-        <section aria-labelledby="ws-map" id="map">
-          <h2 id="ws-map">The map</h2>
-          <p className="muted">This change is split into {ov.totals.clusters} parts of connected code, riskiest first.
-            {ov.merged_over_limit > 0 && ` ${ov.merged_over_limit} small parts were merged to keep the list short.`}</p>
-          {bandsOf(ov).map((b) => (
-            <section key={b.level} className={`ov-band lv${b.level < 0 ? "x" : b.level % 4}`} aria-label={`Layer ${b.name}`}>
-              <h3>{b.name}</h3>
-              <div className="ov-blocks">{b.clusters.map((c) => (
-                <Link key={c.id} to={ws.link(ws.item({ kind: "cluster", cid: c.id }))} className={`ov-block ${c.risk ?? "none"}`}
-                      title={`Open ${c.name}`} aria-label={`Open ${c.name}`}>
-                  <div className="nm">{c.name} {c.risk && <span className={`sev ${c.risk}`}>{c.risk.toUpperCase()}</span>}</div>
-                  <div className="ct">{c.files.length} files · {c.changed} changed · {c.flows} flows
-                    {c.findings > 0 && ` · ${c.findings} finding${c.findings === 1 ? "" : "s"}`}</div>
-                  {linkLines(ov, c.id, 3).map((l) => <div key={l} className="ln">{l}</div>)}
-                  {c.also.length > 0 && <div className="also">also in {c.also.map((lv) => layerName(lv) ?? `L${lv}`).join(", ")}</div>}
-                </Link>
-              ))}</div>
-            </section>
-          ))}
-        </section>
-      )}
-      {d.board && d.board.nodes.length > 0 && (
-        <section aria-labelledby="ws-map" id="map">
-          <h2 id="ws-map">The map <Link className="ws-open-full" to={ws.link({ ...ws.addr, place: { kind: "whole", view: "graph" } })}
-                                        title="Open the full graph" aria-label="Open the full graph">Open full graph ›</Link></h2>
-          <div className="ws-mapgraph"><ReviewGraph board={d.board} embedded /></div>
-        </section>
-      )}
+      <MapSection />
       {sideEffects.length > 0 && (
         <section aria-labelledby="ws-fx">
           <h2 id="ws-fx">Files with side effects</h2>
@@ -99,18 +138,7 @@ export default function WholePage() {
             submitted CLs). {drift.info.join("; ")}</p>}
         </section>
       )}
-      <section aria-labelledby="ws-talk">
-        <h2 id="ws-talk">Discussion</h2>
-        <Comments reviewId={d.id} comments={d.comments} kind="review" anchor={{}} onChange={d.loadComments} />
-        {[...new Set(d.comments.filter((c) => c.anchor_kind === "chapter" && c.parent_id === null)
-          .map((c) => (typeof c.anchor.level === "number" ? c.anchor.level : null)))]
-          .map((level) => (
-            <div key={String(level)} className="bd-layer-thread">
-              <div className="m">Layer {layerName(level) ?? (level === null ? "unlayered" : `L${level}`)}</div>
-              <Comments reviewId={d.id} comments={d.comments} kind="chapter" anchor={{ level }} onChange={d.loadComments} compact />
-            </div>
-          ))}
-      </section>
+      <Discussion />
     </div></div>
   );
 }
```

`frontend/src/workspace/workspace.css` (diff):

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 04e7263..1a3f294 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -522,3 +522,76 @@ a.ws-chip { text-decoration: none; }
 .bd-hl { display: inline-flex; align-items: center; gap: 4px; padding: 0 2px 0 10px; border-radius: 8px; font: 600 12px var(--bd-sans);
   color: var(--flow); background: color-mix(in srgb, var(--flow) 12%, transparent); }
 .bd-hl .bd-ibtn { background: transparent !important; padding: 0 8px !important; }
+
+/* review reading (spec 2026-10-07-review-reading): the overview and story page in two columns, the right one pinned */
+.ov2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 380px); gap: 28px; max-width: 1280px; margin: 0 auto;
+  align-items: start; }
+.ov2-right { position: sticky; top: 0; max-height: calc(100vh - 140px); overflow: auto; display: flex; flex-direction: column; gap: 14px; }
+.ws-tile { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
+.ws-tile > h3, .ws-tile > summary > h3 { display: flex; align-items: baseline; gap: 8px; margin: 0 0 8px; font-size: 12px;
+  text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
+.ws-tile > summary { cursor: pointer; list-style: none; }
+.ws-tile > summary > h3 { display: inline-flex; margin: 0; }
+.ws-tile[open] > summary > h3 { margin-bottom: 8px; }
+.ck-count { font: 600 11px/1.6 var(--sans); padding: 0 7px; border-radius: 99px; background: var(--gap-bg); color: var(--ink);
+  text-transform: none; letter-spacing: 0; }
+.ck-group + .ck-group { margin-top: 10px; }
+.ck-group h4 { margin: 0 0 4px; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: none; letter-spacing: 0; }
+.ck-list { list-style: none; margin: 0; padding: 0; }
+.ck-row { padding: 7px 0; border-top: 1px solid var(--line); font-size: 13px; }
+.ck-row:first-child { border-top: 0; }
+.ck-row.marked { color: var(--muted); }
+.ck-row.marked .ck-tag { filter: grayscale(1); opacity: .7; }
+.ck-row.lit { background: color-mix(in srgb, var(--accent) 10%, var(--surface)); box-shadow: -3px 0 0 var(--accent); }
+.ck-top { display: flex; gap: 6px; align-items: baseline; }
+.ck-top + .ck-top { margin-top: 3px; }
+.ck-tag { flex: none; font: 600 10.5px/1.5 var(--sans); padding: 0 6px; border-radius: 4px; background: var(--gap-bg); color: var(--ink); }
+/* one colour scale for check kinds (§12): what to act on red, then amber, then the analysis' own kinds in blue */
+.ck-tag.hazard { background: color-mix(in srgb, var(--bad) 16%, var(--surface)); color: var(--bad); }
+.ck-tag.confirm { background: color-mix(in srgb, var(--warn) 12%, var(--surface)); color: var(--warn); }
+.ck-tag.caller, .ck-tag.result, .ck-tag.reader, .ck-tag.target { background: color-mix(in srgb, var(--accent) 12%, var(--surface));
+  color: var(--accent); }
+.ck-tag.ask { background: color-mix(in srgb, var(--accent) 6%, var(--surface)); color: var(--accent); border: 1px dashed var(--accent); }
+.ck-place { margin-top: 3px; font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
+.ck-src { display: block; margin-top: 3px; padding: 2px 6px; font-size: 12px; background: var(--gap-bg); border-radius: 4px;
+  white-space: pre-wrap; overflow-wrap: anywhere; }
+.ck-mark { margin-top: 3px; font-size: 12px; color: var(--muted); }
+.ck-mark.changed { color: var(--warn); font-weight: 600; }
+.ck-acts { display: flex; gap: 12px; margin-top: 4px; font-size: 12px; }
+.ck-acts a { text-decoration: none; }
+.ck-cleared { margin-top: 8px; font-size: 12px; }
+.ck-cleared summary { cursor: pointer; color: var(--muted); }
+.ck-cleared ul { margin: 4px 0 0; padding-left: 18px; }
+.ov-lines { list-style: none; margin: 0; padding: 0; font-size: 13px; }
+.ov-lines li { padding: 3px 0; }
+.ov-conn { position: relative; margin: 4px 0 0; }
+.ov-box { position: absolute; left: 0; width: 220px; display: flex; align-items: center; gap: 8px; padding: 0 10px; text-align: left;
+  background: var(--surface); border: 1px solid var(--line); border-radius: 8px; color: var(--ink); font: inherit; font-size: 13px;
+  cursor: pointer; }
+.ov-box.hot { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 25%, transparent); }
+.ov-box-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
+.ov-letter { flex: none; display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 50%;
+  background: var(--accent); color: var(--surface); font: 700 11px/1 var(--sans); }
+.ov-arcs { position: absolute; left: 220px; top: 0; overflow: visible; }
+.ov-arc { fill: none; stroke: var(--muted); stroke-width: 1.6; pointer-events: visibleStroke; }
+.ov-arc.dashed { stroke: var(--accent); stroke-dasharray: 5 4; }
+.ov-arc.hot { stroke: var(--accent); stroke-width: 2.6; }
+.ov-arc-label { position: absolute; left: calc(220px + var(--reach) + 14px); right: 0; transform: translateY(-50%);
+  font-size: 13px; line-height: 1.35; }
+.ov-arc-label.dashed { color: var(--accent); }
+.ov-arc-label.hot { font-weight: 600; }
+.ov-conn-rows { margin: 0; padding-left: 18px; font-size: 13px; }
+.ov-conn-rows li.bundled { color: var(--accent); }
+.ov-thread { padding: 10px 0 12px; border-top: 1px solid var(--line); }
+.ov-thread header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
+.ov-thread h3 { margin: 0; font-size: 15px; }
+.ov-purpose { margin: 6px 0; font-size: 14px; }
+.ov-stories { margin: 4px 0 0; padding-left: 22px; font-size: 14px; }
+.ov-stories li { padding: 2px 0; }
+.ov-stories a { text-decoration: none; }
+.ov-reason { margin-left: 8px; font-size: 12px; color: var(--muted); }
+.ov-tests { margin: 6px 0 0; padding-top: 8px; border-top: 1px solid var(--line); font-size: 13px; color: var(--muted); }
+@media (max-width: 900px) {
+  .ov2 { grid-template-columns: minmax(0, 1fr); }
+  .ov2-right { order: -1; position: static; max-height: none; }
+}
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd frontend && npx vitest run src/reading/overview.test.ts`
Expected: PASS: `Tests 6 passed (6)`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-detail.spec.ts e2e/workspace-reading.spec.ts e2e/workspace.spec.ts`
Expected: PASS: `36 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `606 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 154 passed (154)`; Playwright `97 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/workspace-detail.spec.ts frontend/e2e/workspace-reading.spec.ts frontend/e2e/workspace.spec.ts frontend/src/reading/overview.test.ts frontend/src/reading/overview.ts frontend/src/workspace/CheckList.tsx frontend/src/workspace/Overview.tsx frontend/src/workspace/WholePage.tsx frontend/src/workspace/workspace.css
git commit -m "feat(ui): the overview tells the change as threads with arcs between them, and pins To check, build impact and coverage beside it"
```

### Task 11: The story page

Spec §6. With a reading, a story page reads from its thread: the crumb "Thread A › name · story 1 of 2" with ‹ › stepping in reading order, the open hazard count, CL chips ("CL 101 · 1 function"). Left: What it does (purpose or summary, then its place in the thread); Before → after beside Where (folder › file › functions with edit size and CL, each opening its code); Call paths, every one, grouped under its entry point, folded past four steps with "Show the N folded steps", each linking "On the graph ›"; Code, each function's code in definition-first order; Questions and comments. Right, pinned: the story's To check and what the strong model also suggests. A review without a reading keeps the old story body.

**Files:**
- Test: `frontend/e2e/ai.spec.ts`
- Test: `frontend/e2e/mention.spec.ts`
- Test: `frontend/e2e/workspace-pages.spec.ts`
- Test: `frontend/e2e/workspace-reading.spec.ts`
- Test: `frontend/e2e/workspace-story.spec.ts`
- Test: `frontend/e2e/workspace-tier1.spec.ts`
- Test: `frontend/src/reading/story.test.ts`
- Create: `frontend/src/reading/story.ts`
- Modify: `frontend/src/workspace/StoryPage.tsx`
- Create: `frontend/src/workspace/StoryTiles.tsx`
- Modify: `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: `StoryDetail.reading` and the reading (Task 9), `CheckTile` (Task 10), `FunctionCode`.
- Produces: `reading/story.ts`: `stepIn(order, sid, by)`, `threadCrumb(r, sid)`, `clCounts(where)`, `whereTree(where)`, `byEntry(paths)`, `foldPath(p, open)`, `codeOrder(where, rows)`; `workspace/StoryTiles.tsx` (default `StoryTiles({ detail, sr })`).

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/ai.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/ai.spec.ts b/frontend/e2e/ai.spec.ts
index 83cd642..42e66e9 100644
--- a/frontend/e2e/ai.spec.ts
+++ b/frontend/e2e/ai.spec.ts
@@ -62,14 +62,14 @@ test.describe("with an AI", () => {
     const told = board.flows.find((f: { what_source: string }) => f.what_source === "llm");
     const sid = ss.flow_story[told.id];
     const s = ss.stories.find((x: { id: string }) => x.id === sid);
-    await page.goto(`${base}/s/${sid}?flow=${s.flows.indexOf(told.id) + 1}`);
+    await page.goto(`${base}/s/${sid}?view=graph&flow=${s.flows.indexOf(told.id) + 1}`);
     const what = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text p").first();
     await expect(what.locator(".ai-label")).toBeVisible();                     // the board's narrative, on the story
     await expect(what.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
     const other = ss.stories.flatMap((x: { id: string; flows: string[] }) => x.flows.map((f) => [x.id, f]))
       .find(([, f]: string[]) => f !== told.id)!;
     const st = ss.stories.find((x: { id: string }) => x.id === other[0]);
-    await page.goto(`${base}/s/${other[0]}?flow=${st.flows.indexOf(other[1]) + 1}`);
+    await page.goto(`${base}/s/${other[0]}?view=graph&flow=${st.flows.indexOf(other[1]) + 1}`);
     const ask = what.getByRole("button", { name: /Explain/ });
     await expect(ask).toHaveText("✦ Explain");
     await ask.click();
@@ -101,7 +101,7 @@ test.describe("with an AI", () => {
     await page.goto(`${base}/f/${tx.id}`);
     await expect(page.locator(".ws-finding h2 .badge")).toHaveText("info");
     await expect(page.locator(".ws-verdict")).toContainText("AI: no clear hazard — Nothing else depends on the value it writes.");
-    await page.goto(`${base}/s/S1`);
+    await page.goto(`${base}/s/S1?view=graph`);                              // a story's flows are on its graph
     const lands = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-lands");
     await expect(lands).toContainText("⚠ Side effect lands on uart_errors.");
     await expect(lands).toContainText("AI: uart_errors assumes only uart_init writes Uart::errors.");
```

`frontend/e2e/mention.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/mention.spec.ts b/frontend/e2e/mention.spec.ts
index b192197..76ef497 100644
--- a/frontend/e2e/mention.spec.ts
+++ b/frontend/e2e/mention.spec.ts
@@ -64,8 +64,9 @@ test.describe("with an AI", () => {
     await expect(talk.locator(".comment", { hasText: "what does this story change for callers?" })).toBeVisible();
     await expect(talk.locator(".comment.ai")).toContainText(answer, { timeout: 30_000 });
 
+    await page.goto(`${base}/s/S1?view=graph`);                              // a story's flows are on its graph
     const strip = page.getByRole("region", { name: "Flow" });
-    await strip.getByRole("button", { name: "Next flow" }).click();          // flow 1's text is the story's summary
+    await strip.getByRole("button", { name: "Next flow" }).click();
     await ask(strip, "is the new writer safe?");
     await expect(strip.locator(".comment.ai")).toContainText(answer, { timeout: 30_000 });
 
```

`frontend/e2e/workspace-pages.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-pages.spec.ts b/frontend/e2e/workspace-pages.spec.ts
index e573849..72711a6 100644
--- a/frontend/e2e/workspace-pages.spec.ts
+++ b/frontend/e2e/workspace-pages.spec.ts
@@ -42,6 +42,7 @@ test.describe("desktop", () => {
     await expect(page.locator(".ws-finding h2 .badge")).toHaveText("info");
     await expect(page.locator(".ws-verdict")).toContainText("Side effect · not yet assessed");
     await page.locator(".ws-where").getByRole("link", { name: /^Go to story/ }).click();
+    await page.getByRole("tab", { name: "Graph" }).click();                  // a story's flows are on its graph
     const strip = page.getByRole("region", { name: "Flow" });
     await strip.getByRole("button", { name: "Every flow" }).click();
     await strip.getByRole("menuitemradio", { name: /uart_errors sees a new writer of Uart::errors/ }).click();
```

`frontend/e2e/workspace-reading.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-reading.spec.ts b/frontend/e2e/workspace-reading.spec.ts
index b8ae25b..52b3ce5 100644
--- a/frontend/e2e/workspace-reading.spec.ts
+++ b/frontend/e2e/workspace-reading.spec.ts
@@ -77,6 +77,32 @@ test.describe("desktop", () => {
     await expect(row.locator(".comments")).toContainText("flush should retry");
     await expect(row.getByRole("button", { name: "Comment (1)" })).toBeVisible();
   });
+  test("a story: its thread, what it does, before → after beside where, its call paths and its own To check", async ({ page }) => {
+    const base = await startReview(page, FOUR);
+    await page.goto(`${base}/s/S2`);
+    const head = page.locator(".ws-story-head");
+    await expect(head.locator(".st-crumb")).toHaveText("Thread A › hal_write in hal · story 1 of 2");
+    await expect(head.locator(".ws-story-meta .ws-chip").first()).toHaveText("CL 102 · 1 function");
+    const contract = page.getByRole("region", { name: "Before → after" });
+    await expect(contract).toContainText("hal_write: gained unsigned");
+    await expect(contract.locator("mark")).toHaveText("unsigned");                  // the part of the signature that differs
+    const paths = page.getByRole("region", { name: /^Call paths/ });
+    await expect(paths.locator(".st-steps")).toHaveText(["contractmain→uart_init→hal_write"]);
+    await expect(page.getByRole("region", { name: "To check" }).locator("h3 .ck-count")).toHaveText("2 of 2 open");
+    await page.getByRole("region", { name: "Where" }).getByRole("link", { name: "Open hal_write in hal/regs.c at line 10" }).click();
+    await expect(page.getByRole("complementary", { name: "Code: regs.c" })).toBeVisible();
+    await head.getByRole("link", { name: /^Next story: S1/ }).click();               // reading order: what S1 uses comes first
+    await expect(head.locator(".st-crumb")).toHaveText("Thread A › hal_write in hal · story 2 of 2");
+    await expect(page.locator(".st-place")).toHaveText("Uses what story 1 adds.");
+    await expect(paths.locator(".st-steps").nth(1)).toHaveText("statemain→… 2 more→Uart::errors→uart_errors");
+    await paths.getByRole("button", { name: "Show the 2 folded steps" }).click();
+    await expect(paths.locator(".st-steps").nth(1)).toHaveText("statemain→logger_write→uart_send→Uart::errors→uart_errors");
+    await expectNoNodeIds(page);
+    await expectNamed(page);
+    await paths.getByRole("link", { name: /On the graph/ }).first().click();
+    await expect(page).toHaveURL(/\/s\/S1\?view=graph&flow=1/);
+    await expect(page.locator(".bd-node").first()).toBeVisible();
+  });
 });
 
 test.describe("phone", () => {
@@ -97,4 +123,14 @@ test.describe("phone", () => {
     await expect(check.locator(".ck-row")).toHaveCount(6);
     expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
   });
+
+  test("a story's To check comes first, folded to its count", async ({ page }) => {
+    const base = await startReview(page, FOUR);
+    await page.goto(`${base}/s/S1`);
+    const check = page.locator("details.ck-tile");
+    await expect(check.locator("summary .ck-count")).toHaveText("3 of 3 open");
+    const tile = (await check.boundingBox())!, what = (await page.getByRole("heading", { name: "What it does" }).boundingBox())!;
+    expect(tile.y).toBeLessThan(what.y);
+    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
+  });
 });
```

`frontend/e2e/workspace-story.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-story.spec.ts b/frontend/e2e/workspace-story.spec.ts
index a23aa27..4c353ef 100644
--- a/frontend/e2e/workspace-story.spec.ts
+++ b/frontend/e2e/workspace-story.spec.ts
@@ -3,31 +3,26 @@ import { expectNamed, expectNoNodeIds, flowStripHolds, startReview } from "./hel
 
 /** A story in the workspace (spec 2026-10-04-review-workspace §3.2, §2.4). */
 
-const step = (page: Page, label: string) => page.getByRole("list", { name: "Flow steps" }).getByRole("link", { name: `Open ${label}'s code` });
 const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });
 
 test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
-  test("steps open the detail panel and mark the step; flows replace history; findings link to their pages", async ({ page }) => {
+  test("Where opens a function's diff in the side panel and Code opens it in place", async ({ page }) => {
     const base = await startReview(page);
     await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
     await expect(page.locator(".ws-story-head h2")).toContainText("uart_send can now return -2");
     await expect(page.getByRole("tab", { name: "Steps" })).toHaveAttribute("aria-selected", "true");
-    await expect(page.locator(".ws-story-meta .ws-chip:not(.ws-onmap)")).toHaveText(["CL 101", "CL 102"]);
-    await step(page, "uart_send").click();
-    await expect(page).toHaveURL(/\/s\/S1\?open=N\d+$/);
-    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
-    await expect(page.getByRole("link", { name: "Close uart_send's code" })).toHaveAttribute("aria-current", "true");
-    await page.getByRole("link", { name: "Close uart_send's code" }).click();
+    await expect(page.locator(".ws-story-meta .ws-chip:not(.ws-onmap)")).toHaveText(["CL 101 · 1 function"]);   // its functions by CL
+    await page.getByRole("region", { name: "Where" }).getByRole("link", { name: "Open uart_send in driver/uart.c at line 11" }).click();
+    await expect(page).toHaveURL(/\/s\/S1\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c%3A11$/);
+    await expect(page.getByRole("complementary", { name: "Code: uart.c" })).toBeVisible();
+    await page.getByRole("link", { name: "Close the code" }).click();
     await expect(page.locator(".ws-detail")).toHaveCount(0);
-
-    await flowStripHolds(page);
-    await page.goBack();                                       // flows replaced the entry: Back undoes the close
-    await expect(page.locator(".ws-detail")).toBeVisible();
-    await page.goForward();
-    await page.getByRole("link", { name: /^Go to finding F1:/ }).first().click();
-    await expect(page).toHaveURL(new RegExp(`${base}/f/F1$`));
+    const code = page.getByRole("region", { name: "Code" });
+    await code.locator("summary", { hasText: "uart_send" }).click();
+    await expect(code.locator(".bd-code").first()).toBeVisible();
+    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));                  // in place: the address stays
     await expectNoNodeIds(page);
   });
 
@@ -61,7 +56,7 @@ test.describe("desktop", () => {
     await expectNamed(page);
 
     await page.getByRole("tab", { name: "Steps" }).click();
-    await expect(page.getByRole("list", { name: "Flow steps" })).toBeVisible();     // measure in the Steps layout
+    await expect(page.getByRole("region", { name: "To check" })).toBeVisible();     // measure in the Steps layout
     const next = page.getByRole("link", { name: /^Next story/ });
     const x = (await next.boundingBox())!.x;
     await next.click();
@@ -101,7 +96,7 @@ test.describe("desktop", () => {
     const real = await (await page.request.get(`/api/reviews/${rid}/stories/S1`)).json();
     await page.route(`**/api/reviews/${rid}/stories/S1`, (r) => r.fulfill({ json: { ...real, graph: null } }));
     await page.goto(`${base}/s/S1?view=graph`);
-    await expect(page.getByRole("list", { name: "Flow steps" })).toBeVisible();
+    await expect(page.getByRole("region", { name: "Before → after" })).toBeVisible();
     await expect(page.getByRole("tab", { name: "Graph" })).toHaveCount(0);
   });
 
@@ -190,10 +185,10 @@ test.describe("phone", () => {
     await startReview(page);
     await page.getByRole("link", { name: /^Go to story S1/ }).click();
     await expect(page.locator(".ws-phonebar")).toContainText("‹ Stories");
-    await step(page, "uart_send").click();
+    await page.getByRole("region", { name: "Where" }).getByRole("link", { name: /^Open uart_send in/ }).click();
     const bar = page.locator(".ws-detail .ws-phonebar");
-    await expect(bar).toContainText("‹ S1");
-    await expect(bar).toContainText("uart_send");
+    await expect(bar).toContainText("‹ Back");
+    await expect(bar).toContainText("uart.c");
     await bar.getByRole("link", { name: "Close the code" }).click();
     await expect(page.locator(".ws-centre .ws-phonebar")).toContainText("‹ Stories");
     expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
@@ -203,7 +198,7 @@ test.describe("phone", () => {
 test.describe("a story's flows on its graph", () => {
   test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });
 
-  test("flow=N is the same flow on Steps and Graph; a flow too long to draw says so and links to Steps", async ({ page }) => {
+  test("a flow too long to draw says so on the graph and links to the story's call paths", async ({ page }) => {
     const base = await startReview(page, "201 202");
     const rid = base.split("/")[2];
     const get = async (url: string) => (await page.request.get(`/api/reviews/${rid}/${url}`)).json();
@@ -218,20 +213,16 @@ test.describe("a story's flows on its graph", () => {
       j.graph.flows = j.graph.flows.slice(1);
       await route.fulfill({ response: res, json: j });
     });
-    await page.goto(`${base}/s/${sid}?flow=2`);
-    const strip = page.getByRole("region", { name: "Flow" }), title = strip.locator(".ws-flow-title");
-    await expect(title).not.toHaveText("");
-    const second = await title.innerText(), of = await strip.locator(".ws-flow-pos").innerText();
-    await page.getByRole("tab", { name: "Graph" }).click();
-    await expect(page).toHaveURL(/view=graph&flow=2$/);
+    await page.goto(`${base}/s/${sid}?view=graph&flow=2`);
+    const strip = page.getByRole("region", { name: "Flow" });
     await expect(page.locator(".ws-graph .bd-node").first()).toBeVisible();
-    await expect(title).toHaveText(second);
-    await expect(strip.locator(".ws-flow-pos")).toHaveText(of);
+    await expect(strip.locator(".ws-flow-pos")).toHaveText(/^flow 2 of \d+$/);
     await strip.getByRole("button", { name: "Previous flow" }).click();
     await expect(page).toHaveURL(/view=graph&flow=1$/);
     await expect(strip).toContainText("This flow is too long to draw here");
     await strip.getByRole("link", { name: "See it in Steps" }).click();
     await expect(page).toHaveURL(new RegExp(`/s/${sid}\\?flow=1$`));
     await expect(page.getByRole("tab", { name: "Steps" })).toHaveAttribute("aria-selected", "true");
+    await expect(page.getByRole("region", { name: /^Call paths/ })).toBeVisible();
   });
 });
```

`frontend/e2e/workspace-tier1.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-tier1.spec.ts b/frontend/e2e/workspace-tier1.spec.ts
index 5c25383..bae0528 100644
--- a/frontend/e2e/workspace-tier1.spec.ts
+++ b/frontend/e2e/workspace-tier1.spec.ts
@@ -6,7 +6,7 @@ const STRONG = "http://127.0.0.1:8795";  // e2e/serve-strong.sh: stories and ris
 test.describe("stories formed by a strong model", () => {
   test.use({ baseURL: STRONG });
 
-  test("a story shows its targets, why its pieces belong together, what to check, questions and related stories", async ({ page }) => {
+  test("a story shows its targets, its hazard, what the strong model suggests checking and its open questions", async ({ page }) => {
     const base = await startReview(page);
     const rail = page.locator(".ws-rail");
     const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
@@ -15,18 +15,14 @@ test.describe("stories formed by a strong model", () => {
     await page.goto(`${base}/s/S1`);
     const head = page.locator(".ws-story-head");
     await expect(head.locator(".ws-chip.target")).toHaveText("⌖ fw");
+    await expect(head.locator(".ct-headline.hazard")).toHaveText("1 hazard");
     await expect(head.getByRole("button", { name: /Explain/ })).toHaveCount(0);       // tier 2 never retells it
     await expect(head.getByRole("button", { name: "Ask…" })).toBeVisible();
-    await expect(page.getByRole("region", { name: "What to check" })).toContainText("Check that logger_flush handles the new -2.");
-    await expect(page.getByRole("region", { name: "Open questions" })).toContainText("Does any caller retry a send after -2?");
-    const why = page.getByRole("region", { name: "Why these belong together" });
-    await expect(why.locator("li")).toHaveCount(2);
-    await expect(why.locator("li").first()).toContainText("starts the story");
-    await expect(why.locator("li").nth(1)).toContainText("same feature");
-    await expect(why.getByRole("link", { name: "Open //fixture/driver/uart.c" })).toBeVisible();
-    const related = page.getByRole("region", { name: "Related" });
-    await related.getByRole("link", { name: "see S2 · hal" }).click();
-    await expect(page.locator(".ws-story-head h2")).toContainText("HAL writes take an unsigned register");
+    const check = page.getByRole("region", { name: "To check" });
+    await expect(check.locator(".ck-row").first().locator(".ck-tag").first()).toHaveText("Hazard");
+    await expect(check.locator(".st-suggested")).toContainText("Check that logger_flush handles the new -2.");
+    await expect(page.getByRole("region", { name: "Questions and comments" })).toContainText("Does any caller retry a send after -2?");
+    await expect(page.getByRole("region", { name: "Why these belong together" })).toHaveCount(0);   // folded into the tiles
     await expectNamed(page);
   });
 
```

`frontend/src/reading/story.test.ts` (new file):

```ts
import { describe, expect, it } from "vitest";
import { byEntry, clCounts, codeOrder, foldPath, stepIn, threadCrumb, whereTree } from "./story";
import type { CallPath, ContractRow, Reading, WhereFile } from "./types";

const fn = (node: string, label: string, cl: number | null, extra = {}) => ({ node, label, add: 2, rem: 1, cl, line: 3, ...extra });
const file = (path: string, functions: ReturnType<typeof fn>[]): WhereFile => ({ path, depot: `//d/${path}`, functions });
const path = (labels: string[], extra: Partial<CallPath> = {}): CallPath => ({
  steps: labels.map((l) => `n-${l}`), labels, kind: "call", entry: `n-${labels[0]}`, hidden: [], text: "", flow: null, ...extra,
});

describe("a story's place", () => {
  it("steps through every story in reading order, wrapping", () => {
    const order = ["S2", "S1", "S3"];
    expect(stepIn(order, "S2", 1)).toBe("S1");
    expect(stepIn(order, "S2", -1)).toBe("S3");
    expect(stepIn(order, "S3", 1)).toBe("S2");
    expect(stepIn(order, "S9", 1)).toBe("S9");
  });

  it("names its thread and its place in it", () => {
    const r = { threads: [{ id: "T1", name: "a", stories: ["S2", "S1"] }, { id: "T2", name: "`b` in x", stories: ["S3"] }] } as Reading;
    expect(threadCrumb(r, "S1")).toEqual({ letter: "A", name: "a", id: "T1", text: "story 2 of 2" });
    expect(threadCrumb(r, "S3")).toEqual({ letter: "B", name: "`b` in x", id: "T2", text: "story 1 of 1" });
    expect(threadCrumb(r, "S5")).toBeNull();
  });
});

describe("Where", () => {
  it("counts each CL's changed functions for the header chips", () => {
    expect(clCounts([file("a/x.c", [fn("N1", "f", 12), fn("N2", "g", 11)]), file("a/y.c", [fn("N3", "h", 12), fn("N4", "k", null)])]))
      .toEqual([{ cl: 11, functions: 1 }, { cl: 12, functions: 2 }]);
  });

  it("goes folder, file, functions, and shows a function's CL only where its file was edited in several", () => {
    const tree = whereTree([file("drv/uart.c", [fn("N1", "send", 101), fn("N2", "init", 102)]), file("drv/hal.c", [fn("N3", "w", 102)]),
                            file("top.c", [fn("N4", "main", 101)])]);
    expect(tree.map((d) => [d.dir, d.files.map((f) => [f.name, f.showCl])])).toEqual([
      ["drv", [["uart.c", true], ["hal.c", false]]], [".", [["top.c", false]]]]);
  });
});

describe("Call paths", () => {
  it("groups the paths under their entry point in rank order", () => {
    const groups = byEntry([path(["main", "flush", "send"]), path(["isr", "send"]), path(["main", "write", "send"]),
                            path(["worker", "send"], { entry: null })]);
    expect(groups.map((g) => [g.label, g.entry, g.paths.length])).toEqual([["main", true, 2], ["isr", true, 1], ["worker", false, 1]]);
  });

  it("folds the middle of a long path into one step until it is opened", () => {
    const p = path(["main", "a", "b", "c", "send"], { hidden: ["n-a", "n-b"] });
    expect(foldPath(p, false)).toEqual([{ label: "main" }, { more: 2 }, { label: "c" }, { label: "send" }]);
    expect(foldPath(p, true).map((s) => ("label" in s ? s.label : s.more))).toEqual(["main", "a", "b", "c", "send"]);
  });
});

describe("Code", () => {
  it("shows the functions whose contract changed first, then the rest in Where's order", () => {
    const where = [file("a.c", [fn("N1", "caller", 1), fn("N2", "callee", 1)]), file("b.c", [fn("N3", "other", 1)])];
    const rows = [{ kind: "signature", nodes: ["N2"] } as ContractRow, { kind: "body", nodes: ["N1", "N3"] } as ContractRow];
    expect(codeOrder(where, rows).map((f) => f.label)).toEqual(["callee", "caller", "other"]);
  });
});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd frontend && npx vitest run src/reading/story.test.ts`
Expected: FAIL: `Tests no tests`; the first error is `Error: Cannot find module './story' imported from frontend/src/reading/story.test.ts`

Run: `cd frontend && npm run build && npx playwright test e2e/ai.spec.ts e2e/mention.spec.ts e2e/workspace-pages.spec.ts e2e/workspace-reading.spec.ts e2e/workspace-story.spec.ts e2e/workspace-tier1.spec.ts`
Expected: FAIL: `npm run build fails with 6 type error(s)`; the first error is `src/reading/story.test.ts(2,88): error TS2307: Cannot find module './story' or its corresponding type declarations.`

- [ ] **Step 3: Implement**

`frontend/src/reading/story.ts` (new file):

```ts
/** A story page's tiles (spec 2026-10-07-review-reading §6): its place in its thread, Where, call paths and code order. */
import { letter } from "./checks";
import type { CallPath, ContractRow, Reading, WhereFile, WhereFn } from "./types";

/** ‹ › on a story page: the story `by` places away in reading order, wrapping; a story not in it stays put. */
export function stepIn(order: string[], sid: string, by: number): string {
  const at = order.indexOf(sid);
  return at < 0 ? sid : order[(at + by + order.length) % order.length];
}

/** "Thread A › name · story 1 of 3" for the header; null for a story in no thread (tests). */
export function threadCrumb(r: Reading, sid: string): { letter: string; name: string; id: string; text: string } | null {
  const i = r.threads.findIndex((t) => t.stories.includes(sid));
  if (i < 0) return null;
  const t = r.threads[i];
  return { letter: letter(i, t.id), name: t.name, id: t.id, text: `story ${t.stories.indexOf(sid) + 1} of ${t.stories.length}` };
}

/** "CL 11 · 14 functions": each CL's changed functions in the story, by CL. */
export function clCounts(where: WhereFile[]): { cl: number; functions: number }[] {
  const n = new Map<number, number>();
  for (const f of where.flatMap((w) => w.functions)) if (f.cl !== null) n.set(f.cl, (n.get(f.cl) ?? 0) + 1);
  return [...n.entries()].sort((a, b) => a[0] - b[0]).map(([cl, functions]) => ({ cl, functions }));
}

/** Folder › file › functions, folders in Where's order; a function's CL shows only where its file was edited in
 * several CLs. */
export function whereTree(where: WhereFile[]): { dir: string; files: { name: string; file: WhereFile; showCl: boolean }[] }[] {
  const dirs = new Map<string, { name: string; file: WhereFile; showCl: boolean }[]>();
  for (const w of where) {
    const cut = w.path.lastIndexOf("/"), dir = cut < 0 ? "." : w.path.slice(0, cut);
    const showCl = new Set(w.functions.map((f) => f.cl)).size > 1;
    dirs.set(dir, [...(dirs.get(dir) ?? []), { name: w.path.slice(cut + 1), file: w, showCl }]);
  }
  return [...dirs.entries()].map(([dir, files]) => ({ dir, files }));
}

/** The paths under the function they start from, in rank order; `entry` when that is an entry point. */
export function byEntry(paths: CallPath[]): { label: string; entry: boolean; paths: CallPath[] }[] {
  const groups = new Map<string, { label: string; entry: boolean; paths: CallPath[] }>();
  for (const p of paths) {
    const key = p.steps[0] ?? "";
    if (!groups.has(key)) groups.set(key, { label: p.labels[0] ?? "", entry: !!p.entry, paths: [] });
    groups.get(key)!.paths.push(p);
  }
  return [...groups.values()];
}

/** A path's steps, the folded middle of a long one as a single "N more" step until it is opened. */
export function foldPath(p: CallPath, open: boolean): ({ label: string } | { more: number })[] {
  const steps = p.labels.map((label) => ({ label }));
  if (open || !p.hidden.length) return steps;
  const from = p.steps.indexOf(p.hidden[0]);
  return [...steps.slice(0, from), { more: p.hidden.length }, ...steps.slice(from + p.hidden.length)];
}

/** The story's changed functions for its Code section: those whose contract changed first (definitions before their
 * users), then the rest in Where's order. */
export function codeOrder(where: WhereFile[], rows: ContractRow[]): WhereFn[] {
  const fns = where.flatMap((w) => w.functions);
  const first = new Set(rows.filter((r) => r.kind !== "body").flatMap((r) => r.nodes));
  return [...fns.filter((f) => first.has(f.node)), ...fns.filter((f) => !first.has(f.node))];
}
```

`frontend/src/workspace/StoryPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/StoryPage.tsx b/frontend/src/workspace/StoryPage.tsx
index ecbe4ad..5a5e968 100644
--- a/frontend/src/workspace/StoryPage.tsx
+++ b/frontend/src/workspace/StoryPage.tsx
@@ -4,6 +4,8 @@ import { ApiError } from "../api";
 import type { StoryDetail } from "../board/types";
 import Comments from "../components/Comments";
 import Explain from "../components/Explain";
+import { isOpen } from "../reading/checks";
+import { clCounts, stepIn, threadCrumb } from "../reading/story";
 import { countLine, reviewTargets, stepStory } from "../stories/stories";
 import { type Address, at as addressAt } from "./address";
 import { useWs } from "./context";
@@ -15,9 +17,11 @@ import NameText, { Ticks } from "./NameText";
 import { MechanicalStory, TestsStory } from "./StoryBodies";
 import { StoryChecks, StoryWhy } from "./StoryPlan";
 import StorySteps from "./StorySteps";
+import StoryTiles from "./StoryTiles";
 
-/** A story (spec 2026-10-04-review-workspace §3.2): header with the Steps | Graph switch beside the title and ‹ S1 of 4 ›
- * in a fixed-width group; its steps or its graph, with the flow strip. */
+/** A story (spec 2026-10-04-review-workspace §3.2): header with the Steps | Graph switch beside the title and ‹ › in a
+ * fixed-width group; its tiles (spec 2026-10-07-review-reading §6) or its graph with the flow strip. A review run before
+ * the reading keeps ‹ S1 of 4 › and the steps with the flow strip. */
 export default function StoryPage({ sid, view }: { sid: string; view: "steps" | "graph" }) {
   const ws = useWs(), d = ws.data, ss = d.stories!;
   // held with its story: another story starts loading, while a refreshed one (AI text) replaces it in place
@@ -41,19 +45,29 @@ export default function StoryPage({ sid, view }: { sid: string; view: "steps" |
   const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
   const index = pickFlow(flows, ws.addr.flow, open);
   const onFlow = (i: number) => ws.go({ ...ws.addr, flow: i + 1 }, true);
+  const r = d.reading, crumb = r ? threadCrumb(r, sid) : null, sr = detail?.reading ?? null;
   const step = (by: number) => {
-    const to = stepStory(ss, sid, by), other = ss.stories.find((s) => s.id === to);
+    const to = r ? stepIn(r.order, sid, by) : stepStory(ss, sid, by), other = ss.stories.find((s) => s.id === to);
     const label = `${by < 0 ? "Previous" : "Next"} story: ${to}${other ? ` ${short(other.title)}` : ""}`;
     return <Link className="bd-ibtn ws-step-btn" to={ws.link(ws.item({ kind: "story", sid: to, view: "steps" }))} title={label} aria-label={label}>
       {by < 0 ? "‹" : "›"}</Link>;
   };
 
+  const hazards = sr ? sr.checks.filter((k) => k.kind === "hazard" && isOpen(k, r?.marks ?? {})).length : 0;
   const map: Address | null = st.board ? { ...addressAt({ kind: "cluster", cid: st.board }), story: st.id }   // the story lit on its map
     : d.board ? { ...addressAt({ kind: "whole", view: "graph" }), story: st.id } : null;
   const header = (
     <header className="ws-story-head">
+      {crumb && (
+        <p className="st-crumb">
+          <Link to={ws.link({ ...addressAt({ kind: "whole" }) })} state={{ page: true }} title={`Go to thread ${crumb.letter} on the overview`}
+                aria-label={`Go to thread ${crumb.letter} on the overview`}>Thread {crumb.letter}</Link>
+          <span className="sep" aria-hidden> › </span><Ticks text={crumb.name} /><span className="muted"> · {crumb.text}</span>
+        </p>
+      )}
       <div className="ws-story-title">
-        <h2>{st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
+        <h2>{!r && st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
+          {hazards > 0 && <span className="ct-headline hazard">{hazards} hazard{hazards === 1 ? "" : "s"}</span>}
           {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
         {hasGraph && (
           <span className="ws-switch" role="tablist" aria-label="View">
@@ -63,22 +77,24 @@ export default function StoryPage({ sid, view }: { sid: string; view: "steps" |
             ))}
           </span>
         )}
-        <span className="ws-pos">{step(-1)}<span>{st.id} of {ss.stories.length}</span>{step(1)}</span>
+        <span className="ws-pos">{step(-1)}<span>{r ? (crumb?.text ?? st.id) : `${st.id} of ${ss.stories.length}`}</span>{step(1)}</span>
       </div>
-      <p><NameText text={st.summary} /> {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} askOnly={st.source === "tier1"} ask={{ kind: "story", anchor: { id: st.id }, onAsked: d.loadComments }} />}</p>
-      <p className="ws-story-meta"><span className="muted">{countLine(st)}</span>
-        {st.cls.map((c) => (
-          <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
+      <p>{!r && <NameText text={st.summary} />} {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} askOnly={st.source === "tier1"} ask={{ kind: "story", anchor: { id: st.id }, onAsked: d.loadComments }} />}</p>
+      <p className="ws-story-meta">{!r && <span className="muted">{countLine(st)}</span>}
+        {(sr ? clCounts(sr.where) : st.cls.map((cl) => ({ cl, functions: 0 }))).map(({ cl: c, functions: n }) => (
+          <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>
+            CL {c}{n > 0 && ` · ${n} function${n === 1 ? "" : "s"}`}</Link>
         ))}
         {targets.map((t) => <span key={t} className="ws-chip target" title={`Build target ${t}`}>⌖ {t}</span>)}
         {map && <Link className="ws-chip ws-onmap" to={ws.link(map)} title={`Show ${st.id} on the map`} aria-label={`Show ${st.id} on the map`}>
           ◎ On the map</Link>}</p>
     </header>
   );
-  if (error) return <div className="ws-page"><div className="ws-text">{header}<div className="banner warn">{error}</div></div></div>;
+  const frame = r ? "st-page" : "ws-text";                 // the header keeps its place while the story loads
+  if (error) return <div className="ws-page"><div className={frame}>{header}<div className="banner warn">{error}</div></div></div>;
   if (shown === "graph" && !detail)
     return <div className="ws-page graph"><div className="ws-story-bar">{header}</div><p className="muted ws-page">Loading {st.id}…</p></div>;
-  if (!detail) return <div className="ws-page"><div className="ws-text">{header}<p className="muted">Loading {st.id}…</p></div></div>;
+  if (!detail) return <div className="ws-page"><div className={frame}>{header}<p className="muted">Loading {st.id}…</p></div></div>;
   if (shown === "graph" && detail.graph)
     return (
       <div className="ws-page graph">
@@ -88,6 +104,8 @@ export default function StoryPage({ sid, view }: { sid: string; view: "steps" |
                    onMore={() => ws.go({ ...ws.addr, place: { kind: "story", sid, view: "steps" } }, true)} />
       </div>
     );
+  if (r && sr)
+    return <div className="ws-page"><div className="st-page">{header}<StoryTiles detail={detail} sr={sr} /></div></div>;
   return (
     <div className="ws-page"><div className="ws-text">
       {header}
```

`frontend/src/workspace/StoryTiles.tsx` (new file):

```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import type { StoryDetail } from "../board/types";
import Comments from "../components/Comments";
import { byEntry, codeOrder, foldPath, whereTree } from "../reading/story";
import type { CallPath, ContractRow, StoryReading } from "../reading/types";
import CheckTile from "./CheckList";
import { useWs } from "./context";
import FunctionCode from "./FunctionCode";
import NameText, { Ticks } from "./NameText";
import { MechanicalStory, TestsStory } from "./StoryBodies";
import { StoryWhy } from "./StoryPlan";

/** A contract row (§8.1): its sentence; a signature with the part that differs marked; repeated and body-only edits
 * name their functions on "show N". */
function Contract({ row }: { row: ContractRow }) {
  const names = useWs().data.names;
  const [open, setOpen] = useState(false);
  const many = (row.kind === "repeated" || row.kind === "body") && row.nodes.length > 1;
  const [a, b] = row.mark.length === 2 ? row.mark : [0, 0];
  return (
    <li className={`st-contract ${row.kind}`}>
      <Ticks text={row.text} />
      {many && <button className="link small" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "hide" : `show ${row.nodes.length}`}</button>}
      {row.before && row.after && (
        <div className="st-sig mono">
          <div className="del">{row.before}</div>
          <div className="add">{row.after.slice(0, a)}<mark>{row.after.slice(a, b)}</mark>{row.after.slice(b)}</div>
        </div>
      )}
      {open && <ul className="st-names">{row.nodes.map((n) => <li key={n} className="mono">{names[n]?.label ?? "a function"}</li>)}</ul>}
    </li>
  );
}

/** Before → after beside Where (§6.1). */
function ContractAndWhere({ sr }: { sr: StoryReading }) {
  const ws = useWs();
  return (
    <div className="st-pair">
      {sr.contracts.length > 0 && (
        <section className="ws-tile" aria-label="Before → after">
          <h3>Before → after</h3>
          <ul className="st-contracts">{sr.contracts.map((r, i) => <Contract key={i} row={r} />)}</ul>
        </section>
      )}
      {sr.where.length > 0 && (
        <section className="ws-tile" aria-label="Where">
          <h3>Where</h3>
          {whereTree(sr.where).map((d) => (
            <div key={d.dir} className="st-dir">
              <div className="st-dir-name mono">{d.dir}/</div>
              {d.files.map(({ name, file, showCl }) => (
                <div key={file.path} className="st-file">
                  <div className="mono">{name}</div>
                  <ul>{file.functions.map((f) => {
                    const label = `Open ${f.label} in ${file.path}${f.line ? ` at line ${f.line}` : ""}`;
                    return (
                      <li key={f.node}>
                        {file.depot ? <Link className="mono" to={ws.link(ws.opened({ file: file.depot, line: f.line }))} title={label}
                                            aria-label={label}>{f.label}</Link> : <span className="mono">{f.label}</span>}
                        <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
                        {showCl && f.cl !== null && <span className="ws-chip">CL {f.cl}</span>}
                      </li>
                    );
                  })}</ul>
                </div>
              ))}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function PathRow({ p, graph }: { p: CallPath; graph: string | null }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="st-path">
      <div className="st-steps mono">
        <span className={`bd-tag ${p.kind}`}>{p.kind}</span>
        {foldPath(p, open).map((s, i) => (
          <span key={i}>{i > 0 && <span className="sep" aria-hidden>→</span>}
            {"label" in s ? s.label : <button className="link small" onClick={() => setOpen(true)}
                                              aria-label={`Show the ${s.more} folded steps`}>… {s.more} more</button>}</span>
        ))}
      </div>
      {p.text && <div className="st-path-text"><NameText text={p.text} /></div>}
      {graph && <Link className="small" to={graph} title="Show this path on the story's graph">On the graph ›</Link>}
    </li>
  );
}

/** Every call path the analysis found (§8.2), under the function it starts from, with what changes for whoever runs
 * it; a path drawn as a flow links to it on the graph. */
function CallPaths({ sr, detail }: { sr: StoryReading; detail: StoryDetail }) {
  const ws = useWs(), st = detail.story;
  if (!sr.paths.length) return null;
  const groups = byEntry(sr.paths);
  const graph = (p: CallPath) => {
    const i = p.flow ? st.flows.indexOf(p.flow) : -1;
    return i < 0 || !detail.graph ? null
      : ws.link({ ...ws.addr, place: { kind: "story", sid: st.id, view: "graph" }, flow: i + 1 });
  };
  return (
    <section aria-labelledby="st-paths">
      <h3 id="st-paths">Call paths <span className="muted small">{sr.paths.length}</span></h3>
      {groups.map((g, i) => (
        <details key={g.label + i} className="st-entry" open={i === 0 || sr.paths.length <= 8}>
          <summary>{g.entry ? "From the entry point " : "From "}<b className="mono">{g.label}</b>
            <span className="muted small"> {g.paths.length} path{g.paths.length === 1 ? "" : "s"}</span></summary>
          <ul className="st-paths">{g.paths.map((p, j) => <PathRow key={j} p={p} graph={graph(p)} />)}</ul>
        </details>
      ))}
    </section>
  );
}

/** Each changed function's code, definitions first (§6.3); opened one at a time. */
function Code({ sr, detail }: { sr: StoryReading; detail: StoryDetail }) {
  const ws = useWs();
  const [open, setOpen] = useState<Set<string>>(new Set());
  const nodes = new Map(detail.board.nodes.map((n) => [n.id, n]));
  const fns = codeOrder(sr.where, sr.contracts);
  if (!fns.length) return null;
  const toggle = (id: string, on: boolean) => setOpen((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n; });
  return (
    <section aria-labelledby="st-code">
      <h3 id="st-code">Code</h3>
      {fns.map((f) => {
        const node = nodes.get(f.node), file = sr.where.find((w) => w.functions.includes(f));
        return (
          <details key={f.node} className="st-fn" onToggle={(e) => toggle(f.node, (e.target as HTMLDetailsElement).open)}>
            <summary><b className="mono">{f.label}</b> <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
              {f.cl !== null && <span className="ws-chip">CL {f.cl}</span>}{file && <span className="muted small mono"> {file.path}</span>}</summary>
            {open.has(f.node) && (node?.path && node.range ? <FunctionCode node={node} board={detail.board} />
              : file?.depot ? <Link to={ws.link(ws.opened({ file: file.depot, line: f.line }))}>Open {file.path}</Link>
                : <p className="muted small">No code for {f.label} in this review.</p>)}
          </details>
        );
      })}
    </section>
  );
}

/** A story in layout B (spec 2026-10-07-review-reading §6): what it does, Before → after beside Where and its call
 * paths on the left, its To check pinned on the right; its code and questions below. */
export default function StoryTiles({ detail, sr }: { detail: StoryDetail; sr: StoryReading }) {
  const ws = useWs(), d = ws.data, st = detail.story;
  const suggested = st.check ?? [], questions = st.questions ?? [];
  return (
    <div className="ov2 st-tiles">
      <div className="ov2-left">
        <section aria-labelledby="st-what">
          <h3 id="st-what">What it does</h3>
          <p>{st.text_source === "llm" && <span className="ai-label">AI</span>}<NameText text={st.purpose || st.summary} />
            {sr.place_text && <span className="st-place"> {sr.place_text}</span>}</p>
          {st.kind === "unsorted" && <StoryWhy detail={detail} />}
        </section>
        {st.kind === "mechanical" ? <MechanicalStory detail={detail} /> : st.kind === "tests" ? <TestsStory detail={detail} /> : <>
          <ContractAndWhere sr={sr} />
          <CallPaths sr={sr} detail={detail} />
          <Code sr={sr} detail={detail} />
        </>}
        <section aria-labelledby="ws-talk" className="ws-talk">
          <h3 id="ws-talk">Questions and comments</h3>
          {questions.length > 0 && <ul className="st-questions">{questions.map((q, k) => (
            <li key={k}><span className="ai-label">AI</span><NameText text={q} /></li>))}</ul>}
          <Comments reviewId={d.id} comments={d.comments} kind="story" anchor={{ id: st.id }} onChange={d.loadComments} compact />
        </section>
      </div>
      <aside className="ov2-right" aria-label="What to check in this story">
        <CheckTile groups={[{ label: null, checks: sr.checks }]} ofTotal footer={suggested.length > 0 && (
          <div className="st-suggested"><h4><span className="ai-label">AI</span>The strong model also suggests</h4>
            <ul>{suggested.map((c, k) => <li key={k}><NameText text={c} /></li>)}</ul></div>
        )} />
      </aside>
    </div>
  );
}
```

`frontend/src/workspace/workspace.css` (diff):

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 1a3f294..fab24e1 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -595,3 +595,41 @@ a.ws-chip { text-decoration: none; }
   .ov2 { grid-template-columns: minmax(0, 1fr); }
   .ov2-right { order: -1; position: static; max-height: none; }
 }
+.st-page { max-width: 1280px; margin: 0 auto; }
+.st-crumb { margin: 0 0 4px; font-size: 13px; }
+.st-crumb a { text-decoration: none; font-weight: 600; }
+.st-tiles .ov2-left > section { margin: 0 0 22px; }
+.st-tiles .ov2-left h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 0 0 8px; }
+.st-place { color: var(--muted); }
+.st-pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin: 0 0 22px; }
+.st-contracts { list-style: none; margin: 0; padding: 0; font-size: 13px; }
+.st-contract { padding: 5px 0; border-top: 1px solid var(--line); }
+.st-contract:first-child { border-top: 0; }
+.st-contract button { margin-left: 8px; }
+.st-sig { margin-top: 4px; font-size: 12px; }
+.st-sig .del { color: var(--del-ink); } .st-sig .add { color: var(--add-ink); }
+.st-sig mark { background: var(--chg-bg); color: inherit; border-radius: 2px; }
+.st-names { margin: 4px 0 0; padding-left: 18px; font-size: 12px; }
+.st-dir + .st-dir { margin-top: 8px; }
+.st-dir-name { font-size: 12px; color: var(--muted); }
+.st-file { margin: 2px 0 0 12px; font-size: 13px; }
+.st-file ul { list-style: none; margin: 0; padding: 0 0 0 14px; }
+.st-file li { display: flex; gap: 8px; align-items: baseline; padding: 1px 0; }
+.st-file a { text-decoration: none; }
+.st-entry { margin: 0 0 8px; }
+.st-entry > summary { cursor: pointer; font-size: 13px; }
+.st-paths { list-style: none; margin: 4px 0 0; padding: 0 0 0 14px; }
+.st-path { padding: 5px 0; border-top: 1px solid var(--line); font-size: 13px; }
+.st-path:first-child { border-top: 0; }
+.st-steps { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px; font-size: 12px; }
+.st-steps .bd-tag { margin-right: 6px; }
+.st-steps .sep { color: var(--muted); padding: 0 5px; }
+.st-path-text { margin-top: 2px; }
+.st-fn { border-top: 1px solid var(--line); padding: 5px 0; }
+.st-fn > summary { cursor: pointer; font-size: 13px; }
+.st-questions { margin: 0 0 8px; padding-left: 18px; font-size: 14px; }
+.st-suggested { margin-top: 10px; font-size: 13px; }
+.st-suggested h4 { margin: 0 0 4px; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: none; letter-spacing: 0; }
+.st-suggested ul { margin: 0; padding-left: 18px; }
+.st-tiles .cnt { font: 11px var(--mono); } .st-tiles .cnt .p { color: var(--ok); } .st-tiles .cnt .m { color: var(--bad); }
+.bd-tag.call { background: var(--gap-bg); color: var(--ink); }
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd frontend && npx vitest run src/reading/story.test.ts`
Expected: PASS: `Tests 7 passed (7)`

Run: `cd frontend && npm run build && npx playwright test e2e/ai.spec.ts e2e/mention.spec.ts e2e/workspace-pages.spec.ts e2e/workspace-reading.spec.ts e2e/workspace-story.spec.ts e2e/workspace-tier1.spec.ts`
Expected: PASS: `42 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `606 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 161 passed (161)`; Playwright `1 failed, 98 passed` (in the replay, the first run's failures were timeouts under load; `npx playwright test --last-failed` then gave `1 passed`)

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/ai.spec.ts frontend/e2e/mention.spec.ts frontend/e2e/workspace-pages.spec.ts frontend/e2e/workspace-reading.spec.ts frontend/e2e/workspace-story.spec.ts frontend/e2e/workspace-tier1.spec.ts frontend/src/reading/story.test.ts frontend/src/reading/story.ts frontend/src/workspace/StoryPage.tsx frontend/src/workspace/StoryTiles.tsx frontend/src/workspace/workspace.css
git commit -m "feat(ui): a story page reads from its thread: what it does, before → after beside where, every call path, and its own To check pinned"
```

### Task 12: The rail, the Index and old addresses

Spec §11. With a reading, the rail lists the overview (with its headline), each thread with its stories in reading order (an Unsorted story marked "Needs a person to place it"), Tests, a divider, Possibly missed (the overview's To check) and the Index. The Index (`/i/cls`, `/i/files`, `/i/checks`, `/i/map`) holds what the rail no longer lists, as tabs; a cluster opens on the Map tab. A story's breadcrumb is its thread; a CL's is CLs, a finding's Checks, a cluster's Map. Old addresses land: `#files`, `#findings`, `#changeset` and `#map` redirect to the Index; a finding opens its story (or the overview) with its row lit (`?check=`), and the row's Details link opens the finding page (`?details=1`).

**Files:**
- Test: `frontend/e2e/ai.spec.ts`
- Test: `frontend/e2e/mention.spec.ts`
- Test: `frontend/e2e/theme.spec.ts`
- Test: `frontend/e2e/workspace-detail.spec.ts`
- Test: `frontend/e2e/workspace-graph.spec.ts`
- Test: `frontend/e2e/workspace-legacy.spec.ts`
- Test: `frontend/e2e/workspace-map-stories.spec.ts`
- Test: `frontend/e2e/workspace-pages.spec.ts`
- Test: `frontend/e2e/workspace-reading.spec.ts`
- Test: `frontend/e2e/workspace-story.spec.ts`
- Test: `frontend/e2e/workspace-tier1.spec.ts`
- Test: `frontend/e2e/workspace.spec.ts`
- Test: `frontend/src/workspace/address.test.ts`
- Test: `frontend/src/workspace/crumbs.test.ts`
- Test: `frontend/src/workspace/legacy.test.ts`
- Modify: `frontend/src/reading/checks.ts`
- Modify: `frontend/src/workspace/CheckList.tsx`
- Modify: `frontend/src/workspace/FindingPage.tsx`
- Create: `frontend/src/workspace/IndexPage.tsx`
- Modify: `frontend/src/workspace/Overview.tsx`
- Modify: `frontend/src/workspace/Rail.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/address.ts`
- Modify: `frontend/src/workspace/crumbs.ts`
- Modify: `frontend/src/workspace/legacy.ts`
- Modify: `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: Tasks 9–11.
- Produces: `address.ts`: `Place` kind `index`, `INDEX_TABS`, `IndexTab`, `Address.check`, `Address.details`; `crumbs.ts`: `CrumbContext.threadOf`, `INDEX_LABEL`; `legacy.indexFor(hash) -> Place | null`;
  `checks.ts`: `CHECK_ORDER`; `CheckTile({ groups, ofTotal, footer, id })` (lit from the address); `workspace/IndexPage.tsx` (`IndexTabs`, default `IndexPage({ tab, cid })`).

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/ai.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/ai.spec.ts b/frontend/e2e/ai.spec.ts
index 42e66e9..cdb7268 100644
--- a/frontend/e2e/ai.spec.ts
+++ b/frontend/e2e/ai.spec.ts
@@ -83,7 +83,7 @@ test.describe("with an AI", () => {
     const findings: { id: string; severity: string }[] = await (await page.request.get(`/api/reviews/${rid}/findings`)).json();
     const high = findings.find((f) => f.severity === "high")!;
     expect(high, "the fixture has a high finding").toBeTruthy();
-    await page.goto(`${base}/f/${high.id}`);
+    await page.goto(`${base}/f/${high.id}?details=1`);
     const ai = page.getByRole("region", { name: "AI analysis" });
     await expect(ai).toContainText("uart_send can now return -2, and logger_flush drops it.", { timeout: 30_000 });
     await expect(ai.locator(".ai-label")).toBeVisible();
@@ -95,10 +95,10 @@ test.describe("with an AI", () => {
     const findings = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as { id: string; title: string }[];
     const errors = findings.find((f) => f.title.startsWith("uart_send now writes Uart::errors"))!;
     const tx = findings.find((f) => f.title.startsWith("uart_send now writes Stats::tx"))!;
-    await page.goto(`${base}/f/${errors.id}`);
+    await page.goto(`${base}/f/${errors.id}?details=1`);
     await expect(page.locator(".ws-finding h2 .badge")).toHaveText("high");
     await expect(page.locator(".ws-verdict")).toContainText("AI: hazard — uart_errors assumes only uart_init writes Uart::errors.");
-    await page.goto(`${base}/f/${tx.id}`);
+    await page.goto(`${base}/f/${tx.id}?details=1`);
     await expect(page.locator(".ws-finding h2 .badge")).toHaveText("info");
     await expect(page.locator(".ws-verdict")).toContainText("AI: no clear hazard — Nothing else depends on the value it writes.");
     await page.goto(`${base}/s/S1?view=graph`);                              // a story's flows are on its graph
@@ -109,8 +109,8 @@ test.describe("with an AI", () => {
 
   test("✦ Summarise sums up a file in its diff", async ({ page }) => {
     await startReview(page);
-    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
-    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Files" }).click();
+    await page.getByRole("link", { name: "Open uart.c's diff" }).click();
     const panel = page.getByRole("complementary", { name: "Code: uart.c" });
     await panel.getByRole("button", { name: /Summarise/ }).click();
     await expect(panel).toContainText("This file now counts transmit errors.", { timeout: 30_000 });
```

`frontend/e2e/mention.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/mention.spec.ts b/frontend/e2e/mention.spec.ts
index 76ef497..075d383 100644
--- a/frontend/e2e/mention.spec.ts
+++ b/frontend/e2e/mention.spec.ts
@@ -5,8 +5,8 @@ const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with t
 
 /** Open uart.c's diff in the detail panel and start a comment on its new `return -2;` line. */
 async function commentOnReturn(page: Page): Promise<{ viewer: Locator; box: Locator }> {
-  await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
-  await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+  await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Files" }).click();
+  await page.getByRole("link", { name: "Open uart.c's diff" }).click();
   const viewer = page.getByRole("complementary", { name: "Code: uart.c" });
   await viewer.getByRole("button", { name: "Stacked" }).click();
   await viewer.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
@@ -52,7 +52,7 @@ test.describe("with an AI", () => {
     };
     const answer = "logger_flush drops the -2 that uart_send now returns.";
 
-    await page.goto(`${base}/f/F1`);
+    await page.goto(`${base}/f/F1?details=1`);
     const finding = page.locator(".ws-finding");
     await ask(finding.locator("#ws-ai").locator(".."), "why is this risky for the logger?");
     await expect(finding.locator(".comment", { hasText: "@tortoise why is this risky for the logger?" })).toBeVisible();
```

`frontend/e2e/theme.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/theme.spec.ts b/frontend/e2e/theme.spec.ts
index 9720211..3c8fc24 100644
--- a/frontend/e2e/theme.spec.ts
+++ b/frontend/e2e/theme.spec.ts
@@ -19,7 +19,7 @@ const CHECKS = [
   ".ws-crumbs a",                  // a breadcrumb
   ".bd-toolbar .bd-ibtn",          // a graph button
   ".topbar a",                     // app chrome link
-  ".ws-rail .bd-pill.high",        // a high-risk pill
+  ".ws-rail .ct-headline",         // what to act on, in the rail
   ".ws-head .ct-headline",         // what to act on
 ];
 
```

`frontend/e2e/workspace-detail.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-detail.spec.ts b/frontend/e2e/workspace-detail.spec.ts
index 897cb19..b2a7a54 100644
--- a/frontend/e2e/workspace-detail.spec.ts
+++ b/frontend/e2e/workspace-detail.spec.ts
@@ -6,10 +6,10 @@ import { expectIconsOnly, expectNamed, expectNoNodeIds, startReview } from "./he
 test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
-  test("a file from the rail opens its diff; ✕ closes it", async ({ page }) => {
+  test("a file from the Index opens its diff; ✕ closes it", async ({ page }) => {
     const base = await startReview(page);
-    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
-    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Files" }).click();
+    await page.getByRole("link", { name: "Open uart.c's diff" }).click();
     await expect(page).toHaveURL(/\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c$/);
     const panel = page.getByRole("complementary", { name: "Code: uart.c" });
     await expect(panel.locator(".ws-detail-path")).toHaveText("//fixture/driver/uart.c");
@@ -19,7 +19,7 @@ test.describe("desktop", () => {
     await expect(panel.locator(".bd-gap")).toHaveCount(0);
     await expectNamed(page);
     await panel.getByRole("link", { name: "Close the code" }).click();
-    await expect(page).toHaveURL(new RegExp(`${base}$`));
+    await expect(page).toHaveURL(new RegExp(`${base}/i/files$`));
     await expect(page.locator(".ws-detail")).toHaveCount(0);
   });
 
@@ -66,8 +66,8 @@ test.describe("desktop", () => {
 
   test("the diff colours added lines, highlights code and fills annotations, outside any graph", async ({ page }) => {
     await startReview(page);
-    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
-    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Files" }).click();
+    await page.getByRole("link", { name: "Open uart.c's diff" }).click();
     const file = page.getByRole("complementary", { name: "Code: uart.c" });
     const css = (sel: string, prop: string) => file.locator(sel).first().evaluate((e, p) => getComputedStyle(e).getPropertyValue(p), prop);
     const clear = "rgba(0, 0, 0, 0)";
@@ -78,8 +78,8 @@ test.describe("desktop", () => {
 
   test("a line comment in a file's diff shows in that function's code", async ({ page }) => {
     const base = await startReview(page);
-    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
-    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Files" }).click();
+    await page.getByRole("link", { name: "Open uart.c's diff" }).click();
     const file = page.getByRole("complementary", { name: "Code: uart.c" });
     await file.getByRole("button", { name: "Stacked" }).click();
     await file.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
@@ -94,8 +94,8 @@ test.describe("desktop", () => {
 
   test("one changelist's diff keeps the comments made on it", async ({ page }) => {
     await startReview(page);
-    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
-    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Files" }).click();
+    await page.getByRole("link", { name: "Open uart.c's diff" }).click();
     const file = page.getByRole("complementary", { name: "Code: uart.c" });
     await expect(file.locator(".act")).toContainText("edit");
     await file.getByRole("button", { name: "Stacked" }).click();
@@ -113,8 +113,8 @@ test.describe("desktop", () => {
   test("the diff goes side by side when the panel is wide enough, until the reader picks", async ({ page }) => {
     await page.addInitScript(() => localStorage.setItem("ct.ws.detailW", "600"));
     await startReview(page);
-    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
-    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Files" }).click();
+    await page.getByRole("link", { name: "Open uart.c's diff" }).click();
     const panel = page.getByRole("complementary", { name: "Code: uart.c" });
     await expect(panel.getByRole("button", { name: "Stacked" })).toHaveAttribute("aria-pressed", "true");
     const drag = async (dx: number) => {
@@ -151,7 +151,7 @@ test.describe("desktop", () => {
 
   test("a To check row opens its file at its line, folded away or not", async ({ page }) => {
     await startReview(page);
-    await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Go to the overview" }).click();
     await page.getByRole("region", { name: "To check" }).getByRole("link", { name: "Open driver/uart.c at line 8" }).click();   // outside the hunks
     await expect(page.getByRole("complementary", { name: "Code: uart.c" }).locator('.focus[data-n="8"]')).toBeVisible();
   });
```

`frontend/e2e/workspace-graph.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-graph.spec.ts b/frontend/e2e/workspace-graph.spec.ts
index 320e891..0c54466 100644
--- a/frontend/e2e/workspace-graph.spec.ts
+++ b/frontend/e2e/workspace-graph.spec.ts
@@ -27,8 +27,10 @@ async function offset(canvas: ReturnType<Page["locator"]>) {
 test.describe("the wheel", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
-  test("over the whole change's map a plain wheel scrolls the page; Shift pans it; the full graph pans on the wheel", async ({ page }) => {
+  test("over the Index's map a plain wheel scrolls the page; Shift pans it; the full graph pans on the wheel", async ({ page }) => {
+    await page.setViewportSize({ width: 1440, height: 560 });              // the map runs past the page's foot
     const base = await startReview(page);
+    await page.goto(`${base}/i/map`);
     const map = page.locator(".ws-mapgraph .bd-canvas"), scroller = page.locator(".ws-page").first();
     await expect(map.locator(".bd-node").first()).toBeVisible();
     await page.locator(".ws-mapgraph").evaluate((e) => e.scrollIntoView({ block: "center" }));
@@ -64,6 +66,7 @@ test.describe("desktop", () => {
 
   test("the review's graph: open full graph, select and deselect a node, flows keep their controls", async ({ page }) => {
     const base = await startReview(page);
+    await page.goto(`${base}/i/map`);
     await page.getByRole("link", { name: "Open the full graph" }).click();
     await expect(page).toHaveURL(new RegExp(`${base}\\?view=graph$`));
     await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Graph");
@@ -82,13 +85,12 @@ test.describe("desktop", () => {
     await expectNamed(page);
   });
 
-  test("a file from the rail highlights its functions on the graph and never refilters it", async ({ page }) => {
+  test("a file opened over the graph highlights its functions and never refilters it", async ({ page }) => {
     const base = await startReview(page);
     await page.goto(`${base}?view=graph`);
     await expect(page.locator(".bd-node").first()).toBeVisible();
     const count = await page.locator(".bd-node").count();
-    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
-    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
+    await page.goto(`${base}?view=graph&open=${encodeURIComponent("file://fixture/driver/uart.c")}`);
     await expect(page.locator(".bd-node.lit").first()).toBeVisible();
     await expect(page.locator(".bd-node")).toHaveCount(count);
   });
```

`frontend/e2e/workspace-legacy.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-legacy.spec.ts b/frontend/e2e/workspace-legacy.spec.ts
index dcf45a4..f557b79 100644
--- a/frontend/e2e/workspace-legacy.spec.ts
+++ b/frontend/e2e/workspace-legacy.spec.ts
@@ -11,7 +11,7 @@ test.describe("desktop", () => {
     const rid = base.split("/")[2];
     const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
     const [nid, sid] = Object.entries(ss.node_story as Record<string, string>)[0];
-    for (const [old, now] of [["/files", "#files"], ["/findings", "#findings"], ["/cls", "#changeset"], ["/overview", "#map"],
+    for (const [old, now] of [["/files", "/i/files"], ["/findings", "/i/checks"], ["/cls", "/i/cls"], ["/overview", "/i/map"],
                               ["/board", "?view=graph"]]) {
       await page.goto(`${base}${old}`);
       await expect(page).toHaveURL(new RegExp(`${base}${now.replace("?", "\\?")}$`));
@@ -56,7 +56,7 @@ test.describe("a large change", () => {
     // a reader who leaves before the server answers stays where they went
     await page.route(`**/api/reviews/${rid}/locate**`, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.continue(); });
     await page.goto(base);
-    await expect(page.getByRole("region", { name: "The map" })).toBeVisible();
+    await expect(page.getByRole("region", { name: "To check" })).toBeVisible();
     await page.evaluate((u) => { history.pushState(null, "", u); dispatchEvent(new PopStateEvent("popstate")); }, `${base}?node=${nid}`);
     await expect(page.locator("main.page")).toContainText("Loading");
     await page.goBack();
```

`frontend/e2e/workspace-map-stories.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-map-stories.spec.ts b/frontend/e2e/workspace-map-stories.spec.ts
index e088d8c..41bc84d 100644
--- a/frontend/e2e/workspace-map-stories.spec.ts
+++ b/frontend/e2e/workspace-map-stories.spec.ts
@@ -30,7 +30,7 @@ test.describe("one board", () => {
     await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).hover();
     await expect.poll(() => ids(page, "instory")).toEqual(s1);
     expect((await ids(page, "offstory")).length).toBe(drawn.length - s1.length);
-    await page.mouse.move(5, 300);                                      // off the rail
+    await page.locator(".ws-head h1").hover();                         // off the rail
     await expect.poll(() => ids(page, "offstory")).toEqual([]);
 
     const tagged = s1.find((n) => changed.includes(n))!;
```

`frontend/e2e/workspace-pages.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-pages.spec.ts b/frontend/e2e/workspace-pages.spec.ts
index 72711a6..0af5dd4 100644
--- a/frontend/e2e/workspace-pages.spec.ts
+++ b/frontend/e2e/workspace-pages.spec.ts
@@ -8,16 +8,16 @@ test.describe("desktop", () => {
 
   test("a finding: to its story and back, on the graph, evidence opens the diff at its line", async ({ page }) => {
     const base = await startReview(page);
-    await page.goto(`${base}/f/F4`);
+    await page.goto(`${base}/f/F4?details=1`);
     await expect(page.locator(".ws-finding h2")).toContainText("uart_send: new return value(s) -2");
     await expect(page.getByRole("region", { name: "AI analysis" })).toContainText("AI analysis unavailable.");
     await page.getByRole("link", { name: /^Go to story S1/ }).first().click();
     await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
     await page.goBack();
-    await expect(page).toHaveURL(new RegExp(`${base}/f/F4$`));
+    await expect(page).toHaveURL(new RegExp(`${base}/f/F4\\?details=1$`));
 
     await page.getByRole("link", { name: "Open service/logger.c at line 12" }).first().click();
-    await expect(page).toHaveURL(/open=file%3A%2F%2Ffixture%2Fservice%2Flogger\.c%3A12$/);
+    await expect(page).toHaveURL(/open=file%3A%2F%2Ffixture%2Fservice%2Flogger\.c%3A12&details=1$/);
     await expect(page.getByRole("complementary", { name: "Code: logger.c" }).locator('[data-n="12"]').first()).toBeVisible();
     await page.goBack();
 
@@ -27,7 +27,7 @@ test.describe("desktop", () => {
     await page.goBack();
 
     await page.getByRole("link", { name: /^Next finding: F5/ }).click();
-    await expect(page).toHaveURL(new RegExp(`${base}/f/F5$`));
+    await expect(page).toHaveURL(new RegExp(`${base}/f/F5\\?details=1$`));
     await page.getByRole("button", { name: "mark acknowledged" }).click();
     await expect(page.locator(".ws-finding .ws-badge")).toHaveText("acknowledged");
     await expectNoNodeIds(page);
@@ -96,7 +96,9 @@ test.describe("desktop", () => {
     });
     await page.goto(`${base}/cl/102`);
     await expect(page.locator(".ws-finding h2")).toHaveText("CL 102 · uart: flags field");
-    await expect(page.locator(".ws-rail").getByRole("link", { name: "Open CL 102" })).toContainText("uart: flags field");
+    await page.goto(`${base}/i/cls`);
+    await expect(page.getByRole("link", { name: "Open CL 102" })).toContainText("uart: flags field");
+    await page.goto(`${base}/cl/102`);
     const desc = page.locator(".ws-desc");
     await expect(desc.locator("li")).toHaveCount(2);
     await expect(desc.locator("li code")).toHaveText("flags");
@@ -109,7 +111,8 @@ test.describe("desktop", () => {
 
   test("a changelist: its Swarm card, its files filtered to it, the stories and findings drawn from it", async ({ page }) => {
     const base = await startReview(page);
-    await page.locator(".ws-rail").getByRole("link", { name: "Open CL 102" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: CLs" }).click();
+    await page.getByRole("link", { name: "Open CL 102" }).click();
     await expect(page).toHaveURL(new RegExp(`${base}/cl/102$`));
     await expect(page.locator(".ws-finding h2")).toHaveText("CL 102 · uart: add flags field; hal_write takes unsigned reg");
     await expect(page.getByRole("region", { name: "Swarm" })).toContainText("No Swarm review.");
```

`frontend/e2e/workspace-reading.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-reading.spec.ts b/frontend/e2e/workspace-reading.spec.ts
index 52b3ce5..4143b5b 100644
--- a/frontend/e2e/workspace-reading.spec.ts
+++ b/frontend/e2e/workspace-reading.spec.ts
@@ -24,7 +24,7 @@ test.describe("desktop", () => {
   test("the overview tells the change as threads, how they connect and what to check", async ({ page }) => {
     await startReview(page, FOUR);
     const left = page.locator(".ov2-left");
-    await expect(left.locator("h2")).toHaveText(["The change as a whole", "How the threads connect", "Threads", /^The map/, "Discussion"]);
+    await expect(left.locator("h2")).toHaveText(["The change as a whole", "How the threads connect", "Threads", "Discussion"]);
     await expect(left.locator(".ws-lead")).toHaveText("3 threads: A and B: both run inside main; B and C: nothing besides arriving in CL 104.");
     const conn = page.locator(".ov-conn");
     await expect(conn.locator(".ov-box")).toHaveCount(3);
@@ -103,6 +103,49 @@ test.describe("desktop", () => {
     await expect(page).toHaveURL(/\/s\/S1\?view=graph&flow=1/);
     await expect(page.locator(".bd-node").first()).toBeVisible();
   });
+  test("the rail: the overview, each thread with its stories in reading order, what may be missed and the Index", async ({ page }) => {
+    const base = await startReview(page, FOUR);
+    const rail = page.locator(".ws-rail");
+    await expect(rail.getByRole("link", { name: "Go to the overview" })).toContainText("Medium risk · rules only");
+    await expect(rail.locator(".ws-thread h3")).toHaveText(["A hal_write in hal5", "B logger_init in service", "C svc::Engine::step in cpp1"]);
+    await expect(rail.locator(".ws-thread").first().getByRole("link", { name: /^Go to story/ })).toHaveCount(2);
+    await expect(rail.locator(".ws-thread").first().getByRole("link").nth(1)).toHaveAccessibleName(/^Go to story S1/);
+    await expect(rail.locator(".ws-missed .ck-count")).toHaveText("6 open");
+    await rail.getByRole("link", { name: /^Go to story S1/ }).click();
+    const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
+    await expect(crumbs).toContainText("Thread A");
+    await rail.getByRole("link", { name: "Open the Index: Files" }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}/i/files$`));
+    await expect(page.getByRole("tab", { name: /^Files/ })).toHaveAttribute("aria-selected", "true");
+    await page.getByRole("link", { name: "Open logger.c's diff" }).click();
+    await expect(page.getByRole("complementary", { name: "Code: logger.c" })).toBeVisible();
+    await page.getByRole("tab", { name: /^CLs/ }).click();
+    await page.getByRole("link", { name: "Open CL 104" }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}/cl/104$`));
+    await expect(crumbs).toContainText("CLs");
+    await rail.getByRole("link", { name: /^Go to what may have been missed/ }).click();
+    await expect(page.getByRole("region", { name: "To check" })).toBeInViewport();
+    await expectNamed(page);
+  });
+
+  test("old addresses: a finding opens its story with its row lit, #map the Index's map", async ({ page }) => {
+    const base = await startReview(page, FOUR);
+    const findings = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as { id: string; title: string; severity: string }[];
+    const sig = findings.find((f) => f.title === "hal_write: signature changed")!;
+    await page.goto(`${base}/f/${sig.id}`);
+    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?check=${sig.id}$`));
+    const lit = page.getByRole("region", { name: "To check" }).locator(".ck-row.lit");
+    await expect(lit).toContainText("hal_write: signature changed");
+    await lit.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();     // the finding's own page stays one click away
+    await expect(page).toHaveURL(new RegExp(`${base}/f/${sig.id}\\?details=1$`));
+    await expect(page.locator(".ws-finding h2")).toContainText("hal_write: signature changed");
+    const info = findings.find((f) => f.severity === "info")!;                      // no row for it: its own page
+    await page.goto(`${base}/f/${info.id}`);
+    await expect(page.locator(".ws-finding h2")).toBeVisible();
+    await page.goto(`${base}#map`);
+    await expect(page).toHaveURL(new RegExp(`${base}/i/map$`));
+    await expect(page.getByRole("region", { name: "The map" })).toBeVisible();
+  });
 });
 
 test.describe("phone", () => {
@@ -111,7 +154,7 @@ test.describe("phone", () => {
 
   test("To check comes first, folded to its count, and the connections are sentences", async ({ page }) => {
     await startReview(page, FOUR);
-    await page.getByRole("link", { name: "Go to the whole change" }).click();
+    await page.getByRole("link", { name: "Go to the overview" }).click();
     const check = page.locator("details.ck-tile");
     await expect(check).not.toHaveAttribute("open");
     await expect(check.locator("summary .ck-count")).toHaveText("6 open");
```

`frontend/e2e/workspace-story.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-story.spec.ts b/frontend/e2e/workspace-story.spec.ts
index 4c353ef..4bb5885 100644
--- a/frontend/e2e/workspace-story.spec.ts
+++ b/frontend/e2e/workspace-story.spec.ts
@@ -28,7 +28,7 @@ test.describe("desktop", () => {
 
   test("names in text read as text: the sentence's colour and a faint dotted underline, the accent on hover", async ({ page }) => {
     const base = await startReview(page);
-    await page.goto(`${base}/f/F4`);
+    await page.goto(`${base}/f/F4?details=1`);
     const name = page.locator(".ws-where li .ws-name").first();
     await expect(name).toBeVisible();
     const look = () => name.evaluate((el) => {
@@ -72,7 +72,8 @@ test.describe("desktop", () => {
     await node(page, "uart_send").click();
     await expect(page).toHaveURL(/view=graph&flow=2&open=N\d+$/);
     const there = page.url();
-    await page.locator(".ws-rail").getByRole("link", { name: "Open CL 101" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: CLs" }).click();
+    await page.getByRole("link", { name: "Open CL 101" }).click();
     await expect(page).toHaveURL(new RegExp(`${base}/cl/101$`));
     await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
     await expect(page).toHaveURL(there);
@@ -80,10 +81,12 @@ test.describe("desktop", () => {
     await expect(page.locator(".ws-flow-pos")).toHaveText("flow 2 of 2");
   });
 
-  test("a review without stories (run before them) leaves Stories out of the rail", async ({ page }) => {
+  test("a review without stories or a reading (run before them) keeps the old rail and page", async ({ page }) => {
     const base = await startReview(page);
     await page.route(`**/api/reviews/${base.split("/")[2]}/stories`, (r) =>
       r.fulfill({ status: 404, json: { detail: "this review has no stories: re-run it" } }));
+    await page.route(`**/api/reviews/${base.split("/")[2]}/reading`, (r) =>
+      r.fulfill({ status: 404, json: { detail: "this review has no reading: re-run it" } }));
     await page.reload();
     await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to finding/ }).first()).toBeAttached();
     await expect(page.locator(".ws-rail").getByRole("button", { name: /^Stories/ })).toHaveCount(0);
@@ -184,13 +187,13 @@ test.describe("phone", () => {
   test("rail → story → detail sheet, each top bar naming the place", async ({ page }) => {
     await startReview(page);
     await page.getByRole("link", { name: /^Go to story S1/ }).click();
-    await expect(page.locator(".ws-phonebar")).toContainText("‹ Stories");
+    await expect(page.locator(".ws-phonebar")).toContainText("‹ Thread A");
     await page.getByRole("region", { name: "Where" }).getByRole("link", { name: /^Open uart_send in/ }).click();
     const bar = page.locator(".ws-detail .ws-phonebar");
     await expect(bar).toContainText("‹ Back");
     await expect(bar).toContainText("uart.c");
     await bar.getByRole("link", { name: "Close the code" }).click();
-    await expect(page.locator(".ws-centre .ws-phonebar")).toContainText("‹ Stories");
+    await expect(page.locator(".ws-centre .ws-phonebar")).toContainText("‹ Thread A");
     expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
   });
 });
```

`frontend/e2e/workspace-tier1.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-tier1.spec.ts b/frontend/e2e/workspace-tier1.spec.ts
index bae0528..cde7323 100644
--- a/frontend/e2e/workspace-tier1.spec.ts
+++ b/frontend/e2e/workspace-tier1.spec.ts
@@ -32,10 +32,10 @@ test.describe("stories formed by a strong model", () => {
     await expect(page.locator(".ws-head .ct-headline")).toHaveClass(/\bhazard\b/);
   });
 
-  test("the pieces it could not place are listed last, each with the check that failed", async ({ page }) => {
+  test("the pieces it could not place say so in the rail, each with the check that failed", async ({ page }) => {
     const base = await startReview(page);
-    const group = page.getByRole("region", { name: /^Stories/ }).locator(".ws-group").last();
-    await expect(group.locator("h3")).toHaveText("Needs a person to place these");
+    const s3 = page.locator(".ws-rail").getByRole("link", { name: /^Go to story S3/ });
+    await expect(s3.locator(".ws-row-sub")).toHaveText("Needs a person to place it");
     await page.goto(`${base}/s/S3`);
     const place = page.getByRole("region", { name: "Pieces to place" });
     await expect(place).toContainText("need a person to place them");
@@ -44,16 +44,16 @@ test.describe("stories formed by a strong model", () => {
 
   test("a finding shows the AI review: hazard red, needs review amber, with its citations as links", async ({ page }) => {
     const base = await startReview(page);
-    await page.goto(`${base}/f/F1`);
+    await page.goto(`${base}/f/F1?details=1`);
     const hazard = page.locator(".ws-verdict");
     await expect(hazard).toHaveClass(/hazard/);
     await expect(hazard).toContainText("AI review: hazard — logger_flush ignores the new -2, so a failed send goes unnoticed.");
     await hazard.getByRole("link", { name: "uart_send" }).click();               // a node id cited: its code opens
     await expect(page.getByRole("complementary", { name: /uart_send/ }).or(page.locator(".ws-detail"))).toBeVisible();
-    await page.goto(`${base}/f/F2`);
+    await page.goto(`${base}/f/F2?details=1`);
     await expect(page.locator(".ws-verdict")).toHaveClass(/needs_review/);
     await expect(page.locator(".ws-verdict")).toContainText("AI review: needs review —");
-    await page.goto(`${base}/f/F5`);
+    await page.goto(`${base}/f/F5?details=1`);
     const cited = page.locator(".ws-verdict").getByRole("link", { name: /^driver\/uart\.c:\d+$/ });
     await expect(cited).toBeVisible();                                            // a file:line cited: the diff opens there
   });
```

`frontend/e2e/workspace.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index 4d399fe..992544b 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -6,32 +6,23 @@ import { expectNamed, expectNoNodeIds, startReview } from "./helpers";
 test.describe("desktop", () => {
   test.use({ viewport: { width: 1440, height: 900 } });
 
-  test("the rail lists the review, its CLs, the stories drawn from them, findings and files", async ({ page }) => {
+  test("the rail lists the overview, the thread's stories, what may be missed and the Index", async ({ page }) => {
     const base = await startReview(page);
     const rail = page.locator(".ws-rail");
-    await expect(rail.locator(".ws-sec h2")).toHaveText([/Change set \(2 CLs\)/, /Stories \(from 2 CLs\)/, /Findings \(6\)/, /Files \(4\)/]);
-    await expect(rail.getByRole("link", { name: "Go to the whole change" })).toHaveAttribute("aria-current", "page");
+    await expect(rail.locator(".ws-sec h2")).toHaveText([/Threads \(1\)$/, "Index"]);
+    await expect(rail.getByRole("link", { name: "Go to the overview" })).toHaveAttribute("aria-current", "page");
     const home = (await rail.locator(".ws-home").boundingBox())!, first = (await rail.locator(".ws-sec-t").first().boundingBox())!;
     expect(first.y - (home.y + home.height)).toBeLessThan(12);               // sections follow on: the grip takes no room
+    await expect(rail.locator(".ws-index-row")).toHaveText(["CLs", "Files", "Checks", "Map"]);
     const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
-    await expect(s1.locator(".ws-chip")).toHaveText(["CL 101", "CL 102"]);     // CL 102's uart.h is used most by S1
-
-    // the CL filter lights the stories drawn from it and dims the rest; again clears it
-    const s2 = rail.getByRole("link", { name: /^Go to story S2/ });
-    await rail.getByRole("button", { name: "Highlight the stories drawn from CL 101" }).click();
-    await expect(s2).toHaveClass(/\bdim\b/);
-    await expect(s1).not.toHaveClass(/\bdim\b/);
-    await rail.getByRole("button", { name: "Show every story" }).click();
-    await expect(s2).not.toHaveClass(/\bdim\b/);
-
     await s1.click();
     await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
     await expect(s1).toHaveAttribute("aria-current", "page");
     const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
-    await expect(crumbs).toContainText("Stories");
+    await expect(crumbs).toContainText("Thread A");
     await expect(crumbs.locator("[aria-current=page]")).toContainText("uart_send can now return -2");
-    await crumbs.getByRole("link", { name: "Go to Stories" }).click();
-    await expect(page).toHaveURL(new RegExp(`${base}#stories$`));
+    await crumbs.getByRole("link", { name: "Go to Thread A" }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}$`));
     await page.goBack();
     await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
     await expectNoNodeIds(page);
@@ -41,7 +32,7 @@ test.describe("desktop", () => {
   test("the overview: the change as a whole, its one thread and what to check", async ({ page }) => {
     await startReview(page);
     const left = page.locator(".ov2-left");
-    await expect(left.locator("h2")).toHaveText(["The change as a whole", "How the threads connect", "Threads", /^The map/, "Discussion"]);
+    await expect(left.locator("h2")).toHaveText(["The change as a whole", "How the threads connect", "Threads", "Discussion"]);
     await expect(left.locator(".ws-lead")).toHaveText("One thread: hal_write in hal.");
     await expect(left).toContainText("One thread: all stories are connected by calls or shared data.");
     await expect(page.getByRole("region", { name: "To check" }).locator(".ck-row")).toHaveCount(5);
@@ -67,8 +58,8 @@ test.describe("desktop", () => {
   test("the rail keeps its closed sections and its width across a reload", async ({ page }) => {
     await startReview(page);
     const rail = page.locator(".ws-rail");
-    await rail.getByRole("button", { name: /^Findings/ }).click();
-    await expect(rail.getByRole("button", { name: /^Findings/ })).toHaveAttribute("aria-expanded", "false");
+    await rail.getByRole("button", { name: /^Threads/ }).click();
+    await expect(rail.getByRole("button", { name: /^Threads/ })).toHaveAttribute("aria-expanded", "false");
     const grip = rail.locator(".bd-resizer");
     const g = (await grip.boundingBox())!, w = (await rail.boundingBox())!.width;
     await page.mouse.move(g.x + g.width / 2, g.y + 200);
@@ -78,16 +69,14 @@ test.describe("desktop", () => {
     await expect.poll(async () => (await rail.boundingBox())!.width).toBeGreaterThan(w + 60);
     const wider = (await rail.boundingBox())!.width;
     await page.reload();
-    await expect(rail.getByRole("button", { name: /^Findings/ })).toHaveAttribute("aria-expanded", "false");
-    await expect(rail.getByRole("button", { name: /^Stories/ })).toHaveAttribute("aria-expanded", "true");
+    await expect(rail.getByRole("button", { name: /^Threads/ })).toHaveAttribute("aria-expanded", "false");
     expect(Math.abs((await rail.boundingBox())!.width - wider)).toBeLessThan(2);
   });
 
   test("the rail's grip straddles its border, clear of its scrollbar, and drags from there", async ({ page }) => {
-    await page.setViewportSize({ width: 1440, height: 420 });
+    await page.setViewportSize({ width: 1440, height: 300 });
     await startReview(page);
     const rail = page.locator(".ws-rail");
-    await rail.getByRole("button", { name: /^Files/ }).click();
     expect(await rail.evaluate((e) => { const s = e.querySelector(".ws-rail-scroll") ?? e; return s.scrollHeight > s.clientHeight; })).toBe(true);
     const r = (await rail.boundingBox())!, x = r.x + r.width + 3, y = r.y + r.height / 2;   // just past the border
     expect(await page.evaluate(([px, py]) => !!document.elementFromPoint(px, py)?.closest(".bd-resizer"), [x, y])).toBe(true);
@@ -130,7 +119,7 @@ test.describe("tablet", () => {
     await menu.focus();
     for (let i = 0; i < 4; i++) { await page.keyboard.press("Tab"); expect(await inRail()).toBe(false); }
     await menu.click();
-    await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).focus();
+    await page.locator(".ws-rail").getByRole("link", { name: "Go to the overview" }).focus();
     expect(await inRail()).toBe(true);
   });
 });
@@ -146,17 +135,18 @@ test.describe("phone", () => {
     await page.getByRole("link", { name: /^Go to story S1/ }).click();
     await expect(page.locator(".ws-rail")).toHaveCount(0);
     const bar = page.locator(".ws-phonebar");
-    await expect(bar).toContainText("‹ Stories");
+    await expect(bar).toContainText("‹ Thread A");
     await expect(bar).toContainText("S1");
-    await bar.getByRole("link", { name: "Back to Stories" }).click();
-    await expect(page).toHaveURL(new RegExp(`${base}#stories$`));
+    await bar.getByRole("link", { name: "Back to Thread A" }).click();
+    await expect(page).toHaveURL(new RegExp(`${base}$`));
     await expect(page.locator(".ws-rail")).toBeVisible();
     expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
   });
 
-  test("#map opens the whole change at its map, not the rail", async ({ page }) => {
+  test("#map opens the Index at its map, not the rail", async ({ page }) => {
     const base = await startReview(page);
     await page.goto(`${base}#map`);
+    await expect(page).toHaveURL(new RegExp(`${base}/i/map$`));
     await expect(page.getByRole("region", { name: "The map" })).toBeInViewport();
     await expect(page.locator(".ws-rail")).toHaveCount(0);
   });
@@ -165,8 +155,9 @@ test.describe("phone", () => {
 test.describe("a large change", () => {
   test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });
 
-  test("the whole change maps its parts; a part opens its page", async ({ page }) => {
+  test("the Index maps the change's parts; a part opens its page", async ({ page }) => {
     const base = await startReview(page, "201 202");
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Map" }).click();
     const map = page.getByRole("region", { name: "The map" });
     await expect(map.locator(".ov-block")).toHaveCount(7);
     await expect(map.getByRole("region", { name: "Layer drv" })).toContainText("drv/dma");
@@ -199,7 +190,7 @@ test.describe("a large change on a phone", () => {
 
   test("the map stacks the parts; a part opens with its place among them", async ({ page }) => {
     await startReview(page, "201 202");
-    await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).click();
+    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Map" }).click();
     const first = page.locator(".ov-block").first(), second = page.locator(".ov-block").nth(1);
     const a = (await first.boundingBox())!, b = (await second.boundingBox())!;
     expect(b.y).toBeGreaterThan(a.y + a.height - 1);                      // stacked, not side by side
```

`frontend/src/workspace/address.test.ts` (diff):

```diff
diff --git a/frontend/src/workspace/address.test.ts b/frontend/src/workspace/address.test.ts
index e40a842..e8cb196 100644
--- a/frontend/src/workspace/address.test.ts
+++ b/frontend/src/workspace/address.test.ts
@@ -1,5 +1,5 @@
 import { describe, expect, it } from "vitest";
-import { type Address, href, placeKey, readAddress, samePlace } from "./address";
+import { type Address, at, href, placeKey, readAddress, samePlace } from "./address";
 
 const q = (s: string) => new URLSearchParams(s);
 
@@ -66,3 +66,21 @@ describe("places", () => {
     expect(samePlace({ kind: "finding", fid: "F1" }, { kind: "finding", fid: "F2" })).toBe(false);
   });
 });
+
+describe("the Index and lit checks", () => {
+  it("reads and writes the Index's tabs", () => {
+    expect(readAddress("/i/map", q("")).place).toEqual({ kind: "index", tab: "map" });
+    expect(readAddress("/i/cls", q("")).place).toEqual({ kind: "index", tab: "cls" });
+    expect(readAddress("/i/elsewhere", q("")).place).toEqual({ kind: "unknown", path: "/i/elsewhere" });
+    expect(href("/r/7", at({ kind: "index", tab: "checks" }))).toBe("/r/7/i/checks");
+    expect(placeKey({ kind: "index", tab: "files" })).toBe("i:files");
+  });
+
+  it("carries the finding whose row to light, and asks for a finding's own page", () => {
+    expect(readAddress("/s/S1", q("check=F2")).check).toBe("F2");
+    expect(href("/r/7", at({ kind: "story", sid: "S1", view: "steps" }, { check: "F2" }))).toBe("/r/7/s/S1?check=F2");
+    expect(readAddress("/f/F2", q("details=1")).details).toBe(true);
+    expect(href("/r/7", at({ kind: "finding", fid: "F2" }, { details: true }))).toBe("/r/7/f/F2?details=1");
+    expect(readAddress("/f/F2", q("")).details).toBeUndefined();
+  });
+});
```

`frontend/src/workspace/crumbs.test.ts` (diff):

```diff
diff --git a/frontend/src/workspace/crumbs.test.ts b/frontend/src/workspace/crumbs.test.ts
index 7df3c17..1b18e82 100644
--- a/frontend/src/workspace/crumbs.test.ts
+++ b/frontend/src/workspace/crumbs.test.ts
@@ -37,6 +37,19 @@ describe("the breadcrumb", () => {
       { label: "Map", to: "/r/7#map" }, { label: "driver/uart", to: null }]);
   });
 
+  it("with a reading, puts a story under its thread and CLs, files, checks and the map under the Index", () => {
+    const r = { ...ctx, threadOf: (sid: string) => (sid === "S1" ? "Thread A" : null) };
+    const home = { label: "Review 7", to: "/r/7" };
+    expect(crumbs({ kind: "story", sid: "S1", view: "steps" }, r)).toEqual([home, { label: "Thread A", to: "/r/7" },
+      { label: "frame_pop writes pool->free from two threads…", handle: "S1", to: null }]);
+    expect(crumbs({ kind: "cluster", cid: "C1" }, r)).toEqual([home, { label: "Map", to: "/r/7/i/map" }, { label: "driver/uart", to: null }]);
+    expect(crumbs({ kind: "cl", cl: 101 }, r)).toEqual([home, { label: "CLs", to: "/r/7/i/cls" },
+      { label: "CL 101 · uart: count tx stats", to: null }]);
+    expect(crumbs({ kind: "finding", fid: "F2" }, r)).toEqual([home, { label: "Checks", to: "/r/7/i/checks" },
+      { label: "uart_send: new return value(s) -2", handle: "F2", to: null }]);
+    expect(crumbs({ kind: "index", tab: "files" }, r)).toEqual([home, { label: "Files", to: null }]);
+  });
+
   it("names a changelist without a description by number, and cuts a long one", () => {
     const c = { ...ctx, cls: [{ cl: 5, description: null }, { cl: 6, description: "  \n" },
                               { cl: 7, description: "uart: count tx stats, rx stats, framing errors and parity errors per port" }] };
```

`frontend/src/workspace/legacy.test.ts` (diff):

```diff
diff --git a/frontend/src/workspace/legacy.test.ts b/frontend/src/workspace/legacy.test.ts
index 779fd62..38a1ce0 100644
--- a/frontend/src/workspace/legacy.test.ts
+++ b/frontend/src/workspace/legacy.test.ts
@@ -1,5 +1,5 @@
 import { describe, expect, it } from "vitest";
-import { legacy } from "./legacy";
+import { indexFor, legacy } from "./legacy";
 
 const q = (s: string) => new URLSearchParams(s);
 const ctx = { base: "/r/7", nodeStory: { N9: "S1" } as Record<string, string>, oneBoard: true };
@@ -34,3 +34,11 @@ describe("old addresses", () => {
     expect(legacy("", q(""), ctx)).toBeNull();
   });
 });
+
+describe("the old sections' anchors", () => {
+  it("open the Index's tabs once the review has a reading", () => {
+    expect(["map", "findings", "changeset", "files", "stories", "x"].map(indexFor)).toEqual([
+      { kind: "index", tab: "map" }, { kind: "index", tab: "checks" }, { kind: "index", tab: "cls" }, { kind: "index", tab: "files" },
+      null, null]);
+  });
+});
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd frontend && npx vitest run src/workspace/address.test.ts src/workspace/crumbs.test.ts src/workspace/legacy.test.ts`
Expected: FAIL: `Tests 4 failed | 18 passed (22)`; the first error is `AssertionError: expected { kind: 'unknown', path: '/i/map' } to deeply equal { kind: 'index', tab: 'map' }`

Run: `cd frontend && npm run build && npx playwright test e2e/ai.spec.ts e2e/mention.spec.ts e2e/theme.spec.ts e2e/workspace-detail.spec.ts e2e/workspace-graph.spec.ts e2e/workspace-legacy.spec.ts e2e/workspace-map-stories.spec.ts e2e/workspace-pages.spec.ts e2e/workspace-reading.spec.ts e2e/workspace-story.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace.spec.ts`
Expected: FAIL: `npm run build fails with 9 type error(s)`; the first error is `src/workspace/address.test.ts(75,30): error TS2322: Type '"index"' is not assignable to type '"unknown" | "finding" | "story" | "cluster" | "cl" | "whole"'.`

- [ ] **Step 3: Implement**

`frontend/src/reading/checks.ts` (diff):

```diff
diff --git a/frontend/src/reading/checks.ts b/frontend/src/reading/checks.ts
index c63f6e8..dc01377 100644
--- a/frontend/src/reading/checks.ts
+++ b/frontend/src/reading/checks.ts
@@ -8,6 +8,9 @@ export const KIND_LABEL: Record<CheckKind, string> = {
   ask: "Ask the author", cleared: "No hazard",
 };
 
+/** The kinds in the order the list shows them (§7.1). */
+export const CHECK_ORDER: CheckKind[] = ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask"];
+
 /** Open unless someone marked it and its line has not changed since (§7.4). */
 export const isOpen = (k: Check, marks: Record<string, Mark>) => !marks[k.key] || marks[k.key].changed;
 
```

`frontend/src/workspace/CheckList.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/CheckList.tsx b/frontend/src/workspace/CheckList.tsx
index ced6cb8..9b16a8f 100644
--- a/frontend/src/workspace/CheckList.tsx
+++ b/frontend/src/workspace/CheckList.tsx
@@ -1,9 +1,10 @@
-import { type ReactNode, useState } from "react";
+import { type ReactNode, useEffect, useRef, useState } from "react";
 import { Link } from "react-router-dom";
 import { api } from "../api";
 import Comments from "../components/Comments";
 import { isOpen, KIND_LABEL, markLine, openCount, placeOf, splitChecks } from "../reading/checks";
 import type { Check } from "../reading/types";
+import { at } from "./address";
 import { useWs } from "./context";
 import { Ticks } from "./NameText";
 
@@ -21,10 +22,12 @@ function CheckRow({ k, lit }: { k: Check; lit: boolean }) {
     (marked ? api.unmarkCheck(d.id, k.key) : api.markCheck(d.id, k.key)).then(d.loadReading)
       .catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
   };
+  const li = useRef<HTMLLIElement>(null);
+  useEffect(() => { if (lit) li.current?.scrollIntoView({ block: "center" }); }, [lit]);
   const talks = d.comments.filter((c) => c.parent_id === null && c.anchor_kind === "check" && c.anchor.key === k.key).length;
-  const where = placeOf(k), at = `${k.path}${k.line ? ` at line ${k.line}` : ""}`;
+  const where = placeOf(k), place = `${k.path}${k.line ? ` at line ${k.line}` : ""}`;
   return (
-    <li className={`ck-row${marked ? " marked" : ""}${lit ? " lit" : ""}`} data-key={k.key} data-finding={k.finding ?? undefined}>
+    <li ref={li} className={`ck-row${marked ? " marked" : ""}${lit ? " lit" : ""}`} data-key={k.key} data-finding={k.finding ?? undefined}>
       {[{ kind: k.kind, text: k.text }, ...k.also].map((r, i) => (
         <div key={i} className="ck-top"><span className={`ck-tag ${r.kind}`}>{KIND_LABEL[r.kind]}</span>
           <span className="ck-text"><Ticks text={r.text} /></span></div>
@@ -35,7 +38,9 @@ function CheckRow({ k, lit }: { k: Check; lit: boolean }) {
       <div className="ck-acts">
         <button className="link" onClick={toggle} disabled={busy} aria-pressed={marked}>{marked ? "Reopen" : "Looks fine"}</button>
         <button className="link" onClick={() => setTalk(!talk)} aria-expanded={talk}>Comment{talks ? ` (${talks})` : ""}</button>
-        {k.depot && <Link to={ws.link(ws.opened({ file: k.depot, line: k.line }))} title={`Open ${at}`} aria-label={`Open ${at}`}>Open</Link>}
+        {k.depot && <Link to={ws.link(ws.opened({ file: k.depot, line: k.line }))} title={`Open ${place}`} aria-label={`Open ${place}`}>Open</Link>}
+        {k.finding && <Link to={ws.link(at({ kind: "finding", fid: k.finding }, { details: true }))} title={`Finding ${k.finding}'s details`}
+                            aria-label={`Finding ${k.finding}'s details`}>Details</Link>}
       </div>
       {error && <div className="banner warn">{error}</div>}
       {talk && <Comments reviewId={d.id} comments={d.comments} kind="check" anchor={{ key: k.key }} onChange={d.loadComments} autoFocus />}
@@ -46,10 +51,11 @@ function CheckRow({ k, lit }: { k: Check; lit: boolean }) {
 export interface CheckGroup { label: string | null; checks: Check[] }
 
 /** A To check tile: open rows first, marked ones below; the overview's grouped by thread with "5 open" (§5.2), a story's
- * with "3 of 5 open" (§6.2). On a phone it comes first, folded to its count. `lit` highlights the rows of a finding. */
-export default function CheckTile({ groups, ofTotal, footer, lit = null }:
-  { groups: CheckGroup[]; ofTotal: boolean; footer?: ReactNode; lit?: string | null }) {
-  const ws = useWs(), marks = ws.data.reading?.marks ?? {};
+ * with "3 of 5 open" (§6.2). On a phone it comes first, folded to its count, unless it holds the finding an old
+ * address leads to: that row is lit. */
+export default function CheckTile({ groups, ofTotal, footer, id }:
+  { groups: CheckGroup[]; ofTotal: boolean; footer?: ReactNode; id?: string }) {
+  const ws = useWs(), marks = ws.data.reading?.marks ?? {}, lit = ws.addr.check ?? null;
   const all = groups.flatMap((g) => g.checks);
   const count = openCount(all.filter((k) => isOpen(k, marks)).length, all.length, ofTotal);
   const head = <>To check{count && <span className="ck-count">{count}</span>}</>;
@@ -67,6 +73,6 @@ export default function CheckTile({ groups, ofTotal, footer, lit = null }:
     {footer}
   </>;
   return ws.screen === "phone"
-    ? <details className="ws-tile ck-tile" aria-label="To check"><summary><h3>{head}</h3></summary>{body}</details>
-    : <section className="ws-tile ck-tile" aria-label="To check"><h3>{head}</h3>{body}</section>;
+    ? <details className="ws-tile ck-tile" aria-label="To check" id={id} open={!!lit || undefined}><summary><h3>{head}</h3></summary>{body}</details>
+    : <section className="ws-tile ck-tile" aria-label="To check" id={id}><h3>{head}</h3>{body}</section>;
 }
```

`frontend/src/workspace/FindingPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/FindingPage.tsx b/frontend/src/workspace/FindingPage.tsx
index f93202e..ecea60b 100644
--- a/frontend/src/workspace/FindingPage.tsx
+++ b/frontend/src/workspace/FindingPage.tsx
@@ -34,7 +34,7 @@ export default function FindingPage({ fid }: { fid: string }) {
   const step = (by: number) => {
     const to = d.findings[((i + by) % n + n) % n];
     const label = `${by < 0 ? "Previous" : "Next"} finding: ${to.id} ${short(to.title)}`;
-    return <Link className="bd-ibtn ws-step-btn" to={ws.link(ws.item({ kind: "finding", fid: to.id }))} title={label} aria-label={label}>
+    return <Link className="bd-ibtn ws-step-btn" to={ws.link({ ...ws.item({ kind: "finding", fid: to.id }), details: true })} title={label} aria-label={label}>
       {by < 0 ? "‹" : "›"}</Link>;
   };
   const name = (nid: string) => {
```

`frontend/src/workspace/IndexPage.tsx` (new file):

```tsx
import { Link } from "react-router-dom";
import { plainTitle } from "../lib/markdown";
import { CHECK_ORDER, KIND_LABEL, placeOf } from "../reading/checks";
import { at, INDEX_TABS, type IndexTab } from "./address";
import CheckTile from "./CheckList";
import ClusterPage from "./ClusterPage";
import { useWs } from "./context";
import { INDEX_LABEL } from "./crumbs";
import { Ticks } from "./NameText";
import { MapSection } from "./WholePage";

/** The Index's tabs, as links so each tab has its address. */
export function IndexTabs({ tab }: { tab: IndexTab }) {
  const ws = useWs(), r = ws.data.reading, d = ws.data;
  const count: Partial<Record<IndexTab, number>> = {
    cls: d.detail?.cls.length, files: d.about?.tree.reduce((n, t) => n + t.files.length, 0), checks: r ? r.checks.length : undefined,
  };
  return (
    <nav className="ws-switch ix-tabs" role="tablist" aria-label="Index">
      {INDEX_TABS.map((t) => (
        <Link key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""}
              to={ws.link(at({ kind: "index", tab: t }))}>{INDEX_LABEL[t]}{count[t] ? ` (${count[t]})` : ""}</Link>
      ))}
    </nav>
  );
}

/** What the rail no longer lists (spec 2026-10-07-review-reading §11): the CLs, the files, every check by kind and the
 * map; a part of the map opens with the Map tab above it. */
export default function IndexPage({ tab, cid }: { tab: IndexTab; cid?: string }) {
  const ws = useWs(), d = ws.data, r = d.reading;
  if (tab === "map" && cid)
    return <div className="ix-frame"><div className="ix-bar"><IndexTabs tab="map" /></div><ClusterPage cid={cid} /></div>;
  return (
    <div className="ws-page"><div className="ws-text ws-whole ix-page">
      <IndexTabs tab={tab} />
      {tab === "cls" && (
        <ul className="ix-list">{(d.detail?.cls ?? []).map((c) => {
          const first = plainTitle((c.description ?? "").trim().split("\n")[0]);
          const files = d.about?.cls.find((x) => x.cl === c.cl)?.file_count;
          return (
            <li key={c.cl}>
              <Link to={ws.link(ws.item({ kind: "cl", cl: c.cl }))} title={`Open CL ${c.cl}`} aria-label={`Open CL ${c.cl}`}><b>CL {c.cl}</b></Link>
              {c.user && <span className="muted"> {c.user}</span>}
              {!!files && <span className="muted small"> · {files} file{files === 1 ? "" : "s"}</span>}
              {first && <div className="ix-sub">{first}</div>}
            </li>
          );
        })}</ul>
      )}
      {tab === "files" && (d.about?.tree ?? []).map((t) => (
        <section key={t.dir} aria-label={`Files in ${t.dir}`} className="ix-dir">
          <h3 className="mono">{t.dir}/</h3>
          <ul className="ix-list">{t.files.map((f) => (
            <li key={f.path}>
              <Link className="mono" to={ws.link(ws.opened({ file: f.path, line: null }))} title={`Open ${f.name}'s diff`}
                    aria-label={`Open ${f.name}'s diff`}>{f.name}</Link>
              <span className="muted small"> {f.action}</span>
              <span className="cnt"> <span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
              {f.cls.map((c) => <span key={c} className="ws-chip">CL {c}</span>)}
            </li>
          ))}</ul>
        </section>
      ))}
      {tab === "checks" && r && <>
        <CheckTile ofTotal={false} groups={CHECK_ORDER.map((k) => ({ label: KIND_LABEL[k], checks: r.checks.filter((c) => c.kind === k) }))
          .filter((g) => g.checks.length)} />
        {r.cleared.length > 0 && (
          <section className="ws-tile" aria-label="Found no hazard">
            <h3>Found no hazard</h3>
            <ul className="ov-lines">{r.cleared.map((k) => (
              <li key={k.key}><Ticks text={k.text} />{placeOf(k) && <span className="mono small"> · <Ticks text={placeOf(k)} /></span>}</li>
            ))}</ul>
          </section>
        )}
      </>}
      {tab === "map" && <MapSection />}
    </div></div>
  );
}
```

`frontend/src/workspace/Overview.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Overview.tsx b/frontend/src/workspace/Overview.tsx
index c8ce177..22fb9c2 100644
--- a/frontend/src/workspace/Overview.tsx
+++ b/frontend/src/workspace/Overview.tsx
@@ -7,7 +7,7 @@ import CheckTile from "./CheckList";
 import { useWs } from "./context";
 import { short } from "./crumbs";
 import { Ticks } from "./NameText";
-import { Discussion, MapSection } from "./WholePage";
+import { Discussion } from "./WholePage";
 
 const ROW = 56;                       // one thread box and the room around it in the connections tile
 
@@ -114,11 +114,10 @@ export default function Overview({ r }: { r: Reading }) {
             )}
           </section>
         )}
-        <MapSection />
         <Discussion />
       </div>
       <aside className="ov2-right" aria-label="What to check">
-        <CheckTile groups={byThread(r)} ofTotal={false} footer={<>
+        <CheckTile id="checks" groups={byThread(r)} ofTotal={false} footer={<>
           {r.rules_only && <p className="muted small">Risks judged by rules only.</p>}
           {r.cleared.length > 0 && (
             <details className="ck-cleared">
```

`frontend/src/workspace/Rail.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Rail.tsx b/frontend/src/workspace/Rail.tsx
index 0aa6d23..665dbad 100644
--- a/frontend/src/workspace/Rail.tsx
+++ b/frontend/src/workspace/Rail.tsx
@@ -3,11 +3,13 @@ import { Link } from "react-router-dom";
 import type { Story } from "../board/types";
 import { keys, load, loadWidth, save } from "../board/prefs";
 import Resizer from "../board/Resizer";
+import HeadlinePill from "../components/HeadlinePill";
 import { plainTitle } from "../lib/markdown";
+import { isOpen, letter, openCount } from "../reading/checks";
 import { reviewTargets, sections } from "../stories/stories";
-import { type Place, samePlace } from "./address";
+import { INDEX_TABS, type Place, samePlace } from "./address";
 import { useWs } from "./context";
-import { short } from "./crumbs";
+import { INDEX_LABEL, short } from "./crumbs";
 import { Ticks } from "./NameText";
 import { bySeverity, litStories, storyCls } from "./rail";
 
@@ -76,6 +78,57 @@ export default function Rail({ show, onPick, hidden = false }: { show: string |
   const of = d.stories ? sections(d.stories) : null;
   const shown = ws.addr.open && "file" in ws.addr.open ? ws.addr.open.file : null;
 
+  const r = d.reading;
+  if (r && ss) {                                         // the reading's rail (spec 2026-10-07-review-reading §11)
+    const byId = new Map(ss.stories.map((st) => [st.id, st]));
+    const open = r.checks.filter((k) => isOpen(k, r.marks)).length;
+    const tests = ss.stories.filter((st) => st.kind === "tests");
+    const storyRow = (st: Story, why?: string) => { const reason = st.kind === "unsorted" ? "Needs a person to place it" : why; return row({ kind: "story", sid: st.id, view: "steps" }, `Go to story ${st.id}: ${short(st.title)}`, <>
+      <span className="ws-row-top">
+        <span className="ws-row-title"><Ticks text={st.title} /></span>
+        <span className="ws-handle">{st.id}</span>
+      </span>
+      {(reason || (manyTargets && (st.targets ?? []).length > 0)) && <span className="ws-chips">
+        {reason && <span className="ws-row-sub">{reason}</span>}
+        {manyTargets && (st.targets ?? []).map((t) => <span key={t} className="ws-chip target">⌖ {t}</span>)}</span>}
+    </>, "story", st.id); };
+    return (
+      <aside className="ws-rail" style={{ ["--w" as string]: `${width}px` }} aria-label="Review contents" inert={hidden}>
+        <Resizer size={width} edge="right" min={200} max={() => 600} onSize={setWidth} onDone={(w) => save(keys.railW, w)} />
+        <div className="ws-rail-scroll" ref={box}>
+        <Link to={ws.base} state={{ page: true }} className="ws-row ws-home" aria-current={here({ kind: "whole" })}
+              title="Go to the overview" aria-label="Go to the overview" onClick={onPick}>
+          <span aria-hidden>⌂</span> Overview <HeadlinePill h={r.headline} />
+        </Link>
+        {section("stories", `Threads (${r.threads.length})`, <>
+          {r.threads.map((t, i) => (
+            <div key={t.id} className="ws-group ws-thread">
+              <h3><span className="ov-letter">{letter(i, t.id)}</span> <Ticks text={t.name} />
+                {t.open_checks > 0 && <span className="ck-count">{t.open_checks}</span>}</h3>
+              <ul>{t.stories.map((sid) => byId.get(sid) && <li key={sid}>{storyRow(byId.get(sid)!, r.reasons[sid])}</li>)}</ul>
+            </div>
+          ))}
+          {tests.length > 0 && <div className="ws-group"><h3>Tests</h3><ul>{tests.map((st) => <li key={st.id}>{storyRow(st)}</li>)}</ul></div>}
+          {!r.threads.length && !tests.length && <p className="muted small">No changed functions.</p>}
+        </>)}
+        <hr className="ws-divider" />
+        <Link to={`${ws.base}#checks`} state={{ page: true }} className="ws-row ws-missed" onClick={onPick}
+              title="Go to what may have been missed: the review's To check" aria-label="Go to what may have been missed: the review's To check">
+          <span className="ws-row-top"><span className="ws-row-title">Possibly missed</span>
+            {r.checks.length > 0 && <span className="ck-count">{openCount(open, r.checks.length, false)}</span>}</span>
+        </Link>
+        <section className="ws-sec ws-index" aria-label="Index">
+          <h2 className="ws-sec-t">Index</h2>
+          <ul>{INDEX_TABS.map((t) => (
+            <li key={t}>{row({ kind: "index", tab: t }, `Open the Index: ${INDEX_LABEL[t]}`, <span className="ws-row-top">{INDEX_LABEL[t]}</span>,
+                             "ws-index-row")}</li>
+          ))}</ul>
+        </section>
+        </div>
+      </aside>
+    );
+  }
+
   return (
     <aside className="ws-rail" style={{ ["--w" as string]: `${width}px` }} aria-label="Review contents" inert={hidden}>
       {/* the grip sits on the frame, outside the scrolling box, so the scrollbar never covers it */}
```

`frontend/src/workspace/Workspace.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index b01e9fc..71a9a4d 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -1,5 +1,5 @@
 import { useCallback, useEffect, useMemo, useRef, useState } from "react";
-import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
+import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
 import { api } from "../api";
 import { useMe } from "../App";
 import { driftSummary } from "../board/drift";
@@ -18,9 +18,10 @@ import { loadMemory, recall, remember, saveMemory } from "./memory";
 import ClPage from "./ClPage";
 import ClusterPage from "./ClusterPage";
 import FindingPage from "./FindingPage";
+import IndexPage from "./IndexPage";
 import Rail from "./Rail";
 import StoryPage from "./StoryPage";
-import { legacy } from "./legacy";
+import { indexFor, legacy } from "./legacy";
 import { useReview } from "./useReview";
 import WholePage, { ReviewGraph } from "./WholePage";
 import "./workspace.css";
@@ -54,10 +55,15 @@ export default function Workspace() {
                          [root, data, addr, screen, sources, link, go, item, opened, hover]);
 
   const d = data.detail;
+  const r = data.reading;
+  const threadOf = useMemo(() => r ? (sid: string) => {
+    const i = r.threads.findIndex((t) => t.stories.includes(sid));
+    return i >= 0 ? `Thread ${String.fromCharCode(65 + Math.min(i, 25))}` : "Tests";
+  } : undefined, [r]);
   const trail = useMemo(() => crumbs(addr.place, {
     base: root, title: d?.review.title ?? `Review ${id}`, stories: data.stories?.stories ?? [], findings: data.findings,
-    cls: d?.cls ?? [], clusters: data.overview?.clusters ?? [],
-  }), [addr.place, root, d, id, data.stories, data.findings, data.overview]);
+    cls: d?.cls ?? [], clusters: data.overview?.clusters ?? [], threadOf,
+  }), [addr.place, root, d, id, data.stories, data.findings, data.overview, threadOf]);
   const hash = location.hash.slice(1) || null;
 
   // an address from before the workspace goes to where that thing lives now (§2.3)
@@ -75,17 +81,20 @@ export default function Workspace() {
       () => to(root));
     return () => { live = false; };
   }, [old, id, root, navigate]);
-  const scrolled = useRef(false);                          // #map scrolls once, when the map is there to scroll to
+  const scrolled = useRef(false);                          // #map or #checks scrolls once, when it is there to scroll to
   useEffect(() => {
-    if (hash !== "map") { scrolled.current = false; return; }
-    const map = document.getElementById("map");
-    if (map && !scrolled.current) { map.scrollIntoView({ block: "start" }); scrolled.current = true; }
+    if (hash !== "map" && hash !== "checks") { scrolled.current = false; return; }
+    const el = document.getElementById(hash);
+    if (el && !scrolled.current) { el.scrollIntoView({ block: "start" }); scrolled.current = true; }
   });
-  const page = (location.state as { page?: boolean } | null)?.page || hash === "map";
+  const page = (location.state as { page?: boolean } | null)?.page || hash === "map" || hash === "checks";
+  // with a reading, an old section's anchor (#map, #findings…) opens its Index tab (review reading §11)
+  const anchored = r && hash && addr.place.kind === "whole" && !addr.place.view ? indexFor(hash) : null;
   const level = addr.open ? "detail" : addr.place.kind === "whole" && !addr.place.view && !page ? "rail" : "item";
 
   if (data.error) return <main className="page error">{data.error}</main>;
   if (!d || old) return <main className="page muted">Loading…</main>;
+  if (anchored) return <Navigate replace to={href(root, at(anchored))} />;
   return (
     <AiProvider value={data.ai}>
       <WsContext.Provider value={ws}>
@@ -148,7 +157,8 @@ function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
 function Centre() {
   const ws = useWs(), d = ws.data, p = ws.addr.place;
   if (!d.ready) return <div className="ws-page"><Stages stages={d.detail!.stages} /><p className="muted">Analysis in progress…</p></div>;
-  const exists = p.kind === "whole" || (p.kind === "story" && !!d.stories?.stories.some((s) => s.id === p.sid))
+  const r = d.reading;
+  const exists = p.kind === "whole" || (p.kind === "index" && !!r) || (p.kind === "story" && !!d.stories?.stories.some((s) => s.id === p.sid))
     || (p.kind === "finding" && d.findings.some((f) => f.id === p.fid)) || (p.kind === "cl" && !!d.detail?.cls.some((c) => c.cl === p.cl))
     || (p.kind === "cluster" && !!d.overview?.clusters.some((c) => c.id === p.cid));
   if (!exists) return <Missing what={p} />;
@@ -156,9 +166,16 @@ function Centre() {
     return d.board ? <div className="ws-page graph"><ReviewGraph board={d.board} /></div> : <Missing what={p} />;
   if (p.kind === "whole") return <WholePage />;
   if (p.kind === "story") return <StoryPage key={p.sid} sid={p.sid} view={p.view} />;
-  if (p.kind === "finding") return <FindingPage key={p.fid} fid={p.fid} />;
+  if (p.kind === "finding") {
+    // with a reading, an old finding address opens its story with its row lit (§11); its own page is Details
+    const k = r && !ws.addr.details ? r.checks.find((c) => c.finding === p.fid) : null;
+    const sid = k ? k.story ?? d.stories?.finding_story[p.fid] ?? null : null;
+    if (k) return <Navigate replace to={ws.link(at(sid ? { kind: "story", sid, view: "steps" } : { kind: "whole" }, { check: p.fid }))} />;
+    return <FindingPage key={p.fid} fid={p.fid} />;
+  }
   if (p.kind === "cl") return <ClPage key={p.cl} cl={p.cl} />;
-  if (p.kind === "cluster") return <ClusterPage key={p.cid} cid={p.cid} />;
+  if (p.kind === "cluster") return r ? <IndexPage key={p.cid} tab="map" cid={p.cid} /> : <ClusterPage key={p.cid} cid={p.cid} />;
+  if (p.kind === "index") return <IndexPage key={p.tab} tab={p.tab} />;
   return <Missing what={p} />;
 }
 
```

`frontend/src/workspace/address.ts` (diff):

```diff
diff --git a/frontend/src/workspace/address.ts b/frontend/src/workspace/address.ts
index c88b38c..861e41f 100644
--- a/frontend/src/workspace/address.ts
+++ b/frontend/src/workspace/address.ts
@@ -7,8 +7,13 @@ export type Place =
   | { kind: "finding"; fid: string }
   | { kind: "cl"; cl: number }
   | { kind: "cluster"; cid: string }
+  | { kind: "index"; tab: IndexTab }
   | { kind: "unknown"; path: string };
 
+/** The Index's tabs (spec 2026-10-07-review-reading §11): what the rail no longer lists. */
+export const INDEX_TABS = ["cls", "files", "checks", "map"] as const;
+export type IndexTab = typeof INDEX_TABS[number];
+
 /** What the detail panel shows: a node's code, or a file's diff (at a line). */
 export type Open = { node: string } | { file: string; line: number | null } | null;
 export type Tab = "diff" | "neighbours";
@@ -21,6 +26,10 @@ export interface Address {
   tab: Tab;
   /** A story lit on a map (the whole graph or a part's), from its "Show on the map". */
   story?: string | null;
+  /** The finding whose To check row is lit: where an old finding address leads. */
+  check?: string | null;
+  /** A finding's own page, from its row's Details, rather than its story. */
+  details?: boolean;
 }
 
 function readPlace(path: string, q: URLSearchParams): Place {
@@ -32,6 +41,7 @@ function readPlace(path: string, q: URLSearchParams): Place {
   if (kind === "f") return { kind: "finding", fid: id };
   if (kind === "cl" && /^\d+$/.test(id)) return { kind: "cl", cl: Number(id) };
   if (kind === "c") return { kind: "cluster", cid: id };
+  if (kind === "i" && (INDEX_TABS as readonly string[]).includes(id)) return { kind: "index", tab: id as IndexTab };
   return { kind: "unknown", path };
 }
 
@@ -51,6 +61,8 @@ export function readAddress(path: string, q: URLSearchParams): Address {
     open: readOpen(q.get("open")),
     tab: q.get("tab") === "neighbours" ? "neighbours" : "diff",
     ...(q.get("story") ? { story: q.get("story") } : {}),
+    ...(q.get("check") ? { check: q.get("check") } : {}),
+    ...(q.get("details") === "1" ? { details: true } : {}),
   };
 }
 
@@ -61,6 +73,7 @@ function placePath(p: Place): string {
     case "finding": return `/f/${p.fid}`;
     case "cl": return `/cl/${p.cl}`;
     case "cluster": return `/c/${p.cid}`;
+    case "index": return `/i/${p.tab}`;
     case "unknown": return p.path;
   }
 }
@@ -73,6 +86,8 @@ export function href(base: string, a: Address): string {
   if (a.flow) q.set("flow", String(a.flow));
   if (a.open) q.set("open", "node" in a.open ? a.open.node : `file:${a.open.file}${a.open.line ? `:${a.open.line}` : ""}`);
   if (a.tab !== "diff") q.set("tab", a.tab);
+  if (a.check) q.set("check", a.check);
+  if (a.details && a.place.kind === "finding") q.set("details", "1");
   return `${base}${placePath(a.place)}${q.size ? `?${q}` : ""}`;
 }
 
@@ -84,6 +99,7 @@ export function placeKey(p: Place): string {
     case "finding": return `f:${p.fid}`;
     case "cl": return `cl:${p.cl}`;
     case "cluster": return `c:${p.cid}`;
+    case "index": return `i:${p.tab}`;
     case "unknown": return `?:${p.path}`;
   }
 }
```

`frontend/src/workspace/crumbs.ts` (diff):

```diff
diff --git a/frontend/src/workspace/crumbs.ts b/frontend/src/workspace/crumbs.ts
index 00f4a77..a3feb4f 100644
--- a/frontend/src/workspace/crumbs.ts
+++ b/frontend/src/workspace/crumbs.ts
@@ -11,8 +11,12 @@ export interface CrumbContext {
   findings: Pick<Finding, "id" | "title">[];
   cls: { cl: number; description: string | null }[];
   clusters: { id: string; name: string }[];
+  /** With a reading: a story's thread ("Thread A", "Tests"); CLs, files, checks and the map then live in the Index. */
+  threadOf?: (sid: string) => string | null;
 }
 
+export const INDEX_LABEL = { cls: "CLs", files: "Files", checks: "Checks", map: "Map" } as const;
+
 /** `text` without backticks, cut at a word to fit `n` characters with its ellipsis. */
 export function short(text: string, n = 46): string {
   const t = text.replace(/`/g, "").trim();
@@ -26,15 +30,21 @@ const missing = (): Crumb => ({ label: "Not found", to: null });
 export function crumbs(place: Place, c: CrumbContext): Crumb[] {
   const home = { label: c.title, to: c.base };
   if (place.kind === "whole") return place.view === "graph" ? [home, { label: "Graph", to: null }] : [{ label: c.title, to: null }];
-  const section = (label: string, anchor: string): Crumb => ({ label, to: `${c.base}#${anchor}` });
+  const reading = !!c.threadOf;
+  const tab = (t: keyof typeof INDEX_LABEL): Crumb => ({ label: INDEX_LABEL[t], to: `${c.base}/i/${t}` });
+  const section = (label: string, anchor: string): Crumb => (
+    reading && anchor === "findings" ? tab("checks") : reading && anchor === "changeset" ? tab("cls")
+      : reading && anchor === "map" ? tab("map") : { label, to: `${c.base}#${anchor}` });
   switch (place.kind) {
     case "story": {
       const st = c.stories.find((s) => s.id === place.sid);
-      if (!st) return [home, section("Stories", "stories"), missing()];
+      const up = c.threadOf?.(place.sid);
+      const parent = up ? { label: up, to: c.base } : section("Stories", "stories");
+      if (!st) return [home, parent, missing()];
       const graph = place.view === "graph";
       const me: Crumb = { label: short(st.title), handle: st.id,
                           to: graph ? href(c.base, { place: { ...place, view: "steps" }, flow: null, open: null, tab: "diff" }) : null };
-      return [home, section("Stories", "stories"), me, ...(graph ? [{ label: "Graph", to: null }] : [])];
+      return [home, parent, me, ...(graph ? [{ label: "Graph", to: null }] : [])];
     }
     case "finding": {
       const f = c.findings.find((x) => x.id === place.fid);
@@ -50,6 +60,8 @@ export function crumbs(place: Place, c: CrumbContext): Crumb[] {
       const k = c.clusters.find((x) => x.id === place.cid);
       return [home, section("Map", "map"), k ? { label: short(k.name), to: null } : missing()];
     }
+    case "index":
+      return [home, { label: INDEX_LABEL[place.tab], to: null }];
     case "unknown":
       return [home, missing()];
   }
```

`frontend/src/workspace/legacy.ts` (diff):

```diff
diff --git a/frontend/src/workspace/legacy.ts b/frontend/src/workspace/legacy.ts
index 343e0dd..80e9a75 100644
--- a/frontend/src/workspace/legacy.ts
+++ b/frontend/src/workspace/legacy.ts
@@ -1,5 +1,5 @@
 /** Addresses from before the workspace (spec 2026-10-04-review-workspace §2.3) and where they go now. */
-import { at, href, readAddress } from "./address";
+import { at, href, type Place, readAddress } from "./address";
 
 interface Ctx {
   base: string;
@@ -33,3 +33,14 @@ export function legacy(path: string, q: URLSearchParams, c: Ctx): { to: string }
   }
   return null;
 }
+
+const ANCHORS: Record<string, Place> = {
+  map: { kind: "index", tab: "map" }, findings: { kind: "index", tab: "checks" }, changeset: { kind: "index", tab: "cls" },
+  files: { kind: "index", tab: "files" },
+};
+
+/** Where an old section anchor (#map, #findings…) leads once the review has a reading: the Index's tab (spec
+ * 2026-10-07-review-reading §11); null for anchors the rail still has. */
+export function indexFor(hash: string): Place | null {
+  return ANCHORS[hash] ?? null;
+}
```

`frontend/src/workspace/workspace.css` (diff):

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index fab24e1..ba88e4b 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -633,3 +633,18 @@ a.ws-chip { text-decoration: none; }
 .st-suggested ul { margin: 0; padding-left: 18px; }
 .st-tiles .cnt { font: 11px var(--mono); } .st-tiles .cnt .p { color: var(--ok); } .st-tiles .cnt .m { color: var(--bad); }
 .bd-tag.call { background: var(--gap-bg); color: var(--ink); }
+.ws-thread h3 { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink); }
+.ws-thread h3 .ov-letter { width: 18px; height: 18px; font-size: 10px; }
+.ws-thread h3 .ck-count { margin-left: auto; }
+.ws-divider { border: 0; border-top: 1px solid var(--line); margin: 6px 0; }
+.ws-missed .ck-count { margin-left: auto; }
+.ws-index > h2 { margin: 0; }
+.ws-index ul { list-style: none; margin: 0; padding: 0; }
+.ix-frame { flex: 1; min-height: 0; display: flex; flex-direction: column; }
+.ix-bar { flex: none; padding: 10px 24px 0; }
+.ix-tabs { margin: 0 0 16px; }
+.ix-list { list-style: none; margin: 0; padding: 0; font-size: 14px; }
+.ix-list li { padding: 6px 0; border-bottom: 1px solid var(--line); display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
+.ix-sub { flex-basis: 100%; color: var(--muted); font-size: 13px; }
+.ix-dir h3 { font-size: 12px; color: var(--muted); margin: 14px 0 4px; }
+.ix-page .cnt { font: 11px var(--mono); } .ix-page .cnt .p { color: var(--ok); } .ix-page .cnt .m { color: var(--bad); }
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd frontend && npx vitest run src/workspace/address.test.ts src/workspace/crumbs.test.ts src/workspace/legacy.test.ts`
Expected: PASS: `Tests 22 passed (22)`

Run: `cd frontend && npm run build && npx playwright test e2e/ai.spec.ts e2e/mention.spec.ts e2e/theme.spec.ts e2e/workspace-detail.spec.ts e2e/workspace-graph.spec.ts e2e/workspace-legacy.spec.ts e2e/workspace-map-stories.spec.ts e2e/workspace-pages.spec.ts e2e/workspace-reading.spec.ts e2e/workspace-story.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace.spec.ts`
Expected: PASS: `93 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `606 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 165 passed (165)`; Playwright `1 failed, 100 passed` (in the replay, the first run's failures were timeouts under load; `npx playwright test --last-failed` then gave `1 passed`)

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/ai.spec.ts frontend/e2e/mention.spec.ts frontend/e2e/theme.spec.ts frontend/e2e/workspace-detail.spec.ts frontend/e2e/workspace-graph.spec.ts frontend/e2e/workspace-legacy.spec.ts frontend/e2e/workspace-map-stories.spec.ts frontend/e2e/workspace-pages.spec.ts frontend/e2e/workspace-reading.spec.ts frontend/e2e/workspace-story.spec.ts frontend/e2e/workspace-tier1.spec.ts frontend/e2e/workspace.spec.ts frontend/src/workspace/address.test.ts frontend/src/workspace/crumbs.test.ts frontend/src/workspace/legacy.test.ts frontend/src/reading/checks.ts frontend/src/workspace/CheckList.tsx frontend/src/workspace/FindingPage.tsx frontend/src/workspace/IndexPage.tsx frontend/src/workspace/Overview.tsx frontend/src/workspace/Rail.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/address.ts frontend/src/workspace/crumbs.ts frontend/src/workspace/legacy.ts frontend/src/workspace/workspace.css
git commit -m "feat(ui): the rail follows the threads; CLs, files, checks and the map move to an Index; old finding and cluster addresses land on their rows"
```

### Task 13: Evidence reads as people write it

Spec §12. `tidy(text, root=None)` rewrites dict and list reprs as lists ("by layer: L1: hal (1), L2: driver (1)"), "N word(s)" as a counted noun (and "1 change(s) reach" as "1 change reaches"), a listed "value(s) -2" by the number of its list, "->" as "→", and drops the workspace root from paths; text in backticks is code and stays. Check rows, tier-1 and tier-2 prompts and the findings API's summaries and evidence use it. Stored titles stay as the detectors wrote them (comments and verdicts are anchored on them), so `frontend/src/lib/tidy.ts` applies the same rules where the browser shows a finding's title, summary or evidence. `counted(n, noun)` never shows an empty count: the map's blocks and a part's header leave out "0 flows".

**Files:**
- Test: `backend/tests/test_reading.py`
- Test: `backend/tests/test_tidy.py`
- Test: `backend/tests/test_tortoise.py`
- Test: `backend/tests/test_web.py`
- Test: `frontend/e2e/workspace-pages.spec.ts`
- Test: `frontend/e2e/workspace.spec.ts`
- Test: `frontend/src/lib/tidy.test.ts`
- Test: `frontend/src/workspace/crumbs.test.ts`
- Modify: `backend/codetortoise/llm/review.py`
- Modify: `backend/codetortoise/llm/stories.py`
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `backend/codetortoise/llm/tortoise.py`
- Modify: `backend/codetortoise/reading.py`
- Create: `backend/codetortoise/tidy.py`
- Modify: `backend/codetortoise/web/app.py`
- Create: `frontend/src/lib/tidy.ts`
- Modify: `frontend/src/workspace/ClPage.tsx`
- Modify: `frontend/src/workspace/ClusterPage.tsx`
- Modify: `frontend/src/workspace/FindingPage.tsx`
- Modify: `frontend/src/workspace/Rail.tsx`
- Modify: `frontend/src/workspace/StorySteps.tsx`
- Modify: `frontend/src/workspace/WholePage.tsx`
- Modify: `frontend/src/workspace/crumbs.ts`

**Interfaces:**
- Consumes: findings (title, summary, evidence), `canon(cfg.workspace.root)`.
- Produces: `codetortoise.tidy.tidy(text: str, root: str | None = None) -> str`; `frontend/src/lib/tidy.ts`: `tidy(text)`, `counted(n, noun)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_reading.py` (diff):

```diff
diff --git a/backend/tests/test_reading.py b/backend/tests/test_reading.py
index 11a95bc..4caa5c7 100644
--- a/backend/tests/test_reading.py
+++ b/backend/tests/test_reading.py
@@ -392,6 +392,15 @@ def test_without_verdicts_high_and_medium_findings_are_confirm_rows_except_heade
     assert _rows(open_) == [("confirm", "S1", "drv/uart.c", 1, "send", "send: signature changed")]
 
 
+def test_a_check_reads_its_finding_tidied():
+    c = _world([_edit("send", "drv/uart.c")])
+    ss = _set(["N1"])
+    ss.finding_story = {"F1": "S1"}
+    c.findings = [_f("F1", severity="medium", title="send: new return value(s) -2")]
+    open_, _ = _checks(c, ss)
+    assert [k.text for k in open_] == ["send: new return value -2"]
+
+
 def _caller_world(**kw):
     """`send` (S1) changed its signature; `log` and `flush` call it, `log` is changed too (S2)."""
     c = _world([_edit("send", "drv/uart.c"), _edit("log", "svc/log.c"), _same("flush", "svc/flush.c")],
```

`backend/tests/test_tidy.py` (new file):

```python
"""Evidence written for people (spec 2026-10-07-review-reading §12)."""
from codetortoise.tidy import tidy


def test_python_reprs_become_lists_and_sentences():
    assert tidy("by layer: {'L1: hal': 1, 'L2: drv': 3}") == "by layer: L1: hal (1), L2: drv (3)"
    assert tidy("returns before: ['0']; after: ['-2', '0']") == "returns before: 0; after: -2, 0"
    assert tidy("returns before: []; after: [1]") == "returns before: none; after: 1"


def test_counts_read_as_words():
    assert tidy("regs.h: 1 change(s) reach 4 TU(s)") == "regs.h: 1 change reaches 4 TUs"
    assert tidy("affect 1 translation unit(s) across 2 layer(s).") == "affect 1 translation unit across 2 layers."
    assert tidy("3 caller(s) must be re-checked: a, b, c") == "3 callers must be re-checked: a, b, c"


def test_a_listed_value_takes_the_number_of_its_list():
    assert tidy("uart_send: new return value(s) -2") == "uart_send: new return value -2"
    assert tidy("f: new return value(s) -2, -3") == "f: new return values -2, -3"


def test_arrows_read_as_arrows_and_code_is_left_alone():
    assert tidy("signature: `int f(int a[4])` -> `int f(int a[8])`") == "signature: `int f(int a[4])` → `int f(int a[8])`"
    assert tidy("writes Uart::errors via a -> b") == "writes Uart::errors via a → b"


def test_paths_under_the_workspace_read_relative_to_it():
    assert tidy("Changes in /ws/root/include/regs.h affect 4 translation unit(s)", root="/ws/root") == \
        "Changes in include/regs.h affect 4 translation units"
    assert tidy("Changes in /elsewhere/regs.h", root="/ws/root") == "Changes in /elsewhere/regs.h"


def test_anything_else_is_left_as_it_was():
    for text in ("[medium] flush drops it", "{not a dict}", "a set {1, 2} of ids", "plain text", ""):
        assert tidy(text) == text
```

`backend/tests/test_tortoise.py` (diff):

```diff
diff --git a/backend/tests/test_tortoise.py b/backend/tests/test_tortoise.py
index e517c2d..0908b1c 100644
--- a/backend/tests/test_tortoise.py
+++ b/backend/tests/test_tortoise.py
@@ -173,7 +173,7 @@ def test_each_anchor_kind_brings_its_context(world):
     _ask(bob, rid, "@tortoise finding?", "finding", {"kind": "contract", "title": "uart_send: new return value(s) -2"})
     _ask(bob, rid, "@tortoise review?", "review", {})
     assert "int uart_send" in script.prompts[0]
-    assert "new return value(s) -2" in script.prompts[1]
+    assert "new return value -2" in script.prompts[1]                   # the model reads the finding tidied
     assert "FLOWS" in script.prompts[2] and "FINDINGS" in script.prompts[2]
 
 
```

`backend/tests/test_web.py` (diff):

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index 2928565..62e55e6 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -72,7 +72,10 @@ def test_owner_creates_review_others_view_and_comment(env):
     # the raw storyboard and impact graph are not served: the board replaced them (spec §14.4)
     assert bob.get(f"/api/reviews/{rid}/storyboard").status_code == 404
     assert bob.get(f"/api/reviews/{rid}/impact").status_code == 404
-    assert len(bob.get(f"/api/reviews/{rid}/findings").json()) == 6
+    found = bob.get(f"/api/reviews/{rid}/findings").json()
+    assert len(found) == 6
+    fan = next(f for f in found if f["kind"] == "header_fanout")                # paths in the text are workspace-relative
+    assert fan["summary"].startswith("Changes in include/") and "{'" not in str([e["text"] for e in fan["evidence"]])
     assert [f["depot"] for f in bob.get(f"/api/reviews/{rid}/files").json()][0] == "//fixture/driver/uart.c"
     ev = bob.get(f"/api/reviews/{rid}/events")
     assert ev.status_code == 200 and ev.text.startswith("data: ")
```

`frontend/e2e/workspace-pages.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-pages.spec.ts b/frontend/e2e/workspace-pages.spec.ts
index 0af5dd4..b5e182d 100644
--- a/frontend/e2e/workspace-pages.spec.ts
+++ b/frontend/e2e/workspace-pages.spec.ts
@@ -9,7 +9,8 @@ test.describe("desktop", () => {
   test("a finding: to its story and back, on the graph, evidence opens the diff at its line", async ({ page }) => {
     const base = await startReview(page);
     await page.goto(`${base}/f/F4?details=1`);
-    await expect(page.locator(".ws-finding h2")).toContainText("uart_send: new return value(s) -2");
+    await expect(page.locator(".ws-finding h2")).toContainText("uart_send: new return value -2");
+    await expect(page.locator(".ws-finding")).toContainText("returns before: 0; after: -2, 0");      // evidence as a list, not a repr
     await expect(page.getByRole("region", { name: "AI analysis" })).toContainText("AI analysis unavailable.");
     await page.getByRole("link", { name: /^Go to story S1/ }).first().click();
     await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
@@ -34,6 +35,17 @@ test.describe("desktop", () => {
     await expectNamed(page);
   });
 
+  test("a header's reach reads as words: counts with their nouns, its layers as a list", async ({ page }) => {
+    const base = await startReview(page);
+    await page.goto(`${base}/f/F1?details=1`);
+    await expect(page.locator(".ws-finding h2")).toContainText("regs.h: 1 change reaches 4 TUs");
+    const finding = page.locator(".ws-finding");
+    await expect(finding).toContainText("Changes in include/hal/regs.h affect 4 translation units across 4 layers.");
+    await expect(finding).toContainText("included (transitively) by 4 TUs; by layer: ");
+    for (const layer of ["L1: hal (1)", "L2: driver (1)", "L3: service (1)", "L4: app (1)"]) await expect(finding).toContainText(layer);
+    await expect(finding).not.toContainText("{'");
+  });
+
   test("a side effect is neutral until the AI judges it: no red, and it says it isn't assessed", async ({ page }) => {
     const base = await startReview(page);
     const findings = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as { id: string; title: string }[];
```

`frontend/e2e/workspace.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index 992544b..f12d0f9 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -160,6 +160,7 @@ test.describe("a large change", () => {
     await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Map" }).click();
     const map = page.getByRole("region", { name: "The map" });
     await expect(map.locator(".ov-block")).toHaveCount(7);
+    await expect(map.locator(".ov-block .ct").filter({ hasText: /\b0 \w/ })).toHaveCount(0);      // an empty count is never shown
     await expect(map.getByRole("region", { name: "Layer drv" })).toContainText("drv/dma");
     const tints = await map.locator(".ov-band").evaluateAll((els) => els.map((e) => getComputedStyle(e).backgroundColor));
     expect(new Set(tints).size).toBeGreaterThan(1);   // each layer band keeps its level tint
@@ -168,6 +169,7 @@ test.describe("a large change", () => {
     await map.getByRole("link", { name: "Open drv/uart" }).click();
     await expect(page).toHaveURL(new RegExp(`${base}/c/C\\d+$`));
     await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Map › drv/uart");
+    await expect(page.locator(".ws-story-meta")).not.toContainText(/\b0 \w/);
     await expect(page.locator(".bd-node").first()).toBeVisible();
     await expect(page.getByRole("region", { name: "Flow" })).toBeVisible();
     let visitor = page.locator(".bd-home").first();
```

`frontend/src/lib/tidy.test.ts` (new file):

```ts
import { describe, expect, it } from "vitest";
import { counted, tidy } from "./tidy";

/** The same rules as backend/codetortoise/tidy.py (spec 2026-10-07-review-reading §12). */
describe("tidy", () => {
  it("turns Python reprs into lists and sentences", () => {
    expect(tidy("by layer: {'L1: hal': 1, 'L2: drv': 3}")).toBe("by layer: L1: hal (1), L2: drv (3)");
    expect(tidy("returns before: ['0']; after: ['-2', '0']")).toBe("returns before: 0; after: -2, 0");
    expect(tidy("returns before: []; after: [1]")).toBe("returns before: none; after: 1");
  });

  it("reads counts as words", () => {
    expect(tidy("regs.h: 1 change(s) reach 4 TU(s)")).toBe("regs.h: 1 change reaches 4 TUs");
    expect(tidy("affect 1 translation unit(s) across 2 layer(s).")).toBe("affect 1 translation unit across 2 layers.");
    expect(tidy("3 caller(s) must be re-checked: a, b, c")).toBe("3 callers must be re-checked: a, b, c");
  });

  it("gives a listed value the number of its list", () => {
    expect(tidy("uart_send: new return value(s) -2")).toBe("uart_send: new return value -2");
    expect(tidy("f: new return value(s) -2, -3")).toBe("f: new return values -2, -3");
  });

  it("reads arrows as arrows and leaves code alone", () => {
    expect(tidy("signature: `int f(int a[4])` -> `int f(int a[8])`")).toBe("signature: `int f(int a[4])` → `int f(int a[8])`");
    expect(tidy("writes Uart::errors via a -> b")).toBe("writes Uart::errors via a → b");
  });

  it("leaves anything else as it was", () => {
    for (const text of ["[medium] flush drops it", "{not a dict}", "a set {1, 2} of ids", "plain text", ""])
      expect(tidy(text)).toBe(text);
  });
});

describe("counted", () => {
  it("names a count with its noun and never shows an empty one", () => {
    expect(counted(0, "flow")).toBe("");
    expect(counted(1, "flow")).toBe("1 flow");
    expect(counted(3, "file")).toBe("3 files");
  });
});
```

`frontend/src/workspace/crumbs.test.ts` (diff):

```diff
diff --git a/frontend/src/workspace/crumbs.test.ts b/frontend/src/workspace/crumbs.test.ts
index 1b18e82..e07356c 100644
--- a/frontend/src/workspace/crumbs.test.ts
+++ b/frontend/src/workspace/crumbs.test.ts
@@ -30,7 +30,7 @@ describe("the breadcrumb", () => {
 
   it("names findings, changelists and clusters under their sections", () => {
     expect(crumbs({ kind: "finding", fid: "F2" }, ctx).slice(1)).toEqual([
-      { label: "Findings", to: "/r/7#findings" }, { label: "uart_send: new return value(s) -2", handle: "F2", to: null }]);
+      { label: "Findings", to: "/r/7#findings" }, { label: "uart_send: new return value -2", handle: "F2", to: null }]);
     expect(crumbs({ kind: "cl", cl: 101 }, ctx).slice(1)).toEqual([
       { label: "Change set", to: "/r/7#changeset" }, { label: "CL 101 · uart: count tx stats", to: null }]);
     expect(crumbs({ kind: "cluster", cid: "C1" }, ctx).slice(1)).toEqual([
@@ -46,7 +46,7 @@ describe("the breadcrumb", () => {
     expect(crumbs({ kind: "cl", cl: 101 }, r)).toEqual([home, { label: "CLs", to: "/r/7/i/cls" },
       { label: "CL 101 · uart: count tx stats", to: null }]);
     expect(crumbs({ kind: "finding", fid: "F2" }, r)).toEqual([home, { label: "Checks", to: "/r/7/i/checks" },
-      { label: "uart_send: new return value(s) -2", handle: "F2", to: null }]);
+      { label: "uart_send: new return value -2", handle: "F2", to: null }]);
     expect(crumbs({ kind: "index", tab: "files" }, r)).toEqual([home, { label: "Files", to: null }]);
   });
 
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_reading.py tests/test_tidy.py tests/test_tortoise.py tests/test_web.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.tidy'`

Run: `cd frontend && npx vitest run src/lib/tidy.test.ts src/workspace/crumbs.test.ts`
Expected: FAIL: `Tests 2 failed | 6 passed (8)`; the first error is `Error: Cannot find module './tidy' imported from frontend/src/lib/tidy.test.ts`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-pages.spec.ts e2e/workspace.spec.ts`
Expected: FAIL: `npm run build fails with 1 type error(s)`; the first error is `src/lib/tidy.test.ts(2,31): error TS2307: Cannot find module './tidy' or its corresponding type declarations.`

- [ ] **Step 3: Implement**

`backend/codetortoise/llm/review.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/review.py b/backend/codetortoise/llm/review.py
index 6d2f0d8..30f1b9b 100644
--- a/backend/codetortoise/llm/review.py
+++ b/backend/codetortoise/llm/review.py
@@ -25,6 +25,7 @@ from codetortoise.llm.stories import Tools, ask, pieces_of
 from codetortoise.llm.storyboard import _styled
 from codetortoise.llm.style import MODES, STYLE
 from codetortoise.pieces import PieceSet
+from codetortoise.tidy import tidy
 
 SEVERITY = {"hazard": "high", "needs_review": "medium", "no_hazard": "info"}
 
@@ -86,7 +87,8 @@ def question(f: Finding) -> str:
 
 def review_parts(s: PlannedStory, ps: PieceSet, mine: list[Finding], facts: dict[str, str]) -> list[str]:
     cards = "\n\n".join(p.card for p in ps.pieces if p.id in s.pieces)
-    rows = [f"{f.id} [{f.severity}] {f.kind}: {f.title}\n{f.summary}\nFACTS:\n{facts.get(finding_key(f), 'no prepared facts')}"
+    rows = [f"{f.id} [{f.severity}] {f.kind}: {tidy(f.title)}\n{tidy(f.summary)}\n"
+            f"FACTS:\n{facts.get(finding_key(f), 'no prepared facts')}"
             f"\nQUESTION: {question(f)}" for f in mine]
     return [RULES + "\n\nCHANGE OVERVIEW:\n" + ps.overview,
             f"STORY {s.key}: {s.title or '(untitled)'}" + (f"\nPurpose: {s.purpose}" if s.purpose else "") + "\nPIECES:\n" + cards,
```

`backend/codetortoise/llm/stories.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/stories.py b/backend/codetortoise/llm/stories.py
index a03a087..3967c71 100644
--- a/backend/codetortoise/llm/stories.py
+++ b/backend/codetortoise/llm/stories.py
@@ -29,6 +29,7 @@ from codetortoise.llm.ledger import Ledger, Refused
 from codetortoise.llm.storyboard import _styled, _titled
 from codetortoise.llm.style import MODES, STYLE
 from codetortoise.pieces import Piece, PieceSet
+from codetortoise.tidy import tidy
 
 STORY_RULES_VERSION = 2               # bump with every change to RULES or the prompts' wording
 CHUNK_SHARE = 0.6                     # a chunk's prompt stays within this share of the context
@@ -205,7 +206,7 @@ def _findings_of(ids: list[str], ps: PieceSet, findings: list[Finding]) -> list[
     for f in findings:
         mine = [pid for pid in pieces_of(f, ps) if pid in ids]
         if mine:
-            out.append(f"{f.id} [{f.severity}] {f.kind}: {f.title} — {', '.join(mine)}")
+            out.append(f"{f.id} [{f.severity}] {f.kind}: {tidy(f.title)} — {', '.join(mine)}")
     return out
 
 
```

`backend/codetortoise/llm/storyboard.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index 03b27dc..94b60d1 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -18,6 +18,7 @@ from codetortoise.llm.ledger import Ledger, Refused
 from codetortoise.llm.style import MODES, STYLE, check_style
 from codetortoise.provenance import merge
 from codetortoise.stories import StoryDetail
+from codetortoise.tidy import tidy
 
 SYSTEM = ("You are a senior C/C++ code reviewer. You are given facts extracted by static analysis "
           "for a set of changes. Use ONLY these facts. Refer to functions/fields by their node id (e.g. N3) "
@@ -187,8 +188,8 @@ def _facts_for_nodes(impact: ImpactModel, nids: list[str]) -> str:
 
 
 def _finding_text(f: Finding) -> str:
-    ev = "\n".join(f"  - [{e.severity}] {e.text} ({e.file}:{e.line})" for e in f.evidence)
-    return f"{f.id} [{f.severity}] {f.kind}: {f.title}\n{f.summary}\nnodes: {f.nodes}\nevidence:\n{ev}"
+    ev = "\n".join(f"  - [{e.severity}] {tidy(e.text)} ({e.file}:{e.line})" for e in f.evidence)
+    return f"{f.id} [{f.severity}] {f.kind}: {tidy(f.title)}\n{tidy(f.summary)}\nnodes: {f.nodes}\nevidence:\n{ev}"
 
 
 def _flow_prompt(fl: Flow, impact: ImpactModel, findings: list[Finding], snippets: dict[str, str], per_call: int) -> str:
```

`backend/codetortoise/llm/tortoise.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/tortoise.py b/backend/codetortoise/llm/tortoise.py
index 8906220..101b483 100644
--- a/backend/codetortoise/llm/tortoise.py
+++ b/backend/codetortoise/llm/tortoise.py
@@ -22,6 +22,7 @@ from codetortoise.llm.storyboard import STYLE, AiContext, _facts_for_nodes, _fin
 from codetortoise.llm.style import MODES, check_style
 from codetortoise.provenance import merge
 from codetortoise.services import Services
+from codetortoise.tidy import tidy
 from codetortoise.vcs.model import ChangeSet
 
 AUTHOR = "tortoise"
@@ -248,7 +249,7 @@ def _anchor_context(svc: Services, rid: int, comment: dict, ctx: AiContext, boar
         reader.ids.update(nodes)
         return "LAYER FUNCTIONS:\n" + _facts_for_nodes(im, nodes)
     flows = "\n".join(f"{f.id}: {f.title} — {f.what}" for f in board.flows)
-    finds = "\n".join(f"{f.id} [{f.severity}] {f.title}" for f in ctx.findings)
+    finds = "\n".join(f"{f.id} [{f.severity}] {tidy(f.title)}" for f in ctx.findings)
     reader.ids.update(f.id for f in ctx.findings)
     return f"CHANGE: {board.about.intent}\nFLOWS:\n{flows}\nFINDINGS:\n{finds}"
 
```

`backend/codetortoise/reading.py` (diff):

```diff
diff --git a/backend/codetortoise/reading.py b/backend/codetortoise/reading.py
index 0ff0cbe..6c0d666 100644
--- a/backend/codetortoise/reading.py
+++ b/backend/codetortoise/reading.py
@@ -19,6 +19,7 @@ from codetortoise.detectors.base import SEVERITY_RANK, Finding
 from codetortoise.pieces import PieceSet, node_cl
 from codetortoise.stories import Story, StoryDetail, StorySet
 from codetortoise.targets import UNKNOWN
+from codetortoise.tidy import tidy
 
 READING_VERSION = 1                   # bump with every change to the thread text's prompt or checks (keys its cache)
 _KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}
@@ -777,7 +778,7 @@ def build_checks(ss: StorySet, threads: list[Thread], conns: list[Connection], x
         story = story if story is not None else (home.get(related) if related else None)
         rows.append(Check(key=f"{kind}|{rel_path(x, path)}|{func or ''}|{_qual(x, related) if related else kw.pop('rel', '')}",
                           kind=kind, story=story, thread=thread_of.get(story) if story else kw.pop("thread", None),
-                          path=rel_path(x, path), line=line, function=func, node=place, text=text,
+                          path=rel_path(x, path), line=line, function=func, node=place, text=tidy(text),
                           source_line=_source(x, path, line, read_text), **kw))
 
     # 1–2: the strong model's verdicts; without one, high and medium findings (not header fan-out) to confirm
```

`backend/codetortoise/tidy.py` (new file):

```python
"""Evidence written for people (spec 2026-10-07-review-reading §12): no Python reprs, counts that read as words, arrows as
arrows. Findings are stored as the detectors wrote them (their titles anchor comments and verdicts); text is tidied
where people and models read it. Code in backticks is left alone. frontend/src/lib/tidy.ts keeps the same rules."""
import re

_ITEM = r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|True|False|None"""
_LIST = re.compile(rf"\[\s*((?:{_ITEM})(?:\s*,\s*(?:{_ITEM}))*)?\s*\]")
_DICT = re.compile(rf"\{{\s*((?:{_ITEM})\s*:\s*(?:{_ITEM})(?:\s*,\s*(?:{_ITEM})\s*:\s*(?:{_ITEM}))*)?\s*\}}")
_ONE = re.compile(_ITEM)
_COUNT = re.compile(r"\b(\d+) ((?:[A-Za-z_]+ )?[A-Za-z_]+)\(s\)( (?:reach|affect|call|use|need|read|write)\b)?")
_LISTED = re.compile(r"\b([A-Za-z_]+)\(s\) ([^;]+)")


def _plain(item: str) -> str:
    return item[1:-1] if item[:1] in "'\"" else item


def _items(body: str | None) -> list[str]:
    return [_plain(m.group(0)) for m in _ONE.finditer(body or "")]


def _list(m: re.Match) -> str:
    return ", ".join(_items(m.group(1))) or "none"


def _dict(m: re.Match) -> str:
    xs = _items(m.group(1))
    return ", ".join(f"{k} ({v})" for k, v in zip(xs[::2], xs[1::2], strict=True)) or "none"


def _count(m: re.Match) -> str:
    n, word, verb = int(m.group(1)), m.group(2), m.group(3) or ""
    if n != 1:
        return f"{n} {word}s{verb}"
    return f"1 {word}{verb + ('es' if verb.endswith(('ch', 'sh', 's', 'x')) else 's') if verb else ''}"


def _listed(m: re.Match) -> str:
    return f"{m.group(1)}{'s' if ',' in m.group(2) else ''} {m.group(2)}"


def _prose(text: str) -> str:
    text = text.replace(" -> ", " → ")
    text = _DICT.sub(_dict, _LIST.sub(_list, text))
    return _LISTED.sub(_listed, _COUNT.sub(_count, text))


def tidy(text: str, root: str | None = None) -> str:
    """`text` as a reader should see it, paths under the workspace `root` relative to it; the parts in backticks are code
    and stay as they are."""
    if root:
        text = text.replace(root.rstrip("/") + "/", "")
    parts = text.split("`")
    return "`".join(p if i % 2 else _prose(p) for i, p in enumerate(parts))
```

`backend/codetortoise/web/app.py` (diff):

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index bcf49c0..21eb0b8 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -21,6 +21,7 @@ from codetortoise.provenance import tag_board
 from codetortoise.reading import Check, Reading, with_marks
 from codetortoise.services import Services
 from codetortoise.swarm import SwarmError
+from codetortoise.tidy import tidy
 from codetortoise.vcs.p4runner import P4Error
 from codetortoise.vcs.source import SourceBinary, SourceNotAllowed, SourceTooLarge
 
@@ -402,7 +403,10 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
     @app.get("/api/reviews/{rid}/findings")
     def findings(rid: int, _: str = Depends(user_of)):
         review_or_404(rid)
-        return [f.model_dump() for f in store.list_findings(rid)]
+        root = canon(str(cfg.workspace.root))                     # text read by people; titles stay as stored (anchors)
+        return [f.model_copy(update={"summary": tidy(f.summary, root),
+                                     "evidence": [e.model_copy(update={"text": tidy(e.text, root)}) for e in f.evidence]})
+                .model_dump() for f in store.list_findings(rid)]
 
     @app.patch("/api/reviews/{rid}/findings/{fid}")
     def finding_state(rid: int, fid: str, body: FindingStateIn, _: str = Depends(owner_of)):
```

`frontend/src/lib/tidy.ts` (new file):

```ts
/** Evidence written for people (spec 2026-10-07-review-reading §12): the rules of backend/codetortoise/tidy.py, for the
 * finding text the server sends as the detectors wrote it (its titles anchor comments, so they are tidied only here). */

const ITEM = String.raw`'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|True|False|None`;
const LIST = new RegExp(String.raw`\[\s*((?:${ITEM})(?:\s*,\s*(?:${ITEM}))*)?\s*\]`, "g");
const DICT = new RegExp(String.raw`\{\s*((?:${ITEM})\s*:\s*(?:${ITEM})(?:\s*,\s*(?:${ITEM})\s*:\s*(?:${ITEM}))*)?\s*\}`, "g");
const ONE = new RegExp(ITEM, "g");
const COUNT = /\b(\d+) ((?:[A-Za-z_]+ )?[A-Za-z_]+)\(s\)( (?:reach|affect|call|use|need|read|write)\b)?/g;
const LISTED = /\b([A-Za-z_]+)\(s\) ([^;]+)/g;

const items = (body: string | undefined) => [...(body ?? "").matchAll(ONE)].map(([m]) => (/^['"]/.test(m) ? m.slice(1, -1) : m));

function prose(text: string): string {
  return text.replaceAll(" -> ", " → ")
    .replace(LIST, (_, body) => items(body).join(", ") || "none")
    .replace(DICT, (_, body) => {
      const xs = items(body);
      return xs.filter((_, i) => i % 2 === 0).map((k, i) => `${k} (${xs[2 * i + 1]})`).join(", ") || "none";
    })
    .replace(COUNT, (_, n: string, word: string, verb = "") =>
      n !== "1" ? `${n} ${word}s${verb}` : `1 ${word}${verb && verb + (/(ch|sh|s|x)$/.test(verb) ? "es" : "s")}`)
    .replace(LISTED, (_, word: string, rest: string) => `${word}${rest.includes(",") ? "s" : ""} ${rest}`);
}

/** `text` as a reader should see it; the parts in backticks are code and stay as they are. */
export function tidy(text: string): string {
  return text.split("`").map((p, i) => (i % 2 ? p : prose(p))).join("`");
}

/** "3 files", "1 flow"; an empty count is never shown (""). */
export function counted(n: number, noun: string): string {
  return n ? `${n} ${noun}${n === 1 ? "" : "s"}` : "";
}
```

`frontend/src/workspace/ClPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/ClPage.tsx b/frontend/src/workspace/ClPage.tsx
index 72ec45f..bf6a448 100644
--- a/frontend/src/workspace/ClPage.tsx
+++ b/frontend/src/workspace/ClPage.tsx
@@ -5,6 +5,7 @@ import { useMe } from "../App";
 import { SeverityBadge } from "../components/Badges";
 import Markdown from "../components/Markdown";
 import { descriptionParts, plainTitle } from "../lib/markdown";
+import { tidy } from "../lib/tidy";
 import { useWs } from "./context";
 import { short } from "./crumbs";
 import { Ticks } from "./NameText";
@@ -71,8 +72,8 @@ export default function ClPage({ cl }: { cl: number }) {
         <section aria-labelledby="ws-clfi"><h3 id="ws-clfi">Findings in its files</h3>
           <ul className="ws-findings">{findings.map((f) => (
             <li key={f.id}><SeverityBadge severity={f.severity} />{" "}
-              <Link to={ws.link(ws.item({ kind: "finding", fid: f.id }))} title={`Go to finding ${f.id}: ${short(f.title)}`}
-                    aria-label={`Go to finding ${f.id}: ${short(f.title)}`}>{f.title}</Link><span className="ws-handle">{f.id}</span></li>
+              <Link to={ws.link(ws.item({ kind: "finding", fid: f.id }))} title={`Go to finding ${f.id}: ${short(tidy(f.title))}`}
+                    aria-label={`Go to finding ${f.id}: ${short(tidy(f.title))}`}>{tidy(f.title)}</Link><span className="ws-handle">{f.id}</span></li>
           ))}</ul></section>
       )}
     </div></div>
```

`frontend/src/workspace/ClusterPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/ClusterPage.tsx b/frontend/src/workspace/ClusterPage.tsx
index 122eddc..fa06bf5 100644
--- a/frontend/src/workspace/ClusterPage.tsx
+++ b/frontend/src/workspace/ClusterPage.tsx
@@ -2,6 +2,7 @@ import { useEffect, useState } from "react";
 import { Link } from "react-router-dom";
 import { api, type Board } from "../api";
 import { stepCluster } from "../board/overview";
+import { counted } from "../lib/tidy";
 import { useWs } from "./context";
 import { short } from "./crumbs";
 import { pickFlow } from "./flows";
@@ -39,8 +40,8 @@ export default function ClusterPage({ cid }: { cid: string }) {
             <h2>{c.risk && <span className={`bd-pill ${c.risk}`}>{c.risk}</span>}{c.name}</h2>
             <span className="ws-pos">{step(-1)}<span>{at + 1} of {ov.clusters.length}</span>{step(1)}</span>
           </div>
-          <p className="ws-story-meta"><span className="muted">{layer ? `${layer} · ` : ""}{c.files.length} files · {c.changed} changed ·{" "}
-            {c.flows} flows · {c.findings} finding{c.findings === 1 ? "" : "s"}</span>
+          <p className="ws-story-meta"><span className="muted">{[layer, counted(c.files.length, "file"), c.changed ? `${c.changed} changed` : "",
+                                                                 counted(c.flows, "flow"), counted(c.findings, "finding")].filter(Boolean).join(" · ")}</span>
             {stories.map((s) => (
               <Link key={s.id} className="ws-chip" to={ws.link(ws.item({ kind: "story", sid: s.id, view: "steps" }))}
                     title={`Go to story ${s.id}: ${short(s.title)}`} aria-label={`Go to story ${s.id}: ${short(s.title)}`}>
```

`frontend/src/workspace/FindingPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/FindingPage.tsx b/frontend/src/workspace/FindingPage.tsx
index ecea60b..f10c4b7 100644
--- a/frontend/src/workspace/FindingPage.tsx
+++ b/frontend/src/workspace/FindingPage.tsx
@@ -5,6 +5,7 @@ import { SeverityBadge } from "../components/Badges";
 import Comments from "../components/Comments";
 import Explain from "../components/Explain";
 import { useAi } from "../lib/ai";
+import { tidy } from "../lib/tidy";
 import { citeTarget } from "../stories/stories";
 import type { Address } from "./address";
 import { useWs } from "./context";
@@ -33,7 +34,7 @@ export default function FindingPage({ fid }: { fid: string }) {
   const depots = [...(f.files ?? []), ...d.files.map((x) => x.depot), ...Object.values(d.names).flatMap((x) => (x.path ? [x.path] : []))];
   const step = (by: number) => {
     const to = d.findings[((i + by) % n + n) % n];
-    const label = `${by < 0 ? "Previous" : "Next"} finding: ${to.id} ${short(to.title)}`;
+    const label = `${by < 0 ? "Previous" : "Next"} finding: ${to.id} ${short(tidy(to.title))}`;
     return <Link className="bd-ibtn ws-step-btn" to={ws.link({ ...ws.item({ kind: "finding", fid: to.id }), details: true })} title={label} aria-label={label}>
       {by < 0 ? "‹" : "›"}</Link>;
   };
@@ -47,7 +48,7 @@ export default function FindingPage({ fid }: { fid: string }) {
     <div className="ws-page"><div className="ws-text ws-finding">
       <header className="ws-story-head">
         <div className="ws-story-title">
-          <h2><SeverityBadge severity={f.severity} /> {f.title}</h2>
+          <h2><SeverityBadge severity={f.severity} /> {tidy(f.title)}</h2>
           <span className="ws-pos">{step(-1)}<span>{f.id} of {n}</span>{step(1)}</span>
         </div>
         <p className="ws-story-meta">
@@ -99,12 +100,12 @@ export default function FindingPage({ fid }: { fid: string }) {
       </section>
       <section aria-labelledby="ws-ev">
         <h3 id="ws-ev">Evidence</h3>
-        <p><NameText text={f.summary} /></p>
+        <p><NameText text={tidy(f.summary)} /></p>
         <ul className="ws-evidence">{f.evidence.map((e, k) => {
           const depot = e.file ? depotFor(e.file, depots) : null, file = depot ?? e.file;
           const fileTail = file ? file.split("/").slice(-2).join("/") : null;
           return (
-            <li key={k} className={`sev-${e.severity}`}><NameText text={e.text} />
+            <li key={k} className={`sev-${e.severity}`}><NameText text={tidy(e.text)} />
               {depot ? <> <Link className="mono small" to={ws.link(ws.opened({ file: depot, line: e.line }))}
                                 title={`Open ${fileTail}${e.line ? ` at line ${e.line}` : ""}`}
                                 aria-label={`Open ${fileTail}${e.line ? ` at line ${e.line}` : ""}`}>{fileTail}{e.line ? `:${e.line}` : ""}</Link></>
```

`frontend/src/workspace/Rail.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Rail.tsx b/frontend/src/workspace/Rail.tsx
index 665dbad..9ba59ee 100644
--- a/frontend/src/workspace/Rail.tsx
+++ b/frontend/src/workspace/Rail.tsx
@@ -5,6 +5,7 @@ import { keys, load, loadWidth, save } from "../board/prefs";
 import Resizer from "../board/Resizer";
 import HeadlinePill from "../components/HeadlinePill";
 import { plainTitle } from "../lib/markdown";
+import { tidy } from "../lib/tidy";
 import { isOpen, letter, openCount } from "../reading/checks";
 import { reviewTargets, sections } from "../stories/stories";
 import { INDEX_TABS, type Place, samePlace } from "./address";
@@ -172,9 +173,9 @@ export default function Rail({ show, onPick, hidden = false }: { show: string |
       {d.ready && section("findings", `Findings (${d.findings.length})`, (
         bySeverity(d.findings).map((g) => (
           <div key={g.severity} className="ws-group"><h3>{g.severity}</h3><ul>{g.findings.map((f) => (
-            <li key={f.id}>{row({ kind: "finding", fid: f.id }, `Go to finding ${f.id}: ${short(f.title)}`, <span className="ws-row-top">
+            <li key={f.id}>{row({ kind: "finding", fid: f.id }, `Go to finding ${f.id}: ${short(tidy(f.title))}`, <span className="ws-row-top">
               <span className={`ws-sev ${f.severity}`} aria-hidden />
-              <span className="ws-row-title">{f.title}</span>
+              <span className="ws-row-title">{tidy(f.title)}</span>
               <span className="ws-handle">{f.id}</span>
               {ss?.finding_story[f.id] && <span className="ws-handle">{ss.finding_story[f.id]}</span>}
             </span>, f.state !== "open" ? "done" : "")}</li>
```

`frontend/src/workspace/StorySteps.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/StorySteps.tsx b/frontend/src/workspace/StorySteps.tsx
index 5163d6c..8f879f4 100644
--- a/frontend/src/workspace/StorySteps.tsx
+++ b/frontend/src/workspace/StorySteps.tsx
@@ -2,6 +2,7 @@ import { Link } from "react-router-dom";
 import { flowSteps } from "../board/phone/flowSteps";
 import type { BoardFlow, StoryDetail } from "../board/types";
 import { SeverityBadge } from "../components/Badges";
+import { tidy } from "../lib/tidy";
 import { useWs } from "./context";
 import { short } from "./crumbs";
 import NameText from "./NameText";
@@ -57,8 +58,8 @@ export default function StorySteps({ detail, flow }: { detail: StoryDetail; flow
           <h3 id="ws-sf">Findings</h3>
           <ul className="ws-findings">{mine.map((f) => (
             <li key={f.id}><SeverityBadge severity={f.severity} />{" "}
-              <Link to={ws.link(ws.item({ kind: "finding", fid: f.id }))} title={`Go to finding ${f.id}: ${short(f.title)}`}
-                    aria-label={`Go to finding ${f.id}: ${short(f.title)}`}>{f.title}</Link><span className="ws-handle">{f.id}</span></li>
+              <Link to={ws.link(ws.item({ kind: "finding", fid: f.id }))} title={`Go to finding ${f.id}: ${short(tidy(f.title))}`}
+                    aria-label={`Go to finding ${f.id}: ${short(tidy(f.title))}`}>{tidy(f.title)}</Link><span className="ws-handle">{f.id}</span></li>
           ))}</ul>
         </section>
       )}
```

`frontend/src/workspace/WholePage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/WholePage.tsx b/frontend/src/workspace/WholePage.tsx
index fd29eae..a17a864 100644
--- a/frontend/src/workspace/WholePage.tsx
+++ b/frontend/src/workspace/WholePage.tsx
@@ -5,6 +5,7 @@ import { bandsOf, linkLines } from "../board/overview";
 import { sideEffectFiles } from "../board/sideEffects";
 import type { Board } from "../board/types";
 import Comments from "../components/Comments";
+import { counted } from "../lib/tidy";
 import { useWs } from "./context";
 import { pickFlow } from "./flows";
 import GraphView from "./graph/GraphView";
@@ -47,8 +48,8 @@ export function MapSection() {
               <Link key={c.id} to={ws.link(ws.item({ kind: "cluster", cid: c.id }))} className={`ov-block ${c.risk ?? "none"}`}
                     title={`Open ${c.name}`} aria-label={`Open ${c.name}`}>
                 <div className="nm">{c.name} {c.risk && <span className={`sev ${c.risk}`}>{c.risk.toUpperCase()}</span>}</div>
-                <div className="ct">{c.files.length} files · {c.changed} changed · {c.flows} flows
-                  {c.findings > 0 && ` · ${c.findings} finding${c.findings === 1 ? "" : "s"}`}</div>
+                <div className="ct">{[counted(c.files.length, "file"), c.changed ? `${c.changed} changed` : "", counted(c.flows, "flow"),
+                                      counted(c.findings, "finding")].filter(Boolean).join(" · ")}</div>
                 {linkLines(ov, c.id, 3).map((l) => <div key={l} className="ln">{l}</div>)}
                 {c.also.length > 0 && <div className="also">also in {c.also.map((lv) => layerName(lv) ?? `L${lv}`).join(", ")}</div>}
               </Link>
```

`frontend/src/workspace/crumbs.ts` (diff):

```diff
diff --git a/frontend/src/workspace/crumbs.ts b/frontend/src/workspace/crumbs.ts
index a3feb4f..f79dea6 100644
--- a/frontend/src/workspace/crumbs.ts
+++ b/frontend/src/workspace/crumbs.ts
@@ -1,6 +1,7 @@
 /** The centre's breadcrumb (spec 2026-10-04-review-workspace §2.4): every part but the current one is a link up. */
 import type { Finding } from "../api";
 import type { Story } from "../board/types";
+import { tidy } from "../lib/tidy";
 import { href, type Place } from "./address";
 
 export interface Crumb { label: string; to: string | null; handle?: string }
@@ -48,7 +49,7 @@ export function crumbs(place: Place, c: CrumbContext): Crumb[] {
     }
     case "finding": {
       const f = c.findings.find((x) => x.id === place.fid);
-      return [home, section("Findings", "findings"), f ? { label: short(f.title), handle: f.id, to: null } : missing()];
+      return [home, section("Findings", "findings"), f ? { label: short(tidy(f.title)), handle: f.id, to: null } : missing()];
     }
     case "cl": {
       const cl = c.cls.find((x) => x.cl === place.cl);
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_reading.py tests/test_tidy.py tests/test_tortoise.py tests/test_web.py -q`
Expected: PASS: `100 passed`

Run: `cd frontend && npx vitest run src/lib/tidy.test.ts src/workspace/crumbs.test.ts`
Expected: PASS: `Tests 14 passed (14)`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-pages.spec.ts e2e/workspace.spec.ts`
Expected: PASS: `20 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `613 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 171 passed (171)`; Playwright `1 failed, 101 passed` (in the replay, the first run's failures were timeouts under load; `npx playwright test --last-failed` then gave `1 passed`)

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_reading.py backend/tests/test_tidy.py backend/tests/test_tortoise.py backend/tests/test_web.py frontend/e2e/workspace-pages.spec.ts frontend/e2e/workspace.spec.ts frontend/src/lib/tidy.test.ts frontend/src/workspace/crumbs.test.ts backend/codetortoise/llm/review.py backend/codetortoise/llm/stories.py backend/codetortoise/llm/storyboard.py backend/codetortoise/llm/tortoise.py backend/codetortoise/reading.py backend/codetortoise/tidy.py backend/codetortoise/web/app.py frontend/src/lib/tidy.ts frontend/src/workspace/ClPage.tsx frontend/src/workspace/ClusterPage.tsx frontend/src/workspace/FindingPage.tsx frontend/src/workspace/Rail.tsx frontend/src/workspace/StorySteps.tsx frontend/src/workspace/WholePage.tsx frontend/src/workspace/crumbs.ts
git commit -m "feat(reading): evidence reads as people write it — no Python reprs, counts with their nouns, paths relative to the workspace, no empty counts"
```

### Task 14: Lab check (review 19 and the owner's work review)

Spec §13 (lab). There is no code here: read lab review 19 with and without the strong model, then the owner's work review, and record the results in `lab/README.md`.

- [ ] **Step 1: Rebuild review 19 with the strong model**

In `$LAB/tortoise.yaml`, keep the `llm.strong` block for the strong model the owner chose (its key in `TORTOISE_STRONG_KEY` in `$LAB/env.sh`; never print it). Run `source $LAB/env.sh && $CT serve --config $LAB/tortoise.yaml`. As the owner, open review 19 and press **Re-run stories (fresh)**. If the P4 ticket has expired, log in again as `lab/README.md` says.
Expected:
- the reading stage says "N thread(s), M connection(s) shown, K check(s); thread text by <model>";
- the overview names each thread in at most 6 words, and every arc's text names a caller, a type, a condition, a folder or "nothing besides arriving in CL …";
- To check lists the strong model's hazards first, then Caller not updated, Result handled the old way and Unchanged reader rows, each with its source line;
- no evidence shows a Python dict or list, an absolute path or "0 flows".

- [ ] **Step 2: Read it without the strong model**

Remove `llm.strong`, restart and re-run review 19.
Expected: the reading stage says "fixed thread text (no strong model)"; thread names read "`<function>` in <folder>"; the headline is labelled "rules only"; the threads and connections are the same as in Step 1.

- [ ] **Step 3: Mark a check and re-run**

Press Looks fine on one To check row, re-run, and reload.
Expected: the row is still marked, by the same user, below the open rows.

- [ ] **Step 4: The owner's work review**

The owner reviews their own large multi-CL change at work on this branch and notes where the overview, the story pages or To check still read as disconnected.

- [ ] **Step 5: Record the results**

Add a "Review reading" subsection to `lab/README.md`: review 19's threads (name, stories), the connections shown, the headline and To check counts with and without the strong model, and the owner's notes.

- [ ] **Step 6: Commit**

```bash
git add lab/README.md
git commit -m "docs(lab): review reading on review 19"
```

## Finish

Every task's suite is green, and the lab README records review 19 read as threads. The branch stays `review-reading`; merging it is the owner's decision. Use superpowers:finishing-a-development-branch.
