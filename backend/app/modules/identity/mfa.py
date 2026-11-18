"""TOTP two-factor sign-in helpers (FR-AUTH-07; RFC 6238 with 30-second steps).

- Codes are accepted one step either side of now, and never twice: the accepted step
  is stored and earlier or equal steps are refused (replay protection).
- Recovery codes are shown once at enrolment and stored as SHA-256 hashes; each works
  once.
- Between the password and the code, the browser holds a short-lived pending-sign-in
  token: an HMAC-signed user ID and expiry. It grants nothing but the code step.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote
from uuid import UUID

import pyotp

STEP_SECONDS = 30
RECOVERY_CODES = 10
PENDING_COOKIE = "mfa_pending"
PENDING_LIFETIME = timedelta(minutes=5)
ISSUER = "Light CRM"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def verify_code(secret: str, code: str, now: datetime, last_counter: int | None) -> int | None:
    """The time step the code belongs to, or None if it is wrong, expired or reused."""
    digits = code.replace(" ", "")
    if len(digits) != 6 or not digits.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    current = int(now.timestamp()) // STEP_SECONDS
    for counter in (current - 1, current, current + 1):
        if last_counter is not None and counter <= last_counter:
            continue
        if hmac.compare_digest(totp.generate_otp(counter), digits):
            return counter
    return None


def _normalize(code: str) -> str:
    return code.replace("-", "").replace(" ", "").lower()


def _hash(code: str) -> str:
    return hashlib.sha256(_normalize(code).encode()).hexdigest()


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """(codes to show once, hashes to store)."""
    codes = []
    for _ in range(RECOVERY_CODES):
        raw = secrets.token_hex(5)
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, [_hash(c) for c in codes]


def use_recovery_code(stored: list[str], code: str) -> list[str] | None:
    """The remaining hashes if `code` is one of them, else None."""
    if len(_normalize(code)) != 10:
        return None
    wanted = _hash(code)
    for index, candidate in enumerate(stored):
        if hmac.compare_digest(candidate, wanted):
            return stored[:index] + stored[index + 1 :]
    return None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _signature(key: str, payload: str) -> str:
    message = f"mfa-pending:{payload}".encode()
    return _b64(hmac.new(key.encode(), message, hashlib.sha256).digest())


def pending_token(key: str, user_id: UUID, now: datetime) -> str:
    payload = f"{user_id}.{int((now + PENDING_LIFETIME).timestamp())}"
    return f"{payload}.{_signature(key, payload)}"


def read_pending_token(key: str, token: str | None, now: datetime) -> UUID | None:
    if not token:
        return None
    payload, _, signature = token.rpartition(".")
    if not payload or not hmac.compare_digest(signature, _signature(key, payload)):
        return None
    user_part, _, expiry = payload.partition(".")
    try:
        if int(expiry) < now.timestamp():
            return None
        return UUID(user_part)
    except ValueError:
        return None


def cookie_header(token: str, max_age: int, path: str) -> str:
    """Set-Cookie value for the pending token (sent on an error response)."""
    return (
        f"{PENDING_COOKIE}={quote(token)}; Max-Age={max_age}; Path={path}; "
        "HttpOnly; Secure; SameSite=Strict"
    )
