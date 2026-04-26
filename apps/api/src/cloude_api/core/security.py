"""Password hashing (argon2id) + JWT issue/decode (HS256)."""

from __future__ import annotations

import time
import uuid
from typing import Any, cast

from jose import jwt
from passlib.context import CryptContext

from cloude_api.config import get_settings

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"  # noqa: S105
REFRESH_TOKEN_TYPE = "refresh"  # noqa: S105


def _now() -> int:
    return int(time.time())


def hash_password(plaintext: str) -> str:
    return cast(str, _pwd.hash(plaintext))


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return cast(bool, _pwd.verify(plaintext, hashed))
    except Exception:
        return False


def _encode(payload: dict[str, Any]) -> str:
    s = get_settings()
    return cast(str, jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm))


def create_access_token(*, subject: str, extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": subject,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + s.jwt_access_ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return _encode(payload)


def create_refresh_token(*, subject: str) -> str:
    s = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": subject,
        "type": REFRESH_TOKEN_TYPE,
        "iat": now,
        "exp": now + s.jwt_refresh_ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    return _encode(payload)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    return cast(dict[str, Any], jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm]))
