"""Programs and libraries a workspace's settings or compile database could have the server run or load (final review
I3 of spec 2026-10-31): a workspace added in the UI runs compilers and loads libclang only from the toolchain folders
tortoise.yaml lists, judged by where a path really leads; tortoise.yaml's own workspace is not held to them."""
import grp
import os
import pwd
import shutil
import stat
import subprocess

import pytest
from test_toolchain_review_fixes import _compiler, _ws

from codetortoise.config import ConfigError, ToolchainConfig, parse_settings, program_settings
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.toolchain import Toolchain, changeable


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


def _runs(tmp_path, compiler, folders):
    """Whether a workspace held to `folders` (None: tortoise.yaml's) runs `compiler`, and why not."""
    log = tmp_path / "runs.log"
    log.unlink(missing_ok=True)
    tc, file = _toolchain_for(tmp_path, compiler, folders)
    tc.args_for(file)
    return log.exists(), tc.groups()[0].error


def test_a_compiler_anyone_can_change_is_not_run_for_a_workspace_added_in_the_ui(tmp_path):
    """The owner's choice (2026-11-01): a workspace added in the UI runs a compiler only when no one but root and the
    server's own account can change it or a folder above it; the reason says how to fix it. tortoise.yaml's workspace
    is not held to this."""
    cc = _compiler(tmp_path / "opt" / "bin" / "cc", tmp_path / "runs.log")
    opt, bin_ = [str(tmp_path / "opt")], tmp_path / "opt" / "bin"
    bin_.chmod(0o755)
    (tmp_path / "opt").chmod(0o1777)                             # others can add to it, but can't swap what is mine
    assert _runs(tmp_path, cc, opt) == (True, None)
    bin_.chmod(0o777)
    assert _runs(tmp_path, cc, opt) == (False, f"compiler {cc} is not run: anyone can change {bin_} "
                                               f"(`chmod o-w {bin_}` fixes it)")
    assert _runs(tmp_path, cc, None)[0]                          # tortoise.yaml's workspace: as before


def test_a_compiler_a_shared_group_can_change_is_not_run_but_the_accounts_own_group_may(tmp_path):
    """A group may write only when it is the account's own private group (named after it, no other member), as
    Debian's sshd judges it: on a system whose umask is 002 that is every folder the owner makes."""
    cc = _compiler(tmp_path / "opt" / "bin" / "cc", tmp_path / "runs.log")
    opt, bin_ = [str(tmp_path / "opt")], tmp_path / "opt" / "bin"
    bin_.chmod(0o775)
    me, mine = pwd.getpwuid(os.geteuid()), grp.getgrgid(os.getegid())
    if mine.gr_name == me.pw_name and set(mine.gr_mem) <= {me.pw_name}:
        assert _runs(tmp_path, cc, opt) == (True, None)
    shared = [g for g in os.getgroups() if g != os.getegid()]
    if not shared:
        pytest.skip("the account is in no other group to share a folder with")
    os.chown(bin_, -1, shared[0])
    name = grp.getgrgid(shared[0]).gr_name
    assert _runs(tmp_path, cc, opt) == (False, f"compiler {cc} is not run: the group {name} can change {bin_} "
                                               f"(`chmod g-w {bin_}` fixes it)")


def test_the_accounts_own_group_may_not_change_a_folder_whose_access_list_names_others(tmp_path):
    """With an access list (ACL), a folder's group bits are the most it lets the users and groups it names do."""
    me, mine = pwd.getpwuid(os.geteuid()), grp.getgrgid(os.getegid())
    if not (mine.gr_gid == me.pw_gid and mine.gr_name == me.pw_name and set(mine.gr_mem) <= {me.pw_name}):
        pytest.skip("the account has no private group")
    d = tmp_path / "d"
    d.mkdir()
    d.chmod(0o775)
    assert changeable(str(d)) is None
    if not shutil.which("setfacl") or subprocess.run(["setfacl", "-m", "u:nobody:rwx", str(d)]).returncode:
        pytest.skip("no access lists here")
    assert changeable(str(d)) == f"an access list (ACL) on {d} can let others change it (`chmod g-w {d}` fixes it)"


def test_a_path_another_account_owns_is_one_it_can_change(tmp_path):
    (tmp_path / "f").write_text("")
    os.chmod(tmp_path / "f", 0o644)
    owner = pwd.getpwuid(os.geteuid()).pw_name
    assert changeable(str(tmp_path / "f")) is None
    assert changeable(str(tmp_path / "f"), me=os.geteuid() + 1) \
        == f"{tmp_path / 'f'} belongs to {owner}, who can change it (`sudo chown root {tmp_path / 'f'}` fixes it)"


def test_a_compiler_that_runs_a_program_anyone_can_change_is_not_run(tmp_path):
    """gcc preprocesses with cc1 and cc1plus, which it names when asked (-print-prog-name): they are held to the same
    rule as the compiler."""
    log, shared = tmp_path / "runs.log", tmp_path / "shared"
    shared.mkdir()
    helper = shared / "cc1plus"
    helper.write_text("")
    cc = _compiler(tmp_path / "opt" / "bin" / "gcc", log)
    with open(cc) as fh:
        script = fh.read()
    with open(cc, "w") as fh:                    # asked for its programs, it runs none of them and logs no run
        fh.write(script.replace("#!/bin/sh\n", "#!/bin/sh\ncase \"$*\" in "
                                f"*-print-prog-name=cc1plus*) echo {helper}; exit 0;; *-print-prog-name=*) exit 0;; esac\n", 1))
    shared.chmod(0o755)
    assert _runs(tmp_path, cc, [str(tmp_path / "opt")]) == (True, None)
    shared.chmod(0o777)
    assert _runs(tmp_path, cc, [str(tmp_path / "opt")]) == \
        (False, f"compiler {cc} is not run: it runs {helper}, and anyone can change {shared} (`chmod o-w {shared}` fixes it)")


def test_a_compiler_named_through_a_link_others_can_swap_is_not_run(tmp_path):
    """gcc finds the programs it runs from the name it is run by, so a link on the way to it that others could swap
    would send it elsewhere: every folder and link on the way is held to the rule, not only where it leads."""
    cc = _compiler(tmp_path / "opt" / "bin" / "cc", tmp_path / "runs.log")
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "cc").symlink_to(cc)
    shared.chmod(0o755)
    assert _runs(tmp_path, str(shared / "cc"), [str(tmp_path / "opt")]) == (True, None)
    shared.chmod(0o777)
    assert _runs(tmp_path, str(shared / "cc"), [str(tmp_path / "opt")]) == \
        (False, f"compiler {shared / 'cc'} is not run: anyone can change {shared} (`chmod o-w {shared}` fixes it)")


def test_a_link_another_account_owns_is_one_it_can_swap(tmp_path):
    (tmp_path / "l").symlink_to("/usr")
    owner = pwd.getpwuid(os.geteuid()).pw_name
    assert changeable(str(tmp_path / "l")) is None
    assert changeable(str(tmp_path / "l"), me=os.geteuid() + 1) \
        == f"{tmp_path / 'l'} belongs to {owner}, who can change it (`sudo chown -h root {tmp_path / 'l'}` fixes it)"


def test_a_library_anyone_can_change_is_not_loaded_for_a_workspace_added_in_the_ui(tmp_path):
    clang, lib = _toolchain(tmp_path / "opt" / "vendor")
    libdir = tmp_path / "opt" / "vendor" / "lib"
    libdir.chmod(libdir.stat().st_mode | stat.S_IWOTH)
    tc, file = _toolchain_for(tmp_path, clang, [str(tmp_path / "opt")])
    chosen = tc.group_of(file).libclang
    assert chosen.path != lib and f"{lib} (anyone can change {libdir} (`chmod o-w {libdir}` fixes it))" in chosen.reason
    tc, file = _toolchain_for(tmp_path, clang, None)
    assert tc.group_of(file).libclang.path == lib                # tortoise.yaml's workspace: as before
