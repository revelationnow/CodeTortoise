"""Checks grouped by the change that raised them (spec 2026-10-16-outline-and-causes §4)."""
from __future__ import annotations

import hashlib
from collections import defaultdict

from codetortoise.board import Flow, _Ctx
from codetortoise.reading import CHECK_ORDER, Cause, Check, Thread, _qual

_ALONE = {"unanalysed", "ask"}       # a row of these kinds is its own cause


def cause_id(kind: str, qual: str, subject: str) -> str:
    """Stable across re-runs: kind, the function's qualified name and the subject only."""
    return "c" + hashlib.sha1(f"{kind}|{qual}|{subject}".encode()).hexdigest()[:10]


def _group(k: Check, x: _Ctx) -> tuple[str, str, str]:
    if k.kind == "untested":
        return k.kind, f"story:{k.story or ''}", ""
    if k.kind in _ALONE:
        return k.kind, "", k.key
    return k.kind, _qual(x, k.cause_fn) if k.cause_fn else "", k.cause_subject


def _text(kind: str, rows: list[Check], fn: str) -> str:
    n = len(rows)
    if n == 1 or kind in ("hazard", "confirm") or kind in _ALONE:
        return rows[0].text
    if kind == "reader":
        return f"{n} places read `{rows[0].field}`, which `{fn}` now writes"
    if kind == "caller":
        return f"{n} callers not updated for `{fn}`'s new signature"
    if kind == "result":
        return f"{n} callers handle `{fn}`'s result the old way"
    if kind == "target":
        return f"{n} calls to `{fn}` from other build targets" if fn else rows[0].text
    return f"{n} functions no test calls"          # untested


def build_causes(rows: list[Check], x: _Ctx, threads: list[Thread], order: list[str],
                 flows_of: dict[str, list[Flow]]) -> list[Cause]:
    """Every row's cause, in reading order (§4.5): thread, the story's reading order, the first flow it touches, kind
    order, text. Sets each row's `cause`."""
    groups: dict[tuple[str, str, str], list[Check]] = defaultdict(list)
    for k in rows:
        groups[_group(k, x)].append(k)
    by_id: dict[str, Cause] = {}
    for (kind, qual, subject), members in groups.items():
        members.sort(key=lambda k: (k.path, k.line or 0, k.key))
        lead = members[0]
        if kind == "untested":
            qual = ",".join(sorted({_qual(x, k.cause_fn) for k in members if k.cause_fn}))
        cid = cause_id(kind, qual, subject)
        for k in members:
            k.cause = cid
        if cid in by_id:                                  # two groups with one id are one cause
            by_id[cid].places += [k.key for k in members]
            continue
        fn = x.label(lead.cause_fn) if lead.cause_fn else ""
        touched = {lead.cause_fn} | {k.node for k in members}
        flows = [fl.id for fl in flows_of.get(lead.story or "", []) if touched & set(fl.path)]
        by_id[cid] = Cause(id=cid, kind=kind, thread=lead.thread, story=lead.story, text=_text(kind, members, fn),
                           places=[k.key for k in members], flows=flows, finding=lead.finding)
    thread_at = {t.id: i for i, t in enumerate(threads)}
    story_at = {s: i for i, s in enumerate(order)}
    rank = {k: i for i, k in enumerate(CHECK_ORDER)}

    def first_flow(z: Cause) -> int:
        ids = [fl.id for fl in flows_of.get(z.story or "", [])]
        return min((ids.index(f) for f in z.flows), default=len(ids))
    return sorted(by_id.values(), key=lambda z: (thread_at.get(z.thread or "", len(threads)),
                                                 story_at.get(z.story or "", len(order)), first_flow(z), rank[z.kind], z.text))
