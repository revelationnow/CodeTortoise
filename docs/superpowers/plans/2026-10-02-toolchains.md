# Toolchains, Compile Databases and Parse Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Files parse with libclang on real production workspaces (wrapped compilers, response files, out-of-tree and nested builds, several targets), with a newer libclang when available, and when one doesn't parse, one command shows why.

**Architecture:** `compile_db.py` reads commands the way the build ran them and merges several databases with a fixed precedence. `toolchain.py` groups files by compiler, target and target flags, queries each group's compiler once, and picks each group's libclang (`libclang.find_libclang`). Parsing runs in worker processes per library. `check-parse`, Health and the `facts` stage message explain the outcome.

**Tech Stack:** Python 3.12, `clang.cindex` from the `libclang` 18.1.1 wheel (kept; newer libraries load through it), ctypes, pytest, ruff. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-02-toolchains-design.md` (spike results in §5).

**Base:** branch `index-scale` (step 1a: batched, compile-DB-scoped, incremental symbol index). Merge it first, or branch from it.

**Provenance:** every code block was run before the plan was written. The tasks were then replayed in order on a fresh tree from `index-scale`: each task's tests failed before its implementation and passed after it, and the suite (ruff and pytest) stayed green after every task. The replayed tree is byte-identical to the validated one. New files are given in full; changes to existing files are unified diffs against the previous task's state (`git apply`, or by hand).

## Global Constraints

- **Compatibility:** a `tortoise.yaml` that works today keeps working; every new setting is optional.
- **Libraries:** the `libclang` wheel stays the dependency and the fallback; no private binding APIs (`ci._CXString`); unknown cursor/type kinds read as `UNEXPOSED_EXPR`/`UNEXPOSED`.
- **Precedence:** a list of databases: first listed wins; `auto`: deepest first; one database listed twice: first entry wins.
- **Library order:** override or `toolchain.libclang` > next to a clang compiler > `toolchain.search_paths` > fetched (`<data_dir>/libclang`) > system LLVM > bundled.
- **Downloads:** `fetch-libclang` defaults to LLVM 23.1.2; the whole archive is checked against `--sha256`, a pinned digest, or GitHub's published digest; nothing is kept on a mismatch or an unsafe archive path.
- **Tests are hermetic:** `tests/conftest.py` empties `SYSTEM_GLOBS`; only tests that opt in use a machine's LLVM.
- **Commits:** end every commit message with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (add it as a second `-m` paragraph to the commands shown).

## Review Focus

Conditions the spec implies that are most likely to bite a real user, most likely first. Each is pinned by a test in the task that owns the code.

1. **A compile command behind a cache wrapper** (`ccache /usr/bin/gcc …`), the likeliest cause of "every file fell back to tree-sitter". Pinned by `test_a_compiler_wrapper_is_skipped` (Task 2), with a real libclang parse.
2. **The build's compiler isn't installed on the review machine:** parsing must go on and the group report the failed query. Pinned by `test_a_compiler_that_cannot_run_is_reported_and_parsing_goes_on` (Task 4).
3. **Two targets in one workspace** must not share macros or headers. Pinned by `test_files_built_by_different_compilers_get_their_own_headers_macros_and_target` (Task 4), with real parses returning different values.
4. **A library newer than the bindings** must not crash on unknown kinds. Pinned by `test_unknown_cursor_and_type_kinds_read_as_unexposed` (Task 1) and the real run `test_files_parse_in_workers_with_a_newer_library` (Task 5; skips without LLVM 21).
5. **A tampered or path-traversing release archive** must leave nothing behind. Pinned by `test_a_checksum_mismatch_keeps_nothing` and `test_unsafe_paths_in_the_archive_are_refused` (Task 5).

---

### Task 1: libclang without private binding APIs; unknown kinds tolerated

Spec §5. Two calls used a private part of the Python bindings (`ci._CXString.from_result`) that changed after
version 18: the libclang version string and the binary-operator spelling in `aliasflow`. They now go through
`libclang.cx_string`, which calls the C library through its own `ctypes` handle and declares `CXString` itself. A
library newer than the bindings can report cursor or type kinds the bindings don't know; `load_libclang` makes
`CursorKind.from_id` and `TypeKind.from_id` read those as `UNEXPOSED_EXPR` / `UNEXPOSED` instead of raising. With both,
the bundled 18.1.1 bindings parse identically with libclang 21 and 23 (the spike).

**Files:**
- Modify: `backend/codetortoise/toolchain/libclang.py`
- Modify: `backend/codetortoise/facts/aliasflow.py`
- Test: `backend/tests/test_libclang_api.py`

**Interfaces:**
- Produces: `toolchain.libclang.CXString`, `cx_string(name, *args, argtypes=None) -> str | None`; unknown-kind tolerance
  installed by `load_libclang`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_libclang_api.py`:

```python
"""libclang C API calls that don't depend on private parts of the Python bindings (they changed after 18)."""
import clang.cindex as ci

from codetortoise.toolchain import libclang


def test_version_and_operator_spelling_without_private_bindings(monkeypatch):
    libclang.load_libclang(None)
    monkeypatch.delattr(ci, "_CXString", raising=False)         # absent or changed in newer bindings
    assert "clang version" in libclang._version()
    from codetortoise.facts import aliasflow
    monkeypatch.setattr(aliasflow, "_capi", None)
    api = aliasflow._c_api()
    assert api["bin_spell"] is not None and api["bin_spell"](22) == "="           # CXBinaryOperator_Assign


def test_unknown_cursor_and_type_kinds_read_as_unexposed():
    libclang.load_libclang(None)                                  # installs the tolerance
    assert ci.CursorKind.from_id(9999) == ci.CursorKind.UNEXPOSED_EXPR
    assert ci.TypeKind.from_id(9999) == ci.TypeKind.UNEXPOSED
    assert ci.CursorKind.from_id(ci.CursorKind.CALL_EXPR.value) == ci.CursorKind.CALL_EXPR
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_libclang_api.py -q`
Expected: FAIL — `2 failed` (`AttributeError: module 'clang.cindex' has no attribute '_CXString'`, `ValueError: Unknown template argument kind 9999`)

- [ ] **Step 3: Implement**

`backend/codetortoise/toolchain/libclang.py` (replace the whole file):

```python
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
```

`backend/codetortoise/facts/aliasflow.py`:

```diff
diff --git a/backend/codetortoise/facts/aliasflow.py b/backend/codetortoise/facts/aliasflow.py
index 59e53f6..f803a31 100644
--- a/backend/codetortoise/facts/aliasflow.py
+++ b/backend/codetortoise/facts/aliasflow.py
@@ -16,6 +16,7 @@ import clang.cindex as ci
 
 from codetortoise.facts.model import FieldAccess, GlobalAccess
 from codetortoise.paths import canon
+from codetortoise.toolchain.libclang import cx_string
 
 K = ci.CursorKind
 T = ci.TypeKind
@@ -114,10 +115,9 @@ def _c_api() -> dict:
 
     api["bin_kind"] = bind("clang_getCursorBinaryOperatorKind", [ci.Cursor], ctypes.c_int)
     api["un_kind"] = bind("clang_getCursorUnaryOperatorKind", [ci.Cursor], ctypes.c_int)
-    spell = bind("clang_getBinaryOperatorKindSpelling", [ctypes.c_int], ci._CXString)
-    if spell is not None:
-        spell.errcheck = ci._CXString.from_result
-    api["bin_spell"] = spell
+    has_spell = getattr(lib, "clang_getBinaryOperatorKindSpelling", None) is not None
+    api["bin_spell"] = ((lambda kind: cx_string("clang_getBinaryOperatorKindSpelling", kind, argtypes=[ctypes.c_int]))
+                        if has_spell else None)
     api["eval"] = bind("clang_Cursor_Evaluate", [ci.Cursor], ctypes.c_void_p)
     api["eval_kind"] = bind("clang_EvalResult_getKind", [ctypes.c_void_p], ctypes.c_int)
     api["eval_unsigned"] = bind("clang_EvalResult_isUnsignedInt", [ctypes.c_void_p], ctypes.c_uint)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_libclang_api.py -q`
Expected: `2 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `257 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/toolchain/libclang.py backend/codetortoise/facts/aliasflow.py backend/tests/test_libclang_api.py
git commit -m "fix(libclang): no private binding APIs; unknown kinds read as unexposed"
```

---

### Task 2: Reading compile commands the way the build ran them

Spec §3. `CompileDb.load` expands `@file` response files (shell rules, recursively, relative to the entry's
`directory`; a missing one is kept and listed in `CompileDb.problems`), drops an `env VAR=x` prefix and build wrappers
(`ccache`, `sccache`, `distcc`, `icecc`, `buildcache`, with a path or `.exe`), and records the real compiler in
`CompileEntry.compiler`. `sanitize_args` starts every argument list with `-working-directory <directory>` so relative
paths resolve as in the build, and for `cl`/`clang-cl` adds `--driver-mode=cl`, drops MSVC output flags and makes `/I`
paths absolute (cl mode ignores the working directory for them). The safe-subset retry keeps the working directory
and driver mode. Tests that compared whole argument lists now expect the working directory first.

**Files:**
- Modify: `backend/codetortoise/toolchain/compile_db.py`
- Modify: `backend/codetortoise/facts/clang_extractor.py`
- Test: `backend/tests/test_compile_commands.py`
- Modify: `backend/tests/test_compile_db.py`
- Modify: `backend/tests/test_driver_toolchain.py`

**Interfaces:**
- Produces: `CompileEntry.compiler: str`; `CompileDb.problems: list[str]`; `compile_db.WRAPPERS`, `is_cl(compiler)`;
  `sanitize_args` output begins `["-working-directory", directory, ...]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_compile_commands.py`:

```python
"""Reading compile commands the way the build ran them: response files, wrappers, cl mode, working directory."""
import json

import pytest

from codetortoise.facts.clang_extractor import TuRequest, extract_tu
from codetortoise.toolchain.compile_db import CompileDb, sanitize_args


def _db(tmp_path, entries):
    p = tmp_path / "compile_commands.json"
    p.write_text(json.dumps(entries))
    return CompileDb.load(p)


def _parse(e):
    return extract_tu(TuRequest(file=e.file, args=sanitize_args(e), variant="after"))


def _src(tmp_path, text='#ifndef FOO\n#error FOO missing\n#endif\n#include "lib.h"\nint f(void) { return LIB; }\n'):
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "inc").mkdir(exist_ok=True)
    (tmp_path / "inc" / "lib.h").write_text("#define LIB 3\n")
    (tmp_path / "src" / "a.c").write_text(text)
    (tmp_path / "build").mkdir(exist_ok=True)
    return str(tmp_path / "build")


@pytest.mark.parametrize("wrapper", ["ccache", "/usr/bin/ccache", "sccache", "distcc", "icecc", "buildcache",
                                     "ccache.exe"])
def test_a_compiler_wrapper_is_skipped(tmp_path, wrapper):
    b = _src(tmp_path)
    db = _db(tmp_path, [{"directory": b, "file": "../src/a.c",
                         "command": f"{wrapper} /usr/bin/gcc -DFOO -I../inc -c ../src/a.c -o a.o"}])
    e = db.entries[0]
    assert e.compiler == "/usr/bin/gcc"
    facts = _parse(e)
    assert facts.tu.confidence == "precise", facts.tu.diagnostics
    assert facts.functions[0].returns == ["3"]


def test_an_env_prefix_is_skipped(tmp_path):
    b = _src(tmp_path)
    e = _db(tmp_path, [{"directory": b, "file": "../src/a.c",
                        "arguments": ["env", "LANG=C", "CCACHE_DIR=/x", "ccache", "gcc", "-DFOO", "-I../inc", "-c",
                                      "../src/a.c"]}]).entries[0]
    assert e.compiler == "gcc" and _parse(e).tu.confidence == "precise"


def test_response_files_are_expanded_relative_to_the_entry_and_recursively(tmp_path):
    b = _src(tmp_path)
    (tmp_path / "build" / "rsp").mkdir()
    (tmp_path / "build" / "rsp" / "defs.rsp").write_text('-DFOO "-DNAME=\\"x y\\""\n@rsp/incs.rsp\n')
    (tmp_path / "build" / "rsp" / "incs.rsp").write_text("-I../inc\n")
    e = _db(tmp_path, [{"directory": b, "file": "../src/a.c",
                        "command": "gcc @rsp/defs.rsp -c ../src/a.c"}]).entries[0]
    assert "-DNAME=\"x y\"" in e.args and not any(a.startswith("@") for a in e.args)
    facts = _parse(e)
    assert facts.tu.confidence == "precise", facts.tu.diagnostics


def test_a_missing_response_file_is_kept_and_reported(tmp_path):
    b = _src(tmp_path)
    db = _db(tmp_path, [{"directory": b, "file": "../src/a.c", "command": "gcc @nope.rsp -c ../src/a.c"}])
    assert "@nope.rsp" in db.entries[0].args
    assert db.problems == [f"response file not found: {b}/nope.rsp (for ../src/a.c)"]


def test_relative_paths_resolve_from_the_entry_directory(tmp_path):
    b = _src(tmp_path)
    e = _db(tmp_path, [{"directory": b, "file": "../src/a.c",
                        "arguments": ["gcc", "-DFOO", "--include-directory=../inc", "-c", "../src/a.c"]}]).entries[0]
    args = sanitize_args(e)
    assert args[:2] == ["-working-directory", b]
    facts = _parse(e)
    assert facts.tu.confidence == "precise", facts.tu.diagnostics


@pytest.mark.parametrize("compiler", ["cl.exe", "cl", "C:/VS/bin/cl.exe", "clang-cl"])
def test_msvc_commands_use_cl_mode(tmp_path, compiler):
    b = _src(tmp_path)
    e = _db(tmp_path, [{"directory": b, "file": "../src/a.c",
                        "arguments": [compiler, "/nologo", "/c", "/DFOO", "/I../inc", "/Fo:a.obj", "/Fdvc.pdb",
                                      "../src/a.c"]}]).entries[0]
    args = sanitize_args(e)
    assert "--driver-mode=cl" in args and not any(a.startswith(("/Fo", "/Fd")) for a in args)
    facts = _parse(e)
    assert facts.tu.confidence == "precise", facts.tu.diagnostics
    assert facts.functions[0].returns == ["3"]
```

`backend/tests/test_compile_db.py`:

```diff
diff --git a/backend/tests/test_compile_db.py b/backend/tests/test_compile_db.py
index ef1836f..d7c3f27 100644
--- a/backend/tests/test_compile_db.py
+++ b/backend/tests/test_compile_db.py
@@ -7,13 +7,14 @@ def test_sanitize_drops_output_and_dep_flags_and_absolutizes_paths():
     e = CompileEntry("/w/src/a.c", "/w/build", (
         "armclang", "--target=arm-none-eabi", "-Iinc", "-I", "../x", "-isystem", "sys", "--sysroot=../sr",
         "-c", "../src/a.c", "-o", "a.o", "-MD", "-MF", "a.d", "-DFOO=1", "-mcpu=cortex-m4", "-Wall"))
-    assert sanitize_args(e) == ["--target=arm-none-eabi", "-I/w/build/inc", "-I", "/w/x", "-isystem", "/w/build/sys",
+    assert sanitize_args(e) == ["-working-directory", "/w/build",
+                                "--target=arm-none-eabi", "-I/w/build/inc", "-I", "/w/x", "-isystem", "/w/build/sys",
                                 "--sysroot=/w/sr", "-DFOO=1", "-mcpu=cortex-m4", "-Wall"]
 
 
 def test_sanitize_strip_list_matches_exact_and_key_value():
     e = CompileEntry("/w/a.c", "/w", ("cc", "-mvendor-x", "--vendor-opt=3", "-O2", "a.c"))
-    assert sanitize_args(e, {"-mvendor-x", "--vendor-opt"}) == ["-O2"]
+    assert sanitize_args(e, {"-mvendor-x", "--vendor-opt"}) == ["-working-directory", "/w", "-O2"]
 
 
 def test_load_command_strings_and_nearest_entry(tmp_path):
@@ -37,7 +38,7 @@ def test_include_dirs_are_canonicalized_through_symlinks(tmp_path):
     e = CompileEntry(str(real / "a.c"), str(tmp_path / "link"),
                      ("cc", "-Iinclude", "-isystem", str(tmp_path / "link/include"), "-c", "a.c"))
     inc = str((real / "include").resolve())
-    assert sanitize_args(e) == [f"-I{inc}", "-isystem", inc]
+    assert sanitize_args(e)[2:] == [f"-I{inc}", "-isystem", inc]
 
 
 def test_new_header_behind_symlinked_include_dir_parses(tmp_path):
@@ -69,5 +70,5 @@ def test_forced_include_resolves_like_gcc(tmp_path):
                      ("cc", "-Igen", "-include", "suite.h", "-include", "local.h", "-imacros", "cfg.h", "-c", "../a.c"))
     build = str((tmp_path / "build").resolve())
     # found in the working directory -> absolute; otherwise left for the -I search chain
-    assert sanitize_args(e) == [f"-I{build}/gen", "-include", "suite.h", "-include", f"{build}/local.h",
+    assert sanitize_args(e)[2:] == [f"-I{build}/gen", "-include", "suite.h", "-include", f"{build}/local.h",
                                 "-imacros", "cfg.h"]
```

`backend/tests/test_driver_toolchain.py`:

```diff
diff --git a/backend/tests/test_driver_toolchain.py b/backend/tests/test_driver_toolchain.py
index 6c7894b..f388412 100644
--- a/backend/tests/test_driver_toolchain.py
+++ b/backend/tests/test_driver_toolchain.py
@@ -40,7 +40,7 @@ def test_args_for_adds_driver_info_when_libclang_is_not_vendor(tmp_path):
     tc.driver["c"] = DriverInfo(("/opt/vendor/lib/clang/17/include", "/opt/vendor/sysroot/usr/include"),
                                 (("__VENDOR__", "1"),), "/opt/vendor/lib/clang/17")
     tc._preludes["c"] = tmp_path / "prelude-c.h"
-    args = tc.args_for("/w/a.c")
+    args = tc.args_for("/w/a.c")[2:]                      # after -working-directory /w
     assert args[:1] == ["--target=arm"]
     assert ["-resource-dir", "/opt/vendor/lib/clang/17"] == args[1:3]
     assert "/opt/vendor/lib/clang/17/include" not in args  # builtin headers come via -resource-dir
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_compile_commands.py tests/test_compile_db.py tests/test_driver_toolchain.py -q`
Expected: FAIL — `20 failed, 8 passed` (no `compiler` attribute, wrappers and response files not handled, no `-working-directory` first)

- [ ] **Step 3: Implement**

`backend/codetortoise/toolchain/compile_db.py`:

```diff
diff --git a/backend/codetortoise/toolchain/compile_db.py b/backend/codetortoise/toolchain/compile_db.py
index 01fa0c0..f385e83 100644
--- a/backend/codetortoise/toolchain/compile_db.py
+++ b/backend/codetortoise/toolchain/compile_db.py
@@ -18,13 +18,58 @@ _DROP = {"-c", "-M", "-MM", "-MD", "-MMD", "-MP", "-MG", "-Werror", "-fcolor-dia
 _SEP_PATH_FLAGS = {"-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros", "--sysroot",
                    "-isysroot", "-F"}
 _JOINED_PATH_FLAGS = ("-isystem", "-iquote", "-idirafter", "-I", "-F")
+# words in front of the real compiler: build caches and distributed compilers
+WRAPPERS = {"ccache", "sccache", "distcc", "icecc", "buildcache"}
+# MSVC output/debug-file flags (joined value, optionally after ':'), dropped like -o
+_CL_OUTPUT = ("/Fo", "/Fd", "/Fe", "/Fp", "/Fa", "/Fm", "/Fr", "/FR", "/FS")
+
+
+def _base(word: str) -> str:
+    """Program name without directory, case or .exe: "C:/VS/bin/cl.exe" -> "cl"."""
+    name = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
+    return name[:-4] if name.endswith(".exe") else name
+
+
+def is_cl(compiler: str) -> bool:
+    return _base(compiler) in ("cl", "clang-cl")
 
 
 @dataclass(frozen=True)
 class CompileEntry:
     file: str
     directory: str
-    args: tuple[str, ...]
+    args: tuple[str, ...]            # args[0] is the compiler (wrappers and response files already resolved)
+    compiler: str = ""
+
+
+def _expand(args: list[str], directory: str, problems: list[str], what: str, depth: int = 0) -> list[str]:
+    """Replace each @file with its words (shell rules), recursively, relative to the entry's directory."""
+    out: list[str] = []
+    for a in args:
+        if a.startswith("@") and len(a) > 1 and depth < 10:
+            path = _abs(directory, a[1:])
+            try:
+                words = shlex.split(Path(path).read_text(errors="replace"))
+            except (OSError, ValueError):
+                problems.append(f"response file not found: {path} (for {what})")
+                out.append(a)
+                continue
+            out += _expand(words, directory, problems, what, depth + 1)
+        else:
+            out.append(a)
+    return out
+
+
+def _compiler_words(args: list[str]) -> list[str]:
+    """Drop an `env VAR=x ...` prefix and build wrappers, so args[0] is the real compiler."""
+    i = 0
+    if args and _base(args[0]) == "env":
+        i = 1
+        while i < len(args) and ("=" in args[i] or args[i].startswith("-")):
+            i += 1
+    while i < len(args) - 1 and _base(args[i]) in WRAPPERS:
+        i += 1
+    return args[i:]
 
 
 def _abs(directory: str, p: str) -> str:
@@ -32,8 +77,9 @@ def _abs(directory: str, p: str) -> str:
 
 
 class CompileDb:
-    def __init__(self, entries: list[CompileEntry]):
+    def __init__(self, entries: list[CompileEntry], problems: list[str] | None = None):
         self.entries = entries
+        self.problems = problems or []           # e.g. response files that could not be read
         self._by_file = {e.file: e for e in entries}
         self._by_dir: dict[str, list[CompileEntry]] = {}
         for e in entries:
@@ -42,12 +88,14 @@ class CompileDb:
     @classmethod
     def load(cls, path: Path) -> CompileDb:
         raw = json.loads(Path(path).read_text())
-        entries = []
+        entries, problems = [], []
         for item in raw:
             directory = item.get("directory", os.path.dirname(str(path)))
             args = item.get("arguments") or shlex.split(item.get("command", ""))
-            entries.append(CompileEntry(canon(_abs(directory, item["file"])), directory, tuple(args)))
-        return cls(entries)
+            args = _compiler_words(_expand(list(args), directory, problems, item["file"]))
+            entries.append(CompileEntry(canon(_abs(directory, item["file"])), directory, tuple(args),
+                                        compiler=args[0] if args else ""))
+        return cls(entries, problems)
 
     def files(self) -> list[str]:
         return list(self._by_file)
@@ -85,9 +133,11 @@ def include_dirs(cdb: CompileDb) -> list[str]:
 
 
 def sanitize_args(entry: CompileEntry, strip: set[str] = frozenset()) -> list[str]:
-    """Compiler argv -> libclang args: drop compiler, output/dep flags, the source file; absolutize paths."""
+    """Compiler argv -> libclang args: drop compiler, output/dep flags, the source file; absolutize paths. Relative
+    paths that remain resolve from the entry's directory (`-working-directory`); MSVC commands use clang's cl mode."""
     args = list(entry.args[1:])
-    out: list[str] = []
+    cl = is_cl(entry.compiler or (entry.args[0] if entry.args else ""))
+    out: list[str] = ["-working-directory", entry.directory] + (["--driver-mode=cl"] if cl else [])
     i = 0
     src = entry.file
     while i < len(args):
@@ -95,7 +145,7 @@ def sanitize_args(entry: CompileEntry, strip: set[str] = frozenset()) -> list[st
         if a in _DROP_WITH_VALUE:
             i += 2
             continue
-        if a in _DROP or a in strip or a.split("=", 1)[0] in strip:
+        if a in _DROP or a in strip or a.split("=", 1)[0] in strip or (cl and (a.startswith(_CL_OUTPUT) or a == "/c")):
             i += 1
             continue
         if not a.startswith("-") and canon(_abs(entry.directory, a)) == src:
@@ -116,7 +166,7 @@ def sanitize_args(entry: CompileEntry, strip: set[str] = frozenset()) -> list[st
         if a.startswith("--sysroot="):
             out.append("--sysroot=" + canon(_abs(entry.directory, a[len("--sysroot="):])))
             continue
-        for flag in _JOINED_PATH_FLAGS:
+        for flag in _JOINED_PATH_FLAGS + (("/I",) if cl else ()):    # cl mode ignores -working-directory for /I
             if a.startswith(flag) and len(a) > len(flag):
                 out.append(flag + canon(_abs(entry.directory, a[len(flag):])))
                 break
```

`backend/codetortoise/facts/clang_extractor.py`:

```diff
diff --git a/backend/codetortoise/facts/clang_extractor.py b/backend/codetortoise/facts/clang_extractor.py
index 3e61cc1..f9eb0c0 100644
--- a/backend/codetortoise/facts/clang_extractor.py
+++ b/backend/codetortoise/facts/clang_extractor.py
@@ -22,9 +22,9 @@ _SCOPE_KINDS = {K.NAMESPACE, K.CLASS_DECL, K.STRUCT_DECL, K.UNION_DECL, K.CLASS_
 _BAD_FLAG = re.compile(r"(?:unknown argument:?|unsupported option) '([^']+)'")
 # flags kept when a TU cannot be created at all with the full argument list
 _SAFE_WITH_VALUE = {"-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros", "-D", "-U", "-x",
-                    "--sysroot", "-isysroot", "-resource-dir"}
+                    "--sysroot", "-isysroot", "-resource-dir", "-working-directory"}
 _SAFE_PREFIXES = ("-I", "-isystem", "-iquote", "-idirafter", "-D", "-U", "-std=", "-x", "--sysroot=", "-f", "-W",
-                  "-nostdinc", "-include", "-imacros")
+                  "-nostdinc", "-include", "-imacros", "--driver-mode=")
 _CMP_OPS = {"==", "!=", "<", ">", "<=", ">="}
 
 
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_compile_commands.py tests/test_compile_db.py tests/test_driver_toolchain.py -q`
Expected: `28 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `272 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/toolchain/compile_db.py backend/codetortoise/facts/clang_extractor.py backend/tests/test_compile_commands.py backend/tests/test_compile_db.py backend/tests/test_driver_toolchain.py
git commit -m "fix(compile-db): expand response files, skip wrappers, cl mode, resolve from the entry directory"
```

---

### Task 3: Several and nested compile databases

Spec §2. `workspace.compile_commands` takes a path, a list of paths or globs, or `auto` (with `workspace.build_root`).
`load_databases` merges them in precedence order: a list's order, or for `auto` the deepest database first. A file
in several databases uses its first entry (`CompileDb.duplicates` counts those whose flags differ); nearest-entry
guessing stays inside the database whose files' common folder contains the file, and with several databases a file
outside all of them gets none. Health lists the databases; `init` writes `auto` when it finds several (a database
reached through a link counts once).

**Files:**
- Modify: `backend/codetortoise/toolchain/compile_db.py`
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/services.py`
- Modify: `backend/codetortoise/health.py`
- Modify: `backend/codetortoise/init_config.py`
- Test: `backend/tests/test_compile_dbs.py`

**Interfaces:**
- Consumes: `CompileEntry.compiler` (Task 2).
- Produces: `WorkspaceConfig.compile_commands: Literal["auto"] | Path | list[Path]`, `WorkspaceConfig.build_root`;
  `CompileEntry.db`; `CompileDb.databases: list[tuple[str, int]]`, `.duplicates`;
  `compile_db.load_databases(spec, root, build_root) -> CompileDb`, `find_databases(top)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_compile_dbs.py`:

```python
"""Several and nested compile databases: one lookup by file, predictable precedence (spec 2026-10-02 toolchains §2)."""
import json

from codetortoise.toolchain.compile_db import load_databases


def _db(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{"directory": str(path.parent), "file": f, "arguments": ["cc", *flags, "-c", f]}
                                for f, flags in entries]))
    return path


def _tree(tmp_path):
    ws = tmp_path / "ws"
    for f in ("app/main.c", "dsp/fir.c", "dsp/iir.c", "dsp/sub/x.c", "lib/util.c"):
        (ws / f).parent.mkdir(parents=True, exist_ok=True)
        (ws / f).write_text("")
    b = tmp_path / "build"
    _db(b / "compile_commands.json", [(str(ws / "app/main.c"), ["-DROOT"]), (str(ws / "dsp/fir.c"), ["-DROOT"])])
    _db(b / "dsp" / "compile_commands.json", [(str(ws / "dsp/fir.c"), ["-DDSP"]), (str(ws / "dsp/iir.c"), ["-DDSP"])])
    return ws, b


def _flag(db, f):
    return [a for a in db.entry_for(f).args if a.startswith("-D")]


def test_auto_finds_every_database_and_the_deepest_wins(tmp_path):
    ws, b = _tree(tmp_path)
    db = load_databases("auto", ws, b)
    assert sorted(p.split("/build")[-1] for p, _ in db.databases) == ["/compile_commands.json", "/dsp/compile_commands.json"]
    assert _flag(db, str(ws / "dsp/fir.c")) == ["-DDSP"]                 # in both: the nested build's command
    assert _flag(db, str(ws / "app/main.c")) == ["-DROOT"] and _flag(db, str(ws / "dsp/iir.c")) == ["-DDSP"]
    assert db.duplicates == 1 and len(db.files()) == 3


def test_a_list_keeps_its_order(tmp_path):
    ws, b = _tree(tmp_path)
    db = load_databases([b / "compile_commands.json", b / "dsp" / "compile_commands.json"], ws, None)
    assert _flag(db, str(ws / "dsp/fir.c")) == ["-DROOT"]                # first listed wins
    db = load_databases([str(b / "**" / "compile_commands.json")], ws, None)
    assert len(db.databases) == 2


def test_a_file_in_no_database_borrows_only_from_its_own_database(tmp_path):
    ws, b = _tree(tmp_path)
    db = load_databases("auto", ws, b)
    near = db.nearest_entry(str(ws / "dsp/sub/x.c"))
    assert near is not None and _flag(db, near.file) == ["-DDSP"]       # the dsp database, not the root one
    assert db.nearest_entry("/elsewhere/z.c") is None                    # several databases: no cross-build guess


def test_one_database_and_auto_without_a_build_root(tmp_path):
    ws, b = _tree(tmp_path)
    one = load_databases(b / "compile_commands.json", ws, None)
    assert len(one.databases) == 1 and one.nearest_entry("/elsewhere/z.h") is not None   # as before
    (ws / "build").mkdir()
    _db(ws / "build" / "compile_commands.json", [(str(ws / "lib/util.c"), ["-DIN_TREE"])])
    assert [p.split("/ws")[-1] for p, _ in load_databases("auto", ws, None).databases] == ["/build/compile_commands.json"]
    assert load_databases(tmp_path / "missing.json", ws, None).entries == []


def test_config_accepts_a_path_a_list_or_auto(tmp_path):
    from codetortoise.config import load_config
    cfg = tmp_path / "t.yaml"
    for value, expected in [("cc.json", tmp_path / "cc.json"), ("auto", "auto"),
                            (["a.json", "/abs/b.json"], [tmp_path / "a.json", "/abs/b.json"])]:
        cfg.write_text(json.dumps({"owner": "o", "workspace": {"vcs": "git", "root": str(tmp_path),
                                                               "compile_commands": value, "build_root": "build"}}))
        ws = load_config(cfg, env={}).workspace
        got = ws.compile_commands if not isinstance(ws.compile_commands, list) else [str(p) for p in ws.compile_commands]
        assert got == (expected if not isinstance(expected, list) else [str(p) for p in expected])
        assert ws.build_root == tmp_path / "build"


def test_init_writes_auto_when_it_finds_several_databases(tmp_path):
    from codetortoise.init_config import render, scan
    ws, b = _tree(tmp_path)
    (ws / "build").symlink_to(b)                        # the workspace's build folder holds both databases
    text = render(scan(ws, {}, client_root=lambda p, c: None))
    assert "  compile_commands: auto" in text and f"  build_root: {ws / 'build'}" in text


def test_health_lists_the_databases_and_duplicates(tmp_path):
    from codetortoise.config import Config
    from codetortoise.health import run_health
    from codetortoise.services import build_services
    ws, b = _tree(tmp_path)
    cfg = Config.model_validate({"owner": "o", "workspace": {"vcs": "git", "root": str(ws), "compile_commands": "auto",
                                                             "build_root": str(b)},
                                 "server": {"data_dir": str(tmp_path / "d")}})
    check = next(c for c in run_health(build_services(cfg)).checks if c.name == "compile_commands")
    assert check.ok and "3 files from 2 database(s)" in check.detail
    assert "1 file(s) listed again with different flags" in check.detail
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_compile_dbs.py -q`
Expected: FAIL — `ImportError: cannot import name 'load_databases'` (collection stops: `1 error`)

- [ ] **Step 3: Implement**

`backend/codetortoise/toolchain/compile_db.py`:

```diff
diff --git a/backend/codetortoise/toolchain/compile_db.py b/backend/codetortoise/toolchain/compile_db.py
index f385e83..8fff6da 100644
--- a/backend/codetortoise/toolchain/compile_db.py
+++ b/backend/codetortoise/toolchain/compile_db.py
@@ -1,6 +1,7 @@
 """compile_commands.json loading and libclang argument sanitation."""
 from __future__ import annotations
 
+import glob as globmod
 import json
 import os
 import shlex
@@ -40,6 +41,7 @@ class CompileEntry:
     directory: str
     args: tuple[str, ...]            # args[0] is the compiler (wrappers and response files already resolved)
     compiler: str = ""
+    db: str = ""                     # the compile_commands.json it came from
 
 
 def _expand(args: list[str], directory: str, problems: list[str], what: str, depth: int = 0) -> list[str]:
@@ -77,25 +79,36 @@ def _abs(directory: str, p: str) -> str:
 
 
 class CompileDb:
+    """Compile entries by source file, from one or more databases listed in precedence order.
+
+    A file in several databases (or listed twice) uses its first entry; `duplicates` counts those whose other entries
+    differ. A file in no database borrows the nearest entry of the database whose files' common folder contains it,
+    never one from another database.
+    """
+
     def __init__(self, entries: list[CompileEntry], problems: list[str] | None = None):
-        self.entries = entries
         self.problems = problems or []           # e.g. response files that could not be read
-        self._by_file = {e.file: e for e in entries}
-        self._by_dir: dict[str, list[CompileEntry]] = {}
+        self._by_file: dict[str, CompileEntry] = {}
+        self.duplicates = 0
         for e in entries:
-            self._by_dir.setdefault(os.path.dirname(e.file), []).append(e)
+            first = self._by_file.setdefault(e.file, e)
+            if first is not e and first.args[1:] != e.args[1:]:
+                self.duplicates += 1
+        self.entries = list(self._by_file.values())
+        self.databases: list[tuple[str, int]] = []           # (path, entries used from it), precedence order
+        self._dbs: dict[str, tuple[str, dict[str, list[CompileEntry]]]] = {}   # db -> (files' common folder, by dir)
+        for e in self.entries:
+            root, by_dir = self._dbs.setdefault(e.db, (os.path.dirname(e.file), {}))
+            by_dir.setdefault(os.path.dirname(e.file), []).append(e)
+            if not (os.path.dirname(e.file) + "/").startswith(root.rstrip("/") + "/"):
+                root = os.path.commonpath([root, os.path.dirname(e.file)])
+            self._dbs[e.db] = (root, by_dir)
+        self.databases = [(db, sum(len(v) for v in by_dir.values())) for db, (_, by_dir) in self._dbs.items() if db]
 
     @classmethod
     def load(cls, path: Path) -> CompileDb:
-        raw = json.loads(Path(path).read_text())
-        entries, problems = [], []
-        for item in raw:
-            directory = item.get("directory", os.path.dirname(str(path)))
-            args = item.get("arguments") or shlex.split(item.get("command", ""))
-            args = _compiler_words(_expand(list(args), directory, problems, item["file"]))
-            entries.append(CompileEntry(canon(_abs(directory, item["file"])), directory, tuple(args),
-                                        compiler=args[0] if args else ""))
-        return cls(entries, problems)
+        problems: list[str] = []
+        return cls(_read(Path(path), problems), problems)
 
     def files(self) -> list[str]:
         return list(self._by_file)
@@ -104,19 +117,76 @@ class CompileDb:
         return self._by_file.get(canon(file))
 
     def nearest_entry(self, file: str) -> CompileEntry | None:
-        """Exact entry, else an entry in the same directory, else the one sharing the longest path prefix."""
+        """Exact entry, else one in the same folder, else the nearest folder up, within the file's own database."""
         file = canon(file)
         if file in self._by_file:
             return self._by_file[file]
+        owners = [(len(root), db) for db, (root, _) in self._dbs.items()
+                  if (file + "/").startswith(root.rstrip("/") + "/")]
+        if owners:
+            by_dir = self._dbs[max(owners)[1]][1]
+        elif len(self._dbs) == 1:                # one database: as before, its nearest entry anywhere
+            by_dir = next(iter(self._dbs.values()))[1]
+        else:
+            return None
         d = os.path.dirname(file)
         while True:
-            if d in self._by_dir:
-                return self._by_dir[d][0]
+            if d in by_dir:
+                return by_dir[d][0]
             parent = os.path.dirname(d)
             if parent == d:
                 break
             d = parent
-        return self.entries[0] if self.entries else None
+        return next(iter(by_dir.values()))[0] if by_dir else None
+
+
+def _read(path: Path, problems: list[str]) -> list[CompileEntry]:
+    entries = []
+    for item in json.loads(path.read_text()):
+        directory = item.get("directory", os.path.dirname(str(path)))
+        args = item.get("arguments") or shlex.split(item.get("command", ""))
+        args = _compiler_words(_expand(list(args), directory, problems, item["file"]))
+        entries.append(CompileEntry(canon(_abs(directory, item["file"])), directory, tuple(args),
+                                    compiler=args[0] if args else "", db=str(path)))
+    return entries
+
+
+SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".svn", ".tortoise"}
+
+
+def find_databases(top: Path) -> list[Path]:
+    """Every compile_commands.json under `top` (hidden folders skipped), deepest first."""
+    found = []
+    for dirpath, dirnames, filenames in os.walk(top):
+        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
+        if "compile_commands.json" in filenames:
+            found.append(Path(dirpath) / "compile_commands.json")
+    return sorted(found, key=lambda p: (-len(p.parts), str(p)))
+
+
+def load_databases(spec, root: Path, build_root: Path | None) -> CompileDb:
+    """`workspace.compile_commands`: one path, a list of paths or globs (first listed wins), or "auto" (every database
+    under `build_root`, deepest first; without one, under the folder of the first database `codetortoise init` would
+    find). Missing files are skipped."""
+    if spec == "auto":
+        if build_root is None:
+            from codetortoise.init_config import _compile_dbs
+            first = _compile_dbs(Path(root))
+            build_root = first[0].parent if first else None
+        paths = find_databases(Path(build_root)) if build_root is not None else []
+    else:
+        paths = []
+        for item in spec if isinstance(spec, list) else [spec]:
+            text = str(item)
+            hits = sorted(Path(p) for p in globmod.glob(text, recursive=True)) if any(c in text for c in "*?[") \
+                else [Path(text)]
+            paths += [p for p in hits if p not in paths]
+    entries: list[CompileEntry] = []
+    problems: list[str] = []
+    for p in paths:
+        if p.is_file():
+            entries += _read(p, problems)
+    return CompileDb(entries, problems)
 
 
 def include_dirs(cdb: CompileDb) -> list[str]:
```

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index e1db8a1..b41f1bf 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -23,7 +23,8 @@ class WorkspaceConfig(BaseModel):
     p4port: str | None = None
     client: str | None = None
     root: Path
-    compile_commands: Path
+    compile_commands: Literal["auto"] | Path | list[Path]   # a path, a list of paths/globs, or every one under build_root
+    build_root: Path | None = None
     p4_bin: str = "p4"
     p4_sources: dict[str, str] = Field(default_factory=dict)   # where p4port, client and owner came from (set on load)
 
@@ -116,7 +117,13 @@ def load_config(path: Path, env: Mapping[str, str] | None = None) -> Config:
             raise ConfigError(f"{label} is not set: not in tortoise.yaml, {where}, and {var} is not in the environment")
         setattr(obj, attr, value)
         ws.p4_sources[attr] = p4.source(var) or ""
-    ws.compile_commands = (base / ws.compile_commands).resolve() if not ws.compile_commands.is_absolute() else ws.compile_commands
+    def rel(p: Path) -> Path:
+        return p if p.is_absolute() else (base / p).resolve()
+    if isinstance(ws.compile_commands, list):
+        ws.compile_commands = [rel(p) for p in ws.compile_commands]
+    elif ws.compile_commands != "auto":
+        ws.compile_commands = rel(ws.compile_commands)
+    ws.build_root = rel(ws.build_root) if ws.build_root is not None else None
     if not cfg.server.data_dir.is_absolute():
         cfg.server.data_dir = (base / cfg.server.data_dir).resolve()
     srv = cfg.server
```

`backend/codetortoise/services.py`:

```diff
diff --git a/backend/codetortoise/services.py b/backend/codetortoise/services.py
index a64d59d..8cfbe58 100644
--- a/backend/codetortoise/services.py
+++ b/backend/codetortoise/services.py
@@ -14,7 +14,7 @@ from codetortoise.llm.client import LlmClient
 from codetortoise.llm.storyboard import name_layers
 from codetortoise.store import Store
 from codetortoise.swarm import SwarmClient
-from codetortoise.toolchain.compile_db import CompileDb, include_dirs
+from codetortoise.toolchain.compile_db import CompileDb, include_dirs, load_databases
 from codetortoise.toolchain.toolchain import Toolchain
 from codetortoise.vcs.gitfixture import GitFixtureSource
 from codetortoise.vcs.p4runner import P4Runner
@@ -106,7 +106,7 @@ def build_services(cfg: Config, llm: LlmClient | None = None, source: Source | N
     data.mkdir(parents=True, exist_ok=True)
     store = Store(data / "tortoise.db")
     index = SymbolIndex(data / "symbols.db")
-    cdb = CompileDb.load(cfg.workspace.compile_commands) if cfg.workspace.compile_commands.exists() else CompileDb([])
+    cdb = load_databases(cfg.workspace.compile_commands, cfg.workspace.root, cfg.workspace.build_root)
     tc = Toolchain(cfg.toolchain, cdb, data / "toolchain")
     tc.strip.update(store.kv_get(f"strip_flags:{cfg.workspace.root}") or [])
     llm = llm if llm is not None else make_llm(cfg)
```

`backend/codetortoise/health.py`:

```diff
diff --git a/backend/codetortoise/health.py b/backend/codetortoise/health.py
index ea1815d..a3299db 100644
--- a/backend/codetortoise/health.py
+++ b/backend/codetortoise/health.py
@@ -40,8 +40,14 @@ def run_health(svc: Services) -> HealthReport:
                                 detail=f"client {ws.client} Root={root}" + ("" if ok else f" (config root {ws.root})")))
         except P4Error as e:
             checks.append(Check(name="p4 client", ok=False, hard=True, detail=str(e)))
-    checks.append(Check(name="compile_commands", ok=bool(svc.cdb.entries), hard=True,
-                        detail=f"{len(svc.cdb.entries)} entries in {ws.compile_commands}"))
+    dbs = svc.cdb.databases
+    detail = (f"{len(svc.cdb.entries)} files from {len(dbs)} database(s): "
+              + "; ".join(f"{p} ({n})" for p, n in dbs) if dbs else f"no compile database found ({ws.compile_commands})")
+    if svc.cdb.duplicates:
+        detail += f"; {svc.cdb.duplicates} file(s) listed again with different flags (the first entry is used)"
+    if svc.cdb.problems:
+        detail += f"; {len(svc.cdb.problems)} problem(s), e.g. {svc.cdb.problems[0]}"
+    checks.append(Check(name="compile_commands", ok=bool(svc.cdb.entries), hard=True, detail=detail))
     try:
         svc.toolchain.prepare()
         lc = svc.toolchain.libclang
```

`backend/codetortoise/init_config.py`:

```diff
diff --git a/backend/codetortoise/init_config.py b/backend/codetortoise/init_config.py
index b370074..dbfc814 100644
--- a/backend/codetortoise/init_config.py
+++ b/backend/codetortoise/init_config.py
@@ -39,7 +39,7 @@ def _inside(path: Path, parent: Path) -> bool:
 
 def _walk(top: Path, depth0: int) -> list[tuple[int, Path]]:
     found = []
-    for dirpath, dirnames, filenames in os.walk(top):
+    for dirpath, dirnames, filenames in os.walk(top, followlinks=True):     # depth-limited, so links are safe
         depth = depth0 + len(Path(dirpath).relative_to(top).parts)
         dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS) if depth < MAX_DEPTH else []
         if "compile_commands.json" in filenames:
@@ -53,7 +53,8 @@ def _compile_dbs(root: Path) -> list[Path]:
     for side in sorted(root.parent.iterdir()) if root.parent != root else []:
         if side != root and side.is_dir() and side.name.lower().startswith(("build", "out", "_build", "cmake-build")):
             found += [(d + 1, p) for d, p in _walk(side, 1)]
-    return [p for _, p in sorted(found)]
+    seen: set[str] = set()                      # the same database reached through a link counts once
+    return [p for _, p in sorted(found) if not (os.path.realpath(p) in seen or seen.add(os.path.realpath(p)))]
 
 
 def _compiler(db: Path) -> str | None:
@@ -128,10 +129,13 @@ def render(s: Scan) -> str:
     if s.root_guessed:
         out.append("  # check: guessed from where the P4CONFIG file is; it must equal the client's Root (p4 client -o)\n")
     out.append(f"  root: {s.root}\n")
-    if s.compile_dbs:
+    if len(s.compile_dbs) > 1:
+        top = Path(os.path.commonpath([str(d.parent) for d in s.compile_dbs]))
+        out.append("  compile_commands: auto           # every compile_commands.json under build_root; the deepest wins\n")
+        out.append(f"  build_root: {top}\n")
+        out += [f"  #   found: {d}\n" for d in s.compile_dbs]
+    elif s.compile_dbs:
         out.append(f"  compile_commands: {s.compile_dbs[0]}\n")
-        for other in s.compile_dbs[1:]:
-            out.append(f"  # compile_commands: {other}   # also found; pick the one for the build you review\n")
     else:
         out.append(f"  # compile_commands:   # check: compile_commands.json not found under {s.root}; "
                    "generate it (see the README) and put its path here\n")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_compile_dbs.py -q`
Expected: `7 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `279 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/toolchain/compile_db.py backend/codetortoise/config.py backend/codetortoise/services.py backend/codetortoise/health.py backend/codetortoise/init_config.py backend/tests/test_compile_dbs.py
git commit -m "feat(compile-db): several and nested compile databases with predictable precedence"
```

---

### Task 4: Per-file compiler and target, toolchain groups, path overrides

Spec §3.5, §4, §6. `Toolchain` no longer queries one compiler for everything: each entry's own compiler (or
`toolchain.clang`, or an override's `clang`) is queried lazily, once per group of compiler, target and target flags,
and per language; its prelude file is named per group. The target comes from the command, an override,
`toolchain.target`, the compiler's name (`arm-none-eabi-gcc`), or `-dumpmachine`. `toolchain.overrides` match
workspace-relative globs (the toolchain gets the workspace root) and can pin a database (`CompileDb.entry_for(file,
prefer=db)`), compiler, target or library. Health shows one warning-level check per group.

**Files:**
- Modify: `backend/codetortoise/toolchain/toolchain.py`
- Modify: `backend/codetortoise/toolchain/compile_db.py`
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/services.py`
- Modify: `backend/codetortoise/health.py`
- Test: `backend/tests/test_toolchain_groups.py`
- Modify: `backend/tests/test_driver_toolchain.py`

**Interfaces:**
- Consumes: `CompileEntry.compiler`, `.db` (Tasks 2-3).
- Produces: `config.ToolchainOverride {match, compile_commands, clang, target, libclang}`,
  `ToolchainConfig.target`, `.overrides`; `toolchain.Group {compiler, target, flags, files, error, info, preludes}`,
  `triple_from_name(compiler)`; `Toolchain(cfg, cdb, work_dir, root=None)`, `.groups()`, `.group_of(file)`;
  `CompileDb.entry_for(file, prefer=None)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_toolchain_groups.py`:

```python
"""Each file uses its own compiler and target (spec 2026-10-02 toolchains §3.5, §4, §6)."""
import json
import os
import stat

from codetortoise.config import ToolchainConfig
from codetortoise.facts.clang_extractor import TuRequest, extract_tu
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.toolchain import Toolchain

DRIVER = """#!/bin/sh
echo "$0 $*" >> "{log}"
for a in "$@"; do
  case "$a" in
    -dumpmachine) echo "{machine}"; exit 0;;
    -print-resource-dir) exit 1;;
  esac
done
echo '#define {macro} 1'
echo '#include <...> search starts here:' >&2
echo ' {inc}' >&2
echo 'End of search list.' >&2
"""


def _driver(tmp_path, name, macro, machine=""):
    inc = tmp_path / f"sys-{macro}"
    inc.mkdir(exist_ok=True)
    (inc / "board.h").write_text(f"#define BOARD_NAME_{macro} 1\n")
    p = tmp_path / "bin" / name
    p.parent.mkdir(exist_ok=True)
    p.write_text(DRIVER.format(log=tmp_path / "calls.log", machine=machine, macro=macro, inc=inc))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


SRC = ('#include <board.h>\nint which(void) {\n#if defined(BOARD_A) && defined(BOARD_NAME_BOARD_A)\n  return 1;\n'
       '#elif defined(BOARD_B) && defined(BOARD_NAME_BOARD_B)\n  return 2;\n#else\n  return 0;\n#endif\n}\n')


def _workspace(tmp_path, entries):
    ws = tmp_path / "ws"
    for f in ("m4/a.c", "m4/b.c", "dsp/c.c"):
        (ws / f).parent.mkdir(parents=True, exist_ok=True)
        (ws / f).write_text(SRC)
    cc = ws / "compile_commands.json"
    cc.write_text(json.dumps([{"directory": str(ws), "file": f, "arguments": [c, *flags, "-c", f]} for f, c, flags in entries]))
    return ws, load_databases(cc, ws, None)


def _which(tc, path):
    facts = extract_tu(TuRequest(file=str(path), args=tc.args_for(str(path)), variant="after"))
    assert facts.tu.extractor == "clang", facts.tu.diagnostics
    return facts.functions[0].returns


def test_files_built_by_different_compilers_get_their_own_headers_macros_and_target(tmp_path):
    arm = _driver(tmp_path, "arm-none-eabi-gcc", "BOARD_A")
    dsp = _driver(tmp_path, "dspcc", "BOARD_B", machine="riscv32-unknown-elf")
    ws, db = _workspace(tmp_path, [("m4/a.c", arm, ["-mcpu=cortex-m4"]), ("m4/b.c", arm, ["-mcpu=cortex-m4"]),
                                   ("dsp/c.c", dsp, [])])
    tc = Toolchain(ToolchainConfig(), db, tmp_path / "work")
    tc.prepare()
    a, c = tc.args_for(str(ws / "m4/a.c")), tc.args_for(str(ws / "dsp/c.c"))
    assert "--target=arm-none-eabi" in a                                  # from the compiler's name
    assert "--target=riscv32-unknown-elf" in c                            # from -dumpmachine
    assert _which(tc, ws / "m4/a.c") == ["1"] and _which(tc, ws / "dsp/c.c") == ["2"]
    tc.args_for(str(ws / "m4/b.c"))
    queries = [line for line in (tmp_path / "calls.log").read_text().splitlines() if "-dM" in line]
    assert len(queries) == 2                                              # one query per toolchain group and language
    groups = {g.compiler.split("/")[-1]: g for g in tc.groups()}
    assert groups["arm-none-eabi-gcc"].files == 2 and groups["dspcc"].target == "riscv32-unknown-elf"


def test_a_target_in_the_command_wins_and_settings_override_the_rest(tmp_path):
    arm = _driver(tmp_path, "arm-none-eabi-gcc", "BOARD_A")
    ws, db = _workspace(tmp_path, [("m4/a.c", arm, ["--target=thumbv7em-none-eabi"]), ("m4/b.c", arm, []),
                                   ("dsp/c.c", arm, [])])
    tc = Toolchain(ToolchainConfig(target="armv7m-none-eabi",
                                   overrides=[{"match": "dsp/**", "target": "hexagon"}]), db, tmp_path / "w", root=ws)
    tc.prepare()
    a = tc.args_for(str(ws / "m4/a.c"))
    assert "--target=thumbv7em-none-eabi" in a and sum(x.startswith("--target") for x in a) == 1
    assert "--target=armv7m-none-eabi" in tc.args_for(str(ws / "m4/b.c"))
    assert "--target=hexagon" in tc.args_for(str(ws / "dsp/c.c"))


def test_the_clang_setting_and_an_override_replace_the_entry_compiler(tmp_path):
    arm = _driver(tmp_path, "arm-none-eabi-gcc", "BOARD_A")
    vendor = _driver(tmp_path, "vendor-clang", "BOARD_B", machine="x86_64-pc-linux-gnu")
    ws, db = _workspace(tmp_path, [("m4/a.c", arm, []), ("m4/b.c", arm, []), ("dsp/c.c", arm, [])])
    tc = Toolchain(ToolchainConfig(overrides=[{"match": "dsp/**", "clang": vendor}]), db, tmp_path / "w", root=ws)
    tc.prepare()
    assert _which(tc, ws / "m4/a.c") == ["1"] and _which(tc, ws / "dsp/c.c") == ["2"]
    everything = Toolchain(ToolchainConfig(clang=vendor), db, tmp_path / "w2")
    everything.prepare()
    assert _which(everything, ws / "m4/a.c") == ["2"]


def test_a_compiler_that_cannot_run_is_reported_and_parsing_goes_on(tmp_path):
    ws, db = _workspace(tmp_path, [("m4/a.c", "/no/such/arm-none-eabi-gcc", []), ("m4/b.c", "/no/such/arm-none-eabi-gcc", []),
                                   ("dsp/c.c", "/no/such/arm-none-eabi-gcc", [])])
    tc = Toolchain(ToolchainConfig(), db, tmp_path / "w")
    tc.prepare()
    args = tc.args_for(str(ws / "m4/a.c"))
    assert "--target=arm-none-eabi" in args                               # the name still names the target
    [g] = tc.groups()
    assert g.error and "driver query failed" in g.error and g.files == 3
    assert os.path.basename(g.compiler) == "arm-none-eabi-gcc"


def test_an_override_can_pin_the_database_for_its_paths(tmp_path):
    arm = _driver(tmp_path, "arm-none-eabi-gcc", "BOARD_A")
    ws, root_db = _workspace(tmp_path, [("m4/a.c", arm, []), ("m4/b.c", arm, []), ("dsp/c.c", arm, ["-DFROM_ROOT"])])
    dsp_cc = ws / "dsp" / "compile_commands.json"
    dsp_cc.write_text(json.dumps([{"directory": str(ws), "file": "dsp/c.c", "arguments": [arm, "-DFROM_DSP", "-c", "dsp/c.c"]}]))
    db = load_databases([ws / "compile_commands.json", dsp_cc], ws, None)    # the root database is listed first
    plain = Toolchain(ToolchainConfig(), db, tmp_path / "w", root=ws)
    assert "-DFROM_ROOT" in plain.args_for(str(ws / "dsp/c.c"))
    pinned = Toolchain(ToolchainConfig(overrides=[{"match": "dsp/**", "compile_commands": str(dsp_cc)}]), db,
                       tmp_path / "w2", root=ws)
    assert "-DFROM_DSP" in pinned.args_for(str(ws / "dsp/c.c"))
```

`backend/tests/test_driver_toolchain.py`:

```diff
diff --git a/backend/tests/test_driver_toolchain.py b/backend/tests/test_driver_toolchain.py
index f388412..c3f81d4 100644
--- a/backend/tests/test_driver_toolchain.py
+++ b/backend/tests/test_driver_toolchain.py
@@ -34,18 +34,19 @@ def test_query_real_driver():
     assert info.include_dirs and any(name == "__STDC__" or name == "__GNUC__" for name, _ in info.defines)
 
 
-def test_args_for_adds_driver_info_when_libclang_is_not_vendor(tmp_path):
-    db = CompileDb([CompileEntry("/w/a.c", "/w", ("vcc", "--target=arm", "-c", "a.c"))])
+def test_args_for_adds_driver_info_when_libclang_is_not_vendor(tmp_path, monkeypatch):
+    from codetortoise.toolchain import toolchain as tcmod
+    db = CompileDb([CompileEntry("/w/a.c", "/w", ("vcc", "--target=arm", "-c", "a.c"), compiler="vcc")])
     tc = Toolchain(ToolchainConfig(clang="/opt/vendor/bin/clang"), db, tmp_path)
-    tc.driver["c"] = DriverInfo(("/opt/vendor/lib/clang/17/include", "/opt/vendor/sysroot/usr/include"),
-                                (("__VENDOR__", "1"),), "/opt/vendor/lib/clang/17")
-    tc._preludes["c"] = tmp_path / "prelude-c.h"
+    monkeypatch.setattr(tcmod, "query_driver", lambda driver, flags, lang: DriverInfo(
+        ("/opt/vendor/lib/clang/17/include", "/opt/vendor/sysroot/usr/include"), (("__VENDOR__", "1"),),
+        "/opt/vendor/lib/clang/17"))
     args = tc.args_for("/w/a.c")[2:]                      # after -working-directory /w
-    assert args[:1] == ["--target=arm"]
+    assert args[:1] == ["--target=arm"]                   # the command's own target, nothing added
     assert ["-resource-dir", "/opt/vendor/lib/clang/17"] == args[1:3]
     assert "/opt/vendor/lib/clang/17/include" not in args  # builtin headers come via -resource-dir
     assert ["-isystem", "/opt/vendor/sysroot/usr/include"] == args[3:5]
-    assert args[5:7] == ["-include", str(tmp_path / "prelude-c.h")]
+    assert args[5] == "-include" and args[6].startswith(str(tmp_path / "prelude-"))
 
 
 def test_prepare_loads_bundled_libclang(tmp_path):
@@ -64,7 +65,8 @@ def test_prelude_skips_compiler_identity_macros(tmp_path, monkeypatch):
     db = CompileDb([CompileEntry("/w/a.c", "/w", ("vcc", "-c", "a.c"))])
     tc = Toolchain(ToolchainConfig(clang="/opt/v/bin/vcc"), db, tmp_path)
     tc.prepare()
-    prelude = (tmp_path / "prelude-c.h").read_text()
+    tc.args_for("/w/a.c")                                  # compilers are queried on first use
+    prelude = tc.group_of("/w/a.c").preludes["c"].read_text()
     assert "__ARM_ARCH 7" in prelude and "__VENDOR_CHIP__ 1" in prelude and "__SIZEOF_LONG__ 4" in prelude
     for name in ("__GNUC__", "__GNUC_MINOR__", "__clang_major__", "__VERSION__", "__STDC_VERSION__", "__GCC_HAVE"):
         assert name not in prelude
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_toolchain_groups.py tests/test_driver_toolchain.py -q`
Expected: FAIL — `7 failed, 4 passed` (no target added, one compiler for every file, overrides ignored)

- [ ] **Step 3: Implement**

`backend/codetortoise/toolchain/toolchain.py` (replace the whole file):

```python
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
```

`backend/codetortoise/toolchain/compile_db.py`:

```diff
diff --git a/backend/codetortoise/toolchain/compile_db.py b/backend/codetortoise/toolchain/compile_db.py
index 8fff6da..f2bcd63 100644
--- a/backend/codetortoise/toolchain/compile_db.py
+++ b/backend/codetortoise/toolchain/compile_db.py
@@ -89,8 +89,10 @@ class CompileDb:
     def __init__(self, entries: list[CompileEntry], problems: list[str] | None = None):
         self.problems = problems or []           # e.g. response files that could not be read
         self._by_file: dict[str, CompileEntry] = {}
+        self._all: dict[str, list[CompileEntry]] = {}
         self.duplicates = 0
         for e in entries:
+            self._all.setdefault(e.file, []).append(e)
             first = self._by_file.setdefault(e.file, e)
             if first is not e and first.args[1:] != e.args[1:]:
                 self.duplicates += 1
@@ -113,8 +115,14 @@ class CompileDb:
     def files(self) -> list[str]:
         return list(self._by_file)
 
-    def entry_for(self, file: str) -> CompileEntry | None:
-        return self._by_file.get(canon(file))
+    def entry_for(self, file: str, prefer: str | None = None) -> CompileEntry | None:
+        """The file's entry; with `prefer`, the entry from that database when it has one."""
+        file = canon(file)
+        if prefer is not None:
+            hit = next((e for e in self._all.get(file, []) if e.db == str(prefer)), None)
+            if hit is not None:
+                return hit
+        return self._by_file.get(file)
 
     def nearest_entry(self, file: str) -> CompileEntry | None:
         """Exact entry, else one in the same folder, else the nearest folder up, within the file's own database."""
```

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index b41f1bf..ee9d70b 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -29,8 +29,18 @@ class WorkspaceConfig(BaseModel):
     p4_sources: dict[str, str] = Field(default_factory=dict)   # where p4port, client and owner came from (set on load)
 
 
+class ToolchainOverride(BaseModel):
+    match: str                       # glob on the workspace-relative source path, e.g. "dsp/**"
+    compile_commands: Path | None = None   # use this database's entry for matching files
+    clang: str | None = None         # compiler to query for built-in includes and macros
+    target: str | None = None        # e.g. "hexagon"
+    libclang: str | None = None
+
+
 class ToolchainConfig(BaseModel):
-    clang: str | None = None
+    clang: str | None = None         # query this compiler for every file (default: each entry's own compiler)
+    target: str | None = None        # target for files whose command names none (default: from the compiler)
+    overrides: list[ToolchainOverride] = Field(default_factory=list)
     libclang: str | None = None
     resource_dir: str | None = None
     strip_flags: list[str] = Field(default_factory=list)
```

`backend/codetortoise/services.py`:

```diff
diff --git a/backend/codetortoise/services.py b/backend/codetortoise/services.py
index 8cfbe58..5c61c7b 100644
--- a/backend/codetortoise/services.py
+++ b/backend/codetortoise/services.py
@@ -107,7 +107,7 @@ def build_services(cfg: Config, llm: LlmClient | None = None, source: Source | N
     store = Store(data / "tortoise.db")
     index = SymbolIndex(data / "symbols.db")
     cdb = load_databases(cfg.workspace.compile_commands, cfg.workspace.root, cfg.workspace.build_root)
-    tc = Toolchain(cfg.toolchain, cdb, data / "toolchain")
+    tc = Toolchain(cfg.toolchain, cdb, data / "toolchain", root=cfg.workspace.root)
     tc.strip.update(store.kv_get(f"strip_flags:{cfg.workspace.root}") or [])
     llm = llm if llm is not None else make_llm(cfg)
     p4 = None
```

`backend/codetortoise/health.py`:

```diff
diff --git a/backend/codetortoise/health.py b/backend/codetortoise/health.py
index a3299db..8e9b9bb 100644
--- a/backend/codetortoise/health.py
+++ b/backend/codetortoise/health.py
@@ -1,6 +1,8 @@
 """Startup validation. Hard checks gate review creation."""
 from __future__ import annotations
 
+import os
+
 from pydantic import BaseModel
 
 from codetortoise.paths import canon
@@ -55,10 +57,14 @@ def run_health(svc: Services) -> HealthReport:
                             detail=f"{lc.version} ({'vendor' if lc.vendor else 'bundled'}) {lc.path}"))
     except (OSError, RuntimeError) as e:
         checks.append(Check(name="libclang", ok=False, hard=True, detail=str(e)))
-    if cfg.toolchain.clang:
-        err = svc.toolchain.driver_error
-        checks.append(Check(name="driver query", ok=err is None, hard=False,
-                            detail=err or f"langs: {sorted(svc.toolchain.driver)}"))
+    for g in svc.toolchain.groups():          # one compiler query per toolchain group (warning only)
+        if not (svc.toolchain.libclang and svc.toolchain.libclang.vendor):
+            sample = next((e.file for e in svc.cdb.entries if svc.toolchain.group_of(e.file) is g), None)
+            if sample:
+                svc.toolchain.args_for(sample)
+        checks.append(Check(name=f"toolchain {os.path.basename(g.compiler)}", ok=g.error is None, hard=False,
+                            detail=f"{g.files} file(s), target {g.target or 'from the command or host'}"
+                                   + (f": {g.error}" if g.error else "")))
     if svc.llm is not None:
         checks.append(Check(name="llm endpoint", ok=svc.llm.ping(), hard=False, detail=cfg.llm.base_url or ""))
     else:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_toolchain_groups.py tests/test_driver_toolchain.py -q`
Expected: `11 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `284 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/toolchain/toolchain.py backend/codetortoise/toolchain/compile_db.py backend/codetortoise/config.py backend/codetortoise/services.py backend/codetortoise/health.py backend/tests/test_toolchain_groups.py backend/tests/test_driver_toolchain.py
git commit -m "feat(toolchain): per-file compiler and target, toolchain groups, path overrides"
```

---

### Task 5: Finding a newer libclang, fetch-libclang, a library per group

Spec §5. `find_libclang` picks, in order: an override's or `toolchain.libclang`; one next to a clang compiler; the
newest under `toolchain.search_paths`; one installed by `fetch-libclang` under `<data_dir>/libclang`; the newest
system LLVM; the bundled one. It returns the library's resource directory, passed to every parse. The first two are
"vendor" (their compiler isn't queried). `fetch_libclang` streams the official LLVM release (23.1.2 by default),
keeps only `lib/libclang.so*` and `lib/clang/<v>/include`, refuses unsafe archive paths, and checks the whole archive
against `--sha256`, a pinned digest or GitHub's published one. Each group carries its library; requests carry it
(`TuRequest.libclang`) and the facts stage runs each library's requests in workers that load it. Tests never pick up
the machine's system LLVM (`conftest.py` empties the search) except one real run that skips without LLVM 21.

**Files:**
- Modify: `backend/codetortoise/toolchain/libclang.py`
- Modify: `backend/codetortoise/toolchain/toolchain.py`
- Modify: `backend/codetortoise/config.py`
- Modify: `backend/codetortoise/facts/clang_extractor.py`
- Modify: `backend/codetortoise/facts/runner.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/health.py`
- Modify: `backend/codetortoise/cli.py`
- Test: `backend/tests/test_libclang_discovery.py`
- Test: `backend/tests/test_libclang_groups.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `Group`, `Toolchain.group_of` (Task 4).
- Produces: `libclang.LibclangChoice {path, kind, reason, resource_dir, vendor}`, `find_libclang(cfg, compiler=None,
  override=None, data_dir=None, system_globs=None)`, `fetch_libclang(data_dir, version, source=None, sha256=None,
  arch=None) -> Path`, `SYSTEM_GLOBS`, `DEFAULT_VERSION`, `PINNED_SHA256`; `ToolchainConfig.search_paths`;
  `Toolchain.choice`, `.libclang_for(file)`, `Group.libclang`; `TuRequest.libclang`; CLI `fetch-libclang`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_libclang_discovery.py`:

```python
"""Which libclang each file uses, and fetching a newer one (spec 2026-10-02 toolchains §5)."""
import hashlib
import io
import tarfile

import pytest

from codetortoise.config import ToolchainConfig
from codetortoise.toolchain.libclang import fetch_libclang, find_libclang


def _lib(path, version="21"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    (path.parent / "clang" / version / "include").mkdir(parents=True, exist_ok=True)
    return path


def test_discovery_order_and_reasons(tmp_path):
    vendor = _lib(tmp_path / "vendor" / "lib" / "libclang.so.17")
    (tmp_path / "vendor" / "bin").mkdir()
    (tmp_path / "vendor" / "bin" / "clang").write_text("")
    search = tmp_path / "tools"
    _lib(search / "llvm-19" / "lib" / "libclang.so.19.1.0", "19")
    _lib(search / "llvm-22" / "lib" / "libclang.so.22.1.1", "22")
    fetched = _lib(tmp_path / "data" / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2", "23")
    system = _lib(tmp_path / "usr" / "lib" / "llvm-20" / "lib" / "libclang-20.so.1", "20")
    systems = [str(tmp_path / "usr" / "lib" / "llvm-*" / "lib")]
    explicit = _lib(tmp_path / "x" / "libclang.so")

    def find(cfg, compiler=None, override=None):
        return find_libclang(cfg, compiler=compiler, override=override, data_dir=tmp_path / "data", system_globs=systems)

    c = find(ToolchainConfig(libclang=str(explicit)), compiler=str(tmp_path / "vendor/bin/clang"))
    assert (c.path, c.kind) == (str(explicit), "explicit")
    c = find(ToolchainConfig(), compiler=str(tmp_path / "vendor/bin/clang"))
    assert (c.path, c.kind) == (str(vendor), "toolchain") and "next to" in c.reason
    c = find(ToolchainConfig(search_paths=[str(search)]), compiler="/usr/bin/gcc")       # gcc ships no libclang
    assert c.path.endswith("libclang.so.22.1.1") and c.kind == "search"                 # newest in the search paths
    assert c.resource_dir == str(search / "llvm-22" / "lib" / "clang" / "22")
    c = find(ToolchainConfig())
    assert (c.path, c.kind) == (str(fetched), "fetched")
    (tmp_path / "data" / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2").unlink()
    c = find(ToolchainConfig())
    assert (c.path, c.kind) == (str(system), "system")
    c = find_libclang(ToolchainConfig(), data_dir=tmp_path / "none", system_globs=[])
    assert (c.path, c.kind, c.resource_dir) == (None, "bundled", None) and "bundled" in c.reason
    c = find(ToolchainConfig(libclang=str(explicit)), override=str(vendor))
    assert (c.path, c.kind) == (str(vendor), "explicit")                                  # an override's library


def _tarball(tmp_path, top="LLVM-23.1.2-Linux-X64"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name, data in [(f"{top}/lib/libclang.so.23.1.2", b"ELF"), (f"{top}/lib/clang/23/include/stddef.h", b"x"),
                           (f"{top}/bin/clang-23", b"big"), (f"{top}/lib/libLLVM.so", b"big")]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(f"{top}/lib/libclang.so")
        link.type, link.linkname = tarfile.SYMTYPE, "libclang.so.23.1.2"
        tar.addfile(link)
    p = tmp_path / f"{top}.tar.xz"
    p.write_bytes(buf.getvalue())
    return p, hashlib.sha256(buf.getvalue()).hexdigest()


def test_fetch_from_a_file_keeps_only_libclang_and_its_headers(tmp_path):
    tar, digest = _tarball(tmp_path)
    dest = fetch_libclang(tmp_path / "data", version="23.1.2", source=str(tar), sha256=digest)
    assert dest == tmp_path / "data" / "libclang" / "23.1.2"
    kept = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file() or p.is_symlink())
    assert kept == ["lib/clang/23/include/stddef.h", "lib/libclang.so", "lib/libclang.so.23.1.2"]


def test_a_checksum_mismatch_keeps_nothing(tmp_path):
    tar, _ = _tarball(tmp_path)
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        fetch_libclang(tmp_path / "data", version="23.1.2", source=str(tar), sha256="0" * 64)
    assert not (tmp_path / "data" / "libclang" / "23.1.2").exists()


def test_an_unknown_file_needs_a_checksum(tmp_path):
    tar, _ = _tarball(tmp_path)
    with pytest.raises(RuntimeError, match="--sha256"):
        fetch_libclang(tmp_path / "data", version="9.9.9", source=str(tar))


def test_unsafe_paths_in_the_archive_are_refused(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        info = tarfile.TarInfo("LLVM-23.1.2-Linux-X64/lib/../../../evil/libclang.so.1")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    p = tmp_path / "evil.tar.xz"
    p.write_bytes(buf.getvalue())
    with pytest.raises(RuntimeError, match="unsafe path"):
        fetch_libclang(tmp_path / "data", version="23.1.2", source=str(p), sha256=hashlib.sha256(buf.getvalue()).hexdigest())
    assert not (tmp_path / "evil").exists()


def test_the_fetch_command_installs_from_a_file(tmp_path, capsys):
    import yaml

    from codetortoise.cli import main
    tar, digest = _tarball(tmp_path)
    cfg = tmp_path / "t.yaml"
    cfg.write_text(yaml.safe_dump({"owner": "o", "workspace": {"vcs": "git", "root": str(tmp_path), "compile_commands": "x"},
                                   "server": {"data_dir": str(tmp_path / "data")}}))
    assert main(["fetch-libclang", "--config", str(cfg), "--from", str(tar), "--sha256", digest]) == 0
    assert (tmp_path / "data" / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2").exists()
    assert "installed libclang 23.1.2" in capsys.readouterr().out
    assert main(["fetch-libclang", "--config", str(cfg), "--from", str(tar), "--sha256", "0" * 64]) == 1


SYSTEM21 = "/usr/lib/llvm-21/lib/libclang-21.so.1"


@pytest.mark.skipif(not __import__("os").path.exists(SYSTEM21), reason="needs a system LLVM 21")
def test_files_parse_in_workers_with_a_newer_library(fx):
    from codetortoise.facts.clang_extractor import TuRequest
    from codetortoise.facts.runner import run_extraction
    from codetortoise.toolchain.compile_db import CompileDb, sanitize_args
    db = CompileDb.load(fx.compile_commands)
    reqs = [TuRequest(file=e.file, args=sanitize_args(e) + ["-resource-dir", "/usr/lib/llvm-21/lib/clang/21"],
                      variant="after", libclang=SYSTEM21) for e in db.entries]
    facts = run_extraction(reqs, SYSTEM21, workers=2)
    assert len(facts) == len(reqs) and all(f.tu.extractor == "clang" and f.tu.confidence == "precise" for f in facts)
    assert sum(len(f.functions) for f in facts) == 13
```

`backend/tests/test_libclang_groups.py`:

```python
"""Each toolchain group parses with its own library, given that library's built-in headers."""
import json

from codetortoise.config import ToolchainConfig, ToolchainOverride
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.toolchain import Toolchain


def _ws(tmp_path):
    ws = tmp_path / "ws"
    for f in ("m4/a.c", "dsp/c.c"):
        (ws / f).parent.mkdir(parents=True, exist_ok=True)
        (ws / f).write_text("int f(void) { return 0; }\n")
    cc = ws / "compile_commands.json"
    cc.write_text(json.dumps([{"directory": str(ws), "file": f, "arguments": ["/no/cc", "-c", f]}
                              for f in ("m4/a.c", "dsp/c.c")]))
    return ws, load_databases(cc, ws, None)


def _fake_lib(root, version):
    lib = root / "lib" / f"libclang.so.{version}"
    (root / "lib" / "clang" / version.split(".")[0] / "include").mkdir(parents=True)
    lib.write_bytes(b"")
    return lib


def test_an_override_gives_its_files_their_own_library_and_resource_dir(tmp_path):
    ws, db = _ws(tmp_path)
    hexlib = _fake_lib(tmp_path / "hexagon", "19.1.0")
    tc = Toolchain(ToolchainConfig(overrides=[{"match": "dsp/**", "libclang": str(hexlib)}]), db, tmp_path / "d" / "tc",
                   root=ws)
    tc.prepare()                                                     # loads the default (bundled) library here
    assert tc.libclang_for(str(ws / "m4/a.c")).kind == "bundled"
    dsp = tc.libclang_for(str(ws / "dsp/c.c"))
    assert (dsp.path, dsp.kind) == (str(hexlib), "explicit")
    args = tc.args_for(str(ws / "dsp/c.c"))
    assert args[args.index("-resource-dir") + 1] == str(tmp_path / "hexagon" / "lib" / "clang" / "19")
    assert "-resource-dir" not in tc.args_for(str(ws / "m4/a.c"))      # the bundled library finds its own


def test_a_fetched_library_is_used_and_its_resource_dir_passed(tmp_path):
    ws, db = _ws(tmp_path)
    fetched = _fake_lib(tmp_path / "d" / "libclang" / "23.1.2", "23.1.2")
    tc = Toolchain(ToolchainConfig(), db, tmp_path / "d" / "tc", root=ws)
    choice = tc.libclang_for(str(ws / "m4/a.c"))
    assert (choice.path, choice.kind) == (str(fetched), "fetched")
    args = tc.args_for(str(ws / "m4/a.c"))
    assert args[args.index("-resource-dir") + 1] == str(tmp_path / "d" / "libclang" / "23.1.2" / "lib" / "clang" / "23")


def test_the_facts_stage_runs_each_librarys_files_in_their_own_workers(fx, tmp_path, monkeypatch):
    from codetortoise import pipeline
    from tests.helpers import make_services
    svc = make_services(fx, tmp_path)
    lib = _fake_lib(tmp_path / "vendor", "17.0.6")
    svc.cfg.toolchain.overrides = [ToolchainOverride(match="driver/**", libclang=str(lib))]
    calls = []
    real = pipeline.run_extraction

    def spy(reqs, libclang_path, workers, *a, **k):
        calls.append((libclang_path, sorted(r.file.split("/")[-1] for r in reqs)))
        return real(reqs, None, workers, *a, **k) if libclang_path is None else []
    monkeypatch.setattr(pipeline, "run_extraction", spy)
    rid = svc.store.create_review("t", "owner", [101])
    pipeline.run_review(rid, svc)
    libs = {path for path, _ in calls}
    assert libs == {None, str(lib)}
    assert all(files == ["uart.c"] for path, files in calls if path == str(lib))
```

`backend/tests/conftest.py`:

```diff
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
index 59188c3..9cbef57 100644
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -9,11 +9,15 @@ from codetortoise.fixture import build_fixture
 from codetortoise.impact import build_impact
 from codetortoise.index.symbols import SymbolIndex
 from codetortoise.layers import infer_layers
+from codetortoise.toolchain import libclang as _libclang
 from codetortoise.toolchain.compile_db import CompileDb
 from codetortoise.toolchain.toolchain import Toolchain
 from codetortoise.tu_select import select_tus
 from codetortoise.vcs.gitfixture import GitFixtureSource
 
+# hermetic: never pick up whatever system LLVM the machine running the tests has; tests opt in explicitly
+_libclang.SYSTEM_GLOBS = []
+
 
 @pytest.fixture(scope="session")
 def fx(tmp_path_factory):
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_libclang_discovery.py tests/test_libclang_groups.py -q`
Expected: FAIL — `ImportError: cannot import name 'fetch_libclang'` (collection stops: `1 error`)

- [ ] **Step 3: Implement**

`backend/codetortoise/toolchain/libclang.py` (replace the whole file):

```python
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
```

`backend/codetortoise/toolchain/toolchain.py`:

```diff
diff --git a/backend/codetortoise/toolchain/toolchain.py b/backend/codetortoise/toolchain/toolchain.py
index 2e25871..c698e8d 100644
--- a/backend/codetortoise/toolchain/toolchain.py
+++ b/backend/codetortoise/toolchain/toolchain.py
@@ -14,7 +14,7 @@ from codetortoise.config import ToolchainConfig, ToolchainOverride
 from codetortoise.paths import canon
 from codetortoise.toolchain.compile_db import CompileDb, CompileEntry, sanitize_args
 from codetortoise.toolchain.driver import DriverInfo, query_driver, target_flags
-from codetortoise.toolchain.libclang import LibclangInfo, load_libclang
+from codetortoise.toolchain.libclang import LibclangChoice, LibclangInfo, find_libclang, load_libclang
 
 _CXX_EXTS = {".cc", ".cpp", ".cxx", ".c++", ".hpp", ".hh", ".hxx"}
 
@@ -41,6 +41,7 @@ class Group:
     flags: tuple[str, ...]
     files: int = 0
     error: str | None = None
+    libclang: LibclangChoice | None = None
     info: dict[str, DriverInfo] = field(default_factory=dict)
     preludes: dict[str, Path] = field(default_factory=dict)
 
@@ -76,11 +77,15 @@ class Toolchain:
         self.libclang: LibclangInfo | None = None
         self._groups: dict[tuple, Group] = {}
         self._machines: dict[str, str | None] = {}
+        self.data_dir = self.work_dir.parent          # where fetch-libclang puts libraries
+        self.choice: LibclangChoice | None = None    # the library this process loads
 
     def prepare(self) -> None:
-        """Idempotent: loads libclang. Compilers are queried lazily, per group."""
+        """Idempotent: loads this process's library (the default choice). Groups that need another library are parsed
+        in worker processes that load it; compilers are queried lazily, per group."""
         if self.libclang is None:
-            self.libclang = load_libclang(self.cfg.libclang)
+            self.choice = find_libclang(self.cfg, data_dir=self.data_dir)
+            self.libclang = load_libclang(self.choice.path)
 
     # ---- per file
     def _override(self, file: str) -> ToolchainOverride | None:
@@ -119,9 +124,11 @@ class Toolchain:
             target = ((ov.target if ov else None) or self.cfg.target or triple_from_name(entry.compiler)
                       or triple_from_name(driver) or self._machine(driver))
         flags = tuple(target_flags(args))
-        key = (driver, target, flags)
+        lib_override = ov.libclang if ov else None
+        key = (driver, target, flags, lib_override)
         if key not in self._groups:
-            self._groups[key] = Group(compiler=driver, target=target, flags=flags)
+            lib = find_libclang(self.cfg, compiler=driver, override=lib_override, data_dir=self.data_dir)
+            self._groups[key] = Group(compiler=driver, target=target, flags=flags, libclang=lib)
         return self._groups[key]
 
     def _query(self, g: Group, lang: str) -> DriverInfo | None:
@@ -151,19 +158,23 @@ class Toolchain:
         if g.target:
             args += [f"--target={g.target}"]
         lang = lang_of(entry.file)
-        vendor = self.libclang is not None and self.libclang.vendor
-        info = None if vendor else self._query(g, lang)
+        info = None if g.libclang.vendor else self._query(g, lang)
+        rd = self.cfg.resource_dir or g.libclang.resource_dir or (info.resource_dir if info else None)
+        if rd:
+            args += ["-resource-dir", rd]
         if info is not None:
-            rd = self.cfg.resource_dir or info.resource_dir
-            if rd:
-                args += ["-resource-dir", rd]
-            for d in info.include_dirs:
-                if rd and os.path.normpath(d).startswith(os.path.normpath(rd)):
+            builtins = [os.path.normpath(r) for r in (rd, info.resource_dir) if r]
+            for d in info.include_dirs:      # built-in headers come only from the parsing library's resource dir
+                if any(os.path.normpath(d).startswith(b) for b in builtins):
                     continue
                 args += ["-isystem", d]
             args += ["-include", str(g.preludes[lang]), "-Wno-macro-redefined", "-Wno-builtin-macro-redefined"]
         return args
 
+    def libclang_for(self, file: str) -> LibclangChoice:
+        g = self.group_of(file)
+        return g.libclang if g else find_libclang(self.cfg, data_dir=self.data_dir)
+
     def group_of(self, file: str) -> Group | None:
         file = canon(file)
         ov = self._override(file)
```

`backend/codetortoise/config.py`:

```diff
diff --git a/backend/codetortoise/config.py b/backend/codetortoise/config.py
index ee9d70b..f400cb2 100644
--- a/backend/codetortoise/config.py
+++ b/backend/codetortoise/config.py
@@ -42,6 +42,7 @@ class ToolchainConfig(BaseModel):
     target: str | None = None        # target for files whose command names none (default: from the compiler)
     overrides: list[ToolchainOverride] = Field(default_factory=list)
     libclang: str | None = None
+    search_paths: list[str] = Field(default_factory=list)   # folders to search for a newer libclang
     resource_dir: str | None = None
     strip_flags: list[str] = Field(default_factory=list)
 
```

`backend/codetortoise/facts/clang_extractor.py`:

```diff
diff --git a/backend/codetortoise/facts/clang_extractor.py b/backend/codetortoise/facts/clang_extractor.py
index f9eb0c0..cca37ea 100644
--- a/backend/codetortoise/facts/clang_extractor.py
+++ b/backend/codetortoise/facts/clang_extractor.py
@@ -35,6 +35,7 @@ class TuRequest:
     variant: str
     unsaved: dict[str, str] = field(default_factory=dict)
     focus: list[str] = field(default_factory=list)
+    libclang: str | None = None      # the library to parse with (None: bundled); requests are grouped by it
 
 
 def _norm(path: str) -> str:
```

`backend/codetortoise/facts/runner.py`:

```diff
diff --git a/backend/codetortoise/facts/runner.py b/backend/codetortoise/facts/runner.py
index 4eb9d17..d6426d8 100644
--- a/backend/codetortoise/facts/runner.py
+++ b/backend/codetortoise/facts/runner.py
@@ -36,7 +36,8 @@ def build_requests(sel: TuSelection, cs: ChangeSet, tc: Toolchain, variant: str)
             continue
         if variant == "before" and any(f.local == tu and f.action == "add" for f in cs.files):
             continue
-        reqs.append(TuRequest(file=tu, args=tc.args_for(tu), variant=variant, unsaved=unsaved, focus=focus))
+        reqs.append(TuRequest(file=tu, args=tc.args_for(tu), variant=variant, unsaved=unsaved, focus=focus,
+                              libclang=tc.libclang_for(tu).path))
     return reqs
 
 
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 674eaed..92f150c 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -164,11 +164,17 @@ def run_review(rid: int, svc: Services) -> None:
         store.put_blob(rid, "layers", model)
         return f"{len(model.layers)} layer(s)"
 
+    def extract(reqs):
+        """Each library's requests run in workers that load that library (spec 2026-10-02 toolchains §5)."""
+        out = []
+        for lib in sorted({r.libclang for r in reqs}, key=lambda p: p or ""):
+            out += run_extraction([r for r in reqs if r.libclang == lib], lib, cfg.analysis.workers)
+        return out
+
     def facts():
         svc.toolchain.prepare()
-        lib = svc.toolchain.libclang.path if svc.toolchain.libclang and svc.toolchain.libclang.vendor else None
-        before = run_extraction(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "before"), lib, cfg.analysis.workers)
-        after = run_extraction(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "after"), lib, cfg.analysis.workers)
+        before = extract(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "before"))
+        after = extract(build_requests(ctx["sel"], ctx["cs"], svc.toolchain, "after"))
         note = ""
         extra = field_follow_up(ctx["dm"], after, svc.index, svc.cdb, ctx["sel"], cfg.analysis)
         if extra:
@@ -176,7 +182,7 @@ def run_review(rid: int, svc: Services) -> None:
             follow = TuSelection(selected=extra)
             for variant, out in (("before", before), ("after", after)):
                 reqs = [r for r in build_requests(follow, ctx["cs"], svc.toolchain, variant) if r.file not in parsed]
-                out += run_extraction(reqs, lib, cfg.analysis.workers)
+                out += extract(reqs)
             ctx["sel"].selected += extra
             ctx["sel"].hops.update({p: 1 for p in extra})
             store.put_blob(rid, "selection", ctx["sel"])
```

`backend/codetortoise/health.py`:

```diff
diff --git a/backend/codetortoise/health.py b/backend/codetortoise/health.py
index 8e9b9bb..c278252 100644
--- a/backend/codetortoise/health.py
+++ b/backend/codetortoise/health.py
@@ -54,7 +54,7 @@ def run_health(svc: Services) -> HealthReport:
         svc.toolchain.prepare()
         lc = svc.toolchain.libclang
         checks.append(Check(name="libclang", ok=True, hard=True,
-                            detail=f"{lc.version} ({'vendor' if lc.vendor else 'bundled'}) {lc.path}"))
+                            detail=f"{lc.version} ({svc.toolchain.choice.reason}) {lc.path}"))
     except (OSError, RuntimeError) as e:
         checks.append(Check(name="libclang", ok=False, hard=True, detail=str(e)))
     for g in svc.toolchain.groups():          # one compiler query per toolchain group (warning only)
@@ -62,9 +62,10 @@ def run_health(svc: Services) -> HealthReport:
             sample = next((e.file for e in svc.cdb.entries if svc.toolchain.group_of(e.file) is g), None)
             if sample:
                 svc.toolchain.args_for(sample)
+        lib = g.libclang.path or "bundled libclang"
         checks.append(Check(name=f"toolchain {os.path.basename(g.compiler)}", ok=g.error is None, hard=False,
-                            detail=f"{g.files} file(s), target {g.target or 'from the command or host'}"
-                                   + (f": {g.error}" if g.error else "")))
+                            detail=f"{g.files} file(s), target {g.target or 'from the command or host'}, "
+                                   f"parsed with {lib} ({g.libclang.reason})" + (f": {g.error}" if g.error else "")))
     if svc.llm is not None:
         checks.append(Check(name="llm endpoint", ok=svc.llm.ping(), hard=False, detail=cfg.llm.base_url or ""))
     else:
```

`backend/codetortoise/cli.py`:

```diff
diff --git a/backend/codetortoise/cli.py b/backend/codetortoise/cli.py
index dfae6e9..0b345f4 100644
--- a/backend/codetortoise/cli.py
+++ b/backend/codetortoise/cli.py
@@ -98,6 +98,19 @@ def cmd_init(args) -> int:
     return 0
 
 
+def cmd_fetch_libclang(args) -> int:
+    from codetortoise.toolchain.libclang import DEFAULT_VERSION, fetch_libclang
+    cfg = load_config(Path(args.config))
+    args.version = args.version or DEFAULT_VERSION
+    try:
+        dest = fetch_libclang(cfg.server.data_dir, version=args.version, source=args.source, sha256=args.sha256)
+    except (RuntimeError, OSError) as e:
+        print(f"fetch-libclang: {e}", file=sys.stderr)
+        return 1
+    print(f"installed libclang {args.version} in {dest}; CodeTortoise uses it unless tortoise.yaml names another")
+    return 0
+
+
 def cmd_fixture_demo(args) -> int:
     from codetortoise.fixture import build_fixture
     dest = Path(args.dir).resolve()
@@ -142,6 +155,12 @@ def main(argv: list[str] | None = None) -> int:
     s.add_argument("--p4-bin", default="p4")
     s.add_argument("--no-p4", action="store_true", help="do not ask Perforce for the client's Root")
     s.set_defaults(fn=cmd_init)
+    s = sub.add_parser("fetch-libclang", help="install a newer libclang from the official LLVM release")
+    s.add_argument("--config", required=True)
+    s.add_argument("--version", default=None)
+    s.add_argument("--from", dest="source", help="an LLVM-<version>-Linux-<arch>.tar.xz already downloaded")
+    s.add_argument("--sha256", help="the archive's SHA-256 (needed for versions without a pinned digest)")
+    s.set_defaults(fn=cmd_fetch_libclang)
     s = sub.add_parser("fixture-demo", help="create a demo workspace + config from the bundled fixture")
     s.add_argument("--dir", required=True)
     s.add_argument("--port", type=int, default=8765)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_libclang_discovery.py tests/test_libclang_groups.py -q`
Expected: `10 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `294 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/toolchain/libclang.py backend/codetortoise/toolchain/toolchain.py backend/codetortoise/config.py backend/codetortoise/facts/clang_extractor.py backend/codetortoise/facts/runner.py backend/codetortoise/pipeline.py backend/codetortoise/health.py backend/codetortoise/cli.py backend/tests/test_libclang_discovery.py backend/tests/test_libclang_groups.py backend/tests/conftest.py
git commit -m "feat(libclang): find a newer libclang, fetch-libclang, a library per toolchain group"
```

---

### Task 6: check-parse, a sample parse per group, a clearer facts message, README

Spec §7. `codetortoise check-parse --config tortoise.yaml <file>` prints the compile entry and database (and others
ignored), the override, the compiler (and a failed query), target, library and why, the exact arguments, the result,
stripped flags, the first 20 errors and the functions found; exit 0 when libclang loaded the file. Health parses one
sample file per toolchain group in a worker with the group's library. The `facts` stage message becomes
`parse_summary`: precise / degraded / tree-sitter counts and the most common problem. The README documents several
databases, what is understood in a command, toolchains and libclang, `fetch-libclang` and `check-parse`.

**Files:**
- Modify: `backend/codetortoise/facts/runner.py`
- Modify: `backend/codetortoise/toolchain/toolchain.py`
- Modify: `backend/codetortoise/pipeline.py`
- Modify: `backend/codetortoise/health.py`
- Modify: `backend/codetortoise/cli.py`
- Modify: `README.md`
- Test: `backend/tests/test_parse_diagnostics.py`

**Interfaces:**
- Consumes: `Toolchain.explain`-style data via `Group`, `libclang_for` (Tasks 4-5).
- Produces: `runner.parse_summary(facts) -> str`; `Toolchain.explain(file) -> dict`; CLI `check-parse`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_parse_diagnostics.py`:

```python
"""Seeing why a file doesn't parse: check-parse, Health sample parses, the facts stage message."""
import yaml

from codetortoise.facts.model import Facts, TuInfo
from codetortoise.facts.runner import parse_summary


def _f(conf, extractor="clang", diags=()):
    return Facts(tu=TuInfo(file="/w/a.c", variant="after", confidence=conf, extractor=extractor, diagnostics=list(diags)))


def test_the_stage_message_counts_outcomes_and_names_the_commonest_reason():
    facts = [_f("precise"), _f("degraded", diags=["/w/a.c:3: 'board.h' file not found"]),
             _f("degraded", diags=["/w/b.c:9: 'board.h' file not found"]),
             _f("failed", "treesitter", ["clang extractor error: boom"])]
    assert parse_summary(facts) == ("4 parse(s): 1 precise, 2 degraded, 1 tree-sitter fallback; "
                                    "most common problem (2): 'board.h' file not found")
    assert parse_summary([_f("precise")]) == "1 parse(s): 1 precise"


def _cfg(fx, tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump({"owner": "o", "workspace": {"vcs": "git", "root": str(fx.root),
                                                             "compile_commands": str(fx.compile_commands)},
                                 "server": {"data_dir": str(tmp_path / "d")}}))
    return p


def test_check_parse_explains_one_file(fx, tmp_path, capsys):
    from codetortoise.cli import main
    assert main(["check-parse", "--config", str(_cfg(fx, tmp_path)), str(fx.root / "driver" / "uart.c")]) == 0
    out = capsys.readouterr().out
    for heading in ("compile entry:", "database:", "compiler:", "target:", "libclang:", "arguments:", "result: precise"):
        assert heading in out, heading
    assert "uart_send" in out                                        # the functions found


def test_check_parse_reports_a_file_with_no_entry_and_a_fallback(fx, tmp_path, capsys):
    from codetortoise.cli import main
    missing = tmp_path / "nowhere.c"
    missing.write_text("int x(void) { return 0; }\n")
    code = main(["check-parse", "--config", str(_cfg(fx, tmp_path)), str(missing)])
    out = capsys.readouterr().out
    assert "borrowed from the nearest file in the same database" in out and code == 0   # one database: as before


def test_health_parses_one_sample_file_per_toolchain_group(fx, tmp_path):
    from codetortoise.health import run_health
    from tests.helpers import make_services
    checks = [c for c in run_health(make_services(fx, tmp_path)).checks if c.name.startswith("toolchain ")]
    # the fixture's compile commands name a compiler that may not be installed: a warning, yet the sample parses
    assert checks and all("sample" in c.detail and "parsed precise" in c.detail for c in checks)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_parse_diagnostics.py -q`
Expected: FAIL — `ImportError: cannot import name 'parse_summary'` (collection stops: `1 error`)

- [ ] **Step 3: Implement**

`backend/codetortoise/facts/runner.py`:

```diff
diff --git a/backend/codetortoise/facts/runner.py b/backend/codetortoise/facts/runner.py
index d6426d8..a450cc6 100644
--- a/backend/codetortoise/facts/runner.py
+++ b/backend/codetortoise/facts/runner.py
@@ -2,6 +2,8 @@
 from __future__ import annotations
 
 import multiprocessing as mp
+import re
+from collections import Counter
 from collections.abc import Callable
 from concurrent.futures import ProcessPoolExecutor, as_completed
 from concurrent.futures.process import BrokenProcessPool
@@ -95,3 +97,22 @@ def run_extraction(reqs: list[TuRequest], libclang_path: str | None, workers: in
         except BrokenProcessPool:
             finish(i, extract_tu_treesitter(r, reason="libclang crashed while parsing this TU"))
     return [f for f in out if f is not None]
+
+
+_LOCATION = re.compile(r"^\S+?:\d+(:\d+)?: ")
+
+
+def parse_summary(facts: list[Facts]) -> str:
+    """"N parse(s): a precise, b degraded, c tree-sitter fallback; most common problem (k): <message>"."""
+    precise = sum(f.tu.confidence == "precise" for f in facts)
+    fallback = sum(f.tu.extractor == "treesitter" for f in facts)
+    degraded = len(facts) - precise - fallback
+    parts = [f"{precise} precise"] + ([f"{degraded} degraded"] if degraded else []) + \
+            ([f"{fallback} tree-sitter fallback"] if fallback else [])
+    out = f"{len(facts)} parse(s): " + ", ".join(parts)
+    problems = Counter(_LOCATION.sub("", f.tu.diagnostics[0]) for f in facts
+                       if f.tu.confidence != "precise" and f.tu.diagnostics)
+    if problems:
+        text, n = problems.most_common(1)[0]
+        out += f"; most common problem ({n}): {text}"
+    return out
```

`backend/codetortoise/toolchain/toolchain.py`:

```diff
diff --git a/backend/codetortoise/toolchain/toolchain.py b/backend/codetortoise/toolchain/toolchain.py
index c698e8d..ba30052 100644
--- a/backend/codetortoise/toolchain/toolchain.py
+++ b/backend/codetortoise/toolchain/toolchain.py
@@ -171,6 +171,19 @@ class Toolchain:
             args += ["-include", str(g.preludes[lang]), "-Wno-macro-redefined", "-Wno-builtin-macro-redefined"]
         return args
 
+    def explain(self, file: str) -> dict:
+        """What `args_for(file)` is built from, for `codetortoise check-parse`."""
+        file = canon(file)
+        ov = self._override(file)
+        entry = self._entry(file, ov)
+        if entry is None:
+            return {"entry": None}
+        args = self.args_for(file)
+        g = self.group_of(file)
+        others = [e for e in self.cdb._all.get(file, []) if e is not entry]
+        return {"entry": entry, "exact": self.cdb.entry_for(file) is not None, "others": others, "override": ov,
+                "group": g, "args": args}
+
     def libclang_for(self, file: str) -> LibclangChoice:
         g = self.group_of(file)
         return g.libclang if g else find_libclang(self.cfg, data_dir=self.data_dir)
```

`backend/codetortoise/pipeline.py`:

```diff
diff --git a/backend/codetortoise/pipeline.py b/backend/codetortoise/pipeline.py
index 92f150c..0820038 100644
--- a/backend/codetortoise/pipeline.py
+++ b/backend/codetortoise/pipeline.py
@@ -11,7 +11,7 @@ from codetortoise.board import BoardContext, build_board
 from codetortoise.detectors.base import DetectorContext, run_detectors
 from codetortoise.diffmap import map_changes
 from codetortoise.facts.model import Facts
-from codetortoise.facts.runner import build_requests, run_extraction
+from codetortoise.facts.runner import build_requests, parse_summary, run_extraction
 from codetortoise.impact import ImpactModel, build_impact
 from codetortoise.llm.storyboard import build_storyboard
 from codetortoise.paths import canon
@@ -194,10 +194,10 @@ def run_review(rid: int, svc: Services) -> None:
         if learned:
             svc.remember_stripped(learned)
             note += f"; stripped flags learned for this workspace: {' '.join(learned)}"
-        bad = [f.tu.file for f in before + after if f.tu.confidence != "precise"]
-        if bad:
-            raise Degraded(f"{len(bad)} TU parse(s) degraded or fell back to tree-sitter{note}")
-        return f"{len(before) + len(after)} TU parse(s){note}"
+        summary = parse_summary(before + after) + note
+        if any(f.tu.confidence != "precise" for f in before + after):
+            raise Degraded(summary)
+        return summary
 
     def impact():
         im = build_impact(ctx["before"], ctx["after"], ctx["dm"], ctx["sel"], svc.index, ctx.get("layers"), cfg.analysis)
```

`backend/codetortoise/health.py`:

```diff
diff --git a/backend/codetortoise/health.py b/backend/codetortoise/health.py
index c278252..c937652 100644
--- a/backend/codetortoise/health.py
+++ b/backend/codetortoise/health.py
@@ -5,6 +5,8 @@ import os
 
 from pydantic import BaseModel
 
+from codetortoise.facts.clang_extractor import TuRequest
+from codetortoise.facts.runner import run_extraction
 from codetortoise.paths import canon
 from codetortoise.services import Services
 from codetortoise.vcs.p4runner import P4Error
@@ -57,15 +59,21 @@ def run_health(svc: Services) -> HealthReport:
                             detail=f"{lc.version} ({svc.toolchain.choice.reason}) {lc.path}"))
     except (OSError, RuntimeError) as e:
         checks.append(Check(name="libclang", ok=False, hard=True, detail=str(e)))
-    for g in svc.toolchain.groups():          # one compiler query per toolchain group (warning only)
-        if not (svc.toolchain.libclang and svc.toolchain.libclang.vendor):
-            sample = next((e.file for e in svc.cdb.entries if svc.toolchain.group_of(e.file) is g), None)
-            if sample:
-                svc.toolchain.args_for(sample)
+    for g in svc.toolchain.groups():          # one sample parse per toolchain group (warning only)
+        sample = next((e.file for e in svc.cdb.entries if svc.toolchain.group_of(e.file) is g), None)
+        parsed = ""
+        if sample:
+            req = TuRequest(file=sample, args=svc.toolchain.args_for(sample), variant="after", libclang=g.libclang.path)
+            [facts] = run_extraction([req], g.libclang.path, 1)
+            how = "fell back to tree-sitter" if facts.tu.extractor == "treesitter" else f"parsed {facts.tu.confidence}"
+            parsed = f"; sample {os.path.basename(sample)} {how}" + (
+                f": {facts.tu.diagnostics[0]}" if facts.tu.confidence != "precise" and facts.tu.diagnostics else "")
+            if facts.tu.extractor == "treesitter":
+                g.error = g.error or f"sample {os.path.basename(sample)} fell back to tree-sitter"
         lib = g.libclang.path or "bundled libclang"
         checks.append(Check(name=f"toolchain {os.path.basename(g.compiler)}", ok=g.error is None, hard=False,
                             detail=f"{g.files} file(s), target {g.target or 'from the command or host'}, "
-                                   f"parsed with {lib} ({g.libclang.reason})" + (f": {g.error}" if g.error else "")))
+                                   f"parsed with {lib} ({g.libclang.reason})" + parsed + (f": {g.error}" if g.error else "")))
     if svc.llm is not None:
         checks.append(Check(name="llm endpoint", ok=svc.llm.ping(), hard=False, detail=cfg.llm.base_url or ""))
     else:
```

`backend/codetortoise/cli.py`:

```diff
diff --git a/backend/codetortoise/cli.py b/backend/codetortoise/cli.py
index 0b345f4..1d5ca3d 100644
--- a/backend/codetortoise/cli.py
+++ b/backend/codetortoise/cli.py
@@ -98,6 +98,48 @@ def cmd_init(args) -> int:
     return 0
 
 
+def cmd_check_parse(args) -> int:
+    from codetortoise.facts.clang_extractor import TuRequest
+    from codetortoise.facts.runner import run_extraction
+    svc = _services(args.config)
+    tc = svc.toolchain
+    tc.prepare()
+    file = str(Path(args.file).resolve())
+    info = tc.explain(file)
+    e = info["entry"]
+    if e is None:
+        print(f"{file}: no compile entry in any database ({len(svc.cdb.databases)} loaded); "
+              "it parses with default flags only")
+    else:
+        g = info["group"]
+        how = "exact" if info["exact"] else "borrowed from the nearest file in the same database"
+        print(f"compile entry: {e.file} ({how})\n  directory: {e.directory}\n  database: {e.db}")
+        for o in info["others"]:
+            print(f"  also in: {o.db} (ignored: the first entry wins)")
+        if info["override"] is not None:
+            print(f"  override: {info['override'].match}")
+        print(f"compiler: {g.compiler}" + (f" (query failed: {g.error})" if g.error else ""))
+        print(f"target: {g.target or 'from the command or the host'}")
+        lib = g.libclang
+        rd = f", resource dir {lib.resource_dir}" if lib.resource_dir else ""
+        print(f"libclang: {lib.path or 'bundled'} ({lib.reason}){rd}")
+        print("arguments: " + " ".join(info["args"]))
+        if svc.cdb.problems:
+            print("database problems: " + "; ".join(svc.cdb.problems[:5]))
+    args_ = tc.args_for(file)
+    lib_path = tc.libclang_for(file).path
+    [facts] = run_extraction([TuRequest(file=file, args=args_, variant="after", libclang=lib_path)], lib_path, 1)
+    t = facts.tu
+    result = "tree-sitter fallback" if t.extractor == "treesitter" else t.confidence
+    print(f"result: {result} ({t.error_count} error(s))")
+    if t.stripped_flags:
+        print("stripped flags: " + " ".join(t.stripped_flags))
+    for d in t.diagnostics[:20]:
+        print(f"  {d}")
+    print("functions: " + (", ".join(f.qualname for f in facts.functions) or "none"))
+    return 0 if t.extractor == "clang" else 1
+
+
 def cmd_fetch_libclang(args) -> int:
     from codetortoise.toolchain.libclang import DEFAULT_VERSION, fetch_libclang
     cfg = load_config(Path(args.config))
@@ -155,6 +197,10 @@ def main(argv: list[str] | None = None) -> int:
     s.add_argument("--p4-bin", default="p4")
     s.add_argument("--no-p4", action="store_true", help="do not ask Perforce for the client's Root")
     s.set_defaults(fn=cmd_init)
+    s = sub.add_parser("check-parse", help="show how one file is parsed, and why it fails if it does")
+    s.add_argument("--config", required=True)
+    s.add_argument("file")
+    s.set_defaults(fn=cmd_check_parse)
     s = sub.add_parser("fetch-libclang", help="install a newer libclang from the official LLVM release")
     s.add_argument("--config", required=True)
     s.add_argument("--version", default=None)
```

`README.md`:

````diff
diff --git a/README.md b/README.md
index 1c356c6..1751e11 100644
--- a/README.md
+++ b/README.md
@@ -119,9 +119,10 @@ Whether you start from `init` or from scratch, check these values in order.
    `p4 client -o | grep -E '^(Root|AltRoots)'`. Symbolic links to it are fine.
 4. **`workspace.compile_commands`: how each file is compiled.** The path to `compile_commands.json` for the build you
    review. To create one, see [Compile database](#compile-database).
-5. **`toolchain.clang`: your compiler.** The compiler driver your build uses, such as a vendor `clang` or `gcc`.
-   CodeTortoise asks it for its built-in include paths and macros. Find it in the first entry of
-   `compile_commands.json`.
+5. **`toolchain`: usually nothing.** Each file's own compiler, from the compile database, is asked for its built-in
+   include paths and macros, and the target comes from the compiler. Set `toolchain.clang` only if that compiler
+   isn't installed on this machine, and see [Toolchains and libclang](#toolchains-and-libclang) for mixed targets
+   and vendor toolchains. Check one file with `codetortoise check-parse`.
 6. **`server`: how people reach the app.** `host: 127.0.0.1` keeps it on this machine. To share it, use `0.0.0.0`,
    set `public_url` to the address colleagues open, and set `tls_cert` and `tls_key` so sign-ins aren't sent in plain
    text. `data_dir` holds the database and caches; back it up.
@@ -136,8 +137,6 @@ With a P4CONFIG file in the workspace, this is a complete configuration:
 workspace:
   root: /work/main
   compile_commands: /work/main/build/compile_commands.json
-toolchain:
-  clang: /opt/vendor/bin/clang
 ```
 
 #### Every setting
@@ -159,9 +158,17 @@ workspace:
   compile_commands: /work/main/build/compile_commands.json
   # p4_bin: /opt/perforce/bin/p4
 toolchain:
-  clang: /opt/vendor/bin/clang      # your compiler driver, queried for implicit include paths and macros
-  libclang: /opt/vendor/lib/libclang.so   # optional; the bundled libclang 18 is used otherwise
+  # clang: /opt/vendor/bin/clang    # optional: query this compiler for every file (default: each file's own compiler)
+  # target: armv7m-none-eabi        # optional: for files whose command names none (default: from the compiler)
+  # libclang: /opt/vendor/lib/libclang.so   # optional: default is found (see Toolchains and libclang)
+  search_paths: [/opt/tools]        # optional: folders to search for a newer libclang
   strip_flags: []                   # vendor flags libclang must ignore (unknown ones are learned automatically)
+  overrides:                        # optional, first match wins
+    - match: "dsp/**"               # workspace-relative glob
+      compile_commands: /work/main/build/dsp/compile_commands.json
+      clang: /opt/hexagon/bin/hexagon-clang
+      target: hexagon
+      libclang: /opt/hexagon/lib/libclang.so
 swarm:
   url: "https://swarm.example.com"  # optional
 llm:                                # optional; without it, narratives use built-in templates
@@ -215,10 +222,54 @@ libclang needs the exact compile command of each file. Typical ways to get `comp
 | Make or anything else | [Bear](https://github.com/rizsotto/Bear): `bear -- make -j` |
 | Vendor IDEs | most can export it; otherwise wrap the build with Bear |
 
-Keep it in or under the workspace and regenerate it when the build changes. A changed file missing from it is still
-parsed, with flags borrowed from the nearest entry. With a vendor cross-compiler, point `toolchain.clang`
-at the vendor driver, so its built-in include paths and macros are used. Flags libclang does not understand are
-stripped and remembered per workspace; the Health page lists them.
+Regenerate it when the build changes. A changed file missing from it is still parsed, with flags borrowed from the
+nearest file of the same database.
+
+**Several databases.** `workspace.compile_commands` takes one path, a list of paths or globs, or `auto`:
+
+```yaml
+workspace:
+  compile_commands: auto            # every compile_commands.json under build_root
+  build_root: /work/main/build      # default: the folder of the first database `codetortoise init` finds
+```
+
+A file listed in several databases uses the first one in your list, or with `auto` the deepest (a nested build is
+usually the specialised build of that component). To choose for some paths, use `toolchain.overrides` with
+`compile_commands`. The Health page lists every database and how many files appear in more than one.
+
+**What CodeTortoise understands in a command.** Compiler wrappers (`ccache`, `sccache`, `distcc`, `icecc`,
+`buildcache`, an `env VAR=x` prefix) are skipped; `@file` response files are expanded; relative paths resolve from
+the entry's `directory`; MSVC commands (`cl`, `clang-cl`) use clang's `cl` mode. Flags libclang doesn't understand
+are stripped and remembered per workspace; the Health page lists them.
+
+### Toolchains and libclang
+
+Each file is parsed for its own toolchain. CodeTortoise asks the file's compiler (or `toolchain.clang`, or an
+override's `clang`) for its built-in include paths and macros, once per group of files that share a compiler, target
+and target flags. The target comes from the command (`--target`), an override, `toolchain.target`, the compiler's
+name (`arm-none-eabi-gcc` means `arm-none-eabi`), or the compiler's `-dumpmachine`. The Health page lists each group,
+parses one sample file of it, and shows the first error if that fails.
+
+libclang only parses, so one upstream library handles every standard target (ARM, AArch64, RISC-V, x86, MIPS,
+PowerPC). A newer library knows more recent flags. The library for a group is, in order: an override's or
+`toolchain.libclang`; the one next to a clang compiler (that toolchain's own, for vendor forks); the newest under
+`toolchain.search_paths`; one installed with `codetortoise fetch-libclang`; the newest system LLVM
+(`/usr/lib/llvm-*`); the one bundled with CodeTortoise (18.1.1). Groups that need different libraries parse in
+separate worker processes.
+
+```bash
+uv run --project backend codetortoise fetch-libclang --config tortoise.yaml       # LLVM 23.1.2, ~2 GB streamed, ~230 MB kept
+uv run --project backend codetortoise fetch-libclang --config tortoise.yaml \
+    --from LLVM-23.1.2-Linux-X64.tar.xz                                          # offline: a copied release archive
+uv run --project backend codetortoise check-parse --config tortoise.yaml src/drivers/uart.c
+```
+
+`fetch-libclang` checks the archive's SHA-256 against the digest GitHub publishes (or a pinned one, or `--sha256`).
+`check-parse` shows how one file is parsed: the compile entry and database used, the compiler, target and library,
+the exact arguments, the result and the first errors. Run it on the server when a review's `facts` stage says files
+fell back to tree-sitter; the stage message names the most common problem.
+
+Compilers that are neither GCC- nor clang-compatible (IAR, TI `cl6x`, Green Hills, Tasking) aren't supported yet.
 
 ## Enterprise environments
 
@@ -336,7 +387,7 @@ restart. Reviews keep working across upgrades, and re-running a review rebuilds
 | `Unicode server permits only unicode enabled clients` | Set `P4CHARSET` in the service environment. |
 | `CL … is pending with no shelved files` | The CL isn't shelved, or it was shelved on another edge server. See [SSL, Unicode and network topology](#ssl-unicode-and-network-topology). |
 | Files listed as warnings ("content unavailable", "not in client view") | The owner lacks `read` on those paths, or the client view doesn't map them. |
-| `facts` stage degraded, "fell back to tree-sitter" | Unknown vendor flags or missing includes. Check the Health page's stripped flags, add `toolchain.strip_flags`, and make sure `toolchain.clang` points at the vendor driver. |
+| `facts` stage degraded, "fell back to tree-sitter" | Run `codetortoise check-parse` on one of the files: it shows the compile entry, compiler, target, library and first errors. Common causes: the build's compiler isn't on this machine (set `toolchain.clang`), a missing generated header, a target libclang doesn't know (set `toolchain.target`, or a vendor `libclang`). See [Toolchains and libclang](#toolchains-and-libclang). |
 | Board warns about workspace drift | The workspace isn't at the CL's base revision. Sync it, or expect context code to differ from what was analysed. |
 | `llm` stage degraded | The endpoint is unreachable or rejected the request. Reviews are complete without it. Check `llm.base_url` and the key variable. |
 | Swarm actions missing | The owner hasn't signed in since the server started, or `swarm.url` is wrong. |
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_parse_diagnostics.py -q`
Expected: `4 passed`

- [ ] **Step 5: Run the whole suite**

Run: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q`
Expected: `All checks passed!` and `298 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/facts/runner.py backend/codetortoise/toolchain/toolchain.py backend/codetortoise/pipeline.py backend/codetortoise/health.py backend/codetortoise/cli.py README.md backend/tests/test_parse_diagnostics.py
git commit -m "feat(diagnostics): check-parse, a sample parse per toolchain group, clearer facts stage message"
```

---

## Spec Coverage

| Spec | Where |
|---|---|
| §2 compile databases (list, globs, auto, precedence, confined nearest entry, overrides' databases) | Tasks 3, 4 |
| §3 reading a command (response files, wrappers, cl mode, working directory, target) | Tasks 2, 4 |
| §4 toolchain groups | Task 4 |
| §5 libclang (no private APIs, unknown kinds, discovery, fetch, per-group workers, resource dir) | Tasks 1, 5 |
| §6 configuration | Tasks 3, 4, 5 |
| §7 diagnostics (check-parse, Health, stage message) | Tasks 3, 4, 6 |
| §8 testing | every task |

## Finish

- [ ] Run everything: `cd backend && uv run ruff check codetortoise tests && uv run pytest -q` (expected `298 passed`), and
  `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx playwright test` (unchanged by this plan).
- [ ] On a real workspace: `codetortoise check-parse --config tortoise.yaml <a file>` shows `result: precise` or
  `degraded`, and the Health page lists each toolchain group with a parsed sample.
