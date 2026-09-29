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
    assert sb.llm_used and sb.summary == "sum" and sb.risk == "medium"
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
