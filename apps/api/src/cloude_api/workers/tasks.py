"""Background tasks. P1a only ships a stub for create_device.

P1b replaces `create_device_stub` with the real Docker SDK spawn flow:
allocate ADB port, render proxy creds, spawn sidecar, spawn redroid,
poll boot-complete, update DB, publish state. For now we prove the
queue + state-transition + pub/sub fan-out works end-to-end.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

import redis.asyncio as aioredis

from cloude_api.config import get_settings
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.ws.pubsub import channel_for

log = logging.getLogger("cloude.worker")


async def _publish(redis: aioredis.Redis, device_id: str, payload: dict[str, Any]) -> None:
    await redis.publish(channel_for(device_id), json.dumps(payload))


async def create_device_stub(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """Pretend to spawn a device. Sleeps, then flips creating → running.

    Real implementation lands in P1b. The contract here:
      * If device is in `creating` state, transition to `running`.
      * If device is in any other state, no-op (idempotent retry safe).
      * Always publish state to ws channel.
    """
    redis: aioredis.Redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)
    settle_seconds = float(ctx.get("settle_seconds", 2.0))

    log.info("create_device_stub start device_id=%s", device_id)
    await asyncio.sleep(settle_seconds)

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None:
            log.warning("device %s gone before stub completed", device_id)
            return {"ok": False, "reason": "device_missing"}
        if d.state != DeviceState.creating:
            log.info("device %s in state %s; stub no-op", device_id, d.state)
            return {"ok": True, "noop": True, "state": d.state.value}

        d.state = DeviceState.running
        d.started_at = datetime.now(tz=timezone.utc)
        d.adb_host_port = random.randint(40000, 49999)  # P1b: real port allocator + actual binding
        d.redroid_container_id = f"stub-redroid-{device_id.hex[:12]}"
        d.sidecar_container_id = f"stub-sidecar-{device_id.hex[:12]}"
        await db.commit()
        await db.refresh(d)

        await _publish(
            redis,
            str(device_id),
            {
                "device_id": str(device_id),
                "state": d.state.value,
                "state_reason": None,
                "adb_host_port": d.adb_host_port,
            },
        )
    log.info("create_device_stub done device_id=%s", device_id)
    return {"ok": True, "state": "running"}


async def _on_startup(ctx: dict[str, Any]) -> None:
    s = get_settings()
    ctx["redis"] = aioredis.from_url(s.redis_url, encoding="utf-8", decode_responses=False)
    log.info("worker startup: redis=%s", s.redis_url)


async def _on_shutdown(ctx: dict[str, Any]) -> None:
    redis: aioredis.Redis | None = ctx.get("redis")
    if redis is not None:
        await redis.aclose()
