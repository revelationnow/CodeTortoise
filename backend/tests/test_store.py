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


def test_check_marks_are_per_review_shared_and_pruned_to_the_keys_found_again(store):
    rid = store.create_review("t", "a", [1])
    m = store.set_mark(rid, "caller|a.c|f|g", "bob", "g(1);")
    assert (m["key"], m["user"], m["source_line"]) == ("caller|a.c|f|g", "bob", "g(1);") and m["at"]
    store.set_mark(rid, "reader|b.c|r|w", "ana", "x = u->n;")
    store.set_mark(rid, "caller|a.c|f|g", "ana", "g(2);")                      # marking again replaces the mark
    assert {k: (v["user"], v["source_line"]) for k, v in store.list_marks(rid).items()} == {
        "caller|a.c|f|g": ("ana", "g(2);"), "reader|b.c|r|w": ("ana", "x = u->n;")}
    store.prune_marks(rid, {"reader|b.c|r|w", "new|c.c|h|h"})
    assert list(store.list_marks(rid)) == ["reader|b.c|r|w"]
    store.clear_mark(rid, "reader|b.c|r|w")
    assert store.list_marks(rid) == {} and store.list_marks(rid + 1) == {}



def test_read_ticks_belong_to_one_reader_and_a_run_clears_them_all(store):
    rid = store.create_review("t", "a", [1])
    store.set_tick(rid, "ana", "story", "S1")
    store.set_tick(rid, "ana", "check", "caller|a.c|f|g")
    store.set_tick(rid, "ana", "story", "S1")                                  # ticking again changes nothing
    store.set_tick(rid, "bob", "story", "S2")
    assert store.list_ticks(rid, "ana") == {"stories": ["S1"], "checks": ["caller|a.c|f|g"]}
    assert store.list_ticks(rid, "bob") == {"stories": ["S2"], "checks": []}
    store.clear_tick(rid, "ana", "story", "S1")
    assert store.list_ticks(rid, "ana") == {"stories": [], "checks": ["caller|a.c|f|g"]}
    store.clear_ticks(rid)
    assert store.list_ticks(rid, "ana") == store.list_ticks(rid, "bob") == {"stories": [], "checks": []}

def test_comments_can_be_anchored_to_a_check(store):
    rid = store.create_review("t", "a", [1])
    c = store.add_comment(rid, "bob", "is this fine?", "check", {"key": "caller|a.c|f|g"})
    assert c["anchor_kind"] == "check" and c["anchor"] == {"key": "caller|a.c|f|g"}
