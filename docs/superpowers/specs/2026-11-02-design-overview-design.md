# A review's design overview: purpose, place and walk-throughs — design

Owner's proposal, 2026-11-02, written with an agent that runs CodeTortoise on a production codebase. It came as a
page with a mockup tab and a spec tab; this file transcribes the spec tab, and §3.3 describes the mockup's
walk-through page. A few passages of the screenshots were hard to read; they are marked *(reconstructed)*.

It extends the overview (spec 2026-10-25-review-ui-redesign §5), the reading (2026-10-07-review-reading-phase2) and the
introduction (2026-10-09-review-introduction). The example throughout is the demo review,
`backend/codetortoise/fixtures/cfixture` CLs 101–105.

## 1. What this adds, and why

Threads, stories and checks tell a reviewer *what changed* and *what to look at*. They don't say what the change is
*for*, where it sits among the parts of the code, or how a request travels through it end to end. A hand-written review
of the same change usually opens with exactly that: the problem, the parts involved, a sequence diagram of the main case
and the edge case, a table of what the design must get right, and what happens when its condition is not met. Only then
does it go through the changes one by one.

This proposal adds that opening to the **existing overview**, built from what the pipeline already works out. It adds
no new page and no new unit of review. Threads, stories, flows and checks stay as they are and stay the only things a
reviewer marks.

## 2. How it fits the existing model

> **There is no new "journey" concept.** The earlier draft's journeys are dropped. What it drew as a journey is an
> ordered view over pieces the reading already has. It is called a **walk-through**, and it lives inside the threads:
>
> - A story's **call paths** (`CallPath`, its Call paths tab) give the steps from an entry point down to the changed
>   function.
> - A story's **flows** (the board's Flows, the Flows tab's rows) give the steps from the changed function to where it
>   lands: a caller that gets a new value, a reader that sees a new writer.
> - A **connection** between two threads (`Connection`, the "With Thread B: …" lines) says where one thread's flow
>   continues into another's.
>
> A walk-through chains these in calling order. Every step points back to the flow, story or cause it came from. Its
> open count is the open count of those causes. "Looks fine" on a step sets the same mark as on the flow in the Flows
> tab, so nothing has two states. A walk-through belongs to the thread whose flows it follows. When it crosses threads,
> it belongs to the connection between them.

### Every part of the hand-made opening, mapped

| Part of a hand-made review | What CodeTortoise has today | What this proposal adds |
|---|---|---|
| The problem and the fix, in a paragraph | `Reading.whole`, written by `llm/intro.py` from the stories | The same paragraph, also given the design context (§8), so it can say what the change is for |
| Verdict: does it hold, what to settle | `Reading.headline` (a pill: "5 to check") | A verdict paragraph under `whole` whose points are cause chips (`st-chips`), nothing new to tick |
| Architecture diagram: the parts and what crosses them | The Map tab (`MapSection`: layer bands and blocks); `Thread.modules` | "Where the change sits": the Map's bands drawn on the overview, blocks per component (§5) with thread letters |
| Sequence diagrams (main case, edge case) | Call paths per story; flows per story; connections between threads | Walk-throughs (§4): those pieces chained across stories, drawn as a sequence |
| "What it must get right" table | Nothing; checks are per finding, not per requirement | A concern table (§6) whose rows cite stories and causes; it adds no checks |
| Ownership and shortfalls | Nothing | "Is the design right?" fold (§6), each line citing code |
| "When the condition is not met" | Nothing; a story's Before → after shows lines, not conditions | A fold listing the changed lines that still run when the change's condition is false (§7) |
| The changes one by one | Threads → stories → flows → checks | Unchanged. Story crumbs gain "in walk-throughs: … · answers concerns …" links |

### Names, and why they changed from the first draft

- **Journey → walk-through.** A journey had its own id, steps, open state and page. A walk-through has steps that are
  references and no state of its own. It is drawn on a page shaped like a story, at `/r/{id}/walk/W1` beside
  `/r/{id}/s/S1` (not `/w/`: the top-level `/w/:id` is the old address that redirects to a review).
- **Design brief → reading design.** `brief.py` already holds the tier-1 `Brief` that tier-2 prompts start from
  (`llm/brief_context.py`). The new data is stored as blob `reading_design` and modelled as `ReadingDesign`, so the two
  never meet.
- **Not a sequence.** `sequence.py` and `reading/sequence.ts` are about the CLs as a sequence. The walk-through code is
  `walks.py` and `reading/walks.ts`.

## 3. What the reader sees

All in the existing workspace; the mockup tab marks each addition with a dashed outline.

### 3.1 The overview, top to bottom

1. **Heading and `whole`** ("3 threads", the lead paragraph). It is unchanged, except that the model also gets the
   design context.
2. **Verdict** (new): two or three sentences ending in what to settle, then the causes it names as chips. A chip opens
   its flow, as chips do elsewhere. The source line names the design context and carries the AI menu (§12.3).
3. **Start with Thread A ›**, unchanged.
4. **Where the change sits** (new, §5).
5. **What it must get right** (new, §6).
6. **The thread sections**, unchanged, plus:
   - a line "▶ Walk through: *title* ›" under the stories of a thread that has one;
   - a "▶ Walk through ›" link at the end of a connection line that has one.
7. **Tests** line, unchanged.
8. **Is the design right? · N questionable** (new fold, §6).
9. ***When the condition is false* · N changes still run** (new fold, §7). Its title names the condition, e.g. "Writes
   that fit (64 bytes or less)".
10. **Build impact, Coverage, Discussion**, unchanged.

### 3.2 Elsewhere

- **Outline (Stories view).** In an open thread bar, after its stories, there is one row per walk-through: "▶ Walk
  through · *title*", with its open count and step count. It is a `ws-row walk`.
- **Walk-through page** (`/r/{id}/walk/W1`). Its header has the same shape as a story's: title, a crumb ("Thread B with
  Thread A · 8 steps · over S1"), and the lead. Then:
  - the sequence drawing;
  - the steps as `fl-row`s, each linking to its source flow;
  - the other walk-throughs as chips.

  Clicking a step in the drawing opens its row.
- **Story page.** `st-crumb` gains "· in *walk-through* (steps 2, 3, 4) · answers concerns 1, 2, 3, 4". In the Flows
  tab, a flow on a walk-through shows "▶ step N" in its head and "On the walk-through: step N of … ›" in its body.
- **Review menu ⋯.** It gains "Design context…", which opens an `rm-panel` (§8).
- **Crumbs.** On a walk-through page they read *review* › *Thread B with Thread A* › Walk through: *title*.

Nothing new is counted in the head's progress. "0 of 5 stories read · 0 of 5 checks" stays the measure.

### 3.3 The mockup's walk-through page

The mockup shows "Walk through: A write longer than 64 bytes" for the demo review:

- **Outline.** Thread A's bar lists its two stories, then "▶ Walk through · A write longer than 6… 2 / 8 steps · with
  Thread B" and "▶ Walk through · A write that fits 1 / 7 steps". Thread B's bar lists its two stories, then the same
  first walk-through ("8 steps · with Thread A") and "▶ Walk through · The logger's level 1 / 3 steps". Thread C has
  none.
- **Crumbs:** "uart stats, hal_write and the logger level › Thread B with Thread A › Walk through: A write longer than
  64 bytes".
- **Head:** the title; "Thread B with Thread A · 8 steps · over S1 · 2 open" (thread names and S1 are links); the lead
  as AI text: "What happens to `logger_write("…", 100)`, from `main` to its exit status. It strings together the call
  path of S1 flow 1 and the data flow of S1 flow 3; both cross from Thread B's logger into Thread A's driver."; then a
  quiet note: "Built from the stories' call paths and flows; the arrows are calls (solid) and returns (dashed). Its
  checks are the stories' checks: marking a step fine marks that flow fine."
- **Drawing:** columns `main` (App), `logger_write` (Service), `uart_send` (Driver), `uart_errors` (Driver), scrolling
  sideways when they don't fit. Eight numbered rows:
  1. `logger_write(…)` — a solid call arrow, `main` → `logger_write`, unchanged;
  2. `uart_send(…)` — a call, `logger_write` → `uart_send`, unchanged;
  3. `len > 64: *err` — a loop arrow on `uart_send`, new;
  4. `return -2` — a dashed return, `uart_send` → `logger_write`, new, with an open check (the number on a red disc);
  5. `dropped++; return -1` — a loop on `logger_write`, unchanged;
  6. `-1, ignored` — a dashed return to `main`, unchanged;
  7. `uart_errors(u)` — a call, `main` → `uart_errors`, unchanged;
  8. `errors, now counting overflows` — a dashed return, `uart_errors` → `main`, changed, with an open check.
- **Legend:** new in the change, changed, unchanged, a step with an open check.
- **The steps:** the same eight as rows, each with its reference on the right: "call path of S1 flow 1" (1, 2),
  "S1 · the change ›" (3), "S1 flow 1 ›" (4, with a tick box), "logger_write, unchanged" (5), "main, unchanged" (6),
  "call path of S1 flow 3" (7), "S1 flow 3 ›" (8, with a tick box).

## 4. Walk-throughs

### 4.1 What one is

A walk-through is a path through the changed code that a reviewer would trace by hand. It has:

- **a start**: an entry point, or the outermost caller the parse found;
- **the changed functions** it passes through;
- **the places** where what changed lands.

Each step is one call, one return, one write or read, or one step a function takes inside itself, and each carries a
reference:

| Step | Comes from | Reference |
|---|---|---|
| Calls from the start down to a changed function | The story's `CallPath` (its `steps`, entry first) | story, path index |
| What the changed function now does (the new branch, the new write) | The story's change lines (`CauseChange`, the diff map) | story, cl, line |
| Where the new value lands (a caller's handling, a reader) | The board flow (`lands`, `what`) and its cause | story, flow, cause |
| Unchanged steps between them, so the steps read in order | The impact graph's call and field edges (`impact.Edge`) | edge id; no story |
| Where it continues into another thread | A `Connection` whose facts hold the node the two flows share | connection (a, b) |

### 4.2 How they are chosen

1. **Candidates.** For each thread, the call paths of its stories that end at a changed function, longest first.
2. **Join.** A candidate continues with the board flows of the function it ends at, in flow order. If a flow's `lands`
   node is the start of another story's call path, the walk-through follows on into that story. If the two stories are
   in different threads, the walk-through is anchored on their connection.
3. **Cases from conditions.** When a changed function gains a condition (§7), the walk-through is drawn twice, once each
   way. The model names each case ("A write longer than 64 bytes", "A write that fits"). The steps are the code's.
4. **Keep.** Keep a walk-through if it covers at least one open cause, or at least two stories. Drop any that the others
   already cover entirely. Keep at most `max_walks` per review (default 6), with those covering the most open causes
   first.
5. **Depth.** Unchanged steps more than `walk_depth` calls (default 2) away from a changed function fold into one
   "… N calls" step, as `CallPath.hidden` does today.

Most of it is rules, and only the titles and the lead paragraph come from the model. If the model call fails, the title
falls back to the condition or the entry point ("From `main` through `uart_send`"), and the walk-through is otherwise
unchanged.

### 4.3 State

None of its own. Its open count is the number of distinct open causes among its steps. Marking a step fine posts that
flow's check keys to the existing `POST /api/reviews/{id}/checks/marks`, as the Flows tab's "Looks fine" does, so the
Flows tab, the outline counts and the head's progress change with it. Steps with no flow, such as unchanged calls and
the change itself, have no tick.

### 4.4 Drawing

The drawing is an SVG sequence diagram in the board's colours:

- **columns**: functions, labelled with their component;
- **solid arrows**: calls;
- **dashed arrows**: returns;
- **a loop arrow**: a step inside one function.

Line colours:

- `--add-ink`: new in the change;
- `--chg-deep`: changed;
- `--bd-arrow`: unchanged.

A step with an open cause has its number on `--fx-deep`. Loops drawn from the code (`for`, `while`) frame their steps.
It reflows into a list on a phone, where the step rows are the walk-through.

## 5. Where the change sits

This is the Map tab's layer bands (`.ov-band`, `.ov-block`) on the overview, with three differences:

- **Blocks are components**, not directories. They come from the config's `components:` (§13). Without it, they come
  from `layers.py` levels and `Thread.modules`.
- **Each block shows the letters of the threads that change it**, its changed files, and its `.also` line: what changed
  in it, from the stories' titles.
- **The `.ln` lines are the impact graph's edges that cross from one component to another**, grouped by pair
  ("`logger_write`, `logger_flush` call `uart_send`").

A component whose changes share no edge with the rest gets a dashed block in its own band, labelled as such, which is
Thread C in the demo. It is all rules and needs no model.

## 6. What it must get right, and is the design right

### 6.1 Concerns

The table has four columns:

- **Concern**: what the design asks for.
- **How the change does it**: one sentence.
- **Where**: thread letters and story links.
- **Assessment**: one of `right`, `note`, `confirm`, `ask`. It can add a short note and cause chips.

The model writes the rows from the design context and the stories. Each row must cite at least one story. An assessment
of `confirm` or `ask` must cite an existing cause. A row whose cause doesn't exist is shown as `note` and gets no chip,
so the table never creates work the checks don't already hold.

Without a design context, the concerns come from the stories' purposes alone. The heading's source then reads "AI, from
the stories".

### 6.2 Ownership and shortfalls

The fold is a list of short lines. Each has a tag: `right`; `questionable` (shown as a `confirm` tag); `shortfall`;
`note`.

Each line says which part owns a decision, or what the change leaves undone, and must cite a node, a file or a story.
The fold's title counts the questionable lines and the shortfalls. These lines are opinions, not checks: they never
reach the head's count.

## 7. When the condition is not met

A **condition** is a test the change adds that guards new behaviour. `gates.py` finds them in the diff map and the
after-parse:

- a new `if`, `else if` or `switch` case;
- a new early `return` under a condition;
- a changed condition in an existing `if`.

For the strongest condition (the one guarding the most changed lines; ties go to the earliest story), every changed line
of the review is put in one of three classes:

- **under the condition**: it doesn't run when the condition is false;
- **outside it**: it still runs;
- **elsewhere**: in another function. It still runs unless that function is reached only through the guarded branch.

The fold lists them with their stories. Its title is the false case in words. The model names it; the fallback is
"When `len > 64` is false". The design context can add or remove conditions by hand (§8). If nothing is found, there is
no fold.

## 8. The design context

This is what the code can't say:

- free notes;
- attached documents (markdown or text, or a link the server can read);
- conditions added or removed by hand;
- a choice of components.

It is entered in the ⋯ menu's "Design context…" panel, or at review creation as an optional field. It is stored per
review in blob `design_context`, capped at 12 000 characters after documents are read. Saving it re-runs only the
`design` stage. The prompts that read it are the opening and its new parts. Stories, flows and checks never read it, so
a design context can't change what is flagged.

## 9. Pipeline and data model

`… → board → llm → reading → design → finalize`

The new stage `design` depends on `reading`. It writes blob `reading_design`, which is served with the reading. It is
cheap to re-run, so saving a design context re-runs it alone, and the review keeps its stories and checks. If it fails,
the overview is exactly today's.

New modules:

- `components.py`: components from config or layers, and the crossing edges.
- `walks.py`: candidates, joining and keeping (§4).
- `gates.py`: conditions and the classes of lines (§7).
- `llm/design.py`: the one tier-1 call (§10).

The bands reuse the Map tab's code: `bandsOf` and `MapSection`'s markup in `WholePage.tsx`, with levels from
`layers.py`. Only the blocks differ: components here, clusters (`clusters.py`) there.

```python
class WalkStep(BaseModel):
    kind: Literal["call", "return", "self", "write", "read", "fold"]
    src: str                          # node id
    dst: str                          # node id; == src for "self"
    label: str                        # from the code: the call, the returned value, the assignment
    status: Literal["new", "changed", "same"]
    story: str | None = None          # S1
    flow: str | None = None           # a flow id of that story
    cause: str | None = None          # C2
    edge: str | None = None           # impact edge id, for unchanged steps
    loop: str | None = None           # "for each byte": the loop this step sits in

class Walk(BaseModel):
    id: str                           # W1; cited, never shown
    title: str
    title_source: Literal["template", "llm"] = "template"
    lead: str = ""
    thread: str | None = None         # anchored on a thread …
    connection: tuple[str, str] | None = None   # … or on the connection between two
    condition: str | None = None      # the gate id, when this is one side of it
    parts: list[str]                  # node ids, left to right
    steps: list[WalkStep]

class Component(BaseModel):
    name: str
    level: int | None
    globs: list[str]
    threads: list[str]
    files: list[str]
    crossing: list[str]               # sentences from the crossing edges
    quiet: bool = False               # shares no edge with the rest

class Concern(BaseModel):
    text: str
    how: str
    stories: list[str]
    assessment: Literal["right", "note", "confirm", "ask"]
    note: str = ""
    causes: list[str] = []

class Ownership(BaseModel):
    tag: Literal["right", "questionable", "shortfall", "note"]
    text: str
    cites: list[str]                  # node ids, paths or story ids

class GatedLine(BaseModel):
    story: str
    cl: int
    text: str
    runs: bool                        # when the condition is false

class Gate(BaseModel):
    id: str
    node: str                         # the function holding it
    test: str                         # "len > 64"
    false_case: str                   # "Writes that fit (64 bytes or less)"
    lines: list[GatedLine]
    source: Literal["code", "context"]

class ReadingDesign(BaseModel):
    verdict: str = ""
    verdict_causes: list[str] = []
    components: list[Component] = []
    concerns: list[Concern] = []
    ownership: list[Ownership] = []
    gates: list[Gate] = []
    walks: list[Walk] = []
    sources: dict[str, Literal["template", "llm", "pinned"]] = {}   # per part
    context_hash: str | None = None
```

`Reading.whole` stays where it is; with a design context, `llm/intro.py` receives it as an extra section of its prompt.

## 10. The model call

There is one tier-1 call per review, after `llm/intro.py`. It receives:

- the design context;
- `whole`, and the threads with their stories and purposes;
- the open causes with their kinds;
- the components and their crossing edges;
- the conditions;
- the walk-throughs' steps, which it does not choose.

It returns JSON:

- `verdict` and `verdict_causes`;
- `concerns`;
- `ownership`;
- a title and lead per walk-through;
- a `false_case` per condition.

Each part is checked on its own, as `llm/intro.py` does:

- ids must be listed;
- sentence counts and the house style (`llm/style.py`) must hold;
- a concern must cite a story;
- `confirm` or `ask` must cite a live cause.

A part that fails keeps its fixed text, and if there is none it is left out. It runs through `try_tiers` and the ledger
like every other call. Each AI part carries the AI menu (§12.3) *(reconstructed)*:

- "Rewrite" re-asks that part alone *(reconstructed)*;
- "Rewrite with an instruction…" adds the reviewer's words to the prompt;
- "Pin this text" stores it in `sources` as pinned, so a re-run keeps it.

## 11. API

| Route | What |
|---|---|
| `GET /api/reviews/{id}/reading` | Unchanged, plus `design`: the `ReadingDesign` or null |
| `GET/PUT /api/reviews/{id}/design-context` | Read or save the context. Saving queues the `design` stage and returns 202 |
| `POST /api/reviews/{id}/design/{part}/rewrite` | Re-ask one part (`verdict`, `concerns`, `ownership`, `walk:W1`), with an optional instruction |
| `POST /api/reviews/{id}/design/{part}/pin` | Pin or unpin a part's text |

Marks on walk-through steps use the existing `/checks/marks` and `/checks/unmarks` routes with the flow's check keys.
There is no new mark type.

## 12. Frontend

### 12.1 Files

- `reading/types.ts`: the types of §9.
- `reading/walks.ts`:
  - a walk-through's open count from causes and marks;
  - the step → flow lookups the story page needs;
  - the sequence layout.
- `workspace/Overview.tsx`: `Verdict`, `WhereItSits` (reuses `MapSection`'s band markup), `Concerns`, the walk line in
  `ThreadSection`, the link in the connection lines, and two `Fold`s.
- `workspace/WalkPage.tsx`: the place `walk`, at `/walk/:wid` inside a review, beside `/s/:sid`. It reuses `st-head`,
  `st-flows`, `fl-row` and `Chips`.
- `workspace/Outline.tsx`: the walk rows in `ws-bar-list`.
- `workspace/StoryPage.tsx`, `FlowsTab.tsx`: the crumb links and the "step N" links.
- `workspace/ReviewMenu.tsx`: "Design context…", and the panel.
- `workspace/address.ts`, `workspace/crumbs.ts`: the walk place (`/walk/W1`, `?at=4` for a step) and its crumbs.

### 12.2 Styles

New styles are few and use the app's variables only (`dz-*` in `workspace.css`). The tags `ck-tag.right` and
`ck-tag.note` join the existing kinds. In both themes, the drawing's colours are the board's variables.

### 12.3 The AI menu

It has the shape of Explain ▾ (`.ai-menuwrap`, `.ai-menu`), labelled "Rewrite ▾", with the three items of §10. AI text
keeps the `.ai-text` edge.

## 13. Config

```yaml
analysis:
  components:                  # optional; without it, layers.py levels name the bands
    - { name: App,     globs: ["app/**"] }
    - { name: Service, globs: ["service/**"] }
    - { name: Driver,  globs: ["driver/**"] }
    - { name: HAL,     globs: ["hal/**", "include/hal/**"] }
  walk_depth: 2                # unchanged calls shown either side of a changed function
  max_walks: 6
  design: true                 # false: no design stage, today's overview
```

## 14. Cost and limits

- One tier-1 call per review, at most about 6k tokens in and 1.5k out. Re-asking one part costs one smaller call.
- Walk-throughs and gates are rules over data the pipeline already holds, so they cost no model calls. They are bounded
  by `max_walks` and by `walk_depth`.
- A review with no call paths, such as a header-only change, gets no walk-throughs. One with no conditions gets no
  condition fold. One with a single component gets no "Where the change sits". Each part appears only when it has
  something to show.
- The design context is capped at 12 000 characters, and documents are read once when saved.

## 15. Testing

- **Unit (`cfixture`).**
  - components and crossing edges match the demo's bands;
  - `gates.py` finds `len > 64` and puts `st->tx++`, the `hal_write` signature, `level = 2` and `r.n += 3` on the side
    that still runs;
  - `walks.py` builds the two `uart_send` cases and the level walk-through;
  - W1 is anchored on the connection between Thread B and Thread A;
  - every step's flow and cause exist.
- **Model checks.**
  - a concern citing a missing cause becomes a `note`;
  - an uncited ownership line is dropped;
  - a failed call leaves today's overview exactly.
- **Scale (`fixture_large`).** `max_walks` holds, the stage stays under one second without the model, and the drawing
  reflows on a phone.
- **e2e.**
  - the demo review shows the walk line on Thread A and the link on Thread B's connection;
  - marking W1 step 4 fine marks S1 flow 1 fine, and the head's checks count moves;
  - the outline shows the walk rows;
  - the design context panel saves and re-runs `design` alone.

## 16. Phasing

1. **Rules only.** Ship together:
   - components and "Where the change sits";
   - walk-throughs with fixed titles;
   - the outline rows, the crumb links and the step links;
   - the condition fold.

   No model and no context.
2. **The model call.** The verdict, concerns, ownership, and walk-through titles and leads, from the stories alone.
3. **Design context.** The panel, documents, conditions added by hand, and the "for" in `whole`.
4. **AI menu.** Rewrite, rewrite with an instruction, and pin.

## 17. Open questions

- Should a walk-through be offered for a thread with one story and no conditions, or is its Call paths tab enough? This
  proposal says no: keep only those covering two stories or an open cause.
- Should the concern table be allowed to raise a new `ask` cause when the design context names something the change
  doesn't do? This proposal says no for now, because checks come from code.
- Components from config are a second source of names beside `layers.py`. Should `layers` gain names instead?

## 18. Notes against the code (added when planning, 2026-11-02)

The proposal was written against the demo before the code was read line by line. Where the code says otherwise, these
notes hold.

1. **Ids.** Cause ids are `c` and ten hex digits (`causes.py`), not `C1…`; `C<n>` are cluster ids. Walk-through ids are
   numbered in the order they are listed: by condition, the ones covering the most causes first.
2. **The demo's first walk-through.** `uart_send`'s new `-2` lands in `logger_flush` (S1's flow 1), not in
   `logger_write`, and S1's other flow is the reader `uart_errors`. So the demo's W1 runs `main` → `logger_flush` →
   `uart_send`, takes `len > 64`, returns `-2` to `logger_flush`, goes back to `main` and on to `uart_errors`. That is
   nine steps, and the flow-1 step is step 5. It crosses into the logger's thread because `logger_flush` lives in
   `service/logger.c`, which that thread's stories change, so it sits on the connection between the two threads.
3. **Thread letters.** In the demo the driver and HAL thread is Thread A (stories S2, S1), the logger thread is Thread B
   and the C++ thread is Thread C, so the crumbs read "Thread A with Thread B".
4. **A fourth walk-through.** `hal_write`'s signature change gets one of its own (`main` → `uart_init` → `hal_write`),
   since S2's flow 1 lands there with an open cause.
5. **A step's address** is `?step=N`. `?at=` already places the open cause in the side panel (`open=cause:…&at=N`).
6. **The head's progress** reads "X of N stories read · K checks open" today, and stays as it is.
7. **Unchanged arrows** use `--bd-muted`. `--bd-arrow` (#b3b8cc) is about 2:1 on white, short of the 3:1 that WCAG
   asks of graphics.
8. **Labels.** `/names` names only the nodes on boards and stories and in cited text, so `ReadingDesign` carries its own
   `nodes`: label, component, file and line.
9. **No single-stage re-run exists today.** Phase 3 adds the one a design context needs. Until then `design` runs as
   part of every run.
10. **Fields added to the §9 models**, each commented in the code:
    - a step's `ref` (what it comes from), `keys`, `flow_n`, `path`, `line`, `cl` and `folded`;
    - a walk-through's `case` and `stories`;
    - a gate's `story`, `path`, `line`, `guarded`, `runs` and `stops`;
    - a gated line's `where`, `path`, `line` and `function`. Its `story` may be none: a header line that no story holds.
