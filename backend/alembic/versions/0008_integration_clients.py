"""Integration clients, API keys, external references, idempotency and usage (Phase 6a).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-17

- external_system: configurable list, seeded with conclusion, erp, billing (API spec 6.2).
- integration_client (backed by a service user), api_key (hashed secrets),
  external_reference (one per record per system; external IDs unique per system and
  record type), idempotency_record (24 h), integration_usage (requests and errors
  per client and hour).

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_system",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_system")),
        sa.UniqueConstraint("code", name=op.f("uq_external_system_code")),
    )
    op.create_table(
        "external_reference",
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("external_system_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
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
            "entity_type IN ('organization', 'contact', 'lead', 'opportunity')",
            name=op.f("ck_external_reference_entity_type"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_external_reference_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["external_system_id"],
            ["external_system.id"],
            name=op.f("fk_external_reference_external_system_id_external_system"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_external_reference_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_reference")),
        sa.UniqueConstraint("entity_type", "entity_id", "external_system_id", name="record_system"),
        sa.UniqueConstraint("external_system_id", "entity_type", "external_id", name="external_id"),
    )
    op.create_table(
        "integration_client",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("external_system_id", sa.Uuid(), nullable=False),
        sa.Column("service_user_id", sa.Uuid(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(length=40)), nullable=False),
        sa.Column("default_owner_id", sa.Uuid(), nullable=True),
        sa.Column("ip_allowlist", postgresql.ARRAY(sa.String(length=50)), nullable=False),
        sa.Column("technical_contact", sa.String(length=300), nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer(), server_default="300", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
            "rate_limit_per_minute BETWEEN 1 AND 100000",
            name=op.f("ck_integration_client_rate_limit"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_integration_client_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["default_owner_id"],
            ["app_user.id"],
            name=op.f("fk_integration_client_default_owner_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["external_system_id"],
            ["external_system.id"],
            name=op.f("fk_integration_client_external_system_id_external_system"),
        ),
        sa.ForeignKeyConstraint(
            ["service_user_id"],
            ["app_user.id"],
            name=op.f("fk_integration_client_service_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_integration_client_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_client")),
        sa.UniqueConstraint("service_user_id", name=op.f("uq_integration_client_service_user_id")),
    )
    op.create_table(
        "api_key",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.String(length=16), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", sa.String(length=50), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["integration_client.id"],
            name=op.f("fk_api_key_client_id_integration_client"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_api_key_created_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_key")),
        sa.UniqueConstraint("key_id", name=op.f("uq_api_key_key_id")),
    )
    op.create_index(op.f("ix_api_key_client_id"), "api_key", ["client_id"], unique=False)
    op.create_table(
        "idempotency_record",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed')", name=op.f("ck_idempotency_record_status")
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["integration_client.id"],
            name=op.f("fk_idempotency_record_client_id_integration_client"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_record")),
        sa.UniqueConstraint("client_id", "key", name="client_key"),
    )
    op.create_index(
        "ix_idempotency_record_expires_at", "idempotency_record", ["expires_at"], unique=False
    )
    op.create_table(
        "integration_usage",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["integration_client.id"],
            name=op.f("fk_integration_usage_client_id_integration_client"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("client_id", "hour", name="pk_integration_usage"),
    )

    for table in ("external_system", "external_reference", "integration_client", "api_key"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    op.execute(
        """
        INSERT INTO external_system (id, code, name_en, name_bg, position) VALUES
            (gen_random_uuid(), 'conclusion', 'Conclusion', 'Conclusion', 1),
            (gen_random_uuid(), 'erp', 'ERP', 'ERP', 2),
            (gen_random_uuid(), 'billing', 'Billing', 'Billing', 3)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("integration_usage")
    op.drop_index("ix_idempotency_record_expires_at", table_name="idempotency_record")
    op.drop_table("idempotency_record")
    op.drop_index(op.f("ix_api_key_client_id"), table_name="api_key")
    op.drop_table("api_key")
    op.drop_table("integration_client")
    op.drop_table("external_reference")
    op.drop_table("external_system")
