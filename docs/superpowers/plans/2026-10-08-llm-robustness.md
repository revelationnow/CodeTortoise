# LLM Robustness and Request Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reply cut off by the output limit is retried with a higher limit; a failed strong-model call is tried
fresh, then on the weak model, before the stage's own fallback; every HTTP request to a model can be logged, read
from the CLI and downloaded from the AI usage view.

**Architecture:** `LlmClient` reads each reply's stop reason, raises `LlmTruncated`, doubles its limit per request and
records every HTTP attempt in a thread-local list. A new `llm/tiers.py` runs one piece of strong-model work through
its tries (strong, strong fresh, weak), each a separate ledger call. `Ledger.call` hands the attempt records to a new
`llm/request_log.py`, which stores, prunes, reads and exports them; the CLI and a zip endpoint use the same reader.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, httpx, SQLite (backend); React 19 + TypeScript, vitest, Playwright
(frontend).

**Spec:** `docs/superpowers/specs/2026-10-08-llm-robustness-design.md`

## Global Constraints

- Work in the worktree `/media/anoop/ssd_1/Work/CodeTortoise/.worktrees/llm-robust` on branch `llm-robust`.
- Python: run from `backend/` with
  `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest …` and lint with
  `/media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/ruff check codetortoise tests`. Never `uv`.
- Commit with `git -c user.email=2929430+revelationnow@users.noreply.github.com commit` and end every message with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Headers are never recorded: the `Authorization` and `x-api-key` values never reach a record (spec §4.4).
- Config fields and defaults, verbatim from spec §3: `request_log: all  # all | failed | off`,
  `request_log_days: 14`, `max_output_tokens_cap: 32768`.
- The doubling base when no limit is configured is 8192 (spec §4.3).
- Tries, verbatim from spec §5: strong at its own starting limit; strong fresh starting at `min(cap, 2 × strong.base)`;
  weak starting at `min(cap, 4 × max(weak.base, strong.base))`.
- Note wording follows spec §6: `<prefix>: <failure>; <failure>; <outcome>`; a strong try is labelled with its
  model, a fresh try with `fresh try`, a weak try with its model.
- e2e: `npm run build` first; run Playwright with `TMPDIR=$CLAUDE_JOB_DIR/tmp/pw` and
  `TORTOISE_CMD="env PYTHONPATH=<worktree>/backend /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli"`.
  The first full run often has one `startReview` 60 s timeout; it passes on `--last-failed`.

## Review Focus

1. A reasoning model whose hidden reasoning eats the limit: a reply cut off with only a few visible tokens must still
   raise `LlmTruncated` (the stop reason decides, not the length) — Task 1 tests a short cut-off reply.
2. A view's raised limit must never leak into the shared client that weak-model explanations use concurrently —
   Task 2 tests that the shared client keeps its own limit.
3. A request that fails at the network level (no response) must still be logged with its error — Task 2 and Task 3
   test it.
4. `request_log: failed` must keep a call whose reply was cut off and then recovered (the call succeeded) — Task 3
   tests it.
5. Weak-model work judged on a story must not mark the story reviewed, or a re-run would never ask the strong model
   again — Task 5 tests `out.reviewed`.

---

## File Structure

- `backend/codetortoise/config.py` — `LlmConfig` gains `request_log`, `request_log_days`, `max_output_tokens_cap`.
- `backend/codetortoise/llm/client.py` — stop reason, `LlmTruncated`, chat limit field, limit doubling, per-try views,
  attempt records.
- `backend/codetortoise/services.py` — passes the cap to both clients and the log settings to the ledger.
- `backend/codetortoise/store.py` — `llm_calls.model` migration, `llm_requests` table.
- `backend/codetortoise/llm/request_log.py` (new) — keep / write / prune / rows / files / zip / line.
- `backend/codetortoise/llm/ledger.py` — records the model, logs requests, prunes, counts requests per call.
- `backend/codetortoise/llm/tiers.py` (new) — `try_tiers`, `Tried`, `TiersFailed`, `failure_text`, `tried_note`,
  `done_text`.
- `backend/codetortoise/llm/stories.py`, `llm/review.py`, `llm/threads.py`, `pipeline.py` — the four call sites.
- `backend/codetortoise/cli.py` — `llm-log`.
- `backend/codetortoise/web/app.py` — `/ai/requests.zip`, prune at start.
- `backend/tests/scripted_llm.py` — the test model gains the client's new surface.
- `frontend/src/api.ts`, `frontend/src/components/requestLog.ts` (new), `frontend/src/components/AiPill.tsx`.
- `frontend/e2e/fake_llm.py`, `frontend/e2e/serve-strong.sh`, `frontend/e2e/workspace-tier1.spec.ts`.
- `README.md` — the new config keys.

---

### Task 1: The client knows a cut-off reply and raises its limit

**Files:**
- Modify: `backend/codetortoise/config.py:83-98` (`LlmConfig`)
- Modify: `backend/codetortoise/llm/client.py`
- Modify: `backend/codetortoise/services.py:103-117`
- Modify: `README.md:181`
- Test: `backend/tests/test_llm_client.py`, `backend/tests/test_config.py`

**Interfaces:**
- Produces: `LlmTruncated(LlmError)` with `.limit: int | None`, `.completion: int | None`, message
  `"reply cut off at {limit} tokens"` (or `"reply cut off at the server's limit"` when no limit was sent);
  `LlmClient(..., cap: int = 32768)`; `LlmClient.cap: int`; `LlmClient.base -> int` (property:
  `max_output_tokens or 8192`); `LlmClient.with_start(limit: int | None) -> LlmClient`;
  `DEFAULT_BASE = 8192`, `DEFAULT_CAP = 32768` in `llm/client.py`;
  `LlmConfig.max_output_tokens_cap: int = 32768`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_llm_client.py` (extend the import to
`from codetortoise.llm.client import LlmClient, LlmError, LlmTruncated, LlmUnreachable`):

```python
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
```

Add to `backend/tests/test_config.py` (after the test that checks `max_output_tokens`):

```python
def test_the_output_token_cap_defaults_to_32768_and_reaches_both_clients():
    base = {"workspace": {"root": "/w", "compile_commands": "auto"}}
    assert Config.model_validate(base).llm.max_output_tokens_cap == 32768
    cfg = Config.model_validate({**base, "llm": {"base_url": "https://x/v1", "model": "m", "max_output_tokens_cap": 16000,
                                                 "strong": {"base_url": "https://a/v1", "model": "big"}}})
    assert (make_llm(cfg).cap, make_strong(cfg).cap) == (16000, 16000)
```

(`Config`, `make_llm`, `make_strong` are already imported in that file; check its imports and add any missing.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_llm_client.py tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'LlmTruncated'` (collection error for test_llm_client.py) and
`max_output_tokens_cap` missing in test_config.py.

- [ ] **Step 3: Add the config field**

In `backend/codetortoise/config.py`, `LlmConfig`, after `max_output_tokens`:

```python
    max_output_tokens_cap: int = 32768   # no try asks either model for more output tokens than this
```

- [ ] **Step 4: Implement the client changes**

In `backend/codetortoise/llm/client.py`:

1. Imports: add `import copy`.
2. Constants after `MESSAGES_MAX_TOKENS`:

```python
DEFAULT_BASE = 8192                   # the doubling base when no limit is configured (spec 2026-10-08-llm-robustness §4.3)
DEFAULT_CAP = 32768
```

3. After `class LlmUnreachable`:

```python
class LlmTruncated(LlmError):
    """The reply stopped at its output-token limit (spec 2026-10-08-llm-robustness §4.1)."""

    def __init__(self, limit: int | None, completion: int | None):
        super().__init__(f"reply cut off at {limit} tokens" if limit else "reply cut off at the server's limit")
        self.limit, self.completion = limit, completion
```

4. `__init__`: add the parameter `cap: int = DEFAULT_CAP` after `max_output_tokens`, and in the body:

```python
        self.cap = cap
        self._limit_param = "max_tokens"          # -> "max_completion_tokens" when a chat server asks for it
        self._view = False                        # a per-try view keeps a raised limit (with_start)
```

5. Add after `__init__`:

```python
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
```

6. `_body` takes the limit:

```python
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
                body[self._limit_param] = limit
        if self.temperature is not None:
            body["temperature"] = self.temperature
        return body
```

7. Replace `chat` with `chat` + `_chat`:

```python
    def chat(self, system: str, user: str, schema: type[BaseModel] | None = None) -> str:
        return self._chat(system, user, schema, self.max_output_tokens)

    def _chat(self, system: str, user: str, schema: type[BaseModel] | None, limit: int | None) -> str:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            rf = self._response_format(schema)
            body = self._body(system, user, rf, limit)
            try:
                r = self._http.post(_PATHS[self.api], json=body)
            except httpx.HTTPError as e:
                last = e
            else:
                if (r.status_code == 400 and self.api == "chat" and limit and self._limit_param == "max_tokens"
                        and "max_tokens" in r.text and "max_completion_tokens" in r.text):
                    self._limit_param = "max_completion_tokens"      # OpenAI's newer models name the limit so
                    continue
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
                        tokens = self._count(data)
                        text = self._text(data)
                        _stop, cut = self._stop(data)
                    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
                        raise LlmError(f"unexpected LLM response: {r.text[:300]}") from e
                    if cut:
                        raise LlmTruncated(self._sent(body), tokens[1] if tokens else None)
                    return text
                last = LlmError(f"LLM HTTP {r.status_code}")
            if attempt < self.retries:
                self._sleep(2 ** attempt)
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
```

8. Replace `complete_json`:

```python
    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        """One JSON answer. A reply cut off by the limit is sent again at double the limit (spec
        2026-10-08-llm-robustness §4.3); a complete but invalid one gets one repair round, also at double the limit."""
        system = system + "\n\nReply with a single JSON object matching this JSON schema:\n" + \
            json.dumps(schema.model_json_schema())
        limit, prompt, repaired = self.max_output_tokens, user, False
        while True:
            try:
                text = self._chat(system, prompt, schema, limit)
            except LlmTruncated:
                nxt = self._raised(limit)
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
                limit = self._raised(limit) or limit
                continue
            if self._view:
                self.max_output_tokens = limit
            return out
```

Update the module docstring's first line to: `"""LLM client with JSON output, retries, a raised limit for cut-off replies and one repair round.`

- [ ] **Step 5: Pass the cap to both clients**

In `backend/codetortoise/services.py`, `make_llm`: add `cap=cfg.llm.max_output_tokens_cap` to the `LlmClient(...)` call;
`make_strong`: add `cap=cfg.llm.max_output_tokens_cap` likewise.

- [ ] **Step 6: README**

In `README.md`, replace line 181 with:

```yaml
  # max_output_tokens: 8192         # reply token limit; messages needs one (8192 when unset), others send it only if set
  # max_output_tokens_cap: 32768    # a reply cut off by its limit is sent again at double the limit, up to this
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_llm_client.py tests/test_config.py tests/test_ledger.py -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/llm/client.py backend/codetortoise/services.py README.md backend/tests/test_llm_client.py backend/tests/test_config.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(llm): a reply cut off by its token limit is sent again at double the limit, not repaired; the chat API sends the limit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The client records every HTTP attempt

**Files:**
- Modify: `backend/codetortoise/llm/client.py`
- Modify: `backend/tests/scripted_llm.py`
- Test: `backend/tests/test_llm_client.py`

**Interfaces:**
- Consumes: Task 1's `_chat`, `with_start`.
- Produces: `LlmClient.start_log() -> None`, `LlmClient.take_log() -> list[dict]`. Each record has exactly the keys
  `seq, sent_at, elapsed_ms, url, model, status, error, stop_reason, truncated, repair, max_output_tokens,
  prompt_tokens, completion_tokens, request, response` (`request` a dict, `response` a str or None).
  `ScriptedLlm` gains `max_output_tokens = None`, `cap = 32768`, `base` (property, 8192), `with_start(limit)` (returns
  itself), `start_log()`, `take_log()` (returns `[]`).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_llm_client.py` (add `import itertools` at the top):

```python
def test_each_http_attempt_is_recorded_without_the_key():
    n = itertools.count()

    def handler(req):
        if next(n) == 0:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer": "x", "n": 1}'},
                                                      "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 11, "completion_tokens": 4}})
    c = client(handler, max_output_tokens=500)
    c.start_log()
    c.complete_json("s", "u", Out)
    recs = c.take_log()
    assert [(r["seq"], r["status"], r["stop_reason"], r["truncated"], r["repair"]) for r in recs] == [
        (1, 503, None, False, False), (2, 200, "stop", False, False)]
    r = recs[1]
    assert set(r) == {"seq", "sent_at", "elapsed_ms", "url", "model", "status", "error", "stop_reason", "truncated",
                      "repair", "max_output_tokens", "prompt_tokens", "completion_tokens", "request", "response"}
    assert (r["url"], r["model"], r["max_output_tokens"]) == ("/v1/chat/completions", "m", 500)
    assert (r["prompt_tokens"], r["completion_tokens"]) == (11, 4) and r["request"]["messages"][1]["content"] == "u"
    assert json.loads(r["response"])["choices"][0]["finish_reason"] == "stop"
    assert r["elapsed_ms"] >= 0 and r["sent_at"].startswith("20") and recs[0]["response"] == "busy"
    assert "sk-test" not in json.dumps(recs)
    assert c.take_log() == []                                                # taken: cleared


def test_a_network_error_a_cut_off_reply_and_a_repair_are_recorded():
    n = itertools.count()

    def handler(req):
        i = next(n)
        if i == 0:
            raise httpx.ConnectError("refused")
        if i == 1:
            return cut()
        if i == 2:
            return reply('{"answer": "x"}')
        return reply('{"answer": "x", "n": 1}')
    c = client(handler, max_output_tokens=1000)
    c.start_log()
    c.complete_json("s", "u", Out)
    recs = c.take_log()
    assert [(r["status"], r["truncated"], r["repair"], r["max_output_tokens"]) for r in recs] == [
        (None, False, False, 1000), (200, True, False, 1000), (200, False, False, 2000), (200, False, True, 4000)]
    assert recs[0]["error"] == "ConnectError: refused" and recs[0]["response"] is None
    assert recs[1]["stop_reason"] == "length"


def test_nothing_is_recorded_unless_a_log_was_started():
    c = client(lambda r: reply('{"answer": "x", "n": 1}'))
    c.complete_json("s", "u", Out)
    assert c.take_log() == []


def test_a_view_shares_the_log_and_keeps_a_raised_limit_for_the_rest_of_its_try():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body["max_tokens"])
        return cut() if body["max_tokens"] < 2000 else reply('{"answer": "x", "n": 1}')
    c = client(handler, max_output_tokens=1000)
    v = c.with_start(1000)
    c.start_log()
    v.complete_json("s", "u", Out)
    v.complete_json("s", "u", Out)
    assert bodies == [1000, 2000, 2000] and len(c.take_log()) == 3
    bodies.clear()
    c.complete_json("s", "u", Out)
    c.complete_json("s", "u", Out)
    assert bodies == [1000, 2000, 1000, 2000] and c.max_output_tokens == 1000     # the shared client keeps its own
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_llm_client.py -q -k "recorded or view"`
Expected: FAIL — `AttributeError: 'LlmClient' object has no attribute 'start_log'`.

- [ ] **Step 3: Implement the records**

In `backend/codetortoise/llm/client.py`:

1. Imports: add `from datetime import UTC, datetime`.
2. `__init__` body, after `self._usage = ...`:

```python
        self._log = threading.local()            # this thread's HTTP attempts for the current call (start_log)
        self._url = self._http.base_url.path.rstrip("/")
```

3. Methods (next to `start_usage`):

```python
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
```

4. `_chat` gains `repair: bool = False` as its last parameter, and records each attempt. The loop body becomes:

```python
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
                ... (the existing branches from Task 1, unchanged, except the success branch below)
```

and the success branch, after computing `tokens`, `text`, `_stop, cut` (rename `_stop` to `stop`):

```python
                    if rec is not None:
                        rec.update(stop_reason=stop, truncated=cut, prompt_tokens=tokens[0] if tokens else None,
                                   completion_tokens=tokens[1] if tokens else None)
                    if cut:
                        raise LlmTruncated(self._sent(body), tokens[1] if tokens else None)
                    return text
```

5. In `complete_json`, call `self._chat(system, prompt, schema, limit, repaired)` (the repair flag marks the requests
   of the repair round).

- [ ] **Step 4: Give the scripted test model the client's new surface**

In `backend/tests/scripted_llm.py`, inside `class ScriptedLlm`:

```python
    max_output_tokens = None
    cap = 32768

    @property
    def base(self):
        return 8192

    def with_start(self, limit):
        return self

    def start_log(self):
        pass

    def take_log(self):
        return []
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_llm_client.py tests/test_ledger.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/llm/client.py backend/tests/scripted_llm.py backend/tests/test_llm_client.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(llm): the client records every HTTP attempt of a call — body, reply, status, stop reason, limit, tokens, timing — never its headers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The request log is stored, pruned and read

**Files:**
- Modify: `backend/codetortoise/config.py` (`LlmConfig`)
- Modify: `backend/codetortoise/store.py:34-36` (schema), `:76-79` (migration)
- Create: `backend/codetortoise/llm/request_log.py`
- Modify: `backend/codetortoise/llm/ledger.py`
- Modify: `backend/codetortoise/services.py:136`
- Modify: `README.md` (after the `max_output_tokens_cap` line from Task 1)
- Test: `backend/tests/test_ledger.py`

**Interfaces:**
- Consumes: Task 2's `start_log()` / `take_log()` and the record keys.
- Produces:
  - `LlmConfig.request_log: Literal["all", "failed", "off"] = "all"`, `LlmConfig.request_log_days: int = 14`.
  - `request_log.keep(mode, failed: bool, records: list[dict]) -> bool`
  - `request_log.write(store, call_id: int, rid: int | None, records: list[dict]) -> None`
  - `request_log.prune(store, days: int, now: datetime | None = None) -> int`
  - `request_log.rows(store, rid: int, call: int | None = None) -> list[dict]` (record keys plus `call_id`,
    `purpose`, `target`; `request` decoded to a dict, `response` to a str)
  - `request_log.files(rows) -> dict[str, bytes]` (`"call-<id>/<seq>.json"`)
  - `request_log.zip_bytes(rows) -> bytes`
  - `request_log.line(row) -> str`
  - `Ledger(store, budget, request_log: str = "all", request_log_days: int = 14)`;
    `Ledger.reserve(rid, user, purpose, target, model: str | None = None)`; `Ledger.prune(now=None) -> int`;
    `Ledger.usage(rid)["calls"]` rows gain `model` and `requests`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_ledger.py` (add imports `import sqlite3`, `from datetime import UTC, datetime, timedelta`,
`from codetortoise.llm import request_log`):

```python
def _logged(tmp_path, mode="all"):
    store = Store(tmp_path / "t.db")
    rid = store.create_review("t", "owner", [1])
    return Ledger(store, LlmBudget(), mode), store, rid


def _repairing():
    replies = iter(['{"nope": 1}', '{"ok": true}'])
    return LlmClient("http://llm/v1", "k", "m", sleep=lambda s: None, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})))


def test_every_request_of_a_call_is_logged_when_request_log_is_all(tmp_path):
    ledger, store, rid = _logged(tmp_path)
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)
    [call] = ledger.usage(rid)["calls"]
    assert (call["model"], call["requests"]) == ("m", 1)
    [row] = request_log.rows(store, rid)
    assert (row["call_id"], row["purpose"], row["target"], row["seq"], row["status"]) == (call["id"], "flow", "FL1", 1, 200)
    assert row["request"]["messages"][1]["content"] == "u" and json.loads(row["response"])["usage"]["prompt_tokens"] == 120
    assert row["truncated"] is False and row["repair"] is False


def test_request_log_failed_keeps_only_calls_that_failed_were_cut_off_or_repaired(tmp_path):
    ledger, store, rid = _logged(tmp_path, "failed")
    ledger.call(_llm(), rid, "bob", "flow", "ok", _ask)
    with pytest.raises(LlmError):
        ledger.call(_llm(fail=True), rid, "bob", "flow", "failed", _ask)
    ledger.call(_repairing(), rid, "bob", "flow", "repaired", _ask)
    cut = iter([httpx.Response(200, json={"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]}),
                httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})])
    ledger.call(LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(lambda r: next(cut))),
                rid, "bob", "flow", "cut off", _ask)
    assert [(r["target"], r["seq"]) for r in request_log.rows(store, rid)] == [
        ("failed", 1), ("repaired", 1), ("repaired", 2), ("cut off", 1), ("cut off", 2)]


def test_request_log_off_keeps_nothing(tmp_path):
    ledger, store, rid = _logged(tmp_path, "off")
    with pytest.raises(LlmError):
        ledger.call(_llm(fail=True), rid, "bob", "flow", "failed", _ask)
    assert request_log.rows(store, rid) == [] and ledger.usage(rid)["calls"][0]["requests"] == 0


def test_a_network_failure_is_logged_with_its_error(tmp_path):
    ledger, store, rid = _logged(tmp_path)

    def down(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(LlmError):
        ledger.call(LlmClient("http://llm/v1", "k", "m", transport=httpx.MockTransport(down), sleep=lambda s: None),
                    rid, "bob", "flow", "x", _ask)
    rows = request_log.rows(store, rid)
    assert len(rows) == 3 and all(r["status"] is None and r["error"] == "ConnectError: refused" for r in rows)


def test_requests_older_than_the_retention_are_pruned(tmp_path):
    ledger, store, rid = _logged(tmp_path)
    ledger.call(_llm(), rid, "bob", "flow", "FL1", _ask)
    assert ledger.prune(now=datetime.now(UTC) + timedelta(days=1)) == 0 and len(request_log.rows(store, rid)) == 1
    assert ledger.prune(now=datetime.now(UTC) + timedelta(days=15)) == 1 and request_log.rows(store, rid) == []


def test_an_old_database_gains_the_model_column(tmp_path):
    db = sqlite3.connect(tmp_path / "t.db")
    db.execute("CREATE TABLE llm_calls(id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER, user TEXT, purpose TEXT, "
               "target TEXT, started_at TEXT, finished_at TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, "
               "outcome TEXT, error TEXT)")
    db.commit()
    db.close()
    store = Store(tmp_path / "t.db")
    assert "model" in {r["name"] for r in store._all("PRAGMA table_info(llm_calls)")}


def test_the_log_is_exported_as_one_json_file_per_request_and_one_line_each(tmp_path):
    ledger, store, rid = _logged(tmp_path)
    ledger.call(_repairing(), rid, "bob", "flow", "FL1", _ask)
    rows = request_log.rows(store, rid)
    files = request_log.files(rows)
    call = rows[0]["call_id"]
    assert sorted(files) == [f"call-{call}/1.json", f"call-{call}/2.json"]
    one = json.loads(files[f"call-{call}/2.json"])
    assert (one["purpose"], one["repair"], one["response"]["choices"][0]["message"]["content"]) == ("flow", True, '{"ok": true}')
    assert request_log.line(rows[1]).startswith(f"call {call} flow FL1 m #2 200 - limit=16384 tokens=-+- ")   # the repair round doubles from 8192
    import io
    import zipfile
    assert sorted(zipfile.ZipFile(io.BytesIO(request_log.zip_bytes(rows))).namelist()) == sorted(files)
```

Add to `backend/tests/test_config.py`:

```python
def test_the_request_log_keeps_every_request_for_14_days_unless_told_otherwise():
    base = {"workspace": {"root": "/w", "compile_commands": "auto"}}
    cfg = Config.model_validate(base)
    assert (cfg.llm.request_log, cfg.llm.request_log_days) == ("all", 14)
    assert Config.model_validate({**base, "llm": {"request_log": "failed"}}).llm.request_log == "failed"
    with pytest.raises(pydantic.ValidationError, match="request_log"):
        Config.model_validate({**base, "llm": {"request_log": "some"}})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_ledger.py tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'request_log'` and the config test's missing field.

- [ ] **Step 3: Config fields**

In `LlmConfig`, after `max_output_tokens_cap`:

```python
    request_log: Literal["all", "failed", "off"] = "all"   # HTTP requests kept: every one, a failed call's, or none
    request_log_days: int = 14     # logged requests older than this are deleted
```

- [ ] **Step 4: Schema**

In `backend/codetortoise/store.py` `_SCHEMA`, after the `ix_llm_calls_user` index:

```sql
CREATE TABLE IF NOT EXISTS llm_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, call_id INTEGER NOT NULL,
  review_id INTEGER, seq INTEGER NOT NULL, sent_at TEXT NOT NULL, elapsed_ms INTEGER, url TEXT, model TEXT,
  status INTEGER, error TEXT, stop_reason TEXT, truncated INTEGER NOT NULL, repair INTEGER NOT NULL,
  max_output_tokens INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER, request BLOB, response BLOB);
CREATE INDEX IF NOT EXISTS ix_llm_requests_call ON llm_requests(call_id);
CREATE INDEX IF NOT EXISTS ix_llm_requests_review ON llm_requests(review_id, sent_at);
```

In `Store.__init__`, after the `ai_meta` migration:

```python
            calls = {r[1] for r in self._db.execute("PRAGMA table_info(llm_calls)")}
            if "model" not in calls:                 # databases made before the request log
                self._db.execute("ALTER TABLE llm_calls ADD COLUMN model TEXT")
```

- [ ] **Step 5: Create `backend/codetortoise/llm/request_log.py`**

```python
"""The request log (spec 2026-10-08-llm-robustness §7, §8): each HTTP request to a model, kept as `llm.request_log`
says, compressed, and pruned after `llm.request_log_days`."""
from __future__ import annotations

import io
import json
import zipfile
import zlib
from datetime import UTC, datetime, timedelta

from codetortoise.store import Store

_COLS = ("seq", "sent_at", "elapsed_ms", "url", "model", "status", "error", "stop_reason", "truncated", "repair",
         "max_output_tokens", "prompt_tokens", "completion_tokens")


def keep(mode: str, failed: bool, records: list[dict]) -> bool:
    """Whether a call's records are written: `all` always, `failed` when the call failed or a reply was cut off or
    repaired, `off` never."""
    if mode == "off" or not records:
        return False
    return mode == "all" or failed or any(r["truncated"] or r["repair"] for r in records)


def write(store: Store, call_id: int, rid: int | None, records: list[dict]) -> None:
    sql = (f"INSERT INTO llm_requests(call_id, review_id, {', '.join(_COLS)}, request, response) "
           f"VALUES({','.join('?' * (len(_COLS) + 4))})")
    for r in records:
        store._exec(sql, (call_id, rid, *[int(r[c]) if c in ("truncated", "repair") else r[c] for c in _COLS],
                          zlib.compress(json.dumps(r["request"]).encode()),
                          zlib.compress(r["response"].encode()) if r["response"] is not None else None))


def prune(store: Store, days: int, now: datetime | None = None) -> int:
    """Deletes the requests sent more than `days` before `now`; returns how many."""
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=days)).isoformat(timespec="seconds")
    return store._exec("DELETE FROM llm_requests WHERE sent_at < ?", (cutoff,)).rowcount


def rows(store: Store, rid: int, call: int | None = None) -> list[dict]:
    """The review's logged requests (one call's with `call`), in call and send order, decoded."""
    sql = ("SELECT r.*, c.purpose, c.target FROM llm_requests r JOIN llm_calls c ON c.id = r.call_id "
           "WHERE r.review_id=?" + (" AND r.call_id=?" if call is not None else "") + " ORDER BY r.call_id, r.seq")
    out = []
    for d in store._all(sql, (rid,) if call is None else (rid, call)):
        d["request"] = json.loads(zlib.decompress(d["request"])) if d["request"] is not None else None
        d["response"] = zlib.decompress(d["response"]).decode() if d["response"] is not None else None
        d["truncated"], d["repair"] = bool(d["truncated"]), bool(d["repair"])
        out.append(d)
    return out


def _parsed(text: str | None):
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def files(got: list[dict]) -> dict[str, bytes]:
    """One JSON file per request: `call-<id>/<seq>.json` with its metadata, request and response."""
    return {f"call-{r['call_id']}/{r['seq']}.json": json.dumps(
        {**{k: r[k] for k in ("call_id", "purpose", "target", *_COLS)}, "request": r["request"],
         "response": _parsed(r["response"])}, indent=2).encode() for r in got}


def zip_bytes(got: list[dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files(got).items():
            z.writestr(name, data)
    return buf.getvalue()


def _dash(v) -> str:
    return "-" if v is None else str(v)


def line(r: dict) -> str:
    """One request on one line: call, purpose, target, model, seq, status, stop reason, limit, tokens, ms, error."""
    err = f" {r['error'][:80]}" if r["error"] else ""
    return (f"call {r['call_id']} {r['purpose']} {r['target']} {r['model']} #{r['seq']} {_dash(r['status'])} "
            f"{_dash(r['stop_reason'])} limit={_dash(r['max_output_tokens'])} "
            f"tokens={_dash(r['prompt_tokens'])}+{_dash(r['completion_tokens'])} {_dash(r['elapsed_ms'])}ms{err}")
```

- [ ] **Step 6: The ledger logs, records the model, prunes and counts**

In `backend/codetortoise/llm/ledger.py`:

1. Import: `from codetortoise.llm import request_log as rlog` (the alias keeps the module apart from the
   `request_log` attribute below); `from datetime import UTC, datetime` stays.
2. `__init__`:

```python
    def __init__(self, store: Store, budget: LlmBudget, request_log: str = "all", request_log_days: int = 14):
        self.store, self.limits = store, budget
        self.request_log, self.request_log_days = request_log, request_log_days
```

3. `reserve` gains `model: str | None = None` and inserts it:

```python
            cur = self.store._exec(
                "INSERT INTO llm_calls(review_id, user, purpose, target, started_at, outcome, error, model) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (rid, user or PIPELINE, purpose, target, _now(), "refused" if reason else "running", reason, model))
```

4. `call`:

```python
    def call(self, llm: LlmClient, rid: int | None, user: str | None, purpose: str, target: str,
             fn: Callable[[LlmClient], T]) -> T:
        """Reserve, run `fn(llm)` (one AI call, its retries included), and record the outcome, tokens and, as
        `llm.request_log` says, its HTTP requests."""
        call_id = self.reserve(rid, user, purpose, target, llm.model)
        llm.start_usage()
        llm.start_log()
        try:
            out = fn(llm)
        except Exception as e:
            self.finish(call_id, "failed", llm.take_usage(), f"{type(e).__name__}: {e}"[:500])
            self._log(call_id, rid, llm.take_log(), failed=True)
            raise
        self.finish(call_id, "ok", llm.take_usage())
        self._log(call_id, rid, llm.take_log(), failed=False)
        return out

    def _log(self, call_id: int, rid: int | None, records: list[dict], failed: bool) -> None:
        if rlog.keep(self.request_log, failed, records):
            rlog.write(self.store, call_id, rid, records)

    def prune(self, now: datetime | None = None) -> int:
        """Deletes logged requests older than `llm.request_log_days`."""
        return rlog.prune(self.store, self.request_log_days, now)
```

5. `usage`: the calls query becomes

```python
        calls = self.store._all("SELECT id, user, purpose, target, model, started_at, finished_at, prompt_tokens, "
                                "completion_tokens, outcome, error, (SELECT COUNT(*) FROM llm_requests r "
                                "WHERE r.call_id = llm_calls.id) AS requests FROM llm_calls WHERE review_id=? "
                                "ORDER BY id", (rid,))
```

- [ ] **Step 7: Wire the settings**

In `backend/codetortoise/services.py:136`:

```python
    ledger = Ledger(store, cfg.llm.budget, cfg.llm.request_log, cfg.llm.request_log_days)
```

- [ ] **Step 8: README**

After the `max_output_tokens_cap` line added in Task 1:

```yaml
  # request_log: all                # HTTP requests kept for debugging: all, failed (a failed, cut-off or repaired call's) or off
  # request_log_days: 14            # read them with `codetortoise llm-log` or the AI usage view's download link
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_ledger.py tests/test_config.py tests/test_store.py tests/test_ondemand.py -q`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add backend/codetortoise/config.py backend/codetortoise/store.py backend/codetortoise/llm/request_log.py backend/codetortoise/llm/ledger.py backend/codetortoise/services.py README.md backend/tests/test_ledger.py backend/tests/test_config.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(llm): the ledger keeps each call's HTTP requests as llm.request_log says (all, failed or off), with its model, and prunes them after request_log_days

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Tries — strong, strong fresh, weak

**Files:**
- Create: `backend/codetortoise/llm/tiers.py`
- Test: `backend/tests/test_tiers.py`

**Interfaces:**
- Consumes: `LlmClient.with_start`, `.base`, `.cap`, `.max_output_tokens`, `.model` (Task 1); `LlmTruncated`,
  `LlmUnreachable`; `Ledger.call`, `Refused`.
- Produces:
  - `Tried` dataclass: `value`, `tier: Literal["strong", "fresh", "weak"]`, `model: str`, `failures: list[str]`,
    `strong_unreachable: bool`.
  - `TiersFailed(Exception)` with `.failures: list[str]`, `.strong_unreachable: bool`.
  - `try_tiers(ledger, rid, purpose, target, fn, strong, weak, skip_strong=False) -> Tried`
  - `failure_text(e: Exception) -> str`
  - `tried_note(prefix: str, failures: list[str], outcome: str) -> str`
  - `done_text(t: Tried, verb: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tiers.py`:

```python
"""A strong-model piece of work is tried fresh, then on the weak model (spec 2026-10-08-llm-robustness §5)."""
import json

import httpx
import pytest
from pydantic import BaseModel

from codetortoise.config import LlmBudget
from codetortoise.llm.client import LlmClient, LlmTruncated
from codetortoise.llm.ledger import Ledger, Refused
from codetortoise.llm.tiers import TiersFailed, done_text, failure_text, tried_note, try_tiers
from codetortoise.store import Store


class Out(BaseModel):
    n: int


def _ask(llm):
    return llm.complete_json("s", "u", Out)


def _client(model, handler, **kw):
    return LlmClient("http://llm/v1", "k", model, transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def _reply(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _logging(model, replies, seen, **kw):
    def handler(req):
        seen.append((model, json.loads(req.content).get("max_tokens")))
        return replies(req)
    return _client(model, handler, **kw)


def test_a_strong_answer_is_used_as_it_is():
    t = try_tiers(None, None, "stories", "chunk 1", _ask, _client("big", lambda r: _reply('{"n": 1}')),
                  _client("small", lambda r: _reply('{"n": 2}')))
    assert (t.value.n, t.tier, t.model, t.failures, t.strong_unreachable) == (1, "strong", "big", [], False)


def test_a_failing_strong_model_is_tried_fresh_at_double_its_limit_then_the_weak_model_at_four_times():
    seen = []
    strong = _logging("big", lambda r: _reply("not json"), seen, max_output_tokens=1000)
    weak = _logging("small", lambda r: _reply('{"n": 2}'), seen, max_output_tokens=500)
    t = try_tiers(None, None, "stories", "chunk 1", _ask, strong, weak)
    assert (t.value.n, t.tier, t.model) == (2, "weak", "small")
    assert t.failures == ["big: invalid JSON twice", "fresh try: invalid JSON twice"]
    assert seen == [("big", 1000), ("big", 2000), ("big", 2000), ("big", 4000), ("small", 4000)]
    assert strong.max_output_tokens == 1000                          # the tries' views leave the client as it was


def test_a_fresh_strong_answer_is_marked_fresh():
    replies = iter(["not json", "still not", '{"n": 3}'])
    t = try_tiers(None, None, "review", "story a", _ask, _client("big", lambda r: _reply(next(replies))), None)
    assert (t.value.n, t.tier, t.failures) == (3, "fresh", ["big: invalid JSON twice"])
    assert done_text(t, "judged its findings") == "big judged its findings on a fresh try"


def test_an_unreachable_strong_model_is_not_tried_fresh():
    seen = []
    strong = _logging("big", lambda r: httpx.Response(503), seen)
    t = try_tiers(None, None, "stories", "chunk 1", _ask, strong, _client("small", lambda r: _reply('{"n": 2}')))
    assert (t.tier, t.failures, t.strong_unreachable) == ("weak", ["big: unreachable"], True)
    assert len(seen) == 3                                             # one try's three attempts, no fresh try


def test_skip_strong_goes_straight_to_the_weak_model():
    seen = []
    strong = _logging("big", lambda r: _reply('{"n": 1}'), seen)
    t = try_tiers(None, None, "stories", "chunk 2", _ask, strong, _client("small", lambda r: _reply('{"n": 2}')),
                  skip_strong=True)
    assert seen == [] and (t.tier, t.failures) == ("weak", [])


def test_a_refused_try_stops_the_tries():
    class Budget:
        def call(self, llm, rid, user, purpose, target, fn):
            raise Refused("this review has used its 1 tier-1 AI calls")
    with pytest.raises(Refused):
        try_tiers(Budget(), 1, "stories", "chunk 1", _ask, _client("big", lambda r: _reply('{"n": 1}')),
                  _client("small", lambda r: _reply('{"n": 2}')))


def test_without_a_weak_model_every_failure_is_reported():
    strong = _client("big", lambda r: httpx.Response(400, text="bad request"))
    with pytest.raises(TiersFailed) as e:
        try_tiers(None, None, "threads", "threads", _ask, strong, None)
    assert e.value.failures == ["big: HTTP 400: bad request", "fresh try: HTTP 400: bad request"]
    assert e.value.strong_unreachable is False


def test_each_try_is_its_own_ledger_call_with_its_model(tmp_path):
    store = Store(tmp_path / "t.db")
    rid = store.create_review("t", "owner", [1])
    ledger = Ledger(store, LlmBudget())
    try_tiers(ledger, rid, "stories", "chunk 1", _ask, _client("big", lambda r: _reply("not json")),
              _client("small", lambda r: _reply('{"n": 2}')))
    assert [(c["purpose"], c["target"], c["model"], c["outcome"]) for c in ledger.usage(rid)["calls"]] == [
        ("stories", "chunk 1", "big", "failed"), ("stories", "chunk 1 (fresh)", "big", "failed"),
        ("stories", "chunk 1 (weak)", "small", "ok")]


def test_failures_and_notes_are_worded_for_people():
    assert failure_text(LlmTruncated(16384, 16384)) == "reply cut off at 16384 tokens"
    assert failure_text(ValueError("no answer within the rounds allowed")) == "ValueError: no answer within the rounds allowed"
    assert tried_note("chunk 2", ["big: reply cut off at 16384 tokens", "fresh try: unreachable"],
                      "small grouped its pieces") == \
        "chunk 2: big: reply cut off at 16384 tokens; fresh try: unreachable; small grouped its pieces"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_tiers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'codetortoise.llm.tiers'`.

- [ ] **Step 3: Create `backend/codetortoise/llm/tiers.py`**

```python
"""Tries for one piece of strong-model work (spec 2026-10-08-llm-robustness §5): the strong model, the strong model in
a fresh conversation at double its limit, then the weak model at four times, each its own ledger call. The stage
decides its own last resort when every try fails."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

from codetortoise.llm.client import LlmClient, LlmTruncated, LlmUnreachable
from codetortoise.llm.ledger import Ledger, Refused

T = TypeVar("T")
Tier = Literal["strong", "fresh", "weak"]


@dataclass
class Tried(Generic[T]):
    value: T
    tier: Tier
    model: str
    failures: list[str] = field(default_factory=list)   # the tries before it, worded for a note
    strong_unreachable: bool = False


class TiersFailed(Exception):
    def __init__(self, failures: list[str], strong_unreachable: bool):
        super().__init__("; ".join(failures) or "no model to try")
        self.failures, self.strong_unreachable = failures, strong_unreachable


def failure_text(e: Exception) -> str:
    if isinstance(e, LlmUnreachable):
        return "unreachable"
    if isinstance(e, LlmTruncated):
        return str(e)
    s = str(e)
    if s.startswith("LLM returned invalid JSON twice"):
        return "invalid JSON twice"
    if s.startswith("LLM HTTP "):
        return s[4:124]
    return f"{type(e).__name__}: {s}"[:120]


def tried_note(prefix: str, failures: list[str], outcome: str) -> str:
    return f"{prefix}: " + "; ".join([*failures, outcome])


def done_text(t: Tried, verb: str) -> str:
    """Who did the work: "small grouped its pieces", or "big … on a fresh try"."""
    return f"{t.model} {verb}" + (" on a fresh try" if t.tier == "fresh" else "")


def try_tiers(ledger: Ledger | None, rid: int | None, purpose: str, target: str, fn: Callable[[LlmClient], T],
              strong: LlmClient, weak: LlmClient | None, skip_strong: bool = False) -> Tried[T]:
    """`fn` on each try in turn until one answers. Refused (the budget) stops at once; an unreachable strong model
    is not tried fresh; `skip_strong` starts at the weak model. Raises TiersFailed when every try failed."""
    tries: list[tuple[Tier, LlmClient, str, str]] = []
    if not skip_strong:
        tries += [("strong", strong.with_start(strong.max_output_tokens), target, strong.model),
                  ("fresh", strong.with_start(min(strong.cap, 2 * strong.base)), f"{target} (fresh)", "fresh try")]
    if weak is not None:
        tries.append(("weak", weak.with_start(min(weak.cap, 4 * max(weak.base, strong.base))), f"{target} (weak)",
                      weak.model))
    failures: list[str] = []
    unreachable = False
    for tier, llm, tgt, label in tries:
        if tier == "fresh" and unreachable:
            continue
        try:
            value = ledger.call(llm, rid, None, purpose, tgt, fn) if ledger is not None else fn(llm)
        except Refused:
            raise
        except Exception as e:  # this try failed: the next one goes on
            failures.append(f"{label}: {failure_text(e)}")
            unreachable = unreachable or (tier == "strong" and isinstance(e, LlmUnreachable))
            continue
        return Tried(value, tier, llm.model, failures, unreachable)
    raise TiersFailed(failures, unreachable)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_tiers.py -q`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/codetortoise/llm/tiers.py backend/tests/test_tiers.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(llm): try_tiers runs strong-model work on the strong model, again fresh at double the limit, then on the weak model at four times

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The four stages try the weak model before their own fallback

**Files:**
- Modify: `backend/codetortoise/llm/stories.py:459-529` (`form_stories`)
- Modify: `backend/codetortoise/llm/review.py:110-162` (`review_stories`)
- Modify: `backend/codetortoise/llm/threads.py:89-140` (`write_threads`)
- Modify: `backend/codetortoise/pipeline.py:121-130` (prune), `:290`, `:314`, `:463-484`
- Test: `backend/tests/test_tier1_stories.py`, `backend/tests/test_tier1_review.py`, `backend/tests/test_llm_threads.py`,
  `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 4's `try_tiers`, `Tried`, `TiersFailed`, `tried_note`, `done_text`; Task 3's `Ledger.prune`.
- Produces: `form_stories(..., findings, weak: LlmClient | None = None)`;
  `review_stories(..., skip=None, weak: LlmClient | None = None)`;
  `write_threads(strong, ledger, rid, reading, ss, cls, weak=None) -> tuple[list[str], str | None]` (notes, the model
  that wrote the text or None).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_tier1_stories.py` (add `from codetortoise.llm.client import LlmError, LlmUnreachable`):

```python
def test_a_chunk_the_strong_model_fails_is_grouped_by_the_weak_model_and_the_plan_says_so():
    c, a, ps, pid = _change()
    answer = {"action": "answer", "stories": [
        _story("a", "Modem radio gains band 71", _p(pid["modem_tx"], "starts_purpose"), _p(pid["modem_rx"])),
        _story("b", "DSP runs a faster FFT", _p(pid["dsp_run"], "starts_purpose"), purpose="The DSP's FFT gets faster.")]}
    strong = ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x"))
    weak = ScriptedLlm(lambda s, u: answer, model="small")
    plan = form_stories(strong, None, None, ps, a.x, StrongLlmConfig(base_url="http://x", model="big"), [], weak=weak)
    assert [s.key for s in plan.stories] == ["a", "b"] and {s.source for s in plan.stories} == {"tier1"}
    assert plan.notes == ["chunk 1: big: invalid JSON twice; fresh try: invalid JSON twice; small grouped its pieces"]
    assert not plan.complete and len(strong.prompts) == 2 and len(weak.prompts) == 1


def test_once_the_strong_model_is_unreachable_later_chunks_go_straight_to_the_weak_model():
    c, a, ps, pid = _change()
    strong = ScriptedLlm(lambda s, u: LlmUnreachable("LLM request failed after 3 attempts: ReadTimeout"))
    weak = ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x"), model="small")
    plan = form_stories(strong, None, None, ps, a.x, StrongLlmConfig(base_url="http://x", model="big",
                                                                     context_tokens=_per_target(ps)), [], weak=weak)
    assert len(strong.prompts) == 1 and len(weak.prompts) == 2
    assert plan.notes == ["chunk 1: big: unreachable; small: invalid JSON twice; the rules grouped its pieces",
                          "chunk 2: small: invalid JSON twice; the rules grouped its pieces"]
```

Add to `backend/tests/test_tier1_review.py` (add `from codetortoise.llm.client import LlmError, LlmUnreachable`):

```python
def test_a_story_the_strong_model_fails_is_judged_by_the_weak_model_but_not_marked_reviewed():
    def answer(system, user):
        if "F1" in user:
            return _verdicts(("F1", "hazard", "old_user still calls hal_write the old way.", ["drv/old.c:3", "N3"]))
        return _verdicts(("F2", "no_hazard", "Nothing outside the DSP uses the result.", ["N4"]))
    a, ps, plan, findings, facts = _change()
    strong = ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x"))
    weak = ScriptedLlm(answer, model="small")
    out = review_stories(strong, None, None, plan, ps, a.x, CFG, findings, facts, weak=weak)
    assert len(out.verdicts) == 2 and out.reviewed == []          # the next run asks the strong model again
    assert out.notes == ["story a: big: invalid JSON twice; fresh try: invalid JSON twice; small judged its findings",
                         "story b: big: invalid JSON twice; fresh try: invalid JSON twice; small judged its findings"]


def test_a_story_every_model_fails_keeps_the_detectors_verdicts():
    a, ps, plan, findings, facts = _change()
    fail = ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x"))
    out = review_stories(fail, None, None, plan, ps, a.x, CFG, findings, facts,
                         weak=ScriptedLlm(lambda s, u: RuntimeError("down"), model="small"))
    assert out.verdicts == {} and out.notes[0] == ("story a: big: invalid JSON twice; fresh try: invalid JSON twice; "
                                                   "small: RuntimeError: down; its findings stay as the detectors left them")
```

Add to `backend/tests/test_llm_threads.py` (add `from codetortoise.llm.client import LlmError`):

```python
def test_thread_text_the_strong_model_fails_is_written_by_the_weak_model():
    r, ss = _reading()
    notes, by = write_threads(ScriptedLlm(lambda s, u: LlmError("LLM returned invalid JSON twice: x")), None, None, r, ss,
                              {}, weak=ScriptedLlm(lambda s, u: GOOD, model="small"))
    assert by == "small" and r.whole_source == "llm"
    assert notes == ["thread text: big: invalid JSON twice; fresh try: invalid JSON twice; small wrote it"]
```

Add to `backend/tests/test_pipeline.py`:

```python
def test_a_review_run_prunes_requests_older_than_the_retention(fx, tmp_path):
    from datetime import UTC, datetime, timedelta

    from codetortoise.llm import request_log
    svc = make_services(fx, tmp_path)
    rid = svc.store.create_review("t", "owner", [101, 102])
    call = svc.ledger.reserve(rid, None, "flow", "x", "m")
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat(timespec="seconds")
    request_log.write(svc.store, call, rid, [{"seq": 1, "sent_at": old, "elapsed_ms": 1, "url": "/v1/chat/completions",
                                              "model": "m", "status": 200, "error": None, "stop_reason": "stop",
                                              "truncated": False, "repair": False, "max_output_tokens": None,
                                              "prompt_tokens": 1, "completion_tokens": 1, "request": {}, "response": "{}"}])
    run_review(rid, svc)
    assert request_log.rows(svc.store, rid) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_tier1_stories.py tests/test_tier1_review.py tests/test_llm_threads.py tests/test_pipeline.py -q -k "weak or every_model or prunes"`
Expected: FAIL — `TypeError: form_stories() got an unexpected keyword argument 'weak'` (and likewise for the others;
the prune test fails on the row still being there).

- [ ] **Step 3: `form_stories`**

In `backend/codetortoise/llm/stories.py`: import `from codetortoise.llm.tiers import Tried, TiersFailed, done_text,
tried_note, try_tiers`; drop `LlmUnreachable` from the client import if nothing else uses it. Replace the function:

```python
def form_stories(strong: LlmClient, ledger: Ledger | None, rid: int | None, ps: PieceSet, x: _Ctx,
                 cfg: StrongLlmConfig, findings: list[Finding], weak: LlmClient | None = None) -> StoryPlan:
    """Tier 1's plan for the whole change. A chunk the strong model fails is tried fresh, then on the weak model (spec
    2026-10-08-llm-robustness §6); one every model fails (or the budget refuses) is grouped by the rules. The plan's
    notes say which."""
    limit = int(cfg.context_tokens * 4 * CHUNK_SHARE)
    cls = {m.cl: m.description for m in x.c.cs.cls}
    tools = Tools(x, ps)
    groups = chunks(ps, findings, limit)
    stories: list[PlannedStory] = []
    unsorted: list[Placement] = []
    notes: list[str] = []
    refused = fell_back = False
    gone = {"strong": False}            # the strong model was unreachable this run: later work skips its tries

    def call(purpose: str, target: str, fn) -> Tried:
        t = try_tiers(ledger, rid, purpose, target, fn, strong, weak, skip_strong=gone["strong"])
        gone["strong"] |= t.strong_unreachable
        return t
    for i, ids in enumerate(groups, 1):
        prefix = f"c{i}" if len(groups) > 1 else ""
        parts = chunk_parts(ids, ps, findings)
        later: list[tuple[int, Tried]] = []          # runs a later try answered: each gets a note

        def run(n: int = 1, ids=ids, parts=parts, prefix=prefix, i=i, later=later) -> Got:
            t = call("stories", f"chunk {i}" + (f" run {n}" if n > 1 else ""),
                     lambda llm: ask(llm, parts, tools, cfg.rounds, int(cfg.context_tokens * 4 * 0.9)))
            if t.tier != "strong":
                later.append((n, t))
            return check_answer(t.value, ids, ps, cls, prefix)
        if gone["strong"] and weak is None:
            fell_back = True
            notes.append(f"chunk {i}: the strong model is unreachable; the rules grouped its pieces")
            stories += rules_plan(ps, ids, prefix=f"r{i}_")
            continue
        try:
            if refused:
                raise Refused("the tier-1 budget ran out")
            got = run(1)
            if cfg.agree >= 2:
                first = got
                try:
                    got = agree(first, run(2), lambda: run(3), ps, cls)
                except Refused as e:          # the budget stopped the agreement runs: the first run's checked answer stands
                    refused = fell_back = True
                    notes.append(f"chunk {i}: AI budget: {e.reason}; its first run's answer stands")
                    got = first
        except Refused as e:
            refused = fell_back = True
            notes.append(f"chunk {i}: AI budget: {e.reason}; the rules grouped its pieces")
            got = Got(stories=rules_plan(ps, ids, prefix=f"r{i}_"))
        except TiersFailed as e:
            gone["strong"] |= e.strong_unreachable
            fell_back = True
            notes.append(tried_note(f"chunk {i}", e.failures, "the rules grouped its pieces"))
            got = Got(stories=rules_plan(ps, ids, prefix=f"r{i}_"))
        except Exception as e:  # an answer the checks reject: the rules group the chunk; the others stand
            fell_back = True
            notes.append(f"chunk {i}: {type(e).__name__}: {e}"[:300] + "; the rules grouped its pieces")
            got = Got(stories=rules_plan(ps, ids, prefix=f"r{i}_"))
        for n, t in later:
            fell_back = fell_back or t.tier == "weak"
            notes.append(tried_note(f"chunk {i}" + (f" run {n}" if n > 1 else ""), t.failures,
                                    done_text(t, "grouped its pieces")))
        stories += got.stories
        unsorted += got.unsorted
    tier1 = [s for s in stories if s.source == "tier1"]
    if len(groups) > 1 and len(tier1) > 1 and not refused and not (gone["strong"] and weak is None):
        try:
            t = call("stories_merge", "merge", lambda llm: merge_pass(llm, tier1, ps, cls))
            stories = t.value.stories + [s for s in stories if s.source != "tier1"]
            unsorted += t.value.unsorted
            if t.tier != "strong":
                notes.append(tried_note("merge pass", t.failures, done_text(t, "merged them")))
        except TiersFailed as e:
            notes.append(tried_note("merge pass", e.failures, "the chunks' stories stand unmerged"))
        except Exception as e:  # the chunks' stories stand unmerged
            notes.append(f"merge pass: {type(e).__name__}: {e}"[:300])
    if unsorted:
        stories.append(PlannedStory(key="unsorted", unsorted=True, source="tier1", placements=unsorted))
    return StoryPlan(stories=stories, notes=notes, complete=not fell_back)   # a failed merge pass leaves it complete
```

- [ ] **Step 4: `review_stories`**

In `backend/codetortoise/llm/review.py`: import `from codetortoise.llm.tiers import TiersFailed, done_text, tried_note,
try_tiers`; drop `LlmUnreachable` from the client import if unused. Signature gains `weak: LlmClient | None = None`
after `skip`. In the body: rename `unreachable` to `gone`; the skip branch becomes

```python
        if gone and weak is None:
            out.notes.append(f"story {s.key}: the strong model is unreachable; its findings stay as the detectors left them")
            continue
```

and the call becomes

```python
        try:
            t = try_tiers(ledger, rid, "review", f"story {s.key}", fn, strong, weak, skip_strong=gone)
        except Refused as e:
            refused = True
            out.notes.append(f"story {s.key}: AI budget: {e.reason}; its findings stay as the detectors left them")
            continue
        except TiersFailed as e:  # this story's findings stay as the detectors left them; the others go on
            gone = gone or e.strong_unreachable
            out.notes.append(tried_note(f"story {s.key}", e.failures, "its findings stay as the detectors left them"))
            continue
        gone = gone or t.strong_unreachable
        step = t.value
        if t.tier != "strong":
            out.notes.append(tried_note(f"story {s.key}", t.failures, done_text(t, "judged its findings")))
        if t.tier != "weak":          # a story the weak model judged is asked of the strong model again next run
            out.reviewed.append(s.key)
```

(remove the old `out.reviewed.append(s.key)` line that followed the call). Update the docstring: "…a call failing
on every model (spec 2026-10-08-llm-robustness §6) leaves the remaining findings as the detectors left them".

- [ ] **Step 5: `write_threads`**

In `backend/codetortoise/llm/threads.py`: import `from codetortoise.llm.tiers import TiersFailed, done_text, tried_note,
try_tiers`. Signature: `def write_threads(strong, ledger, rid, reading, ss, cls, weak: LlmClient | None = None) ->
tuple[list[str], str | None]:` with docstring `"""Reword `reading` in place from one checked answer; returns notes on
what kept its fixed text, and the model that wrote the text (None: the fixed text stays)."""`. The call:

```python
    try:
        t = try_tiers(ledger, rid, "threads", "threads", ask, strong, weak)
    except Refused as e:
        return [f"thread text: AI budget: {e.reason}; the fixed text stays"], None
    except TiersFailed as e:  # the fixed text stands
        return [tried_note("thread text", e.failures, "the fixed text stays")], None
    out = t.value
    said = [] if t.tier == "strong" else [tried_note("thread text", t.failures, done_text(t, "wrote it"))]
```

and the two returns at the end become `return said, t.model` (all checks passed) and
`return said + [f"thread text: {joined} failed the checks; their fixed text stays"], t.model`.

- [ ] **Step 6: The pipeline**

In `backend/codetortoise/pipeline.py`:

1. `run_review`, after `store.reset_stages(rid, STAGES)`:

```python
    if svc.ledger:
        svc.ledger.prune()                      # logged requests past llm.request_log_days
```

2. Line 290: `plan = form_stories(svc.strong, svc.ledger, rid, ps, ctx["analysis"].x, strong, ctx["findings"], weak=svc.llm)`
3. Line 314: add `weak=svc.llm` to the `review_stories(...)` call.
4. Threads stage (`:463-484`): `notes, by = write_threads(svc.strong, svc.ledger, rid, r, bs.stories, cls_text, weak=svc.llm)`
   in the uncached branch; in the cached branch set `by = strong.model` before the loop. Replace
   `told = f"thread text by {strong.model}"` with:

```python
            told = (f"thread text by {by}" if by == strong.model else
                    f"thread text by {by} (the strong model failed)" if by else "fixed thread text (the AI's answer failed)")
```

- [ ] **Step 7: Update the existing tests to the new notes**

The fresh try and the labelled failures change these exact expectations:

- `tests/test_tier1_stories.py`, `test_a_chunk_that_fails_is_grouped_by_the_rules_and_the_plan_says_so`:
  `["chunk 1: big: ValueError: no answer within the rounds allowed; fresh try: ValueError: no answer within the rounds allowed; the rules grouped its pieces"]`
- `tests/test_tier1_stories.py`, `test_an_unreachable_strong_model_is_asked_once_and_the_rules_group_the_rest`:
  `["chunk 1: big: unreachable; the rules grouped its pieces", "chunk 2: the strong model is unreachable; the rules grouped its pieces"]`
- `tests/test_tier1_stories.py`, the merge-pass failure test (`plan.notes == ["merge pass: RuntimeError: the merge timed out"]`):
  `["merge pass: big: RuntimeError: the merge timed out; fresh try: RuntimeError: the merge timed out; the chunks' stories stand unmerged"]`
- `tests/test_tier1_review.py`, `test_an_unreachable_strong_model_is_asked_once_and_the_rest_stay_as_the_detectors_left_them`:
  `["story a: big: unreachable; its findings stay as the detectors left them", "story b: the strong model is unreachable; its findings stay as the detectors left them"]`
- `tests/test_llm_threads.py`: `write_threads(...) == []` becomes `== ([], "big")`; the bad-answer test unpacks
  `notes, by = write_threads(...)` and asserts `by == "big"`; the failure test expects
  `notes == ["thread text: big: RuntimeError: down; fresh try: RuntimeError: down; the fixed text stays"]` (unpack
  `notes, by` and assert `by is None`); the budget test unpacks `notes, _`.
- `tests/test_pipeline.py`, `test_a_strong_model_that_fails_leaves_the_rules_stories_and_says_so`:
  `"chunk 1: big: RuntimeError: the endpoint is down; fresh try: RuntimeError: the endpoint is down; the rules grouped its pieces" in st["message"]`

- [ ] **Step 8: Run the stage tests and the full backend suite**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest -q -x -p no:cacheprovider > $CLAUDE_JOB_DIR/tmp/pytest.log 2>&1; tail -5 $CLAUDE_JOB_DIR/tmp/pytest.log`
Expected: all pass (about 670), 1 skipped. Any other test asserting an old note or prompt count fails here: update it
only to the wording §6 of the spec gives, and say which in the commit message.

Run: `/media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/ruff check codetortoise tests`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add backend/codetortoise/llm/stories.py backend/codetortoise/llm/review.py backend/codetortoise/llm/threads.py backend/codetortoise/pipeline.py backend/tests
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(stages): stories, merge, story review and thread text try the strong model fresh, then the weak model, before their own fallback, and the notes say which

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Reading the log — CLI and zip download

**Files:**
- Modify: `backend/codetortoise/cli.py` (new `cmd_llm_log`, parser entry)
- Modify: `backend/codetortoise/web/app.py:93-97` (prune at start), after `:514` (zip route)
- Test: `backend/tests/test_cli.py`, `backend/tests/test_web.py`

**Interfaces:**
- Consumes: Task 3's `request_log.rows`, `files`, `zip_bytes`, `line`; `Ledger.prune`; `Ledger.usage` rows with
  `model` and `requests`.
- Produces: CLI `codetortoise llm-log --config CFG REVIEW [--call N] [--out DIR]`;
  `GET /api/reviews/{rid}/ai/requests.zip[?call=N]` (`application/zip`, 404 when none).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_cli.py`:

```python
def _logged_review(tmp_path):
    from codetortoise.config import load_config
    from codetortoise.llm import request_log
    from codetortoise.llm.ledger import Ledger
    from codetortoise.store import Store
    assert main(["fixture-demo", "--dir", str(tmp_path), "--port", "9999"]) == 0
    cfg = load_config(tmp_path / "tortoise.yaml")
    store = Store(cfg.server.data_dir / "tortoise.db")
    rid = store.create_review("t", "demo", [101])
    call = Ledger(store, cfg.llm.budget).reserve(rid, None, "stories", "chunk 1", "big")
    request_log.write(store, call, rid, [{"seq": 1, "sent_at": "2026-10-08T10:00:00+00:00", "elapsed_ms": 900,
                                          "url": "/v1/chat/completions", "model": "big", "status": 200, "error": None,
                                          "stop_reason": "length", "truncated": True, "repair": False,
                                          "max_output_tokens": 1000, "prompt_tokens": 50, "completion_tokens": 1000,
                                          "request": {"model": "big"}, "response": '{"choices": []}'}])
    return rid, call


def test_llm_log_prints_one_line_per_request_and_writes_the_files(tmp_path, capsys):
    rid, call = _logged_review(tmp_path)
    capsys.readouterr()
    cfg = str(tmp_path / "tortoise.yaml")
    assert main(["llm-log", "--config", cfg, str(rid), "--out", str(tmp_path / "log")]) == 0
    out = capsys.readouterr().out
    assert f"call {call} stories chunk 1 big #1 200 length limit=1000 tokens=50+1000 900ms" in out
    one = json.loads((tmp_path / "log" / f"call-{call}" / "1.json").read_text())
    assert one["request"] == {"model": "big"} and one["response"] == {"choices": []} and one["truncated"] is True
    assert main(["llm-log", "--config", cfg, str(rid), "--call", str(call + 1)]) == 0
    assert capsys.readouterr().out.strip() == f"no requests logged for review {rid}"
```

(add `import json` at the top of `test_cli.py`).

Add to `backend/tests/test_web.py`:

```python
def test_the_request_log_downloads_as_a_zip_and_the_calls_say_how_many_requests_they_hold(env):
    import io
    import zipfile

    from codetortoise.llm import request_log
    svc, app, _ = env
    rid = svc.store.create_review("t", "owner", [101])
    call = svc.ledger.reserve(rid, None, "threads", "threads", "big")
    svc.ledger.finish(call, "ok")
    request_log.write(svc.store, call, rid, [{"seq": 1, "sent_at": "2026-10-08T10:00:00+00:00", "elapsed_ms": 5,
                                              "url": "/v1/chat/completions", "model": "big", "status": 200, "error": None,
                                              "stop_reason": "stop", "truncated": False, "repair": False,
                                              "max_output_tokens": None, "prompt_tokens": 1, "completion_tokens": 1,
                                              "request": {"model": "big"}, "response": "{}"}])
    c = login(app, "bob")
    [row] = c.get(f"/api/reviews/{rid}/ai/calls").json()
    assert (row["model"], row["requests"]) == ("big", 1)
    r = c.get(f"/api/reviews/{rid}/ai/requests.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert f'filename="review-{rid}-requests.zip"' in r.headers["content-disposition"]
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == [f"call-{call}/1.json"]
    one = c.get(f"/api/reviews/{rid}/ai/requests.zip?call={call}")
    assert f'filename="review-{rid}-call-{call}-requests.zip"' in one.headers["content-disposition"]
    assert c.get(f"/api/reviews/{rid}/ai/requests.zip?call={call + 1}").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_cli.py tests/test_web.py -q -k "llm_log or request_log"`
Expected: FAIL — argparse `invalid choice: 'llm-log'` (SystemExit 2) and the zip route's 404.

- [ ] **Step 3: CLI**

In `backend/codetortoise/cli.py`, after `cmd_stories_check`:

```python
def cmd_llm_log(args) -> int:
    """The request log of a review (spec 2026-10-08-llm-robustness §8.1): one line per request; files with --out."""
    from codetortoise.llm import request_log
    from codetortoise.store import Store
    cfg = load_config(Path(args.config))
    got = request_log.rows(Store(cfg.server.data_dir / "tortoise.db"), args.review, args.call)
    if not got:
        off = " (llm.request_log is off)" if cfg.llm.request_log == "off" else ""
        print(f"no requests logged for review {args.review}{off}")
        return 0
    for r in got:
        print(request_log.line(r))
    if args.out:
        for name, data in request_log.files(got).items():
            path = Path(args.out) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        print(f"wrote {len(got)} file(s) under {args.out}")
    return 0
```

and in `main`, after the `stories-check` parser:

```python
    s = sub.add_parser("llm-log", help="print a review's logged AI requests, and write them out as JSON files")
    s.add_argument("--config", required=True)
    s.add_argument("review", type=int)
    s.add_argument("--call", type=int, help="only this call's requests")
    s.add_argument("--out", help="a folder to write call-<id>/<seq>.json files into")
    s.set_defaults(fn=cmd_llm_log)
```

- [ ] **Step 4: Web**

In `backend/codetortoise/web/app.py`: import `from codetortoise.llm import ondemand, request_log, tortoise`. At start,
after `svc.ledger.fail_running()`:

```python
        svc.ledger.prune()                         # logged requests past llm.request_log_days
```

After the `ai_calls` route:

```python
    @app.get("/api/reviews/{rid}/ai/requests.zip")
    def ai_requests(rid: int, call: int | None = None, _: str = Depends(user_of)):
        """The review's logged AI requests, one JSON file per request (spec 2026-10-08-llm-robustness §8.2)."""
        review_or_404(rid)
        got = request_log.rows(store, rid, call)
        if not got:
            raise HTTPException(404, "no requests logged")
        name = f"review-{rid}" + (f"-call-{call}" if call is not None else "") + "-requests.zip"
        return Response(request_log.zip_bytes(got), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `env PYTHONPATH=$PWD /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m pytest tests/test_cli.py tests/test_web.py tests/test_ondemand.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/codetortoise/cli.py backend/codetortoise/web/app.py backend/tests/test_cli.py backend/tests/test_web.py
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(log): codetortoise llm-log prints and writes a review's logged requests; the web serves them as a zip

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The usage view links the log; the e2e model cuts replies off

**Files:**
- Modify: `frontend/src/api.ts:49-50` (`AiCall`)
- Create: `frontend/src/components/requestLog.ts`, `frontend/src/components/requestLog.test.ts`
- Modify: `frontend/src/components/AiPill.tsx:68-83`
- Modify: `frontend/e2e/fake_llm.py` (`do_POST`), `frontend/e2e/serve-strong.sh`
- Test: `frontend/e2e/workspace-tier1.spec.ts`

**Interfaces:**
- Consumes: Task 6's `/ai/requests.zip[?call=N]`; `/ai/calls` rows' `model` and `requests`.
- Produces: `requestLogHref(reviewId: number, call?: number): string`; `hasRequests(calls: AiCall[] | null): boolean`.

- [ ] **Step 1: Write the failing vitest**

Create `frontend/src/components/requestLog.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { AiCall } from "../api";
import { hasRequests, requestLogHref } from "./requestLog";

const call = (id: number, requests: number): AiCall => ({
  id, user: "pipeline", purpose: "stories", target: "chunk 1", model: "big", started_at: "2026-10-08T10:00:00+00:00",
  finished_at: null, prompt_tokens: null, completion_tokens: null, outcome: "ok", error: null, requests,
});

describe("request log links (spec 2026-10-08-llm-robustness §8.2)", () => {
  it("links the whole review's log, or one call's", () => {
    expect(requestLogHref(7)).toBe("/api/reviews/7/ai/requests.zip");
    expect(requestLogHref(7, 12)).toBe("/api/reviews/7/ai/requests.zip?call=12");
  });

  it("offers the download only when a call holds requests", () => {
    expect(hasRequests(null)).toBe(false);
    expect(hasRequests([call(1, 0)])).toBe(false);
    expect(hasRequests([call(1, 0), call(2, 3)])).toBe(true);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `frontend/`): `npx vitest run src/components/requestLog.test.ts`
Expected: FAIL — `Failed to resolve import "./requestLog"`.

- [ ] **Step 3: Implement**

`frontend/src/api.ts`, `AiCall` becomes:

```ts
export interface AiCall { id: number; user: string; purpose: string; target: string | null; model: string | null;
  started_at: string; finished_at: string | null; prompt_tokens: number | null; completion_tokens: number | null;
  outcome: "ok" | "failed" | "refused" | "running" | null; error: string | null; requests: number }
```

Create `frontend/src/components/requestLog.ts`:

```ts
import type { AiCall } from "../api";

/** The zip of a review's logged AI requests, or of one call's (spec 2026-10-08-llm-robustness §8.2). */
export function requestLogHref(reviewId: number, call?: number): string {
  return `/api/reviews/${reviewId}/ai/requests.zip` + (call === undefined ? "" : `?call=${call}`);
}

export function hasRequests(calls: AiCall[] | null): boolean {
  return (calls ?? []).some((c) => c.requests > 0);
}
```

`frontend/src/components/AiPill.tsx`: import `{ hasRequests, requestLogHref } from "./requestLog"`. Inside the
`<details>`, between `{calls === null && …}` and the table:

```tsx
        {hasRequests(calls) && <p className="small"><a href={requestLogHref(ai.reviewId)} download>Download request log</a></p>}
```

The table head becomes `<th>Time</th><th>Who</th><th>What</th><th>Model</th><th>Tokens</th><th>Outcome</th>`; each row
gains `<td>{c.model ?? "–"}</td>` after the What cell, and the Outcome cell becomes

```tsx
                <td title={c.error ?? undefined}>{c.outcome ?? "running"}
                  {c.requests > 0 && <> · <a href={requestLogHref(ai.reviewId, c.id)} download
                                             aria-label={`Requests of call ${c.id}`}>requests</a></>}</td>
```

- [ ] **Step 4: Run vitest and the type check**

Run (from `frontend/`): `npx vitest run && npx tsc -b`
Expected: all vitest files pass (188 tests); `tsc` prints nothing.

- [ ] **Step 5: The fake model cuts off replies under 2000 tokens**

In `frontend/e2e/fake_llm.py`, `do_POST` becomes:

```python
    def do_POST(self):  # noqa: N802 — /v1/chat/completions
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = req["messages"]
        content = json.dumps(answer(msgs[0]["content"], msgs[-1]["content"]))
        limit = req.get("max_tokens") or req.get("max_completion_tokens")
        if limit and limit < 2000:     # spec 2026-10-08-llm-robustness §9: a limit this low cuts the reply off
            self._send({"choices": [{"message": {"content": content[:len(content) // 2]}, "finish_reason": "length"}],
                        "usage": {"prompt_tokens": 900, "completion_tokens": limit}})
            return
        self._send({"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 900, "completion_tokens": 60}})
```

In `frontend/e2e/serve-strong.sh`, under `strong:` add `    max_output_tokens: 1000` (four-space indent, after
`model: fake-strong`).

- [ ] **Step 6: Write the e2e test**

Add to `frontend/e2e/workspace-tier1.spec.ts`, inside the describe block:

```ts
  test("a strong reply cut off by its limit recovers at double the limit, and the request log downloads", async ({ page }) => {
    const base = await startReview(page);
    await expect(page.locator(".ws-head .ct-headline")).toHaveText("1 hazard");      // the strong model's answers stand
    await page.goto(base);
    await page.getByRole("button", { name: /^AI \d+\/\d+$/ }).click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await usage.getByText(/^All calls/).click();
    await expect(usage.locator(".ai-calls tbody tr").first()).toBeVisible();
    await expect(usage.locator(".ai-calls")).toContainText("fake-strong");
    const one = usage.getByRole("link", { name: /^Requests of call \d+$/ }).first();
    await expect(one).toBeVisible();
    const [download] = await Promise.all([page.waitForEvent("download"),
                                          usage.getByRole("link", { name: "Download request log" }).click()]);
    expect(download.suggestedFilename()).toMatch(/^review-\d+-requests\.zip$/);
  });
```

- [ ] **Step 7: Build and run the e2e suite**

Run (from `frontend/`):
`npm run build && mkdir -p $CLAUDE_JOB_DIR/tmp/pw && TMPDIR=$CLAUDE_JOB_DIR/tmp/pw TORTOISE_CMD="env PYTHONPATH=$(cd ../backend && pwd) /media/anoop/ssd_1/Work/CodeTortoise/backend/.venv/bin/python -m codetortoise.cli" npx playwright test > $CLAUDE_JOB_DIR/tmp/e2e.log 2>&1; tail -15 $CLAUDE_JOB_DIR/tmp/e2e.log`
Expected: all pass (116). If one `startReview` 60 s timeout fails, run again with `--last-failed`; it passes.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/requestLog.ts frontend/src/components/requestLog.test.ts frontend/src/components/AiPill.tsx frontend/e2e/fake_llm.py frontend/e2e/serve-strong.sh frontend/e2e/workspace-tier1.spec.ts
git -c user.email=2929430+revelationnow@users.noreply.github.com commit -m "feat(usage): the AI usage view shows each call's model and links its logged requests; the e2e strong model cuts replies off below 2000 tokens

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
