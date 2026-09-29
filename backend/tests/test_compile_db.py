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


def test_include_dirs_are_canonicalized_through_symlinks(tmp_path):
    real = tmp_path / "real"
    (real / "include").mkdir(parents=True)
    (tmp_path / "link").symlink_to(real)
    e = CompileEntry(str(real / "a.c"), str(tmp_path / "link"),
                     ("cc", "-Iinclude", "-isystem", str(tmp_path / "link/include"), "-c", "a.c"))
    inc = str((real / "include").resolve())
    assert sanitize_args(e) == [f"-I{inc}", "-isystem", inc]


def test_new_header_behind_symlinked_include_dir_parses(tmp_path):
    from codetortoise.facts.clang_extractor import TuRequest, extract_tu
    real = tmp_path / "real"
    (real / "include").mkdir(parents=True)
    (tmp_path / "link").symlink_to(real)
    main = real / "a.c"
    main.write_text('#include "new.h"\nint f(void) { return NEW_VALUE; }\n')
    e = CompileEntry(str(main.resolve()), str(tmp_path / "link"), ("cc", "-xc", "-Iinclude", "-c", "a.c"))
    new_h = str((real / "include/new.h").resolve())
    facts = extract_tu(TuRequest(file=str(main), args=sanitize_args(e), variant="after",
                                 unsaved={new_h: "#define NEW_VALUE 7\n"}))
    assert facts.tu.confidence == "precise", facts.tu.diagnostics
    assert facts.functions[0].returns == ["7"]


def test_include_dirs_union():
    from codetortoise.toolchain.compile_db import include_dirs
    db = CompileDb([CompileEntry("/w/a.c", "/w", ("cc", "-Iinc", "-isystem", "/sys", "-c", "a.c")),
                    CompileEntry("/w/b.c", "/w", ("cc", "-Iinc", "-iquote", "q", "-c", "b.c"))])
    assert include_dirs(db) == ["/w/inc", "/sys", "/w/q"]
