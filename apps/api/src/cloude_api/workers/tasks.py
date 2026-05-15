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
