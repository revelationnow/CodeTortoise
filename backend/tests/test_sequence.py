"""Who wrote each line of a file several CLs edit (spec 2026-10-07-review-reading-phase2 §4)."""
from codetortoise.facts.model import Function
from codetortoise.sequence import Gap, Rewrite, rewrites, walk
from codetortoise.vcs.model import FileChange, PerClText


def _file(*texts, cls=None, gap=None):
    """texts: the base, then each CL's after text; CLs 101, 102, … unless `cls` names them. `gap`: (index, text) — that
    CL's before text differs from the previous CL's after (an outside CL changed the file in between)."""
    cls = cls or [101 + i for i in range(len(texts) - 1)]
    lines = ["\n".join(t) + "\n" if t else "" for t in texts]
    steps = []
    for i, cl in enumerate(cls):
        before = lines[i]
        if gap and gap[0] == i:
            before = "\n".join(gap[1]) + "\n"
        steps.append(PerClText(cl=cl, before=before, after=lines[i + 1]))
    return FileChange(depot="//d/f.c", local="/w/f.c", action="edit", before=lines[0], after=lines[-1], per_cl=steps)


def test_each_final_line_knows_the_cl_that_wrote_it_and_unchanged_lines_none():
    fl = walk(_file(["a", "b"], ["a", "x", "b"], ["a", "x", "b", "y"]))
    assert fl.wrote == [None, 101, None, 102]
    assert fl.over == [None, None, None, None] and fl.removed == [None, None]
    assert fl.rewritten == {} and fl.gaps == [] and fl.depot == "//d/f.c" and fl.local == "/w/f.c"


def test_a_later_cl_rewriting_an_earlier_cls_lines_records_the_rewrite_and_what_the_new_lines_replaced():
    fl = walk(_file(["a", "b"], ["a", "x1", "x2", "b"], ["a", "z", "b"]))
    assert fl.wrote == [None, 102, None]
    assert fl.over == [None, 101, None]                      # CL 102's `z` replaced CL 101's lines
    assert fl.rewritten == {101: {2: 102, 3: 102}}           # CL 101's after-text lines 2 and 3
    assert fl.replaced == [(101, 2, 102, 2), (101, 3, 102, 2)]   # each replaced line and where its replacement is now


def test_a_later_cl_deleting_an_earlier_cls_lines_is_a_rewrite_with_nothing_in_their_place():
    fl = walk(_file(["a", "b"], ["a", "x", "b"], ["a", "b"]))
    assert fl.wrote == [None, None] and fl.over == [None, None]
    assert fl.rewritten == {101: {2: 102}} and fl.replaced == [(101, 2, 102, None)]


def test_a_base_line_removed_records_the_cl_that_removed_it():
    fl = walk(_file(["a", "b", "c"], ["a", "c"], ["a", "c", "d"]))
    assert fl.removed == [None, 101, None] and fl.wrote == [None, None, 102] and fl.rewritten == {}


def test_a_change_from_outside_the_review_between_two_cls_is_a_gap_and_its_lines_carry_no_cl():
    # CL 101 adds x; an outside CL adds o; CL 103 adds y
    fl = walk(_file(["a"], ["a", "x"], ["a", "x", "o", "y"], cls=[101, 103], gap=(1, ["a", "x", "o"])))
    assert fl.wrote == [None, 101, None, 103]
    assert fl.gaps == [Gap(file="//d/f.c", after_cl=101, before_cl=103)]


def test_a_rewrite_of_a_rewrite_names_each_cl_it_replaced():
    fl = walk(_file(["a"], ["a", "x"], ["a", "y"], ["a", "z"]))
    assert fl.wrote == [None, 103] and fl.over == [None, 102]
    assert fl.rewritten == {101: {2: 102}, 102: {2: 103}}


def test_a_file_one_cl_touches_is_walked_the_same_way():
    fl = walk(_file(["a"], ["a", "x"]))
    assert fl.wrote == [None, 101] and fl.removed == [None]


def _fn(name, start, end, file="/w/f.c"):
    return Function(usr=f"c:@F@{name}", qualname=name, name=name, signature=f"void {name}(void)", return_type="void",
                    file=file, start_line=start, end_line=end)


def test_a_rewrite_row_counts_the_lines_names_the_function_its_replacement_is_in_and_where():
    fl = walk(_file(["a", "b"], ["a", "x1", "x2", "b"], ["a", "z", "b"]))
    assert rewrites({"//d/f.c": fl}, [_fn("outer", 1, 3), _fn("init", 2, 2)]) == [
        Rewrite(by=102, of=101, file="//d/f.c", function="init", lines=2, line=2)]   # the innermost function


def test_lines_deleted_with_nothing_in_their_place_are_a_rewrite_with_no_function():
    fl = walk(_file(["a", "b"], ["a", "x", "b"], ["a", "b"]))
    assert rewrites({"//d/f.c": fl}, [_fn("init", 1, 2)]) == [
        Rewrite(by=102, of=101, file="//d/f.c", function=None, lines=1, line=None)]


def test_one_rewrite_row_per_function_ordered_by_file_cl_and_line():
    fl = walk(_file(["a", "b", "c", "d"], ["a", "x", "b", "c", "y", "d"], ["a", "X", "b", "c", "Y", "d"]))
    rows = rewrites({"//d/f.c": fl}, [_fn("one", 1, 3), _fn("two", 4, 6)])
    assert [(r.function, r.lines, r.line) for r in rows] == [("one", 1, 2), ("two", 1, 5)]


def test_the_fixtures_cl_105_rewrites_the_line_cl_103_added_and_skipping_cl_104_leaves_a_gap(fx_source):
    logger = "//fixture/service/logger.c"
    fc = next(f for f in fx_source.load([103, 104, 105]).files if f.depot == logger)
    fl = walk(fc)
    assert fl.rewritten == {103: {7: 105}} and fl.gaps == []
    assert fl.wrote[6] == 105 and fl.over[6] == 103 and fl.wrote.count(104) == 5
    fc = next(f for f in fx_source.load([103, 105]).files if f.depot == logger)
    assert walk(fc).gaps == [Gap(file=logger, after_cl=103, before_cl=105)]
