# Design overview, phase 4 (the AI menu) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 4 of the design overview (spec §16 item 4): every part of the opening the strong model wrote — the
verdict, what it must get right, the ownership lines, a walk-through's title and lead, a condition's name — carries a
"Rewrite ▾" menu: *Rewrite* asks the model for that part alone again, *Rewrite with an instruction…* adds the reader's
words to the prompt, and *Pin this text* (the review's owner) keeps the words through later runs of the design stage.

**Architecture:** `llm/design.py` learns to ask for one part (`rewrite_part`): the design's whole prompt, the part as it
stands and the reader's instruction, answered through the tiers, charged to whoever asked, and checked by the same
per-part checks (`apply_answer(only=…)`). `codetortoise/design_pins.py` keeps pins in blob `design_pins`: each holds the
part's words and the names of what it cites, so `design_part` can put it back after the model has written the rest —
a walk-through or a condition found by what it is, a function by its name, a story by its title — and drop one that no
longer fits. `llm/ondemand.py` runs a rewrite as an AI job (the Explain pattern: the call outside the review's lock, the
result stored under it, only onto the design the AI saw) and pins or unpins under the lock. Two routes serve them. The
frontend's `RewriteMenu` has Explain ▾'s shape, sits on each AI part's source line, and the reading reloads when a
rewrite lands.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, SQLite; React 19, TypeScript, Vite, Vitest (node), Playwright 1.63.

**Spec:** `docs/superpowers/specs/2026-11-02-design-overview-design.md` (§10's AI menu, §11's two routes, §12.3, §16
item 4; §18 holds the notes made against the code). Phases 1–3 (`docs/superpowers/plans/2026-11-02-design-overview-phase1.md`
… `-phase3.md`) built the parts this menu rewrites.

## Global Constraints

- Public repo: no owner's proprietary names in code, tests, docs or commits; the bundled fixture's names (`uart_send`,
  `hal_write`, `logger_flush`…) are fine. No absolute local paths in committed files.
- §10: "Rewrite" re-asks that part alone; "Rewrite with an instruction…" adds the reviewer's words to the prompt; "Pin
  this text" stores it in `sources` as pinned, so a re-run keeps it. Each part's answer passes the same checks as in the
  design call (listed ids, sentence counts, house style, no ids in the words).
- §11: `POST /api/reviews/{id}/design/{part}/rewrite` (optional instruction) and `POST /api/reviews/{id}/design/{part}/pin`
  (pin or unpin); parts `verdict`, `concerns`, `ownership`, `walk:W1`, `gate:G1`.
- §12.3: the menu has Explain ▾'s shape (`.ai-menuwrap`, `.ai-menu`), labelled "Rewrite ▾"; AI text keeps its AI mark.
- Security and budget: a rewrite is one AI call on the review's budget, charged to whoever asked, refused (429) over
  the review's budget or their daily limit; anyone in the review may rewrite (as anyone may Explain); only the review's
  owner pins or unpins (403 for anyone else), since a pin decides what every later run keeps. The reviewer's instruction
  is at most 300 characters and only ever reaches the prompt; the answer is checked as any other.
- Styles: app variables only (`dz-*` in `workspace.css`).
- Commits: `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`, messages ending in the
  `Co-Authored-By` and `Claude-Session` lines shown in each task. Stage files by name; never stage
  `frontend/e2e/strong-review.txt`.
- Tests: backend `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider …`
  and `.venv/bin/ruff check codetortoise tests`; frontend `npx vitest run …`, `npx tsc --noEmit`, `npm run build`; e2e
  from `frontend/` after `npm run build`: `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test … --retries=0; rm -rf ../.pwtmp`.

## Review Focus

1. **Two people at once:** a rewrite of the verdict lands while another reader's rewrite of the concerns is out, or
   while the owner pins a part, or while the design context is saved and the design stage re-runs — each lands on the
   design as it is then or is dropped with "the review changed…", never undoing another's change (Task 3).
2. **A pin across runs:** a pinned walk-through after a hand condition renumbers the walk-throughs, a pinned ownership
   line after a re-run renumbers its functions, a pin whose check or story is gone — the pin finds its part again by
   what it is, or is dropped with a note in the design stage's message; the stage is not degraded (Task 2).
3. **A rewrite then a re-run:** the owner re-runs the same change after a rewrite; the kept answer must hold the
   rewrite, not bring the old words back (Task 1's `patch_kept`, Task 3's test).
4. **An answer that fails, or no model:** the rewrite's answer fails the part's checks, or every tier fails, or the
   budget refuses it — nothing changes and the menu says why (Task 1, Task 3, Task 4).
5. **The menu on a phone and for someone else:** the open menu does not push the page sideways; someone who is not
   the owner gets no Pin item, and a pinned part's rewrite items are off with the reason on hover (Task 4, Task 5).

## Rulings made while planning

| # | Ruling | Why |
|---|---|---|
| Q1 | A rewrite is charged as `purpose="rewrite"` to the person who asked: the review's tier-2 budget and their daily limit, not the tier-1 budget | It is a reader's on-demand call, like Explain; charging the tier-1 budget would let rewrites starve the next run's stories |
| Q2 | A rewrite goes through `try_tiers` (strong, fresh, weak), which gains a `user` argument | §10: the model call "runs through `try_tiers` and the ledger like every other call" |
| Q3 | The rewrite prompt is the design's whole prompt, then "REWRITE: write {the part} again, and nothing else. As it stands:" with the part's words, "Reply with the same JSON object holding only {keys}.", and the reader's instruction last when given | The part's checks need the same listed ids; quoting the part lets "shorter" mean something |
| Q4 | Anyone in the review rewrites; only the owner pins and unpins; a pinned part is not rewritten (409) until unpinned | Explain's precedent for rewriting; a pin decides what every later run keeps, as the design context (owner-only) does |
| Q5 | A rewrite also patches blob `design_text` (the kept answer) when its key is the current prompt's, so a re-run of the same change keeps the rewrite | Without it, a re-run would bring back the words the reader replaced |
| Q6 | Pins live in blob `design_pins`, applied in `design_part` after the model's answer (or the rules alone). A walk-through is matched by its condition, side and steps by name; a condition by its function's name and test; an ownership cite to a function by its name; a story by its title; checks and files by id. A pin that no longer fits is dropped and named in the stage's message; the stage is not degraded by it | Walk-through and condition ids follow the order the rules list them in, which a hand condition changes; node ids follow the run |
| Q7 | Only the model's words are pinned (409 for a part whose `sources` is not `llm`/`pinned`); unpinning puts the part back to `llm` | "Pin this text" keeps the AI's words; template text is the rules' and comes back by itself |
| Q8 | The menu shows on a part only when the strong model wrote it (`byModel`) and a strong model is configured (`/ai`'s `strong`); plain Rewrite asks for confirmation ("Replace the {part}? It costs 1 AI call."), as Explain again does; the instruction box's button is "Ask" | Explain's shape (§12.3); "Rewrite" twice would be two controls with one name |
| Q9 | A pinned part's source line ends " · pinned" | Readers see why a re-run left it as it was |

## File map

| File | Change |
|---|---|
| `backend/codetortoise/llm/tiers.py` | `try_tiers(user=)` |
| `backend/codetortoise/llm/design.py` | `apply_answer(only=)`; `has_part`, `part_text`, `rewrite_prompt`, `rewrite_part`, `put_part`, `patch_kept`, `design_key` |
| `backend/codetortoise/design_pins.py` | new: `Pin`, `walk_key`, `gate_key`, `story_titles`, `pin_of`, `apply_pins`, `load_pins` |
| `backend/codetortoise/pipeline.py` | `_design_text` keys by `design_key`; `design_part` applies the pins |
| `backend/codetortoise/llm/ondemand.py` | `Pinned`, `check_part`, `rewrite_design`, `pin_design` |
| `backend/codetortoise/web/app.py` | the two routes |
| `backend/tests/test_llm_design.py`, `test_pipeline.py` | new cases |
| `backend/tests/test_design_pins.py`, `test_design_ai.py` | new |
| `frontend/src/api.ts` | `rewriteDesign`, `pinDesign` |
| `frontend/src/reading/design.ts` (+ test) | `partSource`, `rewriteItems` |
| `frontend/src/workspace/RewriteMenu.tsx` | new: `RewriteMenu`, `SourceRow` |
| `frontend/src/workspace/Overview.tsx`, `WalkPage.tsx` | the source rows |
| `frontend/src/workspace/useReview.ts` | a finished rewrite reloads the reading |
| `frontend/src/workspace/workspace.css` | `dz-srcrow`, `dz-rewrite` |
| `frontend/e2e/fake_llm.py`, `e2e/design-rewrite.spec.ts` | the fake model rewrites; e2e |
| `README.md` | the AI menu |

---

### Task 1: The model writes one part again

**Files:**
- Modify: `backend/codetortoise/llm/tiers.py` (`try_tiers`)
- Modify: `backend/codetortoise/llm/design.py`
- Modify: `backend/codetortoise/pipeline.py:171-186` (`_design_text`)
- Test: `backend/tests/test_llm_design.py`

**Interfaces:**
- Consumes: `prompt`, `apply_answer`, `design_text`, `apply_design_text`, `_Out`, `SYSTEM` (llm/design.py); `try_tiers`.
- Produces:
  - `try_tiers(ledger, rid, purpose, target, fn, strong, weak, skip_strong=False, user: str | None = None)`;
  - `MAX_INSTRUCTION = 300`;
  - `apply_answer(d, r, out, only: str | None = None) -> list[str]`;
  - `has_part(d: ReadingDesign, part: str) -> bool`;
  - `part_text(d, part) -> str`; `rewrite_prompt(d, r, ss, part, context="", instruction="") -> str`;
  - `rewrite_part(strong, ledger, rid, user, d, r, ss, part, instruction="", context="", weak=None) -> tuple[ReadingDesign | None, str]`;
  - `put_part(dst: ReadingDesign, src: ReadingDesign, part: str) -> None`;
  - `patch_kept(kept: dict, d: ReadingDesign, part: str) -> dict`;
  - `design_key(model: str, text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_llm_design.py`:

```python
REWRITTEN = "One new result goes unchecked. Settle whether `logger_flush` must handle the new -2."


class _Calls:
    """A ledger that records each call, then makes it."""

    def __init__(self):
        self.calls = []

    def call(self, llm, rid, user, purpose, target, fn):
        self.calls.append((rid, user, purpose, target))
        return fn(llm)


def test_the_parts_a_rewrite_may_ask_for(made):
    assert all(dl.has_part(made, p) for p in ("verdict", "concerns", "ownership", "walk:W1", "gate:G1"))
    assert not any(dl.has_part(made, p) for p in ("walk:W9", "gate:G9", "verdict:x", "nodes", "walk", ""))


def test_a_rewrite_asks_for_one_part_as_it_stands_with_the_reader_s_instruction(demo, made):
    _write(demo, made, GOOD)
    text = dl.rewrite_prompt(made, demo.r, demo.ss, "walk:W2", "Never drop a byte.", "  Name the register it writes ")
    assert text.startswith(prompt(made, demo.r, demo.ss, "Never drop a byte.") + "\n\n")
    assert text.endswith("\n\nREWRITE: write walk-through W2's title and lead again, and nothing else. As it stands:\n"
                         "title: A write that fits\nlead: It follows a short write down to `hal_write`.\n"
                         'Reply with the same JSON object holding only "walks", with that walk-through alone.\n'
                         "THE REVIEWER'S INSTRUCTION (follow it within the rules above): Name the register it writes")
    assert dl.rewrite_prompt(made, demo.r, demo.ss, "verdict").endswith(
        "\n\nREWRITE: write the verdict again, and nothing else. As it stands:\n" + GOOD["verdict"]
        + '\nReply with the same JSON object holding only "verdict" and "verdict_causes".')
    assert ("As it stands:\n1. Senders learn when a write is too long: `uart_send` now returns -2 for a write longer than "
            "64 bytes. (confirm: `logger_flush` drops the -2.)\n2. ") in dl.rewrite_prompt(made, demo.r, demo.ss, "concerns")
    assert "As it stands:\nright: The driver owns the length check.\nquestionable: " in dl.rewrite_prompt(
        made, demo.r, demo.ss, "ownership")
    assert "As it stands:\nfalse case: Writes that fit (64 bytes or less)\nReply" in dl.rewrite_prompt(
        made, demo.r, demo.ss, "gate:G1")
    fresh = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    assert "As it stands:\n(none)\nReply" in dl.rewrite_prompt(fresh, demo.r, demo.ss, "verdict")


def test_a_rewrite_changes_that_part_alone_and_is_charged_to_whoever_asked(demo, made):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.ledger import TIER1
    _write(demo, made, GOOD)
    before = made.model_dump()
    ledger = _Calls()
    answer = _with(verdict=REWRITTEN, concerns=GOOD["concerns"][:1], walks=[{**GOOD["walks"][0], "title": "Another"}])
    new, by = dl.rewrite_part(ScriptedLlm(lambda s, u: answer), ledger, 7, "bob", made, demo.r, demo.ss, "verdict",
                              instruction="Shorter")
    assert by == "big" and ledger.calls == [(7, "bob", "rewrite", "verdict")] and "rewrite" not in TIER1
    assert made.model_dump() == before                              # the design it was given is left as it was
    assert (new.verdict, new.verdict_causes, new.sources["verdict"]) == (REWRITTEN, ["c504c9fbd94"], "llm")
    rest = {k: v for k, v in new.model_dump().items() if k not in ("verdict", "verdict_causes")}
    assert rest == {k: v for k, v in before.items() if k not in ("verdict", "verdict_causes")}


def test_a_rewritten_title_must_differ_from_the_others_and_an_answer_that_fails_changes_nothing(demo, made):
    from scripted_llm import ScriptedLlm
    _write(demo, made, GOOD)

    def walk(title):
        return _with(walks=[{"id": "W2", "title": title, "lead": "It follows a short write to the register."}])
    new, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: walk("A short write")), None, None, None, made, demo.r, demo.ss,
                             "walk:W2")
    assert [w.title for w in new.walks] == ["A write longer than 64 bytes", "A short write", "Setting up the UART",
                                            "The logger's level"]
    assert new.walks[1].lead == "It follows a short write to the register." and new.sources["walk:W2"] == "llm"
    same, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: walk("Setting up the UART")), None, None, None, made, demo.r,
                              demo.ss, "walk:W2")
    assert same is None                                             # W3's title already
    bad, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(verdict="Too short.")), None, None, None, made, demo.r,
                             demo.ss, "verdict")
    assert bad is None
    gone, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(ownership=[])), None, None, None, made, demo.r, demo.ss,
                              "ownership")
    assert gone is None


def test_a_rewrite_over_a_limit_is_refused_and_one_no_model_answers_raises(demo, made):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.ledger import Refused
    from codetortoise.llm.tiers import TiersFailed

    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            raise Refused("you've used your 20 AI calls today")
    with pytest.raises(Refused):
        dl.rewrite_part(ScriptedLlm(lambda s, u: GOOD), Budget(), 1, "bob", made, demo.r, demo.ss, "verdict")
    with pytest.raises(TiersFailed, match="big: RuntimeError: down; fresh try: RuntimeError: down"):
        dl.rewrite_part(ScriptedLlm(lambda s, u: RuntimeError("down")), None, None, "bob", made, demo.r, demo.ss,
                        "verdict")


def test_a_rewrite_lands_on_the_design_as_it_is_then_and_on_the_kept_text(demo, made):
    from scripted_llm import ScriptedLlm
    _write(demo, made, GOOD)
    kept = dl.design_text(made)
    new, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(verdict=REWRITTEN)), None, None, None, made, demo.r,
                             demo.ss, "verdict")
    now = made.model_copy(deep=True)
    now.concerns = now.concerns[:1]                                 # another part changed meanwhile
    dl.put_part(now, new, "verdict")
    assert now.verdict == REWRITTEN and len(now.concerns) == 1
    walk, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(walks=[{**GOOD["walks"][1], "title": "A short write"}])),
                              None, None, None, made, demo.r, demo.ss, "walk:W2")
    dl.put_part(now, walk, "walk:W2")
    assert now.walks[1].title == "A short write" and now.walks[0].title == "A write longer than 64 bytes"
    again = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    dl.apply_design_text(again, dl.patch_kept(dl.patch_kept(kept, now, "verdict"), now, "walk:W2"))
    assert again.verdict == REWRITTEN and again.walks[1].title == "A short write"
    assert [c.text for c in again.concerns] == [c["text"] for c in GOOD["concerns"]]


def test_the_kept_text_is_keyed_by_the_prompt_the_model_and_the_version(demo, made):
    text = prompt(made, demo.r, demo.ss)
    assert dl.design_key("big", text) == dl.design_key("big", text) != dl.design_key("small", text)
    assert dl.design_key("big", text) != dl.design_key("big", text + " ")
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_llm_design.py`
Expected: the seven new tests FAIL with `AttributeError: module 'codetortoise.llm.design' has no attribute 'has_part'` (and `rewrite_prompt`, `rewrite_part`, `design_key`); the others pass.

- [ ] **Step 3: `try_tiers` charges whoever asked**

In `backend/codetortoise/llm/tiers.py`, replace the head of `try_tiers` and its ledger call:

```python
def try_tiers[T](ledger: Ledger | None, rid: int | None, purpose: str, target: str, fn: Callable[[LlmClient], T],
              strong: LlmClient, weak: LlmClient | None, skip_strong: bool = False, user: str | None = None) -> Tried[T]:
    """`fn` on each try in turn until one answers. Refused (the budget) stops at once; an unreachable strong model
    is not tried fresh; `skip_strong` starts at the weak model. `user`: whom the calls are charged to (None: the
    pipeline). Raises TiersFailed when every try failed."""
```

and, in its loop:

```python
            value = ledger.call(llm, rid, user, purpose, tgt, fn) if ledger is not None else fn(llm)
```

- [ ] **Step 4: One part, asked again**

In `backend/codetortoise/llm/design.py`:

1. Add `import hashlib` above `import re`, and after `TAGS = …`:

```python
MAX_INSTRUCTION = 300                 # a reader's instruction to a rewrite, in characters (§10's AI menu)
_WHAT = {"verdict": "the verdict", "concerns": "the concerns", "ownership": "the ownership lines"}
_KEYS = {"verdict": '"verdict" and "verdict_causes"', "concerns": '"concerns"', "ownership": '"ownership"',
         "walk": '"walks", with that walk-through alone', "gate": '"conditions", with that condition alone'}
```

2. Replace `apply_answer` with this version (the checks are unchanged; each part is gated by `asks`, and a rewritten
   title must differ from every other walk-through's):

```python
def apply_answer(d: ReadingDesign, r: Reading, out: _Out, only: str | None = None) -> list[str]:
    """Write each part of `out` that passes its checks into `d`, marking it the model's in `d.sources`; returns the
    parts that failed, worded for a note. `only`: the one part a rewrite asks for (`verdict`, `concerns`, `ownership`,
    `walk:W1`, `gate:G1`); the rest of `out` is not read, and a walk-through's title must differ from every other's."""
    causes_shown, nodes_shown = _shown(d, r)
    causes = {c.id for c in causes_shown}
    stories = {s for t in r.threads for s in t.stories}
    citable = stories | set(nodes_shown) | {f for c in d.components for f in c.files}

    def asks(part: str) -> bool:
        return only is None or only == part
    bad: list[str] = []
    if asks("verdict"):
        verdict, named = out.verdict.strip(), _ids(out.verdict_causes)
        if _prose(verdict, 2, 3) and all(c in causes for c in named) and (bool(named) or not causes):
            d.verdict, d.verdict_causes, d.sources["verdict"] = verdict, named, "llm"
        else:
            bad.append("the verdict")
    if asks("concerns"):
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
                assessment, named = "note", []       # a cause the review lacks: no chip, nothing to confirm (§6.1)
            rows.append(Concern(text=text, how=how, stories=sids, assessment=assessment, note=note, causes=named))
        if rows:
            d.concerns, d.sources["concerns"] = rows, "llm"
        if dropped or not rows:
            bad.append(f"{dropped} concern(s)" if rows else "the concerns")
    if asks("ownership"):
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
    got, failed = {w.id: w for w in out.walks}, 0
    taken = {w.title.lower() for w in d.walks if not asks(f"walk:{w.id}")}
    for w in d.walks:
        if not asks(f"walk:{w.id}"):
            continue
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
        if not asks(f"gate:{g.id}"):
            continue
        a = cases.get(g.id)
        case = a.false_case.strip() if a else ""
        if _headline(case):
            g.false_case, d.sources[f"gate:{g.id}"] = case, "llm"
        else:
            failed += 1
    if failed:
        bad.append(f"{failed} condition name(s)")
    return bad
```

3. After `apply_design_text`, add:

```python
def design_key(model: str, text: str) -> str:
    """What blob `design_text` is kept under: the prompt, the model that answered it and DESIGN_VERSION."""
    return hashlib.sha256(f"{DESIGN_VERSION}|{model}|{text}".encode()).hexdigest()


def has_part(d: ReadingDesign, part: str) -> bool:
    """Whether `part` names a part of `d` the model writes: `verdict`, `concerns`, `ownership`, `walk:W1`, `gate:G1`."""
    kind, sep, pid = part.partition(":")
    if kind == "walk":
        return any(w.id == pid for w in d.walks)
    if kind == "gate":
        return any(g.id == pid for g in d.gates)
    return not sep and kind in _WHAT


def part_text(d: ReadingDesign, part: str) -> str:
    """Part `part` of `d` as it stands, as a rewrite's prompt quotes it; "(none)" when it has no words yet."""
    kind, _, pid = part.partition(":")
    if kind == "verdict":
        lines = [d.verdict] if d.verdict else []
    elif kind == "concerns":
        lines = [f"{i}. {c.text}: {c.how} ({c.assessment}{': ' + c.note if c.note else ''})"
                 for i, c in enumerate(d.concerns, 1)]
    elif kind == "ownership":
        lines = [f"{o.tag}: {o.text}" for o in d.ownership]
    elif kind == "walk":
        w = next(w for w in d.walks if w.id == pid)
        lines = [f"title: {w.title}"] + ([f"lead: {w.lead}"] if w.lead else [])
    else:
        g = next(g for g in d.gates if g.id == pid)
        lines = [f"false case: {g.false_case}"] if g.false_case else []
    return "\n".join(lines) or "(none)"


def rewrite_prompt(d: ReadingDesign, r: Reading, ss: StorySet, part: str, context: str = "",
                   instruction: str = "") -> str:
    """The prompt that asks for one part again (§10's AI menu): the design's whole prompt, so the same ids are listed
    and the same checks hold, then the part as it stands, then the reader's instruction when there is one."""
    kind, _, pid = part.partition(":")
    what = _WHAT.get(kind) or (f"walk-through {pid}'s title and lead" if kind == "walk" else f"condition {pid}'s false case")
    tail = [f"REWRITE: write {what} again, and nothing else. As it stands:", part_text(d, part),
            f"Reply with the same JSON object holding only {_KEYS[kind]}."]
    if instruction.strip():
        tail.append(f"THE REVIEWER'S INSTRUCTION (follow it within the rules above): {instruction.strip()}")
    return prompt(d, r, ss, context) + "\n\n" + "\n".join(tail)


def rewrite_part(strong: LlmClient, ledger: Ledger | None, rid: int | None, user: str | None, d: ReadingDesign,
                 r: Reading, ss: StorySet, part: str, instruction: str = "", context: str = "",
                 weak: LlmClient | None = None) -> tuple[ReadingDesign | None, str]:
    """Ask for part `part` of `d` again (§10's AI menu), charged to `user` as a "rewrite", with their instruction when
    given, through the tiers as the design call goes. Returns a copy of `d` with that part rewritten and marked the
    model's (None: the answer failed the part's checks) and the model that answered; `d` is left as it was. Raises
    Refused over a limit and TiersFailed when no model answered."""
    text = rewrite_prompt(d, r, ss, part, context, instruction)

    def ask(llm: LlmClient) -> _Out:
        return llm.complete_json(SYSTEM, text, _Out)
    tried = try_tiers(ledger, rid, "rewrite", part, ask, strong, weak, user=user)
    trial = d.model_copy(deep=True)
    trial.sources.pop(part, None)
    apply_answer(trial, r, tried.value, only=part)
    return (trial if trial.sources.get(part) == "llm" else None), tried.model


def put_part(dst: ReadingDesign, src: ReadingDesign, part: str) -> None:
    """Copy part `part` of `src` into `dst`, its source with it: a rewrite lands on the design as it is by then."""
    kind, _, pid = part.partition(":")
    if kind == "verdict":
        dst.verdict, dst.verdict_causes = src.verdict, list(src.verdict_causes)
    elif kind == "concerns":
        dst.concerns = [c.model_copy(deep=True) for c in src.concerns]
    elif kind == "ownership":
        dst.ownership = [o.model_copy(deep=True) for o in src.ownership]
    elif kind == "walk":
        a, b = (next(w for w in x.walks if w.id == pid) for x in (src, dst))
        b.title, b.lead, b.title_source = a.title, a.lead, a.title_source
    else:
        a, b = (next(g for g in x.gates if g.id == pid) for x in (src, dst))
        b.false_case = a.false_case
    dst.sources[part] = src.sources[part]


def patch_kept(kept: dict, d: ReadingDesign, part: str) -> dict:
    """Blob `design_text` with part `part` as `d` now has it: a later run of the same prompt keeps a rewrite."""
    now, (kind, _, pid) = design_text(d), part.partition(":")
    out = {**kept, "sources": {**kept["sources"], part: "llm"}}
    if kind == "verdict":
        out["verdict"], out["verdict_causes"] = now["verdict"], now["verdict_causes"]
    elif kind in ("concerns", "ownership"):
        out[kind] = now[kind]
    elif kind == "walk":
        out["walks"] = {**kept["walks"], pid: now["walks"][pid]}
    else:
        out["gates"] = {**kept["gates"], pid: now["gates"][pid]}
    return out
```

4. In `backend/codetortoise/pipeline.py`, key the kept text by `design_key`. The import line becomes:

```python
from codetortoise.llm.design import apply_design_text, design_key, design_text, write_design
```

and in `_design_text` the key line becomes:

```python
    key = design_key(strong.model, design_prompt(d, r, ss, context))
```

- [ ] **Step 5: Run them to see them pass, with the pipeline's design tests**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_llm_design.py tests/test_pipeline.py -k "design or rewrite or part or kept" && .venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff "All checks passed!".

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/llm/tiers.py backend/codetortoise/llm/design.py backend/codetortoise/pipeline.py backend/tests/test_llm_design.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the strong model writes one part of the design overview again, with a reader's instruction

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 2: Pins, and the design stage puts them back

**Files:**
- Create: `backend/codetortoise/design_pins.py`
- Modify: `backend/codetortoise/pipeline.py` (`design_part`)
- Test: `backend/tests/test_design_pins.py` (new), `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `ReadingDesign`, `Concern`, `Ownership`, `Walk`, `Gate` (design.py); `Reading` (reading.py); a `StorySet`.
- Produces:
  - `BLOB = "design_pins"`; `class Pin(BaseModel)` with `part`, `key`, `verdict`, `verdict_causes`, `concerns`,
    `ownership`, `title`, `lead`, `false_case`, `nodes: dict[str, str]`, `stories: dict[str, str]`;
  - `gate_key(d, g) -> str`; `walk_key(d, w) -> str`; `story_titles(ss) -> dict[str, str]`;
  - `pin_of(d, part, titles) -> Pin`;
  - `apply_pins(d, r, titles, pins) -> tuple[list[Pin], list[str]]`;
  - `load_pins(store, rid) -> list[Pin]`;
  - `design_part` names each dropped pin in its message and stores the pins that still fit.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_design_pins.py`:

```python
"""Pinned design text (spec 2026-11-02 §10): what a pin keeps, and how a later design finds its part again."""
import pytest
from test_llm_design import GOOD

from codetortoise import design as rules
from codetortoise.design_pins import apply_pins, pin_of, story_titles, walk_key
from codetortoise.llm import design as dl


def _rules(demo):
    return rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)


@pytest.fixture
def written(demo):
    """The demo's design with every part of GOOD written into it."""
    d = _rules(demo)
    assert dl.apply_answer(d, demo.r, dl._Out.model_validate(GOOD)) == []
    return d


def test_a_pin_keeps_the_part_s_words_and_the_names_of_what_it_cites(demo, written):
    titles = story_titles(demo.ss)
    v = pin_of(written, "verdict", titles)
    assert (v.part, v.verdict, v.verdict_causes) == ("verdict", GOOD["verdict"], ["c504c9fbd94"])
    o = pin_of(written, "ownership", titles)
    assert o.nodes == {"N3": written.nodes["N3"].label} and o.stories == {"S1": titles["S1"]}
    assert set(pin_of(written, "concerns", titles).stories) == {"S1", "S2", "S5", "S3"}
    w = pin_of(written, "walk:W1", titles)
    assert (w.part, w.title, w.key) == ("walk", "A write longer than 64 bytes", walk_key(written, written.walks[0]))
    g = pin_of(written, "gate:G1", titles)
    assert (g.part, g.false_case, g.key) == ("gate", "Writes that fit (64 bytes or less)", "uart_send|len > 64")


def test_a_fresh_design_takes_each_pin_and_marks_its_part_pinned(demo, written):
    titles = story_titles(demo.ss)
    pins = [pin_of(written, p, titles) for p in ("verdict", "concerns", "ownership", "walk:W1", "gate:G1")]
    fresh = _rules(demo)
    assert apply_pins(fresh, demo.r, titles, pins) == (pins, [])
    assert (fresh.verdict, fresh.concerns, fresh.ownership) == (written.verdict, written.concerns, written.ownership)
    assert (fresh.walks[0].title, fresh.walks[0].lead, fresh.walks[0].title_source) == (
        written.walks[0].title, written.walks[0].lead, "llm")
    assert fresh.gates[0].false_case == written.gates[0].false_case
    assert fresh.sources == {"verdict": "pinned", "concerns": "pinned", "ownership": "pinned", "walk:W1": "pinned",
                             "gate:G1": "pinned"}


def test_a_walk_through_s_pin_finds_it_by_what_it_is_and_a_function_by_its_name(demo, written):
    titles = story_titles(demo.ss)
    pins = [pin_of(written, "walk:W1", titles), pin_of(written, "ownership", titles)]
    fresh = _rules(demo)
    fresh.walks.reverse()                                            # listed in another order: W1 is W4 now
    for i, w in enumerate(fresh.walks, 1):
        w.id = f"W{i}"
    fresh.nodes["N99"] = fresh.nodes.pop("N3")                       # the function the ownership line cites, renumbered
    for w in fresh.walks:
        w.parts = ["N99" if n == "N3" else n for n in w.parts]
        for s in w.steps:
            s.src, s.dst = ("N99" if s.src == "N3" else s.src), ("N99" if s.dst == "N3" else s.dst)
    for g in fresh.gates:
        g.node = "N99" if g.node == "N3" else g.node
    assert apply_pins(fresh, demo.r, titles, pins) == (pins, [])
    assert fresh.walks[3].title == "A write longer than 64 bytes" and fresh.sources["walk:W4"] == "pinned"
    assert fresh.ownership[1].cites == ["N99", "S1"] and "walk:W1" not in fresh.sources


def test_a_pin_that_no_longer_fits_is_dropped_with_a_note(demo, written):
    titles = story_titles(demo.ss)
    pins = [pin_of(written, p, titles) for p in ("verdict", "concerns", "ownership", "walk:W1", "gate:G1")]
    r = demo.r.model_copy(deep=True)
    r.causes = [c for c in r.causes if c.id != "c504c9fbd94"]       # the check the verdict names is gone
    fresh = _rules(demo)
    fresh.walks[0].steps = fresh.walks[0].steps[:-1]                # W1 ends elsewhere now
    fresh.gates[0].test = "len > 128"                               # and its condition reads otherwise
    kept, notes = apply_pins(fresh, r, {**titles, "S1": "Another story"}, pins)
    assert kept == [] and notes == ["the pinned verdict no longer fits the change and was unpinned",
                                    "the pinned concerns no longer fit the change and were unpinned",
                                    "the pinned ownership lines no longer fit the change and were unpinned",
                                    "a pinned walk-through title no longer fits the change and was unpinned",
                                    "a pinned condition name no longer fits the change and was unpinned"]
    assert (fresh.verdict, fresh.concerns, fresh.ownership, fresh.sources) == ("", [], [], {})
```

Append to `backend/tests/test_pipeline.py`:

```python
def test_a_pinned_part_outlives_a_design_re_run_that_writes_the_rest_again(fx, tmp_path):
    from codetortoise import boardstore
    from codetortoise.design import ReadingDesign
    from codetortoise.design_pins import BLOB, load_pins, pin_of, story_titles
    from codetortoise.pipeline import run_design

    def answer(system, user):
        out = _one_story_per_cl(system, user)
        if "CHECKS BY CAUSE (id" in user and "DESIGN CONTEXT (from" in user:
            out = {**out, "verdict": "The change holds against its context. Settle whether its callers handle the new "
                                     "results.",
                   "ownership": [{**out["ownership"][0], "text": "The driver owns the new checks, as the context asks."}]}
        return out
    svc = make_services(fx, tmp_path)
    _strong(svc, answer)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    d = ReadingDesign.model_validate(svc.store.get_blob(rid, "reading_design"))
    svc.store.put_blob(rid, BLOB, [pin_of(d, "verdict", story_titles(boardstore.stories(svc.store, rid)))])
    _context(svc, rid, notes="Never drop a byte.")
    run_design(rid, svc)
    again = svc.store.get_blob(rid, "reading_design")
    assert (again["verdict"], again["sources"]["verdict"]) == (d.verdict, "pinned")
    assert again["ownership"][0]["text"] == "The driver owns the new checks, as the context asks."
    assert again["sources"]["ownership"] == "llm" and len(load_pins(svc.store, rid)) == 1


def test_a_pin_that_no_longer_fits_is_dropped_and_the_design_stage_says_so(fx, tmp_path):
    from codetortoise.design import ReadingDesign
    from codetortoise.design_pins import BLOB, load_pins, pin_of
    from codetortoise.pipeline import run_design
    svc = make_services(fx, tmp_path)
    _strong(svc, _one_story_per_cl)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    d = ReadingDesign.model_validate(svc.store.get_blob(rid, "reading_design"))
    svc.store.put_blob(rid, BLOB, [pin_of(d, "concerns", {})])     # pinned under titles its stories no longer have
    run_design(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}["design"]
    assert st["status"] == "ok"
    assert st["message"].endswith("; the pinned concerns no longer fit the change and were unpinned")
    assert load_pins(svc.store, rid) == [] and svc.store.get_blob(rid, "reading_design")["sources"]["concerns"] == "llm"
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_pins.py tests/test_pipeline.py -k "pin"`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.design_pins'`.

- [ ] **Step 3: The pins**

Create `backend/codetortoise/design_pins.py`:

```python
"""Pinned design text (spec 2026-11-02 §10, the AI menu's "Pin this text"): the review's owner keeps the model's words
for one part of the design overview, and each later run of the design stage puts them back while they still fit.

Pins are kept in blob `design_pins`. A walk-through's or a condition's pin finds its part by what it is rather than by
its id, since ids follow the order the rules list them in; a function or field it cites is found again by its name, and
a story by its title. A pin that no longer fits is dropped, and the design stage says so."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from codetortoise.design import Concern, Gate, Ownership, ReadingDesign, Walk
from codetortoise.reading import Reading

BLOB = "design_pins"
_DROPPED = {"verdict": "the pinned verdict no longer fits the change and was unpinned",
            "concerns": "the pinned concerns no longer fit the change and were unpinned",
            "ownership": "the pinned ownership lines no longer fit the change and were unpinned",
            "walk": "a pinned walk-through title no longer fits the change and was unpinned",
            "gate": "a pinned condition name no longer fits the change and was unpinned"}


class Pin(BaseModel):
    part: str                          # verdict, concerns, ownership, walk or gate
    key: str = ""                      # a walk-through's or a condition's: what it is (walk_key, gate_key)
    verdict: str = ""
    verdict_causes: list[str] = Field(default_factory=list)
    concerns: list[Concern] = Field(default_factory=list)
    ownership: list[Ownership] = Field(default_factory=list)
    title: str = ""
    lead: str = ""
    false_case: str = ""
    nodes: dict[str, str] = Field(default_factory=dict)     # each function or field it cites: its name, by id
    stories: dict[str, str] = Field(default_factory=dict)   # each story it cites: its title, by id


def _label(d: ReadingDesign, nid: str) -> str:
    n = d.nodes.get(nid)
    return n.label if n is not None else nid


def gate_key(d: ReadingDesign, g: Gate) -> str:
    """What a condition is, whatever its id: its function's name and its test."""
    return f"{_label(d, g.node)}|{g.test}"


def walk_key(d: ReadingDesign, w: Walk) -> str:
    """What a walk-through is, whatever its id: its condition and side, and its steps by name."""
    g = next((g for g in d.gates if g.id == w.condition), None)
    head = f"{gate_key(d, g)}|{w.case}" if g is not None else "-"
    return head + "||" + "|".join(f"{s.kind}:{_label(d, s.src)}>{_label(d, s.dst)}:{s.label}" for s in w.steps)


def story_titles(ss) -> dict[str, str]:
    """The stories' titles by id, as a pin records and later checks them."""
    return {s.id: s.title for s in ss.stories} if ss is not None else {}


def pin_of(d: ReadingDesign, part: str, titles: dict[str, str]) -> Pin:
    """Part `part` of `d` as a pin: its words, and the names of what it cites. `titles`: the stories' titles by id."""
    kind, _, pid = part.partition(":")
    if kind == "verdict":
        return Pin(part=kind, verdict=d.verdict, verdict_causes=list(d.verdict_causes))
    if kind == "concerns":
        sids = {s for c in d.concerns for s in c.stories}
        return Pin(part=kind, concerns=[c.model_copy(deep=True) for c in d.concerns],
                   stories={s: titles.get(s, "") for s in sids})
    if kind == "ownership":
        cites = {c for o in d.ownership for c in o.cites}
        return Pin(part=kind, ownership=[o.model_copy(deep=True) for o in d.ownership],
                   nodes={c: d.nodes[c].label for c in cites if c in d.nodes},
                   stories={c: titles[c] for c in cites if c in titles})
    if kind == "walk":
        w = next(w for w in d.walks if w.id == pid)
        return Pin(part=kind, key=walk_key(d, w), title=w.title, lead=w.lead)
    g = next(g for g in d.gates if g.id == pid)
    return Pin(part=kind, key=gate_key(d, g), false_case=g.false_case)


@dataclass
class _Now:
    """What the review has now, as a pin's fit is judged."""
    causes: set[str]
    stories: set[str]
    titles: dict[str, str]
    files: set[str]
    named: dict[str, list[str]]       # node ids by name

    def cite(self, p: Pin, c: str) -> str | None:
        """Cite `c` of pin `p` as the design names it now; None when the review no longer has it."""
        if c in p.stories:
            return c if c in self.stories and self.titles.get(c) == p.stories[c] else None
        if c in p.nodes:
            ids = self.named.get(p.nodes[c], [])
            return ids[0] if len(ids) == 1 else None
        return c if c in self.files else None


def _put(d: ReadingDesign, p: Pin, now: _Now) -> bool:
    """Put pin `p` into `d` when it fits; whether it did."""
    if p.part == "verdict":
        if not set(p.verdict_causes) <= now.causes:
            return False
        d.verdict, d.verdict_causes, d.sources["verdict"] = p.verdict, list(p.verdict_causes), "pinned"
        return True
    if p.part == "concerns":
        if any(now.cite(p, s) is None for c in p.concerns for s in c.stories) or \
                any(x not in now.causes for c in p.concerns for x in c.causes):
            return False
        d.concerns, d.sources["concerns"] = [c.model_copy(deep=True) for c in p.concerns], "pinned"
        return True
    if p.part == "ownership":
        lines = [o.model_copy(update={"cites": [now.cite(p, c) for c in o.cites]}) for o in p.ownership]
        if any(c is None for o in lines for c in o.cites):
            return False
        d.ownership, d.sources["ownership"] = lines, "pinned"
        return True
    if p.part == "walk":
        w = next((w for w in d.walks if walk_key(d, w) == p.key), None)
        if w is None:
            return False
        w.title, w.lead, w.title_source, d.sources[f"walk:{w.id}"] = p.title, p.lead, "llm", "pinned"
        return True
    g = next((g for g in d.gates if gate_key(d, g) == p.key), None)
    if g is None:
        return False
    g.false_case, d.sources[f"gate:{g.id}"] = p.false_case, "pinned"
    return True


def apply_pins(d: ReadingDesign, r: Reading, titles: dict[str, str], pins: list[Pin]) -> tuple[list[Pin], list[str]]:
    """Put each pin that still fits into `d`, its part marked pinned in `d.sources`; returns the pins that fit and a
    note for each that no longer does. A pin fits while the review has every check it names, every story it cites under
    the title it had, every function or field it cites under its name (by whatever id it has now) and every file it
    cites, and, for a walk-through or a condition, one that is the same."""
    named: dict[str, list[str]] = {}
    for nid, n in d.nodes.items():
        named.setdefault(n.label, []).append(nid)
    now = _Now(causes={c.id for c in r.causes or []}, stories={s for t in r.threads for s in t.stories},
               titles=titles, files={f for c in d.components for f in c.files}, named=named)
    kept: list[Pin] = []
    notes: list[str] = []
    for p in pins:
        if _put(d, p, now):
            kept.append(p)
        else:
            notes.append(_DROPPED[p.part])
    return kept, notes


def load_pins(store, rid: int) -> list[Pin]:
    """Review `rid`'s pins; none when it has none."""
    return [Pin.model_validate(p) for p in store.get_blob(rid, BLOB) or []]
```

- [ ] **Step 4: The design stage puts them back**

In `backend/codetortoise/pipeline.py`, import them (after the `design_context` import):

```python
from codetortoise.design_pins import BLOB as PINS
from codetortoise.design_pins import apply_pins, load_pins, story_titles
```

and in `design_part` replace the lines from `store.replace_blobs(rid, ["reading_design"], [], {"reading_design": d})`
to the end of the function with:

```python
    kept, dropped = apply_pins(d, r, story_titles(ss), pins) if (pins := load_pins(store, rid)) else ([], [])
    store.replace_blobs(rid, ["reading_design"], [], {"reading_design": d} | ({PINS: kept} if dropped else {}))
    msg = f"{len(d.components)} component(s), {len(d.walks)} walk-through(s), {len(d.gates)} condition(s)" + told + intro
    if d.context_notes:
        msg += "; design context: " + "; ".join(d.context_notes)
    if dropped:                                  # said, not degraded: the design is whole, only a pin let go
        msg += "; " + "; ".join(dropped)
    return msg, notes
```

and add to its docstring, after "A design the rules can't build leaves none.": "The owner's pins (codetortoise.design_pins) go back on the model's words; one that no longer fits is dropped and said."

- [ ] **Step 5: Run them to see them pass, with the design stage's tests**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_pins.py tests/test_pipeline.py tests/test_llm_design.py -k "pin or design" && .venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff "All checks passed!".

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/design_pins.py backend/codetortoise/pipeline.py backend/tests/test_design_pins.py backend/tests/test_pipeline.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: a pinned part of the design overview outlives later runs of the design stage while it fits

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 3: The rewrite and pin routes

**Files:**
- Modify: `backend/codetortoise/llm/ondemand.py`
- Modify: `backend/codetortoise/web/app.py`
- Test: `backend/tests/test_design_ai.py` (new)

**Interfaces:**
- Consumes: Task 1's `has_part`, `rewrite_part`, `put_part`, `patch_kept`, `design_key`, `MAX_INSTRUCTION`, `prompt`;
  Task 2's `BLOB`, `pin_of`, `load_pins`, `story_titles`; `_lock`, `NotFound`, `Unchecked`, `Changed`, `CHANGED`,
  `UNCHECKED` (ondemand); `in_review`, `owner_in_review`, `bundle`, `TERMINAL`, `RERUNNING` (app.py).
- Produces:
  - `class Pinned(ValueError)`; `PINNED = "this part is pinned: its owner unpins it to rewrite it"`;
  - `check_part(svc, rid, part) -> None` (NotFound, Pinned);
  - `rewrite_design(svc, rid, user, part, instruction="") -> None` — an AI job of kind `"design"`, target the part;
  - `pin_design(svc, rid, part, on: bool) -> None`;
  - `POST /api/reviews/{rid}/design/{part}/rewrite` body `{instruction?: str ≤ 300}` → 202 the job;
  - `POST /api/reviews/{rid}/design/{part}/pin` body `{pinned: bool}` → `{pinned}` (owner only).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_design_ai.py`:

```python
"""The design overview's AI menu (spec 2026-11-02 §10, §11): rewrite one part, with an instruction, and pin it."""
import pytest
from helpers import make_app, make_services
from test_pipeline import _one_story_per_cl, _strong
from test_web import InlineRunner, login

from codetortoise.llm import ondemand

AGAIN = "The change holds together once more. Settle whether its callers handle the new results."
SHORT = "One new result goes unchecked. Settle whether its callers handle it."


def _answer(system, user):
    """The scripted strong model; a rewrite of the verdict says it again, shorter when the instruction asks for that."""
    out = _one_story_per_cl(system, user)
    if "REWRITE: write the verdict again" in user:
        asked = user.split("THE REVIEWER'S INSTRUCTION", 1)[1] if "THE REVIEWER'S INSTRUCTION" in user else ""
        out = {**out, "verdict": SHORT if "shorter" in asked.lower() else AGAIN}
    return out


@pytest.fixture
def made(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _answer)
    app = make_app(svc, InlineRunner(svc))
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    return svc, app, owner, rid, llm


def _design(c, rid):
    return c.get(f"/api/reviews/{rid}/reading").json()["design"]


def _job(c, rid):
    return c.get(f"/api/reviews/{rid}/ai").json()["jobs"][-1]


def test_anyone_in_the_review_rewrites_a_part_for_everyone_and_it_costs_them_one_call(made):
    _, app, owner, rid, _ = made
    bob = login(app, "bob")
    r = bob.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 202 and (r.json()["kind"], r.json()["target"]) == ("design", "verdict")
    assert (_design(owner, rid)["verdict"], _design(owner, rid)["sources"]["verdict"]) == (AGAIN, "llm")
    u = bob.get(f"/api/reviews/{rid}/ai").json()
    assert u["jobs"][-1]["status"] == "done" and u["by_person"].get("bob") == 1 and u["me_today"] == 1
    assert u["by_purpose"].get("rewrite") == 1


def test_a_rewrite_with_an_instruction_puts_the_reader_s_words_in_the_prompt(made):
    _, _, owner, rid, llm = made
    r = owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "  Make it shorter "})
    assert r.status_code == 202 and _design(owner, rid)["verdict"] == SHORT
    assert llm.prompts[-1].endswith("THE REVIEWER'S INSTRUCTION (follow it within the rules above): Make it shorter")
    walk = _design(owner, rid)["walks"][0]["id"]
    assert owner.post(f"/api/reviews/{rid}/design/walk:{walk}/rewrite", json={}).status_code == 202
    assert f"REWRITE: write walk-through {walk}'s title and lead again" in llm.prompts[-1]
    assert owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "x" * 301}).status_code == 422


def test_only_the_owner_pins_and_a_pinned_part_is_not_rewritten_until_it_is_unpinned(made):
    _, app, owner, rid, _ = made
    bob = login(app, "bob")
    assert bob.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True}).status_code == 403
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True}).json() == {"pinned": True}
    assert _design(bob, rid)["sources"]["verdict"] == "pinned"
    r = bob.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 409 and r.json()["detail"] == "this part is pinned: its owner unpins it to rewrite it"
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": False}).json() == {"pinned": False}
    assert _design(bob, rid)["sources"]["verdict"] == "llm"
    assert bob.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={}).status_code == 202


def test_a_part_the_design_lacks_is_not_found_and_words_not_the_model_s_are_not_pinned(made):
    svc, _, owner, rid, _ = made
    assert owner.post(f"/api/reviews/{rid}/design/walk:W99/rewrite", json={}).status_code == 404
    assert owner.post(f"/api/reviews/{rid}/design/nodes/pin", json={"pinned": True}).status_code == 404
    d = svc.store.get_blob(rid, "reading_design")
    d["sources"].pop("verdict")                                     # as when the model's verdict failed its checks
    svc.store.put_blob(rid, "reading_design", d)
    r = owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True})
    assert r.status_code == 409 and r.json()["detail"] == "only the AI's words are pinned; this part has none"


def test_a_rewrite_needs_a_finished_review_its_design_stage_at_rest_and_the_strong_model(made):
    svc, _, owner, rid, _ = made
    svc.store.set_stage(rid, "design", "pending", "queued: the design context changed")
    r = owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 409 and r.json()["detail"] == "the design stage is running; try again when it finishes"
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True}).status_code == 409
    svc.store.set_stage(rid, "design", "ok", "")
    svc.store.set_review_status(rid, "running")
    r = owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 409 and r.json()["detail"] == "the review is being re-run"
    svc.store.set_review_status(rid, "done")
    svc.strong = None
    r = owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 409 and r.json()["detail"] == "no strong model is configured"


def test_an_answer_that_fails_or_no_model_changes_nothing_and_says_why(made):
    _, _, owner, rid, llm = made
    before = _design(owner, rid)
    llm.answer = lambda s, u: {**_answer(s, u), "verdict": "Too short."} if "REWRITE:" in u else _answer(s, u)
    owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert (_job(owner, rid)["status"], _job(owner, rid)["error"]) == ("failed", ondemand.UNCHECKED)
    llm.answer = lambda s, u: RuntimeError("down")
    owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert _job(owner, rid)["error"] == ("the AI did not answer: big: RuntimeError: down; fresh try: RuntimeError: down; "
                                         "nothing was changed. Try again")
    assert _design(owner, rid) == before


def test_a_rewrite_for_a_design_that_changed_meanwhile_is_dropped(made, monkeypatch):
    svc, _, owner, rid, _ = made
    before = _design(owner, rid)
    real = ondemand.rewrite_part

    def meanwhile(*args, **kwargs):
        out = real(*args, **kwargs)
        r = svc.store.get_blob(rid, "reading")
        svc.store.put_blob(rid, "reading", {**r, "whole": "The change was read again."})   # its prompt changes
        return out
    monkeypatch.setattr(ondemand, "rewrite_part", meanwhile)
    assert owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={}).status_code == 202
    assert (_job(owner, rid)["status"], _job(owner, rid)["error"]) == ("failed", ondemand.CHANGED)
    assert _design(owner, rid)["verdict"] == before["verdict"]


def test_a_rewrite_outlives_a_re_run_of_the_same_change_and_a_pin_outlives_a_new_context(made):
    from codetortoise.pipeline import run_review
    svc, _, owner, rid, llm = made
    owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "shorter"})
    asked = sum("CHECKS BY CAUSE (id" in p for p in llm.prompts)
    run_review(rid, svc)                                            # the same prompt: the kept text, with the rewrite
    assert sum("CHECKS BY CAUSE (id" in p for p in llm.prompts) == asked
    assert _design(owner, rid)["verdict"] == SHORT
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True}).status_code == 200
    assert owner.put(f"/api/reviews/{rid}/design-context", json={"notes": "Never drop a byte."}).status_code == 202
    d = _design(owner, rid)                                         # the design stage ran again, on a new prompt
    assert sum("CHECKS BY CAUSE (id" in p for p in llm.prompts) == asked + 1
    assert (d["verdict"], d["sources"]["verdict"]) == (SHORT, "pinned") and d["context_hash"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_ai.py`
Expected: FAIL — the routes answer 404 (`{"detail":"Not Found"}`), and `ondemand` has no `UNCHECKED`-raising rewrite yet.

- [ ] **Step 3: The jobs**

In `backend/codetortoise/llm/ondemand.py`, add these imports (sorted into the existing block):

```python
from codetortoise.design import ReadingDesign
from codetortoise.design_context import context_text, load_context
from codetortoise.design_pins import BLOB as PINS
from codetortoise.design_pins import load_pins, pin_of, story_titles
from codetortoise.llm.design import design_key, has_part, patch_kept, put_part, rewrite_part
from codetortoise.llm.design import prompt as design_prompt
from codetortoise.llm.tiers import TiersFailed, tried_note
from codetortoise.reading import Reading
from codetortoise.stories import StorySet
```

after `UNCHECKED = …` add:

```python
PINNED = "this part is pinned: its owner unpins it to rewrite it"
```

after `class Changed`, add:

```python
class Pinned(ValueError):
    """The part is pinned: a rewrite would replace words its owner chose to keep."""
```

and at the end of the module:

```python
def _design_now(svc: Services, rid: int) -> tuple[ReadingDesign, Reading, StorySet, str]:
    """Review `rid`'s design overview as stored now, and what its prompt reads: the reading, the stories and the design
    context's text. Raises NotFound when the review has none."""
    raw, read = svc.store.get_blob(rid, "reading_design"), svc.store.get_blob(rid, "reading")
    ss = boardstore.stories(svc.store, rid)
    if not raw or not read or ss is None:
        raise NotFound("the review has no design overview")
    return ReadingDesign.model_validate(raw), Reading.model_validate(read), ss, context_text(load_context(svc.store, rid))


def check_part(svc: Services, rid: int, part: str) -> None:
    """Fail fast before queueing a rewrite: NotFound for a part the design lacks, Pinned for a pinned one."""
    d = _design_now(svc, rid)[0]
    if not has_part(d, part):
        raise NotFound(f"{part} is not a part of the design overview")
    if d.sources.get(part) == "pinned":
        raise Pinned(PINNED)


def rewrite_design(svc: Services, rid: int, user: str, part: str, instruction: str = "") -> None:
    """Write part `part` of review `rid`'s design overview again as `user` (spec 2026-11-02 §10's AI menu), with their
    instruction when given, and store it for everyone. Raises NotFound, Refused (over a limit), Unchecked, Changed or
    the LLM's error. The AI call runs without the review's lock; the result lands under it on the design as it is then,
    only while that design is still the one the AI saw and the part is not pinned meanwhile. A later run of the same
    prompt keeps it (blob `design_text`)."""
    if svc.strong is None or svc.cfg.llm.strong is None:
        raise RuntimeError("no strong model is configured")
    model = svc.cfg.llm.strong.model
    d, r, ss, context = _design_now(svc, rid)
    if not has_part(d, part):
        raise NotFound(f"{part} is not a part of the design overview")
    seen = design_key(model, design_prompt(d, r, ss, context))
    try:
        new, _ = rewrite_part(svc.strong, svc.ledger, rid, user, d, r, ss, part, instruction, context, weak=svc.llm)
    except TiersFailed as e:
        raise Unchecked(tried_note("the AI did not answer", e.failures, "nothing was changed. Try again")) from e
    if new is None:
        raise Unchecked(UNCHECKED)
    with _lock(rid):
        try:
            now, r, ss, context = _design_now(svc, rid)
        except NotFound:
            raise Changed(CHANGED) from None
        if design_key(model, design_prompt(now, r, ss, context)) != seen or not has_part(now, part):
            raise Changed(CHANGED)
        if now.sources.get(part) == "pinned":
            raise Changed("the part was pinned while the AI was answering; nothing was changed")
        put_part(now, new, part)
        puts: dict = {"reading_design": now}
        kept = svc.store.get_blob(rid, "design_text")
        if kept and kept.get("key") == seen:                 # a re-run of this prompt keeps the rewrite
            puts["design_text"] = patch_kept(kept, now, part)
        svc.store.replace_blobs(rid, [], [], puts)


def pin_design(svc: Services, rid: int, part: str, on: bool) -> None:
    """Pin part `part` of review `rid`'s design overview (`on`), or unpin it: a pin keeps the model's words through later
    runs of the design stage while they fit (codetortoise.design_pins). Raises NotFound for a part the design lacks and
    Unchecked for one whose words are not the model's."""
    with _lock(rid):
        raw = svc.store.get_blob(rid, "reading_design")
        if not raw:
            raise NotFound("the review has no design overview")
        d = ReadingDesign.model_validate(raw)
        if not has_part(d, part):
            raise NotFound(f"{part} is not a part of the design overview")
        if on and d.sources.get(part) not in ("llm", "pinned"):
            raise Unchecked("only the AI's words are pinned; this part has none")
        pin = pin_of(d, part, story_titles(boardstore.stories(svc.store, rid)))
        pins = [p for p in load_pins(svc.store, rid) if (p.part, p.key) != (pin.part, pin.key)] + ([pin] if on else [])
        if on:
            d.sources[part] = "pinned"
        elif d.sources.get(part) == "pinned":
            d.sources[part] = "llm"
        svc.store.replace_blobs(rid, [], [], {"reading_design": d, PINS: pins})
```

- [ ] **Step 4: The routes**

In `backend/codetortoise/web/app.py`:

1. Import `MAX_INSTRUCTION` (`from codetortoise.llm.design import MAX_INSTRUCTION`, sorted into the imports).
2. Beside `ExplainIn`, add:

```python
class RewriteIn(BaseModel):
    instruction: str = Field("", max_length=MAX_INSTRUCTION)


class PinIn(BaseModel):
    pinned: bool
```

3. After the `explain` route, add:

```python
    DESIGNING = "the design stage is running; try again when it finishes"

    def design_at_rest(svc, a: Access, rid: int) -> None:
        """A part of the design changes only on a finished review whose design stage is not running again (409)."""
        if a.review["status"] not in TERMINAL:
            raise HTTPException(409, RERUNNING)
        if any(s["name"] == "design" and s["status"] in ("pending", "running") for s in svc.store.list_stages(rid)):
            raise HTTPException(409, DESIGNING)

    @app.post("/api/reviews/{rid}/design/{part}/rewrite", status_code=202)
    def rewrite_design(rid: int, part: str, body: RewriteIn, a: Access = Depends(in_review)):
        """Write one part of the design overview again (spec 2026-11-02 §10's AI menu), as an AI job: anyone in the
        review, one call on the review's budget charged to them; a pinned part waits for its owner to unpin it."""
        svc = bundle(a.ws)
        if svc.strong is None or svc.cfg.llm.strong is None:
            raise HTTPException(409, "no strong model is configured")
        design_at_rest(svc, a, rid)
        try:
            ondemand.check_part(svc, rid, part)
        except ondemand.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except ondemand.Pinned as e:
            raise HTTPException(409, str(e)) from e
        if any(j["status"] == "running" and j["kind"] == "design" and j["target"] == part
               for j in reg.pool.jobs.get(rid, [])):
            raise HTTPException(409, "this part is being rewritten; wait for it to finish")
        reason = svc.ledger.check(rid, a.user)
        if reason:
            raise HTTPException(429, reason)
        words = body.instruction.strip()
        return a.ws.runner.submit_ai(rid, a.user, "design", part,
                                     lambda: ondemand.rewrite_design(svc, rid, a.user, part, words))

    @app.post("/api/reviews/{rid}/design/{part}/pin")
    def pin_design(rid: int, part: str, body: PinIn, a: Access = Depends(owner_in_review)):
        """Pin one part's words, or unpin them (§10): the owner's, as a pin decides what every later run keeps."""
        svc = bundle(a.ws)
        design_at_rest(svc, a, rid)
        try:
            ondemand.pin_design(svc, rid, part, body.pinned)
        except ondemand.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {"pinned": body.pinned}
```

- [ ] **Step 5: Run them to see them pass, with the AI and design tests**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_ai.py tests/test_ondemand.py tests/test_web.py -k "design or explain or ai or rewrite or pin" && .venv/bin/ruff check codetortoise tests`
Expected: all pass; ruff "All checks passed!".

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/llm/ondemand.py backend/codetortoise/web/app.py backend/tests/test_design_ai.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: anyone in a review rewrites a part of its design overview, and its owner pins one

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 4: Rewrite ▾ on each AI part

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/reading/design.ts`, test `frontend/src/reading/design.test.ts`
- Create: `frontend/src/workspace/RewriteMenu.tsx`
- Modify: `frontend/src/workspace/Overview.tsx`, `frontend/src/workspace/WalkPage.tsx`, `frontend/src/workspace/useReview.ts`, `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: Task 3's routes; `useAi` (`view.strong`, `view.jobs`, `refresh`, `setUsageOpen`), `jobFor`, `callTitle`,
  `useMenu`, `useViewer`, `useWs` (`data.reading.design`, `data.id`, `data.loadReading`), `byModel`, `sourceLine`.
- Produces:
  - `api.rewriteDesign(id, part, instruction = "") -> Promise<AiJob>`; `api.pinDesign(id, part, pinned) -> Promise<{ pinned: boolean }>`;
  - `partSource(d, part): string`; `rewriteItems(d, part, owner): { rewrite: boolean; why: string; pin: "pin" | "unpin" | null }`;
  - `RewriteMenu({ part, what })`, `SourceRow({ d, part, what })`; class `.dz-srcrow` holds `.dz-src` and the menu
    (`.dz-rewrite`).

- [ ] **Step 1: Write the failing tests**

In `frontend/src/reading/design.test.ts`, add `partSource` and `rewriteItems` to the import from `./design`, and
`ReadingDesign` to the type import from `./types`; then append:

```ts
describe("the AI menu (§10)", () => {
  const d = { context_hash: null, sources: { verdict: "pinned", concerns: "llm" } } as unknown as ReadingDesign;

  it("ends a pinned part's source line with pinned", () => {
    expect(partSource(d, "verdict")).toBe("AI, from the stories · pinned");
    expect(partSource({ ...d, context_hash: "0123456789ab" }, "concerns")).toBe("AI, from the stories and the design context");
  });

  it("offers a rewrite unless the part is pinned, and the pin to the review's owner alone", () => {
    expect(rewriteItems(d, "concerns", true)).toEqual({ rewrite: true, why: "", pin: "pin" });
    expect(rewriteItems(d, "verdict", true)).toEqual({ rewrite: false, why: "Pinned: unpin it to rewrite it", pin: "unpin" });
    expect(rewriteItems(d, "verdict", false)).toEqual({ rewrite: false, why: "Pinned by the review's owner", pin: null });
    expect(rewriteItems(d, "concerns", false)).toEqual({ rewrite: true, why: "", pin: null });
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/reading/design.test.ts`
Expected: FAIL — `partSource is not a function` (and `rewriteItems`).

- [ ] **Step 3: The helpers and the calls**

Append to `frontend/src/reading/design.ts`:

```ts
/** A part's source line (§3.1 item 2): where the AI's words come from, and "pinned" when the review's owner pinned
 * them (§10), so a re-run left them as they were. */
export const partSource = (d: Pick<ReadingDesign, "context_hash" | "sources">, part: string): string =>
  sourceLine(d) + (d.sources[part] === "pinned" ? " · pinned" : "");

/** The AI menu's items for one part (§10, §12.3): Rewrite and Rewrite with an instruction… unless the part is pinned,
 * when `why` says so; Pin this text, or Unpin, for the review's owner alone. */
export function rewriteItems(d: Pick<ReadingDesign, "sources">, part: string, owner: boolean):
    { rewrite: boolean; why: string; pin: "pin" | "unpin" | null } {
  const pinned = d.sources[part] === "pinned";
  return { rewrite: !pinned, why: pinned ? (owner ? "Pinned: unpin it to rewrite it" : "Pinned by the review's owner") : "",
           pin: owner ? (pinned ? "unpin" : "pin") : null };
}
```

In `frontend/src/api.ts`, after the `explain:` entry, add:

```ts
  /** The design overview's AI menu (spec 2026-11-02 §10, §11): write one part again as an AI job — `verdict`, `concerns`,
   * `ownership`, `walk:W1`, `gate:G1` — with the reader's instruction when given. */
  rewriteDesign: (id: number, part: string, instruction = "") =>
    call<AiJob>("POST", `/api/reviews/${id}/design/${encodeURIComponent(part)}/rewrite`, { instruction }),
  /** Pin or unpin one part's words (the review's owner): a pinned part is kept by later runs of the design stage. */
  pinDesign: (id: number, part: string, pinned: boolean) =>
    call<{ pinned: boolean }>("POST", `/api/reviews/${id}/design/${encodeURIComponent(part)}/pin`, { pinned }),
```

- [ ] **Step 4: Run them to see them pass**

Run: `cd frontend && npx vitest run src/reading/design.test.ts`
Expected: PASS.

- [ ] **Step 5: The menu**

Create `frontend/src/workspace/RewriteMenu.tsx`:

```tsx
import { useState } from "react";
import { api, ApiError, errorText } from "../api";
import { useAi } from "../lib/ai";
import { callTitle, jobFor } from "../lib/aiState";
import { useMenu } from "../lib/useMenu";
import { partSource, rewriteItems } from "../reading/design";
import type { ReadingDesign } from "../reading/types";
import { useViewer } from "../viewer";
import { useWs } from "./context";

const REFUSED = /AI calls|AI budget/;
const MAX_INSTRUCTION = 300;                     // as the server takes it

/** Rewrite ▾ (spec 2026-11-02 §10, §12.3): the AI menu of one part of the design overview, in Explain ▾'s shape.
 * Rewrite asks the strong model for the part again, after a confirmation; Rewrite with an instruction… opens a box whose
 * words go into the prompt (Ask sends them, Ctrl+Enter too; Escape shuts it). The review's owner pins the words, so later
 * runs of the design stage keep them, or unpins them. A rewrite is one AI call, shown to everyone once it lands; a pinned
 * part is not rewritten. A refusal or a failure shows beside the menu. */
export default function RewriteMenu({ part, what }: { part: string; what: string }) {
  const ai = useAi(), ws = useWs(), me = useViewer();
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const [words, setWords] = useState("");
  const [error, setError] = useState<{ text: string; refused: boolean } | null>(null);
  const { button, menu } = useMenu<HTMLSpanElement>(open, () => setOpen(false));
  const d = ws.data.reading?.design;
  if (!ai?.view?.strong || !d) return null;
  const view = ai.view, items = rewriteItems(d, part, !!me?.is_owner);
  const job = jobFor(view, "design", part), running = job?.status === "running";
  const failed = error ?? (job && (job.status === "failed" || job.status === "refused")
    ? { text: job.error ?? "the AI call failed", refused: job.status === "refused" || REFUSED.test(job.error ?? "") } : null);
  const shut = () => { setAsking(false); button.current?.focus(); };
  const rewrite = (instruction: string) => {
    setError(null);
    api.rewriteDesign(ws.data.id, part, instruction)
      .then(() => { if (instruction) { setWords(""); shut(); } })
      .catch((e) => setError({ text: errorText(e, "The rewrite could not be started."),
                               refused: e instanceof ApiError && e.status === 429 }))
      .finally(() => ai.refresh());
  };
  const pin = (on: boolean) => {
    setOpen(false);
    setError(null);
    api.pinDesign(ws.data.id, part, on).then(() => ws.data.loadReading())
      .catch((e) => setError({ text: errorText(e, on ? "The words could not be pinned." : "The words could not be unpinned."),
                               refused: false }));
  };
  // title="": nothing here is the AI's text; an empty title keeps the hover of whatever surrounds these controls off them
  return (
    <span className="ai-ask dz-rewrite" title="" onClick={(e) => e.stopPropagation()}>
      <span className="ai-menuwrap">
        <button ref={button} className="ai-btn" aria-haspopup="menu" aria-expanded={open}
                title={`Ask the AI to write the ${what} again`} onClick={() => setOpen(!open)}>
          {running ? "Rewriting…" : "Rewrite"}<span aria-hidden> ▾</span></button>
        {open && (
          <span className="ai-menu" role="menu" aria-label="Rewrite" ref={menu}>
            <button role="menuitem" disabled={running || !items.rewrite} title={items.why || callTitle(view)}
                    onClick={() => {
                      setOpen(false);
                      button.current?.focus();
                      if (window.confirm(`Replace the ${what}? It costs 1 AI call.`)) rewrite("");
                    }}>Rewrite</button>
            <button role="menuitem" disabled={running || !items.rewrite} title={items.why || callTitle(view)}
                    onClick={() => { setOpen(false); setAsking(true); }}>Rewrite with an instruction…</button>
            {items.pin && (
              <button role="menuitem" disabled={running} onClick={() => pin(items.pin === "pin")}>
                {items.pin === "pin" ? "Pin this text" : "Unpin"}</button>
            )}
          </span>
        )}
      </span>
      {asking && (
        <span className="ai-askq">
          <textarea aria-label="How should the AI rewrite it?" rows={2} value={words} autoFocus maxLength={MAX_INSTRUCTION}
                    placeholder="Shorter, or say what it leaves out…" onChange={(e) => setWords(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && words.trim() && !running) rewrite(words.trim());
                      else if (e.key === "Escape") { e.preventDefault(); shut(); }
                    }} />
          <button className="ai-btn" disabled={!words.trim() || running} title={callTitle(view)}
                  onClick={() => rewrite(words.trim())}>Ask</button>
        </span>
      )}
      {failed && !running && (
        <span className="ai-err" role="alert">
          {failed.text}
          {failed.refused && view.is_owner && <button className="link small" onClick={() => ai.setUsageOpen(true)}>Raise budget</button>}
        </span>
      )}
    </span>
  );
}

/** A part's source line and its AI menu (§3.1 item 2, §12.3), on one row: the menu at the row's end. */
export function SourceRow({ d, part, what }: { d: ReadingDesign; part: string; what: string }) {
  return (
    <div className="dz-srcrow">
      <p className="dz-src">{partSource(d, part)}</p>
      <RewriteMenu part={part} what={what} />
    </div>
  );
}
```

- [ ] **Step 6: The menu on each AI part, and the reading after a rewrite**

In `frontend/src/workspace/Overview.tsx`:

1. Import `{ SourceRow }` from `./RewriteMenu` and drop `sourceLine` from the `../reading/design` import if nothing
   else in the file uses it.
2. In `Verdict`, replace `<p className="dz-src">{sourceLine(d)}</p>` with
   `<SourceRow d={d} part="verdict" what="verdict" />`.
3. In `Concerns`, replace `<p className="dz-src">{sourceLine(d)}</p>` with
   `<SourceRow d={d} part="concerns" what="concerns" />`.
4. The two folds become:

```tsx
      {design && design.ownership.length > 0 && (
        <Fold name="Is the design right?" title={ownershipTitle(design.ownership)}>
          {byModel(design, "ownership") && <SourceRow d={design} part="ownership" what="ownership lines" />}
          <OwnershipLines d={design} />
        </Fold>
      )}
      {gate && <Fold name="When the condition is false" title={conditionTitle(gate)} ai={byModel(design, `gate:${gate.id}`)}>
        {byModel(design, `gate:${gate.id}`) && <SourceRow d={design!} part={`gate:${gate.id}`} what="condition's name" />}
        <ConditionLines g={gate} /></Fold>}
```

In `frontend/src/workspace/WalkPage.tsx`, import `{ SourceRow }` from `./RewriteMenu` and, in `.st-summary`, after the
lead:

```tsx
          {byModel(design, `walk:${w.id}`) && <SourceRow d={design} part={`walk:${w.id}`} what="title and lead" />}
```

(import `byModel` from `../reading/design` if the file does not yet).

In `frontend/src/workspace/useReview.ts`, `onAiDone` gains a line and a dependency:

```ts
  const onAiDone = useCallback((jobs: AiJob[]) => {      // an explanation finished: show it
    if (jobs.some((j) => j.kind === "flow" || j.kind === "story")) {
      setReload((k) => k + 1);
      loadStories();
      loadNames();
      if (overview === null) loadBoard();
    }
    if (jobs.some((j) => j.kind === "finding")) { loadFindings(); loadNames(); }
    if (jobs.some((j) => j.kind === "design")) loadReading();         // a part of the design overview was rewritten
  }, [loadStories, loadNames, loadBoard, loadFindings, loadReading, overview]);
```

(`loadReading` must be defined above `onAiDone`; move `onAiDone` below it if it is not.)

In `frontend/src/workspace/workspace.css`, after the `.dz-src` rule:

```css
/* a part's source line and its Rewrite ▾ (spec 2026-11-02 §12.3): the menu sits at the row's end and opens leftward,
   so it stays on a phone's screen */
.dz-srcrow { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; margin: 4px 0 0; }
.dz-srcrow > .dz-src { margin: 0; }
.dz-rewrite { margin-left: auto; }
.dz-rewrite .ai-menu { left: auto; right: 0; }
```

- [ ] **Step 7: Type-check, build, and the unit tests**

Run: `cd frontend && npx tsc --noEmit && npm run build > /dev/null && npx vitest run 2>&1 | tail -4`
Expected: no type errors; the build succeeds; every vitest file passes.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.ts frontend/src/reading/design.ts frontend/src/reading/design.test.ts frontend/src/workspace/RewriteMenu.tsx frontend/src/workspace/Overview.tsx frontend/src/workspace/WalkPage.tsx frontend/src/workspace/useReview.ts frontend/src/workspace/workspace.css
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: Rewrite ▾ on each part of the design overview the AI wrote: rewrite, with an instruction, or pin

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 5: The fake model rewrites, the e2e tests, the README

**Files:**
- Modify: `frontend/e2e/fake_llm.py`
- Create: `frontend/e2e/design-rewrite.spec.ts`
- Modify: `README.md`

**Interfaces:**
- Consumes: Tasks 1–4; e2e helpers `login`, `reviewMenu`, `sideways`, `startReview`, `STRONG`, `test`.
- Produces: the e2e proof of §10's menu; the README's account of it.

- [ ] **Step 1: The fake model rewrites**

In `frontend/e2e/fake_llm.py`, after `design()`, add:

```python
SHORT_VERDICT = "One new result goes unchecked. Settle whether `logger_flush` must handle the new -2."


def rewrite(user: str) -> dict:
    """A rewrite of one part (spec 2026-11-02 §10's AI menu): the verdict again, shorter when the reader's instruction
    asks for that; a walk-through's title and lead again. The rest is the design's answer, which a rewrite leaves unread."""
    out = design(user)
    asked = user.split("THE REVIEWER'S INSTRUCTION", 1)[1].lower() if "THE REVIEWER'S INSTRUCTION" in user else ""
    if "REWRITE: write the verdict again" in user:
        out["verdict"] = SHORT_VERDICT if "shorter" in asked else (
            "The change holds together once more, but one new result goes unchecked. "
            "Settle whether `logger_flush` must handle the new -2.")
    walk = re.search(r"REWRITE: write walk-through (W\d+)'s title", user)
    if walk:
        out["walks"] = [{"id": walk.group(1), "title": "A long write, told again",
                         "lead": "It follows a long write to where `uart_send` refuses it."}]
    return out
```

and in `answer()`, before the `"CHECKS BY CAUSE (id"` test:

```python
    if "REWRITE: write " in user:
        return rewrite(user)
```

- [ ] **Step 2: Write the e2e tests**

Create `frontend/e2e/design-rewrite.spec.ts`:

```ts
import { devices, expect, type Locator, type Page } from "@playwright/test";
import { login, reviewMenu, sideways, startReview, STRONG, test } from "./helpers";

// e2e/serve-strong.sh's fake strong model (e2e/fake_llm.py) writes the verdict again, shorter when the instruction asks,
// and a walk-through's title as "A long write, told again".
const SHORT = "One new result goes unchecked. Settle whether logger_flush must handle the new -2.";

const verdictRow = (page: Page) => page.locator(".ov-top .dz-verdict");

/** Opens the Rewrite ▾ menu inside `at` (the verdict's row by default) and returns it. */
async function rewriteMenu(page: Page, at: Locator = verdictRow(page)) {
  await at.getByRole("button", { name: "Rewrite", exact: true }).click();
  const menu = at.getByRole("menu", { name: "Rewrite" });
  await expect(menu).toBeVisible();
  return menu;
}

async function shorter(page: Page) {
  const v = verdictRow(page);
  await (await rewriteMenu(page)).getByRole("menuitem", { name: "Rewrite with an instruction…" }).click();
  const box = v.getByLabel("How should the AI rewrite it?");
  await expect(box).toBeFocused();
  await box.fill("Make it shorter");
  await v.getByRole("button", { name: "Ask" }).click();
  await expect(v.locator("p.ai-text")).toHaveText(SHORT, { timeout: 30_000 });
  await expect(box).toHaveCount(0);
}

test.describe("the design overview's AI menu", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("anyone in the review rewrites the verdict, after a confirmation, and the new words show", async ({ page }) => {
    await startReview(page);
    const v = verdictRow(page);
    await expect(v.locator("p.ai-text")).toContainText("The change holds together, but one new result goes unchecked.");
    page.once("dialog", (d) => d.accept());
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Rewrite", exact: true }).click();
    await expect(v.locator("p.ai-text")).toContainText("The change holds together once more", { timeout: 30_000 });
    await expect(v.locator(".dz-src")).toHaveText("AI, from the stories");
  });

  test("a rewrite with an instruction puts the reader's words to the model", async ({ page }) => {
    await startReview(page);
    await shorter(page);
  });

  test("the owner pins the verdict; a design re-run keeps it, and a pinned part is not rewritten", async ({ page }) => {
    await startReview(page);
    const v = verdictRow(page);
    await shorter(page);
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Pin this text" }).click();
    await expect(v.locator(".dz-src")).toHaveText("AI, from the stories · pinned");
    // a design context runs the design stage again; its fresh verdict would say it read the context
    await (await reviewMenu(page)).getByRole("menuitem", { name: "Design context…" }).click();
    const panel = page.getByRole("dialog", { name: "Design context" });
    await panel.getByLabel("Notes").fill("The UART must never drop a byte.");
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(v.locator(".dz-src")).toHaveText("AI, from the stories and the design context · pinned", { timeout: 30_000 });
    await expect(v.locator("p.ai-text")).toHaveText(SHORT);
    await page.keyboard.press("Escape");
    const menu = await rewriteMenu(page);
    await expect(menu.getByRole("menuitem", { name: "Rewrite", exact: true })).toBeDisabled();
    await expect(menu.getByRole("menuitem", { name: "Unpin" })).toBeVisible();
  });

  test("someone else in the review may rewrite but has no pin", async ({ page, browser }) => {
    const base = await startReview(page);
    const context = await browser.newContext({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });
    const other = await context.newPage();
    await login(other, "bob");
    await other.goto(base);
    await expect((await rewriteMenu(other)).getByRole("menuitem")).toHaveText(["Rewrite", "Rewrite with an instruction…"]);
    await context.close();
  });

  test("a walk-through's title and lead are rewritten on its page", async ({ page }) => {
    await startReview(page);
    await page.locator(".dz-walks a").first().click();
    const head = page.locator(".dz-walk .st-head");
    await expect(head.locator(".dz-src")).toHaveText("AI, from the stories");
    page.once("dialog", (d) => d.accept());
    await (await rewriteMenu(page, head)).getByRole("menuitem", { name: "Rewrite", exact: true }).click();
    await expect(head.getByRole("heading", { level: 2 })).toContainText("A long write, told again", { timeout: 30_000 });
  });
});

test.describe("the AI menu on a phone", () => {
  test.use({ baseURL: STRONG, viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
             deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the open menu stays on the phone's screen and nothing scrolls sideways", async ({ page }) => {
    await startReview(page);
    const box = await (await rewriteMenu(page)).boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(devices["iPhone 13"].viewport.width);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});
```

- [ ] **Step 3: Build, then run them**

Run: `cd frontend && npm run build > /dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/design-rewrite.spec.ts e2e/design-context.spec.ts e2e/design-text.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: all pass. (If one fails, read the trace: a failing e2e is a finding — debug it, never loosen it.)

- [ ] **Step 4: Say it in the README**

In `README.md`, after the design-context paragraph (it begins "A review's owner can give it a **design context**"),
add:

```markdown
Each part of the opening the strong model wrote — the verdict, what the design must get right, the ownership lines, a
walk-through's title and lead, a condition's name — carries a **Rewrite ▾** menu. *Rewrite* asks the strong model for
that part alone again; *Rewrite with an instruction…* adds your words (at most 300 characters) to its prompt. Either is
one AI call on the review's budget, charged to whoever asked, and everyone sees the new words; an answer that fails the
part's checks changes nothing. The review's owner can *Pin this text*: later runs of the design stage keep the pinned
words while the review still has what they cite, and a pinned part is not rewritten until it is unpinned.
```

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/fake_llm.py frontend/e2e/design-rewrite.spec.ts README.md
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "test: the design overview's AI menu end to end; the README tells of it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 6: Every suite

**Files:** none (a failure found here is fixed under a failing test in the file it concerns).

**Interfaces:**
- Consumes: everything above.
- Produces: every suite green on the branch's head.

- [ ] **Step 1: Run every suite**

Run:

```bash
cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider > ../.superpowers/pytest.log 2>&1; tail -3 ../.superpowers/pytest.log; .venv/bin/ruff check codetortoise tests
cd ../frontend && npx tsc --noEmit && npm run build > /dev/null && npx vitest run 2>&1 | tail -4
mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test --retries=0 > ../.superpowers/e2e.log 2>&1; tail -5 ../.superpowers/e2e.log; rm -rf ../.pwtmp
```

Expected: pytest all pass; ruff "All checks passed!"; no type errors; the build clean; vitest all pass; Playwright all
pass. A failure here is a finding about this branch: debug it (superpowers:systematic-debugging), fix it under a
failing test, and ledger the ruling.
