# P1b: Real Docker Spawn + ws-scrcpy + Minimal Frontend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `create_device_stub` with the real Docker SDK spawn flow (sidecar + redroid pair); add a ws-scrcpy bridge container that streams Android frames over WebSocket; add a barebones Next.js frontend that lets you log in, create a vanilla phone, see it in a list, and interact with it via the embedded ws-scrcpy player.

**Architecture:** The arq worker grows a `create_device` job that allocates an ADB host port from a Redis free-set, spawns the sidecar (with proxy creds rendered into env), waits for redsocks healthy, spawns redroid joining the sidecar's network namespace (`--network=container:sidecar-{uuid}`), polls `getprop sys.boot_completed`, then writes the container IDs + ADB port to the device row and publishes `state=running` to the WS channel. A new `cloude/ws-scrcpy:dev` container runs upstream `ws-scrcpy` and exposes its WS endpoint. The API server adds `/ws/devices/{id}/stream?token=<>` that validates the HMAC stream token (already in P1a) and proxies the WS frames between the browser and ws-scrcpy. The Next.js frontend uses ws-scrcpy's published JS client to render the canvas. P1b does NOT add: snapshot/clone, IP rotation, APK install, file transfer, daily-life image, admin UI — those are P1c/P1d.

**Tech Stack (additions on top of P1a):**
- `docker==7.1.0` (Docker SDK for Python) — used by worker.
- `aiodocker==0.21.0` — async wrapper for the Docker SDK (avoids blocking the asyncio loop during spawn).
- `ws-scrcpy` upstream image (pinned digest) — runs in `cloude-ws-scrcpy` container.
- Next.js 14 (App Router), React Query v5, Zustand, Tailwind v3, shadcn/ui, lucide-react.
- Playwright for E2E browser tests.

**Design reference:** [`docs/superpowers/specs/2026-04-26-cloud-android-platform-upgrade-design.md`](../specs/2026-04-26-cloud-android-platform-upgrade-design.md) §2 (Phase Map: P1b row), §3 (Architecture diff), §6.1 (`create_device` flow steps), §10.3 (Phones grid), §13.2 (P1b DoD).

**Prerequisites:**
- All P1a tasks (`2026-04-25-p1a-backend-foundation.md`) committed and tested.
- All P1a extension tasks (`2026-04-26-p1a-extension-schema.md`) committed (extra columns + tables exist in DB).
- Branch state: ahead of main with all migrations through `0002`.
- `bash scripts/p1a/test-stack.sh` passes locally.

---

## File Structure (after P1b)

```
E:\cloude-phone\
├── docker-compose.yml                              (MODIFY — add ws-scrcpy)
├── apps/
│   ├── api/                                        (MODIFY — extend worker, add stream WS)
│   │   ├── src/cloude_api/
│   │   │   ├── workers/
│   │   │   │   ├── tasks.py                        (MODIFY — replace stub with real spawn)
│   │   │   │   ├── docker_client.py                (NEW)
│   │   │   │   ├── port_allocator.py               (NEW)
│   │   │   │   ├── reapers.py                      (NEW — idle + stuck-state)
│   │   │   │   └── arq_settings.py                 (MODIFY — register reapers)
│   │   │   ├── ws/
│   │   │   │   └── stream.py                       (NEW — WS proxy to ws-scrcpy)
│   │   │   └── api/
│   │   │       └── devices.py                      (MODIFY — start/stop trigger real spawn)
│   │   └── tests/
│   │       ├── unit/
│   │       │   ├── test_port_allocator.py          (NEW)
│   │       │   └── test_reapers.py                 (NEW)
│   │       └── integration/
│   │           └── test_real_spawn.py              (NEW — gated on DOCKER=1)
│   └── web/                                        (NEW)
│       ├── package.json
│       ├── tsconfig.json
│       ├── tailwind.config.ts
│       ├── next.config.mjs
│       ├── Dockerfile
│       ├── public/
│       └── src/
│           ├── app/
│           │   ├── layout.tsx
│           │   ├── page.tsx                        (phones grid)
│           │   ├── login/page.tsx
│           │   ├── redeem/[token]/page.tsx
│           │   └── phones/
│           │       ├── new/page.tsx
│           │       └── [id]/page.tsx
│           ├── components/
│           │   ├── PhoneCard.tsx
│           │   ├── StreamCanvas.tsx
│           │   └── ...
│           ├── lib/
│           │   ├── api.ts                          (fetch wrapper)
│           │   └── auth.ts                         (token storage + refresh)
│           └── styles/
│               └── globals.css
└── docs/superpowers/plans/
    └── 2026-04-26-p1b-spawn-and-frontend.md        (this file)
```

---

## Phase A — Docker spawn replaces stub (worker side)

### Task 1: Add Docker SDK dependency + sanity import

**Files:**
- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/src/cloude_api/workers/docker_client.py`

- [ ] **Step 1:** Add deps to `[project] dependencies` in `apps/api/pyproject.toml`:

```toml
"docker==7.1.0",
"aiodocker==0.21.0",
```

- [ ] **Step 2:** Rebuild API image: `docker compose build api worker`.

- [ ] **Step 3:** Create `apps/api/src/cloude_api/workers/docker_client.py`:

```python
"""Async Docker client wrapper. One client per worker process."""
from __future__ import annotations

import aiodocker

_client: aiodocker.Docker | None = None


def get_docker() -> aiodocker.Docker:
    global _client
    if _client is None:
        _client = aiodocker.Docker()
    return _client


async def close_docker() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
```

- [ ] **Step 4:** Smoke test inside API container:

```bash
docker compose exec api python -c "import asyncio; import aiodocker; \
  async def t(): \
    d = aiodocker.Docker(); \
    info = await d.system.info(); \
    print('docker ok, kernel:', info['KernelVersion']); \
    await d.close(); \
  asyncio.run(t())"
```

Expected: `docker ok, kernel: ...`. **NOTE:** worker container needs `/var/run/docker.sock` mounted — Task 2 below.

- [ ] **Step 5:** Commit:
```bash
git add apps/api/pyproject.toml apps/api/src/cloude_api/workers/docker_client.py
git commit -m "feat(worker): aiodocker client wrapper"
```

---

### Task 2: Mount Docker socket into worker container

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1:** In `docker-compose.yml`, in the `worker:` service, add a `volumes:` section:

```yaml
  worker:
    build: ./apps/api
    image: cloude/api:dev
    container_name: cloude-worker
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
    environment:
      ...                                            # (existing — keep)
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: ["arq", "cloude_api.workers.arq_settings.WorkerSettings"]
    restart: unless-stopped
```

- [ ] **Step 2:** Recreate worker:

```bash
docker compose up -d --force-recreate worker
docker compose exec worker test -S /var/run/docker.sock && echo "socket ok"
```

Expected: `socket ok`.

- [ ] **Step 3:** Commit:
```bash
git add docker-compose.yml
git commit -m "feat(infra): mount /var/run/docker.sock into worker"
```

---

### Task 3: Port allocator (Redis SRANDMEMBER from free-set)

**Files:**
- Create: `apps/api/src/cloude_api/workers/port_allocator.py`
- Create: `apps/api/tests/unit/test_port_allocator.py`

The free-set is initialized once (lazily on first allocation) with all ports in
range 40000–49999. `allocate()` does `SRANDMEMBER` then `SREM` (atomic via Lua,
or check-then-remove with retry). `release()` does `SADD`.

- [ ] **Step 1:** Failing test:

```python
"""Tests for ADB port allocator (real Redis required)."""
from __future__ import annotations

import pytest
import redis.asyncio as aioredis

from cloude_api.workers.port_allocator import PortAllocator


@pytest.fixture
async def redis():
    r = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)
    await r.delete("adb:free", "adb:used")
    yield r
    await r.delete("adb:free", "adb:used")
    await r.aclose()


@pytest.mark.asyncio
async def test_first_allocation_initializes_pool(redis) -> None:
    a = PortAllocator(redis, low=40000, high=40005)
    p = await a.allocate()
    assert 40000 <= p <= 40005
    # Pool should contain the rest
    assert await redis.scard("adb:free") == 5


@pytest.mark.asyncio
async def test_allocations_are_unique(redis) -> None:
    a = PortAllocator(redis, low=40000, high=40005)
    seen = {await a.allocate() for _ in range(6)}
    assert len(seen) == 6


@pytest.mark.asyncio
async def test_release_returns_port(redis) -> None:
    a = PortAllocator(redis, low=40000, high=40005)
    p = await a.allocate()
    await a.release(p)
    assert await redis.sismember("adb:free", p) == 1


@pytest.mark.asyncio
async def test_pool_exhaustion_raises(redis) -> None:
    a = PortAllocator(redis, low=40000, high=40001)  # only 2 ports
    await a.allocate()
    await a.allocate()
    with pytest.raises(RuntimeError, match="exhausted"):
        await a.allocate()
```

Mark this file `pytestmark = [pytest.mark.integration, pytest.mark.asyncio]` because it touches real Redis.

- [ ] **Step 2:** Implement `apps/api/src/cloude_api/workers/port_allocator.py`:

```python
"""ADB host-port allocator backed by a Redis SET of free ports."""
from __future__ import annotations

import redis.asyncio as aioredis

_INIT_SCRIPT = """
if redis.call('SCARD', KEYS[1]) == 0 then
    for i = tonumber(ARGV[1]), tonumber(ARGV[2]) do
        redis.call('SADD', KEYS[1], i)
    end
end
local p = redis.call('SPOP', KEYS[1])
if not p then return nil end
return p
"""


class PortAllocator:
    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        low: int = 40000,
        high: int = 49999,
        free_key: str = "adb:free",
    ) -> None:
        self._redis = redis
        self._low = low
        self._high = high
        self._free_key = free_key

    async def allocate(self) -> int:
        port = await self._redis.eval(_INIT_SCRIPT, 1, self._free_key, self._low, self._high)
        if port is None:
            raise RuntimeError("ADB port pool exhausted")
        return int(port)

    async def release(self, port: int) -> None:
        await self._redis.sadd(self._free_key, port)
```

- [ ] **Step 3:** Run tests with services up:
```bash
docker compose up -d redis
cd apps/api && PYTHONPATH=src INTEGRATION=1 pytest tests/unit/test_port_allocator.py -v
```
Expected: 4 passed.

- [ ] **Step 4:** Commit:
```bash
git add apps/api/src/cloude_api/workers/port_allocator.py apps/api/tests/unit/test_port_allocator.py
git commit -m "feat(worker): Redis-backed ADB port allocator (40000-49999)"
```

---

### Task 4: Real `create_device` job (replaces stub)

**Files:**
- Modify: `apps/api/src/cloude_api/workers/tasks.py`

The new job:
1. Allocate ADB port.
2. Read device row + profile + (optional) proxy + decrypt password.
3. Compute container names from device UUID (idempotent — retries safe).
4. Render proxy env for sidecar.
5. `docker run` sidecar (named `sidecar-{uuid}`, `--cap-add=NET_ADMIN`, `-p {port}:5555`, env).
6. Wait for sidecar healthcheck up to 15 s.
7. `docker run` redroid (named `redroid-{uuid}`, `--network=container:sidecar-{uuid}`, `--privileged`, profile-specific args).
8. Poll `adb shell getprop sys.boot_completed` up to 90 s.
9. Update `devices` row: state=`running`, container IDs, port, started_at.
10. Publish `state=running` to ws channel.
11. On any failure: state=`error`, state_reason=<msg>, attempt cleanup, release port.

- [ ] **Step 1:** Replace `create_device_stub` in `apps/api/src/cloude_api/workers/tasks.py` (RENAME to `create_device` — caller in `api/devices.py` also updates).

```python
"""Background tasks. P1b real Docker SDK spawn replaces the P1a stub."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import aiodocker
import redis.asyncio as aioredis
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core.encryption import decrypt_password
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.proxy import Proxy
from cloude_api.workers.docker_client import get_docker
from cloude_api.workers.port_allocator import PortAllocator
from cloude_api.ws.pubsub import channel_for

log = logging.getLogger("cloude.worker")

SIDECAR_IMAGE = "cloude-phone/sidecar:latest"   # built by docker/sidecar (P0)
REDROID_VANILLA_IMAGE = "redroid/redroid:11.0.0-latest"


async def _publish(redis: aioredis.Redis, device_id: str, payload: dict[str, Any]) -> None:
    await redis.publish(channel_for(device_id), json.dumps(payload))


def _sidecar_name(device_id: uuid.UUID) -> str:
    return f"sidecar-{device_id.hex[:12]}"


def _redroid_name(device_id: uuid.UUID) -> str:
    return f"redroid-{device_id.hex[:12]}"


def _volume_name(device_id: uuid.UUID) -> str:
    return f"device-{device_id.hex[:12]}-data"


async def _wait_for_sidecar(docker: aiodocker.Docker, name: str, timeout: float = 15.0) -> bool:
    """Poll sidecar healthcheck status until healthy."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        c = await docker.containers.get(name)
        info = await c.show()
        health = info.get("State", {}).get("Health", {}).get("Status")
        if health == "healthy":
            return True
        await asyncio.sleep(0.5)
    return False


async def _wait_for_boot(docker: aiodocker.Docker, sidecar_name: str, timeout: float = 90.0) -> bool:
    """adb shell getprop sys.boot_completed inside sidecar netns."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        c = await docker.containers.get(sidecar_name)
        exec_inst = await c.exec(
            cmd=["adb", "-s", "localhost:5555", "shell", "getprop", "sys.boot_completed"],
            stdout=True, stderr=True,
        )
        async with exec_inst.start(detach=False) as stream:
            out = b""
            async for msg in stream:
                out += msg.data
        if b"1" in out:
            return True
        await asyncio.sleep(2.0)
    return False


async def _spawn(
    docker: aiodocker.Docker,
    device: Device,
    profile: DeviceProfile,
    proxy: Proxy | None,
    proxy_password: str | None,
    adb_port: int,
) -> tuple[str, str]:
    sidecar_name = _sidecar_name(device.id)
    redroid_name = _redroid_name(device.id)
    volume_name = _volume_name(device.id)

    # 1. Volume
    try:
        await docker.volumes.create({"Name": volume_name, "Driver": "local"})
    except aiodocker.exceptions.DockerError:
        pass  # already exists, retry-safe

    # 2. Sidecar
    sidecar_env = {
        "PROXY_HOST": proxy.host if proxy else "",
        "PROXY_PORT": str(proxy.port) if proxy else "",
        "PROXY_TYPE": proxy.type.value if proxy else "socks5",
        "PROXY_USER": proxy.username or "" if proxy else "",
        "PROXY_PASS": proxy_password or "",
        "PROXY_SESSION_ID": device.current_session_id or "",
    }
    sidecar = await docker.containers.create_or_replace(
        name=sidecar_name,
        config={
            "Image": SIDECAR_IMAGE,
            "HostConfig": {
                "CapAdd": ["NET_ADMIN"],
                "PortBindings": {"5555/tcp": [{"HostPort": str(adb_port)}]},
                "RestartPolicy": {"Name": "unless-stopped"},
            },
            "Env": [f"{k}={v}" for k, v in sidecar_env.items()],
            "ExposedPorts": {"5555/tcp": {}},
        },
    )
    await sidecar.start()
    if not await _wait_for_sidecar(docker, sidecar_name):
        raise RuntimeError(f"sidecar {sidecar_name} did not become healthy in 15s")

    # 3. Redroid
    redroid = await docker.containers.create_or_replace(
        name=redroid_name,
        config={
            "Image": REDROID_VANILLA_IMAGE,
            "HostConfig": {
                "NetworkMode": f"container:{sidecar_name}",
                "Privileged": True,
                "Memory": profile.ram_mb * 1024 * 1024,
                "NanoCpus": profile.cpu_cores * 1_000_000_000,
                "Binds": [f"{volume_name}:/data"],
                "RestartPolicy": {"Name": "unless-stopped"},
            },
            "Cmd": [
                f"androidboot.redroid_width={profile.screen_width}",
                f"androidboot.redroid_height={profile.screen_height}",
                f"androidboot.redroid_dpi={profile.screen_dpi}",
                "androidboot.redroid_gpu_mode=guest",
                f"ro.product.model={profile.model}",
                f"ro.product.manufacturer={profile.manufacturer}",
            ],
        },
    )
    await redroid.start()
    if not await _wait_for_boot(docker, sidecar_name):
        raise RuntimeError(f"redroid {redroid_name} did not boot in 90s")

    return (sidecar.id, redroid.id)


async def create_device(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """Spawn sidecar + redroid for a device. Idempotent on retry."""
    redis: aioredis.Redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)
    docker = get_docker()
    allocator = PortAllocator(ctx["redis_decoded"])
    s = get_settings()

    log.info("create_device start id=%s", device_id)

    # Read device + relations
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None or d.state != DeviceState.creating:
            log.warning("device %s missing or wrong state — no-op", device_id)
            return {"ok": True, "noop": True}
        profile = await db.scalar(select(DeviceProfile).where(DeviceProfile.id == d.profile_id))
        proxy = None
        proxy_password = None
        if d.proxy_id is not None:
            proxy = await db.scalar(select(Proxy).where(Proxy.id == d.proxy_id))
            if proxy and proxy.password_encrypted:
                proxy_password = decrypt_password(
                    proxy.password_encrypted,
                    pub_b64=s.encryption_public_key,
                    priv_b64=s.encryption_private_key,
                )

    if profile is None:
        await _fail(redis, device_id, "profile gone")
        return {"ok": False}

    adb_port = await allocator.allocate()
    try:
        sidecar_id, redroid_id = await _spawn(docker, d, profile, proxy, proxy_password, adb_port)
    except Exception as e:
        log.exception("spawn failed for %s", device_id)
        await _fail(redis, device_id, f"spawn: {e}")
        await allocator.release(adb_port)
        await _cleanup_partial(docker, device_id)
        return {"ok": False, "error": str(e)}

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None:
            return {"ok": False}
        d.state = DeviceState.running
        d.started_at = datetime.now(tz=timezone.utc)
        d.adb_host_port = adb_port
        d.sidecar_container_id = sidecar_id
        d.redroid_container_id = redroid_id
        await db.commit()

    await _publish(redis, str(device_id), {
        "device_id": str(device_id),
        "state": "running",
        "state_reason": None,
        "adb_host_port": adb_port,
    })
    log.info("create_device done id=%s port=%d", device_id, adb_port)
    return {"ok": True, "state": "running", "port": adb_port}


async def _fail(redis: aioredis.Redis, device_id: uuid.UUID, reason: str) -> None:
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is not None:
            d.state = DeviceState.error
            d.state_reason = reason
            await db.commit()
    await _publish(redis, str(device_id), {
        "device_id": str(device_id),
        "state": "error",
        "state_reason": reason,
    })


async def _cleanup_partial(docker: aiodocker.Docker, device_id: uuid.UUID) -> None:
    """Best-effort: remove any half-spawned containers."""
    for name in (_redroid_name(device_id), _sidecar_name(device_id)):
        try:
            c = await docker.containers.get(name)
            await c.delete(force=True)
        except aiodocker.exceptions.DockerError:
            pass


async def _on_startup(ctx: dict[str, Any]) -> None:
    s = get_settings()
    ctx["redis"] = aioredis.from_url(s.redis_url, encoding="utf-8", decode_responses=False)
    ctx["redis_decoded"] = aioredis.from_url(s.redis_url, encoding="utf-8", decode_responses=True)
    log.info("worker startup")


async def _on_shutdown(ctx: dict[str, Any]) -> None:
    for r in (ctx.get("redis"), ctx.get("redis_decoded")):
        if r is not None:
            await r.aclose()
    from cloude_api.workers.docker_client import close_docker
    await close_docker()
```

- [ ] **Step 2:** Update `apps/api/src/cloude_api/workers/arq_settings.py`:

```python
from cloude_api.workers.tasks import _on_shutdown, _on_startup, create_device

class WorkerSettings:
    functions = [create_device]
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 180   # increased for real spawn
```

- [ ] **Step 3:** Update `apps/api/src/cloude_api/api/devices.py` `_enqueue_create()` to enqueue `create_device` (NOT `create_device_stub`):

```python
await pool.enqueue_job("create_device", str(device_id))
```

- [ ] **Step 4:** Lint + commit:
```bash
cd apps/api && ruff check src && ruff format src
git add apps/api/src/cloude_api/workers/tasks.py apps/api/src/cloude_api/workers/arq_settings.py apps/api/src/cloude_api/api/devices.py
git commit -m "feat(worker): real Docker SDK spawn replaces create_device_stub"
```

---

### Task 5: Stop / start / delete now do real Docker ops

**Files:**
- Modify: `apps/api/src/cloude_api/workers/tasks.py` (add `stop_device`, `start_device`, `delete_device`)
- Modify: `apps/api/src/cloude_api/api/devices.py` (enqueue these jobs instead of doing inline DB-only writes)

The route handlers stop being responsible for actually stopping containers —
they enqueue a worker job and update state to `stopping` / `creating` while
the worker does the real Docker call. This matches the design's state machine
(§6.1 of design spec).

- [ ] **Step 1:** Add to `tasks.py`:

```python
async def stop_device(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)
    docker = get_docker()

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None or d.state == DeviceState.deleted:
            return {"ok": False, "reason": "missing"}

    # Stop both containers (idempotent)
    for name in (_redroid_name(device_id), _sidecar_name(device_id)):
        try:
            c = await docker.containers.get(name)
            await c.stop(t=10)
        except aiodocker.exceptions.DockerError:
            pass

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is not None:
            d.state = DeviceState.stopped
            d.stopped_at = datetime.now(tz=timezone.utc)
            await db.commit()

    await _publish(redis, str(device_id), {"device_id": str(device_id), "state": "stopped"})
    return {"ok": True}


async def delete_device(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)
    docker = get_docker()

    # 1. Stop + remove containers
    for name in (_redroid_name(device_id), _sidecar_name(device_id)):
        try:
            c = await docker.containers.get(name)
            await c.delete(force=True)
        except aiodocker.exceptions.DockerError:
            pass

    # 2. Drop volume (P1a kept devices on stop; delete is the destructive one)
    try:
        v = await docker.volumes.get(_volume_name(device_id))
        await v.delete()
    except aiodocker.exceptions.DockerError:
        pass

    # 3. Release ADB port
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is not None and d.adb_host_port is not None:
            allocator = PortAllocator(ctx["redis_decoded"])
            await allocator.release(d.adb_host_port)
            d.state = DeviceState.deleted
            d.adb_host_port = None
            d.redroid_container_id = None
            d.sidecar_container_id = None
            await db.commit()

    await _publish(redis, str(device_id), {"device_id": str(device_id), "state": "deleted"})
    return {"ok": True}
```

- [ ] **Step 2:** Register in `arq_settings.py`:

```python
from cloude_api.workers.tasks import (
    _on_shutdown, _on_startup,
    create_device, stop_device, delete_device,
)

class WorkerSettings:
    functions = [create_device, stop_device, delete_device]
    ...
```

- [ ] **Step 3:** Update `apps/api/src/cloude_api/api/devices.py` `stop_device` and `delete_device` route handlers to enqueue worker jobs and update state to `stopping` (transient) while keeping the existing API contract:

```python
@router.post("/{device_id}/stop", response_model=DevicePublic)
async def stop_device_route(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    if d.state not in (DeviceState.running, DeviceState.creating):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"cannot stop from {d.state.value}")
    d.state = DeviceState.stopping
    await write_audit(db, user_id=current.id, action="device.stop", target_id=d.id)
    await db.commit()
    await db.refresh(d)
    s = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(s.redis_url))
    try:
        await pool.enqueue_job("stop_device", str(d.id))
    finally:
        await pool.aclose()
    return DevicePublic.model_validate(d)
```

(Same shape for `delete_device_route` — enqueue + transient state.)

- [ ] **Step 4:** Commit:
```bash
git add apps/api/src/cloude_api/workers/tasks.py apps/api/src/cloude_api/workers/arq_settings.py apps/api/src/cloude_api/api/devices.py
git commit -m "feat(worker): stop_device + delete_device real Docker ops"
```

---

### Task 6: Idle session reaper (cron)

**Files:**
- Create: `apps/api/src/cloude_api/workers/reapers.py`
- Modify: `apps/api/src/cloude_api/workers/arq_settings.py`

Per design §13: stop devices with `state=running` AND no session ping in last 4h.

- [ ] **Step 1:** Implement reaper:

```python
"""Cron jobs: idle reaper, stuck-state reaper. Run on arq's cron schedule."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from arq import cron
from sqlalchemy import select

from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.models.session import Session

log = logging.getLogger("cloude.reaper")


async def reap_idle_devices(ctx: dict[str, Any]) -> int:
    """Stop devices with no recent WS ping. Runs every 5 minutes."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=4)
    stopped = 0
    async with async_session_factory() as db:
        devices = (await db.scalars(
            select(Device).where(Device.state == DeviceState.running)
        )).all()
        for d in devices:
            last_session = await db.scalar(
                select(Session)
                .where(Session.device_id == d.id)
                .order_by(Session.last_ping_at.desc())
                .limit(1)
            )
            if last_session is None or last_session.last_ping_at < cutoff:
                # Enqueue stop instead of doing it inline (avoids long DB tx)
                ctx.setdefault("_to_stop", []).append(d.id)
                stopped += 1
    log.info("reap_idle: %d devices to stop", stopped)
    # Actual enqueue happens via WorkerSettings or here — for now log count
    return stopped


async def reap_stuck_creating(ctx: dict[str, Any]) -> int:
    """Mark devices stuck in 'creating' for >5min as 'error'."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    fixed = 0
    async with async_session_factory() as db:
        devices = (await db.scalars(
            select(Device).where(
                Device.state == DeviceState.creating,
                Device.created_at < cutoff,
            )
        )).all()
        for d in devices:
            d.state = DeviceState.error
            d.state_reason = "stuck in creating"
            fixed += 1
        if fixed:
            await db.commit()
    log.info("reap_stuck_creating: %d devices marked error", fixed)
    return fixed


CRON_JOBS = [
    cron(reap_idle_devices, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    cron(reap_stuck_creating, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
]
```

- [ ] **Step 2:** Register in `arq_settings.py`:

```python
from cloude_api.workers.reapers import CRON_JOBS

class WorkerSettings:
    functions = [create_device, stop_device, delete_device]
    cron_jobs = CRON_JOBS
    ...
```

- [ ] **Step 3:** Commit:
```bash
git add apps/api/src/cloude_api/workers/reapers.py apps/api/src/cloude_api/workers/arq_settings.py
git commit -m "feat(worker): idle + stuck-state cron reapers"
```

---

## Phase B — ws-scrcpy bridge + WS proxy

### Task 7: Add ws-scrcpy service to compose

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1:** Add service:

```yaml
  ws-scrcpy:
    image: netrisn/ws-scrcpy:latest
    container_name: cloude-ws-scrcpy
    depends_on:
      api: { condition: service_started }
    environment:
      WS_SCRCPY_PORT: "8000"
    expose:
      - "8000"
    restart: unless-stopped
```

(ws-scrcpy listens on internal port 8000 — only the API container reaches it; it's NOT published to host.)

- [ ] **Step 2:** Bring up + verify:
```bash
docker compose up -d --build ws-scrcpy
docker compose exec api curl -s http://ws-scrcpy:8000 | head -3
```

Expected: HTML response from ws-scrcpy.

- [ ] **Step 3:** Commit:
```bash
git add docker-compose.yml
git commit -m "feat(infra): ws-scrcpy bridge container"
```

---

### Task 8: API `/ws/devices/{id}/stream` proxies to ws-scrcpy

**Files:**
- Create: `apps/api/src/cloude_api/ws/stream.py`
- Modify: `apps/api/src/cloude_api/main.py` (include stream router)

The endpoint:
1. Validates HMAC stream token (already in P1a `core/stream_token.py`).
2. Marks token consumed in Redis (`SETEX` 300s).
3. Looks up device's ADB info (host, port).
4. Opens a WS to `ws://ws-scrcpy:8000/?action=stream&device_id={adb_host}:{adb_port}` (ws-scrcpy's URL convention).
5. Bidirectionally proxies frames between the two WS connections.

- [ ] **Step 1:** Implement `apps/api/src/cloude_api/ws/stream.py`:

```python
"""WS /ws/devices/{id}/stream — proxies to ws-scrcpy bridge."""
from __future__ import annotations

import asyncio
import uuid

import websockets
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from cloude_api.core.deps import get_redis
from cloude_api.core.stream_token import StreamTokenError, verify
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device

router = APIRouter()
WS_SCRCPY_HOST = "ws-scrcpy"
WS_SCRCPY_PORT = 8000


@router.websocket("/ws/devices/{device_id}/stream")
async def device_stream_ws(
    ws: WebSocket, device_id: uuid.UUID, token: str = Query(...)
) -> None:
    # 1. Validate HMAC
    try:
        payload = verify(token, expected_device_id=str(device_id))
    except StreamTokenError:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Single-use enforcement
    redis = get_redis()
    nonce_key = f"stream:nonce:{payload.nonce}"
    if await redis.set(nonce_key, "1", ex=300, nx=True) is False:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. Look up device
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None or d.state != DeviceState.running or d.adb_host_port is None:
            await ws.close(code=status.WS_1011_INTERNAL_ERROR)
            return
        adb_port = d.adb_host_port

    await ws.accept()

    upstream_url = (
        f"ws://{WS_SCRCPY_HOST}:{WS_SCRCPY_PORT}"
        f"/?action=stream&udid=localhost:{adb_port}"
    )

    try:
        async with websockets.connect(upstream_url, max_size=None) as upstream:
            await asyncio.gather(
                _pump_browser_to_upstream(ws, upstream),
                _pump_upstream_to_browser(upstream, ws),
            )
    except WebSocketDisconnect:
        pass


async def _pump_browser_to_upstream(browser: WebSocket, upstream: websockets.WebSocketClientProtocol) -> None:
    try:
        while True:
            data = await browser.receive_bytes()
            await upstream.send(data)
    except WebSocketDisconnect:
        await upstream.close()


async def _pump_upstream_to_browser(upstream: websockets.WebSocketClientProtocol, browser: WebSocket) -> None:
    try:
        async for msg in upstream:
            if isinstance(msg, bytes):
                await browser.send_bytes(msg)
            else:
                await browser.send_text(msg)
    except websockets.ConnectionClosed:
        await browser.close()
```

- [ ] **Step 2:** Mount in `main.py`:

```python
from cloude_api.ws.stream import router as ws_stream_router

app.include_router(ws_stream_router)
```

- [ ] **Step 3:** Commit:
```bash
git add apps/api/src/cloude_api/ws/stream.py apps/api/src/cloude_api/main.py
git commit -m "feat(api): /ws/devices/{id}/stream proxies to ws-scrcpy"
```

---

## Phase C — Minimal Next.js frontend

### Task 9: Scaffold `apps/web/`

**Files:** see file structure above.

- [ ] **Step 1:** Initialize:

```bash
cd apps && npx create-next-app@14 web \
  --typescript --tailwind --app --no-src-dir --import-alias "@/*" \
  --use-npm
cd web
npm install @tanstack/react-query zustand lucide-react clsx tailwind-merge
npm install -D @playwright/test
```

- [ ] **Step 2:** Move source under `src/`:

```bash
mkdir src
mv app src/
mv lib src/ 2>/dev/null || true
mv components src/ 2>/dev/null || true
```

Update `tsconfig.json` baseUrl/paths and `next.config.mjs` if needed.

- [ ] **Step 3:** Commit:
```bash
git add apps/web
git commit -m "feat(web): scaffold Next.js 14 app + Tailwind + react-query + zustand"
```

---

### Task 10: Auth lib (token storage + auto-refresh)

**Files:**
- Create: `apps/web/src/lib/auth.ts`
- Create: `apps/web/src/lib/api.ts`

- [ ] **Step 1:** `apps/web/src/lib/api.ts`:

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  accessToken?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}
```

- [ ] **Step 2:** `apps/web/src/lib/auth.ts`:

```typescript
import { apiFetch } from "./api";

const ACCESS_KEY = "cloude.access";
const REFRESH_KEY = "cloude.refresh";

export interface TokenPair { access: string; refresh: string; }

export const auth = {
  save(p: TokenPair) {
    localStorage.setItem(ACCESS_KEY, p.access);
    localStorage.setItem(REFRESH_KEY, p.refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  access(): string | null { return localStorage.getItem(ACCESS_KEY); },
  refresh(): string | null { return localStorage.getItem(REFRESH_KEY); },
  async login(email: string, password: string): Promise<TokenPair> {
    const tp = await apiFetch<TokenPair>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    auth.save(tp);
    return tp;
  },
  async redeem(token: string, email: string, password: string): Promise<TokenPair> {
    const tp = await apiFetch<TokenPair>("/api/v1/auth/redeem-invite", {
      method: "POST",
      body: JSON.stringify({ token, email, password }),
    });
    auth.save(tp);
    return tp;
  },
  async refreshTokens(): Promise<TokenPair | null> {
    const r = auth.refresh();
    if (!r) return null;
    try {
      const tp = await apiFetch<TokenPair>("/api/v1/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refresh: r }),
      });
      auth.save(tp);
      return tp;
    } catch { auth.clear(); return null; }
  },
};
```

- [ ] **Step 3:** Commit:
```bash
git add apps/web/src/lib/
git commit -m "feat(web): api.ts + auth.ts (login, refresh, redeem)"
```

---

### Task 11: `/login` page

**Files:**
- Create: `apps/web/src/app/login/page.tsx`

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/auth";

export default function Login() {
  const r = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);

  return (
    <main className="min-h-screen grid place-items-center bg-zinc-950 text-zinc-100">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setErr(null);
          try { await auth.login(email, password); r.push("/"); }
          catch (e: any) { setErr(e.message); }
        }}
        className="w-80 space-y-4 p-6 bg-zinc-900 rounded-lg border border-zinc-800"
      >
        <h1 className="text-2xl font-semibold">Cloude Phone</h1>
        <input value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder="email" type="email"
          className="w-full px-3 py-2 bg-zinc-800 rounded" />
        <input value={password} onChange={(e) => setPassword(e.target.value)}
          placeholder="password" type="password"
          className="w-full px-3 py-2 bg-zinc-800 rounded" />
        <button className="w-full py-2 bg-blue-600 hover:bg-blue-500 rounded">Sign in</button>
        {err && <p className="text-red-400 text-sm">{err}</p>}
      </form>
    </main>
  );
}
```

- [ ] **Commit:**
```bash
git add apps/web/src/app/login
git commit -m "feat(web): /login page"
```

---

### Task 12: `/redeem/[token]` page

Same shape as login but uses `auth.redeem()` and a `token` from URL params.

- [ ] **Files:** `apps/web/src/app/redeem/[token]/page.tsx` — analogous to login, three inputs (token prefilled, email, password), call `auth.redeem(token, email, password)`, redirect to `/`.

- [ ] **Commit** with `feat(web): /redeem/[token] page`.

---

### Task 13: Phones grid `/`

**Files:**
- Create: `apps/web/src/app/page.tsx`
- Create: `apps/web/src/components/PhoneCard.tsx`

Use react-query to poll `GET /api/v1/devices` every 5s. Render cards with name, state badge, country flag (use `last_known_country` if present), `[+ Create]` CTA.

- [ ] **Files written, commit:** `feat(web): phones grid + PhoneCard`.

---

### Task 14: Create wizard `/phones/new`

3-step wizard (image variant — for now only "Vanilla" since daily-life is P1d, profile picker, network/proxy picker), POST to `/api/v1/devices`, redirect to `/phones/[id]`.

- [ ] **Commit:** `feat(web): /phones/new create wizard`.

---

### Task 15: Phone detail `/phones/[id]` — Stream tab

**Files:**
- Create: `apps/web/src/app/phones/[id]/page.tsx`
- Create: `apps/web/src/components/StreamCanvas.tsx`

`StreamCanvas`:
1. Calls `GET /api/v1/devices/{id}/stream-token` to fetch a fresh HMAC token.
2. Opens WS to `ws://localhost:8000/ws/devices/{id}/stream?token=<...>`.
3. Renders frames into a `<canvas>` (use ws-scrcpy's published JS client — see https://github.com/NetrisTV/ws-scrcpy README). Embed via `<script>` tag from a CDN or vendor the client.

- [ ] **Commit:** `feat(web): phone detail with embedded ws-scrcpy stream`.

---

### Task 16: Web Dockerfile + compose service

**Files:**
- Create: `apps/web/Dockerfile`
- Modify: `docker-compose.yml`

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
EXPOSE 3000
CMD ["npm", "start"]
```

```yaml
  web:
    build: ./apps/web
    image: cloude/web:dev
    container_name: cloude-web
    environment:
      NEXT_PUBLIC_API_BASE: ${PUBLIC_API_BASE:-http://localhost:8000}
    ports:
      - "3000:3000"
    depends_on:
      api: { condition: service_started }
    restart: unless-stopped
```

- [ ] **Commit:** `feat(infra): web service in compose`.

---

## Phase D — E2E + tests

### Task 17: Playwright E2E

**Files:**
- Create: `apps/web/e2e/login-and-stream.spec.ts`

The single E2E:
1. `await page.goto("/login")`
2. Fill credentials (created by a fixture that mints+redeems an invite via API).
3. Assert redirect to `/`.
4. Click "Create Phone", complete wizard.
5. Wait for state transition `creating → running` (poll every 1s, max 90s).
6. Click into device.
7. Assert `<canvas>` renders (frames received).

- [ ] **Commit:** `test(web): playwright e2e login → create → stream`.

---

### Task 18: P1b closeout

- [ ] Update `README.md` with P1b quick start.
- [ ] Run all unit + integration tests + lint + types.
- [ ] Tag `p1b-complete`.
- [ ] Update `scripts/p1a/test-stack.sh` → `scripts/p1b/test-stack.sh` that adds the real-spawn assertions (waits for an actual `redroid-{uuid}` container in `docker ps`, hits `adb shell echo` through the sidecar's port, etc.).

---

## Definition of Done (P1b)

- [ ] `docker compose up -d --build` brings up postgres, redis, api, worker, ws-scrcpy, web — all healthy.
- [ ] User logs into web UI, creates a vanilla phone, watches state transition, sees the device's home screen in the browser via embedded ws-scrcpy.
- [ ] User can stop and delete the device; containers and volumes are cleaned up; ADB port returns to free pool.
- [ ] Idle reaper auto-stops a device with no WS pings for 4h.
- [ ] Stuck-state reaper marks `creating > 5min` as `error`.
- [ ] 5 phones running simultaneously, stable for 1 hr (no OOM, no port collisions, all reachable).
- [ ] Playwright E2E green in CI.
- [ ] No regressions on P1a unit tests.

---

## Out of scope (deferred to P1c / P1d)

- ❌ Snapshot / clone / restore — P1c.
- ❌ IP rotation — P1c.
- ❌ APK install / file transfer / file browser — P1c.
- ❌ Daily-life image variant (Google Play, libndk_translation) — P1d.
- ❌ S3 / B2 offsite backup — P1d.
- ❌ Admin UI (invite mint, user list, audit viewer, system metrics) — P1d.
- ❌ device-shell-proxy service — P1c.
- ❌ Tags + bulk actions in panel — P1c.
- ❌ Rich error envelope details, retry UI flows — P1c.
- ❌ WebRTC streaming — P2+.

---

## Risks specific to P1b

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Redroid kernel module (`binder_linux`) missing on dev host | High on Mac/Windows Docker | Spawn fails | Document Linux-only requirement; ARM Mac may need `--privileged` + binfmt; falls back to "spawn fails clean with state=error, state_reason='binder module missing'". |
| ws-scrcpy upstream image breaks on update | Med | Stream broken | Pin digest in compose; document upgrade flow. |
| Docker SDK race: two workers spawn the same device on retry | Low (single worker for now) | Duplicate containers | Idempotent container names from device UUID + `create_or_replace` semantics. |
| ADB port pool gets out of sync with reality | Med | Allocation fails or collides | Reaper job (P1c) reconciles `adb:free` set with actual `docker ps` output weekly. |
| WS proxy back-pressure | Med | Stream lag | `max_size=None` on websockets connect; rely on TCP backpressure for now. WebRTC P2+ replaces this. |
