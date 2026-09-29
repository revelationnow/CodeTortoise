"""Field mutations introduced/removed by changed functions, including writes through local aliases."""
from __future__ import annotations

from collections import defaultdict

from codetortoise.detectors.base import DetectorContext, Evidence, Finding, max_severity
from codetortoise.facts.model import FieldAccess


def _writes(facts_list, usr: str) -> dict[tuple[str, str], list[FieldAccess]]:
    out: dict[tuple[str, str], list[FieldAccess]] = defaultdict(list)
    for facts in facts_list:
        for a in facts.fields:
            if a.fn == usr and a.mode != "read" and a.root_kind != "local":
                out[(a.field, a.root_kind)].append(a)
    return out


def detect_field_mutation(ctx: DetectorContext) -> list[Finding]:
    im = ctx.impact
    changed_ids = set(im.changed)
    findings = []
    for nid in im.changed:
        node = im.nodes[nid]
        wb, wa = _writes(ctx.before, node.key), _writes(ctx.after, node.key)
        for key in sorted(set(wa) - set(wb)):
            accesses = wa[key]
            a0 = accesses[0]
            field_node = im.node_by_key(f"field:{a0.field}")
            others = []
            if field_node is not None:
                others = sorted({im.nodes[e.src].label for e in im.edges
                                 if e.dst == field_node.id and e.src not in changed_ids and e.status != "removed"})
            only_may = all(a.mode == "may_write" for a in accesses)
            sev = "low" if only_may else ("high" if others else "medium")
            ev = []
            for a in accesses:
                how = f" via {' -> '.join(a.via)}" if a.via else ""
                ev.append(Evidence(text=f"{a.mode} `{a.path}`{how} ({a.confidence})", file=a.file, line=a.line,
                                   severity=sev))
            if others:
                ev.append(Evidence(text=f"{len(others)} other function(s) access this field: {', '.join(others[:10])}",
                                   severity=sev))
            label = field_node.label if field_node else a0.field_name
            alias = any(a.via for a in accesses)
            findings.append(Finding(
                kind="field_mutation", severity=max_severity(ev),
                title=f"{node.label} now writes {label}" + (" through a local alias" if alias else ""),
                nodes=[nid] + ([field_node.id] if field_node else []), evidence=ev,
                summary=f"{node.label} newly modifies {label} ({a0.path})."))
        for key in sorted(set(wb) - set(wa)):
            a0 = wb[key][0]
            findings.append(Finding(
                kind="field_mutation", severity="low", title=f"{node.label} no longer writes {a0.record}::{a0.field_name}",
                nodes=[nid], evidence=[Evidence(text=f"previously wrote `{a0.path}`", file=a0.file, line=a0.line,
                                                severity="low")],
                summary=f"{node.label} stopped modifying {a0.record}::{a0.field_name}; readers may depend on it."))
    return findings
