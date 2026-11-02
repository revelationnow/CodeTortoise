"""A review's design overview (spec 2026-11-02): where the change sits, its walk-throughs and its conditions.

The `design` stage builds it from the reading, by rules only in phase 1 (§16). It is stored as blob `reading_design` and
served inside GET /reading as `design`. The models are spec §9's with the fields §18.10 adds, each commented."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DesignNode(BaseModel):
    """A node the design cites. /names only names the nodes on boards and stories, so the design names its own (§18.8)."""
    label: str
    kind: Literal["function", "field"] = "function"
    component: str | None = None
    path: str = ""                    # workspace-relative: a function's file, a field's record header
    line: int | None = None           # a function's first line (after side), a field's declaration


class WalkStep(BaseModel):
    kind: Literal["call", "return", "self", "write", "read", "fold"]
    src: str                          # node id
    dst: str                          # node id; == src for "self"
    label: str                        # from the code: the call, the returned value, the assignment
    status: Literal["new", "changed", "same"]
    ref: Literal["path", "change", "flow", "code"] = "code"    # what it comes from (§18.10): a story's call path, its
                                      # changed lines, a flow's landing, or unchanged code
    story: str | None = None          # S1
    flow: str | None = None           # a flow id of that story
    flow_n: int | None = None         # that flow's 1-based place in the story's Flows tab (its `?flow=N`)
    cause: str | None = None          # the cause of its first key
    keys: list[str] = Field(default_factory=list)   # a flow step's check keys: what "Looks fine" on it marks
    edge: str | None = None           # impact edge id, for a call between two functions
    loop: str | None = None           # the loop this step sits in, as written: "for (i = 0; i < len; i++)"
    path: str = ""                    # where its code is, workspace-relative
    line: int | None = None
    cl: int | None = None             # the CL that wrote that line, for a new or changed one
    folded: int = 0                   # a "fold" step: how many steps it stands for


class Walk(BaseModel):
    id: str                           # W1; cited, never shown
    title: str
    title_source: Literal["template", "llm"] = "template"
    lead: str = ""
    thread: str | None = None         # anchored on a thread …
    connection: tuple[str, str] | None = None   # … or on the connection between two
    condition: str | None = None      # the gate id, when this is one side of it
    case: bool | None = None          # which side of it: true, false; None without a condition (§18.10)
    parts: list[str]                  # function node ids, left to right
    stories: list[str] = Field(default_factory=list)   # the stories its steps come from, in order (§18.10)
    steps: list[WalkStep]


class Component(BaseModel):
    name: str
    level: int | None                 # layers.py level: the highest of its changed files'
    band: str = ""                    # the band it sits in: its layer's name, "other" without one
    globs: list[str] = Field(default_factory=list)
    threads: list[str] = Field(default_factory=list)   # the threads whose stories change it
    stories: list[str] = Field(default_factory=list)   # those stories, in reading order
    files: list[str] = Field(default_factory=list)     # its changed files, workspace-relative
    crossing: list[str] = Field(default_factory=list)  # sentences from the impact edges that cross into or out of it
    quiet: bool = False               # shares no edge with the rest


class Concern(BaseModel):            # phase 2 (§6.1)
    text: str
    how: str
    stories: list[str]
    assessment: Literal["right", "note", "confirm", "ask"]
    note: str = ""
    causes: list[str] = Field(default_factory=list)


class Ownership(BaseModel):          # phase 2 (§6.2)
    tag: Literal["right", "questionable", "shortfall", "note"]
    text: str
    cites: list[str]                  # node ids, paths or story ids


class GatedLine(BaseModel):
    story: str | None = None          # none for a line no story holds, such as a header's (§18.10)
    cl: int | None = None
    text: str
    runs: bool                        # when the condition is false
    where: Literal["under", "outside", "elsewhere"] = "elsewhere"
    path: str = ""                    # workspace-relative
    line: int | None = None
    function: str | None = None       # the function holding it, by label


class Gate(BaseModel):
    id: str
    node: str                         # the function holding it
    test: str                         # "len > 64"
    false_case: str = ""              # the model names it in phase 2; until then the fold says "When `test` is false"
    lines: list[GatedLine] = Field(default_factory=list)   # the strongest condition's only (§7)
    source: Literal["code", "context"] = "code"
    story: str | None = None
    path: str = ""
    line: int | None = None           # the test's line
    guarded: list[int] = Field(default_factory=list)       # [first, last] line of the block it guards
    runs: int = 0                     # changed lines that still run when it is false
    stops: int = 0                    # changed lines that don't


class ReadingDesign(BaseModel):
    verdict: str = ""
    verdict_causes: list[str] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    concerns: list[Concern] = Field(default_factory=list)
    ownership: list[Ownership] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)
    walks: list[Walk] = Field(default_factory=list)
    nodes: dict[str, DesignNode] = Field(default_factory=dict)
    sources: dict[str, Literal["template", "llm", "pinned"]] = Field(default_factory=dict)   # per part
    context_hash: str | None = None


def build_design(x, ss, details, r, per, *, lines=None, read_text=None) -> ReadingDesign:
    """The design overview by rules (phase 1): the components, the conditions and the walk-throughs, and every node
    they cite. `x` is the analysis's `_Ctx`; `details` the story details; `r`, `per` the reading and its stories'."""
    from codetortoise.components import build_components
    from codetortoise.gates import Sources, build_gates
    from codetortoise.walks import build_walks
    src = Sources(x, read_text)
    components, node_comp = build_components(x, ss, r, per)
    gates, branches = build_gates(x, ss, r, per, src, lines)
    walks = build_walks(x, ss, details, r, per, src, branches, lines)
    return ReadingDesign(components=components, gates=gates, walks=walks,
                         nodes=design_nodes(x, walks, gates, node_comp))


def design_nodes(x, walks: list[Walk], gates: list[Gate], node_comp: dict[str, str]) -> dict[str, DesignNode]:
    """Label, kind, component, file and line of each node the walk-throughs and conditions cite (R4)."""
    from codetortoise.reading import rel_path
    ids = {g.node for g in gates} | {n for w in walks for n in w.parts}
    ids |= {n for w in walks for s in w.steps for n in (s.src, s.dst)}
    out: dict[str, DesignNode] = {}
    for nid in sorted(ids, key=lambda n: (len(n), n)):
        n = x.im.nodes.get(nid)
        if n is None:
            continue
        fn = x.fa.get(n.key) or x.fb.get(n.key)
        loc = x.local(nid)
        out[nid] = DesignNode(label=n.label, kind=n.kind, component=node_comp.get(nid),
                              path=rel_path(x, loc) if loc else "",
                              line=fn.start_line if fn is not None else x.decl_line.get(n.key))
    return out
