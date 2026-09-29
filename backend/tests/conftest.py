from types import SimpleNamespace

import pytest

from codetortoise.config import AnalysisConfig, ToolchainConfig
from codetortoise.diffmap import map_changes
from codetortoise.facts.runner import build_requests, run_extraction
from codetortoise.fixture import build_fixture
from codetortoise.impact import build_impact
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import infer_layers
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.tu_select import select_tus
from codetortoise.vcs.gitfixture import GitFixtureSource


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """Git-backed fixture workspace checked out at the base commit (CLs 101 and 102 exist as commits)."""
    return build_fixture(tmp_path_factory.mktemp("fixture"))


@pytest.fixture(scope="session")
def fx_source(fx):
    return GitFixtureSource(fx.root)


@pytest.fixture(scope="session")
def analysed(fx, fx_source, tmp_path_factory):
    """CLs 101+102 run through diffmap, TU selection, clang facts and the impact model."""
    tmp = tmp_path_factory.mktemp("impact")
    cfg = AnalysisConfig(module_min_files=1)
    cs = fx_source.load([101, 102])
    dm = map_changes(cs)
    idx = SymbolIndex(tmp / "s.db")
    idx.build(fx.root)
    cdb = CompileDb.load(fx.compile_commands)
    tc = Toolchain(ToolchainConfig(), cdb, tmp / "tc")
    tc.prepare()
    sel = select_tus(dm, idx, cdb, cfg)
    layers = infer_layers(idx, str(fx.root), 1)
    before = run_extraction(build_requests(sel, cs, tc, "before"), None, 1)
    after = run_extraction(build_requests(sel, cs, tc, "after"), None, 1)
    im = build_impact(before, after, dm, sel, idx, layers, cfg)
    return SimpleNamespace(cfg=cfg, cs=cs, dm=dm, sel=sel, layers=layers, before=before, after=after, impact=im)
