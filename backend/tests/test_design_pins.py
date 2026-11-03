"""Pinned design text (spec 2026-11-02 §10): what a pin keeps, and how a later design finds its part again."""
import pytest
from test_llm_design import GOOD

from codetortoise import design as rules
from codetortoise.design_pins import Pin, apply_pins, part_of, pin_of, story_pieces, story_titles, unpin, walk_key
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
    assert (g.part, g.false_case, g.key) == ("gate", "Writes that fit (64 bytes or less)", "uart_send|len > 64|driver/uart.c|1")


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


def test_a_pinned_title_another_walk_through_now_has_is_dropped(demo, written):
    titles = story_titles(demo.ss)
    pins = [pin_of(written, "walk:W1", titles)]
    fresh = _rules(demo)
    fresh.walks[1].title = "A write longer than 64 bytes"            # the fresh answer gave W2 the pinned title
    assert apply_pins(fresh, demo.r, titles, pins) == (
        [], ["a pinned walk-through title no longer fits the change and was unpinned"])
    assert fresh.walks[0].title == "When `len > 64`" and "walk:W1" not in fresh.sources


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


def test_a_pin_keeps_a_story_whose_title_was_told_again(demo, written):
    """Phase 4 M5a: a story a pin cites is found by what the rules made it of (its pieces), whatever its title or id
    now; a pin recorded before (titles only) still matches by title."""
    titles, pieces = story_titles(demo.ss), story_pieces(demo.ss)
    pins = [pin_of(written, p, titles, pieces) for p in ("concerns", "ownership")]
    retold = {**titles, "S1": "The send path, told again"}
    fresh = _rules(demo)
    assert apply_pins(fresh, demo.r, retold, pins, pieces) == (pins, [])
    assert (fresh.concerns, fresh.ownership) == (written.concerns, written.ownership)
    r = demo.r.model_copy(deep=True)                                  # and listed under another id now
    for t in r.threads:
        t.stories = ["S9" if s == "S1" else s for s in t.stories]
    moved = {("S9" if k == "S1" else k): v for k, v in pieces.items()}
    fresh = _rules(demo)
    assert apply_pins(fresh, r, {("S9" if k == "S1" else k): v for k, v in retold.items()}, pins, moved) == (pins, [])
    assert fresh.ownership[1].cites == ["N3", "S9"]
    assert {s for c in fresh.concerns for s in c.stories} == {"S9", "S2", "S5", "S3"}
    old = [pin_of(written, p, titles) for p in ("concerns", "ownership")]       # recorded before: titles only
    assert apply_pins(_rules(demo), demo.r, titles, old, pieces) == (old, [])
    assert apply_pins(_rules(demo), demo.r, retold, old, pieces)[0] == []


def _alike(d):
    """`d` with two more conditions of G1's function and test: G8 in another file, G9 later in G1's."""
    g = d.gates[0]
    d.gates += [g.model_copy(update={"id": "G8", "path": "driver/spi.c", "line": 40, "false_case": ""}),
                g.model_copy(update={"id": "G9", "line": 30, "false_case": ""})]
    return d


def test_two_conditions_with_one_test_keep_their_own_pins(demo, written):
    """Phase 4 M5b: a condition's pin holds its file and its order among the conditions alike; one keyed the old way
    (its function and test) still finds the first of them, and unpinning that condition lets it go."""
    _alike(written)
    words = {"G1": "Short writes", "G8": "Short SPI writes", "G9": "Short retries"}
    for g in written.gates:
        g.false_case = words.get(g.id, g.false_case)
    pins = [pin_of(written, f"gate:{gid}", {}) for gid in words]
    fresh = _alike(_rules(demo))
    fresh.gates.insert(0, fresh.gates.pop(-2))                        # G8 listed first now
    assert apply_pins(fresh, demo.r, {}, pins) == (pins, [])
    assert {g.id: g.false_case for g in fresh.gates if g.id in words} == words
    old = Pin(part="gate", key="uart_send|len > 64", false_case="Writes that fit")
    again = _alike(_rules(demo))
    assert apply_pins(again, demo.r, {}, [old]) == ([old], [])
    assert [g.false_case for g in again.gates if g.id in words] == ["Writes that fit", "", ""]
    assert (part_of(again, old), part_of(again, pins[2])) == ("gate:G1", "gate:G9")
    assert unpin(again, [old, pins[1]], "gate:G1") == [pins[1]] and unpin(again, [old], "gate:G9") == [old]


def test_a_walk_through_pin_keyed_the_old_way_still_finds_it(demo, written):
    """Phase 4 M5b: a walk-through's key holds its condition's; one keyed before still finds its walk-through."""
    pin = pin_of(written, "walk:W1", {})
    old = pin.model_copy(update={"key": pin.key.replace("uart_send|len > 64|driver/uart.c|1|", "uart_send|len > 64|", 1)})
    assert old.key != pin.key
    fresh = _rules(demo)
    assert apply_pins(fresh, demo.r, {}, [old]) == ([old], [])
    assert fresh.walks[0].title == "A write longer than 64 bytes" and part_of(fresh, old) == "walk:W1"
