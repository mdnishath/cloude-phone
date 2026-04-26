"""GET /device-profiles — list available profiles for current user."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import or_, select

from cloude_api.core.deps import CurrentUser, DbSession
from cloude_api.models.device_profile import DeviceProfile
from cloude_api.schemas.device_profile import DeviceProfilePublic

router = APIRouter(prefix="/device-profiles", tags=["device-profiles"])


@router.get("", response_model=list[DeviceProfilePublic])
async def list_profiles(current: CurrentUser, db: DbSession) -> list[DeviceProfilePublic]:
    rows = (
        await db.scalars(
            select(DeviceProfile)
            .where(or_(DeviceProfile.is_public.is_(True), DeviceProfile.created_by == current.id))
            .order_by(DeviceProfile.name)
        )
    ).all()
    return [DeviceProfilePublic.model_validate(r) for r in rows]
