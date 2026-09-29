import shutil

import pytest

from codetortoise.vcs.gitfixture import GitFixtureSource
from codetortoise.vcs.source import SourceError


def test_loads_cls_sorted_with_before_after(fx_source, fx):
    cs = fx_source.load([102, 101])
    assert [c.cl for c in cs.cls] == [101, 102]
    assert cs.cls[0].description == "uart: count tx stats and report overflow"
    depots = [f.depot for f in cs.files]
    assert depots == ["//fixture/driver/uart.c", "//fixture/driver/uart.h", "//fixture/hal/regs.c",
                      "//fixture/include/hal/regs.h"]
    uart_c = cs.files[0]
    assert uart_c.action == "edit"
    assert "return -2;" in uart_c.after and "return -2;" not in uart_c.before
    assert uart_c.local == str((fx.root / "driver/uart.c").resolve())
    assert cs.drift == []


def test_unknown_cl_raises(fx_source):
    with pytest.raises(SourceError, match="CL 999 not found"):
        fx_source.load([999])


def test_drift_when_workspace_differs(tmp_path, fx):
    ws = tmp_path / "ws"
    shutil.copytree(fx.root, ws, symlinks=True)
    (ws / "driver/uart.c").write_text("/* locally modified */\n")
    cs = GitFixtureSource(ws).load([101])
    assert [d.depot for d in cs.drift] == ["//fixture/driver/uart.c"]
