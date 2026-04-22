# Cloud Android Device Diversity Testing Platform — Design Spec

**Date:** 2026-04-20
**Status:** Draft — pending user review
**Scope:** Phase P0 (Foundation) + P1 (MVP). P2–P4 deferred to separate specs.

---

## 1. Purpose & Positioning

A self-hosted cloud Android platform (Genymotion Cloud / BrowserStack style) that lets app developers, QA engineers, and automation experts spawn and use Android device instances from a web browser.

**Use cases targeted:**
- Mobile app testing across hardware profiles (screen size, RAM, model label)
- Geographic behavior testing via per-instance proxy
- Automation / CI integration (ADB over network, future Appium hook)

**Explicit non-goals:**
- No detection-evasion tooling (no Magisk, Shamiko, HideMyApplist, Play Integrity bypass).
- No marketing as "undetectable" or "anti-detect".
- No Google-account mass-management workflows.

Redroid is a virtualized Android runtime — that's a feature for QA, not a flaw.

---

## 2. Phase Scope

### P0 — Foundation *(goal: one working instance end-to-end)*
- Single Redroid container launches on Ubuntu VPS.
- Sidecar proxy routes all TCP through a configured SOCKS5 / HTTP proxy.
- `curl ifconfig.me` from inside Android returns the proxy's IP (proves no leak).
- Manual scrcpy (desktop) connects via ADB and displays the screen.
- No UI, no API — pure shell validation.

### P1 — MVP *(goal: dashboard-driven multi-instance)*
- Authenticated Next.js dashboard (invite-only, JWT).
- User can create / start / stop / delete device instances.
- User can attach a saved proxy to an instance.
- User can open a browser tab with live scrcpy-ws view + input control.
- Target capacity: 20–50 concurrent instances on a single mid-tier VPS (e.g. 16 vCPU / 64 GB RAM / 1 TB NVMe).

### Deferred (P2+)
- Email/password self-signup, Stripe billing, per-plan quota enforcement.
- WebRTC streaming (replaces ws-scrcpy).
- Horizontal scale (K3s migration).
- Android 12 / 13 images, device profile marketplace.
- Regional POPs, GPU passthrough, persistent snapshot/clone.

---

## 3. System Architecture

```
                    ┌─────────────────────────────────────────┐
                    │          PUBLIC INTERNET (TLS)          │
                    └──────────────────┬──────────────────────┘
                          ┌────────────▼────────────┐
                          │      Caddy (edge)        │
                          └────────────┬─────────────┘
        ┌──────────────────────────────┼──────────────────────────────┐
  ┌─────▼──────┐              ┌────────▼────────┐           ┌─────────▼────────┐
  │ Next.js    │              │ FastAPI control │           │ ws-scrcpy bridge │
  │ dashboard  │◄── REST/WS ──┤  plane + auth   │◄──────────┤ (per-session)    │
  └────────────┘              └──┬──────┬───────┘           └─────────┬────────┘
                                 │      │                             │
                     ┌───────────▼──┐ ┌─▼─────────┐                   │
                     │  Postgres    │ │  Redis    │                   │
                     └──────────────┘ └────┬──────┘                   │
                                           │                           │
                                ┌──────────▼──────────┐                │
                                │ arq / Celery worker │                │
                                │ (Docker SDK spawner)│                │
                                └──────────┬──────────┘                │
                                           │                           │
        ┌──────────────────────────────────┼───────────────────────────┘
        │           DATA PLANE (N × per-instance pairs)                
        ▼                                  ▼                           
┌──────────────────────────────────────────────────────────────────┐
│  netns: device-{uuid}                                             │
│  ┌──────────────────────┐    ┌─────────────────────────────────┐ │
│  │ redroid-{uuid}       │    │ sidecar-{uuid}                   │ │
│  │ Android 11 AOSP      │◄──►│ redsocks :12345                   │ │
│  │ /data volume         │    │ dnscrypt-proxy :53                │ │
│  │ scrcpy-server        │    │ iptables REDIRECT                 │ │
│  │ ADB :5555 (shared)   │    │ egress → user proxy               │ │
│  └──────────────────────┘    └─────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### Component inventory

| # | Component | Responsibility | Deploy |
|---|---|---|---|
| 1 | Caddy | TLS, HTTP/WS routing | 1 static container |
| 2 | Next.js dashboard | UI + ws-scrcpy client embed | 1 static container |
| 3 | FastAPI API server | REST + WS endpoints, auth | 1 static container |
| 4 | arq worker | Async instance lifecycle jobs | 1+ static containers |
| 5 | PostgreSQL 16 | Persistent state | 1 static container |
| 6 | Redis 7 | Job queue + session cache | 1 static container |
| 7 | ws-scrcpy bridge | scrcpy → WebSocket translator | 1 static container |
| 8 | Redroid instance | Per-device Android | N dynamic containers |
| 9 | Sidecar proxy | Per-device egress | N dynamic containers (paired with #8) |

Components 1–7 defined in `docker-compose.yml`. Components 8–9 spawned by the worker via Docker SDK.

---

## 4. Data Model (PostgreSQL)

### 4.1 Tables

**`users`**

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `email` | TEXT UNIQUE NOT NULL | login identifier |
| `password_hash` | TEXT NOT NULL | argon2id |
| `role` | ENUM(`admin`, `user`) | |
| `quota_instances` | INT DEFAULT 3 | max concurrent running devices |
| `created_at` | TIMESTAMPTZ | |

**`device_profiles`** — hardware template a user picks at create time

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | TEXT | e.g. "Pixel 5 (1080×2340)" |
| `android_version` | TEXT | `11` only in P1 |
| `screen_width` | INT | |
| `screen_height` | INT | |
| `screen_dpi` | INT | |
| `ram_mb` | INT | default 4096 |
| `cpu_cores` | INT | default 4 |
| `manufacturer` | TEXT | passed as `ro.product.manufacturer` for legitimate QA of brand-gated code paths |
| `model` | TEXT | passed as `ro.product.model` |
| `is_public` | BOOL | visible to all users |
| `created_by` | UUID → users.id | |

Seeded in P1 with ~6 public profiles (Pixel 5, Pixel 7, Galaxy A53, low-end 720p, tablet 1200×1920, small phone 720×1280).

**`proxies`** — user-owned proxy configs

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID → users.id ON DELETE CASCADE | |
| `label` | TEXT | user-given name |
| `type` | ENUM(`socks5`, `http`) | |
| `host` | TEXT | |
| `port` | INT | |
| `username` | TEXT NULLABLE | |
| `password_encrypted` | BYTEA NULLABLE | libsodium sealed box, KMS key in env |
| `created_at` | TIMESTAMPTZ | |

**`devices`** — instance records (the core entity)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID → users.id | |
| `name` | TEXT | user-given label |
| `profile_id` | UUID → device_profiles.id | |
| `proxy_id` | UUID → proxies.id NULLABLE | direct egress if null |
| `state` | ENUM(`creating`, `running`, `stopping`, `stopped`, `error`, `deleted`) | |
| `state_reason` | TEXT NULLABLE | error detail |
| `redroid_container_id` | TEXT NULLABLE | Docker container ID |
| `sidecar_container_id` | TEXT NULLABLE | Docker container ID |
| `adb_host_port` | INT NULLABLE | dynamic from 40000–49999 |
| `created_at` | TIMESTAMPTZ | |
| `started_at` | TIMESTAMPTZ NULLABLE | |
| `stopped_at` | TIMESTAMPTZ NULLABLE | |

**`sessions`** — active streaming WS sessions (for idle-reaper + concurrency tracking)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `device_id` | UUID → devices.id ON DELETE CASCADE | |
| `user_id` | UUID → users.id | |
| `started_at` | TIMESTAMPTZ | |
| `last_ping_at` | TIMESTAMPTZ | updated every 30s from client |
| `client_ip` | INET | |

**`audit_log`** — tamper-resistant action trail

| column | type | notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `user_id` | UUID NULLABLE | |
| `action` | TEXT | e.g. `device.create`, `device.start`, `auth.login` |
| `target_id` | UUID NULLABLE | |
| `metadata` | JSONB | |
| `created_at` | TIMESTAMPTZ | |

### 4.2 Indexes
- `devices(user_id, state)` — dashboard list queries
- `devices(state)` WHERE state IN (`creating`,`running`) — capacity checks
- `sessions(device_id, last_ping_at DESC)` — orphan reaper
- `audit_log(user_id, created_at DESC)` — user activity

### 4.3 Enum definitions live in migrations
Use Alembic + SQLAlchemy 2.x. Enums as native Postgres enums (not CHECK constraints).

---

## 5. API Surface

Base path `/api/v1`. All responses JSON. Auth via `Authorization: Bearer <jwt>`.

### 5.1 REST

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login` | email+password → `{access, refresh}` |
| POST | `/auth/refresh` | refresh token rotation |
| GET | `/me` | current user + quota |
| GET | `/device-profiles` | list available profiles |
| POST | `/proxies` | create proxy |
| GET | `/proxies` | list mine |
| DELETE | `/proxies/{id}` | soft delete if referenced |
| POST | `/devices` | create (async) — returns `{id, state:"creating"}` |
| GET | `/devices` | list mine (pagination) |
| GET | `/devices/{id}` | full detail |
| POST | `/devices/{id}/start` | if stopped |
| POST | `/devices/{id}/stop` | if running |
| DELETE | `/devices/{id}` | stop + remove container + drop volume |
| GET | `/devices/{id}/stream-token` | short-lived HMAC token for WS |
| GET | `/devices/{id}/adb-info` | host, port, one-time `adb connect` cmd |

### 5.2 WebSocket

| Path | Purpose |
|---|---|
| `/ws/devices/{id}/status` | live state transitions pushed to dashboard |
| `/ws/devices/{id}/stream?token=X` | scrcpy frames + input forwarding (token validated server-side, bridged to ws-scrcpy container) |

### 5.3 Error envelope
```json
{ "error": { "code": "quota_exceeded", "message": "...", "details": {...} } }
```

---

## 6. Lifecycle & Worker Design

### 6.1 State machine
```
 creating ──► running ──► stopping ──► stopped ──► deleted
    │           │                          │
    └─► error ◄─┘                          └─► running (on start)
```

### 6.2 `create_device` job steps (happy path)
1. Allocate unused ADB port from 40000–49999 (Redis `SRANDMEMBER` from a free set).
2. Create Docker named volume `device-{uuid}-data`.
3. Read proxy row (if any), decrypt password.
4. Spawn sidecar: `docker run -d --cap-add=NET_ADMIN --name sidecar-{uuid} -p {adb_port}:5555 -e PROXY_* ... sidecar:latest`. Sidecar creates the netns.
5. Poll sidecar healthcheck (redsocks listening) up to 15 s.
6. Spawn Redroid: `docker run -d --name redroid-{uuid} --network=container:sidecar-{uuid} --privileged -v device-{uuid}-data:/data redroid:11 androidboot.redroid_width=... ro.product.model=...`.
7. Poll ADB boot-complete (`adb -s localhost:{adb_port} shell getprop sys.boot_completed`) up to 90 s.
8. Update `devices` row: state=`running`, fill container IDs + ADB port, `started_at=now()`.
9. Publish status event to `ws:device:{id}` Redis channel (API server rebroadcasts to WS subscribers).

### 6.3 Failure branches
- Any step fails → enter `error`, record `state_reason`, attempt cleanup (remove sidecar + redroid if created).
- Idempotency: worker computes container names from device UUID, so retries are safe (check existence first).
- Stuck `creating` > 5 min → reaper cron marks `error`.

### 6.4 `stop_device` / `delete_device`
- Stop: `docker stop redroid-{uuid} sidecar-{uuid}` → state=`stopped`.
- Delete: stop + `docker rm` both + `docker volume rm device-{uuid}-data` → state=`deleted` (row retained for audit, sessions cascade-removed).

### 6.5 Idle reaper
Cron every 5 min: devices with `state=running` but no session with `last_ping_at > now()-4h` → auto-stop. Configurable per plan in P2.

---

## 7. Sidecar Proxy — Detailed Design

### 7.1 Responsibilities (in priority order)
1. **Own the network namespace** for the instance pair.
2. **Force all TCP egress through `redsocks`** via iptables REDIRECT.
3. **Prevent DNS leaks** by running `dnscrypt-proxy` locally + dropping non-local UDP.
4. **Fail closed** — if redsocks crashes, no traffic escapes (default-drop OUTPUT policy except what's REDIRECT'd).

### 7.2 Dockerfile (sketch — full version in implementation plan)
```dockerfile
FROM alpine:3.20
RUN apk add --no-cache redsocks iptables dnscrypt-proxy ca-certificates \
                      bash curl gettext
COPY entrypoint.sh /entrypoint.sh
COPY redsocks.conf.tpl /etc/redsocks/redsocks.conf.tpl
COPY dnscrypt-proxy.toml /etc/dnscrypt-proxy/dnscrypt-proxy.toml
RUN chmod +x /entrypoint.sh
HEALTHCHECK --interval=5s --timeout=2s \
  CMD nc -z 127.0.0.1 12345 || exit 1
ENTRYPOINT ["/entrypoint.sh"]
```

### 7.3 `entrypoint.sh` behavior (sketch)
1. `envsubst` render `redsocks.conf` from template using `$PROXY_HOST`, `$PROXY_PORT`, `$PROXY_TYPE`, `$PROXY_USER`, `$PROXY_PASS`.
2. Start `dnscrypt-proxy` in background.
3. Apply iptables rules (see 7.5).
4. `exec redsocks -c /etc/redsocks/redsocks.conf` in foreground (PID 1).

### 7.4 `redsocks.conf` template
```
base {
  log_debug = off; log_info = on; log = "stderr"; daemon = off;
  redirector = iptables;
}
redsocks {
  local_ip = 0.0.0.0; local_port = 12345;
  ip = ${PROXY_HOST}; port = ${PROXY_PORT};
  type = ${PROXY_TYPE};    // socks5 | http-connect
  login = "${PROXY_USER}";
  password = "${PROXY_PASS}";
}
```

### 7.5 iptables ruleset (applied by entrypoint)
```bash
# TCP: redirect everything to redsocks except loopback + RFC1918
iptables -t nat -N REDSOCKS
iptables -t nat -A REDSOCKS -d 0.0.0.0/8     -j RETURN
iptables -t nat -A REDSOCKS -d 10.0.0.0/8    -j RETURN
iptables -t nat -A REDSOCKS -d 127.0.0.0/8   -j RETURN
iptables -t nat -A REDSOCKS -d 169.254.0.0/16 -j RETURN
iptables -t nat -A REDSOCKS -d 172.16.0.0/12 -j RETURN
iptables -t nat -A REDSOCKS -d 192.168.0.0/16 -j RETURN
iptables -t nat -A REDSOCKS -p tcp -j REDIRECT --to-ports 12345
iptables -t nat -A OUTPUT   -p tcp -j REDSOCKS

# DNS: only via local dnscrypt-proxy (which itself routes via redsocks)
iptables -A OUTPUT -p udp --dport 53 -d 127.0.0.1 -j ACCEPT
iptables -A OUTPUT -p udp -j DROP

# Default drop for anything unexpected (belt + braces)
iptables -P OUTPUT DROP
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -p tcp -j ACCEPT   # (already REDIRECT'd above)
```

**Why this is leak-proof:**
- Android apps that respect `HTTP_PROXY`: caught by redsocks.
- Apps that bypass env vars with direct sockets: caught by iptables at kernel level.
- DNS queries: forced through dnscrypt-proxy → which itself egresses via redsocks.
- UDP apps (QUIC, WebRTC STUN): dropped. QA-appropriate — QUIC testing needs a separate UDP-capable profile (P3+).

### 7.6 Port publishing
The sidecar publishes ADB port (`5555` inside netns → `{adb_host_port}` on host). Since Redroid joins `--network=container:sidecar`, the Redroid's ADB is reachable via the sidecar's port mapping.

---

## 8. Redroid Container Config

**Image:** `redroid/redroid:11.0.0_64only-latest` (pinned digest in compose).

**Host prereqs (P0 setup script):**
- Load kernel modules: `binder_linux` (`modprobe binder_linux num_binders=8`), `ashmem_linux`.
- Create `/etc/modules-load.d/redroid.conf`.

**Launch args (illustrative — full in impl plan):**
```
docker run -d \
  --name redroid-{uuid} \
  --network=container:sidecar-{uuid} \
  --privileged \
  --memory={profile.ram_mb}m --cpus={profile.cpu_cores} \
  -v device-{uuid}-data:/data \
  redroid/redroid:11.0.0_64only-latest \
    androidboot.redroid_width={w} \
    androidboot.redroid_height={h} \
    androidboot.redroid_dpi={dpi} \
    androidboot.redroid_gpu_mode=guest \
    ro.product.model={profile.model} \
    ro.product.manufacturer={profile.manufacturer}
```

`--privileged` is Redroid's current upstream norm. P3 hardening task: replace with `--cap-add SYS_NICE` + specific `--device` bind mounts.

---

## 9. Streaming Bridge (ws-scrcpy)

**Deployment:** run [ws-scrcpy](https://github.com/NetrisTV/ws-scrcpy) upstream image as a separate container on the Docker network (not in per-device netns — it needs to reach multiple ADB endpoints).

**Flow:**
1. User clicks device → frontend calls `GET /devices/{id}/stream-token` → 5-min HMAC token.
2. Frontend opens WS to `wss://host/ws/devices/{id}/stream?token=...`.
3. API validates token, creates `sessions` row, then proxies the WS to ws-scrcpy container with the device's ADB endpoint as the target.
4. ws-scrcpy pushes scrcpy-server into Android over ADB, then streams H.264 frames + input events over WS.

**Token format:** `base64url(device_id):base64url(nonce):hmac_sha256(secret, device_id|nonce|exp)` — server validates exp, checks nonce not consumed, marks consumed in Redis (`SETEX` 300s).

---

## 10. Frontend (Next.js 14)

| Route | Purpose |
|---|---|
| `/login` | JWT login form |
| `/` | Dashboard grid of my devices + "Create" CTA |
| `/devices/new` | Wizard: pick profile → pick proxy → name → create |
| `/devices/[id]` | Live stream (ws-scrcpy embed) + ADB info + stop/delete |
| `/proxies` | CRUD proxies |
| `/admin` | (admin role) user list + quota editor |

State: React Query for server data, Zustand for UI state. WebSocket hook for live status updates.

---

## 11. Security

| Concern | Mitigation |
|---|---|
| Proxy password at rest | libsodium sealed box; master key from `ENCRYPTION_KEY` env (rotated via re-encrypt job) |
| JWT forgery | HS256 with 256-bit secret; access 15 min; refresh 30 d, rotated on use |
| Stream token replay | Single-use, 5 min TTL, stored in Redis |
| Docker socket exposure | API server does NOT mount `/var/run/docker.sock`. Worker does (it's the only one that spawns). Worker runs as dedicated user. |
| Container escape | `--privileged` on Redroid is a known risk; mitigated by host isolation (dedicated VPS, no other tenants); P3 hardening task logged |
| Per-user isolation | Instances labeled with `user_id`; API enforces ownership on every call |
| CORS / CSRF | CORS locked to dashboard origin; mutations require `Authorization` header (no cookie) |
| Rate limit | slowapi on auth + expensive endpoints (10/min login, 5/min device-create) |
| Audit trail | All state-mutating endpoints write `audit_log`; append-only |

---

## 12. Testing Strategy

### P0
- Shell scripts:
  - `scripts/p0/spawn.sh` — spawn pair, wait boot, run `adb shell curl ifconfig.me`, assert output == proxy IP.
  - `scripts/p0/leak_check.sh` — stop sidecar, assert container has no egress.

### P1
- Unit tests (pytest + httpx): all API handlers, with docker SDK mocked.
- Integration (pytest + testcontainers-python): spawn 1 real Redroid pair end-to-end in CI on self-hosted runner.
- E2E (Playwright): login → create device → wait running → click into device → assert scrcpy `<canvas>` receives frames.

Coverage goal P1: 70% lines on API + worker, smoke E2E only.

---

## 13. Operations

| Concern | P1 plan |
|---|---|
| Instance idle TTL | 4 h no active session → auto-stop |
| Stuck-state reaper | `creating` > 5 min → `error`; `stopping` > 2 min → force-kill |
| Storage | `/data` volume ~2 GB each; 50 × 2 GB = 100 GB budget; alert at 70 % disk |
| CPU/RAM budget | ~1 vCPU + 1.5 GB steady per active Redroid. **Single-VPS reality:** 16 vCPU / 64 GB holds ~20–25 concurrently active; hitting 50 requires either bursty usage (many created, few active at once) or adding a second node in P2. Section 2's "20–50" target reflects this spread. |
| Logs | Loki + promtail; retain 14 days |
| Metrics | Prometheus + Grafana; dashboards: cluster capacity, active instances, spawn latency p50/p95, WS session count |
| Backup | Nightly `pg_dump` → S3-compatible bucket; Redroid `/data` NOT backed up in P1 (ephemeral QA workspaces) |
| Deploy | Single `docker-compose.yml`; `git pull && docker compose up -d --build`; zero-downtime not required in P1 |

---

## 14. Resolved Decisions *(user-confirmed 2026-04-20)*

1. **Deployment topology:** Single VPS for all of P1 (Postgres, Redis, API, worker, Redroid pool on same host). Split to multi-node deferred to P2.
2. **Signup model:** Invite-only. Admin generates invite tokens; user redeems token to set email/password. No public signup form in P1.
3. **ws-scrcpy:** Use upstream image (`netrisn/ws-scrcpy` or equivalent), pinned digest. No fork. Config-only customization.
4. **`ro.build.fingerprint` / deep fingerprint manipulation:** **Explicitly out of scope.** Only `ro.product.model` and `ro.product.manufacturer` are exposed as QA parameters (for brand-gated code paths). Deeper prop manipulation stays in the non-goal zone.
5. **Stopped-instance retention:** 7-day TTL. Cron job daily at 03:00 UTC: any device with `state=stopped` AND `stopped_at < now() - 7 days` → cascade delete (containers removed at stop time; volume dropped here; DB row soft-deleted via `state=deleted`).

---

## 15. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Redroid kernel module issues on provider VPS | Med | Blocker | Validate `binder_linux` works on chosen provider *before* any other P0 work |
| Privileged container escape | Low | Critical | Dedicated VPS per deployment; P3 hardening backlog item |
| Proxy provider throttles/drops connections | Med | Degraded UX | Health check endpoint tests proxy on add; surface per-device connection errors in UI |
| Disk fills from zombie volumes | Med | Outage | Reaper job + Grafana disk alert |
| Host network namespace / iptables quirks on Ubuntu | Med | Spawn failures | Pin kernel to 5.15 LTS or 6.5+; document tested kernels in README |
| Scale cliff at ~50 instances | Med | Can't grow | P2 K3s migration spec already scheduled |

---

## 16. Out-of-Scope Reminders (anti-scope-creep)

- ❌ Magisk, Shamiko, HideMyApplist, Play Integrity bypass — not installed, not supported, not planned.
- ❌ Pre-bundled Google accounts or residential proxy provisioning.
- ❌ Mobile-app dashboard, desktop client — web only.
- ❌ Multi-region, CDN, GPU passthrough — P4+.
- ❌ Billing / Stripe — P2.

---

## 17. Success Criteria

P0 complete when:
- [ ] One Redroid + sidecar pair spawned via shell script.
- [ ] `adb shell curl -s ifconfig.me` returns the configured proxy's public IP.
- [ ] Stopping sidecar results in zero egress from Redroid (verified by `tcpdump` on host).
- [ ] Desktop scrcpy connects and displays the home screen.

P1 complete when:
- [ ] User can login, create a device via UI, see it reach `running` state.
- [ ] User can open the device page and interact with Android in the browser.
- [ ] User can stop/delete and quota is enforced.
- [ ] 20 concurrent instances run stable for 24 h on target VPS without OOM/leak.
- [ ] Playwright E2E smoke test green in CI.

---

*Implementation plan (detailed step-by-step tasks, full Dockerfile, full FastAPI skeleton, docker-compose, migrations) will be produced next by the `writing-plans` skill once this design is approved.*
