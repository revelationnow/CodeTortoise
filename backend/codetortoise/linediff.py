"""A file's line diff and the lines each edit takes up: what decides which code a change touched."""
from __future__ import annotations

import bisect
import difflib
import functools
import re
from typing import Literal

_BREAK = re.compile(r"\r\n|\r|\n")


def lines(text: str) -> list[str]:
    """A file's lines as clang numbers them: broken at a newline, a carriage return plus newline or a lone carriage return,
    and nowhere else (str.splitlines also breaks at a form feed and other separators, which would shift every later line).
    A final line break ends the last line; it does not start another. tree-sitter's own rows break at a newline only;
    `cparse.parse_source` reports its lines numbered the same way as these."""
    out = _BREAK.split(text)
    if out[-1] == "":
        out.pop()
    return out


def matched_opcodes(a: list[str], b: list[str]) -> list[tuple[str, int, int, int, int]]:
    """SequenceMatcher's opcodes for a to b, matching only what lies between their common first and last lines: the
    matcher is quadratic on repeated lines (blank ones), and a CL's edit usually touches a small part of a big file."""
    n, m = len(a), len(b)
    p = 0
    while p < n and p < m and a[p] == b[p]:
        p += 1
    q = 0
    while q < n - p and q < m - p and a[n - 1 - q] == b[m - 1 - q]:
        q += 1
    mid = [(t, i1 + p, i2 + p, j1 + p, j2 + p)
           for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a[p:n - q], b[p:m - q], autojunk=False).get_opcodes()
           if (t, i1, i2, j1, j2) != ("equal", 0, 0, 0, 0)]
    return [("equal", 0, p, 0, p)] * (p > 0) + mid + [("equal", n - q, n, m - q, m)] * (q > 0)


# A review walks its files several times (facts, impact, board), so the caches below must hold a whole change; their keys
# are references to texts the change set already holds, not copies.
@functools.lru_cache(maxsize=1024)
def opcodes(before: str, after: str) -> tuple:
    """A file's line diff, once: every function of the file is counted against it."""
    return tuple(matched_opcodes(lines(before), lines(after)))


@functools.lru_cache(maxsize=2048)
def edits(before: str, after: str, side: Literal["before", "after"]) -> tuple[tuple[int, int], ...]:
    """The lines each edit takes up on one side (1-based, inclusive), in order. A pure insertion (seen from the before side)
    or deletion (from the after side) takes up the line after its position, so one just inside a function touches it."""
    out = []
    for tag, i1, i2, j1, j2 in opcodes(before, after):
        if tag != "equal":
            s, e = (i1, i2) if side == "before" else (j1, j2)
            out.append((s + 1, max(e, s + 1)))
    return tuple(out)


def touches(spans: tuple[tuple[int, int], ...], lo: int, hi: int) -> bool:
    """Whether any of `spans` (from `edits`, so in order) overlaps lines lo..hi."""
    k = bisect.bisect_left(spans, lo, key=lambda s: s[1])     # the first edit ending at or after lo
    return k < len(spans) and spans[k][0] <= hi
