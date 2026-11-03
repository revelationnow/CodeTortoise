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
    assert _job(owner, rid)["error"] == ("the AI did not answer: big: RuntimeError: down; fresh try: RuntimeError: down; "
                                         "nothing was changed. Try again")
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
