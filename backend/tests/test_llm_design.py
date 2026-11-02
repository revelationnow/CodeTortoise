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
