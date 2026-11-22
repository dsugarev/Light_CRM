"""The assistant's tools (architecture 8.3).

Each tool validates its arguments against a strict schema, checks the caller's access
through the shared policy, calls the same service functions as the REST endpoints, and
returns compact JSON: only the fields an answer needs, at most 25 rows, and every
record with its type, ID and in-app URL so the answer can link to it (FR-AI-02 AC2).

Reading tools read; `propose_*` tools only store a proposal that the user confirms
(FR-AI-09, ADR 0030). Since ADR 0032 Admins can also read the user list and the
settings, and everyone the configurable lists and stages, with the same access as the
screens. No tool reaches sessions, passwords, API keys, the audit log or other people's
conversations, and no email address or sign-in detail is sent to the model.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import reference, runtime_settings
from app.core.access import AccessLevel
from app.core.config import Settings
from app.core.errors import AppError
from app.core.events import EventBus
from app.core.listing import ListQuery
from app.core.policy import check_access
from app.core.principal import Principal, RoleCode
from app.llm import models
from app.modules.activity import service as activity
from app.modules.assistant import actions
from app.modules.assistant.models import AssistantAction
from app.modules.identity import service as identity
from app.modules.party import service as party
from app.modules.reporting import service as reporting
from app.modules.sales import service as sales

SOFIA = ZoneInfo("Europe/Sofia")
MAX_ROWS = 25
_TEXT_LIMIT = 600
EntityType = Literal["lead", "opportunity", "organization", "contact"]
URL_PREFIX: dict[str, str] = {
    "lead": "/leads/",
    "opportunity": "/opportunities/",
    "organization": "/organizations/",
    "contact": "/contacts/",
}


@dataclass(slots=True)
class ToolContext:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime
    principal: Principal
    locale: Literal["en", "bg"]
    organization_stats: Sequence[Any] = ()
    # Records returned by tools in this turn: (type, id) -> label, for citations.
    seen: dict[tuple[str, UUID], str] = field(default_factory=dict)
    # FR-AI-09: where proposals belong, and the ones made in this answer (ADR 0030).
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    reference_lists: Mapping[str, Any] = field(default_factory=dict)
    proposed: list[AssistantAction] = field(default_factory=list)
    # The record the user is looking at (FR-AI-03): the default link for a new activity.
    context_type: str | None = None
    context_id: UUID | None = None

    def sales(self) -> sales.Context:
        return sales.Context(self.session, self.events, self.settings, self.now)

    def party(self) -> party.Context:
        return party.Context(
            self.session, self.events, self.settings, self.now, self.organization_stats
        )

    def activity(self) -> activity.Context:
        return activity.Context(self.session, self.events, self.settings, self.now)

    def reporting(self) -> reporting.Context:
        return reporting.Context(self.session, self.events, self.settings, self.now)

    def record(self, entity_type: str, entity_id: UUID, label: str) -> dict[str, Any]:
        self.seen[(entity_type, entity_id)] = label
        return {
            "type": entity_type,
            "id": str(entity_id),
            "url": f"{URL_PREFIX[entity_type]}{entity_id}",
        }


# --- Argument schemas ------------------------------------------------------------------------


OwnerName = Annotated[
    str | None,
    Field(
        default=None,
        min_length=2,
        max_length=100,
        description="A person's name (or part of it) to limit to the records they own, "
        "e.g. 'Elena Petrova'. Use it for questions about a named colleague.",
    ),
]
PeriodFrom = Annotated[
    date | None, Field(default=None, description="Period start; default 1 January this year")
]
PeriodTo = Annotated[
    date | None, Field(default=None, description="Period end; default 31 December this year")
]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


Owner = Literal["me", "anyone"]
Limit = Annotated[int, Field(ge=1, le=MAX_ROWS)]
Query = Annotated[str, Field(min_length=1, max_length=200)]


class SearchLeads(_Args):
    query: Query | None = Field(default=None, description="Words to match in the lead")
    status: list[Literal["new", "contacted", "qualified", "converted", "disqualified"]] = []
    owner: Owner = Field(default="anyone", description="'me' for the user's own leads")
    owner_name: OwnerName = None
    limit: Limit = 10


class SearchOpportunities(_Args):
    query: Query | None = Field(default=None, description="Words to match in name or organization")
    stage_type: Literal["open", "won", "lost"] | None = None
    owner: Owner = Field(default="anyone", description="'me' for the user's own opportunities")
    owner_name: OwnerName = None
    organization_id: UUID | None = None
    close_from: date | None = Field(default=None, description="Expected close date from")
    close_to: date | None = Field(default=None, description="Expected close date to")
    closed_from: date | None = Field(
        default=None, description="Actual close date from (won or lost deals, e.g. 'won this year')"
    )
    closed_to: date | None = Field(default=None, description="Actual close date to")
    is_stale: bool | None = Field(default=None, description="No activity for a long time")
    sort: Literal["expected_close_date", "-amount", "-updated_at"] = "expected_close_date"
    limit: Limit = 10


class SearchOrganizations(_Args):
    query: Query | None = Field(default=None, description="Words to match in name or city")
    owner: Owner = "anyone"
    owner_name: OwnerName = None
    limit: Limit = 10


class SearchContacts(_Args):
    query: Query | None = Field(
        default=None, description="Words to match in the person's name, job title or notes"
    )
    organization_id: UUID | None = Field(
        default=None, description="Only people of this organization"
    )
    owner: Owner = "anyone"
    owner_name: OwnerName = None
    limit: Limit = 10


class GetRecord(_Args):
    entity_type: EntityType
    id: UUID


class ListActivities(_Args):
    lead_id: UUID | None = None
    opportunity_id: UUID | None = None
    organization_id: UUID | None = None
    contact_id: UUID | None = None
    types: list[Literal["note", "call", "meeting", "email", "task"]] = []
    owner_name: OwnerName = None
    assignee_name: Annotated[
        str | None,
        Field(
            default=None,
            min_length=2,
            max_length=100,
            description="Tasks assigned to this person (name or part of it)",
        ),
    ] = None
    open_tasks_only: bool = Field(default=False, description="Only tasks not done yet")
    overdue_only: bool = Field(default=False, description="Only open tasks past their due date")
    due_from: date | None = Field(default=None, description="Tasks due on or after this date")
    due_to: date | None = Field(default=None, description="Tasks due on or before this date")
    occurred_from: date | None = Field(default=None, description="Logged on or after this date")
    occurred_to: date | None = Field(default=None, description="Logged on or before this date")
    limit: Limit = 10


class PipelineSummary(_Args):
    owner: Owner = "anyone"
    owner_name: OwnerName = None
    group_by: Literal["stage", "owner"] = Field(
        default="stage", description="'owner' ranks the owners by their open pipeline"
    )


class ForecastSummary(_Args):
    owner: Owner = "anyone"
    owner_name: OwnerName = None
    months: Annotated[int, Field(ge=1, le=12)] = 3


class WinLossSummary(_Args):
    owner: Owner = "anyone"
    owner_name: OwnerName = None
    period_from: PeriodFrom = None
    period_to: PeriodTo = None
    group_by: Literal["loss_reason", "owner", "month"] | None = Field(
        default=None,
        description="Split the figures, e.g. by loss reason to see why deals were lost",
    )


class LeadConversionSummary(_Args):
    owner: Owner = "anyone"
    owner_name: OwnerName = None
    period_from: PeriodFrom = None
    period_to: PeriodTo = None
    group_by: Literal["source", "owner"] | None = None


class MyTasks(_Args):
    include_done: bool = False
    limit: Limit = 10


class ListUsers(_Args):
    query: Query | None = Field(default=None, description="Part of a name")
    role: Literal["admin", "sales_manager", "sales_rep", "viewer"] | None = None
    status: Literal["active", "deactivated", "locked", "any"] = "any"
    limit: Limit = 25


class GetSettings(_Args):
    pass


ListName = Literal[
    "pipeline-stages", "industries", "lead-sources", "disqualification-reasons", "loss-reasons"
]


class ListValues(_Args):
    list: ListName
    include_inactive: bool = Field(default=False, description="Admins: inactive values too")


# --- Helpers -------------------------------------------------------------------------------


def _clip(text: str | None, limit: int = _TEXT_LIMIT) -> str | None:
    if text is None or len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class OwnerNotFoundError(Exception):
    """No user matches the owner name the model passed."""


async def _owners(ctx: ToolContext, owner: str, owner_name: str | None = None) -> tuple[UUID, ...]:
    if owner_name:
        people = await identity.people_named(ctx.session, owner_name)
        if not people:
            raise OwnerNotFoundError
        return tuple(user_id for user_id, _ in people)
    return (ctx.principal.user_id,) if owner == "me" else ()


def _scope(
    ctx: ToolContext, owners: tuple[UUID, ...], first: date | None = None, last: date | None = None
) -> Any:
    rctx = ctx.reporting()
    return reporting.Scope.build(rctx, owners, first, last)


def _query(resource: str, limit: int, sort: str, q: str | None = None) -> ListQuery:
    descending = sort.startswith("-")
    return ListQuery(
        resource=resource,
        page=1,
        page_size=limit,
        sort=((sort.lstrip("-"), descending),),
        q=q,
        include_archived=False,
        updated_since=None,
        cursor=None,
    )


def _name(ctx: ToolContext, item: Any) -> str | None:
    if item is None:
        return None
    return str(item.name_bg if ctx.locale == "bg" else item.name_en)


def _day(value: datetime | date | None) -> str | None:
    return value.isoformat()[:10] if value else None


def _money(value: Any) -> str | None:
    return None if value is None else str(value)


def _lead(ctx: ToolContext, lead: Any, *, detail: bool = False) -> dict[str, Any]:
    out = {
        **ctx.record("lead", lead.id, lead.title),
        "title": lead.title,
        "company_name": lead.company_name,
        "contact_name": lead.contact_name,
        "status": lead.status,
        "source": _name(ctx, lead.source),
        "estimated_value": _money(lead.estimated_value),
        "currency": lead.currency,
        "owner": lead.owner.full_name,
        "qualification_score": lead.qualification.score,
        "fits_target_profile": lead.qualification.fits_target_profile,
        "created": _day(lead.created_at),
    }
    if lead.organization:
        out["organization"] = _link(ctx, "organization", lead.organization)
    if detail:
        q = lead.qualification
        out["description"] = _clip(lead.description)
        out["bant"] = {
            part: {"status": getattr(q, part).status, "note": _clip(getattr(q, part).note, 200)}
            for part in ("budget", "authority", "need", "timeline")
        }
        if lead.converted_opportunity:
            out["converted_opportunity"] = _link(ctx, "opportunity", lead.converted_opportunity)
    return out


def _link(ctx: ToolContext, entity_type: str, link: Any) -> dict[str, Any]:
    return {**ctx.record(entity_type, link.id, link.name), "name": link.name}


def _opportunity(ctx: ToolContext, opp: Any, *, detail: bool = False) -> dict[str, Any]:
    out = {
        **ctx.record("opportunity", opp.id, opp.name),
        "name": opp.name,
        "organization": _link(ctx, "organization", opp.organization),
        "owner": opp.owner.full_name,
        "stage": _name(ctx, opp.stage),
        "stage_type": opp.stage.stage_type,
        "amount": _money(opp.amount),
        "currency": opp.currency,
        "probability": opp.probability,
        "weighted_amount": _money(opp.weighted_amount),
        "expected_close_date": _day(opp.expected_close_date),
        "next_step": _clip(opp.next_step, 300),
        "is_stale": opp.is_stale,
        "last_activity": _day(opp.last_activity_at),
        "actual_close_date": _day(opp.actual_close_date),
        "loss_reason": _name(ctx, opp.loss_reason),
    }
    if opp.primary_contact:
        out["primary_contact"] = _link(ctx, "contact", opp.primary_contact)
    if detail:
        out["description"] = _clip(opp.description)
        out["competitor"] = opp.competitor
        if opp.source_lead:
            out["source_lead"] = _link(ctx, "lead", opp.source_lead)
    return out


def _organization(ctx: ToolContext, org: Any, *, detail: bool = False) -> dict[str, Any]:
    out = {
        **ctx.record("organization", org.id, org.name),
        "name": org.name,
        "industry": _name(ctx, org.industry),
        "size_band": org.size_band,
        "city": org.city,
        "country": org.country,
        "owner": org.owner.full_name,
    }
    if detail:
        out["notes"] = _clip(org.notes)
        out["website"] = org.website
        out["counts"] = org.counts.model_dump(mode="json")
    return out


def _contact(ctx: ToolContext, contact: Any) -> dict[str, Any]:
    # Data minimization: no email address or phone number (architecture 8.4).
    out = {
        **ctx.record("contact", contact.id, contact.full_name),
        "full_name": contact.full_name,
        "job_title": contact.job_title,
        "owner": contact.owner.full_name,
        "notes": _clip(contact.notes),
    }
    if contact.organization:
        out["organization"] = _link(ctx, "organization", contact.organization)
    return out


def _activity(ctx: ToolContext, item: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": item.type,
        "id": str(item.id),
        "subject": item.subject,
        "body": _clip(item.body),
        "occurred": item.occurred_at.isoformat(timespec="minutes"),
        "owner": item.owner.full_name,
    }
    if item.type == "task":
        out["due"] = item.due_at.isoformat(timespec="minutes") if item.due_at else None
        out["is_done"] = item.is_done
        out["is_overdue"] = item.is_overdue
    for kind in ("lead", "opportunity", "organization", "contact"):
        link = getattr(item.links, kind)
        if link is not None:
            out[kind] = _link(ctx, kind, link)
    return out


def _page(items: list[dict[str, Any]], total: int) -> dict[str, Any]:
    return {"items": items, "total": total, "shown": len(items)}


# --- Tools ---------------------------------------------------------------------------------


async def search_leads(ctx: ToolContext, args: SearchLeads) -> dict[str, Any]:
    owners = await _owners(ctx, args.owner, args.owner_name)
    filters = sales.LeadFilters(statuses=tuple(args.status), owner_ids=owners)
    page = await sales.list_leads(
        ctx.sales(), _query("leads", args.limit, "-created_at", args.query), filters
    )
    return _page([_lead(ctx, lead) for lead in page.items], getattr(page, "total", 0))


async def search_opportunities(ctx: ToolContext, args: SearchOpportunities) -> dict[str, Any]:
    filters = sales.OpportunityFilters(
        stage_types=(args.stage_type,) if args.stage_type else (),
        owner_ids=await _owners(ctx, args.owner, args.owner_name),
        organization_ids=(args.organization_id,) if args.organization_id else (),
        close_from=args.close_from,
        close_to=args.close_to,
        closed_from=args.closed_from,
        closed_to=args.closed_to,
        is_stale=args.is_stale,
    )
    page = await sales.opportunities.list_opportunities(
        ctx.sales(), _query("opportunities", args.limit, args.sort, args.query), filters
    )
    return _page([_opportunity(ctx, o) for o in page.items], getattr(page, "total", 0))


async def search_organizations(ctx: ToolContext, args: SearchOrganizations) -> dict[str, Any]:
    filters = party.OrganizationFilters(owner_ids=await _owners(ctx, args.owner, args.owner_name))
    page = await party.list_organizations(
        ctx.party(), _query("organizations", args.limit, "name", args.query), filters
    )
    return _page([_organization(ctx, o) for o in page.items], getattr(page, "total", 0))


async def search_contacts(ctx: ToolContext, args: SearchContacts) -> dict[str, Any]:
    filters = party.ContactFilters(
        organization_ids=(args.organization_id,) if args.organization_id else (),
        owner_ids=await _owners(ctx, args.owner, args.owner_name),
    )
    page = await party.list_contacts(
        ctx.party(), _query("contacts", args.limit, "last_name", args.query), filters
    )
    return _page([_contact(ctx, c) for c in page.items], getattr(page, "total", 0))


async def get_record(ctx: ToolContext, args: GetRecord) -> dict[str, Any]:
    match args.entity_type:
        case "lead":
            return _lead(ctx, await sales.get_lead(ctx.sales(), args.id), detail=True)
        case "opportunity":
            opp = await sales.opportunities.get(ctx.sales(), args.id)
            return _opportunity(ctx, opp, detail=True)
        case "organization":
            org = await party.get_organization(ctx.party(), args.id)
            out = _organization(ctx, org, detail=True)
            # Who to talk to and what is open there, so one call answers "who is our contact
            # at …" and starts a history summary.
            contacts = await party.list_contacts(
                ctx.party(),
                _query("contacts", 10, "last_name"),
                party.ContactFilters(organization_ids=(org.id,)),
            )
            out["contacts"] = [_contact(ctx, c) for c in contacts.items]
            opportunities = await sales.opportunities.list_opportunities(
                ctx.sales(),
                _query("opportunities", 10, "-updated_at"),
                sales.OpportunityFilters(organization_ids=(org.id,)),
            )
            out["opportunities"] = [_opportunity(ctx, o) for o in opportunities.items]
            history = await activity.organization_timeline(ctx.activity(), org.id, 1, 10)
            out["latest_activities"] = [
                _activity(ctx, entry.activity) for entry in history.items if entry.activity
            ][:5]
            return out
        case "contact":
            return _contact(ctx, await party.get_contact(ctx.party(), args.id))


def _start(day: date | None) -> datetime | None:
    return None if day is None else datetime.combine(day, time.min, tzinfo=SOFIA)


def _end(day: date | None) -> datetime | None:
    return None if day is None else datetime.combine(day, time.max, tzinfo=SOFIA)


async def list_activities(ctx: ToolContext, args: ListActivities) -> dict[str, Any]:
    tasks_only = bool(
        args.assignee_name
        or args.open_tasks_only
        or args.overdue_only
        or args.due_from
        or args.due_to
    )
    narrowed = tasks_only or bool(args.owner_name or args.occurred_from or args.occurred_to)
    if (
        args.organization_id
        and not (args.lead_id or args.opportunity_id or args.contact_id)
        and not narrowed
    ):
        # The organization's whole history (its contacts, leads and deals too).
        return await _organization_history(ctx, args)
    owners = await _owners(ctx, "anyone", args.owner_name)
    assignees = await _owners(ctx, "anyone", args.assignee_name)
    due_to = _end(args.due_to)
    if args.overdue_only:
        due_to = min(due_to, ctx.now) if due_to else ctx.now
    filters = activity.ActivityFilters(
        types=("task",) if tasks_only else tuple(args.types),
        lead_ids=(args.lead_id,) if args.lead_id else (),
        opportunity_ids=(args.opportunity_id,) if args.opportunity_id else (),
        organization_ids=(args.organization_id,) if args.organization_id else (),
        contact_ids=(args.contact_id,) if args.contact_id else (),
        owner_ids=owners,
        assignee_ids=assignees,
        is_done=False if (args.open_tasks_only or args.overdue_only) else None,
        due_from=_start(args.due_from),
        due_to=due_to,
        occurred_from=_start(args.occurred_from),
        occurred_to=_end(args.occurred_to),
    )
    sort = "due_at" if tasks_only else "-occurred_at"
    page = await activity.list_activities(
        ctx.activity(), _query("activities", args.limit, sort), filters
    )
    return _page([_activity(ctx, a) for a in page.items], getattr(page, "total", 0))


async def _organization_history(ctx: ToolContext, args: ListActivities) -> dict[str, Any]:
    """An organization's timeline: its own activities and those of its contacts, leads and
    opportunities, with milestones (stage changes, wins, conversions), newest first."""
    assert args.organization_id is not None  # noqa: S101 - checked by the caller
    page = await activity.organization_timeline(
        ctx.activity(), args.organization_id, 1, min(MAX_ROWS, max(args.limit * 2, 10))
    )
    items: list[dict[str, Any]] = []
    for entry in page.items:
        if entry.activity is not None:
            if args.types and entry.activity.type not in args.types:
                continue
            items.append(_activity(ctx, entry.activity))
        elif entry.event is not None and not args.types:
            items.append(
                {
                    "event": entry.event.type,
                    "record_type": entry.event.entity_type,
                    "occurred": entry.occurred_at.isoformat(timespec="minutes"),
                    "by": entry.actor.full_name if entry.actor else None,
                }
            )
        if len(items) >= args.limit:
            break
    return _page(items, page.total)


async def pipeline_summary(ctx: ToolContext, args: PipelineSummary) -> dict[str, Any]:
    owners = await _owners(ctx, args.owner, args.owner_name)
    if args.group_by == "owner":
        rows = await sales.reports.open_pipeline_by_owner(ctx.session, owners)
        return {"currency": "EUR", "owners": rows}
    report = await reporting.pipeline_by_stage(ctx.reporting(), _scope(ctx, owners))
    return {
        "currency": report.currency,
        "stages": [
            {
                "stage": _name(ctx, row.stage),
                "count": row.count,
                "total_amount": str(row.total_amount),
                "weighted_amount": str(row.weighted_amount),
            }
            for row in report.stages
        ],
        "count": report.count,
        "total_amount": str(report.total_amount),
        "weighted_amount": str(report.weighted_amount),
    }


async def forecast_summary(ctx: ToolContext, args: ForecastSummary) -> dict[str, Any]:
    owners = await _owners(ctx, args.owner, args.owner_name)
    report = await reporting.forecast(ctx.reporting(), _scope(ctx, owners), args.months)
    return report.model_dump(mode="json")


async def win_loss_summary(ctx: ToolContext, args: WinLossSummary) -> dict[str, Any]:
    owners = await _owners(ctx, args.owner, args.owner_name)
    scope = _scope(ctx, owners, args.period_from, args.period_to)
    report = await reporting.win_loss(ctx.reporting(), scope, args.group_by)
    return report.model_dump(mode="json")


async def lead_conversion_summary(ctx: ToolContext, args: LeadConversionSummary) -> dict[str, Any]:
    owners = await _owners(ctx, args.owner, args.owner_name)
    scope = _scope(ctx, owners, args.period_from, args.period_to)
    report = await reporting.lead_conversion(ctx.reporting(), scope, args.group_by)
    return report.model_dump(mode="json")


async def my_tasks(ctx: ToolContext, args: MyTasks) -> dict[str, Any]:
    page = await activity.my_tasks(
        ctx.activity(), ctx.principal, _query("my-tasks", args.limit, "due_at"), args.include_done
    )
    return _page([_activity(ctx, a) for a in page.items], page.total)


def _status(user: Any) -> str:
    if not user.is_active:
        return "deactivated"
    return "locked" if user.is_locked else "active"


async def list_users(ctx: ToolContext, args: ListUsers) -> dict[str, Any]:
    """Admins: the user list with counts by role and status (as Admin > Users shows it).
    Others: active colleagues' names only (as the owner pickers show them)."""
    users = await identity.all_users(ctx.session, ctx.now)
    needle = (args.query or "").casefold()
    if ctx.principal.role is not RoleCode.ADMIN:
        active = [u for u in users if u.is_active]
        shown = [u for u in active if needle in u.full_name.casefold()][: args.limit]
        return {
            "active_users": len(active),
            "items": [{"name": u.full_name} for u in shown],
            "note": "Roles and account status are visible to Admins only.",
        }
    by_role: dict[str, int] = {}
    by_status: dict[str, int] = {"active": 0, "locked": 0, "deactivated": 0}
    for user in users:
        by_status[_status(user)] += 1
        if user.is_active:
            by_role[user.role.value] = by_role.get(user.role.value, 0) + 1
    matching = [
        u
        for u in users
        if (args.role is None or u.role.value == args.role)
        and (args.status == "any" or _status(u) == args.status)
        and needle in u.full_name.casefold()
    ]
    return {
        "total_users": len(users),
        "by_status": by_status,
        "active_by_role": by_role,
        "matching": len(matching),
        "items": [
            {
                "name": u.full_name,
                "role": u.role.value,
                "status": _status(u),
                "last_sign_in": _day(u.last_login_at),
            }
            for u in matching[: args.limit]
        ],
    }


async def get_settings(ctx: ToolContext, args: GetSettings) -> dict[str, Any]:
    """Admins: the values on Admin > Settings, with the AI model in use."""
    if ctx.principal.role is not RoleCode.ADMIN:
        return {"error": "not_allowed_for_role"}
    current = await runtime_settings.load(ctx.session)
    out = current.model_dump(mode="json")
    out["ai_model_label"] = models.label_of(current.ai_model)
    out["ai_models_available"] = [
        o.label for o in models.CATALOG if models.available(o, ctx.settings)
    ]
    return out


async def list_values(ctx: ToolContext, args: ListValues) -> dict[str, Any]:
    """Pipeline stages and the configurable lists, as the forms offer them."""
    inactive = args.include_inactive and ctx.principal.role is RoleCode.ADMIN
    if args.list == "pipeline-stages":
        pipelines = await sales.list_pipelines(ctx.sales())
        return {
            "stages": [
                {
                    "name": stage.name_bg if ctx.locale == "bg" else stage.name_en,
                    "stage_type": stage.stage_type,
                    "default_probability": stage.default_probability,
                    "is_active": stage.is_active,
                }
                for pipeline in pipelines
                for stage in pipeline.stages
                if inactive or stage.is_active
            ]
        }
    ref = ctx.reference_lists.get(args.list)
    if ref is None:
        return {"error": "unknown_list"}
    values = await reference.list_values(ctx.session, ref, include_inactive=inactive)
    return {
        "values": [
            {
                "name": v.name_bg if ctx.locale == "bg" else v.name_en,
                "code": v.code,
                "is_active": v.is_active,
            }
            for v in values
        ]
    }


# --- Proposal tools (FR-AI-09, ADR 0030): validate and store; never execute ------------------

DateText = Annotated[str, Field(max_length=40, description="ISO date (2026-11-23) or date-time")]
Text2000 = Annotated[str, Field(max_length=2000)]
Name200 = Annotated[str, Field(min_length=1, max_length=200)]
Money = Annotated[str, Field(max_length=20, description="Amount in EUR, e.g. '48000.00'")]
RecordType = Literal["organization", "contact", "lead", "opportunity", "activity"]


class ProposeCreateActivity(_Args):
    type: Literal["task", "note", "call", "meeting", "email"]
    subject: Name200
    body: Text2000 | None = None
    due: DateText | None = Field(
        default=None, description="Tasks: when it is due (a date means 09:00)"
    )
    occurred: DateText | None = Field(default=None, description="Notes, calls, meetings: when")
    assignee_name: OwnerName = None
    link_type: Literal["lead", "opportunity", "organization", "contact"] | None = None
    link_id: UUID | None = None


class ProposeCreateLead(_Args):
    title: Name200
    company_name: Name200
    contact_name: Name200 | None = None
    email: Annotated[str, Field(max_length=254)] | None = None
    phone: Annotated[str, Field(max_length=50)] | None = None
    source: Name200 | None = Field(default=None, description="Lead source name, e.g. 'Event'")
    estimated_value: Money | None = None
    description: Text2000 | None = None
    owner_name: OwnerName = None


class ProposeCreateOpportunity(_Args):
    name: Name200
    organization_id: UUID
    amount: Money | None = None
    expected_close_date: date | None = None
    stage: Name200 | None = Field(default=None, description="Open stage name; default the first")
    next_step: Text2000 | None = None
    description: Text2000 | None = None
    primary_contact_id: UUID | None = None
    owner_name: OwnerName = None


class ProposeCreateOrganization(_Args):
    name: Name200
    city: Annotated[str, Field(max_length=100)] | None = None
    country: Annotated[str, Field(min_length=2, max_length=2)] | None = None
    registration_number: Annotated[str, Field(max_length=13)] | None = None
    vat_number: Annotated[str, Field(max_length=12)] | None = None
    website: Annotated[str, Field(max_length=300)] | None = None
    industry: Name200 | None = None
    address_line: Name200 | None = None
    postal_code: Annotated[str, Field(max_length=20)] | None = None
    notes: Text2000 | None = None
    create_anyway: bool = Field(
        default=False, description="Only after the user accepted a duplicate"
    )


class ProposeCreateContact(_Args):
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    job_title: Annotated[str, Field(max_length=150)] | None = None
    email: Annotated[str, Field(max_length=254)] | None = None
    phone: Annotated[str, Field(max_length=50)] | None = None
    organization_id: UUID | None = None
    preferred_locale: Literal["en", "bg"] | None = None
    notes: Text2000 | None = None


class ProposeUpdate(_Args):
    entity_type: RecordType
    id: UUID
    changes: dict[str, Any] = Field(
        description="Only the fields to change. organization: name, city, country, website, "
        "registration_number, vat_number, address_line, postal_code, industry (name), notes. "
        "contact: first_name, last_name, job_title, email, phone, preferred_locale, notes, "
        "organization_id. lead: title, company_name, contact_name, email, phone, description, "
        "estimated_value, source (name), qualification {budget|authority|need|timeline: "
        "{status: unknown|no|partial|yes, note}, fits_target_profile}. opportunity: name, amount, "
        "expected_close_date, probability, next_step, description, competitor, "
        "primary_contact_id. activity: subject, body, occurred_at, due_at, assignee_name."
    )


class ProposeArchiveOrRestore(_Args):
    entity_type: RecordType
    id: UUID
    step: Literal["archive", "restore"]


class ProposeLeadStep(_Args):
    lead_id: UUID
    step: Literal["mark_contacted", "qualify", "disqualify", "reopen", "convert"]
    reason: Name200 | None = Field(default=None, description="Disqualification reason name")
    note: Text2000 | None = None


class ProposeOpportunityStep(_Args):
    opportunity_id: UUID
    step: Literal["move", "close_won", "close_lost", "reopen"]
    stage: Name200 | None = Field(default=None, description="Target open stage (move, reopen)")
    loss_reason: Name200 | None = Field(default=None, description="Required to close as lost")
    competitor: Name200 | None = None
    close_date: date | None = Field(default=None, description="Actual close date; default today")


class ProposeAssign(_Args):
    entity_type: Literal["lead", "opportunity"]
    id: UUID
    owner_name: Annotated[
        str, Field(min_length=2, max_length=100, description="New owner, or 'me'")
    ]


class ProposeTaskStep(_Args):
    activity_id: UUID
    step: Literal["complete", "reopen"]


class ProposeProfileUpdate(_Args):
    full_name: Name200 | None = None
    locale: Literal["en", "bg"] | None = None


class ProposeAdminAction(_Args):
    action: Literal[
        "user.create", "user.update", "user.deactivate", "user.activate", "user.unlock",
        "user.revoke_sessions", "settings.update", "reference.add", "reference.update",
        "reference.delete", "stage.add", "stage.update", "stage.delete",
    ]  # fmt: skip
    params: dict[str, Any] = Field(
        description="user.create: email, full_name, role (admin|sales_manager|sales_rep|viewer), "
        "locale. user.*: user (name or email), and for user.update the fields to change. "
        "settings.update: session_idle_timeout_minutes, session_absolute_timeout_minutes, "
        "stale_opportunity_days, mfa_required_for_admins, ai_model (gpt-oss-120b, "
        "nemotron-3-ultra-free, gemini-3.5-flash). reference.*: list (industries, "
        "lead-sources, disqualification-reasons, loss-reasons), value (name, for update/delete), "
        "code, name_en, name_bg, is_active. stage.*: stage (name, for update/delete), name_en, "
        "name_bg, default_probability, stage_type (open|won|lost), is_active."
    )


def _reader(ctx: ToolContext) -> actions.Reader:
    return actions.Reader(
        session=ctx.session,
        events=ctx.events,
        settings=ctx.settings,
        now=ctx.now,
        principal=ctx.principal,
        locale=ctx.locale,
        reference_lists=ctx.reference_lists,
    )


async def _store(ctx: ToolContext, proposal: actions.Proposal) -> dict[str, Any]:
    if ctx.conversation_id is None or ctx.message_id is None:
        return {"error": "not_available"}
    if len(ctx.proposed) >= actions.MAX_PROPOSALS_PER_ANSWER:
        raise actions.ActionError("too_many_proposals", limit=actions.MAX_PROPOSALS_PER_ANSWER)
    title = actions.title_of(proposal.action, proposal.request, ctx.locale)
    row = AssistantAction(
        user_id=ctx.principal.user_id,
        conversation_id=ctx.conversation_id,
        message_id=ctx.message_id,
        action=proposal.action,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_label=proposal.target_label,
        target_version=proposal.target_version,
        request=proposal.request,
        card={"title": title, "details": [{"label": k, "value": v} for k, v in proposal.details]},
        destructive=proposal.destructive,
        status="proposed",
        created_at=ctx.now,
        expires_at=ctx.now + actions.PROPOSAL_TTL,
    )
    ctx.session.add(row)
    await ctx.session.commit()
    ctx.proposed.append(row)
    summary = "; ".join(f"{k}: {v}" for k, v in proposal.details)
    return {
        "proposed": True,
        "action_id": str(row.id),
        "summary": f"{title} — {summary}",
        "note": "Nothing has changed yet: the user must confirm the card in the chat.",
    }


async def _target(ctx: ToolContext, entity_type: str, entity_id: UUID) -> actions.Target:
    return await actions.load(_reader(ctx), entity_type, entity_id)


async def propose_create_activity(ctx: ToolContext, args: ProposeCreateActivity) -> dict[str, Any]:
    link = None
    if args.link_type and args.link_id:
        link = await _target(ctx, args.link_type, args.link_id)
    elif ctx.context_type and ctx.context_id:
        link = await _target(ctx, ctx.context_type, ctx.context_id)
    proposal = await actions.propose_activity(
        _reader(ctx),
        type=args.type,
        subject=args.subject,
        body=args.body,
        due=args.due,
        occurred=args.occurred,
        assignee_name=args.assignee_name,
        link=link,
    )
    return await _store(ctx, proposal)


async def propose_create_lead(ctx: ToolContext, args: ProposeCreateLead) -> dict[str, Any]:
    fields = args.model_dump(exclude_none=True)
    return await _store(ctx, await actions.propose_lead(_reader(ctx), fields))


async def propose_create_opportunity(
    ctx: ToolContext, args: ProposeCreateOpportunity
) -> dict[str, Any]:
    org = await _target(ctx, "organization", args.organization_id)
    fields = args.model_dump(mode="json", exclude_none=True, exclude={"organization_id"})
    return await _store(ctx, await actions.propose_opportunity(_reader(ctx), fields, org))


async def propose_create_organization(
    ctx: ToolContext, args: ProposeCreateOrganization
) -> dict[str, Any]:
    fields = args.model_dump(exclude_none=True, exclude={"create_anyway"})
    proposal = await actions.propose_organization(
        _reader(ctx), fields, create_anyway=args.create_anyway
    )
    return await _store(ctx, proposal)


async def propose_create_contact(ctx: ToolContext, args: ProposeCreateContact) -> dict[str, Any]:
    org = await _target(ctx, "organization", args.organization_id) if args.organization_id else None
    fields = args.model_dump(exclude_none=True, exclude={"organization_id"})
    return await _store(ctx, await actions.propose_contact(_reader(ctx), fields, org))


async def propose_update(ctx: ToolContext, args: ProposeUpdate) -> dict[str, Any]:
    target = await _target(ctx, args.entity_type, args.id)
    return await _store(ctx, await actions.propose_update(_reader(ctx), target, args.changes))


async def propose_archive_or_restore(
    ctx: ToolContext, args: ProposeArchiveOrRestore
) -> dict[str, Any]:
    target = await _target(ctx, args.entity_type, args.id)
    return await _store(
        ctx, await actions.propose_archive_or_restore(_reader(ctx), target, args.step)
    )


async def propose_lead_step(ctx: ToolContext, args: ProposeLeadStep) -> dict[str, Any]:
    target = await _target(ctx, "lead", args.lead_id)
    proposal = await actions.propose_lead_step(
        _reader(ctx), target, args.step, reason=args.reason, note=args.note
    )
    return await _store(ctx, proposal)


async def propose_opportunity_step(
    ctx: ToolContext, args: ProposeOpportunityStep
) -> dict[str, Any]:
    target = await _target(ctx, "opportunity", args.opportunity_id)
    proposal = await actions.propose_opportunity_step(
        _reader(ctx),
        target,
        args.step,
        stage_name=args.stage,
        loss_reason=args.loss_reason,
        competitor=args.competitor,
        close_date=args.close_date.isoformat() if args.close_date else None,
    )
    return await _store(ctx, proposal)


async def propose_assign(ctx: ToolContext, args: ProposeAssign) -> dict[str, Any]:
    target = await _target(ctx, args.entity_type, args.id)
    return await _store(ctx, await actions.propose_assign(_reader(ctx), target, args.owner_name))


async def propose_task_step(ctx: ToolContext, args: ProposeTaskStep) -> dict[str, Any]:
    target = await _target(ctx, "activity", args.activity_id)
    return await _store(ctx, await actions.propose_task_step(_reader(ctx), target, args.step))


async def propose_profile_update(ctx: ToolContext, args: ProposeProfileUpdate) -> dict[str, Any]:
    proposal = await actions.propose_profile(_reader(ctx), args.full_name, args.locale)
    return await _store(ctx, proposal)


async def propose_admin_action(ctx: ToolContext, args: ProposeAdminAction) -> dict[str, Any]:
    return await _store(ctx, await actions.propose_admin(_reader(ctx), args.action, args.params))


# --- Registry ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    arguments: type[_Args]
    run: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]

    def schema(self) -> dict[str, Any]:
        """OpenAI-style function definition sent to the model."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _strip_titles(self.arguments.model_json_schema()),
            },
        }


def _strip_titles(schema: Any) -> Any:
    """Drops pydantic's `title` annotations; a field *named* title (a key of `properties`)
    stays, or `required` would name a property that is not defined (Gemini refuses that)."""
    if isinstance(schema, dict):
        return {
            k: (
                {name: _strip_titles(field) for name, field in v.items()}
                if k == "properties" and isinstance(v, dict)
                else _strip_titles(v)
            )
            for k, v in schema.items()
            if k != "title"
        }
    if isinstance(schema, list):
        return [_strip_titles(v) for v in schema]
    return schema


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            "search_leads",
            "Find leads (unqualified prospects) by words, status and owner (me, or a named "
            "colleague with owner_name). The result's total counts all matches.",
            SearchLeads,
            search_leads,
        ),
        Tool(
            "search_opportunities",
            "Find opportunities (deals) by words, stage type, owner (me, or a named colleague "
            "with owner_name), organization, expected close date range or staleness. The "
            "result's total counts all matches.",
            SearchOpportunities,
            search_opportunities,
        ),
        Tool(
            "search_organizations",
            "Find organizations (customers and prospects) by words and owner.",
            SearchOrganizations,
            search_organizations,
        ),
        Tool(
            "search_contacts",
            "Find contacts (people at customers) by name, job title or notes, by organization "
            "or by owner. Use it for 'who is our contact at …'.",
            SearchContacts,
            search_contacts,
        ),
        Tool(
            "get_record",
            "Full details of one lead, opportunity, organization or contact by its ID. An "
            "organization comes with its contacts, latest opportunities and latest activities "
            "(notes, calls, meetings, emails, tasks).",
            GetRecord,
            get_record,
        ),
        Tool(
            "list_activities",
            "Notes, calls, meetings, emails and tasks, newest first, optionally for one record. "
            "For an organization, the list covers its contacts, leads and opportunities too, "
            "with milestones such as stage changes and wins.",
            ListActivities,
            list_activities,
        ),
        Tool(
            "pipeline_summary",
            "Open pipeline: number, total and weighted value of opportunities per stage, or "
            "per owner with group_by='owner' (who has the most pipeline).",
            PipelineSummary,
            pipeline_summary,
        ),
        Tool(
            "forecast_summary",
            "Weighted forecast of open opportunities by expected close month.",
            ForecastSummary,
            forecast_summary,
        ),
        Tool(
            "win_loss_summary",
            "Won and lost opportunities in a period (default: this year): counts, amounts and "
            "win rate, optionally by loss reason, owner or month. Use it for win rate and "
            "'why do we lose deals'.",
            WinLossSummary,
            win_loss_summary,
        ),
        Tool(
            "lead_conversion_summary",
            "Leads created, qualified, converted and disqualified in a period (default: this "
            "year) and the conversion rate, optionally by source or owner.",
            LeadConversionSummary,
            lead_conversion_summary,
        ),
        Tool(
            "my_tasks",
            "The user's own tasks, overdue first.",
            MyTasks,
            my_tasks,
        ),
        Tool(
            "list_users",
            "The CRM's users. Admins get counts by status and role and each user's role, "
            "status (active, locked, deactivated) and last sign-in date; others get active "
            "colleagues' names. Use it for 'how many users', 'who are the sales reps', "
            "'which accounts are locked'.",
            ListUsers,
            list_users,
        ),
        Tool(
            "get_settings",
            "Admins: the current settings (session timeouts, stale-deal threshold, two-factor "
            "rule for Admins, the AI model in use and the models that can be chosen).",
            GetSettings,
            get_settings,
        ),
        Tool(
            "list_values",
            "The pipeline stages (with type and default probability) or a configurable list: "
            "industries, lead sources, disqualification reasons, loss reasons.",
            ListValues,
            list_values,
        ),
    )
}

_NOT_YET = " Proposes it as a card; nothing changes until the user confirms."
PROPOSAL_TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            "propose_create_activity",
            "Create a task (with due date and assignee) or log a note, call, meeting or email, "
            "optionally linked to a lead, opportunity, organization or contact." + _NOT_YET,
            ProposeCreateActivity,
            propose_create_activity,
        ),
        Tool(
            "propose_create_lead",
            "Create a lead." + _NOT_YET,
            ProposeCreateLead,
            propose_create_lead,
        ),
        Tool(
            "propose_create_opportunity",
            "Create an opportunity for an organization (find its ID first)." + _NOT_YET,
            ProposeCreateOpportunity,
            propose_create_opportunity,
        ),
        Tool(
            "propose_create_organization",
            "Create an organization; possible duplicates are reported first." + _NOT_YET,
            ProposeCreateOrganization,
            propose_create_organization,
        ),
        Tool(
            "propose_create_contact",
            "Create a contact, optionally at an organization." + _NOT_YET,
            ProposeCreateContact,
            propose_create_contact,
        ),
        Tool(
            "propose_update",
            "Change fields of an organization, contact, lead, opportunity or activity (find its "
            "ID first). Not for owner, stage or status: use the step and assign tools." + _NOT_YET,
            ProposeUpdate,
            propose_update,
        ),
        Tool(
            "propose_archive_or_restore",
            "Archive a record, or restore an archived one (managers)." + _NOT_YET,
            ProposeArchiveOrRestore,
            propose_archive_or_restore,
        ),
        Tool(
            "propose_lead_step",
            "Mark a lead contacted, qualify, disqualify (with a reason), reopen (managers) or "
            "convert it into an opportunity." + _NOT_YET,
            ProposeLeadStep,
            propose_lead_step,
        ),
        Tool(
            "propose_opportunity_step",
            "Move an opportunity to another open stage, close it as won or lost (with a loss "
            "reason), or reopen it (managers)." + _NOT_YET,
            ProposeOpportunityStep,
            propose_opportunity_step,
        ),
        Tool(
            "propose_assign",
            "Give a lead or opportunity to another owner, or take it over ('me')." + _NOT_YET,
            ProposeAssign,
            propose_assign,
        ),
        Tool(
            "propose_task_step",
            "Mark a task as done, or reopen it." + _NOT_YET,
            ProposeTaskStep,
            propose_task_step,
        ),
        Tool(
            "propose_profile_update",
            "Change the user's own display name or language." + _NOT_YET,
            ProposeProfileUpdate,
            propose_profile_update,
        ),
        Tool(
            "propose_admin_action",
            "Admins: create, edit, deactivate, activate or unlock users or sign them out "
            "everywhere; change settings; add, edit or delete list values and pipeline stages."
            + _NOT_YET,
            ProposeAdminAction,
            propose_admin_action,
        ),
    )
}
_CONTRIBUTORS = {RoleCode.ADMIN, RoleCode.SALES_MANAGER, RoleCode.SALES_REP}


def tools_for(role: RoleCode | None) -> dict[str, Tool]:
    """Reading tools for everyone; write proposals only for roles that can use them."""
    offered = dict(TOOLS)
    for name, tool in PROPOSAL_TOOLS.items():
        if name == "propose_profile_update":
            offered[name] = tool
        elif name == "propose_admin_action":
            if role is RoleCode.ADMIN:
                offered[name] = tool
        elif role in _CONTRIBUTORS:
            offered[name] = tool
    return offered


def schemas(role: RoleCode | None = None) -> list[dict[str, Any]]:
    """Without a role: the reading tools only."""
    offered = TOOLS if role is None else tools_for(role)
    return [tool.schema() for tool in offered.values()]


async def run(
    ctx: ToolContext, name: str, raw_arguments: str | Mapping[str, Any]
) -> dict[str, Any]:
    """Run one tool call from the model. Failures become a short error the model can read;
    they never raise, and never include anything but a code."""
    offered = tools_for(ctx.principal.role)
    tool = offered.get(name)
    if tool is None:
        if name in PROPOSAL_TOOLS:
            return {"error": "not_allowed_for_role"}
        return {"error": "unknown_tool", "available": list(offered)}
    try:
        args = (
            tool.arguments.model_validate_json(raw_arguments or "{}")
            if isinstance(raw_arguments, str)
            else tool.arguments.model_validate(raw_arguments)
        )
    except ValidationError as error:
        return {
            "error": "invalid_arguments",
            "fields": [".".join(str(p) for p in e["loc"]) or "arguments" for e in error.errors()],
        }
    try:
        # Tools act as the signed-in user, through the same policy as the API (FR-AI-02 AC1).
        check_access(ctx.principal, AccessLevel.SIGNED_IN)
        return await tool.run(ctx, args)
    except actions.ActionError as error:
        await ctx.session.rollback()
        return error.payload()
    except OwnerNotFoundError:
        return {"error": "owner_not_found", "hint": "No user has that name; ask who is meant."}
    except AppError as error:
        return {"error": error.code.value}
