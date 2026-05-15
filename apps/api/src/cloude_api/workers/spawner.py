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

import uuid

import aiodocker

SIDECAR_IMAGE = "cloude/sidecar:p0"
REDROID_IMAGE = "redroid/redroid:11.0.0-latest"


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
            container = await docker.containers.get(name)
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
            vol = await docker.volumes.get(volume_name)
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                return
            return
        try:
            await vol.delete()
        except aiodocker.exceptions.DockerError:
            return
