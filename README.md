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

## Current phase: P1a (Backend Foundation)

P1a stands up the control plane: FastAPI + arq worker + Postgres 16 + Redis 7 in a single `docker-compose.yml`. JWT auth, invite-only signup, full device CRUD with a stub worker that fakes the spawn (real Docker SDK lands in P1b). No frontend yet.

Full task list: [P1a plan](docs/superpowers/plans/2026-04-25-p1a-backend-foundation.md).

### Bring it up locally

```bash
cp .env.example .env
# Mint secrets
python -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))" >> .env
python -c "import secrets;print('STREAM_TOKEN_SECRET=' + secrets.token_urlsafe(64))" >> .env
# Generate libsodium keypair
docker compose run --rm api python -m cloude_api.core.encryption keygen >> .env

docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_profiles.py
docker compose exec api python scripts/make_invite.py --role admin --ttl-hours 24
# copy the printed token, then:
curl -X POST http://localhost:8000/api/v1/auth/redeem-invite \
  -H 'content-type: application/json' \
  -d '{"token":"<TOKEN>","email":"you@example.com","password":"choose-a-good-one"}'
```

API docs: <http://localhost:8000/api/docs>.

## Phases ahead

- **P1a** (this phase) — FastAPI control plane, JWT auth, invite redeem, device CRUD with worker stub.
- **P1b** — real Docker SDK device spawn, idle reaper, GC cron.
- **P1c** — Next.js dashboard.
- **P1d** — ws-scrcpy bridge for in-browser streaming.
- **P2** — public signup + Stripe + per-plan quotas.
- **P3+** — scale, hardening, WebRTC upgrade, device profile library.
