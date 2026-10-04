"""A generated C project large enough to need an overview and cluster boards (spec 2026-10-03-large-change-boards §8).

Six modules in four layers (hal, drv, svc, app), each a header and four source files, plus tests. CL 201 makes
changes across the stack: new return values that callers ignore, and new writes to fields other code reads. CL 202
changes the tests and one service function. Like the bundled fixture, it is a git workspace whose CLs are commits.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from codetortoise.fixture import FixtureWorkspace

# (directory, module, the module it calls into)
MODULES = [("hal/regs", "regs", None), ("drv/uart", "uart", "regs"), ("drv/dma", "dma", "regs"),
           ("svc/logger", "logger", "uart"), ("svc/stats", "stats", "dma"), ("app/telemetry", "telem", "logger")]
FILES = "abcd"
FNS = 5
CL_DESCRIPTIONS = {201: "stats: count transmit errors across the stack", 202: "tests: cover the new error counts"}
CHANGED = {"a": (1, 2, 3), "b": (1, 2)}     # file -> functions CL 201 changes in every module


def _fn(mod: str, f: str, i: int) -> str:
    return f"{mod}_{f}{i}"


def _header(mod: str, low: str | None) -> str:
    protos = "\n".join(f"int {_fn(mod, f, i)}(int v);" for f in FILES for i in range(1, FNS + 1))
    inc = f'#include "{low}.h"\n' if low else ""
    t = mod.capitalize()
    return (f"#ifndef {mod.upper()}_H\n#define {mod.upper()}_H\n{inc}\nstruct {t}Dev {{\n\tint count;\n\tint errors;\n"
            f"\tint state;\n\tint last;\n}};\n\nextern struct {t}Dev {mod}_dev;\n\n{protos}\n\n#endif\n")


def _source(mod: str, low: str | None, f: str, changed: bool) -> str:
    out = [f'#include "{mod}.h"\n']
    if f == "a":
        out.append(f"struct {mod.capitalize()}Dev {mod}_dev;\n")
    for i in range(1, FNS + 1):
        name = _fn(mod, f, i)
        body = []
        if low:
            callee = _fn(low, f, i)
            # odd functions ignore what the lower layer returns (a contract flow lands there when it changes)
            body.append(f"\t{callee}(v);" if i % 2 else f"\tint r = {callee}(v);\n\tif (r < 0)\n\t\treturn r;")
        if f == "d":
            body.append(f"\treturn {mod}_dev.errors + {mod}_dev.last;")       # readers: state flows land here
        else:
            body.append(f"\t{mod}_dev.count += 1;")
            if changed and i in CHANGED.get(f, ()):
                body.append(f"\tif (v > 100) {{\n\t\t{mod}_dev.errors = v;\n\t\t{mod}_dev.last = {i};\n\t\treturn -2;\n\t}}")
            body.append("\tif (v < 0)\n\t\treturn -1;\n\treturn 0;")
        out.append(f"int {name}(int v)\n{{\n" + "\n".join(body) + "\n}\n")
    return "\n".join(out)


def _tests(changed: bool) -> str:
    lines = ['#include "uart.h"', '#include "stats.h"', "", "int test_uart(void)", "{", "\tif (uart_a1(1) != 0)",
             "\t\treturn 1;"]
    if changed:
        lines += ["\tif (uart_a1(101) != -2)", "\t\treturn 2;", "\tif (stats_a2(101) != -2)", "\t\treturn 3;"]
    lines += ["\treturn 0;", "}", ""]
    return "\n".join(lines)


def _write(root: Path, changed: int) -> None:
    for d, mod, low in MODULES:
        (root / "include").mkdir(parents=True, exist_ok=True)
        (root / "include" / f"{mod}.h").write_text(_header(mod, low))
        (root / d).mkdir(parents=True, exist_ok=True)
        for f in FILES:
            ch = changed >= 201 and (mod != "stats" or changed >= 202 or f != "b")
            (root / d / f"{mod}_{f}.c").write_text(_source(mod, low, f, ch))
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_uart.c").write_text(_tests(changed >= 202))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def build_large_fixture(dest: Path) -> FixtureWorkspace:
    root = Path(dest) / "ws"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write(root, 0)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    for cl, desc in sorted(CL_DESCRIPTIONS.items()):
        _write(root, cl)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"CL {cl}: {desc}")
    _git(root, "checkout", "-q", base)
    entries = [{"directory": str(root), "file": str(src),
                "arguments": ["clang", "-xc", "-Iinclude", "-c", str(src), "-o", str(src.with_suffix(".o"))]}
               for src in sorted(root.rglob("*.c")) if ".git" not in src.parts]
    cc = root / "compile_commands.json"
    cc.write_text(json.dumps(entries, indent=2))
    return FixtureWorkspace(root=root, compile_commands=cc, cls=sorted(CL_DESCRIPTIONS))
