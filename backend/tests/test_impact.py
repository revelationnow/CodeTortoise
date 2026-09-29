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
