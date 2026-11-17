"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, BusinessTableMixin, IdMixin, TimestampMixin
from app.core.reference import ReferenceItemMixin

SIZE_BANDS = ("1-9", "10-49", "50-249", "250+")


class Industry(IdMixin, TimestampMixin, ReferenceItemMixin, Base):
    """Configurable list (FR-ADM-02). Owned by party, which organisations need (ADR 0016)."""

    __tablename__ = "industry"


class Organization(BusinessTableMixin, Base):
    """TM Forum party: an organisation the business deals with (FR-PARTY-01)."""

    __tablename__ = "organization"
    __table_args__ = (
        CheckConstraint(
            "size_band IS NULL OR size_band IN ('1-9', '10-49', '50-249', '250+')",
            name="size_band",
        ),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="country"),
        Index("ix_organization_updated_at_id", "updated_at", "id"),
        Index("ix_organization_name_normalized", "name_normalized"),
        Index("ix_organization_registration_number", "registration_number"),
        Index("ix_organization_owner_id", "owner_id"),
        Index("ix_organization_industry_id", "industry_id"),
        Index(
            "ix_organization_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index(
            "ix_organization_name_normalized_trgm",
            "name_normalized",
            postgresql_using="gin",
            postgresql_ops={"name_normalized": "gin_trgm_ops"},
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Duplicate key (app.core.text.normalize_company_name) and folded search text,
    # both maintained by the service.
    name_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    registration_number: Mapped[str | None] = mapped_column(String(13), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(14), nullable=True)
    industry_id: Mapped[UUID | None] = mapped_column(ForeignKey("industry.id"), nullable=True)
    size_band: Mapped[str | None] = mapped_column(String(10), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(200), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="BG")
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    industry: Mapped[Industry | None] = relationship(lazy="joined")


class Contact(BusinessTableMixin, Base):
    """TM Forum individual (FR-PARTY-02). Ownership follows the organisation;
    without one, the creator owns the contact (API spec section 8)."""

    __tablename__ = "contact"
    __table_args__ = (
        CheckConstraint(
            "preferred_locale IS NULL OR preferred_locale IN ('en', 'bg')", name="preferred_locale"
        ),
        Index("ix_contact_updated_at_id", "updated_at", "id"),
        Index("ix_contact_organization_id", "organization_id"),
        Index("ix_contact_email_lower", func.lower(text("email"))),
        Index(
            "ix_contact_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preferred_locale: Mapped[str | None] = mapped_column(String(2), nullable=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organization.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Set by GDPR anonymisation (FR-ADM-04, Phase 8).
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization | None] = relationship(lazy="joined")
