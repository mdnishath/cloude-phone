#!/usr/bin/env bash
# Assert that a named sidecar reaches healthy state within 30s.
set -euo pipefail

NAME="${1:?usage: $0 <sidecar-container-name>}"

echo "Waiting for $NAME to become healthy..."
for i in $(seq 1 30); do
  status=$(docker inspect --format '{{.State.Health.Status}}' "$NAME" 2>/dev/null || echo "missing")
  if [[ "$status" == "healthy" ]]; then
    echo "OK: $NAME healthy in ${i}s"
    exit 0
  fi
  sleep 1
done

echo "FAIL: $NAME did not become healthy (last status: $status)"
echo "--- last 50 lines of container log ---"
docker logs --tail=50 "$NAME" 2>&1 || true
exit 1
