"""End-to-end smoke. Requires: `docker compose up -d postgres redis`
and migrations applied. Run with: `pytest -m integration tests/integration`.

The test:
  1. Mints an invite directly in DB.
  2. Redeems via HTTP.
  3. Logs in.
  4. Creates a device.
  5. Manually invokes the worker stub (we don't run a real arq worker here;
     calling the function directly with an in-memory ctx is enough to prove
     the state-transition + pub/sub contract).
  6. Asserts state is `running` and adb_host_port is set.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core.auth import generate_invite_token, hash_invite_token
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState, UserRole
from cloude_api.main import app
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.invite import Invite
from cloude_api.workers.port_allocator import release as release_port
from cloude_api.workers.spawner import _finalize_running

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# Skip the entire module (including fixtures) when INTEGRATION env var is absent.
# The guard used to live inside the test body, but that let fixtures run first and
# ERROR on a missing postgres connection before the skip could fire.
_integration_enabled = bool(os.environ.get("INTEGRATION") or os.environ.get("PYTEST_INTEGRATION"))

if not _integration_enabled:
    pytestmark.append(pytest.mark.skip(reason="set INTEGRATION=1 to run integration tests"))


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


@pytest.fixture
async def seed_profile() -> DeviceProfile:
    async with async_session_factory() as db:
        prof = DeviceProfile(
            id=uuid.uuid4(),
            name=f"int-test-{uuid.uuid4().hex[:6]}",
            screen_width=1080,
            screen_height=2340,
            screen_dpi=440,
            ram_mb=4096,
            cpu_cores=4,
            manufacturer="Google",
            model="Pixel 5",
            is_public=True,
        )
        db.add(prof)
        await db.commit()
        await db.refresh(prof)
        return prof


async def test_invite_to_running_smoke(client: AsyncClient, seed_profile: DeviceProfile) -> None:
    raw = generate_invite_token()
    async with async_session_factory() as db:
        db.add(
            Invite(
                id=uuid.uuid4(),
                token_hash=hash_invite_token(raw),
                email=None,
                role=UserRole.user,
                expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
            )
        )
        await db.commit()

    email = f"int-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/api/v1/auth/redeem-invite",
        json={"token": raw, "email": email, "password": "password-1234"},
    )
    assert r.status_code == 201, r.text
    access = r.json()["access"]
    auth = {"authorization": f"Bearer {access}"}

    r = await client.post(
        "/api/v1/proxies",
        headers=auth,
        json={"label": "smoke-proxy", "type": "socks5", "host": "127.0.0.1", "port": 1080},
    )
    assert r.status_code == 201, r.text
    proxy_id = r.json()["id"]

    r = await client.post(
        "/api/v1/devices",
        headers=auth,
        json={"name": "smoke", "profile_id": str(seed_profile.id), "proxy_id": proxy_id},
    )
    assert r.status_code == 201, r.text
    device_id = uuid.UUID(r.json()["id"])
    assert r.json()["state"] == "creating"

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
                fdb,
                redis,
                device=fresh,
                sidecar_id="sha256:test-sidecar",
                redroid_id="sha256:test-redroid",
                adb_port=fake_port,
            )
        # Release the port so we don't pollute the free-set for later runs.
        await release_port(redis, fake_port)
    finally:
        await redis.aclose()

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        assert d is not None
        assert d.state == DeviceState.running
        assert d.adb_host_port == fake_port
        assert d.started_at is not None
        assert d.sidecar_container_id == "sha256:test-sidecar"
        assert d.redroid_container_id == "sha256:test-redroid"

    r = await client.get(f"/api/v1/devices/{device_id}/adb-info", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["host"] == "localhost"
    assert body["port"] == d.adb_host_port
    assert body["command"].startswith("adb connect localhost:")
