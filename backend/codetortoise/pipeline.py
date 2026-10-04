"""Staged review pipeline and background job runner."""
from __future__ import annotations

import logging
import queue
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from codetortoise import boardstore
from codetortoise.board import BoardContext, build_boards
from codetortoise.detectors.base import DetectorContext, run_detectors
from codetortoise.diffmap import map_changes
from codetortoise.facts.model import Facts, relative_records
from codetortoise.facts.runner import build_requests, parse_summary, run_extraction
from codetortoise.impact import ImpactModel, build_impact
from codetortoise.llm.storyboard import build_storyboard
from codetortoise.paths import canon
from codetortoise.provenance import finding_files, impact_node_files, local_files
from codetortoise.services import Services
from codetortoise.stories import build_stories
from codetortoise.swarm import SwarmError
from codetortoise.tu_select import TuSelection, field_follow_up, select_tus
from codetortoise.vcs.model import ChangeSet

log = logging.getLogger(__name__)

STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "board", "llm",
          "finalize"]
DEPS = {"swarm_read": ["ingest"], "diffmap": ["ingest"], "tu_select": ["diffmap"], "facts": ["tu_select"],
        "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "board": ["impact", "detectors"],
        "llm": ["detectors"]}


class Degraded(Exception):
    """Stage completed with a warning; its outputs are usable."""


def _snippet(text: str, start: int, end: int, max_lines: int = 120) -> str:
    lines = text.splitlines()
    chunk = lines[max(0, start - 1): min(len(lines), end, start - 1 + max_lines)]
    return "\n".join(f"{start + i:5d} {l}" for i, l in enumerate(chunk))


def collect_snippets(impact: ImpactModel, cs: ChangeSet, after: list[Facts], limit: int = 40) -> dict[str, str]:
    texts = {f.local: f.after for f in cs.files}
    ends = {f.usr: f.end_line for facts in after for f in facts.functions}
    wanted = list(impact.changed) + [b.node for b in impact.blast[:limit]]
    out = {}
    for nid in wanted:
        n = impact.nodes[nid]
        if n.kind != "function" or not n.file or not n.line:
            continue
        text = texts.get(n.file)
        if text is None:
            p = Path(n.file)
            text = p.read_text(errors="replace") if p.exists() else ""
        out[nid] = _snippet(text, n.line, ends.get(n.key, n.line + 40))
    return out


def depot_resolver(source, cs: ChangeSet, root: str, notes: list[str]):
    """Board depot-path lookup: changed files from the change set, other workspace files from the source in one
    call. Paths outside the workspace (system headers, toolchain) are never sent; a failed lookup is noted and
    leaves those nodes without a depot path (no context code on demand for them)."""
    prefix = canon(str(root)).rstrip("/") + "/"

    known = {f.local: f.depot for f in cs.files}
    asked: set[str] = set()                 # each workspace file is looked up once, found or not

    def resolve(locals_: list[str]) -> dict[str, str]:
        rest = sorted({p for p in locals_ if p not in known and p not in asked and p.startswith(prefix)})
        if rest:
            asked.update(rest)
            try:
                known.update(source.depots_for(rest))
            except Exception as e:  # board still useful without depot paths for context nodes
                note = f"depot paths unavailable for context nodes: {type(e).__name__}: {e}"
                if note not in notes:
                    notes.append(note)
        return {p: known[p] for p in locals_ if p in known}
    return resolve



SYSTEM_DIRS = ("/usr/include", "/usr/local/include", "/usr/lib/gcc", "/usr/lib/clang")


def system_include_dirs(toolchain) -> list[str]:
    """Directories whose headers are not under Perforce: the usual system ones and the toolchain driver's."""
    dirs = list(SYSTEM_DIRS)
    for info in getattr(toolchain, "driver", {}).values():
        dirs += [*info.include_dirs, *([info.resource_dir] if info.resource_dir else [])]
    return dirs

def run_review(rid: int, svc: Services) -> None:
    store, cfg = svc.store, svc.cfg
    store.reset_stages(rid, STAGES)
    store.set_review_status(rid, "running")
    status: dict[str, str] = {}
    ctx: dict = {}
    cls = store.get_review(rid)["cls"]

    def stage(name: str, fn) -> None:
        if any(status.get(d) not in ("ok", "degraded") for d in DEPS.get(name, [])):
            status[name] = "skipped"
            store.set_stage(rid, name, "skipped", "missing inputs")
            return
        store.set_stage(rid, name, "running")
        try:
            msg = fn() or ""
            status[name] = "ok"
            store.set_stage(rid, name, "ok", msg)
        except Degraded as e:
            status[name] = "degraded"
            store.set_stage(rid, name, "degraded", str(e))
        except Exception as e:  # stage isolation: record and continue
            log.error("stage %s failed: %s", name, traceback.format_exc())
            status[name] = "failed"
            store.set_stage(rid, name, "failed", f"{type(e).__name__}: {e}")

    def ingest():
        cs = svc.source.load(cls)
        ctx["cs"] = cs
        for meta in cs.cls:
            store.upsert_cl(rid, meta)
        store.put_blob(rid, "changeset", cs)
        msg = f"{len(cs.files)} file(s), {len(cs.drift)} drift warning(s)"
        if cs.warnings:
            more = f" (+{len(cs.warnings) - 5} more)" if len(cs.warnings) > 5 else ""
            raise Degraded(f"{msg}; {len(cs.warnings)} file warning(s): {'; '.join(cs.warnings[:5])}{more}")
        return msg

    def swarm_read():
        client = svc.swarm()
        if client is None:
            raise Degraded("Swarm not configured or owner not logged in")
        errors = []
        for meta in ctx["cs"].cls:
            try:
                store.set_cl_swarm(rid, meta.cl, client.get_review_for_change(meta.cl))
            except SwarmError as e:
                errors.append(str(e))
        if errors:
            raise Degraded("; ".join(errors))

    def diffmap():
        dm = map_changes(ctx["cs"])
        ctx["dm"] = dm
        store.put_blob(rid, "diffmap", dm)
        return f"{len(dm.functions)} function change(s), {len(dm.types)} type/macro/decl change(s)"

    def tu_select():
        if svc.index.generation() == 0:
            svc.build_index()
        sel = select_tus(ctx["dm"], svc.index, svc.cdb, cfg.analysis)
        ctx["sel"] = sel
        store.put_blob(rid, "selection", sel)
        return f"{len(sel.selected)} TU(s) selected, {sel.over_budget} over budget"

    def layers():
        model = svc.layers.get()
        ctx["layers"] = model
        if model is None:
            raise Degraded("symbol index not built yet")
        store.put_blob(rid, "layers", model)
        return f"{len(model.layers)} layer(s)"

    def extract(reqs):
        """Each library's requests run in workers that load that library (spec 2026-10-02 toolchains §5)."""
        out = []
        for lib in sorted({r.libclang for r in reqs}, key=lambda p: p or ""):
            out += run_extraction([r for r in reqs if r.libclang == lib], lib, cfg.analysis.workers)
        return out

    def facts():
        svc.toolchain.prepare()
        before = extract(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "before"))
        after = extract(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "after"))
        note = ""
        extra = field_follow_up(ctx["dm"], after, svc.index, svc.cdb, ctx["sel"], cfg.analysis)
        if extra:
            parsed = {f.tu.file for f in before + after}
            follow = TuSelection(selected=extra)
            for variant, out in (("before", before), ("after", after)):
                reqs = [r for r in build_requests(follow, ctx["cs"], svc.toolchain, variant) if r.file not in parsed]
                out += extract(reqs)
            ctx["sel"].selected += extra
            ctx["sel"].hops.update({p: 1 for p in extra})
            store.put_blob(rid, "selection", ctx["sel"])
            note = f"; {len(extra)} follow-up TU(s) for fields written by the change"
        relative_records(before + after, canon(str(cfg.workspace.root)))
        ctx["before"], ctx["after"] = before, after
        store.put_blob(rid, "facts_before", before)
        store.put_blob(rid, "facts_after", after)
        learned = sorted({f for facts in before + after for f in facts.tu.stripped_flags} - svc.toolchain.strip)
        if learned:
            svc.remember_stripped(learned)
            note += f"; stripped flags learned for this workspace: {' '.join(learned)}"
        summary = parse_summary(before + after) + note
        if any(f.tu.confidence != "precise" for f in before + after):
            raise Degraded(summary)
        return summary

    def impact():
        im = build_impact(ctx["before"], ctx["after"], ctx["dm"], ctx["sel"], svc.index, ctx.get("layers"), cfg.analysis)
        ctx["impact"] = im
        store.put_blob(rid, "impact", im)
        return f"{len(im.nodes)} node(s), {len(im.edges)} edge(s), blast {len(im.blast)}"

    def detectors():
        findings = run_detectors(DetectorContext(ctx["before"], ctx["after"], ctx["dm"], ctx["impact"], cfg.analysis))
        ctx["findings"] = findings
        store.put_findings(rid, findings)
        return f"{len(findings)} finding(s)"

    def board():
        notes: list[str] = []
        resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
        bctx = BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
                            ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root)))
        bs = build_boards(bctx)
        try:                                   # change stories (spec 2026-10-04); the boards stand without them
            bs.stories, bs.story_details = build_stories(bctx, bs.home or None, bs.analysis)
        except Exception as e:
            notes.append(f"stories failed: {type(e).__name__}: {e}")
        # file tags (spec §14.3): every graph node and finding, from one more lookup of the files not yet resolved
        findings, im = ctx["findings"], ctx["impact"]
        decl = {f"field:{a.field}": a.record_file for fx in ctx["before"] + ctx["after"] for a in fx.fields if a.record_file}
        locals_ = sorted({n.file for n in im.nodes.values() if n.file} | set(decl.values())
                         | {e.file for f in findings for e in f.evidence if e.file})
        by_local = local_files(locals_, resolve(locals_), str(cfg.workspace.root), system_include_dirs(svc.toolchain))
        node_files = impact_node_files(im, by_local, decl)
        for f in findings:
            f.files = finding_files(f, node_files, by_local)
        store.put_findings(rid, findings)
        ctx["node_files"], ctx["local_files"] = node_files, by_local
        store.put_blob(rid, "node_files", node_files)          # on-demand AI tags its text with these
        boardstore.save(store, rid, bs, {f.id: f.files for f in findings})
        ctx["boards"] = bs
        if bs.note:
            notes.append(bs.note)
        if notes:
            raise Degraded("; ".join(notes))
        if bs.board is not None:
            b = bs.board
            return f"{len(b.nodes)} node(s), {len(b.flows)} flow(s), {len(b.impacts)} annotation(s)"
        return (f"{len(bs.clusters)} cluster board(s), up to {max(len(b.nodes) for b in bs.clusters.values())} node(s) "
                f"each, {sum(len(b.flows) for b in bs.clusters.values())} flow(s)")

    def llm():
        findings = store.list_findings(rid)
        snippets = collect_snippets(ctx["impact"], ctx["cs"], ctx["after"])
        bs = ctx.get("boards")
        b = None if bs is None else bs.board or boardstore.merge(list(bs.clusters.values()), bs.overview.about)
        top = [] if bs is None or bs.stories is None else [   # the riskiest behaviour stories get AI titles up front
            bs.story_details[s.id] for s in bs.stories.stories if s.kind == "behaviour" and not s.collapsed]
        sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens,
                              board=b, concurrency=cfg.llm.concurrency, upfront_flows=cfg.llm.upfront_flows,
                              node_files=ctx.get("node_files"), ledger=svc.ledger, rid=rid, stories=top,
                              upfront_stories=cfg.llm.upfront_stories)
        if bs is not None and bs.stories is not None:          # the list shows the retold titles too
            bs.stories.stories = [bs.story_details[s.id].story for s in bs.stories.stories]
        store.put_findings(rid, findings)
        store.put_blob(rid, "storyboard", sb)
        if bs is not None:                     # the AI pass rewrote flows and the summary on the stored boards' objects
            boardstore.save(store, rid, bs, {f.id: f.files for f in findings})
        ctx["storyboard"] = sb
        if svc.llm is None:
            raise Degraded("no LLM configured; deterministic storyboard only")
        if sb.llm_error:
            raise Degraded(sb.llm_error)
        if sb.style_dropped:
            return f"{sb.style_dropped} AI output(s) broke the house style and were dropped"

    def finalize():
        sb = ctx.get("storyboard")
        if status.get("ingest") not in ("ok", "degraded"):
            store.set_review_status(rid, "failed")
        elif all(status.get(s) == "ok" for s in STAGES if s != "finalize"):
            store.set_review_status(rid, "done", sb.risk if sb else None)
        else:
            store.set_review_status(rid, "degraded", sb.risk if sb else None)

    from codetortoise.llm.ondemand import _lock
    # an explanation still writing this review's board or findings finishes first; new ones wait for the run
    with _lock(rid):
        store.put_blob(rid, "file_summaries", {})       # they describe the old diff
        for name, fn in [("ingest", ingest), ("swarm_read", swarm_read), ("diffmap", diffmap), ("tu_select", tu_select),
                         ("layers", layers), ("facts", facts), ("impact", impact), ("detectors", detectors),
                         ("board", board), ("llm", llm), ("finalize", finalize)]:
            stage(name, fn)


class JobRunner:
    """Single background worker: reviews and index rebuilds run one at a time."""

    def __init__(self, svc: Services):
        self.svc = svc
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tortoise-jobs")
        self.index_building = False
        # AI jobs (explanations, @tortoise) run beside reviews, not behind them
        self._ai = ThreadPoolExecutor(max(1, svc.cfg.llm.concurrency), thread_name_prefix="tortoise-ai")
        self.ai_jobs: dict[int, list[dict]] = {}
        self._ai_ids: dict[int, int] = {}
        self._ai_lock = threading.Lock()

    def submit_ai(self, rid: int, user: str, kind: str, target: str, fn: Callable[[], None]) -> dict:
        """Queue one AI job for review `rid`; its status ("running", "done", "failed", "refused") is kept in
        `ai_jobs` for the review's AI view."""
        with self._ai_lock:
            jobs = self.ai_jobs.setdefault(rid, [])
            self._ai_ids[rid] = self._ai_ids.get(rid, 0) + 1       # never reused, though only the last 50 are kept
            job = {"id": self._ai_ids[rid], "user": user, "kind": kind, "target": target, "status": "running", "error": None}
            jobs.append(job)
            del jobs[:-50]
        self._dispatch_ai(job, fn)
        return job

    def _dispatch_ai(self, job: dict, fn: Callable[[], None]) -> None:
        self._ai.submit(self._run_ai, job, fn)

    @staticmethod
    def _run_ai(job: dict, fn: Callable[[], None]) -> None:
        from codetortoise.llm.ledger import Refused
        from codetortoise.llm.ondemand import Changed, Unchecked
        try:
            fn()
            job["status"] = "done"
        except Refused as e:
            job["status"], job["error"] = "refused", e.reason
        except (Unchecked, Changed) as e:
            job["status"], job["error"] = "failed", str(e)
        except Exception as e:  # shown to whoever asked
            job["status"], job["error"] = "failed", f"{type(e).__name__}: {e}"[:300]
            log.warning("AI job %s failed: %s", job, e)

    def start(self) -> None:
        self._thread.start()

    def submit_review(self, rid: int) -> None:
        self.svc.store.set_review_status(rid, "queued")
        self._q.put(("review", rid))

    def submit_index(self) -> None:
        self._q.put(("index", None))

    def stop(self) -> None:
        self._q.put(None)

    def _loop(self) -> None:
        while True:
            job = self._q.get()
            if job is None:
                return
            kind, arg = job
            try:
                if kind == "review":
                    run_review(arg, self.svc)
                elif kind == "index":
                    self.index_building = True
                    self.svc.build_index()
            except Exception:
                log.error("job %s failed: %s", job, traceback.format_exc())
            finally:
                self.index_building = False
