"""Repo-wide tree-sitter symbol index stored in SQLite (heuristic, name-based)."""
from __future__ import annotations

import multiprocessing as mp
import os
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path

from codetortoise.cparse import ParsedFile, is_header, is_source, parse_source
from codetortoise.paths import canon

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sym_meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sym_files(path TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS sym_defs(name TEXT, qualname TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS sym_calls(caller TEXT, callee TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS sym_includes(path TEXT, inc TEXT, base TEXT);
CREATE TABLE IF NOT EXISTS sym_members(name TEXT, fn TEXT, path TEXT, line INTEGER, is_write INTEGER);
CREATE TABLE IF NOT EXISTS sym_inc_resolved(path TEXT, target TEXT);
CREATE INDEX IF NOT EXISTS ix_inc_target ON sym_inc_resolved(target);
CREATE INDEX IF NOT EXISTS ix_defs_name ON sym_defs(name);
CREATE INDEX IF NOT EXISTS ix_calls_callee ON sym_calls(callee);
CREATE INDEX IF NOT EXISTS ix_inc_base ON sym_includes(base);
CREATE INDEX IF NOT EXISTS ix_members_name ON sym_members(name);
CREATE TABLE IF NOT EXISTS sym_stat(path TEXT PRIMARY KEY, mtime_ns INTEGER, size INTEGER);
CREATE INDEX IF NOT EXISTS ix_defs_path ON sym_defs(path);
CREATE INDEX IF NOT EXISTS ix_calls_path ON sym_calls(path);
CREATE INDEX IF NOT EXISTS ix_includes_path ON sym_includes(path);
CREATE INDEX IF NOT EXISTS ix_members_path ON sym_members(path);
"""
_PER_FILE = ("sym_files", "sym_defs", "sym_calls", "sym_includes", "sym_members", "sym_stat")


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


def _stat(path: str) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def _resolve(path: str, inc: str, files: set[str], by_base: dict[str, list[str]],
             include_dirs: list[str] | None) -> list[str]:
    """Files an `#include` of `path` may name. Order: relative to the includer, then include dirs, then path-suffix
    match (a unique match when include dirs are known; every candidate when they are not)."""
    local = canon(os.path.join(os.path.dirname(path), inc))
    if local in files:
        return [local]
    hit = next((c for d in include_dirs or [] if (c := canon(os.path.join(d, inc))) in files), None)
    if hit:
        return [hit]
    inc_n = os.path.normpath(inc)
    cands = [c for c in by_base.get(os.path.basename(inc), []) if c.endswith(os.sep + inc_n)]
    return cands if include_dirs is None or len(cands) == 1 else []


class SymbolIndex:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self.skipped: list[str] = []  # files whose parse crashed in the last build

    def generation(self) -> int:
        row = self._db.execute("SELECT value FROM sym_meta WHERE key='generation'").fetchone()
        return int(row[0]) if row else 0

    def build(self, root: Path, workers: int = 0, include_dirs: list[str] | None = None,
              parser: Callable[[str], tuple[str, ParsedFile | None]] = _parse_file, *,
              seeds: list[str] | None = None, full: bool = False, batch: int = 256) -> int:
        """Bring the index up to date. Returns the number of files in it.

        Scope: every C/C++ file under `root`, or with `seeds` (the compile database's files) those files plus the
        workspace headers they include, transitively. Incremental: only files whose size or modification time changed
        are parsed again (`full` re-parses everything); files that left the scope are dropped. Results are written in
        batches of `batch` files as they are parsed, so memory stays flat at any workspace size. `include_dirs`
        (canonical, from the compile DB) resolve `#include` targets.
        """
        root = Path(root)
        db = self._db
        if full:
            with db:
                for t in _PER_FILE:
                    db.execute(f"DELETE FROM {t}")
        stored = {p: (m, z) for p, m, z in db.execute("SELECT path, mtime_ns, size FROM sym_stat")}
        everything = iter_source_files(root)
        if seeds is None:
            queue, headers = everything, None
        else:
            prefix = canon(str(root)).rstrip("/") + "/"
            queue = sorted({c for f in seeds if (c := canon(f)).startswith(prefix) and os.path.isfile(c)})
            headers = {f for f in everything if is_header(f)}
            by_base: dict[str, list[str]] = {}
            for h in headers:
                by_base.setdefault(os.path.basename(h), []).append(h)
        self.skipped = []
        scope: set[str] = set()
        while queue:
            scope.update(queue)
            includes: dict[str, list[str]] = {}
            stale = []
            for f in queue:
                st = _stat(f)
                if st is not None and stored.get(f) == st:
                    includes[f] = [r[0] for r in db.execute("SELECT inc FROM sym_includes WHERE path=?", (f,))]
                else:
                    stale.append(f)
            pending: list[tuple[str, ParsedFile | None]] = []
            for path, pf in self._parse_stream(stale, workers, parser):
                includes[path] = pf.includes if pf is not None else []
                pending.append((path, pf))
                if len(pending) >= batch:
                    self._write(pending)
                    pending = []
            self._write(pending)
            if headers is None:
                break
            found = {t for f, incs in includes.items() for inc in incs
                     for t in _resolve(f, inc, headers, by_base, include_dirs)}
            queue = sorted(found - scope)
        with db:
            gone = [p for (p,) in db.execute("SELECT path FROM sym_files UNION SELECT path FROM sym_stat")
                    if p not in scope]
            for p in gone:
                for t in _PER_FILE:
                    db.execute(f"DELETE FROM {t} WHERE path=?", (p,))
            db.execute("DELETE FROM sym_inc_resolved")
            db.executemany("INSERT INTO sym_inc_resolved VALUES(?,?)", self._resolve_includes(include_dirs))
            db.execute("INSERT OR REPLACE INTO sym_meta VALUES('generation', ?)", (str(self.generation() + 1),))
            db.execute("INSERT OR REPLACE INTO sym_meta VALUES('root', ?)", (str(root),))
        return db.execute("SELECT COUNT(*) FROM sym_files").fetchone()[0]

    def _write(self, results: list[tuple[str, ParsedFile | None]]) -> None:
        """Replace the rows of each parsed file in one transaction; a file that could not be parsed is removed."""
        db = self._db
        with db:
            for path, pf in results:
                for t in _PER_FILE:
                    db.execute(f"DELETE FROM {t} WHERE path=?", (path,))
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
                st = _stat(path)
                if st is not None:
                    db.execute("INSERT INTO sym_stat VALUES(?,?,?)", (path, *st))

    def _parse_stream(self, files: list[str], workers: int, parser) -> Iterator[tuple[str, ParsedFile | None]]:
        """Parse results one by one, a window at a time. With workers, parsing runs in a process pool and a native
        crash on one file skips only that file (recorded in `skipped`)."""
        if not workers or workers <= 1:
            for f in files:
                yield parser(f)
            return
        ctx = mp.get_context("forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn")
        window = max(1, workers) * 256
        for i in range(0, len(files), window):
            part = files[i:i + window]
            done: set[str] = set()
            try:
                with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
                    for path, pf in pool.map(parser, part, chunksize=32):
                        done.add(path)
                        yield path, pf
            except BrokenProcessPool:
                pass
            for f in part:
                if f in done:
                    continue
                try:
                    with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as pool:
                        yield f, pool.submit(parser, f).result()[1]
                except BrokenProcessPool:
                    self.skipped.append(f)
                    yield f, None

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

    def _resolve_includes(self, include_dirs: list[str] | None) -> list[tuple[str, str]]:
        """(includer, target) pairs for every include of every indexed file (see `_resolve`)."""
        files = set(self.files())
        by_base: dict[str, list[str]] = {}
        for f in files:
            by_base.setdefault(os.path.basename(f), []).append(f)
        return [(path, t) for path, inc in self._db.execute("SELECT path, inc FROM sym_includes").fetchall()
                for t in _resolve(path, inc, files, by_base, include_dirs)]

    def includers_of(self, header: str) -> list[str]:
        rows = self._db.execute("SELECT path FROM sym_inc_resolved WHERE target=?", (canon(header),))
        return sorted({r[0] for r in rows})

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
        return [(a, b) for a, b in self._db.execute("SELECT path, target FROM sym_inc_resolved")]

    def call_edges_by_path(self) -> list[tuple[str, str]]:
        """(caller_path, callee_def_path) for callees with a unique definition."""
        rows = self._db.execute(
            "SELECT c.path, d.path FROM sym_calls c JOIN "
            "(SELECT name, MIN(path) AS path FROM sym_defs GROUP BY name HAVING COUNT(*) = 1) d "
            "ON d.name = c.callee")
        out = [(a, b) for a, b in rows]
        return out
