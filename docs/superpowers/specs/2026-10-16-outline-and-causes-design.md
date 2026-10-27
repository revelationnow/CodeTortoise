# Outline layout, checks by cause — design

Owner feedback 2026-10-16, designed with mockups in conversation the same day:

1. Node ids (`N4909`) still show in a story's To check panel.
2. Large reviews lack a coherent path: no clear start or order, no sense of position or of what is left, links
   between flows and stories are hard to see, switching between rail, story, To check and panel loses the place, and
   story pages are long walls of sections.
3. Many Confirm and To check rows make a review noisy; some kinds of check should be off by default and on on demand.
4. The layout as a whole is too cluttered.
5. One change raising many checks (a field's writer changed, 80 readers) is a chore one row at a time; the reviewer
   needs to walk those places with little friction and without flooding the layout.

The reviewer's order on a large review is **understand first, then triage**: walk the change story by story, then
work through what is left to check.

Owner decisions:

- Layout: an **outline** on the left (threads → stories → flows, with counts), the page in the centre, the side panel
  on the right; **no To check column**.
- Checks are grouped **by cause**. A cause's places are walked with a **stepper** in the side panel that always shows
  **the change** that raised the cause above **the place** (split view).
- The outline switches between **Stories** and **Checks**; the top bar has **Next open check ›**.
- **Confirm** is hidden by default; every kind can be hidden or shown.
- The story page's sections become **tabs**: Flows, Before → after, Where, Call paths, Code, Graph, Talk.
- Threads stay as the outline's top level.

Item 1 is fixed by §4.7 (all cause and check text goes through `NameText`).

## 1. The frame

Every review page has the same four parts.

### 1.1 Top bar

One line under the app header, replacing today's review bar:

- the review name (`CLs 201, 202`) and its risk pill (as today);
- one progress line: `3 of 9 stories read · 12 causes open` (hidden kinds left out, §4.6);
- **Next open check ›** (§4.5), shown when a cause is open;
- a **?** button opening "How to read this page" (today's overview section, moved) as a popover;
- for the owner, Re-run and the stage notes, as today.

Progress is shown here only; pages no longer repeat it.

### 1.2 Outline (replaces the rail)

`Outline.tsx` replaces `Rail.tsx`. It keeps the rail's width handle, its fold to a 28px strip on a desktop
(`ct.ws.railFolded`), its drawer on a tablet and a phone, and its scroll position per review.

At its top a two-way switch, **Stories | Checks**. The choice is remembered per browser (`ct.ws.outline`,
`"stories"` | `"checks"`, read and written in try/catch; default `"stories"`).

**Stories view:**

- **Overview** (the whole change), with the risk pill.
- One group per thread: its letter and name, its open-cause count. Under it its stories in reading order, each one
  line: ✓ when this reader has read it, its title (one line, ellipsis, whole title on hover), its open-cause count,
  and today's link note (`← calls 1`).
- The current story is expanded: its flows, numbered, one line each (`1 main → logger_flush`). A flow line opens the
  story's Flows tab scrolled to that flow's card.
- The Tests and Unsorted groups as today.
- **Index** at the bottom, folded by default: CLs, Files, Findings, Map. (Index › Checks is removed, §5.3.)

**Checks view:** §4.4.

### 1.3 Centre

The page (overview §3, story §2, finding, CL, Index tabs). Nothing is pinned beside it.

### 1.4 Side panel

As today (a function's code, a file's diff, a finding, panel tabs, Focus), plus a fourth item, the **cause stepper**
(§4.3). **Focus** now folds the outline only (there is no To check column) and widens the panel; the centre keeps at
least 360px.

### 1.5 Tablet and phone

The outline is the drawer (with its switch), the page is full width, the panel is a full-screen sheet, as today. The
stepper works in the sheet.

## 2. The story page

`StoryPage` keeps its address (`/s/S2`); its body is rebuilt.

### 2.1 Header

- The story's title (wraps).
- One line: `Thread A · story 2 of 4 · after: <title of the story it follows> · feeds: <title of the story it
  feeds>` (the parts that apply; each title a link, one line, ellipsis).
- ‹ › previous and next story in reading order, and **Mark as read** (as today).
- The CL chips, small.

Under it the **summary**: the account's purpose paragraph with the AI label, or, without an account, the story's short
text as today, then its place in its thread (`place_text`).

### 2.2 Tabs

`Flows · Before → after · Where · Call paths · Code · Graph · Talk`, each with its count (flows, contract rows,
files, paths, functions, — , questions + comments). A tab with nothing in it is not shown; Flows always is for a
behaviour story. The open tab is in the address as `?sec=` (`flows` default and left out, `contracts`, `where`,
`paths`, `code`, `graph`, `talk`); `?view=graph` from older links opens the Graph tab. The open tab is part of the
item's memory (`memory.ts`), so returning to a story returns to its tab.

Mechanical, test and unsorted stories have no flows: their current body (`MechanicalStory`, `TestsStory`, the
unsorted reasons) is the first tab, **Changes**; their other tabs follow the same rules.

### 2.3 Flows tab

- One numbered card per flow of the story, in the story's reading order. Heading: the flow's label
  (`main → logger_flush → uart_send`, mono, wraps). Body: the account's section for that flow (AI label), else the
  flow's text (`Flow.what`).
- Under the body, one **chip** per open cause that touches the flow (§4.1 `flows`), shown kinds only (§4.6):
  `80 readers of dev->status` · `1 caller not updated`. A cause whose places are all done shows as a muted chip with
  ✓. Tapping a chip opens the stepper at the cause's first open place.
- After the cards, causes of the story that touch no flow, as chips under "Other checks in this story".
- Then the account's effects section ("What it means for the rest", AI label), when there is one.

### 2.4 Other tabs

- **Before → after**, **Where**, **Call paths**, **Code**: today's tiles' content, unchanged, each alone in its tab.
- **Graph**: today's story graph view.
- **Talk**: the strong model's questions and its suggested checks ("The strong model also suggests"), then the
  story's comment thread.

## 3. The overview page

- **Top**: the change as a whole, one paragraph (AI label when it is AI text), and one button: **Start here ›** to the
  first story in reading order, or, once this reader has read a story, **Continue ›** to the first unread one.
- **Threads**: a block per thread: letter, name, its introduction (2–3 lines), `4 stories · 1 read · 12 causes open`,
  and a link to its first unread story. Stories are not listed again.
- **How the threads connect**: today's sentences, as a short list.
- Removed: "How to read this page" (now behind **?**, §1.1), the progress line, the To check column, the threads'
  story lists. The map stays in Index › Map.

## 4. Checks by cause

### 4.1 A cause

The reading stage groups its check rows into causes. A cause is one change and every place it asks the reviewer to
look at.

```python
class ChangeLine(BaseModel):
    sign: Literal["+", "-", " "]
    text: str
    line: int | None = None          # the line in the after text ("+", " ") or the before text ("-")

class CauseChange(BaseModel):
    path: str                        # workspace-relative
    depot: str | None = None         # the file the panel opens
    function: str | None = None      # its label
    lines: list[ChangeLine]          # 2–6 lines

class Cause(BaseModel):
    id: str                          # "c" + first 10 hex of sha1(kind|<workspace-relative file>::<qualified name>|subject)
    kind: CheckKind
    thread: str | None = None
    story: str | None = None
    text: str                        # its one line (§4.2)
    places: list[str]                # the check keys, sorted by path then line
    flows: list[str] = Field(default_factory=list)   # flow ids of its story that it touches
    finding: str | None = None
    change: CauseChange | None = None
```

`Check` gains `cause: str | None` (the id of its cause; none on a "found no hazard" row). `Reading` gains `causes: list[Cause]`, in reading order (§4.5); a
story's reading (`story_reading:{sid}`) gains its own causes. `READING_VERSION` is bumped.

**Grouping** (the subject is what makes two rows of one kind the same cause):

| Kind | Rows grouped by | Subject |
|---|---|---|
| reader | the changed function that writes the field, and the field | field label |
| caller | the changed function whose signature changed | — |
| result | the changed function, and its new return values | the values, sorted |
| target | the changed function called from another target, or the header | the target names |
| untested | the story | — |
| hazard, confirm | the finding (one finding, one cause) | the finding's kind and title |
| unanalysed, ask | the row alone | the row's key |

A cause's id depends only on kind, function and subject, so it survives a re-run that renumbers findings or reorders
stories. The function part is `"<workspace-relative file>::<qualified name>"`: a C function's qualified name carries
no file, and two files can each change their own `static int init()`; rows are grouped by the changed function itself
(its node), never by its name. Where a kind has no single function, the id uses: for untested, the sorted function
parts of the story's untested functions; for a header's target row, the header's path; for unanalysed and ask, the row's key. Two causes that would share an id are one cause.

**Flows touched**: the flows of the cause's story whose path holds the cause's changed function or the function of
one of its places.

**Places merge no more**: `_merge` stops folding rows of other kinds at the same place into `also`; every row stays
its own place under its own cause, and `Check.also` is removed. A place under more than one cause shows "also: <the
other causes' lines>" in the stepper (§4.3).

### 4.2 Its line

One line, singular when it has one place (then the row's own text, as today):

| Kind | Text (n places) |
|---|---|
| reader | `n places read \`field\`` |
| caller | `n callers not updated for \`callee\`'s new signature` |
| result | `n callers handle \`callee\`'s result the old way` |
| target | `n calls to \`callee\` from other build targets` (a header's row: its own text) |
| untested | `n functions no test calls` |
| hazard, confirm | the finding's verdict reason, else its title |
| unanalysed, ask | the row's text |

### 4.3 The stepper

A fourth panel item: `Open` gains `{ cause: string; at: number }` (`at` 1-based). The address spells it
`?open=cause:<id>&at=<n>`; `readOpen` / `href` learn it; a panel tab per cause (`openKey` `c:<id>`, label: the cause's
line, shortened).

The panel shows, top to bottom:

1. **Header**: the cause's kind tag and line; `‹ 3 / 80 ›`; `2 done`; **All look fine**.
2. **The change** (always shown): `The change · <function> · <path>:<line>`, then the cause's `change.lines` as a
   small diff (− red, + green, context plain). A link "Open the whole diff" opens the file's diff as its own panel
   tab. No change known: this block is not shown.
3. **The place**: `Place 3 / 80 · <function> · <path>:<line>`, then about 7 lines around the place's line from the
   after text, the line marked, and a link "Open the file" (the file's diff as a panel tab, at that line). When the
   place is under other causes: `also: <their lines>`, each a link to that cause at that place.
4. **Actions**: **Looks fine & next** (marks the place, moves to the next open place, or, after the last, to the
   cause's first open place; with none left, says "All 80 places done"), **Comment** (the place's check thread, as
   today), **‹ Back**, **Skip ›**.

Keys while the panel shows a cause and focus is not in a text field: `J` next, `K` back, `F` looks fine & next.

Stepping onto a place ticks it read for this reader (the personal tick, as today), when ticks are on.

**All look fine** marks every open place of the cause in one request: `POST /api/reviews/{rid}/checks/marks` with
`{"keys": [...]}` — any signed-in user, as the single mark; keys that are not checks of the review are a 404 and
nothing is marked.

A flow row's **Reopen** (spec 2026-10-25-review-ui-redesign §7.3) clears several places in one request:
`POST /api/reviews/{rid}/checks/unmarks` with `{"keys": [...]}` — any signed-in user, as the single unmark; all or none,
like the marks: a key that is not a check of the review is a 404 `NO_CHECK` and nothing is cleared. It answers
`{"ok": true}`.

### 4.4 The outline's Checks view

- At its top, **Showing: all but Confirm ▾** (§4.6).
- One group per thread, then per story, in reading order; each cause one line: its kind tag, its line (one line,
  ellipsis, whole line on hover), and `3/80` (done of places) or ✓. The open cause is marked.
- A line opens the stepper at the cause's first open place.
- At the bottom, folded: `N checks found no hazard`, with their reasons (today's "Cleared").

### 4.5 Order and Next open check

Reading order of causes: thread order, then the story's reading order, then, within a story, the first flow each
touches (causes touching no flow last), then kind order (`CHECK_ORDER`), then text.

**Next open check ›** opens the stepper at the first open place of the first open, shown cause after the one in the
panel (or after the current story's position when the panel shows none), wrapping to the start. With none open it is
not shown.

### 4.6 Hidden kinds

**Showing: all but Confirm ▾** opens a list of every check kind with a switch. The hidden set is remembered per browser
(`ct.ws.hiddenKinds`, a list of kinds, read and written in try/catch; default `["confirm"]`). Hidden causes are left
out of the outline's Checks view, chips, open counts (top bar, outline) and Next open check. The control names what it
hides (`Confirm hidden · 23`); with nothing hidden it reads **Showing all**. A link to a hidden cause (an address, an
`also:`) still opens it.

### 4.7 Names, never node ids

Every cause line, check text and `also:` line goes through `NameText` (node ids become linked names, finding ids
links); `Ticks` is no longer used for them. "Found no hazard" reasons too.

### 4.8 The change's lines

Picked from the diff of the cause's function (before → after text of its file), at most 6 lines:

| Kind | Lines |
|---|---|
| reader | the added line(s) that write the field in the writer, with one line of context |
| caller | the function's signature, before (−) and after (+) |
| result | the added `return` lines with the new values, with one line of context |
| target (header) | the header's first changed block |
| hazard, confirm | the finding's evidence lines in the after text, with one line of context |
| others | the function's first changed block |

When the kind's own rule finds no line, the function's first changed block is used; with no diff at all (an unchanged
function), no change is shown.

## 5. Compatibility and removals

### 5.1 Marks and ticks

Check keys keep their format, so existing **Looks fine** marks and read ticks still apply. Rows that `also` used to
hide become their own places, open until someone marks them.

### 5.2 Old addresses

- `?check=<key>` opens the stepper at that check's cause and place.
- `/i/checks` opens the overview with the outline on Checks.
- `?open=finding:F4`, `?open=file:…`, `?open=<node>` work as today.
- A story's `?view=graph` opens its Graph tab.

### 5.3 Removed

- The To check column (`CheckColumns`, its divider and its fold, `ct.ws.checkFolded`, `ct.ws.checkW`), and the
  To check tiles on the overview and on stories.
- Index › Checks.
- The story page's current tile layout (its content moves into tabs).
- "How to read this page" on the overview (moved behind **?**).
- `Check.also` and the place merge.

## 6. Errors and limits

- A cause id in the address that the review lacks: the panel says "This check isn't in this review" with a link to
  the outline's Checks view.
- A place whose file text is not available: the place block says "No code for this place" and keeps the actions.
- Long names follow the long-text rules: one-line labels end in an ellipsis with the whole text on hover; sentences
  wrap.
- A cause with hundreds of places: the stepper shows one at a time; the outline shows only the count.

## 7. Testing

- **Backend**:
  - grouping per kind: two readers of one field by one writer are one cause; another field or writer is another;
    callers of one changed signature are one cause; results by new values; one cause per finding; untested per story;
  - ids stay the same across a re-run that renumbers findings;
  - flows touched; reading order of causes;
  - the change's lines per kind, and the fallback;
  - rows at one place stay apart (no `also`);
  - the batch mark: marks every key; an unknown key marks nothing and is 404.
- **Unit** (vitest): `readOpen`/`href` round-trip `cause:<id>&at=3` and `sec=`; hidden kinds filter counts and Next;
  Next open check order and wrap; stepper next/back over done places; old `?view=graph` and `?check=` read.
- **e2e** (fixtures):
  - the outline's Stories view: threads, stories, the current story's flows; a flow line opens its card;
  - the outline's Checks view; a cause opens the stepper with the change above the place;
  - chips on flow cards open the stepper; J/K/F step; Looks fine & next; All look fine finishes a cause;
  - Confirm hidden by default, shown on demand, remembered;
  - Next open check walks causes in order and wraps;
  - story tabs, `?sec=` in the address, Back;
  - the overview's Start here / Continue and thread blocks;
  - old links (`?check=`, `/i/checks`, `?view=graph`);
  - tablet drawer, phone sheet with the stepper;
  - no node id shown anywhere (`expectNoNodeIds`), including a story with an AI verdict naming a node;
  - the long-text check visits the outline, a stepper and each story tab.
