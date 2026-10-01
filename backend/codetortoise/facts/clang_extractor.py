"""libclang-based FactExtractor. Designed to run inside worker processes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import clang.cindex as ci

from codetortoise.facts.aliasflow import (
    FunctionAnalyzer,
    _strip,
    constant_name,
    literal_text,
    operator_of,
)
from codetortoise.facts.model import CallEdge, Facts, Function, Param, TuInfo
from codetortoise.paths import canon

K = ci.CursorKind
_FUNC_KINDS = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.FUNCTION_TEMPLATE}
_SCOPE_KINDS = {K.NAMESPACE, K.CLASS_DECL, K.STRUCT_DECL, K.UNION_DECL, K.CLASS_TEMPLATE}
_BAD_FLAG = re.compile(r"(?:unknown argument:?|unsupported option) '([^']+)'")
# flags kept when a TU cannot be created at all with the full argument list
_SAFE_WITH_VALUE = {"-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros", "-D", "-U", "-x",
                    "--sysroot", "-isysroot", "-resource-dir"}
_SAFE_PREFIXES = ("-I", "-isystem", "-iquote", "-idirafter", "-D", "-U", "-std=", "-x", "--sysroot=", "-f", "-W",
                  "-nostdinc", "-include", "-imacros")
_CMP_OPS = {"==", "!=", "<", ">", "<=", ">="}


@dataclass
class TuRequest:
    file: str
    args: list[str]
    variant: str
    unsaved: dict[str, str] = field(default_factory=dict)
    focus: list[str] = field(default_factory=list)


def _norm(path: str) -> str:
    return canon(path)


def qualname_of(c: ci.Cursor) -> str:
    parts = [c.spelling]
    p = c.semantic_parent
    while p is not None and p.kind in _SCOPE_KINDS:
        if p.spelling:
            parts.append(p.spelling)
        p = p.semantic_parent
    return "::".join(reversed(parts))


def _param(p: ci.Cursor) -> Param:
    t = p.type.get_canonical()
    if t.kind in (ci.TypeKind.POINTER, ci.TypeKind.LVALUEREFERENCE, ci.TypeKind.RVALUEREFERENCE):
        is_const = t.get_pointee().is_const_qualified()
    else:
        is_const = t.is_const_qualified()
    return Param(name=p.spelling, type=p.type.spelling, is_const=is_const)


def function_fact(c: ci.Cursor) -> Function:
    params = [_param(p) for p in (c.get_arguments() or [])]
    qual = qualname_of(c)
    rt = c.result_type.spelling if c.kind not in (K.CONSTRUCTOR, K.DESTRUCTOR) else ""
    sig = f"{rt} {qual}({', '.join(p.type for p in params)})".strip()
    if c.kind == K.CXX_METHOD and c.is_const_method():
        sig += " const"
    is_virtual = c.kind == K.CXX_METHOD and c.is_virtual_method()
    usr = c.get_usr()
    returns: list[str] = []
    names: dict[str, str] = {}
    lines: dict[str, int] = {}
    for r in c.walk_preorder():
        if r.kind == K.RETURN_STMT:
            kids = list(r.get_children())
            if kids:
                lit = literal_text(kids[0])
                if lit is not None and lit not in returns:
                    returns.append(lit)
                    lines[lit] = r.location.line
                if lit is not None and lit not in names and (name := constant_name(kids[0])):
                    names[lit] = name
    return Function(
        usr=usr, qualname=qual, name=c.spelling, signature=sig, return_type=rt, params=params,
        file=_norm(c.location.file.name), start_line=c.extent.start.line, end_line=c.extent.end.line,
        is_virtual=is_virtual, method_key=usr.split("@F@", 1)[-1] if is_virtual else None,
        is_static=c.storage_class == ci.StorageClass.STATIC, returns=returns, return_names=names, return_lines=lines)


_WRAP = {K.UNEXPOSED_EXPR, K.PAREN_EXPR}
_STMT_PARENTS = {K.COMPOUND_STMT, K.CASE_STMT, K.DEFAULT_STMT, K.LABEL_STMT}


def _result_unused(parent: ci.Cursor | None, idx: int, n: int) -> bool:
    if parent is None:
        return False
    k = parent.kind
    if k in _STMT_PARENTS:
        return True
    if k == K.IF_STMT:
        return idx >= 1
    if k in (K.FOR_STMT, K.WHILE_STMT):
        return idx == n - 1
    if k == K.DO_STMT:
        return idx == 0
    if k == K.CSTYLE_CAST_EXPR:
        return parent.type.spelling == "void"
    return False


def _calls(fn: ci.Cursor, fn_usr: str) -> list[CallEdge]:
    out: list[CallEdge] = []

    def visit(c: ci.Cursor, parent: ci.Cursor | None, idx: int, n: int) -> None:
        if (c.kind == K.CALL_EXPR and c.referenced is not None and c.referenced.kind in _FUNC_KINDS
                and c.referenced.kind != K.CONSTRUCTOR):
            callee = c.referenced
            kids = list(c.get_children())
            via_member = bool(kids) and _strip(kids[0])[0].kind == K.MEMBER_REF_EXPR
            is_virtual = callee.kind == K.CXX_METHOD and callee.is_virtual_method() and via_member
            compared: list[str] = []
            compared_names: dict[str, str] = {}
            if parent is not None and parent.kind == K.BINARY_OPERATOR:
                op = operator_of(parent)
                if op in _CMP_OPS:
                    for other in parent.get_children():
                        lit = literal_text(other)
                        if lit is not None:
                            compared.append(f"{op}{lit}")
                            if name := constant_name(other):
                                compared_names[f"{op}{lit}"] = name
            out.append(CallEdge(
                caller=fn_usr, callee=callee.get_usr(), callee_name=qualname_of(callee),
                file=_norm(c.location.file.name) if c.location.file else "", line=c.location.line,
                kind="virtual" if is_virtual else "direct",
                result_used=not _result_unused(parent, idx, n), compared=compared, compared_names=compared_names))
        kids = list(c.get_children())
        for i, ch in enumerate(kids):
            if c.kind in _WRAP:
                visit(ch, parent, idx, n)
            else:
                visit(ch, c, i, len(kids))

    visit(fn, None, 0, 1)
    return out


def _parse(index: ci.Index, req: TuRequest, args: list[str]) -> ci.TranslationUnit:
    unsaved = [(p, t) for p, t in req.unsaved.items()]
    return index.parse(req.file, args=args, unsaved_files=unsaved, options=ci.TranslationUnit.PARSE_INCOMPLETE)


def _matches_bad(arg: str, bad: str) -> bool:
    # "unknown argument: '-mfoo'" names the whole flag; "unsupported option '-mcpu='" names only its key
    return arg == bad or (bad.endswith("=") and arg.startswith(bad)) or arg.split("=", 1)[0] == bad


def safe_subset(args: list[str]) -> list[str]:
    """Include paths, macros, language/standard and -f/-W flags only; drops target, -Xclang pairs, -m*."""
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "-Xclang":
            i += 2
            continue
        if a in _SAFE_WITH_VALUE and i + 1 < len(args):
            out += [a, args[i + 1]]
            i += 2
            continue
        if a.startswith(_SAFE_PREFIXES):
            out.append(a)
        i += 1
    return out


def _diag_text(d: ci.Diagnostic) -> str:
    loc = f"{d.location.file}:{d.location.line}: " if d.location.file else ""
    return loc + d.spelling


def extract_tu(req: TuRequest) -> Facts:
    """Parse one TU and emit facts for functions defined in the main file or any focus file.

    Flags libclang reports as unknown/unsupported are stripped and the parse retried; if no TU can be
    created at all, it is retried once with `safe_subset(args)` and marked degraded.
    """
    index = ci.Index.create()
    args = list(req.args)
    stripped: list[str] = []
    reduced = False
    try:
        tu = _parse(index, req, args)
    except ci.TranslationUnitLoadError:
        tu = None
    if tu is not None:
        bad = [m.group(1) for d in tu.diagnostics if (m := _BAD_FLAG.search(d.spelling))]
        if bad:
            stripped = [a for a in args if any(_matches_bad(a, b) for b in bad)]
            args = [a for a in args if a not in stripped]
            try:
                tu = _parse(index, req, args)
            except ci.TranslationUnitLoadError:
                tu = None
    if tu is None:
        safe = safe_subset(args)
        stripped += [a for a in args if a not in safe]
        reduced = True
        try:
            tu = _parse(index, req, safe)
        except ci.TranslationUnitLoadError as e:
            return Facts(tu=TuInfo(file=_norm(req.file), variant=req.variant, confidence="failed",
                                   diagnostics=[str(e)], stripped_flags=stripped))
    errors = [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    diags = [_diag_text(d) for d in errors[:20]]
    if reduced:
        diags.insert(0, "parsed with a reduced flag set (full argument list could not create a TU)")
    info = TuInfo(file=_norm(req.file), variant=req.variant, error_count=len(errors), diagnostics=diags,
                  confidence="precise" if not errors and not reduced else "degraded", stripped_flags=stripped)
    focus = {_norm(f) for f in req.focus} | {_norm(req.file)}
    facts = Facts(tu=info)
    seen: set[str] = set()
    for c in tu.cursor.walk_preorder():
        if c.kind not in _FUNC_KINDS or not c.is_definition() or c.location.file is None:
            continue
        if _norm(c.location.file.name) not in focus:
            continue
        usr = c.get_usr()
        if usr in seen:
            continue
        seen.add(usr)
        facts.functions.append(function_fact(c))
        facts.calls.extend(_calls(c, usr))
        fa, ga = FunctionAnalyzer(c, usr).analyze()
        facts.fields.extend(fa)
        facts.globals.extend(ga)
    return facts
