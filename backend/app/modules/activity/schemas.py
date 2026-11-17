"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Same embedded summaries as the records they link to (one OpenAPI component each).
from app.modules.sales.schemas import LinkSummary as LinkSummary
from app.modules.sales.schemas import UserSummary as UserSummary

ActivityType = Literal["note", "call", "meeting", "email", "task"]
Subject = Annotated[str, Field(min_length=1, max_length=200)]
Body = Annotated[str, Field(max_length=10000)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActivityCreate(_Request):
    type: ActivityType
    subject: Subject
    body: Body | None = None
    occurred_at: datetime | None = Field(default=None, description="Defaults to now")
    due_at: datetime | None = Field(default=None, description="Required for tasks")
    owner_id: UUID | None = None
    assignee_id: UUID | None = Field(default=None, description="Tasks; defaults to the owner")
    lead_id: UUID | None = None
    opportunity_id: UUID | None = None
    organization_id: UUID | None = None
    contact_id: UUID | None = None


class ActivityUpdate(_Request):
    version: int = Field(ge=1)
    subject: Subject | None = None
    body: Body | None = None
    occurred_at: datetime | None = None
    due_at: datetime | None = None
    assignee_id: UUID | None = None
    # Present only to answer with validation.use_action_endpoint / immutability.
    type: Any = Field(default=None, description="The type cannot change")
    owner_id: Any = Field(default=None, description="The owner cannot change")
    done: Any = Field(default=None, description="Use /complete or /reopen")


class VersionOnly(_Request):
    version: int = Field(ge=1)


class ActivityLinks(BaseModel):
    lead: LinkSummary | None
    opportunity: LinkSummary | None
    organization: LinkSummary | None
    contact: LinkSummary | None


class ActivityOut(BaseModel):
    id: UUID
    type: ActivityType
    subject: str
    body: str | None
    occurred_at: datetime
    due_at: datetime | None
    done_at: datetime | None
    is_done: bool
    is_overdue: bool
    owner: UserSummary
    assignee: UserSummary | None
    links: ActivityLinks
    created_at: datetime
    updated_at: datetime
    created_by: UserSummary | None
    archived_at: datetime | None
    version: int


class TimelineEventOut(BaseModel):
    type: str
    entity_type: str
    entity_id: UUID
    data: dict[str, Any]


class TimelineItem(BaseModel):
    kind: Literal["activity", "event"]
    occurred_at: datetime
    actor: UserSummary | None
    activity: ActivityOut | None = None
    event: TimelineEventOut | None = None
