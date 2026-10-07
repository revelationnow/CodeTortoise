"""Heuristic FactExtractor used when clang cannot parse a TU."""
from __future__ import annotations

from pathlib import Path

from codetortoise.cparse import parse_source
from codetortoise.facts.clang_extractor import TuRequest, _norm
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function, TuInfo


def extract_tu_treesitter(req: TuRequest, reason: str = "") -> Facts:
    file = _norm(req.file)
    text = req.unsaved.get(req.file)
    if text is None:
        p = Path(req.file)
        text = p.read_text(errors="replace") if p.exists() else ""
    pf = parse_source(file, text)

    def usr(q: str) -> str:
        return f"ts:{file}#{q}"

    facts = Facts(tu=TuInfo(file=file, variant=req.variant, confidence="failed", extractor="treesitter",
                            diagnostics=[reason] if reason else []))
    for f in pf.functions:
        facts.functions.append(Function(usr=usr(f.qualname), qualname=f.qualname, name=f.name,
                                        signature=f.signature, return_type="", file=file,
                                        start_line=f.start_line, end_line=f.end_line))
    for c in pf.calls:
        if c.caller:
            facts.calls.append(CallEdge(caller=usr(c.caller), callee=f"name:{c.callee}", callee_name=c.callee,
                                        file=file, line=c.line, confidence="heuristic"))
    for m in pf.members:
        if m.fn:
            facts.fields.append(FieldAccess(fn=usr(m.fn), field=f"name:{m.field}", field_name=m.field, record="",
                                            path=f"?.{m.field}", root_kind="unknown",
                                            mode="write" if m.is_write else "read", file=file, line=m.line,
                                            confidence="heuristic"))
    return facts


def supplement(facts: Facts, ts: Facts) -> Facts:
    """Add to a degraded clang parse the calls and field accesses tree-sitter sees and clang dropped, as heuristic facts.

    Only functions clang found are supplemented (matched by qualname, else by line). A callee clang already calls from
    that function, a name in capitals (a macro) or one of the function's parameters (a call through a pointer) is
    skipped, as is a field the function already accesses.
    """
    mine = [f for f in facts.functions if f.file == facts.tu.file]
    by_qual = {f.qualname: f for f in mine}

    def match(qualname: str, line: int):
        return by_qual.get(qualname) or next((f for f in mine if f.start_line <= line <= f.end_line), None)

    tsfn = {f.usr: f for f in ts.functions}
    owner = {u: match(f.qualname, f.start_line) for u, f in tsfn.items()}
    called = {(c.caller, c.callee_name.split("::")[-1]) for c in facts.calls}
    touched = {(a.fn, a.field_name) for a in facts.fields}
    added = 0
    for c in ts.calls:
        fn = owner.get(c.caller)
        if fn is None or c.callee_name.isupper() or c.callee_name in {p.name for p in fn.params}:
            continue
        if (fn.usr, c.callee_name) in called:
            continue
        called.add((fn.usr, c.callee_name))
        facts.calls.append(c.model_copy(update={"caller": fn.usr}))
        added += 1
    for a in ts.fields:
        fn = owner.get(a.fn)
        if fn is None or (fn.usr, a.field_name) in touched:
            continue
        touched.add((fn.usr, a.field_name))
        facts.fields.append(a.model_copy(update={"fn": fn.usr}))
        added += 1
    facts.tu.supplemented = added
    return facts
