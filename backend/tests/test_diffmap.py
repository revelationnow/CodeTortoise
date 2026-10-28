from test_cparse import HEAD, SPLIT, tail

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


def test_an_edit_inside_a_dropped_branch_still_changes_its_function():
    before = HEAD + SPLIT.replace("#ifdef OPT_A\n  }\n#endif", "#ifdef OPT_A\n  }\n#else\n    v = 0;\n#endif") + tail(6)
    dm = map_changes(_cs(before, before.replace("v = 0;", "v = 1;")))
    assert [(f.qualname, f.kind) for f in dm.functions] == [("alpha", "body_modified")]


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


def test_a_genuinely_added_function_is_not_misread_even_beside_its_old_prototype():
    before = "int first(void) { return 1; }\nstatic int alpha(int a,\n                 int b);\n"
    added = before + "static int alpha(int a,\n                 int b)\n{\n  return a + b;\n}\n"
    dm = map_changes(_cs(before, added))
    assert [(f.qualname, f.kind, f.misread) for f in dm.functions] == [("alpha", "added", False)]
