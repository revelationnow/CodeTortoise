"""The change cut into pieces, the links between them, a card per piece and an overview of the change (spec
2026-10-05-two-tier-stories §3). Rules only, no AI: both tiers start from these.

A piece is a few changed nodes that are almost never wrong to keep together; pieces never span two targets or two CLs.
Cut in order, each node going to the first piece that takes it: repeated edits, tests, new code with its direct
callers, connected edits (at most 2 hops wide), declarations (one per changed header and CL), singles. Ids P1… follow
target, CL, first file and first line, so the same change always gives the same pieces.
"""
from __future__ import annotations

import posixpath
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import Analysis, BoardContext, _count, _Ctx, _opcodes
from codetortoise.clusters import altered_access
from codetortoise.cparse import is_header
from codetortoise.repeated import Repeated, _note, _plural, _spans, find_repeated
from codetortoise.targets import UNKNOWN

PieceKind = Literal["tests", "repeated", "new", "edits", "declarations", "single"]
LinkType = Literal["call", "field", "sub", "uses", "name"]
CARD_CHARS = 1200                     # 300 tokens
OVERVIEW_CHARS = 6000                 # 1500 tokens
CL_CHARS = 2400                       # a CL description in the overview: 600 tokens
MAX_HOPS = 2
_KIND_TEXT = {"tests": "tests", "new": "new code", "edits": "connected edits", "declarations": "declarations",
              "single": "single change"}


class Piece(BaseModel):
    id: str
    kind: PieceKind
    targets: list[str]
    shared: bool = False              # code built for more than one target
    cl: int | None = None
    nodes: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)   # canonical local paths
    sub: list[str] | None = None      # a repeated edit: [old, new]
    names: list[str] = Field(default_factory=list)   # declarations: the changed macros, types and declarations
    card: str = ""


class PieceLink(BaseModel):
    a: str
    b: str
    type: LinkType
    count: int


class PieceSet(BaseModel):
    pieces: list[Piece] = Field(default_factory=list)
    links: list[PieceLink] = Field(default_factory=list)
    targets: dict[str, list[str]] = Field(default_factory=dict)    # local file -> its targets
    node_piece: dict[str, str] = Field(default_factory=dict)
    overview: str = ""

    def piece(self, pid: str) -> Piece | None:
        return next((p for p in self.pieces if p.id == pid), None)

    def links_of(self, pid: str) -> list[PieceLink]:
        return [lk for lk in self.links if pid in (lk.a, lk.b)]


def _nk(nid: str) -> tuple:
    """Node ids in number order: N3 before N12."""
    return (int(nid[1:]), nid) if nid[1:].isdigit() else (1 << 30, nid)


def _rel(x: _Ctx, path: str) -> str:
    root = x.c.root.rstrip("/") + "/"
    return path[len(root):] if x.c.root and path.startswith(root) else path


def node_cl(x: _Ctx, nid: str) -> int | None:
    """The CL that changed a node: its file's only CL, else the CL whose own diff adds (or, for a removed function,
    deletes) most of the function's lines; ties and no match go to the lowest CL."""
    local = x.local(nid) or ""
    fc = x.texts.get(local)
    cls = [p.cl for p in fc.per_cl] if fc else []
    if not cls:
        return x.c.cs.cls[0].cl if x.c.cs.cls else None
    if len(cls) == 1:
        return cls[0]
    n = x.im.nodes[nid]
    fa, fb = x.fa.get(n.key), x.fb.get(n.key)
    side, fn = ("after", fa) if fa else ("before", fb)
    if fn is None:
        return min(cls)
    text = fc.after if side == "after" else fc.before
    want = {ln.strip() for ln in text.splitlines()[fn.start_line - 1:fn.end_line] if len(ln.strip()) >= 4}

    def score(p) -> int:
        a, b = p.before.splitlines(), p.after.splitlines()
        hit = 0
        for tag, i1, i2, j1, j2 in _opcodes(p.before, p.after):
            if tag == "equal":
                continue
            rows = b[j1:j2] if side == "after" else a[i1:i2]
            hit += sum(1 for r in rows if r.strip() in want)
        return hit
    best = max(sorted(fc.per_cl, key=lambda p: p.cl), key=score)
    return best.cl if score(best) else min(cls)


def _name_cl(fc, name: str) -> int | None:
    """The first CL whose own diff touches a line naming `name` (a header's macro, type or declaration)."""
    word = re.compile(rf"\b{re.escape(name.split()[-1])}\b")
    for p in sorted(fc.per_cl, key=lambda p: p.cl):
        a, b = p.before.splitlines(), p.after.splitlines()
        for tag, i1, i2, j1, j2 in _opcodes(p.before, p.after):
            if tag != "equal" and any(word.search(r) for r in a[i1:i2] + b[j1:j2]):
                return p.cl
    return min((p.cl for p in fc.per_cl), default=None)


def _components(nodes: list[str], adj: dict[str, Counter]) -> list[list[str]]:
    seen: set[str] = set()
    out = []
    pool = set(nodes)
    for n in sorted(nodes, key=_nk):
        if n in seen:
            continue
        comp, stack = [], [n]
        seen.add(n)
        while stack:
            m = stack.pop()
            comp.append(m)
            for k in adj[m]:
                if k in pool and k not in seen:
                    seen.add(k)
                    stack.append(k)
        out.append(sorted(comp, key=_nk))
    return out


def _diameter(comp: list[str], adj: dict[str, Counter]) -> int:
    pool, best = set(comp), 0
    for s in comp:
        dist, frontier = {s: 0}, [s]
        while frontier:
            nxt = []
            for m in frontier:
                for k in adj[m]:
                    if k in pool and k not in dist:
                        dist[k] = dist[m] + 1
                        nxt.append(k)
            frontier = nxt
        best = max(best, max(dist.values()))
    return best


def _cut(nodes: list[str], adj: dict[str, Counter]) -> list[list[str]]:
    """Connected groups at most MAX_HOPS wide: a wider one loses its weakest link (fewest calls and shared fields;
    ties at the lowest node ids) until it splits narrow enough."""
    local = {n: Counter({k: w for k, w in adj[n].items() if k in set(nodes)}) for n in nodes}
    local = defaultdict(Counter, local)
    out, todo = [], _components(nodes, local)
    while todo:
        comp = todo.pop(0)
        if _diameter(comp, local) <= MAX_HOPS:
            out.append(comp)
            continue
        a, b = min(((a, b) for a in comp for b in local[a] if _nk(a) < _nk(b)),
                   key=lambda e: (local[e[0]][e[1]], _nk(e[0]), _nk(e[1])))
        del local[a][b], local[b][a]
        todo = _components(comp, local) + todo
    return out


def _fn_text(x: _Ctx, nid: str) -> str:
    n = x.im.nodes[nid]
    fn = x.fa.get(n.key) or x.fb.get(n.key)
    fc = x.texts.get(fn.file) if fn else None
    if fn is None or fc is None:
        return ""
    text = fc.after if n.key in x.fa else fc.before
    return "\n".join(text.splitlines()[fn.start_line - 1:fn.end_line])


def _fn_lines(x: _Ctx, nid: str) -> tuple[int, int]:
    """(+added, −removed) lines of a changed function."""
    n = x.im.nodes[nid]
    fa, fb = x.fa.get(n.key), x.fb.get(n.key)
    if fa and not fb:
        return fa.end_line - fa.start_line + 1, 0
    if fb and not fa:
        return 0, fb.end_line - fb.start_line + 1
    add = rem = 0
    for fc, _, (a0, a1) in _spans(x, nid):
        a, r = _count(fc.before, fc.after, a0, a1)
        add, rem = add + a, rem + r
    return add, rem


_SPLIT = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")


def _prefix(label: str) -> str | None:
    """A function's first two name tokens (`reftable_stack_add` -> `reftable stack`), None for shorter names."""
    toks = [t.lower() for t in _SPLIT.split(label.split("::")[-1]) if t]
    return " ".join(toks[:2]) if len(toks) >= 2 else None


def build_pieces(c: BoardContext, a: Analysis, targets: dict[str, list[str]],
                 includers: Callable[[str], set[str]] | None = None, rep: Repeated | None = None) -> PieceSet:
    """Cut the change into pieces, link them and write their cards and the change overview. `targets` maps local files
    to their targets (targets.resolve_targets); `includers` (a header's transitive includers) narrows `uses` links."""
    x = a.x
    im = x.im
    rep = rep or find_repeated(c, x)
    changed = [n for n in im.changed if n in im.nodes and im.nodes[n].kind == "function"]

    def tkey(nid: str) -> tuple[str, ...]:
        return tuple(targets.get(x.local(nid) or "") or [UNKNOWN])
    cl_of = {n: node_cl(x, n) for n in changed}
    taken: set[str] = set()
    drafts: list[dict] = []

    def add(kind: str, nodes: list[str], **extra) -> None:
        nodes = sorted(nodes, key=_nk)
        taken.update(nodes)
        drafts.append({"kind": kind, "nodes": nodes, "targets": list(tkey(nodes[0])), "cl": cl_of[nodes[0]], **extra})

    # adjacency among changed functions: direct calls and shared changed fields
    adj: dict[str, Counter] = defaultdict(Counter)
    for e in im.edges:
        if e.kind in ("call", "virtual") and e.src in cl_of and e.dst in cl_of and e.src != e.dst:
            adj[e.src][e.dst] += 1
            adj[e.dst][e.src] += 1
    by_field: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if altered_access(e) and e.src in cl_of:
            by_field[e.dst].add(e.src)
    for fns in by_field.values():
        for f in fns:
            for g in fns - {f}:
                adj[f][g] += 1

    # 1. repeated edits, by substitution, target and CL (a test with the edit is one of its sites)
    groups: dict[tuple, list[str]] = defaultdict(list)
    for n in changed:
        if n in rep.mech_of:
            s = rep.mech_of[n]
            groups[(s.old, s.new, tkey(n), cl_of[n])].append(n)
    for (old, new, _, _), nodes in groups.items():
        add("repeated", nodes, sub=[old, new])
    # 2. tests, by target, CL and directory; test code causing a flow is cut with the code it changes
    causes = {fl.cause or fl.path[-1] for fl in a.flows}
    groups = defaultdict(list)
    for n in changed:
        if n not in taken and n not in causes and x.is_test_path(n):
            groups[(tkey(n), cl_of[n], posixpath.dirname(x.local(n) or ""))].append(n)
    for nodes in groups.values():
        add("tests", nodes)
    # 3. new code with the changed functions calling into it, within a target and CL
    added = [n for n in changed if n not in taken and im.nodes[n].key in x.fa and im.nodes[n].key not in x.fb]
    groups = defaultdict(list)
    for n in added:
        groups[(tkey(n), cl_of[n])].append(n)
    calls: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if e.kind in ("call", "virtual"):
            calls[e.src].add(e.dst)
    for key, nodes in groups.items():
        comps = _components(nodes, adj)
        callers: dict[int, list[str]] = defaultdict(list)
        for m in changed:
            if m in taken or m in added or (tkey(m), cl_of[m]) != key:
                continue
            hit = next((i for i, comp in enumerate(comps) if calls[m] & set(comp)), None)   # the first group it calls
            if hit is not None:
                callers[hit].append(m)
        for i, comp in enumerate(comps):
            add("new", comp + callers[i])
    # 4. connected edits within a target, CL and directory, at most 2 hops wide; one function alone is a single
    groups = defaultdict(list)
    for n in changed:
        if n not in taken:
            groups[(tkey(n), cl_of[n], posixpath.dirname(x.local(n) or ""))].append(n)
    for nodes in groups.values():
        for comp in _cut(nodes, adj):
            add("edits" if len(comp) > 1 else "single", comp)
    # 5. declarations: each changed header's macros, types and declarations, per CL
    decl: dict[tuple[str, int | None], list[str]] = defaultdict(list)
    for t in c.dm.types:
        if is_header(t.file):
            fc = x.texts.get(t.file)
            cl = (_name_cl(fc, t.name) if fc and fc.per_cl else (c.cs.cls[0].cl if c.cs.cls else None))
            decl[(t.file, cl)].append(t.name)
    for (header, cl), names in decl.items():
        drafts.append({"kind": "declarations", "nodes": [], "targets": targets.get(header) or [UNKNOWN], "cl": cl,
                       "files": [header], "names": sorted(set(names))})

    # ids in a fixed order: target, CL, first file, first line
    for d in drafts:
        d.setdefault("files", sorted({x.local(n) for n in d["nodes"] if x.local(n)}))

    def order(d: dict) -> tuple:
        first = d["files"][0] if d["files"] else ""
        line = min((im.nodes[n].line or 0 for n in d["nodes"] if x.local(n) == first), default=0)
        return (",".join(d["targets"]), d["cl"] or 0, first, line, d["kind"], [_nk(n) for n in d["nodes"]])
    drafts.sort(key=order)
    pieces = [Piece(id=f"P{i + 1}", kind=d["kind"], targets=d["targets"], shared=len(d["targets"]) > 1, cl=d["cl"],
                    nodes=d["nodes"], files=d["files"], sub=d.get("sub"), names=d.get("names", []))
              for i, d in enumerate(drafts)]
    node_piece = {n: p.id for p in pieces for n in p.nodes}
    links = _links(x, pieces, node_piece, rep, includers)
    ps = PieceSet(pieces=pieces, links=links, targets={f: targets.get(f) or [UNKNOWN] for f in
                                                       {f for p in pieces for f in p.files}}, node_piece=node_piece)
    for p in pieces:
        p.card = _card(x, p, ps, a, rep)
    ps.overview = change_overview(c, x, ps.targets)
    return ps


def _links(x: _Ctx, pieces: list[Piece], node_piece: dict[str, str], rep: Repeated,
           includers: Callable[[str], set[str]] | None) -> list[PieceLink]:
    im = x.im
    rank = {p.id: i for i, p in enumerate(pieces)}
    counts: Counter = Counter()

    def link(p: str, q: str, typ: str, k: int = 1) -> None:
        if p != q and k:
            a, b = sorted((p, q), key=rank.get)
            counts[(a, b, typ)] += k
    for e in im.edges:
        if e.kind in ("call", "virtual") and e.src in node_piece and e.dst in node_piece:
            link(node_piece[e.src], node_piece[e.dst], "call")
    by_field: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if altered_access(e) and e.src in node_piece:
            by_field[e.dst].add(node_piece[e.src])
    for ps in by_field.values():
        for p in ps:
            for q in ps:
                if rank[p] < rank[q]:
                    link(p, q, "field")
    for s in sorted(rep.mech_subs, key=lambda s: (s.old, s.new)):
        holders = sorted({node_piece[n] for n, sites in rep.fn_sites.items() if n in node_piece
                          and any(st.sub == s for st in sites)}, key=rank.get)
        for i, p in enumerate(holders):
            for q in holders[i + 1:]:
                link(p, q, "sub")
    texts = {n: _fn_text(x, n) for n in node_piece}
    for d in (p for p in pieces if p.kind == "declarations"):
        words = [re.compile(rf"\b{re.escape(n.split()[-1])}\b") for n in d.names]
        inc = includers(d.files[0]) if includers else None
        for p in pieces:
            if p.kind == "declarations" or (inc is not None and not (set(p.files) & inc) and d.files[0] not in p.files):
                continue
            link(d.id, p.id, "uses", sum(1 for n in p.nodes if any(w.search(texts[n]) for w in words)))
    by_prefix: dict[str, Counter] = defaultdict(Counter)
    for n, pid in node_piece.items():
        pre = _prefix(x.label(n))
        if pre:
            by_prefix[pre][pid] += 1
    for cnt in by_prefix.values():
        ids = sorted(cnt, key=rank.get)
        for i, p in enumerate(ids):
            for q in ids[i + 1:]:
                link(p, q, "name", cnt[p] * cnt[q])
    return [PieceLink(a=a, b=b, type=t, count=k)
            for (a, b, t), k in sorted(counts.items(), key=lambda kv: (rank[kv[0][0]], rank[kv[0][1]], kv[0][2]))]


def _cl_line(x: _Ctx, cl: int | None) -> str:
    if cl is None:
        return "no CL"
    meta = next((m for m in x.c.cs.cls if m.cl == cl), None)
    first = (meta.description.strip().splitlines() or [""])[0].strip() if meta else ""
    return f'CL {cl} "{first[:60]}"' if first else f"CL {cl}"


def _card(x: _Ctx, p: Piece, ps: PieceSet, a: Analysis, rep: Repeated) -> str:
    """What the strong model sees of a piece, in a fixed field order, at most CARD_CHARS."""
    im = x.im
    kind = (f"repeated edit `{p.sub[0]}` → `{p.sub[1]}`" if p.kind == "repeated" and p.sub else _KIND_TEXT[p.kind])
    tgt = f"target {p.targets[0]}" if len(p.targets) == 1 else f"targets {', '.join(p.targets)} (shared)"
    head = f"{p.id}  {kind} · {tgt} · {_cl_line(x, p.cl)}"
    lines = {n: _fn_lines(x, n) for n in p.nodes}
    files = []
    for f in p.files:
        fc = x.texts.get(f)
        if p.kind == "declarations" and fc:
            add, rem = _count(fc.before, fc.after)
        else:
            add = sum(lines[n][0] for n in p.nodes if x.local(n) == f)
            rem = sum(lines[n][1] for n in p.nodes if x.local(n) == f)
        files.append(f"{_rel(x, f)} (+{add} new)" if fc and fc.action in ("add", "branch", "move/add") and not fc.before
                     else f"{_rel(x, f)} (+{add} −{rem})")
    if p.kind == "declarations":
        fns = "changed: " + ", ".join(p.names[:8]) + (f" +{len(p.names) - 8} more" if len(p.names) > 8 else "")
    else:
        top = sorted(p.nodes, key=lambda n: (-sum(lines[n]), _nk(n)))
        notes = [f"{x.label(n)}: {_note(x, n, rep.mech_of, rep.fn_sites, rep.mech_subs)}" for n in top[:5]]
        fns = "functions: " + "; ".join(notes) + (f"; +{len(top) - 5} more" if len(top) > 5 else "")
    mine = set(p.nodes)
    flows = [f"{fl.id} {' → '.join(im.nodes[n].label for n in fl.path if n in im.nodes)} ({fl.tag})"
             for fl in a.flows if (fl.cause or fl.path[-1]) in mine]
    finds = [f"{f.id} ({f.kind}, {f.title[:60]})" for f in x.c.findings
             if set(f.nodes) & mine or (p.kind == "declarations" and any(e.file in p.files for e in f.evidence))]
    links = sorted(ps.links_of(p.id), key=lambda lk: (-lk.count, lk.b if lk.a == p.id else lk.a, lk.type))
    lk_text = " · ".join(f"→ {lk.b if lk.a == p.id else lk.a} {lk.type} ×{lk.count}" for lk in links[:6])
    text = "\n".join([head, "files: " + ", ".join(files), fns,
                      f"flows: {'; '.join(flows) or '—'} · findings: {'; '.join(finds) or '—'}",
                      f"links: {lk_text or '—'}"])
    return text if len(text) <= CARD_CHARS else text[:CARD_CHARS - 1] + "…"


def change_overview(c: BoardContext, x: _Ctx, targets: dict[str, list[str]], limit: int = OVERVIEW_CHARS) -> str:
    """Each CL with its description, then per target the changed files, lines and a directory map (as deep as fits);
    shared files once, with their targets."""
    files = [f for f in c.cs.files if f.local]
    stats = {f.local: _count(f.before, f.after) for f in files}
    new = {f.local for f in files if not f.before}
    total_add, total_rem = sum(s[0] for s in stats.values()), sum(s[1] for s in stats.values())
    head = [f"CHANGE: {_plural(len(c.cs.cls), 'CL')}, {_plural(len(files), 'file')}, +{total_add} −{total_rem} lines"]
    for m in c.cs.cls:
        desc = m.description.strip()
        desc = desc if len(desc) <= CL_CHARS else desc[:CL_CHARS - 1] + "…"
        head.append(f"CL {m.cl} ({m.status}{', ' + m.user if m.user else ''}): {desc or '(no description)'}")
    tg = {f.local: targets.get(f.local) or [UNKNOWN] for f in files}
    shared = sorted(f for f, t in tg.items() if len(t) > 1)
    by_target: dict[str, list[str]] = defaultdict(list)
    for f, t in tg.items():
        if len(t) == 1:
            by_target[t[0]].append(f)

    def render(depth: int) -> list[str]:
        out = []
        for t in sorted(by_target):
            fs = by_target[t]
            add, rem = sum(stats[f][0] for f in fs), sum(stats[f][1] for f in fs)
            fresh = sum(stats[f][0] for f in fs if f in new)
            out.append(f"TARGET {t}: {_plural(len(fs), 'file')}, +{add} −{rem}" + (f" (+{fresh} in new files)" if fresh else ""))
            dirs: dict[str, list[str]] = defaultdict(list)
            for f in fs:
                d = posixpath.dirname(_rel(x, f))
                dirs["/".join(d.split("/")[:depth]) or "."].append(f)
            for d in sorted(dirs):
                out.append(f"  {d}: {_plural(len(dirs[d]), 'file')}, +{sum(stats[f][0] for f in dirs[d])} "
                           f"−{sum(stats[f][1] for f in dirs[d])}")
        if shared:
            out.append("SHARED FILES")
            out += [f"  {_rel(x, f)}: {', '.join(tg[f])} (+{stats[f][0]} −{stats[f][1]})" for f in shared]
        return out
    room = limit - len("\n".join(head)) - 1
    for depth in (4, 3, 2, 1):
        body = render(depth)
        if len("\n".join(body)) <= room:
            break
    text = "\n".join(head + body)
    return text if len(text) <= limit else text[:limit - 1] + "…"
