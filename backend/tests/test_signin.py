"""Sign-in per Perforce server, and what each sign-in sees and may do (spec 2026-10-31 §7, §8, §11)."""
import json

import pytest
from fastapi.testclient import TestClient
from helpers import make_app, make_services
from test_web import InlineRunner


@pytest.fixture
def two(fx, fx_b, tmp_path):
    """The fixture's workspace on `local` and a second, b, on second:1666 — both owned by a user named owner."""
    svc = make_services(fx, tmp_path)
    app = make_app(svc, InlineRunner(svc))
    reg = app.state.registry
    b = reg.add({"name": "b", "vcs": "git", "p4port": "second:1666", "client": None, "p4user": "owner",
                 "root": str(fx_b.root), "compile_commands": json.dumps("auto"), "build_root": None,
                 "swarm_url": None, "settings": ""}, "owner")
    assert b.ready
    return app, reg, b


def sign_in(client, server, user):
    r = client.post("/api/login", json={"server": server, "user": user, "password": "x"})
    assert r.status_code == 200 and r.json() == {"server": server, "user": user}, r.text
    return client


def test_one_session_signs_in_to_each_server(two):
    app, reg, b = two
    c = TestClient(app)
    assert c.get("/api/servers").json() == [{"server": "local", "user": None}, {"server": "second:1666", "user": None}]
    r = c.post("/api/login", json={"user": "amy", "password": "x"})
    assert r.status_code == 422 and r.json()["detail"] == "choose a Perforce server"
    assert c.post("/api/login", json={"server": "nowhere:1", "user": "amy", "password": "x"}).status_code == 422
    sign_in(c, "local", "amy")
    sign_in(c, "second:1666", "owner")
    assert c.get("/api/servers").json() == [{"server": "local", "user": "amy"},
                                            {"server": "second:1666", "user": "owner"}]
    assert c.get("/api/me").json() == {"logins": [{"server": "local", "user": "amy"},
                                                  {"server": "second:1666", "user": "owner"}], "owner_of": [b.id]}
    assert c.post("/api/reviews", json={"cls": [101]}).json()["detail"] == "choose a workspace"
    sign_in(c, "local", "owner")                                   # again on a server: replaces that sign-in
    assert c.get("/api/me").json()["owner_of"] == [1, b.id]
    c.post("/api/logout")
    assert c.get("/api/me").status_code == 401                     # sign out ends the whole session


def test_a_review_on_a_server_the_session_isnt_signed_in_to_is_hidden_and_names_its_server(two):
    app, reg, b = two
    both = sign_in(sign_in(TestClient(app), "local", "owner"), "second:1666", "owner")
    here = both.post("/api/reviews", json={"workspace_id": 1, "cls": [101]}).json()["id"]
    there = both.post("/api/reviews", json={"workspace_id": b.id, "cls": [101]}).json()["id"]
    rows = {r["id"]: r["workspace"] for r in both.get("/api/reviews").json()}
    assert rows == {here: {"id": 1, "name": reg.get(1).name, "server": "local"},
                    there: {"id": b.id, "name": "b", "server": "second:1666"}}
    amy = sign_in(TestClient(app), "local", "amy")
    assert [r["id"] for r in amy.get("/api/reviews").json()] == [here]
    for path in ("", "/stories", "/reading", "/findings", "/comments", "/ai", "/files", "/names"):
        r = amy.get(f"/api/reviews/{there}{path}")
        assert r.status_code == 401 and r.json() == {"detail": "sign in required", "server": "second:1666"}, path
    comment = both.post(f"/api/reviews/{there}/comments", json={"body": "hi", "anchor_kind": "review"}).json()
    r = amy.delete(f"/api/comments/{comment['id']}")
    assert r.status_code == 401 and r.json()["server"] == "second:1666"
    assert amy.patch(f"/api/comments/{comment['id']}", json={"resolved": True}).status_code == 401
    assert amy.get("/api/reviews/999").status_code == 404
    d = amy.get(f"/api/reviews/{here}").json()
    assert d["workspace"] == {"id": 1, "name": reg.get(1).name, "server": "local"}
    assert d["viewer"] == {"user": "amy", "is_owner": False}
    assert both.get(f"/api/reviews/{there}").json()["viewer"] == {"user": "owner", "is_owner": True}


def test_owner_rights_follow_the_sign_in_on_the_workspaces_own_server(two):
    app, reg, b = two
    owner_b = sign_in(TestClient(app), "second:1666", "owner")
    rid = owner_b.post("/api/reviews", json={"workspace_id": b.id, "cls": [101]}).json()["id"]
    c = sign_in(sign_in(TestClient(app), "local", "owner"), "second:1666", "mallory")   # owner here, mallory there
    assert c.get("/api/me").json()["owner_of"] == [1]
    assert c.get(f"/api/reviews/{rid}").json()["viewer"] == {"user": "mallory", "is_owner": False}
    for method, path, payload in (
            ("POST", "/api/reviews", {"workspace_id": b.id, "cls": [101]}),
            ("POST", f"/api/reviews/{rid}/rerun", None),
            ("PUT", f"/api/reviews/{rid}/ai/budget", {"budget": 5}),
            ("PUT", f"/api/reviews/{rid}/ai/rounds", {"rounds": 3}),
            ("PATCH", f"/api/reviews/{rid}/findings/F1", {"state": "ack"}),
            ("POST", f"/api/reviews/{rid}/cls/101/swarm/refresh", None),
            ("GET", f"/api/workspaces/{b.id}/health", None),
            ("POST", f"/api/workspaces/{b.id}/index/rebuild", None),
            ("GET", f"/api/workspaces/{b.id}/sinks", None),
            ("PUT", f"/api/workspaces/{b.id}/sinks/x%3A%3Ay", None)):
        r = c.request(method, path, json=payload)
        assert r.status_code == 403, (method, path, r.status_code)
    assert c.get("/api/workspaces/1/health").status_code == 200    # where they are the owner, they act as one


def test_a_workspace_that_isnt_ready_refuses_new_reviews_and_reruns_but_its_reviews_stay_readable(two):
    app, reg, b = two
    c = sign_in(TestClient(app), "second:1666", "owner")
    rid = c.post("/api/reviews", json={"workspace_id": b.id, "cls": [101]}).json()["id"]
    b.reason = "compile_commands: no compile database found (auto)"          # its checks failed since
    r = c.post("/api/reviews", json={"workspace_id": b.id, "cls": [102]})
    assert r.status_code == 409 and r.json()["detail"] == (
        "the workspace b is not ready: compile_commands: no compile database found (auto); see its Health")
    assert c.post(f"/api/reviews/{rid}/rerun").status_code == 409
    assert c.get(f"/api/reviews/{rid}/stories").status_code == 200


def test_a_review_link_opened_with_no_session_names_its_server(two):
    """A visitor with no session at all is told the review's server too, so its sign-in opens in place (spec
    2026-10-31 §9; final review I2)."""
    app, reg, b = two
    both = sign_in(sign_in(TestClient(app), "local", "owner"), "second:1666", "owner")
    there = both.post("/api/reviews", json={"workspace_id": b.id, "cls": [101]}).json()["id"]
    for path in ("", "/stories", "/comments"):
        r = TestClient(app).get(f"/api/reviews/{there}{path}")
        assert r.status_code == 401 and r.json() == {"detail": "sign in required", "server": "second:1666"}, path
    assert TestClient(app).get("/api/reviews").status_code == 401        # the list still needs a sign-in


def test_each_sign_in_gets_a_new_session_token_that_carries_the_others(two):
    """A token planted in a browser before a sign-in gains nothing from it (session fixation; final review I4)."""
    app, reg, b = two
    c = sign_in(TestClient(app), "local", "amy")
    first = c.cookies.get("ct_session")
    sign_in(c, "second:1666", "owner")
    assert c.cookies.get("ct_session") != first
    assert c.get("/api/me").json()["logins"] == [{"server": "local", "user": "amy"},
                                                 {"server": "second:1666", "user": "owner"}]
    planted = TestClient(app)
    planted.cookies.set("ct_session", first)
    assert planted.get("/api/me").status_code == 401             # the old token signs nobody in
