import pytest

from codetortoise.fixture import build_fixture
from codetortoise.vcs.gitfixture import GitFixtureSource


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """Git-backed fixture workspace checked out at the base commit (CLs 101 and 102 exist as commits)."""
    return build_fixture(tmp_path_factory.mktemp("fixture"))


@pytest.fixture(scope="session")
def fx_source(fx):
    return GitFixtureSource(fx.root)
