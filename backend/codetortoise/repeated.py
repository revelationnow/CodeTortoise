"""Repeated edits: one token substitution explaining whole functions (spec 2026-10-04-change-stories §2.1), and the
few words saying what changed in a node. Stories and pieces (spec 2026-10-05-two-tier-stories §3.2) share them."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from codetortoise.board import BoardContext, _count, _Ctx
from codetortoise.substitutions import Site, Sub, changed_pairs


@dataclass
class Repeated:
    fn_sites: dict[str, list[Site]] = field(default_factory=dict)     # changed function -> its substitution sites
    fn_explained: dict[str, bool] = field(default_factory=dict)       # every changed line is a substitution
    outside: list[tuple[Site, str]] = field(default_factory=list)     # sites outside functions, with their file
    count: Counter = field(default_factory=Counter)                   # substitution -> its sites
    mech_subs: set[Sub] = field(default_factory=set)                  # substitutions explaining at least 2 functions
    mech_of: dict[str, Sub] = field(default_factory=dict)             # mechanical function -> its substitution


def _q(s: str) -> str:
    return f"`{s}`"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def find_repeated(c: BoardContext, x: _Ctx) -> Repeated:
    """Substitutions in each changed function and outside functions; those explaining at least 2 functions."""
    im = x.im
    changed = [n for n in im.changed if n in im.nodes]
    fn_sites: dict[str, list[Site]] = {}
    fn_explained: dict[str, bool] = {}
    for nid in changed:
        if im.nodes[nid].kind != "function":
            continue
        spans = _spans(x, nid)
        if not spans:
            continue
        all_sites, unexplained = [], 0
        for fc, (b0, b1), (a0, a1) in spans:
            sites, u = changed_pairs(fc.before.splitlines()[b0 - 1:b1], fc.after.splitlines()[a0 - 1:a1])
            all_sites += [Site(s.sub, s.before_line + b0 - 1, s.after_line + a0 - 1, s.before, s.after) for s in sites]
            unexplained += u
        fn_sites[nid] = all_sites
        fn_explained[nid] = bool(all_sites) and not unexplained
    outside: list[tuple[Site, str]] = []
    spans_a: dict[str, list[tuple[int, int]]] = defaultdict(list)     # file -> its functions' lines, after and before
    spans_b: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for facts, spans in ((c.after, spans_a), (c.before, spans_b)):
        for fx in facts:
            for f in fx.functions:
                spans[f.file].append((f.start_line, f.end_line))
    for fc in c.cs.files:
        if fc.action != "edit":
            continue
        inside_a, inside_b = spans_a[fc.local], spans_b[fc.local]
        sites, _ = changed_pairs(fc.before.splitlines(), fc.after.splitlines())
        for s in sites:
            if not any(lo <= s.after_line <= hi for lo, hi in inside_a) and not any(lo <= s.before_line <= hi
                                                                                   for lo, hi in inside_b):
                outside.append((s, fc.local))

    fns_of: dict[Sub, set[str]] = defaultdict(set)
    for nid, sites in fn_sites.items():
        if fn_explained[nid]:
            for s in sites:
                fns_of[s.sub].add(nid)
    count: Counter[Sub] = Counter(s.sub for sites in fn_sites.values() for s in sites)
    count.update(s.sub for s, _ in outside)
    mech_subs = {s for s, fns in fns_of.items() if len(fns) >= 2}
    mech_of: dict[str, Sub] = {}                              # mechanical function -> its story's substitution
    for nid, sites in fn_sites.items():
        subs = {s.sub for s in sites}
        if fn_explained[nid] and subs <= mech_subs:
            mech_of[nid] = max(subs, key=lambda s: (count[s], s.old, s.new))
    return Repeated(fn_sites, fn_explained, outside, count, mech_subs, mech_of)


def _spans(x: _Ctx, nid: str) -> list[tuple]:
    """A changed function's (file, before lines, after lines), from the diff map: a function defined twice in one file
    (under #ifdef) is the definition that changed, not the first the facts list."""
    n = x.im.nodes[nid]
    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
    if fb is None or fa is None:
        return []
    texts = x.texts
    out = [(texts[d.file], d.before_lines, d.after_lines) for d in x.c.dm.functions
           if d.qualname == fa.qualname and d.file in (fa.file, fb.file) and d.before_lines and d.after_lines
           and d.file in texts]
    own = [o for o in out if o[2][0] <= fa.start_line <= o[2][1]]     # overloads share a name: each reads its own span
    out = own or out
    if not out and fa.file in texts:
        out = [(texts[fa.file], (fb.start_line, fb.end_line), (fa.start_line, fa.end_line))]
    return out


def _note(x: _Ctx, nid: str, mech_of: dict[str, Sub], fn_sites: dict[str, list[Site]], mech_subs: set) -> str:
    """What changed in a node, in a few words."""
    n = x.im.nodes[nid]
    if nid not in x.changed:
        return ""
    if nid in mech_of:
        s = mech_of[nid]
        return f"{_q(s.new)} instead of {_q(s.old)}"
    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
    parts = []
    if fb is None and fa is not None:
        parts.append("new function")
    elif fa is None and fb is not None:
        parts.append("removed")
    else:
        ch = next((d for d in x.c.dm.functions if fa and d.file == fa.file and d.qualname == fa.qualname), None)
        if ch is not None and ch.kind == "signature_changed":
            parts.append("signature changed")
    for status, verb in (("added", "now writes"), ("removed", "no longer writes")):
        fields = [x.label(e.dst).split("::")[-1] for e in x.writes_from.get(nid, [])
                  if e.status == status and e.dst in x.im.nodes and e.dst not in x.im.sinks]
        if fields:
            parts.append(f"{verb} {', '.join(dict.fromkeys(fields[:3]))}" + (f" +{len(fields) - 3}" if len(fields) > 3 else ""))
    also = sorted({s.sub for s in fn_sites.get(nid, []) if s.sub in mech_subs}, key=lambda s: s.old)
    if also:
        parts.append("also " + ", ".join(f"{_q(s.old)} → {_q(s.new)}" for s in also[:2]))
    if not parts:
        add = rem = 0
        for fc, _, (a0, a1) in _spans(x, nid):
            a, r = _count(fc.before, fc.after, a0, a1)
            add, rem = add + a, rem + r
        parts.append(f"+{add} −{rem} lines" if add or rem else "layout only")
    return "; ".join(parts)
