"""Where the change sits (spec 2026-11-02 §5): components, their bands and the edges that cross between them."""
from test_stories import _world

from codetortoise.board import _Ctx
from codetortoise.components import build_components, component_of
from codetortoise.config import ComponentRule


def test_the_demo_sits_in_five_components_banded_by_layer(demo):
    comps, node_comp = build_components(demo.x, demo.ss, demo.r, demo.per, rules=[], details=demo.det)
    assert [(c.name, c.level, c.band, c.threads, c.quiet) for c in comps] == [
        ("service", 3, "service", ["T2"], False), ("driver", 2, "driver", ["T1"], False),
        ("hal", 1, "hal", ["T1"], False), ("cpp", 0, "cpp, include/hal", ["T3"], True),
        ("include/hal", 0, "cpp, include/hal", ["T1"], False)]
    by = {c.name: c for c in comps}
    assert by["service"].crossing == ["`logger_flush`, `logger_write` call `uart_send`", "`main` calls `logger_init`"]
    assert by["driver"].crossing == ["`uart_init`, `uart_send` call `hal_write`"]
    assert by["hal"].crossing == ["`hal_write` writes `Regs::ctrl`, `Regs::status`"]
    assert by["cpp"].crossing == [] and by["include/hal"].crossing == []
    assert (by["driver"].files, by["driver"].globs, by["driver"].stories) == (
        ["driver/uart.c", "driver/uart.h"], ["driver/*"], ["S1"])
    named = {demo.x.label(n): c for n, c in node_comp.items()}
    assert (named["main"], named["uart_send"], named["Regs::ctrl"]) == ("app", "driver", "include/hal")



def test_a_component_of_declarations_names_the_threads_that_change_it(demo):
    comps, _ = build_components(demo.x, demo.ss, demo.r, demo.per, rules=[], details=demo.det)
    hal = next(c for c in comps if c.name == "include/hal")              # only regs.h: S2's declarations piece
    assert (hal.threads, hal.stories, hal.files) == (["T1"], ["S2"], ["include/hal/regs.h"])

def test_components_from_config_take_the_first_rule_a_file_matches(demo):
    rules = [ComponentRule(name="Driver", globs=["driver/*"]), ComponentRule(name="HAL", globs=["hal/*", "include/hal/*"]),
             ComponentRule(name="Everything", globs=["*"])]
    comps, _ = build_components(demo.x, demo.ss, demo.r, demo.per, rules=rules)
    assert [(c.name, c.level, c.globs) for c in comps] == [
        ("Everything", 3, ["*"]), ("Driver", 2, ["driver/*"]), ("HAL", 1, ["hal/*", "include/hal/*"])]
    assert comps[0].files == ["cpp/engine.cpp", "service/logger.c", "service/logger.h"]


def test_a_file_outside_the_workspace_has_no_component_and_one_at_its_root_is_top_level():
    x = _Ctx(_world([("a", "x/y/a.c", ["a = 1;"], ["a = 2;"])]))
    assert component_of(x, "/w/top.c", []) == "top level"
    assert component_of(x, "/elsewhere/sys.h", []) is None
    assert component_of(x, "/w/x/y/a.c", []) == "x/y"
    assert component_of(x, "/w/x/y/a.c", [ComponentRule(name="X", globs=["x/*"])]) == "X"


def test_a_change_inside_one_folder_is_one_component():
    c = _world([("a", "x/a.c", ["a = 1;"], ["a = 2;"]), ("b", "x/b.c", ["b = 1;"], ["b = 2;"])], calls=[("a", "b")])
    x = _Ctx(c)

    class R:
        order, threads = [], []
    comps, _ = build_components(x, None, R, {}, rules=[])
    assert [(c.name, c.level, c.band, c.quiet) for c in comps] == [("x", None, "other", True)]
