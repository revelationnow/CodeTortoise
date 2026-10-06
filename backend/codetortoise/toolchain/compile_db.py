"""compile_commands.json loading and libclang argument sanitation."""
from __future__ import annotations

import glob as globmod
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
# words in front of the real compiler: build caches and distributed compilers
WRAPPERS = {"ccache", "sccache", "distcc", "icecc", "buildcache"}
# MSVC output/debug-file flags (joined value, optionally after ':'), dropped like -o
_CL_OUTPUT = ("/Fo", "/Fd", "/Fe", "/Fp", "/Fa", "/Fm", "/Fr", "/FR", "/FS")


def _base(word: str) -> str:
    """Program name without directory, case or .exe: "C:/VS/bin/cl.exe" -> "cl"."""
    name = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def is_cl(compiler: str) -> bool:
    return _base(compiler) in ("cl", "clang-cl")


@dataclass(frozen=True)
class CompileEntry:
    file: str
    directory: str
    args: tuple[str, ...]            # args[0] is the compiler (wrappers and response files already resolved)
    compiler: str = ""
    db: str = ""                     # the compile_commands.json it came from


def _expand(args: list[str], directory: str, problems: list[str], what: str, depth: int = 0) -> list[str]:
    """Replace each @file with its words (shell rules), recursively, relative to the entry's directory."""
    out: list[str] = []
    for a in args:
        if a.startswith("@") and len(a) > 1 and depth < 10:
            path = _abs(directory, a[1:])
            try:
                words = shlex.split(Path(path).read_text(errors="replace"))
            except (OSError, ValueError):
                problems.append(f"response file not found: {path} (for {what})")
                out.append(a)
                continue
            out += _expand(words, directory, problems, what, depth + 1)
        else:
            out.append(a)
    return out


def _compiler_words(args: list[str]) -> list[str]:
    """Drop an `env VAR=x ...` prefix and build wrappers, so args[0] is the real compiler."""
    i = 0
    if args and _base(args[0]) == "env":
        i = 1
        while i < len(args) and ("=" in args[i] or args[i].startswith("-")):
            i += 1
    while i < len(args) - 1 and _base(args[i]) in WRAPPERS:
        i += 1
    return args[i:]


def _abs(directory: str, p: str) -> str:
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(directory, p))


class CompileDb:
    """Compile entries by source file, from one or more databases listed in precedence order.

    A file in several databases (or listed twice) uses its first entry; `duplicates` counts those whose other entries
    differ. A file in no database borrows the nearest entry of the database whose files' common folder contains it,
    never one from another database.
    """

    def __init__(self, entries: list[CompileEntry], problems: list[str] | None = None):
        self.problems = problems or []           # e.g. response files that could not be read
        self._by_file: dict[str, CompileEntry] = {}
        self._all: dict[str, list[CompileEntry]] = {}
        self.duplicates = 0
        for e in entries:
            self._all.setdefault(e.file, []).append(e)
            first = self._by_file.setdefault(e.file, e)
            if first is not e and first.args[1:] != e.args[1:]:
                self.duplicates += 1
        self.entries = list(self._by_file.values())
        self.databases: list[tuple[str, int]] = []           # (path, entries used from it), precedence order
        self._dbs: dict[str, tuple[str, dict[str, list[CompileEntry]]]] = {}   # db -> (files' common folder, by dir)
        for e in self.entries:
            root, by_dir = self._dbs.setdefault(e.db, (os.path.dirname(e.file), {}))
            by_dir.setdefault(os.path.dirname(e.file), []).append(e)
            if not (os.path.dirname(e.file) + "/").startswith(root.rstrip("/") + "/"):
                root = os.path.commonpath([root, os.path.dirname(e.file)])
            self._dbs[e.db] = (root, by_dir)
        used = {db: sum(len(v) for v in by_dir.values()) for db, (_, by_dir) in self._dbs.items()}
        # every database loaded, in precedence order, with how many of its entries are used (0 when all are shadowed)
        self.databases = [(db, used.get(db, 0)) for db in dict.fromkeys(e.db for e in entries) if db]

    @classmethod
    def load(cls, path: Path) -> CompileDb:
        problems: list[str] = []
        return cls(_read(Path(path), problems), problems)

    def files(self) -> list[str]:
        return list(self._by_file)

    def entry_for(self, file: str, prefer: str | None = None) -> CompileEntry | None:
        """The file's entry; with `prefer`, the entry from that database when it has one."""
        file = canon(file)
        if prefer is not None:
            want = os.path.realpath(str(prefer))
            hit = next((e for e in self._all.get(file, []) if os.path.realpath(e.db) == want), None)
            if hit is not None:
                return hit
        return self._by_file.get(file)

    def databases_of(self, file: str) -> list[str]:
        """Every database holding a command for the file, in precedence order (none: a header, an unbuilt file)."""
        return list(dict.fromkeys(e.db for e in self._all.get(canon(file), [])))

    def nearest_entry(self, file: str) -> CompileEntry | None:
        """Exact entry, else one in the same folder, else the nearest folder up, within the file's own database."""
        file = canon(file)
        if file in self._by_file:
            return self._by_file[file]
        owners = [(len(root), db) for db, (root, _) in self._dbs.items()
                  if (file + "/").startswith(root.rstrip("/") + "/")]
        if owners:
            by_dir = self._dbs[max(owners)[1]][1]
        elif len(self._dbs) == 1:                # one database: as before, its nearest entry anywhere
            by_dir = next(iter(self._dbs.values()))[1]
        else:
            return None
        d = os.path.dirname(file)
        while True:
            if d in by_dir:
                return by_dir[d][0]
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return next(iter(by_dir.values()))[0] if by_dir else None


def _read(path: Path, problems: list[str]) -> list[CompileEntry]:
    entries = []
    for item in json.loads(path.read_text()):
        directory = item.get("directory", os.path.dirname(str(path)))
        args = item.get("arguments") or shlex.split(item.get("command", ""))
        args = _compiler_words(_expand(list(args), directory, problems, item["file"]))
        entries.append(CompileEntry(canon(_abs(directory, item["file"])), directory, tuple(args),
                                    compiler=args[0] if args else "", db=str(path)))
    return entries


SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".svn", ".tortoise"}


def find_databases(top: Path) -> list[Path]:
    """Every compile_commands.json under `top` (hidden folders skipped), deepest first."""
    found = []
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
        if "compile_commands.json" in filenames:
            found.append(Path(dirpath) / "compile_commands.json")
    return sorted(found, key=lambda p: (-len(p.parts), str(p)))


def load_databases(spec, root: Path, build_root: Path | None) -> CompileDb:
    """`workspace.compile_commands`: one path, a list of paths or globs (first listed wins), or "auto" (every database
    under `build_root`, deepest first; without one, under the folder of the first database `codetortoise init` would
    find). Missing files are skipped."""
    if spec == "auto":
        if build_root is None:
            from codetortoise.init_config import _compile_dbs
            first = _compile_dbs(Path(root))
            build_root = first[0].parent if first else None
        paths = find_databases(Path(build_root)) if build_root is not None else []
    else:
        paths = []
        for item in spec if isinstance(spec, list) else [spec]:
            text = str(item)
            hits = sorted(Path(p) for p in globmod.glob(text, recursive=True)) if any(c in text for c in "*?[") \
                else [Path(text)]
            paths += [p for p in hits if p not in paths]
    entries: list[CompileEntry] = []
    problems: list[str] = []
    for p in paths:
        if p.is_file():
            entries += _read(p, problems)
    return CompileDb(entries, problems)


def include_dirs(cdb: CompileDb) -> list[str]:
    """Union of -I/-isystem/-iquote/-idirafter dirs across all entries, canonical, first-seen order."""
    seen: dict[str, None] = {}
    for e in cdb.entries:
        args = sanitize_args(e)
        for i, a in enumerate(args):
            if a in ("-I", "-isystem", "-iquote", "-idirafter") and i + 1 < len(args):
                seen.setdefault(args[i + 1], None)
            elif a.startswith("-I") and len(a) > 2:
                seen.setdefault(a[2:], None)
    return list(seen)


def sanitize_args(entry: CompileEntry, strip: set[str] = frozenset()) -> list[str]:
    """Compiler argv -> libclang args: drop compiler, output/dep flags, the source file; absolutize paths. Relative
    paths that remain resolve from the entry's directory (`-working-directory`); MSVC commands use clang's cl mode."""
    args = list(entry.args[1:])
    cl = is_cl(entry.compiler or (entry.args[0] if entry.args else ""))
    out: list[str] = ["-working-directory", entry.directory] + (["--driver-mode=cl"] if cl else [])
    i = 0
    src = entry.file
    while i < len(args):
        a = args[i]
        if a in _DROP_WITH_VALUE:
            i += 2
            continue
        if a in _DROP or a in strip or a.split("=", 1)[0] in strip or (cl and (a.startswith(_CL_OUTPUT) or a == "/c")):
            i += 1
            continue
        if not a.startswith("-") and canon(_abs(entry.directory, a)) == src:
            i += 1
            continue
        if a in ("-include", "-imacros") and i + 1 < len(args):
            # gcc looks in the working directory first, then the #include "..." chain: only pin it when it exists here
            val = args[i + 1]
            cand = _abs(entry.directory, val)
            out += [a, canon(cand) if os.path.isabs(val) or os.path.exists(cand) else val]
            i += 2
            continue
        if a in _SEP_PATH_FLAGS and i + 1 < len(args):
            out += [a, canon(_abs(entry.directory, args[i + 1]))]
            i += 2
            continue
        i += 1
        if a.startswith("--sysroot="):
            out.append("--sysroot=" + canon(_abs(entry.directory, a[len("--sysroot="):])))
            continue
        for flag in _JOINED_PATH_FLAGS + (("/I",) if cl else ()):    # cl mode ignores -working-directory for /I
            if a.startswith(flag) and len(a) > len(flag):
                out.append(flag + canon(_abs(entry.directory, a[len(flag):])))
                break
        else:
            out.append(a)
    return out
