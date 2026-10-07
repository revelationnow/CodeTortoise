import pytest

from codetortoise.config import ConfigError, load_config


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
