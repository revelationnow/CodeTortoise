"""Walk-throughs (spec 2026-11-02 §4): a story's call path down to its changed function, what that function now does,
and where it lands, chained in calling order and drawn as a sequence. Rules only. Every step points back to the call
path, change, flow or code it comes from; a flow's step carries the flow's check keys, so marking it marks the flow.

One walk-through per story, changed function and case (R3): a function with a condition (gates.py) is walked once each
way. They are listed by condition, those covering the most causes first, and kept when they cover a cause or two
stories that no other walk-through already covers (§4.2, R2)."""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass

from codetortoise.cparse import _negate, _txt, norm_ws
from codetortoise.design import Walk, WalkStep
from codetortoise.gates import SKIP, Branch, FnShape, Sources, line_cl, node_stories
from codetortoise.reading import rel_path

LABEL = 60            # a step's label, in characters (R11)
TITLE = 40            # a condition's test, in a title
MAX_STEPS = 40        # steps per walk-through, after folding (R19)
MAX_LANDINGS = 4      # flows and follow-on reads per walk-through (R19)
REACH = 6             # calls searched down from a frame to a reader
CONTRACT_KINDS = ("caller", "result", "target", "unanalysed")
_LAST = re.compile(r"[\w~]+$")


def _cap(text: str, n: int = LABEL) -> str:
    text = norm_ws(text)
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _code(name: str) -> str:
    """A name in code style for a title: a backtick inside it would flip code and text (frontend Ticks)."""
    return "`" + name.replace("`", "'") + "`"


def statement(src: Sources, path: str, line: int) -> str:
    """A line's code without its trailing comment, `;` or `{`."""
    return _cap(src.line(path, line).split("//", 1)[0].strip().rstrip(";{ \t"))


def call_text(src: Sources, path: str, line: int, callee: str) -> str:
    """The call as written on that line, `uart_send(lg->uart, "\\n", 1)`; else `callee(…)`."""
    want = callee.split("::")[-1]
    s = src.tree(path)[1]
    for node in src.nodes_at(path, line, "call_expression"):
        m = _LAST.search(norm_ws(_txt(s, node.child_by_field_name("function"))))
        if m and m.group(0) == want:
            return _cap(_txt(s, node))
    return f"{want}(…)"


def access_text(src: Sources, path: str, line: int, field: str) -> str:
    """The field access on that line, `u->errors`; else the line's code."""
    s = src.tree(path)[1]
    for node in src.nodes_at(path, line, "field_expression"):
        f = node.child_by_field_name("field")
        if f is not None and _txt(s, f) == field:
            return _cap(_txt(s, node))
    return statement(src, path, line)


def field_of(f) -> str | None:
    """A state flow's field: the node before its landing, when that is not the writer (frontend flowGroups.fieldOf)."""
    if f.tag != "state" or len(f.path) < 2 or not f.cause:
        return None
    return None if f.path[-2] == f.cause else f.path[-2]


def flow_keys(f, checks, x) -> list[str]:
    """A flow's check keys, every kind (R6): frontend flowGroups.flowPlaces, whose hidden kinds the browser leaves out
    itself."""
    if not f.cause:
        return []
    fld = field_of(f)
    name = x.label(fld) if fld else None
    return [k.key for k in checks if k.related == f.cause and k.node == f.lands
            and ((k.kind == "reader" and (name is None or k.field == name)) if f.tag == "state" else k.kind in CONTRACT_KINDS)]


def _raising(x, nid: str) -> int | None:
    """The first line returning a value the function did not return before (clang's literal returns)."""
    key = x.im.nodes[nid].key
    fa, fb = x.fa.get(key), x.fb.get(key)
    if fa is None:
        return None
    new = [fa.return_lines[v] for v in fa.returns if (fb is None or v not in fb.returns) and v in fa.return_lines]
    return min(new) if new else None


def _runs(g: Branch | None, case: bool | None, line: int) -> bool:
    """Whether a line of the gated function runs on this side of its condition."""
    if g is None or case is None or line == g.line or line in g.test_lines:
        return True
    inside = g.first <= line <= g.last
    if not case:
        return not inside
    if inside:
        return True
    if g.chain is not None and g.chain[0] <= line <= g.chain[1]:
        return line in g.tried            # no other arm of its chain runs, only the tests before it
    if line < g.line:
        return True
    return g.skips is None or not g.skips[0] <= line <= g.skips[1]   # after the block: unless its return or jump skips it


def _loop_at(shape: FnShape | None, line: int) -> str | None:
    """The innermost loop holding a line."""
    best = None
    for lp in shape.loops if shape is not None else []:
        if lp.first <= line <= lp.last and (best is None or lp.last - lp.first < best.last - best.first):
            best = lp
    return best.text if best is not None else None


def fold(steps: list[WalkStep], important: set[str], depth: int) -> list[WalkStep]:
    """Unchanged calls (or returns) far from what matters fold into one step (§4.2, R13, R30): a run of two or more of
    one kind, each from a call path or unchanged code, both of whose ends are at least `depth` calls from a changed
    function, a landing or a reader. Distances run over the walk's own calls and returns; an end not measured is 0."""
    adj: dict[str, set[str]] = defaultdict(set)
    for s in steps:
        if s.kind in ("call", "return") and s.src != s.dst:
            adj[s.src].add(s.dst)
            adj[s.dst].add(s.src)
    seeds = set(important) | {n for s in steps if s.ref in ("flow", "change") for n in (s.src, s.dst)}
    dist = {n: 0 for n in seeds}
    q = deque(seeds)
    while q:
        n = q.popleft()
        for m in adj[n]:
            if m not in dist:
                dist[m] = dist[n] + 1
                q.append(m)

    def far(s: WalkStep) -> bool:
        return s.kind in ("call", "return") and s.ref in ("path", "code") and \
            min(dist.get(s.src, 0), dist.get(s.dst, 0)) >= depth
    out: list[WalkStep] = []
    i = 0
    while i < len(steps):
        s, j = steps[i], i
        while j < len(steps) and far(steps[j]) and steps[j].kind == s.kind:
            j += 1
        if j - i >= 2:
            word = "calls" if s.kind == "call" else "returns"
            out.append(WalkStep(kind="fold", src=s.src, dst=steps[j - 1].dst, label=f"… {j - i} {word}", status="same",
                                ref="code", folded=j - i))
            i = j
        else:
            out.append(s)
            i += 1
    return out


def _folded(run: list[WalkStep], label: str) -> WalkStep:
    loops = {s.loop for s in run}
    return WalkStep(kind="fold", src=run[0].src, dst=run[-1].dst, label=label, ref="code", folded=len(run),
                    status="same" if all(s.status == "same" for s in run) else "changed",
                    loop=loops.pop() if len(loops) == 1 else None)


def shrink(steps: list[WalkStep], cap: int, F: str) -> list[WalkStep]:
    """A walk-through over `cap` steps (R19) folds the steps that carry nothing of their own, the longest run first and
    from its end, into one "… N steps" step each, until it fits. Its call path, F's condition, signature and return,
    its flows and reads, and everything after F's return (its landings and the way back up) stay. Should those alone
    pass the cap, the steps past it fold into one at the end, so the walk still says how many it leaves out."""
    back = next((i for i in range(len(steps) - 1, -1, -1) if steps[i].kind == "return" and steps[i].src == F), len(steps))
    keep = [i >= back or s.ref in ("flow", "path") or s.kind in ("read", "fold") or
            (s.src == F and s.kind in ("self", "return")) for i, s in enumerate(steps)]
    steps = list(steps)
    while len(steps) > cap:
        best: tuple[int, int] | None = None
        i = 0
        while i < len(steps):
            j = i
            while j < len(steps) and not keep[j]:
                j += 1
            if j - i >= 2 and (best is None or j - i > best[1] - best[0]):
                best = (i, j)
            i = j + 1
        if best is None:
            break
        i, j = best
        a = max(i, j - (len(steps) - cap + 1))
        steps[a:j] = [_folded(steps[a:j], f"… {j - a} steps")]
        keep[a:j] = [True]                                   # a fold is not folded again
    if len(steps) > cap:
        rest = steps[cap - 1:]
        steps = steps[:cap - 1] + [_folded(rest, f"… {len(rest)} more steps")]
    return steps


@dataclass
class _Cand:
    walk: Walk
    causes: set[str]
    cover: set[str]
    group: str                        # its condition, else story:function
    pos: int                          # its story's place in the reading


def _keep(cands: list[_Cand], max_walks: int) -> list[Walk]:
    """Kept: a cause or two stories, not covered by another (§4.2). Listed by condition, the most causes first, then
    the story's place, the true side before the false (R2); numbered in that order (§18.1)."""
    cands = [c for c in cands if c.causes or len(c.walk.stories) >= 2]
    most: dict[str, int] = defaultdict(int)
    first: dict[str, int] = {}
    for c in cands:
        most[c.group] = max(most[c.group], len(c.causes))
        first[c.group] = min(first.get(c.group, c.pos), c.pos)
    side = {True: 0, False: 1, None: 2}
    cands.sort(key=lambda c: (-most[c.group], first[c.group], c.group, side[c.walk.case]))
    kept: list[_Cand] = []
    for c in cands:
        if any(c.cover < o.cover for o in cands) or any(c.cover == o.cover for o in kept):
            continue
        kept.append(c)
    out = [c.walk for c in kept[:max(max_walks, 0)]]
    for i, w in enumerate(out, 1):
        w.id = f"W{i}"
    return out


class _Walker:
    """What every walk-through of a review looks things up in."""

    def __init__(self, x, ss, details, r, per, src: Sources, branches: list[Branch], lines, depth: int):
        self.x, self.r, self.per, self.src, self.lines, self.depth = x, r, per, src, lines, depth
        self.story_of = node_stories(ss)
        self.thread_of = {sid: t.id for t in r.threads for sid in t.stories}
        self.thread_pos = {t.id: i for i, t in enumerate(r.threads)}
        self.pos = {sid: i for i, sid in enumerate(r.order)}
        self.flows: dict[str, list] = {}
        for s in ss.stories:
            d = (details or {}).get(s.id)
            self.flows[s.id] = [f for f in (d.board.flows if d is not None else []) if f.id in s.flows]
        self.flow_n = {(sid, f.id): i for sid, fs in self.flows.items() for i, f in enumerate(fs, 1)}
        self.flow_story = {f.id: sid for sid, fs in self.flows.items() for f in fs}
        self.flow_by_id = {f.id: f for fs in self.flows.values() for f in fs}
        self.check = {k.key: k for k in r.checks}
        self.gate_of: dict[str, Branch] = {}
        for b in branches:
            self.gate_of.setdefault(b.node, b)
        self.calls: dict[tuple[str, str], list] = defaultdict(list)
        self.calls_from: dict[str, list] = defaultdict(list)
        for e in sorted(x.calls_after, key=lambda e: (e.file, e.line)):
            self.calls[(e.caller, e.callee)].append(e)
            self.calls_from[e.caller].append(e)
        down: dict[str, set[str]] = defaultdict(set)
        for e in x.im.edges:
            if e.kind in ("call", "virtual") and e.status != "removed" and not x.is_test_path(e.src):
                down[e.src].add(e.dst)
        self.down = {k: sorted(v, key=lambda n: (x.label(n), n)) for k, v in down.items()}
        self.edge = {(e.src, e.dst, e.kind): e.id for e in x.im.edges}
        self.access: dict[str, list] = defaultdict(list)
        for a in sorted(x.fields_after, key=lambda a: (a.line, a.field)):
            self.access[a.fn].append(a)
        self.file_threads: dict[str, set[str]] = defaultdict(set)
        for sid, sr in per.items():
            t = self.thread_of.get(sid)
            for w in sr.where if t else []:
                self.file_threads[w.path].add(t)

    # ---------------------------------------------------------------- steps
    def _step(self, kind, a, b, label, status, path=None, line=None, **kw) -> WalkStep:
        cl = line_cl(self.x, path, line, self.lines) if path and line and status != "same" else None
        return WalkStep(kind=kind, src=a, dst=b, label=label, status=status, path=rel_path(self.x, path) if path else "",
                        line=line, cl=cl, **kw)

    def _call(self, a: str, b: str, e=None) -> WalkStep:
        """A call from a to b as written at its first call site (after side)."""
        x = self.x
        if e is None:
            es = self.calls.get((x.im.nodes[a].key, x.im.nodes[b].key))
            e = es[0] if es else None
        edge = self.edge.get((a, b, "call")) or self.edge.get((a, b, "virtual"))
        if e is None:
            return self._step("call", a, b, f"{x.label(b).split('::')[-1]}(…)", "same", edge=edge)
        return self._step("call", a, b, call_text(self.src, e.file, e.line, x.label(b)),
                          self.src.marks(e.file).get(e.line, "same"), e.file, e.line, edge=edge)

    def _sig(self, fn) -> tuple[str, int]:
        """A function's signature as written: the first of its lines that names it."""
        for k in range(fn.start_line, min(fn.start_line + 3, fn.end_line) + 1):
            t = statement(self.src, fn.file, k)
            if fn.name in t:
                return t, k
        return _cap(fn.signature), fn.start_line

    def _single_return(self, nid: str) -> tuple[str, int | None, str | None]:
        """A function's one returned expression, its first line and file; "" when it returns several or none."""
        shape = self.src.shape(nid)
        if shape is None or not shape.returns:
            return "", None, None
        vals = {v for _, v in shape.returns}
        if len(vals) != 1:
            return "", None, shape.path
        return _cap(vals.pop()), shape.returns[0][0], shape.path

    def _back(self, callee: str, caller: str) -> WalkStep:
        label, at, path = self._single_return(callee)
        return self._step("return", callee, caller, label, self.src.marks(path).get(at, "same") if at else "same",
                          path if at else None, at)

    def _flow_ref(self, st: WalkStep, fl) -> None:
        sid = self.flow_story.get(fl.id)
        keys = flow_keys(fl, self.r.checks, self.x)
        st.ref, st.story, st.flow, st.flow_n, st.keys = "flow", sid, fl.id, self.flow_n.get((sid, fl.id)), keys
        st.cause = next((self.check[k].cause for k in keys if k in self.check and self.check[k].cause), None)

    def _attach(self, fl) -> str:
        """Where a contract flow's checks sit on the walk (R31): a result row on the return, other rows on the call."""
        kinds = {self.check[k].kind for k in flow_keys(fl, self.r.checks, self.x) if k in self.check}
        if "result" in kinds:
            return "return"
        if kinds:
            return "call"
        return "call" if fl.text.endswith("signature changed") else "return"

    def _read(self, fld: str, reader: str) -> WalkStep:
        x = self.x
        fkey = x.im.nodes[fld].key
        acc = next((a for a in self.access.get(x.im.nodes[reader].key, [])
                    if f"field:{a.field}" == fkey and a.mode == "read"), None)
        if acc is None:
            return self._step("read", fld, reader, x.label(fld).split("::")[-1], "same")
        return self._step("read", fld, reader, access_text(self.src, acc.file, acc.line, acc.field_name),
                          self.src.marks(acc.file).get(acc.line, "same"), acc.file, acc.line)

    # ---------------------------------------------------------------- the path through
    def _spine(self, sid: str, F: str) -> tuple:
        """The calls from an entry down to F (R3): the story's first flow through F, else its first call path ending at
        F, else F alone; and the flow, when one gave it."""
        for fl in self.flows.get(sid, []):
            if fl.cause == F and F in fl.path:
                return fl, list(fl.path[:fl.path.index(F) + 1])
        sr = self.per.get(sid)
        for p in sr.paths if sr is not None else []:
            if p.steps and p.steps[-1] == F:
                return None, list(p.steps)
        return None, [F]

    def _result_flow(self, sid: str, F: str, caller: str | None):
        """The story's contract flow from F whose checks sit on the return to the caller."""
        if caller is None:
            return None
        return next((fl for fl in self.flows.get(sid, []) if fl.tag == "contract" and fl.cause == F and
                     fl.lands == caller and self._attach(fl) == "return"), None)

    def _taken(self, F: str, shape: FnShape | None, gate: Branch | None, case: bool | None, result) -> int | None:
        """The return F takes on this side: the block's own return, when its condition holds; else the line raising a
        new value a result flow carries back, when it runs; else the first return at F's top level that runs. A return
        nested in another if, switch or loop may not run, so none of those ends the walk: it goes on to F's end."""
        if shape is None:
            return None
        if case is True and gate is not None and gate.ends:
            return gate.ends[0]
        rise = _raising(self.x, F)
        if result is not None and rise is not None and _runs(gate, case, rise):
            return rise
        runs = [k for k in shape.ends if _runs(gate, case, k)]
        return runs[0] if runs else None

    def _writes(self, F: str, fld: str, gate, case, taken) -> bool:
        """Whether F writes the field on a line that runs before its return (marked or not, R29)."""
        fkey = self.x.im.nodes[fld].key
        return any(f"field:{a.field}" == fkey and a.mode != "read" and _runs(gate, case, a.line) and
                   (taken is None or a.line <= taken) for a in self.access.get(self.x.im.nodes[F].key, []))

    def _readers(self, fid: str, F: str, sid: str) -> list[str]:
        """Changed functions of other stories that read a field F wrote."""
        x, fkey = self.x, self.x.im.nodes[fid].key
        out = []
        for n in sorted(x.changed, key=lambda n: (len(n), n)):
            s, k = self.story_of.get(n), x.im.nodes[n].key
            if n == F or s is None or s == sid or k not in x.fa:
                continue
            if any(f"field:{a.field}" == fkey and a.mode == "read" for a in self.access.get(k, [])):
                out.append(n)
        return out

    def _reach(self, a: str, target: str) -> list[str] | None:
        """A shortest chain of live calls from a down to target, at most REACH long."""
        if a == target:
            return [a]
        prev: dict[str, str | None] = {a: None}
        q = deque([(a, 0)])
        while q:
            n, d = q.popleft()
            if d >= REACH:
                continue
            for m in self.down.get(n, []):
                if m in prev:
                    continue
                prev[m] = n
                if m == target:
                    out = [m]
                    while prev[out[-1]] is not None:
                        out.append(prev[out[-1]])
                    return out[::-1]
                q.append((m, d + 1))
        return None

    def _land(self, steps: list[WalkStep], stack: list[str], target: str) -> list[str]:
        """Return to the deepest frame that calls down to target, then call down to it; the new stack. A target no
        frame reaches is read where the walk stands."""
        for i in range(len(stack) - 1, -1, -1):
            path = self._reach(stack[i], target)
            if path is None:
                continue
            while len(stack) > i + 1:
                steps.append(self._back(stack[-1], stack[-2]))
                stack = stack[:-1]
            for a, b in zip(path, path[1:], strict=False):
                steps.append(self._call(a, b))
            return stack + path[1:]
        return stack

    def _call_into(self, F: str, e, sid: str, marks: dict[int, str], loop: str | None) -> list[WalkStep]:
        """A call F makes on a changed line or into changed code, and what changed in the callee: its signature, its
        writes on changed lines, and its return (R10)."""
        x, src = self.x, self.src
        callee = x.id_of[e.callee]
        st = self._call(F, callee, e)
        st.loop = loop
        if e.line in marks:
            st.ref, st.story = "change", sid
        out = [st]
        key = x.im.nodes[callee].key
        cfa, cfb = x.fa.get(key), x.fb.get(key)
        csid = self.story_of.get(callee)
        if cfa is not None and cfb is not None and cfa.signature != cfb.signature:
            label, at = self._sig(cfa)
            out.append(self._step("self", callee, callee, label, "changed", cfa.file, at, ref="change", story=csid,
                                  loop=loop))
        if cfa is not None:
            cm, seen = src.marks(cfa.file), set()
            for acc in self.access.get(key, []):
                fid = x.id_of.get(f"field:{acc.field}")
                if acc.mode == "read" or acc.line not in cm or (acc.line, acc.field) in seen or fid is None:
                    continue
                seen.add((acc.line, acc.field))
                out.append(self._step("write", callee, fid, statement(src, acc.file, acc.line), cm[acc.line], acc.file,
                                      acc.line, ref="change", story=csid, loop=loop))
        back = self._back(callee, F)
        back.loop = loop
        out.append(back)
        return out

    # ---------------------------------------------------------------- one walk-through
    def walk(self, sid: str, F: str, gate: Branch | None, case: bool | None) -> _Cand | None:
        x, src = self.x, self.src
        key = x.im.nodes[F].key
        fa, fb = x.fa[key], x.fb.get(key)
        shape = src.shape(F)
        marks = src.marks(fa.file)
        flow, spine = self._spine(sid, F)
        caller = spine[-2] if len(spine) >= 2 else None
        steps: list[WalkStep] = []

        # 1. down the call path; a contract flow whose checks sit on the call marks the last call
        on_call = flow is not None and flow.tag == "contract" and flow.lands == caller and self._attach(flow) == "call"
        for a, b in zip(spine, spine[1:], strict=False):
            st = self._call(a, b)
            st.ref, st.story = "path", sid
            if flow is not None:
                st.flow, st.flow_n = flow.id, self.flow_n.get((sid, flow.id))
            if b == F and on_call:
                self._flow_ref(st, flow)
            steps.append(st)

        # 2. what F now does, in line order, up to the return it takes (R10, R32)
        result = self._result_flow(sid, F, caller)
        taken = self._taken(F, shape, gate, case, result)
        events: list[tuple[int, int, str, object]] = []
        if fb is not None and fb.signature != fa.signature:
            events.append((fa.start_line, 0, "sig", fa))
        if gate is not None:
            events.append((gate.line, 1, "gate", gate))
        seen: set = set()
        for e in self.calls_from.get(key, []):
            callee = x.id_of.get(e.callee)
            if callee is None or (e.line, callee) in seen or not _runs(gate, case, e.line):
                continue
            if e.line in marks or callee in x.changed:
                seen.add((e.line, callee))
                events.append((e.line, 2, "call", e))
        for acc in self.access.get(key, []):
            if acc.mode == "read" or acc.line not in marks or not _runs(gate, case, acc.line) or (acc.line, acc.field) in seen:
                continue
            seen.add((acc.line, acc.field))
            events.append((acc.line, 3, "write", acc))
        events.sort(key=lambda ev: (ev[0], ev[1]))
        wrote: list[str] = []
        for line, _, kind, obj in events:
            if taken is not None and line > taken:
                break
            loop = _loop_at(shape, line)
            if kind == "sig":
                label, at = self._sig(fa)
                steps.append(self._step("self", F, F, label, "changed", fa.file, at, ref="change", story=sid, loop=loop))
            elif kind == "gate":
                test = obj.test if case is not False else _negate(obj.test)
                steps.append(self._step("self", F, F, _cap(test), marks.get(obj.line, "same"), fa.file, obj.line,
                                        ref="change", story=sid, loop=loop))
            elif kind == "call":
                steps += self._call_into(F, obj, sid, marks, loop)
            else:
                fid = x.id_of.get(f"field:{obj.field}")
                if fid is None:
                    continue
                steps.append(self._step("write", F, fid, statement(src, obj.file, obj.line), marks[obj.line], obj.file,
                                        obj.line, ref="change", story=sid, loop=loop))
                if fid not in wrote:
                    wrote.append(fid)

        # 3. back to the caller, carrying a result flow's checks when this return raises its value
        stack = list(spine)
        if caller is not None:
            label = next((v for k, v in (shape.returns if shape is not None else []) if k == taken), "")
            st = self._step("return", F, caller, _cap(label), marks.get(taken, "same") if taken else "same",
                            fa.file if taken else None, taken)
            if result is not None and taken is not None and taken == _raising(x, F):
                self._flow_ref(st, result)
            elif taken is not None and taken in marks:
                st.ref, st.story = "change", sid
            steps.append(st)
            stack.pop()

        # 4. where its state flows land; 5. changed readers, in other stories, of what it wrote
        landings = 0
        for fl in self.flows.get(sid, []):
            fld = field_of(fl)
            if landings >= MAX_LANDINGS or fl.tag != "state" or fl.cause != F or fld is None:
                continue
            if not self._writes(F, fld, gate, case, taken):
                continue
            stack = self._land(steps, stack, fl.lands)
            st = self._read(fld, fl.lands)
            self._flow_ref(st, fl)
            steps.append(st)
            landings += 1
        for fid in wrote:
            for reader in self._readers(fid, F, sid):
                if landings >= MAX_LANDINGS:
                    break
                stack = self._land(steps, stack, reader)
                st = self._read(fid, reader)
                st.ref, st.story = "change", self.story_of.get(reader)
                steps.append(st)
                landings += 1

        # 6. back up to the entry
        while len(stack) >= 2:
            steps.append(self._back(stack[-1], stack[-2]))
            stack.pop()
        if not steps:
            return None
        return self._finish(sid, F, gate, case, spine, steps)

    def _finish(self, sid, F, gate, case, spine, steps) -> _Cand:
        x = self.x
        important = {n for s in steps for n in (s.src, s.dst) if n in x.changed}
        important |= {s.dst for s in steps if s.kind == "read"}
        important |= {self.flow_by_id[s.flow].lands for s in steps if s.ref == "flow" and s.flow in self.flow_by_id}
        whole = fold(steps, important, self.depth)       # what it covers and the checks it carries, before it shrinks
        steps = shrink(whole, MAX_STEPS, F)
        parts: list[str] = []
        stories: list[str] = []
        for s in steps:
            for n in (s.src, s.dst):
                if x.im.nodes[n].kind == "function" and n not in parts:
                    parts.append(n)
            if s.story and s.story not in stories:
                stories.append(s.story)
        causes = {self.check[k].cause for s in whole if s.ref == "flow" for k in s.keys
                  if k in self.check and self.check[k].cause}
        thread, connection = self._anchor(sid, steps)
        w = Walk(id="", title=self._title(gate, case, spine, F), thread=thread, connection=connection,
                 condition=gate.id if gate is not None else None, case=case, parts=parts, stories=stories, steps=steps)
        cover = {s.story for s in whole if s.story} | {f"flow:{s.flow}" for s in whole if s.ref == "flow" and s.flow}
        group = gate.id if gate is not None else f"{sid}:{F}"
        return _Cand(w, causes, cover, group, self.pos.get(sid, len(self.pos)))

    def _anchor(self, sid: str, steps: list[WalkStep]) -> tuple[str | None, tuple[str, str] | None]:
        """Its thread, and the connection it crosses (§2, R8): a step from another thread's story, or a flow landing in
        a file another thread's stories change."""
        thread = self.thread_of.get(sid)
        for s in steps:
            other: set[str] = set()
            if s.story and self.thread_of.get(s.story) not in (None, thread):
                other = {self.thread_of[s.story]}
            elif s.ref == "flow" and s.flow in self.flow_by_id:
                loc = self.x.local(self.flow_by_id[s.flow].lands)
                other = (self.file_threads.get(rel_path(self.x, loc), set()) - {thread}) if loc else set()
            if other and thread:
                t = min(other, key=lambda t: self.thread_pos.get(t, len(self.thread_pos)))
                k = next((k for k in self.r.connections if {k.a, k.b} == {thread, t}), None)
                if k is not None:
                    return thread, (k.a, k.b)
        return thread, None

    def _title(self, gate, case, spine, F) -> str:
        """The fixed title (§4.2): the condition's side, else the entry and the changed function."""
        if gate is not None and case is not None:
            t = _code(_cap(gate.test, TITLE))
            return f"When {t}" if case else f"When {t} is false"
        if spine[0] == F:
            return f"In {_code(self.x.label(F))}"
        return f"From {_code(self.x.label(spine[0]))} through {_code(self.x.label(F))}"


def build_walks(x, ss, details, r, per, src: Sources, branches: list[Branch], lines=None, *, depth: int | None = None,
                max_walks: int | None = None) -> list[Walk]:
    """The review's walk-throughs (§4.2): for each story in reading order (not mechanical or tests ones), each changed
    function that exists after the change, each side of its strongest condition."""
    cfg = x.c.cfg
    w = _Walker(x, ss, details, r, per, src, branches, lines, cfg.walk_depth if depth is None else depth)
    story = {s.id: s for s in ss.stories}
    cands: list[_Cand] = []
    for sid in r.order:
        s = story.get(sid)
        if s is None or s.kind in SKIP:
            continue
        for F in s.nodes:
            n = x.im.nodes.get(F)
            if n is None or n.kind != "function" or n.key not in x.fa:
                continue
            gate = w.gate_of.get(F)
            for case in ((True, False) if gate is not None else (None,)):
                c = w.walk(sid, F, gate, case)
                if c is not None:
                    cands.append(c)
    return _keep(cands, cfg.max_walks if max_walks is None else max_walks)
