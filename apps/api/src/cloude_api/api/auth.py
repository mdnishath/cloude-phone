"""Auth routes: login, refresh, redeem-invite."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core import auth as auth_core
from cloude_api.core import security
from cloude_api.core.audit import write_audit
from cloude_api.core.deps import DbSession, RedisClient
from cloude_api.core.rate_limit import limiter
from cloude_api.models.invite import Invite
from cloude_api.models.user import User
from cloude_api.schemas.auth import (
    LoginRequest,
    RedeemInviteRequest,
    RefreshRequest,
    TokenPair,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: DbSession) -> TokenPair:
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    access = security.create_access_token(subject=str(user.id), extra={"role": user.role.value})
    refresh = security.create_refresh_token(subject=str(user.id))
    await write_audit(db, user_id=user.id, action="auth.login")
    await db.commit()
    return TokenPair(access=access, refresh=refresh)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
async def refresh_tokens(
    request: Request, body: RefreshRequest, db: DbSession, redis: RedisClient
) -> TokenPair:
    try:
        payload = security.decode_token(body.refresh)
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    if payload.get("type") != security.REFRESH_TOKEN_TYPE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not a refresh token")
    jti = payload.get("jti")
    sub = payload.get("sub")
    exp = payload.get("exp")
    if not jti or not sub or not exp:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="malformed refresh")

    if await auth_core.is_refresh_revoked(redis, jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="refresh reused")

    s = get_settings()
    ttl = max(int(exp) - int(datetime.now(tz=UTC).timestamp()), 0) or s.jwt_refresh_ttl_seconds
    added = await auth_core.revoke_refresh(redis, jti, ttl_seconds=ttl)
    if not added:
        # Race lost — another concurrent request claimed it first.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="refresh reused")

    try:
        user_id = uuid.UUID(sub)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="bad subject") from e
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="user gone")

    access = security.create_access_token(subject=str(user.id), extra={"role": user.role.value})
    new_refresh = security.create_refresh_token(subject=str(user.id))
    return TokenPair(access=access, refresh=new_refresh)


@router.post("/redeem-invite", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def redeem_invite(request: Request, body: RedeemInviteRequest, db: DbSession) -> TokenPair:
    token_hash = auth_core.hash_invite_token(body.token)
    invite = await db.scalar(select(Invite).where(Invite.token_hash == token_hash))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invalid invite")
    now = datetime.now(tz=UTC)
    if invite.redeemed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="already redeemed")
    if invite.expires_at < now:
        raise HTTPException(status.HTTP_410_GONE, detail="invite expired")

    target_email = (invite.email or body.email).lower()
    if invite.email and invite.email.lower() != body.email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="email does not match invite")

    existing = await db.scalar(select(User).where(User.email == target_email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="email already registered")

    user = User(
        id=uuid.uuid4(),
        email=target_email,
        password_hash=security.hash_password(body.password),
        role=invite.role,
    )
    db.add(user)
    invite.redeemed_at = now
    await db.flush()
    await write_audit(
        db,
        user_id=user.id,
        action="auth.redeem_invite",
        target_id=invite.id,
        metadata={"email": target_email},
    )
    await db.commit()

    access = security.create_access_token(subject=str(user.id), extra={"role": user.role.value})
    refresh = security.create_refresh_token(subject=str(user.id))
    return TokenPair(access=access, refresh=refresh)
