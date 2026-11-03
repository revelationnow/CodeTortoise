"""Walk-throughs (spec 2026-11-02 §4, §18.2–§18.4): the demo's four, step by step."""
from codetortoise.design import WalkStep
from codetortoise.gates import build_gates
from codetortoise.walks import build_walks, fold


def _walks(demo, **kw):
    _, branches = build_gates(demo.x, demo.ss, demo.r, demo.src, demo.lines)
    return build_walks(demo.x, demo.ss, demo.det, demo.r, demo.per, demo.src, branches, demo.lines, **kw)


def _rows(x, w):
    return [(s.kind, x.label(s.src), x.label(s.dst), s.label, s.status, s.ref, s.story, s.flow, s.flow_n) for s in w.steps]


def test_the_demo_has_four_walk_throughs_listed_by_condition_then_causes(demo):
    assert [(w.id, w.title, w.thread, w.connection, w.condition, w.case, w.stories) for w in _walks(demo)] == [
        ("W1", "When `len > 64`", "T1", ("T1", "T2"), "G1", True, ["S1"]),
        ("W2", "When `len > 64` is false", "T1", None, "G1", False, ["S1", "S2"]),
        ("W3", "From `main` through `hal_write`", "T1", None, None, None, ["S2"]),
        ("W4", "From `main` through `logger_init`", "T2", None, None, None, ["S5", "S3"])]


def test_w1_takes_the_new_branch_returns_minus_2_to_logger_flush_and_reaches_the_reader(demo):
    x, w = demo.x, _walks(demo)[0]
    assert _rows(x, w) == [
        ("call", "main", "logger_flush", "logger_flush(&g_log)", "same", "path", "S1", "FL1", 1),
        ("call", "logger_flush", "uart_send", 'uart_send(lg->uart, "\\n", 1)', "same", "path", "S1", "FL1", 1),
        ("self", "uart_send", "uart_send", "len > 64", "new", "change", "S1", None, None),
        ("write", "uart_send", "Uart::errors", "*err += 1", "new", "change", "S1", None, None),
        ("return", "uart_send", "logger_flush", "-2", "new", "flow", "S1", "FL1", 1),
        ("return", "logger_flush", "main", "", "same", "code", None, None, None),
        ("call", "main", "uart_errors", "uart_errors(&g_uart)", "same", "code", None, None, None),
        ("read", "Uart::errors", "uart_errors", "u->errors", "same", "flow", "S1", "FL3", 2),
        ("return", "uart_errors", "main", "u->errors", "same", "code", None, None, None)]
    cause = {k.key: k.cause for k in demo.r.checks}
    assert (w.steps[4].keys, w.steps[4].cause) == (["result|service/logger.c|logger_flush|uart_send"],
                                                   cause["result|service/logger.c|logger_flush|uart_send"])
    assert (w.steps[7].keys, w.steps[7].cause) == (["reader|driver/uart.c|uart_errors|uart_send"],
                                                   cause["reader|driver/uart.c|uart_errors|uart_send"])
    assert [x.label(n) for n in w.parts] == ["main", "logger_flush", "uart_send", "uart_errors"]
    assert (w.steps[2].path, w.steps[2].line, w.steps[2].cl) == ("driver/uart.c", 16, 101)


def test_w2_is_the_false_side_through_the_loop_into_hal_write(demo):
    x, w = demo.x, _walks(demo)[1]
    assert [r[:7] for r in _rows(x, w)] == [
        ("call", "main", "logger_flush", "logger_flush(&g_log)", "same", "path", "S1"),
        ("call", "logger_flush", "uart_send", 'uart_send(lg->uart, "\\n", 1)', "same", "path", "S1"),
        ("self", "uart_send", "uart_send", "!(len > 64)", "new", "change", "S1"),
        ("call", "uart_send", "hal_write", "hal_write(u->regs, REG_STATUS, buf[i])", "same", "code", None),
        ("self", "hal_write", "hal_write", "int hal_write(struct Regs *r, unsigned reg, int value)", "changed", "change",
         "S2"),
        ("return", "hal_write", "uart_send", "0", "same", "code", None),
        ("write", "uart_send", "Stats::tx", "st->tx++", "new", "change", "S1"),
        ("return", "uart_send", "logger_flush", "0", "same", "code", None),
        ("return", "logger_flush", "main", "", "same", "code", None)]
    assert [s.loop for s in w.steps] == [None, None, None] + ["for (i = 0; i < len; i++)"] * 4 + [None, None]


def test_w3_follows_the_signature_change_to_the_caller_that_was_not_updated(demo):
    x, w = demo.x, _walks(demo)[2]
    assert _rows(x, w) == [
        ("call", "main", "uart_init", "uart_init(&g_uart, &g_regs, 115200)", "same", "path", "S2", "FL2", 1),
        ("call", "uart_init", "hal_write", "hal_write(regs, REG_CTRL, baud)", "same", "flow", "S2", "FL2", 1),
        ("self", "hal_write", "hal_write", "int hal_write(struct Regs *r, unsigned reg, int value)", "changed", "change",
         "S2", None, None),
        ("return", "hal_write", "uart_init", "0", "same", "code", None, None, None),
        ("return", "uart_init", "main", "hal_write(regs, REG_CTRL, baud)", "same", "code", None, None, None)]
    assert w.steps[1].keys == ["caller|driver/uart.c|uart_init|hal_write"]


def test_w4_writes_the_level_and_the_new_reader_in_another_story_reads_it(demo):
    x, w = demo.x, _walks(demo)[3]
    assert _rows(x, w) == [
        ("call", "main", "logger_init", "logger_init(&g_log, &g_uart)", "same", "path", "S5", None, None),
        ("write", "logger_init", "Logger::level", "lg->level = 2", "new", "change", "S5", None, None),
        ("return", "logger_init", "main", "0", "same", "code", None, None, None),
        ("read", "Logger::level", "logger_level", "lg->level", "new", "change", "S3", None, None)]
    assert [x.label(n) for n in w.parts] == ["main", "logger_init", "logger_level"]


def test_every_steps_story_flow_and_keys_exist_and_max_walks_holds(demo):
    keys = {k.key: k for k in demo.r.checks}
    stories = {s.id for s in demo.ss.stories}
    flows = {f.id for s in demo.ss.stories for f in demo.det[s.id].board.flows if f.id in s.flows}
    for w in _walks(demo):
        for s in w.steps:
            assert s.story is None or s.story in stories
            assert s.flow is None or s.flow in flows
            assert all(k in keys for k in s.keys)
            assert s.cause is None or s.cause in {keys[k].cause for k in s.keys}
    assert [w.id for w in _walks(demo, max_walks=2)] == ["W1", "W2"]


def test_unchanged_calls_more_than_walk_depth_from_the_change_fold_into_one_step():
    def call(a, b, ref="path"):
        return WalkStep(kind="call", src=a, dst=b, label=f"{b}()", status="same", ref=ref)
    steps = [call("N1", "N2"), call("N2", "N3"), call("N3", "N4"), call("N4", "N5"), call("N5", "N6"),
             WalkStep(kind="self", src="N6", dst="N6", label="x > 1", status="new", ref="change")]
    assert [(s.kind, s.src, s.dst, s.label, s.folded) for s in fold(steps, {"N6"}, 2)] == [
        ("fold", "N1", "N4", "… 3 calls", 3), ("call", "N4", "N5", "N5()", 0), ("call", "N5", "N6", "N6()", 0),
        ("self", "N6", "N6", "x > 1", 0)]
    assert len(fold(steps, {"N6"}, 4)) == 6                      # one far call alone never folds
    flowed = [call("N1", "N2", "flow")] + steps[1:]
    assert [s.kind for s in fold(flowed, {"N6"}, 2)] == ["call", "call", "call", "call", "call", "self"]


def _sides(fns, calls, lines, of, shape=None):
    """Each side's walk-through of function `of` in a small world, before any ranking: (kind, from, to, line) a step.
    `lines` puts each call, in `calls` order, on its line of the after text; `shape` reshapes the world first."""
    from test_stories import _world

    from codetortoise.board import analyse
    from codetortoise.gates import Sources
    from codetortoise.reading import build_reading
    from codetortoise.stories import build_stories
    from codetortoise.walks import _Walker
    c = _world(fns, calls=calls)
    for i, ln in enumerate(lines):
        c.after[0].calls[i].line = ln
    c = shape(c) if shape is not None else c
    an = analyse(c)
    ss, det = build_stories(c, analysis=an)
    r, per = build_reading(ss, c, details=det, analysis=an)
    x, src = an.x, Sources(an.x)
    _, branches = build_gates(x, ss, r, src)
    w = _Walker(x, ss, det, r, per, src, branches, None, 2)
    F = next(n for n in x.changed if x.label(n) == of)
    sid = next(s.id for s in ss.stories if F in s.nodes)
    gate = w.gate_of.get(F)
    return {case: [(s.kind, x.label(s.src), x.label(s.dst), s.line) for s in w.walk(sid, F, gate, case).walk.steps]
            for case in ((True, False) if gate is not None else (None,))}


def _changed(name, rel="drv/c.c"):
    return (name, rel, ["y = 1;"], ["y = 2;"])


MAIN = ("main", "app/m.c", ["send();"], ["send();"])


def test_a_void_function_s_early_guard_return_does_not_end_its_walk_through():
    flush = ("flush", "drv/f.c", ["if (!u)", "\treturn;", "a();"], ["if (!u)", "\treturn;", "a();", "b();", "c();"])
    sides = _sides([flush, ("a", "drv/f.c", ["x = 1;"], ["x = 1;"]), _changed("b"), _changed("c"),
                    ("main", "app/m.c", ["flush();"], ["flush();"])],
                   [("flush", "a"), ("flush", "b"), ("flush", "c"), ("main", "flush")], [5, 6, 7, 3], "flush")
    assert sides == {None: [("call", "main", "flush", 3), ("call", "flush", "b", 6), ("return", "b", "flush", None),
                            ("call", "flush", "c", 7), ("return", "c", "flush", None), ("return", "flush", "main", None)]}


def test_a_new_condition_after_an_early_guard_return_still_splits_the_walk_through():
    send = ("send", "drv/s.c", ["if (!u)", "\treturn;", "go();"],
            ["if (!u)", "\treturn;", "if (len > 64) {", "\tdrop();", "\treturn;", "}", "go();"])
    sides = _sides([send, _changed("go"), _changed("drop"), MAIN], [("send", "go"), ("send", "drop"), ("main", "send")],
                   [9, 6, 3], "send")
    assert sides[True] == [("call", "main", "send", 3), ("self", "send", "send", 5), ("call", "send", "drop", 6),
                           ("return", "drop", "send", None), ("return", "send", "main", 7)]
    assert sides[False] == [("call", "main", "send", 3), ("self", "send", "send", 5), ("call", "send", "go", 9),
                            ("return", "go", "send", None), ("return", "send", "main", None)]


def test_a_walk_through_in_a_tree_sitter_file_takes_the_calls_it_knows_by_name():
    """Final review, carried: tree-sitter names a call's callee only by name; found as the impact model finds it, a
    walk-through of a file tree-sitter parsed takes the steps a clang parse gives."""
    from test_stories import _by_name
    send = ("send", "drv/s.c", ["if (!u)", "\treturn;", "go();"],
            ["if (!u)", "\treturn;", "if (len > 64) {", "\tdrop();", "\treturn;", "}", "go();"])
    world = ([send, _changed("go"), _changed("drop"), MAIN], [("send", "go"), ("send", "drop"), ("main", "send")],
             [9, 6, 3], "send")
    clang = _sides(*world)
    assert ("call", "send", "drop", 6) in clang[True]
    assert _sides(*world, shape=lambda c: _by_name(c, {"send", "go", "drop", "main"})) == clang


def test_a_new_block_with_no_return_runs_on_to_the_function_s_end_on_both_sides():
    send = ("send", "drv/s.c", ["if (!u)", "\treturn;", "go();"],
            ["if (!u)", "\treturn;", "if (len > 64) {", "\tdrop();", "}", "go();"])
    sides = _sides([send, _changed("go"), _changed("drop"), MAIN], [("send", "go"), ("send", "drop"), ("main", "send")],
                   [8, 6, 3], "send")
    assert sides[True] == [("call", "main", "send", 3), ("self", "send", "send", 5), ("call", "send", "drop", 6),
                           ("return", "drop", "send", None), ("call", "send", "go", 8), ("return", "go", "send", None),
                           ("return", "send", "main", None)]
    assert sides[False] == [("call", "main", "send", 3), ("self", "send", "send", 5), ("call", "send", "go", 8),
                            ("return", "go", "send", None), ("return", "send", "main", None)]


def test_fixed_titles_that_repeat_name_their_function():
    from codetortoise.design import Walk
    from codetortoise.walks import _Cand, _keep

    def cand(title, gate, fn, path, story):
        w = Walk(id="", title=title, condition=gate, case=True if gate else None, parts=[], stories=[story], steps=[])
        return _Cand(w, {"c1"}, {story}, gate or f"{story}:{fn}", 0, fn, path)
    walks = _keep([cand("When `ret < 0`", "G1", "f", "drv/a.c", "S1"), cand("When `ret < 0`", "G2", "g", "drv/b.c", "S2"),
                   cand("When `ret < 0`", "G3", "g", "drv/c.c", "S3"), cand("In `h`", None, "h", "drv/d.c", "S4"),
                   cand("In `h`", None, "h", "drv/e.c", "S5"), cand("When `n == 0`", "G4", "k", "drv/k.c", "S6")], 10)
    assert [w.title for w in walks] == [
        "When `ret < 0` in `f`", "When `ret < 0` in `g` (drv/b.c)", "When `ret < 0` in `g` (drv/c.c)", "When `n == 0`",
        "In `h` (drv/d.c)", "In `h` (drv/e.c)"]


def test_the_true_side_of_an_else_if_runs_no_other_arm_of_its_chain():
    pick = ("pick", "drv/p.c", ["if (ready(m)) {", "\ta();", "} else {", "\tc();", "}"],
            ["if (ready(m)) {", "\ta();", "} else if (m == 2) {", "\tb();", "} else {", "\tc();", "}"])
    calls = [("pick", "ready"), ("pick", "a"), ("pick", "b"), ("pick", "c"), ("main", "pick")]
    sides = _sides([pick, _changed("ready"), _changed("a"), _changed("b"), _changed("c"),
                    ("main", "app/m.c", ["pick();"], ["pick();"])], calls, [3, 4, 6, 8, 3], "pick")
    assert [s for s in sides[True] if s[0] == "call"] == [            # the first arm's test runs, its body doesn't
        ("call", "main", "pick", 3), ("call", "pick", "ready", 3), ("call", "pick", "b", 6)]


def test_a_condition_inside_an_else_block_runs_no_arm_of_the_if_around_it():
    """Final review, carried: an if inside a plain else { } block: neither side of it runs the arm before the else,
    though the outer test runs on both."""
    pick = ("pick", "drv/p.c", ["if (ready(m)) {", "\ta();", "} else {", "\tc();", "}"],
            ["if (ready(m)) {", "\ta();", "} else {", "\tif (m == 2) {", "\t\tb();", "\t}", "\tc();", "}"])
    calls = [("pick", "ready"), ("pick", "a"), ("pick", "b"), ("pick", "c"), ("main", "pick")]
    sides = _sides([pick, _changed("ready"), _changed("a"), _changed("b"), _changed("c"),
                    ("main", "app/m.c", ["pick();"], ["pick();"])], calls, [3, 4, 7, 9, 3], "pick")
    assert [s for s in sides[True] if s[0] == "call"] == [
        ("call", "main", "pick", 3), ("call", "pick", "ready", 3), ("call", "pick", "b", 7), ("call", "pick", "c", 9)]
    assert [s for s in sides[False] if s[0] == "call"] == [
        ("call", "main", "pick", 3), ("call", "pick", "ready", 3), ("call", "pick", "c", 9)]


def test_the_false_side_of_an_else_if_runs_no_earlier_arm():
    """Final review, carried: an else-if's false side runs the tests before it, not their arms."""
    pick = ("pick", "drv/p.c", ["if (ready(m)) {", "\ta();", "} else {", "\tc();", "}"],
            ["if (ready(m)) {", "\ta();", "} else if (m == 2) {", "\tb();", "} else {", "\tc();", "}"])
    calls = [("pick", "ready"), ("pick", "a"), ("pick", "b"), ("pick", "c"), ("main", "pick")]
    sides = _sides([pick, _changed("ready"), _changed("a"), _changed("b"), _changed("c"),
                    ("main", "app/m.c", ["pick();"], ["pick();"])], calls, [3, 4, 6, 8, 3], "pick")
    assert [s for s in sides[False] if s[0] == "call"] == [
        ("call", "main", "pick", 3), ("call", "pick", "ready", 3), ("call", "pick", "c", 8)]


def test_nested_conditions_run_only_the_arms_on_their_path():
    """A condition in a loop in an else-if's arm: each side runs the tests on its path and the loop's own calls, and no
    other arm of either if around it."""
    def scan(inner):
        return ["if (idle(m)) {", "\ta();", "} else if (busy(m)) {", "\tfor (i = 0; i < n; i++) {", "\t\tstep();",
                *inner, "\t}", "} else {", "\tc();", "}", "d();"]
    calls = [("scan", "idle"), ("scan", "a"), ("scan", "busy"), ("scan", "step"), ("scan", "b"), ("scan", "c"),
             ("scan", "d"), ("main", "scan")]
    sides = _sides([("scan", "drv/s.c", scan([]), scan(["\t\tif (i == 2) {", "\t\t\tb();", "\t\t}"])),
                    *(_changed(n) for n in ("idle", "a", "busy", "step", "b", "c", "d")),
                    ("main", "app/m.c", ["scan();"], ["scan();"])], calls, [3, 4, 5, 7, 9, 13, 15, 3], "scan")
    path = [("call", "main", "scan", 3), ("call", "scan", "idle", 3), ("call", "scan", "busy", 5),
            ("call", "scan", "step", 7)]
    assert [s for s in sides[True] if s[0] == "call"] == [*path, ("call", "scan", "b", 9), ("call", "scan", "d", 15)]
    assert [s for s in sides[False] if s[0] == "call"] == [*path, ("call", "scan", "d", 15)]


def test_a_later_else_if_on_the_closing_brace_s_line_runs_on_neither_side():
    """Final review M4: in K&R layout the then arm's closing brace shares its line with `} else if (busy(m)) {`; a
    condition in the then arm runs neither that test nor its arm."""
    pick = ("pick", "drv/p.c", ["if (idle(m)) {", "\ta();", "} else if (busy(m)) {", "\tc();", "}"],
            ["if (idle(m)) {", "\ta();", "\tif (m == 2) {", "\t\tb();", "\t}", "} else if (busy(m)) {", "\tc();",
             "}"])
    calls = [("pick", "idle"), ("pick", "a"), ("pick", "b"), ("pick", "busy"), ("pick", "c"), ("main", "pick")]
    sides = _sides([pick, _changed("idle"), _changed("a"), _changed("b"), _changed("busy"), _changed("c"),
                    ("main", "app/m.c", ["pick();"], ["pick();"])], calls, [3, 4, 6, 8, 9, 3], "pick")
    path = [("call", "main", "pick", 3), ("call", "pick", "idle", 3), ("call", "pick", "a", 4)]
    assert [s for s in sides[True] if s[0] == "call"] == [*path, ("call", "pick", "b", 6)]
    assert [s for s in sides[False] if s[0] == "call"] == path

def test_the_true_side_of_a_case_runs_the_arms_after_it_only_when_it_falls_through():
    def on(after):
        return ("on", "drv/s.c", ["switch (m) {", "case 1:", "\ta();", "\tbreak;", "case 3:", "\tc();", "\tbreak;", "}"],
                ["switch (m) {", "case 1:", "\ta();", "\tbreak;", *after, "case 3:", "\tc();", "\tbreak;", "}"])
    rest = [_changed("a"), _changed("b"), _changed("c"), ("main", "app/m.c", ["on();"], ["on();"])]
    calls = [("on", "a"), ("on", "b"), ("on", "c"), ("main", "on")]
    breaks = _sides([on(["case 2:", "\tb();", "\tbreak;"]), *rest], calls, [5, 8, 11, 3], "on")
    assert [s for s in breaks[True] if s[0] == "call"] == [("call", "main", "on", 3), ("call", "on", "b", 8)]
    falls = _sides([on(["case 2:", "\tb();"]), *rest], calls, [5, 8, 10, 3], "on")
    assert [s for s in falls[True] if s[0] == "call"] == [
        ("call", "main", "on", 3), ("call", "on", "b", 8), ("call", "on", "c", 10)]


def test_the_true_side_of_a_case_under_an_ifdef_runs_no_other_arm_of_its_switch():
    """Final review minor 4: a case the preprocessor wraps sits in the #ifdef, not in the switch's body; its switch is
    still the one around it."""
    on = ("on", "drv/s.c", ["switch (m) {", "case 1:", "\ta();", "\tbreak;", "case 3:", "\tc();", "\tbreak;", "}"],
          ["switch (m) {", "case 1:", "\ta();", "\tbreak;", "#ifdef FAST", "case 2:", "\tb();", "\tbreak;", "#endif",
           "case 3:", "\tc();", "\tbreak;", "}"])
    rest = [_changed("a"), _changed("b"), _changed("c"), ("main", "app/m.c", ["on();"], ["on();"])]
    sides = _sides([on, *rest], [("on", "a"), ("on", "b"), ("on", "c"), ("main", "on")], [5, 9, 12, 3], "on")
    assert [s for s in sides[True] if s[0] == "call"] == [("call", "main", "on", 3), ("call", "on", "b", 9)]


def test_a_block_that_jumps_away_skips_the_lines_up_to_where_it_lands():
    goto = ("send", "drv/s.c", ["go();", "done();"], ["if (len > 64)", "\tgoto out;", "go();", "out:", "done();"])
    sides = _sides([goto, _changed("go"), _changed("done"), MAIN], [("send", "go"), ("send", "done"), ("main", "send")],
                   [5, 7, 3], "send")
    assert sides[True] == [("call", "main", "send", 3), ("self", "send", "send", 3), ("call", "send", "done", 7),
                           ("return", "done", "send", None), ("return", "send", "main", None)]
    assert sides[False] == [("call", "main", "send", 3), ("self", "send", "send", 3), ("call", "send", "go", 5),
                            ("return", "go", "send", None), ("call", "send", "done", 7), ("return", "done", "send", None),
                            ("return", "send", "main", None)]
    loop = ("send", "drv/s.c", ["for (i = 0; i < n; i++) {", "\tgo();", "}", "done();"],
            ["for (i = 0; i < n; i++) {", "\tif (len > 64)", "\t\tcontinue;", "\tgo();", "}", "done();"])
    sides = _sides([loop, _changed("go"), _changed("done"), MAIN], [("send", "go"), ("send", "done"), ("main", "send")],
                   [6, 8, 3], "send")
    assert sides[True] == [("call", "main", "send", 3), ("self", "send", "send", 4), ("call", "send", "done", 8),
                           ("return", "done", "send", None), ("return", "send", "main", None)]


def test_a_walk_through_over_its_cap_folds_its_middle_and_keeps_its_condition_its_flows_and_its_way_back():
    from codetortoise.walks import shrink

    def st(kind, a, b, ref="code", status="same"):
        return WalkStep(kind=kind, src=a, dst=b, label="", status=status, ref=ref)
    middle = [s for k in range(4, 34) for s in (st("call", "N3", f"N{k}", "change", "new"), st("return", f"N{k}", "N3"))]
    steps = [st("call", "N1", "N2", "path"), st("call", "N2", "N3", "path"), st("self", "N3", "N3", "change", "new"),
             *middle, st("return", "N3", "N2", "flow", "new"), st("call", "N2", "N9"), st("read", "N8", "N9", "flow"),
             st("return", "N9", "N2"), st("return", "N2", "N1")]
    out = shrink(steps, 40, "N3")
    assert len(steps) == 68 and len(out) == 40
    assert out[:34] == steps[:34] and out[35:] == steps[63:]
    assert (out[34].kind, out[34].src, out[34].dst, out[34].label, out[34].folded, out[34].status) == (
        "fold", "N19", "N3", "… 29 steps", 29, "changed")
    assert shrink(steps, 80, "N3") == steps
    reads = [st("read", "N8", f"N{k}", "flow") for k in range(10, 60)]          # nothing to fold: the end is counted
    out = shrink(reads, 40, "N3")
    assert len(out) == 40 and out[:39] == reads[:39]
    assert (out[39].kind, out[39].src, out[39].dst, out[39].label, out[39].folded) == ("fold", "N8", "N59", "… 11 more steps", 11)


def test_a_function_with_many_changed_calls_shrinks_to_the_cap_and_still_returns_to_its_caller():
    from codetortoise.walks import MAX_STEPS
    big = ("big", "drv/b.c", ["x = 0;"], ["x = 0;", *(f"c{k}();" for k in range(1, 26))])
    sides = _sides([big, *(_changed(f"c{k}") for k in range(1, 26)), ("main", "app/m.c", ["big();"], ["big();"])],
                   [*(("big", f"c{k}") for k in range(1, 26)), ("main", "big")], [*range(4, 29), 3], "big")
    steps = sides[None]
    assert len(steps) == MAX_STEPS == 40
    assert steps[:3] == [("call", "main", "big", 3), ("call", "big", "c1", 4), ("return", "c1", "big", None)]
    assert [s[0] for s in steps].count("fold") == 1 and steps[38][0] == "fold"
    assert steps[-1] == ("return", "big", "main", None)
