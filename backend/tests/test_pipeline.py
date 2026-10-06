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
                                "layers": "ok", "facts": "ok", "impact": "ok", "detectors": "ok", "pieces": "ok",
                                "stories": "ok", "verdicts": "ok", "board": "ok", "llm": "degraded", "finalize": "ok"}
    msgs = {s["name"]: s["message"] for s in svc.store.list_stages(rid)}
    assert msgs["pieces"].endswith("target(s): compile_commands")
    assert msgs["stories"].endswith("by the rules")
    ss = svc.store.get_blob(rid, "stories")
    assert all(s["targets"] == ["compile_commands"] and s["pieces"] for s in ss["stories"])
    review = svc.store.get_review(rid)
    assert review["status"] == "degraded" and review["risk"] == "high"
    assert len(svc.store.list_findings(rid)) == 6
    sb = svc.store.get_blob(rid, "storyboard")
    assert [c["name"] for c in sb["chapters"]][:3] == ["L0: cpp, include/hal", "L1: hal", "L2: driver"]
    assert [c["cl"] for c in svc.store.list_cls(rid)] == [101, 102]
    assert svc.store.list_cls(rid)[0]["description"].startswith("uart:")
    board = svc.store.get_blob(rid, "board")
    # the state flow stays, neutral: its side effect hasn't been judged a hazard (no AI here)
    assert [(f["tag"], f["severity"]) for f in board["flows"]] == [("contract", "medium"), ("contract", "medium"),
                                                                   ("state", "info")]
    assert "not assessed" in next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "verdicts")
    assert all(n["path"].startswith("//fixture/") for n in board["nodes"] if n["kind"] == "function")
    assert board["about"]["intent_source"] == "template"
    assert all(n["files"] for n in board["nodes"]) and all(f["files"] for f in board["flows"])   # tags stored (spec §14.3)
    findings = {f.id: f for f in svc.store.list_findings(rid)}
    assert all(f.files for f in findings.values() if f.kind != "header_fanout")
    # header fan-out evidence lists layers by name, which come from directory names: unknown
    assert all(f.files is None for f in findings.values() if f.kind == "header_fanout")
    # F6: the field Uart::errors is declared in uart.h; other accessors are named in its evidence
    assert findings["F6"].files == ["//fixture/driver/uart.c", "//fixture/driver/uart.h"]
    # F3: "callers must be re-checked: uart_init, uart_send" names functions in uart.c
    assert findings["F3"].files == ["//fixture/driver/uart.c", "//fixture/hal/regs.c"]
    assert [w["files"] for w in board["about"]["why"]] == [findings[w["finding"]].files for w in board["about"]["why"]]


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
    # the side effect the AI couldn't judge stays neutral: the contract change sets the risk
    assert sb is not None and sb["risk"] == "medium" and "unexpected LLM response" in sb["llm_error"]
    assert stages(svc, rid)["verdicts"] == "degraded"


def test_llm_text_stored_by_a_review_records_its_prompt_files(fx, tmp_path):
    import json

    import httpx

    from codetortoise.llm.client import LlmClient
    cites = [f"N{i}" for i in range(1, 40)] + [f"F{i}" for i in range(1, 10)]

    def reply(req):
        user = json.loads(req.content)["messages"][1]["content"]
        out = ({"verdicts": []} if "Judge each side effect" in user else
               {"explanation": "e"} if "Explain the risk" in user else
               {"narrative": "n", "cites": cites} if "narrative for this architectural layer" in user else
               {"what": "w", "title": "t", "cites": cites} if "Describe this call flow" in user else
               {"summary": "s", "risk": "high", "cites": cites})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out)}}]})
    llm = LlmClient("http://llm/v1", "k", "m", sleep=lambda s: None, transport=httpx.MockTransport(reply))
    svc = make_services(fx, tmp_path, llm=llm)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    board = svc.store.get_blob(rid, "board")
    # the summary prompt includes the header fan-out findings, whose layer lists are unknown: so is the intent
    assert board["about"]["intent_source"] == "llm" and board["about"]["intent_files"] is None
    llm_flows = [f for f in board["flows"] if f["what_source"] == "llm"]
    assert llm_flows and all(f["what_files"] and set(f["files"]) <= set(f["what_files"]) for f in llm_flows)
    # the up-front pass: the summary, the top 3 flows, the top behaviour stories (the fixture has 2) and the high
    # findings; the rest are explained on demand (spec 2026-10-03 §3, 2026-10-04 §4, review workspace §4.4)
    found = svc.store.list_findings(rid)
    assert len(llm_flows) == 3 and any(f.severity == "high" for f in found)
    assert all((f.explanation is not None) == (f.severity == "high") for f in found)
    usage = svc.ledger.usage(rid)
    assert usage["by_purpose"] == {"verdict": 1, "flow": 3, "story": 2, "finding": 2, "summary": 1}, usage["by_purpose"]
    assert usage["by_person"] == {"pipeline": 9}                       # the fixture's 3 high findings, under the cap of 5


def test_the_llm_stage_reports_text_dropped_for_breaking_the_style(fx, tmp_path):
    import json

    import httpx

    from codetortoise.llm.client import LlmClient
    cites = [f"N{i}" for i in range(1, 40)] + [f"F{i}" for i in range(1, 10)]

    def reply(req):
        user = json.loads(req.content)["messages"][1]["content"]
        out = ({"explanation": "It is fine."} if "Explain the risk" in user else
               {"narrative": "n", "cites": cites} if "narrative for this architectural layer" in user else
               {"what": "Please simply look!", "cites": cites} if "Describe this call flow" in user else
               {"summary": "s", "risk": "high", "cites": cites})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out)}}]})
    svc = make_services(fx, tmp_path, llm=LlmClient("http://llm/v1", "k", "m", sleep=lambda s: None,
                                                    transport=httpx.MockTransport(reply)))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    llm = next(s for s in svc.store.list_stages(rid) if s["name"] == "llm")
    assert llm["status"] == "ok" and llm["message"] == "3 AI output(s) broke the house style and were dropped"
    assert all(f["what_source"] == "template" for f in svc.store.get_blob(rid, "board")["flows"])

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

    def spy(root, workers=0, include_dirs=None, **kw):
        seen["include_dirs"], seen["seeds"] = include_dirs, kw.get("seeds")
        return real_build(root, workers=workers, include_dirs=include_dirs, **kw)

    svc.index.build = spy
    rid = svc.store.create_review("t", "owner", [101])
    run_review(rid, svc)
    root = str(fx.root.resolve())
    assert seen["include_dirs"] == [f"{root}/include", root]
    assert seen["seeds"] and all(f.startswith(root) for f in seen["seeds"])          # compile-DB scope by default


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
    # the files Perforce could not name are unknown, never guessed (spec §14.3)
    tags = {n["label"]: n["files"] for n in board["nodes"]}
    assert tags["uart_send"] == ["//fixture/driver/uart.c"] and tags["main"] is None
    assert all(f["files"] is None for f in board["flows"])                    # every flow starts at main
    f4 = next(f for f in svc.store.list_findings(rid) if f.id == "F4")      # evidence in service/logger.c
    assert f4.files is None
    assert st["board"]["message"].count("connect failed") == 1              # one lookup, not one per caller



class NoLogger(GitFixtureSource):
    """Perforce answers for every file but service/logger.c."""
    def depots_for(self, locals_):
        return {p: d for p, d in super().depots_for(locals_).items() if not p.endswith("service/logger.c")}


def test_one_failed_lookup_leaves_that_files_items_unknown_not_guessed_from_callers(fx, tmp_path):
    svc = make_services(fx, tmp_path, source=NoLogger(fx.root))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    board = svc.store.get_blob(rid, "board")
    tags = {n["label"]: n["files"] for n in board["nodes"]}
    assert tags["logger_write"] is None and tags["logger_flush"] is None and tags["main"] == ["//fixture/app/main.c"]
    assert all(i["files"] is None for i in board["impacts"] if i["node"] in ("N3", "N5"))
    flows = {f["id"]: f["files"] for f in board["flows"]}
    assert flows["FL1"] is None and flows["FL2"] is not None and flows["FL3"] is None   # FL2 avoids logger.c

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
    assert resolve(["/ws/b/c.h", "/ws/e.c"]) == {"/ws/b/c.h": "//d/b/c.h", "/ws/e.c": "//d/e.c"}
    assert asked == [["/ws/b/c.h"], ["/ws/e.c"]]                       # each workspace file is asked about once


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


def test_health_checks_the_strong_model_and_says_where_code_is_sent(fx, tmp_path):
    from codetortoise.config import StrongLlmConfig
    from codetortoise.services import make_strong
    for url, remote in (("https://api.example.com/v1", True), ("http://127.0.0.1:1234/v1", False),
                        ("http://192.168.1.20:8080/v1", False), ("http://localhost:1/v1", False)):
        svc = make_services(fx, tmp_path)
        svc.cfg.llm.strong = StrongLlmConfig(base_url=url, model="big")
        svc.strong = make_strong(svc.cfg)
        svc.strong.ping = lambda: False                     # no network in tests
        check = {c.name: c for c in run_health(svc).checks}["strong model endpoint"]
        assert check.hard is False and check.detail.startswith(f"{url} (big)")
        assert check.detail.endswith("; code from reviewed changes is sent to api.example.com") == remote
    svc = make_services(fx, tmp_path)
    assert {c.name: c for c in run_health(svc).checks}["strong model endpoint"].detail == "not configured (stories by rules)"
