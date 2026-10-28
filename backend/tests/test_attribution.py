"""Which functions a change edits (change attribution): each parsed function's own lines against its file's line diff."""
from codetortoise.attribution import changed_functions, unparsed
from codetortoise.diffmap import DiffMap, FunctionChange
from codetortoise.facts.model import Facts, Function, TuInfo
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange

A, B = "/w/a.c", "/w/b.c"
THREE = ["int alpha(void)", "{", "  return 1;", "}", "int beta(void)", "{", "  int x = 2;", "  return x;", "}",
         "int gamma(void)", "{", "  return 3;", "}"]          # alpha 1-4, beta 5-9, gamma 10-13


def text(lines):
    return "\n".join(lines) + "\n"


def fn(name, start, end, file=A, usr=None):
    return Function(usr=usr or f"c:@F@{name}", qualname=name, name=name, signature=f"int {name}(void)",
                    return_type="int", file=file, start_line=start, end_line=end)


def facts(variant, *fns, file=A):
    return [Facts(tu=TuInfo(file=file, variant=variant), functions=list(fns))]


def three(variant):
    return facts(variant, fn("alpha", 1, 4), fn("beta", 5, 9), fn("gamma", 10, 13))


def change(before, after, local=A):
    return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                     files=[FileChange(depot="//d" + local, local=local, action="edit", before=before, after=after)])


def test_an_edit_marks_only_the_function_whose_own_lines_it_touches():
    after = list(THREE)
    after[7] = "  return x + 1;"
    assert changed_functions(three("before"), three("after"), change(text(THREE), text(after))) == {"c:@F@beta": "changed"}


def test_a_whitespace_only_edit_changes_nothing():
    after = list(THREE)
    after[7] = "    return   x;"
    assert changed_functions(three("before"), three("after"), change(text(THREE), text(after))) == {}


def test_a_pure_deletion_inside_a_function_changes_it():
    after = THREE[:6] + THREE[7:]                       # beta's "int x = 2;" deleted: beta is 5-8 after
    a = facts("after", fn("alpha", 1, 4), fn("beta", 5, 8), fn("gamma", 9, 12))
    assert changed_functions(three("before"), a, change(text(THREE), text(after))) == {"c:@F@beta": "changed"}


def test_a_new_function_is_added_and_a_dropped_one_removed():
    after = THREE[:9] + ["int delta(void)", "{", "  return 4;", "}"]   # gamma replaced by delta
    a = facts("after", fn("alpha", 1, 4), fn("beta", 5, 9), fn("delta", 10, 13))
    assert changed_functions(three("before"), a, change(text(THREE), text(after))) == {"c:@F@delta": "added",
                                                                                         "c:@F@gamma": "removed"}


def test_a_same_named_function_in_an_unchanged_file_is_never_changed():
    after = list(THREE)
    after[7] = "  return x + 1;"
    other = fn("beta", 1, 5, file=B, usr="c:b.c@F@beta")
    got = changed_functions(three("before") + facts("before", other, file=B), three("after") + facts("after", other, file=B),
                            change(text(THREE), text(after)))
    assert got == {"c:@F@beta": "changed"}


def test_a_tree_sitter_version_and_a_clang_version_of_one_function_are_one_function():
    after = list(THREE)
    after[7] = "  return x + 1;"
    b = facts("before", fn("alpha", 1, 4, usr="ts:/w/a.c#alpha"), fn("beta", 5, 9, usr="ts:/w/a.c#beta"),
              fn("gamma", 10, 13, usr="ts:/w/a.c#gamma"))
    assert changed_functions(b, three("after"), change(text(THREE), text(after))) == {"c:@F@beta": "changed"}


def test_a_function_moved_to_another_file_is_changed_only_if_its_text_changed():
    old, new = "/w/old.c", "/w/new.c"
    body = ["int alpha(void)", "{", "  return 1;", "}"]
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/old.c", local=old, action="move/delete", before=text(body), after=""),
        FileChange(depot="//d/new.c", local=new, action="move/add", before="", after=text(body))])
    b, a = facts("before", fn("alpha", 1, 4, file=old), file=old), facts("after", fn("alpha", 1, 4, file=new), file=new)
    assert changed_functions(b, a, cs) == {}
    edited = list(body)
    edited[2] = "  return 2;"
    cs.files[1].after = text(edited)
    assert changed_functions(b, a, cs) == {"c:@F@alpha": "changed"}


def test_a_files_edits_are_worked_out_once_however_many_functions_it_has(monkeypatch):
    import codetortoise.attribution as attribution
    from codetortoise.linediff import edits
    calls = []
    monkeypatch.setattr(attribution, "edits", lambda b, a, side: calls.append(side) or edits(b, a, side))
    n = 500
    before = [f"int f{i}(void) {{ return {i}; }}" for i in range(n)]
    after = [f"int f{i}(void) {{ return {i + 1}; }}" if i % 2 else before[i] for i in range(n)]
    fns = [fn(f"f{i}", i + 1, i + 1) for i in range(n)]
    got = changed_functions(facts("before", *fns), facts("after", *fns), change(text(before), text(after)))
    assert len(got) == n // 2 and sorted(calls) == ["after", "before"]


def test_a_mapped_change_no_parsed_function_covers_is_unparsed():
    dm = DiffMap(functions=[
        FunctionChange(file=A, depot="//d/a.c", qualname="beta", name="beta", kind="body_modified",
                       before_lines=(5, 9), after_lines=(5, 9)),
        FunctionChange(file=A, depot="//d/a.c", qualname="hidden", name="hidden", kind="body_modified",
                       before_lines=(20, 24), after_lines=(20, 24)),
        FunctionChange(file=A, depot="//d/a.c", qualname="gone", name="gone", kind="removed", before_lines=(10, 13))])
    assert [c.qualname for c in unparsed(dm, three("before"), three("after"))] == ["hidden"]
