# Two-Tier Stories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each story has one purpose and one build target, and says why its parts are together. An optional strong model forms the stories from pieces prepared by rules, and code checks every placement. The same model then reviews each story's findings against facts code prepared, giving hazard, needs review or no hazard with citations. The weak model answers readers' questions starting from that work. Without the strong model, better rules form the stories.

**Architecture:** New pipeline stages run after the detectors: `pieces → stories → review`, then today's `verdicts → board → llm`. **pieces** (rules) gives every changed file its targets (`targets.py`) and cuts the change into pieces that never span targets or CLs, with typed links, an evidence card each and a change overview (`pieces.py`). **stories** gets a plan from the strong model (`llm/stories.py`: tools, per-placement checks, chunks with a merge pass, agreement mode, a cache), or from the rules (`grouping.rules_plan`). `stories.build_stories` turns the plan into the review's stories. **review** (`llm/review.py`) asks one question set per story about each finding, using facts from `facts_prep.py`. The validated output is the review's **brief** (`brief.py`, table `briefs`). Tier-2 prompts start with the relevant part of it (`llm/brief_context.py`). The frontend shows targets, why the pieces belong together, what to check, open questions, related stories, the Unsorted story and the AI review on findings.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, SQLite, libclang, httpx, pytest, ruff; React 19, TypeScript (strict), react-router 7, Vite, vitest, Playwright. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-05-two-tier-stories-design.md`

**Base:** `main` (the spec is its latest commit).

**Provenance:** every code block below was run before this plan was written. The tasks were then replayed in order on a fresh tree from `main` by a script that applied each step's blocks and ran each step's command. Every Expected line is that run's output. Each task's tests failed before its implementation and passed after it, and the suite stayed green after every task. A second script built a tree from this document's blocks alone. That tree is byte-identical to the validated one. New files are given in full. Changes to existing files are unified diffs against the previous task's state; apply them with `git apply` or by hand. Under parallel load an end-to-end test may time out or lose its browser on its first run. If one does, rerun it alone with `--last-failed`; if it fails again, it is a real failure.

## Global Constraints

- **Config (§9):** `llm.strong` is optional (absent: the rules form the stories): `base_url`, `model`, `key_env: TORTOISE_STRONG_KEY`, `context_tokens: 64000`, `temperature: 0` (`null` for endpoints that reject it), `rounds: 20`, `agree: 1` (or 2), `timeout_s: 300`. `llm.budget.tier1_per_review: 40`. `targets:` is a list of `{match: <glob on the workspace-relative path>, name: <str>}`, first match wins.
- **Ledger (§9):** tier-1 calls have purposes `stories`, `stories_merge` and `review`, and count only against `tier1_per_review`, never against the tier-2 budgets. Past it, the remaining chunks use the rules and the remaining stories' findings go to the tier-2 `verdicts` stage.
- **Sizes:** a card at most 300 tokens (`CARD_CHARS = 1200`); the overview at most 1500 tokens (`OVERVIEW_CHARS = 6000`), each CL description in it at most 600 (`CL_CHARS = 2400`); a piece at most 2 hops wide (`MAX_HOPS = 2`); a chunk's prompt within 60% of `context_tokens` (`CHUNK_SHARE = 0.6`); prepared facts at most 600 tokens a finding (`FACT_CHARS = 2400`); the brief's part in a tier-2 prompt at most 800 tokens (`BRIEF_CHARS = 3200`); a quote at least 8 characters (`QUOTE_MIN = 8`).
- **Stability (§4.6):** `STORY_RULES_VERSION = 1` in `llm/stories.py`, bumped with every change to the rules or the prompts' wording; the cache key is the SHA-256 of (cards, links, overview, rules version, model, agree).
- **Placement reasons (§4.3):** `starts_purpose`, `same_feature`, `caller_of_new_code`, `same_fix`, `same_refactor`, `shared_code`, `declaration_used`, `split_too_big`; the rules give `linked`, `tests`, `repeated`, `declaration_used`, `starts_purpose`.
- **Verdicts (§5.3):** `hazard` → high, `needs_review` → medium, `no_hazard` → info; findings are renumbered by severity; a verdict citing nothing it was shown is discarded.
- **Targets on screen (§3.1):** a review with one target shows no target chips anywhere.
- **Messages:** the stories stage says "N stories from M piece(s), by the rules (no strong model configured)" or "N stories formed by <model>[ (reused: this change was seen before)], K piece(s) placed, U unsorted" (Degraded with each chunk's fallback reason). The review stage says "N finding(s) judged by <model>: H hazard(s), R to confirm, K no hazard" or "no strong model: N finding(s) left to the detectors and the AI's side-effect pass". The verdicts stage says "all N side effect(s) judged by the strong model". The Unsorted story is titled "Unsorted: needs a person to place these". Health shows "code from reviewed changes is sent to <host>", or "not configured (stories by rules)".
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).
- **End-to-end runs:** build the frontend first (`npm run build` writes `backend/codetortoise/web/static`). Playwright starts the fixture servers itself: 8799; 8798 with the fake model on 8797; 8796 for the large fixture; and, from Task 10, 8795 with the fake model as the strong model too. If Chromium crashes ("Target crashed"), the browser's temp directory is full: point `TMPDIR` at a directory on disk.

## Review Focus

These are the conditions the spec implies that are most likely to bite a real user, most likely first. Each is pinned by a test in the task that owns the code.

1. **The strong model's endpoint fails mid-review** (down, garbage, a timeout). The review must still finish, on the rules' stories, with every finding as the detectors left it, and the stages must say why. Pinned by `test_a_strong_model_that_fails_leaves_the_rules_stories_and_says_so` (Task 6) and `test_a_strong_model_that_fails_leaves_every_finding_as_the_detectors_left_it` (Task 7).
2. **A brief that tier 1 only half formed** (a chunk fell back to the rules, or the budget ran out) must never be reused for the same change; the next run asks the model again. Pinned by `test_only_a_brief_tier_1_formed_entirely_is_reused` (Task 6).
3. **A re-run that numbers the findings differently** (a new finding pushes the others down) must keep each tier-1 verdict on its own finding. Pinned by `test_verdicts_follow_their_finding_when_a_re_run_numbers_the_findings_differently` (Task 7).
4. **Reviews stored before this design** have stories without targets, pieces or a plan, findings without a verdict source, and no brief. They must open as before: no chips, no new sections, tier-2 prompts unchanged. Pinned by `test_a_review_without_a_brief_or_stories_adds_nothing` (Task 8) and the vitest case "reads stories stored before two-tier stories" (Task 10).
5. **A weak model with a small context** gets the brief at the top of every prompt. A long change overview must not crowd out the question: the brief's part stays within 800 tokens. Pinned by `test_tortoise_gets_the_overview_and_its_anchor_s_story_within_800_tokens` (Task 8).

## Spec Coverage

| Spec | Where |
|---|---|
| §3.1 targets | Task 1 |
| §3.2 pieces, §3.3 links, §3.4 cards, §3.5 overview | Task 2 |
| §4.1 input and tools, §4.2 rules, §4.3 output, §4.4 checks, §4.5 chunks and merge pass | Task 6 |
| §4.6 stability: fixed input (Task 2), temperature (Task 5), cache and agreement (Task 6), Re-run stories (fresh) (Tasks 9, 10), `stories-check` (Task 9) | Tasks 2, 5, 6, 9, 10 |
| §5.1 prepared facts | Task 4 |
| §5.2 the pass, §5.3 effect | Task 7 |
| §6 the rules' stories | Task 3 |
| §7.1 models: `Piece`, `PieceLink` (Task 2), `Story` fields and `unsorted` (Task 3), `Finding` fields (Task 7) | Tasks 2, 3, 7 |
| §7.2 the brief | Task 6 (stories), Task 7 (verdicts, facts) |
| §8 tier 2 with the brief | Task 8 |
| §9 config, budget, health | Task 5; the AI view's tier-1 line, Task 9 |
| §10 UI | Task 10 |
| §11 testing: unit and pipeline (each task), fake_llm (Task 10), e2e (Tasks 3, 10), lab (Task 11) | all |
| §12 out of scope | nothing built |

## Decisions the spec left open (or that differ from it)

- **The review and verdicts stages run before the board** (`… detectors → pieces → stories → review → verdicts → board → llm`). The spec's §2 first drew them after it. The board must take the verdicts' severities, as the verdicts stage does today, so flows and stories are coloured by them. §2 was corrected in the commit that added this plan.
- **Titles are at most 8 words**, the house headline rule that `_titled` checks, not 10 (§4.2): a 10-word title would always fail the check. `RULES` says 8.
- **Repeated edits are cut before tests** (§3.2 lists tests first), so a substitution through test and product code stays one piece. Test code that causes a flow stays out of the tests piece: it is behaviour.
- **Declaration pieces are one per header and CL** (§3.2 says one per header), so pieces never span CLs.
- **Prepared facts are computed in the review stage** (as §2 now says) and stored in the brief. Lines in files outside the change are read from the workspace, so call sites in unchanged callers are quoted too.
- **The review covers every story in the plan**, including rules-fallback stories and Unsorted. A finding on two stories is reviewed with the first. A story without findings costs no call. Findings that are none of signature, return value, field or header get the behaviour question. No new findings are created.
- **A brief is reused only when complete** (no chunk fell back). A reused brief whose story reviews stopped early (budget) has the missing ones run.
- **`stories-check` records nothing**: its calls go to the strong model directly, not through the ledger, so the review's budget and usage are untouched (§4.6: "changes nothing stored").
- **On a tier-1 story, ✦ Explain is hidden and refused (404)**; Ask… stays, because tier 2 never retells tier-1 stories (§8).
- **@tortoise on a finding** gets the finding's verdict and prepared facts besides its story and the overview (§8 names only the story and the overview); the facts are what a weak model most needs.
- **The rules' "Why these belong together"** shows only on stories with more than one piece; a tier-1 or Unsorted story always shows it.
- **The Health notice's e2e test serves a mocked `/api/health`**: no test fixture has an off-site endpoint. The detail text comes from the real check, which `test_pipeline.py` covers (Task 5).
- **The fake strong model** (e2e) puts the shared header into the hal story without `shared_code`, so its check fails and the Unsorted story appears.
- **Two existing e2e expectations change** (Task 3): fixture story S1 is now drawn from CLs 101 and 102, because CL 102's `uart.h` declaration piece joins the story that uses it most (§6).

---

### Task 1: Every changed file's build target

Spec §3.1. `targets.resolve_targets` gives each changed file its sorted target names, first rule that applies:
- a configured `targets:` glob on the workspace-relative path;
- when the workspace has several compile databases, the databases holding the file's commands, each named by its directory under `build_root` (`build-modem/compile_commands.json` → `build-modem`);
- the toolchain group's triple;
- the one database's name.

A file with no command (a header) takes the union of the targets of the files that include it (the index's include graph). With none, it takes `unknown`. `CompileDb.databases_of(file)` lists the databases holding a file's commands, in precedence order.

**Files:**
- Test: `backend/tests/test_targets.py`
- Modify: `backend/codetortoise/config.py`
- Create: `backend/codetortoise/targets.py`
- Modify: `backend/codetortoise/toolchain/compile_db.py`

**Interfaces:**
- Consumes: `CompileDb` (its `databases` and the new `databases_of`), `SymbolIndex.transitive_includers`, the toolchain's `group_of(file).target`.
- Produces: `config.TargetRule(match: str, name: str)`, `Config.targets: list[TargetRule]`;
  `targets.UNKNOWN = "unknown"`; `targets.db_name(db: str, base: str) -> str`;
  `targets.resolve_targets(files, rules, root, cdb, build_root, triple_of, includers) -> dict[str, list[str]]`
  (canonical local path → sorted target names); `CompileDb.databases_of(file: str) -> list[str]`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_targets.py` (new file):

```python
"""Build targets of changed files (spec 2026-10-05-two-tier-stories §3.1)."""
from codetortoise.config import Config, TargetRule
from codetortoise.targets import UNKNOWN, resolve_targets
from codetortoise.toolchain.compile_db import CompileDb, CompileEntry

R = "/w"


def _db(*entries):
    """entries: (file relative to R, database path)."""
    return CompileDb([CompileEntry(file=f"{R}/{f}", directory=R, args=("cc", "-c", f), compiler="cc", db=db)
                      for f, db in entries])


def _resolve(files, cdb, rules=(), triple=None, includers=None, build_root=f"{R}/out"):
    return resolve_targets([f"{R}/{f}" for f in files], list(rules), R, cdb, build_root,
                           triple or (lambda f: None), includers or (lambda h: set()))


def test_a_configured_name_wins_and_the_first_matching_rule_applies():
    cdb = _db(("modem/rf/a.c", f"{R}/out/build-modem/compile_commands.json"))
    got = _resolve(["modem/rf/a.c", "app/main.c"], cdb,
                   [TargetRule(match="modem/**", name="modem"), TargetRule(match="modem/rf/*", name="rf"),
                    TargetRule(match="app/*", name="app")])
    assert got == {f"{R}/modem/rf/a.c": ["modem"], f"{R}/app/main.c": ["app"]}


def test_several_databases_name_targets_by_their_directory_under_the_build_root():
    m, d = f"{R}/out/build-modem/compile_commands.json", f"{R}/out/build-dsp/compile_commands.json"
    cdb = _db(("modem/a.c", m), ("dsp/b.c", d), ("common/util.c", m), ("common/util.c", d))
    got = _resolve(["modem/a.c", "dsp/b.c", "common/util.c"], cdb, triple=lambda f: "arm-none-eabi")
    assert got == {f"{R}/modem/a.c": ["build-modem"], f"{R}/dsp/b.c": ["build-dsp"],
                   f"{R}/common/util.c": ["build-dsp", "build-modem"]}          # in both: shared


def test_one_database_names_targets_by_the_compiler_triple():
    db = f"{R}/compile_commands.json"
    cdb = _db(("modem/a.c", db), ("dsp/b.c", db), ("app/c.c", db))
    triples = {f"{R}/modem/a.c": "arm-none-eabi", f"{R}/dsp/b.c": "hexagon"}
    got = _resolve(["modem/a.c", "dsp/b.c", "app/c.c"], cdb, triple=triples.get, build_root=None)
    assert got == {f"{R}/modem/a.c": ["arm-none-eabi"], f"{R}/dsp/b.c": ["hexagon"], f"{R}/app/c.c": ["compile_commands"]}


def test_a_header_takes_the_targets_of_the_files_that_include_it_and_else_unknown():
    m, d = f"{R}/out/build-modem/compile_commands.json", f"{R}/out/build-dsp/compile_commands.json"
    cdb = _db(("modem/a.c", m), ("dsp/b.c", d))
    inc = {f"{R}/inc/shared.h": {f"{R}/modem/a.c", f"{R}/dsp/b.c", f"{R}/inc/other.h"}, f"{R}/inc/modem.h": {f"{R}/modem/a.c"}}
    got = _resolve(["inc/shared.h", "inc/modem.h", "inc/orphan.h"], cdb, includers=lambda h: inc.get(h, set()))
    assert got == {f"{R}/inc/shared.h": ["build-dsp", "build-modem"], f"{R}/inc/modem.h": ["build-modem"],
                   f"{R}/inc/orphan.h": [UNKNOWN]}


def test_a_failing_triple_lookup_leaves_the_database_name():
    def boom(f):
        raise RuntimeError("no libclang")
    cdb = _db(("a.c", f"{R}/compile_commands.json"))
    assert _resolve(["a.c"], cdb, triple=boom, build_root=None) == {f"{R}/a.c": ["compile_commands"]}


def test_targets_are_read_from_the_config():
    cfg = Config.model_validate({"workspace": {"root": "/w", "compile_commands": "auto"},
                                 "targets": [{"match": "modem/**", "name": "modem"}]})
    assert cfg.targets == [TargetRule(match="modem/**", name="modem")]
    assert CompileDb([]).databases_of("/w/a.c") == []
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_targets.py -q`
Expected: FAIL: `1 error`; the first error is `ImportError: cannot import name 'TargetRule' from 'codetortoise.config' (backend/codetortoise/config.py)`

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py` (diff):

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index 7b06444..44eb212 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -50,6 +50,11 @@ class ToolchainConfig(BaseModel):
     strip_flags: list[str] = Field(default_factory=list)
 
 
+class TargetRule(BaseModel):
+    match: str                       # glob on the workspace-relative path, e.g. "modem/**"
+    name: str                        # the target's name on stories (spec 2026-10-05-two-tier-stories §3.1)
+
+
 class SwarmConfig(BaseModel):
     url: str | None = None
 
@@ -109,6 +114,7 @@ class Config(BaseModel):
     llm: LlmConfig = Field(default_factory=LlmConfig)
     auth: AuthConfig = Field(default_factory=AuthConfig)
     analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
+    targets: list[TargetRule] = Field(default_factory=list)   # first match names a file's build target
 
 
 class ConfigError(ValueError):
```

`backend/codetortoise/targets.py` (new file):

```python
"""The build targets of changed files (spec 2026-10-05-two-tier-stories §3.1).

A file's targets, first that applies: a configured name (`targets:` globs on the workspace-relative path); the compile
databases holding its commands, named by their directory under the build root, when the workspace has several; the
toolchain group's triple; the one database's name. A file with no command (a header) takes the targets of the files
including it; with none, `unknown`. A file with more than one target is shared.
"""
from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Callable

from codetortoise.config import TargetRule
from codetortoise.toolchain.compile_db import CompileDb

UNKNOWN = "unknown"


def db_name(db: str, base: str) -> str:
    """`<build_root>/build-modem/compile_commands.json` -> `build-modem`; a database at the base is named by its file."""
    d = posixpath.dirname(db)
    b = base.rstrip("/")
    rel = d[len(b) + 1:] if d.startswith(b + "/") else ("" if d == b else posixpath.basename(d))
    return rel or posixpath.splitext(posixpath.basename(db))[0]


def resolve_targets(files: list[str], rules: list[TargetRule], root: str, cdb: CompileDb, build_root: str | None,
                    triple_of: Callable[[str], str | None], includers: Callable[[str], set[str]]) -> dict[str, list[str]]:
    """Canonical local path -> its sorted target names."""
    base = (build_root or root).rstrip("/")
    several = len(cdb.databases) > 1

    def own(f: str) -> list[str]:
        rel = f[len(root.rstrip("/")) + 1:] if f.startswith(root.rstrip("/") + "/") else f
        rule = next((r for r in rules if fnmatch.fnmatch(rel, r.match)), None)
        if rule is not None:
            return [rule.name]
        dbs = cdb.databases_of(f)
        if not dbs:
            return []
        if several:
            return sorted({db_name(d, base) for d in dbs})
        try:
            t = triple_of(f)
        except Exception:  # no toolchain answer (libclang missing): the database still names it
            t = None
        return [t] if t else [db_name(dbs[0], base)]

    out = {}
    for f in files:
        names = own(f)
        if not names:
            names = sorted({t for inc in includers(f) for t in own(inc)}) or [UNKNOWN]
        out[f] = names
    return out
```

`backend/codetortoise/toolchain/compile_db.py` (diff):

```diff
diff --git a/backend/codetortoise/toolchain/compile_db.py b/backend/codetortoise/toolchain/compile_db.py
index a9f4965..fe5a060 100644
--- a/backend/codetortoise/toolchain/compile_db.py
+++ b/backend/codetortoise/toolchain/compile_db.py
@@ -127,6 +127,10 @@ class CompileDb:
                 return hit
         return self._by_file.get(file)
 
+    def databases_of(self, file: str) -> list[str]:
+        """Every database holding a command for the file, in precedence order (none: a header, an unbuilt file)."""
+        return list(dict.fromkeys(e.db for e in self._all.get(canon(file), [])))
+
     def nearest_entry(self, file: str) -> CompileEntry | None:
         """Exact entry, else one in the same folder, else the nearest folder up, within the file's own database."""
         file = canon(file)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_targets.py -q`
Expected: PASS: `6 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `456 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_targets.py backend/codetortoise/config.py backend/codetortoise/targets.py backend/codetortoise/toolchain/compile_db.py
git commit -m "feat(targets): every changed file's build target — configured name, compile database, triple, includers"
```

### Task 2: Pieces, links, cards and the change overview

Spec §3.2–§3.5. `pieces.build_pieces` cuts the changed nodes into pieces that never span two targets or two CLs. Each node goes to the first piece that takes it, in this order:
1. repeated edits (one substitution explaining at least 2 functions);
2. tests (test code that causes a flow excluded);
3. each connected group of new functions with the changed functions calling into it;
4. connected edits within one directory, at most 2 hops wide, a longer chain cut at its weakest link (ties at the lowest node id);
5. declarations, one per changed header and CL;
6. singles.

Ids `P1…` follow target, CL, first file and first line. Links have a type (`call`, `field`, `sub`, `uses`, `name`) and a count. Each piece gets a card of at most 300 tokens in a fixed field order. `change_overview` lists each CL with its description, then each target's files and directories by changed lines, then the shared files. The repeated-edit finder moves out of `stories.py` into `repeated.py`, unchanged, so pieces and stories share it.

**Files:**
- Test: `backend/tests/test_pieces.py`
- Create: `backend/codetortoise/pieces.py`
- Create: `backend/codetortoise/repeated.py`
- Modify: `backend/codetortoise/stories.py`

**Interfaces:**
- Consumes: `targets` from Task 1 (passed in as a dict); `board.analyse`'s `Analysis` and `_Ctx`; `clusters.altered_access`.
- Produces: `pieces.Piece(id, kind, targets, shared, cl, nodes, files, sub, names, card)`, `pieces.PieceLink(a, b, type, count)`,
  `pieces.PieceSet(pieces, links, targets, node_piece, overview)` with `.piece(pid) -> Piece | None` and `.links_of(pid) -> list[PieceLink]`;
  `pieces.build_pieces(c: BoardContext, a: Analysis, targets: dict[str, list[str]], includers=None, rep: Repeated | None = None) -> PieceSet`;
  `pieces.node_cl(x, nid) -> int | None`; `pieces.change_overview(c, x, targets, limit=OVERVIEW_CHARS) -> str`;
  `repeated.Repeated` and `repeated.find_repeated(c, x) -> Repeated` (with `_note`, `_plural`, `_spans`, `_q`, moved from `stories.py`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pieces.py` (new file):

```python
"""Pieces, links, cards and the change overview (spec 2026-10-05-two-tier-stories §3)."""
from test_stories import W, _edit, _mech, _world

from codetortoise.board import analyse
from codetortoise.diffmap import TypeChange
from codetortoise.pieces import CARD_CHARS, build_pieces, change_overview
from codetortoise.vcs.model import ClMeta, FileChange, PerClText


def _pieces(c, targets=None, includers=None):
    t = {f.local: (targets or {}).get(f.local[len(W) + 1:], ["fw"]) for f in c.cs.files}
    return build_pieces(c, analyse(c), t, includers)


def _labels(c, ps):
    return [(p.kind, sorted(c.impact.nodes[n].label for n in p.nodes)) for p in ps.pieces]


def _cls(c, by_file: dict[str, int], descriptions: dict[int, str] | None = None):
    """Put each file (relative to W) in one CL, and the review's CLs with their descriptions."""
    for f in c.cs.files:
        f.per_cl = [PerClText(cl=by_file[f.local[len(W) + 1:]], before=f.before, after=f.after)]
    c.cs.cls = [ClMeta(cl=n, status="pending", description=(descriptions or {}).get(n, "")) for n in sorted(set(by_file.values()))]
    return c


def test_pieces_never_span_two_targets_and_a_shared_file_is_its_own_piece():
    c = _world([_edit("modem_tx", "modem/tx.c"), _edit("dsp_run", "dsp/run.c"), _edit("util_crc", "common/crc.c")],
               calls=[("modem_tx", "util_crc"), ("dsp_run", "util_crc")])
    ps = _pieces(c, {"modem/tx.c": ["modem"], "dsp/run.c": ["dsp"], "common/crc.c": ["dsp", "modem"]})
    assert [(p.targets, p.shared, sorted(c.impact.nodes[n].label for n in p.nodes)) for p in ps.pieces] == [
        (["dsp"], False, ["dsp_run"]), (["dsp", "modem"], True, ["util_crc"]), (["modem"], False, ["modem_tx"])]
    assert {(lk.a, lk.b, lk.type, lk.count) for lk in ps.links} == {("P1", "P2", "call", 1), ("P2", "P3", "call", 1)}


def test_new_code_takes_the_changed_functions_that_call_into_it():
    c = _world([("band71_init", "rf/band71.c", None, ["setup();"]), ("band71_tables", "rf/band71.c", None, ["t();"]),
                _edit("bands_select", "rf/bands.c"), _edit("unrelated", "rf/bands.c")],
               calls=[("band71_init", "band71_tables"), ("bands_select", "band71_init")])
    ps = _pieces(c)
    assert _labels(c, ps) == [("new", ["band71_init", "band71_tables", "bands_select"]), ("single", ["unrelated"])]


def test_a_chain_wider_than_two_hops_is_cut_at_its_weakest_links():
    names = ["a_one", "b_two", "c_three", "d_four", "e_five"]
    c = _world([_edit(n, "core/chain.c") for n in names],
               calls=[("a_one", "b_two"), ("b_two", "c_three"), ("b_two", "c_three"), ("c_three", "d_four"),
                      ("c_three", "d_four"), ("d_four", "e_five")])
    ps = _pieces(c)
    assert sorted(_labels(c, ps)) == [("edits", ["b_two", "c_three", "d_four"]), ("single", ["a_one"]),
                                      ("single", ["e_five"])]


def test_pieces_never_span_two_cls_even_when_linked():
    c = _world([_edit("ref_write", "deps/ref/w.c"), _edit("ref_read", "deps/ref/r.c"),
                _edit("clar_sandbox", "deps/clar/s.c")], calls=[("ref_write", "ref_read")])
    _cls(c, {"deps/ref/w.c": 11, "deps/ref/r.c": 12, "deps/clar/s.c": 12})
    ps = _pieces(c)
    assert [(p.cl, sorted(c.impact.nodes[n].label for n in p.nodes)) for p in ps.pieces] == [
        (11, ["ref_write"]), (12, ["clar_sandbox"]), (12, ["ref_read"])]


def test_a_function_in_a_file_two_cls_touched_belongs_to_the_cl_that_wrote_it():
    c = _world([_edit("first", "x.c"), _edit("second", "x.c")])
    f = c.cs.files[0]
    mid = f.after.replace("\tsecond_more();\n", "")              # CL 11 adds first's line, CL 12 adds second's
    f.per_cl = [PerClText(cl=11, before=f.before, after=mid), PerClText(cl=12, before=mid, after=f.after)]
    c.cs.cls = [ClMeta(cl=11, status="pending"), ClMeta(cl=12, status="pending")]
    ps = _pieces(c)
    assert [(p.cl, [c.impact.nodes[n].label for n in p.nodes]) for p in ps.pieces] == [(11, ["first"]), (12, ["second"])]


def test_a_changed_header_is_a_declarations_piece_linked_to_the_code_using_it():
    c = _world([("use_flag", "src/use.c", ["a = 0;"], ["a = CFG_FLAG;"]), _edit("other", "lib/other.c")])
    h = f"{W}/inc/config.h"
    c.cs.files.append(FileChange(depot="//d" + h, local=h, action="edit", before="#define X 1\n",
                                 after="#define X 1\n#define CFG_FLAG 2\n"))
    c.dm.types.append(TypeChange(file=h, depot="//d" + h, name="CFG_FLAG", kind="macro_added"))
    ps = _pieces(c, includers=lambda hdr: {f"{W}/src/use.c"})
    (d,) = [p for p in ps.pieces if p.kind == "declarations"]
    assert d.files == [h] and d.names == ["CFG_FLAG"] and d.nodes == []
    use = ps.node_piece[next(n for n, x in c.impact.nodes.items() if x.label == "use_flag")]
    assert [(lk.type, lk.count) for lk in ps.links if {lk.a, lk.b} == {d.id, use}] == [("uses", 1)]
    assert "changed: CFG_FLAG" in d.card and "inc/config.h (+1 −0)" in d.card


def test_repeated_edits_and_tests_are_pieces_of_their_own():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c", var="b"), _edit("test_free", "tests/t.c"),
                _edit("busy", "src/c.c")])
    ps = _pieces(c)
    assert sorted(_labels(c, ps)) == [("repeated", ["free_a", "free_b"]), ("single", ["busy"]), ("tests", ["test_free"])]
    (r,) = [p for p in ps.pieces if p.kind == "repeated"]
    assert r.sub == ["git_vector_free", "git_vector_dispose"]
    assert r.card.startswith(f"{r.id}  repeated edit `git_vector_free` → `git_vector_dispose` · target fw · CL 1")


def test_links_count_calls_shared_fields_and_shared_name_prefixes():
    c = _world([_edit("stack_add_one", "a/x.c"), _edit("stack_add_two", "b/y.c"), _edit("lone", "c/z.c")],
               calls=[("stack_add_one", "lone"), ("stack_add_one", "lone")],
               fields=[("stack_add_one", "R", "v", "write", "added"), ("stack_add_two", "R", "v", "write", "added")])
    ps = _pieces(c)
    one, two, lone = (ps.node_piece[n] for n in ("N1", "N2", "N3"))
    got = {(lk.type, lk.count) for lk in ps.links if {lk.a, lk.b} == {one, two}}
    assert got == {("field", 1), ("name", 1)}
    assert {(lk.type, lk.count) for lk in ps.links if {lk.a, lk.b} == {one, lone}} == {("call", 2)}


def test_ids_and_cards_are_the_same_every_time_and_cards_keep_their_field_order():
    def make():
        c = _world([("band71_init", "rf/band71.c", None, ["setup();"]), _edit("bands_select", "rf/bands.c"),
                    _edit("modem_tx", "modem/tx.c")], calls=[("bands_select", "band71_init")])
        new = next(f for f in c.cs.files if f.local.endswith("band71.c"))
        new.action, new.before = "add", ""
        return _cls(c, {"rf/band71.c": 412, "rf/bands.c": 412, "modem/tx.c": 413},
                    {412: "modem: add LTE band 71 support\n\nlonger text", 413: "tx fix"})
    a, b = _pieces(make()), _pieces(make())
    assert [p.model_dump() for p in a.pieces] == [p.model_dump() for p in b.pieces]
    p1 = a.pieces[0]
    rows = p1.card.split("\n")
    assert rows[0] == 'P1  new code · target fw · CL 412 "modem: add LTE band 71 support"'
    assert rows[1] == "files: rf/band71.c (+4 new), rf/bands.c (+1 −0)"
    assert rows[2].startswith("functions: band71_init: new function; bands_select: +1 −0 lines")
    assert rows[3] == "flows: — · findings: —" and rows[4] == "links: —"
    assert all(len(p.card) <= CARD_CHARS for p in a.pieces)


def test_the_overview_lists_each_cl_and_each_target_with_shared_files_once():
    c = _world([_edit("modem_tx", "modem/rf/tx.c"), _edit("dsp_run", "dsp/run.c"), _edit("util_crc", "common/crc.c")])
    _cls(c, {"modem/rf/tx.c": 11, "dsp/run.c": 11, "common/crc.c": 12}, {11: "modem and dsp", 12: "crc " * 1000})
    t = {f"{W}/modem/rf/tx.c": ["modem"], f"{W}/dsp/run.c": ["dsp"], f"{W}/common/crc.c": ["dsp", "modem"]}
    from codetortoise.board import _Ctx
    text = change_overview(c, _Ctx(c), t)
    assert text.splitlines()[:2] == ["CHANGE: 2 CLs, 3 files, +3 −0 lines", "CL 11 (pending): modem and dsp"]
    assert "TARGET dsp: 1 file, +1 −0\n  dsp: 1 file, +1 −0\nTARGET modem: 1 file, +1 −0\n  modem/rf: 1 file, +1 −0" in text
    assert text.endswith("SHARED FILES\n  common/crc.c: dsp, modem (+1 −0)")
    assert len(text.splitlines()[2]) == len("CL 12 (pending): ") + 2400      # a long description is cut at 600 tokens
    many = {f"{W}/d{i}/e{i}/f{i}/g{i}/x.c": ["fw"] for i in range(400)}
    c.cs.files += [FileChange(depot="//d" + f, local=f, action="edit", before="a\n", after="b\n") for f in many]
    assert len(change_overview(c, _Ctx(c), many, limit=6000)) <= 6000
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_pieces.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.pieces'`

- [ ] **Step 3: Implement**

`backend/codetortoise/pieces.py` (new file):

```python
"""The change cut into pieces, the links between them, a card per piece and an overview of the change (spec
2026-10-05-two-tier-stories §3). Rules only, no AI: both tiers start from these.

A piece is a few changed nodes that are almost never wrong to keep together; pieces never span two targets or two CLs.
Cut in order, each node going to the first piece that takes it: tests, repeated edits, new code with its direct
callers, connected edits (at most 2 hops wide), declarations (one per changed header and CL), singles. Ids P1… follow
target, CL, first file and first line, so the same change always gives the same pieces.
"""
from __future__ import annotations

import posixpath
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import Analysis, BoardContext, _count, _Ctx, _opcodes
from codetortoise.clusters import altered_access
from codetortoise.cparse import is_header
from codetortoise.repeated import Repeated, _note, _plural, _spans, find_repeated
from codetortoise.targets import UNKNOWN

PieceKind = Literal["tests", "repeated", "new", "edits", "declarations", "single"]
LinkType = Literal["call", "field", "sub", "uses", "name"]
CARD_CHARS = 1200                     # 300 tokens
OVERVIEW_CHARS = 6000                 # 1500 tokens
CL_CHARS = 2400                       # a CL description in the overview: 600 tokens
MAX_HOPS = 2
_KIND_TEXT = {"tests": "tests", "new": "new code", "edits": "connected edits", "declarations": "declarations",
              "single": "single change"}


class Piece(BaseModel):
    id: str
    kind: PieceKind
    targets: list[str]
    shared: bool = False              # code built for more than one target
    cl: int | None = None
    nodes: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)   # canonical local paths
    sub: list[str] | None = None      # a repeated edit: [old, new]
    names: list[str] = Field(default_factory=list)   # declarations: the changed macros, types and declarations
    card: str = ""


class PieceLink(BaseModel):
    a: str
    b: str
    type: LinkType
    count: int


class PieceSet(BaseModel):
    pieces: list[Piece] = Field(default_factory=list)
    links: list[PieceLink] = Field(default_factory=list)
    targets: dict[str, list[str]] = Field(default_factory=dict)    # local file -> its targets
    node_piece: dict[str, str] = Field(default_factory=dict)
    overview: str = ""

    def piece(self, pid: str) -> Piece | None:
        return next((p for p in self.pieces if p.id == pid), None)

    def links_of(self, pid: str) -> list[PieceLink]:
        return [lk for lk in self.links if pid in (lk.a, lk.b)]


def _nk(nid: str) -> tuple:
    """Node ids in number order: N3 before N12."""
    return (int(nid[1:]), nid) if nid[1:].isdigit() else (1 << 30, nid)


def _rel(x: _Ctx, path: str) -> str:
    root = x.c.root.rstrip("/") + "/"
    return path[len(root):] if x.c.root and path.startswith(root) else path


def node_cl(x: _Ctx, nid: str) -> int | None:
    """The CL that changed a node: its file's only CL, else the CL whose own diff adds (or, for a removed function,
    deletes) most of the function's lines; ties and no match go to the lowest CL."""
    local = x.local(nid) or ""
    fc = x.texts.get(local)
    cls = [p.cl for p in fc.per_cl] if fc else []
    if not cls:
        return x.c.cs.cls[0].cl if x.c.cs.cls else None
    if len(cls) == 1:
        return cls[0]
    n = x.im.nodes[nid]
    fa, fb = x.fa.get(n.key), x.fb.get(n.key)
    side, fn = ("after", fa) if fa else ("before", fb)
    if fn is None:
        return min(cls)
    text = fc.after if side == "after" else fc.before
    want = {ln.strip() for ln in text.splitlines()[fn.start_line - 1:fn.end_line] if len(ln.strip()) >= 4}

    def score(p) -> int:
        a, b = p.before.splitlines(), p.after.splitlines()
        hit = 0
        for tag, i1, i2, j1, j2 in _opcodes(p.before, p.after):
            if tag == "equal":
                continue
            rows = b[j1:j2] if side == "after" else a[i1:i2]
            hit += sum(1 for r in rows if r.strip() in want)
        return hit
    best = max(sorted(fc.per_cl, key=lambda p: p.cl), key=score)
    return best.cl if score(best) else min(cls)


def _name_cl(fc, name: str) -> int | None:
    """The first CL whose own diff touches a line naming `name` (a header's macro, type or declaration)."""
    word = re.compile(rf"\b{re.escape(name.split()[-1])}\b")
    for p in sorted(fc.per_cl, key=lambda p: p.cl):
        a, b = p.before.splitlines(), p.after.splitlines()
        for tag, i1, i2, j1, j2 in _opcodes(p.before, p.after):
            if tag != "equal" and any(word.search(r) for r in a[i1:i2] + b[j1:j2]):
                return p.cl
    return min((p.cl for p in fc.per_cl), default=None)


def _components(nodes: list[str], adj: dict[str, Counter]) -> list[list[str]]:
    seen: set[str] = set()
    out = []
    pool = set(nodes)
    for n in sorted(nodes, key=_nk):
        if n in seen:
            continue
        comp, stack = [], [n]
        seen.add(n)
        while stack:
            m = stack.pop()
            comp.append(m)
            for k in adj[m]:
                if k in pool and k not in seen:
                    seen.add(k)
                    stack.append(k)
        out.append(sorted(comp, key=_nk))
    return out


def _diameter(comp: list[str], adj: dict[str, Counter]) -> int:
    pool, best = set(comp), 0
    for s in comp:
        dist, frontier = {s: 0}, [s]
        while frontier:
            nxt = []
            for m in frontier:
                for k in adj[m]:
                    if k in pool and k not in dist:
                        dist[k] = dist[m] + 1
                        nxt.append(k)
            frontier = nxt
        best = max(best, max(dist.values()))
    return best


def _cut(nodes: list[str], adj: dict[str, Counter]) -> list[list[str]]:
    """Connected groups at most MAX_HOPS wide: a wider one loses its weakest link (fewest calls and shared fields;
    ties at the lowest node ids) until it splits narrow enough."""
    local = {n: Counter({k: w for k, w in adj[n].items() if k in set(nodes)}) for n in nodes}
    local = defaultdict(Counter, local)
    out, todo = [], _components(nodes, local)
    while todo:
        comp = todo.pop(0)
        if _diameter(comp, local) <= MAX_HOPS:
            out.append(comp)
            continue
        a, b = min(((a, b) for a in comp for b in local[a] if _nk(a) < _nk(b)),
                   key=lambda e: (local[e[0]][e[1]], _nk(e[0]), _nk(e[1])))
        del local[a][b], local[b][a]
        todo = _components(comp, local) + todo
    return out


def _fn_text(x: _Ctx, nid: str) -> str:
    n = x.im.nodes[nid]
    fn = x.fa.get(n.key) or x.fb.get(n.key)
    fc = x.texts.get(fn.file) if fn else None
    if fn is None or fc is None:
        return ""
    text = fc.after if n.key in x.fa else fc.before
    return "\n".join(text.splitlines()[fn.start_line - 1:fn.end_line])


def _fn_lines(x: _Ctx, nid: str) -> tuple[int, int]:
    """(+added, −removed) lines of a changed function."""
    n = x.im.nodes[nid]
    fa, fb = x.fa.get(n.key), x.fb.get(n.key)
    if fa and not fb:
        return fa.end_line - fa.start_line + 1, 0
    if fb and not fa:
        return 0, fb.end_line - fb.start_line + 1
    add = rem = 0
    for fc, _, (a0, a1) in _spans(x, nid):
        a, r = _count(fc.before, fc.after, a0, a1)
        add, rem = add + a, rem + r
    return add, rem


_SPLIT = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")


def _prefix(label: str) -> str | None:
    """A function's first two name tokens (`reftable_stack_add` -> `reftable stack`), None for shorter names."""
    toks = [t.lower() for t in _SPLIT.split(label.split("::")[-1]) if t]
    return " ".join(toks[:2]) if len(toks) >= 2 else None


def build_pieces(c: BoardContext, a: Analysis, targets: dict[str, list[str]],
                 includers: Callable[[str], set[str]] | None = None, rep: Repeated | None = None) -> PieceSet:
    """Cut the change into pieces, link them and write their cards and the change overview. `targets` maps local files
    to their targets (targets.resolve_targets); `includers` (a header's transitive includers) narrows `uses` links."""
    x = a.x
    im = x.im
    rep = rep or find_repeated(c, x)
    changed = [n for n in im.changed if n in im.nodes and im.nodes[n].kind == "function"]

    def tkey(nid: str) -> tuple[str, ...]:
        return tuple(targets.get(x.local(nid) or "") or [UNKNOWN])
    cl_of = {n: node_cl(x, n) for n in changed}
    taken: set[str] = set()
    drafts: list[dict] = []

    def add(kind: str, nodes: list[str], **extra) -> None:
        nodes = sorted(nodes, key=_nk)
        taken.update(nodes)
        drafts.append({"kind": kind, "nodes": nodes, "targets": list(tkey(nodes[0])), "cl": cl_of[nodes[0]], **extra})

    # adjacency among changed functions: direct calls and shared changed fields
    adj: dict[str, Counter] = defaultdict(Counter)
    for e in im.edges:
        if e.kind in ("call", "virtual") and e.src in cl_of and e.dst in cl_of and e.src != e.dst:
            adj[e.src][e.dst] += 1
            adj[e.dst][e.src] += 1
    by_field: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if altered_access(e) and e.src in cl_of:
            by_field[e.dst].add(e.src)
    for fns in by_field.values():
        for f in fns:
            for g in fns - {f}:
                adj[f][g] += 1

    # 1. tests, by target, CL and directory
    groups: dict[tuple, list[str]] = defaultdict(list)
    for n in changed:
        if x.is_test_path(n):
            groups[(tkey(n), cl_of[n], posixpath.dirname(x.local(n) or ""))].append(n)
    for nodes in groups.values():
        add("tests", nodes)
    # 2. repeated edits, by substitution, target and CL
    groups = defaultdict(list)
    for n in changed:
        if n not in taken and n in rep.mech_of:
            s = rep.mech_of[n]
            groups[(s.old, s.new, tkey(n), cl_of[n])].append(n)
    for (old, new, _, _), nodes in groups.items():
        add("repeated", nodes, sub=[old, new])
    # 3. new code with the changed functions calling into it, within a target and CL
    added = [n for n in changed if n not in taken and im.nodes[n].key in x.fa and im.nodes[n].key not in x.fb]
    groups = defaultdict(list)
    for n in added:
        groups[(tkey(n), cl_of[n])].append(n)
    calls: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if e.kind in ("call", "virtual"):
            calls[e.src].add(e.dst)
    for key, nodes in groups.items():
        comps = _components(nodes, adj)
        callers: dict[int, list[str]] = defaultdict(list)
        for m in changed:
            if m in taken or m in added or (tkey(m), cl_of[m]) != key:
                continue
            hit = next((i for i, comp in enumerate(comps) if calls[m] & set(comp)), None)   # the first group it calls
            if hit is not None:
                callers[hit].append(m)
        for i, comp in enumerate(comps):
            add("new", comp + callers[i])
    # 4. connected edits within a target, CL and directory, at most 2 hops wide; one function alone is a single
    groups = defaultdict(list)
    for n in changed:
        if n not in taken:
            groups[(tkey(n), cl_of[n], posixpath.dirname(x.local(n) or ""))].append(n)
    for nodes in groups.values():
        for comp in _cut(nodes, adj):
            add("edits" if len(comp) > 1 else "single", comp)
    # 5. declarations: each changed header's macros, types and declarations, per CL
    decl: dict[tuple[str, int | None], list[str]] = defaultdict(list)
    for t in c.dm.types:
        if is_header(t.file):
            fc = x.texts.get(t.file)
            cl = (_name_cl(fc, t.name) if fc and fc.per_cl else (c.cs.cls[0].cl if c.cs.cls else None))
            decl[(t.file, cl)].append(t.name)
    for (header, cl), names in decl.items():
        drafts.append({"kind": "declarations", "nodes": [], "targets": targets.get(header) or [UNKNOWN], "cl": cl,
                       "files": [header], "names": sorted(set(names))})

    # ids in a fixed order: target, CL, first file, first line
    for d in drafts:
        d.setdefault("files", sorted({x.local(n) for n in d["nodes"] if x.local(n)}))

    def order(d: dict) -> tuple:
        first = d["files"][0] if d["files"] else ""
        line = min((im.nodes[n].line or 0 for n in d["nodes"] if x.local(n) == first), default=0)
        return (",".join(d["targets"]), d["cl"] or 0, first, line, d["kind"], [_nk(n) for n in d["nodes"]])
    drafts.sort(key=order)
    pieces = [Piece(id=f"P{i + 1}", kind=d["kind"], targets=d["targets"], shared=len(d["targets"]) > 1, cl=d["cl"],
                    nodes=d["nodes"], files=d["files"], sub=d.get("sub"), names=d.get("names", []))
              for i, d in enumerate(drafts)]
    node_piece = {n: p.id for p in pieces for n in p.nodes}
    links = _links(x, pieces, node_piece, rep, includers)
    ps = PieceSet(pieces=pieces, links=links, targets={f: targets.get(f) or [UNKNOWN] for f in
                                                       {f for p in pieces for f in p.files}}, node_piece=node_piece)
    for p in pieces:
        p.card = _card(x, p, ps, a, rep)
    ps.overview = change_overview(c, x, ps.targets)
    return ps


def _links(x: _Ctx, pieces: list[Piece], node_piece: dict[str, str], rep: Repeated,
           includers: Callable[[str], set[str]] | None) -> list[PieceLink]:
    im = x.im
    rank = {p.id: i for i, p in enumerate(pieces)}
    counts: Counter = Counter()

    def link(p: str, q: str, typ: str, k: int = 1) -> None:
        if p != q and k:
            a, b = sorted((p, q), key=rank.get)
            counts[(a, b, typ)] += k
    for e in im.edges:
        if e.kind in ("call", "virtual") and e.src in node_piece and e.dst in node_piece:
            link(node_piece[e.src], node_piece[e.dst], "call")
    by_field: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if altered_access(e) and e.src in node_piece:
            by_field[e.dst].add(node_piece[e.src])
    for ps in by_field.values():
        for p in ps:
            for q in ps:
                if rank[p] < rank[q]:
                    link(p, q, "field")
    for s in sorted(rep.mech_subs, key=lambda s: (s.old, s.new)):
        holders = sorted({node_piece[n] for n, sites in rep.fn_sites.items() if n in node_piece
                          and any(st.sub == s for st in sites)}, key=rank.get)
        for i, p in enumerate(holders):
            for q in holders[i + 1:]:
                link(p, q, "sub")
    texts = {n: _fn_text(x, n) for n in node_piece}
    for d in (p for p in pieces if p.kind == "declarations"):
        words = [re.compile(rf"\b{re.escape(n.split()[-1])}\b") for n in d.names]
        inc = includers(d.files[0]) if includers else None
        for p in pieces:
            if p.kind == "declarations" or (inc is not None and not (set(p.files) & inc) and d.files[0] not in p.files):
                continue
            link(d.id, p.id, "uses", sum(1 for n in p.nodes if any(w.search(texts[n]) for w in words)))
    by_prefix: dict[str, Counter] = defaultdict(Counter)
    for n, pid in node_piece.items():
        pre = _prefix(x.label(n))
        if pre:
            by_prefix[pre][pid] += 1
    for cnt in by_prefix.values():
        ids = sorted(cnt, key=rank.get)
        for i, p in enumerate(ids):
            for q in ids[i + 1:]:
                link(p, q, "name", cnt[p] * cnt[q])
    return [PieceLink(a=a, b=b, type=t, count=k)
            for (a, b, t), k in sorted(counts.items(), key=lambda kv: (rank[kv[0][0]], rank[kv[0][1]], kv[0][2]))]


def _cl_line(x: _Ctx, cl: int | None) -> str:
    if cl is None:
        return "no CL"
    meta = next((m for m in x.c.cs.cls if m.cl == cl), None)
    first = (meta.description.strip().splitlines() or [""])[0].strip() if meta else ""
    return f'CL {cl} "{first[:60]}"' if first else f"CL {cl}"


def _card(x: _Ctx, p: Piece, ps: PieceSet, a: Analysis, rep: Repeated) -> str:
    """What the strong model sees of a piece, in a fixed field order, at most CARD_CHARS."""
    im = x.im
    kind = (f"repeated edit `{p.sub[0]}` → `{p.sub[1]}`" if p.kind == "repeated" and p.sub else _KIND_TEXT[p.kind])
    tgt = f"target {p.targets[0]}" if len(p.targets) == 1 else f"targets {', '.join(p.targets)} (shared)"
    head = f"{p.id}  {kind} · {tgt} · {_cl_line(x, p.cl)}"
    lines = {n: _fn_lines(x, n) for n in p.nodes}
    files = []
    for f in p.files:
        fc = x.texts.get(f)
        if p.kind == "declarations" and fc:
            add, rem = _count(fc.before, fc.after)
        else:
            add = sum(lines[n][0] for n in p.nodes if x.local(n) == f)
            rem = sum(lines[n][1] for n in p.nodes if x.local(n) == f)
        files.append(f"{_rel(x, f)} (+{add} new)" if fc and fc.action in ("add", "branch", "move/add") and not fc.before
                     else f"{_rel(x, f)} (+{add} −{rem})")
    if p.kind == "declarations":
        fns = "changed: " + ", ".join(p.names[:8]) + (f" +{len(p.names) - 8} more" if len(p.names) > 8 else "")
    else:
        top = sorted(p.nodes, key=lambda n: (-sum(lines[n]), _nk(n)))
        notes = [f"{x.label(n)}: {_note(x, n, rep.mech_of, rep.fn_sites, rep.mech_subs)}" for n in top[:5]]
        fns = "functions: " + "; ".join(notes) + (f"; +{len(top) - 5} more" if len(top) > 5 else "")
    mine = set(p.nodes)
    flows = [f"{fl.id} {' → '.join(im.nodes[n].label for n in fl.path if n in im.nodes)} ({fl.tag})"
             for fl in a.flows if (fl.cause or fl.path[-1]) in mine]
    finds = [f"{f.id} ({f.kind}, {f.title[:60]})" for f in x.c.findings
             if set(f.nodes) & mine or (p.kind == "declarations" and any(e.file in p.files for e in f.evidence))]
    links = sorted(ps.links_of(p.id), key=lambda lk: (-lk.count, lk.b if lk.a == p.id else lk.a, lk.type))
    lk_text = " · ".join(f"→ {lk.b if lk.a == p.id else lk.a} {lk.type} ×{lk.count}" for lk in links[:6])
    text = "\n".join([head, "files: " + ", ".join(files), fns,
                      f"flows: {'; '.join(flows) or '—'} · findings: {'; '.join(finds) or '—'}",
                      f"links: {lk_text or '—'}"])
    return text if len(text) <= CARD_CHARS else text[:CARD_CHARS - 1] + "…"


def change_overview(c: BoardContext, x: _Ctx, targets: dict[str, list[str]], limit: int = OVERVIEW_CHARS) -> str:
    """Each CL with its description, then per target the changed files, lines and a directory map (as deep as fits);
    shared files once, with their targets."""
    files = [f for f in c.cs.files if f.local]
    stats = {f.local: _count(f.before, f.after) for f in files}
    new = {f.local for f in files if not f.before}
    total_add, total_rem = sum(s[0] for s in stats.values()), sum(s[1] for s in stats.values())
    head = [f"CHANGE: {_plural(len(c.cs.cls), 'CL')}, {_plural(len(files), 'file')}, +{total_add} −{total_rem} lines"]
    for m in c.cs.cls:
        desc = m.description.strip()
        desc = desc if len(desc) <= CL_CHARS else desc[:CL_CHARS - 1] + "…"
        head.append(f"CL {m.cl} ({m.status}{', ' + m.user if m.user else ''}): {desc or '(no description)'}")
    tg = {f.local: targets.get(f.local) or [UNKNOWN] for f in files}
    shared = sorted(f for f, t in tg.items() if len(t) > 1)
    by_target: dict[str, list[str]] = defaultdict(list)
    for f, t in tg.items():
        if len(t) == 1:
            by_target[t[0]].append(f)

    def render(depth: int) -> list[str]:
        out = []
        for t in sorted(by_target):
            fs = by_target[t]
            add, rem = sum(stats[f][0] for f in fs), sum(stats[f][1] for f in fs)
            fresh = sum(stats[f][0] for f in fs if f in new)
            out.append(f"TARGET {t}: {_plural(len(fs), 'file')}, +{add} −{rem}" + (f" (+{fresh} in new files)" if fresh else ""))
            dirs: dict[str, list[str]] = defaultdict(list)
            for f in fs:
                d = posixpath.dirname(_rel(x, f))
                dirs["/".join(d.split("/")[:depth]) or "."].append(f)
            for d in sorted(dirs):
                out.append(f"  {d}: {_plural(len(dirs[d]), 'file')}, +{sum(stats[f][0] for f in dirs[d])} "
                           f"−{sum(stats[f][1] for f in dirs[d])}")
        if shared:
            out.append("SHARED FILES")
            out += [f"  {_rel(x, f)}: {', '.join(tg[f])} (+{stats[f][0]} −{stats[f][1]})" for f in shared]
        return out
    room = limit - len("\n".join(head)) - 1
    for depth in (4, 3, 2, 1):
        body = render(depth)
        if len("\n".join(body)) <= room:
            break
    text = "\n".join(head + body)
    return text if len(text) <= limit else text[:limit - 1] + "…"
```

`backend/codetortoise/repeated.py` (new file):

```python
"""Repeated edits: one token substitution explaining whole functions (spec 2026-10-04-change-stories §2.1), and the
few words saying what changed in a node. Stories and pieces (spec 2026-10-05-two-tier-stories §3.2) share them."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from codetortoise.board import BoardContext, _count, _Ctx
from codetortoise.substitutions import Site, Sub, changed_pairs


@dataclass
class Repeated:
    fn_sites: dict[str, list[Site]] = field(default_factory=dict)     # changed function -> its substitution sites
    fn_explained: dict[str, bool] = field(default_factory=dict)       # every changed line is a substitution
    outside: list[tuple[Site, str]] = field(default_factory=list)     # sites outside functions, with their file
    count: Counter = field(default_factory=Counter)                   # substitution -> its sites
    mech_subs: set[Sub] = field(default_factory=set)                  # substitutions explaining at least 2 functions
    mech_of: dict[str, Sub] = field(default_factory=dict)             # mechanical function -> its substitution


def _q(s: str) -> str:
    return f"`{s}`"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def find_repeated(c: BoardContext, x: _Ctx) -> Repeated:
    """Substitutions in each changed function and outside functions; those explaining at least 2 functions."""
    im = x.im
    changed = [n for n in im.changed if n in im.nodes]
    fn_sites: dict[str, list[Site]] = {}
    fn_explained: dict[str, bool] = {}
    for nid in changed:
        if im.nodes[nid].kind != "function":
            continue
        spans = _spans(x, nid)
        if not spans:
            continue
        all_sites, unexplained = [], 0
        for fc, (b0, b1), (a0, a1) in spans:
            sites, u = changed_pairs(fc.before.splitlines()[b0 - 1:b1], fc.after.splitlines()[a0 - 1:a1])
            all_sites += [Site(s.sub, s.before_line + b0 - 1, s.after_line + a0 - 1, s.before, s.after) for s in sites]
            unexplained += u
        fn_sites[nid] = all_sites
        fn_explained[nid] = bool(all_sites) and not unexplained
    outside: list[tuple[Site, str]] = []
    spans_a: dict[str, list[tuple[int, int]]] = defaultdict(list)     # file -> its functions' lines, after and before
    spans_b: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for facts, spans in ((c.after, spans_a), (c.before, spans_b)):
        for fx in facts:
            for f in fx.functions:
                spans[f.file].append((f.start_line, f.end_line))
    for fc in c.cs.files:
        if fc.action != "edit":
            continue
        inside_a, inside_b = spans_a[fc.local], spans_b[fc.local]
        sites, _ = changed_pairs(fc.before.splitlines(), fc.after.splitlines())
        for s in sites:
            if not any(lo <= s.after_line <= hi for lo, hi in inside_a) and not any(lo <= s.before_line <= hi
                                                                                   for lo, hi in inside_b):
                outside.append((s, fc.local))

    fns_of: dict[Sub, set[str]] = defaultdict(set)
    for nid, sites in fn_sites.items():
        if fn_explained[nid]:
            for s in sites:
                fns_of[s.sub].add(nid)
    count: Counter[Sub] = Counter(s.sub for sites in fn_sites.values() for s in sites)
    count.update(s.sub for s, _ in outside)
    mech_subs = {s for s, fns in fns_of.items() if len(fns) >= 2}
    mech_of: dict[str, Sub] = {}                              # mechanical function -> its story's substitution
    for nid, sites in fn_sites.items():
        subs = {s.sub for s in sites}
        if fn_explained[nid] and subs <= mech_subs:
            mech_of[nid] = max(subs, key=lambda s: (count[s], s.old, s.new))
    return Repeated(fn_sites, fn_explained, outside, count, mech_subs, mech_of)


def _spans(x: _Ctx, nid: str) -> list[tuple]:
    """A changed function's (file, before lines, after lines), from the diff map: a function defined twice in one file
    (under #ifdef) is the definition that changed, not the first the facts list."""
    n = x.im.nodes[nid]
    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
    if fb is None or fa is None:
        return []
    texts = x.texts
    out = [(texts[d.file], d.before_lines, d.after_lines) for d in x.c.dm.functions
           if d.qualname == fa.qualname and d.file in (fa.file, fb.file) and d.before_lines and d.after_lines
           and d.file in texts]
    own = [o for o in out if o[2][0] <= fa.start_line <= o[2][1]]     # overloads share a name: each reads its own span
    out = own or out
    if not out and fa.file in texts:
        out = [(texts[fa.file], (fb.start_line, fb.end_line), (fa.start_line, fa.end_line))]
    return out


def _note(x: _Ctx, nid: str, mech_of: dict[str, Sub], fn_sites: dict[str, list[Site]], mech_subs: set) -> str:
    """What changed in a node, in a few words."""
    n = x.im.nodes[nid]
    if nid not in x.changed:
        return ""
    if nid in mech_of:
        s = mech_of[nid]
        return f"{_q(s.new)} instead of {_q(s.old)}"
    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
    parts = []
    if fb is None and fa is not None:
        parts.append("new function")
    elif fa is None and fb is not None:
        parts.append("removed")
    else:
        ch = next((d for d in x.c.dm.functions if fa and d.file == fa.file and d.qualname == fa.qualname), None)
        if ch is not None and ch.kind == "signature_changed":
            parts.append("signature changed")
    for status, verb in (("added", "now writes"), ("removed", "no longer writes")):
        fields = [x.label(e.dst).split("::")[-1] for e in x.writes_from.get(nid, [])
                  if e.status == status and e.dst in x.im.nodes]
        if fields:
            parts.append(f"{verb} {', '.join(dict.fromkeys(fields[:3]))}" + (f" +{len(fields) - 3}" if len(fields) > 3 else ""))
    also = sorted({s.sub for s in fn_sites.get(nid, []) if s.sub in mech_subs}, key=lambda s: s.old)
    if also:
        parts.append("also " + ", ".join(f"{_q(s.old)} → {_q(s.new)}" for s in also[:2]))
    if not parts:
        add = rem = 0
        for fc, _, (a0, a1) in _spans(x, nid):
            a, r = _count(fc.before, fc.after, a0, a1)
            add, rem = add + a, rem + r
        parts.append(f"+{add} −{rem} lines" if add or rem else "layout only")
    return "; ".join(parts)
```

`backend/codetortoise/stories.py` (diff):

```diff
diff --git a/backend/codetortoise/stories.py b/backend/codetortoise/stories.py
index 3115b0e..def686c 100644
--- a/backend/codetortoise/stories.py
+++ b/backend/codetortoise/stories.py
@@ -34,7 +34,8 @@ from codetortoise.board import (
 from codetortoise.clusters import _shared, altered_access, cluster_change
 from codetortoise.detectors.base import SEVERITY_RANK
 from codetortoise.impact import ImpactModel
-from codetortoise.substitutions import Site, Sub, changed_pairs
+from codetortoise.repeated import _note, _plural, _q, find_repeated
+from codetortoise.substitutions import Site, Sub
 
 Kind = Literal["behaviour", "other", "mechanical", "tests"]
 RISK = {3: "high", 2: "medium", 1: "low"}
@@ -106,14 +107,6 @@ class StorySet(BaseModel):
     finding_story: dict[str, str] = Field(default_factory=dict)
 
 
-def _q(s: str) -> str:
-    return f"`{s}`"
-
-
-def _plural(n: int, one: str, many: str | None = None) -> str:
-    return f"{n} {one if n == 1 else (many or one + 's')}"
-
-
 class _Draft:
     """A story while it is being built."""
 
@@ -153,51 +146,8 @@ def build_stories(c: BoardContext, home: dict[str, str] | None = None,
     is_test = x.is_test_path
 
     # 1. substitutions: in each changed function, and outside functions
-    fn_sites: dict[str, list[Site]] = {}
-    fn_explained: dict[str, bool] = {}
-    for nid in changed:
-        if im.nodes[nid].kind != "function":
-            continue
-        spans = _spans(x, nid)
-        if not spans:
-            continue
-        all_sites, unexplained = [], 0
-        for fc, (b0, b1), (a0, a1) in spans:
-            sites, u = changed_pairs(fc.before.splitlines()[b0 - 1:b1], fc.after.splitlines()[a0 - 1:a1])
-            all_sites += [Site(s.sub, s.before_line + b0 - 1, s.after_line + a0 - 1, s.before, s.after) for s in sites]
-            unexplained += u
-        fn_sites[nid] = all_sites
-        fn_explained[nid] = bool(all_sites) and not unexplained
-    outside: list[tuple[Site, str]] = []
-    spans_a: dict[str, list[tuple[int, int]]] = defaultdict(list)     # file -> its functions' lines, after and before
-    spans_b: dict[str, list[tuple[int, int]]] = defaultdict(list)
-    for facts, spans in ((c.after, spans_a), (c.before, spans_b)):
-        for fx in facts:
-            for f in fx.functions:
-                spans[f.file].append((f.start_line, f.end_line))
-    for fc in c.cs.files:
-        if fc.action != "edit":
-            continue
-        inside_a, inside_b = spans_a[fc.local], spans_b[fc.local]
-        sites, _ = changed_pairs(fc.before.splitlines(), fc.after.splitlines())
-        for s in sites:
-            if not any(lo <= s.after_line <= hi for lo, hi in inside_a) and not any(lo <= s.before_line <= hi
-                                                                                   for lo, hi in inside_b):
-                outside.append((s, fc.local))
-
-    fns_of: dict[Sub, set[str]] = defaultdict(set)
-    for nid, sites in fn_sites.items():
-        if fn_explained[nid]:
-            for s in sites:
-                fns_of[s.sub].add(nid)
-    count: Counter[Sub] = Counter(s.sub for sites in fn_sites.values() for s in sites)
-    count.update(s.sub for s, _ in outside)
-    mech_subs = {s for s, fns in fns_of.items() if len(fns) >= 2}
-    mech_of: dict[str, Sub] = {}                              # mechanical function -> its story's substitution
-    for nid, sites in fn_sites.items():
-        subs = {s.sub for s in sites}
-        if fn_explained[nid] and subs <= mech_subs:
-            mech_of[nid] = max(subs, key=lambda s: (count[s], s.old, s.new))
+    rep = find_repeated(c, x)
+    fn_sites, outside, count, mech_subs, mech_of = rep.fn_sites, rep.outside, rep.count, rep.mech_subs, rep.mech_of
 
     mech = {s: _Draft("mechanical", sub=s) for s in sorted(mech_subs, key=lambda s: (-count[s], s.old, s.new))}
     for nid, s in mech_of.items():
@@ -378,24 +328,6 @@ def build_stories(c: BoardContext, home: dict[str, str] | None = None,
                     finding_story=finding_story), details
 
 
-def _spans(x: _Ctx, nid: str) -> list[tuple]:
-    """A changed function's (file, before lines, after lines), from the diff map: a function defined twice in one file
-    (under #ifdef) is the definition that changed, not the first the facts list."""
-    n = x.im.nodes[nid]
-    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
-    if fb is None or fa is None:
-        return []
-    texts = x.texts
-    out = [(texts[d.file], d.before_lines, d.after_lines) for d in x.c.dm.functions
-           if d.qualname == fa.qualname and d.file in (fa.file, fb.file) and d.before_lines and d.after_lines
-           and d.file in texts]
-    own = [o for o in out if o[2][0] <= fa.start_line <= o[2][1]]     # overloads share a name: each reads its own span
-    out = own or out
-    if not out and fa.file in texts:
-        out = [(texts[fa.file], (fb.start_line, fb.end_line), (fa.start_line, fa.end_line))]
-    return out
-
-
 def _test_file(x: _Ctx, local: str) -> bool:
     """Test code by its workspace-relative path, as functions are (`is_test_path`)."""
     root = x.c.root.rstrip("/") + "/"
@@ -527,41 +459,6 @@ def _summary(mechs: list[_Draft], behaviour: list[_Draft], others: list[_Draft],
     return (", ".join(p for p in parts if p) or "No changed functions") + "."
 
 
-def _note(x: _Ctx, nid: str, mech_of: dict[str, Sub], fn_sites: dict[str, list[Site]], mech_subs: set) -> str:
-    """What changed in a node, in a few words."""
-    n = x.im.nodes[nid]
-    if nid not in x.changed:
-        return ""
-    if nid in mech_of:
-        s = mech_of[nid]
-        return f"{_q(s.new)} instead of {_q(s.old)}"
-    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
-    parts = []
-    if fb is None and fa is not None:
-        parts.append("new function")
-    elif fa is None and fb is not None:
-        parts.append("removed")
-    else:
-        ch = next((d for d in x.c.dm.functions if fa and d.file == fa.file and d.qualname == fa.qualname), None)
-        if ch is not None and ch.kind == "signature_changed":
-            parts.append("signature changed")
-    for status, verb in (("added", "now writes"), ("removed", "no longer writes")):
-        fields = [x.label(e.dst).split("::")[-1] for e in x.writes_from.get(nid, [])
-                  if e.status == status and e.dst in x.im.nodes]
-        if fields:
-            parts.append(f"{verb} {', '.join(dict.fromkeys(fields[:3]))}" + (f" +{len(fields) - 3}" if len(fields) > 3 else ""))
-    also = sorted({s.sub for s in fn_sites.get(nid, []) if s.sub in mech_subs}, key=lambda s: s.old)
-    if also:
-        parts.append("also " + ", ".join(f"{_q(s.old)} → {_q(s.new)}" for s in also[:2]))
-    if not parts:
-        add = rem = 0
-        for fc, _, (a0, a1) in _spans(x, nid):
-            a, r = _count(fc.before, fc.after, a0, a1)
-            add, rem = add + a, rem + r
-        parts.append(f"+{add} −{rem} lines" if add or rem else "layout only")
-    return "; ".join(parts)
-
-
 def _landing_note(impacts: list[Impact], nid: str) -> str:
     i = next((i for i in impacts if i.node == nid and i.landing), None)
     if i is None:
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_pieces.py -q`
Expected: PASS: `10 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `466 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_pieces.py backend/codetortoise/pieces.py backend/codetortoise/repeated.py backend/codetortoise/stories.py
git commit -m "feat(pieces): the change cut into pieces that never span targets or CLs, typed links, evidence cards and an overview"
```

### Task 3: Stories are groups of pieces; the rules' plan; the pieces and stories stages

Spec §6, §7.1. A **plan** (`grouping.py`) says which pieces form which story: `PlannedStory` has the placements (piece, reason, evidence, quote), the tier-1 title, purpose, checks, questions and related keys, its source, and whether it is the Unsorted story. `rules_plan` is §6:
- pieces join on a `call` link of at least 2 or a `field` link, within one target and one CL;
- tests and repeated edits group per target (and substitution);
- a declaration piece joins the group that uses its changes most.

`stories.build_stories` now takes a plan (the rules' plan when none is given) and builds one draft per planned story: Unsorted; all repeated edits → mechanical; with flows → behaviour; all tests → tests; otherwise other. A finding goes to the story of its flow, then its node, its field's writer, a node on a story's flow, then its evidence file's piece (declarations first); otherwise no story. Past `max_stories`, the rules' Other stories merge only within one target and CL set. `Story` gains `targets`, `pieces`, `placements`, `purpose`, `check`, `questions`, `related`, `source`, and kind `unsorted`.

Two stages come after `detectors`. **pieces** resolves targets, builds the pieces and stores the `pieces` blob. **stories** forms the plan; for now it is always the rules' plan, and Task 6 adds the strong model. The board stage hands the plan to `build_stories`. Two e2e expectations change, because fixture story S1 is now drawn from both CLs.

**Files:**
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_stories.py`
- Test: `backend/tests/test_web.py`
- Test: `frontend/e2e/workspace-story.spec.ts`
- Test: `frontend/e2e/workspace.spec.ts`
- Create: `backend/codetortoise/grouping.py`
- Modify: `backend/codetortoise/pieces.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/stories.py`

**Interfaces:**
- Consumes: `PieceSet`, `build_pieces`, `find_repeated` (Task 2); `resolve_targets` (Task 1).
- Produces: `grouping.REASONS`, `grouping.RULE_REASONS`, `grouping.Placement(piece, reason, evidence=[], quote=[])`,
  `grouping.PlannedStory(key, title="", purpose="", check=[], questions=[], related=[], placements=[], source="rules", unsorted=False)` with `.pieces -> list[str]`,
  `grouping.StoryPlan(stories=[], notes=[])`, `grouping.rules_plan(ps, only=None, prefix="r") -> list[PlannedStory]`;
  `stories.build_stories(c, home=None, analysis=None, plan: StoryPlan | None = None, pieces: PieceSet | None = None, rep=None)`;
  pipeline stages `pieces` and `stories` (ctx keys `pieces`, `repeated`, `analysis`, `plan`); `pipeline.board_context(notes)` inside `run_review`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pipeline.py` (diff):

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 723f2a4..19b0452 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -16,8 +16,13 @@ def test_full_review_without_llm_or_swarm(fx, tmp_path):
     rid = svc.store.create_review("t", "owner", [101, 102])
     run_review(rid, svc)
     assert stages(svc, rid) == {"ingest": "ok", "swarm_read": "degraded", "diffmap": "ok", "tu_select": "ok",
-                                "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok", "verdicts": "ok",
-                                "board": "ok", "llm": "degraded", "finalize": "ok"}
+                                "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok", "pieces": "ok",
+                                "stories": "ok", "verdicts": "ok", "board": "ok", "llm": "degraded", "finalize": "ok"}
+    msgs = {s["name"]: s["message"] for s in svc.store.list_stages(rid)}
+    assert msgs["pieces"].endswith("target(s): compile_commands")
+    assert msgs["stories"].endswith("by the rules")
+    ss = svc.store.get_blob(rid, "stories")
+    assert all(s["targets"] == ["compile_commands"] and s["pieces"] for s in ss["stories"])
     review = svc.store.get_review(rid)
     assert review["status"] == "degraded" and review["risk"] == "high"
     assert len(svc.store.list_findings(rid)) == 6
```

`backend/tests/test_stories.py` (diff):

```diff
diff --git a/backend/tests/test_stories.py b/backend/tests/test_stories.py
index b0e5d45..f1c6c38 100644
--- a/backend/tests/test_stories.py
+++ b/backend/tests/test_stories.py
@@ -433,12 +433,12 @@ def test_a_finding_on_the_flows_of_two_stories_is_in_the_riskier_one_only():
 
 def test_other_changes_spread_over_the_workspace_are_named_by_their_main_directories():
     c = _world([_edit("a1", "deps/pcre/a.c"), _edit("a2", "deps/pcre/b.c"), _edit("b1", "src/util/c.c"),
-                _edit("top", "main.c")], calls=[("a1", "a2"), ("a2", "b1"), ("b1", "top")])
+                _edit("top", "main.c")], calls=[("a1", "a2"), ("a2", "b1"), ("b1", "top")] * 2)    # joined: 2 calls each
     ss, _ = build_stories(c)
     (o,) = ss.stories
-    assert o.title == "Other changes in `deps/pcre`, `src/util` and 1 more directory"
+    assert o.title == "Other changes in `deps/pcre`, `the workspace root` and 1 more directory"
     assert "/w" not in o.title
-    c = _world([_edit("top", "main.c"), _edit("top2", "main2.c")], calls=[("top", "top2")])
+    c = _world([_edit("top", "main.c"), _edit("top2", "main2.c")], calls=[("top", "top2")])     # one directory
     assert build_stories(c)[0].stories[0].title == "Other changes in `the workspace root`"
 
 
@@ -475,3 +475,91 @@ def test_a_story_names_the_changelists_of_the_code_behind_its_flows_and_of_sites
     (m,) = _by_kind(ss, "mechanical")
     assert b.nodes == [] and b.cls == [1]                  # no functions of its own: the CL of the edit behind its flows
     assert m.cls == [1, 2, 4]                              # the header holds a site and no function
+
+
+# ---- stories from pieces (spec 2026-10-05-two-tier-stories §6, §7.1)
+def _in_cls(c, by_file, descriptions=None):
+    from codetortoise.vcs.model import ClMeta, PerClText
+    for f in c.cs.files:
+        f.per_cl = [PerClText(cl=by_file[f.local[len(W) + 1:]], before=f.before, after=f.after)]
+    c.cs.cls = [ClMeta(cl=n, status="pending", description=(descriptions or {}).get(n, ""))
+                for n in sorted(set(by_file.values()))]
+    return c
+
+
+
+def test_the_rules_join_pieces_by_two_calls_or_a_field_within_one_target_and_cl():
+    c = _world([_edit("ref_add", "deps/ref/a.c"), _edit("ref_io", "deps/ref/io/b.c"), _edit("ref_log", "deps/ref/log/c.c"),
+                _edit("clar_path", "deps/clar/s.c"), _edit("clar_run", "deps/clar/r/t.c")],
+               calls=[("ref_add", "ref_io"), ("ref_add", "ref_io"), ("ref_add", "ref_log"), ("ref_add", "clar_path"),
+                      ("ref_add", "clar_path"), ("clar_run", "clar_path"), ("clar_run", "clar_path")])
+    _in_cls(c, {"deps/ref/a.c": 11, "deps/ref/io/b.c": 11, "deps/ref/log/c.c": 11, "deps/clar/s.c": 12,
+                "deps/clar/r/t.c": 12})
+    ss, _ = build_stories(c)
+    label = {n: x.label for n, x in c.impact.nodes.items()}
+    groups = sorted(sorted(label[n] for n in s.nodes) for s in ss.stories)
+    assert groups == [["clar_path", "clar_run"], ["ref_add", "ref_io"], ["ref_log"]]   # one call: apart; CL 12: apart
+    assert all(s.source == "rules" and s.targets == ["unknown"] for s in ss.stories)
+    s = next(s for s in ss.stories if "N2" in s.nodes)
+    assert [(p.reason, p.evidence) for p in s.placements] == [("starts_purpose", []), ("linked", [s.pieces[0]])]
+
+
+def test_a_header_joins_the_story_using_it_most_and_its_finding_goes_there_by_file():
+    from codetortoise.detectors.base import Evidence, Finding
+    from codetortoise.diffmap import TypeChange
+    from codetortoise.vcs.model import FileChange
+    c = _world([("pd_get", "src/pd.c", ["a = 0;"], ["a = 0;", "use(PD_DIR);"]),
+                ("pd_set", "src/pd.c", ["b = 1;"], ["b = 1;", "set(PD_DIR, b);"]), _edit("stack_add", "deps/ref/s.c")],
+               calls=[("pd_set", "pd_get")])
+    h = f"{W}/src/sysdir.h"
+    c.cs.files.append(FileChange(depot="//d" + h, local=h, action="edit", before="\n", after="#define PD_DIR 1\n"))
+    _in_cls(c, {"src/pd.c": 12, "deps/ref/s.c": 11, "src/sysdir.h": 12})
+    c.dm.types.append(TypeChange(file=h, depot="//d" + h, name="PD_DIR", kind="macro_added"))
+    c.findings = [Finding(id="F1", kind="header_fanout", severity="low", title="sysdir.h: 1 change(s) reach 0 TU(s)",
+                          summary="s", evidence=[Evidence(text="macro added: PD_DIR", file=h)]),
+                  Finding(id="F2", kind="k", severity="low", title="t", summary="s",
+                          evidence=[Evidence(text="x", file="/elsewhere.c")])]
+    ss, det = build_stories(c)
+    pd = next(s for s in ss.stories if "N1" in s.nodes)
+    assert pd.findings == ["F1"] and pd.cls == [12] and len(pd.pieces) == 2
+    assert pd.placements[-1].reason == "declaration_used"
+    assert "F2" not in ss.finding_story                       # no node and no file of the change: no story
+    assert all("F1" not in s.findings for s in ss.stories if s.id != pd.id)
+
+
+def test_other_changes_over_the_limit_merge_only_within_a_target_and_cl():
+    from codetortoise.config import AnalysisConfig
+    fns = [_edit(f"f{i}", f"d/x{i}.c") for i in range(6)]
+    c = _world(fns, cfg=AnalysisConfig(max_stories=2))
+    _in_cls(c, {f"d/x{i}.c": 11 if i < 3 else 12 for i in range(6)})
+    ss, _ = build_stories(c)
+    assert len(ss.stories) == 2 and sorted(s.cls for s in ss.stories) == [[11], [12]]
+
+
+def test_a_plan_from_tier_1_gives_titles_purposes_checks_related_stories_and_an_unsorted_story_last():
+    from codetortoise.board import analyse
+    from codetortoise.grouping import Placement, PlannedStory, StoryPlan
+    from codetortoise.pieces import build_pieces
+    c = _world([_edit("modem_tx", "modem/tx.c"), _edit("modem_rx", "modem/rx.c"), _edit("dsp_run", "dsp/run.c")])
+    a = analyse(c)
+    t = {f"{W}/modem/tx.c": ["modem"], f"{W}/modem/rx.c": ["modem"], f"{W}/dsp/run.c": ["dsp"]}
+    ps = build_pieces(c, a, t)
+    pid = {c.impact.nodes[p.nodes[0]].label: p.id for p in ps.pieces}
+    plan = StoryPlan(stories=[
+        PlannedStory(key="a", title="Modem radio gains band 71", purpose="Adds band 71 to the modem's radio.",
+                     check=["Check the band tables."], questions=["Is band 71 licensed here?"], related=["b"], source="tier1",
+                     placements=[Placement(piece=pid["modem_tx"], reason="starts_purpose"),
+                                 Placement(piece=pid["modem_rx"], reason="same_feature", evidence=[pid["modem_tx"]])]),
+        PlannedStory(key="b", title="", purpose="DSP side.", source="tier1",
+                     placements=[Placement(piece=pid["dsp_run"], reason="starts_purpose")]),
+        PlannedStory(key="u", unsorted=True, source="tier1", placements=[])])
+    ss, det = build_stories(c, analysis=a, plan=plan, pieces=ps)
+    s1, s2, s3 = ss.stories
+    assert (s1.kind, s1.title, s1.text_source, s1.summary) == ("other", "Modem radio gains band 71", "llm",
+                                                               "Adds band 71 to the modem's radio.")
+    assert s1.targets == ["modem"] and s1.check == ["Check the band tables."] and s1.questions == ["Is band 71 licensed here?"]
+    assert s1.related == [s2.id] and s1.source == "tier1"
+    assert [p.reason for p in s1.placements] == ["starts_purpose", "same_feature"]
+    assert s2.title == "Other changes in `dsp`" and s2.purpose == "DSP side." and s2.targets == ["dsp"]   # its title failed
+    assert (s3.kind, s3.title) == ("unsorted", "Unsorted: needs a person to place these")
+    assert det[s3.id].graph is not None
```

`backend/tests/test_web.py` (diff):

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index e8b9e8c..8b59a75 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -67,7 +67,7 @@ def test_owner_creates_review_others_view_and_comment(env):
     assert r.status_code == 200 and r.json()["title"] == "CLs 101, 102"
     rid = r.json()["id"]
     detail = bob.get(f"/api/reviews/{rid}").json()
-    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 12
+    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 14
     assert detail["review"]["risk"] == "high"
     # the raw storyboard and impact graph are not served: the board replaced them (spec §14.4)
     assert bob.get(f"/api/reviews/{rid}/storyboard").status_code == 404
```

`frontend/e2e/workspace-story.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace-story.spec.ts b/frontend/e2e/workspace-story.spec.ts
index 7300d17..a23aa27 100644
--- a/frontend/e2e/workspace-story.spec.ts
+++ b/frontend/e2e/workspace-story.spec.ts
@@ -14,7 +14,7 @@ test.describe("desktop", () => {
     await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
     await expect(page.locator(".ws-story-head h2")).toContainText("uart_send can now return -2");
     await expect(page.getByRole("tab", { name: "Steps" })).toHaveAttribute("aria-selected", "true");
-    await expect(page.locator(".ws-story-meta .ws-chip:not(.ws-onmap)")).toHaveText(["CL 101"]);
+    await expect(page.locator(".ws-story-meta .ws-chip:not(.ws-onmap)")).toHaveText(["CL 101", "CL 102"]);
     await step(page, "uart_send").click();
     await expect(page).toHaveURL(/\/s\/S1\?open=N\d+$/);
     await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
```

`frontend/e2e/workspace.spec.ts` (diff):

```diff
diff --git a/frontend/e2e/workspace.spec.ts b/frontend/e2e/workspace.spec.ts
index f57c42d..fd94ddf 100644
--- a/frontend/e2e/workspace.spec.ts
+++ b/frontend/e2e/workspace.spec.ts
@@ -14,14 +14,15 @@ test.describe("desktop", () => {
     const home = (await rail.locator(".ws-home").boundingBox())!, first = (await rail.locator(".ws-sec-t").first().boundingBox())!;
     expect(first.y - (home.y + home.height)).toBeLessThan(12);               // sections follow on: the grip takes no room
     const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
-    await expect(s1.locator(".ws-chip")).toHaveText(["CL 101"]);
+    await expect(s1.locator(".ws-chip")).toHaveText(["CL 101", "CL 102"]);     // CL 102's uart.h is used most by S1
 
     // the CL filter lights the stories drawn from it and dims the rest; again clears it
-    await rail.getByRole("button", { name: "Highlight the stories drawn from CL 102" }).click();
-    await expect(s1).toHaveClass(/\bdim\b/);
-    await expect(rail.getByRole("link", { name: /^Go to story S2/ })).not.toHaveClass(/\bdim\b/);
-    await rail.getByRole("button", { name: "Show every story" }).click();
+    const s2 = rail.getByRole("link", { name: /^Go to story S2/ });
+    await rail.getByRole("button", { name: "Highlight the stories drawn from CL 101" }).click();
+    await expect(s2).toHaveClass(/\bdim\b/);
     await expect(s1).not.toHaveClass(/\bdim\b/);
+    await rail.getByRole("button", { name: "Show every story" }).click();
+    await expect(s2).not.toHaveClass(/\bdim\b/);
 
     await s1.click();
     await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_stories.py tests/test_web.py -q`
Expected: FAIL: `7 failed, 69 passed`; the first error is `AssertionError: assert 'Other change...ore directory' == 'Other change...ore directory'`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-story.spec.ts e2e/workspace.spec.ts`
Expected: FAIL: `2 failed, 21 passed`; the first error is `Error: expect(locator).toHaveText(expected) failed`

- [ ] **Step 3: Implement**

`backend/codetortoise/grouping.py` (new file):

```python
"""Which pieces form which story (spec 2026-10-05-two-tier-stories §4.3, §6): the plan the strong model writes, or the
rules' plan without it. `stories.build_stories` turns a plan into the review's stories."""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.pieces import PieceSet

Reason = Literal["starts_purpose", "same_feature", "caller_of_new_code", "same_fix", "same_refactor", "shared_code",
                 "declaration_used", "split_too_big"]
REASONS: tuple[str, ...] = Reason.__args__                     # what the strong model may give
RULE_REASONS = ("linked", "tests", "repeated", "declaration_used", "starts_purpose")   # what the rules give


class Placement(BaseModel):
    piece: str
    reason: str                       # a Reason (tier 1), a rule's reason, or (unsorted) why it could not be placed
    evidence: list[str] = Field(default_factory=list)       # piece ids and CL numbers ("CL412") it relied on
    quote: list[str] = Field(default_factory=list)          # a cross-CL join without a link: one quote per CL


class PlannedStory(BaseModel):
    key: str
    title: str = ""                   # "" : the rules' title
    purpose: str = ""
    check: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)        # other stories' keys
    placements: list[Placement] = Field(default_factory=list)
    source: Literal["tier1", "rules"] = "rules"
    unsorted: bool = False            # pieces no story could take: a person places them

    @property
    def pieces(self) -> list[str]:
        return [p.piece for p in self.placements]


class StoryPlan(BaseModel):
    stories: list[PlannedStory] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)          # why part of it fell back to the rules


def rules_plan(ps: PieceSet, only: list[str] | None = None, prefix: str = "r") -> list[PlannedStory]:
    """§6: pieces join when a `call` link of at least 2 or a `field` link joins them, within one target and one CL;
    a declaration piece joins the group using its changes most; tests and repeated edits group per target (and
    substitution). `only` limits it to some pieces (a chunk tier 1 could not do)."""
    want = set(only) if only is not None else {p.id for p in ps.pieces}
    pieces = [p for p in ps.pieces if p.id in want]
    by_id = {p.id: p for p in pieces}
    parent = {p.id: p.id for p in pieces}
    rank = {p.id: i for i, p in enumerate(ps.pieces)}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    why: dict[str, tuple[str, list[str]]] = {}
    code = {"new", "edits", "single"}
    for lk in ps.links:
        a, b = by_id.get(lk.a), by_id.get(lk.b)
        if a is None or b is None or a.kind not in code or b.kind not in code:
            continue
        if a.targets != b.targets or a.cl != b.cl:
            continue
        if (lk.type == "call" and lk.count >= 2) or lk.type == "field":
            ra, rb = find(a.id), find(b.id)
            if ra != rb:
                lo, hi = sorted((ra, rb), key=rank.get)
                parent[hi] = lo
                why.setdefault(b.id if rank[b.id] > rank[a.id] else a.id,
                               ("linked", [a.id if rank[b.id] > rank[a.id] else b.id]))
    for p in pieces:
        if p.kind == "tests":
            parent[p.id] = next(q.id for q in pieces if q.kind == "tests" and q.targets == p.targets)
            why[p.id] = ("tests", [])
        elif p.kind == "repeated":
            parent[p.id] = next(q.id for q in pieces if q.kind == "repeated" and q.sub == p.sub and q.targets == p.targets)
            why[p.id] = ("repeated", [])
    groups: dict[str, list[str]] = defaultdict(list)
    for p in pieces:
        if p.kind != "declarations":
            groups[find(p.id)].append(p.id)
    for d in (p for p in pieces if p.kind == "declarations"):
        uses: dict[str, int] = defaultdict(int)
        for lk in ps.links_of(d.id):
            other = lk.b if lk.a == d.id else lk.a
            if lk.type == "uses" and other in by_id and by_id[other].kind in code:
                uses[find(other)] += lk.count
        if uses:
            into = max(uses, key=lambda g: (uses[g], -rank[g]))
            groups[into].append(d.id)
            user = max((o for o in groups[into] if o in by_id and by_id[o].kind in code),
                       key=lambda o: (sum(lk.count for lk in ps.links_of(d.id) if lk.type == "uses" and o in (lk.a, lk.b)),
                                      -rank[o]))
            why[d.id] = ("declaration_used", [user])
        else:
            groups[d.id].append(d.id)
    out = []
    for i, (_, ids) in enumerate(sorted(groups.items(), key=lambda kv: rank[kv[1][0]])):
        ids = sorted(ids, key=rank.get)
        places = []
        for j, pid in enumerate(ids):
            reason, ev = why.get(pid, ("starts_purpose", []))
            places.append(Placement(piece=pid, reason="starts_purpose" if j == 0 else reason, evidence=[] if j == 0 else ev))
        out.append(PlannedStory(key=f"{prefix}{i + 1}", placements=places))
    return out
```

`backend/codetortoise/pieces.py` (diff):

```diff
diff --git a/backend/codetortoise/pieces.py b/backend/codetortoise/pieces.py
index d18bb4e..a0cca5a 100644
--- a/backend/codetortoise/pieces.py
+++ b/backend/codetortoise/pieces.py
@@ -2,7 +2,7 @@
 2026-10-05-two-tier-stories §3). Rules only, no AI: both tiers start from these.
 
 A piece is a few changed nodes that are almost never wrong to keep together; pieces never span two targets or two CLs.
-Cut in order, each node going to the first piece that takes it: tests, repeated edits, new code with its direct
+Cut in order, each node going to the first piece that takes it: repeated edits, tests, new code with its direct
 callers, connected edits (at most 2 hops wide), declarations (one per changed header and CL), singles. Ids P1… follow
 target, CL, first file and first line, so the same change always gives the same pieces.
 """
@@ -241,21 +241,22 @@ def build_pieces(c: BoardContext, a: Analysis, targets: dict[str, list[str]],
             for g in fns - {f}:
                 adj[f][g] += 1
 
-    # 1. tests, by target, CL and directory
+    # 1. repeated edits, by substitution, target and CL (a test with the edit is one of its sites)
     groups: dict[tuple, list[str]] = defaultdict(list)
     for n in changed:
-        if x.is_test_path(n):
-            groups[(tkey(n), cl_of[n], posixpath.dirname(x.local(n) or ""))].append(n)
-    for nodes in groups.values():
-        add("tests", nodes)
-    # 2. repeated edits, by substitution, target and CL
-    groups = defaultdict(list)
-    for n in changed:
-        if n not in taken and n in rep.mech_of:
+        if n in rep.mech_of:
             s = rep.mech_of[n]
             groups[(s.old, s.new, tkey(n), cl_of[n])].append(n)
     for (old, new, _, _), nodes in groups.items():
         add("repeated", nodes, sub=[old, new])
+    # 2. tests, by target, CL and directory; test code causing a flow is cut with the code it changes
+    causes = {fl.cause or fl.path[-1] for fl in a.flows}
+    groups = defaultdict(list)
+    for n in changed:
+        if n not in taken and n not in causes and x.is_test_path(n):
+            groups[(tkey(n), cl_of[n], posixpath.dirname(x.local(n) or ""))].append(n)
+    for nodes in groups.values():
+        add("tests", nodes)
     # 3. new code with the changed functions calling into it, within a target and CL
     added = [n for n in changed if n not in taken and im.nodes[n].key in x.fa and im.nodes[n].key not in x.fb]
     groups = defaultdict(list)
```

`backend/codetortoise/pipeline.py` (diff):

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index a74a018..45b1416 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -10,28 +10,32 @@ from concurrent.futures import ThreadPoolExecutor
 from pathlib import Path
 
 from codetortoise import boardstore
-from codetortoise.board import BoardContext, build_boards
+from codetortoise.board import BoardContext, analyse, build_boards
 from codetortoise.detectors.base import DetectorContext, renumber, run_detectors
 from codetortoise.diffmap import map_changes
 from codetortoise.facts.model import Facts, relative_records
 from codetortoise.facts.runner import build_requests, parse_summary, run_extraction
+from codetortoise.grouping import StoryPlan, rules_plan
 from codetortoise.impact import ImpactModel, build_impact
 from codetortoise.llm.storyboard import AiContext, build_storyboard, judge_side_effects
 from codetortoise.paths import canon
+from codetortoise.pieces import build_pieces
 from codetortoise.provenance import finding_files, impact_node_files, local_files
+from codetortoise.repeated import find_repeated
 from codetortoise.services import Services
 from codetortoise.stories import build_stories
 from codetortoise.swarm import SwarmError
+from codetortoise.targets import resolve_targets
 from codetortoise.tu_select import TuSelection, field_follow_up, select_tus
 from codetortoise.vcs.model import ChangeSet
 
 log = logging.getLogger(__name__)
 
-STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "verdicts", "board",
-          "llm", "finalize"]
+STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "pieces", "stories",
+          "verdicts", "board", "llm", "finalize"]
 DEPS = {"swarm_read": ["ingest"], "diffmap": ["ingest"], "tu_select": ["diffmap"], "facts": ["tu_select"],
-        "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "verdicts": ["detectors"],
-        "board": ["impact", "detectors"],
+        "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "pieces": ["impact", "detectors"],
+        "stories": ["pieces"], "verdicts": ["detectors"], "board": ["impact", "detectors"],
         "llm": ["detectors"]}
 
 
@@ -217,6 +221,37 @@ def run_review(rid: int, svc: Services) -> None:
         store.put_findings(rid, findings)
         return f"{len(findings)} finding(s)"
 
+    def board_context(notes: list[str]) -> BoardContext:
+        resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
+        return BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
+                            ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root)))
+
+    def pieces():
+        """The change cut into pieces, by target and CL, with links and cards (spec 2026-10-05-two-tier-stories §3)."""
+        bctx = board_context([])
+        a = analyse(bctx)
+        rep = find_repeated(bctx, a.x)
+        files = sorted({f.local for f in ctx["cs"].files if f.local} | {t.file for t in ctx["dm"].types})
+
+        def triple(f: str) -> str | None:
+            g = svc.toolchain.group_of(f)
+            return g.target if g else None
+        ws = cfg.workspace
+        targets = resolve_targets(files, cfg.targets, bctx.root, svc.cdb, str(ws.build_root) if ws.build_root else None,
+                                  triple, svc.index.transitive_includers)
+        ps = build_pieces(bctx, a, targets, svc.index.transitive_includers, rep)
+        ctx["pieces"], ctx["repeated"] = ps, rep
+        store.put_blob(rid, "pieces", ps)
+        names = sorted({t for p in ps.pieces for t in p.targets})
+        return f"{len(ps.pieces)} piece(s), {len(ps.links)} link(s); target(s): {', '.join(names) or 'none'}"
+
+    def stories():
+        """Which pieces form which story: the rules' grouping (spec §6)."""
+        ps = ctx["pieces"]
+        plan = StoryPlan(stories=rules_plan(ps))
+        ctx["plan"] = plan
+        return f"{len(plan.stories)} stories from {len(ps.pieces)} piece(s), by the rules"
+
     def verdicts():
         """The AI judges side effects before the board is drawn, so flows and stories take the verdicts' colours."""
         findings = ctx["findings"]
@@ -238,12 +273,12 @@ def run_review(rid: int, svc: Services) -> None:
 
     def board():
         notes: list[str] = []
-        resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
-        bctx = BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
-                            ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root)))
+        bctx = board_context(notes)
+        resolve = bctx.depots_for
         bs = build_boards(bctx)
         try:                                   # change stories (spec 2026-10-04); the boards stand without them
-            bs.stories, bs.story_details = build_stories(bctx, bs.home or None, bs.analysis)
+            bs.stories, bs.story_details = build_stories(bctx, bs.home or None, bs.analysis, plan=ctx.get("plan"),
+                                                         pieces=ctx.get("pieces"), rep=ctx.get("repeated"))
         except Exception as e:
             notes.append(f"stories failed: {type(e).__name__}: {e}")
         # file tags (spec §14.3): every graph node and finding, from one more lookup of the files not yet resolved
@@ -311,7 +346,8 @@ def run_review(rid: int, svc: Services) -> None:
         store.put_blob(rid, "file_summaries", {})       # they describe the old diff
         for name, fn in [("ingest", ingest), ("swarm_read", swarm_read), ("diffmap", diffmap), ("tu_select", tu_select),
                          ("layers", layers), ("facts", facts), ("impact", impact), ("detectors", detectors),
-                         ("verdicts", verdicts), ("board", board), ("llm", llm), ("finalize", finalize)]:
+                         ("pieces", pieces), ("stories", stories), ("verdicts", verdicts), ("board", board), ("llm", llm),
+                         ("finalize", finalize)]:
             stage(name, fn)
 
 
```

`backend/codetortoise/stories.py` (diff):

```diff
diff --git a/backend/codetortoise/stories.py b/backend/codetortoise/stories.py
index def686c..7f73912 100644
--- a/backend/codetortoise/stories.py
+++ b/backend/codetortoise/stories.py
@@ -8,7 +8,7 @@ board of every node it mentions (for its steps and code) and a graph of at most
 from __future__ import annotations
 
 import posixpath
-from collections import Counter, defaultdict, deque
+from collections import Counter, defaultdict
 from typing import Literal
 
 from pydantic import BaseModel, Field
@@ -31,13 +31,14 @@ from codetortoise.board import (
     analyse,
     is_test_path,
 )
-from codetortoise.clusters import _shared, altered_access, cluster_change
+from codetortoise.clusters import _shared, altered_access
 from codetortoise.detectors.base import SEVERITY_RANK
-from codetortoise.impact import ImpactModel
-from codetortoise.repeated import _note, _plural, _q, find_repeated
+from codetortoise.grouping import Placement, PlannedStory, StoryPlan, rules_plan
+from codetortoise.pieces import Piece, PieceSet, build_pieces
+from codetortoise.repeated import Repeated, _note, _plural, _q, find_repeated
 from codetortoise.substitutions import Site, Sub
 
-Kind = Literal["behaviour", "other", "mechanical", "tests"]
+Kind = Literal["behaviour", "other", "mechanical", "tests", "unsorted"]
 RISK = {3: "high", 2: "medium", 1: "low"}
 NEIGHBOURS = 4                                               # unchanged code a story graph shows beside its own
 
@@ -88,6 +89,15 @@ class Story(BaseModel):
     subs: list[list[str]] = Field(default_factory=list)     # "N more repeated edits": each substitution
     collapsed: bool = False                                 # a behaviour story past the list's limit
     cls: list[int] = Field(default_factory=list)            # the changelists of the files holding its code
+    # spec 2026-10-05-two-tier-stories §7.1: the pieces it groups and why, and (tier 1) what it is for
+    targets: list[str] = Field(default_factory=list)        # the build targets of its code
+    pieces: list[str] = Field(default_factory=list)
+    placements: list[Placement] = Field(default_factory=list)
+    purpose: str = ""
+    check: list[str] = Field(default_factory=list)          # what a reviewer should check
+    questions: list[str] = Field(default_factory=list)      # open questions
+    related: list[str] = Field(default_factory=list)        # related stories' ids
+    source: Literal["tier1", "rules"] = "rules"             # who grouped it
 
 
 class StoryDetail(BaseModel):
@@ -118,6 +128,8 @@ class _Draft:
         self.subs: list[Sub] = []
         self.name = ""
         self.collapsed = False
+        self.plan: PlannedStory | None = None
+        self.pieces: list[Piece] = []
 
     def rank(self, sev: dict[str, str]) -> tuple:
         f = max((SEVERITY_RANK.get(sev.get(i, "info"), 0) for i in self.findings), default=0)
@@ -130,11 +142,13 @@ class _Draft:
         return RISK.get(top)
 
 
-def build_stories(c: BoardContext, home: dict[str, str] | None = None,
-                  analysis: Analysis | None = None) -> tuple[StorySet, dict[str, StoryDetail]]:
-    """The review's stories and each story's detail. `home` maps nodes to the cluster boards holding them; `analysis`
-    is the boards' (`BoardSet.analysis`), so stories and boards tell the same flows. Stories work on copies: the AI
-    pass later rewrites the boards' flows and summary in place."""
+def build_stories(c: BoardContext, home: dict[str, str] | None = None, analysis: Analysis | None = None,
+                  plan: StoryPlan | None = None, pieces: PieceSet | None = None,
+                  rep: Repeated | None = None) -> tuple[StorySet, dict[str, StoryDetail]]:
+    """The review's stories and each story's detail, from a plan grouping the change's pieces (the strong model's, or
+    the rules' when `plan` is None; spec 2026-10-05-two-tier-stories §6). `home` maps nodes to the cluster boards
+    holding them; `analysis` is the boards' (`BoardSet.analysis`), so stories and boards tell the same flows. Stories
+    work on copies: the AI pass later rewrites the boards' flows and summary in place."""
     a = analysis or analyse(c)
     x = a.x
     impacts = [i.model_copy(deep=True) for i in a.impacts]
@@ -142,95 +156,77 @@ def build_stories(c: BoardContext, home: dict[str, str] | None = None,
     about = a.about.model_copy(deep=True)
     im, cfg = x.im, c.cfg
     sev = {f.id: f.severity for f in c.findings}
-    changed = [n for n in im.changed if n in im.nodes]
     is_test = x.is_test_path
 
-    # 1. substitutions: in each changed function, and outside functions
-    rep = find_repeated(c, x)
-    fn_sites, outside, count, mech_subs, mech_of = rep.fn_sites, rep.outside, rep.count, rep.mech_subs, rep.mech_of
-
-    mech = {s: _Draft("mechanical", sub=s) for s in sorted(mech_subs, key=lambda s: (-count[s], s.old, s.new))}
-    for nid, s in mech_of.items():
-        mech[s].members.append(nid)
-    for nid, sites in fn_sites.items():
-        for s in sites:
-            if s.sub in mech:
-                mech[s.sub].sites.append((s, x.local(nid) or "", nid))
-    for s, local in outside:
-        if s.sub in mech:
-            mech[s.sub].sites.append((s, local, None))
-
-    # 2. behaviour seeds: a flow-causing function's flows; a repeated edit's flows
-    seeds: dict[object, _Draft] = {}
+    # 1. substitutions and pieces (shared with the pieces stage), and the plan grouping the pieces
+    rep = rep or find_repeated(c, x)
+    fn_sites, outside, mech_of = rep.fn_sites, rep.outside, rep.mech_of
+    pieces = pieces or build_pieces(c, a, {}, rep=rep)
+    plan = plan or StoryPlan(stories=rules_plan(pieces))
+    by_id = {p.id: p for p in pieces.pieces}
+    sub_of = {(s.old, s.new): s for s in rep.mech_subs}
+    flows_of: dict[str, list[Flow]] = defaultdict(list)
+    for fl in flows:
+        flows_of[fl.cause or fl.path[-1]].append(fl)
+
+    # 2. each planned story is a draft: unsorted; only repeated edits (mechanical); with flows (behaviour); only tests
+    planned: list[_Draft] = []
+    for g in plan.stories:
+        mine = [by_id[pid] for pid in g.pieces if pid in by_id]
+        nodes = [n for p in mine for n in p.nodes]
+        repeated = bool(mine) and all(p.kind == "repeated" for p in mine)
+        fls = [] if repeated else [fl for n in nodes for fl in flows_of.get(n, [])]
+        kind = ("unsorted" if g.unsorted else "mechanical" if repeated else "behaviour" if fls
+                else "tests" if mine and all(p.kind == "tests" for p in mine) else "other")
+        d = _Draft(kind, members=nodes, flows=fls)
+        d.plan, d.pieces = g, mine
+        if kind == "behaviour":
+            top = min(fls, key=lambda fl: (-SEVERITY_RANK.get(fl.severity, 0), flows.index(fl)))
+            d.cause = top.cause or top.path[-1]
+        if kind == "mechanical":
+            subs = list(dict.fromkeys(sub_of[tuple(p.sub)] for p in mine if p.sub and tuple(p.sub) in sub_of))
+            d.sub, d.subs = (subs[0], []) if len(subs) == 1 else (None, subs)
+        planned.append(d)
+    mechs = [d for d in planned if d.kind == "mechanical"]
+    claimed: set[Sub] = set()                                 # a substitution's sites are told by its first story
+    for d in mechs:
+        own = ({d.sub} if d.sub else set(d.subs)) - claimed
+        claimed |= own
+        for nid, sites in fn_sites.items():
+            d.sites += [(s, x.local(nid) or "", nid) for s in sites if s.sub in own]
+        d.sites += [(s, local, None) for s, local in outside if s.sub in own]
+    # what a repeated edit changes: flows caused by its functions, one behaviour story per substitution
+    mech_member = {n for d in mechs for n in d.members}
+    seeds: dict[Sub, _Draft] = {}
     for fl in flows:
         cause = fl.cause or fl.path[-1]
-        key = ("mech", mech_of[cause]) if cause in mech_of else ("cause", cause)
-        if key not in seeds:
-            seeds[key] = (_Draft("behaviour", sub=key[1]) if key[0] == "mech"
-                          else _Draft("behaviour", members=[cause], cause=cause))
-        seeds[key].flows.append(fl)
-        if key[0] == "mech" and cause not in seeds[key].members:
-            seeds[key].members.append(cause)
-    for d in seeds.values():
+        if cause in mech_member and cause in mech_of:
+            d = seeds.setdefault(mech_of[cause], _Draft("behaviour", sub=mech_of[cause]))
+            d.flows.append(fl)
+            if cause not in d.members:
+                d.members.append(cause)
+    behaviour = [d for d in planned if d.kind == "behaviour"] + list(seeds.values())
+    for d in behaviour:
         d.findings = sorted({f for fl in d.flows for f in fl.findings})
-    taken: set[str] = set()                                   # a finding on two seeds' flows goes with the riskier
-    for d in sorted(seeds.values(), key=lambda d: d.rank(sev)):
+    taken: set[str] = set()                                   # a finding on two stories' flows goes with the riskier
+    for d in sorted(behaviour, key=lambda d: d.rank(sev)):
         d.findings = [f for f in d.findings if f not in taken]
         taken |= set(d.findings)
-
-    # 3. join the rest of the changed code to the nearest seed; "Other changes" for what no seed reaches
-    seeded = {d.cause for d in seeds.values() if d.cause}
-    tests = [n for n in changed if is_test(n) and n not in mech_of and n not in seeded]   # test code causing a flow: its story
-    rest = [n for n in changed if n not in mech_of and n not in seeded and n not in tests]
-    walk = set(rest) | seeded
-    adj: dict[str, set[str]] = defaultdict(set)
-    for e in im.edges:
-        if e.kind in ("call", "virtual") and e.src in walk and e.dst in walk:
-            adj[e.src].add(e.dst)
-            adj[e.dst].add(e.src)
-    by_field: dict[str, set[str]] = defaultdict(set)
-    for e in im.edges:
-        if altered_access(e) and e.src in walk:
-            by_field[e.dst].add(e.src)
-    for fns in by_field.values():
-        for a in fns:
-            adj[a] |= fns - {a}
-    seed_list = sorted((d for d in seeds.values() if d.cause), key=lambda d: d.rank(sev))
-    best: dict[str, tuple[int, int]] = {}                   # node -> (hops, seed index)
-    queue = deque()
-    for i, d in enumerate(seed_list):
-        best[d.cause] = (0, i)
-        queue.append(d.cause)
-    while queue:
-        n = queue.popleft()
-        hops, i = best[n]
-        for m in sorted(adj[n]):
-            if m not in best or (hops + 1, i) < best[m]:
-                if m not in best:
-                    queue.append(m)
-                best[m] = (hops + 1, i)
-    for n in rest:
-        if n in best:
-            seed_list[best[n][1]].members.append(n)
-    unreached = [n for n in rest if n not in best]
-    others: list[_Draft] = []
-    if unreached:
-        sub_im = ImpactModel(nodes=im.nodes, edges=im.edges, changed=unreached, blast=[])
-        res = cluster_change(sub_im, [], [], is_test=lambda _: False, module_of=x.module_of, max_nodes=cfg.board_max_nodes,
-                             min_changed=cfg.cluster_min_changed, max_clusters=10 ** 6)     # split as boards are
-        for cl in res.clusters:
-            others.append(_Draft("other", members=list(cl.members)))
-    test_story = _Draft("tests", members=tests) if tests else None
-
-    behaviour = list(seeds.values())
-    drafts = behaviour + others + list(mech.values()) + ([test_story] if test_story else [])
-    node_draft: dict[str, _Draft] = {n: d for d in drafts if d.kind != "behaviour" or d.cause for n in d.members}
-    for nid, s in mech_of.items():
-        node_draft[nid] = mech[s]
-
-    # 4. findings: the story of their flow, else of their first node with a story
-    flow_draft = {fl.id: d for d in behaviour for fl in d.flows}
-    taken = {f for d in behaviour for f in d.findings}
+    others = [d for d in planned if d.kind == "other"]
+    tests = [d for d in planned if d.kind == "tests"]
+    unsorted = [d for d in planned if d.kind == "unsorted"]
+    drafts = behaviour + others + mechs + tests + unsorted
+    node_draft: dict[str, _Draft] = {n: d for d in drafts if d.kind != "behaviour" or d.cause or d.plan
+                                     for n in d.members}
+
+    # 3. findings: the story of their flow, else of their first node with a story (or on its flows), else of the piece
+    #    holding their file
+    flow_draft = {fl.id: d for d in behaviour + unsorted for fl in d.flows}
+    piece_draft = {p.id: d for d in drafts for p in d.pieces}
+    file_piece: dict[str, str] = {}
+    for p in sorted(pieces.pieces, key=lambda p: p.kind != "declarations"):   # a header's findings: its declarations
+        for f in p.files:
+            file_piece.setdefault(f, p.id)
     for f in c.findings:
         if f.id in taken:
             continue
@@ -243,62 +239,81 @@ def build_stories(c: BoardContext, home: dict[str, str] | None = None,
             elif n in im.nodes and im.nodes[n].kind == "field":
                 d = next((node_draft[e.src] for e in im.edges if e.dst == n and altered_access(e) and e.src in node_draft),
                          None)
-        d = d or (drafts[0] if drafts else None)
-        if d is not None:
+            d = d or next((b for b in behaviour if any(n in fl.path for fl in b.flows)), None)   # on a story's flow
+        for e in f.evidence:
+            if d is not None:
+                break
+            d = piece_draft.get(file_piece.get(e.file or "", ""))
+        if d is not None:                                     # none: the finding stays in the review's list only
             d.findings.append(f.id)
 
-    # 5. order and the list's limit
+    # 4. order and the list's limit; the rules' "Other changes" merge by directory within a target and CL
     behaviour.sort(key=lambda d: d.rank(sev))
     others.sort(key=lambda d: d.rank(sev))
-    mechs = list(mech.values())
     cap = cfg.max_stories
 
     def total() -> int:
-        return len(behaviour) + len(others) + len(mechs) + (1 if test_story else 0)
+        return len(behaviour) + len(others) + len(mechs) + len(tests) + len(unsorted)
 
     def home_dir(d: _Draft) -> str:
-        return Counter(posixpath.dirname(x.local(m) or "") for m in d.members).most_common(1)[0][0]
-
-    while total() > cap and len(others) > 1:                 # the least risky "Other changes" merge by directory
-        small = others.pop()
-        into = max(others, key=lambda o: (len(_shared(home_dir(o), home_dir(small))), -others.index(o)))
+        return Counter(posixpath.dirname(x.local(m) or "") for m in d.members).most_common(1)[0][0] if d.members else ""
+
+    def scope(d: _Draft) -> tuple:
+        return (tuple(sorted({t for p in d.pieces for t in p.targets})), tuple(sorted({p.cl or 0 for p in d.pieces})))
+    while total() > cap:
+        mergeable = [o for o in others if o.plan is None or o.plan.source == "rules"]
+        pair = next(((small, [o for o in mergeable if o is not small and scope(o) == scope(small)])
+                     for small in reversed(mergeable) if any(o is not small and scope(o) == scope(small) for o in mergeable)),
+                    None)
+        if pair is None:
+            break
+        small, into_any = pair
+        into = max(into_any, key=lambda o: (len(_shared(home_dir(o), home_dir(small))), -others.index(o)))
+        others.remove(small)
         into.members += small.members
         into.findings += small.findings
+        into.pieces += small.pieces
+        into.plan.placements += small.plan.placements
     if total() > cap and len(mechs) > 1:                     # the smallest repeated edits fold into one story
         keep = max(1, len(mechs) - (total() - cap) - 1)
         folded = _Draft("mechanical")
+        folded.plan = PlannedStory(key="folded", placements=[])
         for d in mechs[keep:]:
             folded.members += d.members
             folded.sites += d.sites
             folded.findings += d.findings
-            folded.subs.append(d.sub)
+            folded.subs += [d.sub] if d.sub else d.subs
+            folded.pieces += d.pieces
+            folded.plan.placements += d.plan.placements if d.plan else []
         mechs = mechs[:keep] + [folded]
-    if total() > cap:                                        # behaviour stories are never merged: collapse the rest
-        room = max(0, cap - (total() - len(behaviour)) - 1)  # "N more behaviour stories" is one entry too
-        for d in behaviour[room:]:
+    if total() > cap:                                        # stories with a purpose are never merged: collapse the rest
+        purposeful = behaviour + [o for o in others if o.plan is not None and o.plan.source == "tier1"]
+        room = max(0, cap - (total() - len(purposeful)) - 1)  # "N more stories" is one entry too
+        for d in purposeful[room:]:
             d.collapsed = True
 
     for d in others:                                         # "in <directory>"; alike ones add their first function
-        d.name = _dir_name(x, d.members, c.root)
+        d.name = _dir_name(x, d.members, c.root, [f for p in d.pieces for f in p.files])
     alike = Counter(d.name for d in others)
     for d in others:
-        if alike[d.name] > 1:
+        if alike[d.name] > 1 and d.members:
             d.name += f" ({_q(x.label(d.members[0]))})"
-    ordered = behaviour + others + mechs + ([test_story] if test_story else [])
+    ordered = behaviour + others + mechs + tests + unsorted
     ids = {id(d): f"S{i + 1}" for i, d in enumerate(ordered)}
 
-    # 6. the stories, their boards and graphs
+    # 5. the stories, their boards and graphs
     all_locals = set()
     for d in ordered:
         all_locals |= ({x.local(n) for n in _mentioned(d)} | {i.path for i in impacts if i.node in _mentioned(d)}
-                       | {loc for _, loc, _ in d.sites})                # a repeated edit's sites outside functions too
+                       | {loc for _, loc, _ in d.sites} | {f for p in d.pieces for f in p.files})
     depots = c.depots_for(sorted(p for p in all_locals if p))
     node_story: dict[str, str] = {}
     for d in ordered:
         for n in d.members:
             node_story.setdefault(n, ids[id(d)])
-    for nid, s in mech_of.items():
-        node_story[nid] = ids[id(next(d for d in mechs if s == d.sub or s in d.subs))]
+    for d in mechs:
+        for n in d.members:
+            node_story[n] = ids[id(d)]
     for d in behaviour:
         for fl in d.flows:
             for n in fl.path:
@@ -308,6 +323,7 @@ def build_stories(c: BoardContext, home: dict[str, str] | None = None,
         for fl in d.flows:
             if fl.cause in mech_of:
                 effect_of.setdefault(fl.cause, ids[id(d)])
+    key_story = {d.plan.key: ids[id(d)] for d in ordered if d.plan is not None}
 
     stories, details = [], {}
     changed_lines = sum(max(_count(f.before, f.after)) for f in c.cs.files)   # added and deleted files too
@@ -315,19 +331,39 @@ def build_stories(c: BoardContext, home: dict[str, str] | None = None,
     for d in ordered:
         sid = ids[id(d)]
         st = _story(x, d, sid, sev, home, depots, is_test, effect_of)
-        files = {x.local(n) for n in d.members}
+        files = {x.local(n) for n in d.members} | {f for p in d.pieces for f in p.files}
         files |= {loc for _, loc, _ in d.sites}                             # sites outside functions too
         st.cls = sorted(set().union(*(cls_of.get(f, set()) for f in files if f)))
+        _planned(st, d, key_story, pieces, x)
         stories.append(st)
         details[sid] = _detail(x, d, st, impacts, depots, about, cfg.story_graph_nodes, node_story, mech_of, ids, mechs,
                                fn_sites, effect_of, is_test)
-    summary = _summary(mechs, behaviour, others, test_story, changed_lines)
-    flow_story = {fl.id: ids[id(d)] for d in behaviour for fl in d.flows}
+    summary = _summary(mechs, behaviour, others, tests, changed_lines)
+    flow_story = {fl.id: ids[id(d)] for d in behaviour + unsorted for fl in d.flows}
     finding_story = {f: ids[id(d)] for d in ordered for f in d.findings}
     return StorySet(summary=summary, stories=stories, node_story=node_story, flow_story=flow_story,
                     finding_story=finding_story), details
 
 
+def _planned(st: Story, d: _Draft, key_story: dict[str, str], pieces: PieceSet, x: _Ctx) -> None:
+    """What the plan says of a story: its pieces and why each is there, its targets, and (tier 1) its title, purpose,
+    what to check, open questions and related stories."""
+    st.pieces = [p.id for p in d.pieces]
+    st.targets = sorted({t for p in d.pieces for t in p.targets}) or sorted(
+        {t for n in d.members for t in pieces.targets.get(x.local(n) or "", [])})
+    g = d.plan
+    if g is None:
+        return
+    st.placements = [pl.model_copy() for pl in g.placements]
+    st.source = g.source
+    if g.source == "tier1" and not g.unsorted:
+        st.purpose, st.check, st.questions = g.purpose, list(g.check), list(g.questions)
+        st.related = [key_story[k] for k in g.related if k in key_story and key_story[k] != st.id]
+        if g.title:
+            st.title, st.text_source = g.title, "llm"
+            st.summary = g.purpose or st.summary
+
+
 def _test_file(x: _Ctx, local: str) -> bool:
     """Test code by its workspace-relative path, as functions are (`is_test_path`)."""
     root = x.c.root.rstrip("/") + "/"
@@ -341,10 +377,11 @@ def _mentioned(d: _Draft) -> list[str]:
     return list(out)
 
 
-def _dir_name(x: _Ctx, members: list[str], root: str) -> str:
-    """Their common directory, workspace-relative; code spread over the workspace is named by its main directories."""
+def _dir_name(x: _Ctx, members: list[str], root: str, files: list[str] | None = None) -> str:
+    """Their common directory, workspace-relative; code spread over the workspace is named by its main directories.
+    Without members (a header's declarations), the directory of `files`."""
     r = root.rstrip("/") + "/"
-    dirs = [posixpath.dirname(x.local(m) or "") for m in members]
+    dirs = [posixpath.dirname(x.local(m) or "") for m in members] or [posixpath.dirname(f) for f in files or []]
     rel = [(d + "/")[len(r):].rstrip("/") for d in dirs if (d + "/").startswith(r)]
     common = posixpath.commonpath(rel) if rel and len(rel) == len(dirs) and all(rel) else ""
     if rel and len(rel) == len(dirs) and not any(rel):
@@ -392,7 +429,14 @@ def _story(x: _Ctx, d: _Draft, sid: str, sev: dict[str, str], home: dict[str, st
         summary = f"{_plural(len(d.members), 'test function')} changed in {_plural(counts['files'], 'file')}."
     elif d.kind == "other":
         title = f"Other changes in {d.name}"
-        summary = _other_summary(x, d.members)
+        names = [n for p in d.pieces for n in p.names]
+        summary = " ".join(t for t in [_other_summary(x, d.members), f"Declarations: {', '.join(_q(n) for n in names[:4])}"
+                                       + (f" and {len(names) - 4} more." if len(names) > 4 else ".") if names else ""] if t)
+    elif d.kind == "unsorted":
+        title = "Unsorted: needs a person to place these"
+        why = [f"{pl.piece}: {pl.reason}" for pl in (d.plan.placements if d.plan else [])]
+        summary = (f"{_plural(len(d.pieces), 'piece')} no story could take. " + "; ".join(why[:4])
+                   + (f"; and {len(why) - 4} more." if len(why) > 4 else "."))
     else:
         title, summary = _behaviour_text(x, d)
     return Story(id=sid, kind=d.kind, title=title, summary=summary, risk=d.risk(sev), counts=counts, nodes=own,
@@ -443,7 +487,7 @@ def _behaviour_text(x: _Ctx, d: _Draft) -> tuple[str, str]:
     return title, summary
 
 
-def _summary(mechs: list[_Draft], behaviour: list[_Draft], others: list[_Draft], tests: _Draft | None,
+def _summary(mechs: list[_Draft], behaviour: list[_Draft], others: list[_Draft], tests: list[_Draft],
              changed_lines: int) -> str:
     sites = sum(len(d.sites) for d in mechs)
     if mechs and changed_lines and sites * 2 >= changed_lines:
@@ -451,7 +495,7 @@ def _summary(mechs: list[_Draft], behaviour: list[_Draft], others: list[_Draft],
         what = f" ({_q(top.sub.old)} → {_q(top.sub.new)})" if top.sub else ""
         edits = "one edit" if len(mechs) == 1 and top.sub else _plural(len(mechs), "repeated edit")
         return f"Mostly mechanical: {sites} of {changed_lines} changed lines are {edits}{what}."
-    n_tests = len(tests.members) if tests else 0
+    n_tests = sum(len(t.members) for t in tests)
     parts = [_plural(len(behaviour), "behaviour story", "behaviour stories") if behaviour else "",
              _plural(len(mechs), "repeated edit") if mechs else "",
              _plural(sum(len(d.members) for d in others), "other changed function") if others else "",
@@ -472,7 +516,8 @@ def _detail(x: _Ctx, d: _Draft, st: Story, impacts: list[Impact], depots: dict[s
             fn_sites: dict[str, list[Site]], effect_of: dict, is_test) -> StoryDetail:
     mech_subs = {m.sub for m in mechs if m.sub is not None} | {s for m in mechs for s in m.subs}
     mention = [n for n in _mentioned(d) if n in x.im.nodes]
-    files = {depots.get(x.local(n)) for n in d.members if x.local(n)} - {None}
+    files = ({depots.get(x.local(n)) for n in d.members if x.local(n)} | {depots.get(f) for p in d.pieces for f in p.files}
+             ) - {None}
     part = about_for(about, files, set(d.findings), x.c.findings)
     board = _render(x, impacts, d.flows, mention, depots, hidden=0, about=part)
     on_flow = {n for fl in d.flows for n in fl.path}
@@ -500,7 +545,7 @@ def _detail(x: _Ctx, d: _Draft, st: Story, impacts: list[Impact], depots: dict[s
                 effect=effect_of.get(nid) if nid else None, other_edits=other))
         partial = sorted({nid for s, _, nid in d.sites if nid and nid not in mech_of and s.sub in own})
         detail.also_in = [StoryRef(node=n, label=x.label(n), story=node_story.get(n)) for n in partial]
-    elif d.kind in ("behaviour", "other"):
+    elif d.kind in ("behaviour", "other", "unsorted"):
         detail.graph = _graph(x, d, impacts, depots, part, cap, board)
     return detail
 
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_stories.py tests/test_web.py -q`
Expected: PASS: `76 passed`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-story.spec.ts e2e/workspace.spec.ts`
Expected: PASS: `23 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `470 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 134 passed (134)`; Playwright `86 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_pipeline.py backend/tests/test_stories.py backend/tests/test_web.py frontend/e2e/workspace-story.spec.ts frontend/e2e/workspace.spec.ts backend/codetortoise/grouping.py backend/codetortoise/pieces.py backend/codetortoise/pipeline.py backend/codetortoise/stories.py
git commit -m "feat(stories): stories are groups of pieces — the rules join by two calls or a field within a target and CL; headers by use; findings by file"
```

### Task 4: Facts prepared for each finding

Spec §5.1. Code prepares what the strong model checks, per finding, keyed by `finding_key` (kind and title, which survive renumbering):
- signature changed: every call site, marked updated in this change, not updated, compiled only in another target, or not in any compile database;
- new return value: every caller and how it handles the result (ignored, compared with what, propagated, stored, used);
- field write: every reader and writer of the field, which changed, and their lines;
- header change: each changed name and the lines using it in files including the header;
- anything else on a function: its callers and how each uses the result.

Lines in files outside the change come from `read_text`. Each finding's facts are capped at 600 tokens.

**Files:**
- Test: `backend/tests/test_facts_prep.py`
- Create: `backend/codetortoise/facts_prep.py`

**Interfaces:**
- Consumes: `board._Ctx` (calls, field accesses, texts, the impact graph), `targets.UNKNOWN`.
- Produces: `facts_prep.finding_key(f: Finding) -> str`;
  `facts_prep.prepare_facts(x, findings, targets, includers=None, read_text=None) -> dict[str, str]` (finding key → facts text);
  the per-kind builders `signature_facts`, `returns_facts`, `field_facts`, `behaviour_facts`, `header_facts`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_facts_prep.py` (new file):

```python
"""Facts prepared for each finding (spec 2026-10-05-two-tier-stories §5.1)."""
from test_stories import W, _edit, _same, _world

from codetortoise.board import _Ctx
from codetortoise.detectors.base import Evidence, Finding
from codetortoise.facts_prep import finding_key, prepare_facts


def _finding(kind, title, nodes, **kw):
    return Finding(id="F1", kind=kind, severity="medium", title=title, summary="s", nodes=nodes, **kw)


def test_a_signature_change_marks_every_call_site():
    c = _world([_edit("hal_write", "hal/regs.c"), _edit("uart_send", "drv/uart.c"), _same("old_user", "drv/old.c"),
                _same("dsp_call", "dsp/d.c"), _same("tool_main", "tools/t.c")],
               calls=[("uart_send", "hal_write"), ("old_user", "hal_write"), ("dsp_call", "hal_write"),
                      ("tool_main", "hal_write")])
    t = {f"{W}/hal/regs.c": ["fw"], f"{W}/drv/uart.c": ["fw"], f"{W}/drv/old.c": ["fw"], f"{W}/dsp/d.c": ["dsp"]}
    f = _finding("contract", "hal_write: signature changed", ["N1"])
    text = prepare_facts(_Ctx(c), [f], t)[finding_key(f)]
    assert text.splitlines() == [
        "call sites of hal_write (N1):",
        "  drv/old.c:3 in old_user (N3): not updated: `b = 0;`",
        "  drv/uart.c:3 in uart_send (N2): updated in this change: `a = 0;`",
        "  dsp/d.c:3 in dsp_call (N4): compiled only in another target: `b = 0;`",
        "  tools/t.c:3 in tool_main (N5): not in any compile database: `b = 0;`"]


def test_a_new_return_value_says_how_each_caller_handles_the_result():
    c = _world([("send", "s.c", ["a();"], ["a();", "return -2;"]), ("loose", "a.c", ["send();"], ["send();"]),
                ("check", "b.c", ["if (send() == -1) {}"], ["if (send() == -1) {}"]),
                ("pass_on", "c.c", ["return send();"], ["return send();"]), ("keep", "d.c", ["rc = send();"], ["rc = send();"])],
               calls=[("loose", "send"), ("check", "send"), ("pass_on", "send"), ("keep", "send")])
    calls = c.after[0].calls
    calls[0].result_used = False
    calls[1].compared, calls[1].compared_names = ["==-1"], {"==-1": "ERR"}
    f = _finding("contract", "send: new return value(s) -2", ["N1"])
    rows = prepare_facts(_Ctx(c), [f], {})[finding_key(f)].splitlines()
    assert rows == ["callers of send (N1) and how each handles its result:",
                    "  a.c:3 in loose (N2): ignored: `send();`",
                    "  b.c:3 in check (N3): compared with ERR (==-1): `if (send() == -1) {}`",
                    "  c.c:3 in pass_on (N4): propagated: `return send();`",
                    "  d.c:3 in keep (N5): stored: `rc = send();`"]


def test_a_field_write_lists_every_reader_and_writer_and_which_changed():
    c = _world([_edit("uart_send", "drv/uart.c"), _same("uart_errors", "drv/stat.c")],
               fields=[("uart_send", "Uart", "errors", "write", "added"), ("uart_errors", "Uart", "errors", "read", "unchanged")])
    f = _finding("field_mutation", "uart_send now writes Uart::errors", ["N1", "N3"], side_effect=True)
    rows = prepare_facts(_Ctx(c), [f], {})[finding_key(f)].splitlines()
    assert rows == ["readers and writers of Uart::errors (N3):",
                    "  uart_errors (N2) reads it: drv/stat.c:3 read `b = 0;`",
                    "  uart_send (N1) writes it — changed in this change (added by this change): drv/uart.c:3 write `a = 0;`"]


def test_a_header_change_lists_the_lines_using_each_name_in_files_including_it():
    c = _world([("pd_get", "src/pd.c", ["a = 0;"], ["a = PD_DIR;"])])
    h, other = f"{W}/src/sysdir.h", f"{W}/lib/use.c"
    f = Finding(id="F2", kind="header_fanout", severity="low", title="sysdir.h: 2 change(s) reach 2 TU(s)", summary="s",
                evidence=[Evidence(text="macro added: PD_DIR", file=h), Evidence(text="macro removed: OLD_DIR", file=h),
                          Evidence(text="included (transitively) by 2 TU(s)")])
    texts = {other: "int x;\nint y = PD_DIR + 1;\n"}
    rows = prepare_facts(_Ctx(c), [f], {}, includers=lambda hdr: {f"{W}/src/pd.c", other},
                         read_text=texts.get)[finding_key(f)].splitlines()
    assert rows == ["changes in src/sysdir.h: PD_DIR, OLD_DIR",
                    "  PD_DIR: used at", "    lib/use.c:2 `int y = PD_DIR + 1;`", "    src/pd.c:3 `a = PD_DIR;`",
                    "  OLD_DIR: no use found in the files including it", "  (2 including file(s) searched)"]


def test_findings_are_keyed_by_kind_and_title_and_others_get_their_callers():
    c = _world([_edit("core", "x.c"), _same("user", "y.c")], calls=[("user", "core")])
    f = _finding("other_kind", "core: something", ["N1"])
    facts = prepare_facts(_Ctx(c), [f], {})
    assert list(facts) == ["other_kind|core: something"]
    assert facts["other_kind|core: something"].splitlines() == ["core (N1) changed its body; its callers:",
                                                                  "  y.c:3 in user (N2): result used: `b = 0;`"]


def test_lines_in_files_outside_the_change_are_read_from_the_workspace():
    c = _world([_edit("core", "x.c"), _same("user", "y.c")], calls=[("user", "core")])
    x = _Ctx(c)
    del x.texts[f"{W}/y.c"]                                     # y.c is not in the change
    f = _finding("other_kind", "core: something", ["N1"])
    texts = {f"{W}/y.c": "int a;\nvoid user(void)\nif (core() < 0) return;\n"}
    rows = prepare_facts(x, [f], {}, read_text=texts.get)[finding_key(f)].splitlines()
    assert rows[1] == "  y.c:3 in user (N2): result used: `if (core() < 0) return;`"
    assert prepare_facts(x, [f], {})[finding_key(f)].splitlines()[1] == "  y.c:3 in user (N2): result used: ``"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_facts_prep.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.facts_prep'`

- [ ] **Step 3: Implement**

`backend/codetortoise/facts_prep.py` (new file):

```python
"""Facts prepared for each finding before any model sees it (spec 2026-10-05-two-tier-stories §5.1): the strong model
checks them and decides, instead of hunting for them.

- signature changed: every call site, marked updated in this change, not updated, compiled only in another target, or
  not in any compile database;
- new return value: every caller and how it handles the result (ignored, compared with what, propagated, stored);
- field write: every reader and writer of the field, which changed, and the lines that use it;
- header change: each changed macro, type or declaration and the lines using it in files that include the header;
- body changed (a changed function with callers and no finding): its callers and the lines using its result.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from codetortoise.board import _Ctx
from codetortoise.detectors.base import Finding
from codetortoise.targets import UNKNOWN

FACT_CHARS = 2400                     # 600 tokens per finding
_ASSIGN = re.compile(r"(^|[^=!<>])=([^=]|$)")


def finding_key(f: Finding) -> str:
    """A finding's identity across renumbering and re-runs: its kind and title."""
    return f"{f.kind}|{f.title}"


def _rel(x: _Ctx, path: str | None) -> str:
    root = x.c.root.rstrip("/") + "/"
    return (path[len(root):] if path and x.c.root and path.startswith(root) else path) or "?"


def _line(x: _Ctx, path: str, line: int, read: dict[str, str] | None = None) -> str:
    """Line `line` of `path` after the change; `read` holds the text of files outside it."""
    fc = x.texts.get(path)
    rows = (fc.after if fc else (read or {}).get(path, "")).splitlines()
    return rows[line - 1].strip() if 0 < line <= len(rows) else ""


def _cap(rows: list[str]) -> str:
    text = "\n".join(rows)
    return text if len(text) <= FACT_CHARS else text[:FACT_CHARS - 1] + "…"


def _targets_of(targets: dict[str, list[str]], path: str | None) -> set[str]:
    return set(targets.get(path or "", [])) or {UNKNOWN}


def _call_sites(x: _Ctx, nid: str) -> list:
    key = x.im.nodes[nid].key
    return sorted((c for c in x.calls_after if c.callee == key), key=lambda c: (c.file, c.line))


def signature_facts(x: _Ctx, nid: str, targets: dict[str, list[str]], read: dict[str, str] | None = None) -> list[str]:
    n = x.im.nodes[nid]
    mine = _targets_of(targets, x.local(nid))
    rows = [f"call sites of {n.label} ({nid}):"]
    for c in _call_sites(x, nid):
        caller = x.id_of.get(c.caller)
        where = _targets_of(targets, c.file)
        mark = ("not in any compile database" if where == {UNKNOWN}
                else "compiled only in another target" if not (where & mine)
                else "updated in this change" if caller in x.changed else "not updated")
        rows.append(f"  {_rel(x, c.file)}:{c.line} in {x.label(caller) if caller else c.caller} ({caller or '-'}): "
                    f"{mark}: `{_line(x, c.file, c.line, read)}`")
    heur = [e for e in x.im.edges if e.dst == nid and e.kind == "call" and e.confidence == "heuristic"]
    if heur:
        rows.append(f"  {len(heur)} more caller(s) outside the parsed files, by name only: "
                    + ", ".join(sorted({x.label(e.src) for e in heur})[:10]))
    if len(rows) == 1:
        rows.append("  none found in the parsed files")
    return rows


def returns_facts(x: _Ctx, nid: str, read: dict[str, str] | None = None) -> list[str]:
    n = x.im.nodes[nid]
    rows = [f"callers of {n.label} ({nid}) and how each handles its result:"]
    for c in _call_sites(x, nid):
        caller = x.id_of.get(c.caller)
        text = _line(x, c.file, c.line, read)
        before_call = text.split(c.callee_name, 1)[0] if c.callee_name in text else ""
        how = ("ignored" if not c.result_used
               else "compared with " + ", ".join(f"{c.compared_names[v]} ({v})" if v in c.compared_names else v
                                                 for v in c.compared) if c.compared
               else "propagated" if re.search(r"\breturn\b", before_call)
               else "stored" if _ASSIGN.search(before_call) else "used")
        rows.append(f"  {_rel(x, c.file)}:{c.line} in {x.label(caller) if caller else c.caller} ({caller or '-'}): {how}: "
                    f"`{text}`")
    if len(rows) == 1:
        rows.append("  none found in the parsed files")
    return rows


def field_facts(x: _Ctx, field_id: str, read: dict[str, str] | None = None) -> list[str]:
    n = x.im.nodes[field_id]
    rows = [f"readers and writers of {n.label} ({field_id}):"]
    for e in sorted((e for e in x.im.edges if e.dst == field_id and e.kind in ("reads", "writes")),
                    key=lambda e: (x.label(e.src), e.kind)):
        fn = x.im.nodes[e.src]
        lines = sorted({(a.file, a.line, a.mode) for a in x.fields_after if f"field:{a.field}" == n.key
                        and a.fn == fn.key})
        where = "; ".join(f"{_rel(x, f)}:{ln} {mode} `{_line(x, f, ln, read)}`" for f, ln, mode in lines[:3]) or "no lines"
        rows.append(f"  {fn.label} ({e.src}) {e.kind[:-1]}s it" + (" — changed in this change" if e.src in x.changed else "")
                    + (f" ({e.status} by this change)" if e.status != "unchanged" else "") + f": {where}")
    return rows


def behaviour_facts(x: _Ctx, nid: str, read: dict[str, str] | None = None) -> list[str]:
    """A changed function's callers and the lines using its result (its contract did not change)."""
    rows = [f"{x.label(nid)} ({nid}) changed its body; its callers:"]
    for c in _call_sites(x, nid):
        caller = x.id_of.get(c.caller)
        use = "result ignored" if not c.result_used else "result used"
        rows.append(f"  {_rel(x, c.file)}:{c.line} in {x.label(caller) if caller else c.caller} ({caller or '-'}): {use}: "
                    f"`{_line(x, c.file, c.line, read)}`" + (" — changed in this change" if caller in x.changed else ""))
    return rows


def header_facts(x: _Ctx, f: Finding, includers: Callable[[str], set[str]] | None,
                 read_text: Callable[[str], str | None] | None, files: int = 30, hits: int = 5) -> list[str]:
    header = next((e.file for e in f.evidence if e.file), None)
    names = [e.text.split(": ", 1)[-1] for e in f.evidence if e.file]
    rows = [f"changes in {_rel(x, header)}: " + ", ".join(names)]
    users = sorted(includers(header))[:files] if includers and header else []
    for name in names:
        word = re.compile(rf"\b{re.escape(name.split()[-1])}\b")
        found = []
        for path in users:
            fc = x.texts.get(path)
            text = fc.after if fc else (read_text(path) if read_text else None) or ""
            for i, row in enumerate(text.splitlines(), 1):
                if word.search(row):
                    found.append(f"    {_rel(x, path)}:{i} `{row.strip()}`")
                    if len(found) >= hits:
                        break
            if len(found) >= hits:
                break
        rows.append(f"  {name}: " + ("used at\n" + "\n".join(found) if found else "no use found in the files including it"))
    if users:
        rows.append(f"  ({len(users)} including file(s) searched)")
    return rows


def prepare_facts(x: _Ctx, findings: list[Finding], targets: dict[str, list[str]],
                  includers: Callable[[str], set[str]] | None = None,
                  read_text: Callable[[str], str | None] | None = None) -> dict[str, str]:
    """finding_key -> the facts the strong model checks for it. `read_text` reads files outside the change (the lines of
    callers and readers there, and the header search)."""
    read = {p: read_text(p) or "" for p in sorted({c.file for c in x.calls_after} | {a.file for a in x.fields_after})
            if p not in x.texts} if read_text is not None else {}
    out = {}
    for f in findings:
        fn = next((n for n in f.nodes if n in x.im.nodes and x.im.nodes[n].kind == "function"), None)
        rows: list[str] = []
        if f.kind == "contract" and fn:
            if "signature changed" in f.title:
                rows += signature_facts(x, fn, targets, read)
            if "new return value" in f.title:
                rows += returns_facts(x, fn, read)
        elif f.kind == "field_mutation":
            field = next((n for n in f.nodes if n in x.im.nodes and x.im.nodes[n].kind == "field"), None)
            rows += field_facts(x, field, read) if field else []
            rows += behaviour_facts(x, fn, read) if fn and not field else []
        elif f.kind == "header_fanout":
            rows += header_facts(x, f, includers, read_text)
        elif fn:
            rows += behaviour_facts(x, fn, read)
        out[finding_key(f)] = _cap(rows) if rows else "no prepared facts"
    return out
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_facts_prep.py -q`
Expected: PASS: `6 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `476 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_facts_prep.py backend/codetortoise/facts_prep.py
git commit -m "feat(facts): facts prepared per finding — call sites marked, result handling, field readers and writers, header uses, callers"
```

### Task 5: An optional strong model: config, its own budget, Health

Spec §9, §4.6 (temperature):
- `llm.strong` configures a second OpenAI-compatible client (`services.make_strong`), whose requests carry `temperature` when it is set.
- The ledger counts tier-1 purposes (`stories`, `stories_merge`, `review`) against `tier1_per_review` only. `used()` leaves them out, and `usage()` reports them under `tier1`.
- Health checks the strong endpoint as a warning-only check. Its detail names the endpoint and model. When the host is neither this machine nor a private address, it adds "code from reviewed changes is sent to <host>".

**Files:**
- Test: `backend/tests/test_config.py`
- Test: `backend/tests/test_ledger.py`
- Test: `backend/tests/test_llm_client.py`
- Test: `backend/tests/test_ondemand.py`
- Test: `backend/tests/test_pipeline.py`
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/health.py`
- Modify: `backend/codetortoise/llm/client.py`
- Modify: `backend/codetortoise/llm/ledger.py`
- Modify: `backend/codetortoise/services.py`

**Interfaces:**
- Consumes: `LlmClient`, `Ledger`, `run_health`.
- Produces: `config.StrongLlmConfig(base_url, model, key_env="TORTOISE_STRONG_KEY", context_tokens=64000, temperature=0, rounds=20, agree=1, timeout_s=300)`, `LlmConfig.strong: StrongLlmConfig | None`, `LlmBudget.tier1_per_review = 40`;
  `LlmClient(..., temperature: float | None = None)`; `ledger.TIER1`, `Ledger.tier1_used(rid) -> int`, `Ledger.check(rid, user, purpose=None)`, `usage()["tier1"] = {"used", "budget"}`;
  `Services.strong: LlmClient | None`, `services.make_strong(cfg) -> LlmClient | None`, `build_services(..., strong=None)`;
  `health.remote_host(url) -> str | None`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_config.py` (diff):

```diff
diff --git a/backend/tests/test_config.py b/backend/tests/test_config.py
index 6f003b0..7e5c0dd 100644
--- a/backend/tests/test_config.py
+++ b/backend/tests/test_config.py
@@ -91,3 +91,14 @@ def test_a_missing_tls_file_is_a_config_error_not_a_startup_traceback(tmp_path):
     with pytest.raises(ConfigError, match="server.tls_key: no such file"):
         load_config(write(tmp_path, "owner: a\nworkspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"
                                       "server: {tls_cert: ct.pem, tls_key: ct.key}\n"))
+
+
+def test_the_strong_model_and_its_budget_are_optional():
+    from codetortoise.config import Config
+    base = {"workspace": {"root": "/w", "compile_commands": "auto"}}
+    cfg = Config.model_validate(base)
+    assert cfg.llm.strong is None and cfg.llm.budget.tier1_per_review == 40
+    cfg = Config.model_validate({**base, "llm": {"strong": {"base_url": "https://x/v1", "model": "big", "temperature": None,
+                                                            "agree": 2}}})
+    s = cfg.llm.strong
+    assert (s.key_env, s.context_tokens, s.temperature, s.rounds, s.agree) == ("TORTOISE_STRONG_KEY", 64000, None, 20, 2)
```

`backend/tests/test_ledger.py` (diff):

```diff
diff --git a/backend/tests/test_ledger.py b/backend/tests/test_ledger.py
index 7acde5d..55b6193 100644
--- a/backend/tests/test_ledger.py
+++ b/backend/tests/test_ledger.py
@@ -109,3 +109,15 @@ def test_workspace_calls_are_recorded_without_a_review_budget(tmp_path):
     ledger.call(_llm(), None, None, "layers", "generation 3", _ask)          # layer naming: once per index
     ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)                     # the review's one call is still free
     assert ledger.workspace_calls() == 1 and ledger.usage(rid)["used"] == 1
+
+
+def test_tier_1_calls_count_against_their_own_budget_not_the_review_s(tmp_path):
+    ledger, _, rid = _ledger(tmp_path, per_review=1, tier1_per_review=2)
+    for purpose in ("stories", "review"):
+        ledger.call(_llm(), rid, None, purpose, "x", _ask)
+    with pytest.raises(Refused, match="this review has used its 2 tier-1 AI calls"):
+        ledger.call(_llm(), rid, None, "stories_merge", "x", _ask)
+    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)        # the tier-2 budget is untouched
+    u = ledger.usage(rid)
+    assert (u["used"], u["budget"], u["tier1"]) == (1, 1, {"used": 2, "budget": 2})
+    assert u["by_purpose"] == {"stories": 1, "review": 1, "flow": 1}
```

`backend/tests/test_llm_client.py` (diff):

```diff
diff --git a/backend/tests/test_llm_client.py b/backend/tests/test_llm_client.py
index 390dbd5..c0c8557 100644
--- a/backend/tests/test_llm_client.py
+++ b/backend/tests/test_llm_client.py
@@ -123,3 +123,14 @@ def test_switches_to_json_schema_when_server_requires_it():
     assert rf["json_schema"]["schema"]["required"] == ["answer", "n"]
     c.complete_json("s", "u", Out)
     assert len(bodies) == 3  # the mode is remembered: no second rejected request
+
+
+def test_a_temperature_is_sent_only_when_set():
+    seen = []
+
+    def handler(req):
+        seen.append(json.loads(req.content))
+        return reply('{"answer": "ok", "n": 2}')
+    client(handler, temperature=0).complete_json("s", "u", Out)
+    client(handler).complete_json("s", "u", Out)
+    assert seen[0]["temperature"] == 0 and "temperature" not in seen[1]
```

`backend/tests/test_ondemand.py` (diff):

```diff
diff --git a/backend/tests/test_ondemand.py b/backend/tests/test_ondemand.py
index 214717a..5d927c0 100644
--- a/backend/tests/test_ondemand.py
+++ b/backend/tests/test_ondemand.py
@@ -152,7 +152,7 @@ def test_the_ai_view_reports_limits_and_calls(ai):
     assert all(c["prompt_tokens"] == 1000 for c in calls)
     h = owner.get("/api/health").json()                               # + layer naming, once per index
     assert h["ai"]["calls_today"] == 6 and h["ai"]["limits"] == {"per_review": 200, "per_person_daily": 100,
-                                                                 "per_mention": 6}
+                                                                 "per_mention": 6, "tier1_per_review": 40}
 
 
 def test_an_answer_that_fails_the_checks_changes_nothing_and_says_why(ai, monkeypatch):
```

`backend/tests/test_pipeline.py` (diff):

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 19b0452..05179cf 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -347,3 +347,19 @@ def test_depot_resolver_failure_keeps_changed_files_and_notes_why():
     notes: list[str] = []
     assert depot_resolver(Src(), cs, "/ws", notes)(["/ws/a.c", "/ws/b.c"]) == {"/ws/a.c": "//d/a.c"}
     assert notes == ["depot paths unavailable for context nodes: P4Error: p4 where: connect failed"]
+
+
+def test_health_checks_the_strong_model_and_says_where_code_is_sent(fx, tmp_path):
+    from codetortoise.config import StrongLlmConfig
+    from codetortoise.services import make_strong
+    for url, remote in (("https://api.example.com/v1", True), ("http://127.0.0.1:1234/v1", False),
+                        ("http://192.168.1.20:8080/v1", False), ("http://localhost:1/v1", False)):
+        svc = make_services(fx, tmp_path)
+        svc.cfg.llm.strong = StrongLlmConfig(base_url=url, model="big")
+        svc.strong = make_strong(svc.cfg)
+        svc.strong.ping = lambda: False                     # no network in tests
+        check = {c.name: c for c in run_health(svc).checks}["strong model endpoint"]
+        assert check.hard is False and check.detail.startswith(f"{url} (big)")
+        assert check.detail.endswith("; code from reviewed changes is sent to api.example.com") == remote
+    svc = make_services(fx, tmp_path)
+    assert {c.name: c for c in run_health(svc).checks}["strong model endpoint"].detail == "not configured (stories by rules)"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_config.py tests/test_ledger.py tests/test_llm_client.py tests/test_ondemand.py tests/test_pipeline.py -q`
Expected: FAIL: `5 failed, 61 passed`; the first error is `AttributeError: 'LlmConfig' object has no attribute 'strong'`

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py` (diff):

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index 44eb212..b0329ac 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -63,6 +63,19 @@ class LlmBudget(BaseModel):
     per_review: int = 200          # AI calls per review: everyone and the pipeline together
     per_person_daily: int = 100    # AI calls one person can trigger per day (UTC), across reviews
     per_mention: int = 10          # rounds one @tortoise answer may take (one AI call however many); the owner sets it per review
+    tier1_per_review: int = 40     # strong-model calls per review: stories, merge and risk passes (spec 2026-10-05 §9)
+
+
+class StrongLlmConfig(BaseModel):
+    """The strong model that forms stories and reviews their risks (spec 2026-10-05-two-tier-stories §9)."""
+    base_url: str                  # any OpenAI-compatible endpoint
+    model: str
+    key_env: str = "TORTOISE_STRONG_KEY"
+    context_tokens: int = 64000
+    temperature: float | None = 0  # None for endpoints that reject it
+    rounds: int = 20               # reads one stories or review call may make (one AI call however many)
+    agree: Literal[1, 2] = 1       # 2: two runs (a third breaks ties) for stable stories
+    timeout_s: float = 300.0
 
 
 class LlmConfig(BaseModel):
@@ -77,6 +90,7 @@ class LlmConfig(BaseModel):
     upfront_findings: int = 5      # high-severity findings the AI explains when a review runs, not on first open
     upfront_side_effects: int = 36  # side effects (new field writes) the AI judges when a review runs, 12 to a call
     budget: LlmBudget = Field(default_factory=LlmBudget)
+    strong: StrongLlmConfig | None = None   # absent: the rules form the stories
 
 
 class AuthConfig(BaseModel):
```

`backend/codetortoise/health.py` (diff):

```diff
diff --git a/backend/codetortoise/health.py b/backend/codetortoise/health.py
index 78925ad..feefb6e 100644
--- a/backend/codetortoise/health.py
+++ b/backend/codetortoise/health.py
@@ -1,8 +1,10 @@
 """Startup validation. Hard checks gate review creation."""
 from __future__ import annotations
 
+import ipaddress
 import os
 from datetime import UTC, datetime
+from urllib.parse import urlparse
 
 from pydantic import BaseModel
 
@@ -30,6 +32,18 @@ class HealthReport(BaseModel):
     ai: dict = {}                      # AI call limits and today's total across reviews
 
 
+def remote_host(url: str) -> str | None:
+    """The endpoint's host when it is neither this machine nor a private address (code is sent off-site), else None."""
+    host = urlparse(url).hostname or ""
+    if host == "localhost" or host.endswith(".localhost"):
+        return None
+    try:
+        ip = ipaddress.ip_address(host)
+    except ValueError:
+        return host or None
+    return None if ip.is_private or ip.is_loopback or ip.is_link_local else host
+
+
 def run_health(svc: Services, deep: bool = False) -> HealthReport:
     """Hard checks gate review creation. `deep` (the Health page) also checks each toolchain group: its compiler is
     queried and one of its files parsed, once per process (startup doesn't run any compiler)."""
@@ -87,6 +101,14 @@ def run_health(svc: Services, deep: bool = False) -> HealthReport:
         checks.append(Check(name="llm endpoint", ok=svc.llm.ping(), hard=False, detail=cfg.llm.base_url or ""))
     else:
         checks.append(Check(name="llm endpoint", ok=False, hard=False, detail="not configured"))
+    strong = cfg.llm.strong
+    if strong is not None and svc.strong is not None:
+        away = remote_host(strong.base_url)
+        checks.append(Check(name="strong model endpoint", ok=svc.strong.ping(), hard=False,
+                            detail=f"{strong.base_url} ({strong.model})"
+                                   + (f"; code from reviewed changes is sent to {away}" if away else "")))
+    else:
+        checks.append(Check(name="strong model endpoint", ok=False, hard=False, detail="not configured (stories by rules)"))
     if cfg.swarm.url:
         client = svc.swarm()
         checks.append(Check(name="swarm", ok=client is not None, hard=False,
```

`backend/codetortoise/llm/client.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/client.py b/backend/codetortoise/llm/client.py
index c9c1154..203259a 100644
--- a/backend/codetortoise/llm/client.py
+++ b/backend/codetortoise/llm/client.py
@@ -30,8 +30,9 @@ def _extract_json(text: str) -> str:
 class LlmClient:
     def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120,
                  transport: httpx.BaseTransport | None = None, retries: int = 2,
-                 sleep: Callable[[float], None] = time.sleep):
+                 sleep: Callable[[float], None] = time.sleep, temperature: float | None = None):
         self.model = model
+        self.temperature = temperature           # None: the model's own default (some servers reject it)
         self.retries = retries
         self._sleep = sleep
         self._format = "json_object"  # -> "json_schema" (e.g. LM Studio) or "none" as servers reject formats
@@ -50,6 +51,8 @@ class LlmClient:
     def chat(self, system: str, user: str, schema: type[BaseModel] | None = None) -> str:
         body = {"model": self.model,
                 "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
+        if self.temperature is not None:
+            body["temperature"] = self.temperature
         last: Exception | None = None
         for attempt in range(self.retries + 1):
             rf = self._response_format(schema)
```

`backend/codetortoise/llm/ledger.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/ledger.py b/backend/codetortoise/llm/ledger.py
index 9a6f2fa..9db62be 100644
--- a/backend/codetortoise/llm/ledger.py
+++ b/backend/codetortoise/llm/ledger.py
@@ -17,6 +17,8 @@ from codetortoise.store import Store
 
 T = TypeVar("T")
 PIPELINE = "pipeline"
+TIER1 = ("stories", "stories_merge", "review")    # strong-model calls: their own budget (spec 2026-10-05 §9)
+_T1 = "(" + ",".join(f"'{p}'" for p in TIER1) + ")"
 
 
 class Refused(Exception):
@@ -52,16 +54,24 @@ class Ledger:
         self.store._exec("INSERT INTO llm_rounds VALUES(?,?,?,?)", (rid, int(rounds), by, _now()))
 
     def used(self, rid: int) -> int:
-        return self.store._all("SELECT COUNT(*) AS n FROM llm_calls WHERE review_id=? AND outcome != 'refused'",
-                               (rid,))[0]["n"]
+        """Tier-2 calls on the review: everyone's and the pipeline's, not the strong model's."""
+        return self.store._all("SELECT COUNT(*) AS n FROM llm_calls WHERE review_id=? AND outcome != 'refused' "
+                               f"AND purpose NOT IN {_T1}", (rid,))[0]["n"]
+
+    def tier1_used(self, rid: int) -> int:
+        return self.store._all("SELECT COUNT(*) AS n FROM llm_calls WHERE review_id=? AND outcome != 'refused' "
+                               f"AND purpose IN {_T1}", (rid,))[0]["n"]
 
     def person_today(self, user: str) -> int:
         day = datetime.now(UTC).date().isoformat()
         return self.store._all("SELECT COUNT(*) AS n FROM llm_calls WHERE user=? AND outcome != 'refused' "
                                "AND started_at >= ?", (user, day))[0]["n"]
 
-    def check(self, rid: int | None, user: str | None) -> str | None:
+    def check(self, rid: int | None, user: str | None, purpose: str | None = None) -> str | None:
         """Why a call by `user` on review `rid` would be refused now, or None."""
+        if rid is not None and purpose in TIER1:
+            n = self.limits.tier1_per_review
+            return f"this review has used its {n} tier-1 AI calls" if self.tier1_used(rid) >= n else None
         if rid is not None:
             budget = self.budget(rid)
             if self.used(rid) >= budget:
@@ -74,7 +84,7 @@ class Ledger:
     def reserve(self, rid: int | None, user: str | None, purpose: str, target: str) -> int:
         """Record a call about to be made and return its id, or raise Refused (recording the refusal)."""
         with self.store._lock:
-            reason = self.check(rid, user)
+            reason = self.check(rid, user, purpose)
             cur = self.store._exec(
                 "INSERT INTO llm_calls(review_id, user, purpose, target, started_at, outcome, error) VALUES(?,?,?,?,?,?,?)",
                 (rid, user or PIPELINE, purpose, target, _now(), "refused" if reason else "running", reason))
@@ -115,6 +125,8 @@ class Ledger:
         calls = self.store._all("SELECT id, user, purpose, target, started_at, finished_at, prompt_tokens, "
                                 "completion_tokens, outcome, error FROM llm_calls WHERE review_id=? ORDER BY id", (rid,))
         counted = [c for c in calls if c["outcome"] != "refused"]
-        return {"used": len(counted), "budget": self.budget(rid),
+        tier1 = [c for c in counted if c["purpose"] in TIER1]
+        return {"used": len(counted) - len(tier1), "budget": self.budget(rid),
+                "tier1": {"used": len(tier1), "budget": self.limits.tier1_per_review},
                 "by_person": dict(Counter(c["user"] for c in counted)),
                 "by_purpose": dict(Counter(c["purpose"] for c in counted)), "calls": calls}
```

`backend/codetortoise/services.py` (diff):

```diff
diff --git a/backend/codetortoise/services.py b/backend/codetortoise/services.py
index aea4b07..aefe25a 100644
--- a/backend/codetortoise/services.py
+++ b/backend/codetortoise/services.py
@@ -76,6 +76,7 @@ class Services:
     p4: P4Runner | None = None
     owner_ticket: str | None = None
     ledger: Ledger | None = None                  # every AI call goes through it (spec 2026-10-03 §2)
+    strong: LlmClient | None = None               # tier 1: forms stories and reviews their risks (spec 2026-10-05)
     swarm_override: Callable[[], SwarmClient | None] | None = field(default=None, repr=False)
 
     def build_index(self, full: bool = False) -> int:
@@ -106,7 +107,15 @@ def make_llm(cfg: Config) -> LlmClient | None:
     return LlmClient(cfg.llm.base_url, key, cfg.llm.model, timeout=cfg.llm.timeout_s)
 
 
-def build_services(cfg: Config, llm: LlmClient | None = None, source: Source | None = None) -> Services:
+def make_strong(cfg: Config) -> LlmClient | None:
+    s = cfg.llm.strong
+    if s is None:
+        return None
+    return LlmClient(s.base_url, os.environ.get(s.key_env, ""), s.model, timeout=s.timeout_s, temperature=s.temperature)
+
+
+def build_services(cfg: Config, llm: LlmClient | None = None, source: Source | None = None,
+                   strong: LlmClient | None = None) -> Services:
     data = cfg.server.data_dir
     data.mkdir(parents=True, exist_ok=True)
     store = Store(data / "tortoise.db")
@@ -124,4 +133,5 @@ def build_services(cfg: Config, llm: LlmClient | None = None, source: Source | N
             source = P4Source(p4)
     ledger = Ledger(store, cfg.llm.budget)
     return Services(cfg=cfg, store=store, source=source, index=index, cdb=cdb, toolchain=tc, llm=llm,
-                    layers=LayersProvider(cfg, index, store, llm, ledger), p4=p4, ledger=ledger)
+                    layers=LayersProvider(cfg, index, store, llm, ledger), p4=p4, ledger=ledger,
+                    strong=strong if strong is not None else make_strong(cfg))
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_config.py tests/test_ledger.py tests/test_llm_client.py tests/test_ondemand.py tests/test_pipeline.py -q`
Expected: PASS: `66 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `480 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_config.py backend/tests/test_ledger.py backend/tests/test_llm_client.py backend/tests/test_ondemand.py backend/tests/test_pipeline.py backend/codetortoise/config.py backend/codetortoise/health.py backend/codetortoise/llm/client.py backend/codetortoise/llm/ledger.py backend/codetortoise/services.py
git commit -m "feat(llm): an optional strong model — config, temperature, its own tier-1 budget, and Health saying where code is sent"
```

### Task 6: Tier 1 forms the stories

Spec §4, §7.2. `llm/stories.form_stories` sends each chunk the fixed `RULES` (a numbered procedure), the change overview, the chunk's cards, the links among them and its findings. The model may read a piece's code, a file's diff, a function's neighbours or a CL, over rounds that make one AI call (`ask`). `check_answer` checks every placement on its own (§4.4). A failed one moves that piece to the Unsorted story with the failure as its reason: an unknown id, a second placement, another target (unless `shared_code`), or another CL with neither a joining link nor a verbatim quote from each description. A title, purpose or note breaking the house style is dropped (a dropped title gives way to the rules' title) and the placements stand.

A change that fits in 60% of the context is one chunk. A larger one is cut by target, then CL, then top directory, and a merge pass names related stories and merges same-target stories, checked like placements. `agree: 2` runs each chunk twice and lets a third run decide the pieces the first two disagree on. A failed chunk, or one refused by the budget, falls back to the rules, and the plan's notes say so.

The result is stored as the review's **brief** (`brief.py`; table `briefs`) under a cache key. A later run of the same change reuses a complete brief unless `fresh` is asked (`run_review(rid, svc, fresh=False)`; `JobRunner.submit_review(rid, fresh=False)`).

**Files:**
- Test: `backend/tests/scripted_llm.py`
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_tier1_stories.py`
- Test: `backend/tests/test_web.py`
- Create: `backend/codetortoise/brief.py`
- Create: `backend/codetortoise/llm/stories.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/store.py`

**Interfaces:**
- Consumes: `PieceSet` (Task 2), `rules_plan`/`StoryPlan`/`PlannedStory`/`Placement` (Task 3), `Services.strong`, `Ledger.call` with the tier-1 purposes (Task 5).
- Produces: `brief.BriefVerdict(verdict, reason, cites)`, `brief.Brief(key, model, complete, overview, pieces, plan, verdicts, facts, reviewed)`, `brief.cache_key(ps, model, rules_version, agree) -> str`;
  `Store.put_brief(rid, key, brief)`, `Store.get_brief(rid) -> dict | None`, `Store.find_brief(key) -> dict | None` (the newest complete one);
  `llm.stories.STORY_RULES_VERSION`, `Tools(x, ps)` with `.run(tool, arg)`, `chunk_parts`, `chunks(ps, findings, limit)`, `ask(strong, parts, tools, rounds, limit) -> _Step`, `place`, `check_answer`, `agree`, `merge_pass`,
  `form_stories(strong, ledger, rid, ps, x, cfg: StrongLlmConfig, findings) -> StoryPlan`;
  `pipeline.run_review(rid, svc, fresh=False)`, `JobRunner.submit_review(rid, fresh=False)`; `tests/scripted_llm.ScriptedLlm(answer, model="big")` (`.prompts`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/scripted_llm.py` (new file):

```python
"""A model that answers from a script: each call goes to `answer(system, user)`, whose dict is the reply."""
from collections.abc import Callable


class ScriptedLlm:
    def __init__(self, answer: Callable[[str, str], dict], model: str = "big"):
        self.answer, self.model, self.prompts = answer, model, []

    def complete_json(self, system, user, schema):
        self.prompts.append(user)
        out = self.answer(system, user)
        if isinstance(out, Exception):
            raise out
        return schema.model_validate(out)

    def start_usage(self):
        pass

    def take_usage(self):
        return None

    def ping(self):
        return True
```

`backend/tests/test_pipeline.py` (diff):

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 05179cf..67ff5f2 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -20,7 +20,7 @@ def test_full_review_without_llm_or_swarm(fx, tmp_path):
                                 "stories": "ok", "verdicts": "ok", "board": "ok", "llm": "degraded", "finalize": "ok"}
     msgs = {s["name"]: s["message"] for s in svc.store.list_stages(rid)}
     assert msgs["pieces"].endswith("target(s): compile_commands")
-    assert msgs["stories"].endswith("by the rules")
+    assert msgs["stories"].endswith("by the rules (no strong model configured)")
     ss = svc.store.get_blob(rid, "stories")
     assert all(s["targets"] == ["compile_commands"] and s["pieces"] for s in ss["stories"])
     review = svc.store.get_review(rid)
@@ -363,3 +363,58 @@ def test_health_checks_the_strong_model_and_says_where_code_is_sent(fx, tmp_path
         assert check.detail.endswith("; code from reviewed changes is sent to api.example.com") == remote
     svc = make_services(fx, tmp_path)
     assert {c.name: c for c in run_health(svc).checks}["strong model endpoint"].detail == "not configured (stories by rules)"
+
+
+def _strong(svc, answer, model="big"):
+    from scripted_llm import ScriptedLlm
+
+    from codetortoise.config import StrongLlmConfig
+    svc.cfg.llm.strong = StrongLlmConfig(base_url="http://127.0.0.1:9/v1", model=model)
+    svc.strong = ScriptedLlm(answer, model)
+    return svc.strong
+
+
+def _one_story_per_cl(system, user):
+    """Every piece of a CL in one story (the pieces' cards name their CL)."""
+    import re
+    if "STORIES (key | title" in user:
+        return {"related": [], "merge": []}
+    by_cl: dict[str, list[str]] = {}
+    for pid, cl in re.findall(r"^(P\d+)  .*? · CL (\d+)", user, re.M):
+        by_cl.setdefault(cl, []).append(pid)
+    return {"action": "answer", "stories": [
+        {"key": f"cl{cl}", "title": f"Changes of CL {cl}", "purpose": "This changes the UART driver.",
+         "pieces": [{"id": p, "reason": "starts_purpose" if i == 0 else "same_feature"} for i, p in enumerate(ids)]}
+        for cl, ids in sorted(by_cl.items())]}
+
+
+def test_the_strong_model_forms_the_stories_and_a_rerun_of_the_same_change_reuses_them(fx, tmp_path):
+    svc = make_services(fx, tmp_path)
+    llm = _strong(svc, _one_story_per_cl)
+    rid = svc.store.create_review("t", "owner", [101, 102])
+    run_review(rid, svc)
+    msg = next(s for s in svc.store.list_stages(rid) if s["name"] == "stories")
+    assert msg["status"] == "ok" and msg["message"].startswith("2 stories formed by big, ")
+    assert msg["message"].endswith("piece(s) placed, 0 unsorted")
+    ss = svc.store.get_blob(rid, "stories")["stories"]
+    assert {s["title"] for s in ss if s["source"] == "tier1"} == {"Changes of CL 101", "Changes of CL 102"}
+    brief = svc.store.get_brief(rid)
+    assert brief["model"] == "big" and brief["complete"] and brief["overview"].startswith("CHANGE: 2 CLs")
+    calls = len(llm.prompts)
+    run_review(rid, svc)                                            # unchanged: the brief is reused
+    assert len(llm.prompts) == calls
+    assert "reused" in next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "stories")
+    run_review(rid, svc, fresh=True)                                # the owner asked for fresh stories
+    assert len(llm.prompts) == calls * 2
+
+
+def test_a_strong_model_that_fails_leaves_the_rules_stories_and_says_so(fx, tmp_path):
+    svc = make_services(fx, tmp_path)
+    _strong(svc, lambda s, u: RuntimeError("the endpoint is down"))
+    rid = svc.store.create_review("t", "owner", [101, 102])
+    run_review(rid, svc)
+    st = next(s for s in svc.store.list_stages(rid) if s["name"] == "stories")
+    assert st["status"] == "degraded"
+    assert "chunk 1: RuntimeError: the endpoint is down; the rules grouped its pieces" in st["message"]
+    assert {s["source"] for s in svc.store.get_blob(rid, "stories")["stories"]} == {"rules"}
+    assert svc.store.get_brief(rid)["complete"] is False
```

`backend/tests/test_tier1_stories.py` (new file):

```python
"""Tier 1 forms the stories (spec 2026-10-05-two-tier-stories §4)."""
import pytest
from scripted_llm import ScriptedLlm
from test_stories import W, _edit, _in_cls, _world

from codetortoise.board import analyse
from codetortoise.brief import cache_key
from codetortoise.config import LlmBudget, StrongLlmConfig
from codetortoise.llm.ledger import Ledger
from codetortoise.llm.stories import STORY_RULES_VERSION, chunk_parts, form_stories
from codetortoise.pieces import build_pieces
from codetortoise.store import Store

DESC = {11: "modem: add LTE band 71 support", 12: "modem: band 71 tables for the RF front end", 13: "dsp: faster FFT"}


def _change(cls=None, desc=DESC):
    c = _world([_edit("modem_tx", "modem/tx/a.c"), _edit("modem_rx", "modem/rx/b.c"), _edit("dsp_run", "dsp/run.c")],
               calls=[("modem_tx", "modem_rx")])
    if cls:
        _in_cls(c, cls, desc)
    a = analyse(c)
    t = {f"{W}/modem/tx/a.c": ["modem"], f"{W}/modem/rx/b.c": ["modem"], f"{W}/dsp/run.c": ["dsp"]}
    ps = build_pieces(c, a, t)
    pid = {c.impact.nodes[p.nodes[0]].label: p.id for p in ps.pieces}
    return c, a, ps, pid


def _story(key, title, *pieces, purpose="This adds band 71 to the modem.", related=()):
    return {"key": key, "title": title, "purpose": purpose, "check": ["Check the band tables."],
            "questions": ["Does the DSP need band 71 too?"], "related": list(related),
            "pieces": [{"id": p, "reason": r, "evidence": list(ev), "quote": list(q)} for p, r, ev, q in pieces]}


def _p(pid, reason="same_feature", evidence=(), quote=()):
    return (pid, reason, evidence, quote)


def _per_target(ps):
    """A context too small for the whole change but big enough for its largest target's pieces."""
    largest = max(sum(len(t) for t in chunk_parts([p.id for p in ps.pieces if p.targets == [tg]], ps, []))
                   for tg in ("modem", "dsp"))
    return int((largest + 40) / (4 * 0.6)) + 1


def _form(ps, x, answer, **cfg):
    llm = ScriptedLlm(answer)
    plan = form_stories(llm, None, None, ps, x, StrongLlmConfig(base_url="http://x", model="big", **cfg), [])
    return plan, llm


def test_the_strong_model_forms_the_stories_with_its_titles_and_notes():
    c, a, ps, pid = _change()
    answer = {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71", _p(pid["modem_tx"], "starts_purpose"),
               _p(pid["modem_rx"], evidence=[pid["modem_tx"]]),
               related=["b"]),
        _story("b", "DSP runs a faster FFT", _p(pid["dsp_run"], "starts_purpose"), purpose="The DSP's FFT gets faster.")]}
    plan, llm = _form(ps, a.x, lambda s, u: answer)
    assert [(s.key, s.title, s.pieces, s.related, s.source) for s in plan.stories] == [
        ("a", "Modem radio gains band 71", [pid["modem_tx"], pid["modem_rx"]], ["b"], "tier1"),
        ("b", "DSP runs a faster FFT", [pid["dsp_run"]], [], "tier1")]
    assert plan.stories[0].check == ["Check the band tables."] and plan.notes == []
    prompt = llm.prompts[0]
    assert "1. Split the pieces by target." in prompt and "CHANGE OVERVIEW:" in prompt and ps.pieces[0].card in prompt


def test_each_placement_is_checked_on_its_own_and_failures_go_to_unsorted():
    c, a, ps, pid = _change({"modem/tx/a.c": 11, "modem/rx/b.c": 13, "dsp/run.c": 13})
    tx, rx, dsp = pid["modem_tx"], pid["modem_rx"], pid["dsp_run"]
    answer = {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71 support in every mode today",     # 10 words: over the headline limit
               _p(tx, "starts_purpose"), _p("P99"), _p(tx), _p(dsp, evidence=["CL13"])),
        _story("b", "Receive path", _p(rx, "starts_purpose", evidence=["P42"]))],
              "unsorted": []}
    plan, _ = _form(ps, a.x, lambda s, u: answer)
    (s1, unsorted) = plan.stories
    assert s1.pieces == [tx] and s1.title == ""                  # unknown P99 and the second tx dropped; title fails
    assert unsorted.unsorted and {pl.piece: pl.reason for pl in unsorted.placements} == {
        dsp: "target dsp differs from the story's (modem)", rx: "unknown evidence P42"}


def test_a_piece_from_another_cl_needs_a_link_or_a_quote_from_each_description():
    c, a, ps, pid = _change({"modem/tx/a.c": 11, "modem/rx/b.c": 12, "dsp/run.c": 13})
    tx, rx = pid["modem_tx"], pid["modem_rx"]

    def answer_with(quote, linked):
        ps.links = [lk for lk in ps.links if linked or lk.type != "call"]
        return {"action": "answer", "stories": [_story("a", "Band 71 support", _p(tx, "starts_purpose"),
                                                       _p(rx, "same_feature", quote=quote))]}
    for quote, linked, stands in ((["band 71"], True, True), ([], False, False), (["band 71 everywhere", "tables"], False, False),
                                  (["add LTE band 71", "band 71 tables"], False, True)):
        plan, _ = _form(ps, a.x, lambda s, u, q=quote, k=linked: answer_with(q, k))
        assert (rx in plan.stories[0].pieces) == stands, (quote, linked)


def test_the_model_reads_a_piece_s_code_before_it_answers():
    c, a, ps, pid = _change()

    def answer(system, user):
        if "READ piece_code" not in user:
            return {"action": "read", "tool": "piece_code", "arg": pid["modem_tx"]}
        assert "modem_tx (N1):" in user and "modem_tx_more();" in user
        story = _story("a", "Modem changes", _p(pid["modem_tx"], "starts_purpose"), _p(pid["modem_rx"]))
        return {"action": "answer", "stories": [story],
                "unsorted": [{"id": pid["dsp_run"], "reason": "unclear"}]}
    plan, llm = _form(ps, a.x, answer)
    assert len(llm.prompts) == 2 and plan.stories[-1].placements[0].reason == "unclear"


def test_a_chunk_that_fails_is_grouped_by_the_rules_and_the_plan_says_so():
    c, a, ps, pid = _change()
    plan, _ = _form(ps, a.x, lambda s, u: {"action": "read", "tool": "cl", "arg": "11"}, rounds=2)
    assert {s.source for s in plan.stories} == {"rules"}
    assert plan.notes == ["chunk 1: ValueError: no answer within the rounds allowed; the rules grouped its pieces"]


def test_large_changes_are_chunked_by_target_and_a_merge_pass_joins_them():
    c, a, ps, pid = _change()
    calls = []

    def answer(system, user):
        if "STORIES (key | title" in user:
            calls.append("merge")
            assert "c2a | Modem transmit" in user and "c1a | DSP runs a faster FFT" in user and "targets dsp" in user
            return {"related": [{"a": "c1a", "b": "c2a"}], "merge": [{"a": "c2a", "b": "c2b", "reason": "one feature"},
                                                                      {"a": "c2a", "b": "c1a", "reason": "no"}]}
        calls.append("chunk")
        mine = [p.id for p in ps.pieces if p.card in user]
        if "dsp" in ps.piece(mine[0]).targets:
            return {"action": "answer", "stories": [_story("a", "DSP runs a faster FFT", _p(mine[0], "starts_purpose"))]}
        return {"action": "answer", "stories": [_story("a", "Modem transmit", _p(mine[0], "starts_purpose")),
                                                _story("b", "Modem receive", _p(mine[1], "starts_purpose"))]}
    plan, _ = _form(ps, a.x, answer, context_tokens=_per_target(ps))          # one target to a chunk
    assert calls == ["chunk", "chunk", "merge"]
    assert [(s.key, s.related) for s in plan.stories] == [("c1a", ["c2a"]), ("c2a", ["c1a"])]   # dsp and modem never merge
    assert set(plan.stories[1].pieces) == {pid["modem_tx"], pid["modem_rx"]}


def test_agreement_mode_keeps_what_two_runs_agree_on_and_a_third_run_decides_the_rest():
    c, a, ps, pid = _change()
    tx, rx, dsp = pid["modem_tx"], pid["modem_rx"], pid["dsp_run"]
    runs = iter([[[tx, rx], [dsp]], [[tx], [rx], [dsp]], [[tx, rx], [dsp]]])

    def answer(system, user):
        groups = next(runs)
        return {"action": "answer", "stories": [
            _story(f"s{i}", f"Story {i}", *[_p(p, "starts_purpose" if j == 0 else "same_feature") for j, p in enumerate(g)])
            for i, g in enumerate(groups)]}
    plan, llm = _form(ps, a.x, answer, agree=2)
    assert len(llm.prompts) == 3
    assert sorted(sorted(s.pieces) for s in plan.stories) == sorted([sorted([tx, rx]), [dsp]])


def test_the_tier_1_budget_stops_tier_1_and_the_rules_take_the_rest(tmp_path):
    c, a, ps, pid = _change()
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    ledger = Ledger(store, LlmBudget(tier1_per_review=1))
    llm = ScriptedLlm(lambda s, u: {"action": "answer", "stories": [
        _story("a", "Some story", *[_p(p.id, "starts_purpose") for p in ps.pieces if p.card in u][:1])]})
    plan = form_stories(llm, ledger, rid, ps, a.x, StrongLlmConfig(base_url="http://x", model="big",
                                                                            context_tokens=_per_target(ps)), [])
    assert [s.source for s in plan.stories][:1] == ["tier1"] and "rules" in {s.source for s in plan.stories}
    assert plan.notes[0].startswith("chunk 2: AI budget: this review has used its 1 tier-1 AI calls")


def test_the_cache_key_changes_with_the_cards_the_rules_and_the_model():
    _, _, ps, _ = _change()
    k = cache_key(ps, "big", STORY_RULES_VERSION, 1)
    assert k == cache_key(_change()[2], "big", STORY_RULES_VERSION, 1)
    assert len({k, cache_key(ps, "other", STORY_RULES_VERSION, 1), cache_key(ps, "big", STORY_RULES_VERSION + 1, 1),
                cache_key(ps, "big", STORY_RULES_VERSION, 2)}) == 4
    ps.pieces[0].card += " "
    assert cache_key(ps, "big", STORY_RULES_VERSION, 1) != k


def test_only_a_brief_tier_1_formed_entirely_is_reused(tmp_path):
    from codetortoise.brief import Brief
    store = Store(tmp_path / "s.db")
    half, whole = store.create_review("t", "owner", [1]), store.create_review("t", "owner", [1])
    store.put_brief(half, "k", Brief(key="k", complete=False, overview="half"))
    assert store.find_brief("k") is None                     # a chunk fell back to the rules: the next run asks again
    store.put_brief(whole, "k", Brief(key="k", complete=True, overview="whole"))
    assert store.find_brief("k")["overview"] == "whole"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr("httpx.Client.post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
```

`backend/tests/test_web.py` (diff):

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index 8b59a75..6b9ba55 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -10,8 +10,8 @@ from codetortoise.web.app import create_app, make_authenticator
 class InlineRunner(JobRunner):
     """Runs jobs synchronously so tests are deterministic."""
 
-    def submit_review(self, rid):
-        run_review(rid, self.svc)
+    def submit_review(self, rid, fresh=False):
+        run_review(rid, self.svc, fresh=fresh)
 
     def submit_index(self):
         self.svc.build_index()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_tier1_stories.py tests/test_web.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.brief'`

- [ ] **Step 3: Implement**

`backend/codetortoise/brief.py` (new file):

```python
"""A review's brief (spec 2026-10-05-two-tier-stories §7.2): what tier 1 worked out, for tier 2 to start from.

It holds the change overview, the pieces and their links, the plan grouping them into stories, and each finding's
verdict and prepared facts (keyed by `facts_prep.finding_key`, so renumbering findings never breaks it). A brief made
entirely by the strong model is reused by a later run of the same change (its cache key)."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.grouping import StoryPlan
from codetortoise.pieces import PieceSet


class BriefVerdict(BaseModel):
    verdict: Literal["hazard", "needs_review", "no_hazard"]
    reason: str
    cites: list[str] = Field(default_factory=list)


class Brief(BaseModel):
    key: str = ""                     # cache key: the change as tier 1 saw it, the rules version and the model
    model: str = ""                   # "" : no strong model
    complete: bool = False            # tier 1 formed every story (no chunk fell back to the rules): reusable
    overview: str = ""
    pieces: PieceSet = Field(default_factory=PieceSet)
    plan: StoryPlan = Field(default_factory=StoryPlan)
    verdicts: dict[str, BriefVerdict] = Field(default_factory=dict)    # finding key -> tier 1's verdict
    facts: dict[str, str] = Field(default_factory=dict)                # finding key -> its prepared facts
    reviewed: list[str] = Field(default_factory=list)                  # story keys whose risk pass ran


def cache_key(ps: PieceSet, model: str, rules_version: int, agree: int) -> str:
    """Hash of what tier 1 is shown (cards, links, overview), the rules' version and the model."""
    blob = json.dumps({"cards": [p.card for p in ps.pieces], "links": [lk.model_dump() for lk in ps.links],
                       "overview": ps.overview, "rules": rules_version, "model": model, "agree": agree}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()

```

`backend/codetortoise/llm/stories.py` (new file):

```python
"""Tier 1 forms the stories (spec 2026-10-05-two-tier-stories §4).

The strong model gets fixed rules, the change overview, a chunk's piece cards, the links among them and the findings
tied to them, and may read more (a piece's code, a file's diff, a function's neighbours, a CL) in rounds that make
one AI call. Code checks every placement on its own; a failed one goes to the Unsorted story with the failure as its
reason. A change too large for one prompt (60% of the context) is cut into chunks: one target's pieces, split by CL,
then top directory; several chunks get a merge pass. `agree: 2` runs each chunk twice and lets a third run decide the
pieces they disagree on.
"""
from __future__ import annotations

import difflib
import posixpath
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import _Ctx
from codetortoise.config import StrongLlmConfig
from codetortoise.detectors.base import Finding
from codetortoise.grouping import REASONS, Placement, PlannedStory, StoryPlan, rules_plan
from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import _styled, _titled
from codetortoise.llm.style import MODES, STYLE
from codetortoise.pieces import Piece, PieceSet

STORY_RULES_VERSION = 1               # bump with every change to RULES or the prompts' wording
CHUNK_SHARE = 0.6                     # a chunk's prompt stays within this share of the context
JOINING = ("call", "field", "sub", "uses")   # links that let a piece of another CL join a story
QUOTE_MIN = 8                         # a quote shorter than this proves nothing

RULES = """Form the stories of this change for its reviewers. Follow these steps in order.
1. Split the pieces by target. Different targets are different stories. A shared piece goes with the story that uses it \
most (most links); other targets' stories that touch it name that story under "related".
2. Within each target, find the purposes: what each CL description says it does, and what each new-code piece adds.
3. Place every piece in the purpose it serves. New code goes with the edits that call it. A declaration piece goes with \
the story that uses its changes most.
4. Join pieces from different CLs only when a link joins them, or when both CL descriptions state the same purpose: then \
put one quote from each CL description, exactly as written, in "quote".
5. A story with more than 12 pieces or 40 changed functions must be split along its weakest links into purposes.
6. Give each story a title (at most 8 words: what changed and who is affected), a purpose (one sentence), what a \
reviewer should check (at most 3 steps), open questions (at most 3), and related stories by key.
7. Never place a piece twice. A piece you cannot place goes to "unsorted" with a reason.
Each placement has a reason: starts_purpose (the piece that defines the story), same_feature, caller_of_new_code, \
same_fix, same_refactor, shared_code (a shared piece in one target's story), declaration_used, split_too_big; and its \
evidence: the piece ids (P3) and CLs (CL412) it relies on."""

SYSTEM = ("You are a senior C/C++ reviewer forming the stories of a change for other reviewers. Use only what you are "
          "given or have read. Each turn reply with one JSON object: either "
          '{"action": "read", "tool": T, "arg": A} to read more, where T is "piece_code" (A: a piece id), "diff" (A: a '
          'file path as the cards show it), "neighbours" (A: a function name) or "cl" (A: a CL number); or '
          '{"action": "answer", "stories": [{"key", "title", "purpose", "check", "questions", "related", "pieces": '
          '[{"id", "reason", "evidence", "quote"}]}], "unsorted": [{"id", "reason"}]}. ' + STYLE)

MERGE = ("These stories were formed in separate parts of one change. Name related stories across the parts, and merge "
         "two stories only when they have the same targets and you can show they serve the same purpose. Reply with "
         '{"related": [{"a", "b"}], "merge": [{"a", "b", "reason"}]}; a merge moves story b into story a.')


class _Placed(BaseModel):
    id: str
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    quote: list[str] = Field(default_factory=list)


class _Story(BaseModel):
    key: str
    title: str = ""
    purpose: str = ""
    check: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    pieces: list[_Placed] = Field(default_factory=list)


class _Unplaced(BaseModel):
    id: str
    reason: str = ""


class _Step(BaseModel):
    action: Literal["read", "answer"]
    tool: str = ""
    arg: str | int = ""
    stories: list[_Story] = Field(default_factory=list)
    unsorted: list[_Unplaced] = Field(default_factory=list)


class _Pair(BaseModel):
    a: str
    b: str
    reason: str = ""


class _MergeOut(BaseModel):
    related: list[_Pair] = Field(default_factory=list)
    merge: list[_Pair] = Field(default_factory=list)


@dataclass
class Got:
    """A chunk's checked answer: its stories and the pieces it could not place."""
    stories: list[PlannedStory] = field(default_factory=list)
    unsorted: list[Placement] = field(default_factory=list)


# ------------------------------------------------------------------ tools
class Tools:
    """What the strong model may read: a piece's code, a file's diff, a function's neighbours, a CL."""

    def __init__(self, x: _Ctx, ps: PieceSet):
        self.x, self.ps = x, ps

    def _rel(self, path: str) -> str:
        root = self.x.c.root.rstrip("/") + "/"
        return path[len(root):] if self.x.c.root and path.startswith(root) else path

    def _fn(self, nid: str) -> str:
        x = self.x
        n = x.im.nodes[nid]
        out = [f"{n.label} ({nid}):"]
        for side, fns in (("before", x.fb), ("after", x.fa)):
            fn = fns.get(n.key)
            fc = x.texts.get(fn.file) if fn else None
            if fn is None or fc is None:
                out.append(f"  {side}: (none)")
                continue
            rows = (fc.before if side == "before" else fc.after).splitlines()
            lo, hi = max(1, fn.start_line - 3), min(len(rows), fn.end_line + 3)
            code = "\n".join(f"{i:5} {rows[i - 1]}" for i in range(lo, hi + 1))
            out.append(f"  {side} ({self._rel(fn.file)}:{lo}-{hi}):\n{code}")
        return "\n".join(out)

    def piece_code(self, pid: str) -> str:
        p = self.ps.piece(pid.strip())
        if p is None:
            return f"no piece {pid}"
        if p.kind == "declarations":
            return "\n".join(self.diff(f) for f in p.files)
        return "\n\n".join(self._fn(n) for n in p.nodes)[:8000]

    def diff(self, path: str) -> str:
        path = path.strip()
        fc = next((f for f in self.x.c.cs.files if path in (f.local, f.depot, self._rel(f.local))), None)
        if fc is None:
            return f"{path} is not in this change"
        text = "\n".join(difflib.unified_diff(fc.before.splitlines(), fc.after.splitlines(), "before", "after", n=3,
                                              lineterm=""))
        return f"DIFF {self._rel(fc.local)}:\n" + (text[:8000] or "(no line changes)")

    def neighbours(self, name: str) -> str:
        x = self.x
        nid = next((i for i, n in x.im.nodes.items() if n.kind == "function" and n.label == name.strip()), None)
        if nid is None:
            return f"no function named {name}"

        def tag(m: str) -> str:
            return f"{x.label(m)} ({m}{', changed' if m in x.changed else ''})"
        return (f"{x.label(nid)} ({nid}):\n  callers: " + (", ".join(tag(m) for m in sorted(x.callers.get(nid, ()))) or "none")
                + "\n  callees: " + (", ".join(tag(m) for m in sorted(x.callees.get(nid, ()))) or "none"))

    def cl(self, n: str | int) -> str:
        raw = str(n).strip().upper().removeprefix("CL").strip()
        num = int(raw) if raw.isdigit() else None
        meta = next((m for m in self.x.c.cs.cls if m.cl == num), None)
        if meta is None:
            return f"no CL {n} in this change"
        files = [f.depot for f in self.x.c.cs.files if any(p.cl == num for p in f.per_cl)]
        return f"CL {num} ({meta.status}, {meta.user}):\n{meta.description}\nfiles: " + ", ".join(files)

    def run(self, tool: str, arg: str | int) -> str:
        fn = {"piece_code": self.piece_code, "diff": self.diff, "neighbours": self.neighbours, "cl": self.cl}.get(tool)
        return fn(arg if tool == "cl" else str(arg)) if fn else f"no tool {tool}"


# ------------------------------------------------------------------ prompts and chunks
def _chunk_target(p: Piece, ps: PieceSet) -> str:
    """A piece's chunk: its target; a shared piece goes with the target it has most links to."""
    if not p.shared:
        return p.targets[0]
    weight: dict[str, int] = defaultdict(int)
    for lk in ps.links_of(p.id):
        other = ps.piece(lk.b if lk.a == p.id else lk.a)
        if other is not None and not other.shared and other.targets[0] in p.targets:
            weight[other.targets[0]] += lk.count
    return max(p.targets, key=lambda t: (weight[t], -p.targets.index(t)))


def _findings_of(ids: list[str], ps: PieceSet, findings: list[Finding]) -> list[str]:
    out = []
    for f in findings:
        mine = [p.id for p in ps.pieces if p.id in ids and (set(f.nodes) & set(p.nodes) or (
            p.kind == "declarations" and any(e.file in p.files for e in f.evidence)))]
        if mine:
            out.append(f"{f.id} [{f.severity}] {f.kind}: {f.title} — {', '.join(mine)}")
    return out


def chunk_parts(ids: list[str], ps: PieceSet, findings: list[Finding]) -> list[str]:
    """The prompt of one chunk: rules and overview, its cards and links, its findings."""
    keep = set(ids)
    cards = "\n\n".join(p.card for p in ps.pieces if p.id in keep)
    links = "\n".join(f"{lk.a} {lk.b} {lk.type} ×{lk.count}" for lk in ps.links if lk.a in keep and lk.b in keep)
    return [RULES + "\n\nCHANGE OVERVIEW:\n" + ps.overview,
            "PIECES:\n" + cards + "\n\nLINKS (piece, piece, type, count):\n" + (links or "none"),
            "FINDINGS:\n" + ("\n".join(_findings_of(ids, ps, findings)) or "none")]


def chunks(ps: PieceSet, findings: list[Finding], limit: int) -> list[list[str]]:
    """Piece ids per chunk: the whole change when it fits in `limit` chars, else one target's pieces, split by CL, then
    by top directory, then evenly, while past the limit."""
    def size(ids: list[str]) -> int:
        return sum(len(p) for p in chunk_parts(ids, ps, findings))

    root = posixpath.commonpath([f for q in ps.pieces for f in q.files] or ["/"])

    def top(p: Piece) -> str:
        rel = posixpath.relpath(p.files[0], root) if p.files else ""
        return rel.split("/")[0] if "/" in rel else ""

    def split(ids: list[str], keys: list[Callable[[Piece], object]]) -> list[list[str]]:
        if size(ids) <= limit or len(ids) == 1:
            return [ids]
        if not keys:
            half = len(ids) // 2
            return split(ids[:half], []) + split(ids[half:], [])
        groups: dict[object, list[str]] = defaultdict(list)
        for pid in ids:
            groups[keys[0](ps.piece(pid))].append(pid)
        if len(groups) == 1:
            return split(ids, keys[1:])
        return [c for _, g in sorted(groups.items(), key=lambda kv: str(kv[0])) for c in split(g, keys[1:])]
    every = [p.id for p in ps.pieces]
    if size(every) <= limit:                                 # fits in one prompt: one chunk, no merge pass
        return [every]
    by_target: dict[str, list[str]] = defaultdict(list)
    for p in ps.pieces:
        by_target[_chunk_target(p, ps)].append(p.id)
    return [c for t in sorted(by_target) for c in split(by_target[t], [lambda p: p.cl or 0, top])]


def _fit(convo: list[str], limit: int) -> str:
    """The fixed parts, then the newest reads that fit within `limit` chars."""
    head = "\n\n".join(convo[:3])
    room, kept = limit - len(head), []
    for r in reversed(convo[3:]):
        if len(r) + 2 > room:
            break
        kept.insert(0, r)
        room -= len(r) + 2
    return head + "".join("\n\n" + r for r in kept)


def ask(strong: LlmClient, parts: list[str], tools: Tools, rounds: int, limit: int) -> _Step:
    """One chunk's rounds (one AI call): reads until the model answers; the last round must answer."""
    convo = list(parts)
    for n in range(1, max(1, rounds) + 1):
        last = n == max(1, rounds)
        step = strong.complete_json(SYSTEM, _fit(convo, limit) + (
            '\n\nYou must answer now: reply with action "answer".' if last else "")
            + f"\nPurposes and questions: {MODES['explanation']} Checks: {MODES['how-to']} Titles: {MODES['headline']}",
            _Step)
        if step.action == "answer":
            return step
        if last:
            break
        convo.append(f"READ {step.tool} {step.arg} ->\n" + tools.run(step.tool, step.arg))
    raise ValueError("no answer within the rounds allowed")


# ------------------------------------------------------------------ checks
def _linked(ps: PieceSet, a: str, members: list[str]) -> bool:
    """A call, field, substitution or declaration link joins piece `a` to one of `members`."""
    return any(lk.type in JOINING and (lk.b if lk.a == a else lk.a) in members for lk in ps.links_of(a))


def _quoted(quotes: list[str], one: str, other: str) -> bool:
    """One quote found verbatim in each of the two CLs' descriptions."""
    good = [q.strip() for q in quotes if len(q.strip()) >= QUOTE_MIN]
    return any(q in one for q in good) and any(q in other for q in good)


def place(ps: PieceSet, cls: dict[int, str], members: list[str], first: Piece, p: Piece, pl: Placement) -> str | None:
    """Why a placement fails the checks (spec §4.4), or None when it stands."""
    known = {q.id for q in ps.pieces}
    bad = [e for e in pl.evidence if e not in known and not (e.startswith("CL") and e[2:].isdigit() and int(e[2:]) in cls)]
    if bad:
        return f"unknown evidence {', '.join(bad)}"
    if pl.reason not in REASONS:
        return f"unknown reason {pl.reason!r}"
    if p.targets != first.targets and not (pl.reason == "shared_code" and p.shared and set(first.targets) <= set(p.targets)):
        return f"target {', '.join(p.targets)} differs from the story's ({', '.join(first.targets)})"
    if p.cl != first.cl and not _linked(ps, p.id, members) and not _quoted(pl.quote, cls.get(first.cl or 0, ""),
                                                                           cls.get(p.cl or 0, "")):
        return f"CL {p.cl} differs from the story's (CL {first.cl}) with no link or quote"
    return None


def check_answer(step: _Step, chunk: list[str], ps: PieceSet, cls: dict[int, str], prefix: str = "") -> Got:
    """Each placement checked on its own; failures, unplaced pieces and the model's own unsorted go to unsorted."""
    allowed, placed, got = set(chunk), set(), Got()
    keys = {s.key for s in step.stories}
    for s in step.stories:
        ps_: list[Placement] = []
        first: Piece | None = None
        for raw in s.pieces:
            p = ps.piece(raw.id) if raw.id in allowed else None
            if p is None or raw.id in placed:
                continue                                         # unknown, another chunk's, or placed twice: dropped
            pl = Placement(piece=raw.id, reason=raw.reason, evidence=list(raw.evidence), quote=list(raw.quote))
            why = place(ps, cls, [q.piece for q in ps_], first or p, p, pl)
            placed.add(raw.id)
            if why is None:
                ps_.append(pl)
                first = first or p
            else:
                got.unsorted.append(Placement(piece=raw.id, reason=why))
        if not ps_:
            continue
        title = s.title.strip()
        got.stories.append(PlannedStory(
            key=prefix + s.key, source="tier1", placements=ps_,
            title=title if 0 < len(title) <= 80 and _titled(title) else "",
            purpose=s.purpose.strip() if s.purpose.strip() and _styled(s.purpose, "explanation") else "",
            check=[c.strip() for c in s.check if c.strip() and _styled(c, "how-to")][:3],
            questions=[q.strip() for q in s.questions if q.strip() and _styled(q, "explanation")][:3],
            related=[prefix + r for r in s.related if r in keys and r != s.key]))
    for u in step.unsorted:
        if u.id in allowed and u.id not in placed:
            placed.add(u.id)
            got.unsorted.append(Placement(piece=u.id, reason=u.reason.strip() or "the model could not place it"))
    for pid in chunk:
        if pid not in placed:
            got.unsorted.append(Placement(piece=pid, reason="the model did not place it"))
    return got


# ------------------------------------------------------------------ agreement and merging
def _groups(got: Got) -> dict[str, frozenset[str]]:
    out = {pl.piece: frozenset(s.pieces) for s in got.stories for pl in s.placements}
    out.update({pl.piece: frozenset([pl.piece]) for pl in got.unsorted})
    return out


def agree(first: Got, second: Got, third: Callable[[], Got], ps: PieceSet, cls: dict[int, str]) -> Got:
    """Two pieces share a story when both runs put them together; a piece the runs disagree on goes where a third run
    puts it (into the agreed story sharing most pieces with its story there). Titles and notes come from the first."""
    g1, g2 = _groups(first), _groups(second)
    sure = {p for p in g1 if g1[p] == g2.get(p)}
    out = Got(stories=[s.model_copy(update={"placements": [pl for pl in s.placements if pl.piece in sure]}, deep=True)
                       for s in first.stories],
              unsorted=[pl for pl in first.unsorted if pl.piece in sure])
    unsure = sorted((p for p in g1 if p not in sure), key=lambda p: [q.id for q in ps.pieces].index(p))
    if unsure:
        g3 = third()
        for pid in unsure:
            mine = next((s for s in g3.stories if pid in s.pieces), None)
            if mine is None:
                out.unsorted.append(next((pl for pl in g3.unsorted if pl.piece == pid),
                                         Placement(piece=pid, reason="the runs disagreed")))
                continue
            pl = next(pl for pl in mine.placements if pl.piece == pid)
            best = max(out.stories, key=lambda s: len(set(s.pieces) & set(mine.pieces)), default=None)
            if best is not None and set(best.pieces) & set(mine.pieces):
                first_p = ps.piece(best.placements[0].piece) if best.placements else ps.piece(pid)
                why = place(ps, cls, best.pieces, first_p, ps.piece(pid), pl)
                if why is None:
                    best.placements.append(pl)
                else:
                    out.unsorted.append(Placement(piece=pid, reason=why))
            else:
                new = next((s for s in out.stories if s.key == "x" + mine.key), None)
                if new is None:
                    new = mine.model_copy(update={"key": "x" + mine.key, "placements": []}, deep=True)
                    out.stories.append(new)
                new.placements.append(pl)
    out.stories = [s for s in out.stories if s.placements]
    return out


def _targets(s: PlannedStory, ps: PieceSet) -> list[str]:
    return ps.piece(s.placements[0].piece).targets if s.placements else []


def merge_pass(strong: LlmClient, stories: list[PlannedStory], ps: PieceSet, cls: dict[int, str]) -> Got:
    """Across chunks: related stories, and merges of same-target stories checked as placements are."""
    lines = []
    for s in stories:
        cl_set = sorted({ps.piece(p).cl or 0 for p in s.pieces})
        lines.append(f"{s.key} | {s.title or '(untitled)'} | {s.purpose or '-'} | targets {', '.join(_targets(s, ps))} | "
                     f"CLs {', '.join(map(str, cl_set))} | pieces {', '.join(s.pieces)}")
    out = strong.complete_json(SYSTEM, MERGE + "\n\nSTORIES (key | title | purpose | targets | CLs | pieces):\n"
                               + "\n".join(lines), _MergeOut)
    by_key = {s.key: s for s in stories}
    got = Got(stories=list(stories))
    for m in out.merge:
        a, b = by_key.get(m.a), by_key.get(m.b)
        if a is None or b is None or a is b or a not in got.stories or b not in got.stories or _targets(a, ps) != _targets(b, ps):
            continue
        first = ps.piece(a.placements[0].piece)
        for pl in b.placements:
            why = place(ps, cls, a.pieces, first, ps.piece(pl.piece), pl)
            if why is None:
                a.placements.append(pl)
            else:
                got.unsorted.append(Placement(piece=pl.piece, reason=f"merge: {why}"))
        got.stories.remove(b)
        for s in got.stories:
            s.related = list(dict.fromkeys(a.key if r == b.key else r for r in s.related if r != s.key))
    for r in out.related:
        a, b = by_key.get(r.a), by_key.get(r.b)
        if a in got.stories and b in got.stories and a is not b:
            a.related = list(dict.fromkeys(a.related + [b.key]))
            b.related = list(dict.fromkeys(b.related + [a.key]))
    return got


# ------------------------------------------------------------------ the stage
def form_stories(strong: LlmClient, ledger: Ledger | None, rid: int | None, ps: PieceSet, x: _Ctx,
                 cfg: StrongLlmConfig, findings: list[Finding]) -> StoryPlan:
    """Tier 1's plan for the whole change. A chunk that fails (or is refused by the budget) is grouped by the rules,
    and the plan's notes say so."""
    limit = int(cfg.context_tokens * 4 * CHUNK_SHARE)
    cls = {m.cl: m.description for m in x.c.cs.cls}
    tools = Tools(x, ps)
    groups = chunks(ps, findings, limit)
    stories: list[PlannedStory] = []
    unsorted: list[Placement] = []
    notes: list[str] = []
    refused = False

    def call(purpose: str, target: str, fn):
        return ledger.call(strong, rid, None, purpose, target, fn) if ledger is not None else fn(strong)
    for i, ids in enumerate(groups, 1):
        prefix = f"c{i}" if len(groups) > 1 else ""
        parts = chunk_parts(ids, ps, findings)

        def run(n: int = 1, ids=ids, parts=parts, prefix=prefix, i=i) -> Got:
            step = call("stories", f"chunk {i}" + (f" run {n}" if n > 1 else ""),
                        lambda llm: ask(llm, parts, tools, cfg.rounds, int(cfg.context_tokens * 4 * 0.9)))
            return check_answer(step, ids, ps, cls, prefix)
        try:
            if refused:
                raise Refused("the tier-1 budget ran out")
            got = agree(run(1), run(2), lambda: run(3), ps, cls) if cfg.agree >= 2 else run(1)
        except Refused as e:
            refused = True
            notes.append(f"chunk {i}: AI budget: {e.reason}; the rules grouped its pieces")
            got = Got(stories=rules_plan(ps, ids, prefix=f"r{i}_"))
        except Exception as e:  # a chunk that fails falls back to the rules; the others stand
            notes.append(f"chunk {i}: {type(e).__name__}: {e}"[:300] + "; the rules grouped its pieces")
            got = Got(stories=rules_plan(ps, ids, prefix=f"r{i}_"))
        stories += got.stories
        unsorted += got.unsorted
    tier1 = [s for s in stories if s.source == "tier1"]
    if len(groups) > 1 and len(tier1) > 1 and not refused:
        try:
            merged = call("stories_merge", "merge", lambda llm: merge_pass(llm, tier1, ps, cls))
            stories = merged.stories + [s for s in stories if s.source != "tier1"]
            unsorted += merged.unsorted
        except Exception as e:  # the chunks' stories stand unmerged
            notes.append(f"merge pass: {type(e).__name__}: {e}"[:300])
    if unsorted:
        stories.append(PlannedStory(key="unsorted", unsorted=True, source="tier1", placements=unsorted))
    return StoryPlan(stories=stories, notes=notes)
```

`backend/codetortoise/pipeline.py` (diff):

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 45b1416..837150a 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -11,12 +11,14 @@ from pathlib import Path
 
 from codetortoise import boardstore
 from codetortoise.board import BoardContext, analyse, build_boards
+from codetortoise.brief import Brief, cache_key
 from codetortoise.detectors.base import DetectorContext, renumber, run_detectors
 from codetortoise.diffmap import map_changes
 from codetortoise.facts.model import Facts, relative_records
 from codetortoise.facts.runner import build_requests, parse_summary, run_extraction
 from codetortoise.grouping import StoryPlan, rules_plan
 from codetortoise.impact import ImpactModel, build_impact
+from codetortoise.llm.stories import STORY_RULES_VERSION, form_stories
 from codetortoise.llm.storyboard import AiContext, build_storyboard, judge_side_effects
 from codetortoise.paths import canon
 from codetortoise.pieces import build_pieces
@@ -100,7 +102,9 @@ def system_include_dirs(toolchain) -> list[str]:
         dirs += [*info.include_dirs, *([info.resource_dir] if info.resource_dir else [])]
     return dirs
 
-def run_review(rid: int, svc: Services) -> None:
+def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
+    """Run every stage of review `rid`. `fresh`: the strong model forms the stories again, even for a change it has
+    seen (no cached brief)."""
     store, cfg = svc.store, svc.cfg
     store.reset_stages(rid, STAGES)
     store.set_review_status(rid, "running")
@@ -240,17 +244,38 @@ def run_review(rid: int, svc: Services) -> None:
         targets = resolve_targets(files, cfg.targets, bctx.root, svc.cdb, str(ws.build_root) if ws.build_root else None,
                                   triple, svc.index.transitive_includers)
         ps = build_pieces(bctx, a, targets, svc.index.transitive_includers, rep)
-        ctx["pieces"], ctx["repeated"] = ps, rep
+        ctx["pieces"], ctx["repeated"], ctx["analysis"] = ps, rep, a
         store.put_blob(rid, "pieces", ps)
         names = sorted({t for p in ps.pieces for t in p.targets})
         return f"{len(ps.pieces)} piece(s), {len(ps.links)} link(s); target(s): {', '.join(names) or 'none'}"
 
     def stories():
-        """Which pieces form which story: the rules' grouping (spec §6)."""
-        ps = ctx["pieces"]
-        plan = StoryPlan(stories=rules_plan(ps))
-        ctx["plan"] = plan
-        return f"{len(plan.stories)} stories from {len(ps.pieces)} piece(s), by the rules"
+        """Which pieces form which story: the strong model's plan (spec §4), reused for a change it has seen, or the
+        rules' (§6). The plan is stored as the review's brief."""
+        ps, strong = ctx["pieces"], cfg.llm.strong
+        if svc.strong is None or strong is None:
+            plan = StoryPlan(stories=rules_plan(ps))
+            brief = Brief(overview=ps.overview, pieces=ps, plan=plan)
+            msg = f"{len(plan.stories)} stories from {len(ps.pieces)} piece(s), by the rules (no strong model configured)"
+        else:
+            key = cache_key(ps, strong.model, STORY_RULES_VERSION, strong.agree)
+            hit = None if fresh else store.find_brief(key)
+            if hit is not None:
+                brief = Brief.model_validate(hit)
+                brief.pieces, brief.overview, plan = ps, ps.overview, brief.plan
+            else:
+                plan = form_stories(svc.strong, svc.ledger, rid, ps, ctx["analysis"].x, strong, ctx["findings"])
+                brief = Brief(key=key, model=strong.model, complete=not plan.notes, overview=ps.overview, pieces=ps,
+                              plan=plan)
+            unsorted = sum(len(s.placements) for s in plan.stories if s.unsorted)
+            formed = [s for s in plan.stories if not s.unsorted]
+            msg = (f"{len(formed)} stories formed by {strong.model}" + (" (reused: this change was seen before)" if hit else "")
+                   + f", {sum(len(s.placements) for s in formed)} piece(s) placed, {unsorted} unsorted")
+        ctx["plan"], ctx["brief"] = plan, brief
+        store.put_brief(rid, brief.key, brief)
+        if plan.notes:
+            raise Degraded(msg + "; " + "; ".join(plan.notes))
+        return msg
 
     def verdicts():
         """The AI judges side effects before the board is drawn, so flows and stories take the verdicts' colours."""
@@ -398,9 +423,9 @@ class JobRunner:
     def start(self) -> None:
         self._thread.start()
 
-    def submit_review(self, rid: int) -> None:
+    def submit_review(self, rid: int, fresh: bool = False) -> None:
         self.svc.store.set_review_status(rid, "queued")
-        self._q.put(("review", rid))
+        self._q.put(("review", (rid, fresh)))
 
     def submit_index(self) -> None:
         self._q.put(("index", None))
@@ -416,7 +441,7 @@ class JobRunner:
             kind, arg = job
             try:
                 if kind == "review":
-                    run_review(arg, self.svc)
+                    run_review(arg[0], self.svc, fresh=arg[1])
                 elif kind == "index":
                     self.index_building = True
                     self.svc.build_index()
```

`backend/codetortoise/store.py` (diff):

```diff
diff --git a/backend/codetortoise/store.py b/backend/codetortoise/store.py
index 04343ae..b19b5a9 100644
--- a/backend/codetortoise/store.py
+++ b/backend/codetortoise/store.py
@@ -38,6 +38,8 @@ CREATE INDEX IF NOT EXISTS ix_llm_calls_review ON llm_calls(review_id);
 CREATE INDEX IF NOT EXISTS ix_llm_calls_user ON llm_calls(user, started_at);
 CREATE TABLE IF NOT EXISTS llm_budget(review_id INTEGER, budget INTEGER, set_by TEXT, set_at TEXT);
 CREATE TABLE IF NOT EXISTS llm_rounds(review_id INTEGER, rounds INTEGER, set_by TEXT, set_at TEXT);
+CREATE TABLE IF NOT EXISTS briefs(review_id INTEGER PRIMARY KEY, cache_key TEXT, json TEXT, created_at TEXT);
+CREATE INDEX IF NOT EXISTS ix_briefs_key ON briefs(cache_key);
 """
 
 ANCHOR_KINDS = {"line", "function", "finding", "chapter", "review", "story", "flow", "file"}
@@ -261,6 +263,23 @@ class Store:
     def swarm_posts(self, rid: int, cl: int) -> list[dict]:
         return self._all("SELECT kind, swarm_id, posted_at FROM swarm_posts WHERE review_id=? AND cl=?", (rid, cl))
 
+    # ---- briefs (spec 2026-10-05-two-tier-stories §7.2) ------------------------
+    def put_brief(self, rid: int, key: str, brief: BaseModel) -> None:
+        self._exec("INSERT INTO briefs VALUES(?,?,?,?) ON CONFLICT(review_id) DO UPDATE SET cache_key=excluded.cache_key, "
+                   "json=excluded.json, created_at=excluded.created_at", (rid, key, brief.model_dump_json(), _now()))
+
+    def get_brief(self, rid: int) -> dict | None:
+        rows = self._all("SELECT json FROM briefs WHERE review_id=?", (rid,))
+        return json.loads(rows[0]["json"]) if rows else None
+
+    def find_brief(self, key: str) -> dict | None:
+        """The newest complete brief stored under a cache key, from any review."""
+        for r in self._all("SELECT json FROM briefs WHERE cache_key=? ORDER BY created_at DESC", (key,)):
+            got = json.loads(r["json"])
+            if got.get("complete"):
+                return got
+        return None
+
     def kv_get(self, key: str) -> Any:
         rows = self._all("SELECT json FROM kv WHERE key=?", (key,))
         return json.loads(rows[0]["json"]) if rows else None
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_tier1_stories.py tests/test_web.py -q`
Expected: PASS: `54 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `492 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/scripted_llm.py backend/tests/test_pipeline.py backend/tests/test_tier1_stories.py backend/tests/test_web.py backend/codetortoise/brief.py backend/codetortoise/llm/stories.py backend/codetortoise/pipeline.py backend/codetortoise/store.py
git commit -m "feat(stories): tier 1 forms the stories — checked placements, chunks and a merge pass, agreement mode, briefs cached by the change's cards"
```

### Task 7: Tier 1 reviews each story's risks

Spec §5.2, §5.3, §7.1. A new **review** stage runs after stories. It prepares the facts of every finding (Task 4) and stores them in the brief. With a strong model, `review_stories` makes one call per story that has findings. Each call carries the story's title and purpose, its cards, and for each finding its facts and fixed question; the model may use the same tools. Each answer is `hazard`, `needs_review` or `no_hazard` with a reason, and cites node ids or file:line. A cite counts only when it appears in what the model was shown, or is a line inside a range it was shown. A verdict with no such cite is discarded and the finding stays as the detectors left it.

`apply_verdicts` records each verdict on its finding with `verdict_source: "tier1"`, sets the severity from it and renumbers. A reused brief brings its verdicts, and only the stories it has not reviewed are asked. The `verdicts` stage now judges only the side effects tier 1 did not answer. `ask` gains `system`, `schema`, `tail` and `seen` parameters so both passes share it. `Finding` gains `needs_review`, `verdict_cites` and `verdict_source`; tier 2's own verdicts record `"tier2"`.

**Files:**
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_tier1_review.py`
- Test: `backend/tests/test_web.py`
- Modify: `backend/codetortoise/detectors/base.py`
- Create: `backend/codetortoise/llm/review.py`
- Modify: `backend/codetortoise/llm/stories.py`
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `backend/codetortoise/pipeline.py`

**Interfaces:**
- Consumes: `prepare_facts`, `finding_key` (Task 4); `Brief`, `ask`, `Tools` (Task 6); `renumber`.
- Produces: `llm.review.SEVERITY`, `QUESTIONS`, `question(f) -> str`, `review_parts(s, ps, mine, facts) -> list[str]`,
  `review_stories(strong, ledger, rid, plan, ps, x, cfg, findings, facts, skip=None) -> Reviewed(verdicts, reviewed, notes)`,
  `apply_verdicts(findings, verdicts) -> int`; `llm.stories.pieces_of(f, ps) -> list[str]`;
  `Finding.verdict: "hazard" | "needs_review" | "no_hazard" | None`, `Finding.verdict_cites: list[str]`, `Finding.verdict_source: "tier1" | "tier2" | None`; pipeline stage `review` between `stories` and `verdicts`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pipeline.py` (diff):

```diff
diff --git a/backend/tests/test_pipeline.py b/backend/tests/test_pipeline.py
index 67ff5f2..8c992fc 100644
--- a/backend/tests/test_pipeline.py
+++ b/backend/tests/test_pipeline.py
@@ -17,10 +17,12 @@ def test_full_review_without_llm_or_swarm(fx, tmp_path):
     run_review(rid, svc)
     assert stages(svc, rid) == {"ingest": "ok", "swarm_read": "degraded", "diffmap": "ok", "tu_select": "ok",
                                 "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok", "pieces": "ok",
-                                "stories": "ok", "verdicts": "ok", "board": "ok", "llm": "degraded", "finalize": "ok"}
+                                "stories": "ok", "review": "ok", "verdicts": "ok", "board": "ok", "llm": "degraded",
+                                "finalize": "ok"}
     msgs = {s["name"]: s["message"] for s in svc.store.list_stages(rid)}
     assert msgs["pieces"].endswith("target(s): compile_commands")
     assert msgs["stories"].endswith("by the rules (no strong model configured)")
+    assert msgs["review"] == "no strong model: 6 finding(s) left to the detectors and the AI's side-effect pass"
     ss = svc.store.get_blob(rid, "stories")
     assert all(s["targets"] == ["compile_commands"] and s["pieces"] for s in ss["stories"])
     review = svc.store.get_review(rid)
@@ -375,8 +377,13 @@ def _strong(svc, answer, model="big"):
 
 
 def _one_story_per_cl(system, user):
-    """Every piece of a CL in one story (the pieces' cards name their CL)."""
+    """Every piece of a CL in one story (the pieces' cards name their CL); every finding reviewed as no hazard, citing
+    the first node its prompt shows."""
     import re
+    if "QUESTION:" in user:
+        node = re.search(r"\bN\d+\b", user.split("FINDINGS:", 1)[1])[0]
+        return {"action": "answer", "verdicts": [{"finding": f, "verdict": "no_hazard", "reason": "Nothing reads it.",
+                                                  "cites": [node]} for f in re.findall(r"^(F\d+) \[", user, re.M)]}
     if "STORIES (key | title" in user:
         return {"related": [], "merge": []}
     by_cl: dict[str, list[str]] = {}
@@ -418,3 +425,21 @@ def test_a_strong_model_that_fails_leaves_the_rules_stories_and_says_so(fx, tmp_
     assert "chunk 1: RuntimeError: the endpoint is down; the rules grouped its pieces" in st["message"]
     assert {s["source"] for s in svc.store.get_blob(rid, "stories")["stories"]} == {"rules"}
     assert svc.store.get_brief(rid)["complete"] is False
+
+
+def test_the_strong_model_reviews_each_story_s_findings_and_tier_2_leaves_them_alone(fx, tmp_path):
+    svc = make_services(fx, tmp_path)
+    llm = _strong(svc, _one_story_per_cl)
+    rid = svc.store.create_review("t", "owner", [101, 102])
+    run_review(rid, svc)
+    msgs = {s["name"]: (s["status"], s["message"]) for s in svc.store.list_stages(rid)}
+    assert msgs["review"] == ("ok", "6 finding(s) judged by big: 0 hazard(s), 0 to confirm, 6 no hazard")
+    assert msgs["verdicts"] == ("ok", "all 2 side effect(s) judged by the strong model")
+    findings = svc.store.list_findings(rid)
+    assert {(f.severity, f.verdict, f.verdict_source) for f in findings} == {("info", "no_hazard", "tier1")}
+    assert all(f.verdict_cites for f in findings)
+    brief = svc.store.get_brief(rid)
+    assert len(brief["verdicts"]) == 6 and "drv" not in brief["facts"] and len(brief["facts"]) == 6
+    calls = len(llm.prompts)
+    run_review(rid, svc)                                            # the brief brings its verdicts: no call at all
+    assert len(llm.prompts) == calls and len(svc.store.get_brief(rid)["verdicts"]) == 6
```

`backend/tests/test_tier1_review.py` (new file):

```python
"""Tier 1 reviews each story's risks (spec 2026-10-05-two-tier-stories §5)."""
import pytest
from scripted_llm import ScriptedLlm
from test_stories import W, _edit, _same, _world

from codetortoise.board import analyse
from codetortoise.config import LlmBudget, StrongLlmConfig
from codetortoise.detectors.base import Finding
from codetortoise.facts_prep import finding_key, prepare_facts
from codetortoise.grouping import Placement, PlannedStory, StoryPlan
from codetortoise.llm.ledger import Ledger
from codetortoise.llm.review import apply_verdicts, review_stories
from codetortoise.pieces import build_pieces
from codetortoise.store import Store

CFG = StrongLlmConfig(base_url="http://x", model="big")


def _change():
    """hal_write's signature changed; uart_send was updated, old_user was not; dsp_run is another story."""
    c = _world([_edit("hal_write", "hal/regs.c"), _edit("uart_send", "drv/uart.c"), _same("old_user", "drv/old.c"),
                _edit("dsp_run", "dsp/run.c")],
               calls=[("uart_send", "hal_write"), ("old_user", "hal_write")])
    a = analyse(c)
    t = {f"{W}/hal/regs.c": ["fw"], f"{W}/drv/uart.c": ["fw"], f"{W}/drv/old.c": ["fw"], f"{W}/dsp/run.c": ["dsp"]}
    ps = build_pieces(c, a, t)
    sig = Finding(id="F1", kind="contract", severity="medium", title="hal_write: signature changed", summary="s",
                  nodes=["N1"])
    dsp = Finding(id="F2", kind="other_kind", severity="low", title="dsp_run: something", summary="s", nodes=["N4"])
    pid = {c.impact.nodes[p.nodes[0]].label: p.id for p in ps.pieces}
    hal = [pid["hal_write"]] + [pid["uart_send"]] * (pid["uart_send"] != pid["hal_write"])
    plan = StoryPlan(stories=[
        PlannedStory(key="a", title="HAL writes take a width", purpose="This widens the HAL write.", source="tier1",
                     placements=[Placement(piece=p, reason="same_feature") for p in hal]),
        PlannedStory(key="b", title="DSP runs faster", source="tier1",
                     placements=[Placement(piece=pid["dsp_run"], reason="starts_purpose")])])
    findings = [sig, dsp]
    facts = prepare_facts(a.x, findings, t)
    return a, ps, plan, findings, facts


def _verdicts(*vs):
    return {"action": "answer", "verdicts": [{"finding": f, "verdict": v, "reason": r, "cites": list(c)} for f, v, r, c in vs]}


def _review(answer, ledger=None, rid=None, skip=()):
    a, ps, plan, findings, facts = _change()
    llm = ScriptedLlm(answer)
    out = review_stories(llm, ledger, rid, plan, ps, a.x, CFG, findings, facts, skip=set(skip))
    return out, findings, llm


def test_each_story_gets_one_call_with_its_findings_facts_and_fixed_question():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "hazard", "old_user still calls hal_write the old way.", ["drv/old.c:3", "N3"]))
        return _verdicts(("F2", "no_hazard", "Nothing outside the DSP uses the result.", ["N4"]))
    out, findings, llm = _review(answer)
    assert len(llm.prompts) == 2 and out.reviewed == ["a", "b"] and out.notes == []
    first = llm.prompts[0]
    assert "STORY a: HAL writes take a width" in first and "drv/old.c:3 in old_user (N3): not updated" in first
    assert "QUESTION: Do the updated sites match the new signature; is any site left behind?" in first
    assert "F2" not in first                                     # each story sees only its own findings
    v = out.verdicts[finding_key(findings[0])]
    assert (v.verdict, v.cites) == ("hazard", ["drv/old.c:3", "N3"])
    apply_verdicts(findings, out.verdicts)
    by_title = {f.title: f for f in findings}
    sig, dsp = by_title["hal_write: signature changed"], by_title["dsp_run: something"]
    assert (sig.severity, sig.verdict, sig.verdict_source, sig.verdict_cites) == ("high", "hazard", "tier1", ["drv/old.c:3", "N3"])
    assert (dsp.severity, dsp.verdict) == ("info", "no_hazard")
    assert [f.id for f in findings] == ["F1", "F2"]              # renumbered by severity


def test_needs_review_is_medium_and_a_verdict_citing_nothing_shown_is_rejected():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "needs_review", "Callers should confirm the new width.", ["N1"]),
                             ("F2", "hazard", "Not this story's finding.", ["N1"]))
        return _verdicts(("F2", "hazard", "The DSP breaks.", ["N99", "dsp/run.c:400"]))
    out, findings, _ = _review(answer)
    assert {k: v.verdict for k, v in out.verdicts.items()} == {"contract|hal_write: signature changed": "needs_review"}
    assert out.notes == ["story b: F2's verdict cites nothing it was shown; the finding stays as the detectors left it"]
    apply_verdicts(findings, out.verdicts)
    dsp = next(f for f in findings if f.kind == "other_kind")
    assert (dsp.severity, dsp.verdict, dsp.verdict_source) == ("low", None, None)
    assert next(f for f in findings if f.kind == "contract").severity == "medium"


def test_a_line_inside_code_the_model_read_counts_as_shown():
    a, ps, plan, findings, facts = _change()
    hal = next(p.id for p in ps.pieces if p.nodes == ["N1"])

    def answer(system, user):
        if "F1" not in user:
            return _verdicts()
        if "READ piece_code" not in user:
            return {"action": "read", "tool": "piece_code", "arg": hal}
        return _verdicts(("F1", "no_hazard", "Every caller was updated in this change.", ["hal/regs.c:4", "hal/regs.c:40"]))
    out = review_stories(ScriptedLlm(answer), None, None, plan, ps, a.x, CFG, findings, facts)
    assert out.verdicts["contract|hal_write: signature changed"].cites == ["hal/regs.c:4"]     # line 40 was never shown


def test_a_story_without_findings_costs_no_call_and_reviewed_stories_are_skipped():
    out, _, llm = _review(lambda s, u: _verdicts(("F1", "hazard", "old_user is left behind.", ["N3"])), skip=["b"])
    assert len(llm.prompts) == 1 and out.reviewed == ["a", "b"]


def test_the_tier_1_budget_stops_the_review_and_the_rest_stay_as_the_detectors_left_them(tmp_path):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    ledger = Ledger(store, LlmBudget(tier1_per_review=1))
    out, _, llm = _review(lambda s, u: _verdicts(("F1", "hazard", "old_user is left behind.", ["N3"]),
                                                 ("F2", "hazard", "The DSP breaks.", ["N4"])), ledger, rid)
    assert len(llm.prompts) == 1 and out.reviewed == ["a"]
    assert out.notes == ["story b: AI budget: this review has used its 1 tier-1 AI calls; its findings stay as the "
                         "detectors left them"]


def test_a_finding_on_two_stories_is_reviewed_with_the_first():
    a, ps, plan, findings, facts = _change()
    plan.stories[1].placements.append(Placement(piece=plan.stories[0].placements[0].piece, reason="shared_code"))
    llm = ScriptedLlm(lambda s, u: _verdicts())
    review_stories(llm, None, None, plan, ps, a.x, CFG, findings, facts)
    assert ["F1" in p for p in llm.prompts] == [True, False]


def test_verdicts_follow_their_finding_when_a_re_run_numbers_the_findings_differently():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "hazard", "old_user still calls hal_write the old way.", ["N3"]))
        return _verdicts(("F2", "no_hazard", "Nothing outside the DSP uses the result.", ["N4"]))
    out, findings, _ = _review(answer)
    rerun = [Finding(id="F1", kind="header_fanout", severity="high", title="new.h: 1 change(s) reach 2 TU(s)", summary="s")]
    rerun += [f.model_copy(update={"id": f"F{i + 2}"}) for i, f in enumerate(reversed(findings))]
    apply_verdicts(rerun, out.verdicts)
    assert [(f.id, f.title, f.verdict) for f in rerun] == [
        ("F1", "hal_write: signature changed", "hazard"), ("F2", "new.h: 1 change(s) reach 2 TU(s)", None),
        ("F3", "dsp_run: something", "no_hazard")]


def test_a_strong_model_that_fails_leaves_every_finding_as_the_detectors_left_it(fx, tmp_path):
    from helpers import make_services
    from test_pipeline import _strong

    from codetortoise.pipeline import run_review
    svc = make_services(fx, tmp_path)
    _strong(svc, lambda s, u: RuntimeError("the endpoint is down"))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert st["review"]["status"] == "degraded" and "RuntimeError: the endpoint is down" in st["review"]["message"]
    assert st["review"]["message"].startswith("0 finding(s) judged by big")
    assert all(f.verdict_source is None and f.verdict is None for f in svc.store.list_findings(rid))
    assert svc.store.get_review(rid)["status"] == "degraded"       # the review still finishes, on the rules' stories


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr("httpx.Client.post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
```

`backend/tests/test_web.py` (diff):

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index 6b9ba55..c924d3d 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -67,7 +67,7 @@ def test_owner_creates_review_others_view_and_comment(env):
     assert r.status_code == 200 and r.json()["title"] == "CLs 101, 102"
     rid = r.json()["id"]
     detail = bob.get(f"/api/reviews/{rid}").json()
-    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 14
+    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 15
     assert detail["review"]["risk"] == "high"
     # the raw storyboard and impact graph are not served: the board replaced them (spec §14.4)
     assert bob.get(f"/api/reviews/{rid}/storyboard").status_code == 404
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_tier1_review.py tests/test_web.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.llm.review'`

- [ ] **Step 3: Implement**

`backend/codetortoise/detectors/base.py` (diff):

```diff
diff --git a/backend/codetortoise/detectors/base.py b/backend/codetortoise/detectors/base.py
index e598e65..2522ea0 100644
--- a/backend/codetortoise/detectors/base.py
+++ b/backend/codetortoise/detectors/base.py
@@ -45,8 +45,10 @@ class Finding(BaseModel):
     files: list[str] | None = None          # depot paths behind the finding (spec §14.3); None = unknown
     explain_files: list[str] | None = None  # files behind the LLM explanation, verify steps and hypotheses
     side_effect: bool = False               # a new field write: neutral until the AI judges it
-    verdict: Literal["hazard", "no_hazard"] | None = None   # the AI's judgement of a side effect (None: not assessed)
+    verdict: Literal["hazard", "needs_review", "no_hazard"] | None = None   # the AI's judgement (None: not assessed)
     verdict_reason: str | None = None
+    verdict_cites: list[str] = Field(default_factory=list)      # node ids and file:line the verdict relies on
+    verdict_source: Literal["tier1", "tier2"] | None = None     # the strong model's story review, or tier 2's side-effect pass
 
 
 @dataclass
```

`backend/codetortoise/llm/review.py` (new file):

```python
"""Tier 1 reviews each story's risks (spec 2026-10-05-two-tier-stories §5).

One call per story with findings: the story's title and purpose, its pieces' cards, and for each finding its prepared
facts and a fixed question. The model may read more (the tools of §4.1). Each answer is hazard, needs_review or
no_hazard with a reason, and must cite node ids or file:line it was shown; one citing nothing shown is rejected and the
finding stays as the detectors left it. A finding on two stories is reviewed with the first.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import _Ctx
from codetortoise.brief import BriefVerdict
from codetortoise.config import StrongLlmConfig
from codetortoise.detectors.base import Finding, renumber
from codetortoise.facts_prep import finding_key
from codetortoise.grouping import PlannedStory, StoryPlan
from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.stories import Tools, ask, pieces_of
from codetortoise.llm.storyboard import _styled
from codetortoise.llm.style import MODES, STYLE
from codetortoise.pieces import PieceSet

SEVERITY = {"hazard": "high", "needs_review": "medium", "no_hazard": "info"}

QUESTIONS = {
    "signature": "Do the updated sites match the new signature; is any site left behind?",
    "returns": "Does any caller mishandle the new value?",
    "field": "Does any reader's assumption break; is this a hazard or a normal side effect?",
    "behaviour": "Does any caller rely on the old behaviour; should a reviewer confirm it?",
    "header": "Do all users still compile and mean the same thing?",
}

RULES = """Review the risks of one story of a change. For each finding below, check its facts (prepared by code: trust \
them, and read more when they are not enough) and answer its question with one verdict:
- hazard: a clear problem; the reason says what breaks and where;
- needs_review: behaviour changed and a person should confirm it is intended;
- no_hazard: nothing breaks; the reason says why.
Cite the node ids (N12) or file:line you rely on, exactly as shown. A verdict citing nothing you were shown is \
discarded."""

SYSTEM = ("You are a senior C/C++ reviewer judging the risks of one story of a change. Use only what you are given or "
          "have read. Each turn reply with one JSON object: either "
          '{"action": "read", "tool": T, "arg": A} to read more, where T is "piece_code" (A: a piece id), "diff" (A: a '
          'file path as the cards show it), "neighbours" (A: a function name) or "cl" (A: a CL number); or '
          '{"action": "answer", "verdicts": [{"finding", "verdict", "reason", "cites"}]}. ' + STYLE)


class _Verdict(BaseModel):
    finding: str
    verdict: Literal["hazard", "needs_review", "no_hazard"]
    reason: str = ""
    cites: list[str] = Field(default_factory=list)


class _ReviewStep(BaseModel):
    action: Literal["read", "answer"]
    tool: str = ""
    arg: str | int = ""
    verdicts: list[_Verdict] = Field(default_factory=list)


@dataclass
class Reviewed:
    verdicts: dict[str, BriefVerdict] = field(default_factory=dict)    # finding key -> verdict
    reviewed: list[str] = field(default_factory=list)                  # story keys whose pass ran (or had no findings)
    notes: list[str] = field(default_factory=list)


def question(f: Finding) -> str:
    if f.kind == "contract" and "signature changed" in f.title:
        return QUESTIONS["signature"]
    if f.kind == "contract" and "new return value" in f.title:
        return QUESTIONS["returns"]
    if f.kind == "field_mutation" or f.side_effect:
        return QUESTIONS["field"]
    if f.kind == "header_fanout":
        return QUESTIONS["header"]
    return QUESTIONS["behaviour"]


def review_parts(s: PlannedStory, ps: PieceSet, mine: list[Finding], facts: dict[str, str]) -> list[str]:
    cards = "\n\n".join(p.card for p in ps.pieces if p.id in s.pieces)
    rows = [f"{f.id} [{f.severity}] {f.kind}: {f.title}\n{f.summary}\nFACTS:\n{facts.get(finding_key(f), 'no prepared facts')}"
            f"\nQUESTION: {question(f)}" for f in mine]
    return [RULES + "\n\nCHANGE OVERVIEW:\n" + ps.overview,
            f"STORY {s.key}: {s.title or '(untitled)'}" + (f"\nPurpose: {s.purpose}" if s.purpose else "") + "\nPIECES:\n" + cards,
            "FINDINGS:\n" + "\n\n".join(rows)]


def _shown(cite: str, text: str) -> bool:
    """The cite appears in what the model was shown, or is a line inside a range it was shown (file:lo-hi)."""
    cite = cite.strip()
    if not cite:
        return False
    if re.search(rf"(?<![\w/.]){re.escape(cite)}(?![\w])", text):
        return True
    m = re.fullmatch(r"(.+):(\d+)", cite)
    return bool(m) and any(int(lo) <= int(m[2]) <= int(hi) for lo, hi in re.findall(rf"{re.escape(m[1])}:(\d+)-(\d+)", text))


def review_stories(strong: LlmClient, ledger: Ledger | None, rid: int | None, plan: StoryPlan, ps: PieceSet, x: _Ctx,
                   cfg: StrongLlmConfig, findings: list[Finding], facts: dict[str, str],
                   skip: set[str] | None = None) -> Reviewed:
    """Tier 1's verdicts on the findings of every story not in `skip`. The budget running out, or a call failing, leaves
    the remaining findings as the detectors left them; the notes say so."""
    tools, out, taken = Tools(x, ps), Reviewed(), set()
    refused = False
    for s in plan.stories:
        mine = [f for f in findings if f.id not in taken and set(pieces_of(f, ps)) & set(s.pieces)]
        taken |= {f.id for f in mine}
        if s.key in (skip or set()) or not mine:
            out.reviewed.append(s.key)
            continue
        if refused:
            out.notes.append(f"story {s.key}: AI budget: the tier-1 budget ran out; its findings stay as the detectors left them")
            continue
        seen: list[str] = []
        parts = review_parts(s, ps, mine, facts)

        def fn(llm, parts=parts, seen=seen):
            return ask(llm, parts, tools, cfg.rounds, int(cfg.context_tokens * 4 * 0.9), SYSTEM, _ReviewStep,
                       f"\nReasons: {MODES['explanation']}", seen)
        try:
            step = ledger.call(strong, rid, None, "review", f"story {s.key}", fn) if ledger is not None else fn(strong)
        except Refused as e:
            refused = True
            out.notes.append(f"story {s.key}: AI budget: {e.reason}; its findings stay as the detectors left them")
            continue
        except Exception as e:  # this story's findings stay as the detectors left them; the others go on
            out.notes.append(f"story {s.key}: {type(e).__name__}: {e}"[:300])
            continue
        out.reviewed.append(s.key)
        by_id, shown = {f.id: f for f in mine}, "\n".join(seen)
        for v in step.verdicts:
            f = by_id.get(v.finding)
            if f is None or not v.reason.strip() or not _styled(v.reason, "explanation"):
                continue
            cites = [c.strip() for c in v.cites if _shown(c, shown)]
            if not cites:
                out.notes.append(f"story {s.key}: {f.id}'s verdict cites nothing it was shown; the finding stays as the "
                                 "detectors left it")
                continue
            out.verdicts[finding_key(f)] = BriefVerdict(verdict=v.verdict, reason=v.reason.strip(), cites=cites)
    return out


def apply_verdicts(findings: list[Finding], verdicts: dict[str, BriefVerdict]) -> int:
    """Record tier 1's verdicts on the findings (severity follows), renumber them by severity; how many got one."""
    n = 0
    for f in findings:
        v = verdicts.get(finding_key(f))
        if v is None:
            continue
        f.verdict, f.verdict_reason, f.verdict_cites, f.verdict_source = v.verdict, v.reason, list(v.cites), "tier1"
        f.severity = SEVERITY[v.verdict]
        n += 1
    renumber(findings)
    return n
```

`backend/codetortoise/llm/stories.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/stories.py b/backend/codetortoise/llm/stories.py
index e5dd976..c045bfe 100644
--- a/backend/codetortoise/llm/stories.py
+++ b/backend/codetortoise/llm/stories.py
@@ -191,11 +191,16 @@ def _chunk_target(p: Piece, ps: PieceSet) -> str:
     return max(p.targets, key=lambda t: (weight[t], -p.targets.index(t)))
 
 
+def pieces_of(f: Finding, ps: PieceSet) -> list[str]:
+    """The pieces a finding is about: those holding its nodes, or the declaration pieces of its evidence's files."""
+    return [p.id for p in ps.pieces if set(f.nodes) & set(p.nodes) or (
+        p.kind == "declarations" and any(e.file in p.files for e in f.evidence))]
+
+
 def _findings_of(ids: list[str], ps: PieceSet, findings: list[Finding]) -> list[str]:
     out = []
     for f in findings:
-        mine = [p.id for p in ps.pieces if p.id in ids and (set(f.nodes) & set(p.nodes) or (
-            p.kind == "declarations" and any(e.file in p.files for e in f.evidence)))]
+        mine = [pid for pid in pieces_of(f, ps) if pid in ids]
         if mine:
             out.append(f"{f.id} [{f.severity}] {f.kind}: {f.title} — {', '.join(mine)}")
     return out
@@ -256,15 +261,20 @@ def _fit(convo: list[str], limit: int) -> str:
     return head + "".join("\n\n" + r for r in kept)
 
 
-def ask(strong: LlmClient, parts: list[str], tools: Tools, rounds: int, limit: int) -> _Step:
-    """One chunk's rounds (one AI call): reads until the model answers; the last round must answer."""
+ASK_STYLE = f"\nPurposes and questions: {MODES['explanation']} Checks: {MODES['how-to']} Titles: {MODES['headline']}"
+
+
+def ask(strong: LlmClient, parts: list[str], tools: Tools, rounds: int, limit: int, system: str = SYSTEM,
+        schema: type[BaseModel] = _Step, tail: str = ASK_STYLE, seen: list[str] | None = None):
+    """One chunk's (or story's) rounds (one AI call): reads until the model answers; the last round must answer. `seen`
+    receives every prompt sent, so answers can be checked against what the model was shown."""
     convo = list(parts)
     for n in range(1, max(1, rounds) + 1):
         last = n == max(1, rounds)
-        step = strong.complete_json(SYSTEM, _fit(convo, limit) + (
-            '\n\nYou must answer now: reply with action "answer".' if last else "")
-            + f"\nPurposes and questions: {MODES['explanation']} Checks: {MODES['how-to']} Titles: {MODES['headline']}",
-            _Step)
+        prompt = _fit(convo, limit) + ('\n\nYou must answer now: reply with action "answer".' if last else "") + tail
+        if seen is not None:
+            seen.append(prompt)
+        step = strong.complete_json(system, prompt, schema)
         if step.action == "answer":
             return step
         if last:
```

`backend/codetortoise/llm/storyboard.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index b62f411..7eb5ff6 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -260,6 +260,7 @@ def _judge(f: Finding, hazard: bool | None, reason: str) -> bool:
     if not f.side_effect or hazard is None or not reason or not _styled(reason, "explanation"):
         return False
     f.verdict, f.verdict_reason, f.severity = ("hazard" if hazard else "no_hazard"), reason, ("high" if hazard else "info")
+    f.verdict_source = "tier2"
     return True
 
 
```

`backend/codetortoise/pipeline.py` (diff):

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 837150a..35f190c 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -16,8 +16,10 @@ from codetortoise.detectors.base import DetectorContext, renumber, run_detectors
 from codetortoise.diffmap import map_changes
 from codetortoise.facts.model import Facts, relative_records
 from codetortoise.facts.runner import build_requests, parse_summary, run_extraction
+from codetortoise.facts_prep import prepare_facts
 from codetortoise.grouping import StoryPlan, rules_plan
 from codetortoise.impact import ImpactModel, build_impact
+from codetortoise.llm.review import apply_verdicts, review_stories
 from codetortoise.llm.stories import STORY_RULES_VERSION, form_stories
 from codetortoise.llm.storyboard import AiContext, build_storyboard, judge_side_effects
 from codetortoise.paths import canon
@@ -33,11 +35,19 @@ from codetortoise.vcs.model import ChangeSet
 
 log = logging.getLogger(__name__)
 
+
+def _read_text(path: str) -> str | None:
+    """A workspace file's text, for the header facts' search of files outside the change."""
+    try:
+        return Path(path).read_text(errors="replace")
+    except OSError:
+        return None
+
 STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "pieces", "stories",
-          "verdicts", "board", "llm", "finalize"]
+          "review", "verdicts", "board", "llm", "finalize"]
 DEPS = {"swarm_read": ["ingest"], "diffmap": ["ingest"], "tu_select": ["diffmap"], "facts": ["tu_select"],
         "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "pieces": ["impact", "detectors"],
-        "stories": ["pieces"], "verdicts": ["detectors"], "board": ["impact", "detectors"],
+        "stories": ["pieces"], "review": ["stories"], "verdicts": ["detectors"], "board": ["impact", "detectors"],
         "llm": ["detectors"]}
 
 
@@ -277,12 +287,40 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
             raise Degraded(msg + "; " + "; ".join(plan.notes))
         return msg
 
+    def review():
+        """The strong model judges each story's findings against facts code prepared for them (spec §5); a reused brief
+        brings its verdicts. Findings take the verdicts' severities before the board is drawn."""
+        brief, findings, ps, strong = ctx["brief"], ctx["findings"], ctx["pieces"], cfg.llm.strong
+        x = ctx["analysis"].x
+        brief.facts = prepare_facts(x, findings, ps.targets, svc.index.transitive_includers, _read_text)
+        if svc.strong is None or strong is None:
+            store.put_brief(rid, brief.key, brief)
+            return f"no strong model: {len(findings)} finding(s) left to the detectors and the AI's side-effect pass"
+        got = review_stories(svc.strong, svc.ledger, rid, ctx["plan"], ps, x, strong, findings, brief.facts,
+                             skip=set(brief.reviewed))
+        brief.verdicts.update(got.verdicts)
+        brief.reviewed = list(dict.fromkeys(brief.reviewed + got.reviewed))
+        apply_verdicts(findings, brief.verdicts)
+        store.put_findings(rid, findings)
+        store.put_brief(rid, brief.key, brief)
+        mine = [f for f in findings if f.verdict_source == "tier1"]
+        msg = (f"{len(mine)} finding(s) judged by {strong.model}: {sum(f.verdict == 'hazard' for f in mine)} hazard(s), "
+               f"{sum(f.verdict == 'needs_review' for f in mine)} to confirm, {sum(f.verdict == 'no_hazard' for f in mine)} "
+               "no hazard")
+        if got.notes:
+            raise Degraded(msg + "; " + "; ".join(got.notes))
+        return msg
+
     def verdicts():
-        """The AI judges side effects before the board is drawn, so flows and stories take the verdicts' colours."""
+        """The AI judges side effects before the board is drawn, so flows and stories take the verdicts' colours.
+        Side effects the strong model already judged are left alone."""
         findings = ctx["findings"]
-        todo = [f for f in findings if f.side_effect]
-        if not todo:
+        effects = [f for f in findings if f.side_effect]
+        todo = [f for f in effects if f.verdict_source != "tier1"]
+        if not effects:
             return "no side effects"
+        if not todo:
+            return f"all {len(effects)} side effect(s) judged by the strong model"
         if svc.llm is None:
             return f"no LLM: {len(todo)} side effect(s) not assessed (shown neutral)"
         snippets = collect_snippets(ctx["impact"], ctx["cs"], ctx["after"])
@@ -371,7 +409,8 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
         store.put_blob(rid, "file_summaries", {})       # they describe the old diff
         for name, fn in [("ingest", ingest), ("swarm_read", swarm_read), ("diffmap", diffmap), ("tu_select", tu_select),
                          ("layers", layers), ("facts", facts), ("impact", impact), ("detectors", detectors),
-                         ("pieces", pieces), ("stories", stories), ("verdicts", verdicts), ("board", board), ("llm", llm),
+                         ("pieces", pieces), ("stories", stories), ("review", review),
+                         ("verdicts", verdicts), ("board", board), ("llm", llm),
                          ("finalize", finalize)]:
             stage(name, fn)
 
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_tier1_review.py tests/test_web.py -q`
Expected: PASS: `53 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `501 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_pipeline.py backend/tests/test_tier1_review.py backend/tests/test_web.py backend/codetortoise/detectors/base.py backend/codetortoise/llm/review.py backend/codetortoise/llm/stories.py backend/codetortoise/llm/storyboard.py backend/codetortoise/pipeline.py
git commit -m "feat(review): tier 1 reviews each story's findings against prepared facts — hazard, to confirm or no hazard, with citations it was shown"
```

### Task 8: Tier 2 starts from the brief

Spec §8. `brief_context` returns the brief's part for one target, within 800 tokens:
- a finding: its story's title and purpose, tier 1's verdict and reason, its prepared facts;
- a story, flow or file: its story's purpose, what to check and open questions;
- @tortoise: the anchor's story and the change overview.

Every on-demand job (`explain`) and every @tortoise question puts it first, with a line telling tier 2 never to regroup stories or overturn a verdict. Tier 2's side-effect judgement leaves a tier-1 verdict alone (`_judge`). The up-front story-text pass skips tier-1 stories, and explaining a tier-1 story is refused.

**Files:**
- Test: `backend/tests/test_brief_context.py`
- Test: `backend/tests/test_ondemand.py`
- Test: `backend/tests/test_tortoise.py`
- Create: `backend/codetortoise/llm/brief_context.py`
- Modify: `backend/codetortoise/llm/ondemand.py`
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `backend/codetortoise/llm/tortoise.py`
- Modify: `backend/codetortoise/pipeline.py`

**Interfaces:**
- Consumes: `Store.get_brief` (Task 6), `boardstore.stories`, `finding_key` (Task 4), `Finding.verdict_source` (Task 7).
- Produces: `llm.brief_context.BRIEF_CHARS = 3200`, `brief_context(store, rid, *, story=None, finding=None, flow=None, nodes=(), overview=False) -> str` ("" when the brief knows nothing of the target);
  `ondemand._briefed(job, brief) -> Job`; `tortoise._anchor_brief(svc, rid, comment, ctx, board) -> str`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_brief_context.py` (new file):

```python
"""Tier 2 starts from the brief (spec 2026-10-05-two-tier-stories §8)."""
from codetortoise.brief import Brief, BriefVerdict
from codetortoise.detectors.base import Finding
from codetortoise.llm.brief_context import BRIEF_CHARS, brief_context
from codetortoise.store import Store
from codetortoise.stories import Story, StorySet


def _review(tmp_path, overview="CHANGE: 2 CLs, 3 files"):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    f = Finding(id="F1", kind="contract", severity="high", title="hal_write: signature changed", summary="s", nodes=["N1"],
                verdict="hazard", verdict_reason="old_user still calls it the old way.", verdict_cites=["drv/old.c:3"],
                verdict_source="tier1")
    store.put_brief(rid, "k", Brief(key="k", overview=overview, facts={"contract|hal_write: signature changed":
                                                                       "call sites of hal_write (N1):\n  drv/old.c:3 ..."},
                                    verdicts={"contract|hal_write: signature changed": BriefVerdict(
                                        verdict="hazard", reason="old_user still calls it the old way.")}))
    st = Story(id="S1", kind="behaviour", title="HAL writes take a width", summary="s", nodes=["N1", "N2"], flows=["W1"],
               findings=["F1"], purpose="This widens the HAL write.", check=["Check every caller passes a width."],
               questions=["Does the DSP call it?"], source="tier1")
    store.put_blob(rid, "stories", StorySet(summary="s", stories=[st]))
    return store, rid, f


def test_a_finding_s_prompt_starts_with_its_story_verdict_and_facts(tmp_path):
    store, rid, f = _review(tmp_path)
    text = brief_context(store, rid, finding=f)
    assert text.splitlines()[1:] == [
        "STORY: HAL writes take a width — This widens the HAL write.",
        "VERDICT (strong model): hazard — old_user still calls it the old way. (cites drv/old.c:3)",
        "PREPARED FACTS:", "call sites of hal_write (N1):", "  drv/old.c:3 ..."]
    assert text.startswith("BRIEF (")


def test_a_story_flow_or_file_prompt_gets_purpose_checks_and_questions(tmp_path):
    store, rid, _ = _review(tmp_path)
    want = ["STORY: HAL writes take a width — This widens the HAL write.", "What to check: Check every caller passes a width.",
            "Open questions: Does the DSP call it?"]
    assert brief_context(store, rid, story="S1").splitlines()[1:] == want
    assert brief_context(store, rid, flow="W1").splitlines()[1:] == want
    assert brief_context(store, rid, nodes=["N2"]).splitlines()[1:] == want
    assert brief_context(store, rid, nodes=["N9"]) == ""          # nothing known: the prompt is unchanged


def test_tortoise_gets_the_overview_and_its_anchor_s_story_within_800_tokens(tmp_path):
    store, rid, _ = _review(tmp_path, overview="CHANGE: " + "x" * 9000)
    text = brief_context(store, rid, story="S1", overview=True)
    assert text.splitlines()[1] == "STORY: HAL writes take a width — This widens the HAL write."
    assert "CHANGE OVERVIEW:" in text and len(text) == BRIEF_CHARS and text.endswith("…")


def test_a_review_without_a_brief_or_stories_adds_nothing(tmp_path):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    assert brief_context(store, rid, story="S1", overview=True) == ""
```

`backend/tests/test_ondemand.py` (diff):

```diff
diff --git a/backend/tests/test_ondemand.py b/backend/tests/test_ondemand.py
index 5d927c0..ae922ef 100644
--- a/backend/tests/test_ondemand.py
+++ b/backend/tests/test_ondemand.py
@@ -301,3 +301,27 @@ def test_asking_for_an_item_already_being_explained_joins_that_job(ai):
     before = svc.ledger.used(rid)
     r = bob.post(f"/api/reviews/{rid}/explain", json={"kind": "flow", "target": flow})
     assert r.status_code == 202 and r.json()["id"] == 7 and svc.ledger.used(rid) == before   # no second call
+
+
+def test_tier_2_starts_from_the_brief_and_leaves_tier_1_verdicts_and_stories_alone(ai):
+    svc, app, owner, rid, seen = ai
+    assert owner.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": "F4"}).status_code == 202
+    prompt = next(u for u in reversed(seen) if "Explain the risk" in u)
+    assert prompt.startswith("BRIEF (") and "PREPARED FACTS:\ncallers of uart_send" in prompt
+    findings = svc.store.list_findings(rid)                            # as if the strong model had judged the side effect
+    errors = next(f for f in findings if f.title.startswith("uart_send now writes Uart::errors"))
+    errors.verdict, errors.verdict_reason, errors.verdict_source, errors.severity = (
+        "no_hazard", "Only the stats page reads it.", "tier1", "info")
+    svc.store.put_findings(rid, findings)
+    assert owner.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": errors.id}).status_code == 202
+    now = next(f for f in svc.store.list_findings(rid) if f.id == errors.id)
+    assert (now.severity, now.verdict, now.verdict_reason) == ("info", "no_hazard", "Only the stats page reads it.")
+    assert now.explanation.startswith("uart_send can now return -2")  # the explanation is still written
+    assert "VERDICT (strong model): no_hazard — Only the stats page reads it." in seen[-1]
+    from codetortoise import boardstore
+    sid = boardstore.stories(svc.store, rid).stories[0].id
+    d = boardstore.story(svc.store, rid, sid)
+    d.story.source = "tier1"
+    boardstore.put_story(svc.store, rid, d)
+    r = owner.post(f"/api/reviews/{rid}/explain", json={"kind": "story", "target": sid})
+    assert r.status_code == 404 and "written by the strong model" in r.json()["detail"]
```

`backend/tests/test_tortoise.py` (diff):

```diff
diff --git a/backend/tests/test_tortoise.py b/backend/tests/test_tortoise.py
index 3339c16..e517c2d 100644
--- a/backend/tests/test_tortoise.py
+++ b/backend/tests/test_tortoise.py
@@ -298,3 +298,14 @@ def test_a_thread_longer_than_the_prompt_still_keeps_the_newest_read():
     out = _fit(head + ["READ callers uart_send ->\nuart_send(lg->uart"], 2000)
     assert out.startswith("QUESTION: q") and "uart_send(lg->uart" in out and len(out) <= 8000
 
+
+
+def test_a_question_starts_from_its_anchor_s_story_and_the_change_overview(world):
+    script = Script({"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
+    svc, app, rid = world(script)
+    bob = login(app, "bob")
+    story = bob.get(f"/api/reviews/{rid}/stories/S1").json()["story"]
+    _ask(bob, rid, "@tortoise story?", "story", {"id": "S1"})
+    context = script.prompts[0].split("CONTEXT:\n", 1)[1]
+    assert context.startswith("BRIEF (") and f"STORY: {story['title']}" in context
+    assert "CHANGE OVERVIEW:\nCHANGE: 2 CLs" in context
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_brief_context.py tests/test_ondemand.py tests/test_tortoise.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.llm.brief_context'`

- [ ] **Step 3: Implement**

`backend/codetortoise/llm/brief_context.py` (new file):

```python
"""The part of a review's brief a tier-2 prompt starts with (spec 2026-10-05-two-tier-stories §8), within 800 tokens:

- explain or Ask… on a finding: its story's title and purpose, the strong model's verdict and reason, its prepared facts;
- a story, flow or file: its story's purpose, what to check and open questions;
- @tortoise: the story of the anchor, if any, and the change overview.

Tier 2 builds on it: it never regroups the stories or overturns a verdict, and says so in its answer if it disagrees.
"""
from __future__ import annotations

from collections.abc import Iterable

from codetortoise import boardstore
from codetortoise.detectors.base import Finding
from codetortoise.facts_prep import finding_key
from codetortoise.store import Store
from codetortoise.stories import Story

BRIEF_CHARS = 3200                    # 800 tokens
HEAD = ("BRIEF (worked out by the strong model and by code; build on it: never regroup the stories or overturn a "
        "verdict, and if you disagree, say so in your answer):")


def _holding(stories: list[Story], story: str | None, finding: Finding | None, flow: str | None,
             nodes: Iterable[str]) -> Story | None:
    nodes = set(nodes)
    for st in stories:
        if (story is not None and st.id == story or finding is not None and finding.id in st.findings
                or flow is not None and flow in st.flows or nodes and nodes & set(st.nodes)):
            return st
    return None


def brief_context(store: Store, rid: int, *, story: str | None = None, finding: Finding | None = None,
                  flow: str | None = None, nodes: Iterable[str] = (), overview: bool = False) -> str:
    """The brief's lines for one target ("" when the brief knows nothing of it)."""
    ss = boardstore.stories(store, rid)
    brief = store.get_brief(rid) or {}
    st = _holding(ss.stories if ss else [], story, finding, flow, nodes)
    rows: list[str] = []
    if st is not None:
        rows.append(f"STORY: {st.title}" + (f" — {st.purpose}" if st.purpose else ""))
        if finding is None:
            rows += [f"What to check: {'; '.join(st.check)}"] if st.check else []
            rows += [f"Open questions: {'; '.join(st.questions)}"] if st.questions else []
    if finding is not None:
        if finding.verdict and finding.verdict_source == "tier1":
            rows.append(f"VERDICT (strong model): {finding.verdict} — {finding.verdict_reason}"
                        + (f" (cites {', '.join(finding.verdict_cites)})" if finding.verdict_cites else ""))
        facts = brief.get("facts", {}).get(finding_key(finding))
        rows += ["PREPARED FACTS:", facts] if facts else []
    if overview and brief.get("overview"):
        rows += ["CHANGE OVERVIEW:", brief["overview"]]
    if not rows:
        return ""
    text = "\n".join([HEAD] + rows)
    return text if len(text) <= BRIEF_CHARS else text[:BRIEF_CHARS - 1] + "…"
```

`backend/codetortoise/llm/ondemand.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/ondemand.py b/backend/codetortoise/llm/ondemand.py
index 48b80d3..3ac476a 100644
--- a/backend/codetortoise/llm/ondemand.py
+++ b/backend/codetortoise/llm/ondemand.py
@@ -18,6 +18,7 @@ from codetortoise.board import Board
 from codetortoise.detectors.base import Finding
 from codetortoise.facts.model import Facts
 from codetortoise.impact import ImpactModel
+from codetortoise.llm.brief_context import brief_context
 from codetortoise.llm.storyboard import (
     AiContext,
     Job,
@@ -105,6 +106,13 @@ def file_job(ctx: AiContext, board: Board, cs: ChangeSet, path: str, summaries:
     return Job("file", path, prompt, _FileOut, apply)
 
 
+def _briefed(job: Job, brief: str) -> Job:
+    """The job's prompt, starting with the brief's part for its target (spec 2026-10-05-two-tier-stories §8)."""
+    if brief:
+        job.prompt = brief + "\n\n" + job.prompt
+    return job
+
+
 def explain(svc: Services, rid: int, user: str, kind: str, target: str) -> None:
     """Run one explanation as `user` and store it. Raises NotFound, Refused (over a limit), Unchecked, Changed or the
     LLM's error. The AI call runs without the review's lock (other explanations go on meanwhile); the result is
@@ -118,7 +126,7 @@ def explain(svc: Services, rid: int, user: str, kind: str, target: str) -> None:
         if fl is None:
             raise NotFound(f"flow {target} not found")
         trial = fl.model_copy(update={"what_source": "template"})
-        run_job(svc.llm, flow_job(ctx, trial), svc.ledger, rid, user)
+        run_job(svc.llm, _briefed(flow_job(ctx, trial), brief_context(svc.store, rid, flow=target)), svc.ledger, rid, user)
         if trial.what_source != "llm":
             raise Unchecked(UNCHECKED)
         with _lock(rid):
@@ -135,7 +143,7 @@ def explain(svc: Services, rid: int, user: str, kind: str, target: str) -> None:
         if f is None:
             raise NotFound(f"finding {target} not found")
         trial = f.model_copy(update={"explanation": None})
-        run_job(svc.llm, finding_job(ctx, trial), svc.ledger, rid, user)
+        run_job(svc.llm, _briefed(finding_job(ctx, trial), brief_context(svc.store, rid, finding=f)), svc.ledger, rid, user)
         if not trial.explanation:
             raise Unchecked(UNCHECKED)
         with _lock(rid):
@@ -153,9 +161,11 @@ def explain(svc: Services, rid: int, user: str, kind: str, target: str) -> None:
         d = boardstore.story(svc.store, rid, target)
         if d is None:
             raise NotFound(f"story {target} not found")
+        if d.story.source == "tier1":
+            raise NotFound(f"story {target} was written by the strong model; ask about it in a thread instead")
         trial = d.model_copy(deep=True)
         trial.story.text_source, trial.story.text_files = "template", None
-        run_job(svc.llm, story_job(ctx, trial), svc.ledger, rid, user)
+        run_job(svc.llm, _briefed(story_job(ctx, trial), brief_context(svc.store, rid, story=target)), svc.ledger, rid, user)
         if trial.story.text_source != "llm":
             raise Unchecked(UNCHECKED)
         with _lock(rid):
@@ -168,7 +178,10 @@ def explain(svc: Services, rid: int, user: str, kind: str, target: str) -> None:
             boardstore.put_story(svc.store, rid, now)
     elif kind == "file":
         fresh: dict = {}
-        run_job(svc.llm, file_job(ctx, board, cs, target, fresh, user), svc.ledger, rid, user)
+        change = next((c for c in cs.files if c.depot == target), None)
+        nodes = [nid for nid, n in ctx.impact.nodes.items() if change and n.file == change.local and n.kind == "function"]
+        run_job(svc.llm, _briefed(file_job(ctx, board, cs, target, fresh, user), brief_context(svc.store, rid, nodes=nodes)),
+                svc.ledger, rid, user)
         if not fresh.get(target, {}).get("summary"):
             raise Unchecked(UNCHECKED)
         with _lock(rid):
@@ -198,8 +211,11 @@ def check_target(svc: Services, rid: int, kind: str, target: str) -> None:
         if not any(f.id == target for f in svc.store.list_findings(rid)):
             raise NotFound(f"finding {target} not found")
     elif kind == "story":
-        if boardstore.story(svc.store, rid, target) is None:
+        d = boardstore.story(svc.store, rid, target)
+        if d is None:
             raise NotFound(f"story {target} not found")
+        if d.story.source == "tier1":          # spec 2026-10-05-two-tier-stories §8: tier 2 never retells them
+            raise NotFound(f"story {target} was written by the strong model; ask about it in a thread instead")
     elif kind == "file":
         cs = svc.store.get_blob(rid, "changeset") or {}
         if not any(f.get("depot") == target for f in cs.get("files", [])):
```

`backend/codetortoise/llm/storyboard.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index 7eb5ff6..dec66e8 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -257,6 +257,8 @@ def _titled(text: str) -> bool:
 def _judge(f: Finding, hazard: bool | None, reason: str) -> bool:
     """Record the AI's verdict on side effect `f` (severity follows it); False if there is no usable verdict."""
     reason = reason.strip()
+    if f.verdict_source == "tier1":            # the strong model's verdict stands; tier 2 disagrees in its answer only
+        return False
     if not f.side_effect or hazard is None or not reason or not _styled(reason, "explanation"):
         return False
     f.verdict, f.verdict_reason, f.severity = ("hazard" if hazard else "no_hazard"), reason, ("high" if hazard else "info")
```

`backend/codetortoise/llm/tortoise.py` (diff):

```diff
diff --git a/backend/codetortoise/llm/tortoise.py b/backend/codetortoise/llm/tortoise.py
index 26e37bb..8906220 100644
--- a/backend/codetortoise/llm/tortoise.py
+++ b/backend/codetortoise/llm/tortoise.py
@@ -15,6 +15,7 @@ from pydantic import BaseModel, Field
 
 from codetortoise import boardstore
 from codetortoise.board import Board, Flow
+from codetortoise.llm.brief_context import brief_context
 from codetortoise.llm.ledger import Refused
 from codetortoise.llm.ondemand import context_for
 from codetortoise.llm.storyboard import STYLE, AiContext, _facts_for_nodes, _finding_text, budget
@@ -252,6 +253,26 @@ def _anchor_context(svc: Services, rid: int, comment: dict, ctx: AiContext, boar
     return f"CHANGE: {board.about.intent}\nFLOWS:\n{flows}\nFINDINGS:\n{finds}"
 
 
+def _anchor_brief(svc: Services, rid: int, comment: dict, ctx: AiContext, board: Board) -> str:
+    """The brief's part for a question (spec 2026-10-05-two-tier-stories §8): the story of its anchor, if any, and the
+    change overview."""
+    kind, a = comment["anchor_kind"], comment["anchor"]
+    kw: dict = {}
+    if kind == "story":
+        kw["story"] = str(a.get("id"))
+    elif kind == "flow":
+        kw["flow"] = str(a.get("id"))
+    elif kind == "finding":
+        kw["finding"] = next((f for f in ctx.findings if f.kind == a.get("kind") and f.title == a.get("title")), None)
+    elif kind == "function":
+        kw["nodes"] = [i for i, n in ctx.impact.nodes.items() if n.key == a.get("key")]
+    elif kind in ("file", "line"):
+        path, line = a.get("path") or a.get("depot"), a.get("line")
+        kw["nodes"] = [n.id for n in board.nodes if n.path == path and n.change and (
+            line is None or kind == "file" or (n.range and n.range[0] <= int(line) <= n.range[1]))]
+    return brief_context(svc.store, rid, overview=True, **kw)
+
+
 def _flow_text(fl: Flow) -> str:
     return f"FLOW {fl.id}: {fl.title}\n{fl.what}\neffect: {fl.effect}\ncheck: {fl.check}"
 
@@ -298,7 +319,8 @@ def answer(svc: Services, rid: int, user: str, question: dict, reply_id: int) ->
         root = question["parent_id"] or question["id"]
         known = set(ctx.impact.nodes) | {f.id for f in findings}
         convo = [f"QUESTION: {question['body']}", "THREAD SO FAR:\n" + _thread(svc, rid, root, question["id"]),
-                 "CONTEXT:\n" + _anchor_context(svc, rid, question, ctx, board, reader)]
+                 "CONTEXT:\n" + "\n\n".join(t for t in (_anchor_brief(svc, rid, question, ctx, board),
+                                                         _anchor_context(svc, rid, question, ctx, board, reader)) if t)]
 
         def rounds(llm) -> str:            # the whole answer, every round of it, is one AI call
             fixed = False
```

`backend/codetortoise/pipeline.py` (diff):

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 35f190c..b251310 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -374,7 +374,8 @@ def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
         bs = ctx.get("boards")
         b = None if bs is None else bs.board or boardstore.merge(list(bs.clusters.values()), bs.overview.about)
         top = [] if bs is None or bs.stories is None else [   # the riskiest behaviour stories get AI titles up front
-            bs.story_details[s.id] for s in bs.stories.stories if s.kind == "behaviour" and not s.collapsed]
+            bs.story_details[s.id] for s in bs.stories.stories
+            if s.kind == "behaviour" and not s.collapsed and s.source != "tier1"]      # tier 1 wrote its own
         sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens,
                               board=b, concurrency=cfg.llm.concurrency, upfront_flows=cfg.llm.upfront_flows,
                               node_files=ctx.get("node_files"), ledger=svc.ledger, rid=rid, stories=top,
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_brief_context.py tests/test_ondemand.py tests/test_tortoise.py -q`
Expected: PASS: `38 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `507 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_brief_context.py backend/tests/test_ondemand.py backend/tests/test_tortoise.py backend/codetortoise/llm/brief_context.py backend/codetortoise/llm/ondemand.py backend/codetortoise/llm/storyboard.py backend/codetortoise/llm/tortoise.py backend/codetortoise/pipeline.py
git commit -m "feat(llm): tier-2 prompts start from the brief; tier 1's verdicts and stories stand when tier 2 explains"
```

### Task 9: Measuring stability; Re-run stories (fresh); tier 1 in the AI view

Spec §4.6, §9, §10 (owner). `codetortoise stories-check <review> --runs N` runs tier 1 N times on the review's stored change, with no cache. It prints how often each pair of pieces shared a story and the agreement score: the share of piece pairs every run agreed on. It stores nothing. `POST /api/reviews/{id}/rerun?fresh=true` re-runs the review and asks the strong model again. `GET /api/reviews/{id}/ai` adds `tier1` and `strong` (the strong model's name, or null).

**Files:**
- Test: `backend/tests/test_stories_check.py`
- Test: `backend/tests/test_web.py`
- Modify: `backend/codetortoise/cli.py`
- Create: `backend/codetortoise/stories_check.py`
- Modify: `backend/codetortoise/web/app.py`

**Interfaces:**
- Consumes: `form_stories` (Task 6), `JobRunner.submit_review(rid, fresh)` (Task 6), `Ledger.usage()["tier1"]` (Task 5).
- Produces: `stories_check.pair_counts(plans, ids) -> dict[tuple[str, str], int]`, `agreement(plans, ids) -> tuple[int, int]`, `stored_context(svc, rid) -> tuple[BoardContext, PieceSet]`, `stories_check(svc, rid, runs, out=print) -> int` (raises `ValueError` without a strong model or pieces);
  CLI `stories-check --config C <review> [--runs 3]`; `rerun(..., fresh: bool = False)`; the AI view's `tier1` and `strong`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_stories_check.py` (new file):

```python
"""Measuring how stable tier 1's stories are (spec 2026-10-05-two-tier-stories §4.6)."""
import itertools

from helpers import make_services
from test_pipeline import _one_story_per_cl, _strong

from codetortoise.cli import main
from codetortoise.grouping import Placement, PlannedStory, StoryPlan
from codetortoise.pipeline import run_review
from codetortoise.stories_check import agreement, pair_counts, stories_check


def _plan(*groups, unsorted=()):
    stories = [PlannedStory(key=f"s{i}", source="tier1", placements=[Placement(piece=p, reason="same_feature") for p in g])
               for i, g in enumerate(groups)]
    if unsorted:
        stories.append(PlannedStory(key="unsorted", unsorted=True, source="tier1",
                                    placements=[Placement(piece=p, reason="unclear") for p in unsorted]))
    return StoryPlan(stories=stories)


def test_pairs_count_the_runs_putting_them_together_and_agreement_is_the_share_every_run_agreed_on():
    ids = ["P1", "P2", "P3", "P4"]
    plans = [_plan(["P1", "P2"], ["P3"], unsorted=["P4"]), _plan(["P1", "P2", "P3"], ["P4"])]
    assert pair_counts(plans, ids) == {("P1", "P2"): 2, ("P1", "P3"): 1, ("P2", "P3"): 1}
    # 6 pairs; P1-P3 and P2-P3 disagree; unsorted pieces share no story with anything
    assert agreement(plans, ids) == (4, 6)


def test_stories_check_runs_tier_1_without_the_cache_and_changes_nothing_stored(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    before = (svc.store.get_brief(rid), svc.store.get_blob(rid, "stories"), svc.store.list_findings(rid))
    flip = itertools.count()

    def answer(system, user):                       # the second run puts every piece in one story
        out = _one_story_per_cl(system, user)
        if next(flip) == 1:
            out["stories"] = [{**out["stories"][0], "pieces": [p for s in out["stories"] for p in s["pieces"]]}]
            for i, p in enumerate(out["stories"][0]["pieces"]):
                p["reason"] = "starts_purpose" if i == 0 else "same_feature"
        return out
    llm = _strong(svc, answer)
    lines = []
    assert stories_check(svc, rid, 2, out=lines.append) == 0
    assert len(llm.prompts) == 2
    assert lines[0].startswith(f"review {rid}: 2 runs of the stories stage by big, ")
    assert lines[-1].startswith("agreement: ") and "piece pairs agreed in every run" in lines[-1]
    assert any(line.endswith(" 1/2") for line in lines) and any(line.endswith(" 2/2") for line in lines)
    assert (svc.store.get_brief(rid), svc.store.get_blob(rid, "stories"), svc.store.list_findings(rid)) == before
    assert svc.ledger is None or svc.ledger.tier1_used(rid) == 0


def test_stories_check_needs_a_strong_model(fx, tmp_path, capsys, monkeypatch):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    monkeypatch.setattr("codetortoise.cli._services", lambda config: svc)
    assert main(["stories-check", "--config", "x.yaml", str(rid), "--runs", "2"]) == 1
    assert "no strong model configured (llm.strong)" in capsys.readouterr().err
```

`backend/tests/test_web.py` (diff):

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index c924d3d..4df1a1a 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -356,3 +356,19 @@ def test_neighbours_list_a_nodes_callers_and_callees(env):
     assert len(own["callers"]["items"]) == min(50, own["callers"]["total"]) and len(own["callees"]["items"]) <= 1
     r = owner.get(f"/api/reviews/{rid}/nodes/N99999/neighbours")
     assert r.status_code == 404 and r.json()["detail"] == "no node N99999 in this review"
+
+
+def test_the_owner_reruns_stories_fresh_and_the_ai_view_shows_tier_1(env):
+    from test_pipeline import _one_story_per_cl, _strong
+    svc, app, _ = env
+    llm = _strong(svc, _one_story_per_cl)
+    owner = login(app, "owner")
+    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
+    calls = len(llm.prompts)
+    assert owner.post(f"/api/reviews/{rid}/rerun").json() == {"queued": True}
+    assert len(llm.prompts) == calls                                   # the brief was reused
+    assert owner.post(f"/api/reviews/{rid}/rerun?fresh=true").json() == {"queued": True}
+    assert len(llm.prompts) == 2 * calls                               # fresh: the strong model was asked again
+    ai = owner.get(f"/api/reviews/{rid}/ai").json()
+    assert ai["strong"] == "big" and ai["tier1"]["budget"] == 40
+    assert login(app, "bob").post(f"/api/reviews/{rid}/rerun?fresh=true").status_code == 403
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_stories_check.py tests/test_web.py -q`
Expected: FAIL: `1 error`; the first error is `ModuleNotFoundError: No module named 'codetortoise.stories_check'`

- [ ] **Step 3: Implement**

`backend/codetortoise/cli.py` (diff):

```diff
diff --git a/backend/codetortoise/cli.py b/backend/codetortoise/cli.py
index 238b246..36b9b54 100644
--- a/backend/codetortoise/cli.py
+++ b/backend/codetortoise/cli.py
@@ -1,4 +1,4 @@
-"""Command line: serve, index, review (headless), fixture-demo."""
+"""Command line: serve, index, review (headless), stories-check, fixture-demo."""
 from __future__ import annotations
 
 import argparse
@@ -81,6 +81,16 @@ def cmd_review(args) -> int:
     return 0
 
 
+def cmd_stories_check(args) -> int:
+    from codetortoise.stories_check import stories_check
+    svc = _services(args.config)
+    try:
+        return stories_check(svc, args.review, args.runs)
+    except ValueError as e:
+        print(str(e), file=sys.stderr)
+        return 1
+
+
 def cmd_init(args) -> int:
     from codetortoise.init_config import render, scan, summary
     from codetortoise.vcs.p4runner import P4Runner
@@ -191,6 +201,11 @@ def main(argv: list[str] | None = None) -> int:
     s.add_argument("--title")
     s.add_argument("cls", nargs="+", type=int)
     s.set_defaults(fn=cmd_review)
+    s = sub.add_parser("stories-check", help="run tier 1's stories N times on a review and print how often they agree")
+    s.add_argument("--config", required=True)
+    s.add_argument("review", type=int)
+    s.add_argument("--runs", type=int, default=3)
+    s.set_defaults(fn=cmd_stories_check)
     s = sub.add_parser("init", help="write a starter tortoise.yaml for the workspace you are in")
     s.add_argument("--root", default=".", help="a folder inside the workspace (default: the current folder)")
     s.add_argument("--out", default="tortoise.yaml")
```

`backend/codetortoise/stories_check.py` (new file):

```python
"""How stable are tier 1's stories? (spec 2026-10-05-two-tier-stories §4.6)

`codetortoise stories-check <review> --runs N` runs the stories stage N times on the review's stored change, without
the cache, and prints for each pair of pieces how often they shared a story, and the agreement score: the share of
piece pairs every run agreed on (together in every run, or apart in every run). It changes nothing stored and its calls
are not charged to the review.
"""
from __future__ import annotations

import itertools
from collections.abc import Callable

from codetortoise.board import BoardContext, analyse
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import Facts
from codetortoise.grouping import StoryPlan
from codetortoise.impact import ImpactModel
from codetortoise.layers import LayerModel
from codetortoise.llm.stories import form_stories
from codetortoise.paths import canon
from codetortoise.pieces import PieceSet
from codetortoise.services import Services
from codetortoise.vcs.model import ChangeSet


def _home(plan: StoryPlan) -> dict[str, str]:
    """Each piece's story; an unsorted piece shares a story with nothing."""
    return {pl.piece: (pl.piece if s.unsorted else s.key) for s in plan.stories for pl in s.placements}


def pair_counts(plans: list[StoryPlan], ids: list[str]) -> dict[tuple[str, str], int]:
    """(piece, piece) -> how many runs put them in one story; pairs never together are left out."""
    homes = [_home(p) for p in plans]
    out = {}
    for a, b in itertools.combinations(ids, 2):
        n = sum(1 for h in homes if a in h and h.get(a) == h.get(b))
        if n:
            out[(a, b)] = n
    return out


def agreement(plans: list[StoryPlan], ids: list[str]) -> tuple[int, int]:
    """(pairs every run agreed on, all pairs)."""
    counts = pair_counts(plans, ids)
    pairs = list(itertools.combinations(ids, 2))
    return sum(1 for pr in pairs if counts.get(pr, 0) in (0, len(plans))), len(pairs)


def stored_context(svc: Services, rid: int) -> tuple[BoardContext, PieceSet]:
    """The review's change as its last run stored it, and its pieces."""
    s = svc.store
    ctx = BoardContext(ChangeSet.model_validate(s.get_blob(rid, "changeset")), DiffMap.model_validate(s.get_blob(rid, "diffmap")),
                       [Facts.model_validate(f) for f in s.get_blob(rid, "facts_before") or []],
                       [Facts.model_validate(f) for f in s.get_blob(rid, "facts_after") or []],
                       ImpactModel.model_validate(s.get_blob(rid, "impact")), s.list_findings(rid),
                       LayerModel.model_validate(s.get_blob(rid, "layers")) if s.get_blob(rid, "layers") else None,
                       svc.cfg.analysis, lambda paths: {}, root=canon(str(svc.cfg.workspace.root)))
    return ctx, PieceSet.model_validate(s.get_blob(rid, "pieces"))


def stories_check(svc: Services, rid: int, runs: int, out: Callable[[str], None] = print) -> int:
    strong = svc.cfg.llm.strong
    if svc.strong is None or strong is None:
        raise ValueError("no strong model configured (llm.strong)")
    if not svc.store.get_blob(rid, "pieces"):
        raise ValueError(f"review {rid} has no pieces: run it first")
    ctx, ps = stored_context(svc, rid)
    x = analyse(ctx).x
    plans = [form_stories(svc.strong, None, None, ps, x, strong, ctx.findings) for _ in range(max(1, runs))]
    ids = [p.id for p in ps.pieces]
    out(f"review {rid}: {len(plans)} runs of the stories stage by {strong.model}, {len(ids)} pieces")
    for i, p in enumerate(plans, 1):
        for note in p.notes:
            out(f"run {i}: {note}")
    out("pairs that shared a story (runs together / runs):")
    for (a, b), n in sorted(pair_counts(plans, ids).items(), key=lambda kv: (kv[1], kv[0])):
        out(f"  {a} {b}  {n}/{len(plans)}")
    agreed, total = agreement(plans, ids)
    out(f"agreement: {agreed / total if total else 1:.2f} ({agreed} of {total} piece pairs agreed in every run)")
    return 0
```

`backend/codetortoise/web/app.py` (diff):

```diff
diff --git a/backend/codetortoise/web/app.py b/backend/codetortoise/web/app.py
index 0ba8794..9aa6a9b 100644
--- a/backend/codetortoise/web/app.py
+++ b/backend/codetortoise/web/app.py
@@ -168,9 +168,10 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         return {"review": review_or_404(rid), "cls": store.list_cls(rid), "stages": store.list_stages(rid)}
 
     @app.post("/api/reviews/{rid}/rerun")
-    def rerun(rid: int, _: str = Depends(owner_of)):
+    def rerun(rid: int, fresh: bool = False, _: str = Depends(owner_of)):
+        """Run the review again; `fresh` asks the strong model for new stories instead of reusing a brief."""
         review_or_404(rid)
-        runner.submit_review(rid)
+        runner.submit_review(rid, fresh=fresh)
         return {"queued": True}
 
     @app.get("/api/reviews/{rid}/events")
@@ -405,10 +406,12 @@ def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
         review_or_404(rid)
         b = cfg.llm.budget
         u = svc.ledger.usage(rid) if svc.ledger else {"used": 0, "budget": b.per_review, "by_person": {},
-                                                      "by_purpose": {}, "calls": []}
+                                                      "by_purpose": {}, "calls": [],
+                                                      "tier1": {"used": 0, "budget": b.tier1_per_review}}
         u.pop("calls", None)                           # polled while work is pending; the list is /ai/calls
         rounds = svc.ledger.rounds(rid) if svc.ledger else b.per_mention
-        return {**u, "llm": svc.llm is not None, "me_today": svc.ledger.person_today(user) if svc.ledger else 0,
+        strong = cfg.llm.strong.model if svc.strong is not None and cfg.llm.strong else None
+        return {**u, "llm": svc.llm is not None, "strong": strong, "me_today": svc.ledger.person_today(user) if svc.ledger else 0,
                 "me_limit": b.per_person_daily, "per_mention": rounds, "is_owner": user == cfg.owner,
                 "jobs": runner.ai_jobs.get(rid, []), "file_summaries": store.get_blob(rid, "file_summaries") or {}}
 
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_stories_check.py tests/test_web.py -q`
Expected: PASS: `28 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `511 passed, 1 skipped`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_stories_check.py backend/tests/test_web.py backend/codetortoise/cli.py backend/codetortoise/stories_check.py backend/codetortoise/web/app.py
git commit -m "feat(stories): stories-check measures tier 1's agreement across runs; the owner re-runs stories fresh; the AI view shows tier 1"
```

### Task 10: The UI: targets, why together, what to check, Unsorted, the AI review

Spec §10, §11 (fake_llm, e2e). A story's detail lists its pieces with their files and names (`StoryPiece`). The UI changes:
- **Story page:** target chips beside the CL chips when the review spans more than one target; "What to check" and "Open questions" under the header; "Why these belong together" (each piece's files, its reason in words, and evidence links to pieces, stories and CLs) and "Related" ("see S2 · hal") after the steps.
- **Unsorted story:** listed last in the rail under "Needs a person to place these"; each piece shows the check it failed.
- **Finding page:** "AI review: hazard / needs review / no hazard — reason" in red, amber or plain, with its citations as links to the function's code or the file at that line.
- **Rail:** target chips when the review spans more than one target.
- **Header:** the owner gets "Re-run stories (fresh)" when a strong model is configured.
- **AI usage:** the strong model's calls.
- **Health:** a notice when code goes to an off-site endpoint.
- **Tier-1 stories:** Ask… only, no ✦ Explain.

`fake_llm.py` answers the stories, merge and review prompts. `serve-strong.sh` starts a fixture server on 8795 whose targets are `hal` and `fw`, with the fake model as the strong model.

**Files:**
- Test: `backend/tests/test_stories.py`
- Test: `frontend/e2e/fake_llm.py`
- Test: `frontend/e2e/serve-strong.sh`
- Test: `frontend/e2e/workspace-tier1.spec.ts`
- Test: `frontend/playwright.config.ts`
- Test: `frontend/src/stories/stories.test.ts`
- Modify: `backend/codetortoise/stories.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/board/types.ts`
- Modify: `frontend/src/components/AiPill.tsx`
- Modify: `frontend/src/components/Explain.tsx`
- Modify: `frontend/src/pages/Health.tsx`
- Modify: `frontend/src/stories/stories.ts`
- Modify: `frontend/src/workspace/FindingPage.tsx`
- Modify: `frontend/src/workspace/Rail.tsx`
- Modify: `frontend/src/workspace/StoryPage.tsx`
- Create: `frontend/src/workspace/StoryPlan.tsx`
- Modify: `frontend/src/workspace/Workspace.tsx`
- Modify: `frontend/src/workspace/workspace.css`

**Interfaces:**
- Consumes: the `Story` fields (Task 3), `Finding.verdict*` (Task 7), `rerun?fresh=true` and the AI view's `tier1`/`strong` (Task 9), the Health check's detail (Task 5).
- Produces: `stories.StoryPiece(id, kind, cl, files, names)`, `StoryDetail.pieces`; TS types `Placement`, `StoryPiece`, `StoryKind` with `"unsorted"`, `Story`'s optional `targets`, `pieces`, `placements`, `purpose`, `check`, `questions`, `related`, `source`; `Finding.verdict_cites`/`verdict_source`; `AiView.tier1`/`strong`; `api.rerun(id, fresh = false)`;
  `stories.ts`: `Sections.unsorted`, `reasonText`, `reviewTargets`, `relatedLabel`, `citeTarget`; `StoryPlan.tsx`: `StoryChecks`, `StoryWhy`; `Explain`'s `askOnly`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_stories.py` (diff):

```diff
diff --git a/backend/tests/test_stories.py b/backend/tests/test_stories.py
index f1c6c38..f662a21 100644
--- a/backend/tests/test_stories.py
+++ b/backend/tests/test_stories.py
@@ -563,3 +563,5 @@ def test_a_plan_from_tier_1_gives_titles_purposes_checks_related_stories_and_an_
     assert s2.title == "Other changes in `dsp`" and s2.purpose == "DSP side." and s2.targets == ["dsp"]   # its title failed
     assert (s3.kind, s3.title) == ("unsorted", "Unsorted: needs a person to place these")
     assert det[s3.id].graph is not None
+    assert [(p.id, p.files, p.names) for p in det[s1.id].pieces] == [
+        (pid["modem_tx"], ["//d/w/modem/tx.c"], ["modem_tx"]), (pid["modem_rx"], ["//d/w/modem/rx.c"], ["modem_rx"])]
```

`frontend/e2e/fake_llm.py` (diff):

```diff
diff --git a/frontend/e2e/fake_llm.py b/frontend/e2e/fake_llm.py
index d857afa..f52482a 100644
--- a/frontend/e2e/fake_llm.py
+++ b/frontend/e2e/fake_llm.py
@@ -7,7 +7,61 @@ from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
 CITES = [f"N{i}" for i in range(1, 80)] + [f"F{i}" for i in range(1, 20)]
 
 
+PURPOSE = {   # the fixture's targets (serve-strong.sh): what each one's story is for
+    "fw": ("UART driver counts transmit errors", "uart_send now counts transmit errors, so its callers see a new error value.",
+           "Check that logger_flush handles the new -2.", "Does any caller retry a send after -2?"),
+    "hal": ("HAL writes take an unsigned register", "hal_write now takes an unsigned register, so callers pass the new type.",
+            "Check every caller of hal_write passes an unsigned register.", "Do any callers still pass a negative register?"),
+}
+
+
+def tier1_stories(user: str) -> dict:
+    """One story per target, first piece first; a shared piece is put in the last target's story without the shared_code
+    reason, so its check fails and it lands in Unsorted (the e2e tests look for it)."""
+    cards = re.findall(r"^(P\d+)  [^·\n]+ · targets? ([^·\n]+?)( \(shared\))? · CL (\d+)", user, re.M)
+    by_target: dict[str, list[str]] = {}
+    shared = []
+    for pid, targets, is_shared, _ in cards:
+        if is_shared:
+            shared.append(pid)
+        else:
+            by_target.setdefault(targets.split(", ")[0], []).append(pid)
+    keys = {t: f"s{i}" for i, t in enumerate(sorted(by_target))}
+    stories = []
+    for t in sorted(by_target):
+        title, purpose, check, question = PURPOSE.get(t, (f"Changes built for {t}", f"This changes the code built for {t}.",
+                                                         "Check the changed functions' callers.", "Is any caller left behind?"))
+        ids = by_target[t] + (shared if t == sorted(by_target)[-1] else [])
+        stories.append({"key": keys[t], "title": title, "purpose": purpose, "check": [check], "questions": [question],
+                        "related": [k for u, k in keys.items() if u != t],
+                        "pieces": [{"id": p, "reason": "starts_purpose" if i == 0 else "same_feature",
+                                    "evidence": [] if i == 0 else [ids[0]], "quote": []} for i, p in enumerate(ids)]})
+    return {"action": "answer", "stories": stories, "unsorted": []}
+
+
+def tier1_review(user: str) -> dict:
+    """The new -2 is a hazard, the Uart::errors write needs a person to confirm, the rest is fine; each cites a node id or
+    file:line from its own facts."""
+    verdicts = []
+    for block in re.split(r"\n\n(?=F\d+ \[)", user.split("FINDINGS:\n", 1)[1]):
+        head = re.match(r"(F\d+) \[\w+\] ([\w_]+): (.*)", block)
+        cite = re.search(r"\b(N\d+)\b|(\S+\.[ch]:\d+)", block.split("FACTS:", 1)[-1])
+        if not head or not cite:
+            continue
+        title = head.group(3)
+        verdict, reason = (("hazard", "logger_flush ignores the new -2, so a failed send goes unnoticed.")
+                           if "new return value" in title else
+                           ("needs_review", "uart_errors now reports what uart_send counts, so its readers see new values.")
+                           if "Uart::errors" in title else ("no_hazard", "Every user of this change was updated with it."))
+        verdicts.append({"finding": head.group(1), "verdict": verdict, "reason": reason, "cites": [cite.group(0)]})
+    return {"action": "answer", "verdicts": verdicts}
+
+
 def answer(system: str, user: str) -> dict:
+    if "forming the stories of a change" in system:
+        return {"related": [], "merge": []} if "STORIES (key | title" in user else tier1_stories(user)
+    if "judging the risks of one story" in system:
+        return tier1_review(user)
     if "Give each level" in user:
         return {"layers": []}
     if "Judge each side effect" in user:      # Uart::errors is the hazard; every other side effect is fine
```

`frontend/e2e/serve-strong.sh` (new file):

```bash
#!/usr/bin/env bash
# Starts a CodeTortoise whose stories come from a strong model (spec 2026-10-05-two-tier-stories): the fake model of
# fake_llm.py serves both tiers, and the fixture is split into two build targets, hal and fw.
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8795 >/dev/null
cat >> "$DIR/tortoise.yaml" <<YAML
llm:
  base_url: http://127.0.0.1:8797/v1
  model: fake
  upfront_flows: 0
  upfront_stories: 0
  upfront_findings: 0
  strong:
    base_url: http://127.0.0.1:8797/v1
    model: fake-strong
targets:
  - { match: "hal/*", name: hal }
  - { match: "*.c", name: fw }
YAML
export TORTOISE_LLM_KEY=fake TORTOISE_STRONG_KEY=fake
exec $CMD serve --config "$DIR/tortoise.yaml"
```

`frontend/e2e/workspace-tier1.spec.ts` (new file):

```ts
import { expect, test } from "@playwright/test";
import { expectNamed, login, startReview } from "./helpers";

const STRONG = "http://127.0.0.1:8795";  // e2e/serve-strong.sh: stories and risk review by the fake strong model, targets hal and fw

test.describe("stories formed by a strong model", () => {
  test.use({ baseURL: STRONG });

  test("a story shows its targets, why its pieces belong together, what to check, questions and related stories", async ({ page }) => {
    const base = await startReview(page);
    const rail = page.locator(".ws-rail");
    const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
    await expect(s1).toContainText("UART driver counts transmit errors");
    await expect(s1.locator(".ws-chip.target")).toHaveText("⌖ fw");                    // two targets: chips in the rail
    await page.goto(`${base}/s/S1`);
    const head = page.locator(".ws-story-head");
    await expect(head.locator(".ws-chip.target")).toHaveText("⌖ fw");
    await expect(head.getByRole("button", { name: /Explain/ })).toHaveCount(0);       // tier 2 never retells it
    await expect(head.getByRole("button", { name: "Ask…" })).toBeVisible();
    await expect(page.getByRole("region", { name: "What to check" })).toContainText("Check that logger_flush handles the new -2.");
    await expect(page.getByRole("region", { name: "Open questions" })).toContainText("Does any caller retry a send after -2?");
    const why = page.getByRole("region", { name: "Why these belong together" });
    await expect(why.locator("li")).toHaveCount(2);
    await expect(why.locator("li").first()).toContainText("starts the story");
    await expect(why.locator("li").nth(1)).toContainText("same feature");
    await expect(why.getByRole("link", { name: "Open //fixture/driver/uart.c" })).toBeVisible();
    const related = page.getByRole("region", { name: "Related" });
    await related.getByRole("link", { name: "see S2 · hal" }).click();
    await expect(page.locator(".ws-story-head h2")).toContainText("HAL writes take an unsigned register");
    await expectNamed(page);
  });

  test("the pieces it could not place are listed last, each with the check that failed", async ({ page }) => {
    const base = await startReview(page);
    const group = page.getByRole("region", { name: /^Stories/ }).locator(".ws-group").last();
    await expect(group.locator("h3")).toHaveText("Needs a person to place these");
    await page.goto(`${base}/s/S3`);
    const place = page.getByRole("region", { name: "Pieces to place" });
    await expect(place).toContainText("need a person to place them");
    await expect(place.locator(".ws-reason.failed")).toHaveText("target fw, hal differs from the story's (hal)");
  });

  test("a finding shows the AI review: hazard red, needs review amber, with its citations as links", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/f/F1`);
    const hazard = page.locator(".ws-verdict");
    await expect(hazard).toHaveClass(/hazard/);
    await expect(hazard).toContainText("AI review: hazard — logger_flush ignores the new -2, so a failed send goes unnoticed.");
    await hazard.getByRole("link", { name: "uart_send" }).click();               // a node id cited: its code opens
    await expect(page.getByRole("complementary", { name: /uart_send/ }).or(page.locator(".ws-detail"))).toBeVisible();
    await page.goto(`${base}/f/F2`);
    await expect(page.locator(".ws-verdict")).toHaveClass(/needs_review/);
    await expect(page.locator(".ws-verdict")).toContainText("AI review: needs review —");
    await page.goto(`${base}/f/F5`);
    const cited = page.locator(".ws-verdict").getByRole("link", { name: /^driver\/uart\.c:\d+$/ });
    await expect(cited).toBeVisible();                                            // a file:line cited: the diff opens there
  });

  test("the owner re-runs stories fresh and sees the strong model's calls", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(base);
    await page.getByRole("button", { name: /^AI \d+\/\d+$/ }).click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await expect(usage).toContainText(/Strong model \(fake-strong\): \d+ of 40 calls/);
    await usage.getByRole("button", { name: "Close" }).click();
    await page.getByRole("button", { name: "Re-run stories (fresh)" }).click();
    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ })).toBeVisible({ timeout: 60_000 });
  });

  test("Health says plainly when code goes to a model off the network", async ({ page }) => {
    await login(page);
    await page.route("**/api/health*", async (route) => {
      const real = await (await route.fetch()).json();
      real.checks = real.checks.map((c: { name: string; detail: string }) => c.name === "strong model endpoint"
        ? { ...c, detail: "https://models.example.com/v1 (big); code from reviewed changes is sent to models.example.com" } : c);
      await route.fulfill({ json: real });
    });
    await page.goto("/health");
    await expect(page.getByRole("note")).toContainText("Code from reviewed changes is sent to models.example.com");
  });
});
```

`frontend/playwright.config.ts` (diff):

```diff
diff --git a/frontend/playwright.config.ts b/frontend/playwright.config.ts
index c71e05f..c370d74 100644
--- a/frontend/playwright.config.ts
+++ b/frontend/playwright.config.ts
@@ -10,6 +10,8 @@ export default defineConfig({
     { command: "python3 e2e/fake_llm.py 8797", url: "http://127.0.0.1:8797/v1/models", timeout: 30_000, reuseExistingServer: false },
     { command: "bash e2e/serve-ai.sh", url: "http://127.0.0.1:8798/api/me", timeout: 120_000, reuseExistingServer: false },
     // large changes (the "a large change" tests in e2e/workspace*.spec.ts): the generated fixture whose CLs need several boards
+    // two-tier stories (e2e/workspace-tier1.spec.ts): the fake model as the strong model too, the fixture split into targets
+    { command: "bash e2e/serve-strong.sh", url: "http://127.0.0.1:8795/api/me", timeout: 120_000, reuseExistingServer: false },
     { command: "bash e2e/serve-large.sh", url: "http://127.0.0.1:8796/api/me", timeout: 120_000, reuseExistingServer: false },
   ],
 });
```

`frontend/src/stories/stories.test.ts` (diff):

```diff
diff --git a/frontend/src/stories/stories.test.ts b/frontend/src/stories/stories.test.ts
index 7ddedde..d9e680b 100644
--- a/frontend/src/stories/stories.test.ts
+++ b/frontend/src/stories/stories.test.ts
@@ -1,6 +1,6 @@
 import { describe, expect, it } from "vitest";
 import type { Story, StorySet, StorySite } from "../board/types";
-import { countLine, groupSites, sections, stepStory } from "./stories";
+import { citeTarget, countLine, groupSites, reasonText, relatedLabel, reviewTargets, sections, stepStory } from "./stories";
 
 const story = (id: string, kind: Story["kind"], extra: Partial<Story> = {}): Story => ({
   id, kind, title: id, summary: "", text_source: "template", risk: null, counts: {}, nodes: [], flows: [], findings: [],
@@ -18,6 +18,7 @@ describe("stories", () => {
     expect(s.behaviour.map((x) => x.id)).toEqual(["S1"]);
     expect(s.collapsed.map((x) => x.id)).toEqual(["S2"]);
     expect([s.other, s.mechanical, s.tests].map((xs) => xs.map((x) => x.id))).toEqual([["S3"], ["S4"], ["S5"]]);
+    expect(sections(set([story("S1", "other"), story("S2", "unsorted")])).unsorted.map((x) => x.id)).toEqual(["S2"]);
   });
 
   it("steps between stories in list order, wrapping around", () => {
@@ -41,4 +42,31 @@ describe("stories", () => {
     expect(g[0].files.map((f) => [f.name, f.sites.map((s) => s.line)])).toEqual([["a.c", [1]], ["b.c", [3, 9]]]);
     expect(groupSites(sites, true).map((d) => d.dir)).toEqual(["//d/src"]);
   });
+
+  it("says a placement's reason in words, and a failed check as it is", () => {
+    expect(reasonText("caller_of_new_code")).toBe("calls the new code");
+    expect(reasonText("linked")).toBe("calls or shares data with the rest");
+    expect(reasonText("target dsp differs from the story's (modem)")).toBe("target dsp differs from the story's (modem)");
+  });
+
+  it("lists the review's targets, and names a related story with its targets", () => {
+    const ss = set([story("S1", "other", { targets: ["modem"] }), story("S2", "other", { targets: ["dsp", "modem"] }),
+                    story("S3", "tests")]);
+    expect(reviewTargets(ss)).toEqual(["dsp", "modem"]);
+    expect(relatedLabel(ss, "S2")).toBe("S2 · dsp, modem");
+    expect(relatedLabel(ss, "S9")).toBe("S9");
+  });
+
+  it("reads a citation as a node id or a file and line", () => {
+    expect(citeTarget("N12")).toEqual({ node: "N12" });
+    expect(citeTarget("drv/old.c:3")).toEqual({ file: "drv/old.c", line: 3 });
+    expect(citeTarget("whatever")).toBeNull();
+  });
+
+  it("reads stories stored before two-tier stories: no targets, pieces or plan", () => {
+    const old = set([story("S1", "behaviour"), story("S2", "other")]);    // none of the new fields
+    expect(reviewTargets(old)).toEqual([]);
+    expect(relatedLabel(old, "S1")).toBe("S1");
+    expect(sections(old).unsorted).toEqual([]);
+  });
 });
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_stories.py -q`
Expected: FAIL: `1 failed, 34 passed`; the first error is `AttributeError: 'StoryDetail' object has no attribute 'pieces'`

Run: `cd frontend && npx vitest run src/stories/stories.test.ts`
Expected: FAIL: `Tests 5 failed | 3 passed (8)`; the first error is `TypeError: Cannot read properties of undefined (reading 'map')`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-tier1.spec.ts`
Expected: FAIL: `npm run build fails with 10 type error(s)`; the first error is `src/stories/stories.test.ts(3,10): error TS2305: Module '"./stories"' has no exported member 'citeTarget'.`

- [ ] **Step 3: Implement**

`backend/codetortoise/stories.py` (diff):

```diff
diff --git a/backend/codetortoise/stories.py b/backend/codetortoise/stories.py
index 7f73912..1565858 100644
--- a/backend/codetortoise/stories.py
+++ b/backend/codetortoise/stories.py
@@ -100,6 +100,15 @@ class Story(BaseModel):
     source: Literal["tier1", "rules"] = "rules"             # who grouped it
 
 
+class StoryPiece(BaseModel):
+    """One piece of a story, for "Why these belong together" (spec 2026-10-05-two-tier-stories §10)."""
+    id: str
+    kind: str
+    cl: int | None = None
+    files: list[str] = Field(default_factory=list)          # depot paths (workspace-relative when unknown)
+    names: list[str] = Field(default_factory=list)          # its changed functions, or a declaration piece's names
+
+
 class StoryDetail(BaseModel):
     story: Story
     board: Board                                            # every node the story mentions, for steps and code
@@ -107,6 +116,7 @@ class StoryDetail(BaseModel):
     functions: list[StoryFunction] = Field(default_factory=list)
     sites: list[StorySite] = Field(default_factory=list)
     also_in: list[StoryRef] = Field(default_factory=list)   # a mechanical story: functions with other edits too
+    pieces: list[StoryPiece] = Field(default_factory=list)
 
 
 class StorySet(BaseModel):
@@ -534,7 +544,10 @@ def _detail(x: _Ctx, d: _Draft, st: Story, impacts: list[Impact], depots: dict[s
                   if m in x.changed and not is_test(m)] if d.kind == "tests" else [])
         functions.append(StoryFunction(node=n, label=x.label(n), note=_note(x, n, mech_of, fn_sites, mech_subs),
                                        on_flow=n in on_flow, also=also, calls=calls))
-    detail = StoryDetail(story=st, board=board, functions=functions)
+    root = x.c.root.rstrip("/") + "/"
+    detail = StoryDetail(story=st, board=board, functions=functions, pieces=[
+        StoryPiece(id=p.id, kind=p.kind, cl=p.cl, names=(p.names or [x.label(n) for n in p.nodes])[:6],
+                   files=[depots.get(f) or f.removeprefix(root) for f in p.files]) for p in d.pieces])
     if d.kind == "mechanical":
         own = {d.sub} if d.sub else set(d.subs)
         for s, local, nid in sorted(d.sites, key=lambda t: (t[1], t[0].after_line)):
```

`frontend/src/api.ts` (diff):

```diff
diff --git a/frontend/src/api.ts b/frontend/src/api.ts
index c59a60d..3761973 100644
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -18,8 +18,10 @@ export interface Finding {
   explanation: string | null; verify_steps: string[]; hypotheses: Cited[]; state: "open" | "ack" | "dismissed";
   /** Depot paths behind the finding (null: unknown). */
   files: string[] | null;
-  /** A new field write: neutral until the AI judges it; `verdict` is that judgement (null: not assessed). */
-  side_effect?: boolean; verdict?: "hazard" | "no_hazard" | null; verdict_reason?: string | null;
+  /** A new field write: neutral until the AI judges it; `verdict` is that judgement (null: not assessed). The strong
+   * model's story review (`verdict_source` "tier1") judges any finding, citing node ids and file:line it was shown. */
+  side_effect?: boolean; verdict?: "hazard" | "needs_review" | "no_hazard" | null; verdict_reason?: string | null;
+  verdict_cites?: string[]; verdict_source?: "tier1" | "tier2" | null;
 }
 /** A node's name for the workspace (review workspace §4.2): the reader sees names, never node ids. */
 export interface NodeName { label: string; kind: string; path: string | null; line: number | null; story: string | null }
@@ -45,6 +47,8 @@ export interface AiView {
   used: number; budget: number; by_person: Record<string, number>; by_purpose: Record<string, number>;
   llm: boolean; me_today: number; me_limit: number; per_mention: number; is_owner: boolean; jobs: AiJob[];
   file_summaries: Record<string, FileSummary>;
+  /** The strong model's calls on this review (stories and risk review) and its name (null: not configured). */
+  tier1?: { used: number; budget: number }; strong?: string | null;
 }
 export interface HealthCheck { name: string; ok: boolean; hard: boolean; detail: string }
 export interface Health { checks: HealthCheck[]; ready: boolean; index_generation: number; libclang: string | null; strip_flags: string[]; index_building: boolean;
@@ -82,7 +86,7 @@ export const api = {
   reviews: () => call<ReviewRow[]>("GET", "/api/reviews"),
   createReview: (cls: number[], title?: string) => call<ReviewRow>("POST", "/api/reviews", { cls, title }),
   review: (id: number) => call<ReviewDetail>("GET", `/api/reviews/${id}`),
-  rerun: (id: number) => call("POST", `/api/reviews/${id}/rerun`),
+  rerun: (id: number, fresh = false) => call("POST", `/api/reviews/${id}/rerun${fresh ? "?fresh=true" : ""}`),
   board: (id: number, cluster?: string | null) =>
     call<Board>("GET", `/api/reviews/${id}/board${cluster ? `?${new URLSearchParams({ cluster })}` : ""}`),
   overview: (id: number) => call<Overview>("GET", `/api/reviews/${id}/overview`),
```

`frontend/src/board/types.ts` (diff):

```diff
diff --git a/frontend/src/board/types.ts b/frontend/src/board/types.ts
index 13ac94e..cb16afc 100644
--- a/frontend/src/board/types.ts
+++ b/frontend/src/board/types.ts
@@ -55,7 +55,11 @@ export interface Overview {
 export interface SourceText { path: string; depot: string; rev: string; text: string; changed: boolean }
 
 /** Change stories (spec 2026-10-04-change-stories), as served by GET /api/reviews/{id}/stories[/{sid}]. */
-export type StoryKind = "behaviour" | "other" | "mechanical" | "tests";
+export type StoryKind = "behaviour" | "other" | "mechanical" | "tests" | "unsorted";
+/** Why a piece is in its story (spec 2026-10-05-two-tier-stories §4.3): a reason word, the pieces and CLs it relies on,
+ * quotes from CL descriptions; in the Unsorted story, `reason` is the check that failed. */
+export interface Placement { piece: string; reason: string; evidence: string[]; quote: string[] }
+export interface StoryPiece { id: string; kind: string; cl: number | null; files: string[]; names: string[] }
 export interface Story {
   id: string; kind: StoryKind; title: string; summary: string; text_source: "template" | "llm"; risk: string | null;
   /** AI text: the files whose code was in its prompt (null: unknown). */
@@ -65,6 +69,10 @@ export interface Story {
   /** The changelists of the files holding its code (review workspace §4.1; [] for stories stored before them). */
   cls: number[];
   sub: [string, string] | null; subs: [string, string][]; collapsed: boolean;
+  /** Two-tier stories (absent on stories stored before them): build targets, pieces and why each is here, and — when the
+   * strong model formed it — what it is for, what to check, open questions and related stories' ids. */
+  targets?: string[]; pieces?: string[]; placements?: Placement[]; purpose?: string; check?: string[]; questions?: string[];
+  related?: string[]; source?: "tier1" | "rules";
 }
 export interface StoryRef { node: string; label: string; story: string | null }
 export interface StoryFunction { node: string; label: string; note: string; on_flow: boolean; also: string[]; calls: StoryRef[] }
@@ -74,6 +82,7 @@ export interface StorySite {
 }
 export interface StoryDetail {
   story: Story; board: Board; graph: Board | null; functions: StoryFunction[]; sites: StorySite[]; also_in: StoryRef[];
+  pieces?: StoryPiece[];
 }
 export interface StorySet {
   summary: string; stories: Story[];
```

`frontend/src/components/AiPill.tsx` (diff):

```diff
diff --git a/frontend/src/components/AiPill.tsx b/frontend/src/components/AiPill.tsx
index 640683b..fda97e7 100644
--- a/frontend/src/components/AiPill.tsx
+++ b/frontend/src/components/AiPill.tsx
@@ -36,6 +36,8 @@ function Usage({ onClose }: { onClose: () => void }) {
     <div className="ai-usage" role="dialog" aria-label="AI usage">
       <div className="row"><b>AI calls</b><span className="sp" /><button className="link small" onClick={onClose}>Close</button></div>
       <p>This review: <b>{v.used}</b> of {v.budget}. You today: <b>{v.me_today}</b> of {v.me_limit}.</p>
+      {v.strong && v.tier1 && <p>Strong model ({v.strong}): <b>{v.tier1.used}</b> of {v.tier1.budget} calls for stories and
+        their risk review.</p>}
       <p className="muted small">By purpose: {counts(v.by_purpose)}<br />By person: {counts(v.by_person)}</p>
       <p className="muted small">One @tortoise answer is 1 AI call of up to {v.per_mention} rounds.</p>
       {v.is_owner && (
```

`frontend/src/components/Explain.tsx` (diff):

```diff
diff --git a/frontend/src/components/Explain.tsx b/frontend/src/components/Explain.tsx
index 6d98b7f..bdc42fd 100644
--- a/frontend/src/components/Explain.tsx
+++ b/frontend/src/components/Explain.tsx
@@ -13,10 +13,12 @@ interface Props {
   label?: string;
   /** Where a question typed into Ask… goes: an @tortoise thread on this item (spec: explain with a question). */
   ask?: { kind: AnchorKind; anchor: Record<string, unknown>; onAsked: () => void };
+  /** Only Ask…: the item's text is the strong model's and tier 2 never rewrites it (two-tier stories §8). */
+  askOnly?: boolean;
 }
 
 /** ✦ Explain / ✦ Summarise (spec 2026-10-03 §4): one AI call, shown to everyone; a refusal or failure shows here. */
-export default function Explain({ kind, target, has, label = "Explain", ask }: Props) {
+export default function Explain({ kind, target, has, label = "Explain", ask, askOnly = false }: Props) {
   const ai = useAi();
   const [asking, setAsking] = useState(false);
   const [question, setQuestion] = useState("");
@@ -39,10 +41,12 @@ export default function Explain({ kind, target, has, label = "Explain", ask }: P
   const what = kind === "file" ? "summary" : "explanation";
   return (
     <span className="ai-ask" onClick={(e) => e.stopPropagation()}>
-      <button className="ai-btn" disabled={running} title={callTitle(ai.view)}
-              onClick={() => (!has || window.confirm(`Replace the current ${what}? It costs 1 AI call.`)) && ai.explain(kind, target)}>
-        ✦ {running ? `${label === "Explain" ? "Explaining" : "Summarising"}…` : has ? `${label} again` : label}
-      </button>
+      {!askOnly && (
+        <button className="ai-btn" disabled={running} title={callTitle(ai.view)}
+                onClick={() => (!has || window.confirm(`Replace the current ${what}? It costs 1 AI call.`)) && ai.explain(kind, target)}>
+          ✦ {running ? `${label === "Explain" ? "Explaining" : "Summarising"}…` : has ? `${label} again` : label}
+        </button>
+      )}
       {ask && (
         <button className="link small" aria-expanded={asking} title="Ask the AI something specific about this; it answers in a thread"
                 onClick={() => setAsking(!asking)}>Ask…</button>
```

`frontend/src/pages/Health.tsx` (diff):

```diff
diff --git a/frontend/src/pages/Health.tsx b/frontend/src/pages/Health.tsx
index 709cf09..25ee8fc 100644
--- a/frontend/src/pages/Health.tsx
+++ b/frontend/src/pages/Health.tsx
@@ -12,6 +12,10 @@ export default function Health() {
   return (
     <main className="page">
       <h1 className="hc-title">Health <span className={`hc-pill ${h.ready ? "ok" : "bad"}`}>● {h.ready ? "ready" : "not ready"}</span></h1>
+      {h.checks.flatMap((c) => /code from reviewed changes is sent to (\S+)/.exec(c.detail)?.[1] ?? []).map((host) => (
+        <div key={host} className="banner warn" role="note">Code from reviewed changes is sent to <b>{host}</b>, the strong
+          model's endpoint. Point <code>llm.strong.base_url</code> at a model on your network to keep it in house.</div>
+      ))}
       <div className="hc-list">
         {h.checks.map((c) => {
           const kind = c.ok ? "ok" : c.hard ? "bad" : "warn";
```

`frontend/src/stories/stories.ts` (diff):

```diff
diff --git a/frontend/src/stories/stories.ts b/frontend/src/stories/stories.ts
index dd09e1c..5bf8457 100644
--- a/frontend/src/stories/stories.ts
+++ b/frontend/src/stories/stories.ts
@@ -8,13 +8,15 @@ export interface Sections {
   other: Story[];
   mechanical: Story[];
   tests: Story[];
+  /** Pieces the strong model could not place, or whose placement failed a check: listed last. */
+  unsorted: Story[];
 }
 
 export function sections(ss: StorySet): Sections {
   const of = (k: Story["kind"]) => ss.stories.filter((s) => s.kind === k);
   return {
     behaviour: of("behaviour").filter((s) => !s.collapsed), collapsed: of("behaviour").filter((s) => s.collapsed),
-    other: of("other"), mechanical: of("mechanical"), tests: of("tests"),
+    other: of("other"), mechanical: of("mechanical"), tests: of("tests"), unsorted: of("unsorted"),
   };
 }
 
@@ -56,3 +58,33 @@ export function groupSites(sites: StorySite[], hideTests: boolean): SiteDir[] {
 
 /** Sites past which files start closed (a very large repeated edit lists files with a count, spec §6). */
 export const OPEN_SITES = 200;
+
+/** A placement's reason in words (spec 2026-10-05-two-tier-stories §4.2, §6); in the Unsorted story the reason is the
+ * check that failed, shown as it is. */
+const REASONS: Record<string, string> = {
+  starts_purpose: "starts the story", same_feature: "same feature", caller_of_new_code: "calls the new code",
+  same_fix: "same fix", same_refactor: "same refactor", shared_code: "code shared with another target",
+  declaration_used: "declares what the story uses", split_too_big: "split from a larger story",
+  linked: "calls or shares data with the rest", tests: "tests of this target", repeated: "the same edit repeated",
+};
+export function reasonText(reason: string): string {
+  return REASONS[reason] ?? reason;
+}
+
+/** Every build target the review's stories hold, sorted. */
+export function reviewTargets(ss: StorySet): string[] {
+  return [...new Set(ss.stories.flatMap((s) => s.targets ?? []))].sort();
+}
+
+/** "S4 · modem": a related story, with its targets. */
+export function relatedLabel(ss: StorySet, sid: string): string {
+  const t = ss.stories.find((s) => s.id === sid)?.targets ?? [];
+  return t.length ? `${sid} · ${t.join(", ")}` : sid;
+}
+
+/** A verdict's citation: a node id, or a file and line (as the prepared facts show them). */
+export function citeTarget(cite: string): { node: string } | { file: string; line: number } | null {
+  if (/^N\d+$/.test(cite)) return { node: cite };
+  const m = /^(.+):(\d+)$/.exec(cite);
+  return m ? { file: m[1], line: Number(m[2]) } : null;
+}
```

`frontend/src/workspace/FindingPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/FindingPage.tsx b/frontend/src/workspace/FindingPage.tsx
index 187dd16..f93202e 100644
--- a/frontend/src/workspace/FindingPage.tsx
+++ b/frontend/src/workspace/FindingPage.tsx
@@ -5,6 +5,7 @@ import { SeverityBadge } from "../components/Badges";
 import Comments from "../components/Comments";
 import Explain from "../components/Explain";
 import { useAi } from "../lib/ai";
+import { citeTarget } from "../stories/stories";
 import type { Address } from "./address";
 import { useWs } from "./context";
 import { short } from "./crumbs";
@@ -12,6 +13,7 @@ import { depotFor } from "./evidence";
 import NameText from "./NameText";
 
 const STATE = { open: "open", ack: "acknowledged", dismissed: "dismissed" } as const;
+const VERDICT = { hazard: "hazard", needs_review: "needs review", no_hazard: "no hazard" } as const;
 
 /** A finding (spec 2026-10-04-review-workspace §3.3): where it lives, the AI analysis first, then the evidence, each
  * line opening the diff at that line. */
@@ -56,7 +58,18 @@ export default function FindingPage({ fid }: { fid: string }) {
               mark {STATE[s]}</button>
           ))}
         </p>
-        {f.side_effect && (
+        {f.verdict_source === "tier1" && f.verdict ? (
+          <p className={`ws-verdict ${f.verdict}`}>
+            <span className="ai-label">AI</span>AI review: {VERDICT[f.verdict]} — <NameText text={f.verdict_reason ?? ""} />
+            {(f.verdict_cites ?? []).length > 0 && <span className="ws-cites"> · cites {(f.verdict_cites ?? []).map((c, k) => {
+              const t = citeTarget(c), depot = t && "file" in t ? depotFor(t.file, depots) : null;
+              const link = t && "node" in t && d.names[c] ? <Link to={ws.link(ws.opened({ node: c }))} title={`Open ${d.names[c].label}'s code`}>{d.names[c].label}</Link>
+                : t && "file" in t && depot ? <Link className="mono" to={ws.link(ws.opened({ file: depot, line: t.line }))} title={`Open ${c}`}>{c}</Link>
+                : <span className="mono">{c}</span>;
+              return <span key={c}>{k > 0 && ", "}{link}</span>;
+            })}</span>}
+          </p>
+        ) : f.side_effect && (
           <p className={`ws-verdict${f.verdict === "hazard" ? " hazard" : ""}`}>
             {f.verdict === "hazard" ? <><span className="ai-label">AI</span>AI: hazard — <NameText text={f.verdict_reason ?? ""} /></>
               : f.verdict === "no_hazard" ? <><span className="ai-label">AI</span>AI: no clear hazard — <NameText text={f.verdict_reason ?? ""} /></>
```

`frontend/src/workspace/Rail.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Rail.tsx b/frontend/src/workspace/Rail.tsx
index ddb2158..0aa6d23 100644
--- a/frontend/src/workspace/Rail.tsx
+++ b/frontend/src/workspace/Rail.tsx
@@ -4,7 +4,7 @@ import type { Story } from "../board/types";
 import { keys, load, loadWidth, save } from "../board/prefs";
 import Resizer from "../board/Resizer";
 import { plainTitle } from "../lib/markdown";
-import { sections } from "../stories/stories";
+import { reviewTargets, sections } from "../stories/stories";
 import { type Place, samePlace } from "./address";
 import { useWs } from "./context";
 import { short } from "./crumbs";
@@ -59,13 +59,15 @@ export default function Rail({ show, onPick, hidden = false }: { show: string |
     </section>
   );
   const ss = d.stories, lit = ss ? litStories(ss, cl) : null;
+  const manyTargets = !!ss && reviewTargets(ss).length > 1;            // target chips only when the review spans targets
   const story = (st: Story) => row({ kind: "story", sid: st.id, view: "steps" }, `Go to story ${st.id}: ${short(st.title)}`, <>
     <span className="ws-row-top">
       {st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
       <span className="ws-row-title"><Ticks text={st.title} /></span>
       <span className="ws-handle">{st.id}</span>
     </span>
-    {st.cls.length > 0 && <span className="ws-chips">{st.cls.map((c) => <span key={c} className="ws-chip">CL {c}</span>)}</span>}
+    {(st.cls.length > 0 || manyTargets) && <span className="ws-chips">{st.cls.map((c) => <span key={c} className="ws-chip">CL {c}</span>)}
+      {manyTargets && (st.targets ?? []).map((t) => <span key={t} className="ws-chip target">⌖ {t}</span>)}</span>}
   </>, `story${lit && !lit.has(st.id) ? " dim" : ""}`, st.id);
   const group = (title: string, list: Story[]) => list.length > 0 && (
     <div className="ws-group"><h3>{title}</h3><ul>{list.map((st) => <li key={st.id}>{story(st)}</li>)}</ul></div>
@@ -111,6 +113,7 @@ export default function Rail({ show, onPick, hidden = false }: { show: string |
         {group("Other changes", of.other)}
         {group("Repeated edits", of.mechanical)}
         {group("Tests", of.tests)}
+        {group("Needs a person to place these", of.unsorted)}
         {!ss.stories.length && <p className="muted small">No changed functions.</p>}
       </>)}
       {d.ready && section("findings", `Findings (${d.findings.length})`, (
```

`frontend/src/workspace/StoryPage.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/StoryPage.tsx b/frontend/src/workspace/StoryPage.tsx
index 39eb7a5..ecbe4ad 100644
--- a/frontend/src/workspace/StoryPage.tsx
+++ b/frontend/src/workspace/StoryPage.tsx
@@ -4,7 +4,7 @@ import { ApiError } from "../api";
 import type { StoryDetail } from "../board/types";
 import Comments from "../components/Comments";
 import Explain from "../components/Explain";
-import { countLine, stepStory } from "../stories/stories";
+import { countLine, reviewTargets, stepStory } from "../stories/stories";
 import { type Address, at as addressAt } from "./address";
 import { useWs } from "./context";
 import { short } from "./crumbs";
@@ -13,6 +13,7 @@ import FlowStrip from "./FlowStrip";
 import GraphView from "./graph/GraphView";
 import NameText, { Ticks } from "./NameText";
 import { MechanicalStory, TestsStory } from "./StoryBodies";
+import { StoryChecks, StoryWhy } from "./StoryPlan";
 import StorySteps from "./StorySteps";
 
 /** A story (spec 2026-10-04-review-workspace §3.2): header with the Steps | Graph switch beside the title and ‹ S1 of 4 ›
@@ -33,7 +34,8 @@ export default function StoryPage({ sid, view }: { sid: string; view: "steps" |
   const st = detail?.story ?? ss.stories.find((s) => s.id === sid)!;
   const at = ss.stories.findIndex((s) => s.id === sid);
   // known from the list, so the switch is there at once; gone if the story arrives without a graph after all
-  const hasGraph = (st.kind === "behaviour" || st.kind === "other") && (!detail || !!detail.graph);
+  const hasGraph = (st.kind === "behaviour" || st.kind === "other" || st.kind === "unsorted") && (!detail || !!detail.graph);
+  const targets = reviewTargets(ss).length > 1 ? st.targets ?? [] : [];      // chips only when the review spans targets
   const shown = hasGraph ? view : "steps";
   const flows = detail ? detail.board.flows.filter((f) => st.flows.includes(f.id)) : [];
   const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
@@ -63,11 +65,12 @@ export default function StoryPage({ sid, view }: { sid: string; view: "steps" |
         )}
         <span className="ws-pos">{step(-1)}<span>{st.id} of {ss.stories.length}</span>{step(1)}</span>
       </div>
-      <p><NameText text={st.summary} /> {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} ask={{ kind: "story", anchor: { id: st.id }, onAsked: d.loadComments }} />}</p>
+      <p><NameText text={st.summary} /> {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} askOnly={st.source === "tier1"} ask={{ kind: "story", anchor: { id: st.id }, onAsked: d.loadComments }} />}</p>
       <p className="ws-story-meta"><span className="muted">{countLine(st)}</span>
         {st.cls.map((c) => (
           <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
         ))}
+        {targets.map((t) => <span key={t} className="ws-chip target" title={`Build target ${t}`}>⌖ {t}</span>)}
         {map && <Link className="ws-chip ws-onmap" to={ws.link(map)} title={`Show ${st.id} on the map`} aria-label={`Show ${st.id} on the map`}>
           ◎ On the map</Link>}</p>
     </header>
@@ -88,11 +91,13 @@ export default function StoryPage({ sid, view }: { sid: string; view: "steps" |
   return (
     <div className="ws-page"><div className="ws-text">
       {header}
+      <StoryChecks detail={detail} />
       {st.kind === "mechanical" ? <MechanicalStory detail={detail} /> : st.kind === "tests" ? <TestsStory detail={detail} /> : <>
         {flows.length > 0 && <FlowStrip board={detail.board} flows={flows} index={index} onFlow={onFlow} steps={false}
                                         hideWhat={!!flows[index] && st.summary.startsWith(flows[index].what)} />}
         <StorySteps detail={detail} flow={flows[index]} />
       </>}
+      <StoryWhy detail={detail} />
       {at < 0 && <p className="muted">This story isn't in the list.</p>}
       <section aria-labelledby="ws-talk" className="ws-talk">
         <h3 id="ws-talk">Questions and comments</h3>
```

`frontend/src/workspace/StoryPlan.tsx` (new file):

```tsx
import { Link } from "react-router-dom";
import type { Placement, StoryDetail } from "../board/types";
import { reasonText, relatedLabel } from "../stories/stories";
import { useWs } from "./context";
import { short } from "./crumbs";
import NameText from "./NameText";

/** What to check and the open questions of a story the strong model formed (spec 2026-10-05-two-tier-stories §10). */
export function StoryChecks({ detail }: { detail: StoryDetail }) {
  const st = detail.story, check = st.check ?? [], questions = st.questions ?? [];
  return <>
    {check.length > 0 && (
      <section aria-labelledby="ws-check"><h3 id="ws-check">What to check</h3>
        <ol>{check.map((c, k) => <li key={k}><NameText text={c} /></li>)}</ol></section>
    )}
    {questions.length > 0 && (
      <section aria-labelledby="ws-questions"><h3 id="ws-questions">Open questions</h3>
        <ul>{questions.map((q, k) => <li key={k}><NameText text={q} /></li>)}</ul></section>
    )}
  </>;
}

/** Why a story's pieces belong together — each piece's files, its reason in words and the pieces and CLs it relies on —
 * and its related stories. The Unsorted story lists its pieces with the check each failed. */
export function StoryWhy({ detail }: { detail: StoryDetail }) {
  const ws = useWs(), ss = ws.data.stories!, st = detail.story;
  const placements = st.placements ?? [], related = st.related ?? [];
  const pieces = new Map((detail.pieces ?? []).map((p) => [p.id, p]));
  const unsorted = st.kind === "unsorted";
  const shown = unsorted || st.source === "tier1" || placements.length > 1;
  const evidence = (e: string) => {
    const cl = /^CL(\d+)$/.exec(e);
    if (cl) return <Link key={e} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: Number(cl[1]) }))}
                         title={`Open CL ${cl[1]}`} aria-label={`Open CL ${cl[1]}`}>CL {cl[1]}</Link>;
    if (pieces.has(e)) return <a key={e} className="ws-handle" href={`#piece-${e}`} title={`Go to piece ${e}`}>{e}</a>;
    const other = ss.stories.find((s) => s.pieces?.includes(e));
    return other ? <Link key={e} className="ws-handle" to={ws.link(ws.item({ kind: "story", sid: other.id, view: "steps" }))}
                         title={`Go to story ${other.id}: ${short(other.title)}`}>{e} · {other.id}</Link>
      : <span key={e} className="ws-handle">{e}</span>;
  };
  const row = (pl: Placement) => {
    const p = pieces.get(pl.piece);
    return (
      <li key={pl.piece} id={`piece-${pl.piece}`}>
        <span className="ws-handle">{pl.piece}</span>
        {p?.files.map((f) => (f.startsWith("//")
          ? <Link key={f} className="mono small" to={ws.link(ws.opened({ file: f, line: null }))} title={`Open ${f}`}
                  aria-label={`Open ${f}`}>{f.split("/").slice(-2).join("/")}</Link>
          : <span key={f} className="mono small">{f}</span>))}
        {p && p.names.length > 0 && <span className="muted small">{p.names.join(", ")}</span>}
        <span className={unsorted ? "ws-reason failed" : "ws-reason"}>{reasonText(pl.reason)}</span>
        {pl.evidence.length > 0 && <span className="ws-evid">{pl.evidence.map(evidence)}</span>}
        {pl.quote.map((q, k) => <q key={k} className="small">{q}</q>)}
      </li>
    );
  };
  return <>
    {shown && placements.length > 0 && (
      <section aria-labelledby="ws-why"><h3 id="ws-why">{unsorted ? "Pieces to place" : "Why these belong together"}</h3>
        {unsorted && <p className="muted">The strong model could not place these, or its placement failed a check: they need a
          person to place them.</p>}
        <ul className="ws-pieces">{placements.map(row)}</ul></section>
    )}
    {related.length > 0 && (
      <section aria-labelledby="ws-related"><h3 id="ws-related">Related</h3>
        <p className="ws-related">{related.map((r) => {
          const other = ss.stories.find((s) => s.id === r);
          return <Link key={r} to={ws.link(ws.item({ kind: "story", sid: r, view: "steps" }))}
                       title={other ? `Go to story ${r}: ${short(other.title)}` : `Go to story ${r}`}>see {relatedLabel(ss, r)}</Link>;
        })}</p></section>
    )}
  </>;
}
```

`frontend/src/workspace/Workspace.tsx` (diff):

```diff
diff --git a/frontend/src/workspace/Workspace.tsx b/frontend/src/workspace/Workspace.tsx
index f80bbad..ae63a60 100644
--- a/frontend/src/workspace/Workspace.tsx
+++ b/frontend/src/workspace/Workspace.tsx
@@ -6,7 +6,7 @@ import { driftSummary } from "../board/drift";
 import AiPill from "../components/AiPill";
 import { useSources } from "../board/useSources";
 import Stages from "../components/Stages";
-import { AiProvider } from "../lib/ai";
+import { AiProvider, useAi } from "../lib/ai";
 import { type Address, at, href, type Open, type Place, readAddress, type Tab } from "./address";
 import { useWs, type Ws, WsContext } from "./context";
 import Crumbs, { PhoneBar } from "./Crumbs";
@@ -115,7 +115,7 @@ function phoneBar(trail: Crumb[]): { back: Crumb; title: string; handle?: string
 }
 
 function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
-  const ws = useWs(), me = useMe(), d = ws.data, r = d.detail!.review;
+  const ws = useWs(), me = useMe(), ai = useAi(), d = ws.data, r = d.detail!.review;
   const notes = d.detail!.stages.filter((s) => s.status === "failed" || s.status === "degraded");
   const drift = driftSummary(d.about?.drift ?? []).warn;
   return (
@@ -127,6 +127,10 @@ function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
       {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
       {d.ready && <AiPill />}
       {me?.is_owner && d.ready && <button className="link rerun" onClick={() => api.rerun(d.id).then(d.loadDetail)}>Re-run</button>}
+      {me?.is_owner && d.ready && ai?.view?.strong && (
+        <button className="link" title="Ask the strong model for new stories instead of reusing the ones it formed for this change"
+                onClick={() => api.rerun(d.id, true).then(d.loadDetail)}>Re-run stories (fresh)</button>
+      )}
       {drift.length > 0 && <span className="bd-pill high" title={drift.join("\n")}>⚠ workspace drift ({drift.length})</span>}
       {notes.length > 0 && (
         <details className="bd-notes">
```

`frontend/src/workspace/workspace.css` (diff):

```diff
diff --git a/frontend/src/workspace/workspace.css b/frontend/src/workspace/workspace.css
index 54e57cf..04e7263 100644
--- a/frontend/src/workspace/workspace.css
+++ b/frontend/src/workspace/workspace.css
@@ -421,6 +421,15 @@ a.ws-nb:hover { border-color: var(--accent); }
 .ws-flow-lands.warn b { color: var(--bad); }
 .ws-verdict { font-size: 13.5px; color: var(--muted); margin: 4px 0 0; }
 .ws-verdict.hazard { color: var(--bad); }
+.ws-verdict.needs_review { color: var(--warn); }
+.ws-cites { font-size: 12.5px; }
+.ws-chip.target { border-style: dashed; }
+.ws-pieces { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
+.ws-pieces li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
+.ws-reason { font-size: 12.5px; padding: 0 6px; border-radius: 999px; background: var(--gap-bg); }
+.ws-reason.failed { color: var(--warn); }
+.ws-evid { display: inline-flex; flex-wrap: wrap; gap: 4px; }
+.ws-related { display: flex; flex-wrap: wrap; gap: 10px; }
 .ws-flow-check { color: var(--muted); }
 .ws-flow-steps { line-height: 1.9; }
 .ws-flow-steps .arrow { color: var(--muted); }
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && uv run pytest tests/test_stories.py -q`
Expected: PASS: `35 passed`

Run: `cd frontend && npx vitest run src/stories/stories.test.ts`
Expected: PASS: `Tests 8 passed (8)`

Run: `cd frontend && npm run build && npx playwright test e2e/workspace-tier1.spec.ts`
Expected: PASS: `5 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!`, then `511 passed, 1 skipped`

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build && npx playwright test`
Expected: tsc prints nothing; vitest `Tests 138 passed (138)`; Playwright `91 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_stories.py frontend/e2e/fake_llm.py frontend/e2e/serve-strong.sh frontend/e2e/workspace-tier1.spec.ts frontend/playwright.config.ts frontend/src/stories/stories.test.ts backend/codetortoise/stories.py frontend/src/api.ts frontend/src/board/types.ts frontend/src/components/AiPill.tsx frontend/src/components/Explain.tsx frontend/src/pages/Health.tsx frontend/src/stories/stories.ts frontend/src/workspace/FindingPage.tsx frontend/src/workspace/Rail.tsx frontend/src/workspace/StoryPage.tsx frontend/src/workspace/StoryPlan.tsx frontend/src/workspace/Workspace.tsx frontend/src/workspace/workspace.css
git commit -m "feat(ui): stories show their targets, why their pieces belong together, what to check, questions and related stories; Unsorted last; the AI review on findings; fresh re-run; Health's off-site notice"
```

### Task 11: Lab check (review 19)

Spec §11 (lab). There is no code here: rebuild lab review 19, check the spec's conditions and record the results in `lab/README.md`.

- [ ] **Step 1: Configure the strong model and the targets**

In `$LAB/tortoise.yaml`, add an `llm.strong` block for the strong model the owner chose. Which model to use is the owner's decision: an OpenAI-compatible endpoint with at least 64k context. Put its key in `TORTOISE_STRONG_KEY` in `$LAB/env.sh` and never print it. If the endpoint is off-site, Health will say so. libgit2 is one target, so no `targets:` block is needed.

- [ ] **Step 2: Rebuild review 19 and read its stories**

Run: `source $LAB/env.sh && $CT serve --config $LAB/tortoise.yaml`. As the owner, open review 19 and press **Re-run stories (fresh)**. If the P4 ticket has expired, log in again as `lab/README.md` says.
Expected:
- the stories stage reads "N stories formed by <model>, …";
- the clar helper `cl_sandbox_set_search_path_defaults` is in the programdata story;
- F2 (`config.h`) and F4 (`sysdir.h`) are in the programdata story;
- no story mixes CL 11 and CL 12 unless "Why these belong together" shows a link or a quote from each description;
- every finding page shows an AI review line with citations.

Rerun once with `llm.strong` removed. The rules' stories must also keep the clar helper and F2/F4 out of the reftable story.

- [ ] **Step 3: Measure stability**

Run: `$CT stories-check --config $LAB/tortoise.yaml 19 --runs 3`
Expected: one line per pair of pieces that shared a story, then `agreement: <score> (<a> of <b> piece pairs agreed in every run)`. Record the score.

- [ ] **Step 4: Record the results**

Add a "Two-tier stories" subsection to `lab/README.md` under "Change stories": the model, review 19's stories (title, target, pieces), where the clar helper, F2 and F4 landed, the review's verdict counts and the agreement score.

- [ ] **Step 5: Commit**

```bash
git add lab/README.md
git commit -m "docs(lab): two-tier stories on review 19"
```

## Finish

Every task's suite is green, and the lab README records review 19 and the agreement score. Use superpowers:finishing-a-development-branch.
