"""Builds the bundled C/C++ fixture as a git-backed workspace (tests and demo)."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

FIXTURE_SRC = Path(__file__).parent / "fixtures" / "cfixture"
CL_DESCRIPTIONS = {
    101: "uart: count tx stats and report overflow",
    102: "uart: add flags field; hal_write takes unsigned reg",
}


@dataclass
class FixtureWorkspace:
    root: Path
    compile_commands: Path
    cls: list[int]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def build_fixture(dest: Path) -> FixtureWorkspace:
    root = Path(dest) / "ws"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(FIXTURE_SRC / "base", root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    for cl, desc in sorted(CL_DESCRIPTIONS.items()):
        shutil.copytree(FIXTURE_SRC / f"cl{cl}", root, dirs_exist_ok=True)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"CL {cl}: {desc}")
    _git(root, "checkout", "-q", base)
    entries = []
    for src in sorted(root.rglob("*")):
        if src.suffix not in (".c", ".cpp") or ".git" in src.parts:
            continue
        lang = ["-xc"] if src.suffix == ".c" else ["-xc++", "-std=c++17"]
        entries.append({"directory": str(root), "file": str(src),
                        "arguments": ["clang", *lang, "-Iinclude", "-I.", "-c", str(src),
                                      "-o", str(src.with_suffix(".o"))]})
    cc = root / "compile_commands.json"
    cc.write_text(json.dumps(entries, indent=2))
    return FixtureWorkspace(root=root, compile_commands=cc, cls=sorted(CL_DESCRIPTIONS))
