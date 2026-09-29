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
