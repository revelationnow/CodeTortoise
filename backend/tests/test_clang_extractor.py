from codetortoise.facts.clang_extractor import TuRequest, extract_tu


def args(fx, lang="c"):
    base = ["-xc"] if lang == "c" else ["-xc++", "-std=c++17"]
    return base + [f"-I{fx.root}/include", f"-I{fx.root}"]


def test_after_variant_uses_unsaved_content(fx, fx_source):
    cs = fx_source.load([101])
    uart = cs.files[0]
    before = extract_tu(TuRequest(file=uart.local, args=args(fx), variant="before"))
    after = extract_tu(TuRequest(file=uart.local, args=args(fx), variant="after", unsaved={uart.local: uart.after}))
    fb = {f.qualname: f for f in before.functions}
    fa = {f.qualname: f for f in after.functions}
    assert fb["uart_send"].returns == ["0"]
    assert fa["uart_send"].returns == ["-2", "0"]
    assert fa["uart_send"].signature == "int uart_send(struct Uart *, const char *, int)"
    assert [p.is_const for p in fa["uart_send"].params] == [False, True, False]
    assert after.tu.confidence == "precise"


def test_call_result_usage(fx):
    facts = extract_tu(TuRequest(file=str(fx.root / "service/logger.c"), args=args(fx), variant="before"))
    calls = {(c.callee_name, c.line): c for c in facts.calls}
    assert calls[("uart_send", 12)].result_used and calls[("uart_send", 12)].compared == ["!=0"]
    assert not calls[("uart_send", 21)].result_used


def test_virtual_calls_and_methods(fx):
    facts = extract_tu(TuRequest(file=str(fx.root / "cpp/engine.cpp"), args=args(fx, "c++"), variant="before"))
    fns = {f.qualname: f for f in facts.functions}
    assert fns["svc::Engine::base"].is_virtual and fns["svc::Engine::base"].method_key == "base#&$@S@State#"
    assert not fns["svc::Engine::step"].is_virtual
    (call,) = [c for c in facts.calls if c.callee_name == "svc::Engine::base"]
    assert call.kind == "virtual"


def test_unknown_vendor_flags_are_stripped_and_retried(fx):
    facts = extract_tu(TuRequest(file=str(fx.root / "hal/regs.c"),
                                 args=args(fx) + ["-mvendor-special", "--vendor-opt=2"], variant="before"))
    assert facts.tu.confidence == "precise" and facts.tu.error_count == 0
    assert {f.qualname for f in facts.functions} == {"hal_read", "hal_write"}


def test_parse_errors_degrade_confidence(tmp_path):
    f = tmp_path / "bad.c"
    f.write_text("#include \"missing.h\"\nint ok(void) { return 1; }\n")
    facts = extract_tu(TuRequest(file=str(f), args=["-xc"], variant="before"))
    assert facts.tu.confidence == "degraded" and facts.tu.error_count == 1
    assert [fn.qualname for fn in facts.functions] == ["ok"]


def test_macro_return_codes_are_evaluated(tmp_path):
    (tmp_path / "err.h").write_text("#define ERR_HDR (-3)\n")
    src = (tmp_path / "m.c")
    body = """#include "err.h"
#define ERR_BUSY (-4)
int f(int x) {
  x = x * {k};
  if (x) return ERR_BUSY;
  if (x > 3) return ERR_HDR;
  return 0;
}
int g(void) { if (f(1) == ERR_BUSY) return 1; return f(2) != ERR_HDR; }
"""
    args = ["-xc", f"-I{tmp_path}"]
    results = []
    for k in ("2", "3"):
        src.write_text(body.replace("{k}", k))
        facts = extract_tu(TuRequest(file=str(src), args=args, variant="after"))
        results.append(facts)
    fa, fb = ({f.qualname: f for f in r.functions} for r in results)
    assert fa["f"].returns == ["-4", "-3", "0"]
    assert fb["f"].returns == fa["f"].returns  # unrelated body edit does not change return values
    assert [c.compared for c in results[0].calls if c.callee_name == "f"] == [["==-4"], ["!=-3"]]
    assert fa["f"].return_names == {"-4": "ERR_BUSY", "-3": "ERR_HDR"}
    assert [c.compared_names for c in results[0].calls if c.callee_name == "f"] == [
        {"==-4": "ERR_BUSY"}, {"!=-3": "ERR_HDR"}]


def test_unsupported_option_diagnostics_are_stripped(fx):
    facts = extract_tu(TuRequest(file=str(fx.root / "hal/regs.c"),
                                 args=args(fx) + ["-mcpu=vendorcore", "-mfpu=vendorfpu"], variant="before"))
    assert facts.tu.confidence == "precise", facts.tu.diagnostics
    assert sorted(facts.tu.stripped_flags) == ["-mcpu=vendorcore", "-mfpu=vendorfpu"]


def test_load_failure_retries_with_safe_flag_subset(fx):
    facts = extract_tu(TuRequest(file=str(fx.root / "hal/regs.c"),
                                 args=args(fx) + ["-Xclang", "-vendor-cc1", "--target=vendorarch-none-elf"],
                                 variant="before"))
    assert facts.tu.extractor == "clang" and facts.tu.confidence == "degraded"
    assert {f.qualname for f in facts.functions} == {"hal_read", "hal_write"}
    assert "--target=vendorarch-none-elf" in facts.tu.stripped_flags
    assert all(not d.startswith("None") for d in facts.tu.diagnostics)


def test_return_lines_and_field_declaration_lines(fx, fx_source):
    uart = fx_source.load([101]).files[0]
    facts = extract_tu(TuRequest(file=uart.local, args=args(fx), variant="after", unsaved={uart.local: uart.after}))
    fn = {f.qualname: f for f in facts.functions}["uart_send"]
    assert fn.return_lines == {"-2": 18, "0": 24}
    errors = [a for a in facts.fields if a.field_name == "errors" and a.fn == fn.usr]
    assert errors and all(a.decl_line == 14 and a.record_file.endswith("driver/uart.h") for a in errors)
