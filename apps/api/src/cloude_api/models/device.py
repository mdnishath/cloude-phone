"""Per-instance device record. State-machine column drives lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, INET, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import DeviceState, ImageVariant
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

    # --- P1a extension columns (2026-04-26 upgrade design §4.1) ---
    image_variant: Mapped[ImageVariant] = mapped_column(
        SAEnum(ImageVariant, name="image_variant", create_constraint=False, native_enum=True),
        nullable=False,
        default=ImageVariant.vanilla,
        server_default=ImageVariant.vanilla.value,
    )
    current_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_known_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    last_known_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    auto_snapshot_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (Index("ix_devices_user_id_state", "user_id", "state"),)
