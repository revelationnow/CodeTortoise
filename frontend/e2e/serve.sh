#!/usr/bin/env bash
# Starts CodeTortoise on the bundled fixture for end-to-end tests.
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8799 >/dev/null
exec $CMD serve --config "$DIR/tortoise.yaml"
