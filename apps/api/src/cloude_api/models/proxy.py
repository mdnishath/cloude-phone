"""User-owned proxy config. password_encrypted is libsodium sealed box."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cloude_api.enums import ProxyType
from cloude_api.models.base import Base


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[ProxyType] = mapped_column(
        SAEnum(ProxyType, name="proxy_type", create_constraint=False, native_enum=True),
        nullable=False,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    # --- P1a extension columns (2026-04-26 upgrade design §4.5) ---
    session_username_template: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="{user}-session-{session}",
        server_default="{user}-session-{session}",
    )
    supports_rotation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
