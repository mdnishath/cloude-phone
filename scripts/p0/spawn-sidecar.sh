#!/usr/bin/env bash
# Spawn ONE sidecar container with proxy credentials.
#
# Usage:
#   spawn-sidecar.sh --name NAME
#                    --proxy-host HOST --proxy-port PORT --proxy-type socks5|http-connect
#                    [--proxy-user U --proxy-pass P]
#                    [--adb-port 40000]
set -euo pipefail

NAME=""
PROXY_HOST=""
PROXY_PORT=""
PROXY_TYPE=""
PROXY_USER=""
PROXY_PASS=""
ADB_PORT="40000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)        NAME="$2"; shift 2 ;;
    --proxy-host)  PROXY_HOST="$2"; shift 2 ;;
    --proxy-port)  PROXY_PORT="$2"; shift 2 ;;
    --proxy-type)  PROXY_TYPE="$2"; shift 2 ;;
    --proxy-user)  PROXY_USER="$2"; shift 2 ;;
    --proxy-pass)  PROXY_PASS="$2"; shift 2 ;;
    --adb-port)    ADB_PORT="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

: "${NAME:?--name required}"
: "${PROXY_HOST:?--proxy-host required}"
: "${PROXY_PORT:?--proxy-port required}"
: "${PROXY_TYPE:?--proxy-type required}"

IMAGE="${SIDECAR_IMAGE:-cloude/sidecar:p0}"

# Idempotent: remove any stale container by this name
docker rm -f "$NAME" 2>/dev/null || true

docker run -d \
  --name "$NAME" \
  --cap-add NET_ADMIN --cap-add NET_RAW \
  --sysctl net.ipv4.ip_forward=1 \
  -p "${ADB_PORT}:5555" \
  -e PROXY_HOST="$PROXY_HOST" \
  -e PROXY_PORT="$PROXY_PORT" \
  -e PROXY_TYPE="$PROXY_TYPE" \
  -e PROXY_USER="$PROXY_USER" \
  -e PROXY_PASS="$PROXY_PASS" \
  "$IMAGE"

echo "Sidecar started: $NAME"
echo "  image:     $IMAGE"
echo "  proxy:     $PROXY_TYPE $PROXY_HOST:$PROXY_PORT"
echo "  adb port:  host:$ADB_PORT (available once Redroid joins this netns)"
