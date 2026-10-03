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
