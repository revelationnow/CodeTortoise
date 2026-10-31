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
  created_at TEXT, status TEXT, risk TEXT, workspace_id INTEGER);
CREATE TABLE IF NOT EXISTS workspaces(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
  vcs TEXT NOT NULL, p4port TEXT, client TEXT, p4user TEXT NOT NULL, root TEXT NOT NULL UNIQUE,
  compile_commands TEXT NOT NULL, build_root TEXT, swarm_url TEXT, settings TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL, created_by TEXT, created_at TEXT, updated_at TEXT);
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
CREATE TABLE IF NOT EXISTS session_logins(token_hash TEXT, server TEXT, user TEXT, signed_in_at TEXT,
  PRIMARY KEY(token_hash, server));
CREATE TABLE IF NOT EXISTS swarm_posts(review_id INTEGER, cl INTEGER, kind TEXT, swarm_id TEXT, posted_at TEXT);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, json TEXT);
CREATE TABLE IF NOT EXISTS llm_calls(id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER, user TEXT, purpose TEXT,
  target TEXT, started_at TEXT, finished_at TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, outcome TEXT,
  error TEXT);
CREATE INDEX IF NOT EXISTS ix_llm_calls_review ON llm_calls(review_id);
CREATE INDEX IF NOT EXISTS ix_llm_calls_user ON llm_calls(user, started_at);
CREATE TABLE IF NOT EXISTS llm_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, call_id INTEGER NOT NULL,
  review_id INTEGER, seq INTEGER NOT NULL, sent_at TEXT NOT NULL, elapsed_ms INTEGER, url TEXT, model TEXT,
  status INTEGER, error TEXT, stop_reason TEXT, truncated INTEGER NOT NULL, repair INTEGER NOT NULL,
  max_output_tokens INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER, request BLOB, response BLOB);
CREATE INDEX IF NOT EXISTS ix_llm_requests_call ON llm_requests(call_id);
CREATE INDEX IF NOT EXISTS ix_llm_requests_review ON llm_requests(review_id, sent_at);
CREATE TABLE IF NOT EXISTS llm_budget(review_id INTEGER, budget INTEGER, set_by TEXT, set_at TEXT);
CREATE TABLE IF NOT EXISTS llm_rounds(review_id INTEGER, rounds INTEGER, set_by TEXT, set_at TEXT);
CREATE TABLE IF NOT EXISTS briefs(review_id INTEGER PRIMARY KEY, cache_key TEXT, json TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_briefs_key ON briefs(cache_key);
CREATE TABLE IF NOT EXISTS check_marks(review_id INTEGER, key TEXT, user TEXT, at TEXT, source_line TEXT,
    PRIMARY KEY(review_id, key));
CREATE TABLE IF NOT EXISTS read_ticks(review_id INTEGER, user TEXT, kind TEXT, key TEXT, at TEXT,
    PRIMARY KEY(review_id, user, kind, key));
"""

ANCHOR_KINDS = {"line", "function", "finding", "chapter", "review", "story", "flow", "file", "check"}
# a workspace's own columns (spec 2026-10-31 §5): compile_commands is JSON ("auto", a path or a list), settings YAML
WORKSPACE_FIELDS = ("name", "vcs", "p4port", "client", "p4user", "root", "compile_commands", "build_root", "swarm_url",
                    "settings")


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
            had_logins = self._db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_logins'").fetchone() is not None
            self._db.executescript(_SCHEMA)
            cols = {r[1] for r in self._db.execute("PRAGMA table_info(comments)")}
            if "ai_meta" not in cols:                # databases made before @tortoise
                self._db.execute("ALTER TABLE comments ADD COLUMN ai_meta TEXT")
            calls = {r[1] for r in self._db.execute("PRAGMA table_info(llm_calls)")}
            if "model" not in calls:                 # databases made before the request log
                self._db.execute("ALTER TABLE llm_calls ADD COLUMN model TEXT")
            reviews = {r[1] for r in self._db.execute("PRAGMA table_info(reviews)")}
            if "workspace_id" not in reviews:        # databases made before workspaces (spec 2026-10-31 §12)
                self._db.execute("ALTER TABLE reviews ADD COLUMN workspace_id INTEGER")
            if not had_logins:                       # sign-ins from before per-server sign-in end (spec 2026-10-31 §12)
                with self._db:
                    self._db.execute("DELETE FROM sessions")

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._db:
            return self._db.execute(sql, params)

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    # ---- reviews ---------------------------------------------------------
    def create_review(self, title: str, created_by: str, cls: list[int], workspace_id: int | None = None) -> int:
        cur = self._exec("INSERT INTO reviews(title, created_by, created_at, status, risk, workspace_id) "
                         "VALUES(?,?,?,?,?,?)", (title, created_by, _now(), "queued", None, workspace_id))
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

    def adopt_reviews(self, wid: int) -> int:
        """Reviews made before workspaces belong to the seed (spec 2026-10-31 §12); how many there were."""
        return self._exec("UPDATE reviews SET workspace_id=? WHERE workspace_id IS NULL", (wid,)).rowcount

    def review_count(self, wid: int) -> int:
        return self._all("SELECT COUNT(*) AS n FROM reviews WHERE workspace_id=?", (wid,))[0]["n"]

    # ---- workspaces (spec 2026-10-31 §5) -----------------------------------------
    def add_workspace(self, fields: dict, source: str, created_by: str) -> int:
        """A new workspace (`source` "config" for the seed, "ui" for one added on the Workspaces page); a name or root
        another has raises sqlite3.IntegrityError."""
        now = _now()
        cols = WORKSPACE_FIELDS + ("source", "created_by", "created_at", "updated_at")
        cur = self._exec(f"INSERT INTO workspaces({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
                         tuple(fields.get(k) for k in WORKSPACE_FIELDS) + (source, created_by, now, now))
        return int(cur.lastrowid)

    def update_workspace(self, wid: int, fields: dict) -> None:
        sets = ", ".join(f"{k}=?" for k in WORKSPACE_FIELDS)
        self._exec(f"UPDATE workspaces SET {sets}, updated_at=? WHERE id=?",
                   tuple(fields.get(k) for k in WORKSPACE_FIELDS) + (_now(), wid))

    def delete_workspace(self, wid: int) -> None:
        self._exec("DELETE FROM workspaces WHERE id=?", (wid,))

    def get_workspace(self, wid: int) -> dict | None:
        rows = self._all("SELECT * FROM workspaces WHERE id=?", (wid,))
        return rows[0] if rows else None

    def list_workspaces(self) -> list[dict]:
        return self._all("SELECT * FROM workspaces ORDER BY name")

    def seed_workspace(self) -> dict | None:
        """The workspace registered from tortoise.yaml."""
        rows = self._all("SELECT * FROM workspaces WHERE source='config' ORDER BY id")
        return rows[0] if rows else None

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

    def replace_blobs(self, rid: int, keys: list[str], prefixes: list[str], puts: dict[str, Any]) -> None:
        """In one transaction: remove the review's blobs named in `keys` or starting with one of `prefixes`, then store
        `puts`. Every value is serialised first, so a value that can't be stored changes nothing."""
        rows = [(rid, k, _dump(v)) for k, v in puts.items()]
        with self._lock, self._db:
            for k in keys:
                self._db.execute("DELETE FROM blobs WHERE review_id=? AND key=?", (rid, k))
            for p in prefixes:
                self._db.execute("DELETE FROM blobs WHERE review_id=? AND substr(key, 1, ?)=?", (rid, len(p), p))
            self._db.executemany("INSERT OR REPLACE INTO blobs(review_id, key, json) VALUES(?,?,?)", rows)

    def blob_keys(self, rid: int, prefix: str) -> list[str]:
        return [r["key"] for r in self._all("SELECT key FROM blobs WHERE review_id=? AND substr(key, 1, ?)=? ORDER BY key",
                                            (rid, len(prefix), prefix))]

    def get_blob(self, rid: int, key: str) -> Any:
        rows = self._all("SELECT json FROM blobs WHERE review_id=? AND key=?", (rid, key))
        return json.loads(rows[0]["json"]) if rows else None

    def has_blob(self, rid: int, key: str) -> bool:
        """Whether the review has the blob, without reading it."""
        return bool(self._all("SELECT 1 FROM blobs WHERE review_id=? AND key=?", (rid, key)))

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
        r["ai_meta"] = json.loads(r["ai_meta"]) if r.get("ai_meta") else None
        return r

    def end_pending_ai_replies(self, body: str) -> int:
        """At startup: @tortoise replies left pending by a stopped server get `body` and stop being pending."""
        n = 0
        for r in self._all("SELECT id, ai_meta FROM comments WHERE ai_meta IS NOT NULL"):
            meta = json.loads(r["ai_meta"])
            if meta.get("pending"):
                meta.update(pending=False, error="interrupted")
                self.set_ai_reply(r["id"], body, meta)
                n += 1
        return n

    def set_ai_reply(self, cid: int, body: str, meta: dict) -> dict | None:
        """An @tortoise reply's text and its state (pending, round, read, files, calls, error)."""
        self._exec("UPDATE comments SET body=?, ai_meta=? WHERE id=?", (body, json.dumps(meta), cid))
        return self.get_comment(cid)

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

    # ---- To check marks (spec 2026-10-07-review-reading §7.4) -------------
    def set_mark(self, rid: int, key: str, user: str, source_line: str) -> dict:
        """Mark a check "looks fine" for everyone viewing the review; `source_line` is the line it was marked at."""
        at = _now()
        self._exec("INSERT OR REPLACE INTO check_marks(review_id, key, user, at, source_line) VALUES(?,?,?,?,?)",
                   (rid, key, user, at, source_line))
        return {"key": key, "user": user, "at": at, "source_line": source_line}

    def set_marks(self, rid: int, user: str, checks: list[tuple[str, str]]) -> list[dict]:
        """All look fine (spec 2026-10-16 §4.3): mark each (key, source_line) and tick it read for `user`, in one
        transaction."""
        at = _now()
        with self._lock, self._db:
            self._db.executemany("INSERT OR IGNORE INTO read_ticks(review_id, user, kind, key, at) VALUES(?,?,?,?,?)",
                                 [(rid, user, "check", key, at) for key, _ in checks])
            self._db.executemany("INSERT OR REPLACE INTO check_marks(review_id, key, user, at, source_line) "
                                 "VALUES(?,?,?,?,?)", [(rid, key, user, at, line) for key, line in checks])
        return [{"key": key, "user": user, "at": at, "source_line": line} for key, line in checks]

    def clear_mark(self, rid: int, key: str) -> None:
        self._exec("DELETE FROM check_marks WHERE review_id=? AND key=?", (rid, key))

    def clear_marks(self, rid: int, keys: list[str]) -> None:
        """Reopen each of `keys` (a flow's places, together), in one transaction: all of them or none."""
        with self._lock, self._db:
            self._db.executemany("DELETE FROM check_marks WHERE review_id=? AND key=?", [(rid, key) for key in keys])

    def list_marks(self, rid: int) -> dict[str, dict]:
        return {r["key"]: r for r in self._all("SELECT key, user, at, source_line FROM check_marks WHERE review_id=? "
                                               "ORDER BY key", (rid,))}

    def prune_marks(self, rid: int, keep: set[str]) -> None:
        """A re-run drops the marks of checks it no longer finds."""
        for key in set(self.list_marks(rid)) - keep:
            self.clear_mark(rid, key)

    # ---- read ticks (spec 2026-10-07-review-reading-phase2 §6) -----------
    def set_tick(self, rid: int, user: str, kind: str, key: str) -> None:
        """`user` has read the story or check `key`; nobody else sees it."""
        self._exec("INSERT OR IGNORE INTO read_ticks(review_id, user, kind, key, at) VALUES(?,?,?,?,?)",
                   (rid, user, kind, key, _now()))

    def clear_tick(self, rid: int, user: str, kind: str, key: str) -> None:
        self._exec("DELETE FROM read_ticks WHERE review_id=? AND user=? AND kind=? AND key=?", (rid, user, kind, key))

    def list_ticks(self, rid: int, user: str) -> dict[str, list[str]]:
        rows = self._all("SELECT kind, key FROM read_ticks WHERE review_id=? AND user=? ORDER BY at, key", (rid, user))
        return {"stories": [r["key"] for r in rows if r["kind"] == "story"],
                "checks": [r["key"] for r in rows if r["kind"] == "check"]}

    def clear_ticks(self, rid: int) -> None:
        """A run starts every reader over (§6.5)."""
        self._exec("DELETE FROM read_ticks WHERE review_id=?", (rid,))

    # ---- sessions: one sign-in per Perforce server (spec 2026-10-31 §5) ---------------
    def open_session(self, ttl_days: int = 7) -> str:
        """A browser session with no sign-in yet; its token is the cookie's value."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self._exec("INSERT INTO sessions VALUES(?,?,?,?)",
                   (_hash(token), None, now.isoformat(), (now + timedelta(days=ttl_days)).isoformat()))
        return token

    def renew_session(self, token: str | None, ttl_days: int = 7) -> str:
        """A new token for the session `token` names, carrying its sign-ins, with a new expiry; the old token ends. A
        sign-in never joins a token the browser already held, so one planted there gains nothing from it."""
        carried = self.session_logins(token) or {}
        new = self.open_session(ttl_days)
        for server, user in carried.items():
            self.add_login(new, server, user)
        if token:
            self.delete_session(token)
        return new

    def add_login(self, token: str, server: str, user: str) -> None:
        """The session's sign-in on `server`; signing in there again replaces it."""
        self._exec("INSERT OR REPLACE INTO session_logins VALUES(?,?,?,?)", (_hash(token), server, user, _now()))

    def session_logins(self, token: str | None) -> dict[str, str] | None:
        """server -> user for a live session; None without one (or when it has expired)."""
        if not token:
            return None
        rows = self._all("SELECT expires_at FROM sessions WHERE token_hash=?", (_hash(token),))
        if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(UTC):
            return None
        got = self._all("SELECT server, user FROM session_logins WHERE token_hash=? ORDER BY server", (_hash(token),))
        return {r["server"]: r["user"] for r in got}

    def delete_session(self, token: str) -> None:
        self._exec("DELETE FROM session_logins WHERE token_hash=?", (_hash(token),))
        self._exec("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))

    # ---- swarm posts & kv ------------------------------------------------
    def record_swarm_post(self, rid: int, cl: int, kind: str, swarm_id: str) -> None:
        self._exec("INSERT INTO swarm_posts VALUES(?,?,?,?,?)", (rid, cl, kind, swarm_id, _now()))

    def swarm_posts(self, rid: int, cl: int) -> list[dict]:
        return self._all("SELECT kind, swarm_id, posted_at FROM swarm_posts WHERE review_id=? AND cl=?", (rid, cl))

    # ---- briefs (spec 2026-10-05-two-tier-stories §7.2) ------------------------
    def put_brief(self, rid: int, key: str, brief: BaseModel) -> None:
        self._exec("INSERT INTO briefs VALUES(?,?,?,?) ON CONFLICT(review_id) DO UPDATE SET cache_key=excluded.cache_key, "
                   "json=excluded.json, created_at=excluded.created_at", (rid, key, brief.model_dump_json(), _now()))

    def get_brief(self, rid: int) -> dict | None:
        rows = self._all("SELECT json FROM briefs WHERE review_id=?", (rid,))
        return json.loads(rows[0]["json"]) if rows else None

    def find_brief(self, key: str) -> dict | None:
        """The newest complete brief stored under a cache key, from any review."""
        for r in self._all("SELECT json FROM briefs WHERE cache_key=? ORDER BY created_at DESC", (key,)):
            got = json.loads(r["json"])
            if got.get("complete"):
                return got
        return None

    def kv_get(self, key: str) -> Any:
        rows = self._all("SELECT json FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["json"]) if rows else None

    def kv_put(self, key: str, obj: Any) -> None:
        self._exec("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, _dump(obj)))

    def kv_delete_scope(self, scope: str) -> None:
        """Every entry kept for one workspace: its keys hold `:<scope>` as a whole segment (spec 2026-10-31 §5)."""
        self._exec("DELETE FROM kv WHERE key LIKE ? OR key LIKE ?", (f"%:{scope}", f"%:{scope}:%"))
