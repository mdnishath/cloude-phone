"""Tests for spawner helper logic (pure-Python + mocked docker)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import aiodocker
import pytest

from cloude_api.workers import spawner


def test_render_names_uses_first_12_hex_chars_for_containers() -> None:
    device_id = uuid.UUID("12345678-1234-1234-1234-1234567890ab")
    sidecar, redroid, volume, labels = spawner.render_names(device_id)
    assert sidecar == "cloude-sidecar-123456781234"
    assert redroid == "cloude-redroid-123456781234"
    assert volume == f"cloude-data-{device_id}"
    assert labels == {"cloude.device_id": str(device_id)}


def test_spawn_error_carries_human_reason() -> None:
    e = spawner.SpawnError("sidecar failed to start")
    assert str(e) == "sidecar failed to start"


@pytest.mark.asyncio
async def test_tear_down_ignores_missing_containers_and_volume() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    docker.volumes = MagicMock()

    missing_container = AsyncMock(
        side_effect=aiodocker.exceptions.DockerError(404, {"message": "no such container"})
    )
    missing_volume = AsyncMock(
        side_effect=aiodocker.exceptions.DockerError(404, {"message": "no such volume"})
    )
    docker.containers.get = missing_container
    docker.volumes.get = missing_volume

    # Should NOT raise even though both lookups return 404.
    await spawner.tear_down(
        docker, sidecar_name="sc", redroid_name="rd", volume_name="vol", remove_volume=True
    )


@pytest.mark.asyncio
async def test_tear_down_removes_existing_containers_and_volume_when_requested() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    docker.volumes = MagicMock()

    fake_sidecar = MagicMock()
    fake_sidecar.delete = AsyncMock()
    fake_redroid = MagicMock()
    fake_redroid.delete = AsyncMock()
    fake_volume = MagicMock()
    fake_volume.delete = AsyncMock()

    docker.containers.get = AsyncMock(side_effect=[fake_sidecar, fake_redroid])
    docker.volumes.get = AsyncMock(return_value=fake_volume)

    await spawner.tear_down(
        docker, sidecar_name="sc", redroid_name="rd", volume_name="vol", remove_volume=True
    )
    fake_sidecar.delete.assert_awaited_once_with(force=True)
    fake_redroid.delete.assert_awaited_once_with(force=True)
    fake_volume.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_tear_down_skips_volume_when_remove_volume_false() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    docker.volumes = MagicMock()

    docker.containers.get = AsyncMock(
        side_effect=aiodocker.exceptions.DockerError(404, {"message": "missing"})
    )
    docker.volumes.get = AsyncMock()

    await spawner.tear_down(
        docker, sidecar_name="sc", redroid_name="rd", volume_name="vol", remove_volume=False
    )
    docker.volumes.get.assert_not_called()
