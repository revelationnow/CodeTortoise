"""Pieces, links, cards and the change overview (spec 2026-10-05-two-tier-stories §3)."""
from test_stories import W, _edit, _mech, _world

from codetortoise.board import analyse
from codetortoise.diffmap import TypeChange
from codetortoise.pieces import CARD_CHARS, build_pieces, change_overview
from codetortoise.vcs.model import ClMeta, FileChange, PerClText


def _pieces(c, targets=None, includers=None):
    t = {f.local: (targets or {}).get(f.local[len(W) + 1:], ["fw"]) for f in c.cs.files}
    return build_pieces(c, analyse(c), t, includers)


def _labels(c, ps):
    return [(p.kind, sorted(c.impact.nodes[n].label for n in p.nodes)) for p in ps.pieces]


def _cls(c, by_file: dict[str, int], descriptions: dict[int, str] | None = None):
    """Put each file (relative to W) in one CL, and the review's CLs with their descriptions."""
    for f in c.cs.files:
        f.per_cl = [PerClText(cl=by_file[f.local[len(W) + 1:]], before=f.before, after=f.after)]
    c.cs.cls = [ClMeta(cl=n, status="pending", description=(descriptions or {}).get(n, "")) for n in sorted(set(by_file.values()))]
    return c


def test_pieces_never_span_two_targets_and_a_shared_file_is_its_own_piece():
    c = _world([_edit("modem_tx", "modem/tx.c"), _edit("dsp_run", "dsp/run.c"), _edit("util_crc", "common/crc.c")],
               calls=[("modem_tx", "util_crc"), ("dsp_run", "util_crc")])
    ps = _pieces(c, {"modem/tx.c": ["modem"], "dsp/run.c": ["dsp"], "common/crc.c": ["dsp", "modem"]})
    assert [(p.targets, p.shared, sorted(c.impact.nodes[n].label for n in p.nodes)) for p in ps.pieces] == [
        (["dsp"], False, ["dsp_run"]), (["dsp", "modem"], True, ["util_crc"]), (["modem"], False, ["modem_tx"])]
    assert {(lk.a, lk.b, lk.type, lk.count) for lk in ps.links} == {("P1", "P2", "call", 1), ("P2", "P3", "call", 1)}


def test_new_code_takes_the_changed_functions_that_call_into_it():
    c = _world([("band71_init", "rf/band71.c", None, ["setup();"]), ("band71_tables", "rf/band71.c", None, ["t();"]),
                _edit("bands_select", "rf/bands.c"), _edit("unrelated", "rf/bands.c")],
               calls=[("band71_init", "band71_tables"), ("bands_select", "band71_init")])
    ps = _pieces(c)
    assert _labels(c, ps) == [("new", ["band71_init", "band71_tables", "bands_select"]), ("single", ["unrelated"])]


def test_a_chain_wider_than_two_hops_is_cut_at_its_weakest_links():
    names = ["a_one", "b_two", "c_three", "d_four", "e_five"]
    c = _world([_edit(n, "core/chain.c") for n in names],
               calls=[("a_one", "b_two"), ("b_two", "c_three"), ("b_two", "c_three"), ("c_three", "d_four"),
                      ("c_three", "d_four"), ("d_four", "e_five")])
    ps = _pieces(c)
    assert sorted(_labels(c, ps)) == [("edits", ["b_two", "c_three", "d_four"]), ("single", ["a_one"]),
                                      ("single", ["e_five"])]


def test_pieces_never_span_two_cls_even_when_linked():
    c = _world([_edit("ref_write", "deps/ref/w.c"), _edit("ref_read", "deps/ref/r.c"),
                _edit("clar_sandbox", "deps/clar/s.c")], calls=[("ref_write", "ref_read")])
    _cls(c, {"deps/ref/w.c": 11, "deps/ref/r.c": 12, "deps/clar/s.c": 12})
    ps = _pieces(c)
    assert [(p.cl, sorted(c.impact.nodes[n].label for n in p.nodes)) for p in ps.pieces] == [
        (11, ["ref_write"]), (12, ["clar_sandbox"]), (12, ["ref_read"])]


def test_a_function_in_a_file_two_cls_touched_belongs_to_the_cl_that_wrote_it():
    c = _world([_edit("first", "x.c"), _edit("second", "x.c")])
    f = c.cs.files[0]
    mid = f.after.replace("\tsecond_more();\n", "")              # CL 11 adds first's line, CL 12 adds second's
    f.per_cl = [PerClText(cl=11, before=f.before, after=mid), PerClText(cl=12, before=mid, after=f.after)]
    c.cs.cls = [ClMeta(cl=11, status="pending"), ClMeta(cl=12, status="pending")]
    ps = _pieces(c)
    assert [(p.cl, [c.impact.nodes[n].label for n in p.nodes]) for p in ps.pieces] == [(11, ["first"]), (12, ["second"])]


def test_a_changed_header_is_a_declarations_piece_linked_to_the_code_using_it():
    c = _world([("use_flag", "src/use.c", ["a = 0;"], ["a = CFG_FLAG;"]), _edit("other", "lib/other.c")])
    h = f"{W}/inc/config.h"
    c.cs.files.append(FileChange(depot="//d" + h, local=h, action="edit", before="#define X 1\n",
                                 after="#define X 1\n#define CFG_FLAG 2\n"))
    c.dm.types.append(TypeChange(file=h, depot="//d" + h, name="CFG_FLAG", kind="macro_added"))
    ps = _pieces(c, includers=lambda hdr: {f"{W}/src/use.c"})
    (d,) = [p for p in ps.pieces if p.kind == "declarations"]
    assert d.files == [h] and d.names == ["CFG_FLAG"] and d.nodes == []
    use = ps.node_piece[next(n for n, x in c.impact.nodes.items() if x.label == "use_flag")]
    assert [(lk.type, lk.count) for lk in ps.links if {lk.a, lk.b} == {d.id, use}] == [("uses", 1)]
    assert "changed: CFG_FLAG" in d.card and "inc/config.h (+1 −0)" in d.card


def test_repeated_edits_and_tests_are_pieces_of_their_own():
    c = _world([_mech("free_a", "src/a.c"), _mech("free_b", "src/b.c", var="b"), _edit("test_free", "tests/t.c"),
                _edit("busy", "src/c.c")])
    ps = _pieces(c)
    assert sorted(_labels(c, ps)) == [("repeated", ["free_a", "free_b"]), ("single", ["busy"]), ("tests", ["test_free"])]
    (r,) = [p for p in ps.pieces if p.kind == "repeated"]
    assert r.sub == ["git_vector_free", "git_vector_dispose"]
    assert r.card.startswith(f"{r.id}  repeated edit `git_vector_free` → `git_vector_dispose` · target fw · CL 1")


def test_links_count_calls_shared_fields_and_shared_name_prefixes():
    c = _world([_edit("stack_add_one", "a/x.c"), _edit("stack_add_two", "b/y.c"), _edit("lone", "c/z.c")],
               calls=[("stack_add_one", "lone"), ("stack_add_one", "lone")],
               fields=[("stack_add_one", "R", "v", "write", "added"), ("stack_add_two", "R", "v", "write", "added")])
    ps = _pieces(c)
    one, two, lone = (ps.node_piece[n] for n in ("N1", "N2", "N3"))
    got = {(lk.type, lk.count) for lk in ps.links if {lk.a, lk.b} == {one, two}}
    assert got == {("field", 1), ("name", 1)}
    assert {(lk.type, lk.count) for lk in ps.links if {lk.a, lk.b} == {one, lone}} == {("call", 2)}


def test_ids_and_cards_are_the_same_every_time_and_cards_keep_their_field_order():
    def make():
        c = _world([("band71_init", "rf/band71.c", None, ["setup();"]), _edit("bands_select", "rf/bands.c"),
                    _edit("modem_tx", "modem/tx.c")], calls=[("bands_select", "band71_init")])
        new = next(f for f in c.cs.files if f.local.endswith("band71.c"))
        new.action, new.before = "add", ""
        return _cls(c, {"rf/band71.c": 412, "rf/bands.c": 412, "modem/tx.c": 413},
                    {412: "modem: add LTE band 71 support\n\nlonger text", 413: "tx fix"})
    a, b = _pieces(make()), _pieces(make())
    assert [p.model_dump() for p in a.pieces] == [p.model_dump() for p in b.pieces]
    p1 = a.pieces[0]
    rows = p1.card.split("\n")
    assert rows[0] == 'P1  new code · target fw · CL 412 "modem: add LTE band 71 support"'
    assert rows[1] == "files: rf/band71.c (+4 new), rf/bands.c (+1 −0)"
    assert rows[2].startswith("functions: band71_init: new function; bands_select: +1 −0 lines")
    assert rows[3] == "flows: — · findings: —" and rows[4] == "links: —"
    assert all(len(p.card) <= CARD_CHARS for p in a.pieces)


def test_the_overview_lists_each_cl_and_each_target_with_shared_files_once():
    c = _world([_edit("modem_tx", "modem/rf/tx.c"), _edit("dsp_run", "dsp/run.c"), _edit("util_crc", "common/crc.c")])
    _cls(c, {"modem/rf/tx.c": 11, "dsp/run.c": 11, "common/crc.c": 12}, {11: "modem and dsp", 12: "crc " * 1000})
    t = {f"{W}/modem/rf/tx.c": ["modem"], f"{W}/dsp/run.c": ["dsp"], f"{W}/common/crc.c": ["dsp", "modem"]}
    from codetortoise.board import _Ctx
    text = change_overview(c, _Ctx(c), t)
    assert text.splitlines()[:2] == ["CHANGE: 2 CLs, 3 files, +3 −0 lines", "CL 11 (pending): modem and dsp"]
    assert "TARGET dsp: 1 file, +1 −0\n  dsp: 1 file, +1 −0\nTARGET modem: 1 file, +1 −0\n  modem/rf: 1 file, +1 −0" in text
    assert text.endswith("SHARED FILES\n  common/crc.c: dsp, modem (+1 −0)")
    assert len(text.splitlines()[2]) == len("CL 12 (pending): ") + 2400      # a long description is cut at 600 tokens
    many = {f"{W}/d{i}/e{i}/f{i}/g{i}/x.c": ["fw"] for i in range(400)}
    c.cs.files += [FileChange(depot="//d" + f, local=f, action="edit", before="a\n", after="b\n") for f in many]
    assert len(change_overview(c, _Ctx(c), many, limit=6000)) <= 6000


def test_a_shared_sink_links_no_pieces():
    from codetortoise.impact import SinkInfo
    c = _world([_edit("stack_one", "a/x.c"), _edit("other_two", "b/y.c")],
               fields=[("stack_one", "log_t", "buf", "write", "added"), ("other_two", "log_t", "buf", "write", "added")])
    assert any(lk.type == "field" for lk in _pieces(c).links)
    c.impact.sinks = {"N3": SinkInfo(field="N3", label="log_t::buf", users=300, why="threshold")}
    assert not any(lk.type == "field" for lk in _pieces(c).links)
