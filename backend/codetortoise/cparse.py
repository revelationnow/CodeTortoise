"""Tree-sitter based C/C++ structural parsing (fast, flag-free, heuristic)."""
from __future__ import annotations

import bisect
import hashlib
import itertools
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import PurePath
from typing import Literal

import tree_sitter as ts
import tree_sitter_c
import tree_sitter_cpp

C_EXTS = {".c"}
CPP_EXTS = {".cc", ".cpp", ".cxx", ".c++"}
HEADER_EXTS = {".h", ".hh", ".hpp", ".hxx", ".inl"}
SOURCE_EXTS = C_EXTS | CPP_EXTS | HEADER_EXTS

_LANG_C = ts.Language(tree_sitter_c.language())
_LANG_CPP = ts.Language(tree_sitter_cpp.language())


def is_source(path: str) -> bool:
    return PurePath(path).suffix.lower() in SOURCE_EXTS


def is_header(path: str) -> bool:
    return PurePath(path).suffix.lower() in HEADER_EXTS


def _parser_for(path: str) -> ts.Parser:
    lang = _LANG_C if PurePath(path).suffix.lower() in C_EXTS else _LANG_CPP
    return ts.Parser(lang)


def norm_ws(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class FuncDef:
    qualname: str
    name: str
    start_line: int
    end_line: int
    signature: str
    text_hash: str


@dataclass(frozen=True)
class TypeDef:
    name: str
    kind: str
    start_line: int
    end_line: int
    text: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class MacroDef:
    name: str
    line: int
    text: str


@dataclass(frozen=True)
class CallSite:
    caller: str | None
    callee: str
    line: int


@dataclass(frozen=True)
class MemberRef:
    fn: str | None
    field: str
    line: int
    is_write: bool


@dataclass(frozen=True)
class FuncDecl:
    qualname: str
    line: int
    text: str


@dataclass
class ParsedFile:
    functions: list[FuncDef] = field(default_factory=list)
    decls: list[FuncDecl] = field(default_factory=list)
    types: list[TypeDef] = field(default_factory=list)
    macros: list[MacroDef] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    members: list[MemberRef] = field(default_factory=list)
    flattened: bool = False     # functions found on flatten_preproc's text (parse_source)


def _txt(src: bytes, node: ts.Node | None) -> str:
    if node is None:
        return ""
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_function_declarator(node: ts.Node | None) -> ts.Node | None:
    while node is not None:
        if node.type == "function_declarator":
            return node
        node = node.child_by_field_name("declarator")
    return None


def _declared(node: ts.Node | None) -> ts.Node | None:
    """The identifier a declarator names, through pointers, references, arrays, functions and parentheses."""
    while node is not None and node.type not in ("field_identifier", "identifier"):
        inner = node.child_by_field_name("declarator")
        if inner is None and node.type in ("parenthesized_declarator", "reference_declarator"):
            inner = next(iter(node.named_children), None)
        node = inner
    return node


_CONDITIONAL = ("preproc_if", "preproc_ifdef", "preproc_elif", "preproc_elifdef", "preproc_else")


def _members(src: bytes, body: ts.Node) -> tuple[str, ...]:
    """The names a type's body declares, once each and in order: an enum's enumerators, or a struct's, union's or class's
    fields (not methods). A member under `#if` counts in every branch, and the fields of a nameless struct or union member
    are the outer type's own."""
    out: list[str] = []
    todo = [iter(body.children)]            # a stack of iterators, so a deep nest cannot overflow the call stack
    while todo:
        for ch in todo[-1]:
            below = None
            if ch.type in _CONDITIONAL:
                below = ch
            elif ch.type == "enumerator":
                out.append(_txt(src, ch.child_by_field_name("name")))
            elif ch.type == "field_declaration":
                declarators = ch.children_by_field_name("declarator")
                for d in declarators:
                    n = _declared(d)
                    if n is not None and n.parent.type != "function_declarator":    # else a method's declaration
                        out.append(_txt(src, n))
                inner = ch.child_by_field_name("type")
                if not declarators and inner is not None and inner.type in ("struct_specifier", "union_specifier") \
                        and inner.child_by_field_name("name") is None:
                    below = inner.child_by_field_name("body")
            if below is not None:
                todo.append(iter(below.children))
                break
        else:
            todo.pop()
    return tuple(dict.fromkeys(name for name in out if name))      # an unnamed bit-field's identifier is missing


def _callee_name(src: bytes, fn_node: ts.Node | None) -> str | None:
    if fn_node is None:
        return None
    t = fn_node.type
    if t == "identifier":
        return _txt(src, fn_node)
    if t == "field_expression":
        return _txt(src, fn_node.child_by_field_name("field")) or None
    if t == "qualified_identifier":
        return _txt(src, fn_node).replace(" ", "").split("::")[-1] or None
    if t == "template_function":
        return _callee_name(src, fn_node.child_by_field_name("name"))
    return None


def _is_write_target(node: ts.Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "assignment_expression":
        left = parent.child_by_field_name("left")
        return left is not None and left.id == node.id
    if parent.type == "update_expression":
        return True
    return False


_STATEMENTS = frozenset({"if", "else", "for", "while", "do", "switch", "case", "return", "sizeof", "goto"})
_LEADING = re.compile(r"\w+")


def _statement_like(name: str) -> bool:
    """Whether a parsed "function" is a statement taken for a definition: its name starts with a statement keyword
    (tree-sitter names a declarator by its whole text, so `else if ((v == 1)` is named `if((v==1)`). Parentheses in a name
    say nothing: a function named by a macro, `NAME(alpha)`, a C++ `result_type(min)` or `operator()`, and one returning a
    function pointer, `(*name(...))`, are definitions."""
    lead = _LEADING.match(name)
    return lead is not None and lead.group() in _STATEMENTS


def parse_source(path: str, text: str, flatten: Literal["never", "auto", "always"] = "never") -> ParsedFile:
    """Functions, declarations, types, macros, calls, includes and member references of one file.

    `flatten`: "auto" finds the functions (with their calls and member references) again on flatten_preproc's text
    when a preprocessor conditional tangles the parse (a "function" named like a statement, or an error on or across a
    conditional's line), and "always" does so regardless. Line numbers stay; a function's hash still comes from the
    original text, so an edit inside a dropped branch still changes it; a function the first parse found that no
    function of the flattened text covers (one in a branch not kept) stays; "functions" named like statements go.

    Lines are numbered as clang and `linediff.lines` number them: a line ends at a newline, a carriage return plus
    newline or a lone carriage return. tree-sitter's rows break at a newline only, so in a text with a lone carriage
    return every line number is turned from its row's into the line that row starts on."""
    out = _parse(path, text, flatten)
    starts = _line_starts(text)
    return out if starts is None else _renumbered(out, starts)


def _parse(path: str, text: str, flatten: Literal["never", "auto", "always"]) -> ParsedFile:
    """The parse `parse_source` describes, its line numbers still tree-sitter's rows (the merge below works in rows: the
    flattened text keeps every kept line's row)."""
    parser = _parser_for(path)
    src = text.encode("utf-8", errors="replace")
    tree = parser.parse(src)
    out = _collect(tree, src)
    if flatten == "never" or (flatten == "auto" and not _tangled(tree, text, out)):
        return out
    flat_src = flatten_preproc(text).encode("utf-8", errors="replace")
    flat = _collect(parser.parse(flat_src), flat_src, src.split(b"\n"))
    fns = sorted((f for f in flat.functions if not _statement_like(f.name)), key=lambda f: (f.start_line, f.end_line))
    starts = [f.start_line for f in fns]
    reach = list(itertools.accumulate((f.end_line for f in fns), max))

    def covered(f: FuncDef) -> bool:
        k = bisect.bisect_right(starts, f.end_line) - 1      # the flattened functions starting before f ends,
        return k >= 0 and reach[k] >= f.start_line            # and whether one of them reaches f
    lost: dict[str, list[FuncDef]] = defaultdict(list)
    for f in out.functions:
        if not _statement_like(f.name) and not covered(f):
            lost[f.qualname].append(f)

    def kept(fn: str | None, line: int) -> bool:
        return any(f.start_line <= line <= f.end_line for f in lost.get(fn or "", ()))
    out.functions = sorted(fns + [f for fs in lost.values() for f in fs], key=lambda f: (f.start_line, f.end_line))
    out.calls = flat.calls + [c for c in out.calls if kept(c.caller, c.line)]
    out.members = flat.members + [m for m in out.members if kept(m.fn, m.line)]
    out.flattened = True
    return out


def _orig_text(lines: list[bytes], node: ts.Node) -> str:
    """A node's text in the original file, by its start and end points: a flattened text keeps every kept line's number
    and bytes, so the points match."""
    (r0, c0), (r1, c1) = node.start_point, node.end_point
    part = lines[r0][c0:c1] if r0 == r1 else b"\n".join([lines[r0][c0:], *lines[r0 + 1:r1], lines[r1][:c1]])
    return part.decode("utf-8", errors="replace")


def _collect(tree: ts.Tree, src: bytes, orig: list[bytes] | None = None) -> ParsedFile:
    """One walk of a parse. `orig`: the original file's lines, when `src` is a flattened text (function hashes and type
    texts come from it)."""
    def whole(node: ts.Node) -> str:
        return _orig_text(orig, node) if orig is not None else _txt(src, node)
    out = ParsedFile()
    stack: list[tuple[ts.Node, tuple[str, ...], str | None]] = [(tree.root_node, (), None)]
    while stack:
        node, scope, fn = stack.pop()
        t = node.type
        child_scope, child_fn = scope, fn
        if t == "namespace_definition":
            name = node.child_by_field_name("name")
            if name is not None:
                child_scope = scope + (_txt(src, name).replace(" ", ""),)
        elif t in ("class_specifier", "struct_specifier", "union_specifier", "enum_specifier"):
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if body is not None:
                nm = _txt(src, name_node).replace(" ", "")
                qual = "::".join(scope + (nm,)) if nm else ""
                out.types.append(TypeDef(qual, t.split("_")[0], node.start_point.row + 1,
                                         node.end_point.row + 1, norm_ws(whole(node)), _members(src, body)))
                if nm and t != "enum_specifier":
                    child_scope = scope + (nm,)
        elif t == "function_definition":
            fd = _find_function_declarator(node.child_by_field_name("declarator"))
            if fd is not None:
                raw = _txt(src, fd.child_by_field_name("declarator")).replace(" ", "")
                qual = "::".join(scope + (raw,)) if scope else raw
                body = node.child_by_field_name("body")
                sig_end = body.start_byte if body is not None else node.end_byte
                sig = norm_ws(src[node.start_byte:sig_end].decode("utf-8", errors="replace"))
                full = norm_ws(whole(node))
                out.functions.append(FuncDef(qual, raw.split("::")[-1], node.start_point.row + 1,
                                             node.end_point.row + 1, sig,
                                             hashlib.sha1(full.encode()).hexdigest()))
                child_fn = qual
        elif t in ("declaration", "field_declaration") and fn is None:
            fd = _find_function_declarator(node.child_by_field_name("declarator"))
            if fd is not None:
                raw = _txt(src, fd.child_by_field_name("declarator")).replace(" ", "")
                qual = "::".join(scope + (raw,)) if scope else raw
                out.decls.append(FuncDecl(qual, node.start_point.row + 1, norm_ws(_txt(src, node))))
        elif t in ("preproc_def", "preproc_function_def"):
            name = _txt(src, node.child_by_field_name("name"))
            if name:
                out.macros.append(MacroDef(name, node.start_point.row + 1, norm_ws(_txt(src, node))))
        elif t == "preproc_include":
            p = _txt(src, node.child_by_field_name("path")).strip()
            if len(p) >= 2 and p[0] in "\"<":
                out.includes.append(p[1:-1])
        elif t == "call_expression":
            callee = _callee_name(src, node.child_by_field_name("function"))
            if callee:
                out.calls.append(CallSite(fn, callee, node.start_point.row + 1))
        elif t == "field_expression":
            fld = node.child_by_field_name("field")
            if fld is not None and (node.parent is None or node.parent.type != "call_expression"
                                    or node.parent.child_by_field_name("function").id != node.id):
                out.members.append(MemberRef(fn, _txt(src, fld), node.start_point.row + 1,
                                             _is_write_target(node)))
        for ch in reversed(node.children):
            stack.append((ch, child_scope, child_fn))
    return out


_LONE_CR = re.compile(r"\r(?!\n)")


def _line_starts(text: str) -> list[int] | None:
    """For each tree-sitter row of the text (rows break at a newline only), the line it starts on when a lone carriage
    return ends a line too, as clang counts them; None when the text has none, so the two numberings agree."""
    if "\r" not in text or _LONE_CR.search(text) is None:
        return None
    starts = [1]
    for row in text.split("\n")[:-1]:       # a row's last "\r" before its newline is half of a "\r\n", not a line end
        starts.append(starts[-1] + 1 + row.count("\r") - row.endswith("\r"))
    return starts


def _at(starts: list[int] | None, line: int) -> int:
    """The line a tree-sitter line (a row, counted from 1) starts on, given `_line_starts`."""
    return line if starts is None else starts[min(line, len(starts)) - 1]


def _renumbered(pf: ParsedFile, starts: list[int]) -> ParsedFile:
    """`pf` with every line number turned from a row's into the line that row starts on."""
    pf.functions = [replace(f, start_line=_at(starts, f.start_line), end_line=_at(starts, f.end_line)) for f in pf.functions]
    pf.decls = [replace(d, line=_at(starts, d.line)) for d in pf.decls]
    pf.types = [replace(t, start_line=_at(starts, t.start_line), end_line=_at(starts, t.end_line)) for t in pf.types]
    pf.macros = [replace(m, line=_at(starts, m.line)) for m in pf.macros]
    pf.calls = [replace(c, line=_at(starts, c.line)) for c in pf.calls]
    pf.members = [replace(m, line=_at(starts, m.line)) for m in pf.members]
    return pf


_COND = re.compile(r"[ \t]*#[ \t]*(if|ifdef|ifndef|elif|elifdef|elifndef|else|endif)\b(.*)")
_DEFINE = re.compile(r"[ \t]*#[ \t]*(define|undef)[ \t]+(\w+)")
_DEFINED = re.compile(r"(!?)[ \t]*defined[ \t]*\(?[ \t]*(\w+)[ \t]*\)?")


def _tangled(tree: ts.Tree, text: str, pf: ParsedFile) -> bool:
    """Whether a preprocessor conditional tangles a parse: a "function" named like a statement, or a parse error or
    missing token on a conditional directive's line or spanning one."""
    if any(_statement_like(f.name) for f in pf.functions):
        return True
    rows = [i for i, line in enumerate(text.split("\n")) if _COND.match(line)]
    if not rows or not tree.root_node.has_error:
        return False
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "ERROR" or n.is_missing:
            k = bisect.bisect_left(rows, n.start_point.row)
            if k < len(rows) and rows[k] <= n.end_point.row:
                return True
        stack.extend(ch for ch in n.children if ch.has_error or ch.is_missing)
    return False


def _cond(expr: str, assumed: dict[str, bool]) -> bool:
    """One reading of an `#if`/`#elif` condition: literally 0 is false; `defined(X)` and `!defined(X)` read X the way
    an earlier test or `#define` settled it, and settle it when nothing has; anything else is true."""
    expr = expr.split("//")[0].split("/*")[0].strip()
    if expr == "0":
        return False
    m = _DEFINED.fullmatch(expr)
    if m is None:
        return True
    neg = m.group(1) == "!"
    return assumed.setdefault(m.group(2), not neg) != neg


def flatten_preproc(text: str) -> str:
    """The text as one consistent preprocessor reading leaves it, to find function boundaries in: each conditional
    keeps one branch (the first whose condition is not literally 0, a macro tested again, or `#define`d or `#undef`d on
    the way, reading the same way) and its other branches and its directives, continuation lines too, become empty
    lines. Other directives stay. The line count is unchanged, so every kept line keeps its number and its bytes."""
    assumed: dict[str, bool] = {}
    stack: list[list[bool]] = []          # per open conditional: [this branch kept, some branch kept]
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        active = all(f[0] for f in stack)
        m = _COND.match(lines[i])
        if m is None:
            d = _DEFINE.match(lines[i]) if active else None
            if d:
                assumed[d.group(2)] = d.group(1) == "define"
            out.append(lines[i] if active else "")
            i += 1
            continue
        kw, rest, n = m.group(1), m.group(2), 1
        while lines[i + n - 1].rstrip("\r").endswith("\\") and i + n < len(lines):
            rest += " " + lines[i + n]
            n += 1
        rest = rest.replace("\\", " ")
        name = rest.split()[0] if rest.split() else ""
        if kw in ("elifdef", "elifndef"):
            kw, rest = "elif", f"{'!' if kw == 'elifndef' else ''}defined({name})"
        if kw in ("if", "ifdef", "ifndef"):
            if not active:
                keep = False
            elif kw == "if":
                keep = _cond(rest, assumed)
            else:
                keep = assumed.setdefault(name, kw == "ifdef") == (kw == "ifdef")
            stack.append([keep, keep])
        elif kw in ("elif", "else") and stack:
            top = stack[-1]
            top[0] = all(f[0] for f in stack[:-1]) and not top[1] and (kw == "else" or _cond(rest, assumed))
            top[1] = top[1] or top[0]
        elif kw == "endif" and stack:
            stack.pop()
        out += [""] * n
        i += n
    return "\n".join(out)


_GUARD = re.compile(r"(_H|_HH|_HPP|_HXX|_INCLUDED)_*$")


def _negate(cond: str) -> str:
    if cond.startswith("!defined(") and cond.endswith(")"):
        return cond[1:]
    if cond.startswith("defined(") and cond.endswith(")") and cond.count("(") == 1:
        return "!" + cond
    return f"!({cond})"


def preproc_spans(path: str, text: str) -> list[tuple[int, int, str]]:
    """(first line, last line, condition) for each branch of each `#if`/`#ifdef`/`#ifndef` (`#elif` and `#else`
    included), in source order; include guards are left out. `#ifdef X` is `defined(X)`, `#ifndef X` is
    `!defined(X)` and an `#else` negates the branch before it. Lines are numbered as `parse_source` numbers them."""
    src = text.encode("utf-8", errors="replace")
    tree = _parser_for(path).parse(src)
    starts = _line_starts(text)
    out: list[tuple[int, int, str]] = []

    def branch(node: ts.Node, cond: str) -> None:
        alt = node.child_by_field_name("alternative")
        end = _at(starts, alt.start_point.row + 1) - 1 if alt is not None else _at(starts, node.end_point.row + 1)
        out.append((_at(starts, node.start_point.row + 1), end, cond))
        if alt is not None:
            if alt.type == "preproc_elif":
                c = alt.child_by_field_name("condition")
                branch(alt, norm_ws(_txt(src, c)) if c is not None else "")
            else:
                out.append((_at(starts, alt.start_point.row + 1), _at(starts, alt.end_point.row + 1), _negate(cond)))

    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "preproc_ifdef":
            neg = any(ch.type == "#ifndef" for ch in node.children)
            name = _txt(src, node.child_by_field_name("name"))
            if not (neg and _GUARD.search(name)):
                branch(node, f"{'!' if neg else ''}defined({name})")
        elif node.type == "preproc_if":
            c = node.child_by_field_name("condition")
            branch(node, norm_ws(_txt(src, c)) if c is not None else "")
        stack.extend(reversed(node.children))
    return sorted(out)
