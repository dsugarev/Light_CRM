"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, BusinessTableMixin, IdMixin, TimestampMixin
from app.core.reference import ReferenceItemMixin

LEAD_STATUSES = ("new", "contacted", "qualified", "converted", "disqualified")
BANT_STATUSES = ("unknown", "no", "partial", "yes")
_BANT_CHECK = "IN ('unknown', 'no', 'partial', 'yes')"


class LeadSource(IdMixin, TimestampMixin, ReferenceItemMixin, Base):
    """Configurable list (FR-LEAD-01, FR-ADM-02)."""

    __tablename__ = "lead_source"


class DisqualificationReason(IdMixin, TimestampMixin, ReferenceItemMixin, Base):
    """Configurable list (FR-LEAD-02 AC1, FR-ADM-02)."""

    __tablename__ = "disqualification_reason"


class Lead(BusinessTableMixin, Base):
    """TMF699 salesLead: an unqualified prospect (FR-LEAD-01..06)."""

    __tablename__ = "lead"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'converted', 'disqualified')",
            name="status",
        ),
        CheckConstraint(f"bant_budget {_BANT_CHECK}", name="bant_budget"),
        CheckConstraint(f"bant_authority {_BANT_CHECK}", name="bant_authority"),
        CheckConstraint(f"bant_need {_BANT_CHECK}", name="bant_need"),
        CheckConstraint(f"bant_timeline {_BANT_CHECK}", name="bant_timeline"),
        CheckConstraint("estimated_value IS NULL OR estimated_value >= 0", name="estimated_value"),
        CheckConstraint("qualification_score BETWEEN 0 AND 100", name="qualification_score"),
        Index("ix_lead_updated_at_id", "updated_at", "id"),
        Index("ix_lead_owner_id", "owner_id"),
        Index("ix_lead_status", "status"),
        Index("ix_lead_source_id", "source_id"),
        Index("ix_lead_organization_id", "organization_id"),
        Index("ix_lead_created_at", "created_at"),
        Index(
            "ix_lead_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("lead_source.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="new")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)

    # BANT qualification (FR-LEAD-03): a status and a free-text note per item.
    bant_budget: Mapped[str] = mapped_column(String(8), nullable=False, server_default="unknown")
    bant_budget_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    bant_authority: Mapped[str] = mapped_column(String(8), nullable=False, server_default="unknown")
    bant_authority_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    bant_need: Mapped[str] = mapped_column(String(8), nullable=False, server_default="unknown")
    bant_need_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    bant_timeline: Mapped[str] = mapped_column(String(8), nullable=False, server_default="unknown")
    bant_timeline_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    fits_target_profile: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Stored so lists can sort by it; recomputed by the service on every BANT change.
    qualification_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )

    disqualification_reason_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("disqualification_reason.id"), nullable=True
    )
    disqualification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    disqualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optional links to existing records; set by conversion in Phase 4 as well.
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organization.id"), nullable=True
    )
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contact.id"), nullable=True)
    # Phase 4 adds the foreign key to opportunity (additive migration).
    converted_opportunity_id: Mapped[UUID | None] = mapped_column(nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    search_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Optimistic concurrency (architecture 4.1): PATCH and actions must send it.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    source: Mapped[LeadSource | None] = relationship(lazy="joined")
    disqualification_reason: Mapped[DisqualificationReason | None] = relationship(lazy="joined")
