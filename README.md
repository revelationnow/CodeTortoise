# CodeTortoise

Deep, layered code review for C/C++ Perforce changelists. CodeTortoise turns one or more CLs into a
**storyboard**: changes grouped by inferred architectural layer, before/after call flows, blast radius
over call *and* field-data coupling (including writes through local pointer/reference aliases), and
findings with cited static-analysis evidence. An OpenAI-compatible LLM (your endpoint, your key) writes
the narrative; every claim it makes must cite analysis facts.

The web app is the system of record for review discussion. P4 Swarm is a side channel: CodeTortoise reads
review state, can create a review for a shelved CL, and posts a summary link.

## Quick start (bundled fixture, no Perforce needed)

```bash
cd backend && uv sync && cd ..
cd frontend && npm install && npm run build && cd ..
uv run --project backend codetortoise fixture-demo --dir /tmp/tortoise-demo
uv run --project backend codetortoise serve --config /tmp/tortoise-demo/tortoise.yaml
# open http://127.0.0.1:8765, log in as "demo", start a review of CLs 101 102
```

Headless: `uv run --project backend codetortoise review --config /tmp/tortoise-demo/tortoise.yaml 101 102`

## Real setup (Perforce)

`tortoise.yaml`:

```yaml
owner: anoop                        # your P4 user; the only one who can create reviews
server: {host: 0.0.0.0, port: 8765, public_url: "http://myhost:8765", data_dir: .tortoise}
workspace:                          # an existing, synced client; never modified
  vcs: p4
  p4port: ssl:p4:1666
  client: anoop-main-ws
  root: /work/main                  # must equal the client's Root
  compile_commands: /work/main/build/compile_commands.json
toolchain:
  clang: /opt/vendor/bin/clang      # vendor driver, queried for implicit includes/macros
  libclang: /opt/vendor/lib/libclang.so   # optional; bundled libclang is used otherwise
  strip_flags: []                   # vendor flags libclang must ignore (unknown ones are auto-stripped)
swarm: {url: "https://swarm.example.com"}
llm: {base_url: "https://llm.example.com/v1", model: "your-model", api_key_env: TORTOISE_LLM_KEY}
auth: {mode: p4}
```

```bash
export TORTOISE_LLM_KEY=...                      # never stored or logged
uv run --project backend codetortoise index --config tortoise.yaml   # first run: repo-wide symbol index
uv run --project backend codetortoise serve --config tortoise.yaml
```

Colleagues open the shared link and sign in with their P4 credentials (`p4 login -p`; passwords and
tickets are not stored). The server is meant for a trusted LAN/VPN; put it behind a TLS reverse proxy if
it leaves one. Code snippets of changed functions and their callers are sent to the configured LLM.

## Development

```bash
cd backend && uv run pytest && uv run ruff check codetortoise tests
cd frontend && npm test && npm run build && npm run e2e
```

Design: `docs/superpowers/specs/2026-09-29-codetortoise-design.md`.
