"""Finding model and detector registry."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.config import AnalysisConfig
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import Facts
from codetortoise.impact import ImpactModel

Severity = Literal["info", "low", "medium", "high"]
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}


class Evidence(BaseModel):
    text: str
    file: str | None = None
    line: int | None = None
    severity: Severity = "info"
    nodes: list[str] | None = None   # for evidence without a file: the graph nodes its text names (None = undeclared)


class Hypothesis(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)
    verified: bool = True


class Finding(BaseModel):
    id: str = ""
    kind: str
    severity: Severity
    title: str
    nodes: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    summary: str
    explanation: str | None = None
    verify_steps: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    state: Literal["open", "ack", "dismissed"] = "open"
    files: list[str] | None = None          # depot paths behind the finding (spec §14.3); None = unknown
    explain_files: list[str] | None = None  # files behind the LLM explanation, verify steps and hypotheses
    side_effect: bool = False               # a new field write: neutral until the AI judges it
    verdict: Literal["hazard", "no_hazard"] | None = None   # the AI's judgement of a side effect (None: not assessed)
    verdict_reason: str | None = None


@dataclass
class DetectorContext:
    before: list[Facts]
    after: list[Facts]
    dm: DiffMap
    impact: ImpactModel
    cfg: AnalysisConfig


Detector = Callable[[DetectorContext], list[Finding]]


def max_severity(items: list[Evidence], floor: Severity = "info") -> Severity:
    best = floor
    for e in items:
        if SEVERITY_RANK[e.severity] > SEVERITY_RANK[best]:
            best = e.severity
    return best


def run_detectors(ctx: DetectorContext, detectors: list[Detector] | None = None) -> list[Finding]:
    if detectors is None:
        from codetortoise.detectors.contract import detect_contract
        from codetortoise.detectors.field_mutation import detect_field_mutation
        from codetortoise.detectors.header_fanout import detect_header_fanout
        detectors = [detect_contract, detect_field_mutation, detect_header_fanout]
    findings: list[Finding] = []
    for d in detectors:
        findings.extend(d(ctx))
    return renumber(findings)


def renumber(findings: list[Finding]) -> list[Finding]:
    """Sort by severity (then kind and title) and number F1, F2, … in that order, in place."""
    findings.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.kind, f.title))
    for i, f in enumerate(findings):
        f.id = f"F{i + 1}"
    return findings
