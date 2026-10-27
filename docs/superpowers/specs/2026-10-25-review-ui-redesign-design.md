# Flow groups, thread sections, quieter AI marks — design

Owner feedback 2026-10-24, designed with mockups in conversation on 2026-10-24 and 2026-10-25:

1. There is too much AI badging, everywhere; it distracts.
2. The eyebrow headings are not helpful; they blend into the background.
3. The divisions are good, but moving around is still too hard and the pages are still cluttered.
4. The overview needs a clearer division of the threads, with "Thread A", "Thread B" written out in the list.
5. Opening a thread, a story with many flows (30 on large changes) is a wall of text: the reader feels lost and does
   not know how to use it.

The owner's clarification on item 1: **AI-written text always stays visible; the labels marking it as AI are the
problem.**

Owner decisions:

- AI marks: **no chips**. AI paragraphs get a thin, faint violet left edge; hovering says it was written by AI.
  Explain and Ask become one small menu. The AI budget pill shows only near its limit.
- Flows: **grouped by what changed** (the field a flow's writer now writes, or the changed function it calls), each
  group listing its flows as **one-line rows** that open in place and can be ticked, with J/K/F keys.
- Overview: **one section per thread**, headed "Thread A …", with the section headers' counts lined up in
  **table columns** (Stories, Open, Read).
- Outline: an **accordion** — only the current thread open — with the other threads' bars **pinned** so they never
  scroll away.
- Header, headings and AI text: as proposed in the mockups (one quiet header row with a ⋯ menu; dark, sentence-case
  headings that carry the point; faint AI edge).

The work lands in three phases on one branch, each ending with a green suite: **phase 1** §1–§4 (shared pieces,
header, headings, AI marks), **phase 2** §5–§6 (overview, outline), **phase 3** §7–§8 (Flows tab, its one backend
change). §9 is the testing, §10 what is left out.

Examples below use the public libgit2 scratch review ("perf big") and the demo fixture.

## 1. Shared pieces

### 1.1 AI text

Two components replace every `ai-label` chip (§4):

- **`AiText`** (block): wraps a paragraph, list item or box of AI-written text. It draws a 2px left edge in
  `--ai-edge` with 10px padding to its left, carries a `title` (§1.2), and starts with visually hidden text
  `Written by AI. ` (class `vh`) so screen readers hear the mark. It renders as the element it replaces (`p`, `li`,
  `div`).
- **`AiName`** (inline): for AI-written titles and names shown as headings (a story page's title, a thread's name on
  the overview). No edge; the same `title`, and visually hidden `Written by AI: ` before the text. Outline rows and
  other navigation lists carry no AI mark at all.

New colour token, in both themes' blocks of `styles.css`: `--ai-edge: #ddd3fb` (light), `--ai-edge: #4f4378` (dark).

### 1.2 The hover text

`Written by AI`, followed by ` · <model>` only where the app knows which model wrote that text:

- a story's title, purpose, suggested checks and questions when `story.source === "tier1"`: the strong model's name
  (`AiView.strong`), when set;
- a file summary: its `by`.

Everywhere else it is `Written by AI`. (Recording which model wrote each text is out of scope, §10.)

### 1.3 Section headings

One heading style replaces the grey capitals (§3): sentence case, `color: var(--ink)`, `font-weight: 650`, no
`text-transform`, no `letter-spacing`; 16px for `h2`, 15px for `h3` and `h4`; 20px above, 6px below.

## 2. Header

### 2.1 The row

One row, in this order:

1. ☰ (phone and narrow screens), as today.
2. The review title, as today.
3. The risk pill: `HeadlinePill` without the visible ` · rules only`; its `title` keeps saying "Judged by the
   detectors' rules, without the strong model". A review without a reading keeps today's `RISK` pill.
4. The progress line, with **checks** for causes: `0 of 21 stories read · 56 checks open`; `1 check open`;
   `every check done` as today.
5. **Next open check ›**, as today.
6. The status pill while the analysis runs, as today.
7. The AI pill, **only** when AI is configured and `used >= 0.9 × budget` (today's red threshold); it keeps its
   look and its usage panel.
8. The **⋯** button (§2.2), right-aligned.

Gone from the row: the `?` button, Re-run, Re-run stories (fresh), the drift pill, the stage notes, and the AI pill
below 90%. Each moves into the menu.

### 2.2 The ⋯ menu

A button with `aria-label="Review menu"`, `aria-haspopup="menu"` and `aria-expanded`. It opens a menu of these items,
each shown only when it applies, in this order:

| Item | Shown when | Does |
|---|---|---|
| `Workspace drift · N` | drift lines exist | opens a panel listing the drift lines (today's pill tooltip) |
| `Stage notes · N` | a stage failed or degraded | opens the notes (today's `<details>` banners) |
| `AI calls used · X of Y` | AI is configured | opens the AI usage panel (today's pill popover) |
| `How to read this page` | the review has a reading | opens today's `HowToRead` help |
| `Re-run` | the viewer is the owner and the review is ready | as today's button |
| `Re-run stories, fresh` | as Re-run, and a strong model is configured | as today's button, same `title` |

- An **amber dot** (`--warn`) sits on ⋯ when drift lines exist or a stage **failed** (degraded stages alone do not
  light it). The button's accessible name then adds what needs attention, e.g. `Review menu (workspace drift)`.
- Escape or a click outside closes the menu and the panels it opened; Escape returns focus to ⋯.
- The AI usage panel opens from the menu, from the near-limit pill, and from **Raise budget** in an Explain error
  (`ai.setUsageOpen(true)`); it renders under the header's right end whichever opened it. It takes focus when it opens;
  Escape or Close returns focus to whatever opened it (the ⋯ button, the AI pill, or a Raise budget link), or to ⋯ when
  that opener is gone.
- `HowToRead` gains one line: "A faint violet line at the left of a paragraph marks text the AI wrote."

## 3. Headings

The §1.3 style applies to these selectors (today: 12–13px uppercase, `--muted`, letter-spaced):

`.ws-whole h2` · `.ws-finding h3` · `.ws-steps h3` · `.ws-nb-col h3` · `.ws-tree-sec h3` · global `h4` · `.ws-sec-t` ·
`.rv-head h2` · `.ov-band h3`

Words change only where this design says so: the overview's headings (§5) and the finding page's `AI analysis`,
which becomes `Analysis`. The graph's and board's micro-labels (`.bd-tag`, `.bd-blabel`, node kind labels, toolbar
labels, `.bd-layer-thread .m`, `.bd-ann .k`, `.ws-file-tools .act`) are unchanged.

## 4. AI marks

Every site, before and after. "Edge" is `AiText`, "name" is `AiName`.

| Where | Today | After |
|---|---|---|
| Overview thread name, thread intro (`Overview.tsx`) | `AI` chip before each | name; intro: edge |
| Overview lead (`Overview.tsx`), old-review intent (`WholePage.tsx`) | `AI` chip | edge |
| Overview connection lines (`Overview.tsx`) | no mark | the connection's words in edge when the strong model reworded them (`text_source === "llm"`); `With Thread A: ` and ` — ask the author` stay outside it |
| Story title (`StoryPage.tsx`, both headers) | `AI` chip | name |
| Story purpose or summary (`StoryPage.tsx`) | `AI` chip | edge |
| Flow paragraph (`StoryTabs.tsx`) | `AI` chip per flow | edge (§7.3) |
| What it means for the rest (`StoryTabs.tsx`) | `AI` chip | edge |
| Talk questions (`StoryTabs.tsx`) | `AI` chip per question | edge per question |
| "The strong model also suggests" (`StoryTabs.tsx`) | `h4` with `AI` chip | `h4` "Also worth checking"; its list: edge |
| Flow strip what, reason (`FlowStrip.tsx`) | `AI` chip; `AI: <reason>` | edge; `<reason>` in edge |
| Finding verdict, header (`FindingBody.tsx`) | `AI` chip, `AI review: <verdict> — …` | `Hazard — …`, `Needs review — …`, `No hazard — …`, in edge |
| Finding verdict, status line (`FindingBody.tsx`) | `AI` chip, `AI: hazard — …`, `AI: no clear hazard — …` | `Hazard — …`, `No clear hazard — …`, in edge |
| Finding not yet assessed (`FindingBody.tsx`) | `…; ✦ Explain asks the AI whether this one is a hazard.` | `…; Explain asks whether this one is a hazard.` |
| Finding analysis (`FindingBody.tsx`) | `h3` `AI analysis`; `AI` chip on the explanation; `Checking for AI analysis…`; `AI analysis unavailable.` | `h3` `Analysis`; the explanation in edge; `Checking for an analysis…`; `No analysis: AI is not set up.` |
| Finding hypotheses (`FindingBody.tsx`) | `AI` chip each | edge each |
| Finding Verify steps (`FindingBody.tsx`) | no mark (the model writes them in the same call as the analysis; no rule does) | edge each |
| Tortoise reply (`Comments.tsx`) | mascot, `tortoise`, `AI` chip | mascot and `tortoise` (name keeps its colour); body: edge, except a reply the app writes itself on an error (its `meta.error` is set: "I stopped…", "I couldn't answer…", budget spent), which is plain, with no edge |
| @ menu (`Comments.tsx`) | logo, `@tortoise`, `AI` chip, its detail | logo, `@tortoise`, its detail; no chip |
| File summary (`Explain.tsx`) | box with 3px edge, `AI` chip, `summary by <model>` | box in edge (§1.1), heading `Summary`, hover `Written by AI · <model>` |
| ✦ Explain and Ask… (`Explain.tsx`, every caller) | a pill button and a link | one `Explain ▾` menu (§4.1) |
| Header AI pill (`AiPill.tsx`) | always | near the limit only (§2.1) |
| Risk pill (`HeadlinePill.tsx`, header and Reviews page) | ` · rules only` | hover only |
| Re-run stories (fresh) (`Workspace.tsx`) | header button | ⋯ menu (§2.2) |

Unchanged: status lines that say what the AI is doing (`thinking… (round r of n)`, `read: a.c`), **Raise budget**,
the Coverage line "Risks judged by rules only.", and the Unsorted story's explanation.

### 4.1 The Explain menu

`Explain ▾` is a small button opening a menu of:

- `Explain` — or `Explain again` when the item has an AI result (with today's replace confirmation), or the caller's
  label (`Summarise`, `Summarise again`); disabled with `Explaining…`/`Summarising…` while its job runs;
- `Ask a question…` — when the caller allows Ask; opens today's question box below the button.

When the item allows only Ask (`askOnly`), the button is `Ask…` and opens the box directly. Errors, the sent note and
**Raise budget** show beside the button as today. With AI not configured nothing renders, as today.

## 5. Overview

### 5.1 Top

- An `h2` counting the threads: `5 threads`, `1 thread`; with no threads, `The change`.
- The reading's `whole` (in edge when `whole_source === "llm"`).
- The start button: before any story is read, `Start with Thread A ›` naming the thread of the first unread story in
  reading order (`Start here ›` when that story is in no thread); once one is read, `Continue ›`; all read: "You've
  read every story." as today.

Removed: the headings "The change as a whole" and "Threads", and the section "How the threads connect" (§5.3).

### 5.2 Thread sections

Above the first section, a row of column labels `Stories`, `Open`, `Read` (`aria-hidden`), lined up with the
counts in every section header. Header and label row share one grid template, e.g.
`grid-template-columns: auto auto 1fr 72px 72px 72px auto`.

Each thread is a `section` labelled `Thread A: <name>`:

- **Header bar** (background `--gap-bg`, bottom border `--line`): the letter tile; `Thread A` in bold; the name
  (`Ticks`; an `AiName` when the thread's `text_source === "llm"`); the counts — stories, open (shown causes of the
  thread still open; `—` on a reading without causes), read (stories of the thread the viewer has read); and one
  action: `Start ›` (to its first story) when none is read, `Continue ›` (to its first unread story) when some are,
  the text `All read ✓` when all are. Each count carries visually hidden words: `15 stories, 52 open, 0 read`.
- **Intro**: `cardText(t)`, AI paragraphs in edge, clamped to 3 lines with the full text as `title`, as today.
- **Stories**: the first 4, numbered by position in the thread, each a link with its title (`Ticks`), `N open` when
  it has open checks, and `✓` when read. More than 4: `Show the other N stories ▸`, which shows the rest in place
  and becomes `Show fewer ▴` (not remembered).
- **Connections**: every shown connection whose later thread (in thread order) is this one, one line each:
  `With Thread A: <connection text>` (the text in edge when the strong model reworded it), adding ` — ask the author`
  for a bundled one.

Below 640px of the overview's own width (a container query on the overview, not on the window) the header wraps: the
counts move under the name as `15 stories · 52 open · 0 read`, and the column label row is hidden. So a window just
over 640px wide gets the wrapped header, because the page's margins leave the overview itself narrower than 640px
there; so does a wider window with a panel open beside the overview, or the outline dragged wide.

### 5.3 After the threads

- The tests line, as today.
- Three folded rows (`details`), each summary a heading in the §1.3 style:
  - `Build impact · up to N files rebuild` (N: the largest `files` of `build_impact`), opening today's list; absent
    when there is none;
  - `Coverage · N notes` (N: coverage lines, plus one for rules only, plus one for shared sinks), opening today's
    list; absent when N is 0;
  - `Discussion · N comments` (N: top-level review and chapter comments) or `Discussion · no comments yet`, opening
    today's discussion.

## 6. Outline (Stories view)

- `⌂ Overview` at the top, **without** the risk pill (the header has it).
- **One bar per thread**, a `button` with `aria-expanded`: the letter tile, `Thread A`, the name (one line,
  ellipsis), its open count, `0 of 15` read, and ▸/▾. Fixed height (36px).
- **One thread open at a time.** It is the thread holding the current story; on any other page, the thread the
  viewer last opened in this review (kept per review under `ct.ws.<review id>.thread`), else none. Clicking a closed
  bar opens it and closes the open one; clicking the open bar closes it. Going to a story opens its thread.
- **The open thread's stories**: today's rows (read tick, title, open count, reason line), each numbered by its
  position in the thread. Under the current story, its flow groups (§7.6).
- **Pinned bars**: bars before the open thread are `position: sticky` at the top of the outline's scroll area
  (`top: i × 36px`), bars after it at the bottom (`bottom: j × 36px`, counting from the last), so every thread stays
  one click away however long the open list is.
- Tests and the Index stay at the end; the Checks view is unchanged apart from §3. On a phone the outline is the same
  inside its drawer.

## 7. Flows tab

### 7.1 Groups

A pure function groups the story's flows (in the story's order):

- a **state** flow by its field: the node before its landing, `path[path.length − 2]`, when the path has two nodes
  or more and that node is not the flow's `cause` (the backend puts the field there, `board.py` `build_flows`);
  without one, by its writer (`cause`);
- a **contract** flow by its changed function (`cause`).

Groups are ordered by their first flow's position; rows keep the story's order. A flow is numbered by its 1-based
position in the story's list, as `flow=N` addresses and the Graph tab number it.

### 7.2 Group header

- **Title**:
  - field group: `` `F` gets new writers: `W1`, `W2` `` — the group's distinct writers in order of first
    appearance, `and N more` past three; one writer: `` `F` gets a new writer: `W1` ``;
  - writer group (field unknown): `` New writes by `W` ``;
  - function group: `` `C`'s signature changed `` when every row's flow ends in `signature changed`, `` `C` returns
    new values `` when every row ends in `ignored` or `unhandled`, else `` `C` changed `` (the tail after `⟶` in the
    flow's `text`).
- **Line under it**: `` read by `R1`, `R2` and N more · K flows · J open `` (field and writer groups; readers are the
  distinct landings) or `` called by `L1`, `L2` and N more · K flows · J open `` (function groups); `J open` is left
  out when J is 0.
- **Chips**: the group's causes (§7.4), as today's chips (a chip opens the stepper at its first open place).

### 7.3 Rows

- **One line**: a tick box when the flow has places (§7.5), its number, and its sentence with names in code style:
  state `` `R` sees a new writer of `F` · via `W` ``; contract: the flow's `title` with its landing in code style.
  It ends in an ellipsis when too long.
- Click or Enter **opens the row in place** (`aria-expanded`); open, it shows:
  - the path, labels joined by ` → `, the field highlighted;
  - the account section for the flow (`flowPart`), else the flow's `what`, in edge when written by AI;
  - `Check ` + the flow's `check` (e.g. "Check whether `hash_partially` assumes `git_indexer::trailer` only changes
    the way it did before");
  - a flow with no places: the chips of the causes whose `flows` include it;
  - **Looks fine** when it has open places (marks them all, as the stepper's Looks fine), **Reopen** when all its
    places are marked (unmarks them), and **Next flow ›** (closes it and opens the next row).
- **The tick box** is checked when every place of the flow is marked and unchanged; clicking it marks all its open
  places, or unmarks all when checked. Accessible name: `Looks fine: <sentence>`.
- **Folding**: a group with more than 8 rows shows 8 and `Show N more`; a link to a hidden row unfolds its group. The end
  line (§7.7) folds the same way.
- **Keys**, on the Flows tab, when no cause is open in the side panel and focus is not in a text field: **J** next
  row, **K** previous row (focus moves and the row scrolls into view), **Enter** opens or closes the focused row,
  **F** marks the focused row's open places fine and moves to the next row with open places. While a cause is open in
  the side panel, J, K and F stay the stepper's, as today. `HowToRead` lists these keys.
- **Address**: `flow=N` opens row N, unfolds its group and scrolls it into view (today it lights a card).

### 7.4 A group's causes

A pure function sorts the story's shown causes (hidden kinds left out) between the groups and the end line (§7.7):

- `reader`: the field group whose field label equals the `field` of its places' checks; when two field groups carry the
  same label, the one one of whose rows lands where one of the cause's checks is, else the first;
- `caller`, `result`, `target`, `unanalysed`: the function group whose function is its places' checks' `related`
  (§8); on a reading without `related`, the first function group among the groups holding the cause's `flows`, taking the
  flows in order, else the end line;
- `hazard`, `confirm`: the first group holding a flow whose `findings` include the cause's `finding`;
- anything else, and a cause no group takes: the end line.

So a writer with no path in the story (e.g. `indexer_new` writing `git_indexer::trailer`) still shows its checks in
its field's group.

### 7.5 A flow's places

A pure function finds the checks a flow asks about, among the story reading's checks, hidden kinds left out: those
with `related === flow.cause` and `node === flow.lands`, and

- for a state flow: `kind === "reader"`, and the check's `field` equals the field's label when the flow has a field;
- for a contract flow: `kind` in `caller`, `result`, `target`, `unanalysed`.

A flow may have several places (a caller with both a signature and a result check). On a reading without `related`
no flow has places: rows show no tick box and fall back to chips.

### 7.6 In the outline

Under the current story, one row per group instead of one per flow: the field (`` `git_indexer::trailer` ``), the
writer (`` `W`'s writes ``) or the function, then `· K flows`, and its open count. A row opens the Flows tab at the
group's first flow (§7.3 Address).

### 7.7 End of the tab

- `Also in this story:` followed by the chips of the causes §7.4 left for the end line (e.g. "7 functions no test
  calls"); absent when there are none. The end line folds like a group: its first 8 chips, then `Show N more`, which
  shows the rest.
- "What it means for the rest" as today, its text in edge.
- No flows: "No flows in this story." as today.

## 8. Data change

`Check` gains `related: str | None` — the node id of the changed function that raised the row, which the backend
already computes as `cause_fn` but does not send. It is stored in the reading from the next run; a reading stored
before it loads as today and has none (the frontend type gets `related?: string | null`). Nothing else in the
backend changes.

## 9. Testing

- **Unit (vitest)**, for the pure rules: grouping flows (§7.1) and their titles (§7.2); a flow's places (§7.5);
  sorting causes into groups (§7.4); which section shows which connection (§5.2); a thread's counts and its
  Start/Continue/All read action; the start button's label (§5.1); the ⋯ menu's items and its dot (§2.2); the AI
  pill's 90% rule (§2.1); the hover text (§1.2); the progress line's wording (§2.1).
- **Backend (pytest)**: checks carry `related`; a stored reading without it still loads and serves.
- **Playwright** (against the built bundle): update the specs that look for `AI` chips, grey headings, the old
  outline, the overview's old headings or the word "causes"; add:
  - a story with many flows shows groups and rows; J/K/F tick a place; a `flow=N` link opens its row and unfolds its
    group; `Show N more`;
  - overview sections with lined-up counts and `Show the other N stories`;
  - the outline accordion and its pinned bars;
  - the ⋯ menu, its items and its dot;
  - no `.ai-label` anywhere; AI text carries the edge and the hover.
- **Fixtures**: the demo fixture for AI text; the large fixture for many flows — when none of its groups has more
  than 8 flows, a test-only story is added so folding is tested.
- **Phone width (390px)**: overview headers wrap, the outline drawer works, rows stay one line.
- Screenshots after each phase, for the owner.

## 10. Left out

- Recording which model wrote each text (the hover names a model only where §1.2 says).
- Redesigning the Graph tab, the Checks view or the Reviews list (they take §3 and §4 only).
- Pages of reviews run before the reading existed (legacy rail, board page, story steps): §3 and §4 only.
