#!/usr/bin/env bash
# Starts a CodeTortoise on the generated large fixture (CLs 201+202 need an overview and cluster boards).
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --large --dir "$DIR" --port 8796 >/dev/null
exec $CMD serve --config "$DIR/tortoise.yaml"
