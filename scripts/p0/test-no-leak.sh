#!/usr/bin/env bash
# Pause redsocks inside the sidecar, verify a joined container cannot reach
# the internet, then resume redsocks. This proves the fail-closed posture:
# if the proxy daemon dies, no traffic escapes.
#
# Usage: test-no-leak.sh [sidecar-name]
set -euo pipefail

SIDECAR="${1:-p0-sidecar}"

echo "Pausing redsocks inside $SIDECAR (iptables + DROP policy should prevent egress)..."
docker exec "$SIDECAR" sh -c 'pkill -STOP redsocks || true'

echo "Attempting egress from a joined container (expected: TIMEOUT)..."
set +e
OUT=$(docker run --rm \
  --network="container:${SIDECAR}" \
  --dns 127.0.0.1 \
  alpine:3.20 \
  sh -c 'apk add --no-cache curl >/dev/null 2>&1 && curl -fsS --max-time 8 https://ifconfig.me' 2>&1)
RC=$?
set -e

echo "Resuming redsocks..."
docker exec "$SIDECAR" sh -c 'pkill -CONT redsocks || true'

if [[ $RC -eq 0 ]]; then
  echo "FAIL: egress succeeded despite stopped redsocks - LEAK"
  echo "Output: $OUT"
  exit 1
fi

echo "OK: no leak detected (curl exit code $RC, expected non-zero)"
