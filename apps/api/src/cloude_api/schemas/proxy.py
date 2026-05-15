from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cloude_api.enums import ProxyType


class ProxyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    type: ProxyType
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=512)


class ProxyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    type: ProxyType
    host: str
    port: int
    username: str | None
    has_password: bool
    created_at: datetime
