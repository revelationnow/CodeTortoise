from codetortoise.config import ToolchainConfig
from codetortoise.facts import runner
from codetortoise.facts.clang_extractor import TuRequest
from codetortoise.toolchain.compile_db import CompileDb
from codetortoise.toolchain.toolchain import Toolchain
from codetortoise.tu_select import TuSelection
from codetortoise.vcs.model import ChangeSet, ClMeta, FileChange


def test_build_requests_handles_added_and_deleted_files(fx, tmp_path):
    root = str(fx.root.resolve())
    cs = ChangeSet(cls=[ClMeta(cl=1, status="pending")], files=[
        FileChange(depot="//d/driver/uart.c", local=f"{root}/driver/uart.c", action="edit", before="B", after="A"),
        FileChange(depot="//d/driver/new.c", local=f"{root}/driver/new.c", action="add", before="", after="N"),
        FileChange(depot="//d/app/main.c", local=f"{root}/app/main.c", action="delete", before="M", after="")])
    tc = Toolchain(ToolchainConfig(), CompileDb.load(fx.compile_commands), tmp_path)
    sel = TuSelection(selected=[f"{root}/driver/uart.c", f"{root}/app/main.c"])
    before = runner.build_requests(sel, cs, tc, "before")
    after = runner.build_requests(sel, cs, tc, "after")
    assert [r.file.split("/")[-1] for r in before] == ["uart.c", "main.c"]
    assert [r.file.split("/")[-1] for r in after] == ["uart.c", "new.c"]
    assert before[0].unsaved == {f"{root}/driver/uart.c": "B", f"{root}/app/main.c": "M"}
    assert after[0].unsaved == {f"{root}/driver/uart.c": "A", f"{root}/driver/new.c": "N"}
    assert "-I" + root + "/include" in after[1].args  # new file borrows args from its directory neighbour


def test_falls_back_to_treesitter_when_clang_raises(monkeypatch, tmp_path):
    f = tmp_path / "x.c"
    f.write_text("int f(struct S *s) { s->a = 1; return g(); }\n")

    def boom(req):
        raise RuntimeError("libclang crashed")

    monkeypatch.setattr(runner, "extract_tu", boom)
    facts = runner._extract_with_fallback(TuRequest(file=str(f), args=[], variant="after"))
    assert facts.tu.extractor == "treesitter" and facts.tu.confidence == "failed"
    assert [fn.qualname for fn in facts.functions] == ["f"]
    assert [(c.callee, c.confidence) for c in facts.calls] == [("name:g", "heuristic")]
    assert [(a.field_name, a.mode) for a in facts.fields] == [("a", "write")]


def test_process_pool_extraction(fx, tmp_path):
    tc = Toolchain(ToolchainConfig(), CompileDb.load(fx.compile_commands), tmp_path)
    files = [str(fx.root / "hal/regs.c"), str(fx.root / "driver/uart.c")]
    reqs = [TuRequest(file=f, args=tc.args_for(f), variant="before") for f in files]
    out = runner.run_extraction(reqs, None, workers=2)
    assert [len(f.functions) for f in out] == [2, 3]


def reqs_for(fx, tmp_path, names):
    tc = Toolchain(ToolchainConfig(), CompileDb.load(fx.compile_commands), tmp_path)
    files = [str(fx.root / n) for n in names]
    return [TuRequest(file=f, args=tc.args_for(f), variant="before") for f in files]


def test_worker_crash_is_isolated_to_its_tu(fx, tmp_path):
    from crashy import crash_on_uart
    reqs = reqs_for(fx, tmp_path, ["hal/regs.c", "driver/uart.c", "service/logger.c"])
    out = runner.run_extraction(reqs, None, workers=2, worker=crash_on_uart)
    assert [f.tu.file.split("/")[-1] for f in out] == ["regs.c", "uart.c", "logger.c"]
    assert [f.tu.extractor for f in out] == ["clang", "treesitter", "clang"]
    assert "crashed" in out[1].tu.diagnostics[0]
    assert {fn.qualname for fn in out[1].functions} == {"uart_init", "uart_send", "uart_errors"}


def test_single_tu_extraction_never_runs_in_process(fx, tmp_path):
    from crashy import crash_on_uart
    (facts,) = runner.run_extraction(reqs_for(fx, tmp_path, ["driver/uart.c"]), None, workers=1, worker=crash_on_uart)
    assert facts.tu.extractor == "treesitter"  # and this test process is still alive


DROPS = """#include "missing.h"
int helper(int x) { return x + 1; }
int run(const char *name, int (*cb)(int)) {
  git_str buf;
  git_readbuffer(&buf, name);
  buf.size = 0;
  cb(1);
  GIT_ASSERT(name);
  git_str_dispose(&buf);
  return helper(2);
}
"""


def test_a_degraded_parse_gets_the_calls_and_fields_clang_dropped_from_tree_sitter(tmp_path):
    f = tmp_path / "drv.c"
    f.write_text(DROPS)                                          # `git_str` is unknown: clang drops whatever uses buf
    facts = runner._extract_with_fallback(TuRequest(file=str(f), args=["-xc"], variant="after"))
    assert (facts.tu.extractor, facts.tu.confidence, facts.tu.supplemented) == ("clang", "degraded", 3)
    heur = [(c.caller, c.callee, c.line) for c in facts.calls if c.confidence == "heuristic"]
    assert heur == [("c:@F@run", "name:git_readbuffer", 5), ("c:@F@run", "name:git_str_dispose", 9)]
    assert [(c.callee_name, c.confidence) for c in facts.calls if c.callee_name == "helper"] == [("helper", "precise")]
    assert not any(c.callee_name == "cb" for c in facts.calls)   # a call through a parameter names no function
    assert [c.callee_name for c in facts.calls].count("GIT_ASSERT") == 1
    assert [(a.fn, a.field, a.mode, a.confidence) for a in facts.fields] == [("c:@F@run", "name:size", "write", "heuristic")]


def test_a_precise_parse_never_runs_tree_sitter(fx, monkeypatch):
    def boom(req, reason=""):
        raise AssertionError("tree-sitter ran")
    monkeypatch.setattr(runner, "extract_tu_treesitter", boom)
    facts = runner._extract_with_fallback(TuRequest(file=str(fx.root / "hal/regs.c"), args=["-xc", f"-I{fx.root}/include"],
                                                    variant="before"))
    assert (facts.tu.confidence, facts.tu.supplemented) == ("precise", 0)


def test_the_summary_counts_what_tree_sitter_added_to_degraded_parses():
    from codetortoise.facts.model import Facts, TuInfo
    facts = [Facts(tu=TuInfo(file="a.c", variant="after")),
             Facts(tu=TuInfo(file="b.c", variant="after", confidence="degraded", supplemented=3, diagnostics=["b.c:1: x"])),
             Facts(tu=TuInfo(file="c.c", variant="after", confidence="degraded", diagnostics=["c.c:1: x"]))]
    assert runner.parse_summary(facts) == ("3 parse(s): 1 precise, 2 degraded; tree-sitter added 3 call(s) or field "
                                           "access(es) to 1 degraded parse(s); most common problem (2): x")
