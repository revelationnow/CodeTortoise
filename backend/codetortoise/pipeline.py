"""Staged review pipeline and background job runner."""
from __future__ import annotations

import hashlib
import logging
import queue
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from codetortoise import boardstore
from codetortoise.board import BoardContext, analyse, build_boards, is_test_path
from codetortoise.brief import Brief, cache_key
from codetortoise.detectors.base import DetectorContext, renumber, run_detectors
from codetortoise.diffmap import map_changes
from codetortoise.facts.model import Facts, relative_records
from codetortoise.facts.runner import build_requests, parse_summary, run_extraction
from codetortoise.facts_prep import prepare_facts
from codetortoise.grouping import StoryPlan, rules_plan
from codetortoise.impact import ImpactModel, build_impact
from codetortoise.llm.brief_context import brief_context
from codetortoise.llm.review import apply_verdicts, review_stories
from codetortoise.llm.stories import STORY_RULES_VERSION, form_stories
from codetortoise.llm.storyboard import AiContext, build_storyboard, judge_side_effects
from codetortoise.llm.threads import prompt as threads_prompt
from codetortoise.llm.threads import write_threads
from codetortoise.paths import canon
from codetortoise.pieces import build_pieces
from codetortoise.provenance import finding_files, impact_node_files, local_files
from codetortoise.reading import READING_VERSION, build_reading, headline_facts
from codetortoise.repeated import find_repeated
from codetortoise.sequence import file_lines
from codetortoise.services import Services
from codetortoise.stories import build_stories
from codetortoise.swarm import SwarmError
from codetortoise.targets import resolve_targets
from codetortoise.tu_select import TuSelection, field_follow_up, select_tus
from codetortoise.vcs.model import ChangeSet

log = logging.getLogger(__name__)


def _read_text(path: str) -> str | None:
    """A workspace file's text, for the header facts' search of files outside the change."""
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return None

STAGES = ["ingest", "swarm_read", "diffmap", "tu_select", "layers", "facts", "impact", "detectors", "pieces", "stories",
          "review", "verdicts", "board", "llm", "reading", "finalize"]
DEPS = {"swarm_read": ["ingest"], "diffmap": ["ingest"], "tu_select": ["diffmap"], "facts": ["tu_select"],
        "impact": ["facts", "tu_select", "diffmap"], "detectors": ["impact"], "pieces": ["impact", "detectors"],
        "stories": ["pieces"], "review": ["stories"], "verdicts": ["detectors"], "board": ["impact", "detectors"],
        "llm": ["detectors"], "reading": ["board"]}


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

def run_review(rid: int, svc: Services, fresh: bool = False) -> None:
    """Run every stage of review `rid`. `fresh`: the strong model forms the stories again, even for a change it has
    seen (no cached brief)."""
    store, cfg = svc.store, svc.cfg
    store.reset_stages(rid, STAGES)
    if svc.ledger:
        svc.ledger.prune()                      # logged requests past llm.request_log_days
    store.clear_ticks(rid)                     # a re-run starts every reader's reading plan over
    store.set_review_status(rid, "running")
    status: dict[str, str] = {}
    ctx: dict = {}
    cls = store.get_review(rid)["cls"]

    def stage(name: str, fn) -> None:
        if any(status.get(d) not in ("ok", "degraded") for d in DEPS.get(name, [])):
            status[name] = "skipped"
            store.set_stage(rid, name, "skipped", "missing inputs")
            if name == "reading":
                drop_reading()
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

    def board_context(notes: list[str]) -> BoardContext:
        resolve = depot_resolver(svc.source, ctx["cs"], cfg.workspace.root, notes)
        return BoardContext(ctx["cs"], ctx["dm"], ctx["before"], ctx["after"], ctx["impact"], ctx["findings"],
                            ctx.get("layers"), cfg.analysis, resolve, root=canon(str(cfg.workspace.root)))

    def pieces():
        """The change cut into pieces, by target and CL, with links and cards (spec 2026-10-05-two-tier-stories §3)."""
        bctx = board_context([])
        a = analyse(bctx)
        rep = find_repeated(bctx, a.x)
        files = sorted({f.local for f in ctx["cs"].files if f.local} | {t.file for t in ctx["dm"].types})

        def triple(f: str) -> str | None:
            g = svc.toolchain.group_of(f)
            return g.target if g else None
        ws = cfg.workspace

        def resolve(paths: list[str]) -> dict[str, list[str]]:
            return resolve_targets(paths, cfg.targets, bctx.root, svc.cdb, str(ws.build_root) if ws.build_root else None,
                                   triple, svc.index.transitive_includers)
        targets = resolve(files)
        ctx["resolve_targets"] = resolve        # the review's facts resolve call sites in files without a piece
        ps = build_pieces(bctx, a, targets, svc.index.transitive_includers, rep)
        ctx["pieces"], ctx["repeated"], ctx["analysis"] = ps, rep, a
        store.put_blob(rid, "pieces", ps)
        names = sorted({t for p in ps.pieces for t in p.targets})
        return f"{len(ps.pieces)} piece(s), {len(ps.links)} link(s); target(s): {', '.join(names) or 'none'}"

    def stories():
        """Which pieces form which story: the strong model's plan (spec §4), reused for a change it has seen, or the
        rules' (§6). The plan is stored as the review's brief."""
        ps, strong = ctx["pieces"], cfg.llm.strong
        if svc.strong is None or strong is None:
            plan = StoryPlan(stories=rules_plan(ps))
            brief = Brief(overview=ps.overview, pieces=ps, plan=plan)
            msg = f"{len(plan.stories)} stories from {len(ps.pieces)} piece(s), by the rules (no strong model configured)"
        else:
            key = cache_key(ps, strong.model, STORY_RULES_VERSION, strong.agree)
            hit = None if fresh else store.find_brief(key)
            if hit is not None:
                brief = Brief.model_validate(hit)
                brief.pieces, brief.overview, plan = ps, ps.overview, brief.plan
            else:
                plan = form_stories(svc.strong, svc.ledger, rid, ps, ctx["analysis"].x, strong, ctx["findings"],
                                    weak=svc.llm)
                brief = Brief(key=key, model=strong.model, complete=plan.complete, overview=ps.overview, pieces=ps,
                              plan=plan)
            unsorted = sum(len(s.placements) for s in plan.stories if s.unsorted)
            formed = [s for s in plan.stories if not s.unsorted]
            msg = (f"{len(formed)} stories formed by {strong.model}" + (" (reused: this change was seen before)" if hit else "")
                   + f", {sum(len(s.placements) for s in formed)} piece(s) placed, {unsorted} unsorted")
        ctx["plan"], ctx["brief"] = plan, brief
        store.put_brief(rid, brief.key, brief)
        store.put_blob(rid, "story_findings", ctx["findings"])   # as tier 1 saw them, before the review renumbers them
        if plan.notes:
            raise Degraded(msg + "; " + "; ".join(plan.notes))
        return msg

    def review():
        """The strong model judges each story's findings against facts code prepared for them (spec §5); a reused brief
        brings its verdicts. Findings take the verdicts' severities before the board is drawn."""
        brief, findings, ps, strong = ctx["brief"], ctx["findings"], ctx["pieces"], cfg.llm.strong
        x = ctx["analysis"].x
        brief.facts = prepare_facts(x, findings, ps.targets, svc.index.transitive_includers, _read_text,
                                    ctx.get("resolve_targets"))
        if svc.strong is None or strong is None:
            store.put_brief(rid, brief.key, brief)
            return f"no strong model: {len(findings)} finding(s) left to the detectors and the AI's side-effect pass"
        got = review_stories(svc.strong, svc.ledger, rid, ctx["plan"], ps, x, strong, findings, brief.facts,
                             skip=set(brief.reviewed), weak=svc.llm)
        brief.verdicts.update(got.verdicts)
        brief.reviewed = list(dict.fromkeys(brief.reviewed + got.reviewed))
        apply_verdicts(findings, brief.verdicts)
        store.put_findings(rid, findings)
        store.put_brief(rid, brief.key, brief)
        mine = [f for f in findings if f.verdict_source == "tier1"]
        msg = (f"{len(mine)} finding(s) judged by {strong.model}: {sum(f.verdict == 'hazard' for f in mine)} hazard(s), "
               f"{sum(f.verdict == 'needs_review' for f in mine)} to confirm, {sum(f.verdict == 'no_hazard' for f in mine)} "
               "no hazard")
        if got.notes:
            raise Degraded(msg + "; " + "; ".join(got.notes))
        return msg

    def verdicts():
        """The AI judges side effects before the board is drawn, so flows and stories take the verdicts' colours.
        Side effects the strong model already judged are left alone."""
        findings = ctx["findings"]
        effects = [f for f in findings if f.side_effect]
        todo = [f for f in effects if f.verdict_source != "tier1"]
        if not effects:
            return "no side effects"
        if not todo:
            return f"all {len(effects)} side effect(s) judged by the strong model"
        if svc.llm is None:
            return f"no LLM: {len(todo)} side effect(s) not assessed (shown neutral)"
        snippets = collect_snippets(ctx["impact"], ctx["cs"], ctx["after"])
        aictx = AiContext(ctx["impact"], findings, snippets, cfg.llm.max_context_tokens)
        judged, error = judge_side_effects(svc.llm, aictx, findings, cfg.llm.upfront_side_effects, ledger=svc.ledger, rid=rid)
        renumber(findings)                     # a hazard is now high: ids follow severity again
        store.put_findings(rid, findings)
        hazards = sum(f.verdict == "hazard" for f in todo)
        msg = f"{judged} of {len(todo)} side effect(s) judged, {hazards} hazard(s)"
        if error:
            raise Degraded(f"{msg}; {error}")
        return msg + ("" if judged == len(todo) else "; the rest not assessed (shown neutral)")

    def board():
        notes: list[str] = []
        bctx = board_context(notes)
        resolve = bctx.depots_for
        bs = build_boards(bctx)
        try:                                   # change stories (spec 2026-10-04); the boards stand without them
            bs.stories, bs.story_details = build_stories(bctx, bs.home or None, bs.analysis, plan=ctx.get("plan"),
                                                         pieces=ctx.get("pieces"), rep=ctx.get("repeated"))
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

        def brief_for(kind: str, target: str) -> str:
            """The brief's part for an up-front job's target (spec 2026-10-05-two-tier-stories §8)."""
            if kind == "finding":
                f = next((f for f in findings if f.id == target), None)
                return brief_context(store, rid, finding=f) if f is not None else ""
            return brief_context(store, rid, **{kind: target})
        snippets = collect_snippets(ctx["impact"], ctx["cs"], ctx["after"])
        bs = ctx.get("boards")
        b = None if bs is None else bs.board or boardstore.merge(list(bs.clusters.values()), bs.overview.about)
        top = [] if bs is None or bs.stories is None else [   # the riskiest behaviour stories get AI titles up front
            bs.story_details[s.id] for s in bs.stories.stories
            if s.kind == "behaviour" and not s.collapsed and s.source != "tier1"]      # tier 1 wrote its own
        sb = build_storyboard(ctx["impact"], findings, ctx.get("layers"), snippets, svc.llm, cfg.llm.max_context_tokens,
                              board=b, concurrency=cfg.llm.concurrency, upfront_flows=cfg.llm.upfront_flows,
                              node_files=ctx.get("node_files"), ledger=svc.ledger, rid=rid, stories=top,
                              upfront_stories=cfg.llm.upfront_stories,
                              upfront_findings=cfg.llm.upfront_findings, brief_for=brief_for)
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

    def drop_reading() -> None:
        """A run that builds no reading leaves none: the last run's would read as this one's."""
        store.replace_blobs(rid, ["reading", "reading_head", "lines"], ["story_reading:"], {})

    def reading():
        """How the review reads (spec 2026-10-07-review-reading): threads, connections, To check, each story's tiles."""
        try:
            return read()
        except Exception:                      # Degraded too, unless it only notes what the stored reading lacks
            if not ctx.get("reading_stored"):
                drop_reading()
            raise

    def read():
        bs = ctx.get("boards")
        if bs is None or bs.stories is None or bs.analysis is None:
            raise Degraded("no stories to read")
        x = bs.analysis.x
        root = x.c.root.rstrip("/") + "/"

        def rel(p: str) -> str:
            return p[len(root):] if p.startswith(root) else p
        ps = ctx.get("pieces")
        targets = dict(ps.targets) if ps is not None else {}
        resolve = ctx.get("resolve_targets")
        missing = sorted({c.file for c in x.calls_after if c.file not in targets})
        if resolve is not None and missing:
            targets.update(resolve(missing))
        texts: dict[str, str | None] = {}

        def read_text(path: str) -> str | None:
            if path not in texts:
                texts[path] = _read_text(path)
            return texts[path]
        has_tests = any(is_test_path(rel(f)) for f in svc.index.files()) or \
            any(is_test_path(rel(f.local)) for f in ctx["cs"].files)
        lines = file_lines(ctx["cs"])
        r, per = build_reading(bs.stories, x.c, details=bs.story_details, analysis=bs.analysis, pieces=ps,
                               targets=targets, has_tests=has_tests, includers=svc.index.transitive_includers,
                               test_callers=lambda name: {c.path for c in svc.index.callers_of(name)
                                                          if is_test_path(rel(c.path))},
                               read_text=read_text, lines=lines)
        notes: list[str] = []
        strong = cfg.llm.strong
        if svc.strong is None or strong is None:
            told = "fixed thread text (no strong model)"
        else:
            cls_text = {m.cl: m.description for m in ctx["cs"].cls}
            key = hashlib.sha256(f"{READING_VERSION}|{strong.model}|{threads_prompt(r, bs.stories, cls_text)}"
                                 .encode()).hexdigest()
            cached = store.get_blob(rid, "thread_text")
            if cached and cached.get("key") == key and not fresh:
                by: str | None = strong.model
                for t in r.threads:
                    t.name, t.purpose, t.text_source = cached["threads"].get(t.id, (t.name, t.purpose, t.text_source))
                r.whole, r.whole_source = cached["whole"], cached["whole_source"]
                for k in r.connections:
                    k.text = cached["connections"].get(f"{k.a}-{k.b}", k.text)
            else:
                notes, by = write_threads(svc.strong, svc.ledger, rid, r, bs.stories, cls_text, weak=svc.llm)
                if not notes:
                    store.put_blob(rid, "thread_text", {
                        "key": key, "threads": {t.id: (t.name, t.purpose, t.text_source) for t in r.threads},
                        "whole": r.whole, "whole_source": r.whole_source,
                        "connections": {f"{k.a}-{k.b}": k.text for k in r.connections}})
            told = (f"thread text by {by}" if by == strong.model else
                    f"thread text by {by} (the strong model failed)" if by else "fixed thread text (the AI's answer failed)")
        store.replace_blobs(rid, ["reading", "reading_head", "lines"], ["story_reading:"],
                            {"reading": r, "reading_head": headline_facts(r, x.c.findings),
                             "lines": {d: fl.model_dump() for d, fl in lines.items()},
                             **{f"story_reading:{sid}": sr for sid, sr in per.items()}})
        ctx["reading_stored"] = True
        store.prune_marks(rid, {k.key for k in r.checks + r.cleared})
        msg = (f"{len(r.threads)} thread(s), {sum(k.shown for k in r.connections)} connection(s) shown, "
               f"{len(r.checks)} check(s); {told}")
        if notes:
            raise Degraded(msg + "; " + "; ".join(notes))
        return msg

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
                         ("pieces", pieces), ("stories", stories), ("review", review),
                         ("verdicts", verdicts), ("board", board), ("llm", llm), ("reading", reading),
                         ("finalize", finalize)]:
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

    def submit_review(self, rid: int, fresh: bool = False) -> None:
        self.svc.store.set_review_status(rid, "queued")
        self._q.put(("review", (rid, fresh)))

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
                    run_review(arg[0], self.svc, fresh=arg[1])
                elif kind == "index":
                    self.index_building = True
                    self.svc.build_index()
            except Exception:
                log.error("job %s failed: %s", job, traceback.format_exc())
            finally:
                self.index_building = False
