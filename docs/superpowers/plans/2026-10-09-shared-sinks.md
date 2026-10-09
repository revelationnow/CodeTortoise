# Shared Sinks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fields that many functions touch (a log buffer, a trace ring, a statistics counter), or that the owner names or
marks, stop fanning out into To check rows, board notes, flows, story links, grouping and model judgement; a viewer
can show them as quiet lines.

**Architecture:** The impact model decides the shared sinks once per run (`ImpactModel.sinks`, computed by
`sinks.find_sinks` inside `build_impact`, before the blast radius), so every consumer that already holds the impact model
reads the same set: the detector flags sink findings, the board keeps only the writer's quiet note, `altered_access`
ignores sinks (clusters, pieces, board fields), reading drops reader rows and data links and lists the hits, and the
strong model never sees sink findings. Marks live in the store's `kv` table; `/api/sinks` reads and (owner) writes them.
The browser hides `sink` annotations and findings in the API layer unless the viewer's stored Show is on.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, SQLite; React 19 + TypeScript, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-09-shared-sinks-design.md`

## Global Constraints

- Worktree: `/media/anoop/ssd_1/Work/CodeTortoise/.worktrees/sinks` (branch `sinks`). All paths below are relative to it.
- Python: run from `backend/` with
  `env PYTHONPATH=/media/anoop/ssd_1/Work/CodeTortoise/.worktrees/sinks/backend /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest ...`
  (written `PYTEST` below). Never use `uv`.
- Lint: from `backend/`, `/media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/ruff check codetortoise tests` (written `RUFF`).
- Frontend: the worktree needs `frontend/node_modules` symlinked to the main checkout's
  (`ln -s /media/anoop/ssd_1/Work/CodeTortoise/frontend/node_modules frontend/node_modules`); remove the symlink before
  any `git worktree remove`. Unit tests `npx vitest run`, type check and build `npm run build`.
- e2e: `npm run build` first, then from `frontend/`:
  `TMPDIR=$CLAUDE_JOB_DIR/tmp/pw TORTOISE_CMD="env PYTHONPATH=/media/anoop/ssd_1/Work/CodeTortoise/.worktrees/sinks/backend /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test`.
  Known flake: the first full run may time out one to three `startReview` calls; they pass on `--last-failed`.
- Commits: `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`, message ending with the line
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.
- Config (spec §3.2): `analysis.sink_threshold: 20` (strictly more than this many unchanged functions; `0` = off),
  `analysis.sink_fields: []` (case-sensitive `fnmatch` patterns on the field label `record::field`, or the bare name).
- Reason order (spec §3.1): marked, then listed, then threshold. Reason text: threshold `"N functions"`, listed
  `"in tortoise.yaml"`, marked `"marked"`.
- Marks: store `kv` key `sink_marks`, a sorted list of labels. `GET /api/sinks` any signed-in user;
  `PUT`/`DELETE /api/sinks/{label}` owner only (403 otherwise). Body: `{"threshold": int, "patterns": [str], "marked": [str]}`.
- Copy (spec §5): the writer's quiet note and sink finding say
  `writes {label}{how} — a shared sink ({reason}); its users are not checked`; the overview line is
  ``N shared sink(s) hidden: `label` (reason), …`` with **Show**/**Hide**; the owner control is ``Treat `F` as a sink``,
  then `Marked — re-run to apply` with **Re-run**.
- Browser storage key `ct.sinks.show` (per viewer; hidden when missing or unreadable).

## Review Focus

1. A field whose name matches pass `heuristic_fanin_cap` gets no edges (only `im.capped[label]`); it must still count
   toward the threshold, or the real log buffer is never a sink. Pinned in Task 1 (`test_name_matches_over_the_cap_count`).
2. Reviews and boards stored before this change have no `sinks`, `sink` or `field` keys, and the Reviews list rebuilds
   the headline from a stored `reading_head` blob whose findings are 4-item rows; all must still load. Pinned in Task 4
   (`test_a_headline_stored_before_sinks_still_reads`).
3. A label in the URL holds `::` and may hold `/` (a nested record) or `%`; marking must store exactly that label.
   Pinned in Task 6 (`test_a_label_with_a_slash_or_percent_is_stored_as_given`).
4. Browser storage that throws or is missing must leave sinks hidden and the toggle must not throw. Pinned in Task 7.
5. A cached strong-model brief must not be reused after the sink set changes (it grouped stories by the sink's links).
   Pinned in Task 5 (`test_the_cache_key_changes_with_the_shared_sinks`).

---

### Task 1: Decide the sinks once per run

**Files:**
- Modify: `backend/codetortoise/config.py` (class `AnalysisConfig`, after `entrypoint_patterns`)
- Modify: `backend/codetortoise/impact.py` (new `SinkInfo`; `ImpactModel.sinks`; `build_impact(..., marked)`; `_blast`)
- Create: `backend/codetortoise/sinks.py`
- Modify: `backend/codetortoise/pipeline.py` (stage `impact()`)
- Test: `backend/tests/test_sinks.py` (new), `backend/tests/test_impact.py`, `backend/tests/test_config.py`

**Interfaces:**
- Produces:
  - `codetortoise.impact.SinkInfo(field: str, label: str, users: int, why: Literal["marked", "listed", "threshold"])`
  - `ImpactModel.sinks: dict[str, SinkInfo]` (field node id → info; `{}` by default and for stored models)
  - `build_impact(before, after, dm, sel, index, layers, cfg, marked: Collection[str] = ()) -> ImpactModel`
  - `codetortoise.sinks.find_sinks(im: ImpactModel, threshold: int, patterns: list[str], marked: Collection[str]) -> dict[str, SinkInfo]`
  - `codetortoise.sinks.why_text(s) -> str` (any object with `why` and `users`)
  - `codetortoise.sinks.MARKS_KEY = "sink_marks"`, `marks(store) -> list[str]`, `set_mark(store, label: str, on: bool) -> list[str]`
  - `AnalysisConfig.sink_threshold: int = 20`, `AnalysisConfig.sink_fields: list[str] = []`

Ruling carried from planning: spec §3.3 keeps the sinks "in the run context (`ctx["sinks"]`) and in the review's blobs
(`sinks`)". They live on the impact model instead (`ImpactModel.sinks`), which is both `ctx["impact"]` and the stored
`impact` blob: every consumer already holds the impact model, and `build_impact` needs them before the blast radius.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_sinks.py`:

```python
"""Shared sinks (spec 2026-10-09-shared-sinks §3): which fields a run treats as sinks, and the owner's marks."""
from codetortoise.impact import Edge, ImpactModel, Node, SinkInfo
from codetortoise.sinks import MARKS_KEY, find_sinks, marks, set_mark, why_text


def _im(readers=3, capped=0, label="log_t::buf"):
    """N1 (changed) newly writes field N2; `readers` unchanged functions each read it and write it by name match."""
    nodes = {"N1": Node(id="N1", key="c:w", label="w", status="changed"),
             "N2": Node(id="N2", key="field:buf", kind="field", label=label)}
    edges = [Edge(id="E1", src="N1", dst="N2", kind="writes", status="added")]
    for i in range(readers):
        nid = f"N{3 + i}"
        nodes[nid] = Node(id=nid, key=f"c:r{i}", label=f"r{i}")
        edges.append(Edge(id=f"E{2 + 2 * i}", src=nid, dst="N2", kind="reads"))
        edges.append(Edge(id=f"E{3 + 2 * i}", src=nid, dst="N2", kind="writes", confidence="heuristic"))
    return ImpactModel(nodes=nodes, edges=edges, changed=["N1"], capped={label: capped} if capped else {})


def test_a_field_more_unchanged_functions_touch_than_the_threshold_is_a_sink():
    assert find_sinks(_im(3), 2, [], ()) == {"N2": SinkInfo(field="N2", label="log_t::buf", users=3, why="threshold")}
    assert find_sinks(_im(3), 3, [], ()) == {}          # at the threshold: not a sink; the changed writer never counts


def test_a_removed_access_does_not_count():
    im = _im(2)
    im.nodes["N9"] = Node(id="N9", key="c:gone", label="gone")
    im.edges.append(Edge(id="E99", src="N9", dst="N2", kind="reads", status="removed"))
    assert find_sinks(im, 2, [], ()) == {}


def test_name_matches_over_the_cap_count():
    assert find_sinks(_im(1, capped=40), 20, [], ())["N2"].users == 41


def test_a_threshold_of_zero_turns_it_off():
    assert find_sinks(_im(100), 0, [], ()) == {}


def test_patterns_match_the_record_and_field_or_a_bare_field_case_sensitively():
    assert find_sinks(_im(0), 0, ["log_t::*"], ())["N2"].why == "listed"
    assert find_sinks(_im(0, label="trace_buf"), 0, ["trace_buf"], ())["N2"].why == "listed"
    assert find_sinks(_im(0, label="trace_buf"), 0, ["*::buf"], ()) == {}
    assert find_sinks(_im(0), 0, ["LOG_T::*"], ()) == {}


def test_marked_beats_listed_beats_threshold():
    assert find_sinks(_im(30), 20, ["log_t::*"], {"log_t::buf"})["N2"].why == "marked"
    assert find_sinks(_im(30), 20, ["log_t::*"], ())["N2"].why == "listed"
    assert find_sinks(_im(30), 20, [], {"other::x"})["N2"].why == "threshold"


def test_why_text():
    assert [why_text(SinkInfo(field="N2", label="a::b", users=312, why=w)) for w in ("threshold", "listed", "marked")] \
        == ["312 functions", "in tortoise.yaml", "marked"]


class _KV:
    def __init__(self):
        self.rows = {}

    def kv_get(self, key):
        return self.rows.get(key)

    def kv_put(self, key, obj):
        self.rows[key] = obj


def test_marks_are_a_sorted_set_of_labels_in_the_store():
    kv = _KV()
    assert marks(kv) == []
    assert set_mark(kv, "log_t::buf", True) == ["log_t::buf"]
    assert set_mark(kv, "Uart::errors", True) == ["Uart::errors", "log_t::buf"]
    assert set_mark(kv, "Uart::errors", True) == ["Uart::errors", "log_t::buf"]
    assert set_mark(kv, "log_t::buf", False) == ["Uart::errors"]
    assert kv.rows[MARKS_KEY] == ["Uart::errors"]
    kv.rows[MARKS_KEY] = "junk"
    assert marks(kv) == []
```

Append to `backend/tests/test_impact.py`:

```python
def test_the_impact_model_names_its_shared_sinks_and_the_blast_radius_skips_them(analysed):
    from codetortoise.config import AnalysisConfig
    from codetortoise.impact import build_impact

    a = analysed
    assert a.impact.sinks == {}                         # the fixture's fields have few users
    cfg = AnalysisConfig(module_min_files=1)
    plain = build_impact(a.before, a.after, a.dm, a.sel, None, a.layers, cfg)
    data = lambda im: {im.nodes[b.node].label for b in im.blast if b.via == "data"}    # noqa: E731
    assert "uart_errors" in data(plain)
    im = build_impact(a.before, a.after, a.dm, a.sel, None, a.layers, cfg, marked=["Uart::errors"])
    assert [(s.label, s.why) for s in im.sinks.values()] == [("Uart::errors", "marked")]
    assert "uart_errors" not in data(im)


def test_an_impact_model_stored_before_sinks_loads_without_them():
    from codetortoise.impact import ImpactModel
    assert ImpactModel.model_validate({"nodes": {}, "edges": []}).sinks == {}
```

Append to `backend/tests/test_config.py`:

```python
def test_shared_sink_settings_default_to_a_threshold_of_20_and_no_patterns():
    from codetortoise.config import AnalysisConfig
    a = AnalysisConfig()
    assert (a.sink_threshold, a.sink_fields) == (20, [])
    assert AnalysisConfig.model_validate({"sink_threshold": 0, "sink_fields": ["log_t::*"]}).sink_fields == ["log_t::*"]
```

- [ ] **Step 2: Run them to see them fail**

Run (from `backend/`): `PYTEST tests/test_sinks.py tests/test_impact.py tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'SinkInfo'` (test_sinks), `AttributeError ... 'sinks'`, `sink_threshold`.

- [ ] **Step 3: Implement**

`backend/codetortoise/config.py`, in `AnalysisConfig` after `entrypoint_patterns`:

```python
    sink_threshold: int = 20       # a field more unchanged functions than this touch is a shared sink; 0 = off
    sink_fields: list[str] = Field(default_factory=list)   # fnmatch patterns on record::field: always shared sinks
```

`backend/codetortoise/impact.py`: add `from collections.abc import Callable, Collection` (replace the `Callable` import),
then after `class FanOut`:

```python
class SinkInfo(BaseModel):
    """A field so many functions touch, or the owner names, that a new write to it says nothing about its users
    (spec 2026-10-09-shared-sinks §3)."""
    field: str                                      # the field node id
    label: str                                      # record::field
    users: int                                      # distinct unchanged functions reading or writing it
    why: Literal["marked", "listed", "threshold"]
```

In `ImpactModel`, after `capped`:

```python
    sinks: dict[str, SinkInfo] = Field(default_factory=dict)   # field node id -> why it is a shared sink
```

`build_impact` gains `marked: Collection[str] = ()` as its last parameter; after `model.changed = ...` and before
`_flows(model, cfg)`:

```python
    from codetortoise.sinks import find_sinks            # sinks.py builds on this module's models
    model.sinks = find_sinks(model, cfg.sink_threshold, cfg.sink_fields, marked)
```

In `_blast`, the data step skips sinks:

```python
            if n in seeds:
                for w in writes_from.get(n, []):
                    if w.dst in model.sinks:              # a shared sink's users are not affected code
                        continue
                    for u in field_users.get(w.dst, []):
```

`backend/codetortoise/sinks.py`:

```python
"""Shared sinks (spec 2026-10-09-shared-sinks): fields like a log buffer that so many functions touch that a new write
to one says nothing about its users. A run decides them once, on the impact model; every view leaves their users out."""
from __future__ import annotations

import fnmatch
from collections import defaultdict
from collections.abc import Collection
from typing import Any

from codetortoise.impact import ImpactModel, SinkInfo

MARKS_KEY = "sink_marks"          # the store's kv row: the owner's marked labels, for every review of the workspace


def find_sinks(im: ImpactModel, threshold: int, patterns: list[str], marked: Collection[str]) -> dict[str, SinkInfo]:
    """Field node id -> why it is a sink: the owner marked its label, a pattern matches it, or more than `threshold`
    unchanged functions read or write it (precise and name-matched alike, plus name matches over the fan-in cap)."""
    changed = set(im.changed)
    who: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if e.kind in ("reads", "writes") and e.status != "removed" and e.src not in changed:
            who[e.dst].add(e.src)
    marked = set(marked)
    out: dict[str, SinkInfo] = {}
    for nid, n in im.nodes.items():
        if n.kind != "field":
            continue
        users = len(who.get(nid, ())) + im.capped.get(n.label, 0)
        if n.label in marked:
            why = "marked"
        elif any(fnmatch.fnmatchcase(n.label, p) for p in patterns):
            why = "listed"
        elif threshold > 0 and users > threshold:
            why = "threshold"
        else:
            continue
        out[nid] = SinkInfo(field=nid, label=n.label, users=users, why=why)
    return out


def why_text(s: Any) -> str:
    """Why a field is a sink, as the review says it: "312 functions", "in tortoise.yaml" or "marked"."""
    return {"threshold": f"{s.users} functions", "listed": "in tortoise.yaml", "marked": "marked"}[s.why]


def marks(store: Any) -> list[str]:
    got = store.kv_get(MARKS_KEY)
    return sorted(x for x in got if isinstance(x, str)) if isinstance(got, list) else []


def set_mark(store: Any, label: str, on: bool) -> list[str]:
    """Mark or unmark `label` for every review from the next run; the marks after."""
    cur = set(marks(store))
    cur = cur | {label} if on else cur - {label}
    store.kv_put(MARKS_KEY, sorted(cur))
    return sorted(cur)
```

`backend/codetortoise/pipeline.py`, stage `impact()`:

```python
    def impact():
        im = build_impact(ctx["before"], ctx["after"], ctx["dm"], ctx["sel"], svc.index, ctx.get("layers"), cfg.analysis,
                          marked=sink_marks(store))
        ctx["impact"] = im
        store.put_blob(rid, "impact", im)
        return (f"{len(im.nodes)} node(s), {len(im.edges)} edge(s), blast {len(im.blast)}"
                + (f", {len(im.sinks)} shared sink(s)" if im.sinks else ""))
```

with `from codetortoise.sinks import marks as sink_marks` among the imports.

- [ ] **Step 4: Run them to see them pass**

Run: `PYTEST tests/test_sinks.py tests/test_impact.py tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Whole suite and lint**

Run: `PYTEST -q -x` then `RUFF`
Expected: all pass (688+ passed, 1 skipped); ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/impact.py backend/codetortoise/sinks.py \
        backend/codetortoise/pipeline.py backend/tests/test_sinks.py backend/tests/test_impact.py backend/tests/test_config.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(sinks): a run decides its shared sinks once, from the threshold, tortoise.yaml and the owner's marks; the blast radius skips them

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The detector flags a sink write and lists no users

**Files:**
- Modify: `backend/codetortoise/detectors/base.py` (`Finding.sink`)
- Modify: `backend/codetortoise/detectors/field_mutation.py`
- Test: `backend/tests/test_detectors.py`

**Interfaces:**
- Consumes: `ImpactModel.sinks`, `SinkInfo`, `why_text` (Task 1).
- Produces: `Finding.sink: bool = False`. A sink's "now writes" finding: `kind="field_mutation"`, `severity="info"`,
  `side_effect=False`, `sink=True`, `nodes=[writer id]` (no field node), evidence = the writer's own accesses, title as
  before (`"{fn} now writes {label}"` plus `" through a local alias"`). A sink's "no longer writes" finding: as before
  plus `sink=True`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_detectors.py`:

```python
def test_a_write_to_a_shared_sink_is_flagged_lists_no_users_and_is_not_a_side_effect():
    from codetortoise.detectors.field_mutation import detect_field_mutation
    from codetortoise.impact import SinkInfo

    ctx = _mutation_ctx("changed", [])
    (plain,) = detect_field_mutation(ctx)
    assert plain.side_effect and not plain.sink and any("other function" in e.text for e in plain.evidence)
    ctx.impact.sinks = {"N2": SinkInfo(field="N2", label="B::ptr", users=40, why="threshold")}
    (f,) = detect_field_mutation(ctx)
    assert (f.kind, f.severity, f.side_effect, f.sink, f.title, f.nodes) == (
        "field_mutation", "info", False, True, "f now writes B::ptr", ["N1"])
    assert [e.text for e in f.evidence] == ["write `out.ptr` (precise)"]
    assert f.summary == "f newly modifies B::ptr, a shared sink (40 functions); its users are not checked."


def test_no_longer_writing_a_shared_sink_is_flagged_too():
    from codetortoise.detectors.field_mutation import detect_field_mutation
    from codetortoise.impact import SinkInfo

    ctx = _mutation_ctx("changed", [])
    ctx.before, ctx.after = ctx.after, ctx.before      # f wrote B::ptr before and does not now
    (plain,) = detect_field_mutation(ctx)
    assert plain.title == "f no longer writes B::ptr" and not plain.sink
    ctx.impact.sinks = {"N2": SinkInfo(field="N2", label="B::ptr", users=3, why="marked")}
    (f,) = detect_field_mutation(ctx)
    assert f.title == "f no longer writes B::ptr" and f.sink
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTEST tests/test_detectors.py -q -k sink`
Expected: FAIL — `AttributeError: 'Finding' object has no attribute 'sink'` (or `ValueError` setting it).

- [ ] **Step 3: Implement**

`backend/codetortoise/detectors/base.py`, in `Finding` after `side_effect`:

```python
    sink: bool = False                      # a write to a shared sink: shown only when the reader asks (spec 2026-10-09)
```

`backend/codetortoise/detectors/field_mutation.py`: import `from codetortoise.sinks import why_text`. In the "now writes"
loop, compute the field node and its sink first and branch before the users are gathered:

```python
        for key in sorted(set(wa) - set(wb)):
            accesses = wa[key]
            a0 = accesses[0]
            field_node = im.node_by_key(f"field:{a0.field}")
            label = field_node.label if field_node else a0.field_name
            alias = any(not v.startswith("call:") for a in accesses for v in a.via)
            title = f"{node.label} now writes {label}" + (" through a local alias" if alias else "")
            sink = im.sinks.get(field_node.id) if field_node else None
            if sink is not None:
                # a shared sink (spec 2026-10-09 §4): the writer's own lines; its users are neither listed nor judged
                findings.append(Finding(
                    kind="field_mutation", severity="info", sink=True, title=title, nodes=[nid],
                    evidence=[Evidence(text=f"{a.mode} `{a.path}`" + (f" via {' -> '.join(a.via)}" if a.via else "")
                                       + f" ({a.confidence})", file=a.file, line=a.line) for a in accesses],
                    summary=f"{node.label} newly modifies {label}, a shared sink ({why_text(sink)}); its users are not "
                            "checked."))
                continue
            others, heuristic = [], []
            if field_node is not None:
                ...                                   # unchanged from here, using `label` and `title` above
```

and the existing `Finding(...)` at the end of that loop uses `title=title` (delete the old `label =`, `alias =` lines).
In the "no longer writes" loop:

```python
        for key in sorted(set(wb) - set(wa)):
            a0 = wb[key][0]
            gone = im.node_by_key(f"field:{a0.field}")
            findings.append(Finding(
                kind="field_mutation", severity="low", title=f"{node.label} no longer writes {a0.record}::{a0.field_name}",
                sink=gone is not None and gone.id in im.sinks,
                ...))                                  # the rest unchanged
```

- [ ] **Step 4: Run them to see them pass**

Run: `PYTEST tests/test_detectors.py -q`
Expected: PASS (the fixture's F5/F6 titles unchanged).

- [ ] **Step 5: Whole suite, lint, commit**

Run: `PYTEST -q -x` and `RUFF`. Expected: pass, clean.

```bash
git add backend/codetortoise/detectors backend/tests/test_detectors.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(sinks): a write to a shared sink is a flagged finding that lists no users and is no side effect to judge

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Board, flows and grouping leave sinks' users out

**Files:**
- Modify: `backend/codetortoise/board.py` (`Impact`; `build_impacts`; `_required`; `_neighbours`)
- Modify: `backend/codetortoise/clusters.py` (`altered_access`, `cluster_change`)
- Modify: `backend/codetortoise/pieces.py` (both `altered_access` calls)
- Modify: `backend/codetortoise/stories.py:250` (`altered_access` call)
- Test: `backend/tests/test_board.py`, `backend/tests/test_clusters.py`, `backend/tests/test_pieces.py`

**Interfaces:**
- Consumes: `ImpactModel.sinks`, `why_text` (Task 1); `Finding.sink` (Task 2).
- Produces:
  - `board.Impact.sink: bool = False`, `board.Impact.field: str | None = None` (set on a field declaration's note: the
    field's label).
  - `clusters.altered_access(e, sinks: Collection[str] = ()) -> bool` — False for an edge into a sink.
  - A sink write's board notes: only the writer's lines, severity `info`, `sink=True`, text
    `writes {label}{how} — a shared sink ({why}); its users are not checked`; no landing, so no flow.
  - Sink field nodes are neither required nor neighbours on any board or story graph.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_board.py`:

```python
def _sunk(why="threshold", users=40):
    from codetortoise.impact import SinkInfo
    ctx, _ = _synthetic()
    ctx.impact.sinks = {"N2": SinkInfo(field="N2", label="R::v", users=users, why=why)}
    return ctx


def test_a_write_to_a_shared_sink_is_one_quiet_note_on_the_writer_and_no_flow():
    b = build_board(_sunk())
    state = [i for i in b.impacts if i.channel == "state"]
    assert [(i.node, i.line, i.severity, i.sink, i.landing, i.text) for i in state] == [
        ("N1", 5, "info", True, False,
         "writes R::v through alias `p` — a shared sink (40 functions); its users are not checked")]
    assert [f.tag for f in b.flows] == ["contract"]
    assert "N2" not in {n.id for n in b.nodes}


def test_a_field_declarations_note_names_the_field_for_the_owners_mark():
    b = build_board(_synthetic()[0])
    (decl,) = [i for i in b.impacts if i.node == "N2"]
    assert decl.field == "R::v" and not decl.sink
    assert all(i.field is None for i in b.impacts if i.node != "N2")
```

Append to `backend/tests/test_clusters.py`:

```python
def test_a_shared_sink_joins_no_code_and_no_board_requires_it():
    from codetortoise.impact import SinkInfo
    g = G()
    a, b = g.fn("uart_send", "drv/uart.c"), g.fn("logger_put", "svc/logger.c")
    buf = g.field("log_t::buf")
    g.edge(a, buf, "writes", "added")
    g.edge(b, buf, "writes", "added")
    assert members(g.run()) == [sorted([a, b])]
    g.im.sinks = {buf: SinkInfo(field=buf, label="log_t::buf", users=300, why="threshold")}
    res = g.run()
    assert members(res) == sorted([[a], [b]])
    assert all(buf not in c.required for c in res.clusters)
```

Append to `backend/tests/test_pieces.py`:

```python
def test_a_shared_sink_links_no_pieces():
    from codetortoise.impact import SinkInfo
    c = _world([_edit("stack_one", "a/x.c"), _edit("other_two", "b/y.c")],
               fields=[("stack_one", "log_t", "buf", "write", "added"), ("other_two", "log_t", "buf", "write", "added")])
    assert any(lk.type == "field" for lk in _pieces(c).links)
    c.impact.sinks = {"N3": SinkInfo(field="N3", label="log_t::buf", users=300, why="threshold")}
    assert not any(lk.type == "field" for lk in _pieces(c).links)
```

If the pieces test's first assertion fails because both functions land in one piece, put them in two CLs with
`_cls(c, {"a/x.c": 1, "b/y.c": 2})` (pieces never span two CLs; links still join pieces across CLs) — fix the fixture,
not the production code.

- [ ] **Step 2: Run them to see them fail**

Run: `PYTEST tests/test_board.py tests/test_clusters.py tests/test_pieces.py -q -k "sink or declarations_note"`
Expected: FAIL (no `sink`/`field` on `Impact`; clusters still joined; field link present).

- [ ] **Step 3: Implement**

`backend/codetortoise/clusters.py`:

```python
def altered_access(e, sinks: Collection[str] = ()) -> bool:
    """A field access the change added or removed: what joins code and what a board must show. A shared sink's
    (spec 2026-10-09) joins nothing."""
    return e.kind in ("writes", "reads") and e.status != "unchanged" and e.dst not in sinks
```

(add `Collection` to its `collections.abc` import) and in `cluster_change` `if altered_access(e, im.sinks) and ...`.

`backend/codetortoise/pieces.py`: both `altered_access(e)` calls become `altered_access(e, im.sinks)` (in `_links`
`im = x.im` is already bound; in the drafts code `im` is the impact model there too — check the name in scope and use it).

`backend/codetortoise/stories.py:250`: `altered_access(e, im.sinks)`.

`backend/codetortoise/board.py`:

- `Impact`, after `refs`:

```python
    sink: bool = False               # a write to a shared sink: drawn only when the reader shows them (spec 2026-10-09)
    field: str | None = None         # a field declaration's note: the field's label (the owner may mark it a sink)
```

- import `from codetortoise.sinks import why_text`.
- a helper above `build_impacts`:

```python
def _how(a: FieldAccess) -> str:
    alias = [v for v in a.via if not v.startswith("call:")]
    return f" through alias `{alias[0]}`" if alias else (f" via {a.via[0][5:]}()" if a.via else "")
```

- `add(...)` gains `sink=False, field=None` and passes `sink=sink, field=field` to `Impact(...)`.
- the "state" section of `build_impacts` becomes:

```python
        # state: fields this function newly writes
        for field, accs in sorted(_new_writes(x, node.key).items()):
            a0 = accs[0]
            fid = x.id_of.get(f"field:{field}")
            label = f"{a0.record}::{a0.field_name}" if a0.record else a0.field_name
            sink = x.im.sinks.get(fid) if fid else None
            if sink is not None:
                # a shared sink (spec 2026-10-09 §4): the writer's own lines, quiet; nobody else is annotated
                fm = next((f.id for f in x.c.findings if f.sink and f.kind == "field_mutation" and nid in f.nodes
                           and f.title.startswith(f"{node.label} now writes {label}")), None)
                for a in accs:
                    add(nid, a.file, a.line, "info", "state", "State",
                        f"writes {label}{_how(a)} — a shared sink ({why_text(sink)}); its users are not checked", fm,
                        refs=[fid], sink=True)
                continue
            # the finding for this field (a function writing several fields has one finding per field)
            fm = ...                                  # unchanged
            st: Sev = ...                             # unchanged
            for a in accs:
                add(nid, a.file, a.line, st, "state", "State", f"writes {label}{_how(a)}", fm, refs=[fid])
            ...                                       # readers, writers, name matches: unchanged
                    add(fid, a0.record_file, a0.decl_line, st if readers or writers else "info", "state", "State",
                        text, fm, refs=named, field=label)
```

- `_required`: `if altered_access(e, x.im.sinks) and e.src in own and e.dst in x.im.nodes:`
- `_neighbours`: `if e.kind in ("writes", "reads") and e.src in scope and e.src in x.changed and e.dst in x.im.nodes and e.dst not in x.im.sinks:`

- [ ] **Step 4: Run them to see them pass**

Run: `PYTEST tests/test_board.py tests/test_clusters.py tests/test_pieces.py tests/test_stories.py -q`
Expected: PASS.

- [ ] **Step 5: Whole suite, lint, commit**

Run: `PYTEST -q -x` and `RUFF`. Expected: pass, clean.

```bash
git add backend/codetortoise/board.py backend/codetortoise/clusters.py backend/codetortoise/pieces.py \
        backend/codetortoise/stories.py backend/tests/test_board.py backend/tests/test_clusters.py backend/tests/test_pieces.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(sinks): a shared sink gets one quiet note on its writer; no notes on its users, no flows, and it joins no clusters or pieces

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The reading drops sinks' readers and links and lists the hits

**Files:**
- Modify: `backend/codetortoise/reading.py` (`Check.field`; new `SinkHit`, `Reading.sinks`, `sink_hits`; `story_links`;
  `_profiles`; `build_checks` (findings loop and check 5); `headline`; `headline_facts`; `build_reading`)
- Test: `backend/tests/test_reading.py`

**Interfaces:**
- Consumes: `ImpactModel.sinks`, `SinkInfo` (Task 1); `Finding.sink` (Task 2).
- Produces:
  - `reading.SinkHit(field: str, label: str, users: int, why: Literal[...], writers: list[str])` — writers are changed
    function ids whose write to the sink the change added or removed, ordered by label.
  - `Reading.sinks: list[SinkHit]` (default `[]`), sorted by label.
  - `Check.field: str | None = None` — a reader row's field label.
  - `sink_hits(x: _Ctx) -> list[SinkHit]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_reading.py`:

```python
def _sink(c, label, why="threshold", users=300):
    from codetortoise.impact import SinkInfo
    nid = next(n.id for n in c.impact.nodes.values() if n.label == label)
    c.impact.sinks = {nid: SinkInfo(field=nid, label=label, users=users, why=why)}
    return nid


def _logged():
    return _world([_edit("config", "drv/cfg.c"), _same("report", "svc/rep.c"), _edit("dump", "svc/dump.c")],
                  fields=[("config", "Log", "buf", "write", "added"), ("report", "Log", "buf", "read", "unchanged"),
                          ("dump", "Log", "buf", "read", "unchanged")])


def test_a_reader_row_names_its_field_and_a_shared_sink_has_no_reader_rows():
    c, ss = _logged(), _set(["N1"], ["N3"])
    (row,) = _checks(c, ss)[0]
    assert (row.kind, row.field) == ("reader", "Log::buf")
    _sink(c, "Log::buf")
    assert _checks(c, ss)[0] == []


def test_a_shared_sink_makes_no_data_link():
    c, ss = _logged(), _set(["N1"], ["N3"])
    assert [lk.kind for lk in story_links(ss, _x(c))] == ["data"]
    _sink(c, "Log::buf")
    assert all(lk.kind != "data" for lk in story_links(ss, _x(c)))


def test_the_reading_lists_each_shared_sink_the_change_writes_with_its_writers():
    c, ss = _logged(), _set(["N1"], ["N3"])
    reading, _ = build_reading(ss, c)
    assert reading.sinks == []
    _sink(c, "Log::buf", why="listed", users=2)
    reading, _ = build_reading(ss, c)
    assert [(h.label, h.users, h.why, h.writers) for h in reading.sinks] == [("Log::buf", 2, "listed", ["N1"])]


def test_a_shared_sink_the_change_only_reads_is_not_listed():
    c = _world([_edit("report", "svc/rep.c"), _same("config", "drv/cfg.c")],
               fields=[("report", "Log", "buf", "read", "added"), ("config", "Log", "buf", "write", "unchanged")])
    _sink(c, "Log::buf")
    reading, _ = build_reading(_set(["N1"]), c)
    assert reading.sinks == []


def test_threads_sharing_only_a_shared_sinks_struct_share_no_vocabulary():
    c = _world([_edit("a_put", "x/a.c"), _edit("b_put", "y/b.c")],
               fields=[("a_put", "Log", "buf", "write", "added"), ("b_put", "Log", "buf", "write", "added")])
    ss = _set(["N1"], ["N2"])
    threads = [Thread(id="T1", name="a", purpose="", stories=["S1"]), Thread(id="T2", name="b", purpose="", stories=["S2"])]
    assert any(k.kind == "vocabulary" for k in connections(threads, ss, _x(c)))
    _sink(c, "Log::buf")
    assert not any(k.kind == "vocabulary" for k in connections(threads, ss, _x(c)))


def test_a_sink_finding_is_no_check_and_never_raises_the_headline():
    c = _world([_edit("send", "drv/uart.c")])
    ss = _set(["N1"])
    sunk = _f("F1", kind="field_mutation", severity="low")
    sunk.sink = True
    c.findings = [sunk]
    rows, cleared = _checks(c, ss)
    assert rows == [] and cleared == []
    assert headline([], set(), [sunk]).text == "No risks found"


def test_a_headline_stored_before_sinks_still_reads():
    from codetortoise.reading import headline_from
    facts = {"checks": [], "cleared": [], "findings": [["F1", "contract", "medium", None]]}
    assert headline_from(facts, {}).text == "Medium risk"
```

Check the imports at the top of `test_reading.py` include `build_reading`, `connections`, `headline`, `story_links`
and `Thread` (add the missing ones to the existing `from codetortoise.reading import (...)`). If the vocabulary test's
first assertion fails because two threads in different folders are not given a vocabulary connection for a shared
struct, read `_connect` and adjust only the fixture (same struct, different files) — not the production code.

- [ ] **Step 2: Run them to see them fail**

Run: `PYTEST tests/test_reading.py -q -k "sink or headline_stored or field_and"`
Expected: FAIL (no `field` on `Check`, reader rows remain, `Reading` has no `sinks`, `f.sink` unknown).

- [ ] **Step 3: Implement**

In `backend/codetortoise/reading.py`:

```python
class SinkHit(BaseModel):
    """A shared sink the change writes (spec 2026-10-09 §5.1): what the overview says it hid."""
    field: str
    label: str
    users: int
    why: Literal["marked", "listed", "threshold"]
    writers: list[str] = Field(default_factory=list)      # changed functions whose write to it the change added or removed
```

- `Check`: add `field: str | None = None   # a reader row's field label (the owner may mark it a shared sink)`.
- `Reading`: add `sinks: list[SinkHit] = Field(default_factory=list)   # shared sinks the change writes, hidden`.
- new function:

```python
def sink_hits(x: _Ctx) -> list[SinkHit]:
    """The shared sinks whose writes the change added or removed, each with those writers."""
    by: dict[str, set[str]] = defaultdict(set)
    for e in x.im.edges:
        if e.kind == "writes" and e.status != "unchanged" and e.src in x.changed and e.dst in x.im.sinks:
            by[e.dst].add(e.src)
    return [SinkHit(**x.im.sinks[f].model_dump(), writers=sorted(w, key=x.label))
            for f, w in sorted(by.items(), key=lambda kv: x.im.sinks[kv[0]].label)]
```

- `story_links`: `new_writes = [e for e in _live(x, {"writes"}) if e.status == "added" and e.dst not in x.im.sinks]`.
- `_profiles`: `if e.src in p.nodes and e.dst not in x.im.sinks:` before `rec = ...`.
- `build_checks`, top of the findings loop: `if f.sink: continue` (first line inside `for f in findings:`).
- `build_checks` check 5: the writes generator gains `and e.dst not in x.im.sinks`, and the row passes the field:
  `add("reader", n, r, path, line, f"...", field=x.label(w.dst))`.
- `headline`: `sev = [f.severity for f in findings if f.kind != "header_fanout" and not getattr(f, "sink", False) and f.id not in done]`.
- `headline_facts`: `"findings": [[f.id, f.kind, f.severity, f.verdict_source] for f in findings if not f.sink]`.
- `build_reading`: `Reading(..., sinks=sink_hits(x))`.

- [ ] **Step 4: Run them to see them pass**

Run: `PYTEST tests/test_reading.py -q`
Expected: PASS.

- [ ] **Step 5: Whole suite, lint, commit**

Run: `PYTEST -q -x` and `RUFF`. Expected: pass, clean.

```bash
git add backend/codetortoise/reading.py backend/tests/test_reading.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(sinks): To check, story links and thread vocabulary leave shared sinks out; the reading lists the sinks it hid

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The strong model never sees a sink; marking one changes the stories cache

**Files:**
- Modify: `backend/codetortoise/facts_prep.py` (`field_facts`)
- Modify: `backend/codetortoise/brief.py` (`cache_key`)
- Modify: `backend/codetortoise/pipeline.py` (stages `stories()`, `review()`)
- Test: `backend/tests/test_facts_prep.py`, `backend/tests/test_tier1_stories.py`, `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `cache_key(ps, model, rules_version, agree, sinks: Collection[str] = ()) -> str` (unchanged hash when
  `sinks` is empty); `field_facts` returns one line for a sink.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_facts_prep.py`:

```python
def test_a_shared_sinks_facts_are_one_line_without_its_users():
    from codetortoise.impact import SinkInfo
    c = _world([_edit("uart_send", "drv/uart.c"), _same("uart_errors", "drv/stat.c")],
               fields=[("uart_send", "Uart", "errors", "write", "added"), ("uart_errors", "Uart", "errors", "read", "unchanged")])
    c.impact.sinks = {"N3": SinkInfo(field="N3", label="Uart::errors", users=312, why="threshold")}
    f = _finding("field_mutation", "uart_send now writes Uart::errors", ["N1", "N3"], side_effect=True)
    assert prepare_facts(_Ctx(c), [f], {})[finding_key(f)] == \
        "Uart::errors (N3) is a shared sink (312 functions); its users are not listed"
```

Append to `backend/tests/test_tier1_stories.py`:

```python
def test_the_cache_key_changes_with_the_shared_sinks():
    ps = _change()[2]
    k = cache_key(ps, "big", STORY_RULES_VERSION, 1)
    assert cache_key(ps, "big", STORY_RULES_VERSION, 1, []) == k               # no sinks: the key as before
    assert cache_key(ps, "big", STORY_RULES_VERSION, 1, ["log_t::buf"]) != k
    assert cache_key(ps, "big", STORY_RULES_VERSION, 1, ["b", "a"]) == cache_key(ps, "big", STORY_RULES_VERSION, 1, ["a", "b"])
```

Append to `backend/tests/test_pipeline.py`:

```python
def test_shared_sinks_from_the_yaml_and_the_owners_marks_quiet_a_review(fx, tmp_path, monkeypatch):
    from helpers import make_config

    from codetortoise import pipeline
    from codetortoise.services import build_services

    seen = []
    real = pipeline.prepare_facts
    monkeypatch.setattr(pipeline, "prepare_facts", lambda x, fs, *a, **k: (seen.extend(fs), real(x, fs, *a, **k))[1])
    svc = build_services(make_config(fx, tmp_path, analysis={"module_min_files": 1, "workers": 1,
                                                             "sink_fields": ["Stats::*"]}))
    svc.store.kv_put("sink_marks", ["Uart::errors"])
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    sinks = {(s["label"], s["why"]) for s in svc.store.get_blob(rid, "impact")["sinks"].values()}
    assert {("Stats::tx", "listed"), ("Uart::errors", "marked")} <= sinks
    sunk = {f.title for f in svc.store.list_findings(rid) if f.sink}
    assert {"uart_send now writes Stats::tx through a local alias",
            "uart_send now writes Uart::errors through a local alias"} <= sunk
    assert seen and not any(f.sink for f in seen)             # the strong model's facts never cover a sink
    reading = svc.store.get_blob(rid, "reading")
    assert not [k for k in reading["checks"] if k["kind"] == "reader"]
    assert {"Stats::tx", "Uart::errors"} <= {h["label"] for h in reading["sinks"]}
    assert [f["tag"] for f in svc.store.get_blob(rid, "board")["flows"]] == ["contract", "contract"]   # no state flow
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTEST tests/test_facts_prep.py tests/test_tier1_stories.py tests/test_pipeline.py -q -k "sink"`
Expected: FAIL — facts still list readers; `cache_key` takes no fifth argument; `seen` holds sink findings.

- [ ] **Step 3: Implement**

`backend/codetortoise/facts_prep.py`, top of `field_facts` (import `from codetortoise.sinks import why_text`):

```python
    n = x.im.nodes[field_id]
    sink = x.im.sinks.get(field_id)
    if sink is not None:          # a shared sink (spec 2026-10-09 §4): its users would swamp the facts
        return [f"{n.label} ({field_id}) is a shared sink ({why_text(sink)}); its users are not listed"]
```

`backend/codetortoise/brief.py`:

```python
def cache_key(ps: PieceSet, model: str, rules_version: int, agree: int, sinks: Collection[str] = ()) -> str:
    """Hash of what tier 1 is shown (cards, links, overview), the rules' version, the model and the shared sinks (their
    links are left out of the pieces, so marking one regroups the stories)."""
    data = {"cards": [p.card for p in ps.pieces], "links": [lk.model_dump() for lk in ps.links],
            "overview": ps.overview, "rules": rules_version, "model": model, "agree": agree}
    if sinks:
        data["sinks"] = sorted(sinks)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
```

(`from collections.abc import Collection`.)

`backend/codetortoise/pipeline.py`:

- stage `stories()`: `key = cache_key(ps, strong.model, STORY_RULES_VERSION, strong.agree, [s.label for s in ctx["impact"].sinks.values()])`
  and `form_stories(..., [f for f in ctx["findings"] if not f.sink], weak=svc.llm)`.
- stage `review()`: after `brief, findings, ps, strong = ...` add
  `quiet = [f for f in findings if not f.sink]   # shared sinks are never judged (spec 2026-10-09 §4)`;
  pass `quiet` to `prepare_facts(x, quiet, ...)` and to `review_stories(..., strong, quiet, brief.facts, ...)`;
  keep `apply_verdicts(findings, ...)`, `store.put_findings(rid, findings)` and the messages on `findings`.

- [ ] **Step 4: Run them to see them pass**

Run: `PYTEST tests/test_facts_prep.py tests/test_tier1_stories.py tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Whole suite, lint, commit**

Run: `PYTEST -q -x` and `RUFF`. Expected: pass, clean.

```bash
git add backend/codetortoise/facts_prep.py backend/codetortoise/brief.py backend/codetortoise/pipeline.py \
        backend/tests/test_facts_prep.py backend/tests/test_tier1_stories.py backend/tests/test_pipeline.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(sinks): the strong model is never shown a shared sink's finding, its facts say one line, and the sinks key the stories cache

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `/api/sinks` — anyone reads the rules, the owner marks

**Files:**
- Modify: `backend/codetortoise/web/app.py` (new section after `# ---- layers`)
- Test: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: `marks`, `set_mark` (Task 1).
- Produces: `GET /api/sinks` → `{"threshold": int, "patterns": [str], "marked": [str]}`;
  `PUT|DELETE /api/sinks/{label:path}` (owner) → the same body; 422 for an empty label or one over 300 characters.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_web.py`:

```python
def test_the_owner_marks_and_unmarks_shared_sinks_for_every_review(env):
    svc, app, _ = env
    owner, bob = login(app, "owner"), login(app, "bob")
    assert TestClient(app).get("/api/sinks").status_code == 401
    assert bob.get("/api/sinks").json() == {"threshold": 20, "patterns": [], "marked": []}
    assert bob.put("/api/sinks/Uart%3A%3Aerrors").status_code == 403
    assert owner.put("/api/sinks/Uart%3A%3Aerrors").json()["marked"] == ["Uart::errors"]
    assert owner.put("/api/sinks/log_t%3A%3Abuf").json()["marked"] == ["Uart::errors", "log_t::buf"]
    assert bob.delete("/api/sinks/log_t%3A%3Abuf").status_code == 403
    assert owner.delete("/api/sinks/log_t%3A%3Abuf").json()["marked"] == ["Uart::errors"]
    assert svc.store.kv_get("sink_marks") == ["Uart::errors"]
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    sinks = owner.get(f"/api/reviews/{rid}/reading").json()["sinks"]
    assert [(h["label"], h["why"]) for h in sinks] == [("Uart::errors", "marked")]
    assert any(f["sink"] for f in owner.get(f"/api/reviews/{rid}/findings").json())


def test_a_label_with_a_slash_or_percent_is_stored_as_given(env):
    _, app, _ = env
    owner = login(app, "owner")
    assert owner.put("/api/sinks/a%2Fb%3A%3Ac%25d").json()["marked"] == ["a/b::c%d"]
    assert owner.put("/api/sinks/" + "x" * 301).status_code == 422
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTEST tests/test_web.py -q -k "sink or slash"`
Expected: FAIL — 404 for `/api/sinks`.

- [ ] **Step 3: Implement**

`backend/codetortoise/web/app.py` (import `from codetortoise.sinks import marks, set_mark`), after the layers section:

```python
    # ---- shared sinks (spec 2026-10-09-shared-sinks §6) -----------------------
    def sinks_view() -> dict:
        return {"threshold": cfg.analysis.sink_threshold, "patterns": cfg.analysis.sink_fields, "marked": marks(store)}

    def sink_label(label: str) -> str:
        if not label.strip() or len(label) > 300:
            raise HTTPException(422, "a field's label, as record::field")
        return label

    @app.get("/api/sinks")
    def sinks(_: str = Depends(user_of)):
        return sinks_view()

    @app.put("/api/sinks/{label:path}")
    def mark_sink(label: str, _: str = Depends(owner_of)):
        set_mark(store, sink_label(label), True)
        return sinks_view()

    @app.delete("/api/sinks/{label:path}")
    def unmark_sink(label: str, _: str = Depends(owner_of)):
        set_mark(store, sink_label(label), False)
        return sinks_view()
```

If the `%2F` case arrives split or decoded differently by the test client, read the raw path from
`request.scope["raw_path"]` instead and `urllib.parse.unquote` the part after `/api/sinks/`; the test is the authority.

- [ ] **Step 4: Run them to see them pass**

Run: `PYTEST tests/test_web.py -q`
Expected: PASS.

- [ ] **Step 5: Whole suite, lint, commit**

Run: `PYTEST -q -x` and `RUFF`. Expected: pass, clean.

```bash
git add backend/codetortoise/web/app.py backend/tests/test_web.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(sinks): /api/sinks shows the sink rules to anyone and lets the owner mark and unmark a field

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The browser hides sinks unless the viewer shows them

**Files:**
- Create: `frontend/src/lib/sinks.ts`, `frontend/src/lib/sinks.test.ts`
- Modify: `frontend/src/api.ts` (`Finding.sink`, `SinkRules`, `board`/`story`/`findings` filtered, `sinks`/`markSink`/`unmarkSink`)
- Modify: `frontend/src/board/types.ts` (`Annotation.sink`, `Annotation.field`)
- Modify: `frontend/src/reading/types.ts` (`Check.field`, `SinkHit`, `Reading.sinks`)

**Interfaces:**
- Consumes: the backend fields above.
- Produces (TypeScript):
  - `export interface SinkHit { field: string; label: string; users: number; why: "marked" | "listed" | "threshold"; writers: string[] }`
  - `export interface SinkRules { threshold: number; patterns: string[]; marked: string[] }` (in `api.ts`)
  - `lib/sinks.ts`: `SHOW_KEY`, `showSinks(): boolean`, `setShowSinks(on: boolean): void`,
    `whyText(s: { why: SinkHit["why"]; users: number }): string`, `sinkLine(hits: SinkHit[], shown: boolean): string`,
    `quietBoard<B extends Board | null>(b: B, show: boolean): B`, `quietStory(d: StoryDetail, show: boolean): StoryDetail`,
    `quietFindings(fs: Finding[], show: boolean): Finding[]`
  - `api.sinks()`, `api.markSink(label)`, `api.unmarkSink(label)` → `Promise<SinkRules>`.

- [ ] **Step 1: Link node_modules (once per worktree)**

Run: `ln -s /media/anoop/ssd_1/Work/CodeTortoise/frontend/node_modules frontend/node_modules` (skip if present).

- [ ] **Step 2: Write the failing test**

`frontend/src/lib/sinks.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Finding } from "../api";
import type { Annotation, Board, StoryDetail } from "../board/types";
import type { SinkHit } from "../reading/types";
import { quietBoard, quietFindings, quietStory, setShowSinks, showSinks, SHOW_KEY, sinkLine, whyText } from "./sinks";

afterEach(() => vi.unstubAllGlobals());

const hit = (label: string, why: SinkHit["why"], users = 0): SinkHit => ({ field: "N1", label, users, why, writers: [] });
const ann = (text: string, sink?: boolean) => ({ node: "N1", text, sink } as unknown as Annotation);
const board = (impacts: Annotation[]) => ({ impacts, nodes: [] } as unknown as Board);

describe("shared sinks", () => {
  it("says why each field is a sink", () => {
    expect([whyText(hit("a", "threshold", 312)), whyText(hit("a", "listed")), whyText(hit("a", "marked"))])
      .toEqual(["312 functions", "in tortoise.yaml", "marked"]);
  });

  it("writes the overview's line, one or many, hidden or shown", () => {
    expect(sinkLine([hit("log_t::buf", "threshold", 312), hit("stats_t::tx", "listed")], false))
      .toBe("2 shared sinks hidden: `log_t::buf` (312 functions), `stats_t::tx` (in tortoise.yaml)");
    expect(sinkLine([hit("Uart::errors", "marked")], true)).toBe("1 shared sink shown: `Uart::errors` (marked)");
  });

  it("leaves sink annotations and findings out unless shown", () => {
    const b = board([ann("writes x"), ann("writes buf", true)]);
    expect(quietBoard(b, false).impacts.map((a) => a.text)).toEqual(["writes x"]);
    expect(quietBoard(b, true)).toBe(b);
    expect(quietBoard(null, false)).toBe(null);
    const d = { board: b, graph: null } as unknown as StoryDetail;
    expect(quietStory(d, false).board.impacts).toHaveLength(1);
    expect(quietStory(d, false).graph).toBe(null);
    const fs = [{ id: "F1" }, { id: "F2", sink: true }] as Finding[];
    expect(quietFindings(fs, false).map((f) => f.id)).toEqual(["F1"]);
    expect(quietFindings(fs, true)).toBe(fs);
  });

  it("keeps the viewer's choice in the browser; hidden when storage is missing or throws", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
    expect(showSinks()).toBe(false);
    setShowSinks(true);
    expect(store.get(SHOW_KEY)).toBe("true");
    expect(showSinks()).toBe(true);
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("quota"); } } });
    expect(showSinks()).toBe(false);
    expect(() => setShowSinks(true)).not.toThrow();
    vi.unstubAllGlobals();
    expect(showSinks()).toBe(false);                 // no window at all (node)
  });
});
```

- [ ] **Step 3: Run it to see it fail**

Run (from `frontend/`): `npx vitest run src/lib/sinks.test.ts`
Expected: FAIL — cannot resolve `./sinks`.

- [ ] **Step 4: Implement**

`frontend/src/lib/sinks.ts`:

```ts
/** Shared sinks (spec 2026-10-09-shared-sinks §5): fields so many functions touch that the review hides writes to them.
 * Whether to show them is each viewer's own, kept in the browser; hidden is the default. */
import type { Finding } from "../api";
import { load, save } from "../board/prefs";
import type { Board, StoryDetail } from "../board/types";
import type { SinkHit } from "../reading/types";

export const SHOW_KEY = "ct.sinks.show";
export const showSinks = (): boolean => load<unknown>(SHOW_KEY, false) === true;
export const setShowSinks = (on: boolean): void => save(SHOW_KEY, on);

export function whyText(s: { why: SinkHit["why"]; users: number }): string {
  return s.why === "threshold" ? `${s.users} functions` : s.why === "listed" ? "in tortoise.yaml" : "marked";
}

/** "2 shared sinks hidden: `log_t::buf` (312 functions), `stats_t::tx` (in tortoise.yaml)" */
export function sinkLine(hits: SinkHit[], shown: boolean): string {
  const n = hits.length;
  return `${n} shared sink${n === 1 ? "" : "s"} ${shown ? "shown" : "hidden"}: `
    + hits.map((h) => `\`${h.label}\` (${whyText(h)})`).join(", ");
}

export function quietBoard<B extends Board | null>(b: B, show: boolean): B {
  return !b || show ? b : { ...b, impacts: b.impacts.filter((a) => !a.sink) };
}

export function quietStory(d: StoryDetail, show: boolean): StoryDetail {
  return show ? d : { ...d, board: quietBoard(d.board, false), graph: quietBoard(d.graph, false) };
}

export const quietFindings = (fs: Finding[], show: boolean): Finding[] => (show ? fs : fs.filter((f) => !f.sink));
```

`frontend/src/board/types.ts`, `Annotation` gains:

```ts
  /** A write to a shared sink: drawn only when the viewer shows them (spec 2026-10-09). */
  sink?: boolean;
  /** A field declaration's note: the field's label, which the owner may mark a shared sink. */
  field?: string | null;
```

`frontend/src/reading/types.ts`: `Check` gains `/** A reader row's field (the owner may mark it a shared sink). */ field?: string | null;`;
add

```ts
/** A shared sink the change writes (spec 2026-10-09 §5.1): hidden unless the viewer shows them. */
export interface SinkHit { field: string; label: string; users: number; why: "marked" | "listed" | "threshold"; writers: string[] }
```

and `Reading` gains `/** Absent on a reading stored before shared sinks. */ sinks?: SinkHit[];`.

`frontend/src/api.ts`:

- `Finding` gains `/** A write to a shared sink: hidden unless the viewer shows them. */ sink?: boolean;`
- `export interface SinkRules { threshold: number; patterns: string[]; marked: string[] }`
- `import { quietBoard, quietFindings, quietStory, showSinks } from "./lib/sinks";`
- in `api`:

```ts
  board: (id: number, cluster?: string | null) =>
    call<Board>("GET", `/api/reviews/${id}/board${cluster ? `?${new URLSearchParams({ cluster })}` : ""}`)
      .then((b) => quietBoard(b, showSinks())),
  story: (id: number, sid: string) => call<StoryDetail>("GET", `/api/reviews/${id}/stories/${sid}`)
    .then((d) => quietStory(d, showSinks())),
  findings: (id: number) => call<Finding[]>("GET", `/api/reviews/${id}/findings`).then((fs) => quietFindings(fs, showSinks())),
  /** Shared sinks (spec 2026-10-09 §6): the rules, and the owner's marks for every review from the next run. */
  sinks: () => call<SinkRules>("GET", "/api/sinks"),
  markSink: (label: string) => call<SinkRules>("PUT", `/api/sinks/${encodeURIComponent(label)}`),
  unmarkSink: (label: string) => call<SinkRules>("DELETE", `/api/sinks/${encodeURIComponent(label)}`),
```

- [ ] **Step 5: Run it to see it pass, then everything**

Run: `npx vitest run src/lib/sinks.test.ts` then `npx vitest run` then `npm run build`
Expected: PASS; all vitest pass (188+); build clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/sinks.ts frontend/src/lib/sinks.test.ts frontend/src/api.ts frontend/src/board/types.ts \
        frontend/src/reading/types.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(sinks): the browser leaves shared sinks' notes and findings out unless the viewer shows them

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Show/Hide, the owner's mark, and the Health page

**Files:**
- Create: `frontend/src/components/SinkMark.tsx`
- Modify: `frontend/src/workspace/Overview.tsx` (Coverage tile)
- Modify: `frontend/src/workspace/FindingPage.tsx`, `frontend/src/workspace/CheckList.tsx`, `frontend/src/board/CodeView.tsx`
- Modify: `frontend/src/pages/Health.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 7's `api.*Sink`, `showSinks`, `setShowSinks`, `sinkLine`, `SinkHit`, `Check.field`, `Annotation.field`.
- Produces: `SinkMark({ label, on }: { label: string; on?: boolean })` — renders nothing for anyone but the owner;
  button `Treat <code>label</code> as a sink` (accessible name `Treat {label} as a sink`), or with `on`
  `unmark {label}` (accessible name `Unmark {label}`); after a click `Marked — re-run to apply` / `Unmarked — re-run
  to apply` and, inside a review, a **Re-run** button.

- [ ] **Step 1: The mark control**

`frontend/src/components/SinkMark.tsx`:

```tsx
import { useContext, useState } from "react";
import { api } from "../api";
import { useMe } from "../App";
import { WsContext } from "../workspace/context";

/** The owner's mark (spec 2026-10-09-shared-sinks §6.2): treat a field as a shared sink in every review from the next
 * run, or stop. Inside a review it offers the re-run that applies it. */
export default function SinkMark({ label, on = false }: { label: string; on?: boolean }) {
  const me = useMe(), ws = useContext(WsContext);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!me?.is_owner) return null;
  const act = () => (on ? api.unmarkSink(label) : api.markSink(label))
    .then(() => setDone(true), (e) => setError(String(e.message ?? e)));
  if (done)
    return (
      <span className="sink-mark">{on ? "Unmarked" : "Marked"} — re-run to apply
        {ws && <> <button className="link" onClick={() => api.rerun(ws.data.id).then(ws.data.loadDetail)}>Re-run</button></>}
      </span>
    );
  return (
    <span className="sink-mark">
      {on ? <button className="link" onClick={act} aria-label={`Unmark ${label}`}>unmark {label}</button>
        : <button className="link" onClick={act} aria-label={`Treat ${label} as a sink`}
                  title="Hide this field's readers and writers in every review from the next run">Treat <code>{label}</code> as a sink</button>}
      {error && <span className="banner warn">{error}</span>}
    </span>
  );
}
```

- [ ] **Step 2: The overview's line**

`frontend/src/workspace/Overview.tsx`: import `SinkMark`, `setShowSinks`, `showSinks`, `sinkLine` and `type SinkHit`.
Add above the default export:

```tsx
/** The shared sinks the review hid (spec 2026-10-09 §5.2), with the viewer's Show/Hide and the owner's unmark. Show is
 * kept in the browser; the page reloads so every board, story and finding list follows it. */
function SinksLine({ hits }: { hits: SinkHit[] }) {
  const shown = showSinks();
  const flip = () => { setShowSinks(!shown); window.location.reload(); };
  return (
    <li className="ov-sinks">
      <Ticks text={sinkLine(hits, shown)} /> · <button className="link" onClick={flip} aria-pressed={shown}>{shown ? "Hide" : "Show"}</button>
      {hits.filter((h) => h.why === "marked").map((h) => <span key={h.label}> · <SinkMark label={h.label} on /></span>)}
    </li>
  );
}
```

and the Coverage tile becomes:

```tsx
        {(r.coverage.length > 0 || (r.sinks?.length ?? 0) > 0) && (
          <section className="ws-tile" aria-label="Coverage">
            <h3>Coverage</h3>
            <ul className="ov-lines">
              {r.coverage.map((c) => <li key={c}><Ticks text={c} /></li>)}
              {(r.sinks?.length ?? 0) > 0 && <SinksLine hits={r.sinks!} />}
            </ul>
          </section>
        )}
```

- [ ] **Step 3: The three places to mark from**

- `FindingPage.tsx`: after `const first = ...` add
  `const field = f.kind === "field_mutation" && !f.sink ? f.nodes.map((x) => d.names[x]).find((x) => x?.kind === "field")?.label ?? null : null;`
  and inside `<p className="ws-story-meta">`, after the state buttons: `{field && <SinkMark label={field} />}`.
- `CheckList.tsx` (`CheckRow`, inside `ck-acts`, last): `{k.kind === "reader" && k.field && <SinkMark label={k.field} />}`.
- `CodeView.tsx` (the `it.kind === "ann"` branch):
  `<span className="k">{ICON[it.ann.severity]}{it.ann.title}</span>{it.ann.text}{it.ann.field && <> <SinkMark label={it.ann.field} /></>}`.

- [ ] **Step 4: The Health page**

`frontend/src/pages/Health.tsx`: import `SinkMark` and `type SinkRules`; load the rules beside the health report
(`const [sinks, setSinks] = useState<SinkRules | null>(null);` and in `load`, also
`api.sinks().then(setSinks).catch(() => setSinks(null))`), and add a card in `hc-cards`:

```tsx
        {sinks && (
          <section className="card">
            <h2>Shared sinks</h2>
            <p>{sinks.threshold > 0 ? `A field more than ${sinks.threshold} unchanged functions touch` : "No threshold (sink_threshold: 0)"}</p>
            <p className="mono small">In tortoise.yaml: {sinks.patterns.length ? sinks.patterns.join(" ") : "none"}</p>
            <p>Marked: {sinks.marked.length ? sinks.marked.map((m) => <span key={m}><code>{m}</code> <SinkMark label={m} on /> </span>) : "none"}</p>
          </section>
        )}
```

- [ ] **Step 5: Style**

`frontend/src/styles.css`, at the end:

```css
/* Shared sinks (spec 2026-10-09): the owner's mark sits after the text it marks */
.sink-mark { margin-left: 0.4em; white-space: nowrap; }
.sink-mark code { font-size: 0.95em; }
```

- [ ] **Step 6: Check and build**

Run (from `frontend/`): `npx vitest run` and `npm run build`
Expected: all pass; build clean (no type errors).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/SinkMark.tsx frontend/src/workspace/Overview.tsx frontend/src/workspace/FindingPage.tsx \
        frontend/src/workspace/CheckList.tsx frontend/src/board/CodeView.tsx frontend/src/pages/Health.tsx frontend/src/styles.css
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(sinks): the overview says which shared sinks it hid with Show/Hide; the owner marks a field from a finding, a reader row or its declaration, and on the Health page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: End to end on a server of its own

**Files:**
- Create: `frontend/e2e/serve-sinks.sh`, `frontend/e2e/workspace-sinks.spec.ts`
- Modify: `frontend/playwright.config.ts`

**Interfaces:**
- Consumes: everything above.
- Produces: a CodeTortoise on port 8794 whose `tortoise.yaml` lists `Stats::*` (its own data dir, so its marks never
  reach the other servers' reviews).

Ruling carried from planning: spec §7 asks for a fixture field written by more than 20 functions. Changing the
bundled fixture would shift every other e2e expectation, so the e2e uses a listed sink (`Stats::*`) and a marked one
(`Uart::errors`); the threshold is covered by Task 1's tests.

- [ ] **Step 1: The server**

`frontend/e2e/serve-sinks.sh`:

```bash
#!/usr/bin/env bash
# Starts a CodeTortoise on the bundled fixture whose tortoise.yaml lists Stats::* as shared sinks (spec 2026-10-09 §7).
# Its own data dir: the owner's marks made here never reach the other servers' reviews.
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8794 >/dev/null
sed -i 's/^  workers: 1$/  workers: 1\n  sink_fields:\n  - "Stats::*"/' "$DIR/tortoise.yaml"
grep -q 'Stats::\*' "$DIR/tortoise.yaml"
exec $CMD serve --config "$DIR/tortoise.yaml"
```

`chmod +x frontend/e2e/serve-sinks.sh`. Check with `cat` of a generated `tortoise.yaml` (run `fixture-demo` once into
`$CLAUDE_JOB_DIR/tmp/sinks-yaml` with the venv python) that the `analysis:` block ends with `  workers: 1`; if not,
adjust the `sed` anchor to the block's last line.

`frontend/playwright.config.ts`, add to `webServer` after the large server:

```ts
    // shared sinks (e2e/workspace-sinks.spec.ts): the fixture with Stats::* listed as sinks, marks of its own
    { command: "bash e2e/serve-sinks.sh", url: "http://127.0.0.1:8794/api/me", timeout: 120_000, reuseExistingServer: false },
```

- [ ] **Step 2: The tests**

`frontend/e2e/workspace-sinks.spec.ts`:

```ts
import { expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

const SINKS = "http://127.0.0.1:8794";
const READER = "uart_errors reads Uart::errors";

async function findingCount(page: Page): Promise<number> {
  const t = await page.locator(".ws-rail").getByRole("button", { name: /^Findings \(\d+\)$/ }).innerText();
  return Number(t.match(/\((\d+)\)/)![1]);
}

/** Shared sinks (spec 2026-10-09-shared-sinks): this server's tortoise.yaml lists Stats::*. */
test.describe("shared sinks", () => {
  test.use({ baseURL: SINKS });

  test("a write to a listed sink is hidden until the viewer shows it", async ({ page }) => {
    await startReview(page);
    const cov = page.getByRole("region", { name: "Coverage" });
    await expect(cov).toContainText(/shared sinks? hidden: .*Stats::tx \(in tortoise\.yaml\)/);
    const hidden = await findingCount(page);
    await cov.getByRole("button", { name: "Show" }).click();
    await expect(cov).toContainText(/shared sinks? shown: .*Stats::tx/);
    await expect.poll(() => findingCount(page)).toBeGreaterThan(hidden);
    await cov.getByRole("button", { name: "Hide" }).click();
    await expect(cov).toContainText(/hidden/);
    await expect.poll(() => findingCount(page)).toBe(hidden);
  });

  test("the owner marks a field from To check; a re-run hides its rows and unmarking brings them back", async ({ page }) => {
    await startReview(page);
    const row = page.locator(".ck-row", { hasText: READER });
    await row.getByRole("button", { name: "Treat Uart::errors as a sink" }).click();
    await expect(row).toContainText("Marked — re-run to apply");
    await row.getByRole("button", { name: "Re-run" }).click();
    const cov = page.getByRole("region", { name: "Coverage" });
    await expect(cov).toContainText("Uart::errors (marked)", { timeout: 60_000 });
    await expect(page.locator(".ck-row", { hasText: READER })).toHaveCount(0);
    await cov.getByRole("button", { name: "Unmark Uart::errors" }).click();
    await expect(cov).toContainText("Unmarked — re-run to apply");
    await cov.getByRole("button", { name: "Re-run" }).click();
    await expect(page.locator(".ck-row", { hasText: READER })).toHaveCount(1, { timeout: 60_000 });
    await expect(cov).not.toContainText("Uart::errors");
  });
});
```

If the reader row's visible text differs (it comes from `Ticks`, which drops the backticks), read it from the
review-reading e2e spec or the page and fix `READER` — not the production text.

- [ ] **Step 3: Run the new spec**

Run (from `frontend/`): `npm run build`, then
`TMPDIR=$CLAUDE_JOB_DIR/tmp/pw TORTOISE_CMD="env PYTHONPATH=/media/anoop/ssd_1/Work/CodeTortoise/.worktrees/sinks/backend /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test e2e/workspace-sinks.spec.ts`
Expected: 2 passed.

- [ ] **Step 4: Full suites**

Run: `PYTEST -q` (backend), `RUFF`, `npx vitest run`, then the full Playwright run (same command without a file), and
`--last-failed` once if only `startReview` timeouts failed.
Expected: pytest all pass (1 skipped); ruff clean; vitest all pass; e2e all pass (118 tests) after at most one
`--last-failed` rerun of startReview timeouts.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/serve-sinks.sh frontend/e2e/workspace-sinks.spec.ts frontend/playwright.config.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "test(sinks): end to end, a listed sink hides until shown and the owner's mark hides a field's readers after a re-run

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
