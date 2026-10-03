"""Review Board model: nodes, flows (entry -> change -> where the effect lands), impact annotations, change summary.

Built deterministically from the change set, facts, impact model and findings. The LLM stage may later rewrite
flow narratives (`Flow.what`) and the change intent (`About.intent`).
"""
from __future__ import annotations

import difflib
import fnmatch
import posixpath
import re
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from codetortoise.config import AnalysisConfig
from codetortoise.detectors.base import SEVERITY_RANK, Finding
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function
from codetortoise.impact import ImpactModel
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


class NodeChange(BaseModel):
    kind: Literal["modified", "signature", "added", "removed"]
    add: int = 0
    rem: int = 0


class BoardNode(BaseModel):
    id: str
    key: str
    label: str
    kind: Literal["function", "field"] = "function"
    layer: int | None = None
    path: str | None = None          # depot path of the defining file
    local: str | None = None
    range: list[int] | None = None   # [start, end] lines on the new side (old side for removed functions)
    change: NodeChange | None = None
    x: float = 0.0
    warn: int = 0
    files: Files = None


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


class Board(BaseModel):
    nodes: list[BoardNode] = Field(default_factory=list)
    edges: list[BoardEdge] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    impacts: list[Impact] = Field(default_factory=list)
    layers: list[BoardLayer] = Field(default_factory=list)
    about: About
    hidden_nodes: int = 0


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


def _count(before: str, after: str, lo: int | None = None, hi: int | None = None) -> tuple[int, int]:
    """(+added, -removed) lines, optionally only those whose new-side line (or nearest) is within [lo, hi]."""
    a, b = before.splitlines(), after.splitlines()
    add = rem = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
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
        self.calls_after = [e for fx in c.after for e in fx.calls]
        self.fields_after = [a for fx in c.after for a in fx.fields]
        self.fields_before = [a for fx in c.before for a in fx.fields]
        self.finding_by = defaultdict(list)          # (kind, node id) -> finding ids
        for f in c.findings:
            for n in f.nodes:
                self.finding_by[(f.kind, n)].append(f.id)

    def is_test(self, nid: str) -> bool:
        """Test code is never a flow entry or landing, and is not shown as blast radius."""
        node = self.im.nodes[nid]
        if nid in self.changed or not node.file:
            return False
        root = self.c.root.rstrip("/") + "/"
        return is_test_path(node.file[len(root):] if self.c.root and node.file.startswith(root) else node.file)

    def label(self, nid: str) -> str:
        return self.im.nodes[nid].label

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
                          check=check))
    flows.sort(key=lambda f: (-SEVERITY_RANK.get(f.severity, 0), 0 if f.tag == "state" else 1, len(f.path), f.text))
    flows = flows[: x.c.cfg.max_flows]
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


def build_board(c: BoardContext) -> Board:
    x = _Ctx(c)
    impacts = build_impacts(x)
    flows = build_flows(x, impacts)
    im = c.impact
    # node selection: changed, flow nodes, fields around changed functions, then top blast items; capped
    chosen: list[str] = []

    def take(nid):
        if nid in im.nodes and nid not in chosen:
            chosen.append(nid)
    for n in im.changed:
        take(n)
    for f in flows:
        for n in f.path:
            take(n)
    for e in im.edges:
        if e.kind in ("writes", "reads") and e.src in x.changed:
            take(e.dst)
    for i in impacts:
        if not x.is_test(i.node):
            take(i.node)
    for b in [b for b in im.blast if not x.is_test(b.node)][: c.cfg.board_blast_nodes]:
        take(b.node)
    hidden = max(0, len(chosen) - c.cfg.board_max_nodes)
    chosen = chosen[: c.cfg.board_max_nodes]
    sel = set(chosen)
    # layers: fields sit in the layer of their record's module, else their writer's layer
    # after-side facts win: the node shows the new file
    record_file = {f"field:{a.field}": a.record_file for a in x.fields_before + x.fields_after if a.record_file}
    decl_line = {f"field:{a.field}": a.decl_line for a in x.fields_before + x.fields_after if a.decl_line}
    layer_of: dict[str, int] = {}
    for nid in chosen:
        n = im.nodes[nid]
        lv = n.layer
        if n.kind == "field":
            rf = record_file.get(n.key)
            lv = c.layers.level_of(rf) if (c.layers and rf) else None
            if lv is None:
                lv = next((im.nodes[e.src].layer for e in im.edges if e.dst == nid and e.kind == "writes"
                           and im.nodes[e.src].layer is not None), None)
        layer_of[nid] = lv if lv is not None else -1
    edges = [e for e in im.edges if e.src in sel and e.dst in sel]
    xs = barycentre_layout(layer_of, [(e.src, e.dst) for e in edges])
    # per-node details
    warn = defaultdict(int)
    for i in impacts:
        if i.severity == "warn":
            warn[i.node] += 1
    kind_of = {"body_modified": "modified", "signature_changed": "signature", "added": "added", "removed": "removed"}
    texts = {f.local: f for f in c.cs.files}
    shown = [i for i in impacts if i.node in sel]
    locals_of: dict[str, str | None] = {}
    for nid in chosen:
        n = im.nodes[nid]
        fn = x.fa.get(n.key) or x.fb.get(n.key)
        locals_of[nid] = (record_file.get(n.key) or None) if n.kind == "field" else (fn.file if fn else n.file)
    depots = c.depots_for(sorted({p for p in [*locals_of.values(), *(i.path for i in shown)] if p}))
    for i in shown:
        i.path = depots.get(i.path) if i.path else None
    nodes = []
    for nid in chosen:
        n = im.nodes[nid]
        fn = x.fa.get(n.key) or x.fb.get(n.key)
        local, rng, change = locals_of[nid], None, None
        if n.kind == "field":
            dl = decl_line.get(n.key)
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
        nodes.append(BoardNode(id=nid, key=n.key, label=n.label, kind=n.kind, layer=layer_of[nid],
                               path=depots.get(local) if local else None, local=local, range=rng, change=change,
                               x=xs.get(nid, 0.0), warn=warn[nid]))
    levels = sorted({lv for lv in layer_of.values()}, reverse=True)
    layers = [BoardLayer(level=lv, name=(_layer_name(x, lv) if lv >= 0 else "other")) for lv in levels]
    return Board(nodes=nodes, edges=[BoardEdge(src=e.src, dst=e.dst, kind=e.kind, status=e.status, confidence=e.confidence)
                                     for e in edges],
                 flows=flows, impacts=shown, layers=layers,
                 about=build_about(c), hidden_nodes=hidden)


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
