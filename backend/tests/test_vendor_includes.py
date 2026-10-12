"""A toolchain's own libclang finds that toolchain's headers (owner feedback 2026-10-11): it is told where the
toolchain is installed, the compiler's include paths are added when it may run, and an override can name more."""
import glob
import os
import subprocess
import sys
import textwrap

import pytest

from codetortoise.config import ToolchainConfig
from codetortoise.toolchain import toolchain as tcmod
from codetortoise.toolchain.compile_db import CompileDb, CompileEntry
from codetortoise.toolchain.driver import DriverInfo
from codetortoise.toolchain.libclang import LibclangChoice
from codetortoise.toolchain.toolchain import Toolchain


def _install(root, name):
    """A vendor install: bin/<name> beside lib/libclang.so.21 and its built-in headers."""
    (root / "bin").mkdir(parents=True)
    driver = root / "bin" / name
    driver.write_text("#!/bin/sh\nexit 1\n")
    driver.chmod(0o755)
    (root / "lib" / "clang" / "21" / "include").mkdir(parents=True)
    (root / "lib" / "libclang.so.21").write_bytes(b"")
    return driver


def _two_targets(tmp_path, **cfg):
    ws = tmp_path / "ws"
    acc, dsp = _install(tmp_path / "acc", "acc-clang"), _install(tmp_path / "dsp", "clang-21")
    db = CompileDb([CompileEntry(str(ws / "acc/a.c"), str(ws), ("cc", "-c", "acc/a.c")),
                    CompileEntry(str(ws / "dsp/b.c"), str(ws), ("cc", "-c", "dsp/b.c"))])
    overrides = [{"match": "acc/**", "clang": str(acc), "target": "acc", **cfg.pop("acc", {})},
                 {"match": "**", "clang": str(dsp), "target": "dsp", **cfg.pop("dsp", {})}]
    return ws, acc, dsp, Toolchain(ToolchainConfig(overrides=overrides, **cfg), db, tmp_path / "d" / "tc", root=ws)


def _value(args, flag):
    return [args[i + 1] for i, a in enumerate(args) if a == flag]


def test_a_toolchains_own_library_is_told_where_that_toolchain_is_installed(tmp_path):
    ws, acc, dsp, tc = _two_targets(tmp_path, query_compilers="off")
    assert tc.libclang_for(str(ws / "acc/a.c")).kind == "toolchain"
    assert _value(tc.args_for(str(ws / "acc/a.c")), "-ccc-install-dir") == [str(acc.parent)]
    assert _value(tc.args_for(str(ws / "dsp/b.c")), "-ccc-install-dir") == [str(dsp.parent)]


def test_the_install_dir_is_the_compilers_real_folder(tmp_path):
    ws, acc, _, tc = _two_targets(tmp_path, query_compilers="off")
    link = tmp_path / "links" / "acc-clang"
    link.parent.mkdir()
    link.symlink_to(acc)
    tc.cfg.overrides[0].clang = str(link)
    assert _value(tc.args_for(str(ws / "acc/a.c")), "-ccc-install-dir") == [str(acc.parent)]


def test_another_library_gets_no_install_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tcmod, "find_libclang", lambda *a, **k: LibclangChoice("/l/libclang.so.21", "system", "t",
                                                                                 "/l/clang/21"))
    ws, _, _, tc = _two_targets(tmp_path, query_compilers="off")
    assert "-ccc-install-dir" not in tc.args_for(str(ws / "acc/a.c"))


def test_a_compiler_that_may_run_adds_its_include_paths_to_its_own_library_without_a_prelude(tmp_path, monkeypatch):
    ws, acc, dsp, tc = _two_targets(tmp_path, query_compilers="all")
    rd = str(acc.parent.parent / "lib" / "clang" / "21")
    paths = {str(acc): (f"{rd}/include", "/t/acc/include/c++", "/t/acc/include"),
             str(dsp): ("/t/dsp/include",)}
    monkeypatch.setattr(tcmod, "query_driver", lambda driver, flags, lang: DriverInfo(paths[driver], (("X", "1"),), rd))
    args = tc.args_for(str(ws / "acc/a.c"))
    assert _value(args, "-isystem") == ["/t/acc/include/c++", "/t/acc/include"]     # in the compiler's order
    assert f"{rd}/include" not in args and "-include" not in args                 # the library has its own macros
    assert _value(tc.args_for(str(ws / "dsp/b.c")), "-isystem") == ["/t/dsp/include"]
    assert tc.group_of(str(ws / "acc/a.c")).error is None


def test_a_compiler_that_may_not_run_is_not_an_error_for_its_own_library(tmp_path, monkeypatch):
    monkeypatch.setattr(tcmod, "query_driver", lambda *a, **k: pytest.fail("the compiler must not run"))
    ws, _, _, tc = _two_targets(tmp_path, query_compilers="off")
    tc.args_for(str(ws / "acc/a.c"))
    assert tc.group_of(str(ws / "acc/a.c")).error is None


def test_an_override_names_more_system_include_dirs_for_its_files_only(tmp_path):
    ws, _, _, tc = _two_targets(tmp_path, query_compilers="off",
                                acc={"system_include_dirs": ["/t/acc/include", "tools/acc/include"]})
    assert _value(tc.args_for(str(ws / "acc/a.c")), "-isystem") == ["/t/acc/include", str(ws / "tools/acc/include")]
    assert "-isystem" not in tc.args_for(str(ws / "dsp/b.c"))


def test_named_dirs_come_after_the_compilers(tmp_path, monkeypatch):
    ws, acc, _, tc = _two_targets(tmp_path, query_compilers="all", acc={"system_include_dirs": ["/t/extra"]})
    monkeypatch.setattr(tcmod, "query_driver", lambda *a, **k: DriverInfo(("/t/acc/include",), (), None))
    assert _value(tc.args_for(str(ws / "acc/a.c")), "-isystem") == ["/t/acc/include", "/t/extra"]


LLVM = sorted(glob.glob("/usr/lib/llvm-*/lib/libclang-[0-9]*.so.*") + glob.glob("/usr/lib/llvm-*/lib/libclang.so.*"))


@pytest.mark.skipif(not LLVM, reason="needs a system libclang")
def test_libclang_finds_a_vendor_targets_headers_from_the_install_dir(tmp_path):
    tools = tmp_path / "Tools"
    (tools / "bin").mkdir(parents=True)
    inc = tools / "lib" / "clang-runtimes" / "armv7m-none-eabi" / "include"   # clang's bare-metal ARM layout
    inc.mkdir(parents=True)
    (inc / "vendor_std.h").write_text("#define VENDOR_OK 1\n")
    src = tmp_path / "a.c"
    src.write_text("#include <vendor_std.h>\nint x = VENDOR_OK;\n")
    probe = textwrap.dedent(f"""
        import clang.cindex as ci
        ci.Config.set_library_file({LLVM[-1]!r})
        idx = ci.Index.create()
        for extra in ([], ["-ccc-install-dir", {str(tools / "bin")!r}]):
            print(len(idx.parse({str(src)!r}, args=["--target=armv7m-none-eabi", *extra]).diagnostics))
    """)
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True,
                         env={**os.environ}).stdout.split()
    assert out == ["1", "0"]                        # header not found without it; found with it
