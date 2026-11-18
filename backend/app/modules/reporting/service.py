"""Reports and the dashboard (FR-REP-01..03). Public API of the module.

Figures come from the modules that own the data (sales, activity); this module
applies the owner scope and period, composes the dashboard and exports reports.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.events import EventBus
from app.core.export import (
    ExportColumn,
    ExportFile,
    ExportOptions,
    exported_event,
    render,
    select_columns,
)
from app.core.export import Locale as ExportLocale
from app.core.principal import Principal
from app.modules.activity import service as activity
from app.modules.identity import service as identity
from app.modules.reporting.schemas import Dashboard, ReportName, TaskFigures
from app.modules.sales import service as sales
from app.modules.sales.schemas import (
    ForecastReport,
    GroupKey,
    LeadConversionReport,
    PipelineReport,
    WinLossReport,
)

SOFIA = ZoneInfo("Europe/Sofia")
DASHBOARD_FORECAST_MONTHS = 6


@dataclass(frozen=True, slots=True)
class Context:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime

    @property
    def today(self) -> date:
        return self.now.astimezone(SOFIA).date()


@dataclass(frozen=True, slots=True)
class Scope:
    """Owner filter (empty = everyone) and period (default: the current calendar year)."""

    owner_ids: tuple[UUID, ...]
    first: date
    last: date

    @classmethod
    def build(
        cls, ctx: Context, owner_ids: Sequence[UUID], first: date | None, last: date | None
    ) -> Scope:
        year = ctx.today.year
        return cls(
            owner_ids=tuple(owner_ids),
            first=first or date(year, 1, 1),
            last=last or date(year, 12, 31),
        )


async def dashboard(ctx: Context, principal: Principal, scope: Scope) -> Dashboard:
    session = ctx.session
    conversion = await sales.reports.lead_conversion(
        session, scope.owner_ids, scope.first, scope.last, None
    )
    closed = await sales.reports.win_loss(session, scope.owner_ids, scope.first, scope.last, None)
    open_tasks, overdue = await activity.my_task_counts(session, principal.user_id, ctx.now)
    return Dashboard(
        from_date=scope.first,
        to_date=scope.last,
        pipeline=await sales.reports.pipeline_by_stage(session, scope.owner_ids),
        forecast=await sales.reports.forecast(
            session, scope.owner_ids, ctx.today, DASHBOARD_FORECAST_MONTHS
        ),
        lead_conversion=conversion.totals,
        win_loss=closed.totals,
        my_tasks=TaskFigures(open=open_tasks, overdue=overdue),
    )


async def pipeline_by_stage(ctx: Context, scope: Scope) -> PipelineReport:
    return await sales.reports.pipeline_by_stage(ctx.session, scope.owner_ids)


async def forecast(ctx: Context, scope: Scope, months: int) -> ForecastReport:
    return await sales.reports.forecast(ctx.session, scope.owner_ids, ctx.today, months)


async def lead_conversion(
    ctx: Context, scope: Scope, group_by: Literal["source", "owner"] | None
) -> LeadConversionReport:
    return await sales.reports.lead_conversion(
        ctx.session, scope.owner_ids, scope.first, scope.last, group_by
    )


async def win_loss(
    ctx: Context, scope: Scope, group_by: Literal["loss_reason", "owner", "month"] | None
) -> WinLossReport:
    return await sales.reports.win_loss(
        ctx.session, scope.owner_ids, scope.first, scope.last, group_by
    )


# --- Exports (FR-REP-02: "any report above") -----------------------------------------------

_STAGE = ExportColumn("stage", "Stage", "Етап")
_MONTH = ExportColumn("month", "Month", "Месец")
_GROUP = ExportColumn("group", "Group", "Група")
_COUNT = ExportColumn("count", "Opportunities", "Възможности")
_TOTAL = ExportColumn("total_amount", "Total (EUR)", "Общо (EUR)")
_WEIGHTED = ExportColumn("weighted_amount", "Weighted (EUR)", "Претеглено (EUR)")
REPORT_COLUMNS: dict[ReportName, tuple[ExportColumn, ...]] = {
    "pipeline-by-stage": (_STAGE, _COUNT, _TOTAL, _WEIGHTED),
    "forecast": (_MONTH, _COUNT, _TOTAL, _WEIGHTED),
    "lead-conversion": (
        _GROUP,
        ExportColumn("created", "Created", "Създадени"),
        ExportColumn("qualified", "Qualified", "Квалифицирани"),
        ExportColumn("converted", "Converted", "Превърнати"),
        ExportColumn("disqualified", "Disqualified", "Дисквалифицирани"),
        ExportColumn("conversion_rate", "Conversion rate", "Конверсия"),
    ),
    "win-loss": (
        _GROUP,
        ExportColumn("won_count", "Won", "Спечелени"),
        ExportColumn("won_amount", "Won (EUR)", "Спечелени (EUR)"),
        ExportColumn("lost_count", "Lost", "Загубени"),
        ExportColumn("lost_amount", "Lost (EUR)", "Загубени (EUR)"),
        ExportColumn("win_rate", "Win rate", "Успеваемост"),
    ),
}
_TOTAL_LABEL = {"en": "Total", "bg": "Общо"}
_NONE_LABEL = {"en": "Not set", "bg": "Не е посочено"}


def _group_name(group: GroupKey, locale: ExportLocale) -> str:
    name = group.name_bg if locale == "bg" else group.name_en
    return name or _NONE_LABEL[locale]


async def _report_rows(
    ctx: Context, report: ReportName, scope: Scope, params: Mapping[str, Any], locale: ExportLocale
) -> list[dict[str, Any]]:
    if report == "pipeline-by-stage":
        pipeline = await pipeline_by_stage(ctx, scope)
        rows: list[dict[str, Any]] = [
            {
                **s.model_dump(exclude={"stage"}),
                "stage": s.stage.name_bg if locale == "bg" else s.stage.name_en,
            }
            for s in pipeline.stages
        ]
        rows.append(
            {
                "stage": _TOTAL_LABEL[locale],
                "count": pipeline.count,
                "total_amount": pipeline.total_amount,
                "weighted_amount": pipeline.weighted_amount,
            }
        )
        return rows
    if report == "forecast":
        months = await forecast(ctx, scope, params["months"])
        return [m.model_dump() for m in months.months]
    if report == "lead-conversion":
        conversion = await lead_conversion(ctx, scope, params["group_by"])
        rows = [
            {**g.model_dump(exclude={"group"}), "group": _group_name(g.group, locale)}
            for g in conversion.groups
        ]
        return [*rows, {**conversion.totals.model_dump(), "group": _TOTAL_LABEL[locale]}]
    closed = await win_loss(ctx, scope, params["group_by"])
    rows = [
        {**g.model_dump(exclude={"group"}), "group": _group_name(g.group, locale)}
        for g in closed.groups
    ]
    return [*rows, {**closed.totals.model_dump(), "group": _TOTAL_LABEL[locale]}]


async def export_report(
    ctx: Context,
    principal: Principal,
    report: ReportName,
    scope: Scope,
    params: Mapping[str, Any],
    options: ExportOptions,
) -> ExportFile:
    """A report above as XLSX or CSV, with a total row where it applies."""
    columns = select_columns(REPORT_COLUMNS[report], options.columns)
    locale = options.locale or await identity.user_locale(ctx.session, principal.user_id)
    rows = await _report_rows(ctx, report, scope, params, locale)
    content = render(columns, rows, options.format, locale, sheet=report)
    filters = {
        "report": report,
        "owner_ids": scope.owner_ids,
        "from": scope.first,
        "to": scope.last,
        **params,
    }
    await ctx.events.publish(
        ctx.session,
        exported_event("report", principal, ctx.now, rows=len(rows), options=options,
                       filters=filters),
    )  # fmt: skip
    await ctx.session.commit()
    return ExportFile(content, options.format, report, ctx.today)
