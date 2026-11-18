"""Application settings changed at runtime by an Admin (API spec section 6.1).

One row (`app_setting`, id = 1). Phase 1 holds the session timeouts
(FR-AUTH-04); later phases add their settings as new columns with defaults.
Secrets never live here; they come from the environment.
"""

import time
from datetime import datetime
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, SmallInteger, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock, get_clock
from app.core.db import Base, DbSession, TimestampMixin
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus, get_event_bus
from app.core.principal import Principal

_CACHE_SECONDS = 30.0


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_setting"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    session_idle_timeout_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="480"
    )
    session_absolute_timeout_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="10080"
    )
    # FR-OPP-06: open opportunities without activity for this many days are stale.
    stale_opportunity_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="14"
    )
    # FR-AUTH-07: Admins must use two-factor sign-in.
    mfa_required_for_admins: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_idle_timeout_minutes: int = Field(ge=15, le=1440)
    session_absolute_timeout_minutes: int = Field(ge=60, le=43200)
    stale_opportunity_days: int = Field(ge=1, le=365)
    mfa_required_for_admins: bool = False


class RuntimeSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_idle_timeout_minutes: int | None = Field(default=None, ge=15, le=1440)
    session_absolute_timeout_minutes: int | None = Field(default=None, ge=60, le=43200)
    stale_opportunity_days: int | None = Field(default=None, ge=1, le=365)
    mfa_required_for_admins: bool | None = None


class _Cache:
    value: RuntimeSettings | None = None
    loaded_at: float = 0.0


_cache = _Cache()


def invalidate_cache() -> None:
    _cache.value = None


async def load(session: AsyncSession) -> RuntimeSettings:
    """Current settings; cached briefly because every authenticated request reads them."""
    if _cache.value is not None and time.monotonic() - _cache.loaded_at < _CACHE_SECONDS:
        return _cache.value
    row = (await session.execute(select(AppSetting).where(AppSetting.id == 1))).scalar_one()
    _cache.value = RuntimeSettings.model_validate(row)
    _cache.loaded_at = time.monotonic()
    return _cache.value


async def update(
    session: AsyncSession,
    principal: Principal,
    changes: RuntimeSettingsUpdate,
    *,
    events: EventBus,
    now: datetime,
) -> RuntimeSettings:
    row = (
        await session.execute(select(AppSetting).where(AppSetting.id == 1).with_for_update())
    ).scalar_one()
    before = RuntimeSettings.model_validate(row)
    values = before.model_dump() | changes.model_dump(exclude_none=True)
    if values["session_idle_timeout_minutes"] > values["session_absolute_timeout_minutes"]:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("session_idle_timeout_minutes", "validation.exceeds_absolute")],
        )
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_by = principal.user_id
    after = RuntimeSettings.model_validate(values)
    await events.publish(
        session,
        DomainEvent(
            action="settings.updated",
            entity_type="settings",
            entity_id=None,
            actor=principal,
            occurred_at=now,
            before=before.model_dump(),
            after=after.model_dump(),
        ),
    )
    await session.commit()
    invalidate_cache()
    return after


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", summary="Configurable application values", **endpoint(AccessLevel.ADMIN))
async def get_settings(session: DbSession) -> RuntimeSettings:
    invalidate_cache()
    return await load(session)


@router.patch("", summary="Update settings; audited", **endpoint(AccessLevel.ADMIN))
async def patch_settings(
    body: RuntimeSettingsUpdate,
    session: DbSession,
    principal: CurrentPrincipal,
    events: Annotated[EventBus, Depends(get_event_bus)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> RuntimeSettings:
    return await update(session, principal, body, events=events, now=clock.now())
