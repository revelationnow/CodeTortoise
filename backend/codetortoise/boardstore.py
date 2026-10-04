"""Where a review's boards live (spec 2026-10-03-large-change-boards §4).

A review that fits on one board has the blob `board`. A split review has `overview`, one `board:C<n>` per cluster and
`node_cluster` (node id -> cluster id). Everything that reads or rewrites boards (the pipeline's AI pass, on-demand
explanations, the API) goes through here.
"""
from __future__ import annotations

from codetortoise.board import Board, BoardSet, Files, Overview
from codetortoise.provenance import tag_board
from codetortoise.store import Store

PREFIX = "board:"


def save(store: Store, rid: int, bs: BoardSet, finding_files: dict[str, Files]) -> None:
    """Store a board stage's result, replacing whatever an earlier run stored: all of it or, on an error, none of it."""
    if bs.board is not None:
        puts = {"board": tag_board(bs.board, finding_files)}
    else:
        puts = {"overview": bs.overview, "node_cluster": bs.home}
        puts |= {PREFIX + cid: tag_board(b, finding_files) for cid, b in bs.clusters.items()}
    store.replace_blobs(rid, ["board", "overview", "node_cluster"], [PREFIX], puts)

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
