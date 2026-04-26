"""WS /ws/devices/{id}/status — push state transitions to dashboard."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy import select

from cloude_api.core import security
from cloude_api.core.deps import get_redis
from cloude_api.db import async_session_factory
from cloude_api.models.device import Device
from cloude_api.ws.pubsub import channel_for

router = APIRouter()


async def _authenticate(token: str) -> uuid.UUID:
    payload = security.decode_token(token)
    if payload.get("type") != security.ACCESS_TOKEN_TYPE:
        raise JWTError("not an access token")
    return uuid.UUID(payload["sub"])


@router.websocket("/ws/devices/{device_id}/status")
async def device_status_ws(ws: WebSocket, device_id: uuid.UUID, token: str = Query(...)) -> None:
    try:
        user_id = await _authenticate(token)
    except (JWTError, ValueError, KeyError):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with async_session_factory() as db:
        d = await db.scalar(select(Device).where(Device.id == device_id, Device.user_id == user_id))
        if d is None:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await ws.accept()
        # Push current snapshot first
        await ws.send_json(
            {
                "device_id": str(d.id),
                "state": d.state.value,
                "state_reason": d.state_reason,
                "adb_host_port": d.adb_host_port,
            }
        )

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel_for(str(device_id)))
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
            if msg is None:
                # Heartbeat to keep connection alive
                await ws.send_json({"heartbeat": True})
                continue
            data = msg["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            await ws.send_text(data)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        await pubsub.unsubscribe(channel_for(str(device_id)))
        await pubsub.aclose()
