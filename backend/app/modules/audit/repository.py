"""Database queries. Called only by this module's service."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


def add(session: AsyncSession, entry: AuditLog) -> None:
    session.add(entry)


async def get(session: AsyncSession, entry_id: UUID) -> AuditLog | None:
    return await session.get(AuditLog, entry_id)


def search_statement(
    *,
    actor_id: UUID | None,
    entity_type: str | None,
    entity_id: UUID | None,
    actions: list[str],
    occurred_from: datetime | None,
    occurred_to: datetime | None,
) -> Select[AuditLog]:
    statement = select(AuditLog)
    if actor_id is not None:
        statement = statement.where(AuditLog.actor_id == actor_id)
    if entity_type is not None:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(AuditLog.entity_id == entity_id)
    if actions:
        statement = statement.where(AuditLog.action.in_(actions))
    if occurred_from is not None:
        statement = statement.where(AuditLog.occurred_at >= occurred_from)
    if occurred_to is not None:
        statement = statement.where(AuditLog.occurred_at <= occurred_to)
    return statement


async def search(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    entity_type: str | None,
    entity_id: UUID | None,
    actions: list[str],
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    offset: int,
    limit: int,
) -> tuple[list[AuditLog], int]:
    statement = search_statement(
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actions=actions,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )
    total = (
        await session.execute(select(func.count()).select_from(statement.subquery()))
    ).scalar_one()
    rows = await session.execute(
        statement.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(rows.scalars()), total


async def count(session: AsyncSession, statement: Select[AuditLog]) -> int:
    return (
        await session.execute(select(func.count()).select_from(statement.subquery()))
    ).scalar_one()


async def all_rows(session: AsyncSession, statement: Select[AuditLog]) -> list[AuditLog]:
    ordered = statement.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    return list((await session.execute(ordered)).scalars())
