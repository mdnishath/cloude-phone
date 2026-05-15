"""libsodium sealed-box wrapper for proxy passwords.

Sealed boxes give us "anyone-can-encrypt, only-recipient-can-decrypt" with
ephemeral sender keys baked into the ciphertext. The API server holds both
public and private keys (single-tenant); rotation is a future concern (P2+).
"""
from __future__ import annotations

import base64
import sys

from nacl.public import PrivateKey, PublicKey, SealedBox


def generate_keypair() -> tuple[str, str]:
    """Generate a new Curve25519 keypair, returned as base64 strings."""
    sk = PrivateKey.generate()
    pk = sk.public_key
    return (
        base64.b64encode(bytes(pk)).decode("ascii"),
        base64.b64encode(bytes(sk)).decode("ascii"),
    )


def _load_public(pub_b64: str) -> PublicKey:
    return PublicKey(base64.b64decode(pub_b64))


def _load_private(priv_b64: str) -> PrivateKey:
    return PrivateKey(base64.b64decode(priv_b64))


def encrypt_password(plaintext: str, *, pub_b64: str) -> bytes:
    """Encrypt with the public key. Output is opaque bytes for `proxies.password_encrypted`."""
    if not plaintext:
        return b""
    box = SealedBox(_load_public(pub_b64))
    return bytes(box.encrypt(plaintext.encode("utf-8")))


def decrypt_password(ciphertext: bytes, *, pub_b64: str, priv_b64: str) -> str:
    """Decrypt. Raises if ciphertext was forged or wrong key."""
    if not ciphertext:
        return ""
    pk = _load_public(pub_b64)
    sk = _load_private(priv_b64)
    box = SealedBox(sk)  # SealedBox decrypt only needs the recipient secret key
    _ = pk  # kept for symmetry / future explicit verification
    return box.decrypt(ciphertext).decode("utf-8")


def _cli() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "keygen":
        pub, priv = generate_keypair()
        print(f"ENCRYPTION_PUBLIC_KEY={pub}")
        print(f"ENCRYPTION_PRIVATE_KEY={priv}")
        return 0
    print("usage: python -m cloude_api.core.encryption keygen", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
