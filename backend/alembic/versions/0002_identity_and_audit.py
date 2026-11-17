"""Identity, sessions, settings, rate limits and the audit log (Phase 1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17

- set_updated_at(): trigger function keeping updated_at current on every UPDATE
  (architecture 4.5); attached to each table with an updated_at column.
- Seeds the five roles and the single app_setting row (idempotent).
- audit_log is append-only for the application role crm_app (architecture 4.3).

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def _updated_at_trigger(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    # --- identity -------------------------------------------------------------
    op.create_table(
        "role",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role")),
        sa.UniqueConstraint("code", name=op.f("uq_role_code")),
    )
    _updated_at_trigger("role")
    op.execute(
        """
        INSERT INTO role (id, code, name) VALUES
            (gen_random_uuid(), 'admin', 'Admin'),
            (gen_random_uuid(), 'sales_manager', 'Sales Manager'),
            (gen_random_uuid(), 'sales_rep', 'Sales Rep'),
            (gen_random_uuid(), 'viewer', 'Viewer'),
            (gen_random_uuid(), 'integration', 'Integration client')
        ON CONFLICT (code) DO NOTHING
        """
    )

    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_type", sa.String(length=16), server_default="human", nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("locale", sa.String(length=2), server_default="en", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("auth_provider", sa.String(length=32), server_default="local", nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_secret", sa.Text(), nullable=True),
        *_timestamps(),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("locale IN ('en', 'bg')", name=op.f("ck_app_user_locale")),
        sa.CheckConstraint("user_type IN ('human', 'service')", name=op.f("ck_app_user_user_type")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_app_user_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], name=op.f("fk_app_user_role_id_role")),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_app_user_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
    )
    op.create_index(
        "uq_app_user_email_lower", "app_user", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_index(
        "uq_app_user_external_subject",
        "app_user",
        ["auth_provider", "external_subject"],
        unique=True,
        postgresql_where=sa.text("external_subject IS NOT NULL"),
    )
    _updated_at_trigger("app_user")

    op.create_table(
        "user_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_user_session_user_id_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_session_token_hash")),
    )
    op.create_index(op.f("ix_user_session_user_id"), "user_session", ["user_id"], unique=False)

    op.create_table(
        "password_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=8), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("purpose IN ('set', 'reset')", name=op.f("ck_password_token_purpose")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_password_token_created_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_password_token_user_id_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_token_token_hash")),
    )
    op.create_index(op.f("ix_password_token_user_id"), "password_token", ["user_id"], unique=False)

    # --- core: runtime settings and rate limits --------------------------------
    op.create_table(
        "app_setting",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "session_idle_timeout_minutes", sa.Integer(), server_default="480", nullable=False
        ),
        sa.Column(
            "session_absolute_timeout_minutes", sa.Integer(), server_default="10080", nullable=False
        ),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("id = 1", name=op.f("ck_app_setting_single_row")),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f("fk_app_setting_updated_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_setting")),
    )
    _updated_at_trigger("app_setting")
    op.execute("INSERT INTO app_setting (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    op.create_table(
        "rate_limit_bucket",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key", "window_start", name=op.f("pk_rate_limit_bucket")),
    )

    # --- audit ----------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_label", sa.String(length=200), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"], unique=False)
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"], unique=False)
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"], unique=False)
    # Append-only for the application role (FR-ADM-03: entries cannot be edited or
    # deleted through the application). Skipped where the role does not exist.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'crm_app') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM crm_app;
                GRANT SELECT, INSERT ON audit_log TO crm_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("rate_limit_bucket")
    op.drop_table("app_setting")
    op.drop_table("password_token")
    op.drop_table("user_session")
    op.drop_table("app_user")
    op.drop_table("role")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
