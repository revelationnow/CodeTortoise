"""Shared sinks (spec 2026-10-09-shared-sinks §3): which fields a run treats as sinks, and the owner's marks."""
from codetortoise.impact import Edge, ImpactModel, Node, SinkInfo
from codetortoise.sinks import MARKS_KEY, find_sinks, marks, set_mark, why_text


def _im(readers=3, capped=0, label="log_t::buf"):
    """N1 (changed) newly writes field N2; `readers` unchanged functions each read it and write it by name match."""
    nodes = {"N1": Node(id="N1", key="c:w", label="w", status="changed"),
             "N2": Node(id="N2", key="field:buf", kind="field", label=label)}
    edges = [Edge(id="E1", src="N1", dst="N2", kind="writes", status="added")]
    for i in range(readers):
        nid = f"N{3 + i}"
        nodes[nid] = Node(id=nid, key=f"c:r{i}", label=f"r{i}")
        edges.append(Edge(id=f"E{2 + 2 * i}", src=nid, dst="N2", kind="reads"))
        edges.append(Edge(id=f"E{3 + 2 * i}", src=nid, dst="N2", kind="writes", confidence="heuristic"))
    return ImpactModel(nodes=nodes, edges=edges, changed=["N1"], capped_fields={label: capped} if capped else {})


def test_a_field_more_unchanged_functions_touch_than_the_threshold_is_a_sink():
    assert find_sinks(_im(3), 2, [], ()) == {"N2": SinkInfo(field="N2", label="log_t::buf", users=3, why="threshold")}
    assert find_sinks(_im(3), 3, [], ()) == {}          # at the threshold: not a sink; the changed writer never counts


def test_a_removed_access_does_not_count():
    im = _im(2)
    im.nodes["N9"] = Node(id="N9", key="c:gone", label="gone")
    im.edges.append(Edge(id="E99", src="N9", dst="N2", kind="reads", status="removed"))
    assert find_sinks(im, 2, [], ()) == {}


def test_name_matches_over_the_cap_count():
    assert find_sinks(_im(1, capped=40), 20, [], ())["N2"].users == 41


def test_a_threshold_of_zero_turns_it_off():
    assert find_sinks(_im(100), 0, [], ()) == {}


def test_patterns_match_the_record_and_field_or_a_bare_field_case_sensitively():
    assert find_sinks(_im(0), 0, ["log_t::*"], ())["N2"].why == "listed"
    assert find_sinks(_im(0, label="trace_buf"), 0, ["trace_buf"], ())["N2"].why == "listed"
    assert find_sinks(_im(0, label="trace_buf"), 0, ["*::buf"], ()) == {}
    assert find_sinks(_im(0), 0, ["LOG_T::*"], ()) == {}


def test_marked_beats_listed_beats_threshold():
    assert find_sinks(_im(30), 20, ["log_t::*"], {"log_t::buf"})["N2"].why == "marked"
    assert find_sinks(_im(30), 20, ["log_t::*"], ())["N2"].why == "listed"
    assert find_sinks(_im(30), 20, [], {"other::x"})["N2"].why == "threshold"


def test_why_text():
    assert [why_text(SinkInfo(field="N2", label="a::b", users=312, why=w)) for w in ("threshold", "listed", "marked")] \
        == ["312 functions", "in tortoise.yaml", "marked"]


class _KV:
    def __init__(self):
        self.rows = {}

    def kv_get(self, key):
        return self.rows.get(key)

    def kv_put(self, key, obj):
        self.rows[key] = obj


def test_marks_are_a_sorted_set_of_labels_in_the_store():
    kv = _KV()
    assert marks(kv) == []
    assert set_mark(kv, "log_t::buf", True) == ["log_t::buf"]
    assert set_mark(kv, "Uart::errors", True) == ["Uart::errors", "log_t::buf"]
    assert set_mark(kv, "Uart::errors", True) == ["Uart::errors", "log_t::buf"]
    assert set_mark(kv, "log_t::buf", False) == ["Uart::errors"]
    assert kv.rows[MARKS_KEY] == ["Uart::errors"]
    kv.rows[MARKS_KEY] = "junk"
    assert marks(kv) == []
