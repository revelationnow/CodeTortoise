"""Storyboard: deterministic skeleton + optional grounded LLM narrative."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import Board, Flow
from codetortoise.detectors.base import SEVERITY_RANK, Finding, Hypothesis
from codetortoise.impact import ImpactModel
from codetortoise.layers import LayerModel
from codetortoise.llm.client import LlmClient, LlmError
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.style import MODES, STYLE, check_style
from codetortoise.provenance import merge

SYSTEM = ("You are a senior C/C++ code reviewer. You are given facts extracted by static analysis "
          "for a set of changes. Use ONLY these facts. Refer to functions/fields by their node id (e.g. N3) "
          "and to findings by their id (e.g. F2). Every claim must list the ids it relies on in `cites`. "
          "Be concise and concrete; prefer what a reviewer must verify. " + STYLE)


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
    style_dropped: int = 0           # LLM outputs dropped for breaking the house style (llm/style.py)


class _ExplainOut(BaseModel):
    explanation: str
    verify_steps: list[str] = Field(default_factory=list)
    hypotheses: list[Cited] = Field(default_factory=list)


class _SummaryOut(BaseModel):
    summary: str
    risk: Literal["low", "medium", "high"]
    review_order: list[str] = Field(default_factory=list)
    cites: list[str] = Field(default_factory=list)


class _FlowOut(BaseModel):
    what: str
    title: str = ""
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


def _flow_prompt(fl: Flow, impact: ImpactModel, findings: list[Finding], snippets: dict[str, str], per_call: int) -> str:
    steps = " → ".join(f"{n} {impact.nodes[n].label}" for n in fl.path if n in impact.nodes)
    parts = [f"FLOW {fl.id} ({fl.tag}): {steps}\nlands on: {fl.lands}\ndraft: {fl.what}\neffect: {fl.effect}\n"
             f"check: {fl.check}",
             "FINDINGS:\n" + "\n\n".join(_finding_text(f) for f in findings if f.id in fl.findings),
             "GRAPH FACTS:\n" + _facts_for_nodes(impact, [n for n in fl.path if n in impact.nodes])]
    parts += [f"CODE {n}:\n{snippets[n]}" for n in fl.path if n in snippets]
    return ("Describe this call flow for a reviewer in 2-3 sentences: how the entry reaches the change and what the "
            "change does to the function where the effect lands, plus a headline of at most 8 words (title). "
            f"Draft headline: {fl.title}. Cite the node and finding ids you rely on.\n"
            f"Description: {MODES['explanation']} Title: {MODES['headline']}\n\n" +
            budget(parts, per_call))


@dataclass
class AiContext:
    """What every AI job needs: the analysis, code snippets, the prompt budget and the files behind each node."""
    impact: ImpactModel
    findings: list[Finding]
    snippets: dict[str, str]
    max_tokens: int = 64000
    node_files: dict[str, list[str] | None] | None = None

    @property
    def per_call(self) -> int:
        return max(2000, self.max_tokens // 2)

    @property
    def known(self) -> set[str]:
        return set(self.impact.nodes) | {f.id for f in self.findings}

    def prompt_files(self, nodes: list[str], finding_ids: list[str]) -> list[str] | None:
        """The files behind a prompt about these nodes and findings (spec 2026-10-01 §14.3); None if any is unknown."""
        if self.node_files is None:
            return None
        tags = {f.id: f.files for f in self.findings}
        return merge(*(self.node_files.get(n) for n in nodes), *(tags.get(i) for i in finding_ids))


@dataclass
class Job:
    """One AI call: what it is for (ledger purpose and target), its prompt and reply schema, and how the reply is
    applied. `apply` returns how many outputs it dropped for breaking the house style."""
    purpose: str
    target: str
    prompt: str
    schema: type[BaseModel]
    apply: Callable[[BaseModel], int]


def _styled(text: str, mode: str) -> bool:
    return not check_style(text, mode)


def finding_job(ctx: AiContext, f: Finding) -> Job:
    impact = ctx.impact
    nodes = [n for n in f.nodes if n in impact.nodes]
    neighbours = sorted({e.src for e in impact.edges if e.dst in nodes} | {e.dst for e in impact.edges if e.src in nodes})
    parts = ["FINDING:\n" + _finding_text(f), "GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes + neighbours)]
    parts += [f"CODE {n}:\n{ctx.snippets[n]}" for n in nodes + neighbours if n in ctx.snippets]

    def apply(out: _ExplainOut) -> int:
        dropped = 0
        if _styled(out.explanation, "explanation"):
            f.explanation = out.explanation
        else:
            f.explanation, dropped = None, dropped + 1
        f.explain_files = ctx.prompt_files(nodes + neighbours, [f.id])
        steps = [st for st in out.verify_steps if _styled(st, "how-to")]
        hyps = [h for h in ground(out.hypotheses, ctx.known) if _styled(h.text, "explanation")]
        dropped += len(out.verify_steps) - len(steps) + len(ground(out.hypotheses, ctx.known)) - len(hyps)
        f.verify_steps, f.hypotheses = steps, [Hypothesis(text=h.text, cites=h.cites) for h in hyps]
        return dropped
    prompt = ("Explain the risk of this finding, list concrete verification steps, and propose additional side-effect "
              "hypotheses (each citing ids).\n"
              f"Explanation and hypotheses: {MODES['explanation']} Verification steps: {MODES['how-to']}\n\n"
              + budget(parts, ctx.per_call))
    return Job("finding", f.id, prompt, _ExplainOut, apply)


def flow_job(ctx: AiContext, fl: Flow) -> Job:
    def apply(out: _FlowOut) -> int:
        # grounded: keep the LLM text only if it cites a node on this flow or one of its findings
        if not (out.what.strip() and set(out.cites) & (set(fl.path) | set(fl.findings))):
            return 0
        if not _styled(out.what, "explanation"):
            return 1
        fl.what, fl.what_source, fl.what_files = out.what.strip(), "llm", ctx.prompt_files(fl.path, fl.findings)
        if 0 < len(out.title.strip()) <= 80:
            if not _styled(out.title.strip(), "headline"):
                return 1
            fl.title = out.title.strip()
        return 0
    return Job("flow", fl.id, _flow_prompt(fl, ctx.impact, ctx.findings, ctx.snippets, ctx.per_call), _FlowOut, apply)


def summary_job(ctx: AiContext, sb: Storyboard, board: Board | None) -> Job:
    overview = [f"CHAPTER {c.name}: {c.narrative} (cites {c.cites})" for c in sb.chapters]
    overview += [_finding_text(f) for f in ctx.findings[:30]]

    def apply(out: _SummaryOut) -> int:
        ok = bool(out.summary.strip()) and _styled(out.summary, "explanation")
        if ok:
            sb.summary = out.summary
        order_ = ["low", "medium", "high"]       # the LLM may raise the risk, never lower it below the findings
        sb.risk = max(sb.risk, out.risk, key=order_.index)
        sb.review_order = [n for n in out.review_order if n in ctx.impact.nodes] or sb.review_order
        sb.verified = any(c in ctx.known for c in out.cites)
        sb.llm_used = True
        if board is not None and ok:
            board.about.intent, board.about.intent_source = out.summary.strip(), "llm"
            board.about.intent_files = merge(*(ctx.prompt_files(c.nodes, c.findings) for c in sb.chapters),
                                             ctx.prompt_files([], [f.id for f in ctx.findings[:30]]))
        return 0 if ok or not out.summary.strip() else 1
    prompt = ("Summarize the whole change for a reviewer in 3-6 sentences, give an overall risk, and a review_order of "
              f"node ids.\n{MODES['explanation']}\n\n" + budget(overview, ctx.per_call))
    return Job("summary", "", prompt, _SummaryOut, apply)


def run_job(llm: LlmClient, job: Job, ledger: Ledger | None = None, rid: int | None = None,
            user: str | None = None) -> int:
    """Make the job's one call (through the ledger when given) and apply the reply. Returns outputs dropped for
    style. Raises Refused over a limit, LlmError (or anything the client raises) on failure."""
    def ask(client: LlmClient):
        return client.complete_json(SYSTEM, job.prompt, job.schema)
    out = ledger.call(llm, rid, user, job.purpose, job.target, ask) if ledger is not None and rid is not None else ask(llm)
    return job.apply(out)


def build_storyboard(impact: ImpactModel, findings: list[Finding], layers: LayerModel | None,
                     snippets: dict[str, str], llm: LlmClient | None, max_tokens: int = 64000, *,
                     board: Board | None = None, concurrency: int = 1, upfront_flows: int = 3,
                     node_files: dict[str, list[str] | None] | None = None, ledger: Ledger | None = None,
                     rid: int | None = None) -> Storyboard:
    """The deterministic storyboard, then (with an LLM) the up-front pass of spec 2026-10-03 §3: narratives for the
    first `upfront_flows` flows (concurrently), then the change summary. Everything else is explained on demand.

    Every call goes through `ledger` when given (as the pipeline). A refused or failed call stops the pass and leaves
    the deterministic text for whatever wasn't written; `llm_error` says why."""
    sb = skeleton(impact, findings, layers)
    if llm is None:
        return sb
    ctx = AiContext(impact, findings, snippets, max_tokens, node_files)
    jobs = [flow_job(ctx, fl) for fl in (board.flows[:upfront_flows] if board else [])]
    pool = ThreadPoolExecutor(max(1, concurrency), thread_name_prefix="tortoise-llm")
    try:
        for dropped in pool.map(lambda j: run_job(llm, j, ledger, rid), jobs):
            sb.style_dropped += dropped
        sb.style_dropped += run_job(llm, summary_job(ctx, sb, board), ledger, rid)
    except Refused as e:
        sb.llm_error = f"AI budget: {e.reason}"
    except Exception as e:  # any LLM-side failure leaves the deterministic text intact
        sb.llm_error = str(e) if isinstance(e, LlmError) else f"{type(e).__name__}: {e}"
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
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
