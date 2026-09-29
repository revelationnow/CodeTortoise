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
