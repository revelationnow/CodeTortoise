"""Language-agnostic facts emitted by FactExtractors."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Variant = Literal["before", "after"]
Confidence = Literal["precise", "may", "heuristic"]


class Param(BaseModel):
    name: str
    type: str
    is_const: bool = False


class Function(BaseModel):
    usr: str
    qualname: str
    name: str
    signature: str
    return_type: str
    params: list[Param] = Field(default_factory=list)
    file: str
    start_line: int
    end_line: int
    is_virtual: bool = False
    method_key: str | None = None
    is_static: bool = False
    returns: list[str] = Field(default_factory=list)
    return_names: dict[str, str] = Field(default_factory=dict)  # value -> macro/enum name, where known
    return_lines: dict[str, int] = Field(default_factory=dict)  # value -> first line returning it


class CallEdge(BaseModel):
    caller: str
    callee: str
    callee_name: str
    file: str
    line: int
    kind: Literal["direct", "virtual"] = "direct"
    result_used: bool = True
    compared: list[str] = Field(default_factory=list)  # e.g. ["!=0", "==-1"]
    compared_names: dict[str, str] = Field(default_factory=dict)  # "==-1" -> "GIT_ERROR"
    confidence: Confidence = "precise"


class FieldAccess(BaseModel):
    fn: str
    field: str            # FieldDecl USR, or "name:<field>" when heuristic
    field_name: str
    record: str
    record_file: str = ""  # file declaring the record (restricts heuristic name matches)
    decl_line: int = 0     # line of the field's declaration in record_file
    path: str             # display access path, e.g. "u.stats.tx"
    root_kind: Literal["param", "this", "global", "local", "unknown"]
    mode: Literal["read", "write", "may_write"]
    via: list[str] = Field(default_factory=list)  # alias vars / calls involved
    file: str
    line: int
    confidence: Confidence = "precise"


class GlobalAccess(BaseModel):
    fn: str
    var: str
    var_name: str
    mode: Literal["read", "write"]
    file: str
    line: int


class TuInfo(BaseModel):
    file: str
    variant: Variant
    error_count: int = 0
    diagnostics: list[str] = Field(default_factory=list)
    confidence: Literal["precise", "degraded", "failed"] = "precise"
    extractor: Literal["clang", "treesitter"] = "clang"
    stripped_flags: list[str] = Field(default_factory=list)
    supplemented: int = 0  # calls and field accesses tree-sitter added to a degraded parse


class Facts(BaseModel):
    tu: TuInfo
    functions: list[Function] = Field(default_factory=list)
    calls: list[CallEdge] = Field(default_factory=list)
    fields: list[FieldAccess] = Field(default_factory=list)
    globals: list[GlobalAccess] = Field(default_factory=list)


def relative_records(facts: list[Facts], root: str) -> None:
    """Anonymous records are named by their place ("anonymous struct (/ws/src/a.c:3)"): make it workspace-relative
    (spec 2026-10-04-change-stories §2.5), in place."""
    prefix = f"({root.rstrip('/')}/"
    for fx in facts:
        for a in fx.fields:
            if prefix in a.record:
                a.record = a.record.replace(prefix, "(")
