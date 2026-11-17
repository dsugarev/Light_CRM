"""Database queries. Called only by this module's service."""

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listing import search_condition
from app.modules.sales.lifecycle import OPEN_STATUSES
from app.modules.sales.models import (
    DisqualificationReason,
    Lead,
    LeadSource,
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
