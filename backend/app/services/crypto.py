"""symmetric encryption for the AniList access token.

the token is encrypted at rest with Fernet (AES-128-CBC + HMAC) keyed from `FERNET_KEY`.
plaintext tokens never leave the backend and are never logged. decryption failure is
loud (`TokenDecryptionError`) rather than returning a bad/empty token silently.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class TokenDecryptionError(Exception):
    """raised when ciphertext cannot be decrypted (wrong key or tampered data)."""


@lru_cache
def _cipher() -> Fernet:
    # Fernet validates the key shape here; a malformed FERNET_KEY fails loud at first use.
    return Fernet(get_settings().fernet_key.encode("utf-8"))


def encrypt_token(plaintext: str) -> str:
    """encrypt an AniList access token. returns urlsafe-base64 ciphertext."""
    if not plaintext:
        raise ValueError("refusing to encrypt empty token")
    return _cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    """decrypt a stored token. raises TokenDecryptionError on any failure."""
    try:
        return _cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise TokenDecryptionError("failed to decrypt AniList token") from exc
