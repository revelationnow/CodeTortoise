"""Maps a ChangeSet to changed functions / types / macros using tree-sitter."""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.cparse import FuncDef, is_source, parse_source
from codetortoise.vcs.model import ChangeSet

FunctionChangeKind = Literal["added", "removed", "body_modified", "signature_changed"]
TypeChangeKind = Literal["type_added", "type_removed", "type_changed",
                         "macro_added", "macro_removed", "macro_changed",
                         "decl_added", "decl_removed", "decl_changed"]


class FunctionChange(BaseModel):
    file: str
    depot: str
    qualname: str
    name: str
    kind: FunctionChangeKind
    before_lines: tuple[int, int] | None = None
    after_lines: tuple[int, int] | None = None
    signature_before: str | None = None
    signature_after: str | None = None
    written_members: list[str] = Field(default_factory=list)


class TypeChange(BaseModel):
    file: str
    depot: str
    name: str
    kind: TypeChangeKind


class DiffMap(BaseModel):
    functions: list[FunctionChange] = Field(default_factory=list)
    types: list[TypeChange] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)


def _keyed(funcs: list[FuncDef]) -> dict[tuple[str, int], FuncDef]:
    counts: dict[str, int] = defaultdict(int)
    out = {}
    for f in sorted(funcs, key=lambda f: f.start_line):
        out[(f.qualname, counts[f.qualname])] = f
        counts[f.qualname] += 1
    return out


def _diff_named(before: dict[str, str], after: dict[str, str], prefix: str) -> list[tuple[str, str]]:
    out = []
    for name in sorted(set(before) | set(after)):
        if name not in before:
            out.append((name, f"{prefix}_added"))
        elif name not in after:
            out.append((name, f"{prefix}_removed"))
        elif before[name] != after[name]:
            out.append((name, f"{prefix}_changed"))
    return out


def map_changes(cs: ChangeSet) -> DiffMap:
    dm = DiffMap()
    for fc in cs.files:
        if not is_source(fc.local):
            continue
        dm.changed_files.append(fc.local)
        b = parse_source(fc.local, fc.before)
        a = parse_source(fc.local, fc.after)
        bf, af = _keyed(b.functions), _keyed(a.functions)
        for key in sorted(set(bf) | set(af)):
            fb, fa = bf.get(key), af.get(key)
            if fb is not None and fa is not None and fb.text_hash == fa.text_hash:
                continue
            if fb is None:
                kind = "added"
            elif fa is None:
                kind = "removed"
            elif fb.signature != fa.signature:
                kind = "signature_changed"
            else:
                kind = "body_modified"
            ref = fa or fb
            written = sorted({m.field for pf in (a, b) for m in pf.members
                              if m.is_write and m.fn == ref.qualname})
            dm.functions.append(FunctionChange(
                file=fc.local, depot=fc.depot, qualname=ref.qualname, name=ref.name, kind=kind,
                before_lines=(fb.start_line, fb.end_line) if fb else None,
                after_lines=(fa.start_line, fa.end_line) if fa else None,
                signature_before=fb.signature if fb else None,
                signature_after=fa.signature if fa else None,
                written_members=written))
        for name, kind in _diff_named({t.name: t.text for t in b.types if t.name},
                                      {t.name: t.text for t in a.types if t.name}, "type"):
            dm.types.append(TypeChange(file=fc.local, depot=fc.depot, name=name, kind=kind))
        for name, kind in _diff_named({d.qualname: d.text for d in b.decls},
                                      {d.qualname: d.text for d in a.decls}, "decl"):
            dm.types.append(TypeChange(file=fc.local, depot=fc.depot, name=name, kind=kind))
        for name, kind in _diff_named({m.name: m.text for m in b.macros},
                                      {m.name: m.text for m in a.macros}, "macro"):
            dm.types.append(TypeChange(file=fc.local, depot=fc.depot, name=name, kind=kind))
    return dm
