"""Audit-log writer. Always called within an existing session/transaction."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from cloude_api.models.audit_log import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    target_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target_id=target_id,
            metadata_=metadata or {},
        )
    )
    await db.flush()
