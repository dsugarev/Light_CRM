"""Assistant actions with confirmation (Phase 9, R1.1; FR-AI-09, ADR 0030).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-22

- assistant_action: an action the assistant proposed; nothing changes until its user
  confirms it. Holds the validated request, the record version it was proposed against,
  the card text, its status (proposed, confirmed, cancelled, expired, failed) and result.

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_action",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("target_label", sa.String(length=300), nullable=True),
        sa.Column("target_version", sa.Integer(), nullable=True),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("card", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("destructive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="proposed", nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed', 'confirmed', 'cancelled', 'expired', 'failed')",
            name=op.f("ck_assistant_action_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_assistant_action_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["chat_conversation.id"],
            name=op.f("fk_assistant_action_conversation_id_chat_conversation"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_message.id"],
            name=op.f("fk_assistant_action_message_id_chat_message"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_action")),
    )
    op.create_index("ix_assistant_action_message", "assistant_action", ["message_id"])
    op.create_index(
        "ix_assistant_action_user_created", "assistant_action", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_action_user_created", table_name="assistant_action")
    op.drop_index("ix_assistant_action_message", table_name="assistant_action")
    op.drop_table("assistant_action")
