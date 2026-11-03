"""The design context (spec 2026-11-02 §8): what the code can't say, given by the review's owner — free notes,
documents (pasted, from a file, or a link the server can read), conditions added or left out by hand and a choice of
components. The overview's opening and its design parts read it; stories, flows and checks never do, so it can't change
what is flagged."""
from __future__ import annotations

import hashlib
import re
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
    """Why the context is too long to keep (§8: at most CAP characters once its documents are read), or None."""
    n = len(context_text(c))
    if n <= CAP:
        return None
    return f"The design context is {n:,} characters; it holds at most {CAP:,}. Shorten the notes or a document."


def same_test(a: str, b: str) -> bool:
    """Two tests are the same when they differ only in spacing: `len>64` is `len > 64`."""
    return re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b)


def load_context(store, rid: int) -> DesignContext:
    """A review's design context; an empty one when it has none."""
    raw = store.get_blob(rid, BLOB)
    return DesignContext.model_validate(raw) if raw else DesignContext()


MAX_LINK_BYTES = 1_000_000   # a document read from a link holds at most this (§14)
LINK_TIMEOUT = 10.0          # seconds to read it in
_READ = ("text/plain", "text/markdown", "text/x-markdown", "text/html")


class LinkRefused(Exception):
    """A link the server will not or could not read; the message says why, in words for the owner."""


def allowed(url: str, sites: list[str]) -> bool:
    """Whether the server may read `url`: http or https, with no user name and no `.` or `..` in its path, on a site the
    host lists (`server.design_links`) — the same scheme, host and port, and a path at or under the listed one."""
    try:
        u = httpx.URL(url)
    except Exception:  # not a URL at all
        return False
    if u.scheme not in ("http", "https") or not u.host or u.userinfo or any(p in (".", "..") for p in u.path.split("/")):
        return False
    for site in sites:
        try:
            s = httpx.URL(site)
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


def read_link(url: str, sites: list[str], client: httpx.Client | None = None) -> str:
    """The text behind a link, read once when the context is saved (§8): only from a site the host lists, with no
    redirect followed, at most MAX_LINK_BYTES, as text or markdown, or a web page's words."""
    if not sites:
        raise LinkRefused("This server reads no links: its host lists the sites it may read under server.design_links "
                          "in tortoise.yaml. Paste the text or add the file instead.")
    if not allowed(url, sites):
        raise LinkRefused(f"This server reads links only from {', '.join(sites)}.")
    own = client is None
    http = client if client is not None else httpx.Client(timeout=LINK_TIMEOUT, follow_redirects=False)
    try:
        with http.stream("GET", url, follow_redirects=False) as resp:
            if resp.is_redirect:
                raise LinkRefused("The link leads somewhere else; give the address it leads to.")
            if resp.status_code != 200:
                raise LinkRefused(f"The link answered {resp.status_code}.")
            kind = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if kind not in _READ:
                raise LinkRefused(f"The link holds {kind or 'something of no stated type'}; only text, markdown or a "
                                  "web page is read.")
            body = bytearray()
            for chunk in resp.iter_bytes():
                body += chunk
                if len(body) > MAX_LINK_BYTES:
                    raise LinkRefused("The link holds more than 1 MB.")
            text = bytes(body).decode(resp.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as e:
        raise LinkRefused(f"The link could not be read ({type(e).__name__}).") from e
    finally:
        if own:
            http.close()
    return page_text(text) if kind == "text/html" else text
