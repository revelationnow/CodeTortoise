# Review Reading, Phase 2: CLs as a Sequence and a Reading Plan — Design

Date: 2026-10-07. Status: approved by the owner, 2026-10-07. Specifies phase 2 of the review reading design
(2026-10-07-review-reading-design.md §14), whose phase 1 is on main (c9ceb23). Work happens on branch
`review-reading-2`; nothing reaches main until the owner decides.

## 1. Why

Phase 1 made a review read as threads of stories with one To check list. Two problems from the owner's work reviews
remain:

- **The same file edited in several CLs reads as one blur.** A file's side panel shows the combined diff (all CLs) or
  one CL at a time, but in the combined diff nothing says which CL wrote which lines, and nothing says when a later CL
  replaced lines an earlier CL added — so a reviewer reads the earlier version for nothing.
- **A large review has no sense of progress.** Nothing records which stories and checks *I* have read. "Looks fine"
  is shared and means "this check is cleared for everyone", not "I read it".

## 2. Goals and choices

Agreed with the owner, 2026-10-07:

- **Lines carry their CL.** In the combined diff each run of changed lines is tagged with the CL that wrote it; a run
  that replaced an earlier CL's lines says so. In one CL's diff, its lines a later CL replaced are greyed.
- **Rewrites are information, not checks** (owner's choice A). A later CL rewriting or deleting lines an earlier CL in
  the review added is shown in the diff, the story's Where tile and the CL page. It does not add To check rows and does
  not raise the headline.
- **Filtering stays per file** (owner's choice A). The existing per-file CL picker stays; a tag switches its file to
  that CL. No review-wide CL lens.
- **Each story says the order to read its CLs in.**
- **A private reading plan** (owner's choice A). "Read" ticks on stories and checks belong to one signed-in person and
  are seen by nobody else; "Looks fine" stays the shared verdict. The reader ticks a story by hand (owner's choice A).
- **A re-run clears every reader's ticks** (owner's choice C): re-runs are uncommon, and ticks then key on story ids
  and check keys without surviving renumbering.
- **The server works out who wrote each line, once per run** (owner's choice 1); the browser only draws it.

## 3. Vocabulary

- **Wrote:** the CL whose edit produced a line of the final text. A line no CL in the review changed has none.
- **Removed by:** the CL that deleted a line of the base text.
- **Rewrite:** a later CL deleting or replacing lines an earlier CL *in this review* added.
- **Gap:** between two CLs of the review that touch a file, a CL outside the review changed it (the later CL's
  "before" is not the earlier CL's "after").
- **Read:** a reader's private tick on a story or a check.

## 4. Who wrote each line (server)

### 4.1 Input

For each file, its texts in CL order: the base (the first CL's before), then each CL's own before and after
(`FileChange.per_cl`, already stored). A file touched by one CL needs no walk: every changed line is that CL's.

### 4.2 The walk

Every line carries an origin — the base, or (CL, line number in that CL's after text) — and `over`: the earlier CL of
the review whose lines its insertion replaced, if any. For each CL `c` in order:

1. If `c`'s before differs from the previous text, the difference is a **gap**: lines it inserts get no origin (they
   came from outside the review) and the gap `(previous CL, c)` is recorded.
2. Diff `c`'s before against its after (Python `difflib.SequenceMatcher` on lines, `autojunk=False`):
   - lines kept keep their origin;
   - lines inserted get origin `(c, n)`; when they replace (the same `replace` opcode) lines of an earlier review CL
     `a`, their `over` is `a` (the latest such CL when several);
   - a deleted line whose origin is `(a, m)`, with `a` a CL of the review, is a rewrite of CL `a` by `c`, recorded
     against CL `a`'s line `m`;
   - a deleted line from the base is recorded as **removed by** `c` at its base line number.

### 4.3 Output

Per multi-CL file, `FileLines`:

- `wrote: list[int | None]` — for each line of the final text (1-based position = index + 1), the CL that wrote it.
- `over: list[int | None]` — for each line of the final text, the earlier CL whose lines it replaced.
- `removed: list[int | None]` — for each line of the base text, the CL that removed it.
- `rewritten: dict[int, dict[int, int]]` — `rewritten[a][m] = c`: CL `a`'s after-text line `m` was replaced by CL `c`.
- `gaps: list[Gap]`, `Gap {file, after_cl: int, before_cl: int}` — an outside change between review CLs
  `after_cl` and `before_cl`.

Because these are keyed by line number on the final, base and per-CL texts — not by any one diff — the browser's diff
(jsdiff) cannot disagree with them: a `+` row at new line `n` looks up `wrote[n-1]`, a `−` row at old line `o` looks up
`removed[o-1]`; a row whose lookup is None gets no tag.

For the review: `Rewrite {by: int, of: int, file: str, function: str | None, lines: int, line: int | None}`, one per
(file, by, of, function). `lines` counts CL `of`'s lines that CL `by` replaced or deleted. `line` is the first final-text
line CL `by` wrote in their place, and `function` the function holding it by the after facts' ranges; when CL `by` only
deleted them, or its lines did not survive to the final text, `line` and `function` are None and the text reads "in
`logger.c`".

### 4.4 A story's CL order

A story's CLs (`Story.cls`) are read in CL number order — the review's sequence; rewrites only ever go from an earlier
CL to a later one, so that order never contradicts them. The story's reading carries `cl_order` and the rewrites whose
`function` is one of its changed functions (or whose file holds its code when `function` is None).

### 4.5 Honest limits

- A line moved by a CL counts as deleted and inserted: it is tagged with the moving CL.
- Lines inserted across a gap carry no tag.
- A CL that only reverts an earlier CL's lines shows as a rewrite of them.

## 5. CLs as a sequence (browser)

### 5.1 The combined diff ("All CLs", still the default)

- Each run of consecutive changed rows with one CL (and, for added rows, one `over`) gets a chip at its first row:
  **CL 102**, or **CL 103 · rewrites CL 101** when `over` is set.
- Removed rows carry the CL that removed them; unchanged rows and rows with no origin get no chip.
- Clicking a chip switches that file's CL picker to that CL (`All CLs` returns). In side-by-side mode a chip sits on
  the side holding its row.
- Single-CL files show no chips (the file header already names its CL).

### 5.2 One CL's diff

As today (that CL's before → after). Its added lines a later CL replaced (`rewritten[cl]`) are greyed with a chip
**rewritten in CL 103**; clicking it switches to CL 103.

### 5.3 The story's Where tile

- Files grouped under their CL in reading order: "CL 101 · 2 files", "CL 103 · 1 file". A file edited by several of
  the story's CLs is listed once, under its first, with chips for the others ("also CL 103").
- Above the groups, when the story has more than one CL: "Read CL 101, then CL 103".
- Below it, each of the story's rewrites: "CL 103 rewrites 5 lines CL 101 added in `uart_send`"; the function name
  (or the file name when there is none) opens the file at `line`, in the combined diff.

### 5.4 The CL page

A "Rewrites" section with both directions — "rewrites lines CL 101 added: `uart_send` (5 lines)" and "lines it added
are rewritten by CL 103: `uart_send` (5 lines)" — and, when the CL has a gap, "`logger.c`: a CL outside this review
changed it between CL 103 and CL 105". No section when there is nothing to say.

### 5.5 Not changed

To check, the headline, the overview's tiles and the rail's order. On a phone, chips read "102" and stay tappable.

## 6. The reading plan (browser and server)

### 6.1 What is ticked

Stories in the reading's `order`, and the reading's To check rows (`checks`, open and marked; not the cleared "no
hazard" rows). A tick belongs to one signed-in user and one review; nobody else sees it. Several people sharing one
login share ticks — a limit of the staged security set-up (no per-viewer identity beyond the login).

### 6.2 Story page

- Beside ‹ › a **Mark as read** button. Pressing it ticks the story and goes to the next story in reading order the
  reader has not read, wrapping to the start; when every story is read, to the overview, whose header then says
  "You've read every story".
- A read story shows **✓ Read · Mark unread** there instead.
- ‹ › still step through every story.

### 6.3 To check rows

- Each row gets a small **Read** checkbox beside Looks fine.
- Looks fine also ticks the row read for the person marking it; undoing the mark leaves the tick.
- A row the reader has read is slightly dimmed for that reader only; it stays listed and stays open until someone
  marks it Looks fine.

### 6.4 Progress

- **Header**, beside the headline: "7 of 12 stories read · 18 of 30 checks" (hidden on a phone until the header is
  opened).
- **Rail:** ✓ beside each read story; each thread's heading "2 of 3".
- **Overview:** each thread card "2 of 3 read".

### 6.5 Re-run and old reviews

- Starting a run clears every reader's ticks for that review (the header then reads "0 of 12 stories read").
- A review without a reading (run before phase 1) has no reading plan: no buttons, boxes or counts.

## 7. Data and API

### 7.1 Backend `sequence.py` (new)

- `FileLines`, `Rewrite` (pydantic, §4.3).
- `walk(fc: FileChange) -> FileLines`.
- `rewrites(lines: dict[str, FileLines], fns: list[Function]) -> list[Rewrite]`, naming functions by the after
  facts' ranges (§4.3).

### 7.2 Models (`reading.py`)

- `Reading.rewrites: list[Rewrite]`, `Reading.gaps: list[Gap]`.
- `StoryReading.cl_order: list[int]`, `StoryReading.rewrites: list[Rewrite]`.
- The `lines` blob: depot path → `FileLines`, for files touched by more than one CL of the review.

### 7.3 Pipeline

The reading stage runs the walk for each multi-CL file and stores `lines` together with `reading`, `reading_head` and
`story_reading:*` (one `replace_blobs`); a run that builds no reading drops it with them. `run_review` clears the
review's ticks when it starts.

### 7.4 Store

Table `read_ticks(review_id, user, kind, key, at)`, primary key `(review_id, user, kind, key)`, kind `story` or `check`
(`CREATE TABLE IF NOT EXISTS`). `set_tick`, `clear_tick`, `list_ticks(rid, user)`, `clear_ticks(rid)`.

### 7.5 API

- `GET /api/reviews/{rid}/files`: each multi-CL file gains `lines` (its `FileLines`); others are unchanged.
- `GET /api/reviews/{rid}/ticks` → `{stories: [...], checks: [...]}` for the signed-in user; `{stories: [], checks:
  []}` for a review without a reading.
- `PUT` and `DELETE /api/reviews/{rid}/ticks/{kind}/{key:path}`: the key must name a story in the reading's order or a
  check in its `checks`, else 404 ("That story or check is not in this review's reading."); kind must be `story` or
  `check`, else 422.
- `POST …/checks/{key}/mark` also sets the marking user's check tick.

### 7.6 Frontend

- `reading/sequence.ts`: chip runs from a file's `lines` and its diff rows; greyed rows of one CL (pure, vitest).
- `reading/plan.ts`: next unread story, progress counts, a thread's "n of m" (pure, vitest).
- `FileDiff` and `CodeView`: chips and greyed rows. `StoryTiles` Where: CL groups, reading line, rewrites. `ClPage`:
  Rewrites and gaps. Story header: Mark as read. `CheckRow`: Read box. `Rail`, `Overview`, header: progress.
  `useReview` loads the ticks and reloads them after each change.

## 8. Testing

- **Python units (`test_sequence.py`):** two CLs adding lines; a later CL rewriting an earlier CL's lines (wrote,
  rewritten, the Rewrite row and its function); a later CL deleting them; a base line removed; a gap from outside the
  review; a single-CL file needing no walk.
- **Fixture:** a new CL 105 ("logger: start at log level 2") rewrites the line CL 103 added in `logger_init`
  (`lg->level = 1;` → `lg->level = 2;`). A review of CLs 103–105 has the rewrite; a review of 103 and 105 has a
  gap (CL 104 between them). Reviews of 101–104 are unchanged.
- **Store and API:** ticks are per user; a re-run clears them; Looks fine ticks the check; an unknown key is a 404; a
  review without a reading has no ticks; `files` carries `lines` only for multi-CL files.
- **Vitest:** `sequence.ts`, `plan.ts`.
- **Playwright:** chips in the combined diff and a chip switching the file to its CL; "rewritten in CL 105" in CL 103's
  diff; Where grouped by CL with the reading line and the rewrite; the CL page's Rewrites and a gap; Mark as read
  moving to the next unread story with the rail ✓ and the header count; a check's Read box; a re-run clearing ticks; a
  second user not seeing the first's ticks; chips on a phone.

## 9. Out of scope

- A review-wide CL lens (owner chose per-file filtering).
- To check rows for rewrites or for CLs that could be submitted alone (owner chose information only).
- Ticks that survive a re-run (owner chose clearing them).
- Showing other reviewers' progress.
