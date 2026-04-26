"""Pydantic schemas for DeviceFile. Read schema only in P1a — Create lands in P1c."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from cloude_api.enums import DeviceFileOp, DeviceFileState


class DeviceFileRead(BaseModel):
    """Wire format returned by GET /devices/{id}/files/operations (P1c)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    user_id: uuid.UUID
    op: DeviceFileOp
    filename: str
    phone_path: str | None = None
    size_bytes: int
    state: DeviceFileState
    error_msg: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
