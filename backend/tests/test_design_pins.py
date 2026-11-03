"""Pinned design text (spec 2026-11-02 §10): what a pin keeps, and how a later design finds its part again."""
import pytest
from test_llm_design import GOOD

from codetortoise import design as rules
from codetortoise.design_pins import apply_pins, pin_of, story_titles, walk_key
from codetortoise.llm import design as dl


def _rules(demo):
    return rules.build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)


@pytest.fixture
def written(demo):
    """The demo's design with every part of GOOD written into it."""
    d = _rules(demo)
    assert dl.apply_answer(d, demo.r, dl._Out.model_validate(GOOD)) == []
    return d


def test_a_pin_keeps_the_part_s_words_and_the_names_of_what_it_cites(demo, written):
    titles = story_titles(demo.ss)
    v = pin_of(written, "verdict", titles)
    assert (v.part, v.verdict, v.verdict_causes) == ("verdict", GOOD["verdict"], ["c504c9fbd94"])
    o = pin_of(written, "ownership", titles)
    assert o.nodes == {"N3": written.nodes["N3"].label} and o.stories == {"S1": titles["S1"]}
    assert set(pin_of(written, "concerns", titles).stories) == {"S1", "S2", "S5", "S3"}
    w = pin_of(written, "walk:W1", titles)
    assert (w.part, w.title, w.key) == ("walk", "A write longer than 64 bytes", walk_key(written, written.walks[0]))
    g = pin_of(written, "gate:G1", titles)
    assert (g.part, g.false_case, g.key) == ("gate", "Writes that fit (64 bytes or less)", "uart_send|len > 64")


def test_a_fresh_design_takes_each_pin_and_marks_its_part_pinned(demo, written):
    titles = story_titles(demo.ss)
    pins = [pin_of(written, p, titles) for p in ("verdict", "concerns", "ownership", "walk:W1", "gate:G1")]
    fresh = _rules(demo)
    assert apply_pins(fresh, demo.r, titles, pins) == (pins, [])
    assert (fresh.verdict, fresh.concerns, fresh.ownership) == (written.verdict, written.concerns, written.ownership)
    assert (fresh.walks[0].title, fresh.walks[0].lead, fresh.walks[0].title_source) == (
        written.walks[0].title, written.walks[0].lead, "llm")
    assert fresh.gates[0].false_case == written.gates[0].false_case
    assert fresh.sources == {"verdict": "pinned", "concerns": "pinned", "ownership": "pinned", "walk:W1": "pinned",
                             "gate:G1": "pinned"}


def test_a_walk_through_s_pin_finds_it_by_what_it_is_and_a_function_by_its_name(demo, written):
    titles = story_titles(demo.ss)
    pins = [pin_of(written, "walk:W1", titles), pin_of(written, "ownership", titles)]
    fresh = _rules(demo)
    fresh.walks.reverse()                                            # listed in another order: W1 is W4 now
    for i, w in enumerate(fresh.walks, 1):
        w.id = f"W{i}"
    fresh.nodes["N99"] = fresh.nodes.pop("N3")                       # the function the ownership line cites, renumbered
    for w in fresh.walks:
        w.parts = ["N99" if n == "N3" else n for n in w.parts]
        for s in w.steps:
            s.src, s.dst = ("N99" if s.src == "N3" else s.src), ("N99" if s.dst == "N3" else s.dst)
    for g in fresh.gates:
        g.node = "N99" if g.node == "N3" else g.node
    assert apply_pins(fresh, demo.r, titles, pins) == (pins, [])
    assert fresh.walks[3].title == "A write longer than 64 bytes" and fresh.sources["walk:W4"] == "pinned"
    assert fresh.ownership[1].cites == ["N99", "S1"] and "walk:W1" not in fresh.sources


def test_a_pin_that_no_longer_fits_is_dropped_with_a_note(demo, written):
    titles = story_titles(demo.ss)
    pins = [pin_of(written, p, titles) for p in ("verdict", "concerns", "ownership", "walk:W1", "gate:G1")]
    r = demo.r.model_copy(deep=True)
    r.causes = [c for c in r.causes if c.id != "c504c9fbd94"]       # the check the verdict names is gone
    fresh = _rules(demo)
    fresh.walks[0].steps = fresh.walks[0].steps[:-1]                # W1 ends elsewhere now
    fresh.gates[0].test = "len > 128"                               # and its condition reads otherwise
    kept, notes = apply_pins(fresh, r, {**titles, "S1": "Another story"}, pins)
    assert kept == [] and notes == ["the pinned verdict no longer fits the change and was unpinned",
                                    "the pinned concerns no longer fit the change and were unpinned",
                                    "the pinned ownership lines no longer fit the change and were unpinned",
                                    "a pinned walk-through title no longer fits the change and was unpinned",
                                    "a pinned condition name no longer fits the change and was unpinned"]
    assert (fresh.verdict, fresh.concerns, fresh.ownership, fresh.sources) == ("", [], [], {})


def test_a_pin_keeps_who_had_its_words_rewritten_and_puts_that_back_where_the_part_is_now(demo, written):
    """Final review I2: the record of a reader's rewrite goes with the pinned words, to the walk-through's id now; a pin
    without one leaves its part without one."""
    from codetortoise.design import Rewrite
    titles = story_titles(demo.ss)
    written.rewrites = {"walk:W1": Rewrite(by="bob", instruction="Name the 64-byte limit"), "verdict": Rewrite(by="alice")}
    pins = [pin_of(written, p, titles) for p in ("walk:W1", "verdict", "gate:G1")]
    fresh = _rules(demo)
    fresh.walks.reverse()                                            # listed in another order: W1 is W4 now
    for i, w in enumerate(fresh.walks, 1):
        w.id = f"W{i}"
    fresh.rewrites = {"gate:G1": Rewrite(by="carol")}                # a record the pinned words don't carry
    assert apply_pins(fresh, demo.r, titles, pins) == (pins, [])
    assert fresh.rewrites == {"walk:W4": Rewrite(by="bob", instruction="Name the 64-byte limit"),
                              "verdict": Rewrite(by="alice")}
