"""Programs and libraries a workspace's settings or compile database could have the server run or load (final review
I3 of spec 2026-10-31): what is synced into any workspace folder is not run, and for a workspace added in the UI its
toolchain's own library is not loaded either, unless the owner of tortoise.yaml's workspace allows it."""
from test_toolchain_review_fixes import _compiler, _ws

from codetortoise.config import ToolchainConfig
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.toolchain import Toolchain


def _toolchain(base):
    """A clang toolchain with its own library: base/bin/clang and base/lib/libclang.so."""
    (base / "bin").mkdir(parents=True)
    (base / "bin" / "clang").write_text("")
    (base / "lib" / "clang" / "21" / "include").mkdir(parents=True)
    (base / "lib" / "libclang.so").write_bytes(b"")
    return str(base / "bin" / "clang"), str(base / "lib" / "libclang.so")


def test_a_compiler_inside_any_workspace_on_this_server_is_not_run(tmp_path):
    log = tmp_path / "runs.log"
    other = tmp_path / "other"
    ws, cc = _ws(tmp_path, _compiler(other / "tools" / "bin" / "evil-cc", log))
    tc = Toolchain(ToolchainConfig(), load_databases(cc, ws, None), tmp_path / "d" / "tc", root=ws,
                   roots=lambda: [str(ws), str(other)])
    args = tc.args_for(str(ws / "src" / "a.c"))
    [g] = tc.groups()
    assert not log.exists() and not any("prelude" in a for a in args)
    assert "inside another workspace" in (g.error or "") and "query_compilers: all" in g.error


def test_a_workspace_added_in_the_ui_loads_no_library_beside_a_compiler_in_a_workspace(tmp_path):
    other = tmp_path / "other"
    synced, synced_lib = _toolchain(other / "tools")                # checked into a depot, synced into a workspace
    installed, installed_lib = _toolchain(tmp_path / "opt" / "vendor")     # installed outside every workspace

    def library(compiler, trusted, **cfg):
        ws, cc = _ws(tmp_path, compiler)
        tc = Toolchain(ToolchainConfig(**cfg), load_databases(cc, ws, None), tmp_path / "d" / "tc", root=ws,
                       roots=lambda: [str(ws), str(other)], trusted=trusted)
        return tc.group_of(str(ws / "src" / "a.c")).libclang.path

    assert library(synced, trusted=False) != synced_lib
    assert library(synced, trusted=False, query_compilers="all") == synced_lib    # the host allowed it
    assert library(synced, trusted=True) == synced_lib             # tortoise.yaml's workspace: as before
    assert library(installed, trusted=False) == installed_lib      # a toolchain outside the workspaces: as before


def test_the_settings_that_name_programs_compare_by_what_they_name():
    from codetortoise.config import program_settings
    assert program_settings("") == program_settings("analysis: {workers: 2}") == ()
    assert program_settings("toolchain: {target: arm, query_compilers: outside_workspace, search_paths: []}") == ()
    assert program_settings("toolchain: {clang: /opt/x/bin/clang}") != ()
    assert program_settings("toolchain: {overrides: [{match: a, clang: /x/cc}, {match: b}]}") \
        == program_settings("toolchain: {overrides: [{match: b, target: arm}, {match: a, clang: /x/cc}]}")
    assert program_settings("toolchain: {overrides: [{match: a, libclang: /x/l.so}]}") != ()
    assert program_settings("toolchain: [") == ()                  # not YAML: saving it says why
