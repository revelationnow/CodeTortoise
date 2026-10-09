# Review introduction — design

Date: 2026-10-09. Status: draft for the owner's review.

Sub-project D of the owner's feedback from a real change set (2026-10-08). A (shared sinks), B (LLM robustness) and C
(layout) are merged.

## 1. Problem

"Initial approach to the review is still a little difficult, a more detailed introduction explaining the different
threads upfront would be useful."

Today the overview opens with "The change as a whole" (2–4 sentences), the arcs between threads, and one card per
thread: a name of at most 6 words, a one-sentence purpose and its stories. A reader new to the change gets no sense of
what each thread involves or where to begin. A reader new to CodeTortoise also has to guess what a thread, a story or
a To check row is.

## 2. Goals

1. **The change as a whole** says more: 4–6 sentences covering its purpose, its scope (CLs, areas, number of threads)
   and the main risk.
2. **Each thread in depth:** a paragraph of 3–5 sentences saying what it changes and why, where in the code, what could
   go wrong (from its open checks) and how much is open.
3. **Where to start:** every thread in a suggested reading order, each with a one-sentence reason, and the threads
   worth only a skim marked so. The strong model decides the order; the rules decide it when there is no strong model
   or its answer fails the checks.
4. **How to read this page:** a fixed, collapsible explainer of the page's ideas for people new to CodeTortoise.
5. Every part has fixed text from the rules, so a review without a strong model still gets an introduction.

Not goals: changing how threads are formed or named; a separate introduction page; per-story introductions.

## 3. What is made

### 3.1 Data (`reading.py`)

```python
class Thread(BaseModel):
    ...                                   # unchanged: id, name, purpose, text_source, stories, cls, open_checks
    intro: str = ""                       # 3–5 sentences; "" in readings stored before this change
    intro_source: Literal["template", "llm"] = "template"
    files: list[str] = Field(default_factory=list)     # its key files, workspace-relative, at most 8 (§3.3)
    modules: list[str] = Field(default_factory=list)   # its key modules: directories, workspace-relative, at most 4
    files_source: Literal["template", "llm"] = "template"

class RouteStep(BaseModel):
    thread: str                           # thread id
    reason: str                           # one sentence
    skim: bool = False

class Reading(BaseModel):
    ...
    route: list[RouteStep] = Field(default_factory=list)       # every thread once, in reading order; [] before this change
    route_source: Literal["template", "llm"] = "template"
```

`whole` and `whole_source` keep their meaning; the introduction call (§4) may replace the threads call's whole with
the fuller one.

### 3.2 The rules' text (always made, in `build_reading`)

**Thread intro.** From the thread's stories, the files they touch and its open checks:

> 3 stories in `driver/` and `service/` across CL 101. 2 checks open: Confirm, Result handled the old way.
> Starts with “uart_send can now return -2”.

- Directories: the thread's `modules` (§3.3), at most 3, then "and N more".
- Checks: "Nothing is open." when none; otherwise the count and the distinct check kinds by their `KIND_LABEL` labels
  (the labels the To check rows show), at most 3 then "and N more".
- The first story's title, in the thread's reading order.

**Route.** The threads' own order, skim threads last:

1. Threads are groups of stories joined by calls or shared data, so no call or data link runs between two threads; the
   rules have no dependency to order by. They keep the order `build_threads` already gives (most open hazards, then
   most open checks, then most changed functions).
2. A thread is **skim** when it has no open checks and all its stories are repeated edits or tests (`mechanical` or
   `tests`). Skim threads move to the end, keeping their order.

Reasons, one per step:

- "1 hazard and 2 checks open." / "2 checks open." / "1 check open." (hazards counted among the thread's open checks)
- "Nothing is open." for a thread with no open checks that is not skim
- skim: "Only repeated edits and tests; skim it."

The rules' route has `route_source="template"`.

### 3.3 Key files and modules

A thread's **files** are the files its stories change, workspace-relative; its **modules** are directories holding them.
The threads call (§4.0) picks the ones that matter. The rules' pick, made first and kept when the threads call's pick is
missing or fails its check:

- files: the thread's changed files, most changed functions first, then by path; at most 8.
- modules: the directories of those files, most files first, then by path; at most 4.

## 4. The model's text

### 4.0 The threads call picks each thread's key files and modules

The threads call (`llm/threads.py`) is given, per thread, every file its stories change (workspace-relative, with the
number of changed functions in each; at most 40 per thread, most changed first, then "+N more") and asked, per thread,
for `"files"` (at most 8, the ones a reviewer should look at first) and `"modules"` (at most 4 directories naming the
parts of the code it touches).

Check, per thread: every file is one of the thread's listed files; every module is a directory that holds at least one
of them (a prefix of a listed file ending at a `/`); at most 8 files and 4 modules; at least one file. Else the rules'
pick stays. Accepted picks get `files_source="llm"`. The `thread_text` cache stores them with the name and purpose, and
`READING_VERSION` goes up so caches written before this change are not reused.

### 4.1 When

A new tier-1 call, purpose and target `"intro"`, made once per review in the review stage, right after the thread text
(`write_threads`) so it can use the final thread names. It goes through `try_tiers` like the threads call: the strong
model, the strong model fresh, then the weak model. `"intro"` joins `ledger.TIER1`, so it counts against the
strong-model budget.

No strong model configured: no call; the rules' text stands.

### 4.2 Input

```
THREAD DETAILS (id | name | purpose | CLs | open checks):      (not "THREADS (id": the threads call's prompt starts so)
  T1 | `uart_send` returns -2 | … | CL 101 | 2
    modules: driver/, service/                                  (the thread's modules, §3.3)
    files: driver/uart.c, service/logger.c                     (the thread's key files, §3.3)
    stories: S1 uart_send can now return -2…: <purpose> (behaviour); S2 …
    open checks: Confirm: uart_send: new return value -2; Result handled the old way: logger_flush ignores …  (at most 6)
CONNECTIONS (a | b | kind | text):
  …
CL DESCRIPTIONS: (each marked "a hint from its author, not the source of truth", as in the threads prompt)
```

### 4.3 Ask and answer

The ask: write "whole" (4–6 sentences: the change's purpose, its scope, the main risk); for each thread an "intro"
(3–5 sentences: what it changes and why, where, what could go wrong, how much is open); and a "route" listing every
thread once in the order a reviewer should read them, each with a one-sentence "reason" and "skim" true for threads
worth only a skim. Cite the ids (T1, S2, N4, CL12) behind each part.

```json
{"whole": "…", "whole_cites": ["T1", "S2"],
 "threads": [{"id": "T1", "intro": "…", "cites": ["S1", "N4"]}],
 "route": [{"thread": "T2", "reason": "…", "skim": false, "cites": ["T2", "S3"]}]}
```

### 4.4 Checks (each part on its own)

- **whole:** 4–6 sentences, cites only listed ids (at least one), passes the house style (`explanation`). Else the
  threads call's whole stays.
- **a thread's intro:** 3–5 sentences, cites only listed ids (at least one), house style. Else that thread keeps the
  rules' intro.
- **route:** all or nothing. Its threads are exactly the review's threads, each once; every reason is one sentence in
  the house style with cites only from the listed ids (at least one). Else the rules' route stays.

Accepted parts get `"llm"` as their source. The stage notes say which parts kept the fixed text, as the thread text
does ("introduction: 1 thread(s) and the route kept the fixed text").

### 4.5 Cache

Blob `intro_text`: `{"key", "whole", "whole_source", "threads": {id: [intro, source]}, "route": [...],
"route_source"}`. Key: sha256 of `INTRO_VERSION | strong model | intro prompt`. A run whose key matches reuses it
without a call; a fresh re-run (`fresh=True`) always asks again. The blob is written only when every part was accepted,
as `thread_text` is.

The review stage's message gains the introduction's author: "…; introduction by big-model", "…; introduction by
small-model (the strong model failed)" or "…; fixed introduction".

## 5. The overview

The left column, top to bottom:

1. **How to read this page** (collapsible, §5.1).
2. **The change as a whole**, with the AI label when the model wrote it.
3. **Where to start** (§5.2), when the reading has a route.
4. **How the threads connect** (unchanged).
5. **Threads**: each card shows `intro` in place of `purpose` (falling back to `purpose` when empty), with the AI label
   when `intro_source` is `llm`.

The right column (To check, Build impact, Coverage) is unchanged. On a phone the same order stacks.

### 5.1 How to read this page

A `<details>` box, open on a viewer's first visit; once closed it stays closed in that browser (`ct.intro.open`, read
and written through the existing storage helpers, so storage that is missing or throws means open). Its fixed text:

- **Threads** group the change's stories that are joined by calls or shared data. Each has a letter (A, B…) used
  across the page.
- **Stories** are the steps of a thread, one change and its effects each. A story has a **Steps** view (what it does,
  before → after, call paths, its code) and a **Graph** view.
- **Arcs** between threads: solid when they share calls or data, dashed when they only arrived in the same review —
  ask the author why.
- **To check** lists what needs a reviewer's eye. **Looks fine** clears a row, **Read** ticks it for you alone,
  **Comment** starts a thread, **Open** shows the code.
- **Progress** counts the stories and checks you have read.
- **The side panel** shows code beside the page; ⤢ on a story's code opens it there.

### 5.2 Where to start

A numbered list, one row per route step: the thread's letter, its name, " — ", the reason. A skim step is muted and
carries a "skim" tag. The letter and name link to the thread's card below (as the arcs' boxes do); a "first story" link
opens the thread's first story. The AI label sits on the heading when `route_source` is `llm`.

## 6. Stored reviews

Readings stored before this change have no `intro`, `intro_source`, `route` or `route_source`; they load with the
defaults. The overview then shows each thread's purpose and hides Where to start. A re-run writes the new fields.

## 7. Testing

pytest:

- rules: a thread's intro text (directories capped, checks' kinds, "Nothing is open.", first story); the route keeps
  the threads' order, moves skim threads last, and gives each step its reason.
- key files and modules: the rules' pick (most changed functions first, capped); the threads prompt lists each thread's
  files (capped at 40 with "+N more"); an accepted pick sets `files_source="llm"`; a file not in the thread's list, a
  module holding none of its files, more than 8 files or 4 modules, or no file keeps the rules' pick; a cached pick is
  reused.
- intro prompt: holds each thread's modules, key files, stories, open checks (capped) and the connections.
- intro answers: an accepted answer sets every part to `llm`; a whole with 3 sentences, an intro with 6, an intro
  citing an unlisted id, a route missing a thread, a route listing one twice and a reason of two sentences each keep
  their fixed text, and only that part.
- pipeline: the intro call runs after the thread text with purpose `intro`; its cache is reused when the key matches
  and skipped on a fresh run; no strong model means no call and the rules' text; the stage message names the author.
- an old reading without the new fields loads.

vitest: the explainer's open state with storage working, missing and throwing; the route rows' text and skim flag.

e2e (rules server): the explainer is open on a first visit, stays closed after a reload once closed and reopens; Where
to start lists every thread and its links go to the thread card and the first story; a thread card shows its intro.
e2e (fake strong-model server): the AI label on Where to start and on a thread's intro.
