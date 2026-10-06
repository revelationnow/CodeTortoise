"""Measuring how stable tier 1's stories are (spec 2026-10-05-two-tier-stories §4.6)."""
import itertools

from helpers import make_services
from test_pipeline import _one_story_per_cl, _strong

from codetortoise.cli import main
from codetortoise.grouping import Placement, PlannedStory, StoryPlan
from codetortoise.pipeline import run_review
from codetortoise.stories_check import agreement, pair_counts, stories_check


def _plan(*groups, unsorted=()):
    stories = [PlannedStory(key=f"s{i}", source="tier1", placements=[Placement(piece=p, reason="same_feature") for p in g])
               for i, g in enumerate(groups)]
    if unsorted:
        stories.append(PlannedStory(key="unsorted", unsorted=True, source="tier1",
                                    placements=[Placement(piece=p, reason="unclear") for p in unsorted]))
    return StoryPlan(stories=stories)


def test_pairs_count_the_runs_putting_them_together_and_agreement_is_the_share_every_run_agreed_on():
    ids = ["P1", "P2", "P3", "P4"]
    plans = [_plan(["P1", "P2"], ["P3"], unsorted=["P4"]), _plan(["P1", "P2", "P3"], ["P4"])]
    assert pair_counts(plans, ids) == {("P1", "P2"): 2, ("P1", "P3"): 1, ("P2", "P3"): 1}
    # 6 pairs; P1-P3 and P2-P3 disagree; unsorted pieces share no story with anything
    assert agreement(plans, ids) == (4, 6)


def test_stories_check_runs_tier_1_without_the_cache_and_changes_nothing_stored(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    before = (svc.store.get_brief(rid), svc.store.get_blob(rid, "stories"), svc.store.list_findings(rid))
    flip = itertools.count()

    def answer(system, user):                       # the second run puts every piece in one story
        out = _one_story_per_cl(system, user)
        if next(flip) == 1:
            out["stories"] = [{**out["stories"][0], "pieces": [p for s in out["stories"] for p in s["pieces"]]}]
            for i, p in enumerate(out["stories"][0]["pieces"]):
                p["reason"] = "starts_purpose" if i == 0 else "same_feature"
        return out
    llm = _strong(svc, answer)
    lines = []
    assert stories_check(svc, rid, 2, out=lines.append) == 0
    assert len(llm.prompts) == 2
    assert lines[0].startswith(f"review {rid}: 2 runs of the stories stage by big, ")
    assert lines[-1].startswith("agreement: ") and "piece pairs agreed in every run" in lines[-1]
    assert any(line.endswith(" 1/2") for line in lines) and any(line.endswith(" 2/2") for line in lines)
    assert (svc.store.get_brief(rid), svc.store.get_blob(rid, "stories"), svc.store.list_findings(rid)) == before
    assert svc.ledger is None or svc.ledger.tier1_used(rid) == 0


def test_stories_check_shows_tier_1_the_findings_the_stories_stage_saw(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _one_story_per_cl)                       # every finding reviewed: no hazard, so severities change
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    n = len(llm.prompts)
    stories_check(svc, rid, 1, out=lambda line: None)
    assert llm.prompts[n].split("FINDINGS:", 1)[1] == llm.prompts[0].split("FINDINGS:", 1)[1]


def test_stories_check_needs_a_strong_model(fx, tmp_path, capsys, monkeypatch):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    monkeypatch.setattr("codetortoise.cli._services", lambda config: svc)
    assert main(["stories-check", "--config", "x.yaml", str(rid), "--runs", "2"]) == 1
    assert "no strong model configured (llm.strong)" in capsys.readouterr().err
