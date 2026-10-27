# Stable Field Ids and Name-Only Matches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop untouched union/anonymous-record fields from flooding a review with checks when their header shifts, and stop name-only field matches from creating checks or shared sinks.

**Architecture:** The facts stage (`facts/aliasflow.py`) gives every field a stable id (`field_id`) and a line-free label (`record_name`) instead of libclang's offset-bearing USR; everything downstream keys on `field:<id>` and needs no change. The shared-sink count (`sinks.py`) and the "Unchanged reader" checks (`reading.py`) ignore edges whose confidence is `heuristic`; the reading's Coverage gains one line per written field naming how many functions use its name only.

**Tech Stack:** Python 3, libclang (clang.cindex), pydantic v2, pytest. Run Python as `../../../backend/.venv/bin/python` with `PYTHONPATH=$PWD` from `.worktrees/union-fields/backend` (never `uv`).

**Spec:** `docs/superpowers/specs/2026-10-10-union-fields-design.md`

## Global Constraints

- Offset segment: `@<digits>` followed by `@` or the end of the USR.
- Named-member record id: `record_id(outer) + "@" + kind + ">" + member` (kind `U` for a union, `S` otherwise).
- Anonymous-member record id: `record_id(outer) + "@" + kind + "a"`.
- No enclosing record: `c:` + base name of the record's file + `@` + kind + `~` + first variable of that type among the record's semantic parent's children, else the record's field names joined with `,`.
- Field id: `record_id(parent) + "@FI@" + field`, used only when `f.get_usr()` has an offset segment; otherwise the USR itself.
- Labels: held by a named member (arrays and pointers stripped) → `record_name(outer) + "." + member`; anonymous member → `record_name(outer)`; otherwise unchanged `anonymous struct|union (<file>:<line>)`.
- Coverage line: `N functions use a field named `x`, matched by name only — not checked` (`1 function uses …` for one); `x` is the part of the field label after `::`; lines sorted by label; placed after the existing over-the-cap `capped_fields` lines.
- Shared sinks count only `precise` and `may` edges from unchanged functions; heuristic edges and `capped_fields` never count.
- Commits: `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`, message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH`.

## Review Focus

1. A union/struct reached through a pointer member (`struct { int q; } *p;`) must get `dev.p` and `c:@S@dev@S>p@FI@q`, not the line-based fallback — pinned in Task 1's id test.
2. A file-scope anonymous record with no enclosing record keeps one id across a shift (`c:reg.h@S~g_anon@FI@a`) even though its label still moves — pinned in Task 1's id test.
3. A header shift plus a body edit of a writer must produce no added/removed field edge at all (the whole flood) — pinned in Task 1's integration test.
4. A function with both a precise and a heuristic edge into the written field is a reader check, not a name-only count — pinned in Task 3's test.
5. A shared sink's heuristic-only users must not produce a Coverage line (sinks already say their users are not checked) — pinned in Task 3's test.

---

### Task 1: Stable field ids and line-free labels

**Files:**
- Modify: `backend/codetortoise/facts/aliasflow.py` (imports; `record_name` at ~76; `FunctionAnalyzer.__init__` ~250; `_field_file` ~261; `lval` step ~297; the two `FieldAccess(field=f.get_usr(), …)` constructions ~438 and ~480)
- Modify: `backend/codetortoise/facts/model.py:51` (comment only)
- Test: `backend/tests/test_aliasflow.py`, `backend/tests/test_detectors.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `field_id(f: ci.Cursor, cache: dict[int, str] | None = None) -> str`, `record_id(rec: ci.Cursor, cache: dict[int, str] | None = None) -> str`, `_holder(outer: ci.Cursor, rec: ci.Cursor) -> ci.Cursor | None` in `codetortoise.facts.aliasflow`. `FieldAccess.field` values change as described; nothing downstream changes.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_aliasflow.py`:

```python
REG_H = """typedef union { unsigned word; struct { unsigned lo:16, hi:16; } bits; } reg_t;
struct dev {
  int id;
  union { unsigned raw; struct { unsigned en:1, mode:3; }; } ctl;
  union { int i; float f; };
  struct { int x, y; } pos[2];
  struct { int q; } *p;
};
static struct { int a; } g_anon;
"""
REG_C = """#include "reg.h"
void f(struct dev *d, reg_t *r) { r->bits.lo = 1; r->word = 2; d->ctl.en = 1; d->ctl.raw = 0; d->i = 3; d->pos[0].x = 1;
  d->p->q = 1; g_anon.a = 1; d->id = 0; }
"""


def _accesses(tmp_path, sub, header):
    load_libclang(None)
    d = tmp_path / sub
    d.mkdir()
    (d / "reg.h").write_text(header)
    (d / "main.c").write_text(REG_C)
    tu = ci.Index.create().parse(str(d / "main.c"), args=["-xc"])
    assert not [x for x in tu.diagnostics if x.severity >= ci.Diagnostic.Error]
    fn = next(c for c in tu.cursor.walk_preorder() if c.spelling == "f" and c.is_definition())
    return FunctionAnalyzer(fn, fn.get_usr()).analyze()[0]


def test_a_fields_id_does_not_move_with_its_header_and_names_where_it_lives(tmp_path):
    """Owner, 2026-10-09: untouched union fields flooded the review whenever their header shifted."""
    before = _accesses(tmp_path, "a", REG_H)
    after = _accesses(tmp_path, "b", "/* one more line */\n" + REG_H)
    assert {(a.field_name, a.mode, a.field) for a in before} == {(a.field_name, a.mode, a.field) for a in after}
    got = {a.field_name: (a.field, a.record) for a in before if a.mode == "write"}
    assert got["raw"] == ("c:@S@dev@U>ctl@FI@raw", "dev.ctl")
    assert got["en"] == ("c:@S@dev@U>ctl@Sa@FI@en", "dev.ctl")
    assert got["lo"] == ("c:@UA@reg_t@S>bits@FI@lo", "reg_t.bits")
    assert got["x"] == ("c:@S@dev@S>pos@FI@x", "dev.pos")
    assert got["q"] == ("c:@S@dev@S>p@FI@q", "dev.p")
    assert got["a"][0] == "c:reg.h@S~g_anon@FI@a" and got["a"][1].startswith("anonymous struct (")
    assert (got["word"][0], got["i"][0], got["id"][0]) == ("c:@UA@reg_t@FI@word", "c:@S@dev@Ua@FI@i", "c:@S@dev@FI@id")
    assert (got["word"][1], got["i"][1], got["id"][1]) == ("reg_t", "dev", "dev")


def test_a_nameless_record_with_no_variable_of_its_own_is_named_by_its_fields(tmp_path):
    fields, _, _ = writes(tmp_path, "local.c", "void h(void) { struct { int s, t; } v; v.s = 1; }\n", ["-xc"], "h")
    (s,) = [a for a in fields if a.field_name == "s" and a.mode == "write"]
    assert s.field == "c:local.c@S~s,t@FI@s"
```

Append to `backend/tests/test_detectors.py`:

```python
SHIFT_H = "struct dev { int id; union { unsigned raw; struct { unsigned en:1; }; } ctl; };\n"
SHIFT_C_BEFORE = """#include "reg.h"
int get(struct dev *d) { return d->ctl.raw + d->ctl.en; }
void set(struct dev *d, unsigned v) { d->ctl.raw = v; }
"""
SHIFT_C_AFTER = SHIFT_C_BEFORE.replace("{ d->ctl.raw = v; }", "{ v = v + 1; d->ctl.raw = v; }")


def test_a_header_shift_above_a_union_leaves_its_untouched_fields_alone(tmp_path):
    """Spec 2026-10-10-union-fields §1.1: a line inserted above the union plus a body edit of its writer."""
    from codetortoise.config import AnalysisConfig
    from codetortoise.diffmap import map_changes
    from codetortoise.facts.clang_extractor import TuRequest, extract_tu
    from codetortoise.impact import build_impact
    from codetortoise.tu_select import TuSelection
    from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange

    h, c = tmp_path / "reg.h", tmp_path / "a.c"
    h_after = "/* one more line */\n" + SHIFT_H
    h.write_text(h_after)
    c.write_text(SHIFT_C_AFTER)
    hp, cp = str(h.resolve()), str(c.resolve())
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                   files=[FileChange(depot="//d/reg.h", local=hp, action="edit", before=SHIFT_H, after=h_after),
                          FileChange(depot="//d/a.c", local=cp, action="edit", before=SHIFT_C_BEFORE, after=SHIFT_C_AFTER)])
    dm = map_changes(cs)
    args = ["-xc", f"-I{tmp_path}"]
    before = [extract_tu(TuRequest(file=cp, args=args, variant="before", unsaved={hp: SHIFT_H, cp: SHIFT_C_BEFORE}))]
    after = [extract_tu(TuRequest(file=cp, args=args, variant="after", unsaved={hp: h_after, cp: SHIFT_C_AFTER}))]
    cfg = AnalysisConfig(module_min_files=1)
    im = build_impact(before, after, dm, TuSelection(selected=[cp]), None, None, cfg)
    assert [im.nodes[n].label for n in im.changed] == ["set"]
    moved = [(im.nodes[e.src].label, im.nodes[e.dst].label, e.status) for e in im.edges
             if e.kind in ("reads", "writes") and e.status != "unchanged"]
    assert moved == []
    assert [f.title for f in run_detectors(DetectorContext(before, after, dm, im, cfg)) if f.kind == "field_mutation"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd .worktrees/union-fields/backend && PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_aliasflow.py tests/test_detectors.py -k "header or nameless" 2>&1 | tail -15`
Expected: 3 failed — the id test on the first set comparison (ids carry `@a.h`-style offsets that differ), the nameless test on `c:local.c@<n>@F@h@S@local.c@<n>@FI@s != c:local.c@S~s,t@FI@s`, the detector test on `moved` listing `get`/`set` edges as added and removed.

- [ ] **Step 3: Implement `_holder`, `record_id`, `field_id` and the new `record_name`**

In `backend/codetortoise/facts/aliasflow.py`, add `import os` and `import re` to the imports (alphabetical, after `import fnmatch`). Replace `record_name` and add the helpers right after `_RECORDS`:

```python
_RECORDS = (K.STRUCT_DECL, K.UNION_DECL, K.CLASS_DECL)
_ARRAYS = (T.CONSTANTARRAY, T.INCOMPLETEARRAY, T.VARIABLEARRAY, T.DEPENDENTSIZEDARRAY)
_OFFSET = re.compile(r"@\d+(?=@|$)")      # libclang's file offset in an anonymous record's USR: it moves with the header


def _bare(t: ci.Type) -> ci.Type:
    """A type with its arrays and pointers stripped: `struct {…} pos[2]` and `struct {…} *p` hold that struct."""
    t = t.get_canonical()
    while True:
        if t.kind in _ARRAYS:
            t = t.element_type.get_canonical()
        elif t.kind == T.POINTER:
            t = t.get_pointee().get_canonical()
        else:
            return t


def _holder(outer: ci.Cursor, rec: ci.Cursor) -> ci.Cursor | None:
    """The member of `outer` whose type (arrays and pointers stripped) is the record `rec`."""
    return next((m for m in outer.get_children() if m.kind == K.FIELD_DECL and _bare(m.type).get_declaration() == rec),
                None)


def record_name(rec: ci.Cursor | None) -> str:
    """A field's record as people name it (spec 2026-10-04-change-stories §2.5, 2026-10-10-union-fields §3.3): its name;
    an anonymous record by the named record and member holding it ("filesystem_iterator_frame.entries", arrays and
    pointers too); an anonymous member by its enclosing record, whose fields its fields read as; else
    "anonymous struct (<file>:<line>)" (the facts stage makes the file workspace-relative). libclang names a typedef'd
    anonymous struct by its typedef."""
    if rec is None:
        return ""
    if not rec.is_anonymous():
        return rec.spelling
    outer = rec.semantic_parent
    if outer is not None and outer.kind in _RECORDS:
        member = _holder(outer, rec)
        return f"{record_name(outer)}.{member.spelling}" if member is not None else record_name(outer)
    what = "union" if rec.kind == K.UNION_DECL else "struct"
    loc = rec.location
    return f"anonymous {what} ({canon(loc.file.name) if loc.file else '?'}:{loc.line})"


def record_id(rec: ci.Cursor, cache: dict[int, str] | None = None) -> str:
    """A record's id that does not move with its header (spec 2026-10-10-union-fields §3.1): libclang's USR unless it
    holds a file offset; else the enclosing record's id and the member holding it (`c:@S@dev@U>ctl`), or `Ua`/`Sa` for
    an anonymous member; with no enclosing record, the file's base name and the first variable of the type
    (`c:reg.h@S~g_anon`), or its field names."""
    if cache is not None and rec.hash in cache:
        return cache[rec.hash]
    usr = rec.get_usr()
    if not _OFFSET.search(usr):
        out = usr
    else:
        kind = "U" if rec.kind == K.UNION_DECL else "S"
        outer = rec.semantic_parent
        if outer is not None and outer.kind in _RECORDS:
            member = _holder(outer, rec)
            out = f"{record_id(outer, cache)}@{kind}" + (f">{member.spelling}" if member is not None else "a")
        else:
            var = next((c.spelling for c in (outer.get_children() if outer is not None else ())
                        if c.kind == K.VAR_DECL and _bare(c.type).get_declaration() == rec), None)
            name = var or ",".join(f.spelling for f in rec.get_children() if f.kind == K.FIELD_DECL)
            base = os.path.basename(rec.location.file.name) if rec.location.file else "?"
            out = f"c:{base}@{kind}~{name}"
    if cache is not None:
        cache[rec.hash] = out
    return out


def field_id(f: ci.Cursor, cache: dict[int, str] | None = None) -> str:
    """A field's id (spec 2026-10-10-union-fields §3.1): its USR, unless that holds a file offset, then its record's
    stable id and its name."""
    usr = f.get_usr()
    return usr if not _OFFSET.search(usr) else f"{record_id(f.semantic_parent, cache)}@FI@{f.spelling}"
```

- [ ] **Step 4: Use `field_id` wherever the analyzer takes a field's USR**

In `FunctionAnalyzer.__init__`, after `self.fresh: set[str] = set()` add:

```python
        self.record_ids: dict[int, str] = {}  # record cursor hash -> stable record id (field_id's cache)
```

Change the comments on `field_files`/`field_lines` from `FieldDecl USR` to `field id`. Replace `_field_file`:

```python
    def _field_file(self, f: ci.Cursor) -> str:
        fid = field_id(f, self.record_ids)
        if fid not in self.field_files:
            self.field_files[fid] = canon(f.location.file.name) if f.location.file else ""
            self.field_lines[fid] = f.location.line
        return self.field_files[fid]
```

In `lval`, change the step to:

```python
            step = (field_id(f, self.record_ids), f.spelling, record_name(f.semantic_parent))
```

In both `fields.append(FieldAccess(fn=self.fn_usr, field=f.get_usr(), …` constructions, change `field=f.get_usr()` to `field=field_id(f, self.record_ids)`.

In `backend/codetortoise/facts/model.py:51` change the comment to `# stable field id (aliasflow.field_id), or "name:<field>" when heuristic`.

Run `grep -n "get_usr()" backend/codetortoise/facts/aliasflow.py` and confirm none left is called on a FIELD_DECL (the remaining ones are params, variables and references).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_aliasflow.py tests/test_detectors.py tests/test_clang_extractor.py 2>&1 | tail -3`
Expected: all pass (the existing `test_anonymous_records_are_named_by_typedef_member_or_place` still holds: `outer.frame`, `outer.frame.inner`, `u.half`, and `count` keeps its place label).

- [ ] **Step 6: Run the backend suite and ruff**

Run: `PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tail -2 && ../../../backend/.venv/bin/ruff check codetortoise tests`
Expected: all pass; `All checks passed!`. A fixture expectation that quotes an old offset-bearing USR or an `anonymous struct (…)` label for an array/pointer/anonymous-member field is updated to the new id/label and noted in the commit message.

- [ ] **Step 7: Commit**

```bash
git add backend/codetortoise/facts/aliasflow.py backend/codetortoise/facts/model.py backend/tests/test_aliasflow.py backend/tests/test_detectors.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "fix(facts): a field's id and label do not move with its header

libclang puts a file offset in the USR of a field of an anonymous record, so
any edit above a union in its header made its untouched fields look newly
written and every reader a check. field_id names such fields by the member
path holding them (c:@S@dev@U>ctl@FI@raw); record_name names anonymous members
and records held through arrays or pointers by where they live (dev.ctl, dev.pos).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 2: Name-only matches never make a shared sink

**Files:**
- Modify: `backend/codetortoise/sinks.py:15-38` (`find_sinks`)
- Modify: `docs/superpowers/specs/2026-10-09-shared-sinks-design.md` §3.1 (wording)
- Test: `backend/tests/test_sinks.py`

**Interfaces:**
- Consumes: `ImpactModel`, `Edge.confidence` (`"precise" | "may" | "heuristic"`).
- Produces: `find_sinks(im, threshold, patterns, marked) -> dict[str, SinkInfo]` with the same signature; `SinkInfo.users` now counts precise and may users only.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_sinks.py`, replace `test_name_matches_over_the_cap_count` with:

```python
def test_name_matches_never_count_toward_a_sink():
    """Spec 2026-10-10-union-fields §4.1: a member name shared by unrelated records says nothing about this field."""
    assert find_sinks(_im(1, capped=40), 20, [], ()) == {}                    # over the cap: not counted
    im = _im(0)
    for i in range(30):
        nid = f"N{10 + i}"
        im.nodes[nid] = Node(id=nid, key=f"ts:x.c#h{i}", label=f"h{i}", confidence="heuristic")
        im.edges.append(Edge(id=f"E{100 + i}", src=nid, dst="N2", kind="reads", confidence="heuristic"))
    assert find_sinks(im, 20, [], ()) == {}
    assert find_sinks(_im(3), 2, [], ())["N2"].users == 3                     # the precise readers still count
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_sinks.py 2>&1 | tail -5`
Expected: FAIL in `test_name_matches_never_count_toward_a_sink` — the first assert gets a threshold sink with `users=41`.

- [ ] **Step 3: Implement**

In `backend/codetortoise/sinks.py`, change `find_sinks`:

```python
def find_sinks(im: ImpactModel, threshold: int, patterns: list[str], marked: Collection[str]) -> dict[str, SinkInfo]:
    """Field node id -> why it is a sink: the owner marked its label, a pattern matches it, or more than `threshold`
    unchanged functions read or write it. Only clang's own accesses count; a match by member name alone never does
    (spec 2026-10-10-union-fields §4.1)."""
    changed = set(im.changed)
    who: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if e.kind in ("reads", "writes") and e.status != "removed" and e.src not in changed \
                and e.confidence != "heuristic":
            who[e.dst].add(e.src)
```

and in the loop replace `users = len(who.get(nid, ())) + im.capped_fields.get(n.label, 0)` with `users = len(who.get(nid, ()))`.

In `docs/superpowers/specs/2026-10-09-shared-sinks-design.md` §3.1, change the threshold rule's wording so it says unchanged functions with a precise or may access count, and name matches (including those over the fan-in cap) do not, citing `2026-10-10-union-fields §4.1`. Read §3.1 first and edit only the sentence(s) that say name matches count.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_sinks.py tests/test_impact.py tests/test_detectors.py tests/test_reading.py 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 5: Run the backend suite and ruff, then commit**

Run: `PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tail -2 && ../../../backend/.venv/bin/ruff check codetortoise tests`
Expected: all pass; `All checks passed!`.

```bash
git add backend/codetortoise/sinks.py backend/tests/test_sinks.py docs/superpowers/specs/2026-10-09-shared-sinks-design.md
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "fix(sinks): a match by member name alone no longer counts toward a shared sink

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 3: Name-only readers fold into one Coverage line

**Files:**
- Modify: `backend/codetortoise/reading.py` (check 5 at ~923–934; `coverage` at ~1060; a new helper `name_only_users` next to `coverage`)
- Test: `backend/tests/test_reading.py`

**Interfaces:**
- Consumes: `_Ctx` (`x.im`, `x.changed`, `x.label(nid)`, `x.is_test_path(nid)`), `_live(x, kinds)`, `_n(count, noun)`.
- Produces: `name_only_users(x: _Ctx) -> dict[str, int]` (field label → distinct unchanged, non-test functions that reach a field the change newly writes only through heuristic edges); `coverage(...)` gains its lines.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_reading.py` (after `test_a_reader_row_names_its_field_and_a_shared_sink_has_no_reader_rows`):

```python
def _named(c, *fns):
    """Make the given functions' edges into the written field matches by name only."""
    ids = {n.id for n in c.impact.nodes.values() if n.label in fns}
    for e in c.impact.edges:
        if e.src in ids and e.kind in ("reads", "writes"):
            e.confidence = "heuristic"


def test_readers_matched_by_name_only_are_one_coverage_line_not_checks():
    """Spec 2026-10-10-union-fields §4.2."""
    c = _world([_edit("config", "drv/cfg.c"), _same("report", "svc/rep.c"), _same("peek", "svc/peek.c"),
                _same("poke", "svc/poke.c"), _edit("dump", "svc/dump.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged"),
                       ("peek", "Uart", "errors", "read", "added"), ("poke", "Uart", "errors", "read", "added"),
                       ("poke", "Uart", "errors", "write", "added")])
    _named(c, "peek", "poke")
    open_, _ = _checks(c, _set(["N1"], ["N5"]))
    assert [(k.kind, k.function) for k in open_] == [("reader", "report")]
    assert coverage(_x(c), has_tests=True) == ["2 functions use a field named `errors`, matched by name only — not checked"]
    c.impact.edges.append(c.impact.edges[-1].model_copy(update={"id": "E99", "kind": "reads", "confidence": "precise"}))
    open_, _ = _checks(c, _set(["N1"], ["N5"]))                 # a precise read as well: a reader check, not a name match
    assert sorted(k.function for k in open_) == ["poke", "report"]
    assert coverage(_x(c), has_tests=True) == ["1 function uses a field named `errors`, matched by name only — not checked"]


def test_a_shared_sinks_name_matches_add_no_coverage_line():
    c = _world([_edit("config", "drv/cfg.c"), _same("peek", "svc/peek.c")],
               fields=[("config", "Log", "buf", "write", "added"), ("peek", "Log", "buf", "read", "added")])
    _named(c, "peek")
    _sink(c, "Log::buf")
    assert coverage(_x(c), has_tests=True) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_reading.py -k "name_only or name_matches" 2>&1 | tail -8`
Expected: FAIL in the first test — `open_` also holds reader checks for `peek` and `poke`. (The sink test may already pass; it pins that the new line respects sinks.)

- [ ] **Step 3: Implement**

In `backend/codetortoise/reading.py` check 5, take readers from non-heuristic edges only:

```python
            for r in sorted({e.src for e in _live(x, {"reads"}) if e.dst == w.dst and e.confidence != "heuristic"},
                            key=lambda m: x.label(m)):
```

Add above `coverage`:

```python
def name_only_users(x: _Ctx) -> dict[str, int]:
    """Field label -> the unchanged, non-test functions that use a field the change newly writes only by a member of
    the same name (spec 2026-10-10-union-fields §4.2): not checked, only counted. A shared sink's users are never
    listed, so it has none here."""
    out: dict[str, int] = {}
    written = {w.dst for w in x.im.edges if w.src in x.changed and w.kind == "writes" and w.status == "added"
               and w.dst not in x.im.sinks}
    for fid in sorted(written, key=x.label):
        live = [e for e in _live(x, {"reads", "writes"}) if e.dst == fid and e.src not in x.changed
                and not x.is_test_path(e.src)]
        named = {e.src for e in live if e.confidence == "heuristic"} - {e.src for e in live if e.confidence != "heuristic"}
        if named:
            out[x.label(fid)] = len(named)
    return out
```

In `coverage`, right after the `for label, n in sorted(x.im.capped_fields.items()):` block, add:

```python
    for label, n in name_only_users(x).items():
        out.append(f"{_n(n, 'function')} {'uses' if n == 1 else 'use'} a field named `{label.split('::')[-1]}`, matched by "
                   "name only — not checked")
```

Check that `_n(2, 'function')` gives `2 functions` and `_n(1, 'function')` gives `1 function` (it is used that way in the line above); if `x.changed` is not a set of node ids in `_Ctx`, use the attribute check 5 uses (`r in x.changed`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_reading.py 2>&1 | tail -3`
Expected: all pass, including `test_coverage_names_parse_problems_caps_files_outside_compile_databases_drift_and_missing_tests` unchanged (its fixture has no heuristic edges).

- [ ] **Step 5: Run the backend suite, ruff and the e2e reading specs, then commit**

Run: `PYTHONPATH=$PWD ../../../backend/.venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tail -2 && ../../../backend/.venv/bin/ruff check codetortoise tests`
Expected: all pass; `All checks passed!`.

Then from `.worktrees/union-fields/frontend` (node_modules symlinked; build first):
`npm run build >/dev/null && TMPDIR=$(git rev-parse --show-toplevel)/.pwtmp TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) $(cd ../../../backend && pwd)/.venv/bin/python -m codetortoise.cli" npx playwright test --reporter=line 2>&1 | tail -3`
Expected: all pass (the fixture's check counts may change only where a check came from a name match; update such an expectation and say so in the commit message).

```bash
git add backend/codetortoise/reading.py backend/tests/test_reading.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "fix(reading): readers matched by member name only are one Coverage line, not checks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```
