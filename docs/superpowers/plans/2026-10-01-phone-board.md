# Phone Board and Side-Effect Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the review board usable on a phone with a tabbed shell (Flows reader · touch Map · Files · Summary) built around reading flows, and list the files where side effects land in the change panel on every screen size.

**Architecture:** `Board` keeps all shared state (reducer, sources, lens) and, at ≤ 640 px, renders `PhoneBoard` instead of the desktop layout. The flow reader is driven by a pure `flowSteps`; the Map reuses `Canvas` with a `touch` mode and a phone-only zoom applied after the lens (`zoom.ts`); the side-effect file list is a pure `sideEffectFiles` used by the change panel and the phone Files picker. The backend adds one field, `Flow.title`.

**Tech Stack:** React 19, TypeScript 5.9 (strict), Vite 8, vitest 5 (node environment), Playwright (iPhone 13 profile, Chrome DevTools touch events for pinch); Python 3.12, pydantic v2, pytest, ruff. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-01-review-board-design.md` §13 (phone board and side-effect files). Earlier sections still apply where §13 is silent.

**Provenance:** every code block was run before the plan was written. The tasks were then replayed in order on a fresh tree from `main`: each task's tests failed before its implementation and passed after it, and the suites (backend with ruff; frontend unit tests with `tsc`) stayed green after every task. The replayed tree is byte-identical to the validated one. New files are given in full; changes to existing files are unified diffs against the previous task's state (`git apply`, or by hand).

## Global Constraints

- **Phone breakpoint:** `(max-width: 640px)`. At 641 px and wider the board is unchanged.
- **Touch:** zoom z ∈ [0.5, 2.5]; long press 450 ms before a node moves; swipe between flows when |dx| > 50 px and |dx| > 1.5·|dy| (not when the gesture starts in code); node touch targets ≥ 40 px at any zoom.
- **Phone tab:** remembered per review in `localStorage` key `ct.board.<reviewId>.tab` (`flows|map|files|summary`); default Flows, or Map when the review has no flows.
- **Flow titles:** templates "<landing> sees a new writer of <field>", "<landing> ignores <values>", "<landing> doesn't handle <values>", "<landing> calls <changed> (signature changed)"; old boards: the effect after "⟶", else "affects <last step>"; LLM titles ≤ 80 characters and only when the narrative is grounded.
- **CSS:** board classes are `bd-`/`ph-` prefixed or nested under `.bd`; page-level classes must not be generic words (Task 5 exists because `.landing` was).
- **Dependencies:** none added.
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).

## Review Focus

Conditions the spec implies that are most likely to bite a real user, most likely first. Each is pinned by a test in the task that owns the code.

1. **Pinching near the screen edge**, where the lens is folded: the point under the fingers must stay there. Pinned by `zoom.test.ts` › "in the lens's folded rim too" (Task 4) and the anchor check in `e2e/phone.spec.ts` › "phone map" (Task 7).
2. **A tap that opens a sheet under the finger**: the tap's click must not land in the new sheet (it opened a comment box). Pinned by the `textarea` count check in "phone map" (Task 7).
3. **A file that is in the change and also hosts side effects** (`driver/uart.c`): it must still be listed, marked "also changed". Pinned by `sideEffects.test.ts` (Task 3) and `e2e/phone.spec.ts` (Task 6).
4. **Boards stored before titles existed**: the phone reader still needs a headline. Pinned by `test_flows_stored_without_a_title_get_one_from_their_text` and `test_board_stored_by_an_older_version_gets_current_defaults` (Task 1).
5. **Page-level CSS leaking into the board**: the landing page's `.landing` grid broke the desktop flow summary. Pinned by the `display: block` check in `e2e/board.spec.ts` (Task 5).

---

### Task 1: Flow titles (backend)

The phone flow reader shows each flow under a short headline (spec §13.6). `Flow.title` is generated with the other
template text in `build_flows` (`flow_title`), the LLM may rewrite it together with `what` (same grounding rule; at most
80 characters), and boards stored before titles existed get one when `/board` re-validates them: the effect after "⟶"
("-2 ignored"), else "affects <last step>".

**Files:**
- Modify: `backend/codetortoise/board.py`
- Modify: `backend/codetortoise/llm/storyboard.py`
- Modify: `docs/superpowers/specs/2026-10-01-review-board-design.md`
- Modify: `backend/tests/test_board.py`
- Modify: `backend/tests/test_storyboard.py`
- Modify: `backend/tests/test_web.py`

**Interfaces:**
- Produces: `Flow.title: str` (always non-empty after validation); `board.flow_title(kind, landing, changed, field=None,
  values=None)` with kind `state|ignored|unhandled|signature`; `_FlowOut.title` in `llm/storyboard.py`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_board.py`:

```diff
diff --git a/backend/tests/test_board.py b/backend/tests/test_board.py
index b87398e..98991af 100644
--- a/backend/tests/test_board.py
+++ b/backend/tests/test_board.py
@@ -39,6 +39,8 @@ def test_fixture_board_has_the_three_prototype_flows(board):
     assert _labels(board, [ignored.fx_at]) == ["logger_flush"] and ignored.findings
     assert sig.text.endswith("⟶ signature changed")
     assert "uart_errors" in state.effect and "Uart::errors" in state.check
+    assert [f.title for f in board.flows] == ["uart_errors sees a new writer of Uart::errors", "logger_flush ignores -2",
+                                              "uart_init calls hal_write (signature changed)"]
 
 
 def test_fixture_board_annotates_where_the_effects_land(board):
@@ -240,3 +242,19 @@ def test_about_lists_workspace_drift():
     ctx.cs.drift = [DriftItem(depot="//d/lib/src/a.c", local="/w/a.c", expected="#3", actual="#4")]
     assert build_board(ctx).about.drift == ["//d/lib/src/a.c (base #3, workspace #4)"]
     assert build_board(_synthetic()[0]).about.drift == []
+
+
+def test_flow_titles_for_every_kind():
+    from codetortoise.board import flow_title
+    assert flow_title("state", "peek", "set", field="R::v") == "peek sees a new writer of R::v"
+    assert flow_title("ignored", "check_safecrlf", "output_eol", values="-1") == "check_safecrlf ignores -1"
+    assert flow_title("unhandled", "check_safecrlf", "output_eol", values="-1") == "check_safecrlf doesn't handle -1"
+    assert flow_title("signature", "uart_init", "hal_write") == "uart_init calls hal_write (signature changed)"
+
+
+def test_flows_stored_without_a_title_get_one_from_their_text():
+    from codetortoise.board import Flow
+    common = dict(id="FL1", tag="contract", lands="N3", severity="medium", what="w", effect="e", check="c")
+    assert Flow(path=["N1", "N3"], text="main → logger_flush → uart_send ⟶ -2 ignored", **common).title == "-2 ignored"
+    assert Flow(path=["N1", "N3"], text="main → uart_send → Uart::errors → uart_errors", **common).title == \
+        "affects uart_errors"
```

`backend/tests/test_storyboard.py`:

```diff
diff --git a/backend/tests/test_storyboard.py b/backend/tests/test_storyboard.py
index b0aa0c1..df5900d 100644
--- a/backend/tests/test_storyboard.py
+++ b/backend/tests/test_storyboard.py
@@ -128,7 +128,8 @@ def test_unexpected_llm_client_exception_keeps_skeleton():
 def _board(flows=2):
     from codetortoise.board import About, Board, Flow
     fl = [Flow(id=f"FL{i + 1}", path=["N3", "N2"], tag="contract", lands="N3", fx_at="N3", severity="medium",
-               findings=["F1"], text="logger_flush → uart_send ⟶ -2 ignored", what="template what", effect="e",
+               findings=["F1"], text="logger_flush → uart_send ⟶ -2 ignored", title="template title", what="template what",
+               effect="e",
                check="c") for i in range(flows)]
     return Board(flows=fl, about=About(intent="template intent"))
 
@@ -148,7 +149,7 @@ def _respond(flow_reply):
 def test_llm_writes_grounded_flow_narratives_and_the_change_intent():
     im, findings, layers = model()
     board = _board(3)
-    replies = iter([{"what": "flush drops -2", "cites": ["N3", "F1"]},
+    replies = iter([{"what": "flush drops -2", "title": "logger_flush drops -2 on flush", "cites": ["N3", "F1"]},
                     {"what": "uncited guess", "cites": ["N99"]},
                     {"what": "not asked for", "cites": ["N3"]}])
     sb = build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: next(replies))),
@@ -156,6 +157,7 @@ def test_llm_writes_grounded_flow_narratives_and_the_change_intent():
     assert sb.llm_used
     assert [(f.what, f.what_source) for f in board.flows] == [
         ("flush drops -2", "llm"), ("template what", "template"), ("template what", "template")]
+    assert [f.title for f in board.flows] == ["logger_flush drops -2 on flush", "template title", "template title"]
     assert board.about.intent == "the change adds tx stats" and board.about.intent_source == "llm"
 
 
```

`backend/tests/test_web.py`:

```diff
diff --git a/backend/tests/test_web.py b/backend/tests/test_web.py
index 9880e17..4baaa2f 100644
--- a/backend/tests/test_web.py
+++ b/backend/tests/test_web.py
@@ -241,8 +241,11 @@ def test_board_stored_by_an_older_version_gets_current_defaults(env):
     del old["about"]["drift"]
     for i in old["impacts"]:
         del i["cause"], i["landing"]
+    for f in old["flows"]:
+        del f["title"]
     svc.store.put_blob(rid, "board", old)
     b = owner.get(f"/api/reviews/{rid}/board").json()
     assert b["about"]["drift"] == []
     assert all(i["landing"] is False and i["cause"] is None for i in b["impacts"])
     assert len(b["flows"]) == 3
+    assert [f["title"] for f in b["flows"]] == ["affects uart_errors", "-2 ignored", "signature changed"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_board.py tests/test_storyboard.py tests/test_web.py -q`
Expected: FAIL — `5 failed, 54 passed` (`AttributeError: 'Flow' object has no attribute 'title'`, `ImportError: cannot import name 'flow_title'`, `KeyError: 'title'`)

- [ ] **Step 3: Implement**

`backend/codetortoise/board.py`:

```diff
diff --git a/backend/codetortoise/board.py b/backend/codetortoise/board.py
index 696d4f6..e47e19c 100644
--- a/backend/codetortoise/board.py
+++ b/backend/codetortoise/board.py
@@ -14,7 +14,7 @@ from collections.abc import Callable
 from dataclasses import dataclass
 from typing import Literal
 
-from pydantic import BaseModel, Field
+from pydantic import BaseModel, Field, model_validator
 
 from codetortoise.config import AnalysisConfig
 from codetortoise.detectors.base import SEVERITY_RANK, Finding
@@ -89,11 +89,20 @@ class Flow(BaseModel):
     severity: str
     findings: list[str] = Field(default_factory=list)
     text: str
+    title: str = ""                  # short headline for the phone flow reader (spec §13.6)
     what: str
     effect: str
     check: str
     what_source: Literal["template", "llm"] = "template"
 
+    @model_validator(mode="after")
+    def _title_from_text(self) -> Flow:
+        """Boards stored before titles existed: the effect after "⟶", else what the flow ends on."""
+        if not self.title:
+            head, _, tail = self.text.partition("⟶")
+            self.title = tail.strip() or f"affects {head.split(' → ')[-1].strip()}"
+        return self
+
 
 class BoardLayer(BaseModel):
     level: int
@@ -374,6 +383,17 @@ def _entry_path(x: _Ctx, start: str, warn: dict[str, int], avoid: frozenset[str]
     return [start]
 
 
+def flow_title(kind: str, landing: str, changed: str, field: str | None = None, values: str | None = None) -> str:
+    """Short headline of a flow (spec §13.6)."""
+    if kind == "state":
+        return f"{landing} sees a new writer of {field or 'a field'}"
+    if kind == "ignored":
+        return f"{landing} ignores {values}"
+    if kind == "unhandled":
+        return f"{landing} doesn't handle {values}"
+    return f"{landing} calls {changed} (signature changed)"
+
+
 def build_flows(x: _Ctx, impacts: list[Impact]) -> list[Flow]:
     sev_of = {f.id: f.severity for f in x.c.findings}
     warn: dict[str, int] = defaultdict(int)
@@ -399,6 +419,7 @@ def build_flows(x: _Ctx, impacts: list[Impact]) -> list[Flow]:
             what = f"{lead} {fl}. {L} ({layer_name}) uses that field, so it now observes values written by {F}."
             effect = f"{L} now sees {fl} changed by {F}; code that assumed the old writers may be surprised."
             check = f"whether {L} assumes {fl} only changes the way it did before"
+            title = flow_title("state", L, F, field=fl)
             tag, fx_at = "state", None
         else:
             head = _entry_path(x, land, warn)
@@ -409,23 +430,27 @@ def build_flows(x: _Ctx, impacts: list[Impact]) -> list[Flow]:
                 effect = f"Arguments {L} passes to {F} are converted to the new parameter types."
                 check = f"arguments {L} passes that could change meaning under the new types"
                 tail = "signature changed"
+                title = flow_title("signature", L, F)
             elif imp.text.startswith("result ignored"):
                 vals = imp.text.split("can now return ", 1)[-1]
                 what = f"{who} calls {F} and ignores the result. {F} can now return {vals}."
                 effect = f"{L} silently drops the new {vals} result."
                 check = f"whether {L} can hit the new {vals} path, and what it should do then"
                 tail = f"{vals} ignored"
+                title = flow_title("ignored", L, F, values=vals)
             else:
                 vals = imp.text.split("does not handle ", 1)[-1]
                 what = f"{who} calls {F} and {imp.text}."
                 effect = f"{L} does not handle {vals}."
                 check = f"how {L} should treat {vals}"
                 tail = f"{vals} unhandled"
+                title = flow_title("unhandled", L, F, values=vals)
             text = " → ".join(x.label(n) for n in path) + f" ⟶ {tail}"
             tag, fx_at = "contract", land
         sev = sev_of.get(imp.finding or "", "medium")
         flows.append(Flow(id="", path=path, tag=tag, lands=land, fx_at=fx_at, severity=sev,
-                          findings=[imp.finding] if imp.finding else [], text=text, what=what, effect=effect, check=check))
+                          findings=[imp.finding] if imp.finding else [], text=text, title=title, what=what, effect=effect,
+                          check=check))
     flows.sort(key=lambda f: (-SEVERITY_RANK.get(f.severity, 0), 0 if f.tag == "state" else 1, len(f.path), f.text))
     flows = flows[: x.c.cfg.max_flows]
     for i, f in enumerate(flows):
```

`backend/codetortoise/llm/storyboard.py`:

```diff
diff --git a/backend/codetortoise/llm/storyboard.py b/backend/codetortoise/llm/storyboard.py
index 8c06edd..b606df7 100644
--- a/backend/codetortoise/llm/storyboard.py
+++ b/backend/codetortoise/llm/storyboard.py
@@ -67,6 +67,7 @@ class _SummaryOut(BaseModel):
 
 class _FlowOut(BaseModel):
     what: str
+    title: str = ""
     cites: list[str] = Field(default_factory=list)
 
 
@@ -171,7 +172,8 @@ def _flow_prompt(fl: Flow, impact: ImpactModel, findings: list[Finding], snippet
              "GRAPH FACTS:\n" + _facts_for_nodes(impact, [n for n in fl.path if n in impact.nodes])]
     parts += [f"CODE {n}:\n{snippets[n]}" for n in fl.path if n in snippets]
     return ("Describe this call flow for a reviewer in 2-3 sentences: how the entry reaches the change and what the "
-            "change does to the function where the effect lands. Cite the node and finding ids you rely on.\n\n" +
+            "change does to the function where the effect lands, plus a headline of at most 8 words (title). "
+            f"Draft headline: {fl.title}. Cite the node and finding ids you rely on.\n\n" +
             budget(parts, per_call))
 
 
@@ -222,6 +224,8 @@ def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: Layer
             # grounded: keep the LLM text only if it cites a node on this flow or one of its findings
             if out.what.strip() and set(out.cites) & (set(fl.path) | set(fl.findings)):
                 fl.what, fl.what_source = out.what.strip(), "llm"
+                if 0 < len(out.title.strip()) <= 80:
+                    fl.title = out.title.strip()
         jobs.append((_flow_prompt(fl, impact, findings, snippets, per_call), _FlowOut, describe))
 
     pool = ThreadPoolExecutor(max(1, concurrency), thread_name_prefix="tortoise-llm")
```

`docs/superpowers/specs/2026-10-01-review-board-design.md`:

```diff
diff --git a/docs/superpowers/specs/2026-10-01-review-board-design.md b/docs/superpowers/specs/2026-10-01-review-board-design.md
index 9673034..149c8b9 100644
--- a/docs/superpowers/specs/2026-10-01-review-board-design.md
+++ b/docs/superpowers/specs/2026-10-01-review-board-design.md
@@ -409,7 +409,8 @@ changes.
 - signature: "<landing> calls <changed> (signature changed)".
 
 The LLM may rewrite it along with `what` (grounded the same way). Boards stored before this change get the title
-from their `text` (the part before "⟶", else the last step) when `/board` re-validates them.
+from their `text` when `/board` re-validates them: the effect after "⟶" ("-2 ignored"), else
+"affects <last step>".
 
 ### 13.7 Files with side effects (change panel, all sizes)
 
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_board.py tests/test_storyboard.py tests/test_web.py -q`
Expected: `59 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `198 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/board.py backend/codetortoise/llm/storyboard.py docs/superpowers/specs/2026-10-01-review-board-design.md backend/tests/test_board.py backend/tests/test_storyboard.py backend/tests/test_web.py
git commit -m "feat(board): short flow titles for the phone flow reader"
```

---

### Task 2: Flow step list (pure)

The flow reader lists a flow's nodes as steps with a marker and a one-line reason (spec §13.3): `!` and the landing
annotation for where the effect lands (`lands` or `fx_at`, even mid-path), `Δ <kind> +a −r` for changed nodes, `f` and
the declaration note for fields, `entry · <layer>` for the first step, otherwise `calls <next>` plus that step's own
annotation. Ids missing from the board are skipped. `phone/fixture.ts` is a hand-built board shaped like the uart
fixture review, shared by the phone unit tests. `BoardFlow` gains `title`.

**Files:**
- Modify: `frontend/src/board/types.ts`
- Create: `frontend/src/board/phone/flowSteps.ts`
- Test: `frontend/src/board/phone/fixture.ts`
- Test: `frontend/src/board/phone/flowSteps.test.ts`

**Interfaces:**
- Consumes: `Flow.title` (Task 1) through `BoardFlow.title` in `types.ts`.
- Produces: `phone/flowSteps.ts`: `type StepKind = "plain"|"chg"|"field"|"landing"`, `interface Step {id, label, kind,
  marker, reason, hasCode, node}`, `flowSteps(board, flow): Step[]`; `phone/fixture.ts`: `BOARD`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/board/phone/fixture.ts`:

```ts
/** A hand-built board shaped like the uart fixture review (CLs 101+102), for phone unit tests. */
import type { Annotation, Board, BoardNode } from "../types";

const n = (id: string, label: string, layer: number, extra: Partial<BoardNode> = {}): BoardNode => ({
  id, key: id, label, kind: "function", layer, path: "//fixture/x.c", local: "/w/x.c", range: [1, 5], change: null, x: 0, warn: 0,
  ...extra,
});
const ann = (node: string, path: string, line: number, severity: Annotation["severity"], text: string, landing = false): Annotation => ({
  node, path, line, side: "new", severity, channel: "state", title: "State", text, finding: "F1", cause: "N9", landing,
});

export const BOARD: Board = {
  nodes: [
    n("N6", "main", 4, { path: "//fixture/app/main.c" }),
    n("N5", "logger_write", 3, { path: "//fixture/service/logger.c", range: [10, 17] }),
    n("N3", "logger_flush", 3, { path: "//fixture/service/logger.c", range: [19, 22] }),
    n("N9", "uart_send", 2, { path: "//fixture/driver/uart.c", range: [11, 25], change: { kind: "modified", add: 9, rem: 1 } }),
    n("N16", "Uart::errors", 2, { kind: "field", path: "//fixture/driver/uart.h", range: [15, 15] }),
    n("N7", "uart_errors", 2, { path: "//fixture/driver/uart.c", range: [27, 30] }),
    n("N8", "uart_init", 2, { path: "//fixture/driver/uart.c", range: [3, 9] }),
    n("N2", "hal_write", 1, { path: "//fixture/hal/regs.c", change: { kind: "signature", add: 1, rem: 1 } }),
    n("N1", "hal_read", 1, { path: null, range: null }),
  ],
  edges: [],
  flows: [
    { id: "FL1", path: ["N6", "N5", "N9", "N16", "N7"], tag: "state", lands: "N7", fx_at: null, severity: "high", findings: ["F1"],
      text: "main → logger_write → uart_send → Uart::errors → uart_errors", title: "uart_errors sees a new writer of Uart::errors",
      what: "main reaches uart_send…", effect: "uart_errors now sees…", check: "whether…", what_source: "template" },
    { id: "FL2", path: ["N6", "N3", "N9"], tag: "contract", lands: "N3", fx_at: "N3", severity: "medium", findings: ["F5"],
      text: "main → logger_flush → uart_send ⟶ -2 ignored", title: "logger_flush ignores -2",
      what: "…", effect: "logger_flush silently drops the new -2 result.", check: "…", what_source: "template" },
  ],
  impacts: [
    ann("N9", "//fixture/driver/uart.c", 17, "warn", "writes Uart::errors through alias `err`"),
    ann("N5", "//fixture/service/logger.c", 12, "ok", "checks != 0 — covers -2"),
    ann("N3", "//fixture/service/logger.c", 21, "warn", "result ignored — uart_send can now return -2", true),
    ann("N7", "//fixture/driver/uart.c", 29, "warn", "reads Uart::errors — now also written by uart_send (line 17)", true),
    ann("N8", "//fixture/driver/uart.c", 7, "warn", "writes Uart::errors — now also written by uart_send (line 17)"),
    ann("N8", "//fixture/driver/uart.c", 8, "warn", "calls hal_write, whose signature changed"),
    ann("N16", "//fixture/driver/uart.h", 15, "warn", "new writer: uart_send · readers: uart_errors"),
  ],
  layers: [{ level: 4, name: "app" }, { level: 3, name: "service" }, { level: 2, name: "driver" }, { level: 1, name: "hal" }],
  about: { intent: "", intent_source: "template", why: [], cls: [],
           tree: [{ dir: "driver", files: [{ path: "//fixture/driver/uart.c", name: "uart.c", action: "edit", cls: [101], add: 9, rem: 1 },
                                          { path: "//fixture/driver/uart.h", name: "uart.h", action: "edit", cls: [102], add: 1, rem: 0 }] },
                  { dir: "hal", files: [{ path: "//fixture/hal/regs.c", name: "regs.c", action: "edit", cls: [102], add: 1, rem: 1 }] }],
           drift: [] },
  hidden_nodes: 0,
};
```

`frontend/src/board/phone/flowSteps.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { BOARD } from "./fixture";
import { flowSteps } from "./flowSteps";

const view = (i: number) => flowSteps(BOARD, BOARD.flows[i]).map((s) => [s.label, s.kind, s.marker, s.reason, s.hasCode]);

describe("flow steps", () => {
  it("lists a state flow from entry to landing with a reason per step", () => {
    expect(view(0)).toEqual([
      ["main", "plain", "1", "entry · app", true],
      ["logger_write", "plain", "2", "calls uart_send · checks != 0 — covers -2", true],
      ["uart_send", "chg", "Δ", "Δ modified +9 −1", true],
      ["Uart::errors", "field", "f", "field · new writer: uart_send · readers: uart_errors", true],
      ["uart_errors", "landing", "!", "reads Uart::errors — now also written by uart_send (line 17)", true],
    ]);
  });

  it("marks the landing of a contract flow even when it is not the last step", () => {
    expect(view(1)).toEqual([
      ["main", "plain", "1", "entry · app", true],
      ["logger_flush", "landing", "!", "result ignored — uart_send can now return -2", true],
      ["uart_send", "chg", "Δ", "Δ modified +9 −1", true],
    ]);
  });

  it("falls back to the flow's effect, and skips ids missing from the board", () => {
    const flow = { ...BOARD.flows[1], path: ["N6", "N404", "N1"], lands: "N1", fx_at: "N1" };
    expect(flowSteps(BOARD, flow).map((s) => [s.label, s.kind, s.reason, s.hasCode])).toEqual([
      ["main", "plain", "entry · app", true],
      ["hal_read", "landing", "logger_flush silently drops the new -2 result.", false],
    ]);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/board/phone`
Expected: FAIL — `Error: Cannot find module './flowSteps'`

- [ ] **Step 3: Implement**

`frontend/src/board/types.ts`:

```diff
diff --git a/frontend/src/board/types.ts b/frontend/src/board/types.ts
index 9c3c879..0ffbb35 100644
--- a/frontend/src/board/types.ts
+++ b/frontend/src/board/types.ts
@@ -14,7 +14,8 @@ export interface Annotation {
 }
 export interface BoardFlow {
   id: string; path: string[]; tag: "state" | "contract"; lands: string; fx_at: string | null; severity: string;
-  findings: string[]; text: string; what: string; effect: string; check: string; what_source: "template" | "llm";
+  findings: string[]; text: string; title: string; what: string; effect: string; check: string;
+  what_source: "template" | "llm";
 }
 export interface AboutFile { path: string; name: string; action: string; cls: number[]; add: number; rem: number }
 export interface About {
```

`frontend/src/board/phone/flowSteps.ts`:

```ts
/** The phone flow reader's step list (spec §13.3): one entry per node on the flow, with a marker and a one-line reason. */
import type { Board, BoardFlow, BoardNode } from "../types";

export type StepKind = "plain" | "chg" | "field" | "landing";
export interface Step { id: string; label: string; kind: StepKind; marker: string; reason: string; hasCode: boolean; node: BoardNode }

export function flowSteps(board: Board, flow: BoardFlow): Step[] {
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const layerName = (n: BoardNode) => board.layers.find((l) => l.level === n.layer)?.name ?? "unlayered";
  const firstAnn = (id: string, landing = false) => board.impacts.find((a) => a.node === id && (!landing || a.landing));
  const nodes = flow.path.map((id) => byId.get(id)).filter((n): n is BoardNode => !!n);
  return nodes.map((n, i) => {
    const base = { id: n.id, label: n.label, hasCode: !!(n.path && n.range), node: n };
    if (n.id === flow.lands || n.id === flow.fx_at)
      return { ...base, kind: "landing", marker: "!", reason: firstAnn(n.id, true)?.text ?? flow.effect };
    if (n.change)
      return { ...base, kind: "chg", marker: "Δ", reason: `Δ ${n.change.kind} +${n.change.add} −${n.change.rem}` };
    if (n.kind === "field") {
      const a = firstAnn(n.id);
      return { ...base, kind: "field", marker: "f", reason: a ? `field · ${a.text}` : "field" };
    }
    const next = nodes[i + 1], a = firstAnn(n.id);
    const reason = i === 0 ? `entry · ${layerName(n)}`
      : [next ? `calls ${next.label}` : "", a?.text ?? ""].filter(Boolean).join(" · ");
    return { ...base, kind: "plain", marker: String(i + 1), reason };
  });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/board/phone`
Expected: `Tests  3 passed (3)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  60 passed (60)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/types.ts frontend/src/board/phone/flowSteps.ts frontend/src/board/phone/fixture.ts frontend/src/board/phone/flowSteps.test.ts
git commit -m "feat(board): flow step list for the phone flow reader"
```

---

### Task 3: Files with side effects in the change panel

Spec §13.7: after "Files in this change", list every file holding a function the change did not modify that carries an
annotation — landings and warnings first — grouped by directory under the change tree's prefix. A file can also be in
the change (`driver/uart.c` holds the unchanged `uart_errors` and `uart_init`); it is marked "also changed". Each
function row shows its first annotation and opens the file in the viewer at that line.

**Files:**
- Create: `frontend/src/board/sideEffects.ts`
- Modify: `frontend/src/board/ChangePanel.tsx`
- Modify: `frontend/src/board/Board.tsx`
- Modify: `frontend/src/board/board.css`
- Test: `frontend/src/board/sideEffects.test.ts`
- Modify: `frontend/e2e/board.spec.ts`

**Interfaces:**
- Consumes: `Board`, `Annotation` (`types.ts`), `BOARD` (Task 2).
- Produces: `sideEffects.ts`: `AffectedFn {node, label, line, severity, landing, text}`, `AffectedFile {path, name,
  alsoChanged, warn, fns}`, `AffectedDir {dir, files}`, `sideEffectFiles(board): AffectedDir[]`; `ChangePanel` prop
  `sideEffects: AffectedDir[]` (rows `.fx-file`, `.fx-fn`).

- [ ] **Step 1: Write the failing tests**

`frontend/src/board/sideEffects.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { BOARD } from "./phone/fixture";
import { sideEffectFiles } from "./sideEffects";

describe("files with side effects", () => {
  it("groups affected unchanged functions by directory, marking files that are also changed", () => {
    const dirs = sideEffectFiles(BOARD);
    expect(dirs.map((d) => d.dir)).toEqual(["driver", "service"]);
    const [uart] = dirs[0].files, [logger] = dirs[1].files;
    expect([uart.name, uart.path, uart.alsoChanged, uart.warn]).toEqual(["uart.c", "//fixture/driver/uart.c", true, 3]);
    expect(uart.fns.map((f) => [f.label, f.line, f.severity, f.landing])).toEqual([
      ["uart_init", 7, "warn", false], ["uart_errors", 29, "warn", true]]);
    expect([logger.name, logger.alsoChanged, logger.warn]).toEqual(["logger.c", false, 1]);
    expect(logger.fns.map((f) => [f.label, f.line, f.text])).toEqual([
      ["logger_write", 12, "checks != 0 — covers -2"], ["logger_flush", 21, "result ignored — uart_send can now return -2"]]);
  });

  it("leaves out changed functions, fields and annotations without a path", () => {
    const labels = sideEffectFiles(BOARD).flatMap((d) => d.files.flatMap((f) => f.fns.map((x) => x.label)));
    expect(labels).not.toContain("uart_send");
    expect(labels).not.toContain("Uart::errors");
    const none = { ...BOARD, impacts: BOARD.impacts.map((a) => ({ ...a, path: null })) };
    expect(sideEffectFiles(none)).toEqual([]);
  });
});
```

`frontend/e2e/board.spec.ts`:

```diff
diff --git a/frontend/e2e/board.spec.ts b/frontend/e2e/board.spec.ts
index a90a2fd..f4bbf83 100644
--- a/frontend/e2e/board.spec.ts
+++ b/frontend/e2e/board.spec.ts
@@ -181,3 +181,15 @@ test("change panel opens on the left by default, collapses to a bar, and the flo
   expect((await flowbar.boundingBox())!.height).toBeGreaterThan(h0 + 100);
   await expect(page.locator(".bd-flowbar .bd-chip").first()).toBeVisible();
 });
+
+test("the change panel lists files with side effects and opens them at the affected line", async ({ page }) => {
+  await startReview(page);
+  const panel = page.locator(".bd-about");
+  const fx = panel.locator(".fx-tree");
+  await expect(fx.locator(".fx-file", { hasText: "uart.c" })).toContainText("also changed");
+  await expect(fx.locator(".fx-file", { hasText: "logger.c" })).toBeVisible();
+  await fx.locator(".fx-fn", { hasText: "logger_flush" }).click();
+  const viewer = page.locator(".bd-viewer");
+  await expect(viewer.locator('.fsec[data-path="//fixture/service/logger.c"]')).toBeVisible();
+  await expect(viewer.locator(".bd-ln.focus")).toContainText("uart_send(lg->uart");
+});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/board/sideEffects.test.ts && npm run build && npx playwright test e2e/board.spec.ts -g "side effects"`
Expected: FAIL — `Error: Cannot find module './sideEffects'` (the e2e step does not run yet)

- [ ] **Step 3: Implement**

`frontend/src/board/sideEffects.ts`:

```ts
/** "Files with side effects" (spec §13.7): files holding functions the change did not modify but that carry annotations,
 * grouped by directory under the same prefix as the change tree. */
import type { Annotation, Board } from "./types";

export interface AffectedFn { node: string; label: string; line: number; severity: Annotation["severity"]; landing: boolean; text: string }
export interface AffectedFile { path: string; name: string; alsoChanged: boolean; warn: number; fns: AffectedFn[] }
export interface AffectedDir { dir: string; files: AffectedFile[] }

const RANK = (a: Annotation) => (a.landing ? 0 : a.severity === "warn" ? 1 : a.severity === "info" ? 2 : 3);

export function sideEffectFiles(board: Board): AffectedDir[] {
  const nodes = new Map(board.nodes.map((n) => [n.id, n]));
  const changedFiles = new Set(board.about.tree.flatMap((d) => d.files.map((f) => f.path)));
  const first = board.about.tree[0]?.files[0], firstDir = board.about.tree[0]?.dir;
  const prefix = first ? first.path.slice(0, first.path.length - (firstDir === "." ? first.name : `${firstDir}/${first.name}`).length) : "";
  const byPath = new Map<string, Annotation[]>();
  for (const a of board.impacts) {
    const n = nodes.get(a.node);
    if (!a.path || !n || n.change || n.kind !== "function") continue;
    byPath.set(a.path, [...(byPath.get(a.path) ?? []), a]);
  }
  const files: (AffectedFile & { dir: string; best: number })[] = [...byPath].map(([path, anns]) => {
    const perNode = new Map<string, Annotation>();
    for (const a of [...anns].sort((x, y) => RANK(x) - RANK(y) || x.line - y.line))
      if (!perNode.has(a.node)) perNode.set(a.node, a);
    const rel = prefix && path.startsWith(prefix) ? path.slice(prefix.length) : path;
    const cut = rel.lastIndexOf("/");
    return {
      path, name: rel.slice(cut + 1), dir: cut > 0 ? rel.slice(0, cut) : ".", alsoChanged: changedFiles.has(path),
      warn: anns.filter((a) => a.severity === "warn").length, best: Math.min(...anns.map(RANK)),
      fns: [...perNode.values()].sort((x, y) => x.line - y.line).map((a) => ({
        node: a.node, label: nodes.get(a.node)!.label, line: a.line, severity: a.severity, landing: a.landing, text: a.text })),
    };
  });
  const dirs = new Map<string, AffectedFile[]>();
  for (const f of files.sort((a, b) => a.best - b.best || (a.path < b.path ? -1 : 1))) {
    const { dir, best: _best, ...file } = f;
    dirs.set(dir, [...(dirs.get(dir) ?? []), file]);
  }
  return [...dirs].sort(([a], [b]) => (a < b ? -1 : 1)).map(([dir, fs]) => ({ dir, files: fs }));
}
```

`frontend/src/board/ChangePanel.tsx`:

```diff
diff --git a/frontend/src/board/ChangePanel.tsx b/frontend/src/board/ChangePanel.tsx
index a2f2a8d..06cdfd5 100644
--- a/frontend/src/board/ChangePanel.tsx
+++ b/frontend/src/board/ChangePanel.tsx
@@ -2,6 +2,7 @@ import { useState } from "react";
 import type { Comment } from "../api";
 import Comments from "../components/Comments";
 import type { Action } from "./reducer";
+import type { AffectedDir } from "./sideEffects";
 import Resizer from "./Resizer";
 import type { About } from "./types";
 
@@ -13,6 +14,7 @@ interface Props {
   onComments: () => void;
   layers: { level: number; name: string }[];
   about: About;
+  sideEffects: AffectedDir[];
   risk: string | null;
   openFiles: string[];
   dispatch: (a: Action) => void;
@@ -23,8 +25,8 @@ interface Props {
 }
 
 /** "What's this change?" (spec §3.6): files tree first, then intent, why it's risky, changelists. Pushes the board. */
-export default function ChangePanel({ open, onToggle, reviewId, comments, onComments, layers, about, risk, openFiles, dispatch, wide,
-  width, onWidth, onWidthDone }: Props) {
+export default function ChangePanel({ open, onToggle, reviewId, comments, onComments, layers, about, sideEffects, risk, openFiles,
+  dispatch, wide, width, onWidth, onWidthDone }: Props) {
   const [shut, setShut] = useState<Set<string>>(new Set());
   if (!open)
     return (
@@ -70,6 +72,31 @@ export default function ChangePanel({ open, onToggle, reviewId, comments, onComm
             </div>
           ))}
         </div>
+        {sideEffects.length > 0 && <>
+          <h3>Files with side effects</h3>
+          <div className="tree fx-tree">
+            {sideEffects.map((d) => (
+              <div key={d.dir}>
+                <div className="dir"><span className="caret">▾</span>📁 {d.dir}/</div>
+                {d.files.map((f) => (
+                  <div key={f.path}>
+                    <div className={`file fx-file${openFiles.includes(f.path) ? " on" : ""}`}
+                         onClick={() => dispatch({ t: "viewer.open", path: f.path, line: f.fns[0]?.line ?? null, wide })}>
+                      📄 {f.name}{f.alsoChanged && <span className="act">also changed</span>}
+                      {f.warn > 0 && <span className="cnt"><span className="m">⚠ {f.warn}</span></span>}
+                    </div>
+                    {f.fns.map((fn) => (
+                      <div key={fn.node} className={`fx-fn ${fn.landing ? "landing" : fn.severity}`} title={fn.text}
+                           onClick={() => dispatch({ t: "viewer.open", path: f.path, line: fn.line, wide })}>
+                        <b>{fn.label}</b> · {fn.text} <span className="ln">(line {fn.line})</span>
+                      </div>
+                    ))}
+                  </div>
+                ))}
+              </div>
+            ))}
+          </div>
+        </>}
         <h3>Intent</h3>
         <div className="intent">{about.intent}</div>
         {about.why.length > 0 && <>
```

`frontend/src/board/Board.tsx`:

```diff
diff --git a/frontend/src/board/Board.tsx b/frontend/src/board/Board.tsx
index 832dd04..1522529 100644
--- a/frontend/src/board/Board.tsx
+++ b/frontend/src/board/Board.tsx
@@ -7,6 +7,7 @@ import ChangePanel from "./ChangePanel";
 import FileViewer from "./FileViewer";
 import FlowBar from "./FlowBar";
 import { bandsFor, centrePan, preferDepth, worldNodes } from "./layout";
+import { sideEffectFiles } from "./sideEffects";
 import { makeLens, type Viewport } from "./lens";
 import { keys, loadAboutOpen, loadLayout, loadLens, loadMovedAll, loadSize, loadWidth, save } from "./prefs";
 import { type Action, initialState, reduce } from "./reducer";
@@ -51,6 +52,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   useEffect(() => { const t = window.setTimeout(() => setHint(false), 7000); return () => window.clearTimeout(t); }, []);
   const interact = useCallback(() => setHint(false), []);
 
+  const sideEffects = useMemo(() => sideEffectFiles(board), [board]);
   const bands = useMemo(() => bandsFor(board, state.layout), [board, state.layout]);
   const world = useMemo(() => worldNodes(board, state.layout, state.moved[state.layout]), [board, state.layout, state.moved]);
   const lens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
@@ -151,7 +153,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
                height={flowH} onHeight={setFlowH} onHeightDone={(h) => { setFlowH(h); save(keys.flowH, h); }} />
       <div className={`bd-main${state.about ? " with-about" : ""}`}>
         <ChangePanel open={state.about} onToggle={toggleAbout} reviewId={reviewId} comments={comments} onComments={onComments}
-                     layers={board.layers} about={board.about} risk={risk} openFiles={state.viewer.files} dispatch={act}
+                     layers={board.layers} about={board.about} sideEffects={sideEffects} risk={risk} openFiles={state.viewer.files} dispatch={act}
                      wide={wideScreen()} width={aboutW} onWidth={setAboutW} onWidthDone={(w) => save(keys.aboutW, w)} />
         <div className="bd-stage" ref={stage}>
           {vp.W > 0 && <>
```

`frontend/src/board/board.css`:

```diff
diff --git a/frontend/src/board/board.css b/frontend/src/board/board.css
index e4adbe5..b6d2496 100644
--- a/frontend/src/board/board.css
+++ b/frontend/src/board/board.css
@@ -292,6 +292,11 @@ body.bd-resizing-v, body.bd-resizing-v * { cursor: row-resize !important; user-s
 .bd-about .tree .act { font: 700 9.5px var(--bd-sans); text-transform: uppercase; padding: 1px 6px; border-radius: 5px; background: var(--chg-bg-soft); color: var(--chg-ink); }
 .bd-about .tree .cnt { margin-left: auto; font-size: 11px; } .bd-about .tree .cnt .p { color: var(--add-ink); }
 .bd-about .tree .cnt .m { color: var(--del-ink); margin-left: 4px; }
+.bd-about .fx-fn { padding: 3px 12px 3px 52px; font: 12px var(--bd-sans); color: var(--bd-muted); cursor: pointer; overflow: hidden;
+  text-overflow: ellipsis; white-space: nowrap; border-left: 3px solid transparent; }
+.bd-about .fx-fn b { font: 600 12px var(--bd-mono); color: var(--bd-ink); }
+.bd-about .fx-fn.landing { border-left-color: var(--fx); } .bd-about .fx-fn.warn { border-left-color: var(--warn); }
+.bd-about .fx-fn:hover { background: var(--bd-hover); } .bd-about .fx-fn .ln { color: var(--bd-faint); }
 .bd-about .tree .clb { font: 600 10px var(--bd-sans); color: var(--flow); background: var(--bd-sel); padding: 1px 6px; border-radius: 5px; }
 
 @media (max-width: 1100px) {
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/board/sideEffects.test.ts && npm run build && npx playwright test e2e/board.spec.ts -g "side effects"`
Expected: `Tests  2 passed (2)` and `✓ built in …` and `1 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  62 passed (62)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/sideEffects.ts frontend/src/board/ChangePanel.tsx frontend/src/board/Board.tsx frontend/src/board/board.css frontend/src/board/sideEffects.test.ts frontend/e2e/board.spec.ts
git commit -m "feat(board): files with side effects in the change panel"
```

---

### Task 4: Phone zoom maths and the remembered tab

The phone Map zooms with a scale z ∈ [0.5, 2.5] applied after the lens, about the canvas centre (spec §13.4). During a
pinch the world point that was under the fingers when it started stays under their midpoint — so two fingers also
pan. The lens is non-linear near the rims, so the pan is solved through the real projection: screen x only grows with
panX (bisection), and with x fixed, y is linear in panY. The phone shell remembers its tab per review.

**Files:**
- Create: `frontend/src/board/zoom.ts`
- Modify: `frontend/src/board/prefs.ts`
- Test: `frontend/src/board/zoom.test.ts`
- Modify: `frontend/src/board/prefs.test.ts`

**Interfaces:**
- Consumes: `makeLens`, `Lens`, `View`, `Viewport` (`lens.ts`).
- Produces: `zoom.ts`: `ZOOM_MIN`, `ZOOM_MAX`, `zoomLens(lens, z, vp): Lens`, `pinchZoom(z0, d0, d1): number`,
  `pinchView(view, z1, anchor, mid, vp, worldXs): View`; `prefs.ts`: `type PhoneTab`, `keys.tab(id)`, `loadTab(id)`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/board/zoom.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { makeLens } from "./lens";
import { pinchZoom, zoomLens } from "./zoom";

const vp = { W: 400, H: 700 };
const lens = makeLens({ panX: 200, panY: 0, lens: 0 }, vp, [-500, 500]);

describe("phone zoom", () => {
  it("scales about the canvas centre and inverts", () => {
    const z = zoomLens(lens, 2, vp);
    expect(z.project(0, 350)).toMatchObject({ x: 200, y: 350 });          // the centre stays put
    expect(z.project(50, 400)).toMatchObject({ x: 300, y: 450 });
    expect(z.project(50, 400).s).toBe(2);
    expect(z.unprojectX(300)).toBeCloseTo(50, 3);
    expect(z.unprojectY(300, 450)).toBeCloseTo(400, 3);
    expect(zoomLens(lens, 1, vp)).toBe(lens);
  });

  it("scales by the finger spread, clamped", () => {
    expect(pinchZoom(1, 100, 200)).toBe(2);
    expect(pinchZoom(2, 100, 1000)).toBe(2.5);
    expect(pinchZoom(1, 100, 10)).toBe(0.5);
  });
});

describe("pinch keeps the point under the fingers", () => {
  it("in the lens's folded rim too", async () => {
    const { pinchView } = await import("./zoom");
    const xs = [-1500, -600, 0, 600, 1500];
    for (const mid of [{ x: 200, y: 350 }, { x: 40, y: 600 }, { x: 370, y: 90 }]) {
      const view = { panX: 120, panY: -40, lens: 2 as const };
      const before = zoomLens(makeLens(view, vp, xs), 1, vp);
      const wx = before.unprojectX(mid.x), wy = before.unprojectY(mid.x, mid.y);
      const next = pinchView(view, 1.8, { x: wx, y: wy }, mid, vp, xs);
      const after = zoomLens(makeLens(next, vp, xs), 1.8, vp).project(wx, wy);
      expect(Math.abs(after.x - mid.x)).toBeLessThan(1);
      expect(Math.abs(after.y - mid.y)).toBeLessThan(1);
    }
  });

  it("follows the fingers when they move together (two-finger pan)", async () => {
    const { pinchView } = await import("./zoom");
    const xs = [-1500, 0, 1500], view = { panX: 200, panY: 0, lens: 2 as const };
    const next = pinchView(view, 1.5, { x: 0, y: 350 }, { x: 260, y: 380 }, vp, xs);
    const p = zoomLens(makeLens(next, vp, xs), 1.5, vp).project(0, 350);
    expect([Math.round(p.x), Math.round(p.y)]).toEqual([260, 380]);
  });
});
```

`frontend/src/board/prefs.test.ts`:

```diff
diff --git a/frontend/src/board/prefs.test.ts b/frontend/src/board/prefs.test.ts
index 97e0a0f..c20fa26 100644
--- a/frontend/src/board/prefs.test.ts
+++ b/frontend/src/board/prefs.test.ts
@@ -77,3 +77,12 @@ describe("panel prefs", () => {
     expect(loadSize(keys.flowH, 40, 4000)).toBeNull();
   });
 });
+
+describe("phone tab pref", () => {
+  it("remembers the tab per review and ignores junk", async () => {
+    const { loadTab } = await import("./prefs");
+    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => (k === "ct.board.3.tab" ? '"map"' : '"other"'), setItem: () => {} } });
+    expect(loadTab(3)).toBe("map");
+    expect(loadTab(4)).toBeNull();
+  });
+});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/board/zoom.test.ts src/board/prefs.test.ts`
Expected: FAIL — `Error: Cannot find module './zoom'` and `TypeError: loadTab is not a function`

- [ ] **Step 3: Implement**

`frontend/src/board/zoom.ts`:

```ts
/** Phone-only zoom (spec §13.4): a scale z applied after the lens, about the canvas centre. */
import { type Lens, makeLens, type View, type Viewport } from "./lens";

export const ZOOM_MIN = 0.5, ZOOM_MAX = 2.5;

/** The lens seen through zoom z: screen = centre + (lensed − centre) · z. Node scale grows with z. */
export function zoomLens(lens: Lens, z: number, vp: Viewport): Lens {
  if (z === 1) return lens;
  const cx = vp.W / 2, cy = vp.H / 2;
  const back = (sx: number) => cx + (sx - cx) / z;
  return {
    project(wx, wy) {
      const p = lens.project(wx, wy);
      return { x: cx + (p.x - cx) * z, y: cy + (p.y - cy) * z, v: p.v, s: p.s * z };
    },
    bandY: (sx, wy) => cy + (lens.bandY(back(sx), wy) - cy) * z,
    unprojectX: (sx) => lens.unprojectX(back(sx)),
    unprojectY: (sx, sy) => lens.unprojectY(back(sx), cy + (sy - cy) / z),
  };
}

/** The zoom after one pinch update: fingers d0 → d1 apart, clamped to [ZOOM_MIN, ZOOM_MAX]. */
export const pinchZoom = (z0: number, d0: number, d1: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z0 * (d1 / Math.max(1, d0))));

/** The pan that puts world point `anchor` (taken under the fingers when the pinch started) under the current pinch
 * midpoint at zoom z1. The lens is non-linear away from the centre, so solve through the real projection: screen x only
 * grows with panX (bisection), and once x is fixed, screen y is linear in panY (one exact step). */
export function pinchView(view: View, z1: number, anchor: { x: number; y: number }, mid: { x: number; y: number }, vp: Viewport,
                          worldXs: number[]): View {
  const at = (v: View) => zoomLens(makeLens(v, vp, worldXs), z1, vp).project(anchor.x, anchor.y);
  let lo = view.panX - 20000, hi = view.panX + 20000;
  for (let i = 0; i < 60; i++) {
    const m = (lo + hi) / 2;
    if (at({ ...view, panX: m }).x < mid.x) lo = m; else hi = m;
  }
  const v = { ...view, panX: (lo + hi) / 2 };
  const y0 = at(v).y, y1 = at({ ...v, panY: v.panY + 1 }).y;
  return Math.abs(y1 - y0) > 1e-6 ? { ...v, panY: v.panY + (mid.y - y0) / (y1 - y0) } : v;
}
```

`frontend/src/board/prefs.ts`:

```diff
diff --git a/frontend/src/board/prefs.ts b/frontend/src/board/prefs.ts
index bf60061..6a09b87 100644
--- a/frontend/src/board/prefs.ts
+++ b/frontend/src/board/prefs.ts
@@ -21,6 +21,7 @@ export const keys = {
   layout: (reviewId: number) => `ct.board.${reviewId}.layout`,
   about: "ct.panel.about",
   flowH: "ct.panel.flowH",
+  tab: (reviewId: number) => `ct.board.${reviewId}.tab`,
   viewerW: "ct.panel.viewerW",
   aboutW: "ct.panel.aboutW",
   lens: "ct.lens",
@@ -73,3 +74,9 @@ export function loadSize(key: string, min: number, max: number): number | null {
   const v = load<unknown>(key, null);
   return typeof v === "number" && Number.isFinite(v) && v >= min && v <= max ? v : null;
 }
+
+export type PhoneTab = "flows" | "map" | "files" | "summary";
+export function loadTab(reviewId: number): PhoneTab | null {
+  const v = load<unknown>(keys.tab(reviewId), null);
+  return v === "flows" || v === "map" || v === "files" || v === "summary" ? v : null;
+}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/board/zoom.test.ts src/board/prefs.test.ts`
Expected: `Tests  11 passed (11)`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  67 passed (67)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/zoom.ts frontend/src/board/prefs.ts frontend/src/board/zoom.test.ts frontend/src/board/prefs.test.ts
git commit -m "feat(board): phone zoom maths and remembered phone tab"
```

---

### Task 5: Fix: the landing page's layout class leaks into the board

The landing page used a global `.landing` class (`display: grid; padding: 0 !important`). The board's flow summary has
a `.landing` box ("Side effect lands on …") and the phone steps and side-effect rows use `landing` as a modifier, so
they picked up the grid. Rename the page class to `.home-page`.

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/pages/Reviews.tsx`
- Modify: `frontend/e2e/board.spec.ts`

**Interfaces:**
- Produces: `.home-page` (landing page root); `.landing` is free for board modifiers.

- [ ] **Step 1: Write the failing test**

`frontend/e2e/board.spec.ts`:

```diff
diff --git a/frontend/e2e/board.spec.ts b/frontend/e2e/board.spec.ts
index f4bbf83..5f84a60 100644
--- a/frontend/e2e/board.spec.ts
+++ b/frontend/e2e/board.spec.ts
@@ -7,6 +7,8 @@ test("flows, cards, comments, viewer, change panel and layout", async ({ page })
   await startReview(page);
   await expect(page.getByRole("tab")).toHaveCount(3);
   await expect(page.locator(".bd-flowinfo .landing")).toContainText("Side effect lands on uart_errors");
+  // the landing page's own classes must not leak into the board (its .landing grid once did)
+  expect(await page.locator(".bd-flowinfo .landing").evaluate((el) => getComputedStyle(el).display)).toBe("block");
 
   // select a flow; its summary names where the effect lands
   await page.getByRole("tab", { name: /logger_flush/ }).click();
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm run build && npx playwright test e2e/board.spec.ts -g "flows, cards"`
Expected: FAIL — `1 failed` — `Expected: "block"`, `Received: "grid"`

- [ ] **Step 3: Implement**

`frontend/src/styles.css`:

```diff
diff --git a/frontend/src/styles.css b/frontend/src/styles.css
index c6b9f09..571a0d6 100644
--- a/frontend/src/styles.css
+++ b/frontend/src/styles.css
@@ -124,7 +124,7 @@ button.go { background: var(--amber); color: #2b1a00; border: 0; border-radius:
 button.go:disabled { opacity: .55; }
 
 /* ---- landing (spec §12) ---- */
-.landing { display: grid; grid-template-columns: minmax(280px, 340px) 1fr; padding: 0 !important; overflow: auto; }
+.home-page { display: grid; grid-template-columns: minmax(280px, 340px) 1fr; padding: 0 !important; overflow: auto; }
 .rv-hello { background: var(--chrome); background-color: #1e2148; color: var(--chrome-ink); padding: 26px 24px; }
 .rv-hello h1 { font-size: 22px; margin: 12px 0 6px; color: var(--chrome-ink); }
 .rv-hello p { color: var(--chrome-muted); margin: 0 0 14px; font-size: 13.5px; }
@@ -196,7 +196,7 @@ button.go:disabled { opacity: .55; }
 .review-body .badge { border: 0; padding: 2px 9px; background: var(--gap-bg); }
 
 @media (max-width: 760px) {
-  .landing { grid-template-columns: 1fr; }
+  .home-page { grid-template-columns: 1fr; }
   .rv-main { padding: 16px; }
   .rv-row .when { width: 100%; }
   .rv-hello { padding: 18px 16px; } .rv-hello > form > svg:first-child, .rv-hello > svg:first-child { display: none; }
```

`frontend/src/pages/Reviews.tsx`:

```diff
diff --git a/frontend/src/pages/Reviews.tsx b/frontend/src/pages/Reviews.tsx
index 1984dfc..684e352 100644
--- a/frontend/src/pages/Reviews.tsx
+++ b/frontend/src/pages/Reviews.tsx
@@ -34,7 +34,7 @@ export default function Reviews() {
   const counts = useMemo(() => chipCounts(rows ?? [], me?.user ?? null), [rows, me]);
 
   return (
-    <main className="landing">
+    <main className="home-page">
       <section className="rv-hello">
         {me?.is_owner ? <StartReview /> : (
           <>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/board.spec.ts -g "flows, cards"`
Expected: `✓ built in …` and `1 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  67 passed (67)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles.css frontend/src/pages/Reviews.tsx frontend/e2e/board.spec.ts
git commit -m "fix(ui): the landing page's layout class no longer leaks into the board's flow summary"
```

---

### Task 6: Phone shell: flow reader, Files and Summary tabs

At ≤ 640 px `Board` renders `PhoneBoard` instead of the desktop layout (spec §13.2–13.5): the review header with a ☰
review menu (the app's top bar is hidden), one tab at a time and a bottom tab bar Flows · Map · Files · Summary (tab per
review, default Flows or Map without flows). Flows is the flow reader (pager with swipe and ‹ ›, steps that expand to
their code via the shared `CardBody`, ⤢ to the file, landing box); opening any file switches to Files (the viewer,
embedded, or a picker of changed and side-effect files); Summary is the change panel, embedded. The canvas stage is now
a callback ref so it can mount with the Map tab. `e2e/mobile.spec.ts` (card sheets, collapsed panel bar on phones) is
replaced by `e2e/phone.spec.ts`.

**Files:**
- Modify: `frontend/src/board/CardLayer.tsx`
- Modify: `frontend/src/board/FileViewer.tsx`
- Modify: `frontend/src/board/ChangePanel.tsx`
- Create: `frontend/src/board/phone/FlowReader.tsx`
- Create: `frontend/src/board/phone/PhoneBoard.tsx`
- Create: `frontend/src/board/phone/phone.css`
- Modify: `frontend/src/board/Board.tsx`
- Modify: `frontend/src/board/board.css`
- Delete: `frontend/e2e/mobile.spec.ts`
- Modify: `frontend/e2e/helpers.ts`
- Test: `frontend/e2e/phone.spec.ts`

**Interfaces:**
- Consumes: `flowSteps` (Task 2), `sideEffectFiles` (Task 3), `loadTab`/`keys.tab` (Task 4).
- Produces: `phone/PhoneBoard.tsx` (props `reviewId, board, state, act, sources, comments, onComments, risk, sideEffects,
  head, onOpenFile, map`), `phone/FlowReader.tsx`, `phone/phone.css`; `CardBody` exported from `CardLayer.tsx`;
  `embedded` prop on `FileViewer` and `ChangePanel`.

- [ ] **Step 1: Write the failing tests**

`frontend/e2e/helpers.ts`:

```diff
diff --git a/frontend/e2e/helpers.ts b/frontend/e2e/helpers.ts
index 1e3a4a4..5a80d18 100644
--- a/frontend/e2e/helpers.ts
+++ b/frontend/e2e/helpers.ts
@@ -12,5 +12,6 @@ export async function startReview(page: Page) {
   await login(page);
   await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
   await page.getByRole("button", { name: "Start review" }).click();
-  await expect(page.locator(".bd-node").first()).toBeVisible({ timeout: 60_000 });
+  // desktop shows the canvas; phones open on the flow reader (spec §13)
+  await expect(page.locator(".bd-node, .ph-step").first()).toBeVisible({ timeout: 60_000 });
 }
```

`frontend/e2e/phone.spec.ts`:

```ts
import { devices, expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
  deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

const tab = (page: Page, name: string) => page.locator(".ph-tabs").getByRole("tab", { name });

test("phone board: flow reader, files and summary tabs", async ({ page }) => {
  await startReview(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  await expect(page.locator(".topbar")).toBeHidden();                               // the review header is the only bar
  await expect(tab(page, "Flows")).toHaveAttribute("aria-selected", "true");

  // the first flow, as steps from entry to landing
  await expect(page.locator(".ph-title")).toHaveText("uart_errors sees a new writer of Uart::errors");
  await expect(page.locator(".ph-count")).toHaveText("1/3");
  const steps = page.locator(".ph-step");
  await expect(steps).toHaveCount(5);
  await expect(steps.nth(2)).toContainText("uart_send");
  await expect(steps.last()).toHaveClass(/\blanding\b/);
  await expect(page.locator(".ph-landing")).toContainText("Side effect lands on uart_errors");

  // swipe to the next flow, button back
  const box = (await page.locator(".ph-reader").boundingBox())!;
  await page.mouse.move(box.x + box.width - 30, box.y + 120);
  await page.mouse.down();
  await page.mouse.move(box.x + 40, box.y + 130, { steps: 6 });
  await page.mouse.up();
  await expect(page.locator(".ph-count")).toHaveText("2/3");
  await expect(page.locator(".ph-title")).toHaveText("logger_flush ignores -2");
  await page.getByRole("button", { name: "Previous flow" }).click();
  await expect(page.locator(".ph-count")).toHaveText("1/3");

  // a step expands to its code with annotations
  await steps.nth(2).locator(".ph-head").click();
  await expect(page.locator(".ph-step.open .bd-ann").first()).toContainText("writes Uart::errors through alias");

  // ⤢ opens the whole file in the Files tab at the function
  await page.locator(".ph-step.open").getByRole("button", { name: "Open uart_send in Files" }).click();
  await expect(tab(page, "Files")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator('.bd-viewer .fsec[data-path="//fixture/driver/uart.c"]')).toBeVisible();
  await expect(page.locator(".bd-viewer .bd-ln.focus")).toContainText("int uart_send");
  await page.locator(".bd-viewer").getByRole("button", { name: "Close all" }).click();
  await expect(page.locator(".ph-pick")).toContainText("uart.c");
  await expect(page.locator(".ph-pick")).toContainText("logger.c");                 // files with side effects

  // Summary: the change panel, with side-effect files that open in Files
  await tab(page, "Summary").click();
  const summary = page.locator(".bd-about");
  await expect(summary.getByText("Files with side effects")).toBeVisible();
  await summary.locator(".fx-fn", { hasText: "logger_flush" }).click();
  await expect(tab(page, "Files")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator('.bd-viewer .fsec[data-path="//fixture/service/logger.c"]')).toBeVisible();

  // Map shows the graph; the review menu holds the other pages
  await tab(page, "Map").click();
  await expect(page.locator(".bd-node").first()).toBeVisible();
  await page.getByRole("button", { name: "Review menu" }).click();
  await expect(page.locator(".ph-menu").getByRole("link", { name: /Findings/ })).toBeVisible();
  await expect(page.locator(".ph-menu .theme-switch")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

test("the phone tab is remembered for the review", async ({ page }) => {
  await startReview(page);
  await tab(page, "Summary").click();
  await page.reload();
  await expect(tab(page, "Summary")).toHaveAttribute("aria-selected", "true");
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm run build && npx playwright test e2e/phone.spec.ts`
Expected: FAIL — `2 failed` — the app top bar is still visible and there is no tab bar (the phone still gets the desktop board)

- [ ] **Step 3: Implement**

Remove the old phone spec this task replaces:

```bash
git rm frontend/e2e/mobile.spec.ts
```

`frontend/src/board/CardLayer.tsx`:

```diff
diff --git a/frontend/src/board/CardLayer.tsx b/frontend/src/board/CardLayer.tsx
index 6d721c7..70a47e6 100644
--- a/frontend/src/board/CardLayer.tsx
+++ b/frontend/src/board/CardLayer.tsx
@@ -124,9 +124,10 @@ function Card({ node, rect, at, z, front, register, state, dispatch, narrow, onO
   );
 }
 
-type BodyProps = Pick<Props, "reviewId" | "board" | "sources" | "comments" | "onComments"> & { node: BoardNode };
+export type BodyProps = Pick<Props, "reviewId" | "board" | "sources" | "comments" | "onComments"> & { node: BoardNode };
 
-function CardBody({ node, reviewId, board, sources, comments, onComments }: BodyProps) {
+/** A function's code with its effects or context line: used by cards, the phone flow reader and the phone map sheet. */
+export function CardBody({ node, reviewId, board, sources, comments, onComments }: BodyProps) {
   const src = useEnsureSource(node.path, sources);
   const [lo, hi] = node.range ?? [0, 0];
   const pad = node.kind === "field" ? 4 : 0;
```

`frontend/src/board/FileViewer.tsx`:

```diff
diff --git a/frontend/src/board/FileViewer.tsx b/frontend/src/board/FileViewer.tsx
index bd2abd0..ff3f9f6 100644
--- a/frontend/src/board/FileViewer.tsx
+++ b/frontend/src/board/FileViewer.tsx
@@ -19,6 +19,8 @@ interface Props {
   width: number;
   onWidth: (w: number) => void;
   onWidthDone: (w: number) => void;
+  /** Phone Files tab: fills its tab, no resize grip. */
+  embedded?: boolean;
 }
 
 /** Stacked, collapsible full files (spec §3.5); newest on top, diff controls only for changed files. */
@@ -41,8 +43,9 @@ export default function FileViewer(p: Props) {
     return () => window.cancelAnimationFrame(id);
   }, [reveal]);
   return (
-    <aside className="bd-viewer" style={{ ["--w" as string]: `${p.width}px` }}>
-      <Resizer size={p.width} edge="left" min={360} max={() => window.innerWidth * 0.75} onSize={p.onWidth} onDone={p.onWidthDone} />
+    <aside className={`bd-viewer${p.embedded ? " embedded" : ""}`} style={{ ["--w" as string]: `${p.width}px` }}>
+      {!p.embedded && <Resizer size={p.width} edge="left" min={360} max={() => window.innerWidth * 0.75} onSize={p.onWidth}
+                               onDone={p.onWidthDone} />}
       <div className="top">
         <b>Files</b><span className="muted">{viewer.files.length} open</span><span className="sp" />
         <span className="bd-seg">
```

`frontend/src/board/ChangePanel.tsx`:

```diff
diff --git a/frontend/src/board/ChangePanel.tsx b/frontend/src/board/ChangePanel.tsx
index 06cdfd5..6052257 100644
--- a/frontend/src/board/ChangePanel.tsx
+++ b/frontend/src/board/ChangePanel.tsx
@@ -22,13 +22,15 @@ interface Props {
   width: number;
   onWidth: (w: number) => void;
   onWidthDone: (w: number) => void;
+  /** Phone Summary tab: always open, fills its tab, no toggle or resize grip. */
+  embedded?: boolean;
 }
 
 /** "What's this change?" (spec §3.6): files tree first, then intent, why it's risky, changelists. Pushes the board. */
 export default function ChangePanel({ open, onToggle, reviewId, comments, onComments, layers, about, sideEffects, risk, openFiles,
-  dispatch, wide, width, onWidth, onWidthDone }: Props) {
+  dispatch, wide, width, onWidth, onWidthDone, embedded }: Props) {
   const [shut, setShut] = useState<Set<string>>(new Set());
-  if (!open)
+  if (!open && !embedded)
     return (
       <aside className="bd-about collapsed" onClick={onToggle}>
         <button className="bd-ibtn toggle" aria-label="Show change summary" title="Show change summary"
@@ -38,10 +40,10 @@ export default function ChangePanel({ open, onToggle, reviewId, comments, onComm
     );
   const nFiles = about.tree.reduce((n, d) => n + d.files.length, 0);
   return (
-    <aside className="bd-about" style={{ ["--w" as string]: `${width}px` }}>
-      <Resizer size={width} edge="right" min={280} max={() => window.innerWidth * 0.6} onSize={onWidth} onDone={onWidthDone} />
+    <aside className={`bd-about${embedded ? " embedded" : ""}`} style={{ ["--w" as string]: `${width}px` }}>
+      {!embedded && <Resizer size={width} edge="right" min={280} max={() => window.innerWidth * 0.6} onSize={onWidth} onDone={onWidthDone} />}
       <div className="top">
-        <button className="bd-ibtn toggle" title="Collapse" aria-label="Collapse change summary" onClick={onToggle}>‹</button>
+        {!embedded && <button className="bd-ibtn toggle" title="Collapse" aria-label="Collapse change summary" onClick={onToggle}>‹</button>}
         {risk && <span className={`bd-pill ${risk}`}>{risk.toUpperCase()} RISK</span>}
         <h2>What this change is trying to do</h2>
         <p>{about.cls.map((c) => `CL ${c.cl}`).join(" · ")} · {nFiles} files · {about.intent_source === "llm"
```

`frontend/src/board/phone/FlowReader.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import type { Comment } from "../../api";
import { CardBody } from "../CardLayer";
import type { Action, BoardState } from "../reducer";
import type { Board } from "../types";
import type { useSources } from "../useSources";
import { flowSteps } from "./flowSteps";

interface Props {
  reviewId: number;
  board: Board;
  state: BoardState;
  act: (a: Action) => void;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
  onOpenFile: (nodeId: string) => void;
}

/** Phone Flows tab (spec §13.3): one flow at a time as a list of steps; swipe or ‹ › between flows. */
export default function FlowReader({ reviewId, board, state, act, sources, comments, onComments, onOpenFile }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const down = useRef<{ x: number; y: number } | null>(null);
  const n = board.flows.length, i = Math.min(state.flow, n - 1), flow = board.flows[i];
  useEffect(() => setOpen(null), [i]);
  if (!flow) return <div className="ph-empty">No flows: the analysis found no side effect to trace. The Map tab shows the whole graph.</div>;
  const go = (k: number) => act({ t: "flow", i: (k + n) % n });
  const steps = flowSteps(board, flow);
  const lands = board.nodes.find((x) => x.id === flow.lands);
  const layer = board.layers.find((l) => l.level === lands?.layer)?.name ?? "unlayered";

  return (
    <div className="ph-reader"
         onPointerDown={(e) => { down.current = (e.target as HTMLElement).closest(".bd-code, textarea, input") ? null : { x: e.clientX, y: e.clientY }; }}
         onPointerUp={(e) => {                         // horizontal swipe between flows (not inside code, which scrolls sideways)
           const d = down.current;
           down.current = null;
           if (!d || n < 2) return;
           const dx = e.clientX - d.x, dy = e.clientY - d.y;
           if (Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) go(dx < 0 ? i + 1 : i - 1);
         }}>
      <div className="ph-pager">
        <button className="ph-nav" aria-label="Previous flow" onClick={() => go(i - 1)} disabled={n < 2}>‹</button>
        <span className="ph-num">{i + 1}</span>
        <span className="ph-title">{flow.title}</span>
        <span className={`bd-tag ${flow.tag}`}>{flow.tag}</span>
        <span className="ph-count">{i + 1}/{n}</span>
        <button className="ph-nav" aria-label="Next flow" onClick={() => go(i + 1)} disabled={n < 2}>›</button>
      </div>
      <div className="ph-what">{flow.what}</div>
      <ol className="ph-steps">
        {steps.map((s) => (
          <li key={s.id} className={`ph-step ${s.kind}${open === s.id ? " open" : ""}`}>
            <div className="ph-head" onClick={() => s.hasCode && setOpen(open === s.id ? null : s.id)}>
              <span className="ph-marker">{s.marker}</span>
              <div className="ph-text"><b>{s.label}</b><span className="ph-reason">{s.reason}</span></div>
              {s.hasCode && <span className="ph-caret">{open === s.id ? "▾" : "▸"}</span>}
            </div>
            {open === s.id && (
              <div className="ph-code">
                <CardBody node={s.node} reviewId={reviewId} board={board} sources={sources} comments={comments} onComments={onComments} />
                <button className="bd-ibtn ph-go" aria-label={`Open ${s.label} in Files`} onClick={() => onOpenFile(s.id)}>⤢ Full file</button>
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="ph-landing">
        <span className="k">⚠ Side effect lands on {lands?.label} ({layer})</span>
        {flow.effect}
        <div className="chk">{flow.check}</div>
      </div>
    </div>
  );
}
```

`frontend/src/board/phone/PhoneBoard.tsx`:

```tsx
import { type ReactNode, useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { api, type Comment } from "../../api";
import ThemeSwitch from "../../components/ThemeSwitch";
import ChangePanel from "../ChangePanel";
import FileViewer from "../FileViewer";
import { keys, loadTab, type PhoneTab, save } from "../prefs";
import type { Action, BoardState } from "../reducer";
import type { AffectedDir } from "../sideEffects";
import type { Board } from "../types";
import type { useSources } from "../useSources";
import FlowReader from "./FlowReader";
import "./phone.css";

interface Props {
  reviewId: number;
  board: Board;
  state: BoardState;
  act: (a: Action) => void;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  sideEffects: AffectedDir[];
  head: (extra: ReactNode) => ReactNode;
  onOpenFile: (nodeId: string) => void;
  /** The Map tab's content: the board's canvas stage, built by Board. */
  map: ReactNode;
}

const TABS: [PhoneTab, string, string][] = [["flows", "☰", "Flows"], ["map", "◎", "Map"], ["files", "▤", "Files"], ["summary", "✦", "Summary"]];

/** The board on a phone (spec §13.2): compact header, one tab at a time, tab bar at the bottom. */
export default function PhoneBoard(p: Props) {
  const { reviewId, board, state, act } = p;
  const [tab, setTab] = useState<PhoneTab>(() => loadTab(reviewId) ?? (board.flows.length ? "flows" : "map"));
  const [menu, setMenu] = useState(false);
  const choose = (t: PhoneTab) => { setTab(t); save(keys.tab(reviewId), t); };
  const seen = useRef(state.viewer.reveal?.seq ?? 0);
  useEffect(() => {                                    // opening any file (⤢, picker, summary) shows it in Files
    const seq = state.viewer.reveal?.seq ?? 0;
    if (seq !== seen.current) { seen.current = seq; setTab("files"); }
  }, [state.viewer.reveal]);
  const open = (path: string, line: number | null = null) => act({ t: "viewer.open", path, line, wide: false });

  return (
    <div className="bd phone">
      {p.head(<button className="ph-menu-btn" aria-label="Review menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>☰</button>)}
      {menu && (
        <nav className="ph-menu" onClick={() => setMenu(false)}>
          <NavLink to="/">All reviews</NavLink>
          <NavLink to={`/r/${reviewId}/findings`}>Findings</NavLink>
          <NavLink to={`/r/${reviewId}/files`}>Files (diff)</NavLink>
          <NavLink to={`/r/${reviewId}/cls`}>CLs &amp; Swarm</NavLink>
          <span onClick={(e) => e.stopPropagation()}><ThemeSwitch /></span>
          <button className="link" onClick={() => api.logout().then(() => window.location.assign("/login"))}>Log out</button>
        </nav>
      )}
      <div className={`ph-body ph-${tab}`}>
        {tab === "flows" && <FlowReader reviewId={reviewId} board={board} state={state} act={act} sources={p.sources}
                                        comments={p.comments} onComments={p.onComments} onOpenFile={p.onOpenFile} />}
        {tab === "map" && p.map}
        {tab === "files" && (state.viewer.files.length ? (
          <FileViewer reviewId={reviewId} viewer={state.viewer} dispatch={act} sources={p.sources} anns={board.impacts}
                      comments={p.comments} onComments={p.onComments} width={0} onWidth={() => {}} onWidthDone={() => {}} embedded />
        ) : (
          <div className="ph-pick">
            <h3>Files in this change</h3>
            {board.about.tree.flatMap((d) => d.files).map((f) => (
              <button key={f.path} onClick={() => open(f.path)}>📄 {f.name}<span>{f.path}</span></button>
            ))}
            {p.sideEffects.length > 0 && <h3>Files with side effects</h3>}
            {p.sideEffects.flatMap((d) => d.files).map((f) => (
              <button key={f.path} onClick={() => open(f.path, f.fns[0]?.line ?? null)}>⚠ {f.name}
                <span>{f.fns.map((x) => x.label).join(", ")}</span></button>
            ))}
          </div>
        ))}
        {tab === "summary" && (
          <ChangePanel open embedded onToggle={() => {}} reviewId={reviewId} comments={p.comments} onComments={p.onComments}
                       layers={board.layers} about={board.about} sideEffects={p.sideEffects} risk={p.risk}
                       openFiles={state.viewer.files} dispatch={act} wide={false} width={0} onWidth={() => {}} onWidthDone={() => {}} />
        )}
      </div>
      <nav className="ph-tabs" role="tablist">
        {TABS.map(([t, icon, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => choose(t)}>
            <i aria-hidden="true">{icon}</i>{label}
          </button>
        ))}
      </nav>
    </div>
  );
}
```

`frontend/src/board/phone/phone.css`:

```css
/* Phone board (spec §13): only rendered at ≤ 640 px. */
@media (max-width: 640px) {
  body:has(.bd.phone) .topbar { display: none; }                    /* the review header is the only bar */
}
.bd.phone { position: relative; }
.bd.phone .bd-head { flex-wrap: nowrap; }
.bd.phone .bd-head nav, .bd.phone .bd-head .bd-notes, .bd.phone .bd-head .rerun, .bd.phone .bd-head .bd-pill.ghost { display: none; }
.bd.phone .bd-head h1 { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ph-menu-btn { margin-left: auto; background: rgba(255,255,255,.14) !important; color: #fff !important; border: 0 !important;
  border-radius: 8px !important; font-size: 18px !important; line-height: 1; padding: 4px 10px !important; }
.ph-menu { position: absolute; right: 8px; top: 48px; z-index: 80; display: flex; flex-direction: column; gap: 12px; min-width: 190px;
  padding: 14px 16px; background: var(--bd-surface); border: 1px solid var(--bd-line); border-radius: 14px;
  box-shadow: 0 18px 48px rgba(var(--bd-shadow), .3); }
.ph-menu a, .ph-menu button.link { color: var(--bd-ink); font-size: 14px; text-align: left; }
.ph-body { flex: 1; min-height: 0; overflow: auto; position: relative; }
.ph-body.ph-map { overflow: hidden; display: flex; }
.ph-body.ph-map .bd-stage { flex: 1; }
.ph-tabs { flex: none; display: flex; background: var(--bd-surface); border-top: 1px solid var(--bd-line);
  padding-bottom: env(safe-area-inset-bottom); }
.ph-tabs button { flex: 1; border: 0 !important; background: none !important; padding: 7px 0 9px !important; font-size: 11px;
  color: var(--bd-muted) !important; border-radius: 0 !important; }
.ph-tabs button i { display: block; font-style: normal; font-size: 18px; line-height: 1.2; }
.ph-tabs button.on { color: var(--flow) !important; font-weight: 700; }

/* Flows tab */
.ph-reader { padding-bottom: 16px; touch-action: pan-y; }
.ph-pager { position: sticky; top: 0; z-index: 3; display: flex; align-items: center; gap: 7px; padding: 9px 10px;
  background: var(--bd-surface); border-bottom: 1px solid var(--bd-line); }
.ph-nav { border: 0 !important; background: var(--bd-sunken) !important; color: var(--flow) !important; font-size: 18px !important;
  width: 32px; height: 32px; border-radius: 9px !important; padding: 0 !important; flex: none; }
.ph-num { width: 22px; height: 22px; border-radius: 7px; background: var(--flow); color: #fff; display: grid; place-items: center;
  font-weight: 800; font-size: 12px; flex: none; }
.ph-title { flex: 1; min-width: 0; font-weight: 700; font-size: 13.5px; line-height: 1.25; }
.ph-count { color: var(--bd-muted); font-size: 12px; flex: none; }
.ph-what { padding: 10px 14px; font-size: 13px; line-height: 1.45; color: var(--bd-ink); border-bottom: 1px solid var(--bd-line);
  background: var(--bd-surface); }
.ph-steps { list-style: none; margin: 0; padding: 12px 10px 0; position: relative; }
.ph-steps::before { content: ""; position: absolute; left: 25px; top: 24px; bottom: 16px; width: 2px; background: var(--flow); opacity: .35; }
.ph-step { position: relative; margin-bottom: 9px; }
.ph-head { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.ph-marker { width: 32px; height: 32px; border-radius: 50%; flex: none; display: grid; place-items: center; font: 800 12px var(--bd-sans);
  background: var(--bd-surface); border: 2px solid var(--flow); color: var(--flow); z-index: 1; }
.ph-text { flex: 1; min-width: 0; background: var(--bd-surface); border: 1px solid var(--bd-line); border-radius: 12px; padding: 8px 10px; }
.ph-text b { display: block; font: 600 13px var(--bd-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ph-reason { display: block; color: var(--bd-muted); font-size: 12px; margin-top: 2px; }
.ph-caret { position: absolute; right: 12px; top: 10px; color: var(--bd-muted); }
.ph-step.chg .ph-marker { background: linear-gradient(135deg, #ffd36b, #ffab1f); border-color: var(--chg-deep); color: #2b1a00; }
.ph-step.chg .ph-text { border-color: var(--chg); }
.ph-step.field .ph-marker { background: var(--field-bg); border-color: var(--field); color: var(--field-ink); }
.ph-step.landing .ph-marker { background: var(--fx); border-color: var(--fx); color: #fff; }
.ph-step.landing .ph-text { border-color: var(--fx); background: var(--warn-bg); }
.ph-step.open .ph-text { border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
.ph-code { margin: 0 0 0 42px; background: var(--bd-card); border: 1px solid var(--bd-line); border-top: 0; border-radius: 0 0 12px 12px;
  overflow: hidden; }
.ph-code .bd-code { max-height: 55vh; }
.ph-code .ph-go { margin: 8px 10px; }
.ph-landing { margin: 6px 10px 0 52px; border-left: 3px solid var(--fx); background: var(--warn-bg); border-radius: 0 10px 10px 0;
  padding: 8px 12px; font-size: 13px; }
.ph-landing .k { display: block; font: 800 10px var(--bd-sans); letter-spacing: .08em; text-transform: uppercase; color: var(--fx-ink);
  margin-bottom: 3px; }
.ph-landing .chk { margin-top: 6px; color: var(--bd-check-ink); } .ph-landing .chk::before { content: "Check · "; font-weight: 700; }
.ph-empty { padding: 24px 16px; color: var(--bd-muted); }

/* Files and Summary tabs */
.bd-viewer.embedded, .bd-about.embedded { position: static !important; width: 100% !important; max-width: none !important; height: 100%;
  border: 0 !important; box-shadow: none !important; }
.ph-pick { padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
.ph-pick h3 { margin: 8px 0 2px; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--bd-muted); }
.ph-pick button { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; text-align: left; padding: 10px 12px !important;
  border-radius: 12px !important; background: var(--bd-surface) !important; border: 1px solid var(--bd-line) !important;
  font: 600 13.5px var(--bd-mono) !important; color: var(--bd-ink) !important; }
.ph-pick button span { font: 12px var(--bd-sans); color: var(--bd-muted); word-break: break-all; }
```

`frontend/src/board/Board.tsx`:

```diff
diff --git a/frontend/src/board/Board.tsx b/frontend/src/board/Board.tsx
index 1522529..db8c37e 100644
--- a/frontend/src/board/Board.tsx
+++ b/frontend/src/board/Board.tsx
@@ -12,6 +12,7 @@ import { makeLens, type Viewport } from "./lens";
 import { keys, loadAboutOpen, loadLayout, loadLens, loadMovedAll, loadSize, loadWidth, save } from "./prefs";
 import { type Action, initialState, reduce } from "./reducer";
 import type { Board as BoardModel } from "./types";
+import PhoneBoard from "./phone/PhoneBoard";
 import { useSources } from "./useSources";
 
 interface Props {
@@ -28,6 +29,18 @@ interface Props {
 }
 
 const wideScreen = () => window.innerWidth > 1100;
+const PHONE = "(max-width: 640px)";
+
+/** True while the window is phone-sized (spec §13); follows rotation and resizing. */
+function usePhone() {
+  const [phone, setPhone] = useState(() => window.matchMedia(PHONE).matches);
+  useEffect(() => {
+    const mq = window.matchMedia(PHONE), on = () => setPhone(mq.matches);
+    mq.addEventListener("change", on);
+    return () => mq.removeEventListener("change", on);
+  }, []);
+  return phone;
+}
 
 /** The review board (spec §2–§4): flow bar, lensed canvas with cards, file viewer and change panel. */
 export default function Board({ reviewId, board, files, comments, onComments, risk, focus, head }: Props) {
@@ -44,7 +57,8 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const [aboutW, setAboutW] = useState(() => loadWidth(keys.aboutW, 360));
   const [flowH, setFlowH] = useState<number | null>(() => loadSize(keys.flowH, 40, 4000));
   const [hint, setHint] = useState(true);
-  const stage = useRef<HTMLDivElement>(null);
+  const [stage, setStage] = useState<HTMLDivElement | null>(null);   // the canvas element; on phones it mounts with the Map tab
+  const phone = usePhone();
   const anim = useRef(0);
 
   useEffect(() => save(keys.moved(reviewId), state.moved), [reviewId, state.moved]);
@@ -84,7 +98,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
 
   // canvas size: keep the focused world point centred when panels open, close or resize
   useLayoutEffect(() => {
-    const el = stage.current;
+    const el = stage;
     if (!el) return;
     let first = true;
     const ro = new ResizeObserver(() => {
@@ -105,7 +119,7 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
     });
     ro.observe(el);
     return () => ro.disconnect();
-  }, [board, panBy]);
+  }, [stage, board, panBy]);
 
   const act = useCallback((a: Action) => { setHint(false); dispatch(a); }, []);
   const toggleAbout = () => { save(keys.about, !state.about); act({ t: "about.toggle" }); };
@@ -145,6 +159,18 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const narrow = typeof window !== "undefined" && window.innerWidth <= 640;
   const viewerOpen = state.viewer.files.length > 0;
   const cardCount = Object.keys(state.cards).length;
+  const canvas = vp.W > 0 && <>
+    <Canvas board={board} lens={lens} pos={pos} vp={vp} bands={bands} state={state} dispatch={act}
+            panBy={panBy} onOpenFile={openFile} onInteract={interact} />
+    <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
+               comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />
+  </>;
+  if (phone)
+    return (
+      <PhoneBoard reviewId={reviewId} board={board} state={state} act={act} sources={sources} comments={comments}
+                  onComments={onComments} risk={risk} sideEffects={sideEffects} head={head} onOpenFile={openFile}
+                  map={<div className="bd-stage" ref={setStage}>{canvas}</div>} />
+    );
   return (
     <div className="bd">
       {head(null)}
@@ -155,13 +181,8 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
         <ChangePanel open={state.about} onToggle={toggleAbout} reviewId={reviewId} comments={comments} onComments={onComments}
                      layers={board.layers} about={board.about} sideEffects={sideEffects} risk={risk} openFiles={state.viewer.files} dispatch={act}
                      wide={wideScreen()} width={aboutW} onWidth={setAboutW} onWidthDone={(w) => save(keys.aboutW, w)} />
-        <div className="bd-stage" ref={stage}>
-          {vp.W > 0 && <>
-            <Canvas board={board} lens={lens} pos={pos} vp={vp} bands={bands} state={state} dispatch={act}
-                    panBy={panBy} onOpenFile={openFile} onInteract={interact} />
-            <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
-                       comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />
-          </>}
+        <div className="bd-stage" ref={setStage}>
+          {canvas}
           <div className="bd-tools">
             <div className="bd-toolbar">
               <span className="bd-seg">
```

`frontend/src/board/board.css`:

```diff
diff --git a/frontend/src/board/board.css b/frontend/src/board/board.css
index b6d2496..fb2d244 100644
--- a/frontend/src/board/board.css
+++ b/frontend/src/board/board.css
@@ -190,11 +190,12 @@ body.bd-resizing-v, body.bd-resizing-v * { cursor: row-resize !important; user-s
 .bd-card .hd .sp, .bd-viewer .sp { flex: 1; }
 .bd-badge { font: 700 9.5px var(--bd-sans); letter-spacing: .08em; text-transform: uppercase; padding: 2px 7px; border-radius: 6px; }
 .bd-badge.ctx { background: var(--ctx-bg); color: var(--ctx-ink); } .bd-badge.chg { background: var(--chg-bg); color: var(--chg-ink); }
-.bd-card .effects { padding: 8px 12px; background: var(--effects-bg); border-bottom: 1px solid var(--bd-line); font-size: 12px; }
-.bd-card .effects div { margin: 3px 0; } .bd-card .effects .ico { color: var(--fx); font-weight: 700; margin-right: 4px; }
-.bd-card .fetched { padding: 5px 12px; font: 11px var(--bd-mono); color: var(--bd-muted); background: var(--bd-subtle);
+.bd-card .effects, .ph-code .effects { padding: 8px 12px; background: var(--effects-bg); border-bottom: 1px solid var(--bd-line); font-size: 12px; }
+.bd-card .effects div, .ph-code .effects div { margin: 3px 0; }
+.bd-card .effects .ico, .ph-code .effects .ico { color: var(--fx); font-weight: 700; margin-right: 4px; }
+.bd-card .fetched, .ph-code .fetched { padding: 5px 12px; font: 11px var(--bd-mono); color: var(--bd-muted); background: var(--bd-subtle);
   border-bottom: 1px solid var(--bd-line); }
-.bd-card .fetched b { color: var(--ctx-ink); font-weight: 600; }
+.bd-card .fetched b, .ph-code .fetched b { color: var(--ctx-ink); font-weight: 600; }
 .bd-card .bd-code { max-height: 300px; }
 .bd-card .hd .restore { display: none; }
 .bd-card.min { width: auto; border-radius: 99px; box-shadow: 0 6px 16px rgba(var(--bd-shadow), .18); cursor: pointer; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/phone.spec.ts`
Expected: `✓ built in …` and `2 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  67 passed (67)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/CardLayer.tsx frontend/src/board/FileViewer.tsx frontend/src/board/ChangePanel.tsx frontend/src/board/phone/FlowReader.tsx frontend/src/board/phone/PhoneBoard.tsx frontend/src/board/phone/phone.css frontend/src/board/Board.tsx frontend/src/board/board.css frontend/e2e/helpers.ts frontend/e2e/phone.spec.ts
git commit -m "feat(board): phone shell with flow reader, files and summary tabs"
```

---

### Task 7: Phone Map: pinch zoom, code sheet, long-press to move

The Map tab's canvas becomes touch-first (spec §13.4): `Canvas` takes a `touch` prop — two fingers pinch (anchor taken
at the start, then `pinchView`), a tap opens the node's code in a bottom sheet (deferred one tick so the tap's click
doesn't land in the sheet that opens under it), and a node moves only after a 450 ms long press (otherwise the drag
pans). Node hit areas are ≥ 40 px at any zoom (`--hit`). `PhoneMap` adds a floating pill (flow picker, ⋯ for layout,
lens and reset) and the sheet (grip: up = full height, down = half, then away). Cards are not rendered on phones.

**Files:**
- Modify: `frontend/src/board/Canvas.tsx`
- Create: `frontend/src/board/phone/PhoneMap.tsx`
- Modify: `frontend/src/board/phone/phone.css`
- Modify: `frontend/src/board/Board.tsx`
- Modify: `docs/superpowers/specs/2026-10-01-review-board-design.md`
- Modify: `frontend/e2e/phone.spec.ts`

**Interfaces:**
- Consumes: `zoomLens`, `pinchZoom`, `pinchView` (Task 4); `CardBody` (Task 6).
- Produces: `Canvas` prop `touch?: {onPinchStart(mid), onPinch(d0, d1, mid), onTap(id)}`; `phone/PhoneMap.tsx`.

- [ ] **Step 1: Write the failing test**

`frontend/e2e/phone.spec.ts`:

```diff
diff --git a/frontend/e2e/phone.spec.ts b/frontend/e2e/phone.spec.ts
index 8b47473..3cc45d5 100644
--- a/frontend/e2e/phone.spec.ts
+++ b/frontend/e2e/phone.spec.ts
@@ -68,3 +68,42 @@ test("the phone tab is remembered for the review", async ({ page }) => {
   await page.reload();
   await expect(tab(page, "Summary")).toHaveAttribute("aria-selected", "true");
 });
+
+test("phone map: pinch to zoom, tap a node for its code, long-press to move it", async ({ page }) => {
+  await startReview(page);
+  await tab(page, "Map").click();
+  const node = page.locator(".bd-node.chg", { hasText: "uart_send" });
+  await expect(node).toBeVisible();
+  const cdp = await page.context().newCDPSession(page);
+  const touch = (type: string, pts: [number, number][]) =>
+    cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
+  const centre = async () => { const b = (await node.boundingBox())!; return [b.x + b.width / 2, b.y + b.height / 2, b.width] as const; };
+
+  // pinch out around the node: it grows and stays under the fingers
+  const [x0, y0, w0] = await centre();
+  await touch("touchStart", [[x0 - 30, y0], [x0 + 30, y0]]);
+  for (let k = 1; k <= 6; k++) await touch("touchMove", [[x0 - 30 - k * 12, y0], [x0 + 30 + k * 12, y0]]);
+  await touch("touchEnd", []);
+  const [x1, y1, w1] = await centre();
+  expect(w1).toBeGreaterThan(w0 * 1.5);
+  expect(Math.hypot(x1 - x0, y1 - y0)).toBeLessThan(40);
+
+  // tap: the node's code opens in a sheet
+  await node.tap();
+  const sheet = page.locator(".ph-sheet");
+  await expect(sheet.locator(".bd-ann").first()).toContainText("through alias");
+  await expect(sheet.locator("textarea")).toHaveCount(0);                          // the tap's click must not land in the sheet
+  await sheet.getByRole("button", { name: "Close code" }).click();
+  await expect(sheet).toHaveCount(0);
+
+  // long-press, then drag: the node moves; a plain drag pans instead
+  await touch("touchStart", [[x1, y1]]);
+  await page.waitForTimeout(600);
+  for (let k = 1; k <= 5; k++) await touch("touchMove", [[x1 + k * 14, y1 + k * 10]]);
+  await touch("touchEnd", []);
+  await expect(node).toHaveClass(/\bmoved\b/);
+
+  // the floating pill picks flows
+  await page.getByLabel("Flow").selectOption({ label: "2 · logger_flush ignores -2" });
+  await expect(page.locator(".bd-node.onflow", { hasText: "logger_flush" })).toBeVisible();
+});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm run build && npx playwright test e2e/phone.spec.ts -g "phone map"`
Expected: FAIL — `1 failed` — the node does not grow on pinch (`Expected: > 84…`, `Received: 56…`)

- [ ] **Step 3: Implement**

`frontend/src/board/Canvas.tsx`:

```diff
diff --git a/frontend/src/board/Canvas.tsx b/frontend/src/board/Canvas.tsx
index cf87e10..81428f2 100644
--- a/frontend/src/board/Canvas.tsx
+++ b/frontend/src/board/Canvas.tsx
@@ -15,15 +15,37 @@ interface Props {
   panBy: (dx: number, dy: number) => void;
   onOpenFile: (id: string) => void;
   onInteract: () => void;
+  /** Phone Map (spec §13.4): two-finger pinch, tap opens the code sheet, long-press before a node moves. */
+  touch?: {
+    onPinchStart: (mid: { x: number; y: number }) => void;
+    onPinch: (d0: number, d1: number, mid: { x: number; y: number }) => void;
+    onTap: (id: string) => void;
+  };
 }
 
+const LONG_PRESS = 450;
+
 const KIND = { modified: "Δ modified", added: "Δ added", removed: "Δ removed", signature: "Δ signature" } as const;
 
 /** Layer bands, edges and nodes, all drawn through the lens; pans on drag, moves a node sideways when dragged by it. */
-export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, panBy, onOpenFile, onInteract }: Props) {
+export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, panBy, onOpenFile, onInteract, touch }: Props) {
   const root = useRef<HTMLDivElement>(null);
   const down = useRef<{ x: number; y: number; px: number; py: number; id: number; node: string | null; go: boolean;
-                        dragging: boolean; ox: number; oy: number } | null>(null);
+                        dragging: boolean; ox: number; oy: number; armed: boolean; timer: number } | null>(null);
+  const pts = useRef(new Map<number, { x: number; y: number }>());     // touch: active pointers
+  const pinch = useRef<{ d: number } | null>(null);
+  const spread = () => {
+    const [a, b] = [...pts.current.values()];
+    const r = root.current!.getBoundingClientRect();
+    return { d: Math.hypot(a.x - b.x, a.y - b.y), mid: { x: (a.x + b.x) / 2 - r.left, y: (a.y + b.y) / 2 - r.top } };
+  };
+  const end = () => {
+    if (down.current) window.clearTimeout(down.current.timer);
+    down.current = null;
+    document.body.classList.remove("bd-dragging");
+    setGrab(null);
+    setPanning(false);
+  };
   const [grab, setGrab] = useState<string | null>(null);   // node being dragged
   const [panning, setPanning] = useState(false);
   const { W } = vp;
@@ -58,19 +80,45 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
   return (
     <div ref={root} className={`bd-canvas${panning ? " drag" : ""}`}
       onPointerDown={(e) => {
+        e.preventDefault();                                  // no text selection starting on the board
+        if (touch) {
+          pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
+          if (pts.current.size === 2) {                      // a second finger: pinch, never a drag or a tap
+            end();
+            const s = spread();
+            pinch.current = { d: s.d };
+            touch.onPinchStart(s.mid);
+            root.current?.setPointerCapture(e.pointerId);
+            return;
+          }
+          if (pts.current.size > 2) return;
+        }
         const t = e.target as HTMLElement, n = t.closest<HTMLElement>(".bd-node"), r = root.current!.getBoundingClientRect();
         const at = n?.dataset.id ? pos.get(n.dataset.id) : undefined;     // keep the grab point under the pointer
-        down.current = { x: e.clientX, y: e.clientY, px: state.view.panX, py: state.view.panY, id: e.pointerId,
-                         node: n?.dataset.id ?? null, go: !!t.closest(".bd-go"), dragging: false,
-                         ox: at ? at.x - (e.clientX - r.left) : 0, oy: at ? at.y - (e.clientY - r.top) : 0 };
-        e.preventDefault();                                  // no text selection starting on the board
+        const d = { x: e.clientX, y: e.clientY, px: state.view.panX, py: state.view.panY, id: e.pointerId,
+                    node: n?.dataset.id ?? null, go: !!t.closest(".bd-go"), dragging: false,
+                    ox: at ? at.x - (e.clientX - r.left) : 0, oy: at ? at.y - (e.clientY - r.top) : 0,
+                    armed: !touch, timer: 0 };
+        if (touch && d.node)                                 // touch: a node moves only after a long press
+          d.timer = window.setTimeout(() => { if (down.current === d && !d.dragging) { d.armed = true; setGrab(d.node); } }, LONG_PRESS);
+        down.current = d;
       }}
       onPointerMove={(e) => {
+        if (touch && pts.current.has(e.pointerId)) pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
+        if (touch && pinch.current && pts.current.size === 2) {
+          const { d, mid } = spread();
+          touch.onPinch(pinch.current.d, d, mid);
+          pinch.current.d = d;
+          onInteract();
+          return;
+        }
         const d = down.current;
-        if (!d) return;
+        if (!d || d.id !== e.pointerId) return;
         if (!d.dragging) {
           if (Math.hypot(e.clientX - d.x, e.clientY - d.y) <= 6) return;
           d.dragging = true;
+          window.clearTimeout(d.timer);
+          if (!d.armed) d.node = null;                       // touch without a long press: pan, don't move the node
           root.current?.setPointerCapture(d.id);             // only once dragging: early capture swallows clicks
           document.body.classList.add("bd-dragging");
           window.getSelection()?.removeAllRanges();
@@ -82,23 +130,29 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
           dispatch({ t: "node.move", id: d.node, x: Math.round(lens.unprojectX(sx)), y: Math.round(lens.unprojectY(sx, sy)) });
         } else dispatch({ t: "pan", panX: d.px + (e.clientX - d.x), panY: d.py + (e.clientY - d.y) });
       }}
-      onPointerUp={() => {
+      onPointerUp={(e) => {
+        if (touch) {
+          pts.current.delete(e.pointerId);
+          if (pinch.current) { if (pts.current.size < 2) pinch.current = null; return; }
+        }
         const d = down.current;
-        down.current = null;
-        document.body.classList.remove("bd-dragging");
-        setGrab(null);
-        setPanning(false);
+        if (d && d.id !== e.pointerId) return;
+        end();
         if (!d || d.dragging || !d.node) return;
         const n = byId.get(d.node);
         if (!n?.path || !n.range) return;
         onInteract();
-        if (d.go) onOpenFile(d.node); else dispatch({ t: "card.open", id: d.node });
+        if (d.go) onOpenFile(d.node);
+        else if (touch) {                                    // after the tap's click, or it lands in the sheet that opens under it
+          const id = d.node;
+          window.setTimeout(() => touch.onTap(id), 0);
+        }
+        else dispatch({ t: "card.open", id: d.node });
       }}
-      onPointerCancel={() => {
-        down.current = null;
-        document.body.classList.remove("bd-dragging");
-        setGrab(null);
-        setPanning(false);
+      onPointerCancel={(e) => {
+        pts.current.delete(e.pointerId);
+        if (pts.current.size < 2) pinch.current = null;
+        end();
       }}>
       <svg className="bd-bands">
         {bands.map(({ key, row: i }) => (
@@ -137,7 +191,8 @@ export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, p
         const fx = badge.get(n.id);
         return (
           <div key={n.id} data-id={n.id} className={cls} title={n.label}
-               style={{ left: p.x, top: p.y, transform: `translate(-50%, -50%) scale(${p.s})`, zIndex: Math.round(p.s * 20) }}>
+               style={{ left: p.x, top: p.y, transform: `translate(-50%, -50%) scale(${p.s})`, zIndex: Math.round(p.s * 20),
+                        ["--hit" as string]: `${40 / Math.max(p.s, 0.1)}px` }}>
             {n.change && <span className="kind">{KIND[n.change.kind]}</span>}
             <span className="lbl">{n.label}</span>
             {n.change && <span className="stat"><b className="p">+{n.change.add}</b><b className="m">−{n.change.rem}</b></span>}
```

`frontend/src/board/phone/PhoneMap.tsx`:

```tsx
import { type ReactNode, useRef, useState } from "react";
import type { Comment } from "../../api";
import { CardBody } from "../CardLayer";
import type { LensStrength } from "../lens";
import type { Action, BoardState } from "../reducer";
import type { Board } from "../types";
import type { useSources } from "../useSources";

interface Props {
  children: ReactNode;                                  // the canvas stage
  reviewId: number;
  board: Board;
  state: BoardState;
  act: (a: Action) => void;
  setLayout: (l: "layers" | "depth") => void;
  onFlow: (i: number) => void;
  sheet: string | null;
  onCloseSheet: () => void;
  onOpenFile: (id: string) => void;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
}

/** Phone Map tab (spec §13.4): the touch canvas, one floating pill (flow picker + ⋯ options) and a code sheet. */
export default function PhoneMap(p: Props) {
  const { board, state, act } = p;
  const [more, setMore] = useState(false);
  const [full, setFull] = useState(false);
  const grip = useRef<number | null>(null);
  const node = board.nodes.find((n) => n.id === p.sheet);
  const value = state.mode === "graph" ? "graph" : String(state.flow);
  return (
    <div className="ph-mapwrap">
      {p.children}
      <div className="ph-pill">
        <select aria-label="Flow" value={value} onChange={(e) => {
          if (e.target.value === "graph") act({ t: "mode", mode: "graph" }); else p.onFlow(Number(e.target.value));
        }}>
          {board.flows.map((f, i) => <option key={f.id} value={i}>{i + 1} · {f.title}</option>)}
          <option value="graph">Whole graph</option>
        </select>
        <button className="bd-ibtn" aria-label="Map options" aria-expanded={more} onClick={() => setMore(!more)}>⋯</button>
      </div>
      {more && (
        <div className="ph-more">
          <span className="bd-seg">
            {(["layers", "depth"] as const).map((l) => (
              <button key={l} className={`bd-ibtn${state.layout === l ? " on" : ""}`} onClick={() => p.setLayout(l)}>
                {l === "layers" ? "Layers" : "Call depth"}
              </button>
            ))}
          </span>
          <span className="bd-seg">
            {([0, 2, 4] as LensStrength[]).map((m) => (
              <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} onClick={() => act({ t: "lens", lens: m })}>
                {m ? `${m}×` : "Off"}
              </button>
            ))}
          </span>
          {Object.keys(state.moved[state.layout]).length > 0 &&
            <button className="bd-ibtn" onClick={() => act({ t: "layout.reset" })}>Reset layout</button>}
          <span className="ph-tip">Pinch to zoom · drag to pan · long-press a function to move it</span>
        </div>
      )}
      {node && (
        <div className={`ph-sheet${full ? " full" : ""}`}>
          <div className="ph-grip"
               onPointerDown={(e) => { grip.current = e.clientY; e.currentTarget.setPointerCapture(e.pointerId); }}
               onPointerUp={(e) => {                     // drag up: full height; down: half, then away
                 const from = grip.current;
                 grip.current = null;
                 if (from === null) return;
                 const dy = e.clientY - from;
                 if (dy < -40) setFull(true);
                 else if (dy > 60) { if (full) setFull(false); else p.onCloseSheet(); }
               }} />
          <div className="ph-sheet-head">
            <b>{node.label}</b>
            <span className="sp" />
            <button className="bd-ibtn" aria-label={`Open ${node.label} in Files`} onClick={() => p.onOpenFile(node.id)}>⤢</button>
            <button className="bd-ibtn" aria-label="Close code" onClick={() => { setFull(false); p.onCloseSheet(); }}>✕</button>
          </div>
          <div className="ph-sheet-body">
            <CardBody node={node} reviewId={p.reviewId} board={board} sources={p.sources} comments={p.comments} onComments={p.onComments} />
          </div>
        </div>
      )}
    </div>
  );
}
```

`frontend/src/board/phone/phone.css`:

```diff
diff --git a/frontend/src/board/phone/phone.css b/frontend/src/board/phone/phone.css
index 07b8c54..8673b49 100644
--- a/frontend/src/board/phone/phone.css
+++ b/frontend/src/board/phone/phone.css
@@ -70,3 +70,25 @@
   border-radius: 12px !important; background: var(--bd-surface) !important; border: 1px solid var(--bd-line) !important;
   font: 600 13.5px var(--bd-mono) !important; color: var(--bd-ink) !important; }
 .ph-pick button span { font: 12px var(--bd-sans); color: var(--bd-muted); word-break: break-all; }
+
+/* Map tab */
+.ph-mapwrap { position: relative; flex: 1; display: flex; min-width: 0; }
+.ph-mapwrap .bd-stage { flex: 1; }
+.ph-mapwrap .bd-node::before { content: ""; position: absolute; left: 50%; top: 50%; width: max(100%, var(--hit, 40px));
+  height: max(100%, var(--hit, 40px)); transform: translate(-50%, -50%); }    /* ≥ 40 px touch target at any zoom */
+.ph-pill { position: absolute; left: 10px; right: 10px; top: 10px; z-index: 46; display: flex; gap: 6px; align-items: center;
+  background: var(--bd-surface); border-radius: 99px; padding: 5px 6px 5px 12px; box-shadow: 0 4px 14px rgba(var(--bd-shadow), .18); }
+.ph-pill select { flex: 1; min-width: 0; border: 0; background: transparent; color: var(--bd-ink); font: 600 13px var(--bd-sans); padding: 4px 0; }
+.ph-more { position: absolute; left: 10px; right: 10px; top: 58px; z-index: 46; display: flex; flex-wrap: wrap; gap: 8px; padding: 10px;
+  background: var(--bd-surface); border-radius: 14px; box-shadow: 0 8px 24px rgba(var(--bd-shadow), .2); }
+.ph-tip { width: 100%; font-size: 12px; color: var(--bd-muted); }
+.ph-sheet { position: absolute; left: 0; right: 0; bottom: 0; height: 50%; z-index: 60; display: flex; flex-direction: column;
+  background: var(--bd-card); border-radius: 16px 16px 0 0; box-shadow: 0 -10px 30px rgba(var(--bd-shadow), .25); }
+.ph-sheet.full { height: calc(100% - 8px); }
+.ph-grip { flex: none; height: 22px; touch-action: none; cursor: ns-resize; }
+.ph-grip::after { content: ""; display: block; width: 40px; height: 4px; border-radius: 2px; background: var(--bd-grip); margin: 9px auto 0; }
+.ph-sheet-head { flex: none; display: flex; align-items: center; gap: 8px; padding: 0 12px 8px; border-bottom: 1px solid var(--bd-line); }
+.ph-sheet-head b { font: 600 14px var(--bd-mono); } .ph-sheet-head .sp { flex: 1; }
+.ph-sheet-body { flex: 1; min-height: 0; overflow: auto; }
+.ph-sheet-body .effects { padding: 8px 12px; background: var(--effects-bg); border-bottom: 1px solid var(--bd-line); font-size: 12px; }
+.ph-sheet-body .fetched { padding: 5px 12px; font: 11px var(--bd-mono); color: var(--bd-muted); background: var(--bd-subtle); }
```

`frontend/src/board/Board.tsx`:

```diff
diff --git a/frontend/src/board/Board.tsx b/frontend/src/board/Board.tsx
index db8c37e..89897ad 100644
--- a/frontend/src/board/Board.tsx
+++ b/frontend/src/board/Board.tsx
@@ -13,6 +13,8 @@ import { keys, loadAboutOpen, loadLayout, loadLens, loadMovedAll, loadSize, load
 import { type Action, initialState, reduce } from "./reducer";
 import type { Board as BoardModel } from "./types";
 import PhoneBoard from "./phone/PhoneBoard";
+import PhoneMap from "./phone/PhoneMap";
+import { pinchView, pinchZoom, zoomLens } from "./zoom";
 import { useSources } from "./useSources";
 
 interface Props {
@@ -59,6 +61,8 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const [hint, setHint] = useState(true);
   const [stage, setStage] = useState<HTMLDivElement | null>(null);   // the canvas element; on phones it mounts with the Map tab
   const phone = usePhone();
+  const [zoom, setZoom] = useState(1);                // phone Map only (spec §13.4)
+  const [sheet, setSheet] = useState<string | null>(null);
   const anim = useRef(0);
 
   useEffect(() => save(keys.moved(reviewId), state.moved), [reviewId, state.moved]);
@@ -69,7 +73,8 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
   const sideEffects = useMemo(() => sideEffectFiles(board), [board]);
   const bands = useMemo(() => bandsFor(board, state.layout), [board, state.layout]);
   const world = useMemo(() => worldNodes(board, state.layout, state.moved[state.layout]), [board, state.layout, state.moved]);
-  const lens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
+  const baseLens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
+  const lens = useMemo(() => (phone ? zoomLens(baseLens, zoom, vp) : baseLens), [phone, baseLens, zoom, vp]);
   const pos = useMemo(() => new Map([...world.values()].map((n) => [n.id, lens.project(n.x, n.y)])), [world, lens]);
 
   const vpRef = useRef(vp);
@@ -156,20 +161,44 @@ export default function Board({ reviewId, board, files, comments, onComments, ri
     return board.layers.find((l) => l.level === lv)?.name ?? "unlayered";
   }, [nodes, board]);
 
+  const zoomRef = useRef(zoom);
+  zoomRef.current = zoom;
+  const anchor = useRef({ x: 0, y: 0 });               // world point under the fingers when the pinch started
+  const lensRef = useRef(lens);
+  lensRef.current = lens;
+  const onPinchStart = useCallback((mid: { x: number; y: number }) => {
+    anchor.current = { x: lensRef.current.unprojectX(mid.x), y: lensRef.current.unprojectY(mid.x, mid.y) };
+  }, []);
+  const onPinch = useCallback((d0: number, d1: number, mid: { x: number; y: number }) => {
+    const z1 = pinchZoom(zoomRef.current, d0, d1);
+    const next = pinchView(stateRef.current.view, z1, anchor.current, mid, vpRef.current, [...worldRef.current.values()].map((n) => n.x));
+    zoomRef.current = z1;
+    setZoom(z1);
+    window.cancelAnimationFrame(anim.current);
+    stateRef.current = { ...stateRef.current, view: next };       // several pinch moves can arrive before a render
+    dispatch({ t: "pan", panX: next.panX, panY: next.panY });
+  }, []);
   const narrow = typeof window !== "undefined" && window.innerWidth <= 640;
   const viewerOpen = state.viewer.files.length > 0;
   const cardCount = Object.keys(state.cards).length;
   const canvas = vp.W > 0 && <>
     <Canvas board={board} lens={lens} pos={pos} vp={vp} bands={bands} state={state} dispatch={act}
-            panBy={panBy} onOpenFile={openFile} onInteract={interact} />
-    <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
-               comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />
+            panBy={panBy} onOpenFile={openFile} onInteract={interact}
+            touch={phone ? { onPinchStart, onPinch, onTap: setSheet } : undefined} />
+    {!phone && <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
+                          comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />}
   </>;
   if (phone)
     return (
       <PhoneBoard reviewId={reviewId} board={board} state={state} act={act} sources={sources} comments={comments}
                   onComments={onComments} risk={risk} sideEffects={sideEffects} head={head} onOpenFile={openFile}
-                  map={<div className="bd-stage" ref={setStage}>{canvas}</div>} />
+                  map={
+                    <PhoneMap reviewId={reviewId} board={board} state={state} act={act} setLayout={setLayout} onFlow={selectFlow}
+                              sheet={sheet} onCloseSheet={() => setSheet(null)} onOpenFile={openFile} sources={sources}
+                              comments={comments} onComments={onComments}>
+                      <div className="bd-stage" ref={setStage}>{canvas}</div>
+                    </PhoneMap>
+                  } />
     );
   return (
     <div className="bd">
```

`docs/superpowers/specs/2026-10-01-review-board-design.md`:

```diff
diff --git a/docs/superpowers/specs/2026-10-01-review-board-design.md b/docs/superpowers/specs/2026-10-01-review-board-design.md
index 149c8b9..852e087 100644
--- a/docs/superpowers/specs/2026-10-01-review-board-design.md
+++ b/docs/superpowers/specs/2026-10-01-review-board-design.md
@@ -389,7 +389,8 @@ changes.
 - The existing canvas (Layers / Call depth, selected flow highlighted), full height. One floating pill: flow picker,
   and a ⋯ menu with layout, lens and Reset layout.
 - **Gestures:** one finger pans; two fingers pinch-zoom a phone-only scale `z ∈ [0.5, 2.5]` applied after the lens
-  (screen = centre + (lensed − centre) · z), keeping the pinch midpoint fixed; tap a node → its code in a bottom
+  (screen = centre + (lensed − centre) · z); the world point under the fingers when the pinch starts stays under
+  their midpoint (so two fingers also pan), solved through the real lens projection; tap a node → its code in a bottom
   sheet (half height; drag the grip up to full, down to dismiss); long-press (≥ 450 ms) then drag moves a node.
   Node hit areas are at least 40 px whatever the zoom. Dragging never selects text.
 
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run build && npx playwright test e2e/phone.spec.ts -g "phone map"`
Expected: `✓ built in …` and `1 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: `Tests  67 passed (67)` and no `tsc` output

- [ ] **Step 6: Commit**

```bash
git add frontend/src/board/Canvas.tsx frontend/src/board/phone/PhoneMap.tsx frontend/src/board/phone/phone.css frontend/src/board/Board.tsx docs/superpowers/specs/2026-10-01-review-board-design.md frontend/e2e/phone.spec.ts
git commit -m "feat(board): phone map — pinch zoom, tap for a code sheet, long-press to move"
```

---

## Spec Coverage

| Spec §13 | Where |
|---|---|
| 13.1 why / breakpoint | Task 6 (`usePhone`, `(max-width: 640px)`) |
| 13.2 phone shell: header menu, tabs, remembered tab | Tasks 4 (`loadTab`), 6 |
| 13.3 flow reader: pager, swipe, steps, reasons, inline code, ⤢, landing box | Tasks 2 (`flowSteps`), 6 (`FlowReader`) |
| 13.4 touch map: pill, ⋯ options, pinch, tap sheet, long press, 40 px targets | Tasks 4 (`zoom.ts`), 7 |
| 13.5 Files tab (viewer + picker), Summary tab | Task 6 |
| 13.6 flow titles | Task 1 |
| 13.7 files with side effects | Task 3 (panel), Task 6 (phone picker) |
| 13.8 tests | every task |

## Finish

- [ ] Run everything: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q` (expected `198 passed`) and
  `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx playwright test` (expected `Tests  67 passed (67)`, `19 passed`).
- [ ] Look at it on a phone: `uv run --project backend codetortoise fixture-demo --dir /tmp/ct-demo --port 8811`, serve it with
  `server.host: 0.0.0.0`, open it on a phone, review CLs `101 102`, and walk the four tabs.
