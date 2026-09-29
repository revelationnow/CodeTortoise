"""Builds TU requests for a change set and runs extraction (optionally in a process pool)."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor

from codetortoise.cparse import is_header
from codetortoise.facts.clang_extractor import TuRequest, extract_tu
from codetortoise.facts.model import Facts
from codetortoise.facts.treesitter_extractor import extract_tu_treesitter
from codetortoise.toolchain.libclang import load_libclang
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.tu_select import TuSelection
from codetortoise.vcs.model import ChangeSet


def build_requests(sel: TuSelection, cs: ChangeSet, tc: Toolchain, variant: str) -> list[TuRequest]:
    unsaved: dict[str, str] = {}
    for f in cs.files:
        if variant == "before" and f.action != "add":
            unsaved[f.local] = f.before
        elif variant == "after" and f.action != "delete":
            unsaved[f.local] = f.after
    focus = [f.local for f in cs.files]
    tus = list(sel.selected)
    for f in cs.files:  # new source files are TUs only in "after"; deleted ones only in "before"
        if is_header(f.local) or f.local in tus:
            continue
        if (variant == "after" and f.action == "add") or (variant == "before" and f.action == "delete"):
            tus.append(f.local)
    reqs = []
    for tu in tus:
        if variant == "after" and any(f.local == tu and f.action == "delete" for f in cs.files):
            continue
        if variant == "before" and any(f.local == tu and f.action == "add" for f in cs.files):
            continue
        reqs.append(TuRequest(file=tu, args=tc.args_for(tu), variant=variant, unsaved=unsaved, focus=focus))
    return reqs


def _extract_with_fallback(req: TuRequest) -> Facts:
    try:
        facts = extract_tu(req)
    except Exception as e:  # libclang crash paths surface as Python exceptions
        return extract_tu_treesitter(req, reason=f"clang extractor error: {e}")
    if facts.tu.confidence == "failed":
        return extract_tu_treesitter(req, reason="; ".join(facts.tu.diagnostics))
    return facts


def run_extraction(reqs: list[TuRequest], libclang_path: str | None, workers: int,
                   progress: Callable[[int, int], None] | None = None) -> list[Facts]:
    out: list[Facts] = []
    if workers <= 1 or len(reqs) <= 1:
        load_libclang(libclang_path)
        for i, r in enumerate(reqs):
            out.append(_extract_with_fallback(r))
            if progress:
                progress(i + 1, len(reqs))
        return out
    with ProcessPoolExecutor(max_workers=workers, initializer=load_libclang, initargs=(libclang_path,)) as pool:
        for i, facts in enumerate(pool.map(_extract_with_fallback, reqs)):
            out.append(facts)
            if progress:
                progress(i + 1, len(reqs))
    return out
