"""Alias-aware field access analysis over a libclang function cursor.

Access paths are rooted at a parameter, `this`, a global, or a local. Local
pointer/reference variables are tracked as aliases of the object they point
to, so writes like `st->tx++` after `st = &u->stats` resolve to `u.stats.tx`.
Flow-insensitive within a function: aliases are collected to a fixpoint
first, then accesses are recorded.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass

import clang.cindex as ci

from codetortoise.facts.model import FieldAccess, GlobalAccess

K = ci.CursorKind
T = ci.TypeKind

_WRAPPERS = {K.UNEXPOSED_EXPR, K.PAREN_EXPR}
_CASTS = {K.CSTYLE_CAST_EXPR, K.CXX_STATIC_CAST_EXPR, K.CXX_REINTERPRET_CAST_EXPR,
          K.CXX_CONST_CAST_EXPR, K.CXX_FUNCTIONAL_CAST_EXPR}
_PTR = {T.POINTER}
_REF = {T.LVALUEREFERENCE, T.RVALUEREFERENCE}
_ARRAY = {T.CONSTANTARRAY, T.INCOMPLETEARRAY, T.VARIABLEARRAY, T.DEPENDENTSIZEDARRAY}
_MEMFUNCS = {"memcpy", "memset", "memmove", "strcpy", "strncpy", "strcat", "strncat", "bzero"}
DEREF = ("*", "*", "")
ELEM = ("[]", "[]", "")
_FUNC_KINDS = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.FUNCTION_TEMPLATE}


@dataclass(frozen=True)
class AP:
    """Access path: root plus field steps. steps: tuple of (field_usr, field_name, record) or ("[]","[]","")."""
    root_kind: str
    root: str
    steps: tuple[tuple[str, str, str], ...] = ()
    may: bool = False
    via: tuple[str, ...] = ()

    def plus(self, step: tuple[str, str, str], may: bool = False) -> AP:
        if step == ELEM and self.steps and self.steps[-1] == ELEM:
            return self.mark(may=may)
        return AP(self.root_kind, self.root, self.steps + (step,), self.may or may, self.via)

    def mark(self, may: bool = False, via: str | None = None) -> AP:
        return AP(self.root_kind, self.root, self.steps, self.may or may,
                  self.via + ((via,) if via and via not in self.via else ()))

    def display(self) -> str:
        out = self.root
        prev = ""
        for usr, name, _ in self.steps:
            if usr == "[]":
                out += "[]"
            elif usr == "*":
                out += "->"
            else:
                out += name if prev == "*" else "." + name
            prev = usr
        return out + ("*" if prev == "*" else "")

    def key(self) -> tuple:
        return (self.root_kind, self.root, self.steps)


def _strip(c: ci.Cursor) -> tuple[ci.Cursor, bool]:
    may = False
    while True:
        if c.kind in _WRAPPERS:
            kids = list(c.get_children())
            if len(kids) != 1:
                return c, may
            c = kids[0]
        elif c.kind in _CASTS:
            kids = [k for k in c.get_children() if k.kind.is_expression()]
            if not kids:
                return c, may
            c, may = kids[-1], True
        else:
            return c, may


def _type_kind(c: ci.Cursor) -> T:
    return c.type.get_canonical().kind


_UNARY_KINDS = {1: "post++", 2: "post--", 3: "pre++", 4: "pre--", 5: "pre&", 6: "pre*", 7: "pre+", 8: "pre-",
                9: "pre~", 10: "pre!"}
_capi: dict | None = None


def _c_api() -> dict:
    """libclang C entry points missing from the Python bindings (operator kinds, constant evaluation).

    Resolved lazily (after load_libclang) and per process; entries are None on older libclang builds.
    """
    global _capi
    if _capi is not None:
        return _capi
    lib = ci.conf.lib
    api: dict = {}

    def bind(name, argtypes, restype):
        fn = getattr(lib, name, None)
        if fn is not None:
            fn.argtypes, fn.restype = argtypes, restype
        return fn

    api["bin_kind"] = bind("clang_getCursorBinaryOperatorKind", [ci.Cursor], ctypes.c_int)
    api["un_kind"] = bind("clang_getCursorUnaryOperatorKind", [ci.Cursor], ctypes.c_int)
    spell = bind("clang_getBinaryOperatorKindSpelling", [ctypes.c_int], ci._CXString)
    if spell is not None:
        spell.errcheck = ci._CXString.from_result
    api["bin_spell"] = spell
    api["eval"] = bind("clang_Cursor_Evaluate", [ci.Cursor], ctypes.c_void_p)
    api["eval_kind"] = bind("clang_EvalResult_getKind", [ctypes.c_void_p], ctypes.c_int)
    api["eval_unsigned"] = bind("clang_EvalResult_isUnsignedInt", [ctypes.c_void_p], ctypes.c_uint)
    api["eval_ll"] = bind("clang_EvalResult_getAsLongLong", [ctypes.c_void_p], ctypes.c_longlong)
    api["eval_ull"] = bind("clang_EvalResult_getAsUnsigned", [ctypes.c_void_p], ctypes.c_ulonglong)
    api["eval_dispose"] = bind("clang_EvalResult_dispose", [ctypes.c_void_p], None)
    _capi = api
    return api


def _operator_from_tokens(c: ci.Cursor) -> str:
    kids = list(c.get_children())
    toks = list(c.get_tokens())
    if c.kind in (K.BINARY_OPERATOR, K.COMPOUND_ASSIGNMENT_OPERATOR) and kids:
        lend = kids[0].extent.end.offset
        for tok in toks:
            if tok.extent.start.offset >= lend:
                return tok.spelling
        return ""
    if c.kind == K.UNARY_OPERATOR and kids and toks:
        if toks[0].extent.start.offset < kids[0].extent.start.offset:
            return "pre" + toks[0].spelling
        return "post" + toks[-1].spelling
    return ""


def operator_of(c: ci.Cursor) -> str:
    """Operator spelling for BINARY/COMPOUND/UNARY operator cursors ("=", "+=", "pre*", "post++", ...).

    Uses libclang's operator-kind API (correct inside macro expansions); falls back to tokens on
    libclang builds that lack it.
    """
    api = _c_api()
    if c.kind in (K.BINARY_OPERATOR, K.COMPOUND_ASSIGNMENT_OPERATOR) and api["bin_kind"] and api["bin_spell"]:
        kind = api["bin_kind"](c)
        if kind > 0:
            return api["bin_spell"](kind)
    if c.kind == K.UNARY_OPERATOR and api["un_kind"]:
        kind = api["un_kind"](c)
        if kind in _UNARY_KINDS:
            return _UNARY_KINDS[kind]
    return _operator_from_tokens(c)


def _evaluate_int(c: ci.Cursor) -> str | None:
    api = _c_api()
    if not (api["eval"] and api["eval_kind"] and api["eval_ll"] and api["eval_dispose"]):
        return None
    res = api["eval"](c)
    if not res:
        return None
    try:
        if api["eval_kind"](res) != 1:  # CXEval_Int
            return None
        if api["eval_unsigned"] and api["eval_ull"] and api["eval_unsigned"](res):
            return str(api["eval_ull"](res))
        return str(api["eval_ll"](res))
    finally:
        api["eval_dispose"](res)


_LITERAL_KINDS = {K.INTEGER_LITERAL, K.CHARACTER_LITERAL, K.CXX_BOOL_LITERAL_EXPR, K.UNARY_OPERATOR,
                  K.DECL_REF_EXPR, K.PAREN_EXPR, K.CSTYLE_CAST_EXPR}


def literal_text(c: ci.Cursor) -> str | None:
    """Value of an integer constant expression (literal, -literal, enum constant, macro), else None.

    Values are evaluated by clang, so `ERR_BUSY` from a header and `-4` compare equal and a macro's
    spelling never leaks into the result.
    """
    s, _ = _strip(c)
    if s.kind == K.CXX_NULL_PTR_LITERAL_EXPR:
        return "nullptr"
    if s.kind not in _LITERAL_KINDS:
        return None
    if s.kind == K.DECL_REF_EXPR and (s.referenced is None or s.referenced.kind != K.ENUM_CONSTANT_DECL):
        return None
    return _evaluate_int(s)


class FunctionAnalyzer:
    def __init__(self, fn: ci.Cursor, fn_usr: str):
        self.fn = fn
        self.fn_usr = fn_usr
        self.params: dict[str, tuple[int, ci.Cursor]] = {}
        for i, p in enumerate(fn.get_arguments() or []):
            self.params[p.get_usr()] = (i, p)
        self.alias: dict[str, set[AP]] = {}

    # ---- path resolution -------------------------------------------------
    def _var_root(self, ref: ci.Cursor) -> AP | None:
        usr = ref.get_usr()
        if usr in self.params:
            kind = ref.type.get_canonical().kind
            if kind in _PTR or kind in _REF:
                return AP("param", ref.spelling)
            return AP("local", ref.spelling)
        parent = ref.semantic_parent
        is_local = parent is not None and parent.kind in _FUNC_KINDS
        if not is_local or ref.storage_class == ci.StorageClass.STATIC:
            return AP("global", ref.spelling)
        return AP("local", ref.spelling)

    def lval(self, c: ci.Cursor) -> set[AP]:
        s, may = _strip(c)
        out: set[AP] = set()
        if s.kind == K.DECL_REF_EXPR and s.referenced is not None and s.referenced.kind in (K.VAR_DECL, K.PARM_DECL):
            ref = s.referenced
            usr = ref.get_usr()
            if ref.type.get_canonical().kind in _REF and usr in self.alias:
                out = {a.mark(via=ref.spelling) for a in self.alias[usr]}
            else:
                root = self._var_root(ref)
                if root is not None:
                    out = {root}
        elif s.kind == K.MEMBER_REF_EXPR and s.referenced is not None and s.referenced.kind == K.FIELD_DECL:
            f = s.referenced
            step = (f.get_usr(), f.spelling, f.semantic_parent.spelling if f.semantic_parent else "")
            kids = [k for k in s.get_children() if k.kind.is_expression()]
            if not kids:
                bases = {AP("this", "this")}
            else:
                b, _ = _strip(kids[0])
                if b.kind == K.CXX_THIS_EXPR:
                    bases = {AP("this", "this")}
                elif _type_kind(b) in _PTR:
                    bases = self.pointee(kids[0])
                else:
                    bases = self.lval(kids[0])
            out = {p.plus(step) for p in bases}
        elif s.kind == K.UNARY_OPERATOR and operator_of(s) == "pre*":
            kids = list(s.get_children())
            out = self.pointee(kids[0]) if kids else set()
        elif s.kind == K.ARRAY_SUBSCRIPT_EXPR:
            kids = list(s.get_children())
            if kids:
                base, _ = _strip(kids[0])
                src = self.lval(base) if _type_kind(base) in _ARRAY else self.pointee(kids[0])
                out = {p.plus(ELEM, may=False) for p in src}
        elif s.kind == K.CONDITIONAL_OPERATOR:
            kids = list(s.get_children())
            for k in kids[1:]:
                out |= self.lval(k)
            out = {a.mark(may=True) for a in out}
        return {a.mark(may=may) for a in out} if may else out

    def pointee(self, c: ci.Cursor) -> set[AP]:
        s, may = _strip(c)
        out: set[AP] = set()
        if _type_kind(s) in _ARRAY:
            out = {p.plus(ELEM) for p in self.lval(s)}
        elif s.kind == K.UNARY_OPERATOR and operator_of(s) == "pre&":
            kids = list(s.get_children())
            out = self.lval(kids[0]) if kids else set()
        elif s.kind == K.CXX_THIS_EXPR:
            out = {AP("this", "this")}
        elif s.kind == K.DECL_REF_EXPR and s.referenced is not None and s.referenced.kind in (K.VAR_DECL, K.PARM_DECL):
            ref = s.referenced
            usr = ref.get_usr()
            if usr in self.alias:
                out = {a.mark(via=ref.spelling) for a in self.alias[usr]}
            else:
                root = self._var_root(ref)
                if root is not None and root.root_kind in ("param", "global"):
                    out = {root}
        elif s.kind == K.MEMBER_REF_EXPR:
            out = {p.plus(DEREF) for p in self.lval(s)}
        elif s.kind == K.BINARY_OPERATOR and operator_of(s) in ("+", "-"):
            for k in s.get_children():
                kk, _ = _strip(k)
                if _type_kind(kk) in _PTR or _type_kind(kk) in _ARRAY:
                    out |= {p.plus(ELEM, may=True) for p in self.pointee(k)}
        elif s.kind == K.CONDITIONAL_OPERATOR:
            for k in list(s.get_children())[1:]:
                out |= self.pointee(k)
            out = {a.mark(may=True) for a in out}
        return {a.mark(may=may) for a in out} if may else out

    # ---- alias collection ------------------------------------------------
    def _alias_targets(self, var: ci.Cursor, init: ci.Cursor) -> set[AP]:
        kind = var.type.get_canonical().kind
        if kind in _PTR:
            return self.pointee(init)
        if kind in _REF:
            return self.lval(init)
        return set()

    def collect_aliases(self) -> None:
        for _ in range(4):
            changed = False
            for c in self.fn.walk_preorder():
                target_var, init = None, None
                if c.kind == K.VAR_DECL:
                    exprs = [k for k in c.get_children() if k.kind.is_expression()]
                    if exprs:
                        target_var, init = c, exprs[-1]
                elif c.kind == K.BINARY_OPERATOR and operator_of(c) == "=":
                    lhs, rhs = list(c.get_children())[:2]
                    l, _ = _strip(lhs)
                    if (l.kind == K.DECL_REF_EXPR and l.referenced is not None
                            and l.referenced.kind == K.VAR_DECL
                            and l.referenced.type.get_canonical().kind in _PTR):
                        target_var, init = l.referenced, rhs
                if target_var is None:
                    continue
                if self._var_root(target_var).root_kind == "global":
                    continue
                aps = self._alias_targets(target_var, init)
                if not aps:
                    continue
                cur = self.alias.setdefault(target_var.get_usr(), set())
                keys = {a.key() for a in cur}
                for a in aps:
                    if a.key() not in keys:
                        cur.add(a)
                        changed = True
            if not changed:
                return

    # ---- access recording ------------------------------------------------
    def analyze(self) -> tuple[list[FieldAccess], list[GlobalAccess]]:
        self.collect_aliases()
        fields: list[FieldAccess] = []
        globs: list[GlobalAccess] = []
        write_targets: set[int] = set()

        def emit(aps: set[AP], target: ci.Cursor, mode: str, extra_via: str | None = None) -> None:
            line = target.location.line
            file = target.location.file.name if target.location.file else ""
            emitted = False
            for a in aps:
                if a.steps and a.steps[-1] == DEREF and mode == "may_write":
                    emitted = True  # whole pointee object passed on; no specific field known
                    continue
                fstep = next((s for s in reversed(a.steps) if s[0] not in ("[]", "*")), None)
                if fstep is not None:
                    via = list(a.via) + ([extra_via] if extra_via else [])
                    fields.append(FieldAccess(
                        fn=self.fn_usr, field=fstep[0], field_name=fstep[1], record=fstep[2],
                        path=a.display(), root_kind=a.root_kind, mode=mode, via=via,
                        file=file, line=line, confidence="may" if (a.may or mode == "may_write") else "precise"))
                    emitted = True
                elif not a.steps and a.root_kind == "global" and mode != "may_write":
                    ref = _strip(target)[0].referenced
                    globs.append(GlobalAccess(fn=self.fn_usr, var=ref.get_usr() if ref else a.root,
                                              var_name=a.root, mode="write" if mode == "write" else "read",
                                              file=file, line=line))
            if not emitted and mode != "read":
                s, _ = _strip(target)
                if s.kind == K.MEMBER_REF_EXPR and s.referenced is not None and s.referenced.kind == K.FIELD_DECL:
                    f = s.referenced
                    fields.append(FieldAccess(
                        fn=self.fn_usr, field=f.get_usr(), field_name=f.spelling,
                        record=f.semantic_parent.spelling if f.semantic_parent else "",
                        path="?." + f.spelling, root_kind="unknown", mode=mode,
                        via=[extra_via] if extra_via else [], file=file, line=line, confidence="may"))

        for c in self.fn.walk_preorder():
            k = c.kind
            if k == K.BINARY_OPERATOR and operator_of(c) == "=" or k == K.COMPOUND_ASSIGNMENT_OPERATOR:
                lhs = list(c.get_children())[0]
                write_targets.add(_strip(lhs)[0].hash)
                emit(self.lval(lhs), lhs, "write")
            elif k == K.UNARY_OPERATOR and operator_of(c)[-2:] in ("++", "--"):
                kids = list(c.get_children())
                if kids:
                    write_targets.add(_strip(kids[0])[0].hash)
                    emit(self.lval(kids[0]), kids[0], "write")
            elif k == K.CALL_EXPR and c.referenced is not None and c.referenced.kind in _FUNC_KINDS:
                callee = c.referenced
                args = list(c.get_arguments())
                if callee.spelling in _MEMFUNCS and args:
                    emit(self.pointee(args[0]), args[0], "write", extra_via=f"call:{callee.spelling}")
                    continue
                params = list(callee.get_arguments() or [])
                for i, arg in enumerate(args):
                    if i >= len(params):
                        break
                    pt = params[i].type.get_canonical()
                    if pt.kind in _PTR and not pt.get_pointee().is_const_qualified():
                        emit(self.pointee(arg), arg, "may_write", extra_via=f"call:{callee.spelling}")
                    elif pt.kind == T.LVALUEREFERENCE and not pt.get_pointee().is_const_qualified():
                        emit(self.lval(arg), arg, "may_write", extra_via=f"call:{callee.spelling}")
        for c in self.fn.walk_preorder():
            if c.kind == K.MEMBER_REF_EXPR and c.referenced is not None and c.referenced.kind == K.FIELD_DECL:
                if c.hash in write_targets:
                    continue
                aps = self.lval(c)
                f = c.referenced
                file = c.location.file.name if c.location.file else ""
                path = next(iter(sorted(a.display() for a in aps)), "?." + f.spelling)
                root = next(iter(sorted(a.root_kind for a in aps)), "unknown")
                fields.append(FieldAccess(
                    fn=self.fn_usr, field=f.get_usr(), field_name=f.spelling,
                    record=f.semantic_parent.spelling if f.semantic_parent else "",
                    path=path, root_kind=root, mode="read", file=file, line=c.location.line,
                    confidence="precise" if aps else "may"))
            elif (c.kind == K.DECL_REF_EXPR and c.referenced is not None and c.referenced.kind == K.VAR_DECL
                  and c.hash not in write_targets):
                root = self._var_root(c.referenced)
                if root.root_kind == "global":
                    globs.append(GlobalAccess(fn=self.fn_usr, var=c.referenced.get_usr(), var_name=c.spelling,
                                              mode="read", file=c.location.file.name if c.location.file else "",
                                              line=c.location.line))
        return fields, globs
