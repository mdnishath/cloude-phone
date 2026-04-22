#!/usr/bin/env bash
# One-time VPS setup for Redroid. Must run as root. Idempotent.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must be run as root (use sudo)"; exit 1
fi

echo "[1/4] Installing Docker Engine if missing..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  echo "  docker already present"
fi

echo "[2/4] Loading binder_linux kernel module..."
if ! lsmod | grep -qE '^binder_linux'; then
  if modprobe binder_linux num_binders=8 2>/dev/null; then
    echo "  loaded binder_linux"
  elif grep -q binder /proc/kallsyms 2>/dev/null; then
    echo "  binder built into kernel; nothing to load"
  else
    echo "ERROR: binder_linux not available on this kernel ($(uname -r))."
    echo "Use Ubuntu 22.04 generic kernel or newer with binder support."
    exit 1
  fi
fi
modprobe ashmem_linux 2>/dev/null || true

echo "[3/4] Persisting module load across reboots..."
cat >/etc/modules-load.d/redroid.conf <<EOF
binder_linux
ashmem_linux
EOF
echo "options binder_linux num_binders=8" >/etc/modprobe.d/redroid.conf

echo "[4/4] Enabling IP forwarding..."
sysctl -w net.ipv4.ip_forward=1 >/dev/null
grep -qE '^\s*net\.ipv4\.ip_forward\s*=\s*1' /etc/sysctl.conf \
  || echo "net.ipv4.ip_forward=1" >>/etc/sysctl.conf

echo "VPS preparation complete."
