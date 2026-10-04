import clang.cindex as ci

from codetortoise.facts.aliasflow import FunctionAnalyzer
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
