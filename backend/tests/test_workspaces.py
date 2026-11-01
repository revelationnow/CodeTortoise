"""The workspaces one server hosts (spec 2026-10-31 §4–§6, §11, §12)."""
import json
import logging
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


def test_only_workspaces_added_in_the_ui_are_held_to_the_toolchain_folders(fx, fx_b, tmp_path):
    """A workspace added in the UI runs compilers only from tortoise.yaml's toolchain folders; tortoise.yaml's own
    workspace is not held to them (final review I3), in the server and in a command-line tool alike."""
    opt = tmp_path / "opt"
    (opt / "bin").mkdir(parents=True)
    listed, elsewhere = str(opt / "bin" / "cc"), str(tmp_path / "elsewhere" / "bin" / "cc")
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


def test_the_seeds_folder_never_counts_as_a_toolchain_folder(fx, fx_b, tmp_path):
    """tortoise.yaml's workspace may sit in a toolchain folder, but its synced files still don't run for a workspace
    added in the UI (final review I3)."""
    opt = tmp_path / "opt"
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
