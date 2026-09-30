"""Toolchain: turns compile-DB entries into libclang args that work for the vendor cross toolchain."""
from __future__ import annotations

import os
from pathlib import Path

from codetortoise.config import ToolchainConfig
from codetortoise.toolchain.compile_db import CompileDb, sanitize_args
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


class Toolchain:
    def __init__(self, cfg: ToolchainConfig, cdb: CompileDb, work_dir: Path):
        self.cfg = cfg
        self.cdb = cdb
        self.work_dir = Path(work_dir)
        self.strip: set[str] = set(cfg.strip_flags)
        self.libclang: LibclangInfo | None = None
        self.driver: dict[str, DriverInfo] = {}
        self.driver_error: str | None = None
        self._preludes: dict[str, Path] = {}

    def prepare(self) -> None:
        """Idempotent: loads libclang and queries the driver once per process."""
        if self.libclang is not None:
            return
        self.libclang = load_libclang(self.cfg.libclang)
        if not self.cfg.clang or self.libclang.vendor or not self.cdb.entries:
            return
        self.work_dir.mkdir(parents=True, exist_ok=True)
        for lang in ("c", "c++"):
            sample = next((e for e in self.cdb.entries if lang_of(e.file) == lang), None)
            if sample is None:
                continue
            try:
                info = query_driver(self.cfg.clang, target_flags(sanitize_args(sample, self.strip)), lang)
            except RuntimeError as e:
                self.driver_error = str(e)
                continue
            self.driver[lang] = info
            prelude = self.work_dir / f"prelude-{'cxx' if lang == 'c++' else 'c'}.h"
            prelude.write_text("".join(f"#define {n} {v}\n" for n, v in info.defines if not is_identity_macro(n)))
            self._preludes[lang] = prelude

    def args_for(self, file: str) -> list[str]:
        entry = self.cdb.nearest_entry(file)
        if entry is None:
            return ["-x", "c++" if lang_of(file) == "c++" else "c"]
        args = sanitize_args(entry, self.strip)
        lang = lang_of(entry.file)
        info = self.driver.get(lang)
        if info is not None:
            rd = self.cfg.resource_dir or info.resource_dir
            if rd:
                args += ["-resource-dir", rd]
            for d in info.include_dirs:
                if rd and os.path.normpath(d).startswith(os.path.normpath(rd)):
                    continue
                args += ["-isystem", d]
            args += ["-include", str(self._preludes[lang]), "-Wno-macro-redefined",
                     "-Wno-builtin-macro-redefined"]
        return args
