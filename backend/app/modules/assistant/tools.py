"""The assistant's tools (architecture 8.3). All read-only (FR-AI-05).

Each tool validates its arguments against a strict schema, checks the caller's access
through the shared policy, calls the same service functions as the REST endpoints, and
returns compact JSON: only the fields an answer needs, at most 25 rows, and every
record with its type, ID and in-app URL so the answer can link to it (FR-AI-02 AC2).
There is no tool that creates, changes or deletes anything, and none that reaches
users, sessions, settings, the audit log or other people's conversations.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import AccessLevel
from app.core.config import Settings
from app.core.errors import AppError
from app.core.events import EventBus
from app.core.listing import ListQuery
from app.core.policy import check_access
from app.core.principal import Principal
from app.modules.activity import service as activity
from app.modules.identity import service as identity
from app.modules.party import service as party
from app.modules.reporting import service as reporting
from app.modules.sales import service as sales

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


async def list_activities(ctx: ToolContext, args: ListActivities) -> dict[str, Any]:
    if args.organization_id and not (args.lead_id or args.opportunity_id or args.contact_id):
        return await _organization_history(ctx, args)
    filters = activity.ActivityFilters(
        types=tuple(args.types),
        lead_ids=(args.lead_id,) if args.lead_id else (),
        opportunity_ids=(args.opportunity_id,) if args.opportunity_id else (),
        organization_ids=(args.organization_id,) if args.organization_id else (),
        contact_ids=(args.contact_id,) if args.contact_id else (),
    )
    page = await activity.list_activities(
        ctx.activity(), _query("activities", args.limit, "-occurred_at"), filters
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
    if isinstance(schema, dict):
        return {k: _strip_titles(v) for k, v in schema.items() if k != "title"}
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
    )
}


def schemas() -> list[dict[str, Any]]:
    return [tool.schema() for tool in TOOLS.values()]


async def run(
    ctx: ToolContext, name: str, raw_arguments: str | Mapping[str, Any]
) -> dict[str, Any]:
    """Run one tool call from the model. Failures become a short error the model can read;
    they never raise, and never include anything but a code."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": "unknown_tool", "available": list(TOOLS)}
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
    except OwnerNotFoundError:
        return {"error": "owner_not_found", "hint": "No user has that name; ask who is meant."}
    except AppError as error:
        return {"error": error.code.value}
