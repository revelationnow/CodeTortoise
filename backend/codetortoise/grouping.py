"""Which pieces form which story (spec 2026-10-05-two-tier-stories §4.3, §6): the plan the strong model writes, or the
rules' plan without it. `stories.build_stories` turns a plan into the review's stories."""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.pieces import PieceSet

Reason = Literal["starts_purpose", "same_feature", "caller_of_new_code", "same_fix", "same_refactor", "shared_code",
                 "declaration_used", "split_too_big"]
REASONS: tuple[str, ...] = Reason.__args__                     # what the strong model may give
RULE_REASONS = ("linked", "tests", "repeated", "declaration_used", "starts_purpose")   # what the rules give


class Placement(BaseModel):
    piece: str
    reason: str                       # a Reason (tier 1), a rule's reason, or (unsorted) why it could not be placed
    evidence: list[str] = Field(default_factory=list)       # piece ids and CL numbers ("CL412") it relied on
    quote: list[str] = Field(default_factory=list)          # a cross-CL join without a link: one quote per CL


class PlannedStory(BaseModel):
    key: str
    title: str = ""                   # "" : the rules' title
    purpose: str = ""
    check: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)        # other stories' keys
    placements: list[Placement] = Field(default_factory=list)
    source: Literal["tier1", "rules"] = "rules"
    unsorted: bool = False            # pieces no story could take: a person places them

    @property
    def pieces(self) -> list[str]:
        return [p.piece for p in self.placements]


class StoryPlan(BaseModel):
    stories: list[PlannedStory] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)          # why part of it fell back to the rules


def rules_plan(ps: PieceSet, only: list[str] | None = None, prefix: str = "r") -> list[PlannedStory]:
    """§6: pieces join when a `call` link of at least 2 or a `field` link joins them, within one target and one CL;
    a declaration piece joins the group using its changes most; tests and repeated edits group per target (and
    substitution). `only` limits it to some pieces (a chunk tier 1 could not do)."""
    want = set(only) if only is not None else {p.id for p in ps.pieces}
    pieces = [p for p in ps.pieces if p.id in want]
    by_id = {p.id: p for p in pieces}
    parent = {p.id: p.id for p in pieces}
    rank = {p.id: i for i, p in enumerate(ps.pieces)}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    why: dict[str, tuple[str, list[str]]] = {}
    code = {"new", "edits", "single"}
    for lk in ps.links:
        a, b = by_id.get(lk.a), by_id.get(lk.b)
        if a is None or b is None or a.kind not in code or b.kind not in code:
            continue
        if a.targets != b.targets or a.cl != b.cl:
            continue
        if (lk.type == "call" and lk.count >= 2) or lk.type == "field":
            ra, rb = find(a.id), find(b.id)
            if ra != rb:
                lo, hi = sorted((ra, rb), key=rank.get)
                parent[hi] = lo
                why.setdefault(b.id if rank[b.id] > rank[a.id] else a.id,
                               ("linked", [a.id if rank[b.id] > rank[a.id] else b.id]))
    for p in pieces:
        if p.kind == "tests":
            parent[p.id] = next(q.id for q in pieces if q.kind == "tests" and q.targets == p.targets)
            why[p.id] = ("tests", [])
        elif p.kind == "repeated":
            parent[p.id] = next(q.id for q in pieces if q.kind == "repeated" and q.sub == p.sub and q.targets == p.targets)
            why[p.id] = ("repeated", [])
    groups: dict[str, list[str]] = defaultdict(list)
    for p in pieces:
        if p.kind != "declarations":
            groups[find(p.id)].append(p.id)
    for d in (p for p in pieces if p.kind == "declarations"):
        uses: dict[str, int] = defaultdict(int)
        for lk in ps.links_of(d.id):
            other = lk.b if lk.a == d.id else lk.a
            if lk.type == "uses" and other in by_id and by_id[other].kind in code:
                uses[find(other)] += lk.count
        if uses:
            into = max(uses, key=lambda g: (uses[g], -rank[g]))
            groups[into].append(d.id)
            user = max((o for o in groups[into] if o in by_id and by_id[o].kind in code),
                       key=lambda o: (sum(lk.count for lk in ps.links_of(d.id) if lk.type == "uses" and o in (lk.a, lk.b)),
                                      -rank[o]))
            why[d.id] = ("declaration_used", [user])
        else:
            groups[d.id].append(d.id)
    out = []
    for i, (_, ids) in enumerate(sorted(groups.items(), key=lambda kv: rank[kv[1][0]])):
        ids = sorted(ids, key=rank.get)
        places = []
        for j, pid in enumerate(ids):
            reason, ev = why.get(pid, ("starts_purpose", []))
            places.append(Placement(piece=pid, reason="starts_purpose" if j == 0 else reason, evidence=[] if j == 0 else ev))
        out.append(PlannedStory(key=f"{prefix}{i + 1}", placements=places))
    return out
