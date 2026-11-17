"""Helpers shared by the sales services (leads, opportunities, pipelines)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus
from app.core.policy import MANAGER_ROLES
from app.core.principal import Principal
from app.modules.identity import service as identity
from app.modules.sales.schemas import ReferenceSummary, UserSummary


@dataclass(frozen=True, slots=True)
class Context:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime


def not_found() -> AppError:
    return AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)


def invalid(field: str, code: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED,
        HTTPStatus.UNPROCESSABLE_CONTENT,
        errors=[FieldError(field, code)],
    )


def use_action_endpoint(field: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_USE_ACTION_ENDPOINT,
        HTTPStatus.UNPROCESSABLE_CONTENT,
        errors=[FieldError(field, "validation.use_action_endpoint")],
    )


def version_conflict(current: Mapping[str, Any]) -> AppError:
    return AppError(
        ErrorCode.CONFLICT_VERSION_MISMATCH, HTTPStatus.CONFLICT, extra={"current": current}
    )


def reference(item: Any) -> ReferenceSummary | None:
    """Summary of a lookup value (lead source, reason, ...), or None."""
    if item is None:
        return None
    return ReferenceSummary(id=item.id, code=item.code, name_en=item.name_en, name_bg=item.name_bg)


def user(names: Mapping[UUID, str], user_id: UUID | None) -> UserSummary | None:
    return UserSummary(id=user_id, full_name=names.get(user_id, "")) if user_id else None


async def check_owner_choice(ctx: Context, principal: Principal, owner_id: UUID) -> None:
    """FR-LEAD-06 (and opportunities): Reps only themselves; Managers+ any active person."""
    if (
        owner_id != principal.user_id
        and principal.role not in MANAGER_ROLES
        and not principal.is_integration
    ):
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
    if not await identity.is_assignable_owner(ctx.session, owner_id):
        raise invalid("owner_id", "owner.invalid")


async def publish(
    ctx: Context,
    action: str,
    entity_type: str,
    entity_id: UUID,
    principal: Principal,
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    await ctx.events.publish(
        ctx.session,
        DomainEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=principal,
            occurred_at=ctx.now,
            before=before,
            after=after,
            details=details or {},
        ),
    )
