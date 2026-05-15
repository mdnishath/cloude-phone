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

import os
import uuid
from datetime import UTC, datetime, timedelta

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
async def redis_client():
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
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
    )
    await db.commit()

    # Redeem to get a user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/api/v1/auth/redeem-invite",
            json={
                "token": raw,
                "email": f"rs-{uuid.uuid4().hex[:6]}@x.com",
                "password": "abcd1234",
            },
        )
        assert r.status_code == 201, r.text

    # Find the user
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
