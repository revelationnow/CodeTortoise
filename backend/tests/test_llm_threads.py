"""Thread names, purposes and the change as a whole from the strong model (spec 2026-10-07-review-reading §9)."""
from scripted_llm import ScriptedLlm

from codetortoise.llm.ledger import TIER1, Refused
from codetortoise.llm.threads import write_threads
from codetortoise.reading import Connection, Reading, Thread
from codetortoise.stories import Story, StorySet


def _reading():
    ss = StorySet(summary="", stories=[
        Story(id="S1", kind="behaviour", title="Send gains a length type", summary="s1", purpose="Sends bytes", nodes=["N1"]),
        Story(id="S2", kind="behaviour", title="Init sets the baud", summary="s2", nodes=["N2"]),
        Story(id="S3", kind="other", title="Engine step", summary="s3", nodes=["N3"])])
    r = Reading(threads=[Thread(id="T1", name="`send` in drv", purpose="s1", stories=["S1"], cls=[11], open_checks=2),
                         Thread(id="T2", name="`init` in drv", purpose="s2", stories=["S2"], cls=[12]),
                         Thread(id="T3", name="`step` in cpp", purpose="s3", stories=["S3"], cls=[12])],
                connections=[Connection(a="T1", b="T2", kind="caller", text="both run inside `main`", facts=["N9", "N1", "N2"],
                                        shown=True),
                             Connection(a="T2", b="T3", kind="bundled", text="nothing besides arriving in CL 12",
                                        facts=["CL 12"], shown=True)],
                whole="3 threads.")
    return r, ss


GOOD = {"threads": [{"id": "T1", "name": "UART send takes unsigned lengths", "purpose": "Callers pass lengths as unsigned.",
                     "cites": ["S1", "N1"]},
                    {"id": "T2", "name": "UART init", "purpose": "Init programs the baud rate.", "cites": ["S2"]},
                    {"id": "T3", "name": "Engine step", "purpose": "The engine takes a new step.", "cites": ["S3", "CL12"]}],
        "whole": "The change makes UART lengths unsigned and sets the baud at init. The engine step arrives only with "
                 "CL 12.", "whole_cites": ["T1", "T2", "T3"],
        "connections": [{"a": "T1", "b": "T2", "text": "both run from `main` at start-up"},
                        {"a": "T2", "b": "T3", "text": "only bundled together in CL 12"}]}


def test_a_checked_answer_names_the_threads_writes_the_whole_and_rewords_connections():
    r, ss = _reading()
    llm = ScriptedLlm(lambda s, u: GOOD)
    assert write_threads(llm, None, None, r, ss, {11: "Make send unsigned", 12: "Init and engine"}) == []
    assert [(t.name, t.purpose, t.text_source) for t in r.threads] == [
        ("UART send takes unsigned lengths", "Callers pass lengths as unsigned.", "llm"),
        ("UART init", "Init programs the baud rate.", "llm"), ("Engine step", "The engine takes a new step.", "llm")]
    assert r.whole.startswith("The change makes UART") and r.whole_source == "llm"
    assert [k.text for k in r.connections] == ["both run from `main` at start-up", "only bundled together in CL 12"]
    prompt = llm.prompts[0]
    assert "CL 11 (a hint from its author, not the source of truth): Make send unsigned" in prompt
    assert "T1 | 2 open checks | CL 11 | S1 Send gains a length type: Sends bytes" in prompt
    assert "T1 | T2 | caller | both run inside `main` | N9 N1 N2" in prompt


def test_answers_citing_unknown_ids_too_long_names_or_dropping_a_connections_fact_keep_the_fixed_text():
    r, ss = _reading()
    bad = {"threads": [{"id": "T1", "name": "A", "purpose": "B.", "cites": ["S9"]},
                       {"id": "T2", "name": "one two three four five six seven", "purpose": "C.", "cites": ["S2"]},
                       {"id": "T3", "name": "Engine", "purpose": "D.", "cites": []}],
           "whole": "Whole. Text.", "whole_cites": ["T7"],
           "connections": [{"a": "T1", "b": "T2", "text": "both start up together"},
                           {"a": "T2", "b": "T3", "text": "they belong together"}]}
    notes = write_threads(ScriptedLlm(lambda s, u: bad), None, None, r, ss, {})
    assert [(t.name, t.text_source) for t in r.threads] == [("`send` in drv", "template"), ("`init` in drv", "template"),
                                                           ("`step` in cpp", "template")]
    assert (r.whole, r.whole_source) == ("3 threads.", "template")
    assert [k.text for k in r.connections] == ["both run inside `main`", "nothing besides arriving in CL 12"]
    assert notes == ["thread text: 3 thread(s), the whole and 2 connection(s) failed the checks; their fixed text stays"]


def test_a_failed_or_refused_call_keeps_every_fixed_text_and_says_why():
    r, ss = _reading()
    notes = write_threads(ScriptedLlm(lambda s, u: RuntimeError("down")), None, None, r, ss, {})
    assert notes == ["thread text: RuntimeError: down; the fixed text stays"] and r.whole_source == "template"

    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            assert (purpose, target) == ("threads", "threads")
            raise Refused("this review has used its 10 tier-1 AI calls")
    notes = write_threads(ScriptedLlm(lambda s, u: GOOD), Budget(), 1, r, ss, {})
    assert notes == ["thread text: AI budget: this review has used its 10 tier-1 AI calls; the fixed text stays"]


def test_the_thread_text_counts_against_the_tier_1_budget():
    assert "threads" in TIER1
