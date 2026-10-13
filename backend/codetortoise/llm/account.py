"""A behaviour story's account (spec 2026-10-12-story-account-and-panels §1): the weak model retells, section by
section, what the strong model and the analysis found about the story."""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from codetortoise.llm.client import LlmClient, LlmError
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import MODES, AiContext, Job, _facts_for_nodes, _finding_text, _styled, budget, run_job
from codetortoise.reading import AccountPart, StoryReading
from codetortoise.stories import StoryDetail

ACCOUNT_VERSION = 1                    # bump with every change to the prompt below: cached accounts are asked again
PURPOSE, EFFECTS = "What it is for", "What it means for the rest"


class _Section(BaseModel):
    kind: str                          # anything but purpose, flow or effects is dropped, not a failed answer
    flow: str | None = None
    text: str = ""
    cites: list[str] = Field(default_factory=list)


class _AccountOut(BaseModel):
    sections: list[_Section] = Field(default_factory=list)


def account_job(ctx: AiContext, d: StoryDetail, sr: StoryReading) -> Job:
    """The account of story `d`, written onto its reading `sr`. A section is kept only when it keeps the house style,
    cites the story's code or findings and, for a flow section, names one of the story's flows; the first of each
    kind is kept, in the order purpose, the story's flows, effects."""
    st, impact = d.story, ctx.impact
    flows = [fl for fl in d.board.flows if fl.id in st.flows]
    mentioned = list(dict.fromkeys(st.nodes + [n for fl in flows for n in fl.path]))
    nodes = [n for n in mentioned if n in impact.nodes]
    known = set(mentioned) | set(st.findings)
    said = [f"purpose: {st.purpose}"] if st.purpose else []
    said += [f"why {p.piece} belongs: {p.reason}" for p in st.placements]
    said += [f"check: {c}" for c in st.check] + [f"question: {q}" for q in st.questions]
    parts = [f"STORY {st.id} ({st.kind}): {st.title}\nshort text: {st.purpose or st.summary}\n"
             f"CITE FROM: {', '.join(mentioned + st.findings)}"]
    if st.source == "tier1" and said:
        parts.append("WHAT THE GROUPING MODEL SAID:\n" + "\n".join(said))
    parts.append("FLOWS (id | label | what it does):\n"
                 + ("\n".join(f"FLOW {fl.id} | {fl.text} | {fl.what}" for fl in flows) or "none"))
    parts.append("CALL PATHS:\n" + ("\n".join(p.text for p in sr.paths) or "none"))
    parts.append("BEFORE → AFTER:\n" + ("\n".join(
        c.text + (f" ({c.before} → {c.after})" if c.before or c.after else "") for c in sr.contracts) or "none"))
    parts.append("WHERE:\n" + ("\n".join(f"{w.path}: {', '.join(fn.label for fn in w.functions)}" for w in sr.where)
                               or "none"))
    parts.append("FINDINGS:\n" + ("\n\n".join(_finding_text(f) for f in ctx.findings
                                              if f.id in st.findings and not f.sink) or "none"))   # a shared sink's: never
    parts.append("GRAPH FACTS:\n" + _facts_for_nodes(impact, nodes))
    parts += [f"CODE {n}:\n{ctx.snippets[n]}" for n in nodes if n in ctx.snippets]
    label = {fl.id: fl.text for fl in flows}

    def apply(out: _AccountOut) -> int:
        dropped, kept = 0, {}
        for s in out.sections:
            key, text = (f"flow:{s.flow}" if s.kind == "flow" else s.kind), s.text.strip()
            if (s.kind not in ("purpose", "flow", "effects") or key in kept or not text
                    or (s.kind == "flow" and s.flow not in label) or not set(s.cites) & known):
                continue
            if not _styled(text, "explanation"):
                dropped += 1
                continue
            heading = label[s.flow] if s.kind == "flow" else PURPOSE if s.kind == "purpose" else EFFECTS
            kept[key] = AccountPart(kind=s.kind, heading=heading, text=text, cites=[c for c in s.cites if c in known])
        order = ["purpose", *(f"flow:{fl.id}" for fl in flows), "effects"]
        sr.account = [kept[k] for k in order if k in kept]
        sr.account_files = ctx.prompt_files(nodes, st.findings) if sr.account else None
        return dropped
    prompt = ("Write a reviewer's account of this change story, in sections. First a purpose section: what the story "
              "is for and why. Then one flow section per FLOW below, in that order, with its id in `flow`: how the "
              "entry reaches the changed code and what the change does there. Last an effects section: who else sees "
              "the effect and what to watch. Each section is one paragraph of 2-5 sentences. Cite in each section the "
              f"node and finding ids it relies on, from CITE FROM.\n{MODES['explanation']}\n\n"
              + budget(parts, ctx.per_call))
    return Job("story_account", st.id, prompt, _AccountOut, apply)


def account_key(ctx: AiContext, d: StoryDetail, sr: StoryReading) -> str:
    """What a story's account is written from, less what a model may rewrite earlier in each run (spec §1.4): the
    story's title and short text and its flows' text (the rule text behind them follows from the facts kept here), and
    the findings' severities the verdicts set. A plain re-run whose code and analysis are unchanged then reuses the
    account although those answers came back worded otherwise."""
    st = d.story
    flows = [fl for fl in d.board.flows if fl.id in st.flows]
    nodes = [n for n in dict.fromkeys(st.nodes + [n for fl in flows for n in fl.path]) if n in ctx.impact.nodes]
    said = [st.purpose, *(f"{p.piece}: {p.reason}" for p in st.placements), *st.check, *st.questions]
    found = [(f.id, f.kind, f.title, f.nodes, [(e.text, e.file, e.line) for e in f.evidence])
             for f in ctx.findings if f.id in st.findings and not f.sink]
    return repr((st.id, st.kind, st.source, said, st.nodes, st.findings,
                 [(fl.id, fl.text, fl.path) for fl in flows],
                 [p.model_dump() for p in sr.paths], [c.model_dump() for c in sr.contracts],
                 [w.model_dump() for w in sr.where], found, _facts_for_nodes(ctx.impact, nodes),
                 [ctx.snippets.get(n) for n in nodes], ctx.per_call))


def write_accounts(llm: LlmClient, ctx: AiContext, details: dict[str, StoryDetail], per: dict[str, StoryReading],
                   cached: dict, *, fresh: bool = False, concurrency: int = 1, ledger: Ledger | None = None,
                   rid: int | None = None) -> tuple[dict, int, list[str]]:
    """Write the account of every behaviour story that is not collapsed (spec §1.4): one call each, in parallel; a
    story whose inputs (`account_key`) and weak model are unchanged reuses its cached account unless `fresh`. Returns the cache to
    store (sid → key, account, files), the sections dropped for style and the stage notes."""
    jobs = {sid: account_job(ctx, d, per[sid]) for sid, d in details.items()
            if sid in per and d.story.kind == "behaviour" and not d.story.collapsed}
    keys = {sid: hashlib.sha256(f"{ACCOUNT_VERSION}|{llm.model}|{account_key(ctx, details[sid], per[sid])}".encode()).hexdigest()
            for sid, j in jobs.items()}
    cache: dict = {}
    todo: list[str] = []
    for sid in jobs:
        hit = cached.get(sid)
        if hit and hit.get("key") == keys[sid] and not fresh:
            per[sid].account = [AccountPart(**p) for p in hit["account"]]
            per[sid].account_files = hit.get("files")
            cache[sid] = hit
        else:
            todo.append(sid)

    def one(sid: str) -> tuple[str, int, str | None]:
        try:
            return sid, run_job(llm, jobs[sid], ledger, rid), None
        except Refused as e:
            return sid, 0, f"AI budget: {e.reason}"
        except Exception as e:  # that story keeps its short text
            return sid, 0, str(e) if isinstance(e, LlmError) else f"{type(e).__name__}: {e}"
    dropped, failed = 0, []
    with ThreadPoolExecutor(max(1, concurrency), thread_name_prefix="tortoise-account") as pool:
        for sid, n, error in pool.map(one, todo):
            dropped += n
            if error is None:
                cache[sid] = {"key": keys[sid], "account": [p.model_dump() for p in per[sid].account],
                              "files": per[sid].account_files}
            else:
                failed.append(error)
    return cache, dropped, [f"{len(failed)} story account(s) not written: {failed[0]}"] if failed else []
