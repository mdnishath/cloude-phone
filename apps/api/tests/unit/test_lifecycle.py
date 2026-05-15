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
