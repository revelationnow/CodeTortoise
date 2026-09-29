from codetortoise.detectors.base import DetectorContext, Evidence, max_severity, run_detectors


def findings_for(a):
    return run_detectors(DetectorContext(a.before, a.after, a.dm, a.impact, a.cfg))


def test_fixture_findings(analysed):
    findings = findings_for(analysed)
    got = [(f.id, f.severity, f.kind, f.title) for f in findings]
    assert got == [
        ("F1", "high", "field_mutation", "uart_send now writes Uart::errors through a local alias"),
        ("F2", "high", "header_fanout", "regs.h: 1 change(s) reach 4 TU(s)"),
        ("F3", "high", "header_fanout", "uart.h: 1 change(s) reach 3 TU(s)"),
        ("F4", "medium", "contract", "hal_write: signature changed"),
        ("F5", "medium", "contract", "uart_send: new return value(s) -2"),
        ("F6", "medium", "field_mutation", "uart_send now writes Stats::tx through a local alias"),
    ]
    f5 = findings[4]
    texts = [e.text for e in f5.evidence]
    assert "logger_flush ignores the result" in texts
    assert "logger_write checks ['!=0'] (covers new values)" in texts
    f1 = findings[0]
    assert f1.evidence[0].text == "write `u.errors` via err (precise)"
    assert "uart_errors" in f1.evidence[-1].text


def test_max_severity():
    assert max_severity([Evidence(text="a", severity="low"), Evidence(text="b", severity="high")]) == "high"
    assert max_severity([], floor="low") == "low"


def test_custom_detector_list_and_id_assignment(analysed):
    from codetortoise.detectors.base import Finding

    def fake(ctx):
        return [Finding(kind="z", severity="low", title="b", summary="s"),
                Finding(kind="a", severity="high", title="a", summary="s")]

    out = run_detectors(DetectorContext(analysed.before, analysed.after, analysed.dm, analysed.impact, analysed.cfg), [fake])
    assert [(f.id, f.kind) for f in out] == [("F1", "a"), ("F2", "z")]
