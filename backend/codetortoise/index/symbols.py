"""Repo-wide tree-sitter symbol index stored in SQLite (heuristic, name-based)."""
from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from codetortoise.cparse import ParsedFile, is_source, parse_source
from codetortoise.paths import canon

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sym_meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sym_files(path TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS sym_defs(name TEXT, qualname TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS sym_calls(caller TEXT, callee TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS sym_includes(path TEXT, inc TEXT, base TEXT);
CREATE TABLE IF NOT EXISTS sym_members(name TEXT, fn TEXT, path TEXT, line INTEGER, is_write INTEGER);
CREATE INDEX IF NOT EXISTS ix_defs_name ON sym_defs(name);
CREATE INDEX IF NOT EXISTS ix_calls_callee ON sym_calls(callee);
CREATE INDEX IF NOT EXISTS ix_inc_base ON sym_includes(base);
CREATE INDEX IF NOT EXISTS ix_members_name ON sym_members(name);
"""


@dataclass(frozen=True)
class DefRow:
    qualname: str
    path: str
    line: int


@dataclass(frozen=True)
class CallRow:
    caller: str | None
    path: str
    line: int


@dataclass(frozen=True)
class MemberRow:
    fn: str | None
    path: str
    line: int
    is_write: bool


def _parse_file(path: str) -> tuple[str, ParsedFile | None]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return path, parse_source(path, fh.read())
    except OSError:
        return path, None


def iter_source_files(root: Path) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            p = os.path.join(dirpath, f)
            if is_source(p):
                out.append(canon(p))
    return sorted(out)


class SymbolIndex:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._db.executescript(_SCHEMA)

    def generation(self) -> int:
        row = self._db.execute("SELECT value FROM sym_meta WHERE key='generation'").fetchone()
        return int(row[0]) if row else 0

    def build(self, root: Path, workers: int = 0) -> int:
        """Full rebuild over every C/C++ source under root. Returns number of files indexed."""
        files = iter_source_files(Path(root))
        if workers and workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(_parse_file, files, chunksize=64))
        else:
            results = [_parse_file(f) for f in files]
        db = self._db
        with db:
            for t in ("sym_files", "sym_defs", "sym_calls", "sym_includes", "sym_members"):
                db.execute(f"DELETE FROM {t}")
            for path, pf in results:
                if pf is None:
                    continue
                db.execute("INSERT INTO sym_files VALUES(?)", (path,))
                db.executemany("INSERT INTO sym_defs VALUES(?,?,?,?)",
                               [(f.name, f.qualname, path, f.start_line) for f in pf.functions])
                db.executemany("INSERT INTO sym_calls VALUES(?,?,?,?)",
                               [(c.caller, c.callee, path, c.line) for c in pf.calls])
                db.executemany("INSERT INTO sym_includes VALUES(?,?,?)",
                               [(path, inc, os.path.basename(inc)) for inc in pf.includes])
                db.executemany("INSERT INTO sym_members VALUES(?,?,?,?,?)",
                               [(m.field, m.fn, path, m.line, int(m.is_write)) for m in pf.members])
            db.execute("INSERT OR REPLACE INTO sym_meta VALUES('generation', ?)", (str(self.generation() + 1),))
            db.execute("INSERT OR REPLACE INTO sym_meta VALUES('root', ?)", (str(root),))
        return sum(1 for _, pf in results if pf is not None)

    def files(self) -> list[str]:
        return [r[0] for r in self._db.execute("SELECT path FROM sym_files ORDER BY path")]

    def defs(self, name: str) -> list[DefRow]:
        return [DefRow(*r) for r in self._db.execute(
            "SELECT qualname, path, line FROM sym_defs WHERE name=?", (name,))]

    def callers_of(self, name: str) -> list[CallRow]:
        return [CallRow(*r) for r in self._db.execute(
            "SELECT caller, path, line FROM sym_calls WHERE callee=?", (name,))]

    def member_refs(self, field_name: str) -> list[MemberRow]:
        return [MemberRow(r[0], r[1], r[2], bool(r[3])) for r in self._db.execute(
            "SELECT fn, path, line, is_write FROM sym_members WHERE name=?", (field_name,))]

    def includers_of(self, header: str) -> list[str]:
        header = canon(header)
        out = []
        for path, inc in self._db.execute(
                "SELECT path, inc FROM sym_includes WHERE base=?", (os.path.basename(header),)):
            inc_n = os.path.normpath(inc)
            if header == inc_n or header.endswith(os.sep + inc_n):
                out.append(path)
        return sorted(set(out))

    def transitive_includers(self, header: str, limit: int = 1_000_000) -> set[str]:
        seen: set[str] = set()
        frontier = [header]
        while frontier and len(seen) < limit:
            h = frontier.pop()
            for p in self.includers_of(h):
                if p not in seen:
                    seen.add(p)
                    frontier.append(p)
        return seen

    def include_edges(self) -> list[tuple[str, str]]:
        """Resolved (includer, included_file) pairs for files present in the index."""
        by_base: dict[str, list[str]] = {}
        for f in self.files():
            by_base.setdefault(os.path.basename(f), []).append(f)
        out = []
        for path, inc, base in self._db.execute("SELECT path, inc, base FROM sym_includes"):
            inc_n = os.path.normpath(inc)
            for cand in by_base.get(base, []):
                if cand == inc_n or cand.endswith(os.sep + inc_n):
                    out.append((path, cand))
        return out

    def call_edges_by_path(self) -> list[tuple[str, str]]:
        """(caller_path, callee_def_path) for callees with a unique definition."""
        rows = self._db.execute(
            "SELECT c.path, d.path FROM sym_calls c JOIN "
            "(SELECT name, MIN(path) AS path FROM sym_defs GROUP BY name HAVING COUNT(*) = 1) d "
            "ON d.name = c.callee")
        out = [(a, b) for a, b in rows]
        return out
