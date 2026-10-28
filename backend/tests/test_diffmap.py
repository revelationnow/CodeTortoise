import pytest
from test_cparse import ALTERNATE, DROPPED, HEAD, SPLIT, tail

from codetortoise.diffmap import map_changes
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def test_cl101_body_change_with_written_members(fx_source):
    dm = map_changes(fx_source.load([101]))
    assert [(f.qualname, f.kind, f.written_members) for f in dm.functions] == [("uart_send", "body_modified", ["tx"])]
    assert dm.types == []


def test_cl102_signature_type_and_decl_changes(fx_source):
    dm = map_changes(fx_source.load([102]))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("hal_write", "signature_changed")]
    assert sorted((t.name, t.kind) for t in dm.types) == [("Uart", "type_changed"), ("hal_write", "decl_changed")]


def test_added_removed_and_non_source_files():
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/x.c", local="/w/x.c", action="edit",
                   before="int a(void){return 1;}\nint b(void){return 2;}\n",
                   after="int b(void){return 2;}\nint c(void){return 3;}\n"),
        FileChange(depot="//d/README.txt", local="/w/README.txt", action="edit", before="a", after="b")])
    dm = map_changes(cs)
    assert sorted((f.qualname, f.kind) for f in dm.functions) == [("a", "removed"), ("c", "added")]
    assert dm.changed_files == ["/w/x.c"]


def _cs(before, after, local="/w/a.c"):
    return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                     files=[FileChange(depot="//d/a.c", local=local, action="edit", before=before, after=after)])


def _raw_parser(monkeypatch):
    """The diff map with no flattening: what tree-sitter alone makes of each version."""
    from codetortoise import cparse, diffmap
    monkeypatch.setattr(diffmap, "parse_source", lambda path, text, flatten="never": cparse.parse_source(path, text))


def test_an_edit_inside_a_function_whose_braces_an_ifdef_splits_is_mapped_to_it():
    before = HEAD + SPLIT + tail(6)
    dm = map_changes(_cs(before, before.replace("v++;", "v += 2;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("alpha", "body_modified")] and dm.flattened == ["/w/a.c"]


def test_an_edit_inside_a_function_whose_signature_an_ifdef_alternates_is_mapped_to_it():
    before = HEAD + ALTERNATE + tail(6)
    dm = map_changes(_cs(before, before.replace("return v;", "return v + 1;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("beta", "body_modified")] and dm.flattened == ["/w/a.c"]


@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r\r\n"])
def test_an_edit_is_mapped_to_its_function_whatever_the_line_ends_are(eol):
    before = (HEAD + tail(6)).replace("\n", eol)
    dm = map_changes(_cs(before, before.replace("v + 4;", "v + 40;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("g4", "body_modified")]


def test_a_file_whose_functions_are_all_unchanged_is_not_line_diffed(monkeypatch):
    from codetortoise import diffmap
    asked = []
    real = diffmap.edits
    monkeypatch.setattr(diffmap, "edits", lambda *a: asked.append(a) or real(*a))
    table = "".join(f"  {{ {i % 5}, 1, 0 }},\n" for i in range(4000))
    before = "static const int rows[][3] = {\n" + table + "};\n" + tail(2)
    after = before.replace("{ 3, 1, 0 },\n", "{ 3, 1, 9 },\n", 1)           # one row of the table edited, no function
    assert map_changes(_cs(before, after)).functions == [] and asked == []
    dm = map_changes(_cs(before, before.replace("return 0;", "return 7;", 1)))        # g0 edited: both sides are diffed
    assert [f.qualname for f in dm.functions] == ["g0"] and len(asked) == 2


@pytest.mark.parametrize(("tangled_side", "kind"), [("after", "added"), ("before", "removed")])
def test_both_versions_are_read_the_same_way_when_only_one_of_them_is_tangled(tangled_side, kind):
    clean, tangled = HEAD + tail(6), HEAD + SPLIT + tail(6)
    before, after = (clean, tangled) if tangled_side == "after" else (tangled, clean)
    dm = map_changes(_cs(before, after))
    assert [(f.qualname, f.kind, f.misread) for f in dm.functions] == [("alpha", kind, False)]
    assert dm.flattened == ["/w/a.c"]


def test_an_edit_inside_a_dropped_branch_still_changes_its_function():
    before = HEAD + SPLIT.replace("#ifdef OPT_A\n  }\n#endif", "#ifdef OPT_A\n  }\n#else\n    v = 0;\n#endif") + tail(6)
    dm = map_changes(_cs(before, before.replace("v = 0;", "v = 1;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("alpha", "body_modified")]


def test_an_edit_inside_a_function_with_a_parse_error_in_a_dropped_branch_is_mapped_to_it():
    before = HEAD + SPLIT + tail(6) + DROPPED
    dm = map_changes(_cs(before, HEAD + SPLIT + tail(6) + DROPPED.replace("v++;", "v += 2;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("delta", "body_modified")]


def test_an_edit_inside_a_function_named_by_a_macro_is_mapped_to_it_and_no_file_is_flattened():
    before = "#define NAME(x) fn_##x\nint NAME(alpha)(int v) { return v; }\nint beta(void) { return 1; }\n"
    dm = map_changes(_cs(before, before.replace("return v;", "return v + 1;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("NAME(alpha)", "body_modified")] and dm.flattened == []


def test_a_function_the_parser_loses_in_one_version_with_no_edit_in_it_is_not_a_change(monkeypatch):
    from codetortoise import cparse
    before, after = HEAD + SPLIT + tail(5), HEAD + SPLIT + tail(6)
    assert "alpha" in {f.name for f in cparse.parse_source("a.c", before).functions}          # found here …
    assert "alpha" not in {f.name for f in cparse.parse_source("a.c", after).functions}       # … lost here
    _raw_parser(monkeypatch)
    assert [(f.qualname, f.kind) for f in map_changes(_cs(before, after)).functions] == [("g5", "added")]


def test_an_added_function_the_old_text_defines_where_the_parser_found_none_is_marked_misread(monkeypatch):
    before = HEAD + SPLIT + tail(6)
    after = HEAD + SPLIT.replace("v++;", "v += 2;") + tail(5)
    _raw_parser(monkeypatch)
    dm = map_changes(_cs(before, after))
    assert [(f.qualname, f.kind, f.misread) for f in dm.functions] == [("alpha", "added", True), ("g5", "removed", False)]


def test_each_added_or_removed_function_is_judged_by_its_own_name_and_each_text_is_read_once(monkeypatch):
    from codetortoise import diffmap
    read = []
    real = diffmap._defined
    monkeypatch.setattr(diffmap, "_defined", lambda text: read.append(text) or real(text))
    before = HEAD + SPLIT + tail(6)
    after = (HEAD + "int extra(void) { return 0; }\nint extra2(void) { return 0; }\n" + SPLIT.replace("v++;", "v += 2;") + tail(5))
    _raw_parser(monkeypatch)
    dm = map_changes(_cs(before, after))
    assert [(f.qualname, f.kind, f.misread) for f in dm.functions] == [
        ("alpha", "added", True), ("extra", "added", False), ("extra2", "added", False), ("g5", "removed", False)]
    assert read == [before, after]          # the old text for the added ones, the new for the removed one: one read each


def test_the_names_a_text_defines_at_the_left_margin_are_counted_each_with_how_often():
    from codetortoise.diffmap import _defined
    text = ("static int alpha(int a,\n        int b)\n{\n  return a + b;\n}\n"
            "int alpha(int a);\n"                      # a prototype
            "  alpha(1);\n"                            # an indented call
            "beta(2);\n"                               # a call at the margin
            "static int\ngamma (void)\n{\n}\n"        # the type on the line before
            "int alpha(void)\n{\n}\n"                  # another definition of alpha
            "bool operator==(const A &a, const A &b)\n{\n  return true;\n}\n")
    assert _defined(text) == {"alpha": 2, "gamma": 1, "operator==": 1}


def test_a_genuinely_added_function_is_not_misread_even_beside_its_old_prototype():
    before = "int first(void) { return 1; }\nstatic int alpha(int a,\n                 int b);\n"
    added = before + "static int alpha(int a,\n                 int b)\n{\n  return a + b;\n}\n"
    dm = map_changes(_cs(before, added))
    assert [(f.qualname, f.kind, f.misread) for f in dm.functions] == [("alpha", "added", False)]


def test_type_decl_and_macro_changes_carry_both_texts_their_line_and_field_changes():
    before = "#define LIMIT 4\nstruct Widget { int a; int b; };\nint alpha(void);\n"
    after = "#define LIMIT 8\n\nstruct Widget { int a; int c; };\nint alpha(int v);\n"
    got = {t.name: t for t in map_changes(_cs(before, after, local="/w/w.h")).types}
    w = got["Widget"]
    assert (w.kind, w.line, w.fields_added, w.fields_removed) == ("type_changed", 3, ["c"], ["b"])
    assert (w.before, w.after) == ("struct Widget { int a; int b; }", "struct Widget { int a; int c; }")
    assert (got["alpha"].kind, got["alpha"].before, got["alpha"].after) == ("decl_changed", "int alpha(void);",
                                                                             "int alpha(int v);")
    assert (got["LIMIT"].kind, got["LIMIT"].line, got["LIMIT"].after) == ("macro_changed", 1, "#define LIMIT 8")


def test_a_removed_declaration_carries_its_old_line_and_text_and_an_added_one_its_new_ones():
    before = "#define OPT_A 1\nint first(void);\nstruct Widget { int a; };\n"
    after = "int first(void);\n#define OPT_B 2\nenum Mode { MODE_A, MODE_B };\n"
    got = {t.name: t for t in map_changes(_cs(before, after, local="/w/w.h")).types}
    assert {n: (t.kind, t.line, t.before, t.after, t.fields_added, t.fields_removed) for n, t in got.items()} == {
        "OPT_A": ("macro_removed", 1, "#define OPT_A 1", "", [], []),
        "Widget": ("type_removed", 3, "struct Widget { int a; }", "", [], []),
        "OPT_B": ("macro_added", 2, "", "#define OPT_B 2", [], []),
        "Mode": ("type_added", 3, "", "enum Mode { MODE_A, MODE_B }", [], [])}


def test_guarding_a_field_with_an_ifdef_or_dropping_the_guard_changes_the_text_not_the_fields():
    plain = "struct Widget { int a; int b; };\n"
    guarded = "struct Widget {\n  int a;\n#ifdef OPT_A\n  int b;\n#endif\n};\n"
    for before, after in ((plain, guarded), (guarded, plain)):
        (t,) = map_changes(_cs(before, after, local="/w/w.h")).types
        assert (t.kind, t.fields_added, t.fields_removed) == ("type_changed", [], [])


def test_a_field_or_enumerator_added_inside_an_ifdef_is_listed_as_added():
    before = "struct Widget { int a; };\nenum Mode { MODE_A };\n"
    after = ("struct Widget {\n  int a;\n#ifdef OPT_A\n  int c;\n#endif\n};\n"
             "enum Mode {\n  MODE_A,\n#ifdef OPT_A\n  MODE_B,\n#endif\n};\n")
    got = {t.name: (t.fields_added, t.fields_removed) for t in map_changes(_cs(before, after, local="/w/w.h")).types}
    assert got == {"Widget": (["c"], []), "Mode": (["MODE_B"], [])}


def test_a_text_is_stored_up_to_the_cap_and_not_beyond_it_but_the_change_and_its_fields_still_are():
    from codetortoise.diffmap import TEXT_CAP
    kept = "#define LIMIT " + "x" * (TEXT_CAP - len("#define LIMIT "))
    over = "#define OPT_C " + "x" * (TEXT_CAP - len("#define OPT_C ") + 1)
    assert (len(kept), len(over)) == (TEXT_CAP, TEXT_CAP + 1)
    big = "enum Mode { " + ", ".join(f"MODE_{i}" for i in range(200)) + " };"
    assert len(big) > TEXT_CAP
    short = "enum Widget { OPT_A };"
    before = f"{big}\n{short}\n"
    after = f"{big.replace(' };', ', MODE_NEW };')}\n{short.replace('OPT_A', 'OPT_B')}\n{kept}\n{over}\n"
    got = {t.name: t for t in map_changes(_cs(before, after, local="/w/w.h")).types}
    assert (got["LIMIT"].kind, got["LIMIT"].after) == ("macro_added", kept)
    assert (got["OPT_C"].kind, got["OPT_C"].after) == ("macro_added", "")
    assert (got["Widget"].before, got["Widget"].after) == ("enum Widget { OPT_A }", "enum Widget { OPT_B }")
    mode = got["Mode"]
    assert (mode.kind, mode.before, mode.after, mode.fields_added) == ("type_changed", "", "", ["MODE_NEW"])
