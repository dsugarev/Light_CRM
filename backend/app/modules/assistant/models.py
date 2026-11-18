"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin

CONTEXT_TYPES = ("lead", "opportunity", "organization")


class ChatConversation(IdMixin, TimestampMixin, Base):
    """FR-AI-01: one user's conversation; only its owner can see it."""

    __tablename__ = "chat_conversation"
    __table_args__ = (
        CheckConstraint(
            "context_entity_type IN ('lead', 'opportunity', 'organization')",
            name="context_entity_type",
        ),
        Index("ix_chat_conversation_user_updated", "user_id", "updated_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    context_entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    context_entity_id: Mapped[UUID | None] = mapped_column(nullable=True)


class ChatMessage(IdMixin, Base):
    """A user question or an assistant answer. Tool results are not stored (ADR 0026):
    only the tools called and the records cited, so CRM data is not copied into chats."""

    __tablename__ = "chat_message"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        CheckConstraint("status IN ('streaming', 'complete', 'stopped', 'failed')", name="status"),
        Index("ix_chat_message_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_conversation.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    # [{"tool": name, "arguments": {...}}] for assistant messages.
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    # [{"entity_type", "entity_id", "label"}]: records cited in the answer.
    record_refs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    stop_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssistantUsage(IdMixin, Base):
    """FR-AI-08: tokens per request. Kept when a conversation is deleted, so the daily
    budget and usage reporting do not depend on chat history."""

    __tablename__ = "assistant_usage"
    __table_args__ = (Index("ix_assistant_usage_user_occurred", "user_id", "occurred_at"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
