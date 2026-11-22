"""Configurable reference lists (API spec section 6.2, FR-ADM-02).

One uniform set of endpoints serves every list: `/reference/{list}`. Each module
owns its lookup tables (lookup tables, not database enums; architecture 4.1) and
registers them here at start-up (app.main), together with a function that counts
uses of a value, so a value in use is deactivated instead of deleted.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Integer, String, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock, get_clock
from app.core.db import DbSession
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus, get_event_bus
from app.core.principal import Principal

CODE_PATTERN = r"^[a-z0-9_]{1,50}$"


class ReferenceItemMixin:
    """Columns of every lookup table: stable code, names in both languages, order."""

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_bg: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


UsageCounter = Callable[[AsyncSession, UUID], Awaitable[int]]


@dataclass(frozen=True, slots=True)
class ReferenceList:
    name: str  # URL segment, e.g. "industries"
    entity_type: str  # audit entity type, e.g. "industry"
    model: type[Any]  # SQLAlchemy model with ReferenceItemMixin and an `id`
    usage: UsageCounter


class ReferenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name_en: str
    name_bg: str
    position: int
    is_active: bool


class ReferenceItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(pattern=CODE_PATTERN)
    name_en: str = Field(min_length=1, max_length=200)
    name_bg: str = Field(min_length=1, max_length=200)
    is_active: bool = True


class ReferenceItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name_en: str | None = Field(default=None, min_length=1, max_length=200)
    name_bg: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


def _registry(request: Request) -> Mapping[str, ReferenceList]:
    registry: Mapping[str, ReferenceList] = request.app.state.reference_lists
    return registry


def _resolve(request: Request, name: str) -> ReferenceList:
    found = _registry(request).get(name)
    if found is None:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)
    return found


def _view(item: Any) -> dict[str, Any]:
    return ReferenceItem.model_validate(item).model_dump(mode="json", exclude={"id"})


async def _items(session: AsyncSession, ref: ReferenceList, *, include_inactive: bool) -> list[Any]:
    statement = select(ref.model).order_by(ref.model.position, ref.model.name_en)
    if not include_inactive:
        statement = statement.where(ref.model.is_active.is_(True))
    return list((await session.execute(statement)).scalars())


async def list_values(
    session: AsyncSession, ref: ReferenceList, *, include_inactive: bool = False
) -> list[ReferenceItem]:
    """A list's values in order, as GET /reference/{list} returns them (the assistant
    reads them too)."""
    items = await _items(session, ref, include_inactive=include_inactive)
    return [ReferenceItem.model_validate(i) for i in items]


async def _get(session: AsyncSession, ref: ReferenceList, item_id: UUID) -> Any:
    item = await session.get(ref.model, item_id, with_for_update=True)
    if item is None:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)
    return item


async def _publish(
    session: AsyncSession,
    events: EventBus,
    ref: ReferenceList,
    action: str,
    principal: Principal,
    now: datetime,
    entity_id: UUID | None,
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> None:
    await events.publish(
        session,
        DomainEvent(
            action=f"reference.{action}",
            entity_type=ref.entity_type,
            entity_id=entity_id,
            actor=principal,
            occurred_at=now,
            before=before,
            after=after,
            details={"list": ref.name},
        ),
    )


async def is_active_item(session: AsyncSession, model: type[Any], item_id: UUID) -> bool:
    """For modules validating a reference: the value exists and is active."""
    item = await session.get(model, item_id)
    return item is not None and bool(item.is_active)


# --- Endpoints ------------------------------------------------------------------------

router = APIRouter(prefix="/reference", tags=["reference"])
ListName = Annotated[str, Path(alias="list", max_length=64)]
Events = Annotated[EventBus, Depends(get_event_bus)]
Now = Annotated[Clock, Depends(get_clock)]


async def add_value(
    session: AsyncSession,
    events: EventBus,
    now: datetime,
    principal: Principal,
    ref: ReferenceList,
    body: ReferenceItemCreate,
) -> ReferenceItem:
    """Add a value at the end of the list (also used by assistant actions, ADR 0030)."""
    existing = (
        await session.execute(select(ref.model).where(ref.model.code == body.code))
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            ErrorCode.CONFLICT_DUPLICATE,
            HTTPStatus.CONFLICT,
            errors=[FieldError("code", "reference.code_taken")],
        )
    position = (
        await session.execute(select(func.coalesce(func.max(ref.model.position), 0)))
    ).scalar_one()
    item = ref.model(**body.model_dump(), position=position + 1)
    session.add(item)
    await session.flush()
    await _publish(session, events, ref, "created", principal, now, item.id, after=_view(item))
    await session.commit()
    await session.refresh(item)
    return ReferenceItem.model_validate(item)


async def change_value(
    session: AsyncSession,
    events: EventBus,
    now: datetime,
    principal: Principal,
    ref: ReferenceList,
    item_id: UUID,
    body: ReferenceItemUpdate,
) -> ReferenceItem:
    """Rename, activate or deactivate a value."""
    item = await _get(session, ref, item_id)
    before = _view(item)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(item, key, value)
    after = _view(item)
    if after != before:
        await _publish(
            session, events, ref, "updated", principal, now, item.id, before=before, after=after
        )
    await session.commit()
    await session.refresh(item)
    return ReferenceItem.model_validate(item)


async def remove_value(
    session: AsyncSession,
    events: EventBus,
    now: datetime,
    principal: Principal,
    ref: ReferenceList,
    item_id: UUID,
) -> None:
    """Delete a value that was never used; one in use is `409 reference.in_use`."""
    item = await _get(session, ref, item_id)
    if await ref.usage(session, item_id) > 0:
        raise AppError(ErrorCode.REFERENCE_IN_USE, HTTPStatus.CONFLICT)
    before = _view(item)
    await session.delete(item)
    await _publish(session, events, ref, "deleted", principal, now, item_id, before=before)
    await session.commit()


async def all_items(session: AsyncSession, ref: ReferenceList) -> list[ReferenceItem]:
    """Every value, active or not, in list order."""
    return [
        ReferenceItem.model_validate(i) for i in await _items(session, ref, include_inactive=True)
    ]


async def find_item(session: AsyncSession, ref: ReferenceList, text: str) -> UUID | None:
    """An active value of the list by code, English or Bulgarian name (case-insensitive),
    for imports (FR-IMP-01)."""
    wanted = text.strip().casefold()
    for item in await _items(session, ref, include_inactive=False):
        if wanted in (item.code.casefold(), item.name_en.casefold(), item.name_bg.casefold()):
            found: UUID = item.id
            return found
    return None


@router.get(
    "/{list}",
    summary="List values; include_inactive=true for administration",
    **endpoint(AccessLevel.SIGNED_IN, scope="reference:read"),
)
async def list_items(
    request: Request, session: DbSession, list_name: ListName, include_inactive: bool = False
) -> list[ReferenceItem]:
    ref = _resolve(request, list_name)
    items = await _items(session, ref, include_inactive=include_inactive)
    return [ReferenceItem.model_validate(i) for i in items]


@router.post(
    "/{list}",
    status_code=status.HTTP_201_CREATED,
    summary="Add a value",
    **endpoint(AccessLevel.ADMIN),
)
async def create_item(
    request: Request,
    response: Response,
    session: DbSession,
    principal: CurrentPrincipal,
    events: Events,
    clock: Now,
    list_name: ListName,
    body: ReferenceItemCreate,
) -> ReferenceItem:
    ref = _resolve(request, list_name)
    item = await add_value(session, events, clock.now(), principal, ref, body)
    response.headers["Location"] = f"/api/v1/reference/{ref.name}/{item.id}"
    return ReferenceItem.model_validate(item)


@router.patch(
    "/{list}/{item_id}", summary="Rename, activate, deactivate", **endpoint(AccessLevel.ADMIN)
)
async def update_item(
    request: Request,
    session: DbSession,
    principal: CurrentPrincipal,
    events: Events,
    clock: Now,
    list_name: ListName,
    item_id: UUID,
    body: ReferenceItemUpdate,
) -> ReferenceItem:
    ref = _resolve(request, list_name)
    return await change_value(session, events, clock.now(), principal, ref, item_id, body)


@router.put(
    "/{list}/order",
    summary="Reorder; body is the full ordered list of IDs",
    **endpoint(AccessLevel.ADMIN),
)
async def reorder_items(
    request: Request,
    session: DbSession,
    principal: CurrentPrincipal,
    events: Events,
    clock: Now,
    list_name: ListName,
    body: Annotated[list[UUID], Body(max_length=1000)],
) -> list[ReferenceItem]:
    ref = _resolve(request, list_name)
    items = {i.id: i for i in await _items(session, ref, include_inactive=True)}
    if len(body) != len(set(body)) or set(body) != set(items):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("body", "reference.order_incomplete")],
        )
    before = [str(i.id) for i in sorted(items.values(), key=lambda i: i.position)]
    for position, item_id in enumerate(body, start=1):
        items[item_id].position = position
    await _publish(
        session, events, ref, "reordered", principal, clock.now(), None,
        before={"order": before}, after={"order": [str(i) for i in body]},
    )  # fmt: skip
    await session.commit()
    return [
        ReferenceItem.model_validate(i) for i in await _items(session, ref, include_inactive=True)
    ]


@router.delete(
    "/{list}/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete only if never used; otherwise 409 reference.in_use",
    **endpoint(AccessLevel.ADMIN),
)
async def delete_item(
    request: Request,
    session: DbSession,
    principal: CurrentPrincipal,
    events: Events,
    clock: Now,
    list_name: ListName,
    item_id: UUID,
) -> None:
    ref = _resolve(request, list_name)
    await remove_value(session, events, clock.now(), principal, ref, item_id)
