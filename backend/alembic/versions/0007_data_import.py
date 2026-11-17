"""Data import batches and rows; import_batch_id on imported records (Phase 5b).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17

- import_batch: one uploaded file through mapping, validation, commit and
  rollback (FR-IMP-01); import_row: its rows, validation results and what the
  commit did (record, previous values for updates, timestamp stamp).
- import_batch_id (nullable, indexed) on organization, contact, lead and
  opportunity so a batch can be rolled back (FR-IMP-01 AC4).

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_batch",
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="uploaded", nullable=False),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("duplicate_mode", sa.String(length=10), nullable=True),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invalid_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "duplicate_mode IS NULL OR duplicate_mode IN ('skip', 'update')",
            name=op.f("ck_import_batch_duplicate_mode"),
        ),
        sa.CheckConstraint(
            "entity_type IN ('organizations', 'contacts', 'leads', 'opportunities')",
            name=op.f("ck_import_batch_entity_type"),
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'mapped', 'validated', 'committed', 'rolled_back')",
            name=op.f("ck_import_batch_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_import_batch_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_import_batch_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batch")),
    )
    op.create_index("ix_import_batch_created_at", "import_batch", ["created_at"], unique=False)
    op.execute(
        "CREATE TRIGGER trg_import_batch_updated_at BEFORE UPDATE ON import_batch "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_table(
        "import_row",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outcome", sa.String(length=10), nullable=True),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("match_id", sa.Uuid(), nullable=True),
        sa.Column("match_name", sa.String(length=300), nullable=True),
        sa.Column("action", sa.String(length=10), nullable=True),
        sa.Column("record_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_result", sa.String(length=60), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "action IS NULL OR action IN ('created', 'updated', 'skipped')",
            name=op.f("ck_import_row_action"),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('valid', 'invalid', 'duplicate')",
            name=op.f("ck_import_row_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batch.id"],
            name=op.f("fk_import_row_batch_id_import_batch"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_row")),
    )
    op.create_index(
        "ix_import_row_batch_row", "import_row", ["batch_id", "row_number"], unique=True
    )
    op.add_column("contact", sa.Column("import_batch_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_contact_import_batch_id"), "contact", ["import_batch_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_contact_import_batch_id_import_batch"),
        "contact",
        "import_batch",
        ["import_batch_id"],
        ["id"],
    )
    op.add_column("lead", sa.Column("import_batch_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_lead_import_batch_id"), "lead", ["import_batch_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_lead_import_batch_id_import_batch"),
        "lead",
        "import_batch",
        ["import_batch_id"],
        ["id"],
    )
    op.add_column("opportunity", sa.Column("import_batch_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_opportunity_import_batch_id"), "opportunity", ["import_batch_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_opportunity_import_batch_id_import_batch"),
        "opportunity",
        "import_batch",
        ["import_batch_id"],
        ["id"],
    )
    op.add_column("organization", sa.Column("import_batch_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_organization_import_batch_id"), "organization", ["import_batch_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_organization_import_batch_id_import_batch"),
        "organization",
        "import_batch",
        ["import_batch_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_organization_import_batch_id_import_batch"), "organization", type_="foreignkey"
    )
    op.drop_index(op.f("ix_organization_import_batch_id"), table_name="organization")
    op.drop_column("organization", "import_batch_id")
    op.drop_constraint(
        op.f("fk_opportunity_import_batch_id_import_batch"), "opportunity", type_="foreignkey"
    )
    op.drop_index(op.f("ix_opportunity_import_batch_id"), table_name="opportunity")
    op.drop_column("opportunity", "import_batch_id")
    op.drop_constraint(op.f("fk_lead_import_batch_id_import_batch"), "lead", type_="foreignkey")
    op.drop_index(op.f("ix_lead_import_batch_id"), table_name="lead")
    op.drop_column("lead", "import_batch_id")
    op.drop_constraint(
        op.f("fk_contact_import_batch_id_import_batch"), "contact", type_="foreignkey"
    )
    op.drop_index(op.f("ix_contact_import_batch_id"), table_name="contact")
    op.drop_column("contact", "import_batch_id")
    op.drop_index("ix_import_row_batch_row", table_name="import_row")
    op.drop_table("import_row")
    op.drop_index("ix_import_batch_created_at", table_name="import_batch")
    op.drop_table("import_batch")
