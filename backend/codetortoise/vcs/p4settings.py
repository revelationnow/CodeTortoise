"""Perforce settings the way `p4` finds them: the P4CONFIG file, then the environment.

`P4CONFIG` names a file. An absolute name is used as is; otherwise p4 looks for a file of that name in the current
directory and each parent, and the nearest one wins. Its values beat environment variables. CodeTortoise looks from the
workspace root, since that is where `p4` runs for it.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class P4Settings:
    values: dict[str, str] = field(default_factory=dict)   # from the P4CONFIG file
    file: Path | None = None
    env: Mapping[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        return self.values.get(key) or self.env.get(key) or None

    def source(self, key: str) -> str | None:
        """Where `get(key)` came from, for messages and the Health page."""
        if self.values.get(key):
            return f"P4CONFIG file {self.file}"
        if self.env.get(key):
            return f"environment variable {key}"
        return None


def _find(start: Path, name: str) -> Path | None:
    p = Path(name).expanduser()
    if p.is_absolute():
        return p if p.is_file() else None
    for d in [start, *start.parents]:
        if (d / name).is_file():
            return d / name
    return None


def _parse(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def p4_settings(root: Path, env: Mapping[str, str] | None = None) -> P4Settings:
    """The P4CONFIG file found from `root` (if `P4CONFIG` is set) and the environment behind it."""
    env = os.environ if env is None else env
    name = env.get("P4CONFIG")
    path = _find(Path(root), name) if name else None
    values = _parse(path.read_text(errors="replace")) if path else {}
    return P4Settings(values=values, file=path, env=env)
