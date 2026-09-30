"""Chooses which translation units get precise (clang) analysis, within a budget."""
from __future__ import annotations

from pydantic import BaseModel, Field

from codetortoise.config import AnalysisConfig
from codetortoise.cparse import is_header
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import Facts
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

    def add(path: str, h: int, force: bool = False) -> None:
        if path not in tus and not force:
            return
        hop[path] = min(hop.get(path, h), h)
        refs[path] = refs.get(path, 0) + 1

    sel = TuSelection()
    for f in dm.changed_files:
        if f in tus or not is_header(f):
            # changed sources without a compile-DB entry (other variants, new files) still get parsed,
            # borrowing flags from the nearest entry (Toolchain.args_for)
            add(f, 0, force=True)
        else:
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
            for row in index.callers_of(name)[: cfg.heuristic_fanin_cap]:
                add(row.path, h)
                if row.caller:
                    nxt.add(row.caller.split("::")[-1])
        frontier = nxt - {c.name for c in dm.functions}
    for member in sorted({m for c in dm.functions for m in c.written_members}):
        for row in index.member_refs(member)[: cfg.heuristic_fanin_cap]:
            add(row.path, 1)

    ranked = sorted(hop, key=lambda p: (hop[p], -refs[p], p))
    sel.selected = ranked[: cfg.tu_budget]
    sel.hops = {p: hop[p] for p in sel.selected}
    sel.over_budget = max(0, len(ranked) - cfg.tu_budget)
    return sel


def field_follow_up(dm: DiffMap, after: list[Facts], index: SymbolIndex, cdb: CompileDb, sel: TuSelection,
                    cfg: AnalysisConfig) -> list[str]:
    """Second selection round, after clang facts exist for the changed TUs.

    Tree-sitter only sees `x->f = ...` writes; clang also sees writes through local aliases. For every field a
    changed function writes (per clang), add not-yet-parsed TUs that reference a same-named member and can see
    the record's declaration, so its readers get precise facts. Bounded by the remaining TU budget.
    """
    ranges: dict[str, list[tuple[int, int]]] = {}
    for c in dm.functions:
        if c.after_lines:
            ranges.setdefault(c.file, []).append(c.after_lines)
    changed_usrs = {f.usr for facts in after for f in facts.functions
                    if any(f.start_line <= hi and lo <= f.end_line for lo, hi in ranges.get(f.file, []))}
    written: dict[str, str] = {}
    for facts in after:
        for a in facts.fields:
            if a.fn in changed_usrs and a.mode != "read" and a.root_kind != "local":
                written.setdefault(a.field_name, a.record_file)
    tus, have = set(cdb.files()), set(sel.selected)
    extra: dict[str, None] = {}
    for name, rfile in sorted(written.items()):
        allowed = ({rfile} | index.transitive_includers(rfile)) if rfile else None
        rows = [r.path for r in index.member_refs(name)
                if r.path in tus and r.path not in have and (allowed is None or r.path in allowed)]
        if len(set(rows)) > cfg.heuristic_fanin_cap:
            continue
        for p in sorted(set(rows)):
            extra.setdefault(p, None)
    return list(extra)[: max(0, cfg.tu_budget - len(sel.selected))]
