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
        if "Judge each side effect" in user:                                           # the run's verdicts
            return self._reply({"verdicts": []})
        if "Explain the risk of this finding" in user:                                 # the up-front pass
            return self._reply({"explanation": "e", "verify_steps": [], "hypotheses": []})
        if any(k in user for k in ("Summarize the whole change", "Describe this call flow",
                                   "Retell this change story")):
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
    u = svc.ledger.usage(rid)                          # the whole answer is one AI call, with every round's tokens
    assert u["by_purpose"].get("mention") == 1 and u["by_person"].get("bob") == 1
    [call] = [c for c in u["calls"] if c["purpose"] == "mention"]
    assert (call["prompt_tokens"], call["completion_tokens"], call["outcome"]) == (1000, 100, "ok")


def test_the_last_round_must_answer(world):
    script = Script(lambda u: {"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]}
                    if "You must answer now" in u else {"action": "read", "read": {"kind": "search", "name": "uart_send"}})
    svc, app, rid = world(script, per_mention=3)
    q = _ask(login(app, "bob"), rid, "@tortoise what changed?")
    [r] = _reply_to(login(app, "bob"), rid, q["id"])
    assert r["body"] == "uart_send can now return -2." and r["ai_meta"]["calls"] == 3
    assert "You must answer now" in script.prompts[2] and "You must answer now" not in script.prompts[1]



def test_the_owner_sets_a_reviews_round_cap(world):
    script = Script(lambda u: {"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]}
                    if "You must answer now" in u else {"action": "read", "read": {"kind": "search", "name": "uart_send"}})
    svc, app, rid = world(script)
    owner, bob = login(app, "owner"), login(app, "bob")
    assert owner.get(f"/api/reviews/{rid}/ai").json()["per_mention"] == 10           # the config's default
    assert bob.put(f"/api/reviews/{rid}/ai/rounds", json={"rounds": 3}).status_code == 403
    assert owner.put(f"/api/reviews/{rid}/ai/rounds", json={"rounds": 0}).status_code == 422
    assert owner.put(f"/api/reviews/{rid}/ai/rounds", json={"rounds": 3}).json() == {"rounds": 3}
    assert bob.get(f"/api/reviews/{rid}/ai").json()["per_mention"] == 3
    q = _ask(bob, rid, "@tortoise what changed?")
    [r] = _reply_to(bob, rid, q["id"])
    assert r["body"] == "uart_send can now return -2." and r["ai_meta"]["calls"] == 3 and r["ai_meta"]["of"] == 3
    assert "You must answer now" in script.prompts[2]
    assert svc.ledger.usage(rid)["by_purpose"]["mention"] == 1

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
    assert "new return value -2" in script.prompts[1]                   # the model reads the finding tidied
    assert "FLOWS" in script.prompts[2] and "FINDINGS" in script.prompts[2]



def test_a_story_a_flow_and_a_file_bring_their_context(world):
    script = Script({"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
    svc, app, rid = world(script)
    bob = login(app, "bob")
    story = bob.get(f"/api/reviews/{rid}/stories/S1").json()["story"]
    flow = svc.store.get_blob(rid, "board")["flows"][0]
    _ask(bob, rid, "@tortoise story?", "story", {"id": "S1"})
    _ask(bob, rid, "@tortoise flow?", "flow", {"id": flow["id"]})
    _ask(bob, rid, "@tortoise file?", "file", {"path": UART})
    assert f"STORY S1: {story['title']}" in script.prompts[0] and "FLOW " in script.prompts[0]
    assert f"FLOW {flow['id']}: {flow['title']}" in script.prompts[1] and flow["check"] in script.prompts[1]
    assert f"FILE {UART}" in script.prompts[2] and "int uart_send" in script.prompts[2]
    replies = [c for c in bob.get(f"/api/reviews/{rid}/comments").json() if c["author"] == "tortoise"]
    assert [r["anchor_kind"] for r in replies] == ["story", "flow", "file"]

def test_a_question_on_a_check_brings_the_check_its_place_and_source_line(world):
    script = Script({"action": "answer", "text": "flush ignores it.", "cites": []})
    svc, app, rid = world(script)
    bob = login(app, "bob")
    k = next(k for k in bob.get(f"/api/reviews/{rid}/reading").json()["checks"] if k["kind"] == "result")
    _ask(bob, rid, "@tortoise is this fine?", "check", {"key": k["key"]})
    assert f"CHECK (Result handled the old way): {k['text']}" in script.prompts[0]
    assert f"AT {k['path']}:{k['line']} in {k['function']}" in script.prompts[0]
    assert f"SOURCE LINE: {k['source_line']}" in script.prompts[0]


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


def test_a_bad_anchor_ends_the_answer_instead_of_leaving_it_pending(world):
    script = Script({"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
    svc, app, rid = world(script)
    bob = login(app, "bob")
    q = _ask(bob, rid, "@tortoise what changed?", anchor={"path": UART, "side": "new", "line": "seventeen"})
    [r] = _reply_to(bob, rid, q["id"])
    assert r["ai_meta"]["pending"] is False and r["body"].startswith("I couldn't answer:")


def test_a_file_outside_the_workspace_is_skipped_not_fatal(world):
    from codetortoise.llm.ondemand import context_for
    from codetortoise.llm.tortoise import _Reader
    svc, app, rid = world(Script({"action": "answer", "text": "x", "cites": []}))
    ctx, _, _, cs = context_for(svc, rid)
    reader = _Reader(svc, rid, ctx, cs)
    asked = []

    def where(paths):                      # P4Source.depots_for raises for paths p4 can't map
        asked.append(paths)
        raise RuntimeError("p4 where: not under client's root")
    svc.source.depots_for = where
    assert reader.text_of(local="/usr/include/stdio.h") is None and asked == []        # never sent to p4
    assert reader.text_of(local=str(svc.cfg.workspace.root / "driver" / "absent.c")) is None and len(asked) == 1


def test_a_restart_ends_pending_answers_and_running_calls(world):
    svc, app, rid = world(Script({"action": "answer", "text": "x", "cites": []}))
    r = svc.store.add_comment(rid, "tortoise", "thinking…", "review", {}, None)
    svc.store.set_ai_reply(r["id"], "thinking…", {"pending": True, "round": 2, "of": 6, "read": ["callers of uart_send"],
                                                  "files": [], "calls": 1, "error": None})
    svc.ledger.reserve(rid, "bob", "mention", str(r["id"]))           # a call in flight when the server stopped
    create_app(svc, InlineRunner(svc), make_authenticator(svc))       # the server starts again
    after = svc.store.get_comment(r["id"])
    assert after["ai_meta"]["pending"] is False and after["body"] == (
        "I couldn't answer: CodeTortoise restarted before the answer was finished. Ask again.")
    assert after["ai_meta"]["read"] == ["callers of uart_send"]
    assert [c["outcome"] for c in svc.ledger.usage(rid)["calls"] if c["purpose"] == "mention"] == ["failed"]


def test_deleting_the_question_stops_the_answer(world):
    holder = {}

    def step(u):                                  # the asker deletes the question while the first round runs
        holder["svc"].store.delete_comment(holder["q"])
        return {"action": "read", "read": {"kind": "callers", "name": "uart_send"}}
    script = Script(step)
    svc, app, rid = world(script)
    holder["svc"] = svc
    bob = login(app, "bob")
    orig = svc.store.add_comment

    def remember(*a, **k):                        # learn the question's id as it is posted
        c = orig(*a, **k)
        holder.setdefault("q", c["id"])
        return c
    svc.store.add_comment = remember
    _ask(bob, rid, "@tortoise who calls uart_send?")
    assert svc.ledger.usage(rid)["by_purpose"].get("mention") == 1        # no rounds after the delete


def test_the_read_list_says_what_was_actually_read(world):
    from codetortoise.llm.ondemand import context_for
    from codetortoise.llm.tortoise import _Read, _Reader
    svc, app, rid = world(Script({"action": "answer", "text": "x", "cites": []}))
    ctx, _, _, cs = context_for(svc, rid)
    reader = _Reader(svc, rid, ctx, cs)
    reader.run(_Read(kind="function", name="no_such_function"))                    # nothing found: not listed
    reader.text_of = lambda depot=None, local=None: (UART, "/* writes are not allowed here */\\n")
    reader.run(_Read(kind="file", path=UART, **{"from": 1, "to": 5}))                 # read, though it says "not allowed"
    assert reader.done == [f"{UART} 1–5"]


def test_an_oversized_newest_read_is_shortened_not_dropped():
    from codetortoise.llm.tortoise import _fit
    head = ["QUESTION: q", "THREAD SO FAR:\nbob: q", "CONTEXT:\nctx"]
    old, new = "READ file a ->\n" + "a" * 1000, "READ file b ->\n" + "b" * 20000
    out = _fit(head + [old, new], 2000)                        # 8000 characters
    assert "QUESTION: q" in out and "READ file b" in out and "[truncated]" in out and len(out) <= 8000
    assert "READ file a" not in out                             # the older read goes first


def test_a_thread_longer_than_the_prompt_still_keeps_the_newest_read():
    from codetortoise.llm.tortoise import _fit
    head = ["QUESTION: q", "THREAD SO FAR:\n" + "x" * 20000, "CONTEXT:\nctx"]
    out = _fit(head + ["READ callers uart_send ->\nuart_send(lg->uart"], 2000)
    assert out.startswith("QUESTION: q") and "uart_send(lg->uart" in out and len(out) <= 8000



def test_a_question_starts_from_its_anchor_s_story_and_the_change_overview(world):
    script = Script({"action": "answer", "text": "uart_send can now return -2.", "cites": ["N9"]})
    svc, app, rid = world(script)
    bob = login(app, "bob")
    story = bob.get(f"/api/reviews/{rid}/stories/S1").json()["story"]
    _ask(bob, rid, "@tortoise story?", "story", {"id": "S1"})
    context = script.prompts[0].split("CONTEXT:\n", 1)[1]
    assert context.startswith("BRIEF (") and f"STORY: {story['title']}" in context
    assert "CHANGE OVERVIEW:\nCHANGE: 2 CLs" in context
