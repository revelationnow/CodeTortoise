"""Which functions a change edits: each parsed function's own lines (clang's where clang parsed its file, tree-sitter's
elsewhere) against its file's line diff, never the diff map's guess."""
from __future__ import annotations

import bisect
from itertools import accumulate
from typing import Literal

from codetortoise.cparse import norm_ws
from codetortoise.diffmap import DiffMap, FunctionChange
from codetortoise.facts.model import Facts, Function
from codetortoise.linediff import edits, lines, touches
from codetortoise.vcs.model import ChangeSet


def _text(rows: list[str], fn: Function) -> str:
    """A function's own lines of its file's lines, whitespace aside."""
    return norm_ws("\n".join(rows[fn.start_line - 1:fn.end_line]))


def _definitions(facts: list[Facts]) -> dict[str, list[Function]]:
    """usr -> all its definitions, in (file, start line) order. One usr can have several: tree-sitter gives every definition
    of a name in a file the same usr, and a non-static function defined in two parsed files has the same clang usr in both.
    A definition several TUs parsed (an inline function of a header) counts once."""
    out: dict[str, dict[tuple[str, int, int], Function]] = {}
    for fx in facts:
        for f in fx.functions:
            out.setdefault(f.usr, {})[(f.file, f.start_line, f.end_line)] = f
    return {u: [fns[k] for k in sorted(fns)] for u, fns in out.items()}


def _by_name(defs: dict[str, list[Function]]) -> dict[tuple[str, str], Function | None]:
    """(file, qualified name) -> the one function of that name in that file; None when there are several."""
    out: dict[tuple[str, str], Function | None] = {}
    for fns in defs.values():
        for f in fns:
            k = (f.file, f.qualname)
            out[k] = None if k in out else f
    return out


def changed_functions(before: list[Facts], after: list[Facts], cs: ChangeSet) -> dict[str, str]:
    """usr -> "changed", "added" or "removed", for each parsed function of a changed file whose own lines an edit touches.
    A usr with several definitions is edited when an edit touches any of them, and changed when their texts together,
    whitespace aside, differ. A function's other version is the one with its usr, else (each being the only definition of
    its usr) the only function of its file and qualified name (clang on one side, tree-sitter on the other); one with no
    other version is added or removed."""
    texts = {fc.local: (fc.before, fc.after) for fc in cs.files}
    db, da = _definitions(before), _definitions(after)
    named_b, named_a = _by_name(db), _by_name(da)
    pairs: list[tuple[list[Function] | None, list[Function] | None]] = []
    paired: set[str] = set()
    for u, fs in da.items():
        gs = db.get(u)
        key = (fs[0].file, fs[0].qualname)
        if gs is None and len(fs) == 1 and named_a.get(key) is fs[0]:
            g = named_b.get(key)
            if g is not None and len(db[g.usr]) == 1:
                gs = db[g.usr]
        if gs is not None:
            paired.add(gs[0].usr)
        pairs.append((gs, fs))
    pairs += [(gs, None) for u, gs in db.items() if u not in paired]

    spans: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {}   # (file, side) -> its edits, worked out once

    def hit(fns: list[Function] | None, side: Literal["before", "after"]) -> bool:
        """Whether an edit touches any of these definitions on that side."""
        for fn in fns or ():
            if fn.file in texts:
                if (fn.file, side) not in spans:
                    spans[(fn.file, side)] = edits(*texts[fn.file], side)
                if touches(spans[(fn.file, side)], fn.start_line, fn.end_line):
                    return True
        return False

    split: dict[tuple[str, int], list[str]] = {}               # (file, side) -> its lines, split once

    def joined(fns: list[Function], side: int) -> str:
        """The texts of all a usr's definitions on one side (0: before, 1: after), one after the other; a file outside the
        change has no text."""
        for f in fns:
            if (f.file, side) not in split:
                split[(f.file, side)] = lines(texts.get(f.file, ("", ""))[side])
        return "\n".join(_text(split[(f.file, side)], f) for f in fns)

    out: dict[str, str] = {}
    for b, a in pairs:
        if not (hit(b, "before") or hit(a, "after")):
            continue
        if b is None:
            out[a[0].usr] = "added"
        elif a is None:
            out[b[0].usr] = "removed"
        elif joined(b, 0) != joined(a, 1):
            out[a[0].usr] = "changed"
    return out


def unparsed(dm: DiffMap, before: list[Facts], after: list[Facts]) -> list[FunctionChange]:
    """The diff map's function changes that no parsed function covers on their side: code this configuration's #ifs leave
    out, or a file no parse reached. Their edits reach no node of the impact model."""
    def spans(facts: list[Facts]) -> dict[str, tuple[list[int], list[int]]]:
        """file -> its parsed functions' start lines in order, and for each the furthest end line of those starting at or
        before it: a range overlaps a function when the functions starting by its last line reach as far as its first."""
        got: dict[str, list[tuple[int, int]]] = {}
        for fx in facts:
            for f in fx.functions:
                got.setdefault(f.file, []).append((f.start_line, f.end_line))
        out: dict[str, tuple[list[int], list[int]]] = {}
        for file, ss in got.items():
            ss.sort()
            out[file] = ([s for s, _ in ss], list(accumulate((e for _, e in ss), max)))
        return out
    sb, sa = spans(before), spans(after)

    def covered(file: str, span: tuple[int, int], got: dict[str, tuple[list[int], list[int]]]) -> bool:
        starts, reach = got.get(file, ([], []))
        k = bisect.bisect_right(starts, span[1])
        return k > 0 and reach[k - 1] >= span[0]
    return [c for c in dm.functions
            if not (covered(c.file, c.after_lines, sa) if c.after_lines else
                    c.before_lines is not None and covered(c.file, c.before_lines, sb))]
