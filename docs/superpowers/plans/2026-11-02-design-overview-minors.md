# Design Overview Deferred Minors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 37 minors the four phases of the design overview deferred (phase 1: 10, phase 2: 9, phase 3: 10,
phase 4: 8), each under a test that failed first.

**Architecture:** Fixes stay in the module that owns the behaviour: the rules (`gates.py`, `walks.py`, `cparse.py`,
`components.py`), the model call (`llm/design.py`), the design stage and its queue (`pipeline.py`), the AI menu
(`llm/ondemand.py`, `design_pins.py`, `web/app.py`), the design context (`design_context.py`), and the pages
(`frontend/src/workspace/*`, `frontend/src/reading/*`). One new blob, `design_chosen`, replaces patching the kept
answer: it holds the words readers chose for one prompt (a rewrite, or words an unpin left showing) and is applied after
the model's text and before the pins.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, httpx, tree-sitter; React 19, TypeScript, Vite, vitest,
Playwright.

**Spec:** docs/superpowers/specs/2026-11-02-design-overview-design.md (§18 overrides earlier sections). The minors
themselves, with each reviewer's suggested fix, are in the four phases' final reviews; their one-line forms are in
`.superpowers/reports/2026-11-02-design-overview-final.md` ("Deferred minors").

## Global Constraints

- Public repo: no owner names, paths, hosts or anything from the owner's own code in code, tests, docs or commits.
- Every fix: a test that fails first (RED, for the reason the minor names), then passes (GREEN); a whole suite at the end.
- Backend: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider …`;
  `.venv/bin/ruff check codetortoise tests` (line length 132). Never uv.
- Frontend: `npx tsc --noEmit`, `npx tsc -p e2e --noEmit`, `npx vitest run`; e2e only after `npm run build`, from
  `frontend/`: `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test … --retries=0; rm -rf ../.pwtmp`.
- AI text stays marked as AI and is never hidden; a change to what the model is asked bumps `DESIGN_VERSION`.
- Commits: `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`, messages ending with the
  Co-Authored-By and Claude-Session lines.

## Review Focus

1. A design re-run, a rewrite, a pin and an unpin interleaved on one review: the words showing after each are the ones a
   reader expects, and a re-run of the same prompt keeps every reader's choice (Task 8, Task 10).
2. Links on a slow, compressed or badly addressed site: refused in words, within the deadline and the size limit, never
   a 500 (Task 12).
3. Conditions in `else if` chains, `switch` arms, `#if` branches and files with parse errors: the right lines run or
   stop, and no branch is dropped (Tasks 2–3).
4. The concerns table beside an open panel and on a phone: stacked, labelled, still a table to a screen reader (Task 14).
5. The design context page while a design re-run runs: two saves, a failed poll, design turned off (Tasks 11, 13).

---

### Task 1: What a changed line is (phase 1 M1, M3 part 2, M10)

**Files:** Modify `backend/codetortoise/gates.py`; Test `backend/tests/test_gates.py`.

- M10: `trivial()` takes a line for a comment only when nothing but a comment is on it: `/* why */ x = 1;` and
  `*/ x();` are code; `/* x */`, `// x`, a `*` continuation line stay comments.
- M3 (part 2): the condition fold's lists leave out changed lines of test files, preprocessor lines (`#…`) and lines in
  no function (declarations, globals): they neither run nor stop when a condition is false.
- M1: a condition in a function whose story is mechanical or tests (walks' `SKIP`) is not a condition: a rename inside
  an existing test, or a mechanical edit, adds none.

- [ ] Step 1: RED tests: `test_a_comment_followed_by_code_is_code`, `test_the_fold_leaves_out_test_files_preprocessor_lines_and_lines_in_no_function`,
  `test_a_condition_in_a_mechanical_or_tests_story_is_not_one`. Run; each fails for its reason.
- [ ] Step 2: GREEN in `gates.py` (`trivial`, `classify`, `build_gates`); update the demo's expectations only where a
  line the fix leaves out was listed (rule each in the ledger).
- [ ] Step 3: `pytest tests/test_gates.py tests/test_walks.py tests/test_design.py -q`; ruff; commit
  "fix: a condition's fold lists only lines that run, and a mechanical or test story adds no condition".

### Task 2: Arms and negation (phase 1 M5)

**Files:** Modify `backend/codetortoise/gates.py`, `backend/codetortoise/walks.py`, `backend/codetortoise/cparse.py`;
Tests `backend/tests/test_walks.py`, `backend/tests/test_cparse.py`.

- The true side of an `else if` arm runs none of its chain's other arms; the true side of a `case` runs none of the
  arms before it, and the arms after it only when it falls through (no break, return, goto or continue of its own).
  The gate keeps its chain's span (the whole `if … else if … else`, or the `switch` body) for `_runs`.
- `_negate`: a test that is `!` over one operand (`!p`, `!f(x)`, `!(a && b)`) reads without the `!` (`p`, `f(x)`,
  `a && b`); anything else keeps `!(…)`.

- [ ] Step 1: RED tests: `test_the_true_side_of_an_else_if_runs_no_other_arm_of_its_chain`,
  `test_the_true_side_of_a_case_runs_the_arms_after_it_only_when_it_falls_through`,
  `test_negating_a_not_drops_it_and_anything_else_is_wrapped`.
- [ ] Step 2: GREEN; Step 3: walks, gates, cparse tests; ruff; commit
  "fix: a condition's true side skips its chain's other arms, and `!p` negates to `p`".

### Task 3: Parse errors and outside callers (phase 1 M6, M4)

**Files:** Modify `backend/codetortoise/gates.py` (and `cparse.py` if `_tangled` must be shared); Test
`backend/tests/test_gates.py`.

- M6: `Sources.tree` flattens a file's `#if` branches only when its parse error is tangled with a directive, as
  `cparse._tangled` decides; a file with an include guard and an unrelated error keeps every branch.
- M4: `_only_guarded` counts a caller the impact model found in a file it did not parse (`x.im.edges`, a call edge
  whose caller is outside the parsed units) as a call site outside the condition: such a function still runs.

- [ ] Step 1: RED tests: `test_a_file_with_a_guard_and_an_unrelated_parse_error_keeps_its_else_branches`,
  `test_a_function_also_called_from_a_file_not_parsed_still_runs`.
- [ ] Step 2: GREEN; Step 3: gates, cparse, walks tests; ruff; commit
  "fix: conditions keep #else branches past an unrelated parse error and see callers in files not parsed".

### Task 4: Titles that repeat (phase 1 M8, phase 2 minor 1, phase 4 M5c)

**Files:** Modify `backend/codetortoise/walks.py`, `backend/codetortoise/llm/design.py`,
`backend/codetortoise/design_pins.py`; Tests `backend/tests/test_walks.py`, `backend/tests/test_llm_design.py`,
`backend/tests/test_design_pins.py`.

- Fixed walk-through titles that repeat (two functions gaining `ret < 0`) add "in `fn`" (then the file, if still equal).
- `apply_answer`: decide pass or fail per walk-through first; a passing title must differ from every other passing
  title and from every fixed title that stays (repeat until nothing changes).
- A walk-through pin whose title another walk-through now has is dropped with a note.

- [ ] Step 1: RED tests: `test_fixed_titles_that_repeat_name_their_function`,
  `test_a_model_title_equal_to_a_fixed_title_that_stays_fails`, `test_a_pinned_title_another_walk_through_now_has_is_dropped`.
- [ ] Step 2: GREEN; Step 3: walks, llm_design, design_pins tests; ruff; commit
  "fix: no two walk-throughs share a title, fixed, written or pinned".

### Task 5: A component of declarations has its threads (phase 1 M9)

**Files:** Modify `backend/codetortoise/components.py`; Test `backend/tests/test_components.py`.

- A component's threads also come from the files of each story's pieces, so a component whose changed files are only
  headers names the threads whose stories change them.

- [ ] Step 1: RED: `test_a_component_of_declarations_names_the_threads_that_change_it` (the demo's include/hal).
- [ ] Step 2: GREEN (update the demo's pinned `[]` with a ruling); Step 3: components and design tests; commit
  "fix: a component holding only declarations names the threads that change it".

### Task 6: Speed on a large change (phase 1 M7)

**Files:** Modify `backend/codetortoise/walks.py`, `backend/codetortoise/gates.py`; Test
`backend/tests/test_large_change.py`.

- `_readers`: sort the changed nodes and index each field's readers once per walker; `flow_keys`: index the checks by
  what they name once; `_holder`: bisect each file's sorted function spans.
- [ ] Step 1: measure the design stage on a synthetic change several times the large fixture; RED: a test with a time
  bound the old code misses by a wide margin (or, if no bound is robust, count the index builds; rule it).
- [ ] Step 2: GREEN; Step 3: walks, gates, large-change tests; commit "perf: the design rules index a change once".

### Task 7: What the prompt says (phase 2 minors 2, 5, 6)

**Files:** Modify `backend/codetortoise/llm/design.py`; Test `backend/tests/test_llm_design.py`.

- A fold reads as its own label ("… 2 returns", "… 13 steps") and as "some changed" or "unchanged".
- A walk-through over 12 steps shows its first 6 and its last 6, with "… +N steps" between: the landing stays in.
- Only the condition the overview shows (the first, when it has lines) is named and checked; the others stay listed
  as context and never fail the stage.
- `DESIGN_VERSION` goes up.

- [ ] Step 1: RED tests: `test_a_fold_reads_as_its_own_label_and_says_whether_it_holds_a_change`,
  `test_a_long_walk_through_shows_its_first_and_last_steps`, `test_only_the_shown_condition_is_named_and_checked`.
- [ ] Step 2: GREEN; Step 3: llm_design and pipeline tests; commit
  "fix: the design prompt words folds as the page does, keeps a walk-through's landing and names one condition".

### Task 8: The words readers chose survive a re-run (phase 4 M3, M4; phase 2 minor 8)

**Files:** Modify `backend/codetortoise/llm/design.py`, `backend/codetortoise/pipeline.py`,
`backend/codetortoise/llm/ondemand.py`, `README.md`; Tests `backend/tests/test_llm_design.py`,
`backend/tests/test_design_ai.py`, `backend/tests/test_pipeline.py`.

- Blob `design_chosen` = `{key, parts}`: the parts readers chose for the prompt `key` (design_text's shape, with each
  part's rewrite record). A rewrite writes it (replacing a blob of another key); an unpin writes the words left
  showing. The design stage applies it after the kept or fresh answer of the same key, before the pins. The kept
  answer stays the model's own (`patch_kept` goes).
- README: a condition gets a name, no lead; a re-run reuses the model's answer only when it passed every check, and
  always keeps what readers chose.

- [ ] Step 1: RED tests: `test_an_unpin_then_a_re_run_of_the_same_prompt_keeps_the_words_showing`,
  `test_a_rewrite_on_a_degraded_design_outlives_a_re_run_that_asks_again`,
  `test_the_kept_answer_stays_the_model_s_and_what_readers_chose_lands_on_it`.
- [ ] Step 2: GREEN (port the phase 4 tests that called `patch_kept`; rule it); Step 3: design tests, pipeline tests;
  commit "fix: what readers chose for a prompt outlives every re-run of it, degraded or unpinned".

### Task 9: A rewrite costs one call and none it can't land (phase 4 M1, M2)

**Files:** Modify `backend/codetortoise/llm/tiers.py` (or `llm/design.py`), `backend/codetortoise/llm/ondemand.py`,
`backend/codetortoise/web/app.py`, `backend/codetortoise/pipeline.py`; Tests `backend/tests/test_design_ai.py`,
`backend/tests/test_llm_design.py`.

- A rewrite asks the strong model once: no fresh retry, no weak model; "1 AI call" is then true.
- The job checks for a pin before its AI call; the route's "being rewritten" check and the submit happen under the
  pool's lock, so two requests at once start one job.

- [ ] Step 1: RED tests: `test_a_rewrite_asks_the_strong_model_once`, `test_a_part_pinned_while_its_rewrite_waits_costs_no_call`,
  `test_two_requests_at_once_start_one_rewrite`.
- [ ] Step 2: GREEN; Step 3: design AI, tiers, ondemand tests; commit
  "fix: a rewrite is one strong call, never spent on a part pinned meanwhile or asked twice at once".

### Task 10: A pin finds what it cites (phase 4 M5 a, b)

**Files:** Modify `backend/codetortoise/design_pins.py`; Test `backend/tests/test_design_pins.py`.

- A story a pin cites is found by what the rules made it of (its pieces), not by its title: a retold title keeps it;
  pins recorded before (titles only) still match by title.
- `gate_key` holds the condition's file and an ordinal among equal keys; a pin keyed the old way still matches the
  first condition of that function and test.

- [ ] Step 1: RED tests: `test_a_pin_keeps_a_story_whose_title_was_told_again`, `test_two_conditions_with_one_test_keep_their_own_pins`.
- [ ] Step 2: GREEN; Step 3: pins, pipeline, design AI tests; commit "fix: a pin finds its story by its pieces and its condition by file and order".

### Task 11: The design stage's re-run and its queue (phase 3 minors 3, 6 backend, 7, 10c)

**Files:** Modify `backend/codetortoise/pipeline.py`; Tests `backend/tests/test_pipeline.py`, `backend/tests/test_bundle.py`.

- A re-run starts the introduction from its fixed text, so a failed call shows what the stage says ("the fixed text stays").
- With `analysis.design: false`, saving a context still asks the introduction again with it.
- A design re-run that finishes while another for the same review waits leaves the stage pending.
- `busy()` names a design re-run when that is what waits.

- [ ] Step 1: RED tests: `test_a_re_run_s_failed_introduction_shows_the_fixed_text`,
  `test_with_the_design_off_saving_a_context_asks_the_introduction_again`,
  `test_a_design_re_run_with_another_waiting_leaves_the_stage_pending`, `test_busy_names_a_design_re_run`.
- [ ] Step 2: GREEN; Step 3: pipeline, bundle, web tests; commit "fix: a design re-run tells the truth about its introduction, its queue and a design turned off".

### Task 12: Links (phase 3 minors 1, 2, 3, 8 backend, 5 backend, 6 backend)

**Files:** Modify `backend/codetortoise/design_context.py`, `backend/codetortoise/web/app.py`, `README.md`; Tests
`backend/tests/test_design_context.py`, `backend/tests/test_web.py`.

- A link whose host is not a valid name is refused in words (no 500).
- A link is read within one deadline of 10 s for the whole read; a compressed body is unpacked at most 1 MB at a time
  and refused past it; an encoding other than gzip or deflate is refused.
- A transport failure says why in words (the certificate is not trusted, the site could not be reached, it took
  longer than 10 s); the README names `SSL_CERT_FILE`.
- Over the cap, the message names the longest document (or the notes) and its size.
- The PUT answers with the stored context (documents' read text included); the GET says whether the design is on.

- [ ] Step 1: RED tests: `test_a_link_with_an_invalid_host_name_is_refused_in_words`, `test_a_link_is_read_within_one_deadline`,
  `test_a_compressed_link_is_refused_past_1_mb_without_unpacking_it_all`, `test_a_transport_failure_says_why`,
  `test_over_the_cap_the_message_names_the_longest_document`, `test_saving_a_context_answers_with_what_was_stored_and_the_view_says_if_the_design_is_on`.
- [ ] Step 2: GREEN; Step 3: design context and web tests; commit "fix: links are refused in words, within one deadline and 1 MB, and the save answers with what it stored".

### Task 13: The design context panel and page (phase 3 minors 4, 5, 6, 8, 10 a b d)

**Files:** Modify `frontend/src/workspace/DesignContextPanel.tsx`, `frontend/src/workspace/useReview.ts`,
`frontend/src/api.ts`, `frontend/src/workspace/designContext.ts`; Tests `frontend/src/workspace/designContext.test.ts`,
`frontend/e2e/design-context.spec.ts`.

- A failed poll during a design re-run is skipped until the next tick; the page stays.
- The panel takes the PUT's stored context at once (read documents show their text and count).
- Each document shows its first lines, folded, to the owner and to readers; a reader sees a hand condition's function.
- With the design off, the panel hides conditions and components and says the notes reach the introduction.
- Keys are unique per condition; the reading is fetched once when a full run ends.

- [ ] Step 1: RED tests (e2e and vitest): a failed poll keeps the page; a saved link shows its text; a document's
  first lines show; design off hides conditions and components; one `/reading` fetch at a run's end.
- [ ] Step 2: GREEN; Step 3: build, vitest, the design-context e2e spec; commit "fix: the design context panel shows what it holds and the page outlasts a failed poll".

### Task 14: The overview's table, chips and steps (phase 1 step numbers; phase 2 minors 3, 4, 7)

**Files:** Modify `frontend/src/workspace/workspace.css`, `frontend/src/workspace/Overview.tsx`,
`frontend/src/workspace/Chips.tsx`, `frontend/src/workspace/WalkPage.tsx`, `frontend/src/workspace/FlowsTab.tsx`;
Tests `frontend/e2e/design-text.spec.ts`, `frontend/e2e/walk-throughs.spec.ts`, vitest where logic is pure.

- The concerns table stacks by the overview's own width (`@container`), with each stacked cell labelled for sighted
  readers and the table's roles kept for screen readers (`role` attributes; the header row visually hidden).
- The checks the verdict and a concern name show as chips whatever kinds the reader hides; a hidden kind's chip is muted.
- Step rows without a tick box keep the box's room, so every step number lines up.

- [ ] Step 1: RED e2e: the table stacks beside an open panel; stacked cells carry their labels and the cells keep
  `role=cell`; a cited confirm check shows its chip with Confirm hidden; step numbers share one x.
- [ ] Step 2: GREEN; Step 3: build, vitest, the affected e2e specs; commit "fix: the overview's table stacks by its own width and keeps its labels, cited checks always show, steps line up".

### Task 15: The Rewrite menu says why and keeps focus (phase 4 M6, M7, M8 UI)

**Files:** Modify `frontend/src/workspace/RewriteMenu.tsx`, `frontend/src/workspace/workspace.css`; Test
`frontend/e2e/design-rewrite.spec.ts`.

- After Pin or Unpin, focus returns to the Rewrite button.
- On a pinned part, the reason shows as text: in the owner's menu, and beside a disabled Rewrite button for anyone else.
- A failed or refused rewrite shows its error beside the menu (tested).

- [ ] Step 1: RED e2e: focus after Pin; the reason visible to bob on a pinned part; a refused rewrite says so and offers
  the owner Raise budget; a failed one shows its error.
- [ ] Step 2: GREEN; Step 3: build, design-rewrite spec; commit "fix: the Rewrite menu keeps focus and says why a part can't be rewritten".

### Task 16: Test gaps (phase 2 minor 9; phase 4 M8)

**Files:** Modify `frontend/e2e/fake_llm.py`, `frontend/e2e/design-text.spec.ts`; Tests
`backend/tests/test_pipeline.py`, `backend/tests/test_design_ai.py`.

- The fake writes one long verdict code span, a long concern and a long ownership line, and cites a function by its
  node id; the phone test checks nothing scrolls sideways, and the overview shows the function's name.
- A pipeline test changes the prompt between runs and sees the model asked again.
- A threaded test lands two rewrites of different parts together through `rewrite_design`.

- [ ] Step 1: write each; a gap test passes at once only if the code was already right — mutate the code to see it
  fail, then restore (ledger it).
- [ ] Step 2: commit "test: long AI text on a phone, a cited function by name, a changed prompt, two rewrites at once".

### Task 17: Every suite

- [ ] Run pytest, ruff, tsc, tsc -p e2e, build, vitest and the whole e2e suite with no retries; fix any failure under a
  failing test and ledger it.
