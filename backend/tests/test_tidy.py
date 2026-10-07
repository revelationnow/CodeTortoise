"""Evidence written for people (spec 2026-10-07-review-reading §12)."""
from codetortoise.tidy import tidy


def test_python_reprs_become_lists_and_sentences():
    assert tidy("by layer: {'L1: hal': 1, 'L2: drv': 3}") == "by layer: L1: hal (1), L2: drv (3)"
    assert tidy("returns before: ['0']; after: ['-2', '0']") == "returns before: 0; after: -2, 0"
    assert tidy("returns before: []; after: [1]") == "returns before: none; after: 1"


def test_counts_read_as_words():
    assert tidy("regs.h: 1 change(s) reach 4 TU(s)") == "regs.h: 1 change reaches 4 TUs"
    assert tidy("affect 1 translation unit(s) across 2 layer(s).") == "affect 1 translation unit across 2 layers."
    assert tidy("3 caller(s) must be re-checked: a, b, c") == "3 callers must be re-checked: a, b, c"


def test_a_listed_value_takes_the_number_of_its_list():
    assert tidy("uart_send: new return value(s) -2") == "uart_send: new return value -2"
    assert tidy("f: new return value(s) -2, -3") == "f: new return values -2, -3"


def test_arrows_read_as_arrows_and_code_is_left_alone():
    assert tidy("signature: `int f(int a[4])` -> `int f(int a[8])`") == "signature: `int f(int a[4])` → `int f(int a[8])`"
    assert tidy("writes Uart::errors via a -> b") == "writes Uart::errors via a → b"


def test_paths_under_the_workspace_read_relative_to_it():
    assert tidy("Changes in /ws/root/include/regs.h affect 4 translation unit(s)", root="/ws/root") == \
        "Changes in include/regs.h affect 4 translation units"
    assert tidy("Changes in /elsewhere/regs.h", root="/ws/root") == "Changes in /elsewhere/regs.h"


def test_anything_else_is_left_as_it_was():
    for text in ("[medium] flush drops it", "{not a dict}", "a set {1, 2} of ids", "plain text", ""):
        assert tidy(text) == text


def test_a_subscript_or_initialiser_after_a_name_is_code_not_a_list():
    for text in ("writes buf[0] after the lock", "reads x[-1]", "f(a)[2] and m[1][3]", "Regs{0} stays"):
        assert tidy(text) == text
    assert tidy("can return [0, -2]; buf[1] too") == "can return 0, -2; buf[1] too"
