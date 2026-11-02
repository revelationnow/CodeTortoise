"""The workspaces one server hosts (spec 2026-10-31 §4–§6, §11, §12)."""
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from helpers import make_config, make_services
from test_web import InlineRunner, login

from codetortoise import workspaces
from codetortoise.config import ConfigError
from codetortoise.services import Services
from codetortoise.sinks import marks, set_mark
from codetortoise.toolchain.libclang import find_libclang
from codetortoise.workspaces import LOCAL, Conflict, Gone, Invalid, Registry


def server(fx, tmp_path, **overrides):
    """A registry as `serve` opens it, building bundles inline."""
    return Registry.open(make_config(fx, tmp_path / "data", **overrides), spawn=lambda fn: fn(),
                         runner_class=InlineRunner)


def fields(root, name="b", **kw):
    return {"name": name, "vcs": "git", "p4port": None, "client": None, "p4user": "owner", "root": str(root),
            "compile_commands": json.dumps("auto"), "build_root": None, "swarm_url": None, "settings": "", **kw}


def test_the_seed_is_registered_from_the_file_and_refreshed_at_each_start(fx, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    [ws] = reg.all()
    assert (ws.id, ws.name, ws.server, ws.owner, ws.seed) == (1, fx.root.name, LOCAL, "owner", True)
    assert ws.ready and ws.svc.index.db_path == tmp_path / "data" / "workspaces" / "1" / "symbols.db"
    assert ws.svc.index.generation() > 0                        # an empty index is built when the bundle loads
    again = server(fx, tmp_path, owner="amy")
    again.load()
    [ws2] = again.all()
    assert (ws2.id, ws2.owner) == (1, "amy") and again.store.get_workspace(1)["p4user"] == "amy"


def test_a_request_right_after_startup_waits_for_its_workspace_to_load(fx, tmp_path):
    reg = Registry.open(make_config(fx, tmp_path / "data"), spawn=lambda fn: threading.Timer(0.3, fn).start(),
                        runner_class=InlineRunner)
    reg.load()
    ws = reg.seed()
    assert ws.reason == workspaces.LOADING and not ws.loaded.is_set()
    reg.settle(ws)
    assert ws.ready and ws.loaded.is_set()


def test_ai_answers_wait_for_a_loading_workspace(fx, tmp_path):
    """Right after a start, the AI panel and an @tortoise question wait for the workspace's bundle as other requests
    do, rather than saying it isn't loaded (final review M6 of spec 2026-10-31)."""
    from test_tortoise import _ask, _reply_to

    from codetortoise.web.app import create_app, make_authenticator
    first = server(fx, tmp_path)
    first.load()
    rid = login(create_app(first, make_authenticator(first)), "owner").post("/api/reviews", json={"cls": [101]}).json()["id"]

    def started(llm):
        reg = Registry.open(make_config(fx, tmp_path / "data"), spawn=lambda fn: threading.Timer(0.3, fn).start(),
                            runner_class=InlineRunner)
        reg.llm = llm
        reg.load()
        return login(create_app(reg, make_authenticator(reg)), "owner")
    class Llm:                                                   # a configured AI that Health finds answering
        def ping(self):
            return True
    assert started(Llm()).get(f"/api/reviews/{rid}/ai").json()["llm"]
    owner = started(None)
    q = _ask(owner, rid, "@tortoise hello")
    assert [r["body"] for r in _reply_to(owner, rid, q["id"])] == ["I can't answer: no AI is configured for CodeTortoise."]


def test_with_no_workspace_the_server_names_both_ways_in(fx, tmp_path):
    with pytest.raises(ConfigError, match="`workspace:` section.*data folder"):
        server(fx, tmp_path, workspace=None).load()
    server(fx, tmp_path).load()                                 # an earlier run stored the seed
    later = server(fx, tmp_path, workspace=None)
    later.load()
    [ws] = later.all()
    assert ws.name == fx.root.name and not ws.seed and ws.ready  # served from its row, editable now


def test_a_workspace_whose_bundle_fails_to_build_is_kept_not_ready_with_the_reason(fx, fx_b, tmp_path, monkeypatch):
    reg = server(fx, tmp_path)
    reg.load()

    def broken(*a, **k):
        raise OSError("compile database unreadable")
    monkeypatch.setattr(workspaces, "build_services", broken)
    ws = reg.add(fields(fx_b.root), "owner")
    assert ws.svc is None and not ws.ready
    assert ws.reason == "could not load: OSError: compile database unreadable"
    assert reg.get(ws.id) is ws and reg.get(1).ready             # the others are untouched


def test_a_failing_hard_check_keeps_a_workspace_not_ready_with_its_reason(fx, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    empty = tmp_path / "empty"
    empty.mkdir()
    ws = reg.add(fields(empty, name="empty"), "owner")
    assert ws.svc is not None and not ws.ready
    assert ws.reason == "compile_commands: no compile database found (auto)"
    assert any(c.name == "compile_commands" and not c.ok for c in ws.checks)


def test_adding_and_editing_check_the_name_root_and_perforce_fields(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    for bad, match in ((fields(fx_b.root, name="a/b"), "name"), (fields(fx_b.root, name="x" * 41), "name"),
                       (fields("relative/b"), "full path"), (fields(fx_b.root, vcs="p4", client="amy-b"), "P4PORT"),
                       (fields(fx_b.root, settings="server: {port: 1}"), "settings")):
        with pytest.raises(Invalid, match=match):
            reg.add(bad, "owner")
    with pytest.raises(Conflict, match=f"a workspace named {fx.root.name} already exists"):
        reg.add(fields(fx_b.root, name=fx.root.name), "owner")
    ws = reg.add(fields(fx_b.root, p4port="second:1666"), "owner")
    assert (ws.id, ws.server, ws.seed, ws.ready) == (2, "second:1666", False, True)
    assert reg.store.get_workspace(2)["created_by"] == "owner" and reg.store.get_workspace(2)["source"] == "ui"
    assert reg.servers() == [LOCAL, "second:1666"] and reg.owners("second:1666") == {"owner"}
    edited = reg.edit(2, fields(fx_b.root, name="b2", p4port="second:1666", p4user="amy"))
    assert reg.get(2) is edited and (edited.name, edited.owner, edited.ready) == ("b2", "amy", True)
    ws.runner._thread.join(10)
    assert not ws.runner._thread.is_alive()                     # the old bundle's queue stopped
    with pytest.raises(Conflict, match="set in tortoise.yaml"):
        reg.edit(1, fields(fx.root, name=fx.root.name))
    with pytest.raises(Conflict, match="set in tortoise.yaml"):
        reg.remove(1)
    with pytest.raises(Gone):
        reg.edit(99, fields(fx_b.root))


def test_an_edit_waits_for_the_workspaces_queue(fx, fx_b, tmp_path, monkeypatch):
    reg = server(fx, tmp_path)
    reg.load()
    ws = reg.add(fields(fx_b.root), "owner")
    monkeypatch.setattr(ws.runner, "busy", lambda: "a review is running in this workspace; try again when it finishes")
    with pytest.raises(Conflict, match="a review is running in this workspace; try again when it finishes"):
        reg.edit(ws.id, fields(fx_b.root, name="b2"))
    with pytest.raises(Conflict, match="a review is running in this workspace"):
        reg.remove(ws.id)
    assert reg.get(ws.id) is ws and reg.store.get_workspace(ws.id)["name"] == "b"


def test_a_workspace_with_reviews_is_kept(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    ws = reg.add(fields(fx_b.root), "owner")
    reg.store.create_review("t", "owner", [101], workspace_id=ws.id)
    with pytest.raises(Conflict, match="has 1 review"):
        reg.remove(ws.id)


def test_a_root_in_another_spelling_is_the_same_root_and_a_removed_workspace_leaves_nothing_behind(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    link = tmp_path / "link"
    link.symlink_to(fx_b.root)
    ws = reg.add(fields(fx_b.root), "owner")
    for spelling in (f"{fx_b.root}/", str(fx_b.root.parent / "x" / ".." / fx_b.root.name), str(link)):
        with pytest.raises(Conflict, match="the workspace b already has the root"):
            reg.add(fields(spelling, name="again"), "owner")
    ws.svc.remember_stripped(["-mfoo"])
    set_mark(reg.store, "Uart::errors", True, ws.svc.scope)
    home = tmp_path / "data" / "workspaces" / str(ws.id)
    assert (home / "symbols.db").exists()
    reg.remove(ws.id)
    assert reg.get(ws.id) is None and reg.store.get_workspace(ws.id) is None and not home.exists()
    again = reg.add(fields(fx_b.root), "owner")
    assert again.id == ws.id + 1                                 # ids never repeat
    assert again.svc.toolchain.strip == set() and marks(reg.store, again.svc.scope) == []
    assert reg.store.kv_get(f"strip_flags:ws{ws.id}") is None and reg.store.kv_get(f"sink_marks:ws{ws.id}") is None


def test_the_first_start_after_the_upgrade_keeps_what_the_single_workspace_server_had(fx, tmp_path):
    data = tmp_path / "data"
    old = make_services(fx, data)                                # today's single-workspace server, same data folder
    rid = old.store.create_review("t", "owner", [101])
    set_mark(old.store, "Uart::errors", True)
    old.remember_stripped(["-mfoo"])
    reg = server(fx, tmp_path)
    reg.load()
    ws = reg.seed()
    review = reg.store.get_review(rid)
    assert review["workspace_id"] == ws.id and reg.for_review(review) is ws
    assert marks(reg.store, ws.svc.scope) == ["Uart::errors"] and "-mfoo" in ws.svc.toolchain.strip
    fetched = data / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2"    # what fetch-libclang leaves
    fetched.parent.mkdir(parents=True)
    fetched.write_bytes(b"")
    (fetched.parent / "clang" / "23" / "include").mkdir(parents=True)
    got = find_libclang(ws.svc.toolchain.cfg, data_dir=ws.svc.toolchain.data_dir)
    assert (got.kind, got.path) == ("fetched", str(fetched))     # still found from the seed's own toolchain folder


def test_the_owners_swarm_ticket_reaches_every_workspace_they_own_on_that_server(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    b = reg.add(fields(fx_b.root, p4port="second:1666"), "owner")
    reg.keep_ticket("second:1666", "owner", "T2")
    assert b.svc.owner_ticket == "T2" and reg.seed().svc.owner_ticket is None
    edited = reg.edit(b.id, fields(fx_b.root, name="b2", p4port="second:1666"))
    assert edited.svc.owner_ticket == "T2"                       # a bundle built later gets it too


def test_sign_in_runs_p4_from_a_perforce_workspace_on_that_server(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    assert reg.login_runner(LOCAL) is None                       # git only: nothing checks a password there
    ws = reg.add(fields(fx_b.root, vcs="p4", p4port="ssl:p4b:1666", client="amy-b", p4user="amy"), "owner")
    assert not ws.ready and ws.reason.startswith("p4 client")    # no Perforce here: the client check fails
    r = reg.login_runner("ssl:p4b:1666")
    assert (r.p4port, r.client, r.cwd, r.user) == ("ssl:p4b:1666", None, str(fx_b.root), None)
    assert ws.svc.p4.user == "amy"                               # its reads run as its owner


def test_only_workspaces_added_in_the_ui_are_held_to_the_toolchain_folders(fx, fx_b, tmp_path, closed):
    """A workspace added in the UI runs compilers only from tortoise.yaml's toolchain folders; tortoise.yaml's own
    workspace is not held to them (final review I3), in the server and in a command-line tool alike."""
    opt = tmp_path / "opt"
    (opt / "bin").mkdir(parents=True)
    listed, elsewhere = str(opt / "bin" / "cc"), str(tmp_path / "elsewhere" / "bin" / "cc")
    (opt / "bin" / "cc").write_text("")                          # one there to check: no one else can change it
    folders = {"data_dir": str(tmp_path / "data"), "toolchain_folders": [str(opt)]}
    reg = server(fx, tmp_path, server=folders)
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    assert b.svc.toolchain.not_run(listed) is None
    assert "outside the toolchain folders" in (b.svc.toolchain.not_run(elsewhere) or "")
    assert reg.seed().svc.toolchain.not_run(elsewhere) is None and reg.seed().svc.toolchain.not_run(listed) is None
    tool = Registry.open(make_config(fx, tmp_path / "data", server=folders)).tool_workspace("b").svc.toolchain
    assert "outside the toolchain folders" in (tool.not_run(elsewhere) or "")
    assert make_config(fx, tmp_path / "data").server.toolchain_folders == ["/usr", "/opt"]


def test_a_workspace_added_in_the_ui_cannot_overlap_a_toolchain_folder(fx, fx_b, tmp_path):
    """Its synced files would count as toolchains that every workspace added in the UI may run (final review I3)."""
    team = tmp_path / "opt" / "team"
    (team / "ws").mkdir(parents=True)
    reg = server(fx, tmp_path, server={"data_dir": str(tmp_path / "data"), "toolchain_folders": [str(team)]})
    reg.load()
    for i, root in enumerate((team / "ws", team, team.parent)):   # inside one, one, around one
        with pytest.raises(Invalid, match=f"root: .*the toolchain folder {team}"):
            reg.add(fields(root, name=f"t{i}"), "owner")
    b = reg.add(fields(fx_b.root), "owner")
    with pytest.raises(Invalid, match="toolchain folder"):
        reg.edit(b.id, fields(team / "ws"))


def test_a_stored_workspace_that_overlaps_a_toolchain_folder_loads_not_ready(fx, fx_b, tmp_path):
    """One stored before its folder was listed waits, with the reason, until its root or the list changes."""
    reg = server(fx, tmp_path)
    reg.load()
    reg.add(fields(fx_b.root), "owner")
    again = server(fx, tmp_path, server={"data_dir": str(tmp_path / "data"), "toolchain_folders": [str(fx_b.root)]})
    again.load()
    b = next(w for w in again.all() if w.name == "b")
    assert "toolchain folder" in (b.reason or "") and b.svc is None


def test_the_seeds_folder_never_counts_as_a_toolchain_folder(fx, fx_b, tmp_path, closed):
    """tortoise.yaml's workspace may sit in a toolchain folder, but its synced files still don't run for a workspace
    added in the UI (final review I3)."""
    opt = tmp_path / "opt"
    (opt / "bin").mkdir(parents=True)
    (opt / "bin" / "cc").write_text("")                          # one there to check: no one else can change it
    folders = {"data_dir": str(tmp_path / "data"), "toolchain_folders": [str(opt), str(fx.root.parent)]}
    reg = server(fx, tmp_path, server=folders)
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    assert "outside the toolchain folders" in (b.svc.toolchain.not_run(str(fx.root / "tools" / "cc")) or "")
    assert b.svc.toolchain.not_run(str(opt / "bin" / "cc")) is None
    tool = Registry.open(make_config(fx, tmp_path / "data", server=folders)).tool_workspace("b").svc.toolchain
    assert "outside the toolchain folders" in (tool.not_run(str(fx.root / "tools" / "cc")) or "")


def test_a_tool_works_on_the_named_workspace_else_the_seed_else_the_only_one(fx, fx_b, tmp_path):
    reg = server(fx, tmp_path)
    reg.load()
    reg.add(fields(fx_b.root), "owner")
    data = tmp_path / "data"
    assert Registry.open(make_config(fx, data)).tool_workspace("b").name == "b"
    assert Registry.open(make_config(fx, data)).tool_workspace(None).seed
    on_b = reg.store.create_review("t", "owner", [101], workspace_id=next(w.id for w in reg.all() if w.name == "b"))
    older = reg.store.create_review("t", "owner", [101])                # made before workspaces: the seed's
    assert Registry.open(make_config(fx, data)).tool_workspace(review=on_b).name == "b"   # final review M7
    assert Registry.open(make_config(fx, data)).tool_workspace(review=older).seed
    bare = make_config(fx, data, workspace=None)
    with pytest.raises(ConfigError, match=rf"several workspaces: name one with --workspace \(b, {fx.root.name}\)"):
        Registry.open(bare).tool_workspace(None)
    with pytest.raises(ConfigError, match=rf"no workspace named nope \(there are: b, {fx.root.name}\)"):
        Registry.open(bare).tool_workspace("nope")


def test_a_git_workspace_is_refused_outside_dev_mode(fx, fx_b, tmp_path):
    """In p4 mode a git workspace labelled with a real server would serve any file under its root to whoever signs in
    there (final review C1); it is a dev-mode fixture (spec 2026-10-31 §5). The seed in tortoise.yaml is the host's own."""
    reg = server(fx, tmp_path, auth={"mode": "p4"})
    reg.load()
    with pytest.raises(Invalid, match="dev mode"):
        reg.add(fields(fx_b.root, p4port="p4:1666"), "owner")
    assert [w.name for w in reg.all()] == [fx.root.name]          # nothing stored
    p4 = reg.add(fields(fx_b.root, vcs="p4", p4port="p4:1666", client="b"), "owner")
    with pytest.raises(Invalid, match="dev mode"):
        reg.edit(p4.id, fields(fx_b.root, p4port="p4:1666"))      # nor does an edit make one


def test_sign_in_never_runs_from_a_root_that_is_not_there(fx, fx_b, tmp_path):
    """A Perforce workspace saved with a missing root (§11) must not lock everyone out of its server (final review
    I1): p4 runs from the root of one whose root is a folder, else from no folder of ours."""
    reg = server(fx, tmp_path)
    reg.load()
    reg.add(fields(tmp_path / "gone", name="a", vcs="p4", p4port="p4:1666", client="a"), "owner")
    assert reg.login_runner("p4:1666").cwd is None
    reg.add(fields(fx_b.root, name="b", vcs="p4", p4port="p4:1666", client="b"), "owner")
    assert reg.login_runner("p4:1666").cwd == str(fx_b.root)


def test_an_edit_vets_its_change_against_the_row_stored_when_it_runs(fx, fx_b, tmp_path):
    """An edit's `check` reads the row once no other change of the workspace runs, so a change vetted against what an
    earlier request read can't undo what was saved meanwhile (final review I3-M7)."""
    reg = server(fx, tmp_path)
    reg.load()
    ws = reg.add(fields(fx_b.root), "owner")
    seen = []
    with reg.guard(ws.id):                                       # another change of it is under way
        t = threading.Thread(target=reg.edit, args=(ws.id, fields(fx_b.root, name="b2")),
                             kwargs={"check": lambda row: seen.append(row["settings"])})
        t.start()
        time.sleep(0.2)
        assert seen == []                                        # it waits for that change
        reg.store.update_workspace(ws.id, fields(fx_b.root, settings="analysis: {sink_threshold: 3}"))
    t.join(30)
    assert seen == ["analysis: {sink_threshold: 3}"] and reg.get(ws.id).name == "b2"


def test_two_rechecks_of_a_workspace_that_could_not_load_build_it_once(fx, fx_b, tmp_path, monkeypatch):
    """Recheck tries a bundle that failed to build again; two at once build it once (final review M2)."""
    reg = server(fx, tmp_path)
    reg.load()
    real = workspaces.build_services

    def broken(*a, **k):
        raise OSError("not yet")
    monkeypatch.setattr(workspaces, "build_services", broken)
    ws = reg.add(fields(fx_b.root), "owner")
    assert ws.reason == "could not load: OSError: not yet"
    builds = []
    monkeypatch.setattr(workspaces, "build_services", lambda *a, **k: builds.append(1) or real(*a, **k))
    with reg.guard(ws.id):                                       # an edit of it, say, is under way
        both = [threading.Thread(target=reg.recheck, args=(ws,)) for _ in range(2)]
        for t in both:
            t.start()
        time.sleep(0.2)
        assert builds == []                                      # each waits for it before trying the bundle again
    for t in both:
        t.join(60)
    assert builds == [1] and ws.ready


def test_a_workspace_removed_while_its_bundle_builds_leaves_no_folder_behind(fx, fx_b, tmp_path):
    """The build under way finds it gone and takes back the folder it made (final review M2)."""
    first = server(fx, tmp_path)
    first.load()
    wid = first.add(fields(fx_b.root), "owner").id
    later = []
    reg = Registry.open(make_config(fx, tmp_path / "data"), spawn=later.append, runner_class=InlineRunner)
    reg.load()                                                   # its bundles build later
    home = tmp_path / "data" / "workspaces" / str(wid)
    reg.remove(wid)
    assert not home.exists()
    for build in later:
        build()
    assert not home.exists() and reg.get(wid) is None


def test_an_edit_or_a_remove_stops_the_index_build_under_way(fx, fx_b, tmp_path, monkeypatch):
    """The first index of a big tree takes long: an owner who saved a wrong setting fixes it, or removes the workspace,
    at once (final review M3)."""
    real = Services.build_index
    under_way = threading.Event()

    def build_index(svc, full=False, cancel=None):              # b's index: long, until it is stopped
        if Path(svc.cfg.workspace.root) != fx_b.root:
            return real(svc, full=full, cancel=cancel)
        under_way.set()
        assert cancel.wait(30)
        return 0
    monkeypatch.setattr(Services, "build_index", build_index)
    reg = Registry.open(make_config(fx, tmp_path / "data"), spawn=lambda fn: fn())     # queues on their own threads
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    assert under_way.wait(10)
    under_way.clear()
    edited = reg.edit(b.id, fields(fx_b.root, name="b2"))      # not refused
    assert b.runner.join(10) and under_way.wait(10)             # its build stopped; the new bundle's started over
    reg.remove(edited.id)
    assert edited.runner.join(10)
    reg.seed().runner.stop()


def test_adding_or_editing_a_workspace_answers_at_once_and_builds_its_bundle_after(fx, fx_b, tmp_path):
    """A slow Perforce server or a deep glob doesn't hold the request: its row shows it loading until its checks have
    run (final review M11)."""
    later = []
    reg = Registry.open(make_config(fx, tmp_path / "data"), spawn=later.append, runner_class=InlineRunner)
    reg.load()
    later.pop()()                                                # the seed's
    ws = reg.add(fields(fx_b.root), "owner")
    assert (ws.reason, ws.svc, ws.loaded.is_set(), len(later)) == (workspaces.LOADING, None, False, 1)
    later.pop()()
    assert ws.ready and ws.svc.index.generation() == 1
    edited = reg.edit(ws.id, fields(fx_b.root, name="b2"))
    assert reg.get(ws.id) is edited and (edited.reason, edited.svc, len(later)) == (workspaces.LOADING, None, 1)
    later.pop()()
    assert edited.ready and edited.svc.index.generation() == 2   # the index caught up, once


def test_moving_the_seed_to_another_perforce_server_with_reviews_is_logged(fx, tmp_path, caplog):
    """Its reviews then show to those signed in to the new server (final review M4): the host decides that in
    tortoise.yaml, and the log says so."""
    reg = server(fx, tmp_path)
    reg.load()
    reg.store.create_review("t", "owner", [101], workspace_id=reg.seed().id)
    moved = {"vcs": "git", "root": str(fx.root), "compile_commands": str(fx.compile_commands), "p4port": "second:1666"}
    with caplog.at_level(logging.WARNING, logger="codetortoise.workspaces"):
        server(fx, tmp_path, workspace=moved).load()
    assert ("the workspace in tortoise.yaml moved from the Perforce server local to second:1666: its 1 review(s) now "
            "show to those signed in there") in caplog.text


def test_two_quick_edits_never_run_two_index_builds_of_the_workspace_at_once(fx, fx_b, tmp_path, monkeypatch):
    """A second save while the first one's bundle still builds waits, too, for the index build the first one stopped
    (final review of branch minors, M1)."""
    real = Services.build_index
    running, most, started, ending = [], [0], threading.Event(), threading.Event()
    lock = threading.Lock()

    def build_index(svc, full=False, cancel=None):              # b's index: long, and a while to end once stopped
        if Path(svc.cfg.workspace.root) != fx_b.root:
            return real(svc, full=full, cancel=cancel)
        with lock:
            running.append(svc)
            most[0] = max(most[0], len(running))
        started.set()
        try:
            cancel.wait(30)
            ending.wait(30)
        finally:
            with lock:
                running.remove(svc)
        return 0
    monkeypatch.setattr(Services, "build_index", build_index)
    later = []
    reg = Registry.open(make_config(fx, tmp_path / "data"), spawn=later.append)     # real queues; bundles built later
    reg.load()
    later.pop()()
    b = reg.add(fields(fx_b.root), "owner")
    later.pop()()
    assert started.wait(10)
    reg.edit(b.id, fields(fx_b.root, name="b2"))                # stops that build; its own bundle builds later
    last = reg.edit(b.id, fields(fx_b.root, name="b3"))          # saved again before that bundle has built
    first, second = later
    t = threading.Thread(target=second)
    t.start()
    time.sleep(0.3)
    assert most[0] == 1 and last.runner is None                  # it waits for the stopped build to end
    ending.set()
    t.join(30)
    first()                                                      # replaced meanwhile: it starts no queue
    assert most[0] == 1 and last.runner is not None and reg.get(b.id) is last
    for w in reg.all():
        w.runner.stop()


def test_a_recheck_that_loads_an_edited_workspace_builds_the_index_its_edit_asked_for(fx, fx_b, tmp_path, monkeypatch):
    """An edit whose bundle could not load, then a Recheck once the host is fixed: the index catches up with the new
    settings (final review of branch minors, M7)."""
    reg = server(fx, tmp_path)
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    assert b.svc.index.generation() == 1
    real = workspaces.build_services

    def broken(*a, **k):
        raise OSError("compile database unreadable")
    monkeypatch.setattr(workspaces, "build_services", broken)
    edited = reg.edit(b.id, fields(fx_b.root, name="b2"))
    assert edited.reason.startswith("could not load")
    monkeypatch.setattr(workspaces, "build_services", real)
    reg.recheck(edited)
    assert edited.ready and edited.svc.index.generation() == 2


def test_an_error_escaping_a_workspaces_checks_is_why_it_isnt_ready(fx, fx_b, tmp_path, monkeypatch):
    """A failure escaping the checks of a bundle built in the background is shown as its reason, so its row never stays
    "loading" (review of branch minors, M11)."""
    reg = server(fx, tmp_path)
    reg.load()

    def broken(svc, deep=False):
        raise RuntimeError("the checks broke")
    monkeypatch.setattr(workspaces, "run_health", broken)
    ws = reg.add(fields(fx_b.root), "owner")
    assert ws.loaded.is_set() and not ws.ready
    assert ws.reason == "could not finish loading: RuntimeError: the checks broke"


def test_an_index_built_for_other_settings_is_rebuilt_when_its_bundle_loads(fx, fx_b, tmp_path):
    """An index records the root, compile databases and scope it was built for, and a bundle whose index was built for
    others rebuilds it: an edit's new settings get indexed even when the server stopped before that build ended (review
    of branch minors, M7). An index from before such records is taken as built for its workspace's settings."""

    class Stopped(InlineRunner):                                 # the server stops before an index build ends
        def submit_index(self):
            pass
    reg = server(fx, tmp_path)
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    other = tmp_path / "other"
    other.mkdir()
    (other / "o.c").write_text("int o(void) { return 0; }\n")
    reg.runner_class = Stopped
    reg.edit(b.id, fields(other))
    again = server(fx, tmp_path)
    again.load()
    index = again.get(b.id).svc.index
    assert index.files() == [str((other / "o.c").resolve())]
    gen = index.generation()
    with sqlite3.connect(index.db_path) as db:
        db.execute("DELETE FROM sym_meta WHERE key='stamp'")
    third = server(fx, tmp_path)
    third.load()
    ws = third.get(b.id)
    assert ws.svc.index.generation() == gen and ws.svc.index.stamp() == ws.svc.index_stamp()


def test_an_index_from_before_stamps_is_taken_only_for_the_root_it_was_built_for(fx, fx_b, tmp_path):
    """An index from before stamps still records the root its last whole build was for: one built for another root is
    rebuilt when its bundle loads, not taken as built for these settings (final review of branch deferred-minors,
    M2)."""

    class Stopped(InlineRunner):                                 # the server stops before an index build ends
        def submit_index(self):
            pass
    reg = server(fx, tmp_path)
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    other = tmp_path / "other"
    other.mkdir()
    (other / "o.c").write_text("int o(void) { return 0; }\n")
    reg.runner_class = Stopped
    reg.edit(b.id, fields(other))                                # its index still holds b's files, built for b's root
    with sqlite3.connect(reg.get(b.id).svc.index.db_path) as db:
        db.execute("DELETE FROM sym_meta WHERE key='stamp'")     # as one from before stamps
    again = server(fx, tmp_path)
    again.load()
    ws = again.get(b.id)
    assert ws.svc.index.files() == [str((other / "o.c").resolve())]
    assert ws.svc.index.stamp() == ws.svc.index_stamp()


def test_an_index_stamped_before_the_stamp_had_a_version_catches_up_once(fx, fx_b, tmp_path):
    """The stamp names its version (final review of branch deferred-minors, recommendation), so a change of what it
    covers is a deliberate catch-up of every index, once: one stamped without it is built again as its bundle loads,
    and only then."""
    reg = server(fx, tmp_path)
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    index = b.svc.index
    assert json.loads(index.stamp())["v"] == 1
    unversioned = json.dumps({k: v for k, v in json.loads(index.stamp()).items() if k != "v"}, sort_keys=True)
    index.set_stamp(unversioned)
    gen = index.generation()
    again = server(fx, tmp_path)
    again.load()
    assert again.get(b.id).svc.index.generation() == gen + 1
    third = server(fx, tmp_path)
    third.load()
    assert third.get(b.id).svc.index.generation() == gen + 1


def test_a_bundle_that_fails_as_it_is_attached_is_closed_and_built_again_by_recheck(fx, fx_b, tmp_path, monkeypatch):
    """An error between a bundle's build and its attach (its queue not starting, say) leaves no index open, and Recheck
    builds the bundle again, as for one that could not load (final review of branch deferred-minors, M3)."""

    class Unstartable(InlineRunner):
        def start(self):
            raise RuntimeError("can't start new thread")
    reg = server(fx, tmp_path)
    reg.load()
    real, built = workspaces.build_services, []
    monkeypatch.setattr(workspaces, "build_services", lambda *a, **k: built.append(real(*a, **k)) or built[-1])
    reg.runner_class = Unstartable
    ws = reg.add(fields(fx_b.root), "owner")
    assert ws.svc is None and ws.reason == "could not load: RuntimeError: can't start new thread"
    with pytest.raises(sqlite3.ProgrammingError):
        built[0].index.generation()                              # closed: nothing else would close it
    reg.runner_class = InlineRunner
    reg.recheck(ws)
    assert ws.ready and len(built) == 2


def test_an_error_after_a_bundle_is_attached_still_catches_its_index_up(fx, fx_b, tmp_path, monkeypatch):
    """An error between a bundle's attach and its checks (reading its index's stamp, say) still queues the index build
    an edit asked for, and Recheck then runs its checks (final review of branch deferred-minors, M3)."""
    reg = server(fx, tmp_path)
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    other = tmp_path / "other"
    other.mkdir()
    (other / "o.c").write_text("int o(void) { return 0; }\n")
    real, calls = Services.index_stamp, []

    def once(svc):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real(svc)
    monkeypatch.setattr(Services, "index_stamp", once)
    edited = reg.edit(b.id, fields(other))
    assert edited.reason == "could not finish loading: OperationalError: database is locked"
    assert edited.svc.index.files() == [str((other / "o.c").resolve())]
    reg.recheck(edited)
    assert reg.get(b.id).reason == "compile_commands: no compile database found (auto)"   # its checks' own verdict now


def _synced(root):
    """A root as its client's sync leaves it: one file and the compile database that builds it."""
    root.mkdir(exist_ok=True)
    (root / "a.c").write_text("int a(void) { return 0; }\n")
    (root / "compile_commands.json").write_text(json.dumps(
        [{"directory": str(root), "file": "a.c", "arguments": ["cc", "-c", "a.c"]}]))


def test_recheck_builds_a_workspace_whose_checks_failed_again(fx, tmp_path):
    """Fix the host and press Recheck (spec 2026-10-31 §11): a workspace whose checks failed is built again, as an edit
    builds it, once no review waits or runs in its queue, so a compile database made since counts (final review of
    branch deferred-minors-2, I2)."""
    reg = server(fx, tmp_path)
    reg.load()
    root = tmp_path / "late"
    root.mkdir()
    (root / "a.c").write_text("int a(void) { return 0; }\n")
    ws = reg.add(fields(root, name="late"), "owner")
    assert ws.reason == "compile_commands: no compile database found (auto)"
    _synced(root)
    rep = reg.recheck(ws)
    now = reg.get(ws.id)
    assert now.ready and rep.ready, now.reason
    assert next(c for c in now.checks if c.name == "compile_commands").ok


def test_an_index_built_before_its_root_was_there_is_built_when_the_workspace_next_loads(fx, tmp_path):
    """A workspace added before its client was synced: its index, built over nothing, isn't taken as built for its
    settings, so the next load builds it (final review of branch deferred-minors-2, M3)."""
    reg = server(fx, tmp_path)
    reg.load()
    root = tmp_path / "unsynced"
    ws = reg.add(fields(root, name="unsynced"), "owner")
    assert ws.svc is not None and ws.reason == f"workspace root: {root}"
    _synced(root)
    again = server(fx, tmp_path)
    again.load()
    now = again.get(ws.id)
    assert now.ready, now.reason
    assert now.svc.index.files() == [str((root / "a.c").resolve())]


def test_a_health_look_that_breaks_leaves_a_ready_workspace_ready(fx, fx_b, tmp_path, monkeypatch):
    """The Health page's look at each toolchain group runs compilers and parses while reviews change the toolchain's
    state: when that look breaks, the load's own checks decide whether the workspace is ready, and a row says what
    broke (final review of branch deferred-minors-2, M1)."""
    reg = server(fx, tmp_path)
    reg.load()
    b = reg.add(fields(fx_b.root), "owner")
    assert b.ready
    real = workspaces.run_health

    def deep_breaks(svc, deep=False):
        if deep:
            raise RuntimeError("dictionary changed size during iteration")
        return real(svc)
    monkeypatch.setattr(workspaces, "run_health", deep_breaks)
    rep = reg.recheck(b, deep=True)
    assert b.ready and rep is not None and rep.ready
    row = next(c for c in rep.checks if c.name == "toolchain groups")
    assert not row.ok and not row.hard
    assert row.detail == ("could not be checked (RuntimeError: dictionary changed size during iteration); "
                          "Recheck tries again")


def test_each_workspace_refused_a_compiler_says_so_in_the_log_once_by_name(fx, fx_b, tmp_path, caplog):
    """Two workspaces whose compiler the toolchain folders refuse each say so in the server's log, naming the
    workspace, once each (review of branch deferred-minors-2, deferred minor)."""
    opt = tmp_path / "opt"
    opt.mkdir()
    elsewhere = str(tmp_path / "elsewhere" / "bin" / "cc")
    reg = server(fx, tmp_path, server={"data_dir": str(tmp_path / "data"), "toolchain_folders": [str(opt)]})
    reg.load()
    other = tmp_path / "other"
    other.mkdir()
    b, c = reg.add(fields(fx_b.root), "owner"), reg.add(fields(other, name="c"), "owner")
    with caplog.at_level(logging.WARNING, logger="codetortoise.toolchain.toolchain"):
        for ws in (b, c, b):
            assert ws.svc.toolchain.refusal(elsewhere)
    said = [r.getMessage() for r in caplog.records if f"compiler {elsewhere} is outside" in r.getMessage()]
    assert [m.split(":")[0] for m in said] == ["workspace b", "workspace c"], said
