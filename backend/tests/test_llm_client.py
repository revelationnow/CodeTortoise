import json

import httpx
import pytest
from pydantic import BaseModel

from codetortoise.llm.client import LlmClient, LlmError, LlmTruncated, LlmUnreachable


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
    assert "temperature" not in seen["body"]          # some servers reject it; each model's own default applies


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


def test_an_endpoint_that_never_answers_is_unreachable():
    def handler(req):
        raise httpx.ReadTimeout("timed out", request=req)
    with pytest.raises(LlmUnreachable, match="after 3 attempts: timed out"):
        client(handler).chat("s", "u")
    with pytest.raises(LlmUnreachable):
        client(lambda r: httpx.Response(503)).chat("s", "u")


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


def test_switches_to_json_schema_when_server_requires_it():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        rf = body.get("response_format", {})
        if rf.get("type") == "json_object":
            return httpx.Response(400, json={"error": "'response_format.type' must be 'json_schema' or 'text'"})
        return reply('{"answer": "a", "n": 1}')

    c = client(handler)
    assert c.complete_json("s", "u", Out).n == 1
    rf = bodies[-1]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["name"] == "Out"
    assert rf["json_schema"]["schema"]["required"] == ["answer", "n"]
    c.complete_json("s", "u", Out)
    assert len(bodies) == 3  # the mode is remembered: no second rejected request


def test_a_temperature_is_sent_only_when_set():
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return reply('{"answer": "ok", "n": 2}')
    client(handler, temperature=0).complete_json("s", "u", Out)
    client(handler).complete_json("s", "u", Out)
    assert seen[0]["temperature"] == 0 and "temperature" not in seen[1]


def responses_reply(text, usage=None):
    return httpx.Response(200, json={"output": [{"type": "reasoning", "summary": []},
                                                {"type": "message", "content": [{"type": "output_text", "text": text}]}],
                                     "usage": usage or {}})


def messages_reply(text, usage=None):
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}], "usage": usage or {}})


def test_the_responses_api_sends_instructions_and_input_and_reads_the_output_message():
    seen = {}

    def handler(req):
        seen.update(path=req.url.path, auth=req.headers["authorization"], body=json.loads(req.content))
        return responses_reply('{"answer": "ok", "n": 2}', {"input_tokens": 120, "output_tokens": 30})

    c = client(handler, api="responses", temperature=0)
    c.start_usage()
    assert c.complete_json("sys", "user", Out) == Out(answer="ok", n=2)
    assert (seen["path"], seen["auth"]) == ("/v1/responses", "Bearer sk-test")
    body = seen["body"]
    assert body["model"] == "m" and body["input"] == "user" and body["instructions"].startswith("sys")
    assert body["text"] == {"format": {"type": "json_object"}} and body["temperature"] == 0
    assert "messages" not in body and "response_format" not in body and "max_output_tokens" not in body
    assert c.take_usage() == (120, 30)


def test_the_responses_api_moves_to_a_json_schema_then_to_plain_text_as_the_server_rejects_formats():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        fmt = body.get("text", {}).get("format", {}).get("type")
        if fmt == "json_object":
            return httpx.Response(400, json={"error": {"message": "Invalid 'text.format': use json_schema"}})
        if fmt == "json_schema":
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'text.format'"}})
        return responses_reply('{"answer": "a", "n": 1}')

    assert client(handler, api="responses").complete_json("s", "u", Out).n == 1
    assert bodies[1]["text"]["format"]["name"] == "Out" and bodies[1]["text"]["format"]["schema"]["required"] == ["answer", "n"]
    assert "text" not in bodies[2]


def test_the_messages_api_sends_the_key_its_version_and_a_token_limit_and_reads_the_text_blocks():
    seen = {}

    def handler(req):
        seen.update(path=req.url.path, headers=req.headers, body=json.loads(req.content))
        return httpx.Response(200, json={"content": [{"type": "thinking", "thinking": "hm"},
                                                     {"type": "text", "text": '{"answer": "ok",'},
                                                     {"type": "text", "text": ' "n": 2}'}],
                                         "usage": {"input_tokens": 50, "output_tokens": 9}})

    c = client(handler, api="messages")
    c.start_usage()
    assert c.complete_json("sys", "user", Out) == Out(answer="ok", n=2)
    assert seen["path"] == "/v1/messages" and "authorization" not in seen["headers"]
    assert (seen["headers"]["x-api-key"], seen["headers"]["anthropic-version"]) == ("sk-test", "2023-06-01")
    body = seen["body"]
    assert body["system"].startswith("sys") and body["messages"] == [{"role": "user", "content": "user"}]
    assert body["max_tokens"] == 8192 and "response_format" not in body and "temperature" not in body
    assert c.take_usage() == (50, 9)
    client(handler, api="messages", max_output_tokens=2000).chat("s", "u")
    assert seen["body"]["max_tokens"] == 2000


def test_a_token_limit_goes_to_the_responses_api_as_max_output_tokens():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return responses_reply("hi")
    assert client(handler, api="responses", max_output_tokens=3000).chat("s", "u") == "hi"
    assert seen["max_output_tokens"] == 3000


@pytest.mark.parametrize("api,body", [("responses", {"output": None}), ("responses", {"output": [{"type": "message"}]}),
                                      ("messages", {"content": None}), ("messages", [1])])
def test_malformed_responses_and_messages_bodies_raise_llm_error(api, body):
    with pytest.raises(LlmError, match="unexpected LLM response"):
        client(lambda r: httpx.Response(200, json=body), api=api).chat("s", "u")


def cut(content="{", completion=7):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "length"}],
                                     "usage": {"prompt_tokens": 10, "completion_tokens": completion}})


def test_a_reply_cut_off_by_the_limit_is_sent_again_with_double_the_limit_and_no_repair():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        return cut('{"answer": "x"') if body["max_tokens"] < 4000 else reply('{"answer": "x", "n": 1}')
    assert client(handler, max_output_tokens=1000).complete_json("s", "u", Out).n == 1
    assert [b["max_tokens"] for b in bodies] == [1000, 2000, 4000]
    assert all(b["messages"][1]["content"] == "u" for b in bodies)        # sent again as it was: no repair round


def test_a_short_reply_cut_off_by_the_limit_is_still_cut_off():
    # a reasoning model spends the limit thinking: two visible tokens, cut off all the same
    with pytest.raises(LlmTruncated):
        client(lambda r: cut("{", completion=2), max_output_tokens=1000, cap=1000).complete_json("s", "u", Out)


def test_a_reply_cut_off_at_the_cap_fails_with_llm_truncated():
    with pytest.raises(LlmTruncated, match="reply cut off at 2000 tokens") as e:
        client(lambda r: cut(), max_output_tokens=1000, cap=2000).complete_json("s", "u", Out)
    assert (e.value.limit, e.value.completion) == (2000, 7)


def test_with_no_limit_set_a_cut_off_reply_is_sent_again_from_the_base():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return cut() if len(bodies) == 1 else reply('{"answer": "x", "n": 1}')
    assert client(handler).complete_json("s", "u", Out).n == 1
    assert "max_tokens" not in bodies[0] and bodies[1]["max_tokens"] == 16384


def test_a_complete_but_invalid_reply_is_repaired_with_double_the_limit():
    replies = iter(['{"answer": "x"}', '{"answer": "x", "n": 3}'])
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return reply(next(replies))
    assert client(handler, max_output_tokens=1000).complete_json("s", "u", Out).n == 3
    assert [b["max_tokens"] for b in bodies] == [1000, 2000] and "invalid" in bodies[1]["messages"][1]["content"]


@pytest.mark.parametrize("api,data", [
    ("chat", {"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}),
    ("messages", {"content": [{"type": "text", "text": "{"}], "stop_reason": "max_tokens"}),
    ("responses", {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
                   "output": [{"type": "message", "content": [{"type": "output_text", "text": "{"}]}]}),
])
def test_each_api_says_when_a_reply_was_cut_off(api, data):
    with pytest.raises(LlmTruncated):
        client(lambda r: httpx.Response(200, json=data), api=api, max_output_tokens=1000).chat("s", "u")


@pytest.mark.parametrize("api,data", [
    ("chat", {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}),
    ("messages", {"content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn"}),
    ("responses", {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "hi"}]}]}),
])
def test_other_stop_reasons_change_nothing(api, data):
    assert client(lambda r: httpx.Response(200, json=data), api=api).chat("s", "u") == "hi"


def test_the_chat_api_sends_its_limit_as_max_tokens_and_moves_to_max_completion_tokens_when_told():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "max_tokens" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'max_tokens' is not supported "
                                                                  "with this model. Use 'max_completion_tokens' instead."}})
        return reply("hi")
    c = client(handler, max_output_tokens=3000)
    assert c.chat("s", "u") == "hi" and c.chat("s", "u") == "hi"
    assert [("max_tokens" in b, b.get("max_completion_tokens")) for b in bodies] == [(True, None), (False, 3000), (False, 3000)]
