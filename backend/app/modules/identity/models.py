"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, BusinessTableMixin, IdMixin, TimestampMixin


class Role(IdMixin, TimestampMixin, Base):
    """Fixed roles (seeded by migration); permissions live in app.core.policy."""

    __tablename__ = "role"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class User(BusinessTableMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint("user_type IN ('human', 'service')", name="user_type"),
        CheckConstraint("locale IN ('en', 'bg')", name="locale"),
        Index("uq_app_user_email_lower", func.lower(text("email")), unique=True),
        Index(
            "uq_app_user_external_subject",
            "auth_provider",
            "external_subject",
            unique=True,
            postgresql_where=text("external_subject IS NOT NULL"),
        ),
    )

    user_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="human")
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("role.id"), nullable=False)
    locale: Mapped[str] = mapped_column(String(2), nullable=False, server_default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # SSO-ready (FR-AUTH-06): OIDC users are matched on (auth_provider, external_subject).
    auth_provider: Mapped[str] = mapped_column(String(32), nullable=False, server_default="local")
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Optional TOTP (FR-AUTH-07). Secrets are encrypted with APP_ENCRYPTION_KEY; recovery
    # codes are kept as SHA-256 hashes; the last accepted time step blocks code replay.
    mfa_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_pending_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_recovery_codes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    mfa_last_counter: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    role: Mapped[Role] = relationship(lazy="joined")

    @property
    def is_human(self) -> bool:
        return self.user_type == "human"


class UserSession(IdMixin, Base):
    """Server-side session; only the SHA-256 hash of the cookie token is stored."""

    __tablename__ = "user_session"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped[User] = relationship(lazy="joined")


class PasswordToken(IdMixin, Base):
    """One-time token for setting (new user) or resetting a password."""

    __tablename__ = "password_token"
    __table_args__ = (CheckConstraint("purpose IN ('set', 'reset')", name="purpose"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(8), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)

    user: Mapped[User] = relationship(lazy="joined", foreign_keys=[user_id])
