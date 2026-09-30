import os

import pytest

from codetortoise.config import AnalysisConfig
from codetortoise.diffmap import map_changes
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import infer_layers
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.tu_select import select_tus
from codetortoise.vcs.gitfixture import GitFixtureSource


@pytest.fixture(scope="module")
def index(fx, tmp_path_factory):
    idx = SymbolIndex(tmp_path_factory.mktemp("idx") / "s.db")
    idx.build(fx.root)
    return idx


def names(paths):
    return sorted(p.split("/")[-2] + "/" + p.split("/")[-1] for p in paths)


def test_selects_changed_tus_header_includers_and_callers(fx, fx_source, index):
    dm = map_changes(fx_source.load([101, 102]))
    sel = select_tus(dm, index, CompileDb.load(fx.compile_commands), AnalysisConfig())
    assert names(sel.selected) == ["app/main.c", "driver/uart.c", "hal/regs.c", "service/logger.c"]
    assert {k.split("/")[-1]: v for k, v in sel.header_fanout.items()} == {"uart.h": 3, "regs.h": 4}
    assert sel.over_budget == 0


def test_budget_caps_selection_changed_first(fx, fx_source, index):
    dm = map_changes(fx_source.load([101]))
    sel = select_tus(dm, index, CompileDb.load(fx.compile_commands), AnalysisConfig(tu_budget=1))
    assert names(sel.selected) == ["driver/uart.c"]
    assert sel.hops == {sel.selected[0]: 0}
    assert sel.over_budget == 2  # service/logger.c (hop 1) and app/main.c (hop 2) did not fit


def test_layers_from_dependency_graph(fx, index):
    lm = infer_layers(index, str(fx.root), min_files=1)
    assert lm.module_level == {"include/hal": 0, "cpp": 0, "hal": 1, "driver": 2, "service": 3, "app": 4}
    assert [l.name for l in lm.layers] == ["L0: cpp, include/hal", "L1: hal", "L2: driver", "L3: service", "L4: app"]
    assert lm.module_of(str(fx.root / "driver/new_file.c")) == "driver"
    assert lm.level_of(str(fx.root / "service/logger.c")) == 3


def test_layers_group_small_dirs_and_cap_count(fx, index):
    lm = infer_layers(index, str(fx.root), min_files=100)
    assert lm.module_level == {".": 0}
    lm = infer_layers(index, str(fx.root), min_files=1, max_layers=2)
    assert sorted(set(lm.module_level.values())) == [0, 1]


def test_symlinked_workspace_root_still_matches_compile_db(fx, tmp_path):
    link = tmp_path / "ws-link"
    os.symlink(fx.root, link)
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(link)
    dm = map_changes(GitFixtureSource(link).load([101]))
    sel = select_tus(dm, idx, CompileDb.load(fx.compile_commands), AnalysisConfig())
    assert names(sel.selected) == ["app/main.c", "driver/uart.c", "service/logger.c"]


def test_changed_source_missing_from_compile_db_is_still_selected(fx, fx_source, index):
    full = CompileDb.load(fx.compile_commands)
    partial = CompileDb([e for e in full.entries if not e.file.endswith("driver/uart.c")])
    dm = map_changes(fx_source.load([101]))
    sel = select_tus(dm, index, partial, AnalysisConfig())
    assert "driver/uart.c" in names(sel.selected)
    assert sel.hops[[p for p in sel.selected if p.endswith("driver/uart.c")][0]] == 0


def test_layers_survive_cycles_by_dropping_weak_back_edges(tmp_path):
    files = {}
    for i in range(6):
        files[f"util/u{i}.h"] = f"int u{i}(void);\n"
        files[f"util/u{i}.c"] = f'#include "u{i}.h"\nint u{i}(void) {{ return {i}; }}\n'
        files[f"core/c{i}.c"] = f'#include "../util/u{i}.h"\nint c{i}(void) {{ return u{i}(); }}\n'
        files[f"app/a{i}.c"] = f"int a{i}(void) {{ return c{i}(); }}\n"
    files["util/u0.c"] += '#include "../core/core_cfg.h"\n'  # one real back-edge: util -> core
    files["core/core_cfg.h"] = "#define CORE_CFG 1\n"
    files["core/c1.c"] += "int t(void) { return test_helper(); }\n"  # name-matched call into tests
    files["tests/t.c"] = "int test_helper(void) { return a0(); }\n"
    for rel_path, text in files.items():
        (tmp_path / rel_path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel_path).write_text(text)
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(tmp_path)
    lm = infer_layers(idx, str(tmp_path), min_files=1)
    lv = lm.module_level
    assert lv["util"] < lv["core"] < lv["app"] <= lv["tests"]
    assert lm.cycles_broken >= 2
    assert lm.layer(lv["core"]).name.startswith(f"L{lv['core']}: core")


def test_follow_up_selects_tus_touching_fields_written_through_aliases(tmp_path):
    import json

    from codetortoise.facts.clang_extractor import TuRequest, extract_tu
    from codetortoise.tu_select import field_follow_up
    from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange

    before = '#include "a.h"\nvoid bump(struct A *a) { (void)a; }\n'
    after = '#include "a.h"\nvoid bump(struct A *a) { int *c = &a->count; *c += 1; }\n'
    files = {"a.h": "struct A { int count; };\nvoid bump(struct A *a);\n", "a.c": before,
             "user.c": '#include "a.h"\nint peek(struct A *a) { return a->count; }\n',
             "other.c": "struct B { int count; };\nint unrelated(struct B *b) { return b->count; }\n"}
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    root = str(tmp_path.resolve())
    (tmp_path / "cc.json").write_text(json.dumps([
        {"directory": root, "file": f, "arguments": ["cc", "-xc", "-c", f]} for f in ("a.c", "user.c", "other.c")]))
    cdb = CompileDb.load(tmp_path / "cc.json")
    a = f"{root}/a.c"
    dm = map_changes(ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/a.c", local=a, action="edit", before=before, after=after)]))
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(tmp_path)
    sel = select_tus(dm, idx, cdb, AnalysisConfig())
    assert names(sel.selected) == [f"{tmp_path.name}/a.c"]  # tree-sitter cannot see the alias write
    facts_after = [extract_tu(TuRequest(file=a, args=["-xc", f"-I{root}"], variant="after", unsaved={a: after}))]
    assert field_follow_up(dm, facts_after, idx, cdb, sel, AnalysisConfig()) == [f"{root}/user.c"]
