"""Which functions a change edits: each parsed function's own lines (clang's where clang parsed its file, tree-sitter's
elsewhere) against its file's line diff, never the diff map's guess."""
from __future__ import annotations

from codetortoise.cparse import norm_ws
from codetortoise.diffmap import DiffMap, FunctionChange
from codetortoise.facts.model import Facts, Function
from codetortoise.linediff import edits, touches
from codetortoise.vcs.model import ChangeSet


def _text(text: str, fn: Function) -> str:
    return norm_ws("\n".join(text.splitlines()[fn.start_line - 1:fn.end_line]))


def _by_name(fns: dict[str, Function]) -> dict[tuple[str, str], Function | None]:
    """(file, qualified name) -> the one function of that name in that file; None when there are several."""
    out: dict[tuple[str, str], Function | None] = {}
    for f in fns.values():
        k = (f.file, f.qualname)
        out[k] = None if k in out else f
    return out


def changed_functions(before: list[Facts], after: list[Facts], cs: ChangeSet) -> dict[str, str]:
    """usr -> "changed", "added" or "removed", for each parsed function of a changed file whose own lines an edit touches.
    A function's other version is the one with its usr, else the only function of its file and qualified name (clang on
    one side, tree-sitter on the other); one with no other version is added or removed; one whose text, whitespace aside,
    is the same in both versions is left out."""
    texts = {fc.local: (fc.before, fc.after) for fc in cs.files}
    fb = {f.usr: f for facts in before for f in facts.functions}
    fa = {f.usr: f for facts in after for f in facts.functions}
    named_b, named_a = _by_name(fb), _by_name(fa)
    pairs: list[tuple[Function | None, Function | None]] = []
    paired: set[str] = set()
    for u, f in fa.items():
        g = fb.get(u)
        if g is None and named_a.get((f.file, f.qualname)) is f:
            g = named_b.get((f.file, f.qualname))
        if g is not None:
            paired.add(g.usr)
        pairs.append((g, f))
    pairs += [(f, None) for u, f in fb.items() if u not in paired]

    spans: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {}   # (file, side) -> its edits, worked out once

    def hit(fn: Function | None, side: str) -> bool:
        if fn is None or fn.file not in texts:
            return False
        if (fn.file, side) not in spans:
            spans[(fn.file, side)] = edits(*texts[fn.file], side)
        return touches(spans[(fn.file, side)], fn.start_line, fn.end_line)

    out: dict[str, str] = {}
    for b, a in pairs:
        if not (hit(b, "before") or hit(a, "after")):
            continue
        if b is None:
            out[a.usr] = "added"
        elif a is None:
            out[b.usr] = "removed"
        elif _text(texts.get(b.file, ("", ""))[0], b) != _text(texts.get(a.file, ("", ""))[1], a):
            out[a.usr] = "changed"
    return out


def unparsed(dm: DiffMap, before: list[Facts], after: list[Facts]) -> list[FunctionChange]:
    """The diff map's function changes that no parsed function covers on their side: code this configuration's #ifs leave
    out, or a file no parse reached. Their edits reach no node of the impact model."""
    def spans(facts: list[Facts]) -> dict[str, list[tuple[int, int]]]:
        out: dict[str, list[tuple[int, int]]] = {}
        for fx in facts:
            for f in fx.functions:
                out.setdefault(f.file, []).append((f.start_line, f.end_line))
        return out
    sb, sa = spans(before), spans(after)

    def covered(file: str, lines: tuple[int, int], got: dict[str, list[tuple[int, int]]]) -> bool:
        return any(s <= lines[1] and lines[0] <= e for s, e in got.get(file, ()))
    return [c for c in dm.functions
            if not (covered(c.file, c.after_lines, sa) if c.after_lines else
                    c.before_lines is not None and covered(c.file, c.before_lines, sb))]
