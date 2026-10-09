# Shared sinks — design

Date: 2026-10-09. Status: draft for the owner's review.

Sub-project A of the owner's feedback from a real change set (2026-10-08). B (LLM robustness) is merged; C (layout
fixes) and D (introduction) follow.

## 1. Problem

"When a change is made that writes to something like a log buffer, it triggers to check all over the code base where
writes to that log buffer happen; there needs to be a way to filter out such things which cause huge fan-outs."

When a changed function newly writes a struct field, every consumer fans out to the field's other users:

- **To check** gets one "reader" row per unchanged function that reads the field (`reading.py`, check 5).
- **The board** puts a State note on the writer, one on every other reader or writer ("now also written by …"), one
  per name-matched access ("may access … (name match)"), and a "new writer · readers · other writers" note on the
  field's declaration (`board.py`, the state annotations).
- **Flows** run from the writer to each reader ("X now writes F; Y reads it", `stories.py`, `board.build_flows`).
- **The `field_mutation` finding** lists "N other function(s) access this field" and goes to the model as a side effect
  to judge (`detectors/field_mutation.py`, `judge_side_effects`, the strong model's review facts).
- **Story links** join any two stories that touch the field with a strong "data" link (`reading.story_links`), and the
  rules' grouping joins pieces by data edges (`clusters.py`). A log buffer written all over can glue unrelated stories
  into one thread.

A field like `log_t::buf`, a trace ring or a statistics counter is touched by hundreds of functions; none of that fan-out
helps a reviewer.

## 2. Goals

1. A field that many functions touch, or that the owner names or marks, is a **shared sink**.
2. A new write to a sink makes no To check rows, no notes on other functions, no flows, no story links, no grouping by
   data, and no model judgement.
3. Sink writes are hidden by default. A per-viewer **Show** control reveals each as one quiet line where it happens.
4. The owner can mark a field as a sink from the review, and unmark it; marks apply to every review from the next run.
5. The review says which sinks it hid and why, so a field the threshold misjudged is visible.

Not goals: plain global variables (they are not in the impact graph today, so they do not fan out); recomputing a review
without a re-run; per-review or per-reviewer sinks.

## 3. Deciding the sinks

### 3.1 Rules

A field node (kind `field`, label `record::field`, or the bare field name when it has no record) is a sink when any of:

- **threshold:** more than `analysis.sink_threshold` distinct functions **outside the change** read or write it,
  counting precise and name-matched (heuristic) accesses, in the impact graph's live edges (`reads`/`writes`, status not
  `removed`). `0` turns the threshold off.
- **listed:** its label matches a pattern in `analysis.sink_fields` (`fnmatch`, case-sensitive), e.g. `log_t::*`,
  `*::trace_buf`, `stats_t::tx_*`.
- **marked:** the owner marked its label (§6).

The first rule that matches gives the reason, in the order marked, listed, threshold.

### 3.2 Configuration

```yaml
analysis:
  sink_threshold: 20          # a field more than this many unchanged functions touch is a shared sink; 0 = off
  sink_fields: []             # fnmatch patterns on record::field, always sinks
```

### 3.3 Where it is decided

A new module `sinks.py`:

```python
class SinkInfo(BaseModel):
    field: str                 # the field node id
    label: str                 # record::field
    users: int                 # distinct unchanged functions that read or write it
    why: Literal["marked", "listed", "threshold"]

def find_sinks(im: ImpactModel, changed: set[str], threshold: int, patterns: list[str],
               marked: set[str]) -> dict[str, SinkInfo]
```

`changed` is the impact model's changed function ids. Each function counts once, whatever its edges' confidence. The
pipeline calls it once per run, right after the impact model is built (`ctx["impact"]`) and before the detectors, and keeps the
result in the run context (`ctx["sinks"]`) and in the review's blobs (`sinks`), so every consumer reads the same set.

### 3.4 Cache

The stories cache key (`brief.cache_key(ps, model, rules_version, agree)`) gains a `sinks` argument, the sorted sink
labels, so marking or unmarking a field regroups the
stories on the next run. The thread-text cache key already includes the threads prompt, which changes with the links.

## 4. What each consumer does with a sink

| Consumer | With a sink field |
|---|---|
| `detect_field_mutation` | The "now writes F" finding is still made, with `sink=True`, severity `info`, `side_effect=False`, no "other functions access this field" evidence and no field node in `nodes`. "No longer writes F" for a sink is also flagged `sink=True`. A new function's one "writes N field(s)" summary is unchanged (it lists no users). |
| `judge_side_effects`, strong-model review facts | Never see it (`side_effect=False`; facts skip sink fields and say instead "`F` is a shared sink (N users); its users are not listed"). |
| Board state annotations | Only the writer's own lines, each flagged `sink=True`. No notes on other readers or writers, no name-match notes, no note on the field's declaration. |
| Flows (`build_flows` state flows) | None through a sink field. |
| To check (`reading.py` check 5) | No reader rows for a sink field. |
| Story links (`story_links`) | Sink fields' read and write edges are ignored for data links. |
| Rules grouping (`clusters.py`) | Sink fields' data edges do not join pieces. |
| Story text, headline, counts | A sink finding counts nowhere (not in hazards, open checks or the headline). |

## 5. Showing sinks

### 5.1 Reading

`Reading` gains `sinks: list[SinkHit]`: the sinks this change writes, each with `label`, `users`, `why`, and the
writers in the change (`writers: list[str]`, node ids). It is empty when the change writes no sink.

### 5.2 Overview

In the overview's "not analysed" area, when `sinks` is not empty, one line:

> 2 shared sinks hidden: `log_t::buf` (312 functions), `stats_t::tx` (in tortoise.yaml) · **Show**

- The reason reads "N functions" (threshold), "in tortoise.yaml" (listed) or "marked" (marked).
- **Show** / **Hide** toggles a per-viewer setting kept in the browser (`localStorage`, wrapped in try/catch; hidden when
  unavailable).
- The owner sees **unmark** after each marked sink (§6).

### 5.3 Board and story page

`Finding` and board annotations gain `sink: bool = False`. With Show off, those flagged `sink` are not drawn, and sink findings are left out of the story
page's findings. With Show on, each appears in its quiet form: the writer's State note reads
"writes `log_t::buf` — a shared sink (312 functions); its users are not checked", styled as info, and the finding is
listed under the story's findings with the same text.

## 6. Marking

### 6.1 Storage and API

Marks live in the store's `kv` table under `sink_marks` as a sorted list of labels.

- `GET /api/sinks` (any signed-in user): `{"threshold": int, "patterns": [str], "marked": [str]}`.
- `PUT /api/sinks/{label}` and `DELETE /api/sinks/{label}` (owner only, 403 otherwise): add or remove a mark; return
  the same body as GET. The label is URL-encoded (`::` in it).

### 6.2 Controls

The owner (`is_owner`) sees **Treat `F` as a sink** on:

- a `field_mutation` finding's detail ("now writes F");
- a To check reader row ("`R` reads `F`, which `W` now writes");
- the field's declaration note on the board ("new writer: … · readers: …").

After a click: the control reads "Marked — re-run to apply" with a **Re-run** button (the existing re-run). Others see
no control.

### 6.3 Health page

A "Shared sinks" section: the threshold, the YAML patterns, and the marked labels; the owner gets **unmark** on each
marked label.

## 7. Testing

pytest:

- `find_sinks`: over and at the threshold (strictly more than); precise and heuristic users counted once per function;
  changed functions not counted; `0` turns it off; patterns match `record::field` and a bare field; marked; the reason's
  precedence.
- detector: a sink write makes one `sink=True`, `side_effect=False` finding with no other-users evidence; "no longer
  writes" a sink is flagged `sink=True`.
- board: only the writer's own `sink` notes; no notes on other users, name matches or the declaration; no flows.
- reading: no reader rows; no data links through a sink; `Reading.sinks` lists the hit with its writers.
- clusters: two pieces joined only by a sink field stay apart.
- facts: a sink field gets the one-line summary.
- cache: the stories cache key changes when the sink set changes.
- store and API: marks persist; GET for anyone; PUT/DELETE owner-only (403 for others); labels with `::`.
- pipeline: `ctx["sinks"]` and the `sinks` blob; a mark changes the next run.

vitest: the overview's sink line text for each reason; Show/Hide filtering of `sink` annotations and findings.

e2e (rules server): the fixture gains a `log_t::buf` field written from more than 20 unchanged functions and newly from
a changed one. A review shows no reader rows and the overview line; Show reveals the writer's quiet note; the owner
marks another field from a To check row, re-runs, and its rows are gone; unmark brings them back after a re-run.
