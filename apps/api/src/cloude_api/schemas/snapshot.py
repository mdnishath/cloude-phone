"""Pydantic schemas for Snapshot. Read schema only in P1a — Create lands in P1c."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from cloude_api.enums import SnapshotKind, SnapshotState


class SnapshotRead(BaseModel):
    """Wire format returned by GET /snapshots/{id} and list endpoints (P1c)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    kind: SnapshotKind
    size_bytes: int
    local_path: str
    s3_key: str | None = None
    state: SnapshotState
    error_msg: str | None = None
    created_at: datetime
