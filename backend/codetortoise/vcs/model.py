"""Change-set model shared by all VCS sources."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClMeta(BaseModel):
    cl: int
    status: Literal["pending", "submitted"]
    user: str = ""
    description: str = ""


class PerClText(BaseModel):
    cl: int
    before: str
    after: str


class FileChange(BaseModel):
    depot: str
    local: str
    action: str                 # add | edit | delete | move/add | move/delete | integrate | branch
    before: str                 # content before the first CL touching this file ("" if added)
    after: str                  # content after the last CL touching this file ("" if deleted)
    base_rev: str | None = None  # revision the first CL is based on (p4: "#N"; git: commit sha)
    per_cl: list[PerClText] = Field(default_factory=list)


class DriftItem(BaseModel):
    depot: str
    local: str
    expected: str
    actual: str


class SourceFile(BaseModel):
    depot: str
    local: str
    rev: str       # p4: "#<have rev>"; git fixture: "workspace"
    text: str


class ChangeSet(BaseModel):
    cls: list[ClMeta]
    files: list[FileChange]
    drift: list[DriftItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # per-file problems that did not stop ingest


def stack(per_cl: list[tuple[ClMeta, list[FileChange]]]) -> list[FileChange]:
    """Combine per-CL file changes (sorted by CL number) into cumulative changes.

    For a file touched by several CLs: before = first CL's before, after = last CL's after,
    per_cl keeps each CL's own before/after.
    """
    merged: dict[str, FileChange] = {}
    for meta, files in sorted(per_cl, key=lambda x: x[0].cl):
        for f in files:
            step = PerClText(cl=meta.cl, before=f.before, after=f.after)
            if f.depot not in merged:
                merged[f.depot] = f.model_copy(update={"per_cl": [step]})
            else:
                m = merged[f.depot]
                action = m.action
                if f.action == "delete":
                    action = "delete"
                elif action == "delete":
                    action = "edit"
                merged[f.depot] = m.model_copy(update={"after": f.after, "action": action,
                                                       "per_cl": m.per_cl + [step]})
    return sorted(merged.values(), key=lambda f: f.depot)
