"""Startup validation. Hard checks gate review creation."""
from __future__ import annotations

from pydantic import BaseModel

from codetortoise.paths import canon
from codetortoise.services import Services
from codetortoise.vcs.p4runner import P4Error


class Check(BaseModel):
    name: str
    ok: bool
    hard: bool
    detail: str = ""


class HealthReport(BaseModel):
    checks: list[Check]
    ready: bool
    index_generation: int = 0
    libclang: str | None = None
    strip_flags: list[str] = []
    p4_sources: dict[str, str] = {}    # where the owner, port and client came from (tortoise.yaml, P4CONFIG, environment)


def run_health(svc: Services) -> HealthReport:
    cfg = svc.cfg
    ws = cfg.workspace
    checks: list[Check] = []
    checks.append(Check(name="workspace root", ok=ws.root.is_dir(), hard=True, detail=str(ws.root)))
    if ws.vcs == "p4" and svc.p4 is not None:
        try:
            recs = svc.p4.run("client", "-o", ws.client or "")
            rec = recs[0] if recs else {}
            root = rec.get("Root", "")
            roots = [root] + [v for k, v in sorted(rec.items()) if k.startswith("AltRoots")]
            ok = any(r and canon(r) == canon(str(ws.root)) for r in roots)
            checks.append(Check(name="p4 client", ok=ok, hard=True,
                                detail=f"client {ws.client} Root={root}" + ("" if ok else f" (config root {ws.root})")))
        except P4Error as e:
            checks.append(Check(name="p4 client", ok=False, hard=True, detail=str(e)))
    dbs = svc.cdb.databases
    detail = (f"{len(svc.cdb.entries)} files from {len(dbs)} database(s): "
              + "; ".join(f"{p} ({n})" for p, n in dbs) if dbs else f"no compile database found ({ws.compile_commands})")
    if svc.cdb.duplicates:
        detail += f"; {svc.cdb.duplicates} file(s) listed again with different flags (the first entry is used)"
    if svc.cdb.problems:
        detail += f"; {len(svc.cdb.problems)} problem(s), e.g. {svc.cdb.problems[0]}"
    checks.append(Check(name="compile_commands", ok=bool(svc.cdb.entries), hard=True, detail=detail))
    try:
        svc.toolchain.prepare()
        lc = svc.toolchain.libclang
        checks.append(Check(name="libclang", ok=True, hard=True,
                            detail=f"{lc.version} ({'vendor' if lc.vendor else 'bundled'}) {lc.path}"))
    except (OSError, RuntimeError) as e:
        checks.append(Check(name="libclang", ok=False, hard=True, detail=str(e)))
    if cfg.toolchain.clang:
        err = svc.toolchain.driver_error
        checks.append(Check(name="driver query", ok=err is None, hard=False,
                            detail=err or f"langs: {sorted(svc.toolchain.driver)}"))
    if svc.llm is not None:
        checks.append(Check(name="llm endpoint", ok=svc.llm.ping(), hard=False, detail=cfg.llm.base_url or ""))
    else:
        checks.append(Check(name="llm endpoint", ok=False, hard=False, detail="not configured"))
    if cfg.swarm.url:
        client = svc.swarm()
        checks.append(Check(name="swarm", ok=client is not None, hard=False,
                            detail=cfg.swarm.url if client else "owner must log in for Swarm access"))
    lc = svc.toolchain.libclang
    return HealthReport(checks=checks, ready=all(c.ok for c in checks if c.hard),
                        index_generation=svc.index.generation(),
                        libclang=lc.version if lc else None, strip_flags=sorted(svc.toolchain.strip),
                        p4_sources=dict(ws.p4_sources))
