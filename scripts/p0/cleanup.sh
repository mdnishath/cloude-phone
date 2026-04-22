#!/usr/bin/env bash
# Remove the P0 pair + its data volume. Idempotent.
set -euo pipefail

docker rm -f p0-redroid p0-sidecar 2>/dev/null || true
docker volume rm p0-redroid-data 2>/dev/null || true
echo "P0 pair removed."
