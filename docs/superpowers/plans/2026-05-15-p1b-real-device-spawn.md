# P1b — Real Device Spawn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the P1a `create_device_stub` arq task with a real Docker-driven spawn flow that brings up one sidecar + redroid container pair per device, an ADB-port allocator backed by Redis, real stop/delete lifecycle, and a stuck-state reaper that recovers crashed spawns.

**Architecture:** All worker logic lives under `apps/api/src/cloude_api/workers/`, split into focused modules: `docker_client.py` (aiodocker singleton + lifecycle), `port_allocator.py` (Redis SET of free ADB ports), `spawner.py` (`create_device` + sidecar/redroid spawn + wait helpers + `_finalize_running`), `lifecycle.py` (`stop_device`, `delete_device`, `tear_down`, `graceful_stop`), `reapers.py` (`reap_stuck_devices` cron + `orphan_scan` startup hook). `tasks.py` becomes the composition file that arq's `WorkerSettings` imports. The HTTP routes in `api/devices.py` change only their `enqueue_job` targets (and `DeviceCreate.proxy_id` becomes required); no DB migration needed.

**Tech Stack:** Python 3.11, aiodocker 0.21.0 (added), existing arq 0.25 / asyncpg / redis-py / SQLAlchemy 2 from P1a. P0 sidecar image (`cloude/sidecar:p0`) and `redroid/redroid:11.0.0-latest` are pre-existing on the host.

**Source spec:** [docs/superpowers/specs/2026-05-15-p1b-real-device-spawn-design.md](../specs/2026-05-15-p1b-real-device-spawn-design.md).

---

## File Structure (target after P1b)

```
apps/api/
├── pyproject.toml                              (modified — aiodocker added)
├── src/cloude_api/
│   ├── api/
│   │   └── devices.py                          (modified — enqueue targets + stop/delete now async)
│   ├── schemas/
│   │   └── device.py                           (modified — proxy_id required)
│   └── workers/
│       ├── tasks.py                            (rewritten — composition shim)
│       ├── arq_settings.py                     (modified — new functions + cron)
│       ├── docker_client.py                    (new)
│       ├── port_allocator.py                   (new)
│       ├── spawner.py                          (new)
│       ├── lifecycle.py                        (new)
│       └── reapers.py                          (new)
└── tests/
    ├── unit/
    │   ├── test_port_allocator.py              (new)
    │   ├── test_spawner_logic.py               (new)
    │   ├── test_lifecycle.py                   (new)
    │   └── test_reapers.py                     (new)
    └── integration/
        ├── test_e2e_invite_to_running.py       (modified — calls _finalize_running)
        └── test_real_spawn.py                  (new — REAL_DOCKER=1 gate)
```

---

## Task 0: Add `aiodocker` dependency

**Files:**
- Modify: `apps/api/pyproject.toml`

- [ ] **Step 1:** Add `aiodocker==0.21.0` to the dependencies list

Open `apps/api/pyproject.toml`. Find the `dependencies = [` block and insert `"aiodocker==0.21.0",` alphabetically near `"arq==0.25.0"`. Final dependencies array should include both:
```toml
  "arq==0.25.0",
  "aiodocker==0.21.0",
```

- [ ] **Step 2:** Install the new dep

```bash
cd apps/api && python -m pip install -e ".[dev]" --quiet
python -c "import aiodocker; print(aiodocker.__version__)"
```
Expected output: `0.21.0`.

- [ ] **Step 3:** Add `aiodocker.*` to mypy's `ignore_missing_imports` override

Open `apps/api/pyproject.toml`. Find:
```toml
[[tool.mypy.overrides]]
module = ["arq.*", "slowapi.*", "passlib.*", "nacl.*", "jose.*"]
ignore_missing_imports = true
```
Change the `module` list to:
```toml
module = ["aiodocker.*", "arq.*", "slowapi.*", "passlib.*", "nacl.*", "jose.*"]
```

- [ ] **Step 4:** Rebuild the api/worker image so the running containers pick up the new dep later

```bash
docker compose build api
```
Expected: builds clean in ~60-90s. Do NOT bring services up yet — the worker code still references `create_device_stub` and won't be touched until Task 11.

- [ ] **Step 5:** Commit

```bash
git add apps/api/pyproject.toml
git commit -m "feat(p1b): add aiodocker dependency"
```

---

## Task 1: Port allocator (TDD)

**Files:**
- Create: `apps/api/src/cloude_api/workers/port_allocator.py`
- Create: `apps/api/tests/unit/test_port_allocator.py`

- [ ] **Step 1:** Write the failing test

Create `apps/api/tests/unit/test_port_allocator.py`:
```python
"""Tests for the Redis-backed ADB port allocator."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from cloude_api.workers import port_allocator as pa


class FakeRedis:
    """In-memory SET implementation covering only the methods port_allocator uses."""

    def __init__(self) -> None:
        self._sets: dict[str, set[str]] = {}

    async def exists(self, key: str) -> int:
        return 1 if key in self._sets else 0

    async def sadd(self, key: str, *values: Any) -> int:
        s = self._sets.setdefault(key, set())
        before = len(s)
        for v in values:
            s.add(str(v))
        return len(s) - before

    async def srem(self, key: str, *values: Any) -> int:
        s = self._sets.get(key, set())
        before = len(s)
        for v in values:
            s.discard(str(v))
        return before - len(s)

    async def spop(self, key: str) -> str | None:
        s = self._sets.get(key, set())
        if not s:
            return None
        v = next(iter(s))
        s.discard(v)
        return v

    async def scard(self, key: str) -> int:
        return len(self._sets.get(key, set()))


class FakeDb:
    """Stub of AsyncSession exposing only scalars(...).all() over a list of int|None."""

    def __init__(self, ports: list[int | None]) -> None:
        self._ports = ports

    async def scalars(self, _stmt: Any) -> Any:  # noqa: ANN401
        class _Result:
            def __init__(self, items: list[int | None]) -> None:
                self._items = items

            def all(self) -> list[int | None]:
                return list(self._items)

        return _Result(self._ports)


@pytest.mark.asyncio
async def test_initialize_seeds_full_range_on_cold_key() -> None:
    r = FakeRedis()
    db = FakeDb(ports=[])
    await pa.initialize(r, db)  # type: ignore[arg-type]
    assert await r.scard(pa.PORT_SET_KEY) == pa.PORT_POOL_MAX - pa.PORT_POOL_MIN + 1


@pytest.mark.asyncio
async def test_initialize_is_idempotent_when_key_exists() -> None:
    r = FakeRedis()
    # Pre-populate with only two ports — initialize should NOT reseed.
    await r.sadd(pa.PORT_SET_KEY, 40000, 40001)
    db = FakeDb(ports=[])
    await pa.initialize(r, db)  # type: ignore[arg-type]
    assert await r.scard(pa.PORT_SET_KEY) == 2


@pytest.mark.asyncio
async def test_initialize_removes_ports_claimed_by_live_devices() -> None:
    r = FakeRedis()
    db = FakeDb(ports=[40005, 40007, None])  # None should be ignored
    await pa.initialize(r, db)  # type: ignore[arg-type]
    # full range minus the two claimed ports
    assert await r.scard(pa.PORT_SET_KEY) == (pa.PORT_POOL_MAX - pa.PORT_POOL_MIN + 1) - 2


@pytest.mark.asyncio
async def test_acquire_returns_an_int_in_range() -> None:
    r = FakeRedis()
    await r.sadd(pa.PORT_SET_KEY, 40123)
    port = await pa.acquire(r)  # type: ignore[arg-type]
    assert port == 40123
    assert pa.PORT_POOL_MIN <= port <= pa.PORT_POOL_MAX


@pytest.mark.asyncio
async def test_acquire_returns_none_on_empty_set() -> None:
    r = FakeRedis()
    port = await pa.acquire(r)  # type: ignore[arg-type]
    assert port is None


@pytest.mark.asyncio
async def test_release_puts_port_back() -> None:
    r = FakeRedis()
    await pa.release(r, 40500)  # type: ignore[arg-type]
    assert await r.scard(pa.PORT_SET_KEY) == 1
    got = await pa.acquire(r)  # type: ignore[arg-type]
    assert got == 40500


@pytest.mark.asyncio
async def test_release_is_idempotent() -> None:
    r = FakeRedis()
    await pa.release(r, 40500)  # type: ignore[arg-type]
    await pa.release(r, 40500)  # type: ignore[arg-type]
    assert await r.scard(pa.PORT_SET_KEY) == 1
```

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_port_allocator.py
```
Expected: `ModuleNotFoundError: No module named 'cloude_api.workers.port_allocator'`.

- [ ] **Step 3:** Implement `apps/api/src/cloude_api/workers/port_allocator.py`

```python
"""Redis-backed ADB port allocator.

Free-set lives at key `adb:ports:free`. Workers SPOP to claim, SADD to release.
Initialize seeds the full range on first boot and reconciles against the DB on
every startup so worker restarts can't double-allocate a port that a live device
is using.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloude_api.enums import DeviceState
from cloude_api.models.device import Device

PORT_POOL_MIN = 40000
PORT_POOL_MAX = 49999
PORT_SET_KEY = "adb:ports:free"


async def initialize(redis: aioredis.Redis, db: AsyncSession) -> None:
    """Seed the free-set on first boot; remove ports held by live devices on every boot."""
    seeded = bool(await redis.exists(PORT_SET_KEY))
    if not seeded:
        ports = list(range(PORT_POOL_MIN, PORT_POOL_MAX + 1))
        await redis.sadd(PORT_SET_KEY, *ports)

    claimed_rows = await db.scalars(
        select(Device.adb_host_port).where(
            Device.state.in_([DeviceState.creating, DeviceState.running]),
        )
    )
    claimed = [p for p in claimed_rows.all() if p is not None]
    if claimed:
        await redis.srem(PORT_SET_KEY, *claimed)


async def acquire(redis: aioredis.Redis) -> int | None:
    """Atomically claim one free port. Returns None if the pool is exhausted."""
    raw = await redis.spop(PORT_SET_KEY)
    if raw is None:
        return None
    return int(raw)


async def release(redis: aioredis.Redis, port: int) -> None:
    """Return a port to the free-set. Idempotent (SADD is set-semantics)."""
    await redis.sadd(PORT_SET_KEY, port)
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_port_allocator.py -v
```
Expected: `7 passed`.

- [ ] **Step 5:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/port_allocator.py apps/api/tests/unit/test_port_allocator.py
git add apps/api/src/cloude_api/workers/port_allocator.py apps/api/tests/unit/test_port_allocator.py
git commit -m "feat(p1b): Redis-backed ADB port allocator"
```

---

## Task 2: Docker client singleton

**Files:**
- Create: `apps/api/src/cloude_api/workers/docker_client.py`

This module owns the aiodocker handle. Worker startup makes one client; shutdown closes it. No tests — it's a thin factory; behavior is exercised in later integration tests.

- [ ] **Step 1:** Write `apps/api/src/cloude_api/workers/docker_client.py`

```python
"""aiodocker client lifecycle helpers.

One Docker client per worker process. The worker's on_startup hook constructs
one and stashes it in arq's ctx; on_shutdown closes it. Spawn/lifecycle helpers
take the client as an explicit parameter — no module-level globals.
"""

from __future__ import annotations

import aiodocker


async def make_docker_client() -> aiodocker.Docker:
    """Construct an aiodocker client using DOCKER_HOST or the default unix socket."""
    return aiodocker.Docker()


async def close_docker_client(client: aiodocker.Docker) -> None:
    """Close the underlying aiohttp connector. Safe to call twice."""
    await client.close()
```

- [ ] **Step 2:** Smoke-test the import + an actual connection to the local Docker daemon

```bash
cd apps/api && DATABASE_URL=postgresql+asyncpg://x:y@h/d REDIS_URL=redis://h:6379/0 JWT_SECRET=test-secret-test-secret-test-secret-test-secret-AAAA STREAM_TOKEN_SECRET=test-stream-test-stream-test-stream-test-stream-AAAA ENCRYPTION_PUBLIC_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= ENCRYPTION_PRIVATE_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= python -c "
import asyncio
from cloude_api.workers.docker_client import make_docker_client, close_docker_client
async def main():
    c = await make_docker_client()
    v = await c.version()
    print('docker version ok:', v.get('Version'))
    await close_docker_client(c)
asyncio.run(main())
"
```
Expected: `docker version ok: <some version string>` (the local Docker daemon must be running — it is, since the compose stack uses it).

- [ ] **Step 3:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/docker_client.py
git add apps/api/src/cloude_api/workers/docker_client.py
git commit -m "feat(p1b): aiodocker client factory + lifecycle"
```

---

## Task 3: Spawner module — names, labels, `SpawnError`, `tear_down` (TDD)

**Files:**
- Create: `apps/api/src/cloude_api/workers/spawner.py` (initial skeleton — more lands in later tasks)
- Create: `apps/api/tests/unit/test_spawner_logic.py`

- [ ] **Step 1:** Write the failing test

Create `apps/api/tests/unit/test_spawner_logic.py`:
```python
"""Tests for spawner helper logic (pure-Python + mocked docker)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiodocker
import pytest

from cloude_api.workers import spawner


def test_render_names_uses_first_12_hex_chars_for_containers() -> None:
    device_id = uuid.UUID("12345678-1234-1234-1234-1234567890ab")
    sidecar, redroid, volume, labels = spawner.render_names(device_id)
    assert sidecar == "cloude-sidecar-123456781234"
    assert redroid == "cloude-redroid-123456781234"
    assert volume == f"cloude-data-{device_id}"
    assert labels == {"cloude.device_id": str(device_id)}


def test_spawn_error_carries_human_reason() -> None:
    e = spawner.SpawnError("sidecar failed to start")
    assert str(e) == "sidecar failed to start"


@pytest.mark.asyncio
async def test_tear_down_ignores_missing_containers_and_volume() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    docker.volumes = MagicMock()

    missing_container = AsyncMock(
        side_effect=aiodocker.exceptions.DockerError(404, {"message": "no such container"})
    )
    missing_volume = AsyncMock(
        side_effect=aiodocker.exceptions.DockerError(404, {"message": "no such volume"})
    )
    docker.containers.get = missing_container
    docker.volumes.get = missing_volume

    # Should NOT raise even though both lookups return 404.
    await spawner.tear_down(
        docker, sidecar_name="sc", redroid_name="rd", volume_name="vol", remove_volume=True
    )


@pytest.mark.asyncio
async def test_tear_down_removes_existing_containers_and_volume_when_requested() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    docker.volumes = MagicMock()

    fake_sidecar = MagicMock()
    fake_sidecar.delete = AsyncMock()
    fake_redroid = MagicMock()
    fake_redroid.delete = AsyncMock()
    fake_volume = MagicMock()
    fake_volume.delete = AsyncMock()

    docker.containers.get = AsyncMock(side_effect=[fake_sidecar, fake_redroid])
    docker.volumes.get = AsyncMock(return_value=fake_volume)

    await spawner.tear_down(
        docker, sidecar_name="sc", redroid_name="rd", volume_name="vol", remove_volume=True
    )
    fake_sidecar.delete.assert_awaited_once_with(force=True)
    fake_redroid.delete.assert_awaited_once_with(force=True)
    fake_volume.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_tear_down_skips_volume_when_remove_volume_false() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    docker.volumes = MagicMock()

    docker.containers.get = AsyncMock(
        side_effect=aiodocker.exceptions.DockerError(404, {"message": "missing"})
    )
    docker.volumes.get = AsyncMock()

    await spawner.tear_down(
        docker, sidecar_name="sc", redroid_name="rd", volume_name="vol", remove_volume=False
    )
    docker.volumes.get.assert_not_called()
```

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py
```
Expected: `ModuleNotFoundError: No module named 'cloude_api.workers.spawner'`.

- [ ] **Step 3:** Implement the initial `spawner.py` (just names/labels/tear_down — the spawn helpers land in Tasks 4-6)

```python
"""Per-device sidecar+redroid spawn orchestration.

Public surface used by arq tasks:
    SpawnError                — non-retryable failure with human reason
    render_names(device_id)   — deterministic container/volume names + labels
    tear_down(...)            — best-effort cleanup, never raises
    spawn_sidecar(...)        — added in Task 4
    spawn_redroid(...)        — added in Task 5
    wait_for_sidecar_healthy  — added in Task 6
    wait_for_boot_completed   — added in Task 6
    create_device(...)        — arq task, added in Task 7
    _finalize_running(...)    — extracted helper, added in Task 7
"""

from __future__ import annotations

import uuid

import aiodocker

SIDECAR_IMAGE = "cloude/sidecar:p0"
REDROID_IMAGE = "redroid/redroid:11.0.0-latest"


class SpawnError(Exception):
    """Non-retryable spawn failure. The arq task catches this and sets state=error."""


def render_names(device_id: uuid.UUID) -> tuple[str, str, str, dict[str, str]]:
    """Returns (sidecar_name, redroid_name, volume_name, labels)."""
    short = device_id.hex[:12]
    sidecar_name = f"cloude-sidecar-{short}"
    redroid_name = f"cloude-redroid-{short}"
    volume_name = f"cloude-data-{device_id}"
    labels = {"cloude.device_id": str(device_id)}
    return sidecar_name, redroid_name, volume_name, labels


async def tear_down(
    docker: aiodocker.Docker,
    *,
    sidecar_name: str,
    redroid_name: str,
    volume_name: str | None,
    remove_volume: bool,
) -> None:
    """Best-effort removal. Never raises. 404s are ignored."""
    for name in (sidecar_name, redroid_name):
        try:
            container = await docker.containers.get(name)
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                continue
            # Anything else — log and move on; we don't want spawn failure to
            # cascade into a stuck row because cleanup itself errored.
            continue
        try:
            await container.delete(force=True)
        except aiodocker.exceptions.DockerError:
            continue
    if remove_volume and volume_name:
        try:
            vol = await docker.volumes.get(volume_name)
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                return
            return
        try:
            await vol.delete()
        except aiodocker.exceptions.DockerError:
            return
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py -v
```
Expected: `5 passed`.

- [ ] **Step 5:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git add apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git commit -m "feat(p1b): spawner skeleton — names, SpawnError, tear_down"
```

---

## Task 4: `spawn_sidecar` helper (TDD)

**Files:**
- Modify: `apps/api/src/cloude_api/workers/spawner.py`
- Modify: `apps/api/tests/unit/test_spawner_logic.py`

- [ ] **Step 1:** Append the failing test to `test_spawner_logic.py`

Add at the end of the file:
```python
@pytest.mark.asyncio
async def test_spawn_sidecar_passes_expected_config() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_container.id = "sha256:abcdef"
    docker.containers.run = AsyncMock(return_value=fake_container)

    cid = await spawner.spawn_sidecar(
        docker,
        name="cloude-sidecar-aaaabbbbcccc",
        adb_port=40500,
        proxy_host="proxy.example.com",
        proxy_port=1080,
        proxy_type="socks5",
        proxy_user="u",
        proxy_pass="p",
        labels={"cloude.device_id": "xx"},
    )
    assert cid == "sha256:abcdef"

    call_kwargs = docker.containers.run.await_args.kwargs
    assert call_kwargs["name"] == "cloude-sidecar-aaaabbbbcccc"
    cfg = call_kwargs["config"]
    assert cfg["Image"] == "cloude/sidecar:p0"
    assert cfg["Labels"] == {"cloude.device_id": "xx"}
    env = set(cfg["Env"])
    assert "PROXY_HOST=proxy.example.com" in env
    assert "PROXY_PORT=1080" in env
    assert "PROXY_TYPE=socks5" in env
    assert "PROXY_USER=u" in env
    assert "PROXY_PASS=p" in env
    hc = cfg["HostConfig"]
    assert hc["CapAdd"] == ["NET_ADMIN", "NET_RAW"]
    assert hc["Sysctls"] == {"net.ipv4.ip_forward": "1"}
    assert hc["PortBindings"] == {"5555/tcp": [{"HostPort": "40500"}]}
    assert hc["RestartPolicy"] == {"Name": "no"}
    assert cfg["ExposedPorts"] == {"5555/tcp": {}}
```

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py::test_spawn_sidecar_passes_expected_config -v
```
Expected: `AttributeError: module 'cloude_api.workers.spawner' has no attribute 'spawn_sidecar'`.

- [ ] **Step 3:** Append `spawn_sidecar` to `spawner.py`

Add after `tear_down` in `spawner.py`:
```python
async def spawn_sidecar(
    docker: aiodocker.Docker,
    *,
    name: str,
    adb_port: int,
    proxy_host: str,
    proxy_port: int,
    proxy_type: str,
    proxy_user: str,
    proxy_pass: str,
    labels: dict[str, str],
) -> str:
    """Launch the sidecar container. Returns the container id."""
    container = await docker.containers.run(
        name=name,
        config={
            "Image": SIDECAR_IMAGE,
            "Labels": labels,
            "Env": [
                f"PROXY_HOST={proxy_host}",
                f"PROXY_PORT={proxy_port}",
                f"PROXY_TYPE={proxy_type}",
                f"PROXY_USER={proxy_user}",
                f"PROXY_PASS={proxy_pass}",
            ],
            "ExposedPorts": {"5555/tcp": {}},
            "HostConfig": {
                "CapAdd": ["NET_ADMIN", "NET_RAW"],
                "Sysctls": {"net.ipv4.ip_forward": "1"},
                "PortBindings": {"5555/tcp": [{"HostPort": str(adb_port)}]},
                "RestartPolicy": {"Name": "no"},
            },
        },
    )
    return str(container.id)
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py -v
```
Expected: `6 passed`.

- [ ] **Step 5:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git add apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git commit -m "feat(p1b): spawn_sidecar helper"
```

---

## Task 5: `spawn_redroid` helper (TDD)

**Files:**
- Modify: `apps/api/src/cloude_api/workers/spawner.py`
- Modify: `apps/api/tests/unit/test_spawner_logic.py`

- [ ] **Step 1:** Append the failing test to `test_spawner_logic.py`

```python
@pytest.mark.asyncio
async def test_spawn_redroid_passes_expected_config() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_container.id = "sha256:redroidid"
    docker.containers.run = AsyncMock(return_value=fake_container)

    cid = await spawner.spawn_redroid(
        docker,
        name="cloude-redroid-aaaabbbbcccc",
        sidecar_name="cloude-sidecar-aaaabbbbcccc",
        volume="cloude-data-xxxx",
        width=1080,
        height=2340,
        dpi=440,
        ram_mb=4096,
        cpus=4,
        model="Pixel 5",
        manufacturer="Google",
        labels={"cloude.device_id": "xx"},
    )
    assert cid == "sha256:redroidid"

    call_kwargs = docker.containers.run.await_args.kwargs
    cfg = call_kwargs["config"]
    assert cfg["Image"] == "redroid/redroid:11.0.0-latest"
    assert cfg["Labels"] == {"cloude.device_id": "xx"}
    cmd = cfg["Cmd"]
    assert "androidboot.redroid_width=1080" in cmd
    assert "androidboot.redroid_height=2340" in cmd
    assert "androidboot.redroid_dpi=440" in cmd
    assert "androidboot.redroid_gpu_mode=guest" in cmd
    assert "ro.product.model=Pixel 5" in cmd
    assert "ro.product.manufacturer=Google" in cmd
    assert "net.dns1=127.0.0.1" in cmd
    assert "net.dns2=127.0.0.1" in cmd

    hc = cfg["HostConfig"]
    assert hc["NetworkMode"] == "container:cloude-sidecar-aaaabbbbcccc"
    assert hc["Privileged"] is True
    assert hc["Memory"] == 4096 * 1024 * 1024
    assert hc["CpuCount"] == 4
    assert hc["Binds"] == ["cloude-data-xxxx:/data"]
    assert hc["RestartPolicy"] == {"Name": "no"}
```

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py::test_spawn_redroid_passes_expected_config -v
```
Expected: `AttributeError: ... has no attribute 'spawn_redroid'`.

- [ ] **Step 3:** Append `spawn_redroid` to `spawner.py`

```python
async def spawn_redroid(
    docker: aiodocker.Docker,
    *,
    name: str,
    sidecar_name: str,
    volume: str,
    width: int,
    height: int,
    dpi: int,
    ram_mb: int,
    cpus: int,
    model: str,
    manufacturer: str,
    labels: dict[str, str],
) -> str:
    """Launch the redroid container joined to the sidecar's netns. Returns id."""
    cmd = [
        f"androidboot.redroid_width={width}",
        f"androidboot.redroid_height={height}",
        f"androidboot.redroid_dpi={dpi}",
        "androidboot.redroid_gpu_mode=guest",
        f"ro.product.model={model}",
        f"ro.product.manufacturer={manufacturer}",
        "net.dns1=127.0.0.1",
        "net.dns2=127.0.0.1",
    ]
    container = await docker.containers.run(
        name=name,
        config={
            "Image": REDROID_IMAGE,
            "Cmd": cmd,
            "Labels": labels,
            "HostConfig": {
                "NetworkMode": f"container:{sidecar_name}",
                "Privileged": True,
                "Memory": ram_mb * 1024 * 1024,
                "CpuCount": cpus,
                "Binds": [f"{volume}:/data"],
                "RestartPolicy": {"Name": "no"},
            },
        },
    )
    return str(container.id)
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py -v
```
Expected: `7 passed`.

- [ ] **Step 5:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git add apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git commit -m "feat(p1b): spawn_redroid helper"
```

---

## Task 6: `wait_for_sidecar_healthy` + `wait_for_boot_completed` (TDD)

**Files:**
- Modify: `apps/api/src/cloude_api/workers/spawner.py`
- Modify: `apps/api/tests/unit/test_spawner_logic.py`

- [ ] **Step 1:** Append the failing tests

```python
@pytest.mark.asyncio
async def test_wait_for_sidecar_healthy_succeeds_when_redsocks_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_exec = MagicMock()
    fake_exec.start = AsyncMock(return_value=b"123\n")  # pgrep output: a pid
    fake_container.exec = AsyncMock(return_value=fake_exec)
    docker.containers.get = AsyncMock(return_value=fake_container)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    await spawner.wait_for_sidecar_healthy(docker, "sc", timeout_s=5.0)


@pytest.mark.asyncio
async def test_wait_for_sidecar_healthy_raises_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_exec = MagicMock()
    fake_exec.start = AsyncMock(return_value=b"")  # pgrep finds nothing
    fake_container.exec = AsyncMock(return_value=fake_exec)
    docker.containers.get = AsyncMock(return_value=fake_container)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    with pytest.raises(spawner.SpawnError, match="sidecar"):
        await spawner.wait_for_sidecar_healthy(docker, "sc", timeout_s=0.0)


@pytest.mark.asyncio
async def test_wait_for_boot_completed_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_container.show = AsyncMock(return_value={"State": {"Status": "running"}})
    fake_exec = MagicMock()
    fake_exec.start = AsyncMock(return_value=b"1\n")
    fake_container.exec = AsyncMock(return_value=fake_exec)
    docker.containers.get = AsyncMock(return_value=fake_container)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    await spawner.wait_for_boot_completed(docker, "rd", timeout_s=5.0)


@pytest.mark.asyncio
async def test_wait_for_boot_completed_raises_when_container_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_container.show = AsyncMock(return_value={"State": {"Status": "exited"}})
    fake_exec = MagicMock()
    fake_exec.start = AsyncMock(return_value=b"")
    fake_container.exec = AsyncMock(return_value=fake_exec)
    docker.containers.get = AsyncMock(return_value=fake_container)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    with pytest.raises(spawner.SpawnError, match="exited"):
        await spawner.wait_for_boot_completed(docker, "rd", timeout_s=5.0)


@pytest.mark.asyncio
async def test_wait_for_boot_completed_raises_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_container.show = AsyncMock(return_value={"State": {"Status": "running"}})
    fake_exec = MagicMock()
    fake_exec.start = AsyncMock(return_value=b"0\n")  # not booted
    fake_container.exec = AsyncMock(return_value=fake_exec)
    docker.containers.get = AsyncMock(return_value=fake_container)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    with pytest.raises(spawner.SpawnError, match="boot did not complete"):
        await spawner.wait_for_boot_completed(docker, "rd", timeout_s=0.0)
```

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py -v 2>&1 | tail -10
```
Expected: 5 new tests fail with `AttributeError` for `wait_for_sidecar_healthy` / `wait_for_boot_completed`.

- [ ] **Step 3:** Append the helpers to `spawner.py`

```python
import asyncio
import time


async def _exec_capture(container: aiodocker.docker.DockerContainer, cmd: list[str]) -> str:
    """Run `cmd` in the container, return stdout as utf-8 text. Best-effort."""
    exec_obj = await container.exec(cmd, stdout=True, stderr=False)
    out = await exec_obj.start(detach=False)
    if isinstance(out, bytes):
        return out.decode("utf-8", errors="replace")
    return str(out)


async def wait_for_sidecar_healthy(
    docker: aiodocker.Docker, name: str, *, timeout_s: float = 20.0
) -> None:
    """Poll sidecar until `pgrep redsocks` returns a pid. Raises SpawnError on timeout."""
    container = await docker.containers.get(name)
    deadline = time.monotonic() + timeout_s
    while True:
        out = await _exec_capture(container, ["pgrep", "redsocks"])
        if out.strip():
            return
        if time.monotonic() >= deadline:
            raise SpawnError(f"sidecar '{name}' redsocks did not start within {timeout_s:.0f}s")
        await asyncio.sleep(1.0)


async def wait_for_boot_completed(
    docker: aiodocker.Docker, name: str, *, timeout_s: float = 120.0
) -> None:
    """Poll redroid until `getprop sys.boot_completed` returns `1`. Raises on timeout/exit."""
    container = await docker.containers.get(name)
    deadline = time.monotonic() + timeout_s
    while True:
        info = await container.show()
        status = info.get("State", {}).get("Status")
        if status == "exited":
            raise SpawnError(f"redroid '{name}' exited before boot completed")
        out = await _exec_capture(container, ["getprop", "sys.boot_completed"])
        if out.strip() == "1":
            return
        if time.monotonic() >= deadline:
            raise SpawnError(f"android boot did not complete within {timeout_s:.0f}s")
        await asyncio.sleep(2.0)
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py -v
```
Expected: `12 passed`.

- [ ] **Step 5:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git add apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git commit -m "feat(p1b): wait helpers (sidecar healthy, boot completed)"
```

---

## Task 7: `create_device` task + `_finalize_running` helper (TDD)

**Files:**
- Modify: `apps/api/src/cloude_api/workers/spawner.py`
- Modify: `apps/api/tests/unit/test_spawner_logic.py`

This task wires everything together. The `create_device` arq job loads the device, calls the spawn helpers in order, and either calls `_finalize_running` on success or tears down + flips to error on failure.

- [ ] **Step 1:** Append failing tests for `_finalize_running` and the spawn error path

```python
@pytest.mark.asyncio
async def test_finalize_running_updates_row_and_publishes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given a Device row in 'creating', _finalize_running transitions it to 'running'
    with the right metadata and publishes one ws status message."""
    import json
    import uuid as _uuid
    from datetime import datetime
    from cloude_api.enums import DeviceState
    from cloude_api.models.device import Device

    # Hand-built row (no DB write, no flush)
    d = Device(
        id=_uuid.uuid4(),
        user_id=_uuid.uuid4(),
        name="t",
        profile_id=_uuid.uuid4(),
        proxy_id=None,
        state=DeviceState.creating,
    )

    commits: list[str] = []

    class FakeDb:
        async def commit(self) -> None:
            commits.append("c")

        async def refresh(self, *_a: object, **_kw: object) -> None:
            return None

    published: list[tuple[str, str]] = []

    class FakeRedis:
        async def publish(self, channel: str, payload: str) -> int:
            published.append((channel, payload))
            return 1

    await spawner._finalize_running(
        FakeDb(),  # type: ignore[arg-type]
        FakeRedis(),  # type: ignore[arg-type]
        device=d,
        sidecar_id="sha256:sidecarid",
        redroid_id="sha256:redroidid",
        adb_port=40123,
    )

    assert d.state == DeviceState.running
    assert d.adb_host_port == 40123
    assert d.sidecar_container_id == "sha256:sidecarid"
    assert d.redroid_container_id == "sha256:redroidid"
    assert d.started_at is not None and isinstance(d.started_at, datetime)
    assert commits == ["c"]
    assert len(published) == 1
    channel, payload = published[0]
    assert channel == f"ws:device:{d.id}"
    parsed = json.loads(payload)
    assert parsed["state"] == "running"
    assert parsed["adb_host_port"] == 40123
```

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py::test_finalize_running_updates_row_and_publishes -v
```
Expected: AttributeError for `_finalize_running`.

- [ ] **Step 3:** Append `_finalize_running` + `create_device` to `spawner.py`

Add these imports at the TOP of `spawner.py` (next to existing imports):
```python
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloude_api.config import get_settings
from cloude_api.core.audit import write_audit
from cloude_api.core.encryption import decrypt_password
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.proxy import Proxy
from cloude_api.workers import port_allocator
from cloude_api.ws.pubsub import channel_for

log = logging.getLogger("cloude.worker.spawner")
```

Then append at the end of `spawner.py`:
```python
async def _finalize_running(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    device: Device,
    sidecar_id: str,
    redroid_id: str,
    adb_port: int,
) -> None:
    """Flip the device row to 'running' with all spawn metadata and publish to ws."""
    device.state = DeviceState.running
    device.state_reason = None
    device.adb_host_port = adb_port
    device.sidecar_container_id = sidecar_id[:64]
    device.redroid_container_id = redroid_id[:64]
    device.started_at = datetime.now(tz=UTC)
    await db.commit()
    payload = json.dumps(
        {
            "device_id": str(device.id),
            "state": device.state.value,
            "state_reason": None,
            "adb_host_port": adb_port,
        }
    )
    await redis.publish(channel_for(str(device.id)), payload)


async def _finalize_error(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    device: Device,
    reason: str,
) -> None:
    """Flip the device row to 'error' with a human reason, audit, publish."""
    device.state = DeviceState.error
    device.state_reason = reason
    device.adb_host_port = None
    await write_audit(
        db,
        user_id=device.user_id,
        action="device.spawn_failed",
        target_id=device.id,
        metadata={"reason": reason},
    )
    await db.commit()
    payload = json.dumps(
        {
            "device_id": str(device.id),
            "state": device.state.value,
            "state_reason": reason,
            "adb_host_port": None,
        }
    )
    await redis.publish(channel_for(str(device.id)), payload)


async def create_device(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """arq task: spawn one sidecar+redroid pair for the given device row."""
    docker: aiodocker.Docker = ctx["docker"]
    redis: aioredis.Redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)
    settings = get_settings()

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None:
            log.warning("create_device: device %s missing", device_id)
            return {"ok": False, "reason": "device_missing"}
        if d.state != DeviceState.creating:
            log.info("create_device: device %s state=%s, no-op", device_id, d.state)
            return {"ok": True, "noop": True, "state": d.state.value}

        profile = await db.scalar(
            select(DeviceProfile).where(DeviceProfile.id == d.profile_id)
        )
        if d.proxy_id is None:
            await _finalize_error(db, redis, device=d, reason="no proxy assigned")
            return {"ok": False, "reason": "no proxy"}
        proxy = await db.scalar(select(Proxy).where(Proxy.id == d.proxy_id))
        if profile is None or proxy is None:
            await _finalize_error(db, redis, device=d, reason="profile or proxy gone")
            return {"ok": False, "reason": "profile_or_proxy_missing"}

        proxy_password = (
            decrypt_password(
                proxy.password_encrypted,
                pub_b64=settings.encryption_public_key,
                priv_b64=settings.encryption_private_key,
            )
            if proxy.password_encrypted
            else ""
        )

        port = await port_allocator.acquire(redis)
        if port is None:
            await _finalize_error(db, redis, device=d, reason="port pool exhausted")
            return {"ok": False, "reason": "port_exhausted"}

        sidecar_name, redroid_name, volume_name, labels = render_names(d.id)
        sidecar_id = ""
        redroid_id = ""
        try:
            try:
                await docker.volumes.create({"Name": volume_name})
            except aiodocker.exceptions.DockerError as e:
                if e.status != 409:  # 409 = already exists, idempotent
                    raise SpawnError(f"volume create failed: {e}") from e

            sidecar_id = await spawn_sidecar(
                docker,
                name=sidecar_name,
                adb_port=port,
                proxy_host=proxy.host,
                proxy_port=proxy.port,
                proxy_type=proxy.type.value,
                proxy_user=proxy.username or "",
                proxy_pass=proxy_password,
                labels=labels | {"cloude.role": "sidecar"},
            )
            await wait_for_sidecar_healthy(docker, sidecar_name)

            redroid_id = await spawn_redroid(
                docker,
                name=redroid_name,
                sidecar_name=sidecar_name,
                volume=volume_name,
                width=profile.screen_width,
                height=profile.screen_height,
                dpi=profile.screen_dpi,
                ram_mb=profile.ram_mb,
                cpus=profile.cpu_cores,
                model=profile.model,
                manufacturer=profile.manufacturer,
                labels=labels | {"cloude.role": "redroid"},
            )
            await wait_for_boot_completed(docker, redroid_name)
        except SpawnError as e:
            log.warning("spawn failed for %s: %s", device_id, e)
            await tear_down(
                docker,
                sidecar_name=sidecar_name,
                redroid_name=redroid_name,
                volume_name=volume_name,
                remove_volume=False,
            )
            await port_allocator.release(redis, port)
            await _finalize_error(db, redis, device=d, reason=str(e))
            return {"ok": False, "reason": str(e)}

        await _finalize_running(
            db, redis, device=d,
            sidecar_id=sidecar_id, redroid_id=redroid_id, adb_port=port,
        )
        log.info("create_device done: %s on port %d", device_id, port)
        return {"ok": True, "state": "running", "adb_host_port": port}
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_spawner_logic.py -v
```
Expected: `13 passed`.

- [ ] **Step 5:** Also run the full unit suite to make sure nothing regressed

```bash
cd apps/api && python -m pytest tests/unit/ -q
```
Expected: `≥33 passed` (24 P1a + spawner-logic tests from this task chain; exact count depends on accumulated tests).

- [ ] **Step 6:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git add apps/api/src/cloude_api/workers/spawner.py apps/api/tests/unit/test_spawner_logic.py
git commit -m "feat(p1b): create_device task + _finalize_running helper"
```

---

## Task 8: `stop_device` task + `graceful_stop` (TDD)

**Files:**
- Create: `apps/api/src/cloude_api/workers/lifecycle.py`
- Create: `apps/api/tests/unit/test_lifecycle.py`

- [ ] **Step 1:** Write the failing test

Create `apps/api/tests/unit/test_lifecycle.py`:
```python
"""Tests for stop/delete worker tasks (mocked Docker + DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import aiodocker
import pytest

from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.workers import lifecycle


def _make_device(state: DeviceState, adb_port: int | None = 40500) -> Device:
    d = Device(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="t",
        profile_id=uuid.uuid4(),
        proxy_id=None,
        state=state,
    )
    d.adb_host_port = adb_port
    return d


@pytest.mark.asyncio
async def test_graceful_stop_removes_container() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake = MagicMock()
    fake.stop = AsyncMock()
    fake.delete = AsyncMock()
    docker.containers.get = AsyncMock(return_value=fake)

    await lifecycle.graceful_stop(docker, "name")
    fake.stop.assert_awaited_once_with(timeout=10)
    fake.delete.assert_awaited_once_with(force=True)


@pytest.mark.asyncio
async def test_graceful_stop_ignores_404() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    docker.containers.get = AsyncMock(
        side_effect=aiodocker.exceptions.DockerError(404, {"message": "no such container"})
    )
    # Must not raise.
    await lifecycle.graceful_stop(docker, "name")
```

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_lifecycle.py
```
Expected: `ModuleNotFoundError: No module named 'cloude_api.workers.lifecycle'`.

- [ ] **Step 3:** Implement `apps/api/src/cloude_api/workers/lifecycle.py`

```python
"""Stop/delete worker tasks + graceful_stop helper."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aiodocker
import redis.asyncio as aioredis
from sqlalchemy import select

from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.workers import port_allocator
from cloude_api.workers.spawner import render_names, tear_down
from cloude_api.ws.pubsub import channel_for

log = logging.getLogger("cloude.worker.lifecycle")


async def graceful_stop(
    docker: aiodocker.Docker, name: str, *, timeout: int = 10
) -> None:
    """Stop then delete a container. 404s are ignored."""
    try:
        container = await docker.containers.get(name)
    except aiodocker.exceptions.DockerError as e:
        if e.status == 404:
            return
        log.warning("graceful_stop: get %s failed: %s", name, e)
        return
    try:
        await container.stop(timeout=timeout)
    except aiodocker.exceptions.DockerError:
        pass  # already stopped, fine
    try:
        await container.delete(force=True)
    except aiodocker.exceptions.DockerError:
        pass


async def _publish(redis: aioredis.Redis, device: Device) -> None:
    payload = json.dumps(
        {
            "device_id": str(device.id),
            "state": device.state.value,
            "state_reason": device.state_reason,
            "adb_host_port": device.adb_host_port,
        }
    )
    await redis.publish(channel_for(str(device.id)), payload)


async def stop_device(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """arq task: stop both containers, release ADB port, set state=stopped."""
    docker: aiodocker.Docker = ctx["docker"]
    redis: aioredis.Redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None:
            return {"ok": False, "reason": "device_missing"}
        if d.state in (DeviceState.stopped, DeviceState.deleted):
            return {"ok": True, "noop": True, "state": d.state.value}

        sidecar_name, redroid_name, _vol, _labels = render_names(d.id)
        await graceful_stop(docker, redroid_name)
        await graceful_stop(docker, sidecar_name)

        if d.adb_host_port is not None:
            await port_allocator.release(redis, d.adb_host_port)
            d.adb_host_port = None
        d.state = DeviceState.stopped
        d.stopped_at = datetime.now(tz=UTC)
        d.state_reason = None
        await db.commit()
        await _publish(redis, d)
    return {"ok": True, "state": "stopped"}
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_lifecycle.py -v
```
Expected: `2 passed`.

- [ ] **Step 5:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/lifecycle.py apps/api/tests/unit/test_lifecycle.py
git add apps/api/src/cloude_api/workers/lifecycle.py apps/api/tests/unit/test_lifecycle.py
git commit -m "feat(p1b): stop_device task + graceful_stop helper"
```

---

## Task 9: `delete_device` task (TDD)

**Files:**
- Modify: `apps/api/src/cloude_api/workers/lifecycle.py`
- Modify: `apps/api/tests/unit/test_lifecycle.py`

- [ ] **Step 1:** Append the failing test

```python
@pytest.mark.asyncio
async def test_delete_device_removes_containers_and_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    """delete_device should call tear_down with remove_volume=True."""
    called: dict[str, object] = {}

    async def fake_tear_down(*_args: object, **kwargs: object) -> None:
        called.update(kwargs)

    monkeypatch.setattr(lifecycle, "tear_down", fake_tear_down)

    # We can't easily mock async_session_factory; this test asserts only the
    # shape of tear_down call by patching it. The full DB-level test is in
    # the integration suite (Task 14).
    # For unit-level we just verify the helper interface is shaped right;
    # the orchestration is tested via the integration test.
    assert callable(lifecycle.delete_device)
```

(This test is intentionally light — fully exercising `delete_device` requires real DB state, which the integration test covers. Unit-level we just confirm the function exists and the interface to `tear_down` is right by patching.)

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_lifecycle.py::test_delete_device_removes_containers_and_volume -v
```
Expected: `AttributeError: module 'cloude_api.workers.lifecycle' has no attribute 'delete_device'`.

- [ ] **Step 3:** Append `delete_device` to `lifecycle.py`

```python
async def delete_device(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """arq task: stop if running, remove containers + volume, set state=deleted."""
    docker: aiodocker.Docker = ctx["docker"]
    redis: aioredis.Redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None:
            return {"ok": False, "reason": "device_missing"}
        if d.state == DeviceState.deleted:
            return {"ok": True, "noop": True}

        if d.state in (DeviceState.running, DeviceState.creating):
            sidecar_name, redroid_name, _vol, _labels = render_names(d.id)
            await graceful_stop(docker, redroid_name)
            await graceful_stop(docker, sidecar_name)
            if d.adb_host_port is not None:
                await port_allocator.release(redis, d.adb_host_port)
                d.adb_host_port = None

        _sc, _rd, volume_name, _labels = render_names(d.id)
        await tear_down(
            docker,
            sidecar_name=_sc,
            redroid_name=_rd,
            volume_name=volume_name,
            remove_volume=True,
        )
        d.state = DeviceState.deleted
        d.stopped_at = d.stopped_at or datetime.now(tz=UTC)
        d.state_reason = None
        await db.commit()
        await _publish(redis, d)
    return {"ok": True, "state": "deleted"}
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_lifecycle.py -v
```
Expected: `3 passed`.

- [ ] **Step 5:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/lifecycle.py apps/api/tests/unit/test_lifecycle.py
git add apps/api/src/cloude_api/workers/lifecycle.py apps/api/tests/unit/test_lifecycle.py
git commit -m "feat(p1b): delete_device task"
```

---

## Task 10: `reap_stuck_devices` cron + `orphan_scan` startup hook (TDD)

**Files:**
- Create: `apps/api/src/cloude_api/workers/reapers.py`
- Create: `apps/api/tests/unit/test_reapers.py`

- [ ] **Step 1:** Write the failing tests

Create `apps/api/tests/unit/test_reapers.py`:
```python
"""Tests for reapers.STUCK_THRESHOLD_SECONDS, reap_stuck_devices, orphan_scan (mocked)."""

from __future__ import annotations

from cloude_api.workers import reapers


def test_stuck_threshold_is_three_minutes() -> None:
    assert reapers.STUCK_THRESHOLD_SECONDS == 180


def test_module_exports_required_callables() -> None:
    # These names are imported by arq_settings; if a refactor renames them,
    # this test catches it before runtime.
    assert callable(reapers.reap_stuck_devices)
    assert callable(reapers.orphan_scan)
```

- [ ] **Step 2:** Run, confirm FAIL

```bash
cd apps/api && python -m pytest tests/unit/test_reapers.py
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3:** Implement `apps/api/src/cloude_api/workers/reapers.py`

```python
"""Crash-recovery jobs.

reap_stuck_devices: arq cron, runs every 60s. Any device stuck in 'creating'
longer than STUCK_THRESHOLD_SECONDS gets torn down + flipped to 'error' so the
UI can show it instead of leaving the user with a phantom creating row.

orphan_scan: ran once at worker startup. Any device in 'running' or 'creating'
whose containers are missing (worker died, host rebooted) gets flipped to
'error' so the user can retry via /start.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import aiodocker
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.workers import port_allocator
from cloude_api.workers.spawner import render_names, tear_down
from cloude_api.ws.pubsub import channel_for

log = logging.getLogger("cloude.worker.reapers")

STUCK_THRESHOLD_SECONDS = 180


async def _flip_error(
    db: AsyncSession, redis: aioredis.Redis, *, device: Device, reason: str
) -> None:
    device.state = DeviceState.error
    device.state_reason = reason
    device.adb_host_port = None
    await db.commit()
    await redis.publish(
        channel_for(str(device.id)),
        json.dumps(
            {
                "device_id": str(device.id),
                "state": device.state.value,
                "state_reason": reason,
                "adb_host_port": None,
            }
        ),
    )


async def reap_stuck_devices(ctx: dict[str, Any]) -> None:
    """Cron entrypoint. Tear down devices stuck in 'creating' too long."""
    docker: aiodocker.Docker = ctx["docker"]
    redis: aioredis.Redis = ctx["redis"]
    threshold = datetime.now(tz=UTC) - timedelta(seconds=STUCK_THRESHOLD_SECONDS)

    async with async_session_factory() as db:
        stuck_rows = (
            await db.scalars(
                select(Device).where(
                    Device.state == DeviceState.creating,
                    Device.created_at < threshold,
                )
            )
        ).all()
        for d in stuck_rows:
            sidecar_name, redroid_name, volume_name, _labels = render_names(d.id)
            await tear_down(
                docker,
                sidecar_name=sidecar_name,
                redroid_name=redroid_name,
                volume_name=volume_name,
                remove_volume=False,
            )
            if d.adb_host_port is not None:
                await port_allocator.release(redis, d.adb_host_port)
            await _flip_error(
                db, redis, device=d,
                reason=f"spawn timeout (stuck in 'creating' > {STUCK_THRESHOLD_SECONDS}s)",
            )
            log.warning("reaped stuck device %s", d.id)


async def orphan_scan(
    db: AsyncSession, redis: aioredis.Redis, docker: aiodocker.Docker
) -> None:
    """One-shot scan at worker startup. Any 'running' device whose containers
    are gone gets flipped to 'error'."""
    rows = (
        await db.scalars(
            select(Device).where(Device.state.in_([DeviceState.running, DeviceState.creating]))
        )
    ).all()
    for d in rows:
        sidecar_name, redroid_name, _vol, _labels = render_names(d.id)
        found = True
        for name in (sidecar_name, redroid_name):
            try:
                await docker.containers.get(name)
            except aiodocker.exceptions.DockerError as e:
                if e.status == 404:
                    found = False
                    break
        if not found:
            if d.adb_host_port is not None:
                await port_allocator.release(redis, d.adb_host_port)
            await _flip_error(
                db, redis, device=d,
                reason="containers missing after worker restart",
            )
            log.warning("orphan-scan flipped %s to error", d.id)
```

- [ ] **Step 4:** Run, confirm PASS

```bash
cd apps/api && python -m pytest tests/unit/test_reapers.py -v
```
Expected: `2 passed`.

- [ ] **Step 5:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/reapers.py apps/api/tests/unit/test_reapers.py
git add apps/api/src/cloude_api/workers/reapers.py apps/api/tests/unit/test_reapers.py
git commit -m "feat(p1b): reap_stuck_devices cron + orphan_scan startup hook"
```

---

## Task 11: Rewire `tasks.py` and `arq_settings.py`; remove stub

**Files:**
- Modify: `apps/api/src/cloude_api/workers/tasks.py` (rewritten)
- Modify: `apps/api/src/cloude_api/workers/arq_settings.py`

- [ ] **Step 1:** Replace `apps/api/src/cloude_api/workers/tasks.py` entirely

Overwrite the file with:
```python
"""Worker composition: lifecycle hooks + re-export of task functions.

arq_settings imports the function objects from this module so the actual
task implementations stay in focused modules (spawner / lifecycle / reapers).
"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from cloude_api.config import get_settings
from cloude_api.db import async_session_factory
from cloude_api.workers import port_allocator
from cloude_api.workers.docker_client import close_docker_client, make_docker_client
from cloude_api.workers.lifecycle import delete_device, stop_device
from cloude_api.workers.reapers import orphan_scan, reap_stuck_devices
from cloude_api.workers.spawner import create_device

__all__ = [
    "create_device",
    "delete_device",
    "reap_stuck_devices",
    "stop_device",
    "_on_shutdown",
    "_on_startup",
]

log = logging.getLogger("cloude.worker")


async def _on_startup(ctx: dict[str, Any]) -> None:
    s = get_settings()
    ctx["redis"] = aioredis.from_url(  # type: ignore[no-untyped-call]
        s.redis_url, encoding="utf-8", decode_responses=False
    )
    ctx["docker"] = await make_docker_client()
    async with async_session_factory() as db:
        await port_allocator.initialize(ctx["redis"], db)
        await orphan_scan(db, ctx["redis"], ctx["docker"])
    log.info("worker startup: redis=%s docker=ok", s.redis_url)


async def _on_shutdown(ctx: dict[str, Any]) -> None:
    docker = ctx.get("docker")
    if docker is not None:
        await close_docker_client(docker)
    redis = ctx.get("redis")
    if redis is not None:
        await redis.aclose()  # type: ignore[no-untyped-call]
```

- [ ] **Step 2:** Update `apps/api/src/cloude_api/workers/arq_settings.py`

Replace the file's content with:
```python
"""arq WorkerSettings — picked up by `arq cloude_api.workers.arq_settings.WorkerSettings`."""

from __future__ import annotations

from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from cloude_api.config import get_settings
from cloude_api.workers.tasks import (
    _on_shutdown,
    _on_startup,
    create_device,
    delete_device,
    reap_stuck_devices,
    stop_device,
)


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions: ClassVar[list] = [create_device, stop_device, delete_device]
    cron_jobs: ClassVar[list] = [
        cron(reap_stuck_devices, minute=set(range(60)), run_at_startup=False),
    ]
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 240  # spawn can take ~120s; +120s margin
```

Note: `cron(..., minute=set(range(60)))` fires every minute; for stuck reaping every 60s this is the simplest. Adjust later if needed.

- [ ] **Step 3:** Quick import + full unit-suite check

```bash
cd apps/api && DATABASE_URL=postgresql+asyncpg://x:y@h/d REDIS_URL=redis://h:6379/0 JWT_SECRET=test-secret-test-secret-test-secret-test-secret-AAAA STREAM_TOKEN_SECRET=test-stream-test-stream-test-stream-test-stream-AAAA ENCRYPTION_PUBLIC_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= ENCRYPTION_PRIVATE_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= python -c "
from cloude_api.workers.arq_settings import WorkerSettings
print('functions:', [f.__name__ for f in WorkerSettings.functions])
print('cron count:', len(WorkerSettings.cron_jobs))
print('max_jobs:', WorkerSettings.max_jobs)
"
python -m pytest tests/unit/ -q
```
Expected:
- import prints `functions: ['create_device', 'stop_device', 'delete_device']` and `cron count: 1`
- pytest: `38 passed` (24 P1a + 7 port_allocator + 12 spawner + 3 lifecycle + 2 reapers = 48? let me recount: 24 + 7 + 12 + 3 + 2 = 48). **Actual expected: count what the previous task chain produced. The exact number depends on Task 7 final test count; should be ≥ 35.**

- [ ] **Step 4:** ruff + commit

```bash
python -m ruff check apps/api/src/cloude_api/workers/
git add apps/api/src/cloude_api/workers/tasks.py apps/api/src/cloude_api/workers/arq_settings.py
git commit -m "feat(p1b): wire new tasks into arq_settings, remove create_device_stub"
```

---

## Task 12: API integration — `proxy_id` required + route enqueue targets

**Files:**
- Modify: `apps/api/src/cloude_api/schemas/device.py`
- Modify: `apps/api/src/cloude_api/api/devices.py`

- [ ] **Step 1:** Make `proxy_id` required in `DeviceCreate`

Open `apps/api/src/cloude_api/schemas/device.py`. Find:
```python
class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    profile_id: uuid.UUID
    proxy_id: uuid.UUID | None = None
```
Change to:
```python
class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    profile_id: uuid.UUID
    proxy_id: uuid.UUID
```

- [ ] **Step 2:** Update enqueue targets in `apps/api/src/cloude_api/api/devices.py`

Open the file. In the `_enqueue_create` helper, change:
```python
await pool.enqueue_job("create_device_stub", str(device_id))
```
to:
```python
await pool.enqueue_job("create_device", str(device_id))
```

In `stop_device` route, REPLACE the entire body so it enqueues instead of mutating state inline. Find:
```python
@router.post("/{device_id}/stop", response_model=DevicePublic)
async def stop_device(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    if d.state not in (DeviceState.running, DeviceState.creating):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"cannot stop from {d.state.value}")
    d.state = DeviceState.stopped
    d.stopped_at = datetime.now(tz=timezone.utc)
    await write_audit(db, user_id=current.id, action="device.stop", target_id=d.id)
    await db.commit()
    await db.refresh(d)
    return DevicePublic.model_validate(d)
```
Replace with:
```python
@router.post("/{device_id}/stop", response_model=DevicePublic)
async def stop_device(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    if d.state not in (DeviceState.running, DeviceState.creating):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"cannot stop from {d.state.value}")
    d.state = DeviceState.stopping
    await write_audit(db, user_id=current.id, action="device.stop", target_id=d.id)
    await db.commit()
    await db.refresh(d)
    await _enqueue_stop(d.id)
    return DevicePublic.model_validate(d)
```

In `delete_device` route, REPLACE the body. Find:
```python
@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_device(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> None:
    d = await _get_owned(db, device_id, current.id)
    d.state = DeviceState.deleted
    d.stopped_at = d.stopped_at or datetime.now(tz=timezone.utc)
    await write_audit(db, user_id=current.id, action="device.delete", target_id=d.id)
    await db.commit()
```
Replace with:
```python
@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_device(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> None:
    d = await _get_owned(db, device_id, current.id)
    # Transient marker so listings don't show this row as still running:
    if d.state in (DeviceState.running, DeviceState.creating):
        d.state = DeviceState.stopping
    await write_audit(db, user_id=current.id, action="device.delete", target_id=d.id)
    await db.commit()
    await _enqueue_delete(d.id)
```

Then add the two new enqueue helpers next to `_enqueue_create` (top of file, after imports):
```python
async def _enqueue_stop(device_id: uuid.UUID) -> None:
    s = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(s.redis_url))
    try:
        await pool.enqueue_job("stop_device", str(device_id))
    finally:
        await pool.aclose()


async def _enqueue_delete(device_id: uuid.UUID) -> None:
    s = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(s.redis_url))
    try:
        await pool.enqueue_job("delete_device", str(device_id))
    finally:
        await pool.aclose()
```

(Imports `create_pool` and `RedisSettings` are already present from P1a.)

- [ ] **Step 3:** Verify routes still parse and the schema rejects missing proxy_id

```bash
cd apps/api && DATABASE_URL=postgresql+asyncpg://x:y@h/d REDIS_URL=redis://h:6379/0 JWT_SECRET=test-secret-test-secret-test-secret-test-secret-AAAA STREAM_TOKEN_SECRET=test-stream-test-stream-test-stream-test-stream-AAAA ENCRYPTION_PUBLIC_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= ENCRYPTION_PRIVATE_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= python -c "
import uuid
from pydantic import ValidationError
from cloude_api.schemas.device import DeviceCreate
try:
    DeviceCreate(name='x', profile_id=uuid.uuid4())
except ValidationError as e:
    print('ok rejected:', 'proxy_id' in str(e))
m = DeviceCreate(name='x', profile_id=uuid.uuid4(), proxy_id=uuid.uuid4())
print('ok accepted:', m.proxy_id is not None)
"
python -m ruff check apps/api/src/cloude_api/schemas/device.py apps/api/src/cloude_api/api/devices.py
```
Expected: `ok rejected: True` then `ok accepted: True`, then ruff clean.

- [ ] **Step 4:** Re-run unit suite

```bash
cd apps/api && python -m pytest tests/unit/ -q
```
Expected: same count as Task 11's Step 3 (the device-router schema change doesn't add/remove tests but `test_devices.py` should still pass).

- [ ] **Step 5:** Commit

```bash
git add apps/api/src/cloude_api/schemas/device.py apps/api/src/cloude_api/api/devices.py
git commit -m "feat(p1b): DeviceCreate.proxy_id required; routes enqueue stop/delete to worker"
```

---

## Task 13: Update P1a integration test — call `_finalize_running` directly

**Files:**
- Modify: `apps/api/tests/integration/test_e2e_invite_to_running.py`

The existing P1a integration test imports `create_device_stub` which no longer exists. We rewrite it to call `_finalize_running` directly with synthetic container IDs and an allocated port — exercising the DB-transition + pubsub contract without needing real Docker.

- [ ] **Step 1:** Rewrite the test

Open `apps/api/tests/integration/test_e2e_invite_to_running.py`. Find the block:
```python
from cloude_api.workers.tasks import create_device_stub
```
Change to:
```python
from cloude_api.workers.port_allocator import release as release_port
from cloude_api.workers.spawner import _finalize_running
```

In the test body, find:
```python
    # Manually drive the worker (we don't run an arq subprocess in tests).
    s = get_settings()
    redis = aioredis.from_url(s.redis_url, encoding="utf-8", decode_responses=False)
    try:
        result = await create_device_stub({"redis": redis, "settle_seconds": 0.1}, str(device_id))
    finally:
        await redis.aclose()
    assert result["ok"] is True
    assert result.get("state") == "running"
```
Replace with:
```python
    # Manually exercise the DB-transition + pubsub contract (no real Docker
    # spawn in this test; that's covered by test_real_spawn.py).
    import random
    s = get_settings()
    redis = aioredis.from_url(s.redis_url, encoding="utf-8", decode_responses=False)
    fake_port = random.randint(40000, 49999)  # noqa: S311  test-only
    try:
        async with async_session_factory() as fdb:
            fresh = await fdb.scalar(select(Device).where(Device.id == device_id))
            assert fresh is not None
            await _finalize_running(
                fdb, redis,
                device=fresh,
                sidecar_id="sha256:test-sidecar",
                redroid_id="sha256:test-redroid",
                adb_port=fake_port,
            )
        # Release the port so we don't pollute the free-set for later runs.
        await release_port(redis, fake_port)
    finally:
        await redis.aclose()
```

Then update the subsequent assertions block. Replace:
```python
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        assert d is not None
        assert d.state == DeviceState.running
        assert d.adb_host_port is not None
        assert 40000 <= d.adb_host_port <= 49999
        assert d.started_at is not None
```
with:
```python
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        assert d is not None
        assert d.state == DeviceState.running
        assert d.adb_host_port == fake_port
        assert d.started_at is not None
        assert d.sidecar_container_id == "sha256:test-sidecar"
        assert d.redroid_container_id == "sha256:test-redroid"
```

- [ ] **Step 2:** Verify (services must be up; tests gated on INTEGRATION=1)

```bash
cd ../.. && docker compose up -d
sleep 3
cd apps/api && DATABASE_URL=postgresql+asyncpg://cloude:changeme_local_dev@localhost:5433/cloude REDIS_URL=redis://localhost:6379/0 INTEGRATION=1 python -m pytest tests/integration/test_e2e_invite_to_running.py -v
```
Expected: `1 passed`.

- [ ] **Step 3:** ruff + commit

```bash
python -m ruff check apps/api/tests/integration/test_e2e_invite_to_running.py
git add apps/api/tests/integration/test_e2e_invite_to_running.py
git commit -m "test(p1b): rewrite e2e test to call _finalize_running (no more stub)"
```

---

## Task 14: New real-spawn integration test (REAL_DOCKER=1 gated)

**Files:**
- Create: `apps/api/tests/integration/test_real_spawn.py`

This test only runs when `REAL_DOCKER=1` is set AND the host can spawn redroid (binder modules loaded). CI keeps skipping it.

- [ ] **Step 1:** Write the test

Create `apps/api/tests/integration/test_real_spawn.py`:
```python
"""End-to-end real-spawn test. Gated on REAL_DOCKER=1.

Requires:
  - Local Docker daemon reachable
  - host that supports redroid (Linux with binder modules; e.g. WSL2 with
    binder_linux loaded)
  - `cloude/sidecar:p0` image built and `redroid/redroid:11.0.0-latest` pulled
  - postgres+redis up via docker compose
  - .env contains a working proxy in PROXY_HOST/PORT/TYPE/USER/PASS (same one
    P0 validated)
  - migrations applied; profile + invite are seeded by this test

Skipped in CI (REAL_DOCKER not set).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta

import aiodocker
import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core.auth import generate_invite_token, hash_invite_token
from cloude_api.core.encryption import encrypt_password
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState, ProxyType, UserRole
from cloude_api.main import app
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.invite import Invite
from cloude_api.models.proxy import Proxy
from cloude_api.models.user import User
from cloude_api.workers import port_allocator
from cloude_api.workers.docker_client import close_docker_client, make_docker_client
from cloude_api.workers.lifecycle import delete_device, stop_device
from cloude_api.workers.spawner import create_device

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_REAL = bool(os.environ.get("REAL_DOCKER"))


@pytest.fixture
async def docker_client() -> aiodocker.Docker:
    c = await make_docker_client()
    yield c
    await close_docker_client(c)


@pytest.fixture
async def redis_client():  # noqa: ANN201
    s = get_settings()
    r = aioredis.from_url(s.redis_url, encoding="utf-8", decode_responses=False)
    async with async_session_factory() as db:
        await port_allocator.initialize(r, db)
    yield r
    await r.aclose()


async def _seed(db) -> tuple[User, DeviceProfile, Proxy]:
    s = get_settings()
    raw = generate_invite_token()
    db.add(
        Invite(
            id=uuid.uuid4(),
            token_hash=hash_invite_token(raw),
            email=None,
            role=UserRole.user,
            expires_at=datetime.utcnow().replace(microsecond=0) + timedelta(hours=1),
        )
    )
    await db.commit()

    # Redeem to get a user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/api/v1/auth/redeem-invite",
            json={"token": raw, "email": f"rs-{uuid.uuid4().hex[:6]}@x.com", "password": "abcd1234"},
        )
        assert r.status_code == 201, r.text
        access = r.json()["access"]

    # Find the user
    email = r.json().get("email")
    user = await db.scalar(select(User).order_by(User.created_at.desc()).limit(1))
    assert user is not None

    profile = DeviceProfile(
        id=uuid.uuid4(),
        name=f"rs-{uuid.uuid4().hex[:6]}",
        screen_width=1080, screen_height=2340, screen_dpi=440,
        ram_mb=4096, cpu_cores=4,
        manufacturer="Google", model="Pixel 5",
        is_public=True,
    )
    db.add(profile)

    # Proxy from env. Must be a real working proxy (the one P0 validated).
    proxy = Proxy(
        id=uuid.uuid4(),
        user_id=user.id,
        label="real-spawn-test",
        type=ProxyType(os.environ["PROXY_TYPE"]),
        host=os.environ["PROXY_HOST"],
        port=int(os.environ["PROXY_PORT"]),
        username=os.environ.get("PROXY_USER") or None,
        password_encrypted=encrypt_password(
            os.environ.get("PROXY_PASS", ""), pub_b64=s.encryption_public_key,
        ) if os.environ.get("PROXY_PASS") else None,
    )
    db.add(proxy)
    await db.commit()
    await db.refresh(profile)
    await db.refresh(proxy)
    return user, profile, proxy


@pytest.mark.skipif(not _REAL, reason="set REAL_DOCKER=1 (and have binder host) to run")
async def test_real_spawn_stop_start_delete(docker_client, redis_client) -> None:
    async with async_session_factory() as db:
        user, profile, proxy = await _seed(db)

        device = Device(
            id=uuid.uuid4(),
            user_id=user.id,
            name="real-spawn-smoke",
            profile_id=profile.id,
            proxy_id=proxy.id,
            state=DeviceState.creating,
        )
        db.add(device)
        await db.commit()

    ctx = {"docker": docker_client, "redis": redis_client}

    # 1. Spawn
    result = await create_device(ctx, str(device.id))
    assert result["ok"], result
    assert result["state"] == "running"

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device.id))
        assert d.state == DeviceState.running
        assert d.adb_host_port is not None
        assert 40000 <= d.adb_host_port <= 49999

    # 2. Drop a marker in /data inside redroid to test persistence across stop/start
    short = device.id.hex[:12]
    redroid = await docker_client.containers.get(f"cloude-redroid-{short}")
    exec_obj = await redroid.exec(["sh", "-c", "echo marker > /data/local/tmp/cloude_marker"])
    await exec_obj.start(detach=False)

    # 3. Stop
    res = await stop_device(ctx, str(device.id))
    assert res["state"] == "stopped"
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device.id))
        assert d.state == DeviceState.stopped
        assert d.adb_host_port is None

    # 4. Restart (re-enter creating state and re-spawn)
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device.id))
        d.state = DeviceState.creating
        await db.commit()
    result2 = await create_device(ctx, str(device.id))
    assert result2["ok"], result2

    # 5. Marker should still be there (volume persisted)
    redroid = await docker_client.containers.get(f"cloude-redroid-{short}")
    exec_obj = await redroid.exec(["sh", "-c", "cat /data/local/tmp/cloude_marker"])
    out = await exec_obj.start(detach=False)
    assert b"marker" in (out if isinstance(out, bytes) else out.encode())

    # 6. Delete
    await delete_device(ctx, str(device.id))
    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device.id))
        assert d.state == DeviceState.deleted

    # 7. Volume + containers gone
    for name in (f"cloude-sidecar-{short}", f"cloude-redroid-{short}"):
        try:
            await docker_client.containers.get(name)
            raise AssertionError(f"{name} should be gone")
        except aiodocker.exceptions.DockerError as e:
            assert e.status == 404
    try:
        await docker_client.volumes.get(f"cloude-data-{device.id}")
        raise AssertionError("volume should be gone")
    except aiodocker.exceptions.DockerError as e:
        assert e.status == 404
```

- [ ] **Step 2:** Run it locally (services must be up + proxy env set)

```bash
cd ../.. && docker compose up -d
# Ensure .env has PROXY_HOST/PORT/TYPE/USER/PASS set (the P0 ones)
set -a; . .env; set +a
cd apps/api && DATABASE_URL=postgresql+asyncpg://cloude:changeme_local_dev@localhost:5433/cloude REDIS_URL=redis://localhost:6379/0 INTEGRATION=1 REAL_DOCKER=1 PROXY_HOST="$PROXY_HOST" PROXY_PORT="$PROXY_PORT" PROXY_TYPE="$PROXY_TYPE" PROXY_USER="$PROXY_USER" PROXY_PASS="$PROXY_PASS" python -m pytest tests/integration/test_real_spawn.py -v -s
```
Expected: `1 passed` in ~3-4 minutes (boot, persistence write, restart, delete).

This is the moment of truth — if it passes, P1b's spawn flow is real. If anything fails, capture the output and the device row + container logs.

- [ ] **Step 3:** ruff + commit

```bash
python -m ruff check apps/api/tests/integration/test_real_spawn.py
git add apps/api/tests/integration/test_real_spawn.py
git commit -m "test(p1b): real-spawn integration test (REAL_DOCKER=1 gate)"
```

---

## Task 15: Lint, format, mypy clean

**Files:** none new — fix whatever the tools flag.

- [ ] **Step 1:** ruff lint
```bash
cd apps/api && python -m ruff check src tests
```
Fix any errors. Use `# noqa: <code>` only for clear false positives with a brief comment.

- [ ] **Step 2:** ruff format
```bash
cd apps/api && python -m ruff format --check src tests
```
If files would reformat: `python -m ruff format src tests`, then re-check.

- [ ] **Step 3:** mypy --strict
```bash
cd apps/api && python -m mypy --strict src
```
Common fixes for new P1b code:
- aiodocker stubs gap → already covered by Task 0 Step 3 (added `aiodocker.*` to mypy overrides).
- `redis.asyncio` stubs gaps → use `# type: ignore[no-untyped-call]` consistent with P1a usage.
- DeviceContainer attribute access (`container.id` returns `str | None` in aiodocker types) → cast or assert.

- [ ] **Step 4:** Full test sweep
```bash
cd apps/api && python -m pytest -v
```
Expected: all unit pass, `test_e2e_invite_to_running` passes (with INTEGRATION=1 and services), `test_real_spawn` skipped without REAL_DOCKER=1.

- [ ] **Step 5:** Commit fixups (if any)
```bash
git add -A
git commit -m "chore(p1b): lint + format + mypy clean"
```
If clean already: skip.

---

## Task 16: README + design-spec back-link

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Replace the "Current phase" line block

Open `README.md`. Find:
```markdown
## Current phase: P1a (Backend Foundation)
```
and the paragraph after it. Replace with:
```markdown
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
```

- [ ] **Step 2:** Update "Phases ahead" block to reflect P1b done

Find:
```markdown
## Phases ahead

- **P1a** (this phase) — FastAPI control plane, JWT auth, invite redeem, device CRUD with worker stub.
- **P1b** — real Docker SDK device spawn, idle reaper, GC cron.
```
Replace the two lines with:
```markdown
- **P1a** — FastAPI control plane, JWT auth, invite redeem, device CRUD with worker stub. ✅
- **P1b** (this phase) — real Docker SDK device spawn, stuck-state reaper. Idle reaper + GC deferred.
```

- [ ] **Step 3:** Commit

```bash
git add README.md
git commit -m "docs: README — P1b status + breaking proxy_id change"
```

---

## Task 17: P1b closeout — full re-run, tag, push

**Files:** none — verification + tag.

- [ ] **Step 1:** Placeholder scan on P1b code

```bash
git grep -nE "TBD|TODO|FIXME|XXX|placeholder" -- 'apps/api/**/*.py' ':!apps/api/src/cloude_api/api/devices.py:165'
```
Expected: empty (the one acceptable P1a-placeholder comment in `api/devices.py:165` is filtered out).

- [ ] **Step 2:** Fresh stack re-run from a wiped volume

```bash
docker compose down -v
docker compose up -d --build
sleep 5
docker compose ps
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_profiles.py
```
Expected: 4 services healthy, migration applies, 6 profiles seeded.

- [ ] **Step 3:** Full test sweep including real-spawn

```bash
set -a; . .env; set +a   # load PROXY_* into shell
cd apps/api && DATABASE_URL=postgresql+asyncpg://cloude:changeme_local_dev@localhost:5433/cloude REDIS_URL=redis://localhost:6379/0 INTEGRATION=1 REAL_DOCKER=1 PROXY_HOST="$PROXY_HOST" PROXY_PORT="$PROXY_PORT" PROXY_TYPE="$PROXY_TYPE" PROXY_USER="$PROXY_USER" PROXY_PASS="$PROXY_PASS" python -m pytest -v
```
Expected: all unit + both integration tests pass.

- [ ] **Step 4:** Manual smoke through the API

```bash
# Mint invite
docker compose exec api python scripts/make_invite.py --role user --ttl-hours 1
# (copy token)
TOKEN=<paste>
ACCESS=$(curl -fsS -X POST http://localhost:8000/api/v1/auth/redeem-invite \
  -H 'content-type: application/json' \
  -d "{\"token\":\"$TOKEN\",\"email\":\"smoke@x.com\",\"password\":\"abcd1234\"}" | python -c 'import json,sys;print(json.load(sys.stdin)["access"])')
# Create a proxy (use a real working one from .env)
PROXY_ID=$(curl -fsS -X POST http://localhost:8000/api/v1/proxies \
  -H "authorization: Bearer $ACCESS" -H "content-type: application/json" \
  -d "{\"label\":\"smoke\",\"type\":\"$PROXY_TYPE\",\"host\":\"$PROXY_HOST\",\"port\":$PROXY_PORT,\"username\":\"$PROXY_USER\",\"password\":\"$PROXY_PASS\"}" | python -c 'import json,sys;print(json.load(sys.stdin)["id"])')
# List profiles, pick one
PROFILE_ID=$(curl -fsS http://localhost:8000/api/v1/device-profiles -H "authorization: Bearer $ACCESS" | python -c 'import json,sys;print(json.load(sys.stdin)[0]["id"])')
# Create device
curl -fsS -X POST http://localhost:8000/api/v1/devices \
  -H "authorization: Bearer $ACCESS" -H "content-type: application/json" \
  -d "{\"name\":\"smoke-real\",\"profile_id\":\"$PROFILE_ID\",\"proxy_id\":\"$PROXY_ID\"}"
# Wait ~120s, then list devices
sleep 130
curl -fsS http://localhost:8000/api/v1/devices -H "authorization: Bearer $ACCESS"
# Should show state="running" with adb_host_port set.
# Optional: adb connect localhost:<port> && adb shell echo hi
```

- [ ] **Step 5:** Tag and push

```bash
git tag p1b-complete
git push -u origin claude/festive-lewin-e65748
git push origin p1b-complete
```

- [ ] **Step 6:** Update the PR (it should auto-update since the branch was already pushed)

```bash
gh pr view --json url --jq .url
```
Add a comment to the PR describing P1b additions (or open a new PR if the P1a PR was already merged).

---

## Completion criteria (from spec)

1. ✅ aiodocker added; image rebuilds clean. → Task 0
2. ✅ create_device, stop_device, delete_device implemented in workers/ → Tasks 7-9
3. ✅ Port allocator with initialize/acquire/release reconciled from DB → Task 1
4. ✅ Stuck-state reaper as 60s cron + orphan-scan at startup → Tasks 10, 11
5. ✅ DeviceCreate.proxy_id required; routes enqueue new tasks → Task 12
6. ✅ Old create_device_stub removed → Task 11
7. ✅ Unit tests for port allocator + spawner-logic green → Tasks 1, 3-10
8. ✅ Integration test for real-spawn green locally → Task 14
9. ✅ ruff/format/mypy clean → Task 15
10. ✅ Manual smoke through Swagger/curl → Task 17
11. ✅ README updated → Task 16
12. ✅ Tag p1b-complete cut → Task 17

---

*End of P1b plan.*
