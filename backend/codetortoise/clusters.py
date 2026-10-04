"""Clusters of a large change (spec 2026-10-03-large-change-boards §2).

Changed functions and fields are joined when changed code calls changed code or shares a field whose access the
change added or removed; unchanged code they have in common (a logger everyone calls) never joins them. A cluster whose
board would need more than `max_nodes` nodes is split by module, directory, file, then by its flows, with whole parts
sharing a board while they fit; clusters of fewer than `min_changed` changed functions are merged into the nearest
directory's. Every changed node and every flow ends up in exactly one cluster.
"""
from __future__ import annotations

import posixpath
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from codetortoise.detectors.base import SEVERITY_RANK, Finding
from codetortoise.impact import ImpactModel


@dataclass
class Cluster:
    members: list[str]                                # changed nodes whose home is this cluster
    flows: list[str] = field(default_factory=list)    # flow ids, each in exactly one cluster
    required: list[str] = field(default_factory=list)  # nodes its board must show (members, fields, flow nodes)
    part: tuple[int, int] | None = None               # (i, n) when one function's flows were split over n boards
    of: str | None = None                             # that function
    test: bool = False
    id: str = ""
    name: str = ""
    findings: list[str] = field(default_factory=list)
    risk: str | None = None
    level: int | None = None
    also: list[int] = field(default_factory=list)


@dataclass
class Clustering:
    clusters: list[Cluster]
    home: dict[str, str]                 # node id -> cluster id, for every node a board shows that has a home
    merged_over_limit: int = 0


class _FlowLike:                          # what clustering needs of a flow (board.Flow satisfies it)
    id: str
    path: list[str]
    cause: str | None


def cluster_change(im: ImpactModel, flows: list[_FlowLike], findings: list[Finding], *,
                   is_test: Callable[[str], bool], module_of: Callable[[str], str] | None = None,
                   max_nodes: int = 30, min_changed: int = 3, max_clusters: int = 60) -> Clustering:
    changed = [n for n in im.changed if n in im.nodes]
    chg = set(changed)
    touches: dict[str, set[str]] = defaultdict(set)          # changed function -> fields whose access changed
    for e in im.edges:
        if altered_access(e) and e.src in chg and e.dst in im.nodes:
            touches[e.src].add(e.dst)
    flows_of: dict[str, list[_FlowLike]] = defaultdict(list)
    for f in flows:
        flows_of[f.cause or f.path[-1]].append(f)

    def file_of(n: str) -> str:
        node = im.nodes[n]
        if node.file:
            return node.file
        toucher = next((t for t in sorted(touches, key=_num) if n in touches[t] and im.nodes[t].file), None)
        return im.nodes[toucher].file if toucher else ""

    def required(members: list[str], only: list[_FlowLike] | None = None, fields: bool = True) -> list[str]:
        out: dict[str, None] = dict.fromkeys(members)
        if fields:
            for m in members:
                out.update(dict.fromkeys(sorted(touches.get(m, ()), key=_num)))
        for f in (only if only is not None else [f for m in members for f in flows_of.get(m, [])]):
            out.update(dict.fromkeys(f.path))
        return list(out)

    # 1. join: changed code calling changed code, or sharing a field (test code apart)
    parent = {n: n for n in changed}

    def find(n: str) -> str:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    def union(a: str, b: str) -> None:
        if is_test(a) == is_test(b):
            parent[find(a)] = find(b)
    for e in im.edges:
        if e.kind in ("call", "virtual") and e.src in chg and e.dst in chg:
            union(e.src, e.dst)
    sharers: dict[str, list[str]] = defaultdict(list)
    for fn, fs in touches.items():
        for f in fs:
            sharers[f].append(fn)
            if f in chg:
                union(f, fn)
    for fns in sharers.values():
        for a, b in zip(fns, fns[1:], strict=False):
            union(a, b)
    groups: dict[str, list[str]] = defaultdict(list)
    for n in changed:
        groups[find(n)].append(n)

    # 2. split what doesn't fit
    root = _common_dir([file_of(m) for m in changed if file_of(m)])
    depth = len(root.split("/"))
    module = module_of or (lambda p: posixpath.dirname(p))
    keys: list[Callable[[str], str]] = [lambda n: module(file_of(n)), lambda n: posixpath.dirname(file_of(n)),
                                        file_of]

    def split(members: list[str], level: int = 0) -> list[Cluster]:
        if len(required(members)) <= max_nodes:
            return [Cluster(members=members)]
        for key in keys[level:]:
            level += 1
            parts: dict[str, list[str]] = defaultdict(list)
            for m in members:
                parts[key(m)].append(m)
            if len(parts) > 1:                               # parts under one directory share a board while they fit
                bins: list[tuple[str, list[str]]] = []
                for k, p in sorted(parts.items()):
                    up = posixpath.dirname(k)
                    joinable = key is file_of or len(up.split("/")) > depth     # never two top directories
                    if bins and bins[-1][0] == up and joinable and len(required(bins[-1][1] + p)) <= max_nodes:
                        bins[-1][1].extend(p)
                    else:
                        bins.append((up, list(p)))
                if len(bins) > 1:
                    return [c for _, b in bins for c in split(b, level)]
        packs: list[list[str]] = [[]]                        # one file: pack its functions in source order
        for m in sorted(members, key=lambda n: (im.nodes[n].line or 0, _num(n))):
            if packs[-1] and len(required(packs[-1] + [m])) > max_nodes:
                packs.append([])
            packs[-1].append(m)
        out: list[Cluster] = []
        for p in packs:
            if len(p) > 1 or len(required(p)) <= max_nodes:
                out.append(Cluster(members=p))
            else:
                out.extend(_flow_groups(p[0], flows_of.get(p[0], []), required, max_nodes))   # its board drops fields past 30
        return out

    clusters = [c for g in sorted(groups.values(), key=lambda g: _num(g[0])) for c in split(g)]
    def mem(c: Cluster) -> list[str]:
        return c.members or ([c.of] if c.of else [])
    for c in clusters:
        c.test = all(is_test(m) for m in mem(c))

    def size(c: Cluster) -> int:
        return len(c.required or required(c.members))

    def fns(c: Cluster) -> int:
        return sum(1 for m in c.members if im.nodes[m].kind == "function")

    def home_dir(c: Cluster) -> str:
        return Counter(posixpath.dirname(file_of(m)) for m in c.members).most_common(1)[0][0]

    # 3. merge small clusters into the nearest directory's below the change's root, within the node budget
    merged = True
    while merged:
        merged = False
        for small in sorted([c for c in clusters if c.part is None and fns(c) < min_changed], key=size):
            if small not in clusters:
                continue
            fits = [c for c in clusters if c is not small and c.part is None and c.test == small.test
                    and len(_shared(home_dir(c), home_dir(small))) > depth
                    and len(required(c.members + small.members)) <= max_nodes]
            if fits:                                         # the nearest directory first, then the smallest result
                into = min(fits, key=lambda c: (-len(_shared(home_dir(c), home_dir(small))),
                                                len(required(c.members + small.members)), _num(c.members[0])))
                into.members += small.members
                clusters.remove(small)
                merged = True

    # 4. too many clusters: merge the smallest that share the most directory, past the budget if need be; with too few
    #    of those, join a function's flow groups back into one cluster
    over = 0
    while len(clusters) > max_clusters:
        cands = sorted([c for c in clusters if c.part is None], key=size)
        if len(cands) < 2:
            split_fns = Counter(c.of for c in clusters if c.part is not None)
            if not split_fns:
                break
            f, n = split_fns.most_common(1)[0]
            parts = [c for c in clusters if c.part is not None and c.of == f]
            at = clusters.index(parts[0])
            clusters[at:at + 1] = [Cluster(members=[f], test=parts[0].test)]
            for c in parts[1:]:
                clusters.remove(c)
            over += n - 1
            continue
        a = cands[0]
        b = max(cands[1:], key=lambda c: (len(_shared(home_dir(a), home_dir(c))), -size(c)))
        b.members += a.members
        clusters.remove(a)
        over += 1

    # flows, required nodes, findings, risk, placement, names, order
    for c in clusters:
        if c.part is None:
            c.flows = [f.id for m in c.members for f in flows_of.get(m, [])]
            c.required = required(c.members)
    home: dict[str, str] = {}
    for c in clusters:
        for m in c.members:
            home.setdefault(m, str(id(c)))
    sev = {f.id: f.severity for f in findings}
    for f in findings:
        owner = next((c for n in f.nodes for c in clusters if n in c.members), None)
        if owner:
            owner.findings.append(f.id)
    for c in clusters:
        c.risk = max((sev[i] for i in c.findings), key=lambda s: SEVERITY_RANK.get(s, 0), default=None)
        levels = Counter(im.nodes[m].layer for m in mem(c) if im.nodes[m].layer is not None)
        c.level = levels.most_common(1)[0][0] if levels else None
        c.also = sorted((lv for lv in levels if lv != c.level), reverse=True)
        c.name = _name([file_of(m) for m in mem(c) if file_of(m)], root)
    names = Counter(c.name for c in clusters if c.part is None)
    for c in clusters:
        main = max(mem(c), key=lambda m: (len(flows_of.get(m, [])), -_num(m)))
        if c.part is not None:
            c.name += f" · {im.nodes[main].label} ({c.part[0]} of {c.part[1]})"
        elif names[c.name] > 1:
            c.name += f" · {im.nodes[main].label}"
    clusters.sort(key=lambda c: (-SEVERITY_RANK.get(c.risk or "", -1), -len(c.flows), -fns(c), c.name))
    rename = {str(id(c)): f"C{i}" for i, c in enumerate(clusters, 1)}
    for i, c in enumerate(clusters, 1):
        c.id = f"C{i}"
    home = {n: rename[k] for n, k in home.items()}
    # nodes without a cluster of their own live on a board that shows them: the one with most changed code in their
    # directory, else the first (riskiest)
    by_dir: dict[str, Counter] = defaultdict(Counter)
    for c in clusters:
        for m in c.members:
            by_dir[posixpath.dirname(file_of(m))][c.id] += 1
    shown: dict[str, list[str]] = defaultdict(list)
    for c in clusters:
        for n in c.required:
            if n not in home:
                shown[n].append(c.id)
    for n, ids in shown.items():
        near = by_dir.get(posixpath.dirname(file_of(n)), Counter()) if file_of(n) else Counter()
        home[n] = max(ids, key=lambda cid: (near[cid], -ids.index(cid)))
    return Clustering(clusters=clusters, home=home, merged_over_limit=over)


def _flow_groups(m: str, flows: list[_FlowLike], required: Callable, max_nodes: int) -> list[Cluster]:
    """One function that doesn't fit on a board: its flows in groups whose nodes fit (the function is home in the
    first). Its fields don't count here: a board leaves out the fields past its budget."""
    groups: list[list[_FlowLike]] = [[]]
    for f in flows:
        if groups[-1] and len(required([m], groups[-1] + [f], fields=False)) > max_nodes:
            groups.append([])
        groups[-1].append(f)
    n = len(groups)
    if n == 1:
        return [Cluster(members=[m])]
    return [Cluster(members=[m] if i == 0 else [], flows=[f.id for f in g], required=required([m], g), part=(i + 1, n),
                    of=m) for i, g in enumerate(groups)]


def altered_access(e) -> bool:
    """A field access the change added or removed: what joins code and what a board must show."""
    return e.kind in ("writes", "reads") and e.status != "unchanged"


def _name(files: list[str], root: str) -> str:
    """The deepest directory the files share, relative to the change's root; files under several top directories are
    named by each one's deepest shared directory ("deps/reftable + src/libgit2")."""
    rel = [f[len(root):].lstrip("/") if root and f.startswith(root + "/") else f for f in files]
    tops: dict[str, list[str]] = defaultdict(list)
    for f in rel:
        tops[f.split("/")[0] if "/" in f else ""].append(f)
    names = [_common_dir(fs) or posixpath.basename(root) or "." for _, fs in sorted(tops.items())]
    return " + ".join(names[:3]) + (" + …" if len(names) > 3 else "")


def _num(nid: str) -> int:
    return int(nid[1:]) if nid[1:].isdigit() else 0


def _common_dir(paths: list[str]) -> str:
    if not paths:
        return ""
    parts = [p.split("/")[:-1] for p in paths]
    out = []
    for segs in zip(*parts, strict=False):
        if len(set(segs)) != 1:
            break
        out.append(segs[0])
    return "/".join(out)


def _shared(a: str, b: str) -> list[str]:
    out = []
    for x, y in zip(a.split("/"), b.split("/"), strict=False):
        if x != y:
            break
        out.append(x)
    return out
