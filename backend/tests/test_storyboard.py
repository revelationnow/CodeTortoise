import json

import httpx

from codetortoise.detectors.base import Evidence, Finding
from codetortoise.impact import Edge, ImpactModel, Node
from codetortoise.layers import Layer, LayerModel
from codetortoise.llm.client import LlmClient
from codetortoise.llm.storyboard import (
    AiContext,
    Cited,
    budget,
    build_storyboard,
    finding_job,
    flow_job,
    ground,
    name_layers,
    run_job,
    skeleton,
)


def model():
    im = ImpactModel()
    im.nodes = {
        "N1": Node(id="N1", key="c:@F@hal_write", label="hal_write", status="changed", layer=1, file="/w/hal/regs.c", line=3),
        "N2": Node(id="N2", key="c:@F@uart_send", label="uart_send", status="changed", layer=2, file="/w/d/uart.c", line=9),
        "N3": Node(id="N3", key="c:@F@logger_flush", label="logger_flush", layer=3),
    }
    im.edges = [Edge(id="E1", src="N3", dst="N2", kind="call"), Edge(id="E2", src="N2", dst="N1", kind="call")]
    im.changed = ["N1", "N2"]
    findings = [
        Finding(id="F1", kind="contract", severity="medium", title="uart_send: new return", nodes=["N2"],
                summary="s", evidence=[Evidence(text="logger_flush ignores the result")]),
        Finding(id="F2", kind="header_fanout", severity="high", title="regs.h", summary="s",
                evidence=[Evidence(text="decl changed", file="/w/include/hal/regs.h")]),
    ]
    layers = LayerModel(root="/w", layers=[Layer(level=0, name="L0: include/hal", modules=["include/hal"]),
                                           Layer(level=1, name="L1: hal", modules=["hal"]),
                                           Layer(level=2, name="L2: d", modules=["d"])],
                        module_level={"include/hal": 0, "hal": 1, "d": 2})
    return im, findings, layers


def test_skeleton_orders_chapters_bottom_up_and_attaches_findings():
    im, findings, layers = model()
    sb = skeleton(im, findings, layers)
    assert [(c.name, c.nodes, c.findings) for c in sb.chapters] == [
        ("L0: include/hal", [], ["F2"]), ("L1: hal", ["N1"], []), ("L2: d", ["N2"], ["F1"])]
    assert sb.risk == "high"
    assert sb.review_order == ["N1", "N2"]
    assert sb.summary == "2 function(s) changed across 2 layer(s); 2 finding(s), 1 high."
    assert not sb.llm_used


def test_ground_drops_uncited_and_unknown():
    items = [Cited(text="a", cites=["N1", "N99"]), Cited(text="b", cites=[]), Cited(text="c", cites=["X"])]
    assert ground(items, {"N1"}) == [Cited(text="a", cites=["N1"])]


def test_budget_truncates_by_priority():
    out = budget(["A" * 400, "B" * 400, "C" * 400], max_tokens=175)  # 700 chars
    assert out.startswith("A" * 400) and "B" in out and "C" not in out and out.endswith("[truncated]")


def fake_llm(responder):
    def handler(req):
        body = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
            responder(body["messages"][0]["content"], body["messages"][1]["content"]))}}]})
    return LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_name_layers():
    _, _, layers = model()
    llm = fake_llm(lambda s, u: {"layers": [{"level": 0, "name": "HAL API", "description": "d"},
                                            {"level": 2, "name": "Drivers"}]})
    out = name_layers(layers, llm)
    assert [l.name for l in out.layers] == ["L0: HAL API", "L1: hal", "L2: Drivers"]


def _board(flows=2):
    from codetortoise.board import About, Board, Flow
    fl = [Flow(id=f"FL{i + 1}", path=["N3", "N2"], tag="contract", lands="N3", fx_at="N3", severity="medium",
               findings=["F1"], text="logger_flush → uart_send ⟶ -2 ignored", title="template title", what="template what",
               effect="e",
               check="c") for i in range(flows)]
    for f in fl:
        f.files = f.what_files = ["//fixture/service/logger.c"]
    return Board(flows=fl, about=About(intent="template intent", intent_files=["//fixture/driver/uart.c"]))


def _respond(flow_reply):
    def respond(system, user):
        if "Explain the risk" in user:
            return {"explanation": "e"}
        if "narrative for this architectural layer" in user:
            return {"narrative": "n", "cites": ["N1"]}
        if "Describe this call flow" in user:
            return flow_reply(user)
        return {"summary": "the change adds tx stats", "risk": "medium", "cites": ["F1"]}
    return respond


def _ctx(findings, im, node_files=None, snippets=None):
    return AiContext(impact=im, findings=findings, snippets=snippets or {}, max_tokens=64000, node_files=node_files)


def test_the_upfront_pass_writes_the_summary_and_the_top_flows_only():
    im, findings, layers = model()
    board = _board(4)
    asked = []

    def respond(system, user):
        asked.append(user.split("\n", 1)[0][:30])
        return _respond(lambda u: {"what": "flush drops -2", "title": "logger_flush drops -2", "cites": ["N3", "F1"]})(system, user)
    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond), board=board, upfront_flows=2)
    assert sb.llm_used and sb.summary == "the change adds tx stats" and sb.risk == "high"   # never below the findings
    assert sum("Describe this call flow" in a for a in asked) == 2 and sum("Summarize" in a for a in asked) == 1
    assert not any("Explain the risk" in a or "architectural layer" in a for a in asked)    # on demand only
    assert [f.what_source for f in board.flows] == ["llm", "llm", "template", "template"]
    assert board.about.intent == "the change adds tx stats" and board.about.intent_source == "llm"
    assert all(f.explanation is None for f in findings)


def test_upfront_flows_run_concurrently_then_the_summary():
    import threading
    im, findings, layers = model()
    board = _board(2)
    gate = threading.Barrier(2, timeout=5)

    def respond(system, user):
        if "Describe this call flow" in user:
            gate.wait()
        return _respond(lambda u: {"what": "w", "cites": ["N3"]})(system, user)
    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond), board=board, concurrency=4, upfront_flows=2)
    assert sb.llm_used, sb.llm_error
    assert [f.what_source for f in board.flows] == ["llm", "llm"]


def test_every_upfront_call_goes_through_the_ledger_and_stops_at_the_budget(tmp_path):
    from codetortoise.config import LlmBudget
    from codetortoise.llm.ledger import Ledger
    from codetortoise.store import Store
    im, findings, layers = model()
    store = Store(tmp_path / "t.db")
    rid = store.create_review("t", "owner", [1])
    ledger = Ledger(store, LlmBudget(per_review=2))
    board = _board(3)
    sb = build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: {"what": "w", "cites": ["N3"]})),
                          board=board, upfront_flows=3, ledger=ledger, rid=rid)
    u = ledger.usage(rid)
    assert u["used"] == 2 and all(c["user"] == "pipeline" for c in u["calls"])
    assert "this review has used its 2 AI calls" in (sb.llm_error or "")
    assert board.about.intent_source == "template"                                         # the summary was refused


def test_llm_failure_keeps_the_deterministic_storyboard():
    im, findings, layers = model()
    board = _board(1)
    llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(500)),
                    sleep=lambda s: None)
    sb = build_storyboard(im, findings, layers, {}, llm, board=board)
    assert not sb.llm_used and "failed after" in sb.llm_error
    assert sb.chapters[1].narrative.startswith("Changed: hal_write")
    assert board.flows[0].what == "template what" and board.about.intent_source == "template"


def test_unexpected_llm_client_exception_keeps_skeleton():
    im, findings, layers = model()

    class Exploding:
        def complete_json(self, *a, **k):
            raise TypeError("boom")

    sb = build_storyboard(im, findings, layers, {}, Exploding(), board=_board(1))
    assert not sb.llm_used and "boom" in sb.llm_error and sb.chapters


def test_a_finding_explanation_is_one_grounded_call():
    im, findings, layers = model()
    out = {"explanation": "exp", "verify_steps": ["Check callers."],
           "hypotheses": [{"text": "flush drops -2", "cites": ["N3", "F1"]}, {"text": "made up", "cites": []}]}
    dropped = run_job(fake_llm(lambda s, u: out), finding_job(_ctx(findings, im), findings[0]))
    assert dropped == 0
    assert findings[0].explanation == "exp" and findings[0].verify_steps == ["Check callers."]
    assert [h.text for h in findings[0].hypotheses] == ["flush drops -2"]
    assert findings[1].explanation is None


def test_flow_and_summary_jobs_ground_their_text():
    im, findings, layers = model()
    board = _board(2)
    ctx = _ctx(findings, im)
    run_job(fake_llm(lambda s, u: {"what": "uncited guess", "cites": ["N99"]}), flow_job(ctx, board.flows[0]))
    assert board.flows[0].what_source == "template"
    run_job(fake_llm(lambda s, u: {"what": "flush drops -2", "title": "logger_flush drops -2", "cites": ["N3"]}),
            flow_job(ctx, board.flows[1]))
    assert (board.flows[1].what, board.flows[1].title) == ("flush drops -2", "logger_flush drops -2")


def test_ai_text_records_the_files_behind_its_prompt():
    im, findings, layers = model()
    findings[0].files, findings[1].files = ["//w/d/uart.c"], ["//w/include/hal/regs.h"]
    node_files = {"N1": ["//w/hal/regs.c"], "N2": ["//w/d/uart.c"], "N3": ["//w/svc/logger.c"]}
    board = _board(1)
    build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: {"what": "flush drops -2", "cites": ["N3"]})),
                     board=board, node_files=node_files)
    assert board.flows[0].what_source == "llm" and board.flows[0].what_files == ["//w/d/uart.c", "//w/svc/logger.c"]
    assert board.about.intent_files == ["//w/d/uart.c", "//w/hal/regs.c", "//w/include/hal/regs.h"]
    run_job(fake_llm(lambda s, u: {"explanation": "e"}), finding_job(_ctx(findings, im, node_files), findings[0]))
    assert findings[0].explain_files == ["//w/d/uart.c", "//w/hal/regs.c", "//w/svc/logger.c"]   # nodes + neighbours
    findings[1].files = None
    run_job(fake_llm(lambda s, u: {"explanation": "e"}), finding_job(_ctx(findings, im, node_files), findings[1]))
    assert findings[1].explain_files is None                                            # an unknown input: unknown


def test_prompts_carry_the_style_guide_and_one_diataxis_mode_each():
    from codetortoise.llm.style import MODES, STYLE
    im, findings, layers = model()
    seen = []

    def respond(system, user):
        seen.append((system, user))
        return _respond(lambda u: {"what": "w", "cites": ["N3"]})(system, user)
    llm = fake_llm(respond)
    build_storyboard(im, findings, layers, {}, llm, board=_board(1))
    run_job(llm, finding_job(_ctx(findings, im), findings[0]))
    assert seen and all(STYLE in system for system, _ in seen)
    kinds = {k: [u for _, u in seen if marker in u] for k, marker in [
        ("explain", "Explain the risk"), ("flow", "Describe this call flow"), ("summary", "Summarize the whole change")]}
    assert all(kinds.values())
    assert all(MODES["explanation"] in u and MODES["how-to"] in u for u in kinds["explain"])
    assert all(MODES["explanation"] in u for u in kinds["summary"])
    assert all(MODES["explanation"] in u and MODES["headline"] in u for u in kinds["flow"])


def test_ai_text_that_breaks_the_style_is_dropped_for_the_deterministic_text():
    im, findings, layers = model()
    board = _board(1)

    def respond(system, user):
        if "Describe this call flow" in user:
            return {"what": "Please simply check the result.", "title": "t", "cites": ["N3"]}
        return {"summary": "Please read this.", "risk": "medium", "cites": ["F1"]}
    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond), board=board)
    assert (board.flows[0].what, board.flows[0].what_source) == ("template what", "template")
    assert board.about.intent == "template intent" and sb.style_dropped == 2
    dropped = run_job(fake_llm(lambda s, u: {
        "explanation": "This is just wrong!", "verify_steps": ["Check that logger_flush handles -2.", "The caller ignores it."],
        "hypotheses": [{"text": "Simply put, it breaks.", "cites": ["N1"]},
                       {"text": "uart_send can now return -2.", "cites": ["N2"]}]}),
        finding_job(_ctx(findings, im), findings[0]))
    assert findings[0].explanation is None and findings[0].verify_steps == ["Check that logger_flush handles -2."]
    assert [h.text for h in findings[0].hypotheses] == ["uart_send can now return -2."] and dropped == 3


def test_a_flow_title_that_breaks_the_headline_rules_keeps_the_template_title():
    im, findings, layers = model()
    board = _board(1)
    sb = build_storyboard(im, findings, layers, {}, fake_llm(_respond(
        lambda u: {"what": "logger_flush drops -2.", "title": "logger_flush drops the new -2 result on every flush.",
                   "cites": ["N3"]})), board=board)
    assert board.flows[0].what == "logger_flush drops -2." and board.flows[0].title == "template title"
    assert sb.style_dropped == 1


def _story_details(n=2):
    from codetortoise.stories import Story, StoryDetail
    out = []
    for i in range(1, n + 1):
        st = Story(id=f"S{i}", kind="behaviour", title=f"template {i}", summary="template summary", nodes=["N3"],
                   flows=["FL1"], findings=["F1"])
        out.append(StoryDetail(story=st, board=_board(1)))
    return out


def test_the_upfront_pass_retells_the_top_stories_only():
    im, findings, layers = model()
    details = _story_details(3)
    asked = []

    def respond(system, user):
        asked.append(user)
        if "Retell this change story" in user:
            return {"title": "logger_flush drops -2", "summary": "uart_send can now return -2 and logger_flush drops it.",
                    "cites": ["N3"]}
        return _respond(lambda u: {"what": "w", "cites": []})(system, user)
    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(0), stories=details, upfront_stories=2)
    assert [d.story.text_source for d in details] == ["llm", "llm", "template"]
    assert details[0].story.title == "logger_flush drops -2"
    assert details[0].story.summary == "uart_send can now return -2 and logger_flush drops it."
    prompt = next(u for u in asked if "Retell this change story" in u)
    assert "template 1" in prompt and "logger_flush → uart_send" in prompt and "F1" in prompt


def test_a_story_answer_that_cites_nothing_of_the_story_keeps_the_template():
    im, findings, layers = model()
    details = _story_details(1)

    def respond(system, user):
        if "Retell this change story" in user:
            return {"title": "made up", "summary": "Something else entirely.", "cites": ["N99"]}
        return _respond(lambda u: {"what": "w", "cites": []})(system, user)
    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(0), stories=details, upfront_stories=3)
    assert details[0].story.text_source == "template" and details[0].story.title == "template 1"


def test_a_retold_story_records_the_files_behind_its_prompt():
    im, findings, layers = model()
    findings[0].files = ["//w/d/uart.c"]
    node_files = {"N1": ["//w/hal/regs.c"], "N2": ["//w/d/uart.c"], "N3": ["//w/svc/logger.c"]}
    details = _story_details(2)

    def respond(system, user):
        if "Retell this change story" in user:
            return {"title": "logger_flush drops -2", "summary": "uart_send can now return -2 and logger_flush drops it.",
                    "cites": ["N3"]}
        return _respond(lambda u: {"what": "w", "cites": []})(system, user)
    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(0), stories=details, upfront_stories=1,
                     node_files=node_files)
    assert details[0].story.text_files == ["//w/d/uart.c", "//w/svc/logger.c"]     # its code, its flow's and F1's
    assert details[1].story.text_source == "template" and details[1].story.text_files is None


def test_the_upfront_pass_explains_high_findings_only_up_to_the_cap():
    im, findings, layers = model()
    findings.append(Finding(id="F3", kind="contract", severity="high", title="t", summary="s", nodes=["N1"]))
    asked = []

    def respond(system, user):
        if "Explain the risk" in user:
            asked.append(user)
            return {"explanation": "uart_send can now return -2 and logger_flush drops it.", "verify_steps": [],
                    "hypotheses": []}
        return _respond(lambda u: {"what": "w", "cites": []})(system, user)
    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(0), upfront_findings=1)
    assert len(asked) == 1 and "regs.h" in asked[0]                                # F2: the first high finding
    assert findings[1].explanation == "uart_send can now return -2 and logger_flush drops it."
    assert findings[0].explanation is None and findings[2].explanation is None    # medium; past the cap
    asked.clear()
    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(0), upfront_findings=0)
    assert asked == []                                                              # a cap of 0 explains none up front


def test_ai_titles_naming_node_or_finding_ids_keep_the_template_title():
    im, findings, layers = model()
    details = _story_details(1)
    board = _board(1)

    def respond(system, user):
        if "Retell this change story" in user:
            return {"title": "uart_send changes reach N3", "summary": "uart_send can now return -2 and logger_flush drops it.",
                    "cites": ["N3"]}
        if "Describe this call flow" in user:
            return {"what": "logger_flush drops -2.", "title": "F1 drops the new result", "cites": ["N3"]}
        return _respond(lambda u: {})(system, user)
    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond), board=board, stories=details, upfront_stories=1)
    assert details[0].story.title == "template 1" and details[0].story.text_source == "template"
    assert board.flows[0].title == "template title"
    assert sb.style_dropped == 2
