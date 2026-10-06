"""How stable are tier 1's stories? (spec 2026-10-05-two-tier-stories §4.6)

`codetortoise stories-check <review> --runs N` runs the stories stage N times on the review's stored change, without
the cache, and prints for each pair of pieces how often they shared a story, and the agreement score: the share of
piece pairs every run agreed on (together in every run, or apart in every run). It changes nothing stored and its calls
are not charged to the review.
"""
from __future__ import annotations

import itertools
from collections.abc import Callable

from codetortoise.board import BoardContext, analyse
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import Facts
from codetortoise.grouping import StoryPlan
from codetortoise.impact import ImpactModel
from codetortoise.layers import LayerModel
from codetortoise.llm.stories import form_stories
from codetortoise.paths import canon
from codetortoise.pieces import PieceSet
from codetortoise.services import Services
from codetortoise.vcs.model import ChangeSet


def _home(plan: StoryPlan) -> dict[str, str]:
    """Each piece's story; an unsorted piece shares a story with nothing."""
    return {pl.piece: (pl.piece if s.unsorted else s.key) for s in plan.stories for pl in s.placements}


def pair_counts(plans: list[StoryPlan], ids: list[str]) -> dict[tuple[str, str], int]:
    """(piece, piece) -> how many runs put them in one story; pairs never together are left out."""
    homes = [_home(p) for p in plans]
    out = {}
    for a, b in itertools.combinations(ids, 2):
        n = sum(1 for h in homes if a in h and h.get(a) == h.get(b))
        if n:
            out[(a, b)] = n
    return out


def agreement(plans: list[StoryPlan], ids: list[str]) -> tuple[int, int]:
    """(pairs every run agreed on, all pairs)."""
    counts = pair_counts(plans, ids)
    pairs = list(itertools.combinations(ids, 2))
    return sum(1 for pr in pairs if counts.get(pr, 0) in (0, len(plans))), len(pairs)


def stored_context(svc: Services, rid: int) -> tuple[BoardContext, PieceSet]:
    """The review's change as its last run stored it, and its pieces."""
    s = svc.store
    ctx = BoardContext(ChangeSet.model_validate(s.get_blob(rid, "changeset")), DiffMap.model_validate(s.get_blob(rid, "diffmap")),
                       [Facts.model_validate(f) for f in s.get_blob(rid, "facts_before") or []],
                       [Facts.model_validate(f) for f in s.get_blob(rid, "facts_after") or []],
                       ImpactModel.model_validate(s.get_blob(rid, "impact")), s.list_findings(rid),
                       LayerModel.model_validate(s.get_blob(rid, "layers")) if s.get_blob(rid, "layers") else None,
                       svc.cfg.analysis, lambda paths: {}, root=canon(str(svc.cfg.workspace.root)))
    return ctx, PieceSet.model_validate(s.get_blob(rid, "pieces"))


def stories_check(svc: Services, rid: int, runs: int, out: Callable[[str], None] = print) -> int:
    strong = svc.cfg.llm.strong
    if svc.strong is None or strong is None:
        raise ValueError("no strong model configured (llm.strong)")
    if not svc.store.get_blob(rid, "pieces"):
        raise ValueError(f"review {rid} has no pieces: run it first")
    ctx, ps = stored_context(svc, rid)
    x = analyse(ctx).x
    plans = [form_stories(svc.strong, None, None, ps, x, strong, ctx.findings) for _ in range(max(1, runs))]
    ids = [p.id for p in ps.pieces]
    out(f"review {rid}: {len(plans)} runs of the stories stage by {strong.model}, {len(ids)} pieces")
    for i, p in enumerate(plans, 1):
        for note in p.notes:
            out(f"run {i}: {note}")
    out("pairs that shared a story (runs together / runs):")
    for (a, b), n in sorted(pair_counts(plans, ids).items(), key=lambda kv: (kv[1], kv[0])):
        out(f"  {a} {b}  {n}/{len(plans)}")
    agreed, total = agreement(plans, ids)
    out(f"agreement: {agreed / total if total else 1:.2f} ({agreed} of {total} piece pairs agreed in every run)")
    return 0
