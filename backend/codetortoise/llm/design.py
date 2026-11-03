"""The strong model's parts of the design overview (spec 2026-11-02 §10): the verdict and the checks it names, what the
design must get right (§6.1), whether it is right (§6.2), each walk-through's title and lead (§4.2) and each condition's
false case (§7).

One tier-1 call per review, in the design stage once the rules have built the rest. Each part is checked on its own: it
cites only listed ids, keeps its sentence counts and the house style, and names no id in its words; a concern cites a
story, and one that says to confirm or ask cites a cause the review has. A part that fails keeps its fixed text, or is
left out when it has none.
"""
from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from codetortoise.design import Concern, Ownership, ReadingDesign, Rewrite, WalkStep
from codetortoise.llm.client import LlmClient
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.storyboard import _styled
from codetortoise.llm.style import STYLE
from codetortoise.llm.threads import _SENT
from codetortoise.llm.tiers import TiersFailed, done_text, tried_note, try_tiers
from codetortoise.reading import Cause, Reading
from codetortoise.stories import StorySet

DESIGN_VERSION = 4                    # bump with every change to the prompt or its checks (keys its cache)
CAUSES_SHOWN = 30                     # §14: about 6k tokens in; only what is listed may be cited
NODES_SHOWN = 60
STEPS_SHOWN = 12                      # a walk-through's steps, half from each end; the rest are counted
MAX_CONCERNS = 6
MAX_OWNERSHIP = 8
ASSESSMENTS = ("right", "note", "confirm", "ask")
TAGS = ("right", "questionable", "shortfall", "note")
MAX_INSTRUCTION = 300                 # a reader's instruction to a rewrite, in characters (§10's AI menu)
_WHAT = {"verdict": "the verdict", "concerns": "the concerns", "ownership": "the ownership lines"}
_KEYS = {"verdict": '"verdict" and "verdict_causes"', "concerns": '"concerns"', "ownership": '"ownership"',
         "walk": '"walks", with that walk-through alone', "gate": '"conditions", with that condition alone'}
# a node, finding, thread, walk-through, condition or cause id: names belong in the words; a reader sees none of these
_NO_IDS = re.compile(r"\b(?:[NFTWG]\d+|c[0-9a-f]{10})\b")

SYSTEM = ("You are a senior C/C++ reviewer writing the opening of a review for reviewers who have not seen the change. "
          'Use only what you are given. Reply with one JSON object: {"verdict", "verdict_causes", "concerns": [{"text", '
          '"how", "stories", "assessment", "note", "causes"}], "ownership": [{"tag", "text", "cites"}], "walks": [{"id", '
          '"title", "lead"}], "conditions": [{"id", "false_case"}]}. ' + STYLE)

ASK = """The opening says what the change is for, where it sits and whether its design holds; the checks listed below \
stay the only things a reviewer marks. Write "verdict": 2 or 3 sentences on whether the change holds together, the \
last saying what a reviewer must settle; list in "verdict_causes" the ids of the checks it names. Write "concerns": at \
most 6 rows, each one thing the design must get right: "text" (at most 8 words), "how" (one sentence: how the change \
does it), "stories" (the ids of the stories that do it), "assessment" ("right": it does; "note": worth knowing; \
"confirm": a reviewer must confirm it; "ask": ask the author) and an optional one-sentence "note"; a "confirm" or "ask" \
row lists the checks it rests on in "causes". Write "ownership": short lines on which part owns each decision the \
change makes, or what it leaves undone, each with a "tag" ("right", "questionable", "shortfall" or "note"), one or two \
sentences of "text" and "cites": the ids of the functions or fields, the changed files or the stories it rests on. For \
each walk-through write a "title" (at most 8 words, naming the case it follows, no final period) and a "lead" (1 or 2 \
sentences: what it follows and where it lands). For the condition to name, write "false_case": the case when its \
test is false, in at most 8 words, no final period; the other conditions are context only. Cite only the ids listed. \
In the words, write names, never ids. A DESIGN CONTEXT, when given, is the review owner's word on what the change is \
for and what the code can't say: draw the concerns from it as well as the stories, and say in the verdict where the \
change falls short of it; cite nothing from it."""


def _shown(d: ReadingDesign, r: Reading) -> tuple[list[Cause], list[str]]:
    """The causes and the node ids the prompt lists, the only ones an answer may cite: hazards first, then the reading's
    order, at most CAUSES_SHOWN; the design's nodes, at most NODES_SHOWN."""
    causes = sorted(r.causes or [], key=lambda c: c.kind != "hazard")[:CAUSES_SHOWN]
    return causes, list(d.nodes)[:NODES_SHOWN]


def _name(d: ReadingDesign, nid: str) -> str:
    n = d.nodes.get(nid)
    return n.label if n is not None else nid


def shown_gate(d: ReadingDesign):
    """The condition the overview shows (frontend foldGate): the first, when it lists lines; the only one named."""
    return d.gates[0] if d.gates and d.gates[0].lines else None


def step_line(d: ReadingDesign, s: WalkStep) -> str:
    """A walk-through step as the prompt reads it: what happens, in names and code, then whether it is new and where it
    comes from. A fold reads as the page words it: its own label, and whether a step in it changed."""
    if s.kind == "fold":
        return f"{s.label or f'… {s.folded} steps'} ({'unchanged' if s.status == 'same' else 'some changed'})"
    a, b = f"`{_name(d, s.src)}`", f"`{_name(d, s.dst)}`"
    code = f"`{s.label.replace('`', chr(39))}`" if s.label else ""
    said = {"call": f"{a} calls {code or b}",
            "return": f"{a} returns {code} to {b}" if code else f"{a} returns to {b}",
            "self": f"{a}: {code}" if code else a,
            "write": f"{a} writes {b}" + (f": {code}" if code else ""),
            "read": f"{b} reads {a}" + (f": {code}" if code else "")}[s.kind]
    story = s.story or "a story"
    ref = {"path": f"{story}'s call path", "change": f"{story}'s change",
           "flow": f"{story} flow {s.flow_n}" + (f", check {s.cause}" if s.cause else ""), "code": "unchanged code"}[s.ref]
    return f"{said} ({'; '.join(x for x in ('' if s.status == 'same' else s.status, ref) if x)})"


def prompt(d: ReadingDesign, r: Reading, ss: StorySet, context: str = "") -> str:
    by = {s.id: s for s in ss.stories}
    causes, nodes = _shown(d, r)
    lines = ([f"DESIGN CONTEXT (from the review's owner):\n{context}\nEND OF DESIGN CONTEXT"] if context else []) + [
        f"THE CHANGE: {r.whole or '(no summary)'}", "THREAD LIST (id | name | purpose):"]
    for t in r.threads:
        lines.append(f"{t.id} | {t.name} | {t.purpose}")
        lines.append("  stories: " + "; ".join(f"{s} {by[s].title}" + (f": {by[s].purpose}" if by[s].purpose else "")
                                               + f" ({by[s].kind})" for s in t.stories if s in by))
    lines.append("CHECKS BY CAUSE (id | kind | thread | story | what):")
    lines += [f"{c.id} | {c.kind} | {c.thread or '-'} | {c.story or '-'} | {c.text}" for c in causes] or ["(none)"]
    if len(r.causes or []) > len(causes):
        lines.append(f"… +{len(r.causes or []) - len(causes)} more checks")
    lines.append("COMPONENTS (name | layer | threads | changed files):")
    for c in d.components:
        lines.append(f"{c.name} | {c.band} | {', '.join(c.threads) or '-'} | {', '.join(c.files) or '-'}")
        if c.crossing:
            lines.append("  crossing: " + "; ".join(c.crossing))
        elif c.quiet:
            lines.append("  shares no calls or fields with the rest")
    lines.append("FUNCTIONS AND FIELDS (id | name | component | where):")
    for nid in nodes:
        n = d.nodes[nid]
        lines.append(f"{nid} | {n.label} | {n.component or '-'} | {n.path}" + (f":{n.line}" if n.line else ""))
    if len(d.nodes) > len(nodes):
        lines.append(f"… +{len(d.nodes) - len(nodes)} more")
    shown = shown_gate(d)

    def where(g) -> str:
        return f"{g.id} | {g.test} | {_name(d, g.node)} | {g.path}" + (f":{g.line}" if g.line else "")
    lines.append("CONDITION TO NAME (id | test | function | where | changed lines that still run when it is false | "
                 "that stop):")
    lines.append(f"{where(shown)} | {shown.runs} | {shown.stops}" if shown is not None else "(none)")
    if any(g is not shown for g in d.gates):
        lines.append("OTHER CONDITIONS, context only (id | test | function | where):")
        lines += [where(g) for g in d.gates if g is not shown]
    lines.append("WALK-THROUGHS (id | case | anchored on | stories):")
    for w in d.walks:
        case = f"{w.condition} {'true' if w.case else 'false'}" if w.condition else "-"
        anchor = f"{w.connection[0]} with {w.connection[1]}" if w.connection else (w.thread or "-")
        lines.append(f"{w.id} | {case} | {anchor} | {', '.join(w.stories) or '-'}")
        steps = list(enumerate(w.steps, 1))
        if len(steps) > STEPS_SHOWN:                 # its first steps and its last: where it lands stays in
            half = STEPS_SHOWN // 2
            lines += [f"  {i}. {step_line(d, s)}" for i, s in steps[:half]]
            lines.append(f"  … +{len(steps) - STEPS_SHOWN} steps")
            steps = steps[-half:]
        lines += [f"  {i}. {step_line(d, s)}" for i, s in steps]
    if not d.walks:
        lines.append("(none)")
    return ASK + "\n\n" + "\n".join(lines)


class _Concern(BaseModel):
    text: str = ""
    how: str = ""
    stories: list[str] = Field(default_factory=list)
    assessment: str = ""
    note: str = ""
    causes: list[str] = Field(default_factory=list)


class _Owner(BaseModel):
    tag: str = ""
    text: str = ""
    cites: list[str] = Field(default_factory=list)


class _WalkText(BaseModel):
    id: str = ""
    title: str = ""
    lead: str = ""


class _Case(BaseModel):
    id: str = ""
    false_case: str = ""


class _Out(BaseModel):
    verdict: str = ""
    verdict_causes: list[str] = Field(default_factory=list)
    concerns: list[_Concern] = Field(default_factory=list)
    ownership: list[_Owner] = Field(default_factory=list)
    walks: list[_WalkText] = Field(default_factory=list)
    conditions: list[_Case] = Field(default_factory=list)


def _prose(text: str, lo: int, hi: int) -> bool:
    """`lo` to `hi` sentences in the house style, naming no id."""
    return bool(text) and lo <= len(_SENT.split(text)) <= hi and _styled(text, "explanation") and not _NO_IDS.search(text)


def _headline(text: str) -> bool:
    return bool(text) and _styled(text, "headline") and not _NO_IDS.search(text)


def _ids(xs: list[str]) -> list[str]:
    """Cited ids as given, each once, in order."""
    return list(dict.fromkeys(x.strip() for x in xs if x.strip()))


def apply_answer(d: ReadingDesign, r: Reading, out: _Out, only: str | None = None) -> list[str]:
    """Write each part of `out` that passes its checks into `d`, marking it the model's in `d.sources`; returns the
    parts that failed, worded for a note. `only`: the one part a rewrite asks for (`verdict`, `concerns`, `ownership`,
    `walk:W1`, `gate:G1`); the rest of `out` is not read, and a walk-through's title must differ from every other's."""
    causes_shown, nodes_shown = _shown(d, r)
    causes = {c.id for c in causes_shown}
    stories = {s for t in r.threads for s in t.stories}
    citable = stories | set(nodes_shown) | {f for c in d.components for f in c.files}

    def asks(part: str) -> bool:
        return only is None or only == part
    bad: list[str] = []
    if asks("verdict"):
        verdict, named = out.verdict.strip(), _ids(out.verdict_causes)
        if _prose(verdict, 2, 3) and all(c in causes for c in named) and (bool(named) or not causes):
            d.verdict, d.verdict_causes, d.sources["verdict"] = verdict, named, "llm"
        else:
            bad.append("the verdict")
    if asks("concerns"):
        rows: list[Concern] = []
        dropped = 0
        for c in out.concerns[:MAX_CONCERNS]:
            text, how, note, sids = c.text.strip(), c.how.strip(), c.note.strip(), _ids(c.stories)
            if not (_headline(text) and _prose(how, 1, 1) and (not note or _prose(note, 1, 1)) and sids
                    and all(s in stories for s in sids) and c.assessment in ASSESSMENTS):
                dropped += 1
                continue
            named, assessment = _ids(c.causes), c.assessment
            if any(x not in causes for x in named) or (assessment in ("confirm", "ask") and not named):
                assessment, named = "note", []       # a cause the review lacks: no chip, nothing to confirm (§6.1)
            rows.append(Concern(text=text, how=how, stories=sids, assessment=assessment, note=note, causes=named))
        if rows:
            d.concerns, d.sources["concerns"] = rows, "llm"
        if dropped or not rows:
            bad.append(f"{dropped} concern(s)" if rows else "the concerns")
    if asks("ownership"):
        lines: list[Ownership] = []
        dropped = 0
        for o in out.ownership[:MAX_OWNERSHIP]:
            text, cites = o.text.strip(), _ids(o.cites)
            if o.tag in TAGS and _prose(text, 1, 2) and cites and all(x in citable for x in cites):
                lines.append(Ownership(tag=o.tag, text=text, cites=cites))
            else:
                dropped += 1
        if lines:
            d.ownership, d.sources["ownership"] = lines, "llm"
        if dropped:
            bad.append(f"{dropped} ownership line(s)")
    got = {w.id: w for w in out.walks}
    asked = [w for w in d.walks if asks(f"walk:{w.id}")]
    passing: dict[str, tuple[str, str]] = {}
    for w in asked:
        a = got.get(w.id)
        title, lead = (a.title.strip(), a.lead.strip()) if a else ("", "")
        if _headline(title) and _prose(lead, 1, 2):
            passing[w.id] = (title, lead)
    while True:               # a title must differ from every title that stays and from each passing one before it
        stays = {w.title.lower() for w in d.walks if w.id not in passing}
        seen: set[str] = set()
        clash: list[str] = []
        for wid, (t, _) in passing.items():
            if t.lower() in stays or t.lower() in seen:
                clash.append(wid)
            seen.add(t.lower())
        if not clash:
            break
        for wid in clash:
            del passing[wid]
    for w in asked:
        if w.id in passing:
            (w.title, w.lead), w.title_source, d.sources[f"walk:{w.id}"] = passing[w.id], "llm", "llm"
    if len(asked) > len(passing):
        bad.append(f"{len(asked) - len(passing)} walk-through title(s)")
    cases, failed, shown = {g.id: g for g in out.conditions}, 0, shown_gate(d)
    for g in d.gates:
        if not asks(f"gate:{g.id}") or (only is None and g is not shown):     # the others are context, never named
            continue
        a = cases.get(g.id)
        case = a.false_case.strip() if a else ""
        if _headline(case):
            g.false_case, d.sources[f"gate:{g.id}"] = case, "llm"
        else:
            failed += 1
    if failed:
        bad.append(f"{failed} condition name(s)")
    return bad


def write_design(strong: LlmClient, ledger: Ledger | None, rid: int | None, d: ReadingDesign, r: Reading, ss: StorySet,
                 weak: LlmClient | None = None, context: str = "") -> tuple[list[str], str | None]:
    """Write the model's parts of `d` in place from one checked answer; returns notes on the parts that failed, and the
    model that answered (None: every part keeps its fixed text). The strong model failing is tried fresh, then on the
    weak model. `context` is the design context's text (§8)."""
    text = prompt(d, r, ss, context)

    def ask(llm: LlmClient) -> _Out:
        return llm.complete_json(SYSTEM, text, _Out)
    try:
        tried = try_tiers(ledger, rid, "design", "design", ask, strong, weak)
    except Refused as e:
        return [f"design: AI budget: {e.reason}; the fixed text stays"], None
    except TiersFailed as e:  # the fixed text stands
        return [tried_note("design", e.failures, "the fixed text stays")], None
    said = [] if tried.tier == "strong" else [tried_note("design", tried.failures, done_text(tried, "wrote it"))]
    bad = apply_answer(d, r, tried.value)
    if not bad:
        return said, tried.model
    joined = bad[0] if len(bad) == 1 else ", ".join(bad[:-1]) + " and " + bad[-1]
    return said + [f"design: {joined} failed the checks"], tried.model


def design_text(d: ReadingDesign) -> dict:
    """The model's parts of `d`, as blob `design_text` keeps them for a re-run of the same prompt: the model's own
    answer, which passed every check (what readers chose is kept apart, in blob `design_chosen`)."""
    return {"verdict": d.verdict, "verdict_causes": d.verdict_causes,
            "concerns": [c.model_dump() for c in d.concerns], "ownership": [o.model_dump() for o in d.ownership],
            "walks": {w.id: [w.title, w.lead] for w in d.walks if w.title_source == "llm"},
            "gates": {g.id: g.false_case for g in d.gates if d.sources.get(f"gate:{g.id}") == "llm"},
            "sources": dict(d.sources)}


def apply_design_text(d: ReadingDesign, kept: dict) -> None:
    """Put the model's parts kept in blob `design_text` back into `d`, the rules' design of the same prompt."""
    d.verdict, d.verdict_causes = kept["verdict"], list(kept["verdict_causes"])
    d.concerns = [Concern(**c) for c in kept["concerns"]]
    d.ownership = [Ownership(**o) for o in kept["ownership"]]
    for w in d.walks:
        if w.id in kept["walks"]:
            (w.title, w.lead), w.title_source = kept["walks"][w.id], "llm"
    for g in d.gates:
        if g.id in kept["gates"]:
            g.false_case = kept["gates"][g.id]
    d.sources.update(kept["sources"])


def chosen_part(d: ReadingDesign, part: str) -> dict:
    """Part `part` of `d` as blob `design_chosen` keeps what readers chose for a prompt (a rewrite, or the words left
    showing when a pin goes): its words and its rewrite's record."""
    kind, _, pid = part.partition(":")
    if kind == "verdict":
        words: object = [d.verdict, list(d.verdict_causes)]
    elif kind in ("concerns", "ownership"):
        words = [x.model_dump() for x in getattr(d, kind)]
    elif kind == "walk":
        w = next(w for w in d.walks if w.id == pid)
        words = [w.title, w.lead]
    else:
        words = next(g for g in d.gates if g.id == pid).false_case
    rec = d.rewrites.get(part)
    return {"words": words, "rewrite": rec.model_dump() if rec is not None else None}


def apply_chosen(d: ReadingDesign, chosen: dict) -> None:
    """Put the parts readers chose (blob `design_chosen`, of the same prompt) into `d` over the model's answer, each
    marked the model's with its rewrite's record, if any."""
    for part, c in chosen["parts"].items():
        if not has_part(d, part):
            continue
        kind, _, pid = part.partition(":")
        words = c["words"]
        if kind == "verdict":
            d.verdict, d.verdict_causes = words[0], list(words[1])
        elif kind == "concerns":
            d.concerns = [Concern(**x) for x in words]
        elif kind == "ownership":
            d.ownership = [Ownership(**x) for x in words]
        elif kind == "walk":
            w = next(w for w in d.walks if w.id == pid)
            (w.title, w.lead), w.title_source = words, "llm"
        else:
            next(g for g in d.gates if g.id == pid).false_case = words
        d.sources[part] = "llm"
        if c.get("rewrite"):
            d.rewrites[part] = Rewrite(**c["rewrite"])
        else:
            d.rewrites.pop(part, None)


def choose(chosen: dict | None, key: str, d: ReadingDesign, part: str) -> dict:
    """Blob `design_chosen` with part `part` as `d` now shows it, for the prompt `key` (a blob of another prompt
    goes)."""
    parts = dict(chosen["parts"]) if chosen and chosen.get("key") == key else {}
    return {"key": key, "parts": {**parts, part: chosen_part(d, part)}}


def design_key(model: str, text: str) -> str:
    """What blob `design_text` is kept under: the prompt, the model that answered it and DESIGN_VERSION."""
    return hashlib.sha256(f"{DESIGN_VERSION}|{model}|{text}".encode()).hexdigest()


def has_part(d: ReadingDesign, part: str) -> bool:
    """Whether `part` names a part of `d` the model writes: `verdict`, `concerns`, `ownership`, `walk:W1`, `gate:G1`."""
    kind, sep, pid = part.partition(":")
    if kind == "walk":
        return any(w.id == pid for w in d.walks)
    if kind == "gate":
        return any(g.id == pid for g in d.gates)
    return not sep and kind in _WHAT


def part_text(d: ReadingDesign, part: str) -> str:
    """Part `part` of `d` as it stands, as a rewrite's prompt quotes it; "(none)" when it has no words yet."""
    kind, _, pid = part.partition(":")
    if kind == "verdict":
        lines = [d.verdict] if d.verdict else []
    elif kind == "concerns":
        lines = [f"{i}. {c.text}: {c.how} ({c.assessment}{': ' + c.note if c.note else ''})"
                 for i, c in enumerate(d.concerns, 1)]
    elif kind == "ownership":
        lines = [f"{o.tag}: {o.text}" for o in d.ownership]
    elif kind == "walk":
        w = next(w for w in d.walks if w.id == pid)
        lines = [f"title: {w.title}"] + ([f"lead: {w.lead}"] if w.lead else [])
    else:
        g = next(g for g in d.gates if g.id == pid)
        lines = [f"false case: {g.false_case}"] if g.false_case else []
    return "\n".join(lines) or "(none)"


def rewrite_prompt(d: ReadingDesign, r: Reading, ss: StorySet, part: str, context: str = "",
                   instruction: str = "") -> str:
    """The prompt that asks for one part again (§10's AI menu): the design's whole prompt, so the same ids are listed
    and the same checks hold, then the part as it stands, then the reader's instruction when there is one."""
    kind, _, pid = part.partition(":")
    what = _WHAT.get(kind) or (f"walk-through {pid}'s title and lead" if kind == "walk" else f"condition {pid}'s false case")
    tail = [f"REWRITE: write {what} again, and nothing else. As it stands:", part_text(d, part),
            f"Reply with the same JSON object holding only {_KEYS[kind]}."]
    if instruction.strip():
        tail.append(f"THE REVIEWER'S INSTRUCTION (follow it within the rules above): {instruction.strip()}")
    return prompt(d, r, ss, context) + "\n\n" + "\n".join(tail)


def rewrite_part(strong: LlmClient, ledger: Ledger | None, rid: int | None, user: str | None, d: ReadingDesign,
                 r: Reading, ss: StorySet, part: str, instruction: str = "",
                 context: str = "") -> tuple[ReadingDesign | None, str]:
    """Ask for part `part` of `d` again (§10's AI menu), charged to `user` as a "rewrite", with their instruction when
    given: one call to the strong model, as the menu says (no fresh try, no weak model). Returns a copy of `d` with
    that part rewritten, marked the model's and recorded as `user`'s rewrite with their instruction (None: the answer,
    or any one row of it, failed the part's checks) and the model that answered; `d` is left as it was. Raises Refused
    over a limit and TiersFailed when the strong model did not answer."""
    text = rewrite_prompt(d, r, ss, part, context, instruction)

    def ask(llm: LlmClient) -> _Out:
        return llm.complete_json(SYSTEM, text, _Out)
    tried = try_tiers(ledger, rid, "rewrite", part, ask, strong, None, user=user, once=True)
    trial = d.model_copy(deep=True)
    trial.sources.pop(part, None)
    bad = apply_answer(trial, r, tried.value, only=part)      # one failing row fails the whole part (final review I1)
    if bad or trial.sources.get(part) != "llm":
        return None, tried.model
    trial.rewrites.pop(part, None)
    if user:                                                  # words a reader asked for say so (final review I2)
        trial.rewrites[part] = Rewrite(by=user, instruction=instruction.strip())
    return trial, tried.model


def put_part(dst: ReadingDesign, src: ReadingDesign, part: str) -> None:
    """Copy part `part` of `src` into `dst`, its source and its rewrite's record with it: a rewrite lands on the design
    as it is by then."""
    kind, _, pid = part.partition(":")
    if kind == "verdict":
        dst.verdict, dst.verdict_causes = src.verdict, list(src.verdict_causes)
    elif kind == "concerns":
        dst.concerns = [c.model_copy(deep=True) for c in src.concerns]
    elif kind == "ownership":
        dst.ownership = [o.model_copy(deep=True) for o in src.ownership]
    elif kind == "walk":
        a, b = (next(w for w in x.walks if w.id == pid) for x in (src, dst))
        b.title, b.lead, b.title_source = a.title, a.lead, a.title_source
    else:
        a, b = (next(g for g in x.gates if g.id == pid) for x in (src, dst))
        b.false_case = a.false_case
    dst.sources[part] = src.sources[part]
    if part in src.rewrites:
        dst.rewrites[part] = src.rewrites[part].model_copy()
    else:
        dst.rewrites.pop(part, None)
