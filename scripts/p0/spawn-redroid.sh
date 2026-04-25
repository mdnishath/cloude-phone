#!/usr/bin/env bash
# Spawn ONE Redroid container joined to an existing sidecar's netns.
#
# Usage:
#   spawn-redroid.sh --name NAME --sidecar SIDECAR_NAME
#                    [--width 1080 --height 2340 --dpi 420]
#                    [--ram-mb 4096 --cpus 4]
#                    [--model Pixel_5 --manufacturer Google]
set -euo pipefail

NAME=""
SIDECAR=""
WIDTH="1080"
HEIGHT="2340"
DPI="420"
RAM_MB="4096"
CPUS="4"
MODEL="Pixel_5"
MANUFACTURER="Google"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)          NAME="$2"; shift 2 ;;
    --sidecar)       SIDECAR="$2"; shift 2 ;;
    --width)         WIDTH="$2"; shift 2 ;;
    --height)        HEIGHT="$2"; shift 2 ;;
    --dpi)           DPI="$2"; shift 2 ;;
    --ram-mb)        RAM_MB="$2"; shift 2 ;;
    --cpus)          CPUS="$2"; shift 2 ;;
    --model)         MODEL="$2"; shift 2 ;;
    --manufacturer)  MANUFACTURER="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

: "${NAME:?--name required}"
: "${SIDECAR:?--sidecar required}"

IMAGE="${REDROID_IMAGE:-redroid/redroid:11.0.0-latest}"
VOLUME="${NAME}-data"

docker volume create "$VOLUME" >/dev/null

# Idempotent
docker rm -f "$NAME" 2>/dev/null || true

docker run -d \
  --name "$NAME" \
  --network="container:${SIDECAR}" \
  --privileged \
  --memory="${RAM_MB}m" --cpus="$CPUS" \
  -v "${VOLUME}:/data" \
  "$IMAGE" \
  androidboot.redroid_width="$WIDTH" \
  androidboot.redroid_height="$HEIGHT" \
  androidboot.redroid_dpi="$DPI" \
  androidboot.redroid_gpu_mode=guest \
  ro.product.model="$MODEL" \
  ro.product.manufacturer="$MANUFACTURER" \
  net.dns1=127.0.0.1 \
  net.dns2=127.0.0.1

# net.dns1/2 points Android's system resolver at the sidecar's dnscrypt-proxy.
# Required because the netns has no DHCP and Android's default DNS (8.8.8.8
# over UDP) would be dropped by our iptables policy.

echo "Redroid started: $NAME (joined netns of $SIDECAR, data volume $VOLUME)"
echo "  profile: ${WIDTH}x${HEIGHT} @ ${DPI}dpi, ${RAM_MB}MB RAM, ${CPUS} CPUs"
echo "  model:   $MANUFACTURER $MODEL"
