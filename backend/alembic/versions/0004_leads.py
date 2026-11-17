"""Leads with BANT qualification, lead sources and disqualification reasons (Phase 3).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17

- lead_source, disqualification_reason: configurable lists owned by sales, seeded
  in English and Bulgarian (owner decision, Phase 3).
- lead: status lifecycle, BANT items with notes and a stored score, optional
  links to an organization and contact, version for optimistic concurrency.
  converted_opportunity_id gets its foreign key with the opportunity table (0005).

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "disqualification_reason",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disqualification_reason")),
        sa.UniqueConstraint("code", name=op.f("uq_disqualification_reason_code")),
    )
    op.create_table(
        "lead_source",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_source")),
        sa.UniqueConstraint("code", name=op.f("uq_lead_source_code")),
    )
    op.create_table(
        "lead",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("estimated_value", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("bant_budget", sa.String(length=8), server_default="unknown", nullable=False),
        sa.Column("bant_budget_note", sa.Text(), nullable=True),
        sa.Column("bant_authority", sa.String(length=8), server_default="unknown", nullable=False),
        sa.Column("bant_authority_note", sa.Text(), nullable=True),
        sa.Column("bant_need", sa.String(length=8), server_default="unknown", nullable=False),
        sa.Column("bant_need_note", sa.Text(), nullable=True),
        sa.Column("bant_timeline", sa.String(length=8), server_default="unknown", nullable=False),
        sa.Column("bant_timeline_note", sa.Text(), nullable=True),
        sa.Column(
            "fits_target_profile", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("qualification_score", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("disqualification_reason_id", sa.Uuid(), nullable=True),
        sa.Column("disqualification_note", sa.Text(), nullable=True),
        sa.Column("disqualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("converted_opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
            "bant_authority IN ('unknown', 'no', 'partial', 'yes')",
            name=op.f("ck_lead_bant_authority"),
        ),
        sa.CheckConstraint(
            "bant_budget IN ('unknown', 'no', 'partial', 'yes')", name=op.f("ck_lead_bant_budget")
        ),
        sa.CheckConstraint(
            "bant_need IN ('unknown', 'no', 'partial', 'yes')", name=op.f("ck_lead_bant_need")
        ),
        sa.CheckConstraint(
            "bant_timeline IN ('unknown', 'no', 'partial', 'yes')",
            name=op.f("ck_lead_bant_timeline"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'converted', 'disqualified')",
            name=op.f("ck_lead_status"),
        ),
        sa.CheckConstraint(
            "estimated_value IS NULL OR estimated_value >= 0", name=op.f("ck_lead_estimated_value")
        ),
        sa.CheckConstraint(
            "qualification_score BETWEEN 0 AND 100", name=op.f("ck_lead_qualification_score")
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contact.id"], name=op.f("fk_lead_contact_id_contact")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_lead_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["disqualification_reason_id"],
            ["disqualification_reason.id"],
            name=op.f("fk_lead_disqualification_reason_id_disqualification_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_lead_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["app_user.id"], name=op.f("fk_lead_owner_id_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["lead_source.id"], name=op.f("fk_lead_source_id_lead_source")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_lead_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead")),
    )
    op.create_index("ix_lead_created_at", "lead", ["created_at"], unique=False)
    op.create_index("ix_lead_organization_id", "lead", ["organization_id"], unique=False)
    op.create_index("ix_lead_owner_id", "lead", ["owner_id"], unique=False)
    op.create_index(
        "ix_lead_search_text_trgm",
        "lead",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index("ix_lead_source_id", "lead", ["source_id"], unique=False)
    op.create_index("ix_lead_status", "lead", ["status"], unique=False)
    op.create_index("ix_lead_updated_at_id", "lead", ["updated_at", "id"], unique=False)
    for table in ("lead_source", "disqualification_reason", "lead"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    op.execute(
        """
        INSERT INTO lead_source (id, code, name_en, name_bg, position) VALUES
            (gen_random_uuid(), 'campaign', 'Campaign', 'Кампания', 1),
            (gen_random_uuid(), 'inbound', 'Inbound inquiry', 'Входящо запитване', 2),
            (gen_random_uuid(), 'referral', 'Referral', 'Препоръка', 3),
            (gen_random_uuid(), 'event', 'Event', 'Събитие', 4),
            (gen_random_uuid(), 'cold_outreach', 'Cold outreach', 'Студен контакт', 5),
            (gen_random_uuid(), 'partner', 'Partner', 'Партньор', 6),
            (gen_random_uuid(), 'other', 'Other', 'Друго', 7)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO disqualification_reason (id, code, name_en, name_bg, position) VALUES
            (gen_random_uuid(), 'no_budget', 'No budget', 'Няма бюджет', 1),
            (gen_random_uuid(), 'no_need', 'No need', 'Няма нужда', 2),
            (gen_random_uuid(), 'no_decision_maker', 'No decision maker', 'Няма лице, вземащо решение', 3),
            (gen_random_uuid(), 'bad_timing', 'Bad timing', 'Неподходящ момент', 4),
            (gen_random_uuid(), 'chose_competitor', 'Chose a competitor', 'Избра конкурент', 5),
            (gen_random_uuid(), 'unreachable', 'Cannot be reached', 'Не може да се осъществи контакт', 6),
            (gen_random_uuid(), 'duplicate', 'Duplicate', 'Дубликат', 7),
            (gen_random_uuid(), 'outside_target', 'Outside target profile', 'Извън целевия профил', 8),
            (gen_random_uuid(), 'other', 'Other', 'Друго', 9)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_lead_updated_at_id", table_name="lead")
    op.drop_index("ix_lead_status", table_name="lead")
    op.drop_index("ix_lead_source_id", table_name="lead")
    op.drop_index(
        "ix_lead_search_text_trgm",
        table_name="lead",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_index("ix_lead_owner_id", table_name="lead")
    op.drop_index("ix_lead_organization_id", table_name="lead")
    op.drop_index("ix_lead_created_at", table_name="lead")
    op.drop_table("lead")
    op.drop_table("lead_source")
    op.drop_table("disqualification_reason")
