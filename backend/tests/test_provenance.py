"""File tags on every visible item (spec §14.3)."""
from codetortoise.board import About, AboutDir, AboutFile, Board, BoardEdge, BoardNode, Flow, Impact
from codetortoise.provenance import tag_board
from tests.test_board import board  # noqa: F401  (module fixture: the fixture review's board)

D = "//fixture/"


def test_every_item_on_the_fixture_board_is_tagged(board):  # noqa: F811
    b = tag_board(board.model_copy(deep=True))
    items = [*b.nodes, *b.edges, *b.impacts, *b.flows, *b.about.cls,
             *(f for d in b.about.tree for f in d.files)]
    assert items and all(i.files for i in items)
    assert all(f.what_files == f.files for f in b.flows)                  # template text: the flow's own files
    assert b.about.intent_files == sorted(f.path for d in b.about.tree for f in d.files)


def test_fixture_tags_are_exact(board):  # noqa: F811
    b = tag_board(board.model_copy(deep=True))
    state = next(f for f in b.flows if f.tag == "state")                  # through the field Uart::errors in uart.h
    assert state.files == [D + "app/main.c", D + "driver/uart.c", D + "driver/uart.h", D + "service/logger.c"]
    by_cl = {c.cl: c.files for c in b.about.cls}
    assert by_cl == {101: [D + "driver/uart.c"], 102: [D + "driver/uart.h", D + "hal/regs.c", D + "include/hal/regs.h"]}
    assert [c.file_count for c in b.about.cls] == [1, 3]
    # layer names come from directory names across the workspace, not only these files: unknown (stage 2 shows L<n>)
    assert all(layer.files is None for layer in b.layers)
    assert not any(f"({layer.name})" in f.what for f in b.flows for layer in b.layers)
    imp = next(i for i in b.impacts if i.node == "N8" and i.line == 8)   # uart_init calls hal_write (changed)
    assert imp.files == [D + "driver/uart.c", D + "hal/regs.c"]
    decl = next(i for i in b.impacts if i.text.startswith("new writer: uart_send · readers: uart_errors"))   # uart.h
    assert decl.files == [D + "driver/uart.c", D + "driver/uart.h"]
    tx = next(i for i in b.impacts if i.text.startswith("writes Stats::tx"))          # on uart_send in uart.c
    assert tx.files == [D + "driver/uart.c", D + "driver/uart.h"]


def test_why_lines_take_their_findings_files_and_are_unknown_without_them(board):  # noqa: F811
    b = tag_board(board.model_copy(deep=True), {"F1": [D + "driver/uart.c", D + "driver/uart.h"]})
    assert b.about.why[0].finding == "F1" and b.about.why[0].files == [D + "driver/uart.c", D + "driver/uart.h"]
    assert all(w.files is None for w in b.about.why[1:])


def _tiny(**about):
    nodes = [BoardNode(id="A", key="a", label="caller", path="//d/a.c"),
             BoardNode(id="B", key="b", label="hal_read"),                 # no visible definition
             BoardNode(id="C", key="c", label="orphan")]                   # no definition, nothing calls it
    edges = [BoardEdge(src="A", dst="B", kind="call", status="unchanged", confidence="precise"),
             BoardEdge(src="B", dst="C", kind="call", status="unchanged", confidence="precise")]
    flow = Flow(id="FL1", path=["A", "B"], tag="contract", lands="A", severity="medium", text="caller → hal_read",
                what="w", effect="e", check="c")
    return Board(nodes=nodes, edges=edges, flows=[flow],
                 about=About(intent="i", tree=[AboutDir(dir=".", files=[AboutFile(path="//d/a.c", name="a.c", action="edit",
                                                                                  cls=[1], add=1, rem=0)])], **about))


def test_a_node_without_a_path_takes_its_callers_files_else_is_unknown():
    b = tag_board(_tiny())
    files = {n.id: n.files for n in b.nodes}
    assert files == {"A": ["//d/a.c"], "B": ["//d/a.c"], "C": None}
    assert [e.files for e in b.edges] == [["//d/a.c"], None]               # unknown on either end: unknown
    assert b.flows[0].files == ["//d/a.c"]
    b.nodes[1].local = "/ws/hal.c"                       # a definition we know of, whose depot lookup failed
    b.impacts = [Impact(node="A", path=None, line=3, severity="warn", channel="contract", title="t", text="x", refs=[])]
    b = tag_board(b)
    assert b.nodes[1].files is None and b.impacts[0].files is None


def test_llm_text_keeps_its_recorded_files_and_is_unknown_when_none_were_recorded():
    b = _tiny(intent_source="llm")
    b.flows[0].what_source = "llm"
    tagged = tag_board(b.model_copy(deep=True))
    assert tagged.flows[0].what_files is None and tagged.about.intent_files is None
    b.flows[0].what_files, b.about.intent_files = ["//d/z.c"], ["//d/a.c"]
    tagged = tag_board(b)
    # LLM text stands in for the flow's own text, so it also carries the flow's files
    assert tagged.flows[0].what_files == ["//d/a.c", "//d/z.c"] and tagged.about.intent_files == ["//d/a.c"]


def test_boards_stored_before_tags_load_with_counts_and_drift_migrated():
    old = _tiny().model_dump()
    old["about"]["cls"] = [{"cl": 1, "user": "u", "description": "d", "files": 1}]
    old["about"]["drift"] = ["//d/a.c (base #3, workspace #4)"]
    b = tag_board(Board.model_validate(old))
    assert b.about.cls[0].file_count == 1 and b.about.cls[0].files == ["//d/a.c"]
    assert b.about.drift[0].text == "//d/a.c (base #3, workspace #4)" and b.about.drift[0].files == ["//d/a.c"]
    old["impacts"] = [{"node": "A", "path": "//d/a.c", "line": 3, "severity": "warn", "channel": "state", "title": "t",
                       "text": "new writer: x · readers: y"}]                 # stored before refs: may name anything
    assert tag_board(Board.model_validate(old)).impacts[0].files is None


def test_local_files_resolve_through_perforce_and_skip_paths_outside_the_workspace():
    from codetortoise.provenance import local_files
    got = local_files(["/ws/a.c", "/ws/b.c", "/usr/include/stdio.h", "/sdk/vendor/bsp.h"], {"/ws/a.c": "//d/a.c"}, "/ws",
                      ["/usr/include"])
    # system headers are not under Perforce; anything else outside the workspace may be (another client): unknown
    assert got == {"/ws/a.c": ["//d/a.c"], "/ws/b.c": None, "/usr/include/stdio.h": [], "/sdk/vendor/bsp.h": None}


def _impact():
    from codetortoise.impact import Edge, ImpactModel, Node
    nodes = {"N1": Node(id="N1", key="set", label="set", file="/ws/a.c", line=1, status="changed"),
             "N2": Node(id="N2", key="field:R::v", kind="field", label="R::v"),         # no file: named by its accessors
             "N3": Node(id="N3", key="peek", label="peek", file="/ws/b.c", line=20),
             "N4": Node(id="N4", key="printf", label="printf", file="/usr/include/stdio.h", line=9),
             "N5": Node(id="N5", key="lost", label="lost", file="/ws/lost.c", line=3)}      # lookup failed: unknown
    edges = [Edge(id="E1", src="N1", dst="N2", kind="writes"), Edge(id="E2", src="N3", dst="N2", kind="reads"),
             Edge(id="E3", src="N3", dst="N1", kind="call"), Edge(id="E4", src="N1", dst="N4", kind="call")]
    return ImpactModel(nodes=nodes, edges=edges, changed=["N1"])


def test_graph_nodes_take_their_files_or_their_accessors_files():
    from codetortoise.provenance import impact_node_files, local_files
    by_local = local_files(["/ws/a.c", "/ws/b.c", "/usr/include/stdio.h", "/ws/lost.c", "/ws/r.h"],
                           {"/ws/a.c": "//d/a.c", "/ws/b.c": "//d/b.c", "/ws/r.h": "//d/r.h"}, "/ws", ["/usr/include"])
    assert impact_node_files(_impact(), by_local) == {
        "N1": ["//d/a.c"], "N2": ["//d/a.c", "//d/b.c"], "N3": ["//d/b.c"], "N4": [], "N5": None}
    # a field is also named by its declaration
    assert impact_node_files(_impact(), by_local, {"field:R::v": "/ws/r.h"})["N2"] == ["//d/a.c", "//d/b.c", "//d/r.h"]


def test_a_finding_depends_on_its_nodes_and_its_evidence():
    from codetortoise.detectors.base import Evidence, Finding
    from codetortoise.provenance import finding_files
    nf = {"N1": ["//d/a.c"], "N5": None}
    by_local = {"/ws/b.c": ["//d/b.c"], "/usr/include/stdio.h": []}
    f = Finding(kind="k", severity="high", title="t", summary="s", nodes=["N1"],
                evidence=[Evidence(text="e", file="/ws/b.c", line=2), Evidence(text="sys", file="/usr/include/stdio.h")])
    assert finding_files(f, nf, by_local) == ["//d/a.c", "//d/b.c"]
    assert finding_files(f.model_copy(update={"nodes": ["N1", "N5"]}), nf, by_local) is None
    assert Finding(kind="k", severity="low", title="t", summary="s").files is None        # stored before tags: unknown
    named = f.model_copy(update={"evidence": [Evidence(text="2 callers: a, z", nodes=["N1", "N9"])]})
    assert finding_files(named, {**nf, "N9": ["//d/z.c"]}, by_local) == ["//d/a.c", "//d/z.c"]
    counted = f.model_copy(update={"evidence": [Evidence(text="3 caller(s) outside the parsed TUs", nodes=[])]})
    assert finding_files(counted, nf, by_local) == ["//d/a.c"]
    undeclared = f.model_copy(update={"evidence": [Evidence(text="by layer: {'L2: net': 4}")]})
    assert finding_files(undeclared, nf, by_local) is None


def test_comment_scope_follows_the_anchor(board):  # noqa: F811
    from codetortoise.detectors.base import Finding
    from codetortoise.provenance import comment_scope
    why = {"F1": [D + "driver/uart.c"], "F2": [D + "include/hal/regs.h"], "F3": [D + "driver/uart.h"],
           "F4": [D + "hal/regs.c"]}
    b = tag_board(board.model_copy(deep=True), why)
    finding = Finding(id="F1", kind="field_mutation", severity="high", title="uart_send now writes Uart::errors",
                      summary="s", explanation="e", files=[D + "driver/uart.c"],
                      explain_files=[D + "driver/uart.c", D + "service/logger.c"])
    scope = lambda kind, anchor: comment_scope(b, [finding], kind, anchor)  # noqa: E731
    assert scope("line", {"path": D + "service/logger.c", "side": "new", "line": 21}) == [D + "service/logger.c"]
    assert scope("line", {"depot": D + "app/main.c", "cl": 101, "side": "new", "line": 3}) == [D + "app/main.c"]  # M1 shape
    assert scope("function", {"key": next(n.key for n in b.nodes if n.label == "uart_errors")}) == [D + "driver/uart.c"]
    assert scope("function", {"key": "c:@F@not_on_the_board"}) is None
    assert scope("finding", {"kind": "field_mutation", "title": "uart_send now writes Uart::errors"}) == \
        [D + "driver/uart.c", D + "service/logger.c"]                   # what its readers saw, explanation included
    assert scope("chapter", {"level": 2}) == [D + "driver/uart.c", D + "driver/uart.h"]
    everything = scope("review", {})
    assert set(everything) >= {f.path for d in b.about.tree for f in d.files} | {n.path for n in b.nodes}
    assert scope("line", {}) is None
    unknown_why = tag_board(board.model_copy(deep=True), {"F1": [D + "driver/uart.c"]})   # F2-F4 unknown
    assert comment_scope(unknown_why, [finding], "review", {}) is None


def test_a_finding_comment_covers_every_finding_with_that_kind_and_title(board):  # noqa: F811
    from codetortoise.detectors.base import Finding
    from codetortoise.provenance import comment_scope
    twins = [Finding(id=f"F{i}", kind="contract", severity="medium", title="init: new return value(s) -1", summary="s",
                     files=[f"//d/{n}.c"]) for i, n in ((1, "a"), (2, "b"))]
    anchor = {"kind": "contract", "title": "init: new return value(s) -1"}
    assert comment_scope(board, twins, "finding", anchor) == ["//d/a.c", "//d/b.c"]
