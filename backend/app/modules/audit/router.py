"""HTTP layer only: parse requests, call the service, shape responses."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock, get_clock
from app.core.db import DbSession
from app.core.events import EventBus, get_event_bus
from app.core.export import EXPORT_RESPONSES, ExportOptions, export_options
from app.modules.audit import service
from app.modules.audit.schemas import AuditEntry, AuditPage

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get(
    "",
    summary="Browse audit entries, newest first",
    **endpoint(AccessLevel.ADMIN),
)
async def list_entries(
    session: DbSession,
    actor_id: UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: UUID | None = None,
    action: Annotated[list[str] | None, Query(max_length=64)] = None,
    occurred_at_from: datetime | None = None,
    occurred_at_to: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AuditPage:
    return await service.search(
        session,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actions=action or [],
        occurred_from=occurred_at_from,
        occurred_to=occurred_at_to,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/export",
    summary="Export the filtered log as XLSX or CSV",
    response_class=Response,
    responses=EXPORT_RESPONSES,
    **endpoint(AccessLevel.ADMIN),
)
async def export_entries(
    session: DbSession,
    principal: CurrentPrincipal,
    events: Annotated[EventBus, Depends(get_event_bus)],
    clock: Annotated[Clock, Depends(get_clock)],
    options: Annotated[ExportOptions, Depends(export_options)],
    actor_id: UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: UUID | None = None,
    action: Annotated[list[str] | None, Query(max_length=64)] = None,
    occurred_at_from: datetime | None = None,
    occurred_at_to: datetime | None = None,
) -> Response:
    filters = {
        "actor_id": actor_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actions": action or [],
        "occurred_from": occurred_at_from,
        "occurred_to": occurred_at_to,
    }
    file = await service.export_entries(session, events, principal, clock.now(), filters, options)
    return file.response()


@router.get(
    "/{entry_id}",
    summary="One entry with full before and after values",
    **endpoint(AccessLevel.ADMIN),
)
async def get_entry(entry_id: UUID, session: DbSession) -> AuditEntry:
    return await service.get_entry(session, entry_id)
