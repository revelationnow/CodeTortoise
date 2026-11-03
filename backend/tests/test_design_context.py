"""The design context (spec 2026-11-02 §8): its text, its cap, how a review keeps it and how a link is read."""
from helpers import make_services

from codetortoise.config import ComponentRule
from codetortoise.design_context import (
    BLOB,
    CAP,
    ContextDoc,
    DesignContext,
    HandCondition,
    HandConditions,
    context_hash,
    context_text,
    load_context,
    over_cap,
    same_test,
)


def test_the_prompts_read_the_notes_then_each_document_under_its_name():
    c = DesignContext(notes="  The UART must never drop a byte.\n", documents=[
        ContextDoc(name="Design note", text="Writes over 64 bytes are refused.\n"), ContextDoc(name="Empty", text="  ")])
    assert context_text(c) == "The UART must never drop a byte.\n\nDOCUMENT Design note:\nWrites over 64 bytes are refused."


def test_a_context_without_text_has_no_hash_though_it_adds_conditions_or_components():
    c = DesignContext(conditions=HandConditions(add=[HandCondition(test="len > 64")]),
                      components=[ComponentRule(name="Driver", globs=["driver/*"])])
    assert context_text(c) == "" and context_hash(c) is None
    assert context_hash(DesignContext(notes="a")) != context_hash(DesignContext(notes="b"))
    assert len(context_hash(DesignContext(notes="a"))) == 12


def test_the_cap_counts_what_the_prompts_read():
    assert over_cap(DesignContext(notes="x" * CAP)) is None
    long = DesignContext(notes="x" * 6000, documents=[ContextDoc(name="d", text="y" * 6000)])
    assert over_cap(long) == ("The design context is 12,014 characters; it holds at most 12,000. Shorten the notes or a "
                              "document.")


def test_tests_that_differ_only_in_spacing_are_the_same():
    assert same_test("len>64", "len > 64") and same_test(" a  &&\n b ", "a && b")
    assert not same_test("len > 64", "len >= 64")


def test_a_review_without_a_context_reads_an_empty_one(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101])
    assert load_context(svc.store, rid) == DesignContext()
    svc.store.put_blob(rid, BLOB, DesignContext(notes="n").model_dump())
    assert load_context(svc.store, rid).notes == "n"
