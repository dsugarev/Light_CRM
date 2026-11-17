"""In-process domain events (architecture section 3).

Services publish an event for every change; subscribers (the audit log now, the
integration outbox in Phase 6) handle it in the same database session, so their
rows commit or roll back together with the change.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal


@dataclass(frozen=True, slots=True)
class DomainEvent:
    action: str  # e.g. "user.created", "auth.login_failed"
    entity_type: str
    entity_id: UUID | None
    actor: Principal | None
    occurred_at: datetime
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None
    # Free-form context that is not part of the record (e.g. a failure reason).
    details: Mapping[str, Any] = field(default_factory=dict)


Handler = Callable[[AsyncSession, DomainEvent], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def publish(self, session: AsyncSession, event: DomainEvent) -> None:
        for handler in self._handlers:
            await handler(session, event)


def get_event_bus(request: Request) -> EventBus:
    bus: EventBus = request.app.state.event_bus
    return bus
