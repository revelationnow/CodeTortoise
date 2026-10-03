"""Several and nested compile databases: one lookup by file, predictable precedence (spec 2026-10-02 toolchains §2)."""
import json

from codetortoise.toolchain.compile_db import load_databases


def _db(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{"directory": str(path.parent), "file": f, "arguments": ["cc", *flags, "-c", f]}
                                for f, flags in entries]))
    return path


def _tree(tmp_path):
    ws = tmp_path / "ws"
    for f in ("app/main.c", "dsp/fir.c", "dsp/iir.c", "dsp/sub/x.c", "lib/util.c"):
        (ws / f).parent.mkdir(parents=True, exist_ok=True)
        (ws / f).write_text("")
    b = tmp_path / "build"
    _db(b / "compile_commands.json", [(str(ws / "app/main.c"), ["-DROOT"]), (str(ws / "dsp/fir.c"), ["-DROOT"])])
    _db(b / "dsp" / "compile_commands.json", [(str(ws / "dsp/fir.c"), ["-DDSP"]), (str(ws / "dsp/iir.c"), ["-DDSP"])])
    return ws, b


def _flag(db, f):
    return [a for a in db.entry_for(f).args if a.startswith("-D")]


def test_auto_finds_every_database_and_the_deepest_wins(tmp_path):
    ws, b = _tree(tmp_path)
    db = load_databases("auto", ws, b)
    assert sorted(p.split("/build")[-1] for p, _ in db.databases) == ["/compile_commands.json", "/dsp/compile_commands.json"]
    assert _flag(db, str(ws / "dsp/fir.c")) == ["-DDSP"]                 # in both: the nested build's command
    assert _flag(db, str(ws / "app/main.c")) == ["-DROOT"] and _flag(db, str(ws / "dsp/iir.c")) == ["-DDSP"]
    assert db.duplicates == 1 and len(db.files()) == 3


def test_a_list_keeps_its_order(tmp_path):
    ws, b = _tree(tmp_path)
    db = load_databases([b / "compile_commands.json", b / "dsp" / "compile_commands.json"], ws, None)
    assert _flag(db, str(ws / "dsp/fir.c")) == ["-DROOT"]                # first listed wins
    db = load_databases([str(b / "**" / "compile_commands.json")], ws, None)
    assert len(db.databases) == 2


def test_a_file_in_no_database_borrows_only_from_its_own_database(tmp_path):
    ws, b = _tree(tmp_path)
    db = load_databases("auto", ws, b)
    near = db.nearest_entry(str(ws / "dsp/sub/x.c"))
    assert near is not None and _flag(db, near.file) == ["-DDSP"]       # the dsp database, not the root one
    assert db.nearest_entry("/elsewhere/z.c") is None                    # several databases: no cross-build guess


def test_one_database_and_auto_without_a_build_root(tmp_path):
    ws, b = _tree(tmp_path)
    one = load_databases(b / "compile_commands.json", ws, None)
    assert len(one.databases) == 1 and one.nearest_entry("/elsewhere/z.h") is not None   # as before
    (ws / "build").mkdir()
    _db(ws / "build" / "compile_commands.json", [(str(ws / "lib/util.c"), ["-DIN_TREE"])])
    assert [p.split("/ws")[-1] for p, _ in load_databases("auto", ws, None).databases] == ["/build/compile_commands.json"]
    assert load_databases(tmp_path / "missing.json", ws, None).entries == []


def test_config_accepts_a_path_a_list_or_auto(tmp_path):
    from codetortoise.config import load_config
    cfg = tmp_path / "t.yaml"
    for value, expected in [("cc.json", tmp_path / "cc.json"), ("auto", "auto"),
                            (["a.json", "/abs/b.json"], [tmp_path / "a.json", "/abs/b.json"])]:
        cfg.write_text(json.dumps({"owner": "o", "workspace": {"vcs": "git", "root": str(tmp_path),
                                                               "compile_commands": value, "build_root": "build"}}))
        ws = load_config(cfg, env={}).workspace
        got = ws.compile_commands if not isinstance(ws.compile_commands, list) else [str(p) for p in ws.compile_commands]
        assert got == (expected if not isinstance(expected, list) else [str(p) for p in expected])
        assert ws.build_root == tmp_path / "build"


def test_init_writes_auto_when_it_finds_several_databases(tmp_path):
    from codetortoise.init_config import render, scan
    ws, b = _tree(tmp_path)
    (ws / "build").symlink_to(b)                        # the workspace's build folder holds both databases
    text = render(scan(ws, {}, client_root=lambda p, c: None))
    assert "  compile_commands: auto" in text and f"  build_root: {ws / 'build'}" in text


def test_health_lists_the_databases_and_duplicates(tmp_path):
    from codetortoise.config import Config
    from codetortoise.health import run_health
    from codetortoise.services import build_services
    ws, b = _tree(tmp_path)
    cfg = Config.model_validate({"owner": "o", "workspace": {"vcs": "git", "root": str(ws), "compile_commands": "auto",
                                                             "build_root": str(b)},
                                 "server": {"data_dir": str(tmp_path / "d")}})
    check = next(c for c in run_health(build_services(cfg)).checks if c.name == "compile_commands")
    assert check.ok and "3 files from 2 database(s)" in check.detail
    assert "1 file(s) listed again with different flags" in check.detail
