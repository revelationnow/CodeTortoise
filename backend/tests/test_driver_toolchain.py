import shutil

import pytest

from codetortoise.config import ToolchainConfig
from codetortoise.toolchain.compile_db import CompileDb, CompileEntry
from codetortoise.toolchain.driver import DriverInfo, parse_driver_output, query_driver, target_flags
from codetortoise.toolchain.toolchain import Toolchain

STDERR = """clang -cc1 version 17.0.0 based upon LLVM
#include "..." search starts here:
#include <...> search starts here:
 /opt/vendor/lib/clang/17/include
 /opt/vendor/sysroot/usr/include
 /opt/vendor/Frameworks (framework directory)
End of search list.
"""


def test_parse_driver_output():
    dirs, defines = parse_driver_output("#define __ARM_ARCH 7\n#define __VENDOR__ 1\n#define EMPTY\n", STDERR)
    assert dirs == ["/opt/vendor/lib/clang/17/include", "/opt/vendor/sysroot/usr/include", "/opt/vendor/Frameworks"]
    assert defines == [("__ARM_ARCH", "7"), ("__VENDOR__", "1"), ("EMPTY", "")]


def test_target_flags_keeps_only_target_affecting_flags():
    args = ["--target=arm-none-eabi", "-DX", "-mcpu=m4", "-I/w", "-target", "armv7", "-std=c11", "-O2", "-mthumb"]
    assert target_flags(args) == ["--target=arm-none-eabi", "-mcpu=m4", "-target", "armv7", "-std=c11", "-mthumb"]


@pytest.mark.skipif(shutil.which("gcc") is None, reason="needs a host compiler to query")
def test_query_real_driver():
    info = query_driver("gcc", [], "c")
    assert info.include_dirs and any(name == "__STDC__" or name == "__GNUC__" for name, _ in info.defines)


def test_args_for_adds_driver_info_when_libclang_is_not_vendor(tmp_path, monkeypatch):
    from codetortoise.toolchain import toolchain as tcmod
    db = CompileDb([CompileEntry("/w/a.c", "/w", ("vcc", "--target=arm", "-c", "a.c"), compiler="vcc")])
    tc = Toolchain(ToolchainConfig(clang="/opt/vendor/bin/clang"), db, tmp_path)
    monkeypatch.setattr(tcmod, "query_driver", lambda driver, flags, lang: DriverInfo(
        ("/opt/vendor/lib/clang/17/include", "/opt/vendor/sysroot/usr/include"), (("__VENDOR__", "1"),),
        "/opt/vendor/lib/clang/17"))
    args = tc.args_for("/w/a.c")[2:]                      # after -working-directory /w
    assert args[:1] == ["--target=arm"]                   # the command's own target, nothing added
    assert ["-resource-dir", "/opt/vendor/lib/clang/17"] == args[1:3]
    assert "/opt/vendor/lib/clang/17/include" not in args  # builtin headers come via -resource-dir
    assert ["-isystem", "/opt/vendor/sysroot/usr/include"] == args[3:5]
    assert args[5] == "-include" and args[6].startswith(str(tmp_path / "prelude-"))


def test_prepare_loads_bundled_libclang(tmp_path):
    tc = Toolchain(ToolchainConfig(), CompileDb([]), tmp_path)
    tc.prepare()
    assert tc.libclang.version.startswith("clang version") and tc.libclang.vendor is False


def test_prelude_skips_compiler_identity_macros(tmp_path, monkeypatch):
    from codetortoise.toolchain import toolchain as tcmod
    info = DriverInfo(("/opt/v/include",), (("__GNUC__", "15"), ("__GNUC_MINOR__", "2"), ("__clang_major__", "17"),
                                            ("__VERSION__", '"15.2"'), ("__STDC_VERSION__", "201710L"),
                                            ("__GCC_HAVE_DWARF2_CFI_ASM", "1"), ("__ARM_ARCH", "7"),
                                            ("__VENDOR_CHIP__", "1"), ("__SIZEOF_LONG__", "4")), None)
    monkeypatch.setattr(tcmod, "query_driver", lambda *a, **k: info)
    db = CompileDb([CompileEntry("/w/a.c", "/w", ("vcc", "-c", "a.c"))])
    tc = Toolchain(ToolchainConfig(clang="/opt/v/bin/vcc"), db, tmp_path)
    tc.prepare()
    tc.args_for("/w/a.c")                                  # compilers are queried on first use
    prelude = tc.group_of("/w/a.c").preludes["c"].read_text()
    assert "__ARM_ARCH 7" in prelude and "__VENDOR_CHIP__ 1" in prelude and "__SIZEOF_LONG__ 4" in prelude
    for name in ("__GNUC__", "__GNUC_MINOR__", "__clang_major__", "__VERSION__", "__STDC_VERSION__", "__GCC_HAVE"):
        assert name not in prelude


def test_gcc_only_macros_and_gcc_internal_headers_stay_out(tmp_path, monkeypatch):
    from codetortoise.toolchain import toolchain as tcmod
    from codetortoise.toolchain.libclang import LibclangChoice
    info = DriverInfo(("/usr/lib/gcc/x86_64-linux-gnu/15/include", "/usr/local/include", "/usr/include"),
                      (("__cpp_rtti", "199711L"), ("__BFLT16_MAX__", "3.0bf16"), ("__EXCEPTIONS", "1"),
                       ("__SIZEOF_FLOAT128__", "16"), ("__x86_64__", "1")), None)
    monkeypatch.setattr(tcmod, "query_driver", lambda *a, **k: info)
    monkeypatch.setattr(tcmod, "find_libclang", lambda *a, **k: LibclangChoice("/l/libclang.so.21", "system", "t",
                                                                                 "/l/clang/21"))
    db = CompileDb([CompileEntry("/w/a.cc", "/w", ("g++", "-c", "a.cc"), compiler="g++")])
    tc = Toolchain(ToolchainConfig(), db, tmp_path)
    args = tc.args_for("/w/a.cc")
    assert "/usr/lib/gcc/x86_64-linux-gnu/15/include" not in args and "/usr/include" in args
    prelude = tc.group_of("/w/a.cc").preludes["c++"].read_text()
    assert "__x86_64__" in prelude
    assert not any(m in prelude for m in ("__cpp_rtti", "__BFLT16_MAX__", "__EXCEPTIONS", "__SIZEOF_FLOAT128__"))
