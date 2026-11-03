# Design overview, phase 3 (the design context) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 3 of the design overview (spec §16 item 3): a review's owner gives it a design context — free notes,
documents (pasted, from a file, or a link the server can read), conditions added or left out by hand and a choice of
components — in the ⋯ menu's "Design context…" panel or when starting the review; saving it re-runs the design stage
alone, the introduction's `whole` and the design's model parts read it, and nothing that flags work ever does.

**Architecture:** `codetortoise/design_context.py` holds the context's model, the text the prompts read, its cap and
the reading of a link (only from sites the host lists in `server.design_links`). The rules read the context's
components and conditions (`build_design(context=…)`); the intro and design prompts gain a DESIGN CONTEXT section. The
pipeline's design work moves out of `run_review`'s closures into module functions so a new `run_design` can run the
design stage alone from the stored blobs, on the workspace's queue (`JobRunner.submit_design`); the review's status
moves only between done and degraded, so its page stays readable while the frontend polls the stage. Two routes read
and save the context (the owner saves, anyone in the review reads); the creation form gains a notes field.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, httpx, SQLite; React 19, TypeScript, Vite, Vitest (node), Playwright 1.63.

**Spec:** `docs/superpowers/specs/2026-11-02-design-overview-design.md` (§8, §9, §11, §16 item 3; §18 holds the notes
made against the code). Phases 1 and 2 (`docs/superpowers/plans/2026-11-02-design-overview-phase1.md`, `…-phase2.md`)
built what this phase feeds.

## Global Constraints

- Public repo: no owner's proprietary names in code, tests, docs or commits; the bundled fixture's names (`uart_send`,
  `hal_write`, `logger_flush`…) and `example.com` hosts are fine. No absolute local paths in committed files.
- §8: the context is stored per review in blob `design_context`, capped at 12 000 characters after documents are read;
  saving it re-runs only the `design` stage; the prompts that read it are the opening (the introduction) and the design's
  parts; stories, flows and checks never read it, so it can't change what is flagged.
- §11: `GET/PUT /api/reviews/{id}/design-context`; saving queues the `design` stage and returns 202.
- Security: only the review's owner saves a context (403 for anyone else). The server reads a link only from a site the
  host lists in `server.design_links` (tortoise.yaml; none by default), follows no redirect, reads at most 1 MB within 10
  seconds, and only text, markdown or a web page. Say why in plain words wherever a link is refused.
- AI text keeps its AI mark; the opening's source line says when the model read the context (§3.1 item 2).
- Styles: app variables only (`dc-*` in `workspace.css`); the panel is an `rm-panel`.
- Commits: `git -c user.email=2929430+revelationnow@users.noreply.github.com commit`, messages ending in the
  `Co-Authored-By` and `Claude-Session` lines shown in each task. Stage files by name; never stage
  `frontend/e2e/strong-review.txt`.
- Tests: backend `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider …`
  and `.venv/bin/ruff check codetortoise tests`; frontend `npx vitest run …`, `npx tsc --noEmit`, `npm run build`; e2e
  from `frontend/` after `npm run build`: `mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test … --retries=0; rm -rf ../.pwtmp`.

## Review Focus

1. **A link the host didn't list, or one that tricks the check:** another host whose name starts like a listed one
   (`wiki.example.com.evil.net`), another port or scheme, a user name in the URL, `..` in the path, a redirect, a body
   over 1 MB, an image — each refused with a reason, and nothing fetched off the list (Task 2's cases).
2. **A design-only re-run in an odd state:** the review has no reading, the design is off, the model fails or is
   refused, a full run is queued behind it, the stored blobs are those of an older run — the stage says so, the review
   stays readable, and its status settles to done or degraded, never stuck (Task 5).
3. **A hand condition the code lacks, or one to leave out that the rules never found:** the design still builds and
   the panel says what was not found (Task 3, Task 8's e2e).
4. **A context over the cap:** notes plus documents over 12 000 characters, or one field over its own limit — 422 with
   a message the panel shows; the panel's count warns before saving (Task 6, Task 7).
5. **Someone else in the review:** they read the context but get no field to change it, and the server refuses their
   save (Task 6, Task 8's e2e).

## Rulings made while planning

| # | Ruling | Why |
|---|---|---|
| P1 | The context is `{notes, documents: [{name, text, url}], conditions: {add: [{test, function}], remove: [test]}, components: [{name, globs}]}`, every part optional; an empty one is `DesignContext()` | §8's four parts; one model for the blob, the API body and the panel |
| P2 | The cap counts the text the prompts read: the notes, then each document as "DOCUMENT name:" and its text, joined by blank lines (`context_text`); conditions and components act through the rules and are bounded by their own lengths | §8 caps the context "after documents are read"; what costs tokens is that text |
| P3 | A link is read once, at save, by the server, only from `server.design_links` (the host's tortoise.yaml, none by default): same scheme, host and port, a path at or under the listed one, no user name, no `.`/`..` segment, no redirect followed, at most 1 MB in 10 s, `text/plain`, `text/markdown` or `text/html` (its words, without tags, scripts or styles). A document sent with its text keeps it: only a link with no text yet is read | §8 "a link the server can read"; a workspace owner who is not the host must not make the server fetch other addresses on its network (the `server.toolchain_folders` precedent) |
| P4 | A file is read in the browser and sent as a document's text; pasting goes into the notes | No upload route needed; the server stores text only |
| P5 | A condition added by hand is an `if`, `else if` or `case` in a changed function outside the tests whose test matches the given one with spacing ignored, in the named function when one is named (`Engine::step` answers to `step`); the added ones come first, in the order given, then the rules' less those left out; an added one is a `Gate` with `source="context"`. What the context names but the code lacks goes to `ReadingDesign.context_notes` and the stage's message, without degrading the stage | §8 "conditions added or removed by hand"; §9's `source: code / context`; the fold is about the first condition (R14), so the owner's leads |
| P6 | Components given in the context replace `analysis.components` for this review's design; none given: the config's | §8 "a choice of components", §13 |
| P7 | `context_hash` is the first 12 hex digits of the sha256 of the context's text, None when it has none; the opening's source line reads "AI, from the stories and the design context" when it is set, else "AI, from the stories" | §3.1 item 2, §6.1; a context of only conditions or components gives the model no text to read |
| P8 | The intro and design prompts carry the text between "DESIGN CONTEXT (from the review's owner):" and "END OF DESIGN CONTEXT"; with no text the section is left out. `INTRO_VERSION` 2→3 and `DESIGN_VERSION` 1→2, as their asks change | §8, §9 ("with a design context, `llm/intro.py` receives it"); the versions key the caches |
| P9 | `run_design(rid, svc)` re-runs the design stage alone on the workspace's queue (`submit_design`, counted by `busy()`), under the review's lock: it asks the introduction again with the context (kept by its prompt, as in a full run), stores `reading`, builds the design from the stored blobs and stores it. Only the design stage's row changes; the review's status is set again to done or degraded only when it was one of them | §8, §18.9; the page stays readable; a queued full run settles its own status |
| P10 | `submit_design` marks the design stage `pending` at once ("queued: the design context changed"); the frontend polls the review every 1.5 s from the save on, while its status is final and until its design stage is no longer pending or running, then loads the reading again | The review's events stream ends at a final status; the reading holds `whole` and the design |
| P11 | Everyone in the review sees "Design context…" once it has a reading; the owner's panel edits and saves, anyone else's reads | §8 says it is entered there; readers benefit from seeing what the opening drew on |
| P12 | Review creation gains an optional "Design context" notes field (`ReviewIn.design_context`, at most 12 000 characters), stored before the run is queued | §8 "or at review creation as an optional field" |

## File map

| File | Change |
|---|---|
| `backend/codetortoise/design_context.py` | new: the model, its text, cap and hash, `load_context`, `read_link` |
| `backend/codetortoise/config.py` | `ServerConfig.design_links` |
| `backend/codetortoise/gates.py` | `hand_gates`; `build_gates(hand=, notes=)` |
| `backend/codetortoise/design.py` | `ReadingDesign.context_notes`; `build_design(context=)` |
| `backend/codetortoise/llm/design.py`, `llm/intro.py` | the DESIGN CONTEXT section; version bumps |
| `backend/codetortoise/pipeline.py` | `_intro_text`, `_design_text`, `design_part`, `run_design`, `_settle`; `JobRunner.submit_design` |
| `backend/codetortoise/web/app.py` | the two routes; `ReviewIn.design_context` |
| `backend/tests/test_design_context.py` | new |
| `backend/tests/test_gates.py`, `test_llm_design.py`, `test_llm_intro.py`, `test_pipeline.py`, `test_web.py` | new cases |
| `frontend/src/api.ts`, `src/reading/types.ts` | the context's types and calls; `context_notes` |
| `frontend/src/workspace/designContext.ts` (+ test) | new: the panel's pure helpers |
| `frontend/src/reading/design.ts` (+ test) | `sourceLine` |
| `frontend/src/workspace/useReview.ts` | `designing`, the poll |
| `frontend/src/workspace/reviewMenu.ts` (+ test), `ReviewMenu.tsx` | "Design context…" and its panel |
| `frontend/src/workspace/DesignContextPanel.tsx` | new: the panel |
| `frontend/src/workspace/Overview.tsx` | the source line |
| `frontend/src/pages/Reviews.tsx` | the creation field |
| `frontend/src/workspace/workspace.css` | `dc-*` |
| `frontend/e2e/fake_llm.py`, `e2e/design-context.spec.ts` | the fake model reads the context; e2e |
| `README.md` | the design context |

---

### Task 1: The design context, its text and its cap

**Files:**
- Create: `backend/codetortoise/design_context.py`
- Create: `backend/tests/test_design_context.py`

**Interfaces:**
- Consumes: `ComponentRule` (`codetortoise/config.py`: `name: str`, `globs: list[str]`); a store's `get_blob`.
- Produces: `CAP = 12_000`, `BLOB = "design_context"`; models `ContextDoc(name, text, url)`, `HandCondition(test,
  function)`, `HandConditions(add, remove)`, `DesignContext(notes, documents, conditions, components)`;
  `context_text(c) -> str`, `context_hash(c) -> str | None`, `over_cap(c) -> str | None`, `same_test(a, b) -> bool`,
  `load_context(store, rid) -> DesignContext`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_design_context.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_context.py`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'codetortoise.design_context'`.

- [ ] **Step 3: Write the module**

Create `backend/codetortoise/design_context.py`:

```python
"""The design context (spec 2026-11-02 §8): what the code can't say, given by the review's owner — free notes,
documents (pasted, from a file, or a link the server can read), conditions added or left out by hand and a choice of
components. The overview's opening and its design parts read it; stories, flows and checks never do, so it can't change
what is flagged."""
from __future__ import annotations

import hashlib
import re

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
```

- [ ] **Step 4: Run them to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_context.py && .venv/bin/ruff check codetortoise tests`
Expected: 5 passed; "All checks passed!".

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/design_context.py backend/tests/test_design_context.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: a review's design context: notes, documents, conditions and components, its text and its cap

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 2: Reading a link, only from the sites the host lists

**Files:**
- Modify: `backend/codetortoise/design_context.py`, `backend/codetortoise/config.py:14-23`
- Test: `backend/tests/test_design_context.py`

**Interfaces:**
- Consumes: Task 1's module.
- Produces: `ServerConfig.design_links: list[str]`; `MAX_LINK_BYTES = 1_000_000`, `LINK_TIMEOUT = 10.0`;
  `class LinkRefused(Exception)`; `allowed(url, sites) -> bool`; `page_text(html) -> str`;
  `read_link(url, sites, client: httpx.Client | None = None) -> str` (raises `LinkRefused`).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_design_context.py`:

```python
import httpx  # noqa: E402
import pytest  # noqa: E402

from codetortoise.config import ServerConfig  # noqa: E402
from codetortoise.design_context import MAX_LINK_BYTES, LinkRefused, allowed, page_text, read_link  # noqa: E402

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
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_context.py`
Expected: FAIL at collection: `ImportError: cannot import name 'MAX_LINK_BYTES'`.

- [ ] **Step 3: The host's list, and the reading**

In `backend/codetortoise/config.py`, `ServerConfig` gains, after `toolchain_folders`:

```python
    # the sites a design context's link may be read from (spec 2026-11-02 §8): the server reads a link only under one of
    # these, so a workspace owner can't make it fetch other addresses on its network; none: no link is read
    design_links: list[str] = Field(default_factory=list)
```

In `backend/codetortoise/design_context.py`, the imports become:

```python
import hashlib
import re
from html.parser import HTMLParser

import httpx
from pydantic import BaseModel, Field

from codetortoise.config import ComponentRule
```

and after `load_context` append:

```python
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
```

- [ ] **Step 4: Run them to see them pass**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_design_context.py tests/test_config.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; "All checks passed!". (If ruff's import order puts the appended imports elsewhere, move the
test file's appended imports to its top instead of the `noqa` lines.)

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/design_context.py backend/codetortoise/config.py backend/tests/test_design_context.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: a design context's link is read once, only from the sites the host lists

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 3: The rules read the context: conditions by hand, a choice of components, its hash

**Files:**
- Modify: `backend/codetortoise/gates.py` (`build_gates`, a new `hand_gates`), `backend/codetortoise/design.py`
  (`ReadingDesign`, `build_design`)
- Test: `backend/tests/test_gates.py`

**Interfaces:**
- Consumes: Task 1's `DesignContext`, `HandConditions`, `same_test`, `context_hash`; `build_components(x, ss, r, per,
  rules=None)`.
- Produces: `hand_gates(x, src, hand) -> tuple[list[Branch], list[str]]`; `build_gates(x, ss, r, per, src, lines=None,
  hand=None, notes=None)` (still returns `(gates, branches)`); `ReadingDesign.context_notes: list[str]`;
  `build_design(x, ss, details, r, per, *, lines=None, read_text=None, context=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_gates.py`:

```python
def test_a_condition_the_design_context_adds_leads_and_lists_its_lines(demo):
    from codetortoise.design_context import HandCondition, HandConditions
    notes: list[str] = []
    hand = HandConditions(add=[HandCondition(test="reg==REG_CTRL", function="hal_write")])
    gates, branches = build_gates(demo.x, demo.ss, demo.r, demo.per, demo.src, demo.lines, hand=hand, notes=notes)
    assert [(g.id, demo.x.label(g.node), g.test, g.source, g.path) for g in gates] == [
        ("G1", "hal_write", "reg == REG_CTRL", "context", "hal/regs.c"),
        ("G2", "uart_send", "len > 64", "code", "driver/uart.c")]
    assert gates[0].lines and not gates[1].lines and notes == []
    assert [b.id for b in branches] == ["G1", "G2"]


def test_a_condition_the_design_context_leaves_out_is_gone_and_what_it_names_but_lacks_is_said(demo):
    from codetortoise.design_context import HandCondition, HandConditions
    notes: list[str] = []
    hand = HandConditions(add=[HandCondition(test="x == 1")], remove=["len>64", "y > 2"])
    gates, branches = build_gates(demo.x, demo.ss, demo.r, demo.per, demo.src, demo.lines, hand=hand, notes=notes)
    assert gates == [] and branches == []
    assert notes == ["the condition `x == 1` is not in the changed functions",
                     "the condition `y > 2` to leave out is not among those the rules found"]


def test_the_design_context_s_components_replace_the_config_s_and_its_text_marks_the_design(demo):
    from codetortoise.config import ComponentRule
    from codetortoise.design import build_design
    from codetortoise.design_context import DesignContext, context_hash
    ctx = DesignContext(notes="The UART must never drop a byte.", components=[
        ComponentRule(name="Firmware", globs=["driver/*", "hal/*", "include/*"]),
        ComponentRule(name="Service", globs=["service/*"])])
    d = build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text, context=ctx)
    holder = {f: c.name for c in d.components for f in c.files}
    assert holder["driver/uart.c"] == holder["hal/regs.c"] == "Firmware" and holder["service/logger.c"] == "Service"
    assert d.context_hash == context_hash(ctx) and d.context_notes == []
    plain = build_design(demo.x, demo.ss, demo.det, demo.r, demo.per, lines=demo.lines, read_text=demo.read_text)
    assert plain.context_hash is None and "Firmware" not in {c.name for c in plain.components}
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gates.py -k "design_context"`
Expected: 3 FAIL: `TypeError: build_gates() got an unexpected keyword argument 'hand'` (twice) and
`TypeError: build_design() got an unexpected keyword argument 'context'`.

- [ ] **Step 3: Conditions by hand**

In `backend/codetortoise/gates.py`, add to the imports `from codetortoise.design_context import same_test`, and before
`build_gates` add:

```python
def hand_gates(x, src: Sources, hand) -> tuple[list[Branch], list[str]]:
    """The conditions the design context adds (§8), in its order: an if, else if or case in a changed function outside
    the tests whose test is the one given (spacing aside), in the function named when one is (`Engine::step` answers to
    `step`). The notes say which the code lacks."""
    out: list[Branch] = []
    notes: list[str] = []
    for h in hand.add:
        hit = None
        for nid in sorted(x.changed, key=lambda n: (len(n), n)):
            n, name = x.im.nodes[nid], x.label(nid)
            if n.kind != "function" or x.is_test_path(nid) or (h.function and h.function not in (name, name.rsplit("::", 1)[-1])):
                continue
            shape = src.shape(nid)
            hit = next((b for b in shape.branches if same_test(b.test, h.test)), None) if shape is not None else None
            if hit is not None:
                break
        if hit is None:
            where = f" in `{h.function}`" if h.function else ""
            notes.append(f"the condition `{h.test}`{where} is not in the changed functions")
        elif not any((b.node, b.line) == (hit.node, hit.line) for b in out):
            marks = src.marks(hit.path)
            strength = sum(1 for k in hit.body if k in marks and not trivial(src.line(hit.path, k)))
            out.append(replace(hit, kind="context", strength=strength))
    return out, notes
```

and `build_gates` becomes:

```python
def build_gates(x, ss, r, per, src: Sources, lines=None, hand=None, notes: list[str] | None = None
                ) -> tuple[list[Gate], list[Branch]]:
    """The review's conditions, at most MAX_GATES: those the design context adds first (§8), then those the rules find,
    strongest first, less those the context leaves out; only the first lists its lines (R14). `notes` gathers what the
    context names that the code lacks."""
    story_of = node_stories(ss)
    path_story: dict[str, str] = {}
    for sid in r.order:
        sr = per.get(sid)
        for w in sr.where if sr is not None else []:
            path_story.setdefault(w.path, sid)
    found = find_gates(x, src, story_of, r.order)
    added: list[Branch] = []
    if hand is not None:
        added, said = hand_gates(x, src, hand)
        said += [f"the condition `{t}` to leave out is not among those the rules found"
                 for t in hand.remove if not any(same_test(b.test, t) for b in found)]
        found = [b for b in found if not any(same_test(b.test, t) for t in hand.remove)
                 and not any((a.node, a.line) == (b.node, b.line) for a in added)]
        if notes is not None:
            notes += said
    branches = (added + found)[:MAX_GATES]
    gates: list[Gate] = []
    for i, b in enumerate(branches, 1):
        b.id = f"G{i}"
        g = Gate(id=b.id, node=b.node, test=b.test, story=story_of.get(b.node), path=rel_path(x, b.path), line=b.line,
                 guarded=[b.first, b.last], source="context" if b.kind == "context" else "code")
        if i == 1:
            g.lines, g.runs, g.stops = classify(b, x, src, story_of, path_story, r.order, lines)
        gates.append(g)
    return gates, branches
```

- [ ] **Step 4: The design reads the context**

In `backend/codetortoise/design.py`, `ReadingDesign` gains after `context_hash`:

```python
    context_notes: list[str] = Field(default_factory=list)   # what the design context names that the code lacks (§8)
```

and `build_design` becomes:

```python
def build_design(x, ss, details, r, per, *, lines=None, read_text=None, context=None) -> ReadingDesign:
    """The design overview by rules (phase 1): the components, the conditions and the walk-throughs, and every node
    they cite. `x` is the analysis's `_Ctx`; `details` the story details; `r`, `per` the reading and its stories'.
    `context`, the review's design context (§8): its components replace the config's, its conditions lead the rules' or
    leave them out, and its text's hash marks the design as written with it."""
    from codetortoise.components import build_components
    from codetortoise.design_context import context_hash
    from codetortoise.gates import Sources, build_gates
    from codetortoise.walks import build_walks
    src = Sources(x, read_text)
    rules = context.components if context is not None and context.components else None
    components, node_comp = build_components(x, ss, r, per, rules)
    notes: list[str] = []
    gates, branches = build_gates(x, ss, r, per, src, lines, hand=context.conditions if context is not None else None,
                                  notes=notes)
    walks = build_walks(x, ss, details, r, per, src, branches, lines)
    return ReadingDesign(components=components, gates=gates, walks=walks,
                         nodes=design_nodes(x, walks, gates, node_comp),
                         context_hash=context_hash(context) if context is not None else None, context_notes=notes)
```

- [ ] **Step 5: Run them to see them pass, with the design's other tests**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_gates.py tests/test_walks.py tests/test_components.py tests/test_design.py tests/test_llm_design.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; "All checks passed!". (Drop from the command any of those test files that does not exist.)

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/gates.py backend/codetortoise/design.py backend/tests/test_gates.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the design reads its context: conditions added or left out by hand, a choice of components

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 4: The introduction and the design's parts read the context's text

**Files:**
- Modify: `backend/codetortoise/llm/design.py` (`DESIGN_VERSION`, `ASK`, `prompt`, `write_design`),
  `backend/codetortoise/llm/intro.py` (`INTRO_VERSION`, `ASK`, `prompt`, `write_intro`)
- Test: `backend/tests/test_llm_design.py`, `backend/tests/test_llm_intro.py`

**Interfaces:**
- Consumes: nothing new (the text is `context_text`'s, passed in).
- Produces: `llm.design.prompt(d, r, ss, context: str = "")`, `write_design(..., weak=None, context: str = "")`;
  `llm.intro.prompt(reading, ss, cls, context: str = "")`, `write_intro(..., weak=None, context: str = "")`; the
  marker lines `DESIGN CONTEXT (from the review's owner):` and `END OF DESIGN CONTEXT`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_llm_design.py`:

```python
def test_the_prompt_reads_the_design_context_first_and_has_no_such_section_without_one(demo, made):
    text = prompt(made, demo.r, demo.ss, "The UART must never drop a byte.")
    assert ("\n\nDESIGN CONTEXT (from the review's owner):\nThe UART must never drop a byte.\nEND OF DESIGN CONTEXT\n"
            "THE CHANGE: ") in text
    assert "DESIGN CONTEXT (from" not in prompt(made, demo.r, demo.ss)
    assert "draw the concerns from it" in dl.ASK and dl.DESIGN_VERSION == 2


def test_the_model_call_asks_with_the_design_context(demo, made):
    from scripted_llm import ScriptedLlm, design_answer
    llm = ScriptedLlm(lambda system, user: design_answer(user))
    dl.write_design(llm, None, None, made, demo.r, demo.ss, context="Never drop a byte.")
    assert "DESIGN CONTEXT (from the review's owner):\nNever drop a byte.\n" in llm.prompts[0]
```

Append to `backend/tests/test_llm_intro.py`:

```python
def test_the_prompt_reads_the_design_context_last_and_has_no_such_section_without_one():
    from codetortoise.llm import intro
    r, ss = _intro_reading()
    text = prompt(r, ss, {11: "Make send unsigned"}, "The UART must never drop a byte.")
    assert text.endswith("\nDESIGN CONTEXT (from the review's owner):\nThe UART must never drop a byte.\nEND OF DESIGN CONTEXT")
    assert "DESIGN CONTEXT (from" not in prompt(r, ss, {11: "Make send unsigned"})
    assert 'what the change is for from it' in intro.ASK and intro.INTRO_VERSION == 3


def test_the_introduction_is_asked_with_the_design_context():
    r, ss = _intro_reading()
    llm = ScriptedLlm(lambda system, user: GOOD)
    write_intro(llm, None, None, r, ss, {}, context="Never drop a byte.")
    assert "DESIGN CONTEXT (from the review's owner):\nNever drop a byte.\n" in llm.prompts[0]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_llm_design.py tests/test_llm_intro.py -k "design_context"`
Expected: 4 FAIL with `TypeError` (an unexpected argument: `prompt()` takes 3 positional arguments, or `context`).

- [ ] **Step 3: The design's prompt**

In `backend/codetortoise/llm/design.py`:

- `DESIGN_VERSION = 2`.
- `ASK` ends, after "In the words, write names, never ids.", with one more sentence (keep the string's backslash line
  continuations as they are):

```text
 A DESIGN CONTEXT, when given, is the review owner's word on what the change is for and what the code can't say: \
draw the concerns from it as well as the stories, and say in the verdict where the change falls short of it; cite \
nothing from it.
```

- `prompt` takes the context and puts it first:

```python
def prompt(d: ReadingDesign, r: Reading, ss: StorySet, context: str = "") -> str:
```

  and its first `lines = [...]` statement becomes:

```python
    lines = ([f"DESIGN CONTEXT (from the review's owner):\n{context}\nEND OF DESIGN CONTEXT"] if context else []) + [
        f"THE CHANGE: {r.whole or '(no summary)'}", "THREAD LIST (id | name | purpose):"]
```

- `write_design` takes it and passes it on:

```python
def write_design(strong: LlmClient, ledger: Ledger | None, rid: int | None, d: ReadingDesign, r: Reading, ss: StorySet,
                 weak: LlmClient | None = None, context: str = "") -> tuple[list[str], str | None]:
    """Write the model's parts of `d` in place from one checked answer; returns notes on the parts that failed, and the
    model that answered (None: every part keeps its fixed text). The strong model failing is tried fresh, then on the
    weak model. `context` is the design context's text (§8)."""
    text = prompt(d, r, ss, context)
```

- [ ] **Step 4: The introduction's prompt**

In `backend/codetortoise/llm/intro.py`:

- `INTRO_VERSION = 3`.
- `ASK` ends, after "cite nothing that is not listed.", with:

```text
 When a DESIGN CONTEXT is given, say in "whole" what the change is for from it.
```

- `prompt` takes the context and puts it last:

```python
def prompt(reading: Reading, ss: StorySet, cls: dict[int, str], context: str = "") -> str:
```

  and before its `return` add:

```python
    if context:
        lines += ["DESIGN CONTEXT (from the review's owner):", context, "END OF DESIGN CONTEXT"]
```

- `write_intro` takes it and passes it on:

```python
def write_intro(strong: LlmClient, ledger: Ledger | None, rid: int | None, reading: Reading, ss: StorySet,
                cls: dict[int, str], weak: LlmClient | None = None, context: str = "") -> tuple[list[str], str | None]:
```

  with `text = prompt(reading, ss, cls, context)` and its docstring gaining "`context` is the design context's text
  (spec 2026-11-02 §8)."

- [ ] **Step 5: Run them to see them pass, with the prompts' other tests**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_llm_design.py tests/test_llm_intro.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; "All checks passed!".

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/llm/design.py backend/codetortoise/llm/intro.py backend/tests/test_llm_design.py backend/tests/test_llm_intro.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the introduction and the design's parts read the design context's text

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 5: The pipeline reads the context, and runs the design stage alone

**Files:**
- Modify: `backend/codetortoise/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1's `load_context`, `context_text`, `BLOB`; Task 3's `build_design(context=)`; Task 4's
  `intro_prompt(…, context)`, `write_intro(…, context=)`, `design_prompt(…, context)`, `write_design(…, context=)`.
- Produces: module functions `_intro_text(svc, rid, r, ss, cls_text, context, fresh) -> tuple[str, list[str]]`,
  `_design_text(svc, rid, d, r, ss, context, fresh)`, `design_part(svc, rid, x, ss, details, r, per, *, lines,
  read_text, fresh=False) -> tuple[str, list[str]]`, `run_design(rid, svc) -> None`, `_settle(store, rid)`;
  `JobRunner.submit_design(rid)`; `busy()` counts it; the queue's job kind `"design"`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_pipeline.py`:

```python
def _context(svc, rid, **part):
    from codetortoise.design_context import BLOB, DesignContext
    svc.store.put_blob(rid, BLOB, DesignContext(**part).model_dump())


def test_the_design_context_reaches_the_introduction_and_the_design_and_no_other_prompt(fx, tmp_path):
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _one_story_per_cl)
    rid = svc.store.create_review("t", "owner", [101, 102])
    _context(svc, rid, notes="The UART must never drop a byte.")
    run_review(rid, svc)
    read = [p for p in llm.prompts if "The UART must never drop a byte." in p]
    assert len(read) == 2 and "THREAD DETAILS (id" in read[0] and "CHECKS BY CAUSE (id" in read[1]
    d = svc.store.get_blob(rid, "reading_design")
    assert d["context_hash"] and d["concerns"]


def test_a_design_re_run_with_an_unchanged_context_builds_the_same_design(fx, tmp_path):
    from codetortoise.pipeline import run_design
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102, 103, 104, 105])
    run_review(rid, svc)
    before = {s["name"]: (s["status"], s["message"]) for s in svc.store.list_stages(rid)}
    d = svc.store.get_blob(rid, "reading_design")
    run_design(rid, svc)
    assert svc.store.get_blob(rid, "reading_design") == d
    after = {s["name"]: (s["status"], s["message"]) for s in svc.store.list_stages(rid)}
    assert after == before and svc.store.get_review(rid)["status"] == "degraded"   # no LLM: the llm stage degrades


def test_saving_a_context_re_runs_the_design_stage_alone_and_the_review_keeps_its_stories(fx, tmp_path):
    from codetortoise.design_context import HandCondition, HandConditions
    from codetortoise.pipeline import run_design
    svc = make_services(fx, tmp_path)
    llm = _strong(svc, _one_story_per_cl)
    rid = svc.store.create_review("t", "owner", [101, 102])
    run_review(rid, svc)
    stories, stages = svc.store.get_blob(rid, "stories"), svc.store.list_stages(rid)
    asked = len(llm.prompts)
    _context(svc, rid, notes="Never drop a byte.",
             conditions=HandConditions(add=[HandCondition(test="reg == REG_CTRL", function="hal_write"),
                                            HandCondition(test="x == 1")]))
    run_design(rid, svc)
    new = llm.prompts[asked:]
    assert [("THREAD DETAILS (id" in p, "CHECKS BY CAUSE (id" in p) for p in new] == [(True, False), (False, True)]
    assert all("Never drop a byte." in p for p in new)
    d = svc.store.get_blob(rid, "reading_design")
    assert [(g["test"], g["source"]) for g in d["gates"]][:2] == [("reg == REG_CTRL", "context"), ("len > 64", "code")]
    assert d["context_notes"] == ["the condition `x == 1` is not in the changed functions"]
    st = {s["name"]: s for s in svc.store.list_stages(rid)}
    assert st["design"]["status"] == "ok"
    assert st["design"]["message"].endswith("; design text by big; introduction by big; design context: the condition "
                                            "`x == 1` is not in the changed functions")
    assert [s for s in svc.store.list_stages(rid) if s["name"] != "design"] == [s for s in stages if s["name"] != "design"]
    assert svc.store.get_blob(rid, "stories") == stories and svc.store.get_review(rid)["status"] == "done"


def test_a_design_re_run_without_a_reading_says_so_and_leaves_the_status(fx, tmp_path):
    from codetortoise.pipeline import run_design
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101])
    svc.store.reset_stages(rid, ["design"])
    svc.store.set_review_status(rid, "failed")
    run_design(rid, svc)
    assert [(s["status"], s["message"]) for s in svc.store.list_stages(rid)] == [("ok", "no reading to describe")]
    assert svc.store.get_review(rid)["status"] == "failed"


def test_the_queue_marks_a_design_re_run_pending_and_counts_it_as_busy(fx, tmp_path):
    from codetortoise.pipeline import JobRunner
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101])
    svc.store.reset_stages(rid, ["design"])
    runner = JobRunner(svc)                          # not started: the job waits in the queue
    runner.submit_design(rid)
    assert runner.busy() is not None
    assert [(s["status"], s["message"]) for s in svc.store.list_stages(rid)] == [("pending", "queued: the design context changed")]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py -k "design_context or design_re_run or design_stage_alone or busy"`
Expected: FAIL: the first with `assert 0 == 2` (no prompt reads the notes), the others with
`ImportError: cannot import name 'run_design'` or `AttributeError: 'JobRunner' object has no attribute 'submit_design'`.

- [ ] **Step 3: The introduction and the design as module functions**

In `backend/codetortoise/pipeline.py`:

- imports: `from codetortoise.design_context import context_text, load_context`; `from codetortoise.diffmap import
  DiffMap, map_changes` (in place of the plain `map_changes` import); `from codetortoise.layers import LayerModel`;
  `Reading` and `StoryReading` join the `codetortoise.reading` import; `from codetortoise.store import Store` only if ruff asks for it in an annotation (else annotate `store`
  without a type).
- before `def run_review` add:

```python
def _intro_text(svc: Services, rid: int, r: Reading, ss, cls_text: dict[int, str], context: str,
                fresh: bool) -> tuple[str, list[str]]:
    """The strong model's introduction of reading `r` (spec 2026-10-09), written into it: the answer kept for this
    prompt, or a new one, kept when it passes. `context` is the design context's text (spec 2026-11-02 §8). Returns what
    the stage says of it, and its notes."""
    store, strong = svc.store, svc.cfg.llm.strong
    ikey = hashlib.sha256(f"{INTRO_VERSION}|{strong.model}|{intro_prompt(r, ss, cls_text, context)}".encode()).hexdigest()
    icached = store.get_blob(rid, "intro_text")
    said: list[str] = []
    if icached and icached.get("key") == ikey and not fresh:
        iby: str | None = strong.model
        r.whole, r.whole_source = icached["whole"], icached["whole_source"]
        for t in r.threads:
            t.intro, t.intro_source = icached["threads"].get(t.id, (t.intro, t.intro_source))
        r.route, r.route_source = [RouteStep(**s) for s in icached["route"]], icached["route_source"]
    else:
        said, iby = write_intro(svc.strong, svc.ledger, rid, r, ss, cls_text, weak=svc.llm, context=context)
        if not said:
            store.put_blob(rid, "intro_text", {
                "key": ikey, "whole": r.whole, "whole_source": r.whole_source,
                "threads": {t.id: (t.intro, t.intro_source) for t in r.threads},
                "route": [s.model_dump() for s in r.route], "route_source": r.route_source})
    told = (f"; introduction by {iby}" if iby == strong.model else
            f"; introduction by {iby} (the strong model failed)" if iby else "; fixed introduction")
    return told, said


def _design_text(svc: Services, rid: int, d, r: Reading, ss, context: str, fresh: bool):
    """The strong model's parts of design `d` (spec 2026-11-02 §10), written on a copy: the text kept for this prompt,
    or a new answer. Returns what the stage says, its notes and the design."""
    store, strong = svc.store, svc.cfg.llm.strong
    d = d.model_copy(deep=True)
    key = hashlib.sha256(f"{DESIGN_VERSION}|{strong.model}|{design_prompt(d, r, ss, context)}".encode()).hexdigest()
    kept = store.get_blob(rid, "design_text")
    if kept and kept.get("key") == key and not fresh:
        apply_design_text(d, kept)
        return f"; design text by {strong.model}", [], d
    notes, by = write_design(svc.strong, svc.ledger, rid, d, r, ss, weak=svc.llm, context=context)
    if not notes:
        store.put_blob(rid, "design_text", {"key": key, **design_text(d)})
    told = (f"; design text by {by}" if by == strong.model else
            f"; design text by {by} (the strong model failed)" if by else "; fixed design text")
    return told, notes, d


def design_part(svc: Services, rid: int, x, ss, details, r: Reading, per, *, lines, read_text,
                fresh: bool = False) -> tuple[str, list[str]]:
    """The design stage's work on review `rid`'s reading (spec 2026-11-02 §4–§10): the rules' design with the review's
    design context (§8), then the strong model's parts; any failure of the model's part leaves the rules' design exactly
    (§15). Stores blob `reading_design`; returns the stage's message and its notes. A design the rules can't build
    leaves none."""
    store, cfg = svc.store, svc.cfg
    dc = load_context(store, rid)
    try:
        d = build_design(x, ss, details, r, per, lines=lines, read_text=read_text, context=dc)
    except Exception:
        store.replace_blobs(rid, ["reading_design"], [], {})
        raise
    told, notes = "", []
    if svc.strong is not None and cfg.llm.strong is not None and r.threads:
        try:
            told, notes, d = _design_text(svc, rid, d, r, ss, context_text(dc), fresh)
        except Exception as e:  # the rules' design stands
            notes = [f"design text: {type(e).__name__}: {e}"[:200]]
    store.replace_blobs(rid, ["reading_design"], [], {"reading_design": d})
    msg = f"{len(d.components)} component(s), {len(d.walks)} walk-through(s), {len(d.gates)} condition(s)" + told
    return msg, notes
```

- in `run_review`'s `read()`, the introduction's block (from `if r.threads:` with `ikey = …` to its `told += …`)
  becomes:

```python
            if r.threads:
                said, more = _intro_text(svc, rid, r, bs.stories, cls_text, context_text(load_context(store, rid)), fresh)
                notes = notes + more
                told += said
```

- in `run_review`, the closure `design_text_of` goes, and `design()` becomes:

```python
    def design():
        """The design overview (spec 2026-11-02 §4–§10): components, walk-throughs and conditions by rules (R16), then
        the strong model's verdict, concerns, ownership, titles and false cases, with the review's design context."""
        if not cfg.analysis.design:
            drop_design()
            return "off (analysis.design: false)"
        bs, r, per = ctx.get("boards"), ctx.get("reading"), ctx.get("story_readings")
        if bs is None or bs.analysis is None or r is None or per is None:
            drop_design()
            return "no reading to describe"
        msg, notes = design_part(svc, rid, bs.analysis.x, bs.stories, bs.story_details, r, per, lines=ctx.get("lines"),
                                 read_text=ctx.get("read_text"), fresh=fresh)
        if notes:
            raise Degraded(msg + "; " + "; ".join(notes))
        return msg
```

- [ ] **Step 4: What the context names but lacks goes into the message**

In `design_part`, after `msg = …` and before its `return`, add:

```python
    if d.context_notes:
        msg += "; design context: " + "; ".join(d.context_notes)
```

- [ ] **Step 5: The design stage alone**

After `run_review` (before `class AiPool`) add:

```python
def run_design(rid: int, svc: Services) -> None:
    """Run review `rid`'s design stage again, alone (spec 2026-11-02 §8, §18.9), as saving a design context does: the
    introduction is asked again with the context, and the design built again from the reading the last run stored; the
    stories, flows and checks stay as they are. Only the design stage's row changes, and the review's status moves only
    between done and degraded (`_settle`), so its page stays readable meanwhile."""
    from codetortoise.llm.ondemand import _lock
    store = svc.store
    with _lock(rid):
        store.set_stage(rid, "design", "running")
        try:
            msg, notes = _design_again(rid, svc)
            if notes:
                store.set_stage(rid, "design", "degraded", msg + "; " + "; ".join(notes))
            else:
                store.set_stage(rid, "design", "ok", msg)
        except Exception as e:  # recorded as run_review records a stage's failure
            log.error("design re-run of review %s failed: %s", rid, traceback.format_exc())
            store.set_stage(rid, "design", "failed", f"{type(e).__name__}: {e}")
        _settle(store, rid)


def _settle(store, rid: int) -> None:
    """A finished review's status once a stage ran again: done when every stage is ok, else degraded. A review that is
    not finished (queued, running, failed) is left alone: its own run settles it."""
    if store.get_review(rid)["status"] not in ("done", "degraded"):
        return
    st = {s["name"]: s["status"] for s in store.list_stages(rid)}
    store.set_review_status(rid, "done" if all(st.get(s) == "ok" for s in STAGES if s != "finalize") else "degraded")


def _design_again(rid: int, svc: Services) -> tuple[str, list[str]]:
    """The design stage's inputs as the review's last run stored them, and the stage's work on them: the analysis from
    the stored change, the stories and their details, the reading and its stories', the files' lines."""
    store, cfg = svc.store, svc.cfg
    if not cfg.analysis.design:
        store.replace_blobs(rid, ["reading_design"], [], {})
        return "off (analysis.design: false)", []
    ss, raw = boardstore.stories(store, rid), store.get_blob(rid, "reading")
    if ss is None or not raw or not store.get_blob(rid, "changeset"):
        store.replace_blobs(rid, ["reading_design"], [], {})
        return "no reading to describe", []
    r = Reading.model_validate(raw)
    per = {s.id: StoryReading.model_validate(v) for s in ss.stories if (v := store.get_blob(rid, f"story_reading:{s.id}"))}
    details = {s.id: d for s in ss.stories if (d := boardstore.story(store, rid, s.id)) is not None}
    cs = ChangeSet.model_validate(store.get_blob(rid, "changeset"))
    lines = file_lines(cs)                       # as the run made them
    layers = store.get_blob(rid, "layers")
    bctx = BoardContext(cs, DiffMap.model_validate(store.get_blob(rid, "diffmap")),
                        [Facts.model_validate(f) for f in store.get_blob(rid, "facts_before") or []],
                        [Facts.model_validate(f) for f in store.get_blob(rid, "facts_after") or []],
                        ImpactModel.model_validate(store.get_blob(rid, "impact")), store.list_findings(rid),
                        LayerModel.model_validate(layers) if layers else None, cfg.analysis, lambda paths: {},
                        root=canon(str(cfg.workspace.root)))
    x = analyse(bctx).x
    texts: dict[str, str | None] = {}

    def read_text(path: str) -> str | None:
        if path not in texts:
            texts[path] = _read_text(path)
        return texts[path]
    told, notes = "", []
    if svc.strong is not None and cfg.llm.strong is not None and r.threads:
        cls_text = {m.cl: prompt_text(m.description) for m in cs.cls}
        told, notes = _intro_text(svc, rid, r, ss, cls_text, context_text(load_context(store, rid)), fresh=False)
        store.put_blob(rid, "reading", r)
    msg, more = design_part(svc, rid, x, ss, details, r, per, lines=lines, read_text=read_text)
    if told and "; design context: " in msg:     # the introduction's words before what the context lacks
        head, tail = msg.split("; design context: ", 1)
        return head + told + "; design context: " + tail, notes + more
    return msg + told, notes + more
```

- in `JobRunner`: `busy()` counts both kinds:

```python
            if self._pending["review"] or self._pending["design"]:
                return "a review is running in this workspace; try again when it finishes"
```

  after `submit_review` add:

```python
    def submit_design(self, rid: int) -> None:
        """Queue a re-run of review `rid`'s design stage alone (spec 2026-11-02 §8): its design context changed. The
        stage reads pending at once, so the page knows to wait for it."""
        self.svc.store.set_stage(rid, "design", "pending", "queued: the design context changed")
        self._count("design", 1)
        self._q.put(("design", rid))
```

  and `_loop` runs it:

```python
                if kind == "review":
                    run_review(arg[0], self.svc, fresh=arg[1])
                elif kind == "design":
                    run_design(arg, self.svc)
                elif kind == "index" and not self._stop.is_set():
```

- [ ] **Step 6: Run them to see them pass, with the pipeline's other tests**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_tier1_review.py tests/test_web.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; "All checks passed!". If `test_a_design_re_run_with_an_unchanged_context_builds_the_same_design`
fails on a difference, the stored inputs differ from the run's: find which (diff the two designs' parts) and make
`_design_again` read what the run used; never loosen the test's equality.

- [ ] **Step 7: Commit**

```bash
git add backend/codetortoise/pipeline.py backend/tests/test_pipeline.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the pipeline reads the design context, and can run the design stage alone

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 6: The routes: read and save the context; a review started with one

**Files:**
- Modify: `backend/codetortoise/web/app.py` (`ReviewIn`, `create_review`, two new routes)
- Test: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: Task 1's model, `CAP`, `BLOB`, `context_text`, `load_context`, `over_cap`; Task 2's `read_link`,
  `LinkRefused`, `ServerConfig.design_links` (read as `reg.base.server.design_links`); Task 5's
  `runner.submit_design(rid)`.
- Produces: `GET /api/reviews/{rid}/design-context` → `{context, chars, cap, links}`; `PUT
  /api/reviews/{rid}/design-context` (body: a `DesignContext`) → 202 `{queued: true, chars}`; `ReviewIn.design_context:
  str | None`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_web.py`, `InlineRunner` gains (after `submit_review`):

```python
    def submit_design(self, rid):
        from codetortoise.pipeline import run_design
        run_design(rid, self.svc)
```

and append:

```python
def test_the_owner_saves_a_design_context_and_the_design_stage_runs_again(env):
    svc, app, _ = env
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101, 102]}).json()["id"]
    assert owner.get(f"/api/reviews/{rid}/design-context").json() == {
        "context": {"notes": "", "documents": [], "conditions": {"add": [], "remove": []}, "components": []},
        "chars": 0, "cap": 12000, "links": False}
    body = {"notes": "Never drop a byte.", "documents": [{"name": "Design note", "text": "Long writes are refused."}],
            "conditions": {"add": [{"test": "reg == REG_CTRL", "function": "hal_write"}], "remove": []}}
    r = owner.put(f"/api/reviews/{rid}/design-context", json=body)
    assert r.status_code == 202 and r.json() == {"queued": True, "chars": 66}
    got = owner.get(f"/api/reviews/{rid}/design-context").json()
    assert got["context"]["notes"] == "Never drop a byte." and got["chars"] == 66
    d = svc.store.get_blob(rid, "reading_design")
    assert d["gates"][0]["source"] == "context" and d["context_hash"]


def test_only_the_owner_saves_a_design_context_and_anyone_in_the_review_reads_it(env):
    _, app, _ = env
    owner, bob = login(app, "owner"), login(app, "bob")
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    assert bob.put(f"/api/reviews/{rid}/design-context", json={"notes": "mine"}).status_code == 403
    assert bob.get(f"/api/reviews/{rid}/design-context").status_code == 200


def test_a_design_context_over_its_cap_is_refused(env):
    _, app, _ = env
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    assert owner.put(f"/api/reviews/{rid}/design-context", json={"notes": "x" * 12001}).status_code == 422
    r = owner.put(f"/api/reviews/{rid}/design-context",
                  json={"notes": "x" * 6000, "documents": [{"name": "d", "text": "y" * 6000}]})
    assert r.status_code == 422 and r.json()["detail"].startswith("The design context is 12,014 characters")


def test_a_link_is_read_only_when_the_host_lists_its_site(env, monkeypatch):
    from codetortoise.web import app as web
    svc, app, _ = env
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101]}).json()["id"]
    link = {"documents": [{"name": "Design note", "url": "https://wiki.example.com/design/uart.md"}]}
    r = owner.put(f"/api/reviews/{rid}/design-context", json=link)
    assert r.status_code == 422 and r.json()["detail"].startswith("Design note: This server reads no links")
    svc.cfg.server.design_links = ["https://wiki.example.com/design/"]
    seen = []
    monkeypatch.setattr(web, "read_link", lambda url, sites: seen.append((url, sites)) or "Never drop a byte.")
    assert owner.get(f"/api/reviews/{rid}/design-context").json()["links"] is True
    assert owner.put(f"/api/reviews/{rid}/design-context", json=link).status_code == 202
    assert seen == [("https://wiki.example.com/design/uart.md", ["https://wiki.example.com/design/"])]
    doc = owner.get(f"/api/reviews/{rid}/design-context").json()["context"]["documents"][0]
    assert (doc["text"], doc["url"]) == ("Never drop a byte.", "https://wiki.example.com/design/uart.md")
    assert owner.put(f"/api/reviews/{rid}/design-context", json={"documents": [doc]}).status_code == 202
    assert len(seen) == 1                                           # a document with its text is not read again


def test_a_review_started_with_a_design_context_reads_it_from_its_first_run(env):
    svc, app, _ = env
    owner = login(app, "owner")
    rid = owner.post("/api/reviews", json={"cls": [101], "design_context": "  Never drop a byte. "}).json()["id"]
    assert owner.get(f"/api/reviews/{rid}/design-context").json()["context"]["notes"] == "Never drop a byte."
    assert owner.post("/api/reviews", json={"cls": [101], "design_context": "x" * 12001}).status_code == 422
```

Note: `svc.cfg.server` here is the registry's base config when `make_app` builds the registry from `svc`'s config
(`Registry.single`); if `reg.base` is another object, set `design_links` on the object the route reads, found by
reading `Registry.single` — and say so in the ledger.

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web.py -k "design_context or link_is_read"`
Expected: 5 FAIL (404 or 405 on the routes; the creation test with `KeyError` or 404).

- [ ] **Step 3: The routes**

In `backend/codetortoise/web/app.py`:

- imports: `from codetortoise.design_context import BLOB as CONTEXT_BLOB` and `from codetortoise.design_context import
  CAP as CONTEXT_CAP, DesignContext, LinkRefused, context_text, load_context, over_cap, read_link` (one import line
  if it fits in 132 columns).
- `ReviewIn` gains:

```python
    design_context: str | None = Field(default=None, max_length=CONTEXT_CAP)   # notes for the design (spec 2026-11-02 §8)
```

- in `create_review`, between `rid = store.create_review(...)` and `o.ws.runner.submit_review(rid)`:

```python
            if body.design_context and body.design_context.strip():
                store.put_blob(rid, CONTEXT_BLOB, DesignContext(notes=body.design_context.strip()).model_dump())
```

- after the `rerun` route add:

```python
    @app.get("/api/reviews/{rid}/design-context")
    def get_design_context(rid: int, a: Access = Depends(in_review)):
        """The review's design context (spec 2026-11-02 §8), the characters the prompts read of it, its cap, and whether
        this server reads links (its host lists sites in server.design_links)."""
        c = load_context(store, rid)
        return {"context": c, "chars": len(context_text(c)), "cap": CONTEXT_CAP, "links": bool(reg.base.server.design_links)}

    @app.put("/api/reviews/{rid}/design-context", status_code=202)
    def put_design_context(rid: int, body: DesignContext, request: Request, a: Access = Depends(owner_in_review)):
        """Save the review's design context and re-run its design stage alone (§8, §11). A document given as a link with
        no text yet is read now, once, and only from a site the host lists; refused while its workspace isn't ready."""
        sites = list(reg.base.server.design_links)
        docs = []
        for d in body.documents:
            if d.url and not d.text.strip():
                try:
                    d = d.model_copy(update={"text": read_link(d.url, sites)})
                except LinkRefused as e:
                    raise HTTPException(422, f"{d.name}: {e}") from e
            docs.append(d)
        c = body.model_copy(update={"documents": docs})
        if (why := over_cap(c)) is not None:
            raise HTTPException(422, why)
        reg.settle(a.ws)                             # waited for without its guard, as a re-run is
        with reg.guard(a.ws.id):
            a = owner_in_review(in_review(rid, request))     # as it is now: still its owner
            ready(a.ws, wait=False)
            store.put_blob(rid, CONTEXT_BLOB, c.model_dump())
            a.ws.runner.submit_design(rid)
        return {"queued": True, "chars": len(context_text(c))}
```

- [ ] **Step 4: Run them to see them pass, with the web tests**

Run: `cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web.py tests/test_design_context.py && .venv/bin/ruff check codetortoise tests`
Expected: all pass; "All checks passed!".

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/web/app.py backend/tests/test_web.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the owner saves a review's design context, which re-runs its design stage; anyone in the review reads it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 7: The page's side: the context's types and calls, its helpers, and waiting for the design stage

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/reading/types.ts`, `frontend/src/reading/design.ts`,
  `frontend/src/reading/design.test.ts`, `frontend/src/workspace/useReview.ts`
- Create: `frontend/src/workspace/designContext.ts`, `frontend/src/workspace/designContext.test.ts`

**Interfaces:**
- Consumes: Task 6's routes.
- Produces: in `api.ts` the types `ContextDoc`, `HandCondition`, `DesignContext`, `DesignContextView` and the calls
  `api.designContext(id)`, `api.saveDesignContext(id, c)`, `api.createReview(cls, title?, workspace_id?,
  design_context?)`; `ReadingDesign.context_notes: string[]`; `sourceLine(d)` in `reading/design.ts`;
  `EMPTY_CONTEXT`, `componentsText(cs)`, `parseComponents(text)`, `contextChars(c)`, `noteSentence(note)` in
  `workspace/designContext.ts`; `designing: boolean` and `awaitDesign(): void` in the review's data (`useReview`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/workspace/designContext.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { componentsText, contextChars, EMPTY_CONTEXT, noteSentence, parseComponents } from "./designContext";

describe("the design context panel's text (spec 2026-11-02 §8)", () => {
  it("holds the components a line each, a name then its globs", () => {
    const cs = [{ name: "Driver", globs: ["driver/**"] }, { name: "HAL", globs: ["hal/**", "include/hal/**"] }];
    expect(componentsText(cs)).toBe("Driver: driver/**\nHAL: hal/**, include/hal/**");
    expect(parseComponents("Driver: driver/**\n\n HAL :hal/**,  include/hal/** \n")).toEqual({ components: cs, bad: [] });
    expect(parseComponents("Driver\n: x/**\nApp: ")).toEqual({ components: [], bad: ["Driver", ": x/**", "App:"] });
  });

  it("counts the characters the prompts read, as the server does", () => {
    expect(contextChars(EMPTY_CONTEXT)).toBe(0);
    const c = { ...EMPTY_CONTEXT, notes: " Never drop a byte. ", documents: [{ name: "d", text: "y😀", url: null }, { name: "e", text: " ", url: null }] };
    expect(contextChars(c)).toBe("Never drop a byte.".length + 2 + "DOCUMENT d:\n".length + 2);   // the emoji is one character
  });

  it("says a note of the design as a sentence", () => {
    expect(noteSentence("the condition `x == 1` is not in the changed functions"))
      .toBe("The condition `x == 1` is not in the changed functions.");
  });
});
```

In `frontend/src/reading/design.test.ts`, the design import gains `sourceLine`, and the "model's parts" describe gains:

```ts
  it("says where the AI's opening comes from: the stories, and the design context when it read one", () => {
    expect(sourceLine({ context_hash: null })).toBe("AI, from the stories");
    expect(sourceLine({ context_hash: "0123456789ab" })).toBe("AI, from the stories and the design context");
  });
```

- [ ] **Step 2: Run them to see them fail**

Run (from `frontend/`): `npx vitest run src/workspace/designContext.test.ts src/reading/design.test.ts`
Expected: FAIL: `Failed to resolve import "./designContext"`, and `sourceLine is not a function`.

- [ ] **Step 3: Types and calls**

In `frontend/src/api.ts`, after the `AiJob` interface add:

```ts
/** A review's design context (spec 2026-11-02 §8): what the code can't say, as its owner gave it. */
export interface ContextDoc { name: string; text: string; url: string | null }
export interface HandCondition { test: string; function: string | null }
export interface DesignContext {
  notes: string; documents: ContextDoc[]; conditions: { add: HandCondition[]; remove: string[] };
  components: { name: string; globs: string[] }[];
}
/** The context and what its panel needs: the characters the prompts read of it, the cap, whether this server reads links. */
export interface DesignContextView { context: DesignContext; chars: number; cap: number; links: boolean }
```

and in `api`, `createReview` becomes, with two calls after `rerun`:

```ts
  /** A review in workspace `workspace_id` (left out: the only workspace there is), with notes for its design. */
  createReview: (cls: number[], title?: string, workspace_id?: number, design_context?: string) =>
    call<ReviewRow>("POST", "/api/reviews", { workspace_id, cls, title, design_context }),
```

```ts
  designContext: (id: number) => call<DesignContextView>("GET", `/api/reviews/${id}/design-context`),
  saveDesignContext: (id: number, c: DesignContext) =>
    call<{ queued: boolean; chars: number }>("PUT", `/api/reviews/${id}/design-context`, c),
```

In `frontend/src/reading/types.ts`, `ReadingDesign` gains `context_notes: string[];` after `context_hash`.

- [ ] **Step 4: The helpers**

Create `frontend/src/workspace/designContext.ts`:

```ts
/** The design context panel's pure parts (spec 2026-11-02 §8): the components as its text area holds them, the count of
 * what the prompts read, and the design's notes on the context as sentences. */
import type { DesignContext } from "../api";

export const EMPTY_CONTEXT: DesignContext = { notes: "", documents: [], conditions: { add: [], remove: [] }, components: [] };

/** A line per component: its name, a colon, its globs. */
export const componentsText = (cs: DesignContext["components"]): string =>
  cs.map((c) => `${c.name}: ${c.globs.join(", ")}`).join("\n");

/** The text area's components; a line without a name or a glob is `bad`, said back as written (trimmed). */
export function parseComponents(text: string): { components: DesignContext["components"]; bad: string[] } {
  const components: DesignContext["components"] = [], bad: string[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const i = line.indexOf(":"), name = i < 0 ? "" : line.slice(0, i).trim();
    const globs = i < 0 ? [] : line.slice(i + 1).split(",").map((g) => g.trim()).filter(Boolean);
    if (name && globs.length) components.push({ name, globs });
    else bad.push(line);
  }
  return { components, bad };
}

/** The characters the prompts read of the context, counted as the server counts them (`context_text`): the notes, then
 * each document as "DOCUMENT name:" and its text, a blank line between; characters, not UTF-16 units. */
export function contextChars(c: DesignContext): number {
  const parts = [c.notes.trim(), ...c.documents.filter((d) => d.text.trim()).map((d) => `DOCUMENT ${d.name.trim()}:\n${d.text.trim()}`)]
    .filter(Boolean);
  return [...parts.join("\n\n")].length;
}

/** A note of the design on its context ("the condition `x` is not in the changed functions") as a sentence. */
export const noteSentence = (note: string): string => `${note.charAt(0).toUpperCase()}${note.slice(1)}.`;
```

In `frontend/src/reading/design.ts`, after `citeName` add:

```ts
/** Where the AI's opening comes from (§3.1 item 2, §6.1): the stories, and the design context when the model read one. */
export const sourceLine = (d: Pick<ReadingDesign, "context_hash">): string =>
  d.context_hash ? "AI, from the stories and the design context" : "AI, from the stories";
```

- [ ] **Step 5: Waiting for the design stage**

In `frontend/src/workspace/useReview.ts`, after `const missing = …` add:

```ts
/** Whether a review's design stage waits or runs: saving a design context re-runs it alone (spec 2026-11-02 §8). */
const designBusy = (d: ReviewDetail | null | undefined) =>
  !!d?.stages.some((s) => s.name === "design" && (s.status === "pending" || s.status === "running"));
```

and after the effect that opens the events stream (the one ending `}, [id, status, stream, loadResults, loadDetail]);`)
add:

```ts
  // a design context saved re-runs the design stage alone (spec 2026-11-02 §8): the review stays done, so no stream
  // tells of it. The stage is polled while it waits or runs — from the save on (`awaitDesign`), as it may be done before
  // the first look — and the reading (its design and its lead) loads again once it is done.
  const [designWait, setDesignWait] = useState(false);
  const designing = designWait || designBusy(detail);
  const awaitDesign = useCallback(() => setDesignWait(true), []);
  useEffect(() => {
    if (!designing || !status || !TERMINAL.has(status)) return;
    const t = setInterval(() => { loadDetail().then((d) => { if (d && !designBusy(d)) setDesignWait(false); }); }, 1500);
    return () => clearInterval(t);
  }, [designing, status, loadDetail]);
  const wasDesigning = useRef(false);
  useEffect(() => {
    if (wasDesigning.current && !designing) loadReading();
    wasDesigning.current = designing;
  }, [designing, loadReading]);
```

`designing` and `awaitDesign` join the returned object and its dependency list (after `ready`).

- [ ] **Step 6: Run them to see them pass**

Run (from `frontend/`): `npx vitest run src/workspace/designContext.test.ts src/reading/design.test.ts && npx tsc --noEmit`
Expected: all pass; tsc clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api.ts frontend/src/reading/types.ts frontend/src/reading/design.ts frontend/src/reading/design.test.ts frontend/src/workspace/designContext.ts frontend/src/workspace/designContext.test.ts frontend/src/workspace/useReview.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the page reads and saves a design context, and waits for the design stage it re-runs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 8: The panel, the field at creation, and the opening's source line

**Files:**
- Modify: `frontend/src/workspace/reviewMenu.ts`, `frontend/src/workspace/reviewMenu.test.ts`,
  `frontend/src/workspace/ReviewMenu.tsx`, `frontend/src/workspace/Overview.tsx`, `frontend/src/pages/Reviews.tsx`,
  `frontend/src/workspace/workspace.css`, `frontend/e2e/fake_llm.py`
- Create: `frontend/src/workspace/DesignContextPanel.tsx`, `frontend/e2e/design-context.spec.ts`

**Interfaces:**
- Consumes: Task 7's types, calls and helpers; `useWs`, `useViewer`, `Ticks`, `errorText`.
- Produces: the menu item `context` ("Design context…"); `DesignContextPanel({ style })`, a dialog named "Design
  context" with the labelled fields "Notes", "Add a file", "Link", "Condition, as the code writes it", "In the function
  (optional)", "Components", the buttons "Add the link", "Add the condition", "Save", `.dc-count`, `.dc-notes`, a status
  line; the creation form's "Design context (optional)".

- [ ] **Step 1: Write the failing tests**

In `frontend/src/workspace/reviewMenu.test.ts`, every expected list of ids with `reading: true` gains `"context"` after
`"keys"` (for example `["help", "keys", "rerun"]` becomes `["help", "keys", "context", "rerun"]`, and
`["help", "keys"]` becomes `["help", "keys", "context"]`), the labels' list gains `"Design context…"` after
`"Single-key shortcuts"`, and the plain-item check becomes
`toEqual([undefined, undefined, undefined])`. Run it to see those fail before Step 3.

Create `frontend/e2e/design-context.spec.ts`:

```ts
import { devices, expect } from "@playwright/test";
import { login, reviewMenu, sideways, startReview, STRONG, test } from "./helpers";

// e2e/serve-strong.sh's fake strong model (e2e/fake_llm.py) says in its verdict when the prompt carries a design context.
const NOTES = "The UART must never drop a byte: a write that is too long is refused whole, and its sender is told.";

async function openPanel(page: import("@playwright/test").Page) {
  await (await reviewMenu(page)).getByRole("menuitem", { name: "Design context…" }).click();
  const panel = page.getByRole("dialog", { name: "Design context" });
  await expect(panel).toBeVisible();
  return panel;
}

test.describe("the design context", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("the owner gives the review a design context; the design stage runs again and the opening says it read it", async ({ page }) => {
    await startReview(page);
    const verdict = page.locator(".ov-top .dz-verdict");
    await expect(verdict.locator(".dz-src")).toHaveText("AI, from the stories");
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    await expect(panel.locator(".dc-count")).toHaveText(`${NOTES.length} of 12,000 characters`);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByRole("status")).toContainText("Saved");
    await expect(verdict.locator(".dz-src")).toHaveText("AI, from the stories and the design context", { timeout: 30_000 });
    await expect(verdict.locator("p.ai-text")).toContainText("against its design context");
    await expect(page.getByRole("region", { name: "What it must get right" }).locator(".dz-src"))
      .toHaveText("AI, from the stories and the design context");
  });

  test("a condition added by hand leads the condition fold, and one the code lacks is said in the panel", async ({ page }) => {
    await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Condition, as the code writes it").fill("reg == REG_CTRL");
    await panel.getByLabel("In the function (optional)").fill("hal_write");
    await panel.getByRole("button", { name: "Add the condition" }).click();
    await panel.getByLabel("Condition, as the code writes it").fill("x == 1");
    await panel.getByRole("button", { name: "Add the condition" }).click();
    await expect(panel.locator(".dc-added li")).toHaveCount(2);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("heading", { name: /^Writes to any other register · / })).toBeVisible({ timeout: 30_000 });
    await expect(panel.locator(".dc-notes li")).toHaveText(["The condition x == 1 is not in the changed functions."]);
  });

  test("someone else in the review reads the design context but has nothing to change it with", async ({ page, browser }) => {
    const base = await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByRole("status")).toContainText("Saved");
    const context = await browser.newContext({ baseURL: STRONG });
    const other = await context.newPage();
    await login(other, "bob");
    await other.goto(base);
    const theirs = await openPanel(other);
    await expect(theirs.locator(".dc-read")).toContainText(NOTES);
    await expect(theirs.getByRole("textbox")).toHaveCount(0);
    await expect(theirs.getByRole("button", { name: "Save" })).toHaveCount(0);
    await context.close();
  });

  test("a review started with a design context opens with the opening that read it", async ({ page }) => {
    await login(page);
    await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
    await page.getByLabel("Design context (optional)").fill(NOTES);
    await page.getByRole("button", { name: "Start review" }).click();
    await expect(page.locator(".ov-top .dz-verdict .dz-src")).toHaveText("AI, from the stories and the design context",
                                                                          { timeout: 60_000 });
  });
});

test.describe("the design context on a phone", () => {
  test.use({ baseURL: STRONG, viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
             deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the panel fits the phone's width and nothing scrolls sideways", async ({ page }) => {
    await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    const box = await panel.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(devices["iPhone 13"].viewport.width);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});
```

- [ ] **Step 2: The fake strong model reads the context**

In `frontend/e2e/fake_llm.py`, before `def design(` add:

```python
FALSE_CASES = {"len > 64": "Writes that fit (64 bytes or less)", "reg == REG_CTRL": "Writes to any other register"}
```

and in `design(user)`:

- the gates are read with their tests: `walks, gates = re.findall(r"^(W\d+) \| ", user, re.M), re.findall(r"^(G\d+) \| (.+?) \| ", user, re.M)`;
- the verdict says when it read a context:

```python
    read = "DESIGN CONTEXT (from the review's owner):" in user
    verdict = ("The change holds together against its design context, but one new result goes unchecked. "
               if read else "The change holds together, but one new result goes unchecked. ")
```

  with `"verdict": verdict + "Settle whether `logger_flush` must handle the new -2.",`;
- and the conditions: `"conditions": [{"id": g, "false_case": FALSE_CASES.get(test.strip(), "When the test does not hold")} for g, test in gates]`.

- [ ] **Step 3: Run the e2e tests to see them fail**

Run (from `frontend/`): `npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/design-context.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: all 5 FAIL: no "Design context…" item in the menu, and no "Design context (optional)" field.

- [ ] **Step 4: The menu item**

In `frontend/src/workspace/reviewMenu.ts`, `MenuId` gains `"context"`, and `menuItems` pushes it after the keys item:

```ts
  if (m.reading) {
    out.push({ id: "help", label: "How to read this page" });
    out.push({ id: "keys", label: "Single-key shortcuts", checked: m.keys });
    out.push({ id: "context", label: "Design context…" });
  }
```

In `frontend/src/workspace/ReviewMenu.tsx`: `import DesignContextPanel from "./DesignContextPanel";`; the panel state
becomes `useState<"drift" | "notes" | "help" | "rerun" | "context" | null>(null)`; in `pick`, the first line's ids
gain `"context"`: `if (id === "drift" || id === "notes" || id === "help" || id === "context") { setPanel(id); return; }`;
and after the help panel add `{panel === "context" && <DesignContextPanel style={at} />}`.

- [ ] **Step 5: The panel**

Create `frontend/src/workspace/DesignContextPanel.tsx`:

```tsx
import { type ChangeEvent, type CSSProperties, useEffect, useState } from "react";
import { api, type DesignContext, type DesignContextView, errorText } from "../api";
import { useViewer } from "../viewer";
import { useWs } from "./context";
import { componentsText, contextChars, EMPTY_CONTEXT, noteSentence, parseComponents } from "./designContext";
import { Ticks } from "./NameText";

/** The design context panel (spec 2026-11-02 §8): what the code can't say — notes, documents, conditions added or left
 * out by hand, and a choice of components. The owner edits and saves it, which re-runs the design stage alone; anyone
 * else in the review reads it. The AI's opening reads it; the checks never do. */
export default function DesignContextPanel({ style }: { style: CSSProperties }) {
  const ws = useWs(), d = ws.data, me = useViewer(), owner = !!me?.is_owner;
  const [view, setView] = useState<DesignContextView | null>(null);
  const [c, setC] = useState<DesignContext>(EMPTY_CONTEXT);
  const [comps, setComps] = useState("");
  const [link, setLink] = useState("");
  const [test, setTest] = useState("");
  const [fn, setFn] = useState("");
  const [error, setError] = useState("");
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.designContext(d.id).then((v) => { setView(v); setC(v.context); setComps(componentsText(v.context.components)); },
                                 (e) => setError(errorText(e, "The design context could not be loaded.")));
  }, [d.id]);
  const design = d.reading?.design ?? null;
  const found = (design?.gates ?? []).filter((g) => g.source === "code");
  const parsed = parseComponents(comps), chars = contextChars(c), cap = view?.cap ?? 12000;
  const set = (part: Partial<DesignContext>) => { setC({ ...c, ...part }); setSaid(""); };
  const conds = c.conditions;
  const addFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) file.text().then((text) => set({ documents: [...c.documents, { name: file.name, text, url: null }] }));
  };
  const save = () => {
    setBusy(true);
    setError("");
    api.saveDesignContext(d.id, { ...c, components: parsed.components })
      .then(() => { setSaid("Saved. The design stage runs again; the overview changes when it is done."); d.awaitDesign(); })
      .catch((e) => setError(errorText(e, "The design context could not be saved.")))
      .finally(() => setBusy(false));
  };
  return (
    <div className="rm-panel dc-panel" role="dialog" aria-label="Design context" tabIndex={-1} style={style}>
      <h2>Design context</h2>
      <p className="muted small">What the code can't say: what the change is for, the documents behind it, the conditions
        that matter. The AI's opening reads it; the checks never do.</p>
      {error && <div className="banner error" role="alert">{error}</div>}
      {!view ? !error && <p className="muted">Loading…</p> : !owner ? (
        <div className="dc-read">
          {view.context.notes ? <p className="dc-text">{view.context.notes}</p> : <p className="muted">No notes.</p>}
          {view.context.documents.map((doc) => <p key={doc.name} className="small">Document: {doc.name}</p>)}
          {view.context.conditions.add.map((h) => <p key={h.test} className="small">Condition added: <code>{h.test}</code></p>)}
          {view.context.conditions.remove.map((t) => <p key={t} className="small">Condition left out: <code>{t}</code></p>)}
          {view.context.components.length > 0 && <pre className="small">{componentsText(view.context.components)}</pre>}
        </div>
      ) : (
        <div className="dc-form">
          <label>Notes<textarea rows={5} value={c.notes} onChange={(e) => set({ notes: e.target.value })} /></label>
          <div className="dc-docs">
            {c.documents.length > 0 && <ul>{c.documents.map((doc, i) => (
              <li key={`${doc.name}-${i}`}>{doc.name}{doc.url && !doc.text ? " (read when saved)" : ` · ${[...doc.text].length} characters`}
                {" "}<button className="link" onClick={() => set({ documents: c.documents.filter((_, k) => k !== i) })}>Remove</button></li>
            ))}</ul>}
            <label>Add a file<input type="file" accept=".md,.markdown,.txt,text/plain,text/markdown" onChange={addFile} /></label>
            {view.links && <div className="dc-row">
              <label>Link<input type="url" value={link} placeholder="https://" onChange={(e) => setLink(e.target.value)} /></label>
              <button disabled={!link.trim()} onClick={() => { set({ documents: [...c.documents, { name: link.trim(), text: "", url: link.trim() }] }); setLink(""); }}>
                Add the link</button>
            </div>}
          </div>
          <div className="dc-conds">
            <h3>Conditions</h3>
            {found.length > 0 && <ul>{found.map((g) => (
              <li key={g.id}><code>{g.test}</code>{" "}
                <button className="link" onClick={() => set({ conditions: { ...conds, remove: [...conds.remove, g.test] } })}>Leave out</button></li>
            ))}</ul>}
            {conds.remove.length > 0 && <ul>{conds.remove.map((t) => (
              <li key={t}>Left out: <code>{t}</code>{" "}
                <button className="link" onClick={() => set({ conditions: { ...conds, remove: conds.remove.filter((x) => x !== t) } })}>Put back</button></li>
            ))}</ul>}
            {conds.add.length > 0 && <ul className="dc-added">{conds.add.map((h, i) => (
              <li key={`${h.test}-${i}`}>Added: <code>{h.test}</code>{h.function && <> in <code>{h.function}</code></>}{" "}
                <button className="link" onClick={() => set({ conditions: { ...conds, add: conds.add.filter((_, k) => k !== i) } })}>Remove</button></li>
            ))}</ul>}
            <div className="dc-row">
              <label>Condition, as the code writes it<input value={test} placeholder="len > 64" onChange={(e) => setTest(e.target.value)} /></label>
              <label>In the function (optional)<input value={fn} onChange={(e) => setFn(e.target.value)} /></label>
              <button disabled={!test.trim()} onClick={() => {
                set({ conditions: { ...conds, add: [...conds.add, { test: test.trim(), function: fn.trim() || null }] } });
                setTest(""); setFn("");
              }}>Add the condition</button>
            </div>
            {(design?.context_notes.length ?? 0) > 0 && <ul className="dc-notes">{design!.context_notes.map((n) => (
              <li key={n}><Ticks text={noteSentence(n)} /></li>
            ))}</ul>}
          </div>
          <label>Components<textarea rows={4} value={comps} placeholder={"Driver: driver/**\nHAL: hal/**, include/hal/**"}
                                     onChange={(e) => { setComps(e.target.value); setSaid(""); }} /></label>
          <p className="muted small">A line each: a name, a colon, and the files it holds as globs. None: the workspace's own.
            {parsed.bad.length > 0 && <> Not read: {parsed.bad.join("; ")}.</>}</p>
          <p className={`dc-count small${chars > cap ? " over" : ""}`}>{chars.toLocaleString("en-US")} of {cap.toLocaleString("en-US")} characters</p>
          <div className="dc-acts">
            <button onClick={save} disabled={busy || chars > cap || parsed.bad.length > 0}>{busy ? "Saving…" : "Save"}</button>
            <span role="status" className="muted small">{d.designing && said ? "Saved. The design stage is running…" : said}</span>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: The source line and the creation field**

In `frontend/src/workspace/Overview.tsx`: the design import gains `sourceLine`; in `Verdict` and in `Concerns`, each
`<p className="dz-src">AI, from the stories</p>` becomes `<p className="dz-src">{sourceLine(d)}</p>`; and the
`Verdict` and `Concerns` doc comments' "the stories alone until a design context comes (phase 3)" / "AI, from the
stories" become "the stories, and the design context when the model read one".

In `frontend/src/pages/Reviews.tsx`'s `StartReview`: a state `const [context, setContext] = useState("");`; the call
becomes `api.createReview(cls, title.trim() || undefined, target, context.trim() || undefined)`; and after the Title
label add:

```tsx
      <label>Design context (optional)
        <textarea rows={3} value={context} onChange={(e) => setContext(e.target.value)}
                  placeholder="What the change is for, and what the code can't say" />
      </label>
      <div className="hint">The AI's opening reads it; checks never do. More can be added later from the review's ⋯ menu.</div>
```

- [ ] **Step 7: Style it**

Append to `frontend/src/workspace/workspace.css`:

```css
/* the design context panel (spec 2026-11-02 §8): an rm-panel with a form */
.dc-panel label { display: block; margin: 8px 0 0; font-size: 13px; font-weight: 600; }
.dc-panel textarea, .dc-panel input:not([type="file"]) { display: block; width: 100%; box-sizing: border-box; margin-top: 4px;
  font: 13px var(--sans); }
.dc-panel input[type="file"] { display: block; margin-top: 4px; max-width: 100%; }
.dc-panel h3 { margin: 12px 0 0; font-size: 13px; }
.dc-panel ul { margin: 4px 0 0; overflow-wrap: anywhere; }
.dc-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; }
.dc-row label { flex: 1 1 160px; }
.dc-notes li { color: var(--warn); }
.dc-count { margin: 8px 0 0; color: var(--muted); }
.dc-count.over { color: var(--bad); font-weight: 600; }
.dc-acts { display: flex; gap: 10px; align-items: center; margin-top: 8px; }
.dc-read .dc-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.dc-read pre { white-space: pre-wrap; overflow-wrap: anywhere; }
```

- [ ] **Step 8: Run every test that reads the menu, the overview or the creation form**

Run (from `frontend/`): `npx tsc --noEmit && npx vitest run && npm run build >/dev/null && mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test e2e/design-context.spec.ts e2e/design-text.spec.ts e2e/header-menu.spec.ts e2e/landing.spec.ts e2e/workspace-tier1.spec.ts --retries=0; rm -rf ../.pwtmp`
Expected: all pass. (A header-menu test that counts the menu's items gains "Design context…" in its expected list:
change that list, and ledger it.)

- [ ] **Step 9: Commit**

```bash
git add frontend/src/workspace/reviewMenu.ts frontend/src/workspace/reviewMenu.test.ts frontend/src/workspace/ReviewMenu.tsx frontend/src/workspace/DesignContextPanel.tsx frontend/src/workspace/Overview.tsx frontend/src/pages/Reviews.tsx frontend/src/workspace/workspace.css frontend/e2e/fake_llm.py frontend/e2e/design-context.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat: the design context panel in the review menu, the field at creation, and the opening's source line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```

---

### Task 9: The README, and every suite

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: the README's account of the design context and `server.design_links`; every suite green.

- [ ] **Step 1: Say it in the README**

In `README.md`, after the paragraph that begins "With a strong model, the design stage also asks it once" add:

```markdown
A review's owner can give it a **design context**: what the code can't say, such as what the change is for, the
documents behind it (pasted, from a file, or a link), the conditions that matter (added or left out by hand) and a
choice of components. It is entered in the review's ⋯ menu ("Design context…") or when starting the review, and
saving it runs the design stage again on its own. The AI's opening and the design's parts read it; stories, flows and
checks never do, so it can't change what is flagged. It holds at most 12 000 characters. The server reads a link only
from the sites its host lists under `server.design_links` in tortoise.yaml (none by default), so a workspace owner can't
make it fetch other addresses on its network; it follows no redirect and reads at most 1 MB of text, markdown or a web
page.
```

- [ ] **Step 2: Run every suite**

Run:

```bash
cd backend && TMPDIR=$PWD/../.superpowers/pytmp .venv/bin/python -m pytest -q -p no:cacheprovider > ../.superpowers/pytest.log 2>&1; tail -3 ../.superpowers/pytest.log; .venv/bin/ruff check codetortoise tests
cd ../frontend && npm run build > /dev/null && npx vitest run 2>&1 | tail -4
mkdir -p ../.pwtmp && TMPDIR="$PWD/../.pwtmp" TORTOISE_CMD="$PWD/../backend/.venv/bin/codetortoise" npx playwright test --retries=0 > ../.superpowers/e2e.log 2>&1; tail -5 ../.superpowers/e2e.log; rm -rf ../.pwtmp
```

Expected: pytest all pass; ruff "All checks passed!"; the build clean; vitest all pass; Playwright all pass. A failure
here is a finding about this branch: debug it (superpowers:systematic-debugging), fix it under a failing test, and
ledger the ruling.

- [ ] **Step 3: Commit**

```bash
git add README.md
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "docs: the README tells of the design context and the sites a server reads links from

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01M17gxTwmjM6Qhg9xMppJuH"
```
