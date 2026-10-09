"""Tier 1 reviews each story's risks (spec 2026-10-05-two-tier-stories §5)."""
import pytest
from scripted_llm import ScriptedLlm
from test_stories import W, _edit, _same, _world

from codetortoise.board import analyse
from codetortoise.config import LlmBudget, StrongLlmConfig
from codetortoise.detectors.base import Finding
from codetortoise.facts_prep import finding_key, prepare_facts
from codetortoise.grouping import Placement, PlannedStory, StoryPlan
from codetortoise.llm.client import LlmError, LlmUnreachable
from codetortoise.llm.ledger import Ledger
from codetortoise.llm.review import apply_verdicts, review_stories
from codetortoise.pieces import build_pieces
from codetortoise.store import Store

CFG = StrongLlmConfig(base_url="http://x", model="big")


def _change():
    """hal_write's signature changed; uart_send was updated, old_user was not; dsp_run is another story."""
    c = _world([_edit("hal_write", "hal/regs.c"), _edit("uart_send", "drv/uart.c"), _same("old_user", "drv/old.c"),
                _edit("dsp_run", "dsp/run.c")],
               calls=[("uart_send", "hal_write"), ("old_user", "hal_write")])
    a = analyse(c)
    t = {f"{W}/hal/regs.c": ["fw"], f"{W}/drv/uart.c": ["fw"], f"{W}/drv/old.c": ["fw"], f"{W}/dsp/run.c": ["dsp"]}
    ps = build_pieces(c, a, t)
    sig = Finding(id="F1", kind="contract", severity="medium", title="hal_write: signature changed", summary="s",
                  nodes=["N1"])
    dsp = Finding(id="F2", kind="other_kind", severity="low", title="dsp_run: something", summary="s", nodes=["N4"])
    pid = {c.impact.nodes[p.nodes[0]].label: p.id for p in ps.pieces}
    hal = [pid["hal_write"]] + [pid["uart_send"]] * (pid["uart_send"] != pid["hal_write"])
    plan = StoryPlan(stories=[
        PlannedStory(key="a", title="HAL writes take a width", purpose="This widens the HAL write.", source="tier1",
                     placements=[Placement(piece=p, reason="same_feature") for p in hal]),
        PlannedStory(key="b", title="DSP runs faster", source="tier1",
                     placements=[Placement(piece=pid["dsp_run"], reason="starts_purpose")])])
    findings = [sig, dsp]
    facts = prepare_facts(a.x, findings, t)
    return a, ps, plan, findings, facts


def _verdicts(*vs):
    return {"action": "answer", "verdicts": [{"finding": f, "verdict": v, "reason": r, "cites": list(c)} for f, v, r, c in vs]}


def _review(answer, ledger=None, rid=None, skip=()):
    a, ps, plan, findings, facts = _change()
    llm = ScriptedLlm(answer)
    out = review_stories(llm, ledger, rid, plan, ps, a.x, CFG, findings, facts, skip=set(skip))
    return out, findings, llm


def test_each_story_gets_one_call_with_its_findings_facts_and_fixed_question():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "hazard", "old_user still calls hal_write the old way.", ["drv/old.c:3", "N3"]))
        return _verdicts(("F2", "no_hazard", "Nothing outside the DSP uses the result.", ["N4"]))
    out, findings, llm = _review(answer)
    assert len(llm.prompts) == 2 and out.reviewed == ["a", "b"] and out.notes == []
    first = llm.prompts[0]
    assert "STORY a: HAL writes take a width" in first and "drv/old.c:3 in old_user (N3): not updated" in first
    assert "QUESTION: Do the updated sites match the new signature; is any site left behind?" in first
    assert "F2" not in first                                     # each story sees only its own findings
    v = out.verdicts[finding_key(findings[0])]
    assert (v.verdict, v.cites) == ("hazard", ["drv/old.c:3", "N3"])
    apply_verdicts(findings, out.verdicts)
    by_title = {f.title: f for f in findings}
    sig, dsp = by_title["hal_write: signature changed"], by_title["dsp_run: something"]
    assert (sig.severity, sig.verdict, sig.verdict_source, sig.verdict_cites) == ("high", "hazard", "tier1", ["drv/old.c:3", "N3"])
    assert (dsp.severity, dsp.verdict) == ("info", "no_hazard")
    assert [f.id for f in findings] == ["F1", "F2"]              # renumbered by severity


def test_needs_review_is_medium_and_a_verdict_citing_nothing_shown_is_rejected():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "needs_review", "Callers should confirm the new width.", ["N1"]),
                             ("F2", "hazard", "Not this story's finding.", ["N1"]))
        return _verdicts(("F2", "hazard", "The DSP breaks.", ["N99", "dsp/run.c:400"]))
    out, findings, _ = _review(answer)
    assert {k: v.verdict for k, v in out.verdicts.items()} == {"contract|hal_write: signature changed": "needs_review"}
    assert out.notes == ["story b: F2's verdict cites nothing it was shown; the finding stays as the detectors left it"]
    apply_verdicts(findings, out.verdicts)
    dsp = next(f for f in findings if f.kind == "other_kind")
    assert (dsp.severity, dsp.verdict, dsp.verdict_source) == ("low", None, None)
    assert next(f for f in findings if f.kind == "contract").severity == "medium"


def test_a_verdict_citing_only_a_bare_number_is_rejected():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "hazard", "old_user still calls hal_write the old way.", ["3"]))
        return _verdicts(("F2", "no_hazard", "Nothing outside the DSP uses the result.", ["N4"]))
    out, _, llm = _review(answer)
    assert "3" in llm.prompts[0] and list(out.verdicts) == ["other_kind|dsp_run: something"]
    assert out.notes == ["story a: F1's verdict cites nothing it was shown; the finding stays as the detectors left it"]


def test_a_verdict_dropped_for_the_house_style_says_so():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "hazard", "This is just an easy fix.", ["N1"]))
        return _verdicts(("F2", "no_hazard", "Nothing outside the DSP uses the result.", ["N4"]))
    out, _, _ = _review(answer)
    assert list(out.verdicts) == ["other_kind|dsp_run: something"]
    assert out.notes == ["story a: F1's verdict broke the house style; the finding stays as the detectors left it"]


def test_a_line_inside_code_the_model_read_counts_as_shown():
    a, ps, plan, findings, facts = _change()
    hal = next(p.id for p in ps.pieces if p.nodes == ["N1"])

    def answer(system, user):
        if "F1" not in user:
            return _verdicts()
        if "READ piece_code" not in user:
            return {"action": "read", "tool": "piece_code", "arg": hal}
        return _verdicts(("F1", "no_hazard", "Every caller was updated in this change.", ["hal/regs.c:4", "hal/regs.c:40"]))
    out = review_stories(ScriptedLlm(answer), None, None, plan, ps, a.x, CFG, findings, facts)
    assert out.verdicts["contract|hal_write: signature changed"].cites == ["hal/regs.c:4"]     # line 40 was never shown


def test_a_story_without_findings_costs_no_call_and_reviewed_stories_are_skipped():
    out, _, llm = _review(lambda s, u: _verdicts(("F1", "hazard", "old_user is left behind.", ["N3"])), skip=["b"])
    assert len(llm.prompts) == 1 and out.reviewed == ["a", "b"]


def test_the_tier_1_budget_stops_the_review_and_the_rest_stay_as_the_detectors_left_them(tmp_path):
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    ledger = Ledger(store, LlmBudget(tier1_per_review=1))
    out, _, llm = _review(lambda s, u: _verdicts(("F1", "hazard", "old_user is left behind.", ["N3"]),
                                                 ("F2", "hazard", "The DSP breaks.", ["N4"])), ledger, rid)
    assert len(llm.prompts) == 1 and out.reviewed == ["a"]
    assert out.notes == ["story b: AI budget: this review has used its 1 tier-1 AI calls; its findings stay as the "
                         "detectors left them"]


def test_a_finding_on_two_stories_is_reviewed_with_the_first():
    a, ps, plan, findings, facts = _change()
    plan.stories[1].placements.append(Placement(piece=plan.stories[0].placements[0].piece, reason="shared_code"))
    llm = ScriptedLlm(lambda s, u: _verdicts())
    review_stories(llm, None, None, plan, ps, a.x, CFG, findings, facts)
    assert ["F1" in p for p in llm.prompts] == [True, False]


def test_verdicts_follow_their_finding_when_a_re_run_numbers_the_findings_differently():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "hazard", "old_user still calls hal_write the old way.", ["N3"]))
        return _verdicts(("F2", "no_hazard", "Nothing outside the DSP uses the result.", ["N4"]))
    out, findings, _ = _review(answer)
    rerun = [Finding(id="F1", kind="header_fanout", severity="high", title="new.h: 1 change(s) reach 2 TU(s)", summary="s")]
    rerun += [f.model_copy(update={"id": f"F{i + 2}"}) for i, f in enumerate(reversed(findings))]
    apply_verdicts(rerun, out.verdicts)
    assert [(f.id, f.title, f.verdict) for f in rerun] == [
        ("F1", "hal_write: signature changed", "hazard"), ("F2", "new.h: 1 change(s) reach 2 TU(s)", None),
        ("F3", "dsp_run: something", "no_hazard")]


def test_a_strong_model_that_fails_leaves_every_finding_as_the_detectors_left_it(fx, tmp_path):
    from helpers import make_services
    from test_pipeline import _strong

    from codetortoise.pipeline import run_review
    svc = make_services(fx, tmp_path)
    _strong(svc, lambda s, u: RuntimeError("the endpoint is down"))
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert st["review"]["status"] == "degraded" and "RuntimeError: the endpoint is down" in st["review"]["message"]
    assert st["review"]["message"].startswith("0 finding(s) judged by big")
    assert all(f.verdict_source is None and f.verdict is None for f in svc.store.list_findings(rid))
    assert svc.store.get_review(rid)["status"] == "degraded"       # the review still finishes, on the rules' stories


def test_call_sites_in_files_without_a_piece_are_marked_by_their_own_targets():
    a, ps, plan, findings, facts = _change()
    assert f"{W}/drv/old.c" not in ps.targets                     # old_user is unchanged: no piece holds its file
    facts = prepare_facts(a.x, findings, ps.targets, resolve=lambda files: {f: ["fw"] for f in files})
    old = next(r for r in facts[finding_key(findings[0])].splitlines() if "old_user" in r)
    assert "not updated" in old and "not in any compile database" not in old


def test_an_unreachable_strong_model_is_asked_once_and_the_rest_stay_as_the_detectors_left_them():
    out, findings, llm = _review(lambda s, u: LlmUnreachable("LLM request failed after 3 attempts: ReadTimeout"))
    assert len(llm.prompts) == 1 and out.verdicts == {} and out.reviewed == []
    assert out.notes == ["story a: big: unreachable; its findings stay as the detectors left them",
                         "story b: the strong model is unreachable; its findings stay as the detectors left them"]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr("httpx.Client.post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))


def test_a_story_the_strong_model_fails_is_judged_by_the_weak_model_but_not_marked_reviewed():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "hazard", "old_user still calls hal_write the old way.", ["drv/old.c:3", "N3"]))
        return _verdicts(("F2", "no_hazard", "Nothing outside the DSP uses the result.", ["N4"]))
    a, ps, plan, findings, facts = _change()
    strong = ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x"))
    weak = ScriptedLlm(answer, model="small")
    out = review_stories(strong, None, None, plan, ps, a.x, CFG, findings, facts, weak=weak)
    assert len(out.verdicts) == 2 and out.reviewed == []          # the next run asks the strong model again
    assert out.notes == ["story a: big: invalid JSON twice; fresh try: invalid JSON twice; small judged its findings",
                         "story b: big: invalid JSON twice; fresh try: invalid JSON twice; small judged its findings"]


def test_a_story_every_model_fails_keeps_the_detectors_verdicts():
    a, ps, plan, findings, facts = _change()
    fail = ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x"))
    out = review_stories(fail, None, None, plan, ps, a.x, CFG, findings, facts,
                         weak=ScriptedLlm(lambda s, u: RuntimeError("down"), model="small"))
    assert out.verdicts == {} and out.notes[0] == ("story a: big: invalid JSON twice; fresh try: invalid JSON twice; "
                                                   "small: RuntimeError: down; its findings stay as the detectors left them")
