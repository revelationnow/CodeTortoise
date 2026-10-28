"""Checks grouped by cause (spec 2026-10-16-outline-and-causes §4)."""
import hashlib

import pytest
from test_reading import _caller_world, _checks, _f, _set, _x
from test_stories import _edit, _same, _world

from codetortoise.board import Flow
from codetortoise.causes import build_causes, cause_id, change_for
from codetortoise.reading import Reading, StoryReading, Thread, build_reading


def _readers(*readers, writer="config", field="errors"):
    fns = [_edit(writer, "drv/cfg.c"), *(_same(r, f"svc/{r}.c") for r in readers)]
    fields = [(writer, "Uart", field, "write", "added"), *((r, "Uart", field, "read", "unchanged") for r in readers)]
    return _world(fns, fields=fields)


def _causes(c, ss, flows_of=None, threads=None):
    threads = threads or [Thread(id="T1", name="t", purpose="", stories=[s.id for s in ss.stories])]
    rows, _ = _checks(c, ss, threads=threads)
    return rows, build_causes(rows, _x(c), threads, [s for t in threads for s in t.stories], flows_of or {})


def test_readers_of_one_field_written_by_one_function_are_one_cause_with_every_place():
    c = _readers("report", "dump")
    rows, causes = _causes(c, _set(["N1"]))
    (cause,) = causes
    assert cause.kind == "reader" and cause.story == "S1" and cause.thread == "T1"
    assert cause.text == "2 places read `Uart::errors`, which `config` now writes"
    assert cause.places == sorted(k.key for k in rows)
    assert all(k.cause == cause.id for k in rows)
    want = "c" + hashlib.sha1(b"reader|drv/cfg.c::config|Uart::errors").hexdigest()[:10]
    assert cause.id == want == cause_id("reader", "drv/cfg.c::config", "Uart::errors")


def test_one_place_keeps_its_own_text_and_another_field_is_another_cause():
    c = _world([_edit("config", "drv/cfg.c"), _same("report", "svc/rep.c"), _same("dump", "svc/dump.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("config", "Uart", "last", "write", "added"),
                       ("report", "Uart", "errors", "read", "unchanged"), ("dump", "Uart", "last", "read", "unchanged")])
    _, causes = _causes(c, _set(["N1"]))
    assert sorted(z.text for z in causes) == ["`dump` reads `Uart::last`, which `config` now writes",
                                              "`report` reads `Uart::errors`, which `config` now writes"]


def test_callers_of_one_changed_signature_and_results_by_new_values_group_apart():
    c, ss = _caller_world(returns=(["0"], ["0", "-2"]))
    next(e for e in c.after[0].calls if e.caller == "c:@F@flush").result_used = False
    _, causes = _causes(c, ss)
    assert [(z.kind, z.text) for z in causes] == [
        ("caller", "`flush` calls `send` and was not updated for its new signature"),
        ("result", "`flush` ignores the result of `send`, which can now return -2")]
    assert causes[0].id == cause_id("caller", "drv/uart.c::send", "")
    assert causes[1].id == cause_id("result", "drv/uart.c::send", "-2")


def test_each_finding_is_its_own_cause_and_its_id_survives_renumbering():
    c = _world([_edit("send", "drv/uart.c")])
    ss = _set(["N1"])
    ss.finding_story = {"F1": "S1", "F2": "S1"}
    c.findings = [_f("F1", verdict="hazard", reason="drops data", source="tier1", title="lock"),
                  _f("F2", verdict="needs_review", reason="check it", source="tier1", title="order")]
    _, first = _causes(c, ss)
    assert [(z.kind, z.finding, z.text) for z in first] == [("hazard", "F1", "drops data"), ("confirm", "F2", "check it")]
    c.findings[0].id, c.findings[1].id = "F2", "F1"
    ss.finding_story = {"F1": "S1", "F2": "S1"}
    _, again = _causes(c, ss)
    assert [z.id for z in again] == [z.id for z in first]


def test_untested_functions_of_a_story_are_one_cause():
    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _edit("recv", "drv/recv.c"),
                ("test_it", "tests/t.c", ["x;"], ["init_hw();"])])
    ss = _set(["N1", "N3"], ["N2"], ["N4"], kinds={"S3": "tests"})
    threads = [Thread(id="T1", name="t", purpose="", stories=["S1", "S2"])]
    rows, _ = _checks(c, ss, threads=threads, has_tests=True,
                      test_callers=lambda name: {"/w/tests/u.c"} if name == "init" else set())
    (cause,) = build_causes(rows, _x(c), threads, ["S1", "S2"], {})
    assert cause.text == "2 functions no test calls" and cause.id == cause_id("untested", "drv/recv.c::recv,drv/uart.c::send", "")
    assert cause.story == "S1" and len(cause.places) == 2


def test_a_cause_touches_the_flows_of_its_story_whose_path_holds_its_function_or_a_place():
    c = _readers("report")
    fl = Flow(id="FL1", path=["N2", "N1"], tag="state", lands="N1", severity="low", text="report → config", what="",
              effect="", check="")
    other = fl.model_copy(update={"id": "FL2", "path": ["N9"]})
    _, causes = _causes(c, _set(["N1"]), flows_of={"S1": [other, fl]})
    assert causes[0].flows == ["FL1"]


def test_causes_follow_thread_then_story_then_flow_then_kind_order():
    c = _world([_edit("config", "drv/cfg.c"), _edit("send", "drv/uart.c"), _same("report", "svc/rep.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged")])
    ss = _set(["N1"], ["N2"])
    ss.finding_story = {"F1": "S2"}
    c.findings = [_f("F1", nodes=("N2",), verdict="hazard", reason="drops data", source="tier1")]
    threads = [Thread(id="T1", name="b", purpose="", stories=["S2"]), Thread(id="T2", name="a", purpose="", stories=["S1"])]
    _, causes = _causes(c, ss, threads=threads)
    # the two unconnected threads also raise an "ask the author" cause, which closes the last thread
    assert [(z.thread, z.story, z.kind) for z in causes] == [("T1", "S2", "hazard"), ("T2", "S1", "reader"),
                                                             ("T2", None, "ask")]


def test_the_reading_and_each_storys_reading_hold_their_causes():
    c = _readers("report", "dump")
    ss = _set(["N1"])
    reading, per = build_reading(ss, c)
    assert [z.text for z in reading.causes] == ["2 places read `Uart::errors`, which `config` now writes"]
    assert per["S1"].causes == reading.causes
    assert all(k.cause == reading.causes[0].id for k in reading.checks)


def test_a_reading_stored_before_causes_has_none_and_a_fresh_one_without_checks_has_an_empty_list():
    assert Reading.model_validate({}).causes is None
    assert StoryReading.model_validate({"story": "S1"}).causes is None
    reading, per = build_reading(_set(["N1"]), _world([_edit("send", "drv/uart.c")]))
    assert reading.causes == [] and per["S1"].causes == []


def _lines(ch):
    return [(ln.sign, ln.text.strip(), ln.line) for ln in ch.lines]


def test_a_reader_cause_shows_the_new_write_with_a_line_around_it():
    c = _world([("config", "drv/cfg.c", ["a = 0;"], ["a = 0;", "r->errors = 1;"]), _same("report", "svc/rep.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged")])
    next(a for a in c.after[0].fields if a.fn == "c:@F@config").line = 4
    rows, (cause,) = _causes(c, _set(["N1"]))
    assert cause.change.path == "drv/cfg.c" and cause.change.function == "config"
    assert _lines(cause.change) == [(" ", "a = 0;", 3), ("+", "r->errors = 1;", 4), (" ", "}", 5)]


def test_a_caller_cause_shows_the_signature_before_and_after():
    c, ss = _caller_world()
    _, (cause,) = _causes(c, ss)
    assert _lines(cause.change) == [("-", "int send(int len)", 1), ("+", "int send(unsigned len)", 1)]


def test_a_result_cause_shows_the_new_return():
    c = _world([("send", "drv/uart.c", ["a = 0;"], ["a = 0;", "if (full) return -2;", "a = 1;"]), _same("a", "x/a.c")],
               calls=[("a", "send")])
    from test_reading import _sig
    _sig(c, "send", returns=(["0"], ["0", "-2"]))
    next(f for f in c.after[0].functions if f.name == "send").return_lines = {"-2": 4}
    next(e for e in c.after[0].calls if e.caller == "c:@F@a").result_used = False
    _, (cause,) = _causes(c, _set(["N1"]))
    assert ("+", "if (full) return -2;", 4) in _lines(cause.change) and len(cause.change.lines) <= 6


def test_without_its_own_line_a_cause_shows_the_functions_first_changed_block_and_never_more_than_six_lines():
    body_b = ["a = 0;"]
    body_a = ["a = 0;", *(f"x{i} = {i};" for i in range(9))]
    c = _world([("send", "drv/uart.c", body_b, body_a)])
    c.impact.capped = {"send": 90}
    rows, (cause,) = _causes(c, _set(["N1"]))
    assert cause.kind == "unanalysed" and len(cause.change.lines) == 6
    assert all(ln.sign == "+" for ln in cause.change.lines)


@pytest.mark.parametrize("fns, name, want", [
    # an edit in the middle: the context above and below it and the removed and added lines are the rows the diff numbers
    ([("send", "drv/uart.c", ["\f", "a = 0;", "b = 0;", "c = 0;"], ["\f", "a = 0;", "x = 1;", "c = 0;"])], "send",
     [(" ", "a = 0;", 4), ("-", "b = 0;", 5), ("+", "x = 1;", 5), (" ", "c = 0;", 6)]),
    # an edit at the end of the file has no row below it, whatever the rows above it split into
    ([("early", "drv/uart.c", ["\f", "a = 0;"], ["\f", "a = 0;"]), ("late", "drv/uart.c", None, ["a = 0;"])], "late",
     [(" ", "}", 5), ("+", "void late(void)", 6), ("+", "{", 7), ("+", "a = 0;", 8), ("+", "}", 9)])])
def test_a_cause_shows_the_rows_the_line_diff_numbers_when_a_form_feed_line_comes_above_the_change(fns, name, want):
    c = _world(fns)
    c.impact.capped = {name: 90}
    _, (cause,) = _causes(c, _set([next(n for n, x in c.impact.nodes.items() if x.label == name)]))
    assert cause.kind == "unanalysed"
    assert _lines(cause.change) == want


def test_a_cause_without_a_changed_function_has_no_change():
    from codetortoise.reading import Check
    c = _world([_edit("a", "x/a.c")])
    ask = Check(key="ask|||a", kind="ask", text="Ask the author")
    assert change_for("ask", [ask], _x(c)) is None


def test_the_change_names_its_depot_file():
    c = _readers("report")
    reading, _ = build_reading(_set(["N1"]), c)
    assert reading.causes[0].change.depot == "//d/w/drv/cfg.c"


def test_two_changed_functions_of_one_name_in_two_files_are_two_causes_each_with_its_own_change():
    c = _world([_edit("init_u", "drv/uart.c"), _edit("init_s", "drv/spi.c"), _same("report", "svc/rep.c")],
               fields=[("init_u", "Uart", "errors", "write", "added"), ("init_s", "Uart", "errors", "write", "added"),
                       ("report", "Uart", "errors", "read", "unchanged")])
    for f in [*c.before[0].functions, *c.after[0].functions]:       # two `static int init()`: one name, two files
        if f.name.startswith("init_"):
            f.qualname = "init"
    rows, causes = _causes(c, _set(["N1", "N2"]))
    assert len(causes) == 2
    assert sorted(z.id for z in causes) == sorted([cause_id("reader", "drv/uart.c::init", "Uart::errors"),
                                                   cause_id("reader", "drv/spi.c::init", "Uart::errors")])
    assert sorted(z.change.path for z in causes) == ["drv/spi.c", "drv/uart.c"]
    assert all(len(z.places) == 1 for z in causes)
