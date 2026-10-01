import pytest

from codetortoise.board import BoardContext, _common_dir, _crossings, _tree_prefix, barycentre_layout, build_board
from codetortoise.config import AnalysisConfig
from codetortoise.detectors.base import DetectorContext, run_detectors
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function, TuInfo
from codetortoise.impact import BlastItem, Edge, ImpactModel, Node
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def _ctx(a, fx_source, **cfg):
    findings = run_detectors(DetectorContext(a.before, a.after, a.dm, a.impact, a.cfg))
    return BoardContext(a.cs, a.dm, a.before, a.after, a.impact, findings, a.layers,
                        a.cfg.model_copy(update=cfg), fx_source.depots_for)


@pytest.fixture(scope="module")
def board(analysed, fx_source):
    return build_board(_ctx(analysed, fx_source))


def _labels(board, ids):
    by = {n.id: n.label for n in board.nodes}
    return [by[i] for i in ids]


def test_fixture_board_has_the_three_prototype_flows(board):
    got = [(f.tag, _labels(board, f.path)) for f in board.flows]
    assert got == [
        ("state", ["main", "logger_write", "uart_send", "Uart::errors", "uart_errors"]),
        ("contract", ["main", "logger_flush", "uart_send"]),
        ("contract", ["main", "uart_init", "hal_write"]),
    ]
    state, ignored, sig = board.flows
    assert [f.id for f in board.flows] == ["FL1", "FL2", "FL3"]
    assert state.severity == "high" and state.fx_at is None
    assert ignored.text == "main → logger_flush → uart_send ⟶ -2 ignored"
    assert _labels(board, [ignored.fx_at]) == ["logger_flush"] and ignored.findings
    assert sig.text.endswith("⟶ signature changed")
    assert "uart_errors" in state.effect and "Uart::errors" in state.check


def test_fixture_board_annotates_where_the_effects_land(board):
    got = {(i.path.rsplit("/", 2)[-2] + "/" + i.path.rsplit("/", 1)[-1], i.line, i.severity, i.channel)
           for i in board.impacts}
    assert {
        ("service/logger.c", 21, "warn", "contract"),     # logger_flush ignores the result
        ("service/logger.c", 12, "ok", "contract"),       # logger_write checks != 0
        ("driver/uart.c", 29, "warn", "state"),           # uart_errors reads Uart::errors
        ("driver/uart.h", 15, "warn", "state"),           # the field declaration
        ("driver/uart.c", 17, "warn", "state"),           # uart_send writes errors through `err`
        ("driver/uart.c", 18, "warn", "contract"),        # uart_send's new return -2
        ("driver/uart.c", 8, "warn", "signature"),        # uart_init calls hal_write
    } <= got
    (decl,) = [i for i in board.impacts if i.line == 15 and i.path.endswith("uart.h")]
    assert decl.text == "new writer: uart_send · readers: uart_errors · other writers: uart_init"
    (tx,) = [i for i in board.impacts if i.path.endswith("uart.h") and i.line == 7]
    assert tx.severity == "info"                          # nobody else uses Stats::tx
    assert all(i.path.startswith("//fixture/") for i in board.impacts)


def test_co_writers_are_annotated_but_are_not_landings(board):
    (w,) = [i for i in board.impacts if i.path.endswith("uart.c") and i.line == 7]
    assert w.text.startswith("writes Uart::errors") and w.severity == "warn" and not w.landing
    landed = {_labels(board, [f.lands])[0] for f in board.flows}
    assert landed == {"uart_errors", "logger_flush", "uart_init"}


def test_board_nodes_carry_change_ranges_layers_and_warn_counts(board):
    by = {n.label: n for n in board.nodes}
    send = by["uart_send"]
    assert send.change.kind == "modified" and send.change.add > 0
    assert send.path == "//fixture/driver/uart.c" and send.range[0] <= 17 <= send.range[1]
    assert by["hal_write"].change.kind == "signature"
    assert by["uart_errors"].change is None and by["uart_errors"].warn == 1
    assert by["Uart::errors"].kind == "field" and by["Uart::errors"].range == [15, 15]
    assert by["Uart::errors"].layer == by["uart_send"].layer
    names = {l.level: l.name for l in board.layers}
    assert names[by["main"].layer] == "app" and names[by["hal_write"].layer] == "hal"
    assert [l.level for l in board.layers] == sorted(names, reverse=True)
    ids = {n.id for n in board.nodes}
    assert all(e.src in ids and e.dst in ids for e in board.edges)


def test_board_node_cap_keeps_changed_and_flow_nodes_first(analysed, fx_source):
    b = build_board(_ctx(analysed, fx_source, board_max_nodes=6))
    assert len(b.nodes) == 6 and b.hidden_nodes > 0
    labels = {n.label for n in b.nodes}
    assert {"uart_send", "hal_write"} <= labels
    assert all(i.node in {n.id for n in b.nodes} for i in b.impacts)


def test_about_groups_changed_files_by_directory(board):
    tree = {d.dir: [(f.name, f.cls) for f in d.files] for d in board.about.tree}
    assert tree == {"driver": [("uart.c", [101]), ("uart.h", [102])], "hal": [("regs.c", [102])],
                    "include/hal": [("regs.h", [102])]}
    assert [c.cl for c in board.about.cls] == [101, 102]
    assert board.about.intent.startswith("2 function(s) changed in 4 file(s).")
    assert board.about.why and board.about.intent_source == "template"


def test_tree_prefix_keeps_the_deepest_common_directory_visible():
    assert _tree_prefix(["//d/lib/src/a.c", "//d/lib/src/b.h"]) == "//d/lib"
    assert _tree_prefix(["//fixture/driver/uart.c", "//fixture/include/hal/regs.h"]) == "//fixture"


def test_common_dir_keeps_the_depot_prefix():
    assert _common_dir(["//depot/a/x.c", "//depot/a/b/y.c"]) == "//depot/a"
    assert _common_dir(["//depot/a/x.c"]) == "//depot/a"
    assert _common_dir(["//d1/x.c", "//d2/y.c"]) == "/"
    assert _common_dir([]) == ""


def test_barycentre_layout_untangles_crossed_layers():
    layer_of = {"a": 1, "b": 1, "c": 0, "d": 0}
    edges = [("a", "d"), ("b", "c")]                      # initial order a,b / c,d crosses
    xs = barycentre_layout(layer_of, edges)
    order = {lv: sorted([n for n in layer_of if layer_of[n] == lv], key=xs.get) for lv in (0, 1)}
    assert _crossings(order, edges, layer_of) == 0
    assert sorted(xs[n] for n in ("a", "b")) == [-110.0, 110.0]


def test_board_without_findings_has_no_flows(analysed, fx_source):
    c = _ctx(analysed, fx_source)
    c.findings = []
    b = build_board(c)
    assert b.flows == [] or all(f.findings == [] for f in b.flows)
    assert any(n.change for n in b.nodes)


# ---- synthetic facts: shapes seen on real code (libgit2 lab) that the uart fixture does not have
def _fn(usr, name, file, start, end, returns=("0",), lines=None):
    return Function(usr=usr, qualname=name, name=name, signature=f"int {name}(void)", return_type="int", file=file,
                    start_line=start, end_line=end, returns=list(returns), return_lines=lines or {})


def _acc(fn, mode, file, line, w="/w"):
    return FieldAccess(fn=fn, field="c:@S@R@FI@v", field_name="v", record="R", record_file=f"{w}/r.h", decl_line=3,
                       path="r->v", root_kind="param", mode=mode, via=["p"] if fn == "c:@F@set" else [], file=file, line=line)


def _synthetic(callers=("test_set",), test_ignores=False, w="/w"):
    """set() newly writes R::v through alias p and can now return -1; peek() reads and bumps R::v on one line and
    ignores set()'s result; set's only other caller is a test. `w` is the workspace root."""
    set_b = _fn("c:@F@set", "set", f"{w}/a.c", 1, 9)
    set_a = _fn("c:@F@set", "set", f"{w}/a.c", 1, 9, ("0", "-1"), {"-1": 6})
    peek = _fn("c:@F@peek", "peek", f"{w}/b.c", 20, 24)
    fns = {"test_set": _fn("c:@F@test_set", "test_set", f"{w}/tests/t.c", 1, 4),
           "api": _fn("c:@F@api", "api", f"{w}/api.c", 1, 4)}
    calls = [CallEdge(caller=f"c:@F@{c}", callee="c:@F@set", callee_name="set", file=fns[c].file, line=2,
                      result_used=not (test_ignores and c == "test_set")) for c in callers]
    calls.append(CallEdge(caller="c:@F@peek", callee="c:@F@set", callee_name="set", file=f"{w}/b.c", line=22,
                          result_used=False))
    after = [Facts(tu=TuInfo(file=f"{w}/a.c", variant="after"), functions=[set_a, peek, *(fns[c] for c in callers)],
                   calls=calls, fields=[_acc("c:@F@set", "write", f"{w}/a.c", 5, w), _acc("c:@F@peek", "read", f"{w}/b.c", 21, w),
                                        _acc("c:@F@peek", "write", f"{w}/b.c", 21, w)])]
    before = [Facts(tu=TuInfo(file=f"{w}/a.c", variant="before"), functions=[set_b, peek])]
    nodes = {"N1": Node(id="N1", key="c:@F@set", label="set", file=f"{w}/a.c", line=1, status="changed", layer=1),
             "N2": Node(id="N2", key="field:c:@S@R@FI@v", kind="field", label="R::v", layer=1),
             "N3": Node(id="N3", key="c:@F@peek", label="peek", file=f"{w}/b.c", line=20, layer=1),
             "N4": Node(id="N4", key="c:@F@test_set", label="test_set", file=f"{w}/tests/t.c", line=1, layer=2),
             "N5": Node(id="N5", key="c:@F@api", label="api", file=f"{w}/api.c", line=1, layer=2)}
    edges = [Edge(id="E1", src="N1", dst="N2", kind="writes"), Edge(id="E2", src="N3", dst="N2", kind="reads"),
             Edge(id="E3", src="N3", dst="N1", kind="call")]
    edges += [Edge(id=f"E{4 + i}", src={"test_set": "N4", "api": "N5"}[c], dst="N1", kind="call") for i, c in enumerate(callers)]
    im = ImpactModel(nodes=nodes, edges=edges, changed=["N1"],
                     blast=[BlastItem(node="N4", hop=1, score=1.0, via="call", path=["N1", "N4"])])
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                   files=[FileChange(depot="//d/lib/src/a.c", local=f"{w}/a.c", action="edit", before="x\n", after="y\n")])
    asked = []

    def depots_for(locals_):
        asked.append(list(locals_))
        return {p: "//d/lib" + p[len(w):] for p in locals_}
    ctx = BoardContext(cs, DiffMap(), before, after, im, [], None, AnalysisConfig(), depots_for, root=w)
    return ctx, asked


def test_a_line_that_reads_and_writes_a_field_gets_one_annotation():
    b = build_board(_synthetic()[0])
    (imp,) = [i for i in b.impacts if i.node == "N3" and i.channel == "state"]
    assert imp.line == 21 and imp.landing
    assert imp.text == "reads and writes R::v — now also written by set (line 5)"


def test_tests_are_neither_flow_entries_nor_blast_nodes():
    b = build_board(_synthetic()[0])
    labels = {n.id: n.label for n in b.nodes}
    state, contract = sorted(b.flows, key=lambda f: f.tag, reverse=True)
    assert [labels[n] for n in state.path] == ["set", "R::v", "peek"]
    assert state.what.startswith("set now writes R::v. peek (unlayered) uses that field")
    assert [labels[n] for n in contract.path] == ["peek", "set"]
    assert contract.what.startswith("peek (unlayered) calls set and ignores the result.")
    assert "test_set" not in labels.values()


def test_flows_start_at_a_real_caller_when_there_is_one():
    b = build_board(_synthetic(callers=("test_set", "api"))[0])
    labels = {n.id: n.label for n in b.nodes}
    (state,) = [f for f in b.flows if f.tag == "state"]
    assert [labels[n] for n in state.path] == ["api", "set", "R::v", "peek"]


def test_depot_paths_are_resolved_once_for_what_the_board_shows():
    ctx, asked = _synthetic()
    b = build_board(ctx)
    assert len(asked) == 1
    assert set(asked[0]) <= {"/w/a.c", "/w/b.c", "/w/r.h"}
    assert {n.label: n.path for n in b.nodes}["peek"] == "//d/lib/b.c"
    assert {(i.path, i.line) for i in b.impacts} >= {("//d/lib/b.c", 21), ("//d/lib/r.h", 3), ("//d/lib/a.c", 6)}


def test_test_callers_are_never_landings():
    b = build_board(_synthetic(test_ignores=True)[0])
    assert all("N4" not in f.path for f in b.flows)
    assert [f.tag for f in b.flows].count("contract") == 1          # peek only


def test_test_code_is_recognised_relative_to_the_workspace():
    b = build_board(_synthetic(callers=("test_set", "api"), w="/srv/test/ws")[0])
    labels = {n.id: n.label for n in b.nodes}
    (state,) = [f for f in b.flows if f.tag == "state"]
    assert [labels[n] for n in state.path] == ["api", "set", "R::v", "peek"]
    assert "test_set" not in labels.values()


@pytest.mark.parametrize("rel,test", [("tests/a.c", True), ("src/test/a.c", True), ("unittests/x.cc", True),
                                      ("fuzz/f.c", True), ("src/test_uart.c", True), ("src/uart_test.cc", True),
                                      ("src/uart_unittest.cpp", True), ("src/uart.c", False), ("src/attest.c", False),
                                      ("src/contest/x.c", False), ("src/testing_utils.h", False)])
def test_test_path_patterns(rel, test):
    from codetortoise.board import is_test_path
    assert is_test_path(rel) is test
