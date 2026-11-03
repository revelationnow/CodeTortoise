"""A large change is split into clusters with an overview (spec 2026-10-03-large-change-boards), end to end."""
import pytest
from helpers import make_services

from codetortoise import boardstore
from codetortoise.fixture_large import build_large_fixture
from codetortoise.pipeline import run_review

DESIGN_SECONDS: list[float] = []


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    import time

    from codetortoise import pipeline
    d = tmp_path_factory.mktemp("large")
    fx = build_large_fixture(d)
    svc = make_services(fx, d / "data")
    svc.build_index()
    rid = svc.store.create_review("large", "owner", fx.cls)
    real = pipeline.build_design

    def timed(*a, **k):
        t = time.perf_counter()
        try:
            return real(*a, **k)
        finally:
            DESIGN_SECONDS.append(time.perf_counter() - t)
    pipeline.build_design = timed
    try:
        run_review(rid, svc)
    finally:
        pipeline.build_design = real
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


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    from helpers import make_app
    from test_web import InlineRunner, login
    d = tmp_path_factory.mktemp("largeapi")
    fx = build_large_fixture(d)
    svc = make_services(fx, d / "data")
    svc.build_index()
    app = make_app(svc, InlineRunner(svc))
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": fx.cls}).json()["id"]
    return svc, owner, rid


def test_the_api_serves_the_overview_and_each_cluster_board(api):
    svc, owner, rid = api
    ov = owner.get(f"/api/reviews/{rid}/overview").json()
    assert ov["totals"]["clusters"] == len(ov["clusters"]) == 7 and ov["links"]
    c1 = ov["clusters"][0]["id"]
    b = owner.get(f"/api/reviews/{rid}/board", params={"cluster": c1}).json()
    assert b["cluster"]["id"] == c1 and len(b["nodes"]) <= 30 and all(n["files"] for n in b["nodes"] if n["path"])
    r = owner.get(f"/api/reviews/{rid}/board")                           # split: there is no single board
    assert r.status_code == 404 and "overview" in r.json()["detail"]
    r = owner.get(f"/api/reviews/{rid}/board", params={"cluster": "C99"})
    assert r.status_code == 404 and r.json()["detail"] == "That cluster no longer exists after the re-run."


def test_the_small_fixture_has_no_overview(fx, tmp_path):
    from helpers import make_app
    from test_web import InlineRunner, login
    svc = make_services(fx, tmp_path)
    client = login(make_app(svc, InlineRunner(svc)), "owner")
    rid = client.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    assert client.get(f"/api/reviews/{rid}/board").status_code == 200
    assert client.get(f"/api/reviews/{rid}/overview").status_code == 404
    assert client.get(f"/api/reviews/{rid}/locate", params={"node": "N1"}).json()["cluster"] is None


def test_a_board_no_longer_grows_by_expand_the_neighbours_tab_lists_them_instead(api):
    svc, owner, rid = api
    ov = owner.get(f"/api/reviews/{rid}/overview").json()
    boards = {c["id"]: owner.get(f"/api/reviews/{rid}/board", params={"cluster": c["id"]}).json() for c in ov["clusters"]}
    cid, node = next((cid, n) for cid, b in boards.items() for n in b["nodes"] if n["more_callers"] > 0)
    asked = owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": f"{node['id']}:callers"})
    assert asked.status_code == 200 and asked.json() == boards[cid]
    assert owner.get(f"/api/reviews/{rid}/board", params={"cluster": cid, "expand": "N1:sideways"}).status_code == 200
    assert not hasattr(svc.cfg.analysis, "expand_step")


def test_locate_finds_the_cluster_of_a_node_a_flow_and_a_finding(api):
    svc, owner, rid = api
    ov = owner.get(f"/api/reviews/{rid}/overview").json()
    c = ov["clusters"][1]
    loc = lambda **q: owner.get(f"/api/reviews/{rid}/locate", params=q)          # noqa: E731
    ss = owner.get(f"/api/reviews/{rid}/stories").json()
    assert loc(node=c["nodes"][0]).json() == {"cluster": c["id"], "story": ss["node_story"][c["nodes"][0]]}
    fid = c["finding_ids"][0]
    assert loc(finding=fid).json() == {"cluster": c["id"], "story": ss["finding_story"][fid]}
    flow = owner.get(f"/api/reviews/{rid}/board", params={"cluster": c["id"]}).json()["flows"][0]["id"]
    assert loc(flow=flow).json() == {"cluster": c["id"], "story": ss["flow_story"][flow]}
    assert loc(node="N99999").status_code == 404


def test_explaining_a_flow_updates_the_cluster_board_that_holds_it(tmp_path_factory):
    import json

    import httpx
    from helpers import make_app
    from test_web import InlineRunner, login

    from codetortoise.llm.client import LlmClient

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": []})
        user = json.loads(req.content)["messages"][1]["content"]
        out = ({"what": "regs_a1 now returns -2 and its caller drops it.", "cites": [f"N{i}" for i in range(1, 400)]}
               if "Describe this call flow" in user else {"summary": "s", "risk": "high", "cites": []})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out)}}]})
    d = tmp_path_factory.mktemp("largeai")
    fx = build_large_fixture(d)
    llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    svc = make_services(fx, d / "data", llm=llm)
    svc.cfg.llm.upfront_flows = 0
    svc.build_index()
    owner = login(make_app(svc, InlineRunner(svc)), "owner")
    rid = owner.post("/api/reviews", json={"cls": fx.cls}).json()["id"]
    c3 = owner.get(f"/api/reviews/{rid}/overview").json()["clusters"][2]["id"]
    fl = owner.get(f"/api/reviews/{rid}/board", params={"cluster": c3}).json()["flows"][0]
    assert fl["what_source"] == "template"
    assert owner.post(f"/api/reviews/{rid}/explain", json={"kind": "flow", "target": fl["id"]}).status_code == 202
    after = next(f for f in owner.get(f"/api/reviews/{rid}/board", params={"cluster": c3}).json()["flows"]
                 if f["id"] == fl["id"])
    assert after["what_source"] == "llm" and after["what"].startswith("regs_a1 now returns -2")


def test_the_overview_board_and_locate_need_a_signed_in_user(api):
    from fastapi.testclient import TestClient
    svc, owner, rid = api
    anon = TestClient(owner.app)
    for path, params in ((f"/api/reviews/{rid}/overview", {}), (f"/api/reviews/{rid}/board", {"cluster": "C1"}),
                         (f"/api/reviews/{rid}/locate", {"node": "N1"})):
        assert anon.get(path, params=params).status_code == 401, path


def test_a_large_change_is_told_in_at_most_15_stories_with_small_graphs(api):
    svc, owner, rid = api
    ss = owner.get(f"/api/reviews/{rid}/stories").json()
    shown = [s for s in ss["stories"] if not s["collapsed"]]
    collapsed_row = len(shown) < len(ss["stories"])           # "N more behaviour stories" is one entry
    assert 1 <= len(shown) + collapsed_row <= svc.cfg.analysis.max_stories
    for s in ss["stories"]:
        d = owner.get(f"/api/reviews/{rid}/stories/{s['id']}").json()
        assert d["graph"] is None or len(d["graph"]["nodes"]) <= svc.cfg.analysis.story_graph_nodes
        assert not any(n["label"].startswith("/") or "(/" in n["label"] for n in d["board"]["nodes"])
    assert set(ss["node_story"].values()) <= {s["id"] for s in ss["stories"]}


def test_the_design_stage_holds_its_limits_on_a_large_change(large):
    svc, rid = large
    st = next(s for s in svc.store.list_stages(rid) if s["name"] == "design")
    d = svc.store.get_blob(rid, "reading_design")
    assert st["status"] == "ok" and DESIGN_SECONDS and max(DESIGN_SECONDS) < 1.0
    assert len(d["walks"]) <= 6 and len(d["gates"]) <= 20 and all(len(w["steps"]) <= 40 for w in d["walks"])
    assert all(len(g["lines"]) <= 200 for g in d["gates"])


def _many(n):
    """A change of n functions, each gaining a condition and writing or reading one of 50 fields, in a call chain."""
    from test_stories import _world
    fns, calls, fields = [], [], []
    for i in range(n):
        fns.append((f"fn{i}", f"d{i % 40}/f{i % 7}.c", [f"x{i} = 1;", f"r->f{i % 50} = 1;"],
                    [f"x{i} = 2;", f"if (v{i} > {i}) {{", f"\tr->f{i % 50} = 2;", "\treturn;", "}", f"n{i}();"]))
        calls += [(f"fn{i}", f"fn{i - 1}")] if i else []
        fields.append((f"fn{i}", "Rec", f"f{i % 50}", "write" if i % 2 else "read", "added"))
    return _world(fns, calls=calls, fields=fields)


def _walk_seconds(n):
    import time

    from codetortoise.board import analyse
    from codetortoise.gates import Sources, build_gates
    from codetortoise.reading import build_reading
    from codetortoise.stories import build_stories
    from codetortoise.walks import build_walks
    c = _many(n)
    an = analyse(c)
    ss, det = build_stories(c, analysis=an)
    r, per = build_reading(ss, c, details=det, analysis=an)
    src = Sources(an.x)
    _, branches = build_gates(an.x, ss, r, src)
    best = float("inf")
    for _ in range(3):
        t = time.perf_counter()
        build_walks(an.x, ss, det, r, per, src, branches)
        best = min(best, time.perf_counter() - t)
    return best


def test_the_walk_throughs_grow_with_the_change_not_with_its_square():
    """The walker indexes a change once (phase 1 M7): four times the functions takes about four times as long."""
    assert _walk_seconds(1600) < 7 * _walk_seconds(400)
