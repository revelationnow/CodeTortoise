"""Loading libclang: vendor library if configured, else the one bundled with the `libclang` wheel."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass

import clang.cindex as ci

_loaded: LibclangInfo | None = None


@dataclass(frozen=True)
class LibclangInfo:
    path: str
    version: str
    vendor: bool


def _version() -> str:
    fn = ci.conf.lib.clang_getClangVersion
    fn.restype = ci._CXString
    fn.errcheck = ci._CXString.from_result
    return fn()


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
    _loaded = LibclangInfo(path=lib_path, version=_version(), vendor=bool(path))
    return _loaded
