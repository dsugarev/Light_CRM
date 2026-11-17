"""Password hashing (Argon2id) and the password policy (FR-AUTH-03)."""

import asyncio
from functools import cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12
# Upper bound so a huge input cannot be used to burn CPU in the hasher.
MAX_LENGTH = 128

# OWASP Password Storage Cheat Sheet: Argon2id, m=19 MiB, t=2, p=1.
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_COMMON_PASSWORDS = Path(__file__).parent / "data" / "common-passwords.txt"


@cache
def _common_passwords() -> frozenset[str]:
    lines = _COMMON_PASSWORDS.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().casefold() for line in lines if line.strip())


def policy_violations(password: str) -> list[str]:
    """Field error codes for a password that breaks the policy; empty when it is fine."""
    violations: list[str] = []
    if len(password) < MIN_LENGTH:
        violations.append("password.too_short")
    if len(password) > MAX_LENGTH:
        violations.append("password.too_long")
    if password.casefold() in _common_passwords():
        violations.append("password.too_common")
    return violations


async def hash_password(password: str) -> str:
    # Hashing is deliberately slow; keep it off the event loop.
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    def _verify() -> bool:
        try:
            return _hasher.verify(password_hash, password)
        except VerifyMismatchError, VerificationError, InvalidHashError:
            return False

    return await asyncio.to_thread(_verify)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@cache
def _dummy_hash() -> str:
    return _hasher.hash("dummy password for timing equalisation")


async def burn_verification_time(password: str) -> None:
    """Spend the same time as a real check, so unknown emails are not revealed by timing."""
    await verify_password(_dummy_hash(), password)
