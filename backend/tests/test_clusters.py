"""Clusters of a large change (spec 2026-10-03-large-change-boards §2), on synthetic impact graphs."""
from types import SimpleNamespace

from codetortoise.board import is_test_path
from codetortoise.clusters import cluster_change
from codetortoise.detectors.base import Finding
from codetortoise.impact import Edge, ImpactModel, Node


class G:
    """A tiny impact graph: functions by file, changed or not, with call and field edges."""

    def __init__(self):
        self.im = ImpactModel()
        self.flows = []

    def fn(self, label, file, changed=True, layer=None, line=None):
        nid = f"N{len(self.im.nodes) + 1}"
        self.im.nodes[nid] = Node(id=nid, key=f"c:{label}", label=label, file=f"/ws/{file}", layer=layer,
                                  line=line or len(self.im.nodes) + 1, status="changed" if changed else "unchanged")
        if changed:
            self.im.changed.append(nid)
        return nid

    def field(self, label):
        nid = f"N{len(self.im.nodes) + 1}"
        self.im.nodes[nid] = Node(id=nid, key=f"field:{label}", label=label, kind="field")
        return nid

    def edge(self, src, dst, kind="call", status="unchanged"):
        self.im.edges.append(Edge(id=f"E{len(self.im.edges) + 1}", src=src, dst=dst, kind=kind, status=status))

    def flow(self, cause, *path):
        f = SimpleNamespace(id=f"FL{len(self.flows) + 1}", path=[*path, cause] if cause not in path else list(path),
                            cause=cause)
        self.flows.append(f)
        return f

    def run(self, findings=(), **kw):
        kw.setdefault("min_changed", 1)
        return cluster_change(self.im, self.flows, list(findings), is_test=self.is_test, **kw)

    def is_test(self, nid):
        return is_test_path(self.im.nodes[nid].file[len("/ws/"):]) if self.im.nodes[nid].file else False


def members(res):
    return sorted(sorted(c.members) for c in res.clusters)


def test_changed_code_joins_by_calls_and_shared_fields_but_not_by_a_common_helper():
    g = G()
    log = g.fn("log", "util/log.c", changed=False)
    a, b = g.fn("uart_send", "drv/uart.c"), g.fn("uart_write", "drv/uart.c")
    c, d = g.fn("logger_flush", "svc/logger.c"), g.fn("logger_put", "svc/logger.c")
    buf = g.field("Logger::buf")
    g.edge(a, b)
    g.edge(c, buf, "writes", "added")
    g.edge(d, buf, "reads", "removed")
    for n in (a, b, c, d):
        g.edge(n, log)                                       # everyone calls the logger: no join
    assert members(g.run()) == sorted([sorted([a, b]), sorted([c, d])])


def test_only_field_accesses_the_change_added_or_removed_join_code_and_are_required():
    g = G()
    a, b = g.fn("uart_send", "drv/uart.c"), g.fn("logger_put", "svc/logger.c")
    cfg, buf = g.field("Uart::cfg"), g.field("Logger::buf")
    g.edge(a, cfg, "reads")
    g.edge(b, cfg, "reads")                                  # both read it, as they did before the change
    g.edge(a, buf, "writes", "added")
    res = g.run()
    assert members(res) == sorted([[a], [b]])
    send = next(c for c in res.clusters if a in c.members)
    assert buf in send.required and cfg not in send.required


def test_changed_test_code_is_its_own_cluster():
    g = G()
    a = g.fn("uart_send", "drv/uart.c")
    t = g.fn("test_uart_send", "tests/test_uart.c")
    g.edge(t, a)
    res = g.run()
    assert members(res) == sorted([[a], [t]])
    assert next(c for c in res.clusters if t in c.members).test is True


def test_a_cluster_over_the_budget_splits_by_directory_then_packs_a_file():
    g = G()
    chain = [g.fn(f"d{i}", "drv/a.c") for i in range(20)] + [g.fn(f"s{i}", "svc/b.c") for i in range(20)]
    for x, y in zip(chain, chain[1:], strict=False):
        g.edge(x, y)                                          # one connected group of 40
    res = g.run()
    assert [len(c.members) for c in sorted(res.clusters, key=lambda c: c.name)] == [20, 20]
    one = G()
    fns = [one.fn(f"f{i}", "drv/a.c", line=i + 1) for i in range(40)]
    for x, y in zip(fns, fns[1:], strict=False):
        one.edge(x, y)
    packed = one.run()
    assert sorted(len(c.members) for c in packed.clusters) == [10, 30]
    assert all(len(c.required) <= 30 for c in packed.clusters)


def test_files_share_a_board_while_they_fit():
    g = G()
    fns = [g.fn(f"{f}{i}", f"drv/{f}.c") for f in "abc" for i in range(12)]
    for x, y in zip(fns, fns[1:], strict=False):
        g.edge(x, y)                                          # one group of 36 in three files of 12
    assert sorted(len(c.members) for c in g.run().clusters) == [12, 24]


def test_one_function_with_too_many_flows_is_split_into_flow_groups():
    g = G()
    f = g.fn("uart_send", "drv/uart.c")
    for i in range(20):
        g.flow(f, g.fn(f"caller{i}", "app/x.c", changed=False), g.fn(f"top{i}", "app/y.c", changed=False))
    res = g.run()
    parts = sorted(res.clusters, key=lambda c: c.part)
    assert [c.part for c in parts] == [(1, 2), (2, 2)]
    assert [len(c.required) <= 30 for c in parts] == [True, True]
    assert sorted(fid for c in parts for fid in c.flows) == sorted(fl.id for fl in g.flows)   # each flow once
    assert parts[0].members == [f] and parts[1].members == [] and res.home[f] == parts[0].id
    assert parts[0].name.endswith("uart_send (1 of 2)") and parts[1].name.endswith("uart_send (2 of 2)")


def test_small_clusters_merge_into_the_nearest_directory_but_not_across_top_directories():
    g = G()
    it = [g.fn(f"t{i}", "tests/iter/t.c") for i in range(4)]
    src = [g.fn(f"s{i}", "src/a.c") for i in range(4)]
    for chain in (it, src):
        for x, y in zip(chain, chain[1:], strict=False):
            g.edge(x, y)
    p, q = g.fn("pack_t", "tests/pack/p.c"), g.fn("graph_t", "tests/graph/g.c")
    z = g.fn("fuzz", "fuzzers/f.c")
    assert members(g.run(min_changed=3)) == sorted([sorted([*it, p, q]), sorted(src), [z]])


def test_small_clusters_merge_within_a_directory_first():
    g = G()
    a, b, c = g.fn("a", "drv/x.c"), g.fn("b", "drv/x.c"), g.fn("c", "drv/y.c")
    z = g.fn("z", "svc/z.c")
    g.edge(b, c)
    res = g.run(min_changed=3)
    assert members(res) == sorted([sorted([a, b, c]), [z]])


def test_too_many_clusters_merge_and_say_how_many():
    g = G()
    for i in range(5):
        g.fn(f"f{i}", f"d{i}/x.c")
    res = g.run(max_clusters=3)
    assert len(res.clusters) == 3 and res.merged_over_limit == 2
    assert sorted(m for c in res.clusters for m in c.members) == sorted(g.im.changed)


def test_names_order_ids_and_placement():
    g = G()
    a, b = g.fn("uart_send", "drv/uart/uart.c", layer=1), g.fn("uart_init", "drv/uart/uart.c", layer=1)
    c = g.fn("logger_flush", "svc/logger/log.c", layer=2)
    d = g.fn("regs_write", "drv/uart/regs.c", layer=0)
    g.edge(a, b)
    g.edge(a, d)
    f1 = Finding(id="F1", kind="contract", severity="high", title="t", nodes=[c], evidence=[], summary="s")
    f2 = Finding(id="F2", kind="contract", severity="medium", title="t", nodes=[a], evidence=[], summary="s")
    res = g.run(findings=[f2, f1])
    assert [(c_.id, c_.name, c_.risk) for c_ in res.clusters] == [("C1", "svc/logger", "high"), ("C2", "drv/uart", "medium")]
    uart = res.clusters[1]
    assert uart.level == 1 and uart.also == [0] and uart.findings == ["F2"]
    assert res.home[a] == "C2" and res.home[c] == "C1"


def test_two_clusters_in_one_directory_are_told_apart_by_their_main_function():
    g = G()
    a, b = g.fn("uart_send", "drv/uart.c"), g.fn("uart_tx", "drv/uart.c")
    c, d = g.fn("uart_init", "drv/uart.c"), g.fn("uart_cfg", "drv/uart.c")
    g.edge(a, b)
    g.edge(c, d)
    names = sorted(c_.name for c_ in g.run(min_changed=1).clusters)
    assert names[0].startswith("drv · ") and names[1].startswith("drv · ") and names[0] != names[1]


def test_a_cluster_spanning_top_directories_is_named_by_them():
    g = G()
    a, b = g.fn("rt_write", "deps/reftable/basics.c"), g.fn("refdb_write", "src/libgit2/refdb.c")
    g.edge(b, a)
    assert [c.name for c in g.run().clusters] == ["deps/reftable + src/libgit2"]


def test_unchanged_nodes_on_a_flow_live_with_their_directory():
    g = G()
    a = g.fn("uart_send", "drv/uart.c")
    s = g.fn("logger_put", "svc/logger.c")
    land = g.fn("logger_flush", "svc/logger.c", changed=False)
    g.flow(a, land)
    res = g.run()
    by_member = {m: c.id for c in res.clusters for m in c.members}
    assert res.home[land] == by_member[s]                    # a visitor on drv's board, at home with svc's code
    assert land in next(c for c in res.clusters if a in c.members).required


def test_parts_in_different_directories_never_share_a_board():
    g = G()
    fns = [g.fn(f"a{i}", "app/x.c") for i in range(12)] + [g.fn(f"d{i}", "drv/y.c") for i in range(12)]
    fns += [g.fn(f"s{i}", "svc/z.c") for i in range(12)]
    for x, y in zip(fns, fns[1:], strict=False):
        g.edge(x, y)                                          # 36 in three top directories: three boards
    assert sorted(c.name for c in g.run().clusters) == ["app", "drv", "svc"]


def test_one_function_touching_too_many_fields_is_one_cluster_not_a_part():
    g = G()
    f = g.fn("pcre_compile2", "deps/pcre.c")
    for i in range(40):
        g.edge(f, g.field(f"compile_data::f{i}"), "writes", "added")
    g.flow(f, g.fn("caller", "src/regexp.c", changed=False))
    (c,) = g.run().clusters
    assert c.part is None and c.members == [f] and c.name == "deps" and len(c.flows) == 1
