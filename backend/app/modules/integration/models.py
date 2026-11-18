"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import AuthorshipMixin, Base, IdMixin, TimestampMixin
from app.core.reference import ReferenceItemMixin

ENTITY_TYPES = ("organization", "contact", "lead", "opportunity")


class ExternalSystem(IdMixin, TimestampMixin, ReferenceItemMixin, Base):
    """Applications the CRM integrates with (seeded: conclusion, erp, billing)."""

    __tablename__ = "external_system"


class IntegrationClient(IdMixin, TimestampMixin, AuthorshipMixin, Base):
    """FR-INT-01: one per integrated application, backed by a service user."""

    __tablename__ = "integration_client"
    __table_args__ = (
        CheckConstraint("rate_limit_per_minute BETWEEN 1 AND 100000", name="rate_limit"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_system_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_system.id"), nullable=False
    )
    service_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id"), nullable=False, unique=True
    )
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False)
    default_owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    ip_allowlist: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False)
    technical_contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="300"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    system: Mapped[ExternalSystem] = relationship(lazy="joined")


class ApiKey(IdMixin, TimestampMixin, Base):
    """FR-INT-02: `crm_<env>_<key_id>_<secret>`; only the SHA-256 of the secret is stored."""

    __tablename__ = "api_key"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("integration_client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_id: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)


class ExternalReference(IdMixin, TimestampMixin, AuthorshipMixin, Base):
    """FR-INT-04: a CRM record's identifier in another system (one per system)."""

    __tablename__ = "external_reference"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('organization', 'contact', 'lead', 'opportunity')",
            name="entity_type",
        ),
        UniqueConstraint("external_system_id", "entity_type", "external_id", name="external_id"),
        UniqueConstraint("entity_type", "entity_id", "external_system_id", name="record_system"),
    )

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    external_system_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_system.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    system: Mapped[ExternalSystem] = relationship(lazy="joined")


class IdempotencyRecord(IdMixin, Base):
    """FR-INT-06: the first response to a client's Idempotency-Key, kept 24 hours."""

    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint("client_id", "key", name="client_key"),
        CheckConstraint("status IN ('in_progress', 'completed')", name="status"),
        Index("ix_idempotency_record_expires_at", "expires_at"),
    )

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("integration_client.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    response_body: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntegrationUsage(Base):
    """FR-INT-08: requests and errors per client and hour."""

    __tablename__ = "integration_usage"
    __table_args__ = (PrimaryKeyConstraint("client_id", "hour", name="pk_integration_usage"),)

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("integration_client.id", ondelete="CASCADE"), nullable=False
    )
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
