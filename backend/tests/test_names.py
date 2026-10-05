"""Names and neighbours for the review workspace (spec 2026-10-04-review-workspace §4.2–§4.3)."""
from codetortoise.impact import BlastItem, Edge, ImpactModel, Node
from codetortoise.names import cited, names, neighbours


def _im():
    nodes = {
        "N1": Node(id="N1", key="c:@F@send", label="send", file="/w/src/send.c", line=10, status="changed"),
        "N2": Node(id="N2", key="c:@F@flush", label="flush", file="/w/src/log.c", line=3),
        "N3": Node(id="N3", key="c:@F@init", label="init", file="/w/src/init.c", line=7),
        "N4": Node(id="N4", key="c:@F@test_send", label="test_send", file="/w/tests/send_test.c", line=1),
        "N5": Node(id="N5", key="c:@F@hal_write", label="hal_write", file="/w/hal/hal.c", line=20),
        "N6": Node(id="N6", key="field:c:@S@Uart@FI@errors", kind="field", label="Uart::errors"),
    }
    edges = [Edge(id="E1", src="N2", dst="N1", kind="call"), Edge(id="E2", src="N3", dst="N1", kind="call"),
             Edge(id="E3", src="N4", dst="N1", kind="call"), Edge(id="E4", src="N1", dst="N5", kind="virtual"),
             Edge(id="E5", src="N1", dst="N6", kind="writes")]
    blast = [BlastItem(node="N3", hop=1, score=0.9, via="call", path=["N3", "N1"]),
             BlastItem(node="N2", hop=1, score=0.4, via="call", path=["N2", "N1"])]
    return ImpactModel(nodes=nodes, edges=edges, changed=["N1"], blast=blast)


DEPOTS = {"N1": ["//d/src/send.c"], "N2": ["//d/src/log.c"], "N3": ["//d/src/init.c"], "N4": ["//d/tests/send_test.c"],
          "N6": ["//d/src/send.c", "//d/include/uart.h"]}


def test_cited_finds_node_ids_in_text_but_not_finding_or_story_ids():
    assert cited(["`send` (N1) writes N6; see F2 and S1", None, "N12x is not an id, N12 is"]) == {"N1", "N6", "N12"}


def test_names_give_each_node_its_label_kind_depot_path_line_and_story():
    out = names(_im(), ["N1", "N6", "N99"], DEPOTS, {"N1": "S1"})
    assert out == {
        "N1": {"label": "send", "kind": "function", "path": "//d/src/send.c", "line": 10, "story": "S1"},
        "N6": {"label": "Uart::errors", "kind": "field", "path": None, "line": None, "story": None},
    }


def test_neighbours_list_callers_most_affected_first_tests_last_and_callees():
    out = neighbours(_im(), "N1", DEPOTS, {"N1": "S1", "N3": "S2"}, root="/w", limit=20)
    assert out["node"]["label"] == "send" and out["node"]["changed"] is True
    assert [i["label"] for i in out["callers"]["items"]] == ["init", "flush", "test_send"]
    assert out["callers"]["total"] == 3 and out["callers"]["items"][-1]["test"] is True
    assert out["callers"]["items"][0]["story"] == "S2" and out["callers"]["items"][0]["changed"] is False
    assert [i["label"] for i in out["callees"]["items"]] == ["hal_write"] and out["callees"]["items"][0]["path"] is None


def test_neighbours_are_capped_by_the_limit_and_count_them_all():
    out = neighbours(_im(), "N1", DEPOTS, {}, root="/w", limit=1)
    assert [i["label"] for i in out["callers"]["items"]] == ["init"] and out["callers"]["total"] == 3


def test_neighbours_of_an_unknown_node_are_none():
    assert neighbours(_im(), "N99", DEPOTS, {}, root="/w", limit=20) is None
