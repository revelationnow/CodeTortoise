"""Facts prepared for each finding (spec 2026-10-05-two-tier-stories §5.1)."""
from test_stories import W, _edit, _same, _world

from codetortoise.board import _Ctx
from codetortoise.detectors.base import Evidence, Finding
from codetortoise.facts_prep import finding_key, prepare_facts


def _finding(kind, title, nodes, **kw):
    return Finding(id="F1", kind=kind, severity="medium", title=title, summary="s", nodes=nodes, **kw)


def test_a_signature_change_marks_every_call_site():
    c = _world([_edit("hal_write", "hal/regs.c"), _edit("uart_send", "drv/uart.c"), _same("old_user", "drv/old.c"),
                _same("dsp_call", "dsp/d.c"), _same("tool_main", "tools/t.c")],
               calls=[("uart_send", "hal_write"), ("old_user", "hal_write"), ("dsp_call", "hal_write"),
                      ("tool_main", "hal_write")])
    t = {f"{W}/hal/regs.c": ["fw"], f"{W}/drv/uart.c": ["fw"], f"{W}/drv/old.c": ["fw"], f"{W}/dsp/d.c": ["dsp"]}
    f = _finding("contract", "hal_write: signature changed", ["N1"])
    text = prepare_facts(_Ctx(c), [f], t)[finding_key(f)]
    assert text.splitlines() == [
        "call sites of hal_write (N1):",
        "  drv/old.c:3 in old_user (N3): not updated: `b = 0;`",
        "  drv/uart.c:3 in uart_send (N2): updated in this change: `a = 0;`",
        "  dsp/d.c:3 in dsp_call (N4): compiled only in another target: `b = 0;`",
        "  tools/t.c:3 in tool_main (N5): not in any compile database: `b = 0;`"]


def test_a_new_return_value_says_how_each_caller_handles_the_result():
    c = _world([("send", "s.c", ["a();"], ["a();", "return -2;"]), ("loose", "a.c", ["send();"], ["send();"]),
                ("check", "b.c", ["if (send() == -1) {}"], ["if (send() == -1) {}"]),
                ("pass_on", "c.c", ["return send();"], ["return send();"]), ("keep", "d.c", ["rc = send();"], ["rc = send();"])],
               calls=[("loose", "send"), ("check", "send"), ("pass_on", "send"), ("keep", "send")])
    calls = c.after[0].calls
    calls[0].result_used = False
    calls[1].compared, calls[1].compared_names = ["==-1"], {"==-1": "ERR"}
    f = _finding("contract", "send: new return value(s) -2", ["N1"])
    rows = prepare_facts(_Ctx(c), [f], {})[finding_key(f)].splitlines()
    assert rows == ["callers of send (N1) and how each handles its result:",
                    "  a.c:3 in loose (N2): ignored: `send();`",
                    "  b.c:3 in check (N3): compared with ERR (==-1): `if (send() == -1) {}`",
                    "  c.c:3 in pass_on (N4): propagated: `return send();`",
                    "  d.c:3 in keep (N5): stored: `rc = send();`"]


def test_a_field_write_lists_every_reader_and_writer_and_which_changed():
    c = _world([_edit("uart_send", "drv/uart.c"), _same("uart_errors", "drv/stat.c")],
               fields=[("uart_send", "Uart", "errors", "write", "added"), ("uart_errors", "Uart", "errors", "read", "unchanged")])
    f = _finding("field_mutation", "uart_send now writes Uart::errors", ["N1", "N3"], side_effect=True)
    rows = prepare_facts(_Ctx(c), [f], {})[finding_key(f)].splitlines()
    assert rows == ["readers and writers of Uart::errors (N3):",
                    "  uart_errors (N2) reads it: drv/stat.c:3 read `b = 0;`",
                    "  uart_send (N1) writes it — changed in this change (added by this change): drv/uart.c:3 write `a = 0;`"]


def test_a_header_change_lists_the_lines_using_each_name_in_files_including_it():
    c = _world([("pd_get", "src/pd.c", ["a = 0;"], ["a = PD_DIR;"])])
    h, other = f"{W}/src/sysdir.h", f"{W}/lib/use.c"
    f = Finding(id="F2", kind="header_fanout", severity="low", title="sysdir.h: 2 change(s) reach 2 TU(s)", summary="s",
                evidence=[Evidence(text="macro added: PD_DIR", file=h), Evidence(text="macro removed: OLD_DIR", file=h),
                          Evidence(text="included (transitively) by 2 TU(s)")])
    texts = {other: "int x;\nint y = PD_DIR + 1;\n"}
    rows = prepare_facts(_Ctx(c), [f], {}, includers=lambda hdr: {f"{W}/src/pd.c", other},
                         read_text=texts.get)[finding_key(f)].splitlines()
    assert rows == ["changes in src/sysdir.h: PD_DIR, OLD_DIR",
                    "  PD_DIR: used at", "    lib/use.c:2 `int y = PD_DIR + 1;`", "    src/pd.c:3 `a = PD_DIR;`",
                    "  OLD_DIR: no use found in the files including it", "  (2 including file(s) searched)"]


def test_findings_are_keyed_by_kind_and_title_and_others_get_their_callers():
    c = _world([_edit("core", "x.c"), _same("user", "y.c")], calls=[("user", "core")])
    f = _finding("other_kind", "core: something", ["N1"])
    facts = prepare_facts(_Ctx(c), [f], {})
    assert list(facts) == ["other_kind|core: something"]
    assert facts["other_kind|core: something"].splitlines() == ["core (N1) changed its body; its callers:",
                                                                  "  y.c:3 in user (N2): result used: `b = 0;`"]


def test_lines_in_files_outside_the_change_are_read_from_the_workspace():
    c = _world([_edit("core", "x.c"), _same("user", "y.c")], calls=[("user", "core")])
    x = _Ctx(c)
    del x.texts[f"{W}/y.c"]                                     # y.c is not in the change
    f = _finding("other_kind", "core: something", ["N1"])
    texts = {f"{W}/y.c": "int a;\nvoid user(void)\nif (core() < 0) return;\n"}
    rows = prepare_facts(x, [f], {}, read_text=texts.get)[finding_key(f)].splitlines()
    assert rows[1] == "  y.c:3 in user (N2): result used: `if (core() < 0) return;`"
    assert prepare_facts(x, [f], {})[finding_key(f)].splitlines()[1] == "  y.c:3 in user (N2): result used: ``"


def test_findings_of_same_named_functions_in_two_files_keep_their_own_key():
    def sig(path):
        return Finding(kind="contract", severity="medium", title="probe: signature changed", summary="s",
                       evidence=[Evidence(text="probe's parameters changed", file=path, line=3)])
    assert finding_key(sig(f"{W}/drv/a.c")) != finding_key(sig(f"{W}/drv/b.c"))
    assert finding_key(sig(f"{W}/drv/a.c")) == finding_key(sig(f"{W}/drv/a.c"))
    assert finding_key(Finding(kind="contract", severity="medium", title="t", summary="s")) == "contract|t"


def test_each_file_outside_the_change_is_read_once():
    c = _world([("pd_get", "src/pd.c", ["a = 0;"], ["a = PD_DIR;"])])
    h, other = f"{W}/src/sysdir.h", f"{W}/lib/use.c"
    f = Finding(id="F2", kind="header_fanout", severity="low", title="sysdir.h: 3 change(s) reach 2 TU(s)", summary="s",
                evidence=[Evidence(text=f"macro added: {n}", file=h) for n in ("PD_DIR", "OLD_DIR", "NEW_DIR")])
    reads = []

    def read(path):
        reads.append(path)
        return "int x;\n"
    prepare_facts(_Ctx(c), [f, f.model_copy(update={"id": "F3"})], {}, includers=lambda hdr: {other}, read_text=read)
    assert reads == [other]
