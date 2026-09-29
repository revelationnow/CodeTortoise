"""Storyboard: deterministic skeleton + optional grounded LLM narrative."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.detectors.base import SEVERITY_RANK, Finding, Hypothesis
from codetortoise.impact import ImpactModel
from codetortoise.layers import LayerModel
from codetortoise.llm.client import LlmClient, LlmError

SYSTEM = ("You are a senior C/C++ code reviewer. You are given facts extracted by static analysis "
          "for a set of changes. Use ONLY these facts. Refer to functions/fields by their node id (e.g. N3) "
          "and to findings by their id (e.g. F2). Every claim must list the ids it relies on in `cites`. "
          "Be concise and concrete; prefer what a reviewer must verify.")


class Cited(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)
    verified: bool = True


class Chapter(BaseModel):
    level: int | None
    name: str
    narrative: str
    cites: list[str] = Field(default_factory=list)
    verified: bool = True
    cross_layer_effects: list[Cited] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class Storyboard(BaseModel):
    summary: str
    risk: Literal["low", "medium", "high"]
    review_order: list[str] = Field(default_factory=list)
    verified: bool = True
    chapters: list[Chapter] = Field(default_factory=list)
    llm_used: bool = False
    llm_error: str | None = None


class _ExplainOut(BaseModel):
    explanation: str
    verify_steps: list[str] = Field(default_factory=list)
    hypotheses: list[Cited] = Field(default_factory=list)


class _ChapterOut(BaseModel):
    narrative: str
    cites: list[str] = Field(default_factory=list)
    cross_layer_effects: list[Cited] = Field(default_factory=list)


class _SummaryOut(BaseModel):
    summary: str
    risk: Literal["low", "medium", "high"]
    review_order: list[str] = Field(default_factory=list)
    cites: list[str] = Field(default_factory=list)


class _LayerName(BaseModel):
    level: int
    name: str
    description: str = ""


class _LayerNamesOut(BaseModel):
    layers: list[_LayerName]


def ground(items: list[Cited], known: set[str]) -> list[Cited]:
    """Keep only items citing at least one known id; drop unknown ids from cites."""
    out = []
    for it in items:
        cites = [c for c in it.cites if c in known]
        if cites:
            out.append(Cited(text=it.text, cites=cites, verified=True))
    return out


def budget(parts: list[str], max_tokens: int) -> str:
    """Concatenate parts (already in priority order) until ~max_tokens (chars/4)."""
    limit = max_tokens * 4
    out, used = [], 0
    for p in parts:
        if used + len(p) > limit:
            remaining = limit - used
            if remaining > 200:
                out.append(p[:remaining] + "\n...[truncated]")
            break
        out.append(p)
        used += len(p)
    return "\n\n".join(out)


def _risk(findings: list[Finding]) -> str:
    top = max((SEVERITY_RANK[f.severity] for f in findings if f.state != "dismissed"), default=0)
    return "high" if top >= 3 else "medium" if top == 2 else "low"


def _finding_levels(f: Finding, impact: ImpactModel, layers: LayerModel | None) -> set[int | None]:
    levels = {impact.nodes[n].layer for n in f.nodes if n in impact.nodes and impact.nodes[n].kind == "function"}
    if not levels and layers is not None:
        levels = {layers.level_of(e.file) for e in f.evidence if e.file}
    return levels or {None}


def skeleton(impact: ImpactModel, findings: list[Finding], layers: LayerModel | None) -> Storyboard:
    by_level: dict[int | None, Chapter] = {}

    def chapter(level: int | None) -> Chapter:
        if level not in by_level:
            layer = layers.layer(level) if layers is not None else None
            by_level[level] = Chapter(level=level, name=layer.name if layer else "Unlayered", narrative="")
        return by_level[level]

    for nid in impact.changed:
        chapter(impact.nodes[nid].layer).nodes.append(nid)
    for f in findings:
        for lv in _finding_levels(f, impact, layers):
            chapter(lv).findings.append(f.id)
    chapters = sorted(by_level.values(), key=lambda c: (c.level is None, c.level if c.level is not None else 0))
    for c in chapters:
        parts = [f"{impact.nodes[n].label} ({impact.nodes[n].status})" for n in c.nodes]
        c.narrative = (f"Changed: {', '.join(parts)}." if parts else "No functions changed in this layer.") + \
            (f" Findings: {', '.join(c.findings)}." if c.findings else "")
        c.cites = c.nodes + c.findings
    high = sum(1 for f in findings if f.severity == "high")
    summary = (f"{len(impact.changed)} function(s) changed across {len([c for c in chapters if c.nodes])} layer(s); "
               f"{len(findings)} finding(s), {high} high.")
    order = [n for c in chapters for n in c.nodes]
    return Storyboard(summary=summary, risk=_risk(findings), review_order=order, chapters=chapters)


def _node_line(impact: ImpactModel, nid: str) -> str:
    n = impact.nodes[nid]
    return f"{nid} {n.kind} {n.label} status={n.status} layer={n.layer} file={n.file}:{n.line}"


def _facts_for_nodes(impact: ImpactModel, nids: list[str]) -> str:
    lines = [_node_line(impact, n) for n in nids]
    ids = set(nids)
    for e in impact.edges:
        if e.src in ids or e.dst in ids:
            lines.append(f"{e.id}: {e.src} -{e.kind}/{e.status}/{e.confidence}-> {e.dst}")
    return "\n".join(lines[:400])


def _finding_text(f: Finding) -> str:
    ev = "\n".join(f"  - [{e.severity}] {e.text} ({e.file}:{e.line})" for e in f.evidence)
    return f"{f.id} [{f.severity}] {f.kind}: {f.title}\n{f.summary}\nnodes: {f.nodes}\nevidence:\n{ev}"


def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: LayerModel | None,
                     snippets: dict[str, str], llm: LlmClient | None, max_tokens: int = 64000) -> Storyboard:
    sb = skeleton(impact, findings, layers)
    if llm is None:
        return sb
    known = set(impact.nodes) | {f.id for f in findings}
    per_call = max(2000, max_tokens // 2)
    try:
        for f in findings:
            nodes = [n for n in f.nodes if n in impact.nodes]
            neighbours = sorted({e.src for e in impact.edges if e.dst in nodes} |
                                {e.dst for e in impact.edges if e.src in nodes})
            parts = ["FINDING:\n" + _finding_text(f), "GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes + neighbours)]
            parts += [f"CODE {n}:\n{snippets[n]}" for n in nodes + neighbours if n in snippets]
            out = llm.complete_json(SYSTEM, "Explain the risk of this finding, list concrete verification steps, "
                                    "and propose additional side-effect hypotheses (each citing ids).\n\n" +
                                    budget(parts, per_call), _ExplainOut)
            f.explanation = out.explanation
            f.verify_steps = out.verify_steps
            f.hypotheses = [Hypothesis(text=h.text, cites=h.cites) for h in ground(out.hypotheses, known)]
        for ch in sb.chapters:
            parts = [f"LAYER: {ch.name}",
                     "CHANGED NODES AND EDGES:\n" + _facts_for_nodes(impact, ch.nodes),
                     "FINDINGS:\n" + "\n\n".join(_finding_text(f) for f in findings if f.id in ch.findings)]
            parts += [f"CODE {n}:\n{snippets[n]}" for n in ch.nodes if n in snippets]
            out = llm.complete_json(SYSTEM, "Write the narrative for this architectural layer: what changed, why it "
                                    "matters, and effects on layers above/below (cross_layer_effects).\n\n" +
                                    budget(parts, per_call), _ChapterOut)
            ch.narrative = out.narrative
            ch.cites = [c for c in out.cites if c in known]
            ch.verified = bool(ch.cites)
            ch.cross_layer_effects = ground(out.cross_layer_effects, known)
        overview = [f"CHAPTER {c.name}: {c.narrative} (cites {c.cites})" for c in sb.chapters]
        overview += [_finding_text(f) for f in findings[:30]]
        out = llm.complete_json(SYSTEM, "Summarize the whole change for a reviewer in 3-6 sentences, give an overall "
                                "risk, and a review_order of node ids.\n\n" + budget(overview, per_call), _SummaryOut)
        sb.summary = out.summary
        sb.risk = out.risk
        order = [n for n in out.review_order if n in impact.nodes]
        sb.review_order = order or sb.review_order
        sb.verified = any(c in known for c in out.cites)
        sb.llm_used = True
    except LlmError as e:
        sb.llm_error = str(e)
    return sb


def name_layers(model: LayerModel, llm: LlmClient) -> LayerModel:
    listing = "\n".join(f"level {l.level}: modules {', '.join(l.modules[:40])}" for l in model.layers)
    out = llm.complete_json(
        "You name architectural layers of a C/C++ codebase. Level 0 is the lowest (no dependencies).",
        "Give each level a short name (1-3 words) and a one-sentence description.\n\n" + listing, _LayerNamesOut)
    names = {l.level: l for l in out.layers}
    for layer in model.layers:
        if layer.level in names:
            layer.name = f"L{layer.level}: {names[layer.level].name}"
            layer.description = names[layer.level].description
    return model
