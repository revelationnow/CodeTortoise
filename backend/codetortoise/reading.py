"""How a review reads (spec 2026-10-07-review-reading §4–§8): stories joined into threads by calls and shared data,
how the threads connect, the order to read them in, each story's contract rows and call paths, and the reviewer's
To check list. Everything here is computed from the analysis; the strong model only rewords it (llm/threads.py)."""
from __future__ import annotations

import fnmatch
import posixpath
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import BoardContext, Flow, _count, _covered, _Ctx, analyse, is_test_path
from codetortoise.cparse import is_header, preproc_spans
from codetortoise.detectors.base import SEVERITY_RANK, Finding
from codetortoise.pieces import PieceSet, node_cl
from codetortoise.stories import Story, StoryDetail, StorySet
from codetortoise.targets import UNKNOWN
from codetortoise.tidy import tidy

READING_VERSION = 1                   # bump with every change to the thread text's prompt or checks (keys its cache)
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


class ContractRow(BaseModel):
    """One line of a story's Before → after (§8.1)."""
    kind: Literal["signature", "returns", "fields", "repeated", "body"]
    text: str
    node: str | None = None
    before: str = ""
    after: str = ""
    mark: list[int] = Field(default_factory=list)    # [start, end) of the part of `after` that differs
    added: list[str] = Field(default_factory=list)   # return values now returned, fields now written
    removed: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)   # the functions it is about


class WhereFn(BaseModel):
    node: str
    label: str
    add: int = 0
    rem: int = 0
    cl: int | None = None
    line: int | None = None           # new side (old side for a removed function)


class WhereFile(BaseModel):
    path: str                         # workspace-relative
    depot: str | None = None
    functions: list[WhereFn] = Field(default_factory=list)


class CallPath(BaseModel):
    """A caller chain ending at a story's changed code (§8.2): a flow's path, or calls up to an entry point."""
    steps: list[str]                  # node ids, entry first
    labels: list[str]
    kind: Literal["contract", "state", "call"]
    entry: str | None = None          # the first step, when it is an entry point
    hidden: list[str] = Field(default_factory=list)   # folded steps (a path of more than four steps)
    text: str
    flow: str | None = None


CheckKind = Literal["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask", "cleared"]
CHECK_ORDER = ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask", "cleared"]


class Reason(BaseModel):
    kind: CheckKind
    text: str


class Check(BaseModel):
    """One row of To check (§7): a place the reviewer should look at, and why."""
    key: str                          # kind|file|function|related changed function's qualified name (no line numbers),
                                      # a finding's row adds |kind:title, a repeat at one key #2, #3 in line order
    kind: CheckKind
    story: str | None = None
    thread: str | None = None
    path: str = ""                    # workspace-relative
    depot: str | None = None          # the file the side panel opens
    line: int | None = None
    function: str | None = None
    node: str | None = None           # the place's function
    text: str
    source_line: str = ""
    finding: str | None = None
    cites: list[str] = Field(default_factory=list)
    also: list[Reason] = Field(default_factory=list)   # other kinds at the same place


class Headline(BaseModel):
    text: str
    tone: Literal["hazard", "confirm", "none"]
    rules_only: bool = False


class BuildImpact(BaseModel):
    header: str                       # workspace-relative
    text: str
    files: int
    finding: str | None = None
    note: str = ""


class TestsRow(BaseModel):
    """The overview's Tests row (§5.1): which threads the change's tests exercise."""
    stories: list[str] = Field(default_factory=list)
    functions: int = 0
    covers: list[str] = Field(default_factory=list)
    untested: list[str] = Field(default_factory=list)


class StoryReading(BaseModel):
    story: str
    contracts: list[ContractRow] = Field(default_factory=list)
    where: list[WhereFile] = Field(default_factory=list)
    paths: list[CallPath] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    place_text: str = ""              # its place in its thread: "Uses what story 1 adds."
    thread: str | None = None
    position: int | None = None       # 1-based, within its thread


class Reading(BaseModel):
    whole: str = ""
    whole_source: Literal["template", "llm"] = "template"
    threads: list[Thread] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    order: list[str] = Field(default_factory=list)            # story ids, tests last
    reasons: dict[str, str] = Field(default_factory=dict)
    links: list[StoryLink] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    cleared: list[Check] = Field(default_factory=list)        # findings judged no hazard
    build_impact: list[BuildImpact] = Field(default_factory=list)
    coverage: list[str] = Field(default_factory=list)
    headline: Headline = Field(default_factory=lambda: Headline(text="No risks found", tone="none", rules_only=True))
    rules_only: bool = True
    tests: TestsRow | None = None


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


# ------------------------------------------------------------------ contract rows (§8.1), where (§6.1), paths (§8.2)
_IDENT = re.compile(r"\w")


def _differ(before: str, after: str) -> tuple[str, str, int, int]:
    """The differing middle of two signatures, widened to whole words: (old part, new part, start, end in after)."""
    i = 0
    while i < min(len(before), len(after)) and before[i] == after[i]:
        i += 1
    j = 0
    while j < min(len(before), len(after)) - i and before[-1 - j] == after[-1 - j]:
        j += 1
    while i > 0 and _IDENT.match(after[i - 1]) and (i < len(after) - j and _IDENT.match(after[i])
                                                    or i < len(before) - j and _IDENT.match(before[i])):
        i -= 1
    while j > 0 and _IDENT.match(after[-j]) and (len(after) - j > i and _IDENT.match(after[-j - 1])
                                                 or len(before) - j > i and _IDENT.match(before[-j - 1])):
        j -= 1
    return before[i:len(before) - j], after[i:len(after) - j], i, len(after) - j


def _vals(fn, vals) -> list[str]:
    return [f"{fn.return_names[v]} ({v})" if v in fn.return_names else v for v in vals]


def _story_fns(story: Story, x: _Ctx) -> list[str]:
    return [n for n in story.nodes if n in x.im.nodes and x.im.nodes[n].kind == "function"]


def contract_rows(story: Story, x: _Ctx) -> list[ContractRow]:
    """Signatures (one row per repeated signature edit), return values, field writes, a mechanical story's repeated
    edit, then the functions changed only inside their body."""
    fns = _story_fns(story, x)
    if story.kind == "mechanical":
        subs = [story.sub] if story.sub else story.subs
        sites = story.counts.get("sites", 0)
        return [ContractRow(kind="repeated", nodes=fns,
                            text=f"`{old}` → `{new}`" + (f" at {sites} sites" if len(subs) == 1 and sites else ""))
                for old, new in subs]
    sigs, singles, rets, flds, body = defaultdict(list), [], [], [], []
    for n in fns:
        key, label = x.im.nodes[n].key, x.label(n)
        fb, fa = x.fb.get(key), x.fa.get(key)
        touched = False
        if fb is None or fa is None:
            singles.append(ContractRow(kind="signature", node=n, nodes=[n], before=fb.signature if fb else "",
                                       after=fa.signature if fa else "", text=f"`{label}` {'added' if fb is None else 'removed'}"))
            continue
        if fb.signature != fa.signature:
            old, new, i, j = _differ(fb.signature, fa.signature)
            sigs[(old.strip(" ,;"), new.strip(" ,;"))].append((n, fb.signature, fa.signature, [i, j]))
            touched = True
        added, removed = [v for v in fa.returns if v not in fb.returns], [v for v in fb.returns if v not in fa.returns]
        if added or removed:
            parts = ([f"can now return {', '.join(_vals(fa, added))}"] if added else []) + \
                    ([f"no longer returns {', '.join(_vals(fb, removed))}"] if removed else [])
            rets.append(ContractRow(kind="returns", node=n, nodes=[n], added=_vals(fa, added), removed=_vals(fb, removed),
                                    text=f"`{label}` " + "; ".join(parts)))
            touched = True
        writes = [e for e in x.im.edges if e.src == n and e.kind == "writes" and e.status in ("added", "removed")]
        now = [x.label(e.dst) for e in writes if e.status == "added"]
        gone = [x.label(e.dst) for e in writes if e.status == "removed"]
        if now or gone:
            parts = ([f"now writes {', '.join(f'`{f}`' for f in now)}"] if now else []) + \
                    ([f"no longer writes {', '.join(f'`{f}`' for f in gone)}"] if gone else [])
            flds.append(ContractRow(kind="fields", node=n, nodes=[n], added=now, removed=gone,
                                    text=f"`{label}` " + "; ".join(parts)))
            touched = True
        if not touched:
            body.append(n)
    repeated = []
    for (old, new), got in sigs.items():
        what = f"gained `{new}`" if not old else f"lost `{old}`" if not new else f"`{old}` → `{new}`"
        if len(got) >= 2:
            repeated.append(ContractRow(kind="repeated", nodes=[g[0] for g in got],
                                        text=f"{len(got)} signatures {'changed ' if old and new else ''}{what}"))
        else:
            n, b, a, mark = got[0]
            singles.insert(0, ContractRow(kind="signature", node=n, nodes=[n], before=b, after=a, mark=mark,
                                          text=f"`{x.label(n)}`: {what}"))
    rows = repeated + singles + rets + flds
    if body:
        rows.append(ContractRow(kind="body", nodes=body, text=f"{len(body)} function{'s' if len(body) > 1 else ''} "
                                                             "changed only inside the body"))
    return rows


def where(story: Story, x: _Ctx) -> list[WhereFile]:
    """The story's files (workspace-relative, in path order), each with its changed functions, edit sizes and CL."""
    files: dict[str, WhereFile] = {}
    for n in _story_fns(story, x):
        key = x.im.nodes[n].key
        fb, fa = x.fb.get(key), x.fa.get(key)
        fn = fa or fb
        local = x.local(n)
        if not fn or not local:
            continue
        fc = x.texts.get(local)
        if fa is not None and fc is not None:
            add, rem = _count(fc.before, fc.after, fa.start_line, fa.end_line)
        else:
            add, rem = 0, fn.end_line - fn.start_line + 1
        wf = files.setdefault(local, WhereFile(path=rel_path(x, local), depot=fc.depot if fc else None))
        wf.functions.append(WhereFn(node=n, label=x.label(n), add=add, rem=rem, cl=node_cl(x, n), line=fn.start_line))
    for wf in files.values():
        wf.functions.sort(key=lambda f: (f.line or 0, f.label))
    return sorted(files.values(), key=lambda f: f.path)


def _change_text(x: _Ctx, n: str) -> str:
    """What changed in a function, as the end of "calls `f`, …"."""
    key = x.im.nodes[n].key
    fb, fa = x.fb.get(key), x.fa.get(key)
    if fb is None:
        return "which is new"
    if fa is None:
        return "which was removed"
    if fb.signature != fa.signature:
        return "whose signature changed"
    added = [v for v in fa.returns if v not in fb.returns]
    if added:
        return f"which can now return {', '.join(_vals(fa, added))}"
    now = [x.label(e.dst) for e in x.im.edges if e.src == n and e.kind == "writes" and e.status == "added"]
    if now:
        return f"which now writes `{now[0]}`"
    return "whose body changed"


def _path(steps: list[str], kind: str, x: _Ctx, text: str, flow: str | None = None) -> CallPath:
    return CallPath(steps=steps, labels=[x.label(n) for n in steps], kind=kind,
                    entry=steps[0] if _is_entry(x, steps[0]) else None,
                    hidden=steps[1:-2] if len(steps) > 4 else [], text=text, flow=flow)


def call_paths(story: Story, x: _Ctx, flows: list[Flow]) -> list[CallPath]:
    """Every path ending at the story's changed functions, uncapped: its flows first (their effect is the line), then
    caller chains up to an entry point, a function nobody calls or `blast_hops` calls away, entry points first. Every
    caller and every call between callers lies on a path, also where callers share a caller."""
    mine = [f for f in flows if f.id in story.flows]
    out = [_path(list(f.path), f.tag, x, f.effect, f.id) for f in mine]
    seen = {tuple(p.steps) for p in out}
    seeds = set(_story_fns(story, x))
    rev: dict[str, list[str]] = defaultdict(list)
    for e in _live(x, {"call", "virtual"}):
        if not x.is_test(e.src):
            rev[e.dst].append(e.src)
    hops = x.c.cfg.blast_hops
    layer = dict.fromkeys(seeds, 0)
    down: dict[str, list[str]] = defaultdict(list)     # a caller's callees one hop nearer the change
    frontier, starts, order = sorted(seeds), set(), []
    for hop in range(1, hops + 1):
        nxt = []
        for n in frontier:
            for c in sorted(set(rev.get(n, [])), key=lambda m: x.label(m)):
                if layer.get(c, hop) != hop:
                    continue
                down[c].append(n)
                order.append((c, n))
                if c in layer:
                    continue
                layer[c] = hop
                if _is_entry(x, c) or not rev.get(c) or hop == hops:
                    starts.add(c)
                else:
                    nxt.append(c)
        frontier = nxt
    up: dict[str, list[str]] = defaultdict(list)
    for c, n in order:
        up[n].append(c)
    used: set[tuple[str, str]] = set()

    def pick(options: list[str], edge) -> str:
        return next((o for o in options if edge(o) not in used), options[0])

    calls = []
    for c, n in [(c, None) for c, _ in order if c in starts] + order:
        if n is not None and (c, n) in used:
            continue
        steps = [c]
        while steps[0] not in starts and up.get(steps[0]):
            steps.insert(0, pick(up[steps[0]], lambda o: (o, steps[0])))
        if n is not None:
            steps.append(n)
        while steps[-1] not in seeds:
            steps.append(pick(down[steps[-1]], lambda o: (steps[-1], o)))
        used.update(zip(steps, steps[1:]))
        if tuple(steps) not in seen:
            seen.add(tuple(steps))
            calls.append(_path(steps, "call", x, f"calls `{x.label(steps[-1])}`, {_change_text(x, steps[-1])}"))
    calls.sort(key=lambda p: (p.entry is None, len(p.steps), p.labels))
    return out + calls


# ------------------------------------------------------------------ To check (§7)
def _qual(x: _Ctx, n: str) -> str:
    key = x.im.nodes[n].key
    fn = x.fa.get(key) or x.fb.get(key)
    return fn.qualname if fn else x.label(n)


def _source(x: _Ctx, path: str | None, line: int | None, read_text: Callable[[str], str | None] | None) -> str:
    if not path or not line:
        return ""
    fc = x.texts.get(path)
    text = fc.after if fc else (read_text(path) if read_text else None) or ""
    rows = text.splitlines()
    return rows[line - 1].strip() if 0 < line <= len(rows) else ""


def _def_place(x: _Ctx, n: str) -> tuple[str | None, int | None]:
    key = x.im.nodes[n].key
    fn = x.fa.get(key) or x.fb.get(key)
    return (fn.file, fn.start_line) if fn else (x.local(n), x.im.nodes[n].line)


def _cmp_text(c) -> str:
    return ", ".join(c.compared_names.get(v[2:], v[2:]) if v.startswith("==") else v for v in c.compared)


def build_checks(ss: StorySet, threads: list[Thread], conns: list[Connection], x: _Ctx,
                 targets: dict[str, list[str]] | None = None, has_tests: bool = False,
                 test_callers: Callable[[str], set[str]] | None = None,
                 includers: Callable[[str], set[str]] | None = None,
                 read_text: Callable[[str], str | None] | None = None) -> tuple[list[Check], list[Check]]:
    """The review's To check rows in kind order (§7.1), rows at one place merged, and the findings judged no hazard.
    `targets` maps local files to build targets (None: one target); `has_tests`: the workspace has test code;
    `test_callers` gives the test files calling a name (the symbol index); `includers` the files including a header."""
    findings = x.c.findings
    thread_of = {s: t.id for t in threads for s in t.stories}
    home = _home(ss)
    rows: list[Check] = []

    def add(kind: str, related: str | None, place: str | None, path: str | None, line: int | None, text: str,
            story: str | None = None, **kw) -> None:
        func = x.label(place) if place else None
        story = story if story is not None else (home.get(related) if related else None)
        rows.append(Check(key=f"{kind}|{rel_path(x, path)}|{func or ''}|{_qual(x, related) if related else kw.pop('rel', '')}",
                          kind=kind, story=story, thread=thread_of.get(story) if story else kw.pop("thread", None),
                          path=rel_path(x, path), line=line, function=func, node=place, text=tidy(text),
                          source_line=_source(x, path, line, read_text), **kw))

    # 1–2: the strong model's verdicts; without one, high and medium findings (not header fan-out) to confirm
    cleared: list[Check] = []
    for f in findings:
        n = next((m for m in f.nodes if m in x.im.nodes and x.im.nodes[m].kind == "function"), None)
        ev = next((e for e in f.evidence if e.file and e.line), None)
        path, line = (ev.file, ev.line) if ev else (_def_place(x, n) if n else (None, None))
        story = ss.finding_story.get(f.id)
        common = dict(story=story, finding=f.id, cites=f.verdict_cites)
        if f.verdict == "hazard":
            add("hazard", n, n, path, line, f.verdict_reason or f.title, **common)
        elif f.verdict == "needs_review":
            add("confirm", n, n, path, line, f.verdict_reason or f.title, **common)
        elif f.verdict == "no_hazard":
            add("cleared", n, n, path, line, f.verdict_reason or f.title, **common)
        elif f.severity in ("high", "medium") and f.kind != "header_fanout":
            add("confirm", n, n, path, line, f.title, **common)
        else:
            continue
        rows[-1].key += f"|{f.kind}:{f.title}"     # the finding's own identity: its id is renumbered on a re-run
        if f.verdict == "no_hazard":
            cleared.append(rows.pop())

    def tg(path: str | None) -> set[str]:
        return set((targets or {}).get(path or "", [])) or {UNKNOWN}

    changed = [n for s in ss.stories for n in _story_fns(s, x)]
    for n in changed:
        key, callee = x.im.nodes[n].key, x.label(n)
        fb, fa = x.fb.get(key), x.fa.get(key)
        if not fb or not fa:
            continue
        sig = fb.signature != fa.signature
        new = [v for v in fa.returns if v not in fb.returns]
        mine = tg(fa.file)
        for c in sorted((c for c in x.calls_after if c.callee == key), key=lambda c: (c.file, c.line)):
            caller = x.id_of.get(c.caller)
            if not caller or x.is_test_path(caller):
                continue
            who = x.label(caller)
            if sig or new:
                where_ = tg(c.file)
                if targets is not None and where_ == {UNKNOWN} and mine != {UNKNOWN}:
                    add("unanalysed", n, caller, c.file, c.line, f"`{who}` calls `{callee}` from a file outside every "
                                                                  "compile database")
                    continue
                if targets is not None and UNKNOWN not in where_ | mine and not where_ & mine:
                    add("target", n, caller, c.file, c.line,
                        f"`{who}` calls `{callee}` but is built only for {', '.join(f'`{t}`' for t in sorted(where_))}")
                    continue
            if sig and caller not in x.changed:
                add("caller", n, caller, c.file, c.line, f"`{who}` calls `{callee}` and was not updated for its new "
                                                         "signature")
            if new:
                vals = ", ".join(_vals(fa, new))
                if not c.result_used:
                    add("result", n, caller, c.file, c.line, f"`{who}` ignores the result of `{callee}`, which can now "
                                                             f"return {vals}")
                elif c.compared and not _covered(c.compared, new):
                    add("result", n, caller, c.file, c.line, f"`{who}` compares the result of `{callee}` only with "
                                                             f"{_cmp_text(c)}; it can now return {vals}")
    # 5: unchanged readers of fields the change now writes
    for n in changed:
        for w in (e for e in x.im.edges if e.src == n and e.kind == "writes" and e.status == "added"):
            for r in sorted({e.src for e in _live(x, {"reads"}) if e.dst == w.dst}, key=lambda m: x.label(m)):
                if r in x.changed or x.is_test_path(r):
                    continue
                acc = next((a for a in x.fields_after if f"field:{a.field}" == x.im.nodes[w.dst].key
                            and a.fn == x.im.nodes[r].key and a.mode == "read"), None)
                path, line = (acc.file, acc.line) if acc else _def_place(x, r)
                add("reader", n, r, path, line, f"`{x.label(r)}` reads `{x.label(w.dst)}`, which `{x.label(n)}` now writes")
    # 6: a changed header included only by files of another target
    if targets is not None and includers is not None:
        mine = {t for f in x.c.cs.files if not is_header(f.local) for t in targets.get(f.local, [])} - {UNKNOWN}
        for h in sorted(f.local for f in x.c.cs.files if is_header(f.local)):
            other: dict[str, list[str]] = defaultdict(list)
            for inc in sorted(includers(h)):
                where_ = set(targets.get(inc, [])) - {UNKNOWN}
                if mine and where_ and not where_ & mine:
                    other[", ".join(f"`{t}`" for t in sorted(where_))].append(inc)
            for names, files in other.items():
                add("target", None, None, files[0], None,
                    f"`{rel_path(x, h)}` is included by {len(files)} file{'s' if len(files) > 1 else ''} built only for "
                    f"{names}", rel=rel_path(x, h))
    # 7: changed functions no test calls or mentions (only when the workspace has test code)
    if has_tests:
        mentions = "\n".join(f.after for f in x.c.cs.files if is_test_path(rel_path(x, f.local)))
        for s in ss.stories:
            if s.kind == "tests":
                continue
            for n in _story_fns(s, x):
                if x.is_test_path(n) or n not in x.changed:
                    continue
                name = x.label(n).split("::")[-1]
                by_test = any(x.is_test_path(e.src) for e in _live(x, {"call", "virtual"}) if e.dst == n)
                if by_test or re.search(rf"\b{re.escape(name)}\b", mentions) or (test_callers and test_callers(name)):
                    continue
                add("untested", n, n, *_def_place(x, n), f"No test calls `{x.label(n)}`")
    # 8: callers found by name over the fan-in cap
    for name, skipped in sorted(x.im.capped.items()):
        n = next((m for m in changed if x.label(m) == name or x.label(m).split("::")[-1] == name), None)
        if n:
            add("unanalysed", n, n, *_def_place(x, n), f"{skipped} callers of `{x.label(n)}` found by name were not checked")
    # 9: threads tied to the rest only by their bundle
    lone = [t for t in threads if not any(k.kind != "bundled" and t.id in (k.a, k.b) for k in conns)]
    by = {s.id: s for s in ss.stories}
    for t in lone:
        if t is threads[0] and len(lone) == len(threads):
            continue
        k = next((k for k in conns if k.shown and t.id in (k.a, k.b)), None) or \
            next((k for k in conns if t.id in (k.a, k.b)), None)
        fns = _story_fns(by[t.stories[0]], x)
        add("ask", None, None, None, None, "Ask the author how this thread relates to the rest of the change"
            + (f": {k.text}" if k else ""), thread=t.id, rel=_qual(x, fns[0]) if fns else t.name)
    return _unique(_merge(rows)), _unique(cleared)


def _merge(rows: list[Check]) -> list[Check]:
    """One row per place: the first kind leads, the others become its `also`; then kind order, then place. Rows of
    findings stay apart (each has its own verdict)."""
    rank = {k: i for i, k in enumerate(CHECK_ORDER)}
    rows = sorted(rows, key=lambda k: (rank[k.kind], k.path, k.line or 0))
    out: list[Check] = []
    at: dict[tuple, Check] = {}
    for k in rows:
        place = (k.path, k.line, k.function) if k.path and k.line and not k.finding else None
        if place and place in at:
            lead = at[place]
            if all(r.text != k.text for r in lead.also) and lead.text != k.text:
                lead.also.append(Reason(kind=k.kind, text=k.text))
            continue
        if place:
            at[place] = k
        out.append(k)
    return out


def _unique(rows: list[Check]) -> list[Check]:
    """Each key once (§7.4), so a mark or comment reaches one row: a repeat of a key (another call site in one caller,
    two findings alike at one function) gets #2, #3 in line order."""
    seen: Counter[str] = Counter()
    for k in rows:
        seen[k.key] += 1
        if seen[k.key] > 1:
            k.key = f"{k.key}#{seen[k.key]}"
    return rows


# ------------------------------------------------------------------ headline (§5.4), build impact and coverage (§5.2)
def _n(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else plural or word + 's'}"


def headline(checks: list[Check], marked: set[str], findings: list[Finding]) -> Headline:
    """What to act on: open hazards, else open checks to confirm, else none. Without the strong model's verdicts, the
    top severity of the findings not marked, labelled rules only. Build impact never raises it."""
    rules_only = not any(f.verdict_source == "tier1" for f in findings)
    open_ = [k for k in checks if k.key not in marked]
    if not rules_only:
        hz = sum(k.kind == "hazard" for k in open_)
        cf = sum(k.kind == "confirm" for k in open_)
        if hz:
            return Headline(text=_n(hz, "hazard"), tone="hazard")
        if cf:
            return Headline(text=f"{cf} to confirm", tone="confirm")
        return Headline(text="No hazards found", tone="none")
    done = {k.finding for k in checks if k.finding and k.key in marked}
    sev = [f.severity for f in findings if f.kind != "header_fanout" and f.id not in done]
    top = max(sev, key=lambda v: SEVERITY_RANK.get(v, 0), default=None)
    if top is None:
        return Headline(text="No risks found", tone="none", rules_only=True)
    tone = "hazard" if top == "high" else "confirm" if top == "medium" else "none"
    return Headline(text=f"{top.capitalize()} risk", tone=tone, rules_only=True)


def build_impact(x: _Ctx) -> list[BuildImpact]:
    """Header fan-out findings as "`common.h` macro change → 713 files rebuild"."""
    tus = {fo.header: fo.total_tus for fo in x.im.fanout}
    out = []
    for f in x.c.findings:
        if f.kind != "header_fanout":
            continue
        header = next((e.file for e in f.evidence if e.file), None)
        if not header:
            continue
        kinds = {t.kind.split("_")[0] for t in x.c.dm.types if t.file == header}
        what = {"macro": "macro change", "type": "type change", "decl": "declaration change"}.get(
            next(iter(kinds)), "change") if len(kinds) == 1 else "header change"
        n = tus.get(header, 0)
        out.append(BuildImpact(header=rel_path(x, header), files=n, finding=f.id,
                               text=f"`{rel_path(x, header)}` {what} → {_n(n, 'file')} rebuild{'s' if n == 1 else ''}",
                               note="No behaviour change found." if f.verdict == "no_hazard" else ""))
    return sorted(out, key=lambda b: -b.files)


def coverage(x: _Ctx, has_tests: bool, outside: int = 0) -> list[str]:
    """What the analysis could not see fully (§5.2, §7.5); empty counts are left out."""
    facts = x.c.before + x.c.after
    degraded = {f.tu.file for f in facts if f.tu.confidence == "degraded" and f.tu.extractor == "clang"}
    added = sum(f.tu.supplemented for f in facts)
    fallback = {f.tu.file for f in facts if f.tu.extractor == "treesitter"}
    out = []
    if degraded:
        out.append(f"{_n(len(degraded), 'file')} parsed with errors"
                   + (f"; tree-sitter added {_n(added, 'call')} or field accesses" if added else ""))
    if fallback:
        out.append(f"{_n(len(fallback), 'file')} read by tree-sitter only")
    for name, n in sorted(x.im.capped.items()):
        out.append(f"{n} callers of `{name}` found by name were not checked (more than {x.c.cfg.heuristic_fanin_cap})")
    if outside:
        out.append(f"{_n(outside, 'file')} with callers {'is' if outside == 1 else 'are'} outside every compile database")
    if x.c.cs.drift:
        d = len(x.c.cs.drift)
        out.append(f"{_n(d, 'file')} in the workspace {'differs' if d == 1 else 'differ'} from the CL base")
    if not has_tests:
        out.append("No test code found in the workspace")
    return out


# ------------------------------------------------------------------ the whole reading
def _stories_text(ps: list[int]) -> str:
    nums = [str(p) for p in ps]
    return ("story " if len(nums) == 1 else "stories ") + (nums[0] if len(nums) == 1 else
                                                          ", ".join(nums[:-1]) + " and " + nums[-1])


def _place_text(sid: str, order: list[str], strong: list[StoryLink]) -> str:
    at = {s: i + 1 for i, s in enumerate(order)}
    uses = sorted({at[lk.defines] for lk in strong if sid in (lk.a, lk.b) and lk.defines != sid and lk.defines in at})
    built = sorted({at[lk.b if lk.a == sid else lk.a] for lk in strong if lk.defines == sid
                    and (lk.b if lk.a == sid else lk.a) in at})
    parts = ([f"Uses what {_stories_text(uses)} adds"] if uses else []) + \
            ([f"{_stories_text(built)} build{'s' if len(built) == 1 else ''} on this"] if built else [])
    text = "; ".join(parts)
    return (text[0].upper() + text[1:] + ".") if text else ""


def fixed_whole(threads: list[Thread], conns: list[Connection]) -> str:
    """The change as a whole without the strong model (§9): the threads and their strongest shown connections."""
    if not threads:
        return "No changed code to read."
    if len(threads) == 1:
        return f"One thread: {threads[0].name}."
    letter = {t.id: chr(ord("A") + i) if i < 26 else t.id for i, t in enumerate(threads)}
    parts = [f"{letter[k.a]} and {letter[k.b]}: {k.text}" for k in conns if k.shown]
    return f"{len(threads)} threads" + (": " + "; ".join(parts) if parts else "") + "."


def _tests_row(ss: StorySet, threads: list[Thread], x: _Ctx) -> TestsRow | None:
    tests = [s for s in ss.stories if s.kind == "tests"]
    if not tests:
        return None
    thread_of = {s: t.id for t in threads for s in t.stories}
    nodes = {n for s in tests for n in s.nodes}
    home = _home(ss)
    covered = {thread_of[home[e.dst]] for e in _live(x, {"call", "virtual"})
               if e.src in nodes and home.get(e.dst) in thread_of}
    return TestsRow(stories=[s.id for s in tests], functions=len(nodes),
                    covers=[t.id for t in threads if t.id in covered], untested=[t.id for t in threads if t.id not in covered])


def _set_depots(c: BoardContext, checks: list[Check]) -> None:
    """Each check's depot file, which its Open button shows in the side panel (§7.2)."""
    root = c.root.rstrip("/")
    local = {k.path: k.path if k.path.startswith("/") or not root else f"{root}/{k.path}" for k in checks if k.path}
    depots = c.depots_for(sorted(set(local.values()))) if local else {}
    for k in checks:
        k.depot = depots.get(local.get(k.path, ""))


def build_reading(ss: StorySet, c: BoardContext, details: dict[str, StoryDetail] | None = None, analysis=None,
                  pieces: PieceSet | None = None, targets: dict[str, list[str]] | None = None, has_tests: bool = False,
                  test_callers: Callable[[str], set[str]] | None = None, includers: Callable[[str], set[str]] | None = None,
                  read_text: Callable[[str], str | None] | None = None) -> tuple[Reading, dict[str, StoryReading]]:
    """The review's reading (threads, connections, order, To check, build impact, coverage, headline) and each story's
    tiles, with fixed text; llm/threads.py may reword the thread names, purposes and the whole."""
    a = analysis or analyse(c)
    x = a.x
    links = story_links(ss, x)

    def checks_for(threads):
        conns = connections(threads, ss, x, pieces)
        return conns, build_checks(ss, threads, conns, x, targets=targets, has_tests=has_tests, test_callers=test_callers,
                                   includers=includers, read_text=read_text)
    first, _ = build_threads(ss, links, x)
    _, (rows, _) = checks_for(first)
    lead = {t.id: t.stories[0] for t in first}
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for k in rows:
        sid = k.story or lead.get(k.thread or "")
        if sid and k.kind != "ask":               # how a thread relates to the rest is no reason to read it sooner
            counts[sid][0] += k.kind == "hazard"
            counts[sid][1] += 1
    threads, reasons = build_threads(ss, links, x, {s: (h, n) for s, (h, n) in counts.items()})
    conns, (rows, cleared) = checks_for(threads)
    for t in threads:
        t.open_checks = sum(1 for k in rows if k.thread == t.id)
    _set_depots(c, rows + cleared)
    strong = [lk for lk in links if lk.strength == "strong"]
    order = [s for t in threads for s in t.stories] + [s.id for s in ss.stories if s.kind == "tests"]
    outside = 0
    if targets is not None:
        outside = len({cl.file for cl in x.calls_after if not targets.get(cl.file) and cl.file not in x.texts})
    reading = Reading(threads=threads, connections=conns, order=order, reasons=reasons, links=links, checks=rows,
                      cleared=cleared, build_impact=build_impact(x), coverage=coverage(x, has_tests, outside),
                      headline=headline(rows, set(), x.c.findings),
                      rules_only=not any(f.verdict_source == "tier1" for f in x.c.findings),
                      tests=_tests_row(ss, threads, x), whole=fixed_whole(threads, conns))
    thread_of = {s: t for t in threads for s in t.stories}
    per: dict[str, StoryReading] = {}
    for s in ss.stories:
        t = thread_of.get(s.id)
        flows = details[s.id].board.flows if details and s.id in details else a.flows
        per[s.id] = StoryReading(story=s.id, contracts=contract_rows(s, x), where=where(s, x), paths=call_paths(s, x, flows),
                                 checks=[k for k in rows if k.story == s.id],
                                 place_text=_place_text(s.id, t.stories, strong) if t else "",
                                 thread=t.id if t else None, position=t.stories.index(s.id) + 1 if t else None)
    return reading, per


def with_marks(r: Reading, marks: dict[str, dict], findings: list[Finding]) -> dict:
    """The reading as viewers see it (§7.4): each mark with `changed` when the source line at its place is no longer the
    line it was marked at (the check is open again), and the headline and threads' open counts without the marked
    checks."""
    line = {k.key: k.source_line for k in r.checks + r.cleared}
    view = {key: {**m, "changed": m["source_line"] != line.get(key, m["source_line"])}
            for key, m in marks.items() if key in line}
    marked = {key for key, m in view.items() if not m["changed"]}
    out = r.model_dump()
    out["marks"] = view
    out["headline"] = headline(r.checks, marked, findings).model_dump()
    for t in out["threads"]:
        t["open_checks"] = sum(1 for k in r.checks if k.thread == t["id"] and k.key not in marked)
    return out
