import json

import httpx
import pytest
from pydantic import BaseModel

from codetortoise.llm.client import LlmClient, LlmError


class Out(BaseModel):
    answer: str
    n: int


def reply(content, status=200):
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


def client(handler, **kw):
    return LlmClient("http://llm/v1", "sk-test", "m", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def test_parses_json_and_sends_auth_and_response_format():
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return reply('{"answer": "ok", "n": 2}')

    out = client(handler).complete_json("sys", "user", Out)
    assert out == Out(answer="ok", n=2)
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][1] == {"role": "user", "content": "user"}


def test_accepts_fenced_json():
    out = client(lambda r: reply('Here:\n```json\n{"answer": "x", "n": 1}\n```')).complete_json("s", "u", Out)
    assert out.n == 1


def test_repairs_invalid_json_once():
    replies = iter(['{"answer": "x"}', '{"answer": "x", "n": 3}'])
    prompts = []

    def handler(req):
        prompts.append(json.loads(req.content)["messages"][1]["content"])
        return reply(next(replies))

    assert client(handler).complete_json("s", "u", Out).n == 3
    assert "invalid" in prompts[1]


def test_invalid_twice_raises():
    with pytest.raises(LlmError, match="invalid JSON twice"):
        client(lambda r: reply("not json")).complete_json("s", "u", Out)


def test_retries_5xx_then_succeeds():
    codes = iter([500, 503, 200])

    def handler(req):
        c = next(codes)
        return reply('{"answer": "a", "n": 1}') if c == 200 else httpx.Response(c, text="busy")

    assert client(handler).complete_json("s", "u", Out).answer == "a"


def test_gives_up_after_retries():
    with pytest.raises(LlmError, match="after 3 attempts"):
        client(lambda r: httpx.Response(502)).chat("s", "u")


def test_falls_back_when_response_format_unsupported():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, text="unknown field response_format")
        return reply('{"answer": "a", "n": 1}')

    assert client(handler).complete_json("s", "u", Out).n == 1
    assert "response_format" not in bodies[-1]


def test_4xx_is_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, text="bad key")

    with pytest.raises(LlmError, match="401"):
        client(handler).chat("s", "u")
    assert len(calls) == 1


@pytest.mark.parametrize("body", [{"choices": [{"message": None}]}, {"choices": None}, [1, 2], {"choices": [{}]}])
def test_malformed_success_bodies_raise_llm_error(body):
    with pytest.raises(LlmError, match="unexpected LLM response"):
        client(lambda r: httpx.Response(200, json=body)).chat("s", "u")
