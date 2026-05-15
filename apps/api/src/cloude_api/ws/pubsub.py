"""Publish + subscribe helpers for `ws:device:{id}` channel."""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis


def channel_for(device_id: str) -> str:
    return f"ws:device:{device_id}"


async def publish_status(redis: aioredis.Redis, device_id: str, payload: dict[str, Any]) -> int:
    return int(await redis.publish(channel_for(device_id), json.dumps(payload)))
