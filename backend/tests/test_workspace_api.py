"""The Workspaces page's API (spec 2026-10-31 §8, §9, §11)."""
import json
import logging
import threading

import pytest
from fastapi.testclient import TestClient
from helpers import make_app, make_services
from test_web import InlineRunner, login
from test_workspaces import fields


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
    assert all("fields" not in w and "checks" not in w for w in bob.get("/api/workspaces").json())  # owners' only
    assert {c["name"] for c in owner.get("/api/workspaces").json()[0]["checks"]} >= {"workspace root", "libclang"}
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


def test_only_the_seeds_owner_sets_settings_that_name_programs(app, fx_b, tmp_path):
    """Settings naming a program or library the server runs or loads are the host's (final review I3): only the owner
    of the seed sets or changes them; another owner keeps what is there while editing the rest."""
    owner = login(app, "owner")
    b = owner.post("/api/workspaces", json=body(fx_b.root, p4user="amy")).json()
    amy = login(app, "amy")
    (tmp_path / "c").mkdir()
    clang = "toolchain: {clang: /opt/vendor/bin/clang}"
    for settings in (clang, "toolchain: {libclang: /x/libclang.so}", "toolchain: {search_paths: [/x]}",
                     "toolchain: {query_compilers: all}", "toolchain: {overrides: [{match: 'a/**', clang: /x/cc}]}",
                     "toolchain: {overrides: [{match: 'a/**', libclang: /x/l.so}]}"):
        r = amy.post("/api/workspaces", json=body(tmp_path / "c", name="c", p4user="amy", settings=settings))
        assert r.status_code == 422 and "only the owner of the workspace in tortoise.yaml" in r.json()["detail"], settings
    r = amy.post("/api/workspaces", json=body(tmp_path / "c", name="c", p4user="amy", settings="toolchain: {target: arm}"))
    assert r.status_code == 200, r.text
    assert amy.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root, p4user="amy", settings=clang)).status_code == 422
    assert owner.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root, p4user="amy", settings=clang)).status_code == 200
    kept = f"{clang}\nanalysis: {{sink_threshold: 3}}"
    assert amy.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root, p4user="amy", settings=kept)).status_code == 200
    r = amy.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root, p4user="amy", settings="toolchain: {clang: /x/cc}"))
    assert r.status_code == 422


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


def test_the_sinks_of_a_workspace_that_could_not_load_still_answer(app, fx_b, tmp_path):
    """Marks are store entries, so the sinks section of its Health page works while its bundle can't be built (final
    review M5 of spec 2026-10-31)."""
    owner = login(app, "owner")
    broken = tmp_path / "compile_commands.json"
    broken.write_text("not json")
    b = owner.post("/api/workspaces", json=body(fx_b.root, compile_commands=str(broken))).json()
    assert b["reason"].startswith("could not load")
    sinks = f"/api/workspaces/{b['id']}/sinks"
    assert owner.put(f"{sinks}/rec%3A%3Af").json()["marked"] == ["rec::f"]
    assert owner.get(sinks).json()["marked"] == ["rec::f"]


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


class Recorded(InlineRunner):
    """Remembers the reviews it is handed."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.reviews = []

    def submit_review(self, rid, fresh=False):
        self.reviews.append(rid)
        super().submit_review(rid, fresh)


def test_a_review_started_or_rerun_while_its_workspace_is_edited_goes_to_the_new_queue(fx, fx_b, tmp_path, monkeypatch):
    """Not to the queue the edit stopped, where it would wait for ever (final review M2)."""
    svc = make_services(fx, tmp_path / "data")
    app = make_app(svc, Recorded(svc))
    reg, owner = app.state.registry, login(app, "owner")
    wid = owner.post("/api/workspaces", json=body(fx_b.root)).json()["id"]
    real = reg.guard

    def edited_first(w):                                         # an edit of it runs while the request waits
        monkeypatch.setattr(reg, "guard", real)
        reg.edit(w, fields(fx_b.root))
        return real(w)
    old = reg.get(wid)
    monkeypatch.setattr(reg, "guard", edited_first)
    rid = owner.post("/api/reviews", json={"cls": [101], "workspace_id": wid}).json()["id"]
    assert old.runner.reviews == [] and reg.get(wid).runner.reviews == [rid]
    old = reg.get(wid)
    monkeypatch.setattr(reg, "guard", edited_first)
    assert owner.post(f"/api/reviews/{rid}/rerun").json() == {"queued": True}
    assert old.runner.reviews == [rid] and reg.get(wid).runner.reviews == [rid]     # its start, then the re-run


def test_a_workspace_removed_meanwhile_is_404_to_what_waited_on_it(fx, fx_b, tmp_path, monkeypatch):
    """A review started, or an edit or remove asked for, while another request removes the workspace finds it gone,
    leaving no review behind (final review M2)."""
    svc = make_services(fx, tmp_path / "data")
    app = make_app(svc, InlineRunner(svc))
    reg, owner = app.state.registry, login(app, "owner")
    real = reg.guard

    def removed_first(w):                                        # a remove of it runs while the request waits
        monkeypatch.setattr(reg, "guard", real)
        reg.remove(w)
        return real(w)
    for i, ask in enumerate((lambda w: owner.post("/api/reviews", json={"cls": [101], "workspace_id": w}),
                             lambda w: owner.put(f"/api/workspaces/{w}", json=body(tmp_path / "x", name="x")),
                             lambda w: owner.delete(f"/api/workspaces/{w}"))):
        wid = owner.post("/api/workspaces", json=body(fx_b.root, name=f"b{i}")).json()["id"]
        monkeypatch.setattr(reg, "guard", removed_first)
        r = ask(wid)
        assert r.status_code == 404 and r.json()["detail"] == "workspace not found", r.text
    assert reg.store.list_reviews() == []


def test_a_workspace_with_reviews_keeps_its_perforce_server(app, fx_b, tmp_path, caplog):
    """Its reviews were made on that server's code; moved, they would show to those signed in to another one (final
    review M4). The owner of the workspace in tortoise.yaml may move it, as they move that one in the file, and the log
    says so, as it does for that one (review of branch minors, M5)."""
    owner = login(app, "owner")
    b = owner.post("/api/workspaces", json=body(fx_b.root, p4user="amy")).json()
    c = owner.post("/api/workspaces", json=body(tmp_path, name="c", p4user="amy")).json()
    amy = login(app, "amy")
    assert amy.post("/api/reviews", json={"cls": [101], "workspace_id": b["id"]}).status_code == 200
    moved = body(fx_b.root, p4user="amy", p4port="second:1666")
    r = amy.put(f"/api/workspaces/{b['id']}", json=moved)
    assert r.status_code == 409 and r.json()["detail"].startswith("the workspace b has 1 review(s) on local: it keeps"), r.text
    assert amy.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root, p4user="amy", swarm_url="https://sw")).status_code == 200
    assert amy.put(f"/api/workspaces/{c['id']}", json=body(tmp_path, name="c", p4user="amy", p4port="second:1666")).status_code \
        == 200                                                   # one with no reviews moves
    with caplog.at_level(logging.WARNING, logger="codetortoise.workspaces"):
        assert owner.put(f"/api/workspaces/{b['id']}", json=moved).status_code == 200
    assert "the workspace b moved from the Perforce server local to second:1666: its 1 review(s) now show to those " \
           "signed in there" in caplog.text


def test_a_workspace_renamed_in_the_save_that_moves_it_is_logged_by_both_names(app, fx_b, caplog):
    """The log of a move names the workspace as it was too, when the same save renames it (final review of branch
    deferred-minors, M10)."""
    owner = login(app, "owner")
    b = owner.post("/api/workspaces", json=body(fx_b.root, p4user="amy")).json()
    assert login(app, "amy").post("/api/reviews", json={"cls": [101], "workspace_id": b["id"]}).status_code == 200
    with caplog.at_level(logging.WARNING, logger="codetortoise.workspaces"):
        r = owner.put(f"/api/workspaces/{b['id']}", json=body(fx_b.root, name="b2", p4user="amy", p4port="second:1666"))
    assert r.status_code == 200, r.text
    assert "the workspace b2 (renamed from b) moved from the Perforce server local to second:1666: its 1 review(s) " \
           "now show to those signed in there" in caplog.text


@pytest.mark.parametrize("ask", ["start", "rerun", "rebuild"])
def test_a_request_waiting_for_its_workspace_to_load_holds_up_no_edit_of_it(fx, fx_b, tmp_path, ask):
    """Starting a review, re-running one and Rebuild index wait for a bundle being built outside the workspace's guard,
    so no edit of it waits behind them (review of branch minors, M3); then they act on the bundle loaded last."""
    svc = make_services(fx, tmp_path / "data")
    app = make_app(svc, Recorded(svc))
    reg, owner = app.state.registry, login(app, "owner")
    wid = owner.post("/api/workspaces", json=body(fx_b.root)).json()["id"]
    rid = owner.post("/api/reviews", json={"cls": [101], "workspace_id": wid}).json()["id"]
    builds, waiting, settle = [], threading.Event(), reg.settle
    reg.spawn = builds.append                                    # a bundle builds when the test says
    assert owner.put(f"/api/workspaces/{wid}", json=body(fx_b.root, swarm_url="https://sw")).status_code == 200

    def waits(ws, timeout=120.0):
        waiting.set()
        settle(ws, timeout)
    reg.settle = waits
    url = {"start": "/api/reviews", "rerun": f"/api/reviews/{rid}/rerun",
           "rebuild": f"/api/workspaces/{wid}/index/rebuild"}[ask]
    got = {}
    asked = threading.Thread(target=lambda: got.update(r=owner.post(url, json={"cls": [101], "workspace_id": wid})))
    asked.start()
    assert waiting.wait(10)
    edited = {}
    edit = threading.Thread(target=lambda: edited.update(
        r=login(app, "owner").put(f"/api/workspaces/{wid}", json=body(fx_b.root))))
    edit.start()
    edit.join(5)
    try:
        assert not edit.is_alive()                               # not held behind the request's wait
    finally:
        for build in builds[::-1]:                               # the last edit's bundle first
            build()
        asked.join(10)
        edit.join(10)
    assert edited["r"].status_code == 200, edited["r"].text    # done, not refused (final review of branch
    assert got["r"].status_code == 200, got["r"].text          # deferred-minors, M11)
    if ask != "rebuild":
        assert reg.get(wid).runner.reviews == [got["r"].json()["id"] if ask == "start" else rid]


def test_a_rerun_by_someone_who_no_longer_owns_the_workspace_is_refused(fx, fx_b, tmp_path, monkeypatch):
    """A re-run checks, under the workspace's guard, that whoever asks still owns it: an edit that gives the workspace
    to someone else can land while the re-run waits for the guard (review of branch minors, M10)."""
    svc = make_services(fx, tmp_path / "data")
    app = make_app(svc, Recorded(svc))
    reg, owner = app.state.registry, login(app, "owner")
    wid = owner.post("/api/workspaces", json=body(fx_b.root)).json()["id"]
    rid = owner.post("/api/reviews", json={"cls": [101], "workspace_id": wid}).json()["id"]
    real = reg.guard

    def given_away_first(w):                                     # an edit giving it to amy runs while the re-run waits
        monkeypatch.setattr(reg, "guard", real)
        reg.edit(w, fields(fx_b.root, p4user="amy"))
        return real(w)
    monkeypatch.setattr(reg, "guard", given_away_first)
    r = owner.post(f"/api/reviews/{rid}/rerun")
    assert r.status_code == 403 and r.json()["detail"] == "owner only", r.text
    assert reg.get(wid).runner.reviews == []


def test_a_slip_inside_an_add_edit_or_remove_stays_an_error(app, fx_b, monkeypatch):
    """Only a workspace that isn't there answers 404 "workspace not found": a KeyError from a slip anywhere else in an
    add, an edit or a remove stays the error it is (review of branch minors, M4)."""
    reg, owner = app.state.registry, login(app, "owner")
    wid = owner.post("/api/workspaces", json=body(fx_b.root)).json()["id"]

    def slip(*a, **k):
        raise KeyError("compile_commands")
    monkeypatch.setattr(reg, "_validate", slip)
    with pytest.raises(KeyError):
        owner.post("/api/workspaces", json=body(fx_b.root, name="c"))
    with pytest.raises(KeyError):
        owner.put(f"/api/workspaces/{wid}", json=body(fx_b.root))
    monkeypatch.setattr(reg.store, "kv_delete_scope", slip)
    with pytest.raises(KeyError):
        owner.delete(f"/api/workspaces/{wid}")


def test_an_error_in_a_health_pages_look_is_shown_there_not_as_a_server_error(app, fx_b, monkeypatch):
    """Recheck's own look at a workspace that breaks answers with why, which is then why the workspace isn't ready,
    rather than with a server error (final review of branch deferred-minors, M3); the next look that works clears it."""
    from codetortoise import workspaces
    owner = login(app, "owner")
    b = owner.post("/api/workspaces", json=body(fx_b.root)).json()
    real = workspaces.run_health

    def broken(svc, deep=False):
        raise RuntimeError("the checks broke")
    monkeypatch.setattr(workspaces, "run_health", broken)
    r = owner.get(f"/api/workspaces/{b['id']}/health")
    assert r.status_code == 200, r.text
    assert [c["detail"] for c in r.json()["checks"]] == ["its checks could not run: RuntimeError: the checks broke"]
    assert not next(w for w in owner.get("/api/workspaces").json() if w["id"] == b["id"])["ready"]
    monkeypatch.setattr(workspaces, "run_health", real)
    assert owner.get(f"/api/workspaces/{b['id']}/health").json()["ready"]
