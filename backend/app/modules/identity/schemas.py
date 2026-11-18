"""Pydantic request and response schemas."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.principal import RoleCode

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(value: str) -> str:
    """Basic shape check; the address is confirmed when the user receives the link."""
    if not _EMAIL.fullmatch(value):
        raise ValueError("invalid email")
    return value.lower()


EmailAddress = Annotated[str, Field(min_length=3, max_length=320), AfterValidator(_valid_email)]
Locale = Literal["en", "bg"]
HumanRole = Literal["admin", "sales_manager", "sales_rep", "viewer"]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- Authentication -----------------------------------------------------------


class LoginRequest(_Request):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class SessionUser(BaseModel):
    id: UUID
    full_name: str
    role: RoleCode
    locale: Locale


class LoginResponse(BaseModel):
    user: SessionUser


class PasswordSetRequest(_Request):
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


class PasswordTokenInfo(BaseModel):
    email: str
    purpose: Literal["set", "reset"]


class PasswordForgotRequest(_Request):
    email: str = Field(min_length=1, max_length=320)


class PasswordChangeRequest(_Request):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


# --- Current user -------------------------------------------------------------


class Me(BaseModel):
    principal_type: Literal["user", "integration"]
    id: UUID
    email: str
    full_name: str
    role: RoleCode
    locale: Locale
    permissions: list[str]
    # Integration clients (API spec 4): their system code and granted scopes.
    system: str | None = None
    scopes: list[str] = []
    # FR-AUTH-07: whether two-factor sign-in is on, and whether it must be set up first.
    mfa_enabled: bool = False
    mfa_setup_required: bool = False


class MeUpdate(_Request):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    locale: Locale | None = None


class SessionInfo(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool


# --- Users (administration) ---------------------------------------------------


class UserLookupItem(BaseModel):
    id: UUID
    full_name: str
    email: str


class UserLookupPage(BaseModel):
    items: list[UserLookupItem]
    total: int
    page: int
    page_size: int


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: RoleCode
    locale: Locale
    user_type: Literal["human", "service"]
    is_active: bool
    is_locked: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int


class UserCreate(_Request):
    email: EmailAddress
    full_name: str = Field(min_length=1, max_length=200)
    role: HumanRole
    locale: Locale = "en"


class UserUpdate(_Request):
    email: EmailAddress | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: HumanRole | None = None
    locale: Locale | None = None


class PasswordLink(BaseModel):
    """One-time link for the Admin to hand over; emailed as well when SMTP is set."""

    url: str
    expires_at: datetime
    emailed: bool


class UserCreated(BaseModel):
    user: UserOut
    set_password: PasswordLink


class RoleOut(BaseModel):
    code: RoleCode
    name: str
    permissions: list[str]


# --- Two-factor sign-in (FR-AUTH-07) ------------------------------------------------


class LoginMfaRequest(_Request):
    code: str = Field(min_length=6, max_length=20, description="TOTP code or a recovery code")


class MfaSetup(BaseModel):
    secret: str = Field(description="Base32 secret, for typing into an authenticator app")
    provisioning_uri: str = Field(description="otpauth:// URI, for a QR code")


class MfaConfirmRequest(_Request):
    code: str = Field(min_length=6, max_length=10)


class MfaRecoveryCodes(BaseModel):
    recovery_codes: list[str] = Field(description="Shown once; each works once")


class MfaDisableRequest(_Request):
    password: str = Field(min_length=1, max_length=128)
