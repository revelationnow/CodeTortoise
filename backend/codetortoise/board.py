"""Review Board model: nodes, flows (entry -> change -> where the effect lands), impact annotations, change summary.

Built deterministically from the change set, facts, impact model and findings. The LLM stage may later rewrite
flow narratives (`Flow.what`) and the change intent (`About.intent`).
"""
from __future__ import annotations

import difflib
import fnmatch
import functools
import posixpath
import re
from collections import defaultdict, deque
from collections.abc import Callable, Collection
from dataclasses import dataclass
from dataclasses import field as dfield
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from codetortoise.clusters import altered_access, cluster_change
from codetortoise.config import AnalysisConfig
from codetortoise.detectors.base import SEVERITY_RANK, Finding
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function
from codetortoise.impact import Edge, ImpactModel
from codetortoise.layers import LayerModel
from codetortoise.vcs.model import ChangeSet

Channel = Literal["contract", "signature", "state"]
Files = list[str] | None          # depot paths an item depends on (spec §14.3); None = unknown, owner-only in stage 2
Sev = Literal["warn", "info", "ok"]
_RANGE_OPS = ("!=", "<", ">", "<=", ">=")
X_SPACING = 220.0
_TEST_DIR = re.compile(r"(^|/)(tests?|testing|unittests?|fuzzers?|fuzz)/")
_TEST_FILE = re.compile(r"(^|/)(test_[^/]*|[^/]*_(test|tests|unittest)\.[a-z+]+)$")


def is_test_path(rel: str) -> bool:
    """Test code by its workspace-relative path: a tests/test/testing/unittest(s)/fuzz(ers) directory, or a
    test_*.c / *_test.cc / *_unittest.cpp style file name."""
    return bool(_TEST_DIR.search(rel) or _TEST_FILE.search(rel))


def unchanged_test(im: ImpactModel, root: str, nid: str, changed: Collection[str]) -> bool:
    """Unchanged test code (by its path under the workspace `root`): left out of flows, blast radius and "+N callers".
    Changed test code counts like any other code."""
    f = im.nodes[nid].file
    if nid in changed or not f:
        return False
    r = root.rstrip("/") + "/"
    return is_test_path(f[len(r):] if root and f.startswith(r) else f)


class NodeChange(BaseModel):
    kind: Literal["modified", "signature", "added", "removed"]
    add: int = 0
    rem: int = 0


class StructField(BaseModel):
    id: str
    label: str


class BoardNode(BaseModel):
    id: str
    key: str
    label: str
    kind: Literal["function", "field", "struct", "more"] = "function"
    layer: int | None = None
    path: str | None = None          # depot path of the defining file
    local: str | None = None
    range: list[int] | None = None   # [start, end] lines on the new side (old side for removed functions)
    change: NodeChange | None = None
    x: float = 0.0
    warn: int = 0
    files: Files = None
    home: str | None = None          # a visitor: the cluster this node belongs to (spec 2026-10-03-large §3)
    more_callers: int = 0            # callers / callees not on the board, for "+N callers" (expansion)
    more_callees: int = 0
    note: str | None = None          # a story graph: what changed here, in a few words (spec 2026-10-04 §3.1)
    fields: list[StructField] = Field(default_factory=list)   # a struct node: the fields it stands for


class BoardEdge(BaseModel):
    src: str
    dst: str
    kind: str
    status: str
    confidence: str
    files: Files = None


class Impact(BaseModel):
    node: str
    path: str | None
    line: int
    side: Literal["new", "old"] = "new"
    severity: Sev
    channel: Channel
    title: str
    text: str
    finding: str | None = None
    cause: str | None = None         # the changed node this impact comes from
    landing: bool = False            # a flow may land here (ignoring caller, field reader, signature caller)
    refs: list[str] | None = None    # other nodes its text names (readers, writers, the field); None = stored before refs
    files: Files = None


class Flow(BaseModel):
    id: str
    path: list[str]
    tag: Literal["state", "contract"]
    lands: str
    fx_at: str | None = None
    severity: str
    findings: list[str] = Field(default_factory=list)
    text: str
    title: str = ""                  # short headline for the phone flow reader (spec §13.6)
    what: str
    effect: str
    check: str
    what_source: Literal["template", "llm"] = "template"
    cause: str | None = None         # the changed node the flow comes from (its cluster's)
    files: Files = None
    what_files: Files = None         # files behind `what`/`title`: the flow's own for template text, the prompt's for LLM text

    @model_validator(mode="after")
    def _title_from_text(self) -> Flow:
        """Boards stored before titles existed: the effect after "⟶", else what the flow ends on."""
        if not self.title:
            head, _, tail = self.text.partition("⟶")
            self.title = tail.strip() or f"affects {head.split(' → ')[-1].strip()}"
        return self


class BoardLayer(BaseModel):
    level: int
    name: str
    files: Files = None


class AboutFile(BaseModel):
    path: str
    name: str
    action: str
    cls: list[int]
    add: int
    rem: int
    files: Files = None


class AboutDir(BaseModel):
    dir: str
    files: list[AboutFile]


class AboutCl(BaseModel):
    cl: int
    user: str
    description: str
    file_count: int
    files: Files = None

    @model_validator(mode="before")
    @classmethod
    def _count_was_files(cls, data):
        """Boards stored before tags kept the file count in `files`."""
        if isinstance(data, dict) and isinstance(data.get("files"), int):
            data = {**data, "file_count": data["files"], "files": None}
        return data


class AboutWhy(BaseModel):
    severity: str
    text: str
    finding: str
    files: Files = None


class AboutDrift(BaseModel):
    text: str
    files: Files = None
    # ahead: the workspace is newer than the change's base (normal for submitted CLs; information only);
    # behind / missing: context code may lack what the change builds on (a warning); unknown: stored before kinds
    kind: Literal["ahead", "behind", "missing", "unknown"] = "unknown"
    severity: Literal["warn", "info"] = "warn"

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data):
        """Boards stored before tags kept drift lines as "<depot> (base #a, workspace #b)" strings."""
        if isinstance(data, str):
            return {"text": data, "files": [data.split(" (base ", 1)[0]]}
        return data


class About(BaseModel):
    intent: str
    intent_source: Literal["template", "llm"] = "template"
    intent_files: Files = None
    why: list[AboutWhy] = Field(default_factory=list)
    cls: list[AboutCl] = Field(default_factory=list)
    tree: list[AboutDir] = Field(default_factory=list)
    drift: list[AboutDrift] = Field(default_factory=list)   # base workspace differs from the CL base: context code may not match


class ClusterRef(BaseModel):
    id: str
    name: str


class Board(BaseModel):
    nodes: list[BoardNode] = Field(default_factory=list)
    edges: list[BoardEdge] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    impacts: list[Impact] = Field(default_factory=list)
    layers: list[BoardLayer] = Field(default_factory=list)
    about: About
    hidden_nodes: int = 0
    cluster: ClusterRef | None = None   # a cluster's board in a split review


class ClusterInfo(BaseModel):
    id: str
    name: str
    level: int | None = None
    also: list[int] = Field(default_factory=list)
    risk: str | None = None
    test: bool = False
    files: list[str] = Field(default_factory=list)    # depot paths of its changed code
    changed: int = 0                                  # changed functions
    flows: int = 0
    findings: int = 0
    finding_ids: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)    # its changed nodes


class ClusterLink(BaseModel):
    src: str
    dst: str
    calls: int = 0                                    # calls from src's changed code into dst's
    fields: int = 0                                   # fields src's changed code writes and dst's reads or writes


class Overview(BaseModel):
    about: About
    clusters: list[ClusterInfo] = Field(default_factory=list)
    links: list[ClusterLink] = Field(default_factory=list)
    layers: list[BoardLayer] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)
    merged_over_limit: int = 0


@dataclass
class BoardSet:
    """What the board stage stores: one board, or an overview and one board per cluster."""
    board: Board | None = None
    overview: Overview | None = None
    clusters: dict[str, Board] = dfield(default_factory=dict)
    home: dict[str, str] = dfield(default_factory=dict)     # node id -> cluster id
    note: str | None = None                                # why the review fell back to one board
    stories: Any = None                                    # stories.StorySet (spec 2026-10-04), when built
    story_details: dict[str, Any] = dfield(default_factory=dict)   # story id -> stories.StoryDetail
    analysis: Any = None                                   # the Analysis the boards were built from (not stored)


@dataclass
class BoardContext:
    cs: ChangeSet
    dm: DiffMap
    before: list[Facts]
    after: list[Facts]
    impact: ImpactModel
    findings: list[Finding]
    layers: LayerModel | None
    cfg: AnalysisConfig
    depots_for: Callable[[list[str]], dict[str, str]]   # canonical local paths -> depot paths (called once)
    root: str = ""                   # canonical workspace root; test code is recognised by paths relative to it


# ------------------------------------------------------------------ helpers
def _fns(facts: list[Facts]) -> dict[str, Function]:
    return {f.usr: f for fx in facts for f in fx.functions}


def _covered(compared: list[str], new_values: list[str]) -> bool:
    if any(c.startswith(_RANGE_OPS) for c in compared):
        return True
    return all(any(c == f"=={v}" for c in compared) for v in new_values)


def _val(v: str, names: dict[str, str]) -> str:
    return f"{names[v]} ({v})" if v in names else v


def _cmp(c: CallEdge) -> str:
    return ", ".join(f"{c.compared_names[x]} ({x})" if x in c.compared_names else x for x in c.compared)


@functools.lru_cache(maxsize=128)
def _opcodes(before: str, after: str) -> tuple:
    """A file's line diff, once: every changed function of the file is counted against it."""
    return tuple(difflib.SequenceMatcher(None, before.splitlines(), after.splitlines(), autojunk=False).get_opcodes())


def _count(before: str, after: str, lo: int | None = None, hi: int | None = None) -> tuple[int, int]:
    """(+added, -removed) lines, optionally only those whose new-side line (or nearest) is within [lo, hi]."""
    add = rem = 0
    for tag, i1, i2, j1, j2 in _opcodes(before, after):
        if tag == "equal":
            continue
        if lo is not None and not (j1 + 1 <= hi and max(j2, j1 + 1) >= lo):
            continue
        add += j2 - j1
        rem += i2 - i1
    return add, rem


class _Ctx:
    """Shared lookups for the builders below."""

    def __init__(self, c: BoardContext):
        self.c = c
        self.fb, self.fa = _fns(c.before), _fns(c.after)
        self.im = c.impact
        self.id_of = {n.key: n.id for n in c.impact.nodes.values()}
        self.changed = set(c.impact.changed)
        self.changed_keys = {c.impact.nodes[n].key for n in self.changed}
        self.texts = {f.local: f for f in c.cs.files}                 # local path -> the file's before/after text
        self.calls_after = [e for fx in c.after for e in fx.calls]
        self.fields_after = [a for fx in c.after for a in fx.fields]
        self.fields_before = [a for fx in c.before for a in fx.fields]
        self.finding_by = defaultdict(list)          # (kind, node id) -> finding ids
        for f in c.findings:
            for n in f.nodes:
                self.finding_by[(f.kind, n)].append(f.id)
        self.record_file = {f"field:{a.field}": a.record_file for a in self.fields_before + self.fields_after
                            if a.record_file}
        self.decl_line = {f"field:{a.field}": a.decl_line for a in self.fields_before + self.fields_after if a.decl_line}
        self.callers: dict[str, set[str]] = defaultdict(set)
        self.callees: dict[str, set[str]] = defaultdict(set)
        for e in c.impact.edges:
            if e.kind in ("call", "virtual"):
                self.callers[e.dst].add(e.src)
                self.callees[e.src].add(e.dst)

    def is_test(self, nid: str) -> bool:
        """Test code is never a flow entry or landing, and is not shown as blast radius."""
        return unchanged_test(self.im, self.c.root, nid, self.changed)

    def label(self, nid: str) -> str:
        return self.im.nodes[nid].label

    def is_test_path(self, nid: str) -> bool:
        """Test code by path, changed or not (clusters keep changed test code apart)."""
        f = self.im.nodes[nid].file
        if not f:
            return False
        root = self.c.root.rstrip("/") + "/"
        return is_test_path(f[len(root):] if self.c.root and f.startswith(root) else f)

    @functools.cached_property
    def writes_from(self) -> dict[str, list[Edge]]:
        """Node id -> its field writes (edges), for notes on what changed."""
        out: dict[str, list[Edge]] = defaultdict(list)
        for e in self.im.edges:
            if e.kind == "writes":
                out[e.src].append(e)
        return out

    def module_of(self, path: str) -> str:
        return self.c.layers.module_of(path) if self.c.layers and path else posixpath.dirname(path)

    def local(self, nid: str) -> str | None:
        """The node's file: a field's record header, a function's file (after side first)."""
        n = self.im.nodes[nid]
        if n.kind == "field":
            return self.record_file.get(n.key) or None
        fn = self.fa.get(n.key) or self.fb.get(n.key)
        return fn.file if fn else n.file

    def layer(self, nid: str) -> int:
        """Its layer band: fields sit in their record's module's layer, else their writer's; -1 for none."""
        n = self.im.nodes[nid]
        lv = n.layer
        if n.kind == "field":
            rf = self.record_file.get(n.key)
            lv = self.c.layers.level_of(rf) if (self.c.layers and rf) else None
            if lv is None:
                lv = next((self.im.nodes[e.src].layer for e in self.im.edges if e.dst == nid and e.kind == "writes"
                           and self.im.nodes[e.src].layer is not None), None)
        return lv if lv is not None else -1

    def finding(self, kind: str, nid: str) -> str | None:
        ids = self.finding_by.get((kind, nid))
        return ids[0] if ids else None


# ------------------------------------------------------------------ impacts
def _new_writes(x: _Ctx, usr: str) -> dict[str, list[FieldAccess]]:
    """field USR -> accesses newly writing it in `usr` (non-local roots), as the field_mutation detector sees them."""
    def writes(accs):
        out = defaultdict(list)
        for a in accs:
            if a.fn == usr and a.mode != "read" and a.root_kind != "local":
                out[(a.field, a.root_kind)].append(a)
        return out
    wb, wa = writes(x.fields_before), writes(x.fields_after)
    res: dict[str, list[FieldAccess]] = defaultdict(list)
    for key in set(wa) - set(wb):
        res[key[0]].extend(wa[key])
    return res


def build_impacts(x: _Ctx) -> list[Impact]:
    out: list[Impact] = []
    seen: set[tuple] = set()

    def add(node: str | None, local: str, line: int, sev: Sev, channel: Channel, title: str, text: str, finding=None,
            landing=False, refs=()):
        if not node or not line:
            return
        k = (node, local, line, channel, text)
        if k in seen:
            return
        seen.add(k)
        out.append(Impact(node=node, path=local, line=line, severity=sev, channel=channel, title=title,
                          text=text, finding=finding, cause=cause, landing=landing and sev == "warn" and node != cause,
                          refs=sorted({r for r in refs if r})))

    for nid in sorted(x.changed, key=lambda s: int(s[1:])):
        node, cause = x.im.nodes[nid], nid
        before, after = x.fb.get(node.key), x.fa.get(node.key)
        if before is None or after is None:
            continue
        name = after.qualname
        names = {**before.return_names, **after.return_names}
        contract = x.finding("contract", nid)
        # contract: new return values, at the changed function and at each caller
        new_values = [r for r in after.returns if r not in before.returns]
        if new_values:
            vtext = ", ".join(_val(v, names) for v in new_values)
            for v in new_values:
                add(nid, after.file, after.return_lines.get(v, 0), "warn", "contract", "Contract",
                    f"new return value {_val(v, names)}", contract)
            for c in x.calls_after:
                if c.callee != node.key:
                    continue
                caller = x.id_of.get(c.caller)
                if not c.result_used:
                    add(caller, c.file, c.line, "warn", "contract", "Contract", f"result ignored — {name} can now return {vtext}",
                        contract, landing=True)
                elif c.compared and not _covered(c.compared, new_values):
                    add(caller, c.file, c.line, "warn", "contract", "Contract",
                        f"checks {_cmp(c)} — does not handle {vtext}", contract, landing=True)
                elif c.compared:
                    add(caller, c.file, c.line, "ok", "contract", "Handled", f"checks {_cmp(c)} — covers {vtext}", contract)
                else:
                    add(caller, c.file, c.line, "info", "contract", "Contract",
                        f"uses the result without checking it — {name} can now return {vtext}", contract)
        # signature changes: each caller's call line
        if before.signature != after.signature:
            text = f"calls {name}, whose signature changed: `{before.signature}` → `{after.signature}`"
            for c in x.calls_after:
                if c.callee == node.key:
                    add(x.id_of.get(c.caller), c.file, c.line, "warn", "signature", "Signature", text, contract,
                        landing=True)
            for e in x.im.edges_into(nid, {"call"}):
                if e.confidence == "heuristic" and e.file:
                    add(e.src, e.file, e.line or 0, "info", "signature", "Signature", text + " (name match)", contract)
        # state: fields this function newly writes
        for field, accs in sorted(_new_writes(x, node.key).items()):
            a0 = accs[0]
            fid = x.id_of.get(f"field:{field}")
            fm = x.finding("field_mutation", nid)
            label = f"{a0.record}::{a0.field_name}" if a0.record else a0.field_name
            for a in accs:
                alias = [v for v in a.via if not v.startswith("call:")]
                how = f" through alias `{alias[0]}`" if alias else (f" via {a.via[0][5:]}()" if a.via else "")
                add(nid, a.file, a.line, "warn", "state", "State", f"writes {label}{how}", fm, refs=[fid])
            wline = a0.line
            modes: dict[tuple[str, str, int], set[str]] = defaultdict(set)   # one annotation per line: r, w or both
            for o in x.fields_after:
                if o.field == field and o.fn not in x.changed_keys:
                    modes[(o.fn, o.file, o.line)].add("read" if o.mode == "read" else "write")
            readers, writers, named = set(), set(), set()
            for (fn, file, line), ms in sorted(modes.items()):
                oid = x.id_of.get(fn)
                if not oid:
                    continue
                named.add(oid)
                if "read" in ms:
                    readers.add(x.label(oid))
                if "write" in ms:
                    writers.add(x.label(oid))
                verb = "reads and writes" if len(ms) == 2 else "reads" if "read" in ms else "writes"
                # the effect lands on readers: they observe the new values; pure co-writers are annotated only
                add(oid, file, line, "warn", "state", "State", f"{verb} {label} — now also written by {name} (line {wline})", fm,
                    landing="read" in ms, refs=[fid])
            if fid:
                for e in x.im.edges:
                    if e.dst == fid and e.confidence == "heuristic" and e.file and e.src not in x.changed:
                        add(e.src, e.file, e.line or 0, "info", "state", "State",
                            f"may access {label} (name match) — now written by {name}", fm, refs=[fid])
                if a0.record_file and a0.decl_line:
                    text = f"new writer: {name} · readers: {', '.join(sorted(readers)) or 'none in the parsed code'}"
                    if writers:
                        text += f" · other writers: {', '.join(sorted(writers))}"
                    add(fid, a0.record_file, a0.decl_line, "warn" if readers or writers else "info", "state", "State",
                        text, fm, refs=named)
    return out


# ------------------------------------------------------------------ flows
def _entry_path(x: _Ctx, start: str, warn: dict[str, int], avoid: frozenset[str] = frozenset()) -> list[str]:
    """Shortest caller chain from an entry down to `start` (inclusive), via call/virtual edges.

    Among equally short chains, prefer callers with fewer warnings, so a flow does not detour through a caller that
    is itself the landing of another flow. Test code and nodes in `avoid` (a state flow's landing) are not walked."""
    incoming = defaultdict(list)
    for e in x.im.edges:
        if e.kind in ("call", "virtual") and not x.is_test(e.src) and e.src not in avoid:
            incoming[e.dst].append(e.src)
    top = max((n.layer for nid, n in x.im.nodes.items() if n.layer is not None and not x.is_test(nid)), default=None)
    pats = x.c.cfg.entrypoint_patterns

    def is_entry(n: str) -> bool:
        node = x.im.nodes[n]
        return (not incoming.get(n) or any(fnmatch.fnmatchcase(node.label.split("::")[-1], p) for p in pats)
                or (top is not None and node.layer == top))

    prev = {start: None}
    q = deque([start])
    while q:
        n = q.popleft()
        if is_entry(n):
            chain = [n]
            while prev[chain[-1]] is not None:
                chain.append(prev[chain[-1]])
            return chain                                  # entry ... start
        for src in sorted(incoming.get(n, []), key=lambda s: (warn.get(s, 0), int(s[1:]))):
            if src not in prev:
                prev[src] = n
                q.append(src)
    return [start]


def flow_title(kind: str, landing: str, changed: str, field: str | None = None, values: str | None = None) -> str:
    """Short headline of a flow (spec §13.6)."""
    if kind == "state":
        return f"{landing} sees a new writer of {field or 'a field'}"
    if kind == "ignored":
        return f"{landing} ignores {values}"
    if kind == "unhandled":
        return f"{landing} doesn't handle {values}"
    return f"{landing} calls {changed} (signature changed)"


def build_flows(x: _Ctx, impacts: list[Impact]) -> list[Flow]:
    sev_of = {f.id: f.severity for f in x.c.findings}
    warn: dict[str, int] = defaultdict(int)
    for i in impacts:
        if i.severity == "warn":
            warn[i.node] += 1
    by_key: dict[tuple[str, str, str], Impact] = {}   # one flow per (change, landing, state|contract)
    for imp in impacts:
        if imp.landing and imp.cause and imp.node not in x.changed and not x.is_test(imp.node):
            by_key.setdefault((imp.cause, imp.node, "state" if imp.channel == "state" else "contract"), imp)
    flows: list[Flow] = []
    for (cause, land, _), imp in by_key.items():
        F, L = x.label(cause), x.label(land)
        if imp.channel == "state":
            field_id = next((e.dst for e in x.im.edges if e.src == cause and e.kind == "writes"
                             and any(e2.dst == e.dst and e2.src == land for e2 in x.im.edges)), None)
            head = _entry_path(x, cause, warn, frozenset({land}))
            path = head + ([field_id] if field_id else []) + [land]
            fl = x.label(field_id) if field_id else "the field"
            text = " → ".join(x.label(n) for n in path)
            lead = f"{F} now writes" if head[0] == cause else f"{x.label(head[0])} reaches {F}, which now writes"
            what = f"{lead} {fl}. {L} uses that field, so it now observes values written by {F}."
            effect = f"{L} now sees {fl} changed by {F}; code that assumed the old writers may be surprised."
            check = f"whether {L} assumes {fl} only changes the way it did before"
            title = flow_title("state", L, F, field=fl)
            tag, fx_at = "state", None
        else:
            head = _entry_path(x, land, warn)
            path = head + [cause]
            who = L if head[0] == land else f"{x.label(head[0])} reaches {L}, which"
            if imp.channel == "signature":
                what = f"{who} calls {F}. {imp.text[0].upper()}{imp.text[1:]}."
                effect = f"Arguments {L} passes to {F} are converted to the new parameter types."
                check = f"arguments {L} passes that could change meaning under the new types"
                tail = "signature changed"
                title = flow_title("signature", L, F)
            elif imp.text.startswith("result ignored"):
                vals = imp.text.split("can now return ", 1)[-1]
                what = f"{who} calls {F} and ignores the result. {F} can now return {vals}."
                effect = f"{L} silently drops the new {vals} result."
                check = f"whether {L} can hit the new {vals} path, and what it should do then"
                tail = f"{vals} ignored"
                title = flow_title("ignored", L, F, values=vals)
            else:
                vals = imp.text.split("does not handle ", 1)[-1]
                what = f"{who} calls {F} and {imp.text}."
                effect = f"{L} does not handle {vals}."
                check = f"how {L} should treat {vals}"
                tail = f"{vals} unhandled"
                title = flow_title("unhandled", L, F, values=vals)
            text = " → ".join(x.label(n) for n in path) + f" ⟶ {tail}"
            tag, fx_at = "contract", land
        sev = sev_of.get(imp.finding or "", "medium")
        flows.append(Flow(id="", path=path, tag=tag, lands=land, fx_at=fx_at, severity=sev,
                          findings=[imp.finding] if imp.finding else [], text=text, title=title, what=what, effect=effect,
                          check=check, cause=cause))
    flows.sort(key=lambda f: (-SEVERITY_RANK.get(f.severity, 0), 0 if f.tag == "state" else 1, len(f.path), f.text))
    for i, f in enumerate(flows):
        f.id = f"FL{i + 1}"
    return flows


def _layer_name(x: _Ctx, level: int | None) -> str:
    if level is None or x.c.layers is None:
        return "unlayered"
    layer = x.c.layers.layer(level)
    return layer.name.split(": ", 1)[-1] if layer else f"L{level}"


# ------------------------------------------------------------------ nodes, layout, about
def _crossings(order: dict[int, list[str]], edges: list[tuple[str, str]], layer_of: dict[str, int]) -> int:
    pos = {n: i for lst in order.values() for i, n in enumerate(lst)}
    levels = sorted(order, reverse=True)
    total = 0
    for up, down in zip(levels, levels[1:], strict=False):
        es = [(pos[a], pos[b]) if layer_of[a] == up else (pos[b], pos[a]) for a, b in edges
              if {layer_of.get(a), layer_of.get(b)} == {up, down}]
        total += sum(1 for i, (a1, b1) in enumerate(es) for a2, b2 in es[i + 1:] if (a1 - a2) * (b1 - b2) < 0)
    return total


def barycentre_layout(layer_of: dict[str, int], edges: list[tuple[str, str]], sweeps: int = 4) -> dict[str, float]:
    """World x per node: layers ordered by barycentre sweeps (top-down, bottom-up, ...), spaced X_SPACING apart."""
    order: dict[int, list[str]] = defaultdict(list)
    for n in sorted(layer_of, key=lambda s: (len(s), s)):
        order[layer_of[n]].append(n)
    nbrs = defaultdict(set)
    for a, b in edges:
        if a in layer_of and b in layer_of and layer_of[a] != layer_of[b]:
            nbrs[a].add(b)
            nbrs[b].add(a)
    levels = sorted(order, reverse=True)
    for s in range(sweeps):
        seq = levels if s % 2 == 0 else list(reversed(levels))
        for i, lv in enumerate(seq[1:], 1):
            ref = {n: j for j, n in enumerate(order[seq[i - 1]])}
            cur = order[lv]

            def bc(n, cur=cur, ref=ref):
                ps = [ref[m] for m in nbrs[n] if m in ref]
                return sum(ps) / len(ps) if ps else cur.index(n)
            order[lv] = sorted(cur, key=lambda n: (bc(n), cur.index(n)))
    xs = {}
    for lst in order.values():
        for i, n in enumerate(lst):
            xs[n] = (i - (len(lst) - 1) / 2) * X_SPACING
    return xs


def _required(x: _Ctx, members: list[str], flows: list[Flow], fields: bool = True) -> list[str]:
    """Nodes a board must show, in this order: its changed code, every node on its flows, and the fields whose access
    its changed code added or removed (left out past the budget when one function touches too many). A visitor's
    fields are on its own board."""
    out: dict[str, None] = dict.fromkeys(n for n in members if n in x.im.nodes)
    own = {n for n in out if n in x.changed}
    for f in flows:
        out.update(dict.fromkeys(n for n in f.path if n in x.im.nodes))
    for e in x.im.edges if fields else ():
        if altered_access(e) and e.src in own and e.dst in x.im.nodes:
            out.setdefault(e.dst)
    return list(out)


def _neighbours(x: _Ctx, impacts: list[Impact], scope: set[str]) -> list[str]:
    """Unchanged code worth showing beside `scope`'s changes, most relevant first: what its impacts annotate, the fields
    it touches, then the most affected code (blast radius) reached from it."""
    out: dict[str, None] = {}
    for i in impacts:
        if i.cause in scope and i.node in x.im.nodes and not x.is_test(i.node):
            out.setdefault(i.node)
    for e in x.im.edges:                                  # fields the changed code touches as it did before
        if e.kind in ("writes", "reads") and e.src in scope and e.src in x.changed and e.dst in x.im.nodes:
            out.setdefault(e.dst)
    for b in x.im.blast:
        if b.path and b.path[-1] in scope and not x.is_test(b.node):
            out.setdefault(b.node)
    return list(out)


def _choose(x: _Ctx, required: list[str], neighbours: list[str], core: int = 0) -> tuple[list[str], int]:
    """The required nodes, then neighbours up to the board's budget; how many nodes were left out. The first `core`
    required nodes (changed code and flows) always stay; the fields after them only while they fit."""
    budget = x.c.cfg.board_max_nodes
    chosen = required[:max(budget, core)]
    rest = [n for n in neighbours if n not in set(required)]
    room = max(0, budget - len(chosen))
    return chosen + rest[:room], len(required) - len(chosen) + max(0, len(rest) - room)


def _render(x: _Ctx, impacts: list[Impact], flows: list[Flow], chosen: list[str], depots: dict[str, str], *,
            hidden: int, about: About, cluster: ClusterRef | None = None, home: dict[str, str] | None = None) -> Board:
    """Lay out and describe the chosen nodes as a board."""
    c, im = x.c, x.im
    sel = set(chosen)
    layer_of = {nid: x.layer(nid) for nid in chosen}
    edges = [e for e in im.edges if e.src in sel and e.dst in sel]
    xs = barycentre_layout(layer_of, [(e.src, e.dst) for e in edges])
    warn = defaultdict(int)
    for i in impacts:
        if i.severity == "warn":
            warn[i.node] += 1
    kind_of = {"body_modified": "modified", "signature_changed": "signature", "added": "added", "removed": "removed"}
    texts = {f.local: f for f in c.cs.files}
    shown = [i.model_copy() for i in impacts if i.node in sel]
    for i in shown:
        i.path = depots.get(i.path) if i.path else None
    nodes = []
    for nid in chosen:
        n = im.nodes[nid]
        fn = x.fa.get(n.key) or x.fb.get(n.key)
        local, rng, change = x.local(nid), None, None
        if n.kind == "field":
            dl = x.decl_line.get(n.key)
            rng = [dl, dl] if dl else None
        elif fn is not None:
            rng = [fn.start_line, fn.end_line]
        if nid in x.changed and fn is not None:
            ch = next((d for d in c.dm.functions if d.file == fn.file and d.qualname == fn.qualname), None)
            fc = texts.get(fn.file)
            add = rem = 0
            if fc is not None:
                add, rem = _count(fc.before, fc.after, fn.start_line, fn.end_line)
            change = NodeChange(kind=kind_of.get(ch.kind if ch else "", "modified"), add=add, rem=rem)
        callers = {s_ for s_ in x.callers.get(nid, ()) if s_ not in sel and not x.is_test(s_)}
        callees = {d for d in x.callees.get(nid, ()) if d not in sel and not x.is_test(d)}
        h = (home or {}).get(nid)
        nodes.append(BoardNode(id=nid, key=n.key, label=n.label, kind=n.kind, layer=layer_of[nid],
                               path=depots.get(local) if local else None, local=local, range=rng, change=change,
                               x=xs.get(nid, 0.0), warn=warn[nid], home=h if cluster and h and h != cluster.id else None,
                               more_callers=len(callers), more_callees=len(callees)))
    levels = sorted({lv for lv in layer_of.values()}, reverse=True)
    layers = [BoardLayer(level=lv, name=(_layer_name(x, lv) if lv >= 0 else "other")) for lv in levels]
    return Board(nodes=nodes, edges=[BoardEdge(src=e.src, dst=e.dst, kind=e.kind, status=e.status, confidence=e.confidence)
                                     for e in edges],
                 flows=flows, impacts=shown, layers=layers, about=about, hidden_nodes=hidden, cluster=cluster)


@dataclass
class Analysis:
    """What every board of a change, and its stories, are built from: computed once per review."""
    x: _Ctx
    impacts: list[Impact]
    flows: list[Flow]
    about: About


def analyse(c: BoardContext) -> Analysis:
    x = _Ctx(c)
    impacts = build_impacts(x)
    return Analysis(x, impacts, build_flows(x, impacts), build_about(c))


def build_board(c: BoardContext, a: Analysis | None = None) -> Board:
    """One board for the whole change, within the node budget: required nodes first (changed code, flows, fields),
    then neighbours. Large changes use `build_boards`, which splits them; this is also its fallback."""
    a = a or analyse(c)
    x, impacts, flows = a.x, a.impacts, a.flows
    req = _required(x, list(x.im.changed), flows)
    chosen, hidden = _choose(x, req, _neighbours(x, impacts, set(x.changed)), core=len(req))   # trimmed below
    if len(chosen) > c.cfg.board_max_nodes:                 # the fallback: the most important nodes only
        hidden += len(chosen) - c.cfg.board_max_nodes
        chosen = chosen[: c.cfg.board_max_nodes]
        sel = set(chosen)
        flows = [f for f in flows if set(f.path) <= sel]
    sel = set(chosen)
    depots = c.depots_for(sorted({p for p in [*(x.local(n) for n in chosen), *(i.path for i in impacts if i.node in sel)]
                                  if p}))
    return _render(x, impacts, flows, chosen, depots, hidden=hidden, about=a.about)


def build_boards(c: BoardContext) -> BoardSet:
    """The change's board, or (when it would need more than `board_max_nodes` nodes) an overview and one board per
    cluster (spec 2026-10-03-large-change-boards). Every changed node and flow is on exactly one board."""
    a = analyse(c)
    if len(_required(a.x, list(a.x.im.changed), a.flows)) <= c.cfg.board_max_nodes:
        return BoardSet(board=build_board(c, a), analysis=a)
    try:
        bs = _split(c, a)
    except Exception as e:  # never lose the review over clustering: one board of the most important nodes
        bs = BoardSet(board=build_board(c, a), note=f"shown as one board (clustering failed: {type(e).__name__}: {e})")
    bs.analysis = a
    return bs


def _split(c: BoardContext, a: Analysis) -> BoardSet:
    """An overview and one board per cluster."""
    x, impacts, flows = a.x, a.impacts, a.flows
    res = cluster_change(x.im, flows, c.findings, is_test=x.is_test_path, module_of=x.module_of,
                         max_nodes=c.cfg.board_max_nodes, min_changed=c.cfg.cluster_min_changed,
                         max_clusters=c.cfg.overview_max_clusters)
    by_id = {f.id: f for f in flows}
    picks = {}
    for cl in res.clusters:
        cf = [by_id[i] for i in cl.flows]
        mem = cl.members or ([cl.of] if cl.of else [])
        req, core = _required(x, mem, cf), len(_required(x, mem, cf, fields=False))
        picks[cl.id] = (cf, *_choose(x, req, _neighbours(x, impacts, set(cl.members)), core))
    shown = {n for _, chosen, _ in picks.values() for n in chosen}
    locals_ = {x.local(n) for n in shown} | {i.path for i in impacts if i.node in shown}
    locals_ |= {x.local(m) for cl in res.clusters for m in cl.members}
    depots = c.depots_for(sorted(p for p in locals_ if p))
    about = a.about
    boards = {}
    for cl in res.clusters:
        cf, chosen, hidden = picks[cl.id]
        files = {depots.get(x.local(m)) for m in (cl.members or [cl.of]) if x.local(m)} - {None}   # its own code
        part = about_for(about, files, set(cl.findings), c.findings)
        boards[cl.id] = _render(x, impacts, cf, chosen, depots, hidden=hidden, about=part,
                                cluster=ClusterRef(id=cl.id, name=cl.name), home=res.home)
    return BoardSet(overview=_overview(x, res, about, depots, flows), clusters=boards, home=res.home)


def about_for(about: About, files: set[str], mine: set[str], findings: list[Finding]) -> About:
    """The change summary narrowed to part of the change: its files (depot paths) and its findings."""
    part = about.model_copy(deep=True)
    part.tree = [AboutDir(dir=d.dir, files=[f for f in d.files if f.path in files]) for d in part.tree]
    part.tree = [d for d in part.tree if d.files]
    part.why = [w for w in part.why if w.finding in mine] or [AboutWhy(severity=f.severity, text=f.title, finding=f.id)
                                                               for f in findings if f.id in mine][:4]
    part.drift = [d for d in part.drift if set(d.files or []) & files]
    return part


def _overview(x: _Ctx, res, about: About, depots: dict[str, str], flows: list[Flow]) -> Overview:
    infos = []
    for cl in res.clusters:
        infos.append(ClusterInfo(
            id=cl.id, name=cl.name, level=cl.level, also=cl.also, risk=cl.risk, test=cl.test,
            files=sorted({depots[x.local(m)] for m in cl.members if x.local(m) in depots}),
            changed=sum(1 for m in cl.members if x.im.nodes[m].kind == "function"), flows=len(cl.flows),
            findings=len(cl.findings), finding_ids=list(cl.findings), nodes=list(cl.members)))
    owner = {m: cl.id for cl in res.clusters for m in cl.members}
    calls: dict[tuple[str, str], int] = defaultdict(int)
    for e in x.im.edges:
        a, b = owner.get(e.src), owner.get(e.dst)
        if e.kind in ("call", "virtual") and a and b and a != b:
            calls[(a, b)] += 1
    writes: dict[str, set[str]] = defaultdict(set)
    touches: dict[str, set[str]] = defaultdict(set)
    for e in x.im.edges:
        cid = owner.get(e.src)
        if cid and e.kind in ("writes", "reads"):
            touches[cid].add(e.dst)
            if e.kind == "writes":
                writes[cid].add(e.dst)
    shared = {(a, b): len(writes[a] & touches[b]) for a in writes for b in touches if a != b}
    links = [ClusterLink(src=a, dst=b, calls=calls.get((a, b), 0), fields=shared.get((a, b), 0))
             for a, b in sorted(set(calls) | {k for k, v in shared.items() if v})]
    levels = sorted({cl.level if cl.level is not None else -1 for cl in res.clusters}
                    | {lv for cl in res.clusters for lv in cl.also}, reverse=True)
    layers = [BoardLayer(level=lv, name=(_layer_name(x, lv) if lv >= 0 else "other")) for lv in levels]
    totals = {"files": len(about.tree and [f for d in about.tree for f in d.files]), "clusters": len(res.clusters),
              "flows": len(flows), "findings": len(x.c.findings),
              "changed": sum(1 for n in x.im.changed if n in x.im.nodes and x.im.nodes[n].kind == "function")}
    return Overview(about=about, clusters=infos, links=links, layers=layers, totals=totals,
                    merged_over_limit=res.merged_over_limit)


def expand_board(b: Board, im: ImpactModel, asks: list[tuple[str, str]], *, step: int,
                 ranges: dict[str, list[int]], depot_of: dict[str, Files], layer_name: Callable[[int], str],
                 root: str, home: dict[str, str] | None = None) -> Board:
    """`b` with up to `step` more callers or callees of each asked node ("+N callers"), most affected first, laid out
    again. Asks are applied in order, so a node added by one can be expanded by the next. The board may pass its
    node budget: the reader asked for it."""
    out = b.model_copy(deep=True)
    on = {n.id for n in out.nodes}
    changed = set(im.changed)

    def is_test(nid: str) -> bool:
        return unchanged_test(im, root, nid, changed)
    score = {x.node: x.score for x in im.blast}
    callers: dict[str, set[str]] = defaultdict(set)
    callees: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if e.kind in ("call", "virtual"):
            callers[e.dst].add(e.src)
            callees[e.src].add(e.dst)
    for nid, way in asks:
        if nid not in on:
            continue
        cands = [n for n in (callers if way == "callers" else callees)[nid] - on if n in im.nodes and not is_test(n)]
        for n in sorted(cands, key=lambda n: (-score.get(n, 0.0), int(n[1:]) if n[1:].isdigit() else 0))[:step]:
            node = im.nodes[n]
            h = (home or {}).get(n)
            files = depot_of.get(n) or []
            out.nodes.append(BoardNode(id=n, key=node.key, label=node.label, kind=node.kind,
                                       layer=node.layer if node.layer is not None else -1,
                                       path=files[0] if node.file and files else None, local=node.file,
                                       range=ranges.get(node.key), home=h if out.cluster and h and h != out.cluster.id
                                       else None))
            on.add(n)
    to = {f.id: n.id for n in out.nodes for f in n.fields}         # a story graph's folded field -> its struct node
    out.edges, seen = [], set()
    for e in im.edges:
        src, dst = to.get(e.src, e.src), to.get(e.dst, e.dst)
        if src in on and dst in on and src != dst and (src, dst, e.kind) not in seen:
            seen.add((src, dst, e.kind))
            out.edges.append(BoardEdge(src=src, dst=dst, kind=e.kind, status=e.status, confidence=e.confidence))
    xs = barycentre_layout({n.id: n.layer if n.layer is not None else -1 for n in out.nodes},
                           [(e.src, e.dst) for e in out.edges])
    for n in out.nodes:
        n.x = xs.get(n.id, n.x)
        n.more_callers = len({s_ for s_ in callers.get(n.id, ()) if s_ not in on and not is_test(s_)})
        n.more_callees = len({d for d in callees.get(n.id, ()) if d not in on and not is_test(d)})
    have = {lv.level for lv in out.layers}
    for lv in sorted({n.layer for n in out.nodes if n.layer is not None} - have):
        out.layers.append(BoardLayer(level=lv, name=layer_name(lv) if lv >= 0 else "other"))
    out.layers.sort(key=lambda lv: -lv.level)
    return out


def _tree_prefix(depots: list[str]) -> str:
    """Prefix stripped from the change tree: everything above the deepest directory the files share, so that
    directory itself stays visible (a change inside one directory shows that directory, not ".")."""
    return _common_dir([posixpath.dirname(d) for d in depots])


def _common_dir(paths: list[str]) -> str:
    """Longest common directory of depot paths, keeping the leading // (posixpath.commonpath would collapse it)."""
    if not paths:
        return ""
    parts = [p.split("/")[:-1] for p in paths]
    common = []
    for segs in zip(*parts, strict=False):
        if len(set(segs)) != 1:
            break
        common.append(segs[0])
    return "/".join(common)


def drift_kind(expected: str, actual: str) -> Literal["ahead", "behind", "missing", "unknown"]:
    """Compare revisions like "#3" and "#4"; anything else in the workspace means the file isn't synced."""
    e, a = re.fullmatch(r"#(\d+)", expected or ""), re.fullmatch(r"#(\d+)", actual or "")
    if not a:
        return "missing"
    if not e:
        return "unknown"
    return "ahead" if int(a.group(1)) > int(e.group(1)) else "behind"


def build_about(c: BoardContext) -> About:
    files = c.cs.files
    fn_count = len(c.dm.functions)
    descs = "; ".join(f"CL {m.cl}: {m.description}" for m in c.cs.cls if m.description)
    intent = (f"{fn_count} function(s) changed in {len(files)} file(s). " + (descs + "." if descs else "")).strip()
    why = [AboutWhy(severity=f.severity, text=f.title, finding=f.id) for f in c.findings[:4]]
    cls = [AboutCl(cl=m.cl, user=m.user, description=m.description,
                   file_count=sum(1 for f in files if any(p.cl == m.cl for p in f.per_cl))) for m in c.cs.cls]
    prefix = _tree_prefix([f.depot for f in files])
    dirs: dict[str, list[AboutFile]] = defaultdict(list)
    for f in sorted(files, key=lambda f: f.depot):
        rel = f.depot[len(prefix):].lstrip("/") if prefix else f.depot
        d = posixpath.dirname(rel) or "."
        add, rem = _count(f.before, f.after)
        dirs[d].append(AboutFile(path=f.depot, name=posixpath.basename(rel), action=f.action,
                                 cls=[p.cl for p in f.per_cl], add=add, rem=rem))
    tree = [AboutDir(dir=d, files=fs) for d, fs in sorted(dirs.items())]
    drift = []
    for d in c.cs.drift:
        kind = drift_kind(d.expected, d.actual)
        drift.append(AboutDrift(text=f"{d.depot} (base {d.expected}, workspace {d.actual})", files=[d.depot], kind=kind,
                                severity="info" if kind == "ahead" else "warn"))
    return About(intent=intent, why=why, cls=cls, tree=tree, drift=drift)
