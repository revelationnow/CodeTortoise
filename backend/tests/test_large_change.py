"""A large change is split into clusters with an overview (spec 2026-10-03-large-change-boards), end to end."""
import pytest
from helpers import make_services

from codetortoise import boardstore
from codetortoise.fixture_large import build_large_fixture
from codetortoise.pipeline import run_review


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    d = tmp_path_factory.mktemp("large")
    fx = build_large_fixture(d)
    svc = make_services(fx, d / "data")
    svc.build_index()
    rid = svc.store.create_review("large", "owner", fx.cls)
    run_review(rid, svc)
    return svc, rid


def test_a_large_change_gets_an_overview_and_a_board_per_cluster(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    assert ov is not None and boardstore.board(svc.store, rid) is None              # no single board
    assert {c.name for c in ov.clusters} == {"app/telemetry", "drv/dma", "drv/uart", "hal/regs", "svc/logger",
                                             "svc/stats", "tests"}
    assert [c.id for c in ov.clusters] == [f"C{i}" for i in range(1, len(ov.clusters) + 1)]
    assert ov.clusters[-1].name == "tests"                                          # least risky last
    boards = boardstore.boards(svc.store, rid)
    assert set(boards) == {c.id for c in ov.clusters}
    assert all(len(b.nodes) <= 30 for b in boards.values())
    stage = next(s for s in svc.store.list_stages(rid) if s["name"] == "board")
    assert stage["status"] == "ok" and "7 cluster board(s)" in stage["message"]


def test_every_changed_function_and_flow_is_on_exactly_one_board(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    im = svc.store.get_blob(rid, "impact")
    homes = [n for c in ov.clusters for n in c.nodes]
    assert sorted(homes) == sorted(im["changed"]) and len(homes) == len(set(homes))
    flows = [f.id for b in boardstore.boards(svc.store, rid).values() for f in b.flows]
    assert len(flows) == len(set(flows)) == ov.totals["flows"]
    node_cluster = svc.store.get_blob(rid, "node_cluster")
    assert all(node_cluster[n] == c.id for c in ov.clusters for n in c.nodes)


def test_cluster_boards_mark_visitors_and_link_clusters(large):
    svc, rid = large
    ov = boardstore.overview(svc.store, rid)
    regs = next(c for c in ov.clusters if c.name == "hal/regs")
    b = boardstore.board(svc.store, rid, regs.id)
    assert b.cluster.id == regs.id and b.cluster.name == "hal/regs"
    visitors = [n for n in b.nodes if n.home]
    assert visitors and all(n.home != regs.id for n in visitors)
    assert {n.label for n in b.nodes if n.change and not n.home} == {"regs_a1", "regs_a2", "regs_a3", "regs_b1",
                                                                     "regs_b2"}
    uart = next(c for c in ov.clusters if c.name == "drv/uart")
    assert any(l.src == uart.id and l.dst == regs.id and l.calls > 0 for l in ov.links)      # uart calls into regs
    assert {f.path.split("/")[-2] for d in b.about.tree for f in d.files} == {"regs"}         # its own files only


def test_nodes_with_neighbours_off_the_board_say_how_many(large):
    svc, rid = large
    boards = boardstore.boards(svc.store, rid)
    assert any(n.more_callers > 0 for b in boards.values() for n in b.nodes)
