#!/usr/bin/env bash
# Configures and builds the imported libgit2 so compile_commands.json and generated headers exist.
set -euo pipefail
LAB=${LAB:?set LAB}
cmake -S "$LAB/ws" -B "$LAB/build" -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=Debug \
  -DUSE_SSH=OFF -DUSE_HTTPS=OFF -DUSE_AUTH_NTLM=OFF -DUSE_AUTH_NEGOTIATE=OFF -DBUILD_TESTS=ON \
  -DREGEX_BACKEND=builtin -DUSE_BUNDLED_ZLIB=ON > "$LAB/build-config.log"
cmake --build "$LAB/build" -j "$(nproc)" > "$LAB/build.log"
python3 -c "import json;print(len(json.load(open('$LAB/build/compile_commands.json'))),'TUs in compile_commands.json')"
