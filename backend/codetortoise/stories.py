"""A review told as a few stories (spec 2026-10-04-change-stories §2–§3).

Mechanical stories are repeated edits (one substitution in at least two functions). Behaviour stories start from the
changed functions that cause flows (and from the flows of a repeated edit); the rest of the changed code joins the
nearest of them, or forms "Other changes" by connection. Changed test code forms one Tests story. Each story keeps a
board of every node it mentions (for its steps and code) and a graph of at most `story_graph_nodes` nodes.
"""
from __future__ import annotations

import posixpath
from collections import Counter, defaultdict, deque
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import (
    About,
    Board,
    BoardContext,
    BoardNode,
    Flow,
    Impact,
    StructField,
    _count,
    _Ctx,
    _neighbours,
    _render,
    about_for,
    build_about,
    build_flows,
    build_impacts,
    is_test_path,
)
from codetortoise.clusters import _shared, altered_access, cluster_change
from codetortoise.detectors.base import SEVERITY_RANK
from codetortoise.impact import ImpactModel
from codetortoise.substitutions import Site, Sub, changed_pairs

Kind = Literal["behaviour", "other", "mechanical", "tests"]
RISK = {3: "high", 2: "medium", 1: "low"}
NEIGHBOURS = 4                                               # unchanged code a story graph shows beside its own


class StoryRef(BaseModel):
    node: str
    label: str
    story: str | None = None


class StoryFunction(BaseModel):
    """A changed function of a story: what changed, in a few words, and how it relates to other stories."""
    node: str
    label: str
    note: str
    on_flow: bool = False
    also: list[str] = Field(default_factory=list)          # mechanical stories whose edit it also has
    calls: list[StoryRef] = Field(default_factory=list)    # a test: the changed code it calls


class StorySite(BaseModel):
    """One line of a repeated edit."""
    path: str | None                  # depot path
    line: int                         # new side
    function: str | None = None       # its function's label (None: outside functions)
    node: str | None = None
    before: str
    after: str
    test: bool = False
    effect: str | None = None         # the story of the flows its function causes
    other_edits: str | None = None    # its function has other edits too: the story it belongs to


class Story(BaseModel):
    id: str
    kind: Kind
    title: str
    summary: str
    text_source: Literal["template", "llm"] = "template"
    risk: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    nodes: list[str] = Field(default_factory=list)          # changed code whose home is this story
    flows: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    board: str | None = None                                # the cluster board holding its cause (None: one board)
    sub: list[str] | None = None                            # a mechanical story: [old, new]
    subs: list[list[str]] = Field(default_factory=list)     # "N more repeated edits": each substitution
    collapsed: bool = False                                 # a behaviour story past the list's limit


class StoryDetail(BaseModel):
    story: Story
    board: Board                                            # every node the story mentions, for steps and code
    graph: Board | None = None                              # at most story_graph_nodes nodes
    functions: list[StoryFunction] = Field(default_factory=list)
    sites: list[StorySite] = Field(default_factory=list)
    also_in: list[StoryRef] = Field(default_factory=list)   # a mechanical story: functions with other edits too


class StorySet(BaseModel):
    summary: str
    stories: list[Story] = Field(default_factory=list)
    node_story: dict[str, str] = Field(default_factory=dict)
    flow_story: dict[str, str] = Field(default_factory=dict)
    finding_story: dict[str, str] = Field(default_factory=dict)


def _q(s: str) -> str:
    return f"`{s}`"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


class _Draft:
    """A story while it is being built."""

    def __init__(self, kind: Kind, members: list[str] | None = None, flows: list[Flow] | None = None,
                 sub: Sub | None = None, cause: str | None = None):
        self.kind, self.members, self.flows, self.sub, self.cause = kind, list(members or []), list(flows or []), sub, cause
        self.findings: list[str] = []
        self.sites: list[tuple[Site, str, str | None]] = []   # (site, local file, node)
        self.subs: list[Sub] = []
        self.name = ""
        self.collapsed = False

    def rank(self, sev: dict[str, str]) -> tuple:
        f = max((SEVERITY_RANK.get(sev.get(i, "info"), 0) for i in self.findings), default=0)
        fl = max((SEVERITY_RANK.get(x.severity, 0) for x in self.flows), default=0)
        return (-f, -fl, -len(self.flows), -len(self.members))

    def risk(self, sev: dict[str, str]) -> str | None:
        top = max([SEVERITY_RANK.get(sev.get(i, "info"), 0) for i in self.findings]
                  + [SEVERITY_RANK.get(x.severity, 0) for x in self.flows], default=0)
        return RISK.get(top)


def build_stories(c: BoardContext, home: dict[str, str] | None = None) -> tuple[StorySet, dict[str, StoryDetail]]:
    """The review's stories and each story's detail. `home` maps nodes to the cluster boards holding them."""
    x = _Ctx(c)
    impacts = build_impacts(x)
    flows = build_flows(x, impacts)
    im, cfg = x.im, c.cfg
    sev = {f.id: f.severity for f in c.findings}
    changed = [n for n in im.changed if n in im.nodes]
    is_test = x.is_test_path

    # 1. substitutions: in each changed function, and outside functions
    fn_sites: dict[str, list[Site]] = {}
    fn_explained: dict[str, bool] = {}
    for nid in changed:
        if im.nodes[nid].kind != "function":
            continue
        spans = _spans(x, nid)
        if not spans:
            continue
        all_sites, unexplained = [], 0
        for fc, (b0, b1), (a0, a1) in spans:
            sites, u = changed_pairs(fc.before.splitlines()[b0 - 1:b1], fc.after.splitlines()[a0 - 1:a1])
            all_sites += [Site(s.sub, s.before_line + b0 - 1, s.after_line + a0 - 1, s.before, s.after) for s in sites]
            unexplained += u
        fn_sites[nid] = all_sites
        fn_explained[nid] = bool(all_sites) and not unexplained
    outside: list[tuple[Site, str]] = []
    for fc in c.cs.files:
        if fc.action != "edit":
            continue
        inside_a = [(f.start_line, f.end_line) for fx in c.after for f in fx.functions if f.file == fc.local]
        inside_b = [(f.start_line, f.end_line) for fx in c.before for f in fx.functions if f.file == fc.local]
        sites, _ = changed_pairs(fc.before.splitlines(), fc.after.splitlines())
        for s in sites:
            if not any(lo <= s.after_line <= hi for lo, hi in inside_a) and not any(lo <= s.before_line <= hi
                                                                                   for lo, hi in inside_b):
                outside.append((s, fc.local))

    fns_of: dict[Sub, set[str]] = defaultdict(set)
    for nid, sites in fn_sites.items():
        if fn_explained[nid]:
            for s in sites:
                fns_of[s.sub].add(nid)
    count: Counter[Sub] = Counter(s.sub for sites in fn_sites.values() for s in sites)
    count.update(s.sub for s, _ in outside)
    mech_subs = {s for s, fns in fns_of.items() if len(fns) >= 2}
    mech_of: dict[str, Sub] = {}                              # mechanical function -> its story's substitution
    for nid, sites in fn_sites.items():
        subs = {s.sub for s in sites}
        if fn_explained[nid] and subs <= mech_subs:
            mech_of[nid] = max(subs, key=lambda s: (count[s], s.old, s.new))

    mech = {s: _Draft("mechanical", sub=s) for s in sorted(mech_subs, key=lambda s: (-count[s], s.old, s.new))}
    for nid, s in mech_of.items():
        mech[s].members.append(nid)
    for nid, sites in fn_sites.items():
        for s in sites:
            if s.sub in mech:
                mech[s.sub].sites.append((s, x.local(nid) or "", nid))
    for s, local in outside:
        if s.sub in mech:
            mech[s.sub].sites.append((s, local, None))

    # 2. behaviour seeds: a flow-causing function's flows; a repeated edit's flows
    seeds: dict[object, _Draft] = {}
    for fl in flows:
        cause = fl.cause or fl.path[-1]
        key = ("mech", mech_of[cause]) if cause in mech_of else ("cause", cause)
        if key not in seeds:
            seeds[key] = (_Draft("behaviour", sub=key[1]) if key[0] == "mech"
                          else _Draft("behaviour", members=[cause], cause=cause))
        seeds[key].flows.append(fl)
        if key[0] == "mech" and cause not in seeds[key].members:
            seeds[key].members.append(cause)
    for d in seeds.values():
        d.findings = sorted({f for fl in d.flows for f in fl.findings})
    taken: set[str] = set()                                   # a finding on two seeds' flows goes with the riskier
    for d in sorted(seeds.values(), key=lambda d: d.rank(sev)):
        d.findings = [f for f in d.findings if f not in taken]
        taken |= set(d.findings)

    # 3. join the rest of the changed code to the nearest seed; "Other changes" for what no seed reaches
    seeded = {d.cause for d in seeds.values() if d.cause}
    tests = [n for n in changed if is_test(n) and n not in mech_of and n not in seeded]   # test code causing a flow: its story
    rest = [n for n in changed if n not in mech_of and n not in seeded and n not in tests]
    walk = set(rest) | seeded
    adj: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if e.kind in ("call", "virtual") and e.src in walk and e.dst in walk:
            adj[e.src].add(e.dst)
            adj[e.dst].add(e.src)
    by_field: dict[str, set[str]] = defaultdict(set)
    for e in im.edges:
        if altered_access(e) and e.src in walk:
            by_field[e.dst].add(e.src)
    for fns in by_field.values():
        for a in fns:
            adj[a] |= fns - {a}
    seed_list = sorted((d for d in seeds.values() if d.cause), key=lambda d: d.rank(sev))
    best: dict[str, tuple[int, int]] = {}                   # node -> (hops, seed index)
    queue = deque()
    for i, d in enumerate(seed_list):
        best[d.cause] = (0, i)
        queue.append(d.cause)
    while queue:
        n = queue.popleft()
        hops, i = best[n]
        for m in sorted(adj[n]):
            if m not in best or (hops + 1, i) < best[m]:
                if m not in best:
                    queue.append(m)
                best[m] = (hops + 1, i)
    for n in rest:
        if n in best:
            seed_list[best[n][1]].members.append(n)
    unreached = [n for n in rest if n not in best]
    others: list[_Draft] = []
    if unreached:
        sub_im = ImpactModel(nodes=im.nodes, edges=im.edges, changed=unreached, blast=[])
        res = cluster_change(sub_im, [], [], is_test=lambda _: False, module_of=x.module_of, max_nodes=cfg.board_max_nodes,
                             min_changed=cfg.cluster_min_changed, max_clusters=10 ** 6)     # split as boards are
        for cl in res.clusters:
            others.append(_Draft("other", members=list(cl.members)))
    test_story = _Draft("tests", members=tests) if tests else None

    behaviour = list(seeds.values())
    drafts = behaviour + others + list(mech.values()) + ([test_story] if test_story else [])
    node_draft: dict[str, _Draft] = {n: d for d in drafts if d.kind != "behaviour" or d.cause for n in d.members}
    for nid, s in mech_of.items():
        node_draft[nid] = mech[s]

    # 4. findings: the story of their flow, else of their first node with a story
    flow_draft = {fl.id: d for d in behaviour for fl in d.flows}
    taken = {f for d in behaviour for f in d.findings}
    for f in c.findings:
        if f.id in taken:
            continue
        d = next((flow_draft[fl.id] for fl in flows if f.id in fl.findings and fl.id in flow_draft), None)
        for n in f.nodes:
            if d is not None:
                break
            if n in node_draft:
                d = node_draft[n]
            elif n in im.nodes and im.nodes[n].kind == "field":
                d = next((node_draft[e.src] for e in im.edges if e.dst == n and altered_access(e) and e.src in node_draft),
                         None)
        d = d or (drafts[0] if drafts else None)
        if d is not None:
            d.findings.append(f.id)

    # 5. order and the list's limit
    behaviour.sort(key=lambda d: d.rank(sev))
    others.sort(key=lambda d: d.rank(sev))
    mechs = list(mech.values())
    cap = cfg.max_stories

    def total() -> int:
        return len(behaviour) + len(others) + len(mechs) + (1 if test_story else 0)

    def home_dir(d: _Draft) -> str:
        return Counter(posixpath.dirname(x.local(m) or "") for m in d.members).most_common(1)[0][0]

    while total() > cap and len(others) > 1:                 # the least risky "Other changes" merge by directory
        small = others.pop()
        into = max(others, key=lambda o: (len(_shared(home_dir(o), home_dir(small))), -others.index(o)))
        into.members += small.members
        into.findings += small.findings
    if total() > cap and len(mechs) > 1:                     # the smallest repeated edits fold into one story
        keep = max(1, len(mechs) - (total() - cap) - 1)
        folded = _Draft("mechanical")
        for d in mechs[keep:]:
            folded.members += d.members
            folded.sites += d.sites
            folded.findings += d.findings
            folded.subs.append(d.sub)
        mechs = mechs[:keep] + [folded]
    if total() > cap:                                        # behaviour stories are never merged: collapse the rest
        room = max(0, cap - (total() - len(behaviour)) - 1)  # "N more behaviour stories" is one entry too
        for d in behaviour[room:]:
            d.collapsed = True

    for d in others:                                         # "in <directory>"; alike ones add their first function
        d.name = _dir_name(x, d.members, c.root)
    alike = Counter(d.name for d in others)
    for d in others:
        if alike[d.name] > 1:
            d.name += f" ({_q(x.label(d.members[0]))})"
    ordered = behaviour + others + mechs + ([test_story] if test_story else [])
    ids = {id(d): f"S{i + 1}" for i, d in enumerate(ordered)}

    # 6. the stories, their boards and graphs
    all_locals = set()
    for d in ordered:
        all_locals |= ({x.local(n) for n in _mentioned(d)} | {i.path for i in impacts if i.node in _mentioned(d)}
                       | {loc for _, loc, _ in d.sites})                # a repeated edit's sites outside functions too
    depots = c.depots_for(sorted(p for p in all_locals if p))
    about = build_about(c)
    node_story: dict[str, str] = {}
    for d in ordered:
        for n in d.members:
            node_story.setdefault(n, ids[id(d)])
    for nid, s in mech_of.items():
        node_story[nid] = ids[id(next(d for d in mechs if s == d.sub or s in d.subs))]
    for d in behaviour:
        for fl in d.flows:
            for n in fl.path:
                node_story.setdefault(n, ids[id(d)])
    effect_of = {d.sub: ids[id(d)] for d in behaviour if d.sub is not None}
    for d in behaviour:
        for fl in d.flows:
            if fl.cause in mech_of:
                effect_of.setdefault(fl.cause, ids[id(d)])

    stories, details = [], {}
    changed_lines = sum(max(_count(f.before, f.after)) for f in c.cs.files)   # added and deleted files too
    for d in ordered:
        sid = ids[id(d)]
        st = _story(x, d, sid, sev, home, depots, is_test, effect_of)
        stories.append(st)
        details[sid] = _detail(x, d, st, impacts, depots, about, cfg.story_graph_nodes, node_story, mech_of, ids, mechs,
                               fn_sites, effect_of, is_test)
    summary = _summary(mechs, behaviour, others, test_story, changed_lines)
    flow_story = {fl.id: ids[id(d)] for d in behaviour for fl in d.flows}
    finding_story = {f: ids[id(d)] for d in ordered for f in d.findings}
    return StorySet(summary=summary, stories=stories, node_story=node_story, flow_story=flow_story,
                    finding_story=finding_story), details


def _spans(x: _Ctx, nid: str) -> list[tuple]:
    """A changed function's (file, before lines, after lines), from the diff map: a function defined twice in one file
    (under #ifdef) is the definition that changed, not the first the facts list."""
    n = x.im.nodes[nid]
    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
    if fb is None or fa is None:
        return []
    texts = {f.local: f for f in x.c.cs.files}
    out = [(texts[d.file], d.before_lines, d.after_lines) for d in x.c.dm.functions
           if d.qualname == fa.qualname and d.file in (fa.file, fb.file) and d.before_lines and d.after_lines
           and d.file in texts]
    own = [o for o in out if o[2][0] <= fa.start_line <= o[2][1]]     # overloads share a name: each reads its own span
    out = own or out
    if not out and fa.file in texts:
        out = [(texts[fa.file], (fb.start_line, fb.end_line), (fa.start_line, fa.end_line))]
    return out


def _test_file(x: _Ctx, local: str) -> bool:
    """Test code by its workspace-relative path, as functions are (`is_test_path`)."""
    root = x.c.root.rstrip("/") + "/"
    return is_test_path(local[len(root):] if x.c.root and local.startswith(root) else local)


def _mentioned(d: _Draft) -> list[str]:
    out = dict.fromkeys(d.members)
    for fl in d.flows:
        out.update(dict.fromkeys(fl.path))
    return list(out)


def _dir_name(x: _Ctx, members: list[str], root: str) -> str:
    """Their common directory, workspace-relative; code spread over the workspace is named by its main directories."""
    r = root.rstrip("/") + "/"
    dirs = [posixpath.dirname(x.local(m) or "") for m in members]
    rel = [(d + "/")[len(r):].rstrip("/") for d in dirs if (d + "/").startswith(r)]
    common = posixpath.commonpath(rel) if rel and len(rel) == len(dirs) and all(rel) else ""
    if rel and len(rel) == len(dirs) and not any(rel):
        return _q("the workspace root")
    if common:
        return _q(common)
    top = [d or "the workspace root" for d, _ in Counter(rel).most_common()]     # never an absolute path
    if not top:
        return "the workspace"
    return ", ".join(_q(d) for d in top[:2]) + (f" and {_plural(len(top) - 2, 'more directory', 'more directories')}"
                                                if len(top) > 2 else "")


def _labels(x: _Ctx, ids: list[str], most: int = 2) -> str:
    names = [_q(x.label(i)) for i in ids[:most]]
    return ", ".join(names) + (f" and {len(ids) - most} more" if len(ids) > most else "")


def _story(x: _Ctx, d: _Draft, sid: str, sev: dict[str, str], home: dict[str, str] | None, depots: dict[str, str],
           is_test, effect_of) -> Story:
    # a repeated edit's flows: the functions causing them are at home in the edit's story, not this one
    own = [] if d.kind == "behaviour" and d.sub is not None else d.members
    files = {depots.get(x.local(n)) or x.local(n) for n in own} | {depots.get(loc) or loc for _, loc, _ in d.sites}
    counts = {"flows": len(d.flows), "findings": len(d.findings), "functions": len(own), "files": len(files - {None, ""})}
    key = d.cause or (d.members[0] if d.members else None)
    board = (home or {}).get(key) if key else None
    if d.kind == "mechanical":
        n_sites = len(d.sites)
        tests = sum(1 for s, loc, nid in d.sites if (is_test(nid) if nid else _test_file(x, loc)))
        counts.update(sites=n_sites, test_sites=tests)
        in_tests = f" ({tests} in tests)" if tests else ""
        if d.sub is None:
            title = f"{_plural(len(d.subs), 'more repeated edit')}: {n_sites} sites"
            summary = "Each is one token change repeated across functions: " + "; ".join(
                f"{_q(s.old)} → {_q(s.new)}" for s in d.subs[:4]) + ("…" if len(d.subs) > 4 else "") + ". Skim them."
        else:
            title = f"{_q(d.sub.old)} → {_q(d.sub.new)} at {n_sites} sites in {_plural(counts['files'], 'file')}{in_tests}"
            summary = (f"Every changed line in these {_plural(len(d.members), 'function')} is this one edit. Skim them"
                       + (f"; what it changes is in {effect_of[d.sub]}." if d.sub in effect_of else "."))
        return Story(id=sid, kind="mechanical", title=title, summary=summary, risk=d.risk(sev), counts=counts,
                     nodes=d.members, findings=d.findings, board=board,
                     sub=[d.sub.old, d.sub.new] if d.sub else None, subs=[[s.old, s.new] for s in d.subs])
    if d.kind == "tests":
        title = "Tests"
        summary = f"{_plural(len(d.members), 'test function')} changed in {_plural(counts['files'], 'file')}."
    elif d.kind == "other":
        title = f"Other changes in {d.name}"
        summary = _other_summary(x, d.members)
    else:
        title, summary = _behaviour_text(x, d)
    return Story(id=sid, kind=d.kind, title=title, summary=summary, risk=d.risk(sev), counts=counts, nodes=own,
                 flows=[fl.id for fl in d.flows], findings=d.findings, board=board, collapsed=d.collapsed)


def _other_summary(x: _Ctx, members: list[str]) -> str:
    """"New: `a`, `b`. Removed: `c`. Changed: `d` and 2 more." """
    groups: dict[str, list[str]] = {"New": [], "Removed": [], "Changed": []}
    for n in members:
        fb, fa = x.fb.get(x.im.nodes[n].key), x.fa.get(x.im.nodes[n].key)
        groups["New" if fb is None and fa is not None else "Removed" if fa is None and fb is not None else "Changed"].append(n)
    return " ".join(f"{k}: {_labels(x, v, 3)}." for k, v in groups.items() if v)


def _effect(fl: Flow) -> str:
    """state, signature, ignored or unhandled (from the flow's text, as board.build_flows writes it)."""
    if fl.tag == "state":
        return "state"
    tail = fl.text.rsplit("⟶", 1)[-1].strip()
    return "signature" if tail == "signature changed" else "ignored" if tail.endswith(" ignored") else "unhandled"


def _behaviour_text(x: _Ctx, d: _Draft) -> tuple[str, str]:
    first = d.flows[0]
    kind = _effect(first)
    same = [fl for fl in d.flows if _effect(fl) == kind]
    lands = list(dict.fromkeys(x.label(fl.lands) for fl in same))
    who = _q(lands[0]) + (f" and {len(lands) - 1} more" if len(lands) > 1 else "")
    extra = len(d.flows) - len(same)
    tail = f" ({_plural(extra, 'more effect')})" if extra else ""
    cause = _q(x.label(d.cause)) if d.cause else ""
    if d.sub is not None:
        lands = list(dict.fromkeys(x.label(fl.lands) for fl in d.flows))
        who = _q(lands[0]) + (f" and {len(lands) - 1} more" if len(lands) > 1 else "")
        title = f"What {_q(d.sub.old)} → {_q(d.sub.new)} changes: {who} see{'s' if len(lands) == 1 else ''} new values"
    elif kind == "state":
        field = next((x.label(n) for n in first.path if x.im.nodes[n].kind == "field"), "a field")
        title = f"{cause} now writes {_q(field)}; {who} read{'s' if len(lands) == 1 else ''} it{tail}"
    elif kind == "signature":
        title = f"{cause}'s signature changed; {who} call{'s' if len(lands) == 1 else ''} it{tail}"
    else:
        vals = first.text.rsplit("⟶", 1)[-1].strip().rsplit(" ", 1)[0]
        verb = "ignore" if kind == "ignored" else "don't handle"
        verb = (verb + "s" if kind == "ignored" else "doesn't handle") if len(lands) == 1 else verb
        title = f"{cause} can now return {vals}; {who} {verb} it{tail}"
    summary = first.what + (f" {_plural(len(d.flows) - 1, 'more flow')} in this story." if len(d.flows) > 1 else "")
    return title, summary


def _summary(mechs: list[_Draft], behaviour: list[_Draft], others: list[_Draft], tests: _Draft | None,
             changed_lines: int) -> str:
    sites = sum(len(d.sites) for d in mechs)
    if mechs and changed_lines and sites * 2 >= changed_lines:
        top = mechs[0]
        what = f" ({_q(top.sub.old)} → {_q(top.sub.new)})" if top.sub else ""
        edits = "one edit" if len(mechs) == 1 and top.sub else _plural(len(mechs), "repeated edit")
        return f"Mostly mechanical: {sites} of {changed_lines} changed lines are {edits}{what}."
    n_tests = len(tests.members) if tests else 0
    parts = [_plural(len(behaviour), "behaviour story", "behaviour stories") if behaviour else "",
             _plural(len(mechs), "repeated edit") if mechs else "",
             _plural(sum(len(d.members) for d in others), "other changed function") if others else "",
             _plural(n_tests, "test change") if n_tests else ""]
    return (", ".join(p for p in parts if p) or "No changed functions") + "."


def _note(x: _Ctx, nid: str, mech_of: dict[str, Sub], fn_sites: dict[str, list[Site]], mech_subs: set) -> str:
    """What changed in a node, in a few words."""
    n = x.im.nodes[nid]
    if nid not in x.changed:
        return ""
    if nid in mech_of:
        s = mech_of[nid]
        return f"{_q(s.new)} instead of {_q(s.old)}"
    fb, fa = x.fb.get(n.key), x.fa.get(n.key)
    parts = []
    if fb is None and fa is not None:
        parts.append("new function")
    elif fa is None and fb is not None:
        parts.append("removed")
    else:
        ch = next((d for d in x.c.dm.functions if fa and d.file == fa.file and d.qualname == fa.qualname), None)
        if ch is not None and ch.kind == "signature_changed":
            parts.append("signature changed")
    for status, verb in (("added", "now writes"), ("removed", "no longer writes")):
        fields = [x.label(e.dst).split("::")[-1] for e in x.im.edges if e.src == nid and e.kind == "writes"
                  and e.status == status and e.dst in x.im.nodes]
        if fields:
            parts.append(f"{verb} {', '.join(dict.fromkeys(fields[:3]))}" + (f" +{len(fields) - 3}" if len(fields) > 3 else ""))
    also = sorted({s.sub for s in fn_sites.get(nid, []) if s.sub in mech_subs}, key=lambda s: s.old)
    if also:
        parts.append("also " + ", ".join(f"{_q(s.old)} → {_q(s.new)}" for s in also[:2]))
    if not parts:
        add = rem = 0
        for fc, _, (a0, a1) in _spans(x, nid):
            a, r = _count(fc.before, fc.after, a0, a1)
            add, rem = add + a, rem + r
        parts.append(f"+{add} −{rem} lines" if add or rem else "layout only")
    return "; ".join(parts)


def _landing_note(impacts: list[Impact], nid: str) -> str:
    i = next((i for i in impacts if i.node == nid and i.landing), None)
    if i is None:
        return ""
    text = i.text if len(i.text) <= 60 else i.text[:57] + "…"
    return f"⚠ {text}"


def _detail(x: _Ctx, d: _Draft, st: Story, impacts: list[Impact], depots: dict[str, str], about: About, cap: int,
            node_story: dict[str, str], mech_of: dict[str, Sub], ids: dict[int, str], mechs: list[_Draft],
            fn_sites: dict[str, list[Site]], effect_of: dict, is_test) -> StoryDetail:
    mech_subs = {m.sub for m in mechs if m.sub is not None} | {s for m in mechs for s in m.subs}
    mention = [n for n in _mentioned(d) if n in x.im.nodes]
    files = {depots.get(x.local(n)) for n in d.members if x.local(n)} - {None}
    part = about_for(about, files, set(d.findings), x.c.findings)
    board = _render(x, impacts, d.flows, mention, depots, hidden=0, about=part)
    on_flow = {n for fl in d.flows for n in fl.path}
    for bn in board.nodes:
        bn.note = _note(x, bn.id, mech_of, fn_sites, mech_subs) or (_landing_note(impacts, bn.id) if bn.id in on_flow
                                                                     else "") or None
    mech_story = {s: ids[id(m)] for m in mechs for s in ([m.sub] if m.sub else m.subs)}
    functions = []
    for n in d.members:
        if x.im.nodes[n].kind != "function":
            continue
        also = sorted({mech_story[s.sub] for s in fn_sites.get(n, []) if s.sub in mech_story and n not in mech_of})
        calls = ([StoryRef(node=m, label=x.label(m), story=node_story.get(m)) for m in sorted(x.callees.get(n, ()))
                  if m in x.changed and not is_test(m)] if d.kind == "tests" else [])
        functions.append(StoryFunction(node=n, label=x.label(n), note=_note(x, n, mech_of, fn_sites, mech_subs),
                                       on_flow=n in on_flow, also=also, calls=calls))
    detail = StoryDetail(story=st, board=board, functions=functions)
    if d.kind == "mechanical":
        own = {d.sub} if d.sub else set(d.subs)
        for s, local, nid in sorted(d.sites, key=lambda t: (t[1], t[0].after_line)):
            other = node_story.get(nid) if nid and nid not in mech_of else None
            detail.sites.append(StorySite(
                path=depots.get(local), line=s.after_line, function=x.label(nid) if nid else None, node=nid,
                before=s.before, after=s.after, test=is_test(nid) if nid else _test_file(x, local),
                effect=effect_of.get(nid) if nid else None, other_edits=other))
        partial = sorted({nid for s, _, nid in d.sites if nid and nid not in mech_of and s.sub in own})
        detail.also_in = [StoryRef(node=n, label=x.label(n), story=node_story.get(n)) for n in partial]
    elif d.kind in ("behaviour", "other"):
        detail.graph = _graph(x, d, impacts, depots, part, cap, board)
    return detail


def _record(x: _Ctx, nid: str) -> str | None:
    """A field's struct, by name: two anonymous structs named alike (a macro's, in two places) are drawn as one."""
    n = x.im.nodes[nid]
    return n.label.rsplit("::", 1)[0] if n.kind == "field" and "::" in n.label else None


def _graph(x: _Ctx, d: _Draft, impacts: list[Impact], depots: dict[str, str], about: About, cap: int,
           full: Board) -> Board:
    """At most `cap` nodes: the cause, the flows' paths, the story's other changed code, then neighbours; the fields of
    one struct count once (by its name); up to NEIGHBOURS unchanged neighbours; a story with more shows "+N more
    changed functions"."""
    order: dict[str, None] = {}
    if d.cause:
        order[d.cause] = None
    for fl in d.flows:
        order.update(dict.fromkeys(n for n in fl.path if n in x.im.nodes))
    order.update(dict.fromkeys(n for n in d.members if n in x.im.nodes))
    required = list(order)
    slot = lambda n: _record(x, n) or n                      # noqa: E731
    first = set(d.flows[0].path) if d.flows else set()
    slots: set[str] = set()
    chosen: list[str] = []
    over = len({slot(n) for n in required}) > cap
    for n in required:
        if slot(n) in slots or n in first or n == d.cause:
            pass
        elif len(slots) >= (cap - 1 if over else cap):
            continue
        chosen.append(n)
        slots.add(slot(n))
    more = [n for n in d.members if n not in set(chosen) and x.im.nodes[n].kind == "function"]
    if not over:
        room = min(cap, len(slots) + NEIGHBOURS)
        for n in _neighbours(x, impacts, set(d.members)):
            if len(slots) >= room:
                break
            if n not in set(chosen) and (slot(n) in slots or len(slots) < room):
                chosen.append(n)
                slots.add(slot(n))
    sel = set(chosen)
    shown = [fl.model_copy(deep=True) for fl in d.flows if set(fl.path) <= sel]
    g = _render(x, impacts, shown, chosen, depots, hidden=0, about=about)
    notes = {bn.id: bn.note for bn in full.nodes}
    for bn in g.nodes:
        bn.note = notes.get(bn.id)
    # one node per struct: its fields listed inside it
    rep: dict[str, str] = {}
    to: dict[str, str] = {}
    keep = []
    for bn in g.nodes:
        rec = _record(x, bn.id) if bn.kind == "field" else None
        if rec is None:
            keep.append(bn)
            continue
        if rec not in rep:
            rep[rec] = bn.id
            head = bn.model_copy(update={"kind": "struct", "label": bn.label.rsplit("::", 1)[0], "fields": [], "note": None})
            keep.append(head)
        head = next(k for k in keep if k.id == rep[rec])
        to[bn.id] = head.id
        if all(f.label != bn.label.rsplit("::", 1)[-1] for f in head.fields):
            head.fields.append(StructField(id=bn.id, label=bn.label.rsplit("::", 1)[-1]))
    g.nodes = keep
    seen, edges = set(), []
    for e in g.edges:
        e2 = e.model_copy(update={"src": to.get(e.src, e.src), "dst": to.get(e.dst, e.dst)})
        k = (e2.src, e2.dst, e2.kind)
        if e2.src != e2.dst and k not in seen:
            seen.add(k)
            edges.append(e2)
    g.edges = edges
    for fl in g.flows:
        path = [to.get(n, n) for n in fl.path]
        fl.path = [n for i, n in enumerate(path) if i == 0 or n != path[i - 1]]
        fl.lands, fl.fx_at = to.get(fl.lands, fl.lands), to.get(fl.fx_at, fl.fx_at) if fl.fx_at else None
    for i in g.impacts:
        i.node = to.get(i.node, i.node)
    if more:
        g.nodes.append(BoardNode(id="more", key="more", label=f"+{_plural(len(more), 'more changed function')}",
                                 kind="more", layer=min((n.layer or 0) for n in g.nodes) if g.nodes else 0))
    return g
