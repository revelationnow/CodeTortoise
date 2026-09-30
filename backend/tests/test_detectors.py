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
    assert "logger_write checks !=0 (covers new values)" in texts
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


def test_contract_evidence_uses_constant_names():
    from codetortoise.config import AnalysisConfig
    from codetortoise.diffmap import DiffMap
    from codetortoise.facts.model import CallEdge, Facts, Function, TuInfo
    from codetortoise.impact import ImpactModel, Node

    def fn(returns, names):
        return Function(usr="c:@F@f", qualname="f", name="f", signature="int f(void)", return_type="int",
                        file="/w/a.c", start_line=1, end_line=9, returns=returns, return_names=names)

    call = CallEdge(caller="c:@F@g", callee="c:@F@f", callee_name="f", file="/w/a.c", line=12,
                    compared=["==-3"], compared_names={"==-3": "ERR_NOTFOUND"})
    before = [Facts(tu=TuInfo(file="/w/a.c", variant="before"), functions=[fn(["0", "-3"], {"-3": "ERR_NOTFOUND"})])]
    after = [Facts(tu=TuInfo(file="/w/a.c", variant="after"),
                   functions=[fn(["0", "-3", "-4"], {"-3": "ERR_NOTFOUND", "-4": "ERR_BUSY"})], calls=[call])]
    im = ImpactModel(nodes={"N1": Node(id="N1", key="c:@F@f", label="f", status="changed")}, changed=["N1"])
    (f,) = run_detectors(DetectorContext(before, after, DiffMap(), im, AnalysisConfig()))
    assert f.title == "f: new return value(s) ERR_BUSY (-4)"
    assert "checks ERR_NOTFOUND (==-3) which does not handle ERR_BUSY (-4)" in f.evidence[1].text


def _mutation_ctx(status, via):
    from codetortoise.config import AnalysisConfig
    from codetortoise.diffmap import DiffMap
    from codetortoise.facts.model import Facts, FieldAccess, Function, TuInfo
    from codetortoise.impact import Edge, ImpactModel, Node

    fn = Function(usr="c:@F@f", qualname="f", name="f", signature="int f(void)", return_type="int", file="/w/a.c",
                  start_line=1, end_line=9)
    acc = FieldAccess(fn="c:@F@f", field="c:@S@B@FI@ptr", field_name="ptr", record="B", path="out.ptr",
                      root_kind="param", mode="write", via=via, file="/w/a.c", line=3)
    before = [Facts(tu=TuInfo(file="/w/a.c", variant="before"), functions=[] if status == "added" else [fn])]
    after = [Facts(tu=TuInfo(file="/w/a.c", variant="after"), functions=[fn], fields=[acc])]
    im = ImpactModel(nodes={"N1": Node(id="N1", key="c:@F@f", label="f", status=status),
                            "N2": Node(id="N2", key="field:c:@S@B@FI@ptr", kind="field", label="B::ptr"),
                            "N3": Node(id="N3", key="c:@F@other", label="other")},
                     edges=[Edge(id="E1", src="N3", dst="N2", kind="reads")], changed=["N1"])
    return DetectorContext(before, after, DiffMap(), im, AnalysisConfig())


def test_new_function_writes_fold_into_one_info_finding():
    (f,) = run_detectors(_mutation_ctx("added", []))
    assert (f.kind, f.severity, f.title) == ("field_mutation", "info", "new function f writes 1 field(s)")
    assert "B::ptr" in f.evidence[0].text


def test_alias_claim_requires_an_alias_variable():
    (f,) = run_detectors(_mutation_ctx("changed", ["call:memcpy"]))
    assert f.title == "f now writes B::ptr" and f.severity == "high"
    (g,) = run_detectors(_mutation_ctx("changed", ["tmp"]))
    assert g.title == "f now writes B::ptr through a local alias"
