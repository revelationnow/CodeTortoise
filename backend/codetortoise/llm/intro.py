"""The strong model introduces the review (spec 2026-10-09-review-introduction §4): the change as a whole in 4 to 6
sentences, each thread in 3 to 5, and the order to read the threads in with a reason for each.

One tier-1 call per review, after the thread text so it sees the final thread names. Each part is checked on its own:
cites only listed ids, the sentence counts, the house style; the route must hold every thread exactly once. A part that
fails keeps its fixed text from reading.py.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import _styled
from codetortoise.llm.style import STYLE
from codetortoise.llm.threads import _SENT, _ids
from codetortoise.llm.tiers import TiersFailed, done_text, tried_note, try_tiers
from codetortoise.reading import KIND_LABEL, Reading, RouteStep
from codetortoise.stories import StorySet

INTRO_VERSION = 1                     # bump with every change to the introduction's prompt or checks (keys its cache)
CHECKS_SHOWN = 6

SYSTEM = ("You are a senior C/C++ reviewer introducing a change to reviewers who have not seen it. Use only what you "
          'are given. Reply with one JSON object: {"whole", "whole_cites", "threads": [{"id", "intro", "cites"}], '
          '"route": [{"thread", "reason", "skim", "cites"}]}. ' + STYLE)

ASK = """Each thread is a group of stories joined by calls or shared data. Write "whole": the change as a whole in 4 to \
6 sentences, saying its purpose, its scope (its CLs, the parts of the code it touches, how many threads) and its main \
risk. For each thread write "intro": 3 to 5 sentences saying what it changes and why, where in the code, what could go \
wrong (from its open checks) and how much is open. Then write "route": every thread once, in the order a reviewer \
should read them, each with a one-sentence "reason"; set "skim" to true for a thread worth only a skim. Cite the ids \
(T1, S2, N4, CL12) behind each part in "whole_cites" and "cites"; cite nothing that is not listed."""


class _Intro(BaseModel):
    id: str
    intro: str = ""
    cites: list[str] = Field(default_factory=list)


class _Step(BaseModel):
    thread: str
    reason: str = ""
    skim: bool = False
    cites: list[str] = Field(default_factory=list)


class _Out(BaseModel):
    whole: str = ""
    whole_cites: list[str] = Field(default_factory=list)
    threads: list[_Intro] = Field(default_factory=list)
    route: list[_Step] = Field(default_factory=list)


def prompt(reading: Reading, ss: StorySet, cls: dict[int, str]) -> str:
    by = {s.id: s for s in ss.stories}
    lines = ["THREAD DETAILS (id | name | purpose | CLs | open checks):"]
    for t in reading.threads:
        lines.append(f"{t.id} | {t.name} | {t.purpose} | {', '.join(f'CL {c}' for c in t.cls) or '-'} | {t.open_checks}")
        if t.modules:
            lines.append(f"  modules: {', '.join(t.modules)}")
        if t.files:
            lines.append(f"  files: {', '.join(t.files)}")
        lines.append("  stories: " + "; ".join(f"{s} {by[s].title}" + (f": {by[s].purpose}" if by[s].purpose else "")
                                               + f" ({by[s].kind})" for s in t.stories if s in by))
        mine = [k for k in reading.checks if k.thread == t.id]
        if mine:
            more = f" +{len(mine) - CHECKS_SHOWN} more" if len(mine) > CHECKS_SHOWN else ""
            lines.append("  open checks: " + "; ".join(f"{KIND_LABEL[k.kind]}: {k.text}" for k in mine[:CHECKS_SHOWN])
                         + more)
    lines.append("CONNECTIONS (a | b | kind | text):")
    lines += [f"{k.a} | {k.b} | {k.kind} | {k.text}" for k in reading.connections]
    used = sorted({c for t in reading.threads for c in t.cls})
    if used:
        lines.append("CL DESCRIPTIONS:")
        lines += [f"CL {c} (a hint from its author, not the source of truth): {cls.get(c, '').strip() or '(none)'}"
                  for c in used]
    return ASK + "\n\n" + "\n".join(lines)


def write_intro(strong: LlmClient, ledger: Ledger | None, rid: int | None, reading: Reading, ss: StorySet,
                cls: dict[int, str], weak: LlmClient | None = None) -> tuple[list[str], str | None]:
    """Write `reading`'s introduction in place from one checked answer; returns notes on the parts that kept their fixed
    text, and the model that answered (None: every fixed text stays). The strong model failing is tried fresh, then on
    the weak model."""
    text = prompt(reading, ss, cls)

    def ask(llm: LlmClient) -> _Out:
        return llm.complete_json(SYSTEM, text, _Out)
    try:
        tried = try_tiers(ledger, rid, "intro", "intro", ask, strong, weak)
    except Refused as e:
        return [f"introduction: AI budget: {e.reason}; the fixed text stays"], None
    except TiersFailed as e:  # the fixed text stands
        return [tried_note("introduction", e.failures, "the fixed text stays")], None
    out = tried.value
    said = [] if tried.tier == "strong" else [tried_note("introduction", tried.failures, done_text(tried, "wrote it"))]
    ids = _ids(reading, ss)

    def ok(text: str, cites: list[str], lo: int, hi: int) -> bool:
        cs = [c.replace(" ", "") for c in cites]
        return (bool(text) and bool(cs) and all(c in ids for c in cs) and lo <= len(_SENT.split(text)) <= hi
                and _styled(text, "explanation"))
    whole = out.whole.strip()
    bad_whole = not ok(whole, out.whole_cites, 4, 6)
    if not bad_whole:
        reading.whole, reading.whole_source = whole, "llm"
    got = {a.id: a for a in out.threads}
    bad_threads = 0
    for t in reading.threads:
        a = got.get(t.id)
        intro = a.intro.strip() if a else ""
        if a and ok(intro, a.cites, 3, 5):
            t.intro, t.intro_source = intro, "llm"
        else:
            bad_threads += 1
    bad_route = not (sorted(s.thread for s in out.route) == sorted(t.id for t in reading.threads)
                     and all(ok(s.reason.strip(), s.cites, 1, 1) for s in out.route))
    if not bad_route:
        reading.route = [RouteStep(thread=s.thread, reason=s.reason.strip(), skim=s.skim) for s in out.route]
        reading.route_source = "llm"
    if not (bad_whole or bad_threads or bad_route):
        return said, tried.model
    parts = (["the whole"] if bad_whole else []) + ([f"{bad_threads} thread(s)"] if bad_threads else []) + \
            (["the route"] if bad_route else [])
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return said + [f"introduction: {joined} kept the fixed text"], tried.model
