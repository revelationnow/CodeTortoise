from helpers import make_services

from codetortoise.health import run_health
from codetortoise.pipeline import run_review
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def stages(svc, rid):
    return {s["name"]: s["status"] for s in svc.store.list_stages(rid)}


def test_full_review_without_llm_or_swarm(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    assert stages(svc, rid) == {"ingest": "ok", "swarm_read": "degraded", "diffmap": "ok", "tu_select": "ok",
                                "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok",
                                "llm": "degraded", "finalize": "ok"}
    review = svc.store.get_review(rid)
    assert review["status"] == "degraded" and review["risk"] == "high"
    assert len(svc.store.list_findings(rid)) == 6
    sb = svc.store.get_blob(rid, "storyboard")
    assert [c["name"] for c in sb["chapters"]][:3] == ["L0: cpp, include/hal", "L1: hal", "L2: driver"]
    assert [c["cl"] for c in svc.store.list_cls(rid)] == [101, 102]
    assert svc.store.list_cls(rid)[0]["description"].startswith("uart:")


def test_ingest_failure_skips_dependent_stages(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [999])
    run_review(rid, svc)
    st = stages(svc, rid)
    assert st["ingest"] == "failed" and st["diffmap"] == "skipped" and st["detectors"] == "skipped"
    assert "CL 999 not found" in svc.store.list_stages(rid)[0]["message"]
    assert svc.store.get_review(rid)["status"] == "failed"


class OnlyDocs:
    def load(self, cls):
        return ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                         files=[FileChange(depot="//d/README.md", local="/nowhere/README.md", action="edit",
                                           before="a", after="b")])


def test_change_without_c_code_completes(fx, tmp_path):
    svc = make_services(fx, tmp_path, source=OnlyDocs())
    rid = svc.store.create_review("t", "owner", [1])
    run_review(rid, svc)
    st = stages(svc, rid)
    assert st["impact"] == "ok" and st["detectors"] == "ok"
    assert svc.store.list_findings(rid) == []
    assert svc.store.get_blob(rid, "storyboard")["risk"] == "low"


def test_health_ready_on_fixture_and_gates_on_empty_compile_db(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rep = run_health(svc)
    assert rep.ready and rep.libclang.startswith("clang version")
    assert {c.name: c.ok for c in rep.checks}["llm endpoint"] is False  # warning only
    svc.cdb.entries.clear()
    assert run_health(svc).ready is False


class FakeClientRunner:
    def __init__(self, root, alt=()):
        self.root, self.alt = root, alt

    def run(self, command, *args):
        assert command == "client"
        rec = {"Root": self.root}
        rec.update({f"AltRoots{i}": a for i, a in enumerate(self.alt)})
        return [rec]


def test_health_p4_client_root_compared_canonically(fx, tmp_path):
    link = tmp_path / "ws-link"
    link.symlink_to(fx.root)
    svc = make_services(fx, tmp_path)
    svc.cfg.workspace.vcs = "p4"
    svc.cfg.workspace.client = "ws"
    svc.cfg.workspace.root = link
    svc.p4 = FakeClientRunner(str(fx.root.resolve()) + "/")
    assert {c.name: c.ok for c in run_health(svc).checks}["p4 client"] is True
    svc.p4 = FakeClientRunner("/somewhere/else", alt=[str(link)])
    assert {c.name: c.ok for c in run_health(svc).checks}["p4 client"] is True
    svc.p4 = FakeClientRunner("/somewhere/else")
    assert {c.name: c.ok for c in run_health(svc).checks}["p4 client"] is False
