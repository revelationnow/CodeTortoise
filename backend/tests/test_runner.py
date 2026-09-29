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
