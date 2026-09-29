import yaml

from codetortoise.cli import main


def test_fixture_demo_then_headless_review(tmp_path, capsys):
    assert main(["fixture-demo", "--dir", str(tmp_path), "--port", "9999"]) == 0
    cfg = yaml.safe_load((tmp_path / "tortoise.yaml").read_text())
    assert cfg["workspace"]["vcs"] == "git" and cfg["auth"]["mode"] == "dev" and cfg["server"]["port"] == 9999
    capsys.readouterr()
    assert main(["review", "--config", str(tmp_path / "tortoise.yaml"), "101"]) == 0
    out = capsys.readouterr().out
    assert "uart_send now writes Uart::errors through a local alias" in out
    assert "review 1: degraded" in out


def test_bad_config_exit_code(tmp_path, capsys):
    (tmp_path / "bad.yaml").write_text("owner: x\n")
    assert main(["index", "--config", str(tmp_path / "bad.yaml")]) == 2
    assert "config error" in capsys.readouterr().err
