#!/usr/bin/env bash
# Starts a second CodeTortoise on the bundled fixture, using the fake model from fake_llm.py (spec 2026-10-03 §8).
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8798 >/dev/null
cat >> "$DIR/tortoise.yaml" <<YAML
llm:
  base_url: http://127.0.0.1:8797/v1
  model: fake
  upfront_flows: 1
  upfront_stories: 0
YAML
export TORTOISE_LLM_KEY=fake
exec $CMD serve --config "$DIR/tortoise.yaml"
