"""@tortoise (spec 2026-10-03 §5): answer a question in a comment thread, reading the code it needs.

Each round the model replies with JSON: read something (a function, its callers, a declaration, part of a file, or
where a name is used) or answer. Reads go through the review's change set, the workspace source (the same validated
single-file reads as /source) and the symbol index; nothing else. Every round is one ledger call, at most
`per_mention`; the last round must answer. The answer must cite what it relies on and keep the house style.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import Board
from codetortoise.llm.ledger import Refused
from codetortoise.llm.ondemand import context_for
from codetortoise.llm.storyboard import STYLE, AiContext, _facts_for_nodes, _finding_text, budget
from codetortoise.llm.style import MODES, check_style
from codetortoise.provenance import merge
from codetortoise.services import Services
from codetortoise.vcs.model import ChangeSet

AUTHOR = "tortoise"
MENTION = re.compile(r"(?<![\w@.])@tortoise\b", re.I)

SYSTEM = ("You are tortoise, a senior C/C++ code reviewer answering a question in a code review thread. Use only the "
          "code and facts you are given or have read. Each turn reply with one JSON object: either "
          '{"action": "read", "read": {...}, "why": "..."} to read more, or '
          '{"action": "answer", "text": "...", "cites": [...]} to answer. Reads: {"kind": "function", "name": N}, '
          '{"kind": "callers", "name": N}, {"kind": "declaration", "name": N}, '
          '{"kind": "file", "path": DEPOT_PATH, "from": A, "to": B} (at most 200 lines), {"kind": "search", "name": N}. '
          "Cite node ids (like N9) or depot paths you rely on. " + STYLE)


class _Read(BaseModel):
    kind: Literal["function", "callers", "declaration", "file", "search"]
    name: str = ""
    path: str = ""
    from_: int = Field(1, alias="from")
    to: int = 0

    model_config = {"populate_by_name": True}


class _Step(BaseModel):
    action: Literal["read", "answer"]
    read: _Read | None = None
    why: str = ""
    text: str = ""
    cites: list[str] = Field(default_factory=list)


def mentions(body: str) -> bool:
    return bool(MENTION.search(body or ""))


class _Reader:
    """The reads @tortoise may make, inside the review and the workspace. Each returns text and records the files."""

    def __init__(self, svc: Services, rid: int, ctx: AiContext, cs: ChangeSet):
        self.svc, self.rid, self.ctx, self.cs = svc, rid, ctx, cs
        self.files: set[str] = set()
        self.done: list[str] = []
        self.ids: set[str] = set()

    def text_of(self, depot: str | None = None, local: str | None = None) -> tuple[str, str] | None:
        """(depot, text) of a file: the change's new side for changed files, else the workspace's source."""
        for f in self.cs.files:
            if (depot and f.depot == depot) or (local and f.local == local):
                return f.depot, f.after
        if depot is None and local is not None:
            depot = self.svc.source.depots_for([local]).get(local) if hasattr(self.svc.source, "depots_for") else None
        if not depot or not depot.startswith("//"):
            return None
        try:
            sf = self.svc.source.read(depot)
        except Exception:  # not allowed, binary, too large, not in the workspace: no read
            return None
        return sf.depot, sf.text

    @staticmethod
    def lines(text: str, lo: int, hi: int) -> str:
        rows = text.splitlines()
        lo, hi = max(1, lo), min(len(rows), hi)
        return "\n".join(f"{n:5} {rows[n - 1]}" for n in range(lo, hi + 1))

    def function(self, name: str) -> str:
        im = self.ctx.impact
        hit = next((nid for nid, n in im.nodes.items() if n.kind == "function" and name in (n.label, n.key)), None)
        if hit:
            self.ids.add(hit)
            n = im.nodes[hit]
            if n.file:
                got = self.text_of(local=n.file)
                if got:
                    self.files.add(got[0])
            code = self.ctx.snippets.get(hit) or (
                self.lines(got[1], n.line or 1, (n.line or 1) + 40) if n.file and got else "")
            return f"{hit} {n.label}:\n" + _facts_for_nodes(im, [hit]) + "\n" + code
        defs = self.svc.index.defs(name)
        if not defs:
            return f"no function named {name}"
        d = defs[0]
        got = self.text_of(local=d.path)
        if not got:
            return f"{name} is defined in {d.path}, which can't be read"
        self.files.add(got[0])
        return f"{name} ({got[0]}:{d.line}):\n" + self.lines(got[1], d.line, d.line + 40)

    def callers(self, name: str) -> str:
        out = []
        for c in self.svc.index.callers_of(name)[:20]:
            got = self.text_of(local=c.path)
            if not got:
                continue
            self.files.add(got[0])
            out.append(f"{c.caller or '?'} ({got[0]}:{c.line}):\n" + self.lines(got[1], c.line - 3, c.line + 3))
        return "\n\n".join(out) or f"no callers of {name} in the symbol index"

    def declaration(self, name: str) -> str:
        im = self.ctx.impact
        field = next((n for n in im.nodes.values()
                      if n.kind == "field" and (n.label == name or n.label.endswith("::" + name))), None)
        if field is not None:
            from codetortoise.facts.model import Facts
            for fx in self.svc.store.get_blob(self.rid, "facts_after") or []:
                for a in Facts.model_validate(fx).fields:
                    if f"field:{a.field}" == field.key and a.record_file and a.decl_line:
                        got = self.text_of(local=a.record_file)
                        if got:
                            self.files.add(got[0])
                            return (f"{field.label} ({got[0]}:{a.decl_line}):\n"
                                    + self.lines(got[1], a.decl_line - 5, a.decl_line + 5))
        return self.function(name)

    def file(self, path: str, lo: int, hi: int) -> str:
        got = self.text_of(depot=path)
        if not got:
            return f"{path}: not allowed (only files in this change or this workspace, by depot path)"
        self.files.add(got[0])
        hi = min(hi or lo + 199, lo + 199)
        return f"{got[0]} lines {lo}-{hi}:\n" + self.lines(got[1], lo, hi)

    def search(self, name: str) -> str:
        idx = self.svc.index
        defs = [f"defined: {d.path}:{d.line}" for d in idx.defs(name)[:20]]
        calls = [f"called: {c.path}:{c.line} in {c.caller}" for c in idx.callers_of(name)[:20]]
        uses = [f"{'written' if m.is_write else 'read'}: {m.path}:{m.line} in {m.fn}" for m in idx.member_refs(name)[:10]]
        return "\n".join(defs + calls + uses) or f"{name} is not in the symbol index"

    def run(self, r: _Read) -> str:
        label = {"function": f"{r.name}", "callers": f"callers of {r.name}", "declaration": f"declaration of {r.name}",
                 "file": f"{r.path} {r.from_}–{r.to}", "search": f"uses of {r.name}"}[r.kind]
        text = (self.function(r.name) if r.kind == "function" else self.callers(r.name) if r.kind == "callers"
                else self.declaration(r.name) if r.kind == "declaration" else self.file(r.path, r.from_, r.to)
                if r.kind == "file" else self.search(r.name))
        if "not allowed" not in text:
            self.done.append(label)
        return text


def _anchor_context(svc: Services, rid: int, comment: dict, ctx: AiContext, board: Board, reader: _Reader) -> str:
    kind, a = comment["anchor_kind"], comment["anchor"]
    im = ctx.impact
    if kind == "line":
        path = a.get("path") or a.get("depot")
        line = int(a.get("line") or 1)
        got = reader.text_of(depot=path) if path else None
        parts = []
        if got:
            reader.files.add(got[0])
            parts.append(f"FILE {got[0]} around line {line}:\n" + reader.lines(got[1], line - 20, line + 20))
        node = next((n for n in board.nodes if n.path == path and n.range and n.range[0] <= line <= n.range[1]), None)
        if node and node.id in im.nodes:
            reader.ids.add(node.id)
            parts.append("FUNCTION:\n" + _facts_for_nodes(im, [node.id]) + "\n" + ctx.snippets.get(node.id, ""))
        return "\n\n".join(parts)
    if kind == "function":
        nid = next((i for i, n in im.nodes.items() if n.key == a.get("key")), None)
        return "FUNCTION:\n" + reader.function(im.nodes[nid].label) if nid else ""
    if kind == "finding":
        fs = [f for f in ctx.findings if f.kind == a.get("kind") and f.title == a.get("title")]
        out = []
        for f in fs:
            reader.ids.add(f.id)
            reader.files.update(f.files or [])
            out.append("FINDING:\n" + _finding_text(f) + "\n" + "\n".join(ctx.snippets.get(n, "") for n in f.nodes))
        return "\n\n".join(out)
    if kind == "chapter":
        nodes = [n.id for n in board.nodes if n.layer == a.get("level") and n.id in im.nodes]
        reader.ids.update(nodes)
        return "LAYER FUNCTIONS:\n" + _facts_for_nodes(im, nodes)
    flows = "\n".join(f"{f.id}: {f.title} — {f.what}" for f in board.flows)
    finds = "\n".join(f"{f.id} [{f.severity}] {f.title}" for f in ctx.findings)
    reader.ids.update(f.id for f in ctx.findings)
    return f"CHANGE: {board.about.intent}\nFLOWS:\n{flows}\nFINDINGS:\n{finds}"


def _fit(convo: list[str], max_tokens: int) -> str:
    """The prompt so far within ~max_tokens: the question, thread and context first, then the newest reads that fit."""
    head, reads, room = convo[:3], convo[3:], max_tokens * 4 - sum(len(p) for p in convo[:3])
    kept: list[str] = []
    for r in reversed(reads):
        if len(r) > room:
            break
        kept.insert(0, r)
        room -= len(r)
    return budget(head, max_tokens) + "".join("\n\n" + r for r in kept)


def _thread(svc: Services, rid: int, root_id: int, upto: int) -> str:
    rows = [c for c in svc.store.list_comments(rid) if (c["id"] == root_id or c["parent_id"] == root_id) and c["id"] <= upto]
    return "\n".join(f"{c['author']}: {c['body']}" for c in rows if not (c["ai_meta"] or {}).get("pending"))


def answer(svc: Services, rid: int, user: str, question: dict, reply_id: int) -> None:
    """Answer the question comment `question` in reply `reply_id`, as `user` (whose limits the rounds count against)."""
    cap = svc.cfg.llm.budget.per_mention
    meta = {"pending": True, "round": 0, "of": cap, "read": [], "files": [], "calls": 0, "error": None}
    svc.store.set_ai_reply(reply_id, "thinking…", meta)
    ctx, board, findings, cs = context_for(svc, rid)
    reader = _Reader(svc, rid, ctx, cs)
    root = question["parent_id"] or question["id"]
    known = set(ctx.impact.nodes) | {f.id for f in findings}
    convo = [f"QUESTION: {question['body']}", "THREAD SO FAR:\n" + _thread(svc, rid, root, question["id"]),
             "CONTEXT:\n" + _anchor_context(svc, rid, question, ctx, board, reader)]
    fixed = False
    try:
        for n in range(1, cap + 1):
            meta.update(round=n)
            svc.store.set_ai_reply(reply_id, "thinking…", meta)
            last = n == cap
            prompt = _fit(convo, ctx.per_call) + (
                "\n\nYou must answer now: reply with action \"answer\"." if last else "") + f"\n{MODES['explanation']}"
            step = svc.ledger.call(svc.llm, rid, user, "mention", str(reply_id),
                                   lambda llm, p=prompt: llm.complete_json(SYSTEM, p, _Step))
            meta["calls"] += 1
            if step.action == "read" and step.read is not None and not last:
                r = step.read
                what = f"{r.path} from {r.from_} " if r.kind == "file" else r.name
                convo.append(f"READ {r.kind} {what}->\n" + reader.run(r))
                continue
            text = step.text.strip()
            cited = {c for c in step.cites if c in known or c in reader.files or c in ctx.impact.nodes}
            problems = ([] if cited else ["it cites nothing you were given or read"]) + check_style(text, "explanation")
            if text and not problems:
                break
            if not fixed and not last:
                fixed = True
                convo.append(f"YOUR ANSWER: {text}\nIt was not accepted ({'; '.join(problems) or 'empty'}). Answer again: "
                             "cite the node ids or depot paths you rely on, and keep the house style.")
                continue
            raise ValueError("the answer failed the checks: " + "; ".join(problems or ["empty"]))
        else:
            raise ValueError("no answer within the rounds allowed")
    except Refused as e:
        _done(svc, reply_id, meta, reader, f"I couldn't answer: {e.reason}.", e.reason)
        return
    except Exception as e:  # the model failed: say so in the thread
        _done(svc, reply_id, meta, reader, f"I couldn't answer: {e}", str(e)[:300])
        return
    _done(svc, reply_id, meta, reader, text, None)


def _done(svc: Services, reply_id: int, meta: dict, reader: _Reader, body: str, error: str | None) -> None:
    files = merge(sorted(reader.files)) if reader.files else []
    meta.update(pending=False, read=reader.done, files=files, error=error)
    svc.store.set_ai_reply(reply_id, body, meta)
