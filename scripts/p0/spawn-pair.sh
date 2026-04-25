#!/usr/bin/env bash
# Spawn a sidecar + redroid pair (default P0 names) and wait for Android boot.
#
# Usage:
#   spawn-pair.sh                                            # reads .env
#   spawn-pair.sh --proxy-host H --proxy-port P ...          # explicit flags override
set -euo pipefail

PROXY_HOST=""
PROXY_PORT=""
PROXY_TYPE=""
PROXY_USER=""
PROXY_PASS=""
ADB_PORT="40000"

# Auto-load .env from repo root if it exists
ENV_FILE="$(cd "$(dirname "$0")/../.." && pwd)/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "[spawn-pair] loading $ENV_FILE"
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proxy-host) PROXY_HOST="$2"; shift 2 ;;
    --proxy-port) PROXY_PORT="$2"; shift 2 ;;
    --proxy-type) PROXY_TYPE="$2"; shift 2 ;;
    --proxy-user) PROXY_USER="$2"; shift 2 ;;
    --proxy-pass) PROXY_PASS="$2"; shift 2 ;;
    --adb-port)   ADB_PORT="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

: "${PROXY_HOST:?PROXY_HOST not set (env or --proxy-host)}"
: "${PROXY_PORT:?PROXY_PORT not set (env or --proxy-port)}"
: "${PROXY_TYPE:?PROXY_TYPE not set (env or --proxy-type)}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/3] Spawning sidecar..."
bash "$SCRIPT_DIR/spawn-sidecar.sh" \
  --name p0-sidecar \
  --proxy-host "$PROXY_HOST" --proxy-port "$PROXY_PORT" --proxy-type "$PROXY_TYPE" \
  --proxy-user "$PROXY_USER" --proxy-pass "$PROXY_PASS" \
  --adb-port "$ADB_PORT"

bash "$SCRIPT_DIR/test-sidecar-healthy.sh" p0-sidecar

echo "[2/3] Spawning redroid..."
bash "$SCRIPT_DIR/spawn-redroid.sh" --name p0-redroid --sidecar p0-sidecar

echo "[3/3] Waiting for Android to boot (up to 120s)..."
for i in $(seq 1 60); do
  if docker exec p0-redroid sh -c 'getprop sys.boot_completed 2>/dev/null' | grep -q 1; then
    echo "OK: Android booted in $((i*2))s"
    echo ""
    echo "Next:"
    echo "  On VPS:    bash scripts/p0/test-egress-via-proxy.sh p0-sidecar"
    echo "  On laptop: adb connect <VPS_IP>:$ADB_PORT && scrcpy -s <VPS_IP>:$ADB_PORT"
    exit 0
  fi
  sleep 2
done

echo "FAIL: Android did not reach boot_completed within 120s"
echo "--- last 50 lines of redroid log ---"
docker logs --tail=50 p0-redroid 2>&1 || true
exit 1
