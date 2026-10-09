def by_label(im):
    return {n.label: n for n in im.nodes.values()}


def test_changed_nodes_and_layers(analysed):
    im = analysed.impact
    nodes = by_label(im)
    assert sorted(im.nodes[n].label for n in im.changed) == ["hal_write", "uart_send"]
    assert nodes["uart_send"].status == "changed" and nodes["uart_send"].layer == 2
    assert nodes["main"].layer == 4 and nodes["Stats::tx"].kind == "field"


def test_new_data_edges_are_added(analysed):
    im = analysed.impact
    nodes = by_label(im)
    edges = {(im.nodes[e.src].label, e.kind, im.nodes[e.dst].label): e for e in im.edges}
    assert edges[("uart_send", "writes", "Stats::tx")].status == "added"
    assert edges[("uart_send", "writes", "Uart::errors")].status == "added"
    assert edges[("logger_flush", "call", "uart_send")].status == "unchanged"
    assert ("logger_write", "writes", "Logger::uart") not in edges  # passing lg->uart on is not a field write
    flow = next(f for f in im.flows if f.root == nodes["uart_send"].id)
    assert [im.nodes[n].label for n in flow.nodes] == ["uart_send", "hal_write", "logger_flush", "logger_write", "main"]


def test_blast_radius_call_and_data(analysed):
    im = analysed.impact
    blast = {im.nodes[b.node].label: b for b in im.blast}
    assert blast["logger_flush"].hop == 1 and blast["logger_flush"].via == "call"
    assert blast["uart_errors"].via == "data"  # reads Uart::errors, newly written by uart_send
    assert blast["main"].hop == 2
    assert blast["uart_init"].score > blast["logger_flush"].score  # main is an entry point two layers up
    assert [im.nodes[p].label for p in blast["main"].path] == ["main", "uart_init", "hal_write"]


def test_header_fanout_counts_tus_by_layer(analysed):
    im = analysed.impact
    fan = {f.header.split("/")[-1]: f for f in im.fanout}
    assert fan["uart.h"].total_tus == 3
    assert fan["uart.h"].by_layer == {"L2: driver": 1, "L3: service": 1, "L4: app": 1}


def test_heuristic_fan_in_is_capped(analysed, fx):
    from codetortoise.config import AnalysisConfig
    from codetortoise.impact import build_impact
    from codetortoise.index.symbols import SymbolIndex
    from codetortoise.tu_select import TuSelection

    a = analysed
    uart = [p for p in a.sel.selected if p.endswith("driver/uart.c")]
    only_uart = TuSelection(selected=uart)
    before = [f for f in a.before if f.tu.file in uart]
    after = [f for f in a.after if f.tu.file in uart]
    idx = SymbolIndex(fx.root.parent / "cap.db")
    idx.build(fx.root)
    open_im = build_impact(before, after, a.dm, only_uart, idx, a.layers, AnalysisConfig(module_min_files=1))
    labels = {n.label for n in open_im.nodes.values() if n.confidence == "heuristic"}
    assert {"logger_write", "logger_flush"} <= labels
    capped = build_impact(before, after, a.dm, only_uart, idx, a.layers,
                          AnalysisConfig(module_min_files=1, heuristic_fanin_cap=1))
    assert "logger_flush" not in {n.label for n in capped.nodes.values()}
    assert capped.capped == {"uart_send": 2}


def _fn(usr, name, file, line, **kw):
    from codetortoise.facts.model import Function
    return Function(usr=usr, qualname=name, name=name, signature="", return_type="", file=file, start_line=line,
                    end_line=line + 5, **kw)


def _call(caller, name, file, line):
    from codetortoise.facts.model import CallEdge
    return CallEdge(caller=caller, callee=f"name:{name}", callee_name=name, file=file, line=line, confidence="heuristic")


def test_calls_known_only_by_name_reach_the_function_of_that_name():
    from codetortoise.config import AnalysisConfig
    from codetortoise.diffmap import DiffMap, FunctionChange
    from codetortoise.facts.model import Facts, FieldAccess, TuInfo
    from codetortoise.impact import build_impact
    from codetortoise.tu_select import TuSelection

    hal = Facts(tu=TuInfo(file="/w/hal.c", variant="after"),
                functions=[_fn("c:@F@hal_write", "hal_write", "/w/hal.c", 1),
                           _fn("c:hal.c@F@probe", "probe", "/w/hal.c", 10, is_static=True)])
    dsp = Facts(tu=TuInfo(file="/w/dsp.c", variant="after"),
                functions=[_fn("c:dsp.c@F@probe", "probe", "/w/dsp.c", 1, is_static=True)])
    drv = Facts(tu=TuInfo(file="/w/drv.c", variant="after", confidence="degraded"),
                functions=[_fn("c:@F@drv_run", "drv_run", "/w/drv.c", 1)],
                calls=[_call("c:@F@drv_run", "hal_write", "/w/drv.c", 2), _call("c:@F@drv_run", "probe", "/w/drv.c", 3)],
                fields=[FieldAccess(fn="c:@F@drv_run", field="name:size", field_name="size", record="", path="?.size",
                                    root_kind="unknown", mode="write", file="/w/drv.c", line=4, confidence="heuristic")])
    tool = Facts(tu=TuInfo(file="/w/tool.c", variant="after", extractor="treesitter", confidence="failed"),
                 functions=[_fn("ts:/w/tool.c#main", "main", "/w/tool.c", 1)],
                 calls=[_call("ts:/w/tool.c#main", "hal_write", "/w/tool.c", 2)])
    hal.calls.append(_call("c:@F@hal_write", "probe", "/w/hal.c", 3))
    dm = DiffMap(functions=[FunctionChange(file="/w/hal.c", depot="//hal.c", qualname="hal_write", name="hal_write",
                                           kind="body_modified", before_lines=(1, 6), after_lines=(1, 6))])
    im = build_impact([], [hal, dsp, drv, tool], dm, TuSelection(selected=["/w/hal.c", "/w/dsp.c", "/w/drv.c", "/w/tool.c"]),
                      None, None, AnalysisConfig(module_min_files=1))
    edges = {(im.nodes[e.src].key, e.kind, im.nodes[e.dst].key): e.confidence for e in im.edges}
    assert edges[("c:@F@drv_run", "call", "c:@F@hal_write")] == "heuristic"
    assert edges[("ts:/w/tool.c#main", "call", "c:@F@hal_write")] == "heuristic"
    assert edges[("c:@F@hal_write", "call", "c:hal.c@F@probe")] == "heuristic"        # a static of its own file
    assert edges[("c:@F@drv_run", "call", "name:probe")] == "heuristic"              # two files' statics: unresolved
    assert edges[("c:@F@drv_run", "writes", "field:name:size")] == "heuristic"
    assert not any(n.key == "name:hal_write" for n in im.nodes.values())


def test_the_impact_model_names_its_shared_sinks_and_the_blast_radius_skips_them(analysed):
    from codetortoise.config import AnalysisConfig
    from codetortoise.impact import build_impact

    a = analysed
    assert a.impact.sinks == {}                         # the fixture's fields have few users
    cfg = AnalysisConfig(module_min_files=1)
    plain = build_impact(a.before, a.after, a.dm, a.sel, None, a.layers, cfg)
    data = lambda im: {im.nodes[b.node].label for b in im.blast if b.via == "data"}    # noqa: E731
    assert "uart_errors" in data(plain)
    im = build_impact(a.before, a.after, a.dm, a.sel, None, a.layers, cfg, marked=["Uart::errors"])
    assert [(s.label, s.why) for s in im.sinks.values()] == [("Uart::errors", "marked")]
    assert "uart_errors" not in data(im)


def test_an_impact_model_stored_before_sinks_loads_without_them():
    from codetortoise.impact import ImpactModel
    assert ImpactModel.model_validate({"nodes": {}, "edges": []}).sinks == {}


def test_name_matches_over_the_cap_count_each_function_once(analysed):
    from codetortoise.config import AnalysisConfig
    from codetortoise.impact import build_impact
    from codetortoise.index.symbols import MemberRow

    class Index:                                # 60 references to a written field's name, from 3 functions
        def callers_of(self, name):
            return []

        def member_refs(self, name):
            return [MemberRow(fn=f"f{i % 3}", path=f"/x/{i % 3}.c", line=i, is_write=False) for i in range(60)]

        def transitive_includers(self, path):
            return {f"/x/{i}.c" for i in range(3)}

    a = analysed
    im = build_impact(a.before, a.after, a.dm, a.sel, Index(), a.layers, AnalysisConfig(module_min_files=1))
    assert im.capped["Uart::errors"] == 3
