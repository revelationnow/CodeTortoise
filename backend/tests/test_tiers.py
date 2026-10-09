"""A strong-model piece of work is tried fresh, then on the weak model (spec 2026-10-08-llm-robustness §5)."""
import json

import httpx
import pytest
from pydantic import BaseModel

from codetortoise.config import LlmBudget
from codetortoise.llm.client import LlmClient, LlmTruncated
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.tiers import TiersFailed, done_text, failure_text, tried_note, try_tiers
from codetortoise.store import Store


class Out(BaseModel):
    n: int


def _ask(llm):
    return llm.complete_json("s", "u", Out)


def _client(model, handler, **kw):
    return LlmClient("http://llm/v1", "k", model, transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def _reply(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _logging(model, replies, seen, **kw):
    def handler(req):
        seen.append((model, json.loads(req.content).get("max_tokens")))
        return replies(req)
    return _client(model, handler, **kw)


def test_a_strong_answer_is_used_as_it_is():
    t = try_tiers(None, None, "stories", "chunk 1", _ask, _client("big", lambda r: _reply('{"n": 1}')),
                  _client("small", lambda r: _reply('{"n": 2}')))
    assert (t.value.n, t.tier, t.model, t.failures, t.strong_unreachable) == (1, "strong", "big", [], False)


def test_a_failing_strong_model_is_tried_fresh_at_double_its_limit_then_the_weak_model_at_four_times():
    seen = []
    strong = _logging("big", lambda r: _reply("not json"), seen, max_output_tokens=1000)
    weak = _logging("small", lambda r: _reply('{"n": 2}'), seen, max_output_tokens=500)
    t = try_tiers(None, None, "stories", "chunk 1", _ask, strong, weak)
    assert (t.value.n, t.tier, t.model) == (2, "weak", "small")
    assert t.failures == ["big: invalid JSON twice", "fresh try: invalid JSON twice"]
    assert seen == [("big", 1000), ("big", 2000), ("big", 2000), ("big", 4000), ("small", 4000)]
    assert strong.max_output_tokens == 1000                          # the tries' views leave the client as it was


def test_a_fresh_strong_answer_is_marked_fresh():
    replies = iter(["not json", "still not", '{"n": 3}'])
    t = try_tiers(None, None, "review", "story a", _ask, _client("big", lambda r: _reply(next(replies))), None)
    assert (t.value.n, t.tier, t.failures) == (3, "fresh", ["big: invalid JSON twice"])
    assert done_text(t, "judged its findings") == "big judged its findings on a fresh try"


def test_an_unreachable_strong_model_is_not_tried_fresh():
    seen = []
    strong = _logging("big", lambda r: httpx.Response(503), seen)
    t = try_tiers(None, None, "stories", "chunk 1", _ask, strong, _client("small", lambda r: _reply('{"n": 2}')))
    assert (t.tier, t.failures, t.strong_unreachable) == ("weak", ["big: unreachable"], True)
    assert len(seen) == 3                                             # one try's three attempts, no fresh try


def test_skip_strong_goes_straight_to_the_weak_model():
    seen = []
    strong = _logging("big", lambda r: _reply('{"n": 1}'), seen)
    t = try_tiers(None, None, "stories", "chunk 2", _ask, strong, _client("small", lambda r: _reply('{"n": 2}')),
                  skip_strong=True)
    assert seen == [] and (t.tier, t.failures) == ("weak", [])


def test_a_refused_try_stops_the_tries():
    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            raise Refused("this review has used its 1 tier-1 AI calls")
    with pytest.raises(Refused):
        try_tiers(Budget(), 1, "stories", "chunk 1", _ask, _client("big", lambda r: _reply('{"n": 1}')),
                  _client("small", lambda r: _reply('{"n": 2}')))


def test_without_a_weak_model_every_failure_is_reported():
    strong = _client("big", lambda r: httpx.Response(400, text="bad request"))
    with pytest.raises(TiersFailed) as e:
        try_tiers(None, None, "threads", "threads", _ask, strong, None)
    assert e.value.failures == ["big: HTTP 400: bad request", "fresh try: HTTP 400: bad request"]
    assert e.value.strong_unreachable is False


def test_each_try_is_its_own_ledger_call_with_its_model(tmp_path):
    store = Store(tmp_path / "t.db")
    rid = store.create_review("t", "owner", [1])
    ledger = Ledger(store, LlmBudget())
    try_tiers(ledger, rid, "stories", "chunk 1", _ask, _client("big", lambda r: _reply("not json")),
              _client("small", lambda r: _reply('{"n": 2}')))
    assert [(c["purpose"], c["target"], c["model"], c["outcome"]) for c in ledger.usage(rid)["calls"]] == [
        ("stories", "chunk 1", "big", "failed"), ("stories", "chunk 1 (fresh)", "big", "failed"),
        ("stories", "chunk 1 (weak)", "small", "ok")]


def test_failures_and_notes_are_worded_for_people():
    assert failure_text(LlmTruncated(16384, 16384)) == "reply cut off at 16384 tokens"
    assert failure_text(ValueError("no answer within the rounds allowed")) == "ValueError: no answer within the rounds allowed"
    assert tried_note("chunk 2", ["big: reply cut off at 16384 tokens", "fresh try: unreachable"],
                      "small grouped its pieces") == \
        "chunk 2: big: reply cut off at 16384 tokens; fresh try: unreachable; small grouped its pieces"
