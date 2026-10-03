"""Symbol index at production scale: flat memory, compile-DB scope, incremental rebuilds."""
import os
import sqlite3

from codetortoise.index.symbols import SymbolIndex, _parse_file


def _tree(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return str(tmp_path.resolve())


def _short(root, paths):
    return sorted(p.replace(root + "/", "") for p in paths)


def test_results_are_written_in_batches_while_parsing(tmp_path):
    root = _tree(tmp_path / "ws", {f"f{i}.c": f"int f{i}(void) {{ return 0; }}\n" for i in range(9)})
    db = tmp_path / "s.db"
    committed = []

    def parser(path):
        with sqlite3.connect(str(db)) as c:                                   # what another reader sees right now
            committed.append(c.execute("SELECT COUNT(*) FROM sym_files").fetchone()[0])
        return _parse_file(path)
    idx = SymbolIndex(db)
    assert idx.build(tmp_path / "ws", parser=parser, batch=2) == 9
    assert committed[:3] == [0, 0, 2] and committed[-1] == 8                # never all held back until the end
    assert len(idx.files()) == 9 and root


def test_compile_db_scope_indexes_its_files_and_the_headers_they_include(tmp_path):
    root = _tree(tmp_path, {"app/main.c": '#include "lib.h"\nint main(void) { return lib(); }\n',
                            "inc/lib.h": '#include "types.h"\nint lib(void);\n',
                            "inc/types.h": "typedef int t;\n",
                            "inc/unused.h": "int unused(void);\n",
                            "tools/other.c": "int other(void) { return 0; }\n"})
    idx = SymbolIndex(tmp_path / "s.db")
    n = idx.build(tmp_path, seeds=[f"{root}/app/main.c"], include_dirs=[f"{root}/inc"])
    assert _short(root, idx.files()) == ["app/main.c", "inc/lib.h", "inc/types.h"]   # transitive headers, nothing else
    assert n == 3 and [c.path.split("/")[-1] for c in idx.callers_of("lib")] == ["main.c"]


def test_a_rebuild_reparses_only_changed_files_and_drops_deleted_ones(tmp_path):
    root = _tree(tmp_path, {"a.c": "int a(void) { return b(); }\n", "b.c": "int b(void) { return 0; }\n",
                            "c.c": "int c(void) { return 0; }\n"})
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(tmp_path)
    parsed = []

    def parser(path):
        parsed.append(path.split("/")[-1])
        return _parse_file(path)
    (tmp_path / "b.c").write_text("int b(void) { return a(); }\n")
    st = os.stat(tmp_path / "b.c")
    os.utime(tmp_path / "b.c", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))  # a later modification time
    (tmp_path / "c.c").unlink()
    gen = idx.generation()
    assert idx.build(tmp_path, parser=parser) == 2
    assert parsed == ["b.c"] and _short(root, idx.files()) == ["a.c", "b.c"]
    assert [c.path.split("/")[-1] for c in idx.callers_of("a")] == ["b.c"] and idx.defs("c") == []
    assert idx.generation() == gen + 1
    parsed.clear()
    idx.build(tmp_path, parser=parser, full=True)                              # --full re-parses everything
    assert sorted(parsed) == ["a.c", "b.c"]


def test_moving_from_workspace_scope_to_compile_db_scope_drops_out_of_scope_files(tmp_path):
    root = _tree(tmp_path, {"a.c": "int a(void) { return 0; }\n", "b.c": "int b(void) { return 0; }\n"})
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(tmp_path)
    idx.build(tmp_path, seeds=[f"{root}/a.c"])
    assert _short(root, idx.files()) == ["a.c"] and idx.defs("b") == []


def _service(tmp_path):
    import json

    from codetortoise.config import Config
    from codetortoise.services import build_services
    root = _tree(tmp_path / "ws", {"app/main.c": '#include "lib.h"\nint main(void) { return lib(); }\n',
                                   "app/lib.h": "int lib(void);\n", "tools/gen.c": "int gen(void) { return 0; }\n"})
    cc = tmp_path / "ws" / "compile_commands.json"
    cc.write_text(json.dumps([{"directory": root, "file": "app/main.c", "arguments": ["cc", "-c", "app/main.c"]}]))
    cfg = Config.model_validate({"owner": "o", "workspace": {"vcs": "git", "root": root, "compile_commands": str(cc)},
                                 "server": {"data_dir": str(tmp_path / "d")}})
    return build_services(cfg), root


def test_the_service_indexes_the_compile_database_scope_by_default(tmp_path):
    svc, root = _service(tmp_path)
    svc.build_index()
    assert _short(root, svc.index.files()) == ["app/lib.h", "app/main.c"]        # not tools/gen.c
    svc.cfg.analysis.index_scope = "workspace"
    svc.build_index()
    assert _short(root, svc.index.files()) == ["app/lib.h", "app/main.c", "tools/gen.c"]


def test_an_empty_compile_database_falls_back_to_the_workspace(tmp_path):
    svc, root = _service(tmp_path)
    svc.cdb.entries.clear()
    svc.build_index()
    assert len(svc.index.files()) == 3


def test_index_command_full_flag(fx, tmp_path, monkeypatch):
    import yaml

    from codetortoise import services
    from codetortoise.cli import main
    seen = []
    monkeypatch.setattr(services.Services, "build_index", lambda self, full=False: seen.append(full) or 0)
    cfg = tmp_path / "t.yaml"
    cfg.write_text(yaml.safe_dump({"owner": "o", "workspace": {"vcs": "git", "root": str(fx.root),
                                                                 "compile_commands": str(fx.compile_commands)},
                                   "server": {"data_dir": str(tmp_path / "d")}}))
    assert main(["index", "--config", str(cfg)]) == 0 and main(["index", "--config", str(cfg), "--full"]) == 0
    assert seen == [False, True]
