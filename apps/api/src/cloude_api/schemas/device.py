from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cloude_api.enums import DeviceState


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    profile_id: uuid.UUID
    proxy_id: uuid.UUID | None = None


class DevicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    profile_id: uuid.UUID
    proxy_id: uuid.UUID | None
    state: DeviceState
    state_reason: str | None
    adb_host_port: int | None
    created_at: datetime
    started_at: datetime | None
    stopped_at: datetime | None


class AdbInfo(BaseModel):
    host: str
    port: int
    command: str


class StreamTokenResponse(BaseModel):
    token: str
    ttl_seconds: int
