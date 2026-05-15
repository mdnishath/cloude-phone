"""Per-instance device record. State-machine column drives lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import DeviceState
from cloude_api.models.base import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_profiles.id"), nullable=False
    )
    proxy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[DeviceState] = mapped_column(
        SAEnum(DeviceState, name="device_state", create_constraint=False, native_enum=True),
        nullable=False,
        default=DeviceState.creating,
        index=True,
    )
    state_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    redroid_container_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sidecar_container_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adb_host_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (Index("ix_devices_user_id_state", "user_id", "state"),)
