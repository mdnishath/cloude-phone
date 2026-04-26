"""Unit tests for invite hashing + token-rotation logic (Redis mocked)."""
from __future__ import annotations

import pytest

from cloude_api.core import auth


def test_generate_invite_token_returns_url_safe_string() -> None:
    raw = auth.generate_invite_token()
    assert len(raw) >= 32
    # URL-safe base64 alphabet only
    assert all(c.isalnum() or c in "-_" for c in raw)


def test_hash_invite_token_is_deterministic_sha256_hex() -> None:
    h1 = auth.hash_invite_token("hello")
    h2 = auth.hash_invite_token("hello")
    assert h1 == h2 and len(h1) == 64


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0


@pytest.mark.asyncio
async def test_refresh_denylist_set_and_check() -> None:
    r = FakeRedis()
    jti = "j-1"
    assert await auth.is_refresh_revoked(r, jti) is False
    assert await auth.revoke_refresh(r, jti, ttl_seconds=60) is True
    assert await auth.is_refresh_revoked(r, jti) is True


@pytest.mark.asyncio
async def test_revoke_refresh_idempotent_returns_false_second_time() -> None:
    r = FakeRedis()
    assert await auth.revoke_refresh(r, "j-2", ttl_seconds=60) is True
    assert await auth.revoke_refresh(r, "j-2", ttl_seconds=60) is False
