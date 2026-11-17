"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BusinessTableMixin, IdMixin

ACTIVITY_TYPES = ("note", "call", "meeting", "email", "task")


class Activity(BusinessTableMixin, Base):
    """A logged interaction or a task (FR-ACT-01, FR-ACT-02), linked to at least one record."""

    __tablename__ = "activity"
    __table_args__ = (
        CheckConstraint("type IN ('note', 'call', 'meeting', 'email', 'task')", name="type"),
        CheckConstraint(
            "num_nonnulls(lead_id, opportunity_id, organization_id, contact_id) >= 1",
            name="has_link",
        ),
        Index("ix_activity_updated_at_id", "updated_at", "id"),
        Index("ix_activity_lead_id", "lead_id"),
        Index("ix_activity_opportunity_id", "opportunity_id"),
        Index("ix_activity_organization_id", "organization_id"),
        Index("ix_activity_contact_id", "contact_id"),
        Index("ix_activity_owner_id", "owner_id"),
        Index(
            "ix_activity_assignee_open_tasks",
            "assignee_id",
            "due_at",
            postgresql_where=text("done_at IS NULL"),
        ),
    )

    type: Mapped[str] = mapped_column(String(10), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("lead.id"), nullable=True)
    opportunity_id: Mapped[UUID | None] = mapped_column(ForeignKey("opportunity.id"), nullable=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organization.id"), nullable=True
    )
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contact.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class TimelineEvent(IdMixin, Base):
    """A system event shown on record timelines (FR-ACT-03, ADR 0020).

    Written by the activity module's event subscriber in the same transaction as
    the change; `data` holds IDs and values, resolved to names when read.
    """

    __tablename__ = "timeline_event"
    __table_args__ = (Index("ix_timeline_event_entity", "entity_type", "entity_id", "occurred_at"),)

    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
