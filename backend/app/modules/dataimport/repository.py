"""Database queries. Called only by this module's service."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dataimport.models import ImportBatch, ImportRow


async def get_batch(
    session: AsyncSession, batch_id: UUID, *, for_update: bool = False
) -> ImportBatch | None:
    statement = select(ImportBatch).where(ImportBatch.id == batch_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


def batches_statement() -> Select[ImportBatch]:
    return select(ImportBatch)


async def rows(session: AsyncSession, batch_id: UUID) -> list[ImportRow]:
    statement = (
        select(ImportRow).where(ImportRow.batch_id == batch_id).order_by(ImportRow.row_number)
    )
    return list((await session.execute(statement)).scalars())


def rows_statement(batch_id: UUID, outcomes: Sequence[str]) -> Select[ImportRow]:
    statement = select(ImportRow).where(ImportRow.batch_id == batch_id)
    if outcomes:
        statement = statement.where(ImportRow.outcome.in_(outcomes))
    return statement


async def count(session: AsyncSession, statement: Select[ImportRow]) -> int:
    return (
        await session.execute(select(func.count()).select_from(statement.order_by(None).subquery()))
    ).scalar_one()


async def page(
    session: AsyncSession, statement: Select[ImportRow], offset: int, limit: int
) -> list[ImportRow]:
    ordered = statement.order_by(ImportRow.row_number).offset(offset).limit(limit)
    return list((await session.execute(ordered)).scalars())


async def delete_batch(session: AsyncSession, batch_id: UUID) -> None:
    await session.execute(delete(ImportBatch).where(ImportBatch.id == batch_id))


async def clear_raw(session: AsyncSession, batch_id: UUID) -> None:
    """Uploaded contents are kept only until commit (API spec 15)."""
    await session.execute(update(ImportRow).where(ImportRow.batch_id == batch_id).values(raw=None))


async def delete_expired(session: AsyncSession, now: datetime) -> int:
    """Uncommitted batches past their expiry, with their rows (housekeeping)."""
    result = await session.execute(
        delete(ImportBatch)
        .where(
            ImportBatch.expires_at < now,
            ImportBatch.status.in_(("uploaded", "mapped", "validated")),
        )
        .returning(ImportBatch.id)
    )
    return len(result.all())
