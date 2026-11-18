"""Encryption for secrets the application must read back, such as webhook signing
secrets (architecture 4.5). API key secrets are hashed instead, never encrypted.

The Fernet key is derived from `APP_ENCRYPTION_KEY` with HKDF, so any long random
value works as the setting. Changing the setting makes stored values unreadable.
"""

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings

__all__ = ["InvalidToken", "decrypt", "encrypt"]


@lru_cache(maxsize=4)
def _fernet(key: str) -> Fernet:
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"light-crm stored secrets"
    ).derive(key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(settings: Settings, plaintext: str) -> str:
    return _fernet(settings.app_encryption_key).encrypt(plaintext.encode()).decode()


def decrypt(settings: Settings, token: str) -> str:
    """Raises `InvalidToken` when the value was encrypted with another key."""
    return _fernet(settings.app_encryption_key).decrypt(token.encode()).decode()
