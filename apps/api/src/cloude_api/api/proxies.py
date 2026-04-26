"""Proxy CRUD. Passwords encrypted at rest with libsodium sealed box."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from cloude_api.config import get_settings
from cloude_api.core.audit import write_audit
from cloude_api.core.deps import CurrentUser, DbSession
from cloude_api.core.encryption import encrypt_password
from cloude_api.models.proxy import Proxy
from cloude_api.schemas.proxy import ProxyCreate, ProxyPublic

router = APIRouter(prefix="/proxies", tags=["proxies"])


def _to_public(p: Proxy) -> ProxyPublic:
    return ProxyPublic(
        id=p.id,
        label=p.label,
        type=p.type,
        host=p.host,
        port=p.port,
        username=p.username,
        has_password=bool(p.password_encrypted),
        created_at=p.created_at,
    )


@router.post("", response_model=ProxyPublic, status_code=status.HTTP_201_CREATED)
async def create_proxy(body: ProxyCreate, current: CurrentUser, db: DbSession) -> ProxyPublic:
    s = get_settings()
    enc = (
        encrypt_password(body.password or "", pub_b64=s.encryption_public_key)
        if body.password
        else None
    )
    p = Proxy(
        id=uuid.uuid4(),
        user_id=current.id,
        label=body.label,
        type=body.type,
        host=body.host,
        port=body.port,
        username=body.username,
        password_encrypted=enc,
    )
    db.add(p)
    await db.flush()
    await write_audit(db, user_id=current.id, action="proxy.create", target_id=p.id)
    await db.commit()
    await db.refresh(p)
    return _to_public(p)


@router.get("", response_model=list[ProxyPublic])
async def list_proxies(current: CurrentUser, db: DbSession) -> list[ProxyPublic]:
    rows = (
        await db.scalars(
            select(Proxy).where(Proxy.user_id == current.id).order_by(Proxy.created_at.desc())
        )
    ).all()
    return [_to_public(p) for p in rows]


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_proxy(proxy_id: uuid.UUID, current: CurrentUser, db: DbSession) -> None:
    p = await db.scalar(select(Proxy).where(Proxy.id == proxy_id, Proxy.user_id == current.id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="proxy not found")
    await db.delete(p)
    await write_audit(db, user_id=current.id, action="proxy.delete", target_id=p.id)
    await db.commit()
