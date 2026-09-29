"""Header changes (types, macros, prototypes) weighted by how many TUs and layers include them."""
from __future__ import annotations

from codetortoise.cparse import is_header
from codetortoise.detectors.base import DetectorContext, Evidence, Finding


def detect_header_fanout(ctx: DetectorContext) -> list[Finding]:
    fan = {f.header: f for f in ctx.impact.fanout}
    by_header: dict[str, list[str]] = {}
    for t in ctx.dm.types:
        if is_header(t.file):
            by_header.setdefault(t.file, []).append(f"{t.kind.replace('_', ' ')}: {t.name}")
    findings = []
    for header, changes in sorted(by_header.items()):
        fo = fan.get(header)
        total = fo.total_tus if fo else 0
        layers = len(fo.by_layer) if fo else 0
        if total >= 100 or layers >= 3:
            sev = "high"
        elif total >= 10 or layers >= 2:
            sev = "medium"
        else:
            sev = "low"
        ev = [Evidence(text=c, file=header, severity=sev) for c in changes]
        if fo:
            ev.append(Evidence(text=f"included (transitively) by {total} TU(s); by layer: {fo.by_layer}",
                               severity=sev))
        findings.append(Finding(
            kind="header_fanout", severity=sev, title=f"{header.split('/')[-1]}: {len(changes)} change(s) reach {total} TU(s)",
            evidence=ev, summary=f"Changes in {header} affect {total} translation unit(s) across {layers} layer(s)."))
    return findings
