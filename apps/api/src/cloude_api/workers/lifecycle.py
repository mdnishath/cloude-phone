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
