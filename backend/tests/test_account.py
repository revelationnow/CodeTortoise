from test_storyboard import _board, fake_llm, model

from codetortoise.grouping import Placement
from codetortoise.llm.account import account_job, write_accounts
from codetortoise.llm.storyboard import AiContext, run_job
from codetortoise.reading import CallPath, StoryReading
from codetortoise.stories import Story, StoryDetail

P = "This story makes uart_send return -2 on a full buffer. You see it in every caller."


def _detail(sid="S1", **kw):
    st = Story(id=sid, kind=kw.pop("kind", "behaviour"), title="uart_send reports errors", summary="uart_send can return -2.",
               nodes=["N2"], flows=["FL1", "FL2"], findings=["F1"], **kw)
    d = StoryDetail(story=st, board=_board(2))
    d.board.flows[1].text = "main → uart_send"
    return d


def _ctx():
    im, findings, _ = model()
    return AiContext(im, findings, {"N2": "int uart_send(void) { return -2; }"})


def _sections(*extra):
    return {"sections": [
        {"kind": "effects", "cites": ["F1"], "text": "Callers that ignore the result now drop an error. Check the ones you own."},
        {"kind": "flow", "flow": "FL2", "cites": ["N2"], "text": "main reaches uart_send directly. It now gets -2 back."},
        {"kind": "purpose", "cites": ["N2"], "text": P},
        {"kind": "flow", "flow": "FL1", "cites": ["N3"],
         "text": "logger_flush calls uart_send on each flush. It drops the new -2."},
        *extra]}


def test_an_account_keeps_purpose_flows_in_story_order_and_effects():
    d, sr = _detail(), StoryReading(story="S1")
    assert run_job(fake_llm(lambda s, u: _sections()), account_job(_ctx(), d, sr)) == 0
    assert [(p.kind, p.heading) for p in sr.account] == [
        ("purpose", "What it is for"), ("flow", "logger_flush → uart_send ⟶ -2 ignored"), ("flow", "main → uart_send"),
        ("effects", "What it means for the rest")]
    assert sr.account[0].text == P and sr.account[0].cites == ["N2"]


def test_sections_that_cite_nothing_of_the_story_name_another_flow_or_repeat_a_kind_are_dropped():
    d, sr = _detail(), StoryReading(story="S1")
    out = _sections({"kind": "purpose", "cites": ["N2"], "text": "A second purpose. It repeats the first."},
                    {"kind": "flow", "flow": "FL9", "cites": ["N2"], "text": "Another story's flow. It isn't this one's."},
                    {"kind": "flow", "flow": "FL1", "cites": ["N3"], "text": "A second section for this flow. It comes too late."},
                    {"kind": "summary", "cites": ["N2"], "text": "A kind the account doesn't have."})
    out["sections"][0]["cites"] = ["N99"]          # the effects section cites nothing of the story
    run_job(fake_llm(lambda s, u: out), account_job(_ctx(), d, sr))
    assert [p.kind for p in sr.account] == ["purpose", "flow", "flow"]
    assert sr.account[0].text == P and "too late" not in sr.account[1].text


def test_with_no_section_left_there_is_no_account_and_style_breaks_are_counted():
    d, sr = _detail(), StoryReading(story="S1")
    bad = {"sections": [{"kind": "purpose", "cites": ["N2"], "text": "Simply put, it changes uart_send."},
                        {"kind": "effects", "cites": ["N99"], "text": "Callers see -2."}]}
    assert run_job(fake_llm(lambda s, u: bad), account_job(_ctx(), d, sr)) == 1
    assert sr.account == [] and sr.account_files is None


def test_the_prompt_holds_what_the_strong_model_said_the_flows_paths_and_findings():
    d = _detail(source="tier1", purpose="Report transmit errors to the logger.", check=["Check logger_flush handles -2."],
                questions=["Should uart_errors reset on init?"],
                placements=[Placement(piece="P1", reason="It adds the -2 that logger_flush now sees.")])
    sr = StoryReading(story="S1", paths=[CallPath(steps=["N3", "N2"], labels=["logger_flush", "uart_send"], kind="contract",
                                                  text="logger_flush calls uart_send")])
    prompt = account_job(_ctx(), d, sr).prompt
    assert prompt.startswith("Write a reviewer's account of this change story")
    for want in ["Report transmit errors to the logger.", "It adds the -2 that logger_flush now sees.",
                 "Check logger_flush handles -2.", "Should uart_errors reset on init?",
                 "FLOW FL1 | logger_flush → uart_send ⟶ -2 ignored | template what", "logger_flush calls uart_send",
                 "F1 [medium] contract", "int uart_send(void)", "CITE FROM: N2, N3, F1"]:
        assert want in prompt
    rules = account_job(_ctx(), _detail(purpose="Not from tier 1."), StoryReading(story="S1")).prompt
    assert "WHAT THE GROUPING MODEL SAID" not in rules


def test_a_shared_sink_finding_stays_out_of_the_prompt():
    ctx = _ctx()
    ctx.findings[0].sink = True
    assert "F1 [medium]" not in account_job(ctx, _detail(), StoryReading(story="S1")).prompt


def test_the_account_records_the_files_behind_its_prompt():
    ctx = _ctx()
    ctx.node_files = {"N2": ["//w/d/uart.c"], "N3": ["//w/svc/logger.c"]}
    ctx.findings[0].files = ["//w/d/uart.c"]
    sr = StoryReading(story="S1")
    run_job(fake_llm(lambda s, u: _sections()), account_job(ctx, _detail(), sr))
    assert sr.account_files == ["//w/d/uart.c", "//w/svc/logger.c"]


def test_write_accounts_skips_mechanical_and_collapsed_stories_and_reuses_an_unchanged_prompts_account():
    ctx, asked = _ctx(), []

    def respond(s, u):
        asked.append(u)
        return _sections()
    details = {"S1": _detail("S1"), "S2": _detail("S2", collapsed=True), "S3": _detail("S3", kind="mechanical")}
    per = {s: StoryReading(story=s) for s in details}
    cache, dropped, notes = write_accounts(fake_llm(respond), ctx, details, per, {})
    assert (len(asked), set(cache), dropped, notes) == (1, {"S1"}, 0, [])
    assert per["S1"].account and not per["S2"].account and not per["S3"].account
    again = {s: StoryReading(story=s) for s in details}
    assert write_accounts(fake_llm(respond), ctx, details, again, cache)[0] == cache
    assert len(asked) == 1 and [p.text for p in again["S1"].account] == [p.text for p in per["S1"].account]
    write_accounts(fake_llm(respond), ctx, details, {s: StoryReading(story=s) for s in details}, cache, fresh=True)
    assert len(asked) == 2


def test_a_different_weak_model_asks_again():
    ctx, asked = _ctx(), []

    def respond(s, u):
        asked.append(u)
        return _sections()
    details = {"S1": _detail("S1")}
    cache = write_accounts(fake_llm(respond), ctx, details, {"S1": StoryReading(story="S1")}, {})[0]
    other = fake_llm(respond)
    other.model = "another-model"
    write_accounts(other, ctx, details, {"S1": StoryReading(story="S1")}, cache)
    assert len(asked) == 2


def test_a_failed_call_leaves_that_story_without_an_account_and_says_why():
    details = {"S1": _detail("S1")}
    per = {"S1": StoryReading(story="S1")}
    cache, _, notes = write_accounts(fake_llm(lambda s, u: {"sections": "not a list"}), _ctx(), details, per, {})
    assert cache == {} and per["S1"].account == []
    assert len(notes) == 1 and notes[0].startswith("1 story account(s) not written: ")


def test_a_rerun_that_only_rewrote_ai_text_reuses_the_account():
    ctx, asked = _ctx(), []

    def respond(s, u):
        asked.append(u)
        return _sections()
    details = {"S1": _detail("S1")}
    cache = write_accounts(fake_llm(respond), ctx, details, {"S1": StoryReading(story="S1")}, {})[0]
    st = details["S1"].story             # the up-front pass retold the story; the verdicts moved a finding's severity
    st.title, st.summary, st.text_source = "uart_send reports -2", "uart_send can now fail.", "llm"
    ctx.findings[0].severity = "high"
    details["S1"].board.flows[0].what = "logger_flush now hands the uart error back."
    again = {"S1": StoryReading(story="S1")}
    write_accounts(fake_llm(respond), ctx, details, again, cache)
    assert len(asked) == 1 and again["S1"].account
    ctx.snippets["N2"] = "int uart_send(void) { return -3; }"     # the code changed: ask again
    write_accounts(fake_llm(respond), ctx, details, {"S1": StoryReading(story="S1")}, cache)
    assert len(asked) == 2
