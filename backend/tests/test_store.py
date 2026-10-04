from datetime import UTC, datetime, timedelta

import pytest

from codetortoise.detectors.base import Finding
from codetortoise.store import Store
from codetortoise.vcs.model import ClMeta


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


def test_reviews_and_cls(store):
    rid = store.create_review("t", "anoop", [5, 3, 5])
    assert store.get_review(rid)["cls"] == [3, 5]
    store.upsert_cl(rid, ClMeta(cl=3, status="pending", user="bob", description="d"))
    store.set_cl_swarm(rid, 3, {"id": 42})
    rows = store.list_cls(rid)
    assert rows[0]["status"] == "pending" and rows[0]["swarm"] == {"id": 42} and rows[1]["swarm"] is None
    store.set_review_status(rid, "done", "high")
    assert store.list_reviews()[0]["risk"] == "high"
    assert store.get_review(999) is None


def test_stages_and_blobs(store):
    rid = store.create_review("t", "a", [1])
    store.reset_stages(rid, ["ingest", "facts"])
    store.set_stage(rid, "ingest", "running")
    store.set_stage(rid, "ingest", "ok", "4 files")
    st = store.list_stages(rid)
    assert [(s["name"], s["status"]) for s in st] == [("ingest", "ok"), ("facts", "pending")]
    assert st[0]["started_at"] and st[0]["finished_at"]
    store.put_blob(rid, "k", {"a": [1, 2]})
    store.put_blob(rid, "m", [Finding(kind="x", severity="low", title="t", summary="s")])
    assert store.get_blob(rid, "k") == {"a": [1, 2]}
    assert store.get_blob(rid, "m")[0]["title"] == "t"
    assert store.get_blob(rid, "missing") is None


def test_finding_state_survives_rerun(store):
    rid = store.create_review("t", "a", [1])
    store.put_findings(rid, [Finding(id="F1", kind="contract", severity="high", title="a", summary="s")])
    assert store.set_finding_state(rid, "F1", "dismissed")
    store.put_findings(rid, [Finding(id="F1", kind="contract", severity="high", title="a", summary="s"),
                             Finding(id="F2", kind="contract", severity="low", title="b", summary="s")])
    assert [(f.id, f.state) for f in store.list_findings(rid)] == [("F1", "dismissed"), ("F2", "open")]
    assert not store.set_finding_state(rid, "F9", "ack")


def test_comments(store):
    rid = store.create_review("t", "a", [1])
    c = store.add_comment(rid, "bob", "hi", "line", {"depot": "//d/a.c", "line": 3})
    r = store.add_comment(rid, "amy", "re", "line", {"depot": "//d/a.c", "line": 3}, parent_id=c["id"])
    assert c["anchor"] == {"depot": "//d/a.c", "line": 3} and c["resolved"] is False
    assert store.update_comment(c["id"], resolved=True)["resolved"] is True
    assert store.update_comment(c["id"], body="hello")["edited_at"]
    store.delete_comment(c["id"])
    assert store.list_comments(rid) == [] and store.get_comment(r["id"]) is None
    with pytest.raises(ValueError):
        store.add_comment(rid, "bob", "x", "bogus", {})


def test_sessions(store):
    tok = store.create_session("bob")
    assert store.session_user(tok) == "bob"
    assert store.session_user("nope") is None and store.session_user(None) is None
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    store._exec("UPDATE sessions SET expires_at=?", (past,))
    assert store.session_user(tok) is None
    tok2 = store.create_session("amy")
    store.delete_session(tok2)
    assert store.session_user(tok2) is None


def test_swarm_posts_and_kv(store):
    store.record_swarm_post(1, 7, "summary", "99")
    assert [p["swarm_id"] for p in store.swarm_posts(1, 7)] == ["99"]
    store.kv_put("x", {"a": 1})
    assert store.kv_get("x") == {"a": 1} and store.kv_get("y") is None


def test_an_existing_database_gains_ai_meta(tmp_path):
    import sqlite3

    from codetortoise.store import Store
    db = tmp_path / "old.db"
    s = Store(db)
    rid = s.create_review("old", "owner", [101])
    s.add_comment(rid, "bob", "a comment from before @tortoise", "review", {}, None)
    s._db.close()
    with sqlite3.connect(db) as raw:                          # the table as databases made before @tortoise had it
        raw.execute("ALTER TABLE comments DROP COLUMN ai_meta")
    s = Store(db)
    [c] = s.list_comments(rid)
    assert c["body"] == "a comment from before @tortoise" and c["ai_meta"] is None
    assert s.set_ai_reply(c["id"], "x", {"pending": False})["ai_meta"] == {"pending": False}
