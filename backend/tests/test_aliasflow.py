import clang.cindex as ci

from codetortoise.facts.aliasflow import FunctionAnalyzer
from codetortoise.paths import canon
from codetortoise.toolchain.libclang import load_libclang

ALIAS_C = """struct Inner { int n; };
struct Foo { int count; struct Inner inner; struct Foo *child; int arr[4]; };
int helper(int *p);
void consume(struct Foo *f);
void *memset(void *s, int c, unsigned long n);
int g_total;
int touch(struct Foo *s, int v) {
  struct Foo *c = s->child;
  int *q = &s->count;
  struct Inner *in = &s->inner;
  int *e = s->arr + 2;
  struct Foo local;
  local.count = 1;
  c->count = v;
  *q += 1;
  in->n++;
  e[0] = 4;
  g_total = v;
  helper(&s->arr[1]);
  memset(&s->inner, 0, sizeof(s->inner));
  ((struct Inner *)q)->n = 2;
  consume(s->child);
  return 0;
}
"""

ALIAS_CPP = """struct Inner { int n; };
struct State { Inner inner; int x; };
struct Engine {
  int level;
  int step(State &st);
};
int Engine::step(State &st) {
  auto &r = st.inner;
  r.n += 2;
  level = 3;
  this->level++;
  State *p = nullptr;
  p = &st;
  p->x = 1;
  return 0;
}
"""


def writes(tmp_path, name, src, args, fn_name):
    load_libclang(None)
    f = tmp_path / name
    f.write_text(src)
    tu = ci.Index.create().parse(str(f), args=args)
    assert not [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    fn = next(c for c in tu.cursor.walk_preorder()
              if c.spelling == fn_name and c.is_definition() and c.kind in (ci.CursorKind.FUNCTION_DECL, ci.CursorKind.CXX_METHOD))
    fields, globs = FunctionAnalyzer(fn, fn.get_usr()).analyze()
    return fields, globs, {(a.line, a.path, a.mode, tuple(a.via), a.confidence) for a in fields if a.mode != "read"}


def test_c_alias_writes(tmp_path):
    fields, globs, w = writes(tmp_path, "alias.c", ALIAS_C, ["-xc"], "touch")
    assert (13, "local.count", "write", (), "precise") in w
    assert (14, "s.child->count", "write", ("c",), "precise") in w
    assert (15, "s.count", "write", ("q",), "precise") in w
    assert (16, "s.inner.n", "write", ("in",), "precise") in w
    assert (17, "s.arr[]", "write", ("e",), "may") in w
    assert (19, "s.arr[]", "may_write", ("call:helper",), "may") in w
    assert (20, "s.inner", "write", ("call:memset",), "precise") in w
    assert (21, "s.count.n", "write", ("q",), "may") in w
    # passing a pointer field's pointee on is not a write to the field itself
    assert not any(line == 22 for line, *_ in w)
    assert [(g.var_name, g.line) for g in globs if g.mode == "write"] == [("g_total", 18)]
    local = [a for a in fields if a.path == "local.count"][0]
    assert local.root_kind == "local"


def test_cpp_reference_this_and_reassigned_pointer(tmp_path):
    _, _, w = writes(tmp_path, "alias.cpp", ALIAS_CPP, ["-xc++", "-std=c++17"], "step")
    assert (9, "st.inner.n", "write", ("r",), "precise") in w
    assert (10, "this.level", "write", (), "precise") in w
    assert (11, "this.level", "write", (), "precise") in w
    assert (14, "st.x", "write", ("p",), "precise") in w


def test_reads_are_recorded_with_paths(tmp_path):
    fields, _, _ = writes(tmp_path, "alias.c", ALIAS_C, ["-xc"], "touch")
    reads = {(a.path, a.field_name) for a in fields if a.mode == "read"}
    assert ("s.child", "child") in reads


MACRO_C = """#define REG_WRITE(r, v) ((r) = (v))
#define INC(x) ((x)++)
#define SET_BIT(r, b) ((r) |= (1u << (b)))
struct U { int ctrl; int cnt; unsigned flags; };
void poke(struct U *u) {
  REG_WRITE(u->ctrl, 5);
  INC(u->cnt);
  SET_BIT(u->flags, 3);
}
"""


def test_writes_spelled_inside_macros(tmp_path):
    _, _, w = writes(tmp_path, "macro.c", MACRO_C, ["-xc"], "poke")
    assert {(line, path, mode) for line, path, mode, _, _ in w} == {
        (6, "u.ctrl", "write"), (7, "u.cnt", "write"), (8, "u.flags", "write")}


FRESH_C = """struct E { int n; char sig[4]; };
void *git__malloc(unsigned long);
void *memcpy(void *d, const void *s, unsigned long n);
struct E *lookup(void);
void mk(void) {
  struct E *e = git__malloc(sizeof(*e));
  e->n = 1;
  memcpy(e->sig, "ab", 2);
  struct E *g = lookup();
  g->n = 2;
}
"""


def test_writes_to_freshly_allocated_objects_are_local(tmp_path):
    fields, _, w = writes(tmp_path, "fresh.c", FRESH_C, ["-xc"], "mk")
    roots = {(a.line, a.path, a.root_kind) for a in fields if a.mode != "read"}
    assert (7, "e.n", "local") in roots and (8, "e.sig[]", "local") in roots
    assert (10, "?.n", "unknown") in roots  # object from a getter may be shared


ANON_C = """typedef struct { int size; } vec_t;
struct outer { struct { int size; struct { int depth; } inner; } frame; int n; };
static struct { int count; } stats;
union u { struct { int lo; } half; };
void f(vec_t *v, struct outer *o, union u *x) { v->size = 1; o->frame.size = 2; o->frame.inner.depth = 3; stats.count = 4;
  x->half.lo = 5; }
"""


def test_anonymous_records_are_named_by_typedef_member_or_place(tmp_path):
    fields, _, _ = writes(tmp_path, "anon.c", ANON_C, ["-xc"], "f")
    records = {a.field_name: a.record for a in fields if a.mode == "write"}
    here = str(tmp_path / "anon.c")
    assert records["size"] in ("vec_t", "outer.frame")
    assert {a.record for a in fields if a.field_name == "size"} == {"vec_t", "outer.frame"}
    assert records["depth"] == "outer.frame.inner" and records["lo"] == "u.half"
    assert records["count"] == f"anonymous struct ({here}:3)"
    assert not any("unnamed" in a.record for a in fields)


def test_the_facts_stage_makes_anonymous_record_places_workspace_relative():
    from codetortoise.facts.model import Facts, FieldAccess, TuInfo, relative_records
    acc = FieldAccess(fn="f", field="c:@S@x@FI@n", field_name="n", record="anonymous struct (/ws/src/a.c:3)", file="/ws/src/a.c",
                      line=4, path="s.n", root_kind="global", mode="write")
    named = acc.model_copy(update={"record": "outer.frame"})
    fx = [Facts(tu=TuInfo(file="/ws/src/a.c", variant="after"), fields=[acc, named])]
    relative_records(fx, "/ws/")
    assert [a.record for a in fx[0].fields] == ["anonymous struct (src/a.c:3)", "outer.frame"]


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
    d.mkdir(exist_ok=True)
    (d / "reg.h").write_text(header)
    (d / "main.c").write_text(REG_C)
    tu = ci.Index.create().parse(str(d / "main.c"), args=["-xc"])
    assert not [x for x in tu.diagnostics if x.severity >= ci.Diagnostic.Error]
    fn = next(c for c in tu.cursor.walk_preorder()
              if c.spelling == "f" and c.kind == ci.CursorKind.FUNCTION_DECL and c.is_definition())
    return FunctionAnalyzer(fn, fn.get_usr()).analyze()[0]


def test_a_fields_id_does_not_move_with_its_header_and_names_where_it_lives(tmp_path):
    """Owner, 2026-10-09: untouched union fields flooded the review whenever their header shifted."""
    before = _accesses(tmp_path, "a", REG_H)
    after = _accesses(tmp_path, "a", "/* one more line */\n" + REG_H)
    assert {(a.field_name, a.mode, a.field) for a in before} == {(a.field_name, a.mode, a.field) for a in after}
    got = {a.field_name: (a.field, a.record) for a in before if a.mode == "write"}
    assert got["raw"] == ("c:@S@dev@U>ctl@FI@raw", "dev.ctl")
    assert got["en"] == ("c:@S@dev@U>ctl@Sa@FI@en", "dev.ctl")
    assert got["lo"] == ("c:@UA@reg_t@S>bits@FI@lo", "reg_t.bits")
    assert got["x"] == ("c:@S@dev@S>pos@FI@x", "dev.pos")
    assert got["q"] == ("c:@S@dev@S>p@FI@q", "dev.p")
    assert got["a"][0] == f"c:{canon(str(tmp_path / 'a' / 'reg.h'))}@S~g_anon@FI@a"
    assert got["a"][1].startswith("anonymous struct (")
    assert (got["word"][0], got["i"][0], got["id"][0]) == ("c:@UA@reg_t@FI@word", "c:@S@dev@Ua@FI@i", "c:@S@dev@FI@id")
    assert (got["word"][1], got["i"][1], got["id"][1]) == ("reg_t", "dev", "dev")


def test_a_nameless_record_with_no_variable_of_its_own_is_named_by_its_fields(tmp_path):
    fields, _, _ = writes(tmp_path, "local.c", "void h(void) { struct { int s, t; } v; v.s = 1; }\n", ["-xc"], "h")
    (s,) = [a for a in fields if a.field_name == "s" and a.mode == "write"]
    assert s.field == "c:@F@h@S~s,t@FI@s"                     # the function holding it is part of its id


def test_records_declared_in_different_functions_keep_different_ids(tmp_path):
    """Final review: a struct declared inside f1 and one inside f2 are different fields, named or not."""
    src = ("void f1(void) { struct point { int x, y; } p; p.x = 1; struct { int s; } q; q.s = 1; }\n"
           "void f2(void) { struct point { int x, y; } p; p.x = 2; struct { int s; } q; q.s = 2; }\n")
    ids = {}
    for fn in ("f1", "f2"):
        fields, _, _ = writes(tmp_path, "two.c", src, ["-xc"], fn)
        ids[fn] = {a.field_name: (a.field, a.record) for a in fields if a.mode == "write"}
    assert ids["f1"]["x"] == ("c:@F@f1@S~point@FI@x", "point") and ids["f2"]["x"] == ("c:@F@f2@S~point@FI@x", "point")
    assert ids["f1"]["s"][0] == "c:@F@f1@S~s@FI@s" and ids["f2"]["s"][0] == "c:@F@f2@S~s@FI@s"


def test_records_held_through_reference_members_are_told_apart(tmp_path):
    """Deferred minor (union-fields review): `_bare` stripped arrays and pointers but not C++ references."""
    src = ("struct R { struct { int v; } &r1; struct { int v; } &r2; };\n"
           "void f(R &x) { x.r1.v = 1; x.r2.v = 2; }\n")
    fields, _, _ = writes(tmp_path, "ref.cpp", src, ["-xc++"], "f")
    got = sorted((a.field, a.record) for a in fields if a.mode == "write")
    assert got == [("c:@S@R@S>r1@FI@v", "R.r1"), ("c:@S@R@S>r2@FI@v", "R.r2")]


def test_file_scope_records_in_same_named_headers_of_different_folders_are_told_apart(tmp_path):
    """Deferred minor: the id named the header by its base name only, so a/cfg.h and b/cfg.h shared their fields."""
    load_libclang(None)
    ids = []
    for sub in ("a", "b"):
        d = tmp_path / sub
        d.mkdir()
        (d / "cfg.h").write_text("static struct { int n; } cfg;\n")
        (d / "main.c").write_text('#include "cfg.h"\nvoid f(void) { cfg.n = 1; }\n')
        tu = ci.Index.create().parse(str(d / "main.c"), args=["-xc"])
        fn = next(c for c in tu.cursor.walk_preorder() if c.spelling == "f" and c.kind == ci.CursorKind.FUNCTION_DECL)
        (n,) = [a for a in FunctionAnalyzer(fn, fn.get_usr()).analyze()[0] if a.field_name == "n"]
        ids.append(n.field)
    assert ids == [f"c:{canon(str(tmp_path / s / 'cfg.h'))}@S~cfg@FI@n" for s in ("a", "b")]


def test_a_nameless_record_named_only_by_a_pointer_typedef_takes_the_typedefs_name(tmp_path):
    """Deferred minor: `typedef struct {…} *h_t;` declares no variable, so its id fell back to its field names."""
    src = ("typedef struct { int n; } *h_t;\nstatic struct { int n; } other;\n"
           "void f(h_t h) { h->n = 1; other.n = 2; }\n")
    fields, _, _ = writes(tmp_path, "ptr.c", src, ["-xc"], "f")
    here = canon(str(tmp_path / "ptr.c"))
    assert sorted(a.field for a in fields if a.mode == "write") == [f"c:{here}@S~h_t@FI@n", f"c:{here}@S~other@FI@n"]


PLACES_C = """struct Cell { int f; int g; };
struct Ctx { struct Cell cells[4]; int arr[4]; struct Cell one; struct Cell *ptr; int idx; };
struct Ctx g_ctx;
int g_arr[4];
struct Ctx *get_ctx(void);
void *memset(void *s, int c, unsigned long n);
void fill(struct Ctx *s, int i) {
  s->cells[i].f = 1;
  s->arr[i] = 2;
  s->one.g += 3;
  s->arr[s->idx]++;
  g_arr[i] = 4;
  g_ctx.cells[0].g = 5;
  get_ctx()->cells[i].f = 6;
  s->ptr->f = 7;
  memset(s->cells, 0, sizeof(s->cells));
  memset(&s->one, 0, sizeof s->one);
}
"""


def test_the_place_an_assignment_stores_to_is_not_a_read(tmp_path):
    """`s->cells` in `s->cells[i].f = 1` names where to store; only values used on the way (an index, a pointer
    followed) are read. Owner feedback 2026-10-12: element assignments showed as unchanged readers."""
    fields, globs, w = writes(tmp_path, "places.c", PLACES_C, ["-xc"], "fill")
    assert {(a.line, a.field_name) for a in fields if a.mode == "read"} == {(11, "idx"), (15, "ptr")}
    assert [g.var_name for g in globs if g.mode == "read"] == []
    assert {(line, path) for line, path, *_ in w} >= {(8, "s.cells[].f"), (9, "s.arr[]"), (10, "s.one.g"),
                                                    (11, "s.arr[]"), (15, "s.ptr->f"), (16, "s.cells[]"), (17, "s.one")}
