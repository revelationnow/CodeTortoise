#!/usr/bin/env bash
# Starts a CodeTortoise whose stories come from a strong model (spec 2026-10-05-two-tier-stories): the fake model of
# fake_llm.py serves both tiers, and the fixture is split into two build targets, hal and fw.
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8795 >/dev/null
cat >> "$DIR/tortoise.yaml" <<YAML
llm:
  base_url: http://127.0.0.1:8797/v1
  model: fake
  upfront_flows: 0
  upfront_stories: 0
  upfront_findings: 0
  strong:
    base_url: http://127.0.0.1:8797/v1
    model: fake-strong
    max_output_tokens: 1000
targets:
  - { match: "hal/*", name: hal }
  - { match: "*.c", name: fw }
YAML
export TORTOISE_LLM_KEY=fake TORTOISE_STRONG_KEY=fake
exec $CMD serve --config "$DIR/tortoise.yaml"
