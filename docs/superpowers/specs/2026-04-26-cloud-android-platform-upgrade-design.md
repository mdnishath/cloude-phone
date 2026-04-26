# Cloud Android Platform — Upgrade Design Spec

**Date:** 2026-04-26
**Status:** Draft — pending user review
**Builds on:** [`2026-04-20-cloud-android-platform-design.md`](2026-04-20-cloud-android-platform-design.md)
**Scope of this doc:** Pivot from pure-QA platform to **dual-mode (QA + daily-life) hybrid**, plus the new subsystems that pivot requires (snapshots, clone, image variants, IP rotation, APK install, file transfer, full-functional panel). Phases P1a (existing), P1b, P1c, P1d.

> **How to read this document.** It does **not** replace the 2026-04-20 design — it amends and extends it. Sections cite the original by number (§N). Where a section here contradicts the original, **this document wins**. Where this document is silent, the original applies.

---

## 1. Positioning Change

### 1.1 What changed
The original spec (§1) positioned this as a pure QA platform: ephemeral Android instances for app testing, geo testing, automation. Daily-life use was excluded.

The upgrade re-positions this as a **dual-mode hybrid**:
- **QA mode** — vanilla Android, no Google services, ephemeral-by-default. Same as original spec. Use cases: app testing, geo testing, automation.
- **Daily-life mode** — Android with Google Play, persistent across reboots, snapshot-protected, sticky IP. Use case: a "second phone in the cloud" — for the operator and invited users.

The infrastructure runs **both modes side-by-side** on the same VPS. Image variant is selected at create time per phone.

### 1.2 Goals (additive)
On top of the original goals (§1):
- Persistent /data with manual + auto snapshots, restore, clone (§5–6 below).
- Google Play Services available on daily-life phones (§7).
- Sticky IP per phone with manual rotate (§8).
- APK install + file transfer from the panel (§9).
- A full-functional admin panel (§10).
- Optional offsite backup to S3/B2 (§5, P1d).

### 1.3 Non-goals (unchanged + reinforced)
Original §16 stays. Specifically still excluded:
- ❌ Detection-evasion tooling (Magisk, Shamiko, HideMyApplist, Play Integrity bypass).
- ❌ Mass Google-account workflows.
- ❌ Public signup (P1 stays invite-only; deferred to P2).
- ❌ Mobile-app dashboard, desktop client.
- ❌ Multi-region, CDN, GPU passthrough.
- ❌ Stripe/billing.

New non-goals introduced by this upgrade:
- ❌ Clipboard sync, GPS spoof, notification mirror, camera/mic relay (deferred to P2+).
- ❌ Built-in proxy-provider API integrations (Bright Data API, Smartproxy API). Manual proxy entry only in P1; integrations deferred to P2.
- ❌ IP auto-rotation on schedule. Manual rotate only.

---

## 2. Phase Map

| Phase | Goal | Status |
|---|---|---|
| P0 | 1 Redroid + sidecar pair, leak-proof, manual scrcpy | ✅ Shipped |
| **P1a** | Backend foundation (FastAPI + Postgres + Redis + worker stub + JWT auth + invite redeem) | 📝 Existing plan (`2026-04-25-p1a-backend-foundation.md`), **lightly extended** for new tables |
| **P1b** | Real Docker spawn (Docker SDK) + ws-scrcpy bridge + barebones frontend (login → create vanilla phone → list → live stream → start/stop/delete) | 🔜 New plan |
| **P1c** | Snapshot/clone subsystem + IP rotation + APK install + file transfer + panel UI for all of the above | 🔜 New plan |
| **P1d** | Daily-life image variant + offsite S3/B2 backup + admin features (invite UI, quota, audit log viewer, system metrics) | 🔜 New plan |
| P2+ | Public signup, Stripe, WebRTC streaming, clipboard sync, GPS spoof, notification mirror, camera/mic, proxy-provider API integrations | Deferred |

**Demoable point: end of P1b** — login → create → live-stream a vanilla phone end-to-end. P1c and P1d incrementally enrich.

---

## 3. Architecture Diff

The original §3 architecture stays. This section shows what's *added*.

```
                    ┌────────────────────────────────┐
                    │     PUBLIC INTERNET (TLS)       │
                    └───────────────┬────────────────┘
                          ┌─────────▼──────────┐
                          │   Caddy (edge)      │
                          └─────────┬──────────┘
        ┌─────────────────┬────────┴─────────┬─────────────────┐
   ┌────▼────┐    ┌───────▼───────┐   ┌──────▼──────┐   ┌──────▼──────┐
   │ Next.js │    │ FastAPI ctrl  │   │ ws-scrcpy   │   │ device-shell │
   │ panel   │◄──►│ plane + auth  │◄─►│ bridge      │   │ -proxy (RPC) │ ← NEW (P1c)
   └─────────┘    └──┬─────────┬──┘   └─────────────┘   └─────┬───────┘
                                                              │ docker.sock
                     │         │
              ┌──────▼──┐  ┌───▼────┐
              │Postgres │  │ Redis  │
              └─────────┘  └───┬────┘
                               │
                  ┌────────────▼─────────────┐
                  │   arq worker             │
                  │ ┌──────────────────────┐ │
                  │ │ spawn / stop / delete│ │
                  │ │ snapshot / restore   │ │ ← NEW (P1c)
                  │ │ clone                │ │ ← NEW (P1c)
                  │ │ ip-rotate            │ │ ← NEW (P1c)
                  │ │ apk-install / file   │ │ ← NEW (P1c)
                  │ │ backup-to-s3         │ │ ← NEW (P1d)
                  │ │ daily-snapshot-cron  │ │ ← NEW (P1d)
                  │ └──────────────────────┘ │
                  └────────┬─────────────────┘
                           │
       ┌───────────────────┼─────────────────────────────────┐
       │ DATA PLANE: per-phone pairs (vanilla OR daily-life) │
       ▼                                                      ▼
┌────────────────────────────────────────────────────────────────┐
│ netns: device-{uuid}                                            │
│ ┌──────────────────────────┐    ┌─────────────────────────────┐│
│ │ redroid-{uuid}            │    │ sidecar-{uuid}              ││
│ │   image:                  │◄──►│   redsocks + dnscrypt       ││
│ │   - vanilla:11            │    │   sticky session ID          ││
│ │   - daily:11+gapps+ndk    │    │   IP-rotate via SIGHUP      ││
│ │ /data volume              │    │                             ││
│ └──────────────────────────┘    └─────────────────────────────┘│
│ Snapshots: /var/lib/cloude-phone/snapshots/{device}/{ts}.tar.zst│
│ Optional offsite: S3/B2 (P1d)                                    │
└────────────────────────────────────────────────────────────────┘
```

### 3.1 Net-new components / responsibilities

1. **`device-shell-proxy` service** — small internal-only HTTP+WS service introduced in P1c. Runs in its own container with the Docker socket mounted (the API server still does NOT mount `/var/run/docker.sock` directly). Exposes a narrow RPC surface on the private docker network only:
   - `POST /exec` — run an ADB command against `sidecar-{uuid}`, return parsed/JSON output (used for fast ops: file listing, ip probe).
   - `POST /push` — receive bytes + push via ADB to `{phone_path}` (used for APK install, file push). Drives `device_files` row updates.
   - `GET /pull?device=&path=` — stream bytes via ADB pull (used for file pull → API forwards stream to user).
   - Auth: shared HMAC token in `Authorization` header, both API and worker sign requests with the same secret.
   - This isolates Docker-socket capability from the public-facing API server.
2. **Worker job types** — extended catalog: snapshot, restore, clone, ip-rotate, apk-install, file-push, backup-to-s3, daily-snapshot-cron. Worker still has its own Docker socket (it spawns containers); calls `device-shell-proxy` only for ADB ops to keep that knowledge centralized.
3. **Daily-life image build** — `docker/redroid-daily/Dockerfile` (built locally on VPS, OpenGApps + libndk_translation downloaded by build script).
4. **Snapshot storage** — local: `/var/lib/cloude-phone/snapshots/{device_id}/{snapshot_id}.tar.zst`. Optional offsite: S3/B2 (P1d).

### 3.2 Components NOT changed
Caddy, Postgres, Redis, ws-scrcpy bridge, sidecar (proxy egress) all unchanged from §3 of the original. Sidecar Dockerfile gets one new feature in P1c (SIGHUP-based redsocks reload — see §8).

---

## 4. Data Model Additions

Original §4 schema stays. The following columns and tables are added.

### 4.1 `devices` — new columns

| column | type | notes |
|---|---|---|
| `image_variant` | ENUM(`vanilla`, `daily`) DEFAULT `vanilla` | which redroid image to spawn |
| `current_session_id` | TEXT NULLABLE | sticky proxy session ID, rotated on demand |
| `last_known_ip` | INET NULLABLE | last seen egress IP (cached, refreshed on boot + rotate) |
| `last_known_country` | TEXT NULLABLE | ISO-2 country code |
| `tags` | TEXT[] DEFAULT '{}' | user labels for grouping/filtering |
| `auto_snapshot_enabled` | BOOL DEFAULT FALSE | true by default for `daily` variant, false for `vanilla` |

### 4.2 `snapshots` — NEW table

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `device_id` | UUID → devices.id ON DELETE CASCADE | |
| `user_id` | UUID → users.id | for audit + per-user disk quota |
| `name` | TEXT | user-given OR auto: `daily-2026-04-26T03-00Z` / `pre-restore-{ts}` |
| `kind` | ENUM(`manual`, `auto`, `pre-restore`) | |
| `size_bytes` | BIGINT | compressed tar.zst size |
| `local_path` | TEXT | abs path on host |
| `s3_key` | TEXT NULLABLE | populated if uploaded to offsite (P1d) |
| `state` | ENUM(`creating`, `ready`, `error`, `deleted`) | |
| `error_msg` | TEXT NULLABLE | populated when state=error |
| `created_at` | TIMESTAMPTZ | |

Indexes: `(device_id, created_at DESC)`, `(state)` partial WHERE `state='creating'` (stuck reaper).

### 4.3 `invites` — NEW table (was implied; now explicit)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `token` | TEXT UNIQUE | random 32-byte URL-safe string |
| `created_by` | UUID → users.id | admin who minted |
| `email` | TEXT NULLABLE | optional pre-bind |
| `quota_instances` | INT | quota the redeemed user gets |
| `expires_at` | TIMESTAMPTZ | default 7d |
| `redeemed_by` | UUID → users.id NULLABLE | |
| `redeemed_at` | TIMESTAMPTZ NULLABLE | |
| `created_at` | TIMESTAMPTZ | |

### 4.4 `device_files` — NEW table (audit only, not file storage)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `device_id` | UUID → devices.id ON DELETE CASCADE | |
| `user_id` | UUID → users.id | |
| `op` | ENUM(`apk_install`, `file_push`, `file_pull`) | |
| `filename` | TEXT | |
| `phone_path` | TEXT NULLABLE | for push/pull |
| `size_bytes` | BIGINT | |
| `state` | ENUM(`pending`, `running`, `done`, `error`) | |
| `error_msg` | TEXT NULLABLE | |
| `created_at` | TIMESTAMPTZ | |
| `completed_at` | TIMESTAMPTZ NULLABLE | |

### 4.5 `proxies` — new column

| column | type | notes |
|---|---|---|
| `session_username_template` | TEXT DEFAULT `'{user}-session-{session}'` | how to build sticky session login (Bright Data: `{user}-session-{session}`; others vary) |
| `supports_rotation` | BOOL DEFAULT TRUE | UI hides "Rotate IP" button when false |

### 4.6 `users` — new column (P1d)

| column | type | notes |
|---|---|---|
| `s3_backup_config` | JSONB NULLABLE | `{endpoint, bucket, access_key, secret_key_encrypted}`; populated when user enables offsite backup |
| `disk_quota_bytes` | BIGINT DEFAULT 50_000_000_000 | per-user snapshot+upload quota (50 GB default) |

---

## 5. New API Surface

Base path `/api/v1`, auth via `Authorization: Bearer <jwt>`. All async ops return `202 { "id": ..., "state": "pending" }` and emit WS events on the relevant device channel.

### 5.1 Snapshots (P1c)

| Method | Path | Purpose |
|---|---|---|
| POST | `/devices/{id}/snapshots` | body: `{ name?, mode?: "quiesce"\|"live" }` (default quiesce). Async. |
| GET | `/devices/{id}/snapshots` | list snapshots for this device |
| GET | `/snapshots/{id}` | detail |
| POST | `/snapshots/{id}/restore` | async; auto-takes pre-restore snapshot first |
| POST | `/snapshots/{id}/upload-to-s3` | offsite upload (P1d) |
| DELETE | `/snapshots/{id}` | delete local (and S3 if uploaded) |

### 5.2 Clone (P1c)

| Method | Path | Purpose |
|---|---|---|
| POST | `/devices/{id}/clone` | body: `{ name, profile_id?, proxy_id? }`. Async. Source quiesced briefly. |

### 5.3 IP rotation (P1c)

| Method | Path | Purpose |
|---|---|---|
| POST | `/devices/{id}/rotate-ip` | async; ~3-5s connection drop |
| GET | `/devices/{id}/ip-info` | `{ current_ip, country, session_id, last_rotated_at, history: [...last 10] }` |

### 5.4 APK install + files (P1c)

| Method | Path | Purpose |
|---|---|---|
| POST | `/devices/{id}/apk` | multipart, max 200 MB. Async. |
| POST | `/devices/{id}/files/push` | multipart, max 500 MB. Body: `{ phone_path, file }`. Async. |
| GET | `/devices/{id}/files/pull?path=...` | streamed download |
| GET | `/devices/{id}/files?path=...` | list directory contents |
| GET | `/devices/{id}/files/operations` | list `device_files` rows for this phone |

### 5.5 Admin (P1d)

| Method | Path | Purpose |
|---|---|---|
| POST | `/admin/invites` | mint invite |
| GET | `/admin/invites` | list (pending/redeemed/expired) |
| DELETE | `/admin/invites/{id}` | revoke unredeemed |
| GET | `/admin/users` | list + quota |
| PATCH | `/admin/users/{id}` | edit quota / role / disk_quota_bytes |
| GET | `/admin/audit?user_id=&from=&to=` | filtered audit_log |
| GET | `/admin/system` | resource utilization (CPU, RAM, disk, container count, snapshot disk usage) |

### 5.6 Account / S3 backup (P1d)

| Method | Path | Purpose |
|---|---|---|
| PUT | `/me/s3-backup` | body: `{ endpoint, bucket, access_key, secret_key }`. Encrypted server-side. |
| DELETE | `/me/s3-backup` | clear |
| GET | `/me/s3-backup` | redacted view (no secret) |

### 5.7 WebSocket events (additions)

On `/ws/devices/{id}/status` channel, additional event types:
- `snapshot.created` `snapshot.progress` `snapshot.ready` `snapshot.error`
- `restore.started` `restore.progress` `restore.completed` `restore.error`
- `clone.started` `clone.completed` (with new device id)
- `ip.rotated` (with new ip + country)
- `apk.install.started` `apk.install.completed` `apk.install.error`
- `file.push.progress` `file.push.completed`

---

## 6. Snapshot / Restore / Clone Subsystem

### 6.1 Snapshot creation flow (`snapshot_device` worker job)

1. Read device row; resolve volume name `device-{uuid}-data`.
2. Decide quiesce vs live:
   - Manual snapshot: user choice, default **quiesce**.
   - Auto daily snapshot: always **live** (no downtime).
3. If quiesce: `docker stop redroid-{uuid}` (sidecar stays — no IP churn).
4. Run helper container:
   ```bash
   docker run --rm \
     -v device-{uuid}-data:/src:ro \
     -v /var/lib/cloude-phone/snapshots/{device}:/dst \
     alpine:3.20 \
     sh -c 'tar -cf - -C /src . | zstd -19 -T0 > /dst/{snapshot_id}.tar.zst'
   ```
5. Update `snapshots` row: `size_bytes`, `state=ready`, push WS event.
6. If quiesced: `docker start redroid-{uuid}`. Wait `boot_completed`.
7. If user has S3 enabled and `kind=manual` (auto snapshots upload via separate cron): enqueue `upload_snapshot_to_s3`.
8. Audit log entry.

### 6.2 Restore flow (`restore_snapshot` worker job)

1. **Always take a `pre-restore` auto-snapshot first** (live mode, ~30s).
2. `docker stop redroid-{uuid}`.
3. Wipe volume contents (without removing the volume itself):
   ```bash
   docker run --rm -v device-{uuid}-data:/v alpine:3.20 \
     sh -c 'rm -rf /v/* /v/.[!.]* /v/..?* 2>/dev/null || true'
   ```
4. Restore:
   ```bash
   docker run --rm \
     -v device-{uuid}-data:/dst \
     -v /var/lib/cloude-phone/snapshots/{device}:/src:ro \
     alpine:3.20 \
     sh -c 'apk add --no-cache zstd && zstd -d < /src/{id}.tar.zst | tar -xf - -C /dst'
   ```
5. `docker start redroid-{uuid}`. Wait `boot_completed`.
6. Push WS `restore.completed`. Audit log.

### 6.3 Clone flow (`clone_device` worker job)

1. Take **live snapshot** of source device (no source downtime, < 30s).
2. INSERT new `devices` row (state=`creating`, new UUID, new name, same profile, same proxy by default but NEW `current_session_id`).
3. Allocate new ADB host port from 40000–49999 free pool.
4. Spawn **new sidecar** for clone with new session ID.
5. Create new Docker volume `device-{new_uuid}-data`.
6. Restore the snapshot taken in step 1 into the new volume (same restore command path).
7. Spawn new redroid against new sidecar's network namespace + new volume.
8. Wait `boot_completed`.
9. Probe new IP, update `last_known_ip` + `last_known_country`.
10. State → `running`. WS event `clone.completed` with new device id.

**UX warning** at clone time: "Clone copies all apps and data, including logged-in sessions. The new phone gets a different IP." User confirms.

### 6.4 Auto-snapshot schedule (P1d)

- Cron job `daily_snapshot_all` runs at 03:00 UTC (configurable via env `AUTO_SNAPSHOT_CRON`).
- For each `state=running` device with `auto_snapshot_enabled=true`: enqueue live snapshot.
- **Retention rules** (applied per device, after each new auto snapshot completes):
  - The 4 most-recent **Sunday** auto-snapshots are tagged "weekly" and retained.
  - The 7 most-recent auto-snapshots **excluding** those already tagged "weekly" are retained as "daily".
  - Any other auto snapshot older than the above is deleted.
  - Net effect: at any time a device has at most 4 weekly + 7 daily = **11 auto snapshots** (in addition to manual + pre-restore snapshots, which are never auto-deleted).
- If user has S3 backup enabled, auto snapshots also uploaded (rate-limited to 1 concurrent S3 upload per user to avoid bandwidth saturation).

### 6.5 Storage budget

| Item | Per device | At 20 daily-life devices |
|---|---|---|
| /data volume | 4–8 GB | ~120 GB |
| Snapshot, compressed | 1–3 GB | — |
| 7 daily snapshots | — | ~280 GB |
| 4 weekly snapshots | — | ~160 GB |
| **Total snapshot disk** | — | **~440 GB** |

Within 1 TB NVMe budget. Grafana alert at 70% disk (P1d).

---

## 7. Image Variants

### 7.1 Vanilla image — `docker/redroid-vanilla/Dockerfile`

```dockerfile
# Pinned by digest in production compose.
FROM redroid/redroid:11.0.0-latest
# No customization; this is the base QA image.
LABEL org.cloudephone.variant="vanilla"
```

### 7.2 Daily-life image — `docker/redroid-daily/Dockerfile`

```dockerfile
FROM redroid/redroid:11.0.0-latest

# 1. ARM translation — most apps are ARM-only.
COPY ndk-translation-arm64/ /system/lib64/arm64/
COPY ndk-translation-arm/   /system/lib/arm/

# 2. OpenGApps pico (smallest with Play Store).
COPY opengapps-arm64-11-pico/ /system/
COPY opengapps-priv-app/      /system/priv-app/

# 3. Required props for ABI + native bridge.
RUN echo 'ro.product.cpu.abilist=arm64-v8a,armeabi-v7a,armeabi,x86_64,x86' >> /system/build.prop \
 && echo 'ro.dalvik.vm.native.bridge=libndk_translation.so'                 >> /system/build.prop

LABEL org.cloudephone.variant="daily"
```

### 7.3 Build script — `scripts/build-daily-image.sh`

Downloads OpenGApps + libndk_translation from upstream sources at build time. **NOT redistributed in this repo** (license cleanliness).

```bash
#!/usr/bin/env bash
set -euo pipefail
# 1. Download libndk_translation tarball from upstream → extract to docker/redroid-daily/ndk-translation-{arm64,arm}/
# 2. Download opengapps-arm64-11-pico zip → extract to docker/redroid-daily/opengapps-*/
# 3. docker build -t cloude-phone/redroid-daily:11.0.0-{git_sha} docker/redroid-daily/
# 4. tag :latest, push to local registry (or just keep local for single-VPS)
```

### 7.4 Image selection at create time

- Frontend wizard step "Image": two cards — Vanilla (description: "no Google Play, QA-clean, faster boot") vs Daily-life ("Google Play included, ARM apps work, persistent").
- Default: Vanilla.
- Backend writes `devices.image_variant`.
- Worker `create_device` job reads variant and uses corresponding image tag.

### 7.5 Known limitations (documented to user in UI)

- **SafetyNet / Play Integrity strict apps fail on Redroid.** Banking apps that require basicIntegrity often will not work. Documented in `/help/known-limitations` page in panel.
- **Some newer NDK apps may crash with libndk_translation.** Houdini fallback considered if reproducible; for now, document and allow user to flag broken apps via panel.
- **Daily-life image ~3 GB compressed.** First spawn slower as image pulls; subsequent spawns reuse cached image.

---

## 8. Sticky IP + Rotation

### 8.1 Sticky session at create

1. Worker generates `session_id = secrets.token_hex(16)` on create.
2. Sidecar started with env: `PROXY_SESSION_ID=<session_id>`.
3. Sidecar `entrypoint.sh` (already exists from P0) renders `redsocks.conf` from template:
   ```
   redsocks {
     login = "$(envsubst <<< $(cat /proxy_session_username_tpl))"
     password = "${PROXY_PASS}"
     ...
   }
   ```
   where `proxy_session_username_tpl` = `proxies.session_username_template` from DB (default `{user}-session-{session}`).
4. Phone boots with that sticky IP; same IP across container restarts as long as `session_id` unchanged.
5. After `boot_completed`, worker probes egress: `adb shell curl -s --max-time 10 ifconfig.me`. Updates `last_known_ip`.
6. Country lookup via local geoip2 mmdb (MaxMind GeoLite2-Country, refreshed monthly via cron). Updates `last_known_country`.

### 8.2 Manual rotate (`rotate_ip` worker job)

1. Generate new `session_id = secrets.token_hex(16)`.
2. UPDATE `devices.current_session_id`.
3. Re-render sidecar's redsocks.conf with new session ID:
   ```bash
   docker exec sidecar-{uuid} sh -c '
     export PROXY_SESSION_ID=<new>
     envsubst < /etc/redsocks/redsocks.conf.tpl > /etc/redsocks/redsocks.conf
     pkill -HUP redsocks
   '
   ```
4. Redsocks gracefully reloads on SIGHUP (open connections drop, new ones use new config). ~3–5s connection drop.
5. Re-probe IP. Update `last_known_ip`. Push WS `ip.rotated`.
6. Append rotation event to in-memory ring buffer (last 10 per device, persisted via JSON column on devices — column added in P1c migration).

### 8.3 Fallback if SIGHUP path fails
If pkill -HUP redsocks doesn't take effect within 2s, worker falls back to: `docker restart sidecar-{uuid}` (5–10s downtime instead of 3–5s). Same end state.

### 8.4 Edge cases

- **Proxy doesn't support sticky sessions** → `proxies.supports_rotation = false` set at proxy create time; "Rotate IP" button hidden.
- **Rate limit** → 1 rotation per device per minute (slowapi on the endpoint). Prevents accidental burst.

---

## 9. APK Install + File Transfer

All ADB-mediated, all routed through the `device-shell-proxy` service (§3.1) so neither the API server nor the worker has to embed `docker exec` logic in their own code. API server forwards user uploads + streams; worker enqueues long ops and observes them.

### 9.1 APK install flow

1. User drag-drops `.apk` on the panel device page; frontend POSTs `/devices/{id}/apk` (multipart, max 200 MB).
2. API:
   - Validates: ownership, `state='running'`, MIME = `application/vnd.android.package-archive`, magic bytes start with `PK\x03\x04`.
   - Persists upload to `/var/lib/cloude-phone/uploads/{user_id}/{file_uuid}.apk`. 24h TTL via cleanup cron.
   - Inserts `device_files` row (op=`apk_install`, state=`pending`).
   - Enqueues `apk_install` worker job.
   - Returns 202 `{ file_id, state: "pending" }`.
3. Worker `apk_install` job:
   - state → `running`, push WS event.
   - Calls `device-shell-proxy` `POST /push` with the APK bytes + target `/data/local/tmp/install.apk`.
   - Calls `device-shell-proxy` `POST /exec` with `adb install -r -t /data/local/tmp/install.apk` (timeout 120s).
   - On success: parse adb stdout, state=`done`, push event.
   - On failure: capture stderr to `error_msg`, state=`error`.
   - Calls `POST /exec` with `adb shell rm /data/local/tmp/install.apk` to clean up. Delete uploaded APK from host.
4. Panel shows live progress + final toast.

### 9.2 File push flow

Same shape as APK install, but the `POST /exec` call is `adb push /tmp/upload {phone_path}` (worker streams the upload bytes through `device-shell-proxy`). Phone-path validation enforced both in API (early reject) and in `device-shell-proxy` (defense in depth): must start with `/sdcard/`, `/storage/emulated/0/`, or `/data/local/tmp/`. Reject everything else, reject `..`.

### 9.3 File pull flow

Synchronous streaming via `device-shell-proxy`:

1. API endpoint validates ownership + path prefix.
2. API calls `GET /pull?device=...&path=...` on `device-shell-proxy` with HMAC-signed request; the proxy streams bytes back.
3. API forwards the body stream to the client browser, sets `Content-Disposition: attachment; filename=...`.
4. No `device_files` row for pulls under 10 MB; pulls over 10 MB written as audit row.
5. Total request timeout 10 min; no enforced max file size (streamed, no buffering).

### 9.4 File browser

- `GET /devices/{id}/files?path=/sdcard/Download` → API calls `device-shell-proxy` `POST /exec` with `adb shell ls -la --time-style=long-iso {path}`.
- `device-shell-proxy` returns parsed JSON: `[{ name, size, mtime, is_dir }, ...]` (parsing happens in the proxy, not in API).
- Frontend: simple table view, breadcrumb nav. No previews. No multi-select in P1c (defer).

### 9.5 Quotas (P1d)

- Per-user **monthly upload bandwidth**: 50 GB default. Tracked in Redis counter, reset 1st of month.
- Per-device disk usage shown in panel: `adb shell df /data` parsed and cached 60s.
- Hard limit at 90% of quota; 80% warning email.

---

## 10. Frontend Panel (Full Functional)

### 10.1 Stack

Next.js 14 App Router, React Query v5, Zustand, Tailwind v3, shadcn/ui, lucide-react icons. WebSocket hook (custom) for live status. Playwright for E2E. Vitest for components.

### 10.2 Routes

| Route | Purpose | Phase |
|---|---|---|
| `/login` | JWT login | P1b |
| `/redeem/{token}` | Invite redemption | P1b |
| `/` | Phones grid (landing) | P1b |
| `/phones/new` | Create wizard | P1b |
| `/phones/[id]` | Phone detail (tabbed) | P1b (Stream tab) → P1c (Files/APKs/Network/Snapshots) |
| `/proxies` | Proxy CRUD | P1b |
| `/snapshots` | Cross-device snapshot library | P1c |
| `/admin` | Admin (role-gated) | P1d |
| `/account` | Profile, password, S3 backup config | P1d |

### 10.3 Phones grid (`/`)

```
┌─────────────────────────────────────────────────────────────────┐
│ Cloude Phone           [+ Create Phone]   Search ▢   nishat ▾   │
├─────────────────────────────────────────────────────────────────┤
│ ╭─────────────╮ ╭─────────────╮ ╭─────────────╮ ╭─────────────╮ │
│ │ 📱 My Daily │ │ 📱 WhatsApp │ │ 🧪 QA-Pixel │ │ 📱 Banking  │ │
│ │ ●  running  │ │ ●  running  │ │ ○  stopped  │ │ ●  running  │ │
│ │ 🇧🇩 BD       │ │ 🇧🇩 BD       │ │ 🇺🇸 US       │ │ 🇧🇩 BD       │ │
│ │ daily-life  │ │ daily-life  │ │ vanilla      │ │ daily-life  │ │
│ │ 103.x.x.x   │ │ 103.x.x.x   │ │ —            │ │ 103.x.x.x   │ │
│ │ [▶ open]    │ │ [▶ open]    │ │ [▶ start]   │ │ [▶ open]    │ │
│ ╰─────────────╯ ╰─────────────╯ ╰─────────────╯ ╰─────────────╯ │
│                                                                  │
│ Tags: [all] [daily] [qa] [banking]                              │
└─────────────────────────────────────────────────────────────────┘
```

- Cards push-updated via WS (`/ws/me/devices` aggregate channel).
- Optional thumbnail polling (off by default; toggle in `/account` settings — when on, poll `GET /devices/{id}/screenshot` every 30s).
- Bulk-select toolbar appears on shift-click: Start, Stop, Snapshot, Delete.
- Tag filter chips. Tag editor on phone detail.

### 10.4 Create wizard (`/phones/new`)

- **Step 1 — Mode:** Vanilla / Daily-life (visual cards with description and warning about Play Integrity).
- **Step 2 — Profile:** dropdown of `device_profiles` (Pixel 5, Galaxy A53, etc.) + optional custom resolution toggle.
- **Step 3 — Network:** dropdown of saved proxies + "Create new" inline form. Sticky session toggle (default ON, hidden if proxy doesn't support).
- Confirm + Create → redirects to `/phones/[id]` with state=`creating`. WS shows live progress bar.

### 10.5 Phone detail (`/phones/[id]`)

Top bar: name (inline-edit), state badge, IP+flag, RAM/CPU live tiny chart, action buttons.

| Tab | Phase | Notes |
|---|---|---|
| Stream | P1b | embedded ws-scrcpy canvas, fullscreen, screenshot button |
| Files | P1c | basic browser + drag-drop upload + download links |
| APKs | P1c | drag-drop install zone, install history table |
| Network | P1c | current IP card, country flag, "Rotate IP" button (5s cooldown), rotation history |
| Snapshots | P1c | list + create/restore/delete; S3 toggle in P1d |
| Settings | P1b → P1c | rename, change proxy, tags, auto-snapshot toggle, danger-zone delete |

### 10.6 Proxies (`/proxies`)

CRUD list. Form fields: label, type (socks5/http-connect), host, port, username, password, `session_username_template` (advanced, prefilled). On save: `supports_rotation` auto-detected by attempting a session-suffixed login (best-effort; user can override).

### 10.7 Admin (`/admin`, P1d)

- **Users tab** — table (email, role, quota, active devices, last login). Click → edit quota / role / disk_quota_bytes.
- **Invites tab** — table (token-prefix, created_by, created_at, status, expires_at). [+ Mint invite] button.
- **System tab** — gauges: CPU, RAM, disk, container count, snapshot disk, instance count by state.
- **Audit tab** — filterable log viewer (user, action, target, date range, free text on `metadata`).

### 10.8 Account (`/account`, P1d)

- Profile (email — read only, password change).
- S3/B2 backup config — endpoint, bucket, access key, secret key. "Test connection" button. Stored encrypted.
- Thumbnail polling toggle.

---

## 11. Worker Job Catalog (Consolidated)

| Job | Phase | Idempotent? | Avg duration | Lock |
|---|---|---|---|---|
| `create_device` | P1b | yes (UUID-based names) | 60–90s | `device:{id}` |
| `stop_device` | P1b | yes | 5–10s | `device:{id}` |
| `start_device` | P1b | yes | 30–60s | `device:{id}` |
| `delete_device` | P1b | yes | 10–20s | `device:{id}` |
| `snapshot_device` | P1c | yes (snapshot_id) | 10–60s | `device:{id}` |
| `restore_snapshot` | P1c | yes | 30–90s | `device:{id}` |
| `clone_device` | P1c | yes | 60–120s | `device:{id}` (source) |
| `rotate_ip` | P1c | yes | 5–10s | `device:{id}` |
| `apk_install` | P1c | yes (file_id) | 5–30s | `device:{id}` |
| `file_push` | P1c | yes | 5–60s | `device:{id}` |
| `upload_snapshot_to_s3` | P1d | yes | minutes | `snapshot:{id}` |
| `daily_snapshot_all` | P1d | yes (cron lock `cron:daily-snapshot`) | minutes | global |
| `reap_idle_sessions` | P1c | yes (cron) | seconds | global |
| `reap_stuck_states` | P1b | yes (cron) | seconds | global |
| `cleanup_stopped_volumes` | P1d | yes (cron, 7d TTL) | seconds | global |
| `cleanup_uploaded_apks` | P1c | yes (cron, 24h TTL) | seconds | global |

**Rules:**
- All jobs operating on the same `device_id` are serialized via Redis lock `lock:device:{id}` (5-min TTL, owner-checked release).
- Long jobs push WS events at milestones.
- All jobs write `audit_log` rows on completion (success or failure).

---

## 12. Security Additions

Original §11 unchanged. New concerns introduced by this upgrade:

| Concern | Mitigation |
|---|---|
| Snapshot path traversal | Paths derived from device_id + snapshot_id; never user-supplied. |
| APK upload abuse | Per-user upload bandwidth quota; uploaded APKs auto-deleted 24h after install attempt; magic-byte validation. |
| File-pull / push path traversal | Whitelist allowed phone-path prefixes (`/sdcard/`, `/storage/emulated/0/`, `/data/local/tmp/`). Reject `..`, absolute paths to `/system`, `/data/data`. |
| Daily-life image binaries (OpenGApps, libndk_translation) | NOT redistributed in repo. Build script downloads at build time from upstream. README documents this. |
| S3 backup credentials (P1d) | Per-user S3 keys encrypted with libsodium sealed box, master key from `ENCRYPTION_KEY` env. Same flow as proxy passwords. |
| Clone propagating sensitive data | Always assign new sticky session (different IP). UI warning before clone. Audit log records the clone. |
| Pre-restore safety | Restore always takes a `pre-restore` auto-snapshot first; user can undo a bad restore via that snapshot. |
| Worker job privilege | Worker runs as dedicated `cloudephone` system user (only this user has docker group). API server NEVER mounts docker socket. |
| `device-shell-proxy` privilege | Has docker socket but is bound to the internal docker network only (no public ingress); accepts only HMAC-signed requests from API or worker; whitelists allowed adb subcommands (`install`, `uninstall`, `shell ls`, `shell rm`, `push`, `pull`, `shell getprop`); rejects anything else. |
| Sidecar SIGHUP arbitrary exec via API | No — API only enqueues jobs; only worker has `docker exec` capability for spawn ops; ADB ops are mediated through `device-shell-proxy` which whitelists subcommands. |

---

## 13. Per-Phase Definition of Done

### 13.1 P1a — Backend foundation (lightly extended)

- [ ] Admin mints invite via CLI; user redeems via `POST /auth/redeem-invite`; gets JWT.
- [ ] User CRUDs proxies; password encrypted at rest.
- [ ] User POSTs `/devices` → row created `state=creating` → stub worker flips to `running` after 5s.
- [ ] CI green: ruff, mypy --strict, pytest, coverage > 70 %.
- [ ] **Schema extensions migrated empty:** `snapshots`, `invites`, `device_files` tables; `image_variant`, `current_session_id`, `last_known_ip`, `last_known_country`, `tags`, `auto_snapshot_enabled` columns on `devices`; `session_username_template`, `supports_rotation` columns on `proxies`.

### 13.2 P1b — Real spawn + minimal frontend — DoD

- [ ] Worker uses Docker SDK to spawn real Redroid + sidecar (vanilla image only).
- [ ] User creates phone via panel → reaches `running` → opens phone detail page → ws-scrcpy stream visible → can interact.
- [ ] Stop / start / delete work end-to-end.
- [ ] **5 phones running simultaneously, stable for 1 hr**.
- [ ] Single-pane Playwright E2E green: login → create → stream visible → stop.
- [ ] Sidecar retains its existing P0 leak-proof behavior under spawn-from-API.

### 13.3 P1c — Snapshots, IP rotate, APK, files — DoD

- [ ] Manual snapshot (quiesce or live) from panel works → restore works → pre-restore safety snapshot auto-created.
- [ ] Clone produces working second phone with different IP.
- [ ] IP rotate works → new IP visible in panel within 10 s; SIGHUP path used; fallback to restart works if SIGHUP fails.
- [ ] APK drag-drop installs in < 30 s for typical 50 MB APK.
- [ ] File push/pull works for files up to 500 MB (push) / unlimited streamed (pull).
- [ ] File browser shows /sdcard/ contents accurately.

### 13.4 P1d — Daily-life image, backup, admin — DoD

- [ ] Daily-life image variant builds locally on VPS via `scripts/build-daily-image.sh`.
- [ ] Daily-life phone boots → Play Store opens → user can sign in → install WhatsApp → WhatsApp launches.
- [ ] Auto daily snapshots run at 03:00 UTC → retention enforced (last 7 daily, last 4 weekly).
- [ ] S3/B2 backup uploads + restores from S3 works.
- [ ] Admin panel: invite mint+revoke, user quota edit, audit viewer, system metrics — all functional.
- [ ] **20 phones running simultaneously, stable for 24 hr**.
- [ ] Documented "known limitations" page listed in panel.

---

## 14. Risk Register Additions

Original §15 stays. New risks introduced by upgrade:

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| OpenGApps / Play Integrity blocks key apps (banking attestation) | High | Daily-life UX | Document upfront in `/help/known-limitations`; provide list of "tested working" apps; users self-test |
| Snapshot disk fills VPS | Med | Outage | Retention policy + Grafana alert at 70% disk; admin force-prune endpoint |
| libndk_translation incompatible with newer NDK apps | Med | App crashes | Document; user can flag broken apps via panel; houdini fallback considered as future task |
| Sidecar SIGHUP doesn't gracefully reload redsocks | Low | IP rotate fails | Fallback to `docker restart sidecar` (5–10s downtime); same end state |
| Clone race: source modified during snapshot | Med | Corrupt clone | Quiesce source briefly during clone snapshot phase (override default live-snapshot for clones) |
| S3 backup cost runaway (P1d) | Med | Bill shock | Per-user S3 disk quota; admin alert at 80%; user-side toggle to disable |
| OpenGApps download URL changes / disappears | Med | Build break | Mirror to internal storage on first successful build; build script falls back to mirror if upstream fails |
| Per-instance `/data` corrupted by ungraceful host shutdown | Low | Phone broken | Daily auto-snapshot serves as recovery point; user can restore |

---

## 15. Out-of-Scope Reminders

Original §16 stays. Reinforced:

- ❌ Magisk, Shamiko, HideMyApplist, Play Integrity bypass — never.
- ❌ Pre-bundled Google accounts or residential proxy provisioning.
- ❌ Mobile-app dashboard, desktop client.
- ❌ Multi-region, CDN, GPU passthrough, WebRTC streaming.
- ❌ Stripe / billing.
- ❌ Clipboard sync, GPS spoof, notification mirror, camera/mic relay (P2+).
- ❌ Built-in proxy-provider API integrations (P2+).
- ❌ IP auto-rotation on schedule (P2+).
- ❌ Snapshot diff / incremental snapshots (full-tar only in P1).
- ❌ APK store, in-panel app catalog.

---

## 16. Open Questions for Implementation Plans

These are intentionally NOT decided here; they belong to the writing-plans phase:

1. **Sidecar template hot-reload mechanism** — exact `redsocks.conf` template variables and SIGHUP handling code.
2. **OpenGApps + libndk_translation upstream URLs** — pin exact versions.
3. **WS message schema** — exact JSON shapes for each event type (status, snapshot, ip, apk, file).
4. **Frontend component tree + state slices** — Zustand stores, React Query keys.
5. **Geoip2 mmdb refresh cadence** — monthly cron details.
6. **Per-user S3 backup encryption key derivation** — KDF parameters.

---

## 17. Success Criteria (Top-Level)

The upgrade is complete when:

- [ ] One operator (admin) can manage their personal daily-life phone end-to-end via the panel: create → use Play Store → install banking/messaging apps → snapshot → IP-rotate → restore.
- [ ] Operator can mint invites; invited users can redeem and run their own (vanilla or daily-life) phones with quota enforcement.
- [ ] Snapshots survive VPS reboot. Restored snapshot produces a working phone identical to the snapshot point.
- [ ] Auto-snapshots run unattended; retention enforced; S3 offsite backup works.
- [ ] Panel meets the "full functional" bar: live stream, file browser, APK install, IP management, snapshot library, admin tools.
- [ ] 20 daily-life phones run stably for 24 hr on target VPS.
- [ ] Documented known limitations (Play Integrity, NDK compatibility, no UDP) are visible in the panel.

---

*Implementation plans for P1b, P1c, P1d (and a small extension diff to P1a) will be produced next by the `writing-plans` skill once this design is approved.*
