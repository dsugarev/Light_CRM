"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ContextType = Literal["lead", "opportunity", "organization"]
NoteTarget = Literal["lead", "opportunity", "organization", "contact"]
MessageRole = Literal["user", "assistant"]
MessageStatus = Literal["streaming", "complete", "stopped", "failed"]
MAX_MESSAGE_CHARS = 4000


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecordContext(_Request):
    """FR-AI-03: the record the user is looking at."""

    entity_type: ContextType
    entity_id: UUID


class ConversationCreate(_Request):
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    context: RecordContext | None = None


class ConversationRename(_Request):
    title: Annotated[str, Field(min_length=1, max_length=200)]


class MessageCreate(_Request):
    content: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_CHARS)]
    context: RecordContext | None = Field(
        default=None, description="Overrides the conversation's record context for this question"
    )


class SaveAsNote(_Request):
    entity_type: NoteTarget
    entity_id: UUID
    content: Annotated[str, Field(min_length=1, max_length=10000)] = Field(
        description="The draft, possibly edited by the user"
    )


class AssistantStatus(BaseModel):
    enabled: bool
    daily_token_budget: int
    used_today: int
    remaining_budget: int


class RecordRef(BaseModel):
    entity_type: str
    entity_id: UUID
    label: str


class ConversationOut(BaseModel):
    id: UUID
    title: str | None
    context: RecordContext | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    status: MessageStatus
    error_code: str | None
    tools_used: list[str] = Field(description="Tools the assistant called; never their results")
    record_refs: list[RecordRef]
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
