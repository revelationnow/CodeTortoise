"""compile_commands.json loading and libclang argument sanitation."""
from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from codetortoise.paths import canon

# flags that take a separate value and should be dropped together with it
_DROP_WITH_VALUE = {"-o", "-MF", "-MT", "-MQ", "-MJ", "--serialize-diagnostics"}
_DROP = {"-c", "-M", "-MM", "-MD", "-MMD", "-MP", "-MG", "-Werror", "-fcolor-diagnostics",
         "-fdiagnostics-color", "-pipe"}
# flags whose value is a path: made absolute (libclang resolves against the process cwd) and canonical
# (libclang matches unsaved files, e.g. headers added by a CL, by their canonical path)
_SEP_PATH_FLAGS = {"-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros", "--sysroot",
                   "-isysroot", "-F"}
_JOINED_PATH_FLAGS = ("-isystem", "-iquote", "-idirafter", "-I", "-F")


@dataclass(frozen=True)
class CompileEntry:
    file: str
    directory: str
    args: tuple[str, ...]


def _abs(directory: str, p: str) -> str:
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(directory, p))


class CompileDb:
    def __init__(self, entries: list[CompileEntry]):
        self.entries = entries
        self._by_file = {e.file: e for e in entries}
        self._by_dir: dict[str, list[CompileEntry]] = {}
        for e in entries:
            self._by_dir.setdefault(os.path.dirname(e.file), []).append(e)

    @classmethod
    def load(cls, path: Path) -> CompileDb:
        raw = json.loads(Path(path).read_text())
        entries = []
        for item in raw:
            directory = item.get("directory", os.path.dirname(str(path)))
            args = item.get("arguments") or shlex.split(item.get("command", ""))
            entries.append(CompileEntry(canon(_abs(directory, item["file"])), directory, tuple(args)))
        return cls(entries)

    def files(self) -> list[str]:
        return list(self._by_file)

    def entry_for(self, file: str) -> CompileEntry | None:
        return self._by_file.get(canon(file))

    def nearest_entry(self, file: str) -> CompileEntry | None:
        """Exact entry, else an entry in the same directory, else the one sharing the longest path prefix."""
        file = canon(file)
        if file in self._by_file:
            return self._by_file[file]
        d = os.path.dirname(file)
        while True:
            if d in self._by_dir:
                return self._by_dir[d][0]
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return self.entries[0] if self.entries else None


def sanitize_args(entry: CompileEntry, strip: set[str] = frozenset()) -> list[str]:
    """Compiler argv -> libclang args: drop compiler, output/dep flags, the source file; absolutize paths."""
    args = list(entry.args[1:])
    out: list[str] = []
    i = 0
    src = entry.file
    while i < len(args):
        a = args[i]
        if a in _DROP_WITH_VALUE:
            i += 2
            continue
        if a in _DROP or a in strip or a.split("=", 1)[0] in strip:
            i += 1
            continue
        if not a.startswith("-") and canon(_abs(entry.directory, a)) == src:
            i += 1
            continue
        if a in _SEP_PATH_FLAGS and i + 1 < len(args):
            out += [a, canon(_abs(entry.directory, args[i + 1]))]
            i += 2
            continue
        i += 1
        if a.startswith("--sysroot="):
            out.append("--sysroot=" + canon(_abs(entry.directory, a[len("--sysroot="):])))
            continue
        for flag in _JOINED_PATH_FLAGS:
            if a.startswith(flag) and len(a) > len(flag):
                out.append(flag + canon(_abs(entry.directory, a[len(flag):])))
                break
        else:
            out.append(a)
    return out
