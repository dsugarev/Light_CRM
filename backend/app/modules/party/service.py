"""Organisations and contacts (FR-PARTY-01..04): rules, ownership, duplicates, search.

Public API of the module. Every change publishes a domain event (audited) and
commits here. Permission rules: Contributors create; Owner+ edit and archive
(Sales Reps only their own records); Manager+ restore and change owners.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from http import HTTPStatus
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus
from app.core.export import (
    SOFIA,
    ExportColumn,
    ExportFile,
    ExportOptions,
    build_export,
    exported_event,
    reference_name,
)
from app.core.export import Locale as ExportLocale
from app.core.external import ExternalFilter, ExternalQuery, apply_external
from app.core.listing import ListQuery, Page, SyncPage, encode_cursor, fetch_page, fetch_sync
from app.core.policy import MANAGER_ROLES, check_owner, export_owner_ids, record_owner
from app.core.principal import Principal
from app.core.reference import ReferenceList, is_active_item
from app.core.search import SearchHit, SearchProvider
from app.core.text import normalize_company_name, search_terms, search_text
from app.modules.identity import service as identity
from app.modules.party import repository
from app.modules.party.eik import is_valid_eik
from app.modules.party.models import Contact, Industry, Organization
from app.modules.party.schemas import (
    ContactCreate,
    ContactOut,
    ContactUpdate,
    DuplicateCheck,
    Match,
    OrganizationCounts,
    OrganizationCreate,
    OrganizationDetail,
    OrganizationOut,
    OrganizationSummary,
    OrganizationUpdate,
    ReferenceSummary,
    UserSummary,
)

ORGANIZATION_SORT = {
    "name": Organization.name_normalized,
    "created_at": Organization.created_at,
    "updated_at": Organization.updated_at,
}
CONTACT_SORT = {"last_name": Contact.last_name, "created_at": Contact.created_at}
# Higher modules (sales) contribute figures to the organisation 360 view through
# providers registered at start-up (ADR 0018); party never imports them.
OrganizationStats = Callable[[AsyncSession, UUID], Awaitable[Mapping[str, Any]]]
# Returns an error code when another module forbids archiving the organisation.
OrganizationArchiveGuard = Callable[[AsyncSession, UUID], Awaitable[ErrorCode | None]]


@dataclass(frozen=True, slots=True)
class DataSubject:
    """A contact as a GDPR data subject (FR-ADM-04): what other modules look for."""

    contact_id: UUID
    full_name: str
    email: str | None


@dataclass(frozen=True, slots=True)
class AnonymizeContext:
    session: AsyncSession
    events: EventBus
    now: datetime
    principal: Principal


# Other modules contribute to the GDPR export and to anonymization (ADR 0018 pattern):
# a provider returns {section: data}; an anonymizer clears what its module holds.
PersonalDataProvider = Callable[[AsyncSession, DataSubject], Awaitable[Mapping[str, Any]]]
ContactAnonymizer = Callable[[AnonymizeContext, DataSubject], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Context:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime
    organization_stats: Sequence[OrganizationStats] = ()
    external_filter: ExternalFilter | None = None
    organization_archive_guards: Sequence[OrganizationArchiveGuard] = ()
    personal_data_providers: Sequence[PersonalDataProvider] = ()
    contact_anonymizers: Sequence[ContactAnonymizer] = ()


@dataclass(frozen=True, slots=True)
class OrganizationFilters:
    owner_ids: tuple[UUID, ...] = ()
    industry_ids: tuple[UUID, ...] = ()
    cities: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    size_bands: tuple[str, ...] = ()
    external: ExternalQuery | None = None


@dataclass(frozen=True, slots=True)
class ContactFilters:
    organization_ids: tuple[UUID, ...] = ()
    owner_ids: tuple[UUID, ...] = ()
    external: ExternalQuery | None = None


# --- Shared helpers ---------------------------------------------------------------------


def _not_found() -> AppError:
    return AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)


def _invalid(field: str, code: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED,
        HTTPStatus.UNPROCESSABLE_CONTENT,
        errors=[FieldError(field, code)],
    )


async def _publish(
    ctx: Context,
    action: str,
    entity_type: str,
    entity_id: UUID,
    principal: Principal,
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> None:
    await ctx.events.publish(
        ctx.session,
        DomainEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=principal,
            occurred_at=ctx.now,
            before=before,
            after=after,
        ),
    )


async def _names(ctx: Context, *ids: UUID | None) -> dict[UUID, str]:
    return await identity.user_names(ctx.session, {i for i in ids if i is not None})


def _user(names: Mapping[UUID, str], user_id: UUID | None) -> UserSummary | None:
    if user_id is None:
        return None
    return UserSummary(id=user_id, full_name=names.get(user_id, ""))


async def _check_owner_choice(ctx: Context, principal: Principal, owner_id: UUID) -> None:
    """Owners must be active people; only Managers+ give a record to someone else."""
    if (
        owner_id != principal.user_id
        and principal.role not in MANAGER_ROLES
        and not principal.is_integration
    ):
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
    if not await identity.is_assignable_owner(ctx.session, owner_id):
        raise _invalid("owner_id", "owner.invalid")


def _ensure_not_archived(archived_at: datetime | None) -> None:
    if archived_at is not None:
        raise AppError(ErrorCode.RESOURCE_ARCHIVED, HTTPStatus.CONFLICT)


# --- Organisations ----------------------------------------------------------------------


def _org_view(org: Organization) -> dict[str, Any]:
    """Fields recorded in the audit log and compared for changes."""
    return {
        "name": org.name,
        "registration_number": org.registration_number,
        "vat_number": org.vat_number,
        "industry_id": str(org.industry_id) if org.industry_id else None,
        "size_band": org.size_band,
        "website": org.website,
        "address_line": org.address_line,
        "postal_code": org.postal_code,
        "city": org.city,
        "country": org.country,
        "owner_id": str(org.owner_id),
        "notes": org.notes,
    }


def _org_search_text(org: Organization) -> str:
    return search_text(org.name, org.registration_number, org.vat_number, org.city, org.website)


def _warnings(org: Organization) -> list[FieldError]:
    if org.registration_number and not is_valid_eik(org.registration_number):
        return [FieldError("registration_number", "organization.registration_checksum")]
    return []


def _industry(industry: Industry | None) -> ReferenceSummary | None:
    if industry is None:
        return None
    return ReferenceSummary(
        id=industry.id, code=industry.code, name_en=industry.name_en, name_bg=industry.name_bg
    )


def _org_out(org: Organization, names: Mapping[UUID, str]) -> OrganizationOut:
    owner = _user(names, org.owner_id)
    assert owner is not None  # noqa: S101 - owner_id is NOT NULL
    return OrganizationOut(
        id=org.id,
        name=org.name,
        registration_number=org.registration_number,
        vat_number=org.vat_number,
        industry=_industry(org.industry),
        size_band=org.size_band,  # type: ignore[arg-type]
        website=org.website,
        address_line=org.address_line,
        postal_code=org.postal_code,
        city=org.city,
        country=org.country,
        owner=owner,
        notes=org.notes,
        created_at=org.created_at,
        updated_at=org.updated_at,
        created_by=_user(names, org.created_by),
        archived_at=org.archived_at,
        warnings=_warnings(org),
    )


async def _orgs_out(ctx: Context, orgs: list[Organization]) -> list[OrganizationOut]:
    names = await _names(ctx, *(o.owner_id for o in orgs), *(o.created_by for o in orgs))
    return [_org_out(o, names) for o in orgs]


async def _check_industry(ctx: Context, industry_id: UUID | None) -> None:
    if industry_id is not None and not await is_active_item(ctx.session, Industry, industry_id):
        raise _invalid("industry_id", "reference.invalid")


async def _duplicates(
    ctx: Context,
    name: str | None,
    registration_number: str | None,
    exclude_id: UUID | None,
    *,
    similar: bool,
) -> list[Match]:
    found = await repository.organization_duplicates(
        ctx.session,
        name_normalized=normalize_company_name(name) if name else None,
        registration_number=registration_number,
        exclude_id=exclude_id,
        similar=similar,
    )
    return [
        Match(
            id=org.id,
            name=org.name,
            registration_number=org.registration_number,
            city=org.city,
            archived=org.archived_at is not None,
            reason=reason,  # type: ignore[arg-type]
        )
        for org, reason in found
    ]


def _duplicate_error(matches: list[Match]) -> AppError:
    return AppError(
        ErrorCode.CONFLICT_DUPLICATE,
        HTTPStatus.CONFLICT,
        extra={"matches": [m.model_dump(mode="json") for m in matches]},
    )


async def duplicate_check(
    ctx: Context, *, name: str | None, registration_number: str | None
) -> DuplicateCheck:
    """FR-PARTY-01 AC1: exact matches plus similar names, before saving."""
    return DuplicateCheck(
        matches=await _duplicates(ctx, name, registration_number, None, similar=True)
    )


async def create_organization(
    ctx: Context, principal: Principal, data: OrganizationCreate, *, commit: bool = True
) -> OrganizationOut:
    """`commit=False` lets another module create it inside its own transaction (lead conversion)."""
    owner_id = record_owner(principal, data.owner_id)
    await _check_owner_choice(ctx, principal, owner_id)
    await _check_industry(ctx, data.industry_id)
    if not data.confirm_duplicate:
        matches = await _duplicates(ctx, data.name, data.registration_number, None, similar=False)
        if matches:
            raise _duplicate_error(matches)
    values = data.model_dump(exclude={"confirm_duplicate", "owner_id"})
    org = Organization(
        **values,
        owner_id=owner_id,
        name_normalized=normalize_company_name(data.name),
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    org.search_text = _org_search_text(org)
    ctx.session.add(org)
    await ctx.session.flush()
    await _publish(
        ctx, "organization.created", "organization", org.id, principal, after=_org_view(org)
    )
    if commit:
        await ctx.session.commit()
    else:
        await ctx.session.refresh(org)
    created = await repository.get_organization(ctx.session, org.id)
    assert created is not None  # noqa: S101 - just created
    return (await _orgs_out(ctx, [created]))[0]


async def get_organization(ctx: Context, org_id: UUID) -> OrganizationDetail:
    """FR-PARTY-03: the organisation with counts for the 360 view."""
    org = await repository.get_organization(ctx.session, org_id)
    if org is None:
        raise _not_found()
    [out] = await _orgs_out(ctx, [org])
    figures: dict[str, Any] = {
        "contacts": await repository.count_contacts(ctx.session, org.id),
        "open_leads": 0,
        "open_opportunities": 0,
        "open_pipeline_value": "0.00",
    }
    for provider in ctx.organization_stats:
        figures.update(await provider(ctx.session, org.id))
    counts = OrganizationCounts(**figures)
    return OrganizationDetail(**out.model_dump(), counts=counts)


async def list_organizations(
    ctx: Context, query: ListQuery, filters: OrganizationFilters
) -> Page[OrganizationOut] | SyncPage[OrganizationOut]:
    statement = repository.organizations_statement(
        search=search_terms(query.q) if query.q else None,
        include_archived=query.include_archived,
        owner_ids=filters.owner_ids,
        industry_ids=filters.industry_ids,
        cities=filters.cities,
        countries=filters.countries,
        size_bands=filters.size_bands,
    )
    statement = apply_external(
        statement, ctx.external_filter, "organization", Organization.id, filters.external
    )
    if query.sync:
        rows, cursor = await fetch_sync(
            ctx.session, statement, query, Organization.updated_at, Organization.id,
            safety_lag_seconds=ctx.settings.sync_safety_lag_seconds,
        )  # fmt: skip
        return SyncPage[OrganizationOut](
            items=await _orgs_out(ctx, rows),
            next_cursor=encode_cursor(ctx.settings.app_secret_key, query.resource, cursor)
            if cursor
            else None,
        )
    rows, total = await fetch_page(
        ctx.session, statement, query, ORGANIZATION_SORT, Organization.id
    )
    return Page[OrganizationOut](
        items=await _orgs_out(ctx, rows), total=total, page=query.page, page_size=query.page_size
    )


async def _load_org_for_change(ctx: Context, principal: Principal, org_id: UUID) -> Organization:
    org = await repository.get_organization(ctx.session, org_id, for_update=True)
    if org is None:
        raise _not_found()
    check_owner(principal, org.owner_id)
    return org


async def update_organization(
    ctx: Context, principal: Principal, org_id: UUID, data: OrganizationUpdate
) -> OrganizationOut:
    org = await _load_org_for_change(ctx, principal, org_id)
    _ensure_not_archived(org.archived_at)
    changes = data.model_dump(exclude_unset=True, exclude={"confirm_duplicate"})
    if "name" in changes and changes["name"] is None:
        raise _invalid("name", "validation.missing")
    if "country" in changes and changes["country"] is None:
        changes["country"] = "BG"
    if "owner_id" in changes:
        new_owner = changes.pop("owner_id")
        if new_owner is not None and new_owner != org.owner_id:
            # Managers+ only; integration clients may not change owners (API spec 19.3).
            if principal.role not in MANAGER_ROLES:
                raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
            await _check_owner_choice(ctx, principal, new_owner)
            changes["owner_id"] = new_owner
    if "industry_id" in changes:
        await _check_industry(ctx, changes["industry_id"])
    identity_changed = ("name" in changes and changes["name"] != org.name) or (
        "registration_number" in changes
        and changes["registration_number"] != org.registration_number
    )
    if identity_changed and not data.confirm_duplicate:
        matches = await _duplicates(
            ctx,
            changes.get("name", org.name),
            changes.get("registration_number", org.registration_number),
            org.id,
            similar=False,
        )
        if matches:
            raise _duplicate_error(matches)

    before = _org_view(org)
    for key, value in changes.items():
        setattr(org, key, value)
    org.name_normalized = normalize_company_name(org.name)
    org.search_text = _org_search_text(org)
    org.updated_by = principal.user_id
    after = _org_view(org)
    if after != before:
        action = (
            "organization.owner_changed"
            if after["owner_id"] != before["owner_id"]
            else "organization.updated"
        )
        await _publish(ctx, action, "organization", org.id, principal, before=before, after=after)
    await ctx.session.commit()
    return await _fresh_org(ctx, org.id)


async def _fresh_org(ctx: Context, org_id: UUID) -> OrganizationOut:
    ctx.session.expire_all()
    org = await repository.get_organization(ctx.session, org_id)
    assert org is not None  # noqa: S101 - exists
    return (await _orgs_out(ctx, [org]))[0]


async def archive_organization(ctx: Context, principal: Principal, org_id: UUID) -> None:
    """Soft delete; refused while a guard objects (open opportunities, API spec 7)."""
    org = await _load_org_for_change(ctx, principal, org_id)
    if org.archived_at is None:
        for guard in ctx.organization_archive_guards:
            code = await guard(ctx.session, org.id)
            if code:
                raise AppError(code, HTTPStatus.CONFLICT)
        org.archived_at = ctx.now
        org.updated_by = principal.user_id
        await _publish(ctx, "organization.archived", "organization", org.id, principal)
    await ctx.session.commit()


async def restore_organization(ctx: Context, principal: Principal, org_id: UUID) -> OrganizationOut:
    org = await repository.get_organization(ctx.session, org_id, for_update=True)
    if org is None:
        raise _not_found()
    if org.archived_at is not None:
        org.archived_at = None
        org.updated_by = principal.user_id
        await _publish(ctx, "organization.restored", "organization", org.id, principal)
    await ctx.session.commit()
    return await _fresh_org(ctx, org.id)


async def industry_usage(session: AsyncSession, industry_id: UUID) -> int:
    return await repository.count_organizations_with_industry(session, industry_id)


REFERENCE_LISTS = (ReferenceList("industries", "industry", Industry, industry_usage),)


# --- Contacts ---------------------------------------------------------------------------


def _contact_owner_id(contact: Contact) -> UUID:
    """Ownership follows the organisation; without one, the creator (API spec section 8)."""
    if contact.organization is not None:
        return contact.organization.owner_id
    assert contact.created_by is not None  # noqa: S101 - set on create
    return contact.created_by


def _contact_view(contact: Contact) -> dict[str, Any]:
    return {
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "job_title": contact.job_title,
        "email": contact.email,
        "phone": contact.phone,
        "preferred_locale": contact.preferred_locale,
        "organization_id": str(contact.organization_id) if contact.organization_id else None,
        "notes": contact.notes,
    }


def _contact_search_text(contact: Contact) -> str:
    return search_text(
        contact.first_name, contact.last_name, contact.email, contact.phone, contact.job_title
    )


def _contact_out(contact: Contact, names: Mapping[UUID, str]) -> ContactOut:
    owner = _user(names, _contact_owner_id(contact))
    assert owner is not None  # noqa: S101 - always resolvable
    org = contact.organization
    return ContactOut(
        id=contact.id,
        first_name=contact.first_name,
        last_name=contact.last_name,
        full_name=f"{contact.first_name} {contact.last_name}",
        job_title=contact.job_title,
        email=contact.email,
        phone=contact.phone,
        preferred_locale=contact.preferred_locale,  # type: ignore[arg-type]
        organization=OrganizationSummary(id=org.id, name=org.name) if org else None,
        owner=owner,
        notes=contact.notes,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        created_by=_user(names, contact.created_by),
        archived_at=contact.archived_at,
        anonymized_at=contact.anonymized_at,
    )


async def _contacts_out(ctx: Context, contacts: list[Contact]) -> list[ContactOut]:
    names = await _names(
        ctx, *(_contact_owner_id(c) for c in contacts), *(c.created_by for c in contacts)
    )
    return [_contact_out(c, names) for c in contacts]


async def _check_contact_organization(ctx: Context, org_id: UUID | None) -> None:
    if org_id is None:
        return
    org = await repository.get_organization(ctx.session, org_id)
    if org is None:
        raise _invalid("organization_id", "organization.not_found")
    if org.archived_at is not None:
        raise _invalid("organization_id", "organization.archived")


async def _email_duplicates(ctx: Context, email: str, exclude_id: UUID | None) -> list[Match]:
    contacts = await repository.contacts_with_email(ctx.session, email, exclude_id=exclude_id)
    return [
        Match(
            id=c.id,
            name=f"{c.first_name} {c.last_name}",
            email=c.email,
            archived=c.archived_at is not None,
            reason="email",
        )
        for c in contacts
    ]


async def create_contact(
    ctx: Context, principal: Principal, data: ContactCreate, *, commit: bool = True
) -> ContactOut:
    """`commit=False` lets another module create it inside its own transaction (lead conversion)."""
    await _check_contact_organization(ctx, data.organization_id)
    if data.email and not data.confirm_duplicate:
        matches = await _email_duplicates(ctx, data.email, None)
        if matches:
            raise _duplicate_error(matches)
    contact = Contact(
        **data.model_dump(exclude={"confirm_duplicate"}),
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    contact.search_text = _contact_search_text(contact)
    ctx.session.add(contact)
    await ctx.session.flush()
    await _publish(
        ctx, "contact.created", "contact", contact.id, principal, after=_contact_view(contact)
    )
    if not commit:
        await ctx.session.refresh(contact)
        return (await _contacts_out(ctx, [contact]))[0]
    await ctx.session.commit()
    return await _fresh_contact(ctx, contact.id)


async def _fresh_contact(ctx: Context, contact_id: UUID) -> ContactOut:
    ctx.session.expire_all()
    contact = await repository.get_contact(ctx.session, contact_id)
    assert contact is not None  # noqa: S101 - exists
    return (await _contacts_out(ctx, [contact]))[0]


async def get_contact(ctx: Context, contact_id: UUID) -> ContactOut:
    contact = await repository.get_contact(ctx.session, contact_id)
    if contact is None:
        raise _not_found()
    return (await _contacts_out(ctx, [contact]))[0]


async def list_contacts(
    ctx: Context, query: ListQuery, filters: ContactFilters
) -> Page[ContactOut] | SyncPage[ContactOut]:
    statement = repository.contacts_statement(
        search=search_terms(query.q) if query.q else None,
        include_archived=query.include_archived,
        organization_ids=filters.organization_ids,
        owner_ids=filters.owner_ids,
    )
    statement = apply_external(
        statement, ctx.external_filter, "contact", Contact.id, filters.external
    )
    if query.sync:
        rows, cursor = await fetch_sync(
            ctx.session, statement, query, Contact.updated_at, Contact.id,
            safety_lag_seconds=ctx.settings.sync_safety_lag_seconds,
        )  # fmt: skip
        return SyncPage[ContactOut](
            items=await _contacts_out(ctx, rows),
            next_cursor=encode_cursor(ctx.settings.app_secret_key, query.resource, cursor)
            if cursor
            else None,
        )
    rows, total = await fetch_page(ctx.session, statement, query, CONTACT_SORT, Contact.id)
    return Page[ContactOut](
        items=await _contacts_out(ctx, rows),
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


# --- Exports (FR-REP-02, API spec 14) ---------------------------------------------------------

ORGANIZATION_EXPORT = (
    ExportColumn("name", "Name", "Име"),
    ExportColumn("registration_number", "Registration number (EIK)", "ЕИК"),
    ExportColumn("vat_number", "VAT number", "ДДС номер"),
    ExportColumn("industry", "Industry", "Отрасъл"),
    ExportColumn("size_band", "Size", "Размер"),
    ExportColumn("website", "Website", "Уебсайт"),
    ExportColumn("address_line", "Address", "Адрес"),
    ExportColumn("postal_code", "Postal code", "Пощенски код"),
    ExportColumn("city", "City", "Град"),
    ExportColumn("country", "Country", "Държава"),
    ExportColumn("owner", "Owner", "Отговорник"),
    ExportColumn("created_at", "Created", "Създадена"),
    ExportColumn("archived_at", "Archived", "Архивирана"),
    ExportColumn("id", "ID", "ID"),
)
CONTACT_EXPORT = (
    ExportColumn("first_name", "First name", "Име"),
    ExportColumn("last_name", "Last name", "Фамилия"),
    ExportColumn("job_title", "Job title", "Длъжност"),
    ExportColumn("email", "Email", "Имейл"),
    ExportColumn("phone", "Phone", "Телефон"),
    ExportColumn("organization", "Organization", "Организация"),
    ExportColumn("owner", "Owner", "Отговорник"),
    ExportColumn("created_at", "Created", "Създаден"),
    ExportColumn("archived_at", "Archived", "Архивиран"),
    ExportColumn("id", "ID", "ID"),
)


def _organization_row(org: OrganizationOut, locale: ExportLocale) -> dict[str, Any]:
    return {
        **org.model_dump(include={c.key for c in ORGANIZATION_EXPORT}),
        "industry": reference_name(org.industry, locale),
        "owner": org.owner.full_name,
    }


def _contact_row(contact: ContactOut, locale: ExportLocale) -> dict[str, Any]:
    return {
        **contact.model_dump(include={c.key for c in CONTACT_EXPORT}),
        "organization": contact.organization.name if contact.organization else None,
        "owner": contact.owner.full_name,
    }


async def _finish_export(
    ctx: Context,
    principal: Principal,
    entity_type: str,
    rows: int,
    options: ExportOptions,
    filters: Mapping[str, Any],
) -> None:
    await ctx.events.publish(
        ctx.session,
        exported_event(
            entity_type, principal, ctx.now, rows=rows, options=options, filters=filters
        ),
    )
    await ctx.session.commit()


async def export_organizations(
    ctx: Context,
    principal: Principal,
    query: ListQuery,
    filters: OrganizationFilters,
    options: ExportOptions,
) -> ExportFile:
    """FR-REP-02: the filtered organization list as XLSX or CSV."""
    filters = replace(filters, owner_ids=export_owner_ids(principal, filters.owner_ids))
    statement = repository.organizations_statement(
        search=search_terms(query.q) if query.q else None,
        include_archived=query.include_archived,
        owner_ids=filters.owner_ids,
        industry_ids=filters.industry_ids,
        cities=filters.cities,
        countries=filters.countries,
        size_bands=filters.size_bands,
    )
    statement = apply_external(
        statement, ctx.external_filter, "organization", Organization.id, filters.external
    )
    locale = options.locale or await identity.user_locale(ctx.session, principal.user_id)
    file, rows = await build_export(
        ctx.session, statement, query, ORGANIZATION_SORT, Organization.id,
        lambda batch: _orgs_out(ctx, batch), _organization_row, ORGANIZATION_EXPORT, options,
        locale, name="organizations", day=ctx.now.astimezone(SOFIA).date(),
    )  # fmt: skip
    await _finish_export(
        ctx, principal, "organization", rows, options, {**asdict(filters), "q": query.q}
    )
    return file


async def export_contacts(
    ctx: Context,
    principal: Principal,
    query: ListQuery,
    filters: ContactFilters,
    options: ExportOptions,
) -> ExportFile:
    """FR-REP-02: the filtered contact list as XLSX or CSV."""
    filters = replace(filters, owner_ids=export_owner_ids(principal, filters.owner_ids))
    statement = repository.contacts_statement(
        search=search_terms(query.q) if query.q else None,
        include_archived=query.include_archived,
        organization_ids=filters.organization_ids,
        owner_ids=filters.owner_ids,
    )
    statement = apply_external(
        statement, ctx.external_filter, "contact", Contact.id, filters.external
    )
    locale = options.locale or await identity.user_locale(ctx.session, principal.user_id)
    file, rows = await build_export(
        ctx.session, statement, query, CONTACT_SORT, Contact.id,
        lambda batch: _contacts_out(ctx, batch), _contact_row, CONTACT_EXPORT, options,
        locale, name="contacts", day=ctx.now.astimezone(SOFIA).date(),
    )  # fmt: skip
    await _finish_export(
        ctx, principal, "contact", rows, options, {**asdict(filters), "q": query.q}
    )
    return file


async def organization_contacts(
    ctx: Context, org_id: UUID, query: ListQuery
) -> Page[ContactOut] | SyncPage[ContactOut]:
    if await repository.get_organization(ctx.session, org_id) is None:
        raise _not_found()
    return await list_contacts(ctx, query, ContactFilters(organization_ids=(org_id,)))


async def _load_contact_for_change(ctx: Context, principal: Principal, contact_id: UUID) -> Contact:
    contact = await repository.get_contact(ctx.session, contact_id, for_update=True)
    if contact is None:
        raise _not_found()
    check_owner(principal, _contact_owner_id(contact))
    return contact


async def update_contact(
    ctx: Context, principal: Principal, contact_id: UUID, data: ContactUpdate
) -> ContactOut:
    contact = await _load_contact_for_change(ctx, principal, contact_id)
    _ensure_not_archived(contact.archived_at)
    _ensure_not_anonymized(contact)
    changes = data.model_dump(exclude_unset=True, exclude={"confirm_duplicate"})
    for required in ("first_name", "last_name"):
        if required in changes and changes[required] is None:
            raise _invalid(required, "validation.missing")
    if "organization_id" in changes and changes["organization_id"] != contact.organization_id:
        await _check_contact_organization(ctx, changes["organization_id"])
    new_email = changes.get("email")
    if new_email and new_email != contact.email and not data.confirm_duplicate:
        matches = await _email_duplicates(ctx, new_email, contact.id)
        if matches:
            raise _duplicate_error(matches)
    before = _contact_view(contact)
    for key, value in changes.items():
        setattr(contact, key, value)
    contact.search_text = _contact_search_text(contact)
    contact.updated_by = principal.user_id
    after = _contact_view(contact)
    if after != before:
        await _publish(
            ctx, "contact.updated", "contact", contact.id, principal, before=before, after=after
        )
    await ctx.session.commit()
    return await _fresh_contact(ctx, contact.id)


async def archive_contact(ctx: Context, principal: Principal, contact_id: UUID) -> None:
    contact = await _load_contact_for_change(ctx, principal, contact_id)
    if contact.archived_at is None:
        contact.archived_at = ctx.now
        contact.updated_by = principal.user_id
        await _publish(ctx, "contact.archived", "contact", contact.id, principal)
    await ctx.session.commit()


async def restore_contact(ctx: Context, principal: Principal, contact_id: UUID) -> ContactOut:
    contact = await repository.get_contact(ctx.session, contact_id, for_update=True)
    if contact is None:
        raise _not_found()
    if contact.archived_at is not None:
        contact.archived_at = None
        contact.updated_by = principal.user_id
        await _publish(ctx, "contact.restored", "contact", contact.id, principal)
    await ctx.session.commit()
    return await _fresh_contact(ctx, contact.id)


# --- Search providers (registered with app.core.search) --------------------------------


async def search_organizations(
    session: AsyncSession, terms: list[list[str]], limit: int
) -> list[SearchHit]:
    statement = (
        repository.organizations_statement(
            search=terms, include_archived=False, owner_ids=(), industry_ids=(),
            cities=(), countries=(), size_bands=(),
        )
        .order_by(Organization.name_normalized)
        .limit(limit)
    )  # fmt: skip
    return [
        SearchHit(type="organization", id=org.id, label=org.name, detail=org.city)
        for org in (await session.execute(statement)).unique().scalars()
    ]


async def search_contacts(
    session: AsyncSession, terms: list[list[str]], limit: int
) -> list[SearchHit]:
    statement = (
        repository.contacts_statement(
            search=terms, include_archived=False, organization_ids=(), owner_ids=()
        )
        .order_by(Contact.last_name, Contact.first_name)
        .limit(limit)
    )
    return [
        SearchHit(
            type="contact",
            id=c.id,
            label=f"{c.first_name} {c.last_name}",
            detail=c.organization.name if c.organization else c.email,
        )
        for c in (await session.execute(statement)).unique().scalars()
    ]


SEARCH_PROVIDERS = (
    SearchProvider("organization", search_organizations),
    SearchProvider("contact", search_contacts),
)


# --- For other modules -------------------------------------------------------------------


async def organization_summary(session: AsyncSession, org_id: UUID) -> OrganizationSummary | None:
    """Name of an organisation for embedding, or None if it does not exist."""
    org = await repository.get_organization(session, org_id)
    return OrganizationSummary(id=org.id, name=org.name) if org else None


async def organization_summaries(
    session: AsyncSession, org_ids: set[UUID]
) -> dict[UUID, OrganizationSummary]:
    """Names of many organisations in one query (embedded summaries, exports)."""
    return {
        org.id: OrganizationSummary(id=org.id, name=org.name)
        for org in await repository.get_organizations(session, org_ids)
    }


async def check_organization_link(session: AsyncSession, org_id: UUID) -> str | None:
    """Field code when an organisation cannot be linked to a new record, else None."""
    org = await repository.get_organization(session, org_id)
    if org is None:
        return "organization.not_found"
    if org.archived_at is not None:
        return "organization.archived"
    return None


@dataclass(frozen=True, slots=True)
class ContactLink:
    id: UUID
    full_name: str
    organization_id: UUID | None


async def contact_link(
    session: AsyncSession, contact_id: UUID, *, include_archived: bool = False
) -> ContactLink | None:
    """A contact that may be linked to a record (e.g. a lead), else None. Archived
    contacts count only with `include_archived` (for showing existing links)."""
    contact = await repository.get_contact(session, contact_id)
    if contact is None or (contact.archived_at is not None and not include_archived):
        return None
    return ContactLink(
        id=contact.id,
        full_name=f"{contact.first_name} {contact.last_name}",
        organization_id=contact.organization_id,
    )


async def contact_email_matches(ctx: Context, email: str) -> list[Match]:
    """Contacts with this email (FR-PARTY-02), e.g. to suggest them when converting a lead."""
    return await _email_duplicates(ctx, email.strip().lower(), None)


async def organization_contact_ids(session: AsyncSession, org_id: UUID) -> list[UUID]:
    """IDs of the organisation's contacts, archived included (merged timelines, FR-ACT-03)."""
    return await repository.contact_ids_of_organization(session, org_id)


async def contact_links(session: AsyncSession, contact_ids: set[UUID]) -> dict[UUID, ContactLink]:
    """Many contacts in one query, archived included (for showing existing links)."""
    return {
        c.id: ContactLink(
            id=c.id, full_name=f"{c.first_name} {c.last_name}", organization_id=c.organization_id
        )
        for c in await repository.get_contacts(session, contact_ids)
    }


# --- Import support (FR-IMP-01; used by the dataimport module) --------------------------------

ImportKind = Literal["organization", "contact"]
# Fields an import may update on an existing record (duplicates in "update" mode). The name,
# registration number and owner identify the record and are left alone.
IMPORT_UPDATABLE: dict[ImportKind, frozenset[str]] = {
    "organization": frozenset(
        {"vat_number", "industry_id", "size_band", "website", "address_line", "postal_code",
         "city", "country", "notes"}
    ),
    "contact": frozenset(
        {"job_title", "phone", "preferred_locale", "organization_id", "notes"}
    ),
}  # fmt: skip


async def import_create_organization(
    ctx: Context, principal: Principal, data: OrganizationCreate, batch_id: UUID
) -> UUID:
    """Create inside the import's transaction; duplicates were decided during validation."""
    owner_id = data.owner_id or principal.user_id
    await _check_owner_choice(ctx, principal, owner_id)
    await _check_industry(ctx, data.industry_id)
    org = Organization(
        **data.model_dump(exclude={"confirm_duplicate", "owner_id"}),
        owner_id=owner_id,
        name_normalized=normalize_company_name(data.name),
        import_batch_id=batch_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    org.search_text = _org_search_text(org)
    ctx.session.add(org)
    await ctx.session.flush()
    await _publish(
        ctx, "organization.created", "organization", org.id, principal, after=_org_view(org)
    )
    return org.id


async def import_create_contact(
    ctx: Context, principal: Principal, data: ContactCreate, batch_id: UUID
) -> UUID:
    await _check_contact_organization(ctx, data.organization_id)
    contact = Contact(
        **data.model_dump(exclude={"confirm_duplicate"}),
        import_batch_id=batch_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    contact.search_text = _contact_search_text(contact)
    ctx.session.add(contact)
    await ctx.session.flush()
    await _publish(
        ctx, "contact.created", "contact", contact.id, principal, after=_contact_view(contact)
    )
    return contact.id


async def find_organization(session: AsyncSession, text: str) -> tuple[UUID | None, str | None]:
    """An existing organisation by registration number (digits) or by name in either script.
    Returns (id, None) or (None, field code)."""
    digits = "".join(text.split())
    if digits.isdigit() and len(digits) in (9, 13):
        found = await repository.organization_duplicates(
            session, name_normalized=None, registration_number=digits, exclude_id=None,
            similar=False,
        )  # fmt: skip
    else:
        found = await repository.organization_duplicates(
            session, name_normalized=normalize_company_name(text), registration_number=None,
            exclude_id=None, similar=False,
        )  # fmt: skip
    active = [org for org, _ in found if org.archived_at is None]
    if not active:
        return None, "organization.not_found"
    if len(active) > 1:
        return None, "organization.ambiguous"
    return active[0].id, None


async def duplicate_organization(
    session: AsyncSession, name: str, registration_number: str | None
) -> tuple[UUID, str] | None:
    """The existing organisation an imported one duplicates (FR-PARTY-01 rules), if any."""
    found = await repository.organization_duplicates(
        session, name_normalized=normalize_company_name(name),
        registration_number=registration_number, exclude_id=None, similar=False,
    )  # fmt: skip
    return (found[0][0].id, found[0][0].name) if found else None


async def duplicate_contact(session: AsyncSession, email: str) -> tuple[UUID, str] | None:
    """The existing contact with this email (FR-PARTY-02 duplicate rule), if any."""
    found = await repository.contacts_with_email(session, email.lower(), exclude_id=None)
    return (found[0].id, f"{found[0].first_name} {found[0].last_name}") if found else None


def _json_value(value: Any) -> Any:
    return str(value) if isinstance(value, UUID) else value


def _db_value(key: str, value: Any) -> Any:
    return UUID(value) if key.endswith("_id") and isinstance(value, str) else value


async def _import_record(ctx: Context, kind: ImportKind, record_id: UUID) -> Organization | Contact:
    record: Organization | Contact | None = (
        await repository.get_organization(ctx.session, record_id, for_update=True)
        if kind == "organization"
        else await repository.get_contact(ctx.session, record_id, for_update=True)
    )
    if record is None:
        raise _not_found()
    return record


async def _publish_import_change(
    ctx: Context, principal: Principal, kind: ImportKind, record: Organization | Contact,
    before: Mapping[str, Any],
) -> None:  # fmt: skip
    if isinstance(record, Organization):
        record.search_text = _org_search_text(record)
        after = _org_view(record)
    else:
        record.search_text = _contact_search_text(record)
        after = _contact_view(record)
    if after != before:
        record.updated_by = principal.user_id
        await _publish(
            ctx, f"{kind}.updated", kind, record.id, principal, before=before, after=after
        )


def _view_of(record: Organization | Contact) -> dict[str, Any]:
    return _org_view(record) if isinstance(record, Organization) else _contact_view(record)


async def import_update(
    ctx: Context,
    principal: Principal,
    kind: ImportKind,
    record_id: UUID,
    changes: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the import's non-empty values to an existing record; returns the previous
    values of the fields it changed (stored for rollback)."""
    record = await _import_record(ctx, kind, record_id)
    if kind == "organization" and changes.get("industry_id") is not None:
        await _check_industry(ctx, changes["industry_id"])
    view = _view_of(record)
    previous: dict[str, Any] = {}
    for key, value in changes.items():
        if key in IMPORT_UPDATABLE[kind] and value is not None and getattr(record, key) != value:
            previous[key] = _json_value(getattr(record, key))
            setattr(record, key, value)
    await _publish_import_change(ctx, principal, kind, record, view)
    await ctx.session.flush()
    return previous


async def import_restore(
    ctx: Context,
    principal: Principal,
    kind: ImportKind,
    record_id: UUID,
    previous: Mapping[str, Any],
) -> None:
    """Rollback of an import update: put back the stored previous values."""
    record = await _import_record(ctx, kind, record_id)
    view = _view_of(record)
    for key, value in previous.items():
        setattr(record, key, _db_value(key, value))
    await _publish_import_change(ctx, principal, kind, record, view)
    await ctx.session.flush()


async def record_stamps(
    session: AsyncSession, kind: ImportKind, ids: set[UUID]
) -> dict[UUID, datetime]:
    """updated_at of many records (import rollback detects later changes with it)."""
    records: list[Organization] | list[Contact] = (
        await repository.get_organizations(session, ids)
        if kind == "organization"
        else await repository.get_contacts(session, ids)
    )
    return {r.id: r.updated_at for r in records}


# --- GDPR (FR-ADM-04) --------------------------------------------------------------------

ANONYMIZED_FIRST_NAME = "Anonymized"


def _ensure_not_anonymized(contact: Contact) -> None:
    if contact.anonymized_at is not None:
        raise AppError(ErrorCode.CONTACT_ANONYMIZED, HTTPStatus.CONFLICT)


def _subject(contact: Contact) -> DataSubject:
    return DataSubject(
        contact_id=contact.id,
        full_name=f"{contact.first_name} {contact.last_name}",
        email=contact.email,
    )


async def personal_data(ctx: Context, principal: Principal, contact_id: UUID) -> dict[str, Any]:
    """Everything the CRM holds about the contact as a person, as one JSON document.
    Sections from other modules list linked records and, for manual review, free text
    that mentions the name or email. The export itself is audited (NFR-05)."""
    contact = await repository.get_contact(ctx.session, contact_id)
    if contact is None:
        raise _not_found()
    [out] = await _contacts_out(ctx, [contact])
    sections: dict[str, Any] = {}
    subject = _subject(contact)
    for provider in ctx.personal_data_providers:
        sections.update(await provider(ctx.session, subject))
    await _publish(ctx, "contact.personal_data_exported", "contact", contact.id, principal)
    await ctx.session.commit()
    return {
        "generated_at": ctx.now.isoformat(),
        "contact": out.model_dump(mode="json"),
        **sections,
    }


async def anonymize_contact(ctx: Context, principal: Principal, contact_id: UUID) -> ContactOut:
    """Irreversibly replace the contact's personal fields, keeping the record and its
    commercial history; linked records in other modules are cleared by their anonymizers.
    The audit entry records only the result, never the old values."""
    contact = await repository.get_contact(ctx.session, contact_id, for_update=True)
    if contact is None:
        raise _not_found()
    _ensure_not_anonymized(contact)
    subject = _subject(contact)
    contact.first_name = ANONYMIZED_FIRST_NAME
    contact.last_name = f"#{contact.id.hex[-6:]}"
    contact.job_title = None
    contact.email = None
    contact.phone = None
    contact.preferred_locale = None
    contact.notes = None
    contact.anonymized_at = ctx.now
    contact.search_text = _contact_search_text(contact)
    contact.updated_by = principal.user_id
    anonymize_ctx = AnonymizeContext(ctx.session, ctx.events, ctx.now, principal)
    for anonymizer in ctx.contact_anonymizers:
        await anonymizer(anonymize_ctx, subject)
    await _publish(
        ctx, "contact.anonymized", "contact", contact.id, principal, after=_contact_view(contact)
    )
    await ctx.session.commit()
    return await _fresh_contact(ctx, contact.id)
