# Design Overview Deferred Minors, Round 2, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 13 minors the first minors round deferred (its final review's Minor 1, 2 and 5–10, four
pre-existing walk and facts faults, and one wording), each under a test that failed first.

**Architecture:** Each fix stays in the module that owns the behaviour. Links: `design_context.py`. Pins: `design_pins.py`.
Rules: `board._Ctx`, `gates.py`, `walks.py` and `facts_prep.py`. Pages: `useReview.ts`, `RewriteMenu.tsx` and
`workspace.css`. Two shared pieces are new:
- `_Ctx.callee_of(call)` resolves a call that tree-sitter knows only by name, the way the impact model does.
- `Branch.shut` holds the lines of the other arms of the `if` statements around a condition, which run on neither side of
  it.

**Tech Stack:** Python 3 (FastAPI, Pydantic v2, httpx, tree-sitter, zlib), React 19 + TypeScript, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-02-design-overview-design.md` (§18 overrides). The minors and their
reviewer's fixes: `.superpowers/reports/2026-11-02-design-overview-minors-final-review.md` and the "Deferred minors"
section of `.superpowers/reports/2026-11-02-design-overview-minors-rulings.md`.

## Global Constraints

- Public repository: generic names only, nothing from the owner's material (no proprietary identifiers, paths, user or
  machine names), and no absolute local paths in committed files.
- Spec §14: "Walk-throughs and gates are rules over data the pipeline already holds, so they cost no model calls."
- Spec §7 keeps the fold's three classes as defined: "under the condition: it doesn't run when the condition is false;
  outside it: it still runs; elsewhere: in another function. It still runs unless that function is reached only through
  the guarded branch." This plan changes the walk-throughs' sides, not the fold's classes.
- A link is read "at most 1 MB (unpacked, when packed), within 10 s for the whole read" (`MAX_LINK_BYTES`,
  `LINK_TIMEOUT`, README). Every refusal is said in plain words to the owner.
- Backend checks: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider …`
  and `.venv/bin/ruff check codetortoise tests`. Never `uv`.
- Frontend checks:
  - `npx tsc --noEmit -p .`, `npx tsc --noEmit -p e2e` and `npx vitest run`.
  - Playwright runs from `frontend/` after `npm run build`, with `TMPDIR` on disk:
    `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test … --retries=0; rm -rf ../.pwtmp`.

## Review Focus

1. A link whose site hangs before its headers, or before it connects. The save answers within the deadline and a moment,
   refused in words, and the read left behind holds up no later save. Tested in Task 1.
2. Packed bodies at the edges. A gzip body that unpacks to exactly 1 MB is read. A gzip body followed by a newline or a
   second member is read whole and not refused. Tested in Task 2.
3. A change parsed partly by clang and partly by tree-sitter. A function called only from the guarded block stops. One
   also called from the other parse's file still runs. Tested in Task 5.
4. Conditions nested two or three deep across `then` and `else` arms, with else-if chains and loops in between. Each side
   lists only the arms on its path, and no arm on the path is dropped. Tested in Task 6.
5. The owner's menu on a pinned part, used only with a keyboard:
   - arrow keys reach the shut items;
   - Enter on one does nothing;
   - Escape returns focus to Rewrite ▾;
   - on an unpinned part the items still work.

   Tested in Task 10.

---

### Task 1: A link's read ends within the deadline (final review Minor 1)

**Files:** Modify `backend/codetortoise/design_context.py` (`read_link`). Test `backend/tests/test_design_context.py`.

**Interfaces:** Produces `_read(url: str, deadline: float, client: httpx.Client | None) -> str`: today's body of
`read_link` after its checks. `read_link` keeps its signature and its refusals.

- [ ] **Step 1: RED.** Write `test_a_site_that_trickles_its_headers_is_refused_within_the_deadline`:
  - Start a local server, on a free port of 127.0.0.1 in a thread, that sends one byte of its status line every 0.2 s
    for 5 s.
  - Patch `LINK_TIMEOUT` to 0.5.
  - Call `read_link(f"http://127.0.0.1:{port}/a.md", [f"127.0.0.1:{port}"])`.
  - It raises `LinkRefused` with `_slow()`'s words within 1.5 s.
  - For Review Focus 1, a second `read_link` right after it, against a normal local server, reads its text at once.
  - Run it. Expected: FAIL, because the read takes about 5 s or answers with something else.
- [ ] **Step 2: GREEN.** `read_link` runs `_read` in a daemon thread named `read-link` and joins it for `LINK_TIMEOUT`:
  ```python
  box: dict = {}

  def work() -> None:
      try:
          box["text"] = _read(url, deadline, client)
      except BaseException as e:  # noqa: BLE001 - handed to the caller below
          box["error"] = e
  t = threading.Thread(target=work, name="read-link", daemon=True)
  t.start()
  t.join(max(0.0, deadline - time.monotonic()))
  if t.is_alive():              # connect, DNS or a header that trickles: httpx bounds each step, not the whole read
      raise LinkRefused(_slow())
  if "error" in box:
      raise box["error"]
  return box["text"]
  ```
  The thread left behind ends on its own: httpx's per-step timeout, or `_body`'s deadline check. The docstring says so.
- [ ] **Step 3:** Run `tests/test_design_context.py` and the design-context web tests. Expected: PASS.
- [ ] **Step 4: Commit.** "fix: a link's read ends within its deadline, however slowly the site answers".

### Task 2: A packed body is read to its end and no further (final review Minor 2)

**Files:** Modify `backend/codetortoise/design_context.py` (`_body`). Test `backend/tests/test_design_context.py`.

- [ ] **Step 1: RED.** Write `test_a_packed_body_is_read_to_its_end_and_no_further`, with httpx `MockTransport`
  responses whose stream is a generator:
  - A gzip body of a short markdown text, then zero chunks of 64 KiB with no end. The generator raises `AssertionError`
    after 50 of them, so reading on fails the test. Expected: the text.
  - Two gzip members, "one " and "two". Expected: "one two".
  - A gzip body that unpacks to exactly `MAX_LINK_BYTES`, followed by `b"\n"`. Expected: read, not refused.

  Run it. Expected: FAIL. The endless one raises `AssertionError`, and two members read as "one ".
- [ ] **Step 2: GREEN.** In `_body`'s unpacking branch, after each `decompress`:
  - When `unpack.eof`, the leftover is `unpack.unused_data`.
  - If the encoding is gzip and the leftover starts with `b"\x1f\x8b"`, a new `zlib.decompressobj(16 + zlib.MAX_WBITS)`
    takes it, and the size check stays across members.
  - When the leftover is empty, mark the stream ended. The next chunk is read only to see whether it starts a gzip
    member.
  - Anything else after the end: return what was unpacked and stop reading. The connection closes with the stream.
- [ ] **Step 3:** Run `tests/test_design_context.py`. Expected: PASS.
- [ ] **Step 4: Commit.** "fix: a packed link body is read to its end and no further, every gzip member of it".

### Task 3: A certificate failure says what is wrong, and a blank name reads as one (final review Minor 5; the blank-name wording)

**Files:** Modify `backend/codetortoise/design_context.py` (`_untrusted`, `_why`, `over_cap`). Test
`backend/tests/test_design_context.py`.

**Interfaces:** `_untrusted(e) -> bool` becomes `_certificate(e) -> str | None`. It returns the failed check in words:
the `verify_message` of the `ssl.SSLCertVerificationError` in the cause chain, else the words after "certificate verify
failed: " in the text, else "".

- [ ] **Step 1: RED.** Write `test_a_certificate_failure_says_what_is_wrong`:
  - Build an `ssl.SSLCertVerificationError` with `verify_message` "certificate has expired", as the `__cause__` of an
    `httpx.ConnectError`.
  - `_why` of it reads "The site's certificate is not valid: certificate has expired."
  - With "unable to get local issuer certificate", or "self-signed certificate in certificate chain", it still gives
    today's `SSL_CERT_FILE` advice.

  Write `test_the_cap_message_names_a_document_with_a_blank_name_in_words`: `over_cap` of a context whose only document
  is named "   " and holds 13 000 characters ends "The longest part is the document with no name, at 13,000
  characters." Run both. Expected: FAIL.
- [ ] **Step 2: GREEN.**
  - The `SSL_CERT_FILE` advice is given for a failed check of "unable to get local issuer certificate", "unable to get
    issuer certificate", or one naming a self-signed certificate.
  - Any other check: "The site's certificate is not valid: <check>."
  - No words found: today's advice.
  - `over_cap` names a document `d.name.strip() or "with no name"`.
- [ ] **Step 3:** Run `tests/test_design_context.py`. Expected: PASS.
- [ ] **Step 4: Commit.** "fix: a certificate failure says which check failed, and a blank document name reads as one".

### Task 4: A condition's key counts its place by line (final review Minor 7)

**Files:** Modify `backend/codetortoise/design_pins.py` (`gate_key`). Test `backend/tests/test_design_pins.py`.

- [ ] **Step 1: RED.** Write `test_a_condition_key_counts_its_place_by_line_not_by_strength`:
  - Take `_alike(written)` (G1 at line 16, G9 at line 30, same function, test and file).
  - Pin G9's false case, then move G9 ahead of G1 in `d.gates`, as a change that makes it the stronger would.
  - The pin still lands on G9 (by line), and G1 keeps its own words.

  Run it. Expected: FAIL. Today the place follows `d.gates`' order, so the pin moves to G1.
- [ ] **Step 2: GREEN.** `alike` is the matching conditions sorted by `(o.line or 0, o.id)`.
- [ ] **Step 3:** Run `tests/test_design_pins.py` and `tests/test_design_ai.py`. Expected: PASS.
- [ ] **Step 4: Commit.** "fix: a condition's pin key counts its place in source order, not strength order".

### Task 5: A call known only by name finds its function (deferred pre-existing: tree-sitter files never stop; facts_prep counts callers twice)

**Files:**
- Modify `backend/codetortoise/board.py` (`_Ctx`), `backend/codetortoise/gates.py` (`_only_guarded`) and
  `backend/codetortoise/facts_prep.py` (`_call_sites`, `signature_facts`).
- Test `backend/tests/test_gates.py` and `backend/tests/test_facts_prep.py`.

**Interfaces:**
- `_Ctx.callee_of(call) -> str`: the callee's key, a "name:" key resolved by `impact._name_resolver({**fb, **fa})` as
  the impact model resolves it.
- `_Ctx.outside_callers(nid: str) -> set[str]`: node ids with a live call edge (status not "removed") into `nid` from a
  function this review did not parse (src key not in `fa`). These are the callers "outside the parsed files".

- [ ] **Step 1: RED.** Write `test_a_function_called_only_from_the_guarded_block_stops_in_a_tree_sitter_file`, with the
  reviewer's world from `test_probe_guarded_ts.py`:
  - Functions `send`, `only`, `both` and `other`. `send` calls `only()` inside `if (len > 64) { … return -2; }` and
    `both()` after it; `other` calls `both()`.
  - The world is converted to tree-sitter facts: `ts:` keys, "name:" callees, heuristic edges.
  - `only` is `elsewhere` and stops, and `both` runs, as with clang facts.
  - For Review Focus 3, a mixed world (`send` parsed by clang, `other` by tree-sitter) gives the same classes.

  Write `test_a_call_known_by_name_is_a_call_site_and_counted_once` in `test_facts_prep.py`, on the same tree-sitter
  world:
  - `signature_facts` for `only` lists `send`'s call at its line as a call site.
  - It writes no "more caller(s) outside the parsed files" row.
  - A by-name caller outside the parsed files, an impact edge from a `ts:other.c#far` key, adds one, counted once.

  Run both. Expected: FAIL. `only` runs, and the tree-sitter caller is counted as outside.
- [ ] **Step 2: GREEN.**
  - `_Ctx.__init__` keeps `self._resolve = _name_resolver({**self.fb, **self.fa})`, and adds `callee_of` and
    `outside_callers`.
  - `_only_guarded` keys its sites by `x.callee_of(e)`. A callee is called from afar when `x.outside_callers(nid)` is
    non-empty for its node, not whenever an edge into it is heuristic. That is the Task 3 ruling's own reading: "a
    caller outside the parsed units".
  - `facts_prep._call_sites` matches `x.callee_of(c) == key`, and `signature_facts` counts `x.outside_callers(nid)`.
- [ ] **Step 3:** Run `tests/test_gates.py`, `tests/test_walks.py`, `tests/test_facts_prep.py`, `tests/test_design*.py`
  and `tests/test_large_change.py`. Expected: PASS. A changed count in an existing assertion is ledgered with its cause.
- [ ] **Step 4: Commit.** "fix: a call tree-sitter knows by name finds its function, for conditions and call sites".

### Task 6: A walk-through skips the other arms of the ifs around its condition (deferred pre-existing: an if inside a plain else; an else-if's false side)

**Files:** Modify `backend/codetortoise/gates.py` (`Branch`, `_if_branch`, `_case_branch`, new `_shut`) and
`backend/codetortoise/walks.py` (`_runs`). Test `backend/tests/test_walks.py`.

**Interfaces:**
- `Branch.shut: set[int]`, default empty: the lines of the other arms of every enclosing `if_statement`. They run on
  neither side of the condition.
- `_shut(node, ln) -> set[int]` walks up from the condition's node to the function:
  - At each `if_statement` whose consequence holds the path, the alternative's lines are shut: its statements' span, or
    a whole else-if.
  - At each one whose alternative holds the path, the consequence's statements' span is shut.
  - That statement's own test lines are never shut (the declined item 4 ruling: a line shared with a test reads as run).
- `_runs` returns False for a line in `g.shut`, on both sides. It comes after the test-line check and before everything
  else.

- [ ] **Step 1: RED.** Write `test_a_condition_inside_an_else_block_runs_no_arm_of_the_if_around_it`, from the reviewer's
  probe `test_if_in_plain_else_block`:
  - `pick` has `if (ready(m)) { a(); } else { if (m == 2) { b(); } c(); }`.
  - The true side holds `ready` (its test) and `b()`, then `c()`, and no `a()`.
  - The false side holds `c()` and no `a()`.

  Write `test_the_false_side_of_an_else_if_runs_no_earlier_arm`: on the chain of
  `test_the_true_side_of_an_else_if_runs_no_other_arm_of_its_chain`, the false side of `m == 2` holds `ready` and `c()`,
  and no `a()`.

  For Review Focus 4, write `test_nested_conditions_run_only_the_arms_on_their_path`. An `if` inside a `for` inside the
  `then` arm of an `if` that is itself an else-if arm. Each side lists only its path's arms, and the loop's own calls stay
  on both sides.

  Run them. Expected: FAIL, on `a()` listed as running.
- [ ] **Step 2: GREEN.** Add `Branch.shut` and `_shut`, called by `_if_branch` and `_case_branch`. `_runs` checks it.
  `_runs` keeps chain and `tried` for the true side, as Task 2 of the first round made it.
- [ ] **Step 3:** Run `tests/test_walks.py`, `tests/test_gates.py`, `tests/test_design*.py` and the demo-based tests
  (`tests/test_llm_design.py`, `tests/test_large_change.py`). Expected: PASS. A demo walk-through that changes is
  ledgered with the line that moved and why.
- [ ] **Step 4: Commit.** "fix: a walk-through skips the other arms of the ifs around its condition, on both sides".

### Task 7: The speed test times the conditions' classing too (final review Minor 10)

**Files:** Modify `backend/tests/test_large_change.py` (the ratio test at about lines 225–248).

- [ ] **Step 1:** Extend the ratio test to time `build_gates` (and with it `classify`) on the same 400- and 1600-function
  changes, with the same bound (under 7× for 4× the functions, best of 3).
- [ ] **Step 2: watch it fail.** The code is right today, so the test passes at once. To see it fail:
  - Swap `_Spans.holder`'s bisection for a scan of every function in the file (a temporary edit), and watch the test
    fail on the ratio.
  - Restore the code, and ledger the mutation and its numbers.
- [ ] **Step 3: Commit.** "test: the speed test times the conditions' classing as well as the walker".

### Task 8: The re-run poll stops on a failure that lasts (final review Minor 6)

**Files:** Modify `frontend/src/workspace/useReview.ts`. Test `frontend/e2e/design-context.spec.ts`.

- [ ] **Step 1: RED.** In the "phase 3 minors" describe, write "a look the server refuses for good ends the re-run's
  polling and says why":
  - Save a context so the design re-runs.
  - Then route `**/api/reviews/<id>` to a 404 `{"detail": "no such review"}`.
  - The page shows an alert with "no such review".
  - The route's hit count stays the same over the next 3.5 s.

  Run it. Expected: FAIL. No alert shows, and the hits keep growing.
- [ ] **Step 2: GREEN.**
  - A look that fails with an `ApiError` of status 401, 403 or 404 sets `gone`, a new state that ends `rerun`, and is
    passed to `fail`.
  - Any other failure (no answer, a 5xx) is skipped until the next look, as phase 3 minor 4 made it.
  - The comment above the effect says which failures are which.
- [ ] **Step 3:** `npx tsc --noEmit -p .`, build, then run `e2e/design-context.spec.ts`. Expected: PASS.
- [ ] **Step 4: Commit.** "fix: the design re-run's poll stops and says why when the server refuses it for good".

### Task 9: A stacked cell's label is read once (final review Minor 8)

**Files:** Modify `frontend/src/workspace/workspace.css` (the `td[data-label]::before` rule). Test
`frontend/e2e/design-text.spec.ts` (the phone describe).

- [ ] **Step 1: RED.** In the phone test, get each stacked cell's accessible name from Chromium's accessibility tree
  through a CDP session (`Accessibility.getPartialAXTree` on the cell's node), so the check is the browser's own.
  - The second cell's name holds the "how" text and not "How the change does it".
  - The `::before` label is still drawn: the computed `content` of `::before` holds `attr(data-label)`'s text.

  Run it. Expected: FAIL, because the name holds the label too. If Chromium's tree leaves generated content out of a
  cell's name, the test passes at once. Then ledger it, keep the CSS fix for other browsers, and prove the test with a
  mutation.
- [ ] **Step 2: GREEN.** Keep `content: attr(data-label);` and add `content: attr(data-label) / "";` after it. A browser
  that knows the alternative-text form takes the second; one that doesn't keeps the first.
- [ ] **Step 3:** Build, then run `e2e/design-text.spec.ts`. Expected: PASS.
- [ ] **Step 4: Commit.** "fix: a stacked cell's label is drawn for the eye and read once by a screen reader".

### Task 10: The owner's menu says why Rewrite is shut, to a keyboard too (final review Minor 9)

**Files:** Modify `frontend/src/workspace/RewriteMenu.tsx`. Test `frontend/e2e/design-rewrite.spec.ts`.

- [ ] **Step 1: RED.** In the "says why and keeps focus" describe, write "on a pinned part the menu's shut items take
  focus and say why". The owner pins the verdict and opens the menu with Enter on Rewrite ▾. Then, for Review Focus 5:
  - The focused item is "Rewrite", with `aria-disabled="true"` and the accessible description "Pinned: unpin it to
    rewrite it".
  - Enter on it opens no dialog and sends no rewrite request.
  - ArrowDown reaches "Rewrite with an instruction…" (shut, same description), then "Unpin".
  - Escape returns focus to Rewrite ▾.
  - Bob's disabled Rewrite ▾ has the reason as its accessible description.
  - On an unpinned part, Enter on "Rewrite" still opens the confirmation.

  Run it. Expected: FAIL. The disabled items take no focus, and the first focused item is "Unpin".
- [ ] **Step 2: GREEN.**
  - The reason line gets `id={why}` (from `useId`).
  - The two Rewrite items keep `disabled={running}` and add `aria-disabled={!items.rewrite || undefined}` and
    `aria-describedby={items.why ? why : undefined}`. Their `onClick` returns at once when `!items.rewrite`.
  - Rewrite ▾ gets `aria-describedby={barred ? why : undefined}`, pointing at the reason shown beside it.
  - Check `lib/useMenu.ts`: an `aria-disabled` item must stay reachable by the arrow keys.
- [ ] **Step 3:** Build, then run `e2e/design-rewrite.spec.ts`. Expected: PASS.
- [ ] **Step 4: Commit.** "fix: the shut Rewrite items take focus and say why, to a keyboard and a screen reader".

### Task 11: Every suite

- [ ] Run pytest, ruff, tsc, `tsc -p e2e`, the build, vitest and the whole e2e suite with no retries. Fix any failure
  under a failing test and ledger it.
