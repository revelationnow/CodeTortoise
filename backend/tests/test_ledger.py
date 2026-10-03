"""Every AI call is counted; none is made over a limit (spec 2026-10-03 §2)."""
import json
import threading

import httpx
import pytest

from codetortoise.config import LlmBudget
from codetortoise.llm.client import LlmClient, LlmError
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.store import Store


def _llm(reply=None, fail=False, usage=(120, 30)):
    def handler(req):
        if fail:
            return httpx.Response(400, json={"error": "bad"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply or {"ok": True})}}],
                                         "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}})
    return LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def _ledger(tmp_path, **budget):
    store = Store(tmp_path / "t.db")
    rid = store.create_review("t", "owner", [1])
    return Ledger(store, LlmBudget(**budget)), store, rid


def _ask(llm):
    from pydantic import BaseModel

    class Out(BaseModel):
        ok: bool
    return llm.complete_json("s", "u", Out)


def test_a_call_is_recorded_with_its_tokens(tmp_path):
    ledger, _, rid = _ledger(tmp_path)
    out = ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)
    assert out.ok
    [row] = ledger.usage(rid)["calls"]
    assert (row["user"], row["purpose"], row["target"], row["outcome"]) == ("bob", "flow", "FL1", "ok")
    assert (row["prompt_tokens"], row["completion_tokens"]) == (120, 30)


def test_failures_count_and_refusals_are_recorded_but_not_made(tmp_path):
    ledger, _, rid = _ledger(tmp_path, per_review=2)
    with pytest.raises(LlmError):
        ledger.call(_llm(fail=True), rid, "bob", "flow", "FL1", _ask)
    ledger.call(_llm(), rid, "bob", "flow", "FL2", _ask)
    made = []
    with pytest.raises(Refused, match="this review has used its 2 AI calls; the owner can raise it"):
        ledger.call(_llm(), rid, "bob", "flow", "FL3", lambda llm: made.append(1))
    assert made == []
    u = ledger.usage(rid)
    assert [c["outcome"] for c in u["calls"]] == ["failed", "ok", "refused"] and u["used"] == 2 and u["budget"] == 2


def test_the_daily_limit_is_per_person_and_the_pipeline_is_exempt(tmp_path):
    ledger, store, rid = _ledger(tmp_path, per_person_daily=1)
    other = store.create_review("t2", "owner", [2])
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)
    with pytest.raises(Refused, match="you've used your 1 AI calls today"):
        ledger.call(_llm(), other, "bob", "flow", "FL1", _ask)
    ledger.call(_llm(), other, "carol", "flow", "FL1", _ask)
    ledger.call(_llm(), other, None, "summary", "", _ask)                  # the pipeline: no daily limit
    assert ledger.person_today("bob") == 1 and ledger.person_today("carol") == 1


def test_the_owner_raises_a_reviews_budget(tmp_path):
    ledger, _, rid = _ledger(tmp_path, per_review=1)
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)
    with pytest.raises(Refused):
        ledger.call(_llm(), rid, "bob", "flow", "FL2", _ask)
    ledger.raise_budget(rid, 5, "owner")
    ledger.call(_llm(), rid, "bob", "flow", "FL2", _ask)
    assert ledger.usage(rid)["budget"] == 5 and ledger.usage(rid)["used"] == 2


def test_concurrent_reservations_never_exceed_the_budget(tmp_path):
    ledger, _, rid = _ledger(tmp_path, per_review=10, per_person_daily=1000)
    ok, refused = [], []

    def worker():
        for _ in range(5):
            try:
                ok.append(ledger.reserve(rid, "bob", "flow", "x"))
            except Refused:
                refused.append(1)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ok) == 10 and len(refused) == 30


def test_usage_groups_by_person_and_purpose(tmp_path):
    ledger, _, rid = _ledger(tmp_path)
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)
    ledger.call(_llm(), rid, "bob", "mention", "7", _ask)
    ledger.call(_llm(), rid, None, "summary", "", _ask)
    u = ledger.usage(rid)
    assert u["by_person"] == {"bob": 2, "pipeline": 1} and u["by_purpose"] == {"flow": 1, "mention": 1, "summary": 1}
