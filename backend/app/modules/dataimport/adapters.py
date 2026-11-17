"""Per record type: turn mapped values into the owning module's create schema, find
duplicates, create, update, restore and archive (FR-IMP-01).

Everything goes through the public service functions of party, sales and identity,
so imported records get the same validation, ownership rules and audit entries as
records created in the UI.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.events import EventBus
from app.core.principal import Principal
from app.core.reference import ReferenceList, find_item
from app.core.text import normalize_company_name
from app.modules.dataimport.fields import EntityType
from app.modules.identity import service as identity
from app.modules.party import service as party
from app.modules.party.schemas import ContactCreate, OrganizationCreate
from app.modules.sales import service as sales
from app.modules.sales.schemas import LeadCreate, OpportunityCreate

Values = Mapping[str, str | None]
RowError = dict[str, str]
# Schema fields that come from a looked-up import column.
_FIELD_OF = {
    "industry_id": "industry",
    "owner_id": "owner",
    "organization_id": "organization",
    "stage_id": "stage",
    "source_id": "source",
}
_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")


@dataclass(frozen=True, slots=True)
class ImportContext:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime

    def party(self) -> party.Context:
        return party.Context(
            session=self.session, events=self.events, settings=self.settings, now=self.now
        )

    def sales(self) -> sales.Context:
        return sales.Context(
            session=self.session, events=self.events, settings=self.settings, now=self.now
        )


@dataclass(slots=True)
class Lookups:
    """Per-batch caches: the same organization or owner usually appears on many rows."""

    found: dict[tuple[str, str], tuple[UUID | None, str | None]] = field(default_factory=dict)


def _reference(name: str) -> ReferenceList:
    lists = {ref.name: ref for ref in (*party.REFERENCE_LISTS, *sales.REFERENCE_LISTS)}
    return lists[name]


async def _lookup(
    ctx: ImportContext, lookups: Lookups, kind: str, text: str
) -> tuple[UUID | None, str | None]:
    key = (kind, text.strip().casefold())
    if key in lookups.found:
        return lookups.found[key]
    session = ctx.session
    result: tuple[UUID | None, str | None]
    if kind == "owner":
        owner = await identity.owner_id_by_email(session, text)
        result = (owner, None if owner else "owner.invalid")
    elif kind == "organization":
        result = await party.find_organization(session, text)
    elif kind == "stage":
        stage = await sales.links.find_open_stage(session, text)
        result = (stage, None if stage else "stage.not_open")
    else:  # reference lists: industry, source
        item = await find_item(
            session, _reference("industries" if kind == "industry" else "lead-sources"), text
        )
        result = (item, None if item else "reference.invalid")
    lookups.found[key] = result
    return result


def _decimal(text: str) -> str:
    return text.replace(" ", "").replace(" ", "").replace(",", ".")


def _date(text: str) -> str:
    match = _DATE.match(text)
    return f"{match[3]}-{int(match[2]):02d}-{int(match[1]):02d}" if match else text[:10]


def _validate(
    schema: type[BaseModel], data: dict[str, Any], errors: list[RowError]
) -> BaseModel | None:
    try:
        return schema.model_validate(data)
    except ValidationError as error:
        for item in error.errors():
            name = str(item["loc"][0]) if item["loc"] else "row"
            errors.append(
                {"field": _FIELD_OF.get(name, name), "code": f"validation.{item['type']}"}
            )
        return None


@dataclass(frozen=True, slots=True)
class Prepared:
    payload: BaseModel | None
    errors: list[RowError]
    # Key for duplicates within the same file (organization name/EIK, contact email).
    file_key: str | None = None


class Adapter:
    """Defaults for a record type; subclasses fill in the specifics."""

    record: ClassVar[Literal["organization", "contact", "lead", "opportunity"]]
    schema: ClassVar[type[BaseModel]]
    lookups: ClassVar[Mapping[str, str]] = {}  # import field -> schema field by lookup
    plain: ClassVar[Mapping[str, str]] = {}  # import field -> schema field as is
    decimals: ClassVar[frozenset[str]] = frozenset()
    dates: ClassVar[frozenset[str]] = frozenset()
    updatable: ClassVar[bool] = False

    async def prepare(self, ctx: ImportContext, lookups: Lookups, values: Values) -> Prepared:
        errors: list[RowError] = []
        data: dict[str, Any] = {}
        for column, target in self.plain.items():
            text = values.get(column)
            if text:
                if column in self.decimals:
                    text = _decimal(text)
                elif column in self.dates:
                    text = _date(text)
                data[target] = text
        for column, target in self.lookups.items():
            text = values.get(column)
            if text:
                found, problem = await _lookup(ctx, lookups, column, text)
                if problem:
                    errors.append({"field": column, "code": problem})
                else:
                    data[target] = found
        payload = _validate(self.schema, self.with_defaults(data), errors)
        if errors:
            return Prepared(None, errors)
        return Prepared(payload, [], self.file_key(payload))

    def with_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        return data

    def file_key(self, payload: BaseModel | None) -> str | None:
        return None

    async def duplicate(self, ctx: ImportContext, payload: BaseModel) -> tuple[UUID, str] | None:
        return None

    async def create(
        self, ctx: ImportContext, principal: Principal, payload: BaseModel, batch_id: UUID
    ) -> UUID:
        raise NotImplementedError

    async def update(
        self, ctx: ImportContext, principal: Principal, record_id: UUID, payload: BaseModel
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def restore(
        self,
        ctx: ImportContext,
        principal: Principal,
        record_id: UUID,
        previous: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError

    async def archive(self, ctx: ImportContext, principal: Principal, record_id: UUID) -> None:
        raise NotImplementedError

    async def stamps(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, datetime]:
        raise NotImplementedError


class Organizations(Adapter):
    record = "organization"
    schema = OrganizationCreate
    lookups: ClassVar[Mapping[str, str]] = {"industry": "industry_id", "owner": "owner_id"}
    plain: ClassVar[Mapping[str, str]] = {
        k: k
        for k in ("name", "registration_number", "vat_number", "size_band", "website",
                  "address_line", "postal_code", "city", "country", "notes")
    }  # fmt: skip
    updatable = True

    def with_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        # Duplicates are decided by the import (skip or update), not refused at creation.
        return {**data, "confirm_duplicate": True}

    def file_key(self, payload: BaseModel | None) -> str | None:
        assert isinstance(payload, OrganizationCreate)  # noqa: S101
        return payload.registration_number or f"name:{normalize_company_name(payload.name)}"

    async def duplicate(self, ctx: ImportContext, payload: BaseModel) -> tuple[UUID, str] | None:
        assert isinstance(payload, OrganizationCreate)  # noqa: S101
        return await party.duplicate_organization(
            ctx.session, payload.name, payload.registration_number
        )

    async def create(
        self, ctx: ImportContext, principal: Principal, payload: BaseModel, batch_id: UUID
    ) -> UUID:
        assert isinstance(payload, OrganizationCreate)  # noqa: S101
        return await party.import_create_organization(ctx.party(), principal, payload, batch_id)

    async def update(
        self, ctx: ImportContext, principal: Principal, record_id: UUID, payload: BaseModel
    ) -> dict[str, Any]:
        changes = payload.model_dump(exclude_unset=True)
        return await party.import_update(ctx.party(), principal, "organization", record_id, changes)

    async def restore(
        self,
        ctx: ImportContext,
        principal: Principal,
        record_id: UUID,
        previous: Mapping[str, Any],
    ) -> None:
        await party.import_restore(ctx.party(), principal, "organization", record_id, previous)

    async def archive(self, ctx: ImportContext, principal: Principal, record_id: UUID) -> None:
        await party.archive_organization(ctx.party(), principal, record_id)

    async def stamps(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, datetime]:
        return await party.record_stamps(session, "organization", ids)


class Contacts(Adapter):
    record = "contact"
    schema = ContactCreate
    lookups: ClassVar[Mapping[str, str]] = {"organization": "organization_id"}
    plain: ClassVar[Mapping[str, str]] = {
        k: k for k in ("first_name", "last_name", "job_title", "email", "phone", "notes")
    }
    updatable = True

    def with_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        return {**data, "confirm_duplicate": True}

    def file_key(self, payload: BaseModel | None) -> str | None:
        assert isinstance(payload, ContactCreate)  # noqa: S101
        return f"email:{payload.email}" if payload.email else None

    async def duplicate(self, ctx: ImportContext, payload: BaseModel) -> tuple[UUID, str] | None:
        assert isinstance(payload, ContactCreate)  # noqa: S101
        return await party.duplicate_contact(ctx.session, payload.email) if payload.email else None

    async def create(
        self, ctx: ImportContext, principal: Principal, payload: BaseModel, batch_id: UUID
    ) -> UUID:
        assert isinstance(payload, ContactCreate)  # noqa: S101
        return await party.import_create_contact(ctx.party(), principal, payload, batch_id)

    async def update(
        self, ctx: ImportContext, principal: Principal, record_id: UUID, payload: BaseModel
    ) -> dict[str, Any]:
        changes = payload.model_dump(exclude_unset=True)
        return await party.import_update(ctx.party(), principal, "contact", record_id, changes)

    async def restore(
        self,
        ctx: ImportContext,
        principal: Principal,
        record_id: UUID,
        previous: Mapping[str, Any],
    ) -> None:
        await party.import_restore(ctx.party(), principal, "contact", record_id, previous)

    async def archive(self, ctx: ImportContext, principal: Principal, record_id: UUID) -> None:
        await party.archive_contact(ctx.party(), principal, record_id)

    async def stamps(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, datetime]:
        return await party.record_stamps(session, "contact", ids)


class Leads(Adapter):
    record = "lead"
    schema = LeadCreate
    lookups: ClassVar[Mapping[str, str]] = {
        "source": "source_id",
        "owner": "owner_id",
        "organization": "organization_id",
    }
    plain: ClassVar[Mapping[str, str]] = {
        k: k
        for k in ("title", "company_name", "contact_name", "email", "phone", "estimated_value",
                  "description")
    }  # fmt: skip
    decimals = frozenset({"estimated_value"})

    async def create(
        self, ctx: ImportContext, principal: Principal, payload: BaseModel, batch_id: UUID
    ) -> UUID:
        assert isinstance(payload, LeadCreate)  # noqa: S101
        return await sales.import_create_lead(ctx.sales(), principal, payload, batch_id)

    async def archive(self, ctx: ImportContext, principal: Principal, record_id: UUID) -> None:
        await sales.archive_lead(ctx.sales(), principal, record_id)

    async def stamps(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, datetime]:
        return await sales.links.record_stamps(session, "lead", ids)


class Opportunities(Adapter):
    record = "opportunity"
    schema = OpportunityCreate
    lookups: ClassVar[Mapping[str, str]] = {
        "organization": "organization_id",
        "stage": "stage_id",
        "owner": "owner_id",
    }
    plain: ClassVar[Mapping[str, str]] = {
        k: k
        for k in ("name", "amount", "probability", "expected_close_date", "next_step",
                  "competitor", "description")
    }  # fmt: skip
    decimals = frozenset({"amount"})
    dates = frozenset({"expected_close_date"})

    async def create(
        self, ctx: ImportContext, principal: Principal, payload: BaseModel, batch_id: UUID
    ) -> UUID:
        assert isinstance(payload, OpportunityCreate)  # noqa: S101
        opportunity = await sales.opportunities.create_opportunity(
            ctx.sales(), principal, payload, commit=False, import_batch_id=batch_id
        )
        return opportunity.id

    async def archive(self, ctx: ImportContext, principal: Principal, record_id: UUID) -> None:
        await sales.opportunities.archive(ctx.sales(), principal, record_id)

    async def stamps(self, session: AsyncSession, ids: set[UUID]) -> dict[UUID, datetime]:
        return await sales.links.record_stamps(session, "opportunity", ids)


ADAPTERS: Mapping[EntityType, Adapter] = {
    "organizations": Organizations(),
    "contacts": Contacts(),
    "leads": Leads(),
    "opportunities": Opportunities(),
}
