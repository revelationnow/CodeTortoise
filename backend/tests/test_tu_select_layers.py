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
