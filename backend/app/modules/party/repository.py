"""Database queries. Called only by this module's service."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listing import search_condition
from app.modules.party.models import Contact, Industry, Organization

# --- Organizations -----------------------------------------------------------------------


async def get_organization(
    session: AsyncSession, org_id: UUID, *, for_update: bool = False
) -> Organization | None:
    statement = select(Organization).where(Organization.id == org_id)
    if for_update:
        statement = statement.with_for_update(of=Organization)
    return (await session.execute(statement)).unique().scalar_one_or_none()


def organizations_statement(
    *,
    search: Sequence[Sequence[str]] | None,
    include_archived: bool,
    owner_ids: Sequence[UUID],
    industry_ids: Sequence[UUID],
    cities: Sequence[str],
    countries: Sequence[str],
    size_bands: Sequence[str],
) -> Select[Organization]:
    statement = select(Organization)
    if not include_archived:
        statement = statement.where(Organization.archived_at.is_(None))
    if search:
        statement = statement.where(search_condition(Organization.search_text, search))
    if owner_ids:
        statement = statement.where(Organization.owner_id.in_(owner_ids))
    if industry_ids:
        statement = statement.where(Organization.industry_id.in_(industry_ids))
    if cities:
        statement = statement.where(func.lower(Organization.city).in_([c.lower() for c in cities]))
    if countries:
        statement = statement.where(Organization.country.in_([c.upper() for c in countries]))
    if size_bands:
        statement = statement.where(Organization.size_band.in_(size_bands))
    return statement


async def organization_duplicates(
    session: AsyncSession,
    *,
    name_normalized: str | None,
    registration_number: str | None,
    exclude_id: UUID | None,
    similar: bool,
    limit: int = 10,
) -> list[tuple[Organization, str]]:
    """Organisations sharing the registration number or the name key, and optionally
    names similar by trigram (pg_trgm), with the reason for each match."""
    found: dict[UUID, tuple[Organization, str]] = {}

    async def collect(condition: object, reason: str) -> None:
        statement = select(Organization).where(condition)  # type: ignore[arg-type]
        if exclude_id is not None:
            statement = statement.where(Organization.id != exclude_id)
        for org in (await session.execute(statement.limit(limit))).unique().scalars():
            found.setdefault(org.id, (org, reason))

    if registration_number:
        await collect(
            Organization.registration_number == registration_number, "registration_number"
        )
    if name_normalized:
        await collect(Organization.name_normalized == name_normalized, "name")
        if similar:
            similarity = func.similarity(Organization.name_normalized, literal(name_normalized))
            statement = (
                select(Organization)
                .where(Organization.name_normalized.op("%")(name_normalized))
                .order_by(similarity.desc())
            )
            if exclude_id is not None:
                statement = statement.where(Organization.id != exclude_id)
            for org in (await session.execute(statement.limit(limit))).unique().scalars():
                found.setdefault(org.id, (org, "similar_name"))
    return list(found.values())[:limit]


async def count_contacts(session: AsyncSession, org_id: UUID) -> int:
    statement = select(func.count()).where(
        Contact.organization_id == org_id, Contact.archived_at.is_(None)
    )
    return (await session.execute(statement)).scalar_one()


async def count_organizations_with_industry(session: AsyncSession, industry_id: UUID) -> int:
    statement = select(func.count()).where(Organization.industry_id == industry_id)
    return (await session.execute(statement)).scalar_one()


# --- Contacts ---------------------------------------------------------------------------


def contact_owner_condition(owner_ids: Sequence[UUID]) -> object:
    """Contacts owned by these users: through their organisation, else as creator."""
    return or_(
        Contact.organization.has(Organization.owner_id.in_(owner_ids)),
        and_(Contact.organization_id.is_(None), Contact.created_by.in_(owner_ids)),
    )


async def get_contact(
    session: AsyncSession, contact_id: UUID, *, for_update: bool = False
) -> Contact | None:
    statement = select(Contact).where(Contact.id == contact_id)
    if for_update:
        statement = statement.with_for_update(of=Contact)
    return (await session.execute(statement)).unique().scalar_one_or_none()


def contacts_statement(
    *,
    search: Sequence[Sequence[str]] | None,
    include_archived: bool,
    organization_ids: Sequence[UUID],
    owner_ids: Sequence[UUID],
) -> Select[Contact]:
    statement = select(Contact)
    if not include_archived:
        statement = statement.where(Contact.archived_at.is_(None))
    if search:
        statement = statement.where(search_condition(Contact.search_text, search))
    if organization_ids:
        statement = statement.where(Contact.organization_id.in_(organization_ids))
    if owner_ids:
        statement = statement.where(contact_owner_condition(owner_ids))  # type: ignore[arg-type]
    return statement


async def contacts_with_email(
    session: AsyncSession, email: str, *, exclude_id: UUID | None
) -> list[Contact]:
    statement = select(Contact).where(func.lower(Contact.email) == email.lower())
    if exclude_id is not None:
        statement = statement.where(Contact.id != exclude_id)
    return list((await session.execute(statement.limit(10))).unique().scalars())


async def contact_ids_of_organization(session: AsyncSession, org_id: UUID) -> list[UUID]:
    statement = select(Contact.id).where(Contact.organization_id == org_id)
    return list((await session.execute(statement)).scalars())


# --- Industries -------------------------------------------------------------------------


async def get_industry(session: AsyncSession, industry_id: UUID) -> Industry | None:
    return await session.get(Industry, industry_id)
