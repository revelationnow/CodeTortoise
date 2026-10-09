# LLM robustness and request log — design

Date: 2026-10-08. Status: draft for the owner's review.

Sub-project B of the owner's feedback from a real change set (2026-10-08). The other sub-projects — A: fan-out filter,
C: layout fixes, D: introduction — get their own designs.

## 1. Problem

On a real change set the strong model sometimes sent back JSON that did not parse, and the stories of several files
fell back to the rules. Some replies looked cut off by length (an output token limit); others were not long. Nothing
recorded enough to tell which: `llm_calls` keeps one row per call with at most 500 characters of the error, and none of
the HTTP requests inside the call.

What the code does today:

- `LlmClient.chat` tries a request 3 times (waits 1 s, 2 s) on network errors, 5xx and 429, and steps the response
  format down (`json_object` → `json_schema` → none) when a server rejects it.
- `LlmClient.complete_json` sends a bad reply back once ("reply again with valid JSON") with the same limit.
- It never reads the stop reason, so a reply cut off by the limit looks like bad JSON, and the repair round, sent with
  the same limit and a longer prompt, is likely cut off again.
- With the chat API the configured `max_output_tokens` is never sent; only the Messages and Responses APIs send it.
- When a strong call fails, a stories chunk is grouped by the rules, a story's review keeps the detectors' verdicts, and
  the threads keep their fixed text. The weak model is never tried.
- One ledger call (`Ledger.call`) can hold many HTTP requests: up to `rounds` (20) read rounds, each with a repair
  round and its network retries.

## 2. Goals

1. A reply cut off by the output limit is recognised as such and retried with a higher limit, not "repaired".
2. A strong call that still fails is tried once more on the strong model, then on the weak model, each time with a
   higher output limit, before the stage's own fallback.
3. Every HTTP request to a model can be kept — request body, response body, status, stop reason, limit, tokens,
   timing — so a failure can be root-caused afterwards. A YAML field chooses whether all requests are kept or only
   those of calls that went wrong.
4. The owner can read the log from the CLI and download it from the review's AI usage view.
5. The review's notes say what happened to each piece: which tries failed, how, and who did the work in the end.

Not goals: a page that browses requests in the app; splitting chunks smaller on truncation; changing prompts.

## 3. Configuration

New fields under `llm:` in `tortoise.yaml`:

```yaml
llm:
  request_log: all            # all | failed | off
  request_log_days: 14        # requests older than this are deleted
  max_output_tokens_cap: 32768  # no try asks for more output tokens than this (both models)
```

- `request_log: all` keeps every request; `failed` keeps a call's requests only when the call failed, or when any of
  its replies was cut off or needed a repair round; `off` keeps none. Default `all`.
- `max_output_tokens_cap` should not exceed what the models accept. A server that rejects a raised limit (HTTP 400 on
  a limit above the client's own) gets the request again at the client's own limit (none when unset), and that call
  raises it no further; the log shows both.
- The existing `llm.max_output_tokens` and `llm.strong.max_output_tokens` stay the starting limits.

## 4. The client (`llm/client.py`)

### 4.1 Stop reason

`chat()` reads the stop reason of every successful reply:

| API | cut off when |
|---|---|
| chat | `choices[0].finish_reason == "length"` |
| messages | `stop_reason == "max_tokens"` |
| responses | `status == "incomplete"` and `incomplete_details.reason == "max_output_tokens"` |

A cut-off reply raises `LlmTruncated(LlmError)`, which carries the limit sent (or none) and the completion tokens the
server reported (or none). Other stop reasons are recorded but change nothing.

### 4.2 The limit on the chat API

The chat API now sends the limit as `max_tokens` when one is set. A server that rejects it with a 400 naming
`max_tokens` and mentioning `max_completion_tokens` (OpenAI's newer models) gets `max_completion_tokens` from then on —
the same step-down the response format already does. No limit set: no field sent, as today. Step-downs are shared
by every per-try view of a client, so they are learned once, and they cost none of the request's attempts.

### 4.3 Raising the limit

A client has a starting limit `start` (its configured `max_output_tokens`) and a base for doubling:
`base = start or 8192`. A per-try view of the client (§5) may carry a higher starting limit.

Inside `complete_json`:

- A cut-off reply is not repaired. The same prompt is sent again at once with the limit doubled from the one just sent
  (from `base` when none was sent), capped at `max_output_tokens_cap`. A reply cut off at the cap is a failure:
  `LlmTruncated` propagates.
- A complete reply that does not parse or validate gets the repair round as today, sent with the doubled limit.
- Once raised, the limit stays raised for the rest of that try (later read rounds of the same conversation use it).

### 4.4 Attempt records

The client keeps, per thread, a list of the HTTP attempts of the current call, as it keeps token usage today
(`start_log()` clears it, `take_log()` returns and clears it). Each record:

- `seq` (order within the call), `sent_at`, `elapsed_ms`, `url` (path only), `model`;
- `status` (HTTP status, or none for a network error), `error` (text, or none);
- `stop_reason` (the API's own value), `truncated` (bool), `repair` (bool: this request was a repair round),
  `max_output_tokens` (the limit sent, or none);
- `prompt_tokens`, `completion_tokens` (as reported, or none);
- `request` (the JSON body), `response` (the response text, or none).

Headers are never recorded: the `Authorization` and `x-api-key` values never reach a record.

## 5. Tries (`llm/tiers.py`, new)

One helper runs a strong-model piece of work through its tries:

```python
def try_tiers(ledger: Ledger | None, rid: int | None, purpose: str, target: str,
              fn: Callable[[LlmClient], T], strong: LlmClient, weak: LlmClient | None,
              skip_strong: bool = False) -> Tried[T]
```

Tries, in order:

1. **strong** — the strong client at its own starting limit.
2. **strong, fresh** — a new conversation (`fn` called again) on the strong client, starting at
   `min(cap, 2 × strong.base)`.
3. **weak** — the weak client, starting at `min(cap, 4 × max(weak.base, strong.base))`.

Rules:

- Each try is its own `ledger.call(...)` with the stage's purpose; the target gets " (fresh)" or " (weak)" appended for
  tries 2 and 3. Each try counts against the budget the purpose belongs to (the tier-1 budget for all four purposes).
- `LlmUnreachable` on try 1 skips try 2. `skip_strong=True` (the stage already saw the strong model unreachable this run)
  starts at try 3.
- `Refused` from any try stops at once and propagates: the stage's budget handling applies, as today.
- No weak client configured: try 3 is skipped.
- All tries failed: `TiersFailed` is raised, carrying each try's failure.
- `Tried[T]` carries the value, which try produced it (`"strong" | "fresh" | "weak"`), the model, and the failures of
  the tries before it.
- A per-try view of a client shares its HTTP connection, usage and log state, and has its own starting limit.

`failure_text(f)` words one failure for a note: "reply cut off at 16384 tokens", "invalid JSON twice",
"unreachable", "HTTP 400: …" (first 120 characters).

## 6. The stages

The four strong-model call sites use `try_tiers` in place of `ledger.call(strong, …)`:

| stage | call site | last resort (unchanged) |
|---|---|---|
| stories chunk (each agreement run too) | `form_stories` | the rules group the chunk's pieces |
| merge pass | `form_stories` | the chunks' stories stand unmerged |
| story review | `review_stories` | the story's findings keep the detectors' verdicts |
| thread text | `write_threads` | the fixed thread text stays |

Notes. When a later try produced the answer, or every try failed, the stage adds one note naming what happened, e.g.:

- `chunk 2: fake-strong: reply cut off at 16384 tokens; fresh try: reply cut off at 32768 tokens; gpt-4o-mini grouped
  its pieces`
- `story s3: fake-strong: invalid JSON twice; fresh try: unreachable; gpt-4o-mini: invalid JSON twice; its findings stay
  as the detectors left them`
- `thread text: fake-strong: HTTP 500 …; gpt-4o-mini wrote it`

An answer the first try produced adds no note. Notes are the existing stage notes, shown where they are shown today.

Other effects:

- A chunk the weak model grouped counts as fallen back: the plan is not `complete`, as with a rules chunk today.
- Thread text the weak model wrote is not cached (the cache already skips a run with notes), so the next run asks the
  strong model again. The stage message says who wrote it: "thread text by gpt-4o-mini (the strong model failed)".
- The stage's existing `unreachable` flag now means "skip the strong tries" (`skip_strong=True`) rather than "skip the
  model": later chunks and stories still get the weak try.
- Weak-model work (explanations, side-effect judgments, narratives) keeps its own handling; it gains §4's truncation
  handling and the request log, not tries.

## 7. Storage

### 7.1 Schema

`llm_calls` gains a `model TEXT` column (added by the store's existing `ALTER TABLE` migration pattern); `reserve`
records the client's model.

New table:

```sql
CREATE TABLE IF NOT EXISTS llm_requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT, call_id INTEGER NOT NULL, review_id INTEGER, seq INTEGER NOT NULL,
  sent_at TEXT NOT NULL, elapsed_ms INTEGER, url TEXT, model TEXT, status INTEGER, error TEXT, stop_reason TEXT,
  truncated INTEGER NOT NULL, repair INTEGER NOT NULL, max_output_tokens INTEGER, prompt_tokens INTEGER,
  completion_tokens INTEGER, request BLOB, response BLOB);
CREATE INDEX IF NOT EXISTS llm_requests_call ON llm_requests(call_id);
CREATE INDEX IF NOT EXISTS llm_requests_review ON llm_requests(review_id, sent_at);
```

`request` and `response` are zlib-compressed UTF-8 (the request as JSON text).

### 7.2 Writing

`Ledger.call` clears the client's log before `fn` and takes it in `finish`:

- `all`: every record is written.
- `failed`: the records are written when the call failed, or when any record is `truncated` or `repair`.
- `off`: nothing is written.

Calls made without a ledger (tests, `stories-check` without one) are not logged.

### 7.3 Pruning

Rows with `sent_at` older than `request_log_days` are deleted when the server starts and when a review run starts.

## 8. Reading the log

### 8.1 CLI

`tortoise llm-log REVIEW [--call N] [--out DIR]` (with `--config` like the other commands):

- prints one line per request, in order: call id, purpose, target, model, seq, status, stop reason, limit, prompt and
  completion tokens, ms, error (first 80 characters);
- with `--out DIR`, writes `DIR/call-<id>/<seq>.json` per request: the metadata fields, `request` (parsed JSON) and
  `response` (parsed JSON when it parses, else the text);
- prints "no requests logged for review N" (exit 0) when there are none, and mentions `request_log: off` when that is
  the setting.

### 8.2 Web

- `GET /api/reviews/{rid}/ai/requests.zip[?call=N]` returns a zip of the same files; 404 when the review has none
  (or the call has none). Any user who can open the review can download it, as with `/ai/calls`.
- `/ai/calls` rows gain `model` and `requests` (the count logged for that call).
- The AI usage view: a "Download request log" link above the "All calls" table when any call has requests, and a
  "requests" link in each row whose `requests` is above 0 (`?call=N`). The model column shows each call's model.

## 9. Testing

pytest:

- client: the stop reason of each API sets `truncated`; a cut-off reply is resent with the doubled limit and no repair;
  the cap ends it with `LlmTruncated`; a complete invalid reply is repaired at the doubled limit; chat sends
  `max_tokens` and steps to `max_completion_tokens` on the 400; no record holds the API key; records carry the fields
  of §4.4.
- `try_tiers`: the order and starting limits; `LlmUnreachable` skips the fresh try; `skip_strong`; `Refused`
  propagates; no weak client; `TiersFailed` carries every failure; `failure_text`.
- stages: a stories chunk the weak model grouped (note, plan not complete); a chunk every try failed (rules, note); a
  review story and the thread text falling back to the weak model and then to their last resort.
- ledger and store: the three `request_log` modes; the `model` column; pruning by age; the migration on an old
  database.
- CLI: the printed lines and the files; the empty case.
- web: the zip (all, one call, 404), the calls rows' `model` and `requests`.

vitest: the usage view shows the download link and the per-row links only when requests exist.

e2e (strong-model server, port 8795): `serve-strong.sh` sets the strong `max_output_tokens: 1000`; `fake_llm.py`
answers any request whose limit is under 2000 with a cut-off reply (`finish_reason: "length"`). Every strong call is
then cut off once and recovers at 2000, so the existing strong-model tests still see the same answers. A new test opens
the usage view, sees the "requests" links and downloads the zip.
