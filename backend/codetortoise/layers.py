"""Architectural layers inferred from the module dependency graph."""
from __future__ import annotations

import os
from collections import Counter

import networkx as nx
from pydantic import BaseModel, Field

from codetortoise.index.symbols import SymbolIndex
from codetortoise.paths import canon

# bump when inference changes so cached layer models (keyed by index generation) are recomputed
ALGORITHM_VERSION = 2


class Layer(BaseModel):
    level: int
    name: str
    description: str = ""
    modules: list[str] = Field(default_factory=list)


class LayerModel(BaseModel):
    root: str
    generation: int = 0
    layers: list[Layer] = Field(default_factory=list)
    module_level: dict[str, int] = Field(default_factory=dict)
    cycles_broken: int = 0  # module dependency edges dropped to make the graph acyclic

    def module_of(self, path: str) -> str:
        rel = os.path.relpath(os.path.dirname(canon(path)), self.root)
        rel = "." if rel in ("", ".") else rel
        cur = rel
        while True:
            if cur in self.module_level:
                return cur
            if cur in (".", "") or cur.startswith(".."):
                return "."
            cur = os.path.dirname(cur) or "."

    def level_of(self, path: str) -> int | None:
        return self.module_level.get(self.module_of(path))

    def layer(self, level: int | None) -> Layer | None:
        return next((l for l in self.layers if l.level == level), None)


def _modules(files: list[str], root: str, min_files: int) -> dict[str, str]:
    """file -> module dir (relative to root): deepest ancestor dir whose subtree has >= min_files files."""
    subtree: Counter[str] = Counter()
    rels = {}
    for f in files:
        d = os.path.relpath(os.path.dirname(f), root)
        rels[f] = d
        cur = d
        while True:
            subtree[cur] += 1
            if cur in (".", ""):
                break
            cur = os.path.dirname(cur) or "."
    out = {}
    for f, d in rels.items():
        cur = d
        while subtree[cur] < min_files and cur not in (".", ""):
            cur = os.path.dirname(cur) or "."
        out[f] = cur
    return out


def _break_cycles(g: nx.DiGraph) -> int:
    """Make g acyclic by removing the weakest edge of each remaining cycle (greedy feedback-arc removal).

    Real codebases have cycles (utilities including core headers, name-matched calls into tests); collapsing
    them into one SCC would flatten the architecture into a couple of layers.
    """
    removed = 0
    for a, b in list(g.edges):
        if g.has_edge(b, a) and g.has_edge(a, b):
            wa, wb = g.edges[a, b]["weight"], g.edges[b, a]["weight"]
            if wa != wb:
                g.remove_edge(*((a, b) if wa < wb else (b, a)))
                removed += 1
    while True:
        try:
            cycle = nx.find_cycle(g)
        except nx.NetworkXNoCycle:
            return removed
        u, v = min(((u, v) for u, v, *_ in cycle), key=lambda e: (g.edges[e]["weight"], e))
        g.remove_edge(u, v)
        removed += 1


def infer_layers(index: SymbolIndex, root: str, min_files: int = 5, max_layers: int = 8) -> LayerModel:
    root = canon(root)
    files = index.files()
    mod = _modules(files, root, min_files)
    sizes = Counter(mod.values())
    g = nx.DiGraph()
    g.add_nodes_from(set(mod.values()))
    for a, b in index.include_edges() + index.call_edges_by_path():
        ma, mb = mod.get(a), mod.get(b)
        if ma and mb and ma != mb:
            if g.has_edge(ma, mb):
                g.edges[ma, mb]["weight"] += 1
            else:
                g.add_edge(ma, mb, weight=1)
    broken = _break_cycles(g)
    level: dict[str, int] = {}
    for n in reversed(list(nx.topological_sort(g))):
        succ = list(g.successors(n))
        level[n] = 0 if not succ else 1 + max(level[s] for s in succ)
    top = max(level.values(), default=0)
    if top + 1 > max_layers:
        level = {n: l * max_layers // (top + 1) for n, l in level.items()}
    layers = []
    for lv in sorted(set(level.values())):
        mods = sorted((m for m, l in level.items() if l == lv), key=lambda m: (-sizes[m], m))
        layers.append(Layer(level=lv, name=f"L{lv}: {', '.join(mods[:3])}", modules=sorted(mods)))
    return LayerModel(root=root, generation=index.generation(), layers=layers, module_level=level,
                      cycles_broken=broken)
