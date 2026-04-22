#!/usr/bin/env bash
# Build the sidecar image locally.
set -euo pipefail

IMAGE="${SIDECAR_IMAGE:-cloude/sidecar:p0}"
CONTEXT="$(cd "$(dirname "$0")/../.." && pwd)/docker/sidecar"

echo "Building $IMAGE from $CONTEXT"
docker build -t "$IMAGE" "$CONTEXT"
echo "Built: $IMAGE"
docker images "$IMAGE"
