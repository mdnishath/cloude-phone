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

## Current phase: P1c (Electron Desktop Dashboard)

P1c adds `apps/desktop/` — a native Windows dashboard built with Electron + React + TypeScript + Tailwind + shadcn/ui. It connects to the P1a+P1b backend over HTTP and subscribes to `/ws/devices/{id}/status` for live state updates. Auth tokens persist in the OS keychain via Electron `safeStorage`. Backend URL is editable in Settings (default `http://localhost:8000`). No backend changes in P1c; the only thing the dashboard can't do is show the device's screen — that's P1d.

Full task list: [P1c plan](docs/superpowers/plans/2026-05-15-p1c-electron-dashboard.md). Design: [P1c spec](docs/superpowers/specs/2026-05-15-p1c-electron-dashboard-design.md).

### Run the dashboard locally

Prereqs: the backend is already up (`docker compose up -d` per P1a/P1b). Then:

```bash
cd apps/desktop
npm install
npm run dev
```

A native window opens on `/login`. Mint an invite from the api container (`docker compose exec api python scripts/make_invite.py --role admin --ttl-hours 24`) and redeem it in the UI. Create a proxy, then create a device — watch the state go `creating → running` live.

### Build an installer

```bash
cd apps/desktop && npm run package
# -> dist/Cloude Phone Setup 0.1.0.exe
```

### Bring up the backend (P1a + P1b)

```bash
cp .env.example .env
# Fill PROXY_HOST/PORT/TYPE/USER/PASS (the same proxy you validated with P0).
python -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))" >> .env
python -c "import secrets;print('STREAM_TOKEN_SECRET=' + secrets.token_urlsafe(64))" >> .env
docker compose run --rm api python -m cloude_api.core.encryption keygen >> .env

docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_profiles.py
```

API docs: <http://localhost:8000/api/docs>.

## Phases ahead

- **P1a** — FastAPI control plane, JWT auth, invite redeem, device CRUD with worker stub. ✅
- **P1b** — real Docker SDK device spawn, stuck-state reaper. ✅
- **P1c** (this phase) — Electron desktop dashboard (login, devices, proxies, settings) with live WS updates.
- **P1d** — Live device screen in Electron (scrcpy / streaming bridge).
- **P2** — public signup + Stripe + per-plan quotas + idle reaper + 7-day GC.
- **P3+** — scale, hardening, WebRTC upgrade, device profile library.
