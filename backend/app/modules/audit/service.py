"""Audit log (FR-ADM-03): records every domain event; Admins browse it.

`record` is subscribed to the event bus in app.main, so every change, sign-in
and failed sign-in published by any module is written in the same transaction.
"""

from collections.abc import Mapping
from datetime import datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.core.events import DomainEvent, EventBus
from app.core.export import (
    SOFIA,
    ExportColumn,
    ExportFile,
    ExportOptions,
    check_row_count,
    exported_event,
    render,
    select_columns,
)
from app.core.logging import client_ip_var, request_id_var
from app.core.principal import Principal
from app.modules.audit import repository
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditActor, AuditEntry, AuditEntrySummary, AuditPage
from app.modules.identity import service as identity

# Defence in depth: these keys are dropped wherever they appear in a payload.
_SECRET_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "new_password",
        "current_password",
        "token",
        "token_hash",
        "secret",
        "secret_hash",
        "mfa_secret",
        "api_key",
    }
)


def _scrub(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _scrub(v) for k, v in value.items() if k not in _SECRET_KEYS}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _payload(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return None if value is None else _scrub(dict(value))


async def record(session: AsyncSession, event: DomainEvent) -> None:
    actor = event.actor
    repository.add(
        session,
        AuditLog(
            occurred_at=event.occurred_at,
            actor_id=actor.user_id if actor else None,
            actor_type=actor.type.value if actor else "anonymous",
            actor_label=actor.display_name if actor else None,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            before=_payload(event.before),
            after=_payload(event.after),
            details=_payload(event.details) or None,
            ip=client_ip_var.get(),
            request_id=request_id_var.get(),
        ),
    )


def _actor(entry: AuditLog) -> AuditActor:
    return AuditActor(type=entry.actor_type, id=entry.actor_id, name=entry.actor_label)  # type: ignore[arg-type]


def _summary(entry: AuditLog) -> AuditEntrySummary:
    return AuditEntrySummary(
        id=entry.id,
        occurred_at=entry.occurred_at,
        actor=_actor(entry),
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        ip=entry.ip,
    )


async def search(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    entity_type: str | None,
    entity_id: UUID | None,
    actions: list[str],
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    page: int,
    page_size: int,
) -> AuditPage:
    entries, total = await repository.search(
        session,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actions=actions,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return AuditPage(
        items=[_summary(e) for e in entries], total=total, page=page, page_size=page_size
    )


async def get_entry(session: AsyncSession, entry_id: UUID) -> AuditEntry:
    entry = await repository.get(session, entry_id)
    if entry is None:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)
    return AuditEntry(
        **_summary(entry).model_dump(),
        before=entry.before,
        after=entry.after,
        details=entry.details,
        request_id=entry.request_id,
    )


AUDIT_EXPORT = (
    ExportColumn("occurred_at", "Time", "Време"),
    ExportColumn("actor", "Actor", "Извършил"),
    ExportColumn("actor_type", "Actor type", "Вид извършил"),
    ExportColumn("action", "Action", "Действие"),
    ExportColumn("entity_type", "Record type", "Вид запис"),
    ExportColumn("entity_id", "Record ID", "ID на запис"),
    ExportColumn("ip", "IP address", "IP адрес"),
    ExportColumn("id", "ID", "ID"),
)


async def export_entries(
    session: AsyncSession,
    events: EventBus,
    principal: Principal,
    now: datetime,
    filters: Mapping[str, Any],
    options: ExportOptions,
) -> ExportFile:
    """FR-ADM-03 / FR-REP-02: the filtered audit log as XLSX or CSV (Admin)."""
    statement = repository.search_statement(**filters)
    columns = select_columns(AUDIT_EXPORT, options.columns)
    check_row_count(await repository.count(session, statement))
    locale = options.locale or await identity.user_locale(session, principal.user_id)
    rows = []
    for entry in await repository.all_rows(session, statement):
        summary = _summary(entry)
        rows.append(
            {
                **summary.model_dump(include={c.key for c in AUDIT_EXPORT}),
                "actor": summary.actor.name,
                "actor_type": summary.actor.type,
            }
        )
    content = render(columns, rows, options.format, locale, sheet="audit-log")
    await events.publish(
        session,
        exported_event(
            "audit_log", principal, now, rows=len(rows), options=options, filters=filters
        ),
    )
    await session.commit()
    return ExportFile(content, options.format, "audit-log", now.astimezone(SOFIA).date())
