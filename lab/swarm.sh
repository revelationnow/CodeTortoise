#!/usr/bin/env bash
# Starts Redis + Helix Swarm linked to the lab-p4d container; Swarm is published on ${SWARM_BIND:-127.0.0.1}:8081.
# For LAN access (e.g. from a phone): SWARM_BIND=0.0.0.0 SWARM_HOSTNAME=<this machine's LAN IP> lab/swarm.sh
set -euo pipefail
LAB=${LAB:?set LAB}; source "$LAB/env.sh"
PASS=${OWNER_PASSWD:-TortoiseLab-2026}
docker rm -f helix-swarm helix-redis >/dev/null 2>&1 || true
docker run -d --name helix-redis redis:7-alpine redis-server --port 7379 >/dev/null
docker run -d --name helix-swarm --link helix-redis --link lab-p4d -p "${SWARM_BIND:-127.0.0.1}:8081:80" \
  -e P4D_PORT=lab-p4d:1666 -e P4D_SUPER="$P4USER" -e P4D_SUPER_PASSWD="$PASS" \
  -e SWARM_USER=swarm -e SWARM_PASSWD=SwarmLab-2026 -e SWARM_HOST="${SWARM_HOSTNAME:-localhost}" \
  -e SWARM_REDIS=helix-redis -e SWARM_REDIS_PORT=7379 perforce/helix-swarm:2026.3 >/dev/null
until docker logs helix-swarm 2>&1 | grep -q "Swarm setup finished"; do sleep 5; done
# the Swarm server extension calls back to Swarm; "localhost" inside the p4d container is not Swarm
SIP=$(docker inspect helix-swarm --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
p4 extension --configure Perforce::helix-swarm -o \
  | sed "s#Swarm-URL: http://localhost/#Swarm-URL: http://$SIP/#; s#^Owner:\tsuper#Owner:\t$P4USER#" \
  | p4 extension --configure Perforce::helix-swarm -i >/dev/null 2>&1 || true
echo "Swarm ready at http://${SWARM_HOSTNAME:-localhost}:8081"
