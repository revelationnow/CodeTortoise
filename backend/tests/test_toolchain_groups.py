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
