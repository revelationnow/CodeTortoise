"""The design context (spec 2026-11-02 §8): what the code can't say, given by the review's owner — free notes,
documents (pasted, from a file, or a link the server can read), conditions added or left out by hand and a choice of
components. The overview's opening and its design parts read it; stories, flows and checks never do, so it can't change
what is flagged."""
from __future__ import annotations

import hashlib
import re
import ssl
import threading
import time
import zlib
from html.parser import HTMLParser

import httpx
from pydantic import BaseModel, Field

from codetortoise.config import ComponentRule

CAP = 12_000                 # characters of it the prompts read, documents included once read (§8, §14)
BLOB = "design_context"      # where a review keeps it


class ContextDoc(BaseModel):
    """A document of the context: its text, pasted, from a file, or read from `url` once when the context was saved."""
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=CAP)
    url: str | None = Field(default=None, max_length=2000)


class HandCondition(BaseModel):
    """A condition the owner adds: its test as the code writes it ("len > 64"), and the function holding it when the
    test alone does not find it."""
    test: str = Field(min_length=1, max_length=300)
    function: str | None = Field(default=None, max_length=200)


class HandConditions(BaseModel):
    add: list[HandCondition] = Field(default_factory=list, max_length=10)
    remove: list[str] = Field(default_factory=list, max_length=20)        # tests of conditions the rules found


class DesignContext(BaseModel):
    notes: str = Field(default="", max_length=CAP)
    documents: list[ContextDoc] = Field(default_factory=list, max_length=10)
    conditions: HandConditions = Field(default_factory=HandConditions)
    components: list[ComponentRule] = Field(default_factory=list, max_length=30)   # empty: analysis.components


def context_text(c: DesignContext) -> str:
    """What the prompts read of it: the notes, then each document under its name."""
    parts = [c.notes.strip()] if c.notes.strip() else []
    parts += [f"DOCUMENT {d.name.strip()}:\n{d.text.strip()}" for d in c.documents if d.text.strip()]
    return "\n\n".join(parts)


def context_hash(c: DesignContext) -> str | None:
    """Which text the opening was written from (§9's `context_hash`); None when the context has none to read."""
    text = context_text(c)
    return hashlib.sha256(text.encode()).hexdigest()[:12] if text else None


def over_cap(c: DesignContext) -> str | None:
    """Why the context is too long to keep (§8: at most CAP characters once its documents are read), or None; it names
    the longest part, a document or the notes, and its size."""
    n = len(context_text(c))
    if n <= CAP:
        return None
    parts = [("the notes", len(c.notes.strip()))] + [(f"the document {d.name.strip()}", len(d.text.strip()))
                                                     for d in c.documents]
    what, size = max(parts, key=lambda p: p[1])
    return (f"The design context is {n:,} characters; it holds at most {CAP:,}. The longest part is {what}, at "
            f"{size:,} characters.")


def same_test(a: str, b: str) -> bool:
    """Two tests are the same when they differ only in spacing: `len>64` is `len > 64`."""
    return re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b)


def load_context(store, rid: int) -> DesignContext:
    """A review's design context; an empty one when it has none."""
    raw = store.get_blob(rid, BLOB)
    return DesignContext.model_validate(raw) if raw else DesignContext()


MAX_LINK_BYTES = 1_000_000   # a document read from a link holds at most this (§14)
LINK_TIMEOUT = 10.0          # seconds to read it in, all of it
_PACKED = {"gzip": 16 + zlib.MAX_WBITS, "x-gzip": 16 + zlib.MAX_WBITS, "deflate": zlib.MAX_WBITS}   # zlib's wbits
_READ = ("text/plain", "text/markdown", "text/x-markdown", "text/html")
# in a raw path: a separator or a dot some servers read where this check sees none (Tomcat and Jetty drop `;…` before
# resolving `..`, IIS reads `\` and `%5C` as `/`, `%2F` is a hidden `/`, `%25` a second decoding)
_UNSAFE = re.compile(rb"[\\;]|%(?:2f|5c|25)", re.I)


class LinkRefused(Exception):
    """A link the server will not or could not read; the message says why, in words for the owner."""


def allowed(url: str, sites: list[str]) -> bool:
    """Whether the server may read `url`: http or https, with no user name and no `.` or `..` in its path, nor any
    spelling of a separator or a dot that some servers resolve where this check sees none (`_UNSAFE`), on a site the
    host lists (`server.design_links`) — the same scheme, host and port, and a path at or under the listed one."""
    try:
        u = httpx.URL(url)
        _ = u.host                                      # a host that is not a valid name (IDNA) raises here
    except Exception:  # not a URL at all
        return False
    raw = u.raw_path.split(b"?", 1)[0]                  # the path as sent, before any decoding; the query is the page's
    if (u.scheme not in ("http", "https") or not u.host or u.userinfo or _UNSAFE.search(raw)
            or any(p in (".", "..") for p in u.path.split("/"))):
        return False
    for site in sites:
        try:
            s = httpx.URL(site)
            _ = s.host
        except Exception:  # a listed site that is no URL lets nothing through
            continue
        base = s.path or "/"
        under = u.path == base or u.path.startswith(base if base.endswith("/") else base + "/")
        if (u.scheme, u.host.lower(), u.port) == (s.scheme, s.host.lower(), s.port) and under:
            return True
    return False


class _Words(HTMLParser):
    """A web page's words: tags dropped, scripts and styles left out, a line break at each block."""
    SKIP = {"script", "style", "noscript", "template"}
    BLOCK = {"p", "div", "br", "li", "tr", "pre", "section", "article", "table", "ul", "ol", "h1", "h2", "h3", "h4",
             "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def page_text(html: str) -> str:
    """A web page as the prompts read it: its words, a blank line at most between blocks."""
    p = _Words()
    p.feed(html)
    p.close()
    rows = [" ".join(r.split()) for r in "".join(p.out).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(rows)).strip()


def _slow() -> str:
    return f"The link took longer than {LINK_TIMEOUT:g} s to read."


def _untrusted(e: BaseException | None) -> bool:
    """Whether transport error `e` comes of a certificate this server does not trust."""
    for _ in range(10):                                # the chain of causes, as httpx and httpcore wrap the ssl error
        if e is None:
            return False
        if isinstance(e, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
            return True
        e = e.__cause__ or e.__context__
    return False


def _why(e: httpx.HTTPError) -> str:
    """A transport failure in words for the owner (phase 3 minor 9)."""
    if isinstance(e, httpx.TimeoutException):
        return _slow()
    if _untrusted(e):
        return ("The site's certificate is not trusted by this server: its host can add the authority that signed it to "
                "the bundle SSL_CERT_FILE names.")
    if isinstance(e, httpx.ConnectError):
        return "The site could not be reached."
    return f"The link could not be read ({type(e).__name__})."


def _body(resp: httpx.Response, deadline: float) -> bytes:
    """`resp`'s body by `deadline`, at most MAX_LINK_BYTES: as sent, or unpacked when sent gzip- or deflate-encoded, at
    most what is left of MAX_LINK_BYTES at a time, so a small packed body can't fill memory before it is refused."""
    enc = resp.headers.get("content-encoding", "").strip().lower() or "identity"
    if enc != "identity" and enc not in _PACKED:
        raise LinkRefused(f"The link is sent {enc}-encoded; only gzip or deflate is read.")
    unpack = zlib.decompressobj(_PACKED[enc]) if enc in _PACKED else None
    raw = False                                        # a deflate body without zlib's header, as some servers send
    body = bytearray()
    for chunk in resp.iter_raw() if unpack is not None else resp.iter_bytes():
        if time.monotonic() > deadline:
            raise LinkRefused(_slow())
        while chunk:
            if unpack is None:
                body += chunk
                chunk = b""
            else:
                try:
                    body += unpack.decompress(chunk, MAX_LINK_BYTES + 1 - len(body))
                except zlib.error as e:
                    if enc != "deflate" or raw or body:
                        raise LinkRefused("The link's packed body could not be unpacked.") from e
                    unpack, raw = zlib.decompressobj(-zlib.MAX_WBITS), True
                    continue
                chunk = unpack.unconsumed_tail
            if len(body) > MAX_LINK_BYTES:
                raise LinkRefused("The link holds more than 1 MB.")
    return bytes(body)


def read_link(url: str, sites: list[str], client: httpx.Client | None = None) -> str:
    """The text behind a link, read once when the context is saved (§8): only from a site the host lists, with no
    redirect followed, at most MAX_LINK_BYTES (unpacked, when packed), within LINK_TIMEOUT for the whole read, as text or
    markdown, or a web page's words.

    httpx bounds each step of a read (the connect, each wait for bytes) but not the whole, so a site that sends its
    headers a byte at a time would hold the save past the deadline. The read runs in a thread of its own instead: one
    still going at the deadline is refused, and the client it reads with, when it is this function's own, is closed
    under it, so the thread ends at the site's next byte or step timeout rather than waiting on the site."""
    if not sites:
        raise LinkRefused("This server reads no links: its host lists the sites it may read under server.design_links "
                          "in tortoise.yaml. Paste the text or add the file instead.")
    try:
        _ = httpx.URL(url).host
    except httpx.InvalidURL:  # not a URL at all: refused below as off the list
        pass
    except ValueError as e:   # a host that is not a valid name, such as a malformed IDNA label (phase 3 minor 1)
        raise LinkRefused("The link's host is not a valid name.") from e
    if not allowed(url, sites):
        raise LinkRefused(f"This server reads links only from {', '.join(sites)}.")
    deadline = time.monotonic() + LINK_TIMEOUT
    http = client if client is not None else httpx.Client(timeout=LINK_TIMEOUT, follow_redirects=False)
    box: dict = {}

    def work() -> None:
        try:
            box["text"] = _read(url, deadline, http)
        except BaseException as e:  # noqa: BLE001 - raised again in the caller's thread below
            box["error"] = e
    reader = threading.Thread(target=work, name="read-link", daemon=True)
    reader.start()
    reader.join(max(0.0, deadline - time.monotonic()))
    if client is None:
        http.close()
    if reader.is_alive():
        raise LinkRefused(_slow())
    if "error" in box:
        raise box["error"]
    return box["text"]


def _read(url: str, deadline: float, http: httpx.Client) -> str:
    """The read itself, with `http`: the answer checked, its body by `deadline`, a web page as its words."""
    try:
        with http.stream("GET", url, follow_redirects=False, headers={"Accept-Encoding": "gzip, deflate"}) as resp:
            if resp.is_redirect:
                raise LinkRefused("The link leads somewhere else; give the address it leads to.")
            if resp.status_code != 200:
                raise LinkRefused(f"The link answered {resp.status_code}.")
            kind = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if kind not in _READ:
                raise LinkRefused(f"The link holds {kind or 'something of no stated type'}; only text, markdown or a "
                                  "web page is read.")
            text = _body(resp, deadline).decode(resp.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as e:
        raise LinkRefused(_why(e)) from e
    return page_text(text) if kind == "text/html" else text
