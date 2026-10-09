# Review Introduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The review's overview opens with an introduction: a collapsible "How to read this page", a fuller "change as a whole", a "Where to start" route through the threads, and a paragraph per thread, written by the strong model and checked, with fixed text from the rules otherwise.

**Architecture:** `reading.py` gains the data (`Thread.intro/files/modules`, `RouteStep`, `Reading.route`) and the rules' text, always made in `build_reading`. The existing threads call (`llm/threads.py`) also picks each thread's key files and modules. A new tier-1 call (`llm/intro.py`) runs after it in the pipeline's reading stage and rewrites the whole, the thread intros and the route, each part checked on its own and cached in an `intro_text` blob. The overview (`Overview.tsx`) shows the new parts.

**Tech Stack:** Python 3 / FastAPI / pydantic v2 / SQLite (backend), React 19 + TypeScript, vitest, Playwright (frontend).

**Spec:** `docs/superpowers/specs/2026-10-09-review-introduction-design.md`

## Global Constraints

- Work in worktree `.worktrees/intro` on branch `intro`. Never commit to `main`.
- Commit with `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`; end every message with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.
- pytest, from `backend/`: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no <files>`
- ruff, from `backend/`: `/media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/ruff check --output-format concise codetortoise tests`
- vitest, from `frontend/`: `npx vitest run <files>`; typecheck: `npx tsc -b --noEmit` (or `npm run build`, which also typechecks).
- e2e, from `frontend/`: `npm run build` first (the server serves `frontend/dist`), then `TMPDIR=$CLAUDE_JOB_DIR/tmp/pw TORTOISE_CMD="env PYTHONPATH=/media/anoop/ssd_1/Work/CodeTortoise/.worktrees/intro/backend /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test <specs>`. Known flakes (pass on `--last-failed`): startReview 60 s timeouts, `workspace-detail.spec.ts:134`.
- Never use `uv`, bare `git stash`, `git clean -fdx`, or `pkill -f`. Use `$CLAUDE_JOB_DIR/tmp` for temporary files. Never print `TORTOISE_LLM_KEY` or `TORTOISE_STRONG_KEY`.
- Limits, verbatim from the spec: key files at most **8**, key modules at most **4**, files listed to the threads call at most **40** per thread then "+N more"; the intro's whole **4–6** sentences, a thread intro **3–5** sentences, a route reason **1** sentence; open checks in the intro prompt at most **6**; the fixed intro names at most **3** directories and **3** check kinds, then "and N more".
- The intro prompt's thread header is `THREAD DETAILS (id | name | purpose | CLs | open checks):`. It must never contain the text `THREADS (id`, which the test and fake-model dispatchers match for the threads call.
- The explainer's storage key is `ct.intro.open`, read and written only through `frontend/src/board/prefs.ts` `load`/`save`.
- Model text passes `_styled(text, "explanation")` (`llm/storyboard.py`); cites are checked against `llm/threads.py` `_ids(reading, ss)`; sentences are counted with `llm/threads.py` `_SENT`.
- Code style: match the surrounding code (dense one-line docstrings citing the spec, 120-column lines, no new abbreviations).

## Review Focus

1. **A review with no threads** (every story is tests, or no changed code): no intro call is made, `route` is `[]`, the overview hides Where to start, and nothing crashes. Pinned in Task 1 (`fixed_introduction` with no threads) and Task 4 (the pipeline skips the call).
2. **A thread whose stories change no function** (only macros, types or a removed file): its files and modules are empty, its fixed intro has no "in …" part, the threads prompt shows no files line and the threads call's pick for it is not checked. Pinned in Task 1 (`fixed_intro` without modules) and Task 2 (no files line, no pick note).
3. **A file at the workspace root** (`main.c`): it can be a key file but gives no module; the threads call may not name `/` or `""` as a module. Pinned in Task 1 (`pick_files`) and Task 2 (`_pick` rejects a module that is not a directory prefix).
4. **A stored reading from before this change**, opened in the new UI: no `intro`, `route`, `files` fields; the cards show the purpose, Where to start is hidden, nothing throws. Pinned in Task 1 (old JSON loads) and Task 5 (`routeRows` with `route` absent).
5. **The explainer when storage is blocked** (private mode, storage throwing): it opens and toggling it never throws. Pinned in Task 5 (vitest with throwing storage).

---

## File Structure

- Modify `backend/codetortoise/reading.py`: new fields, `RouteStep`, `thread_files`, `module_of`, `pick_files`, `fixed_intro`, `fixed_route`, `fixed_introduction`; wired into `build_reading`; `READING_VERSION = 2`.
- Modify `backend/codetortoise/llm/threads.py`: files listed per thread, `"files"`/`"modules"` asked and checked (`_pick`).
- Create `backend/codetortoise/llm/intro.py`: the introduction call (`INTRO_VERSION`, `prompt`, `write_intro`).
- Modify `backend/codetortoise/llm/ledger.py`: `"intro"` in `TIER1`.
- Modify `backend/codetortoise/pipeline.py`: thread files to the threads call and its cache, the fixed intros refreshed, the intro call and its cache, the stage message.
- Modify `backend/tests/scripted_llm.py`: `intro_answer(user)` shared by the scripted strong models.
- Modify tests: `backend/tests/test_reading.py`, `backend/tests/test_llm_threads.py`, `backend/tests/test_pipeline.py`; create `backend/tests/test_llm_intro.py`.
- Modify `frontend/src/reading/types.ts`, `frontend/src/board/prefs.ts`, `frontend/src/reading/overview.ts` (+ test), `frontend/src/workspace/Overview.tsx`, `frontend/src/workspace/workspace.css`.
- Modify `frontend/e2e/fake_llm.py`, `frontend/e2e/workspace-reading.spec.ts`, `frontend/e2e/workspace-tier1.spec.ts`.

## Clarifications of the spec made here

- **Route reasons with hazards.** The spec's "1 hazard and 2 checks open." counts hazards among the checks, which reads as 3 things. The plan words it so nothing is counted twice: `h` hazards and `r` other open checks give "1 hazard and 2 other checks open." (both), "1 hazard open." (hazards only), "2 checks open." / "1 check open." (no hazard), "Nothing is open." (none).
- **Fixed intro joins.** Directories join as "`a/`", "`a/` and `b/`", "`a/`, `b/` and `c/`", past 3 "… and N more"; check kinds join with ", " as in the spec's example, past 3 "… and N more".
- **Modules in the threads call's pick.** At least one module is required when the rules found any module for that thread (otherwise an answer with no modules would erase them); a thread whose files are all at the root may answer none.
- **The rules' intros follow the threads call's pick.** The fixed intro names the thread's modules, so the pipeline remakes the fixed intros after the threads call (`fixed_introduction` again) when it changed the picks.
- **Stage message without a strong model** stays "fixed thread text (no strong model)"; the introduction suffixes ("; introduction by big", "; introduction by small (the strong model failed)", "; fixed introduction") appear only when a strong model is configured and the review has threads.

---

### Task 1: The introduction's data and the rules' text

**Files:**
- Modify: `backend/codetortoise/reading.py` (Thread at :45, Reading at :181, `build_reading` at :1121)
- Test: `backend/tests/test_reading.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (in `codetortoise.reading`):
  - `Thread.intro: str = ""`, `Thread.intro_source: Literal["template","llm"] = "template"`, `Thread.files: list[str]`, `Thread.modules: list[str]`, `Thread.files_source: Literal["template","llm"] = "template"`
  - `class RouteStep(BaseModel): thread: str; reason: str; skim: bool = False`
  - `Reading.route: list[RouteStep]`, `Reading.route_source: Literal["template","llm"] = "template"`
  - `MAX_FILES = 8`, `MAX_MODULES = 4`
  - `thread_files(threads: list[Thread], per: dict[str, StoryReading]) -> dict[str, list[tuple[str, int]]]`
  - `module_of(path: str) -> str`
  - `pick_files(files: list[tuple[str, int]]) -> tuple[list[str], list[str]]`
  - `fixed_intro(t: Thread, checks: list[Check], titles: dict[str, str]) -> str`
  - `fixed_route(threads: list[Thread], checks: list[Check], kinds: dict[str, str]) -> list[RouteStep]`
  - `fixed_introduction(reading: Reading, ss: StorySet) -> None` (sets every template intro and a template route, in place)

- [ ] **Step 1: Write the failing tests**

Add `Reading`, `RouteStep`, `StoryReading`, `WhereFile`, `WhereFn`, `fixed_intro`, `fixed_introduction`, `fixed_route`, `module_of`, `pick_files`, `thread_files` to the `from codetortoise.reading import (...)` list at the top of `backend/tests/test_reading.py` (keep it sorted), then append:

```python
# ---- the review's introduction (spec 2026-10-09-review-introduction §3)
def _ck(kind, thread="T1", n=0):
    return Check(key=f"{kind}|{thread}|{n}", kind=kind, thread=thread, text="t")


def test_a_threads_key_files_are_its_most_changed_files_and_its_modules_their_directories():
    files = [(f"d{i % 3}/f{i}.c", 10 - i) for i in range(10)] + [("main.c", 1)]
    top, modules = pick_files(files)
    assert top == [f"d{i % 3}/f{i}.c" for i in range(8)]
    assert modules == ["d0/", "d1/", "d2/"]                         # d0 and d1 hold 3 of the top 8 each, d2 two
    assert pick_files([("main.c", 2)]) == (["main.c"], [])           # a root file has no module
    assert module_of("a/b/c.c") == "a/b/" and module_of("c.c") == ""


def test_modules_are_capped_at_four_most_files_first_then_by_path():
    files = [("e/1.c", 5), ("e/2.c", 5), ("a/1.c", 4), ("b/1.c", 3), ("c/1.c", 2), ("d/1.c", 1)]
    assert pick_files(files)[1] == ["e/", "a/", "b/", "c/"]


def test_thread_files_count_each_changed_function_once_most_first_then_by_path():
    t = Thread(id="T1", name="n", purpose="p", stories=["S1", "S2"])
    per = {"S1": StoryReading(story="S1", where=[WhereFile(path="b/x.c", functions=[WhereFn(node="N1", label="f")]),
                                                 WhereFile(path="a/y.c", functions=[WhereFn(node="N2", label="g")])]),
           "S2": StoryReading(story="S2", where=[WhereFile(path="b/x.c", functions=[WhereFn(node="N1", label="f"),
                                                                                    WhereFn(node="N3", label="h")])])}
    assert thread_files([t], per) == {"T1": [("b/x.c", 2), ("a/y.c", 1)]}


def test_a_threads_fixed_intro_says_where_what_is_open_and_where_it_starts():
    t = Thread(id="T1", name="n", purpose="p", stories=["S2", "S1", "S3"], cls=[101],
               modules=["driver/", "service/"])
    titles = {"S1": "b", "S2": "`uart_send` can now return -2", "S3": "c"}
    assert fixed_intro(t, [_ck("confirm"), _ck("result", n=1), _ck("confirm", "T2")], titles) == (
        "3 stories in `driver/` and `service/` across CL 101. 2 checks open: Confirm, Result handled the old way. "
        "Starts with “`uart_send` can now return -2”.")


def test_a_fixed_intro_caps_directories_and_check_kinds_and_says_nothing_is_open():
    t = Thread(id="T1", name="n", purpose="p", stories=["S1"], cls=[1, 2], modules=["a/", "b/", "c/", "d/"])
    assert fixed_intro(t, [], {"S1": "s"}) == (
        "1 story in `a/`, `b/`, `c/` and 1 more across CL 1 and CL 2. Nothing is open. Starts with “s”.")
    kinds = ["hazard", "confirm", "caller", "result", "reader"]
    text = fixed_intro(t, [_ck(k, n=i) for i, k in enumerate(kinds)], {"S1": "s"})
    assert "5 checks open: Hazard, Confirm, Caller not updated and 2 more." in text


def test_a_fixed_intro_without_modules_or_cls_leaves_those_parts_out():
    t = Thread(id="T1", name="n", purpose="p", stories=["S1"])
    assert fixed_intro(t, [_ck("ask")], {"S1": "s"}) == "1 story. 1 check open: Ask the author. Starts with “s”."


def test_the_fixed_route_keeps_the_threads_order_moves_skim_threads_last_and_says_why():
    threads = [Thread(id="T1", name="a", purpose="p", stories=["S1"], open_checks=3),
               Thread(id="T2", name="b", purpose="p", stories=["S2", "S3"]),
               Thread(id="T3", name="c", purpose="p", stories=["S4"], open_checks=1),
               Thread(id="T4", name="d", purpose="p", stories=["S5"], open_checks=1),
               Thread(id="T5", name="e", purpose="p", stories=["S6"])]
    checks = [_ck("hazard"), _ck("confirm", n=1), _ck("caller", n=2), _ck("confirm", "T3"), _ck("hazard", "T4")]
    kinds = {"S1": "behaviour", "S2": "mechanical", "S3": "mechanical", "S4": "mechanical", "S5": "other", "S6": "other"}
    assert [(s.thread, s.reason, s.skim) for s in fixed_route(threads, checks, kinds)] == [
        ("T1", "1 hazard and 2 other checks open.", False), ("T3", "1 check open.", False),
        ("T4", "1 hazard open.", False), ("T5", "Nothing is open.", False),
        ("T2", "Only repeated edits and tests; skim it.", True)]


def test_fixed_introduction_keeps_what_the_strong_model_wrote_and_handles_no_threads():
    ss = _set(["N1"])
    r = Reading(threads=[Thread(id="T1", name="n", purpose="p", stories=["S1"], intro="Mine.", intro_source="llm")],
                route=[RouteStep(thread="T1", reason="Mine.")], route_source="llm")
    fixed_introduction(r, ss)
    assert (r.threads[0].intro, r.route[0].reason) == ("Mine.", "Mine.")
    empty = Reading()
    fixed_introduction(empty, ss)
    assert empty.route == [] and empty.route_source == "template"


def test_build_reading_gives_each_thread_its_key_files_modules_intro_and_a_route():
    c, ss = _chain()
    reading, _ = build_reading(ss, c)
    t1 = next(t for t in reading.threads if "S3" in t.stories)
    assert (t1.files, t1.modules, t1.files_source) == (["drv/uart.c", "svc/flush.c", "svc/log.c"], ["svc/", "drv/"],
                                                       "template")
    assert t1.intro.startswith("3 stories in `svc/` and `drv/` across CL 1. ") and t1.intro.endswith("Starts with “story 3”.")
    assert [s.thread for s in reading.route] == [t.id for t in reading.threads] and reading.route_source == "template"


def test_a_reading_stored_before_the_introduction_loads_with_its_defaults():
    r = Reading.model_validate({"whole": "w", "threads": [{"id": "T1", "name": "n", "purpose": "p", "stories": ["S1"]}]})
    t = r.threads[0]
    assert (t.intro, t.intro_source, t.files, t.modules, t.files_source) == ("", "template", [], [], "template")
    assert (r.route, r.route_source) == ([], "template")
```

- [ ] **Step 2: Run them to verify they fail**

Run (from `backend/`): `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no tests/test_reading.py`
Expected: collection error `ImportError: cannot import name 'RouteStep' from 'codetortoise.reading'`.

- [ ] **Step 3: Implement**

In `backend/codetortoise/reading.py`:

Change the version line and add the constants under it:

```python
READING_VERSION = 2                   # bump with every change to the thread text's prompt or checks (keys its cache)
MAX_FILES, MAX_MODULES = 8, 4         # a thread's key files and modules (spec 2026-10-09-review-introduction §3.3)
SHOWN_DIRS = SHOWN_KINDS = 3          # how many directories and check kinds a thread's fixed intro names
SKIM_KINDS = {"mechanical", "tests"}
```

Extend `Thread`:

```python
class Thread(BaseModel):
    id: str
    name: str
    purpose: str
    text_source: Literal["template", "llm"] = "template"
    stories: list[str] = Field(default_factory=list)  # in reading order
    cls: list[int] = Field(default_factory=list)
    open_checks: int = 0
    intro: str = ""                                   # 3–5 sentences (spec 2026-10-09-review-introduction §3)
    intro_source: Literal["template", "llm"] = "template"
    files: list[str] = Field(default_factory=list)    # its key files, workspace-relative, at most MAX_FILES
    modules: list[str] = Field(default_factory=list)  # its key directories ("driver/"), at most MAX_MODULES
    files_source: Literal["template", "llm"] = "template"
```

Add just above `class Reading`:

```python
class RouteStep(BaseModel):
    """One step of Where to start (spec 2026-10-09-review-introduction §3.1): a thread and why to read it then."""
    thread: str
    reason: str
    skim: bool = False
```

Add to `Reading`, after `whole_source`:

```python
    route: list[RouteStep] = Field(default_factory=list)       # every thread once, in reading order
    route_source: Literal["template", "llm"] = "template"
```

Add after `fixed_whole`:

```python
def thread_files(threads: list[Thread], per: dict[str, StoryReading]) -> dict[str, list[tuple[str, int]]]:
    """Each thread's changed files (workspace-relative) with how many of its changed functions each holds, most first,
    then by path (spec 2026-10-09-review-introduction §3.3)."""
    out: dict[str, list[tuple[str, int]]] = {}
    for t in threads:
        fns: dict[str, set[str]] = defaultdict(set)
        for sid in t.stories:
            for wf in per[sid].where if sid in per else []:
                fns[wf.path].update(f.node for f in wf.functions)
        out[t.id] = sorted(((p, len(ns)) for p, ns in fns.items() if p), key=lambda pn: (-pn[1], pn[0]))
    return out


def module_of(path: str) -> str:
    """A file's directory ending in "/"; "" for a file at the workspace root."""
    d = posixpath.dirname(path)
    return d + "/" if d else ""


def pick_files(files: list[tuple[str, int]]) -> tuple[list[str], list[str]]:
    """The rules' key files (the most changed, at most MAX_FILES) and modules (their directories, most files first, then
    by path, at most MAX_MODULES) from `thread_files`' list (§3.3)."""
    top = [p for p, _ in files[:MAX_FILES]]
    count = Counter(m for p in top if (m := module_of(p)))
    return top, sorted(count, key=lambda m: (-count[m], m))[:MAX_MODULES]


def _some(xs: list[str], cap: int) -> str:
    """"a", "a and b", "a, b and c"; past `cap`: "a, b, c and 2 more"."""
    if len(xs) > cap:
        return ", ".join(xs[:cap]) + f" and {len(xs) - cap} more"
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def fixed_intro(t: Thread, checks: list[Check], titles: dict[str, str]) -> str:
    """A thread's introduction without the strong model (§3.2): its stories and where they are, what is open, and the
    story it starts with."""
    n = len(t.stories)
    where = f" in {_some([f'`{m}`' for m in t.modules], SHOWN_DIRS)}" if t.modules else ""
    across = f" across {_cls(t.cls)}" if t.cls else ""
    out = [f"{n} stor{'y' if n == 1 else 'ies'}{where}{across}."]
    mine = [k for k in checks if k.thread == t.id]
    if mine:
        kinds = [KIND_LABEL[kd] for kd in CHECK_ORDER if any(k.kind == kd for k in mine)]
        more = f" and {len(kinds) - SHOWN_KINDS} more" if len(kinds) > SHOWN_KINDS else ""
        out.append(f"{len(mine)} check{'' if len(mine) == 1 else 's'} open: {', '.join(kinds[:SHOWN_KINDS])}{more}.")
    else:
        out.append("Nothing is open.")
    if t.stories:
        out.append(f"Starts with “{titles.get(t.stories[0], t.stories[0])}”.")
    return " ".join(out)


def _route_reason(t: Thread, checks: list[Check], skim: bool) -> str:
    if skim:
        return "Only repeated edits and tests; skim it."
    mine = [k for k in checks if k.thread == t.id]
    h = sum(k.kind == "hazard" for k in mine)
    rest = len(mine) - h

    def n(x: int, word: str) -> str:
        return f"{x} {word}{'' if x == 1 else 's'}"
    if h and rest:
        return f"{n(h, 'hazard')} and {n(rest, 'other check')} open."
    if h:
        return f"{n(h, 'hazard')} open."
    return f"{n(rest, 'check')} open." if rest else "Nothing is open."


def fixed_route(threads: list[Thread], checks: list[Check], kinds: dict[str, str]) -> list[RouteStep]:
    """Where to start without the strong model (§3.2): the threads' own order (no call or data link runs between two
    threads), threads with nothing open and only repeated edits or tests last, marked skim."""
    steps = []
    for t in threads:
        skim = t.open_checks == 0 and bool(t.stories) and all(kinds.get(s) in SKIM_KINDS for s in t.stories)
        steps.append(RouteStep(thread=t.id, reason=_route_reason(t, checks, skim), skim=skim))
    return [s for s in steps if not s.skim] + [s for s in steps if s.skim]


def fixed_introduction(reading: Reading, ss: StorySet) -> None:
    """Every thread's fixed intro and the fixed route, in place; text the strong model wrote stays."""
    titles = {s.id: s.title for s in ss.stories}
    for t in reading.threads:
        if t.intro_source == "template":
            t.intro = fixed_intro(t, reading.checks, titles)
    if reading.route_source == "template":
        reading.route = fixed_route(reading.threads, reading.checks, {s.id: s.kind for s in ss.stories})
```

In `build_reading`, replace the final `return reading, per` with:

```python
    files = thread_files(threads, per)
    for t in threads:
        t.files, t.modules = pick_files(files[t.id])
    fixed_introduction(reading, ss)
    return reading, per
```

Note: `fixed_route`'s test sets `open_checks` by hand while `checks` holds the rows; in `build_reading` both come from the same rows (`t.open_checks = sum(1 for k in rows if k.thread == t.id)`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no tests/test_reading.py`
Expected: all pass.

- [ ] **Step 5: Run the whole backend suite and ruff**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no > $CLAUDE_JOB_DIR/tmp/t1.log 2>&1; tail -5 $CLAUDE_JOB_DIR/tmp/t1.log` and the ruff command.
Expected: all pass (the version bump only changes cache keys), ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/reading.py backend/tests/test_reading.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): each thread gets key files, modules and a fixed intro; the reading gets a fixed route (skim threads last)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The threads call picks each thread's key files and modules

**Files:**
- Modify: `backend/codetortoise/llm/threads.py`
- Modify: `backend/codetortoise/pipeline.py` (reading stage, ~:470–495)
- Modify: `backend/tests/test_pipeline.py` (`_one_story_per_cl` at :402; the thread-text test at :497)
- Modify: `frontend/e2e/fake_llm.py` (`threads()` at :60)
- Test: `backend/tests/test_llm_threads.py`

**Interfaces:**
- Consumes: `thread_files`, `module_of`, `fixed_introduction`, `MAX_FILES`, `MAX_MODULES` and the new `Thread` fields from Task 1.
- Produces:
  - `llm.threads.MAX_LISTED = 40`
  - `llm.threads.prompt(reading, ss, cls, files: dict[str, list[tuple[str, int]]] | None = None) -> str` — each thread with files gets a line `  files (changed functions): drv/uart.c (3), svc/log.c (1)` (then ` +N more` past 40).
  - `llm.threads.write_threads(strong, ledger, rid, reading, ss, cls, weak=None, files=None) -> tuple[list[str], str | None]` — sets `t.files`, `t.modules`, `t.files_source="llm"` for an accepted pick; a failed pick adds "N file pick(s)" to the note.
  - Pipeline blob `thread_text` gains `"picks": {thread id: [files, modules, files_source]}`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_llm_threads.py` (add `import pytest` is not needed):

```python
FILES = {"T1": [("drv/uart.c", 2), ("drv/regs.h", 1), ("main.c", 1)], "T2": [("drv/init.c", 1)], "T3": []}


def _with_picks(**picks):
    """GOOD with each thread's files and modules: `picks` maps a thread id to (files, modules)."""
    return {**GOOD, "threads": [{**t, "files": picks.get(t["id"], ([], []))[0], "modules": picks.get(t["id"], ([], []))[1]}
                                for t in GOOD["threads"]]}


def test_the_prompt_lists_each_threads_files_with_their_changed_functions_capped_at_40():
    r, ss = _reading()
    many = {"T1": [(f"d/f{i:02}.c", 1) for i in range(45)]}
    llm = ScriptedLlm(lambda s, u: GOOD)
    write_threads(llm, None, None, r, ss, {}, files=many)
    line = next(x for x in llm.prompts[0].splitlines() if x.startswith("  files (changed functions): "))
    assert line.startswith("  files (changed functions): d/f00.c (1), d/f01.c (1)")
    assert line.endswith("d/f39.c (1) +5 more")
    assert sum(x.startswith("  files") for x in llm.prompts[0].splitlines()) == 1     # T2 and T3 have none listed
    assert '"files"' in llm.prompts[0] and '"modules"' in llm.prompts[0]


def test_an_accepted_pick_sets_the_threads_key_files_and_modules():
    r, ss = _reading()
    r.threads[0].modules = ["drv/"]
    r.threads[1].modules = ["drv/"]
    answer = _with_picks(T1=(["drv/uart.c", "main.c"], ["drv/"]), T2=(["drv/init.c"], ["drv/"]))
    notes, _ = write_threads(ScriptedLlm(lambda s, u: answer), None, None, r, ss, {}, files=FILES)
    assert notes == []
    assert [(t.files, t.modules, t.files_source) for t in r.threads[:2]] == [
        (["drv/uart.c", "main.c"], ["drv/"], "llm"), (["drv/init.c"], ["drv/"], "llm")]
    assert r.threads[2].files_source == "template"                     # nothing listed: nothing to pick


def test_a_pick_naming_an_unlisted_file_a_module_holding_none_too_many_or_none_keeps_the_rules_pick():
    many = [(f"drv/f{i}.c", 1) for i in range(9)]
    cases = [(["drv/nope.c"], ["drv/"]),                              # not one of the thread's files
             (["drv/uart.c"], ["svc/"]),                              # a module holding none of them
             (["drv/uart.c"], ["drv"]),                               # not a directory ending in "/"
             (["drv/uart.c"], ["/"]),
             ([], ["drv/"]),                                          # no file
             (["drv/uart.c"], []),                                    # no module though the rules found one
             ([f"drv/f{i}.c" for i in range(9)], ["drv/"]),           # more than 8 files
             (["drv/uart.c"], ["drv/", "a/", "b/", "c/", "d/"])]       # more than 4 modules
    for files, modules in cases:
        r, ss = _reading()
        r.threads[0].files, r.threads[0].modules = ["drv/uart.c"], ["drv/"]
        listed = {"T1": many + [("drv/uart.c", 1)]} if len(files) == 9 else FILES
        notes, _ = write_threads(ScriptedLlm(lambda s, u, f=files, m=modules: _with_picks(T1=(f, m))), None, None,
                                 r, ss, {}, files={"T1": listed["T1"]})
        assert (r.threads[0].files, r.threads[0].modules, r.threads[0].files_source) == (
            ["drv/uart.c"], ["drv/"], "template"), (files, modules)
        assert notes == ["thread text: 1 file pick(s) failed the checks; their fixed text stays"], (files, modules)


def test_a_thread_whose_files_are_all_at_the_root_may_pick_no_module():
    r, ss = _reading()
    notes, _ = write_threads(ScriptedLlm(lambda s, u: _with_picks(T1=(["main.c"], []))), None, None, r, ss, {},
                             files={"T1": [("main.c", 1)]})
    assert notes == [] and (r.threads[0].files, r.threads[0].modules, r.threads[0].files_source) == (["main.c"], [], "llm")
```

In `backend/tests/test_pipeline.py`, extend `_one_story_per_cl`'s threads branch so the scripted model picks each thread's first listed file and its directory:

```python
    if "THREADS (id" in user:
        rows = re.findall(r"^(T\d+) \|.*?\| (S\d+)", user, re.M)
        first = dict(re.findall(r"^(T\d+) \|.*\n  files \(changed functions\): (\S+) \(", user, re.M))

        def pick(t):
            f = first.get(t)
            return {"files": [f], "modules": [f.rsplit("/", 1)[0] + "/"] if "/" in f else []} if f else {}
        return {"threads": [{"id": t, "name": "UART driver changes", "purpose": "This changes the UART driver.",
                             "cites": [sid], **pick(t)} for t, sid in rows],
                "whole": "The change reworks the UART driver. Its callers see new results.", "whole_cites": ["T1"],
                "connections": []}
```

and in `test_the_strong_model_names_the_threads_once_and_a_rerun_reuses_the_text`, after the first `reading = …` line add:

```python
    t1 = reading["threads"][0]
    assert t1["files_source"] == "llm" and len(t1["files"]) == 1
```

and after the re-run's last line add:

```python
    assert svc.store.get_blob(rid, "reading")["threads"][0]["files"] == t1["files"]      # the cached pick
```

- [ ] **Step 2: Run them to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no tests/test_llm_threads.py tests/test_pipeline.py -k "pick or files or names_the_threads_once"`
Expected: FAIL — `TypeError: write_threads() got an unexpected keyword argument 'files'`, and the pipeline test fails on `files_source == "llm"`.

- [ ] **Step 3: Implement the threads call**

In `backend/codetortoise/llm/threads.py`:

Import `from codetortoise.reading import MAX_FILES, MAX_MODULES, Reading` (replacing the `Reading` import) and add `MAX_LISTED = 40` under `NAME_WORDS`.

Replace `SYSTEM` and `ASK`:

```python
SYSTEM = ("You are a senior C/C++ reviewer explaining a change to other reviewers. Use only what you are given. Reply "
          'with one JSON object: {"threads": [{"id", "name", "purpose", "cites", "files", "modules"}], "whole", '
          '"whole_cites", "connections": [{"a", "b", "text"}]}. ' + STYLE)

ASK = """Each thread is a group of stories joined by calls or shared data. For each thread write a name (at most 6 \
words, what it does) and a purpose (one sentence). For each thread with files listed, also pick "files": at most 8 of \
its listed files, the ones a reviewer should look at first, and "modules": at most 4 directories (each ending in "/") \
holding those files that name the parts of the code it touches. Then write "whole": the change as a whole in 2 to 4 \
sentences, saying how the threads connect. You may reword each connection's text, but keep every name in backticks and \
every CL number it has. When the only tie between two threads is that they arrived together, say so plainly. Cite the \
ids (T1, S2, N4, CL12) that support each thread's text in "cites" and the whole's in "whole_cites"; cite nothing that is \
not listed."""
```

Add `files` and `modules` to `_T`:

```python
class _T(BaseModel):
    id: str
    name: str = ""
    purpose: str = ""
    cites: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
```

Replace `prompt`:

```python
def prompt(reading: Reading, ss: StorySet, cls: dict[int, str], files: dict[str, list[tuple[str, int]]] | None = None) -> str:
    """`files`: each thread's changed files with their changed functions, most first (reading.thread_files)."""
    by = {s.id: s for s in ss.stories}
    lines = ["THREADS (id | open checks | CLs | stories: id title: purpose):"]
    for t in reading.threads:
        stories = "; ".join(f"{s} {by[s].title}" + (f": {by[s].purpose}" if by[s].purpose else "") for s in t.stories)
        lines.append(f"{t.id} | {t.open_checks} open checks | {', '.join(f'CL {c}' for c in t.cls) or '-'} | {stories}")
        fs = (files or {}).get(t.id, [])
        if fs:
            more = f" +{len(fs) - MAX_LISTED} more" if len(fs) > MAX_LISTED else ""
            lines.append("  files (changed functions): " + ", ".join(f"{p} ({n})" for p, n in fs[:MAX_LISTED]) + more)
    lines.append("CONNECTIONS (a | b | kind | text | facts):")
    lines += [f"{k.a} | {k.b} | {k.kind} | {k.text} | {' '.join(k.facts) or '-'}" for k in reading.connections]
    used = sorted({c for t in reading.threads for c in t.cls})
    if used:
        lines.append("CL DESCRIPTIONS:")
        lines += [f"CL {c} (a hint from its author, not the source of truth): {cls.get(c, '').strip() or '(none)'}"
                  for c in used]
    return ASK + "\n\n" + "\n".join(lines)
```

Add after `_keeps`:

```python
def _pick(a: _T, listed: list[str], need_module: bool) -> tuple[list[str], list[str]] | None:
    """A thread's key files and modules from the answer, or None when they fail the check (spec
    2026-10-09-review-introduction §4.0): listed files only, directories holding one of them, within the limits."""
    files = list(dict.fromkeys(f.strip() for f in a.files if f.strip()))
    modules = list(dict.fromkeys(m.strip() for m in a.modules if m.strip()))
    ok = (1 <= len(files) <= MAX_FILES and len(modules) <= MAX_MODULES and (bool(modules) or not need_module)
          and all(f in listed for f in files)
          and all(m.endswith("/") and len(m) > 1 and any(f.startswith(m) for f in listed) for m in modules))
    return (files, modules) if ok else None
```

Change `write_threads`' signature and docstring, and its body from `got = {…}` to the end:

```python
def write_threads(strong: LlmClient, ledger: Ledger | None, rid: int | None, reading: Reading, ss: StorySet,
                  cls: dict[int, str], weak: LlmClient | None = None,
                  files: dict[str, list[tuple[str, int]]] | None = None) -> tuple[list[str], str | None]:
    """Reword `reading` in place from one checked answer and take its pick of each thread's key files and modules
    (`files`: reading.thread_files); returns notes on what kept its fixed text, and the model that wrote the text (None:
    the fixed text stays). The strong model failing is tried fresh, then on the weak model (spec
    2026-10-08-llm-robustness §6)."""
    text = prompt(reading, ss, cls, files)
```

(the `ask`/`try_tiers`/`said`/`ids`/`cited` lines stay as they are), then:

```python
    got = {t.id: t for t in out.threads}
    listed = {tid: [p for p, _ in fs[:MAX_LISTED]] for tid, fs in (files or {}).items()}
    bad_threads = bad_picks = 0
    for t in reading.threads:
        a = got.get(t.id)
        name, purpose = (a.name.strip(), a.purpose.strip()) if a else ("", "")
        if (a and cited(a.cites) and name and len(name.split()) <= NAME_WORDS and _titled(name) and purpose
                and len(_SENT.split(purpose)) == 1 and _styled(purpose, "explanation")):
            t.name, t.purpose, t.text_source = name, purpose, "llm"
        else:
            bad_threads += 1
        if listed.get(t.id):
            pick = _pick(a, listed[t.id], bool(t.modules)) if a else None
            if pick:
                t.files, t.modules, t.files_source = pick[0], pick[1], "llm"
            else:
                bad_picks += 1
```

(the whole and connections blocks stay), and the ending becomes:

```python
    if not (bad_threads or bad_picks or bad_whole or bad_conns):
        return said, tried.model
    parts = ([f"{bad_threads} thread(s)"] if bad_threads else []) + ([f"{bad_picks} file pick(s)"] if bad_picks else []) + \
            (["the whole"] if bad_whole else []) + ([f"{bad_conns} connection(s)"] if bad_conns else [])
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return said + [f"thread text: {joined} failed the checks; their fixed text stays"], tried.model
```

Update the module docstring's check list: "…a connection's rewording keeps its cited names and CLs; a thread's key files are its listed files and its modules directories holding them; anything that fails keeps the fixed text from reading.py."

- [ ] **Step 4: Implement the pipeline's side**

In `backend/codetortoise/pipeline.py`, change the import line to `from codetortoise.reading import READING_VERSION, build_reading, fixed_introduction, headline_facts, thread_files`, then in `read()` replace the block from `else:` (after `told = "fixed thread text (no strong model)"`) down to the `told = (…)` assignment with:

```python
        else:
            cls_text = {m.cl: m.description for m in ctx["cs"].cls}
            files = thread_files(r.threads, per)
            key = hashlib.sha256(f"{READING_VERSION}|{strong.model}|{threads_prompt(r, bs.stories, cls_text, files)}"
                                 .encode()).hexdigest()
            cached = store.get_blob(rid, "thread_text")
            if cached and cached.get("key") == key and not fresh:
                by: str | None = strong.model
                for t in r.threads:
                    t.name, t.purpose, t.text_source = cached["threads"].get(t.id, (t.name, t.purpose, t.text_source))
                    t.files, t.modules, t.files_source = cached["picks"].get(t.id, (t.files, t.modules, t.files_source))
                r.whole, r.whole_source = cached["whole"], cached["whole_source"]
                for k in r.connections:
                    k.text = cached["connections"].get(f"{k.a}-{k.b}", k.text)
            else:
                notes, by = write_threads(svc.strong, svc.ledger, rid, r, bs.stories, cls_text, weak=svc.llm, files=files)
                if not notes:
                    store.put_blob(rid, "thread_text", {
                        "key": key, "threads": {t.id: (t.name, t.purpose, t.text_source) for t in r.threads},
                        "picks": {t.id: (t.files, t.modules, t.files_source) for t in r.threads},
                        "whole": r.whole, "whole_source": r.whole_source,
                        "connections": {f"{k.a}-{k.b}": k.text for k in r.connections}})
            fixed_introduction(r, bs.stories)          # the fixed intros name the modules the threads call picked
            told = (f"thread text by {by}" if by == strong.model else
                    f"thread text by {by} (the strong model failed)" if by else "fixed thread text (the AI's answer failed)")
```

(`READING_VERSION` is now 2, so a `thread_text` blob without `"picks"` never matches the key.)

- [ ] **Step 5: Teach the e2e fake strong model to pick files**

In `frontend/e2e/fake_llm.py`, replace `threads()`:

```python
def threads(user: str) -> dict:
    """Each thread named after its first story, its first listed file its key file; the whole cites the first thread;
    connections keep their text."""
    rows = re.findall(r"^(T\d+) \|.*?\| (S\d+) ", user, re.M)
    first = dict(re.findall(r"^(T\d+) \|.*\n  files \(changed functions\): (\S+) \(", user, re.M))

    def pick(t: str) -> dict:
        f = first.get(t)
        return {"files": [f], "modules": [f.rsplit("/", 1)[0] + "/"] if "/" in f else []} if f else {}
    return {"threads": [{"id": t, "name": f"Thread of {sid}", "purpose": f"This thread holds {sid} and what builds on it.",
                         "cites": [sid], **pick(t)} for t, sid in rows],
            "whole": "The change reworks the UART driver and what calls it. Each thread says what it adds.",
            "whole_cites": [rows[0][0]] if rows else [], "connections": []}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no tests/test_llm_threads.py tests/test_pipeline.py`
Expected: all pass.

- [ ] **Step 7: Whole backend suite and ruff**

Run the full pytest (output to `$CLAUDE_JOB_DIR/tmp/t2.log`, read the tail) and ruff.
Expected: all pass, ruff clean.

- [ ] **Step 8: Commit**

```bash
git add backend/codetortoise/llm/threads.py backend/codetortoise/pipeline.py backend/tests/test_llm_threads.py backend/tests/test_pipeline.py frontend/e2e/fake_llm.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(threads): the threads call picks each thread's key files and modules from its listed files, checked; cached with the thread text

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The introduction call

**Files:**
- Create: `backend/codetortoise/llm/intro.py`
- Modify: `backend/codetortoise/llm/ledger.py:21` (TIER1)
- Modify: `backend/tests/scripted_llm.py` (add `intro_answer`)
- Test: `backend/tests/test_llm_intro.py`

**Interfaces:**
- Consumes: `Reading`, `RouteStep`, `KIND_LABEL`, the `Thread` fields from Task 1; `_ids`, `_SENT` from `llm/threads.py`; `try_tiers`, `tried_note`, `done_text`, `TiersFailed` from `llm/tiers.py`; `Refused`, `Ledger` from `llm/ledger.py`.
- Produces:
  - `llm.intro.INTRO_VERSION = 1`, `llm.intro.CHECKS_SHOWN = 6`
  - `llm.intro.prompt(reading: Reading, ss: StorySet, cls: dict[int, str]) -> str` (header `THREAD DETAILS (id | name | purpose | CLs | open checks):`)
  - `llm.intro.write_intro(strong, ledger, rid, reading, ss, cls, weak=None) -> tuple[list[str], str | None]` — sets `reading.whole/whole_source`, each `t.intro/intro_source`, `reading.route/route_source` for the parts that pass; notes "introduction: …".
  - `ledger.TIER1` contains `"intro"`.
  - `tests/scripted_llm.py` `intro_answer(user: str) -> dict`: a passing answer for any intro prompt (used by Task 4).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/scripted_llm.py`:

```python
def intro_answer(user: str) -> dict:
    """A passing introduction for any intro prompt (spec 2026-10-09-review-introduction §4.3): every thread introduced
    citing its first story, the route in the threads' order."""
    import re
    body = user.split("THREAD DETAILS (id", 1)[1].split("CONNECTIONS (a", 1)[0]
    rows = re.findall(r"^(T\d+) \| ", body, re.M)
    first = dict(re.findall(r"^(T\d+) \|.*\n(?:  (?:modules|files): .*\n)*  stories: (S\d+) ", body, re.M))
    return {"whole": "The change reworks the UART driver. It spans the driver and the code that calls it. Each thread "
                     "below says what it adds. The main risk is a caller that misses a new result.",
            "whole_cites": rows[:1],
            "threads": [{"id": t, "intro": f"This thread holds {first.get(t, t)} and what builds on it. Its code sits in "
                                           "the driver. Its open checks say what to confirm.",
                         "cites": [first.get(t, t)]} for t in rows],
            "route": [{"thread": t, "reason": "This thread comes next in the change.", "skim": False, "cites": [t]}
                      for t in rows]}
```

Create `backend/tests/test_llm_intro.py`:

```python
"""The review's introduction from the strong model (spec 2026-10-09-review-introduction §4)."""
from scripted_llm import ScriptedLlm, intro_answer
from test_llm_threads import _reading

from codetortoise.llm.client import LlmError
from codetortoise.llm.intro import prompt, write_intro
from codetortoise.llm.ledger import TIER1, Refused
from codetortoise.reading import Check, RouteStep


def _intro_reading():
    r, ss = _reading()
    r.threads[0].modules, r.threads[0].files = ["drv/"], ["drv/uart.c", "drv/regs.h"]
    r.checks = [Check(key=f"confirm|{i}", kind="confirm", thread="T1", text=f"`send` row {i}") for i in range(7)]
    r.route = [RouteStep(thread=t.id, reason="Nothing is open.") for t in r.threads]
    for t in r.threads:
        t.intro = f"Fixed intro of {t.id}."
    return r, ss


GOOD = {"whole": "The change makes UART lengths unsigned. It also sets the baud rate at init. An engine step arrives "
                 "with CL 12. The main risk is a caller that still passes a signed length.",
        "whole_cites": ["T1", "T2", "T3"],
        "threads": [{"id": "T1", "intro": "Send now takes an unsigned length. The change sits in `drv/`. A caller "
                                          "passing a negative length breaks.", "cites": ["S1", "N1"]},
                    {"id": "T2", "intro": "Init programs the baud rate. The change sits in `drv/`. Nothing is open.",
                     "cites": ["S2"]},
                    {"id": "T3", "intro": "The engine takes a new step. It arrives with CL 12. Nothing is open.",
                     "cites": ["S3", "CL12"]}],
        "route": [{"thread": "T1", "reason": "It has the open checks.", "skim": False, "cites": ["T1"]},
                  {"thread": "T2", "reason": "Init runs before any send.", "skim": False, "cites": ["T2"]},
                  {"thread": "T3", "reason": "It only arrived in the same CL.", "skim": True, "cites": ["T3", "CL12"]}]}


def _with(**part):
    return {**GOOD, **part}


def test_the_prompt_holds_each_threads_modules_files_stories_open_checks_and_the_connections():
    r, ss = _intro_reading()
    text = prompt(r, ss, {11: "Make send unsigned"})
    assert "THREAD DETAILS (id | name | purpose | CLs | open checks):" in text and "THREADS (id" not in text
    assert "T1 | `send` in drv | s1 | CL 11 | 2" in text
    assert "  modules: drv/" in text and "  files: drv/uart.c, drv/regs.h" in text
    assert "  stories: S1 Send gains a length type: Sends bytes (behaviour)" in text
    assert "  open checks: Confirm: `send` row 0; " in text and "Confirm: `send` row 5 +1 more" in text
    assert "`send` row 6" not in text
    assert "T1 | T2 | caller | both run inside `main`" in text
    assert "CL 11 (a hint from its author, not the source of truth): Make send unsigned" in text


def test_an_accepted_answer_writes_the_whole_every_intro_and_the_route():
    r, ss = _intro_reading()
    assert write_intro(ScriptedLlm(lambda s, u: GOOD), None, None, r, ss, {}) == ([], "big")
    assert r.whole.startswith("The change makes UART lengths unsigned.") and r.whole_source == "llm"
    assert [(t.intro_source, t.intro.split(".")[0]) for t in r.threads] == [
        ("llm", "Send now takes an unsigned length"), ("llm", "Init programs the baud rate"),
        ("llm", "The engine takes a new step")]
    assert [(s.thread, s.reason, s.skim) for s in r.route] == [
        ("T1", "It has the open checks.", False), ("T2", "Init runs before any send.", False),
        ("T3", "It only arrived in the same CL.", True)] and r.route_source == "llm"


def test_each_failing_part_keeps_its_fixed_text_and_only_that_part():
    cases = {
        "whole": (_with(whole="The change makes lengths unsigned. It sets the baud. It adds a step."), "the whole"),
        "intro6": (_with(threads=[{**GOOD["threads"][0], "intro": "A. B. C. D. E. F."}, *GOOD["threads"][1:]]),
                   "1 thread(s)"),
        "unlisted": (_with(threads=[{**GOOD["threads"][0], "cites": ["S9"]}, *GOOD["threads"][1:]]), "1 thread(s)"),
        "missing": (_with(route=GOOD["route"][:2]), "the route"),
        "twice": (_with(route=[*GOOD["route"][:2], GOOD["route"][0]]), "the route"),
        "two sentences": (_with(route=[{**GOOD["route"][0], "reason": "It is first. It has checks."},
                                       *GOOD["route"][1:]]), "the route"),
    }
    for name, (answer, part) in cases.items():
        r, ss = _intro_reading()
        notes, by = write_intro(ScriptedLlm(lambda s, u, a=answer: a), None, None, r, ss, {})
        assert by == "big" and notes == [f"introduction: {part} kept the fixed text"], name
        assert (r.whole_source == "template") == (part == "the whole"), name
        assert (r.route_source == "template") == (part == "the route"), name
        assert [t.intro_source for t in r.threads] == (["template", "llm", "llm"] if part == "1 thread(s)" else ["llm"] * 3), name
        if part == "1 thread(s)":
            assert r.threads[0].intro == "Fixed intro of T1.", name
        if part == "the route":
            assert [s.reason for s in r.route] == ["Nothing is open."] * 3, name


def test_several_failing_parts_are_named_together():
    r, ss = _intro_reading()
    notes, _ = write_intro(ScriptedLlm(lambda s, u: {"whole": "", "threads": [], "route": []}), None, None, r, ss, {})
    assert notes == ["introduction: the whole, 3 thread(s) and the route kept the fixed text"]


def test_a_failed_or_refused_call_keeps_every_fixed_text_and_says_why():
    r, ss = _intro_reading()
    notes, by = write_intro(ScriptedLlm(lambda s, u: RuntimeError("down")), None, None, r, ss, {})
    assert notes == ["introduction: big: RuntimeError: down; fresh try: RuntimeError: down; the fixed text stays"]
    assert by is None and r.route_source == "template" and r.threads[0].intro == "Fixed intro of T1."

    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            assert (purpose, target) == ("intro", "intro")
            raise Refused("this review has used its 10 tier-1 AI calls")
    notes, _ = write_intro(ScriptedLlm(lambda s, u: GOOD), Budget(), 1, r, ss, {})
    assert notes == ["introduction: AI budget: this review has used its 10 tier-1 AI calls; the fixed text stays"]


def test_the_introduction_the_strong_model_fails_is_written_by_the_weak_model():
    r, ss = _intro_reading()
    notes, by = write_intro(ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x")), None, None, r, ss,
                            {}, weak=ScriptedLlm(lambda s, u: GOOD, model="small"))
    assert by == "small" and r.route_source == "llm"
    assert notes == ["introduction: big: invalid JSON twice; fresh try: invalid JSON twice; small wrote it"]


def test_the_introduction_counts_against_the_tier_1_budget():
    assert "intro" in TIER1


def test_the_scripted_intro_answer_passes_every_check():
    r, ss = _intro_reading()
    llm = ScriptedLlm(lambda s, u: intro_answer(u))
    assert write_intro(llm, None, None, r, ss, {}) == ([], "big")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no tests/test_llm_intro.py`
Expected: collection error `ModuleNotFoundError: No module named 'codetortoise.llm.intro'`.

- [ ] **Step 3: Implement**

In `backend/codetortoise/llm/ledger.py:21`:

```python
TIER1 = ("stories", "stories_merge", "review", "threads", "intro")   # strong-model calls: their own budget (spec 2026-10-05 §9)
```

Create `backend/codetortoise/llm/intro.py`:

```python
"""The strong model introduces the review (spec 2026-10-09-review-introduction §4): the change as a whole in 4 to 6
sentences, each thread in 3 to 5, and the order to read the threads in with a reason for each.

One tier-1 call per review, after the thread text so it sees the final thread names. Each part is checked on its own:
cites only listed ids, the sentence counts, the house style; the route must hold every thread exactly once. A part that
fails keeps its fixed text from reading.py.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import _styled
from codetortoise.llm.style import STYLE
from codetortoise.llm.threads import _SENT, _ids
from codetortoise.llm.tiers import TiersFailed, done_text, tried_note, try_tiers
from codetortoise.reading import KIND_LABEL, Reading, RouteStep
from codetortoise.stories import StorySet

INTRO_VERSION = 1                     # bump with every change to the introduction's prompt or checks (keys its cache)
CHECKS_SHOWN = 6

SYSTEM = ("You are a senior C/C++ reviewer introducing a change to reviewers who have not seen it. Use only what you "
          'are given. Reply with one JSON object: {"whole", "whole_cites", "threads": [{"id", "intro", "cites"}], '
          '"route": [{"thread", "reason", "skim", "cites"}]}. ' + STYLE)

ASK = """Each thread is a group of stories joined by calls or shared data. Write "whole": the change as a whole in 4 to \
6 sentences, saying its purpose, its scope (its CLs, the parts of the code it touches, how many threads) and its main \
risk. For each thread write "intro": 3 to 5 sentences saying what it changes and why, where in the code, what could go \
wrong (from its open checks) and how much is open. Then write "route": every thread once, in the order a reviewer \
should read them, each with a one-sentence "reason"; set "skim" to true for a thread worth only a skim. Cite the ids \
(T1, S2, N4, CL12) behind each part in "whole_cites" and "cites"; cite nothing that is not listed."""


class _Intro(BaseModel):
    id: str
    intro: str = ""
    cites: list[str] = Field(default_factory=list)


class _Step(BaseModel):
    thread: str
    reason: str = ""
    skim: bool = False
    cites: list[str] = Field(default_factory=list)


class _Out(BaseModel):
    whole: str = ""
    whole_cites: list[str] = Field(default_factory=list)
    threads: list[_Intro] = Field(default_factory=list)
    route: list[_Step] = Field(default_factory=list)


def prompt(reading: Reading, ss: StorySet, cls: dict[int, str]) -> str:
    by = {s.id: s for s in ss.stories}
    lines = ["THREAD DETAILS (id | name | purpose | CLs | open checks):"]
    for t in reading.threads:
        lines.append(f"{t.id} | {t.name} | {t.purpose} | {', '.join(f'CL {c}' for c in t.cls) or '-'} | {t.open_checks}")
        if t.modules:
            lines.append(f"  modules: {', '.join(t.modules)}")
        if t.files:
            lines.append(f"  files: {', '.join(t.files)}")
        lines.append("  stories: " + "; ".join(f"{s} {by[s].title}" + (f": {by[s].purpose}" if by[s].purpose else "")
                                               + f" ({by[s].kind})" for s in t.stories if s in by))
        mine = [k for k in reading.checks if k.thread == t.id]
        if mine:
            more = f" +{len(mine) - CHECKS_SHOWN} more" if len(mine) > CHECKS_SHOWN else ""
            lines.append("  open checks: " + "; ".join(f"{KIND_LABEL[k.kind]}: {k.text}" for k in mine[:CHECKS_SHOWN])
                         + more)
    lines.append("CONNECTIONS (a | b | kind | text):")
    lines += [f"{k.a} | {k.b} | {k.kind} | {k.text}" for k in reading.connections]
    used = sorted({c for t in reading.threads for c in t.cls})
    if used:
        lines.append("CL DESCRIPTIONS:")
        lines += [f"CL {c} (a hint from its author, not the source of truth): {cls.get(c, '').strip() or '(none)'}"
                  for c in used]
    return ASK + "\n\n" + "\n".join(lines)


def write_intro(strong: LlmClient, ledger: Ledger | None, rid: int | None, reading: Reading, ss: StorySet,
                cls: dict[int, str], weak: LlmClient | None = None) -> tuple[list[str], str | None]:
    """Write `reading`'s introduction in place from one checked answer; returns notes on the parts that kept their fixed
    text, and the model that answered (None: every fixed text stays). The strong model failing is tried fresh, then on
    the weak model."""
    text = prompt(reading, ss, cls)

    def ask(llm: LlmClient) -> _Out:
        return llm.complete_json(SYSTEM, text, _Out)
    try:
        tried = try_tiers(ledger, rid, "intro", "intro", ask, strong, weak)
    except Refused as e:
        return [f"introduction: AI budget: {e.reason}; the fixed text stays"], None
    except TiersFailed as e:  # the fixed text stands
        return [tried_note("introduction", e.failures, "the fixed text stays")], None
    out = tried.value
    said = [] if tried.tier == "strong" else [tried_note("introduction", tried.failures, done_text(tried, "wrote it"))]
    ids = _ids(reading, ss)

    def ok(text: str, cites: list[str], lo: int, hi: int) -> bool:
        cs = [c.replace(" ", "") for c in cites]
        return (bool(text) and bool(cs) and all(c in ids for c in cs) and lo <= len(_SENT.split(text)) <= hi
                and _styled(text, "explanation"))
    whole = out.whole.strip()
    bad_whole = not ok(whole, out.whole_cites, 4, 6)
    if not bad_whole:
        reading.whole, reading.whole_source = whole, "llm"
    got = {a.id: a for a in out.threads}
    bad_threads = 0
    for t in reading.threads:
        a = got.get(t.id)
        intro = a.intro.strip() if a else ""
        if a and ok(intro, a.cites, 3, 5):
            t.intro, t.intro_source = intro, "llm"
        else:
            bad_threads += 1
    bad_route = not (sorted(s.thread for s in out.route) == sorted(t.id for t in reading.threads)
                     and all(ok(s.reason.strip(), s.cites, 1, 1) for s in out.route))
    if not bad_route:
        reading.route = [RouteStep(thread=s.thread, reason=s.reason.strip(), skim=s.skim) for s in out.route]
        reading.route_source = "llm"
    if not (bad_whole or bad_threads or bad_route):
        return said, tried.model
    parts = (["the whole"] if bad_whole else []) + ([f"{bad_threads} thread(s)"] if bad_threads else []) + \
            (["the route"] if bad_route else [])
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return said + [f"introduction: {joined} kept the fixed text"], tried.model
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no tests/test_llm_intro.py tests/test_llm_threads.py tests/test_ledger.py`
Expected: all pass.

- [ ] **Step 5: Whole backend suite and ruff**

Run the full pytest (to `$CLAUDE_JOB_DIR/tmp/t3.log`, read the tail) and ruff.
Expected: all pass, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/llm/intro.py backend/codetortoise/llm/ledger.py backend/tests/scripted_llm.py backend/tests/test_llm_intro.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(intro): a tier-1 call writes the fuller whole, each thread's intro and the route, each part checked on its own

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The reading stage makes the introduction

**Files:**
- Modify: `backend/codetortoise/pipeline.py` (imports; `read()` after the thread text)
- Modify: `backend/tests/test_pipeline.py`
- Modify: `frontend/e2e/fake_llm.py` (`answer()` at :69; new `intro()`)

**Interfaces:**
- Consumes: `INTRO_VERSION`, `prompt`, `write_intro` from `llm/intro.py` (Task 3); `RouteStep`, `fixed_introduction` (Task 1); `intro_answer` from `tests/scripted_llm.py` (Task 3).
- Produces: blob `intro_text` = `{"key", "whole", "whole_source", "threads": {id: [intro, intro_source]}, "route": [RouteStep dicts], "route_source"}`; the reading stage message ends "; introduction by <model>", "; introduction by <model> (the strong model failed)" or "; fixed introduction" when a strong model is configured and the review has threads.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_pipeline.py`:

At the top of `_one_story_per_cl`, after `import re`, add:

```python
    from scripted_llm import intro_answer
    if "THREAD DETAILS (id" in user:
        return intro_answer(user)
```

In `test_the_strong_model_names_the_threads_once_and_a_rerun_reuses_the_text`, change `assert msg.endswith("thread text by big")` to `assert msg.endswith("thread text by big; introduction by big")`.

Append:

```python
def test_the_strong_model_introduces_the_review_once_a_rerun_reuses_it_and_a_fresh_run_asks_again(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _one_story_per_cl)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    r = svc.store.get_blob(rid, "reading")
    assert r["whole_source"] == r["route_source"] == "llm"
    assert {t["intro_source"] for t in r["threads"]} == {"llm"}
    assert [s["thread"] for s in r["route"]] == [t["id"] for t in r["threads"]]
    asked = lambda: sum("THREAD DETAILS (id" in p for p in llm.prompts)     # noqa: E731
    assert asked() == 1
    first = llm.prompts.index(next(p for p in llm.prompts if "THREAD DETAILS (id" in p))
    assert any("THREADS (id" in p for p in llm.prompts[:first])            # after the thread text
    run_review(rid, svc)
    assert asked() == 1 and svc.store.get_blob(rid, "reading")["route_source"] == "llm"
    run_review(rid, svc, fresh=True)
    assert asked() == 2


def test_an_introduction_that_fails_its_checks_keeps_the_rules_text_and_says_so(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    _strong(svc, lambda s, u: {} if "THREAD DETAILS (id" in u else _one_story_per_cl(s, u))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = next(s for s in svc.store.list_stages(rid) if s["name"] == "reading")
    assert st["status"] == "degraded"
    assert "; introduction by big; introduction: the whole, " in st["message"]
    assert st["message"].endswith("thread(s) and the route kept the fixed text")
    r = svc.store.get_blob(rid, "reading")
    assert r["route_source"] == "template" and r["route"] and r["whole_source"] == "llm"     # the threads call's whole
    assert all(t["intro"].startswith(f"{len(t['stories'])} stor") for t in r["threads"])
    assert svc.store.get_blob(rid, "intro_text") is None


def test_without_a_strong_model_the_reading_has_the_rules_introduction(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    r = svc.store.get_blob(rid, "reading")
    assert [s["thread"] for s in r["route"]] == [t["id"] for t in r["threads"]] and r["route_source"] == "template"
    assert all("Starts with “" in t["intro"] and t["intro_source"] == "template" for t in r["threads"])
    assert all(t["files"] and t["files_source"] == "template" for t in r["threads"])
```

If `store.get_blob` returns something other than `None` for a missing blob (check `codetortoise/store.py` `get_blob`), change the last assertion of the second test to match what it returns for a blob never written (for example `{}`), and record that in the ledger as a ruling.

- [ ] **Step 2: Run them to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no tests/test_pipeline.py -k "introduc or names_the_threads_once"`
Expected: FAIL — the strong-model tests find no `THREAD DETAILS` prompt (`asked() == 0`) and the message lacks "; introduction by big"; the no-strong-model test passes already (Task 1 made the rules text) — that is expected: it pins the rules path through the pipeline.

- [ ] **Step 3: Implement**

In `backend/codetortoise/pipeline.py`, add imports:

```python
from codetortoise.llm.intro import INTRO_VERSION, write_intro
from codetortoise.llm.intro import prompt as intro_prompt
```

and add `RouteStep` to the `codetortoise.reading` import. In `read()`, directly after the `told = (f"thread text by {by}" …)` assignment inside the strong-model `else:` branch, add:

```python
            if r.threads:
                ikey = hashlib.sha256(f"{INTRO_VERSION}|{strong.model}|{intro_prompt(r, bs.stories, cls_text)}"
                                      .encode()).hexdigest()
                icached = store.get_blob(rid, "intro_text")
                if icached and icached.get("key") == ikey and not fresh:
                    iby: str | None = strong.model
                    r.whole, r.whole_source = icached["whole"], icached["whole_source"]
                    for t in r.threads:
                        t.intro, t.intro_source = icached["threads"].get(t.id, (t.intro, t.intro_source))
                    r.route, r.route_source = [RouteStep(**s) for s in icached["route"]], icached["route_source"]
                else:
                    said, iby = write_intro(svc.strong, svc.ledger, rid, r, bs.stories, cls_text, weak=svc.llm)
                    notes = notes + said
                    if not said:
                        store.put_blob(rid, "intro_text", {
                            "key": ikey, "whole": r.whole, "whole_source": r.whole_source,
                            "threads": {t.id: (t.intro, t.intro_source) for t in r.threads},
                            "route": [s.model_dump() for s in r.route], "route_source": r.route_source})
                told += (f"; introduction by {iby}" if iby == strong.model else
                         f"; introduction by {iby} (the strong model failed)" if iby else "; fixed introduction")
```

- [ ] **Step 4: Teach the e2e fake strong model the introduction**

In `frontend/e2e/fake_llm.py`, add after `threads()`:

```python
def intro(user: str) -> dict:
    """Every part of the introduction, each citing what it introduces; the route keeps the threads' order."""
    body = user.split("THREAD DETAILS (id", 1)[1].split("CONNECTIONS (a", 1)[0]
    rows = re.findall(r"^(T\d+) \| ", body, re.M)
    first = dict(re.findall(r"^(T\d+) \|.*\n(?:  (?:modules|files): .*\n)*  stories: (S\d+) ", body, re.M))
    return {"whole": "The change reworks the UART driver. It spans the driver and the code that calls it. Each thread "
                     "below says what it adds. The main risk is a caller that misses a new result.",
            "whole_cites": rows[:1],
            "threads": [{"id": t, "intro": "This thread changes the UART driver. Its code sits in the driver. Its open "
                                           "checks say what to confirm.", "cites": [first.get(t, t)]} for t in rows],
            "route": [{"thread": t, "reason": "This thread comes next in the change.", "skim": False, "cites": [t]}
                      for t in rows]}
```

and make it the first dispatch in `answer()`:

```python
def answer(system: str, user: str) -> dict:
    if "THREAD DETAILS (id" in user:
        return intro(user)
    if "THREADS (id" in user:
        return threads(user)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -p no:cacheprovider --color=no tests/test_pipeline.py tests/test_web.py tests/test_stories_check.py`
Expected: all pass.

- [ ] **Step 6: Whole backend suite and ruff**

Run the full pytest (to `$CLAUDE_JOB_DIR/tmp/t4.log`, read the tail) and ruff.
Expected: all pass, ruff clean. A test elsewhere whose scripted strong model now meets the intro prompt and leaves the reading stage degraded is fixed by dispatching `"THREAD DETAILS (id"` to `scripted_llm.intro_answer` in that test's answer function (ledger it as a ruling naming the test).

- [ ] **Step 7: Commit**

```bash
git add backend/codetortoise/pipeline.py backend/tests/test_pipeline.py frontend/e2e/fake_llm.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(pipeline): the reading stage asks the strong model for the introduction after the thread text, caches it and names its author

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The overview shows the introduction

**Files:**
- Modify: `frontend/src/reading/types.ts` (Thread at :7, Reading at :32)
- Modify: `frontend/src/board/prefs.ts` (`keys`)
- Modify: `frontend/src/reading/overview.ts`
- Modify: `frontend/src/workspace/Overview.tsx`
- Modify: `frontend/src/workspace/workspace.css` (after `.ov-purpose` at :612)
- Test: `frontend/src/reading/overview.test.ts`

**Interfaces:**
- Consumes: the JSON fields from Tasks 1–4 (`intro`, `intro_source`, `files`, `modules`, `files_source`, `route`, `route_source`).
- Produces:
  - `types.ts`: `RouteStep { thread: string; reason: string; skim: boolean }`; optional fields on `Thread` and `Reading`.
  - `prefs.ts` `keys.introOpen = "ct.intro.open"`.
  - `overview.ts`: `interface RouteRow { id; letter; name; reason; skim; first: string | null }`, `routeRows(r: Pick<Reading, "threads" | "route">): RouteRow[]`, `introOpen(): boolean`, `setIntroOpen(open: boolean): void`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/reading/overview.test.ts`, change the imports to:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { keys } from "../board/prefs";
import { arcLayout, connectionRows, introOpen, routeRows, setIntroOpen, testsLine } from "./overview";
import type { Connection, RouteStep, TestsRow, Thread } from "./types";
```

and append:

```ts
describe("the introduction", () => {
  afterEach(() => vi.unstubAllGlobals());
  const step = (thread: string, reason = `why ${thread}`, skim = false): RouteStep => ({ thread, reason, skim });
  const threads = [{ ...thread("T1", "`send` changes"), stories: ["S2", "S1"] }, thread("T2", "init"), thread("T3", "step")];

  it("lists the route in its own order, lettering each thread by its place in the threads", () => {
    const rows = routeRows({ threads, route: [step("T3", "only bundled", true), step("T1"), step("T2")] });
    expect(rows.map((r) => [r.letter, r.name, r.reason, r.skim, r.first])).toEqual([
      ["C", "step", "only bundled", true, null], ["A", "`send` changes", "why T1", false, "S2"], ["B", "init", "why T2", false, null]]);
  });

  it("drops a step naming no thread of the reading, and has no rows for a reading stored before the route", () => {
    expect(routeRows({ threads, route: [step("T9"), step("T2")] }).map((r) => r.id)).toEqual(["T2"]);
    expect(routeRows({ threads })).toEqual([]);
  });

  it("opens the explainer on a first visit and keeps it closed once closed", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
    expect(introOpen()).toBe(true);
    setIntroOpen(false);
    expect(store.get(keys.introOpen)).toBe("false");
    expect(introOpen()).toBe(false);
    setIntroOpen(true);
    expect(introOpen()).toBe(true);
  });

  it("opens the explainer when storage is missing or throws, and closing it never throws", () => {
    expect(introOpen()).toBe(true);                                   // no window at all (node)
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("quota"); } } });
    expect(introOpen()).toBe(true);
    expect(() => setIntroOpen(false)).not.toThrow();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run (from `frontend/`): `npx vitest run src/reading/overview.test.ts`
Expected: FAIL — `routeRows`/`introOpen` are not exported (`TypeError: ... is not a function`) and `keys.introOpen` is undefined.

- [ ] **Step 3: Implement the types, the key and the helpers**

`frontend/src/reading/types.ts` — replace `Thread` and add `RouteStep`; add the route to `Reading`:

```ts
export interface Thread {
  id: string; name: string; purpose: string; text_source: "template" | "llm";
  /** In reading order. */
  stories: string[]; cls: number[]; open_checks: number;
  /** 3–5 sentences (spec 2026-10-09-review-introduction §3); absent on a reading stored before the introduction. */
  intro?: string; intro_source?: "template" | "llm";
  /** Its key files and directories, workspace-relative. */
  files?: string[]; modules?: string[]; files_source?: "template" | "llm";
}
/** One step of Where to start: a thread and why to read it then. */
export interface RouteStep { thread: string; reason: string; skim: boolean }
```

and in `Reading`, after `sinks?: SinkHit[];`:

```ts
  /** Every thread once, in the order to read them; absent on a reading stored before the introduction. */
  route?: RouteStep[]; route_source?: "template" | "llm";
```

`frontend/src/board/prefs.ts` — add to `keys`, after `headH`:

```ts
  /** Whether the overview's "How to read this page" is open (spec 2026-10-09-review-introduction §5.1). */
  introOpen: "ct.intro.open",
```

`frontend/src/reading/overview.ts` — change the header comment's first line to `/** The overview's connections tile, Tests row and introduction (specs 2026-10-07-review-reading §5.1, 2026-10-09-review-introduction §5). */`, change the imports to:

```ts
import { keys, load, save } from "../board/prefs";
import { letter } from "./checks";
import type { Connection, ConnKind, Reading, TestsRow, Thread } from "./types";
```

and append:

```ts
export interface RouteRow { id: string; letter: string; name: string; reason: string; skim: boolean; first: string | null }

/** Where to start, one row per step in the route's order; each thread keeps the letter its place in the threads gives it. */
export function routeRows(r: Pick<Reading, "threads" | "route">): RouteRow[] {
  const at = new Map(r.threads.map((t, i) => [t.id, i]));
  return (r.route ?? []).filter((s) => at.has(s.thread)).map((s) => {
    const i = at.get(s.thread)!, t = r.threads[i];
    return { id: t.id, letter: letter(i, t.id), name: t.name, reason: s.reason, skim: s.skim, first: t.stories[0] ?? null };
  });
}

/** "How to read this page" is open until the viewer closes it; storage that is missing or throws leaves it open. */
export const introOpen = (): boolean => load<unknown>(keys.introOpen, true) !== false;
export const setIntroOpen = (open: boolean): void => save(keys.introOpen, open);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/reading/overview.test.ts`
Expected: all pass.

- [ ] **Step 5: Show it on the overview**

In `frontend/src/workspace/Overview.tsx`, change the overview import to:

```ts
import { arcLayout, connectionRows, introOpen, routeRows, setIntroOpen, testsLine } from "../reading/overview";
```

Add these two components above `ThreadCard`:

```tsx
/** What the page's parts are, for a reader new to CodeTortoise (spec 2026-10-09-review-introduction §5.1): open on a
 * first visit; once closed it stays closed in this browser. */
function HowToRead() {
  const [open, setOpen] = useState(introOpen);
  const toggled = (now: boolean) => { if (now !== open) { setOpen(now); setIntroOpen(now); } };
  return (
    <details className="ov-howto" open={open} onToggle={(e) => toggled(e.currentTarget.open)}>
      <summary><h2 id="ov-howto">How to read this page</h2></summary>
      <ul>
        <li><b>Threads</b> group the change's stories that are joined by calls or shared data. Each has a letter (A, B…)
          used across the page.</li>
        <li><b>Stories</b> are the steps of a thread, one change and its effects each. A story has a <b>Steps</b> view
          (what it does, before → after, call paths, its code) and a <b>Graph</b> view.</li>
        <li><b>Arcs</b> between threads are solid when they share calls or data, dashed when they only arrived in the same
          review — ask the author why.</li>
        <li><b>To check</b> lists what needs a reviewer's eye. <b>Looks fine</b> clears a row, <b>Read</b> ticks it for
          you alone, <b>Comment</b> starts a thread, <b>Open</b> shows the code.</li>
        <li><b>Progress</b> counts the stories and checks you have read.</li>
        <li><b>The side panel</b> shows code beside the page; ⤢ on a story's code opens it there.</li>
      </ul>
    </details>
  );
}

/** Where to start (§5.2): every thread in the suggested order with why, threads worth only a skim muted. The letter and
 * name go to the thread's card below, as the connections' boxes do; "first story" opens its first story. */
function WhereToStart({ r }: { r: Reading }) {
  const ws = useWs();
  const rows = routeRows(r);
  if (!rows.length) return null;
  return (
    <section aria-labelledby="ov-start">
      <h2 id="ov-start">{r.route_source === "llm" && <span className="ai-label">AI</span>}Where to start</h2>
      <ol className="ov-route">{rows.map((row) => (
        <li key={row.id} className={row.skim ? "skim" : ""}>
          <button className="link" onClick={() => document.getElementById(`thread-${row.id}`)?.scrollIntoView({ block: "start" })}
                  aria-label={`Go to thread ${row.letter}: ${short(row.name.replaceAll("`", ""))}`}>
            <span className="ov-letter">{row.letter}</span> <Ticks text={row.name} />
          </button>
          {" — "}<Ticks text={row.reason} />
          {row.skim && <span className="ov-skim">skim</span>}
          {row.first && <> · <Link to={ws.link(ws.item({ kind: "story", sid: row.first, view: "steps" }))}
                                 aria-label={`Open the first story of thread ${row.letter}`}>first story</Link></>}
        </li>
      ))}</ol>
    </section>
  );
}
```

In `ThreadCard`, replace the purpose line `{t.purpose && <p className="ov-purpose"><Ticks text={t.purpose} /></p>}` with:

```tsx
      {(t.intro || t.purpose) && (
        <p className="ov-purpose">{t.intro && t.intro_source === "llm" && <span className="ai-label">AI</span>}
          <Ticks text={t.intro || t.purpose} /></p>
      )}
```

and update `ThreadCard`'s doc comment to "A thread: name, CLs, open checks and its intro (its purpose on a reading stored before the introduction), then its stories…".

In `Overview`, make the left column's order: progress line, `<HowToRead />`, the whole's section, `<WhereToStart r={r} />`, `<Connections r={r} />`, threads, `<Discussion />`:

```tsx
        {p && <p className={`ov-progress${p.all ? " done" : ""}`}>{overviewProgress(p)}</p>}
        <HowToRead />
        <section aria-labelledby="ov-whole">
          <h2 id="ov-whole">The change as a whole</h2>
          <p className="ws-lead">{r.whole_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={r.whole} /></p>
        </section>
        <WhereToStart r={r} />
        <Connections r={r} />
```

Update the `Overview` doc comment: "…the introduction (how to read the page, the change as a whole, where to start), how its threads connect and the threads on the left; …".

In `frontend/src/workspace/workspace.css`, after `.ov-purpose { … }` add:

```css
.ov-howto { margin: 0 0 14px; }
.ov-howto summary { cursor: pointer; }
.ov-howto summary h2 { display: inline; }
.ov-howto ul { margin: 6px 0 0; padding-left: 18px; font-size: 14px; }
.ov-howto li { margin: 3px 0; }
.ov-route { margin: 6px 0 14px; padding-left: 22px; font-size: 14px; }
.ov-route li { margin: 4px 0; }
.ov-route li.skim { color: var(--muted); }
.ov-route .ov-letter { margin-right: 2px; }
.ov-skim { margin-left: 6px; padding: 0 6px; font-size: 12px; border: 1px solid var(--line); border-radius: 8px; }
```

- [ ] **Step 6: Typecheck, the whole vitest suite and the build**

Run (from `frontend/`): `npx vitest run > $CLAUDE_JOB_DIR/tmp/t5.log 2>&1; tail -5 $CLAUDE_JOB_DIR/tmp/t5.log` and `npm run build > $CLAUDE_JOB_DIR/tmp/t5b.log 2>&1; tail -5 $CLAUDE_JOB_DIR/tmp/t5b.log`
Expected: every vitest passes; the build (with its typecheck) succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/reading/types.ts frontend/src/board/prefs.ts frontend/src/reading/overview.ts frontend/src/reading/overview.test.ts frontend/src/workspace/Overview.tsx frontend/src/workspace/workspace.css
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(overview): how to read this page (collapsible, remembered), where to start, and each thread's intro on its card

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: End-to-end checks

**Files:**
- Modify: `frontend/e2e/workspace-reading.spec.ts` (the first desktop test at :24; new test)
- Modify: `frontend/e2e/workspace-tier1.spec.ts` (new test)

**Interfaces:**
- Consumes: everything above; `startReview`, `expectNamed` from `e2e/helpers.ts`; `fake_llm.py` `intro()` (Task 4).
- Produces: nothing.

- [ ] **Step 1: Write the tests**

In `frontend/e2e/workspace-reading.spec.ts`, in "the overview tells the change as threads…", change the headings line to:

```ts
    await expect(left.locator("h2")).toHaveText(["How to read this page", "The change as a whole", "Where to start",
                                                 "How the threads connect", "Threads", "Discussion"]);
```

Then add to the `desktop` describe:

```ts
  test("the overview introduces the review: how to read it, where to start and each thread's intro", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const how = page.locator(".ov-howto");
    await expect(how.locator("ul")).toBeVisible();                                       // open on a first visit
    await expect(how).toContainText("Threads group the change's stories");
    await how.locator("summary").click();
    await expect(how.locator("ul")).toBeHidden();
    await page.reload();
    await expect(how.locator("ul")).toBeHidden();                                        // stays closed in this browser
    await how.locator("summary").click();
    await page.reload();
    await expect(how.locator("ul")).toBeVisible();

    const route = page.getByRole("region", { name: "Where to start" }).locator(".ov-route li");
    await expect(route).toHaveCount(3);
    await expect(route).toHaveText([/^A hal_write in hal — 5 checks open\./, /^B logger_init in service — Nothing is open\./,
                                    /^C svc::Engine::step in cpp — 1 check open\./]);
    await expect(page.getByRole("region", { name: "Where to start" }).locator(".ai-label")).toHaveCount(0);
    await route.nth(2).getByRole("button", { name: /^Go to thread C/ }).click();
    await expect(page.locator("#thread-T3")).toBeInViewport();
    const card = page.locator(".ov-thread").first();
    await expect(card.locator(".ov-purpose")).toContainText("Starts with “hal_write's signature changed");
    await expect(card.locator(".ov-purpose .ai-label")).toHaveCount(0);
    await route.first().getByRole("link", { name: "Open the first story of thread A" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S\\d+$`));
    await expectNamed(page);
  });
```

If the fixture's thread B turns out to be all repeated edits (then its row reads "Only repeated edits and tests; skim it." and moves last), change the expected rows to what the rules give — the order and reasons follow §3.2 — and ledger the ruling.

In `frontend/e2e/workspace-tier1.spec.ts`, inside the describe, add:

```ts
  test("the overview's introduction is the strong model's, each part labelled AI", async ({ page }) => {
    await startReview(page);
    const start = page.getByRole("region", { name: "Where to start" });
    await expect(start.locator("h2 .ai-label")).toBeVisible();
    await expect(start.locator(".ov-route li").first()).toContainText("This thread comes next in the change.");
    const intro = page.locator(".ov-thread").first().locator(".ov-purpose");
    await expect(intro.locator(".ai-label")).toBeVisible();
    await expect(intro).toContainText("This thread changes the UART driver.");
    await expect(page.locator(".ov2-left .ws-lead")).toContainText("The main risk is a caller that misses a new result.");
  });
```

- [ ] **Step 2: Build and run the e2e specs**

Run (from `frontend/`): `npm run build > $CLAUDE_JOB_DIR/tmp/t6b.log 2>&1; tail -3 $CLAUDE_JOB_DIR/tmp/t6b.log`, then
`TMPDIR=$CLAUDE_JOB_DIR/tmp/pw TORTOISE_CMD="env PYTHONPATH=/media/anoop/ssd_1/Work/CodeTortoise/.worktrees/intro/backend /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/workspace-reading.spec.ts e2e/workspace-tier1.spec.ts > $CLAUDE_JOB_DIR/tmp/t6.log 2>&1; tail -20 $CLAUDE_JOB_DIR/tmp/t6.log`
Expected: all pass (a startReview timeout passes on `--last-failed`).

- [ ] **Step 3: The whole e2e suite**

Run the same command without spec arguments (output to `$CLAUDE_JOB_DIR/tmp/t6all.log`, read the tail); rerun failures with `--last-failed`.
Expected: all pass except known flakes, which pass on `--last-failed`. A spec that counted the overview's `h2`s or `.ov-purpose` text and now fails is updated to the new order and text (ledger each as a ruling).

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/workspace-reading.spec.ts frontend/e2e/workspace-tier1.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "test(e2e): the overview's introduction: the explainer's remembered state, where to start's links, thread intros, AI labels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review

- **Spec coverage.** §3.1 data: Task 1. §3.2 rules intro and route: Task 1 (`fixed_intro`, `fixed_route`). §3.3 rules pick: Task 1 (`thread_files`, `pick_files`). §4.0 threads call picks, cache, version bump: Task 2. §4.1 tier-1 call after the thread text, `TIER1`, no strong model no call: Tasks 3–4. §4.2–4.4 input, ask, per-part checks, notes: Task 3. §4.5 cache, fresh, stage message: Task 4. §5 overview order, §5.1 explainer, §5.2 Where to start, cards' intro and AI labels: Task 5. §6 old readings: Task 1 (backend), Task 5 (`routeRows` without a route; optional types). §7 tests: spread as listed in each task; e2e in Task 6.
- **Placeholders.** None; the two "if the fixture differs" notes name the rule that decides and require a ledger ruling.
- **Type consistency.** `thread_files` → `dict[str, list[tuple[str, int]]]` is what `prompt(files=…)`, `write_threads(files=…)` and the pipeline pass. `RouteStep(thread, reason, skim)` matches the TS `RouteStep`. `fixed_introduction(reading, ss)` is called in `build_reading` and the pipeline. `intro_answer` and `fake_llm.intro` both parse the `THREAD DETAILS (id` header and the `  stories: S…` line that `llm/intro.py` `prompt` writes.
- **Review Focus.** Each of the five lines has its test in the named task.
