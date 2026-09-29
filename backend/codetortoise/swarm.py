"""Minimal P4 Swarm REST client (API v9): read review, create review, post comment."""
from __future__ import annotations

import httpx


class SwarmError(RuntimeError):
    pass


def _summary(base: str, r: dict) -> dict:
    votes = {}
    participants = r.get("participants") or {}
    if isinstance(participants, dict):
        for user, p in participants.items():
            vote = (p or {}).get("vote") if isinstance(p, dict) else None
            if isinstance(vote, dict):
                votes[user] = vote.get("value", 0)
    return {"id": r.get("id"), "state": r.get("state"), "state_label": r.get("stateLabel", r.get("state")),
            "author": r.get("author"), "votes": votes, "url": f"{base}/reviews/{r.get('id')}"}


class SwarmClient:
    def __init__(self, base_url: str, user: str, ticket: str, transport: httpx.BaseTransport | None = None,
                 timeout: float = 30):
        self.base = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base, auth=(user, ticket), timeout=timeout, transport=transport)

    def _req(self, method: str, path: str, **kw) -> dict:
        try:
            r = self._http.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise SwarmError(f"swarm {method} {path}: {e}") from e
        if r.status_code >= 400:
            raise SwarmError(f"swarm {method} {path}: HTTP {r.status_code} {r.text[:300]}")
        return r.json()

    def get_review_for_change(self, cl: int) -> dict | None:
        data = self._req("GET", "/api/v9/reviews", params={"change[]": cl, "max": 1})
        reviews = data.get("reviews") or []
        return _summary(self.base, reviews[0]) if reviews else None

    def create_review(self, cl: int, description: str) -> dict:
        data = self._req("POST", "/api/v9/reviews", data={"change": cl, "description": description})
        return _summary(self.base, data.get("review") or {})

    def post_comment(self, review_id: int | str, body: str) -> str:
        data = self._req("POST", "/api/v9/comments", data={"topic": f"reviews/{review_id}", "body": body})
        return str((data.get("comment") or {}).get("id", ""))

    def version(self) -> dict:
        return self._req("GET", "/api/version")
