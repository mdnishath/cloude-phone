"""Auth-flow primitives shared by routes + scripts.

Includes:
- invite token generation + sha256 hashing
- refresh-token denylist via Redis (set-on-use, with TTL = refresh lifetime)

The denylist stores the *used* refresh JTI. When the client presents a
refresh, the route checks the JTI is NOT in the denylist, then atomically
adds it (using SET NX), then issues a fresh access+refresh pair.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Protocol


def generate_invite_token() -> str:
    """Return a 32-byte url-safe random token (~43 chars)."""
    return secrets.token_urlsafe(32)


def hash_invite_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class _RedisLike(Protocol):
    async def set(self, key: str, value: str, *, ex: int | None = ..., nx: bool = ...) -> bool: ...
    async def exists(self, key: str) -> int: ...


def _denylist_key(jti: str) -> str:
    return f"refresh:used:{jti}"


async def is_refresh_revoked(redis: _RedisLike, jti: str) -> bool:
    return bool(await redis.exists(_denylist_key(jti)))


async def revoke_refresh(redis: _RedisLike, jti: str, *, ttl_seconds: int) -> bool:
    """Mark a refresh JTI as used. Returns True if newly added, False if already revoked."""
    return bool(await redis.set(_denylist_key(jti), "1", ex=ttl_seconds, nx=True))
