"""Build targets of changed files (spec 2026-10-05-two-tier-stories §3.1)."""
from codetortoise.config import Config, TargetRule
from codetortoise.targets import UNKNOWN, resolve_targets
from codetortoise.toolchain.compile_db import CompileDb, CompileEntry

R = "/w"


def _db(*entries):
    """entries: (file relative to R, database path)."""
    return CompileDb([CompileEntry(file=f"{R}/{f}", directory=R, args=("cc", "-c", f), compiler="cc", db=db)
                      for f, db in entries])


def _resolve(files, cdb, rules=(), triple=None, includers=None, build_root=f"{R}/out"):
    return resolve_targets([f"{R}/{f}" for f in files], list(rules), R, cdb, build_root,
                           triple or (lambda f: None), includers or (lambda h: set()))


def test_a_configured_name_wins_and_the_first_matching_rule_applies():
    cdb = _db(("modem/rf/a.c", f"{R}/out/build-modem/compile_commands.json"))
    got = _resolve(["modem/rf/a.c", "app/main.c"], cdb,
                   [TargetRule(match="modem/**", name="modem"), TargetRule(match="modem/rf/*", name="rf"),
                    TargetRule(match="app/*", name="app")])
    assert got == {f"{R}/modem/rf/a.c": ["modem"], f"{R}/app/main.c": ["app"]}


def test_several_databases_name_targets_by_their_directory_under_the_build_root():
    m, d = f"{R}/out/build-modem/compile_commands.json", f"{R}/out/build-dsp/compile_commands.json"
    cdb = _db(("modem/a.c", m), ("dsp/b.c", d), ("common/util.c", m), ("common/util.c", d))
    got = _resolve(["modem/a.c", "dsp/b.c", "common/util.c"], cdb, triple=lambda f: "arm-none-eabi")
    assert got == {f"{R}/modem/a.c": ["build-modem"], f"{R}/dsp/b.c": ["build-dsp"],
                   f"{R}/common/util.c": ["build-dsp", "build-modem"]}          # in both: shared


def test_one_database_names_targets_by_the_compiler_triple():
    db = f"{R}/compile_commands.json"
    cdb = _db(("modem/a.c", db), ("dsp/b.c", db), ("app/c.c", db))
    triples = {f"{R}/modem/a.c": "arm-none-eabi", f"{R}/dsp/b.c": "hexagon"}
    got = _resolve(["modem/a.c", "dsp/b.c", "app/c.c"], cdb, triple=triples.get, build_root=None)
    assert got == {f"{R}/modem/a.c": ["arm-none-eabi"], f"{R}/dsp/b.c": ["hexagon"], f"{R}/app/c.c": ["compile_commands"]}


def test_a_header_takes_the_targets_of_the_files_that_include_it_and_else_unknown():
    m, d = f"{R}/out/build-modem/compile_commands.json", f"{R}/out/build-dsp/compile_commands.json"
    cdb = _db(("modem/a.c", m), ("dsp/b.c", d))
    inc = {f"{R}/inc/shared.h": {f"{R}/modem/a.c", f"{R}/dsp/b.c", f"{R}/inc/other.h"}, f"{R}/inc/modem.h": {f"{R}/modem/a.c"}}
    got = _resolve(["inc/shared.h", "inc/modem.h", "inc/orphan.h"], cdb, includers=lambda h: inc.get(h, set()))
    assert got == {f"{R}/inc/shared.h": ["build-dsp", "build-modem"], f"{R}/inc/modem.h": ["build-modem"],
                   f"{R}/inc/orphan.h": [UNKNOWN]}


def test_a_failing_triple_lookup_leaves_the_database_name():
    def boom(f):
        raise RuntimeError("no libclang")
    cdb = _db(("a.c", f"{R}/compile_commands.json"))
    assert _resolve(["a.c"], cdb, triple=boom, build_root=None) == {f"{R}/a.c": ["compile_commands"]}


def test_targets_are_read_from_the_config():
    cfg = Config.model_validate({"workspace": {"root": "/w", "compile_commands": "auto"},
                                 "targets": [{"match": "modem/**", "name": "modem"}]})
    assert cfg.targets == [TargetRule(match="modem/**", name="modem")]
    assert CompileDb([]).databases_of("/w/a.c") == []
