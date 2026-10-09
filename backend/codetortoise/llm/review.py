"""Tier 1 reviews each story's risks (spec 2026-10-05-two-tier-stories §5).

One call per story with findings: the story's title and purpose, its pieces' cards, and for each finding its prepared
facts and a fixed question. The model may read more (the tools of §4.1). Each answer is hazard, needs_review or
no_hazard with a reason, and must cite node ids or file:line it was shown; one citing nothing shown is rejected and the
finding stays as the detectors left it. A finding on two stories is reviewed with the first.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import _Ctx
from codetortoise.brief import BriefVerdict
from codetortoise.config import StrongLlmConfig
from codetortoise.detectors.base import Finding, renumber
from codetortoise.facts_prep import finding_key
from codetortoise.grouping import PlannedStory, StoryPlan
from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.stories import Tools, ask, pieces_of
from codetortoise.llm.storyboard import _styled
from codetortoise.llm.style import MODES, STYLE
from codetortoise.llm.tiers import TiersFailed, done_text, tried_note, try_tiers
from codetortoise.pieces import PieceSet
from codetortoise.tidy import tidy

SEVERITY = {"hazard": "high", "needs_review": "medium", "no_hazard": "info"}

QUESTIONS = {
    "signature": "Do the updated sites match the new signature; is any site left behind?",
    "returns": "Does any caller mishandle the new value?",
    "field": "Does any reader's assumption break; is this a hazard or a normal side effect?",
    "behaviour": "Does any caller rely on the old behaviour; should a reviewer confirm it?",
    "header": "Do all users still compile and mean the same thing?",
}

RULES = """Review the risks of one story of a change. For each finding below, check its facts (prepared by code: trust \
them, and read more when they are not enough) and answer its question with one verdict:
- hazard: a clear problem; the reason says what breaks and where;
- needs_review: behaviour changed and a person should confirm it is intended;
- no_hazard: nothing breaks; the reason says why.
Cite the node ids (N12) or file:line you rely on, exactly as shown. A verdict citing nothing you were shown is \
discarded."""

SYSTEM = ("You are a senior C/C++ reviewer judging the risks of one story of a change. Use only what you are given or "
          "have read. Each turn reply with one JSON object: either "
          '{"action": "read", "tool": T, "arg": A} to read more, where T is "piece_code" (A: a piece id), "diff" (A: a '
          'file path as the cards show it), "neighbours" (A: a function name) or "cl" (A: a CL number); or '
          '{"action": "answer", "verdicts": [{"finding", "verdict", "reason", "cites"}]}. ' + STYLE)


class _Verdict(BaseModel):
    finding: str
    verdict: Literal["hazard", "needs_review", "no_hazard"]
    reason: str = ""
    cites: list[str] = Field(default_factory=list)


class _ReviewStep(BaseModel):
    action: Literal["read", "answer"]
    tool: str = ""
    arg: str | int = ""
    verdicts: list[_Verdict] = Field(default_factory=list)


@dataclass
class Reviewed:
    verdicts: dict[str, BriefVerdict] = field(default_factory=dict)    # finding key -> verdict
    reviewed: list[str] = field(default_factory=list)                  # story keys whose pass ran (or had no findings)
    notes: list[str] = field(default_factory=list)


def question(f: Finding) -> str:
    if f.kind == "contract" and "signature changed" in f.title:
        return QUESTIONS["signature"]
    if f.kind == "contract" and "new return value" in f.title:
        return QUESTIONS["returns"]
    if f.kind == "field_mutation" or f.side_effect:
        return QUESTIONS["field"]
    if f.kind == "header_fanout":
        return QUESTIONS["header"]
    return QUESTIONS["behaviour"]


def review_parts(s: PlannedStory, ps: PieceSet, mine: list[Finding], facts: dict[str, str]) -> list[str]:
    cards = "\n\n".join(p.card for p in ps.pieces if p.id in s.pieces)
    rows = [f"{f.id} [{f.severity}] {f.kind}: {tidy(f.title)}\n{tidy(f.summary)}\n"
            f"FACTS:\n{facts.get(finding_key(f), 'no prepared facts')}"
            f"\nQUESTION: {question(f)}" for f in mine]
    return [RULES + "\n\nCHANGE OVERVIEW:\n" + ps.overview,
            f"STORY {s.key}: {s.title or '(untitled)'}" + (f"\nPurpose: {s.purpose}" if s.purpose else "") + "\nPIECES:\n" + cards,
            "FINDINGS:\n" + "\n\n".join(rows)]


def _shown(cite: str, text: str) -> bool:
    """The cite is a node, finding or piece id or a file:line, and appears in what the model was shown, or is a line
    inside a range it was shown (file:lo-hi)."""
    cite = cite.strip()
    if not re.fullmatch(r"[NFP]\d+|\S+:\d+", cite):
        return False
    if re.search(rf"(?<![\w/.]){re.escape(cite)}(?![\w])", text):
        return True
    m = re.fullmatch(r"(.+):(\d+)", cite)
    return bool(m) and any(int(lo) <= int(m[2]) <= int(hi) for lo, hi in re.findall(rf"{re.escape(m[1])}:(\d+)-(\d+)", text))


def review_stories(strong: LlmClient, ledger: Ledger | None, rid: int | None, plan: StoryPlan, ps: PieceSet, x: _Ctx,
                   cfg: StrongLlmConfig, findings: list[Finding], facts: dict[str, str],
                   skip: set[str] | None = None, weak: LlmClient | None = None) -> Reviewed:
    """Tier 1's verdicts on the findings of every story not in `skip`. A story the strong model fails is tried fresh,
    then on the weak model; the budget running out, or a call failing on every model (spec 2026-10-08-llm-robustness
    §6), leaves the remaining findings as the detectors left them; the notes say so."""
    tools, out, taken = Tools(x, ps), Reviewed(), set()
    refused = gone = False
    for s in plan.stories:
        mine = [f for f in findings if f.id not in taken and set(pieces_of(f, ps)) & set(s.pieces)]
        taken |= {f.id for f in mine}
        if s.key in (skip or set()) or not mine:
            out.reviewed.append(s.key)
            continue
        if refused:
            out.notes.append(f"story {s.key}: AI budget: the tier-1 budget ran out; its findings stay as the detectors left them")
            continue
        if gone and weak is None:
            out.notes.append(f"story {s.key}: the strong model is unreachable; its findings stay as the detectors left them")
            continue
        seen: list[str] = []
        parts = review_parts(s, ps, mine, facts)

        def fn(llm, parts=parts, seen=seen):
            return ask(llm, parts, tools, cfg.rounds, int(cfg.context_tokens * 4 * 0.9), SYSTEM, _ReviewStep,
                       f"\nReasons: {MODES['explanation']}", seen)
        try:
            t = try_tiers(ledger, rid, "review", f"story {s.key}", fn, strong, weak, skip_strong=gone)
        except Refused as e:
            refused = True
            out.notes.append(f"story {s.key}: AI budget: {e.reason}; its findings stay as the detectors left them")
            continue
        except TiersFailed as e:  # this story's findings stay as the detectors left them; the others go on
            gone = gone or e.strong_unreachable
            out.notes.append(tried_note(f"story {s.key}", e.failures, "its findings stay as the detectors left them"))
            continue
        gone = gone or t.strong_unreachable
        step = t.value
        if t.tier != "strong":
            out.notes.append(tried_note(f"story {s.key}", t.failures, done_text(t, "judged its findings")))
        if t.tier != "weak":          # a story the weak model judged is asked of the strong model again next run
            out.reviewed.append(s.key)
        by_id, shown = {f.id: f for f in mine}, "\n".join(seen)
        for v in step.verdicts:
            f = by_id.get(v.finding)
            if f is None or not v.reason.strip():
                continue
            if not _styled(v.reason, "explanation"):
                out.notes.append(f"story {s.key}: {f.id}'s verdict broke the house style; the finding stays as the "
                                 "detectors left it")
                continue
            cites = [c.strip() for c in v.cites if _shown(c, shown)]
            if not cites:
                out.notes.append(f"story {s.key}: {f.id}'s verdict cites nothing it was shown; the finding stays as the "
                                 "detectors left it")
                continue
            out.verdicts[finding_key(f)] = BriefVerdict(verdict=v.verdict, reason=v.reason.strip(), cites=cites)
    return out


def apply_verdicts(findings: list[Finding], verdicts: dict[str, BriefVerdict]) -> int:
    """Record tier 1's verdicts on the findings (severity follows), renumber them by severity; how many got one."""
    n = 0
    for f in findings:
        v = verdicts.get(finding_key(f))
        if v is None:
            continue
        f.verdict, f.verdict_reason, f.verdict_cites, f.verdict_source = v.verdict, v.reason, list(v.cites), "tier1"
        f.severity = SEVERITY[v.verdict]
        n += 1
    renumber(findings)
    return n
