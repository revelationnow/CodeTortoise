#!/usr/bin/env bash
# Configures and builds the imported libgit2 so compile_commands.json and generated headers exist.
set -euo pipefail
LAB=${LAB:?set LAB}
WS=${WS:-$LAB/ws} BUILD=${BUILD:-$LAB/build}      # WS=$LAB/big-ws BUILD=$LAB/big-build for the large-change import
cmake -S "$WS" -B "$BUILD" -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=Debug \
  -DUSE_SSH=OFF -DUSE_HTTPS=OFF -DUSE_AUTH_NTLM=OFF -DUSE_AUTH_NEGOTIATE=OFF -DBUILD_TESTS=ON \
  -DREGEX_BACKEND=builtin -DUSE_BUNDLED_ZLIB=ON > "$BUILD-config.log"
cmake --build "$BUILD" -j "$(nproc)" > "$BUILD.log"
python3 -c "import json;print(len(json.load(open('$BUILD/compile_commands.json'))),'TUs in compile_commands.json')"
