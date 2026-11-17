"""HTTP layer only: parse requests, call the service, shape responses."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.export import EXPORT_PARAMS, EXPORT_RESPONSES, ExportOptions, export_options
from app.core.listing import ListQuery, Page, SyncPage, list_query
from app.core.principal import Principal
from app.modules.party import service
from app.modules.party.schemas import (
    ContactCreate,
    ContactOut,
    ContactUpdate,
    DuplicateCheck,
    OrganizationCreate,
    OrganizationDetail,
    OrganizationOut,
    OrganizationUpdate,
    SizeBand,
)

organizations_router = APIRouter(prefix="/organizations", tags=["organizations"])
contacts_router = APIRouter(prefix="/contacts", tags=["contacts"])


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    return service.Context(
        session=session,
        events=request.app.state.event_bus,
        settings=request.app.state.settings,
        now=clock.now(),
        organization_stats=request.app.state.organization_stats,
        organization_archive_guards=request.app.state.organization_archive_guards,
    )


Ctx = Annotated[service.Context, Depends(context)]
Repeated = Annotated[list[str] | None, Query(max_length=50)]


def _owner_ids(values: list[str] | None, principal: Principal) -> tuple[UUID, ...]:
    """`owner_id` filter values: user IDs or `me` (API spec 1.3)."""
    ids: list[UUID] = []
    for value in values or []:
        if value == "me":
            ids.append(principal.user_id)
            continue
        try:
            ids.append(UUID(value))
        except ValueError as error:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                HTTPStatus.BAD_REQUEST,
                errors=[FieldError("owner_id", "validation.uuid_parsing")],
            ) from error
    return tuple(ids)


# --- Organisations (API spec section 7) -------------------------------------------------

OrganizationList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "organizations",
            sortable=tuple(service.ORGANIZATION_SORT),
            default_sort="name",
            filters=("owner_id", "industry_id", "city", "country", "size_band"),
        )
    ),
]


@organizations_router.get(
    "",
    summary="List and search organizations",
    **endpoint(AccessLevel.SIGNED_IN, scope="organizations:read"),
)
async def list_organizations(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: OrganizationList,
    owner_id: Repeated = None,
    industry_id: Annotated[list[UUID] | None, Query()] = None,
    city: Repeated = None,
    country: Repeated = None,
    size_band: Annotated[list[SizeBand] | None, Query()] = None,
) -> Page[OrganizationOut] | SyncPage[OrganizationOut]:
    filters = service.OrganizationFilters(
        owner_ids=_owner_ids(owner_id, principal),
        industry_ids=tuple(industry_id or ()),
        cities=tuple(city or ()),
        countries=tuple(country or ()),
        size_bands=tuple(size_band or ()),
    )
    return await service.list_organizations(ctx, query, filters)


@organizations_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create; 409 conflict.duplicate with matches unless confirm_duplicate",
    **endpoint(AccessLevel.CONTRIBUTOR, scope="organizations:write"),
)
async def create_organization(
    body: OrganizationCreate, ctx: Ctx, principal: CurrentPrincipal, response: Response
) -> OrganizationOut:
    created = await service.create_organization(ctx, principal, body)
    response.headers["Location"] = f"/api/v1/organizations/{created.id}"
    return created


@organizations_router.get(
    "/duplicate-check",
    summary="Possible duplicates by name and/or registration number",
    **endpoint(AccessLevel.SIGNED_IN, scope="organizations:read"),
)
async def duplicate_check(
    ctx: Ctx,
    name: Annotated[str | None, Query(max_length=200)] = None,
    registration_number: Annotated[str | None, Query(max_length=20)] = None,
) -> DuplicateCheck:
    reg = "".join((registration_number or "").split()) or None
    return await service.duplicate_check(ctx, name=name, registration_number=reg)


OrganizationExportList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "organizations-export",
            sortable=tuple(service.ORGANIZATION_SORT),
            default_sort="name",
            filters=("owner_id", "industry_id", "city", "country", "size_band", *EXPORT_PARAMS),
        )
    ),
]


@organizations_router.get(
    "/export",
    summary="Export the filtered list as XLSX or CSV",
    response_class=Response,
    responses=EXPORT_RESPONSES,
    **endpoint(AccessLevel.SIGNED_IN),
)
async def export_organizations(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: OrganizationExportList,
    options: Annotated[ExportOptions, Depends(export_options)],
    owner_id: Repeated = None,
    industry_id: Annotated[list[UUID] | None, Query()] = None,
    city: Repeated = None,
    country: Repeated = None,
    size_band: Annotated[list[SizeBand] | None, Query()] = None,
) -> Response:
    filters = service.OrganizationFilters(
        owner_ids=_owner_ids(owner_id, principal),
        industry_ids=tuple(industry_id or ()),
        cities=tuple(city or ()),
        countries=tuple(country or ()),
        size_bands=tuple(size_band or ()),
    )
    file = await service.export_organizations(ctx, principal, query, filters, options)
    return file.response()


@organizations_router.get(
    "/{org_id}",
    summary="Detail with counts of contacts, open leads, open opportunities and pipeline value",
    **endpoint(AccessLevel.SIGNED_IN, scope="organizations:read"),
)
async def get_organization(org_id: UUID, ctx: Ctx) -> OrganizationDetail:
    return await service.get_organization(ctx, org_id)


@organizations_router.patch(
    "/{org_id}",
    summary="Update fields, including owner_id (owner change requires Manager+)",
    **endpoint(AccessLevel.OWNER_PLUS, scope="organizations:write"),
)
async def update_organization(
    org_id: UUID, body: OrganizationUpdate, ctx: Ctx, principal: CurrentPrincipal
) -> OrganizationOut:
    return await service.update_organization(ctx, principal, org_id, body)


@organizations_router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive",
    **endpoint(AccessLevel.OWNER_PLUS),
)
async def archive_organization(org_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.archive_organization(ctx, principal, org_id)


@organizations_router.post(
    "/{org_id}/restore",
    summary="Restore from archive",
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def restore_organization(
    org_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> OrganizationOut:
    return await service.restore_organization(ctx, principal, org_id)


OrganizationContactList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "organization-contacts", sortable=tuple(service.CONTACT_SORT), default_sort="last_name"
        )
    ),
]


@organizations_router.get(
    "/{org_id}/contacts",
    summary="Contacts of this organization",
    **endpoint(AccessLevel.SIGNED_IN, scope="organizations:read"),
)
async def organization_contacts(
    org_id: UUID, ctx: Ctx, query: OrganizationContactList
) -> Page[ContactOut] | SyncPage[ContactOut]:
    return await service.organization_contacts(ctx, org_id, query)


# --- Contacts (API spec section 8) -----------------------------------------------------

ContactList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "contacts",
            sortable=tuple(service.CONTACT_SORT),
            default_sort="last_name",
            filters=("organization_id", "owner_id"),
        )
    ),
]


@contacts_router.get(
    "",
    summary="List and search contacts",
    **endpoint(AccessLevel.SIGNED_IN, scope="contacts:read"),
)
async def list_contacts(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: ContactList,
    organization_id: Annotated[list[UUID] | None, Query()] = None,
    owner_id: Repeated = None,
) -> Page[ContactOut] | SyncPage[ContactOut]:
    filters = service.ContactFilters(
        organization_ids=tuple(organization_id or ()), owner_ids=_owner_ids(owner_id, principal)
    )
    return await service.list_contacts(ctx, query, filters)


@contacts_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create; duplicate check on email",
    **endpoint(AccessLevel.CONTRIBUTOR, scope="contacts:write"),
)
async def create_contact(
    body: ContactCreate, ctx: Ctx, principal: CurrentPrincipal, response: Response
) -> ContactOut:
    created = await service.create_contact(ctx, principal, body)
    response.headers["Location"] = f"/api/v1/contacts/{created.id}"
    return created


ContactExportList = Annotated[
    ListQuery,
    Depends(
        list_query(
            "contacts-export",
            sortable=tuple(service.CONTACT_SORT),
            default_sort="last_name",
            filters=("organization_id", "owner_id", *EXPORT_PARAMS),
        )
    ),
]


@contacts_router.get(
    "/export",
    summary="Export the filtered list as XLSX or CSV",
    response_class=Response,
    responses=EXPORT_RESPONSES,
    **endpoint(AccessLevel.SIGNED_IN),
)
async def export_contacts(
    ctx: Ctx,
    principal: CurrentPrincipal,
    query: ContactExportList,
    options: Annotated[ExportOptions, Depends(export_options)],
    organization_id: Annotated[list[UUID] | None, Query()] = None,
    owner_id: Repeated = None,
) -> Response:
    filters = service.ContactFilters(
        organization_ids=tuple(organization_id or ()), owner_ids=_owner_ids(owner_id, principal)
    )
    file = await service.export_contacts(ctx, principal, query, filters, options)
    return file.response()


@contacts_router.get(
    "/{contact_id}", summary="Detail", **endpoint(AccessLevel.SIGNED_IN, scope="contacts:read")
)
async def get_contact(contact_id: UUID, ctx: Ctx) -> ContactOut:
    return await service.get_contact(ctx, contact_id)


@contacts_router.patch(
    "/{contact_id}", summary="Update", **endpoint(AccessLevel.OWNER_PLUS, scope="contacts:write")
)
async def update_contact(
    contact_id: UUID, body: ContactUpdate, ctx: Ctx, principal: CurrentPrincipal
) -> ContactOut:
    return await service.update_contact(ctx, principal, contact_id, body)


@contacts_router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive",
    **endpoint(AccessLevel.OWNER_PLUS),
)
async def archive_contact(contact_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.archive_contact(ctx, principal, contact_id)


@contacts_router.post(
    "/{contact_id}/restore", summary="Restore", **endpoint(AccessLevel.MANAGER_PLUS)
)
async def restore_contact(contact_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> ContactOut:
    return await service.restore_contact(ctx, principal, contact_id)


routers = [organizations_router, contacts_router]
