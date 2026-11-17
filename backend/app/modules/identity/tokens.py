"""Opaque random tokens; only their SHA-256 hashes are stored."""

import hashlib
import secrets


def new_token() -> tuple[str, str]:
    """Return (raw token for the user, hash to store). 256 bits of randomness."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
