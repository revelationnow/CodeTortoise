import pytest
from fastapi.testclient import TestClient
from helpers import make_services

from codetortoise import boardstore
from codetortoise.pipeline import JobRunner, run_review
from codetortoise.web.app import create_app, make_authenticator


class InlineRunner(JobRunner):
    """Runs jobs synchronously so tests are deterministic."""

    def submit_review(self, rid, fresh=False):
        run_review(rid, self.svc, fresh=fresh)

    def submit_index(self):
        self.svc.build_index()

    def _dispatch_ai(self, job, fn):
        self._run_ai(job, fn)


class FakeSwarm:
    def __init__(self):
        self.posts = []

    def get_review_for_change(self, cl):
        return {"id": 42, "state": "needsReview", "url": "https://swarm/reviews/42", "votes": {}}

    def create_review(self, cl, desc):
        return {"id": 77, "state": "needsReview", "url": "https://swarm/reviews/77", "votes": {}}

    def post_comment(self, review_id, body):
        self.posts.append((review_id, body))
        return "c1"


@pytest.fixture
def env(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    swarm = FakeSwarm()
    svc.swarm_override = lambda: swarm
    app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
    return svc, app, swarm


def login(app, user):
    c = TestClient(app)
    assert c.post("/api/login", json={"user": user, "password": "x"}).status_code == 200
    return c


def test_auth_required_and_me(env):
    _, app, _ = env
    assert TestClient(app).get("/api/reviews").status_code == 401
    c = login(app, "owner")
    assert c.get("/api/me").json() == {"user": "owner", "is_owner": True, "swarm_ready": True}
    c.post("/api/logout")
    assert c.get("/api/me").status_code == 401


def test_owner_creates_review_others_view_and_comment(env):
    svc, app, _ = env
    owner, bob = login(app, "owner"), login(app, "bob")
    assert bob.post("/api/reviews", json={"cls": [101]}).status_code == 403
    r = owner.post("/api/reviews", json={"cls": [102, 101]})
    assert r.status_code == 200 and r.json()["title"] == "CLs 101, 102"
    rid = r.json()["id"]
    detail = bob.get(f"/api/reviews/{rid}").json()
    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 16
    assert detail["review"]["risk"] == "high"
    # the raw storyboard and impact graph are not served: the board replaced them (spec §14.4)
    assert bob.get(f"/api/reviews/{rid}/storyboard").status_code == 404
    assert bob.get(f"/api/reviews/{rid}/impact").status_code == 404
    found = bob.get(f"/api/reviews/{rid}/findings").json()
    assert len(found) == 6
    fan = next(f for f in found if f["kind"] == "header_fanout")                # paths in the text are workspace-relative
    assert fan["summary"].startswith("Changes in include/") and "{'" not in str([e["text"] for e in fan["evidence"]])
    assert [f["depot"] for f in bob.get(f"/api/reviews/{rid}/files").json()][0] == "//fixture/driver/uart.c"
    ev = bob.get(f"/api/reviews/{rid}/events")
    assert ev.status_code == 200 and ev.text.startswith("data: ")

    c = bob.post(f"/api/reviews/{rid}/comments",
                 json={"body": "why -2?", "anchor_kind": "line", "anchor": {"depot": "//fixture/driver/uart.c", "line": 18}})
    cid = c.json()["id"]
    assert c.json()["author"] == "bob"
    reply = owner.post(f"/api/reviews/{rid}/comments",
                       json={"body": "overflow", "anchor_kind": "line", "anchor": {}, "parent_id": cid})
    assert reply.json()["parent_id"] == cid
    assert owner.patch(f"/api/comments/{cid}", json={"body": "hijack"}).status_code == 403
    assert owner.patch(f"/api/comments/{cid}", json={"resolved": True}).json()["resolved"] is True
    assert bob.delete(f"/api/comments/{reply.json()['id']}").status_code == 403
    assert owner.delete(f"/api/comments/{cid}").status_code == 200
    assert bob.get(f"/api/reviews/{rid}/comments").json() == []


def test_finding_state_owner_only(env):
    _, app, _ = env
    owner, bob = login(app, "owner"), login(app, "bob")
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    assert bob.patch(f"/api/reviews/{rid}/findings/F1", json={"state": "ack"}).status_code == 403
    assert owner.patch(f"/api/reviews/{rid}/findings/F1", json={"state": "ack"}).status_code == 200
    assert owner.get(f"/api/reviews/{rid}/findings").json()[0]["state"] == "ack"
    assert owner.patch(f"/api/reviews/{rid}/findings/F99", json={"state": "ack"}).status_code == 404


def test_swarm_actions(env):
    svc, app, swarm = env
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    cls = owner.get(f"/api/reviews/{rid}").json()["cls"]
    assert cls[0]["swarm"]["id"] == 42  # swarm_read stage used the (fake) client
    assert owner.post(f"/api/reviews/{rid}/cls/101/swarm/create").status_code == 409  # submitted CL
    r = owner.post(f"/api/reviews/{rid}/cls/101/swarm/post", json={})
    assert r.status_code == 200 and swarm.posts[0][0] == 42
    assert "http://tortoise.local:8765/r/" + str(rid) in swarm.posts[0][1]
    assert owner.post(f"/api/reviews/{rid}/cls/101/swarm/post", json={}).status_code == 409
    assert owner.post(f"/api/reviews/{rid}/cls/101/swarm/post", json={"confirm_repeat": True}).status_code == 200
    assert owner.post(f"/api/reviews/{rid}/cls/555/swarm/refresh").status_code == 404


def test_health_and_layer_rename(env):
    svc, app, _ = env
    owner = login(app, "owner")
    svc.cfg.workspace.p4_sources = {"p4port": "P4CONFIG file /w/.p4config"}   # as load_config records it
    h = owner.get("/api/health").json()
    assert h["ready"] is True
    assert h["p4_sources"] == {"p4port": "P4CONFIG file /w/.p4config"}
    assert {c["name"] for c in h["checks"]} >= {"workspace root", "compile_commands", "libclang"}
    assert owner.put("/api/layers/2", json={"name": "Drivers"}).json() == {"2": "Drivers"}
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    names = [layer["name"] for layer in owner.get(f"/api/reviews/{rid}/board").json()["layers"]]
    assert "Drivers" in names and "L2: driver" not in names
    assert login(app, "bob").put("/api/layers/2", json={"name": "x"}).status_code == 403


def test_review_creation_blocked_when_not_ready(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    svc.cdb.entries.clear()  # hard check fails: empty compile DB
    app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
    owner = login(app, "owner")
    assert owner.post("/api/reviews", json={"cls": [101]}).status_code == 409


def test_spa_fallback_and_api_404(env):
    _, app, _ = env
    c = TestClient(app)
    assert c.get("/r/1").status_code == 200
    assert c.get("/api/nope").status_code in (401, 404)


def test_p4_authenticator_rejects_without_runner(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    svc.cfg.auth.mode = "p4"
    auth = make_authenticator(svc)
    assert auth("bob", "pw") is None


def test_owner_login_requests_host_unlocked_ticket_for_swarm(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    svc.cfg.auth.mode = "p4"
    calls = []

    class P4:
        def login_check(self, user, password, all_hosts=False):
            calls.append((user, all_hosts))
            return "TICKET"

    svc.p4 = P4()
    auth = make_authenticator(svc)
    assert auth("owner", "pw") == "TICKET" and auth("bob", "pw") == "TICKET"
    assert calls == [("owner", True), ("bob", False)]


def test_expired_p4_password_is_explained_but_other_failures_stay_generic(fx, tmp_path):
    from codetortoise.vcs.p4runner import P4Error
    svc = make_services(fx, tmp_path)
    svc.cfg.auth.mode = "p4"

    class P4:
        def login_check(self, user, password, all_hosts=False):
            if user == "bob":
                raise P4Error("p4 login failed: Your password has expired, please change your password.")
            raise P4Error("p4 login failed: User carol doesn't exist.")

    svc.p4 = P4()
    app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
    c = TestClient(app)
    r = c.post("/api/login", json={"user": "bob", "password": "x"})
    assert r.status_code == 401 and "expired" in r.json()["detail"] and "p4 passwd" in r.json()["detail"]
    r = c.post("/api/login", json={"user": "carol", "password": "x"})
    assert r.status_code == 401 and r.json()["detail"] == "invalid credentials"


def _review(app):
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    return owner, rid


def test_board_endpoint_serves_the_board_with_layer_renames(env):
    svc, app, _ = env
    owner, rid = _review(app)
    assert owner.get("/api/reviews/999/board").status_code == 404
    board = owner.get(f"/api/reviews/{rid}/board").json()
    assert [f["id"] for f in board["flows"]] == ["FL1", "FL2", "FL3"]
    level = next(l["level"] for l in board["layers"] if l["name"] == "driver")
    owner.put(f"/api/layers/{level}", json={"name": "Drivers"})
    names = {l["level"]: l["name"] for l in owner.get(f"/api/reviews/{rid}/board").json()["layers"]}
    assert names[level] == "Drivers"
    svc.store.put_blob(rid, "board", None)
    r = owner.get(f"/api/reviews/{rid}/board")
    assert r.status_code == 404 and "not built" in r.json()["detail"]


def test_source_endpoint_serves_changed_and_unchanged_files(env):
    svc, app, _ = env
    owner, rid = _review(app)
    bob = login(app, "bob")
    new = bob.get(f"/api/reviews/{rid}/source", params={"path": "//fixture/driver/uart.c", "side": "after"}).json()
    old = bob.get(f"/api/reviews/{rid}/source", params={"path": "//fixture/driver/uart.c", "side": "before"}).json()
    assert new["changed"] and "err" in new["text"] and new["text"] != old["text"]
    ctx = bob.get(f"/api/reviews/{rid}/source", params={"path": "//fixture/service/logger.c"}).json()
    assert not ctx["changed"] and ctx["rev"] == "workspace" and "logger_flush" in ctx["text"]
    assert svc.store.get_blob(rid, "source://fixture/service/logger.c")["text"] == ctx["text"]


@pytest.mark.parametrize("path,status", [("//fixture/../../etc/passwd", 403), ("//other/x.c", 403),
                                         ("//fixture/nope.c", 403)])
def test_source_endpoint_refuses_paths_outside_the_workspace(env, path, status):
    _, app, _ = env
    owner, rid = _review(app)
    assert owner.get(f"/api/reviews/{rid}/source", params={"path": path}).status_code == status


@pytest.mark.parametrize("exc,status", [("SourceBinary", 415), ("SourceTooLarge", 413)])
def test_source_endpoint_maps_unreadable_files(env, monkeypatch, exc, status):
    from codetortoise.vcs import source
    svc, app, _ = env
    owner, rid = _review(app)

    def refuse(depot):
        raise getattr(source, exc)(depot)
    monkeypatch.setattr(svc.source, "read", refuse)
    r = owner.get(f"/api/reviews/{rid}/source", params={"path": "//fixture/service/logger.c"})
    assert r.status_code == status


def test_board_stored_by_an_older_version_gets_current_defaults(env):
    svc, app, _ = env
    owner, rid = _review(app)
    old = svc.store.get_blob(rid, "board")
    del old["about"]["drift"]
    for i in old["impacts"]:
        del i["cause"], i["landing"]
    for f in old["flows"]:
        del f["title"]
    svc.store.put_blob(rid, "board", old)
    b = owner.get(f"/api/reviews/{rid}/board").json()
    assert b["about"]["drift"] == []
    assert all(i["landing"] is False and i["cause"] is None for i in b["impacts"])
    assert len(b["flows"]) == 3
    assert [f["title"] for f in b["flows"]] == ["-2 ignored", "signature changed", "affects uart_errors"]


def test_board_stored_before_file_tags_gets_them_on_load(env):
    svc, app, _ = env
    owner, rid = _review(app)
    old = svc.store.get_blob(rid, "board")
    for item in [*old["nodes"], *old["edges"], *old["impacts"], *old["layers"], *old["about"]["why"],
                 *(f for d in old["about"]["tree"] for f in d["files"])]:
        item.pop("files")
    for f in old["flows"]:
        f.pop("files"), f.pop("what_files")
    for c in old["about"]["cls"]:
        c["files"] = c.pop("file_count")
    old["about"].pop("intent_files")
    svc.store.put_blob(rid, "board", old)
    b = owner.get(f"/api/reviews/{rid}/board").json()
    assert all(n["files"] for n in b["nodes"]) and all(f["files"] == f["what_files"] for f in b["flows"])
    assert [c["file_count"] for c in b["about"]["cls"]] == [1, 3] and all(c["files"] for c in b["about"]["cls"])


def test_session_cookie_is_secure_only_when_https_is_configured(fx, tmp_path):
    from pathlib import Path
    svc = make_services(fx, tmp_path)
    plain = TestClient(create_app(svc, InlineRunner(svc), make_authenticator(svc)))
    r = plain.post("/api/login", json={"user": "anoop", "password": "x"})
    assert "secure" not in r.headers["set-cookie"].lower()
    svc.cfg.server.tls_cert, svc.cfg.server.tls_key = Path("/c.pem"), Path("/c.key")
    tls = TestClient(create_app(svc, InlineRunner(svc), make_authenticator(svc)))
    r = tls.post("/api/login", json={"user": "anoop", "password": "x"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_story_endpoints_serve_the_list_and_each_story(env):
    svc, app, _ = env
    owner, rid = _review(app)
    assert TestClient(app).get(f"/api/reviews/{rid}/stories").status_code == 401
    assert TestClient(app).get(f"/api/reviews/{rid}/stories/S1").status_code == 401
    ss = owner.get(f"/api/reviews/{rid}/stories").json()
    assert ss["summary"] == "2 behaviour stories." and [s["id"] for s in ss["stories"]] == ["S1", "S2"]
    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()
    assert s1["story"]["title"].startswith("`uart_send` can now return -2")
    assert len(s1["graph"]["nodes"]) <= 12 and s1["board"]["flows"]
    assert all(n["path"] is None or n["path"].startswith("//") for n in s1["graph"]["nodes"])
    send = next(n["id"] for n in s1["graph"]["nodes"] if n["label"] == "uart_send")
    asked = owner.get(f"/api/reviews/{rid}/stories/S1", params={"expand": f"{send}:callers"}).json()
    assert asked["graph"] == s1["graph"]                                   # graphs no longer grow by `expand`
    r = owner.get(f"/api/reviews/{rid}/stories/S9")
    assert r.status_code == 404 and r.json()["detail"] == "That story no longer exists after the re-run."
    svc.store.replace_blobs(rid, ["stories"], [boardstore.STORY], {})     # a review run before stories
    for url in (f"/api/reviews/{rid}/stories", f"/api/reviews/{rid}/stories/S1"):
        r = owner.get(url)
        assert r.status_code == 404 and r.json()["detail"] == "this review has no stories: re-run it"


def test_locate_names_the_story_of_a_node_flow_or_finding(env):
    svc, app, _ = env
    owner, rid = _review(app)
    ss = owner.get(f"/api/reviews/{rid}/stories").json()
    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()
    send = next(n["id"] for n in s1["board"]["nodes"] if n["label"] == "uart_send")
    assert owner.get(f"/api/reviews/{rid}/locate", params={"node": send}).json() == {"cluster": None, "story": "S1"}
    fl = ss["stories"][1]["flows"][0]
    assert owner.get(f"/api/reviews/{rid}/locate", params={"flow": fl}).json() == {"cluster": None, "story": "S2"}
    fid = ss["stories"][0]["findings"][0]
    assert owner.get(f"/api/reviews/{rid}/locate", params={"finding": fid}).json()["story"] == "S1"
    assert owner.get(f"/api/reviews/{rid}/locate", params={"node": "N999"}).json() == {"cluster": None, "story": None}


def test_names_give_the_ui_a_name_for_every_node_it_can_show(env):
    svc, app, _ = env
    owner, rid = _review(app)
    assert TestClient(app).get(f"/api/reviews/{rid}/names").status_code == 401
    names = owner.get(f"/api/reviews/{rid}/names").json()
    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()
    send = next(n["id"] for n in s1["board"]["nodes"] if n["label"] == "uart_send")
    assert names[send] == {"label": "uart_send", "kind": "function", "path": "//fixture/driver/uart.c",
                           "line": names[send]["line"], "story": "S1"}
    findings = owner.get(f"/api/reviews/{rid}/findings").json()
    assert {n for f in findings for n in f["nodes"]} <= set(names)
    assert all(n.startswith("N") for n in names) and len(names) < 200        # what the UI shows, not the whole graph


def test_neighbours_list_a_nodes_callers_and_callees(env):
    svc, app, _ = env
    owner, rid = _review(app)
    names = owner.get(f"/api/reviews/{rid}/names").json()
    send = next(k for k, v in names.items() if v["label"] == "uart_send")
    assert TestClient(app).get(f"/api/reviews/{rid}/nodes/{send}/neighbours").status_code == 401
    nb = owner.get(f"/api/reviews/{rid}/nodes/{send}/neighbours").json()
    assert nb["node"]["label"] == "uart_send" and nb["node"]["changed"] is True
    assert "logger_flush" in [i["label"] for i in nb["callers"]["items"]]
    assert nb["callers"]["total"] >= len(nb["callers"]["items"])
    one = owner.get(f"/api/reviews/{rid}/nodes/{send}/neighbours", params={"limit": 1}).json()
    assert len(one["callers"]["items"]) == 1
    own = owner.get(f"/api/reviews/{rid}/nodes/{send}/neighbours", params={"limit": 1, "callers": 50}).json()
    assert len(own["callers"]["items"]) == min(50, own["callers"]["total"]) and len(own["callees"]["items"]) <= 1
    r = owner.get(f"/api/reviews/{rid}/nodes/N99999/neighbours")
    assert r.status_code == 404 and r.json()["detail"] == "no node N99999 in this review"


def test_the_owner_reruns_stories_fresh_and_the_ai_view_shows_tier_1(env):
    from test_pipeline import _one_story_per_cl, _strong
    svc, app, _ = env
    llm = _strong(svc, _one_story_per_cl)
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    calls = len(llm.prompts)
    assert owner.post(f"/api/reviews/{rid}/rerun").json() == {"queued": True}
    assert len(llm.prompts) == calls                                   # the brief was reused
    assert owner.post(f"/api/reviews/{rid}/rerun?fresh=true").json() == {"queued": True}
    assert len(llm.prompts) == 2 * calls                               # fresh: the strong model was asked again
    ai = owner.get(f"/api/reviews/{rid}/ai").json()
    assert ai["strong"] == "big" and ai["tier1"]["budget"] == 40
    assert login(app, "bob").post(f"/api/reviews/{rid}/rerun?fresh=true").status_code == 403


def test_the_reading_endpoint_serves_threads_checks_and_marks_and_the_story_its_tiles(env):
    svc, app, _ = env
    owner, rid = _review(app)
    assert TestClient(app).get(f"/api/reviews/{rid}/reading").status_code == 401
    r = owner.get(f"/api/reviews/{rid}/reading").json()
    assert [t["stories"] for t in r["threads"]] == [["S2", "S1"]] and r["marks"] == {}
    assert r["headline"] == {"text": "Medium risk", "tone": "confirm", "rules_only": True}
    s1 = owner.get(f"/api/reviews/{rid}/stories/S1").json()
    assert s1["reading"]["thread"] == "T1" and s1["reading"]["position"] == 2
    assert {k["kind"] for k in s1["reading"]["checks"]} >= {"result", "reader"}


def test_any_viewer_marks_a_check_and_a_rerun_keeps_drops_or_reopens_it(env):
    from urllib.parse import quote
    svc, app, _ = env
    owner, rid = _review(app)
    bob = login(app, "bob")
    checks = owner.get(f"/api/reviews/{rid}/reading").json()["checks"]
    caller = next(k for k in checks if k["kind"] == "caller")
    reader = next(k for k in checks if k["kind"] == "reader")
    for k in (caller, reader):
        m = bob.post(f"/api/reviews/{rid}/checks/{quote(k['key'], safe='')}/mark").json()
        assert m["user"] == "bob" and m["source_line"] == k["source_line"]
    assert bob.post(f"/api/reviews/{rid}/checks/nope/mark").status_code == 404
    r = owner.get(f"/api/reviews/{rid}/reading").json()
    assert r["marks"][caller["key"]]["user"] == "bob" and not r["marks"][caller["key"]]["changed"]
    t1 = r["threads"][0]
    assert t1["open_checks"] == len(checks) - 2
    assert f"{len(checks) - 2} checks open" in t1["intro"] and r["route"][0]["reason"].startswith(f"{len(checks) - 2} ")
    svc.store.set_mark(rid, reader["key"], "bob", "an older line")             # the line changed since it was marked
    svc.store.set_mark(rid, "caller|gone.c|f|g", "bob", "x")                   # a check the re-run will not find
    owner.post(f"/api/reviews/{rid}/rerun")
    r = owner.get(f"/api/reviews/{rid}/reading").json()
    assert set(r["marks"]) == {caller["key"], reader["key"]}
    assert r["marks"][reader["key"]]["changed"] and not r["marks"][caller["key"]]["changed"]
    assert r["threads"][0]["open_checks"] == len(checks) - 1
    assert bob.delete(f"/api/reviews/{rid}/checks/{quote(caller['key'], safe='')}/mark").json() == {"ok": True}
    assert set(owner.get(f"/api/reviews/{rid}/reading").json()["marks"]) == {reader["key"]}
    c = bob.post(f"/api/reviews/{rid}/comments", json={"body": "fine?", "anchor_kind": "check",
                                                         "anchor": {"key": caller["key"]}})
    assert c.status_code == 200 and c.json()["anchor"] == {"key": caller["key"]}


def test_the_reviews_list_shows_each_reviews_headline(env):
    svc, app, _ = env
    owner, rid = _review(app)
    (item,) = owner.get("/api/reviews").json()
    assert item["headline"] == {"text": "Medium risk", "tone": "confirm", "rules_only": True}
    svc.store.replace_blobs(rid, ["reading", "reading_head"], ["story_reading:"], {})   # a review run before the reading
    assert owner.get("/api/reviews").json()[0]["headline"] is None
    r = owner.get(f"/api/reviews/{rid}/reading")
    assert r.status_code == 404 and r.json()["detail"] == "this review has no reading: re-run it"
    assert owner.get(f"/api/reviews/{rid}/stories/S1").json()["reading"] is None


def test_the_reviews_list_reads_only_each_reviews_small_headline_blob_and_survives_one_it_cannot_read(env):
    from urllib.parse import quote
    svc, app, _ = env
    owner, rid = _review(app)
    r = owner.get(f"/api/reviews/{rid}/reading").json()
    assert "links" not in r                                                    # the browser never uses them
    confirm = [k for k in r["checks"] if k["finding"]]
    for k in confirm:
        owner.post(f"/api/reviews/{rid}/checks/{quote(k['key'], safe='')}/mark")
    after = owner.get(f"/api/reviews/{rid}/reading").json()["headline"]
    svc.store.replace_blobs(rid, ["reading"], [], {})                         # the list never opens the full reading
    assert owner.get("/api/reviews").json()[0]["headline"] == after
    svc.store.put_blob(rid, "reading_head", {"checks": "not a list"})
    rid2 = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    items = {i["id"]: i for i in owner.get("/api/reviews").json()}
    assert items[rid]["headline"] is None and items[rid2]["headline"]


def test_a_mark_on_a_check_judged_no_hazard_survives_a_rerun(env):
    from urllib.parse import quote

    from test_pipeline import _one_story_per_cl, _strong
    svc, app, _ = env
    _strong(svc, _one_story_per_cl)
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    cleared = owner.get(f"/api/reviews/{rid}/reading").json()["cleared"]
    assert cleared
    assert owner.post(f"/api/reviews/{rid}/checks/{quote(cleared[0]['key'], safe='')}/mark").status_code == 200
    owner.post(f"/api/reviews/{rid}/rerun")
    assert set(owner.get(f"/api/reviews/{rid}/reading").json()["marks"]) == {cleared[0]["key"]}


def test_a_file_several_cls_edit_comes_with_who_wrote_each_line(env):
    svc, app, _ = env
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [103, 104, 105]}).json()["id"]
    files = {f["depot"]: f for f in owner.get(f"/api/reviews/{rid}/files").json()}
    logger = files["//fixture/service/logger.c"]["lines"]
    assert logger["wrote"][6] == 105 and logger["over"][6] == 103 and logger["rewritten"] == {"103": {"7": 105}}
    assert [d for d, f in files.items() if "lines" in f] == ["//fixture/service/logger.c"]


def test_read_ticks_are_each_readers_own_looks_fine_ticks_the_check_and_a_rerun_clears_them(env):
    from urllib.parse import quote
    svc, app, _ = env
    owner, rid = _review(app)
    bob = login(app, "bob")
    r = owner.get(f"/api/reviews/{rid}/reading").json()
    story, check = r["order"][0], r["checks"][0]["key"]
    assert TestClient(app).get(f"/api/reviews/{rid}/ticks").status_code == 401
    assert owner.put(f"/api/reviews/{rid}/ticks/story/{story}").json() == {"ok": True}
    assert owner.put(f"/api/reviews/{rid}/ticks/check/{quote(check, safe='')}").status_code == 200
    assert owner.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [story], "checks": [check]}
    assert bob.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": []}      # private to each reader
    other = r["checks"][1]["key"]
    bob.post(f"/api/reviews/{rid}/checks/{quote(other, safe='')}/mark")                    # Looks fine: read by bob
    assert bob.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": [other]}
    bob.delete(f"/api/reviews/{rid}/checks/{quote(other, safe='')}/mark")                  # undoing it keeps the tick
    assert bob.get(f"/api/reviews/{rid}/ticks").json()["checks"] == [other]
    assert owner.delete(f"/api/reviews/{rid}/ticks/story/{story}").json() == {"ok": True}
    assert owner.get(f"/api/reviews/{rid}/ticks").json()["stories"] == []
    bad = owner.put(f"/api/reviews/{rid}/ticks/story/S99")
    assert bad.status_code == 404 and bad.json()["detail"] == "That story or check is not in this review's reading."
    assert owner.put(f"/api/reviews/{rid}/ticks/flow/F1").status_code == 422
    assert owner.delete(f"/api/reviews/{rid}/ticks/story/S99").status_code == 404           # review M4: as PUT
    owner.post(f"/api/reviews/{rid}/rerun")
    assert owner.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": []}
    assert bob.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": []}
    svc.store.replace_blobs(rid, ["reading", "reading_head"], ["story_reading:"], {})        # a review run before the reading
    assert owner.get(f"/api/reviews/{rid}/ticks").json() == {"stories": [], "checks": []}
    assert owner.put(f"/api/reviews/{rid}/ticks/story/{story}").status_code == 404


def test_the_request_log_downloads_as_a_zip_and_the_calls_say_how_many_requests_they_hold(env):
    import io
    import zipfile

    from codetortoise.llm import request_log
    svc, app, _ = env
    rid = svc.store.create_review("t", "owner", [101])
    call = svc.ledger.reserve(rid, None, "threads", "threads", "big")
    svc.ledger.finish(call, "ok")
    request_log.write(svc.store, call, rid, [{"seq": 1, "sent_at": "2026-10-08T10:00:00+00:00", "elapsed_ms": 5,
                                              "url": "/v1/chat/completions", "model": "big", "status": 200, "error": None,
                                              "stop_reason": "stop", "truncated": False, "repair": False,
                                              "max_output_tokens": None, "prompt_tokens": 1, "completion_tokens": 1,
                                              "request": {"model": "big"}, "response": "{}"}])
    c = login(app, "bob")
    [row] = c.get(f"/api/reviews/{rid}/ai/calls").json()
    assert (row["model"], row["requests"]) == ("big", 1)
    r = c.get(f"/api/reviews/{rid}/ai/requests.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert f'filename="review-{rid}-requests.zip"' in r.headers["content-disposition"]
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == [f"call-{call}/1.json"]
    one = c.get(f"/api/reviews/{rid}/ai/requests.zip?call={call}")
    assert f'filename="review-{rid}-call-{call}-requests.zip"' in one.headers["content-disposition"]
    assert c.get(f"/api/reviews/{rid}/ai/requests.zip?call={call + 1}").status_code == 404


def test_the_owner_marks_and_unmarks_shared_sinks_for_every_review(env):
    svc, app, _ = env
    owner, bob = login(app, "owner"), login(app, "bob")
    assert TestClient(app).get("/api/sinks").status_code == 401
    assert bob.get("/api/sinks").json() == {"threshold": 20, "patterns": [], "marked": []}
    assert bob.put("/api/sinks/Uart%3A%3Aerrors").status_code == 403
    assert owner.put("/api/sinks/Uart%3A%3Aerrors").json()["marked"] == ["Uart::errors"]
    assert owner.put("/api/sinks/log_t%3A%3Abuf").json()["marked"] == ["Uart::errors", "log_t::buf"]
    assert bob.delete("/api/sinks/log_t%3A%3Abuf").status_code == 403
    assert owner.delete("/api/sinks/log_t%3A%3Abuf").json()["marked"] == ["Uart::errors"]
    assert svc.store.kv_get("sink_marks") == ["Uart::errors"]
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    sinks = owner.get(f"/api/reviews/{rid}/reading").json()["sinks"]
    assert [(h["label"], h["why"]) for h in sinks] == [("Uart::errors", "marked")]
    assert any(f["sink"] for f in owner.get(f"/api/reviews/{rid}/findings").json())


def test_a_label_with_a_slash_or_percent_is_stored_as_given(env):
    _, app, _ = env
    owner = login(app, "owner")
    assert owner.put("/api/sinks/a%2Fb%3A%3Ac%25d").json()["marked"] == ["a/b::c%d"]
    assert owner.put("/api/sinks/" + "x" * 301).status_code == 422
