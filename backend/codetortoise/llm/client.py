"""OpenAI-compatible chat client with JSON output, retries and one repair round."""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LlmError(RuntimeError):
    pass


def _extract_json(text: str) -> str:
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


class LlmClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120,
                 transport: httpx.BaseTransport | None = None, retries: int = 2,
                 sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self.retries = retries
        self._sleep = sleep
        self._json_mode = True
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def chat(self, system: str, user: str) -> str:
        body = {"model": self.model, "temperature": 0.2,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            if self._json_mode:
                body["response_format"] = {"type": "json_object"}
            else:
                body.pop("response_format", None)
            try:
                r = self._http.post("/chat/completions", json=body)
            except httpx.HTTPError as e:
                last = e
            else:
                if r.status_code == 400 and self._json_mode and "response_format" in r.text:
                    self._json_mode = False
                    continue
                if r.status_code < 500 and r.status_code != 429:
                    if r.status_code >= 400:
                        raise LlmError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
                    try:
                        return r.json()["choices"][0]["message"]["content"] or ""
                    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
                        raise LlmError(f"unexpected LLM response: {r.text[:300]}") from e
                last = LlmError(f"LLM HTTP {r.status_code}")
            if attempt < self.retries:
                self._sleep(2 ** attempt)
        raise LlmError(f"LLM request failed after {self.retries + 1} attempts: {last}")

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        system = system + "\n\nReply with a single JSON object matching this JSON schema:\n" + \
            json.dumps(schema.model_json_schema())
        text = self.chat(system, user)
        try:
            return schema.model_validate_json(_extract_json(text))
        except ValidationError as e:
            log.debug("LLM JSON invalid, repairing: %s", e)
            repair = (user + "\n\nYour previous reply was:\n" + text[:4000] +
                      f"\n\nIt was invalid: {str(e)[:1000]}\nReply again with valid JSON only.")
            text = self.chat(system, repair)
            try:
                return schema.model_validate_json(_extract_json(text))
            except ValidationError as e2:
                raise LlmError(f"LLM returned invalid JSON twice: {str(e2)[:300]}") from e2

    def ping(self) -> bool:
        try:
            return self._http.get("/models").status_code < 500
        except httpx.HTTPError:
            return False
