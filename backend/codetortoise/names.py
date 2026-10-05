"""Names and neighbours of graph nodes for the review workspace (spec 2026-10-04-review-workspace §4.2–§4.3): the
reader sees a function's name, never its node id."""
from __future__ import annotations

import re
from collections.abc import Iterable

from codetortoise.board import is_test_path
from codetortoise.impact import ImpactModel

CITE = re.compile(r"\bN\d+\b")


def cited(texts: Iterable[str | None]) -> set[str]:
    """Node ids (`N12`) named in text."""
    return {m for t in texts if t for m in CITE.findall(t)}


def _name(im: ImpactModel, nid: str, depot_of: dict[str, list[str] | None], node_story: dict[str, str]) -> dict:
    n = im.nodes[nid]
    files = depot_of.get(nid) or []
    return {"label": n.label, "kind": n.kind, "path": files[0] if n.file and files else None, "line": n.line,
            "story": node_story.get(nid)}


def names(im: ImpactModel, ids: Iterable[str], depot_of: dict[str, list[str] | None],
          node_story: dict[str, str]) -> dict[str, dict]:
    """Each known node's label, kind, depot path (None for a field, or when unknown), line and story."""
    return {nid: _name(im, nid, depot_of, node_story) for nid in sorted(set(ids)) if nid in im.nodes}


def neighbours(im: ImpactModel, nid: str, depot_of: dict[str, list[str] | None], node_story: dict[str, str], *,
               root: str, limit: int) -> dict | None:
    """A node's callers and callees (call and virtual edges): the most affected first, test code last; at most `limit`
    of each, with their totals. None for an unknown node."""
    if nid not in im.nodes:
        return None
    r = root.rstrip("/") + "/"
    changed = set(im.changed)
    score = {b.node: b.score for b in im.blast}

    def item(m: str) -> dict:
        f = im.nodes[m].file or ""
        test = is_test_path(f[len(r):] if f.startswith(r) else f) if f else False
        return {"id": m, **_name(im, m, depot_of, node_story), "changed": m in changed, "test": test}

    def side(ids: set[str]) -> dict:
        items = sorted((item(m) for m in ids if m in im.nodes),
                       key=lambda i: (i["test"], -score.get(i["id"], 0.0), i["label"], i["id"]))
        return {"total": len(items), "items": items[:limit]}

    calls = [e for e in im.edges if e.kind in ("call", "virtual")]
    return {"node": item(nid), "callers": side({e.src for e in calls if e.dst == nid and e.src != nid}),
            "callees": side({e.dst for e in calls if e.src == nid and e.dst != nid})}
