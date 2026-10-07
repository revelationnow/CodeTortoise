"""LLM client with JSON output, retries and one repair round.

It speaks one of three APIs: OpenAI-compatible chat completions ("chat"), the OpenAI Responses API ("responses") or the
Anthropic Messages API ("messages"), each at `base_url` plus its path."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
Api = Literal["chat", "responses", "messages"]
_PATHS = {"chat": "/chat/completions", "responses": "/responses", "messages": "/messages"}
_FORMAT_PARAM = {"chat": "response_format", "responses": "format"}   # the word a server's rejection names
ANTHROPIC_VERSION = "2023-06-01"
MESSAGES_MAX_TOKENS = 8192            # the Messages API requires a limit; used when none is configured


class LlmError(RuntimeError):
    pass


class LlmUnreachable(LlmError):
    """Every attempt failed to reach the endpoint or got a server error: later calls this run will fare no better."""


def _extract_json(text: str) -> str:
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


class LlmClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120,
                 transport: httpx.BaseTransport | None = None, retries: int = 2,
                 sleep: Callable[[float], None] = time.sleep, temperature: float | None = None,
                 api: Api = "chat", max_output_tokens: int | None = None):
        self.model = model
        self.api = api
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature           # None: the model's own default (some servers reject it)
        self.retries = retries
        self._sleep = sleep
        # -> "json_schema" (e.g. LM Studio) or "none" as servers reject formats; the Messages API has none to ask for
        self._format = "none" if api == "messages" else "json_object"
        headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION} if api == "messages" else \
            {"Authorization": f"Bearer {api_key}"}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport, headers=headers)
        self._usage = threading.local()          # tokens reported by the responses of this thread's current call

    def _response_format(self, schema: type[BaseModel] | None) -> dict | None:
        if self._format == "json_object":
            return {"type": "json_object"}
        if self._format == "json_schema" and schema is not None:
            return {"type": "json_schema",
                    "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}}
        return None

    def _body(self, system: str, user: str, rf: dict | None) -> dict:
        if self.api == "messages":
            body = {"model": self.model, "system": system, "messages": [{"role": "user", "content": user}],
                    "max_tokens": self.max_output_tokens or MESSAGES_MAX_TOKENS}
        elif self.api == "responses":
            body = {"model": self.model, "instructions": system, "input": user}
            if rf is not None:   # the Responses API takes the json_schema fields flat
                body["text"] = {"format": rf if rf["type"] == "json_object" else {"type": "json_schema", **rf["json_schema"]}}
            if self.max_output_tokens:
                body["max_output_tokens"] = self.max_output_tokens
        else:
            body = {"model": self.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if rf is not None:
                body["response_format"] = rf
        if self.temperature is not None:
            body["temperature"] = self.temperature
        return body

    def _text(self, data: dict) -> str:
        if self.api == "messages":
            return "".join(b["text"] for b in data["content"] if b.get("type") == "text")
        if self.api == "responses":
            return "".join(c["text"] for item in data["output"] if item.get("type") == "message"
                           for c in item["content"] if c.get("type") == "output_text")
        return data["choices"][0]["message"]["content"] or ""

    def chat(self, system: str, user: str, schema: type[BaseModel] | None = None) -> str:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            rf = self._response_format(schema)
            body = self._body(system, user, rf)
            try:
                r = self._http.post(_PATHS[self.api], json=body)
            except httpx.HTTPError as e:
                last = e
            else:
                if r.status_code == 400 and rf is not None and _FORMAT_PARAM[self.api] in r.text:
                    # server rejects this structured-output form: prefer json_schema if it asks for it, else plain text
                    wants_schema = self._format == "json_object" and "json_schema" in r.text
                    self._format = "json_schema" if wants_schema else "none"
                    continue
                if r.status_code < 500 and r.status_code != 429:
                    if r.status_code >= 400:
                        raise LlmError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
                    try:
                        data = r.json()
                        u = data.get("usage") if isinstance(data, dict) else None
                        if isinstance(u, dict):
                            p, c = getattr(self._usage, "tokens", None) or (0, 0)
                            self._usage.tokens = (p + int(u.get("prompt_tokens") or u.get("input_tokens") or 0),
                                                  c + int(u.get("completion_tokens") or u.get("output_tokens") or 0))
                        return self._text(data)
                    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
                        raise LlmError(f"unexpected LLM response: {r.text[:300]}") from e
                last = LlmError(f"LLM HTTP {r.status_code}")
            if attempt < self.retries:
                self._sleep(2 ** attempt)
        raise LlmUnreachable(f"LLM request failed after {self.retries + 1} attempts: {last}")

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        system = system + "\n\nReply with a single JSON object matching this JSON schema:\n" + \
            json.dumps(schema.model_json_schema())
        text = self.chat(system, user, schema)
        try:
            return schema.model_validate_json(_extract_json(text))
        except ValidationError as e:
            log.debug("LLM JSON invalid, repairing: %s", e)
            repair = (user + "\n\nYour previous reply was:\n" + text[:4000] +
                      f"\n\nIt was invalid: {str(e)[:1000]}\nReply again with valid JSON only.")
            text = self.chat(system, repair, schema)
            try:
                return schema.model_validate_json(_extract_json(text))
            except ValidationError as e2:
                raise LlmError(f"LLM returned invalid JSON twice: {str(e2)[:300]}") from e2

    def start_usage(self) -> None:
        self._usage.tokens = None

    def take_usage(self) -> tuple[int, int] | None:
        """(prompt, completion) tokens the responses reported since start_usage, on this thread; None if none did."""
        t = getattr(self._usage, "tokens", None)
        self._usage.tokens = None
        return t

    def ping(self) -> bool:
        try:
            return self._http.get("/models").status_code < 500
        except httpx.HTTPError:
            return False
