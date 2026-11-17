"""Sales reports (FR-REP-01, FR-REP-03; API spec section 13).

Figures come from the opportunity and lead tables owned by this module; the
reporting module composes them into the dashboard and exports them. Periods are
calendar dates in Europe/Sofia; amounts are EUR.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity import service as identity
from app.modules.sales import repository
from app.modules.sales.models import LeadSource, LossReason
from app.modules.sales.schemas import (
    ConversionFigures,
    ConversionGroup,
    ForecastMonth,
    ForecastReport,
    GroupKey,
    LeadConversionReport,
    PipelineReport,
    StageFigures,
    WinLossFigures,
    WinLossGroup,
    WinLossReport,
)
from app.modules.sales.service.pipelines import stage_summary

SOFIA = ZoneInfo("Europe/Sofia")
CENT = Decimal("0.01")
FORECAST_MONTHS_MAX = 12


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _start_of_day(day: date) -> datetime:
    """Midnight in Sofia as a UTC instant (stored timestamps are UTC)."""
    return datetime.combine(day, time.min, SOFIA).astimezone(UTC)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


async def pipeline_by_stage(session: AsyncSession, owner_ids: Sequence[UUID]) -> PipelineReport:
    """Count, total and weighted amount per open stage of the default pipeline."""
    pipeline = await repository.get_default_pipeline(session)
    assert pipeline is not None  # noqa: S101 - seeded by migration 0005
    statement = repository.opportunities_statement(
        search=None, include_archived=False, owner_ids=owner_ids, stage_types=("open",),
        pipeline_ids=(pipeline.id,),
    )  # fmt: skip
    totals = await repository.column_totals(session, statement)
    stages = sorted(
        (s for s in pipeline.stages if s.stage_type == "open" and (s.is_active or s.id in totals)),
        key=lambda s: s.position,
    )
    rows = []
    for stage in stages:
        count, total, weighted = totals.get(stage.id, (0, Decimal(0), Decimal(0)))
        rows.append(
            StageFigures(
                stage=stage_summary(stage),
                count=count,
                total_amount=_money(total),
                weighted_amount=_money(weighted),
            )
        )
    return PipelineReport(
        stages=rows,
        count=sum(r.count for r in rows),
        total_amount=_money(sum((r.total_amount for r in rows), Decimal(0))),
        weighted_amount=_money(sum((r.weighted_amount for r in rows), Decimal(0))),
    )


async def forecast(
    session: AsyncSession, owner_ids: Sequence[UUID], today: date, months: int
) -> ForecastReport:
    """FR-REP-01 AC1: per month from the current one, Σ amount × probability / 100 over open,
    non-archived opportunities expected to close in that month."""
    first = today.replace(day=1)
    found = {
        month: (count, total, weighted)
        for month, count, total, weighted in await repository.forecast_rows(
            session, owner_ids, first, _add_months(first, months)
        )
    }
    rows = []
    for offset in range(months):
        month = _add_months(first, offset)
        label = month.strftime("%Y-%m")
        count, total, weighted = found.get(label, (0, Decimal(0), Decimal(0)))
        rows.append(
            ForecastMonth(
                month=label,
                count=count,
                total_amount=_money(total),
                weighted_amount=_money(weighted),
            )
        )
    return ForecastReport(
        months=rows, weighted_amount=_money(sum((r.weighted_amount for r in rows), Decimal(0)))
    )


async def _group_keys(
    session: AsyncSession, group_by: str | None, keys: set[Any]
) -> dict[Any, GroupKey]:
    ids = {k for k in keys if isinstance(k, UUID)}
    if group_by == "owner":
        names = await identity.user_names(session, ids)
        return {i: GroupKey(key=str(i), name_en=names.get(i), name_bg=names.get(i)) for i in ids}
    if group_by in ("source", "loss_reason"):
        model: type[LeadSource] | type[LossReason] = (
            LeadSource if group_by == "source" else LossReason
        )
        items: list[LeadSource | LossReason] = await repository.get_reference_items(
            session, model, ids
        )
        return {i.id: GroupKey(key=str(i.id), name_en=i.name_en, name_bg=i.name_bg) for i in items}
    return {}


def _key(group_by: str | None, value: Any, known: dict[Any, GroupKey]) -> GroupKey:
    if value is None:
        return GroupKey(key="none", name_en=None, name_bg=None)
    if group_by == "month":
        return GroupKey(key=value, name_en=value, name_bg=value)
    return known.get(value, GroupKey(key=str(value), name_en=None, name_bg=None))


async def lead_conversion(
    session: AsyncSession,
    owner_ids: Sequence[UUID],
    first: date,
    last: date,
    group_by: Literal["source", "owner"] | None,
) -> LeadConversionReport:
    """Leads created in the period and how far they got; rate = converted / created."""
    start, end = _start_of_day(first), _start_of_day(date.fromordinal(last.toordinal() + 1))
    totals_row = (await repository.lead_conversion_rows(session, owner_ids, start, end, None))[0]
    _, created, qualified, converted, disqualified = totals_row
    groups: list[ConversionGroup] = []
    if group_by:
        rows = await repository.lead_conversion_rows(session, owner_ids, start, end, group_by)
        known = await _group_keys(session, group_by, {r[0] for r in rows})
        groups = sorted(
            (
                ConversionGroup(
                    group=_key(group_by, k, known),
                    created=c,
                    qualified=q,
                    converted=v,
                    disqualified=d,
                    conversion_rate=_rate(v, c),
                )
                for k, c, q, v, d in rows
            ),
            key=lambda g: (-g.created, g.group.name_en or ""),
        )
    return LeadConversionReport(
        from_date=first,
        to_date=last,
        group_by=group_by,
        totals=ConversionFigures(
            created=created,
            qualified=qualified,
            converted=converted,
            disqualified=disqualified,
            conversion_rate=_rate(converted, created),
        ),
        groups=groups,
    )


def _win_loss(won: int, won_amount: Decimal, lost: int, lost_amount: Decimal) -> dict[str, Any]:
    return {
        "won_count": won,
        "won_amount": _money(won_amount),
        "lost_count": lost,
        "lost_amount": _money(lost_amount),
        "win_rate": _rate(won, won + lost),
    }


async def win_loss(
    session: AsyncSession,
    owner_ids: Sequence[UUID],
    first: date,
    last: date,
    group_by: Literal["loss_reason", "owner", "month"] | None,
) -> WinLossReport:
    """FR-REP-03: opportunities closed in the period, won against lost."""
    _, won, won_amount, lost, lost_amount = (
        await repository.win_loss_rows(session, owner_ids, first, last, None)
    )[0]
    groups: list[WinLossGroup] = []
    if group_by:
        rows = await repository.win_loss_rows(session, owner_ids, first, last, group_by)
        known = await _group_keys(session, group_by, {r[0] for r in rows})
        groups = [
            WinLossGroup(group=_key(group_by, k, known), **_win_loss(w, wa, lc, la))
            for k, w, wa, lc, la in rows
        ]
        groups.sort(
            key=lambda g: (
                g.group.key
                if group_by == "month"
                else (-(g.won_count + g.lost_count), g.group.name_en or "")
            )
        )
    return WinLossReport(
        from_date=first,
        to_date=last,
        group_by=group_by,
        totals=WinLossFigures(**_win_loss(won, won_amount, lost, lost_amount)),
        groups=groups,
    )
