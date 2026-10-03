"""Seeing why a file doesn't parse: check-parse, Health sample parses, the facts stage message."""
import yaml

from codetortoise.facts.model import Facts, TuInfo
from codetortoise.facts.runner import parse_summary


def _f(conf, extractor="clang", diags=()):
    return Facts(tu=TuInfo(file="/w/a.c", variant="after", confidence=conf, extractor=extractor, diagnostics=list(diags)))


def test_the_stage_message_counts_outcomes_and_names_the_commonest_reason():
    facts = [_f("precise"), _f("degraded", diags=["/w/a.c:3: 'board.h' file not found"]),
             _f("degraded", diags=["/w/b.c:9: 'board.h' file not found"]),
             _f("failed", "treesitter", ["clang extractor error: boom"])]
    assert parse_summary(facts) == ("4 parse(s): 1 precise, 2 degraded, 1 tree-sitter fallback; "
                                    "most common problem (2): 'board.h' file not found")
    assert parse_summary([_f("precise")]) == "1 parse(s): 1 precise"


def _cfg(fx, tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump({"owner": "o", "workspace": {"vcs": "git", "root": str(fx.root),
                                                             "compile_commands": str(fx.compile_commands)},
                                 "server": {"data_dir": str(tmp_path / "d")}}))
    return p


def test_check_parse_explains_one_file(fx, tmp_path, capsys):
    from codetortoise.cli import main
    assert main(["check-parse", "--config", str(_cfg(fx, tmp_path)), str(fx.root / "driver" / "uart.c")]) == 0
    out = capsys.readouterr().out
    for heading in ("compile entry:", "database:", "compiler:", "target:", "libclang:", "arguments:", "result: precise"):
        assert heading in out, heading
    assert "uart_send" in out                                        # the functions found


def test_check_parse_reports_a_file_with_no_entry_and_a_fallback(fx, tmp_path, capsys):
    from codetortoise.cli import main
    missing = tmp_path / "nowhere.c"
    missing.write_text("int x(void) { return 0; }\n")
    code = main(["check-parse", "--config", str(_cfg(fx, tmp_path)), str(missing)])
    out = capsys.readouterr().out
    assert "borrowed from the nearest file in the same database" in out and code == 0   # one database: as before


def test_health_parses_one_sample_file_per_toolchain_group(fx, tmp_path):
    from codetortoise.health import run_health
    from tests.helpers import make_services
    checks = [c for c in run_health(make_services(fx, tmp_path), deep=True).checks if c.name.startswith("toolchain ")]
    # the fixture's compile commands name a compiler that may not be installed: a warning, yet the sample parses
    assert checks and all("sample" in c.detail and "parsed precise" in c.detail for c in checks)
