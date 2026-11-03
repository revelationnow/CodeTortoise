"""The conditions a change adds and the lines that still run when one is false (spec 2026-11-02 §7)."""
from test_stories import _by_name, _world

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


def test_a_comment_followed_by_code_is_code():
    for code in ("/* why */ x = 1;", "*/ x();", "/* a */ /* b */ f();", "} /* end */ else {", "x = 1; // note"):
        assert not trivial(code), code
    for said in ("/* a */ /* b */", "} /* end */", "*/", "  * more", "/* starts", "// note"):
        assert trivial(said), said


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
    assert (found[0].chain, found[0].tried) == ((3, 9), {3})        # the first arm's test runs before it


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
    lines, runs, stops = classify(found[0], x, Sources(x), {}, [])
    assert [(g.where, g.function, g.line, g.runs) for g in lines] == [
        ("under", "send", 4, False), ("under", "send", 5, False), ("elsewhere", "only", 11, False),
        ("elsewhere", "both", 15, True)]
    assert (runs, stops) == (1, 3)


def test_a_function_also_called_from_a_file_not_parsed_still_runs():
    from test_stories import W

    from codetortoise.impact import Edge, Node
    c = _world([("send", "drv/u.c", ["go();"], ["if (len > 64) {", "\tonly();", "\treturn -2;", "}", "go();"]),
                ("only", "drv/u.c", ["a = 1;"], ["a = 2;"])], calls=[("send", "only")])
    c.after[0].calls[0].line = 4
    c.impact.nodes["N9"] = Node(id="N9", key="c:@F@remote", label="remote", file=f"{W}/far/r.c", line=1, layer=1)
    c.impact.edges.append(Edge(id="E9", src="N9", dst="N2", kind="call", confidence="heuristic", file=f"{W}/far/r.c",
                               line=3))                            # a caller found by name in a file not parsed
    x, found = _found(c)
    lines, runs, stops = classify(found[0], x, Sources(x), {}, [])
    assert [(g.where, g.function, g.runs) for g in lines if g.where == "elsewhere"] == [("elsewhere", "only", True)]


def test_a_file_with_a_guard_and_an_unrelated_parse_error_keeps_its_else_branches():
    c = _world([("send", "drv/u.c", ["go();"], ["go();"])])
    c.cs.files[0].after = ("#ifndef U_H\n#define U_H\nint broken = ;\nint fine = 1;\nvoid send(void)\n{\n#ifdef FAST\n"
                           "\tgo();\n#else\n\tif (len > 64)\n\t\treturn;\n#endif\n}\n#endif\n")
    tree, src, _ = Sources(_Ctx(c)).tree(c.cs.files[0].local)
    assert tree.root_node.has_error and b"if (len > 64)" in src


def test_the_fold_leaves_out_test_files_preprocessor_lines_and_lines_in_no_function():
    c = _world([("send", "drv/u.c", ["both();"],
                 ["if (len > 64) {", "\treturn -2;", "}", "#ifdef TRACE", "trace(len);", "#endif", "both();"]),
                ("both", "drv/u.c", ["b = 1;"], ["b = 1;"]),
                ("check_send", "tests/test_u.c", ["send();"], ["send();", "x = 1;"])])
    c.cs.files[0].after += "int limit = 64;\n"                       # a global: in no function
    x, found = _found(c)
    lines, runs, stops = classify(found[0], x, Sources(x), {}, [])
    assert [(g.where, g.path, g.line, g.text) for g in lines] == [
        ("under", "drv/u.c", 4, "return -2;"), ("outside", "drv/u.c", 7, "trace(len);")]
    assert (runs, stops) == (1, 1)


def test_the_demo_has_one_condition_and_its_false_case_still_runs_the_other_changes(demo):
    gates, branches = build_gates(demo.x, demo.ss, demo.r, demo.src, demo.lines)
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


def test_a_condition_in_a_mechanical_or_tests_story_is_not_one(demo):
    for kind in ("mechanical", "tests"):
        ss = demo.ss.model_copy(deep=True)
        next(s for s in ss.stories if s.id == "S1").kind = kind
        gates, branches = build_gates(demo.x, ss, demo.r, demo.src, demo.lines)
        assert (gates, branches) == ([], []), kind


def test_a_condition_changed_only_on_a_continuation_line_is_a_changed_condition():
    c = _world([("check", "drv/u.c", ["if (p == NULL ||", "    len == 0) {", "\treturn -1;", "}", "go();"],
                 ["if (p == NULL ||", "    len == 0 ||", "    len > 64) {", "\treturn -1;", "}", "go();"])])
    assert [_gate(b) for b in _found(c)[1]] == [("changed", "p == NULL || len == 0 || len > 64", 3, [6])]
    c = _world([("check", "drv/u.c", ["if (p == NULL ||", "    len > 32) {", "\treturn -1;", "}"],
                 ["if (p == NULL ||", "    len > 64) {", "\treturn -1;", "}"])])
    assert [_gate(b) for b in _found(c)[1]] == [("changed", "p == NULL || len > 64", 3, [5])]


def test_a_condition_the_design_context_adds_leads_and_lists_its_lines(demo):
    from codetortoise.design_context import HandCondition, HandConditions
    notes: list[str] = []
    hand = HandConditions(add=[HandCondition(test="reg==REG_CTRL", function="hal_write")])
    gates, branches = build_gates(demo.x, demo.ss, demo.r, demo.src, demo.lines, hand=hand, notes=notes)
    assert [(g.id, demo.x.label(g.node), g.test, g.source, g.path) for g in gates] == [
        ("G1", "hal_write", "reg == REG_CTRL", "context", "hal/regs.c"),
        ("G2", "uart_send", "len > 64", "code", "driver/uart.c")]
    assert gates[0].lines and not gates[1].lines and notes == []
    assert [b.id for b in branches] == ["G1", "G2"]


def test_a_condition_the_design_context_leaves_out_is_gone_and_what_it_names_but_lacks_is_said(demo):
    from codetortoise.design_context import HandCondition, HandConditions
    notes: list[str] = []
    hand = HandConditions(add=[HandCondition(test="x == 1")], remove=["len>64", "y > 2"])
    gates, branches = build_gates(demo.x, demo.ss, demo.r, demo.src, demo.lines, hand=hand, notes=notes)
    assert gates == [] and branches == []
    assert notes == ["the condition `x == 1` is not in the changed functions",
                     "the condition `y > 2` to leave out is not among those the rules found"]


def test_the_design_context_s_components_replace_the_config_s_and_its_text_marks_the_design(demo):
    from codetortoise.config import ComponentRule
    from codetortoise.design import build_design
    from codetortoise.design_context import DesignContext, context_hash
    ctx = DesignContext(notes="The UART must never drop a byte.", components=[
        ComponentRule(name="Firmware", globs=["driver/*", "hal/*", "include/*"]),
        ComponentRule(name="Service", globs=["service/*"])])
    d = build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text, context=ctx)
    holder = {f: c.name for c in d.components for f in c.files}
    assert holder["driver/uart.c"] == holder["hal/regs.c"] == "Firmware" and holder["service/logger.c"] == "Service"
    assert d.context_hash == context_hash(ctx) and d.context_notes == []
    plain = build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    assert plain.context_hash is None and "Firmware" not in {c.name for c in plain.components}


def _guard_world(other_file="drv/u.c"):
    """send calls only() and shared() inside its new guard; other, in `other_file`, calls shared() too."""
    c = _world([("send", "drv/u.c", ["x = 1;"],
                 ["if (len > 64) {", "\tonly();", "\tshared();", "\treturn -2;", "}", "x = 1;"]),
                ("only", "drv/u.c", ["a = 1;"], ["a = 2;"]),
                ("shared", "drv/u.c", ["b = 1;"], ["b = 2;"]),
                ("other", other_file, ["shared();"], ["shared();"])],
               calls=[("send", "only"), ("send", "shared"), ("other", "shared")])
    c.after[0].calls[0].line, c.after[0].calls[1].line = 4, 5
    return c


def _elsewhere(c):
    x, found = _found(c)
    lines, _, _ = classify(found[0], x, Sources(x), {}, [])
    return {g.function: g.runs for g in lines if g.where == "elsewhere"}


def test_a_function_called_only_from_the_guarded_block_stops_in_a_tree_sitter_file():
    """Final review, carried: tree-sitter names a call's callee only by name, so in a file it parsed nothing was classed
    as stopping with a condition. Calls now find their function as the impact model's edges do: a tree-sitter file
    classes as a clang one, and so does a change parsed partly by each (a caller in the other parse's file still makes
    its callee run)."""
    want = {"only": False, "shared": True}
    assert _elsewhere(_guard_world()) == want
    assert _elsewhere(_by_name(_guard_world(), {"send", "only", "shared", "other"})) == want
    assert _elsewhere(_by_name(_guard_world("drv/v.c"), {"other"})) == want
