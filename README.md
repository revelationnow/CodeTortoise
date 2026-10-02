# CodeTortoise

Deep, layered code review for C/C++ Perforce changelists. CodeTortoise turns one or more CLs into a **review board**:
a lensed map of the call graph, by architectural layer or by call depth, with numbered **flows** that trace
*entry → change → where the side effect lands*. The board covers contract changes (new return values a caller
ignores), state changes (fields written through local pointer/reference aliases and who reads them) and signature
changes. Changed functions open as diffs with inline annotations and comment threads. Any other function's code is
fetched on demand from your workspace. An OpenAI-compatible LLM (your endpoint, your key) can rewrite the narratives,
and every claim it makes must cite analysis facts.

The web app is the system of record for review discussion. P4 Swarm is a side channel: CodeTortoise reads review state,
can create a Swarm review for a shelved CL and posts a summary link.

- [Quick start (no Perforce needed)](#quick-start-bundled-fixture-no-perforce-needed)
- [Connecting to an existing Perforce server](#connecting-to-an-existing-perforce-server)
- [Enterprise environments](#enterprise-environments)
- [Running it as a service](#running-it-as-a-service)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Quick start (bundled fixture, no Perforce needed)

```bash
cd backend && uv sync && cd ..
cd frontend && npm install && npm run build && cd ..
uv run --project backend codetortoise fixture-demo --dir /tmp/tortoise-demo
uv run --project backend codetortoise serve --config /tmp/tortoise-demo/tortoise.yaml
# open http://127.0.0.1:8765, sign in as "demo", and review CLs "101 102" from the landing page
```

Headless run, which prints the findings: `uv run --project backend codetortoise review --config /tmp/tortoise-demo/tortoise.yaml 101 102`

## Connecting to an existing Perforce server

CodeTortoise never changes your depot or workspace. It reads changelists (shelved or submitted) and the files around
them from one **base workspace**: an existing client that is synced to the code the changes are based on. Every
Perforce call goes through a read-only allowlist: `describe`, `print`, `where`, `have`, `client -o`, `info`,
`changes`, `fstat`, `files`, plus `login -p` to check sign-ins.

### 1. Prerequisites

| What | Notes |
|---|---|
| Linux host near the Perforce server | Python ≥ 3.12 with [uv](https://docs.astral.sh/uv/), Node 20.19+ or 22.12+ to build the UI, and the `p4` command-line client on `PATH` (or set `workspace.p4_bin`). |
| A Perforce user for the **owner** | The owner is the person who runs the server and creates reviews. Their `read` access defines everything the app can show (see [Access and protections](#access-and-protections)). |
| A synced **base workspace** on this host | A normal client whose `Root` is on local disk. Sync it to the revisions your changes are based on, typically the head of the branch under review. CodeTortoise compares each CL's base revision with the workspace's have revision and warns about drift. |
| `compile_commands.json` for that workspace | It tells libclang how each file is compiled. See [Compile database](#compile-database). |
| Optional: Swarm URL, LLM endpoint | Neither is required; both degrade gracefully. |

### 2. Prepare the environment the server runs in

CodeTortoise passes `-p <p4port> -c <client>` to every command and takes everything else from the normal Perforce
environment of the user running the server. Set it up once, as that OS user:

```bash
export P4PORT=ssl:perforce.example.com:1666   # the same value goes in tortoise.yaml
export P4USER=anoop                           # the owner
export P4CLIENT=anoop-main-ws
export P4TICKETS=$HOME/.p4tickets             # or a dedicated file for the service
export P4CHARSET=utf8                         # only on Unicode-mode servers
p4 trust -y                                   # once, for ssl: ports
p4 login -a                                   # a ticket valid from any host
p4 client -o | grep -E '^(Root|AltRoots)'     # must match workspace.root below
```

### 3. Configure

`tortoise.yaml` (relative paths are resolved against the config file's directory):

```yaml
owner: anoop                        # P4 user who creates reviews; everyone else views and comments
server:
  host: 0.0.0.0                     # 127.0.0.1 to keep it local
  port: 8765
  public_url: "https://codetortoise.example.com"   # what shared links and Swarm summaries point to
  data_dir: /var/lib/codetortoise   # SQLite database, symbol index, toolchain cache
  # tls_cert: /etc/codetortoise/ct.pem   # both set: serve HTTPS directly (plain HTTP on a network address
  # tls_key: /etc/codetortoise/ct.key    #   is allowed but warned about at startup and in a banner)
workspace:
  vcs: p4
  p4port: ssl:perforce.example.com:1666
  client: anoop-main-ws
  root: /work/main                  # must equal the client's Root (or one of its AltRoots); symlinks are fine
  compile_commands: /work/main/build/compile_commands.json
  # p4_bin: /opt/perforce/bin/p4
toolchain:
  clang: /opt/vendor/bin/clang      # your compiler driver, queried for implicit include paths and macros
  libclang: /opt/vendor/lib/libclang.so   # optional; the bundled libclang 18 is used otherwise
  strip_flags: []                   # vendor flags libclang must ignore (unknown ones are learned automatically)
swarm:
  url: "https://swarm.example.com"  # optional
llm:                                # optional; without it, narratives use built-in templates
  base_url: "https://llm.example.com/v1"
  model: "your-model"
  api_key_env: TORTOISE_LLM_KEY     # name of the environment variable holding the key
  max_context_tokens: 64000
  concurrency: 4                    # parallel LLM calls
auth:
  mode: p4                          # sign in with Perforce credentials ("dev" accepts any name: demos only)
analysis:
  tu_budget: 200                    # max translation units parsed per review (callers of changed code first)
  workers: 4                        # parallel libclang processes
  entrypoint_patterns: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"]
```

### 4. Index, check, run

```bash
cd frontend && npm ci && npm run build && cd ..                          # once per upgrade
export TORTOISE_LLM_KEY=...                                              # never stored or logged
uv run --project backend codetortoise index --config tortoise.yaml       # repo-wide symbol index (tree-sitter)
uv run --project backend codetortoise review --config tortoise.yaml 12345   # optional headless smoke test
uv run --project backend codetortoise serve --config tortoise.yaml
```

Open the **Health** page as the owner. Reviews can only be created when the hard checks pass: workspace root,
`p4 client` (Root matches), `compile_commands`, and libclang. The LLM endpoint, the driver query and Swarm are warnings
only. After a restart, the owner signs in once in the browser; that sign-in also gives CodeTortoise the owner's Swarm
access (the ticket is kept in memory only).

Colleagues open the shared link and sign in with their own Perforce credentials. The app checks them with
`p4 login -p` and then discards the ticket; passwords are never stored. Only the owner can start reviews.

### Compile database

libclang needs the exact compile command of each file. Typical ways to get `compile_commands.json`:

| Build system | How |
|---|---|
| CMake | `cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON …` |
| Ninja | `ninja -t compdb > compile_commands.json` |
| Make or anything else | [Bear](https://github.com/rizsotto/Bear): `bear -- make -j` |
| Vendor IDEs | most can export it; otherwise wrap the build with Bear |

Keep it in or under the workspace and regenerate it when the build changes. A changed file missing from it is still
parsed, with flags borrowed from the nearest entry. With a vendor cross-compiler, point `toolchain.clang`
at the vendor driver, so its built-in include paths and macros are used. Flags libclang does not understand are
stripped and remembered per workspace; the Health page lists them.

## Enterprise environments

### Access and protections

- Everything shown is read **as the owner**. The owner's ticket must have `read` (not just `list`) on every depot path
  the changelists touch and on the workspace's view. Without it, files appear as warnings and context code can't be
  fetched.
- **Viewers see what the owner's workspace can see.** Anyone who can sign in can open any review and fetch any
  synced file in the base workspace. Their own Perforce protections are not applied to what they read. If you host
  code that is restricted to a subset of users, run a separate instance per audience, with a workspace whose view
  contains only what that audience may read.
- Only paths that map into the base workspace are served. Wildcards, revision specifiers and paths outside the client
  view are refused (HTTP 403), binary files are refused (415), and files over 2 MiB are refused (413).
- Restricted changelists can be reviewed only if the owner can `describe` them.

### Tickets and session timeouts

Perforce tickets expire. The default group timeout is 12 hours, and a server with an expired ticket fails every review
with *"Your session has expired, please login again."* Options, best first:

1. Ask your Perforce admins to put the owner (or a dedicated read-only service user that acts as the owner) in a group
   with a longer `Timeout`, for example a week, or a `PasswordTimeout` policy you agree on.
2. Renew from cron with a ticket the service can use from any host: `p4 login -a < /path/to/secret` (keep the secret
   readable only by the service user).
3. Re-run `p4 login -a` by hand after the Health page shows the `p4 client` check failing.

Use `p4 login -a` (all hosts), not a host-locked ticket. The owner's ticket is also presented to Swarm, which runs on
another host.

### SSL, Unicode and network topology

- **SSL ports** (`ssl:host:1666`): run `p4 trust -y` once as the service user. Re-run it when the server's certificate
  changes, otherwise every call fails with a fingerprint mismatch.
- **Unicode-mode servers**: set `P4CHARSET=utf8` (or your server's charset) in the service environment. File contents
  are decoded as UTF-8, and undecodable bytes become replacement characters without shifting line numbers.
- **Proxies (`p4p`)**: fine. `p4 print` benefits from the cache. Point `p4port` at the proxy.
- **Edge and commit servers**: point `p4port` at the server where the changes live. Shelves created on an edge server
  are local to that edge unless they are promoted (`p4 shelve -p`, or `dm.shelve.promote=1` on the edge). Either run
  CodeTortoise against the same edge your developers shelve on, or ask them to promote shelves meant for review.
  Submitted changelists work from any server that has them.
- **Brokers (`p4broker`)**: the broker must allow the read-only commands listed above plus `login -p`.
- **Large servers**: CodeTortoise runs a handful of commands per review (`describe`, one `where`, one `print` per
  changed file revision, `fstat`/`print` for context files on demand). It never runs `sync`, `opened` or wide
  `files //...` queries.

### Scale and performance

- `codetortoise index` scans the workspace with tree-sitter: roughly 1,000 files in a few seconds. Re-run it after
  large syncs (the Health page has a Rebuild button).
- A review parses only the translation units it needs: the changed files, their callers up to `analysis.caller_hops`,
  and a sample for header fan-out. This is capped by `tu_budget` and parsed by `workers` processes. For a 5,000-TU
  codebase, start with the defaults and raise `workers` to your core count.
- libclang runs out of process with crash isolation. A file that crashes the parser falls back to tree-sitter facts,
  is marked "degraded", and does not stop the review.

### LLM and data egress

With `llm` configured, snippets of changed functions and their callers, plus the analysis findings, are sent to that
endpoint. Use an on-prem or contractually approved endpoint (any OpenAI-compatible server: vLLM, LM Studio, Azure
OpenAI, …). Leave `llm` out to keep everything on the host. Reviews then use deterministic text and still show every
flow and annotation.

LLM text follows a house style: the Microsoft Writing Style Guide (you, active voice, short sentences, plain words) and
one Diátaxis mode per output (narratives and explanations are explanation, verification steps are a how-to, flow
titles are headlines; facts and evidence stay deterministic reference). Text that breaks a checkable rule is dropped in
favour of the deterministic text, and the LLM stage says how many outputs were dropped (`backend/codetortoise/llm/style.py`).

### Swarm

Set `swarm.url`. When the owner signs in, CodeTortoise can read the Swarm review attached to each CL, create a Swarm
review for a shelved CL, and post a summary comment with a link back to the board. Posting is idempotent unless the
owner confirms a repeat. Swarm is never required: if it is down or the owner hasn't signed in, reviews still run.

## Running it as a service

Run it as a dedicated OS user that owns the workspace, the tickets file and `data_dir`. A systemd unit, for example:

```ini
# /etc/systemd/system/codetortoise.service
[Unit]
Description=CodeTortoise review server
After=network-online.target

[Service]
User=codetortoise
WorkingDirectory=/opt/codetortoise
EnvironmentFile=/etc/codetortoise/env     # P4PORT, P4USER, P4CLIENT, P4TICKETS, P4CHARSET, TORTOISE_LLM_KEY
ExecStart=/usr/local/bin/uv run --project /opt/codetortoise/backend codetortoise serve --config /etc/codetortoise/tortoise.yaml
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

The app speaks plain HTTP unless `server.tls_cert` and `server.tls_key` are set. On a network address over plain HTTP
it prints a warning at startup and every page shows a "Not encrypted" banner. Beyond a trusted LAN or VPN, set the
certificate or put it behind a TLS-terminating reverse proxy (nginx, Caddy, your ingress), and set `server.public_url`
to the HTTPS address. Proxy `/api/reviews/*/events` without buffering
(server-sent events), for example `proxy_buffering off;` in nginx. Sessions are HTTP-only cookies. There is no built-in
sign-in rate limit; Perforce's own login policies apply.

Back up `data_dir` (`tortoise.db` holds reviews and comments). To upgrade: pull, `uv sync`, `npm ci && npm run build`,
restart. Reviews keep working across upgrades, and re-running a review rebuilds its board with the new analysis.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ingest failed: … Your session has expired, please login again` | The service user's ticket expired. Run `p4 login -a` and see [Tickets and session timeouts](#tickets-and-session-timeouts). |
| Health: `p4 client` fails with `Root=…` | `workspace.root` is not the client's `Root` or an `AltRoots` entry. Fix the config or the client spec. |
| `The authenticity of '…' can't be established` / fingerprint mismatch | Run `p4 trust -y` (again) as the service user. |
| `Unicode server permits only unicode enabled clients` | Set `P4CHARSET` in the service environment. |
| `CL … is pending with no shelved files` | The CL isn't shelved, or it was shelved on another edge server. See [SSL, Unicode and network topology](#ssl-unicode-and-network-topology). |
| Files listed as warnings ("content unavailable", "not in client view") | The owner lacks `read` on those paths, or the client view doesn't map them. |
| `facts` stage degraded, "fell back to tree-sitter" | Unknown vendor flags or missing includes. Check the Health page's stripped flags, add `toolchain.strip_flags`, and make sure `toolchain.clang` points at the vendor driver. |
| Board warns about workspace drift | The workspace isn't at the CL's base revision. Sync it, or expect context code to differ from what was analysed. |
| `llm` stage degraded | The endpoint is unreachable or rejected the request. Reviews are complete without it. Check `llm.base_url` and the key variable. |
| Swarm actions missing | The owner hasn't signed in since the server started, or `swarm.url` is wrong. |

## Development

```bash
cd backend && uv run pytest && uv run ruff check codetortoise tests
cd frontend && npm test && npx tsc --noEmit && npm run build && npm run e2e
```

A local Perforce + Swarm + libgit2 lab for end-to-end checks lives in `lab/` (see `lab/README.md`).
Design: `docs/superpowers/specs/2026-09-29-codetortoise-design.md` (M1) and
`docs/superpowers/specs/2026-10-01-review-board-design.md` (review board, themes, landing page).
