"""Hardware template chosen at device-create time."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.models.base import Base


class DeviceProfile(Base):
    __tablename__ = "device_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    android_version: Mapped[str] = mapped_column(String(8), nullable=False, default="11")
    screen_width: Mapped[int] = mapped_column(Integer, nullable=False)
    screen_height: Mapped[int] = mapped_column(Integer, nullable=False)
    screen_dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    ram_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    manufacturer: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
