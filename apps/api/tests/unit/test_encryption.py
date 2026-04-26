"""Tests for libsodium sealed-box helpers."""
from __future__ import annotations

import base64

from cloude_api.core.encryption import (
    decrypt_password,
    encrypt_password,
    generate_keypair,
)


def test_keypair_generates_two_distinct_b64_strings() -> None:
    pub, priv = generate_keypair()
    assert isinstance(pub, str) and isinstance(priv, str)
    assert pub != priv
    # base64-decoded length is 32 (Curve25519)
    assert len(base64.b64decode(pub)) == 32
    assert len(base64.b64decode(priv)) == 32


def test_round_trip_encrypts_and_decrypts() -> None:
    pub, priv = generate_keypair()
    plaintext = "hunter2-passw0rd!"
    ct = encrypt_password(plaintext, pub_b64=pub)
    assert isinstance(ct, bytes) and len(ct) > 0
    assert decrypt_password(ct, pub_b64=pub, priv_b64=priv) == plaintext


def test_two_encryptions_differ_due_to_random_nonce() -> None:
    pub, _priv = generate_keypair()
    a = encrypt_password("same", pub_b64=pub)
    b = encrypt_password("same", pub_b64=pub)
    assert a != b


def test_decrypt_with_wrong_key_raises() -> None:
    pub_a, _ = generate_keypair()
    _, priv_b = generate_keypair()
    ct = encrypt_password("secret", pub_b64=pub_a)
    try:
        decrypt_password(ct, pub_b64=pub_a, priv_b64=priv_b)
    except Exception:
        return
    raise AssertionError("expected decryption with wrong key to fail")
