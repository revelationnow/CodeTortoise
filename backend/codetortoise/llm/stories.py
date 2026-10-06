"""Tier 1 forms the stories (spec 2026-10-05-two-tier-stories §4).

The strong model gets fixed rules, the change overview, a chunk's piece cards, the links among them and the findings
tied to them, and may read more (a piece's code, a file's diff, a function's neighbours, a CL) in rounds that make
one AI call. Code checks every placement on its own; a failed one goes to the Unsorted story with the failure as its
reason. A change too large for one prompt (60% of the context) is cut into chunks: one target's pieces, split by CL,
then top directory; several chunks get a merge pass. `agree: 2` runs each chunk twice and lets a third run decide the
pieces they disagree on.
"""
from __future__ import annotations

import difflib
import json
import posixpath
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import _Ctx
from codetortoise.config import StrongLlmConfig
from codetortoise.detectors.base import Finding
from codetortoise.grouping import REASONS, Placement, PlannedStory, StoryPlan, rules_plan
from codetortoise.llm.client import LlmClient, LlmUnreachable
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import _styled, _titled
from codetortoise.llm.style import MODES, STYLE
from codetortoise.pieces import Piece, PieceSet

STORY_RULES_VERSION = 2               # bump with every change to RULES or the prompts' wording
CHUNK_SHARE = 0.6                     # a chunk's prompt stays within this share of the context
JOINING = ("call", "field", "sub", "uses")   # links that let a piece of another CL join a story
QUOTE_MIN = 8                         # a quote shorter than this proves nothing

RULES = """Form the stories of this change for its reviewers. Follow these steps in order.
1. Split the pieces by target. Different targets are different stories. A shared piece goes with the story that uses it \
most (most links); other targets' stories that touch it name that story under "related".
2. Within each target, find the purposes: what each CL description says it does, and what each new-code piece adds.
3. Place every piece in the purpose it serves. New code goes with the edits that call it. A declaration piece goes with \
the story that uses its changes most.
4. Join pieces from different CLs only when a link joins them, or when both CL descriptions state the same purpose: then \
put one quote from each CL description, exactly as written, in "quote".
5. A story with more than 12 pieces or 40 changed functions must be split along its weakest links into purposes.
6. Give each story a title (at most 8 words: what changed and who is affected), a purpose (one sentence), what a \
reviewer should check (at most 3 steps), open questions (at most 3), and related stories by key.
7. Never place a piece twice. A piece you cannot place goes to "unsorted" with a reason.
Each placement has a reason: starts_purpose (the piece that defines the story), same_feature, caller_of_new_code, \
same_fix, same_refactor, shared_code (a shared piece in one target's story), declaration_used, split_too_big; and its \
evidence: the piece ids (P3) and CLs (CL412) it relies on."""

SYSTEM = ("You are a senior C/C++ reviewer forming the stories of a change for other reviewers. Use only what you are "
          "given or have read. Each turn reply with one JSON object: either "
          '{"action": "read", "tool": T, "arg": A} to read more, where T is "piece_code" (A: a piece id), "diff" (A: a '
          'file path as the cards show it), "neighbours" (A: a function name) or "cl" (A: a CL number); or '
          '{"action": "answer", "stories": [{"key", "title", "purpose", "check", "questions", "related", "pieces": '
          '[{"id", "reason", "evidence", "quote"}]}], "unsorted": [{"id", "reason"}]}. ' + STYLE)

MERGE = ("These stories were formed in separate parts of one change. Name related stories across the parts, and merge "
         "two stories only when they have the same targets and you can show they serve the same purpose. Reply with "
         '{"related": [{"a", "b"}], "merge": [{"a", "b", "reason"}]}; a merge moves story b into story a.')


class _Placed(BaseModel):
    id: str
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    quote: list[str] = Field(default_factory=list)


class _Story(BaseModel):
    key: str
    title: str = ""
    purpose: str = ""
    check: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    pieces: list[_Placed] = Field(default_factory=list)


class _Unplaced(BaseModel):
    id: str
    reason: str = ""


class _Step(BaseModel):
    action: Literal["read", "answer"]
    tool: str = ""
    arg: str | int = ""
    stories: list[_Story] = Field(default_factory=list)
    unsorted: list[_Unplaced] = Field(default_factory=list)


class _Pair(BaseModel):
    a: str
    b: str
    reason: str = ""


class _MergeOut(BaseModel):
    related: list[_Pair] = Field(default_factory=list)
    merge: list[_Pair] = Field(default_factory=list)


@dataclass
class Got:
    """A chunk's checked answer: its stories and the pieces it could not place."""
    stories: list[PlannedStory] = field(default_factory=list)
    unsorted: list[Placement] = field(default_factory=list)


# ------------------------------------------------------------------ tools
class Tools:
    """What the strong model may read: a piece's code, a file's diff, a function's neighbours, a CL."""

    def __init__(self, x: _Ctx, ps: PieceSet):
        self.x, self.ps = x, ps

    def _rel(self, path: str) -> str:
        root = self.x.c.root.rstrip("/") + "/"
        return path[len(root):] if self.x.c.root and path.startswith(root) else path

    def _fn(self, nid: str) -> str:
        x = self.x
        n = x.im.nodes[nid]
        out = [f"{n.label} ({nid}):"]
        for side, fns in (("before", x.fb), ("after", x.fa)):
            fn = fns.get(n.key)
            fc = x.texts.get(fn.file) if fn else None
            if fn is None or fc is None:
                out.append(f"  {side}: (none)")
                continue
            rows = (fc.before if side == "before" else fc.after).splitlines()
            lo, hi = max(1, fn.start_line - 3), min(len(rows), fn.end_line + 3)
            code = "\n".join(f"{i:5} {rows[i - 1]}" for i in range(lo, hi + 1))
            out.append(f"  {side} ({self._rel(fn.file)}:{lo}-{hi}):\n{code}")
        return "\n".join(out)

    def piece_code(self, pid: str) -> str:
        p = self.ps.piece(pid.strip())
        if p is None:
            return f"no piece {pid}"
        if p.kind == "declarations":
            return "\n".join(self.diff(f) for f in p.files)
        return "\n\n".join(self._fn(n) for n in p.nodes)[:8000]

    def diff(self, path: str) -> str:
        path = path.strip()
        fc = next((f for f in self.x.c.cs.files if path in (f.local, f.depot, self._rel(f.local))), None)
        if fc is None:
            return f"{path} is not in this change"
        text = "\n".join(difflib.unified_diff(fc.before.splitlines(), fc.after.splitlines(), "before", "after", n=3,
                                              lineterm=""))
        return f"DIFF {self._rel(fc.local)}:\n" + (text[:8000] or "(no line changes)")

    def neighbours(self, name: str) -> str:
        x = self.x
        nid = next((i for i, n in x.im.nodes.items() if n.kind == "function" and n.label == name.strip()), None)
        if nid is None:
            return f"no function named {name}"

        def tag(m: str) -> str:
            return f"{x.label(m)} ({m}{', changed' if m in x.changed else ''})"
        return (f"{x.label(nid)} ({nid}):\n  callers: " + (", ".join(tag(m) for m in sorted(x.callers.get(nid, ()))) or "none")
                + "\n  callees: " + (", ".join(tag(m) for m in sorted(x.callees.get(nid, ()))) or "none"))

    def cl(self, n: str | int) -> str:
        raw = str(n).strip().upper().removeprefix("CL").strip()
        num = int(raw) if raw.isdigit() else None
        meta = next((m for m in self.x.c.cs.cls if m.cl == num), None)
        if meta is None:
            return f"no CL {n} in this change"
        files = [f.depot for f in self.x.c.cs.files if any(p.cl == num for p in f.per_cl)]
        return (f"CL {num} ({meta.status}" + (f", {meta.user}" if meta.user else "") + f"):\n{meta.description}\nfiles: "
                + ", ".join(files))

    def run(self, tool: str, arg: str | int) -> str:
        fn = {"piece_code": self.piece_code, "diff": self.diff, "neighbours": self.neighbours, "cl": self.cl}.get(tool)
        return fn(arg if tool == "cl" else str(arg)) if fn else f"no tool {tool}"


# ------------------------------------------------------------------ prompts and chunks
def _chunk_target(p: Piece, ps: PieceSet) -> str:
    """A piece's chunk: its target; a shared piece goes with the target it has most links to."""
    if not p.shared:
        return p.targets[0]
    weight: dict[str, int] = defaultdict(int)
    for lk in ps.links_of(p.id):
        other = ps.piece(lk.b if lk.a == p.id else lk.a)
        if other is not None and not other.shared and other.targets[0] in p.targets:
            weight[other.targets[0]] += lk.count
    return max(p.targets, key=lambda t: (weight[t], -p.targets.index(t)))


def pieces_of(f: Finding, ps: PieceSet) -> list[str]:
    """The pieces a finding is about: those holding its nodes, or the declaration pieces of its evidence's files."""
    return [p.id for p in ps.pieces if set(f.nodes) & set(p.nodes) or (
        p.kind == "declarations" and any(e.file in p.files for e in f.evidence))]


def _findings_of(ids: list[str], ps: PieceSet, findings: list[Finding]) -> list[str]:
    out = []
    for f in findings:
        mine = [pid for pid in pieces_of(f, ps) if pid in ids]
        if mine:
            out.append(f"{f.id} [{f.severity}] {f.kind}: {f.title} — {', '.join(mine)}")
    return out


def chunk_parts(ids: list[str], ps: PieceSet, findings: list[Finding]) -> list[str]:
    """The prompt of one chunk: rules and overview, its cards and links, its findings."""
    keep = set(ids)
    cards = "\n\n".join(p.card for p in ps.pieces if p.id in keep)
    links = "\n".join(f"{lk.a} {lk.b} {lk.type} ×{lk.count}" for lk in ps.links if lk.a in keep and lk.b in keep)
    return [RULES + "\n\nCHANGE OVERVIEW:\n" + ps.overview,
            "PIECES:\n" + cards + "\n\nLINKS (piece, piece, type, count):\n" + (links or "none"),
            "FINDINGS:\n" + ("\n".join(_findings_of(ids, ps, findings)) or "none")]


def chunks(ps: PieceSet, findings: list[Finding], limit: int) -> list[list[str]]:
    """Piece ids per chunk: the whole change when it fits in `limit` chars, else one target's pieces, split by CL, then
    by top directory, then evenly, while past the limit."""
    def size(ids: list[str]) -> int:
        return sum(len(p) for p in chunk_parts(ids, ps, findings))

    root = posixpath.commonpath([f for q in ps.pieces for f in q.files] or ["/"])

    def top(p: Piece) -> str:
        rel = posixpath.relpath(p.files[0], root) if p.files else ""
        return rel.split("/")[0] if "/" in rel else ""

    def split(ids: list[str], keys: list[Callable[[Piece], object]]) -> list[list[str]]:
        if size(ids) <= limit or len(ids) == 1:
            return [ids]
        if not keys:
            half = len(ids) // 2
            return split(ids[:half], []) + split(ids[half:], [])
        groups: dict[object, list[str]] = defaultdict(list)
        for pid in ids:
            groups[keys[0](ps.piece(pid))].append(pid)
        if len(groups) == 1:
            return split(ids, keys[1:])
        return [c for _, g in sorted(groups.items(), key=lambda kv: str(kv[0])) for c in split(g, keys[1:])]
    every = [p.id for p in ps.pieces]
    if size(every) <= limit:                                 # fits in one prompt: one chunk, no merge pass
        return [every]
    by_target: dict[str, list[str]] = defaultdict(list)
    for p in ps.pieces:
        by_target[_chunk_target(p, ps)].append(p.id)
    return [c for t in sorted(by_target) for c in split(by_target[t], [lambda p: p.cl or 0, top])]


def _fit(convo: list[str], limit: int) -> str:
    """The fixed parts, then the newest reads that fit within `limit` chars."""
    head = "\n\n".join(convo[:3])
    room, kept = limit - len(head), []
    for r in reversed(convo[3:]):
        if len(r) + 2 > room:
            break
        kept.insert(0, r)
        room -= len(r) + 2
    return head + "".join("\n\n" + r for r in kept)


ASK_STYLE = f"\nPurposes and questions: {MODES['explanation']} Checks: {MODES['how-to']} Titles: {MODES['headline']}"


def ask(strong: LlmClient, parts: list[str], tools: Tools, rounds: int, limit: int, system: str = SYSTEM,
        schema: type[BaseModel] = _Step, tail: str = ASK_STYLE, seen: list[str] | None = None):
    """One chunk's (or story's) rounds (one AI call): reads until the model answers; the last round must answer. `seen`
    receives every prompt sent, so answers can be checked against what the model was shown."""
    convo = list(parts)
    # the system prompt and the schema the client appends to it share the context with the prompt
    room = limit - len(system) - len(json.dumps(schema.model_json_schema())) - len(tail) - 120
    for n in range(1, max(1, rounds) + 1):
        last = n == max(1, rounds)
        prompt = _fit(convo, room) + ('\n\nYou must answer now: reply with action "answer".' if last else "") + tail
        if seen is not None:
            seen.append(prompt)
        step = strong.complete_json(system, prompt, schema)
        if step.action == "answer":
            return step
        if last:
            break
        convo.append(f"READ {step.tool} {step.arg} ->\n" + tools.run(step.tool, step.arg))
    raise ValueError("no answer within the rounds allowed")


# ------------------------------------------------------------------ checks
def _linked(ps: PieceSet, a: str, members: list[str]) -> bool:
    """A call, field, substitution or declaration link joins piece `a` to one of `members`."""
    return any(lk.type in JOINING and (lk.b if lk.a == a else lk.a) in members for lk in ps.links_of(a))


def _quoted(quotes: list[str], one: str, other: str) -> bool:
    """One quote found verbatim in each of the two CLs' descriptions."""
    good = [q.strip() for q in quotes if len(q.strip()) >= QUOTE_MIN]
    return any(q in one for q in good) and any(q in other for q in good)


def place(ps: PieceSet, cls: dict[int, str], members: list[str], first: Piece, p: Piece, pl: Placement,
          anchor: Piece | None = None) -> str | None:
    """Why a placement fails the checks (spec §4.4), or None when it stands. The story's target is `anchor`'s (its first
    single-target piece), its CL `first`'s."""
    anchor = anchor or first
    known = {q.id for q in ps.pieces}
    bad = [e for e in pl.evidence if e not in known and not (e.startswith("CL") and e[2:].isdigit() and int(e[2:]) in cls)]
    if bad:
        return f"unknown evidence {', '.join(bad)}"
    if pl.reason not in REASONS:
        return f"unknown reason {pl.reason!r}"
    if p.targets != anchor.targets and not (pl.reason == "shared_code" and p.shared and set(anchor.targets) <= set(p.targets)):
        return f"target {', '.join(p.targets)} differs from the story's ({', '.join(anchor.targets)})"
    if p.cl != first.cl and not _linked(ps, p.id, members) and not _quoted(pl.quote, cls.get(first.cl or 0, ""),
                                                                           cls.get(p.cl or 0, "")):
        return f"CL {p.cl} differs from the story's (CL {first.cl}) with no link or quote"
    return None


def _evidence(e: str) -> str:
    """A CL however the model writes it ("CL 412", "cl412") as the cards name it: CL412."""
    m = re.fullmatch(r"\s*[Cc][Ll]\s*(\d+)\s*", e)
    return f"CL{m[1]}" if m else e.strip()


def check_answer(step: _Step, chunk: list[str], ps: PieceSet, cls: dict[int, str], prefix: str = "") -> Got:
    """Each placement checked on its own; failures, unplaced pieces and the model's own unsorted go to unsorted."""
    allowed, placed, got = set(chunk), set(), Got()
    keys = {s.key for s in step.stories}
    used: set[str] = set()
    for s in step.stories:
        ps_: list[Placement] = []
        first: Piece | None = None
        valid = [p for p in (ps.piece(r.id) for r in s.pieces if r.id in allowed) if p is not None]
        # the story's target is its first single-target piece's: a shared header listed first does not decide it
        anchor = next((p for p in valid if not p.shared), valid[0] if valid else None)
        for raw in s.pieces:
            p = ps.piece(raw.id) if raw.id in allowed else None
            if p is None or raw.id in placed:
                continue                                         # unknown, another chunk's, or placed twice: dropped
            pl = Placement(piece=raw.id, reason=raw.reason, evidence=[_evidence(e) for e in raw.evidence],
                           quote=list(raw.quote))
            why = place(ps, cls, [q.piece for q in ps_], first or p, p, pl, anchor)
            placed.add(raw.id)
            if why is None:
                ps_.append(pl)
                first = first or p
            else:
                got.unsorted.append(Placement(piece=raw.id, reason=why))
        if not ps_:
            continue
        key, n = s.key, 1
        while key in used:                                       # the model gave two stories one key
            n += 1
            key = f"{s.key}_{n}"
        used.add(key)
        title = s.title.strip()
        got.stories.append(PlannedStory(
            key=prefix + key, source="tier1", placements=ps_,
            title=title if 0 < len(title) <= 80 and _titled(title) else "",
            purpose=s.purpose.strip() if s.purpose.strip() and _styled(s.purpose, "explanation") else "",
            check=[c.strip() for c in s.check if c.strip() and _styled(c, "how-to")][:3],
            questions=[q.strip() for q in s.questions if q.strip() and _styled(q, "explanation")][:3],
            related=[prefix + r for r in s.related if r in keys and r != key]))
    for u in step.unsorted:
        if u.id in allowed and u.id not in placed:
            placed.add(u.id)
            got.unsorted.append(Placement(piece=u.id, reason=u.reason.strip() or "the model could not place it"))
    for pid in chunk:
        if pid not in placed:
            got.unsorted.append(Placement(piece=pid, reason="the model did not place it"))
    return got


# ------------------------------------------------------------------ agreement and merging
def _groups(got: Got) -> dict[str, frozenset[str]]:
    out = {pl.piece: frozenset(s.pieces) for s in got.stories for pl in s.placements}
    out.update({pl.piece: frozenset([pl.piece]) for pl in got.unsorted})
    return out


def agree(first: Got, second: Got, third: Callable[[], Got], ps: PieceSet, cls: dict[int, str]) -> Got:
    """Two pieces share a story when both runs put them together; a piece the runs disagree on goes where a third run
    puts it (into the agreed story sharing most pieces with its story there). Titles and notes come from the first."""
    g1, g2 = _groups(first), _groups(second)
    sure = {p for p in g1 if g1[p] == g2.get(p)}
    out = Got(stories=[s.model_copy(update={"placements": [pl for pl in s.placements if pl.piece in sure]}, deep=True)
                       for s in first.stories],
              unsorted=[pl for pl in first.unsorted if pl.piece in sure])
    unsure = sorted((p for p in g1 if p not in sure), key=lambda p: [q.id for q in ps.pieces].index(p))
    if unsure:
        g3 = third()
        for pid in unsure:
            mine = next((s for s in g3.stories if pid in s.pieces), None)
            if mine is None:
                out.unsorted.append(next((pl for pl in g3.unsorted if pl.piece == pid),
                                         Placement(piece=pid, reason="the runs disagreed")))
                continue
            pl = next(pl for pl in mine.placements if pl.piece == pid)
            best = max(out.stories, key=lambda s: len(set(s.pieces) & set(mine.pieces)), default=None)
            if best is not None and set(best.pieces) & set(mine.pieces):
                first_p = ps.piece(best.placements[0].piece) if best.placements else ps.piece(pid)
                why = place(ps, cls, best.pieces, first_p, ps.piece(pid), pl)
                if why is None:
                    best.placements.append(pl)
                else:
                    out.unsorted.append(Placement(piece=pid, reason=why))
            else:
                new = next((s for s in out.stories if s.key == "x" + mine.key), None)
                if new is None:
                    new = mine.model_copy(update={"key": "x" + mine.key, "placements": []}, deep=True)
                    out.stories.append(new)
                new.placements.append(pl)
    out.stories = [s for s in out.stories if s.placements]
    return out


def _targets(s: PlannedStory, ps: PieceSet) -> list[str]:
    return ps.piece(s.placements[0].piece).targets if s.placements else []


def merge_pass(strong: LlmClient, stories: list[PlannedStory], ps: PieceSet, cls: dict[int, str]) -> Got:
    """Across chunks: related stories, and merges of same-target stories checked as placements are."""
    lines = []
    for s in stories:
        cl_set = sorted({ps.piece(p).cl or 0 for p in s.pieces})
        lines.append(f"{s.key} | {s.title or '(untitled)'} | {s.purpose or '-'} | targets {', '.join(_targets(s, ps))} | "
                     f"CLs {', '.join(map(str, cl_set))} | pieces {', '.join(s.pieces)}")
    out = strong.complete_json(SYSTEM, MERGE + "\n\nSTORIES (key | title | purpose | targets | CLs | pieces):\n"
                               + "\n".join(lines), _MergeOut)
    by_key = {s.key: s for s in stories}
    got = Got(stories=list(stories))
    for m in out.merge:
        a, b = by_key.get(m.a), by_key.get(m.b)
        if a is None or b is None or a is b or a not in got.stories or b not in got.stories or _targets(a, ps) != _targets(b, ps):
            continue
        first = ps.piece(a.placements[0].piece)
        for pl in b.placements:
            why = place(ps, cls, a.pieces, first, ps.piece(pl.piece), pl)
            if why is None:
                a.placements.append(pl)
            else:
                got.unsorted.append(Placement(piece=pl.piece, reason=f"merge: {why}"))
        got.stories.remove(b)
        for s in got.stories:
            s.related = list(dict.fromkeys(a.key if r == b.key else r for r in s.related if r != s.key))
    for r in out.related:
        a, b = by_key.get(r.a), by_key.get(r.b)
        if a in got.stories and b in got.stories and a is not b:
            a.related = list(dict.fromkeys(a.related + [b.key]))
            b.related = list(dict.fromkeys(b.related + [a.key]))
    return got


# ------------------------------------------------------------------ the stage
def form_stories(strong: LlmClient, ledger: Ledger | None, rid: int | None, ps: PieceSet, x: _Ctx,
                 cfg: StrongLlmConfig, findings: list[Finding]) -> StoryPlan:
    """Tier 1's plan for the whole change. A chunk that fails (or is refused by the budget) is grouped by the rules,
    and the plan's notes say so."""
    limit = int(cfg.context_tokens * 4 * CHUNK_SHARE)
    cls = {m.cl: m.description for m in x.c.cs.cls}
    tools = Tools(x, ps)
    groups = chunks(ps, findings, limit)
    stories: list[PlannedStory] = []
    unsorted: list[Placement] = []
    notes: list[str] = []
    refused = unreachable = fell_back = False

    def call(purpose: str, target: str, fn):
        return ledger.call(strong, rid, None, purpose, target, fn) if ledger is not None else fn(strong)
    for i, ids in enumerate(groups, 1):
        prefix = f"c{i}" if len(groups) > 1 else ""
        parts = chunk_parts(ids, ps, findings)

        def run(n: int = 1, ids=ids, parts=parts, prefix=prefix, i=i) -> Got:
            step = call("stories", f"chunk {i}" + (f" run {n}" if n > 1 else ""),
                        lambda llm: ask(llm, parts, tools, cfg.rounds, int(cfg.context_tokens * 4 * 0.9)))
            return check_answer(step, ids, ps, cls, prefix)
        if unreachable:
            fell_back = True
            notes.append(f"chunk {i}: the strong model is unreachable; the rules grouped its pieces")
            stories += rules_plan(ps, ids, prefix=f"r{i}_")
            continue
        try:
            if refused:
                raise Refused("the tier-1 budget ran out")
            got = run(1)
            if cfg.agree >= 2:
                first = got
                try:
                    got = agree(first, run(2), lambda: run(3), ps, cls)
                except Refused as e:          # the budget stopped the agreement runs: the first run's checked answer stands
                    refused = fell_back = True
                    notes.append(f"chunk {i}: AI budget: {e.reason}; its first run's answer stands")
                    got = first
        except Refused as e:
            refused = fell_back = True
            notes.append(f"chunk {i}: AI budget: {e.reason}; the rules grouped its pieces")
            got = Got(stories=rules_plan(ps, ids, prefix=f"r{i}_"))
        except Exception as e:  # a chunk that fails falls back to the rules; the others stand
            unreachable = isinstance(e, LlmUnreachable)          # no point waiting on it again this run
            fell_back = True
            notes.append(f"chunk {i}: {type(e).__name__}: {e}"[:300] + "; the rules grouped its pieces")
            got = Got(stories=rules_plan(ps, ids, prefix=f"r{i}_"))
        stories += got.stories
        unsorted += got.unsorted
    tier1 = [s for s in stories if s.source == "tier1"]
    if len(groups) > 1 and len(tier1) > 1 and not refused and not unreachable:
        try:
            merged = call("stories_merge", "merge", lambda llm: merge_pass(llm, tier1, ps, cls))
            stories = merged.stories + [s for s in stories if s.source != "tier1"]
            unsorted += merged.unsorted
        except Exception as e:  # the chunks' stories stand unmerged
            notes.append(f"merge pass: {type(e).__name__}: {e}"[:300])
    if unsorted:
        stories.append(PlannedStory(key="unsorted", unsorted=True, source="tier1", placements=unsorted))
    return StoryPlan(stories=stories, notes=notes, complete=not fell_back)   # a failed merge pass leaves it complete
