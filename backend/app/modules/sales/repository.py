"""Database queries. Called only by this module's service."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listing import search_condition
from app.modules.sales.lifecycle import OPEN_STATUSES
from app.modules.sales.models import DisqualificationReason, Lead, LeadSource


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
