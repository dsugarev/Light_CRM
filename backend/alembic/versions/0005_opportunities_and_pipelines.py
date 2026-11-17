"""Pipelines, stages, loss reasons and opportunities (Phase 4a).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17

- pipeline, pipeline_stage: one default pipeline seeded with six stages in
  English and Bulgarian (owner decision, Phase 4): Prospecting 10,
  Qualification 25, Solution & Proposal 50, Negotiation 75, Closed Won 100,
  Closed Lost 0.
- loss_reason: configurable list owned by sales, seeded in both languages.
- opportunity, opportunity_stage_history: FR-OPP-01..06.
- lead.converted_opportunity_id gets its foreign key (announced in 0004).
- app_setting.stale_opportunity_days (FR-OPP-06, default 14).

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "loss_reason",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loss_reason")),
        sa.UniqueConstraint("code", name=op.f("uq_loss_reason_code")),
    )
    op.create_table(
        "pipeline",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline")),
    )
    op.create_table(
        "pipeline_stage",
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("name_en", sa.String(length=100), nullable=False),
        sa.Column("name_bg", sa.String(length=100), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("default_probability", sa.SmallInteger(), nullable=False),
        sa.Column("stage_type", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint(
            "stage_type IN ('open', 'won', 'lost')", name=op.f("ck_pipeline_stage_stage_type")
        ),
        sa.CheckConstraint(
            "default_probability BETWEEN 0 AND 100",
            name=op.f("ck_pipeline_stage_default_probability"),
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"], ["pipeline.id"], name=op.f("fk_pipeline_stage_pipeline_id_pipeline")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_stage")),
    )
    op.create_index(
        "ix_pipeline_stage_pipeline_id", "pipeline_stage", ["pipeline_id"], unique=False
    )
    op.create_table(
        "opportunity",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("primary_contact_id", sa.Uuid(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("stage_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.Column("probability", sa.SmallInteger(), nullable=False),
        sa.Column(
            "probability_overridden", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("actual_close_date", sa.Date(), nullable=True),
        sa.Column("next_step", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_lead_id", sa.Uuid(), nullable=True),
        sa.Column("loss_reason_id", sa.Uuid(), nullable=True),
        sa.Column("competitor", sa.String(length=200), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("amount IS NULL OR amount >= 0", name=op.f("ck_opportunity_amount")),
        sa.CheckConstraint(
            "probability BETWEEN 0 AND 100", name=op.f("ck_opportunity_probability")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_opportunity_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["loss_reason_id"],
            ["loss_reason.id"],
            name=op.f("fk_opportunity_loss_reason_id_loss_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_opportunity_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["app_user.id"], name=op.f("fk_opportunity_owner_id_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"], ["pipeline.id"], name=op.f("fk_opportunity_pipeline_id_pipeline")
        ),
        sa.ForeignKeyConstraint(
            ["primary_contact_id"],
            ["contact.id"],
            name=op.f("fk_opportunity_primary_contact_id_contact"),
        ),
        sa.ForeignKeyConstraint(
            ["source_lead_id"], ["lead.id"], name=op.f("fk_opportunity_source_lead_id_lead")
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["pipeline_stage.id"], name=op.f("fk_opportunity_stage_id_pipeline_stage")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_opportunity_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity")),
    )
    op.create_index(
        "ix_opportunity_expected_close_date", "opportunity", ["expected_close_date"], unique=False
    )
    op.create_index(
        "ix_opportunity_organization_id", "opportunity", ["organization_id"], unique=False
    )
    op.create_index("ix_opportunity_owner_id", "opportunity", ["owner_id"], unique=False)
    op.create_index(
        "ix_opportunity_search_text_trgm",
        "opportunity",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index("ix_opportunity_stage_id", "opportunity", ["stage_id"], unique=False)
    op.create_index(
        "ix_opportunity_updated_at_id", "opportunity", ["updated_at", "id"], unique=False
    )
    op.create_table(
        "opportunity_stage_history",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("from_stage_id", sa.Uuid(), nullable=True),
        sa.Column("to_stage_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["app_user.id"],
            name=op.f("fk_opportunity_stage_history_changed_by_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["from_stage_id"],
            ["pipeline_stage.id"],
            name=op.f("fk_opportunity_stage_history_from_stage_id_pipeline_stage"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunity.id"],
            name=op.f("fk_opportunity_stage_history_opportunity_id_opportunity"),
        ),
        sa.ForeignKeyConstraint(
            ["to_stage_id"],
            ["pipeline_stage.id"],
            name=op.f("fk_opportunity_stage_history_to_stage_id_pipeline_stage"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_stage_history")),
    )
    op.create_index(
        "ix_opportunity_stage_history_opportunity_id",
        "opportunity_stage_history",
        ["opportunity_id"],
        unique=False,
    )
    op.add_column(
        "app_setting",
        sa.Column("stale_opportunity_days", sa.Integer(), server_default="14", nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_lead_converted_opportunity_id_opportunity"),
        "lead",
        "opportunity",
        ["converted_opportunity_id"],
        ["id"],
        use_alter=True,
    )

    for table in ("loss_reason", "pipeline", "pipeline_stage", "opportunity"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    op.execute(
        """
        WITH p AS (
            INSERT INTO pipeline (id, name, is_default)
            VALUES (gen_random_uuid(), 'Sales pipeline', true)
            RETURNING id
        )
        INSERT INTO pipeline_stage
            (id, pipeline_id, name_en, name_bg, position, default_probability, stage_type)
        SELECT gen_random_uuid(), p.id, s.name_en, s.name_bg, s.position, s.probability, s.stage_type
        FROM p, (VALUES
            ('Prospecting', 'Проучване', 1, 10, 'open'),
            ('Qualification', 'Квалификация', 2, 25, 'open'),
            ('Solution & Proposal', 'Решение и оферта', 3, 50, 'open'),
            ('Negotiation', 'Преговори', 4, 75, 'open'),
            ('Closed Won', 'Спечелена', 5, 100, 'won'),
            ('Closed Lost', 'Загубена', 6, 0, 'lost')
        ) AS s (name_en, name_bg, position, probability, stage_type)
        """
    )
    op.execute(
        """
        INSERT INTO loss_reason (id, code, name_en, name_bg, position) VALUES
            (gen_random_uuid(), 'price', 'Price', 'Цена', 1),
            (gen_random_uuid(), 'chose_competitor', 'Chose a competitor', 'Избра конкурент', 2),
            (gen_random_uuid(), 'no_budget', 'No budget', 'Няма бюджет', 3),
            (gen_random_uuid(), 'no_decision', 'No decision or project stopped', 'Няма решение или проектът е спрян', 4),
            (gen_random_uuid(), 'timing', 'Timing', 'Неподходящ момент', 5),
            (gen_random_uuid(), 'solution_fit', 'Solution did not fit', 'Решението не е подходящо', 6),
            (gen_random_uuid(), 'other', 'Other', 'Друго', 7)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_lead_converted_opportunity_id_opportunity"), "lead", type_="foreignkey"
    )
    op.drop_column("app_setting", "stale_opportunity_days")
    op.drop_index(
        "ix_opportunity_stage_history_opportunity_id", table_name="opportunity_stage_history"
    )
    op.drop_table("opportunity_stage_history")
    op.drop_index("ix_opportunity_updated_at_id", table_name="opportunity")
    op.drop_index("ix_opportunity_stage_id", table_name="opportunity")
    op.drop_index(
        "ix_opportunity_search_text_trgm",
        table_name="opportunity",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_index("ix_opportunity_owner_id", table_name="opportunity")
    op.drop_index("ix_opportunity_organization_id", table_name="opportunity")
    op.drop_index("ix_opportunity_expected_close_date", table_name="opportunity")
    op.drop_table("opportunity")
    op.drop_index("ix_pipeline_stage_pipeline_id", table_name="pipeline_stage")
    op.drop_table("pipeline_stage")
    op.drop_table("pipeline")
    op.drop_table("loss_reason")
