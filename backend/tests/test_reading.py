"""How a review reads (spec 2026-10-07-review-reading §4–§8): story links, threads, connections, reading order."""
from test_stories import _edit, _in_cls, _same, _world

from codetortoise.board import analyse
from codetortoise.reading import Thread, build_threads, call_paths, connections, contract_rows, story_links, where
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


# ---- §4.3 thread connections
def _threads(*groups):
    """One thread per group of story ids."""
    return [Thread(id=f"T{i}", name=f"t{i}", purpose="", stories=list(g)) for i, g in enumerate(groups, 1)]


def _conn(conns, a, b):
    return next(k for k in conns if {k.a, k.b} == {a, b})


def test_threads_whose_changes_share_a_caller_within_three_hops_meet_there_preferring_an_entry_point():
    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _same("helper", "app/h.c"),
                _same("main", "app/main.c")],
               calls=[("helper", "send"), ("helper", "init"), ("main", "helper")])
    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
    assert (k.kind, k.text, k.facts, k.shown) == ("caller", "both run inside `main`", ["N4", "N1", "N2"], True)
    c.cfg.entrypoint_patterns = []
    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
    assert k.text == "both run inside `helper`"


def test_a_caller_four_hops_away_is_not_shared():
    c = _world([_edit("send", "drv/uart.c"), _edit("init", "drv/init.c"), _same("a", "x/a.c"), _same("b", "x/b.c"),
                _same("cc", "x/c.c"), _same("main", "app/main.c")],
               calls=[("a", "send"), ("b", "a"), ("cc", "b"), ("main", "cc"), ("main", "init")])
    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
    assert k.kind != "caller"
    c.impact.edges.append(c.impact.edges[0].model_copy(update={"id": "E9", "src": "N6", "dst": "N3"}))   # main → a too
    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
    assert (k.kind, k.facts) == ("caller", ["N6", "N1", "N2"])


def test_threads_using_one_struct_share_vocabulary():
    c = _world([_edit("cfg", "drv/a.c"), _edit("rep", "svc/b.c")],
               fields=[("cfg", "Uart", "baud", "write", "unchanged"), ("rep", "Uart", "errors", "read", "unchanged")])
    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
    assert (k.kind, k.text, k.facts) == ("vocabulary", "both use `struct Uart`", ["N3", "N4"])


def test_threads_using_a_changed_macro_or_including_a_changed_header_share_vocabulary():
    from codetortoise.diffmap import TypeChange
    from codetortoise.vcs.model import FileChange
    c = _world([("cfg", "drv/a.c", ["a = 0;"], ["a = UART_MAX;"]), ("rep", "svc/b.c", ["b = 0;"], ["b = UART_MAX + 1;"])])
    c.dm.types.append(TypeChange(file="/w/drv/uart.h", depot="//d/w/drv/uart.h", name="UART_MAX", kind="macro_changed"))
    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
    assert (k.kind, k.text, k.facts) == ("vocabulary", "both use `UART_MAX`", ["drv/uart.h"])
    c = _world([_edit("cfg", "drv/a.c"), _edit("rep", "svc/b.c")])
    for f in c.cs.files:
        f.after = '#include "uart.h"\n' + f.after
    c.cs.files.append(FileChange(depot="//d/w/drv/uart.h", local="/w/drv/uart.h", action="edit", before="\n",
                                 after="#define UART_MAX 4\n"))
    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
    assert (k.kind, k.text, k.facts) == ("vocabulary", "both include `drv/uart.h`", ["drv/uart.h"])


def test_threads_built_only_for_one_target_of_several_or_under_one_condition_share_it():
    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c"), _edit("h", "z/h.c")])
    ss = _set(["N1"], ["N2"], ["N3"], cls={"S1": [1], "S2": [2], "S3": [3]})
    for s, t in zip(ss.stories, (["fw"], ["fw"], ["host"]), strict=True):
        s.targets = t
    conns = connections(_threads(["S1"], ["S2"], ["S3"]), ss, _x(c))
    assert (_conn(conns, "T1", "T2").kind, _conn(conns, "T1", "T2").text) == ("condition", "both build only for `fw`")
    c = _world([_edit("a", "x/a.c"), _edit("b", "y/b.c")])
    for f in c.cs.files:
        f.after = "#ifdef CONFIG_WIN\n" + f.after + "#endif\n"
    ss = _set(["N1"], ["N2"], cls={"S1": [1], "S2": [2]})
    k = _conn(connections(_threads(["S1"], ["S2"]), ss, _x(c)), "T1", "T2")
    assert (k.kind, k.text, k.facts) == ("condition", "both sit under `#if defined(CONFIG_WIN)`", ["x/a.c", "y/b.c"])


def test_threads_alone_in_a_folder_share_the_place_and_otherwise_only_their_bundle():
    c = _world([_edit("a", "src/util/win32/a.c"), _edit("b", "src/util/win32/b.c"), _edit("c", "src/util/c.c"),
                _edit("d", "lib/d.c")])
    _in_cls(c, {"src/util/win32/a.c": 11, "src/util/win32/b.c": 11, "src/util/c.c": 11, "lib/d.c": 12})
    c.cs.cls[1].user = c.cs.cls[0].user = "ana"
    ss = _set(["N1"], ["N2"], ["N3"], ["N4"], cls={"S1": [11], "S2": [11], "S3": [11], "S4": [12]})
    conns = connections(_threads(["S1"], ["S2"], ["S3"], ["S4"]), ss, _x(c))
    assert (_conn(conns, "T1", "T2").kind, _conn(conns, "T1", "T2").text) == ("place", "both live under `src/util/win32`")
    assert _conn(conns, "T1", "T3").text == "nothing besides arriving in CL 11"      # src/util holds T2's files too
    assert (_conn(conns, "T1", "T4").kind, _conn(conns, "T1", "T4").text) == ("bundled", "nothing besides their author ana")
    c.cs.cls[1].user = "bo"
    conns = connections(_threads(["S1"], ["S2"], ["S3"], ["S4"]), ss, _x(c))
    assert _conn(conns, "T1", "T4").text == "nothing besides arriving in this review"
    ss.stories[3].cls = [11, 12]
    conns = connections(_threads(["S1"], ["S2"], ["S3"], ["S4"]), ss, _x(c))
    assert _conn(conns, "T1", "T4").text == "nothing besides arriving in CL 11"


def test_a_lone_threads_arc_goes_to_a_thread_sharing_its_cl_when_folders_tie():
    c = _world([_edit("a", "p/a.c"), _edit("b", "q/b.c"), _edit("c", "r/c.c")])
    ss = _set(["N1"], ["N2"], ["N3"], cls={"S1": [1], "S2": [2], "S3": [2]})
    conns = connections(_threads(["S1"], ["S2"], ["S3"]), ss, _x(c))
    assert sorted((k.a, k.b) for k in conns if k.shown) == [("T1", "T2"), ("T2", "T3")]


def test_only_pairs_not_already_joined_by_as_strong_a_connection_are_shown_and_a_lone_thread_gets_one_bundled_arc():
    c = _world([_edit("a", "src/a.c"), _edit("b", "src/k/b.c"), _edit("c", "src/k/c.c"), _edit("d", "src/k/d/d.c"),
                _same("main", "app/main.c")],
               calls=[("main", "a"), ("main", "b"), ("main", "c")])
    ss = _set(["N1"], ["N2"], ["N3"], ["N4"], cls={"S1": [1], "S2": [2], "S3": [3], "S4": [4]})
    conns = connections(_threads(["S1"], ["S2"], ["S3"], ["S4"]), ss, _x(c))
    shown = sorted((k.a, k.b, k.kind) for k in conns if k.shown)
    assert shown == [("T1", "T2", "caller"), ("T1", "T3", "caller"), ("T2", "T4", "bundled")]
    assert len(conns) == 6


# ---- §8.1 contract rows
def _sig(c, name, before=None, after=None, returns=None, names=None):
    """Give `name` a signature (before / after side) and, after, return values."""
    for fx, sig in ((c.before[0], before), (c.after[0], after)):
        f = next(f for f in fx.functions if f.name == name)
        if sig:
            f.signature = sig
    if returns:
        b, a = returns
        next(f for f in c.before[0].functions if f.name == name).returns = b
        fa = next(f for f in c.after[0].functions if f.name == name)
        fa.returns, fa.return_names = a, names or {}


def test_a_signature_row_marks_the_part_that_differs():
    c = _world([_edit("send", "drv/uart.c")])
    _sig(c, "send", "int send(int len)", "int send(unsigned len)")
    (row,) = contract_rows(_set(["N1"]).stories[0], _x(c))
    assert (row.kind, row.node, row.before, row.after, row.mark) == ("signature", "N1", "int send(int len)",
                                                                     "int send(unsigned len)", [9, 17])
    assert row.text == "`send`: `int` → `unsigned`"


def test_the_same_signature_edit_in_two_functions_is_one_repeated_row():
    c = _world([_edit("a", "x/a.c"), _edit("b", "x/b.c"), _edit("solo", "x/c.c")])
    _sig(c, "a", "void a(int x)", "void a(int x, const opts *o)")
    _sig(c, "b", "void b(char *s)", "void b(char *s, const opts *o)")
    _sig(c, "solo", "void solo(void)", "int solo(void)")
    rows = contract_rows(_set(["N1", "N2", "N3"]).stories[0], _x(c))
    assert [(r.kind, r.text, r.nodes) for r in rows] == [
        ("repeated", "2 signatures gained `const opts *o`", ["N1", "N2"]),
        ("signature", "`solo`: `void` → `int`", ["N3"])]


def test_return_values_fields_and_body_only_changes_each_get_a_row():
    c = _world([_edit("send", "drv/uart.c"), _edit("config", "drv/cfg.c"), _edit("p", "x/p.c"), _edit("q", "x/q.c")],
               fields=[("config", "Uart", "errors", "write", "added")])
    _sig(c, "send", returns=(["0"], ["0", "-2"]), names={"-2": "UART_EBUSY"})
    c.impact.edges.append(c.impact.edges[0].model_copy(update={"id": "E9", "status": "removed", "dst": "N6"}))
    c.impact.nodes["N6"] = c.impact.nodes["N5"].model_copy(update={"id": "N6", "key": "field:c:@S@Uart@FI@old",
                                                                    "label": "Uart::old"})
    rows = contract_rows(_set(["N1", "N2", "N3", "N4"]).stories[0], _x(c))
    assert [(r.kind, r.text, r.added, r.removed, r.nodes) for r in rows] == [
        ("returns", "`send` can now return UART_EBUSY (-2)", ["UART_EBUSY (-2)"], [], ["N1"]),
        ("fields", "`config` now writes `Uart::errors`; no longer writes `Uart::old`", ["Uart::errors"], ["Uart::old"],
         ["N2"]),
        ("body", "2 functions changed only inside the body", [], [], ["N3", "N4"])]


def test_a_mechanical_story_is_one_repeated_row_and_added_or_removed_functions_say_so():
    from test_stories import _mech

    from codetortoise.stories import build_stories
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c", var="b"), ("fresh", "src/n.c", None, ["x = 1;"])])
    ss, _ = build_stories(c)
    m = next(s for s in ss.stories if s.kind == "mechanical")
    assert [(r.kind, r.text, r.nodes) for r in contract_rows(m, _x(c))] == [
        ("repeated", "`git_vector_free` → `git_vector_dispose` at 2 sites", ["N1", "N2"])]
    (row,) = contract_rows(_set(["N3"]).stories[0], _x(c))
    assert (row.kind, row.text, row.before, row.after) == ("signature", "`fresh` added", "", "void fresh(void)")


# ---- §6.1 where
def test_where_lists_each_file_and_its_functions_with_edit_size_and_cl():
    c = _world([_edit("a", "drv/uart.c"), ("b", "drv/uart.c", ["x;"], ["y;", "z;"]), _edit("c", "svc/log.c")])
    _in_cls(c, {"drv/uart.c": 11, "svc/log.c": 12})
    got = where(_set(["N1", "N2", "N3"]).stories[0], _x(c))
    assert [(f.path, f.depot, [(fn.label, fn.add, fn.rem, fn.cl, fn.line) for fn in f.functions]) for f in got] == [
        ("drv/uart.c", "//d/w/drv/uart.c", [("a", 1, 0, 11, 1), ("b", 2, 1, 11, 6)]),
        ("svc/log.c", "//d/w/svc/log.c", [("c", 1, 0, 12, 1)])]


# ---- §8.2 call paths
def test_every_caller_chain_up_to_an_entry_point_is_a_call_path_long_ones_folded_flows_first():
    from codetortoise.board import Flow
    c = _world([_edit("send", "drv/uart.c"), _same("low", "a/l.c"), _same("mid", "a/m.c"), _same("app", "a/a.c"),
                _same("main", "a/main.c"), _same("other", "b/o.c")],
               calls=[("low", "send"), ("mid", "low"), ("app", "mid"), ("main", "app"), ("other", "send")])
    _sig(c, "send", "int send(int len)", "int send(unsigned len)")
    fl = Flow(id="FL1", path=["N6", "N1"], tag="contract", lands="N6", severity="medium", text="", what="",
              effect="Arguments other passes to send are converted.", check="")
    story = _set(["N1"]).stories[0]
    story.flows = ["FL1"]
    paths = call_paths(story, _x(c), [fl])
    assert [(p.steps, p.kind, p.entry, p.hidden, p.text, p.flow) for p in paths] == [
        (["N6", "N1"], "contract", None, [], "Arguments other passes to send are converted.", "FL1"),
        (["N5", "N4", "N3", "N2", "N1"], "call", "N5", ["N4", "N3"], "calls `send`, whose signature changed", None)]
    assert paths[1].labels == ["main", "app", "mid", "low", "send"]


def test_call_paths_are_not_capped():
    fns = [_edit("send", "drv/uart.c")] + [_same(f"c{i}", f"k/c{i}.c") for i in range(30)]
    c = _world(fns, calls=[(f"c{i}", "send") for i in range(30)])
    paths = call_paths(_set(["N1"]).stories[0], _x(c), [])
    assert len(paths) == 30 and paths[0].text == "calls `send`, whose body changed"
