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
                                "stories": "ok", "review": "ok", "verdicts": "ok", "board": "ok", "llm": "degraded",
                                "reading": "ok", "finalize": "ok"}
    msgs = {s["name"]: s["message"] for s in svc.store.list_stages(rid)}
    assert msgs["pieces"].endswith("target(s): compile_commands")
    assert msgs["stories"].endswith("by the rules (no strong model configured)")
    assert msgs["review"] == "no strong model: 6 finding(s) left to the detectors and the AI's side-effect pass"
    assert msgs["reading"] == "1 thread(s), 0 connection(s) shown, 5 check(s); fixed thread text (no strong model)"
    reading = svc.store.get_blob(rid, "reading")
    assert [t["stories"] for t in reading["threads"]] == [["S2", "S1"]] and reading["headline"]["rules_only"]
    assert svc.store.get_blob(rid, "story_reading:S1")["thread"] == "T1"
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


def test_an_endpoint_without_a_scheme_or_with_a_bare_name_is_still_judged():
    from codetortoise.health import remote_host
    assert remote_host("api.example.com/v1") == "api.example.com"
    assert remote_host("127.0.0.1:1234/v1") is None and remote_host("192.168.1.20:8080") is None
    assert remote_host("http://gpubox:8080/v1") == "gpubox"


def test_health_says_a_bare_name_may_be_on_this_network(fx, tmp_path):
    from codetortoise.config import StrongLlmConfig
    from codetortoise.services import make_strong
    svc = make_services(fx, tmp_path)
    svc.cfg.llm.strong = StrongLlmConfig(base_url="http://gpubox:8080/v1", model="big")
    svc.strong = make_strong(svc.cfg)
    svc.strong.ping = lambda: False
    check = {c.name: c for c in run_health(svc).checks}["strong model endpoint"]
    assert check.detail.endswith("; code from reviewed changes is sent to gpubox (a bare name: check whether it is on "
                                 "this network)")


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


def _strong(svc, answer, model="big"):
    from scripted_llm import ScriptedLlm

    from codetortoise.config import StrongLlmConfig
    svc.cfg.llm.strong = StrongLlmConfig(base_url="http://127.0.0.1:9/v1", model=model)
    svc.strong = ScriptedLlm(answer, model)
    return svc.strong


def _one_story_per_cl(system, user):
    """Every piece of a CL in one story (the pieces' cards name their CL); every finding reviewed as no hazard, citing
    the first node its prompt shows."""
    import re
    if "QUESTION:" in user:
        node = re.search(r"\bN\d+\b", user.split("FINDINGS:", 1)[1])[0]
        return {"action": "answer", "verdicts": [{"finding": f, "verdict": "no_hazard", "reason": "Nothing reads it.",
                                                  "cites": [node]} for f in re.findall(r"^(F\d+) \[", user, re.M)]}
    if "STORIES (key | title" in user:
        return {"related": [], "merge": []}
    if "THREADS (id" in user:
        rows = re.findall(r"^(T\d+) \|.*?\| (S\d+)", user, re.M)
        return {"threads": [{"id": t, "name": "UART driver changes", "purpose": "This changes the UART driver.",
                             "cites": [sid]} for t, sid in rows],
                "whole": "The change reworks the UART driver. Its callers see new results.", "whole_cites": ["T1"],
                "connections": []}
    by_cl: dict[str, list[str]] = {}
    for pid, cl in re.findall(r"^(P\d+)  .*? · CL (\d+)", user, re.M):
        by_cl.setdefault(cl, []).append(pid)
    return {"action": "answer", "stories": [
        {"key": f"cl{cl}", "title": f"Changes of CL {cl}", "purpose": "This changes the UART driver.",
         "pieces": [{"id": p, "reason": "starts_purpose" if i == 0 else "same_feature"} for i, p in enumerate(ids)]}
        for cl, ids in sorted(by_cl.items())]}


def test_the_strong_model_forms_the_stories_and_a_rerun_of_the_same_change_reuses_them(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _one_story_per_cl)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    msg = next(s for s in svc.store.list_stages(rid) if s["name"] == "stories")
    assert msg["status"] == "ok" and msg["message"].startswith("2 stories formed by big, ")
    assert msg["message"].endswith("piece(s) placed, 0 unsorted")
    ss = svc.store.get_blob(rid, "stories")["stories"]
    assert {s["title"] for s in ss if s["source"] == "tier1"} == {"Changes of CL 101", "Changes of CL 102"}
    brief = svc.store.get_brief(rid)
    assert brief["model"] == "big" and brief["complete"] and brief["overview"].startswith("CHANGE: 2 CLs")
    calls = len(llm.prompts)
    run_review(rid, svc)                                            # unchanged: the brief is reused
    assert len(llm.prompts) == calls
    assert "reused" in next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "stories")
    run_review(rid, svc, fresh=True)                                # the owner asked for fresh stories
    assert len(llm.prompts) == calls * 2


def test_the_upfront_ai_pass_starts_each_finding_s_prompt_from_the_brief(fx, tmp_path):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.brief_context import HEAD
    weak = ScriptedLlm(lambda s, u: {})
    svc = make_services(fx, tmp_path, llm=weak)

    def hazard(system, user):
        out = _one_story_per_cl(system, user)
        for v in out.get("verdicts", []):
            v["verdict"] = "hazard"
        return out
    _strong(svc, hazard)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    explained = [p for p in weak.prompts if "Explain the risk of this finding" in p]
    assert explained and all(p.startswith(HEAD) and "VERDICT (strong model): hazard" in p for p in explained)


def test_a_strong_model_that_fails_leaves_the_rules_stories_and_says_so(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    _strong(svc, lambda s, u: RuntimeError("the endpoint is down"))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = next(s for s in svc.store.list_stages(rid) if s["name"] == "stories")
    assert st["status"] == "degraded"
    assert "chunk 1: RuntimeError: the endpoint is down; the rules grouped its pieces" in st["message"]
    assert {s["source"] for s in svc.store.get_blob(rid, "stories")["stories"]} == {"rules"}
    assert svc.store.get_brief(rid)["complete"] is False


def test_the_strong_model_reviews_each_story_s_findings_and_tier_2_leaves_them_alone(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _one_story_per_cl)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    msgs = {s["name"]: (s["status"], s["message"]) for s in svc.store.list_stages(rid)}
    assert msgs["review"] == ("ok", "6 finding(s) judged by big: 0 hazard(s), 0 to confirm, 6 no hazard")
    assert msgs["verdicts"] == ("ok", "all 2 side effect(s) judged by the strong model")
    findings = svc.store.list_findings(rid)
    assert {(f.severity, f.verdict, f.verdict_source) for f in findings} == {("info", "no_hazard", "tier1")}
    assert all(f.verdict_cites for f in findings)
    brief = svc.store.get_brief(rid)
    assert len(brief["verdicts"]) == 6 and "drv" not in brief["facts"] and len(brief["facts"]) == 6
    calls = len(llm.prompts)
    run_review(rid, svc)                                            # the brief brings its verdicts: no call at all
    assert len(llm.prompts) == calls and len(svc.store.get_brief(rid)["verdicts"]) == 6


def test_the_strong_model_names_the_threads_once_and_a_rerun_reuses_the_text(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _one_story_per_cl)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    reading = svc.store.get_blob(rid, "reading")
    assert {t["name"] for t in reading["threads"]} == {"UART driver changes"} and reading["whole_source"] == "llm"
    msg = next(s["message"] for s in svc.store.list_stages(rid) if s["name"] == "reading")
    assert msg.endswith("thread text by big")
    asked = sum("THREADS (id" in p for p in llm.prompts)
    run_review(rid, svc)
    assert sum("THREADS (id" in p for p in llm.prompts) == asked == 1
    assert svc.store.get_blob(rid, "reading")["whole_source"] == "llm"


def test_a_four_cl_review_reads_as_three_connected_threads(fx, tmp_path):
    """CLs 103–104 add a logger level across two CLs (one thread meeting the UART thread in `main`) and an engine
    change tied to the rest only by CL 104 (spec 2026-10-07-review-reading §13)."""
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102, 103, 104])
    run_review(rid, svc)
    r = svc.store.get_blob(rid, "reading")
    titles = {s["id"]: s["title"] for s in svc.store.get_blob(rid, "stories")["stories"]}
    assert [[titles[s] for s in t["stories"]] for t in r["threads"]] == [
        ["`hal_write`'s signature changed; `uart_init` calls it",
         "`uart_send` can now return -2; `logger_flush` ignores it (1 more effect)"],
        ["Other changes in `service` (`logger_init`)", "Other changes in `service` (`logger_level`)"],
        ["Other changes in `cpp`"]]
    assert [t["cls"] for t in r["threads"]] == [[101, 102], [103, 104], [104]]
    assert [(k["a"], k["b"], k["kind"], k["text"]) for k in r["connections"] if k["shown"]] == [
        ("T1", "T2", "caller", "both run inside `main`"), ("T2", "T3", "bundled", "nothing besides arriving in CL 104")]
    assert [(k["kind"], k["thread"]) for k in r["checks"]] == [
        ("confirm", "T1"), ("confirm", "T1"), ("caller", "T1"), ("result", "T1"), ("reader", "T1"), ("ask", "T3")]
    assert r["whole"] == "3 threads: A and B: both run inside `main`; B and C: nothing besides arriving in CL 104."
    assert "`service/logger.h` header change → 2 files rebuild" in [b["text"] for b in r["build_impact"]]


def test_a_rerun_that_builds_no_reading_leaves_none_behind(fx, tmp_path, monkeypatch):
    from codetortoise import pipeline
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    assert svc.store.get_blob(rid, "reading") and svc.store.blob_keys(rid, "story_reading:")

    def boom(*a, **k):
        raise RuntimeError("broken")
    monkeypatch.setattr(pipeline, "build_stories", boom)                       # the stories fail: nothing to read
    run_review(rid, svc)
    assert svc.store.get_blob(rid, "reading") is None and svc.store.blob_keys(rid, "story_reading:") == []
    monkeypatch.undo()
    run_review(rid, svc)
    assert svc.store.get_blob(rid, "reading")
    monkeypatch.setattr(pipeline, "build_boards", boom)                        # the board fails: reading is skipped
    run_review(rid, svc)
    assert stages(svc, rid)["reading"] == "skipped"
    assert svc.store.get_blob(rid, "reading") is None and svc.store.blob_keys(rid, "story_reading:") == []


def test_a_later_cl_rewriting_an_earlier_ones_line_is_a_rewrite_and_each_story_reads_only_the_cls_in_its_code(fx, tmp_path):
    """CL 105 rewrites the line CL 103 added in `logger_init`; CL 104 adds `logger_level` (phase 2 §4)."""
    svc = make_services(fx, tmp_path)
    logger = "//fixture/service/logger.c"
    rid = svc.store.create_review("t", "owner", [103, 104, 105])
    run_review(rid, svc)
    r = svc.store.get_blob(rid, "reading")
    rewrite = {"by": 105, "of": 103, "file": logger, "function": "logger_init", "lines": 1, "line": 7}
    assert r["rewrites"] == [rewrite] and r["gaps"] == []
    assert list(svc.store.get_blob(rid, "lines")) == [logger]                     # only files several CLs edit
    titles = {s["title"]: s["id"] for s in svc.store.get_blob(rid, "stories")["stories"]}
    init = svc.store.get_blob(rid, f"story_reading:{titles['Other changes in `service` (`logger_init`)']}")
    level = svc.store.get_blob(rid, f"story_reading:{titles['Other changes in `service` (`logger_level`)']}")
    assert (init["cl_order"], init["rewrites"], init["where"][0]["cls"]) == ([103, 105], [rewrite], [103, 105])
    assert (level["cl_order"], level["rewrites"]) == ([104], [])
    rid = svc.store.create_review("t", "owner", [103, 105])                       # CL 104 is outside this review
    run_review(rid, svc)
    assert svc.store.get_blob(rid, "reading")["gaps"] == [{"file": logger, "after_cl": 103, "before_cl": 105,
                                                              "same_base": False}]   # CL 104 came between: not one base
