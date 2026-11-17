"""HTTP layer only: parse requests, call the service, shape responses."""

from datetime import datetime
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.listing import ListQuery, Page, SyncPage, list_query
from app.core.principal import Principal
from app.modules.sales import service
from app.modules.sales.schemas import (
    AssignRequest,
    DisqualifyRequest,
    LeadCreate,
    LeadOut,
    LeadStatus,
    LeadUpdate,
    VersionOnly,
)

leads_router = APIRouter(prefix="/leads", tags=["leads"])
organization_leads_router = APIRouter(prefix="/organizations", tags=["organizations"])


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    return service.Context(
        session=session,
        events=request.app.state.event_bus,
        settings=request.app.state.settings,
        now=clock.now(),
    )


Ctx = Annotated[service.Context, Depends(context)]


def _owner_ids(values: list[str] | None, principal: Principal) -> tuple[UUID, ...]:
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
                HTTPStatus.BAD_REQUEST,
                errors=[FieldError("owner_id", "validation.uuid_parsing")],
            ) from error
    return tuple(ids)


LeadList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "leads",
            sortable=tuple(service.LEAD_SORT),
            default_sort="-created_at",
            filters=(
                "status", "owner_id", "source_id", "created_at_from", "created_at_to",
                "fits_target_profile",
            ),
        )
    ),
]  # fmt: skip


@leads_router.get(
    "", summary="List and search leads", **endpoint(AccessLevel.SIGNED_IN, scope="leads:read")
)
async def list_leads(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: LeadList,
    lead_status: Annotated[list[LeadStatus] | None, Query(alias="status")] = None,
    owner_id: Annotated[list[str] | None, Query(max_length=50)] = None,
    source_id: Annotated[list[UUID] | None, Query()] = None,
    created_at_from: datetime | None = None,
    created_at_to: datetime | None = None,
    fits_target_profile: bool | None = None,
) -> Page[LeadOut] | SyncPage[LeadOut]:
    filters = service.LeadFilters(
        statuses=tuple(lead_status or ()),
        owner_ids=_owner_ids(owner_id, principal),
        source_ids=tuple(source_id or ()),
        created_from=created_at_from,
        created_to=created_at_to,
        fits_target_profile=fits_target_profile,
    )
    return await service.list_leads(ctx, query, filters)


@leads_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Capture a lead; status starts as new; owner defaults to the caller",
    **endpoint(AccessLevel.CONTRIBUTOR, scope="leads:write"),
)
async def create_lead(
    body: LeadCreate, ctx: Ctx, principal: CurrentPrincipal, response: Response
) -> LeadOut:
    created = await service.create_lead(ctx, principal, body)
    response.headers["Location"] = f"/api/v1/leads/{created.id}"
    return created


@leads_router.get(
    "/{lead_id}",
    summary="Detail including BANT, score and links",
    **endpoint(AccessLevel.SIGNED_IN, scope="leads:read"),
)
async def get_lead(lead_id: UUID, ctx: Ctx) -> LeadOut:
    return await service.get_lead(ctx, lead_id)


@leads_router.patch(
    "/{lead_id}",
    summary="Update fields and BANT items; requires version",
    **endpoint(AccessLevel.OWNER_PLUS, scope="leads:write"),
)
async def update_lead(
    lead_id: UUID, body: LeadUpdate, ctx: Ctx, principal: CurrentPrincipal
) -> LeadOut:
    return await service.update_lead(ctx, principal, lead_id, body)


@leads_router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive",
    **endpoint(AccessLevel.OWNER_PLUS),
)
async def archive_lead(lead_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.archive_lead(ctx, principal, lead_id)


@leads_router.post("/{lead_id}/restore", summary="Restore", **endpoint(AccessLevel.MANAGER_PLUS))
async def restore_lead(lead_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> LeadOut:
    return await service.restore_lead(ctx, principal, lead_id)


@leads_router.post(
    "/{lead_id}/assign",
    summary="Change owner; a Sales Rep may only assign to themselves",
    **endpoint(AccessLevel.CONTRIBUTOR_RULES_IN_SERVICE),
)
async def assign_lead(
    lead_id: UUID, body: AssignRequest, ctx: Ctx, principal: CurrentPrincipal
) -> LeadOut:
    return await service.assign(ctx, principal, lead_id, body)


@leads_router.post(
    "/{lead_id}/mark-contacted",
    summary="new -> contacted",
    **endpoint(AccessLevel.OWNER_PLUS, scope="leads:write"),
)
async def mark_contacted(
    lead_id: UUID, body: VersionOnly, ctx: Ctx, principal: CurrentPrincipal
) -> LeadOut:
    return await service.mark_contacted(ctx, principal, lead_id, body.version)


@leads_router.post(
    "/{lead_id}/qualify",
    summary="-> qualified; 409 lead.bant_incomplete if any BANT item is unknown",
    **endpoint(AccessLevel.OWNER_PLUS, scope="leads:write"),
)
async def qualify(
    lead_id: UUID, body: VersionOnly, ctx: Ctx, principal: CurrentPrincipal
) -> LeadOut:
    return await service.qualify(ctx, principal, lead_id, body.version)


@leads_router.post(
    "/{lead_id}/disqualify",
    summary="-> disqualified with a reason",
    **endpoint(AccessLevel.OWNER_PLUS, scope="leads:write"),
)
async def disqualify(
    lead_id: UUID, body: DisqualifyRequest, ctx: Ctx, principal: CurrentPrincipal
) -> LeadOut:
    return await service.disqualify(ctx, principal, lead_id, body)


@leads_router.post(
    "/{lead_id}/reopen", summary="disqualified -> contacted", **endpoint(AccessLevel.MANAGER_PLUS)
)
async def reopen(
    lead_id: UUID, body: VersionOnly, ctx: Ctx, principal: CurrentPrincipal
) -> LeadOut:
    return await service.reopen(ctx, principal, lead_id, body.version)


OrganizationLeadList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "organization-leads", sortable=tuple(service.LEAD_SORT), default_sort="-created_at"
        )
    ),
]


@organization_leads_router.get(
    "/{org_id}/leads",
    summary="Leads linked to this organization",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def organization_leads(
    org_id: UUID, ctx: Ctx, query: OrganizationLeadList
) -> Page[LeadOut] | SyncPage[LeadOut]:
    return await service.list_leads(ctx, query, service.LeadFilters(organization_ids=(org_id,)))


routers = [leads_router, organization_leads_router]
