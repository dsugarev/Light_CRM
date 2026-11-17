"""Fixed-window rate limits stored in PostgreSQL (API spec section 18).

Counters are written in their own short transaction so they count even when the
request itself fails or rolls back.
"""

import math
from datetime import datetime, timedelta
from http import HTTPStatus

from sqlalchemy import Column, DateTime, Integer, Table, Text, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import Base
from app.core.errors import AppError, ErrorCode

rate_limit_bucket = Table(
    "rate_limit_bucket",
    Base.metadata,
    Column("key", Text, primary_key=True),
    Column("window_start", DateTime(timezone=True), primary_key=True),
    Column("hits", Integer, nullable=False),
)


def _window_start(now: datetime, window: timedelta) -> datetime:
    seconds = window.total_seconds()
    return datetime.fromtimestamp(math.floor(now.timestamp() / seconds) * seconds, tz=now.tzinfo)


async def hit(
    engine: AsyncEngine, key: str, *, limit: int, window: timedelta, now: datetime
) -> None:
    """Count one request for `key`; raise 429 with Retry-After when over `limit`."""
    start = _window_start(now, window)
    statement = (
        insert(rate_limit_bucket)
        .values(key=key, window_start=start, hits=1)
        .on_conflict_do_update(
            index_elements=["key", "window_start"],
            set_={"hits": rate_limit_bucket.c.hits + 1},
        )
        .returning(rate_limit_bucket.c.hits)
    )
    async with engine.begin() as connection:
        hits = (await connection.execute(statement)).scalar_one()
    if hits > limit:
        retry_after = max(1, math.ceil((start + window - now).total_seconds()))
        raise AppError(
            ErrorCode.RATE_LIMIT_EXCEEDED,
            HTTPStatus.TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
        )


async def purge_expired(engine: AsyncEngine, now: datetime) -> int:
    """Housekeeping: drop windows older than a day."""
    async with engine.begin() as connection:
        result = await connection.execute(
            delete(rate_limit_bucket).where(
                rate_limit_bucket.c.window_start < now - timedelta(days=1)
            )
        )
    return result.rowcount
