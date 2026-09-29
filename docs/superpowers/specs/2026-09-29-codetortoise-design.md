# CodeTortoise — Design Spec

Date: 2026-09-29
Status: Draft for review

## 1. Purpose

CodeTortoise is a self-hosted, CodeRabbit-style review assistant focused on *deep* impact analysis rather than flat, alphabetical diff listings. It targets large C/C++ codebases (first-class), built with a vendor clang-based cross toolchain, versioned in Perforce, with P4 Swarm as a side channel.

Given one or more Perforce changelists (CLs), it produces a **storyboard**: the change explained layer by layer, with call-flow diffs, blast radius, architecture impact, and side effects the author may not have called out (notably field mutations through local pointer/reference aliases). An LLM (user-supplied OpenAI-compatible endpoint + API key) writes narrative and explanations, grounded in deterministic static-analysis facts.

The web app is the system of record for review discussion. It is single-owner, locally hosted, and shared by link; viewers authenticate with their Perforce credentials and can comment.

### Success criteria (M1 POC)

- Owner enters a set of real shelved and/or submitted CLs against a configured base workspace; a review completes for a CL set touching a 5k+ TU codebase in minutes, not hours.
- Storyboard groups changes by inferred architectural layer, not by file path.
- Call-flow graph shows before/after/diff for changed functions, with precise (clang) vs heuristic (tree-sitter) edges distinguished.
- Blast radius includes both call edges and data-coupling edges from modified struct/class fields, including writes via local pointer/reference aliases.
- Findings for contract changes, field mutations, and header fan-out, each with cited evidence.
- LLM output only contains claims that cite fact/finding IDs; uncited content is dropped or marked unverified.
- Colleagues log in with P4 credentials and leave threaded comments anchored to lines, functions, findings, or chapters.
- Swarm: read review state, create review for a shelved CL, post a summary link comment.

### Non-goals (for now)

- Multi-tenant / multi-owner operation.
- Mirroring comments to Swarm.
- Full heap points-to analysis, function-pointer target resolution.
- Modifying the base workspace (no sync, unshelve, or edit — ever).
- Languages other than C/C++ before M3.

## 2. Key decisions

| Decision | Choice | Reason |
|---|---|---|
| Analysis engine | libclang (Python `clang.cindex`) primary, tree-sitter secondary | Compile DB is usually available; libclang C API is stable and can load the vendor's `libclang.so`. LibTooling would require exact vendor LLVM headers/libs. clangd LSP lacks AST detail needed by detectors. |
| Scale strategy | Repo-wide tree-sitter symbol index + clang on a budgeted TU subset | Codebase is 5k+ TUs. |
| Layers | Inferred from module dependency graph, LLM-named, cached per workspace | Owner preference: zero config. |
| Stack | Python 3.12+ (uv), FastAPI, SQLite; React + TypeScript + Vite; Cytoscape.js + ELK | Fastest iteration; one process serves API + static SPA. |
| Source of code | Existing synced base workspace, read-only; CL file contents via `p4 describe`/`p4 print`; "after" state via clang VFS overlay | Supports shelved and submitted CLs without mutating the workspace. |
| Auth | P4 login (`p4 -u <user> login`) → session cookie | Owner preference; no password/ticket storage. |
| Swarm | Read state, create review, post summary link; non-blocking | Owner's tooling is Swarm-based, but the app is the source of truth. |

## 3. Configuration

Backend read-only p4 commands (describe, print, where, have, client -o) run with the host environment's existing P4 credentials (the owner's login on the host), not with viewer credentials.

`tortoise.yaml` (path passed to `codetortoise serve --config`):

```yaml
owner: anoop                     # P4 user with admin rights in the app
server:
  host: 0.0.0.0
  port: 8765
  public_url: http://myhost:8765 # used in Swarm summary links
workspace:                       # REQUIRED base workspace
  p4port: ssl:p4:1666
  client: anoop-main-ws          # existing, synced client
  root: /work/main               # must equal the client's Root
  compile_commands: /work/main/build/compile_commands.json
toolchain:
  clang: /opt/vendor/bin/clang   # driver queried for implicit flags
  libclang: /opt/vendor/lib/libclang.so   # optional; upstream fallback
  resource_dir: null             # optional override
  strip_flags: []                # extra flags to drop for libclang
swarm:
  url: https://swarm.example.com
llm:
  base_url: https://llm.example.com/v1
  api_key_env: TORTOISE_LLM_KEY  # key read from env; never stored in DB or logged
  model: some-model
  max_context_tokens: 64000
analysis:
  caller_hops: 2                 # K
  tu_budget: 200                 # M
  flow_depth: 4                  # D
  blast_hops: 4
  header_sample_tus: 20
  lock_patterns: ["*lock*", "*Lock*", "pthread_mutex_*"]
  unlock_patterns: ["*unlock*", "*Unlock*"]
  atomic_patterns: ["std::atomic*", "__atomic_*", "atomic_*"]
  entrypoint_patterns: ["main", "*_isr", "*_irq_handler", "*Callback"]
```

### Startup validation (hard gate for creating reviews)

- `p4 -p <p4port> -c <client> client -o` succeeds; its Root equals `workspace.root`.
- `compile_commands` exists and parses.
- libclang loads (vendor path first, else bundled/upstream); record version.
- Toolchain driver query succeeds (see §5.4).
- LLM endpoint reachable (warning only).
- Swarm reachable (warning only).

Status is shown on an admin "Health" page. Reviews cannot be created while a hard check fails.

## 4. Architecture

Single Python process: FastAPI API + background job runner (in-process worker thread pulling from a SQLite-backed queue; clang parsing fans out to a `ProcessPoolExecutor`) + static React SPA.

```
                ┌──────────── Review (set of CLs) ────────────┐
 p4 / Swarm ──► Ingest ──► DiffMap ──► Clang facts (before/after) ──► Impact graph ──► Detectors ──► LLM storyboard ──► Store ──► Web UI
                              ▲              ▲                            ▲
                     tree-sitter      Symbol index (repo-wide,      Layer model (graph-
                     (hunk→function)  tree-sitter, cached)          inferred, cached)
```

### Units

| Unit | Responsibility | Interface (sketch) | Depends on |
|---|---|---|---|
| `vcs.Source` | Produce a `ChangeSet` for CL list | `load(cls: list[int]) -> ChangeSet` | p4 CLI / git |
| `vcs.P4Source` | Perforce impl | uses `p4 describe -s/-S`, `p4 print`, `p4 where`, `p4 have` | `p4` binary |
| `vcs.GitFixtureSource` | Dev/test impl: "CL" = git commit | same | git |
| `swarm.Client` | Swarm REST | `get_review(change)`, `create_review(change, desc)`, `post_comment(review_id, body)` | httpx |
| `index.SymbolIndex` | Repo-wide tree-sitter index | `callers_of(name)`, `includers_of(header)`, `member_refs(field_name)`, `defs(name)` | tree-sitter, SQLite |
| `toolchain.Toolchain` | libclang loading, flag preparation, VFS overlay | `args_for(file, overlay) -> list[str]`, `make_overlay(files) -> Path` | compile DB, vendor clang |
| `facts.FactExtractor` | Protocol: parse TU → `Facts` | `extract(tu, variant) -> Facts` | — |
| `facts.ClangExtractor` | libclang impl | | `toolchain` |
| `facts.TreeSitterExtractor` | fallback impl (heuristic) | | tree-sitter |
| `diffmap` | Hunks → changed functions | `map(changeset) -> list[FunctionChange]` | tree-sitter |
| `aliasflow` | Access-path / alias field-write analysis | `field_accesses(fn_cursor) -> list[FieldAccess]` | libclang cursors |
| `impact` | Build graph, flows, blast radius, fan-out | `build(facts_before, facts_after, changes) -> ImpactModel` | networkx |
| `detectors` | Rules → `Finding`s | `Detector.run(impact, facts) -> list[Finding]` | impact |
| `layers` | Module graph → levels → names | `layer_of(path) -> Layer` | SymbolIndex, llm |
| `llm.Client` | OpenAI-compatible chat, JSON output, grounding filter | `complete_json(prompt, schema) -> Model` | httpx, pydantic |
| `pipeline` | Staged job runner with status | `run(review_id)` | all above |
| `store` | SQLite persistence | repositories per entity | sqlite3 |
| `web` | REST API, auth, SPA | FastAPI routers | store, pipeline |

Language extension (M3) = new `FactExtractor` impls + tree-sitter grammars; downstream units are language-agnostic, operating on `Facts`.

## 5. Data flow

### 5.1 Ingest

For each CL:
- `p4 describe -s <cl>` → status (`pending`/`submitted`), description, user, files. Pending CLs are read with `-S` (shelved files); a pending CL with no shelved files is an error.
- Per file: action (add/edit/delete/move/integrate), depot path, rev.
  - Shelved: before = `p4 print -q <depot>#<base rev>`, after = `p4 print -q <depot>@=<cl>`.
  - Submitted: before = `<depot>#<rev-1>` (empty for add), after = `<depot>#<rev>`.
- Local path via `p4 -c <client> where <depot>`.
- **Stacking:** CLs are sorted ascending. If a file appears in multiple CLs, CL(n)'s before becomes CL(n-1)'s after; per-CL diffs are kept for the per-CL tab, and a cumulative diff (first before → last after) drives analysis.
- **Drift check:** compare `p4 have` rev of each touched file to the analysis base rev. Mismatches are recorded and displayed as a review banner. The rest of the tree is analyzed at the workspace's have revisions.

Swarm: `get_review(cl)` per CL; failures recorded, never fatal.

`ChangeSet` = `{cls: [ClMeta], files: [FileChange{depot, local, action, before, after, per_cl_diffs}], drift: [...]}`.

### 5.2 DiffMap (tree-sitter)

Parse before/after text of each changed C/C++ file with tree-sitter-c/cpp. Enumerate function definitions (qualified name from enclosing namespaces/classes, extents). Intersect with unified-diff hunks. Classify each function: `added | removed | body_modified | signature_changed`. Header changes also classify `type_changed` (struct/class/enum bodies), `macro_changed`. Output `FunctionChange{qualname, file, before_extent, after_extent, kind, hunks}`. USRs attached later by clang facts; matching before↔after by USR, falling back to qualified name + parameter count.

### 5.3 TU selection

1. Seed TUs: compile-DB entries for changed `.c/.cc/.cpp` files. For each changed header: `includers_of` transitively via SymbolIndex include graph; total count recorded (fan-out), and a sample of `header_sample_tus` TUs (preferring those that reference changed symbols) added as seeds.
2. Caller expansion: for each changed function name, `callers_of(name)` up to `caller_hops`; for each changed/written field, `member_refs(field)`; collect owning TUs.
3. Rank by (hop distance, reference count); take up to `tu_budget`. Unselected TUs contribute only heuristic SymbolIndex edges.

### 5.4 Toolchain and clang facts

**Toolchain preparation:**
- Load `libclang` from `toolchain.libclang`; else the libclang bundled with the Python `libclang` wheel. Record version and whether it is vendor or upstream.
- Driver query (once, cached by driver path + mtime): run `<clang> -E -dM -v -x c++ /dev/null` and `-x c` equivalents with the target flags from a representative compile-DB entry; parse implicit include dirs and predefined macros. When libclang is upstream, pass these as `-isystem`/`-D` plus `-resource-dir` (vendor's, from `<clang> -print-resource-dir`) and keep `--target`/`--sysroot` from the compile entry.
- Flag sanitation: drop output/codegen-only flags (`-o`, `-c`, `-M*`, `-W*` optional), and any flag in `strip_flags`; unknown-flag diagnostics from a probe parse are auto-added to a per-workspace strip list and surfaced on the Health page.
- "After" state: write after-contents of changed files to a review scratch dir and generate a clang VFS overlay YAML mapping local workspace paths → scratch files; pass `-ivfsoverlay`. "Before" state uses before-contents overlaid the same way (the workspace may not match the CL base; see drift).

**Per-TU extraction** (`ClangExtractor`, runs in process pool, both variants):
- `TuInfo{file, variant, error_count, missing_includes, confidence}`; confidence = precise if error_count == 0, degraded if errors but AST present, failed → fall back to `TreeSitterExtractor` for that TU.
- `Function{usr, qualname, signature, return_type, params[{name,type,is_const,default}], file, extent, is_virtual, overrides[], is_static, linkage}` — only for functions defined in the TU's main file or changed headers, plus declarations of callees.
- `CallEdge{caller_usr, callee_usr, site, kind: direct|virtual|fnptr_candidate, result_used: bool, result_compared_to: [literals]}`.
- `FieldAccess` (from `aliasflow`, §5.5).
- `GlobalAccess{fn_usr, var_usr, mode: read|write, site}`.
- `LockOp{fn_usr, op: lock|unlock, target_expr, site, block_id, order}` (patterns from config).
- `Record{usr, name, size, align, fields[{usr, name, type, offset}], vtable_methods[]}` via `Type.get_size/get_offset`.
- `Macro{name, definition_hash, file}` for changed headers.

Parse results cached by `(sha256(file contents incl. overlays of its includes that changed), flags hash, libclang version)` — M2 (M1 caches within a review only).

### 5.5 Alias-aware field mutation analysis (`aliasflow`)

Goal: find every field written by a function, including writes through local pointer/reference aliases, expressed as access paths rooted at something visible to callers.

**Access path:** `Root.f1.f2...` where Root ∈ `param#i`, `this`, `global:<usr>`, `local:<name>` (local objects; not visible to callers). Each `fk` is a FieldDecl USR (e.g. `c:@S@Foo@FI@count`); `[]` denotes array element (index-insensitive); `*` denotes dereference of a pointer field.

**Intraprocedural algorithm** (flow-insensitive within a function for M1; single pass in source order, re-assignments union):
1. Alias map `A: local_var → set[AccessPath]`, initialized empty.
2. On declarations/assignments to a local pointer or reference variable `v`:
   - `T *v = &E;` / `T &v = E;` / `v = &E;` → `A[v] ∪= path(E)`
   - `T *v = E;` where E is a pointer-typed field expression (`s->child`) → `A[v] ∪= path(E) + '*'`
   - `T *v = &E[i];` / `v = E + k;` → `path(E) + '[]'` (confidence: may)
   - `v = w;` where w is an aliased local → `A[v] ∪= A[w]`
   - casts on RHS → propagate with confidence `may`
3. `path(E)`: recursive over `MEMBER_REF_EXPR`, `ARRAY_SUBSCRIPT_EXPR`, unary `*`/`&`, `DECL_REF_EXPR` (param/global/this/local, or aliased local via `A`).
4. Writes: LHS of `=`, compound assignments, `++/--`; `memcpy/memset/memmove/strcpy`-family first arg; passing `&E` or `E` to a non-const pointer/reference parameter of a callee (recorded as `may_write_via_call{callee_usr, arg_index}`).
5. Emit `FieldAccess{fn_usr, path, mode: read|write|may_write, via_alias: [var chain], site, confidence: precise|may}`.

Operator kinds use the libclang `binary_operator`/`unary_operator` cursor properties when available (clang ≥ 17); otherwise the operator token is found by tokenizing the cursor extent between operand extents.

**Interprocedural summaries (M2):** bottom-up over the call graph with SCCs collapsed and iterated to fixpoint (bounded). Summary = set of `(root, path, mode)` for roots `param#i/this/global`. At a call site, callee summary paths are rebased onto the caller's argument access paths (including aliased locals). M1 uses only direct `may_write_via_call` records (one level).

**Before/after diff:** compute summaries (or M1 direct accesses) for each changed function in both variants; new/removed writes (by field USR + root kind) become `field_mutation` findings with the alias/call chain as evidence.

### 5.6 Impact model

Graph (networkx `MultiDiGraph`), nodes = functions (USR), plus field nodes (FieldDecl USR) for data coupling.

- Call edges from clang facts (`confidence=precise`) and SymbolIndex name matches for unselected TUs (`confidence=heuristic`).
- Data edges: `fn --writes--> field`, `field --read_by/written_by--> fn`. Precise from `FieldAccess` in selected TUs; heuristic from SymbolIndex `member_refs(field_name)` restricted to matching member name and, where resolvable by tree-sitter, matching record type name.

Computed artefacts:
- **Call flows:** for each changed function, forward paths to `flow_depth` in before and after graphs; diff status per node/edge: `added | removed | changed | unchanged`.
- **Blast radius:** from changed functions and fields they write, reverse call reachability and data-coupling reachability to `blast_hops`. Score per reached function = `Σ over paths (1/hop × edge_confidence_weight)` (precise 1.0, may 0.6, heuristic 0.4), ×1.5 if declared in a public header (a header included outside its own module), ×1.5 if an entry point (matches `entrypoint_patterns` or registered as callback — callback registration is M2), ×1.3 if reached via virtual dispatch. Ranked; rings by hop.
- **Header fan-out:** per changed header, total dependent TUs and breakdown by layer.

### 5.7 Detectors

Common output: `Finding{id, kind, severity: info|low|medium|high, title, functions[], fields[], evidence: [fact_id], deterministic_summary, llm_explanation?, hypotheses?[]}`.

| Detector | M | Rules (initial) |
|---|---|---|
| `contract` | M1 | signature/return type/param const/default changed; new `return` of a literal/enumerator not present before; for each caller: `result_used == false` → medium; caller compares result against literals that don't include new return values → high. |
| `field_mutation` | M1 | new/removed field writes per changed function (incl. alias chains); severity raised when the field has readers outside the changed CL set, or the write is via `may` alias. |
| `header_fanout` | M1 | changed header with type/macro change; severity by fan-out count and number of layers affected. |
| `shared_state` | M2 | new/changed global/static writes; other readers/writers listed; interprocedural summary-based. |
| `concurrency` | M2 | lock/unlock pairing changed; new calls between lock and unlock (block order); changed atomics; function reachable from ≥2 entry points and writes shared state. |
| `abi_virtual` | M2 | record size/offset/order changes; vtable method set/order changes; override set changes; macro redefinition with use count. |

### 5.8 Layers

- Module = directory at a configurable depth (default: deepest directory containing ≥ N source files, N=5) — heuristic, overridable later.
- Module graph edges from `#include` (SymbolIndex) and cross-module call edges (heuristic).
- Condense SCCs, assign topological level (level 0 = no outgoing dependencies = lowest layer). Merge levels with too few modules into neighbours to target 3–8 layers.
- LLM names each layer from module names and sample file names (JSON: `{level, name, description}`).
- Cached per workspace keyed by SymbolIndex generation; recomputed on explicit refresh. Owner can rename layers in UI (stored overrides).

### 5.9 LLM

OpenAI-compatible `POST {base_url}/chat/completions`, `response_format: {"type": "json_object"}` when supported, else instruction-only JSON; pydantic validation, one repair round.

Calls:
1. `layer_names` (§5.8).
2. `finding_explain` per finding (batched): input = finding + evidence facts + code snippets of involved functions (after, and before where changed) within budget; output = `{explanation, verify_steps[], hypotheses[{text, cites:[fact_id]}]}`.
3. `chapter_narrative` per layer: input = changed functions in layer, their flows, findings, cross-layer edges; output = `{narrative, cites[], cross_layer_effects[{text, cites}]}`.
4. `storyboard_summary`: input = chapter outputs + top findings; output = `{summary, risk: low|medium|high, review_order: [function_or_chapter_ids], cites[]}`.

**Grounding filter:** every emitted statement item must cite ≥1 known fact/finding ID; items citing unknown IDs or none are dropped (hypotheses) or shown with an "unverified" badge (narrative sentences cannot be split reliably, so a narrative with zero valid cites is badged as a whole).

**Budgeting:** token estimate by chars/4; priority order: changed function bodies > findings evidence > top-N blast-radius callers' signatures > caller snippets.

API key read from the configured env var; never persisted, never logged; requests/responses logged at debug level with the Authorization header redacted.

### 5.10 Pipeline

Stages: `ingest → swarm_read → diffmap → tu_select → facts → impact → detectors → layers → llm → finalize`. Each stage persists output and status `pending|running|ok|degraded|failed` + message + timing. Later stages run if their inputs exist (degraded mode). Re-run: owner button; M2 adds auto re-run when shelf/Swarm revision changes (polling).

## 6. Storage (SQLite)

Tables (JSON columns for fact payloads):
- `reviews(id, title, created_by, created_at, status, risk, config_snapshot)`
- `review_cls(review_id, cl, status, description, user, swarm_review_id, swarm_state_json)`
- `files(id, review_id, depot, local, action, before_text, after_text, per_cl_diffs_json)`
- `stages(review_id, name, status, message, started_at, finished_at)`
- `functions(review_id, usr, variant, json)`, `edges(review_id, variant, json)`, `field_accesses(review_id, variant, json)`, `tu_info(review_id, json)`
- `impact(review_id, json)` (flows, blast radius, fan-out)
- `findings(id, review_id, kind, severity, json, state: open|ack|dismissed)`
- `llm_outputs(review_id, kind, key, json)`
- `layers(workspace_key, json)`, `layer_overrides(workspace_key, level, name)`
- `comments(id, review_id, parent_id, author, body, anchor_kind: line|function|finding|chapter, anchor_json, resolved, created_at, edited_at)`
- `swarm_posts(review_id, cl, kind, swarm_comment_id, posted_at)` — idempotency
- `sessions(token_hash, user, created_at, expires_at)`
- `symbol_index` tables: `sym_files(path, have_rev, digest)`, `sym_defs(name, qualname, path, line)`, `sym_calls(caller_path, caller_qualname, callee_name, line)`, `sym_includes(path, included)`, `sym_members(name, path, line, record_hint)`

## 7. Web UI

SPA routes:
- `/login` — P4 username/password → `POST /api/login` runs `p4 -p <p4port> -u <user> login -p` with password on stdin (`-p` prints the ticket instead of writing it to the host's tickets file); success → random session token (HTTP-only, SameSite=Lax cookie; hash stored). Password discarded. For non-owner users the ticket is discarded; for the owner it is held in memory only, for Swarm calls (§8).
- `/` — reviews list (status, risk, CLs, created).
- `/new` — owner only; CL numbers input; live stage progress (SSE).
- `/health` — owner only; startup checks, toolchain info, strip list, SymbolIndex status + rebuild button.
- `/r/:id` — review with tabs:
  - **Storyboard:** summary card (risk, review order), drift banner, chapters bottom→top layer; each chapter: narrative (with cite links), changed functions, mini flow-diff, findings, hunks.
  - **Call flows:** Cytoscape + ELK layered layout; layer bands; before/after/diff toggle; node colours by diff status; edge styles: solid=precise call, dotted=heuristic call, dashed=data (field) edge; click node → side panel with function diff, findings, comments.
  - **Blast radius:** rings by hop, ranked list, filters (layer, edge kind, confidence), header fan-out table.
  - **Findings:** by severity; evidence, LLM explanation, hypotheses (unverified flagged); ack/dismiss (owner).
  - **Files:** per-file diff (cumulative or per-CL), inline line comments.
  - **CLs:** per-CL diffs and Swarm panel (review link, state, votes, reviewers; "Create review" for shelved without review; "Post summary link").
- Comments: threads on line/function/finding/chapter anchors; reply, resolve; author = session P4 user; edit/delete own; owner can delete any.

Permissions: owner = create/re-run/delete reviews, Swarm actions, health, ack/dismiss findings. Others = view + comment.

## 8. Swarm integration

REST (API version detected from `/api/version`, target v9+/v11), authenticated with the owner's P4 ticket obtained at owner login (held in memory only for the process lifetime; if absent, Swarm actions prompt the owner to re-login).
- Read: `GET /api/vX/reviews?change[]=<cl>`.
- Create: `POST /api/vX/reviews` with `change=<cl>`, description.
- Comment: `POST /api/vX/comments` with `topic=reviews/<id>`, body = summary + `public_url/r/<review_id>`.
Posts recorded in `swarm_posts`; repeat posts require explicit confirmation.

## 9. Error handling

- Stage failures isolated; review renders available outputs with per-stage status.
- Per-TU confidence surfaced on edges/findings; fallback extractor on failed parse.
- LLM: 2 retries with backoff on transport/5xx/timeout; one JSON repair; else stage degraded.
- p4 errors shown verbatim; Swarm errors non-fatal badges.
- All subprocess calls have timeouts; p4 calls use `-ztag` where parsing is needed.
- No write operations against the workspace; enforced by a single `P4Runner` that allowlists read-only commands plus `login` (auth) — Swarm writes go through HTTP only.

## 10. Security notes

- Server binds to configured host; intended for trusted LAN/VPN. HTTPS termination is out of scope for M1 (documented: put behind a reverse proxy for TLS).
- Passwords only transit to `p4 login` via stdin; never logged or stored.
- LLM API key from env only; redacted in logs.
- Session tokens random 256-bit; stored hashed; expiry 7 days.
- Code snippets are sent to the configured LLM endpoint — documented prominently on Health page.

## 11. Testing

- **Unit + golden tests** on a C/C++ fixture repo (`tests/fixtures/cfixture/`): modules `hal/`, `driver/`, `service/`, `app/`; cases for alias field writes (pointer, reference, array element, pointer field deref, cast), lock scope change, signature/return-value change, struct layout change, virtual override change, header fan-out. Paired patches act as "CLs" via `GitFixtureSource`. Golden JSON for diffmap, facts, aliasflow, impact, detectors.
- **libclang in dev/CI:** PyPI `libclang` wheel.
- **p4 integration:** local `p4d` in a temp dir (auto-skip if binary absent): submit fixture, create shelved and submitted CLs, verify `P4Source` stacking and drift.
- **Swarm:** respx-recorded HTTP contract tests.
- **LLM:** fake OpenAI-compatible server (FastAPI in-process) with canned responses; tests for grounding filter, repair round, budgeting.
- **Frontend:** Vitest for components; Playwright smoke (login with fake P4 auth backend, create review on fixture, storyboard renders, graph renders, comment round-trip).

## 12. Milestones

**M1 — POC:** config + health; `P4Source`, `GitFixtureSource`, drift check; toolchain (vendor/upstream libclang, driver query, flag sanitation, VFS overlay); tree-sitter diffmap + basic SymbolIndex (defs, calls, includes, member refs; full build, no incremental); `ClangExtractor` (functions, calls, intraprocedural aliasflow, direct may-write-via-call); impact (flows, blast radius with call + data edges, header fan-out); detectors `contract`, `field_mutation`, `header_fanout`; layers (graph-inferred, LLM-named, overridable names); LLM finding/chapter/summary with grounding; web UI (login, reviews, new, health, storyboard, call flows, blast radius, findings, files, CLs/Swarm) + comments; Swarm read/create/post.

**M2 — Foundation:** interprocedural write summaries; `shared_state`, `concurrency`, `abi_virtual` detectors; callback-registration entry points; persistent parse cache; SymbolIndex incremental refresh via `p4 have`; auto re-run on shelf/Swarm update; dedicated tool-managed workspace option.

**M3 — Languages:** Python, Rust, JS `FactExtractor`s (tree-sitter-first); optional vendor clangd LSP call-hierarchy source.

## 13. Repository layout

```
backend/
  pyproject.toml            # uv-managed
  codetortoise/
    config.py  health.py  cli.py
    vcs/ (source.py, p4.py, gitfixture.py, p4runner.py)
    swarm/client.py
    index/symbols.py
    toolchain/ (loader.py, driver_query.py, flags.py, overlay.py)
    facts/ (model.py, clang_extractor.py, treesitter_extractor.py, aliasflow.py)
    diffmap.py  impact.py  layers.py
    detectors/ (base.py, contract.py, field_mutation.py, header_fanout.py)
    llm/ (client.py, prompts.py, grounding.py)
    pipeline.py  store.py
    web/ (app.py, auth.py, routes/*.py, static/)
frontend/                   # React + TS + Vite; builds into backend/codetortoise/web/static
tests/
  fixtures/cfixture/
docs/
```
