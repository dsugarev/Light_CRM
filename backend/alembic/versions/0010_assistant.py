"""AI assistant: conversations, messages and token usage (Phase 7).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18

- chat_conversation: a user's conversation, with optional record context (FR-AI-01, 03).
- chat_message: questions and answers; tool results are not stored (ADR 0026).
- assistant_usage: tokens per request for the daily budget and reporting (FR-AI-08);
  kept when a conversation is deleted.

Migration policy (architecture 4.2): additive only, never edit a released
migration, and keep a working downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_conversation",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("context_entity_type", sa.String(length=20), nullable=True),
        sa.Column("context_entity_id", sa.Uuid(), nullable=True),
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
            "context_entity_type IN ('lead', 'opportunity', 'organization')",
            name=op.f("ck_chat_conversation_context_entity_type"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_chat_conversation_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_conversation")),
    )
    op.create_index(
        "ix_chat_conversation_user_updated",
        "chat_conversation",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "chat_message",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("record_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("stop_requested", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_chat_message_role")),
        sa.CheckConstraint(
            "status IN ('streaming', 'complete', 'stopped', 'failed')",
            name=op.f("ck_chat_message_status"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["chat_conversation.id"],
            name=op.f("fk_chat_message_conversation_id_chat_conversation"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_message")),
    )
    op.create_index(
        "ix_chat_message_conversation_created",
        "chat_message",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "assistant_usage",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("tool_rounds", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_assistant_usage_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_usage")),
    )
    op.create_index(
        "ix_assistant_usage_user_occurred",
        "assistant_usage",
        ["user_id", "occurred_at"],
        unique=False,
    )
    op.execute(
        "CREATE TRIGGER trg_chat_conversation_updated_at BEFORE UPDATE ON chat_conversation "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_usage_user_occurred", table_name="assistant_usage")
    op.drop_table("assistant_usage")
    op.drop_index("ix_chat_message_conversation_created", table_name="chat_message")
    op.drop_table("chat_message")
    op.drop_index("ix_chat_conversation_user_updated", table_name="chat_conversation")
    op.drop_table("chat_conversation")
