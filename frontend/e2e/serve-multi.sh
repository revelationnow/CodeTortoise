#!/usr/bin/env bash
# Starts one CodeTortoise for two workspaces (spec 2026-10-31 §13): the bundled fixture as the seed (`ws`, on `local`), and
# a second copy of it at $DIR/second/ws, which e2e/multi-workspace.spec.ts adds on the Workspaces page as `second`,
# labelled with a second Perforce server (second:1666). Only the seed is in tortoise.yaml.
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8793 >/dev/null
$CMD fixture-demo --dir "$DIR/second" --port 8793 >/dev/null      # its own tortoise.yaml goes unused
exec $CMD serve --config "$DIR/tortoise.yaml"
