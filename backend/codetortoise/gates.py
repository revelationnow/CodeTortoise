"""The conditions a change adds, and which of its changed lines still run when one is false (spec 2026-11-02 §7).

Rules only. A tree-sitter walk of each changed function, after and before, finds its ifs, else-ifs, cases, loops and
returns; `line_marks` finds its new and changed lines. `Sources` reads, parses and diffs each file once, for the
conditions here and the walk-throughs (walks.py) alike. Lines are numbered as clang numbers them (`linediff.lines`)."""
from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from codetortoise import linediff
from codetortoise.cparse import _COND, _at, _line_starts, _parser_for, _txt, flatten_preproc, norm_ws
from codetortoise.design import Gate, GatedLine
from codetortoise.reading import rel_path

MAX_GATES = 20            # conditions kept per review (§14)
MAX_LINES = 200           # lines the strongest condition lists
SIMILAR = 0.6             # an added line this like one its block replaced is "changed", not "new"
PAIRS = 400               # a replaced block bigger than this (old lines × new lines) is all "changed", unpaired
_TRIVIAL = re.compile(r"[{}();,\s]*")
_COMMENT = re.compile(r"//|/\*|\*(\s|/|$)")   # a comment, or a block comment's next line: "* more", "*/"
_LOOPS = {"for_statement", "while_statement", "do_statement", "for_range_loop"}
_INDEXED = ("call_expression", "field_expression")


def trivial(text: str) -> bool:
    """A line that says nothing alone: braces and punctuation, a blank, a comment."""
    t = text.strip()
    return bool(_TRIVIAL.fullmatch(t) or _COMMENT.match(t))         # "*err += 1;" is code


def line_marks(before: str, after: str) -> dict[int, str]:
    """The after side's added lines (1-based), each "new" or "changed": changed when it is at least SIMILAR to a line
    its block replaced (R12). A line whose text, whitespace folded, is one its block removed is a whitespace edit."""
    a, b = linediff.lines(before), linediff.lines(after)
    out: dict[int, str] = {}
    for tag, i1, i2, j1, j2 in linediff.opcodes(before, after):
        if tag not in ("insert", "replace"):
            continue
        old = [norm_ws(t) for t in a[i1:i2]]
        same, big = set(old), len(old) * (j2 - j1) > PAIRS
        for j in range(j1, j2):
            t = norm_ws(b[j])
            if t in same:
                continue
            like = big or any(difflib.SequenceMatcher(None, o, t, autojunk=False).ratio() >= SIMILAR for o in old)
            out[j + 1] = "changed" if old and like else "new"
    return out


@dataclass
class Loop:
    text: str                         # its header as written: "for (i = 0; i < len; i++)"
    first: int
    last: int


@dataclass
class Branch:
    """One if, else if or case of a function and what it guards."""
    node: str                         # the function's node id
    path: str                         # its file (canonical)
    line: int                         # the test's line
    test: str                         # the test, whitespace folded
    first: int                        # the guarded block's first and last line
    last: int
    body: set[int]                    # the lines its statements take up
    own: set[int]                     # the test's lines and the block's braces, statements left out
    returns: list[int] = field(default_factory=list)      # return lines in the body
    alt: tuple[int, int] | None = None                    # a plain else's lines (an else-if is a branch of its own)
    kind: str = "if"                  # if | else if | case; as a gate also changed (its test) or return (a new one)
    strength: int = 0                 # new or changed lines it guards
    id: str = ""


@dataclass
class FnShape:
    node: str
    path: str
    first: int
    last: int
    branches: list[Branch]
    loops: list[Loop]
    returns: list[tuple[int, str]]    # (line, the returned expression as written; "" for a bare return)


def _cond_text(src: bytes, cond) -> str:
    """An if's or switch's test: inside its parentheses (C) or its condition_clause's value (C++)."""
    if cond is None:
        return ""
    inner = cond
    if cond.type == "condition_clause":
        inner = cond.child_by_field_name("value") or next((c for c in cond.named_children if c.type != "comment"), None)
    elif cond.type == "parenthesized_expression":
        inner = next((c for c in cond.named_children if c.type != "comment"), None)
    return norm_ws(_txt(src, inner))


def _stmts(node) -> list:
    if node is None:
        return []
    if node.type == "compound_statement":
        return [c for c in node.named_children if c.type != "comment"]
    return [node]


def _span(ln, nodes) -> set[int]:
    out: set[int] = set()
    for n in nodes:
        out.update(range(ln(n.start_point), ln(n.end_point) + 1))
    return out


def _if_branch(node, src: bytes, ln, nid: str, path: str) -> Branch | None:
    cond, cons = node.child_by_field_name("condition"), node.child_by_field_name("consequence")
    if cond is None or cons is None:
        return None
    body = _span(ln, _stmts(cons))
    own = (set(range(ln(node.start_point), ln(cond.end_point) + 1)) | {ln(cons.start_point), ln(cons.end_point)}) - body
    alt = None
    other = node.child_by_field_name("alternative")
    if other is not None:
        inner = next((c for c in other.named_children if c.type != "comment"), None)
        if inner is not None and inner.type != "if_statement":
            alt = (ln(other.start_point), ln(other.end_point))
    kind = "else if" if node.parent is not None and node.parent.type == "else_clause" else "if"
    return Branch(nid, path, ln(node.start_point), _cond_text(src, cond), ln(cons.start_point), ln(cons.end_point),
                  body, own, alt=alt, kind=kind)


def _case_branch(node, src: bytes, ln, nid: str, path: str) -> Branch | None:
    value = node.child_by_field_name("value")
    if value is None:                                      # default: no condition of its own
        return None
    sw = node.parent.parent if node.parent is not None else None
    subject = _cond_text(src, sw.child_by_field_name("condition")) if sw is not None and sw.type == "switch_statement" else ""
    v = norm_ws(_txt(src, value))
    body = _span(ln, [c for c in node.named_children if c.id != value.id and c.type != "comment"])
    line = ln(node.start_point)
    return Branch(nid, path, line, f"{subject} == {v}" if subject else v, line, ln(node.end_point), body, {line} - body,
                  kind="case")


def _loop_text(node, src: bytes) -> str:
    """A loop's header as written: `for (i = 0; i < len; i++)`, `while (n)`, `do … while (n)`."""
    if node.type == "do_statement":
        return f"do … while {norm_ws(_txt(src, node.child_by_field_name('condition')))}"
    body = node.child_by_field_name("body")
    return norm_ws(src[node.start_byte:body.start_byte if body is not None else node.end_byte].decode("utf-8", "replace"))


class Sources:
    """Each file's text, parse and changed lines, read once and shared by the conditions and the walk-throughs (R34). A
    changed file's text is the change set's; any other file's is read with `read_text`, the same on both sides."""

    def __init__(self, x, read_text: Callable[[str], str | None] | None = None):
        self.x = x
        self.read_text = read_text
        self._text: dict[tuple[str, str], str] = {}
        self._rows: dict[str, list[str]] = {}
        self._marks: dict[str, dict[int, str]] = {}
        self._trees: dict[tuple[str, str], tuple] = {}
        self._index: dict[str, dict[str, dict[int, list]]] = {}
        self._shapes: dict[tuple[str, str], FnShape | None] = {}

    def text(self, path: str, side: str = "after") -> str:
        key = (path, side)
        if key not in self._text:
            fc = self.x.texts.get(path)
            if fc is not None:
                self._text[key] = fc.after if side == "after" else fc.before
            else:
                self._text[key] = (self.read_text(path) if self.read_text else None) or ""
        return self._text[key]

    def rows(self, path: str) -> list[str]:
        if path not in self._rows:
            self._rows[path] = linediff.lines(self.text(path))
        return self._rows[path]

    def line(self, path: str, n: int) -> str:
        rows = self.rows(path)
        return rows[n - 1] if 0 < n <= len(rows) else ""

    def marks(self, path: str) -> dict[int, str]:
        """The file's new and changed lines; none for a file the change leaves alone."""
        if path not in self._marks:
            fc = self.x.texts.get(path)
            self._marks[path] = line_marks(fc.before, fc.after) if fc is not None else {}
        return self._marks[path]

    def tree(self, path: str, side: str = "after") -> tuple:
        """(tree, source bytes, row starts). A parse an `#if` tangles is redone on `flatten_preproc`'s text, which keeps
        every kept line's number and bytes."""
        key = (path, side)
        if key not in self._trees:
            text = self.text(path, side)
            parser = _parser_for(path)
            src = text.encode("utf-8", errors="replace")
            tree = parser.parse(src)
            if tree.root_node.has_error and any(_COND.match(t) for t in text.split("\n")):
                src = flatten_preproc(text).encode("utf-8", errors="replace")
                tree = parser.parse(src)
            self._trees[key] = (tree, src, _line_starts(text))
        return self._trees[key]

    def nodes_at(self, path: str, line: int, kind: str) -> list:
        """The after side's calls or field accesses that start on a line."""
        if path not in self._index:
            tree, _, starts = self.tree(path)
            idx: dict[str, dict[int, list]] = {k: {} for k in _INDEXED}
            stack = [tree.root_node]
            while stack:
                n = stack.pop()
                if n.type in idx:
                    idx[n.type].setdefault(_at(starts, n.start_point[0] + 1), []).append(n)
                stack.extend(n.children)
            for by in idx.values():
                for ns in by.values():
                    ns.sort(key=lambda n: n.start_byte)
            self._index[path] = idx
        return self._index[path].get(kind, {}).get(line, [])

    def shape(self, nid: str, side: str = "after") -> FnShape | None:
        key = (nid, side)
        if key not in self._shapes:
            self._shapes[key] = self._shape(nid, side)
        return self._shapes[key]

    def _shape(self, nid: str, side: str) -> FnShape | None:
        n = self.x.im.nodes[nid]
        fn = (self.x.fa if side == "after" else self.x.fb).get(n.key)
        if fn is None:
            return None
        tree, src, starts = self.tree(fn.file, side)

        def ln(p) -> int:
            return _at(starts, p[0] + 1)
        out = FnShape(nid, fn.file, fn.start_line, fn.end_line, [], [], [])
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if ln(node.end_point) < fn.start_line or ln(node.start_point) > fn.end_line:
                continue
            t = node.type
            b = None
            if t == "if_statement":
                b = _if_branch(node, src, ln, nid, fn.file)
            elif t == "case_statement":
                b = _case_branch(node, src, ln, nid, fn.file)
            elif t in _LOOPS:
                out.loops.append(Loop(_loop_text(node, src), ln(node.start_point), ln(node.end_point)))
            elif t == "return_statement":
                val = next((c for c in node.named_children if c.type != "comment"), None)
                out.returns.append((ln(node.start_point), norm_ws(_txt(src, val))))
            if b is not None:
                out.branches.append(b)
            stack.extend(node.children)
        out.branches.sort(key=lambda b: (b.line, b.first))
        out.loops.sort(key=lambda lp: (lp.first, -lp.last))
        out.returns.sort()
        for b in out.branches:
            b.returns = [r for r, _ in out.returns if r in b.body]
        return out


def node_stories(ss) -> dict[str, str]:
    """Each changed node's story: the first that holds it."""
    out: dict[str, str] = {}
    for s in ss.stories:
        for n in s.nodes:
            out.setdefault(n, s.id)
    return out


def line_cl(x, path: str, n: int, lines=None) -> int | None:
    """The CL that wrote line n of a changed file's final text (R25): sequence.py's per-line record for a file several
    CLs edit, else the file's one CL."""
    fc = x.texts.get(path)
    if fc is None:
        return None
    fl = (lines or {}).get(fc.depot)
    if fl is not None and 0 < n <= len(fl.wrote):
        return fl.wrote[n - 1]
    if len(fc.per_cl) == 1:
        return fc.per_cl[0].cl
    if not fc.per_cl and x.c.cs.cls:
        return x.c.cs.cls[0].cl
    return None


def find_gates(x, src: Sources, story_of: dict[str, str], order: list[str]) -> list[Branch]:
    """The conditions the change adds (§7, R20–R23): a new if, else if or case; a changed test; a new return under an
    existing one. Only functions that existed before, outside tests. Strongest first: the most new or changed lines it
    guards, then the earliest story, file and line."""
    pos = {s: i for i, s in enumerate(order)}
    out: list[Branch] = []
    for nid in sorted(x.changed, key=lambda n: (len(n), n)):
        n = x.im.nodes[nid]
        if n.kind != "function" or n.key not in x.fa or n.key not in x.fb or x.is_test_path(nid):
            continue
        after = src.shape(nid)
        if after is None:
            continue
        before = src.shape(nid, "before")
        had = {b.test for b in before.branches} if before is not None else set()
        marks = src.marks(after.path)
        for b in after.branches:
            strength = sum(1 for k in b.body if k in marks and not trivial(src.line(after.path, k)))
            if b.line in marks and b.test not in had:
                kind = "changed" if marks[b.line] == "changed" else b.kind
            elif any(r in marks for r in b.returns):
                kind = "return"
            else:
                continue
            out.append(replace(b, kind=kind, strength=strength))
    out.sort(key=lambda b: (-b.strength, pos.get(story_of.get(b.node, ""), len(pos)), b.path, b.line))
    return out


def _only_guarded(x, g: Branch) -> set[str]:
    """Functions reached only through the guarded block: every call to them sits in its body, or in a function already
    reached only through it."""
    usr = x.im.nodes[g.node].key
    sites: dict[str, list] = {}
    for e in x.calls_after:
        sites.setdefault(e.callee, []).append(e)
    inside: set[str] = set()
    grew = True
    while grew:
        grew = False
        for callee, es in sites.items():
            if callee in inside or callee == usr:
                continue
            if all((e.caller == usr and e.line in g.body) or e.caller in inside for e in es):
                inside.add(callee)
                grew = True
    return {x.id_of[k] for k in inside if k in x.id_of}


def _holder(spans: list[tuple[int, int, str]], n: int) -> str | None:
    """The innermost function holding line n."""
    best = None
    for a, b, nid in spans:
        if a <= n <= b and (best is None or b - a < best[1] - best[0]):
            best = (a, b, nid)
    return best[2] if best else None


def classify(g: Branch, x, src: Sources, story_of: dict[str, str], path_story: dict[str, str], order: list[str],
             lines=None) -> tuple[list[GatedLine], int, int]:
    """Every new or changed line of the review against the strongest condition (§7, R24): under it (it doesn't run when
    the condition is false), outside it (it still runs), or elsewhere (another function: it runs unless that function is
    reached only through the guarded block). The test's own lines and lines that say nothing alone are left out."""
    pos = {s: i for i, s in enumerate(order)}
    guarded = _only_guarded(x, g)
    spans: dict[str, list[tuple[int, int, str]]] = {}
    for key, fn in x.fa.items():
        if key in x.id_of:
            spans.setdefault(fn.file, []).append((fn.start_line, fn.end_line, x.id_of[key]))
    rows: list[tuple] = []
    for fc in x.c.cs.files:
        path = fc.local
        for n in sorted(src.marks(path)):
            text = src.line(path, n)
            if trivial(text):
                continue
            nid = _holder(spans.get(path, []), n)
            if nid == g.node:
                if n in g.own:
                    continue
                where, runs = ("under", False) if n in g.body else ("outside", True)
            else:
                where, runs = "elsewhere", nid not in guarded
            story = story_of.get(nid) if nid else path_story.get(rel_path(x, path))
            rows.append((where, story, path, n, text, runs, nid))
    rank = {"under": 0, "outside": 1, "elsewhere": 2}
    rows.sort(key=lambda r: (rank[r[0]], pos.get(r[1], len(pos)), r[2], r[3]))
    out = [GatedLine(story=s, cl=line_cl(x, p, n, lines), text=norm_ws(t), runs=run, where=w, path=rel_path(x, p), line=n,
                     function=x.label(nid) if nid else None)
           for w, s, p, n, t, run, nid in rows[:MAX_LINES]]
    return out, sum(1 for r in rows if r[5]), sum(1 for r in rows if not r[5])


def build_gates(x, ss, r, per, src: Sources, lines=None) -> tuple[list[Gate], list[Branch]]:
    """The review's conditions, strongest first, at most MAX_GATES; only the first lists its lines (R14)."""
    story_of = node_stories(ss)
    path_story: dict[str, str] = {}
    for sid in r.order:
        sr = per.get(sid)
        for w in sr.where if sr is not None else []:
            path_story.setdefault(w.path, sid)
    branches = find_gates(x, src, story_of, r.order)[:MAX_GATES]
    gates: list[Gate] = []
    for i, b in enumerate(branches, 1):
        b.id = f"G{i}"
        g = Gate(id=b.id, node=b.node, test=b.test, story=story_of.get(b.node), path=rel_path(x, b.path), line=b.line,
                 guarded=[b.first, b.last])
        if i == 1:
            g.lines, g.runs, g.stops = classify(b, x, src, story_of, path_story, r.order, lines)
        gates.append(g)
    return gates, branches
