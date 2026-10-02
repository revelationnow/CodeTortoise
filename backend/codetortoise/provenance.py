"""File tags (spec §14.3): the Perforce depot paths each visible item depends on.

`None` means unknown; stage 2 shows unknown items to the owner only. Structural tags are derived from the board itself,
so boards stored before tags existed get the same tags when they load. Tags on LLM-written text are recorded when the
text is written (the files whose code was in the prompt) and stay unknown otherwise.
"""
from __future__ import annotations

from collections.abc import Iterable

from codetortoise.board import Board, Files


def merge(*parts: Iterable[str] | None) -> Files:
    """Union of several tags, sorted; unknown if any part is unknown."""
    out: set[str] = set()
    for p in parts:
        if p is None:
            return None
        out.update(p)
    return sorted(out)


def _node_files(board: Board) -> dict[str, Files]:
    """A node's own file; a node without one (no visible definition) is named by the code that calls or reads it."""
    own: dict[str, Files] = {n.id: [n.path] if n.path else None for n in board.nodes}
    out = dict(own)
    for n in board.nodes:
        if own[n.id] is None:
            refs = [own[e.src] for e in board.edges if e.dst == n.id and own.get(e.src)]
            out[n.id] = merge(*refs) if refs else None
    return out


def tag_board(board: Board, finding_files: dict[str, Files] | None = None) -> Board:
    """Set the structural tags on every item of `board` (in place, returned for chaining). `finding_files` maps
    finding ids to their tags, for the change summary's "why it's risky" lines."""
    nf = _node_files(board)

    def of(ids: Iterable[str]) -> Files:
        return merge(*(nf.get(i) for i in ids))

    for n in board.nodes:
        n.files = nf[n.id]
    for e in board.edges:
        e.files = of([e.src, e.dst])
    for i in board.impacts:
        i.files = merge([i.path] if i.path else [], of([i.node, *([i.cause] if i.cause else [])]))
    for fl in board.flows:
        fl.files = of([*fl.path, fl.lands, *([fl.fx_at] if fl.fx_at else [])])
        if fl.what_source == "template":
            fl.what_files = fl.files
    for layer in board.layers:
        layer.files = of(n.id for n in board.nodes if n.layer == layer.level)
    tree = [f for d in board.about.tree for f in d.files]
    for f in tree:
        f.files = [f.path]
    for c in board.about.cls:
        c.files = sorted(f.path for f in tree if c.cl in f.cls) or None
    for w in board.about.why:
        w.files = (finding_files or {}).get(w.finding)
    if board.about.intent_source == "template":                     # counts and CL descriptions: every changed file
        board.about.intent_files = sorted(f.path for f in tree)
    return board
