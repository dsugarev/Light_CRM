"""Database queries. Called only by this module's service."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.integration.models import (
    ApiKey,
    ExternalReference,
    ExternalSystem,
    IdempotencyRecord,
    IntegrationClient,
    IntegrationUsage,
)


async def get_system_by_code(session: AsyncSession, code: str) -> ExternalSystem | None:
    statement = select(ExternalSystem).where(ExternalSystem.code == code)
    return (await session.execute(statement)).scalar_one_or_none()


async def list_clients(session: AsyncSession) -> list[IntegrationClient]:
    statement = select(IntegrationClient).order_by(IntegrationClient.name)
    return list((await session.execute(statement)).scalars())


async def get_client(
    session: AsyncSession, client_id: UUID, *, for_update: bool = False
) -> IntegrationClient | None:
    statement = select(IntegrationClient).where(IntegrationClient.id == client_id)
    if for_update:
        statement = statement.with_for_update(of=IntegrationClient)
    return (await session.execute(statement)).scalar_one_or_none()


async def get_client_by_system(session: AsyncSession, system_id: UUID) -> IntegrationClient | None:
    statement = select(IntegrationClient).where(IntegrationClient.external_system_id == system_id)
    return (await session.execute(statement)).scalars().first()


async def keys_of(session: AsyncSession, client_id: UUID) -> list[ApiKey]:
    statement = (
        select(ApiKey).where(ApiKey.client_id == client_id).order_by(ApiKey.created_at.desc())
    )
    return list((await session.execute(statement)).scalars())


async def get_key_by_key_id(session: AsyncSession, key_id: str) -> ApiKey | None:
    return (
        await session.execute(select(ApiKey).where(ApiKey.key_id == key_id))
    ).scalar_one_or_none()


async def get_key(session: AsyncSession, client_id: UUID, key_id: UUID) -> ApiKey | None:
    statement = select(ApiKey).where(ApiKey.client_id == client_id, ApiKey.id == key_id)
    return (await session.execute(statement)).scalar_one_or_none()


async def usage_since(
    session: AsyncSession, client_ids: Sequence[UUID], since: datetime
) -> dict[UUID, tuple[int, int]]:
    if not client_ids:
        return {}
    statement = (
        select(
            IntegrationUsage.client_id,
            func.sum(IntegrationUsage.requests),
            func.sum(IntegrationUsage.errors),
        )
        .where(IntegrationUsage.client_id.in_(client_ids), IntegrationUsage.hour >= since)
        .group_by(IntegrationUsage.client_id)
    )
    rows = await session.execute(statement)
    return {client: (int(r), int(e)) for client, r, e in rows.all()}


async def record_usage(engine: AsyncEngine, client_id: UUID, hour: datetime, error: bool) -> None:
    statement = (
        insert(IntegrationUsage)
        .values(client_id=client_id, hour=hour, requests=1, errors=int(error))
        .on_conflict_do_update(
            index_elements=["client_id", "hour"],
            set_={
                "requests": IntegrationUsage.requests + 1,
                "errors": IntegrationUsage.errors + int(error),
            },
        )
    )
    async with engine.begin() as connection:
        await connection.execute(statement)


# --- External references -----------------------------------------------------------------------


async def references_of(
    session: AsyncSession, entity_type: str, entity_id: UUID
) -> list[ExternalReference]:
    statement = (
        select(ExternalReference)
        .where(
            ExternalReference.entity_type == entity_type, ExternalReference.entity_id == entity_id
        )
        .order_by(ExternalReference.created_at)
    )
    return list((await session.execute(statement)).unique().scalars())


async def find_reference(
    session: AsyncSession, system_id: UUID, external_id: str, entity_type: str | None
) -> list[ExternalReference]:
    statement = select(ExternalReference).where(
        ExternalReference.external_system_id == system_id,
        ExternalReference.external_id == external_id,
    )
    if entity_type is not None:
        statement = statement.where(ExternalReference.entity_type == entity_type)
    return list((await session.execute(statement)).unique().scalars())


async def get_reference(
    session: AsyncSession, entity_type: str, entity_id: UUID, system_id: UUID
) -> ExternalReference | None:
    statement = (
        select(ExternalReference)
        .where(
            ExternalReference.entity_type == entity_type,
            ExternalReference.entity_id == entity_id,
            ExternalReference.external_system_id == system_id,
        )
        .with_for_update(of=ExternalReference)
    )
    return (await session.execute(statement)).unique().scalar_one_or_none()


async def count_with_system(session: AsyncSession, system_id: UUID) -> int:
    references = select(func.count()).where(ExternalReference.external_system_id == system_id)
    clients = select(func.count()).where(IntegrationClient.external_system_id == system_id)
    return int((await session.execute(references)).scalar_one()) + int(
        (await session.execute(clients)).scalar_one()
    )


def reference_condition(
    entity_type: str,
    id_column: ColumnElement[UUID],
    system_code: str,
    external_id: str | None,
    has_reference: bool | None,
) -> ColumnElement[bool]:
    """List filter: records with (or without) a reference in a system (API spec 19.4)."""
    linked = (
        select(ExternalReference.entity_id)
        .join(ExternalSystem, ExternalSystem.id == ExternalReference.external_system_id)
        .where(ExternalReference.entity_type == entity_type, ExternalSystem.code == system_code)
    )
    if external_id is not None:
        linked = linked.where(ExternalReference.external_id == external_id)
    condition = id_column.in_(linked)
    return ~condition if has_reference is False else condition


# --- Idempotency ---------------------------------------------------------------------------------


async def purge_idempotency(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(
        delete(IdempotencyRecord)
        .where(IdempotencyRecord.expires_at < now)
        .returning(IdempotencyRecord.id)
    )
    return len(result.all())


async def purge_usage(session: AsyncSession, before: datetime) -> int:
    result = await session.execute(
        delete(IntegrationUsage)
        .where(IntegrationUsage.hour < before)
        .returning(IntegrationUsage.hour)
    )
    return len(result.all())
