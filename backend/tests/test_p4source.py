import marshal

import pytest

from codetortoise.vcs.p4runner import P4Error, P4Runner, unmarshal_all
from codetortoise.vcs.p4source import P4Source
from codetortoise.vcs.source import SourceError


class FakeP4:
    """Stands in for P4Runner: canned `run` records and file contents."""

    def __init__(self, describe, files, have=None, where_root="/ws"):
        self.describe = describe
        self.files = files
        self.have = have or {}
        self.where_root = where_root
        self.calls = []

    def run(self, command, *args):
        self.calls.append((command, *args))
        if command == "describe":
            cl = int(args[-1])
            return [self.describe[(cl, "-S" in args)]]
        if command == "where":
            return [{"depotFile": d, "path": self.where_root + d[len("//depot"):]} for d in args]
        if command == "have":
            if args[0] not in self.have:
                raise P4Error("file(s) not on client")
            return [{"haveRev": self.have[args[0]]}]
        raise AssertionError(command)

    def print_text(self, spec):
        return self.files[spec]


def test_shelved_cl_reads_base_rev_and_shelf():
    p4 = FakeP4(
        describe={(7, False): {"status": "pending", "user": "bob", "desc": "fix\n"},
                  (7, True): {"status": "pending", "user": "bob", "desc": "fix\n",
                              "depotFile0": "//depot/a.c", "action0": "edit", "rev0": "4", "type0": "text",
                              "depotFile1": "//depot/n.c", "action1": "add", "rev1": "none", "type1": "text",
                              "depotFile2": "//depot/img.bin", "action2": "edit", "rev2": "2", "type2": "binary"}},
        files={"//depot/a.c#4": "old", "//depot/a.c@=7": "new", "//depot/n.c@=7": "added"},
        have={"//depot/a.c": "4", "//depot/img.bin": "2"})
    cs = P4Source(p4).load([7])
    assert cs.cls[0].status == "pending" and cs.cls[0].description == "fix"
    a, img, n = cs.files
    assert (a.before, a.after, a.base_rev, a.local) == ("old", "new", "#4", "/ws/a.c")
    assert (n.action, n.before, n.after, n.base_rev) == ("add", "", "added", None)
    assert (img.before, img.after) == ("", "")  # binary content never fetched
    assert cs.drift == []


def test_submitted_cl_uses_previous_revision_and_reports_drift():
    p4 = FakeP4(
        describe={(9, False): {"status": "submitted", "user": "amy", "desc": "x",
                               "depotFile0": "//depot/a.c", "action0": "edit", "rev0": "5", "type0": "text"}},
        files={"//depot/a.c#4": "v4", "//depot/a.c#5": "v5"}, have={"//depot/a.c": "3"})
    cs = P4Source(p4).load([9])
    f = cs.files[0]
    assert (f.before, f.after, f.base_rev) == ("v4", "v5", "#4")
    assert [(d.expected, d.actual) for d in cs.drift] == [("#4", "#3")]


def test_pending_without_shelved_files_is_error():
    p4 = FakeP4(describe={(3, False): {"status": "pending"}, (3, True): {"status": "pending"}}, files={})
    with pytest.raises(SourceError, match="no shelved files"):
        P4Source(p4).load([3])


def test_runner_refuses_mutating_commands():
    with pytest.raises(P4Error, match="not allowed"):
        P4Runner("p4:1666", "ws").run("submit", "-c", "1")


def test_unmarshal_all_decodes_records():
    data = marshal.dumps({b"code": b"stat", b"change": b"12"}) + marshal.dumps({b"code": b"error", b"data": b"no"})
    assert unmarshal_all(data) == [{"code": "stat", "change": "12"}, {"code": "error", "data": "no"}]


class Completed:
    def __init__(self, stdout, returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, b"", returncode


def test_runner_treats_warnings_as_non_fatal(monkeypatch):
    import subprocess
    warn = marshal.dumps({b"code": b"error", b"severity": 2, b"data": b"//x/... - file(s) not in client view.\n"})
    stat = marshal.dumps({b"code": b"stat", b"depotFile": b"//depot/a.c", b"path": b"/ws/a.c"})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Completed(warn + stat, returncode=1))
    assert P4Runner("p4:1666", "ws").run("where", "//depot/a.c", "//x/b.c") == [
        {"code": "stat", "depotFile": "//depot/a.c", "path": "/ws/a.c"}]
    fatal = marshal.dumps({b"code": b"error", b"severity": 3, b"data": b"Access denied.\n"})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Completed(fatal, returncode=1))
    with pytest.raises(P4Error, match="Access denied"):
        P4Runner("p4:1666", "ws").run("describe", "-s", "1")


class ViewP4(FakeP4):
    """where: //depot/other is outside the client view; //depot/a.c has an exclusion line plus a mapping."""

    def run(self, command, *args):
        if command == "where":
            self.calls.append((command, *args))
            return [{"depotFile": "//depot/a.c", "path": "/elsewhere/a.c", "unmap": ""},
                    {"depotFile": "//depot/a.c", "path": "/ws/a.c"}]
        return super().run(command, *args)

    def print_text(self, spec):
        if spec.startswith("//depot/purged.c"):
            raise P4Error("p4 print //depot/purged.c#3: purged revision")
        return super().print_text(spec)


def test_unmapped_and_unprintable_files_become_warnings_not_failures():
    p4 = ViewP4(
        describe={(9, False): {"status": "submitted", "user": "amy", "desc": "x",
                               "depotFile0": "//depot/a.c", "action0": "edit", "rev0": "5", "type0": "text",
                               "depotFile1": "//depot/other/b.c", "action1": "edit", "rev1": "2", "type1": "text",
                               "depotFile2": "//depot/purged.c", "action2": "edit", "rev2": "3", "type2": "text+S"}},
        files={"//depot/a.c#4": "v4", "//depot/a.c#5": "v5", "//depot/other/b.c#1": "b1", "//depot/other/b.c#2": "b2"},
        have={"//depot/a.c": "4"})
    cs = P4Source(p4).load([9])
    by = {f.depot: f for f in cs.files}
    assert by["//depot/a.c"].local == "/ws/a.c"  # exclusion (unmap) record ignored
    assert by["//depot/other/b.c"].local == "" and by["//depot/other/b.c"].after == "b2"
    assert (by["//depot/purged.c"].before, by["//depot/purged.c"].after) == ("", "")
    assert any("//depot/other/b.c" in w and "client view" in w for w in cs.warnings)
    assert any("purged revision" in w for w in cs.warnings)
    assert [d.depot for d in cs.drift] == []  # unmapped files are not drift


def test_login_check_can_request_host_unlocked_ticket(monkeypatch):
    import subprocess
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return Completed(b"0123456789ABCDEF0123456789ABCDEF\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = P4Runner("p4:1666", "ws")
    assert r.login_check("anoop", "pw", all_hosts=True) == "0123456789ABCDEF0123456789ABCDEF"
    assert seen[-1][-3:] == ["login", "-p", "-a"]
    r.login_check("bob", "pw")
    assert seen[-1][-2:] == ["login", "-p"]


class FstatP4(FakeP4):
    def __init__(self, fstat, files):
        super().__init__(describe={}, files=files)
        self.fstat = fstat

    def run(self, command, *args):
        if command == "fstat":
            rec = self.fstat.get(args[-1])
            return [rec] if rec else []
        return super().run(command, *args)


def test_read_unchanged_file_at_have_revision():
    from codetortoise.vcs.source import SourceBinary, SourceNotAllowed
    p4 = FstatP4({"//depot/a.c": {"depotFile": "//depot/a.c", "clientFile": "/ws/a.c", "haveRev": "7", "headType": "text"},
                  "//depot/img.bin": {"depotFile": "//depot/img.bin", "clientFile": "/ws/img.bin", "haveRev": "1",
                                      "headType": "binary"},
                  "//depot/unsynced.c": {"depotFile": "//depot/unsynced.c", "clientFile": "/ws/unsynced.c", "headType": "text"}},
                 files={"//depot/a.c#7": "int a;\n"})
    src = P4Source(p4).read("//depot/a.c")
    assert (src.depot, src.local, src.rev, src.text) == ("//depot/a.c", "/ws/a.c", "#7", "int a;\n")
    with pytest.raises(SourceBinary):
        P4Source(p4).read("//depot/img.bin")
    with pytest.raises(SourceNotAllowed):
        P4Source(p4).read("//depot/unsynced.c")      # not synced in the base workspace
    with pytest.raises(SourceNotAllowed):
        P4Source(p4).read("//other/x.c")             # not in the client view


def test_depots_for_maps_local_paths_in_one_where_call():
    class WhereP4(FakeP4):
        def run(self, command, *args):
            self.calls.append((command, *args))
            assert command == "where"
            return [{"depotFile": "//depot" + a[len("/ws"):], "path": a} for a in args if a.startswith("/ws/")]
    p4 = WhereP4(describe={}, files={})
    assert P4Source(p4).depots_for(["/ws/a.c", "/ws/b/c.h", "/elsewhere/x.c"]) == {
        "/ws/a.c": "//depot/a.c", "/ws/b/c.h": "//depot/b/c.h"}
    assert len(p4.calls) == 1
    assert P4Source(p4).depots_for([]) == {}
