#!/usr/bin/env bash
# Spawn a throwaway alpine container into the sidecar's netns and verify that
# its public IP differs from the host's (i.e. egress exits via the proxy).
#
# Usage: test-egress-via-proxy.sh [sidecar-name] [expected-proxy-exit-ip]
set -euo pipefail

SIDECAR="${1:-p0-sidecar}"
EXPECTED_PROXY_EGRESS_IP="${2:-}"

echo "Host public IP:"
HOST_IP=$(curl -fsS --max-time 10 https://ifconfig.me || echo "HOST_IP_ERROR")
echo "  $HOST_IP"

echo "Container-via-sidecar public IP:"
# --dns 127.0.0.1: the sidecar's dnscrypt-proxy lives at 127.0.0.1:53 inside
# the shared netns. Docker's default 127.0.0.11 resolver is NOT reachable there.
CONTAINER_IP=$(docker run --rm \
  --network="container:${SIDECAR}" \
  --dns 127.0.0.1 \
  alpine:3.20 \
  sh -c 'apk add --no-cache curl >/dev/null 2>&1 && curl -fsS --max-time 15 https://ifconfig.me')
echo "  $CONTAINER_IP"

if [[ "$HOST_IP" == "$CONTAINER_IP" ]]; then
  echo "FAIL: container IP matches host IP - traffic NOT going through proxy"
  exit 1
fi

if [[ -n "$EXPECTED_PROXY_EGRESS_IP" && "$CONTAINER_IP" != "$EXPECTED_PROXY_EGRESS_IP" ]]; then
  echo "FAIL: container IP ($CONTAINER_IP) != expected proxy IP ($EXPECTED_PROXY_EGRESS_IP)"
  exit 1
fi

echo "OK: egress correctly routed via proxy"
