"""Organisations, contacts and the industries list (Phase 2).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17

- industry: configurable list owned by the party module (ADR 0016), seeded.
- organization / contact: business tables with (updated_at, id) indexes for sync
  mode and trigram (pg_trgm) GIN indexes on the folded search text.
- updated_at maintained by the set_updated_at() trigger from 0002.

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "industry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column("name_bg", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_industry")),
        sa.UniqueConstraint("code", name=op.f("uq_industry_code")),
    )
    op.create_table(
        "organization",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_normalized", sa.String(length=200), nullable=False),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("registration_number", sa.String(length=13), nullable=True),
        sa.Column("vat_number", sa.String(length=14), nullable=True),
        sa.Column("industry_id", sa.Uuid(), nullable=True),
        sa.Column("size_band", sa.String(length=10), nullable=True),
        sa.Column("website", sa.String(length=300), nullable=True),
        sa.Column("address_line", sa.String(length=200), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=2), server_default="BG", nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name=op.f("ck_organization_country")),
        sa.CheckConstraint(
            "size_band IS NULL OR size_band IN ('1-9', '10-49', '50-249', '250+')",
            name=op.f("ck_organization_size_band"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_organization_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["industry_id"], ["industry.id"], name=op.f("fk_organization_industry_id_industry")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["app_user.id"], name=op.f("fk_organization_owner_id_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_organization_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization")),
    )
    op.create_index("ix_organization_industry_id", "organization", ["industry_id"], unique=False)
    op.create_index(
        "ix_organization_name_normalized", "organization", ["name_normalized"], unique=False
    )
    op.create_index(
        "ix_organization_name_normalized_trgm",
        "organization",
        ["name_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_normalized": "gin_trgm_ops"},
    )
    op.create_index("ix_organization_owner_id", "organization", ["owner_id"], unique=False)
    op.create_index(
        "ix_organization_registration_number", "organization", ["registration_number"], unique=False
    )
    op.create_index(
        "ix_organization_search_text_trgm",
        "organization",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_organization_updated_at_id", "organization", ["updated_at", "id"], unique=False
    )
    op.create_table(
        "contact",
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("job_title", sa.String(length=150), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("preferred_locale", sa.String(length=2), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "preferred_locale IS NULL OR preferred_locale IN ('en', 'bg')",
            name=op.f("ck_contact_preferred_locale"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_contact_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_contact_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_contact_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact")),
    )
    op.create_index(
        "ix_contact_email_lower", "contact", [sa.literal_column("lower(email)")], unique=False
    )
    op.create_index("ix_contact_organization_id", "contact", ["organization_id"], unique=False)
    op.create_index(
        "ix_contact_search_text_trgm",
        "contact",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index("ix_contact_updated_at_id", "contact", ["updated_at", "id"], unique=False)
    for table in ("industry", "organization", "contact"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    op.execute(
        """
        INSERT INTO industry (id, code, name_en, name_bg, position) VALUES
            (gen_random_uuid(), 'telecommunications', 'Telecommunications', 'Телекомуникации', 1),
            (gen_random_uuid(), 'it_software', 'IT and software', 'ИТ и софтуер', 2),
            (gen_random_uuid(), 'finance_banking', 'Finance and banking', 'Финанси и банково дело', 3),
            (gen_random_uuid(), 'public_sector', 'Public sector', 'Публичен сектор', 4),
            (gen_random_uuid(), 'healthcare', 'Healthcare', 'Здравеопазване', 5),
            (gen_random_uuid(), 'manufacturing', 'Manufacturing', 'Производство', 6),
            (gen_random_uuid(), 'retail_wholesale', 'Retail and wholesale', 'Търговия на дребно и едро', 7),
            (gen_random_uuid(), 'energy_utilities', 'Energy and utilities', 'Енергетика и комунални услуги', 8),
            (gen_random_uuid(), 'transport_logistics', 'Transport and logistics', 'Транспорт и логистика', 9),
            (gen_random_uuid(), 'construction_real_estate', 'Construction and real estate', 'Строителство и недвижими имоти', 10),
            (gen_random_uuid(), 'education', 'Education', 'Образование', 11),
            (gen_random_uuid(), 'hospitality_tourism', 'Hospitality and tourism', 'Хотелиерство и туризъм', 12),
            (gen_random_uuid(), 'media', 'Media', 'Медии', 13),
            (gen_random_uuid(), 'other', 'Other', 'Друго', 14)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_contact_updated_at_id", table_name="contact")
    op.drop_index(
        "ix_contact_search_text_trgm",
        table_name="contact",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_index("ix_contact_organization_id", table_name="contact")
    op.drop_index("ix_contact_email_lower", table_name="contact")
    op.drop_table("contact")
    op.drop_index("ix_organization_updated_at_id", table_name="organization")
    op.drop_index(
        "ix_organization_search_text_trgm",
        table_name="organization",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_index("ix_organization_registration_number", table_name="organization")
    op.drop_index("ix_organization_owner_id", table_name="organization")
    op.drop_index(
        "ix_organization_name_normalized_trgm",
        table_name="organization",
        postgresql_using="gin",
        postgresql_ops={"name_normalized": "gin_trgm_ops"},
    )
    op.drop_index("ix_organization_name_normalized", table_name="organization")
    op.drop_index("ix_organization_industry_id", table_name="organization")
    op.drop_table("organization")
    op.drop_table("industry")
