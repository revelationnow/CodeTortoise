import json
from pathlib import Path

import pytest

from codetortoise.config import ConfigError, effective_config, load_config, parse_settings, seed_name, valid_name


def write(tmp_path, text):
    p = tmp_path / "tortoise.yaml"
    p.write_text(text)
    return p


def test_loads_and_resolves_relative_paths(tmp_path):
    cfg = load_config(write(tmp_path, """
owner: anoop
workspace:
  vcs: p4
  p4port: ssl:p4:1666
  client: anoop-ws
  root: ws
  compile_commands: ws/build/compile_commands.json
"""))
    assert cfg.owner == "anoop"
    assert cfg.workspace.root == (tmp_path / "ws").resolve()
    assert cfg.workspace.compile_commands == (tmp_path / "ws/build/compile_commands.json").resolve()
    assert cfg.server.data_dir == (tmp_path / ".tortoise").resolve()
    assert cfg.analysis.tu_budget == 200
    assert cfg.auth.mode == "p4"


def test_p4_requires_port_and_client(tmp_path):
    with pytest.raises(ConfigError, match="workspace.p4port is not set: not in tortoise.yaml, no P4CONFIG file was found"):
        load_config(write(tmp_path, "owner: a\nworkspace: {root: /w, compile_commands: /w/cc.json}\n"), env={})


def test_port_client_and_owner_come_from_the_p4config_file(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".p4config").write_text("P4PORT=ssl:p4:1666\nP4CLIENT=anoop-ws\nP4USER=anoop\n")
    cfg = load_config(write(tmp_path, "workspace: {root: ws, compile_commands: ws/cc.json}\n"),
                      env={"P4CONFIG": ".p4config", "P4PORT": "env:1666"})
    assert (cfg.owner, cfg.workspace.p4port, cfg.workspace.client) == ("anoop", "ssl:p4:1666", "anoop-ws")
    assert cfg.workspace.p4_sources == {"p4port": f"P4CONFIG file {ws / '.p4config'}",
                                        "client": f"P4CONFIG file {ws / '.p4config'}",
                                        "owner": f"P4CONFIG file {ws / '.p4config'}"}


def test_tortoise_yaml_beats_the_p4config_file(tmp_path):
    (tmp_path / ".p4config").write_text("P4PORT=file:1666\nP4CLIENT=file-ws\n")
    cfg = load_config(write(tmp_path, "owner: a\nworkspace: {root: ., compile_commands: cc.json, p4port: yaml:1666}\n"),
                      env={"P4CONFIG": ".p4config"})
    assert (cfg.workspace.p4port, cfg.workspace.client) == ("yaml:1666", "file-ws")
    assert cfg.workspace.p4_sources["p4port"] == "tortoise.yaml"


def test_a_missing_owner_names_where_it_looked(tmp_path):
    with pytest.raises(ConfigError, match="owner is not set: not in tortoise.yaml, .*P4USER"):
        load_config(write(tmp_path, "workspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"), env={})


def test_git_workspace_needs_no_p4(tmp_path):
    cfg = load_config(write(tmp_path, "owner: a\nworkspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"))
    assert cfg.workspace.vcs == "git"


def test_invalid_yaml_is_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, "owner: [unclosed\n"))


def test_tls_cert_and_key_resolve_relative_to_the_config(tmp_path):
    (tmp_path / "certs").mkdir()
    (tmp_path / "certs/ct.pem").write_text("cert")
    (tmp_path / "certs/ct.key").write_text("key")
    cfg = load_config(write(tmp_path, """
owner: a
workspace: {vcs: git, root: /w, compile_commands: /w/cc.json}
server: {host: 0.0.0.0, tls_cert: certs/ct.pem, tls_key: certs/ct.key}
"""))
    assert cfg.server.tls_cert == (tmp_path / "certs/ct.pem").resolve()
    assert cfg.server.tls_key == (tmp_path / "certs/ct.key").resolve()


def test_settings_analysis_is_a_mapping():
    """It is laid over tortoise.yaml's analysis keys, so a number or a list says so, not a server error (final review
    M1 of spec 2026-10-31)."""
    for text in ("analysis: 5", "analysis: [workers]"):
        with pytest.raises(ConfigError, match="analysis: a mapping"):
            parse_settings(text)


def test_toolchain_folders_resolve_relative_to_the_config(tmp_path):
    cfg = load_config(write(tmp_path, """
owner: a
workspace: {vcs: git, root: /w, compile_commands: /w/cc.json}
server: {toolchain_folders: [/opt, tools]}
"""))
    assert cfg.server.toolchain_folders == ["/opt", str((tmp_path / "tools").resolve())]


def test_the_whole_disk_is_not_a_toolchain_folder(tmp_path):
    """It would hold every workspace, so a workspace added in the UI could run anything synced to it."""
    (tmp_path / "root-link").symlink_to("/")
    for entry in ("/", "/usr/..", "root-link"):
        with pytest.raises(ConfigError, match=f"server.toolchain_folders: {entry} is the whole disk"):
            load_config(write(tmp_path, "owner: a\nworkspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"
                                        f"server: {{toolchain_folders: [/opt, {entry}]}}\n"))


def test_tls_cert_without_key_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="tls_cert and server.tls_key"):
        load_config(write(tmp_path, "owner: a\nworkspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"
                                      "server: {tls_cert: ct.pem}\n"))


def test_a_missing_tls_file_is_a_config_error_not_a_startup_traceback(tmp_path):
    (tmp_path / "ct.pem").write_text("cert")
    with pytest.raises(ConfigError, match="server.tls_key: no such file"):
        load_config(write(tmp_path, "owner: a\nworkspace: {vcs: git, root: /w, compile_commands: /w/cc.json}\n"
                                      "server: {tls_cert: ct.pem, tls_key: ct.key}\n"))


def test_the_strong_model_and_its_budget_are_optional():
    from codetortoise.config import Config
    base = {"workspace": {"root": "/w", "compile_commands": "auto"}}
    cfg = Config.model_validate(base)
    assert cfg.llm.strong is None and cfg.llm.budget.tier1_per_review == 40
    cfg = Config.model_validate({**base, "llm": {"strong": {"base_url": "https://x/v1", "model": "big", "temperature": None,
                                                            "agree": 2}}})
    s = cfg.llm.strong
    assert (s.key_env, s.context_tokens, s.temperature, s.rounds, s.agree) == ("TORTOISE_STRONG_KEY", 64000, None, 20, 2)


def test_each_model_names_the_api_its_endpoint_speaks():
    import pydantic

    from codetortoise.config import Config
    from codetortoise.services import make_llm, make_strong
    base = {"workspace": {"root": "/w", "compile_commands": "auto"}}
    cfg = Config.model_validate(base)
    assert cfg.llm.api == "chat" and cfg.llm.max_output_tokens is None
    cfg = Config.model_validate({**base, "llm": {"base_url": "https://x/v1", "model": "m", "api": "responses",
                                                 "strong": {"base_url": "https://a/v1", "model": "big", "api": "messages",
                                                            "max_output_tokens": 4000}}})
    assert (cfg.llm.api, cfg.llm.strong.api, cfg.llm.strong.max_output_tokens) == ("responses", "messages", 4000)
    assert (make_llm(cfg).api, make_strong(cfg).api, make_strong(cfg).max_output_tokens) == ("responses", "messages", 4000)
    with pytest.raises(pydantic.ValidationError, match="api"):
        Config.model_validate({**base, "llm": {"api": "completions"}})


def test_the_output_token_cap_defaults_to_32768_and_reaches_both_clients():
    from codetortoise.config import Config
    from codetortoise.services import make_llm, make_strong
    base = {"workspace": {"root": "/w", "compile_commands": "auto"}}
    assert Config.model_validate(base).llm.max_output_tokens_cap == 32768
    cfg = Config.model_validate({**base, "llm": {"base_url": "https://x/v1", "model": "m", "max_output_tokens_cap": 16000,
                                                 "strong": {"base_url": "https://a/v1", "model": "big"}}})
    assert (make_llm(cfg).cap, make_strong(cfg).cap) == (16000, 16000)


def test_the_request_log_keeps_every_request_for_14_days_unless_told_otherwise():
    import pydantic

    from codetortoise.config import Config
    base = {"workspace": {"root": "/w", "compile_commands": "auto"}}
    cfg = Config.model_validate(base)
    assert (cfg.llm.request_log, cfg.llm.request_log_days) == ("all", 14)
    assert Config.model_validate({**base, "llm": {"request_log": "failed"}}).llm.request_log == "failed"
    with pytest.raises(pydantic.ValidationError, match="request_log"):
        Config.model_validate({**base, "llm": {"request_log": "some"}})


def test_shared_sink_settings_default_to_a_threshold_of_20_and_no_patterns():
    from codetortoise.config import AnalysisConfig
    a = AnalysisConfig()
    assert (a.sink_threshold, a.sink_fields) == (20, [])
    assert AnalysisConfig.model_validate({"sink_threshold": 0, "sink_fields": ["log_t::*"]}).sink_fields == ["log_t::*"]


def test_a_file_without_a_workspace_holds_the_server_settings_alone(tmp_path):
    cfg = load_config(write(tmp_path, "server:\n  port: 9000\nauth:\n  mode: dev\n"))
    assert cfg.workspace is None and cfg.server.port == 9000
    assert cfg.server.data_dir == (tmp_path / ".tortoise").resolve()


def test_the_seed_is_named_by_workspace_name_else_its_client_else_its_root_folder(tmp_path):
    named = load_config(write(tmp_path, """
owner: amy
workspace: {name: firmware, vcs: p4, p4port: "p4:1666", client: amy-ws, root: ws, compile_commands: auto}
"""))
    assert seed_name(named) == "firmware"
    by_client = load_config(write(tmp_path, """
owner: amy
workspace: {vcs: p4, p4port: "p4:1666", client: amy-ws, root: ws, compile_commands: auto}
"""))
    assert seed_name(by_client) == "amy-ws"
    by_folder = load_config(write(tmp_path, """
owner: amy
workspace: {vcs: git, root: projects/fw, compile_commands: auto}
"""))
    assert seed_name(by_folder) == "fw"


def test_names_are_1_to_40_characters_without_a_slash():
    assert valid_name("fw") and valid_name("x" * 40) and valid_name("dsp tools")
    assert not valid_name("") and not valid_name("x" * 41) and not valid_name("a/b")


ROW = {"name": "sensor", "vcs": "p4", "p4port": "ssl:p4b:1666", "client": "amy-sensor", "p4user": "amy",
       "root": "/work/sensor", "compile_commands": json.dumps("build/compile_commands.json"), "build_root": None,
       "swarm_url": "https://swarm.example.com", "settings": ""}


def test_a_workspace_takes_server_llm_and_auth_from_the_file_and_overlays_analysis(tmp_path):
    base = load_config(write(tmp_path, """
server: {port: 9000}
llm: {model: big}
auth: {mode: dev}
analysis: {workers: 2, sink_threshold: 20}
"""))
    cfg = effective_config(base, {**ROW, "settings": "analysis: {sink_threshold: 5}\n"
                                                     "toolchain: {clang: tools/clang}\n"
                                                     "targets: [{match: 'dsp/**', name: dsp}]\n"})
    assert (cfg.server.port, cfg.llm.model, cfg.auth.mode) == (9000, "big", "dev")
    assert (cfg.analysis.workers, cfg.analysis.sink_threshold) == (2, 5)
    assert (cfg.owner, cfg.workspace.name, cfg.workspace.client) == ("amy", "sensor", "amy-sensor")
    assert cfg.workspace.compile_commands == Path("/work/sensor/build/compile_commands.json")   # relative to its root
    assert cfg.toolchain.clang == "/work/sensor/tools/clang" and cfg.targets[0].name == "dsp"
    assert cfg.swarm.url == "https://swarm.example.com"
    assert base.analysis.sink_threshold == 20                       # the file's own settings are untouched


def test_workspace_settings_take_toolchain_targets_and_analysis_only():
    assert parse_settings("") == {} and parse_settings(None) == {}
    with pytest.raises(ConfigError, match="server"):
        parse_settings("server: {port: 1}")
    with pytest.raises(ConfigError, match="not YAML"):
        parse_settings("toolchain: [")
    with pytest.raises(ConfigError, match="mapping"):
        parse_settings("- a")


def test_a_bad_value_in_a_workspaces_settings_is_a_config_error(tmp_path):
    base = load_config(write(tmp_path, "auth: {mode: dev}\n"))
    with pytest.raises(ConfigError):
        effective_config(base, {**ROW, "settings": "analysis: {workers: many}"})
