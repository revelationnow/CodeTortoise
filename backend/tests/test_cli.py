import json

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


def test_plain_http_on_the_network_is_warned_about():
    from pathlib import Path

    from codetortoise.cli import plain_http_warning
    from codetortoise.config import ServerConfig
    w = plain_http_warning(ServerConfig(host="0.0.0.0", port=8767))
    assert w is not None and w.startswith("Serving plain HTTP on 0.0.0.0:8767")
    assert "Set server.tls_cert/tls_key, or bind 127.0.0.1." in w
    for host in ("192.168.1.122", "::", "myhost.local"):                  # IPv6 any-address and host names too
        assert plain_http_warning(ServerConfig(host=host)) is not None
    for host in ("127.0.0.1", "127.0.1.1", "::1", "localhost"):
        assert plain_http_warning(ServerConfig(host=host)) is None
    tls = ServerConfig(host="0.0.0.0", tls_cert=Path("/c.pem"), tls_key=Path("/c.key"))
    assert plain_http_warning(tls) is None


def _logged_review(tmp_path):
    from codetortoise.config import load_config
    from codetortoise.llm import request_log
    from codetortoise.llm.ledger import Ledger
    from codetortoise.store import Store
    assert main(["fixture-demo", "--dir", str(tmp_path), "--port", "9999"]) == 0
    cfg = load_config(tmp_path / "tortoise.yaml")
    store = Store(cfg.server.data_dir / "tortoise.db")
    rid = store.create_review("t", "demo", [101])
    call = Ledger(store, cfg.llm.budget).reserve(rid, None, "stories", "chunk 1", "big")
    request_log.write(store, call, rid, [{"seq": 1, "sent_at": "2026-10-08T10:00:00+00:00", "elapsed_ms": 900,
                                          "url": "/v1/chat/completions", "model": "big", "status": 200, "error": None,
                                          "stop_reason": "length", "truncated": True, "repair": False,
                                          "max_output_tokens": 1000, "prompt_tokens": 50, "completion_tokens": 1000,
                                          "request": {"model": "big"}, "response": '{"choices": []}'}])
    return rid, call


def test_llm_log_prints_one_line_per_request_and_writes_the_files(tmp_path, capsys):
    rid, call = _logged_review(tmp_path)
    capsys.readouterr()
    cfg = str(tmp_path / "tortoise.yaml")
    assert main(["llm-log", "--config", cfg, str(rid), "--out", str(tmp_path / "log")]) == 0
    out = capsys.readouterr().out
    assert f"call {call} stories chunk 1 big #1 200 length limit=1000 tokens=50+1000 900ms" in out
    one = json.loads((tmp_path / "log" / f"call-{call}" / "1.json").read_text())
    assert one["request"] == {"model": "big"} and one["response"] == {"choices": []} and one["truncated"] is True
    assert main(["llm-log", "--config", cfg, str(rid), "--call", str(call + 1)]) == 0
    assert capsys.readouterr().out.strip() == f"no requests logged for review {rid}"
