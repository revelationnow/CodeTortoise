"""How a review reads (spec 2026-10-07-review-reading §4–§8): stories joined into threads by calls and shared data,
how the threads connect, the order to read them in, each story's contract rows and call paths, and the reviewer's
To check list. Everything here is computed from the analysis; the strong model only rewords it (llm/threads.py)."""
from __future__ import annotations

import fnmatch
import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import _Ctx
from codetortoise.cparse import is_header, preproc_spans
from codetortoise.pieces import PieceSet
from codetortoise.stories import Story, StorySet

_KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}
ConnKind = Literal["caller", "vocabulary", "condition", "place", "bundled"]
_CONN_RANK = {"caller": 1, "vocabulary": 2, "condition": 3, "place": 4, "bundled": 5}
CALLER_HOPS = 3
_INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.M)


class StoryLink(BaseModel):
    """The strongest link between two stories' changed code (§4.1). `a` comes before `b` in the story list."""
    a: str
    b: str
    strength: Literal["strong", "weak"]
    kind: Literal["calls", "data", "file", "cl"]
    defines: str | None = None        # strong links: the story that changed the callee or now writes the field
    text: str
    facts: list[str] = Field(default_factory=list)   # node ids, workspace-relative paths or "CL n"


class Thread(BaseModel):
    id: str
    name: str
    purpose: str
    text_source: Literal["template", "llm"] = "template"
    stories: list[str] = Field(default_factory=list)  # in reading order
    cls: list[int] = Field(default_factory=list)
    open_checks: int = 0


class Connection(BaseModel):
    """The strongest connection between two threads (§4.3); `shown` pairs are drawn as arcs."""
    a: str
    b: str
    kind: ConnKind
    text: str
    facts: list[str] = Field(default_factory=list)   # node ids, workspace-relative paths, targets, "CL n" or authors
    shown: bool = False


def rel_path(x: _Ctx, path: str | None) -> str:
    """A workspace-relative path (§12); paths outside the workspace stay as they are."""
    if not path:
        return ""
    root = x.c.root.rstrip("/") + "/"
    return path[len(root):] if x.c.root and path.startswith(root) else path


def _home(ss: StorySet) -> dict[str, str]:
    """Changed node -> its story (a story set's `node_story` also maps the unchanged code on its flows)."""
    return {n: s.id for s in ss.stories for n in s.nodes}


def _live(x: _Ctx, kinds: set[str]):
    return [e for e in x.im.edges if e.kind in kinds and e.status != "removed"]


def _cls(cls: list[int]) -> str:
    return " and ".join(f"CL {n}" for n in cls)


def story_links(ss: StorySet, x: _Ctx) -> list[StoryLink]:
    """Every linked pair of stories with its strongest link: calls, then data (strong), then a shared file, then a
    shared CL (weak)."""
    home = _home(ss)
    order = {s.id: i for i, s in enumerate(ss.stories)}
    calls: dict[tuple[str, str], list] = defaultdict(list)   # (defines, uses) -> call edges
    for e in _live(x, {"call", "virtual"}):
        d, u = home.get(e.dst), home.get(e.src)
        if d and u and d != u:
            calls[(d, u)].append(e)
    data: dict[tuple[str, str], list] = defaultdict(list)    # (defines, uses) -> (writer, field, user)
    new_writes = [e for e in _live(x, {"writes"}) if e.status == "added"]
    users = defaultdict(list)
    for e in _live(x, {"reads", "writes"}):
        users[e.dst].append(e)
    for w in new_writes:
        d = home.get(w.src)
        for e in users[w.dst]:
            u = home.get(e.src)
            if d and u and d != u:
                data[(d, u)].append((w, e))
    files = {s.id: {rel_path(x, x.local(n)) for n in s.nodes} - {""} for s in ss.stories}
    out: list[StoryLink] = []
    for i, sa in enumerate(ss.stories):
        for sb in ss.stories[i + 1:]:
            lk = (_calls_link(sa, sb, calls, x) or _data_link(sa, sb, data, x)
                  or _weak_link(sa, sb, files))
            if lk:
                out.append(lk)
    return sorted(out, key=lambda lk: (order[lk.a], order[lk.b]))


def _pick(a: str, b: str, found: dict) -> tuple[str, str, list] | None:
    """The direction with more evidence; a tie goes to the earlier story defining."""
    ab, ba = found.get((a, b), []), found.get((b, a), [])
    if not ab and not ba:
        return None
    return (a, b, ab) if len(ab) >= len(ba) else (b, a, ba)


def _calls_link(sa: Story, sb: Story, calls: dict, x: _Ctx) -> StoryLink | None:
    got = _pick(sa.id, sb.id, calls)
    if not got:
        return None
    d, _u, edges = got
    per = defaultdict(int)
    for e in edges:
        per[e.dst] += 1
    callees = sorted(per, key=lambda n: (-per[n], x.label(n)))
    edges = sorted(edges, key=lambda e: callees.index(e.dst))
    more = f" and {len(callees) - 1} more" if len(callees) > 1 else ""
    return StoryLink(a=sa.id, b=sb.id, strength="strong", kind="calls", defines=d,
                     text=f"calls `{x.label(callees[0])}`{more}, changed in {d}",
                     facts=list(dict.fromkeys(n for e in edges for n in (e.src, e.dst))))


def _data_link(sa: Story, sb: Story, data: dict, x: _Ctx) -> StoryLink | None:
    got = _pick(sa.id, sb.id, data)
    if not got:
        return None
    d, _u, pairs = got
    w, e = pairs[0]
    verb = "reads" if e.kind == "reads" else "writes"
    return StoryLink(a=sa.id, b=sb.id, strength="strong", kind="data", defines=d,
                     text=f"{verb} `{x.label(w.dst)}`, which {d} now writes",
                     facts=list(dict.fromkeys(n for w, e in pairs for n in (w.src, w.dst, e.src))))


def _weak_link(sa: Story, sb: Story, files: dict[str, set[str]]) -> StoryLink | None:
    shared = sorted(files[sa.id] & files[sb.id])
    if shared:
        return StoryLink(a=sa.id, b=sb.id, strength="weak", kind="file", text=f"both edit `{shared[0]}`", facts=shared)
    cls = sorted(set(sa.cls) & set(sb.cls))
    if cls:
        return StoryLink(a=sa.id, b=sb.id, strength="weak", kind="cl", text=f"both arrive in {_cls(cls)}",
                         facts=[f"CL {n}" for n in cls])
    return None


# ------------------------------------------------------------------ threads (§4.2) and reading order (§4.4)
def _components(ids: list[str], strong: list[StoryLink]) -> list[list[str]]:
    parent = {i: i for i in ids}

    def find(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for lk in strong:
        parent[find(lk.a)] = find(lk.b)
    groups: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return list(groups.values())


def _topo(members: list[str], strong: list[StoryLink], size: dict[str, int], pos: dict[str, int]) -> list[str]:
    """Defines before uses; ties (and cycles) by size, larger first, then story order."""
    mine = set(members)
    indeg = {m: 0 for m in members}
    uses = defaultdict(list)
    for lk in strong:
        if lk.a in mine and lk.b in mine:
            u = lk.b if lk.defines == lk.a else lk.a
            indeg[u] += 1
            uses[lk.defines].append(u)
    out: list[str] = []
    left = set(members)
    while left:
        low = min(indeg[m] for m in left)
        ready = [m for m in left if indeg[m] == low]
        m = min(ready, key=lambda m: (-size[m], pos[m]))
        out.append(m)
        left.discard(m)
        for u in uses[m]:
            indeg[u] -= 1
    return out


def _reason(sid: str, order: list[str], strong: list[StoryLink]) -> str | None:
    """Why a story sits where it does in its thread: its best link to an earlier story, else to a later one."""
    at = {s: i for i, s in enumerate(order)}
    mine = [lk for lk in strong if sid in (lk.a, lk.b) and (lk.b if lk.a == sid else lk.a) in at]
    if not mine:
        return None

    def other(lk):
        return lk.b if lk.a == sid else lk.a

    def key(lk):
        earlier = at[other(lk)] < at[sid]
        return (not earlier, lk.defines == sid, _KIND_RANK[lk.kind], at[other(lk)])
    lk = min(mine, key=key)
    o = other(lk)
    verb = {("calls", False): "calls", ("data", False): "uses",
            ("calls", True): "called by", ("data", True): "used by"}[(lk.kind, lk.defines == sid)]
    return f"{'←' if at[o] < at[sid] else '→'} {verb} {at[o] + 1}"


def _fixed_name(story: Story, strong: list[StoryLink], x: _Ctx) -> str:
    """`main function` in its folder: the defining story's function other stories cite most, else its first."""
    cited = defaultdict(int)
    for lk in strong:
        for n in lk.facts:
            cited[n] += 1
    fns = [n for n in story.nodes if n in x.im.nodes and x.im.nodes[n].kind == "function"] or story.nodes
    if not fns:
        return story.title
    main = min(fns, key=lambda n: (-cited[n], fns.index(n)))
    folder = posixpath.dirname(rel_path(x, x.local(main)))
    return f"`{x.label(main)}` in {folder}" if folder else f"`{x.label(main)}`"


def build_threads(ss: StorySet, links: list[StoryLink], x: _Ctx,
                  open_counts: dict[str, tuple[int, int]] | None = None) -> tuple[list[Thread], dict[str, str]]:
    """Threads in reading order (by open hazards, open checks, then changed functions), each with its stories in
    reading order, and each placed story's reason. `open_counts`: story id -> (open hazards, open checks). Tests
    stories stay out."""
    open_counts = open_counts or {}
    by = {s.id: s for s in ss.stories}
    pos = {s.id: i for i, s in enumerate(ss.stories)}
    ids = [s.id for s in ss.stories if s.kind != "tests"]
    strong = [lk for lk in links if lk.strength == "strong" and lk.a in by and lk.b in by
              and by[lk.a].kind != "tests" and by[lk.b].kind != "tests"]
    size = {i: len(by[i].nodes) for i in ids}
    drafts = []
    for members in _components(ids, strong):
        order = _topo(members, strong, size, pos)
        hz = sum(open_counts.get(s, (0, 0))[0] for s in order)
        ck = sum(open_counts.get(s, (0, 0))[1] for s in order)
        drafts.append(((-hz, -ck, -sum(size[s] for s in order), pos[order[0]]), order))
    threads, reasons = [], {}
    for n, (_, order) in enumerate(sorted(drafts), 1):
        first = by[order[0]]
        threads.append(Thread(id=f"T{n}", name=_fixed_name(first, strong, x), purpose=first.summary, stories=order,
                              cls=sorted({c for s in order for c in by[s].cls})))
        for s in order[1:]:
            r = _reason(s, order, strong)
            if r:
                reasons[s] = r
    return threads, reasons


# ------------------------------------------------------------------ thread connections (§4.3)
@dataclass
class _Profile:
    """What a thread's changed code touches, for comparing threads."""
    nodes: set[str] = field(default_factory=set)
    files: set[str] = field(default_factory=set)                  # workspace-relative
    callers: dict[str, tuple[int, str]] = field(default_factory=dict)   # caller -> (hops, the changed node it reaches)
    structs: dict[str, str] = field(default_factory=dict)          # record -> a field node of it the thread touches
    names: set[str] = field(default_factory=set)                   # changed declarations it changes or uses
    includes: set[str] = field(default_factory=set)                # changed headers its files include
    targets: set[str] = field(default_factory=set)
    conds: set[str] | None = None
    cls: set[int] = field(default_factory=set)
    authors: set[str] = field(default_factory=set)


def _callers_within(x: _Ctx, start: set[str], hops: int) -> dict[str, tuple[int, str]]:
    rev: dict[str, list[str]] = defaultdict(list)
    for e in _live(x, {"call", "virtual"}):
        rev[e.dst].append(e.src)
    out: dict[str, tuple[int, str]] = {}
    frontier = [(n, n) for n in sorted(start)]
    for hop in range(1, hops + 1):
        nxt = []
        for n, origin in frontier:
            for c in rev.get(n, []):
                if c in start or c in out or x.is_test(c):
                    continue
                out[c] = (hop, origin)
                nxt.append((c, origin))
        frontier = nxt
    return out


def _profiles(threads: list[Thread], ss: StorySet, x: _Ctx, pieces: PieceSet | None) -> dict[str, _Profile]:
    by = {s.id: s for s in ss.stories}
    piece_files = {p.id: p.files for p in pieces.pieces} if pieces else {}
    users = {m.cl: m.user for m in x.c.cs.cls if m.user}
    headers = {rel_path(x, f.local) for f in x.c.cs.files if is_header(f.local)}
    decls = [(t.name, rel_path(x, t.file)) for t in x.c.dm.types]
    spans: dict[str, list[tuple[int, int, str]]] = {}
    out: dict[str, _Profile] = {}
    for t in threads:
        p = _Profile()
        for sid in t.stories:
            s = by[sid]
            p.nodes.update(s.nodes)
            p.files.update(rel_path(x, x.local(n)) for n in s.nodes)
            p.files.update(rel_path(x, f) for pid in s.pieces for f in piece_files.get(pid, []))
            p.targets.update(tg for tg in s.targets if tg != "unknown")
            p.cls.update(s.cls)
        p.files.discard("")
        p.authors = {users[c] for c in p.cls if c in users}
        fns = sorted(n for n in p.nodes if n in x.im.nodes and x.im.nodes[n].kind == "function")
        p.callers = _callers_within(x, set(fns), CALLER_HOPS)
        for e in _live(x, {"reads", "writes"}):
            if e.src in p.nodes:
                rec = x.label(e.dst).rsplit("::", 1)[0]
                p.structs.setdefault(rec, e.dst)
        bodies, conds = [], None
        for n in fns:
            key = x.im.nodes[n].key
            fn = x.fa.get(key) or x.fb.get(key)
            fc = x.texts.get(fn.file) if fn else None
            if not fn or not fc or fc.after is None:
                conds = set()
                continue
            lines = fc.after.splitlines()
            bodies.append("\n".join(lines[fn.start_line - 1:fn.end_line]))
            if fn.file not in spans:
                spans[fn.file] = preproc_spans(fn.file, fc.after)
            here = {c for lo, hi, c in spans[fn.file] if lo <= fn.start_line <= hi}
            conds = here if conds is None else conds & here
        p.conds = conds or set()
        body = "\n".join(bodies)
        p.names = {nm for nm, f in decls if f in p.files or re.search(rf"\b{re.escape(nm)}\b", body)}
        for f in p.files:
            fc = x.texts.get(x.c.root.rstrip("/") + "/" + f)
            for inc in _INCLUDE.findall(fc.after or "") if fc else []:
                p.includes.update(h for h in headers if h == inc or h.endswith("/" + inc))
        out[t.id] = p
    return out


def _is_entry(x: _Ctx, n: str) -> bool:
    return any(fnmatch.fnmatchcase(x.label(n).split("::")[-1], pat) for pat in x.c.cfg.entrypoint_patterns)


def _folder(files: set[str]) -> str:
    dirs = [posixpath.dirname(f) for f in files]
    if not dirs or any(not d for d in dirs):
        return ""
    common = posixpath.commonpath(dirs)
    return "" if common in ("", ".", "/") else common


def _connect(ta: str, tb: str, pa: _Profile, pb: _Profile, x: _Ctx, everyone: dict[str, _Profile],
             multi_target: bool) -> Connection:
    def conn(kind: ConnKind, text: str, facts: list[str]) -> Connection:
        return Connection(a=ta, b=tb, kind=kind, text=text, facts=facts)
    common = set(pa.callers) & set(pb.callers)
    if common:
        pool = [n for n in common if _is_entry(x, n)] or list(common)
        c = min(pool, key=lambda n: (max(pa.callers[n][0], pb.callers[n][0]), pa.callers[n][0] + pb.callers[n][0],
                                     x.label(n)))
        return conn("caller", f"both run inside `{x.label(c)}`", [c, pa.callers[c][1], pb.callers[c][1]])
    structs = sorted(set(pa.structs) & set(pb.structs))
    if structs:
        r = structs[0]
        return conn("vocabulary", f"both use `struct {r}`", list(dict.fromkeys([pa.structs[r], pb.structs[r]])))
    names = sorted(pa.names & pb.names)
    if names:
        f = next(f for nm, f in ((t.name, rel_path(x, t.file)) for t in x.c.dm.types) if nm == names[0])
        return conn("vocabulary", f"both use `{names[0]}`", [f])
    edited = sorted(f for f in pa.files & pb.files if is_header(f))
    if edited:
        return conn("vocabulary", f"both edit `{edited[0]}`", [edited[0]])
    incs = sorted(pa.includes & pb.includes)
    if incs:
        return conn("vocabulary", f"both include `{incs[0]}`", [incs[0]])
    if multi_target and len(pa.targets) == 1 and pa.targets == pb.targets:
        (tg,) = pa.targets
        return conn("condition", f"both build only for `{tg}`", [tg])
    conds = sorted(pa.conds & pb.conds)
    if conds:
        return conn("condition", f"both sit under `#if {conds[0]}`", sorted(pa.files | pb.files))
    folder = _folder(pa.files | pb.files)
    if folder and not any(f.startswith(folder + "/") for t, p in everyone.items() if t not in (ta, tb) for f in p.files):
        return conn("place", f"both live under `{folder}`", [folder])
    cls = sorted(pa.cls & pb.cls)
    if cls:
        return conn("bundled", f"nothing besides arriving in {_cls(cls)}", [f"CL {n}" for n in cls])
    authors = sorted(pa.authors & pb.authors)
    if authors:
        return conn("bundled", f"nothing besides their author {authors[0]}", authors[:1])
    return conn("bundled", "nothing besides arriving in this review", [])


def _depth(fa: set[str], fb: set[str]) -> int:
    """How many leading folders the nearest pair of files shares."""
    best = 0
    for a in fa:
        for b in fb:
            da, db = posixpath.dirname(a).split("/"), posixpath.dirname(b).split("/")
            n = 0
            while n < min(len(da), len(db)) and da[n] == db[n] and da[n]:
                n += 1
            best = max(best, n)
    return best


def connections(threads: list[Thread], ss: StorySet, x: _Ctx, pieces: PieceSet | None = None) -> list[Connection]:
    """The strongest connection of every pair of threads, strongest first. Shown: each pair of kinds 1–4 not already
    joined through other shown pairs of the same or a stronger kind, and for each thread with nothing but "only
    bundled", one arc to the thread nearest it by folder (ties: one sharing a CL, then an author, then the first)."""
    prof = _profiles(threads, ss, x, pieces)
    multi = len({tg for p in prof.values() for tg in p.targets}) > 1
    pos = {t.id: i for i, t in enumerate(threads)}
    out = [_connect(a.id, b.id, prof[a.id], prof[b.id], x, prof, multi)
           for i, a in enumerate(threads) for b in threads[i + 1:]]
    out.sort(key=lambda k: (_CONN_RANK[k.kind], pos[k.a], pos[k.b]))
    parent = {t.id: t.id for t in threads}

    def find(i: str) -> str:
        while parent[i] != i:
            i = parent[i]
        return i
    for k in out:
        if k.kind != "bundled" and find(k.a) != find(k.b):
            k.shown = True
            parent[find(k.a)] = find(k.b)
    joined = {t for k in out if k.kind != "bundled" for t in (k.a, k.b)}
    for t in threads:
        if t.id in joined or len(threads) < 2:
            continue
        mine = [k for k in out if t.id in (k.a, k.b)]
        best = max(mine, key=lambda k: (_depth(prof[k.a].files, prof[k.b].files), bool(prof[k.a].cls & prof[k.b].cls),
                                        bool(prof[k.a].authors & prof[k.b].authors), -pos[k.b if k.a == t.id else k.a]))
        best.shown = True
    return out
