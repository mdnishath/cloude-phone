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

## Current phase: P1b (Real Device Spawn)

P1b replaces the P1a `create_device_stub` worker job with a real Docker-driven spawn flow: an arq worker brings up a sidecar (proxy + iptables) and a redroid (Android 11) container per device, allocates an ADB port from a Redis-backed free-set, and waits for `sys.boot_completed`. Stop/delete tear the pair down and release the port. A 60s cron reaps devices stuck in `creating` for more than 3 minutes. Per-device Docker named volume keeps installed apps/data across stop/start.

**Breaking API change vs P1a:** `POST /api/v1/devices` now REQUIRES `proxy_id` (was optional). No-proxy mode lands in a later phase.

Full task list: [P1b plan](docs/superpowers/plans/2026-05-15-p1b-real-device-spawn.md). Design: [P1b spec](docs/superpowers/specs/2026-05-15-p1b-real-device-spawn-design.md).

### Bring it up locally (WSL2 with binder loaded)

```bash
cp .env.example .env
# Fill PROXY_HOST/PORT/TYPE/USER/PASS (the same proxy you validated with P0).
python -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))" >> .env
python -c "import secrets;print('STREAM_TOKEN_SECRET=' + secrets.token_urlsafe(64))" >> .env
docker compose run --rm api python -m cloude_api.core.encryption keygen >> .env

docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_profiles.py
docker compose exec api python scripts/make_invite.py --role admin --ttl-hours 24
# Redeem the invite, create a proxy via /api/v1/proxies, then POST /api/v1/devices
# with both profile_id and proxy_id. Watch state: creating → running.
```

API docs: <http://localhost:8000/api/docs>.

## Phases ahead

- **P1a** — FastAPI control plane, JWT auth, invite redeem, device CRUD with worker stub. ✅
- **P1b** (this phase) — real Docker SDK device spawn, stuck-state reaper. Idle reaper + GC deferred.
- **P1c** — Electron desktop dashboard.
- **P1d** — Live device screen in Electron (scrcpy / streaming bridge).
- **P2** — public signup + Stripe + per-plan quotas + idle reaper + 7-day GC.
- **P3+** — scale, hardening, WebRTC upgrade, device profile library.
