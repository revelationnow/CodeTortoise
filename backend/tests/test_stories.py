"""Change stories (spec 2026-10-04-change-stories §2–§3): a review told as a few stories."""
from test_board import _ctx, _synthetic

from codetortoise.board import BoardContext
from codetortoise.config import AnalysisConfig
from codetortoise.diffmap import DiffMap, FunctionChange
from codetortoise.facts.model import CallEdge, Facts, FieldAccess, Function, TuInfo
from codetortoise.impact import Edge, ImpactModel, Node
from codetortoise.stories import build_stories
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange, PerClText

W = "/w"


def _fn(name, file, start, end):
    return Function(usr=f"c:@F@{name}", qualname=name, name=name, signature=f"void {name}(void)", return_type="void",
                    file=file, start_line=start, end_line=end)


def _body(name, lines):
    return [f"void {name}(void)", "{", *(f"\t{x}" for x in lines), "}"]


def _world(fns, calls=(), fields=(), cfg=None):
    """fns: (name, path relative to W, body lines before | None, body lines after | None). Functions are laid out in
    order, one file per path; a function whose body differs (or that is added or removed) is changed. calls: (caller,
    callee). fields: (function, record, field, mode, status) with status "added" for an access the change added."""
    texts: dict[str, tuple[list[str], list[str]]] = {}
    before, after, nodes, dm, changed = [], [], {}, [], []
    for i, (name, rel, b, a) in enumerate(fns, 1):
        path = f"{W}/{rel}"
        tb, ta = texts.setdefault(path, ([], []))
        nid = f"N{i}"
        status = "added" if b is None else "removed" if a is None else "changed" if b != a else "unchanged"
        nodes[nid] = Node(id=nid, key=f"c:@F@{name}", label=name, file=path, line=len(ta) + 1, status=status, layer=1)
        br = ar = None
        if b is not None:
            br = (len(tb) + 1, len(tb) + len(b) + 3)
            before.append(_fn(name, path, *br))
            tb += _body(name, b)
        if a is not None:
            ar = (len(ta) + 1, len(ta) + len(a) + 3)
            after.append(_fn(name, path, *ar))
            ta += _body(name, a)
        if status != "unchanged":
            changed.append(nid)
            kind = {"added": "added", "removed": "removed"}.get(status, "body_modified")
            dm.append(FunctionChange(file=path, depot="//d" + path, qualname=name, name=name, kind=kind,
                                     before_lines=br, after_lines=ar))
    by = {n.label: n.id for n in nodes.values()}
    edges = [Edge(id=f"E{i}", src=by[s], dst=by[d], kind="call") for i, (s, d) in enumerate(calls, 1)]
    accs = []
    for fn, rec, field, mode, st in fields:
        fid = f"field:c:@S@{rec}@FI@{field}"
        if fid not in {n.key for n in nodes.values()}:
            nid = f"N{len(nodes) + 1}"
            nodes[nid] = Node(id=nid, key=fid, kind="field", label=f"{rec}::{field}", layer=1)
        fnode = next(n.id for n in nodes.values() if n.key == fid)
        edges.append(Edge(id=f"E{len(edges) + 1}", src=by[fn], dst=fnode, kind="writes" if mode == "write" else "reads",
                          status=st))
        f = next(x for x in after if x.name == fn)
        accs.append(FieldAccess(fn=f.usr, field=f"c:@S@{rec}@FI@{field}", field_name=field, record=rec,
                                record_file=f"{W}/r.h", decl_line=1, path=f"r->{field}", root_kind="param", mode=mode,
                                file=f.file, line=f.start_line + 2))
    call_facts = [CallEdge(caller=f"c:@F@{s}", callee=f"c:@F@{d}", callee_name=d,
                           file=nodes[by[s]].file, line=nodes[by[s]].line + 2) for s, d in calls]
    files = [FileChange(depot="//d" + p, local=p, action="edit", before="\n".join(b) + "\n", after="\n".join(a) + "\n")
             for p, (b, a) in texts.items()]
    im = ImpactModel(nodes=nodes, edges=edges, changed=changed, blast=[])
    return BoardContext(ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=files), DiffMap(functions=dm),
                        [Facts(tu=TuInfo(file=f"{W}/a.c", variant="before"), functions=before)],
                        [Facts(tu=TuInfo(file=f"{W}/a.c", variant="after"), functions=after, calls=call_facts,
                               fields=accs)],
                        im, [], None, cfg or AnalysisConfig(), lambda ps: {p: "//d" + p for p in ps}, root=W)


def _mech(name, rel, var="a"):
    return (name, rel, ["x = 1;", f"git_vector_free(&{var});"], ["x = 1;", f"git_vector_dispose(&{var});"])


def _edit(name, rel):
    """A change that is not a substitution (a line added)."""
    return (name, rel, ["a = 0;"], ["a = 0;", f"{name}_more();"])


def _same(name, rel):
    """An unchanged function."""
    return (name, rel, ["b = 0;"], ["b = 0;"])


def _by_kind(ss, kind):
    return [s for s in ss.stories if s.kind == kind]


# ---- 1. repeated edits
def test_one_substitution_in_two_functions_is_a_mechanical_story_with_its_sites():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c", var="b"),
                ("lonely", "src/c.c", ["y = 1;"], ["y = 2;"])])           # `1` → `2` once: not a repeated edit
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.title == "`git_vector_free` → `git_vector_dispose` at 2 sites in 2 files"
    assert m.sub == ["git_vector_free", "git_vector_dispose"] and m.counts["sites"] == 2
    d = det[m.id]
    assert [(s.path, s.line, s.function, s.before, s.after) for s in d.sites] == [
        ("//d/w/src/a.c", 4, "free_a", "git_vector_free(&a);", "git_vector_dispose(&a);"),
        ("//d/w/src/b.c", 4, "free_b", "git_vector_free(&b);", "git_vector_dispose(&b);")]
    assert {f.note for f in d.functions} == {"`git_vector_dispose` instead of `git_vector_free`"}
    assert d.graph is None
    assert ss.node_story["N1"] == ss.node_story["N2"] == m.id and ss.node_story["N3"] != m.id


def test_a_function_with_the_edit_and_another_change_stays_out_and_is_listed_as_also_in():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c"),
                ("busy", "src/c.c", ["q(1);", "x = 1;", "git_vector_free(&a);"],
                 ["q(1, 2);", "x = 1;", "git_vector_dispose(&a);"])])
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.nodes == ["N1", "N2"] and m.counts["sites"] == 3
    d = det[m.id]
    assert [(r.label, r.story) for r in d.also_in] == [("busy", ss.node_story["N3"])]
    (site,) = [s for s in d.sites if s.function == "busy"]
    assert site.other_edits == ss.node_story["N3"] != m.id
    (other,) = _by_kind(ss, "other")
    (fn,) = det[other.id].functions
    assert fn.also == [m.id] and "also `git_vector_free` → `git_vector_dispose`" in fn.note


def test_test_sites_are_counted_and_test_code_without_the_edit_is_the_tests_story():
    c = _world([_mech("free_a", "src/a.c"), _mech("test_free", "tests/t.c"),
                ("test_other", "tests/u.c", ["check(1);"], ["check(2);", "check(3);"])])
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.counts["test_sites"] == 1 and m.title.endswith("(1 in tests)")
    assert [s.test for s in det[m.id].sites] == [False, True]
    (t,) = _by_kind(ss, "tests")
    assert t.title == "Tests" and t.nodes == ["N3"] and t.summary == "1 test function changed in 1 file."


def test_added_and_removed_functions_are_never_mechanical():
    c = _world([("old_api", "src/v.c", ["free(p);"], None), ("new_api", "src/v.c", None, ["dispose(p);"]),
                _mech("free_a", "src/a.c"), _mech("free_b", "src/b.c")])
    ss, det = build_stories(c)
    assert [s.kind for s in ss.stories] == ["other", "other", "mechanical"]
    assert {s.summary for s in _by_kind(ss, "other")} == {"New: `new_api`.", "Removed: `old_api`."}
    notes = {f.label: f.note for s in _by_kind(ss, "other") for f in det[s.id].functions}
    assert notes == {"old_api": "removed", "new_api": "new function"}


def test_a_function_defined_twice_in_one_file_is_read_at_the_definition_that_changed():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c")])
    # free_b also has an earlier, unchanged definition (under #ifdef): the facts list that one first
    first = _fn("free_b", f"{W}/src/b.c", 1, 5)
    fc = next(f for f in c.cs.files if f.local.endswith("b.c"))
    pad = "\n".join(_body("free_b", ["y = 0;", "y = 1;"])) + "\n"
    fc.before, fc.after = pad + fc.before, pad + fc.after
    for fx in (c.before[0], c.after[0]):
        for f in fx.functions:
            if f.name == "free_b":
                f.start_line, f.end_line = f.start_line + 5, f.end_line + 5
        fx.functions.insert(0, first)
    (d,) = [d for d in c.dm.functions if d.name == "free_b"]
    d.before_lines, d.after_lines = (6, 10), (6, 10)
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.nodes == ["N1", "N2"] and [s.line for s in det[m.id].sites] == [4, 9]


def test_overloads_in_one_file_each_count_only_their_own_sites():
    c = _world([_mech("put", "src/p.cpp"), _mech("put2", "src/p.cpp")])
    for fx in (c.before[0], c.after[0]):                      # put(long) beside put(int): one name, two definitions
        for f in fx.functions:
            if f.name == "put2":
                f.qualname, f.name, f.usr = "put", "put", "c:@F@put#l"
    c.impact.nodes["N2"].key = "c:@F@put#l"
    for d in c.dm.functions:
        if d.name == "put2":
            d.qualname, d.name = "put", "put"
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.counts["sites"] == 2 and [s.line for s in det[m.id].sites] == [4, 9]


def test_the_summary_says_mostly_mechanical_when_repeated_edits_are_half_the_changed_lines():
    ss, _ = build_stories(_world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c"),
                                  ("f", "src/c.c", ["y = 1;"], ["y = 2;"])]))
    assert ss.summary == "Mostly mechanical: 2 of 3 changed lines are one edit (`git_vector_free` → `git_vector_dispose`)."
    ss, _ = build_stories(_world([_edit("f", "src/c.c"), _edit("test_f", "tests/t.c")]))
    assert ss.summary == "1 other changed function, 1 test change."
    ss, _ = build_stories(_world([_same("f", "src/c.c")]))
    assert ss.summary == "No changed functions." and ss.stories == []


def test_the_summary_counts_the_lines_of_added_and_deleted_files_too():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c")])
    c.cs.files += [FileChange(depot="//d/w/src/n.h", local=f"{W}/src/n.h", action="add", before="", after="int n;\n"),
                   FileChange(depot="//d/w/src/o.h", local=f"{W}/src/o.h", action="delete", before="int o;\n", after="")]
    ss, _ = build_stories(c)
    assert ss.summary == "Mostly mechanical: 2 of 4 changed lines are one edit (`git_vector_free` → `git_vector_dispose`)."


def test_the_flows_of_a_repeated_edit_are_one_story_whose_functions_stay_with_the_edit():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c"), _same("peek", "src/c.c")],
               fields=[("free_a", "R", "v", "write", "added"), ("peek", "R", "v", "read", "unchanged")])
    ss, det = build_stories(c)
    (b,) = _by_kind(ss, "behaviour")
    (m,) = _by_kind(ss, "mechanical")
    assert b.title.startswith("What `git_vector_free` → `git_vector_dispose` changes: `peek`")
    assert b.nodes == [] and "functions" not in {k for k, v in b.counts.items() if v}     # their home is the edit's story
    assert m.nodes == ["N1", "N2"] and ss.node_story["N1"] == m.id and b.flows
    assert next(s for s in det[m.id].sites if s.node == "N1").effect == b.id


# ---- 2. behaviour, joining, other changes
def test_a_flow_causing_function_is_a_behaviour_story_titled_from_its_flows():
    ctx, _ = _synthetic(callers=("api",))
    ss, det = build_stories(ctx)
    (b,) = ss.stories
    assert b.kind == "behaviour" and b.nodes == ["N1"]
    assert b.title == "`set` now writes `R::v`; `peek` reads it (1 more effect)"
    assert set(b.flows) == {fl.id for fl in det[b.id].board.flows} and len(b.flows) == 2
    assert ss.flow_story == {f: b.id for f in b.flows}
    g = det[b.id].graph
    assert g is not None and len(g.nodes) <= 12
    assert {n.kind for n in g.nodes} >= {"function", "struct"}
    (rec,) = [n for n in g.nodes if n.kind == "struct"]
    assert rec.label == "R" and [f.label for f in rec.fields] == ["v"]


def test_stories_tell_the_flows_the_boards_hold():
    from codetortoise.board import build_boards
    ctx, _ = _synthetic(callers=("api",))
    bs = build_boards(ctx)
    bs.analysis.flows[0].id = "FLX"                          # the boards' own analysis, not a second one
    ss, det = build_stories(ctx, bs.home or None, bs.analysis)
    assert "FLX" in ss.flow_story
    b = next(d for d in det.values() if any(fl.id == "FLX" for fl in d.board.flows))
    assert next(fl for fl in b.board.flows if fl.id == "FLX") is not bs.analysis.flows[0]   # copies: no aliasing


def _joined():
    """`set` newly writes R::v and `peek` reads it (a flow); `helper` (changed) is called by `set`; `far` is called by
    `helper`; `lonely` is changed and connected to nothing; `test_x` is changed test code."""
    return _world([_edit("set", "src/a.c"), _same("peek", "src/b.c"), _edit("helper", "src/a.c"),
                   _edit("far", "src/d.c"), _edit("lonely", "lib/x/l.c"), _edit("test_x", "tests/t.c")],
                  calls=[("set", "helper"), ("helper", "far")],
                  fields=[("set", "R", "v", "write", "added"), ("peek", "R", "v", "read", "unchanged")])


def test_changed_code_joins_the_nearest_seed_and_the_rest_is_other_changes_and_tests():
    ss, det = build_stories(_joined())
    kinds = [(s.kind, s.title) for s in ss.stories]
    assert kinds == [("behaviour", "`set` now writes `R::v`; `peek` reads it"),
                     ("other", "Other changes in `lib/x`"), ("tests", "Tests")]
    b = ss.stories[0]
    assert b.nodes == ["N1", "N3", "N4"]                     # set, then helper (1 hop) and far (2 hops)
    assert ss.stories[1].nodes == ["N5"] and ss.stories[2].nodes == ["N6"]
    assert {ss.node_story[n] for n in ("N1", "N3", "N4")} == {b.id}


def test_other_changes_in_one_directory_are_told_apart_by_their_first_function():
    c = _world([_edit("a1", "src/a.c"), _edit("a2", "src/b.c")])
    ss, _ = build_stories(c)
    assert sorted(s.title for s in ss.stories) == ["Other changes in `src` (`a1`)", "Other changes in `src` (`a2`)"]


def test_findings_go_to_the_story_holding_their_node():
    from codetortoise.detectors.base import Finding
    c = _joined()
    c.findings = [Finding(id="F1", kind="field_mutation", severity="medium", title="t", summary="s", nodes=["N5"]),
                  Finding(id="F2", kind="field_mutation", severity="info", title="t", summary="s", nodes=["N4"])]
    ss, _ = build_stories(c)
    by = {s.kind: s for s in ss.stories}
    assert ss.finding_story["F1"] == by["other"].id and ss.finding_story["F2"] == by["behaviour"].id
    assert by["other"].risk == "medium"


# ---- 3. the list's limit
def test_past_the_limit_other_changes_merge_then_repeated_edits_fold():
    fns = [_edit(f"o{i}", f"src/d{i}/f.c") for i in range(4)]
    fns += [(f"m{i}{j}", f"src/m/f{i}.c", [f"old{i}(p);"], [f"new{i}(p);"]) for i in range(3) for j in range(2)]
    ss, det = build_stories(_world(fns, cfg=AnalysisConfig(max_stories=4)))
    assert [s.kind for s in ss.stories] == ["other", "mechanical", "mechanical", "mechanical"]
    (o,) = _by_kind(ss, "other")
    assert sorted(o.nodes) == ["N1", "N2", "N3", "N4"] and o.title == "Other changes in `src`"
    ss, det = build_stories(_world(fns, cfg=AnalysisConfig(max_stories=3)))
    assert [(s.kind, s.title) for s in ss.stories] == [
        ("other", "Other changes in `src`"), ("mechanical", "`old0` → `new0` at 2 sites in 1 file"),
        ("mechanical", "2 more repeated edits: 4 sites")]
    folded = ss.stories[2]
    assert folded.subs == [["old1", "new1"], ["old2", "new2"]] and len(det[folded.id].sites) == 4
    assert ss.node_story["N7"] == ss.node_story["N10"] == folded.id


def test_behaviour_stories_are_never_merged_but_collapse_past_the_limit():
    fns, fields = [], []
    for i in range(4):
        fns += [_edit(f"w{i}", f"src/w{i}.c"), _same(f"r{i}", f"src/r{i}.c")]
        fields += [(f"w{i}", f"R{i}", "v", "write", "added"), (f"r{i}", f"R{i}", "v", "read", "unchanged")]
    ss, _ = build_stories(_world(fns, fields=fields, cfg=AnalysisConfig(max_stories=2)))
    assert [s.kind for s in ss.stories] == ["behaviour"] * 4
    assert [s.collapsed for s in ss.stories] == [False, True, True, True]     # 1 shown + "3 more behaviour stories"


# ---- 4. graphs
def test_a_story_graph_has_at_most_the_configured_nodes_and_a_more_node_for_the_rest():
    fns = [_edit("set", "src/a.c"), _same("peek", "src/b.c")]
    fns += [_edit(f"h{i}", "src/a.c") for i in range(8)]
    calls = [("set", f"h{i}") for i in range(8)]
    ss, det = build_stories(_world(fns, calls=calls, fields=[("set", "R", "v", "write", "added"),
                                                              ("peek", "R", "v", "read", "unchanged")],
                                   cfg=AnalysisConfig(story_graph_nodes=6)))
    (b,) = ss.stories
    g = det[b.id].graph
    assert len(g.nodes) == 6
    (more,) = [n for n in g.nodes if n.kind == "more"]
    assert more.label == f"+{8 - 2} more changed functions"
    assert {n.label for n in g.nodes} >= {"set", "R", "peek"}
    assert len(det[b.id].board.nodes) == 11                    # the story's board keeps every node it mentions


def test_fields_of_one_struct_are_one_node_listing_them_and_edges_follow():
    fns = [_edit("set", "src/a.c"), _same("peek", "src/b.c")]
    ss, det = build_stories(_world(fns, fields=[("set", "R", "v", "write", "added"), ("set", "R", "w", "write", "added"),
                                                ("peek", "R", "v", "read", "unchanged")]))
    g = det[ss.stories[0].id].graph
    (rec,) = [n for n in g.nodes if n.kind == "struct"]
    assert sorted(f.label for f in rec.fields) == ["v", "w"]
    ids = {n.id for n in g.nodes}
    assert all(e.src in ids and e.dst in ids for e in g.edges)
    assert all(n in ids for fl in g.flows for n in fl.path)


def test_story_nodes_carry_a_one_line_note():
    ss, det = build_stories(_joined())
    notes = {n.label: n.note for n in det[ss.stories[0].id].graph.nodes}
    assert notes["set"] == "now writes v"
    assert notes["helper"] == "+1 −0 lines"
    assert notes["peek"].startswith("⚠ reads R::v")


# ---- 5. the uart fixture
def test_the_fixture_tells_two_behaviour_stories(analysed, fx_source):
    ss, det = build_stories(_ctx(analysed, fx_source))
    assert ss.summary == "2 behaviour stories."
    assert [(s.kind, s.risk, s.title) for s in ss.stories] == [
        ("behaviour", "high", "`uart_send` can now return -2; `logger_flush` ignores it (1 more effect)"),
        ("behaviour", "medium", "`hal_write`'s signature changed; `uart_init` calls it")]
    for s in ss.stories:
        g = det[s.id].graph
        assert len(g.nodes) <= 12 and not any(n.label.startswith("/") or "(/" in n.label for n in g.nodes)
    assert {n.label: n.note for n in det["S2"].graph.nodes}["hal_write"] == "signature changed"


# ---- spec §8 cases
def test_a_function_explained_by_two_substitutions_joins_the_bigger_edit():
    two = ("both", "src/c.c", ["x = 1;", "git_vector_free(&a);", "f(OLD);"], ["x = 1;", "git_vector_dispose(&a);", "f(NEW);"])
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c"), two,
                ("g", "src/d.c", ["f(OLD);"], ["f(NEW);"])])
    ss, det = build_stories(c)
    big, small = _by_kind(ss, "mechanical")
    assert big.sub == ["git_vector_free", "git_vector_dispose"] and big.nodes == ["N1", "N2", "N3"]
    assert small.sub == ["OLD", "NEW"] and small.nodes == ["N4"] and small.counts["sites"] == 2   # both's site too


def test_sites_outside_functions_count_with_the_edit():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c")])
    c.cs.files.append(FileChange(depot="//d/w/src/v.h", local=f"{W}/src/v.h", action="edit",     # a header: no functions
                                 before="#define FREE(v) git_vector_free(&v)\n", after="#define FREE(v) git_vector_dispose(&v)\n"))
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.counts["sites"] == 3 and m.counts["files"] == 3
    (macro,) = [s for s in det[m.id].sites if s.function is None]
    assert macro.after == "#define FREE(v) git_vector_dispose(&v)" and macro.line == 1 and macro.path == "//d/w/src/v.h"


def test_sites_outside_functions_are_test_code_by_the_same_rule_as_functions():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c")])
    for rel in ("src/testbed/v.h", "src/vec_test.h"):           # not a test directory; a test file name
        c.cs.files.append(FileChange(depot=f"//d/w/{rel}", local=f"{W}/{rel}", action="edit",
                                     before="#define F(v) git_vector_free(&v)\n", after="#define F(v) git_vector_dispose(&v)\n"))
    ss, det = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    assert m.counts["test_sites"] == 1
    assert [s.path for s in det[m.id].sites if s.test] == ["//d/w/src/vec_test.h"]


def test_code_as_near_to_two_seeds_joins_the_riskier():
    from codetortoise.detectors.base import Finding
    c = _world([_edit("w1", "src/a.c"), _same("r1", "src/b.c"), _edit("w2", "src/c.c"), _same("r2", "src/d.c"),
                _edit("mid", "src/e.c")],
               calls=[("w1", "mid"), ("w2", "mid")],
               fields=[("w1", "R1", "v", "write", "added"), ("r1", "R1", "v", "read", "unchanged"),
                       ("w2", "R2", "v", "write", "added"), ("r2", "R2", "v", "read", "unchanged")])
    c.findings = [Finding(id="F1", kind="field_mutation", severity="high", title="t", summary="s", nodes=["N3"])]
    ss, _ = build_stories(c)
    risky = next(s for s in ss.stories if "N3" in s.nodes)
    assert ss.stories[0] is risky and "N5" in risky.nodes


def test_every_changed_function_flow_and_finding_is_in_exactly_one_story():
    from codetortoise.detectors.base import Finding
    c = _joined()
    c.findings = [Finding(id=f"F{i}", kind="k", severity="low", title="t", summary="s", nodes=[n])
                  for i, n in enumerate(["N1", "N3", "N5", "N6", "N2"], 1)]
    ss, det = build_stories(c)
    homes = [n for s in ss.stories for n in s.nodes]
    assert sorted(homes) == sorted(c.impact.changed) and len(homes) == len(set(homes))
    flows = [f for s in ss.stories for f in s.flows]
    assert len(flows) == len(set(flows)) and set(flows) == set(ss.flow_story)
    found = [f for s in ss.stories for f in s.findings]
    assert sorted(found) == ["F1", "F2", "F3", "F4", "F5"]


def test_test_code_that_causes_a_flow_is_in_its_behaviour_story_only():
    c = _world([_edit("test_set", "tests/t.c"), _same("peek", "src/b.c"), _edit("test_other", "tests/t.c")],
               fields=[("test_set", "R", "v", "write", "added"), ("peek", "R", "v", "read", "unchanged")])
    ss, _ = build_stories(c)
    homes = [n for s in ss.stories for n in s.nodes]
    assert sorted(homes) == sorted(c.impact.changed) and len(homes) == len(set(homes))
    assert [(s.kind, s.nodes) for s in ss.stories] == [("behaviour", ["N1"]), ("tests", ["N3"])]


def test_a_finding_on_the_flows_of_two_stories_is_in_the_riskier_one_only():
    from codetortoise.detectors.base import Finding
    c = _world([_edit("set_v", "src/a.c"), _edit("set_w", "src/a.c"), _same("peek", "src/b.c")],
               fields=[("set_v", "R", "v", "write", "added"), ("set_w", "R", "w", "write", "added"),
                       ("peek", "R", "v", "read", "unchanged"), ("peek", "R", "w", "read", "unchanged")])
    c.findings = [Finding(id="F1", kind="field_mutation", severity="high", title="t", summary="s", nodes=["N1", "N2"])]
    ss, _ = build_stories(c)
    assert [s.kind for s in ss.stories] == ["behaviour", "behaviour"]
    assert [f for s in ss.stories for f in s.findings] == ["F1"] and ss.finding_story["F1"] == ss.stories[0].id


def test_other_changes_spread_over_the_workspace_are_named_by_their_main_directories():
    c = _world([_edit("a1", "deps/pcre/a.c"), _edit("a2", "deps/pcre/b.c"), _edit("b1", "src/util/c.c"),
                _edit("top", "main.c")], calls=[("a1", "a2"), ("a2", "b1"), ("b1", "top")] * 2)    # joined: 2 calls each
    ss, _ = build_stories(c)
    (o,) = ss.stories
    assert o.title == "Other changes in `deps/pcre`, `the workspace root` and 1 more directory"
    assert "/w" not in o.title
    c = _world([_edit("top", "main.c"), _edit("top2", "main2.c")], calls=[("top", "top2")])     # one directory
    assert build_stories(c)[0].stories[0].title == "Other changes in `the workspace root`"


def test_unreached_code_over_the_board_budget_is_split_as_boards_are():
    fns = [_edit(f"p{i}", f"deps/p/f{i % 3}.c") for i in range(6)] + [_edit(f"q{i}", f"src/q/f{i}.c") for i in range(3)]
    calls = [(f"p{i}", f"p{i + 1}") for i in range(5)] + [("p5", "q0"), ("q0", "q1"), ("q1", "q2")]
    ss, _ = build_stories(_world(fns, calls=calls, cfg=AnalysisConfig(board_max_nodes=4)))
    assert len(ss.stories) > 1 and all(len(s.nodes) <= 4 for s in ss.stories)
    assert all(s.title.startswith("Other changes in `") for s in ss.stories)


def test_each_story_names_the_changelists_of_its_files():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c", var="b"),
                ("lonely", "src/c.c", ["y = 1;"], ["y = 2;"])])
    per = {"/w/src/a.c": [1], "/w/src/b.c": [1, 2], "/w/src/c.c": [3]}
    for f in c.cs.files:
        f.per_cl = [PerClText(cl=n, before=f.before, after=f.after) for n in per[f.local]]
    ss, _ = build_stories(c)
    (m,) = _by_kind(ss, "mechanical")
    (o,) = _by_kind(ss, "other")
    assert m.cls == [1, 2] and o.cls == [3]


def test_a_story_names_the_changelists_of_the_code_behind_its_flows_and_of_sites_outside_functions():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c"), _same("peek", "src/c.c")],
               fields=[("free_a", "R", "v", "write", "added"), ("peek", "R", "v", "read", "unchanged")])
    c.cs.files.append(FileChange(depot="//d/w/src/v.h", local=f"{W}/src/v.h", action="edit",
                                 before="#define FREE(v) git_vector_free(&v)\n", after="#define FREE(v) git_vector_dispose(&v)\n"))
    per = {"/w/src/a.c": [1], "/w/src/b.c": [2], "/w/src/c.c": [3], "/w/src/v.h": [4]}
    for f in c.cs.files:
        f.per_cl = [PerClText(cl=n, before=f.before, after=f.after) for n in per[f.local]]
    ss, _ = build_stories(c)
    (b,) = _by_kind(ss, "behaviour")
    (m,) = _by_kind(ss, "mechanical")
    assert b.nodes == [] and b.cls == [1]                  # no functions of its own: the CL of the edit behind its flows
    assert m.cls == [1, 2, 4]                              # the header holds a site and no function


# ---- stories from pieces (spec 2026-10-05-two-tier-stories §6, §7.1)
def _in_cls(c, by_file, descriptions=None):
    from codetortoise.vcs.model import ClMeta, PerClText
    for f in c.cs.files:
        f.per_cl = [PerClText(cl=by_file[f.local[len(W) + 1:]], before=f.before, after=f.after)]
    c.cs.cls = [ClMeta(cl=n, status="pending", description=(descriptions or {}).get(n, ""))
                for n in sorted(set(by_file.values()))]
    return c



def test_the_rules_join_pieces_by_two_calls_or_a_field_within_one_target_and_cl():
    c = _world([_edit("ref_add", "deps/ref/a.c"), _edit("ref_io", "deps/ref/io/b.c"), _edit("ref_log", "deps/ref/log/c.c"),
                _edit("clar_path", "deps/clar/s.c"), _edit("clar_run", "deps/clar/r/t.c")],
               calls=[("ref_add", "ref_io"), ("ref_add", "ref_io"), ("ref_add", "ref_log"), ("ref_add", "clar_path"),
                      ("ref_add", "clar_path"), ("clar_run", "clar_path"), ("clar_run", "clar_path")])
    _in_cls(c, {"deps/ref/a.c": 11, "deps/ref/io/b.c": 11, "deps/ref/log/c.c": 11, "deps/clar/s.c": 12,
                "deps/clar/r/t.c": 12})
    ss, _ = build_stories(c)
    label = {n: x.label for n, x in c.impact.nodes.items()}
    groups = sorted(sorted(label[n] for n in s.nodes) for s in ss.stories)
    assert groups == [["clar_path", "clar_run"], ["ref_add", "ref_io"], ["ref_log"]]   # one call: apart; CL 12: apart
    assert all(s.source == "rules" and s.targets == ["unknown"] for s in ss.stories)
    s = next(s for s in ss.stories if "N2" in s.nodes)
    assert [(p.reason, p.evidence) for p in s.placements] == [("starts_purpose", []), ("linked", [s.pieces[0]])]


def test_a_header_joins_the_story_using_it_most_and_its_finding_goes_there_by_file():
    from codetortoise.detectors.base import Evidence, Finding
    from codetortoise.diffmap import TypeChange
    from codetortoise.vcs.model import FileChange
    c = _world([("pd_get", "src/pd.c", ["a = 0;"], ["a = 0;", "use(PD_DIR);"]),
                ("pd_set", "src/pd.c", ["b = 1;"], ["b = 1;", "set(PD_DIR, b);"]), _edit("stack_add", "deps/ref/s.c")],
               calls=[("pd_set", "pd_get")])
    h = f"{W}/src/sysdir.h"
    c.cs.files.append(FileChange(depot="//d" + h, local=h, action="edit", before="\n", after="#define PD_DIR 1\n"))
    _in_cls(c, {"src/pd.c": 12, "deps/ref/s.c": 11, "src/sysdir.h": 12})
    c.dm.types.append(TypeChange(file=h, depot="//d" + h, name="PD_DIR", kind="macro_added"))
    c.findings = [Finding(id="F1", kind="header_fanout", severity="low", title="sysdir.h: 1 change(s) reach 0 TU(s)",
                          summary="s", evidence=[Evidence(text="macro added: PD_DIR", file=h)]),
                  Finding(id="F2", kind="k", severity="low", title="t", summary="s",
                          evidence=[Evidence(text="x", file="/elsewhere.c")])]
    ss, det = build_stories(c)
    pd = next(s for s in ss.stories if "N1" in s.nodes)
    assert pd.findings == ["F1"] and pd.cls == [12] and len(pd.pieces) == 2
    assert pd.placements[-1].reason == "declaration_used"
    assert "F2" not in ss.finding_story                       # no node and no file of the change: no story
    assert all("F1" not in s.findings for s in ss.stories if s.id != pd.id)


def test_other_changes_over_the_limit_merge_only_within_a_target_and_cl():
    from codetortoise.config import AnalysisConfig
    fns = [_edit(f"f{i}", f"d/x{i}.c") for i in range(6)]
    c = _world(fns, cfg=AnalysisConfig(max_stories=2))
    _in_cls(c, {f"d/x{i}.c": 11 if i < 3 else 12 for i in range(6)})
    ss, _ = build_stories(c)
    assert len(ss.stories) == 2 and sorted(s.cls for s in ss.stories) == [[11], [12]]


def test_a_plan_from_tier_1_gives_titles_purposes_checks_related_stories_and_an_unsorted_story_last():
    from codetortoise.board import analyse
    from codetortoise.grouping import Placement, PlannedStory, StoryPlan
    from codetortoise.pieces import build_pieces
    c = _world([_edit("modem_tx", "modem/tx.c"), _edit("modem_rx", "modem/rx.c"), _edit("dsp_run", "dsp/run.c")])
    a = analyse(c)
    t = {f"{W}/modem/tx.c": ["modem"], f"{W}/modem/rx.c": ["modem"], f"{W}/dsp/run.c": ["dsp"]}
    ps = build_pieces(c, a, t)
    pid = {c.impact.nodes[p.nodes[0]].label: p.id for p in ps.pieces}
    plan = StoryPlan(stories=[
        PlannedStory(key="a", title="Modem radio gains band 71", purpose="Adds band 71 to the modem's radio.",
                     check=["Check the band tables."], questions=["Is band 71 licensed here?"], related=["b"], source="tier1",
                     placements=[Placement(piece=pid["modem_tx"], reason="starts_purpose"),
                                 Placement(piece=pid["modem_rx"], reason="same_feature", evidence=[pid["modem_tx"]])]),
        PlannedStory(key="b", title="", purpose="DSP side.", source="tier1",
                     placements=[Placement(piece=pid["dsp_run"], reason="starts_purpose")]),
        PlannedStory(key="u", unsorted=True, source="tier1", placements=[])])
    ss, det = build_stories(c, analysis=a, plan=plan, pieces=ps)
    s1, s2, s3 = ss.stories
    assert (s1.kind, s1.title, s1.text_source, s1.summary) == ("other", "Modem radio gains band 71", "llm",
                                                               "Adds band 71 to the modem's radio.")
    assert s1.targets == ["modem"] and s1.check == ["Check the band tables."] and s1.questions == ["Is band 71 licensed here?"]
    assert s1.related == [s2.id] and s1.source == "tier1"
    assert [p.reason for p in s1.placements] == ["starts_purpose", "same_feature"]
    assert s2.title == "Other changes in `dsp`" and s2.purpose == "DSP side." and s2.targets == ["dsp"]   # its title failed
    assert (s3.kind, s3.title) == ("unsorted", "Unsorted: needs a person to place these")
    assert det[s3.id].graph is not None
    assert [(p.id, p.files, p.names) for p in det[s1.id].pieces] == [
        (pid["modem_tx"], ["//d/w/modem/tx.c"], ["modem_tx"]), (pid["modem_rx"], ["//d/w/modem/rx.c"], ["modem_rx"])]


def test_a_shared_sink_finding_is_listed_but_never_counted_or_raises_the_risk():
    from codetortoise.detectors.base import Finding
    from codetortoise.impact import SinkInfo
    c = _world([_edit("stack_one", "a/x.c")], fields=[("stack_one", "log_t", "buf", "write", "added")])
    c.impact.sinks = {"N2": SinkInfo(field="N2", label="log_t::buf", users=300, why="threshold")}
    c.findings = [Finding(id="F1", kind="field_mutation", severity="low", title="stack_one no longer writes log_t::buf",
                          summary="s", nodes=["N1"], sink=True)]
    ss, _ = build_stories(c)
    (s,) = ss.stories
    assert s.findings == ["F1"] and s.counts["findings"] == 0 and s.risk is None
