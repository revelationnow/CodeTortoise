"""Tier 2 starts from the brief (spec 2026-10-05-two-tier-stories §8)."""
from codetortoise.brief import Brief, BriefVerdict
from codetortoise.detectors.base import Finding
from codetortoise.llm.brief_context import BRIEF_CHARS, brief_context
from codetortoise.store import Store
from codetortoise.stories import Story, StorySet


def _review(tmp_path, overview="CHANGE: 2 CLs, 3 files"):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    f = Finding(id="F1", kind="contract", severity="high", title="hal_write: signature changed", summary="s", nodes=["N1"],
                verdict="hazard", verdict_reason="old_user still calls it the old way.", verdict_cites=["drv/old.c:3"],
                verdict_source="tier1")
    store.put_brief(rid, "k", Brief(key="k", overview=overview, facts={"contract|hal_write: signature changed":
                                                                       "call sites of hal_write (N1):\n  drv/old.c:3 ..."},
                                    verdicts={"contract|hal_write: signature changed": BriefVerdict(
                                        verdict="hazard", reason="old_user still calls it the old way.")}))
    st = Story(id="S1", kind="behaviour", title="HAL writes take a width", summary="s", nodes=["N1", "N2"], flows=["W1"],
               findings=["F1"], purpose="This widens the HAL write.", check=["Check every caller passes a width."],
               questions=["Does the DSP call it?"], source="tier1")
    store.put_blob(rid, "stories", StorySet(summary="s", stories=[st]))
    return store, rid, f


def test_a_finding_s_prompt_starts_with_its_story_verdict_and_facts(tmp_path):
    store, rid, f = _review(tmp_path)
    text = brief_context(store, rid, finding=f)
    assert text.splitlines()[1:] == [
        "STORY: HAL writes take a width — This widens the HAL write.",
        "VERDICT (strong model): hazard — old_user still calls it the old way. (cites drv/old.c:3)",
        "PREPARED FACTS:", "call sites of hal_write (N1):", "  drv/old.c:3 ..."]
    assert text.startswith("BRIEF (")


def test_a_story_flow_or_file_prompt_gets_purpose_checks_and_questions(tmp_path):
    store, rid, _ = _review(tmp_path)
    want = ["STORY: HAL writes take a width — This widens the HAL write.", "What to check: Check every caller passes a width.",
            "Open questions: Does the DSP call it?"]
    assert brief_context(store, rid, story="S1").splitlines()[1:] == want
    assert brief_context(store, rid, flow="W1").splitlines()[1:] == want
    assert brief_context(store, rid, nodes=["N2"]).splitlines()[1:] == want
    assert brief_context(store, rid, nodes=["N9"]) == ""          # nothing known: the prompt is unchanged


def test_tortoise_gets_the_overview_and_its_anchor_s_story_within_800_tokens(tmp_path):
    store, rid, _ = _review(tmp_path, overview="CHANGE: " + "x" * 9000)
    text = brief_context(store, rid, story="S1", overview=True)
    assert text.splitlines()[1] == "STORY: HAL writes take a width — This widens the HAL write."
    assert "CHANGE OVERVIEW:" in text and len(text) == BRIEF_CHARS and text.endswith("…")


def test_a_review_without_a_brief_or_stories_adds_nothing(tmp_path):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    assert brief_context(store, rid, story="S1", overview=True) == ""


def test_stories_stored_before_briefs_existed_add_nothing(tmp_path):
    store, _, _ = _review(tmp_path)
    old = store.create_review("t", "owner", [2])
    st = Story(id="S1", kind="behaviour", title="Other changes in `src`", summary="s", nodes=["N1"], findings=["F1"])
    store.put_blob(old, "stories", StorySet(summary="s", stories=[st]))
    assert brief_context(store, old, story="S1") == "" and brief_context(store, old, nodes=["N1"]) == ""


def test_the_brief_says_who_worked_it_out(tmp_path):
    store, rid, _ = _review(tmp_path)                                  # stored without a model: the rules formed it
    assert brief_context(store, rid, story="S1").startswith("BRIEF (worked out by code; build on it:")
    store.put_brief(rid, "k", Brief(key="k", model="big", overview="CHANGE: 2 CLs"))
    assert brief_context(store, rid, story="S1").startswith("BRIEF (worked out by the strong model and by code;")
