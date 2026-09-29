"""Canonical file identity. Every module compares files through canon() so that symlinked
workspace roots, `..` segments and relative compile-DB entries all agree."""
from __future__ import annotations

import os


def canon(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))
