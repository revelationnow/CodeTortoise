"""Where a review's boards live (spec 2026-10-03-large-change-boards §4).

A review that fits on one board has the blob `board`. A split review has `overview`, one `board:C<n>` per cluster and
`node_cluster` (node id -> cluster id). Every review run since change stories (spec 2026-10-04) also has `stories` and
one `story:S<n>` per story. Everything that reads or rewrites boards (the pipeline's AI pass, on-demand
explanations, the API) goes through here.
"""
from __future__ import annotations

from codetortoise.board import Board, BoardSet, Files, Overview
from codetortoise.detectors.base import SEVERITY_RANK, Finding
from codetortoise.provenance import tag_board
from codetortoise.store import Store
from codetortoise.stories import RISK, StoryDetail, StorySet

PREFIX = "board:"
STORY = "story:"


def save(store: Store, rid: int, bs: BoardSet, finding_files: dict[str, Files]) -> None:
    """Store a board stage's result, replacing whatever an earlier run stored: all of it or, on an error, none of it."""
    if bs.board is not None:
        puts = {"board": tag_board(bs.board, finding_files)}
    else:
        puts = {"overview": bs.overview, "node_cluster": bs.home}
        puts |= {PREFIX + cid: tag_board(b, finding_files) for cid, b in bs.clusters.items()}
    if bs.stories is not None:
        puts["stories"] = bs.stories
        for sid, d in bs.story_details.items():
            tag_board(d.board, finding_files)
            if d.graph is not None:
                tag_board(d.graph, finding_files)
            puts[STORY + sid] = d
    store.replace_blobs(rid, ["board", "overview", "node_cluster", "stories"], [PREFIX, STORY], puts)


def stories(store: Store, rid: int) -> StorySet | None:
    raw = store.get_blob(rid, "stories")
    return StorySet.model_validate(raw) if raw else None


def story(store: Store, rid: int, sid: str) -> StoryDetail | None:
    """A story, its flows told as the boards holding them tell them now (the AI narrates flows on the boards)."""
    raw = store.get_blob(rid, STORY + sid)
    if not raw:
        return None
    d = StoryDetail.model_validate(raw)
    live = {f.id: f for b in boards(store, rid).values() for f in b.flows}
    for b in (d.board, d.graph):
        for fl in b.flows if b is not None else []:
            if fl.id in live:
                src = live[fl.id]
                fl.what, fl.what_source, fl.what_files, fl.title = src.what, src.what_source, src.what_files, src.title
    return d


def put_story(store: Store, rid: int, d: StoryDetail) -> None:
    """Store a story's detail and its entry in the list (an AI rewrite of its title and summary)."""
    ss = stories(store, rid)
    if ss is not None:
        ss.stories = [d.story if s.id == d.story.id else s for s in ss.stories]
        store.replace_blobs(rid, [], [], {"stories": ss, STORY + d.story.id: d})


def overview(store: Store, rid: int) -> Overview | None:
    o = store.get_blob(rid, "overview")
    return Overview.model_validate(o) if o else None


def board(store: Store, rid: int, cluster: str | None = None) -> Board | None:
    raw = store.get_blob(rid, PREFIX + cluster if cluster else "board")
    return Board.model_validate(raw) if raw else None


def boards(store: Store, rid: int) -> dict[str | None, Board]:
    """Every board of the review: {None: board} for one board, {cluster id: board} for a split review."""
    single = board(store, rid)
    if single is not None:
        return {None: single}
    keys = sorted(store.blob_keys(rid, PREFIX), key=lambda k: int(k[len(PREFIX) + 1:]))
    return {k[len(PREFIX):]: Board.model_validate(store.get_blob(rid, k)) for k in keys}


def put(store: Store, rid: int, cluster: str | None, b: Board) -> None:
    store.put_blob(rid, PREFIX + cluster if cluster else "board", b)


def with_flow(store: Store, rid: int, flow_id: str) -> tuple[str | None, Board] | None:
    """The board holding a flow (each flow is on exactly one board)."""
    for key, b in boards(store, rid).items():
        if any(f.id == flow_id for f in b.flows):
            return key, b
    return None


def combined(store: Store, rid: int) -> Board | None:
    """One board standing for the whole review, for AI prompts: the single board, or the overview's summary with every
    cluster's nodes, flows (in review order) and annotations. Its flows are the stored boards' own objects."""
    bs = boards(store, rid)
    if None in bs:
        return bs[None]
    if not bs:
        return None
    ov = overview(store, rid)
    return merge(list(bs.values()), ov.about if ov else next(iter(bs.values())).about)


def merge(parts: list[Board], about) -> Board:
    nodes, seen = [], set()
    for b in parts:
        for n in b.nodes:
            if n.id not in seen:
                seen.add(n.id)
                nodes.append(n)
    flows = sorted((f for b in parts for f in b.flows), key=lambda f: int(f.id[2:]) if f.id[2:].isdigit() else 0)
    return Board(nodes=nodes, edges=[e for b in parts for e in b.edges], flows=flows,
                 impacts=[i for b in parts for i in b.impacts], layers=parts[0].layers if parts else [], about=about)


def recolor(store: Store, rid: int, f: Finding, findings: list[Finding]) -> None:
    """A finding's severity changed after the boards were drawn (an AI verdict on a side effect): its flows and state
    annotations, and the risk of the stories holding it, follow — on every board and story, in one write."""
    sev = {x.id: x.severity for x in findings}
    warn = "warn" if SEVERITY_RANK.get(f.severity, 0) >= SEVERITY_RANK["medium"] else "info"

    def paint(b: Board) -> None:
        for fl in b.flows:
            if f.id in fl.findings:
                fl.severity = f.severity
        for imp in b.impacts:
            if imp.finding == f.id and imp.channel == "state":
                imp.severity = warn
    puts: dict = {}
    for key, b in boards(store, rid).items():
        paint(b)
        puts[PREFIX + key if key else "board"] = b
    ss = stories(store, rid)
    if ss is not None:
        for s in ss.stories:
            raw = store.get_blob(rid, STORY + s.id)
            if not raw or (f.id not in s.findings and not any(f.id in fl.findings for fl in StoryDetail.model_validate(
                    raw).board.flows)):
                continue
            d = StoryDetail.model_validate(raw)
            paint(d.board)
            if d.graph is not None:
                paint(d.graph)
            top = max([SEVERITY_RANK.get(sev.get(i, "info"), 0) for i in d.story.findings]
                      + [SEVERITY_RANK.get(fl.severity, 0) for fl in d.board.flows], default=0)
            d.story.risk = s.risk = RISK.get(top)
            puts[STORY + s.id] = d
        puts["stories"] = ss
    store.replace_blobs(rid, [], [], puts)
