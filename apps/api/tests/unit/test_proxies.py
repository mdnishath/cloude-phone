"""Unit-level test of proxy serialization helper.

End-to-end CRUD is covered by the integration test (Task 30+). Here we just
prove the to-public mapper masks passwords correctly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from cloude_api.api.proxies import _to_public
from cloude_api.enums import ProxyType
from cloude_api.models.proxy import Proxy


def _make(password: bytes | None) -> Proxy:
    p = Proxy(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        label="t",
        type=ProxyType.socks5,
        host="h",
        port=1080,
        username="u",
        password_encrypted=password,
    )
    p.created_at = datetime.now(tz=timezone.utc)
    return p


def test_to_public_marks_has_password_true_when_bytes_present() -> None:
    out = _to_public(_make(b"\x00\x01\x02"))
    assert out.has_password is True


def test_to_public_marks_has_password_false_when_none() -> None:
    out = _to_public(_make(None))
    assert out.has_password is False
    assert "password" not in out.model_dump()  # password never serialized
