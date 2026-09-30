#!/usr/bin/env bash
# Local Perforce + Swarm lab for exercising CodeTortoise on a real, medium-sized C codebase (libgit2).
# Requires: docker (rootless is fine), git, cmake, ninja, gcc, curl. Runs p4d in a container so that
# Swarm (also a container) can reach it without exposing p4d beyond localhost.
set -euo pipefail
LAB=${LAB:?set LAB to a working directory, e.g. export LAB=\$HOME/tortoise-lab}
PASS=${OWNER_PASSWD:-TortoiseLab-2026}
REL=${P4_RELEASE:-r26.1}   # newer releases no longer ship raw p4/p4d binaries
mkdir -p "$LAB/bin" "$LAB/p4root"
for b in p4 p4d; do
  [ -x "$LAB/bin/$b" ] || curl -sSfL -o "$LAB/bin/$b" "https://ftp.perforce.com/perforce/$REL/bin.linux26x86_64/$b"
  chmod +x "$LAB/bin/$b"
done
docker rm -f lab-p4d >/dev/null 2>&1 || true
docker run -d --name lab-p4d -v "$LAB:$LAB" -p 127.0.0.1:1666:1666 debian:stable-slim \
  "$LAB/bin/p4d" -r "$LAB/p4root" -p 1666 -L "$LAB/p4root/log" -J "$LAB/p4root/journal" >/dev/null
sleep 4
cat > "$LAB/env.sh" <<ENV
export PATH=$LAB/bin:\$PATH P4PORT=127.0.0.1:1666 P4USER=${USER} P4TICKETS=$LAB/p4tickets P4CLIENT=lab-ws LAB=$LAB
CT="uv run --project $(cd "$(dirname "$0")/.." && pwd)/backend codetortoise"
ENV
source "$LAB/env.sh"
if ! echo "$PASS" | p4 login >/dev/null 2>&1; then
  printf '%s\n%s\n' "$PASS" "$PASS" | p4 passwd >/dev/null   # first user becomes super
  echo "$PASS" | p4 login >/dev/null
fi
p4 user -o | p4 user -i -f >/dev/null
for u in bob swarm; do
  printf 'User: %s\nEmail: %s@lab\nFullName: %s\n' "$u" "$u" "$u" | p4 user -i -f >/dev/null
  printf '%s\n%s\n' "${u^}Lab-2026" "${u^}Lab-2026" | p4 passwd "$u" >/dev/null
done
p4 protect -o | grep -q "admin user swarm" || { p4 protect -o; printf '\tadmin user swarm * //...\n'; } | p4 protect -i >/dev/null
[ -d "$LAB/upstream" ] || git clone -q https://github.com/libgit2/libgit2.git "$LAB/upstream"
echo "p4d ready at 127.0.0.1:1666 (owner $USER). Next: lab/import.sh, lab/build.sh, lab/plant.sh, lab/swarm.sh"
