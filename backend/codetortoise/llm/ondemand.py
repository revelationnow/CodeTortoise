"""On-demand AI (spec 2026-10-03 §4): explain one flow, finding, file or story when someone asks, once, for everyone.

Each explanation is one job (storyboard.Job) run through the ledger as the person who asked. Its context is rebuilt
from what the review stored; the result is stored with the review (the board, the findings, the file summaries).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import threading
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from codetortoise import boardstore
from codetortoise.board import Board
from codetortoise.detectors.base import Finding
from codetortoise.facts.model import Facts
from codetortoise.impact import ImpactModel
from codetortoise.llm.brief_context import brief_context
from codetortoise.llm.storyboard import (
    AiContext,
    Job,
    _facts_for_nodes,
    briefed_job,
    budget,
    finding_job,
    flow_job,
    run_job,
    story_job,
)
from codetortoise.llm.style import MODES, check_style
from codetortoise.provenance import merge, tag_board
from codetortoise.services import Services
from codetortoise.vcs.model import ChangeSet

KINDS = ("flow", "finding", "file", "story")
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


class NotFound(LookupError):
    pass


class Unchecked(ValueError):
    """The AI answered, but its answer didn't cite the item's code or keep the house style; nothing is stored."""


class Changed(ValueError):
    """The review changed (a re-run) while the AI was answering; the answer is about the old change and isn't stored."""


CHANGED = "the review changed while the AI was answering; nothing was changed. Ask again"
UNCHECKED = "the AI's answer didn't pass the checks (citations or house style); nothing was changed. Try again"


class _FileOut(BaseModel):
    summary: str
    check: list[str] = Field(default_factory=list)
    cites: list[str] = Field(default_factory=list)


def _lock(rid: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(rid, threading.Lock())


def context_for(svc: Services, rid: int) -> tuple[AiContext, Board, list[Finding], ChangeSet]:
    """The AI context of a review, from what its run stored."""
    from codetortoise.pipeline import collect_snippets
    store = svc.store
    impact = ImpactModel.model_validate(store.get_blob(rid, "impact") or {})
    cs = ChangeSet.model_validate(store.get_blob(rid, "changeset") or {"cls": [], "files": []})
    after = [Facts.model_validate(f) for f in store.get_blob(rid, "facts_after") or []]
    findings = store.list_findings(rid)
    board = boardstore.combined(store, rid) or Board(about={"intent": ""})    # a split review: all its boards
    snippets = collect_snippets(impact, cs, after) if impact.nodes else {}
    ctx = AiContext(impact, findings, snippets, svc.cfg.llm.max_context_tokens, store.get_blob(rid, "node_files"))
    return ctx, board, findings, cs


def file_job(ctx: AiContext, board: Board, cs: ChangeSet, path: str, summaries: dict, by: str) -> Job:
    """New: what changed in one file and what to check, from its diff, its functions' facts and its notes."""
    change = next((f for f in cs.files if f.depot == path), None)
    if change is None:
        raise NotFound(f"{path} is not in this change")
    nodes = [nid for nid, n in ctx.impact.nodes.items() if n.file == change.local and n.kind == "function"]
    diff = "\n".join(difflib.unified_diff(change.before.splitlines(), change.after.splitlines(), "before", "after",
                                          n=3, lineterm=""))
    notes = "\n".join(f"line {i.line} [{i.severity}] {i.title}: {i.text}" for i in board.impacts if i.path == path)
    parts = [f"FILE {path} ({change.action})\nDIFF:\n{diff}", "FUNCTIONS:\n" + _facts_for_nodes(ctx.impact, nodes),
             "NOTES:\n" + (notes or "none")]

    def apply(out: _FileOut) -> int:
        grounded = bool(set(out.cites) & (set(nodes) | {path}))   # it must cite the file or one of its functions
        ok = grounded and bool(out.summary.strip()) and not check_style(out.summary, "explanation")
        steps = [c for c in out.check if not check_style(c, "how-to")]
        summaries[path] = {"summary": out.summary if ok else "", "check": steps,
                           "files": merge([path], *(ctx.node_files.get(n) for n in nodes)) if ctx.node_files is not None
                           else None, "by": by, "at": datetime.now(UTC).isoformat(timespec="seconds")}
        return (0 if ok else 1) + len(out.check) - len(steps)
    prompt = ("Summarise this file for a reviewer: what changed and why it matters (summary), and what to check "
              "(check: a few steps). Cite the node ids you rely on, or the file's depot path.\n"
              f"Summary: {MODES['explanation']} Check: {MODES['how-to']}\n\n" + budget(parts, ctx.per_call))
    return Job("file", path, prompt, _FileOut, apply)


def explain(svc: Services, rid: int, user: str, kind: str, target: str) -> None:
    """Run one explanation as `user` and store it. Raises NotFound, Refused (over a limit), Unchecked, Changed or the
    LLM's error. The AI call runs without the review's lock (other explanations go on meanwhile); the result is
    stored under it, onto the review as it is then, and only if the change is still the one the AI saw."""
    if svc.llm is None or svc.ledger is None:
        raise RuntimeError("no LLM configured")
    ctx, board, findings, cs = context_for(svc, rid)
    seen = _fingerprint(svc, rid)
    if kind == "flow":
        fl = next((f for f in board.flows if f.id == target), None)
        if fl is None:
            raise NotFound(f"flow {target} not found")
        trial = fl.model_copy(update={"what_source": "template"})
        run_job(svc.llm, briefed_job(ctx, brief_context(svc.store, rid, flow=target), lambda: flow_job(ctx, trial)),
                svc.ledger, rid, user)
        if trial.what_source != "llm":
            raise Unchecked(UNCHECKED)
        with _lock(rid):
            _same(svc, rid, seen)
            held = boardstore.with_flow(svc.store, rid, target)          # the board holding the flow, as it is now
            now = next((f for f in held[1].flows if f.id == target and f.path == fl.path), None) if held else None
            if now is None:
                raise Changed(CHANGED)
            now.what, now.what_source, now.what_files, now.title = trial.what, "llm", trial.what_files, trial.title
            findings = svc.store.list_findings(rid)
            boardstore.put(svc.store, rid, held[0], tag_board(held[1], {f.id: f.files for f in findings}))
    elif kind == "finding":
        f = next((f for f in findings if f.id == target), None)
        if f is None:
            raise NotFound(f"finding {target} not found")
        trial = f.model_copy(update={"explanation": None})
        run_job(svc.llm, briefed_job(ctx, brief_context(svc.store, rid, finding=f), lambda: finding_job(ctx, trial)),
                svc.ledger, rid, user)
        if not trial.explanation:
            raise Unchecked(UNCHECKED)
        with _lock(rid):
            _same(svc, rid, seen)
            findings = svc.store.list_findings(rid)                     # as they are now (states may have changed)
            now = next((x for x in findings if x.id == target and x.kind == f.kind and x.title == f.title), None)
            if now is None:
                raise Changed(CHANGED)
            for k in ("explanation", "verify_steps", "hypotheses", "explain_files", "verdict", "verdict_reason", "severity"):
                setattr(now, k, getattr(trial, k))
            svc.store.put_findings(rid, findings)
            if f.severity != now.severity:            # a verdict on a side effect: its flows and stories follow
                boardstore.recolor(svc.store, rid, now, findings)
    elif kind == "story":
        d = boardstore.story(svc.store, rid, target)
        if d is None:
            raise NotFound(f"story {target} not found")
        if d.story.source == "tier1":
            raise NotFound(f"story {target} was written by the strong model; ask about it in a thread instead")
        trial = d.model_copy(deep=True)
        trial.story.text_source, trial.story.text_files = "template", None
        run_job(svc.llm, briefed_job(ctx, brief_context(svc.store, rid, story=target), lambda: story_job(ctx, trial)),
                svc.ledger, rid, user)
        if trial.story.text_source != "llm":
            raise Unchecked(UNCHECKED)
        with _lock(rid):
            _same(svc, rid, seen)
            now = boardstore.story(svc.store, rid, target)                # as stored now
            if now is None or now.story.nodes != d.story.nodes or now.story.flows != d.story.flows:
                raise Changed(CHANGED)
            now.story.title, now.story.summary, now.story.text_source = trial.story.title, trial.story.summary, "llm"
            now.story.text_files = trial.story.text_files
            boardstore.put_story(svc.store, rid, now)
    elif kind == "file":
        fresh: dict = {}
        change = next((c for c in cs.files if c.depot == target), None)
        nodes = [nid for nid, n in ctx.impact.nodes.items() if change and n.file == change.local and n.kind == "function"]
        run_job(svc.llm, briefed_job(ctx, brief_context(svc.store, rid, nodes=nodes),
                                     lambda: file_job(ctx, board, cs, target, fresh, user)), svc.ledger, rid, user)
        if not fresh.get(target, {}).get("summary"):
            raise Unchecked(UNCHECKED)
        with _lock(rid):
            _same(svc, rid, seen)
            summaries = svc.store.get_blob(rid, "file_summaries") or {}
            svc.store.put_blob(rid, "file_summaries", {**summaries, **fresh})
    else:
        raise NotFound(f"unknown kind {kind}")


def _fingerprint(svc: Services, rid: int) -> str:
    """What the AI was shown: the review's change set (a re-run on a new shelve changes it)."""
    return hashlib.sha256(json.dumps(svc.store.get_blob(rid, "changeset"), sort_keys=True).encode()).hexdigest()


def _same(svc: Services, rid: int, seen: str) -> None:
    if _fingerprint(svc, rid) != seen:
        raise Changed(CHANGED)


def check_target(svc: Services, rid: int, kind: str, target: str) -> None:
    """Fail fast (NotFound) before queueing an explanation of something that doesn't exist."""
    if kind == "flow":
        if boardstore.with_flow(svc.store, rid, target) is None:
            raise NotFound(f"flow {target} not found")
    elif kind == "finding":
        if not any(f.id == target for f in svc.store.list_findings(rid)):
            raise NotFound(f"finding {target} not found")
    elif kind == "story":
        d = boardstore.story(svc.store, rid, target)
        if d is None:
            raise NotFound(f"story {target} not found")
        if d.story.source == "tier1":          # spec 2026-10-05-two-tier-stories §8: tier 2 never retells them
            raise NotFound(f"story {target} was written by the strong model; ask about it in a thread instead")
    elif kind == "file":
        cs = svc.store.get_blob(rid, "changeset") or {}
        if not any(f.get("depot") == target for f in cs.get("files", [])):
            raise NotFound(f"{target} is not in this change")
    else:
        raise NotFound(f"unknown kind {kind}")
