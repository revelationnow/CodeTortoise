# CodeTortoise

Deep, layered code review for C/C++ Perforce changelists. CodeTortoise turns one or more CLs into a **review board**:
a lensed map of the call graph, by architectural layer or by call depth, with numbered **flows** that trace
*entry → change → where the side effect lands*. The board covers contract changes (new return values a caller
ignores), state changes (fields written through local pointer/reference aliases and who reads them) and signature
changes. Changed functions open as diffs with inline annotations and comment threads. Any other function's code is
fetched on demand from your workspace. An LLM (your endpoint, your key) can rewrite the narratives,
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

CodeTortoise runs `p4` from the workspace root, as the OS user who runs the server, so it sees the same Perforce
settings you see in a terminal there: a P4CONFIG file, environment variables, `p4 set` values and the tickets file.
Set it up once, as that user.

The simplest setup is a P4CONFIG file at the workspace root, which many teams already use:

```bash
export P4CONFIG=.p4config                     # in that user's shell profile
cat > /work/main/.p4config <<'EOF'
P4PORT=ssl:perforce.example.com:1666
P4CLIENT=anoop-main-ws
P4USER=anoop
P4CHARSET=utf8
EOF
```

Then, from inside the workspace:

```bash
cd /work/main
p4 set                                        # shows each value and where it comes from
p4 trust -y                                   # once, for ssl: ports
p4 login -a                                   # a ticket valid from any host
p4 info                                       # User name, Client name and Server address must be right
p4 client -o | grep -E '^(Root|AltRoots)'     # the workspace root you put in tortoise.yaml
```

Plain environment variables (`P4PORT`, `P4CLIENT`, `P4USER`) work too. Values in `tortoise.yaml` win over a P4CONFIG
file, and a P4CONFIG file wins over the environment, as in `p4` itself. Only `P4CHARSET` is needed for Unicode-mode
servers, and `P4TICKETS` only if the service keeps its ticket in a dedicated file.

### 3. Write tortoise.yaml

`tortoise.yaml` tells CodeTortoise who owns it, which workspace to read, how your code is compiled and how to serve
the app. Relative paths are resolved against the folder that holds the file.

#### Start with `codetortoise init`

Run it from anywhere inside the workspace:

```bash
cd /work/main/src
uv run --project /path/to/CodeTortoise/backend codetortoise init --out ~/codetortoise/tortoise.yaml
```

It writes a commented starter file and prints what it found:

- **owner, server address and client:** read the way `p4` reads them. Values from a P4CONFIG file are left to that
  file, so the two stay in sync.
- **Workspace root:** the client's `Root`, from `p4 client -o` (read-only).
- **Compile database:** `compile_commands.json` under the workspace, or in a `build*`/`out*` folder beside it. If it
  finds several, it lists them all.
- **Compiler:** the compiler that the first compile command uses.
- **Server:** this machine only (`127.0.0.1:8765`). Swarm and AI settings stay commented out.

Read every line marked `check:`. If your ticket has expired, `init` can't read the client's Root and tells you to run
`p4 login -a` first. It never overwrites a file unless you pass `--force`.

#### Fill it in step by step

Whether you start from `init` or from scratch, check these values in order.

1. **`owner`: who runs reviews.** Your Perforce user name, from `p4 info` (User name). The owner starts reviews and
   their Perforce access decides what the app can show. Leave it out to use `P4USER`.
2. **`workspace.p4port` and `workspace.client`: which server and workspace.** From `p4 info` (Server address and
   Client name). Leave them out to use your P4CONFIG file or environment.
3. **`workspace.root`: where the workspace is on disk.** It must equal the client's `Root`, or one of its `AltRoots`:
   `p4 client -o | grep -E '^(Root|AltRoots)'`. Symbolic links to it are fine.
4. **`workspace.compile_commands`: how each file is compiled.** The path to `compile_commands.json` for the build you
   review. To create one, see [Compile database](#compile-database).
5. **`toolchain`: usually nothing.** Each file's own compiler, from the compile database, is asked for its built-in
   include paths and macros, and the target comes from the compiler. Set `toolchain.clang` only if that compiler
   isn't installed on this machine, and see [Toolchains and libclang](#toolchains-and-libclang) for mixed targets
   and vendor toolchains. Check one file with `codetortoise check-parse`.
6. **`server`: how people reach the app.** `host: 127.0.0.1` keeps it on this machine. To share it, use `0.0.0.0`,
   set `public_url` to the address colleagues open, and set `tls_cert` and `tls_key` so sign-ins aren't sent in plain
   text. `data_dir` holds the database and caches; back it up.
7. **Optional: `swarm.url` and `llm`.** Add Swarm to read and post Swarm reviews. Add an `llm`
   endpoint for AI-written narratives; code is sent to it (see [LLM and data egress](#llm-and-data-egress)).

#### Minimal example

With a P4CONFIG file in the workspace, this is a complete configuration:

```yaml
workspace:
  root: /work/main
  compile_commands: /work/main/build/compile_commands.json
```

#### Every setting

```yaml
owner: anoop                        # optional with P4CONFIG or P4USER; the P4 user who creates reviews
server:
  host: 0.0.0.0                     # 127.0.0.1 to keep it local
  port: 8765
  public_url: "https://codetortoise.example.com"   # what shared links and Swarm summaries point to
  data_dir: /var/lib/codetortoise   # SQLite database, symbol index, toolchain cache
  # tls_cert: /etc/codetortoise/ct.pem   # both set: serve HTTPS directly (plain HTTP on a network address
  # tls_key: /etc/codetortoise/ct.key    #   is allowed but warned about at startup and in a banner)
workspace:
  vcs: p4
  p4port: ssl:perforce.example.com:1666   # optional with P4CONFIG or P4PORT
  client: anoop-main-ws             # optional with P4CONFIG or P4CLIENT
  root: /work/main                  # must equal the client's Root (or one of its AltRoots); symlinks are fine
  compile_commands: /work/main/build/compile_commands.json
  # p4_bin: /opt/perforce/bin/p4
toolchain:
  # clang: /opt/vendor/bin/clang    # optional: query this compiler for every file (default: each file's own compiler)
  # target: armv7m-none-eabi        # optional: for files whose command names none (default: from the compiler)
  # libclang: /opt/vendor/lib/libclang.so   # optional: default is found (see Toolchains and libclang)
  search_paths: [/opt/tools]        # optional: folders to search for a newer libclang
  query_compilers: outside_workspace   # run compilers named in compile databases to learn their includes and
                                    #   macros, except ones inside the workspace; "all" or "off"
  strip_flags: []                   # vendor flags libclang must ignore (unknown ones are learned automatically)
  overrides:                        # optional, first match wins
    - match: "dsp/**"               # workspace-relative glob
      compile_commands: /work/main/build/dsp/compile_commands.json
      clang: /opt/hexagon/bin/hexagon-clang
      target: hexagon
      libclang: /opt/hexagon/lib/libclang.so
swarm:
  url: "https://swarm.example.com"  # optional
llm:                                # optional; without it, narratives use built-in templates
  base_url: "https://llm.example.com/v1"
  model: "your-model"
  api: chat                         # chat (OpenAI-compatible /chat/completions), responses (OpenAI Responses API)
                                    #   or messages (Anthropic Messages API, e.g. base_url https://api.anthropic.com/v1)
  # max_output_tokens: 8192         # reply token limit; messages needs one (8192 when unset), others send it only if set
  # max_output_tokens_cap: 32768    # a reply cut off by its limit is sent again at double the limit, up to this
  # request_log: all                # HTTP requests kept for debugging: all, failed (a failed, cut-off or repaired call's) or off
  # request_log_days: 14            # read them with `codetortoise llm-log` or the AI usage view's download link
  api_key_env: TORTOISE_LLM_KEY     # name of the environment variable holding the key
  max_context_tokens: 64000
  concurrency: 4                    # parallel LLM calls
  upfront_flows: 3                  # flow narratives written when a review runs; the rest on demand (✦ Explain)
  upfront_side_effects: 36          # new field writes the AI judges when a review runs (12 a call); red only if a hazard
  budget:                           # AI calls (failed calls count; refused ones cost nothing)
    per_review: 200                 # per review, everyone and the pipeline together; the owner can raise it
    per_person_daily: 100           # calls one person can trigger per day (UTC), across reviews
    per_mention: 10                 # rounds one @tortoise answer may take (the answer is 1 call); owners change it per review
auth:
  mode: p4                          # sign in with Perforce credentials ("dev" accepts any name: demos only)
analysis:
  tu_budget: 200                    # max translation units parsed per review (callers of changed code first)
  index_scope: compile_db           # symbol index: compile_commands.json files and the headers they include
                                    #   ("workspace" indexes every C/C++ file under root)
  workers: 4                        # parallel libclang processes
  entrypoint_patterns: ["main", "*_isr", "*_irq_handler", "*Callback", "*_callback"]
```

### 4. Index, check, run

```bash
cd frontend && npm ci && npm run build && cd ..                          # once per upgrade
export TORTOISE_LLM_KEY=...                                              # never stored or logged
uv run --project backend codetortoise index --config tortoise.yaml       # symbol index (tree-sitter); --full to redo it all
uv run --project backend codetortoise review --config tortoise.yaml 12345   # optional headless smoke test
uv run --project backend codetortoise serve --config tortoise.yaml
```

Open the **Health** page as the owner. Reviews can only be created when the hard checks pass: workspace root,
`p4 client` (Root matches), `compile_commands`, and libclang. The LLM endpoint, the driver query and Swarm are warnings
only. After a restart, the owner signs in once in the browser; that sign-in also gives CodeTortoise the owner's Swarm
access (the ticket is kept in memory only).

Colleagues open the shared link and sign in with their own Perforce credentials. The app checks them with
`p4 login -p` and then discards the ticket; passwords are never stored. Only the owner can start reviews.

The symbol index finds callers and includers outside the files under review. By default it covers the files in
`compile_commands.json` and the workspace headers they include, so a large workspace with a small build stays small.
Later runs of `codetortoise index` (and the Health page's "Rebuild index") only parse files whose size or
modification time changed; `--full` parses everything again. Results are written as they're parsed, so memory stays
flat however large the workspace is.

### Compile database

libclang needs the exact compile command of each file. Typical ways to get `compile_commands.json`:

| Build system | How |
|---|---|
| CMake | `cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON …` |
| Ninja | `ninja -t compdb > compile_commands.json` |
| Make or anything else | [Bear](https://github.com/rizsotto/Bear): `bear -- make -j` |
| Vendor IDEs | most can export it; otherwise wrap the build with Bear |

Regenerate it when the build changes. A changed file missing from it is still parsed, with flags borrowed from the
nearest file of the same database.

**Several databases.** `workspace.compile_commands` takes one path, a list of paths or globs, or `auto`:

```yaml
workspace:
  compile_commands: auto            # every compile_commands.json under build_root
  build_root: /work/main/build      # default: the folder of the first database `codetortoise init` finds
```

A file listed in several databases uses the first one in your list, or with `auto` the deepest (a nested build is
usually the specialised build of that component). To choose for some paths, use `toolchain.overrides` with
`compile_commands`. The Health page lists every database and how many files appear in more than one.

**What CodeTortoise understands in a command.** Compiler wrappers (`ccache`, `sccache`, `distcc`, `icecc`,
`buildcache`, an `env VAR=x` prefix) are skipped; `@file` response files are expanded; relative paths resolve from
the entry's `directory`; MSVC commands (`cl`, `clang-cl`) use clang's `cl` mode. Flags libclang doesn't understand
are stripped and remembered per workspace; the Health page lists them.

### Toolchains and libclang

Each file is parsed for its own toolchain. CodeTortoise asks the file's compiler (or `toolchain.clang`, or an
override's `clang`) for its built-in include paths and macros, once per group of files that share a compiler, target
and target flags. The target comes from the command (`--target`), an override, `toolchain.target`, the compiler's
name (`arm-none-eabi-gcc` means `arm-none-eabi`), or the compiler's `-dumpmachine`. The Health page lists each group,
parses one sample file of it (once per server start), and shows the first error if that fails.

Querying runs the compiler program. CodeTortoise doesn't run compilers that live inside the workspace, since a compile
database or toolchain synced from the depot could name any program there; if your toolchain is checked in, set
`toolchain.query_compilers: all`. `off` never runs a compiler (files then parse without the toolchain's built-in
include paths and macros). Server startup runs no compiler; the Health page and reviews do.

libclang only parses, so one upstream library handles every standard target (ARM, AArch64, RISC-V, x86, MIPS,
PowerPC). A newer library knows more recent flags. The library for a group is, in order: an override's or
`toolchain.libclang`; the one next to a clang compiler (that toolchain's own, for vendor forks); the newest under
`toolchain.search_paths`; one installed with `codetortoise fetch-libclang`; the newest system LLVM
(`/usr/lib/llvm-*`); the one bundled with CodeTortoise (18.1.1). Groups that need different libraries parse in
separate worker processes.

```bash
uv run --project backend codetortoise fetch-libclang --config tortoise.yaml       # LLVM 23.1.2, ~2 GB streamed, ~230 MB kept
uv run --project backend codetortoise fetch-libclang --config tortoise.yaml \
    --from LLVM-23.1.2-Linux-X64.tar.xz                                          # offline: a copied release archive
uv run --project backend codetortoise check-parse --config tortoise.yaml src/drivers/uart.c
```

`fetch-libclang` checks the archive's SHA-256 against the digest GitHub publishes (or a pinned one, or `--sha256`).
`check-parse` shows how one file is parsed: the compile entry and database used, the compiler, target and library,
the exact arguments, the result and the first errors. Run it on the server when a review's `facts` stage says files
fell back to tree-sitter; the stage message names the most common problem.

Compilers that are neither GCC- nor clang-compatible (IAR, TI `cl6x`, Green Hills, Tasking) aren't supported yet.

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
endpoint. Use an on-prem or contractually approved endpoint: any OpenAI-compatible server (vLLM, LM Studio, Azure
OpenAI, …) with `api: chat`, the OpenAI Responses API with `api: responses`, or the Anthropic Messages API with
`api: messages`. `llm.strong` takes the same `api` and `max_output_tokens` keys. Leave `llm` out to keep everything on the host. Reviews then use deterministic text and still show every
flow and annotation.

LLM text follows a house style: the Microsoft Writing Style Guide (you, active voice, short sentences, plain words) and
one Diátaxis mode per output (narratives and explanations are explanation, verification steps are a how-to, flow
titles are headlines; facts and evidence stay deterministic reference). Text that breaks a checkable rule is dropped in
favour of the deterministic text, and the LLM stage says how many outputs were dropped (`backend/codetortoise/llm/style.py`).

### AI calls on a budget

A function that newly writes a field other code uses is a *side effect*: normal, and shown neutral. When a review runs
the AI judges up to `upfront_side_effects` of them and marks one red only when the code shows a clear hazard or breaks
an assumption other code makes, with its reason; **✦ Explain** on a side effect judges it too. Without an AI they stay
neutral, marked "not yet assessed".

When a review runs, the AI writes only the change summary and the first `upfront_flows` flow narratives. Everything
else is written when someone asks, once, and shown to everyone: **✦ Explain** on a flow or a finding, **✦ Summarise**
on a changed file. Type `@tortoise` in any comment (the `@` menu offers it) to ask the AI about that thread; it reads the
functions, callers, declarations and files it needs from this review and the workspace, in up to `per_mention` rounds,
and answers in the thread with what it read. The whole answer counts as one AI call; the owner can change the rounds
per review in the AI usage panel.

Every call is recorded and checked against `llm.budget` before it is made. The **AI 57/200** pill in the review
header shows the review's usage (by person, by purpose, every call); the owner raises the review's budget there. The
Health page shows the limits and today's total.

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
| `config error: owner is not set` (or `workspace.p4port`, `workspace.client`) | The value isn't in `tortoise.yaml`, the P4CONFIG file or the environment. The message says where it looked. Run `p4 set` in the workspace as the service user, or put the value in `tortoise.yaml`. |
| Health shows the wrong server or client | A P4CONFIG file or environment variable you didn't expect is in effect. The Health page lists where each value came from; `p4 set` in the workspace shows the same. |
| `ingest failed: … Your session has expired, please login again` | The service user's ticket expired. Run `p4 login -a` and see [Tickets and session timeouts](#tickets-and-session-timeouts). |
| Health: `p4 client` fails with `Root=…` | `workspace.root` is not the client's `Root` or an `AltRoots` entry. Fix the config or the client spec. |
| `The authenticity of '…' can't be established` / fingerprint mismatch | Run `p4 trust -y` (again) as the service user. |
| `Unicode server permits only unicode enabled clients` | Set `P4CHARSET` in the service environment. |
| `CL … is pending with no shelved files` | The CL isn't shelved, or it was shelved on another edge server. See [SSL, Unicode and network topology](#ssl-unicode-and-network-topology). |
| Files listed as warnings ("content unavailable", "not in client view") | The owner lacks `read` on those paths, or the client view doesn't map them. |
| `facts` stage degraded, "fell back to tree-sitter" | Run `codetortoise check-parse` on one of the files: it shows the compile entry, compiler, target, library and first errors. Common causes: the build's compiler isn't on this machine (set `toolchain.clang`), a missing generated header, a target libclang doesn't know (set `toolchain.target`, or a vendor `libclang`). See [Toolchains and libclang](#toolchains-and-libclang). |
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
