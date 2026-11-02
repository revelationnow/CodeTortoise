"""Walk-throughs (spec 2026-11-02 §4, §18.2–§18.4): the demo's four, step by step."""
from codetortoise.design import WalkStep
from codetortoise.gates import build_gates
from codetortoise.walks import build_walks, fold


def _walks(demo, **kw):
    _, branches = build_gates(demo.x, demo.ss, demo.r, demo.per, demo.src, demo.lines)
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
