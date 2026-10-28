from codetortoise.cparse import flatten_preproc, is_header, is_source, parse_source, preproc_spans

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


HEAD = "int first(void) { return 1; }\n"
SPLIT = """int alpha(int v)
{
#ifdef OPT_A
  if (v == 1) { return 2; }
  else
  {
#endif
    v++;
    return 0;
#ifdef OPT_A
  }
#endif
}
"""


def tail(n):
    return "".join(f"int g{i}(int v) {{ if (v) {{ return v + {i}; }} return {i}; }}\n" for i in range(n))


def _spans(pf):
    return [(f.name, f.start_line, f.end_line) for f in pf.functions]


def test_flatten_keeps_one_consistent_branch_of_each_conditional_and_every_line_number():
    text = "\n".join(["a", "#ifdef A", "b", "#else", "c", "#endif", "#ifndef A", "d", "#else", "e", "#endif",
                      "#if 0", "x", "#else", "y", "#endif", "#if defined(B) && C", "z", "#elif 1", "w", "#endif",
                      "#define M \\", "  1", "#if X \\", "  > 2", "q", "#endif", "end"])
    assert flatten_preproc(text) == "\n".join(["a", "", "b", "", "", "", "", "", "", "e", "", "", "", "", "y", "", "",
                                               "z", "", "", "", "#define M \\", "  1", "", "", "q", "", "end"])


def test_flatten_blanks_a_continued_directive_in_crlf_text_too():
    text = ("int alpha(void)\r\n{\r\n#if defined(OPT_A) && \\\r\n    defined(OPT_B)\r\n  return 1;\r\n#else\r\n  return 2;\r\n"
            "#endif\r\n}\r\n")
    assert flatten_preproc(text) == "int alpha(void)\r\n{\r\n\n\n  return 1;\r\n\n\n\n}\r\n"


def test_a_function_whose_braces_an_ifdef_splits_is_found_on_the_flattened_text():
    text = HEAD + SPLIT + tail(6)
    assert "alpha" not in [f.name for f in parse_source("a.c", text).functions]     # the raw parse loses it
    pf = parse_source("a.c", text, flatten="auto")
    assert ("alpha", 2, 14) in _spans(pf) and pf.flattened


def test_a_flattened_function_is_hashed_on_the_original_text_so_an_edit_in_a_dropped_branch_counts():
    text = HEAD + SPLIT.replace("#ifdef OPT_A\n  }\n#endif", "#ifdef OPT_A\n  }\n#else\n    v = 0;\n#endif") + tail(6)
    a, b = parse_source("a.c", text, flatten="auto"), parse_source("a.c", text.replace("v = 0;", "v = 1;"), flatten="auto")
    ha, hb = {f.name: f.text_hash for f in a.functions}, {f.name: f.text_hash for f in b.functions}
    assert ha["alpha"] != hb["alpha"] and ha["g0"] == hb["g0"]


def test_complementary_conditions_are_read_one_way():
    text = "#ifdef OPT_B\nint beta(int v, int w)\n{\n#endif\n#ifndef OPT_B\nint beta(int v)\n{\n#endif\n  return v;\n}\n" + tail(6)
    assert ("beta", 2, 10) in _spans(parse_source("a.c", text, flatten="auto"))


def test_a_function_only_the_raw_parse_read_in_a_dropped_branch_is_kept():
    text = HEAD + SPLIT + tail(6) + "#ifdef OPT_C\nint gamma(void) { return 1; }\n#else\nint delta(void) { return 2; }\n#endif\n"
    names = [f.name for f in parse_source("a.c", text, flatten="auto").functions]
    assert {"alpha", "gamma", "delta"} <= set(names)


def test_a_statement_parsed_as_a_function_is_dropped():
    text = ("int pick(int v)\n{\n  if (v == 1) {\n    v = 2;\n  }\n#ifndef OPT_D\n  else if (v == 3) {\n    v = 4;\n  }\n"
            "#endif\n  return v;\n}\n")
    assert [f.name for f in parse_source("a.c", text).functions] == ["pick", "if"]
    pf = parse_source("a.c", text, flatten="auto")
    assert _spans(pf) == [("pick", 1, 12)] and pf.flattened


def test_an_untangled_file_is_not_flattened():
    text = "int first(void) { return 1; }\n#ifdef OPT_A\nint beta(void) { return 2; }\n#endif\n"
    pf = parse_source("a.c", text, flatten="auto")
    assert not pf.flattened and _spans(pf) == [("first", 1, 1), ("beta", 3, 3)]


def test_a_flattened_parse_of_crlf_and_non_ascii_text_keeps_spans_and_hashes():
    text = "int first(void) { return 1; } /* é */\r\n" + SPLIT.replace("\n", "\r\n") + tail(6).replace("\n", "\r\n")
    raw, flat = parse_source("a.c", text), parse_source("a.c", text, flatten="always")
    assert ("alpha", 2, 14) in _spans(flat)
    same = {f.name: f for f in raw.functions}
    assert len(same) == 7
    assert all((same[f.name].start_line, same[f.name].end_line, same[f.name].text_hash) ==
               (f.start_line, f.end_line, f.text_hash) for f in flat.functions if f.name in same)


def test_tree_sitter_facts_find_a_function_whose_braces_an_ifdef_splits():
    from codetortoise.facts.clang_extractor import TuRequest
    from codetortoise.facts.treesitter_extractor import extract_tu_treesitter
    text = HEAD + SPLIT + tail(6)
    facts = extract_tu_treesitter(TuRequest(file="/w/a.c", args=[], variant="after", unsaved={"/w/a.c": text}))
    assert ("alpha", 2, 14) in [(f.name, f.start_line, f.end_line) for f in facts.functions]
