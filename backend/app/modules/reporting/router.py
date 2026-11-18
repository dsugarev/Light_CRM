"""HTTP layer only: parse requests, call the service, shape responses."""

from datetime import date
from http import HTTPStatus
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.export import EXPORT_RESPONSES, ExportOptions, export_options
from app.modules.reporting import service
from app.modules.reporting.schemas import Dashboard, ReportName
from app.modules.sales.schemas import (
    ForecastReport,
    LeadConversionReport,
    PipelineReport,
    WinLossReport,
)

router = APIRouter(prefix="/reports", tags=["reports"])


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    return service.Context(
        session=session,
        events=request.app.state.event_bus,
        settings=request.app.state.settings,
        now=clock.now(),
    )


Ctx = Annotated[service.Context, Depends(context)]


def _bad(field: str, code: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED, HTTPStatus.BAD_REQUEST, errors=[FieldError(field, code)]
    )


async def scope(
    ctx: Ctx,
    principal: CurrentPrincipal,
    owner_id: Annotated[str | None, Query(max_length=50, description="`me` or a user ID")] = None,
    first: Annotated[date | None, Query(alias="from")] = None,
    last: Annotated[date | None, Query(alias="to")] = None,
) -> service.Scope:
    """Owner filter and period shared by every report (API spec 13)."""
    owner_ids: tuple[UUID, ...] = ()
    if owner_id == "me":
        owner_ids = (principal.user_id,)
    elif owner_id:
        try:
            owner_ids = (UUID(owner_id),)
        except ValueError as error:
            raise _bad("owner_id", "validation.uuid_parsing") from error
    built = service.Scope.build(ctx, owner_ids, first, last)
    if built.first > built.last:
        raise _bad("from", "validation.period")
    return built


Scope = Annotated[service.Scope, Depends(scope)]
Months = Annotated[int, Query(ge=1, le=12)]
ConversionGroup = Annotated[Literal["source", "owner"] | None, Query()]
WinLossGroup = Annotated[Literal["loss_reason", "owner", "month"] | None, Query()]


@router.get(
    "/dashboard",
    summary="Pipeline by stage, 6-month forecast, conversion rate, win rate, my open tasks",
    **endpoint(AccessLevel.SIGNED_IN, scope="reports:read"),
)
async def dashboard(ctx: Ctx, principal: CurrentPrincipal, report_scope: Scope) -> Dashboard:
    return await service.dashboard(ctx, principal, report_scope)


@router.get(
    "/pipeline-by-stage",
    summary="Count, total and weighted amount per open stage",
    **endpoint(AccessLevel.SIGNED_IN, scope="reports:read"),
)
async def pipeline_by_stage(ctx: Ctx, report_scope: Scope) -> PipelineReport:
    return await service.pipeline_by_stage(ctx, report_scope)


@router.get(
    "/forecast",
    summary="Weighted forecast by expected close month",
    **endpoint(AccessLevel.SIGNED_IN, scope="reports:read"),
)
async def forecast(ctx: Ctx, report_scope: Scope, months: Months = 6) -> ForecastReport:
    return await service.forecast(ctx, report_scope, months)


@router.get(
    "/lead-conversion",
    summary="Leads created, qualified, converted, disqualified and conversion rate",
    **endpoint(AccessLevel.SIGNED_IN, scope="reports:read"),
)
async def lead_conversion(
    ctx: Ctx, report_scope: Scope, group_by: ConversionGroup = None
) -> LeadConversionReport:
    return await service.lead_conversion(ctx, report_scope, group_by)


@router.get(
    "/win-loss",
    summary="Won and lost counts and amounts, win rate",
    **endpoint(AccessLevel.SIGNED_IN, scope="reports:read"),
)
async def win_loss(ctx: Ctx, report_scope: Scope, group_by: WinLossGroup = None) -> WinLossReport:
    return await service.win_loss(ctx, report_scope, group_by)


@router.get(
    "/{report}/export",
    summary="XLSX or CSV export of a report",
    response_class=Response,
    responses=EXPORT_RESPONSES,
    **endpoint(AccessLevel.SIGNED_IN),
)
async def export_report(
    report: ReportName,
    ctx: Ctx,
    principal: CurrentPrincipal,
    report_scope: Scope,
    options: Annotated[ExportOptions, Depends(export_options)],
    months: Months = 6,
    group_by: Annotated[str | None, Query(max_length=20)] = None,
) -> Response:
    allowed: dict[str, tuple[str, ...]] = {
        "lead-conversion": ("source", "owner"),
        "win-loss": ("loss_reason", "owner", "month"),
    }
    if group_by is not None and group_by not in allowed.get(report, ()):
        raise _bad("group_by", "validation.literal_error")
    params: dict[str, Any] = {"months": months, "group_by": group_by}
    file = await service.export_report(ctx, principal, report, report_scope, params, options)
    return file.response()
