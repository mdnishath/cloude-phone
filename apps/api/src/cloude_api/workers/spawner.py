"""Per-device sidecar+redroid spawn orchestration.

Public surface used by arq tasks:
    SpawnError                — non-retryable failure with human reason
    render_names(device_id)   — deterministic container/volume names + labels
    tear_down(...)            — best-effort cleanup, never raises
    spawn_sidecar(...)        — added in Task 4
    spawn_redroid(...)        — added in Task 5
    wait_for_sidecar_healthy  — added in Task 6
    wait_for_boot_completed   — added in Task 6
    create_device(...)        — arq task, added in Task 7
    _finalize_running(...)    — extracted helper, added in Task 7
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import aiodocker
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloude_api.config import get_settings
from cloude_api.core.audit import write_audit
from cloude_api.core.encryption import decrypt_password
from cloude_api.db import async_session_factory
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.proxy import Proxy
from cloude_api.workers import port_allocator
from cloude_api.ws.pubsub import channel_for

SIDECAR_IMAGE = "cloude/sidecar:p0"
REDROID_IMAGE = "redroid/redroid:11.0.0-latest"

log = logging.getLogger("cloude.worker.spawner")


class SpawnError(Exception):
    """Non-retryable spawn failure. The arq task catches this and sets state=error."""


def render_names(device_id: uuid.UUID) -> tuple[str, str, str, dict[str, str]]:
    """Returns (sidecar_name, redroid_name, volume_name, labels)."""
    short = device_id.hex[:12]
    sidecar_name = f"cloude-sidecar-{short}"
    redroid_name = f"cloude-redroid-{short}"
    volume_name = f"cloude-data-{device_id}"
    labels = {"cloude.device_id": str(device_id)}
    return sidecar_name, redroid_name, volume_name, labels


async def tear_down(
    docker: aiodocker.Docker,
    *,
    sidecar_name: str,
    redroid_name: str,
    volume_name: str | None,
    remove_volume: bool,
) -> None:
    """Best-effort removal. Never raises. 404s are ignored."""
    for name in (sidecar_name, redroid_name):
        try:
            container = await docker.containers.get(name)  # type: ignore[no-untyped-call]
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                continue
            # Anything else — log and move on; we don't want spawn failure to
            # cascade into a stuck row because cleanup itself errored.
            continue
        try:
            await container.delete(force=True)
        except aiodocker.exceptions.DockerError:
            continue
    if remove_volume and volume_name:
        try:
            vol = await docker.volumes.get(volume_name)  # type: ignore[attr-defined]
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                return
            return
        try:
            await vol.delete()
        except aiodocker.exceptions.DockerError:
            return


async def spawn_sidecar(
    docker: aiodocker.Docker,
    *,
    name: str,
    adb_port: int,
    proxy_host: str,
    proxy_port: int,
    proxy_type: str,
    proxy_user: str,
    proxy_pass: str,
    labels: dict[str, str],
) -> str:
    """Launch the sidecar container. Returns the container id."""
    container = await docker.containers.run(
        name=name,
        config={
            "Image": SIDECAR_IMAGE,
            "Labels": labels,
            "Env": [
                f"PROXY_HOST={proxy_host}",
                f"PROXY_PORT={proxy_port}",
                f"PROXY_TYPE={proxy_type}",
                f"PROXY_USER={proxy_user}",
                f"PROXY_PASS={proxy_pass}",
            ],
            "ExposedPorts": {"5555/tcp": {}},
            "HostConfig": {
                "CapAdd": ["NET_ADMIN", "NET_RAW"],
                "Sysctls": {"net.ipv4.ip_forward": "1"},
                "PortBindings": {"5555/tcp": [{"HostPort": str(adb_port)}]},
                "RestartPolicy": {"Name": "no"},
            },
        },
    )
    return str(container.id)


async def spawn_redroid(
    docker: aiodocker.Docker,
    *,
    name: str,
    sidecar_name: str,
    volume: str,
    width: int,
    height: int,
    dpi: int,
    ram_mb: int,
    cpus: int,
    model: str,
    manufacturer: str,
    labels: dict[str, str],
) -> str:
    """Launch the redroid container joined to the sidecar's netns. Returns id."""
    cmd = [
        f"androidboot.redroid_width={width}",
        f"androidboot.redroid_height={height}",
        f"androidboot.redroid_dpi={dpi}",
        "androidboot.redroid_gpu_mode=guest",
        f"ro.product.model={model}",
        f"ro.product.manufacturer={manufacturer}",
        "net.dns1=127.0.0.1",
        "net.dns2=127.0.0.1",
    ]
    container = await docker.containers.run(
        name=name,
        config={
            "Image": REDROID_IMAGE,
            "Cmd": cmd,
            "Labels": labels,
            "HostConfig": {
                "NetworkMode": f"container:{sidecar_name}",
                "Privileged": True,
                "Memory": ram_mb * 1024 * 1024,
                "CpuCount": cpus,
                "Binds": [f"{volume}:/data"],
                "RestartPolicy": {"Name": "no"},
            },
        },
    )
    return str(container.id)


async def _exec_capture(container: aiodocker.docker.DockerContainer, cmd: list[str]) -> str:
    """Run `cmd` in the container, return stdout as utf-8 text. Best-effort."""
    exec_obj = await container.exec(cmd, stdout=True, stderr=False)
    out = await exec_obj.start(detach=False)
    if isinstance(out, bytes):
        return out.decode("utf-8", errors="replace")
    return str(out)


async def wait_for_sidecar_healthy(
    docker: aiodocker.Docker, name: str, *, timeout_s: float = 20.0
) -> None:
    """Poll sidecar until `pgrep redsocks` returns a pid. Raises SpawnError on timeout."""
    container = await docker.containers.get(name)  # type: ignore[no-untyped-call]
    deadline = time.monotonic() + timeout_s
    while True:
        out = await _exec_capture(container, ["pgrep", "redsocks"])
        if out.strip():
            return
        if time.monotonic() >= deadline:
            raise SpawnError(f"sidecar '{name}' redsocks did not start within {timeout_s:.0f}s")
        await asyncio.sleep(1.0)


async def wait_for_boot_completed(
    docker: aiodocker.Docker, name: str, *, timeout_s: float = 120.0
) -> None:
    """Poll redroid until `getprop sys.boot_completed` returns `1`. Raises on timeout/exit."""
    container = await docker.containers.get(name)  # type: ignore[no-untyped-call]
    deadline = time.monotonic() + timeout_s
    while True:
        info = await container.show()
        status = info.get("State", {}).get("Status")
        if status == "exited":
            raise SpawnError(f"redroid '{name}' exited before boot completed")
        out = await _exec_capture(container, ["getprop", "sys.boot_completed"])
        if out.strip() == "1":
            return
        if time.monotonic() >= deadline:
            raise SpawnError(f"android boot did not complete within {timeout_s:.0f}s")
        await asyncio.sleep(2.0)


async def _finalize_running(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    device: Device,
    sidecar_id: str,
    redroid_id: str,
    adb_port: int,
) -> None:
    """Flip the device row to 'running' with all spawn metadata and publish to ws."""
    device.state = DeviceState.running
    device.state_reason = None
    device.adb_host_port = adb_port
    device.sidecar_container_id = sidecar_id[:64]
    device.redroid_container_id = redroid_id[:64]
    device.started_at = datetime.now(tz=UTC)
    await db.commit()
    payload = json.dumps(
        {
            "device_id": str(device.id),
            "state": device.state.value,
            "state_reason": None,
            "adb_host_port": adb_port,
        }
    )
    await redis.publish(channel_for(str(device.id)), payload)


async def _finalize_error(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    device: Device,
    reason: str,
) -> None:
    """Flip the device row to 'error' with a human reason, audit, publish."""
    device.state = DeviceState.error
    device.state_reason = reason
    device.adb_host_port = None
    await write_audit(
        db,
        user_id=device.user_id,
        action="device.spawn_failed",
        target_id=device.id,
        metadata={"reason": reason},
    )
    await db.commit()
    payload = json.dumps(
        {
            "device_id": str(device.id),
            "state": device.state.value,
            "state_reason": reason,
            "adb_host_port": None,
        }
    )
    await redis.publish(channel_for(str(device.id)), payload)


async def create_device(ctx: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """arq task: spawn one sidecar+redroid pair for the given device row."""
    docker: aiodocker.Docker = ctx["docker"]
    redis: aioredis.Redis = ctx["redis"]
    device_id = uuid.UUID(device_id_str)
    settings = get_settings()

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id))
        if d is None:
            log.warning("create_device: device %s missing", device_id)
            return {"ok": False, "reason": "device_missing"}
        if d.state != DeviceState.creating:
            log.info("create_device: device %s state=%s, no-op", device_id, d.state)
            return {"ok": True, "noop": True, "state": d.state.value}

        profile = await db.scalar(select(DeviceProfile).where(DeviceProfile.id == d.profile_id))
        if d.proxy_id is None:
            await _finalize_error(db, redis, device=d, reason="no proxy assigned")
            return {"ok": False, "reason": "no proxy"}
        proxy = await db.scalar(select(Proxy).where(Proxy.id == d.proxy_id))
        if profile is None or proxy is None:
            await _finalize_error(db, redis, device=d, reason="profile or proxy gone")
            return {"ok": False, "reason": "profile_or_proxy_missing"}

        proxy_password = (
            decrypt_password(
                proxy.password_encrypted,
                pub_b64=settings.encryption_public_key,
                priv_b64=settings.encryption_private_key,
            )
            if proxy.password_encrypted
            else ""
        )

        port = await port_allocator.acquire(redis)
        if port is None:
            await _finalize_error(db, redis, device=d, reason="port pool exhausted")
            return {"ok": False, "reason": "port_exhausted"}

        sidecar_name, redroid_name, volume_name, labels = render_names(d.id)
        sidecar_id = ""
        redroid_id = ""
        try:
            try:
                await docker.volumes.create({"Name": volume_name})  # type: ignore[no-untyped-call]
            except aiodocker.exceptions.DockerError as e:
                if e.status != 409:  # 409 = already exists, idempotent
                    raise SpawnError(f"volume create failed: {e}") from e

            sidecar_id = await spawn_sidecar(
                docker,
                name=sidecar_name,
                adb_port=port,
                proxy_host=proxy.host,
                proxy_port=proxy.port,
                proxy_type=proxy.type.value,
                proxy_user=proxy.username or "",
                proxy_pass=proxy_password,
                labels=labels | {"cloude.role": "sidecar"},
            )
            await wait_for_sidecar_healthy(docker, sidecar_name)

            redroid_id = await spawn_redroid(
                docker,
                name=redroid_name,
                sidecar_name=sidecar_name,
                volume=volume_name,
                width=profile.screen_width,
                height=profile.screen_height,
                dpi=profile.screen_dpi,
                ram_mb=profile.ram_mb,
                cpus=profile.cpu_cores,
                model=profile.model,
                manufacturer=profile.manufacturer,
                labels=labels | {"cloude.role": "redroid"},
            )
            await wait_for_boot_completed(docker, redroid_name)
        except SpawnError as e:
            log.warning("spawn failed for %s: %s", device_id, e)
            await tear_down(
                docker,
                sidecar_name=sidecar_name,
                redroid_name=redroid_name,
                volume_name=volume_name,
                remove_volume=False,
            )
            await port_allocator.release(redis, port)
            await _finalize_error(db, redis, device=d, reason=str(e))
            return {"ok": False, "reason": str(e)}

        await _finalize_running(
            db,
            redis,
            device=d,
            sidecar_id=sidecar_id,
            redroid_id=redroid_id,
            adb_port=port,
        )
        log.info("create_device done: %s on port %d", device_id, port)
        return {"ok": True, "state": "running", "adb_host_port": port}
