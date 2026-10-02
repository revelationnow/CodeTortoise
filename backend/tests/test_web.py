import pytest
from fastapi.testclient import TestClient
from helpers import make_services

from codetortoise.pipeline import JobRunner, run_review
from codetortoise.web.app import create_app, make_authenticator


class InlineRunner(JobRunner):
    """Runs jobs synchronously so tests are deterministic."""

    def submit_review(self, rid):
        run_review(rid, self.svc)

    def submit_index(self):
        self.svc.build_index()


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
    assert detail["review"]["status"] == "degraded" and len(detail["stages"]) == 11
    assert bob.get(f"/api/reviews/{rid}/storyboard").json()["storyboard"]["risk"] == "high"
    assert len(bob.get(f"/api/reviews/{rid}/impact").json()["nodes"]) > 5
    assert len(bob.get(f"/api/reviews/{rid}/findings").json()) == 6
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
    _, app, _ = env
    owner = login(app, "owner")
    h = owner.get("/api/health").json()
    assert h["ready"] is True and {c["name"] for c in h["checks"]} >= {"workspace root", "compile_commands", "libclang"}
    assert owner.put("/api/layers/2", json={"name": "Drivers"}).json() == {"2": "Drivers"}
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    names = [c["name"] for c in owner.get(f"/api/reviews/{rid}/storyboard").json()["storyboard"]["chapters"]]
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
    assert [f["title"] for f in b["flows"]] == ["affects uart_errors", "-2 ignored", "signature changed"]


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
