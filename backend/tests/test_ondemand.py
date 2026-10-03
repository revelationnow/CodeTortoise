"""On-demand explanations, usage and the owner's budget control (spec 2026-10-03 §4, §6)."""
import json

import httpx
import pytest
from helpers import make_services
from test_web import InlineRunner, login

from codetortoise.config import LlmBudget
from codetortoise.llm.client import LlmClient
from codetortoise.web.app import create_app, make_authenticator

CITES = [f"N{i}" for i in range(1, 40)] + [f"F{i}" for i in range(1, 10)]


def _reply(user: str) -> dict:
    if "Explain the risk" in user:
        return {"explanation": "uart_send can now return -2, and logger_flush drops it.", "verify_steps": ["Check logger_flush."],
                "hypotheses": [{"text": "uart_errors may count twice.", "cites": ["N9"]}]}
    if "Describe this call flow" in user:
        return {"what": "main reaches uart_send through logger_flush.", "title": "flush drops -2", "cites": CITES}
    if "Summarise this file" in user:
        return {"summary": "uart.c now counts errors through an alias.", "check": ["Check uart_errors readers."],
                "cites": ["N9"]}
    return {"summary": "The change adds tx stats.", "risk": "high", "cites": CITES}


@pytest.fixture
def ai(fx, tmp_path):
    seen = []

    def handler(req):
        if req.method == "GET":                                        # the health check's /models
            return httpx.Response(200, json={"data": []})
        user = json.loads(req.content)["messages"][1]["content"]
        seen.append(user)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(_reply(user))}}],
                                         "usage": {"prompt_tokens": 1000, "completion_tokens": 100}})
    llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    svc = make_services(fx, tmp_path, llm=llm)
    svc.cfg.llm.base_url = "http://llm/v1"
    svc.cfg.llm.upfront_flows = 1                                      # the fixture has 3 flows: leave 2 for later
    app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    return svc, app, owner, rid, seen


def test_a_reviewer_explains_a_flow_and_everyone_sees_it(ai):
    svc, app, owner, rid, _ = ai
    bob = login(app, "bob")
    flows = owner.get(f"/api/reviews/{rid}/board").json()["flows"]
    later = flows[-1]
    assert later["what_source"] == "template"                         # not in the up-front pass
    r = bob.post(f"/api/reviews/{rid}/explain", json={"kind": "flow", "target": later["id"]})
    assert r.status_code == 202
    after = next(f for f in owner.get(f"/api/reviews/{rid}/board").json()["flows"] if f["id"] == later["id"])
    assert after["what"] == "main reaches uart_send through logger_flush." and after["what_source"] == "llm"
    u = bob.get(f"/api/reviews/{rid}/ai").json()
    assert u["by_person"].get("bob") == 1 and u["me_today"] == 1 and u["jobs"][-1]["status"] == "done"


def test_explaining_a_finding_and_summarising_a_file(ai):
    svc, app, owner, rid, seen = ai
    assert owner.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": "F1"}).status_code == 202
    f1 = next(f for f in owner.get(f"/api/reviews/{rid}/findings").json() if f["id"] == "F1")
    assert f1["explanation"].startswith("uart_send can now return -2") and f1["explain_files"]
    assert owner.post(f"/api/reviews/{rid}/explain",
                      json={"kind": "file", "target": "//fixture/driver/uart.c"}).status_code == 202
    s = owner.get(f"/api/reviews/{rid}/ai").json()["file_summaries"]["//fixture/driver/uart.c"]
    assert s["summary"] == "uart.c now counts errors through an alias." and s["check"] == ["Check uart_errors readers."]
    assert "//fixture/driver/uart.c" in s["files"] and s["by"] == "owner"
    prompt = next(u for u in seen if "Summarise this file" in u)
    assert "uart_send" in prompt and "+" in prompt                    # the diff and the functions' facts


def test_explain_is_refused_over_the_budget_and_the_owner_raises_it(ai):
    svc, app, owner, rid, _ = ai
    bob = login(app, "bob")
    used = owner.get(f"/api/reviews/{rid}/ai").json()["used"]
    assert used == 2                                                   # the up-front pass: 1 flow + the summary
    assert bob.put(f"/api/reviews/{rid}/ai/budget", json={"budget": 10}).status_code == 403
    assert owner.put(f"/api/reviews/{rid}/ai/budget", json={"budget": used}).json()["budget"] == used
    r = bob.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": "F1"})
    assert r.status_code == 429 and "this review has used its 2 AI calls" in r.json()["detail"]
    owner.put(f"/api/reviews/{rid}/ai/budget", json={"budget": used + 5})
    assert bob.post(f"/api/reviews/{rid}/explain", json={"kind": "finding", "target": "F1"}).status_code == 202


def test_bad_targets_and_no_llm(ai, fx, tmp_path):
    svc, app, owner, rid, _ = ai
    assert owner.post(f"/api/reviews/{rid}/explain", json={"kind": "flow", "target": "FL99"}).status_code == 404
    assert owner.post(f"/api/reviews/{rid}/explain", json={"kind": "file", "target": "//fixture/nope.c"}).status_code == 404
    plain = make_services(fx, tmp_path / "p")
    app2 = create_app(plain, InlineRunner(plain), make_authenticator(plain))
    o2 = login(app2, "owner")
    rid2 = o2.post("/api/reviews", json={"cls": [101]}).json()["id"]
    assert o2.post(f"/api/reviews/{rid2}/explain", json={"kind": "finding", "target": "F1"}).status_code == 409
    assert o2.get(f"/api/reviews/{rid2}/ai").json()["llm"] is False


def test_the_ai_view_reports_limits_and_calls(ai):
    svc, app, owner, rid, _ = ai
    svc.cfg.llm.budget = LlmBudget(per_review=200, per_person_daily=100, per_mention=6)
    u = owner.get(f"/api/reviews/{rid}/ai").json()
    assert (u["budget"], u["me_limit"], u["per_mention"], u["llm"]) == (200, 100, 6, True)
    assert [c["purpose"] for c in u["calls"]] == ["flow", "summary"]
    assert all(c["prompt_tokens"] == 1000 for c in u["calls"])
    h = owner.get("/api/health").json()                               # + layer naming, once per index
    assert h["ai"]["calls_today"] == 3 and h["ai"]["limits"] == {"per_review": 200, "per_person_daily": 100,
                                                                 "per_mention": 6}


def test_an_answer_that_fails_the_checks_changes_nothing_and_says_why(ai, monkeypatch):
    svc, app, owner, rid, _ = ai
    good = _reply

    def bad(user):                     # uncited (flow, file) or off the house style (finding)
        if "Describe this call flow" in user:
            return {"what": "It is fine.", "cites": []}
        if "Explain the risk" in user:
            return {"explanation": "Simply put, it is fine!", "verify_steps": [], "hypotheses": []}
        if "Summarise this file" in user:
            return {"summary": "It is fine.", "check": [], "cites": []}
        return good(user)
    monkeypatch.setitem(globals(), "_reply", bad)
    f1 = next(f for f in owner.get(f"/api/reviews/{rid}/findings").json() if f["id"] == "F1")
    later = owner.get(f"/api/reviews/{rid}/board").json()["flows"][-1]
    for kind, target in (("flow", later["id"]), ("finding", "F1"), ("file", "//fixture/driver/uart.c")):
        assert owner.post(f"/api/reviews/{rid}/explain", json={"kind": kind, "target": target}).status_code == 202
        job = owner.get(f"/api/reviews/{rid}/ai").json()["jobs"][-1]
        assert job["status"] == "failed" and job["error"].startswith("the AI's answer didn't pass the checks"), (kind, job)
    assert next(f for f in owner.get(f"/api/reviews/{rid}/board").json()["flows"] if f["id"] == later["id"]) == later
    assert next(f for f in owner.get(f"/api/reviews/{rid}/findings").json() if f["id"] == "F1") == f1
    assert "//fixture/driver/uart.c" not in owner.get(f"/api/reviews/{rid}/ai").json()["file_summaries"]
