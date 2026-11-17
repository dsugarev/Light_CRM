"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AuthorshipMixin, Base, IdMixin, TimestampMixin

ENTITY_TYPES = ("organizations", "contacts", "leads", "opportunities")
BATCH_STATUSES = ("uploaded", "mapped", "validated", "committed", "rolled_back")


class ImportBatch(IdMixin, TimestampMixin, AuthorshipMixin, Base):
    """One uploaded file and its way through mapping, validation and commit (FR-IMP-01)."""

    __tablename__ = "import_batch"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('organizations', 'contacts', 'leads', 'opportunities')",
            name="entity_type",
        ),
        CheckConstraint(
            "status IN ('uploaded', 'mapped', 'validated', 'committed', 'rolled_back')",
            name="status",
        ),
        CheckConstraint(
            "duplicate_mode IS NULL OR duplicate_mode IN ('skip', 'update')", name="duplicate_mode"
        ),
        Index("ix_import_batch_created_at", "created_at"),
    )

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="uploaded")
    columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    duplicate_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Uploaded contents are kept only until commit or discard, and at most 7 days (API spec 15).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportRow(IdMixin, Base):
    """A data row of a batch: the uploaded values, the validation result and what the
    commit did (the record, and its previous values when an existing record was updated)."""

    __tablename__ = "import_row"
    __table_args__ = (
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('valid', 'invalid', 'duplicate')", name="outcome"
        ),
        CheckConstraint(
            "action IS NULL OR action IN ('created', 'updated', 'skipped')", name="action"
        ),
        Index("ix_import_row_batch_row", "batch_id", "row_number", unique=True),
    )

    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)
    errors: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    match_id: Mapped[UUID | None] = mapped_column(nullable=True)
    match_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    action: Mapped[str | None] = mapped_column(String(10), nullable=True)
    record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # updated_at of the record right after the commit; a different value at rollback
    # time means someone changed the record since (API spec 15).
    stamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_result: Mapped[str | None] = mapped_column(String(60), nullable=True)
