"""FastAPI application: JSON API under /api, React SPA everywhere else."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from codetortoise import boardstore, filestore
from codetortoise.config import program_settings
from codetortoise.design_context import BLOB as CONTEXT_BLOB
from codetortoise.design_context import CAP as CONTEXT_CAP
from codetortoise.design_context import DesignContext, LinkRefused, context_text, load_context, over_cap, read_link
from codetortoise.health import HealthReport
from codetortoise.impact import ImpactModel, Node
from codetortoise.init_config import scan
from codetortoise.llm import ondemand, request_log, tortoise
from codetortoise.names import cited, names, neighbours
from codetortoise.paths import canon
from codetortoise.pipeline import end_design_reruns
from codetortoise.provenance import tag_board
from codetortoise.reading import Check, Reading, headline_from, with_marks
from codetortoise.services import Services
from codetortoise.sinks import marks, set_mark
from codetortoise.swarm import SwarmError
from codetortoise.tidy import tidy
from codetortoise.vcs.p4runner import P4Error, P4Runner
from codetortoise.vcs.source import SourceBinary, SourceNotAllowed, SourceTooLarge
from codetortoise.workspaces import Conflict, Gone, Invalid, Registry, Workspace, server_of

COOKIE = "ct_session"
STATIC = Path(__file__).parent / "static"
TERMINAL = {"done", "degraded", "failed"}
log = logging.getLogger(__name__)


class LoginRejected(Exception):
    """Raised by an authenticator with a message that is safe to show (never reveals whether a user exists)."""


class LoginIn(BaseModel):
    server: str | None = None        # the Perforce server to sign in to (spec 2026-10-31 §7); may be left out with one
    user: str
    password: str = ""


class ReviewIn(BaseModel):
    workspace_id: int | None = None  # may be left out on a server of one workspace
    cls: list[int] = Field(min_length=1)
    title: str | None = None
    design_context: str | None = Field(default=None, max_length=CONTEXT_CAP)   # notes for the design (spec 2026-11-02 §8)


class FindingStateIn(BaseModel):
    state: Literal["open", "ack", "dismissed"]


class ExplainIn(BaseModel):
    kind: Literal["flow", "finding", "file", "story"]
    target: str = Field(min_length=1, max_length=2000)


class BudgetIn(BaseModel):
    budget: int = Field(ge=0, le=1_000_000)


class RoundsIn(BaseModel):
    rounds: int = Field(ge=1, le=50)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    anchor_kind: Literal["line", "function", "finding", "chapter", "review", "story", "flow", "file", "check"]
    anchor: dict = Field(default_factory=dict)
    parent_id: int | None = None


class CommentPatch(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    resolved: bool | None = None


class SwarmPostIn(BaseModel):
    confirm_repeat: bool = False


class KeysIn(BaseModel):
    keys: list[str]


class WorkspaceIn(BaseModel):
    """A workspace as the Workspaces page sends it (spec 2026-10-31 §9)."""
    name: str
    vcs: Literal["p4", "git"] = "p4"
    p4port: str | None = None
    client: str | None = None
    p4user: str
    root: str
    compile_commands: str = "auto"       # "auto", a path, or several (one per line)
    build_root: str | None = None
    swarm_url: str | None = None
    settings: str = ""                   # YAML: tortoise.yaml's toolchain, targets and analysis keys

    def fields(self) -> dict:
        """The workspaces table's columns: blanks unset, the root normalised, the compile database as JSON."""
        def opt(v: str | None) -> str | None:
            return (v.strip() or None) if v is not None else None
        paths = [line.strip() for line in self.compile_commands.splitlines() if line.strip()]
        cc = "auto" if paths in ([], ["auto"]) else paths[0] if len(paths) == 1 else paths
        return {"name": self.name.strip(), "vcs": self.vcs, "p4port": opt(self.p4port), "client": opt(self.client),
                "p4user": self.p4user.strip(), "root": os.path.normpath(self.root.strip()) if self.root.strip() else "",
                "compile_commands": json.dumps(cc), "build_root": opt(self.build_root),
                "swarm_url": opt(self.swarm_url), "settings": self.settings}


class DetectIn(BaseModel):
    root: str


def validation_text(errors: list[dict]) -> str:
    """A request the models refused, as sentences naming each field and its limit (at most three): never the value sent,
    which may be pages of the sender's own text (final review I4)."""
    def field(loc: tuple) -> str:
        parts = loc[1:] if loc and loc[0] in ("body", "query", "path") else loc
        return " ".join(f"#{p + 1}" if isinstance(p, int) else str(p).replace("_", " ") for p in parts) or "the request"

    def sentence(e: dict) -> str:
        kind, ctx, name = e.get("type", ""), e.get("ctx") or {}, field(tuple(e.get("loc", ())))
        if kind == "json_invalid":
            return "the request is not valid JSON"
        if kind == "string_too_long":
            return f"{name} is longer than {ctx['max_length']:,} characters"
        if kind == "too_long":
            return f"{name} holds more than {ctx['max_length']:,} items"
        if kind == "string_too_short":
            return f"{name} is empty" if ctx.get("min_length") == 1 else f"{name} is shorter than {ctx['min_length']:,} characters"
        if kind == "too_short":
            n = ctx["min_length"]
            return f"{name} needs at least {n:,} item{'' if n == 1 else 's'}"
        if kind == "missing":
            return f"{name} is missing"
        return f"{name}: {e.get('msg', 'not accepted')}"
    text = "; ".join(sentence(e) for e in errors[:3]) or "the request was not accepted"
    return text[0].upper() + text[1:] + ("" if text.endswith(".") else ".")


RERUNNING = "the review is being re-run"


class SignInRequired(Exception):
    """A review on a Perforce server the session has no sign-in on (spec 2026-10-31 §7): 401 naming the server, so the
    UI can offer that server's sign-in."""

    def __init__(self, server: str):
        super().__init__(server)
        self.server = server


@dataclass
class Access:
    """A review, its workspace and the session's sign-in on that workspace's server: who acts inside it (§7)."""
    review: dict
    ws: Workspace
    user: str

    @property
    def rid(self) -> int:
        return self.review["id"]

    @property
    def is_owner(self) -> bool:
        return self.user == self.ws.owner


@dataclass
class Owned:
    """A workspace, acted on by its owner (§7)."""
    ws: Workspace
    user: str
    logins: dict[str, str]


def create_app(reg: Registry, authenticate) -> FastAPI:
    """authenticate(server, user, password) -> ticket str on success, None on failure."""
    app = FastAPI(title="CodeTortoise")
    app.state.registry = reg
    store = reg.store
    # work a stopped server left unfinished: answers can't resume, so end them (spec 2026-10-03 §5); once per server
    store.end_pending_ai_replies("I couldn't answer: CodeTortoise restarted before the answer was finished. Ask again.")
    end_design_reruns(store)                   # a design re-run the stopped queue held (final review I3)
    reg.ledger.fail_running()
    reg.ledger.prune()                         # logged requests past llm.request_log_days

    @app.exception_handler(RequestValidationError)
    async def not_valid(request: Request, e: RequestValidationError):
        return JSONResponse({"detail": validation_text(list(e.errors()))}, status_code=422)

    @app.exception_handler(SignInRequired)
    async def sign_in_required(request: Request, e: SignInRequired):
        return JSONResponse({"detail": "sign in required", "server": e.server}, status_code=401)

    def logins_of(request: Request) -> dict[str, str]:
        """The session's sign-ins, server -> user."""
        got = store.session_logins(request.cookies.get(COOKIE))
        if not got:
            raise HTTPException(401, "login required")
        return got

    def in_review(rid: int, request: Request) -> Access:
        """The review, read as the session's sign-in on its workspace's server (§7). Without that sign-in — or with no
        session at all, as for a link opened in a new browser — the 401 names the server, so its sign-in opens in place
        (§9)."""
        return review_access(rid, store.session_logins(request.cookies.get(COOKIE)) or {})

    def review_access(rid: int, logins: dict[str, str]) -> Access:
        """The review as the sign-ins `logins` may read it: 404 when it doesn't exist, 401 naming its server without a
        sign-in there."""
        r = store.get_review(rid)
        ws = reg.for_review(r) if r is not None else None
        if ws is None:
            raise HTTPException(404, "review not found")
        user = logins.get(ws.server)
        if user is None:
            raise SignInRequired(ws.server)
        return Access(r, ws, user)

    def owner_in_review(a: Access = Depends(in_review)) -> Access:
        if not a.is_owner:
            raise HTTPException(403, "owner only")
        return a

    def owned(wid: int, logins: dict[str, str] = Depends(logins_of)) -> Owned:
        """A workspace its owner acts on: 404 off the session's servers, 403 for anyone else (§7)."""
        ws = reg.get(wid)
        if ws is None or ws.server not in logins:
            raise HTTPException(404, "workspace not found")
        if logins[ws.server] != ws.owner:
            raise HTTPException(403, "owner only")
        return Owned(ws, logins[ws.server], logins)

    def hosts(logins: dict[str, str]) -> bool:
        """Signed in as the owner of the seed, the workspace tortoise.yaml names: the owner of this server."""
        seed = reg.seed()
        return seed is not None and logins.get(seed.server) == seed.owner

    def managed(wid: int, logins: dict[str, str] = Depends(logins_of)) -> Owned:
        """Edit or remove a workspace: its owner (§7), or the owner of the seed, so that one saved with a server or user
        nobody can sign in as (§11) can still be fixed or removed."""
        ws = reg.get(wid)
        if ws is not None and hosts(logins):
            return Owned(ws, logins.get(ws.server, ""), logins)
        return owned(wid, logins)

    def bundle(ws: Workspace, wait: bool = True) -> Services:
        """A workspace's bundle (waited for while it is still being built, right after startup, unless `wait` is False:
        under its guard); 409 with the reason while it has none."""
        if wait:
            reg.settle(ws)
        if ws.svc is None:
            raise HTTPException(409, f"the workspace {ws.name} is not loaded: {ws.reason}")
        return ws.svc

    def ready(ws: Workspace, wait: bool = True) -> Services:
        """A workspace's bundle when its checks pass; 409 with the reason otherwise (§11). Waited for as bundle() is."""
        if wait:
            reg.settle(ws)
        if not ws.ready:
            raise HTTPException(409, f"the workspace {ws.name} is not ready: {ws.reason}; see its Health")
        return ws.svc

    def ws_ref(ws: Workspace) -> dict:
        return {"id": ws.id, "name": ws.name, "server": ws.server}

    # ---- sign-in: one per Perforce server (spec 2026-10-31 §7) ----------------------
    @app.get("/api/servers")
    def servers(request: Request):
        """The Perforce servers of all workspaces, each with the session's user there or null; open to the sign-in
        page."""
        logins = store.session_logins(request.cookies.get(COOKIE)) or {}
        return [{"server": s, "user": logins.get(s)} for s in reg.servers()]

    @app.post("/api/login")
    def login(body: LoginIn, request: Request, response: Response):
        known = reg.servers()
        server = body.server if body.server is not None else (known[0] if len(known) == 1 else None)
        if server is None:
            raise HTTPException(422, "choose a Perforce server")
        if server not in known:
            raise HTTPException(422, f"no workspace is on {server}")
        try:
            ticket = authenticate(server, body.user, body.password)
        except LoginRejected as e:
            raise HTTPException(401, str(e)) from e
        if ticket is None:
            raise HTTPException(401, "invalid credentials")
        if body.user in reg.owners(server):
            reg.keep_ticket(server, body.user, ticket)
        token = store.renew_session(request.cookies.get(COOKIE))     # a new token at each sign-in (no fixation)
        store.add_login(token, server, body.user)
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 86400,
                            secure=reg.base.server.tls_cert is not None)
        return {"server": server, "user": body.user}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        tok = request.cookies.get(COOKIE)
        if tok:
            store.delete_session(tok)
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(logins: dict[str, str] = Depends(logins_of)):
        """The session's sign-ins and the workspaces it owns (§8)."""
        return {"logins": [{"server": s, "user": u} for s, u in sorted(logins.items())],
                "owner_of": sorted(w.id for w in reg.all() if logins.get(w.server) == w.owner)}

    # ---- a workspace's health, index and shared sinks (owner; spec 2026-10-31 §8) -----
    @app.get("/api/workspaces/{wid}/health")
    def health(o: Owned = Depends(owned)):
        """Its checks run again, with a sample parse per toolchain group (its Health page)."""
        rep = reg.recheck(o.ws, deep=True)
        ws = reg.get(o.ws.id) or o.ws                # Recheck may have built it again (final review of branch
                                                     # deferred-minors-2, I2)
        if rep is None:                              # no bundle, or its checks broke: why is the one check shown
            rep = HealthReport(checks=[{"name": "workspace", "ok": False, "hard": True, "detail": ws.reason or ""}],
                               ready=False)
        return {**rep.model_dump(), "index_building": ws.runner.index_building if ws.runner else False}

    @app.post("/api/workspaces/{wid}/index/rebuild")
    def rebuild_index(wid: int, o: Owned = Depends(owned)):
        reg.settle(o.ws)                             # waited for without its guard (review of branch minors, M3)
        with reg.guard(wid):                         # into its queue as it is once no edit of it runs (final review M2)
            o = owned(wid, o.logins)
            bundle(o.ws, wait=False)
            o.ws.runner.submit_index()
        return {"queued": True}

    # ---- reviews ------------------------------------------------------------
    def reading_view(rid: int) -> dict | None:
        raw = store.get_blob(rid, "reading")
        if not raw:
            return None
        return with_marks(Reading.model_validate(raw), store.list_marks(rid), store.list_findings(rid),
                          boardstore.stories(store, rid))

    def review_headline(rid: int) -> dict | None:
        """The Reviews list's headline from the small `reading_head` blob (a reading stored before it: from the reading);
        a blob it cannot read leaves that review without one rather than failing the list."""
        try:
            head = store.get_blob(rid, "reading_head")
            if head:
                return headline_from(head, store.list_marks(rid)).model_dump()
            view = reading_view(rid)
            return view["headline"] if view else None
        except (ValueError, KeyError, TypeError) as e:          # pydantic's ValidationError is a ValueError
            log.warning("review %s: no headline: %s: %s", rid, type(e).__name__, e)
            return None

    @app.get("/api/reviews")
    def list_reviews(logins: dict[str, str] = Depends(logins_of)):
        """The reviews on the session's servers, each with its workspace (§8)."""
        out = []
        for r in store.list_reviews():
            ws = reg.for_review(r)
            if ws is None or ws.server not in logins:
                continue
            r["workspace"] = ws_ref(ws)
            r["headline"] = review_headline(r["id"])
            out.append(r)
        return out

    @app.post("/api/reviews")
    def create_review(body: ReviewIn, logins: dict[str, str] = Depends(logins_of)):
        """A review in a workspace, by its owner; refused while the workspace isn't ready (§8, §11)."""
        wid = body.workspace_id
        if wid is None:
            every = reg.all()
            if len(every) != 1:
                raise HTTPException(422, "choose a workspace")
            wid = every[0].id
        # 404 or 403 first, then waited for without its guard (review of branch minors, M3); under it, no edit or remove
        # of it until the review is queued (final review M2)
        reg.settle(owned(wid, logins).ws)
        with reg.guard(wid):
            o = owned(wid, logins)                   # as it is now
            ready(o.ws, wait=False)
            title = body.title or "CLs " + ", ".join(str(c) for c in sorted(set(body.cls)))
            rid = store.create_review(title, o.user, body.cls, workspace_id=o.ws.id)
            if body.design_context and body.design_context.strip():
                store.put_blob(rid, CONTEXT_BLOB, DesignContext(notes=body.design_context.strip()).model_dump())
            o.ws.runner.submit_review(rid)
        return store.get_review(rid)

    @app.get("/api/reviews/{rid}")
    def get_review(rid: int, a: Access = Depends(in_review)):
        """The review, its CLs and stages, its workspace, and who the session is inside it (§8)."""
        return {"review": a.review, "cls": store.list_cls(rid), "stages": store.list_stages(rid),
                "workspace": ws_ref(a.ws), "viewer": {"user": a.user, "is_owner": a.is_owner}}

    @app.post("/api/reviews/{rid}/rerun")
    def rerun(rid: int, request: Request, fresh: bool = False, a: Access = Depends(owner_in_review)):
        """Run the review again; `fresh` asks the strong model for new stories instead of reusing a brief. Refused while
        its workspace isn't ready (§11)."""
        reg.settle(a.ws)                             # waited for without its guard (review of branch minors, M3)
        with reg.guard(a.ws.id):                     # into its queue as it is once no edit of it runs (final review M2)
            a = owner_in_review(in_review(rid, request))     # as it is now: still its owner (review of branch minors, M10)
            ready(a.ws, wait=False)
            a.ws.runner.submit_review(rid, fresh=fresh)
        return {"queued": True}

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

    @app.get("/api/reviews/{rid}/events")
    async def events(rid: int, request: Request, a: Access = Depends(in_review)):

        async def gen():
            last = None
            while not await request.is_disconnected():
                review = store.get_review(rid)          # read once: the stream ends only on an end it has sent
                payload = json.dumps({"review": review, "stages": store.list_stages(rid)})
                if payload != last:
                    last = payload
                    yield f"data: {payload}\n\n"
                if review["status"] in TERMINAL:
                    return
                await asyncio.sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/reviews/{rid}/overview")
    def overview(rid: int, a: Access = Depends(in_review)):
        """A split review's overview (spec 2026-10-03-large-change-boards §4); 404 for a review shown as one board."""
        ov = boardstore.overview(store, rid)
        if ov is None:
            raise HTTPException(404, "this review is shown as one board")
        return ov.model_dump()

    @app.get("/api/reviews/{rid}/board")
    def board(rid: int, cluster: str | None = None, a: Access = Depends(in_review)):
        b = boardstore.board(store, rid, cluster)
        if b is None:
            if cluster:
                raise HTTPException(404, "That cluster no longer exists after the re-run.")
            if boardstore.overview(store, rid) is not None:
                raise HTTPException(404, "this review is split into clusters: see its overview")
            raise HTTPException(404, "board not built yet")
        # boards stored by an older version get current defaults and file tags (spec §14.3)
        tags = {f.id: f.files for f in store.list_findings(rid)}
        b = tag_board(b, tags)
        return b.model_dump()

    NO_STORIES = "this review has no stories: re-run it"

    @app.get("/api/reviews/{rid}/stories")
    def stories(rid: int, a: Access = Depends(in_review)):
        """The review told as stories (spec 2026-10-04-change-stories §2); 404 for a review run before them."""
        ss = boardstore.stories(store, rid)
        if ss is None:
            raise HTTPException(404, NO_STORIES)
        return ss.model_dump()

    @app.get("/api/reviews/{rid}/stories/{sid}")
    def story(rid: int, sid: str, a: Access = Depends(in_review)):
        """One story: its board (every node it mentions) and its graph."""
        d = boardstore.story(store, rid, sid)
        if d is None:
            if boardstore.stories(store, rid) is None:
                raise HTTPException(404, NO_STORIES)
            raise HTTPException(404, "That story no longer exists after the re-run.")
        tags = {f.id: f.files for f in store.list_findings(rid)}
        d.board = tag_board(d.board, tags)
        if d.graph is not None:
            d.graph = tag_board(d.graph, tags)
        out = d.model_dump()
        out["reading"] = store.get_blob(rid, f"story_reading:{sid}")
        return out

    NO_READING = "this review has no reading: re-run it"
    NO_CHECK = "That check no longer exists after the re-run."

    @app.get("/api/reviews/{rid}/reading")
    def reading(rid: int, a: Access = Depends(in_review)):
        """Threads, connections, To check and the marks on it (spec 2026-10-07-review-reading §10.4)."""
        view = reading_view(rid)
        if view is None:
            raise HTTPException(404, NO_READING)
        view["design"] = store.get_blob(rid, "reading_design")       # spec 2026-11-02 §11; null without one
        return view

    def checks_or_404(rid: int) -> dict[str, Check]:
        """The reading's checks, found-no-hazard rows too, by key."""
        raw = store.get_blob(rid, "reading")
        if not raw:
            raise HTTPException(404, NO_READING)
        r = Reading.model_validate(raw)
        return {k.key: k for k in r.checks + r.cleared}

    def check_or_404(rid: int, key: str) -> Check:
        k = checks_or_404(rid).get(key)
        if k is None:
            raise HTTPException(404, NO_CHECK)
        return k

    def known_checks_or_404(rid: int, keys: list[str]) -> dict[str, Check]:
        """The reading's checks by key, once every key given is one of them: else 404 NO_CHECK, before anything is changed."""
        by_key = checks_or_404(rid)
        if any(key not in by_key for key in keys):
            raise HTTPException(404, NO_CHECK)
        return by_key

    @app.post("/api/reviews/{rid}/checks/marks")
    def mark_checks(rid: int, body: KeysIn, a: Access = Depends(in_review)):
        """All look fine (spec 2026-10-16 §4.3): every key or none."""
        keys = list(dict.fromkeys(body.keys))                # a key given twice is marked once
        by_key = known_checks_or_404(rid, keys)
        return {"marked": store.set_marks(rid, a.user, [(key, by_key[key].source_line) for key in keys])}

    @app.post("/api/reviews/{rid}/checks/unmarks")
    def unmark_checks(rid: int, body: KeysIn, a: Access = Depends(in_review)):
        """Reopen several places at once, as a Flows row's Reopen does: every key or none."""
        known_checks_or_404(rid, body.keys)
        store.clear_marks(rid, body.keys)
        return {"ok": True}

    @app.post("/api/reviews/{rid}/checks/{key:path}/mark")
    def mark_check(rid: int, key: str, a: Access = Depends(in_review)):
        k = check_or_404(rid, key)
        store.set_tick(rid, a.user, "check", k.key)          # Looks fine is also read, for the one who says it
        return store.set_mark(rid, k.key, a.user, k.source_line)

    @app.delete("/api/reviews/{rid}/checks/{key:path}/mark")
    def unmark_check(rid: int, key: str, a: Access = Depends(in_review)):
        store.clear_mark(rid, key)
        return {"ok": True}

    # ---- the reading plan (spec 2026-10-07-review-reading-phase2 §6) --------
    @app.get("/api/reviews/{rid}/ticks")
    def ticks(rid: int, a: Access = Depends(in_review)):
        if not store.has_blob(rid, "reading"):
            return {"stories": [], "checks": []}
        return store.list_ticks(rid, a.user)

    def tick_or_404(rid: int, kind: str, key: str) -> None:
        raw = store.get_blob(rid, "reading") or {}          # the stored keys alone: no need to build the whole model
        known = raw.get("order", []) if kind == "story" else [k.get("key") for k in raw.get("checks", [])]
        if key not in known:
            raise HTTPException(404, "That story or check is not in this review's reading.")

    @app.put("/api/reviews/{rid}/ticks/{kind}/{key:path}")
    def tick(rid: int, kind: Literal["story", "check"], key: str, a: Access = Depends(in_review)):
        tick_or_404(rid, kind, key)
        store.set_tick(rid, a.user, kind, key)
        return {"ok": True}

    @app.delete("/api/reviews/{rid}/ticks/{kind}/{key:path}")
    def untick(rid: int, kind: Literal["story", "check"], key: str, a: Access = Depends(in_review)):
        tick_or_404(rid, kind, key)
        store.clear_tick(rid, a.user, kind, key)
        return {"ok": True}

    @app.get("/api/reviews/{rid}/locate")
    def locate(rid: int, node: str | None = None, flow: str | None = None, finding: str | None = None,
               a: Access = Depends(in_review)):
        """The cluster to open for a node, flow or finding (null for a review shown as one board), and its story."""
        ss = boardstore.stories(store, rid)
        sid = None
        if ss is not None:
            sid = (ss.flow_story.get(flow) if flow else ss.finding_story.get(finding) if finding
                   else ss.node_story.get(node) if node else None)
        ov = boardstore.overview(store, rid)
        if ov is None:
            return {"cluster": None, "story": sid}
        if flow:
            held = boardstore.with_flow(store, rid, flow)
            if held:
                return {"cluster": held[0], "story": sid}
        elif finding:
            c = next((c for c in ov.clusters if finding in c.finding_ids), None)
            if c:
                return {"cluster": c.id, "story": sid}
        elif node:
            home = (store.get_blob(rid, "node_cluster") or {}).get(node)
            if home:
                return {"cluster": home, "story": sid}
            for cid, b in boardstore.boards(store, rid).items():
                if any(n.id == node for n in b.nodes):
                    return {"cluster": cid, "story": sid}
        if sid:
            return {"cluster": None, "story": sid}
        raise HTTPException(404, "not on any board of this review")

    def shown(rid: int):
        """The review's graph, node files and stories (None before stories), for neighbours."""
        im = ImpactModel.model_validate(store.get_blob(rid, "impact") or {})
        return im, store.get_blob(rid, "node_files") or {}, boardstore.stories(store, rid)

    @app.get("/api/reviews/{rid}/names")
    def node_names(rid: int, a: Access = Depends(in_review)):
        """A name for every node the UI can show (spec 2026-10-04-review-workspace §4.2): changed code, nodes on any
        board or story, findings' nodes and the nodes cited in flow, story, finding and summary text."""
        im = store.get_blob(rid, "impact") or {}               # as stored: only the nodes named are built, not the graph
        ss = boardstore.stories(store, rid)
        ids, texts = boardstore.shown_nodes(store, rid, ss)
        ids |= set(im.get("changed", []))
        for f in store.list_findings(rid):
            ids |= set(f.nodes) | {n for e in f.evidence for n in e.nodes or []}
            ids |= {n for h in f.hypotheses for n in h.cites}
            texts += [f.summary, f.explanation, *f.verify_steps, *(h.text for h in f.hypotheses),
                      *(e.text for e in f.evidence)]
        wanted, known = ids | cited(texts), im.get("nodes", {})
        nodes = {nid: Node.model_validate(known[nid]) for nid in wanted if nid in known}
        return names(nodes, wanted, store.get_blob(rid, "node_files") or {}, ss.node_story if ss else {})

    @app.get("/api/reviews/{rid}/nodes/{nid}/neighbours")
    def node_neighbours(rid: int, nid: str, limit: int = 20, callers: int | None = None, callees: int | None = None,
                        a: Access = Depends(in_review)):
        """A node's callers and callees, the most affected first (spec 2026-10-04-review-workspace §4.3)."""
        im, depot_of, ss = shown(rid)
        out = neighbours(im, nid, depot_of, ss.node_story if ss else {}, root=canon(str(a.ws.cfg.workspace.root)),
                         limit=limit, callers=callers, callees=callees)
        if out is None:
            raise HTTPException(404, f"no node {nid} in this review")
        return out

    @app.get("/api/reviews/{rid}/source")
    def source(rid: int, path: str, side: Literal["before", "after"] = "after", a: Access = Depends(in_review)):
        """A file's text for the board: changed files from the change set, others from the base workspace."""
        f = filestore.one(store, rid, path)
        if f is not None:
            rev = (f.get("base_rev") or "base") if side == "before" else "changed"
            return {"path": path, "depot": path, "rev": rev, "text": f[side], "changed": True}
        key = f"source:{path}"
        cached = store.get_blob(rid, key)
        if cached is None:
            try:
                sf = bundle(a.ws).source.read(path)
            except SourceNotAllowed as e:
                raise HTTPException(403, str(e)) from e
            except SourceBinary as e:
                raise HTTPException(415, str(e)) from e
            except SourceTooLarge as e:
                raise HTTPException(413, str(e)) from e
            except P4Error as e:
                raise HTTPException(502, f"Perforce: {e}") from e
            cached = {"path": path, "depot": sf.depot, "rev": sf.rev, "text": sf.text, "changed": False}
            store.put_blob(rid, key, cached)
        return cached

    @app.get("/api/reviews/{rid}/findings")
    def findings(rid: int, a: Access = Depends(in_review)):
        root = canon(str(a.ws.cfg.workspace.root))               # text read by people; titles stay as stored (anchors)
        return [f.model_copy(update={"summary": tidy(f.summary, root),
                                     "evidence": [e.model_copy(update={"text": tidy(e.text, root)}) for e in f.evidence]})
                .model_dump() for f in store.list_findings(rid)]

    @app.patch("/api/reviews/{rid}/findings/{fid}")
    def finding_state(rid: int, fid: str, body: FindingStateIn, a: Access = Depends(owner_in_review)):
        if not store.set_finding_state(rid, fid, body.state):
            raise HTTPException(404, "finding not found")
        return {"ok": True}

    @app.get("/api/reviews/{rid}/files")
    def files(rid: int, a: Access = Depends(in_review)):
        """The changed files without their text (a file's text comes with /file, when it is shown)."""
        return filestore.listing(store, rid)

    @app.get("/api/reviews/{rid}/file")
    def changed_file(rid: int, path: str, a: Access = Depends(in_review)):
        """A changed file's text before and after, and each CL's, with who wrote each line of a file several CLs edit
        (phase 2 §4)."""
        f = filestore.one(store, rid, path)
        if f is None:
            raise HTTPException(404, f"{path} is not a changed file of this review")
        lines = store.get_blob(rid, "lines") or {}
        return {**f, "lines": lines[path]} if path in lines else f

    # ---- shared sinks (spec 2026-10-09-shared-sinks §6), per workspace (spec 2026-10-31 §5) ----
    def sinks_view(ws: Workspace) -> dict:
        an = ws.cfg.analysis
        return {"threshold": an.sink_threshold, "patterns": an.sink_fields, "marked": marks(store, ws.scope)}

    def sink_label(label: str) -> str:
        if not label.strip() or len(label) > 300:
            raise HTTPException(422, "a field's label, as record::field")
        return label

    @app.get("/api/workspaces/{wid}/sinks")
    def sinks(o: Owned = Depends(owned)):
        return sinks_view(o.ws)

    @app.put("/api/workspaces/{wid}/sinks/{label:path}")
    def mark_sink(label: str, o: Owned = Depends(owned)):
        set_mark(store, sink_label(label), True, o.ws.scope)
        return sinks_view(o.ws)

    @app.delete("/api/workspaces/{wid}/sinks/{label:path}")
    def unmark_sink(label: str, o: Owned = Depends(owned)):
        set_mark(store, sink_label(label), False, o.ws.scope)
        return sinks_view(o.ws)

    # ---- workspaces (spec 2026-10-31 §8) ----------------------------------------------
    def ws_row(ws: Workspace, logins: dict[str, str]) -> dict:
        """A workspace as the Workspaces page lists it; whoever may edit it (its owner, or the seed's) also gets its
        fields."""
        mine = logins.get(ws.server) == ws.owner
        manage = mine or hosts(logins)
        out = {**ws_ref(ws), "client": ws.cfg.workspace.client, "vcs": ws.cfg.workspace.vcs, "ready": ws.ready,
               "reason": ws.reason, "seed": ws.seed, "is_owner": mine, "can_manage": manage}
        row = store.get_workspace(ws.id) if manage else None
        if row is not None:
            cc = json.loads(row["compile_commands"])
            out["fields"] = {**{k: row[k] for k in ("name", "vcs", "p4port", "client", "p4user", "root", "build_root",
                                                     "swarm_url", "settings")},
                             "compile_commands": "\n".join(cc) if isinstance(cc, list) else cc}
            out["checks"] = [c.model_dump() for c in ws.checks]   # what a save answers, once its bundle has loaded
        return out

    def adder(logins: dict[str, str] = Depends(logins_of)) -> dict[str, str]:
        """Adding a workspace takes owner rights on at least one (§7; everyone signed in, with project 3)."""
        if not any(logins.get(w.server) == w.owner for w in reg.all()):
            raise HTTPException(403, "only the owner of a workspace adds workspaces")
        return logins

    def checked(ws: Workspace, logins: dict[str, str]) -> dict:
        return {**ws_row(ws, logins), "checks": [c.model_dump() for c in ws.checks]}

    def host_programs(settings: str, before: str | None, logins: dict[str, str]) -> None:
        """Settings naming a program or library the server runs or loads are the host's (final review I3): only the
        owner of the seed sets or changes them; anyone who edits a workspace keeps what is there."""
        if not hosts(logins) and program_settings(settings) != program_settings(before):
            raise HTTPException(422, "settings: toolchain clang, libclang, search_paths and query_compilers, and an "
                                     "override's clang and libclang, name programs this server runs or loads: only the "
                                     "owner of the workspace in tortoise.yaml sets them")

    def stays(row: dict, p4port: str | None, logins: dict[str, str]) -> None:
        """A workspace with reviews keeps its Perforce server: they were made on that server's code, and moved they
        would show to those signed in to another (final review M4). The owner of the seed may move it, as they move
        the seed in tortoise.yaml."""
        was = server_of(row["p4port"])
        if server_of(p4port) != was and not hosts(logins) and (n := store.review_count(row["id"])):
            raise HTTPException(409, f"the workspace {row['name']} has {n} review(s) on {was}: it keeps its Perforce "
                                     "server, so they stay with those signed in there (the owner of the workspace in "
                                     "tortoise.yaml can move it)")

    def saved(change: Callable[[], Workspace], logins: dict[str, str]) -> dict:
        try:
            return checked(change(), logins)
        except Invalid as e:
            raise HTTPException(422, str(e)) from e
        except Conflict as e:
            raise HTTPException(409, str(e)) from e
        except Gone as e:                            # removed by another request meanwhile
            raise HTTPException(404, "workspace not found") from e

    @app.get("/api/workspaces")
    def list_workspaces(logins: dict[str, str] = Depends(logins_of)):
        """The workspaces on the session's servers; the owner of the seed gets every one, to fix or remove."""
        return [ws_row(w, logins) for w in reg.all() if w.server in logins or hosts(logins)]

    @app.post("/api/workspaces")
    def add_workspace(body: WorkspaceIn, logins: dict[str, str] = Depends(adder)):
        """Saved even when its checks fail; the answer carries them (§11)."""
        if len(body.settings) > 100_000:
            raise HTTPException(422, "settings: at most 100000 characters")
        host_programs(body.settings, None, logins)
        by = next(logins[w.server] for w in reg.all() if logins.get(w.server) == w.owner)
        return saved(lambda: reg.add(body.fields(), by), logins)

    @app.post("/api/workspaces/detect")
    def detect(body: DetectIn, _: dict[str, str] = Depends(adder)):
        """What `codetortoise init` finds at a root, to fill the add form: P4CONFIG's server, client and user, the
        client's Root, the compile databases."""
        if not os.path.isabs(body.root):
            raise HTTPException(422, "root: a full path on this host")
        p4_bin = reg.base.workspace.p4_bin if reg.base.workspace is not None else "p4"

        def client_root(port: str, client: str) -> str | None:
            recs = P4Runner(port, client, p4_bin, timeout=30, cwd=body.root).run("client", "-o", client)
            return recs[0].get("Root") if recs else None
        s = scan(Path(body.root), client_root=client_root)
        notes = ([] if Path(body.root).is_dir() else [f"{body.root} is not a folder on this host"]) + s.notes
        return {"root": str(s.root), "p4port": s.values["p4port"], "client": s.values["client"],
                "p4user": s.values["owner"], "compile_commands": [str(p) for p in s.compile_dbs],
                "client_root": s.client_root, "notes": notes}

    @app.put("/api/workspaces/{wid}")
    def edit_workspace(body: WorkspaceIn, o: Owned = Depends(managed)):
        """New fields, a new bundle swapped in; refused for the seed and while a review waits or runs in it (§6)."""
        if len(body.settings) > 100_000:
            raise HTTPException(422, "settings: at most 100000 characters")
        fields = body.fields()

        def vet(row: dict) -> None:                  # against the row as stored, once no other change of it runs
            host_programs(body.settings, row["settings"], o.logins)
            stays(row, fields["p4port"], o.logins)
        return saved(lambda: reg.edit(o.ws.id, fields, check=vet), o.logins)

    @app.delete("/api/workspaces/{wid}")
    def remove_workspace(o: Owned = Depends(managed)):
        try:
            reg.remove(o.ws.id)
        except Conflict as e:
            raise HTTPException(409, str(e)) from e
        except Gone as e:                            # removed by another request meanwhile
            raise HTTPException(404, "workspace not found") from e
        return {"ok": True}

    # ---- AI on demand (spec 2026-10-03) ---------------------------------------
    @app.post("/api/reviews/{rid}/explain", status_code=202)
    def explain(rid: int, body: ExplainIn, a: Access = Depends(in_review)):
        svc = bundle(a.ws)
        if svc.llm is None or svc.ledger is None:
            raise HTTPException(409, "no LLM is configured")
        if a.review["status"] not in TERMINAL:
            raise HTTPException(409, RERUNNING)
        try:
            ondemand.check_target(svc, rid, body.kind, body.target)
        except ondemand.NotFound as e:
            raise HTTPException(404, str(e)) from e
        same = next((j for j in reg.pool.jobs.get(rid, []) if j["status"] == "running" and j["kind"] == body.kind
                     and j["target"] == body.target), None)
        if same:                                       # someone is already asking: share that answer, pay once
            return same
        reason = svc.ledger.check(rid, a.user)
        if reason:
            raise HTTPException(429, reason)
        return a.ws.runner.submit_ai(rid, a.user, body.kind, body.target,
                                     lambda: ondemand.explain(svc, rid, a.user, body.kind, body.target))

    @app.get("/api/reviews/{rid}/ai")
    def ai_view(rid: int, a: Access = Depends(in_review)):
        reg.settle(a.ws)                               # right after a start: what its bundle has, once built
        svc, cfg, ledger = a.ws.svc, a.ws.cfg, reg.ledger
        b = cfg.llm.budget
        u = ledger.usage(rid)
        u.pop("calls", None)                           # polled while work is pending; the list is /ai/calls
        strong = cfg.llm.strong.model if svc is not None and svc.strong is not None and cfg.llm.strong else None
        return {**u, "llm": svc is not None and svc.llm is not None, "strong": strong,
                "me_today": ledger.person_today(a.user), "me_limit": b.per_person_daily,
                "per_mention": ledger.rounds(rid), "is_owner": a.is_owner, "jobs": reg.pool.jobs.get(rid, []),
                "file_summaries": store.get_blob(rid, "file_summaries") or {}}

    @app.get("/api/reviews/{rid}/ai/calls")
    def ai_calls(rid: int, a: Access = Depends(in_review)):
        return reg.ledger.usage(rid)["calls"]

    @app.get("/api/reviews/{rid}/ai/requests.zip")
    def ai_requests(rid: int, call: int | None = None, a: Access = Depends(in_review)):
        """The review's logged AI requests, one JSON file per request (spec 2026-10-08-llm-robustness §8.2)."""
        got = request_log.rows(store, rid, call)
        if not got:
            raise HTTPException(404, "no requests logged")
        name = f"review-{rid}" + (f"-call-{call}" if call is not None else "") + "-requests.zip"
        return Response(request_log.zip_bytes(got), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.put("/api/reviews/{rid}/ai/budget")
    def ai_budget(rid: int, body: BudgetIn, a: Access = Depends(owner_in_review)):
        reg.ledger.raise_budget(rid, body.budget, a.user)
        return {"budget": reg.ledger.budget(rid)}

    @app.put("/api/reviews/{rid}/ai/rounds")
    def ai_rounds(rid: int, body: RoundsIn, a: Access = Depends(owner_in_review)):
        reg.ledger.set_rounds(rid, body.rounds, a.user)
        return {"rounds": reg.ledger.rounds(rid)}

    # ---- comments ----------------------------------------------------------
    @app.get("/api/reviews/{rid}/comments")
    def comments(rid: int, a: Access = Depends(in_review)):
        return store.list_comments(rid)

    @app.post("/api/reviews/{rid}/comments")
    def add_comment(rid: int, body: CommentIn, a: Access = Depends(in_review)):
        if body.parent_id is not None:
            parent = store.get_comment(body.parent_id)
            if parent is None or parent["review_id"] != rid:
                raise HTTPException(400, "bad parent_id")
        c = store.add_comment(rid, a.user, body.body, body.anchor_kind, body.anchor, body.parent_id)
        if tortoise.mentions(body.body) and a.user != tortoise.AUTHOR:
            ask_tortoise(a, c)
        return c

    def ask_tortoise(a: Access, question: dict) -> None:
        """Post tortoise's reply in the question's thread and answer it as a job (spec 2026-10-03 §5)."""
        reg.settle(a.ws)                               # right after a start: answered once the bundle is built
        rid, user, svc = a.rid, a.user, a.ws.svc
        root = question["parent_id"] or question["id"]
        reply = store.add_comment(rid, tortoise.AUTHOR, "thinking…", question["anchor_kind"], question["anchor"], root)
        base = {"pending": False, "read": [], "files": [], "calls": 0}
        if svc is None:
            why = f"the workspace {a.ws.name} is not loaded: {a.ws.reason}"
            store.set_ai_reply(reply["id"], f"I can't answer: {why}.", {**base, "error": why})
            return
        if svc.llm is None or svc.ledger is None:
            store.set_ai_reply(reply["id"], "I can't answer: no AI is configured for CodeTortoise.",
                               {**base, "error": "no LLM"})
            return
        reason = svc.ledger.check(rid, user)
        if reason:
            store.set_ai_reply(reply["id"], f"I couldn't answer: {reason}.", {**base, "error": reason})
            return
        if store.get_review(rid)["status"] not in TERMINAL:
            store.set_ai_reply(reply["id"], f"I couldn't answer: {RERUNNING}. Ask again when it finishes.",
                               {**base, "error": RERUNNING})
            return
        store.set_ai_reply(reply["id"], "thinking…", {**base, "pending": True, "round": 0,
                                                      "of": svc.ledger.rounds(rid)})
        a.ws.runner.submit_ai(rid, user, "mention", str(reply["id"]),
                              lambda: tortoise.answer(svc, rid, user, question, reply["id"]))

    def comment_access(cid: int, logins: dict[str, str] = Depends(logins_of)) -> tuple[dict, Access]:
        """A comment and its review, read as the session's sign-in on that review's server."""
        c = store.get_comment(cid)
        if c is None:
            raise HTTPException(404, "comment not found")
        return c, review_access(c["review_id"], logins)

    @app.patch("/api/comments/{cid}")
    def edit_comment(cid: int, body: CommentPatch, got: tuple[dict, Access] = Depends(comment_access)):
        c, a = got
        if body.body is not None and c["author"] != a.user:
            raise HTTPException(403, "only the author can edit")
        return store.update_comment(cid, body=body.body, resolved=body.resolved)

    @app.delete("/api/comments/{cid}")
    def delete_comment(cid: int, got: tuple[dict, Access] = Depends(comment_access)):
        c, a = got
        if c["author"] != a.user and not a.is_owner:
            raise HTTPException(403, "only the author or owner can delete")
        store.delete_comment(cid)
        return {"ok": True}

    # ---- swarm ---------------------------------------------------------------
    def swarm_client(a: Access):
        client = bundle(a.ws).swarm()
        if client is None:
            raise HTTPException(409, "Swarm not configured or owner not logged in")
        return client

    def cl_row(rid: int, cl: int) -> dict:
        row = next((c for c in store.list_cls(rid) if c["cl"] == cl), None)
        if row is None:
            raise HTTPException(404, "CL not in review")
        return row

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/refresh")
    def swarm_refresh(rid: int, cl: int, a: Access = Depends(owner_in_review)):
        cl_row(rid, cl)
        try:
            data = swarm_client(a).get_review_for_change(cl)
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.set_cl_swarm(rid, cl, data)
        return data

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/create")
    def swarm_create(rid: int, cl: int, a: Access = Depends(owner_in_review)):
        row = cl_row(rid, cl)
        if row["status"] != "pending":
            raise HTTPException(409, "only pending (shelved) CLs can get a new Swarm review")
        if row.get("swarm"):
            raise HTTPException(409, "CL already has a Swarm review")
        try:
            data = swarm_client(a).create_review(cl, row.get("description") or f"CL {cl}")
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.set_cl_swarm(rid, cl, data)
        store.record_swarm_post(rid, cl, "create", str(data.get("id")))
        return data

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/post")
    def swarm_post(rid: int, cl: int, body: SwarmPostIn, a: Access = Depends(owner_in_review)):
        row = cl_row(rid, cl)
        if not row.get("swarm"):
            raise HTTPException(409, "CL has no Swarm review")
        if any(p["kind"] == "summary" for p in store.swarm_posts(rid, cl)) and not body.confirm_repeat:
            raise HTTPException(409, "summary already posted; resend with confirm_repeat")
        sb = store.get_blob(rid, "storyboard") or {}
        link = f"{reg.base.server.public_url.rstrip('/')}/r/{rid}"
        text = f"CodeTortoise review (risk: {sb.get('risk', 'n/a')}): {sb.get('summary', '')}\n\nFull storyboard: {link}"
        try:
            cid = swarm_client(a).post_comment(row["swarm"]["id"], text)
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.record_swarm_post(rid, cl, "summary", cid)
        return {"comment_id": cid}

    # ---- SPA -------------------------------------------------------------------
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        target = STATIC / path
        if path and target.is_file() and STATIC in target.resolve().parents:
            return FileResponse(target)
        index = STATIC / "index.html"
        if index.exists():
            return FileResponse(index)
        return Response("frontend not built; run `npm run build` in frontend/", media_type="text/plain")

    return app


def make_authenticator(reg: Registry, runner_for: Callable[[str], P4Runner | None] | None = None):
    """authenticate(server, user, password) -> a ticket, or None. `runner_for(server)` is what runs `p4 login` there
    (default: the registry's, from one of that server's Perforce workspaces; none for a git workspace's server)."""
    if reg.base.auth.mode == "dev":
        return lambda server, user, password: "" if user else None
    runner_for = runner_for or reg.login_runner

    def p4_auth(server: str, user: str, password: str) -> str | None:
        p4 = runner_for(server)
        if p4 is None or not user:
            return None
        try:
            return p4.login_check(user, password, all_hosts=user in reg.owners(server))
        except P4Error as e:
            if "expired" in str(e).lower():
                raise LoginRejected("Your Perforce password has expired. Change it with `p4 passwd`, then sign in "
                                    "again.") from e
            if _unreachable(str(e)):
                raise LoginRejected(f"Could not sign in to {server}: {_p4_message(str(e))}") from e
            return None                              # a wrong password or user: never says which (no user lookup)
    return p4_auth


def _unreachable(msg: str) -> bool:
    """A failure of the Perforce server or of this host, not of the credentials (spec 2026-10-31 §11): p4 could not
    run or timed out, or could not connect to the server."""
    low = msg.lower()
    return msg.startswith("p4 login: ") or any(s in low for s in ("connect to server failed", "tcp connect to",
                                                                  "ssl connect to", "the authenticity of"))


def _p4_message(msg: str) -> str:
    """Perforce's message, on one line, without our own prefix."""
    for prefix in ("p4 login failed: ", "p4 login: "):
        msg = msg.removeprefix(prefix)
    return " ".join(msg.split())
