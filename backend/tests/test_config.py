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
    with pytest.raises(ConfigError, match="p4port"):
        load_config(write(tmp_path, "owner: a\nworkspace: {root: /w, compile_commands: /w/cc.json}\n"))


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
