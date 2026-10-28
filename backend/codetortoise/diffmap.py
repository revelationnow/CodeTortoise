"""Maps a ChangeSet to changed functions / types / macros using tree-sitter."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.cparse import FuncDef, is_source, parse_source
from codetortoise.linediff import edits, touches
from codetortoise.vcs.model import ChangeSet, FileChange

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
    misread: bool = False     # added or removed, yet the other version's text defines it where the parser found nothing


class TypeChange(BaseModel):
    file: str
    depot: str
    name: str
    kind: TypeChangeKind
    line: int | None = None           # new side (old side for a removed one)
    before: str = ""                  # its text in each version, whitespace collapsed ("" where it does not exist)
    after: str = ""
    fields_added: list[str] = Field(default_factory=list)     # a changed type's fields or enumerators
    fields_removed: list[str] = Field(default_factory=list)


class DiffMap(BaseModel):
    functions: list[FunctionChange] = Field(default_factory=list)
    types: list[TypeChange] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    flattened: list[str] = Field(default_factory=list)   # files whose functions were found on one branch of each #if


def _keyed(funcs: list[FuncDef]) -> dict[tuple[str, int], FuncDef]:
    counts: dict[str, int] = defaultdict(int)
    out = {}
    for f in sorted(funcs, key=lambda f: f.start_line):
        out[(f.qualname, counts[f.qualname])] = f
        counts[f.qualname] += 1
    return out


def _named(before: dict[str, tuple[int, str, tuple[str, ...]]], after: dict[str, tuple[int, str, tuple[str, ...]]],
           prefix: str, fc: FileChange) -> list[TypeChange]:
    """Added, removed and changed names of one kind (types, declarations or macros): name -> (line, text, fields)."""
    out = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if b is not None and a is not None and b[1] == a[1]:
            continue
        kind = f"{prefix}_added" if b is None else f"{prefix}_removed" if a is None else f"{prefix}_changed"
        added: list[str] = []
        removed: list[str] = []
        if a is not None and b is not None:
            had, has = set(b[2]), set(a[2])             # sets: a generated header's enum can hold thousands of names
            added, removed = [f for f in a[2] if f not in had], [f for f in b[2] if f not in has]
        out.append(TypeChange(file=fc.local, depot=fc.depot, name=name, kind=kind, line=(a or b)[0],
                              before=b[1] if b else "", after=a[1] if a else "",
                              fields_added=added, fields_removed=removed))
    return out


_DEF_HEAD = re.compile(r"^(?:[A-Za-z_][\w \t*&:<>,]*[ \t*&])?(~?[A-Za-z_]\w*|operator[^\w\s(]+)[ \t]*\(", re.M)
_TO_BODY = re.compile(r"[;{]")


def _defined(text: str) -> Counter[str]:
    """The names the text defines at the left margin, each with how many times: a type (or nothing) then the name and "("
    at the start of a line, then "{" before any ";" (a call is indented; a prototype reaches ";" first)."""
    out: Counter[str] = Counter()
    for m in _DEF_HEAD.finditer(text):
        nxt = _TO_BODY.search(text, m.end())
        if nxt is not None and nxt.group() == "{":
            out[m.group(1)] += 1
    return out


def map_changes(cs: ChangeSet) -> DiffMap:
    dm = DiffMap()
    for fc in cs.files:
        if not is_source(fc.local):
            continue
        dm.changed_files.append(fc.local)
        b = parse_source(fc.local, fc.before, flatten="auto")
        a = parse_source(fc.local, fc.after, flatten="auto")
        if b.flattened != a.flattened:             # read both versions the same way
            b = b if b.flattened else parse_source(fc.local, fc.before, flatten="always")
            a = a if a.flattened else parse_source(fc.local, fc.after, flatten="always")
        if a.flattened:
            dm.flattened.append(fc.local)
        bf, af = _keyed(b.functions), _keyed(a.functions)
        eb = ea = None                             # the edits on each side, worked out when a function first differs
        # per side, once an added or removed function needs it: the names its text defines more often than the parser found
        unread: dict[str, Counter[str]] = {}
        for key in sorted(set(bf) | set(af)):
            fb, fa = bf.get(key), af.get(key)
            if fb is not None and fa is not None and fb.text_hash == fa.text_hash:
                continue
            if eb is None:
                eb, ea = edits(fc.before, fc.after, "before"), edits(fc.before, fc.after, "after")
            if not ((fb is not None and touches(eb, fb.start_line, fb.end_line))
                    or (fa is not None and touches(ea, fa.start_line, fa.end_line))):
                continue                           # no edit in its own lines: the parser read the versions differently
            if fb is None:
                kind = "added"
            elif fa is None:
                kind = "removed"
            elif fb.signature != fa.signature:
                kind = "signature_changed"
            else:
                kind = "body_modified"
            ref = fa or fb
            misread = False
            if fb is None or fa is None:
                side, other, parsed = ("before", fc.before, b) if fb is None else ("after", fc.after, a)
                if side not in unread:
                    unread[side] = _defined(other) - Counter(f.name for f in parsed.functions)
                misread = unread[side][ref.name] > 0
            written = sorted({m.field for pf in (a, b) for m in pf.members
                              if m.is_write and m.fn == ref.qualname})
            dm.functions.append(FunctionChange(
                file=fc.local, depot=fc.depot, qualname=ref.qualname, name=ref.name, kind=kind,
                before_lines=(fb.start_line, fb.end_line) if fb else None,
                after_lines=(fa.start_line, fa.end_line) if fa else None,
                signature_before=fb.signature if fb else None,
                signature_after=fa.signature if fa else None,
                written_members=written, misread=misread))
        dm.types += _named({t.name: (t.start_line, t.text, t.fields) for t in b.types if t.name},
                           {t.name: (t.start_line, t.text, t.fields) for t in a.types if t.name}, "type", fc)
        dm.types += _named({d.qualname: (d.line, d.text, ()) for d in b.decls},
                           {d.qualname: (d.line, d.text, ()) for d in a.decls}, "decl", fc)
        dm.types += _named({m.name: (m.line, m.text, ()) for m in b.macros},
                           {m.name: (m.line, m.text, ()) for m in a.macros}, "macro", fc)
    return dm
