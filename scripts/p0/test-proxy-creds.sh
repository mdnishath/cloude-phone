#!/usr/bin/env bash
# Pre-flight proxy credential test — runs from the VPS host, NO containers.
# Curls https://ifconfig.me through the proxy and prints the egress IP.
# Catches typos/expired creds in 5 seconds instead of 90 seconds of failed
# Docker healthchecks.
#
# Usage:
#   bash scripts/p0/test-proxy-creds.sh             # reads .env
#   bash scripts/p0/test-proxy-creds.sh --proxy-host H --proxy-port P ...
set -euo pipefail

PROXY_HOST=""
PROXY_PORT=""
PROXY_TYPE=""
PROXY_USER=""
PROXY_PASS=""

# Load .env if present and no explicit flags
if [[ -f "$(dirname "$0")/../../.env" && $# -eq 0 ]]; then
  # shellcheck disable=SC1091
  set -a; . "$(dirname "$0")/../../.env"; set +a
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proxy-host) PROXY_HOST="$2"; shift 2 ;;
    --proxy-port) PROXY_PORT="$2"; shift 2 ;;
    --proxy-type) PROXY_TYPE="$2"; shift 2 ;;
    --proxy-user) PROXY_USER="$2"; shift 2 ;;
    --proxy-pass) PROXY_PASS="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

: "${PROXY_HOST:?PROXY_HOST not set (env or --proxy-host)}"
: "${PROXY_PORT:?PROXY_PORT not set}"
: "${PROXY_TYPE:?PROXY_TYPE not set (socks5 | http-connect)}"

# Map our type names to curl's
case "$PROXY_TYPE" in
  socks5)        CURL_PROXY="socks5h://${PROXY_HOST}:${PROXY_PORT}" ;;
  http-connect)  CURL_PROXY="http://${PROXY_HOST}:${PROXY_PORT}" ;;
  *) echo "unknown PROXY_TYPE: $PROXY_TYPE (expected socks5 or http-connect)"; exit 2 ;;
esac

AUTH=()
if [[ -n "${PROXY_USER}${PROXY_PASS}" ]]; then
  AUTH=(-U "${PROXY_USER}:${PROXY_PASS}")
fi

echo "[1/2] Host's own public IP:"
HOST_IP=$(curl -fsS --max-time 10 https://ifconfig.me || echo "ERROR")
echo "      $HOST_IP"

echo "[2/2] Public IP via proxy ($PROXY_TYPE $PROXY_HOST:$PROXY_PORT):"
PROXY_IP=$(curl -fsS --max-time 20 -x "$CURL_PROXY" "${AUTH[@]}" https://ifconfig.me) \
  || { echo "FAIL: curl through proxy errored. Check creds, host, port, type."; exit 1; }
echo "      $PROXY_IP"

if [[ "$HOST_IP" == "$PROXY_IP" ]]; then
  echo "FAIL: proxy IP equals host IP — proxy bypass or misconfig"; exit 1
fi

echo "OK: proxy credentials work. Egress IP via proxy = $PROXY_IP"
