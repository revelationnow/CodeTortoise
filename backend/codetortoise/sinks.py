"""Shared sinks (spec 2026-10-09-shared-sinks): fields like a log buffer that so many functions touch that a new write
to one says nothing about its users. A run decides them once, on the impact model; every view leaves their users out."""
from __future__ import annotations

import fnmatch
from collections import defaultdict
from collections.abc import Collection
from typing import Any

from codetortoise.impact import ImpactModel, SinkInfo

MARKS_KEY = "sink_marks"          # the store's kv row: the owner's marked labels, for every review of the workspace


def find_sinks(im: ImpactModel, threshold: int, patterns: list[str], marked: Collection[str]) -> dict[str, SinkInfo]:
    """Field node id -> why it is a sink: the owner marked its label, a pattern matches it, or more than `threshold`
    unchanged functions read or write it (precise and name-matched alike, plus name matches over the fan-in cap)."""
    changed = set(im.changed)
    who: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if e.kind in ("reads", "writes") and e.status != "removed" and e.src not in changed:
            who[e.dst].add(e.src)
    marked = set(marked)
    out: dict[str, SinkInfo] = {}
    for nid, n in im.nodes.items():
        if n.kind != "field":
            continue
        users = len(who.get(nid, ())) + im.capped.get(n.label, 0)
        if n.label in marked:
            why = "marked"
        elif any(fnmatch.fnmatchcase(n.label, p) for p in patterns):
            why = "listed"
        elif threshold > 0 and users > threshold:
            why = "threshold"
        else:
            continue
        out[nid] = SinkInfo(field=nid, label=n.label, users=users, why=why)
    return out


def why_text(s: Any) -> str:
    """Why a field is a sink, as the review says it: "312 functions", "in tortoise.yaml" or "marked"."""
    return {"threshold": f"{s.users} functions", "listed": "in tortoise.yaml", "marked": "marked"}[s.why]


def marks(store: Any) -> list[str]:
    got = store.kv_get(MARKS_KEY)
    return sorted(x for x in got if isinstance(x, str)) if isinstance(got, list) else []


def set_mark(store: Any, label: str, on: bool) -> list[str]:
    """Mark or unmark `label` for every review from the next run; the marks after."""
    cur = set(marks(store))
    cur = cur | {label} if on else cur - {label}
    store.kv_put(MARKS_KEY, sorted(cur))
    return sorted(cur)
