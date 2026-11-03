"""Where the change sits (spec 2026-11-02 §5): the components the change touches, banded by layer, each with the
threads that change it and the impact edges that cross into or out of it. Rules only (R15, R26)."""
from __future__ import annotations

import posixpath
from fnmatch import fnmatch

from codetortoise.board import _layer_name
from codetortoise.design import Component
from codetortoise.reading import rel_path

MAX_CROSSING = 3          # sentences per block
NAMES = 3                 # names in a sentence before "and N more"
TOP = "top level"
_CROSSING_KINDS = ("call", "virtual", "reads", "writes")


def component_of(x, path: str | None, rules) -> str | None:
    """A file's component: the first rule with a glob matching its workspace-relative path, else its module
    (layers.py), else its folder; None for a file outside the workspace."""
    if not path:
        return None
    rel = rel_path(x, path)
    if rel.startswith("/"):
        return None
    for rule in rules:
        if any(fnmatch(rel, g) for g in rule.globs):
            return rule.name
    m = x.c.layers.module_of(path) if x.c.layers is not None else posixpath.dirname(rel)
    return TOP if m in ("", ".") else m


def _names(x, nids) -> str:
    names = sorted({x.label(n) for n in nids})
    head = ", ".join(f"`{n}`" for n in names[:NAMES])
    return head + (f" and {len(names) - NAMES} more" if len(names) > NAMES else "")


def build_components(x, ss, r, per, rules=None, details=None) -> tuple[list[Component], dict[str, str]]:
    """The components holding the change's files, highest layer first, and every node's component. An edge crosses
    when its ends sit in two components and one end is changed code; its sentence goes on its source's block when that
    holds changed files, else on its destination's. A component no crossing edge touches is quiet. A component's
    stories are those whose reading or pieces (`details`: a header's declarations) touch its files."""
    rules = x.c.cfg.components if rules is None else rules
    files: dict[str, list[str]] = {}
    levels: dict[str, list[int]] = {}
    for fc in x.c.cs.files:
        name = component_of(x, fc.local, rules)
        if name is None:
            continue
        files.setdefault(name, []).append(rel_path(x, fc.local))
        lv = x.c.layers.level_of(fc.local) if x.c.layers is not None else None
        if lv is not None:
            levels.setdefault(name, []).append(lv)
    node_comp: dict[str, str] = {}
    for nid in x.im.nodes:
        comp = component_of(x, x.local(nid), rules)
        if comp is not None:
            node_comp[nid] = comp
    groups: dict[tuple[str, str, str], set[str]] = {}       # (kind, block, the shared end) -> the other ends
    counted: set[str] = set()
    for e in x.im.edges:
        if e.status == "removed" or e.kind not in _CROSSING_KINDS or (e.src not in x.changed and e.dst not in x.changed):
            continue
        a, b = node_comp.get(e.src), node_comp.get(e.dst)
        if a is None or b is None or a == b:
            continue
        counted.update((a, b))
        home = a if a in files else b if b in files else None
        if home is None:
            continue
        if e.kind in ("call", "virtual"):
            groups.setdefault(("call", home, e.dst), set()).add(e.src)
        else:
            groups.setdefault((e.kind, home, e.src), set()).add(e.dst)
    said: dict[str, list[tuple[int, str]]] = {}
    for (kind, home, end), others in groups.items():
        if kind == "call":
            verb = "calls" if len({x.label(n) for n in others}) == 1 else "call"
            text = f"{_names(x, others)} {verb} `{x.label(end)}`"
        else:
            text = f"`{x.label(end)}` {kind} {_names(x, others)}"
        said.setdefault(home, []).append((len(others), text))
    thread_of = {sid: t.id for t in r.threads for sid in t.stories}
    comp_of_rel = {f: name for name, fs in files.items() for f in fs}
    rel_of = {fc.depot: rel_path(x, fc.local) for fc in x.c.cs.files}
    holders: dict[str, list[str]] = {}
    for sid in r.order:
        sr, d = per.get(sid), (details or {}).get(sid)
        paths = [w.path for w in (sr.where if sr is not None else [])]
        paths += [rel_of.get(f, f) for p in (d.pieces if d is not None else []) for f in p.files]
        for path in paths:
            name = comp_of_rel.get(path)
            if name is not None and sid not in holders.setdefault(name, []):
                holders[name].append(sid)
    out: list[Component] = []
    for name, fs in files.items():
        lv = max(levels[name]) if name in levels else None
        sids = holders.get(name, [])
        threads = [t.id for t in r.threads if any(thread_of.get(s) == t.id for s in sids)]
        rule = next((rr for rr in rules if rr.name == name), None)
        globs = list(rule.globs) if rule is not None else (["*"] if name == TOP else [f"{name}/*"])
        crossing = [t for _, t in sorted(said.get(name, []), key=lambda p: (-p[0], p[1]))[:MAX_CROSSING]]
        out.append(Component(name=name, level=lv, band=_layer_name(x, lv) if lv is not None else "other", globs=globs,
                             threads=threads, stories=sids, files=sorted(fs), crossing=crossing,
                             quiet=name not in counted))
    out.sort(key=lambda c: (c.level is None, -(c.level or 0), c.name))
    return out, node_comp
