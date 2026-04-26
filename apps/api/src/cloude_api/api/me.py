"""GET /me — current user."""

from __future__ import annotations

from fastapi import APIRouter

from cloude_api.core.deps import CurrentUser
from cloude_api.schemas.user import UserPublic

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserPublic)
async def me(current: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(current)
