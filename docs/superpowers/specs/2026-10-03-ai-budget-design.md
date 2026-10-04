# AI Calls on a Budget: Up-Front Pass, On-Demand Explanations and @tortoise — Design

Date: 2026-10-03. Status: draft for review. Step 3 of the production-readiness work.

## 1. Why

Today a review makes one AI call per finding, per layer and per flow (up to 6), plus a summary, with no limit and no
record. Large changes produce many findings, so cost grows without bound, and everything is spent up front whether
anyone reads it or not. Reviewers can't ask follow-up questions; the analysis is a one-time deep dive.

Goals:
- Every AI call is counted, and no call is made over a limit.
- A review starts with a small automatic pass; everything else is generated when someone asks, once, and shared.
- Anyone in a review can ask the AI a question in a comment thread with `@tortoise`; it reads the code it needs, within
  a per-question cap.
- The owner sees and controls spending from the review page.

Limits are measured in **calls** (decided 2026-10-03). Each prompt is already capped by `llm.max_context_tokens`, so
calls bound cost; token counts are recorded for the usage view, not enforced.

## 2. Ledger and limits

- **Ledger.** A table `llm_calls(id, review_id, user, purpose, target, started_at, finished_at, prompt_tokens,
  completion_tokens, outcome, error)`. `user` is the person who triggered the call, or `pipeline`. `purpose` is one of
  `summary`, `flow`, `finding`, `file`, `mention`. `target` names the item (flow id, finding id, depot path,
  comment id). Tokens come from the response's `usage` object when the endpoint reports it (else null). `outcome` is
  `ok`, `failed` or `refused`.
- **Limits** (`tortoise.yaml`):

  ```yaml
  llm:
    upfront_flows: 3          # flow narratives written when a review runs
    budget:
      per_review: 200         # calls per review, everyone and the pipeline together
      per_person_daily: 100   # calls one person can trigger per day (UTC), across reviews
      per_mention: 6          # rounds one @tortoise answer may take
  ```

- **Before every call** the budget is checked atomically (one SQLite transaction reserves the call):
  - review calls used (all `ok` and `failed` rows) < the review's budget (`per_review`, or the raised value);
  - for a person: their calls today < `per_person_daily`. Pipeline calls don't count against anyone's daily limit.
  A refused call is recorded with `outcome = refused` (it costs nothing) and the caller gets a reason:
  "this review has used its 200 AI calls; the owner can raise it" or "you've used your 100 AI calls today".
- **Failures count.** A failed call counts against both limits (it may have cost tokens); retries inside one client
  call don't count separately.
- **Raising a review's budget.** Only the owner, by any amount, recorded in a table `llm_budget(review_id, budget,
  set_by, set_at)` (the latest row wins).
- **No LLM configured:** no buttons, `@tortoise` greyed out in the @ menu, nothing recorded. A mention typed by hand gets the reply "I can't answer: no AI is configured for CodeTortoise." so the asker knows why nothing happened.

## 3. Up-front pass

When a review runs, the `llm` stage makes only:
- the change summary and risk (1 call);
- flow narratives for the top `upfront_flows` flows, in board order.

Finding explanations, the remaining flows and file summaries are no longer generated in the pipeline. Layer narratives
are not generated at all: nothing on the board shows them since the storyboard page was retired. Existing checks still apply (citations, house style, file tags). The pipeline's calls go through the ledger
like any other; if the review budget is too small for the whole pass, the pass stops and the stage says why.

## 4. On-demand explanations

| Item | Control | Call (existing prompt unless noted) | Result |
|---|---|---|---|
| Flow (desktop flow summary, phone flow reader) | **✦ Explain** | flow narrative | replaces `what`/`title` (LLM text, tagged) |
| Finding (Findings page) | **✦ Explain** | finding explanation | explanation, verify steps, hypotheses |
| File (file viewer header) | **✦ Summarise** | new: the file's diff, the facts of its changed functions and its annotations; returns what changed and what to check | shown above the code |

- `POST /api/reviews/{id}/explain {kind, target}` checks the budget, records the call and runs it in the job
  runner's thread pool; `202` with a job id. The board, findings and file summaries are re-read by the client when an
  `explain` event arrives on the review's event stream (the existing `/events` SSE), or by polling the item.
- Results are stored with the review (the board blob, findings, a new `file_summaries` blob) and shown to everyone.
  Asking again replaces the result after a confirmation, and costs a call.
- A refusal or failure is returned to the requester and shown where the button was.

## 5. @tortoise

**Trigger.** A new root comment or reply whose body contains `@tortoise` (case-insensitive, word-bounded). Edits never
trigger. The system immediately posts a reply in the same thread, author `tortoise`, with `pending: true` and body
"thinking…", and runs the answer as a job.

**Context, first round:** the question; the thread's previous comments (oldest first, trimmed); the anchor's context:
- line: the file's diff around the line (± 20 lines) and the facts of the function containing it;
- function: its code and facts;
- finding: the finding, its evidence and its functions' code;
- layer (chapter): the layer's changed functions and their facts;
- review: the change summary, the flows and the findings' titles.

**Rounds.** Each round the model returns JSON, either

```json
{"action": "read", "read": {"kind": "function", "name": "uart_send"}, "why": "…"}
{"action": "answer", "text": "…", "cites": ["N9", "//depot/driver/uart.c:17"]}
```

| `read.kind` | Argument | Returns |
|---|---|---|
| `function` | `name` | code and facts of that function (impact graph; else the symbol index's definition and the file text around it) |
| `callers` | `name` | up to 20 call sites from the symbol index, each with ± 3 lines |
| `declaration` | `name` | the struct/field/macro declaration and ± 5 lines |
| `file` | `path`, `from`, `to` | up to 200 lines of a file |
| `search` | `name` | where the name is defined, called and used (symbol index rows, up to 50) |

- Reads go through the existing read-only paths: the change set for changed files, `Source.read` for others (same
  single-file validation as `/source`), the symbol index for names. Nothing outside the workspace; no new Perforce
  commands.
- What was read accumulates in the prompt, trimmed to `llm.max_context_tokens` (oldest reads first).
- At most `per_mention` rounds; the last round's prompt says it must answer. Each round is one ledger row
  (`purpose = mention`, `target` = the reply's comment id) and counts against the review budget and the asker's daily
  limit. A refused round ends the answer.

**Answer.**
- Checked like other LLM text: it must cite at least one function id or file it was given or read; it follows the
  house style (`check_style`, explanation mode). A failed check gets one more round asking it to fix the answer (if
  rounds remain), else the reply says the answer failed the checks.
- The reply records `files` (the files whose code it saw: anchor, reads) as its tag, and a `read` list shown as
  "read: uart_send, callers of uart_send, logger.c 10–30".
- When a limit stops it or the model fails, the reply says so ("I couldn't answer: …") and is no longer pending.

**Storage.** Comments gain columns `ai_meta` (JSON: `pending`, `read`, `files`, `calls`, `error`) and the author
`tortoise`. tortoise replies can't be edited by users; the owner can delete them like any comment.

## 6. Interface

- **@ menu** in every comment box (desktop, cards, viewer, panel, phone): typing `@` opens a list under the cursor —
  **@tortoise** first ("ask the AI about this thread — reads code as needed, up to 6 AI calls", with calls left on the
  review and today), then the review's people (owner and anyone who commented; plain text, no notifications). Typing
  narrows the list; ↑/↓ move; Enter or Tab inserts; Esc closes; touch works. When @tortoise can't run (no LLM, a limit
  reached) it is shown greyed out with the reason.
- **tortoise replies:** the tortoise icon, an **AI** label, the "read:" line, and while pending "thinking… (round n of
  6)", updated live from the event stream.
- **✦ buttons** on flows, findings and files, with the cost on hover ("1 AI call · 143 left on this review").
- **Review header, owner only:** an **AI 57/200** pill; clicking it opens a small popover with the usage summary and a
  **Raise budget** field (new total). Everyone else sees the pill without the control. When a refusal is shown to the
  owner, it carries a **Raise budget** button too.
- **Usage view** (from the pill, and the phone ☰): this review's calls by person and purpose, the list of calls
  (time, who, what, tokens, outcome), and your own calls today against your limit.
- **Health page:** the configured limits and today's totals across reviews.

## 7. Permissions and stage 2

Every AI result carries file tags (spec 2026-10-01 §14.3): explanations as today, file summaries their file plus its
functions' files, tortoise replies the files they saw. Stage 2 filters by them; stage 1 shows everything.

## 8. Testing

- Ledger: a refused call is recorded and not made; per-review, per-person-daily and per-mention limits; failures count;
  pipeline calls skip the daily limit; concurrent reservations never exceed a budget (threads racing on one review).
- Up-front pass: exactly 1 + `upfront_flows` calls; stops cleanly when the budget is smaller.
- On-demand: each kind runs one call, stores its result, replaces on repeat, refuses over budget; file summaries are
  tagged.
- @tortoise: a mention posts a pending reply; a scripted fake LLM that reads `callers` then answers produces a reply
  with the read list, citations and tags; the round cap forces an answer; a read outside the workspace is refused; a
  limit ends it with an explanation; an edit doesn't trigger; follow-ups see earlier replies.
- API: explain and raise-budget permissions (raise: owner only); usage endpoint numbers.
- e2e: the @ menu (open, filter, keyboard select, greyed out without an LLM), a mention producing a tortoise reply
  (fake LLM server), ✦ Explain on a flow, the owner's AI pill raising the budget, a reviewer not seeing the control.

## 9. Out of scope

Money-based limits, per-model prices, streaming answers token by token, notifications for person mentions, and
@tortoise in Swarm comments.
