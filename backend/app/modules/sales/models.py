"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

from app.core.db import Base, BusinessTableMixin, IdMixin, ImportedMixin, TimestampMixin
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


class Lead(BusinessTableMixin, ImportedMixin, Base):
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
    converted_opportunity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("opportunity.id", use_alter=True), nullable=True
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    search_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Optimistic concurrency (architecture 4.1): PATCH and actions must send it.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    source: Mapped[LeadSource | None] = relationship(lazy="joined")
    disqualification_reason: Mapped[DisqualificationReason | None] = relationship(lazy="joined")


class LossReason(IdMixin, TimestampMixin, ReferenceItemMixin, Base):
    """Configurable list (FR-OPP-05, FR-ADM-02)."""

    __tablename__ = "loss_reason"


class Pipeline(IdMixin, TimestampMixin, Base):
    """One default pipeline in R1 (assumption A3); paths are pipeline-scoped for later."""

    __tablename__ = "pipeline"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    stages: Mapped[list[PipelineStage]] = relationship(
        lazy="selectin", order_by="PipelineStage.position", back_populates="pipeline"
    )


class PipelineStage(IdMixin, TimestampMixin, Base):
    """Configurable stage (FR-OPP-02): open, won or lost, with a default probability."""

    __tablename__ = "pipeline_stage"
    __table_args__ = (
        CheckConstraint("stage_type IN ('open', 'won', 'lost')", name="stage_type"),
        CheckConstraint("default_probability BETWEEN 0 AND 100", name="default_probability"),
        Index("ix_pipeline_stage_pipeline_id", "pipeline_id"),
    )

    pipeline_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline.id"), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    name_bg: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    default_probability: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    stage_type: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    pipeline: Mapped[Pipeline] = relationship(back_populates="stages")


class Opportunity(BusinessTableMixin, ImportedMixin, Base):
    """TMF699 salesOpportunity: a qualified potential deal (FR-OPP-01..06)."""

    __tablename__ = "opportunity"
    __table_args__ = (
        CheckConstraint("probability BETWEEN 0 AND 100", name="probability"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="amount"),
        Index("ix_opportunity_updated_at_id", "updated_at", "id"),
        Index("ix_opportunity_owner_id", "owner_id"),
        Index("ix_opportunity_stage_id", "stage_id"),
        Index("ix_opportunity_organization_id", "organization_id"),
        Index("ix_opportunity_expected_close_date", "expected_close_date"),
        Index(
            "ix_opportunity_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organization.id"), nullable=False)
    primary_contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contact.id"), nullable=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    pipeline_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline.id"), nullable=False)
    stage_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_stage.id"), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    probability: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # True once a user sets the probability; moves then keep it (API spec section 10).
    probability_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("lead.id"), nullable=True)
    loss_reason_id: Mapped[UUID | None] = mapped_column(ForeignKey("loss_reason.id"), nullable=True)
    competitor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Maintained by the activity module (Phase 4b); drives the stale indicator.
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    search_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    stage: Mapped[PipelineStage] = relationship(lazy="joined")
    loss_reason: Mapped[LossReason | None] = relationship(lazy="joined")


class OpportunityStageHistory(IdMixin, Base):
    """Every stage change with who and when (FR-OPP-02 AC2)."""

    __tablename__ = "opportunity_stage_history"
    __table_args__ = (Index("ix_opportunity_stage_history_opportunity_id", "opportunity_id"),)

    opportunity_id: Mapped[UUID] = mapped_column(ForeignKey("opportunity.id"), nullable=False)
    from_stage_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("pipeline_stage.id"), nullable=True
    )
    to_stage_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_stage.id"), nullable=False)
    changed_by: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    from_stage: Mapped[PipelineStage | None] = relationship(
        foreign_keys=[from_stage_id], lazy="joined"
    )
    to_stage: Mapped[PipelineStage] = relationship(foreign_keys=[to_stage_id], lazy="joined")
