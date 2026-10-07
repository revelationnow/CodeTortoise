"""How a review reads (spec 2026-10-07-review-reading §4–§8): stories joined into threads by calls and shared data,
how the threads connect, the order to read them in, each story's contract rows and call paths, and the reviewer's
To check list. Everything here is computed from the analysis; the strong model only rewords it (llm/threads.py)."""
from __future__ import annotations

import posixpath
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import _Ctx
from codetortoise.stories import Story, StorySet

_KIND_RANK = {"calls": 0, "data": 1, "file": 2, "cl": 3}


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
