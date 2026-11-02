# Design overview, phase 2 (the model call) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 2 of the design overview (spec §16 item 2): one tier-1 call per review writes the verdict and the
checks it names, what the design must get right, whether the design is right, each walk-through's title and lead and
each condition's false case, from the stories alone; each part is checked on its own, and a part that fails keeps
phase 1's fixed text or is left out.

**Architecture:** `llm/design.py` builds the prompt from the reading and the rules' design (phase 1), asks through
`try_tiers` as `llm/intro.py` does, checks each part of the answer on its own and writes the parts that pass into the
`ReadingDesign`, recording each in `sources`. The design stage runs it on a copy of the rules' design, so a failure of any
kind leaves phase 1's design exactly, and keeps the model's parts in blob `design_text`, keyed by the prompt, so a re-run
of an unchanged review asks nothing. The overview gains the verdict and its chips under the lead, "What it must get
right" after "Where the change sits" and the "Is the design right?" fold before the condition fold; the condition
fold's title and the walk-through titles carry the AI mark when the model wrote them.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, SQLite; React 19, TypeScript, Vite, Vitest (node), Playwright 1.63.

**Spec:** `docs/superpowers/specs/2026-11-02-design-overview-design.md` (§18 holds the notes made against the code;
phase 1's plan, `docs/superpowers/plans/2026-11-02-design-overview-phase1.md`, built what this phase writes into).

## Global Constraints

- Public repo: no owner's proprietary names in code, tests, docs or commits; the bundled fixture's names (`uart_send`,
  `hal_write`, `logger_flush`…) are fine. No absolute local paths in committed files.
- One tier-1 call per review, after `llm/intro.py`, through `try_tiers` and the ledger like every other call (§10); it
  counts against the strong model's per-review budget (`TIER1`).
- Each part is checked on its own (§10): ids must be listed; sentence counts and the house style (`llm/style.py`) must
  hold; a concern must cite a story; `confirm` or `ask` must cite a live cause. A part that fails keeps its fixed text,
  and if there is none it is left out.
- §6.1: a row whose cause doesn't exist is shown as `note` and gets no chip, so the table never creates work the checks
  don't already hold. §6.2: an ownership line cites a node, a file or a story; these lines are opinions, not checks, and
  never reach the head's count.
- §15: a failed call leaves today's overview exactly — phase 1's design, its titles and its fold title.
- No design context in this phase (§16): the concerns come from the stories alone, and their source reads "AI, from the
  stories" (§6.1). No AI menu yet (phase 4).
- AI text carries the AI mark (`AiText`'s edge, or `AiName` on a title), as elsewhere; never hidden.
- Styles: app variables only; the tags `ck-tag.right` and `ck-tag.note` join the existing kinds (§12.2).
- Commits: `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`, messages ending in the
  `Co-Authored-By` and `Claude-Session` lines shown in each task. Stage files by name; never stage
  `frontend/e2e/strong-review.txt`.
- Tests: backend `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider …`
  and `.venv/bin/ruff check codetortoise tests`; frontend `npx vitest run …`, `npm run build`; e2e from `frontend/`
  after `npm run build`: `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test … --retries=0; rm -rf ../.pwtmp`.

## Review Focus

1. **An answer citing what the review lacks, or naming ids in its words:** a verdict or concern citing a cause it was
   not shown, an ownership line citing an unknown file, a node id (`N10`) or cause id in prose — the part fails or the
   row is dropped or turned into a note, and the overview never shows an id (Task 2's cases; the e2e
   `expectNoNodeIds`).
2. **A model that fails, is refused by the budget, answers garbage or breaks the stage's code:** phase 1's design
   stands exactly (titles, fold title, no verdict), the stage is degraded with a note, and the overview renders (Task 2,
   Task 3).
3. **Re-runs:** an unchanged review reuses the kept text with no call; `fresh` asks again; a changed prompt asks again
   (Task 3).
4. **Long AI text on a phone:** a long verdict, concern or ownership line wraps; the concerns table stacks its cells,
   and nothing scrolls sideways (Task 5's phone test).
5. **Two walk-throughs given one title:** the second keeps its fixed title, so the outline's rows and the crumbs stay
   distinct (Task 2).

## Rulings made while planning

| # | Ruling | Why |
|---|---|---|
| P1 | The prompt heads its sections THE CHANGE, THREAD LIST (id, CHECKS BY CAUSE (id, COMPONENTS, FUNCTIONS AND FIELDS, CONDITIONS, WALK-THROUGHS — never "THREADS (id" or "THREAD DETAILS (id" | The fake model (`e2e/fake_llm.py`) and the scripted one (`tests/test_pipeline.py`) route prompts by those markers; "CHECKS BY CAUSE (id" is the design prompt's own |
| P2 | Kinds are listed raw (`hazard`, `confirm`, `result`…), causes hazards first then in reading order, at most 30 (`CAUSES_SHOWN`), nodes at most 60 (`NODES_SHOWN`), a walk-through's steps at most 12 (`STEPS_SHOWN`), the rest counted | §14: about 6k tokens in; only listed ids may be cited |
| P3 | The verdict: 2–3 sentences; it must name at least one listed cause when the prompt lists any, and none it wasn't shown | §3.1: it ends in what to settle and names its causes as chips |
| P4 | A concern: `text` a headline (≤ 8 words, no final period), `how` one sentence, an optional one-sentence `note`, at least one listed story, an assessment of the four; a row failing any of these is dropped. Its causes: any it wasn't shown, or `confirm`/`ask` with none, make it a `note` with no causes. No row at all fails "the concerns" | §6.1, §10, §15 ("a concern citing a missing cause becomes a note") |
| P5 | An ownership line: a tag of the four, 1–2 sentences, at least one cite, every cite a listed story, a listed node id or a changed file of a listed component; otherwise dropped. No lines at all is not a failure (nothing to say) | §6.2, §15 ("an uncited ownership line is dropped") |
| P6 | A walk-through's title (a headline) and lead (1–2 sentences) pass together or neither is used; a title another walk-through already took (case aside) fails | Distinct names in the outline and crumbs |
| P7 | `false_case` is a headline; the fold's title then reads "<false case> · N changes still run" (phase 1's `conditionTitle`) | §7 |
| P8 | Prose and titles name no node, finding or cause id (`N10`, `F2`, `c504c9fbd94`); the prompt says to write names | `expectNoNodeIds`; ids mean nothing to a reader |
| P9 | `sources` gains `verdict`, `concerns`, `ownership`, `walk:W1`…, `gate:G1`… = `llm` for each part the model wrote; a walk-through also keeps `title_source` | §9's per-part sources; phase 4 pins by these keys |
| P10 | Notes name the failed parts — "the verdict", "N concern(s)" or "the concerns", "N ownership line(s)", "N walk-through title(s)", "N condition name(s)" — as "design: … failed the checks"; any note degrades the stage, as the reading's do | Same as the introduction |
| P11 | The stage runs the model part on a deep copy of the rules' design; an exception there is a note ("design text: …") and the rules' design is stored | §15: a failed call leaves today's overview exactly |
| P12 | Blob `design_text` = {key, verdict, verdict_causes, concerns, ownership, walks {id: [title, lead]}, gates {id: false case}, sources}, key = sha256(`DESIGN_VERSION`\|model\|prompt); kept only from an answer with no note; reused unless `fresh` | As `intro_text` |
| P13 | No call for a review without threads | As the introduction |
| P14 | The stage's message gains "; design text by <model>", "; design text by <model> (the strong model failed)" or "; fixed design text" | As the reading's |
| P15 | The verdict sits in the overview's top section between the lead and Start (§3.1 items 1–3), as `.dz-verdict` (not `.ws-lead`, which the lead alone holds); its chips are the shown kinds' | §3.1 |
| P16 | "What it must get right" is a table (Concern, How the change does it, Where, Assessment); Where is its stories' thread letters then the stories as links; Assessment is the tag, the note and the causes as chips. On a phone (≤ 640px) its cells stack | §6.1 |
| P17 | The ownership fold is titled "Is the design right? · N questionable · N shortfall(s)" ("· nothing questionable" with neither); a line shows its tag word, `questionable` styled as `confirm`, its text and its cites (a story as a link, a node by its name, a path as code) | §6.2 |
| P18 | e2e runs on the strong server (`e2e/serve-strong.sh`, CLs 101 and 102), whose fake model gains a design answer | It is the only fixture server with a strong model |

## File map

- Create: `backend/codetortoise/llm/design.py` — the prompt, the checks, `write_design`, the kept text.
- Create: `backend/tests/test_llm_design.py`.
- Modify: `backend/codetortoise/pipeline.py` — the design stage asks the strong model and keeps its text.
- Modify: `backend/codetortoise/llm/ledger.py` — `TIER1` gains `design`.
- Modify: `backend/tests/scripted_llm.py` — `design_answer`.
- Modify: `backend/tests/test_pipeline.py` — `_one_story_per_cl` answers the design prompt; three stage tests.
- Modify: `frontend/src/reading/design.ts`, `frontend/src/reading/design.test.ts` — the verdict's causes, the ownership
  fold's title and tags, a concern's places, whether the model wrote a part.
- Modify: `frontend/src/workspace/Overview.tsx`, `frontend/src/workspace/workspace.css` — the verdict, What it must get
  right, Is the design right?, the AI marks.
- Modify: `frontend/e2e/fake_llm.py`, `frontend/e2e/helpers.ts`; Create: `frontend/e2e/design-text.spec.ts`.
- Modify: `README.md`.

---

### Task 1: The design prompt

**Files:**
- Create: `backend/codetortoise/llm/design.py`
- Test: `backend/tests/test_llm_design.py`

**Interfaces:**
- Consumes: phase 1's `ReadingDesign`, `WalkStep`, `build_design`; `Reading` (`whole`, `threads`, `causes`);
  `StorySet`; the `demo` fixture (`backend/tests/conftest.py`: CLs 101–105).
- Produces: `DESIGN_VERSION`, `CAUSES_SHOWN`, `NODES_SHOWN`, `STEPS_SHOWN`, `SYSTEM`, `ASK`,
  `step_line(d, s) -> str`, `prompt(d, r, ss) -> str`, `_shown(d, r) -> (causes, node ids)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_llm_design.py`:

```python
"""The design overview's model call (spec 2026-11-02 §10): its prompt, the checks on each part, and what they leave."""
import pytest

from codetortoise import design as rules
from codetortoise.llm import design as dl
from codetortoise.llm.design import prompt


@pytest.fixture
def made(demo):
    """The demo's design as the rules build it, a new one per test: the model's parts are written into it."""
    return rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)


def _walk(text: str, wid: str) -> str:
    return text.split(f"\n{wid} | ", 1)[1].split("\nW", 1)[0]


def test_the_prompt_lists_the_threads_checks_components_names_conditions_and_each_walk_through_s_steps(demo, made):
    text = prompt(made, demo.r, demo.ss)
    assert text.startswith(dl.ASK)
    assert "THE CHANGE: A and B: both run inside `main`; B and C: nothing besides arriving in CL 104." in text
    assert "THREAD LIST (id | name | purpose):" in text and "THREADS (id" not in text and "THREAD DETAILS (id" not in text
    assert "\nT1 | `hal_write` in hal | main reaches uart_init, which calls hal_write." in text
    assert ("\n  stories: S2 `hal_write`'s signature changed; `uart_init` calls it (behaviour); S1 `uart_send` can now "
            "return -2; `logger_flush` ignores it (1 more effect) (behaviour)\n") in text
    assert "CHECKS BY CAUSE (id | kind | thread | story | what):" in text
    assert "\nc504c9fbd94 | result | T1 | S1 | `logger_flush` ignores the result of `uart_send`, which can now return -2\n" in text
    assert "\nc072df68d70 | ask | T3 | - | Ask the author how this thread relates to the rest of the change" in text
    assert "COMPONENTS (name | layer | threads | changed files):" in text
    assert "\ndriver | driver | T1 | driver/uart.c, driver/uart.h\n  crossing: `uart_init`, `uart_send` call `hal_write`\n" in text
    assert "\ncpp | cpp, include/hal | T3 | cpp/engine.cpp\n  shares no calls or fields with the rest\n" in text
    assert "\nN10 | uart_send | driver | driver/uart.c:11\n" in text and "\nN26 | Uart::errors | driver | driver/uart.h:15\n" in text
    assert "\nG1 | len > 64 | uart_send | driver/uart.c:16 | 13 | 2\n" in text
    w1 = _walk(text, "W1")
    assert w1.startswith("G1 true | T1 with T2 | S1\n")
    assert "\n  1. `main` calls `logger_flush(&g_log)` (S1's call path)" in w1
    assert "\n  4. `uart_send` writes `Uart::errors`: `*err += 1` (new; S1's change)" in w1
    assert "\n  5. `uart_send` returns `-2` to `logger_flush` (new; S1 flow 1, check c504c9fbd94)" in w1
    assert "\n  6. `logger_flush` returns to `main` (unchanged code)" in w1
    assert "\n  8. `uart_errors` reads `Uart::errors`: `u->errors` (S1 flow 2, check c688d2f20d3)" in w1
    assert _walk(text, "W2").startswith("G1 false | T1 | S1, S2\n") and _walk(text, "W4").startswith("- | T2 | S5, S3\n")


def test_a_long_walk_through_shows_its_first_steps_and_counts_the_rest(demo, made):
    made.walks[0].steps = made.walks[0].steps * 2
    w1 = _walk(prompt(made, demo.r, demo.ss), "W1")
    assert "\n  12. " in w1 and "\n  13. " not in w1 and w1.endswith("\n  … +6 more steps")


def test_the_prompt_lists_at_most_its_share_of_checks_and_names_hazards_first(demo, made, monkeypatch):
    monkeypatch.setattr(dl, "CAUSES_SHOWN", 2)
    monkeypatch.setattr(dl, "NODES_SHOWN", 3)
    made_r = demo.r.model_copy(deep=True)
    made_r.causes[3].kind = "hazard"                         # c504c9fbd94
    text = prompt(made, made_r, demo.ss)
    checks = text.split("CHECKS BY CAUSE (id | kind | thread | story | what):\n", 1)[1].split("\nCOMPONENTS", 1)[0]
    assert [line.split(" | ")[0] for line in checks.splitlines()] == ["c504c9fbd94", "c8143badb9b", "… +4 more checks"]
    names = text.split("FUNCTIONS AND FIELDS (id | name | component | where):\n", 1)[1].split("\nCONDITIONS", 1)[0]
    assert [line.split(" | ")[0] for line in names.splitlines()] == ["N2", "N3", "N4", "… +8 more"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_llm_design.py`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'codetortoise.llm.design'`.

- [ ] **Step 3: Write the prompt**

Create `backend/codetortoise/llm/design.py`:

```python
"""The strong model's parts of the design overview (spec 2026-11-02 §10): the verdict and the checks it names, what the
design must get right (§6.1), whether it is right (§6.2), each walk-through's title and lead (§4.2) and each condition's
false case (§7).

One tier-1 call per review, in the design stage once the rules have built the rest. Each part is checked on its own: it
cites only listed ids, keeps its sentence counts and the house style, and names no id in its words; a concern cites a
story, and one that says to confirm or ask cites a cause the review has. A part that fails keeps its fixed text, or is
left out when it has none.
"""
from __future__ import annotations

from codetortoise.design import ReadingDesign, WalkStep
from codetortoise.llm.style import STYLE
from codetortoise.reading import Cause, Reading
from codetortoise.stories import StorySet

DESIGN_VERSION = 1                    # bump with every change to the prompt or its checks (keys its cache)
CAUSES_SHOWN = 30                     # §14: about 6k tokens in; only what is listed may be cited
NODES_SHOWN = 60
STEPS_SHOWN = 12                      # a walk-through's steps; the rest are counted

SYSTEM = ("You are a senior C/C++ reviewer writing the opening of a review for reviewers who have not seen the change. "
          'Use only what you are given. Reply with one JSON object: {"verdict", "verdict_causes", "concerns": [{"text", '
          '"how", "stories", "assessment", "note", "causes"}], "ownership": [{"tag", "text", "cites"}], "walks": [{"id", '
          '"title", "lead"}], "conditions": [{"id", "false_case"}]}. ' + STYLE)

ASK = """The opening says what the change is for, where it sits and whether its design holds; the checks listed below \
stay the only things a reviewer marks. Write "verdict": 2 or 3 sentences on whether the change holds together, the \
last saying what a reviewer must settle; list in "verdict_causes" the ids of the checks it names. Write "concerns": at \
most 6 rows, each one thing the design must get right: "text" (at most 8 words), "how" (one sentence: how the change \
does it), "stories" (the ids of the stories that do it), "assessment" ("right": it does; "note": worth knowing; \
"confirm": a reviewer must confirm it; "ask": ask the author) and an optional one-sentence "note"; a "confirm" or "ask" \
row lists the checks it rests on in "causes". Write "ownership": short lines on which part owns each decision the \
change makes, or what it leaves undone, each with a "tag" ("right", "questionable", "shortfall" or "note"), one or two \
sentences of "text" and "cites": the ids of the functions or fields, the changed files or the stories it rests on. For \
each walk-through write a "title" (at most 8 words, naming the case it follows, no final period) and a "lead" (1 or 2 \
sentences: what it follows and where it lands). For each condition write "false_case": the case when its test is \
false, in at most 8 words, no final period. Cite only the ids listed. In the words, write names, never ids."""


def _shown(d: ReadingDesign, r: Reading) -> tuple[list[Cause], list[str]]:
    """The causes and the node ids the prompt lists, the only ones an answer may cite: hazards first, then the reading's
    order, at most CAUSES_SHOWN; the design's nodes, at most NODES_SHOWN."""
    causes = sorted(r.causes or [], key=lambda c: c.kind != "hazard")[:CAUSES_SHOWN]
    return causes, list(d.nodes)[:NODES_SHOWN]


def _name(d: ReadingDesign, nid: str) -> str:
    n = d.nodes.get(nid)
    return n.label if n is not None else nid


def step_line(d: ReadingDesign, s: WalkStep) -> str:
    """A walk-through step as the prompt reads it: what happens, in names and code, then whether it is new and where it
    comes from."""
    a, b = f"`{_name(d, s.src)}`", f"`{_name(d, s.dst)}`"
    code = f"`{s.label.replace('`', chr(39))}`" if s.label else ""
    said = {"call": f"{a} calls {code or b}",
            "return": f"{a} returns {code} to {b}" if code else f"{a} returns to {b}",
            "self": f"{a}: {code}" if code else a,
            "write": f"{a} writes {b}" + (f": {code}" if code else ""),
            "read": f"{b} reads {a}" + (f": {code}" if code else ""),
            "fold": f"… {s.folded} more call{'' if s.folded == 1 else 's'}"}[s.kind]
    story = s.story or "a story"
    ref = {"path": f"{story}'s call path", "change": f"{story}'s change",
           "flow": f"{story} flow {s.flow_n}" + (f", check {s.cause}" if s.cause else ""), "code": "unchanged code"}[s.ref]
    return f"{said} ({'; '.join(x for x in ('' if s.status == 'same' else s.status, ref) if x)})"


def prompt(d: ReadingDesign, r: Reading, ss: StorySet) -> str:
    by = {s.id: s for s in ss.stories}
    causes, nodes = _shown(d, r)
    lines = [f"THE CHANGE: {r.whole or '(no summary)'}", "THREAD LIST (id | name | purpose):"]
    for t in r.threads:
        lines.append(f"{t.id} | {t.name} | {t.purpose}")
        lines.append("  stories: " + "; ".join(f"{s} {by[s].title}" + (f": {by[s].purpose}" if by[s].purpose else "")
                                               + f" ({by[s].kind})" for s in t.stories if s in by))
    lines.append("CHECKS BY CAUSE (id | kind | thread | story | what):")
    lines += [f"{c.id} | {c.kind} | {c.thread or '-'} | {c.story or '-'} | {c.text}" for c in causes] or ["(none)"]
    if len(r.causes or []) > len(causes):
        lines.append(f"… +{len(r.causes or []) - len(causes)} more checks")
    lines.append("COMPONENTS (name | layer | threads | changed files):")
    for c in d.components:
        lines.append(f"{c.name} | {c.band} | {', '.join(c.threads) or '-'} | {', '.join(c.files) or '-'}")
        if c.crossing:
            lines.append("  crossing: " + "; ".join(c.crossing))
        elif c.quiet:
            lines.append("  shares no calls or fields with the rest")
    lines.append("FUNCTIONS AND FIELDS (id | name | component | where):")
    for nid in nodes:
        n = d.nodes[nid]
        lines.append(f"{nid} | {n.label} | {n.component or '-'} | {n.path}" + (f":{n.line}" if n.line else ""))
    if len(d.nodes) > len(nodes):
        lines.append(f"… +{len(d.nodes) - len(nodes)} more")
    lines.append("CONDITIONS (id | test | function | where | changed lines that still run when it is false | that stop):")
    lines += [f"{g.id} | {g.test} | {_name(d, g.node)} | {g.path}" + (f":{g.line}" if g.line else "")
              + f" | {g.runs} | {g.stops}" for g in d.gates] or ["(none)"]
    lines.append("WALK-THROUGHS (id | case | anchored on | stories):")
    for w in d.walks:
        case = f"{w.condition} {'true' if w.case else 'false'}" if w.condition else "-"
        anchor = f"{w.connection[0]} with {w.connection[1]}" if w.connection else (w.thread or "-")
        lines.append(f"{w.id} | {case} | {anchor} | {', '.join(w.stories) or '-'}")
        lines += [f"  {i}. {step_line(d, s)}" for i, s in enumerate(w.steps[:STEPS_SHOWN], 1)]
        if len(w.steps) > STEPS_SHOWN:
            lines.append(f"  … +{len(w.steps) - STEPS_SHOWN} more steps")
    if not d.walks:
        lines.append("(none)")
    return ASK + "\n\n" + "\n".join(lines)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_llm_design.py && .venv/bin/ruff check codetortoise tests`
Expected: 3 passed; `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/llm/design.py backend/tests/test_llm_design.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the design overview's prompt: threads, checks by cause, components, names, conditions and each walk-through's steps

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 2: The checks, and `write_design`

**Files:**
- Modify: `backend/codetortoise/llm/design.py`
- Test: `backend/tests/test_llm_design.py`

**Interfaces:**
- Consumes: Task 1's `prompt`, `_shown`; `try_tiers`, `TiersFailed`, `done_text`, `tried_note` (`llm/tiers.py`);
  `Refused` (`llm/ledger.py`); `_styled` (`llm/storyboard.py`); `_SENT` (`llm/threads.py`); `Concern`, `Ownership`.
- Produces: `MAX_CONCERNS = 6`, `MAX_OWNERSHIP = 8`, `ASSESSMENTS`, `TAGS`, `apply_answer(d, r, out) -> list[str]`,
  `write_design(strong, ledger, rid, d, r, ss, weak=None) -> (notes, model | None)`,
  `design_text(d) -> dict`, `apply_design_text(d, kept) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_llm_design.py`:

```python
GOOD = {
    "verdict": "The change holds together, but one new result goes unchecked. Settle whether `logger_flush` must "
               "handle the new -2.",
    "verdict_causes": ["c504c9fbd94"],
    "concerns": [
        {"text": "Senders learn when a write is too long",
         "how": "`uart_send` now returns -2 for a write longer than 64 bytes.", "stories": ["S1"],
         "assessment": "confirm", "note": "`logger_flush` drops the -2.", "causes": ["c504c9fbd94"]},
        {"text": "Register numbers are never negative", "how": "`hal_write` now takes an unsigned register.",
         "stories": ["S2"], "assessment": "right"},
        {"text": "The logger starts at a known level", "how": "`logger_init` now sets the level to 2.",
         "stories": ["S5", "S3"], "assessment": "note"}],
    "ownership": [
        {"tag": "right", "text": "The driver owns the length check.", "cites": ["driver/uart.c"]},
        {"tag": "questionable", "text": "The logger decides what a failed send means, and it drops the result.",
         "cites": ["N3", "S1"]},
        {"tag": "shortfall", "text": "Nothing tells the caller of `logger_write` that a write was dropped.",
         "cites": ["S1"]}],
    "walks": [
        {"id": "W1", "title": "A write longer than 64 bytes",
         "lead": "It follows a long write from `main` into `uart_send` and back."},
        {"id": "W2", "title": "A write that fits", "lead": "It follows a short write down to `hal_write`."},
        {"id": "W3", "title": "Setting up the UART", "lead": "It follows `uart_init` into the new `hal_write`."},
        {"id": "W4", "title": "The logger's level", "lead": "It follows the new level from `logger_init` to "
         "`logger_level`."}],
    "conditions": [{"id": "G1", "false_case": "Writes that fit (64 bytes or less)"}]}


def _with(**part):
    return {**GOOD, **part}


def _write(demo, d, answer, **kw):
    from scripted_llm import ScriptedLlm
    return dl.write_design(ScriptedLlm(lambda s, u: answer), None, None, d, demo.r, demo.ss, **kw)


def test_an_accepted_answer_writes_every_part_and_says_the_model_wrote_it(demo, made):
    assert _write(demo, made, GOOD) == ([], "big")
    assert made.verdict.startswith("The change holds together") and made.verdict_causes == ["c504c9fbd94"]
    assert [(c.text, c.stories, c.assessment, c.note, c.causes) for c in made.concerns] == [
        ("Senders learn when a write is too long", ["S1"], "confirm", "`logger_flush` drops the -2.", ["c504c9fbd94"]),
        ("Register numbers are never negative", ["S2"], "right", "", []),
        ("The logger starts at a known level", ["S5", "S3"], "note", "", [])]
    assert [(o.tag, o.cites) for o in made.ownership] == [
        ("right", ["driver/uart.c"]), ("questionable", ["N3", "S1"]), ("shortfall", ["S1"])]
    assert [(w.id, w.title, w.title_source) for w in made.walks] == [
        ("W1", "A write longer than 64 bytes", "llm"), ("W2", "A write that fits", "llm"),
        ("W3", "Setting up the UART", "llm"), ("W4", "The logger's level", "llm")]
    assert made.walks[0].lead == "It follows a long write from `main` into `uart_send` and back."
    assert made.gates[0].false_case == "Writes that fit (64 bytes or less)"
    assert made.sources == {"verdict": "llm", "concerns": "llm", "ownership": "llm", "walk:W1": "llm", "walk:W2": "llm",
                            "walk:W3": "llm", "walk:W4": "llm", "gate:G1": "llm"}


def test_a_concern_on_a_cause_the_review_lacks_is_a_note_without_chips_and_so_is_a_confirm_on_none(demo, made):
    concerns = [{**GOOD["concerns"][0], "causes": ["c0000000000"]}, {**GOOD["concerns"][0], "causes": []},
                {**GOOD["concerns"][1], "assessment": "ask", "causes": ["c504c9fbd94", "c0000000000"]},
                {**GOOD["concerns"][1], "causes": ["c8143badb9b"]}]
    assert _write(demo, made, _with(concerns=concerns)) == ([], "big")
    assert [(c.assessment, c.causes) for c in made.concerns] == [
        ("note", []), ("note", []), ("note", []), ("right", ["c8143badb9b"])]


def test_each_failing_part_keeps_its_fixed_text_or_is_left_out_and_only_that_part(demo):
    c, o, w = GOOD["concerns"], GOOD["ownership"], GOOD["walks"]
    cases = {
        "a node id in the verdict": (_with(verdict="N10 now returns -2. Settle whether its callers handle it."),
                                     "the verdict"),
        "a cause id in the verdict": (_with(verdict="c504c9fbd94 is open. Settle it."), "the verdict"),
        "a verdict naming no check": (_with(verdict_causes=[]), "the verdict"),
        "a verdict naming a check it was not shown": (_with(verdict_causes=["c0000000000"]), "the verdict"),
        "a four-sentence verdict": (_with(verdict="A holds. B holds. C holds. Settle D."), "the verdict"),
        "a concern on an unlisted story": (_with(concerns=[*c[:2], {**c[2], "stories": ["S9"]}]), "1 concern(s)"),
        "a concern on no story": (_with(concerns=[*c[:2], {**c[2], "stories": []}]), "1 concern(s)"),
        "two sentences of how": (_with(concerns=[{**c[0], "how": "It returns -2. Callers see it."}, *c[1:]]),
                                 "1 concern(s)"),
        "a nine-word concern": (_with(concerns=[{**c[0], "text": "One two three four five six seven eight nine"},
                                                *c[1:]]), "1 concern(s)"),
        "an unknown assessment": (_with(concerns=[{**c[0], "assessment": "maybe"}, *c[1:]]), "1 concern(s)"),
        "no concerns": (_with(concerns=[]), "the concerns"),
        "an uncited ownership line": (_with(ownership=[*o[:2], {**o[2], "cites": []}]), "1 ownership line(s)"),
        "a cite it was not shown": (_with(ownership=[{**o[0], "cites": ["drv/old.c"]}, *o[1:]]), "1 ownership line(s)"),
        "an unknown tag": (_with(ownership=[{**o[0], "tag": "good"}, *o[1:]]), "1 ownership line(s)"),
        "two walk-throughs with one title": (_with(walks=[w[0], {**w[1], "title": "A Write Longer Than 64 Bytes"},
                                                          *w[2:]]), "1 walk-through title(s)"),
        "a title with a final period": (_with(walks=[{**w[0], "title": "A long write."}, *w[1:]]),
                                        "1 walk-through title(s)"),
        "a walk-through with no lead": (_with(walks=[{**w[0], "lead": ""}, *w[1:]]), "1 walk-through title(s)"),
        "a false case naming a node": (_with(conditions=[{"id": "G1", "false_case": "When N10 gets a short write"}]),
                                       "1 condition name(s)"),
    }
    for name, (answer, part) in cases.items():
        d = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
        assert _write(demo, d, answer) == ([f"design: {part} failed the checks"], "big"), name


def test_a_walk_through_whose_title_fails_keeps_its_fixed_title_and_no_lead(demo, made):
    _write(demo, made, _with(walks=[{**GOOD["walks"][0], "title": "A long write."}, *GOOD["walks"][1:]]))
    assert (made.walks[0].title, made.walks[0].lead, made.walks[0].title_source) == ("When `len > 64`", "", "template")
    assert "walk:W1" not in made.sources and made.walks[1].title == "A write that fits"


def test_several_failing_parts_are_named_together(demo, made):
    answer = {"verdict": "", "concerns": [], "ownership": [{"tag": "note", "text": "Uncited.", "cites": []}],
              "walks": [], "conditions": []}
    assert _write(demo, made, answer) == ([
        "design: the verdict, the concerns, 1 ownership line(s), 4 walk-through title(s) and 1 condition name(s) "
        "failed the checks"], "big")


def test_a_model_that_fails_or_is_refused_leaves_the_rules_design_exactly(demo, made):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.ledger import Refused
    before = made.model_dump()
    notes, by = dl.write_design(ScriptedLlm(lambda s, u: RuntimeError("down")), None, None, made, demo.r, demo.ss)
    assert by is None and notes == ["design: big: RuntimeError: down; fresh try: RuntimeError: down; the fixed text stays"]
    assert made.model_dump() == before

    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            assert (purpose, target) == ("design", "design")
            raise Refused("this review has used its 10 tier-1 AI calls")
    notes, by = dl.write_design(ScriptedLlm(lambda s, u: GOOD), Budget(), 1, made, demo.r, demo.ss)
    assert by is None and notes == ["design: AI budget: this review has used its 10 tier-1 AI calls; the fixed text stays"]
    assert made.model_dump() == before


def test_the_design_the_strong_model_fails_is_written_by_the_weak_model_and_says_so(demo, made):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.client import LlmError
    notes, by = dl.write_design(ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x")), None, None,
                                made, demo.r, demo.ss, weak=ScriptedLlm(lambda s, u: GOOD, model="small"))
    assert by == "small" and made.sources["verdict"] == "llm"
    assert notes == ["design: big: invalid JSON twice; fresh try: invalid JSON twice; small wrote it"]


def test_the_kept_text_puts_back_every_part_the_model_wrote(demo, made):
    _write(demo, made, GOOD)
    kept = dl.design_text(made)
    again = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    dl.apply_design_text(again, kept)
    assert again.model_dump() == made.model_dump()


def test_the_design_counts_against_the_tier_1_budget():
    from codetortoise.llm.ledger import TIER1
    assert "design" in TIER1


def test_the_scripted_design_answer_passes_every_check(demo, made):
    from scripted_llm import ScriptedLlm, design_answer
    assert dl.write_design(ScriptedLlm(lambda s, u: design_answer(u)), None, None, made, demo.r, demo.ss) == ([], "big")
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_llm_design.py`
Expected: the 3 prompt tests pass; the new ones FAIL (`AttributeError: module 'codetortoise.llm.design' has no
attribute 'write_design'`, and `ImportError: cannot import name 'design_answer'` for the last).

- [ ] **Step 3: Write the checks**

In `backend/codetortoise/llm/design.py`, replace the import block with:

```python
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from codetortoise.design import Concern, Ownership, ReadingDesign, WalkStep
from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import _styled
from codetortoise.llm.style import STYLE
from codetortoise.llm.threads import _SENT
from codetortoise.llm.tiers import TiersFailed, done_text, tried_note, try_tiers
from codetortoise.reading import Cause, Reading
from codetortoise.stories import StorySet
```

after `STEPS_SHOWN = …` add:

```python
MAX_CONCERNS = 6
MAX_OWNERSHIP = 8
ASSESSMENTS = ("right", "note", "confirm", "ask")
TAGS = ("right", "questionable", "shortfall", "note")
_NO_IDS = re.compile(r"\b(?:[NF]\d+|c[0-9a-f]{10})\b")      # a node, finding or cause id: names belong in the words
```

and at the end of the file add:

```python
class _Concern(BaseModel):
    text: str = ""
    how: str = ""
    stories: list[str] = Field(default_factory=list)
    assessment: str = ""
    note: str = ""
    causes: list[str] = Field(default_factory=list)


class _Owner(BaseModel):
    tag: str = ""
    text: str = ""
    cites: list[str] = Field(default_factory=list)


class _WalkText(BaseModel):
    id: str = ""
    title: str = ""
    lead: str = ""


class _Case(BaseModel):
    id: str = ""
    false_case: str = ""


class _Out(BaseModel):
    verdict: str = ""
    verdict_causes: list[str] = Field(default_factory=list)
    concerns: list[_Concern] = Field(default_factory=list)
    ownership: list[_Owner] = Field(default_factory=list)
    walks: list[_WalkText] = Field(default_factory=list)
    conditions: list[_Case] = Field(default_factory=list)


def _prose(text: str, lo: int, hi: int) -> bool:
    """`lo` to `hi` sentences in the house style, naming no id."""
    return bool(text) and lo <= len(_SENT.split(text)) <= hi and _styled(text, "explanation") and not _NO_IDS.search(text)


def _headline(text: str) -> bool:
    return bool(text) and _styled(text, "headline") and not _NO_IDS.search(text)


def _ids(xs: list[str]) -> list[str]:
    """Cited ids as given, each once, in order."""
    return list(dict.fromkeys(x.strip() for x in xs if x.strip()))


def apply_answer(d: ReadingDesign, r: Reading, out: _Out) -> list[str]:
    """Write each part of `out` that passes its checks into `d`, marking it the model's in `d.sources`; returns the
    parts that failed, worded for a note."""
    causes_shown, nodes_shown = _shown(d, r)
    causes = {c.id for c in causes_shown}
    stories = {s for t in r.threads for s in t.stories}
    citable = stories | set(nodes_shown) | {f for c in d.components for f in c.files}
    bad: list[str] = []
    verdict, named = out.verdict.strip(), _ids(out.verdict_causes)
    if _prose(verdict, 2, 3) and all(c in causes for c in named) and (bool(named) or not causes):
        d.verdict, d.verdict_causes, d.sources["verdict"] = verdict, named, "llm"
    else:
        bad.append("the verdict")
    rows: list[Concern] = []
    dropped = 0
    for c in out.concerns[:MAX_CONCERNS]:
        text, how, note, sids = c.text.strip(), c.how.strip(), c.note.strip(), _ids(c.stories)
        if not (_headline(text) and _prose(how, 1, 1) and (not note or _prose(note, 1, 1)) and sids
                and all(s in stories for s in sids) and c.assessment in ASSESSMENTS):
            dropped += 1
            continue
        named, assessment = _ids(c.causes), c.assessment
        if any(x not in causes for x in named) or (assessment in ("confirm", "ask") and not named):
            assessment, named = "note", []           # a cause the review lacks: no chip, nothing to confirm (§6.1)
        rows.append(Concern(text=text, how=how, stories=sids, assessment=assessment, note=note, causes=named))
    if rows:
        d.concerns, d.sources["concerns"] = rows, "llm"
    if dropped or not rows:
        bad.append(f"{dropped} concern(s)" if rows else "the concerns")
    lines: list[Ownership] = []
    dropped = 0
    for o in out.ownership[:MAX_OWNERSHIP]:
        text, cites = o.text.strip(), _ids(o.cites)
        if o.tag in TAGS and _prose(text, 1, 2) and cites and all(x in citable for x in cites):
            lines.append(Ownership(tag=o.tag, text=text, cites=cites))
        else:
            dropped += 1
    if lines:
        d.ownership, d.sources["ownership"] = lines, "llm"
    if dropped:
        bad.append(f"{dropped} ownership line(s)")
    got, taken, failed = {w.id: w for w in out.walks}, set(), 0
    for w in d.walks:
        a = got.get(w.id)
        title, lead = (a.title.strip(), a.lead.strip()) if a else ("", "")
        if _headline(title) and title.lower() not in taken and _prose(lead, 1, 2):
            w.title, w.lead, w.title_source, d.sources[f"walk:{w.id}"] = title, lead, "llm", "llm"
            taken.add(title.lower())
        else:
            failed += 1
    if failed:
        bad.append(f"{failed} walk-through title(s)")
    cases, failed = {g.id: g for g in out.conditions}, 0
    for g in d.gates:
        a = cases.get(g.id)
        case = a.false_case.strip() if a else ""
        if _headline(case):
            g.false_case, d.sources[f"gate:{g.id}"] = case, "llm"
        else:
            failed += 1
    if failed:
        bad.append(f"{failed} condition name(s)")
    return bad


def write_design(strong: LlmClient, ledger: Ledger | None, rid: int | None, d: ReadingDesign, r: Reading, ss: StorySet,
                 weak: LlmClient | None = None) -> tuple[list[str], str | None]:
    """Write the model's parts of `d` in place from one checked answer; returns notes on the parts that failed, and the
    model that answered (None: every part keeps its fixed text). The strong model failing is tried fresh, then on the
    weak model."""
    text = prompt(d, r, ss)

    def ask(llm: LlmClient) -> _Out:
        return llm.complete_json(SYSTEM, text, _Out)
    try:
        tried = try_tiers(ledger, rid, "design", "design", ask, strong, weak)
    except Refused as e:
        return [f"design: AI budget: {e.reason}; the fixed text stays"], None
    except TiersFailed as e:  # the fixed text stands
        return [tried_note("design", e.failures, "the fixed text stays")], None
    said = [] if tried.tier == "strong" else [tried_note("design", tried.failures, done_text(tried, "wrote it"))]
    bad = apply_answer(d, r, tried.value)
    if not bad:
        return said, tried.model
    joined = bad[0] if len(bad) == 1 else ", ".join(bad[:-1]) + " and " + bad[-1]
    return said + [f"design: {joined} failed the checks"], tried.model


def design_text(d: ReadingDesign) -> dict:
    """The model's parts of `d`, as blob `design_text` keeps them for a re-run of the same prompt."""
    return {"verdict": d.verdict, "verdict_causes": d.verdict_causes,
            "concerns": [c.model_dump() for c in d.concerns], "ownership": [o.model_dump() for o in d.ownership],
            "walks": {w.id: [w.title, w.lead] for w in d.walks if w.title_source == "llm"},
            "gates": {g.id: g.false_case for g in d.gates if d.sources.get(f"gate:{g.id}") == "llm"},
            "sources": dict(d.sources)}


def apply_design_text(d: ReadingDesign, kept: dict) -> None:
    """Put the model's parts kept in blob `design_text` back into `d`, the rules' design of the same prompt."""
    d.verdict, d.verdict_causes = kept["verdict"], list(kept["verdict_causes"])
    d.concerns = [Concern(**c) for c in kept["concerns"]]
    d.ownership = [Ownership(**o) for o in kept["ownership"]]
    for w in d.walks:
        if w.id in kept["walks"]:
            (w.title, w.lead), w.title_source = kept["walks"][w.id], "llm"
    for g in d.gates:
        if g.id in kept["gates"]:
            g.false_case = kept["gates"][g.id]
    d.sources.update(kept["sources"])
```

In `backend/codetortoise/llm/ledger.py`, the tier-1 purposes gain `design`:

```python
TIER1 = ("stories", "stories_merge", "review", "threads", "intro", "design")   # strong-model calls: their own budget (spec 2026-10-05 §9)
```

In `backend/tests/scripted_llm.py`, after `intro_answer` add:

```python
def design_answer(user: str) -> dict:
    """A passing design text for any design prompt (spec 2026-11-02 §10): the verdict names the first check, one concern
    and one ownership line cite the first story, and every walk-through and condition is named."""
    import re
    causes = re.findall(r"^(c[0-9a-f]{10}) \| ", user, re.M)
    first = re.search(r"^  stories: (S\d+) ", user, re.M)
    sid = first.group(1) if first else "S1"
    return {"verdict": "The change holds together. Settle whether its callers handle the new results.",
            "verdict_causes": causes[:1],
            "concerns": [{"text": "Callers handle the new results", "how": "Each caller now checks what it gets back.",
                          "stories": [sid], "assessment": "right"}],
            "ownership": [{"tag": "right", "text": "The driver owns the new checks.", "cites": [sid]}],
            "walks": [{"id": w, "title": f"Case {i} of the change", "lead": "It follows the call to where the change "
                       "lands."} for i, w in enumerate(re.findall(r"^(W\d+) \| ", user, re.M), 1)],
            "conditions": [{"id": g, "false_case": "Writes that fit"} for g in re.findall(r"^(G\d+) \| ", user, re.M)]}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_llm_design.py tests/test_llm_intro.py tests/test_llm_threads.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/llm/design.py backend/codetortoise/llm/ledger.py backend/tests/scripted_llm.py backend/tests/test_llm_design.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the design overview's model call: each part checked on its own, a failing part keeps its fixed text

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 3: The design stage asks the strong model and keeps its text

**Files:**
- Modify: `backend/codetortoise/pipeline.py` (imports; the `design()` stage)
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 2's `write_design`, `design_text`, `apply_design_text`; Task 1's `prompt`, `DESIGN_VERSION`;
  `_strong(svc, answer)` and `_one_story_per_cl` in `tests/test_pipeline.py`; `design_answer` in `tests/scripted_llm.py`.
- Produces: blob `design_text`; the design stage's message suffix (P14); a degraded design stage on any note (P10, P11).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_pipeline.py`, `_one_story_per_cl` answers the design prompt first — after its imports
(`import re` and `from scripted_llm import intro_answer`) its body starts:

```python
    from scripted_llm import design_answer
    if "CHECKS BY CAUSE (id" in user:
        return design_answer(user)
```

and at the end of the file add:

```python
def test_the_strong_model_writes_the_design_text_once_and_a_rerun_reuses_it(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _one_story_per_cl)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert st["design"]["status"] == "ok" and st["design"]["message"].endswith("; design text by big")
    d = svc.store.get_blob(rid, "reading_design")
    assert d["verdict"] == "The change holds together. Settle whether its callers handle the new results."
    assert d["sources"]["verdict"] == "llm" and [c["text"] for c in d["concerns"]] == ["Callers handle the new results"]
    assert d["walks"] and all(w["title_source"] == "llm" and w["title"].startswith("Case ") for w in d["walks"])
    asked = sum("CHECKS BY CAUSE (id" in p for p in llm.prompts)
    run_review(rid, svc)                                            # unchanged: the kept text, no call
    assert sum("CHECKS BY CAUSE (id" in p for p in llm.prompts) == asked == 1
    again = svc.store.get_blob(rid, "reading_design")
    assert (again["verdict"], again["walks"], again["sources"]) == (d["verdict"], d["walks"], d["sources"])
    run_review(rid, svc, fresh=True)                                # the owner asked for fresh text
    assert sum("CHECKS BY CAUSE (id" in p for p in llm.prompts) == 2


def test_a_design_call_that_fails_leaves_the_rules_design_and_says_so(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    _strong(svc, lambda s, u: RuntimeError("down") if "CHECKS BY CAUSE (id" in u else _one_story_per_cl(s, u))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert st["design"]["status"] == "degraded"
    assert st["design"]["message"].endswith("; fixed design text; design: big: RuntimeError: down; fresh try: "
                                            "RuntimeError: down; the fixed text stays")
    d = svc.store.get_blob(rid, "reading_design")
    assert (d["verdict"], d["concerns"], d["ownership"], d["sources"]) == ("", [], [], {})
    assert d["walks"] and all(w["title_source"] == "template" and not w["lead"] for w in d["walks"])
    assert svc.store.get_blob(rid, "design_text") is None


def test_design_text_code_that_breaks_keeps_the_rules_design(fx, tmp_path, monkeypatch):
    from codetortoise import pipeline
    svc = make_services(fx, tmp_path)
    _strong(svc, _one_story_per_cl)

    def boom(*args, **kwargs):
        raise RuntimeError("broken")
    monkeypatch.setattr(pipeline, "write_design", boom)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert st["design"]["status"] == "degraded" and st["design"]["message"].endswith("; design text: RuntimeError: broken")
    d = svc.store.get_blob(rid, "reading_design")
    assert d["walks"] and d["sources"] == {} and all(w["title_source"] == "template" for w in d["walks"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py -k "design"`
Expected: the three new tests FAIL (the stage's message has no "; design text by big", the design no verdict); the
earlier design tests pass.

- [ ] **Step 3: The stage**

In `backend/codetortoise/pipeline.py`, after the `codetortoise.llm.brief_context` import add:

```python
from codetortoise.llm.design import DESIGN_VERSION, apply_design_text, design_text, write_design
from codetortoise.llm.design import prompt as design_prompt
```

and replace the `design()` stage with:

```python
    def design_text_of(d, r, ss, strong):
        """The strong model's parts of design `d` (spec 2026-11-02 §10), written on a copy: the text kept for this
        prompt, or a new answer. Returns what the stage says, its notes and the design."""
        d = d.model_copy(deep=True)
        key = hashlib.sha256(f"{DESIGN_VERSION}|{strong.model}|{design_prompt(d, r, ss)}".encode()).hexdigest()
        kept = store.get_blob(rid, "design_text")
        if kept and kept.get("key") == key and not fresh:
            apply_design_text(d, kept)
            return f"; design text by {strong.model}", [], d
        notes, by = write_design(svc.strong, svc.ledger, rid, d, r, ss, weak=svc.llm)
        if not notes:
            store.put_blob(rid, "design_text", {"key": key, **design_text(d)})
        told = (f"; design text by {by}" if by == strong.model else
                f"; design text by {by} (the strong model failed)" if by else "; fixed design text")
        return told, notes, d

    def design():
        """The design overview (spec 2026-11-02 §4–§7, §10): components, walk-throughs and conditions by rules (R16), then
        the strong model's verdict, concerns, ownership, titles and false cases. Any failure of the model's part leaves
        the rules' design exactly (§15)."""
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
        told, notes = "", []
        strong = cfg.llm.strong
        if svc.strong is not None and strong is not None and r.threads:
            try:
                told, notes, d = design_text_of(d, r, bs.stories, strong)
            except Exception as e:  # the rules' design stands
                notes = [f"design text: {type(e).__name__}: {e}"[:200]]
        store.replace_blobs(rid, ["reading_design"], [], {"reading_design": d})
        msg = f"{len(d.components)} component(s), {len(d.walks)} walk-through(s), {len(d.gates)} condition(s)" + told
        if notes:
            raise Degraded(msg + "; " + "; ".join(notes))
        return msg
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_llm_design.py tests/test_tier1_review.py tests/test_stories_check.py tests/test_web.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; `All checks passed!` (Each strong-model test meets the design prompt now: `_one_story_per_cl`
answers it, and a model that fails everything leaves a degraded design stage on a review already degraded.)

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/pipeline.py backend/tests/test_pipeline.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the design stage asks the strong model for its text once and keeps it for a re-run

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 4: The overview's rules for the model's parts

**Files:**
- Modify: `frontend/src/reading/design.ts`
- Test: `frontend/src/reading/design.test.ts`

**Interfaces:**
- Consumes: `Cause`, `Ownership`, `ReadingDesign`, `Thread` (`reading/types.ts`); `letter` (`reading/checks.ts`);
  `counted` (`lib/tidy.ts`).
- Produces: `verdictCauses(d, causes) -> Cause[]`; `OWNER_TAG`; `ownershipTitle(lines) -> string`;
  `concernWhere(stories, threads) -> { letters: string[]; stories: string[] }`; `byModel(d, part) -> boolean`;
  `citeName(d, cite) -> string`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/reading/design.test.ts`, the import becomes

```ts
import { alsoLine, blockLine, byModel, citeName, componentBands, concernWhere, conditionTitle, foldGate, gateGroups,
  OWNER_TAG, ownershipTitle, showsWhere, verdictCauses } from "./design";
import type { Cause, Component, Gate, GatedLine } from "./types";
```

and at the end of the file add:

```ts
const cause = (id: string): Cause => ({ id, kind: "result", thread: "T1", story: "S1", text: id, places: [], flows: [], finding: null, change: null });

describe("the model's parts (spec 2026-11-02 §3.1, §6)", () => {
  it("chips the causes the verdict names that the review has, in the verdict's order", () => {
    const causes = [cause("c1"), cause("c2"), cause("c3")];
    expect(verdictCauses({ verdict_causes: ["c3", "c9", "c1"] }, causes).map((c) => c.id)).toEqual(["c3", "c1"]);
    expect(verdictCauses({ verdict_causes: ["c1"] }, null)).toEqual([]);
  });

  it("titles the ownership fold by its questionable lines and shortfalls", () => {
    expect(ownershipTitle([{ tag: "right" }, { tag: "questionable" }, { tag: "shortfall" }, { tag: "shortfall" }]))
      .toBe("Is the design right? · 1 questionable · 2 shortfalls");
    expect(ownershipTitle([{ tag: "questionable" }])).toBe("Is the design right? · 1 questionable");
    expect(ownershipTitle([{ tag: "right" }, { tag: "note" }])).toBe("Is the design right? · nothing questionable");
    expect(OWNER_TAG).toEqual({ right: "right", questionable: "confirm", shortfall: "shortfall", note: "note" });
  });

  it("places a concern by its stories' thread letters, each once, then its stories", () => {
    const threads = [{ id: "T1", stories: ["S2", "S1"] }, { id: "T2", stories: ["S3"] }];
    expect(concernWhere(["S1", "S3", "S2"], threads)).toEqual({ letters: ["A", "B"], stories: ["S1", "S3", "S2"] });
    expect(concernWhere(["S9"], threads)).toEqual({ letters: [], stories: ["S9"] });
  });

  it("says which parts the model wrote, and names a cited node", () => {
    const d = { sources: { verdict: "llm", "gate:G1": "pinned", "walk:W1": "template" } as Record<string, "template" | "llm" | "pinned">,
                nodes: { N3: { label: "logger_flush", kind: "function" as const, component: "service", path: "service/logger.c", line: 20 } } };
    expect([byModel(d, "verdict"), byModel(d, "gate:G1"), byModel(d, "walk:W1"), byModel(d, "concerns"), byModel(null, "verdict")])
      .toEqual([true, true, false, false, false]);
    expect([citeName(d, "N3"), citeName(d, "S1"), citeName(d, "driver/uart.c")]).toEqual(["logger_flush", "S1", "driver/uart.c"]);
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run (from `frontend/`): `npx vitest run src/reading/design.test.ts`
Expected: FAIL: `verdictCauses` (and the others) are not exported.

- [ ] **Step 3: Write the rules**

In `frontend/src/reading/design.ts`, the type import becomes

```ts
import type { Cause, Component, Gate, GatedLine, Ownership, ReadingDesign, Thread } from "./types";
```

and at the end of the file add:

```ts
/** The verdict's chips (spec 2026-11-02 §3.1): the causes it names that the review has, in its order. */
export function verdictCauses(d: Pick<ReadingDesign, "verdict_causes">, causes: Cause[] | null | undefined): Cause[] {
  const by = new Map((causes ?? []).map((c) => [c.id, c]));
  return d.verdict_causes.flatMap((id) => by.get(id) ?? []);
}

/** An ownership line's tag as the check tags draw it (§6.2): a questionable line looks like a `confirm` tag. */
export const OWNER_TAG: Record<Ownership["tag"], string> = { right: "right", questionable: "confirm", shortfall: "shortfall", note: "note" };

/** The ownership fold's title (§3.1 item 8): how many lines are questionable and how many are shortfalls. */
export function ownershipTitle(lines: Pick<Ownership, "tag">[]): string {
  const q = lines.filter((l) => l.tag === "questionable").length, s = lines.filter((l) => l.tag === "shortfall").length;
  const said = [q ? `${q} questionable` : "", counted(s, "shortfall")].filter(Boolean);
  return `Is the design right? · ${said.length ? said.join(" · ") : "nothing questionable"}`;
}

/** Where a concern is done (§6.1): the letters of its stories' threads, each once, then its stories. */
export function concernWhere(stories: string[], threads: Pick<Thread, "id" | "stories">[]): { letters: string[]; stories: string[] } {
  const letters: string[] = [];
  for (const s of stories) {
    const i = threads.findIndex((t) => t.stories.includes(s));
    const L = i < 0 ? null : letter(i, threads[i].id);
    if (L && !letters.includes(L)) letters.push(L);
  }
  return { letters, stories };
}

/** Whether the model wrote a part — `verdict`, `concerns`, `ownership`, `walk:W1`, `gate:G1` — as the design's sources
 * say (§9); a pinned part is the model's words kept (phase 4). */
export const byModel = (d: Pick<ReadingDesign, "sources"> | null | undefined, part: string): boolean =>
  d?.sources[part] === "llm" || d?.sources[part] === "pinned";

/** An ownership line's cite as the reader sees it (§6.2): a function's or field's name for its id; a story id or a path
 * as cited. */
export const citeName = (d: Pick<ReadingDesign, "nodes">, cite: string): string => d.nodes[cite]?.label ?? cite;
```

- [ ] **Step 4: Run them to see them pass**

Run (from `frontend/`): `npx vitest run src/reading/design.test.ts && npx tsc --noEmit`
Expected: all pass; tsc clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/reading/design.ts frontend/src/reading/design.test.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the overview's rules for the model's design parts: the verdict's chips, the ownership fold's title, a concern's places

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 5: The overview shows the verdict, what it must get right and whether it is right

**Files:**
- Modify: `frontend/src/workspace/Overview.tsx`, `frontend/src/workspace/workspace.css`, `frontend/e2e/fake_llm.py`,
  `frontend/e2e/helpers.ts`
- Create: `frontend/e2e/design-text.spec.ts`

**Interfaces:**
- Consumes: Task 4's `verdictCauses`, `OWNER_TAG`, `ownershipTitle`, `concernWhere`, `byModel`, `citeName`; `Chips`
  (`workspace/Chips.tsx`); `shown` (`reading/causes.ts`); `AiText`, `AiName`; Task 1's prompt markers (P1); `startReview`,
  `openFold`, `sideways`, `expectNoNodeIds`, `expectNamed`, `STRONG`, `test` (`e2e/helpers.ts`).
- Produces: `.ov-top .dz-verdict` (its `p.ai-text`, `.st-chips`, `.dz-src`); `section.dz-concerns` (a region named
  "What it must get right": `.dz-src`, `.dz-table table` with `thead` and a `tbody tr` per concern: `td` 1 the concern,
  2 how, 3 `.dz-c-where` (`.ov-letter` per thread, a link per story), 4 `.ck-tag`, `.dz-c-note`, `.st-chips`); the fold
  region "Is the design right?" (`ul.dz-owner > li`: `.ck-tag`, the text, `.dz-cites`); `Fold`'s `ai` prop; the walk
  lines' titles in `AiName`; `openFold`'s name "Is the design right?"; `design(user)` in `e2e/fake_llm.py`, answered
  first in `answer()`.

- [ ] **Step 1: Write the failing e2e tests**


Create `frontend/e2e/design-text.spec.ts`:

```ts
import { devices, expect } from "@playwright/test";
import { expectNamed, expectNoNodeIds, openFold, sideways, startReview, STRONG, test } from "./helpers";

// e2e/serve-strong.sh: CLs 101 and 102, stories from the fake strong model (e2e/fake_llm.py), whose design answer
// writes the verdict, three concerns, three ownership lines, the walk-throughs' titles and the condition's false case.
const VERDICT = "The change holds together, but one new result goes unchecked. Settle whether logger_flush must handle the new -2.";
const HAZARD = "logger_flush ignores the new -2, so a failed send goes unnoticed.";

test.describe("the strong model's design text", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("the verdict says what to settle and names its check as a chip, edged as AI", async ({ page }) => {
    await startReview(page);
    const verdict = page.locator(".ov-top .dz-verdict");
    await expect(verdict.locator("p.ai-text")).toHaveText(`Written by AI. ${VERDICT}`);
    await expect(verdict.locator(".st-chip")).toHaveText([HAZARD]);
    await expect(verdict.locator(".dz-src")).toHaveText("AI, from the stories");
    await verdict.locator(".st-chip").click();
    await expect(page.locator(".cs")).toBeVisible();                        // a chip opens its check, as chips do elsewhere
  });

  test("what it must get right is a row per concern: how the change does it, where, and its assessment", async ({ page }) => {
    await startReview(page);
    const section = page.getByRole("region", { name: "What it must get right" }), rows = section.locator("tbody tr");
    await expect(section.locator(".dz-src")).toHaveText("AI, from the stories");
    await expect(section.locator(".dz-table")).toHaveClass(/\bai-text\b/);
    await expect(section.locator("thead th")).toHaveText(["Concern", "How the change does it", "Where", "Assessment"]);
    await expect(rows).toHaveCount(3);
    const first = rows.first();
    await expect(first.locator("td").nth(0)).toHaveText("Senders learn when a write is too long");
    await expect(first.locator("td").nth(1)).toHaveText("uart_send now returns -2 for a write longer than 64 bytes.");
    await expect(first.locator(".dz-c-where .ov-letter")).toHaveText(["A"]);
    await expect(first.locator(".dz-c-where a")).toHaveText(["S1"]);
    await expect(first.locator(".dz-c-note")).toHaveText(" logger_flush drops the -2.");
    await expect(first.locator(".st-chip")).toHaveText([HAZARD]);
    await expect(rows.locator(".ck-tag")).toHaveText(["confirm", "right", "note"]);
    await expect(rows.nth(2).locator(".dz-c-where a")).toHaveText(["S1", "S2"]);
    await expectNamed(page);
    await expectNoNodeIds(page);
    await first.locator(".dz-c-where a").click();
    await expect(page).toHaveURL(/\/s\/S1(\?|$)/);
  });

  test("is the design right? counts its questionable lines and shortfalls, each line tagged and citing its code or story", async ({ page }) => {
    await startReview(page);
    await expect(page.getByRole("heading", { name: "Is the design right? · 1 questionable · 1 shortfall" })).toBeVisible();
    const fold = await openFold(page, "Is the design right?"), lines = fold.locator("ul.dz-owner > li");
    await expect(lines).toHaveCount(3);
    await expect(lines.locator(".ck-tag")).toHaveText(["right", "questionable", "shortfall"]);
    await expect(lines.nth(1).locator(".ck-tag")).toHaveClass(/\bconfirm\b/);       // a questionable line looks like a confirm tag
    await expect(lines.first()).toHaveClass(/\bai-text\b/);
    await expect(lines.first()).toContainText("The driver owns the length check.");
    await expect(lines.first().locator(".dz-cites code")).toHaveText(["driver/uart.c"]);
    await expect(lines.nth(1).locator(".dz-cites a")).toHaveText(["S1"]);
    await expectNoNodeIds(page);
  });

  test("the walk-throughs and the condition carry the model's names, marked as AI", async ({ page }) => {
    const base = await startReview(page);
    const walks = page.locator("section.ov-sec").first().locator(".dz-walks a");
    await expect(walks).toHaveCount(3);
    const titles = ["A write longer than 64 bytes", "A write that fits", "Setting up the UART"];
    for (const [i, t] of titles.entries()) await expect(walks.nth(i)).toHaveAttribute("aria-label", `Walk through: ${t}`);
    await expect(walks.locator(".ai-name")).toHaveCount(3);
    await expect(page.getByRole("heading", { name: /Writes that fit \(64 bytes or less\) · 7 changes still run$/ })).toBeVisible();
    await expect(page.getByRole("region", { name: "When the condition is false" }).locator("summary .ai-name")).toHaveCount(1);
    await walks.first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/walk/W1$`));
    await expect(page.locator(".dz-walk h2 .ai-name")).toHaveText("Written by AI: A write longer than 64 bytes");
    await expect(page.locator(".dz-walk p.ai-text").first()).toContainText("It follows a long write from main into uart_send and back.");
    await expect(page.locator("aside.ws-outline .ws-row.walk[aria-current='page']"))
      .toHaveAttribute("aria-label", /^Walk through: A write longer than 64 bytes, 9 steps/);
  });
});

test.describe("the strong model's design text on a phone", () => {
  test.use({ baseURL: STRONG, viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
             deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("each concern's cells stack under one another, and nothing scrolls sideways", async ({ page }) => {
    await startReview(page);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    const section = page.getByRole("region", { name: "What it must get right" }), cells = section.locator("tbody tr").first().locator("td");
    await expect(cells).toHaveCount(4);
    await expect(section.locator("thead")).toBeHidden();
    const [a, b] = [await cells.nth(0).boundingBox(), await cells.nth(1).boundingBox()];
    expect(b!.y).toBeGreaterThanOrEqual(a!.y + a!.height - 1);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
    await openFold(page, "Is the design right?");
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});
```

In `frontend/e2e/helpers.ts`, `openFold`'s names gain the ownership fold:

```ts
export async function openFold(page: Page, name: "Is the design right?" | "When the condition is false" | "Build impact" | "Coverage" | "Discussion"): Promise<Locator> {
```

- [ ] **Step 2: The fake strong model's design answer**


In `frontend/e2e/fake_llm.py`, before `def answer(` add:

```python
TITLES = ["A write longer than 64 bytes", "A write that fits", "Setting up the UART"]
LEADS = ["It follows a long write from `main` into `uart_send` and back.", "It follows a short write down to `hal_write`.",
         "It follows `uart_init` into the new `hal_write`."]


def design(user: str) -> dict:
    """The design overview's parts (spec 2026-11-02 §10): the verdict names the hazard, three concerns, three ownership
    lines, a title and a lead for each walk-through and the condition's false case; every part passes its checks."""
    causes = re.findall(r"^(c[0-9a-f]{10}) \| (\w+) \|", user, re.M)
    hazard = next((c for c, kind in causes if kind == "hazard"), causes[0][0] if causes else None)
    listed = re.findall(r"\b(S\d+) ", " ".join(re.findall(r"^  stories: (.*)$", user, re.M)))
    s1 = "S1" if "S1" in listed else listed[0] if listed else "S1"
    s2 = "S2" if "S2" in listed else s1
    path = "driver/uart.c" if "driver/uart.c" in user else s1
    walks, gates = re.findall(r"^(W\d+) \| ", user, re.M), re.findall(r"^(G\d+) \| ", user, re.M)
    return {"verdict": "The change holds together, but one new result goes unchecked. Settle whether `logger_flush` "
                       "must handle the new -2.",
            "verdict_causes": [hazard] if hazard else [],
            "concerns": [
                {"text": "Senders learn when a write is too long",
                 "how": "`uart_send` now returns -2 for a write longer than 64 bytes.", "stories": [s1],
                 "assessment": "confirm", "note": "`logger_flush` drops the -2.", "causes": [hazard] if hazard else []},
                {"text": "Register numbers are never negative", "how": "`hal_write` now takes an unsigned register.",
                 "stories": [s2], "assessment": "right", "note": "", "causes": []},
                {"text": "The error count stays readable", "how": "`uart_errors` reads the count that `uart_send` now writes.",
                 "stories": [s1, s2], "assessment": "note", "note": "", "causes": []}],
            "ownership": [
                {"tag": "right", "text": "The driver owns the length check.", "cites": [path]},
                {"tag": "questionable", "text": "The logger decides what a failed send means, and it drops the result.",
                 "cites": [s1]},
                {"tag": "shortfall", "text": "Nothing tells the caller of `logger_write` that a write was dropped.",
                 "cites": [s1]}],
            "walks": [{"id": w, "title": TITLES[i] if i < len(TITLES) else f"Path {i + 1} through the change",
                       "lead": LEADS[i] if i < len(LEADS) else "It follows the call to where the change lands."}
                      for i, w in enumerate(walks)],
            "conditions": [{"id": g, "false_case": "Writes that fit (64 bytes or less)"} for g in gates]}
```

and `answer()` asks it first:

```python
def answer(system: str, user: str) -> dict:
    if "CHECKS BY CAUSE (id" in user:
        return design(user)
    if "THREAD DETAILS (id" in user:
```


- [ ] **Step 3: Run the e2e tests to see them fail**

Run (from `frontend/`): `npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/design-text.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: all 5 FAIL. The stage now writes the model's parts, but the overview shows none of them: no `.dz-verdict`,
no "What it must get right" region, no "Is the design right?" fold, and no `.ai-name` on the walk lines.

- [ ] **Step 4: The parts**


In `frontend/src/workspace/Overview.tsx`:

- imports: `import { Fragment, type ReactNode, useState } from "react";`; `import { openCount, shown } from
  "../reading/causes";`; the design import becomes

```ts
import { alsoLine, blockLine, byModel, citeName, componentBands, concernWhere, conditionTitle, foldGate, gateGroups,
  OWNER_TAG, ownershipTitle, showsWhere, verdictCauses } from "../reading/design";
```

  and add `import Chips from "./Chips";` after the `./context` import;
- in `ThreadSection`'s walk lines, the title is the model's when it wrote it:

```tsx
          <span aria-hidden>▶ </span>Walk through: <AiName ai={w.title_source === "llm"}><Ticks text={w.title} /></AiName> ›</Link></li>
```

- before `WhereItSits` add:

```tsx
/** The verdict (spec 2026-11-02 §3.1): two or three sentences ending in what to settle, the checks it names as chips (a
 * chip opens its check, as chips do elsewhere), and where it comes from: the stories alone until a design context
 * comes (phase 3). */
function Verdict({ d, r }: { d: ReadingDesign; r: Reading }) {
  const ws = useWs();
  return (
    <div className="dz-verdict">
      <AiText><Ticks text={d.verdict} /></AiText>
      <Chips causes={shown(verdictCauses(d, r.causes), ws.hidden)} />
      <p className="dz-src">AI, from the stories</p>
    </div>
  );
}

/** What it must get right (§6.1): a row per thing the design must get right, how the change does it, where (its stories'
 * thread letters and the stories), and the assessment with its note and the checks it rests on. Nothing here is a new
 * check: a chip is one the review already has. */
function Concerns({ d, r }: { d: ReadingDesign; r: Reading }) {
  const ws = useWs(), by = new Map((r.causes ?? []).map((c) => [c.id, c]));
  const titles = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st.title]));
  return (
    <section className="dz-concerns" aria-labelledby="dz-concerns">
      <h2 id="dz-concerns">What it must get right</h2>
      <p className="dz-src">AI, from the stories</p>
      <AiText as="div" className="dz-table">
        <table>
          <thead><tr><th>Concern</th><th>How the change does it</th><th>Where</th><th>Assessment</th></tr></thead>
          <tbody>{d.concerns.map((c, i) => {
            const where = concernWhere(c.stories, r.threads);
            return (
              <tr key={i}>
                <td className="dz-c-text"><Ticks text={c.text} /></td>
                <td><Ticks text={c.how} /></td>
                <td className="dz-c-where">
                  {where.letters.map((L) => <span key={L} className="ov-letter" title={`Thread ${L}`}>{L}</span>)}
                  {where.stories.map((s) => (
                    <Link key={s} className="ws-handle link" to={storyTo(ws, s)} title={bare(titles.get(s) ?? s)}
                          aria-label={`Go to story ${s}: ${short(titles.get(s) ?? s)}`}>{s}</Link>
                  ))}
                </td>
                <td>
                  <span className={`ck-tag ${c.assessment}`}>{c.assessment}</span>
                  {c.note && <span className="dz-c-note"> <Ticks text={c.note} /></span>}
                  <Chips causes={shown(c.causes.flatMap((id) => by.get(id) ?? []), ws.hidden)} />
                </td>
              </tr>
            );
          })}</tbody>
        </table>
      </AiText>
    </section>
  );
}

/** Is the design right? (§6.2): a line on which part owns each decision the change makes, or what it leaves undone, each
 * tagged and citing the story, the code or the file it rests on. Opinions, not checks: nothing here is counted. */
function OwnershipLines({ d }: { d: ReadingDesign }) {
  const ws = useWs(), titles = new Map((ws.data.stories?.stories ?? []).map((st) => [st.id, st.title]));
  return (
    <ul className="ov-lines dz-owner">{d.ownership.map((o, i) => (
      <AiText as="li" key={i}>
        <span className={`ck-tag ${OWNER_TAG[o.tag]}`}>{o.tag}</span> <Ticks text={o.text} />
        <span className="dz-cites">{o.cites.map((c, k) => (
          <Fragment key={c}>{k > 0 && ", "}{titles.has(c)
            ? <Link className="ws-handle link" to={storyTo(ws, c)} title={bare(titles.get(c)!)}
                    aria-label={`Go to story ${c}: ${short(titles.get(c)!)}`}>{c}</Link>
            : <code>{citeName(d, c)}</code>}</Fragment>
        ))}</span>
      </AiText>
    ))}</ul>
  );
}
```

- `Fold` takes `ai`, its title the model's words when it wrote them:

```tsx
function Fold({ name, title, open, ai = false, children }: { name: string; title: string; open?: boolean; ai?: boolean; children: ReactNode }) {
  return (
    <section aria-label={name}>
      <details className="ov-fold" open={open}>
        <summary><h2><AiName ai={ai}><Ticks text={title} /></AiName></h2></summary>
        {children}
      </details>
    </section>
  );
}
```

- in `Overview`, the verdict follows the lead:

```tsx
        {r.whole && <AiText className="ws-lead" ai={r.whole_source === "llm"}><Ticks text={r.whole} /></AiText>}
        {design?.verdict && <Verdict d={design} r={r} />}
```

  What it must get right follows Where the change sits:

```tsx
      {design && showsWhere(design) && <WhereItSits d={design} r={r} />}
      {design && design.concerns.length > 0 && <Concerns d={design} r={r} />}
```

  and the condition fold gives way to the ownership fold, then follows it with its AI mark:

```tsx
      {design && design.ownership.length > 0 && (
        <Fold name="Is the design right?" title={ownershipTitle(design.ownership)}><OwnershipLines d={design} /></Fold>
      )}
      {gate && <Fold name="When the condition is false" title={conditionTitle(gate)} ai={byModel(design, `gate:${gate.id}`)}>
        <ConditionLines g={gate} /></Fold>}
```

- the `Overview` doc comment's list gains "the verdict" after the lead, "what it must get right" after where the
  change sits, and "whether the design is right" before the condition fold.

- [ ] **Step 5: Style it**


Append to `frontend/src/workspace/workspace.css`:

```css
/* the strong model's design parts (spec 2026-11-02 §3.1, §6): the verdict and its chips, What it must get right, and Is
   the design right?; the tags right, note and shortfall join the check kinds */
.ov3 .dz-verdict { margin: 10px 0 0; }
.ov3 .dz-verdict > p.ai-text { margin: 0; font-size: 15px; line-height: 1.6; }
.dz-src { margin: 4px 0 0; font-size: 12px; color: var(--muted); }
.ov3 .dz-concerns { margin: 18px 0 10px; }
.ov3 .dz-concerns > h2 { margin: 0; }
.dz-table table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 8px; font-size: 13px; }
.dz-table th { text-align: left; font: 600 12px var(--sans); color: var(--muted); padding: 4px 8px; border-bottom: 1px solid var(--line); }
.dz-table th:nth-child(1) { width: 24%; } .dz-table th:nth-child(2) { width: 34%; }
.dz-table th:nth-child(3) { width: 14%; } .dz-table th:nth-child(4) { width: 28%; }
.dz-table td { vertical-align: top; padding: 6px 8px; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
.dz-table .dz-c-text { font-weight: 600; }
.dz-c-where .ov-letter { margin-right: 4px; }
.dz-c-where a { margin-right: 6px; }
.dz-table .st-chips { margin-top: 4px; }
.ck-tag.right { background: color-mix(in srgb, var(--ok) 14%, var(--surface)); color: var(--ok); }
.ck-tag.note { background: var(--gap-bg); color: var(--muted); }
.ck-tag.shortfall { background: color-mix(in srgb, var(--bad) 10%, var(--surface)); color: var(--bad); border: 1px dashed var(--bad); }
.dz-owner li { overflow-wrap: anywhere; }
.dz-cites { margin-left: 6px; font-size: 12px; color: var(--muted); }
@media (max-width: 640px) {
  .dz-table table, .dz-table tbody, .dz-table tr, .dz-table td { display: block; width: auto; }
  .dz-table thead { display: none; }
  .dz-table tr { padding: 8px 0; border-bottom: 1px solid var(--line); }
  .dz-table td { border: 0; padding: 2px 0; }
}
```


- [ ] **Step 6: Run the e2e tests, and the others that read the overview**

Run (from `frontend/`): `npx tsc --noEmit && npx vitest run && npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/design-text.spec.ts e2e/workspace-tier1.spec.ts e2e/outline-causes.spec.ts e2e/workspace-pages.spec.ts e2e/walk-throughs.spec.ts e2e/workspace-reading.spec.ts e2e/thread-sections.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: all pass. (The default server has no strong model, so its overview is unchanged; the strong server's
outline now names the walk-throughs as the model did.)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/workspace/Overview.tsx frontend/src/workspace/workspace.css frontend/e2e/fake_llm.py frontend/e2e/helpers.ts frontend/e2e/design-text.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the overview shows the verdict, what the design must get right and whether it is right, marked as AI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 6: The README, and every suite

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: the README's account of the model's design parts; every suite green.

- [ ] **Step 1: Say it in the README**

In `README.md`, after the paragraph that begins "The overview also says **where the change sits**" add:

```markdown
With a strong model, the design stage also asks it once for the opening of the overview: a **verdict** that ends in
what to settle, with the checks it names as chips; **what it must get right**, a row per concern with how the change
does it, where, and an assessment (right, note, confirm, ask); an **Is the design right?** fold on which part owns each
decision and what the change leaves undone; and a name and a lead for each walk-through and each condition. Each part
is checked on its own: it cites only what it was shown, a concern that says to confirm or ask rests on a check the
review already has, and a part that fails keeps its fixed text or is left out. None of it adds a check. A re-run of the
same change reuses the answer.
```

- [ ] **Step 2: Run every suite**

Run:

```bash
cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider > ../.superpowers/pytest.log 2>&1; tail -3 ../.superpowers/pytest.log; .venv/bin/ruff check codetortoise tests
cd ../frontend && npm run build > /dev/null && npx vitest run 2>&1 | tail -4
mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test --retries=0 > ../.superpowers/e2e.log 2>&1; tail -5 ../.superpowers/e2e.log; rm -rf ../.pwtmp
```

Expected: pytest all pass; ruff "All checks passed!"; the build clean; vitest all pass; Playwright all pass. A failure
here is a finding about this branch: debug it (superpowers:systematic-debugging), fix it under a failing test, and
ledger the ruling.

- [ ] **Step 3: Commit**

```bash
git add README.md
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "docs: the README tells of the strong model's verdict, concerns, ownership and names

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```
