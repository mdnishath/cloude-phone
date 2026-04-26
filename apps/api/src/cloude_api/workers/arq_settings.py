"""arq WorkerSettings — picked up by `arq cloude_api.workers.arq_settings.WorkerSettings`."""
from __future__ import annotations

from arq.connections import RedisSettings

from cloude_api.config import get_settings
from cloude_api.workers.tasks import _on_shutdown, _on_startup, create_device_stub


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions = [create_device_stub]
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 120
