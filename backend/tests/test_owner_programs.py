"""Programs and libraries a workspace's settings or compile database could have the server run or load (final review
I3 of spec 2026-10-31): a workspace added in the UI runs compilers and loads libclang only from the toolchain folders
tortoise.yaml lists, judged by where a path really leads; tortoise.yaml's own workspace is not held to them."""
import subprocess

import pytest
from test_toolchain_review_fixes import _compiler, _ws

from codetortoise.config import ConfigError, ToolchainConfig, parse_settings, program_settings
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.toolchain import Toolchain


def _toolchain(base):
    """A clang toolchain with its own library: base/bin/clang and base/lib/libclang.so."""
    (base / "bin").mkdir(parents=True)
    (base / "bin" / "clang").write_text("")
    (base / "lib" / "clang" / "21" / "include").mkdir(parents=True)
    (base / "lib" / "libclang.so").write_bytes(b"")
    return str(base / "bin" / "clang"), str(base / "lib" / "libclang.so")


def _toolchain_for(tmp_path, compiler, folders, **cfg):
    ws, cc = _ws(tmp_path, compiler)
    tc = Toolchain(ToolchainConfig(**cfg), load_databases(cc, ws, None), tmp_path / "d" / "tc", root=ws, folders=folders)
    return tc, str(ws / "src" / "a.c")


def test_a_workspace_added_in_the_ui_runs_compilers_only_from_the_toolchain_folders(tmp_path):
    log = tmp_path / "runs.log"
    opt = [str(tmp_path / "opt")]
    listed = _compiler(tmp_path / "opt" / "bin" / "cc", log)
    synced = _compiler(tmp_path / "other" / "tools" / "bin" / "cc", log)

    def runs(compiler, folders):
        log.unlink(missing_ok=True)
        tc, file = _toolchain_for(tmp_path, compiler, folders)
        tc.args_for(file)
        return log.exists(), tc.groups()[0].error

    assert runs(listed, opt) == (True, None)
    ran, why = runs(synced, opt)
    assert not ran and "outside the toolchain folders" in why and "server.toolchain_folders" in why
    assert runs(synced, None)[0]                                 # tortoise.yaml's workspace: as before


def test_a_compiler_path_through_a_link_is_judged_by_where_it_really_leads(tmp_path):
    log = tmp_path / "runs.log"
    (tmp_path / "y" / "z").mkdir(parents=True)
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "l").symlink_to(tmp_path / "y" / "z")
    _compiler(tmp_path / "y" / "opt" / "bin" / "cc", log)        # where the path leads: no toolchain folder
    tc, file = _toolchain_for(tmp_path, f"{tmp_path}/x/l/../opt/bin/cc", [str(tmp_path / "x" / "opt")])   # reads as x/opt
    tc.args_for(file)
    assert not log.exists() and "outside the toolchain folders" in (tc.groups()[0].error or "")


def test_a_link_that_moves_after_the_check_does_not_change_what_runs(tmp_path, monkeypatch):
    """The run executes the real file the check approved, under the name the compile database gives it."""
    log, moved = tmp_path / "runs.log", tmp_path / "moved.log"
    good = _compiler(tmp_path / "opt" / "bin" / "cc", log)
    other = _compiler(tmp_path / "other" / "cc", moved)
    link = tmp_path / "links" / "cc"
    link.parent.mkdir()
    link.symlink_to(good)
    run = subprocess.run

    def moving(args, **kw):                                      # the link moves between the check and the run
        link.unlink()
        link.symlink_to(other)
        return run(args, **kw)
    monkeypatch.setattr(subprocess, "run", moving)
    tc, file = _toolchain_for(tmp_path, str(link), [str(tmp_path / "opt")])
    tc.args_for(file)
    assert log.exists() and not moved.exists()


def test_a_workspace_added_in_the_ui_loads_libclang_only_from_the_toolchain_folders(tmp_path):
    opt = [str(tmp_path / "opt")]
    listed, listed_lib = _toolchain(tmp_path / "opt" / "vendor")
    synced, synced_lib = _toolchain(tmp_path / "other" / "tools")
    elsewhere = _toolchain(tmp_path / "home" / "llvm")[1]
    fetched = tmp_path / "d" / "libclang" / "23.1.2" / "lib" / "libclang.so.23.1.2"     # codetortoise fetch-libclang's
    (fetched.parent / "clang" / "23" / "include").mkdir(parents=True)
    fetched.write_bytes(b"")

    def library(compiler, folders, **cfg):
        tc, file = _toolchain_for(tmp_path, compiler, folders, **cfg)
        return tc.group_of(file).libclang

    assert library(listed, opt).path == listed_lib
    assert library(synced, opt).path == str(fetched)              # the synced one is passed over
    assert library(synced, None).path == synced_lib              # tortoise.yaml's workspace: as before
    refused = library(listed, opt, libclang=elsewhere)
    assert refused.path == listed_lib and f"{elsewhere}" in refused.reason and "toolchain_folders" in refused.reason


def test_a_library_reached_through_a_link_loads_from_where_the_link_led(tmp_path):
    """A parse loads the real file the check approved, so a link that moves later can't swap the library."""
    real_lib = _toolchain(tmp_path / "opt" / "vendor")[1]
    tools = tmp_path / "other" / "tools"
    (tools / "bin").mkdir(parents=True)
    (tools / "bin" / "clang").write_text("")
    (tools / "lib").mkdir()
    (tools / "lib" / "libclang.so").symlink_to(real_lib)
    tc, file = _toolchain_for(tmp_path, str(tools / "bin" / "clang"), [str(tmp_path / "opt")])
    assert tc.group_of(file).libclang.path == real_lib


def test_the_settings_that_name_programs_compare_by_what_they_name():
    assert program_settings("") == program_settings("analysis: {workers: 2}") == ()
    assert program_settings("toolchain: {target: arm, query_compilers: outside_workspace, search_paths: []}") == ()
    assert program_settings("toolchain: {clang: /opt/x/bin/clang}") != ()
    assert program_settings("toolchain: {overrides: [{match: a, clang: /x/cc}, {match: b}]}") \
        == program_settings("toolchain: {overrides: [{match: b, target: arm}, {match: a, clang: /x/cc}]}")
    assert program_settings("toolchain: {overrides: [{match: a, libclang: /x/l.so}]}") != ()
    assert program_settings("toolchain: [") == ()                  # not YAML: saving it says why


def test_settings_with_yaml_anchors_or_aliases_are_refused():
    """An alias repeats what it names without copying it, so a kilobyte of them unfolds into gigabytes."""
    with pytest.raises(ConfigError, match="anchors and aliases"):
        parse_settings("toolchain: {strip_flags: &f [-x]}\nanalysis: {entrypoint_patterns: *f}")
