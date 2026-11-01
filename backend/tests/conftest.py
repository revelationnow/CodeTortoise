from types import SimpleNamespace

import pytest

from codetortoise.config import AnalysisConfig, ToolchainConfig
from codetortoise.diffmap import map_changes
from codetortoise.facts.runner import build_requests, run_extraction
from codetortoise.fixture import build_fixture
from codetortoise.impact import build_impact
from codetortoise.index.symbols import SymbolIndex
from codetortoise.layers import infer_layers
from codetortoise.toolchain import libclang as _libclang
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.tu_select import select_tus
from codetortoise.vcs.gitfixture import GitFixtureSource

# hermetic: never pick up whatever system LLVM the machine running the tests has; tests opt in explicitly
_libclang.SYSTEM_GLOBS = []


@pytest.fixture
def closed(tmp_path):
    """For tests of the rule that a workspace added in the UI runs and loads only what root and the server's account
    alone can change: skipped, saying why, when a folder above tmp_path is open to others (a TMPDIR that a shared group
    can write, say), since the rule then refuses everything below it (final review of branch deferred-minors, M8)."""
    from codetortoise.toolchain.toolchain import changeable
    why = changeable(str(tmp_path))
    if why:
        pytest.skip(f"the folders above the test's temp folder aren't closed to others ({why}); run the tests with a "
                    "TMPDIR only you and root can change")
    return tmp_path


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """Git-backed fixture workspace checked out at the base commit (CLs 101 and 102 exist as commits)."""
    return build_fixture(tmp_path_factory.mktemp("fixture"))


@pytest.fixture(scope="session")
def fx_b(tmp_path_factory):
    """A second fixture workspace, for a server hosting two."""
    return build_fixture(tmp_path_factory.mktemp("fixture_b"))


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
    im = build_impact(before, after, cs, sel, idx, layers, cfg)
    return SimpleNamespace(cfg=cfg, cs=cs, dm=dm, sel=sel, layers=layers, before=before, after=after, impact=im)
