# Stable field ids and name-only matches — design

Date: 2026-10-10. Status: draft for owner review.
Owner feedback (2026-10-09): "when there are multiple fields in a union, untouched fields of the union aliasing the
same memory are triggering a large number of checks, this should be handled somehow".
Approved approach: A (stable ids for fields of anonymous records) + B (name-only matches are informational).
Union storage aliasing (C) is out of scope.
Added while writing this spec (not in the approved outline): line-free labels for the same records (§3.3), since
the labels have the same line-shift weakness as the ids.

## 1. Problem

Two independent causes produce the flood.

### 1.1 Field ids that move with the header

The facts stage keys every field by its libclang USR (`FieldAccess.field`), and the impact model keys field nodes
`field:<USR>`. For a field of an anonymous record that is not itself an anonymous member, libclang puts the record's
file and byte offset in the USR. Verified with the bundled libclang, the same header before and after one line is
inserted above it:

| Field | Before | After |
|---|---|---|
| `struct dev { union { unsigned raw; … } ctl; }` → `raw` | `c:@S@dev@U@a.h@105@FI@raw` | `c:@S@dev@U@b.h@118@FI@raw` |
| … `union { … struct { unsigned en:1; }; } ctl;` → `en` | `c:@S@dev@U@a.h@105@Sa@FI@en` | `c:@S@dev@U@b.h@118@Sa@FI@en` |
| `typedef union { struct { unsigned lo:16; } bits; } reg_t;` → `lo` | `c:@UA@reg_t@S@a.h@31@FI@lo` | `c:@UA@reg_t@S@b.h@44@FI@lo` |
| `struct dev { struct { int x; } pos[2]; }` → `x` | `c:@S@dev@S@a.h@200@FI@x` | `c:@S@dev@S@b.h@213@FI@x` |
| `static struct { int a; } g_anon;` → `a` | `c:a.h@S@a.h@239@FI@a` | `c:b.h@S@b.h@252@FI@a` |

These are stable: a named record's field (`c:@S@dev@FI@id`), a typedef'd anonymous record's field
(`c:@UA@reg_t@FI@word`), and a field of an anonymous member (`c:@S@dev@Ua@FI@i`).

(The table uses `a.h`/`b.h` to show the offset; in a real review the file name is the same and only the offset moves.)

So any edit that shifts bytes above such a record in its header gives every one of its fields two ids, one per side.
Register maps — a union of a raw word and a bit-field struct — are exactly this shape. Then:

- a changed function that writes `d->ctl.raw` exactly as before is reported as "now writes `dev.ctl::raw`" and
  "no longer writes `dev.ctl::raw`" (the write sets are compared by id in `detectors/field_mutation.py`);
- its write edge is "added" (only the after variant has it), so every unchanged reader of that field becomes an
  "Unchanged reader" check (`reading.py` check 5), and every reader edge of the field is itself "added"/"removed";
- the field's users split across two nodes, which distorts the shared-sink count.

The fields are untouched; only the header moved. That is the reported flood.

The field labels (`record_name()`, `record::field`) have the same weakness in two shapes: an anonymous record that is an
anonymous member (the bit-field struct inside `ctl`) and an anonymous record that is the element type of an array or
pointer member (`pos[2]`) are both labelled `anonymous struct (<file>:<line>)`. Verified: `en` is labelled
`anonymous struct (a.h:4)` and `x` `anonymous struct (a.h:6)`. Such labels change when the line moves (so a shared-sink
mark on one is lost) and do not say where the field lives.

### 1.2 Name-only matches counted as users

For each field a changed function writes, `impact.py` step 3 adds `heuristic` edges from functions outside the parsed
TUs that use a member with the same name (`index.member_refs(name)`, limited to files that can see the record's header).
Over `heuristic_fanin_cap` the functions are only counted (`capped_fields`). Both feed:

- `sinks.find_sinks`: `users` counts heuristic edges and adds `capped_fields`, so a common member name (`antenna_index`,
  `trx_id`, `len`) can push a field over `sink_threshold`, or inflate the count shown;
- `reading.py` check 5: a heuristic `reads` edge into a newly written field is an "Unchanged reader" check like any
  other. One common name gives dozens of checks, most of them about unrelated records.

## 2. Goals

- A field's id is the same before and after unless the field itself (its name or its enclosing named path) changed.
- A name-only match never creates a check and never counts toward a shared sink. It is still reported, once per
  field, in Coverage.
- The owner's check marks are not lost (check keys contain no ids). Shared-sink marks are not lost except on labels
  that already moved with their line (§3.4).
- A field's label names where it lives (`dev.ctl::en`, `dev.pos::x`) instead of a file and line whenever an enclosing
  named record exists.

Non-goals: modelling union storage aliasing (a write to `raw` is not treated as a write to `en`); changing how
tree-sitter names fields (`name:<field>`).

## 3. A — stable field ids

### 3.1 Rule

A new function `field_id(f: Cursor) -> str` in `facts/aliasflow.py` gives a FIELD_DECL's id:

1. If `f.get_usr()` has no offset segment, it is the id. An offset segment is `@<digits>` followed by `@` or the end of
   the USR (identifiers cannot be all digits, so this matches only offsets).
2. Otherwise the id is `record_id(f.semantic_parent) + "@FI@" + f.spelling`, where `record_id(rec)` is:
   - `rec.get_usr()` when it has no offset segment (named records, typedef'd anonymous records, anonymous members);
   - for an anonymous record that is the type of a named member `m` of an enclosing record `outer`:
     `record_id(outer) + "@" + kind + ">" + m.spelling`, kind `U` for a union and `S` otherwise
     (`c:@S@dev@U>ctl`, so `raw` is `c:@S@dev@U>ctl@FI@raw`);
   - for an anonymous record that is an anonymous member of `outer` (no member names it):
     `record_id(outer) + "@" + kind + "a"`, matching libclang's own `Ua`/`Sa`
     (`en` is `c:@S@dev@U>ctl@Sa@FI@en`);
   - for a record with no enclosing record (file, namespace or function scope; a named record declared in a function
     carries an offset too): a scope — `c:` + the base name of its file at file scope, else the USR of the function or
     namespace declaring it — then `@` + kind + `~` + the record's name if it has one, else the first variable declared
     with that type among the record's semantic parent's children, else the record's field names joined with `,`
     (`c:a.h@S~g_anon`, so `a` is `c:a.h@S~g_anon@FI@a`; `struct point` inside `f1` is `c:@F@f1@S~point`).
     Amended after the final review: without the scope, records declared in different functions shared one id.


The member lookup is a new helper `_holder(outer, rec) -> Cursor | None`: the FIELD_DECL of `outer` whose canonical
type, after stripping arrays and pointers (`element_type` / `get_pointee()` until neither applies), is declared by
`rec`. Today's `record_name()` lookup does not strip arrays or pointers; it switches to `_holder` (§3.3). `record_id`
results are cached per record cursor hash, one cache per TU.

### 3.2 Where ids are used

Every place `aliasflow.py` takes a FIELD_DECL's USR uses `field_id(f)` instead: the access-path step tuple in `lval`,
`_field_file` (its maps are keyed by the id), and the two direct `FieldAccess(field=…)` constructions. Nothing else in
the facts stage reads field USRs. `FieldAccess.field`'s comment becomes "stable field id (see `field_id`), or
`name:<field>` when heuristic".

Downstream code keys on `field:<FieldAccess.field>` only (impact, board, reading, detectors, `facts_prep`,
`llm/tortoise.py`) and needs no change.

### 3.3 Labels

`record_name(rec)` for an anonymous record becomes:

- held by a named member of an enclosing record (found by `_holder`, so arrays and pointers count):
  `record_name(outer) + "." + member` — as today, plus the array/pointer case (`dev.pos`);
- an anonymous member of an enclosing record: `record_name(outer)`, since its fields are written as fields of `outer`
  (`d->ctl.en`, so `en` is labelled `dev.ctl::en`);
- otherwise unchanged: `anonymous struct|union (<file>:<line>)`.

### 3.4 What changes for existing reviews

There is no facts cache, so the next run of a review uses the new ids. Check keys
(`kind|path|function|related`) contain no ids, so the owner's check marks carry over; check keys and texts that quote
a relabelled field change once. Field labels change only where they were `anonymous struct (<file>:<line>)`, so a
shared-sink mark carries over unless it was on such a label (which a line move already broke). Stored briefs keyed on piece content miss once where a piece named a
moved field; they are rebuilt on that run.

A known limit stays: a top-level anonymous record's label is still `anonymous struct (<file>:<line>)`, so a shared-sink
mark on such a field is lost when its line moves. This is rare (such records are usually typedef'd) and unchanged by
this work.

## 4. B — name-only matches are informational

A field edge whose confidence is `heuristic` is a name-only match: it comes from step 3's `member_refs` rows or from a
tree-sitter parse.

### 4.1 Shared sinks

`sinks.find_sinks` counts, per field, the distinct unchanged functions with a `reads` or `writes` edge into it whose
confidence is `precise` or `may`. Heuristic edges and `capped_fields` no longer count. Marked and listed sinks are
unchanged. The docstring and the shared-sinks spec's §3.1 wording are updated ("precise and name-matched alike" goes).

### 4.2 Reader checks

`reading.py` check 5 ("Unchanged reader") takes readers only from non-heuristic `reads` edges. For each field the
change newly writes (the same fields check 5 visits), the unchanged non-test functions that reach it only through
heuristic edges are counted instead, and `coverage()` gains one line per such field:

`N functions use a field named `x`, matched by name only — not checked` (`1 function uses …` for one)

where `x` is the field's member name (the part after `::` in its label), N counts distinct functions, and the lines
are sorted by label. The existing over-the-cap line for `capped_fields` stays as it is. A field with no heuristic-only
users adds no line.

`coverage()` receives what it needs through `_Ctx` (it already has `x.im` and the changed set); the count is computed
in one helper, `name_only_users(x) -> dict[str, int]` (field label → functions), used by `coverage()` only.

### 4.3 Unchanged

- The board's `may access <label> (name match)` notes and the field-mutation finding's "N more by name match"
  evidence stay; they are informational and already say so.
- Heuristic edges stay in the impact model; blast scoring keeps its 0.4 weight for them.
- Heuristic call edges and the "callers found by name" checks are not part of this change.

## 5. Testing

Backend, pytest:

- `test_aliasflow` (or the clang extractor tests): one header parsed twice, the second with a line inserted above the
  records, covering each row of the table in §1.1. Every field access has the same `field` on both sides; the ids for
  `raw`, `en`, `lo`, `x` and `a` are exactly `c:@S@dev@U>ctl@FI@raw`, `c:@S@dev@U>ctl@Sa@FI@en`,
  `c:@UA@reg_t@S>bits@FI@lo`, `c:@S@dev@S>pos@FI@x`, `c:<header base name>@S~g_anon@FI@a`; stable USRs pass through
  unchanged.
- A top-level anonymous record with no variable gets the field-name fallback.
- Labels: `en` is `dev.ctl::en`, `x` is `dev.pos::x`, `lo` is `reg_t.bits::lo`, and a pointer member
  `struct { int q; } *p;` of `dev` gives `dev.p::q`; `a` keeps `anonymous struct (<file>:<line>)`.
- Pipeline/detector level: a change that only inserts a line above a union in a header and edits the body of a function
  that writes a union field (without changing that write) yields no "now writes"/"no longer writes" finding for the
  field and no "Unchanged reader" check for its readers.
- `test_sinks`: a field with more than `threshold` heuristic users and no precise users is not a sink; `capped_fields`
  does not count; precise users still do.
- `test_reading`: a newly written field with precise readers and heuristic-only readers gets reader checks for the
  precise ones only, and one Coverage line `N functions use a field named `x`, matched by name only — not checked`.

No frontend change: checks and Coverage lines render as they do today.
