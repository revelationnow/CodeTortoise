"""Programs and libraries a workspace's settings or compile database could have the server run or load (final review
I3 of spec 2026-10-31): a workspace added in the UI runs compilers and loads libclang only from the toolchain folders
tortoise.yaml lists, judged by where a path really leads; tortoise.yaml's own workspace is not held to them."""
import errno
import grp
import json
import logging
import os
import pwd
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from test_toolchain_review_fixes import _compiler, _ws

import codetortoise.toolchain.toolchain as tcmod
from codetortoise.config import ConfigError, ToolchainConfig, parse_settings, program_settings
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.libclang import LibclangInfo
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
        == f"{tmp_path / 'f'} belongs to {owner}, who can change it (`sudo chown root {tmp_path / 'f'}` fixes it; or " \
           "move the toolchain to a folder only you and root can change)"


def _gcc(path, log, install, programs, libraries):
    """A gcc (see _compiler) that names the folders it searches when asked (-print-search-dirs): `install`, where it
    reads its specs, then the folders it looks in for the programs it runs and for its specs; asked, it logs no run."""
    cc = _compiler(path, log)
    with open(cc) as fh:
        script = fh.read()
    dirs = f"install: {install}\\nprograms: ={':'.join(programs)}\\nlibraries: ={':'.join(libraries)}\\n"
    with open(cc, "w") as fh:
        fh.write(script.replace("#!/bin/sh\n", f'#!/bin/sh\ncase "$*" in *-print-search-dirs*) printf "{dirs}"; exit 0;; '
                                "*-print-prog-name=*) exit 0;; esac\n", 1))
    return cc


def test_a_compiler_that_runs_a_program_anyone_can_change_is_not_run(tmp_path):
    """gcc preprocesses with cc1 and cc1plus, which it looks for in the folders it names when asked
    (-print-search-dirs): no one else may change one there or add one where it looks first."""
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "cc1plus").write_text("")
    cc = _gcc(tmp_path / "opt" / "bin" / "gcc", tmp_path / "runs.log", f"{tmp_path}/opt/lib/", [f"{shared}/"], [])
    shared.chmod(0o755)
    assert _runs(tmp_path, cc, [str(tmp_path / "opt")]) == (True, None)
    shared.chmod(0o777)
    assert _runs(tmp_path, cc, [str(tmp_path / "opt")]) == \
        (False, f"compiler {cc} is not run: it looks for {shared}/cc1, and anyone can add {shared}/cc1 "
                f"(`chmod o-w {shared}` fixes it)")


def test_a_compiler_whose_specs_others_could_add_is_not_run(tmp_path):
    """gcc reads a specs file from the folders it names (its install folder first), and a specs file can have cc1 load
    any library: no one else may add one where gcc looks, whether or not one is there, and a sticky folder doesn't
    stop them adding one."""
    opt = tmp_path / "opt"
    install, libexec = opt / "lib" / "gcc" / "x" / "1", opt / "libexec" / "gcc" / "x" / "1"
    install.mkdir(parents=True)
    libexec.mkdir(parents=True)
    cc = _gcc(opt / "bin" / "gcc", tmp_path / "runs.log", f"{install}/", [f"{libexec}/"], [f"{install}/", f"{opt}/x/lib/"])
    assert _runs(tmp_path, cc, [str(opt)]) == (True, None)
    install.chmod(0o1777)
    assert _runs(tmp_path, cc, [str(opt)]) == \
        (False, f"compiler {cc} is not run: it looks for {install}/specs, and anyone can add {install}/specs "
                f"(`chmod o-w {install}` fixes it)")
    install.chmod(0o755)
    (install / "specs").write_text("")
    (install / "specs").chmod(0o666)
    assert _runs(tmp_path, cc, [str(opt)]) == \
        (False, f"compiler {cc} is not run: it looks for {install}/specs, and anyone can change {install}/specs "
                f"(`chmod o-w {install}/specs` fixes it)")


@pytest.fixture
def accounts(monkeypatch):
    """Accounts to add to the system's, as the checks read them; each check below reads them afresh."""
    extra = []
    real = pwd.getpwall
    reads = []
    monkeypatch.setattr(pwd, "getpwall", lambda: reads.append(1) or [*real(), *extra])
    tcmod._private_group.cache_clear()
    yield extra, reads
    tcmod._private_group.cache_clear()


def test_a_group_another_account_has_as_its_own_is_not_the_accounts_private_group(tmp_path, accounts):
    """An account whose primary group it is belongs to it too, though the group's list doesn't name it."""
    me, mine = pwd.getpwuid(os.geteuid()), grp.getgrgid(os.getegid())
    if not (mine.gr_gid == me.pw_gid and mine.gr_name == me.pw_name and set(mine.gr_mem) <= {me.pw_name}):
        pytest.skip("the account has no private group")
    d = tmp_path / "d"
    d.mkdir()
    d.chmod(0o775)
    accounts[0].append(pwd.struct_passwd(("deploy", "x", os.geteuid() + 1000, os.getegid(), "", "/", "/bin/false")))
    assert changeable(str(d)) == f"the group {mine.gr_name} can change {d} (`chmod g-w {d}` fixes it)"


def test_the_systems_accounts_are_read_once_for_many_checks(tmp_path, accounts):
    me, mine = pwd.getpwuid(os.geteuid()), grp.getgrgid(os.getegid())
    if not (mine.gr_gid == me.pw_gid and mine.gr_name == me.pw_name and set(mine.gr_mem) <= {me.pw_name}):
        pytest.skip("the account has no private group")
    d = tmp_path / "d"
    d.mkdir()
    d.chmod(0o775)
    for _ in range(20):
        assert changeable(str(d)) is None
    assert len(accounts[1]) == 1


def test_the_checks_cost_the_same_for_one_file_as_for_many(tmp_path, monkeypatch):
    """What not_run judges is kept per compiler until the Health page looks again; a run still checks afresh."""
    walked = []
    real = tcmod.changeable
    monkeypatch.setattr(tcmod, "changeable", lambda *a, **k: walked.append(a[0]) or real(*a, **k))
    cc = _compiler(tmp_path / "opt" / "bin" / "gcc", tmp_path / "runs.log")     # no target in its name: asked for one

    def walks(n):
        ws = tmp_path / f"ws{n}"
        (ws / "src").mkdir(parents=True)
        entries = []
        for i in range(n):
            (ws / "src" / f"a{i}.c").write_text("int a(void) { return 0; }\n")
            entries.append({"directory": str(ws), "file": f"src/a{i}.c", "arguments": [cc, "-c", f"src/a{i}.c"]})
        (ws / "compile_commands.json").write_text(json.dumps(entries))
        tc = Toolchain(ToolchainConfig(), load_databases(ws / "compile_commands.json", ws, None), tmp_path / f"d{n}",
                       root=ws, folders=[str(tmp_path / "opt")])
        walked.clear()
        [g] = tc.groups()
        for i in range(n):
            tc.args_for(str(ws / "src" / f"a{i}.c"))
        assert g.files == n and g.error is None
        return len(walked)

    assert walks(40) == walks(1)


def test_a_compiler_fixed_since_runs_when_the_health_page_looks_again(tmp_path):
    """Recheck after `chmod`: what was refused is judged afresh (its target comes from its name, so its group stays)."""
    cc = _compiler(tmp_path / "opt" / "bin" / "arm-none-eabi-gcc", tmp_path / "runs.log")
    bin_ = tmp_path / "opt" / "bin"
    bin_.chmod(0o777)
    tc, file = _toolchain_for(tmp_path, cc, [str(tmp_path / "opt")])
    tc.args_for(file)
    assert "anyone can change" in (tc.groups()[0].error or "")
    bin_.chmod(0o755)
    tc.again()
    tc.args_for(file)
    assert tc.groups()[0].error is None


def test_a_library_fixed_since_loads_when_the_health_page_looks_again(tmp_path, monkeypatch):
    monkeypatch.setattr(tcmod, "library_info", lambda path: LibclangInfo(path, "21.1.0", True))
    clang, lib = _toolchain(tmp_path / "opt" / "vendor")
    libdir = tmp_path / "opt" / "vendor" / "lib"
    libdir.chmod(libdir.stat().st_mode | stat.S_IWOTH)
    tc, file = _toolchain_for(tmp_path, clang, [str(tmp_path / "opt")], libclang=lib)
    tc.prepare()
    assert tc.group_of(file).libclang.path != lib and tc.choice.path != lib
    libdir.chmod(libdir.stat().st_mode & ~stat.S_IWOTH)
    tc.again()
    tc.prepare()
    assert tc.group_of(file).libclang.path == lib and tc.choice.path == lib


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
        == f"{tmp_path / 'l'} belongs to {owner}, who can change it (`sudo chown -h root {tmp_path / 'l'}` fixes it; or " \
           "move the toolchain to a folder only you and root can change)"


def test_a_library_anyone_can_change_is_not_loaded_for_a_workspace_added_in_the_ui(tmp_path):
    clang, lib = _toolchain(tmp_path / "opt" / "vendor")
    libdir = tmp_path / "opt" / "vendor" / "lib"
    libdir.chmod(libdir.stat().st_mode | stat.S_IWOTH)
    tc, file = _toolchain_for(tmp_path, clang, [str(tmp_path / "opt")])
    chosen = tc.group_of(file).libclang
    assert chosen.path != lib and f"{lib} (anyone can change {libdir} (`chmod o-w {libdir}` fixes it))" in chosen.reason
    tc, file = _toolchain_for(tmp_path, clang, None)
    assert tc.group_of(file).libclang.path == lib                # tortoise.yaml's workspace: as before


def test_only_the_health_pages_look_judges_afresh(fx, tmp_path, monkeypatch):
    """Opening the Health page or pressing Recheck (deep) forgets what was judged; the quick checks don't."""
    from codetortoise.health import run_health
    from tests.helpers import make_services
    looks = []
    monkeypatch.setattr(Toolchain, "again", lambda self: looks.append(self))
    svc = make_services(fx, tmp_path)
    run_health(svc, deep=False)
    assert looks == []
    run_health(svc, deep=True)
    assert looks == [svc.toolchain]


def test_the_health_page_forgetting_meanwhile_doesnt_break_a_check(tmp_path):
    """again() can forget the verdicts while a review's thread is judging the same compiler."""
    class Forgetting(dict):                      # forgets right after each look, as again() in another thread may
        def __contains__(self, key):
            had = dict.__contains__(self, key)
            self.clear()
            return had

        def get(self, key, default=None):
            got = dict.get(self, key, default)
            self.clear()
            return got

    cc = _compiler(tmp_path / "opt" / "bin" / "cc", tmp_path / "runs.log")
    tc, _ = _toolchain_for(tmp_path, cc, [str(tmp_path / "opt")])
    assert tc.not_run(cc) is None
    tc._verdicts = Forgetting(tc._verdicts)
    assert tc.not_run(cc) is None


def test_a_folder_on_the_way_is_named_though_the_rest_cant_be_read(tmp_path):
    """Its owner can open it whenever they like: that, not the error, is what the host needs to know."""
    d = tmp_path / "d"
    (d / "x").mkdir(parents=True)
    d.chmod(0o777)
    (d / "x").chmod(0o000)
    try:
        assert changeable(str(d / "x" / "specs"), create=True) == f"anyone can change {d} (`chmod o-w {d}` fixes it)"
    finally:
        (d / "x").chmod(0o755)


def test_another_accounts_home_is_never_to_be_given_to_root(tmp_path, monkeypatch):
    """`chown root` of a person's home would take it from them: the fix there is to move the toolchain (final review
    of branch deferred-minors, M5)."""
    home = tmp_path / "home"
    home.mkdir()
    home.chmod(0o755)
    st = home.stat()
    monkeypatch.setattr(tcmod.pwd, "getpwuid",
                        lambda uid: pwd.struct_passwd(("amy", "x", uid, st.st_gid, "", str(home), "/bin/sh")))
    assert changeable(str(home), me=os.geteuid() + 1) \
        == f"{home} is the home of amy, who can change it (move the toolchain to a folder only you and root can change)"


def test_a_fix_inside_a_toolchains_own_folder_says_how_to_fix_all_of_it_at_once(tmp_path):
    """A toolchain unpacked with loose modes has many folders gcc looks in: the reason also gives the one command that
    fixes the whole toolchain, so the host isn't walked through one folder per Recheck (final review of branch
    deferred-minors, recommendation). Its folder is the one above the compiler's, inside a toolchain folder."""
    opt = tmp_path / "opt"
    cc = _compiler(opt / "tc" / "bin" / "gcc", tmp_path / "runs.log")
    bin_ = opt / "tc" / "bin"
    bin_.chmod(0o777)
    assert _runs(tmp_path, cc, [str(opt)]) == \
        (False, f"compiler {cc} is not run: anyone can change {bin_} (`chmod o-w {bin_}` fixes it; "
                f"`chmod -R go-w {opt / 'tc'}` fixes the whole toolchain)")
    bin_.chmod(0o755)
    opt.chmod(0o777)                                             # above the toolchain's own folder: that one alone
    assert _runs(tmp_path, cc, [str(opt)]) == \
        (False, f"compiler {cc} is not run: anyone can change {opt} (`chmod o-w {opt}` fixes it)")
    opt.chmod(0o755)
    f = opt / "tc" / "bin" / "gcc"
    owner = pwd.getpwuid(os.geteuid()).pw_name
    assert changeable(str(f), me=os.geteuid() + 1, tree=str(opt / "tc")) \
        == f"{f} belongs to {owner}, who can change it (`sudo chown root {f}` fixes it; `sudo chown -R root " \
           f"{opt / 'tc'}` fixes the whole toolchain; or move the toolchain to a folder only you and root can change)"


def _private_group_or_skip():
    me, mine = pwd.getpwuid(os.geteuid()), grp.getgrgid(os.getegid())
    if not (mine.gr_gid == me.pw_gid and mine.gr_name == me.pw_name and set(mine.gr_mem) <= {me.pw_name}):
        pytest.skip("the account has no private group")


def test_an_access_list_that_cant_be_read_is_taken_as_one_that_lets_others_write(tmp_path, monkeypatch):
    """Only "none here" and "not supported here" mean a folder has no access list (ACL); any other error reading one
    fails closed (final review of branch deferred-minors, M6)."""
    _private_group_or_skip()
    d = tmp_path / "d"
    d.mkdir()
    d.chmod(0o775)

    def unreadable(path, name, follow_symlinks=True):
        raise PermissionError(errno.EACCES, "Permission denied", path)
    monkeypatch.setattr(os, "getxattr", unreadable)
    assert changeable(str(d)) == f"the access list (ACL) of {d} can't be read (Permission denied): it may let others " \
                                 f"change it (`chmod g-w {d}` fixes it)"
    assert changeable(str(d / "specs"), create=True) == f"the access list (ACL) of {d} can't be read (Permission " \
                                                        f"denied): it may let others add {d / 'specs'} (`chmod g-w {d}` fixes it)"
    for code in (errno.ENODATA, errno.EOPNOTSUPP):
        def none(path, name, follow_symlinks=True, code=code):
            raise OSError(code, os.strerror(code), path)
        monkeypatch.setattr(os, "getxattr", none)
        assert changeable(str(d)) is None


def test_a_group_parsing_with_its_toolchains_own_library_shows_its_compilers_refusal(tmp_path):
    """Its library parses without the compiler, but a compiler the toolchain folders' rule refuses is said on the
    Health page all the same (final review of branch deferred-minors); queries a setting turns off stay quiet there, as
    before."""
    clang, lib = _toolchain(tmp_path / "opt" / "vendor")
    _compiler(Path(clang), tmp_path / "runs.log")
    vendor, bin_ = tmp_path / "opt" / "vendor", tmp_path / "opt" / "vendor" / "bin"
    bin_.chmod(0o777)
    tc, file = _toolchain_for(tmp_path, clang, [str(tmp_path / "opt")])
    tc.args_for(file)
    [g] = tc.groups()
    assert g.libclang.path == lib
    assert g.error == f"compiler {clang} is not run: anyone can change {bin_} (`chmod o-w {bin_}` fixes it; " \
                      f"`chmod -R go-w {vendor}` fixes the whole toolchain)"
    bin_.chmod(0o755)
    tc.again()
    tc.args_for(file)
    assert tc.groups()[0].error is None
    bin_.chmod(0o777)
    tc, file = _toolchain_for(tmp_path, clang, [str(tmp_path / "opt")], query_compilers="off")
    tc.args_for(file)
    assert tc.groups()[0].error is None


def test_a_refusal_is_logged_once_per_compiler_and_per_library(tmp_path, caplog):
    """A toolchain that ran before an upgrade and is refused after it shows in the log, not only on a Health page
    someone has to open; once per process (final review of branch deferred-minors, recommendation)."""
    clang, lib = _toolchain(tmp_path / "opt" / "vendor")
    _compiler(Path(clang), tmp_path / "runs.log")
    for d in ("bin", "lib"):
        (tmp_path / "opt" / "vendor" / d).chmod(0o777)
    with caplog.at_level(logging.WARNING, logger="codetortoise.toolchain.toolchain"):
        for _ in range(2):
            tc, file = _toolchain_for(tmp_path, clang, [str(tmp_path / "opt")])
            tc.args_for(file)
            tc.again()
            tc.args_for(file)
    said = [r.getMessage() for r in caplog.records]
    assert len([m for m in said if f"compiler {clang} is not run" in m]) == 1, said
    assert len([m for m in said if f"libclang {lib} (" in m]) == 1, said
