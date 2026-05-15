"""arq WorkerSettings — picked up by `arq cloude_api.workers.arq_settings.WorkerSettings`."""

from __future__ import annotations

from typing import Any, ClassVar

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
    functions: ClassVar[list[Any]] = [create_device, stop_device, delete_device]
    cron_jobs: ClassVar[list[Any]] = [
        cron(reap_stuck_devices, minute=set(range(60)), run_at_startup=False),
    ]
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 240  # spawn can take ~120s; +120s margin
