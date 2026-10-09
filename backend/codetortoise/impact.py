"""Impact model: before/after call + data-coupling graph, call flows, blast radius, header fan-out."""
from __future__ import annotations

import fnmatch
from collections import deque
from collections.abc import Callable, Collection
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.config import AnalysisConfig
from codetortoise.cparse import is_header
from codetortoise.diffmap import DiffMap
from codetortoise.facts.model import Facts, Function
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import LayerModel
from codetortoise.tu_select import TuSelection

Status = Literal["added", "removed", "changed", "unchanged"]
EdgeKind = Literal["call", "virtual", "writes", "reads"]
EdgeConf = Literal["precise", "may", "heuristic"]
_WEIGHT = {"precise": 1.0, "may": 0.6, "heuristic": 0.4}


class Node(BaseModel):
    id: str
    key: str
    kind: Literal["function", "field"] = "function"
    label: str
    file: str | None = None
    line: int | None = None
    status: Status = "unchanged"
    layer: int | None = None
    confidence: Literal["precise", "heuristic"] = "precise"


class Edge(BaseModel):
    id: str
    src: str
    dst: str
    kind: EdgeKind
    status: Literal["added", "removed", "unchanged"] = "unchanged"
    confidence: EdgeConf = "precise"
    file: str | None = None
    line: int | None = None


class Flow(BaseModel):
    root: str
    nodes: list[str]
    edges: list[str]


class BlastItem(BaseModel):
    node: str
    hop: int
    score: float
    via: Literal["call", "data"]
    path: list[str]


class FanOut(BaseModel):
    header: str
    total_tus: int
    by_layer: dict[str, int] = Field(default_factory=dict)


class SinkInfo(BaseModel):
    """A field so many functions touch, or the owner names, that a new write to it says nothing about its users
    (spec 2026-10-09-shared-sinks §3)."""
    field: str                                      # the field node id
    label: str                                      # record::field
    users: int                                      # distinct unchanged functions reading or writing it
    why: Literal["marked", "listed", "threshold"]


class ImpactModel(BaseModel):
    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    blast: list[BlastItem] = Field(default_factory=list)
    fanout: list[FanOut] = Field(default_factory=list)
    capped: dict[str, int] = Field(default_factory=dict)  # name -> heuristic matches skipped (over the cap)
    capped_fields: dict[str, int] = Field(default_factory=dict)  # field label -> functions using its name, skipped
    sinks: dict[str, SinkInfo] = Field(default_factory=dict)   # field node id -> why it is a shared sink

    def node_by_key(self, key: str) -> Node | None:
        return next((n for n in self.nodes.values() if n.key == key), None)

    def edges_into(self, node_id: str, kinds: set[str]) -> list[Edge]:
        return [e for e in self.edges if e.dst == node_id and e.kind in kinds]


def _overlaps(fn: Function, file: str, lines: tuple[int, int] | None) -> bool:
    return (lines is not None and fn.file == file
            and fn.start_line <= lines[1] and lines[0] <= fn.end_line)


def _name_resolver(fns: dict[str, Function]) -> Callable[[str, str], str]:
    """A call tree-sitter knows only by name ("name:foo") goes to the one function called foo: the one in the caller's
    own file, else the one non-static function of that name. A clang parse of a function wins over tree-sitter's.
    Anything else keeps its name."""
    named: dict[str, list[Function]] = {}
    for f in fns.values():
        named.setdefault(f.name, []).append(f)

    def resolve(callee: str, file: str) -> str:
        if not callee.startswith("name:"):
            return callee
        cands = named.get(callee[5:], [])
        real = {(f.file, f.qualname) for f in cands if not f.usr.startswith("ts:")}
        cands = [f for f in cands if not f.usr.startswith("ts:") or (f.file, f.qualname) not in real]
        pick = [f for f in cands if f.file == file] or [f for f in cands if not f.is_static]
        return pick[0].usr if len(pick) == 1 else callee
    return resolve


class _Builder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}                 # key -> node attrs
        self.edges: dict[tuple, dict] = {}               # (src_key, dst_key, kind) -> attrs

    def node(self, key: str, **attrs) -> None:
        cur = self.nodes.setdefault(key, {"key": key})
        for k, v in attrs.items():
            if v is not None and (k not in cur or cur[k] is None):
                cur[k] = v

    def edge(self, src: str, dst: str, kind: str, variant: str, conf: str, file=None, line=None) -> None:
        k = (src, dst, kind)
        cur = self.edges.setdefault(k, {"variants": set(), "confidence": conf, "file": file, "line": line})
        cur["variants"].add(variant)
        if _WEIGHT[conf] > _WEIGHT[cur["confidence"]]:
            cur["confidence"] = conf


def build_impact(before: list[Facts], after: list[Facts], dm: DiffMap, sel: TuSelection,
                 index: SymbolIndex | None, layers: LayerModel | None, cfg: AnalysisConfig,
                 marked: Collection[str] = ()) -> ImpactModel:
    fb = {f.usr: f for facts in before for f in facts.functions}
    fa = {f.usr: f for facts in after for f in facts.functions}
    resolve = _name_resolver({**fb, **fa})
    b = _Builder()

    # 1. changed functions
    changed_status: dict[str, str] = {}
    for ch in dm.functions:
        if ch.kind == "removed":
            hit = [u for u, f in fb.items() if _overlaps(f, ch.file, ch.before_lines)]
            status = "removed"
        else:
            hit = [u for u, f in fa.items() if _overlaps(f, ch.file, ch.after_lines)]
            status = "added" if ch.kind == "added" else "changed"
        if not hit:
            pool = fb if ch.kind == "removed" else fa
            hit = [u for u, f in pool.items() if f.qualname == ch.qualname]
        for u in hit:
            changed_status[u] = status

    # 2. function nodes and call edges
    for variant, facts_list, funcs in (("before", before, fb), ("after", after, fa)):
        for facts in facts_list:
            heuristic = facts.tu.extractor == "treesitter"
            for f in facts.functions:
                b.node(f.usr, kind="function", label=f.qualname, file=f.file, line=f.start_line,
                       confidence="heuristic" if heuristic else "precise")
            for c in facts.calls:
                callee = resolve(c.callee, c.file)
                b.node(callee, kind="function", label=c.callee_name)
                b.edge(c.caller, callee, c.kind if c.kind == "virtual" else "call", variant,
                       "heuristic" if heuristic else c.confidence, c.file, c.line)
                if c.kind == "virtual":
                    mkey = c.callee.split("@F@", 1)[-1]
                    for other in funcs.values():
                        if other.method_key == mkey and other.usr != c.callee:
                            b.node(other.usr, kind="function", label=other.qualname, file=other.file,
                                   line=other.start_line)
                            b.edge(c.caller, other.usr, "virtual", variant, "may", c.file, c.line)
            for a in facts.fields:
                fkey = f"field:{a.field}"
                b.node(fkey, kind="field", label=f"{a.record}::{a.field_name}" if a.record else a.field_name)
                kind = "reads" if a.mode == "read" else "writes"
                conf = "heuristic" if heuristic or a.confidence == "heuristic" else \
                    ("may" if a.confidence == "may" or a.mode == "may_write" else "precise")
                b.edge(a.fn, fkey, kind, variant, conf, a.file, a.line)

    # 3. heuristic edges from the symbol index for code outside the parsed TUs
    parsed = set(sel.selected)
    capped: dict[str, int] = {}
    capped_fields: dict[str, int] = {}
    by_qual = {}
    for u, f in {**fb, **fa}.items():
        by_qual.setdefault(f.qualname, u)
    if index is not None:
        frontier = {(fa.get(u) or fb[u]).name: u for u in changed_status if (fa.get(u) or fb.get(u))}
        for _hop in range(cfg.caller_hops):
            nxt: dict[str, str] = {}
            for name, target in frontier.items():
                rows = [r for r in index.callers_of(name) if r.path not in parsed and r.caller]
                if len(rows) > cfg.heuristic_fanin_cap:
                    capped[name] = len(rows)
                    continue
                for row in rows:
                    key = by_qual.get(row.caller) or f"ts:{row.path}#{row.caller}"
                    b.node(key, kind="function", label=row.caller, file=row.path, line=row.line,
                           confidence="heuristic")
                    b.edge(key, target, "call", "after", "heuristic", row.path, row.line)
                    nxt[row.caller.split("::")[-1]] = key
            frontier = nxt
        written = {(k[1], b.nodes[k[1]]["label"]) for k, e in b.edges.items()
                   if k[2] == "writes" and k[0] in changed_status}
        record_files = {f"field:{a.field}": a.record_file for facts in before + after for a in facts.fields}
        for fkey, label in written:
            fname = label.split("::")[-1]
            rfile = record_files.get(fkey, "")
            # a same-named member only counts if its file can see the record's declaration
            allowed = ({rfile} | index.transitive_includers(rfile)) if rfile else None
            rows = [r for r in index.member_refs(fname) if r.path not in parsed and r.fn
                    and (allowed is None or r.path in allowed)]
            if len(rows) > cfg.heuristic_fanin_cap:
                capped_fields[label] = len({(r.path, r.fn) for r in rows})   # functions, not references: a sink's users
                continue
            for row in rows:
                key = by_qual.get(row.fn) or f"ts:{row.path}#{row.fn}"
                b.node(key, kind="function", label=row.fn, file=row.path, line=row.line, confidence="heuristic")
                b.edge(key, fkey, "writes" if row.is_write else "reads", "after", "heuristic", row.path, row.line)

    # 4. materialize with stable ids
    model = ImpactModel()
    key_to_id: dict[str, str] = {}
    for i, key in enumerate(sorted(b.nodes)):
        attrs = b.nodes[key]
        nid = f"N{i + 1}"
        key_to_id[key] = nid
        file = attrs.get("file")
        model.nodes[nid] = Node(
            id=nid, key=key, kind=attrs.get("kind", "function"), label=attrs.get("label", key),
            file=file, line=attrs.get("line"), status=changed_status.get(key, "unchanged"),
            layer=layers.level_of(file) if (layers and file) else None,
            confidence=attrs.get("confidence", "precise"))
    for i, (k, e) in enumerate(sorted(b.edges.items(), key=lambda kv: kv[0])):
        v = e["variants"]
        status = "unchanged" if len(v) == 2 else ("added" if "after" in v else "removed")
        model.edges.append(Edge(id=f"E{i + 1}", src=key_to_id[k[0]], dst=key_to_id[k[1]], kind=k[2],
                                status=status, confidence=e["confidence"], file=e["file"], line=e["line"]))
    model.capped, model.capped_fields = capped, capped_fields
    model.changed = sorted((key_to_id[u] for u in changed_status if u in key_to_id), key=lambda s: int(s[1:]))

    from codetortoise.sinks import find_sinks  # sinks.py builds on this module's models
    model.sinks = find_sinks(model, cfg.sink_threshold, cfg.sink_fields, marked)
    _flows(model, cfg)
    _blast(model, cfg)
    _fanout(model, sel, index, layers)
    return model


def _flows(model: ImpactModel, cfg: AnalysisConfig) -> None:
    """Per changed function: callees down to flow_depth plus callers up to caller_hops."""
    out_edges: dict[str, list[Edge]] = {}
    in_edges: dict[str, list[Edge]] = {}
    for e in model.edges:
        if e.kind in ("call", "virtual"):
            out_edges.setdefault(e.src, []).append(e)
            in_edges.setdefault(e.dst, []).append(e)
    for root in model.changed:
        nodes, edges = [root], []
        seen, seen_edges = {root}, set()
        for adjacency, depth, forward in ((out_edges, cfg.flow_depth, True), (in_edges, cfg.caller_hops, False)):
            q = deque([(root, 0)])
            while q:
                n, d = q.popleft()
                if d >= depth:
                    continue
                for e in adjacency.get(n, []):
                    if e.id not in seen_edges:
                        seen_edges.add(e.id)
                        edges.append(e.id)
                    nxt = e.dst if forward else e.src
                    if nxt not in seen:
                        seen.add(nxt)
                        nodes.append(nxt)
                        q.append((nxt, d + 1))
        model.flows.append(Flow(root=root, nodes=nodes, edges=edges))


def _blast(model: ImpactModel, cfg: AnalysisConfig) -> None:
    incoming: dict[str, list[Edge]] = {}
    field_users: dict[str, list[Edge]] = {}
    writes_from: dict[str, list[Edge]] = {}
    for e in model.edges:
        if e.kind in ("call", "virtual"):
            incoming.setdefault(e.dst, []).append(e)
        elif e.status != "removed":
            field_users.setdefault(e.dst, []).append(e)
            if e.kind == "writes":
                writes_from.setdefault(e.src, []).append(e)
    seeds = set(model.changed)
    score: dict[str, float] = {}
    hop_of: dict[str, int] = {}
    via_of: dict[str, str] = {}
    pred: dict[str, str] = {}
    virtual_hit: set[str] = set()
    frontier = list(model.changed)
    for hop in range(1, cfg.blast_hops + 1):
        nxt: list[str] = []
        for n in frontier:
            reached: list[tuple[str, Edge, str]] = [(e.src, e, "call") for e in incoming.get(n, [])]
            if n in seeds:
                for w in writes_from.get(n, []):
                    if w.dst in model.sinks:              # a shared sink's users are not affected code
                        continue
                    for u in field_users.get(w.dst, []):
                        if u.src != n:
                            reached.append((u.src, u, "data"))
            for m, e, via in reached:
                if m in seeds:
                    continue
                score[m] = score.get(m, 0.0) + _WEIGHT[e.confidence] / hop
                if e.kind == "virtual":
                    virtual_hit.add(m)
                if m not in hop_of:
                    hop_of[m], via_of[m], pred[m] = hop, via, n
                    nxt.append(m)
        frontier = nxt
    layer_of = {nid: n.layer for nid, n in model.nodes.items()}
    for m, s in score.items():
        node = model.nodes[m]
        callers_layers = {layer_of[e.src] for e in incoming.get(m, [])}
        if any(l is not None and l != node.layer for l in callers_layers):
            s *= 1.5
        if any(fnmatch.fnmatchcase(node.label.split("::")[-1], p) for p in cfg.entrypoint_patterns):
            s *= 1.5
        if m in virtual_hit:
            s *= 1.3
        path = [m]
        while path[-1] in pred:
            path.append(pred[path[-1]])
        model.blast.append(BlastItem(node=m, hop=hop_of[m], score=round(s, 3), via=via_of[m], path=path))
    model.blast.sort(key=lambda x: (-x.score, x.hop, int(x.node[1:])))


def _fanout(model: ImpactModel, sel: TuSelection, index: SymbolIndex | None, layers: LayerModel | None) -> None:
    for header, total in sorted(sel.header_fanout.items()):
        by_layer: dict[str, int] = {}
        if index is not None and layers is not None:
            for p in index.transitive_includers(header):
                if is_header(p):
                    continue
                lv = layers.level_of(p)
                layer = layers.layer(lv)
                name = layer.name if layer else "unlayered"
                by_layer[name] = by_layer.get(name, 0) + 1
        model.fanout.append(FanOut(header=header, total_tus=total, by_layer=by_layer))
