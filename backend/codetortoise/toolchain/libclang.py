"""Loading libclang: vendor library if configured, else the one bundled with the `libclang` wheel."""
from __future__ import annotations

import ctypes
import glob as globmod
import hashlib
import io
import os
import platform
import re
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import clang.cindex as ci

_loaded: LibclangInfo | None = None


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


# ---------------------------------------------------------------- choosing a library
SYSTEM_GLOBS = ["/usr/lib/llvm-*/lib", "/usr/lib64/llvm*/lib", "/opt/llvm*/lib"]
_LIB_PATTERNS = ("libclang.so*", "libclang-*.so*")


@dataclass(frozen=True)
class LibclangChoice:
    path: str | None                 # None: the library bundled with the Python bindings
    kind: str                        # explicit | toolchain | search | fetched | system | bundled
    reason: str
    resource_dir: str | None = None  # built-in headers of that library, passed to every parse

    @property
    def vendor(self) -> bool:
        """A toolchain's own library knows that toolchain: its compiler isn't queried for includes and macros."""
        return self.kind in ("explicit", "toolchain")


def _version_key(p: Path) -> tuple:
    nums = [int(n) for n in re.findall(r"\d+", p.name)] or [int(n) for n in re.findall(r"\d+", str(p.parent.parent))]
    return tuple(nums)


def _libs_in(d: Path, deep: bool = False) -> list[Path]:
    found: set[Path] = set()
    for pat in _LIB_PATTERNS:
        found.update(p for p in (d.rglob(pat) if deep else d.glob(pat)) if p.is_file())
    return sorted(found, key=_version_key, reverse=True)


def _resource_dir(lib: Path) -> str | None:
    dirs = sorted((d for d in (lib.parent / "clang").glob("*") if (d / "include").is_dir()),
                  key=lambda d: [int(n) for n in re.findall(r"\d+", d.name)], reverse=True)
    return str(dirs[0]) if dirs else None


def find_libclang(cfg, compiler: str | None = None, override: str | None = None, data_dir: Path | None = None,
                  system_globs: list[str] | None = None) -> LibclangChoice:
    """The library to parse with, in order: an override's or `toolchain.libclang`; one next to a clang compiler (that
    toolchain's own); the newest under `toolchain.search_paths`; one fetched by `codetortoise fetch-libclang`; the
    newest system LLVM; the one bundled with the bindings."""
    explicit = override or cfg.libclang
    if explicit:
        return LibclangChoice(explicit, "explicit", "set in tortoise.yaml", _resource_dir(Path(explicit)))
    if compiler and "clang" in os.path.basename(compiler):
        bindir = Path(compiler).resolve().parent if Path(compiler).exists() else Path(compiler).parent
        for libdir in (bindir.parent / "lib", bindir.parent / "lib64"):
            hits = _libs_in(libdir) if libdir.is_dir() else []
            if hits:
                return LibclangChoice(str(hits[0]), "toolchain", f"next to {compiler}", _resource_dir(hits[0]))
    for sp in getattr(cfg, "search_paths", []) or []:
        hits = _libs_in(Path(sp), deep=True) if Path(sp).is_dir() else []
        if hits:
            return LibclangChoice(str(hits[0]), "search", f"newest under {sp}", _resource_dir(hits[0]))
    if data_dir is not None and (Path(data_dir) / "libclang").is_dir():
        hits = sorted((h for v in (Path(data_dir) / "libclang").iterdir() if v.is_dir() and not v.name.startswith(".")
                       for h in _libs_in(v / "lib")), key=_version_key, reverse=True)
        if hits:
            return LibclangChoice(str(hits[0]), "fetched", "fetched with codetortoise fetch-libclang",
                                  _resource_dir(hits[0]))
    dirs = [Path(d) for g in (SYSTEM_GLOBS if system_globs is None else system_globs) for d in globmod.glob(g)]
    hits = sorted((h for d in dirs for h in _libs_in(d)), key=_version_key, reverse=True)
    if hits:
        return LibclangChoice(str(hits[0]), "system", f"system LLVM in {hits[0].parent}", _resource_dir(hits[0]))
    return LibclangChoice(None, "bundled", "bundled with the Python bindings (no newer library found)")


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
