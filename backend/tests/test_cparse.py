from codetortoise.cparse import is_header, is_source, parse_source

CPP = """
#include "cpp/engine.h"
#define LIMIT 4
namespace svc {
struct Local { int a; };
int Engine::step(State &st) {
  auto &r = st.inner;
  r.n += 2;
  helper(st.x);
  obj.method();
  return base(st) + 1;
}
int free_fn(int);
}
"""


def test_functions_get_namespace_qualified_names():
    pf = parse_source("e.cpp", CPP)
    assert [f.qualname for f in pf.functions] == ["svc::Engine::step"]
    f = pf.functions[0]
    assert f.name == "step"
    assert f.signature == "int Engine::step(State &st)"
    assert (f.start_line, f.end_line) == (6, 12)


def test_calls_members_includes_macros_types_decls():
    pf = parse_source("e.cpp", CPP)
    assert {c.callee for c in pf.calls} == {"helper", "method", "base"}
    assert all(c.caller == "svc::Engine::step" for c in pf.calls)
    members = {(m.field, m.is_write) for m in pf.members}
    assert ("n", True) in members and ("inner", False) in members and ("x", False) in members
    assert ("method", False) not in members  # callee member expressions are calls, not field refs
    assert pf.includes == ["cpp/engine.h"]
    assert [m.name for m in pf.macros] == ["LIMIT"]
    assert [t.name for t in pf.types] == ["svc::Local"]
    assert [d.qualname for d in pf.decls] == ["svc::free_fn"]


def test_function_hash_changes_with_body_only():
    a = parse_source("a.c", "int f(int x) { return x; }\n").functions[0]
    b = parse_source("a.c", "int f(int x) {   return x; }\n").functions[0]
    c = parse_source("a.c", "int f(int x) { return x + 1; }\n").functions[0]
    assert a.text_hash == b.text_hash != c.text_hash


def test_extension_helpers():
    assert is_source("a.c") and is_source("b.HPP") and not is_source("c.txt")
    assert is_header("x.h") and not is_header("x.cpp")


def test_non_ascii_and_replacement_chars_keep_line_numbers():
    text = "/* d\u00e9j\u00e0 vu \ufffd\ufffd */\nint f(void) { return 0; }\n"
    (f,) = parse_source("x.c", text).functions
    assert (f.qualname, f.start_line) == ("f", 2)
