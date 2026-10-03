"""The host gcc/g++ queried by default must not degrade parses (final review C1). Opt-in: needs gcc, g++ and LLVM 21."""
import json
import os
import shutil

import pytest

from codetortoise.config import ToolchainConfig
from codetortoise.facts.clang_extractor import TuRequest
from codetortoise.facts.runner import run_extraction
from codetortoise.toolchain import libclang
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.toolchain import Toolchain

LLVM = "/usr/lib/llvm-21/lib"
needs = pytest.mark.skipif(not (shutil.which("gcc") and shutil.which("g++") and os.path.isdir(LLVM)),
                           reason="needs host gcc, g++ and a system LLVM 21")

CASES = {
    "vec.cpp": ("g++", ["-std=c++17"], "#include <vector>\n#include <string>\n#include <map>\n"
                "int f() { std::vector<std::string> v{\"a\"}; std::map<int,int> m; return (int)v.size() + (int)m.size(); }\n"),
    "nortti.cpp": ("g++", ["-std=c++17", "-fno-exceptions", "-fno-rtti"],
                   "#include <vector>\nint g() { std::vector<int> v; return 0; }\n"),
    "simd.c": ("gcc", ["-O2"], "#include <immintrin.h>\nint h(void) { return 1; }\n"),
}


@needs
@pytest.mark.parametrize("name", list(CASES))
def test_host_gcc_files_parse_precisely_through_the_toolchain(tmp_path, monkeypatch, name):
    monkeypatch.setattr(libclang, "SYSTEM_GLOBS", [LLVM])
    compiler, flags, text = CASES[name]
    (tmp_path / name).write_text(text)
    cc = tmp_path / "compile_commands.json"
    cc.write_text(json.dumps([{"directory": str(tmp_path), "file": name, "arguments": [compiler, *flags, "-c", name]}]))
    tc = Toolchain(ToolchainConfig(), load_databases(cc, tmp_path, None), tmp_path / "d" / "tc", root=tmp_path)
    f = str(tmp_path / name)
    lib = tc.libclang_for(f)
    assert lib.kind == "system"
    [facts] = run_extraction([TuRequest(file=f, args=tc.args_for(f), variant="after", libclang=lib.path)], lib.path, 1)
    assert facts.tu.extractor == "clang" and facts.tu.confidence == "precise", facts.tu.diagnostics[:3]
