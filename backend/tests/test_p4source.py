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
