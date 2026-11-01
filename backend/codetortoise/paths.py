"""Canonical file identity. Every module compares files through canon() so that symlinked
workspace roots, `..` segments and relative compile-DB entries all agree."""
from __future__ import annotations

import os


def canon(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))


def within(path: str, folder: str) -> bool:
    """Whether `path` is `folder` or lies below it, both as given (pass real paths to judge where files really are)."""
    return path == folder or path.startswith(folder.rstrip("/") + "/")
