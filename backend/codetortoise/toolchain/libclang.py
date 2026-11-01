"""Loading libclang: vendor library if configured, else the one bundled with the `libclang` wheel."""
from __future__ import annotations

import ctypes
import glob as globmod
import hashlib
import importlib.metadata
import io
import multiprocessing as mp
import os
import platform
import re
import shutil
import signal
import tarfile
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import clang.cindex as ci

_loaded: LibclangInfo | None = None
_lock = threading.Lock()


@dataclass(frozen=True)
class LibclangInfo:
    path: str
    version: str
    vendor: bool


class CXString(ctypes.Structure):
    """libclang's string type; declared here so no private part of the Python bindings is needed."""
    _fields_ = [("data", ctypes.c_void_p), ("flags", ctypes.c_uint)]


_own: ctypes.CDLL | None = None


def _c() -> ctypes.CDLL:
    """Our own handle on the loaded library (the bindings' function objects carry version-specific hooks)."""
    global _own
    if _own is None:
        _own = ctypes.CDLL(ci.conf.get_filename())
        _own.clang_getCString.argtypes, _own.clang_getCString.restype = [CXString], ctypes.c_char_p
        _own.clang_disposeString.argtypes = [CXString]
    return _own


def cx_string(name: str, *args, argtypes: list | None = None) -> str | None:
    """Call a libclang function returning CXString and return it as text (None if the library lacks it)."""
    lib = _c()
    fn = getattr(lib, name, None)
    if fn is None:
        return None
    fn.argtypes, fn.restype = argtypes or [], CXString
    s = fn(*args)
    try:
        raw = lib.clang_getCString(s)
        return raw.decode(errors="replace") if raw else ""
    finally:
        lib.clang_disposeString(s)


def _version() -> str:
    return cx_string("clang_getClangVersion") or "unknown"


def _tolerate_unknown_kinds() -> None:
    """A library newer than the bindings can report kinds the bindings don't know: read them as unexposed."""
    for enum, fallback in ((ci.CursorKind, "UNEXPOSED_EXPR"), (ci.TypeKind, "UNEXPOSED")):
        orig = enum.from_id
        if getattr(orig, "_tolerant", False):
            continue

        def from_id(id, _orig=orig, _enum=enum, _fallback=fallback):
            try:
                return _orig(id)
            except ValueError:
                return getattr(_enum, _fallback)
        from_id._tolerant = True
        enum.from_id = staticmethod(from_id)


def load_libclang(path: str | None) -> LibclangInfo:
    """Idempotent. Must be called before any other clang.cindex use in the process."""
    global _loaded
    if _loaded is not None:
        if path and _loaded.path != path:
            raise RuntimeError(f"libclang already loaded from {_loaded.path}, cannot switch to {path}")
        return _loaded
    if path:
        ci.Config.set_library_file(path)
    lib_path = path or ci.conf.get_filename()
    ctypes.CDLL(lib_path)  # fail early with a clear OSError if unloadable
    _tolerate_unknown_kinds()
    _loaded = LibclangInfo(path=lib_path, version=_version(), vendor=bool(path))
    return _loaded


LIBRARY_INFO_TIMEOUT = 120.0     # seconds a worker may take to load and describe a library


def _describe(path: str | None, out) -> None:
    """In a worker process: load the library and send back its description, or the error loading it raised."""
    try:
        out.send(load_libclang(path))
    except Exception as e:
        out.send(e)
    finally:
        out.close()


def _ended(code: int | None) -> str:
    """How a worker process ended, from its exit code."""
    if code is not None and code < 0:
        try:
            return f"killed by signal {-code}, {signal.Signals(-code).name}"
        except ValueError:
            return f"killed by signal {-code}"
    return f"exit code {code}"


def library_info(path: str | None) -> LibclangInfo:
    """The library a workspace parses with, described: loaded here when this process has none yet (or has this one);
    else described from a worker process, since a process loads one libclang and workspaces may each choose another
    (spec 2026-10-31 §6). Every parse already runs in worker processes that load the request's library."""
    with _lock:
        if _loaded is None:
            return load_libclang(path)
        same = _loaded.path == path if path else not _loaded.vendor
    if same:
        return _loaded
    ctx = mp.get_context("forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn")
    got, out = ctx.Pipe(duplex=False)
    worker = ctx.Process(target=_describe, args=(path, out), daemon=True, name="tortoise-libclang")
    worker.start()
    out.close()                                  # the worker's end: once the worker is gone, reading here ends
    # the worker is ended, so a library whose loading hangs costs the timeout, not the hang (final review M10 of spec
    # 2026-10-31); one whose loading ends the worker is said at once (review of branch minors, M6)
    try:
        if not got.poll(LIBRARY_INFO_TIMEOUT):
            raise TimeoutError(f"libclang {path} took over {LIBRARY_INFO_TIMEOUT:.0f} s to load")
        try:
            answer = got.recv()
        except EOFError:
            worker.join(5)
            raise RuntimeError(f"libclang {path} ended the process loading it ({_ended(worker.exitcode)})") from None
        worker.join(1)                           # it ends once it has answered: killed below only if it doesn't (final
    finally:                                     # review of branch deferred-minors, M7)
        got.close()
        if worker.is_alive():
            worker.kill()
        worker.join()
    if isinstance(answer, Exception):
        raise answer
    return answer


# ---------------------------------------------------------------- choosing a library
SYSTEM_GLOBS = ["/usr/lib/llvm-*/lib", "/usr/lib64/llvm*/lib", "/opt/llvm*/lib"]
_LIB_PATTERNS = ("libclang.so*", "libclang-*.so*")


@dataclass(frozen=True)
class LibclangChoice:
    path: str | None                 # None: the library bundled with the Python bindings
    kind: str                        # explicit | toolchain | search | fetched | system | bundled
    reason: str
    resource_dir: str | None = None  # built-in headers of that library, passed to every parse
    passed: tuple[str, ...] = ()     # libraries passed over, each with why (a workspace added in the UI)

    @property
    def vendor(self) -> bool:
        """A toolchain's own library knows that toolchain: its compiler isn't queried for includes and macros."""
        return self.kind in ("explicit", "toolchain")


def _version_key(p: Path) -> tuple:
    nums = [int(n) for n in re.findall(r"\d+", p.name)] or [int(n) for n in re.findall(r"\d+", str(p.parent.parent))]
    return tuple(nums)


def _major(p: Path) -> int | None:
    """The library's major version, from its name (libclang.so.21, libclang-21.so.1) or its clang/<v> folder."""
    nums = [int(n) for n in re.findall(r"\d+", p.name)]
    if nums:
        return nums[0]
    rd = _resource_dir(p)
    return int(re.findall(r"\d+", Path(rd).name)[0]) if rd and re.findall(r"\d+", Path(rd).name) else None


def bindings_major() -> int:
    """The bindings register every function of their version; a library older than them can't be loaded."""
    try:
        return int(importlib.metadata.version("libclang").split(".")[0])
    except (importlib.metadata.PackageNotFoundError, ValueError):
        return 0


def _usable(p: Path) -> bool:
    major = _major(p)
    return major is None or major >= bindings_major()


def _libs_in(d: Path, deep: bool = False) -> list[Path]:
    """libclang candidates under `d`, newest first (ties by name, so the order never depends on the run).
    libclang-cpp (the C++ library) isn't the C API; libraries older than the bindings are left out."""
    found: set[Path] = set()
    for pat in _LIB_PATTERNS:
        found.update(p for p in (d.rglob(pat) if deep else d.glob(pat))
                     if p.is_file() and not p.name.startswith("libclang-cpp") and _usable(p))
    return sorted(found, key=lambda p: (_version_key(p), p.name), reverse=True)


def _resource_dir(lib: Path) -> str | None:
    dirs = sorted((d for d in (lib.parent / "clang").glob("*") if (d / "include").is_dir()),
                  key=lambda d: [int(n) for n in re.findall(r"\d+", d.name)], reverse=True)
    return str(dirs[0]) if dirs else None


def find_libclang(cfg, compiler: str | None = None, override: str | None = None, data_dir: Path | None = None,
                  system_globs: list[str] | None = None,
                  refuses: Callable[[str], str | None] | None = None) -> LibclangChoice:
    """The library to parse with, in order: an override's or `toolchain.libclang`; one next to a clang compiler (that
    toolchain's own); the newest under `toolchain.search_paths`; one fetched by `codetortoise fetch-libclang`; the
    newest system LLVM; the one bundled with the bindings.

    `refuses` (a workspace added in the UI: server.toolchain_folders, and who can change a library) judges a library by
    its real path, and the choice names that path, so a link that moves later can't change what loads; a library it
    refuses is passed over, and the reason names it and why."""
    passed: list[str] = []

    def pick(hits):
        for h in hits:
            if refuses is None:
                return h
            real = os.path.realpath(h)
            why = refuses(real)
            if why is None:
                return Path(real)
            passed.append(f"{h} ({why})")
        return None

    def chosen(lib, kind: str, reason: str) -> LibclangChoice:
        names = tuple(dict.fromkeys(passed))
        if names:
            reason += ("; not loaded: " + ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else ""))
        return LibclangChoice(None if lib is None else str(lib), kind, reason,
                              None if lib is None else _resource_dir(Path(lib)), names)

    explicit = override or cfg.libclang
    lib = pick([explicit]) if explicit else None
    if lib:
        note = "" if _usable(Path(explicit)) else f"; older than the bindings ({bindings_major()}), it may fail to load"
        return chosen(lib, "explicit", "set in tortoise.yaml" + note)
    if compiler and "clang" in os.path.basename(compiler):
        bindir = Path(compiler).resolve().parent if Path(compiler).exists() else Path(compiler).parent
        for libdir in (bindir.parent / "lib", bindir.parent / "lib64"):
            lib = pick(_libs_in(libdir)) if libdir.is_dir() else None
            if lib:
                return chosen(lib, "toolchain", f"next to {compiler}")
    for sp in getattr(cfg, "search_paths", []) or []:
        lib = pick(_libs_in(Path(sp), deep=True)) if Path(sp).is_dir() else None
        if lib:
            return chosen(lib, "search", f"newest under {sp}")
    if data_dir is not None and (Path(data_dir) / "libclang").is_dir():
        lib = pick(sorted((h for v in (Path(data_dir) / "libclang").iterdir() if v.is_dir() and not v.name.startswith(".")
                           for h in _libs_in(v / "lib")), key=lambda p: (_version_key(p), p.name), reverse=True))
        if lib:
            return chosen(lib, "fetched", "fetched with codetortoise fetch-libclang")
    dirs = [Path(d) for g in (SYSTEM_GLOBS if system_globs is None else system_globs) for d in globmod.glob(g)]
    lib = pick(sorted((h for d in dirs for h in _libs_in(d)), key=lambda p: (_version_key(p), p.name), reverse=True))
    if lib:
        return chosen(lib, "system", f"system LLVM in {lib.parent}")
    return chosen(None, "bundled", "bundled with the Python bindings (no newer library found)")


# ---------------------------------------------------------------- fetching a release
DEFAULT_VERSION = "23.1.2"
RELEASE_URL = "https://github.com/llvm/llvm-project/releases/download/llvmorg-{v}/LLVM-{v}-Linux-{arch}.tar.xz"
PINNED_SHA256 = {   # GitHub's published digests for the release assets
    ("23.1.2", "X64"): "b5ed9675149cc837c282e9b6962c276c9fa62863d5b2f91537b60848552995b7",
    ("23.1.2", "ARM64"): "075da47cb832273717d4c7bad4b6b4848d7c154262e9ba0dcc0025426d4073f0",
}
_KEEP = re.compile(r"^lib/(libclang(\.so[.\d]*|-[\d.]+\.so[.\d]*)|clang/[^/]+/include(/.*)?)$")


class _Hashing(io.RawIOBase):
    """Reads through `raw` while hashing every byte, so the whole download is checked, not only what is kept."""

    def __init__(self, raw):
        self.raw, self.sha = raw, hashlib.sha256()

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        data = self.raw.read(len(b))
        self.sha.update(data)
        b[:len(data)] = data
        return len(data)


def _arch() -> str:
    return "ARM64" if platform.machine().lower() in ("aarch64", "arm64") else "X64"


def fetch_libclang(data_dir: Path, version: str = DEFAULT_VERSION, source: str | None = None,
                   sha256: str | None = None, arch: str | None = None) -> Path:
    """Install the official LLVM release's libclang and built-in headers under <data_dir>/libclang/<version>.

    The release (about 2 GB) is streamed and only `lib/libclang.so*` and `lib/clang/<v>/include` are kept. The whole
    archive is checked against `sha256`, else the digest pinned here, else (when downloading) the one GitHub publishes.
    `source` is a downloaded archive for machines without internet access."""
    arch = arch or _arch()
    url = RELEASE_URL.format(v=version, arch=arch)
    expected = (sha256 or PINNED_SHA256.get((version, arch)) or (None if source else _published_digest(version, arch)))
    if not expected:
        raise RuntimeError(f"no known checksum for LLVM {version} ({arch}); pass --sha256 with the release's digest")
    dest = Path(data_dir) / "libclang" / version
    tmp = Path(data_dir) / "libclang" / f".tmp-{version}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    raw = open(source, "rb") if source else urllib.request.urlopen(url, timeout=60)  # noqa: S310 (fixed https URL)
    try:
        reader = _Hashing(raw)
        with tarfile.open(fileobj=io.BufferedReader(reader, 1 << 20), mode="r|xz") as tar:
            for m in tar:
                parts = m.name.split("/", 1)
                rel = parts[1] if len(parts) == 2 else ""
                if m.name.startswith("/") or ".." in m.name.split("/") or (m.issym() and (
                        m.linkname.startswith("/") or ".." in m.linkname.split("/"))):
                    raise RuntimeError(f"unsafe path in archive: {m.name}")
                if not _KEEP.match(rel) or not (m.isfile() or m.issym() or m.isdir()):
                    continue
                target = tmp / rel
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif m.issym():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(m.linkname)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(m) as fsrc, open(target, "wb") as fdst:
                        shutil.copyfileobj(fsrc, fdst)
        while reader.readinto(bytearray(1 << 20)):          # hash the rest of the archive
            pass
        if reader.sha.hexdigest() != expected.lower():
            raise RuntimeError(f"checksum mismatch for {source or url}: got {reader.sha.hexdigest()}, expected {expected}")
        if not _libs_in(tmp / "lib"):
            raise RuntimeError(f"no libclang in {source or url}")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    finally:
        raw.close()
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    return dest


def _published_digest(version: str, arch: str) -> str | None:
    import json
    api = f"https://api.github.com/repos/llvm/llvm-project/releases/tags/llvmorg-{version}"
    with urllib.request.urlopen(api, timeout=30) as r:  # noqa: S310 (fixed https URL)
        assets = json.load(r).get("assets", [])
    name = f"LLVM-{version}-Linux-{arch}.tar.xz"
    digest = next((a.get("digest", "") for a in assets if a.get("name") == name), "")
    return digest.split(":", 1)[1] if digest.startswith("sha256:") else None
