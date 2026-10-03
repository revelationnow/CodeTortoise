"""Toolchain: turns compile-DB entries into libclang args that work for the vendor cross toolchain."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from codetortoise.config import ToolchainConfig, ToolchainOverride
from codetortoise.paths import canon
from codetortoise.toolchain.compile_db import CompileDb, CompileEntry, sanitize_args
from codetortoise.toolchain.driver import DriverInfo, query_driver, target_flags
from codetortoise.toolchain.libclang import LibclangInfo, load_libclang

_CXX_EXTS = {".cc", ".cpp", ".cxx", ".c++", ".hpp", ".hh", ".hxx"}


# Macros that describe the *compiler* rather than the target. Importing the driver's values would make
# libclang impersonate that compiler (e.g. gcc's __GNUC__ makes glibc expect _Float32/_Float64 types).
_IDENTITY_PREFIXES = ("__GNUC", "__GNUG", "__clang", "__llvm", "__VERSION__", "__STDC", "__GCC_", "__GXX_",
                      "__apple_build", "__OPTIMIZE", "__NO_INLINE__", "__OBJC", "__cplusplus")


def is_identity_macro(name: str) -> bool:
    return name.startswith(_IDENTITY_PREFIXES)


def lang_of(path: str) -> str:
    return "c++" if Path(path).suffix.lower() in _CXX_EXTS else "c"


@dataclass
class Group:
    """Files sharing a compiler, target and target-affecting flags: one driver query per language."""
    compiler: str
    target: str | None
    flags: tuple[str, ...]
    files: int = 0
    error: str | None = None
    info: dict[str, DriverInfo] = field(default_factory=dict)
    preludes: dict[str, Path] = field(default_factory=dict)


_COMPILER_SUFFIXES = ("-gcc", "-g++", "-cc", "-c++", "-clang", "-clang++", "-cpp")


def triple_from_name(compiler: str) -> str | None:
    """"arm-none-eabi-gcc" -> "arm-none-eabi" (also with a version suffix like "-12"); None for plain names."""
    base = os.path.basename(compiler).lower().removesuffix(".exe")
    base = re.sub(r"-\d+(\.\d+)*$", "", base)
    for suffix in _COMPILER_SUFFIXES:
        if base.endswith(suffix):
            stem = base[: -len(suffix)]
            return stem if "-" in stem else None
    return None


def _explicit_target(args: list[str]) -> bool:
    return any(a.startswith("--target=") or a == "-target" for a in args)


class Toolchain:
    """Turns compile entries into libclang arguments, per file: each file's own compiler is queried (once per
    toolchain group and language) for its built-in include paths and macros, and its target is made explicit."""

    def __init__(self, cfg: ToolchainConfig, cdb: CompileDb, work_dir: Path, root: Path | None = None):
        self.cfg = cfg
        self.cdb = cdb
        self.work_dir = Path(work_dir)
        self.root = canon(str(root)) if root else None
        self.strip: set[str] = set(cfg.strip_flags)
        self.libclang: LibclangInfo | None = None
        self._groups: dict[tuple, Group] = {}
        self._machines: dict[str, str | None] = {}

    def prepare(self) -> None:
        """Idempotent: loads libclang. Compilers are queried lazily, per group."""
        if self.libclang is None:
            self.libclang = load_libclang(self.cfg.libclang)

    # ---- per file
    def _override(self, file: str) -> ToolchainOverride | None:
        rel = file[len(self.root) + 1:] if self.root and file.startswith(self.root + "/") else file
        return next((o for o in self.cfg.overrides if fnmatch.fnmatch(rel, o.match)), None)

    def _entry(self, file: str, ov: ToolchainOverride | None) -> CompileEntry | None:
        if ov is not None and ov.compile_commands is not None:
            hit = self.cdb.entry_for(file, prefer=str(ov.compile_commands))
            if hit is not None and hit.db == str(ov.compile_commands):
                return hit
        return self.cdb.nearest_entry(file)

    def _driver(self, entry: CompileEntry, ov: ToolchainOverride | None) -> str:
        name = (ov.clang if ov and ov.clang else None) or self.cfg.clang or entry.compiler
        if os.path.isabs(name):
            return name
        if "/" in name:
            return os.path.normpath(os.path.join(entry.directory, name))
        return shutil.which(name) or name

    def _machine(self, driver: str) -> str | None:
        if driver not in self._machines:
            try:
                r = subprocess.run([driver, "-dumpmachine"], capture_output=True, text=True, timeout=30)
                self._machines[driver] = r.stdout.strip() or None if r.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired):
                self._machines[driver] = None
        return self._machines[driver]

    def _group(self, entry: CompileEntry, args: list[str], ov: ToolchainOverride | None) -> Group:
        driver = self._driver(entry, ov)
        if _explicit_target(args):
            target = None
        else:
            target = ((ov.target if ov else None) or self.cfg.target or triple_from_name(entry.compiler)
                      or triple_from_name(driver) or self._machine(driver))
        flags = tuple(target_flags(args))
        key = (driver, target, flags)
        if key not in self._groups:
            self._groups[key] = Group(compiler=driver, target=target, flags=flags)
        return self._groups[key]

    def _query(self, g: Group, lang: str) -> DriverInfo | None:
        if lang in g.info or g.error:
            return g.info.get(lang)
        try:
            info = query_driver(g.compiler, list(g.flags), lang)
        except RuntimeError as e:
            g.error = str(e)
            return None
        g.info[lang] = info
        self.work_dir.mkdir(parents=True, exist_ok=True)
        tag = hashlib.sha1(repr((g.compiler, g.target, g.flags)).encode()).hexdigest()[:10]
        prelude = self.work_dir / f"prelude-{tag}-{'cxx' if lang == 'c++' else 'c'}.h"
        prelude.write_text("".join(f"#define {n} {v}\n" for n, v in info.defines if not is_identity_macro(n)))
        g.preludes[lang] = prelude
        return info

    def args_for(self, file: str) -> list[str]:
        file = canon(file)
        ov = self._override(file)
        entry = self._entry(file, ov)
        if entry is None:
            return ["-x", "c++" if lang_of(file) == "c++" else "c"]
        args = sanitize_args(entry, self.strip)
        g = self._group(entry, args, ov)
        if g.target:
            args += [f"--target={g.target}"]
        lang = lang_of(entry.file)
        vendor = self.libclang is not None and self.libclang.vendor
        info = None if vendor else self._query(g, lang)
        if info is not None:
            rd = self.cfg.resource_dir or info.resource_dir
            if rd:
                args += ["-resource-dir", rd]
            for d in info.include_dirs:
                if rd and os.path.normpath(d).startswith(os.path.normpath(rd)):
                    continue
                args += ["-isystem", d]
            args += ["-include", str(g.preludes[lang]), "-Wno-macro-redefined", "-Wno-builtin-macro-redefined"]
        return args

    def group_of(self, file: str) -> Group | None:
        file = canon(file)
        ov = self._override(file)
        entry = self._entry(file, ov)
        return self._group(entry, sanitize_args(entry, self.strip), ov) if entry else None

    def groups(self) -> list[Group]:
        """Every toolchain group in the compile databases, with its file count (queries happen on first use)."""
        for g in self._groups.values():
            g.files = 0
        for e in self.cdb.entries:
            ov = self._override(e.file)
            self._group(e, sanitize_args(e, self.strip), ov).files += 1
        return [g for g in self._groups.values() if g.files]
