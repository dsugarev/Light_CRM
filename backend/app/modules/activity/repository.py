"""Database queries. Called only by this module's service."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, Select, false, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.listing import search_condition
from app.modules.activity.models import Activity, TimelineEvent


async def get_activity(
    session: AsyncSession, activity_id: UUID, *, for_update: bool = False
) -> Activity | None:
    statement = select(Activity).where(Activity.id == activity_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def get_activities(session: AsyncSession, ids: Sequence[UUID]) -> list[Activity]:
    if not ids:
        return []
    return list((await session.execute(select(Activity).where(Activity.id.in_(ids)))).scalars())


async def get_events(session: AsyncSession, ids: Sequence[UUID]) -> list[TimelineEvent]:
    if not ids:
        return []
    statement = select(TimelineEvent).where(TimelineEvent.id.in_(ids))
    return list((await session.execute(statement)).scalars())


def activities_statement(
    *,
    include_archived: bool,
    search: Sequence[Sequence[str]] | None = None,
    types: Sequence[str] = (),
    lead_ids: Sequence[UUID] = (),
    opportunity_ids: Sequence[UUID] = (),
    organization_ids: Sequence[UUID] = (),
    contact_ids: Sequence[UUID] = (),
    owner_ids: Sequence[UUID] = (),
    assignee_ids: Sequence[UUID] = (),
    is_done: bool | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
) -> Select[Activity]:
    statement = select(Activity)
    if not include_archived:
        statement = statement.where(Activity.archived_at.is_(None))
    if search:
        statement = statement.where(search_condition(Activity.subject, search))
    for values, column in (
        (types, Activity.type),
        (lead_ids, Activity.lead_id),
        (opportunity_ids, Activity.opportunity_id),
        (organization_ids, Activity.organization_id),
        (contact_ids, Activity.contact_id),
        (owner_ids, Activity.owner_id),
        (assignee_ids, Activity.assignee_id),
    ):
        if values:
            statement = statement.where(column.in_(values))
    if is_done is not None:
        statement = statement.where(
            Activity.type == "task",
            Activity.done_at.is_not(None) if is_done else Activity.done_at.is_(None),
        )
    if due_from is not None:
        statement = statement.where(Activity.due_at >= due_from)
    if due_to is not None:
        statement = statement.where(Activity.due_at <= due_to)
    if occurred_from is not None:
        statement = statement.where(Activity.occurred_at >= occurred_from)
    if occurred_to is not None:
        statement = statement.where(Activity.occurred_at <= occurred_to)
    return statement


@dataclass(frozen=True, slots=True)
class TimelineScope:
    """Records whose activities and events make up one timeline."""

    leads: Sequence[UUID] = ()
    opportunities: Sequence[UUID] = ()
    organizations: Sequence[UUID] = ()
    contacts: Sequence[UUID] = ()


def _in(
    column: InstrumentedAttribute[UUID | None] | InstrumentedAttribute[UUID], ids: Sequence[UUID]
) -> ColumnElement[bool]:
    return column.in_(ids) if ids else false()


async def timeline_page(
    session: AsyncSession, scope: TimelineScope, *, page: int, page_size: int
) -> tuple[list[tuple[str, UUID]], int]:
    """(kind, id) of one page, newest first, and the total number of items."""
    activities = select(
        literal("activity").label("kind"), Activity.id.label("id"), Activity.occurred_at.label("at")
    ).where(
        Activity.archived_at.is_(None),
        or_(
            _in(Activity.lead_id, scope.leads),
            _in(Activity.opportunity_id, scope.opportunities),
            _in(Activity.organization_id, scope.organizations),
            _in(Activity.contact_id, scope.contacts),
        ),
    )
    events = select(
        literal("event").label("kind"),
        TimelineEvent.id.label("id"),
        TimelineEvent.occurred_at.label("at"),
    ).where(
        or_(
            *(
                (TimelineEvent.entity_type == entity_type) & _in(TimelineEvent.entity_id, ids)
                for entity_type, ids in (
                    ("lead", scope.leads),
                    ("opportunity", scope.opportunities),
                    ("organization", scope.organizations),
                    ("contact", scope.contacts),
                )
            )
        )
    )
    merged = union_all(activities, events).subquery()
    total = (await session.execute(select(func.count()).select_from(merged))).scalar_one()
    rows = await session.execute(
        select(merged.c.kind, merged.c.id)
        .order_by(merged.c.at.desc(), merged.c.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [(kind, item_id) for kind, item_id in rows.all()], total


async def open_task_counts(session: AsyncSession, user_id: UUID, now: datetime) -> tuple[int, int]:
    """(open, overdue) tasks assigned to the user."""
    statement = select(func.count(), func.count().filter(Activity.due_at < now)).where(
        Activity.type == "task",
        Activity.assignee_id == user_id,
        Activity.done_at.is_(None),
        Activity.archived_at.is_(None),
    )
    open_count, overdue = (await session.execute(statement)).one()
    return open_count, overdue
