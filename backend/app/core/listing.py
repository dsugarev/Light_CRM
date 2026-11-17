"""Shared list machinery (API spec section 1.3), used by every list endpoint.

Two modes:
- page mode: `page`, `page_size` (max 100), `sort`, `q`, filters, `include_archived`;
  envelope `{items, total, page, page_size}`.
- sync mode (`updated_since`, for integrations): ordered by (updated_at, id),
  archived rows included, `sort`/`page` ignored, page size up to 500, opaque signed
  cursor; envelope `{items, next_cursor}`. Rows younger than the safety lag are held
  back so a late-committing transaction cannot slip behind a cursor (FR-INT-05).

Unknown query parameters, sort fields or a tampered cursor return 400.
"""

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated, Any
from uuid import UUID

from fastapi import Query, Request
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, and_, func, literal, or_, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.text import escape_like

PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX = 100
SYNC_PAGE_SIZE_DEFAULT = 100
SYNC_PAGE_SIZE_MAX = 500
_COMMON_PARAMS = frozenset(
    {"page", "page_size", "sort", "q", "include_archived", "updated_since", "cursor"}
)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class SyncPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class Cursor:
    updated_at: datetime
    id: UUID


@dataclass(frozen=True, slots=True)
class ListQuery:
    resource: str
    page: int
    page_size: int
    sort: tuple[tuple[str, bool], ...]  # (field, descending)
    q: str | None
    include_archived: bool
    updated_since: datetime | None
    cursor: Cursor | None

    @property
    def sync(self) -> bool:
        return self.updated_since is not None


def _bad(field: str, code: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED, HTTPStatus.BAD_REQUEST, errors=[FieldError(field, code)]
    )


# --- Cursor -----------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _signature(key: str, payload: str) -> str:
    return _b64(hmac.new(key.encode(), payload.encode(), hashlib.sha256).digest()[:16])


def encode_cursor(key: str, resource: str, cursor: Cursor) -> str:
    payload = _b64(
        json.dumps(
            {"r": resource, "u": cursor.updated_at.isoformat(), "i": str(cursor.id)},
            separators=(",", ":"),
        ).encode()
    )
    return f"{payload}.{_signature(key, payload)}"


def decode_cursor(key: str, resource: str, token: str) -> Cursor:
    """Verify and decode a cursor; a cursor from another list or altered is refused."""
    payload, _, signature = token.partition(".")
    if not signature or not hmac.compare_digest(signature, _signature(key, payload)):
        raise _bad("cursor", "validation.invalid_cursor")
    try:
        data = json.loads(_unb64(payload))
        if data["r"] != resource:
            raise ValueError("cursor for another list")
        return Cursor(updated_at=datetime.fromisoformat(data["u"]), id=UUID(data["i"]))
    except (ValueError, KeyError, TypeError) as error:
        raise _bad("cursor", "validation.invalid_cursor") from error


# --- Request parsing -----------------------------------------------------------------


def list_query(
    resource: str,
    *,
    sortable: Sequence[str],
    default_sort: str,
    filters: Sequence[str] = (),
) -> Callable[..., Any]:
    """FastAPI dependency parsing the common list parameters.

    Module-specific filters are declared on the route (so they appear in OpenAPI)
    and listed in `filters`, so that unknown parameters can be refused.
    """
    allowed = _COMMON_PARAMS | frozenset(filters)
    sortable_set = frozenset(sortable)

    async def dependency(
        request: Request,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int | None, Query(ge=1)] = None,
        sort: Annotated[
            str | None,
            Query(
                max_length=200,
                description=f"Sortable: {', '.join(sortable)}; prefix - for descending",
            ),
        ] = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        include_archived: bool = False,
        updated_since: datetime | None = None,
        cursor: Annotated[str | None, Query(max_length=1000)] = None,
    ) -> ListQuery:
        unknown = sorted(set(request.query_params) - allowed)
        if unknown:
            raise _bad(unknown[0], "validation.unknown_filter")
        settings: Settings = request.app.state.settings

        if updated_since is not None:
            if updated_since.tzinfo is None:
                updated_since = updated_since.replace(tzinfo=UTC)
            size = page_size or SYNC_PAGE_SIZE_DEFAULT
            if size > SYNC_PAGE_SIZE_MAX:
                raise _bad("page_size", "validation.less_than_equal")
            decoded = decode_cursor(settings.app_secret_key, resource, cursor) if cursor else None
            return ListQuery(resource, 1, size, (), q, True, updated_since, decoded)

        if cursor is not None:
            raise _bad("cursor", "validation.cursor_requires_updated_since")
        size = page_size or PAGE_SIZE_DEFAULT
        if size > PAGE_SIZE_MAX:
            raise _bad("page_size", "validation.less_than_equal")
        parsed: list[tuple[str, bool]] = []
        for raw in (sort or default_sort).split(","):
            name = raw.strip()
            descending = name.startswith("-")
            name = name.removeprefix("-")
            if name not in sortable_set:
                raise _bad("sort", "validation.unknown_sort")
            parsed.append((name, descending))
        return ListQuery(resource, page, size, tuple(parsed), q, include_archived, None, None)

    return dependency


# --- Query building ------------------------------------------------------------------


def search_condition(
    column: ColumnElement[str] | InstrumentedAttribute[str], variants: Sequence[Sequence[str]]
) -> ColumnElement[bool]:
    """Every term must match, each in its original or folded form (ILIKE, trigram-indexed)."""
    return and_(
        *(
            or_(*(column.ilike(f"%{escape_like(variant)}%", escape="\\") for variant in term))
            for term in variants
        )
    )


async def fetch_page[M](
    session: AsyncSession,
    statement: Select[M],
    query: ListQuery,
    sort_columns: Mapping[str, InstrumentedAttribute[Any]],
    id_column: InstrumentedAttribute[UUID],
) -> tuple[list[M], int]:
    total = (
        await session.execute(select(func.count()).select_from(statement.order_by(None).subquery()))
    ).scalar_one()
    order = [
        (sort_columns[name].desc() if descending else sort_columns[name].asc()).nulls_last()
        for name, descending in query.sort
    ]
    rows = await session.execute(
        statement.order_by(*order, id_column)
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
    )
    items: list[M] = list(rows.unique().scalars())
    return items, total


async def fetch_sync[M](
    session: AsyncSession,
    statement: Select[M],
    query: ListQuery,
    updated_at: InstrumentedAttribute[datetime],
    id_column: InstrumentedAttribute[UUID],
    *,
    safety_lag_seconds: float,
) -> tuple[list[M], Cursor | None]:
    """Rows changed at or after `updated_since`, in (updated_at, id) order."""
    assert query.updated_since is not None  # noqa: S101 - sync mode only
    statement = statement.where(
        updated_at >= query.updated_since,
        updated_at
        < func.now() - text("make_interval(secs => :lag)").bindparams(lag=safety_lag_seconds),
    )
    if query.cursor is not None:
        statement = statement.where(
            tuple_(updated_at, id_column)
            > tuple_(literal(query.cursor.updated_at), literal(query.cursor.id))
        )
    result = await session.execute(
        statement.order_by(updated_at, id_column).limit(query.page_size + 1)
    )
    rows: list[M] = list(result.unique().scalars())
    if len(rows) <= query.page_size:
        return rows, None
    rows = rows[: query.page_size]
    last = rows[-1]
    return rows, Cursor(updated_at=getattr(last, updated_at.key), id=getattr(last, id_column.key))
