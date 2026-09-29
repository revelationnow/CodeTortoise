"""Builds TU requests for a change set and runs extraction (optionally in a process pool)."""
from __future__ import annotations

import multiprocessing as mp
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool

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


def _pool(workers: int, libclang_path: str | None) -> ProcessPoolExecutor:
    # forkserver: the web server is multi-threaded, and a fresh interpreter per worker keeps libclang state isolated
    method = "forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn"
    return ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context(method),
                               initializer=load_libclang, initargs=(libclang_path,))


def run_extraction(reqs: list[TuRequest], libclang_path: str | None, workers: int,
                   progress: Callable[[int, int], None] | None = None,
                   worker: Callable[[TuRequest], Facts] | None = None) -> list[Facts]:
    """Extract facts for every request, always out of process.

    A libclang crash (worker process death) never propagates: after the pool breaks, unfinished requests are
    re-run one per fresh single-worker pool, and a request that crashes on its own falls back to tree-sitter.
    """
    worker = worker or _extract_with_fallback
    out: list[Facts | None] = [None] * len(reqs)
    done = 0

    def finish(i: int, facts: Facts) -> None:
        nonlocal done
        out[i] = facts
        done += 1
        if progress:
            progress(done, len(reqs))

    if not reqs:
        return []
    try:
        with _pool(max(1, min(workers, len(reqs))), libclang_path) as pool:
            futures = {pool.submit(worker, r): i for i, r in enumerate(reqs)}
            for fut in as_completed(futures):
                finish(futures[fut], fut.result())
    except BrokenProcessPool:
        pass
    for i, r in enumerate(reqs):
        if out[i] is not None:
            continue
        try:
            with _pool(1, libclang_path) as pool:
                finish(i, pool.submit(worker, r).result())
        except BrokenProcessPool:
            finish(i, extract_tu_treesitter(r, reason="libclang crashed while parsing this TU"))
    return [f for f in out if f is not None]
