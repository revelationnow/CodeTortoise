#!/usr/bin/env bash
# Starts a CodeTortoise on the bundled fixture whose tortoise.yaml lists Stats::* as shared sinks (spec 2026-10-09 §7).
# Its own data dir: the owner's marks made here never reach the other servers' reviews.
set -euo pipefail
DIR=$(mktemp -d)
CMD=${TORTOISE_CMD:-"uv run --project ../backend codetortoise"}
$CMD fixture-demo --dir "$DIR" --port 8794 >/dev/null
sed -i 's/^  workers: 1$/  workers: 1\n  sink_fields:\n  - "Stats::*"/' "$DIR/tortoise.yaml"
grep -q 'Stats::\*' "$DIR/tortoise.yaml"
exec $CMD serve --config "$DIR/tortoise.yaml"
