from codetortoise.cparse import is_header, is_source, parse_source, preproc_spans

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


def test_large_files_parse_without_crashing(tmp_path):
    # tree-sitter 0.26.0 corrupts node positions and segfaults on files of a few thousand lines;
    # run in a subprocess so a native crash fails this test instead of killing the whole run.
    import subprocess
    import sys
    src = "".join(f"int f{i}(int a, int b)\n{{\n\tint x = a + b;\n\tif (x > {i})\n\t\treturn x;\n\treturn -1;\n}}\n\n"
                  for i in range(400))
    (tmp_path / "big.c").write_text(src)
    code = ("import sys; from codetortoise.cparse import parse_source; p = sys.argv[1]; "
            "fs = parse_source(p, open(p).read()).functions; print(len(fs), fs[-1].start_line, fs[-1].end_line)")
    r = subprocess.run([sys.executable, "-c", code, str(tmp_path / "big.c")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
    assert r.stdout.split() == ["400", "3193", "3199"]


GUARDED = """#ifndef UART_H
#define UART_H
#ifdef CONFIG_WIN
int f(void) { return 1; }
#elif defined(X)
int g;
#else
int h;
#endif
#if FOO > 1
int k;
#endif
#endif
"""


def test_preproc_spans_give_each_branch_its_condition_and_skip_include_guards():
    assert preproc_spans("a.h", GUARDED) == [(3, 4, "defined(CONFIG_WIN)"), (5, 6, "defined(X)"), (7, 8, "!defined(X)"),
                                             (10, 12, "FOO > 1")]


def test_preproc_spans_negate_an_ifndef_in_its_else_branch():
    text = "#ifndef NO_LOG\nint a;\n#else\nint b;\n#endif\n"
    assert preproc_spans("a.c", text) == [(1, 2, "!defined(NO_LOG)"), (3, 4, "defined(NO_LOG)")]
