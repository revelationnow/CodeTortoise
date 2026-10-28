"""A file's line diff: how its lines are counted, which lines each edit takes up, and whether an edit touches a function."""
import pytest

from codetortoise.linediff import edits, lines, matched_opcodes, opcodes, touches


@pytest.mark.parametrize(("text", "expected"), [
    ("a\nb\n", ["a", "b"]),
    ("a\nb", ["a", "b"]),                               # no final newline: the same lines
    ("a\r\nb\r\n", ["a", "b"]),
    ("a\rb\r", ["a", "b"]),                             # a lone carriage return ends a line
    ("a\n\nb\n", ["a", "", "b"]),
    ("a\n\n", ["a", ""]),                               # only one final line break ends the last line
    ("\n", [""]),
    ("", []),
    ("a\n\f\nb\n", ["a", "\f", "b"]),                   # a page-break line is one line, as clang and tree-sitter count it
    ("a\x0bb\x1cc\x85d e f\n", ["a\x0bb\x1cc\x85d e f"]),   # none of the other separators splitlines knows
])
def test_lines_are_broken_at_newlines_and_carriage_returns_only(text, expected):
    assert lines(text) == expected


def test_a_pure_insertion_takes_up_the_line_after_its_position_seen_from_the_before_side():
    assert edits("b\nc\n", "a\nb\nc\n", "before") == ((1, 1),)          # at the start: the old first line
    assert edits("a\nb\n", "a\nb\nc\n", "before") == ((3, 3),)          # at the end: the line after the old last one
    assert edits("a\nc\n", "a\nb\nc\n", "before") == ((2, 2),)          # inside: the line it went in front of
    assert edits("b\nc\n", "a\nb\nc\n", "after") == ((1, 1),)           # from the after side: the new lines themselves
    assert edits("a\nb\n", "a\nb\nc\nd\n", "after") == ((3, 4),)


def test_a_pure_deletion_takes_up_the_line_after_its_position_seen_from_the_after_side():
    assert edits("a\nb\nc\n", "a\nc\n", "after") == ((2, 2),)           # inside: the line that followed it
    assert edits("a\nb\nc\n", "b\nc\n", "after") == ((1, 1),)           # at the start
    assert edits("a\nb\nc\n", "a\nb\n", "after") == ((3, 3),)           # at the end: the line after the new last one
    assert edits("a\nb\nc\n", "a\nc\n", "before") == ((2, 2),)          # from the before side: the deleted line itself
    assert edits("a\nb\nc\nd\n", "a\nd\n", "before") == ((2, 3),)


def test_a_replacement_takes_up_its_own_lines_on_each_side_and_edits_come_in_order():
    before, after = "a\nb\nc\nd\ne\n", "a\nB\nc\nd\nE\nF\n"
    assert edits(before, after, "before") == ((2, 2), (5, 5))
    assert edits(before, after, "after") == ((2, 2), (5, 6))
    assert edits("a\nb\n", "a\nb\n", "after") == ()                     # nothing edited


@pytest.mark.parametrize(("lo", "hi", "expected"), [
    (1, 3, True),            # a function ending on the first line of an edit
    (5, 8, True),            # starting on the last line of an edit
    (3, 3, True), (5, 5, True), (10, 10, True), (12, 12, True),      # one line: the first or last of an edit
    (4, 4, True),            # inside an edit
    (1, 20, True),           # around both edits
    (1, 2, False),           # just above the first edit
    (6, 9, False),           # between the two
    (13, 20, False),         # just below the last
])
def test_a_function_is_touched_when_its_lines_share_even_one_line_with_an_edit(lo, hi, expected):
    assert touches(((3, 5), (10, 12)), lo, hi) is expected


def test_nothing_is_touched_when_there_are_no_edits():
    assert touches((), 1, 10) is False


def test_matched_opcodes_match_only_what_lies_between_the_common_first_and_last_lines():
    a, b = ["p", "q", "x", "y", "r"], ["p", "q", "X", "r"]
    assert matched_opcodes(a, b) == [("equal", 0, 2, 0, 2), ("replace", 2, 4, 2, 3), ("equal", 4, 5, 3, 4)]
    assert matched_opcodes(["a", "b"], ["a", "b"]) == [("equal", 0, 2, 0, 2)]
    assert matched_opcodes([], ["a"]) == [("insert", 0, 0, 0, 1)]
    assert matched_opcodes(["a", "b"], ["a"]) == [("equal", 0, 1, 0, 1), ("delete", 1, 2, 1, 1)]


def test_the_line_diff_of_two_texts_is_the_matched_opcodes_of_their_lines():
    before, after = "p\nq\nx\ny\nr\n", "p\nq\nX\nr\n"
    assert opcodes(before, after) == tuple(matched_opcodes(lines(before), lines(after)))
    assert edits(before, after, "before") == ((3, 4),) and edits(before, after, "after") == ((3, 3),)
