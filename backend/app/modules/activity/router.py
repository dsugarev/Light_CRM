"""HTTP layer only: parse requests, call the service, shape responses."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.listing import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, ListQuery, Page, SyncPage, list_query
from app.core.principal import Principal
from app.modules.activity import service
from app.modules.activity.schemas import (
    ActivityCreate,
    ActivityOut,
    ActivityType,
    ActivityUpdate,
    TimelineItem,
    VersionOnly,
)

activities_router = APIRouter(prefix="/activities", tags=["activities"])
me_router = APIRouter(prefix="/me", tags=["me"])
timelines_router = APIRouter(tags=["timelines"])


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    return service.Context(
        session=session,
        events=request.app.state.event_bus,
        settings=request.app.state.settings,
        now=clock.now(),
    )


Ctx = Annotated[service.Context, Depends(context)]


def _ids(name: str, values: list[str] | None, principal: Principal) -> tuple[UUID, ...]:
    """Repeatable user filters; `me` stands for the caller."""
    ids: list[UUID] = []
    for value in values or []:
        if value == "me":
            ids.append(principal.user_id)
            continue
        try:
            ids.append(UUID(value))
        except ValueError as error:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                400,
                errors=[FieldError(name, "validation.uuid_parsing")],
            ) from error
    return tuple(ids)


ActivityList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "activities",
            sortable=tuple(service.ACTIVITY_SORT),
            default_sort="-occurred_at",
            filters=(
                "type", "lead_id", "opportunity_id", "organization_id", "contact_id", "owner_id",
                "assignee_id", "is_done", "due_at_from", "due_at_to", "occurred_at_from",
                "occurred_at_to",
            ),
        )
    ),
]  # fmt: skip
Repeated = Annotated[list[UUID] | None, Query()]
People = Annotated[list[str] | None, Query(max_length=50)]


@activities_router.get(
    "",
    summary="List activities and tasks",
    **endpoint(AccessLevel.SIGNED_IN, scope="activities:read"),
)
async def list_activities(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: ActivityList,
    activity_type: Annotated[list[ActivityType] | None, Query(alias="type")] = None,
    lead_id: Repeated = None,
    opportunity_id: Repeated = None,
    organization_id: Repeated = None,
    contact_id: Repeated = None,
    owner_id: People = None,
    assignee_id: People = None,
    is_done: bool | None = None,
    due_at_from: datetime | None = None,
    due_at_to: datetime | None = None,
    occurred_at_from: datetime | None = None,
    occurred_at_to: datetime | None = None,
) -> Page[ActivityOut] | SyncPage[ActivityOut]:
    filters = service.ActivityFilters(
        types=tuple(activity_type or ()),
        lead_ids=tuple(lead_id or ()),
        opportunity_ids=tuple(opportunity_id or ()),
        organization_ids=tuple(organization_id or ()),
        contact_ids=tuple(contact_id or ()),
        owner_ids=_ids("owner_id", owner_id, principal),
        assignee_ids=_ids("assignee_id", assignee_id, principal),
        is_done=is_done,
        due_from=due_at_from,
        due_to=due_at_to,
        occurred_from=occurred_at_from,
        occurred_to=occurred_at_to,
    )
    return await service.list_activities(ctx, query, filters)


@activities_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Log a note, call, meeting, email or task linked to at least one record",
    **endpoint(AccessLevel.CONTRIBUTOR, scope="activities:write"),
)
async def create_activity(
    body: ActivityCreate, ctx: Ctx, principal: CurrentPrincipal, response: Response
) -> ActivityOut:
    created = await service.create_activity(ctx, principal, body)
    response.headers["Location"] = f"/api/v1/activities/{created.id}"
    return created


@activities_router.get(
    "/{activity_id}",
    summary="Detail",
    **endpoint(AccessLevel.SIGNED_IN, scope="activities:read"),
)
async def get_activity(activity_id: UUID, ctx: Ctx) -> ActivityOut:
    return await service.get_activity(ctx, activity_id)


@activities_router.patch(
    "/{activity_id}",
    summary="Update; requires version",
    **endpoint(AccessLevel.OWNER_PLUS_OR_TASK_ASSIGNEE, scope="activities:write"),
)
async def update_activity(
    activity_id: UUID, body: ActivityUpdate, ctx: Ctx, principal: CurrentPrincipal
) -> ActivityOut:
    return await service.update_activity(ctx, principal, activity_id, body)


@activities_router.delete(
    "/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive",
    **endpoint(AccessLevel.OWNER_PLUS),
)
async def archive_activity(activity_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.archive_activity(ctx, principal, activity_id)


@activities_router.post(
    "/{activity_id}/complete",
    summary="Mark a task done",
    **endpoint(AccessLevel.OWNER_PLUS_OR_ASSIGNEE),
)
async def complete_task(
    activity_id: UUID, body: VersionOnly, ctx: Ctx, principal: CurrentPrincipal
) -> ActivityOut:
    return await service.complete_task(ctx, principal, activity_id, body.version)


@activities_router.post(
    "/{activity_id}/reopen",
    summary="Mark a task not done",
    **endpoint(AccessLevel.OWNER_PLUS_OR_ASSIGNEE),
)
async def reopen_task(
    activity_id: UUID, body: VersionOnly, ctx: Ctx, principal: CurrentPrincipal
) -> ActivityOut:
    return await service.reopen_task(ctx, principal, activity_id, body.version)


TaskList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "my-tasks", sortable=("due_at",), default_sort="due_at", filters=("include_done",)
        )
    ),
]


@me_router.get(
    "/tasks",
    summary="Own open tasks, overdue first; filter include_done",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def my_tasks(
    ctx: Ctx, principal: CurrentPrincipal, query: TaskList, include_done: bool = False
) -> Page[ActivityOut]:
    return await service.my_tasks(ctx, principal, query, include_done)


# --- Timelines (FR-ACT-03); paths belong to the records' sections of the spec ---------------

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)]


@timelines_router.get(
    "/leads/{lead_id}/timeline",
    summary="Activities and system events for the lead",
    **endpoint(AccessLevel.SIGNED_IN, scope="leads:read"),
)
async def lead_timeline(
    lead_id: UUID, ctx: Ctx, page: PageNumber = 1, page_size: PageSize = PAGE_SIZE_DEFAULT
) -> Page[TimelineItem]:
    return await service.lead_timeline(ctx, lead_id, page, page_size)


@timelines_router.get(
    "/opportunities/{opp_id}/timeline",
    summary="Activities, stage changes and events, including those from the source lead",
    **endpoint(AccessLevel.SIGNED_IN, scope="opportunities:read"),
)
async def opportunity_timeline(
    opp_id: UUID, ctx: Ctx, page: PageNumber = 1, page_size: PageSize = PAGE_SIZE_DEFAULT
) -> Page[TimelineItem]:
    return await service.opportunity_timeline(ctx, opp_id, page, page_size)


@timelines_router.get(
    "/organizations/{org_id}/timeline",
    summary="Merged timeline for the organization and its contacts, leads and opportunities",
    **endpoint(AccessLevel.SIGNED_IN, scope="organizations:read"),
)
async def organization_timeline(
    org_id: UUID, ctx: Ctx, page: PageNumber = 1, page_size: PageSize = PAGE_SIZE_DEFAULT
) -> Page[TimelineItem]:
    return await service.organization_timeline(ctx, org_id, page, page_size)


@timelines_router.get(
    "/contacts/{contact_id}/timeline",
    summary="Activities and system events for the contact",
    **endpoint(AccessLevel.SIGNED_IN, scope="contacts:read"),
)
async def contact_timeline(
    contact_id: UUID, ctx: Ctx, page: PageNumber = 1, page_size: PageSize = PAGE_SIZE_DEFAULT
) -> Page[TimelineItem]:
    return await service.contact_timeline(ctx, contact_id, page, page_size)


routers = [activities_router, me_router, timelines_router]
