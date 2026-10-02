"""File tags (spec §14.3): the Perforce depot paths each visible item depends on.

`None` means unknown; stage 2 shows unknown items to the owner only. Structural tags are derived from the board itself,
so boards stored before tags existed get the same tags when they load. Tags on LLM-written text are recorded when the
text is written (the files whose code was in the prompt) and stay unknown otherwise.
"""
from __future__ import annotations

from collections.abc import Iterable

from codetortoise.board import Board, Files
from codetortoise.detectors.base import Finding
from codetortoise.impact import ImpactModel
from codetortoise.paths import canon


def merge(*parts: Iterable[str] | None) -> Files:
    """Union of several tags, sorted; unknown if any part is unknown."""
    out: set[str] = set()
    for p in parts:
        if p is None:
            return None
        out.update(p)
    return sorted(out)


def _node_files(board: Board) -> dict[str, Files]:
    """A node's own file; a node without a visible definition is named by the code that calls or reads it. A node whose
    definition is known (`local`) but whose depot lookup failed stays unknown."""
    own: dict[str, Files] = {n.id: [n.path] if n.path else None for n in board.nodes}
    out = dict(own)
    for n in board.nodes:
        if own[n.id] is None and n.local is None:
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
    for i in board.impacts:                                          # its line, its node, its cause and what it names
        i.files = merge([i.path] if i.path else None, of([i.node, *([i.cause] if i.cause else [])]),
                        of(i.refs) if i.refs is not None else None)
    for fl in board.flows:
        fl.files = of([*fl.path, fl.lands, *([fl.fx_at] if fl.fx_at else [])])
        if fl.what_source == "template":
            fl.what_files = fl.files
        elif fl.what_files is not None:                              # LLM text stands in for the flow's own text
            fl.what_files = merge(fl.what_files, fl.files)
    for layer in board.layers:          # names come from directory names across the workspace: stage 2 shows L<n>
        layer.files = None
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


def local_files(locals_: Iterable[str], resolved: dict[str, str], root: str,
                system_dirs: Iterable[str] = ()) -> dict[str, Files]:
    """Local paths to tags: the depot path Perforce gave; `[]` under a system or toolchain include directory (not under
    Perforce); unknown otherwise, including other paths outside the workspace (another client could map them)."""
    dirs = [canon(str(d)).rstrip("/") + "/" for d in system_dirs]
    return {p: [resolved[p]] if p in resolved else ([] if any(p.startswith(d) for d in dirs) else None) for p in locals_}


def impact_node_files(impact: ImpactModel, by_local: dict[str, Files],
                      decl: dict[str, str] | None = None) -> dict[str, Files]:
    """Tags for every node of the impact graph: its file; a node without one (a field) is named by the code that
    accesses it and by its declaration (`decl`: node key -> local file of the declaring header)."""
    own: dict[str, Files] = {nid: by_local.get(n.file) if n.file else None for nid, n in impact.nodes.items()}
    out = dict(own)
    for nid, n in impact.nodes.items():
        if n.file is None:
            parts = [own[e.src] for e in impact.edges if e.dst == nid and own.get(e.src)]
            if (decl or {}).get(n.key):
                parts.append(by_local.get(decl[n.key]))
            out[nid] = merge(*parts) if parts else None
    return out


def finding_files(f: Finding, node_files: dict[str, Files], by_local: dict[str, Files]) -> Files:
    """A finding's nodes' files and the files its evidence points at."""
    def evidence(e) -> Files:            # a file, or the nodes a file-less line names; undeclared: unknown
        if e.file:
            return by_local.get(e.file)
        return None if e.nodes is None else merge(*(node_files.get(n) for n in e.nodes))
    return merge(*(node_files.get(n) for n in f.nodes), *(evidence(e) for e in f.evidence))


def comment_scope(board: Board, findings: list[Finding], anchor_kind: str, anchor: dict) -> Files:
    """The files a comment depends on, from where it is anchored (not stored): what its author was looking at."""
    if anchor_kind == "line":
        path = anchor.get("path") or anchor.get("depot")             # M1 line anchors used `depot`
        return [path] if path else None
    if anchor_kind == "function":
        return next((n.files for n in board.nodes if n.key == anchor.get("key")), None)
    if anchor_kind == "finding":       # shown under every finding with that kind and title
        same = [f for f in findings if f.kind == anchor.get("kind") and f.title == anchor.get("title")]
        return merge(*(t for f in same for t in (f.files, f.explain_files if f.explanation else []))) if same else None
    if anchor_kind == "chapter":       # what the layer shows: its nodes
        ids = [n.files for n in board.nodes if n.layer == anchor.get("level")]
        return merge(*ids) if ids else None
    if anchor_kind == "review":
        return review_files(board, findings)
    return None


def review_files(board: Board, findings: list[Finding]) -> Files:
    """Every file behind anything shown for the review: the board, the change summary and the findings."""
    a = board.about
    tags = [*(i.files for i in [*board.nodes, *board.edges, *board.impacts, *a.cls, *a.why, *a.drift]),
            *(f.files for d in a.tree for f in d.files), *(t for fl in board.flows for t in (fl.files, fl.what_files)),
            a.intent_files, *(f.files for f in findings), *(f.explain_files for f in findings if f.explanation)]
    return merge(*tags)
