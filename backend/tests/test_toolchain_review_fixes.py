"""Final-review fixes I4-I8 (toolchains branch)."""
import json
import stat

import yaml

from codetortoise.config import ToolchainConfig, load_config
from codetortoise.toolchain.compile_db import load_databases
from codetortoise.toolchain.toolchain import Toolchain

COUNTING = """#!/bin/sh
echo run >> "{log}"
case "$*" in *-dumpmachine*) echo x86_64-linux-gnu; exit 0;; esac
echo '#define FROM_DRIVER 1'
echo '#include <...> search starts here:' >&2
echo 'End of search list.' >&2
"""


def _compiler(path, log):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(COUNTING.format(log=log))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def _ws(tmp_path, compiler):
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "a.c").write_text("int a(void) { return 0; }\n")
    cc = ws / "compile_commands.json"
    cc.write_text(json.dumps([{"directory": str(ws), "file": "src/a.c", "arguments": [compiler, "-c", "src/a.c"]}]))
    return ws, cc


def test_a_compiler_inside_the_workspace_is_not_run_unless_allowed(tmp_path):
    log = tmp_path / "runs.log"
    ws, cc = _ws(tmp_path, "tools/bin/evil-cc")
    _compiler(ws / "tools" / "bin" / "evil-cc", log)
    db = load_databases(cc, ws, None)
    tc = Toolchain(ToolchainConfig(), db, tmp_path / "d" / "tc", root=ws)
    args = tc.args_for(str(ws / "src" / "a.c"))
    assert not log.exists() and not any("prelude" in a for a in args)
    [g] = tc.groups()
    assert "inside the workspace" in (g.error or "") and "query_compilers: all" in g.error
    allowed = Toolchain(ToolchainConfig(query_compilers="all"), db, tmp_path / "d" / "tc2", root=ws)
    assert any("prelude" in a for a in allowed.args_for(str(ws / "src" / "a.c"))) and log.exists()
    off = Toolchain(ToolchainConfig(query_compilers="off"), load_databases(cc, ws, None), tmp_path / "d" / "tc3", root=ws)
    log.unlink()
    off.args_for(str(ws / "src" / "a.c"))
    assert not log.exists()


def test_health_at_startup_runs_no_compiler_and_the_page_caches_its_samples(tmp_path, monkeypatch):
    from codetortoise import health
    from codetortoise.config import Config
    from codetortoise.services import build_services
    log = tmp_path / "runs.log"
    comp = _compiler(tmp_path / "bin" / "host-cc", log)
    ws, cc = _ws(tmp_path, comp)
    cfg = Config.model_validate({"owner": "o", "workspace": {"vcs": "git", "root": str(ws), "compile_commands": str(cc)},
                                 "server": {"data_dir": str(tmp_path / "d")}})
    svc = build_services(cfg)
    quick = health.run_health(svc)
    assert not log.exists() and not any(c.name.startswith("toolchain ") for c in quick.checks)
    parses = []
    real = health.run_extraction
    monkeypatch.setattr(health, "run_extraction", lambda reqs, lib, w: parses.append(1) or real(reqs, lib, w))
    deep = health.run_health(svc, deep=True)
    again = health.run_health(svc, deep=True)
    assert [c.detail for c in deep.checks if c.name.startswith("toolchain ")] == \
        [c.detail for c in again.checks if c.name.startswith("toolchain ")]
    assert len(parses) == 1                                              # one sample parse per group per process


def test_a_failed_sample_does_not_poison_the_group(tmp_path, monkeypatch):
    from codetortoise import health
    from codetortoise.config import Config
    from codetortoise.facts.model import Facts, TuInfo
    from codetortoise.services import build_services
    ws, cc = _ws(tmp_path, _compiler(tmp_path / "bin" / "host-cc", tmp_path / "runs.log"))
    cfg = Config.model_validate({"owner": "o", "workspace": {"vcs": "git", "root": str(ws), "compile_commands": str(cc)},
                                 "server": {"data_dir": str(tmp_path / "d")}})
    svc = build_services(cfg)
    monkeypatch.setattr(health, "run_extraction", lambda reqs, lib, w: [Facts(tu=TuInfo(
        file=reqs[0].file, variant="after", confidence="failed", extractor="treesitter", diagnostics=["boom"]))])
    check = next(c for c in health.run_health(svc, deep=True).checks if c.name.startswith("toolchain "))
    assert not check.ok and "fell back to tree-sitter" in check.detail
    assert all(g.error is None for g in svc.toolchain.groups())
    assert any("prelude" in a for a in svc.toolchain.args_for(str(ws / "src" / "a.c")))   # still queried for reviews


def test_override_paths_resolve_from_the_config_folder_and_unmatched_ones_are_flagged(tmp_path):
    ws = tmp_path / "ws"
    (ws / "dsp").mkdir(parents=True)
    (ws / "dsp" / "c.c").write_text("int c(void) { return 0; }\n")
    (ws / "build" / "dsp").mkdir(parents=True)
    (ws / "build" / "compile_commands.json").write_text(json.dumps(
        [{"directory": str(ws), "file": "dsp/c.c", "arguments": ["cc", "-DROOT", "-c", "dsp/c.c"]}]))
    (ws / "build" / "dsp" / "compile_commands.json").write_text(json.dumps(
        [{"directory": str(ws), "file": "dsp/c.c", "arguments": ["cc", "-DDSP", "-c", "dsp/c.c"]}]))
    cfgfile = ws / "tortoise.yaml"
    cfgfile.write_text(yaml.safe_dump({
        "owner": "o", "workspace": {"vcs": "git", "root": ".", "compile_commands": ["build/compile_commands.json",
                                                                                   "build/dsp/compile_commands.json"]},
        "toolchain": {"query_compilers": "off", "search_paths": ["tools"],
                      "overrides": [{"match": "dsp/**", "compile_commands": "build/dsp/compile_commands.json"},
                                    {"match": "nothing/**", "compile_commands": "build/missing.json"}]}}))
    cfg = load_config(cfgfile, env={})
    assert cfg.toolchain.overrides[0].compile_commands == (ws / "build" / "dsp" / "compile_commands.json").resolve()
    assert cfg.toolchain.search_paths == [str((ws / "tools").resolve())]
    db = load_databases(cfg.workspace.compile_commands, cfg.workspace.root, None)
    tc = Toolchain(cfg.toolchain, db, tmp_path / "d" / "tc", root=cfg.workspace.root)
    assert "-DDSP" in tc.args_for(str(ws / "dsp" / "c.c"))
    assert tc.unmatched_overrides() == ["nothing/**: build/missing.json is not one of the compile databases"
                                        .replace("build/missing.json", str((ws / "build" / "missing.json").resolve()))]


def test_init_comments_the_compiler_out_and_skips_the_wrapper(tmp_path):
    from codetortoise.init_config import render, scan
    ws = tmp_path / "ws"
    (ws / "build").mkdir(parents=True)
    (ws / "build" / "compile_commands.json").write_text(json.dumps(
        [{"directory": str(ws), "file": "a.c", "command": "ccache /opt/x/bin/arm-none-eabi-gcc -c a.c"}]))
    text = render(scan(ws, {}, client_root=lambda p, c: None))
    assert "\n  clang:" not in text and "  # clang: /opt/x/bin/arm-none-eabi-gcc" in text


def test_init_never_points_build_root_above_the_workspace(tmp_path):
    from codetortoise.init_config import render, scan
    ws = tmp_path / "ws"
    for d in (ws / "build", tmp_path / "build-x"):
        d.mkdir(parents=True)
        (d / "compile_commands.json").write_text("[]")
    text = render(scan(ws, {}, client_root=lambda p, c: None))
    assert "compile_commands: auto" not in text and f"build_root: {tmp_path}\n" not in text
    assert f"    - {ws / 'build' / 'compile_commands.json'}" in text
    assert f"    - {tmp_path / 'build-x' / 'compile_commands.json'}" in text
