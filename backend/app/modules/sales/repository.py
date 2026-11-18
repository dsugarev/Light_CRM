"""Database queries. Called only by this module's service."""

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listing import search_condition
from app.modules.sales.lifecycle import OPEN_STATUSES
from app.modules.sales.models import (
    DisqualificationReason,
    Lead,
    LeadSource,
    LossReason,
    Opportunity,
    OpportunityStageHistory,
    Pipeline,
    PipelineStage,
)


async def get_lead(
    session: AsyncSession, lead_id: UUID, *, for_update: bool = False
) -> Lead | None:
    statement = select(Lead).where(Lead.id == lead_id)
    if for_update:
        statement = statement.with_for_update(of=Lead)
    return (await session.execute(statement)).unique().scalar_one_or_none()


def leads_statement(
    *,
    search: Sequence[Sequence[str]] | None,
    include_archived: bool,
    statuses: Sequence[str],
    owner_ids: Sequence[UUID],
    source_ids: Sequence[UUID],
    organization_ids: Sequence[UUID],
    created_from: datetime | None,
    created_to: datetime | None,
    fits_target_profile: bool | None,
) -> Select[Lead]:
    statement = select(Lead)
    if not include_archived:
        statement = statement.where(Lead.archived_at.is_(None))
    if search:
        statement = statement.where(search_condition(Lead.search_text, search))
    if statuses:
        statement = statement.where(Lead.status.in_(statuses))
    if owner_ids:
        statement = statement.where(Lead.owner_id.in_(owner_ids))
    if source_ids:
        statement = statement.where(Lead.source_id.in_(source_ids))
    if organization_ids:
        statement = statement.where(Lead.organization_id.in_(organization_ids))
    if created_from is not None:
        statement = statement.where(Lead.created_at >= created_from)
    if created_to is not None:
        statement = statement.where(Lead.created_at <= created_to)
    if fits_target_profile is not None:
        statement = statement.where(Lead.fits_target_profile.is_(fits_target_profile))
    return statement


async def count_open_leads(session: AsyncSession, organization_id: UUID) -> int:
    statement = select(func.count()).where(
        Lead.organization_id == organization_id,
        Lead.status.in_(OPEN_STATUSES),
        Lead.archived_at.is_(None),
    )
    return (await session.execute(statement)).scalar_one()


async def count_with_source(session: AsyncSession, source_id: UUID) -> int:
    return (
        await session.execute(select(func.count()).where(Lead.source_id == source_id))
    ).scalar_one()


async def count_with_disqualification_reason(session: AsyncSession, reason_id: UUID) -> int:
    statement = select(func.count()).where(Lead.disqualification_reason_id == reason_id)
    return (await session.execute(statement)).scalar_one()


async def get_source(session: AsyncSession, source_id: UUID) -> LeadSource | None:
    return await session.get(LeadSource, source_id)


async def get_disqualification_reason(
    session: AsyncSession, reason_id: UUID
) -> DisqualificationReason | None:
    return await session.get(DisqualificationReason, reason_id)


# --- Pipelines and stages -----------------------------------------------------------------


async def list_pipelines(session: AsyncSession) -> list[Pipeline]:
    statement = select(Pipeline).order_by(Pipeline.is_default.desc(), Pipeline.name)
    return list((await session.execute(statement)).scalars())


async def get_pipeline(session: AsyncSession, pipeline_id: UUID) -> Pipeline | None:
    return await session.get(Pipeline, pipeline_id)


async def get_default_pipeline(session: AsyncSession) -> Pipeline | None:
    statement = select(Pipeline).where(Pipeline.is_default.is_(True)).limit(1)
    return (await session.execute(statement)).scalar_one_or_none()


async def get_stage(session: AsyncSession, stage_id: UUID) -> PipelineStage | None:
    return await session.get(PipelineStage, stage_id)


async def stage_usage(session: AsyncSession, stage_id: UUID) -> int:
    in_opportunities = (
        await session.execute(select(func.count()).where(Opportunity.stage_id == stage_id))
    ).scalar_one()
    in_history = (
        await session.execute(
            select(func.count()).where(
                (OpportunityStageHistory.to_stage_id == stage_id)
                | (OpportunityStageHistory.from_stage_id == stage_id)
            )
        )
    ).scalar_one()
    return in_opportunities + in_history


# --- Opportunities ------------------------------------------------------------------------


async def get_opportunity(
    session: AsyncSession, opportunity_id: UUID, *, for_update: bool = False
) -> Opportunity | None:
    statement = select(Opportunity).where(Opportunity.id == opportunity_id)
    if for_update:
        statement = statement.with_for_update(of=Opportunity)
    return (await session.execute(statement)).unique().scalar_one_or_none()


def stale_condition(stale_before: datetime, today: date) -> ColumnElement[bool]:
    """Open, and no activity since `stale_before` or the expected close date has passed."""
    return and_(
        PipelineStage.stage_type == "open",
        or_(
            func.coalesce(Opportunity.last_activity_at, Opportunity.created_at) < stale_before,
            Opportunity.expected_close_date < today,
        ),
    )


def opportunities_statement(
    *,
    search: Sequence[Sequence[str]] | None,
    include_archived: bool,
    stage_ids: Sequence[UUID] = (),
    stage_types: Sequence[str] = (),
    owner_ids: Sequence[UUID] = (),
    organization_ids: Sequence[UUID] = (),
    pipeline_ids: Sequence[UUID] = (),
    close_from: date | None = None,
    close_to: date | None = None,
    amount_from: Decimal | None = None,
    amount_to: Decimal | None = None,
    stale: tuple[bool, datetime, date] | None = None,
) -> Select[Opportunity]:
    statement = select(Opportunity).join(Opportunity.stage)
    if not include_archived:
        statement = statement.where(Opportunity.archived_at.is_(None))
    if search:
        statement = statement.where(search_condition(Opportunity.search_text, search))
    if stage_ids:
        statement = statement.where(Opportunity.stage_id.in_(stage_ids))
    if stage_types:
        statement = statement.where(PipelineStage.stage_type.in_(stage_types))
    if owner_ids:
        statement = statement.where(Opportunity.owner_id.in_(owner_ids))
    if organization_ids:
        statement = statement.where(Opportunity.organization_id.in_(organization_ids))
    if pipeline_ids:
        statement = statement.where(Opportunity.pipeline_id.in_(pipeline_ids))
    if close_from is not None:
        statement = statement.where(Opportunity.expected_close_date >= close_from)
    if close_to is not None:
        statement = statement.where(Opportunity.expected_close_date <= close_to)
    if amount_from is not None:
        statement = statement.where(Opportunity.amount >= amount_from)
    if amount_to is not None:
        statement = statement.where(Opportunity.amount <= amount_to)
    if stale is not None:
        wanted, stale_before, today = stale
        condition = stale_condition(stale_before, today)
        statement = statement.where(condition if wanted else ~condition)
    return statement


async def column_totals(
    session: AsyncSession, statement: Select[Opportunity]
) -> dict[UUID, tuple[int, Decimal, Decimal]]:
    """Per stage: count, total amount and weighted amount (amount x probability / 100)."""
    sub = statement.order_by(None).subquery()
    weighted = func.coalesce(func.sum(sub.c.amount * sub.c.probability / 100), 0)
    rows = await session.execute(
        select(
            sub.c.stage_id, func.count(), func.coalesce(func.sum(sub.c.amount), 0), weighted
        ).group_by(sub.c.stage_id)
    )
    return {stage_id: (count, Decimal(total), Decimal(w)) for stage_id, count, total, w in rows}


async def stage_history(
    session: AsyncSession, opportunity_id: UUID
) -> list[OpportunityStageHistory]:
    statement = (
        select(OpportunityStageHistory)
        .where(OpportunityStageHistory.opportunity_id == opportunity_id)
        .order_by(OpportunityStageHistory.changed_at, OpportunityStageHistory.id)
    )
    return list((await session.execute(statement)).unique().scalars())


async def open_opportunity_figures(
    session: AsyncSession, organization_id: UUID
) -> tuple[int, Decimal]:
    statement = (
        select(func.count(), func.coalesce(func.sum(Opportunity.amount), 0))
        .select_from(Opportunity)
        .join(Opportunity.stage)
        .where(
            Opportunity.organization_id == organization_id,
            Opportunity.archived_at.is_(None),
            PipelineStage.stage_type == "open",
        )
    )
    count, total = (await session.execute(statement)).one()
    return count, Decimal(total or 0)


async def count_with_loss_reason(session: AsyncSession, reason_id: UUID) -> int:
    statement = select(func.count()).where(Opportunity.loss_reason_id == reason_id)
    return (await session.execute(statement)).scalar_one()


async def opportunity_names(session: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(
        select(Opportunity.id, Opportunity.name).where(Opportunity.id.in_(ids))
    )
    return {row_id: name for row_id, name in rows.all()}  # noqa: C416 - Row to tuple


async def lead_ids_of_organization(session: AsyncSession, organization_id: UUID) -> list[UUID]:
    statement = select(Lead.id).where(Lead.organization_id == organization_id)
    return list((await session.execute(statement)).scalars())


async def opportunity_ids_of_organization(
    session: AsyncSession, organization_id: UUID
) -> list[UUID]:
    statement = select(Opportunity.id).where(Opportunity.organization_id == organization_id)
    return list((await session.execute(statement)).scalars())


async def touch_opportunity(session: AsyncSession, opportunity_id: UUID, at: datetime) -> None:
    """Move last_activity_at forward only (an older activity never makes it look staler)."""
    await session.execute(
        update(Opportunity)
        .where(Opportunity.id == opportunity_id)
        .values(last_activity_at=func.greatest(func.coalesce(Opportunity.last_activity_at, at), at))
    )


async def get_stages(session: AsyncSession, ids: set[UUID]) -> list[PipelineStage]:
    if not ids:
        return []
    return list(
        (await session.execute(select(PipelineStage).where(PipelineStage.id.in_(ids)))).scalars()
    )


async def get_loss_reasons(session: AsyncSession, ids: set[UUID]) -> list[LossReason]:
    if not ids:
        return []
    return list((await session.execute(select(LossReason).where(LossReason.id.in_(ids)))).scalars())


async def lead_titles(session: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(select(Lead.id, Lead.title).where(Lead.id.in_(ids)))
    return {row_id: name for row_id, name in rows.all()}  # noqa: C416 - Row to tuple


# --- Reports (FR-REP-01, FR-REP-03) -------------------------------------------------------------


def _owned(statement: Select[Any], column: Any, owner_ids: Sequence[UUID]) -> Select[Any]:
    return statement.where(column.in_(owner_ids)) if owner_ids else statement


async def forecast_rows(
    session: AsyncSession, owner_ids: Sequence[UUID], first: date, end: date
) -> list[tuple[str, int, Decimal, Decimal]]:
    """Open, non-archived opportunities by expected close month in [first, end)."""
    # to_char, not date_trunc: date_trunc yields a timestamp in the session time zone.
    month = func.to_char(Opportunity.expected_close_date, "YYYY-MM").label("month")
    statement = _owned(
        select(
            month,
            func.count(),
            func.coalesce(func.sum(Opportunity.amount), 0),
            func.coalesce(func.sum(Opportunity.amount * Opportunity.probability / 100), 0),
        )
        .select_from(Opportunity)
        .join(Opportunity.stage)
        .where(
            Opportunity.archived_at.is_(None),
            PipelineStage.stage_type == "open",
            Opportunity.expected_close_date >= first,
            Opportunity.expected_close_date < end,
        ),
        Opportunity.owner_id,
        owner_ids,
    ).group_by(month)
    rows = await session.execute(statement)
    return [(m, c, Decimal(t), Decimal(w)) for m, c, t, w in rows.all()]


async def lead_conversion_rows(
    session: AsyncSession,
    owner_ids: Sequence[UUID],
    start: datetime,
    end: datetime,
    group_by: str | None,
) -> list[tuple[UUID | None, int, int, int, int]]:
    """(group key, created, qualified or later, converted, disqualified) for leads created in
    [start, end), archived excluded."""
    key: Any = {"source": Lead.source_id, "owner": Lead.owner_id}.get(group_by or "")

    def status_count(statuses: tuple[str, ...]) -> Any:
        return func.count().filter(Lead.status.in_(statuses))

    statement = _owned(
        select(
            key if key is not None else literal(None),
            func.count(),
            status_count(("qualified", "converted")),
            status_count(("converted",)),
            status_count(("disqualified",)),
        )
        .select_from(Lead)
        .where(Lead.archived_at.is_(None), Lead.created_at >= start, Lead.created_at < end),
        Lead.owner_id,
        owner_ids,
    )
    if key is not None:
        statement = statement.group_by(key)
    rows = await session.execute(statement)
    return [(k, c, q, v, d) for k, c, q, v, d in rows.all()]


async def win_loss_rows(
    session: AsyncSession,
    owner_ids: Sequence[UUID],
    first: date,
    last: date,
    group_by: str | None,
) -> list[tuple[Any, int, Decimal, int, Decimal]]:
    """(group key, won count, won amount, lost count, lost amount) for opportunities closed
    between first and last (inclusive), archived excluded."""
    keys: dict[str, Any] = {
        "loss_reason": Opportunity.loss_reason_id,
        "owner": Opportunity.owner_id,
        "month": func.to_char(Opportunity.actual_close_date, "YYYY-MM"),
    }
    key = keys.get(group_by or "")
    won = PipelineStage.stage_type == "won"
    lost = PipelineStage.stage_type == "lost"
    statement = _owned(
        select(
            key if key is not None else literal(None),
            func.count().filter(won),
            func.coalesce(func.sum(Opportunity.amount).filter(won), 0),
            func.count().filter(lost),
            func.coalesce(func.sum(Opportunity.amount).filter(lost), 0),
        )
        .select_from(Opportunity)
        .join(Opportunity.stage)
        .where(
            Opportunity.archived_at.is_(None),
            PipelineStage.stage_type.in_(("won", "lost")),
            Opportunity.actual_close_date >= first,
            Opportunity.actual_close_date <= last,
        ),
        Opportunity.owner_id,
        owner_ids,
    )
    if key is not None:
        statement = statement.group_by(key)
    rows = await session.execute(statement)
    return [(k, w, Decimal(wa), lc, Decimal(la)) for k, w, wa, lc, la in rows.all()]


async def get_reference_items[R](session: AsyncSession, model: type[R], ids: set[UUID]) -> list[R]:
    if not ids:
        return []
    statement = select(model).where(model.id.in_(ids))  # type: ignore[attr-defined]
    return list((await session.execute(statement)).scalars())


async def updated_at_of(session: AsyncSession, kind: str, ids: set[UUID]) -> dict[UUID, datetime]:
    if not ids:
        return {}
    model: type[Lead] | type[Opportunity] = Lead if kind == "lead" else Opportunity
    rows = await session.execute(select(model.id, model.updated_at).where(model.id.in_(ids)))
    return {row_id: stamp for row_id, stamp in rows.all()}  # noqa: C416 - Row to tuple


# --- GDPR (FR-ADM-04) ---------------------------------------------------------------------


async def leads_of_person(
    session: AsyncSession, contact_id: UUID, email: str | None, *, for_update: bool = False
) -> list[Lead]:
    """Leads linked to the contact, or carrying the same email address."""
    match = Lead.contact_id == contact_id
    if email:
        match = or_(match, func.lower(Lead.email) == email.lower())
    statement = select(Lead).where(match).order_by(Lead.created_at, Lead.id)
    if for_update:
        statement = statement.with_for_update(of=Lead)
    return list((await session.execute(statement)).unique().scalars())


async def opportunities_of_contact(session: AsyncSession, contact_id: UUID) -> list[Opportunity]:
    statement = (
        select(Opportunity)
        .where(Opportunity.primary_contact_id == contact_id)
        .order_by(Opportunity.created_at, Opportunity.id)
    )
    return list((await session.execute(statement)).unique().scalars())
