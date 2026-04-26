# P1a Testing Guide

P1a backend foundation complete. This guide walks you through verifying it
end-to-end. Two paths:

1. **Automated** (recommended): one shell script does everything.
2. **Manual**: run each step yourself for visibility.

---

## Prerequisites

You need these on your local machine:

- **Docker Desktop** (Windows/Mac) or **docker + compose plugin** (Linux), running.
- **Python 3** (any 3.11+ — the script only uses stdlib + `secrets`/`json`).
- **curl** (built into git-bash and most shells).
- **bash** (git-bash works; Windows cmd / PowerShell don't).

That's it. The API itself runs **inside** containers with Python 3.11 — your
host Python doesn't matter.

If `docker info` works without errors, you're good.

---

## Path 1 — Automated test (one command)

```bash
cd E:/cloude-phone   # or wherever you cloned the repo
git fetch origin
git checkout claude/serene-khorana-a5447d   # the P1a branch

bash scripts/p1a/test-stack.sh
```

The script will:

1. Verify Docker is running.
2. Auto-generate `.env` if missing (JWT/stream secrets + libsodium keypair).
3. `docker compose up -d --build` — pulls postgres:16 + redis:7-alpine, builds the API image (~2-3 min on first run).
4. Wait for postgres + redis healthchecks.
5. `alembic upgrade head` — applies migration 0001 (and 0002 if extension is in your branch).
6. `python scripts/seed_profiles.py` — inserts 6 public device profiles.
7. `python scripts/make_invite.py --role admin --ttl-hours 1` — mints an admin invite.
8. Wait for `/healthz`.
9. `POST /auth/redeem-invite` — creates the user.
10. `GET /me` — verifies role=admin.
11. `GET /device-profiles` — verifies 6 rows seeded.
12. `POST /devices` — creates a stub device (worker stub flips it to running in ~2s).
13. Polls until `state=running`.
14. `GET /devices/{id}/adb-info` — verifies host/port returned.
15. `GET /devices/{id}/stream-token` — verifies HMAC token format.
16. `POST /auth/refresh` — rotates token; verifies single-use (second use returns 401).

**Expected final output:**

```
════════════════════════════════════════════════
  ALL CHECKS GREEN — P1a stack works end-to-end
════════════════════════════════════════════════

  • API:        http://localhost:8000
  • Docs:       http://localhost:8000/api/docs
  • Postgres:   localhost:5432 (cloude / changeme_local_dev / cloude)
  • Redis:      localhost:6379

  Login creds:
    email:    admin-test-1234567890@example.com
    password: test-password-1234567890

  Cleanup: docker compose down -v
```

If anything fails, the script prints which step + the error. Common failures:

| Failure | Fix |
|---|---|
| `Docker not found` / `daemon not running` | Start Docker Desktop. |
| Image build fails on `argon2-cffi` | Probably ARM Mac without buildx. Try `docker compose build --pull api`. |
| `docker compose exec` hangs | Service didn't come up healthy. Check `docker compose logs api worker`. |
| `Could not parse invite token` | Check `docker compose logs api`. Probably DATABASE_URL points wrong (must use `postgres` host inside container, not `localhost`). |

---

## Path 2 — Manual (one step at a time)

For when you want to see each piece work independently.

### 1. Configure secrets

```bash
cp .env.example .env
nano .env   # or your preferred editor
```

Fill in:
- `PROXY_HOST/PORT/USER/PASS` (P0 leftover — not used by P1a but kept for compatibility)
- Run these to fill the P1a secrets:
  ```bash
  python -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))" >> .env
  python -c "import secrets;print('STREAM_TOKEN_SECRET=' + secrets.token_urlsafe(64))" >> .env
  ```

For `ENCRYPTION_PUBLIC_KEY` / `ENCRYPTION_PRIVATE_KEY`, generate once Docker is up:
```bash
docker compose run --rm api python -m cloude_api.core.encryption keygen >> .env
```

(Or use the automated script's logic to generate them via host Python with pynacl.)

### 2. Bring stack up

```bash
docker compose up -d --build
docker compose ps
```

Expected: `postgres`, `redis`, `api`, `worker` — all `Up (healthy)` or `running`.

### 3. Apply migrations

```bash
docker compose exec api alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema` (and `0002` if the extension migration is in your branch).

Verify schema:
```bash
docker exec -it cloude-postgres psql -U cloude -d cloude -c "\dt"
```

Expected tables: `users`, `invites`, `device_profiles`, `proxies`, `devices`, `sessions`, `audit_log`, plus `snapshots` and `device_files` if extension applied.

### 4. Seed profiles

```bash
docker compose exec api python scripts/seed_profiles.py
```

Expected: 6 `add: ...` lines (or `skip (exists)` on rerun).

### 5. Mint an invite

```bash
docker compose exec api python scripts/make_invite.py --role admin --ttl-hours 24
```

Output prints the **raw token** in the middle. Copy it.

### 6. Redeem the invite

```bash
TOKEN="paste-the-token-here"
curl -fsS -X POST http://localhost:8000/api/v1/auth/redeem-invite \
  -H "content-type: application/json" \
  -d "{\"token\":\"$TOKEN\",\"email\":\"you@example.com\",\"password\":\"choose-strong-pw\"}"
```

Expected: `{"access":"eyJ...","refresh":"eyJ...","token_type":"bearer"}`. Copy the `access` token.

### 7. Verify auth

```bash
ACCESS="paste-the-access-here"
curl -fsS http://localhost:8000/api/v1/me -H "authorization: Bearer $ACCESS"
```

Expected: `{"id":"...","email":"you@example.com","role":"admin","quota_instances":3,...}`.

### 8. List profiles + create a device

```bash
curl -fsS http://localhost:8000/api/v1/device-profiles \
  -H "authorization: Bearer $ACCESS" | python -m json.tool

# Pick the first profile ID:
PROFILE_ID=$(curl -fsS http://localhost:8000/api/v1/device-profiles \
  -H "authorization: Bearer $ACCESS" \
  | python -c "import json,sys;print(json.load(sys.stdin)[0]['id'])")

# Create a device:
curl -fsS -X POST http://localhost:8000/api/v1/devices \
  -H "authorization: Bearer $ACCESS" \
  -H "content-type: application/json" \
  -d "{\"name\":\"smoke-test\",\"profile_id\":\"$PROFILE_ID\"}"
```

Expected: `{"id":"...","name":"smoke-test","state":"creating",...}`.

### 9. Watch worker flip state

```bash
sleep 4
curl -fsS http://localhost:8000/api/v1/devices \
  -H "authorization: Bearer $ACCESS" | python -m json.tool
```

Expected: device row now shows `"state": "running"` and `"adb_host_port"` is set
(somewhere in 40000–49999 range).

If still `creating` after 10 seconds:
```bash
docker compose logs worker
```

You should see `create_device_stub start ... done` lines.

---

## Endpoints to play with

Open <http://localhost:8000/api/docs> for the auto-generated Swagger UI. All
endpoints are listed there with example payloads.

Available endpoints:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/healthz` | no | liveness |
| POST | `/api/v1/auth/login` | no | email + password → token pair |
| POST | `/api/v1/auth/refresh` | no | refresh → new token pair (single-use) |
| POST | `/api/v1/auth/redeem-invite` | no | invite token + email + password → user + tokens |
| GET | `/api/v1/me` | bearer | current user |
| GET | `/api/v1/device-profiles` | bearer | list profiles |
| POST | `/api/v1/proxies` | bearer | create proxy (password encrypted) |
| GET | `/api/v1/proxies` | bearer | list mine |
| DELETE | `/api/v1/proxies/{id}` | bearer | delete |
| POST | `/api/v1/devices` | bearer | create device (worker spawns) |
| GET | `/api/v1/devices` | bearer | list mine |
| GET | `/api/v1/devices/{id}` | bearer | detail |
| POST | `/api/v1/devices/{id}/start` | bearer | restart stopped device |
| POST | `/api/v1/devices/{id}/stop` | bearer | stop running |
| DELETE | `/api/v1/devices/{id}` | bearer | soft delete |
| GET | `/api/v1/devices/{id}/adb-info` | bearer | adb connect host/port |
| GET | `/api/v1/devices/{id}/stream-token` | bearer | HMAC token for WS |
| WS | `/ws/devices/{id}/status?token=<access>` | query token | live state push |

---

## Cleanup

```bash
docker compose down       # stops, keeps volumes
docker compose down -v    # stops + drops postgres data + redis data
```

---

## Limitations of P1a (intentional)

These are **stubs** that get real implementations in P1b:

- **No actual Android.** `create_device_stub` just sleeps 2s and flips state. No
  redroid container is spawned. `redroid_container_id` is a fake string.
- **`adb-info` returns `localhost:<random_port>`** but nothing is listening there.
- **No browser stream.** `/ws/devices/{id}/stream` doesn't exist yet (only `/status`).
- **No frontend.** All testing is via curl / Swagger UI.
- **No idle reaper / GC cron.** Devices live forever until you delete.

These are **all by design** — P1a's goal is to prove the auth + DB + worker
queue + WS pubsub plumbing works without coupling to docker-in-docker spawn
complexity. P1b replaces the stub with the real Docker SDK flow.

---

## What's next

If P1a tests green, the next phase is:

- **P1b** — real Docker SDK device spawn (replaces stub), ws-scrcpy bridge
  for browser streaming, minimal Next.js frontend (login, create, list,
  stream). Plan to be written.
- **P1c** — snapshot/clone subsystem, IP rotation, APK install, file transfer,
  panel features.
- **P1d** — daily-life image variant (Google Play), S3 backup, admin features.

See the upgrade design spec:
[`docs/superpowers/specs/2026-04-26-cloud-android-platform-upgrade-design.md`](superpowers/specs/2026-04-26-cloud-android-platform-upgrade-design.md).
