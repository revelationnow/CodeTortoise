"""The Workspaces page's API (spec 2026-10-31 §8, §9, §11)."""
import json

import pytest
from fastapi.testclient import TestClient
from helpers import make_app, make_services
from test_web import InlineRunner, login


@pytest.fixture
def app(fx, tmp_path):
    svc = make_services(fx, tmp_path / "data")
    return make_app(svc, InlineRunner(svc))


def body(root, name="b", **kw):
    return {"name": name, "vcs": "git", "p4user": "owner", "root": str(root), **kw}


def test_an_owner_adds_checks_edits_and_removes_a_workspace(app, fx, fx_b, tmp_path):
    owner, bob = login(app, "owner"), login(app, "bob")
    r = bob.post("/api/workspaces", json=body(fx_b.root))
    assert r.status_code == 403 and r.json()["detail"] == "only the owner of a workspace adds workspaces"
    r = owner.post("/api/workspaces", json=body(f"{fx_b.root}/"))
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["name"], b["server"], b["ready"], b["seed"], b["is_owner"]) == ("b", "local", True, False, True)
    assert b["fields"]["root"] == str(fx_b.root) and b["fields"]["compile_commands"] == "auto"   # stored normalised
    assert {c["name"] for c in b["checks"]} >= {"workspace root", "compile_commands", "libclang"}
    assert owner.post("/api/workspaces", json=body(fx_b.root, name="again")).status_code == 409
    assert owner.post("/api/workspaces", json=body(fx_b.root, name="a/b")).status_code == 422
    r = owner.post("/api/workspaces", json=body(tmp_path, name="x", settings="server: {}"))
    assert r.status_code == 422 and "only toolchain, targets and analysis" in r.json()["detail"]
    assert [(w["name"], w["seed"]) for w in owner.get("/api/workspaces").json()] == [("b", False), (fx.root.name, True)]
    assert all("fields" not in w for w in bob.get("/api/workspaces").json())   # only owners get the settings
    assert owner.put("/api/workspaces/1", json=body(fx.root, name="x")).json()["detail"] == "set in tortoise.yaml"
    assert owner.delete("/api/workspaces/1").json()["detail"] == "set in tortoise.yaml"
    assert bob.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root)).status_code == 403
    e = owner.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root, settings="analysis: {sink_threshold: 3}",
                                                       compile_commands=f"{fx_b.root}/compile_commands.json"))
    assert e.status_code == 200, e.text
    assert e.json()["fields"]["settings"] == "analysis: {sink_threshold: 3}"
    assert e.json()["fields"]["compile_commands"] == f"{fx_b.root}/compile_commands.json"
    assert owner.get(f"/api/workspaces/{b['id']}/sinks").json()["threshold"] == 3     # its own analysis settings
    assert owner.get("/api/workspaces/1/sinks").json()["threshold"] == 20
    assert owner.delete(f"/api/workspaces/{b['id']}").json() == {"ok": True}
    assert [w["name"] for w in owner.get("/api/workspaces").json()] == [fx.root.name]


def test_a_workspace_on_another_server_is_listed_to_those_signed_in_there(app, fx_b):
    owner = login(app, "owner")
    assert owner.post("/api/workspaces", json=body(fx_b.root, p4port="second:1666")).status_code == 200
    amy = TestClient(app)
    amy.post("/api/login", json={"server": "local", "user": "amy", "password": "x"})
    assert [w["server"] for w in amy.get("/api/workspaces").json()] == ["local"]
    amy.post("/api/login", json={"server": "second:1666", "user": "amy", "password": "x"})
    assert [w["server"] for w in amy.get("/api/workspaces").json()] == ["second:1666", "local"]
    # the owner of the seed gets every workspace, to fix or remove one (final review I5)
    assert [w["server"] for w in owner.get("/api/workspaces").json()] == ["second:1666", "local"]


def test_detect_fills_the_add_form_from_what_is_at_a_root(app, tmp_path, monkeypatch):
    owner = login(app, "owner")
    root = tmp_path / "w"
    (root / "build").mkdir(parents=True)
    (root / "build" / "compile_commands.json").write_text(
        json.dumps([{"directory": str(root), "file": "a.c", "arguments": ["cc", "-c", "a.c"]}]))
    (root / ".p4config").write_text("P4PORT=p4.invalid:1666\nP4CLIENT=amy-w\nP4USER=amy\n")
    monkeypatch.setenv("P4CONFIG", ".p4config")
    d = owner.post("/api/workspaces/detect", json={"root": str(root)}).json()
    assert (d["root"], d["p4port"], d["client"], d["p4user"]) == (str(root.resolve()), "p4.invalid:1666", "amy-w", "amy")
    assert d["compile_commands"] == [str((root / "build" / "compile_commands.json").resolve())]
    assert any("p4 client -o amy-w" in n for n in d["notes"])      # no Perforce here: said, not fatal
    assert owner.post("/api/workspaces/detect", json={"root": "w"}).status_code == 422
    assert login(app, "bob").post("/api/workspaces/detect", json={"root": str(root)}).status_code == 403


def test_the_seeds_owner_fixes_or_removes_a_workspace_saved_with_a_mistyped_server_or_user(app, fx, fx_b, tmp_path):
    """A workspace saved with a server or user nobody can sign in as (§11) is edited or removed by the owner of the
    seed, the server's own workspace (final review I5); no one else gains rights on it."""
    owner = login(app, "owner")
    typo = owner.post("/api/workspaces", json=body(fx_b.root, p4port="tpyo:1666", p4user="nobdy")).json()
    rows = {w["name"]: w for w in owner.get("/api/workspaces").json()}
    assert (rows["b"]["is_owner"], rows["b"]["can_manage"], rows["b"]["fields"]["p4port"]) == (False, True, "tpyo:1666")
    assert rows[fx.root.name]["can_manage"]
    carol = owner.post("/api/workspaces", json=body(tmp_path, name="c", p4user="carol")).json()
    c = TestClient(app)
    c.post("/api/login", json={"server": "local", "user": "carol", "password": "x"})
    assert [w["name"] for w in c.get("/api/workspaces").json()] == ["c", fx.root.name]     # not b: not on her servers
    assert c.delete(f"/api/workspaces/{typo['id']}").status_code == 404
    assert not {w["name"]: w for w in c.get("/api/workspaces").json()}[fx.root.name]["can_manage"]
    e = owner.put(f"/api/workspaces/{typo['id']}", json=body(fx_b.root, p4port="second:1666", p4user="owner"))
    assert e.status_code == 200 and (e.json()["server"], e.json()["can_manage"]) == ("second:1666", True), e.text
    assert owner.delete(f"/api/workspaces/{typo['id']}").json() == {"ok": True}
    assert owner.delete(f"/api/workspaces/{carol['id']}").json() == {"ok": True}
