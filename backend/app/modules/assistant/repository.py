"""Database queries. Called only by this module's service."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assistant.models import AssistantUsage, ChatConversation, ChatMessage


def conversations_statement(user_id: UUID) -> Select[Any]:
    return select(ChatConversation).where(ChatConversation.user_id == user_id)


async def get_conversation(
    session: AsyncSession, conversation_id: UUID, user_id: UUID
) -> ChatConversation | None:
    """The conversation, only if it belongs to the user (another user's is "not found")."""
    return (
        await session.execute(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id, ChatConversation.user_id == user_id
            )
        )
    ).scalar_one_or_none()


async def messages_of(session: AsyncSession, conversation_id: UUID) -> list[ChatMessage]:
    return list(
        (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        ).scalars()
    )


async def get_message(
    session: AsyncSession, message_id: UUID, user_id: UUID
) -> tuple[ChatMessage, ChatConversation] | None:
    row = (
        await session.execute(
            select(ChatMessage, ChatConversation)
            .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
            .where(ChatMessage.id == message_id, ChatConversation.user_id == user_id)
        )
    ).first()
    if row is None:
        return None
    message, conversation = row
    return message, conversation


async def stop_requested(session: AsyncSession, message_id: UUID) -> bool:
    return bool(
        (
            await session.execute(
                select(ChatMessage.stop_requested).where(ChatMessage.id == message_id)
            )
        ).scalar_one_or_none()
    )


async def request_stop(session: AsyncSession, message_id: UUID) -> None:
    await session.execute(
        update(ChatMessage).where(ChatMessage.id == message_id).values(stop_requested=True)
    )


async def touch_conversation(session: AsyncSession, conversation_id: UUID, at: datetime) -> None:
    await session.execute(
        update(ChatConversation).where(ChatConversation.id == conversation_id).values(updated_at=at)
    )


async def tokens_used(session: AsyncSession, user_id: UUID, since: datetime) -> int:
    total = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(AssistantUsage.prompt_tokens + AssistantUsage.completion_tokens), 0
                )
            ).where(AssistantUsage.user_id == user_id, AssistantUsage.occurred_at >= since)
        )
    ).scalar_one()
    return int(total)
