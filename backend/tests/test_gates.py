"""The conditions a change adds and the lines that still run when one is false (spec 2026-11-02 §7)."""
from test_stories import _world

from codetortoise.board import _Ctx
from codetortoise.gates import Sources, build_gates, classify, find_gates, line_marks, trivial


def _found(c):
    x = _Ctx(c)
    return x, find_gates(x, Sources(x), {}, [])


def _gate(b):
    return (b.kind, b.test, b.line, sorted(b.body))


def test_line_marks_tell_new_lines_from_changed_ones_and_skip_whitespace_edits():
    before = "x = 1;\nif (len > 32) {\n\tsend();\n}\n"
    after = "x  =  1;\nif (len > 64) {\n\tsend();\n}\ndone();\n"
    assert line_marks(before, after) == {2: "changed", 5: "new"}


def test_a_line_of_braces_or_a_comment_says_nothing_alone():
    assert all(trivial(t) for t in ["}", "\t{", "  );", "", "// note", " * more", "/* x */"])
    assert not any(trivial(t) for t in ["\t} else {", "break;", "x++;", "\t*err += 1;", "*(p + 1) = 0;"])


def test_a_new_if_with_an_early_return_outranks_a_changed_condition():
    c = _world([("check", "drv/u.c", ["if (len > 32) {", "\tgo();", "}"], ["if (len > 64) {", "\tgo();", "}"]),
                ("send", "drv/u.c", ["x = 1;", "go();"],
                 ["x = 1;", "if (len > 64) {", "\terr++;", "\treturn -2;", "}", "go();"]),
                ("go", "drv/u.c", ["y = 1;"], ["y = 1;"])])
    x, found = _found(c)
    assert [(x.label(b.node), b.kind, b.test, b.strength) for b in found] == [
        ("send", "if", "len > 64", 2), ("check", "changed", "len > 64", 0)]
    send = found[0]
    assert (send.line, send.first, send.last, sorted(send.body), sorted(send.own), send.returns) == (
        10, 10, 13, [11, 12], [10, 13], [12])


def test_a_new_else_if_is_a_condition_of_its_own_and_a_plain_else_its_other_side():
    c = _world([("pick", "drv/p.c", ["if (m == 1) {", "\ta();", "} else {", "\tc();", "}"],
                 ["if (m == 1) {", "\ta();", "} else if (m == 2) {", "\tb();", "} else {", "\tc();", "}"])])
    x, found = _found(c)
    assert [_gate(b) for b in found] == [("else if", "m == 2", 5, [6])]
    assert found[0].alt == (7, 9)


def test_a_new_case_is_a_condition_on_the_switch_subject():
    c = _world([("on", "drv/s.c", ["switch (m) {", "case 1:", "\ta();", "\tbreak;", "}"],
                 ["switch (m) {", "case 1:", "\ta();", "\tbreak;", "case 2:", "\tb();", "\tbreak;", "}"])])
    x, found = _found(c)
    assert [_gate(b) for b in found] == [("case", "m == 2", 7, [8, 9])]


def test_a_new_return_under_an_existing_condition_makes_it_one():
    c = _world([("use", "drv/r.c", ["if (!p) {", "\tlog();", "}", "go(p);"],
                 ["if (!p) {", "\tlog();", "\treturn;", "}", "go(p);"])])
    x, found = _found(c)
    assert [(b.kind, b.test, b.line, b.returns) for b in found] == [("return", "!p", 3, [5])]


def test_a_cpp_file_reads_its_condition_from_the_condition_clause():
    c = _world([("send", "drv/u.cpp", ["go();"], ["if (len > 64) {", "\treturn;", "}", "go();"])])
    x, found = _found(c)
    assert [(b.kind, b.test) for b in found] == [("if", "len > 64")]


def test_a_condition_tangled_in_an_ifdef_is_found_on_the_branch_the_parse_keeps():
    c = _world([("send", "drv/t.c", ["go();"],
                 ["#ifdef FAST", "if (n > 1) {", "#else", "if (n > 2) {", "#endif", "\tgo();", "}"])])
    x, found = _found(c)
    assert [(b.test, b.line, sorted(b.body)) for b in found] == [("n > 1", 4, [8])]


def test_lines_count_a_lone_carriage_return_as_clang_does():
    c = _world([("send", "drv/cr.c", ["x = 1; // a\r// b", "go();"],
                 ["x = 1; // a\r// b", "if (len > 64) {", "\treturn;", "}", "go();"])])
    x, found = _found(c)
    assert [(b.test, b.line, sorted(b.body)) for b in found] == [("len > 64", 5, [6])]


def test_an_added_function_has_no_condition_to_meet():
    c = _world([("fresh", "drv/n.c", None, ["if (x) {", "\treturn;", "}"])])
    assert _found(c)[1] == []


def test_a_function_called_only_under_the_condition_stops_with_it_and_one_called_elsewhere_runs():
    c = _world([("send", "drv/u.c", ["both();"], ["if (len > 64) {", "\tonly();", "\treturn -2;", "}", "both();"]),
                ("only", "drv/u.c", ["a = 1;"], ["a = 2;"]),
                ("both", "drv/u.c", ["b = 1;"], ["b = 2;"]),
                ("other", "drv/u.c", ["both();"], ["both();"])],
               calls=[("send", "only"), ("send", "both"), ("other", "both")])
    c.after[0].calls[0].line, c.after[0].calls[1].line = 4, 7          # inside the new block, and after it
    x, found = _found(c)
    lines, runs, stops = classify(found[0], x, Sources(x), {}, {}, [])
    assert [(g.where, g.function, g.line, g.runs) for g in lines] == [
        ("under", "send", 4, False), ("under", "send", 5, False), ("elsewhere", "only", 11, False),
        ("elsewhere", "both", 15, True)]
    assert (runs, stops) == (1, 3)


def test_the_demo_has_one_condition_and_its_false_case_still_runs_the_other_changes(demo):
    gates, branches = build_gates(demo.x, demo.ss, demo.r, demo.per, demo.src, demo.lines)
    assert [(g.id, demo.x.label(g.node), g.test, g.story, g.path, g.line, g.guarded) for g in gates] == [
        ("G1", "uart_send", "len > 64", "S1", "driver/uart.c", 16, [16, 19])]
    assert [b.id for b in branches] == ["G1"]
    g = gates[0]
    assert [(k.path, k.line) for k in g.lines if k.where == "under"] == [("driver/uart.c", 17), ("driver/uart.c", 18)]
    assert [(k.line, k.runs) for k in g.lines if k.where == "outside"] == [(14, True), (15, True), (20, True), (22, True)]
    elsewhere = {(k.path, k.line): k.runs for k in g.lines if k.where == "elsewhere"}
    assert {("hal/regs.c", 10), ("service/logger.c", 7), ("cpp/engine.cpp", 21)} <= set(elsewhere)
    assert all(elsewhere.values())
    tx = next(k for k in g.lines if (k.path, k.line) == ("driver/uart.c", 22))
    assert (tx.story, tx.cl, tx.text, tx.function) == ("S1", 101, "st->tx++;", "uart_send")
    assert (g.stops, g.runs) == (2, len(g.lines) - 2)


def test_a_condition_changed_only_on_a_continuation_line_is_a_changed_condition():
    c = _world([("check", "drv/u.c", ["if (p == NULL ||", "    len == 0) {", "\treturn -1;", "}", "go();"],
                 ["if (p == NULL ||", "    len == 0 ||", "    len > 64) {", "\treturn -1;", "}", "go();"])])
    assert [_gate(b) for b in _found(c)[1]] == [("changed", "p == NULL || len == 0 || len > 64", 3, [6])]
    c = _world([("check", "drv/u.c", ["if (p == NULL ||", "    len > 32) {", "\treturn -1;", "}"],
                 ["if (p == NULL ||", "    len > 64) {", "\treturn -1;", "}"])])
    assert [_gate(b) for b in _found(c)[1]] == [("changed", "p == NULL || len > 64", 3, [5])]
