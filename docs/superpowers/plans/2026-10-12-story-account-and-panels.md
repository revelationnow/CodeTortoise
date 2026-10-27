# Story accounts, side-panel findings, collapsible panels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A behaviour story's page shows a longer, sectioned account written by the weak model; a check's Details opens the finding in a tabbed side panel; the rail and To check fold away (with Focus); an Index › Findings tab lists every finding; Index › CLs expands each CL's files in place; the unused layer-rename route is gone.

**Architecture:** Backend: a new `codetortoise/llm/account.py` builds one weak-model job per behaviour story (same `Job`/`run_job` pattern as `storyboard.story_job`) and `write_accounts` runs them in parallel with a per-story cache; the pipeline's reading stage calls it and the result rides on the stored `story_reading:{sid}` blob. Frontend: `Open` gains `{finding}`; the workspace (`Workspace.tsx` → `Ws` context) gains panel tabs, folds/focus and expanded CLs as visit state; `FindingBody` is extracted from `FindingPage` so the detail panel can show a finding; two new pure modules (`tabs.ts`, `findings.ts`) carry the rules that vitest checks.

**Tech Stack:** Python 3 / FastAPI / pydantic v2 / SQLite; React 19 + TypeScript + vite; vitest (node env, `src/**/*.test.ts`); Playwright e2e with the fake LLM in `frontend/e2e/fake_llm.py`.

**Spec:** `docs/superpowers/specs/2026-10-12-story-account-and-panels-design.md` (approved 2026-10-12).

## Global Constraints

- The repo is public: no proprietary identifiers from the owner's code, toolchains or builds in code, tests, docs or commit messages. Use the fixture's names (`uart_send`, `logger_flush`, `hal_write`, `Uart::errors`) or generic stand-ins.
- Work in the worktree `.worktrees/story-panels` on branch `story-panels`. Don't push; integration is the owner's call.
- Every commit: `git -c user.email=2929430+revelationnow@users.noreply.github.com commit …`, message ending with the two lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH`.
- Never bare `git stash`, never `git clean -fdx`, never `--force` a worktree removal. Kill processes by PID, never `pkill -f`. Never use `uv`. Use `$CLAUDE_JOB_DIR/tmp`, not `/tmp`, for scratch files.
- AI-written text follows the house style (`codetortoise/llm/style.py`): test texts in fake answers must pass `check_style(text, "explanation")` (no "just", "simply", "easy", "please", "e.g.", "etc.", no sentence over 30 words).
- `ACCOUNT_VERSION = 1`; ledger purpose `story_account`; cache blob `story_account`; prefs keys `ct.ws.railFolded`, `ct.ws.checkFolded`; at most 8 panel tabs; folded strip 28px; Focus leaves the centre at least 360px; Index tab `/i/findings` placed after Checks; filters `?sev=` and `?status=`.
- Account headings: `What it is for` (purpose), the flow's own label `Flow.text` (flow), `What it means for the rest` (effects).
- Long-text rules: one-line labels end in an ellipsis and carry the whole text in a `title`; sentences wrap.

### Commands

Run backend commands from `backend/`, frontend ones from `frontend/`:

```bash
# backend/
export PYTEST="env PYTHONPATH=$PWD .venv/bin/python -m pytest -q -p no:cacheprovider"
export RUFF=".venv/bin/ruff check codetortoise tests"
# frontend/  (once, before the first frontend task: the worktree shares main's node_modules)
[ -e node_modules ] || ln -s ../../../frontend/node_modules node_modules
mkdir -p $(git rev-parse --show-toplevel)/.pwtmp
export E2E="env TMPDIR=$(git rev-parse --show-toplevel)/.pwtmp TORTOISE_CMD='env PYTHONPATH=$(cd ../backend && pwd) $(cd ../backend && pwd)/.venv/bin/python -m codetortoise.cli' npx playwright test"
```

e2e runs need `npm run build` first. `startReview` can time out at 60 s when the whole suite runs at once: rerun a test that failed that way on its own before treating it as a failure. Remove `$(git rev-parse --show-toplevel)/.pwtmp` after the last e2e run, and remove the `frontend/node_modules` symlink before any `git worktree remove`.

## Review Focus

1. A `?open=finding:F9` link to a finding the review no longer has (a re-run renumbered it, or a stale tab): the panel shows "Finding F9 isn't in this review." with a link to All findings; nothing crashes. Test: Task 6 e2e "a finding the review lacks shows Not found in the panel".
2. A hand-edited or old link with `?sev=critical&status=closed`: the filters fall back to All and the list shows every finding. Test: Task 9 vitest "ignores filter values it does not know, and writes them only on the findings tab".
3. Blocked browser storage (private window, site data blocked): the workspace loads unfolded and folding still works for the visit. Test: Task 8 e2e "with storage blocked the columns still fold for the visit".
4. The owner switches the weak model in `tortoise.yaml` and re-runs: every account is asked again, not served from the old model's cache. Test: Task 1 "a different weak model asks again".
5. Back (browser history) while Focus is on: the panel closes and the rail and To check come back as they were before Focus. Test: Task 8 e2e Focus test ends with `page.goBack()`.

---

### Task 1: The account job (backend)

**Files:**
- Modify: `backend/codetortoise/reading.py` (imports at line 17; new `AccountPart` before `StoryReading` at line 167; two fields on `StoryReading`)
- Create: `backend/codetortoise/llm/account.py`
- Test: `backend/tests/test_account.py`

**Interfaces:**
- Consumes: `storyboard.AiContext`, `Job`, `run_job`, `budget`, `MODES`, `_facts_for_nodes`, `_finding_text`, `_styled` (`backend/codetortoise/llm/storyboard.py`); `StoryDetail`/`Story` (`codetortoise/stories.py`); `Placement` (`codetortoise/grouping.py`); test helpers `model`, `_board`, `fake_llm` from `backend/tests/test_storyboard.py`.
- Produces:
  - `codetortoise.reading.AccountPart(kind: Literal["purpose","flow","effects"], heading: str, text: str, cites: list[str])`
  - `StoryReading.account: list[AccountPart]` (default `[]`), `StoryReading.account_files: Files` (default `None`)
  - `codetortoise.llm.account.ACCOUNT_VERSION: int = 1`
  - `account_job(ctx: AiContext, d: StoryDetail, sr: StoryReading) -> Job` — purpose `"story_account"`, target the story id; `apply` writes `sr.account`/`sr.account_files` and returns sections dropped for style.
  - `write_accounts(llm, ctx, details: dict[str, StoryDetail], per: dict[str, StoryReading], cached: dict, *, fresh=False, concurrency=1, ledger=None, rid=None) -> tuple[dict, int, list[str]]` — returns (cache to store: `sid → {"key", "account", "files"}`, sections dropped for style, notes). Notes is `[]` or `["N story account(s) not written: <first error>"]`.
  - Prompt markers other code matches on: the prompt starts `Write a reviewer's account of this change story`; it holds a line `CITE FROM: <ids, comma-space separated>` and one line per flow `FLOW <id> | <label> | <what>`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_account.py`:

```python
from test_storyboard import _board, fake_llm, model

from codetortoise.grouping import Placement
from codetortoise.llm.account import account_job, write_accounts
from codetortoise.llm.storyboard import AiContext, run_job
from codetortoise.reading import CallPath, StoryReading
from codetortoise.stories import Story, StoryDetail

P = "This story makes uart_send return -2 on a full buffer. You see it in every caller."


def _detail(sid="S1", **kw):
    st = Story(id=sid, kind=kw.pop("kind", "behaviour"), title="uart_send reports errors", summary="uart_send can return -2.",
               nodes=["N2"], flows=["FL1", "FL2"], findings=["F1"], **kw)
    d = StoryDetail(story=st, board=_board(2))
    d.board.flows[1].text = "main → uart_send"
    return d


def _ctx():
    im, findings, _ = model()
    return AiContext(im, findings, {"N2": "int uart_send(void) { return -2; }"})


def _sections(*extra):
    return {"sections": [
        {"kind": "effects", "cites": ["F1"], "text": "Callers that ignore the result now drop an error. Check the ones you own."},
        {"kind": "flow", "flow": "FL2", "cites": ["N2"], "text": "main reaches uart_send directly. It now gets -2 back."},
        {"kind": "purpose", "cites": ["N2"], "text": P},
        {"kind": "flow", "flow": "FL1", "cites": ["N3"], "text": "logger_flush calls uart_send on each flush. It drops the new -2."},
        *extra]}


def test_an_account_keeps_purpose_flows_in_story_order_and_effects():
    d, sr = _detail(), StoryReading(story="S1")
    assert run_job(fake_llm(lambda s, u: _sections()), account_job(_ctx(), d, sr)) == 0
    assert [(p.kind, p.heading) for p in sr.account] == [
        ("purpose", "What it is for"), ("flow", "logger_flush → uart_send ⟶ -2 ignored"), ("flow", "main → uart_send"),
        ("effects", "What it means for the rest")]
    assert sr.account[0].text == P and sr.account[0].cites == ["N2"]


def test_sections_that_cite_nothing_of_the_story_name_another_flow_or_repeat_a_kind_are_dropped():
    d, sr = _detail(), StoryReading(story="S1")
    out = _sections({"kind": "purpose", "cites": ["N2"], "text": "A second purpose. It repeats the first."},
                    {"kind": "flow", "flow": "FL9", "cites": ["N2"], "text": "Another story's flow. It isn't this one's."},
                    {"kind": "flow", "flow": "FL1", "cites": ["N3"], "text": "A second section for this flow. It comes too late."},
                    {"kind": "summary", "cites": ["N2"], "text": "A kind the account doesn't have."})
    out["sections"][0]["cites"] = ["N99"]          # the effects section cites nothing of the story
    run_job(fake_llm(lambda s, u: out), account_job(_ctx(), d, sr))
    assert [p.kind for p in sr.account] == ["purpose", "flow", "flow"]
    assert sr.account[0].text == P and "too late" not in sr.account[1].text


def test_with_no_section_left_there_is_no_account_and_style_breaks_are_counted():
    d, sr = _detail(), StoryReading(story="S1")
    bad = {"sections": [{"kind": "purpose", "cites": ["N2"], "text": "Simply put, it changes uart_send."},
                        {"kind": "effects", "cites": ["N99"], "text": "Callers see -2."}]}
    assert run_job(fake_llm(lambda s, u: bad), account_job(_ctx(), d, sr)) == 1
    assert sr.account == [] and sr.account_files is None


def test_the_prompt_holds_what_the_strong_model_said_the_flows_paths_and_findings():
    d = _detail(source="tier1", purpose="Report transmit errors to the logger.", check=["Check logger_flush handles -2."],
                questions=["Should uart_errors reset on init?"],
                placements=[Placement(piece="P1", reason="It adds the -2 that logger_flush now sees.")])
    sr = StoryReading(story="S1", paths=[CallPath(steps=["N3", "N2"], labels=["logger_flush", "uart_send"], kind="contract",
                                                  text="logger_flush calls uart_send")])
    prompt = account_job(_ctx(), d, sr).prompt
    assert prompt.startswith("Write a reviewer's account of this change story")
    for want in ["Report transmit errors to the logger.", "It adds the -2 that logger_flush now sees.",
                 "Check logger_flush handles -2.", "Should uart_errors reset on init?",
                 "FLOW FL1 | logger_flush → uart_send ⟶ -2 ignored | template what", "logger_flush calls uart_send",
                 "F1 [medium] contract", "int uart_send(void)", "CITE FROM: N2, N3, F1"]:
        assert want in prompt
    rules = account_job(_ctx(), _detail(purpose="Not from tier 1."), StoryReading(story="S1")).prompt
    assert "WHAT THE GROUPING MODEL SAID" not in rules


def test_a_shared_sink_finding_stays_out_of_the_prompt():
    ctx = _ctx()
    ctx.findings[0].sink = True
    assert "F1 [medium]" not in account_job(ctx, _detail(), StoryReading(story="S1")).prompt


def test_the_account_records_the_files_behind_its_prompt():
    ctx = _ctx()
    ctx.node_files = {"N2": ["//w/d/uart.c"], "N3": ["//w/svc/logger.c"]}
    ctx.findings[0].files = ["//w/d/uart.c"]
    sr = StoryReading(story="S1")
    run_job(fake_llm(lambda s, u: _sections()), account_job(ctx, _detail(), sr))
    assert sr.account_files == ["//w/d/uart.c", "//w/svc/logger.c"]


def test_write_accounts_skips_mechanical_and_collapsed_stories_and_reuses_an_unchanged_prompts_account():
    ctx, asked = _ctx(), []

    def respond(s, u):
        asked.append(u)
        return _sections()
    details = {"S1": _detail("S1"), "S2": _detail("S2", collapsed=True), "S3": _detail("S3", kind="mechanical")}
    per = {s: StoryReading(story=s) for s in details}
    cache, dropped, notes = write_accounts(fake_llm(respond), ctx, details, per, {})
    assert (len(asked), set(cache), dropped, notes) == (1, {"S1"}, 0, [])
    assert per["S1"].account and not per["S2"].account and not per["S3"].account
    again = {s: StoryReading(story=s) for s in details}
    assert write_accounts(fake_llm(respond), ctx, details, again, cache)[0] == cache
    assert len(asked) == 1 and [p.text for p in again["S1"].account] == [p.text for p in per["S1"].account]
    write_accounts(fake_llm(respond), ctx, details, {s: StoryReading(story=s) for s in details}, cache, fresh=True)
    assert len(asked) == 2


def test_a_different_weak_model_asks_again():
    ctx, asked = _ctx(), []

    def respond(s, u):
        asked.append(u)
        return _sections()
    details = {"S1": _detail("S1")}
    cache = write_accounts(fake_llm(respond), ctx, details, {"S1": StoryReading(story="S1")}, {})[0]
    other = fake_llm(respond)
    other.model = "another-model"
    write_accounts(other, ctx, details, {"S1": StoryReading(story="S1")}, cache)
    assert len(asked) == 2


def test_a_failed_call_leaves_that_story_without_an_account_and_says_why():
    details = {"S1": _detail("S1")}
    per = {"S1": StoryReading(story="S1")}
    cache, _, notes = write_accounts(fake_llm(lambda s, u: {"sections": "not a list"}), _ctx(), details, per, {})
    assert cache == {} and per["S1"].account == []
    assert len(notes) == 1 and notes[0].startswith("1 story account(s) not written: ")
```

If `LlmClient.model` turns out to be read-only, set the model by building the second client with `LlmClient("http://llm/v1", "k", "another-model", transport=…)` the way `fake_llm` does; the test's point is a different `model` string.

- [ ] **Step 2: Run the tests to watch them fail**

Run: `cd backend && $PYTEST tests/test_account.py`
Expected: collection error `ModuleNotFoundError: No module named 'codetortoise.llm.account'`.

- [ ] **Step 3: Add `AccountPart` and the two `StoryReading` fields**

In `backend/codetortoise/reading.py`, add `Files` to the board import (line 17):

```python
from codetortoise.board import BoardContext, Files, Flow, _count, _covered, _Ctx, analyse, is_test_path
```

(If `Files` is not exported by `codetortoise.board`, import it from where `codetortoise/stories.py` gets it — `grep -n "Files" codetortoise/stories.py`.)

Just above `class StoryReading(BaseModel):` add:

```python
class AccountPart(BaseModel):
    """One section of a behaviour story's account (spec 2026-10-12-story-account-and-panels §1.4)."""
    kind: Literal["purpose", "flow", "effects"]
    heading: str                      # "What it is for", the flow's label, "What it means for the rest"
    text: str
    cites: list[str] = Field(default_factory=list)
```

and at the end of `StoryReading`'s fields:

```python
    account: list[AccountPart] = Field(default_factory=list)   # the weak model's account (spec 2026-10-12 §1)
    account_files: Files = None       # provenance: the files whose code was in its prompt
```

- [ ] **Step 4: Write `backend/codetortoise/llm/account.py`**

```python
"""A behaviour story's account (spec 2026-10-12-story-account-and-panels §1): the weak model retells, section by
section, what the strong model and the analysis found about the story."""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from codetortoise.llm.client import LlmClient, LlmError
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import MODES, AiContext, Job, _facts_for_nodes, _finding_text, _styled, budget, run_job
from codetortoise.reading import AccountPart, StoryReading
from codetortoise.stories import StoryDetail

ACCOUNT_VERSION = 1                    # bump with every change to the prompt below: cached accounts are asked again
PURPOSE, EFFECTS = "What it is for", "What it means for the rest"


class _Section(BaseModel):
    kind: str                          # anything but purpose, flow or effects is dropped, not a failed answer
    flow: str | None = None
    text: str = ""
    cites: list[str] = Field(default_factory=list)


class _AccountOut(BaseModel):
    sections: list[_Section] = Field(default_factory=list)


def account_job(ctx: AiContext, d: StoryDetail, sr: StoryReading) -> Job:
    """The account of story `d`, written onto its reading `sr`. A section is kept only when it keeps the house style,
    cites the story's code or findings and, for a flow section, names one of the story's flows; the first of each
    kind is kept, in the order purpose, the story's flows, effects."""
    st, impact = d.story, ctx.impact
    flows = [fl for fl in d.board.flows if fl.id in st.flows]
    mentioned = list(dict.fromkeys(st.nodes + [n for fl in flows for n in fl.path]))
    nodes = [n for n in mentioned if n in impact.nodes]
    known = set(mentioned) | set(st.findings)
    said = [f"purpose: {st.purpose}"] if st.purpose else []
    said += [f"why {p.piece} belongs: {p.reason}" for p in st.placements]
    said += [f"check: {c}" for c in st.check] + [f"question: {q}" for q in st.questions]
    parts = [f"STORY {st.id} ({st.kind}): {st.title}\nshort text: {st.purpose or st.summary}\n"
             f"CITE FROM: {', '.join(mentioned + st.findings)}"]
    if st.source == "tier1" and said:
        parts.append("WHAT THE GROUPING MODEL SAID:\n" + "\n".join(said))
    parts.append("FLOWS (id | label | what it does):\n"
                 + ("\n".join(f"FLOW {fl.id} | {fl.text} | {fl.what}" for fl in flows) or "none"))
    parts.append("CALL PATHS:\n" + ("\n".join(p.text for p in sr.paths) or "none"))
    parts.append("BEFORE → AFTER:\n" + ("\n".join(
        c.text + (f" ({c.before} → {c.after})" if c.before or c.after else "") for c in sr.contracts) or "none"))
    parts.append("WHERE:\n" + ("\n".join(f"{w.path}: {', '.join(fn.label for fn in w.functions)}" for w in sr.where)
                               or "none"))
    parts.append("FINDINGS:\n" + ("\n\n".join(_finding_text(f) for f in ctx.findings
                                              if f.id in st.findings and not f.sink) or "none"))   # a shared sink's: never
    parts.append("GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes))
    parts += [f"CODE {n}:\n{ctx.snippets[n]}" for n in nodes if n in ctx.snippets]
    label = {fl.id: fl.text for fl in flows}

    def apply(out: _AccountOut) -> int:
        dropped, kept = 0, {}
        for s in out.sections:
            key, text = (f"flow:{s.flow}" if s.kind == "flow" else s.kind), s.text.strip()
            if (s.kind not in ("purpose", "flow", "effects") or key in kept or not text
                    or (s.kind == "flow" and s.flow not in label) or not set(s.cites) & known):
                continue
            if not _styled(text, "explanation"):
                dropped += 1
                continue
            heading = label[s.flow] if s.kind == "flow" else PURPOSE if s.kind == "purpose" else EFFECTS
            kept[key] = AccountPart(kind=s.kind, heading=heading, text=text, cites=[c for c in s.cites if c in known])
        order = ["purpose", *(f"flow:{fl.id}" for fl in flows), "effects"]
        sr.account = [kept[k] for k in order if k in kept]
        sr.account_files = ctx.prompt_files(nodes, st.findings) if sr.account else None
        return dropped
    prompt = ("Write a reviewer's account of this change story, in sections. First a purpose section: what the story "
              "is for and why. Then one flow section per FLOW below, in that order, with its id in `flow`: how the "
              "entry reaches the changed code and what the change does there. Last an effects section: who else sees "
              "the effect and what to watch. Each section is one paragraph of 2-5 sentences. Cite in each section the "
              f"node and finding ids it relies on, from CITE FROM.\n{MODES['explanation']}\n\n"
              + budget(parts, ctx.per_call))
    return Job("story_account", st.id, prompt, _AccountOut, apply)


def write_accounts(llm: LlmClient, ctx: AiContext, details: dict[str, StoryDetail], per: dict[str, StoryReading],
                   cached: dict, *, fresh: bool = False, concurrency: int = 1, ledger: Ledger | None = None,
                   rid: int | None = None) -> tuple[dict, int, list[str]]:
    """Write the account of every behaviour story that is not collapsed (spec §1.4): one call each, in parallel; a
    story whose prompt (and weak model) is unchanged reuses its cached account unless `fresh`. Returns the cache to
    store (sid → key, account, files), the sections dropped for style and the stage notes."""
    jobs = {sid: account_job(ctx, d, per[sid]) for sid, d in details.items()
            if sid in per and d.story.kind == "behaviour" and not d.story.collapsed}
    keys = {sid: hashlib.sha256(f"{ACCOUNT_VERSION}|{llm.model}|{j.prompt}".encode()).hexdigest()
            for sid, j in jobs.items()}
    cache: dict = {}
    todo: list[str] = []
    for sid in jobs:
        hit = cached.get(sid)
        if hit and hit.get("key") == keys[sid] and not fresh:
            per[sid].account = [AccountPart(**p) for p in hit["account"]]
            per[sid].account_files = hit.get("files")
            cache[sid] = hit
        else:
            todo.append(sid)

    def one(sid: str) -> tuple[str, int, str | None]:
        try:
            return sid, run_job(llm, jobs[sid], ledger, rid), None
        except Refused as e:
            return sid, 0, f"AI budget: {e.reason}"
        except Exception as e:  # that story keeps its short text
            return sid, 0, str(e) if isinstance(e, LlmError) else f"{type(e).__name__}: {e}"
    dropped, failed = 0, []
    with ThreadPoolExecutor(max(1, concurrency), thread_name_prefix="tortoise-account") as pool:
        for sid, n, error in pool.map(one, todo):
            dropped += n
            if error is None:
                cache[sid] = {"key": keys[sid], "account": [p.model_dump() for p in per[sid].account],
                              "files": per[sid].account_files}
            else:
                failed.append(error)
    return cache, dropped, [f"{len(failed)} story account(s) not written: {failed[0]}"] if failed else []
```

- [ ] **Step 5: Run the tests to watch them pass**

Run: `cd backend && $PYTEST tests/test_account.py`
Expected: `9 passed`.

- [ ] **Step 6: Run the backend suite and ruff**

Run: `cd backend && $PYTEST 2>&1 | tail -3 && $RUFF`
Expected: all tests pass; `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add backend/codetortoise/reading.py backend/codetortoise/llm/account.py backend/tests/test_account.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(reading): a behaviour story's account, written by the weak model in sections" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 2: The reading stage writes the accounts

**Files:**
- Modify: `backend/codetortoise/pipeline.py` (imports; inside `read()`, between the thread/intro block ending at line 529 and `store.replace_blobs(` at line 530)
- Test: `backend/tests/test_pipeline.py` (append)

**Interfaces:**
- Consumes: `write_accounts` from Task 1; `AiContext` (already imported in `pipeline.py`); `collect_snippets` (pipeline.py:81); `ctx["impact"]`, `ctx["cs"]`, `ctx["after"]`, `ctx.get("node_files")`, `x.c.findings`, `bs.story_details`, `per`, `fresh`, `svc.llm`, `svc.ledger`, `cfg.llm.concurrency`, `cfg.llm.max_context_tokens`.
- Produces: `story_reading:{sid}` blobs carry `account`/`account_files`; blob `story_account` holds the cache; the reading stage message gains `; N story account(s)` and, when calls failed, either `; <note>` (some written) or a degraded stage (none written).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_pipeline.py`:

```python
def _weak(svc, answer, model="small"):
    from scripted_llm import ScriptedLlm
    svc.llm = ScriptedLlm(answer, model)
    return svc.llm


def _account_answer(system, user):
    """A passing account for any account prompt (spec 2026-10-12 §1); every other weak-model call fails, so its stage
    keeps its fixed text."""
    import re
    if "Write a reviewer's account" not in user:
        return RuntimeError("not scripted")
    cites = re.search(r"^CITE FROM: (.*)$", user, re.M)[1].split(", ")[:1]
    flows = re.findall(r"^FLOW (FL\d+) \| ", user, re.M)
    return {"sections": [
        {"kind": "purpose", "cites": cites, "text": "This story changes what uart_send reports. You see it in its callers."},
        *({"kind": "flow", "flow": f, "cites": cites,
           "text": "The caller reaches uart_send on this path. The new result changes what it gets back."} for f in flows),
        {"kind": "effects", "cites": cites, "text": "Code that reads the result now sees a new value. Check the readers you own."}]}


def _behaviour(svc, rid):
    return [s for s in svc.store.get_blob(rid, "stories")["stories"] if s["kind"] == "behaviour" and not s["collapsed"]]


def test_the_weak_model_writes_each_behaviour_storys_account_once_and_a_fresh_run_asks_again(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _weak(svc, _account_answer)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    stories = _behaviour(svc, rid)
    assert stories
    for s in stories:
        acc = svc.store.get_blob(rid, f"story_reading:{s['id']}")["account"]
        assert acc[0]["heading"] == "What it is for" and acc[-1]["heading"] == "What it means for the rest"
        assert all(p["kind"] == "flow" for p in acc[1:-1])
    st = next(s for s in svc.store.list_stages(rid) if s["name"] == "reading")
    assert f"; {len(stories)} story account(s)" in st["message"]
    asked = lambda: sum("Write a reviewer's account" in p for p in llm.prompts)     # noqa: E731
    assert asked() == len(stories)
    run_review(rid, svc)
    assert asked() == len(stories)
    assert svc.store.get_blob(rid, f"story_reading:{stories[0]['id']}")["account"]     # reused, not lost
    run_review(rid, svc, fresh=True)
    assert asked() == 2 * len(stories)


def test_without_a_weak_model_no_story_has_an_account_and_the_stage_says_nothing_of_them(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    assert all(not svc.store.get_blob(rid, f"story_reading:{s['id']}")["account"] for s in _behaviour(svc, rid))
    st = next(s for s in svc.store.list_stages(rid) if s["name"] == "reading")
    assert "account" not in st["message"]


def test_when_every_account_call_fails_the_reading_is_degraded_and_says_why(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    _weak(svc, lambda s, u: RuntimeError("the endpoint is down"))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = next(s for s in svc.store.list_stages(rid) if s["name"] == "reading")
    assert st["status"] == "degraded"
    assert "story account(s) not written: RuntimeError: the endpoint is down" in st["message"]
    assert svc.store.get_blob(rid, "reading") is not None                     # the reading itself still stands
```

- [ ] **Step 2: Run them to watch them fail**

Run: `cd backend && $PYTEST tests/test_pipeline.py -k "account"`
Expected: 3 tests run; the first fails on `acc[0]` (`IndexError: list index out of range`), the third on `assert st["status"] == "degraded"`; the second passes already (it pins the no-LLM case and stays green).

- [ ] **Step 3: Call `write_accounts` from the reading stage**

In `backend/codetortoise/pipeline.py`, add the import next to the storyboard import:

```python
from codetortoise.llm.account import write_accounts
```

Then, inside `read()`, right before `store.replace_blobs(rid, ["reading", "reading_head", "lines"], ["story_reading:"],` (line 530), insert:

```python
        if svc.llm is not None:                # each behaviour story's account (spec 2026-10-12 §1.4)
            aictx = AiContext(ctx["impact"], x.c.findings, collect_snippets(ctx["impact"], ctx["cs"], ctx["after"]),
                              cfg.llm.max_context_tokens, ctx.get("node_files"))
            accounts, dropped, said = write_accounts(svc.llm, aictx, bs.story_details, per,
                                                     store.get_blob(rid, "story_account") or {}, fresh=fresh,
                                                     concurrency=cfg.llm.concurrency, ledger=svc.ledger, rid=rid)
            store.put_blob(rid, "story_account", accounts)
            told += f"; {sum(bool(per[sid].account) for sid in accounts)} story account(s)"
            if dropped:
                told += f"; {dropped} account section(s) broke the house style and were dropped"
            if said and not accounts:
                notes = notes + said           # not one account: the stage is degraded
            elif said:
                told += "; " + said[0]
```

The ledger records these calls as the pipeline's (`user=None`), as every review-time AI call is; the review's AI budget applies through `rid`.

- [ ] **Step 4: Run them to watch them pass**

Run: `cd backend && $PYTEST tests/test_pipeline.py -k "account"`
Expected: `3 passed`.

- [ ] **Step 5: Run the backend suite and ruff**

Run: `cd backend && $PYTEST 2>&1 | tail -3 && $RUFF`
Expected: all pass; `All checks passed!`. If a pipeline test that sets no weak model now fails, read its message first: no code path above runs without `svc.llm`.

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/pipeline.py backend/tests/test_pipeline.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(pipeline): the reading stage writes story accounts, cached per story" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 3: Remove the layer-rename route

**Files:**
- Modify: `backend/codetortoise/web/app.py` (`LayerNameIn` lines 83-84; `named()` lines 223-227 and its calls at 237, 254, 282, 284; the route at 470-476)
- Modify: `backend/codetortoise/services.py` (lines 59-62)
- Modify: `frontend/src/api.ts` (line 147)
- Test: `backend/tests/test_web.py` (lines 122-134 and 201-212)

**Interfaces:**
- Consumes: nothing new.
- Produces: `PUT /api/layers/{level}` answers 404 or 405; `api.renameLayer` no longer exists; a stored `layer_overrides` value no longer changes layer names.

- [ ] **Step 1: Write the failing test and drop the rename asserts**

In `backend/tests/test_web.py`:
- rename `test_health_and_layer_rename` to `test_health` and delete its four layer lines (the `owner.put("/api/layers/2", …)` assert, the `rid = …` line, the `names = …` line and the two asserts after it);
- rename `test_board_endpoint_serves_the_board_with_layer_renames` to `test_board_endpoint_serves_the_board` and delete its `level = …`, `owner.put(f"/api/layers/{level}", …)`, `names = …` and `assert names[level] == "Drivers"` lines;
- add after it:

```python
def test_the_layer_rename_route_is_gone_and_stored_names_no_longer_apply(env):
    svc, app, _ = env
    owner, rid = _review(app)
    assert owner.put("/api/layers/2", json={"name": "Drivers"}).status_code in (404, 405)
    levels = [l["level"] for l in owner.get(f"/api/reviews/{rid}/board").json()["layers"]]
    svc.store.kv_put("layer_overrides", {str(level): "Drivers" for level in levels})    # what the route once stored
    assert "Drivers" not in {l["name"] for l in owner.get(f"/api/reviews/{rid}/board").json()["layers"]}
    assert "Drivers" not in {l["name"] for l in svc.layers.get().layers}
```

(`svc.layers.get()` is the layer service whose `get` applied the overrides; if its accessor differs, use the name in `services.py` around line 50.)

- [ ] **Step 2: Run it to watch it fail**

Run: `cd backend && $PYTEST tests/test_web.py -k "layer_rename_route or test_health or board_endpoint"`
Expected: the new test FAILS (the PUT answers 200).

- [ ] **Step 3: Remove the route and every use of `layer_overrides`**

- `app.py`: delete `class LayerNameIn` (and its blank lines); delete the `def named(…)` block; delete the four `named(...)` call lines (at `overview`, `board`, and the two in `story`, keeping the `if out["graph"]:` line only if something else is under it — otherwise delete it too); delete the `# ---- layers ----` comment and the `rename_layer` route.
- `services.py`: delete the four lines from `overrides = self.store.kv_get("layer_overrides") or {}` through `layer.name = overrides[str(layer.level)]`.
- `frontend/src/api.ts`: delete the `renameLayer:` line.
- Then: `grep -rn "layer_overrides\|LayerNameIn\|renameLayer\|api/layers" backend/codetortoise frontend/src README.md docs --include=*.py --include=*.ts --include=*.tsx --include=README.md` — expect no hits outside `docs/superpowers/` history. Remove a hit in README or a non-history doc that documents the route.

- [ ] **Step 4: Run tests, ruff and the frontend type check**

Run: `cd backend && $PYTEST tests/test_web.py && $RUFF && cd ../frontend && npx tsc --noEmit`
Expected: test_web passes; `All checks passed!`; tsc prints nothing (Field, if now unused in app.py, is flagged by ruff — remove the unused import).

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/web/app.py backend/codetortoise/services.py backend/tests/test_web.py frontend/src/api.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "fix(web): remove the layer-rename route, which nothing calls" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 4: The story page shows the account

**Files:**
- Modify: `frontend/src/reading/types.ts:70-76` (`StoryReading`)
- Modify: `frontend/src/workspace/StoryTiles.tsx` ("What it does" section, around line 185; new `StoryAccount` component above `StoryTiles`)
- Modify: `frontend/src/workspace/workspace.css` (append)
- Modify: `frontend/e2e/fake_llm.py` (new `account()`; branch in `answer()`)
- Test: `frontend/e2e/ai.spec.ts` (append inside `test.describe("with an AI", …)`)

**Interfaces:**
- Consumes: `story_reading:{sid}.account` from Tasks 1-2; prompt markers `Write a reviewer's account`, `CITE FROM: `, `FLOW <id> | `.
- Produces: TS `AccountPart { kind: "purpose" | "flow" | "effects"; heading: string; text: string; cites: string[] }`; `StoryReading.account?: AccountPart[]`, `account_files?: string[] | null`; DOM: `.st-account` holding one `.st-acc.st-acc-<kind>` per section (`h4` heading, `p` with `.ai-label`), then `p.st-place`.

- [ ] **Step 1: Teach the fake model to write accounts**

In `frontend/e2e/fake_llm.py`, above `def answer`, add:

```python
def account(user: str) -> dict:
    """A story's account (spec 2026-10-12-story-account-and-panels §1): purpose, one section per flow, effects."""
    cites = re.search(r"^CITE FROM: (.*)$", user, re.M).group(1).split(", ")[:1]
    flows = re.findall(r"^FLOW (FL\d+) \| ", user, re.M)
    return {"sections": [
        {"kind": "purpose", "flow": None, "cites": cites,
         "text": "This story makes uart_send count its transmit errors. You see the count through uart_errors."},
        *({"kind": "flow", "flow": f, "cites": cites,
           "text": "The caller reaches uart_send on this path. The new error count changes what it reports."} for f in flows),
        {"kind": "effects", "flow": None, "cites": cites,
         "text": "Code that reads Uart::errors now sees transmit errors too. Check the readers you own."}]}
```

and in `answer()`, before the `"Retell this change story"` branch:

```python
    if "Write a reviewer's account" in user:
        return account(user)
```

- [ ] **Step 2: Write the failing e2e test**

Append inside the `test.describe("with an AI", …)` block of `frontend/e2e/ai.spec.ts`:

```ts
  test("a story's What it does is the weak model's account: purpose, its flows and what it means, each AI-labelled", async ({ page }) => {
    await startReview(page);
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    const what = page.getByRole("region", { name: "What it does" });
    await expect(what.locator(".st-acc").first()).toBeVisible({ timeout: 30_000 });
    await expect(what.locator(".st-acc h4").first()).toHaveText("What it is for");
    await expect(what.locator(".st-acc h4").last()).toHaveText("What it means for the rest");
    await expect(what.locator(".st-acc .ai-label")).toHaveCount(await what.locator(".st-acc").count());
    await expect(what).toContainText("This story makes uart_send count its transmit errors.");
  });
```

- [ ] **Step 3: Run it to watch it fail**

Run: `cd frontend && npm run build && $E2E e2e/ai.spec.ts -g "weak model's account"`
Expected: FAIL — `.st-acc` not found (the backend stores the account; the page doesn't show it yet).

- [ ] **Step 4: Add the type and render the account**

`frontend/src/reading/types.ts` — above `export interface StoryReading`:

```ts
/** One section of a behaviour story's account (spec 2026-10-12-story-account-and-panels §1). */
export interface AccountPart { kind: "purpose" | "flow" | "effects"; heading: string; text: string; cites: string[] }
```

and inside `StoryReading`, after `cl_order?: number[]; rewrites?: Rewrite[];`:

```ts
  /** The weak model's account, section by section (spec 2026-10-12 §1); absent or empty: the short text stands. */
  account?: AccountPart[]; account_files?: string[] | null;
```

`frontend/src/workspace/StoryTiles.tsx` — import `AccountPart` alongside the other `../reading/types` imports, add above `export default function StoryTiles`:

```tsx
/** The weak model's account of a behaviour story (spec 2026-10-12-story-account-and-panels §1.1): its purpose, one
 * section per flow and what it means for the rest, each with the AI label; its place in its thread after. */
function StoryAccount({ parts, place }: { parts: AccountPart[]; place: string }) {
  return (
    <div className="st-account">
      {parts.map((p, k) => (
        <div key={k} className={`st-acc st-acc-${p.kind}`}>
          <h4 className={p.kind === "flow" ? "mono" : undefined}>{p.heading}</h4>
          <p><span className="ai-label">AI</span><NameText text={p.text} /></p>
        </div>
      ))}
      {place && <p className="st-place">{place}</p>}
    </div>
  );
}
```

and replace the `<p>…</p>` under `<h3 id="st-what">What it does</h3>` with:

```tsx
          {st.kind === "behaviour" && (sr.account?.length ?? 0) > 0 ? <StoryAccount parts={sr.account!} place={sr.place_text} />
            : <p>{st.text_source === "llm" && <span className="ai-label">AI</span>}<NameText text={st.purpose || st.summary} />
              {sr.place_text && <span className="st-place"> {sr.place_text}</span>}</p>}
```

`frontend/src/workspace/workspace.css` — append:

```css
/* a behaviour story's account (spec 2026-10-12-story-account-and-panels §1.1) */
.st-account h4 { margin: 14px 0 4px; font-size: 13px; color: var(--muted); font-weight: 600; }
.st-account .st-acc:first-child h4 { margin-top: 0; }
.st-account p { margin: 0 0 6px; }
.st-account > .st-place { color: var(--muted); }
```

- [ ] **Step 5: Run the test, the AI and tier-1 specs, and the unit tests**

Run: `cd frontend && npm run build && npm test && $E2E e2e/ai.spec.ts e2e/workspace-tier1.spec.ts e2e/workspace-reading.spec.ts`
Expected: all pass. Each behaviour story now adds one weak-model call at review time: if a test asserts an exact weak-model call count or remaining budget, recount it with that in mind and say so in the commit body.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/reading/types.ts frontend/src/workspace/StoryTiles.tsx frontend/src/workspace/workspace.css frontend/e2e/fake_llm.py frontend/e2e/ai.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(story): What it does shows the story's account, section by section" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 5: `{finding}` in the panel's address

**Files:**
- Modify: `frontend/src/workspace/address.ts` (`Open`, new `Item`, `readOpen`, `href`)
- Modify: `frontend/src/workspace/memory.ts:35-40` (`isOpen`)
- Test: `frontend/src/workspace/address.test.ts`, `frontend/src/workspace/memory.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `export type Open = { node: string } | { file: string; line: number | null; all?: true } | { finding: string } | null;` and `export type Item = Exclude<Open, null>;` in `address.ts`; `?open=finding:F4` ↔ `{ finding: "F4" }`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/workspace/address.test.ts` (inside a new `describe`):

```ts
describe("a finding in the panel", () => {
  it("reads and writes ?open=finding:F4", () => {
    const a = readAddress("/s/S1", q("open=finding:F4"));
    expect(a.open).toEqual({ finding: "F4" });
    expect(href("/r/7", a)).toBe("/r/7/s/S1?open=finding%3AF4");
    expect(readAddress("/s/S1", new URLSearchParams(href("/r/7", a).split("?")[1])).open).toEqual({ finding: "F4" });
  });

  it("reads an empty finding as nothing open", () => {
    expect(readAddress("", q("open=finding:")).open).toBeNull();
  });
});
```

In `frontend/src/workspace/memory.test.ts`, add a test in the style of the file's existing load tests that saves `{ "s:S1": at({ kind: "story", sid: "S1", view: "steps" }, { open: { finding: "F4" } }) }` to session storage and expects `loadMemory` to return it unchanged (read how the file stubs `window.sessionStorage` and reuse that stub):

```ts
  it("keeps an item whose panel showed a finding", () => {
    const m = { "s:S1": at({ kind: "story", sid: "S1", view: "steps" }, { open: { finding: "F4" } }) };
    saveMemory(1, m);
    expect(loadMemory(1)).toEqual(m);
  });
```

- [ ] **Step 2: Run them to watch them fail**

Run: `cd frontend && npx vitest run src/workspace/address.test.ts src/workspace/memory.test.ts`
Expected: FAIL — `readAddress` returns `{ node: "finding:F4" }`; `loadMemory` drops the entry.

- [ ] **Step 3: Implement**

`address.ts`:

```ts
/** What the detail panel shows: a node's code, a file's diff (at a line) or a finding (spec 2026-10-12 §2.1). */
/** `all`: the file in all CLs, whatever CL the page is about (phase 2 §5.4: a rewrite's line is a final-text line). */
export type Open = { node: string } | { file: string; line: number | null; all?: true } | { finding: string } | null;
/** One thing the panel can show. */
export type Item = Exclude<Open, null>;
```

In `readOpen`, before `if (!raw.startsWith("file:"))`:

```ts
  if (raw.startsWith("finding:")) return raw.length > 8 ? { finding: raw.slice(8) } : null;
```

In `href`, replace the `if (a.open) q.set("open", …)` line with:

```ts
  if (a.open) q.set("open", "node" in a.open ? a.open.node : "finding" in a.open ? `finding:${a.open.finding}`
    : `file:${a.open.file}${a.open.line ? `:${a.open.line}` : ""}`);
```

`memory.ts` `isOpen`, after the `"node" in o` line:

```ts
  if ("finding" in o) return str(o.finding);
```

- [ ] **Step 4: Run tests and the type check**

Run: `cd frontend && npm test && npx tsc --noEmit`
Expected: all vitest pass; tsc prints nothing. (Every other `Open` reader in the workspace guards with `"node" in` or `"file" in`, so a finding is "no node, no file" there — `Detail.tsx` gets its finding view in Task 6.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/workspace/address.ts frontend/src/workspace/memory.ts frontend/src/workspace/address.test.ts frontend/src/workspace/memory.test.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): the panel's address can name a finding" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 6: A finding in the side panel; Details opens it there

**Files:**
- Create: `frontend/src/workspace/FindingBody.tsx`
- Modify: `frontend/src/workspace/FindingPage.tsx` (keeps title row, previous/next; body moves out)
- Modify: `frontend/src/workspace/Detail.tsx`
- Modify: `frontend/src/workspace/CheckList.tsx:49-50` (Details link)
- Modify: `frontend/src/workspace/workspace.css` (append)
- Test: `frontend/e2e/workspace-panels.spec.ts` (create); `frontend/e2e/workspace-reading.spec.ts:173-175` (Details now opens the panel)

**Interfaces:**
- Consumes: `Open`/`Item` with `{finding}` (Task 5); `ws.opened(open)`.
- Produces: `FindingBody({ fid, head, ids }: { fid: string; head: ReactNode; ids: string })` — renders the finding's `<header className="ws-story-head">` (`head`, status line, verdict) and its sections, section ids prefixed with `ids` (`ids="ws"` keeps the page's ids `ws-where`, `ws-ai`, `ws-ev`, `ws-verify`, `ws-hyp`, `ws-fc`; the panel uses `ids="ws-p"`). The panel for a finding is `<aside aria-label="Finding: F4">`; its header has links "Open as a page" (`/f/F4?details=1`) and "All findings" (`/i/findings`, keeping `open`).

- [ ] **Step 1: Write the failing e2e tests**

Create `frontend/e2e/workspace-panels.spec.ts`:

```ts
import { expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

/** The side panel, folding and the Index's new views (spec 2026-10-12-story-account-and-panels §2-§5). */

const FOUR = "101 102 103 104";
type F = { id: string; title: string; severity: string; state: string };
const findingsOf = async (page: Page, base: string) =>
  await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as F[];

test.use({ viewport: { width: 1400, height: 900 } });

test("a check's Details opens its finding in the side panel; the story stays and Back closes it", async ({ page }) => {
  const base = await startReview(page, FOUR);
  const sig = (await findingsOf(page, base)).find((f) => f.title === "hal_write: signature changed")!;
  await page.goto(`${base}/s/S2`);
  const row = page.getByRole("region", { name: "To check" }).locator(`.ck-row[data-finding="${sig.id}"]`);
  await row.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();
  await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=finding%3A${sig.id}$`));
  const panel = page.getByRole("complementary", { name: `Finding: ${sig.id}` });
  await expect(panel.locator("h2")).toContainText("hal_write: signature changed");
  await expect(panel.getByRole("link", { name: "Open as a page" })).toHaveAttribute("href", `${base}/f/${sig.id}?details=1`);
  await expect(page.getByRole("region", { name: "To check" })).toBeVisible();          // the story stays
  await page.goBack();
  await expect(page.locator(".ws-detail")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`${base}/s/S2$`));
});

test("a finding the review lacks shows Not found in the panel", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/s/S1?open=finding:F999`);
  await expect(page.getByRole("complementary", { name: "Finding: F999" })).toContainText("Finding F999 isn't in this review.");
});
```

In `frontend/e2e/workspace-reading.spec.ts`, replace the two lines after `await lit.getByRole("link", { name: \`Finding ${sig.id}'s details\` }).click();` with:

```ts
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=finding%3A${sig.id}&check=${sig.id}$`));   // in the panel
    await expect(page.locator(".ws-detail .ws-finding h2")).toContainText("hal_write: signature changed");
```

(and change the comment on the click line to `// the finding opens beside its story`).

- [ ] **Step 2: Run them to watch them fail**

Run: `cd frontend && npm run build && $E2E e2e/workspace-panels.spec.ts e2e/workspace-reading.spec.ts -g "Details|lacks|old addresses"`
Expected: FAIL — Details still navigates to `/f/…?details=1`; `?open=finding:F999` shows the code panel's "Not found".

- [ ] **Step 3: Extract `FindingBody`**

Create `frontend/src/workspace/FindingBody.tsx` with the imports `FindingPage.tsx` has now except `SeverityBadge` and `short` (keep `short` only if the moved code still uses it — it does, in the story link), plus `import type { ReactNode } from "react";`. Move into it, verbatim:
- the `STATE` and `VERDICT` constants;
- from `FindingPage`'s body: the lines computing `ws, d, me, ai` (line 23), `f` (as `const f = d.findings.find((x) => x.id === fid)!;`), `sid`, `st`, `first`, `field`, `cluster`, `graph`, `tree`, `cls`, `depots` (lines 26-36), `name` and `talk` (lines 43-48);
- the JSX from `<p className="ws-story-meta">` (line 56) through the closing `</section>` of Comments (line 133).

Its signature and shell:

```tsx
/** What a finding says (spec 2026-10-04-review-workspace §3.3), on its page and in the side panel (spec
 * 2026-10-12-story-account-and-panels §2.1): its status, the AI's verdict, where it lives, the AI analysis, the
 * evidence (each line opening the diff at that line) and comments. `head` is the caller's title row; `ids` prefixes
 * the sections' ids, so a page and the panel can each show a finding. */
export default function FindingBody({ fid, head, ids }: { fid: string; head: ReactNode; ids: string }) {
  // …moved lines…
  return <>
    <header className="ws-story-head">
      {head}
      {/* moved: <p className="ws-story-meta">…</p> and the verdict paragraph */}
    </header>
    {/* moved: the Where it lives, AI analysis, Evidence, Verify, Possible side effects and Comments sections */}
  </>;
}
```

In the moved sections replace each fixed id with the prefixed one — `"ws-where"` → `` `${ids}-where` ``, and likewise `ws-ai`, `ws-ev`, `ws-verify`, `ws-hyp`, `ws-fc` — in both `id=` and `aria-labelledby=`.

`FindingPage.tsx` becomes:

```tsx
import { Link } from "react-router-dom";
import { SeverityBadge } from "../components/Badges";
import { tidy } from "../lib/tidy";
import { useWs } from "./context";
import { short } from "./crumbs";
import FindingBody from "./FindingBody";

/** A finding's own page (spec 2026-10-04-review-workspace §3.3): its title and its place among the findings, then what
 * it says (FindingBody, which the side panel shows too). */
export default function FindingPage({ fid }: { fid: string }) {
  const ws = useWs(), d = ws.data;
  const i = d.findings.findIndex((x) => x.id === fid), f = d.findings[i];
  const n = d.findings.length;
  const step = (by: number) => {
    const to = d.findings[((i + by) % n + n) % n];
    const label = `${by < 0 ? "Previous" : "Next"} finding: ${to.id} ${short(tidy(to.title))}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link({ ...ws.item({ kind: "finding", fid: to.id }), details: true })} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };
  return (
    <div className="ws-page"><div className="ws-text ws-finding">
      <FindingBody fid={fid} ids="ws" head={
        <div className="ws-story-title">
          <h2><SeverityBadge severity={f.severity} /> {tidy(f.title)}</h2>
          <span className="ws-pos">{step(-1)}<span>{f.id} of {n}</span>{step(1)}</span>
        </div>} />
    </div></div>
  );
}
```

- [ ] **Step 4: Show a finding in `Detail.tsx`**

Add imports: `import { SeverityBadge } from "../components/Badges";`, `import { tidy } from "../lib/tidy";`, `import FindingBody from "./FindingBody";`.

After line 20 (`const nid = …`), add:

```tsx
  const fid = "finding" in open ? open.finding : null, finding = fid ? d.findings.find((x) => x.id === fid) ?? null : null;
```

Change `label` (line 60) to:

```tsx
  const label = fid ? (finding ? fid : null) : "file" in open ? path!.slice(path!.lastIndexOf("/") + 1) : node?.label ?? name?.label ?? null;
```

At the top of `body()` add:

```tsx
    if (fid) return finding
      ? <div className="ws-finding ws-panel-finding"><FindingBody fid={fid} ids="ws-p" head={
          <h2 className="ws-panel-title"><SeverityBadge severity={finding.severity} /> {tidy(finding.title)}</h2>} /></div>
      : <div className="banner warn">Finding {fid} isn't in this review. <Link to={ws.link(at({ kind: "index", tab: "findings" }))}>All findings</Link></div>;
```

Set the panel's names: replace `aria-label={\`Code: ${label ?? "not found"}\`}` with `aria-label={fid ? \`Finding: ${fid}\` : \`Code: ${label ?? "not found"}\`}`; define `const closeLabel = fid ? "Close the finding" : "Close the code";` and use it for both close links' `aria-label` and `title`. In `.ws-detail-name`, after the story link, add:

```tsx
          {fid && finding && <span className="ws-detail-links">
            <Link to={ws.link(at({ kind: "finding", fid }, { details: true }))} title={`Open finding ${fid} as a page`}>Open as a page</Link>
            <Link to={ws.link(at({ kind: "index", tab: "findings" }, { open }))} title="Every finding of the review">All findings</Link>
          </span>}
```

`at({ kind: "index", tab: "findings" })` needs the tab to exist, so add it now: in `address.ts` set `export const INDEX_TABS = ["cls", "files", "checks", "findings", "map"] as const;` and in `crumbs.ts` add `findings: "Findings"` to `INDEX_LABEL` after `checks`. Task 9 builds the tab's page; until then `/i/findings` shows the Index tabs and nothing under them.

- [ ] **Step 5: Point Details at the panel**

`CheckList.tsx` line 49: replace `to={ws.link(at({ kind: "finding", fid: k.finding }, { details: true }))}` with `to={ws.link(ws.opened({ finding: k.finding }))}`. Remove the `at` import if nothing else in the file uses it.

`workspace.css` — append:

```css
/* a finding in the side panel (spec 2026-10-12-story-account-and-panels §2.1) */
.ws-panel-finding { padding: 4px 2px; }
.ws-panel-title { font-size: 16px; margin: 0; }
.ws-detail-links { display: inline-flex; gap: 10px; font-size: 12.5px; }
```

- [ ] **Step 6: Run the tests**

Run: `cd frontend && npx tsc --noEmit && npm test && npm run build && $E2E e2e/workspace-panels.spec.ts e2e/workspace-reading.spec.ts e2e/workspace-pages.spec.ts e2e/mention.spec.ts e2e/workspace-story.spec.ts`
Expected: all pass (the finding page keeps its ids and look: `mention.spec.ts` still finds `#ws-ai`).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/workspace/FindingBody.tsx frontend/src/workspace/FindingPage.tsx frontend/src/workspace/Detail.tsx frontend/src/workspace/CheckList.tsx frontend/src/workspace/workspace.css frontend/src/workspace/address.ts frontend/src/workspace/crumbs.ts frontend/e2e/workspace-panels.spec.ts frontend/e2e/workspace-reading.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): a check's Details opens the finding in the side panel" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 7: Panel tabs

**Files:**
- Create: `frontend/src/workspace/tabs.ts`, `frontend/src/workspace/tabs.test.ts`
- Modify: `frontend/src/workspace/context.ts` (`Ws`), `frontend/src/workspace/Workspace.tsx` (state + memo), `frontend/src/workspace/Detail.tsx` (tab bar), `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace-panels.spec.ts` (append)

**Interfaces:**
- Consumes: `Item` (Task 5); `Names` from `../api`.
- Produces:
  - `tabs.ts`: `MAX_TABS = 8`; `openKey(o: Item): string` (`f:F4`, `n:N2`, `d:<file>`); `addTab(tabs: Item[], o: Item): Item[]`; `closeTab(tabs: Item[], o: Item, active: Item | null): { tabs: Item[]; next: Item | null | undefined }`; `tabLabel(o: Item, names: Names): string`.
  - `Ws.tabs: Item[]`, `Ws.closeTab: (o: Item) => void`.
  - DOM: `role="tablist"` named "Open items", shown only with 2+ tabs and not on a phone; each tab a `role="tab"` link named by `tabLabel`, with a button "Close <name>".

- [ ] **Step 1: Write the failing unit tests**

Create `frontend/src/workspace/tabs.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Item } from "./address";
import { addTab, closeTab, MAX_TABS, openKey, tabLabel } from "./tabs";

const f = (id: string): Item => ({ finding: id });
const file = (p: string, line: number | null = null): Item => ({ file: p, line });

describe("addTab", () => {
  it("adds new items last and keeps an open item's place, taking its new line", () => {
    let t = addTab([], f("F1"));
    t = addTab(t, file("//d/a.c", 3));
    t = addTab(t, { node: "N2" });
    t = addTab(t, file("//d/a.c", 9));
    expect(t).toEqual([f("F1"), file("//d/a.c", 9), { node: "N2" }]);
  });

  it("returns the same list when the item is already there as it is", () => {
    const t = [f("F1")];
    expect(addTab(t, f("F1"))).toBe(t);
  });

  it("keeps at most 8, dropping the oldest", () => {
    let t: Item[] = [];
    for (let i = 1; i <= 9; i++) t = addTab(t, f(`F${i}`));
    expect(t).toHaveLength(MAX_TABS);
    expect(t.map(openKey)).toEqual(["f:F2", "f:F3", "f:F4", "f:F5", "f:F6", "f:F7", "f:F8", "f:F9"]);
  });
});

describe("closeTab", () => {
  const t = [f("F1"), f("F2"), f("F3")];

  it("closing a tab that is not active leaves the panel as it is", () => {
    expect(closeTab(t, f("F1"), f("F3"))).toEqual({ tabs: [f("F2"), f("F3")], next: undefined });
  });

  it("closing the active tab activates its left neighbour, or the right one when it was first", () => {
    expect(closeTab(t, f("F2"), f("F2")).next).toEqual(f("F1"));
    expect(closeTab(t, f("F1"), f("F1")).next).toEqual(f("F2"));
  });

  it("closing the last tab closes the panel", () => {
    expect(closeTab([f("F1")], f("F1"), f("F1"))).toEqual({ tabs: [], next: null });
  });
});

describe("tabLabel", () => {
  it("names a finding by its id, a file by its name and a function by its name", () => {
    const names = { N2: { label: "uart_send", kind: "function", path: null, line: null, story: null } };
    expect([tabLabel(f("F4"), names), tabLabel(file("//d/driver/uart.c", 4), names), tabLabel({ node: "N2" }, names)])
      .toEqual(["F4", "uart.c", "uart_send"]);
  });
});
```

- [ ] **Step 2: Run them to watch them fail**

Run: `cd frontend && npx vitest run src/workspace/tabs.test.ts`
Expected: FAIL — `Failed to resolve import "./tabs"`.

- [ ] **Step 3: Write `tabs.ts`**

```ts
/** The side panel's tabs (spec 2026-10-12-story-account-and-panels §2.2): every item opened this visit, oldest first,
 * at most MAX_TABS. Pure, so the rules are tested apart from React. */
import type { Names } from "../api";
import type { Item } from "./address";

export const MAX_TABS = 8;

/** One key per item: a file's tab is the file's, whatever line it opened at. */
export const openKey = (o: Item): string => ("finding" in o ? `f:${o.finding}` : "node" in o ? `n:${o.node}` : `d:${o.file}`);

/** The tabs with `o` opened: an item already there keeps its place and takes the new line; a new one goes last, and
 * past the cap the oldest goes (never `o`, the active one). */
export function addTab(tabs: Item[], o: Item): Item[] {
  const i = tabs.findIndex((t) => openKey(t) === openKey(o));
  if (i >= 0) return JSON.stringify(tabs[i]) === JSON.stringify(o) ? tabs : tabs.map((t, k) => (k === i ? o : t));
  const next = [...tabs, o];
  return next.length > MAX_TABS ? next.slice(next.length - MAX_TABS) : next;
}

/** The tabs without `o`, and what the panel shows next: undefined (no change) when `o` was not active; else its left
 * neighbour, the right one when it was first, or null (the panel closes) when it was the last tab. */
export function closeTab(tabs: Item[], o: Item, active: Item | null): { tabs: Item[]; next: Item | null | undefined } {
  const i = tabs.findIndex((t) => openKey(t) === openKey(o));
  if (i < 0) return { tabs, next: undefined };
  const rest = tabs.filter((_, k) => k !== i);
  if (!active || openKey(active) !== openKey(o)) return { tabs: rest, next: undefined };
  return { tabs: rest, next: rest.length ? rest[Math.max(0, i - 1)] : null };
}

/** A tab's name: the finding's id, the file's name or the function's name. */
export function tabLabel(o: Item, names: Names): string {
  if ("finding" in o) return o.finding;
  if ("file" in o) return o.file.slice(o.file.lastIndexOf("/") + 1);
  return names[o.node]?.label ?? "function";
}
```

- [ ] **Step 4: Run them to watch them pass**

Run: `cd frontend && npx vitest run src/workspace/tabs.test.ts`
Expected: `7 passed`.

- [ ] **Step 5: Write the failing e2e test**

Append to `frontend/e2e/workspace-panels.spec.ts`:

```ts
test("the panel keeps a tab per item opened; a tab switches back and × closes it", async ({ page }) => {
  const base = await startReview(page, FOUR);
  const sig = (await findingsOf(page, base)).find((f) => f.title === "hal_write: signature changed")!;
  await page.goto(`${base}/s/S2`);
  const row = page.getByRole("region", { name: "To check" }).locator(`.ck-row[data-finding="${sig.id}"]`);
  await row.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();
  await row.getByRole("link", { name: /^Open / }).click();                 // the row's file, at its line
  const tabs = page.getByRole("tablist", { name: "Open items" });
  await expect(tabs.getByRole("tab")).toHaveCount(2);
  await expect(tabs.getByRole("tab", { selected: true })).toHaveText(/\.[ch]$/);
  await tabs.getByRole("tab", { name: sig.id }).click();
  await expect(page.getByRole("complementary", { name: `Finding: ${sig.id}` })).toBeVisible();
  await tabs.getByRole("button", { name: `Close ${sig.id}` }).click();     // the active one, first: its right neighbour shows
  await expect(page.getByRole("complementary", { name: /^Code: / })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Open items" })).toHaveCount(0);   // one tab left: no bar
});
```

- [ ] **Step 6: Wire the tabs into the workspace and the panel**

`context.ts` — import `Item` with the other address types and add to `Ws`:

```ts
  /** The side panel's tabs this visit, oldest first (spec 2026-10-12 §2.2); the address holds the active one. */
  tabs: Item[];
  closeTab: (o: Item) => void;
```

`Workspace.tsx` — import `type Item` from `./address` and `{ addTab, closeTab as closeOf }` from `./tabs`; after the `opened` callback:

```tsx
  const [tabs, setTabs] = useState<Item[]>([]);
  useEffect(() => { if (addr.open) setTabs((t) => addTab(t, addr.open!)); }, [addr.open]);
  const closeTab = useCallback((o: Item) => {
    const { tabs: rest, next } = closeOf(tabs, o, addr.open);
    setTabs(rest);
    if (next !== undefined) go({ ...addr, open: next, tab: "diff" });
  }, [tabs, addr, go]);
```

and add `tabs, closeTab` to the `ws` object and to its `useMemo` dependency list.

`Detail.tsx` — import `{ openKey, tabLabel }` from `./tabs`; inside `.ws-detail-head`, before `.ws-detail-name`:

```tsx
        {ws.screen !== "phone" && ws.tabs.length > 1 && (
          <div className="ws-ptabs" role="tablist" aria-label="Open items">
            {ws.tabs.map((t) => {
              const on = openKey(t) === openKey(open), tname = tabLabel(t, d.names);
              return (
                <span key={openKey(t)} role="presentation" className={`ws-ptab${on ? " on" : ""}`}>
                  <Link role="tab" aria-selected={on} to={ws.link(ws.opened(t))} title={`Show ${tname}`}>{tname}</Link>
                  <button className="ws-ptab-x" aria-label={`Close ${tname}`} title={`Close ${tname}`} onClick={() => ws.closeTab(t)}>×</button>
                </span>
              );
            })}
          </div>
        )}
```

`workspace.css` — append:

```css
/* the side panel's tabs (spec 2026-10-12-story-account-and-panels §2.2) */
.ws-ptabs { display: flex; gap: 4px; overflow-x: auto; padding-bottom: 2px; }
.ws-ptab { display: inline-flex; align-items: center; gap: 2px; flex: none; max-width: 160px; border: 1px solid var(--line);
  border-radius: 6px; padding: 1px 2px 1px 8px; font-size: 12px; }
.ws-ptab a { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-decoration: none; color: var(--muted); }
.ws-ptab.on { border-color: var(--accent); }
.ws-ptab.on a { color: var(--ink); font-weight: 600; }
.ws-ptab-x { border: 0; background: none; color: var(--muted); padding: 0 4px; cursor: pointer; font-size: 14px; line-height: 1; }
```

The tab bar shows from two tabs: with one, the panel's own ✕ already closes it (a ruling where the spec is silent).

- [ ] **Step 7: Run the tests**

Run: `cd frontend && npx tsc --noEmit && npm test && npm run build && $E2E e2e/workspace-panels.spec.ts e2e/workspace-detail.spec.ts`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/workspace/tabs.ts frontend/src/workspace/tabs.test.ts frontend/src/workspace/context.ts frontend/src/workspace/Workspace.tsx frontend/src/workspace/Detail.tsx frontend/src/workspace/workspace.css frontend/e2e/workspace-panels.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): the side panel keeps a tab per item opened this visit" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 8: Folding the rail and To check; Focus

**Files:**
- Create: `frontend/src/workspace/Strip.tsx`
- Modify: `frontend/src/board/prefs.ts` (`keys`), `frontend/src/workspace/context.ts`, `frontend/src/workspace/Workspace.tsx`, `frontend/src/workspace/Rail.tsx` (line 28 and a new wrapper), `frontend/src/workspace/CheckColumns.tsx`, `frontend/src/workspace/Overview.tsx:171`, `frontend/src/workspace/StoryTiles.tsx:182`, `frontend/src/workspace/Detail.tsx`, `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace-panels.spec.ts` (append)

**Interfaces:**
- Consumes: `load`, `save`, `keys` (`board/prefs.ts`); `isOpen(check, marks)` (`reading/checks.ts`).
- Produces:
  - `keys.railFolded = "ct.ws.railFolded"`, `keys.checkFolded = "ct.ws.checkFolded"`.
  - `export interface Folds { rail: boolean; check: boolean }` in `context.ts`; `Ws.folds: Folds` (what is shown: both true while focused), `Ws.setFold(which: keyof Folds, folded: boolean)`, `Ws.focus: boolean`, `Ws.toggleFocus(): void`.
  - `Strip({ name, label, side, onUnfold })`, `FoldButton({ label, side, onFold })` in `Strip.tsx`; buttons named "Fold the contents" / "Unfold the contents" / "Fold To check" / "Unfold To check" / "Focus".
  - `CheckColumns` takes a required `foldName: string` (the strip's text, "To check · 3 open").

- [ ] **Step 1: Write the failing e2e tests**

Append to `frontend/e2e/workspace-panels.spec.ts`:

```ts
test("the rail and To check fold to strips and stay folded; Focus folds both and widens the panel until pressed again", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/s/S1`);
  await page.getByRole("button", { name: "Fold the contents" }).click();
  await expect(page.locator(".ws-rail.folded")).toContainText("Contents");
  await page.getByRole("button", { name: "Fold To check" }).click();
  await expect(page.locator(".ws-strip.right")).toContainText(/^To check/);
  await page.reload();
  await expect(page.locator(".ws-rail.folded")).toBeVisible();
  await expect(page.locator(".ws-strip.right")).toBeVisible();
  await page.getByRole("button", { name: "Unfold the contents" }).click();
  await page.getByRole("button", { name: "Unfold To check" }).click();
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  await expect(page.locator(".ws-strip.right")).toHaveCount(0);

  await page.getByRole("region", { name: "To check" }).getByRole("link", { name: /^Open / }).first().click();
  const panel = page.locator(".ws-detail");
  const before = (await panel.boundingBox())!.width;
  await panel.getByRole("button", { name: "Focus" }).click();
  await expect(page.locator(".ws-rail.folded")).toBeVisible();
  await expect(page.locator(".ws-strip.right")).toBeVisible();
  expect((await panel.boundingBox())!.width).toBeGreaterThan(before);
  expect((await page.getByRole("region", { name: "Centre" }).boundingBox())!.width).toBeGreaterThanOrEqual(359);
  await panel.getByRole("button", { name: "Focus" }).click();                // pressed again: as it was
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  expect(Math.abs((await panel.boundingBox())!.width - before)).toBeLessThan(2);
  await panel.getByRole("button", { name: "Focus" }).click();
  await page.goBack();                                                       // the panel closes: the columns come back
  await expect(page.locator(".ws-detail")).toHaveCount(0);
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  await expect(page.locator(".ws-strip.right")).toHaveCount(0);
});

test("with storage blocked the columns still fold for the visit", async ({ page }) => {
  const base = await startReview(page);
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new Error("blocked"); };
    Storage.prototype.setItem = () => { throw new Error("blocked"); };
  });
  await page.goto(`${base}/s/S1`);
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  await page.getByRole("button", { name: "Fold the contents" }).click();
  await expect(page.locator(".ws-rail.folded")).toBeVisible();
});
```

If the blocked-storage test fails because some workspace code reads storage outside a try/catch, wrap that access the way `board/prefs.ts` `load`/`save` do (spec §3: read and written in try/catch) and name the file in the commit body.

- [ ] **Step 2: Run them to watch them fail**

Run: `cd frontend && npm run build && $E2E e2e/workspace-panels.spec.ts -g "fold"`
Expected: FAIL — no button named "Fold the contents".

- [ ] **Step 3: Keys, context and workspace state**

`board/prefs.ts`, inside `keys` after `headH`:

```ts
  /** Whether the rail and the To check column are folded to strips (spec 2026-10-12-story-account-and-panels §3). */
  railFolded: "ct.ws.railFolded",
  checkFolded: "ct.ws.checkFolded",
```

`context.ts` — add above `Ws`:

```ts
/** Which columns are folded to strips (spec 2026-10-12 §3). */
export interface Folds { rail: boolean; check: boolean }
```

and to `Ws`:

```ts
  /** The folds shown (both, while focused) and how the reader changes them; desktop only. */
  folds: Folds;
  setFold: (which: keyof Folds, folded: boolean) => void;
  /** Focus: the rail and To check folded and the panel widened, until pressed again or the panel closes. */
  focus: boolean;
  toggleFocus: () => void;
```

`Workspace.tsx` — change the prefs import to `import { keys, load, save } from "../board/prefs";`, import `type Folds` from `./context`, and add after the tabs state:

```tsx
  const [folds, setFolds] = useState<Folds>(() => ({ rail: load(keys.railFolded, false) === true,
                                                     check: load(keys.checkFolded, false) === true }));
  const [focus, setFocus] = useState(false);
  const setFold = useCallback((which: keyof Folds, folded: boolean) => {
    setFocus(false);                                       // unfolding by hand ends Focus
    setFolds((f) => ({ ...f, [which]: folded }));
    save(which === "rail" ? keys.railFolded : keys.checkFolded, folded);
  }, []);
  const toggleFocus = useCallback(() => setFocus((x) => !x), []);
  useEffect(() => { if (!addr.open) setFocus(false); }, [addr.open]);   // closing the panel restores the columns
  const shown = useMemo(() => (focus ? { rail: true, check: true } : folds), [focus, folds]);
```

and add `folds: shown, setFold, focus, toggleFocus` to `ws` and `shown, setFold, focus, toggleFocus` to its dependency list.

- [ ] **Step 4: `Strip.tsx`**

```tsx
/** A folded column (spec 2026-10-12-story-account-and-panels §3): a 28px strip with its name written down it and a
 * button that unfolds it; and the button that folds it. */
export default function Strip({ name, label, side, onUnfold }:
  { name: string; label: string; side: "left" | "right"; onUnfold: () => void }) {
  return (
    <div className={`ws-strip ${side}`}>
      <button className="bd-ibtn ws-unfold" aria-label={`Unfold ${label}`} title={`Unfold ${label}`} onClick={onUnfold}>
        {side === "left" ? "»" : "«"}</button>
      <span className="ws-strip-name">{name}</span>
    </div>
  );
}

export function FoldButton({ label, side, onFold }: { label: string; side: "left" | "right"; onFold: () => void }) {
  return <button className="bd-ibtn ws-fold" aria-label={`Fold ${label}`} title={`Fold ${label}`} onClick={onFold}>
    {side === "left" ? "«" : "»"}</button>;
}
```

- [ ] **Step 5: Fold the rail**

`Rail.tsx`: import `Strip, { FoldButton }` from `./Strip`. Rename line 28's `export default function Rail(` to `function RailBody(` and add above it:

```tsx
type RailProps = { show: string | null; onPick: () => void; hidden?: boolean };

/** The rail, or on a desktop the strip it folds to (spec 2026-10-12 §3). */
export default function Rail(props: RailProps) {
  const ws = useWs();
  if (ws.screen === "desktop" && ws.folds.rail)
    return <aside className="ws-rail folded" aria-label="Review contents">
      <Strip name="Contents" label="the contents" side="left" onUnfold={() => ws.setFold("rail", false)} /></aside>;
  return <RailBody {...props} />;
}
```

and give `RailBody` the parameter type `RailProps` (`function RailBody({ show, onPick, hidden = false }: RailProps)`). In both `<aside className="ws-rail" …>` returns, right after the `<Resizer … />` line, add:

```tsx
        {ws.screen === "desktop" && <FoldButton label="the contents" side="left" onFold={() => ws.setFold("rail", true)} />}
```

- [ ] **Step 6: Fold To check**

`CheckColumns.tsx` becomes:

```tsx
import { type ReactNode, useRef, useState } from "react";
import { keys, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import { useWs } from "./context";
import { CHECK_W, checkMax, loadCheckW } from "./layout";
import Strip, { FoldButton } from "./Strip";

/** The reading on the left and its To check column on the right, with a divider the reader drags (owner feedback
 * 2026-10-08 C on the story page, 2026-10-09 on the overview). One width, kept per browser, for every page that has it.
 * On a desktop the column folds to a strip named `foldName` (spec 2026-10-12 §3). */
export default function CheckColumns({ className = "", left, children, foldName }:
  { className?: string; left: ReactNode; children: ReactNode; foldName: string }) {
  const ws = useWs();
  const page = useRef<HTMLDivElement>(null);
  const [checkW, setCheckW] = useState(loadCheckW);
  const desktop = ws.screen === "desktop", folded = desktop && ws.folds.check;
  return (
    <div className={`ov2 ov2-cols${folded ? " check-folded" : ""} ${className}`.trim()} ref={page}
         style={{ ["--cw" as string]: `${checkW}px` }}>
      {left}
      {folded ? <Strip name={foldName} label="To check" side="right" onUnfold={() => ws.setFold("check", false)} /> : (
        <div className="ov2-check">
          <Resizer size={checkW} edge="left" min={CHECK_W.min} max={() => checkMax(page.current?.clientWidth ?? 0)}
                   onSize={setCheckW} onDone={(w) => save(keys.checkW, w)}
                   onReset={() => { setCheckW(CHECK_W.def); save(keys.checkW, CHECK_W.def); }} />
          {desktop && <FoldButton label="To check" side="right" onFold={() => ws.setFold("check", true)} />}
          {children}
        </div>
      )}
    </div>
  );
}
```

Callers pass the strip's name:
- `Overview.tsx` — import `isOpen` from `../reading/checks`; before the `return`: `const openChecks = r.checks.filter((k) => isOpen(k, r.marks)).length;`; on `<CheckColumns` add `foldName={\`To check · ${openChecks} open\`}`.
- `StoryTiles.tsx` — import `isOpen` from `../reading/checks`; before the `return`: `const openChecks = sr.checks.filter((k) => isOpen(k, d.reading?.marks ?? {})).length;`; on `<CheckColumns` add `foldName={\`To check · ${openChecks} open\`}`.

- [ ] **Step 7: Focus in the panel**

`Detail.tsx`:

```tsx
  const focused = ws.focus && ws.screen === "desktop";
  const shownW = focused ? Math.max(width, window.innerWidth - 28 - 360) : width;   // the centre keeps 360px
```

Use `shownW` in the `style` (`--w`) and in `wide` (`ws.screen === "desktop" && shownW > 900`); give the aside `className={\`ws-detail${focused ? " focus" : ""}\`}`; render the `Resizer` only when `ws.screen === "desktop" && !focused`. In `.ws-detail-name`, before the ✕ link:

```tsx
          {ws.screen === "desktop" && <button className={`bd-ibtn ws-focus${focused ? " on" : ""}`} aria-pressed={focused}
                                              title={focused ? "Bring back the contents and To check" : "Fold the contents and To check, and widen this panel"}
                                              onClick={ws.toggleFocus}>Focus</button>}
```

- [ ] **Step 8: CSS**

Append to `workspace.css`:

```css
/* folded columns and Focus (spec 2026-10-12-story-account-and-panels §3) */
.ws-rail.folded { width: 28px; }
.ws-strip { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 8px 0; width: 28px; }
.ws-strip.right { position: sticky; top: 0; align-self: start; min-height: 200px; border-left: 1px solid var(--line); }
.ws-strip-name { writing-mode: vertical-rl; font-size: 12px; color: var(--muted); white-space: nowrap; }
.ov2.ov2-cols.check-folded { grid-template-columns: minmax(0, 1fr) 28px; }
.ws-rail > .ws-fold { position: absolute; top: 6px; right: 8px; z-index: 2; }
.ws-rail .ws-home { padding-right: 36px; }
.ov2-check > .ws-fold { position: absolute; top: 6px; right: 6px; z-index: 2; }
.ov2-check .ck-tile > h3 { padding-right: 30px; }
.ws-detail.focus { max-width: none; }
.ws-focus { margin-left: auto; }
.ws-focus.on { border-color: var(--accent); color: var(--ink); }
.ws-focus + .ws-x { margin-left: 0; }
```

- [ ] **Step 9: Run the tests**

Run: `cd frontend && npx tsc --noEmit && npm test && npm run build && $E2E e2e/workspace-panels.spec.ts e2e/workspace-layout.spec.ts e2e/workspace-reading.spec.ts e2e/long-text.spec.ts`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/workspace/Strip.tsx frontend/src/board/prefs.ts frontend/src/workspace/context.ts frontend/src/workspace/Workspace.tsx frontend/src/workspace/Rail.tsx frontend/src/workspace/CheckColumns.tsx frontend/src/workspace/Overview.tsx frontend/src/workspace/StoryTiles.tsx frontend/src/workspace/Detail.tsx frontend/src/workspace/workspace.css frontend/e2e/workspace-panels.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(workspace): fold the rail and To check to strips; Focus widens the side panel" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 9: Index › Findings

**Files:**
- Create: `frontend/src/workspace/findings.ts`, `frontend/src/workspace/findings.test.ts`, `frontend/src/workspace/FindingsIndex.tsx`
- Modify: `frontend/src/workspace/address.ts` (`Address.sev`, `Address.status`; `readAddress`; `href`), `frontend/src/workspace/IndexPage.tsx`, `frontend/src/workspace/CheckList.tsx` (`CheckTile` header link), `frontend/src/workspace/Overview.tsx`, `frontend/src/workspace/StoryTiles.tsx`, `frontend/src/workspace/workspace.css`
- Test: `frontend/src/workspace/address.test.ts`, `frontend/e2e/workspace-panels.spec.ts`

**Interfaces:**
- Consumes: `INDEX_TABS` with `"findings"` and `INDEX_LABEL.findings` (added in Task 6 Step 4); `Finding`, `Severity` (`../api`); `ws.opened({ finding })`.
- Produces:
  - `findings.ts`: `SEVERITIES: Severity[]` (`high, medium, low, info`), `type FindingState = Finding["state"]`, `FINDING_STATES`, `STATE_LABEL`, `listFindings(fs, sev: Severity | null, status: FindingState | null): Finding[]`.
  - `Address.sev?: Severity | null`, `Address.status?: FindingState | null` — read and written only for `/i/findings`, written after `open`.
  - `CheckTile` prop `allFindings?: boolean` (a link "All findings" in its header).
  - DOM: `<section aria-label="Findings">` with selects labelled "Severity" and "Status", rows `.ix-findings-list > li`, each row's link named `Open finding <id> in the side panel`.

- [ ] **Step 1: Write the failing unit tests**

Create `frontend/src/workspace/findings.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Finding } from "../api";
import { listFindings } from "./findings";

const f = (id: string, severity: Finding["severity"], state: Finding["state"] = "open") =>
  ({ id, severity, state, kind: "contract", title: id, nodes: [], evidence: [], summary: "", explanation: null,
     verify_steps: [], hypotheses: [], files: null }) as Finding;

describe("listFindings", () => {
  const all = [f("F10", "low"), f("F2", "high", "ack"), f("F1", "high"), f("F3", "info", "dismissed"), f("F4", "medium")];

  it("puts the worst first, then by id as a number", () => {
    expect(listFindings(all, null, null).map((x) => x.id)).toEqual(["F1", "F2", "F4", "F10", "F3"]);
  });

  it("filters by severity and by status", () => {
    expect(listFindings(all, "high", null).map((x) => x.id)).toEqual(["F1", "F2"]);
    expect(listFindings(all, null, "dismissed").map((x) => x.id)).toEqual(["F3"]);
    expect(listFindings(all, "high", "dismissed")).toEqual([]);
  });
});
```

Append to `frontend/src/workspace/address.test.ts`:

```ts
describe("the findings index's filters", () => {
  it("reads and writes ?sev= and ?status= on the findings tab, after the panel's item", () => {
    const a = readAddress("/i/findings", q("sev=high&status=ack&open=finding:F2"));
    expect([a.sev, a.status]).toEqual(["high", "ack"]);
    expect(href("/r/7", a)).toBe("/r/7/i/findings?open=finding%3AF2&sev=high&status=ack");
  });

  it("ignores filter values it does not know, and writes them only on the findings tab", () => {
    const a = readAddress("/i/findings", q("sev=critical&status=closed"));
    expect([a.sev ?? null, a.status ?? null]).toEqual([null, null]);
    expect(readAddress("/i/checks", q("sev=high")).sev ?? null).toBeNull();
    expect(href("/r/7", { ...at({ kind: "index", tab: "checks" }), sev: "high" })).toBe("/r/7/i/checks");
  });
});
```

- [ ] **Step 2: Run them to watch them fail**

Run: `cd frontend && npx vitest run src/workspace/findings.test.ts src/workspace/address.test.ts`
Expected: FAIL — `./findings` cannot be resolved; `a.sev` is undefined.

- [ ] **Step 3: `findings.ts` and the address**

`frontend/src/workspace/findings.ts`:

```ts
/** Index › Findings' rules (spec 2026-10-12-story-account-and-panels §4): the worst first, then by id; filtered by
 * severity and status. */
import type { Finding, Severity } from "../api";

export const SEVERITIES: Severity[] = ["high", "medium", "low", "info"];
export type FindingState = Finding["state"];
export const FINDING_STATES: FindingState[] = ["open", "ack", "dismissed"];
export const STATE_LABEL: Record<FindingState, string> = { open: "open", ack: "acknowledged", dismissed: "dismissed" };

const num = (id: string) => Number(id.replace(/\D/g, "")) || 0;

export function listFindings(fs: Finding[], sev: Severity | null, status: FindingState | null): Finding[] {
  return fs.filter((f) => (!sev || f.severity === sev) && (!status || f.state === status))
    .sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity) || num(a.id) - num(b.id)
      || a.id.localeCompare(b.id));
}
```

`address.ts` — add `import type { Severity } from "../api";` and `import { FINDING_STATES, type FindingState, SEVERITIES } from "./findings";`; to `Address`:

```ts
  /** Index › Findings' filters (spec 2026-10-12 §4); only on that tab. */
  sev?: Severity | null;
  status?: FindingState | null;
```

In `readAddress`, compute the place once (`const place = readPlace(path, q);`, use `place` for the `place:` field) and add to the returned object:

```ts
    ...(place.kind === "index" && place.tab === "findings" && (SEVERITIES as string[]).includes(q.get("sev") ?? "")
      ? { sev: q.get("sev") as Severity } : {}),
    ...(place.kind === "index" && place.tab === "findings" && (FINDING_STATES as string[]).includes(q.get("status") ?? "")
      ? { status: q.get("status") as FindingState } : {}),
```

In `href`, just before the final `return`:

```ts
  if (a.place.kind === "index" && a.place.tab === "findings") {
    if (a.sev) q.set("sev", a.sev);
    if (a.status) q.set("status", a.status);
  }
```

(`readAddress` tests that `toEqual` a whole address keep passing: the filters are only spread in when present.)

- [ ] **Step 4: Run the unit tests to watch them pass**

Run: `cd frontend && npx vitest run src/workspace/findings.test.ts src/workspace/address.test.ts`
Expected: all pass.

- [ ] **Step 5: Write the failing e2e test**

Append to `frontend/e2e/workspace-panels.spec.ts`:

```ts
test("Index › Findings lists every finding worst first, filters by severity and status, and opens one in the panel", async ({ page }) => {
  const base = await startReview(page);
  const all = await findingsOf(page, base);
  await expect(page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Findings" })).toBeVisible();
  await page.getByRole("region", { name: "To check" }).getByRole("link", { name: "All findings" }).click();
  await expect(page).toHaveURL(new RegExp(`${base}/i/findings$`));
  await expect(page.getByRole("tab", { name: `Findings (${all.length})` })).toHaveAttribute("aria-selected", "true");
  const list = page.getByRole("region", { name: "Findings" });
  const rows = list.locator(".ix-findings-list > li");
  await expect(rows).toHaveCount(all.length);
  const rank = ["high", "medium", "low", "info"];
  const sevs = (await rows.locator(".badge").allTextContents()).map((s) => rank.indexOf(s.trim()));
  expect(sevs).toEqual([...sevs].sort((a, b) => a - b));
  const top = rank[sevs[0]];
  await list.getByLabel("Severity").selectOption(top);
  await expect(page).toHaveURL(new RegExp(`/i/findings\\?sev=${top}$`));
  await expect(rows).toHaveCount(all.filter((f) => f.severity === top).length);
  await list.getByLabel("Status").selectOption("dismissed");
  await expect(page).toHaveURL(new RegExp(`sev=${top}&status=dismissed$`));
  await expect(list).toContainText("No findings match.");
  await list.getByLabel("Status").selectOption("");
  await rows.first().getByRole("link", { name: /^Open finding F\d+ in the side panel$/ }).click();
  await expect(page).toHaveURL(new RegExp(`/i/findings\\?open=finding%3AF\\d+&sev=${top}$`));
  await expect(page.getByRole("complementary", { name: /^Finding: F\d+$/ }).locator("h2")).toBeVisible();
  await expect(rows.first()).toBeVisible();                                   // the list stays
});
```

- [ ] **Step 6: The tab, its page and the links**

`FindingsIndex.tsx`:

```tsx
import { Link } from "react-router-dom";
import type { Severity } from "../api";
import { SeverityBadge } from "../components/Badges";
import { tidy } from "../lib/tidy";
import type { Address } from "./address";
import { useWs } from "./context";
import { FINDING_STATES, type FindingState, listFindings, SEVERITIES, STATE_LABEL } from "./findings";

/** Index › Findings (spec 2026-10-12-story-account-and-panels §4): every finding, worst first, filtered by severity and
 * status from the address; a row opens the finding in the side panel. */
export default function FindingsIndex() {
  const ws = useWs(), d = ws.data, sev = ws.addr.sev ?? null, status = ws.addr.status ?? null;
  const rows = listFindings(d.findings, sev, status), story = d.stories?.finding_story ?? {};
  const set = (next: Partial<Pick<Address, "sev" | "status">>) => ws.go({ ...ws.addr, ...next }, true);
  return (
    <section aria-label="Findings" className="ix-findings">
      <div className="ix-filters">
        <label>Severity <select value={sev ?? ""} onChange={(e) => set({ sev: (e.target.value || null) as Severity | null })}>
          <option value="">All</option>{SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
        <label>Status <select value={status ?? ""} onChange={(e) => set({ status: (e.target.value || null) as FindingState | null })}>
          <option value="">All</option>{FINDING_STATES.map((s) => <option key={s} value={s}>{STATE_LABEL[s]}</option>)}</select></label>
        <span className="muted small">{rows.length} of {d.findings.length}</span>
      </div>
      {rows.length === 0 ? <p className="muted">No findings match.</p> : (
        <ul className="ix-list ix-findings-list">{rows.map((f) => {
          const ev = f.evidence.find((e) => e.file);
          const place = ev?.file ? `${ev.file.slice(ev.file.lastIndexOf("/") + 1)}${ev.line ? `:${ev.line}` : ""}` : null;
          const title = tidy(f.title), sid = story[f.id] ?? null;
          const on = !!ws.addr.open && "finding" in ws.addr.open && ws.addr.open.finding === f.id;
          return (
            <li key={f.id} className={on ? "on" : undefined}>
              <SeverityBadge severity={f.severity} />
              <Link className="ix-ftitle" to={ws.link(ws.opened({ finding: f.id }))} title={`${f.id}: ${title}`}
                    aria-label={`Open finding ${f.id} in the side panel`}><span className="ws-handle">{f.id}</span> {title}</Link>
              <span className={`ws-badge state-${f.state}`}>{STATE_LABEL[f.state]}</span>
              {sid && <span className="ws-handle">{sid}</span>}
              {place && <span className="mono small muted" title={ev!.file!}>{place}</span>}
              {f.sink && <span className="ws-chip" title="A write to a shared field">shared field</span>}
            </li>
          );
        })}</ul>
      )}
    </section>
  );
}
```

`IndexPage.tsx` — import `FindingsIndex`; in `IndexTabs`' `count` add `findings: d.findings.length,`; after the `{tab === "checks" && …}` block add `{tab === "findings" && <FindingsIndex />}`.

`CheckList.tsx` — `CheckTile` gets `allFindings?: boolean` in its props; replace `const head = …` with:

```tsx
  const head = <>To check{count && <span className="ck-count">{count}</span>}
    {allFindings && ws.data.findings.length > 0 && <Link className="ck-all" to={ws.link(at({ kind: "index", tab: "findings" }))}
                                                         title="Every finding of the review">All findings</Link>}</>;
```

(re-add the `at` import if Task 6 removed it). Pass `allFindings` on the `CheckTile` in `Overview.tsx` and in `StoryTiles.tsx`.

`workspace.css` — append:

```css
/* Index › Findings (spec 2026-10-12-story-account-and-panels §4) */
.ix-filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 8px 0 12px; font-size: 13px; }
.ix-findings-list li.on { background: var(--hover, transparent); }
.ix-ftitle { flex: 1 1 240px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ck-all { margin-left: auto; font-size: 12px; font-weight: 400; }
```

- [ ] **Step 7: Run the tests**

Run: `cd frontend && npx tsc --noEmit && npm test && npm run build && $E2E e2e/workspace-panels.spec.ts e2e/workspace-reading.spec.ts e2e/workspace-legacy.spec.ts`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/workspace/findings.ts frontend/src/workspace/findings.test.ts frontend/src/workspace/FindingsIndex.tsx frontend/src/workspace/address.ts frontend/src/workspace/address.test.ts frontend/src/workspace/IndexPage.tsx frontend/src/workspace/CheckList.tsx frontend/src/workspace/Overview.tsx frontend/src/workspace/StoryTiles.tsx frontend/src/workspace/workspace.css frontend/e2e/workspace-panels.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(index): a Findings tab lists every finding, filtered by severity and status" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 10: Index › CLs expands each CL's files

**Files:**
- Modify: `frontend/src/workspace/context.ts`, `frontend/src/workspace/Workspace.tsx`, `frontend/src/workspace/IndexPage.tsx` (cls branch, lines 36-49), `frontend/src/workspace/workspace.css`
- Test: `frontend/e2e/workspace-panels.spec.ts`

**Interfaces:**
- Consumes: `d.detail.cls`, `d.about.tree[].files[]` (`{ path, name, action, add, rem, cls }`), `ws.opened({ file, line })`.
- Produces: `Ws.clsOpen: ReadonlySet<number>`, `Ws.setClsOpen(cls: ReadonlySet<number>): void`; per CL row a button named `Show CL <n>'s files` / `Hide CL <n>'s files`; a button `Expand all` / `Collapse all`; file links named `Open <name>'s diff in CL <n>`.

- [ ] **Step 1: Write the failing e2e test**

Append to `frontend/e2e/workspace-panels.spec.ts`:

```ts
test("Index › CLs expands a CL's files in place and opens a file's diff in the panel without leaving", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/i/cls`);
  await page.getByRole("button", { name: "Show CL 101's files" }).click();
  const file = page.getByRole("link", { name: /^Open .+'s diff in CL 101$/ }).first();
  await file.click();
  await expect(page).toHaveURL(new RegExp(`${base}/i/cls\\?open=file`));
  await expect(page.getByRole("complementary", { name: /^Code: / })).toBeVisible();
  await expect(page.getByRole("button", { name: "Hide CL 101's files" })).toBeVisible();      // the list stays as it was
  await page.getByRole("button", { name: "Expand all" }).click();
  await expect(page.getByRole("button", { name: "Hide CL 102's files" })).toBeVisible();
  await page.getByRole("button", { name: "Collapse all" }).click();
  await expect(page.getByRole("link", { name: /'s diff in CL \d+$/ })).toHaveCount(0);
});
```

- [ ] **Step 2: Run it to watch it fail**

Run: `cd frontend && npm run build && $E2E e2e/workspace-panels.spec.ts -g "CLs expands"`
Expected: FAIL — no button named "Show CL 101's files".

- [ ] **Step 3: Visit state**

`context.ts`, in `Ws`:

```ts
  /** The CLs whose files are expanded on Index › CLs this visit (spec 2026-10-12 §5). */
  clsOpen: ReadonlySet<number>;
  setClsOpen: (cls: ReadonlySet<number>) => void;
```

`Workspace.tsx`: `const [clsOpen, setClsOpen] = useState<ReadonlySet<number>>(() => new Set());` and add `clsOpen, setClsOpen` to `ws` and its dependencies.

- [ ] **Step 4: The CLs tab**

In `IndexPage.tsx`, add above `export default function IndexPage`:

```tsx
/** Index › CLs (spec 2026-10-12-story-account-and-panels §5): each CL's files expand under it, and a file opens its diff
 * in the side panel, so the list stays. Which CLs are expanded lasts the visit. */
function ClsTab() {
  const ws = useWs(), d = ws.data, cls = d.detail?.cls ?? [];
  const files = d.about?.tree.flatMap((t) => t.files) ?? [];
  const open = ws.clsOpen, all = cls.length > 0 && cls.every((c) => open.has(c.cl));
  const flip = (cl: number) => {
    const next = new Set(open);
    if (!next.delete(cl)) next.add(cl);
    ws.setClsOpen(next);
  };
  return <>
    {cls.length > 0 && <div className="ix-tools">
      <button className="link" onClick={() => ws.setClsOpen(all ? new Set() : new Set(cls.map((c) => c.cl)))}>
        {all ? "Collapse all" : "Expand all"}</button></div>}
    <ul className="ix-list">{cls.map((c) => {
      const first = plainTitle((c.description ?? "").trim().split("\n")[0]);
      const count = d.about?.cls.find((x) => x.cl === c.cl)?.file_count;
      const mine = files.filter((f) => f.cls.includes(c.cl)), on = open.has(c.cl), verb = on ? "Hide" : "Show";
      return (
        <li key={c.cl}>
          <button className="bd-ibtn ix-exp" aria-expanded={on} aria-label={`${verb} CL ${c.cl}'s files`}
                  title={`${verb} CL ${c.cl}'s files`} onClick={() => flip(c.cl)}>{on ? "▾" : "▸"}</button>
          <Link to={ws.link(ws.item({ kind: "cl", cl: c.cl }))} title={`Open CL ${c.cl}`} aria-label={`Open CL ${c.cl}`}><b>CL {c.cl}</b></Link>
          {c.user && <span className="muted"> {c.user}</span>}
          {!!count && <span className="muted small"> · {count} file{count === 1 ? "" : "s"}</span>}
          {first && <div className="ix-sub">{first}</div>}
          {on && (mine.length ? <ul className="ix-files">{mine.map((f) => (
            <li key={f.path}>
              <Link className="mono" to={ws.link(ws.opened({ file: f.path, line: null }))} title={`Open ${f.path}'s diff`}
                    aria-label={`Open ${f.name}'s diff in CL ${c.cl}`}>{f.path}</Link>
              <span className="muted small"> {f.action}</span>
              <span className="cnt"> <span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span>
            </li>
          ))}</ul> : <p className="muted small ix-files">No files of this CL in the review's change summary.</p>)}
        </li>
      );
    })}</ul>
  </>;
}
```

and replace the whole `{tab === "cls" && ( <ul className="ix-list">…</ul> )}` block with `{tab === "cls" && <ClsTab />}`.

`workspace.css` — append:

```css
/* Index › CLs: a CL's files in place (spec 2026-10-12-story-account-and-panels §5) */
.ix-tools { display: flex; justify-content: flex-end; margin: 4px 0 8px; }
.ix-exp { padding: 0 6px; }
.ix-files { flex-basis: 100%; list-style: none; margin: 4px 0 0 28px; padding: 0; }
.ix-list .ix-files li { border-bottom: 0; padding: 2px 0; }
.ix-files a { min-width: 0; overflow-wrap: anywhere; }
```

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npx tsc --noEmit && npm test && npm run build && $E2E e2e/workspace-panels.spec.ts e2e/workspace-pages.spec.ts e2e/cl-text.spec.ts`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/workspace/context.ts frontend/src/workspace/Workspace.tsx frontend/src/workspace/IndexPage.tsx frontend/src/workspace/workspace.css frontend/e2e/workspace-panels.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(index): CLs expand their files in place; a file opens its diff in the side panel" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 11: Long text in the new views; full suites

**Files:**
- Modify: `frontend/e2e/long-text.spec.ts` (paths list at line 49; a new AI test)
- Modify: `frontend/src/workspace/workspace.css` only if the checks below find a box that overflows

**Interfaces:**
- Consumes: everything above; `longNames`, `problems` helpers already in the spec.
- Produces: no new names.

- [ ] **Step 1: Extend the long-text checks**

In `frontend/e2e/long-text.spec.ts`, change the paths list to:

```ts
  for (const path of ["", "/s/S1", "/s/S2", "/cl/101", "/f/F4?details=1", "/i/cls", "/i/files", "/i/checks", "/i/findings",
                      "/s/S1?open=finding:F4"]) {
```

and append:

```ts
test.describe("with an AI", () => {
  test.use({ baseURL: "http://127.0.0.1:8798" });       // e2e/serve-ai.sh: the fake model writes story accounts

  test("a story's account keeps long names inside its box", async ({ page }) => {
    test.setTimeout(180_000);
    await longNames(page);
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".st-acc").first()).toBeVisible({ timeout: 30_000 });
    await page.waitForLoadState("networkidle");
    expect(await problems(page)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run them**

Run: `cd frontend && npm run build && $E2E e2e/long-text.spec.ts`
Expected: PASS. If a new view is listed as sticking out or cut without a hover text, fix the CSS for that element (wrap a sentence with `overflow-wrap: anywhere`; give a one-line label `min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap` and a `title`) and rerun.

- [ ] **Step 3: Run every suite**

Run:

```bash
cd backend && $PYTEST 2>&1 | tail -3 && $RUFF
cd ../frontend && npx tsc --noEmit && npm test && npm run build && $E2E 2>&1 | tail -15
```

Expected: backend all pass, ruff clean, tsc clean, vitest all pass, Playwright all pass (rerun alone any test that failed on the 60 s `startReview` wait before calling it a failure).

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/long-text.spec.ts frontend/src/workspace/workspace.css
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "test(ui): long names stay inside the findings index, the finding panel and story accounts" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

Then `rm -rf $(git rev-parse --show-toplevel)/.pwtmp`.
