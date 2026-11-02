"""Toolchain: turns compile-DB entries into libclang args that work for the vendor cross toolchain."""
from __future__ import annotations

import errno
import fnmatch
import functools
import grp
import hashlib
import logging
import os
import pwd
import re
import shutil
import stat
import subprocess
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from codetortoise.config import ToolchainConfig, ToolchainOverride
from codetortoise.paths import canon, within
from codetortoise.toolchain.compile_db import CompileDb, CompileEntry, sanitize_args
from codetortoise.toolchain.driver import DriverInfo, query_driver, target_flags
from codetortoise.toolchain.libclang import LibclangChoice, LibclangInfo, find_libclang, library_info

_CXX_EXTS = {".cc", ".cpp", ".cxx", ".c++", ".hpp", ".hh", ".hxx"}
log = logging.getLogger(__name__)


# Macros that describe the *compiler* rather than the target. Importing the driver's values would make
# libclang impersonate that compiler (e.g. gcc's __GNUC__ makes glibc expect _Float32/_Float64 types).
_IDENTITY_PREFIXES = ("__GNUC", "__GNUG", "__clang", "__llvm", "__VERSION__", "__STDC", "__GCC_", "__GXX_",
                      "__apple_build", "__OPTIMIZE", "__NO_INLINE__", "__OBJC", "__cplusplus",
                      # language-feature and gcc-only type macros: clang sets its own from the file's own flags
                      # (-fno-rtti, -std), and gcc 13+'s __BFLT16_* make libstdc++ use 'bf16' constants clang rejects
                      "__cpp_", "__STDCPP_", "__BFLT16_", "__FLT16_", "__EXCEPTIONS", "__FLT128", "__SIZEOF_FLOAT128",
                      "__SIZEOF_FLOAT80")

# gcc's own header folder (intrinsics, stddef, ...): libclang has its own; mixing them breaks parses
_GCC_INTERNAL = re.compile(r"/lib(?:64)?/gcc(?:-cross)?/[^/]+/[^/]+/include(?:-fixed)?/?$")


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
    refused: bool = False            # the error is why the compiler isn't run, judged again by again()
    libclang: LibclangChoice | None = None
    sample: str | None = None        # a file of the group, for Health
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


def changeable(path: str, me: int | None = None, create: bool = False, tree: str | None = None) -> str | None:
    """Who besides root and this server's account (`me`) can change what `path` leads to — the file, a folder on the
    way, or a link followed on the way, where a program could be swapped in — and how to stop them; None when no one
    can. A folder others may write to but whose sticky bit keeps them from renaming what isn't theirs counts as safe,
    and a group may write only when it is the account's own private group (the owner's choice, 2026-11-01: final review
    I3 of spec 2026-10-31). With `create`, `path` need not be there: then no one else may add it either, and the folder
    it would go in must be closed to them, sticky or not. `tree`, the folder a toolchain is installed in, adds the
    command that fixes all of it to the fix for what lies in it. Another account's home on the way is said first, with
    the move as the fix: it is theirs to keep, and what lies in it is theirs to change however it is owned (final
    review of branch deferred-minors-2, M2)."""
    me = os.geteuid() if me is None else me
    todo = path.split("/") if os.path.isabs(path) else [*os.getcwd().split("/"), *path.split("/")]
    at, links, missing, failed = "/", 0, None, None
    passed = []                                  # every entry the system goes through to reach `path`, in order
    try:
        passed.append(("/", os.lstat("/")))
        while todo:
            name = todo.pop(0)
            if name in ("", "."):
                continue
            if name == "..":
                at = os.path.dirname(at)
                continue
            entry = os.path.join(at, name)
            try:
                st = os.lstat(entry)
            except FileNotFoundError:
                if not create:
                    raise
                missing = entry                  # what others could add, in the folder `at`
                break
            passed.append((entry, st))
            if not stat.S_ISLNK(st.st_mode):
                at = entry
                continue
            links += 1
            if links > 40:
                failed = f"{path} can't be checked (too many links on the way)"
                break
            target = os.readlink(entry)
            at = "/" if target.startswith("/") else at
            todo[:0] = target.split("/")
    except OSError as e:                         # who could change what was passed still comes first
        failed = f"{e.filename or path} can't be checked ({e.strerror})"
    for entry, st in passed:
        name = _home(entry, st, me)
        if name:
            return f"{entry} is the home of {name}, who can change it ({_MOVE})"
    if missing is not None:
        why = _adds(at, missing, path, me, tree)
        if why:
            return why
    for entry, st in reversed(passed):           # the file first, then the folders and links on the way to it
        why = _who(entry, st, me, tree)
        if why:
            return why
    return failed


_MOVE = "move the toolchain to a folder only you and root can change"


def _fix(command: str, path: str, tree: str | None, whole: str) -> str:
    """How to stop others: `command` for `path` itself and, for a path inside a toolchain's folder `tree`, `whole` run
    on `tree` for all of it, so the host isn't walked through one folder per Recheck (final review of branch
    deferred-minors); said as what it fixes, everything in `tree` (final review of branch deferred-minors-2, I1)."""
    if tree is not None and within(path, tree):
        return f"`{command}` fixes it; `{whole} {tree}` fixes everything in {tree}"
    return f"`{command}` fixes it"


def _adds(folder: str, missing: str, path: str, me: int, tree: str | None = None) -> str | None:
    """Who besides root and `me` can add `missing`, on the way to `path`, to `folder`: a sticky bit doesn't stop them
    adding what isn't there (its owner is judged with the folders on the way)."""
    try:
        st = os.lstat(folder)
    except OSError as e:
        return f"{folder} can't be checked ({e.strerror})"
    if st.st_mode & stat.S_IWOTH:
        # a shared folder such as /tmp stays open to all: a folder of root's in its place stops them
        fix = f"`sudo mkdir {missing}` stops that" if st.st_mode & stat.S_ISVTX and missing != path \
            else _fix(f"chmod o-w {folder}", folder, tree, "chmod -R go-w")
        return f"anyone can add {missing} ({fix})"
    if st.st_mode & stat.S_IWGRP:
        fix = _fix(f"chmod g-w {folder}", folder, tree, "chmod -R go-w")
        if not _own_group(st.st_gid, me):
            return f"the group {_name(grp.getgrgid, st.st_gid)} can add {missing} ({fix})"
        try:
            if _listed_others(folder):
                return f"an access list (ACL) on {folder} can let others add {missing} ({fix})"
        except OSError as e:
            return f"the access list (ACL) of {folder} can't be read ({e.strerror}): it may let others add {missing} ({fix})"
    return None


def _who(path: str, st: os.stat_result, me: int, tree: str | None = None) -> str | None:
    """Who besides root and `me` can change the one entry `path` (its lstat `st`), and how to stop them."""
    if st.st_uid not in (0, me):
        try:
            owner = pwd.getpwuid(st.st_uid)
        except KeyError:
            owner = None
        name = owner.pw_name if owner is not None else str(st.st_uid)
        fix = _fix(f"sudo chown{' -h' if stat.S_ISLNK(st.st_mode) else ''} root {path}", path, tree, "sudo chown -R root")
        return f"{path} belongs to {name}, who can change it ({fix}; or {_MOVE})"
    if stat.S_ISLNK(st.st_mode) or stat.S_ISDIR(st.st_mode) and st.st_mode & stat.S_ISVTX:
        return None                              # a link's own mode means nothing; a sticky folder, see changeable
    if st.st_mode & stat.S_IWOTH:
        return f"anyone can change {path} ({_fix(f'chmod o-w {path}', path, tree, 'chmod -R go-w')})"
    if st.st_mode & stat.S_IWGRP:
        fix = _fix(f"chmod g-w {path}", path, tree, "chmod -R go-w")
        if not _own_group(st.st_gid, me):
            return f"the group {_name(grp.getgrgid, st.st_gid)} can change {path} ({fix})"
        try:
            if _listed_others(path):
                return f"an access list (ACL) on {path} can let others change it ({fix})"
        except OSError as e:
            return f"the access list (ACL) of {path} can't be read ({e.strerror}): it may let others change it ({fix})"
    return None


def _home(path: str, st: os.stat_result, me: int) -> str | None:
    """The name of the account besides root and `me` that owns `path` (its lstat `st`) as its home, which is where its
    account says it is, links followed (final review of branch deferred-minors-2, M2); None when it is no one's."""
    if st.st_uid in (0, me):
        return None
    try:
        owner = pwd.getpwuid(st.st_uid)
    except KeyError:
        return None
    return owner.pw_name if owner.pw_dir and os.path.realpath(owner.pw_dir) == path else None


def _listed_others(path: str) -> bool:
    """Whether `path` has an access list (ACL) beyond its mode, whose group bits are then the most it lets the users
    and groups it names do. Only "none here" and "not supported here" mean it has none; another error reading it is
    raised, so the check fails closed (final review of branch deferred-minors, M6)."""
    try:
        os.getxattr(path, "system.posix_acl_access", follow_symlinks=False)
    except OSError as e:
        if e.errno in (errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP):
            return False
        raise
    return True


def _own_group(gid: int, uid: int) -> bool:
    """Whether `gid` is the private group of the account `uid`: its primary group, named after it, and no other
    account's, whether listed in it or having it as its own primary group (as Debian's sshd judges it). The system's
    accounts are read again after a minute at most."""
    return _private_group(gid, uid, int(time.monotonic() // 60))


@functools.lru_cache(maxsize=64)
def _private_group(gid: int, uid: int, minute: int) -> bool:
    try:
        user, group = pwd.getpwuid(uid), grp.getgrgid(gid)
    except KeyError:
        return False
    if gid != user.pw_gid or group.gr_name != user.pw_name or set(group.gr_mem) - {user.pw_name}:
        return False
    return all(a.pw_gid != gid or a.pw_uid == uid for a in pwd.getpwall())


def _homes(me: int) -> tuple[str, ...]:
    """The homes of the system's accounts besides root and `me`, as their accounts name them (not followed: a home on
    a disk mounted when needed stays unmounted); read again after a minute at most."""
    return _accounts_homes(me, int(time.monotonic() // 60))


@functools.lru_cache(maxsize=8)
def _accounts_homes(me: int, minute: int) -> tuple[str, ...]:
    return tuple({os.path.normpath(a.pw_dir) for a in pwd.getpwall()
                  if a.pw_uid not in (0, me) and a.pw_dir and os.path.normpath(a.pw_dir) != "/"})


_UNJUDGED = object()                             # refusal: no verdict since again()
_said: set[tuple[str, str]] = set()              # refusals the log has had, by workspace and compiler or library


def _say(label: str, what: str, why: str) -> None:
    """Log a refusal once per process for each workspace (final review of branch deferred-minors), naming it (review of
    branch deferred-minors-2): after an upgrade a toolchain that ran before loses its include paths and macros, and
    the log says so as soon as a review or the Health page meets it."""
    if (label, what) not in _said:
        _said.add((label, what))
        log.warning("%s: %s; its Health page says the same", f"workspace {label}" if label else "a workspace", why)


def _dirs(said: str) -> list[str]:
    """The folders in a list gcc prints (-print-search-dirs): `=a:b:c`."""
    return [d for d in said.removeprefix("=").split(":") if os.path.isabs(d)]


def _name(lookup, id_: int) -> str:
    try:
        return lookup(id_)[0]
    except KeyError:
        return str(id_)


class Toolchain:
    """Turns compile entries into libclang arguments, per file: each file's own compiler is queried (once per
    toolchain group and language) for its built-in include paths and macros, and its target is made explicit."""

    def __init__(self, cfg: ToolchainConfig, cdb: CompileDb, work_dir: Path, root: Path | None = None,
                 data_dir: Path | None = None, folders: Iterable[str] | None = None, outside: Iterable[str] = (),
                 label: str = ""):
        self.cfg = cfg
        self.label = label                               # the workspace's name, for the log
        self.cdb = cdb
        self.work_dir = Path(work_dir)
        self.root = canon(str(root)) if root else None
        self.strip: set[str] = set(cfg.strip_flags)
        self.libclang: LibclangInfo | None = None
        self._groups: dict[tuple, Group] = {}
        # reviews' parses add groups while Health page looks count them and judge them again: what reads or changes
        # the groups, or the default library, does so under it (review of branch deferred-minors-2, deferred minor)
        self._lock = threading.RLock()
        self._machines: dict[str, str | None] = {}
        # where fetch-libclang puts libraries: the server's data folder (a workspace's own folder sits below it)
        self.data_dir = Path(data_dir) if data_dir is not None else self.work_dir.parent
        # a workspace added in the UI runs compilers and loads libraries only from these folders
        # (server.toolchain_folders, and the libraries fetch-libclang installed); None for tortoise.yaml's workspace,
        # which isn't held to them (final review I3 of spec 2026-10-31)
        self.folders = None if folders is None else \
            [os.path.realpath(f) for f in [*folders, str(self.data_dir / "libclang")]]
        self.outside = [os.path.realpath(o) for o in outside]    # never toolchain folders: tortoise.yaml's workspace
        self._refuses = self._refused if self.folders is not None else None    # what find_libclang may not load
        self._searched: dict[str, list[str]] = {}    # per compiler: where it looks for what it runs and reads
        self._verdicts: dict[str, str | None] = {}   # per compiler: why others could change it, until again()
        self.choice: LibclangChoice | None = None    # the library this workspace parses with by default
        self._agains = 0                             # again()s so far: a library chosen before one is chosen afresh
        self.samples: dict[tuple, str] = {}          # Health's sample parse per group, once per process

    def _within(self, real: str) -> bool:
        """Whether the real path `real` lies in a toolchain folder (always, for tortoise.yaml's workspace)."""
        return self.folders is None or (any(within(real, f) for f in self.folders)
                                        and not any(within(real, o) for o in self.outside))

    def listed(self, path: str) -> bool:
        """Whether `path` really lies in a toolchain folder, links followed the way the system follows them."""
        return self._within(os.path.realpath(path))

    def _refused(self, real: str) -> str | None:
        """Why a workspace held to the toolchain folders may not run or load the real path `real`: it lies outside
        them, or someone besides root and this server's account can change it (the owner's choice, 2026-11-01)."""
        return changeable(real) if self._within(real) else "outside server.toolchain_folders"

    def _exe(self, driver: str) -> str | None:
        """The file a run of `driver` executes, its name kept as argv[0] (a compiler picks its mode and target from
        it): for a workspace held to the toolchain folders, the real path, resolved and checked as the run starts, so a
        link that moves after not_run can't send the run elsewhere; None (`driver` itself) for tortoise.yaml's."""
        if self.folders is None:
            return None
        real = os.path.realpath(driver)
        if not self._within(real):
            raise PermissionError(f"compiler {driver} is outside the toolchain folders and is not run")
        why = self._unsafe(driver)                       # judged afresh as each run starts
        if why:
            raise PermissionError(f"compiler {driver} is not run: {why}")
        return real

    def _unsafe(self, driver: str) -> str | None:
        """For a workspace held to the toolchain folders: who besides root and this server's account can change
        `driver` — the compiler, or a folder or link on the way to it (gcc finds its programs from the name it is run
        by) — or add or change what it runs or reads where it looks (gcc's cc1, cc1plus and specs, final review I2 of
        branch deferred-minors), and how to stop them; None when no one can, and for tortoise.yaml's workspace."""
        if self.folders is None:
            return None
        tree = self._tree(driver)
        why = changeable(driver, tree=tree)
        if why:
            return why
        for path in self._looks_for(driver):
            why = changeable(path, create=True, tree=tree)
            if why:
                return f"it looks for {path}, and {why}"
        return None

    def _tree(self, driver: str) -> str | None:
        """The folder a compiler's toolchain is installed in, for a fix text that fixes all of it at once: the one above
        the compiler's own bin folder (/opt/tc for /opt/tc/bin/gcc), when it lies inside a toolchain folder and isn't
        one. Never a prefix programs share (/usr, /usr/local: final review of branch deferred-minors-2, I1), nor one
        that is, lies in or holds another account's home (M2), whose files are theirs."""
        own = os.path.dirname(os.path.realpath(driver))
        top = os.path.dirname(own)
        if os.path.basename(own) != "bin" or os.path.basename(top) in ("usr", "local") \
                or not any(within(top, f) and top != f for f in self.folders):
            return None
        if any(within(top, h) or within(h, top) for h in _homes(os.geteuid())):
            return None
        return top

    def _looks_for(self, driver: str) -> list[str]:
        """Where `driver` looks for what a query runs or reads, from the folders it names when asked
        (-print-search-dirs, asked only once `driver` itself has passed changeable): gcc's cc1 and cc1plus in each
        folder it runs programs from, and its specs in its install folder and the folders it reads libraries from,
        and the folder above each; nothing for clang, which runs itself and reads no specs."""
        real = os.path.realpath(driver)
        found = self._searched.get(real)                 # read once: again() may forget them meanwhile
        if found is None:
            try:
                r = subprocess.run([driver, "-print-search-dirs"], executable=real, capture_output=True, text=True,
                                   timeout=30, stdin=subprocess.DEVNULL, env={**os.environ, "LC_ALL": "C"})
                said = dict(line.split(": ", 1) for line in r.stdout.splitlines() if ": " in line) \
                    if r.returncode == 0 else {}
            except (OSError, subprocess.TimeoutExpired):
                said = {}
            found = []
            if "install" in said:                        # gcc: clang says no install folder
                found += [os.path.join(d, p) for d in _dirs(said.get("programs", "")) for p in ("cc1", "cc1plus")]
                for d in [said["install"], *_dirs(said.get("libraries", ""))]:
                    found += [os.path.join(d, "specs"), os.path.join(os.path.dirname(d.rstrip("/")), "specs")]
            found = self._searched[real] = list(dict.fromkeys(found))
        return found

    def again(self) -> None:
        """Judge afresh what others could change, as the Health page looks again (Recheck after a fix): the verdicts
        and the folders each compiler searches are forgotten, a group refused is tried again with its sample, and a
        library chosen in place of one refused is chosen again."""
        with self._lock:
            self._agains += 1
            self._verdicts.clear()
            self._searched.clear()
            if self.choice is not None and self.choice.passed and self._default() != self.choice:
                self.libclang = None                     # prepare() chooses and describes it again
            judged = list(self._groups.items())
        for key, g in judged:                            # compilers may run: reviews go on meanwhile
            own = g.libclang is not None and g.libclang.vendor       # judged as args_for judges it
            changed = g.refused and g.error != (self.refusal(g.compiler) if own else self.not_run(g.compiler))
            if changed:
                g.error, g.refused = None, False
            if g.libclang is not None and g.libclang.passed:
                lib = self._find(compiler=g.compiler, override=key[3])
                changed, g.libclang = changed or lib != g.libclang, lib
            if changed:
                self.samples.pop(key, None)

    def _default(self) -> LibclangChoice:
        return self._find()

    def _find(self, **kw) -> LibclangChoice:
        """find_libclang for this workspace: a library it passes over is said in the log once (final review of branch
        deferred-minors)."""
        choice = find_libclang(self.cfg, data_dir=self.data_dir, refuses=self._refuses, **kw)
        for p in choice.passed:
            _say(self.label, p, f"libclang {p} is passed over")
        return choice

    def prepare(self) -> tuple[LibclangChoice, LibclangInfo]:
        """Idempotent: chooses and describes this workspace's default library (loading it here when the process has no
        other), and returns them: another Health page look may choose it again meanwhile (again()), so a caller uses
        what it returns. Every parse runs in worker processes that load the request's library; compilers are queried
        lazily, per group. Describing may load the library in a worker and wait for it, so it runs outside the lock,
        and a choice an again() overtook meanwhile is made afresh (final review of branch deferred-minors-3, M2)."""
        while True:
            with self._lock:
                if self.libclang is not None:
                    return self.choice, self.libclang
                agains = self._agains
            choice = self._default()
            info = library_info(choice.path)
            with self._lock:
                if self.libclang is None and self._agains == agains:
                    self.choice, self.libclang = choice, info

    # ---- per file
    def _override(self, file: str) -> ToolchainOverride | None:
        rel = file[len(self.root) + 1:] if self.root and file.startswith(self.root + "/") else file
        return next((o for o in self.cfg.overrides if fnmatch.fnmatch(rel, o.match)), None)

    def _entry(self, file: str, ov: ToolchainOverride | None) -> CompileEntry | None:
        if ov is not None and ov.compile_commands is not None:
            hit = self.cdb.entry_for(file, prefer=str(ov.compile_commands))
            if hit is not None and os.path.realpath(hit.db) == os.path.realpath(str(ov.compile_commands)):
                return hit
        return self.cdb.nearest_entry(file)

    def _driver(self, entry: CompileEntry, ov: ToolchainOverride | None) -> str:
        name = (ov.clang if ov and ov.clang else None) or self.cfg.clang or entry.compiler
        if os.path.isabs(name):
            return name
        if "/" in name:
            return os.path.normpath(os.path.join(entry.directory, name))
        return shutil.which(name) or name

    def not_run(self, driver: str) -> str | None:
        """Why `driver` must not be run (toolchain.query_compilers, server.toolchain_folders, who else can change it),
        or None."""
        mode = self.cfg.query_compilers
        if mode == "off":
            return "compiler queries are off (toolchain.query_compilers: off)"
        if not self.listed(driver):
            return self.refusal(driver)
        if mode == "outside_workspace" and self.root and os.path.realpath(driver).startswith(self.root + "/"):
            return (f"compiler {driver} is inside the workspace and is not run "
                    "(set toolchain.query_compilers: all to allow it)")
        return self.refusal(driver)

    def refusal(self, driver: str) -> str | None:
        """Why the toolchain folders keep `driver` from running: it lies outside them, or someone besides root and
        this server's account can change it; None when compiler queries are off, and for tortoise.yaml's workspace. The
        log says it once per compiler. Who else can change it is judged once per compiler until the Health page looks
        again (again()); a run judges it afresh as it starts (_exe)."""
        if self.folders is None or self.cfg.query_compilers == "off":
            return None
        if not self.listed(driver):
            why = (f"compiler {driver} is outside the toolchain folders and is not run "
                   "(server.toolchain_folders in tortoise.yaml lists them)")
        else:
            why = self._verdicts.get(driver, _UNJUDGED)  # read once: again() may forget them meanwhile
            if why is _UNJUDGED:
                unsafe = self._unsafe(driver)
                why = self._verdicts[driver] = f"compiler {driver} is not run: {unsafe}" if unsafe else None
        if why:
            _say(self.label, driver, why)
        return why

    def _machine(self, driver: str) -> str | None:
        if driver in self._machines:                     # asked once: every compile entry comes here
            return self._machines[driver]
        if self.not_run(driver):
            return None
        try:
            r = subprocess.run([driver, "-dumpmachine"], executable=self._exe(driver), capture_output=True,
                               text=True, timeout=30, stdin=subprocess.DEVNULL)
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
        lib_override = ov.libclang if ov else None
        key = (driver, target, flags, lib_override)
        # one group per key, whoever asks first; its library is found under the lock as well (find_libclang may search
        # the toolchain's folders), once per group (final review of branch deferred-minors-3, M2)
        with self._lock:
            g = self._groups.get(key)
            if g is None:
                g = self._groups[key] = Group(compiler=driver, target=target, flags=flags,
                                              libclang=self._find(compiler=driver, override=lib_override))
        return g

    def _query(self, g: Group, lang: str) -> DriverInfo | None:
        if lang in g.info or g.error:
            return g.info.get(lang)
        reason = self.not_run(g.compiler)
        if reason:
            g.error, g.refused = reason, True
            return None
        try:
            info = query_driver(g.compiler, list(g.flags), lang, executable=self._exe(g.compiler))
        except PermissionError as e:                     # refused as the run started
            g.error, g.refused = str(e), True
            return None
        except (RuntimeError, OSError) as e:
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
        own = g.libclang.vendor
        if own and os.path.isfile(g.compiler):
            # libclang runs its driver as a bare "clang": told where the toolchain lives, it finds that toolchain's
            # target headers (<bin>/../target/<arch>/include and the like) the way the compiler does
            args += ["-ccc-install-dir", os.path.dirname(os.path.realpath(g.compiler))]
        # a toolchain's own library still takes the compiler's include paths when it may run (wrappers and config
        # files add some), but not its macros: the library defines them itself. A compiler the toolchain folders
        # refuse is said on the Health page all the same (final review of branch deferred-minors)
        if own and not g.error and (why := self.refusal(g.compiler)):
            g.error, g.refused = why, True
        info = None if own and self.not_run(g.compiler) else self._query(g, lang)
        rd = self.cfg.resource_dir or g.libclang.resource_dir or (info.resource_dir if info else None)
        if rd:
            args += ["-resource-dir", rd]
        if info is not None:
            builtins = [os.path.normpath(r) for r in (rd, info.resource_dir) if r]
            for d in info.include_dirs:      # built-in headers come only from the parsing library's resource dir
                if any(os.path.normpath(d).startswith(b) for b in builtins) or (rd and _GCC_INTERNAL.search(d)):
                    continue
                args += ["-isystem", d]
            if not own:
                args += ["-include", str(g.preludes[lang]), "-Wno-macro-redefined", "-Wno-builtin-macro-redefined"]
        for d in ov.system_include_dirs if ov else ():
            args += ["-isystem", d if os.path.isabs(d) or not self.root else os.path.join(self.root, d)]
        return args

    def explain(self, file: str) -> dict:
        """What `args_for(file)` is built from, for `codetortoise check-parse`."""
        file = canon(file)
        ov = self._override(file)
        entry = self._entry(file, ov)
        if entry is None:
            return {"entry": None}
        args = self.args_for(file)
        g = self.group_of(file)
        others = [e for e in self.cdb._all.get(file, []) if e is not entry]
        return {"entry": entry, "exact": self.cdb.entry_for(file) is not None, "others": others, "override": ov,
                "group": g, "args": args}

    def libclang_for(self, file: str) -> LibclangChoice:
        g = self.group_of(file)
        return g.libclang if g else self._default()

    def group_of(self, file: str) -> Group | None:
        file = canon(file)
        ov = self._override(file)
        entry = self._entry(file, ov)
        return self._group(entry, sanitize_args(entry, self.strip), ov) if entry else None

    def groups(self) -> list[Group]:
        """Every toolchain group in the compile databases, with its file count (queries happen on first use). Counted
        apart from the groups themselves, then set at once, so two looks at a time each count every group."""
        counted: dict[int, tuple[Group, int, str]] = {}
        for e in self.cdb.entries:
            g = self._group(e, sanitize_args(e, self.strip), self._override(e.file))
            _, n, sample = counted.get(id(g), (g, 0, e.file))
            counted[id(g)] = (g, n + 1, sample)
        with self._lock:
            for g, n, sample in counted.values():
                g.files, g.sample = n, sample
            return [g for g in self._groups.values() if id(g) in counted]

    def key_of(self, g: Group) -> tuple:
        with self._lock:
            return next(k for k, v in self._groups.items() if v is g)

    def unmatched_overrides(self) -> list[str]:
        """Overrides whose compile_commands is not one of the loaded databases (so they can never apply)."""
        loaded = {os.path.realpath(db) for db, _ in self.cdb.databases}
        return [f"{o.match}: {o.compile_commands} is not one of the compile databases" for o in self.cfg.overrides
                if o.compile_commands is not None and os.path.realpath(str(o.compile_commands)) not in loaded]
