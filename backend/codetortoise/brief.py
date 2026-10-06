"""A review's brief (spec 2026-10-05-two-tier-stories §7.2): what tier 1 worked out, for tier 2 to start from.

It holds the change overview, the pieces and their links, the plan grouping them into stories, and each finding's
verdict and prepared facts (keyed by `facts_prep.finding_key`, so renumbering findings never breaks it). A brief made
entirely by the strong model is reused by a later run of the same change (its cache key)."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.grouping import StoryPlan
from codetortoise.pieces import PieceSet


class BriefVerdict(BaseModel):
    verdict: Literal["hazard", "needs_review", "no_hazard"]
    reason: str
    cites: list[str] = Field(default_factory=list)


class Brief(BaseModel):
    key: str = ""                     # cache key: the change as tier 1 saw it, the rules version and the model
    model: str = ""                   # "" : no strong model
    complete: bool = False            # tier 1 formed every story (no chunk fell back to the rules): reusable
    overview: str = ""
    pieces: PieceSet = Field(default_factory=PieceSet)
    plan: StoryPlan = Field(default_factory=StoryPlan)
    verdicts: dict[str, BriefVerdict] = Field(default_factory=dict)    # finding key -> tier 1's verdict
    facts: dict[str, str] = Field(default_factory=dict)                # finding key -> its prepared facts
    reviewed: list[str] = Field(default_factory=list)                  # story keys whose risk pass ran


def cache_key(ps: PieceSet, model: str, rules_version: int, agree: int) -> str:
    """Hash of what tier 1 is shown (cards, links, overview), the rules' version and the model."""
    blob = json.dumps({"cards": [p.card for p in ps.pieces], "links": [lk.model_dump() for lk in ps.links],
                       "overview": ps.overview, "rules": rules_version, "model": model, "agree": agree}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()

