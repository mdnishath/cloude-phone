"""Tests for HMAC stream-token issue/verify (no Redis)."""
from __future__ import annotations

import time

import pytest

from cloude_api.core import stream_token as st


def test_token_is_three_segments() -> None:
    tok = st.issue("device-id-1")
    assert tok.count(":") == 2


def test_verify_round_trip_returns_payload() -> None:
    tok = st.issue("device-id-1")
    payload = st.verify(tok, expected_device_id="device-id-1")
    assert payload.device_id == "device-id-1"
    assert payload.exp > int(time.time())


def test_verify_rejects_wrong_device_id() -> None:
    tok = st.issue("device-id-1")
    with pytest.raises(st.StreamTokenError):
        st.verify(tok, expected_device_id="device-id-2")


def test_verify_rejects_tampered_signature() -> None:
    tok = st.issue("device-id-1")
    head, nonce, sig = tok.split(":")
    bad = f"{head}:{nonce}:{'A' * len(sig)}"
    with pytest.raises(st.StreamTokenError):
        st.verify(bad, expected_device_id="device-id-1")


def test_verify_rejects_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st, "_now", lambda: int(time.time()) - 10_000)
    tok = st.issue("device-id-1")
    monkeypatch.setattr(st, "_now", lambda: int(time.time()))
    with pytest.raises(st.StreamTokenError):
        st.verify(tok, expected_device_id="device-id-1")
