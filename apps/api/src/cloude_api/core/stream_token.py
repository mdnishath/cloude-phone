"""Single-use, short-TTL HMAC token gating /ws/devices/{id}/stream.

Format: base64url(device_id):base64url(nonce):base64url(hmac_sha256)
where the HMAC input is `device_id|nonce|exp`, exp is encoded as ascii int
inside `device_id` segment (we pack `<device_id>|<exp>`).

Single-use enforcement (Redis SETNX `stream:nonce:<nonce>` with TTL) lives in
the websocket route — not here, because nonce-store testing belongs in the
integration suite where Redis is real.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from cloude_api.config import get_settings


def _now() -> int:
    return int(time.time())


class StreamTokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class StreamPayload:
    device_id: str
    nonce: str
    exp: int


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue(device_id: str) -> str:
    s = get_settings()
    exp = _now() + s.stream_token_ttl_seconds
    head_raw = f"{device_id}|{exp}".encode()
    nonce = secrets.token_bytes(16)
    msg = head_raw + b"|" + nonce
    sig = hmac.new(s.stream_token_secret.encode("utf-8"), msg, hashlib.sha256).digest()
    return f"{_b64e(head_raw)}:{_b64e(nonce)}:{_b64e(sig)}"


def verify(token: str, *, expected_device_id: str) -> StreamPayload:
    s = get_settings()
    try:
        head_b64, nonce_b64, sig_b64 = token.split(":")
        head_raw = _b64d(head_b64)
        nonce = _b64d(nonce_b64)
        sig = _b64d(sig_b64)
    except (ValueError, IndexError) as e:
        raise StreamTokenError("malformed token") from e

    expected_sig = hmac.new(
        s.stream_token_secret.encode("utf-8"), head_raw + b"|" + nonce, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(sig, expected_sig):
        raise StreamTokenError("bad signature")

    try:
        device_id, exp_str = head_raw.decode("utf-8").split("|", 1)
        exp = int(exp_str)
    except (ValueError, UnicodeDecodeError) as e:
        raise StreamTokenError("malformed payload") from e

    if device_id != expected_device_id:
        raise StreamTokenError("device mismatch")
    if exp < _now():
        raise StreamTokenError("expired")

    return StreamPayload(device_id=device_id, nonce=nonce.hex(), exp=exp)
