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
    assert over_cap(long) == ("The design context is 12,014 characters; it holds at most 12,000. The longest part is the "
                              "notes, at 6,000 characters.")


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


def test_a_link_whose_path_some_servers_read_as_outside_the_listed_folder_is_refused():
    """Tomcat and Jetty drop a `;…` path parameter before they resolve `..`; IIS reads `\\` and `%5C` as `/`; a `%2F`
    hides a separator and a `%25` a second decoding from the check (final review I1)."""
    for path in ["..;/admin", "%2e%2e;/admin", "..;jsessionid=x/admin", "..\\admin", "..%5Cadmin", "..%5cadmin",
                 "%252e%252e/admin", "x%2F..%2Fadmin", "x%2f..%2fadmin", "notes;v=2.md"]:
        assert not allowed("https://wiki.example.com/design/" + path, SITE), path
    assert allowed("https://wiki.example.com/design/uart%20notes.md", SITE)       # an escaped space is still a page
    assert allowed("https://wiki.example.com/design/page?id=%2Fuart;v=2", SITE)   # the query is the page's own business


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
                       ("down", "could not be reached"), ("big", "more than 1 MB")]:
        with pytest.raises(LinkRefused, match=said):
            read_link(f"https://wiki.example.com/design/{path}", SITE, c)


def test_a_link_with_an_invalid_host_name_is_refused_in_words():
    """Phase 3 minor 1: a host that is not a valid name (a malformed IDNA label) is refused in words, not with a 500;
    a listed site with one lets nothing through."""
    with pytest.raises(LinkRefused, match="The link's host is not a valid name"):
        read_link("https://xn--wiki-.example.com/design/uart.md", SITE)
    assert not allowed("https://wiki.example.com/design/uart.md", ["https://xn--wiki-.example.com/design/"])


class _Raw(httpx.SyncByteStream):
    """A body as the network sends it, not read ahead (a `content=` body is unpacked as the response is made)."""

    def __init__(self, body: bytes):
        self.body = body

    def __iter__(self):
        for i in range(0, len(self.body), 65536):
            yield self.body[i:i + 65536]


def test_a_link_is_read_within_one_deadline(monkeypatch):
    """Phase 3 minor 2: the whole read has one deadline; a site that sends a little at a time is cut off at it."""
    import time

    from codetortoise import design_context as dc
    monkeypatch.setattr(dc, "LINK_TIMEOUT", 0.3)

    def drip():
        for _ in range(40):
            time.sleep(0.05)
            yield b"x"
    c = _client(lambda req: httpx.Response(200, headers={"content-type": "text/plain"}, content=drip()))
    t = time.monotonic()
    with pytest.raises(LinkRefused, match="took longer than 0.3 s"):
        read_link("https://wiki.example.com/design/slow.md", SITE, c)
    assert time.monotonic() - t < 1.0


def _site(gap: float, stop) -> int:
    """A site on this machine that answers "hi" as text, sending its status line and headers a byte every `gap`
    seconds until `stop` is set; its port."""
    import socket
    import threading
    import time
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(4)

    def run():
        with s:
            conn, _ = s.accept()
            with conn:
                try:
                    conn.recv(65536)
                    for b in b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\n":
                        if stop.is_set():
                            return
                        conn.sendall(bytes([b]))
                        time.sleep(gap)
                    conn.sendall(b"hi")
                except OSError:     # the reader gave up and closed its end
                    pass
    threading.Thread(target=run, daemon=True).start()
    return s.getsockname()[1]


def test_a_site_that_trickles_its_headers_is_refused_within_the_deadline(monkeypatch):
    """Final review minor 1: the deadline holds for the whole read, not only between body chunks: a listed site that
    sends its headers a byte at a time (each within httpx's per-step timeout) is refused at the deadline, the read left
    behind ends rather than waiting on the site, and the next link is read at once."""
    import threading
    import time

    from codetortoise import design_context as dc
    monkeypatch.setattr(dc, "LINK_TIMEOUT", 0.5)
    stop = threading.Event()
    try:
        port = _site(0.08, stop)                     # about 5 s for its 64 bytes of head
        base = threading.active_count()
        t = time.monotonic()
        with pytest.raises(LinkRefused, match="took longer than 0.5 s"):
            read_link(f"http://127.0.0.1:{port}/a.md", [f"http://127.0.0.1:{port}/"])
        assert time.monotonic() - t < 1.5
        end = time.monotonic() + 2
        while threading.active_count() > base and time.monotonic() < end:
            time.sleep(0.05)
        assert threading.active_count() <= base      # the site still trickles; the read gave up on it
    finally:
        stop.set()
    port = _site(0, threading.Event())
    t = time.monotonic()
    assert read_link(f"http://127.0.0.1:{port}/b.md", [f"http://127.0.0.1:{port}/"]) == "hi"
    assert time.monotonic() - t < 0.5


def test_a_compressed_link_is_refused_past_1_mb_without_unpacking_it_all(monkeypatch):
    """Phase 3 minor 2: a gzip or deflate body is unpacked at most 1 MB at a time and refused past 1 MB; another
    encoding is refused; a small packed body reads as its text."""
    import gzip
    import zlib

    real, sizes, asked = zlib.decompressobj, [], []

    class Counted:
        def __init__(self, *args):
            self.d = real(*args)

        def decompress(self, data, max_length=0):
            out = self.d.decompress(data, max_length)
            sizes.append(len(out))
            return out

        def __getattr__(self, name):
            return getattr(self.d, name)
    monkeypatch.setattr(zlib, "decompressobj", Counted)
    raw = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    pages = {"/design/bomb": ("gzip", gzip.compress(b"\0" * 20_000_000)),
             "/design/small": ("gzip", gzip.compress(b"Never drop a byte.")),
             "/design/zipped": ("deflate", zlib.compress(b"Long writes are refused.")),
             "/design/raw": ("deflate", raw.compress(b"Reads are short.") + raw.flush()),
             "/design/brotli": ("br", b"\x0b\x02\x80hi\x03")}

    def answer(req):
        asked.append(req.headers.get("accept-encoding"))
        enc, body = pages[req.url.path]
        return httpx.Response(200, headers={"content-type": "text/plain", "content-encoding": enc}, stream=_Raw(body))
    c = _client(answer)
    assert read_link("https://wiki.example.com/design/small", SITE, c) == "Never drop a byte."
    assert read_link("https://wiki.example.com/design/zipped", SITE, c) == "Long writes are refused."
    assert read_link("https://wiki.example.com/design/raw", SITE, c) == "Reads are short."
    sizes.clear()
    with pytest.raises(LinkRefused, match="more than 1 MB"):
        read_link("https://wiki.example.com/design/bomb", SITE, c)
    assert sizes and max(sizes) <= MAX_LINK_BYTES + 1
    with pytest.raises(LinkRefused, match="sent br-encoded; only gzip or deflate is read"):
        read_link("https://wiki.example.com/design/brotli", SITE, c)
    assert set(asked) == {"gzip, deflate"}


class _Sent(httpx.SyncByteStream):
    """A body sent as the given chunks then, when `on`, 64 KiB of zeros at a time with no end: a reader that reads on
    past 50 of them fails the test."""

    def __init__(self, *chunks: bytes, on: bool = False):
        self.chunks, self.on = chunks, on

    def __iter__(self):
        yield from self.chunks
        if self.on:
            for _ in range(50):
                yield b"\0" * 65536
            raise AssertionError("read on past the packed body's end")


def test_a_packed_body_is_read_to_its_end_and_no_further():
    """Final review minor 2: what a site sends after a packed body's end is not read on (zlib would keep it, counted by
    no limit), except another gzip member, read as part of the body, the two held to 1 MB together; a body of exactly
    1 MB with a newline after its end is read."""
    import gzip
    import zlib
    raw = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    one, two = gzip.compress(b"one "), gzip.compress(b"two")
    pages = {"/design/tail": ("gzip", _Sent(gzip.compress(b"Reads are short."), on=True)),
             "/design/zipped": ("deflate", _Sent(zlib.compress(b"Writes are long."), on=True)),
             "/design/raw": ("deflate", _Sent(raw.compress(b"Never drop a byte.") + raw.flush(), on=True)),
             "/design/members": ("gzip", _Sent(one + two)),
             "/design/split": ("gzip", _Sent(one + two[:1], two[1:])),
             "/design/full": ("gzip", _Sent(gzip.compress(b"x" * MAX_LINK_BYTES) + b"\n")),
             "/design/over": ("gzip", _Sent(gzip.compress(b"y" * 600_000) + gzip.compress(b"z" * 600_000)))}

    def answer(req):
        enc, stream = pages[req.url.path]
        return httpx.Response(200, headers={"content-type": "text/plain", "content-encoding": enc}, stream=stream)
    c = _client(answer)
    assert read_link("https://wiki.example.com/design/tail", SITE, c) == "Reads are short."
    assert read_link("https://wiki.example.com/design/zipped", SITE, c) == "Writes are long."
    assert read_link("https://wiki.example.com/design/raw", SITE, c) == "Never drop a byte."
    assert read_link("https://wiki.example.com/design/members", SITE, c) == "one two"
    assert read_link("https://wiki.example.com/design/split", SITE, c) == "one two"
    assert len(read_link("https://wiki.example.com/design/full", SITE, c)) == MAX_LINK_BYTES
    with pytest.raises(LinkRefused, match="more than 1 MB"):
        read_link("https://wiki.example.com/design/over", SITE, c)


def test_a_transport_failure_says_why():
    """Phase 3 minor 9: a certificate the server doesn't trust, a site it can't reach and one too slow are each said
    in words; the first names SSL_CERT_FILE, where its host can add the authority that signed it."""
    def answer(req):
        p = req.url.path
        if p.endswith("/cert"):
            raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local "
                                     "issuer certificate (_ssl.c:1006)")
        if p.endswith("/slow"):
            raise httpx.ReadTimeout("The read operation timed out")
        raise httpx.ConnectError("[Errno -2] Name or service not known")
    c = _client(answer)
    for path, said in [("cert", "certificate is not trusted by this server.*SSL_CERT_FILE"),
                       ("slow", "took longer than 10 s"), ("down", "The site could not be reached")]:
        with pytest.raises(LinkRefused, match=said):
            read_link(f"https://wiki.example.com/design/{path}", SITE, c)


def test_over_the_cap_the_message_names_the_longest_document():
    """Phase 3 minor 8: over the cap, the message names the longest part (a document, or the notes) and its size, so
    the owner knows what to shorten."""
    docs = DesignContext(notes="x" * 3000, documents=[ContextDoc(name="Bus spec", text="y" * 8000),
                                                      ContextDoc(name="d", text="z" * 1100)])
    assert over_cap(docs) == (f"The design context is {len(context_text(docs)):,} characters; it holds at most 12,000. "
                              "The longest part is the document Bus spec, at 8,000 characters.")
    notes = DesignContext(notes="x" * 9000, documents=[ContextDoc(name="Bus spec", text="y" * 3100)])
    assert over_cap(notes).endswith("The longest part is the notes, at 9,000 characters.")
