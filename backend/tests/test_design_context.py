"""The design context (spec 2026-11-02 §8): its text, its cap, how a review keeps it and how a link is read."""
import httpx
import pytest
from helpers import make_services

from codetortoise.config import ComponentRule, ServerConfig
from codetortoise.design_context import (
    BLOB,
    CAP,
    MAX_LINK_BYTES,
    ContextDoc,
    DesignContext,
    HandCondition,
    HandConditions,
    LinkRefused,
    allowed,
    context_hash,
    context_text,
    load_context,
    over_cap,
    page_text,
    read_link,
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


SITE = ["https://wiki.example.com/design/"]


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_the_host_lists_no_site_to_read_links_from_by_default():
    assert ServerConfig().design_links == []


def test_a_link_is_read_only_from_a_site_the_host_lists():
    assert allowed("https://wiki.example.com/design/uart.md", SITE)
    assert allowed("https://WIKI.example.com/design/", SITE)
    for url in ["https://wiki.example.com/admin", "https://wiki.example.com/designs/x", "http://wiki.example.com/design/x",
                "https://wiki.example.com.evil.net/design/x", "https://wiki.example.com:8443/design/x",
                "https://user@wiki.example.com/design/x", "https://wiki.example.com/design/../admin",
                "https://wiki.example.com/design/%2e%2e/admin", "file:///etc/passwd", "not a link"]:
        assert not allowed(url, SITE), url
    assert allowed("https://wiki.example.com/x", ["https://wiki.example.com"])     # a site listed without a path: all of it


def test_with_no_site_listed_no_link_is_read_and_one_off_the_list_is_refused():
    with pytest.raises(LinkRefused, match="This server reads no links"):
        read_link("https://wiki.example.com/design/uart.md", [])
    with pytest.raises(LinkRefused, match="only from https://wiki.example.com/design/"):
        read_link("https://other.example.com/x", SITE)


def test_a_listed_link_is_read_as_text_and_a_web_page_as_its_words():
    pages = {"/design/uart.md": ("text/markdown; charset=utf-8", "# UART\nNever drop a byte."),
             "/design/page": ("text/html", "<html><head><style>p{}</style></head><body><p>Writes &amp; reads</p>"
                                           "<script>x()</script><ul><li>One</li><li>Two</li></ul></body></html>")}

    def answer(req):
        kind, body = pages[req.url.path]
        return httpx.Response(200, headers={"content-type": kind}, text=body)
    c = _client(answer)
    assert read_link("https://wiki.example.com/design/uart.md", SITE, c) == "# UART\nNever drop a byte."
    assert read_link("https://wiki.example.com/design/page", SITE, c) == "Writes & reads\n\nOne\n\nTwo"


def test_a_web_page_s_words_keep_its_blocks_apart():
    assert page_text("<p>A &lt;b&gt;</p><p>C</p>") == "A <b>\n\nC"
    assert page_text("<div>x<br>y</div>") == "x\ny"


def test_a_link_that_leads_elsewhere_fails_holds_no_text_or_too_much_is_refused():
    def answer(req):
        p = req.url.path
        if p.endswith("/moved"):
            return httpx.Response(302, headers={"location": "https://evil.example.net/"})
        if p.endswith("/gone"):
            return httpx.Response(404)
        if p.endswith("/image"):
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG")
        if p.endswith("/down"):
            raise httpx.ConnectError("down")
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"x" * (MAX_LINK_BYTES + 1))
    c = _client(answer)
    for path, said in [("moved", "leads somewhere else"), ("gone", "answered 404"), ("image", "holds image/png"),
                       ("down", r"could not be read \(ConnectError\)"), ("big", "more than 1 MB")]:
        with pytest.raises(LinkRefused, match=said):
            read_link(f"https://wiki.example.com/design/{path}", SITE, c)
