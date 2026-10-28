"""Which functions a change edits (change attribution): each parsed function's own lines against its file's line diff."""
import pytest

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


def test_a_non_static_function_moved_to_another_file_is_changed_only_if_its_text_changed():
    # non-static: its usr is the same in both files (a static function's usr carries its file name, so a moved static
    # function reads as added and removed, as the diff map always had it)
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


@pytest.mark.parametrize("edited", [1, 3])
def test_definitions_that_share_a_tree_sitter_usr_are_all_tested_so_an_edit_in_either_counts(edited):
    both = ["#ifdef OPT_A", "int pick(void) { return 1; }", "#else", "int pick(void) { return 2; }", "#endif"]
    after = list(both)
    after[edited] = "int pick(void) { return 9; }"
    usr = "ts:/w/a.c#pick"                     # tree-sitter names every definition of a name in a file the same
    ts = lambda variant: facts(variant, fn("pick", 2, 2, usr=usr), fn("pick", 4, 4, usr=usr))   # noqa: E731
    assert changed_functions(ts("before"), ts("after"), change(text(both), text(after))) == {usr: "changed"}


@pytest.mark.parametrize("first", ["/w/one/a.c", "/w/two/a.c"])
def test_a_function_defined_in_two_parsed_files_is_changed_when_either_definition_is_whichever_is_listed_first(first):
    one, two = "/w/one/a.c", "/w/two/a.c"
    body = ["int alpha(void)", "{", "  return 1;", "}"]
    edited = list(body)
    edited[2] = "  return 2;"
    order = [first, two if first == one else one]
    before = [x for f in order for x in facts("before", fn("alpha", 1, 4, file=f), file=f)]
    after = [x for f in order for x in facts("after", fn("alpha", 1, 4, file=f), file=f)]
    # one non-static function, one clang usr; only /w/one/a.c is in the change
    assert changed_functions(before, after, change(text(body), text(edited), local=one)) == {"c:@F@alpha": "changed"}


def test_a_header_function_several_tus_parsed_is_one_definition_however_many_parsed_it():
    h = "/w/a.h"
    body = ["static inline int alpha(void)", "{", "  return 1;", "}"]
    spaced = list(body)
    spaced[2] = "    return   1;"                       # whitespace only
    before = facts("before", fn("alpha", 1, 4, file=h), file="/w/x.c") + facts("before", fn("alpha", 1, 4, file=h), file="/w/y.c")
    after = facts("after", fn("alpha", 1, 4, file=h), file="/w/x.c")      # one TU parses it now, not two
    assert changed_functions(before, after, change(text(body), text(spaced), local=h)) == {}


def test_two_definitions_of_a_name_in_one_file_are_not_paired_with_another_version_of_that_name_by_name():
    both = ["#ifdef OPT_A", "int pick(void) { return 1; }", "#else", "int pick(void) { return 2; }", "#endif"]
    after = list(both)
    after[1] = "int pick(void) { return 9; }"
    ts = "ts:/w/a.c#pick"
    b = facts("before", fn("pick", 2, 2, usr=ts), fn("pick", 4, 4, usr=ts))
    a = facts("after", fn("pick", 2, 2))                  # clang takes one branch: which of the two it is cannot be told
    assert changed_functions(b, a, change(text(both), text(after))) == {ts: "removed", "c:@F@pick": "added"}


@pytest.mark.parametrize("defined_twice", ["after", "before"])
def test_a_clang_usr_defined_in_two_files_is_never_paired_by_name_with_a_tree_sitter_function_of_one_of_them(defined_twice):
    one, two = "/w/one/a.c", "/w/two/a.c"
    body = ["int alpha(void)", "{", "  return 1;", "}"]
    edited = list(body)
    edited[2] = "  return 2;"
    ts_one, ts_two = "ts:/w/one/a.c#alpha", "ts:/w/two/a.c#alpha"

    def parsed(variant, usrs):
        return [x for f, u in zip((one, two), usrs, strict=True) for x in facts(variant, fn("alpha", 1, 4, file=f, usr=u), file=f)]
    clang, tree = ("c:@F@alpha", "c:@F@alpha"), (ts_one, ts_two)
    b, a = (tree, clang) if defined_twice == "after" else (clang, tree)
    got = changed_functions(parsed("before", b), parsed("after", a), change(text(body), text(edited), local=one))
    assert got == ({"c:@F@alpha": "added", ts_one: "removed"} if defined_twice == "after" else
                   {ts_one: "added", "c:@F@alpha": "removed"})


def test_a_functions_definitions_are_compared_in_file_order_however_the_parses_are_listed():
    one, two = "/w/one/a.c", "/w/two/a.c"
    body = ["int alpha(void)", "{", "  return 1;", "}"]
    spaced = list(body)
    spaced[2] = "    return   1;"                       # whitespace only, in /w/one/a.c
    parsed = lambda variant, order: [x for f in order for x in facts(variant, fn("alpha", 1, 4, file=f), file=f)]   # noqa: E731
    got = changed_functions(parsed("before", (one, two)), parsed("after", (two, one)), change(text(body), text(spaced), local=one))
    assert got == {}


def test_a_form_feed_line_is_one_line_as_the_parsers_number_it_so_an_edit_after_it_is_still_found():
    alpha, beta = ["int alpha(void)", "{", "  return 1;", "}"], ["int beta(void)", "{", "  return 2;", "}"]
    before = alpha + ["\f", "\f", "\f"] + beta           # alpha 1-4, the page breaks 5-7, beta 8-11, as clang numbers them
    after = list(before)
    after[9] = "  return 3;"
    numbered = lambda variant: facts(variant, fn("alpha", 1, 4), fn("beta", 8, 11))   # noqa: E731
    assert changed_functions(numbered("before"), numbered("after"), change(text(before), text(after))) == {"c:@F@beta": "changed"}


def test_unparsed_checks_every_range_against_a_file_with_many_functions_by_how_far_they_reach():
    small = [fn(f"f{i}", 10 + 3 * i, 11 + 3 * i) for i in range(400)]        # lines 10-11, 13-14, ... 1207-1208
    parsed = lambda variant: facts(variant, *small, fn("outer", 2000, 2100), fn("inner", 2050, 2051))   # noqa: E731

    def mapped(name, lo, hi, kind="body_modified", file=A):
        return FunctionChange(file=file, depot="//d" + file, qualname=name, name=name, kind=kind,
                              before_lines=(lo, hi) if kind != "added" else None,
                              after_lines=(lo, hi) if kind != "removed" else None)
    dm = DiffMap(functions=[
        mapped("last_small", 1207, 1208),                  # covered by the last of the many
        mapped("past_small", 1209, 1210),                  # after the last of them, before outer
        mapped("gap", 12, 12),                             # between the first two
        mapped("across", 11, 13),                          # reaches into both of the first two
        mapped("above", 1, 5),                             # above the first function
        mapped("under_outer", 2090, 2095),                 # outer reaches past inner, the function that starts nearest
        mapped("past_end", 2200, 2300),
        mapped("gone_far", 1207, 1208, kind="removed"),    # a removed function is looked for among the before parse
        mapped("gone_gap", 1209, 1209, kind="removed"),
        mapped("ends_on_a_start", 5, 10),                  # its last line is the first line of the first function
        mapped("starts_on_an_end", 1208, 1209),            # its first line is the last line of the last of the many
        mapped("elsewhere", 1, 3, file=B)])                # a file no function was parsed in
    assert [c.qualname for c in unparsed(dm, parsed("before"), parsed("after"))] == [
        "past_small", "gap", "above", "past_end", "gone_gap", "elsewhere"]
