"""Activities, tasks and timelines (FR-ACT-01..03). Public API of the module.

Activities link to leads, opportunities, organisations and contacts through
those modules' public functions. Timelines merge activities with system events
that `record_event` stores from the domain event bus (ADR 0020).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus
from app.core.listing import ListQuery, Page, SyncPage, encode_cursor, fetch_page, fetch_sync
from app.core.policy import MANAGER_ROLES, can_edit_owned
from app.core.principal import Principal
from app.core.text import search_terms
from app.modules.activity import repository
from app.modules.activity.models import Activity, TimelineEvent
from app.modules.activity.repository import TimelineScope
from app.modules.activity.schemas import (
    ActivityCreate,
    ActivityLinks,
    ActivityOut,
    ActivityUpdate,
    LinkSummary,
    TimelineEventOut,
    TimelineItem,
    UserSummary,
)
from app.modules.identity import service as identity
from app.modules.party import service as party
from app.modules.sales import service as sales

ACTIVITY_SORT = {
    "occurred_at": Activity.occurred_at,
    "due_at": Activity.due_at,
    "created_at": Activity.created_at,
    "updated_at": Activity.updated_at,
}
TIMELINE_ENTITIES = frozenset({"lead", "opportunity", "organization", "contact"})
# Domain event verbs shown on timelines (API spec 11); others (e.g. logins) are not.
TIMELINE_EVENTS = frozenset(
    {
        "created",
        "updated",
        "owner_changed",
        "status_changed",
        "stage_changed",
        "converted",
        "closed_won",
        "closed_lost",
        "reopened",
        "archived",
        "restored",
    }
)


@dataclass(frozen=True, slots=True)
class Context:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime


@dataclass(frozen=True, slots=True)
class ActivityFilters:
    types: tuple[str, ...] = ()
    lead_ids: tuple[UUID, ...] = ()
    opportunity_ids: tuple[UUID, ...] = ()
    organization_ids: tuple[UUID, ...] = ()
    contact_ids: tuple[UUID, ...] = ()
    owner_ids: tuple[UUID, ...] = ()
    assignee_ids: tuple[UUID, ...] = ()
    is_done: bool | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None


# --- Helpers ------------------------------------------------------------------------------


def _not_found() -> AppError:
    return AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)


def _invalid(field: str, code: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED,
        HTTPStatus.UNPROCESSABLE_CONTENT,
        errors=[FieldError(field, code)],
    )


def _user(names: Mapping[UUID, str], user_id: UUID | None) -> UserSummary | None:
    return UserSummary(id=user_id, full_name=names.get(user_id, "")) if user_id else None


def _view(activity: Activity) -> dict[str, Any]:
    """Fields recorded in the audit log and compared for changes."""

    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    def text(value: UUID | None) -> str | None:
        return str(value) if value else None

    return {
        "type": activity.type,
        "subject": activity.subject,
        "body": activity.body,
        "occurred_at": iso(activity.occurred_at),
        "due_at": iso(activity.due_at),
        "done_at": iso(activity.done_at),
        "owner_id": text(activity.owner_id),
        "assignee_id": text(activity.assignee_id),
        "lead_id": text(activity.lead_id),
        "opportunity_id": text(activity.opportunity_id),
        "organization_id": text(activity.organization_id),
        "contact_id": text(activity.contact_id),
    }


async def _publish(
    ctx: Context,
    action: str,
    activity: Activity,
    principal: Principal,
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> None:
    await ctx.events.publish(
        ctx.session,
        DomainEvent(
            action=action,
            entity_type="activity",
            entity_id=activity.id,
            actor=principal,
            occurred_at=ctx.now,
            before=before,
            after=after,
        ),
    )


async def _outs(ctx: Context, activities: list[Activity]) -> list[ActivityOut]:
    session = ctx.session
    names = await identity.user_names(
        session,
        {a.owner_id for a in activities}
        | {a.assignee_id for a in activities if a.assignee_id}
        | {a.created_by for a in activities if a.created_by},
    )
    leads = await sales.links.lead_names(session, {a.lead_id for a in activities if a.lead_id})
    opportunities = await sales.links.opportunity_names(
        session, {a.opportunity_id for a in activities if a.opportunity_id}
    )
    organizations = {
        i: await party.organization_summary(session, i)
        for i in {a.organization_id for a in activities if a.organization_id}
    }
    contacts = {
        i: await party.contact_link(session, i, include_archived=True)
        for i in {a.contact_id for a in activities if a.contact_id}
    }
    out: list[ActivityOut] = []
    for a in activities:
        owner = _user(names, a.owner_id)
        assert owner is not None  # noqa: S101 - owner_id is NOT NULL
        org = organizations.get(a.organization_id) if a.organization_id else None
        contact = contacts.get(a.contact_id) if a.contact_id else None
        is_task = a.type == "task"
        out.append(
            ActivityOut(
                id=a.id,
                type=a.type,  # type: ignore[arg-type]
                subject=a.subject,
                body=a.body,
                occurred_at=a.occurred_at,
                due_at=a.due_at,
                done_at=a.done_at,
                is_done=a.done_at is not None,
                is_overdue=is_task
                and a.done_at is None
                and a.due_at is not None
                and a.due_at < ctx.now,
                owner=owner,
                assignee=_user(names, a.assignee_id),
                links=ActivityLinks(
                    lead=LinkSummary(id=a.lead_id, name=leads.get(a.lead_id, ""))
                    if a.lead_id
                    else None,
                    opportunity=LinkSummary(
                        id=a.opportunity_id, name=opportunities.get(a.opportunity_id, "")
                    )
                    if a.opportunity_id
                    else None,
                    organization=LinkSummary(id=org.id, name=org.name) if org else None,
                    contact=LinkSummary(id=contact.id, name=contact.full_name) if contact else None,
                ),
                created_at=a.created_at,
                updated_at=a.updated_at,
                created_by=_user(names, a.created_by),
                archived_at=a.archived_at,
                version=a.version,
            )
        )
    return out


async def _fresh(ctx: Context, activity_id: UUID) -> ActivityOut:
    ctx.session.expire_all()
    activity = await repository.get_activity(ctx.session, activity_id)
    assert activity is not None  # noqa: S101 - exists
    return (await _outs(ctx, [activity]))[0]


async def _check_links(ctx: Context, data: ActivityCreate) -> None:
    """FR-ACT-01: at least one link; each to an existing, non-archived record."""
    session = ctx.session
    if not any((data.lead_id, data.opportunity_id, data.organization_id, data.contact_id)):
        raise _invalid("links", "activity.link_required")
    checks: list[tuple[str, str | None]] = []
    if data.lead_id:
        checks.append(("lead_id", await sales.links.check_lead_link(session, data.lead_id)))
    if data.opportunity_id:
        checks.append(
            (
                "opportunity_id",
                await sales.links.check_opportunity_link(session, data.opportunity_id),
            )
        )
    if data.organization_id:
        checks.append(
            (
                "organization_id",
                await party.check_organization_link(session, data.organization_id),
            )
        )
    if data.contact_id and await party.contact_link(session, data.contact_id) is None:
        checks.append(("contact_id", "contact.not_found"))
    for field, problem in checks:
        if problem:
            raise _invalid(field, problem)


async def _check_owner(ctx: Context, principal: Principal, owner_id: UUID) -> None:
    """Same rule as other records (FR-LEAD-06): Reps only themselves, Managers+ anyone active."""
    if (
        owner_id != principal.user_id
        and principal.role not in MANAGER_ROLES
        and not principal.is_integration
    ):
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
    if not await identity.is_assignable_owner(ctx.session, owner_id):
        raise _invalid("owner_id", "owner.invalid")


async def _check_assignee(ctx: Context, assignee_id: UUID) -> None:
    """Tasks go to any active user who can change records (owner decision, Phase 4)."""
    if not await identity.is_contributor(ctx.session, assignee_id):
        raise _invalid("assignee_id", "assignee.invalid")


def _may_edit(principal: Principal, activity: Activity) -> bool:
    """Owner+, or the assignee of a task (API spec 11)."""
    if can_edit_owned(principal, activity.owner_id):
        return True
    return activity.type == "task" and activity.assignee_id == principal.user_id


async def _touch(ctx: Context, activity: Activity, at: datetime) -> None:
    """Logged activity keeps an opportunity fresh (FR-OPP-06)."""
    if activity.opportunity_id is not None:
        await sales.links.touch_opportunity(ctx.session, activity.opportunity_id, min(at, ctx.now))


async def _load(ctx: Context, activity_id: UUID, version: int | None = None) -> Activity:
    activity = await repository.get_activity(ctx.session, activity_id, for_update=True)
    if activity is None:
        raise _not_found()
    if version is not None and activity.version != version:
        current = (await _outs(ctx, [activity]))[0]
        raise AppError(
            ErrorCode.CONFLICT_VERSION_MISMATCH,
            HTTPStatus.CONFLICT,
            extra={"current": current.model_dump(mode="json")},
        )
    if activity.archived_at is not None:
        raise AppError(ErrorCode.RESOURCE_ARCHIVED, HTTPStatus.CONFLICT)
    return activity


async def _commit(
    ctx: Context, principal: Principal, activity: Activity, action: str, before: Mapping[str, Any]
) -> ActivityOut:
    activity.updated_by = principal.user_id
    after = _view(activity)
    if after != before:
        activity.version += 1
        await _publish(ctx, action, activity, principal, before=before, after=after)
    await ctx.session.commit()
    return await _fresh(ctx, activity.id)


# --- Activities -----------------------------------------------------------------------------


async def create_activity(ctx: Context, principal: Principal, data: ActivityCreate) -> ActivityOut:
    """FR-ACT-01, FR-ACT-02: log an interaction or create a task."""
    owner_id = data.owner_id or principal.user_id
    await _check_owner(ctx, principal, owner_id)
    await _check_links(ctx, data)
    assignee_id: UUID | None = None
    if data.type == "task":
        if data.due_at is None:
            raise _invalid("due_at", "activity.due_required")
        assignee_id = data.assignee_id or owner_id
        await _check_assignee(ctx, assignee_id)
    else:
        for field in ("due_at", "assignee_id"):
            if getattr(data, field) is not None:
                raise _invalid(field, "activity.task_only")
    activity = Activity(
        **data.model_dump(exclude={"owner_id", "assignee_id", "occurred_at"}),
        occurred_at=data.occurred_at or ctx.now,
        owner_id=owner_id,
        assignee_id=assignee_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    ctx.session.add(activity)
    await ctx.session.flush()
    if activity.type != "task":
        await _touch(ctx, activity, activity.occurred_at)
    await _publish(ctx, "activity.created", activity, principal, after=_view(activity))
    await ctx.session.commit()
    return await _fresh(ctx, activity.id)


async def get_activity(ctx: Context, activity_id: UUID) -> ActivityOut:
    activity = await repository.get_activity(ctx.session, activity_id)
    if activity is None:
        raise _not_found()
    return (await _outs(ctx, [activity]))[0]


async def list_activities(
    ctx: Context, query: ListQuery, filters: ActivityFilters
) -> Page[ActivityOut] | SyncPage[ActivityOut]:
    statement = repository.activities_statement(
        include_archived=query.include_archived,
        search=search_terms(query.q) if query.q else None,
        types=filters.types,
        lead_ids=filters.lead_ids,
        opportunity_ids=filters.opportunity_ids,
        organization_ids=filters.organization_ids,
        contact_ids=filters.contact_ids,
        owner_ids=filters.owner_ids,
        assignee_ids=filters.assignee_ids,
        is_done=filters.is_done,
        due_from=filters.due_from,
        due_to=filters.due_to,
        occurred_from=filters.occurred_from,
        occurred_to=filters.occurred_to,
    )
    if query.sync:
        rows, cursor = await fetch_sync(
            ctx.session, statement, query, Activity.updated_at, Activity.id,
            safety_lag_seconds=ctx.settings.sync_safety_lag_seconds,
        )  # fmt: skip
        return SyncPage[ActivityOut](
            items=await _outs(ctx, rows),
            next_cursor=encode_cursor(ctx.settings.app_secret_key, query.resource, cursor)
            if cursor
            else None,
        )
    rows, total = await fetch_page(ctx.session, statement, query, ACTIVITY_SORT, Activity.id)
    return Page[ActivityOut](
        items=await _outs(ctx, rows), total=total, page=query.page, page_size=query.page_size
    )


async def my_tasks(
    ctx: Context, principal: Principal, query: ListQuery, include_done: bool
) -> Page[ActivityOut]:
    """FR-ACT-02: the caller's open tasks, overdue first (earliest due date first)."""
    statement = repository.activities_statement(
        include_archived=False,
        types=("task",),
        assignee_ids=(principal.user_id,),
        is_done=None if include_done else False,
    )
    rows, total = await fetch_page(ctx.session, statement, query, ACTIVITY_SORT, Activity.id)
    return Page[ActivityOut](
        items=await _outs(ctx, rows), total=total, page=query.page, page_size=query.page_size
    )


async def update_activity(
    ctx: Context, principal: Principal, activity_id: UUID, data: ActivityUpdate
) -> ActivityOut:
    for field in ("type", "owner_id", "done"):
        if field in data.model_fields_set:
            raise AppError(
                ErrorCode.VALIDATION_USE_ACTION_ENDPOINT,
                HTTPStatus.UNPROCESSABLE_CONTENT,
                errors=[FieldError(field, "validation.use_action_endpoint")],
            )
    activity = await _load(ctx, activity_id, data.version)
    if not _may_edit(principal, activity):
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
    changes = data.model_dump(exclude_unset=True, exclude={"version", "type", "owner_id", "done"})
    if "subject" in changes and changes["subject"] is None:
        raise _invalid("subject", "validation.missing")
    if activity.type != "task":
        for field in ("due_at", "assignee_id"):
            if changes.get(field) is not None:
                raise _invalid(field, "activity.task_only")
    else:
        if "due_at" in changes and changes["due_at"] is None:
            raise _invalid("due_at", "activity.due_required")
        if changes.get("assignee_id") is not None:
            await _check_assignee(ctx, changes["assignee_id"])
        elif "assignee_id" in changes:
            raise _invalid("assignee_id", "validation.missing")
    if "occurred_at" in changes and changes["occurred_at"] is None:
        raise _invalid("occurred_at", "validation.missing")
    before = _view(activity)
    for key, value in changes.items():
        setattr(activity, key, value)
    if activity.type != "task" and "occurred_at" in changes:
        await _touch(ctx, activity, activity.occurred_at)
    return await _commit(ctx, principal, activity, "activity.updated", before)


async def _set_done(
    ctx: Context, principal: Principal, activity_id: UUID, version: int, done: bool
) -> ActivityOut:
    activity = await _load(ctx, activity_id, version)
    if not _may_edit(principal, activity):
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
    if activity.type != "task":
        raise AppError(ErrorCode.ACTIVITY_NOT_A_TASK, HTTPStatus.CONFLICT)
    before = _view(activity)
    if done and activity.done_at is None:
        activity.done_at = ctx.now
        await _touch(ctx, activity, ctx.now)
    elif not done:
        activity.done_at = None
    action = "activity.completed" if done else "activity.reopened"
    return await _commit(ctx, principal, activity, action, before)


async def complete_task(
    ctx: Context, principal: Principal, activity_id: UUID, version: int
) -> ActivityOut:
    """FR-ACT-02: the owner (Owner+) or the assignee marks a task done."""
    return await _set_done(ctx, principal, activity_id, version, done=True)


async def reopen_task(
    ctx: Context, principal: Principal, activity_id: UUID, version: int
) -> ActivityOut:
    return await _set_done(ctx, principal, activity_id, version, done=False)


async def archive_activity(ctx: Context, principal: Principal, activity_id: UUID) -> None:
    activity = await repository.get_activity(ctx.session, activity_id, for_update=True)
    if activity is None:
        raise _not_found()
    if not can_edit_owned(principal, activity.owner_id):
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
    if activity.archived_at is None:
        activity.archived_at = ctx.now
        activity.updated_by = principal.user_id
        activity.version += 1
        await _publish(ctx, "activity.archived", activity, principal)
    await ctx.session.commit()


# --- Timelines (FR-ACT-03) --------------------------------------------------------------------


async def _event_data(ctx: Context, events: list[TimelineEvent]) -> dict[UUID, dict[str, Any]]:
    """Resolve the IDs stored in event data to names (users, stages, loss reasons)."""
    session = ctx.session
    user_ids: set[UUID] = set()
    stage_ids: set[UUID] = set()
    reason_ids: set[UUID] = set()
    opportunity_ids: set[UUID] = set()
    for event in events:
        for key, value in event.data.items():
            if value and key.endswith("owner_id"):
                user_ids.add(UUID(value))
            elif value and key.endswith("stage_id"):
                stage_ids.add(UUID(value))
            elif value and key == "loss_reason_id":
                reason_ids.add(UUID(value))
            elif value and key == "opportunity_id":
                opportunity_ids.add(UUID(value))
    names = await identity.user_names(session, user_ids)
    stages = await sales.links.stage_summaries(session, stage_ids)
    reasons = await sales.links.loss_reason_summaries(session, reason_ids)
    opportunities = await sales.links.opportunity_names(session, opportunity_ids)
    resolved: dict[UUID, dict[str, Any]] = {}
    for event in events:
        data: dict[str, Any] = {}
        for key, value in event.data.items():
            if key.endswith("_id") and value:
                name = key.removesuffix("_id")
                item_id = UUID(value)
                if key.endswith("owner_id"):
                    data[name] = {"id": value, "full_name": names.get(item_id, "")}
                elif key.endswith("stage_id") and item_id in stages:
                    data[name] = stages[item_id].model_dump(mode="json")
                elif key == "loss_reason_id" and item_id in reasons:
                    data[name] = reasons[item_id].model_dump(mode="json")
                elif key == "opportunity_id":
                    data[name] = {"id": value, "name": opportunities.get(item_id, "")}
                else:
                    data[key] = value
            else:
                data[key] = value
        resolved[event.id] = data
    return resolved


async def _timeline(
    ctx: Context, scope: TimelineScope, page: int, page_size: int
) -> Page[TimelineItem]:
    keys, total = await repository.timeline_page(ctx.session, scope, page=page, page_size=page_size)
    activity_rows = await repository.get_activities(
        ctx.session, [i for kind, i in keys if kind == "activity"]
    )
    event_rows = await repository.get_events(
        ctx.session, [i for kind, i in keys if kind == "event"]
    )
    activities = {a.id: a for a in await _outs(ctx, activity_rows)}
    events = {e.id: e for e in event_rows}
    data = await _event_data(ctx, event_rows)
    actors = await identity.user_names(ctx.session, {e.actor_id for e in event_rows if e.actor_id})
    items: list[TimelineItem] = []
    for kind, item_id in keys:
        if kind == "activity":
            activity = activities[item_id]
            items.append(
                TimelineItem(
                    id=item_id,
                    kind="activity",
                    occurred_at=activity.occurred_at,
                    actor=activity.owner,
                    activity=activity,
                )
            )
        else:
            event = events[item_id]
            items.append(
                TimelineItem(
                    id=item_id,
                    kind="event",
                    occurred_at=event.occurred_at,
                    actor=_user(actors, event.actor_id),
                    event=TimelineEventOut(
                        type=event.event_type,
                        entity_type=event.entity_type,
                        entity_id=event.entity_id,
                        data=data[event.id],
                    ),
                )
            )
    return Page[TimelineItem](items=items, total=total, page=page, page_size=page_size)


async def lead_timeline(
    ctx: Context, lead_id: UUID, page: int, page_size: int
) -> Page[TimelineItem]:
    if not await sales.links.lead_exists(ctx.session, lead_id):
        raise _not_found()
    return await _timeline(ctx, TimelineScope(leads=(lead_id,)), page, page_size)


async def opportunity_timeline(
    ctx: Context, opportunity_id: UUID, page: int, page_size: int
) -> Page[TimelineItem]:
    """FR-LEAD-04 AC3: includes the activities and events of the source lead."""
    exists, source_lead = await sales.links.opportunity_source(ctx.session, opportunity_id)
    if not exists:
        raise _not_found()
    scope = TimelineScope(
        opportunities=(opportunity_id,), leads=(source_lead,) if source_lead else ()
    )
    return await _timeline(ctx, scope, page, page_size)


async def contact_timeline(
    ctx: Context, contact_id: UUID, page: int, page_size: int
) -> Page[TimelineItem]:
    if await party.contact_link(ctx.session, contact_id, include_archived=True) is None:
        raise _not_found()
    return await _timeline(ctx, TimelineScope(contacts=(contact_id,)), page, page_size)


async def organization_timeline(
    ctx: Context, organization_id: UUID, page: int, page_size: int
) -> Page[TimelineItem]:
    """The organisation and its contacts, leads and opportunities (API spec 7)."""
    if await party.organization_summary(ctx.session, organization_id) is None:
        raise _not_found()
    leads, opportunities = await sales.links.organization_records(ctx.session, organization_id)
    scope = TimelineScope(
        organizations=(organization_id,),
        contacts=tuple(await party.organization_contact_ids(ctx.session, organization_id)),
        leads=tuple(leads),
        opportunities=tuple(opportunities),
    )
    return await _timeline(ctx, scope, page, page_size)


# --- Event subscriber (registered in app.main) -----------------------------------------------


def _event_data_from(verb: str, event: DomainEvent) -> dict[str, Any]:
    before = event.before or {}
    after = event.after or {}
    if verb == "owner_changed":
        return {"from_owner_id": before.get("owner_id"), "to_owner_id": after.get("owner_id")}
    if verb == "status_changed":
        return {"from_status": before.get("status"), "to_status": after.get("status")}
    if verb in {"stage_changed", "closed_won", "closed_lost", "reopened"}:
        data = {"from_stage_id": before.get("stage_id"), "to_stage_id": after.get("stage_id")}
        if verb == "closed_lost":
            data["loss_reason_id"] = after.get("loss_reason_id")
        return data
    if verb == "converted":
        return {"opportunity_id": after.get("converted_opportunity_id")}
    if verb == "updated":
        return {"fields": sorted(k for k in after if before.get(k) != after.get(k))}
    return {}


async def record_event(session: AsyncSession, event: DomainEvent) -> None:
    """Store timeline events for record changes, in the same transaction (ADR 0020)."""
    entity_type, _, verb = event.action.partition(".")
    if (
        entity_type not in TIMELINE_ENTITIES
        or verb not in TIMELINE_EVENTS
        or event.entity_id is None
        or entity_type != event.entity_type
    ):
        return
    session.add(
        TimelineEvent(
            entity_type=entity_type,
            entity_id=event.entity_id,
            event_type=verb,
            occurred_at=event.occurred_at,
            actor_id=event.actor.user_id if event.actor else None,
            data=_event_data_from(verb, event),
        )
    )
