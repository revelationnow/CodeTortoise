"""A review told as a few stories (spec 2026-10-04-change-stories §2–§3).

Mechanical stories are repeated edits (one substitution in at least two functions). Behaviour stories start from the
changed functions that cause flows (and from the flows of a repeated edit); the rest of the changed code joins the
nearest of them, or forms "Other changes" by connection. Changed test code forms one Tests story. Each story keeps a
board of every node it mentions (for its steps and code) and a graph of at most `story_graph_nodes` nodes.
"""
from __future__ import annotations

import posixpath
from collections import Counter, defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from codetortoise.board import (
    About,
    Analysis,
    Board,
    BoardContext,
    BoardNode,
    Files,
    Flow,
    Impact,
    StructField,
    _count,
    _Ctx,
    _neighbours,
    _render,
    about_for,
    analyse,
    is_test_path,
)
from codetortoise.clusters import _shared, altered_access
from codetortoise.detectors.base import SEVERITY_RANK
from codetortoise.grouping import Placement, PlannedStory, StoryPlan, rules_plan
from codetortoise.pieces import Piece, PieceSet, build_pieces
from codetortoise.repeated import Repeated, _note, _plural, _q, find_repeated
from codetortoise.substitutions import Site, Sub

Kind = Literal["behaviour", "other", "mechanical", "tests", "unsorted"]
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
    text_files: Files = None                                # LLM text: the files whose code was in its prompt
    risk: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    nodes: list[str] = Field(default_factory=list)          # changed code whose home is this story
    flows: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    board: str | None = None                                # the cluster board holding its cause (None: one board)
    sub: list[str] | None = None                            # a mechanical story: [old, new]
    subs: list[list[str]] = Field(default_factory=list)     # "N more repeated edits": each substitution
    collapsed: bool = False                                 # a behaviour story past the list's limit
    cls: list[int] = Field(default_factory=list)            # the changelists of the files holding its code
    # spec 2026-10-05-two-tier-stories §7.1: the pieces it groups and why, and (tier 1) what it is for
    targets: list[str] = Field(default_factory=list)        # the build targets of its code
    pieces: list[str] = Field(default_factory=list)
    placements: list[Placement] = Field(default_factory=list)
    purpose: str = ""
    check: list[str] = Field(default_factory=list)          # what a reviewer should check
    questions: list[str] = Field(default_factory=list)      # open questions
    related: list[str] = Field(default_factory=list)        # related stories' ids
    source: Literal["tier1", "rules"] = "rules"             # who grouped it


class StoryPiece(BaseModel):
    """One piece of a story, for "Why these belong together" (spec 2026-10-05-two-tier-stories §10)."""
    id: str
    kind: str
    cl: int | None = None
    files: list[str] = Field(default_factory=list)          # depot paths (workspace-relative when unknown)
    names: list[str] = Field(default_factory=list)          # its changed functions, or a declaration piece's names


class StoryDetail(BaseModel):
    story: Story
    board: Board                                            # every node the story mentions, for steps and code
    graph: Board | None = None                              # at most story_graph_nodes nodes
    functions: list[StoryFunction] = Field(default_factory=list)
    sites: list[StorySite] = Field(default_factory=list)
    also_in: list[StoryRef] = Field(default_factory=list)   # a mechanical story: functions with other edits too
    pieces: list[StoryPiece] = Field(default_factory=list)


class StorySet(BaseModel):
    summary: str
    stories: list[Story] = Field(default_factory=list)
    node_story: dict[str, str] = Field(default_factory=dict)
    flow_story: dict[str, str] = Field(default_factory=dict)
    finding_story: dict[str, str] = Field(default_factory=dict)


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
        self.plan: PlannedStory | None = None
        self.pieces: list[Piece] = []

    def rank(self, sev: dict[str, str]) -> tuple:
        f = max((SEVERITY_RANK.get(sev.get(i, "info"), 0) for i in self.findings), default=0)
        fl = max((SEVERITY_RANK.get(x.severity, 0) for x in self.flows), default=0)
        return (-f, -fl, -len(self.flows), -len(self.members))

    def risk(self, sev: dict[str, str]) -> str | None:
        top = max([SEVERITY_RANK.get(sev.get(i, "info"), 0) for i in self.findings]
                  + [SEVERITY_RANK.get(x.severity, 0) for x in self.flows], default=0)
        return RISK.get(top)


def build_stories(c: BoardContext, home: dict[str, str] | None = None, analysis: Analysis | None = None,
                  plan: StoryPlan | None = None, pieces: PieceSet | None = None,
                  rep: Repeated | None = None) -> tuple[StorySet, dict[str, StoryDetail]]:
    """The review's stories and each story's detail, from a plan grouping the change's pieces (the strong model's, or
    the rules' when `plan` is None; spec 2026-10-05-two-tier-stories §6). `home` maps nodes to the cluster boards
    holding them; `analysis` is the boards' (`BoardSet.analysis`), so stories and boards tell the same flows. Stories
    work on copies: the AI pass later rewrites the boards' flows and summary in place."""
    a = analysis or analyse(c)
    x = a.x
    impacts = [i.model_copy(deep=True) for i in a.impacts]
    flows = [f.model_copy(deep=True) for f in a.flows]
    about = a.about.model_copy(deep=True)
    im, cfg = x.im, c.cfg
    sev = {f.id: f.severity for f in c.findings}
    is_test = x.is_test_path

    # 1. substitutions and pieces (shared with the pieces stage), and the plan grouping the pieces
    rep = rep or find_repeated(c, x)
    fn_sites, outside, mech_of = rep.fn_sites, rep.outside, rep.mech_of
    pieces = pieces or build_pieces(c, a, {}, rep=rep)
    plan = plan or StoryPlan(stories=rules_plan(pieces))
    by_id = {p.id: p for p in pieces.pieces}
    sub_of = {(s.old, s.new): s for s in rep.mech_subs}
    flows_of: dict[str, list[Flow]] = defaultdict(list)
    for fl in flows:
        flows_of[fl.cause or fl.path[-1]].append(fl)

    # 2. each planned story is a draft: unsorted; only repeated edits (mechanical); with flows (behaviour); only tests
    planned: list[_Draft] = []
    for g in plan.stories:
        mine = [by_id[pid] for pid in g.pieces if pid in by_id]
        nodes = [n for p in mine for n in p.nodes]
        repeated = bool(mine) and all(p.kind == "repeated" for p in mine)
        fls = [] if repeated else [fl for n in nodes for fl in flows_of.get(n, [])]
        kind = ("unsorted" if g.unsorted else "mechanical" if repeated else "behaviour" if fls
                else "tests" if mine and all(p.kind == "tests" for p in mine) else "other")
        d = _Draft(kind, members=nodes, flows=fls)
        d.plan, d.pieces = g, mine
        if kind == "behaviour":
            top = min(fls, key=lambda fl: (-SEVERITY_RANK.get(fl.severity, 0), flows.index(fl)))
            d.cause = top.cause or top.path[-1]
        if kind == "mechanical":
            subs = list(dict.fromkeys(sub_of[tuple(p.sub)] for p in mine if p.sub and tuple(p.sub) in sub_of))
            d.sub, d.subs = (subs[0], []) if len(subs) == 1 else (None, subs)
        planned.append(d)
    mechs = [d for d in planned if d.kind == "mechanical"]
    claimed: set[Sub] = set()                                 # a substitution's sites are told by its first story
    for d in mechs:
        own = ({d.sub} if d.sub else set(d.subs)) - claimed
        claimed |= own
        for nid, sites in fn_sites.items():
            d.sites += [(s, x.local(nid) or "", nid) for s in sites if s.sub in own]
        d.sites += [(s, local, None) for s, local in outside if s.sub in own]
    # what a repeated edit changes: flows caused by its functions, one behaviour story per substitution
    mech_member = {n for d in mechs for n in d.members}
    seeds: dict[Sub, _Draft] = {}
    for fl in flows:
        cause = fl.cause or fl.path[-1]
        if cause in mech_member and cause in mech_of:
            d = seeds.setdefault(mech_of[cause], _Draft("behaviour", sub=mech_of[cause]))
            d.flows.append(fl)
            if cause not in d.members:
                d.members.append(cause)
    behaviour = [d for d in planned if d.kind == "behaviour"] + list(seeds.values())
    for d in behaviour:
        d.findings = sorted({f for fl in d.flows for f in fl.findings})
    taken: set[str] = set()                                   # a finding on two stories' flows goes with the riskier
    for d in sorted(behaviour, key=lambda d: d.rank(sev)):
        d.findings = [f for f in d.findings if f not in taken]
        taken |= set(d.findings)
    others = [d for d in planned if d.kind == "other"]
    tests = [d for d in planned if d.kind == "tests"]
    unsorted = [d for d in planned if d.kind == "unsorted"]
    drafts = behaviour + others + mechs + tests + unsorted
    node_draft: dict[str, _Draft] = {n: d for d in drafts if d.kind != "behaviour" or d.cause or d.plan
                                     for n in d.members}

    # 3. findings: the story of their flow, else of their first node with a story (or on its flows), else of the piece
    #    holding their file
    flow_draft = {fl.id: d for d in behaviour + unsorted for fl in d.flows}
    piece_draft = {p.id: d for d in drafts for p in d.pieces}
    file_piece: dict[str, str] = {}
    for p in sorted(pieces.pieces, key=lambda p: p.kind != "declarations"):   # a header's findings: its declarations
        for f in p.files:
            file_piece.setdefault(f, p.id)
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
            d = d or next((b for b in behaviour if any(n in fl.path for fl in b.flows)), None)   # on a story's flow
        for e in f.evidence:
            if d is not None:
                break
            d = piece_draft.get(file_piece.get(e.file or "", ""))
        if d is not None:                                     # none: the finding stays in the review's list only
            d.findings.append(f.id)

    # 4. order and the list's limit; the rules' "Other changes" merge by directory within a target and CL
    behaviour.sort(key=lambda d: d.rank(sev))
    others.sort(key=lambda d: d.rank(sev))
    cap = cfg.max_stories

    def total() -> int:
        return len(behaviour) + len(others) + len(mechs) + len(tests) + len(unsorted)

    def home_dir(d: _Draft) -> str:
        return Counter(posixpath.dirname(x.local(m) or "") for m in d.members).most_common(1)[0][0] if d.members else ""

    def scope(d: _Draft) -> tuple:
        return (tuple(sorted({t for p in d.pieces for t in p.targets})), tuple(sorted({p.cl or 0 for p in d.pieces})))
    while total() > cap:
        mergeable = [o for o in others if o.plan is None or o.plan.source == "rules"]
        pair = next(((small, [o for o in mergeable if o is not small and scope(o) == scope(small)])
                     for small in reversed(mergeable) if any(o is not small and scope(o) == scope(small) for o in mergeable)),
                    None)
        if pair is None:
            break
        small, into_any = pair
        into = max(into_any, key=lambda o: (len(_shared(home_dir(o), home_dir(small))), -others.index(o)))
        others.remove(small)
        into.members += small.members
        into.findings += small.findings
        into.pieces += small.pieces
        into.plan.placements += small.plan.placements
    if total() > cap and len(mechs) > 1:                     # the smallest repeated edits fold into one story
        keep = max(1, len(mechs) - (total() - cap) - 1)
        folded = _Draft("mechanical")
        folded.plan = PlannedStory(key="folded", placements=[])
        for d in mechs[keep:]:
            folded.members += d.members
            folded.sites += d.sites
            folded.findings += d.findings
            folded.subs += [d.sub] if d.sub else d.subs
            folded.pieces += d.pieces
            folded.plan.placements += d.plan.placements if d.plan else []
        mechs = mechs[:keep] + [folded]
    if total() > cap:                                        # stories with a purpose are never merged: collapse the rest
        purposeful = behaviour + [o for o in others if o.plan is not None and o.plan.source == "tier1"]
        room = max(0, cap - (total() - len(purposeful)) - 1)  # "N more stories" is one entry too
        for d in purposeful[room:]:
            d.collapsed = True

    for d in others:                                         # "in <directory>"; alike ones add their first function
        d.name = _dir_name(x, d.members, c.root, [f for p in d.pieces for f in p.files])
    alike = Counter(d.name for d in others)
    for d in others:
        if alike[d.name] > 1 and d.members:
            d.name += f" ({_q(x.label(d.members[0]))})"
    ordered = behaviour + others + mechs + tests + unsorted
    ids = {id(d): f"S{i + 1}" for i, d in enumerate(ordered)}

    # 5. the stories, their boards and graphs
    all_locals = set()
    for d in ordered:
        all_locals |= ({x.local(n) for n in _mentioned(d)} | {i.path for i in impacts if i.node in _mentioned(d)}
                       | {loc for _, loc, _ in d.sites} | {f for p in d.pieces for f in p.files})
    depots = c.depots_for(sorted(p for p in all_locals if p))
    node_story: dict[str, str] = {}
    for d in ordered:
        for n in d.members:
            node_story.setdefault(n, ids[id(d)])
    for d in mechs:
        for n in d.members:
            node_story[n] = ids[id(d)]
    for d in behaviour:
        for fl in d.flows:
            for n in fl.path:
                node_story.setdefault(n, ids[id(d)])
    effect_of = {d.sub: ids[id(d)] for d in behaviour if d.sub is not None}
    for d in behaviour:
        for fl in d.flows:
            if fl.cause in mech_of:
                effect_of.setdefault(fl.cause, ids[id(d)])
    key_story = {d.plan.key: ids[id(d)] for d in ordered if d.plan is not None}

    stories, details = [], {}
    changed_lines = sum(max(_count(f.before, f.after)) for f in c.cs.files)   # added and deleted files too
    cls_of = {f.local: {p.cl for p in f.per_cl} for f in c.cs.files}
    for d in ordered:
        sid = ids[id(d)]
        st = _story(x, d, sid, sev, home, depots, is_test, effect_of)
        files = {x.local(n) for n in d.members} | {f for p in d.pieces for f in p.files}
        files |= {loc for _, loc, _ in d.sites}                             # sites outside functions too
        st.cls = sorted(set().union(*(cls_of.get(f, set()) for f in files if f)))
        _planned(st, d, key_story, pieces, x)
        stories.append(st)
        details[sid] = _detail(x, d, st, impacts, depots, about, cfg.story_graph_nodes, node_story, mech_of, ids, mechs,
                               fn_sites, effect_of, is_test)
    summary = _summary(mechs, behaviour, others, tests, changed_lines)
    flow_story = {fl.id: ids[id(d)] for d in behaviour + unsorted for fl in d.flows}
    finding_story = {f: ids[id(d)] for d in ordered for f in d.findings}
    return StorySet(summary=summary, stories=stories, node_story=node_story, flow_story=flow_story,
                    finding_story=finding_story), details


def _planned(st: Story, d: _Draft, key_story: dict[str, str], pieces: PieceSet, x: _Ctx) -> None:
    """What the plan says of a story: its pieces and why each is there, its targets, and (tier 1) its title, purpose,
    what to check, open questions and related stories."""
    st.pieces = [p.id for p in d.pieces]
    st.targets = sorted({t for p in d.pieces for t in p.targets}) or sorted(
        {t for n in d.members for t in pieces.targets.get(x.local(n) or "", [])})
    g = d.plan
    if g is None:
        return
    st.placements = [pl.model_copy() for pl in g.placements]
    st.source = g.source
    if g.source == "tier1" and not g.unsorted:
        st.purpose, st.check, st.questions = g.purpose, list(g.check), list(g.questions)
        st.related = [key_story[k] for k in g.related if k in key_story and key_story[k] != st.id]
        if g.title:
            st.title, st.text_source = g.title, "llm"
            st.summary = g.purpose or st.summary


def _test_file(x: _Ctx, local: str) -> bool:
    """Test code by its workspace-relative path, as functions are (`is_test_path`)."""
    root = x.c.root.rstrip("/") + "/"
    return is_test_path(local[len(root):] if x.c.root and local.startswith(root) else local)


def _mentioned(d: _Draft) -> list[str]:
    out = dict.fromkeys(d.members)
    for fl in d.flows:
        out.update(dict.fromkeys(fl.path))
    return list(out)


def _dir_name(x: _Ctx, members: list[str], root: str, files: list[str] | None = None) -> str:
    """Their common directory, workspace-relative; code spread over the workspace is named by its main directories.
    Without members (a header's declarations), the directory of `files`."""
    r = root.rstrip("/") + "/"
    dirs = [posixpath.dirname(x.local(m) or "") for m in members] or [posixpath.dirname(f) for f in files or []]
    rel = [(d + "/")[len(r):].rstrip("/") for d in dirs if (d + "/").startswith(r)]
    common = posixpath.commonpath(rel) if rel and len(rel) == len(dirs) and all(rel) else ""
    if rel and len(rel) == len(dirs) and not any(rel):
        return _q("the workspace root")
    if common:
        return _q(common)
    top = [d or "the workspace root"                                  # never an absolute path; ties by name
           for d, _ in sorted(Counter(rel).items(), key=lambda kv: (-kv[1], kv[0]))]
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
        names = [n for p in d.pieces for n in p.names]
        summary = " ".join(t for t in [_other_summary(x, d.members), f"Declarations: {', '.join(_q(n) for n in names[:4])}"
                                       + (f" and {len(names) - 4} more." if len(names) > 4 else ".") if names else ""] if t)
    elif d.kind == "unsorted":
        title = "Unsorted: needs a person to place these"
        why = [f"{pl.piece}: {pl.reason}" for pl in (d.plan.placements if d.plan else [])]
        summary = (f"{_plural(len(d.pieces), 'piece')} no story could take. " + "; ".join(why[:4])
                   + (f"; and {len(why) - 4} more." if len(why) > 4 else "."))
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


def _summary(mechs: list[_Draft], behaviour: list[_Draft], others: list[_Draft], tests: list[_Draft],
             changed_lines: int) -> str:
    sites = sum(len(d.sites) for d in mechs)
    if mechs and changed_lines and sites * 2 >= changed_lines:
        top = mechs[0]
        what = f" ({_q(top.sub.old)} → {_q(top.sub.new)})" if top.sub else ""
        edits = "one edit" if len(mechs) == 1 and top.sub else _plural(len(mechs), "repeated edit")
        return f"Mostly mechanical: {sites} of {changed_lines} changed lines are {edits}{what}."
    n_tests = sum(len(t.members) for t in tests)
    parts = [_plural(len(behaviour), "behaviour story", "behaviour stories") if behaviour else "",
             _plural(len(mechs), "repeated edit") if mechs else "",
             _plural(sum(len(d.members) for d in others), "other changed function") if others else "",
             _plural(n_tests, "test change") if n_tests else ""]
    return (", ".join(p for p in parts if p) or "No changed functions") + "."


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
    files = ({depots.get(x.local(n)) for n in d.members if x.local(n)} | {depots.get(f) for p in d.pieces for f in p.files}
             ) - {None}
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
    root = x.c.root.rstrip("/") + "/"
    detail = StoryDetail(story=st, board=board, functions=functions, pieces=[
        StoryPiece(id=p.id, kind=p.kind, cl=p.cl, names=(p.names or [x.label(n) for n in p.nodes])[:6],
                   files=[depots.get(f) or f.removeprefix(root) for f in p.files]) for p in d.pieces])
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
    elif d.kind in ("behaviour", "other", "unsorted"):
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
