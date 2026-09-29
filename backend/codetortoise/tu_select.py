"""Chooses which translation units get precise (clang) analysis, within a budget."""
from __future__ import annotations

from pydantic import BaseModel, Field

from codetortoise.config import AnalysisConfig
from codetortoise.cparse import is_header
from codetortoise.diffmap import DiffMap
from codetortoise.index.symbols import SymbolIndex
from codetortoise.toolchain.compile_db import CompileDb


class TuSelection(BaseModel):
    selected: list[str] = Field(default_factory=list)
    hops: dict[str, int] = Field(default_factory=dict)
    header_fanout: dict[str, int] = Field(default_factory=dict)
    over_budget: int = 0


def select_tus(dm: DiffMap, index: SymbolIndex, cdb: CompileDb, cfg: AnalysisConfig) -> TuSelection:
    tus = set(cdb.files())
    hop: dict[str, int] = {}
    refs: dict[str, int] = {}

    def add(path: str, h: int) -> None:
        if path not in tus:
            return
        hop[path] = min(hop.get(path, h), h)
        refs[path] = refs.get(path, 0) + 1

    sel = TuSelection()
    for f in dm.changed_files:
        if f in tus:
            add(f, 0)
        elif is_header(f):
            includers = index.transitive_includers(f)
            sel.header_fanout[f] = sum(1 for p in includers if p in tus)
            names = {c.name for c in dm.functions if c.file == f}
            names |= {t.name.split("::")[-1] for t in dm.types if t.file == f}
            users = {r.path for n in names for r in index.callers_of(n)}
            ranked = sorted((p for p in includers if p in tus), key=lambda p: (p not in users, p))
            for p in ranked[: cfg.header_sample_tus]:
                add(p, 0)

    frontier = {c.name for c in dm.functions}
    for h in range(1, cfg.caller_hops + 1):
        nxt: set[str] = set()
        for name in sorted(frontier):
            for row in index.callers_of(name):
                add(row.path, h)
                if row.caller:
                    nxt.add(row.caller.split("::")[-1])
        frontier = nxt - {c.name for c in dm.functions}
    for member in sorted({m for c in dm.functions for m in c.written_members}):
        for row in index.member_refs(member):
            add(row.path, 1)

    ranked = sorted(hop, key=lambda p: (hop[p], -refs[p], p))
    sel.selected = ranked[: cfg.tu_budget]
    sel.hops = {p: hop[p] for p in sel.selected}
    sel.over_budget = max(0, len(ranked) - cfg.tu_budget)
    return sel
