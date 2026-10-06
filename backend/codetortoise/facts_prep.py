"""Facts prepared for each finding before any model sees it (spec 2026-10-05-two-tier-stories §5.1): the strong model
checks them and decides, instead of hunting for them.

- signature changed: every call site, marked updated in this change, not updated, compiled only in another target, or
  not in any compile database;
- new return value: every caller and how it handles the result (ignored, compared with what, propagated, stored);
- field write: every reader and writer of the field, which changed, and the lines that use it;
- header change: each changed macro, type or declaration and the lines using it in files that include the header;
- body changed (a changed function with callers and no finding): its callers and the lines using its result.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from codetortoise.board import _Ctx
from codetortoise.detectors.base import Finding
from codetortoise.targets import UNKNOWN

FACT_CHARS = 2400                     # 600 tokens per finding
_ASSIGN = re.compile(r"(^|[^=!<>])=([^=]|$)")


def finding_key(f: Finding) -> str:
    """A finding's identity across renumbering and re-runs: its kind and title."""
    return f"{f.kind}|{f.title}"


def _rel(x: _Ctx, path: str | None) -> str:
    root = x.c.root.rstrip("/") + "/"
    return (path[len(root):] if path and x.c.root and path.startswith(root) else path) or "?"


def _line(x: _Ctx, path: str, line: int, read: dict[str, str] | None = None) -> str:
    """Line `line` of `path` after the change; `read` holds the text of files outside it."""
    fc = x.texts.get(path)
    rows = (fc.after if fc else (read or {}).get(path, "")).splitlines()
    return rows[line - 1].strip() if 0 < line <= len(rows) else ""


def _cap(rows: list[str]) -> str:
    text = "\n".join(rows)
    return text if len(text) <= FACT_CHARS else text[:FACT_CHARS - 1] + "…"


def _targets_of(targets: dict[str, list[str]], path: str | None) -> set[str]:
    return set(targets.get(path or "", [])) or {UNKNOWN}


def _call_sites(x: _Ctx, nid: str) -> list:
    key = x.im.nodes[nid].key
    return sorted((c for c in x.calls_after if c.callee == key), key=lambda c: (c.file, c.line))


def signature_facts(x: _Ctx, nid: str, targets: dict[str, list[str]], read: dict[str, str] | None = None) -> list[str]:
    n = x.im.nodes[nid]
    mine = _targets_of(targets, x.local(nid))
    rows = [f"call sites of {n.label} ({nid}):"]
    for c in _call_sites(x, nid):
        caller = x.id_of.get(c.caller)
        where = _targets_of(targets, c.file)
        mark = ("not in any compile database" if where == {UNKNOWN}
                else "compiled only in another target" if not (where & mine)
                else "updated in this change" if caller in x.changed else "not updated")
        rows.append(f"  {_rel(x, c.file)}:{c.line} in {x.label(caller) if caller else c.caller} ({caller or '-'}): "
                    f"{mark}: `{_line(x, c.file, c.line, read)}`")
    heur = [e for e in x.im.edges if e.dst == nid and e.kind == "call" and e.confidence == "heuristic"]
    if heur:
        rows.append(f"  {len(heur)} more caller(s) outside the parsed files, by name only: "
                    + ", ".join(sorted({x.label(e.src) for e in heur})[:10]))
    if len(rows) == 1:
        rows.append("  none found in the parsed files")
    return rows


def returns_facts(x: _Ctx, nid: str, read: dict[str, str] | None = None) -> list[str]:
    n = x.im.nodes[nid]
    rows = [f"callers of {n.label} ({nid}) and how each handles its result:"]
    for c in _call_sites(x, nid):
        caller = x.id_of.get(c.caller)
        text = _line(x, c.file, c.line, read)
        before_call = text.split(c.callee_name, 1)[0] if c.callee_name in text else ""
        how = ("ignored" if not c.result_used
               else "compared with " + ", ".join(f"{c.compared_names[v]} ({v})" if v in c.compared_names else v
                                                 for v in c.compared) if c.compared
               else "propagated" if re.search(r"\breturn\b", before_call)
               else "stored" if _ASSIGN.search(before_call) else "used")
        rows.append(f"  {_rel(x, c.file)}:{c.line} in {x.label(caller) if caller else c.caller} ({caller or '-'}): {how}: "
                    f"`{text}`")
    if len(rows) == 1:
        rows.append("  none found in the parsed files")
    return rows


def field_facts(x: _Ctx, field_id: str, read: dict[str, str] | None = None) -> list[str]:
    n = x.im.nodes[field_id]
    rows = [f"readers and writers of {n.label} ({field_id}):"]
    for e in sorted((e for e in x.im.edges if e.dst == field_id and e.kind in ("reads", "writes")),
                    key=lambda e: (x.label(e.src), e.kind)):
        fn = x.im.nodes[e.src]
        lines = sorted({(a.file, a.line, a.mode) for a in x.fields_after if f"field:{a.field}" == n.key
                        and a.fn == fn.key})
        where = "; ".join(f"{_rel(x, f)}:{ln} {mode} `{_line(x, f, ln, read)}`" for f, ln, mode in lines[:3]) or "no lines"
        rows.append(f"  {fn.label} ({e.src}) {e.kind[:-1]}s it" + (" — changed in this change" if e.src in x.changed else "")
                    + (f" ({e.status} by this change)" if e.status != "unchanged" else "") + f": {where}")
    return rows


def behaviour_facts(x: _Ctx, nid: str, read: dict[str, str] | None = None) -> list[str]:
    """A changed function's callers and the lines using its result (its contract did not change)."""
    rows = [f"{x.label(nid)} ({nid}) changed its body; its callers:"]
    for c in _call_sites(x, nid):
        caller = x.id_of.get(c.caller)
        use = "result ignored" if not c.result_used else "result used"
        rows.append(f"  {_rel(x, c.file)}:{c.line} in {x.label(caller) if caller else c.caller} ({caller or '-'}): {use}: "
                    f"`{_line(x, c.file, c.line, read)}`" + (" — changed in this change" if caller in x.changed else ""))
    return rows


def header_facts(x: _Ctx, f: Finding, includers: Callable[[str], set[str]] | None,
                 read_text: Callable[[str], str | None] | None, files: int = 30, hits: int = 5) -> list[str]:
    header = next((e.file for e in f.evidence if e.file), None)
    names = [e.text.split(": ", 1)[-1] for e in f.evidence if e.file]
    rows = [f"changes in {_rel(x, header)}: " + ", ".join(names)]
    users = sorted(includers(header))[:files] if includers and header else []
    for name in names:
        word = re.compile(rf"\b{re.escape(name.split()[-1])}\b")
        found = []
        for path in users:
            fc = x.texts.get(path)
            text = fc.after if fc else (read_text(path) if read_text else None) or ""
            for i, row in enumerate(text.splitlines(), 1):
                if word.search(row):
                    found.append(f"    {_rel(x, path)}:{i} `{row.strip()}`")
                    if len(found) >= hits:
                        break
            if len(found) >= hits:
                break
        rows.append(f"  {name}: " + ("used at\n" + "\n".join(found) if found else "no use found in the files including it"))
    if users:
        rows.append(f"  ({len(users)} including file(s) searched)")
    return rows


def prepare_facts(x: _Ctx, findings: list[Finding], targets: dict[str, list[str]],
                  includers: Callable[[str], set[str]] | None = None,
                  read_text: Callable[[str], str | None] | None = None) -> dict[str, str]:
    """finding_key -> the facts the strong model checks for it. `read_text` reads files outside the change (the lines of
    callers and readers there, and the header search)."""
    read = {p: read_text(p) or "" for p in sorted({c.file for c in x.calls_after} | {a.file for a in x.fields_after})
            if p not in x.texts} if read_text is not None else {}
    out = {}
    for f in findings:
        fn = next((n for n in f.nodes if n in x.im.nodes and x.im.nodes[n].kind == "function"), None)
        rows: list[str] = []
        if f.kind == "contract" and fn:
            if "signature changed" in f.title:
                rows += signature_facts(x, fn, targets, read)
            if "new return value" in f.title:
                rows += returns_facts(x, fn, read)
        elif f.kind == "field_mutation":
            field = next((n for n in f.nodes if n in x.im.nodes and x.im.nodes[n].kind == "field"), None)
            rows += field_facts(x, field, read) if field else []
            rows += behaviour_facts(x, fn, read) if fn and not field else []
        elif f.kind == "header_fanout":
            rows += header_facts(x, f, includers, read_text)
        elif fn:
            rows += behaviour_facts(x, fn, read)
        out[finding_key(f)] = _cap(rows) if rows else "no prepared facts"
    return out
