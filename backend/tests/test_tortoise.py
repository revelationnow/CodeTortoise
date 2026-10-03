"""@tortoise answers questions in comment threads, reading the code it needs within a cap (spec 2026-10-03 §5)."""
import json

import httpx
import pytest
from helpers import make_services
from test_web import InlineRunner, login

from codetortoise.llm.client import LlmClient
from codetortoise.web.app import create_app, make_authenticator

UART = "//fixture/driver/uart.c"


class Script:
    """A fake model: `steps` are replies given in order (the last repeats); records every prompt."""

    def __init__(self, *steps):
        self.steps, self.prompts = list(steps), []

    def handler(self, req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": []})
        user = json.loads(req.content)["messages"][1]["content"]
        if "Give each level" in user:                                                  # layer naming
            return self._reply({"layers": []})
        if "Summarize the whole change" in user or "Describe this call flow" in user:   # the up-front pass
            return self._reply({"summary": "s", "risk": "high", "cites": []} if "Summarize" in user
                               else {"what": "w", "cites": []})
        self.prompts.append(user)
        step = self.steps[min(len(self.prompts) - 1, len(self.steps) - 1)]
        return self._reply(step(user) if callable(step) else step)

    @staticmethod
    def _reply(obj):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(obj)}}],
                                         "usage": {"prompt_tokens": 500, "completion_tokens": 50}})


@pytest.fixture
def world(fx, tmp_path):
    def make(script, **budget):
        llm = LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(script.handler), sleep=lambda s: None)
        svc = make_services(fx, tmp_path / str(len(budget)) / str(id(script)), llm=llm)
        for k, v in budget.items():
            setattr(svc.cfg.llm.budget, k, v)
        app = create_app(svc, InlineRunner(svc), make_authenticator(svc))
        owner = login(app, "owner")
        rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
        return svc, app, rid
    return make


def _ask(client, rid, body, kind="line", anchor=None, parent=None):
    anchor = anchor if anchor is not None else {"path": UART, "side": "new", "line": 17}
    return client.post(f"/api/reviews/{rid}/comments",
                       json={"body": body, "anchor_kind": kind, "anchor": anchor, "parent_id": parent}).json()


def _reply_to(client, rid, cid):
    return [c for c in client.get(f"/api/reviews/{rid}/comments").json() if c["parent_id"] == cid and c["author"] == "tortoise"]


def test_a_mention_reads_code_then_answers_in_the_thread(world):
    script = Script({"action": "read", "read": {"kind": "callers", "name": "uart_send"}, "why": "who handles -2"},
                    {"action": "answer", "text": "logger_flush ignores the -2 that uart_send now returns.",
                     "cites": ["N3", "//fixture/service/logger.c"]})
    svc, app, rid = world(script)
    bob = login(app, "bob")
    q = _ask(bob, rid, "@tortoise who handles the new -2?")
    [r] = _reply_to(bob, rid, q["id"])
    assert r["body"] == "logger_flush ignores the -2 that uart_send now returns."
    meta = r["ai_meta"]
    assert meta["pending"] is False and meta["read"] == ["callers of uart_send"] and meta["calls"] == 2
    assert {UART, "//fixture/service/logger.c"} <= set(meta["files"])
    assert "int uart_send" in script.prompts[0] and "@tortoise who handles the new -2?" in script.prompts[0]
    assert "logger_flush" in script.prompts[1] and "uart_send(lg->uart" in script.prompts[1]   # the read's result
    u = svc.ledger.usage(rid)
    assert u["by_purpose"].get("mention") == 2 and u["by_person"].get("bob") == 2


def test_the_last_round_must_answer(world):
    script = Script(lambda u: {"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]}
                    if "You must answer now" in u else {"action": "read", "read": {"kind": "search", "name": "uart_send"}})
    svc, app, rid = world(script, per_mention=3)
    q = _ask(login(app, "bob"), rid, "@tortoise what changed?")
    [r] = _reply_to(login(app, "bob"), rid, q["id"])
    assert r["body"] == "uart_send can now return -2." and r["ai_meta"]["calls"] == 3
    assert "You must answer now" in script.prompts[2] and "You must answer now" not in script.prompts[1]


def test_reads_stay_inside_the_workspace(world):
    script = Script({"action": "read", "read": {"kind": "file", "path": "/etc/passwd", "from": 1, "to": 5}},
                    {"action": "read", "read": {"kind": "file", "path": "//other/depot/x.c", "from": 1, "to": 5}},
                    {"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
    svc, app, rid = world(script)
    q = _ask(login(app, "bob"), rid, "@tortoise read something odd")
    [r] = _reply_to(login(app, "bob"), rid, q["id"])
    assert "not allowed" in script.prompts[1] and "not allowed" in script.prompts[2]
    assert "root:" not in "".join(script.prompts) and r["ai_meta"]["read"] == []


def test_an_uncited_answer_gets_one_more_round(world):
    script = Script({"action": "answer", "text": "It is probably fine.", "cites": []},
                    {"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
    svc, app, rid = world(script)
    q = _ask(login(app, "bob"), rid, "@tortoise is this safe?")
    [r] = _reply_to(login(app, "bob"), rid, q["id"])
    assert r["body"] == "uart_send can now return -2." and "cite" in script.prompts[1].lower()


def test_limits_no_llm_edits_and_its_own_replies(world, fx, tmp_path):
    script = Script({"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
    svc, app, rid = world(script, per_review=2)                               # the up-front pass used both
    bob = login(app, "bob")
    q = _ask(bob, rid, "@tortoise anything?")
    [r] = _reply_to(bob, rid, q["id"])
    assert r["body"].startswith("I couldn't answer: this review has used its 2 AI calls") and script.prompts == []
    bob.patch(f"/api/comments/{q['id']}", json={"body": "@tortoise edited"})
    assert len(_reply_to(bob, rid, q["id"])) == 1                            # editing never asks again
    assert bob.patch(f"/api/comments/{r['id']}", json={"body": "x"}).status_code == 403
    plain = make_services(fx, tmp_path / "plain")
    app2 = create_app(plain, InlineRunner(plain), make_authenticator(plain))
    o2 = login(app2, "owner")
    rid2 = o2.post("/api/reviews", json={"cls": [101]}).json()["id"]
    q2 = _ask(o2, rid2, "@tortoise hello")
    [r2] = _reply_to(o2, rid2, q2["id"])
    assert r2["body"] == "I can't answer: no AI is configured for CodeTortoise."
    assert _ask(o2, rid2, "mail me at someone@tortoise.example")["id"] and len(o2.get(f"/api/reviews/{rid2}/comments").json()) == 3


def test_a_follow_up_sees_the_thread_so_far(world):
    script = Script({"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
    svc, app, rid = world(script)
    bob = login(app, "bob")
    q = _ask(bob, rid, "@tortoise what changed?")
    _ask(bob, rid, "@tortoise and who reads uart_errors?", parent=q["id"])
    assert "uart_send can now return -2." in script.prompts[1] and "what changed?" in script.prompts[1]
    assert len(_reply_to(bob, rid, q["id"])) == 2


def test_each_anchor_kind_brings_its_context(world):
    script = Script({"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
    svc, app, rid = world(script)
    board = svc.store.get_blob(rid, "board")
    send = next(n for n in board["nodes"] if n["label"] == "uart_send")
    bob = login(app, "bob")
    _ask(bob, rid, "@tortoise f?", "function", {"key": send["key"]})
    _ask(bob, rid, "@tortoise finding?", "finding", {"kind": "contract", "title": "uart_send: new return value(s) -2"})
    _ask(bob, rid, "@tortoise review?", "review", {})
    assert "int uart_send" in script.prompts[0]
    assert "new return value(s) -2" in script.prompts[1]
    assert "FLOWS" in script.prompts[2] and "FINDINGS" in script.prompts[2]


def test_a_full_prompt_drops_the_oldest_reads_first(world):
    calls = []

    def step(u):                                    # reads uart.c from line 1, 2, 3, ... until it must answer
        calls.append(u)
        n = len(calls) - 1
        return ({"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]} if "must answer" in u
                else {"action": "read", "read": {"kind": "file", "path": UART, "from": n + 1, "to": 40}})
    script = Script(step)
    svc, app, rid = world(script, per_mention=14)
    svc.cfg.llm.max_context_tokens = 1000           # 2000 tokens a call: 13 reads of ~800 characters don't all fit
    _ask(login(app, "bob"), rid, "@tortoise what changed?")
    last = script.prompts[-1]
    assert "QUESTION: @tortoise what changed?" in last and "CONTEXT:" in last and "must answer" in last
    assert f"READ file {UART} from 13" in last and f"READ file {UART} from 1 " not in last
    assert "[truncated]" not in last
