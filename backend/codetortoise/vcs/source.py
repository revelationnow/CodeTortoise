"""VCS source protocol."""
from __future__ import annotations

from typing import Protocol

from codetortoise.vcs.model import ChangeSet


class SourceError(RuntimeError):
    pass


class Source(Protocol):
    def load(self, cls: list[int]) -> ChangeSet: ...
