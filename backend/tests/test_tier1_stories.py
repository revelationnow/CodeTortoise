"""Tier 1 forms the stories (spec 2026-10-05-two-tier-stories §4)."""
import pytest
from scripted_llm import ScriptedLlm
from test_stories import W, _edit, _in_cls, _world

from codetortoise.board import analyse
from codetortoise.brief import cache_key
from codetortoise.config import LlmBudget, StrongLlmConfig
from codetortoise.llm.client import LlmUnreachable
from codetortoise.llm.ledger import Ledger
from codetortoise.llm.stories import ASK_STYLE, STORY_RULES_VERSION, Tools, ask, chunk_parts, form_stories
from codetortoise.pieces import build_pieces
from codetortoise.store import Store

DESC = {11: "modem: add LTE band 71 support", 12: "modem: band 71 tables for the RF front end", 13: "dsp: faster FFT"}


def _change(cls=None, desc=DESC):
    c = _world([_edit("modem_tx", "modem/tx/a.c"), _edit("modem_rx", "modem/rx/b.c"), _edit("dsp_run", "dsp/run.c")],
               calls=[("modem_tx", "modem_rx")])
    if cls:
        _in_cls(c, cls, desc)
    a = analyse(c)
    t = {f"{W}/modem/tx/a.c": ["modem"], f"{W}/modem/rx/b.c": ["modem"], f"{W}/dsp/run.c": ["dsp"]}
    ps = build_pieces(c, a, t)
    pid = {c.impact.nodes[p.nodes[0]].label: p.id for p in ps.pieces}
    return c, a, ps, pid


def _story(key, title, *pieces, purpose="This adds band 71 to the modem.", related=()):
    return {"key": key, "title": title, "purpose": purpose, "check": ["Check the band tables."],
            "questions": ["Does the DSP need band 71 too?"], "related": list(related),
            "pieces": [{"id": p, "reason": r, "evidence": list(ev), "quote": list(q)} for p, r, ev, q in pieces]}


def _p(pid, reason="same_feature", evidence=(), quote=()):
    return (pid, reason, evidence, quote)


def _per_target(ps):
    """A context too small for the whole change but big enough for its largest target's pieces."""
    largest = max(sum(len(t) for t in chunk_parts([p.id for p in ps.pieces if p.targets == [tg]], ps, []))
                   for tg in ("modem", "dsp"))
    return int((largest + 40) / (4 * 0.6)) + 1


def _form(ps, x, answer, **cfg):
    llm = ScriptedLlm(answer)
    plan = form_stories(llm, None, None, ps, x, StrongLlmConfig(base_url="http://x", model="big", **cfg), [])
    return plan, llm


def test_the_strong_model_forms_the_stories_with_its_titles_and_notes():
    c, a, ps, pid = _change()
    answer = {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71", _p(pid["modem_tx"], "starts_purpose"),
               _p(pid["modem_rx"], evidence=[pid["modem_tx"]]),
               related=["b"]),
        _story("b", "DSP runs a faster FFT", _p(pid["dsp_run"], "starts_purpose"), purpose="The DSP's FFT gets faster.")]}
    plan, llm = _form(ps, a.x, lambda s, u: answer)
    assert [(s.key, s.title, s.pieces, s.related, s.source) for s in plan.stories] == [
        ("a", "Modem radio gains band 71", [pid["modem_tx"], pid["modem_rx"]], ["b"], "tier1"),
        ("b", "DSP runs a faster FFT", [pid["dsp_run"]], [], "tier1")]
    assert plan.stories[0].check == ["Check the band tables."] and plan.notes == []
    prompt = llm.prompts[0]
    assert "1. Split the pieces by target." in prompt and "CHANGE OVERVIEW:" in prompt and ps.pieces[0].card in prompt


def test_each_placement_is_checked_on_its_own_and_failures_go_to_unsorted():
    c, a, ps, pid = _change({"modem/tx/a.c": 11, "modem/rx/b.c": 13, "dsp/run.c": 13})
    tx, rx, dsp = pid["modem_tx"], pid["modem_rx"], pid["dsp_run"]
    answer = {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71 support in every mode today",     # 10 words: over the headline limit
               _p(tx, "starts_purpose"), _p("P99"), _p(tx), _p(dsp, evidence=["CL13"])),
        _story("b", "Receive path", _p(rx, "starts_purpose", evidence=["P42"]))],
              "unsorted": []}
    plan, _ = _form(ps, a.x, lambda s, u: answer)
    (s1, unsorted) = plan.stories
    assert s1.pieces == [tx] and s1.title == ""                  # unknown P99 and the second tx dropped; title fails
    assert unsorted.unsorted and {pl.piece: pl.reason for pl in unsorted.placements} == {
        dsp: "target dsp differs from the story's (modem)", rx: "unknown evidence P42"}


def test_a_piece_from_another_cl_needs_a_link_or_a_quote_from_each_description():
    c, a, ps, pid = _change({"modem/tx/a.c": 11, "modem/rx/b.c": 12, "dsp/run.c": 13})
    tx, rx = pid["modem_tx"], pid["modem_rx"]

    def answer_with(quote, linked):
        ps.links = [lk for lk in ps.links if linked or lk.type != "call"]
        return {"action": "answer", "stories": [_story("a", "Band 71 support", _p(tx, "starts_purpose"),
                                                       _p(rx, "same_feature", quote=quote))]}
    for quote, linked, stands in ((["band 71"], True, True), ([], False, False), (["band 71 everywhere", "tables"], False, False),
                                  (["add LTE band 71", "band 71 tables"], False, True)):
        plan, _ = _form(ps, a.x, lambda s, u, q=quote, k=linked: answer_with(q, k))
        assert (rx in plan.stories[0].pieces) == stands, (quote, linked)


def test_the_model_reads_a_piece_s_code_before_it_answers():
    c, a, ps, pid = _change()

    def answer(system, user):
        if "READ piece_code" not in user:
            return {"action": "read", "tool": "piece_code", "arg": pid["modem_tx"]}
        assert "modem_tx (N1):" in user and "modem_tx_more();" in user
        story = _story("a", "Modem changes", _p(pid["modem_tx"], "starts_purpose"), _p(pid["modem_rx"]))
        return {"action": "answer", "stories": [story],
                "unsorted": [{"id": pid["dsp_run"], "reason": "unclear"}]}
    plan, llm = _form(ps, a.x, answer)
    assert len(llm.prompts) == 2 and plan.stories[-1].placements[0].reason == "unclear"


def test_a_chunk_that_fails_is_grouped_by_the_rules_and_the_plan_says_so():
    c, a, ps, pid = _change()
    plan, _ = _form(ps, a.x, lambda s, u: {"action": "read", "tool": "cl", "arg": "11"}, rounds=2)
    assert {s.source for s in plan.stories} == {"rules"}
    assert plan.notes == ["chunk 1: ValueError: no answer within the rounds allowed; the rules grouped its pieces"]


def test_large_changes_are_chunked_by_target_and_a_merge_pass_joins_them():
    c, a, ps, pid = _change()
    calls = []

    def answer(system, user):
        if "STORIES (key | title" in user:
            calls.append("merge")
            assert "c2a | Modem transmit" in user and "c1a | DSP runs a faster FFT" in user and "targets dsp" in user
            return {"related": [{"a": "c1a", "b": "c2a"}], "merge": [{"a": "c2a", "b": "c2b", "reason": "one feature"},
                                                                      {"a": "c2a", "b": "c1a", "reason": "no"}]}
        calls.append("chunk")
        mine = [p.id for p in ps.pieces if p.card in user]
        if "dsp" in ps.piece(mine[0]).targets:
            return {"action": "answer", "stories": [_story("a", "DSP runs a faster FFT", _p(mine[0], "starts_purpose"))]}
        return {"action": "answer", "stories": [_story("a", "Modem transmit", _p(mine[0], "starts_purpose")),
                                                _story("b", "Modem receive", _p(mine[1], "starts_purpose"))]}
    plan, _ = _form(ps, a.x, answer, context_tokens=_per_target(ps))          # one target to a chunk
    assert calls == ["chunk", "chunk", "merge"]
    assert [(s.key, s.related) for s in plan.stories] == [("c1a", ["c2a"]), ("c2a", ["c1a"])]   # dsp and modem never merge
    assert set(plan.stories[1].pieces) == {pid["modem_tx"], pid["modem_rx"]}


def test_agreement_mode_keeps_what_two_runs_agree_on_and_a_third_run_decides_the_rest():
    c, a, ps, pid = _change()
    tx, rx, dsp = pid["modem_tx"], pid["modem_rx"], pid["dsp_run"]
    runs = iter([[[tx, rx], [dsp]], [[tx], [rx], [dsp]], [[tx, rx], [dsp]]])

    def answer(system, user):
        groups = next(runs)
        return {"action": "answer", "stories": [
            _story(f"s{i}", f"Story {i}", *[_p(p, "starts_purpose" if j == 0 else "same_feature") for j, p in enumerate(g)])
            for i, g in enumerate(groups)]}
    plan, llm = _form(ps, a.x, answer, agree=2)
    assert len(llm.prompts) == 3
    assert sorted(sorted(s.pieces) for s in plan.stories) == sorted([sorted([tx, rx]), [dsp]])


def test_the_tier_1_budget_stops_tier_1_and_the_rules_take_the_rest(tmp_path):
    c, a, ps, pid = _change()
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    ledger = Ledger(store, LlmBudget(tier1_per_review=1))
    llm = ScriptedLlm(lambda s, u: {"action": "answer", "stories": [
        _story("a", "Some story", *[_p(p.id, "starts_purpose") for p in ps.pieces if p.card in u][:1])]})
    plan = form_stories(llm, ledger, rid, ps, a.x, StrongLlmConfig(base_url="http://x", model="big",
                                                                            context_tokens=_per_target(ps)), [])
    assert [s.source for s in plan.stories][:1] == ["tier1"] and "rules" in {s.source for s in plan.stories}
    assert plan.notes[0].startswith("chunk 2: AI budget: this review has used its 1 tier-1 AI calls")


def test_the_cache_key_changes_with_the_cards_the_rules_and_the_model():
    _, _, ps, _ = _change()
    k = cache_key(ps, "big", STORY_RULES_VERSION, 1)
    assert k == cache_key(_change()[2], "big", STORY_RULES_VERSION, 1)
    assert len({k, cache_key(ps, "other", STORY_RULES_VERSION, 1), cache_key(ps, "big", STORY_RULES_VERSION + 1, 1),
                cache_key(ps, "big", STORY_RULES_VERSION, 2)}) == 4
    ps.pieces[0].card += " "
    assert cache_key(ps, "big", STORY_RULES_VERSION, 1) != k


def test_only_a_brief_tier_1_formed_entirely_is_reused(tmp_path):
    from codetortoise.brief import Brief
    store = Store(tmp_path / "s.db")
    half, whole = store.create_review("t", "owner", [1]), store.create_review("t", "owner", [1])
    store.put_brief(half, "k", Brief(key="k", complete=False, overview="half"))
    assert store.find_brief("k") is None                     # a chunk fell back to the rules: the next run asks again
    store.put_brief(whole, "k", Brief(key="k", complete=True, overview="whole"))
    assert store.find_brief("k")["overview"] == "whole"


def test_an_unreachable_strong_model_is_asked_once_and_the_rules_group_the_rest():
    c, a, ps, pid = _change()
    plan, llm = _form(ps, a.x, lambda s, u: LlmUnreachable("LLM request failed after 3 attempts: ReadTimeout"),
                      context_tokens=_per_target(ps))
    assert len(llm.prompts) == 1 and {s.source for s in plan.stories} == {"rules"}
    assert plan.notes == ["chunk 1: LlmUnreachable: LLM request failed after 3 attempts: ReadTimeout; the rules grouped "
                          "its pieces", "chunk 2: the strong model is unreachable; the rules grouped its pieces"]


def test_a_shared_piece_placed_first_leaves_the_story_to_its_single_target_pieces():
    c = _world([_edit("modem_tx", "modem/tx/a.c"), _edit("modem_rx", "modem/rx/b.c"), _edit("dsp_run", "dsp/run.c")],
               calls=[("modem_tx", "modem_rx")])
    a = analyse(c)
    ps = build_pieces(c, a, {f"{W}/modem/tx/a.c": ["dsp", "modem"], f"{W}/modem/rx/b.c": ["modem"],
                             f"{W}/dsp/run.c": ["dsp"]})
    pid = {c.impact.nodes[p.nodes[0]].label: p.id for p in ps.pieces}
    assert ps.piece(pid["modem_tx"]).shared
    answer = {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71", _p(pid["modem_tx"], "shared_code"),
               _p(pid["modem_rx"], "starts_purpose", evidence=[pid["modem_tx"]])),
        _story("b", "DSP runs a faster FFT", _p(pid["dsp_run"], "starts_purpose"), purpose="The DSP's FFT gets faster.")]}
    plan, _ = _form(ps, a.x, lambda s, u: answer)
    assert [(s.key, s.pieces) for s in plan.stories] == [("a", [pid["modem_tx"], pid["modem_rx"]]), ("b", [pid["dsp_run"]])]


def test_two_stories_the_model_gives_one_key_keep_their_own_keys():
    c, a, ps, pid = _change()
    answer = {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71", _p(pid["modem_tx"], "starts_purpose"),
               _p(pid["modem_rx"], evidence=[pid["modem_tx"]])),
        _story("a", "DSP runs a faster FFT", _p(pid["dsp_run"], "starts_purpose"), purpose="The DSP's FFT gets faster.",
               related=["a"])]}
    plan, _ = _form(ps, a.x, lambda s, u: answer)
    assert [(s.key, s.related) for s in plan.stories] == [("a", []), ("a_2", ["a"])]


def test_cl_evidence_is_read_however_the_model_writes_it():
    c, a, ps, pid = _change({"modem/tx/a.c": 11, "modem/rx/b.c": 12, "dsp/run.c": 13})
    tx, rx = pid["modem_tx"], pid["modem_rx"]
    answer = {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71", _p(tx, "starts_purpose"), _p(rx, evidence=[tx, "CL 12", "cl11"]))]}
    plan, _ = _form(ps, a.x, lambda s, u: answer)
    assert plan.stories[0].pieces == [tx, rx] and plan.stories[0].placements[1].evidence == [tx, "CL12", "CL11"]


def test_reading_a_cl_without_a_user_leaves_the_user_out():
    c, a, ps, pid = _change({"modem/tx/a.c": 11, "modem/rx/b.c": 11, "dsp/run.c": 13})
    assert Tools(a.x, ps).cl("11").startswith("CL 11 (pending):\nmodem: add LTE band 71 support")


def test_reads_are_kept_only_while_the_system_prompt_and_schema_still_fit():
    c, a, ps, pid = _change({"modem/tx/a.c": 11, "modem/rx/b.c": 11, "dsp/run.c": 13})
    parts, tools = chunk_parts([p.id for p in ps.pieces], ps, []), Tools(a.x, ps)
    read = "READ cl 11 ->\n" + tools.run("cl", "11")
    answer = {"action": "answer", "stories": [_story("a", "Modem radio gains band 71", _p(pid["modem_tx"], "starts_purpose"))]}
    steps = iter([{"action": "read", "tool": "cl", "arg": "11"}, answer])
    llm = ScriptedLlm(lambda s, u: next(steps))
    ask(llm, parts, tools, 2, len("\n\n".join(parts)) + len(read) + 2 + len(ASK_STYLE) + 200)  # fits only without SYSTEM
    assert "READ cl 11" not in llm.prompts[1]


def test_a_failed_merge_pass_leaves_the_plan_complete_and_a_failed_chunk_does_not():
    c, a, ps, pid = _change()

    def answer(system, user):
        if "STORIES (key | title" in user:
            return RuntimeError("the merge timed out")
        mine = [p.id for p in ps.pieces if p.card in user]
        return {"action": "answer", "stories": [_story(f"s{i}", "Modem transmit", _p(m, "starts_purpose"))
                                                for i, m in enumerate(mine)]}
    plan, _ = _form(ps, a.x, answer, context_tokens=_per_target(ps))
    assert plan.complete and plan.notes == ["merge pass: RuntimeError: the merge timed out"]
    plan, _ = _form(ps, a.x, lambda s, u: {"action": "read", "tool": "cl", "arg": "11"}, rounds=2)
    assert not plan.complete


def test_agreement_mode_keeps_the_first_run_when_the_budget_stops_the_second(tmp_path):
    c, a, ps, pid = _change()
    store = Store(tmp_path / "s.db")
    rid = store.create_review("t", "owner", [1])
    llm = ScriptedLlm(lambda s, u: {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71", _p(pid["modem_tx"], "starts_purpose"), _p(pid["modem_rx"])),
        _story("b", "DSP runs a faster FFT", _p(pid["dsp_run"], "starts_purpose"), purpose="The DSP's FFT gets faster.")]})
    plan = form_stories(llm, Ledger(store, LlmBudget(tier1_per_review=1)), rid, ps, a.x,
                        StrongLlmConfig(base_url="http://x", model="big", agree=2), [])
    assert [(s.key, s.source) for s in plan.stories] == [("a", "tier1"), ("b", "tier1")] and not plan.complete
    assert plan.notes == ["chunk 1: AI budget: this review has used its 1 tier-1 AI calls; its first run's answer stands"]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr("httpx.Client.post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
