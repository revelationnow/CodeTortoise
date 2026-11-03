"""Pinned design text (spec 2026-11-02 §10, the AI menu's "Pin this text"): the review's owner keeps the model's words
for one part of the design overview, and each later run of the design stage puts them back while they still fit.

Pins are kept in blob `design_pins`. A walk-through's or a condition's pin finds its part by what it is rather than by
its id, since ids follow the order the rules list them in; a function or field it cites is found again by its name, and
a story by what the rules made it of (its pieces), or by its title for a pin recorded before pins kept pieces. A pin
that no longer fits is dropped, and the design stage says so."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from codetortoise.design import Concern, Gate, Ownership, ReadingDesign, Rewrite, Walk
from codetortoise.reading import Reading

BLOB = "design_pins"
_DROPPED = {"verdict": "the pinned verdict no longer fits the change and was unpinned",
            "concerns": "the pinned concerns no longer fit the change and were unpinned",
            "ownership": "the pinned ownership lines no longer fit the change and were unpinned",
            "walk": "a pinned walk-through title no longer fits the change and was unpinned",
            "gate": "a pinned condition name no longer fits the change and was unpinned"}


class Pin(BaseModel):
    part: str                          # verdict, concerns, ownership, walk or gate
    key: str = ""                      # a walk-through's or a condition's: what it is (walk_key, gate_key)
    verdict: str = ""
    verdict_causes: list[str] = Field(default_factory=list)
    concerns: list[Concern] = Field(default_factory=list)
    ownership: list[Ownership] = Field(default_factory=list)
    title: str = ""
    lead: str = ""
    false_case: str = ""
    nodes: dict[str, str] = Field(default_factory=dict)     # each function or field it cites: its name, by id
    stories: dict[str, str] = Field(default_factory=dict)   # each story it cites: its title, by id
    pieces: dict[str, list[str]] = Field(default_factory=dict)   # and its pieces (none: a pin from before, by title)
    rewrite: Rewrite | None = None     # the reader who had these words written, and their instruction (final review I2)


def _label(d: ReadingDesign, nid: str) -> str:
    n = d.nodes.get(nid)
    return n.label if n is not None else nid


def _old_gate_key(d: ReadingDesign, g: Gate) -> str:
    """A condition's key before phase 4 M5b: its function's name and its test."""
    return f"{_label(d, g.node)}|{g.test}"


def gate_key(d: ReadingDesign, g: Gate) -> str:
    """What a condition is, whatever its id: its function's name, its test, its file, and its place (from 1) among the
    conditions of that function, test and file."""
    head = _old_gate_key(d, g)
    alike = [o.id for o in d.gates if o.path == g.path and _old_gate_key(d, o) == head]
    return f"{head}|{g.path}|{alike.index(g.id) + 1}"


def walk_key(d: ReadingDesign, w: Walk, old: bool = False) -> str:
    """What a walk-through is, whatever its id: its condition and side, and its steps by name. `old`: with its
    condition's key from before phase 4 M5b."""
    g = next((g for g in d.gates if g.id == w.condition), None)
    head = f"{_old_gate_key(d, g) if old else gate_key(d, g)}|{w.case}" if g is not None else "-"
    return head + "||" + "|".join(f"{s.kind}:{_label(d, s.src)}>{_label(d, s.dst)}:{s.label}" for s in w.steps)


def story_titles(ss) -> dict[str, str]:
    """The stories' titles by id, as a pin records and later checks them."""
    return {s.id: s.title for s in ss.stories} if ss is not None else {}


def story_pieces(ss) -> dict[str, list[str]]:
    """The stories' pieces by id: what the rules made each of, by which a pin finds a story whatever its title."""
    return {s.id: sorted(s.pieces) for s in ss.stories} if ss is not None else {}


def pin_of(d: ReadingDesign, part: str, titles: dict[str, str], pieces: dict[str, list[str]] | None = None) -> Pin:
    """Part `part` of `d` as a pin: its words, the names of what it cites, and who had them rewritten. `titles` and
    `pieces`: the stories' titles and pieces by id."""
    p = _words(d, part, titles)
    p.pieces = {s: list(pieces[s]) for s in p.stories if pieces and pieces.get(s)}
    w = d.rewrites.get(part)
    p.rewrite = w.model_copy() if w is not None else None
    return p


def _words(d: ReadingDesign, part: str, titles: dict[str, str]) -> Pin:
    kind, _, pid = part.partition(":")
    if kind == "verdict":
        return Pin(part=kind, verdict=d.verdict, verdict_causes=list(d.verdict_causes))
    if kind == "concerns":
        sids = {s for c in d.concerns for s in c.stories}
        return Pin(part=kind, concerns=[c.model_copy(deep=True) for c in d.concerns],
                   stories={s: titles.get(s, "") for s in sids})
    if kind == "ownership":
        cites = {c for o in d.ownership for c in o.cites}
        return Pin(part=kind, ownership=[o.model_copy(deep=True) for o in d.ownership],
                   nodes={c: d.nodes[c].label for c in cites if c in d.nodes},
                   stories={c: titles[c] for c in cites if c in titles})
    if kind == "walk":
        w = next(w for w in d.walks if w.id == pid)
        return Pin(part=kind, key=walk_key(d, w), title=w.title, lead=w.lead)
    g = next(g for g in d.gates if g.id == pid)
    return Pin(part=kind, key=gate_key(d, g), false_case=g.false_case)


@dataclass
class _Now:
    """What the review has now, as a pin's fit is judged."""
    causes: set[str]
    stories: set[str]
    titles: dict[str, str]
    pieces: dict[str, list[str]]
    files: set[str]
    named: dict[str, list[str]]       # node ids by name

    def cite(self, p: Pin, c: str) -> str | None:
        """Cite `c` of pin `p` as the design names it now; None when the review no longer has it."""
        if c in p.stories:
            made = [s for s in self.stories if p.pieces.get(c) and self.pieces.get(s) == p.pieces[c]]
            if len(made) == 1:                             # what the rules made it of: whatever its title or id now
                return made[0]
            return c if c in self.stories and self.titles.get(c) == p.stories[c] else None
        if c in p.nodes:
            ids = self.named.get(p.nodes[c], [])
            return ids[0] if len(ids) == 1 else None
        return c if c in self.files else None


def _find(items: list, key: str, now, before):
    """The walk-through or condition `key` names: the one whose key is `key` now, else (a pin from before phase 4 M5b)
    the first whose old key is."""
    found = next((i for i in items if now(i) == key), None)
    return found if found is not None else next((i for i in items if before(i) == key), None)


def _walk(d: ReadingDesign, p: Pin) -> Walk | None:
    return _find(d.walks, p.key, lambda w: walk_key(d, w), lambda w: walk_key(d, w, old=True))


def _gate(d: ReadingDesign, p: Pin) -> Gate | None:
    return _find(d.gates, p.key, lambda g: gate_key(d, g), lambda g: _old_gate_key(d, g))


def part_of(d: ReadingDesign, p: Pin) -> str | None:
    """The part of `d` pin `p` is for (None: a walk-through or condition `d` no longer has)."""
    if p.part == "walk":
        return f"walk:{w.id}" if (w := _walk(d, p)) is not None else None
    if p.part == "gate":
        return f"gate:{g.id}" if (g := _gate(d, p)) is not None else None
    return p.part


def unpin(d: ReadingDesign, pins: list[Pin], part: str) -> list[Pin]:
    """`pins` without those for part `part` of `d`, however they were keyed."""
    return [p for p in pins if part_of(d, p) != part]


def _put(d: ReadingDesign, p: Pin, now: _Now) -> str | None:
    """Put pin `p` into `d` when it fits; the part it filled (None: it doesn't fit)."""
    if p.part == "verdict":
        if not set(p.verdict_causes) <= now.causes:
            return None
        d.verdict, d.verdict_causes, d.sources["verdict"] = p.verdict, list(p.verdict_causes), "pinned"
        return "verdict"
    if p.part == "concerns":
        concerns = [c.model_copy(deep=True, update={"stories": [now.cite(p, s) for s in c.stories]}) for c in p.concerns]
        if any(s is None for c in concerns for s in c.stories) or \
                any(x not in now.causes for c in p.concerns for x in c.causes):
            return None
        d.concerns, d.sources["concerns"] = concerns, "pinned"
        return "concerns"
    if p.part == "ownership":
        lines = [o.model_copy(update={"cites": [now.cite(p, c) for c in o.cites]}) for o in p.ownership]
        if any(c is None for o in lines for c in o.cites):
            return None
        d.ownership, d.sources["ownership"] = lines, "pinned"
        return "ownership"
    if p.part == "walk":
        w = _walk(d, p)
        if w is None or any(o is not w and o.title.lower() == p.title.lower() for o in d.walks):
            return None                                    # gone, or its title is another walk-through's now
        w.title, w.lead, w.title_source, d.sources[f"walk:{w.id}"] = p.title, p.lead, "llm", "pinned"
        return f"walk:{w.id}"
    g = _gate(d, p)
    if g is None:
        return None
    g.false_case, d.sources[f"gate:{g.id}"] = p.false_case, "pinned"
    return f"gate:{g.id}"


def apply_pins(d: ReadingDesign, r: Reading, titles: dict[str, str], pins: list[Pin],
               pieces: dict[str, list[str]] | None = None) -> tuple[list[Pin], list[str]]:
    """Put each pin that still fits into `d`, its part marked pinned in `d.sources` and its rewrite's record, if any, in
    `d.rewrites`; returns the pins that fit and a note for each that no longer does. A pin fits while the review has
    every check it names, every story it cites (made of the same pieces, or under the title it had), every function or
    field it cites under its name (by whatever id each has now) and every file it cites, and, for a walk-through or a
    condition, one that is the same. `titles` and `pieces`: the stories' now, by id."""
    named: dict[str, list[str]] = {}
    for nid, n in d.nodes.items():
        named.setdefault(n.label, []).append(nid)
    now = _Now(causes={c.id for c in r.causes or []}, stories={s for t in r.threads for s in t.stories},
               titles=titles, pieces=pieces or {}, files={f for c in d.components for f in c.files}, named=named)
    kept: list[Pin] = []
    notes: list[str] = []
    for p in pins:
        part = _put(d, p, now)
        if part is None:
            notes.append(_DROPPED[p.part])
            continue
        kept.append(p)
        if p.rewrite is not None:                             # the pinned words' own record, or none
            d.rewrites[part] = p.rewrite.model_copy()
        else:
            d.rewrites.pop(part, None)
    return kept, notes


def load_pins(store, rid: int) -> list[Pin]:
    """Review `rid`'s pins; none when it has none."""
    return [Pin.model_validate(p) for p in store.get_blob(rid, BLOB) or []]

