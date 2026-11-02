"""The strong model's parts of the design overview (spec 2026-11-02 §10): the verdict and the checks it names, what the
design must get right (§6.1), whether it is right (§6.2), each walk-through's title and lead (§4.2) and each condition's
false case (§7).

One tier-1 call per review, in the design stage once the rules have built the rest. Each part is checked on its own: it
cites only listed ids, keeps its sentence counts and the house style, and names no id in its words; a concern cites a
story, and one that says to confirm or ask cites a cause the review has. A part that fails keeps its fixed text, or is
left out when it has none.
"""
from __future__ import annotations

from codetortoise.design import ReadingDesign, WalkStep
from codetortoise.llm.style import STYLE
from codetortoise.reading import Cause, Reading
from codetortoise.stories import StorySet

DESIGN_VERSION = 1                    # bump with every change to the prompt or its checks (keys its cache)
CAUSES_SHOWN = 30                     # §14: about 6k tokens in; only what is listed may be cited
NODES_SHOWN = 60
STEPS_SHOWN = 12                      # a walk-through's steps; the rest are counted

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
sentences: what it follows and where it lands). For each condition write "false_case": the case when its test is \
false, in at most 8 words, no final period. Cite only the ids listed. In the words, write names, never ids."""


def _shown(d: ReadingDesign, r: Reading) -> tuple[list[Cause], list[str]]:
    """The causes and the node ids the prompt lists, the only ones an answer may cite: hazards first, then the reading's
    order, at most CAUSES_SHOWN; the design's nodes, at most NODES_SHOWN."""
    causes = sorted(r.causes or [], key=lambda c: c.kind != "hazard")[:CAUSES_SHOWN]
    return causes, list(d.nodes)[:NODES_SHOWN]


def _name(d: ReadingDesign, nid: str) -> str:
    n = d.nodes.get(nid)
    return n.label if n is not None else nid


def step_line(d: ReadingDesign, s: WalkStep) -> str:
    """A walk-through step as the prompt reads it: what happens, in names and code, then whether it is new and where it
    comes from."""
    a, b = f"`{_name(d, s.src)}`", f"`{_name(d, s.dst)}`"
    code = f"`{s.label.replace('`', chr(39))}`" if s.label else ""
    said = {"call": f"{a} calls {code or b}",
            "return": f"{a} returns {code} to {b}" if code else f"{a} returns to {b}",
            "self": f"{a}: {code}" if code else a,
            "write": f"{a} writes {b}" + (f": {code}" if code else ""),
            "read": f"{b} reads {a}" + (f": {code}" if code else ""),
            "fold": f"… {s.folded} more call{'' if s.folded == 1 else 's'}"}[s.kind]
    story = s.story or "a story"
    ref = {"path": f"{story}'s call path", "change": f"{story}'s change",
           "flow": f"{story} flow {s.flow_n}" + (f", check {s.cause}" if s.cause else ""), "code": "unchanged code"}[s.ref]
    return f"{said} ({'; '.join(x for x in ('' if s.status == 'same' else s.status, ref) if x)})"


def prompt(d: ReadingDesign, r: Reading, ss: StorySet) -> str:
    by = {s.id: s for s in ss.stories}
    causes, nodes = _shown(d, r)
    lines = [f"THE CHANGE: {r.whole or '(no summary)'}", "THREAD LIST (id | name | purpose):"]
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
    lines.append("CONDITIONS (id | test | function | where | changed lines that still run when it is false | that stop):")
    lines += [f"{g.id} | {g.test} | {_name(d, g.node)} | {g.path}" + (f":{g.line}" if g.line else "")
              + f" | {g.runs} | {g.stops}" for g in d.gates] or ["(none)"]
    lines.append("WALK-THROUGHS (id | case | anchored on | stories):")
    for w in d.walks:
        case = f"{w.condition} {'true' if w.case else 'false'}" if w.condition else "-"
        anchor = f"{w.connection[0]} with {w.connection[1]}" if w.connection else (w.thread or "-")
        lines.append(f"{w.id} | {case} | {anchor} | {', '.join(w.stories) or '-'}")
        lines += [f"  {i}. {step_line(d, s)}" for i, s in enumerate(w.steps[:STEPS_SHOWN], 1)]
        if len(w.steps) > STEPS_SHOWN:
            lines.append(f"  … +{len(w.steps) - STEPS_SHOWN} more steps")
    if not d.walks:
        lines.append("(none)")
    return ASK + "\n\n" + "\n".join(lines)
