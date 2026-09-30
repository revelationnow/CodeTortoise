"""Contract changes: signatures, parameter const-ness, new return values vs caller handling."""
from __future__ import annotations

from codetortoise.detectors.base import DetectorContext, Evidence, Finding, max_severity

_RANGE_OPS = ("!=", "<", ">", "<=", ">=")


def _val(v: str, names: dict[str, str]) -> str:
    return f"{names[v]} ({v})" if v in names else v


def _cmp(c) -> str:
    return ", ".join(f"{c.compared_names[x]} ({x})" if x in c.compared_names else x for x in c.compared)


def _covered(compared: list[str], new_values: list[str]) -> bool:
    for c in compared:
        if c.startswith(_RANGE_OPS):
            return True
    return all(any(c == f"=={v}" for c in compared) for v in new_values)


def detect_contract(ctx: DetectorContext) -> list[Finding]:
    fb = {f.usr: f for facts in ctx.before for f in facts.functions}
    fa = {f.usr: f for facts in ctx.after for f in facts.functions}
    after_calls = [c for facts in ctx.after for c in facts.calls]
    findings = []
    for nid in ctx.impact.changed:
        node = ctx.impact.nodes[nid]
        before, after = fb.get(node.key), fa.get(node.key)
        if before is None or after is None:
            continue
        ev: list[Evidence] = []
        titles = []
        if before.signature != after.signature:
            titles.append("signature changed")
            ev.append(Evidence(text=f"signature: `{before.signature}` -> `{after.signature}`",
                               file=after.file, line=after.start_line, severity="medium"))
            callers = ctx.impact.edges_into(nid, {"call", "virtual"})
            if callers:
                names = sorted({ctx.impact.nodes[e.src].label for e in callers})
                ev.append(Evidence(text=f"{len(names)} caller(s) must be re-checked: {', '.join(names[:10])}",
                                   severity="medium"))
        new_values = [r for r in after.returns if r not in before.returns]
        names = {**before.return_names, **after.return_names}
        new_text = ", ".join(_val(v, names) for v in new_values)
        if new_values:
            titles.append(f"new return value(s) {new_text}")
            ev.append(Evidence(text=f"returns before: {[_val(v, names) for v in before.returns] or ['(non-literal)']}; "
                                    f"after: {[_val(v, names) for v in after.returns]}",
                               file=after.file, line=after.start_line, severity="low"))
            for c in after_calls:
                if c.callee != node.key:
                    continue
                caller = fa.get(c.caller)
                cname = caller.qualname if caller else c.caller
                if not c.result_used:
                    ev.append(Evidence(text=f"{cname} ignores the result", file=c.file, line=c.line,
                                       severity="medium"))
                elif c.compared and not _covered(c.compared, new_values):
                    ev.append(Evidence(text=f"{cname} checks {_cmp(c)} which does not handle {new_text}",
                                       file=c.file, line=c.line, severity="high"))
                elif c.compared:
                    ev.append(Evidence(text=f"{cname} checks {_cmp(c)} (covers new values)",
                                       file=c.file, line=c.line, severity="info"))
                else:
                    ev.append(Evidence(text=f"{cname} uses the result without comparing it",
                                       file=c.file, line=c.line, severity="low"))
            if after.name in ctx.impact.capped:
                ev.append(Evidence(text=f"{ctx.impact.capped[after.name]} caller(s) outside the parsed TUs not examined "
                                        "(over heuristic_fanin_cap)", severity="low"))
            heur = [e for e in ctx.impact.edges_into(nid, {"call"}) if e.confidence == "heuristic"]
            if heur:
                ev.append(Evidence(text=f"{len(heur)} more caller(s) outside the parsed TUs (heuristic) not checked",
                                   severity="low"))
        if not ev:
            continue
        findings.append(Finding(
            kind="contract", severity=max_severity(ev), title=f"{after.qualname}: {'; '.join(titles)}",
            nodes=[nid], evidence=ev,
            summary=f"Contract of {after.qualname} changed ({'; '.join(titles)})."))
    return findings
