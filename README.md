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
# 1. Clone + prep
git clone https://github.com/mdnishath/cloude-phone.git /root/cloude-phone
cd /root/cloude-phone

sudo bash scripts/p0/prepare-vps.sh
bash scripts/p0/check-vps.sh             # expect: VPS READY
bash scripts/p0/build-sidecar.sh

# 2. Configure proxy creds (gitignored, stays local)
cp .env.example .env
nano .env                                  # fill PROXY_HOST/PORT/TYPE/USER/PASS

# 3. Pre-flight: verify proxy creds work BEFORE spinning containers
bash scripts/p0/test-proxy-creds.sh        # expect: OK: proxy credentials work

# 4. Spawn the pair (auto-loads .env)
bash scripts/p0/spawn-pair.sh              # expect: OK: Android booted in Ns

# 5. Validate
bash scripts/p0/test-egress-via-proxy.sh p0-sidecar
bash scripts/p0/test-no-leak.sh p0-sidecar
```

From your laptop:

```bash
adb connect <VPS_IP>:40000
scrcpy -s <VPS_IP>:40000 --max-size 1080
```

Cleanup: `bash scripts/p0/cleanup.sh`

### Proxy type cheat-sheet

| Vendor terminology | `PROXY_TYPE` value |
|---|---|
| SOCKS5 / SOCKS5h | `socks5` |
| "HTTPS proxy" / HTTP CONNECT | `http-connect` |
| Plain HTTP proxy | `http-connect` |

## Phases ahead

- **P1 MVP** — dashboard (Next.js), control-plane API (FastAPI), Postgres, Redis, worker, ws-scrcpy browser streaming, multi-instance orchestration.
- **P2** — multi-tenant auth, invite redeem flow, per-user quota, billing hooks.
- **P3+** — scale, hardening, WebRTC upgrade, device profile library.
