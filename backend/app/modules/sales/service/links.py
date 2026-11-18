"""Sales records as seen by other modules (activities and timelines, Phase 4b).

Only small, read-mostly functions that work on a session; the activity module
uses them to validate links, build merged timelines and keep
`opportunity.last_activity_at` current (FR-OPP-06).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales import repository
from app.modules.sales.schemas import ReferenceSummary, StageSummary
from app.modules.sales.service.common import reference
from app.modules.sales.service.pipelines import stage_summary


async def check_lead_link(session: AsyncSession, lead_id: UUID) -> str | None:
    """Field code when an activity cannot be linked to the lead, else None."""
    lead = await repository.get_lead(session, lead_id)
    if lead is None:
        return "lead.not_found"
    return "lead.archived" if lead.archived_at is not None else None


async def check_opportunity_link(session: AsyncSession, opportunity_id: UUID) -> str | None:
    opportunity = await repository.get_opportunity(session, opportunity_id)
    if opportunity is None:
        return "opportunity.not_found"
    return "opportunity.archived" if opportunity.archived_at is not None else None


async def lead_exists(session: AsyncSession, lead_id: UUID) -> bool:
    return await repository.get_lead(session, lead_id) is not None


async def opportunity_source(
    session: AsyncSession, opportunity_id: UUID
) -> tuple[bool, UUID | None]:
    """Whether the opportunity exists, and its source lead (FR-LEAD-04 AC3)."""
    opportunity = await repository.get_opportunity(session, opportunity_id)
    if opportunity is None:
        return False, None
    return True, opportunity.source_lead_id


async def organization_records(
    session: AsyncSession, organization_id: UUID
) -> tuple[list[UUID], list[UUID]]:
    """IDs of the organisation's leads and opportunities, archived included."""
    return (
        await repository.lead_ids_of_organization(session, organization_id),
        await repository.opportunity_ids_of_organization(session, organization_id),
    )


async def touch_opportunity(session: AsyncSession, opportunity_id: UUID, at: datetime) -> None:
    """Record activity on an opportunity: it is no longer stale for `at` (FR-OPP-06)."""
    await repository.touch_opportunity(session, opportunity_id, at)


async def stage_summaries(session: AsyncSession, ids: set[UUID]) -> dict[UUID, StageSummary]:
    return {s.id: stage_summary(s) for s in await repository.get_stages(session, ids)}


async def loss_reason_summaries(
    session: AsyncSession, ids: set[UUID]
) -> dict[UUID, ReferenceSummary]:
    out: dict[UUID, ReferenceSummary] = {}
    for item in await repository.get_loss_reasons(session, ids):
        summary = reference(item)
        if summary is not None:
            out[item.id] = summary
    return out


async def lead_names(session: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    return await repository.lead_titles(session, ids)


async def opportunity_names(session: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    return await repository.opportunity_names(session, ids)


async def find_open_stage(session: AsyncSession, text: str) -> UUID | None:
    """An active open stage of the default pipeline by its English or Bulgarian name
    (case-insensitive), for imports."""
    pipeline = await repository.get_default_pipeline(session)
    wanted = text.strip().casefold()
    for stage in pipeline.stages if pipeline else []:
        if (
            stage.is_active
            and stage.stage_type == "open"
            and wanted in (stage.name_en.casefold(), stage.name_bg.casefold())
        ):
            return stage.id
    return None


async def record_stamps(
    session: AsyncSession, kind: Literal["lead", "opportunity"], ids: set[UUID]
) -> dict[UUID, datetime]:
    """updated_at of many leads or opportunities (import rollback detects later changes)."""
    return await repository.updated_at_of(session, kind, ids)
