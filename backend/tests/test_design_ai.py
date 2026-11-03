"""The design overview's AI menu (spec 2026-11-02 §10, §11): rewrite one part, with an instruction, and pin it."""
import pytest
from helpers import make_app, make_services
from test_pipeline import _one_story_per_cl, _strong
from test_web import InlineRunner, login

from codetortoise.llm import ondemand

AGAIN = "The change holds together once more. Settle whether its callers handle the new results."
SHORT = "One new result goes unchecked. Settle whether its callers handle it."


def _answer(system, user):
    """The scripted strong model; a rewrite of the verdict says it again, shorter when the instruction asks for that."""
    out = _one_story_per_cl(system, user)
    if "REWRITE: write the verdict again" in user:
        asked = user.split("THE REVIEWER'S INSTRUCTION", 1)[1] if "THE REVIEWER'S INSTRUCTION" in user else ""
        out = {**out, "verdict": SHORT if "shorter" in asked.lower() else AGAIN}
    return out


@pytest.fixture
def made(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _answer)
    app = make_app(svc, InlineRunner(svc))
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    return svc, app, owner, rid, llm


def _design(c, rid):
    return c.get(f"/api/reviews/{rid}/reading").json()["design"]


def _job(c, rid):
    return c.get(f"/api/reviews/{rid}/ai").json()["jobs"][-1]


def test_anyone_in_the_review_rewrites_a_part_for_everyone_and_it_costs_them_one_call(made):
    _, app, owner, rid, _ = made
    bob = login(app, "bob")
    r = bob.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 202 and (r.json()["kind"], r.json()["target"]) == ("design", "verdict")
    assert (_design(owner, rid)["verdict"], _design(owner, rid)["sources"]["verdict"]) == (AGAIN, "llm")
    u = bob.get(f"/api/reviews/{rid}/ai").json()
    assert u["jobs"][-1]["status"] == "done" and u["by_person"].get("bob") == 1 and u["me_today"] == 1
    assert u["by_purpose"].get("rewrite") == 1


def test_a_rewrite_with_an_instruction_puts_the_reader_s_words_in_the_prompt(made):
    _, _, owner, rid, llm = made
    r = owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "  Make it shorter "})
    assert r.status_code == 202 and _design(owner, rid)["verdict"] == SHORT
    assert llm.prompts[-1].endswith("THE REVIEWER'S INSTRUCTION (follow it within the rules above): Make it shorter")
    walk = _design(owner, rid)["walks"][0]["id"]
    assert owner.post(f"/api/reviews/{rid}/design/walk:{walk}/rewrite", json={}).status_code == 202
    assert f"REWRITE: write walk-through {walk}'s title and lead again" in llm.prompts[-1]
    assert owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "x" * 301}).status_code == 422


def test_only_the_owner_pins_and_a_pinned_part_is_not_rewritten_until_it_is_unpinned(made):
    _, app, owner, rid, _ = made
    bob = login(app, "bob")
    assert bob.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True}).status_code == 403
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True}).json() == {"pinned": True}
    assert _design(bob, rid)["sources"]["verdict"] == "pinned"
    r = bob.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 409 and r.json()["detail"] == "this part is pinned: its owner unpins it to rewrite it"
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": False}).json() == {"pinned": False}
    assert _design(bob, rid)["sources"]["verdict"] == "llm"
    assert bob.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={}).status_code == 202


def test_a_part_the_design_lacks_is_not_found_and_words_not_the_model_s_are_not_pinned(made):
    svc, _, owner, rid, _ = made
    assert owner.post(f"/api/reviews/{rid}/design/walk:W99/rewrite", json={}).status_code == 404
    assert owner.post(f"/api/reviews/{rid}/design/nodes/pin", json={"pinned": True}).status_code == 404
    d = svc.store.get_blob(rid, "reading_design")
    d["sources"].pop("verdict")                                     # as when the model's verdict failed its checks
    svc.store.put_blob(rid, "reading_design", d)
    r = owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True})
    assert r.status_code == 409 and r.json()["detail"] == "only the AI's words are pinned; this part has none"


def test_a_rewrite_needs_a_finished_review_its_design_stage_at_rest_and_the_strong_model(made):
    svc, _, owner, rid, _ = made
    svc.store.set_stage(rid, "design", "pending", "queued: the design context changed")
    r = owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 409 and r.json()["detail"] == "the design stage is running; try again when it finishes"
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True}).status_code == 409
    svc.store.set_stage(rid, "design", "ok", "")
    svc.store.set_review_status(rid, "running")
    r = owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 409 and r.json()["detail"] == "the review is being re-run"
    svc.store.set_review_status(rid, "done")
    svc.strong = None
    r = owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert r.status_code == 409 and r.json()["detail"] == "no strong model is configured"


def test_an_answer_that_fails_or_no_model_changes_nothing_and_says_why(made):
    _, _, owner, rid, llm = made
    before = _design(owner, rid)
    llm.answer = lambda s, u: {**_answer(s, u), "verdict": "Too short."} if "REWRITE:" in u else _answer(s, u)
    owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert (_job(owner, rid)["status"], _job(owner, rid)["error"]) == ("failed", ondemand.UNCHECKED)
    llm.answer = lambda s, u: RuntimeError("down")
    owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={})
    assert _job(owner, rid)["error"] == "the AI did not answer: big: RuntimeError: down; nothing was changed. Try again"
    assert _design(owner, rid) == before


def test_a_rewrite_for_a_design_that_changed_meanwhile_is_dropped(made, monkeypatch):
    svc, _, owner, rid, _ = made
    before = _design(owner, rid)
    real = ondemand.rewrite_part

    def meanwhile(*args, **kwargs):
        out = real(*args, **kwargs)
        r = svc.store.get_blob(rid, "reading")
        svc.store.put_blob(rid, "reading", {**r, "whole": "The change was read again."})   # its prompt changes
        return out
    monkeypatch.setattr(ondemand, "rewrite_part", meanwhile)
    assert owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={}).status_code == 202
    assert (_job(owner, rid)["status"], _job(owner, rid)["error"]) == ("failed", ondemand.CHANGED)
    assert _design(owner, rid)["verdict"] == before["verdict"]


def test_a_rewrite_outlives_a_re_run_of_the_same_change_and_a_pin_outlives_a_new_context(made):
    from codetortoise.pipeline import run_review
    svc, _, owner, rid, llm = made
    owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "shorter"})
    asked = sum("CHECKS BY CAUSE (id" in p for p in llm.prompts)
    run_review(rid, svc)                                            # the same prompt: the kept text, with the rewrite
    assert sum("CHECKS BY CAUSE (id" in p for p in llm.prompts) == asked
    assert _design(owner, rid)["verdict"] == SHORT
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True}).status_code == 200
    assert owner.put(f"/api/reviews/{rid}/design-context", json={"notes": "Never drop a byte."}).status_code == 202
    d = _design(owner, rid)                                         # the design stage ran again, on a new prompt
    assert sum("CHECKS BY CAUSE (id" in p for p in llm.prompts) == asked + 1
    assert (d["verdict"], d["sources"]["verdict"]) == (SHORT, "pinned") and d["context_hash"]


def test_a_rewrite_says_who_asked_and_how_for_everyone_through_a_re_run_and_a_pin(made):
    """Final review I2: the design says who had a part rewritten and their instruction; a re-run of the same prompt and a
    pin keep that with the words, and the model's fresh words on a new prompt carry none."""
    from codetortoise.pipeline import run_review
    svc, app, owner, rid, _ = made
    bob = login(app, "bob")
    assert _design(owner, rid)["rewrites"] == {}
    bob.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "  Make it shorter "})
    steered = {"verdict": {"by": "bob", "instruction": "Make it shorter"}}
    assert _design(owner, rid)["rewrites"] == steered
    walk = _design(owner, rid)["walks"][0]["id"]
    owner.post(f"/api/reviews/{rid}/design/walk:{walk}/rewrite", json={})
    assert _job(owner, rid)["status"] == "done"
    run_review(rid, svc)                                            # the same prompt: the kept text, with its records
    assert _design(owner, rid)["rewrites"] == {**steered, f"walk:{walk}": {"by": "owner", "instruction": ""}}
    owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True})
    owner.put(f"/api/reviews/{rid}/design-context", json={"notes": "Never drop a byte."})
    d = _design(owner, rid)                                         # a new prompt: the walk-through's words are fresh
    assert (d["sources"]["verdict"], d["rewrites"]) == ("pinned", steered)


def test_the_kept_answer_stays_the_model_s_and_what_readers_chose_lands_on_it(made):
    """Phase 4 M3/M4: a rewrite is kept apart from the model's answer, under the prompt it was asked for."""
    from codetortoise.pipeline import run_review
    svc, _, owner, rid, _ = made
    said = _design(owner, rid)["verdict"]
    owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "shorter"})
    kept, chosen = svc.store.get_blob(rid, "design_text"), svc.store.get_blob(rid, "design_chosen")
    assert kept["verdict"] == said != SHORT and chosen["key"] == kept["key"] and list(chosen["parts"]) == ["verdict"]
    assert (chosen["parts"]["verdict"]["words"][0], chosen["parts"]["verdict"]["rewrite"]) == (
        SHORT, {"by": "owner", "instruction": "shorter"})
    run_review(rid, svc)                                            # the same prompt: the model's answer, then the choice
    d = _design(owner, rid)
    assert (d["verdict"], d["sources"]["verdict"], d["rewrites"]) == (
        SHORT, "llm", {"verdict": {"by": "owner", "instruction": "shorter"}})
    assert svc.store.get_blob(rid, "design_text")["verdict"] == said


def test_an_unpin_then_a_re_run_of_the_same_prompt_keeps_the_words_showing(made):
    """Phase 4 M3: the model's words a pin covered don't come back when it goes."""
    from codetortoise.pipeline import run_review
    svc, _, owner, rid, _ = made
    owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "shorter"})
    owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True})
    owner.put(f"/api/reviews/{rid}/design-context", json={"notes": "Never drop a byte."})   # the model's own words, kept
    assert _design(owner, rid)["verdict"] == SHORT
    assert owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": False}).status_code == 200
    run_review(rid, svc)                                            # the same prompt again
    d = _design(owner, rid)
    assert (d["verdict"], d["sources"]["verdict"], d["rewrites"]["verdict"]["by"]) == (SHORT, "llm", "owner")


def test_a_rewrite_on_a_degraded_design_outlives_a_re_run_that_asks_again(fx, tmp_path):
    """Phase 4 M4: with no answer kept (a part failed), a re-run asks again, and the rewrite still lands."""
    from codetortoise.pipeline import run_review

    def answer(system, user):
        out = _answer(system, user)
        return out if "REWRITE:" in user else {**out, "walks": []}     # every walk-through title fails: nothing kept
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, answer)
    owner = login(make_app(svc, InlineRunner(svc)), "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    assert svc.store.get_blob(rid, "design_text") is None
    assert owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={"instruction": "shorter"}).status_code == 202
    assert _design(owner, rid)["verdict"] == SHORT
    asked = sum("CHECKS BY CAUSE (id" in p for p in llm.prompts)
    run_review(rid, svc)
    assert sum("CHECKS BY CAUSE (id" in p for p in llm.prompts) == asked + 1      # nothing kept: asked again
    assert _design(owner, rid)["verdict"] == SHORT


def test_a_rewrite_asks_the_strong_model_once(fx, tmp_path):
    """Phase 4 M1: the menu says one AI call, so a failing rewrite is not tried fresh, nor on the weak model."""
    from scripted_llm import ScriptedLlm

    def answer(system, user):
        return RuntimeError("down") if "REWRITE:" in user else _answer(system, user)
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, answer)
    owner = login(make_app(svc, InlineRunner(svc)), "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    svc.llm = weak = ScriptedLlm(_answer, "small")
    assert owner.post(f"/api/reviews/{rid}/design/verdict/rewrite", json={}).status_code == 202
    assert sum("REWRITE:" in p for p in llm.prompts) == 1 and weak.prompts == []
    assert _job(owner, rid)["status"] == "failed" and "big: RuntimeError: down" in _job(owner, rid)["error"]


def test_a_part_pinned_while_its_rewrite_waits_costs_no_call(made):
    """Phase 4 M2: a job that starts after its part was pinned asks nothing."""
    svc, _, owner, rid, llm = made
    owner.post(f"/api/reviews/{rid}/design/verdict/pin", json={"pinned": True})   # while the job waited in the queue
    asked = len(llm.prompts)
    with pytest.raises(ondemand.Changed, match="pinned"):
        ondemand.rewrite_design(svc, rid, "bob", "verdict")
    assert len(llm.prompts) == asked


def test_two_requests_at_once_start_one_rewrite(made):
    """Phase 4 M2: the check for a running rewrite of the part and the job's start are one step."""
    import threading

    from codetortoise.pipeline import JobRunner
    svc, _, _, rid, _ = made
    runner, hold = JobRunner(svc), threading.Event()
    try:
        first = runner.submit_ai(rid, "owner", "design", "verdict", hold.wait, alone=True)
        second = runner.submit_ai(rid, "bob", "design", "verdict", hold.wait, alone=True)
        other = runner.submit_ai(rid, "bob", "design", "concerns", lambda: None, alone=True)
    finally:
        hold.set()
    assert first is not None and second is None and other is not None


def test_a_pin_outlives_a_re_run_that_tells_its_stories_titles_again(made):
    """Phase 4 M5a: a pin records the pieces of each story it cites, and a re-run finds the story by them though its
    title was told again."""
    from codetortoise.pipeline import run_design
    svc, _, owner, rid, _ = made
    assert owner.post(f"/api/reviews/{rid}/design/concerns/pin", json={"pinned": True}).status_code == 200
    cited = {s for c in _design(owner, rid)["concerns"] for s in c["stories"]}
    ss = svc.store.get_blob(rid, "stories")
    for s in ss["stories"]:
        if s["id"] in cited:
            s["title"] += ", told again"
    svc.store.put_blob(rid, "stories", ss)
    run_design(rid, svc)
    assert cited and _design(owner, rid)["sources"]["concerns"] == "pinned"


def test_two_rewrites_of_different_parts_asked_at_once_both_land(fx, tmp_path):
    """Phase 4 M8: two readers rewrite different parts at the same time. Both calls are out before either lands; each
    lands on the design as it is by then, and a re-run of the same prompt keeps both."""
    import threading

    from codetortoise.pipeline import run_review
    both = threading.Barrier(2, timeout=10)

    def answer(system, user):
        if "REWRITE:" in user:
            both.wait()                                             # neither call answers until both are asked
        return _answer(system, user)
    svc = make_services(fx, tmp_path)
    _strong(svc, answer)
    owner = login(make_app(svc, InlineRunner(svc)), "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    walk = f"walk:{_design(owner, rid)['walks'][0]['id']}"
    failed: list[Exception] = []

    def rewrite(user: str, part: str, instruction: str) -> None:
        try:
            ondemand.rewrite_design(svc, rid, user, part, instruction)
        except Exception as e:                                      # noqa: BLE001 - asserted below
            failed.append(e)
    threads = [threading.Thread(target=rewrite, args=("bob", "verdict", "shorter")),
               threading.Thread(target=rewrite, args=("owner", walk, ""))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    landed = {"verdict": {"by": "bob", "instruction": "shorter"}, walk: {"by": "owner", "instruction": ""}}
    assert failed == [] and (_design(owner, rid)["verdict"], _design(owner, rid)["rewrites"]) == (SHORT, landed)
    assert sorted(svc.store.get_blob(rid, "design_chosen")["parts"]) == sorted(landed)
    run_review(rid, svc)                                            # the same prompt: both rewrites stay
    assert (_design(owner, rid)["verdict"], _design(owner, rid)["rewrites"]) == (SHORT, landed)
