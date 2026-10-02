import json

import httpx

from codetortoise.detectors.base import Evidence, Finding
from codetortoise.impact import Edge, ImpactModel, Node
from codetortoise.layers import Layer, LayerModel
from codetortoise.llm.client import LlmClient
from codetortoise.llm.storyboard import Cited, budget, build_storyboard, ground, name_layers, skeleton


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


def test_llm_storyboard_is_grounded():
    im, findings, layers = model()

    def respond(system, user):
        if "Explain the risk" in user:
            return {"explanation": "exp", "verify_steps": ["check callers"],
                    "hypotheses": [{"text": "flush drops -2", "cites": ["N3", "F1"]},
                                   {"text": "made up", "cites": []}]}
        if "narrative for this architectural layer" in user:
            return {"narrative": "story", "cites": ["N2", "BOGUS"],
                    "cross_layer_effects": [{"text": "logger affected", "cites": ["N3"]}]}
        return {"summary": "sum", "risk": "medium", "review_order": ["N2", "N1", "NX"], "cites": ["F1"]}

    sb = build_storyboard(im, findings, layers, {"N2": "   9 int uart_send(...)"}, fake_llm(respond))
    assert sb.llm_used and sb.summary == "sum" and sb.risk == "high"  # LLM said medium; findings say high
    assert sb.review_order == ["N2", "N1"]
    assert findings[0].explanation == "exp" and findings[0].verify_steps == ["check callers"]
    assert [h.text for h in findings[0].hypotheses] == ["flush drops -2"]
    ch = sb.chapters[2]
    assert ch.narrative == "story" and ch.cites == ["N2"] and ch.verified
    assert [c.text for c in ch.cross_layer_effects] == ["logger affected"]


def test_llm_failure_keeps_deterministic_storyboard():
    im, findings, layers = model()
    llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(500)),
                    sleep=lambda s: None)
    sb = build_storyboard(im, findings, layers, {}, llm)
    assert not sb.llm_used and "failed after" in sb.llm_error
    assert sb.chapters[1].narrative.startswith("Changed: hal_write")


def test_name_layers():
    _, _, layers = model()
    llm = fake_llm(lambda s, u: {"layers": [{"level": 0, "name": "HAL API", "description": "d"},
                                            {"level": 2, "name": "Drivers"}]})
    out = name_layers(layers, llm)
    assert [l.name for l in out.layers] == ["L0: HAL API", "L1: hal", "L2: Drivers"]


def test_llm_cannot_lower_risk_below_findings():
    im, findings, layers = model()

    def respond(system, user):
        if "Explain the risk" in user:
            return {"explanation": "e"}
        if "narrative for this architectural layer" in user:
            return {"narrative": "n", "cites": ["N1"]}
        return {"summary": "all fine", "risk": "low", "cites": ["F1"]}

    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond))
    assert sb.llm_used and sb.risk == "high"


def test_unexpected_llm_client_exception_keeps_skeleton():
    im, findings, layers = model()

    class Exploding:
        def complete_json(self, *a, **k):
            raise TypeError("boom")

    sb = build_storyboard(im, findings, layers, {}, Exploding())
    assert not sb.llm_used and "boom" in sb.llm_error and sb.chapters


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


def test_llm_writes_grounded_flow_narratives_and_the_change_intent():
    im, findings, layers = model()
    board = _board(3)
    replies = iter([{"what": "flush drops -2", "title": "logger_flush drops -2 on flush", "cites": ["N3", "F1"]},
                    {"what": "uncited guess", "cites": ["N99"]},
                    {"what": "not asked for", "cites": ["N3"]}])
    sb = build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: next(replies))),
                          board=board, max_flow_narratives=2)
    assert sb.llm_used
    assert [(f.what, f.what_source) for f in board.flows] == [
        ("flush drops -2", "llm"), ("template what", "template"), ("template what", "template")]
    assert [f.title for f in board.flows] == ["logger_flush drops -2 on flush", "template title", "template title"]
    assert board.about.intent == "the change adds tx stats" and board.about.intent_source == "llm"
    # LLM text no longer depends only on the template's files: unknown until its prompt's files are recorded
    assert board.flows[0].what_files is None and board.about.intent_files is None


def test_llm_text_records_the_files_behind_its_prompt():
    im, findings, layers = model()
    findings[0].files, findings[1].files = ["//w/d/uart.c"], ["//w/include/hal/regs.h"]
    node_files = {"N1": ["//w/hal/regs.c"], "N2": ["//w/d/uart.c"], "N3": ["//w/svc/logger.c"]}
    board = _board(1)
    build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: {"what": "flush drops -2", "cites": ["N3"]})),
                     board=board, node_files=node_files)
    # the flow's prompt: its steps (N3, N2) and its finding F1
    assert board.flows[0].what_source == "llm" and board.flows[0].what_files == ["//w/d/uart.c", "//w/svc/logger.c"]
    # a finding's explanation also saw its nodes' neighbours (N3 calls N2, N2 calls N1)
    assert findings[0].explain_files == ["//w/d/uart.c", "//w/hal/regs.c", "//w/svc/logger.c"]
    assert findings[1].explain_files == ["//w/include/hal/regs.h"]
    # the intent summarises every chapter (its nodes and findings) and the findings
    assert board.about.intent_files == ["//w/d/uart.c", "//w/hal/regs.c", "//w/include/hal/regs.h"]


def test_llm_text_is_unknown_when_a_prompt_file_is():
    im, findings, layers = model()
    findings[0].files = None                                   # F1 stored before tags
    findings[1].files = ["//w/include/hal/regs.h"]
    board = _board(1)
    build_storyboard(im, findings, layers, {}, fake_llm(_respond(lambda u: {"what": "w", "cites": ["N3"]})),
                     board=board, node_files={"N1": ["//w/hal/regs.c"], "N2": ["//w/d/uart.c"], "N3": ["//w/svc/logger.c"]})
    assert board.flows[0].what_files is None and findings[0].explain_files is None and board.about.intent_files is None
    assert findings[1].explain_files == ["//w/include/hal/regs.h"]

def test_llm_calls_run_concurrently():
    import threading
    im, findings, layers = model()
    board = _board(2)
    gate = threading.Barrier(4, timeout=5)   # 2 findings + 2 flows must be in flight together

    def respond(system, user):
        if "Explain the risk" in user or "Describe this call flow" in user:
            gate.wait()
        return _respond(lambda u: {"what": "w", "cites": ["N3"]})(system, user)

    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond), board=board, concurrency=4)
    assert sb.llm_used, sb.llm_error
    assert [f.what_source for f in board.flows] == ["llm", "llm"]


def test_llm_failure_keeps_template_flow_text():
    im, findings, layers = model()
    board = _board(1)
    llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(500)),
                    sleep=lambda s: None)
    sb = build_storyboard(im, findings, layers, {}, llm, board=board, concurrency=4)
    assert not sb.llm_used and sb.llm_error
    assert board.flows[0].what == "template what" and board.about.intent_source == "template"


def test_prompts_carry_the_style_guide_and_one_diataxis_mode_per_output():
    from codetortoise.llm.style import MODES, STYLE
    im, findings, layers = model()
    seen = []

    def respond(system, user):
        seen.append((system, user))
        return _respond(lambda u: {"what": "w", "cites": ["N3"]})(system, user)
    build_storyboard(im, findings, layers, {}, fake_llm(respond), board=_board(1))
    assert seen and all(STYLE in system for system, _ in seen)
    by_kind = {k: [u for _, u in seen if marker in u] for k, marker in [
        ("explain", "Explain the risk"), ("chapter", "narrative for this architectural layer"),
        ("flow", "Describe this call flow"), ("summary", "Summarize the whole change")]}
    assert all(by_kind.values())
    assert all(MODES["explanation"] in u and MODES["how-to"] in u for u in by_kind["explain"])
    assert all(MODES["explanation"] in u for u in by_kind["chapter"] + by_kind["summary"])
    assert all(MODES["explanation"] in u and MODES["headline"] in u for u in by_kind["flow"])


def test_llm_text_that_breaks_the_style_is_dropped_for_the_deterministic_text():
    im, findings, layers = model()
    board = _board(1)

    def respond(system, user):
        if "Explain the risk" in user:
            return {"explanation": "This is just wrong!",
                    "verify_steps": ["Check that logger_flush handles -2.", "The caller ignores it."],
                    "hypotheses": [{"text": "Simply put, it breaks.", "cites": ["N1"]},
                                   {"text": "uart_send can now return -2.", "cites": ["N2"]}]}
        if "Describe this call flow" in user:
            return {"what": "Please simply check the result.", "title": "t", "cites": ["N3"]}
        if "Summarize the whole change" in user:
            return {"summary": "Please read this.", "risk": "medium", "cites": ["F1"]}
        return _respond(lambda u: {})(system, user)
    sb = build_storyboard(im, findings, layers, {}, fake_llm(respond), board=board)
    assert all(f.explanation is None for f in findings)
    assert [f.verify_steps for f in findings] == [["Check that logger_flush handles -2."]] * 2
    assert [[h.text for h in f.hypotheses] for f in findings] == [["uart_send can now return -2."]] * 2
    assert (board.flows[0].what, board.flows[0].what_source) == ("template what", "template")
    assert board.about.intent == "template intent" and board.about.intent_source == "template"
    assert sb.style_dropped == 8          # 2 explanations, 2 steps, 2 hypotheses, 1 flow, 1 summary


def test_a_flow_title_that_breaks_the_headline_rules_keeps_the_template_title():
    im, findings, layers = model()
    board = _board(1)
    sb = build_storyboard(im, findings, layers, {}, fake_llm(_respond(
        lambda u: {"what": "logger_flush drops -2.", "title": "logger_flush drops the new -2 result on every flush.",
                   "cites": ["N3"]})), board=board)
    assert board.flows[0].what == "logger_flush drops -2." and board.flows[0].title == "template title"
    assert sb.style_dropped == 1
