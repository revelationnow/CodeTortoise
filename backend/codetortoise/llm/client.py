"""LLM client with JSON output, retries, a raised limit for cut-off replies and one repair round.

It speaks one of three APIs: OpenAI-compatible chat completions ("chat"), the OpenAI Responses API ("responses") or the
Anthropic Messages API ("messages"), each at `base_url` plus its path."""
from __future__ import annotations

import copy
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
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
DEFAULT_BASE = 8192                   # the doubling base when no limit is configured (spec 2026-10-08-llm-robustness §4.3)
DEFAULT_CAP = 32768


class LlmError(RuntimeError):
    pass


class LlmUnreachable(LlmError):
    """Every attempt failed to reach the endpoint or got a server error: later calls this run will fare no better."""


class LlmLimitRejected(LlmError):
    """HTTP 400 on a request whose output limit was raised above the client's own: the model may allow no more."""

    def __init__(self, limit: int, text: str):
        super().__init__(f"LLM rejected a limit of {limit} tokens: {text[:300]}")
        self.limit = limit


class LlmTruncated(LlmError):
    """The reply stopped at its output-token limit (spec 2026-10-08-llm-robustness §4.1)."""

    def __init__(self, limit: int | None, completion: int | None):
        super().__init__(f"reply cut off at {limit} tokens" if limit else "reply cut off at the server's limit")
        self.limit, self.completion = limit, completion


def _extract_json(text: str) -> str:
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


class LlmClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120,
                 transport: httpx.BaseTransport | None = None, retries: int = 2,
                 sleep: Callable[[float], None] = time.sleep, temperature: float | None = None,
                 api: Api = "chat", max_output_tokens: int | None = None, cap: int = DEFAULT_CAP):
        self.model = model
        self.api = api
        self.max_output_tokens = max_output_tokens
        self._own = max_output_tokens             # the configured limit: a view falls back to it (with_start)
        self.cap = cap
        self._view = False                        # a per-try view keeps a raised limit (with_start)
        self.temperature = temperature           # None: the model's own default (some servers reject it)
        self.retries = retries
        self._sleep = sleep
        # what servers rejected, shared by every view (with_start): the format steps down to "json_schema" (e.g. LM
        # Studio) or "none" (the Messages API has none to ask for); the chat limit to "max_completion_tokens"
        self._learned = {"format": "none" if api == "messages" else "json_object", "limit_param": "max_tokens"}
        headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION} if api == "messages" else \
            {"Authorization": f"Bearer {api_key}"}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport, headers=headers)
        self._usage = threading.local()          # tokens reported by the responses of this thread's current call
        self._log = threading.local()            # this thread's HTTP attempts for the current call (start_log)
        self._url = self._http.base_url.path.rstrip("/")

    @property
    def base(self) -> int:
        """The limit a raise doubles from when none was sent."""
        return self.max_output_tokens or DEFAULT_BASE

    def with_start(self, limit: int | None) -> LlmClient:
        """A view for one try: the same connection, usage and log, its own starting limit, which stays raised once a
        cut-off reply raises it (spec 2026-10-08-llm-robustness §4.3, §5)."""
        v = copy.copy(self)
        v.max_output_tokens, v._view = limit, True
        return v

    def _raised(self, limit: int | None) -> int | None:
        """The limit after `limit`: doubled (from the base when none was sent) and capped; None when already at the cap."""
        nxt = min(self.cap, 2 * (limit or self.base))
        return nxt if limit is None or nxt > limit else None

    @staticmethod
    def _sent(body: dict) -> int | None:
        return body.get("max_tokens") or body.get("max_completion_tokens") or body.get("max_output_tokens")

    def _stop(self, data: dict) -> tuple[str | None, bool]:
        """The reply's stop reason as the API words it, and whether the output limit cut it off."""
        if self.api == "messages":
            stop = data.get("stop_reason")
            return stop, stop == "max_tokens"
        if self.api == "responses":
            status = data.get("status")
            reason = (data.get("incomplete_details") or {}).get("reason")
            return (reason or status) if status == "incomplete" else status, \
                status == "incomplete" and reason == "max_output_tokens"
        stop = data["choices"][0].get("finish_reason")
        return stop, stop == "length"

    def _response_format(self, schema: type[BaseModel] | None) -> dict | None:
        if self._learned["format"] == "json_object":
            return {"type": "json_object"}
        if self._learned["format"] == "json_schema" and schema is not None:
            return {"type": "json_schema",
                    "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}}
        return None

    def _body(self, system: str, user: str, rf: dict | None, limit: int | None) -> dict:
        if self.api == "messages":
            body = {"model": self.model, "system": system, "messages": [{"role": "user", "content": user}],
                    "max_tokens": limit or MESSAGES_MAX_TOKENS}
        elif self.api == "responses":
            body = {"model": self.model, "instructions": system, "input": user}
            if rf is not None:   # the Responses API takes the json_schema fields flat
                body["text"] = {"format": rf if rf["type"] == "json_object" else {"type": "json_schema", **rf["json_schema"]}}
            if limit:
                body["max_output_tokens"] = limit
        else:
            body = {"model": self.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if rf is not None:
                body["response_format"] = rf
            if limit:
                body[self._learned["limit_param"]] = limit
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
        return self._chat(system, user, schema, self.max_output_tokens)

    def _chat(self, system: str, user: str, schema: type[BaseModel] | None, limit: int | None,
              repair: bool = False) -> str:
        last: Exception | None = None
        attempt = steps = 0                       # a step-down (format, limit field) costs no attempt
        while attempt <= self.retries:
            rf = self._response_format(schema)
            body = self._body(system, user, rf, limit)
            rec = self._record(body, repair)
            t0 = time.monotonic()
            try:
                r = self._http.post(_PATHS[self.api], json=body)
            except httpx.HTTPError as e:
                if rec is not None:
                    rec.update(elapsed_ms=int((time.monotonic() - t0) * 1000), error=f"{type(e).__name__}: {e}")
                last = e
            else:
                if rec is not None:
                    rec.update(elapsed_ms=int((time.monotonic() - t0) * 1000), status=r.status_code, response=r.text)
                if (r.status_code == 400 and self.api == "chat" and limit and steps < 3
                        and self._learned["limit_param"] == "max_tokens"
                        and "max_tokens" in r.text and "max_completion_tokens" in r.text):
                    self._learned["limit_param"] = "max_completion_tokens"      # OpenAI's newer models name it so
                    steps += 1
                    continue
                if r.status_code == 400 and rf is not None and _FORMAT_PARAM[self.api] in r.text and steps < 3:
                    # server rejects this structured-output form: prefer json_schema if it asks for it, else plain text
                    wants_schema = self._learned["format"] == "json_object" and "json_schema" in r.text
                    self._learned["format"] = "json_schema" if wants_schema else "none"
                    steps += 1
                    continue
                if r.status_code < 500 and r.status_code != 429:
                    if r.status_code == 400 and limit and limit > (self._own or DEFAULT_BASE):
                        raise LlmLimitRejected(limit, r.text)
                    if r.status_code >= 400:
                        raise LlmError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
                    try:
                        data = r.json()
                        tokens = self._count(data)
                        text = self._text(data)
                        stop, cut = self._stop(data)
                    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
                        raise LlmError(f"unexpected LLM response: {r.text[:300]}") from e
                    if rec is not None:
                        rec.update(stop_reason=stop, truncated=cut, prompt_tokens=tokens[0] if tokens else None,
                                   completion_tokens=tokens[1] if tokens else None)
                    if cut:
                        raise LlmTruncated(self._sent(body), tokens[1] if tokens else None)
                    return text
                last = LlmError(f"LLM HTTP {r.status_code}")
            if attempt < self.retries:
                self._sleep(2 ** attempt)
            attempt += 1
        raise LlmUnreachable(f"LLM request failed after {self.retries + 1} attempts: {last}")

    def _count(self, data: dict) -> tuple[int, int] | None:
        """Adds the reply's reported tokens to this thread's usage; returns them (prompt, completion), or None."""
        u = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(u, dict):
            return None
        got = (int(u.get("prompt_tokens") or u.get("input_tokens") or 0),
               int(u.get("completion_tokens") or u.get("output_tokens") or 0))
        p, c = getattr(self._usage, "tokens", None) or (0, 0)
        self._usage.tokens = (p + got[0], c + got[1])
        return got

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        """One JSON answer. A reply cut off by the limit is sent again at double the limit (spec
        2026-10-08-llm-robustness §4.3); a complete but invalid one gets one repair round, also at double the limit."""
        system = system + "\n\nReply with a single JSON object matching this JSON schema:\n" + \
            json.dumps(schema.model_json_schema())
        limit, prompt, repaired, raising = self.max_output_tokens, user, False, True
        while True:
            try:
                text = self._chat(system, prompt, schema, limit, repaired)
            except LlmLimitRejected:
                # the model allows no more: send it again at the client's own limit, and raise no further this call
                limit, raising = self._own, False
                continue
            except LlmTruncated:
                nxt = self._raised(limit) if raising else None
                if nxt is None:
                    raise
                limit = nxt
                continue
            try:
                out = schema.model_validate_json(_extract_json(text))
            except ValidationError as e:
                if repaired:
                    raise LlmError(f"LLM returned invalid JSON twice: {str(e)[:300]}") from e
                log.debug("LLM JSON invalid, repairing: %s", e)
                repaired = True
                prompt = (user + "\n\nYour previous reply was:\n" + text[:4000] +
                          f"\n\nIt was invalid: {str(e)[:1000]}\nReply again with valid JSON only.")
                limit = (self._raised(limit) if raising else None) or limit
                continue
            if self._view:
                self.max_output_tokens = limit
            return out

    def start_log(self) -> None:
        self._log.records = []

    def take_log(self) -> list[dict]:
        """The HTTP attempts since start_log, on this thread (spec 2026-10-08-llm-robustness §4.4); [] if none was
        started. Headers are never recorded."""
        recs = getattr(self._log, "records", None) or []
        self._log.records = None
        return recs

    def _record(self, body: dict, repair: bool) -> dict | None:
        recs = getattr(self._log, "records", None)
        if recs is None:
            return None
        rec = {"seq": len(recs) + 1, "sent_at": datetime.now(UTC).isoformat(timespec="seconds"), "elapsed_ms": None,
               "url": self._url + _PATHS[self.api], "model": self.model, "status": None, "error": None,
               "stop_reason": None, "truncated": False, "repair": repair, "max_output_tokens": self._sent(body),
               "prompt_tokens": None, "completion_tokens": None, "request": body, "response": None}
        recs.append(rec)
        return rec

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
