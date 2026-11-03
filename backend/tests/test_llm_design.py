"""The design overview's model call (spec 2026-11-02 §10): its prompt, the checks on each part, and what they leave."""
import pytest

from codetortoise import design as rules
from codetortoise.llm import design as dl
from codetortoise.llm.design import prompt


@pytest.fixture
def made(demo):
    """The demo's design as the rules build it, a new one per test: the model's parts are written into it."""
    return rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)


def _walk(text: str, wid: str) -> str:
    return text.split(f"\n{wid} | ", 1)[1].split("\nW", 1)[0]


def test_the_prompt_lists_the_threads_checks_components_names_conditions_and_each_walk_through_s_steps(demo, made):
    text = prompt(made, demo.r, demo.ss)
    assert text.startswith(dl.ASK)
    assert "THE CHANGE: A and B: both run inside `main`; B and C: nothing besides arriving in CL 104." in text
    assert "THREAD LIST (id | name | purpose):" in text and "THREADS (id" not in text and "THREAD DETAILS (id" not in text
    assert "\nT1 | `hal_write` in hal | main reaches uart_init, which calls hal_write." in text
    assert ("\n  stories: S2 `hal_write`'s signature changed; `uart_init` calls it (behaviour); S1 `uart_send` can now "
            "return -2; `logger_flush` ignores it (1 more effect) (behaviour)\n") in text
    assert "CHECKS BY CAUSE (id | kind | thread | story | what):" in text
    assert "\nc504c9fbd94 | result | T1 | S1 | `logger_flush` ignores the result of `uart_send`, which can now return -2\n" in text
    assert "\nc072df68d70 | ask | T3 | - | Ask the author how this thread relates to the rest of the change" in text
    assert "COMPONENTS (name | layer | threads | changed files):" in text
    assert "\ndriver | driver | T1 | driver/uart.c, driver/uart.h\n  crossing: `uart_init`, `uart_send` call `hal_write`\n" in text
    assert "\ncpp | cpp, include/hal | T3 | cpp/engine.cpp\n  shares no calls or fields with the rest\n" in text
    assert "\nN10 | uart_send | driver | driver/uart.c:11\n" in text
    assert "\nN26 | Uart::errors | driver | driver/uart.h:15\n" in text
    assert "\nG1 | len > 64 | uart_send | driver/uart.c:16 | 13 | 2\n" in text
    w1 = _walk(text, "W1")
    assert w1.startswith("G1 true | T1 with T2 | S1\n")
    assert "\n  1. `main` calls `logger_flush(&g_log)` (S1's call path)" in w1
    assert "\n  4. `uart_send` writes `Uart::errors`: `*err += 1` (new; S1's change)" in w1
    assert "\n  5. `uart_send` returns `-2` to `logger_flush` (new; S1 flow 1, check c504c9fbd94)" in w1
    assert "\n  6. `logger_flush` returns to `main` (unchanged code)" in w1
    assert "\n  8. `uart_errors` reads `Uart::errors`: `u->errors` (S1 flow 2, check c688d2f20d3)" in w1
    assert _walk(text, "W2").startswith("G1 false | T1 | S1, S2\n") and _walk(text, "W4").startswith("- | T2 | S5, S3\n")


def test_a_long_walk_through_shows_its_first_steps_and_counts_the_rest(demo, made):
    made.walks[0].steps = made.walks[0].steps * 2
    w1 = _walk(prompt(made, demo.r, demo.ss), "W1")
    assert "\n  12. " in w1 and "\n  13. " not in w1 and w1.endswith("\n  … +6 more steps")


def test_the_prompt_lists_at_most_its_share_of_checks_and_names_hazards_first(demo, made, monkeypatch):
    monkeypatch.setattr(dl, "CAUSES_SHOWN", 2)
    monkeypatch.setattr(dl, "NODES_SHOWN", 3)
    made_r = demo.r.model_copy(deep=True)
    made_r.causes[3].kind = "hazard"                         # c504c9fbd94
    text = prompt(made, made_r, demo.ss)
    checks = text.split("CHECKS BY CAUSE (id | kind | thread | story | what):\n", 1)[1].split("\nCOMPONENTS", 1)[0]
    assert [line.split(" | ")[0] for line in checks.splitlines()] == ["c504c9fbd94", "c8143badb9b", "… +4 more checks"]
    names = text.split("FUNCTIONS AND FIELDS (id | name | component | where):\n", 1)[1].split("\nCONDITIONS", 1)[0]
    assert [line.split(" | ")[0] for line in names.splitlines()] == ["N2", "N3", "N4", "… +8 more"]


GOOD = {
    "verdict": "The change holds together, but one new result goes unchecked. Settle whether `logger_flush` must "
               "handle the new -2.",
    "verdict_causes": ["c504c9fbd94"],
    "concerns": [
        {"text": "Senders learn when a write is too long",
         "how": "`uart_send` now returns -2 for a write longer than 64 bytes.", "stories": ["S1"],
         "assessment": "confirm", "note": "`logger_flush` drops the -2.", "causes": ["c504c9fbd94"]},
        {"text": "Register numbers are never negative", "how": "`hal_write` now takes an unsigned register.",
         "stories": ["S2"], "assessment": "right"},
        {"text": "The logger starts at a known level", "how": "`logger_init` now sets the level to 2.",
         "stories": ["S5", "S3"], "assessment": "note"}],
    "ownership": [
        {"tag": "right", "text": "The driver owns the length check.", "cites": ["driver/uart.c"]},
        {"tag": "questionable", "text": "The logger decides what a failed send means, and it drops the result.",
         "cites": ["N3", "S1"]},
        {"tag": "shortfall", "text": "Nothing tells the caller of `logger_write` that a write was dropped.",
         "cites": ["S1"]}],
    "walks": [
        {"id": "W1", "title": "A write longer than 64 bytes",
         "lead": "It follows a long write from `main` into `uart_send` and back."},
        {"id": "W2", "title": "A write that fits", "lead": "It follows a short write down to `hal_write`."},
        {"id": "W3", "title": "Setting up the UART", "lead": "It follows `uart_init` into the new `hal_write`."},
        {"id": "W4", "title": "The logger's level", "lead": "It follows the new level from `logger_init` to "
         "`logger_level`."}],
    "conditions": [{"id": "G1", "false_case": "Writes that fit (64 bytes or less)"}]}


def _with(**part):
    return {**GOOD, **part}


def _write(demo, d, answer, **kw):
    from scripted_llm import ScriptedLlm
    return dl.write_design(ScriptedLlm(lambda s, u: answer), None, None, d, demo.r, demo.ss, **kw)


def test_an_accepted_answer_writes_every_part_and_says_the_model_wrote_it(demo, made):
    assert _write(demo, made, GOOD) == ([], "big")
    assert made.verdict.startswith("The change holds together") and made.verdict_causes == ["c504c9fbd94"]
    assert [(c.text, c.stories, c.assessment, c.note, c.causes) for c in made.concerns] == [
        ("Senders learn when a write is too long", ["S1"], "confirm", "`logger_flush` drops the -2.", ["c504c9fbd94"]),
        ("Register numbers are never negative", ["S2"], "right", "", []),
        ("The logger starts at a known level", ["S5", "S3"], "note", "", [])]
    assert [(o.tag, o.cites) for o in made.ownership] == [
        ("right", ["driver/uart.c"]), ("questionable", ["N3", "S1"]), ("shortfall", ["S1"])]
    assert [(w.id, w.title, w.title_source) for w in made.walks] == [
        ("W1", "A write longer than 64 bytes", "llm"), ("W2", "A write that fits", "llm"),
        ("W3", "Setting up the UART", "llm"), ("W4", "The logger's level", "llm")]
    assert made.walks[0].lead == "It follows a long write from `main` into `uart_send` and back."
    assert made.gates[0].false_case == "Writes that fit (64 bytes or less)"
    assert made.sources == {"verdict": "llm", "concerns": "llm", "ownership": "llm", "walk:W1": "llm", "walk:W2": "llm",
                            "walk:W3": "llm", "walk:W4": "llm", "gate:G1": "llm"}


def test_a_concern_on_a_cause_the_review_lacks_is_a_note_without_chips_and_so_is_a_confirm_on_none(demo, made):
    concerns = [{**GOOD["concerns"][0], "causes": ["c0000000000"]}, {**GOOD["concerns"][0], "causes": []},
                {**GOOD["concerns"][1], "assessment": "ask", "causes": ["c504c9fbd94", "c0000000000"]},
                {**GOOD["concerns"][1], "causes": ["c8143badb9b"]}]
    assert _write(demo, made, _with(concerns=concerns)) == ([], "big")
    assert [(c.assessment, c.causes) for c in made.concerns] == [
        ("note", []), ("note", []), ("note", []), ("right", ["c8143badb9b"])]


def test_each_failing_part_keeps_its_fixed_text_or_is_left_out_and_only_that_part(demo):
    c, o, w = GOOD["concerns"], GOOD["ownership"], GOOD["walks"]
    cases = {
        "a node id in the verdict": (_with(verdict="N10 now returns -2. Settle whether its callers handle it."),
                                     "the verdict"),
        "a cause id in the verdict": (_with(verdict="c504c9fbd94 is open. Settle it."), "the verdict"),
        "a verdict naming no check": (_with(verdict_causes=[]), "the verdict"),
        "a verdict naming a check it was not shown": (_with(verdict_causes=["c0000000000"]), "the verdict"),
        "a four-sentence verdict": (_with(verdict="A holds. B holds. C holds. Settle D."), "the verdict"),
        "a concern on an unlisted story": (_with(concerns=[*c[:2], {**c[2], "stories": ["S9"]}]), "1 concern(s)"),
        "a concern on no story": (_with(concerns=[*c[:2], {**c[2], "stories": []}]), "1 concern(s)"),
        "two sentences of how": (_with(concerns=[{**c[0], "how": "It returns -2. Callers see it."}, *c[1:]]),
                                 "1 concern(s)"),
        "a nine-word concern": (_with(concerns=[{**c[0], "text": "One two three four five six seven eight nine"},
                                                *c[1:]]), "1 concern(s)"),
        "an unknown assessment": (_with(concerns=[{**c[0], "assessment": "maybe"}, *c[1:]]), "1 concern(s)"),
        "no concerns": (_with(concerns=[]), "the concerns"),
        "an uncited ownership line": (_with(ownership=[*o[:2], {**o[2], "cites": []}]), "1 ownership line(s)"),
        "a cite it was not shown": (_with(ownership=[{**o[0], "cites": ["drv/old.c"]}, *o[1:]]), "1 ownership line(s)"),
        "an unknown tag": (_with(ownership=[{**o[0], "tag": "good"}, *o[1:]]), "1 ownership line(s)"),
        "two walk-throughs with one title": (_with(walks=[w[0], {**w[1], "title": "A Write Longer Than 64 Bytes"},
                                                          *w[2:]]), "1 walk-through title(s)"),
        "a title with a final period": (_with(walks=[{**w[0], "title": "A long write."}, *w[1:]]),
                                        "1 walk-through title(s)"),
        "a walk-through with no lead": (_with(walks=[{**w[0], "lead": ""}, *w[1:]]), "1 walk-through title(s)"),
        "a false case naming a node": (_with(conditions=[{"id": "G1", "false_case": "When N10 gets a short write"}]),
                                       "1 condition name(s)"),
        "thread ids in the verdict": (_with(verdict="T1 now returns -2 that T2 ignores. Settle whether T2 must handle it."),
                                      "the verdict"),
        "condition and walk-through ids in a lead": (_with(walks=[{**w[0], "lead": "It follows the G1 true case of W1 into T1."},
                                                                  *w[1:]]), "1 walk-through title(s)"),
        "a false case naming a walk-through": (_with(conditions=[{"id": "G1", "false_case": "When W2 takes the short path"}]),
                                               "1 condition name(s)"),
    }
    for name, (answer, part) in cases.items():
        d = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
        assert _write(demo, d, answer) == ([f"design: {part} failed the checks"], "big"), name


def test_a_walk_through_whose_title_fails_keeps_its_fixed_title_and_no_lead(demo, made):
    _write(demo, made, _with(walks=[{**GOOD["walks"][0], "title": "A long write."}, *GOOD["walks"][1:]]))
    assert (made.walks[0].title, made.walks[0].lead, made.walks[0].title_source) == ("When `len > 64`", "", "template")
    assert "walk:W1" not in made.sources and made.walks[1].title == "A write that fits"


def test_several_failing_parts_are_named_together(demo, made):
    answer = {"verdict": "", "concerns": [], "ownership": [{"tag": "note", "text": "Uncited.", "cites": []}],
              "walks": [], "conditions": []}
    assert _write(demo, made, answer) == ([
        "design: the verdict, the concerns, 1 ownership line(s), 4 walk-through title(s) and 1 condition name(s) "
        "failed the checks"], "big")


def test_a_model_that_fails_or_is_refused_leaves_the_rules_design_exactly(demo, made):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.ledger import Refused
    before = made.model_dump()
    notes, by = dl.write_design(ScriptedLlm(lambda s, u: RuntimeError("down")), None, None, made, demo.r, demo.ss)
    assert by is None and notes == ["design: big: RuntimeError: down; fresh try: RuntimeError: down; the fixed text stays"]
    assert made.model_dump() == before

    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            assert (purpose, target) == ("design", "design")
            raise Refused("this review has used its 10 tier-1 AI calls")
    notes, by = dl.write_design(ScriptedLlm(lambda s, u: GOOD), Budget(), 1, made, demo.r, demo.ss)
    assert by is None and notes == ["design: AI budget: this review has used its 10 tier-1 AI calls; the fixed text stays"]
    assert made.model_dump() == before


def test_the_design_the_strong_model_fails_is_written_by_the_weak_model_and_says_so(demo, made):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.client import LlmError
    notes, by = dl.write_design(ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x")), None, None,
                                made, demo.r, demo.ss, weak=ScriptedLlm(lambda s, u: GOOD, model="small"))
    assert by == "small" and made.sources["verdict"] == "llm"
    assert notes == ["design: big: invalid JSON twice; fresh try: invalid JSON twice; small wrote it"]


def test_the_kept_text_puts_back_every_part_the_model_wrote(demo, made):
    _write(demo, made, GOOD)
    kept = dl.design_text(made)
    again = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    dl.apply_design_text(again, kept)
    assert again.model_dump() == made.model_dump()


def test_the_design_counts_against_the_tier_1_budget():
    from codetortoise.llm.ledger import TIER1
    assert "design" in TIER1


def test_the_scripted_design_answer_passes_every_check(demo, made):
    from scripted_llm import ScriptedLlm, design_answer
    assert dl.write_design(ScriptedLlm(lambda s, u: design_answer(u)), None, None, made, demo.r, demo.ss) == ([], "big")


def test_the_prompt_reads_the_design_context_first_and_has_no_such_section_without_one(demo, made):
    text = prompt(made, demo.r, demo.ss, "The UART must never drop a byte.")
    assert ("\n\nDESIGN CONTEXT (from the review's owner):\nThe UART must never drop a byte.\nEND OF DESIGN CONTEXT\n"
            "THE CHANGE: ") in text
    assert "DESIGN CONTEXT (from" not in prompt(made, demo.r, demo.ss)
    assert "draw the concerns from it" in dl.ASK and dl.DESIGN_VERSION >= 2


def test_the_model_call_asks_with_the_design_context(demo, made):
    from scripted_llm import ScriptedLlm, design_answer
    llm = ScriptedLlm(lambda system, user: design_answer(user))
    dl.write_design(llm, None, None, made, demo.r, demo.ss, context="Never drop a byte.")
    assert "DESIGN CONTEXT (from the review's owner):\nNever drop a byte.\n" in llm.prompts[0]


REWRITTEN = "One new result goes unchecked. Settle whether `logger_flush` must handle the new -2."


class _Calls:
    """A ledger that records each call, then makes it."""

    def __init__(self):
        self.calls = []

    def call(self, llm, rid, user, purpose, target, fn):
        self.calls.append((rid, user, purpose, target))
        return fn(llm)


def test_the_parts_a_rewrite_may_ask_for(made):
    assert all(dl.has_part(made, p) for p in ("verdict", "concerns", "ownership", "walk:W1", "gate:G1"))
    assert not any(dl.has_part(made, p) for p in ("walk:W9", "gate:G9", "verdict:x", "nodes", "walk", ""))


def test_a_rewrite_asks_for_one_part_as_it_stands_with_the_reader_s_instruction(demo, made):
    _write(demo, made, GOOD)
    text = dl.rewrite_prompt(made, demo.r, demo.ss, "walk:W2", "Never drop a byte.", "  Name the register it writes ")
    assert text.startswith(prompt(made, demo.r, demo.ss, "Never drop a byte.") + "\n\n")
    assert text.endswith("\n\nREWRITE: write walk-through W2's title and lead again, and nothing else. As it stands:\n"
                         "title: A write that fits\nlead: It follows a short write down to `hal_write`.\n"
                         'Reply with the same JSON object holding only "walks", with that walk-through alone.\n'
                         "THE REVIEWER'S INSTRUCTION (follow it within the rules above): Name the register it writes")
    assert dl.rewrite_prompt(made, demo.r, demo.ss, "verdict").endswith(
        "\n\nREWRITE: write the verdict again, and nothing else. As it stands:\n" + GOOD["verdict"]
        + '\nReply with the same JSON object holding only "verdict" and "verdict_causes".')
    assert ("As it stands:\n1. Senders learn when a write is too long: `uart_send` now returns -2 for a write longer than "
            "64 bytes. (confirm: `logger_flush` drops the -2.)\n2. ") in dl.rewrite_prompt(made, demo.r, demo.ss, "concerns")
    assert "As it stands:\nright: The driver owns the length check.\nquestionable: " in dl.rewrite_prompt(
        made, demo.r, demo.ss, "ownership")
    assert "As it stands:\nfalse case: Writes that fit (64 bytes or less)\nReply" in dl.rewrite_prompt(
        made, demo.r, demo.ss, "gate:G1")
    fresh = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    assert "As it stands:\n(none)\nReply" in dl.rewrite_prompt(fresh, demo.r, demo.ss, "verdict")


def test_a_rewrite_changes_that_part_alone_and_is_charged_to_whoever_asked(demo, made):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.ledger import TIER1
    _write(demo, made, GOOD)
    before = made.model_dump()
    ledger = _Calls()
    answer = _with(verdict=REWRITTEN, concerns=GOOD["concerns"][:1], walks=[{**GOOD["walks"][0], "title": "Another"}])
    new, by = dl.rewrite_part(ScriptedLlm(lambda s, u: answer), ledger, 7, "bob", made, demo.r, demo.ss, "verdict",
                              instruction="Shorter")
    assert by == "big" and ledger.calls == [(7, "bob", "rewrite", "verdict")] and "rewrite" not in TIER1
    assert made.model_dump() == before                              # the design it was given is left as it was
    assert (new.verdict, new.verdict_causes, new.sources["verdict"]) == (REWRITTEN, ["c504c9fbd94"], "llm")
    assert new.model_dump()["rewrites"] == {"verdict": {"by": "bob", "instruction": "Shorter"}}
    rest = {k: v for k, v in new.model_dump().items() if k not in ("verdict", "verdict_causes", "rewrites")}
    assert rest == {k: v for k, v in before.items() if k not in ("verdict", "verdict_causes", "rewrites")}


def test_a_rewritten_title_must_differ_from_the_others_and_an_answer_that_fails_changes_nothing(demo, made):
    from scripted_llm import ScriptedLlm
    _write(demo, made, GOOD)

    def walk(title):
        return _with(walks=[{"id": "W2", "title": title, "lead": "It follows a short write to the register."}])
    new, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: walk("A short write")), None, None, None, made, demo.r, demo.ss,
                             "walk:W2")
    assert [w.title for w in new.walks] == ["A write longer than 64 bytes", "A short write", "Setting up the UART",
                                            "The logger's level"]
    assert new.walks[1].lead == "It follows a short write to the register." and new.sources["walk:W2"] == "llm"
    same, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: walk("Setting up the UART")), None, None, None, made, demo.r,
                              demo.ss, "walk:W2")
    assert same is None                                             # W3's title already
    bad, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(verdict="Too short.")), None, None, None, made, demo.r,
                             demo.ss, "verdict")
    assert bad is None
    gone, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(ownership=[])), None, None, None, made, demo.r, demo.ss,
                              "ownership")
    assert gone is None


def test_a_rewrite_whose_answer_fails_one_row_of_its_part_changes_nothing(demo, made):
    """Final review I1: a concerns or ownership answer with one good row and one bad row is a failed rewrite, not a
    part with the bad row left out."""
    from scripted_llm import ScriptedLlm
    _write(demo, made, GOOD)
    bad_concern = {**GOOD["concerns"][1], "stories": ["S99"]}         # a story the review lacks
    half, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(concerns=[GOOD["concerns"][0], bad_concern])), None, None,
                              None, made, demo.r, demo.ss, "concerns")
    assert half is None
    bad_line = {**GOOD["ownership"][0], "cites": ["nowhere.c"]}       # cites nothing the review shows
    half, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(ownership=[GOOD["ownership"][1], bad_line])), None, None,
                              None, made, demo.r, demo.ss, "ownership")
    assert half is None


def test_a_rewrite_over_a_limit_is_refused_and_one_no_model_answers_raises(demo, made):
    from scripted_llm import ScriptedLlm

    from codetortoise.llm.ledger import Refused
    from codetortoise.llm.tiers import TiersFailed

    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            raise Refused("you've used your 20 AI calls today")
    with pytest.raises(Refused):
        dl.rewrite_part(ScriptedLlm(lambda s, u: GOOD), Budget(), 1, "bob", made, demo.r, demo.ss, "verdict")
    with pytest.raises(TiersFailed, match="big: RuntimeError: down; fresh try: RuntimeError: down"):
        dl.rewrite_part(ScriptedLlm(lambda s, u: RuntimeError("down")), None, None, "bob", made, demo.r, demo.ss,
                        "verdict")


def test_a_rewrite_lands_on_the_design_as_it_is_then_and_on_the_kept_text(demo, made):
    from scripted_llm import ScriptedLlm
    _write(demo, made, GOOD)
    kept = dl.design_text(made)
    new, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(verdict=REWRITTEN)), None, None, None, made, demo.r,
                             demo.ss, "verdict")
    now = made.model_copy(deep=True)
    now.concerns = now.concerns[:1]                                 # another part changed meanwhile
    dl.put_part(now, new, "verdict")
    assert now.verdict == REWRITTEN and len(now.concerns) == 1
    walk, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(walks=[{**GOOD["walks"][1], "title": "A short write"}])),
                              None, None, None, made, demo.r, demo.ss, "walk:W2")
    dl.put_part(now, walk, "walk:W2")
    assert now.walks[1].title == "A short write" and now.walks[0].title == "A write longer than 64 bytes"
    again = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    dl.apply_design_text(again, dl.patch_kept(dl.patch_kept(kept, now, "verdict"), now, "walk:W2"))
    assert again.verdict == REWRITTEN and again.walks[1].title == "A short write"
    assert [c.text for c in again.concerns] == [c["text"] for c in GOOD["concerns"]]


def test_a_rewrite_says_who_asked_and_how_and_the_record_goes_where_its_words_go(demo, made):
    """Final review I2: a reader's rewrite records who asked and their instruction, so words they steered don't read as
    the model's own; the record lands with the words and the kept text keeps it for a re-run of the same prompt."""
    from scripted_llm import ScriptedLlm

    from codetortoise.design import Rewrite
    _write(demo, made, GOOD)
    kept = dl.design_text(made)
    new, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: _with(verdict=REWRITTEN)), None, 7, "bob", made, demo.r, demo.ss,
                             "verdict", instruction=" Shorter ")
    assert new.rewrites == {"verdict": Rewrite(by="bob", instruction="Shorter")} and made.rewrites == {}
    now = made.model_copy(deep=True)
    dl.put_part(now, new, "verdict")
    assert now.rewrites == new.rewrites
    again = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    dl.apply_design_text(again, dl.patch_kept(kept, now, "verdict"))
    assert again.rewrites == new.rewrites
    plain, _ = dl.rewrite_part(ScriptedLlm(lambda s, u: GOOD), None, 7, "alice", now, demo.r, demo.ss, "verdict")
    assert plain.rewrites == {"verdict": Rewrite(by="alice", instruction="")}      # the last rewrite's record
    before = rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    dl.apply_design_text(before, {k: v for k, v in kept.items() if k != "rewrites"})   # kept before records were
    assert before.rewrites == {} and before.verdict == GOOD["verdict"]


def test_the_kept_text_is_keyed_by_the_prompt_the_model_and_the_version(demo, made):
    text = prompt(made, demo.r, demo.ss)
    assert dl.design_key("big", text) == dl.design_key("big", text) != dl.design_key("small", text)
    assert dl.design_key("big", text) != dl.design_key("big", text + " ")
