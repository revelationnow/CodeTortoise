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


COLLIDE = {
    "a.h": "struct A { int count; };\nvoid bump(struct A *a);\n",
    "user.c": '#include "a.h"\nint peek(struct A *a) { return a->count; }\n',
    "other.c": "struct B { int count; };\nint unrelated(struct B *b) { return b->count; }\n",
}
A_BEFORE = '#include "a.h"\nvoid bump(struct A *a) { (void)a; }\n'
A_AFTER = '#include "a.h"\nvoid bump(struct A *a) { int *c = &a->count; *c += 1; }\n'


def test_heuristic_field_users_restricted_to_record_includers(tmp_path):
    from codetortoise.config import AnalysisConfig
    from codetortoise.diffmap import map_changes
    from codetortoise.facts.clang_extractor import TuRequest, extract_tu
    from codetortoise.impact import build_impact
    from codetortoise.index.symbols import SymbolIndex
    from codetortoise.tu_select import TuSelection
    from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange

    for name, text in COLLIDE.items():
        (tmp_path / name).write_text(text)
    a_c = tmp_path / "a.c"
    a_c.write_text(A_BEFORE)
    a = str(a_c.resolve())
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")],
                   files=[FileChange(depot="//d/a.c", local=a, action="edit", before=A_BEFORE, after=A_AFTER)])
    dm = map_changes(cs)
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(tmp_path)
    args = ["-xc", f"-I{tmp_path}"]
    before = [extract_tu(TuRequest(file=a, args=args, variant="before", unsaved={a: A_BEFORE}))]
    after = [extract_tu(TuRequest(file=a, args=args, variant="after", unsaved={a: A_AFTER}))]
    cfg = AnalysisConfig(module_min_files=1)
    im = build_impact(before, after, dm, TuSelection(selected=[a]), idx, None, cfg)
    users = {im.nodes[e.src].label for e in im.edges if im.nodes[e.dst].label == "A::count" and e.src != im.changed[0]}
    assert users == {"peek"}  # other.c's B::count is a different record
    (f,) = [f for f in run_detectors(DetectorContext(before, after, dm, im, cfg)) if f.kind == "field_mutation"]
    assert f.severity == "medium"  # only heuristic users; not escalated to high
    assert "peek" in f.evidence[-1].text and "heuristic" in f.evidence[-1].text
