"""File tags on every visible item (spec §14.3)."""
from codetortoise.board import About, AboutDir, AboutFile, Board, BoardEdge, BoardNode, Flow
from codetortoise.provenance import tag_board
from tests.test_board import board  # noqa: F401  (module fixture: the fixture review's board)

D = "//fixture/"


def test_every_item_on_the_fixture_board_is_tagged(board):  # noqa: F811
    b = tag_board(board.model_copy(deep=True))
    items = [*b.nodes, *b.edges, *b.impacts, *b.flows, *b.layers, *b.about.cls,
             *(f for d in b.about.tree for f in d.files)]
    assert items and all(i.files for i in items)
    assert all(f.what_files == f.files for f in b.flows)                  # template text: the flow's own files
    assert b.about.intent_files == sorted(f.path for d in b.about.tree for f in d.files)


def test_fixture_tags_are_exact(board):  # noqa: F811
    b = tag_board(board.model_copy(deep=True))
    fl1 = next(f for f in b.flows if f.id == "FL1")
    assert fl1.files == [D + "app/main.c", D + "driver/uart.c", D + "driver/uart.h", D + "service/logger.c"]
    by_cl = {c.cl: c.files for c in b.about.cls}
    assert by_cl == {101: [D + "driver/uart.c"], 102: [D + "driver/uart.h", D + "hal/regs.c", D + "include/hal/regs.h"]}
    assert [c.file_count for c in b.about.cls] == [1, 3]
    assert next(layer.files for layer in b.layers if layer.name == "driver") == [D + "driver/uart.c", D + "driver/uart.h"]
    imp = next(i for i in b.impacts if i.node == "N8" and i.line == 8)   # uart_init calls hal_write (changed)
    assert imp.files == [D + "driver/uart.c", D + "hal/regs.c"]


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


def test_llm_text_keeps_its_recorded_files_and_is_unknown_when_none_were_recorded():
    b = _tiny(intent_source="llm")
    b.flows[0].what_source = "llm"
    tagged = tag_board(b.model_copy(deep=True))
    assert tagged.flows[0].what_files is None and tagged.about.intent_files is None
    b.flows[0].what_files, b.about.intent_files = ["//d/a.c", "//d/z.c"], ["//d/a.c"]
    tagged = tag_board(b)
    assert tagged.flows[0].what_files == ["//d/a.c", "//d/z.c"] and tagged.about.intent_files == ["//d/a.c"]


def test_boards_stored_before_tags_load_with_counts_and_drift_migrated():
    old = _tiny().model_dump()
    old["about"]["cls"] = [{"cl": 1, "user": "u", "description": "d", "files": 1}]
    old["about"]["drift"] = ["//d/a.c (base #3, workspace #4)"]
    b = tag_board(Board.model_validate(old))
    assert b.about.cls[0].file_count == 1 and b.about.cls[0].files == ["//d/a.c"]
    assert b.about.drift[0].text == "//d/a.c (base #3, workspace #4)" and b.about.drift[0].files == ["//d/a.c"]
