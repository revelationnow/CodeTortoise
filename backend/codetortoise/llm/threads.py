"""The strong model names the threads and tells the change as a whole (spec 2026-10-07-review-reading §9).

One tier-1 call per review, after the analysis. The model is given the threads with their stories, the connections
with their facts, the CL descriptions marked as hints and the open checks' counts. Every answer is checked: a thread's
text must cite ids from the input, a name has at most 6 words, a connection's rewording keeps its cited names and CLs;
a thread's key files are its listed files and its modules directories holding them; anything that fails keeps the fixed
text from reading.py.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import _styled, _titled
from codetortoise.llm.style import STYLE
from codetortoise.llm.tiers import TiersFailed, done_text, tried_note, try_tiers
from codetortoise.reading import MAX_FILES, MAX_MODULES, Reading
from codetortoise.stories import StorySet

NAME_WORDS = 6
MAX_LISTED = 40                       # a thread's files listed in the prompt
_TICKS = re.compile(r"`[^`]+`")
_CL = re.compile(r"\bCL ?\d+\b")
_SENT = re.compile(r"(?<=[.?!])\s+")

SYSTEM = ("You are a senior C/C++ reviewer explaining a change to other reviewers. Use only what you are given. Reply "
          'with one JSON object: {"threads": [{"id", "name", "purpose", "cites", "files", "modules"}], "whole", '
          '"whole_cites", "connections": [{"a", "b", "text"}]}. ' + STYLE)

ASK = """Each thread is a group of stories joined by calls or shared data. For each thread write a name (at most 6 \
words, what it does) and a purpose (one sentence). For each thread with files listed, also pick "files": at most 8 of \
its listed files, the ones a reviewer should look at first, and "modules": at most 4 directories (each ending in "/") \
holding those files that name the parts of the code it touches. Then write "whole": the change as a whole in 2 to 4 \
sentences, saying how the threads connect. You may reword each connection's text, but keep every name in backticks and \
every CL number it has. When the only tie between two threads is that they arrived together, say so plainly. Cite the \
ids (T1, S2, N4, CL12) that support each thread's text in "cites" and the whole's in "whole_cites"; cite nothing that is \
not listed."""


class _T(BaseModel):
    id: str
    name: str = ""
    purpose: str = ""
    cites: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)


class _C(BaseModel):
    a: str
    b: str
    text: str = ""


class _Out(BaseModel):
    threads: list[_T] = Field(default_factory=list)
    whole: str = ""
    whole_cites: list[str] = Field(default_factory=list)
    connections: list[_C] = Field(default_factory=list)


def prompt(reading: Reading, ss: StorySet, cls: dict[int, str], files: dict[str, list[tuple[str, int]]] | None = None) -> str:
    """`files`: each thread's changed files with their changed functions, most first (reading.thread_files)."""
    by = {s.id: s for s in ss.stories}
    lines = ["THREADS (id | open checks | CLs | stories: id title: purpose):"]
    for t in reading.threads:
        stories = "; ".join(f"{s} {by[s].title}" + (f": {by[s].purpose}" if by[s].purpose else "") for s in t.stories)
        lines.append(f"{t.id} | {t.open_checks} open checks | {', '.join(f'CL {c}' for c in t.cls) or '-'} | {stories}")
        fs = (files or {}).get(t.id, [])
        if fs:
            more = f" +{len(fs) - MAX_LISTED} more" if len(fs) > MAX_LISTED else ""
            lines.append("  files (changed functions): " + ", ".join(f"{p} ({n})" for p, n in fs[:MAX_LISTED]) + more)
    lines.append("CONNECTIONS (a | b | kind | text | facts):")
    lines += [f"{k.a} | {k.b} | {k.kind} | {k.text} | {' '.join(k.facts) or '-'}" for k in reading.connections]
    used = sorted({c for t in reading.threads for c in t.cls})
    if used:
        lines.append("CL DESCRIPTIONS:")
        lines += [f"CL {c} (a hint from its author, not the source of truth): {cls.get(c, '').strip() or '(none)'}"
                  for c in used]
    return ASK + "\n\n" + "\n".join(lines)


def _ids(reading: Reading, ss: StorySet) -> set[str]:
    ids = {t.id for t in reading.threads} | {s.id for s in ss.stories} | {n for s in ss.stories for n in s.nodes}
    ids |= {f for k in reading.connections for f in k.facts if re.fullmatch(r"[NS]\d+", f)}
    ids |= {f"CL{c}" for t in reading.threads for c in t.cls}
    return ids


def _keeps(fixed: str, facts: list[str], text: str) -> bool:
    """A reworded connection keeps the fixed text's names in backticks and its CLs; one with neither says "only" or
    "nothing" (the only tie is the bundle)."""
    need = _TICKS.findall(fixed) + [f for f in facts if f.startswith("CL ")]
    if need:
        return all(n in text for n in need)
    return bool(re.search(r"\b(only|nothing)\b", text, re.I))


def _pick(a: _T, listed: list[str], need_module: bool) -> tuple[list[str], list[str]] | None:
    """A thread's key files and modules from the answer, or None when they fail the check (spec
    2026-10-09-review-introduction §4.0): listed files only, directories holding one of them, within the limits."""
    files = list(dict.fromkeys(f.strip() for f in a.files if f.strip()))
    modules = list(dict.fromkeys(m.strip() for m in a.modules if m.strip()))
    ok = (1 <= len(files) <= MAX_FILES and len(modules) <= MAX_MODULES and (bool(modules) or not need_module)
          and all(f in listed for f in files)
          and all(m.endswith("/") and len(m) > 1 and any(f.startswith(m) for f in listed) for m in modules))
    return (files, modules) if ok else None


def write_threads(strong: LlmClient, ledger: Ledger | None, rid: int | None, reading: Reading, ss: StorySet,
                  cls: dict[int, str], weak: LlmClient | None = None,
                  files: dict[str, list[tuple[str, int]]] | None = None) -> tuple[list[str], str | None]:
    """Reword `reading` in place from one checked answer and take its pick of each thread's key files and modules
    (`files`: reading.thread_files); returns notes on what kept its fixed text, and the model that wrote the text (None:
    the fixed text stays). The strong model failing is tried fresh, then on the weak model (spec
    2026-10-08-llm-robustness §6)."""
    text = prompt(reading, ss, cls, files)

    def ask(llm: LlmClient) -> _Out:
        return llm.complete_json(SYSTEM, text, _Out)
    try:
        tried = try_tiers(ledger, rid, "threads", "threads", ask, strong, weak)
    except Refused as e:
        return [f"thread text: AI budget: {e.reason}; the fixed text stays"], None
    except TiersFailed as e:  # the fixed text stands
        return [tried_note("thread text", e.failures, "the fixed text stays")], None
    out = tried.value
    said = [] if tried.tier == "strong" else [tried_note("thread text", tried.failures, done_text(tried, "wrote it"))]
    ids = _ids(reading, ss)

    def cited(cites: list[str]) -> bool:
        cs = [c.replace(" ", "") for c in cites]
        return bool(cs) and all(c in ids for c in cs)
    got = {t.id: t for t in out.threads}
    listed = {tid: [p for p, _ in fs[:MAX_LISTED]] for tid, fs in (files or {}).items()}
    bad_threads = bad_picks = 0
    for t in reading.threads:
        a = got.get(t.id)
        name, purpose = (a.name.strip(), a.purpose.strip()) if a else ("", "")
        if (a and cited(a.cites) and name and len(name.split()) <= NAME_WORDS and _titled(name) and purpose
                and len(_SENT.split(purpose)) == 1 and _styled(purpose, "explanation")):
            t.name, t.purpose, t.text_source = name, purpose, "llm"
        else:
            bad_threads += 1
        if listed.get(t.id):
            pick = _pick(a, listed[t.id], bool(t.modules)) if a else None
            if pick:
                t.files, t.modules, t.files_source = pick[0], pick[1], "llm"
            else:
                bad_picks += 1
    whole = out.whole.strip()
    bad_whole = not (whole and cited(out.whole_cites) and 2 <= len(_SENT.split(whole)) <= 4 and _styled(whole, "explanation"))
    if not bad_whole:
        reading.whole, reading.whole_source = whole, "llm"
    words = {frozenset((c.a, c.b)): c.text.strip() for c in out.connections}
    bad_conns = 0
    for k in reading.connections:
        new = words.get(frozenset((k.a, k.b)))
        if new is None:
            continue
        if new and _keeps(k.text, k.facts, new) and _styled(new, "explanation"):
            k.text = new
        else:
            bad_conns += 1
    if not (bad_threads or bad_picks or bad_whole or bad_conns):
        return said, tried.model
    parts = ([f"{bad_threads} thread(s)"] if bad_threads else []) + ([f"{bad_picks} file pick(s)"] if bad_picks else []) + \
            (["the whole"] if bad_whole else []) + ([f"{bad_conns} connection(s)"] if bad_conns else [])
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return said + [f"thread text: {joined} failed the checks; their fixed text stays"], tried.model
