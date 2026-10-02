"""Perforce settings from the P4CONFIG file, the way p4 finds them."""
from codetortoise.vcs.p4settings import p4_settings


def test_reads_the_named_file_from_the_workspace_or_a_parent(tmp_path):
    ws = tmp_path / "main" / "ws"
    ws.mkdir(parents=True)
    (tmp_path / "main" / ".p4config").write_text("# team settings\n\nP4PORT=ssl:p4:1666\nP4CLIENT = anoop-ws\nP4USER=anoop\n")
    s = p4_settings(ws, {"P4CONFIG": ".p4config"})
    assert s.values == {"P4PORT": "ssl:p4:1666", "P4CLIENT": "anoop-ws", "P4USER": "anoop"}
    assert s.file == tmp_path / "main" / ".p4config"
    assert s.source("P4PORT") == f"P4CONFIG file {tmp_path / 'main' / '.p4config'}"


def test_the_nearest_file_wins_and_an_absolute_path_is_used_as_is(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / ".p4config").write_text("P4PORT=far:1666\n")
    (ws / ".p4config").write_text("P4PORT=near:1666\n")
    assert p4_settings(ws, {"P4CONFIG": ".p4config"}).values["P4PORT"] == "near:1666"
    other = tmp_path / "elsewhere.cfg"
    other.write_text("P4PORT=abs:1666\n")
    assert p4_settings(ws, {"P4CONFIG": str(other)}).values["P4PORT"] == "abs:1666"


def test_the_file_beats_the_environment_which_fills_the_rest(tmp_path):
    (tmp_path / ".p4config").write_text("P4CLIENT=from-file\n")
    s = p4_settings(tmp_path, {"P4CONFIG": ".p4config", "P4CLIENT": "from-env", "P4PORT": "env:1666"})
    assert s.get("P4CLIENT") == "from-file" and s.get("P4PORT") == "env:1666"
    assert s.source("P4PORT") == "environment variable P4PORT"
    assert s.get("P4USER") is None and s.source("P4USER") is None


def test_no_p4config_or_no_file_falls_back_to_the_environment(tmp_path):
    assert p4_settings(tmp_path, {"P4PORT": "env:1666"}).get("P4PORT") == "env:1666"
    s = p4_settings(tmp_path, {"P4CONFIG": ".missing"})
    assert s.file is None and s.get("P4PORT") is None
