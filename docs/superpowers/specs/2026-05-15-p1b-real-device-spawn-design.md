# P1b — Real Device Spawn (Design)

**Status:** Approved (brainstorm complete; awaiting user review of spec before plan).
**Replaces:** the `create_device_stub` worker task introduced in P1a Task 22.
**Depends on:** P0 (validated sidecar image + Redroid working on host) and P1a (FastAPI control plane, ORM models, arq worker scaffold).

## Goal

Replace the P1a `create_device_stub` arq task with a real Docker-driven spawn flow that brings up one **sidecar** + **redroid** container pair per device row, identical in behavior to the manual `scripts/p0/spawn-pair.sh` flow but driven from inside the worker via the async Docker SDK. After P1b, `POST /api/v1/devices` results in an actually-running Android instance whose ADB endpoint is reachable from the host, network egress goes through the user's selected proxy, and apps/data installed inside Android persist across stop/start.

P1b stops there. No UI changes (that's [P1c](#future-phases-out-of-scope-for-p1b)), no in-browser streaming (P1d), no idle reaper, no 7-day GC, no multi-host scheduling. Stuck-state reaper IS in scope — it's required to make spawn-failure recovery work without manual DB editing.

## Non-goals (deliberately deferred)

- **Idle reaper.** Stopping running-but-inactive devices on session timeout. P2.
- **7-day GC.** Hard-deleting old `state=stopped` rows + their volumes. P2.
- **No-proxy device mode.** P1b requires every device to have a `proxy_id`; the existing sidecar entrypoint requires `PROXY_HOST/PORT/TYPE` env. Add passthrough-mode to the sidecar later. P2.
- **Multi-host capacity scheduling.** P1b assumes one Docker daemon per worker; no spread-across-hosts logic.
- **Host capacity pre-check.** No "host out of RAM" rejection at create time. Quota is enforced via `users.quota_instances` (already in P1a). Docker's own OOM kill is the safety net if a user finds a way past quota.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ Worker process (apps/api/.../workers/tasks.py)                 │
│                                                                │
│  arq job: create_device(device_id)         (NEW)               │
│  arq job: stop_device(device_id)           (NEW)               │
│  arq job: delete_device(device_id)         (NEW)               │
│  arq cron: _reap_stuck_devices (every 60s) (NEW)               │
│                                                                │
│  Shared deps from ctx:                                         │
│    ctx["docker"]: aiodocker.Docker                             │
│    ctx["redis"]:  redis.asyncio.Redis                          │
└──┬──────────────────────────────┬──────────────────────────────┘
   │                              │
   ▼                              ▼
┌────────────────┐         ┌─────────────────────────────┐
│ Postgres       │         │ Redis                       │
│   devices      │         │  adb:ports:free  (SET)      │
│   audit_log    │         │  ws:device:{id}  (PUB/SUB)  │
└────────────────┘         └─────────────────────────────┘
   │                              │
   └──────┐               ┌───────┘
          ▼               ▼
   ┌──────────────────────────────┐
   │ Docker daemon                │
   │   per-device:                │
   │     cloude-sidecar-<short>   │
   │     cloude-redroid-<short>   │
   │     cloude-data-<uuid> (vol) │
   └──────────────────────────────┘
```

The HTTP layer (`apps/api/.../api/devices.py`) is untouched except for one schema-level change: `DeviceCreate.proxy_id` becomes required. State transitions (`creating → running`, etc.) still happen exclusively in the worker — the route enqueues, the worker mutates. Pub/sub fan-out to `ws:device:{id}` matches the P1a contract so the existing `/ws/devices/{id}/status` endpoint keeps working without change.

### Module layout

New files:
```
apps/api/src/cloude_api/workers/
  ├── docker_client.py     # aiodocker singleton, on_startup/shutdown wiring
  ├── port_allocator.py    # Redis-backed ADB port pool
  ├── spawner.py           # create_device + helpers (split from tasks.py so tasks stays slim)
  ├── lifecycle.py         # stop_device, delete_device, tear_down helpers
  └── reapers.py           # _reap_stuck_devices cron
apps/api/tests/unit/
  ├── test_port_allocator.py
  └── test_spawner_logic.py    # pure-logic bits (name rendering, label match, error paths with mocks)
apps/api/tests/integration/
  └── test_real_spawn.py        # full spawn → boot → adb → stop → delete (gated on REAL_DOCKER=1 + binder host)
```

Modified files:
```
apps/api/src/cloude_api/workers/tasks.py         # remove create_device_stub, add 3 new tasks
apps/api/src/cloude_api/workers/arq_settings.py  # register new functions + cron
apps/api/src/cloude_api/schemas/device.py        # DeviceCreate.proxy_id → required UUID
apps/api/src/cloude_api/api/devices.py           # change enqueue target from "create_device_stub" → "create_device"
apps/api/pyproject.toml                          # +aiodocker==0.21.0
```

The split (`spawner.py` + `lifecycle.py` + `reapers.py` separate from `tasks.py`) is so the arq-facing entrypoints stay focused on signature + transaction boundaries, while the actual logic lives in normal pure-async functions that are easier to test in isolation.

## Spawn flow (the meat)

`create_device(ctx, device_id_str: str) -> dict` — called by the API enqueue.

```
load row:
  d = SELECT * FROM devices WHERE id = device_id
  if d is None: return {"ok": False, "reason": "device_missing"}
  if d.state != creating: return {"ok": True, "noop": True, "state": d.state}
  profile = d.profile (eager-loaded or SELECT)
  proxy   = d.proxy   (REQUIRED — if proxy_id NULL: state=error("no proxy"), return)
  proxy_password = decrypt_password(proxy.password_encrypted, pub_b64, priv_b64) if proxy.password_encrypted else ""

allocate port:
  port = await port_allocator.acquire(redis)
  if port is None:
    state = error("port pool exhausted")
    publish, return

render names:
  short = device_id.hex[:12]
  sidecar_name  = f"cloude-sidecar-{short}"
  redroid_name  = f"cloude-redroid-{short}"
  volume_name   = f"cloude-data-{device_id}"          # full uuid for uniqueness
  labels        = {"cloude.device_id": str(device_id)}

try:
  await docker.volumes.create({"Name": volume_name})    # idempotent: 409 → ok

  await spawn_sidecar(
    docker, name=sidecar_name, image=SIDECAR_IMAGE,
    adb_port=port,
    proxy_host=proxy.host, proxy_port=proxy.port, proxy_type=proxy.type.value,
    proxy_user=proxy.username or "", proxy_pass=proxy_password,
    labels=labels | {"cloude.role": "sidecar"},
  )

  await wait_for_sidecar_healthy(docker, sidecar_name, timeout=20s)

  await spawn_redroid(
    docker, name=redroid_name, image=REDROID_IMAGE,
    sidecar_name=sidecar_name, volume=volume_name,
    width=profile.screen_width, height=profile.screen_height, dpi=profile.screen_dpi,
    ram_mb=profile.ram_mb, cpus=profile.cpu_cores,
    model=profile.model, manufacturer=profile.manufacturer,
    labels=labels | {"cloude.role": "redroid"},
  )

  await wait_for_boot_completed(docker, redroid_name, timeout=120s)

  d.state                  = running
  d.started_at             = now()
  d.adb_host_port          = port
  d.sidecar_container_id   = short_id(sidecar_container)
  d.redroid_container_id   = short_id(redroid_container)
  d.state_reason           = None
  commit
  publish_status(d)
  return {"ok": True, "state": "running"}

except SpawnError as e:
  await tear_down(docker, sidecar_name, redroid_name, remove_volume=False)
  await port_allocator.release(redis, port)
  d.state = error
  d.state_reason = str(e)
  commit
  publish_status(d)
  return {"ok": False, "reason": str(e)}
```

`SpawnError` is the one exception class spawn helpers raise; anything else propagates and arq logs+retries (we let arq do up to 1 retry on unexpected errors so transient Docker daemon hiccups self-heal; explicit `SpawnError` is non-retryable).

### Sidecar spawn (aiodocker call)

```python
await docker.containers.run(
    name=sidecar_name,
    config={
        "Image": SIDECAR_IMAGE,        # "cloude/sidecar:p0"
        "Labels": labels,
        "Env": [
            f"PROXY_HOST={proxy_host}",
            f"PROXY_PORT={proxy_port}",
            f"PROXY_TYPE={proxy_type}",
            f"PROXY_USER={proxy_user}",
            f"PROXY_PASS={proxy_pass}",
        ],
        "HostConfig": {
            "CapAdd": ["NET_ADMIN", "NET_RAW"],
            "Sysctls": {"net.ipv4.ip_forward": "1"},
            "PortBindings": {"5555/tcp": [{"HostPort": str(adb_port)}]},
            "RestartPolicy": {"Name": "no"},
        },
        "ExposedPorts": {"5555/tcp": {}},
    },
)
```

### Redroid spawn

```python
runtime_args = [
    f"androidboot.redroid_width={width}",
    f"androidboot.redroid_height={height}",
    f"androidboot.redroid_dpi={dpi}",
    "androidboot.redroid_gpu_mode=guest",
    f"ro.product.model={model}",
    f"ro.product.manufacturer={manufacturer}",
    "net.dns1=127.0.0.1",
    "net.dns2=127.0.0.1",
]
await docker.containers.run(
    name=redroid_name,
    config={
        "Image": REDROID_IMAGE,        # "redroid/redroid:11.0.0-latest"
        "Cmd": runtime_args,
        "Labels": labels,
        "HostConfig": {
            "NetworkMode": f"container:{sidecar_name}",
            "Privileged": True,
            "Memory": ram_mb * 1024 * 1024,
            "CpuCount": cpus,                              # Windows-equivalent of --cpus
            "Binds": [f"{volume}:/data"],
            "RestartPolicy": {"Name": "no"},
        },
    },
)
```

### Wait helpers

- `wait_for_sidecar_healthy`: poll `docker exec sidecar pgrep redsocks` every 1s up to 20s; raise `SpawnError("sidecar redsocks did not start")` on timeout.
- `wait_for_boot_completed`: poll `docker exec redroid getprop sys.boot_completed` every 2s up to 120s; expects exact output `1\n`; raise `SpawnError("android boot did not complete within 120s")` on timeout. Also abort early if container has exited (`State.Status == "exited"`).

Both poll with cheap `exec_create + exec_start` calls; no shell parsing beyond exact-string match.

## Port allocator

Public API (in `workers/port_allocator.py`):

```python
PORT_POOL_MIN = 40000
PORT_POOL_MAX = 49999
PORT_SET_KEY  = "adb:ports:free"

async def initialize(redis, db) -> None:
    """On worker startup. Idempotent."""

async def acquire(redis) -> int | None:
    """SPOP one port. Returns None if pool empty."""

async def release(redis, port: int) -> None:
    """SADD port back to the free-set. No-op if already present (atomic SADD)."""
```

`initialize` is the only nuanced piece:

```
if redis.EXISTS(PORT_SET_KEY):
    # already populated by a prior worker
    pass
else:
    # cold start: seed full range, then remove ports already claimed by live devices
    SADD adb:ports:free 40000 40001 ... 49999

# Reconcile from DB on every startup (idempotent — handles crash recovery):
claimed = SELECT adb_host_port FROM devices
          WHERE state IN ('running','creating') AND adb_host_port IS NOT NULL
SREM adb:ports:free <claimed...>
```

Reconcile-on-every-startup means a worker crash mid-spawn that left a row in `creating` with a port assigned won't double-allocate that port on restart. The stuck-state reaper (§next) is what eventually frees it.

## Stuck-state reaper

`_reap_stuck_devices` runs every 60s as an arq cron job. Pseudocode:

```
threshold = now() - 3 minutes
stuck = SELECT * FROM devices
        WHERE state='creating' AND created_at < threshold
for d in stuck:
    short = d.id.hex[:12]
    await tear_down(docker, f"cloude-sidecar-{short}", f"cloude-redroid-{short}", remove_volume=False)
    if d.adb_host_port:
        await port_allocator.release(redis, d.adb_host_port)
    d.state         = error
    d.state_reason  = "spawn timeout (stuck in 'creating' > 3 min)"
    d.adb_host_port = None
    commit
    publish_status(d)
```

Three minutes is a comfortable upper bound: boot timeout is 120s, plus 20s for sidecar, plus margin. A device legitimately mid-boot at 2:55 never gets reaped; one whose worker crashed at second 5 gets fixed within the next minute.

On worker startup we also do a one-shot orphan scan:

```
SELECT * FROM devices WHERE state IN ('running','creating')
for d in rows:
    if not container_exists(docker, label="cloude.device_id="+d.id) for either role:
        d.state = error
        d.state_reason = "containers missing after worker restart"
        release port if held
        publish
```

This catches "worker died, then host rebooted, containers gone" — the device row is stale and we surface it as `error` so the user can `start` it again.

## Stop / delete

```python
async def stop_device(ctx, device_id_str: str) -> dict:
    d = load_device(device_id)
    if d.state not in (running, creating, error):
        return {"ok": True, "noop": True}
    await graceful_stop(docker, sidecar_name(d), timeout=10)
    await graceful_stop(docker, redroid_name(d), timeout=10)
    if d.adb_host_port:
        await port_allocator.release(redis, d.adb_host_port)
    d.state          = stopped
    d.stopped_at     = now()
    d.adb_host_port  = None
    commit
    publish_status(d)

async def delete_device(ctx, device_id_str: str) -> dict:
    d = load_device(device_id)
    if d.state not in (stopped, error, deleted):
        await stop_device(ctx, device_id_str)
        d = reload(device_id)
    await tear_down(docker, sidecar_name(d), redroid_name(d), remove_volume=True)
    d.state = deleted
    commit
    publish_status(d)
```

`tear_down` is best-effort: `docker rm -f` ignores "no such container", `docker volume rm` only when `remove_volume=True` and ignores "no such volume". It never raises — the worst-case outcome is leftover Docker resources, which the eventual `delete_device` (or manual cleanup) handles.

`graceful_stop` issues `container.stop(timeout=10)` then `container.delete(force=True)`. We DELETE the container after stop (not just stop) so name collisions don't happen on next `start` — the volume is the persistence boundary, not the container.

### API integration

The two existing routes need to enqueue the new tasks:

- `POST /api/v1/devices` (create) → enqueue `create_device` (was `create_device_stub`)
- `POST /api/v1/devices/{id}/start` → enqueue `create_device` (reuses spawn flow, volume is reused so apps persist)
- `POST /api/v1/devices/{id}/stop` → ALSO enqueue `stop_device` (currently the route directly mutates state and skips the worker; that needs to change because actual `docker stop` lives in the worker now). The route flips state to `stopping` and enqueues; the worker does the docker work and flips to `stopped`. New intermediate state value: `stopping` already exists in the `DeviceState` enum (P1a Task 2) so no migration needed.
- `DELETE /api/v1/devices/{id}` → enqueue `delete_device`. Route flips state to a transient (we use `stopping` for both — state machine is simple enough that we don't need a separate "deleting"; the worker flips to `deleted` at the end).

This means the API stays sync-fast and the worker does the slow work, matching the P1a design intent.

## Error handling philosophy

1. **Every spawn step is wrapped.** Failure raises `SpawnError(reason: str)` — never bubbles raw exceptions.
2. **Cleanup on failure is best-effort.** `docker rm -f` ignored on 404, no exceptions out of tear-down.
3. **Volumes are sticky.** A failed spawn leaves the volume so a retry (via `start`) reuses the disk state. Volume is only removed by explicit `delete_device`.
4. **No arq auto-retry on SpawnError.** It's a user-facing error; show it. arq's built-in retry only fires on unexpected exceptions (network blip talking to Docker daemon, redis briefly down).
5. **State is always the source of truth.** No "in-flight" job tracking outside the DB — if the row says `creating`, exactly one spawn job is in flight or stuck (the reaper catches the stuck case).
6. **Audit log on every transition.** `device.spawn_failed`, `device.stop`, `device.delete` actions written via `core.audit.write_audit` with `metadata` containing the failure reason.

## Schema / API changes (no DB migration)

`apps/api/src/cloude_api/schemas/device.py`:

```diff
 class DeviceCreate(BaseModel):
     name: str = Field(min_length=1, max_length=120)
     profile_id: uuid.UUID
-    proxy_id: uuid.UUID | None = None
+    proxy_id: uuid.UUID
```

That's the entire API contract change. DB schema stays — `devices.proxy_id` remains nullable (rows from P1a integration tests may exist with NULL, which is fine; only NEW creates require proxy).

The Pydantic schema change is a breaking API change vs P1a's behavior. Documented in the P1b changelog/README update.

## Dependencies

Add to `apps/api/pyproject.toml` `[project] dependencies`:
```toml
"aiodocker==0.21.0",
```
This needs a fresh `pip install -e ".[dev]"` and a rebuilt Docker image. Both are mechanical.

## Testing strategy

Two tiers:

### Unit tests (run everywhere, including CI)

- `test_port_allocator.py`
  - `initialize` seeds full range on cold key
  - `initialize` is idempotent (running twice doesn't double-seed)
  - `initialize` removes ports claimed by `state in (running, creating)` rows
  - `acquire` returns an integer in [40000, 49999] from a populated set
  - `acquire` returns None when set is empty
  - `release` puts the port back; `acquire` can re-claim it
- `test_spawner_logic.py`
  - Name + label rendering helpers
  - `tear_down` ignores 404 on container/volume
  - `wait_for_sidecar_healthy` raises after timeout with `SpawnError` (mock docker exec returns no match)
  - SpawnError propagation: spawn flow catches → state=error, port released (use mocked aiodocker)

CI keeps running on ubuntu-22.04 which doesn't have binder/redroid, but unit tests are pure-Python with mocks so all of P1b unit suite runs in CI alongside the P1a tests.

### Integration test (gated; runs locally on your WSL2)

`tests/integration/test_real_spawn.py`, gated on env var `REAL_DOCKER=1`. The existing P1a integration test (`test_e2e_invite_to_running.py`) uses the stub; this new one exercises the actual flow:

```
1. Mint invite + redeem (reusing helpers from the P1a integration test).
2. Seed a profile + proxy (using a known-working proxy from .env — same one P0 validated).
3. POST /api/v1/devices → state=creating.
4. Wait for state=running (poll DB up to 180s).
5. Assert adb_host_port set, redroid_container_id non-null.
6. `docker exec` into redroid and assert getprop sys.boot_completed==1 (sanity).
7. (Optional) ADB connect localhost:{port} and assert `adb shell echo hi` works.
8. POST /api/v1/devices/{id}/stop → wait for state=stopped, port released.
9. POST /api/v1/devices/{id}/start → wait for state=running, /data preserved (write a marker file in step 6, assert it's there after restart).
10. DELETE /api/v1/devices/{id} → state=deleted, both containers gone, volume gone.
```

This test takes ~3-4 minutes in real time. It only runs locally on your WSL2; CI skips it because the runner can't spawn redroid.

The P1a `test_e2e_invite_to_running` integration test that exercises the stub stays — renamed conceptually to "the worker contract test" (uses `create_device` task directly, but with a stub redis pubsub + a flag to skip the real Docker calls). Spec-wise this means we don't delete coverage when removing the stub; we re-use the flow at a smaller scope. Implementation detail: split the spawn flow's "DB transition + pubsub" part into a function the existing test can keep calling directly.

## Out of scope for P1b — captured for future phases

- **Idle reaper.** When `sessions.last_ping_at` for a device's most recent session is > N minutes (default 30 in prod, configurable per-user), stop the device. P2 because P1d hasn't been built — there are no sessions to track yet.
- **7-day stopped GC.** Hard-delete `state=stopped` devices older than 7 days. P2.
- **Host capacity pre-check.** Reject create when host RAM/CPU is insufficient. P2.
- **Multi-host worker.** One Docker daemon assumption holds; sharding workers across hosts comes with P2's multi-tenant goals.
- **No-proxy device mode.** Add `--passthrough` flag to sidecar entrypoint that skips redsocks but keeps DNS guarding; relax `DeviceCreate.proxy_id` back to optional. P2.

## Completion criteria

P1b is done when:
1. `aiodocker` added to deps; image rebuilds clean.
2. `create_device`, `stop_device`, `delete_device` arq tasks implemented in `workers/` (with the module split above).
3. Port allocator with `initialize` / `acquire` / `release`, reconciled from DB on every worker startup.
4. Stuck-state reaper as a 60s arq cron, plus orphan-scan at worker startup.
5. `DeviceCreate.proxy_id` is required; existing `/api/v1/devices` routes enqueue the new tasks (including `/stop` and `DELETE`).
6. Old `create_device_stub` removed; arq registration updated.
7. Unit test suite for port allocator + spawner-logic green (CI).
8. Integration test for full real-spawn flow green locally on WSL2 with `REAL_DOCKER=1` and a working proxy.
9. `ruff check`, `ruff format --check`, `mypy --strict` clean.
10. Manual smoke from the user: create device via Swagger, see Android boot, `adb connect localhost:<port>` works, `scrcpy -s localhost:<port>` shows the home screen.
11. README updated with the "P1b status" line and a note that `DeviceCreate.proxy_id` is now required.
12. Git tag `p1b-complete` cut once everything's green.

## Open question (for your call)

None — all earlier brainstorming questions resolved:
- Functional level: full end-to-end ✅
- Host: local WSL2 (P0 already validated there) ✅
- Order: P1b → P1c → P1d ✅
- Persistence: per-device volume ✅
- Reapers: stuck-state only ✅

Any new question that surfaces during writing-plans will be raised explicitly there.
