"""Leads (FR-LEAD-01..03, 05, 06): capture, lifecycle, BANT, assignment.

Public API of the module. Every change publishes a domain event (audited) and
commits here. Changes require the `version` the caller loaded (optimistic
concurrency, architecture 4.1); a stale version returns 409 with the current lead.
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
from app.core.policy import MANAGER_ROLES, check_owner
from app.core.principal import Principal
from app.core.reference import ReferenceList, is_active_item
from app.core.search import SearchHit, SearchProvider
from app.core.text import search_terms, search_text
from app.modules.identity import service as identity
from app.modules.party import service as party
from app.modules.sales import repository
from app.modules.sales.lifecycle import (
    BANT_ITEMS,
    READ_ONLY_STATUSES,
    next_status,
    qualification_score,
    unknown_bant_items,
)
from app.modules.sales.models import DisqualificationReason, Lead, LeadSource
from app.modules.sales.schemas import (
    AssignRequest,
    BantItem,
    Disqualification,
    DisqualifyRequest,
    LeadCreate,
    LeadOut,
    LeadUpdate,
    LinkSummary,
    Qualification,
    QualificationUpdate,
    ReferenceSummary,
    UserSummary,
)

LEAD_SORT = {
    "created_at": Lead.created_at,
    "estimated_value": Lead.estimated_value,
    "qualification_score": Lead.qualification_score,
    "company_name": Lead.company_name,
}


@dataclass(frozen=True, slots=True)
class Context:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime


@dataclass(frozen=True, slots=True)
class LeadFilters:
    statuses: tuple[str, ...] = ()
    owner_ids: tuple[UUID, ...] = ()
    source_ids: tuple[UUID, ...] = ()
    organization_ids: tuple[UUID, ...] = ()
    created_from: datetime | None = None
    created_to: datetime | None = None
    fits_target_profile: bool | None = None


# --- Helpers ------------------------------------------------------------------------------


def _not_found() -> AppError:
    return AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)


def _invalid(field: str, code: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED,
        HTTPStatus.UNPROCESSABLE_CONTENT,
        errors=[FieldError(field, code)],
    )


def _statuses(lead: Lead) -> dict[str, str]:
    return {item: getattr(lead, f"bant_{item}") for item in BANT_ITEMS}


def _view(lead: Lead) -> dict[str, Any]:
    """Fields recorded in the audit log and compared for changes."""
    view: dict[str, Any] = {
        "title": lead.title,
        "company_name": lead.company_name,
        "contact_name": lead.contact_name,
        "email": lead.email,
        "phone": lead.phone,
        "source_id": str(lead.source_id) if lead.source_id else None,
        "status": lead.status,
        "description": lead.description,
        "estimated_value": f"{lead.estimated_value:.2f}"
        if lead.estimated_value is not None
        else None,
        "owner_id": str(lead.owner_id),
        "fits_target_profile": lead.fits_target_profile,
        "qualification_score": lead.qualification_score,
        "organization_id": str(lead.organization_id) if lead.organization_id else None,
        "contact_id": str(lead.contact_id) if lead.contact_id else None,
        "disqualification_reason_id": str(lead.disqualification_reason_id)
        if lead.disqualification_reason_id
        else None,
        "disqualification_note": lead.disqualification_note,
    }
    for item in BANT_ITEMS:
        view[f"bant_{item}"] = getattr(lead, f"bant_{item}")
        view[f"bant_{item}_note"] = getattr(lead, f"bant_{item}_note")
    return view


async def _publish(
    ctx: Context,
    action: str,
    lead: Lead,
    principal: Principal,
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> None:
    await ctx.events.publish(
        ctx.session,
        DomainEvent(
            action=action,
            entity_type="lead",
            entity_id=lead.id,
            actor=principal,
            occurred_at=ctx.now,
            before=before,
            after=after,
        ),
    )


def _reference(item: LeadSource | DisqualificationReason | None) -> ReferenceSummary | None:
    if item is None:
        return None
    return ReferenceSummary(id=item.id, code=item.code, name_en=item.name_en, name_bg=item.name_bg)


def _user(names: Mapping[UUID, str], user_id: UUID | None) -> UserSummary | None:
    return UserSummary(id=user_id, full_name=names.get(user_id, "")) if user_id else None


async def _leads_out(ctx: Context, leads: list[Lead]) -> list[LeadOut]:
    names = await identity.user_names(
        ctx.session,
        {lead.owner_id for lead in leads} | {lead.created_by for lead in leads if lead.created_by},
    )
    org_ids = {lead.organization_id for lead in leads if lead.organization_id}
    orgs = {i: await party.organization_summary(ctx.session, i) for i in org_ids}
    contacts = {
        lead.contact_id: await party.contact_link(
            ctx.session, lead.contact_id, include_archived=True
        )
        for lead in leads
        if lead.contact_id
    }
    out: list[LeadOut] = []
    for lead in leads:
        owner = _user(names, lead.owner_id)
        assert owner is not None  # noqa: S101 - owner_id is NOT NULL
        org = orgs.get(lead.organization_id) if lead.organization_id else None
        contact = contacts.get(lead.contact_id) if lead.contact_id else None
        disqualification = (
            Disqualification(
                reason=_reference(lead.disqualification_reason),
                note=lead.disqualification_note,
                disqualified_at=lead.disqualified_at,
            )
            if lead.status == "disqualified"
            else None
        )
        out.append(
            LeadOut(
                id=lead.id,
                title=lead.title,
                company_name=lead.company_name,
                contact_name=lead.contact_name,
                email=lead.email,
                phone=lead.phone,
                source=_reference(lead.source),
                status=lead.status,  # type: ignore[arg-type]
                description=lead.description,
                estimated_value=lead.estimated_value,
                currency=lead.currency,
                owner=owner,
                qualification=Qualification(
                    **{
                        item: BantItem(
                            status=getattr(lead, f"bant_{item}"),
                            note=getattr(lead, f"bant_{item}_note") or "",
                        )
                        for item in BANT_ITEMS
                    },
                    fits_target_profile=lead.fits_target_profile,
                    score=lead.qualification_score,
                ),
                organization=LinkSummary(id=org.id, name=org.name) if org else None,
                contact=LinkSummary(id=contact.id, name=contact.full_name) if contact else None,
                # Opportunities arrive in Phase 4 (conversion).
                converted_opportunity=None,
                converted_at=lead.converted_at,
                disqualification=disqualification,
                created_at=lead.created_at,
                updated_at=lead.updated_at,
                created_by=_user(names, lead.created_by),
                archived_at=lead.archived_at,
                version=lead.version,
            )
        )
    return out


async def _fresh(ctx: Context, lead_id: UUID) -> LeadOut:
    ctx.session.expire_all()
    lead = await repository.get_lead(ctx.session, lead_id)
    assert lead is not None  # noqa: S101 - exists
    return (await _leads_out(ctx, [lead]))[0]


def _search_text(lead: Lead) -> str:
    return search_text(lead.title, lead.company_name, lead.contact_name, lead.email, lead.phone)


def _apply_qualification(lead: Lead, update: QualificationUpdate | None) -> None:
    if update is None:
        return
    for item in BANT_ITEMS:
        change = getattr(update, item)
        if change is None:
            continue
        if change.status is not None:
            setattr(lead, f"bant_{item}", change.status)
        if "note" in change.model_fields_set:
            setattr(lead, f"bant_{item}_note", change.note or None)
    if update.fits_target_profile is not None:
        lead.fits_target_profile = update.fits_target_profile
    lead.qualification_score = qualification_score(_statuses(lead))


async def _check_links(ctx: Context, org_id: UUID | None, contact_id: UUID | None) -> None:
    """Optional links to an existing organisation and contact (owner decision, Phase 3)."""
    if org_id is not None:
        problem = await party.check_organization_link(ctx.session, org_id)
        if problem:
            raise _invalid("organization_id", problem)
    if contact_id is not None:
        contact = await party.contact_link(ctx.session, contact_id)
        if contact is None:
            raise _invalid("contact_id", "contact.not_found")
        if org_id is not None and contact.organization_id not in (None, org_id):
            raise _invalid("contact_id", "contact.organization_mismatch")


async def _check_source(ctx: Context, source_id: UUID | None) -> None:
    if source_id is not None and not await is_active_item(ctx.session, LeadSource, source_id):
        raise _invalid("source_id", "reference.invalid")


async def _check_owner_choice(ctx: Context, principal: Principal, owner_id: UUID) -> None:
    """FR-LEAD-06: Sales Reps assign only to themselves; Managers+ to anyone active."""
    if (
        owner_id != principal.user_id
        and principal.role not in MANAGER_ROLES
        and not principal.is_integration
    ):
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
    if not await identity.is_assignable_owner(ctx.session, owner_id):
        raise _invalid("owner_id", "owner.invalid")


async def _load(ctx: Context, lead_id: UUID) -> Lead:
    lead = await repository.get_lead(ctx.session, lead_id, for_update=True)
    if lead is None:
        raise _not_found()
    return lead


async def _check_version(ctx: Context, lead: Lead, version: int) -> None:
    if lead.version != version:
        current = (await _leads_out(ctx, [lead]))[0]
        raise AppError(
            ErrorCode.CONFLICT_VERSION_MISMATCH,
            HTTPStatus.CONFLICT,
            extra={"current": current.model_dump(mode="json")},
        )


def _ensure_editable(lead: Lead) -> None:
    if lead.archived_at is not None:
        raise AppError(ErrorCode.RESOURCE_ARCHIVED, HTTPStatus.CONFLICT)
    if lead.status in READ_ONLY_STATUSES:
        raise AppError(ErrorCode.LEAD_READ_ONLY, HTTPStatus.CONFLICT)


async def _commit_change(
    ctx: Context, principal: Principal, lead: Lead, action: str, before: Mapping[str, Any]
) -> LeadOut:
    lead.search_text = _search_text(lead)
    lead.updated_by = principal.user_id
    after = _view(lead)
    if after != before:
        lead.version += 1
        await _publish(ctx, action, lead, principal, before=before, after=after)
    await ctx.session.commit()
    return await _fresh(ctx, lead.id)


# --- Capture and read ---------------------------------------------------------------------


async def create_lead(ctx: Context, principal: Principal, data: LeadCreate) -> LeadOut:
    """FR-LEAD-01: company name alone is enough; status starts as `new`."""
    owner_id = data.owner_id or principal.user_id
    await _check_owner_choice(ctx, principal, owner_id)
    await _check_source(ctx, data.source_id)
    await _check_links(ctx, data.organization_id, data.contact_id)
    lead = Lead(
        **data.model_dump(exclude={"owner_id", "qualification"}),
        owner_id=owner_id,
        status="new",
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    for item in BANT_ITEMS:
        setattr(lead, f"bant_{item}", "unknown")
    lead.fits_target_profile = False
    _apply_qualification(lead, data.qualification)
    lead.search_text = _search_text(lead)
    ctx.session.add(lead)
    await ctx.session.flush()
    await _publish(ctx, "lead.created", lead, principal, after=_view(lead))
    await ctx.session.commit()
    return await _fresh(ctx, lead.id)


async def get_lead(ctx: Context, lead_id: UUID) -> LeadOut:
    lead = await repository.get_lead(ctx.session, lead_id)
    if lead is None:
        raise _not_found()
    return (await _leads_out(ctx, [lead]))[0]


async def list_leads(
    ctx: Context, query: ListQuery, filters: LeadFilters
) -> Page[LeadOut] | SyncPage[LeadOut]:
    """FR-LEAD-05."""
    statement = repository.leads_statement(
        search=search_terms(query.q) if query.q else None,
        include_archived=query.include_archived,
        statuses=filters.statuses,
        owner_ids=filters.owner_ids,
        source_ids=filters.source_ids,
        organization_ids=filters.organization_ids,
        created_from=filters.created_from,
        created_to=filters.created_to,
        fits_target_profile=filters.fits_target_profile,
    )
    if query.sync:
        rows, cursor = await fetch_sync(
            ctx.session, statement, query, Lead.updated_at, Lead.id,
            safety_lag_seconds=ctx.settings.sync_safety_lag_seconds,
        )  # fmt: skip
        return SyncPage[LeadOut](
            items=await _leads_out(ctx, rows),
            next_cursor=encode_cursor(ctx.settings.app_secret_key, query.resource, cursor)
            if cursor
            else None,
        )
    rows, total = await fetch_page(ctx.session, statement, query, LEAD_SORT, Lead.id)
    return Page[LeadOut](
        items=await _leads_out(ctx, rows), total=total, page=query.page, page_size=query.page_size
    )


# --- Update and lifecycle -----------------------------------------------------------------


async def update_lead(
    ctx: Context, principal: Principal, lead_id: UUID, data: LeadUpdate
) -> LeadOut:
    """FR-LEAD-01, 03: fields and BANT; status and owner only through actions."""
    for field in ("status", "owner_id"):
        if field in data.model_fields_set:
            raise AppError(
                ErrorCode.VALIDATION_USE_ACTION_ENDPOINT,
                HTTPStatus.UNPROCESSABLE_CONTENT,
                errors=[FieldError(field, "validation.use_action_endpoint")],
            )
    lead = await _load(ctx, lead_id)
    check_owner(principal, lead.owner_id)
    await _check_version(ctx, lead, data.version)
    _ensure_editable(lead)
    changes = data.model_dump(
        exclude_unset=True, exclude={"version", "status", "owner_id", "qualification"}
    )
    for required in ("title", "company_name"):
        if required in changes and changes[required] is None:
            raise _invalid(required, "validation.missing")
    if "source_id" in changes and changes["source_id"] != lead.source_id:
        await _check_source(ctx, changes["source_id"])
    org_id = changes.get("organization_id", lead.organization_id)
    contact_id = changes.get("contact_id", lead.contact_id)
    if "organization_id" in changes or "contact_id" in changes:
        await _check_links(ctx, org_id, contact_id)
    before = _view(lead)
    for key, value in changes.items():
        setattr(lead, key, value)
    _apply_qualification(lead, data.qualification)
    return await _commit_change(ctx, principal, lead, "lead.updated", before)


async def _transition(
    ctx: Context,
    principal: Principal,
    lead_id: UUID,
    action: str,
    version: int,
    *,
    owner_check: bool = True,
) -> tuple[Lead, dict[str, Any]]:
    lead = await _load(ctx, lead_id)
    if owner_check:
        check_owner(principal, lead.owner_id)
    await _check_version(ctx, lead, version)
    if lead.archived_at is not None:
        raise AppError(ErrorCode.RESOURCE_ARCHIVED, HTTPStatus.CONFLICT)
    target = next_status(action, lead.status)
    if target is None:
        raise AppError(
            ErrorCode.LEAD_INVALID_TRANSITION,
            HTTPStatus.CONFLICT,
            extra={"status": lead.status, "action": action},
        )
    before = _view(lead)
    lead.status = target
    return lead, before


async def mark_contacted(
    ctx: Context, principal: Principal, lead_id: UUID, version: int
) -> LeadOut:
    lead, before = await _transition(ctx, principal, lead_id, "mark_contacted", version)
    return await _commit_change(ctx, principal, lead, "lead.status_changed", before)


async def qualify(ctx: Context, principal: Principal, lead_id: UUID, version: int) -> LeadOut:
    """FR-LEAD-03 AC1: all four BANT items must be other than unknown."""
    lead = await _load(ctx, lead_id)
    check_owner(principal, lead.owner_id)
    await _check_version(ctx, lead, version)
    if lead.status == "contacted":
        missing = unknown_bant_items(_statuses(lead))
        if missing:
            raise AppError(
                ErrorCode.LEAD_BANT_INCOMPLETE,
                HTTPStatus.CONFLICT,
                errors=[
                    FieldError(f"qualification.{item}", "lead.bant_unknown") for item in missing
                ],
            )
    lead, before = await _transition(ctx, principal, lead_id, "qualify", version)
    return await _commit_change(ctx, principal, lead, "lead.status_changed", before)


async def disqualify(
    ctx: Context, principal: Principal, lead_id: UUID, data: DisqualifyRequest
) -> LeadOut:
    """FR-LEAD-02 AC1: needs a reason from the configurable list."""
    if not await is_active_item(ctx.session, DisqualificationReason, data.reason_id):
        raise _invalid("reason_id", "reference.invalid")
    lead, before = await _transition(ctx, principal, lead_id, "disqualify", data.version)
    lead.disqualification_reason_id = data.reason_id
    lead.disqualification_note = data.note or None
    lead.disqualified_at = ctx.now
    return await _commit_change(ctx, principal, lead, "lead.status_changed", before)


async def reopen(ctx: Context, principal: Principal, lead_id: UUID, version: int) -> LeadOut:
    """FR-LEAD-02 AC2: Managers and Admins reopen a disqualified lead (route is Manager+)."""
    lead, before = await _transition(ctx, principal, lead_id, "reopen", version, owner_check=False)
    lead.disqualification_reason_id = None
    lead.disqualification_note = None
    lead.disqualified_at = None
    return await _commit_change(ctx, principal, lead, "lead.status_changed", before)


async def assign(ctx: Context, principal: Principal, lead_id: UUID, data: AssignRequest) -> LeadOut:
    """FR-LEAD-06: Reps take leads for themselves; Managers+ assign to anyone. Audited."""
    lead = await _load(ctx, lead_id)
    await _check_version(ctx, lead, data.version)
    _ensure_editable(lead)
    await _check_owner_choice(ctx, principal, data.owner_id)
    before = _view(lead)
    lead.owner_id = data.owner_id
    return await _commit_change(ctx, principal, lead, "lead.owner_changed", before)


async def archive_lead(ctx: Context, principal: Principal, lead_id: UUID) -> None:
    lead = await _load(ctx, lead_id)
    check_owner(principal, lead.owner_id)
    if lead.archived_at is None:
        lead.archived_at = ctx.now
        lead.updated_by = principal.user_id
        lead.version += 1
        await _publish(ctx, "lead.archived", lead, principal)
    await ctx.session.commit()


async def restore_lead(ctx: Context, principal: Principal, lead_id: UUID) -> LeadOut:
    lead = await _load(ctx, lead_id)
    if lead.archived_at is not None:
        lead.archived_at = None
        lead.updated_by = principal.user_id
        lead.version += 1
        await _publish(ctx, "lead.restored", lead, principal)
    await ctx.session.commit()
    return await _fresh(ctx, lead.id)


# --- Contributions to other modules (registered in app.main, ADR 0018) --------------------


async def organization_lead_stats(session: AsyncSession, organization_id: UUID) -> dict[str, Any]:
    return {"open_leads": await repository.count_open_leads(session, organization_id)}


async def search_leads(
    session: AsyncSession, terms: list[list[str]], limit: int
) -> list[SearchHit]:
    statement = (
        repository.leads_statement(
            search=terms, include_archived=False, statuses=(), owner_ids=(), source_ids=(),
            organization_ids=(), created_from=None, created_to=None, fits_target_profile=None,
        )
        .order_by(Lead.created_at.desc())
        .limit(limit)
    )  # fmt: skip
    return [
        SearchHit(type="lead", id=lead.id, label=lead.title, detail=lead.company_name)
        for lead in (await session.execute(statement)).unique().scalars()
    ]


async def _source_usage(session: AsyncSession, item_id: UUID) -> int:
    return await repository.count_with_source(session, item_id)


async def _reason_usage(session: AsyncSession, item_id: UUID) -> int:
    return await repository.count_with_disqualification_reason(session, item_id)


REFERENCE_LISTS = (
    ReferenceList("lead-sources", "lead_source", LeadSource, _source_usage),
    ReferenceList(
        "disqualification-reasons", "disqualification_reason", DisqualificationReason, _reason_usage
    ),
)
SEARCH_PROVIDERS = (SearchProvider("lead", search_leads),)
