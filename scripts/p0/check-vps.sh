#!/usr/bin/env bash
# Idempotent VPS readiness check for Redroid.
# Exits 0 if ready, 1 with reasons if not.
set -u

FAIL=0
ok()   { echo "  OK    $1"; }
fail() { echo "  FAIL  $1"; FAIL=1; }

echo "Checking VPS readiness for Redroid..."

if command -v docker >/dev/null 2>&1; then
  ok "docker installed ($(docker --version | head -c 40))"
else
  fail "docker not installed"
fi

if docker info >/dev/null 2>&1; then
  ok "docker daemon reachable"
else
  fail "docker daemon not running or user not in docker group"
fi

if lsmod 2>/dev/null | grep -qE '^binder_linux'; then
  ok "binder_linux module loaded"
elif grep -q binder /proc/kallsyms 2>/dev/null; then
  ok "binder built into kernel"
else
  fail "binder_linux not available"
fi

if [[ "$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo 0)" == "1" ]]; then
  ok "net.ipv4.ip_forward = 1"
else
  fail "net.ipv4.ip_forward not enabled"
fi

if [[ $FAIL -eq 0 ]]; then
  echo "VPS READY"
  exit 0
else
  echo "VPS NOT READY - run: sudo bash scripts/p0/prepare-vps.sh"
  exit 1
fi
