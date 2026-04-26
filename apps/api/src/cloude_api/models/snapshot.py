"""Snapshot of a device's /data volume.

A snapshot is a compressed (zstd) tarball stored at ``local_path`` on the
host. ``s3_key`` is populated only when the user has S3/B2 backup enabled
(P1d) and the snapshot has been uploaded.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import SnapshotKind, SnapshotState
from cloude_api.models.base import Base


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[SnapshotKind] = mapped_column(
        SAEnum(SnapshotKind, name="snapshot_kind", create_constraint=False, native_enum=True),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    local_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    state: Mapped[SnapshotState] = mapped_column(
        SAEnum(SnapshotState, name="snapshot_state", create_constraint=False, native_enum=True),
        nullable=False,
        default=SnapshotState.creating,
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_snapshots_device_created", "device_id", "created_at"),
    )
