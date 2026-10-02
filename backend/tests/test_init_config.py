"""`codetortoise init`: a starter tortoise.yaml from what the workspace already knows."""
import json

import pytest

from codetortoise.config import load_config
from codetortoise.init_config import render, scan


def _workspace(tmp_path, compiler="/usr/bin/gcc"):
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "build").mkdir()
    (ws / "build" / "compile_commands.json").write_text(json.dumps(
        [{"directory": str(ws / "build"), "file": str(ws / "src/a.c"), "arguments": [compiler, "-c", "../src/a.c"]}]))
    (ws / "node_modules" / "x").mkdir(parents=True)
    (ws / "node_modules" / "x" / "compile_commands.json").write_text("[]")      # never offered
    return ws


def test_a_written_config_loads_with_the_p4config_values_left_to_the_file(tmp_path):
    ws = _workspace(tmp_path)
    (ws / ".p4config").write_text("P4PORT=ssl:p4:1666\nP4CLIENT=anoop-ws\nP4USER=anoop\n")
    env = {"P4CONFIG": ".p4config"}
    s = scan(ws / "src", env, client_root=lambda port, client: str(ws))
    assert s.root == ws and s.compile_dbs == [ws / "build" / "compile_commands.json"]
    assert s.compiler == "/usr/bin/gcc" and s.root_matches_client is True
    text = render(s)
    assert "\np4port:" not in text and "# p4port: ssl:p4:1666" in text and "P4CONFIG file" in text
    out = tmp_path / "tortoise.yaml"
    out.write_text(text)
    cfg = load_config(out, env=env)
    assert (cfg.owner, cfg.workspace.p4port, cfg.workspace.client) == ("anoop", "ssl:p4:1666", "anoop-ws")
    assert cfg.workspace.root == ws and cfg.workspace.compile_commands == ws / "build" / "compile_commands.json"
    assert cfg.toolchain.clang == "/usr/bin/gcc" and cfg.server.host == "127.0.0.1"
    assert cfg.llm.base_url is None and cfg.swarm.url is None                    # optional sections stay commented


def test_values_only_in_the_environment_are_written_out(tmp_path):
    ws = _workspace(tmp_path)
    env = {"P4PORT": "p4:1666", "P4CLIENT": "ci-ws", "P4USER": "ci"}
    out = tmp_path / "tortoise.yaml"
    out.write_text(render(scan(ws, env, client_root=lambda port, client: str(ws))))
    cfg = load_config(out, env={})                                              # the server may not have that env
    assert (cfg.owner, cfg.workspace.p4port, cfg.workspace.client) == ("ci", "p4:1666", "ci-ws")


def test_the_client_root_is_used_from_a_subdirectory_and_a_mismatch_is_flagged(tmp_path):
    ws = _workspace(tmp_path)
    env = {"P4PORT": "p4:1666", "P4CLIENT": "ws", "P4USER": "u"}
    assert scan(ws / "src", env, client_root=lambda p, c: str(ws)).root == ws
    other = scan(ws, env, client_root=lambda p, c: "/elsewhere")
    assert other.root == ws and other.root_matches_client is False
    assert "check: the client's Root is /elsewhere" in render(other)


def test_missing_values_are_left_for_the_reader_with_how_to_find_them(tmp_path):
    ws = tmp_path / "empty"
    ws.mkdir()
    s = scan(ws, {}, client_root=lambda p, c: None)
    text = render(s)
    assert s.compile_dbs == [] and s.compiler is None
    assert "# owner:" in text and "p4 info" in text and "compile_commands.json not found" in text


def test_p4_errors_do_not_stop_init(tmp_path):
    ws = _workspace(tmp_path)

    def broken(port, client):
        raise RuntimeError("connect failed")
    s = scan(ws, {"P4PORT": "p4:1666", "P4CLIENT": "ws", "P4USER": "u"}, client_root=broken)
    assert s.root_matches_client is None and "connect failed" in s.notes[0]


def test_the_command_refuses_to_overwrite_without_force(tmp_path, monkeypatch, capsys):
    from codetortoise.cli import main
    ws = _workspace(tmp_path)
    monkeypatch.chdir(ws)
    for k in ("P4CONFIG", "P4PORT", "P4CLIENT", "P4USER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("P4USER", "anoop")
    out = tmp_path / "t.yaml"
    assert main(["init", "--root", str(ws), "--out", str(out), "--no-p4"]) == 0
    assert "owner: anoop" in out.read_text() and "next:" in capsys.readouterr().out
    assert main(["init", "--root", str(ws), "--out", str(out), "--no-p4"]) == 1
    assert "exists" in capsys.readouterr().err
    assert main(["init", "--root", str(ws), "--out", str(out), "--no-p4", "--force"]) == 0


@pytest.mark.parametrize("command,expected", [("clang++ -O2 -c a.cc", "clang++"), ('"/opt/x y/gcc" -c a.c', "/opt/x y/gcc")])
def test_the_compiler_comes_from_the_first_entry_command(tmp_path, command, expected):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "compile_commands.json").write_text(json.dumps([{"directory": str(ws), "file": "a.c", "command": command}]))
    assert scan(ws, {}, client_root=lambda p, c: None).compiler == expected


def test_without_the_clients_root_a_p4config_file_marks_the_workspace_root(tmp_path):
    ws = _workspace(tmp_path)
    (ws / ".p4config").write_text("P4USER=u\n")
    s = scan(ws / "src", {"P4CONFIG": ".p4config"}, client_root=lambda p, c: None)
    assert s.root == ws and "check: guessed from where the P4CONFIG file is" in render(s)


def test_a_build_folder_beside_the_workspace_is_searched_too(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "compile_commands.json").write_text(json.dumps([{"directory": "/", "file": "a.c",
                                                                            "command": "gcc -c a.c"}]))
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "compile_commands.json").write_text("[]")                # not a build folder: not offered
    assert scan(ws, {}, client_root=lambda p, c: None).compile_dbs == [tmp_path / "build" / "compile_commands.json"]


def test_an_expired_ticket_says_how_to_log_in(tmp_path):
    def expired(port, client):
        raise RuntimeError("p4 client: Your session has expired, please login again.")
    s = scan(tmp_path, {"P4PORT": "p4:1666", "P4CLIENT": "ws", "P4USER": "u"}, client_root=expired)
    assert "run `p4 login -a`, then run init again" in s.notes[0]
