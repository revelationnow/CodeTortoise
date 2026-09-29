import json

from codetortoise.toolchain.compile_db import CompileDb, CompileEntry, sanitize_args


def test_sanitize_drops_output_and_dep_flags_and_absolutizes_paths():
    e = CompileEntry("/w/src/a.c", "/w/build", (
        "armclang", "--target=arm-none-eabi", "-Iinc", "-I", "../x", "-isystem", "sys", "--sysroot=../sr",
        "-c", "../src/a.c", "-o", "a.o", "-MD", "-MF", "a.d", "-DFOO=1", "-mcpu=cortex-m4", "-Wall"))
    assert sanitize_args(e) == ["--target=arm-none-eabi", "-I/w/build/inc", "-I", "/w/x", "-isystem", "/w/build/sys",
                                "--sysroot=/w/sr", "-DFOO=1", "-mcpu=cortex-m4", "-Wall"]


def test_sanitize_strip_list_matches_exact_and_key_value():
    e = CompileEntry("/w/a.c", "/w", ("cc", "-mvendor-x", "--vendor-opt=3", "-O2", "a.c"))
    assert sanitize_args(e, {"-mvendor-x", "--vendor-opt"}) == ["-O2"]


def test_load_command_strings_and_nearest_entry(tmp_path):
    (tmp_path / "src/sub").mkdir(parents=True)
    cc = tmp_path / "compile_commands.json"
    cc.write_text(json.dumps([
        {"directory": str(tmp_path), "file": "src/a.c", "command": "cc -Iinc -c src/a.c"},
        {"directory": str(tmp_path), "file": "src/sub/b.c", "arguments": ["cc", "-c", "src/sub/b.c"]}]))
    db = CompileDb.load(cc)
    a = str((tmp_path / "src/a.c").resolve())
    assert db.entry_for(a).args == ("cc", "-Iinc", "-c", "src/a.c")
    assert db.nearest_entry(str(tmp_path / "src/a.h")).file == a
    assert db.nearest_entry(str(tmp_path / "src/sub/b.h")).file == str((tmp_path / "src/sub/b.c").resolve())
    assert db.nearest_entry("/elsewhere/z.h") is not None
