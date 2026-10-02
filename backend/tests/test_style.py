"""Microsoft style and Diátaxis modes for LLM text: the checkable rules."""
from codetortoise.llm.style import MODES, STYLE, check_style


def test_the_rule_set_names_the_guide_and_each_mode():
    assert "Microsoft Writing Style Guide" in STYLE and "active voice" in STYLE
    assert set(MODES) == {"explanation", "how-to", "headline"}
    assert "Diátaxis" in MODES["explanation"] and "imperative verb" in MODES["how-to"]


def test_banned_words_and_exclamations_are_flagged():
    assert check_style("Please simply check the result.", "explanation") == ["avoid 'Please'", "avoid 'simply'"]
    assert check_style("It's just easy, e.g. here etc.", "explanation") == [
        "avoid 'just'", "avoid 'easy'", "avoid 'e.g.'", "avoid 'etc.'"]
    assert check_style("This breaks the build!", "explanation") == ["avoid '!'"]


def test_code_is_not_prose():
    assert check_style("logger_flush checks `rc != 0` and `!ptr`; simply_read stays.", "explanation") == []
    assert check_style("uart_send returns -2 when len != 0.", "explanation") == []


def test_long_sentences_are_flagged():
    long = " ".join(["word"] * 31) + "."
    assert check_style(long, "explanation") == ["sentence over 30 words"]
    assert check_style(" ".join(["word"] * 30) + ". Short one.", "explanation") == []


def test_headlines_are_short_with_no_final_period():
    assert check_style("logger_flush ignores -2", "headline") == []
    assert check_style("logger_flush ignores -2.", "headline") == ["headline ends with a period"]
    assert check_style("one two three four five six seven eight nine", "headline") == ["headline over 8 words"]


def test_how_to_steps_start_with_an_imperative_verb():
    for ok in ("Check that logger_flush handles -2.", "Run the uart tests.", "Confirm `err` is reset.", "Pass -2 to the caller.",
               "Focus on the -2 path."):
        assert check_style(ok, "how-to") == [], ok
    for bad in ("The caller ignores -2.", "Checks the result.", "Checking the result.", "You should check it.",
                "Verified by tests."):
        assert check_style(bad, "how-to") == ["step does not start with an imperative verb"], bad
