"""Tree-sitter based C/C++ structural parsing (fast, flag-free, heuristic)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import PurePath

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


def parse_source(path: str, text: str) -> ParsedFile:
    src = text.encode("utf-8", errors="replace")
    tree = _parser_for(path).parse(src)
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
                                         node.end_point.row + 1, norm_ws(_txt(src, node))))
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
                full = norm_ws(_txt(src, node))
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
    `!defined(X)` and an `#else` negates the branch before it."""
    src = text.encode("utf-8", errors="replace")
    tree = _parser_for(path).parse(src)
    out: list[tuple[int, int, str]] = []

    def branch(node: ts.Node, cond: str) -> None:
        alt = node.child_by_field_name("alternative")
        end = alt.start_point.row if alt is not None else node.end_point.row + 1
        out.append((node.start_point.row + 1, end, cond))
        if alt is not None:
            if alt.type == "preproc_elif":
                c = alt.child_by_field_name("condition")
                branch(alt, norm_ws(_txt(src, c)) if c is not None else "")
            else:
                out.append((alt.start_point.row + 1, alt.end_point.row + 1, _negate(cond)))

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
