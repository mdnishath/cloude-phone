"""Tests for password hashing + JWT issue/decode."""

from __future__ import annotations

import time

import pytest
from jose import JWTError

from cloude_api.core import security


def test_hash_password_returns_argon2_phc_string() -> None:
    h = security.hash_password("hunter2")
    assert h.startswith("$argon2id$")


def test_verify_password_accepts_correct() -> None:
    h = security.hash_password("hunter2")
    assert security.verify_password("hunter2", h) is True


def test_verify_password_rejects_wrong() -> None:
    h = security.hash_password("hunter2")
    assert security.verify_password("nope", h) is False


def test_create_access_and_decode_round_trip() -> None:
    tok = security.create_access_token(subject="user-123")
    payload = security.decode_token(tok)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_create_refresh_includes_jti() -> None:
    tok = security.create_refresh_token(subject="user-123")
    payload = security.decode_token(tok)
    assert payload["type"] == "refresh"
    assert "jti" in payload


def test_decode_rejects_tampered_token() -> None:
    tok = security.create_access_token(subject="user-123")
    tampered = tok[:-2] + ("aa" if tok[-2:] != "aa" else "bb")
    with pytest.raises(JWTError):
        security.decode_token(tampered)


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_now", lambda: int(time.time()) - 10_000)
    tok = security.create_access_token(subject="user-123")
    with pytest.raises(JWTError):
        security.decode_token(tok)
