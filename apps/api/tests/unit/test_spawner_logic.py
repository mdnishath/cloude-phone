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


@pytest.mark.asyncio
async def test_spawn_sidecar_passes_expected_config() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_container.id = "sha256:abcdef"
    docker.containers.run = AsyncMock(return_value=fake_container)

    cid = await spawner.spawn_sidecar(
        docker,
        name="cloude-sidecar-aaaabbbbcccc",
        adb_port=40500,
        proxy_host="proxy.example.com",
        proxy_port=1080,
        proxy_type="socks5",
        proxy_user="u",
        proxy_pass="p",
        labels={"cloude.device_id": "xx"},
    )
    assert cid == "sha256:abcdef"

    call_kwargs = docker.containers.run.await_args.kwargs
    assert call_kwargs["name"] == "cloude-sidecar-aaaabbbbcccc"
    cfg = call_kwargs["config"]
    assert cfg["Image"] == "cloude/sidecar:p0"
    assert cfg["Labels"] == {"cloude.device_id": "xx"}
    env = set(cfg["Env"])
    assert "PROXY_HOST=proxy.example.com" in env
    assert "PROXY_PORT=1080" in env
    assert "PROXY_TYPE=socks5" in env
    assert "PROXY_USER=u" in env
    assert "PROXY_PASS=p" in env
    hc = cfg["HostConfig"]
    assert hc["CapAdd"] == ["NET_ADMIN", "NET_RAW"]
    assert hc["Sysctls"] == {"net.ipv4.ip_forward": "1"}
    assert hc["PortBindings"] == {"5555/tcp": [{"HostPort": "40500"}]}
    assert hc["RestartPolicy"] == {"Name": "no"}
    assert cfg["ExposedPorts"] == {"5555/tcp": {}}


@pytest.mark.asyncio
async def test_spawn_redroid_passes_expected_config() -> None:
    docker = MagicMock(spec=aiodocker.Docker)
    docker.containers = MagicMock()
    fake_container = MagicMock()
    fake_container.id = "sha256:redroidid"
    docker.containers.run = AsyncMock(return_value=fake_container)

    cid = await spawner.spawn_redroid(
        docker,
        name="cloude-redroid-aaaabbbbcccc",
        sidecar_name="cloude-sidecar-aaaabbbbcccc",
        volume="cloude-data-xxxx",
        width=1080,
        height=2340,
        dpi=440,
        ram_mb=4096,
        cpus=4,
        model="Pixel 5",
        manufacturer="Google",
        labels={"cloude.device_id": "xx"},
    )
    assert cid == "sha256:redroidid"

    call_kwargs = docker.containers.run.await_args.kwargs
    cfg = call_kwargs["config"]
    assert cfg["Image"] == "redroid/redroid:11.0.0-latest"
    assert cfg["Labels"] == {"cloude.device_id": "xx"}
    cmd = cfg["Cmd"]
    assert "androidboot.redroid_width=1080" in cmd
    assert "androidboot.redroid_height=2340" in cmd
    assert "androidboot.redroid_dpi=440" in cmd
    assert "androidboot.redroid_gpu_mode=guest" in cmd
    assert "ro.product.model=Pixel 5" in cmd
    assert "ro.product.manufacturer=Google" in cmd
    assert "net.dns1=127.0.0.1" in cmd
    assert "net.dns2=127.0.0.1" in cmd

    hc = cfg["HostConfig"]
    assert hc["NetworkMode"] == "container:cloude-sidecar-aaaabbbbcccc"
    assert hc["Privileged"] is True
    assert hc["Memory"] == 4096 * 1024 * 1024
    assert hc["CpuCount"] == 4
    assert hc["Binds"] == ["cloude-data-xxxx:/data"]
    assert hc["RestartPolicy"] == {"Name": "no"}
