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
    findings.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.kind, f.title))
    for i, f in enumerate(findings):
        f.id = f"F{i + 1}"
    return findings
