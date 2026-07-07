import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.config import get_settings

_NONCE_LENGTH = 12  # 96 bits, the standard/recommended nonce size for AES-GCM


def _key() -> bytes:
    settings = get_settings()
    # Accept either a urlsafe-base64-encoded key (the documented .env format, e.g. from
    # secrets.token_urlsafe(32)) or raw bytes of the right length, so a manually-typed 32-byte
    # ASCII key also works without erroring.
    raw = settings.gmail_token_encryption_key.encode("utf-8")
    if len(raw) == 32:
        return raw
    padded = raw + b"=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded)


def encrypt_token(plaintext: str) -> str:
    """AES-256-GCM encrypt, for Gmail access/refresh tokens at rest. Output is a single
    urlsafe-base64 string (nonce prepended to ciphertext) suitable for a Text column."""
    aesgcm = AESGCM(_key())
    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    aesgcm = AESGCM(_key())
    raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    nonce, encrypted = raw[:_NONCE_LENGTH], raw[_NONCE_LENGTH:]
    return aesgcm.decrypt(nonce, encrypted, None).decode("utf-8")
