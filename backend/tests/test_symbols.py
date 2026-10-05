import pytest

from codetortoise.index.symbols import SymbolIndex


@pytest.fixture(scope="module")
def index(fx, tmp_path_factory):
    idx = SymbolIndex(tmp_path_factory.mktemp("idx") / "symbols.db")
    assert idx.build(fx.root) == 9
    return idx


def rel(fx, paths):
    root = str(fx.root.resolve()) + "/"
    return sorted(p.replace(root, "") for p in paths)


def test_generation_increments(index):
    assert index.generation() >= 1


def test_callers_and_defs(index, fx):
    assert rel(fx, [r.path for r in index.callers_of("uart_send")]) == ["service/logger.c", "service/logger.c"]
    assert {r.caller for r in index.callers_of("uart_send")} == {"logger_write", "logger_flush"}
    assert [d.qualname for d in index.defs("hal_write")] == ["hal_write"]


def test_includers(index, fx):
    uart_h = str(fx.root / "driver/uart.h")
    assert rel(fx, index.includers_of(uart_h)) == ["driver/uart.c", "service/logger.h"]
    regs_h = str(fx.root / "include/hal/regs.h")
    assert rel(fx, index.transitive_includers(regs_h)) == [
        "app/main.c", "driver/uart.c", "driver/uart.h", "hal/regs.c", "service/logger.c", "service/logger.h"]


def test_member_refs(index):
    refs = index.member_refs("errors")
    assert {(r.fn, r.is_write) for r in refs} == {("uart_init", True), ("uart_errors", False)}


def test_edges(index, fx):
    inc = {(a.split("/")[-1], b.split("/")[-1]) for a, b in index.include_edges()}
    assert ("uart.c", "uart.h") in inc and ("uart.h", "regs.h") in inc
    calls = {(a.split("/")[-1], b.split("/")[-1]) for a, b in index.call_edges_by_path()}
    assert ("logger.c", "uart.c") in calls and ("uart.c", "regs.c") in calls


def test_includes_resolve_relative_then_include_dirs(tmp_path):
    files = {"a/config.h": "", "b/config.h": "", "a/x.c": '#include "config.h"\n', "b/y.c": '#include "config.h"\n',
             "c/z.c": '#include "../a/config.h"\n', "d/w.c": '#include "config.h"\n'}
    for rel_path, text in files.items():
        (tmp_path / rel_path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel_path).write_text(text)
    root = str(tmp_path.resolve())
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(tmp_path, include_dirs=[f"{root}/b"])
    def short(ps): return sorted(p.replace(root + "/", "") for p in ps)
    assert short(idx.includers_of(f"{root}/a/config.h")) == ["a/x.c", "c/z.c"]
    assert short(idx.includers_of(f"{root}/b/config.h")) == ["b/y.c", "d/w.c"]
    idx.build(tmp_path)  # no include dirs: an unresolvable ambiguous include matches every candidate
    assert short(idx.includers_of(f"{root}/a/config.h")) == ["a/x.c", "c/z.c", "d/w.c"]



def test_includes_resolve_through_symlinked_headers_and_dirs(tmp_path):
    files = {"src/foo.h": "", "other/foo.h": "", "real/sub/bar.h": "", "vendor/sub/bar.h": "",
             "lib/x.c": '#include "foo.h"\n#include "sub/bar.h"\n'}
    for rel_path, text in files.items():
        (tmp_path / rel_path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel_path).write_text(text)
    (tmp_path / "include").mkdir()
    (tmp_path / "include/foo.h").symlink_to("../src/foo.h")
    (tmp_path / "include/sub").symlink_to("../real/sub")
    root = str(tmp_path.resolve())
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(tmp_path, include_dirs=[f"{root}/include"])
    assert idx.includers_of(f"{root}/src/foo.h") == [f"{root}/lib/x.c"]
    assert idx.includers_of(f"{root}/real/sub/bar.h") == [f"{root}/lib/x.c"]
    assert idx.includers_of(f"{root}/other/foo.h") == []


def test_include_resolution_skips_realpath_when_lookups_decide(tmp_path, monkeypatch):
    """Many include dirs times many includes made one realpath per (include, dir): runaway on big workspaces."""
    import codetortoise.index.symbols as symbols
    dirs = [f"d{i}" for i in range(20)]
    for d in dirs:
        (tmp_path / d).mkdir()
    (tmp_path / "d19/common.h").write_text("")
    for i in range(30):
        (tmp_path / f"f{i}.c").write_text('#include "common.h"\n#include "missing.h"\n')
    root = str(tmp_path.resolve())
    include_dirs = [f"{root}/{d}" for d in dirs]
    idx = SymbolIndex(tmp_path / "s.db")
    idx.build(tmp_path, include_dirs=include_dirs)
    calls = []
    real = symbols.canon
    monkeypatch.setattr(symbols, "canon", lambda p: calls.append(p) or real(p))
    pairs = idx._resolve_includes(include_dirs)
    assert sorted({t for _, t in pairs}) == [f"{root}/d19/common.h"] and len(pairs) == 30
    assert calls == []  # a symlink-free tree is decided by set lookups and lstat alone

def test_native_parser_crash_skips_only_that_file(tmp_path):
    from crashy import parse_crash_on_boom
    (tmp_path / "a.c").write_text("int a(void) { return b(); }\n")
    (tmp_path / "boom.c").write_text("int boom(void) { return 0; }\n")
    (tmp_path / "c.c").write_text("int c(void) { return a(); }\n")
    idx = SymbolIndex(tmp_path / "s.db")
    assert idx.build(tmp_path, workers=2, parser=parse_crash_on_boom) == 2
    assert [p.split("/")[-1] for p in idx.files()] == ["a.c", "c.c"]
    assert [p.split("/")[-1] for p in idx.skipped] == ["boom.c"]
