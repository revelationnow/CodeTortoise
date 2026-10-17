"""Checks grouped by the change that raised them (spec 2026-10-16-outline-and-causes §4)."""
from __future__ import annotations

import hashlib
from collections import defaultdict

from codetortoise.board import Flow, _Ctx, _opcodes
from codetortoise.reading import CHECK_ORDER, Cause, CauseChange, ChangeLine, Check, Thread, _qual, rel_path

_ALONE = {"unanalysed", "ask"}       # a row of these kinds is its own cause


def cause_id(kind: str, qual: str, subject: str) -> str:
    """Stable across re-runs: kind, the function's qualified name and the subject only."""
    return "c" + hashlib.sha1(f"{kind}|{qual}|{subject}".encode()).hexdigest()[:10]


def _group(k: Check, x: _Ctx) -> tuple[str, str, str]:
    if k.kind == "untested":
        return k.kind, f"story:{k.story or ''}", ""
    if k.kind in _ALONE:
        return k.kind, "", k.key
    return k.kind, _qual(x, k.cause_fn) if k.cause_fn else "", k.cause_subject


def _text(kind: str, rows: list[Check], fn: str) -> str:
    n = len(rows)
    if n == 1 or kind in ("hazard", "confirm") or kind in _ALONE:
        return rows[0].text
    if kind == "reader":
        return f"{n} places read `{rows[0].field}`, which `{fn}` now writes"
    if kind == "caller":
        return f"{n} callers not updated for `{fn}`'s new signature"
    if kind == "result":
        return f"{n} callers handle `{fn}`'s result the old way"
    if kind == "target":
        return f"{n} calls to `{fn}` from other build targets" if fn else rows[0].text
    return f"{n} functions no test calls"          # untested


MAX_LINES = 6


def _cap(lines: list[ChangeLine], focus: set[int]) -> list[ChangeLine]:
    """At most six: context goes first, then removed lines, then added lines farthest from the focus."""
    if len(lines) <= MAX_LINES:
        return lines
    lines = [ln for ln in lines if ln.sign != " "]
    while len(lines) > MAX_LINES:
        minus = [i for i, ln in enumerate(lines) if ln.sign == "-"]
        if minus:
            lines.pop(minus[0])
            continue
        if focus:
            far = max(range(len(lines)), key=lambda i: min(abs((lines[i].line or 0) - f) for f in focus))
        else:
            far = len(lines) - 1
        lines.pop(far)
    return lines


def _block(x: _Ctx, local: str, lo: int | None, hi: int | None, focus: set[int]) -> list[ChangeLine]:
    """The changed block of `local` within after-lines [lo, hi] holding a focus line (any block when `focus` is empty),
    with a line of context each side."""
    fc = x.texts.get(local)
    if fc is None:
        return []
    b, a = fc.before.splitlines(), fc.after.splitlines()
    blocks = [op for op in _opcodes(fc.before, fc.after) if op[0] != "equal"
              and (lo is None or (op[3] + 1 <= hi and max(op[4], op[3] + 1) >= lo))]
    pick = next((op for op in blocks if any(op[3] < f <= max(op[4], op[3] + 1) for f in focus)), None) if focus \
        else (blocks[0] if blocks else None)
    if pick is None:
        return []
    _, i1, i2, j1, j2 = pick
    out = [ChangeLine(sign=" ", text=a[j1 - 1], line=j1)] if j1 > 0 else []
    out += [ChangeLine(sign="-", text=b[i], line=i + 1) for i in range(i1, i2)]
    out += [ChangeLine(sign="+", text=a[j], line=j + 1) for j in range(j1, j2)]
    if j2 < len(a):
        out.append(ChangeLine(sign=" ", text=a[j2], line=j2 + 1))
    return _cap(out, focus)


def change_for(kind: str, rows: list[Check], x: _Ctx) -> CauseChange | None:
    """The 2–6 changed lines that raised a cause of `kind` made of `rows` (spec 2026-10-16 §4.8)."""
    lead = rows[0]
    if kind == "target" and lead.cause_fn is None:          # a changed header included by another target's files
        local = next((p for p in x.texts if rel_path(x, p) == lead.cause_subject), None)
        lines = _block(x, local, None, None, set()) if local else []
        return CauseChange(path=lead.cause_subject, lines=lines) if lines else None
    n = lead.cause_fn
    if n is None or n not in x.im.nodes:
        return None
    key = x.im.nodes[n].key
    fb, fa = x.fb.get(key), x.fa.get(key)
    if fa is None:
        return None
    label = x.label(n)

    def made(lines: list[ChangeLine]) -> CauseChange | None:
        return CauseChange(path=rel_path(x, fa.file), function=label, lines=lines) if lines else None
    if kind == "caller" and fb is not None and fb.signature != fa.signature:
        return made([ChangeLine(sign="-", text=fb.signature, line=fb.start_line),
                     ChangeLine(sign="+", text=fa.signature, line=fa.start_line)])
    focus: set[int] = set()
    local = fa.file
    if kind == "reader":
        focus = {a.line for a in x.fields_after if a.fn == key and a.mode in ("write", "may_write")
                 and x.im.nodes.get(x.id_of.get(f"field:{a.field}", ""), None) is not None
                 and x.label(x.id_of[f"field:{a.field}"]) == lead.field}
    elif kind == "result" and fb is not None:
        focus = {fa.return_lines[v] for v in fa.returns if v not in fb.returns and v in fa.return_lines}
    elif kind in ("hazard", "confirm"):
        f = next((f for f in x.c.findings if f.id == lead.finding), None)
        ev = [e for e in (f.evidence if f else []) if e.file and e.line]
        if ev:
            local = ev[0].file
            focus = {e.line for e in ev if e.file == local}
    lo, hi = (fa.start_line, fa.end_line) if local == fa.file else (None, None)
    lines = _block(x, local, lo, hi, focus) if focus else []
    if not lines:                                            # the kind's own rule found nothing: the first block
        local = fa.file
        lines = _block(x, local, fa.start_line, fa.end_line, set())
    return CauseChange(path=rel_path(x, local), function=label, lines=lines) if lines else None


def build_causes(rows: list[Check], x: _Ctx, threads: list[Thread], order: list[str],
                 flows_of: dict[str, list[Flow]]) -> list[Cause]:
    """Every row's cause, in reading order (§4.5): thread, the story's reading order, the first flow it touches, kind
    order, text. Sets each row's `cause`."""
    groups: dict[tuple[str, str, str], list[Check]] = defaultdict(list)
    for k in rows:
        groups[_group(k, x)].append(k)
    by_id: dict[str, Cause] = {}
    for (kind, qual, subject), members in groups.items():
        members.sort(key=lambda k: (k.path, k.line or 0, k.key))
        lead = members[0]
        if kind == "untested":
            qual = ",".join(sorted({_qual(x, k.cause_fn) for k in members if k.cause_fn}))
        cid = cause_id(kind, qual, subject)
        for k in members:
            k.cause = cid
        if cid in by_id:                                  # two groups with one id are one cause
            by_id[cid].places += [k.key for k in members]
            continue
        fn = x.label(lead.cause_fn) if lead.cause_fn else ""
        touched = {lead.cause_fn} | {k.node for k in members}
        flows = [fl.id for fl in flows_of.get(lead.story or "", []) if touched & set(fl.path)]
        by_id[cid] = Cause(id=cid, kind=kind, thread=lead.thread, story=lead.story, text=_text(kind, members, fn),
                           places=[k.key for k in members], flows=flows, finding=lead.finding,
                           change=change_for(kind, members, x))
    thread_at = {t.id: i for i, t in enumerate(threads)}
    story_at = {s: i for i, s in enumerate(order)}
    rank = {k: i for i, k in enumerate(CHECK_ORDER)}

    def first_flow(z: Cause) -> int:
        ids = [fl.id for fl in flows_of.get(z.story or "", [])]
        return min((ids.index(f) for f in z.flows), default=len(ids))
    return sorted(by_id.values(), key=lambda z: (thread_at.get(z.thread or "", len(threads)),
                                                 story_at.get(z.story or "", len(order)), first_flow(z), rank[z.kind], z.text))
