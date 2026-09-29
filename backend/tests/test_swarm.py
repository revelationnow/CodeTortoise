import httpx
import pytest

from codetortoise.swarm import SwarmClient, SwarmError

REVIEW = {"id": 42, "state": "needsReview", "stateLabel": "Needs Review", "author": "bob",
          "participants": {"bob": [], "amy": {"vote": {"value": 1, "version": 2}}}}


def client(handler):
    return SwarmClient("https://swarm.example.com/", "anoop", "TICKET", transport=httpx.MockTransport(handler))


def test_get_review_for_change_normalizes():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json={"reviews": [REVIEW]})

    r = client(handler).get_review_for_change(123)
    assert r == {"id": 42, "state": "needsReview", "state_label": "Needs Review", "author": "bob",
                 "votes": {"amy": 1}, "url": "https://swarm.example.com/reviews/42"}
    assert "change%5B%5D=123" in seen["url"] and seen["auth"].startswith("Basic ")


def test_no_review_returns_none():
    assert client(lambda r: httpx.Response(200, json={"reviews": []})).get_review_for_change(1) is None


def test_create_and_comment_send_form_data():
    bodies = []

    def handler(req):
        bodies.append((req.method, req.url.path, req.content.decode()))
        if req.url.path.endswith("/reviews"):
            return httpx.Response(200, json={"review": REVIEW})
        return httpx.Response(200, json={"comment": {"id": 7}})

    c = client(handler)
    assert c.create_review(123, "desc")["id"] == 42
    assert c.post_comment(42, "hello world") == "7"
    assert bodies[0] == ("POST", "/api/v9/reviews", "change=123&description=desc")
    assert bodies[1] == ("POST", "/api/v9/comments", "topic=reviews%2F42&body=hello+world")


def test_http_error_raises():
    with pytest.raises(SwarmError, match="HTTP 403"):
        client(lambda r: httpx.Response(403, text="denied")).get_review_for_change(1)
