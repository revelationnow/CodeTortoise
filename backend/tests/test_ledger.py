"""Every AI call is counted; none is made over a limit (spec 2026-10-03 §2)."""
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from codetortoise.config import LlmBudget
from codetortoise.llm import request_log
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


def test_workspace_calls_are_recorded_without_a_review_budget(tmp_path):
    ledger, _, rid = _ledger(tmp_path, per_review=1)
    ledger.call(_llm(), None, None, "layers", "generation 3", _ask)          # layer naming: once per index
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)                     # the review's one call is still free
    assert ledger.workspace_calls() == 1 and ledger.usage(rid)["used"] == 1


def test_tier_1_calls_count_against_their_own_budget_not_the_review_s(tmp_path):
    ledger, _, rid = _ledger(tmp_path, per_review=1, tier1_per_review=2)
    for purpose in ("stories", "review"):
        ledger.call(_llm(), rid, None, purpose, "x", _ask)
    with pytest.raises(Refused, match="this review has used its 2 tier-1 AI calls"):
        ledger.call(_llm(), rid, None, "stories_merge", "x", _ask)
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)        # the tier-2 budget is untouched
    u = ledger.usage(rid)
    assert (u["used"], u["budget"], u["tier1"]) == (1, 1, {"used": 2, "budget": 2})
    assert u["by_purpose"] == {"stories": 1, "review": 1, "flow": 1}


def _logged(tmp_path, mode="all"):
    store = Store(tmp_path / "t.db")
    rid = store.create_review("t", "owner", [1])
    return Ledger(store, LlmBudget(), mode), store, rid


def _repairing():
    replies = iter(['{"nope": 1}', '{"ok": true}'])
    return LlmClient("http://llm/v1", "k", "m", sleep=lambda s: None, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})))


def test_every_request_of_a_call_is_logged_when_request_log_is_all(tmp_path):
    ledger, store, rid = _logged(tmp_path)
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)
    [call] = ledger.usage(rid)["calls"]
    assert (call["model"], call["requests"]) == ("m", 1)
    [row] = request_log.rows(store, rid)
    assert (row["call_id"], row["purpose"], row["target"], row["seq"], row["status"]) == (call["id"], "flow", "FL1", 1, 200)
    assert row["request"]["messages"][1]["content"] == "u" and json.loads(row["response"])["usage"]["prompt_tokens"] == 120
    assert row["truncated"] is False and row["repair"] is False


def test_request_log_failed_keeps_only_calls_that_failed_were_cut_off_or_repaired(tmp_path):
    ledger, store, rid = _logged(tmp_path, "failed")
    ledger.call(_llm(), rid, "bob", "flow", "ok", _ask)
    with pytest.raises(LlmError):
        ledger.call(_llm(fail=True), rid, "bob", "flow", "failed", _ask)
    ledger.call(_repairing(), rid, "bob", "flow", "repaired", _ask)
    cut = iter([httpx.Response(200, json={"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}),
                httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})])
    ledger.call(LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(lambda r: next(cut))),
                rid, "bob", "flow", "cut off", _ask)
    assert [(r["target"], r["seq"]) for r in request_log.rows(store, rid)] == [
        ("failed", 1), ("repaired", 1), ("repaired", 2), ("cut off", 1), ("cut off", 2)]


def test_request_log_off_keeps_nothing(tmp_path):
    ledger, store, rid = _logged(tmp_path, "off")
    with pytest.raises(LlmError):
        ledger.call(_llm(fail=True), rid, "bob", "flow", "failed", _ask)
    assert request_log.rows(store, rid) == [] and ledger.usage(rid)["calls"][0]["requests"] == 0


def test_a_network_failure_is_logged_with_its_error(tmp_path):
    ledger, store, rid = _logged(tmp_path)

    def down(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(LlmError):
        ledger.call(LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(down), sleep=lambda s: None),
                    rid, "bob", "flow", "x", _ask)
    rows = request_log.rows(store, rid)
    assert len(rows) == 3 and all(r["status"] is None and r["error"] == "ConnectError: refused" for r in rows)


def test_requests_older_than_the_retention_are_pruned(tmp_path):
    ledger, store, rid = _logged(tmp_path)
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)
    assert ledger.prune(now=datetime.now(UTC) + timedelta(days=1)) == 0 and len(request_log.rows(store, rid)) == 1
    assert ledger.prune(now=datetime.now(UTC) + timedelta(days=15)) == 1 and request_log.rows(store, rid) == []


def test_an_old_database_gains_the_model_column(tmp_path):
    db = sqlite3.connect(tmp_path / "t.db")
    db.execute("CREATE TABLE llm_calls(id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER, user TEXT, purpose TEXT, "
               "target TEXT, started_at TEXT, finished_at TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, "
               "outcome TEXT, error TEXT)")
    db.commit()
    db.close()
    store = Store(tmp_path / "t.db")
    assert "model" in {r["name"] for r in store._all("PRAGMA table_info(llm_calls)")}


def test_the_log_is_exported_as_one_json_file_per_request_and_one_line_each(tmp_path):
    ledger, store, rid = _logged(tmp_path)
    ledger.call(_repairing(), rid, "bob", "flow", "FL1", _ask)
    rows = request_log.rows(store, rid)
    files = request_log.files(rows)
    call = rows[0]["call_id"]
    assert sorted(files) == [f"call-{call}/1.json", f"call-{call}/2.json"]
    one = json.loads(files[f"call-{call}/2.json"])
    assert (one["purpose"], one["repair"], one["response"]["choices"][0]["message"]["content"]) == ("flow", True, '{"ok": true}')
    # the repair round doubles the limit from 8192
    assert request_log.line(rows[1]).startswith(f"call {call} flow FL1 m #2 200 - limit=16384 tokens=-+- ")
    import io
    import zipfile
    assert sorted(zipfile.ZipFile(io.BytesIO(request_log.zip_bytes(rows))).namelist()) == sorted(files)
