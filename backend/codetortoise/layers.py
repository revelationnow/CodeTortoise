"""Architectural layers inferred from the module dependency graph."""
from __future__ import annotations

import os
from collections import Counter

import networkx as nx
from pydantic import BaseModel, Field

from codetortoise.index.symbols import SymbolIndex
from codetortoise.paths import canon


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


def infer_layers(index: SymbolIndex, root: str, min_files: int = 5, max_layers: int = 8) -> LayerModel:
    root = canon(root)
    files = index.files()
    mod = _modules(files, root, min_files)
    g = nx.DiGraph()
    g.add_nodes_from(set(mod.values()))
    for a, b in index.include_edges() + index.call_edges_by_path():
        ma, mb = mod.get(a), mod.get(b)
        if ma and mb and ma != mb:
            g.add_edge(ma, mb)
    cond = nx.condensation(g)
    level: dict[int, int] = {}
    for n in reversed(list(nx.topological_sort(cond))):
        succ = list(cond.successors(n))
        level[n] = 0 if not succ else 1 + max(level[s] for s in succ)
    top = max(level.values(), default=0)
    if top + 1 > max_layers:
        level = {n: l * max_layers // (top + 1) for n, l in level.items()}
    module_level = {m: level[cond.graph["mapping"][m]] for m in g.nodes}
    layers = []
    for lv in sorted(set(module_level.values())):
        mods = sorted(m for m, l in module_level.items() if l == lv)
        layers.append(Layer(level=lv, name=f"L{lv}: {', '.join(mods[:3])}", modules=mods))
    return LayerModel(root=root, generation=index.generation(), layers=layers, module_level=module_level)
