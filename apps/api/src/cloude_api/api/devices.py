"""Device CRUD + state transitions. Lifecycle work is enqueued to arq."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core.audit import write_audit
from cloude_api.core.deps import CurrentUser, DbSession
from cloude_api.core.stream_token import issue as issue_stream_token
from cloude_api.enums import DeviceState
from cloude_api.models.device import Device
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.models.proxy import Proxy
from cloude_api.schemas.device import (
    AdbInfo,
    DeviceCreate,
    DevicePublic,
    StreamTokenResponse,
)

router = APIRouter(prefix="/devices", tags=["devices"])


async def _enqueue_create(device_id: uuid.UUID) -> None:
    s = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(s.redis_url))
    try:
        await pool.enqueue_job("create_device_stub", str(device_id))
    finally:
        await pool.aclose()


@router.post("", response_model=DevicePublic, status_code=status.HTTP_201_CREATED)
async def create_device(body: DeviceCreate, current: CurrentUser, db: DbSession) -> DevicePublic:
    profile = await db.scalar(select(DeviceProfile).where(DeviceProfile.id == body.profile_id))
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="profile not found")
    if not profile.is_public and profile.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="profile not visible")

    if body.proxy_id is not None:
        proxy = await db.scalar(
            select(Proxy).where(Proxy.id == body.proxy_id, Proxy.user_id == current.id)
        )
        if proxy is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="proxy not found")

    # Quota: count non-deleted devices
    active = (
        await db.scalars(
            select(Device).where(
                Device.user_id == current.id,
                Device.state.notin_([DeviceState.deleted, DeviceState.stopped]),
            )
        )
    ).all()
    if len(active) >= current.quota_instances:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail="quota exceeded")

    d = Device(
        id=uuid.uuid4(),
        user_id=current.id,
        name=body.name,
        profile_id=body.profile_id,
        proxy_id=body.proxy_id,
        state=DeviceState.creating,
    )
    db.add(d)
    await db.flush()
    await write_audit(db, user_id=current.id, action="device.create", target_id=d.id)
    await db.commit()
    await db.refresh(d)

    await _enqueue_create(d.id)
    return DevicePublic.model_validate(d)


@router.get("", response_model=list[DevicePublic])
async def list_devices(current: CurrentUser, db: DbSession) -> list[DevicePublic]:
    rows = (
        await db.scalars(
            select(Device)
            .where(Device.user_id == current.id, Device.state != DeviceState.deleted)
            .order_by(Device.created_at.desc())
        )
    ).all()
    return [DevicePublic.model_validate(r) for r in rows]


async def _get_owned(db: DbSession, device_id: uuid.UUID, user_id: uuid.UUID) -> Device:
    d = await db.scalar(select(Device).where(Device.id == device_id, Device.user_id == user_id))
    if d is None or d.state == DeviceState.deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="device not found")
    return d


@router.get("/{device_id}", response_model=DevicePublic)
async def get_device(device_id: uuid.UUID, current: CurrentUser, db: DbSession) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    return DevicePublic.model_validate(d)


@router.post("/{device_id}/start", response_model=DevicePublic)
async def start_device(device_id: uuid.UUID, current: CurrentUser, db: DbSession) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    if d.state not in (DeviceState.stopped, DeviceState.error):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"cannot start from {d.state.value}")
    d.state = DeviceState.creating  # re-enter creating; worker re-runs spawn job
    d.state_reason = None
    await write_audit(db, user_id=current.id, action="device.start", target_id=d.id)
    await db.commit()
    await db.refresh(d)
    await _enqueue_create(d.id)
    return DevicePublic.model_validate(d)


@router.post("/{device_id}/stop", response_model=DevicePublic)
async def stop_device(device_id: uuid.UUID, current: CurrentUser, db: DbSession) -> DevicePublic:
    d = await _get_owned(db, device_id, current.id)
    if d.state not in (DeviceState.running, DeviceState.creating):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"cannot stop from {d.state.value}")
    d.state = DeviceState.stopped
    d.stopped_at = datetime.now(tz=UTC)
    await write_audit(db, user_id=current.id, action="device.stop", target_id=d.id)
    await db.commit()
    await db.refresh(d)
    return DevicePublic.model_validate(d)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: uuid.UUID, current: CurrentUser, db: DbSession) -> None:
    d = await _get_owned(db, device_id, current.id)
    d.state = DeviceState.deleted
    d.stopped_at = d.stopped_at or datetime.now(tz=UTC)
    await write_audit(db, user_id=current.id, action="device.delete", target_id=d.id)
    await db.commit()


@router.get("/{device_id}/stream-token", response_model=StreamTokenResponse)
async def get_stream_token(
    device_id: uuid.UUID, current: CurrentUser, db: DbSession
) -> StreamTokenResponse:
    d = await _get_owned(db, device_id, current.id)
    if d.state != DeviceState.running:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="device not running")
    s = get_settings()
    return StreamTokenResponse(
        token=issue_stream_token(str(d.id)),
        ttl_seconds=s.stream_token_ttl_seconds,
    )


@router.get("/{device_id}/adb-info", response_model=AdbInfo)
async def get_adb_info(device_id: uuid.UUID, current: CurrentUser, db: DbSession) -> AdbInfo:
    d = await _get_owned(db, device_id, current.id)
    if d.state != DeviceState.running or d.adb_host_port is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="device not running with adb port")
    # P1a placeholder. P2 swaps to PUBLIC_HOST env so external clients can connect.
    host = "localhost"
    return AdbInfo(
        host=host,
        port=d.adb_host_port,
        command=f"adb connect {host}:{d.adb_host_port}",
    )
