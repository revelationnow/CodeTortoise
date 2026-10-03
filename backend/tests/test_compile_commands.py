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
