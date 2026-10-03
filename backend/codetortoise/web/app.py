"""FastAPI application: JSON API under /api, React SPA everywhere else."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from codetortoise.board import Board
from codetortoise.health import run_health
from codetortoise.pipeline import JobRunner
from codetortoise.provenance import tag_board
from codetortoise.services import Services
from codetortoise.swarm import SwarmError
from codetortoise.vcs.p4runner import P4Error
from codetortoise.vcs.source import SourceBinary, SourceNotAllowed, SourceTooLarge

COOKIE = "ct_session"
STATIC = Path(__file__).parent / "static"
TERMINAL = {"done", "degraded", "failed"}


class LoginRejected(Exception):
    """Raised by an authenticator with a message that is safe to show (never reveals whether a user exists)."""


class LoginIn(BaseModel):
    user: str
    password: str = ""


class ReviewIn(BaseModel):
    cls: list[int] = Field(min_length=1)
    title: str | None = None


class FindingStateIn(BaseModel):
    state: Literal["open", "ack", "dismissed"]


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    anchor_kind: Literal["line", "function", "finding", "chapter", "review"]
    anchor: dict = Field(default_factory=dict)
    parent_id: int | None = None


class CommentPatch(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    resolved: bool | None = None


class SwarmPostIn(BaseModel):
    confirm_repeat: bool = False


class LayerNameIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
    """authenticate(user, password) -> ticket str on success, None on failure."""
    app = FastAPI(title="CodeTortoise")
    store, cfg = svc.store, svc.cfg
    state = {"ready": run_health(svc).ready}

    def user_of(request: Request) -> str:
        user = store.session_user(request.cookies.get(COOKIE))
        if user is None:
            raise HTTPException(401, "login required")
        return user

    def owner_of(user: str = Depends(user_of)) -> str:
        if user != cfg.owner:
            raise HTTPException(403, "owner only")
        return user

    def review_or_404(rid: int) -> dict:
        r = store.get_review(rid)
        if r is None:
            raise HTTPException(404, "review not found")
        return r

    # ---- auth --------------------------------------------------------------
    @app.post("/api/login")
    def login(body: LoginIn, response: Response):
        try:
            ticket = authenticate(body.user, body.password)
        except LoginRejected as e:
            raise HTTPException(401, str(e)) from e
        if ticket is None:
            raise HTTPException(401, "invalid credentials")
        if body.user == cfg.owner:
            svc.owner_ticket = ticket
        token = store.create_session(body.user)
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 86400,
                            secure=cfg.server.tls_cert is not None)
        return {"user": body.user, "is_owner": body.user == cfg.owner}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        tok = request.cookies.get(COOKIE)
        if tok:
            store.delete_session(tok)
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(user: str = Depends(user_of)):
        return {"user": user, "is_owner": user == cfg.owner, "swarm_ready": svc.swarm() is not None}

    # ---- health / index -------------------------------------------------------
    @app.get("/api/health")
    def health(_: str = Depends(owner_of)):
        rep = run_health(svc, deep=True)
        state["ready"] = rep.ready
        return {**rep.model_dump(), "index_building": runner.index_building}

    @app.post("/api/index/rebuild")
    def rebuild_index(_: str = Depends(owner_of)):
        runner.submit_index()
        return {"queued": True}

    # ---- reviews ------------------------------------------------------------
    @app.get("/api/reviews")
    def list_reviews(_: str = Depends(user_of)):
        return store.list_reviews()

    @app.post("/api/reviews")
    def create_review(body: ReviewIn, user: str = Depends(owner_of)):
        if not state["ready"]:
            raise HTTPException(409, "startup checks failing; see Health")
        title = body.title or "CLs " + ", ".join(str(c) for c in sorted(set(body.cls)))
        rid = store.create_review(title, user, body.cls)
        runner.submit_review(rid)
        return store.get_review(rid)

    @app.get("/api/reviews/{rid}")
    def get_review(rid: int, _: str = Depends(user_of)):
        return {"review": review_or_404(rid), "cls": store.list_cls(rid), "stages": store.list_stages(rid)}

    @app.post("/api/reviews/{rid}/rerun")
    def rerun(rid: int, _: str = Depends(owner_of)):
        review_or_404(rid)
        runner.submit_review(rid)
        return {"queued": True}

    @app.get("/api/reviews/{rid}/events")
    async def events(rid: int, request: Request, _: str = Depends(user_of)):
        review_or_404(rid)

        async def gen():
            last = None
            while not await request.is_disconnected():
                payload = json.dumps({"review": store.get_review(rid), "stages": store.list_stages(rid)})
                if payload != last:
                    last = payload
                    yield f"data: {payload}\n\n"
                if store.get_review(rid)["status"] in TERMINAL:
                    return
                await asyncio.sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/reviews/{rid}/board")
    def board(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        b = store.get_blob(rid, "board")
        if b is None:
            raise HTTPException(404, "board not built yet")
        # boards stored by an older version get current defaults and file tags (spec §14.3)
        b = tag_board(Board.model_validate(b), {f.id: f.files for f in store.list_findings(rid)}).model_dump()
        overrides = store.kv_get("layer_overrides") or {}
        for layer in b.get("layers", []):
            if str(layer["level"]) in overrides:
                layer["name"] = overrides[str(layer["level"])]
        return b

    @app.get("/api/reviews/{rid}/source")
    def source(rid: int, path: str, side: Literal["before", "after"] = "after", _: str = Depends(user_of)):
        """A file's text for the board: changed files from the change set, others from the base workspace."""
        review_or_404(rid)
        cs = store.get_blob(rid, "changeset") or {}
        f = next((f for f in cs.get("files", []) if f["depot"] == path), None)
        if f is not None:
            rev = (f.get("base_rev") or "base") if side == "before" else "changed"
            return {"path": path, "depot": path, "rev": rev, "text": f[side], "changed": True}
        key = f"source:{path}"
        cached = store.get_blob(rid, key)
        if cached is None:
            try:
                sf = svc.source.read(path)
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
    def findings(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        return [f.model_dump() for f in store.list_findings(rid)]

    @app.patch("/api/reviews/{rid}/findings/{fid}")
    def finding_state(rid: int, fid: str, body: FindingStateIn, _: str = Depends(owner_of)):
        if not store.set_finding_state(rid, fid, body.state):
            raise HTTPException(404, "finding not found")
        return {"ok": True}

    @app.get("/api/reviews/{rid}/files")
    def files(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        cs = store.get_blob(rid, "changeset") or {}
        return cs.get("files", [])

    # ---- layers ------------------------------------------------------------
    @app.put("/api/layers/{level}")
    def rename_layer(level: int, body: LayerNameIn, _: str = Depends(owner_of)):
        overrides = store.kv_get("layer_overrides") or {}
        overrides[str(level)] = body.name
        store.kv_put("layer_overrides", overrides)
        return overrides

    # ---- comments ----------------------------------------------------------
    @app.get("/api/reviews/{rid}/comments")
    def comments(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        return store.list_comments(rid)

    @app.post("/api/reviews/{rid}/comments")
    def add_comment(rid: int, body: CommentIn, user: str = Depends(user_of)):
        review_or_404(rid)
        if body.parent_id is not None:
            parent = store.get_comment(body.parent_id)
            if parent is None or parent["review_id"] != rid:
                raise HTTPException(400, "bad parent_id")
        return store.add_comment(rid, user, body.body, body.anchor_kind, body.anchor, body.parent_id)

    @app.patch("/api/comments/{cid}")
    def edit_comment(cid: int, body: CommentPatch, user: str = Depends(user_of)):
        c = store.get_comment(cid)
        if c is None:
            raise HTTPException(404, "comment not found")
        if body.body is not None and c["author"] != user:
            raise HTTPException(403, "only the author can edit")
        return store.update_comment(cid, body=body.body, resolved=body.resolved)

    @app.delete("/api/comments/{cid}")
    def delete_comment(cid: int, user: str = Depends(user_of)):
        c = store.get_comment(cid)
        if c is None:
            raise HTTPException(404, "comment not found")
        if c["author"] != user and user != cfg.owner:
            raise HTTPException(403, "only the author or owner can delete")
        store.delete_comment(cid)
        return {"ok": True}

    # ---- swarm ---------------------------------------------------------------
    def swarm_client():
        client = svc.swarm()
        if client is None:
            raise HTTPException(409, "Swarm not configured or owner not logged in")
        return client

    def cl_row(rid: int, cl: int) -> dict:
        row = next((c for c in store.list_cls(rid) if c["cl"] == cl), None)
        if row is None:
            raise HTTPException(404, "CL not in review")
        return row

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/refresh")
    def swarm_refresh(rid: int, cl: int, _: str = Depends(owner_of)):
        cl_row(rid, cl)
        try:
            data = swarm_client().get_review_for_change(cl)
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.set_cl_swarm(rid, cl, data)
        return data

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/create")
    def swarm_create(rid: int, cl: int, _: str = Depends(owner_of)):
        row = cl_row(rid, cl)
        if row["status"] != "pending":
            raise HTTPException(409, "only pending (shelved) CLs can get a new Swarm review")
        if row.get("swarm"):
            raise HTTPException(409, "CL already has a Swarm review")
        try:
            data = swarm_client().create_review(cl, row.get("description") or f"CL {cl}")
        except SwarmError as e:
            raise HTTPException(502, str(e)) from e
        store.set_cl_swarm(rid, cl, data)
        store.record_swarm_post(rid, cl, "create", str(data.get("id")))
        return data

    @app.post("/api/reviews/{rid}/cls/{cl}/swarm/post")
    def swarm_post(rid: int, cl: int, body: SwarmPostIn, _: str = Depends(owner_of)):
        row = cl_row(rid, cl)
        if not row.get("swarm"):
            raise HTTPException(409, "CL has no Swarm review")
        if any(p["kind"] == "summary" for p in store.swarm_posts(rid, cl)) and not body.confirm_repeat:
            raise HTTPException(409, "summary already posted; resend with confirm_repeat")
        sb = store.get_blob(rid, "storyboard") or {}
        link = f"{cfg.server.public_url.rstrip('/')}/r/{rid}"
        text = f"CodeTortoise review (risk: {sb.get('risk', 'n/a')}): {sb.get('summary', '')}\n\nFull storyboard: {link}"
        try:
            cid = swarm_client().post_comment(row["swarm"]["id"], text)
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


def make_authenticator(svc: Services):
    if svc.cfg.auth.mode == "dev":
        return lambda user, password: "" if user else None

    def p4_auth(user: str, password: str) -> str | None:
        if svc.p4 is None or not user:
            return None
        try:
            return svc.p4.login_check(user, password, all_hosts=user == svc.cfg.owner)
        except P4Error as e:
            if "expired" in str(e).lower():
                raise LoginRejected("Your Perforce password has expired. Change it with `p4 passwd`, then sign in "
                                    "again.") from e
            return None
    return p4_auth
