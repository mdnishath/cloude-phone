# Cloud Android — QA Platform

Self-hosted cloud Android platform for app developers, QA engineers, and automation experts. Spawn Android device instances, interact via browser, test with per-instance proxy routing.

**Scope:** Device-diversity QA platform (Genymotion Cloud / BrowserStack style). Explicitly not a detection-evasion tool — see [design spec §16](docs/superpowers/specs/2026-04-20-cloud-android-platform-design.md).

## Layout

- `docs/superpowers/specs/` — design documents
- `docs/superpowers/plans/` — implementation plans
- `docker/` — container image sources
- `scripts/` — operational scripts

## Current phase: P0 (Foundation)

P0 validates **one** Redroid + sidecar pair end-to-end: Android egress goes through a user-supplied SOCKS5/HTTP proxy, zero traffic escapes if the sidecar dies, and a desktop scrcpy client can control it.

Full task list: [P0 plan](docs/superpowers/plans/2026-04-20-cloud-android-platform-p0.md).

## P0 Quick Start

Fresh Ubuntu 22.04 VPS:

```bash
git clone <this-repo> /root/cloude-phone && cd /root/cloude-phone

sudo bash scripts/p0/prepare-vps.sh
bash scripts/p0/check-vps.sh             # expect: VPS READY
bash scripts/p0/build-sidecar.sh

bash scripts/p0/spawn-pair.sh \
  --proxy-host YOUR.PROXY.HOST \
  --proxy-port 1080 \
  --proxy-type socks5 \
  --proxy-user USER --proxy-pass PASS \
  --adb-port 40000

bash scripts/p0/test-egress-via-proxy.sh p0-sidecar
bash scripts/p0/test-no-leak.sh p0-sidecar
```

From your laptop:

```bash
adb connect <VPS_IP>:40000
scrcpy -s <VPS_IP>:40000 --max-size 1080
```

Cleanup: `bash scripts/p0/cleanup.sh`

## Phases ahead

- **P1 MVP** — dashboard (Next.js), control-plane API (FastAPI), Postgres, Redis, worker, ws-scrcpy browser streaming, multi-instance orchestration.
- **P2** — multi-tenant auth, invite redeem flow, per-user quota, billing hooks.
- **P3+** — scale, hardening, WebRTC upgrade, device profile library.
