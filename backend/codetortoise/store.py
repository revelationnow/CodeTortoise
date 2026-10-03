"""SQLite persistence for reviews, stage outputs, findings, comments, sessions."""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from codetortoise.detectors.base import Finding
from codetortoise.vcs.model import ClMeta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_by TEXT,
  created_at TEXT, status TEXT, risk TEXT);
CREATE TABLE IF NOT EXISTS review_cls(review_id INTEGER, cl INTEGER, status TEXT, user TEXT,
  description TEXT, swarm_json TEXT, PRIMARY KEY(review_id, cl));
CREATE TABLE IF NOT EXISTS stages(review_id INTEGER, name TEXT, status TEXT, message TEXT,
  started_at TEXT, finished_at TEXT, PRIMARY KEY(review_id, name));
CREATE TABLE IF NOT EXISTS blobs(review_id INTEGER, key TEXT, json TEXT, PRIMARY KEY(review_id, key));
CREATE TABLE IF NOT EXISTS findings(review_id INTEGER, id TEXT, severity TEXT, kind TEXT, title TEXT,
  json TEXT, state TEXT, PRIMARY KEY(review_id, id));
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER, parent_id INTEGER,
  author TEXT, body TEXT, anchor_kind TEXT, anchor_json TEXT, resolved INTEGER DEFAULT 0,
  created_at TEXT, edited_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user TEXT, created_at TEXT, expires_at TEXT);
CREATE TABLE IF NOT EXISTS swarm_posts(review_id INTEGER, cl INTEGER, kind TEXT, swarm_id TEXT, posted_at TEXT);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, json TEXT);
CREATE TABLE IF NOT EXISTS llm_calls(id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER, user TEXT, purpose TEXT,
  target TEXT, started_at TEXT, finished_at TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, outcome TEXT,
  error TEXT);
CREATE INDEX IF NOT EXISTS ix_llm_calls_review ON llm_calls(review_id);
CREATE INDEX IF NOT EXISTS ix_llm_calls_user ON llm_calls(user, started_at);
CREATE TABLE IF NOT EXISTS llm_budget(review_id INTEGER, budget INTEGER, set_by TEXT, set_at TEXT);
"""

ANCHOR_KINDS = {"line", "function", "finding", "chapter", "review"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _dump(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        return obj.model_dump_json()
    if isinstance(obj, list) and obj and isinstance(obj[0], BaseModel):
        return "[" + ",".join(o.model_dump_json() for o in obj) + "]"
    return json.dumps(obj)


class Store:
    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._db:
            return self._db.execute(sql, params)

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    # ---- reviews ---------------------------------------------------------
    def create_review(self, title: str, created_by: str, cls: list[int]) -> int:
        cur = self._exec("INSERT INTO reviews(title, created_by, created_at, status, risk) VALUES(?,?,?,?,?)",
                         (title, created_by, _now(), "queued", None))
        rid = int(cur.lastrowid)
        for cl in sorted(set(cls)):
            self._exec("INSERT INTO review_cls(review_id, cl, status) VALUES(?,?,?)", (rid, cl, "unknown"))
        return rid

    def _with_cls(self, r: dict) -> dict:
        r["cls"] = [row["cl"] for row in self._all("SELECT cl FROM review_cls WHERE review_id=? ORDER BY cl",
                                                    (r["id"],))]
        return r

    def list_reviews(self) -> list[dict]:
        return [self._with_cls(r) for r in self._all("SELECT * FROM reviews ORDER BY id DESC")]

    def get_review(self, rid: int) -> dict | None:
        rows = self._all("SELECT * FROM reviews WHERE id=?", (rid,))
        return self._with_cls(rows[0]) if rows else None

    def set_review_status(self, rid: int, status: str, risk: str | None = None) -> None:
        if risk is None:
            self._exec("UPDATE reviews SET status=? WHERE id=?", (status, rid))
        else:
            self._exec("UPDATE reviews SET status=?, risk=? WHERE id=?", (status, risk, rid))

    def upsert_cl(self, rid: int, meta: ClMeta) -> None:
        self._exec("INSERT INTO review_cls(review_id, cl, status, user, description) VALUES(?,?,?,?,?) "
                   "ON CONFLICT(review_id, cl) DO UPDATE SET status=excluded.status, user=excluded.user, "
                   "description=excluded.description", (rid, meta.cl, meta.status, meta.user, meta.description))

    def set_cl_swarm(self, rid: int, cl: int, swarm: dict | None) -> None:
        self._exec("UPDATE review_cls SET swarm_json=? WHERE review_id=? AND cl=?",
                   (json.dumps(swarm) if swarm is not None else None, rid, cl))

    def list_cls(self, rid: int) -> list[dict]:
        out = []
        for r in self._all("SELECT * FROM review_cls WHERE review_id=? ORDER BY cl", (rid,)):
            r["swarm"] = json.loads(r.pop("swarm_json")) if r.get("swarm_json") else None
            out.append(r)
        return out

    # ---- stages & blobs --------------------------------------------------
    def reset_stages(self, rid: int, names: list[str]) -> None:
        self._exec("DELETE FROM stages WHERE review_id=?", (rid,))
        for n in names:
            self._exec("INSERT INTO stages(review_id, name, status, message) VALUES(?,?,?,?)", (rid, n, "pending", ""))

    def set_stage(self, rid: int, name: str, status: str, message: str = "") -> None:
        if status == "running":
            self._exec("UPDATE stages SET status=?, message=?, started_at=? WHERE review_id=? AND name=?",
                       (status, message, _now(), rid, name))
        else:
            self._exec("UPDATE stages SET status=?, message=?, finished_at=? WHERE review_id=? AND name=?",
                       (status, message, _now(), rid, name))

    def list_stages(self, rid: int) -> list[dict]:
        return self._all("SELECT name, status, message, started_at, finished_at FROM stages WHERE review_id=? "
                         "ORDER BY rowid", (rid,))

    def put_blob(self, rid: int, key: str, obj: Any) -> None:
        self._exec("INSERT OR REPLACE INTO blobs(review_id, key, json) VALUES(?,?,?)", (rid, key, _dump(obj)))

    def get_blob(self, rid: int, key: str) -> Any:
        rows = self._all("SELECT json FROM blobs WHERE review_id=? AND key=?", (rid, key))
        return json.loads(rows[0]["json"]) if rows else None

    # ---- findings --------------------------------------------------------
    def put_findings(self, rid: int, findings: list[Finding]) -> None:
        """Replace findings; keep ack/dismiss state for findings with the same (kind, title)."""
        old = {(r["kind"], r["title"]): r["state"] for r in
               self._all("SELECT kind, title, state FROM findings WHERE review_id=?", (rid,))}
        self._exec("DELETE FROM findings WHERE review_id=?", (rid,))
        for f in findings:
            f.state = old.get((f.kind, f.title), f.state)
            self._exec("INSERT INTO findings(review_id, id, severity, kind, title, json, state) VALUES(?,?,?,?,?,?,?)",
                       (rid, f.id, f.severity, f.kind, f.title, f.model_dump_json(), f.state))

    def list_findings(self, rid: int) -> list[Finding]:
        out = []
        for r in self._all("SELECT json, state FROM findings WHERE review_id=? ORDER BY rowid", (rid,)):
            f = Finding.model_validate_json(r["json"])
            f.state = r["state"]
            out.append(f)
        return out

    def set_finding_state(self, rid: int, fid: str, state: str) -> bool:
        cur = self._exec("UPDATE findings SET state=? WHERE review_id=? AND id=?", (state, rid, fid))
        return cur.rowcount > 0

    # ---- comments --------------------------------------------------------
    def add_comment(self, rid: int, author: str, body: str, anchor_kind: str, anchor: dict,
                    parent_id: int | None = None) -> dict:
        if anchor_kind not in ANCHOR_KINDS:
            raise ValueError(f"bad anchor kind {anchor_kind}")
        cur = self._exec("INSERT INTO comments(review_id, parent_id, author, body, anchor_kind, anchor_json, "
                         "created_at) VALUES(?,?,?,?,?,?,?)",
                         (rid, parent_id, author, body, anchor_kind, json.dumps(anchor), _now()))
        return self.get_comment(int(cur.lastrowid))

    def _comment(self, r: dict) -> dict:
        r["anchor"] = json.loads(r.pop("anchor_json"))
        r["resolved"] = bool(r["resolved"])
        return r

    def get_comment(self, cid: int) -> dict | None:
        rows = self._all("SELECT * FROM comments WHERE id=?", (cid,))
        return self._comment(rows[0]) if rows else None

    def list_comments(self, rid: int) -> list[dict]:
        return [self._comment(r) for r in self._all("SELECT * FROM comments WHERE review_id=? ORDER BY id", (rid,))]

    def update_comment(self, cid: int, body: str | None = None, resolved: bool | None = None) -> dict | None:
        if body is not None:
            self._exec("UPDATE comments SET body=?, edited_at=? WHERE id=?", (body, _now(), cid))
        if resolved is not None:
            self._exec("UPDATE comments SET resolved=? WHERE id=?", (int(resolved), cid))
        return self.get_comment(cid)

    def delete_comment(self, cid: int) -> None:
        self._exec("DELETE FROM comments WHERE id=? OR parent_id=?", (cid, cid))

    # ---- sessions --------------------------------------------------------
    def create_session(self, user: str, ttl_days: int = 7) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self._exec("INSERT INTO sessions VALUES(?,?,?,?)",
                   (_hash(token), user, now.isoformat(), (now + timedelta(days=ttl_days)).isoformat()))
        return token

    def session_user(self, token: str | None) -> str | None:
        if not token:
            return None
        rows = self._all("SELECT user, expires_at FROM sessions WHERE token_hash=?", (_hash(token),))
        if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(UTC):
            return None
        return rows[0]["user"]

    def delete_session(self, token: str) -> None:
        self._exec("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))

    # ---- swarm posts & kv ------------------------------------------------
    def record_swarm_post(self, rid: int, cl: int, kind: str, swarm_id: str) -> None:
        self._exec("INSERT INTO swarm_posts VALUES(?,?,?,?,?)", (rid, cl, kind, swarm_id, _now()))

    def swarm_posts(self, rid: int, cl: int) -> list[dict]:
        return self._all("SELECT kind, swarm_id, posted_at FROM swarm_posts WHERE review_id=? AND cl=?", (rid, cl))

    def kv_get(self, key: str) -> Any:
        rows = self._all("SELECT json FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["json"]) if rows else None

    def kv_put(self, key: str, obj: Any) -> None:
        self._exec("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, _dump(obj)))
