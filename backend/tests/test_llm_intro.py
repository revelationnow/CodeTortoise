"""The review's introduction from the strong model (spec 2026-10-09-review-introduction §4)."""
from scripted_llm import ScriptedLlm, intro_answer
from test_llm_threads import _reading

from codetortoise.llm.client import LlmError
from codetortoise.llm.intro import prompt, write_intro
from codetortoise.llm.ledger import TIER1, Refused
from codetortoise.reading import Check, RouteStep


def _intro_reading():
    r, ss = _reading()
    r.threads[0].modules, r.threads[0].files = ["drv/"], ["drv/uart.c", "drv/regs.h"]
    r.checks = [Check(key=f"confirm|{i}", kind="confirm", thread="T1", text=f"`send` row {i}") for i in range(7)]
    r.route = [RouteStep(thread=t.id, reason="Nothing is open.") for t in r.threads]
    for t in r.threads:
        t.intro = f"Fixed intro of {t.id}."
    return r, ss


GOOD = {"whole": "The change makes UART lengths unsigned. It also sets the baud rate at init. An engine step arrives "
                 "with CL 12. The main risk is a caller that still passes a signed length.",
        "whole_cites": ["T1", "T2", "T3"],
        "threads": [{"id": "T1", "intro": "Send now takes an unsigned length. The change sits in `drv/`. A caller "
                                          "passing a negative length breaks.", "cites": ["S1", "N1"]},
                    {"id": "T2", "intro": "Init programs the baud rate. The change sits in `drv/`. Nothing is open.",
                     "cites": ["S2"]},
                    {"id": "T3", "intro": "The engine takes a new step. It arrives with CL 12. Nothing is open.",
                     "cites": ["S3", "CL12"]}],
        "route": [{"thread": "T1", "reason": "It has the open checks.", "skim": False, "cites": ["T1"]},
                  {"thread": "T2", "reason": "Init runs before any send.", "skim": False, "cites": ["T2"]},
                  {"thread": "T3", "reason": "It only arrived in the same CL.", "skim": True, "cites": ["T3", "CL12"]}]}


def _with(**part):
    return {**GOOD, **part}


def test_the_prompt_holds_each_threads_modules_files_stories_open_checks_and_the_connections():
    r, ss = _intro_reading()
    text = prompt(r, ss, {11: "Make send unsigned"})
    assert "THREAD DETAILS (id | name | purpose | CLs | open checks):" in text and "THREADS (id" not in text
    assert "T1 | `send` in drv | s1 | CL 11 | 2" in text
    assert "  modules: drv/" in text and "  files: drv/uart.c, drv/regs.h" in text
    assert "  stories: S1 Send gains a length type: Sends bytes (behaviour)" in text
    assert "  open checks: Confirm: `send` row 0; " in text and "Confirm: `send` row 5 +1 more" in text
    assert "`send` row 6" not in text
    assert "T1 | T2 | caller | both run inside `main`" in text
    assert "CL 11 (a hint from its author, not the source of truth): Make send unsigned" in text


def test_an_accepted_answer_writes_the_whole_every_intro_and_the_route():
    r, ss = _intro_reading()
    assert write_intro(ScriptedLlm(lambda s, u: GOOD), None, None, r, ss, {}) == ([], "big")
    assert r.whole.startswith("The change makes UART lengths unsigned.") and r.whole_source == "llm"
    assert [(t.intro_source, t.intro.split(".")[0]) for t in r.threads] == [
        ("llm", "Send now takes an unsigned length"), ("llm", "Init programs the baud rate"),
        ("llm", "The engine takes a new step")]
    assert [(s.thread, s.reason, s.skim) for s in r.route] == [
        ("T1", "It has the open checks.", False), ("T2", "Init runs before any send.", False),
        ("T3", "It only arrived in the same CL.", True)] and r.route_source == "llm"


def test_each_failing_part_keeps_its_fixed_text_and_only_that_part():
    cases = {
        "whole": (_with(whole="The change makes lengths unsigned. It sets the baud. It adds a step."), "the whole"),
        "intro6": (_with(threads=[{**GOOD["threads"][0], "intro": "A. B. C. D. E. F."}, *GOOD["threads"][1:]]),
                   "1 thread(s)"),
        "unlisted": (_with(threads=[{**GOOD["threads"][0], "cites": ["S9"]}, *GOOD["threads"][1:]]), "1 thread(s)"),
        "missing": (_with(route=GOOD["route"][:2]), "the route"),
        "twice": (_with(route=[*GOOD["route"][:2], GOOD["route"][0]]), "the route"),
        "two sentences": (_with(route=[{**GOOD["route"][0], "reason": "It is first. It has checks."},
                                       *GOOD["route"][1:]]), "the route"),
    }
    for name, (answer, part) in cases.items():
        r, ss = _intro_reading()
        notes, by = write_intro(ScriptedLlm(lambda s, u, a=answer: a), None, None, r, ss, {})
        assert by == "big" and notes == [f"introduction: {part} kept the fixed text"], name
        assert (r.whole_source == "template") == (part == "the whole"), name
        assert (r.route_source == "template") == (part == "the route"), name
        assert [t.intro_source for t in r.threads] == (["template", "llm", "llm"] if part == "1 thread(s)" else ["llm"] * 3), name
        if part == "1 thread(s)":
            assert r.threads[0].intro == "Fixed intro of T1.", name
        if part == "the route":
            assert [s.reason for s in r.route] == ["Nothing is open."] * 3, name


def test_several_failing_parts_are_named_together():
    r, ss = _intro_reading()
    notes, _ = write_intro(ScriptedLlm(lambda s, u: {"whole": "", "threads": [], "route": []}), None, None, r, ss, {})
    assert notes == ["introduction: the whole, 3 thread(s) and the route kept the fixed text"]


def test_a_failed_or_refused_call_keeps_every_fixed_text_and_says_why():
    r, ss = _intro_reading()
    notes, by = write_intro(ScriptedLlm(lambda s, u: RuntimeError("down")), None, None, r, ss, {})
    assert notes == ["introduction: big: RuntimeError: down; fresh try: RuntimeError: down; the fixed text stays"]
    assert by is None and r.route_source == "template" and r.threads[0].intro == "Fixed intro of T1."

    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            assert (purpose, target) == ("intro", "intro")
            raise Refused("this review has used its 10 tier-1 AI calls")
    notes, _ = write_intro(ScriptedLlm(lambda s, u: GOOD), Budget(), 1, r, ss, {})
    assert notes == ["introduction: AI budget: this review has used its 10 tier-1 AI calls; the fixed text stays"]


def test_the_introduction_the_strong_model_fails_is_written_by_the_weak_model():
    r, ss = _intro_reading()
    notes, by = write_intro(ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x")), None, None, r, ss,
                            {}, weak=ScriptedLlm(lambda s, u: GOOD, model="small"))
    assert by == "small" and r.route_source == "llm"
    assert notes == ["introduction: big: invalid JSON twice; fresh try: invalid JSON twice; small wrote it"]


def test_the_introduction_counts_against_the_tier_1_budget():
    assert "intro" in TIER1


def test_the_scripted_intro_answer_passes_every_check():
    r, ss = _intro_reading()
    llm = ScriptedLlm(lambda s, u: intro_answer(u))
    assert write_intro(llm, None, None, r, ss, {}) == ([], "big")


def test_a_thread_with_open_checks_is_never_marked_skim():
    r, ss = _intro_reading()
    route = [{**GOOD["route"][0], "skim": True}, *GOOD["route"][1:]]
    notes, _ = write_intro(ScriptedLlm(lambda s, u: _with(route=route)), None, None, r, ss, {})
    assert notes == [] and [s.skim for s in r.route] == [False, False, True]
