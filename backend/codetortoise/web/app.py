"""FastAPI application: JSON API under /api, React SPA everywhere else."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from codetortoise import boardstore
from codetortoise.health import run_health
from codetortoise.impact import ImpactModel
from codetortoise.llm import ondemand, tortoise
from codetortoise.names import cited, names, neighbours
from codetortoise.paths import canon
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


class ExplainIn(BaseModel):
    kind: Literal["flow", "finding", "file", "story"]
    target: str = Field(min_length=1, max_length=2000)


class BudgetIn(BaseModel):
    budget: int = Field(ge=0, le=1_000_000)


class RoundsIn(BaseModel):
    rounds: int = Field(ge=1, le=50)


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


RERUNNING = "the review is being re-run"


def create_app(svc: Services, runner: JobRunner, authenticate) -> FastAPI:
    """authenticate(user, password) -> ticket str on success, None on failure."""
    app = FastAPI(title="CodeTortoise")
    store, cfg = svc.store, svc.cfg
    # work a stopped server left unfinished: answers can't resume, so end them (spec 2026-10-03 §5)
    store.end_pending_ai_replies("I couldn't answer: CodeTortoise restarted before the answer was finished. Ask again.")
    if svc.ledger:
        svc.ledger.fail_running()
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

    def named(layers: list[dict]) -> None:
        overrides = store.kv_get("layer_overrides") or {}
        for layer in layers:
            if str(layer["level"]) in overrides:
                layer["name"] = overrides[str(layer["level"])]

    @app.get("/api/reviews/{rid}/overview")
    def overview(rid: int, _: str = Depends(user_of)):
        """A split review's overview (spec 2026-10-03-large-change-boards §4); 404 for a review shown as one board."""
        review_or_404(rid)
        ov = boardstore.overview(store, rid)
        if ov is None:
            raise HTTPException(404, "this review is shown as one board")
        out = ov.model_dump()
        named(out["layers"])
        return out

    @app.get("/api/reviews/{rid}/board")
    def board(rid: int, cluster: str | None = None, _: str = Depends(user_of)):
        review_or_404(rid)
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
        out = b.model_dump()
        named(out.get("layers", []))
        return out

    NO_STORIES = "this review has no stories: re-run it"

    @app.get("/api/reviews/{rid}/stories")
    def stories(rid: int, _: str = Depends(user_of)):
        """The review told as stories (spec 2026-10-04-change-stories §2); 404 for a review run before them."""
        review_or_404(rid)
        ss = boardstore.stories(store, rid)
        if ss is None:
            raise HTTPException(404, NO_STORIES)
        return ss.model_dump()

    @app.get("/api/reviews/{rid}/stories/{sid}")
    def story(rid: int, sid: str, _: str = Depends(user_of)):
        """One story: its board (every node it mentions) and its graph."""
        review_or_404(rid)
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
        named(out["board"].get("layers", []))
        if out["graph"]:
            named(out["graph"].get("layers", []))
        return out

    @app.get("/api/reviews/{rid}/locate")
    def locate(rid: int, node: str | None = None, flow: str | None = None, finding: str | None = None,
               _: str = Depends(user_of)):
        """The cluster to open for a node, flow or finding (null for a review shown as one board), and its story."""
        review_or_404(rid)
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
        """The review's graph, node files and stories (None before stories), for names and neighbours."""
        im = ImpactModel.model_validate(store.get_blob(rid, "impact") or {})
        return im, store.get_blob(rid, "node_files") or {}, boardstore.stories(store, rid)

    @app.get("/api/reviews/{rid}/names")
    def node_names(rid: int, _: str = Depends(user_of)):
        """A name for every node the UI can show (spec 2026-10-04-review-workspace §4.2): changed code, nodes on any
        board or story, findings' nodes and the nodes cited in flow, story, finding and summary text."""
        review_or_404(rid)
        im, depot_of, ss = shown(rid)
        ids, texts = set(im.changed), []
        for b in boardstore.boards(store, rid).values():
            ids |= {n.id for n in b.nodes} | {n for fl in b.flows for n in fl.path}
            texts += [t for fl in b.flows for t in (fl.what, fl.title, fl.text, fl.effect, fl.check)]
            texts += [b.about.intent, *(w.text for w in b.about.why)]
        for st in ss.stories if ss else []:
            texts += [st.title, st.summary]
            d = boardstore.story(store, rid, st.id)
            if d is not None:
                ids |= {n.id for n in d.board.nodes} | {n.id for n in (d.graph.nodes if d.graph else [])}
                texts += [f.note for f in d.functions]
        for f in store.list_findings(rid):
            ids |= set(f.nodes) | {n for e in f.evidence for n in e.nodes or []}
            ids |= {n for h in f.hypotheses for n in h.cites}
            texts += [f.summary, f.explanation, *f.verify_steps, *(h.text for h in f.hypotheses),
                      *(e.text for e in f.evidence)]
        return names(im, ids | cited(texts), depot_of, ss.node_story if ss else {})

    @app.get("/api/reviews/{rid}/nodes/{nid}/neighbours")
    def node_neighbours(rid: int, nid: str, limit: int = 20, callers: int | None = None, callees: int | None = None,
                        _: str = Depends(user_of)):
        """A node's callers and callees, the most affected first (spec 2026-10-04-review-workspace §4.3)."""
        review_or_404(rid)
        im, depot_of, ss = shown(rid)
        out = neighbours(im, nid, depot_of, ss.node_story if ss else {}, root=canon(str(cfg.workspace.root)), limit=limit,
                         callers=callers, callees=callees)
        if out is None:
            raise HTTPException(404, f"no node {nid} in this review")
        return out

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

    # ---- AI on demand (spec 2026-10-03) ---------------------------------------
    @app.post("/api/reviews/{rid}/explain", status_code=202)
    def explain(rid: int, body: ExplainIn, user: str = Depends(user_of)):
        review_or_404(rid)
        if svc.llm is None or svc.ledger is None:
            raise HTTPException(409, "no LLM is configured")
        if store.get_review(rid)["status"] not in TERMINAL:
            raise HTTPException(409, RERUNNING)
        try:
            ondemand.check_target(svc, rid, body.kind, body.target)
        except ondemand.NotFound as e:
            raise HTTPException(404, str(e)) from e
        same = next((j for j in runner.ai_jobs.get(rid, []) if j["status"] == "running" and j["kind"] == body.kind
                     and j["target"] == body.target), None)
        if same:                                       # someone is already asking: share that answer, pay once
            return same
        reason = svc.ledger.check(rid, user)
        if reason:
            raise HTTPException(429, reason)
        return runner.submit_ai(rid, user, body.kind, body.target,
                                lambda: ondemand.explain(svc, rid, user, body.kind, body.target))

    @app.get("/api/reviews/{rid}/ai")
    def ai_view(rid: int, user: str = Depends(user_of)):
        review_or_404(rid)
        b = cfg.llm.budget
        u = svc.ledger.usage(rid) if svc.ledger else {"used": 0, "budget": b.per_review, "by_person": {},
                                                      "by_purpose": {}, "calls": []}
        u.pop("calls", None)                           # polled while work is pending; the list is /ai/calls
        rounds = svc.ledger.rounds(rid) if svc.ledger else b.per_mention
        return {**u, "llm": svc.llm is not None, "me_today": svc.ledger.person_today(user) if svc.ledger else 0,
                "me_limit": b.per_person_daily, "per_mention": rounds, "is_owner": user == cfg.owner,
                "jobs": runner.ai_jobs.get(rid, []), "file_summaries": store.get_blob(rid, "file_summaries") or {}}

    @app.get("/api/reviews/{rid}/ai/calls")
    def ai_calls(rid: int, _: str = Depends(user_of)):
        review_or_404(rid)
        return svc.ledger.usage(rid)["calls"] if svc.ledger else []

    @app.put("/api/reviews/{rid}/ai/budget")
    def ai_budget(rid: int, body: BudgetIn, user: str = Depends(owner_of)):
        review_or_404(rid)
        svc.ledger.raise_budget(rid, body.budget, user)
        return {"budget": svc.ledger.budget(rid)}

    @app.put("/api/reviews/{rid}/ai/rounds")
    def ai_rounds(rid: int, body: RoundsIn, user: str = Depends(owner_of)):
        review_or_404(rid)
        svc.ledger.set_rounds(rid, body.rounds, user)
        return {"rounds": svc.ledger.rounds(rid)}

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
        c = store.add_comment(rid, user, body.body, body.anchor_kind, body.anchor, body.parent_id)
        if tortoise.mentions(body.body) and user != tortoise.AUTHOR:
            ask_tortoise(rid, user, c)
        return c

    def ask_tortoise(rid: int, user: str, question: dict) -> None:
        """Post tortoise's reply in the question's thread and answer it as a job (spec 2026-10-03 §5)."""
        root = question["parent_id"] or question["id"]
        reply = store.add_comment(rid, tortoise.AUTHOR, "thinking…", question["anchor_kind"], question["anchor"], root)
        base = {"pending": False, "read": [], "files": [], "calls": 0}
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
        runner.submit_ai(rid, user, "mention", str(reply["id"]),
                         lambda: tortoise.answer(svc, rid, user, question, reply["id"]))

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
