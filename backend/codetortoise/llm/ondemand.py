"""On-demand AI (spec 2026-10-03 §4): explain one flow, finding or file when someone asks, once, for everyone.

Each explanation is one job (storyboard.Job) run through the ledger as the person who asked. Its context is rebuilt
from what the review stored; the result is stored with the review (the board, the findings, the file summaries).
"""
from __future__ import annotations

import difflib
import threading
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from codetortoise.board import Board
from codetortoise.detectors.base import Finding
from codetortoise.facts.model import Facts
from codetortoise.impact import ImpactModel
from codetortoise.llm.storyboard import AiContext, Job, _facts_for_nodes, budget, finding_job, flow_job, run_job
from codetortoise.llm.style import MODES, check_style
from codetortoise.provenance import merge, tag_board
from codetortoise.services import Services
from codetortoise.vcs.model import ChangeSet

KINDS = ("flow", "finding", "file")
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


class NotFound(LookupError):
    pass


class Unchecked(ValueError):
    """The AI answered, but its answer didn't cite the item's code or keep the house style; nothing is stored."""


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
    board = Board.model_validate(store.get_blob(rid, "board") or {"about": {"intent": ""}})
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
    """Run one explanation as `user` and store it. Raises NotFound, Refused (over a limit) or the LLM's error."""
    if svc.llm is None or svc.ledger is None:
        raise RuntimeError("no LLM configured")
    with _lock(rid):
        ctx, board, findings, cs = context_for(svc, rid)
        if kind == "flow":
            fl = next((f for f in board.flows if f.id == target), None)
            if fl is None:
                raise NotFound(f"flow {target} not found")
            trial = fl.model_copy(update={"what_source": "template"})
            run_job(svc.llm, flow_job(ctx, trial), svc.ledger, rid, user)
            if trial.what_source != "llm":
                raise Unchecked(UNCHECKED)
            board.flows[board.flows.index(fl)] = trial
            svc.store.put_blob(rid, "board", tag_board(board, {f.id: f.files for f in findings}))
        elif kind == "finding":
            f = next((f for f in findings if f.id == target), None)
            if f is None:
                raise NotFound(f"finding {target} not found")
            trial = f.model_copy(update={"explanation": None})
            run_job(svc.llm, finding_job(ctx, trial), svc.ledger, rid, user)
            if not trial.explanation:
                raise Unchecked(UNCHECKED)
            findings[findings.index(f)] = trial
            svc.store.put_findings(rid, findings)
        elif kind == "file":
            summaries, fresh = svc.store.get_blob(rid, "file_summaries") or {}, {}
            run_job(svc.llm, file_job(ctx, board, cs, target, fresh, user), svc.ledger, rid, user)
            if not fresh.get(target, {}).get("summary"):
                raise Unchecked(UNCHECKED)
            svc.store.put_blob(rid, "file_summaries", {**summaries, **fresh})
        else:
            raise NotFound(f"unknown kind {kind}")


def check_target(svc: Services, rid: int, kind: str, target: str) -> None:
    """Fail fast (NotFound) before queueing an explanation of something that doesn't exist."""
    if kind == "flow":
        board = svc.store.get_blob(rid, "board") or {}
        if not any(f.get("id") == target for f in board.get("flows", [])):
            raise NotFound(f"flow {target} not found")
    elif kind == "finding":
        if not any(f.id == target for f in svc.store.list_findings(rid)):
            raise NotFound(f"finding {target} not found")
    elif kind == "file":
        cs = svc.store.get_blob(rid, "changeset") or {}
        if not any(f.get("depot") == target for f in cs.get("files", [])):
            raise NotFound(f"{target} is not in this change")
    else:
        raise NotFound(f"unknown kind {kind}")
