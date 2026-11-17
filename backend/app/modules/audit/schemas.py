"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditActor(BaseModel):
    type: Literal["user", "integration", "anonymous", "system"]
    id: UUID | None
    name: str | None


class AuditEntrySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    actor: AuditActor
    action: str
    entity_type: str
    entity_id: UUID | None
    ip: str | None


class AuditEntry(AuditEntrySummary):
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    details: dict[str, Any] | None
    request_id: str | None


class AuditPage(BaseModel):
    items: list[AuditEntrySummary]
    total: int
    page: int
    page_size: int
