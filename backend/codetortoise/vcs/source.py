"""VCS source protocol."""
from __future__ import annotations

from typing import Protocol

from codetortoise.vcs.model import ChangeSet, SourceFile

MAX_SOURCE_BYTES = 2 * 1024 * 1024


class SourceError(RuntimeError):
    pass


class SourceNotAllowed(SourceError):
    """The path is not in the base workspace (outside the client view / root, not synced, or missing)."""


class SourceBinary(SourceError):
    pass


class SourceTooLarge(SourceError):
    pass


class Source(Protocol):
    def load(self, cls: list[int]) -> ChangeSet: ...

    def depots_for(self, locals_: list[str]) -> dict[str, str]:
        """Depot path for each canonical local path that is in the base workspace (others are omitted)."""
        ...

    def read(self, depot: str) -> SourceFile:
        """Content of an unchanged file as the base workspace has it (for context code on demand)."""
        ...
