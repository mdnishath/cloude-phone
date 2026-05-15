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
