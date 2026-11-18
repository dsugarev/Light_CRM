"""Webhooks: transactional outbox, subscriptions, deliveries and attempts (Phase 6b).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17

- outbox_event: written in the business transaction by the integration module's
  domain-event handler (FR-INT-07 AC1); the worker fans it out and sets dispatched_at.
- webhook_subscription: a client's HTTPS endpoint, event types and encrypted secrets.
- webhook_delivery: one event to one subscription with its retry state.
- webhook_attempt: every attempt, for the delivery log.

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_event",
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("actor", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_event")),
    )
    op.create_index("ix_outbox_event_occurred_at", "outbox_event", ["occurred_at"], unique=False)
    op.create_index(
        "ix_outbox_event_undispatched",
        "outbox_event",
        ["occurred_at"],
        unique=False,
        postgresql_where="dispatched_at IS NULL",
    )
    op.create_table(
        "webhook_subscription",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("event_types", postgresql.ARRAY(sa.String(length=60)), nullable=False),
        sa.Column("secret_encrypted", sa.String(length=500), nullable=False),
        sa.Column("previous_secret_encrypted", sa.String(length=500), nullable=True),
        sa.Column("previous_secret_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("failing_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["integration_client.id"],
            name=op.f("fk_webhook_subscription_client_id_integration_client"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_webhook_subscription_created_by_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_webhook_subscription_updated_by_app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_subscription")),
    )
    op.create_index(
        op.f("ix_webhook_subscription_client_id"),
        "webhook_subscription",
        ["client_id"],
        unique=False,
    )
    op.create_table(
        "webhook_delivery",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=200), nullable=True),
        sa.Column("last_response_excerpt", sa.String(length=1000), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'retrying', 'succeeded', 'failed')",
            name=op.f("ck_webhook_delivery_status"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["outbox_event.id"],
            name=op.f("fk_webhook_delivery_event_id_outbox_event"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["webhook_subscription.id"],
            name=op.f("fk_webhook_delivery_subscription_id_webhook_subscription"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_delivery")),
    )
    op.create_index(
        "ix_webhook_delivery_created_at", "webhook_delivery", ["created_at"], unique=False
    )
    op.create_index(
        "ix_webhook_delivery_due", "webhook_delivery", ["status", "next_attempt_at"], unique=False
    )
    op.create_index(
        op.f("ix_webhook_delivery_event_id"), "webhook_delivery", ["event_id"], unique=False
    )
    op.create_index(
        op.f("ix_webhook_delivery_subscription_id"),
        "webhook_delivery",
        ["subscription_id"],
        unique=False,
    )
    op.create_table(
        "webhook_attempt",
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("response_excerpt", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["webhook_delivery.id"],
            name=op.f("fk_webhook_attempt_delivery_id_webhook_delivery"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_attempt")),
    )
    op.create_index(
        op.f("ix_webhook_attempt_delivery_id"), "webhook_attempt", ["delivery_id"], unique=False
    )
    op.execute(
        "CREATE TRIGGER trg_webhook_subscription_updated_at BEFORE UPDATE ON webhook_subscription "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_webhook_attempt_delivery_id"), table_name="webhook_attempt")
    op.drop_table("webhook_attempt")
    op.drop_index(op.f("ix_webhook_delivery_subscription_id"), table_name="webhook_delivery")
    op.drop_index(op.f("ix_webhook_delivery_event_id"), table_name="webhook_delivery")
    op.drop_index("ix_webhook_delivery_due", table_name="webhook_delivery")
    op.drop_index("ix_webhook_delivery_created_at", table_name="webhook_delivery")
    op.drop_table("webhook_delivery")
    op.drop_index(op.f("ix_webhook_subscription_client_id"), table_name="webhook_subscription")
    op.drop_table("webhook_subscription")
    op.drop_index(
        "ix_outbox_event_undispatched",
        table_name="outbox_event",
        postgresql_where="dispatched_at IS NULL",
    )
    op.drop_index("ix_outbox_event_occurred_at", table_name="outbox_event")
    op.drop_table("outbox_event")
