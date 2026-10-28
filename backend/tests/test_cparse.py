from codetortoise.cparse import flatten_preproc, is_header, is_source, parse_source, preproc_spans
from codetortoise.linediff import lines

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


def test_types_list_their_fields_and_enums_their_enumerators():
    pf = parse_source("t.c", "struct Widget { int a, b; char *name; void (*cb)(int); unsigned flag : 1; };\n"
                             "enum Mode { MODE_OFF, MODE_ON = 2 };\n")
    assert {t.name: t.fields for t in pf.types} == {"Widget": ("a", "b", "name", "cb", "flag"),
                                                    "Mode": ("MODE_OFF", "MODE_ON")}


def test_a_types_fields_are_names_not_unnamed_bit_fields_methods_or_dropped_references():
    c = parse_source("t.c", "struct Widget { unsigned flag : 1; unsigned : 3; unsigned level : 2; };\n")
    assert [t.fields for t in c.types] == [("flag", "level")]       # tree-sitter gives `unsigned : 3;` a missing identifier
    members = ["int a;", "int &ref;", "int &&moved;", "char *name();", "const char *label() const;", "int &slot(int i);",
               "int get() const;", "Widget();", "~Widget();", "bool operator==(const Widget &o) const;", "void (*cb)(int);",
               "static int count;"]
    cpp = parse_source("t.cpp", "class Widget {\n public:\n" + "".join(f"  {m}\n" for m in members) + "};\n")
    assert [t.fields for t in cpp.types] == [("a", "ref", "moved", "cb", "count")]


def test_members_under_conditionals_and_in_anonymous_members_are_listed_each_once():
    widget = ("struct Widget {\n  int a;\n#ifdef OPT_A\n  int b;\n#else\n  long b;\n  int c;\n#endif\n"
              "#if defined(OPT_B)\n  int d;\n#elif defined(OPT_C)\n  int e;\n#endif\n"
              "  union { int u; float v; };\n  struct { int x; } gamma;\n  struct beta { int q; };\n  int f;\n};\n")
    mode = "enum Mode {\n  MODE_A,\n#ifdef OPT_A\n  MODE_B,\n#else\n  MODE_C,\n#endif\n  MODE_D\n};\n"
    got = {t.name: t.fields for t in parse_source("t.c", widget + mode).types if t.name in ("Widget", "Mode")}
    assert got == {"Widget": ("a", "b", "c", "d", "e", "u", "v", "gamma", "f"),       # `b` once; `x` and `q` belong to other types
                   "Mode": ("MODE_A", "MODE_B", "MODE_C", "MODE_D")}
    cpp = "class Widget {\n public:\n  int a;\n#ifdef OPT_A\n  int &r;\n  char *alpha();\n  struct { int x; int y; };\n#endif\n};\n"
    assert [t.fields for t in parse_source("t.cpp", cpp).types if t.name == "Widget"] == [("a", "r", "x", "y")]


def test_a_deeply_nested_conditional_in_a_type_does_not_overflow_the_call_stack():
    src = "struct Widget {\n  int a;\n" + "#ifdef OPT_A\n  int b;\n" * 1200 + "#endif\n" * 1200 + "  int z;\n};\n"
    assert [t.fields for t in parse_source("t.c", src).types if t.name == "Widget"] == [("a", "b", "z")]


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
# a signature an #ifdef alternates: tree-sitter ends each branch's signature with a missing ";", on the line before a directive
ALTERNATE = """#ifdef OPT_B
static int beta(int v, int w)
#else
static int beta(int v)
#endif
{ return v; }
"""


def tail(n):
    return "".join(f"int g{i}(int v) {{ if (v) {{ return v + {i}; }} return {i}; }}\n" for i in range(n))


# a branch the flattened text drops, holding a function the raw parse reads with an error (a macro in its signature)
DROPPED = "#ifdef OPT_C\nint gamma(void) { return 1; }\n#else\nvoid LIMIT delta(int v)\n{\n  v++;\n}\n#endif\n"


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


def test_a_function_whose_signature_an_ifdef_alternates_is_found_on_the_flattened_text():
    text = HEAD + ALTERNATE + tail(6)
    assert "beta" not in [f.name for f in parse_source("a.c", text).functions]     # the raw parse loses it
    always = _spans(parse_source("a.c", text, flatten="always"))
    assert ("beta", 3, 7) in always                                               # the first branch's signature, to the body's end
    pf = parse_source("a.c", text, flatten="auto")
    assert _spans(pf) == always and pf.flattened


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


def test_a_function_the_raw_parse_read_with_an_error_in_a_dropped_branch_is_kept():
    text = HEAD + SPLIT + tail(6) + DROPPED
    assert ("delta", 24, 27) in _spans(parse_source("a.c", text))        # the raw parse finds it, with an error in it
    assert ("delta", 24, 27) in _spans(parse_source("a.c", text, flatten="auto"))


def test_a_statement_parsed_as_a_function_is_dropped():
    text = ("int pick(int v)\n{\n  if (v == 1) {\n    v = 2;\n  }\n#ifndef OPT_D\n  else if (v == 3) {\n    v = 4;\n  }\n"
            "#endif\n  return v;\n}\n")
    assert [f.name for f in parse_source("a.c", text).functions] == ["pick", "if"]
    pf = parse_source("a.c", text, flatten="auto")
    assert _spans(pf) == [("pick", 1, 12)] and pf.flattened


def test_a_statement_parsed_as_a_function_is_dropped_though_its_name_keeps_parentheses():
    text = ("int pick(int v)\n{\n  if (v == 1) {\n    v = 2;\n  }\n#ifndef OPT_D\n  else if ((v == 1)\n  (v == 1)\n  {\n"
            "    v = 4;\n  }\n#endif\n  return v;\n}\n")
    assert [f.name for f in parse_source("a.c", text).functions] == ["pick", "if((v==1)"]
    pf = parse_source("a.c", text, flatten="auto")
    assert _spans(pf) == [("pick", 1, 14)] and pf.flattened


def test_a_function_whose_name_has_parentheses_in_a_clean_file_is_neither_dropped_nor_a_reason_to_flatten():
    handler = "int (*get_handler(int id))(int)\n{\n  return 0;\n}\n"
    functor = "struct Widget { int operator()(int x) const; };\nint Widget::operator()(int x) const\n{\n  return x;\n}\n"
    for path, text, name in [("a.c", handler, "(*get_handler(intid))"), ("a.cpp", functor, "operator()")]:
        pf = parse_source(path, text, flatten="auto")
        assert [f.name for f in pf.functions] == [name] and not pf.flattened


def test_a_function_named_by_a_macro_is_kept_and_does_not_flatten_a_file_with_no_conditional():
    text = "#define NAME(x) fn_##x\nint NAME(alpha)(int v) { return v; }\nint beta(void) { return 1; }\n"
    pf = parse_source("a.c", text, flatten="auto")
    assert _spans(pf) == [("NAME(alpha)", 2, 2), ("beta", 3, 3)] and not pf.flattened


def test_a_function_whose_name_is_in_parentheses_is_kept_and_does_not_flatten_a_file_with_no_conditional():
    text = ("struct Widget { typedef int result_type; static constexpr result_type(min)() { return 0; } };\n"
            "int beta(void) { return 1; }\n")
    pf = parse_source("a.cpp", text, flatten="auto")
    assert _spans(pf) == [("result_type(min)", 1, 1), ("beta", 2, 2)] and not pf.flattened


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


def test_tree_sitter_facts_find_a_function_whose_signature_an_ifdef_alternates():
    from codetortoise.facts.clang_extractor import TuRequest
    from codetortoise.facts.treesitter_extractor import extract_tu_treesitter
    text = HEAD + ALTERNATE + tail(6)
    facts = extract_tu_treesitter(TuRequest(file="/w/a.c", args=[], variant="after", unsaved={"/w/a.c": text}))
    assert ("beta", 3, 7) in [(f.name, f.start_line, f.end_line) for f in facts.functions]


def test_a_lone_cr_ends_a_line_for_the_parse_as_it_does_for_the_line_diff():
    text = "".join(f"int {n}(int v)\n{{\n  return v + {i};\n}}\n" for i, n in enumerate(["alpha", "beta", "gamma"]))
    text = text.replace("\n", "\r\r\n")       # tree-sitter's rows break at "\n" only; clang and the line diff at each "\r" too
    rows = lines(text)
    for flatten in ("never", "always"):
        got = [(f.name, rows[f.start_line - 1], rows[f.end_line - 1]) for f in parse_source("a.c", text, flatten=flatten).functions]
        assert got == [(n, f"int {n}(int v)", "}") for n in ("alpha", "beta", "gamma")]


def test_every_line_the_parse_reports_is_counted_the_way_the_line_diff_counts_it():
    src = ("#define LIMIT 4\nstruct Widget { int n; };\nint helper(int v);\nint pick(struct Widget *w)\n{\n  w->n = LIMIT;\n"
           "  return helper(w->n);\n}\n")
    text = src.replace("\n", "\r\r\n")
    rows = lines(text)
    pf = parse_source("a.c", text)
    assert [rows[m.line - 1] for m in pf.macros] == ["#define LIMIT 4"]
    assert [(rows[t.start_line - 1], rows[t.end_line - 1]) for t in pf.types] == [("struct Widget { int n; };",) * 2]
    assert [rows[d.line - 1] for d in pf.decls] == ["int helper(int v);"]
    assert [rows[c.line - 1] for c in pf.calls] == ["  return helper(w->n);"]
    assert [rows[m.line - 1] for m in pf.members] == ["  w->n = LIMIT;", "  return helper(w->n);"]
    assert [(rows[f.start_line - 1], rows[f.end_line - 1]) for f in pf.functions] == [("int pick(struct Widget *w)", "}")]


def test_preproc_spans_count_lines_the_way_the_line_diff_does():
    src = ("#ifdef CONFIG_WIN\nint f(void) { return 1; }\n#elif defined(X)\nint g;\n#else\nint h;\n#endif\n"
           "#if FOO > 1\nint k;\n#endif\n")
    assert preproc_spans("a.h", src) == [(1, 2, "defined(CONFIG_WIN)"), (3, 4, "defined(X)"), (5, 6, "!defined(X)"),
                                         (8, 10, "FOO > 1")]
    text = src.replace("\n", "\r\r\n")        # line n of src is lines n * 2 - 1 and n * 2 of this text
    assert preproc_spans("a.h", text) == [(1, 4, "defined(CONFIG_WIN)"), (5, 8, "defined(X)"), (9, 11, "!defined(X)"),
                                          (15, 19, "FOO > 1")]


def test_tree_sitter_facts_count_lines_the_way_the_line_diff_does():
    from codetortoise.facts.clang_extractor import TuRequest
    from codetortoise.facts.treesitter_extractor import extract_tu_treesitter
    text = (HEAD + tail(2)).replace("\n", "\r\r\n")
    facts = extract_tu_treesitter(TuRequest(file="/w/a.c", args=[], variant="after", unsaved={"/w/a.c": text}))
    assert [(f.name, f.start_line, f.end_line) for f in facts.functions] == [("first", 1, 1), ("g0", 3, 3), ("g1", 5, 5)]
