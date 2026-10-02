from helpers import make_services

from codetortoise.health import run_health
from codetortoise.pipeline import run_review
from codetortoise.vcs.gitfixture import GitFixtureSource
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange
from codetortoise.vcs.p4runner import P4Error


def stages(svc, rid):
    return {s["name"]: s["status"] for s in svc.store.list_stages(rid)}


def test_full_review_without_llm_or_swarm(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    assert stages(svc, rid) == {"ingest": "ok", "swarm_read": "degraded", "diffmap": "ok", "tu_select": "ok",
                                "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok", "board": "ok",
                                "llm": "degraded", "finalize": "ok"}
    review = svc.store.get_review(rid)
    assert review["status"] == "degraded" and review["risk"] == "high"
    assert len(svc.store.list_findings(rid)) == 6
    sb = svc.store.get_blob(rid, "storyboard")
    assert [c["name"] for c in sb["chapters"]][:3] == ["L0: cpp, include/hal", "L1: hal", "L2: driver"]
    assert [c["cl"] for c in svc.store.list_cls(rid)] == [101, 102]
    assert svc.store.list_cls(rid)[0]["description"].startswith("uart:")
    board = svc.store.get_blob(rid, "board")
    assert [f["tag"] for f in board["flows"]] == ["state", "contract", "contract"]
    assert all(n["path"].startswith("//fixture/") for n in board["nodes"] if n["kind"] == "function")
    assert board["about"]["intent_source"] == "template"
    assert all(n["files"] for n in board["nodes"]) and all(f["files"] for f in board["flows"])   # tags stored (spec §14.3)


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
    assert st["board"] == "ok" and svc.store.get_blob(rid, "board")["flows"] == []


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


def test_stripped_flags_are_learned_for_the_workspace(fx, tmp_path):
    from codetortoise.toolchain.compile_db import CompileDb, CompileEntry
    svc = make_services(fx, tmp_path)
    svc.cdb.entries[:] = [CompileEntry(e.file, e.directory, e.args + ("-mcpu=vendorcore",)) for e in svc.cdb.entries]
    svc.cdb.__init__(list(svc.cdb.entries))
    rid = svc.store.create_review("t", "owner", [101])
    run_review(rid, svc)
    assert "-mcpu=vendorcore" in svc.toolchain.strip
    facts_msg = next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "facts")
    assert "-mcpu=vendorcore" in facts_msg
    assert "-mcpu=vendorcore" in run_health(svc).strip_flags
    again = make_services(fx, tmp_path)  # persisted per workspace
    assert "-mcpu=vendorcore" in again.toolchain.strip
    assert isinstance(again.cdb, CompileDb)


def test_malformed_llm_reply_still_stores_storyboard(fx, tmp_path):
    import httpx

    from codetortoise.llm.client import LlmClient
    llm = LlmClient("http://llm/v1", "k", "m", sleep=lambda s: None,
                    transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": None})))
    svc = make_services(fx, tmp_path, llm=llm)
    rid = svc.store.create_review("t", "owner", [101])
    run_review(rid, svc)
    assert stages(svc, rid)["llm"] == "degraded"
    sb = svc.store.get_blob(rid, "storyboard")
    assert sb is not None and sb["risk"] == "high" and "unexpected LLM response" in sb["llm_error"]


class WarningSource:
    def __init__(self, inner):
        self.inner = inner

    def load(self, cls):
        cs = self.inner.load(cls)
        cs.warnings.append("//fixture/x.c: not in client view (not analysed)")
        return cs


def test_ingest_warnings_degrade_but_continue(fx, tmp_path, fx_source):
    svc = make_services(fx, tmp_path, source=WarningSource(fx_source))
    rid = svc.store.create_review("t", "owner", [101])
    run_review(rid, svc)
    st = stages(svc, rid)
    assert st["ingest"] == "degraded" and st["impact"] == "ok"
    assert "not in client view" in svc.store.list_stages(rid)[0]["message"]
    assert svc.store.get_review(rid)["status"] == "degraded"


def test_index_is_built_with_compile_db_include_dirs(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    seen = {}
    real_build = svc.index.build

    def spy(root, workers=0, include_dirs=None):
        seen["include_dirs"] = include_dirs
        return real_build(root, workers=workers, include_dirs=include_dirs)

    svc.index.build = spy
    rid = svc.store.create_review("t", "owner", [101])
    run_review(rid, svc)
    root = str(fx.root.resolve())
    assert seen["include_dirs"] == [f"{root}/include", root]


def test_facts_stage_parses_field_follow_up_tus(fx, tmp_path, monkeypatch):
    from codetortoise import pipeline
    svc = make_services(fx, tmp_path)
    svc.cfg.analysis.caller_hops = 0  # initial selection: driver/uart.c only
    logger = str((fx.root / "service/logger.c").resolve())
    seen = {}

    def fake_follow_up(dm, after, index, cdb, sel, cfg):
        seen["after_files"] = [f.tu.file.split("/")[-1] for f in after]
        return [logger]

    monkeypatch.setattr(pipeline, "field_follow_up", fake_follow_up)
    rid = svc.store.create_review("t", "owner", [101])
    run_review(rid, svc)
    assert seen["after_files"] == ["uart.c"]
    sel = svc.store.get_blob(rid, "selection")
    assert logger in sel["selected"] and sel["hops"][logger] == 1
    parsed = {f["tu"]["file"].split("/")[-1] for f in svc.store.get_blob(rid, "facts_before")}
    assert parsed == {"uart.c", "logger.c"}
    msg = next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "facts")
    assert "1 follow-up TU(s)" in msg


def test_layer_cache_is_invalidated_by_algorithm_version(fx, tmp_path, monkeypatch):
    from codetortoise import layers as layers_mod
    from codetortoise.layers import LayerModel
    svc = make_services(fx, tmp_path)
    svc.build_index()
    first = svc.layers.get()
    stale = LayerModel(root=first.root, generation=first.generation, layers=[], module_level={"x": 0})
    svc.store.kv_put(svc.layers._key(), stale)
    monkeypatch.setattr(layers_mod, "ALGORITHM_VERSION", layers_mod.ALGORITHM_VERSION + 1)
    fresh = make_services(fx, tmp_path)
    assert fresh.layers.get().module_level != {"x": 0}


class NoWhere(GitFixtureSource):
    def depots_for(self, locals_):
        raise P4Error("p4 where: connect failed")


def test_board_without_depot_paths_for_context_nodes_is_degraded(fx, tmp_path):
    svc = make_services(fx, tmp_path, source=NoWhere(fx.root))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert st["board"]["status"] == "degraded" and "connect failed" in st["board"]["message"]
    board = svc.store.get_blob(rid, "board")
    paths = {n["label"]: n["path"] for n in board["nodes"]}
    assert paths["uart_send"] == "//fixture/driver/uart.c" and paths["main"] is None
    assert len(board["flows"]) == 3


def test_depot_resolver_asks_the_source_only_about_workspace_files():
    from codetortoise.pipeline import depot_resolver
    asked = []

    class Src:
        def depots_for(self, locals_):
            asked.append(list(locals_))
            return {p: "//d" + p[3:] for p in locals_}
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                   files=[FileChange(depot="//d/a.c", local="/ws/a.c", action="edit", before="", after="")])
    notes: list[str] = []
    resolve = depot_resolver(Src(), cs, "/ws", notes)
    got = resolve(["/ws/a.c", "/ws/b/c.h", "/usr/include/stdio.h", "/wsx/d.c"])
    assert got == {"/ws/a.c": "//d/a.c", "/ws/b/c.h": "//d/b/c.h"}
    assert asked == [["/ws/b/c.h"]] and notes == []


def test_depot_resolver_failure_keeps_changed_files_and_notes_why():
    from codetortoise.pipeline import depot_resolver

    class Src:
        def depots_for(self, locals_):
            raise P4Error("p4 where: connect failed")
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                   files=[FileChange(depot="//d/a.c", local="/ws/a.c", action="edit", before="", after="")])
    notes: list[str] = []
    assert depot_resolver(Src(), cs, "/ws", notes)(["/ws/a.c", "/ws/b.c"]) == {"/ws/a.c": "//d/a.c"}
    assert notes == ["depot paths unavailable for context nodes: P4Error: p4 where: connect failed"]
