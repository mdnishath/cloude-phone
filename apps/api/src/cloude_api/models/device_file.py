"""Audit row for an APK install / file push / file pull operation.

This table is *audit only*. It does not store file bytes — uploaded files
live on host disk under /var/lib/cloude-phone/uploads/{user_id}/, with a
24h TTL cleanup cron (P1c). The row records what was attempted, by whom,
when, and the outcome.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import DeviceFileOp, DeviceFileState
from cloude_api.models.base import Base


class DeviceFile(Base):
    __tablename__ = "device_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    op: Mapped[DeviceFileOp] = mapped_column(
        SAEnum(DeviceFileOp, name="device_file_op", create_constraint=False, native_enum=True),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    state: Mapped[DeviceFileState] = mapped_column(
        SAEnum(
            DeviceFileState,
            name="device_file_state",
            create_constraint=False,
            native_enum=True,
        ),
        nullable=False,
        default=DeviceFileState.pending,
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (Index("ix_device_files_device_created", "device_id", "created_at"),)
