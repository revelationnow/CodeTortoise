"""How a review reads (spec 2026-10-07-review-reading §4–§8): story links, threads, connections, reading order."""
from test_stories import _edit, _world

from codetortoise.board import analyse
from codetortoise.reading import build_threads, story_links
from codetortoise.stories import Story, StorySet


def _set(*groups, kinds=None, cls=None):
    """Stories S1… holding the given node ids; `kinds` and `cls` by story id."""
    stories = [Story(id=f"S{i}", kind=(kinds or {}).get(f"S{i}", "other"), title=f"story {i}", summary=f"does {i}",
                     nodes=list(g), cls=(cls or {}).get(f"S{i}", [1])) for i, g in enumerate(groups, 1)]
    return StorySet(summary="", stories=stories, node_story={n: s.id for s in stories for n in s.nodes})


def _x(c):
    return analyse(c).x


# ---- §4.1 story links
def test_a_call_into_another_storys_changed_function_is_a_strong_link_from_the_story_that_defines_it():
    c = _world([_edit("send", "drv/uart.c"), _edit("write", "svc/log.c")], calls=[("write", "send")])
    (lk,) = story_links(_set(["N1"], ["N2"]), _x(c))
    assert (lk.a, lk.b, lk.strength, lk.kind, lk.defines) == ("S1", "S2", "strong", "calls", "S1")
    assert lk.text == "calls `send`, changed in S1" and lk.facts == ["N2", "N1"]


def test_reading_or_writing_a_field_another_story_now_writes_is_a_data_link():
    c = _world([_edit("config", "drv/uart.c"), _edit("report", "svc/log.c")],
               fields=[("config", "Uart", "errors", "write", "added"), ("report", "Uart", "errors", "read", "unchanged")])
    (lk,) = story_links(_set(["N1"], ["N2"]), _x(c))
    assert (lk.kind, lk.strength, lk.defines) == ("data", "strong", "S1")
    assert lk.text == "reads `Uart::errors`, which S1 now writes" and lk.facts == ["N1", "N3", "N2"]


def test_a_call_beats_data_and_the_story_with_more_calls_into_it_defines():
    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c"), _edit("b2", "y/c.c")],
               calls=[("a", "b"), ("b", "a"), ("b2", "a")],
               fields=[("a", "R", "v", "write", "added"), ("b", "R", "v", "read", "unchanged")])
    (lk,) = story_links(_set(["N1"], ["N2", "N3"]), _x(c))
    assert (lk.kind, lk.defines) == ("calls", "S1")
    assert lk.text == "calls `a`, changed in S1" and lk.facts == ["N2", "N1", "N3"]


def test_stories_sharing_only_a_file_or_a_cl_are_weakly_linked_without_direction():
    c = _world([_edit("p", "src/a.c"), _edit("q", "src/a.c"), _edit("r", "lib/r.c")])
    links = story_links(_set(["N1"], ["N2"], ["N3"]), _x(c))
    got = {(lk.a, lk.b): (lk.strength, lk.kind, lk.defines, lk.text, lk.facts) for lk in links}
    assert got == {("S1", "S2"): ("weak", "file", None, "both edit `src/a.c`", ["src/a.c"]),
                   ("S1", "S3"): ("weak", "cl", None, "both arrive in CL 1", ["CL 1"]),
                   ("S2", "S3"): ("weak", "cl", None, "both arrive in CL 1", ["CL 1"])}


def test_only_a_storys_own_changed_code_links_it_not_the_unchanged_code_its_flows_pass_through():
    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _edit("main", "app/main.c")],
               calls=[("main", "send")])
    ss = _set(["N1"], ["N2"])
    ss.node_story["N3"] = "S2"                       # `main` is on a flow of S2
    (lk,) = story_links(ss, _x(c))
    assert lk.kind == "cl"


def test_a_removed_call_is_not_a_link():
    c = _world([_edit("send", "drv/uart.c"), _edit("write", "svc/log.c")], calls=[("write", "send")])
    c.impact.edges[0].status = "removed"
    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
    assert story_links(ss, _x(c)) == []


# ---- §4.2 threads, §4.4 order within a thread
def _chain():
    """S1 `send` is called by S2 `write`, which writes Log::n that S3 `flush` reads; S4 is apart; S5 is tests."""
    c = _world([_edit("send", "drv/uart.c"), _edit("write", "svc/log.c"), _edit("flush", "svc/flush.c"),
                _edit("lonely", "app/x.c"), _edit("test_send", "tests/t.c")],
               calls=[("write", "send"), ("test_send", "send")],
               fields=[("write", "Log", "n", "write", "added"), ("flush", "Log", "n", "read", "unchanged")])
    return c, _set(["N3"], ["N2"], ["N1"], ["N4"], ["N5"], kinds={"S5": "tests"})


def test_strongly_linked_stories_form_a_thread_in_defines_before_uses_order_with_reasons():
    c, ss = _chain()
    threads, reasons = build_threads(ss, story_links(ss, _x(c)), _x(c))
    assert [(t.id, t.stories) for t in threads] == [("T1", ["S3", "S2", "S1"]), ("T2", ["S4"])]
    assert reasons == {"S2": "← calls 1", "S1": "← uses 2"}


def test_tests_stories_never_join_a_thread():
    c, ss = _chain()
    threads, _ = build_threads(ss, story_links(ss, _x(c)), _x(c))
    assert all("S5" not in t.stories for t in threads)


def test_threads_are_ordered_by_open_hazards_then_open_checks_then_size():
    c, ss = _chain()
    links, x = story_links(ss, _x(c)), _x(c)
    threads, _ = build_threads(ss, links, x, open_counts={"S4": (1, 1)})
    assert [t.stories for t in threads] == [["S4"], ["S3", "S2", "S1"]]
    threads, _ = build_threads(ss, links, x, open_counts={"S4": (0, 2), "S1": (0, 1)})
    assert [t.stories for t in threads] == [["S4"], ["S3", "S2", "S1"]]


def test_a_thread_gets_a_fixed_name_from_its_defining_storys_main_function_and_folder():
    c, ss = _chain()
    threads, _ = build_threads(ss, story_links(ss, _x(c)), _x(c))
    t = threads[0]
    assert (t.name, t.purpose, t.text_source, t.cls) == ("`send` in drv", "does 3", "template", [1])
    assert threads[1].name == "`lonely` in app"


def test_a_cycle_of_definitions_still_orders_every_story_and_prefers_the_link_a_story_uses():
    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c"), _edit("c", "z/c.c")], calls=[("a", "b"), ("b", "c"), ("c", "a")])
    ss = _set(["N1"], ["N2"], ["N3"])
    threads, reasons = build_threads(ss, story_links(ss, _x(c)), _x(c))
    assert [t.stories for t in threads] == [["S1", "S3", "S2"]]
    assert reasons == {"S3": "← calls 1", "S2": "← calls 2"}


def test_a_story_whose_only_links_are_to_later_stories_points_forward():
    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c"), _edit("c", "z/c.c")], calls=[("c", "a"), ("c", "b")])
    ss = _set(["N1"], ["N2"], ["N3"])
    _, reasons = build_threads(ss, story_links(ss, _x(c)), _x(c))
    assert reasons == {"S2": "→ called by 3", "S3": "← calls 1"}


def test_cl_links_name_each_shared_changelist():
    c = _world([_edit("p", "src/a.c"), _edit("q", "lib/b.c")])
    (lk,) = story_links(_set(["N1"], ["N2"], cls={"S1": [11, 12], "S2": [11, 12]}), _x(c))
    assert lk.text == "both arrive in CL 11 and CL 12" and lk.facts == ["CL 11", "CL 12"]
