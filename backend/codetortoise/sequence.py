"""CLs as a sequence (spec 2026-10-07-review-reading-phase2 §4): for a file several CLs of a review edit, which CL wrote
each line of its final text, which CL removed each base line, and which later CL rewrote lines an earlier one added."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from codetortoise.vcs.model import FileChange


class Gap(BaseModel):
    """A CL outside the review changed `file` between review CLs `after_cl` and `before_cl`."""
    file: str
    after_cl: int
    before_cl: int


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
    return text.splitlines()


def walk(fc: FileChange) -> FileLines:
    """Walk the file's CLs in order (§4.2): each CL's diff from its before to its after moves the lines' origins along;
    a CL whose before is not the previous after had an outside change first (a gap, whose lines carry no CL)."""
    cur = _split(fc.before)
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
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, cur, new, autojunk=False).get_opcodes():
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
                gaps.append(Gap(file=fc.depot, after_cl=prev, before_cl=st.cl))
            apply(before, None)
        apply(_split(st.after), st.cl)
        prev = st.cl
    at = {a.id: i + 1 for i, a in enumerate(attrs)}
    return FileLines(depot=fc.depot, local=fc.local, wrote=[a.origin[0] if a.origin else None for a in attrs],
                     over=[a.over for a in attrs], removed=removed, rewritten=dict(rewritten),
                     replaced=[(a, m, by, at.get(put) if put is not None else None) for a, m, by, put in events], gaps=gaps)
