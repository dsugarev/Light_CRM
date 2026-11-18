"""HTTP layer only: parse requests, call the service, shape responses."""

from datetime import date, datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.export import EXPORT_PARAMS, EXPORT_RESPONSES, ExportOptions, export_options
from app.core.external import EXTERNAL_PARAMS, External
from app.core.listing import ListQuery, Page, SyncPage, list_query
from app.core.principal import Principal
from app.modules.sales import service
from app.modules.sales.schemas import (
    AssignRequest,
    Board,
    CloseRequest,
    ConversionPreview,
    ConversionResult,
    ConvertRequest,
    DisqualifyRequest,
    LeadCreate,
    LeadOut,
    LeadStatus,
    LeadUpdate,
    MoveRequest,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
    PipelineOut,
    ReopenRequest,
    StageChange,
    StageCreate,
    StageType,
    StageUpdate,
    VersionOnly,
)

leads_router = APIRouter(prefix="/leads", tags=["leads"])
organization_leads_router = APIRouter(prefix="/organizations", tags=["organizations"])
pipelines_router = APIRouter(prefix="/pipelines", tags=["pipelines"])
opportunities_router = APIRouter(prefix="/opportunities", tags=["opportunities"])


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    return service.Context(
        session=session,
        events=request.app.state.event_bus,
        settings=request.app.state.settings,
        now=clock.now(),
        external_filter=request.app.state.external_filter,
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
            filters=(*EXTERNAL_PARAMS,
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
    external: External,
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
        external=external,
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


LeadExportList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "leads-export",
            sortable=tuple(service.LEAD_SORT),
            default_sort="-created_at",
            filters=(*EXTERNAL_PARAMS,
                "status", "owner_id", "source_id", "created_at_from", "created_at_to",
                "fits_target_profile", *EXPORT_PARAMS,
            ),
        )
    ),
]  # fmt: skip


@leads_router.get(
    "/export",
    summary="Export the filtered list as XLSX or CSV",
    response_class=Response,
    responses=EXPORT_RESPONSES,
    **endpoint(AccessLevel.SIGNED_IN),
)
async def export_leads(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: LeadExportList,
    external: External,
    options: Annotated[ExportOptions, Depends(export_options)],
    lead_status: Annotated[list[LeadStatus] | None, Query(alias="status")] = None,
    owner_id: Annotated[list[str] | None, Query(max_length=50)] = None,
    source_id: Annotated[list[UUID] | None, Query()] = None,
    created_at_from: datetime | None = None,
    created_at_to: datetime | None = None,
    fits_target_profile: bool | None = None,
) -> Response:
    filters = service.LeadFilters(
        statuses=tuple(lead_status or ()),
        owner_ids=_owner_ids(owner_id, principal),
        source_ids=tuple(source_id or ()),
        created_from=created_at_from,
        created_to=created_at_to,
        fits_target_profile=fits_target_profile,
        external=external,
    )
    file = await service.export_leads(ctx, principal, query, filters, options)
    return file.response()


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


@leads_router.get(
    "/{lead_id}/conversion-preview",
    summary="Suggested organization and contact matches to show before converting",
    **endpoint(AccessLevel.OWNER_PLUS),
)
async def conversion_preview(
    lead_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> ConversionPreview:
    return await service.conversion_preview(ctx, principal, lead_id)


@leads_router.post(
    "/{lead_id}/convert",
    status_code=status.HTTP_201_CREATED,
    summary="Convert in one transaction: organization, contact and opportunity",
    **endpoint(AccessLevel.OWNER_PLUS),
)
async def convert(
    lead_id: UUID, body: ConvertRequest, ctx: Ctx, principal: CurrentPrincipal
) -> ConversionResult:
    return await service.convert(ctx, principal, lead_id, body)


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


# --- Pipelines and stages (API spec 6.3) ----------------------------------------------------


@pipelines_router.get(
    "",
    summary="Pipelines (one in R1) with their stages in order",
    **endpoint(AccessLevel.SIGNED_IN, scope="reference:read"),
)
async def list_pipelines(ctx: Ctx) -> list[PipelineOut]:
    return await service.list_pipelines(ctx)


@pipelines_router.get(
    "/{pipeline_id}",
    summary="One pipeline with stages",
    **endpoint(AccessLevel.SIGNED_IN, scope="reference:read"),
)
async def get_pipeline(pipeline_id: UUID, ctx: Ctx) -> PipelineOut:
    return await service.get_pipeline(ctx, pipeline_id)


@pipelines_router.post(
    "/{pipeline_id}/stages",
    status_code=status.HTTP_201_CREATED,
    summary="Add a stage: name (en/bg), default probability, type",
    **endpoint(AccessLevel.ADMIN),
)
async def add_stage(
    pipeline_id: UUID, body: StageCreate, ctx: Ctx, principal: CurrentPrincipal
) -> PipelineOut:
    return await service.add_stage(ctx, principal, pipeline_id, body)


@pipelines_router.put(
    "/{pipeline_id}/stages/order", summary="Reorder stages", **endpoint(AccessLevel.ADMIN)
)
async def reorder_stages(
    pipeline_id: UUID,
    ctx: Ctx,
    principal: CurrentPrincipal,
    body: Annotated[list[UUID], Body(max_length=100)],
) -> PipelineOut:
    return await service.reorder_stages(ctx, principal, pipeline_id, body)


@pipelines_router.patch(
    "/{pipeline_id}/stages/{stage_id}",
    summary="Rename, change probability, activate or deactivate",
    **endpoint(AccessLevel.ADMIN),
)
async def update_stage(
    pipeline_id: UUID, stage_id: UUID, body: StageUpdate, ctx: Ctx, principal: CurrentPrincipal
) -> PipelineOut:
    return await service.update_stage(ctx, principal, pipeline_id, stage_id, body)


@pipelines_router.delete(
    "/{pipeline_id}/stages/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an unused stage; 409 stage.in_use otherwise",
    **endpoint(AccessLevel.ADMIN),
)
async def delete_stage(
    pipeline_id: UUID, stage_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> None:
    await service.delete_stage(ctx, principal, pipeline_id, stage_id)


# --- Opportunities (API spec 10) ------------------------------------------------------------

opps = service.opportunities

OpportunityList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "opportunities",
            sortable=tuple(service.OPPORTUNITY_SORT),
            default_sort="-updated_at",
            filters=(*EXTERNAL_PARAMS,
                "stage_id", "stage_type", "owner_id", "organization_id",
                "expected_close_date_from", "expected_close_date_to", "amount_from", "amount_to",
                "is_stale",
            ),
        )
    ),
]  # fmt: skip


@opportunities_router.get(
    "",
    summary="List and search opportunities",
    **endpoint(AccessLevel.SIGNED_IN, scope="opportunities:read"),
)
async def list_opportunities(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: OpportunityList,
    external: External,
    stage_id: Annotated[list[UUID] | None, Query()] = None,
    stage_type: Annotated[list[StageType] | None, Query()] = None,
    owner_id: Annotated[list[str] | None, Query(max_length=50)] = None,
    organization_id: Annotated[list[UUID] | None, Query()] = None,
    expected_close_date_from: date | None = None,
    expected_close_date_to: date | None = None,
    amount_from: Decimal | None = None,
    amount_to: Decimal | None = None,
    is_stale: bool | None = None,
) -> Page[OpportunityOut] | SyncPage[OpportunityOut]:
    filters = service.OpportunityFilters(
        stage_ids=tuple(stage_id or ()),
        stage_types=tuple(stage_type or ()),
        owner_ids=_owner_ids(owner_id, principal),
        organization_ids=tuple(organization_id or ()),
        close_from=expected_close_date_from,
        close_to=expected_close_date_to,
        amount_from=amount_from,
        amount_to=amount_to,
        is_stale=is_stale,
        external=external,
    )
    return await opps.list_opportunities(ctx, query, filters)


@opportunities_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create; stage defaults to the first open stage, probability to its default",
    **endpoint(AccessLevel.CONTRIBUTOR, scope="opportunities:write"),
)
async def create_opportunity(
    body: OpportunityCreate, ctx: Ctx, principal: CurrentPrincipal, response: Response
) -> OpportunityOut:
    created = await opps.create(ctx, principal, body)
    response.headers["Location"] = f"/api/v1/opportunities/{created.id}"
    return created


OpportunityExportList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "opportunities-export",
            sortable=tuple(service.OPPORTUNITY_SORT),
            default_sort="-updated_at",
            filters=(*EXTERNAL_PARAMS,
                "stage_id", "stage_type", "owner_id", "organization_id",
                "expected_close_date_from", "expected_close_date_to", "amount_from", "amount_to",
                "is_stale", *EXPORT_PARAMS,
            ),
        )
    ),
]  # fmt: skip


@opportunities_router.get(
    "/export",
    summary="Export the filtered list as XLSX or CSV",
    response_class=Response,
    responses=EXPORT_RESPONSES,
    **endpoint(AccessLevel.SIGNED_IN),
)
async def export_opportunities(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: OpportunityExportList,
    external: External,
    options: Annotated[ExportOptions, Depends(export_options)],
    stage_id: Annotated[list[UUID] | None, Query()] = None,
    stage_type: Annotated[list[StageType] | None, Query()] = None,
    owner_id: Annotated[list[str] | None, Query(max_length=50)] = None,
    organization_id: Annotated[list[UUID] | None, Query()] = None,
    expected_close_date_from: date | None = None,
    expected_close_date_to: date | None = None,
    amount_from: Decimal | None = None,
    amount_to: Decimal | None = None,
    is_stale: bool | None = None,
) -> Response:
    filters = service.OpportunityFilters(
        stage_ids=tuple(stage_id or ()),
        stage_types=tuple(stage_type or ()),
        owner_ids=_owner_ids(owner_id, principal),
        organization_ids=tuple(organization_id or ()),
        close_from=expected_close_date_from,
        close_to=expected_close_date_to,
        amount_from=amount_from,
        amount_to=amount_to,
        is_stale=is_stale,
        external=external,
    )
    file = await opps.export_opportunities(ctx, principal, query, filters, options)
    return file.response()


@opportunities_router.get(
    "/board",
    summary="Kanban data: one column per active open stage with totals and cards",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def board(
    ctx: Ctx,
    principal: CurrentPrincipal,
    pipeline_id: UUID | None = None,
    owner_id: Annotated[list[str] | None, Query(max_length=50)] = None,
    expected_close_date_from: date | None = None,
    expected_close_date_to: date | None = None,
) -> Board:
    filters = service.OpportunityFilters(
        pipeline_ids=(pipeline_id,) if pipeline_id else (),
        owner_ids=_owner_ids(owner_id, principal),
        close_from=expected_close_date_from,
        close_to=expected_close_date_to,
    )
    return await opps.board(ctx, principal, filters)


@opportunities_router.get(
    "/{opp_id}",
    summary="Detail with organization, contact, stage, source lead and is_stale",
    **endpoint(AccessLevel.SIGNED_IN, scope="opportunities:read"),
)
async def get_opportunity(opp_id: UUID, ctx: Ctx) -> OpportunityOut:
    return await opps.get(ctx, opp_id)


@opportunities_router.patch(
    "/{opp_id}",
    summary="Update fields; requires version; 409 opportunity.closed if closed",
    **endpoint(AccessLevel.OWNER_PLUS, scope="opportunities:write"),
)
async def update_opportunity(
    opp_id: UUID, body: OpportunityUpdate, ctx: Ctx, principal: CurrentPrincipal
) -> OpportunityOut:
    return await opps.update(ctx, principal, opp_id, body)


@opportunities_router.delete(
    "/{opp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive",
    **endpoint(AccessLevel.OWNER_PLUS),
)
async def archive_opportunity(opp_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await opps.archive(ctx, principal, opp_id)


@opportunities_router.post(
    "/{opp_id}/restore", summary="Restore", **endpoint(AccessLevel.MANAGER_PLUS)
)
async def restore_opportunity(
    opp_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> OpportunityOut:
    return await opps.restore(ctx, principal, opp_id)


@opportunities_router.post(
    "/{opp_id}/assign",
    summary="Change owner; a Sales Rep may only assign to themselves",
    **endpoint(AccessLevel.CONTRIBUTOR_RULES_IN_SERVICE),
)
async def assign_opportunity(
    opp_id: UUID, body: AssignRequest, ctx: Ctx, principal: CurrentPrincipal
) -> OpportunityOut:
    return await opps.assign(ctx, principal, opp_id, body.owner_id, body.version)


@opportunities_router.post(
    "/{opp_id}/move",
    summary="Change stage within open stages; probability follows unless overridden",
    **endpoint(AccessLevel.OWNER_PLUS, scope="opportunities:write"),
)
async def move_opportunity(
    opp_id: UUID, body: MoveRequest, ctx: Ctx, principal: CurrentPrincipal
) -> OpportunityOut:
    return await opps.move(ctx, principal, opp_id, body)


@opportunities_router.post(
    "/{opp_id}/close",
    summary="Close as won or lost; lost needs a loss reason",
    **endpoint(AccessLevel.OWNER_PLUS, scope="opportunities:write"),
)
async def close_opportunity(
    opp_id: UUID, body: CloseRequest, ctx: Ctx, principal: CurrentPrincipal
) -> OpportunityOut:
    return await opps.close(ctx, principal, opp_id, body)


@opportunities_router.post(
    "/{opp_id}/reopen",
    summary="Reopen into a chosen open stage",
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def reopen_opportunity(
    opp_id: UUID, body: ReopenRequest, ctx: Ctx, principal: CurrentPrincipal
) -> OpportunityOut:
    return await opps.reopen(ctx, principal, opp_id, body)


@opportunities_router.get(
    "/{opp_id}/stage-history",
    summary="Stage changes with user, time, from and to",
    **endpoint(AccessLevel.SIGNED_IN, scope="opportunities:read"),
)
async def stage_history(opp_id: UUID, ctx: Ctx) -> list[StageChange]:
    return await opps.stage_history(ctx, opp_id)


OrganizationOpportunityList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "organization-opportunities",
            sortable=tuple(service.OPPORTUNITY_SORT),
            default_sort="-updated_at",
        )
    ),
]


@organization_leads_router.get(
    "/{org_id}/opportunities",
    summary="Opportunities of this organization",
    **endpoint(AccessLevel.SIGNED_IN, scope="organizations:read"),
)
async def organization_opportunities(
    org_id: UUID, ctx: Ctx, query: OrganizationOpportunityList
) -> Page[OpportunityOut] | SyncPage[OpportunityOut]:
    filters = service.OpportunityFilters(organization_ids=(org_id,))
    return await opps.list_opportunities(ctx, query, filters)


routers = [leads_router, organization_leads_router, pipelines_router, opportunities_router]
