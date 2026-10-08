# Review Reading: a Review Reads as One Connected Account — Design

Date: 2026-10-07. Status: draft for review. Follows two-tier stories (2026-10-05-two-tier-stories-design.md) and the
review workspace (2026-10-04-review-workspace-design.md). Work happens on branch `review-reading`; nothing reaches
main until the owner decides.

## 1. Why

On a real change set at work (about 60 files, one feature spread across several CLs, the same file edited in more than
one CL) reviewers could not tell what the change does, where it lives, which call paths it changes or what was missed,
even with a strong model forming the stories. Lab review 19 (three CLs, about 30 files) shows the same problems:

- **Six parallel ways to slice the same code.** The rail lists CLs, stories and 27 findings; the home page adds the
  map's parts and layers and the side-effect files. Each uses its own words (parts, stories, flows, findings, layers,
  TUs, verdicts). The reader assembles the picture.
- **Headlines describe the analysis, not the change.** Stories are named by folder ("Other changes in
  deps/reftable"); "Why it is high risk" leads with "common.h: 2 change(s) reach 713 TU(s)", which measures rebuilds,
  not behaviour; the intent paragraph lists detector output.
- **Lists where a sentence would do.** A story shows 18 identical cards ("signature changed", "+2 −1 lines") where one
  line ("12 signatures gained `opts`") would say it.
- **Raw machine output.** Finding evidence prints a Python dict and absolute paths; "0 flows" reads as broken.
- **What was missed is buried.** The facts already know which callers were not updated and who reads newly written
  fields, but that only appears inside a finding's evidence.
- **Stories read as disconnected articles.** Nothing says how the stories, or the groups of stories, relate.

## 2. Goals

Agreed with the owner, 2026-10-07:

- A reviewer who opens a review understands, without stitching it together: what the change does as a whole, how its
  parts connect, where each part lives, which call paths it changes, and what may have been missed.
- Stories are formed from the code, not from CLs. CL descriptions are hints the strong model may quote; they are not
  a source of truth (one feature can span CLs because of how the depot is organised).
- Stories that belong together form **threads**; the overview says how the threads connect, including when the only
  tie is that they were bundled.
- Every story page answers the same questions in the same place, as tiles (layout B, §6).
- "To check" is the reviewer's to-do list: the strong model's hazards plus the places the analysis thinks were missed,
  each with Looks fine and Comment.
- Everything in §5–§8 is computed by the analysis and works without AI; the strong model writes names and sentences
  over facts it is given.

Phases:

- **Phase 1 (this design, §3–§13):** threads and connections, the overview, the story page, To check, reading order,
  the clean-up.
- **Phase 2 (§14, specified later on the same branch):** CLs as a sequence, per-hunk CL tags, stacked-CL flags, a
  reading plan with progress.

## 3. Vocabulary

The UI uses five words: **story**, **thread**, **call path** (for flows), **check** (for findings), **possibly
missed**. "Parts", "pieces", "clusters", "chapters", "TU" and "layer" leave headings and labels. The map (clusters by
layer) stays, reachable from the Index (§11). Code keeps its names; only what the reader sees changes.

## 4. Threads and connections (analysis, no AI)

Runs in a new pipeline stage `reading` after `llm` (§10.2). Inputs: the story set, pieces and their links, the
impact model, targets, the prepared facts.

### 4.1 Story links

For each pair of stories, the strongest link between their changed code:

| Strength | Link | Example text |
|---|---|---|
| strong | calls: a function in one calls a function the other changed | "calls `reftable_new_stack`, changed in story 1" |
| strong | data: one reads or writes a field the other now writes | "reads `opts.hash_id`, which story 1 now writes" |
| weak | same file only | "both edit `config.c`" |
| weak | same CL only | "both arrive in CL 12" |

The direction is recorded: the story that changed the callee or writes the field **defines**; the other **uses**.

### 4.2 Threads

A thread is a connected component of strong story links. Tests stories never join threads; they get the Tests row
(§5.3). A story with no strong link is a thread of one.

### 4.3 Thread connections

For each pair of threads, the strongest connection found, from strongest to weakest:

1. **Shared caller.** Their changed functions have a common caller within 3 call hops (reverse call edges in the
   impact model, including heuristic edges). Entry points (`analysis.entrypoint_patterns`) are preferred; otherwise
   the nearest common caller. Text: "both run inside `git_repository_open`".
2. **Shared code vocabulary.** Both change or use the same struct (field records), the same header (a changed header
   both include, or a header both edit) or the same macro (header findings' macro names). Text: "both use `struct
   git_config`".
3. **Same build or platform condition.** Both sit only in the same build target while the review spans more than one
   target, or their changed lines sit under the same `#if`/`#ifdef` condition (found by tree-sitter's enclosing
   preprocessor conditional). Text: "both matter only on Windows builds".
4. **Same place.** Their files share a folder below the workspace root that holds no other thread's files. Text: "both
   live under `src/util/win32`".
5. **Only bundled.** None of the above; they share a CL, an author or only the review. Text: "nothing besides
   arriving in CL 11/13". This raises an Ask the author check (§7.1).

Each connection keeps the facts behind it (node ids, file paths, CLs) for the strong model's citations (§9) and for
the tooltip. Direct code links never appear here: they already merged the stories into one thread.

**What is shown.** Every pair whose strongest connection is 1–4, plus every thread whose only connections are 5 (one
"only bundled" arc to the thread it is nearest by folder). A pair joined only through a third thread at the same or
stronger kind is left out. With 6 threads this keeps the drawing to about 6–8 arcs.

### 4.4 Reading order

- **Within a thread:** stories in "defines before uses" order (a topological order of §4.1's directions); ties by
  number of changed functions, larger first.
- **Threads:** by open hazards, then open checks, then number of changed functions. Tests last.
- Each story after the first in a thread carries its reason: "← uses 1", "← calls 1".

This order drives the overview, the rail and the story page's ‹ › buttons. Story ids (S1…) are unchanged; positions
are shown as "1 of 3" within the thread.

## 5. The overview (layout B)

Two columns: understanding on the left, a pinned right column. Header: the review title, the headline (§5.4), CL and
file counts.

### 5.1 Left column

1. **The change as a whole** — 2–4 sentences (§9).
2. **How the threads connect** — threads listed once down the left as coloured boxes (with their open-check count);
   an arc joins each shown pair (§4.3) with its text beside the arc; a dashed arc in the accent colour for "only
   bundled → ask the author". Pointing at an arc highlights both threads. One thread: the tile is replaced by "One
   thread: all stories are connected by calls or shared data."
3. **Threads** — each thread: name, CLs, open-check count, purpose sentence; its stories in reading order with their
   reason; the Tests row last: "Tests: 6 cover threads A and B · nothing tests C".

### 5.2 Right column (pinned while scrolling)

1. **To check** — the review-wide list (§7), grouped by thread, open items first, with counts in the tile header
   ("5 open").
2. **Build impact** — headers whose changes reach many files, as "`git2/common.h` macro change → 713 files rebuild"
   and, when no behaviour change was found, "No behaviour change found." Header fan-out findings move here.
3. **Coverage** — parse quality and limits: degraded parses and how many calls and field accesses tree-sitter added,
   tree-sitter fallbacks, capped fan-in ("140 callers of `git_buf_puts`, 20 checked"), files outside the compile
   database.

### 5.3 What leaves the home page

The intent paragraph built from detector output, "Why it is high risk", the clusters-by-layer map (moves to the
Index), the side-effect files list (its content becomes Unchanged reader and contract rows), the separate drift
section (drift becomes a Coverage line). The discussion stays at the bottom of the left column.

### 5.4 Headline

- With tier-1 verdicts: "N hazards" (red) if any open; else "N to confirm" (amber) if any open; else "No hazards
  found" (neutral).
- Rules only: the detectors' top severity, labelled "rules only".
- Build impact and parse problems never raise the headline. The Reviews list shows the same headline.

## 6. The story page (layout B)

Header: thread crumb ("Thread A › Reftable options · story 1 of 3 ‹ ›"), title, the story's open hazard count, CL
contribution chips ("CL 11 · 14 functions", "CL 12 · 4 functions"), build targets when the review spans more than one.

### 6.1 Left column

1. **What it does** — the story's purpose (tier 1) or a fixed sentence from its main contract change, then its place
   in the thread: "Stories 2 and 3 build on this." / "Uses what story 1 adds."
2. **Before → after** and **Where**, side by side:
   - Before → after: contract rows (§8.1), repeated edits folded with "show N", body-only changes as a count.
   - Where: folder › file › functions, each function with its edit size and CL; clicking opens the diff in the side
     panel; a file edited in several CLs shows each function's CL.
3. **Call paths** — every path the analysis found (§8.2), ranked, grouped under their entry point, each with one line
   saying what changes for whoever runs it; "Graph view" (the existing story graph).

### 6.2 Right column (pinned)

**To check** for this story (§7), open items first, "3 of 5 open" in the tile header.

### 6.3 Below the tiles

- **Code** — per-function diffs in reading order (definitions first); repeated edits as one example diff plus the list
  of places it was applied.
- **Questions and comments** — tier 1's open questions, then the story's comment thread.

Mechanical and tests stories use the same frame: a mechanical story shows the repeated edit and its places; a tests
story shows which threads its tests exercise, what each test checks and the changed functions with no test.

### 6.4 What leaves the story page

The column of per-function cards, the separate checks and "why" blocks (folded into What it does and To check), the
flow strip (replaced by Call paths).

## 7. To check

### 7.1 Kinds

| Order | Kind | Source |
|---|---|---|
| 1 | Hazard | tier-1 verdict `hazard` |
| 2 | Confirm | tier-1 verdict `needs_review` |
| 3 | Caller not updated | signature facts: call site "not updated" |
| 4 | Result handled the old way | returns facts: caller ignores the result, or compares only with values that existed before |
| 5 | Unchanged reader | field facts: a reader of a field the change now writes, in a function the change did not touch |
| 6 | Other build target | a call site or including file compiled only in another target |
| 7 | No test touched | a changed function no test file calls (symbol index callers in test files) and no test file in the change mentions; only when the workspace has test code, otherwise Coverage says "No test code found in the workspace" |
| 8 | Not analysed | capped fan-in; call sites outside any compile database |
| 9 | Ask the author | a thread connected only by "only bundled" (§4.3) |

Kinds 3–9 are computed by the analysis. A finding tier 1 judged `no_hazard` does not appear; the tile ends with "N
checks found no hazard" which opens them with their reasons. Rules only: kinds 1–2 are absent and the tile says
"Risks judged by rules only"; findings of severity high or medium appear as Confirm rows with the detector's title,
except header fan-out findings, which belong to Build impact (§5.2).

### 7.2 Rows

Each row: the kind tag, one line of text, the place (`file:line` in `function`, workspace-relative) and the source line
in monospace; buttons **Looks fine**, **Comment** (a comment thread anchored to the check), **Open** (the code in the
side panel). Two kinds at the same place merge into one row listing both reasons. A marked row shows who marked it
and when, greyed, below the open rows.

### 7.3 Where checks live

Each check belongs to the story whose changed function it concerns (the changed callee, the field's writer, the
function without a test); Ask the author belongs to its thread. The overview lists all checks by thread; the rail
shows each thread's open count. Checks with no story (a header seen only in another target) appear only in the
overview's list, under "Across the change".

### 7.4 Keys and marks

- Key: kind, the place's workspace-relative file and function, and the related changed function's qualified name.
  Line numbers are not in the key.
- Marks are stored per review on the server (§10.3) and shared by everyone viewing the review, like comments.
- A re-run keeps marks whose key is found again; a mark whose key is gone is dropped. If the source line text at the
  place changed since the mark, the check reopens with "changed since marked".

### 7.5 Honest limits

When fan-in was capped or files were outside the compile database, the list says how much it did not check (a Not
analysed row), rather than looking complete.

## 8. Story facts (analysis, no AI)

### 8.1 Contract rows

From the diff map, the facts and repeated-edit detection, per story:

- **Signature**: before and after, the differing part marked.
- **Return values**: values added and removed (names where known: `GIT_EEXISTS (-4)`).
- **Fields**: now written, no longer written.
- **Repeated edit**: one row for a substitution explaining at least two functions ("12 signatures gained `const
  struct reftable_stack_options *opts`"), expandable to the list.
- **Body only**: a count of functions whose only change is inside the body, expandable.

### 8.2 Call paths

Every path ending at the story's changed functions, with no cap on how many. They are ranked: paths that carry a
contract or state flow first, then paths that start at an entry point, then the rest; paths sharing an entry point
are grouped under it. A path longer than four steps keeps its first step and its last two, with "…" between (the
folded steps open on click). Each path's line comes from the flow's effect text where one exists, else a fixed sentence ("calls
`reftable_new_stack`, whose signature changed").

## 9. AI text

One tier-1 call per review, after the analysis in §4–§8, writes:

- each thread's name (at most 6 words) and purpose (one sentence),
- "The change as a whole" (2–4 sentences),
- each connection's text may be reworded but must keep its cited fact.

It is given the threads with their stories' titles and purposes, the connections with their facts, the CL
descriptions marked as hints, and the open checks' counts. It may only state what those support; when the only tie
between threads is "only bundled" it must say so. Answers are checked like tier 1's stories (every cited id must be
in the input; otherwise the fixed text stays). The call counts against `llm.budget.tier1_per_review` under purpose
`threads`.

Without a strong model, or when the call fails: thread names come from the defining story's main changed function and
its folder ("`reftable_new_stack` in deps/reftable"); purposes are the defining story's summary; the whole is a fixed
sentence from the strongest connections ("3 threads: A and B meet in `git_repository_open`; B and C are Windows-only;
A and C share only their CLs").

## 10. Data and API

### 10.1 Models (backend `reading.py`)

- `StoryLink(a, b, strength, kind, defines, text, facts)`.
- `Thread(id, name, purpose, text_source, stories, cls, open_checks)`.
- `Connection(a, b, kind, text, facts, shown)`.
- `Check(key, kind, story, thread, path, line, function, node, text, source_line, finding, cites, also)`.
- `StoryReading(story, contracts, where, paths, checks, place_text)`.
- `Reading(whole, whole_source, threads, connections, order, reasons, build_impact, coverage, headline)`.

### 10.2 Pipeline

New stage `reading` after `llm`, depending on `board`: the stories are built in the `board` stage and the `llm`
stage retitles the rules' stories, so `reading` sees the titles the reader sees. It runs when `review` or `llm` is
degraded or skipped, and uses tier 1's verdicts when present. It stores blobs `reading` and `story_reading:<sid>`. `STORY_RULES_VERSION` is unchanged; a
`READING_VERSION` keys the cached thread text.

### 10.3 Store

Table `check_marks(review_id, key, user, at, source_line, PRIMARY KEY(review_id, key))`. Comments gain anchor kind
`check` (anchor `{key}`).

### 10.4 API

- `GET /api/reviews/{id}/reading` → `Reading` plus the marks.
- `GET /api/reviews/{id}/stories/{sid}` adds `reading: StoryReading`.
- `POST /api/reviews/{id}/checks/{key}/mark` and `DELETE` the same: any signed-in viewer; the response is the mark.
- Reviews list items gain `headline`.

## 11. Rail and navigation

- Rail: Overview; each thread (name, open checks) with its stories in reading order; Tests; a divider; Possibly
  missed (the review-wide To check); **Index** (opens CLs, Files, Checks and Map as tabs).
- Old addresses keep working: a finding opens its story with the check row highlighted (or the overview's list when it
  has no story); a cluster opens the Map tab with the cluster selected; CL, file and node addresses open as today.
- Phone: To check comes first on both pages, collapsed to its counts; the other tiles follow in one column; the
  connection arcs become the sentence rows (one per connection).

## 12. Clean-up rules

Applied in every view and AI prompt:

- Paths are workspace-relative; no Python reprs; evidence is rewritten as sentences or lists.
- Counts carry meaning; an empty count is never shown ("0 flows").
- One colour scale for check kinds; the AI label only on AI-written text; no pill for a missing value.
- Compact rows instead of cards; a summary line first, details on expand.

## 13. Testing

- Backend unit tests: story links (calls, data, file, CL, direction); threads; each connection kind and the shown-pair
  rule; reading order; contract rows; call-path folding; each check kind, merging and keys; marks kept, dropped and
  reopened across a re-run; the headline; the thread-text checks and the fixed-text fallback.
- Fixture: a multi-CL e2e review with two features joined by a shared caller, one feature connected only by its CL,
  a caller left behind and a field reader left behind (the bundled fixture has no test code, so No test touched is
  covered by unit tests).
- Playwright: overview and story page on desktop and phone; arcs; marking a check and seeing it after a re-run; old
  finding and cluster addresses.
- Lab: review 19 with and without the strong model; the owner's work review when the branch is ready.

## 14. Phase 2 (specified in 2026-10-07-review-reading-phase2-design.md)

- CLs as a sequence: the combined diff by default with each hunk tagged by its CL; per-CL filtering.
- Stacked CLs: a flag when a later CL changes lines an earlier CL in the review added; each story says the order to
  read its CLs in.
- A reading plan with progress ticks per story and per check, saved per reviewer.

## 15. Out of scope

- Changing how stories are formed (pieces, tier 1, rules fallback), the detectors or tier 1's verdicts.
- Config keys as a shared-vocabulary connection (no reliable way to recognise them across codebases yet).
- Editing threads or stories by hand.
