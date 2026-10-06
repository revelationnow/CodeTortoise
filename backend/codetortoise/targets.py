"""The build targets of changed files (spec 2026-10-05-two-tier-stories §3.1).

A file's targets, first that applies: a configured name (`targets:` globs on the workspace-relative path); the compile
databases holding its commands, named by their directory under the build root, when the workspace has several; the
toolchain group's triple; the one database's name. A file with no command (a header) takes the targets of the files
including it; with none, `unknown`. A file with more than one target is shared.
"""
from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Callable

from codetortoise.config import TargetRule
from codetortoise.toolchain.compile_db import CompileDb

UNKNOWN = "unknown"


def db_name(db: str, base: str) -> str:
    """`<build_root>/build-modem/compile_commands.json` -> `build-modem`; a database at the base is named by its file."""
    d = posixpath.dirname(db)
    b = base.rstrip("/")
    rel = d[len(b) + 1:] if d.startswith(b + "/") else ("" if d == b else posixpath.basename(d))
    return rel or posixpath.splitext(posixpath.basename(db))[0]


def resolve_targets(files: list[str], rules: list[TargetRule], root: str, cdb: CompileDb, build_root: str | None,
                    triple_of: Callable[[str], str | None], includers: Callable[[str], set[str]]) -> dict[str, list[str]]:
    """Canonical local path -> its sorted target names."""
    base = (build_root or root).rstrip("/")
    several = len(cdb.databases) > 1

    def own(f: str) -> list[str]:
        rel = f[len(root.rstrip("/")) + 1:] if f.startswith(root.rstrip("/") + "/") else f
        rule = next((r for r in rules if fnmatch.fnmatch(rel, r.match)), None)
        if rule is not None:
            return [rule.name]
        dbs = cdb.databases_of(f)
        if not dbs:
            return []
        if several:
            return sorted({db_name(d, base) for d in dbs})
        try:
            t = triple_of(f)
        except Exception:  # no toolchain answer (libclang missing): the database still names it
            t = None
        return [t] if t else [db_name(dbs[0], base)]

    out = {}
    for f in files:
        names = own(f)
        if not names:
            names = sorted({t for inc in includers(f) for t in own(inc)}) or [UNKNOWN]
        out[f] = names
    return out
