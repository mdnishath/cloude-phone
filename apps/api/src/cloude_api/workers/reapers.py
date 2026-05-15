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
                db,
                redis,
                device=d,
                reason=f"spawn timeout (stuck in 'creating' > {STUCK_THRESHOLD_SECONDS}s)",
            )
            log.warning("reaped stuck device %s", d.id)


async def orphan_scan(db: AsyncSession, redis: aioredis.Redis, docker: aiodocker.Docker) -> None:
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
                await docker.containers.get(name)  # type: ignore[no-untyped-call]
            except aiodocker.exceptions.DockerError as e:
                if e.status == 404:
                    found = False
                    break
        if not found:
            if d.adb_host_port is not None:
                await port_allocator.release(redis, d.adb_host_port)
            await _flip_error(
                db,
                redis,
                device=d,
                reason="containers missing after worker restart",
            )
            log.warning("orphan-scan flipped %s to error", d.id)
