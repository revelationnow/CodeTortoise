"""CLs as a sequence (spec 2026-10-07-review-reading-phase2 §4): for a file several CLs of a review edit, which CL wrote
each line of its final text, which CL removed each base line, and which later CL rewrote lines an earlier one added."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from codetortoise.facts.model import Function
from codetortoise.vcs.model import ChangeSet, FileChange


class Gap(BaseModel):
    """A CL outside the review changed `file` between review CLs `after_cl` and `before_cl` — or, with `same_base`,
    `before_cl` was made against the base, not on top of `after_cl` (two CLs shelved against one revision)."""
    file: str
    after_cl: int
    before_cl: int
    same_base: bool = False


class Rewrite(BaseModel):
    """CL `by` replaced or deleted `lines` lines CL `of` added to `file` (a depot path); `line` is the first final line
    written in their place and `function` the function holding it (None when nothing of `by` stands there)."""
    by: int
    of: int
    file: str
    function: str | None = None
    lines: int
    line: int | None = None


class FileLines(BaseModel):
    depot: str
    local: str = ""
    wrote: list[int | None] = Field(default_factory=list)      # per final line: the CL that wrote it
    over: list[int | None] = Field(default_factory=list)       # per final line: the earlier CL whose lines it replaced
    removed: list[int | None] = Field(default_factory=list)    # per base line: the CL that removed it
    rewritten: dict[int, dict[int, int]] = Field(default_factory=dict)  # [cl a][its after line m] = the CL replacing it
    replaced: list[tuple[int, int, int, int | None]] = Field(default_factory=list)  # (a, m, by, final line in its place)
    gaps: list[Gap] = Field(default_factory=list)


@dataclass
class _Line:
    id: int
    origin: tuple[int, int] | None      # (CL, line in that CL's after text); None: the base or outside the review
    over: int | None
    base: int | None                    # its line in the base text, while it is still the base's


def _split(text: str) -> list[str]:
    """Lines as the browser's diff counts them (`codeRows.ts`): split on "\n" only, so a form feed or lone CR stays
    inside its line and line n here is row n there."""
    lines = text.split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def _opcodes(a: list[str], b: list[str]) -> list[tuple[str, int, int, int, int]]:
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
           for t, i1, i2, j1, j2 in SequenceMatcher(None, a[p:n - q], b[p:m - q], autojunk=False).get_opcodes()
           if (t, i1, i2, j1, j2) != ("equal", 0, 0, 0, 0)]
    return [("equal", 0, p, 0, p)] * (p > 0) + mid + [("equal", n - q, n, m - q, m)] * (q > 0)


def walk(fc: FileChange) -> FileLines:
    """Walk the file's CLs in order (§4.2): each CL's diff from its before to its after moves the lines' origins along;
    a CL whose before is not the previous after had an outside change first (a gap, whose lines carry no CL)."""
    cur = base = _split(fc.before)
    ids = iter(range(1 << 62))
    attrs = [_Line(next(ids), None, None, i) for i in range(len(cur))]
    removed: list[int | None] = [None] * len(cur)
    rewritten: dict[int, dict[int, int]] = defaultdict(dict)
    events: list[tuple[int, int, int, int | None]] = []      # (a, m, by, id of the first line put in their place)
    gaps: list[Gap] = []
    prev: int | None = None

    def apply(new: list[str], cl: int | None) -> None:
        nonlocal cur, attrs
        out: list[_Line] = []
        for tag, i1, i2, j1, j2 in _opcodes(cur, new):
            if tag == "equal":
                out += attrs[i1:i2]
                continue
            gone = attrs[i1:i2]
            put = [_Line(next(ids), (cl, j + 1) if cl is not None else None, None, None) for j in range(j1, j2)]
            if cl is not None:
                earlier = [g.origin[0] for g in gone if g.origin is not None]
                for p in put:
                    p.over = max(earlier) if earlier else None
                for g in gone:
                    if g.origin is not None:
                        rewritten[g.origin[0]][g.origin[1]] = cl
                        events.append((g.origin[0], g.origin[1], cl, put[0].id if put else None))
                    elif g.base is not None:
                        removed[g.base] = cl
            out += put
        cur, attrs = new, out

    for st in sorted(fc.per_cl, key=lambda s: s.cl):
        before = _split(st.before)
        if before != cur:
            if prev is not None:
                gaps.append(Gap(file=fc.depot, after_cl=prev, before_cl=st.cl, same_base=before == base))
            apply(before, None)
        apply(_split(st.after), st.cl)
        prev = st.cl
    at = {a.id: i + 1 for i, a in enumerate(attrs)}
    return FileLines(depot=fc.depot, local=fc.local, wrote=[a.origin[0] if a.origin else None for a in attrs],
                     over=[a.over for a in attrs], removed=removed, rewritten=dict(rewritten),
                     replaced=[(a, m, by, at.get(put) if put is not None else None) for a, m, by, put in events], gaps=gaps)


def _holding(fns: list[Function], local: str, line: int | None) -> str | None:
    """The innermost function of `local` whose lines hold `line`."""
    if line is None:
        return None
    inside = [f for f in fns if f.file == local and f.start_line <= line <= f.end_line]
    return min(inside, key=lambda f: f.end_line - f.start_line).qualname if inside else None


def rewrites(lines: dict[str, FileLines], fns: list[Function]) -> list[Rewrite]:
    """The review's rewrites (§4.3), one per file, CL pair and function; `fns` are the after facts' functions."""
    rows: dict[tuple[str, int, int, str | None], Rewrite] = {}
    for depot, fl in lines.items():
        for a, _, by, line in fl.replaced:
            fn = _holding(fns, fl.local, line)
            r = rows.setdefault((depot, by, a, fn), Rewrite(by=by, of=a, file=depot, function=fn, lines=0, line=line))
            r.lines += 1
            if line is not None and (r.line is None or line < r.line):
                r.line = line
    return sorted(rows.values(), key=lambda r: (r.file, r.of, r.by, r.line or 0, r.function or ""))


def file_lines(cs: ChangeSet) -> dict[str, FileLines]:
    """Each file more than one CL of the change set touches, walked; a file one CL touches needs no walk (§4.1)."""
    return {f.depot: walk(f) for f in cs.files if len({p.cl for p in f.per_cl}) > 1}
