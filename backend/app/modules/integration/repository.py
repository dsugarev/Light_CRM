"""Database queries. Called only by this module's service."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import aliased

from app.modules.integration.models import (
    ApiKey,
    ExternalReference,
    ExternalSystem,
    IdempotencyRecord,
    IntegrationClient,
    IntegrationUsage,
    OutboxEvent,
    WebhookAttempt,
    WebhookDelivery,
    WebhookSubscription,
)

OPEN_STATUSES = ("pending", "retrying")


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


# --- Webhooks ------------------------------------------------------------------------------------


async def subscriptions_of(session: AsyncSession, client_id: UUID) -> list[WebhookSubscription]:
    statement = (
        select(WebhookSubscription)
        .where(WebhookSubscription.client_id == client_id)
        .order_by(WebhookSubscription.created_at)
    )
    return list((await session.execute(statement)).scalars())


async def get_subscription(
    session: AsyncSession, subscription_id: UUID, *, for_update: bool = False
) -> WebhookSubscription | None:
    statement = select(WebhookSubscription).where(WebhookSubscription.id == subscription_id)
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def receiving_subscriptions(
    session: AsyncSession,
) -> list[tuple[WebhookSubscription, IntegrationClient]]:
    """Subscriptions that get new deliveries: active and not suspended. Deliveries for
    a deactivated client are kept and sent once it is active again."""
    statement = (
        select(WebhookSubscription, IntegrationClient)
        .join(IntegrationClient, IntegrationClient.id == WebhookSubscription.client_id)
        .where(WebhookSubscription.is_active, WebhookSubscription.suspended_at.is_(None))
    )
    return [(row[0], row[1]) for row in await session.execute(statement)]


async def undispatched_events(session: AsyncSession, limit: int) -> list[OutboxEvent]:
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.dispatched_at.is_(None))
        .order_by(OutboxEvent.occurred_at, OutboxEvent.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await session.execute(statement)).scalars())


async def claim_due_deliveries(
    session: AsyncSession, now: datetime, lease_until: datetime, limit: int
) -> list[UUID]:
    """Due deliveries of active subscriptions and clients (test events always), oldest
    first, locked and leased so a crashed worker's claims are retried. A delivery waits
    while an earlier one for the same record and subscription is still open (per-record
    ordering)."""
    earlier = aliased(WebhookDelivery)
    earlier_event = aliased(OutboxEvent)
    blocked = exists().where(
        earlier.subscription_id == WebhookDelivery.subscription_id,
        earlier.id != WebhookDelivery.id,
        earlier.status.in_(OPEN_STATUSES),
        earlier_event.id == earlier.event_id,
        earlier_event.entity_id == OutboxEvent.entity_id,
        or_(
            earlier_event.occurred_at < OutboxEvent.occurred_at,
            # Same moment: event IDs are UUIDv7, so they follow creation order.
            and_(
                earlier_event.occurred_at == OutboxEvent.occurred_at,
                earlier_event.id < OutboxEvent.id,
            ),
        ),
    )
    statement = (
        select(WebhookDelivery.id)
        .join(OutboxEvent, OutboxEvent.id == WebhookDelivery.event_id)
        .join(WebhookSubscription, WebhookSubscription.id == WebhookDelivery.subscription_id)
        .join(IntegrationClient, IntegrationClient.id == WebhookSubscription.client_id)
        .where(
            WebhookDelivery.status.in_(OPEN_STATUSES),
            WebhookDelivery.next_attempt_at <= now,
            or_(
                and_(
                    WebhookSubscription.is_active,
                    WebhookSubscription.suspended_at.is_(None),
                    IntegrationClient.is_active,
                ),
                # A test event goes out whatever the state, to check a fixed endpoint.
                OutboxEvent.event_type == "ping",
            ),
            or_(OutboxEvent.entity_id.is_(None), ~blocked),
        )
        .order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.created_at)
        .limit(limit)
        .with_for_update(of=WebhookDelivery, skip_locked=True)
    )
    ids = list((await session.execute(statement)).scalars())
    if ids:
        await session.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id.in_(ids))
            .values(next_attempt_at=lease_until)
        )
    return ids


async def get_delivery(
    session: AsyncSession, delivery_id: UUID, *, for_update: bool = False
) -> tuple[WebhookDelivery, OutboxEvent, WebhookSubscription] | None:
    statement = (
        select(WebhookDelivery, OutboxEvent, WebhookSubscription)
        .join(OutboxEvent, OutboxEvent.id == WebhookDelivery.event_id)
        .join(WebhookSubscription, WebhookSubscription.id == WebhookDelivery.subscription_id)
        .where(WebhookDelivery.id == delivery_id)
    )
    if for_update:
        statement = statement.with_for_update(of=WebhookDelivery)
    row = (await session.execute(statement)).one_or_none()
    return (row[0], row[1], row[2]) if row is not None else None


async def list_deliveries(
    session: AsyncSession,
    conditions: Sequence[ColumnElement[bool]],
    offset: int,
    limit: int,
) -> tuple[list[tuple[WebhookDelivery, OutboxEvent, WebhookSubscription]], int]:
    base = (
        select(WebhookDelivery, OutboxEvent, WebhookSubscription)
        .join(OutboxEvent, OutboxEvent.id == WebhookDelivery.event_id)
        .join(WebhookSubscription, WebhookSubscription.id == WebhookDelivery.subscription_id)
        .where(*conditions)
    )
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    statement = (
        base.order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [(r[0], r[1], r[2]) for r in await session.execute(statement)], total


async def attempts_of(session: AsyncSession, delivery_id: UUID) -> list[WebhookAttempt]:
    statement = (
        select(WebhookAttempt)
        .where(WebhookAttempt.delivery_id == delivery_id)
        .order_by(WebhookAttempt.number)
    )
    return list((await session.execute(statement)).scalars())


async def delivery_counts(
    session: AsyncSession, subscription_ids: Sequence[UUID], since: datetime
) -> dict[UUID, dict[str, int]]:
    if not subscription_ids:
        return {}
    statement = (
        select(WebhookDelivery.subscription_id, WebhookDelivery.status, func.count())
        .where(
            WebhookDelivery.subscription_id.in_(subscription_ids),
            WebhookDelivery.created_at >= since,
        )
        .group_by(WebhookDelivery.subscription_id, WebhookDelivery.status)
    )
    counts: dict[UUID, dict[str, int]] = {}
    for subscription_id, status, n in await session.execute(statement):
        counts.setdefault(subscription_id, {})[status] = n
    return counts


async def webhook_figures(
    session: AsyncSession, client_ids: Sequence[UUID], since: datetime
) -> dict[UUID, tuple[int, int, int]]:
    """Per client: subscriptions, failing deliveries (retrying, or failed since
    `since`) and suspended subscriptions."""
    if not client_ids:
        return {}
    subscriptions = (
        select(
            WebhookSubscription.client_id,
            func.count(),
            func.count().filter(WebhookSubscription.suspended_at.is_not(None)),
        )
        .where(WebhookSubscription.client_id.in_(client_ids))
        .group_by(WebhookSubscription.client_id)
    )
    failing = (
        select(WebhookSubscription.client_id, func.count())
        .join(WebhookDelivery, WebhookDelivery.subscription_id == WebhookSubscription.id)
        .where(
            WebhookSubscription.client_id.in_(client_ids),
            or_(
                WebhookDelivery.status == "retrying",
                and_(WebhookDelivery.status == "failed", WebhookDelivery.created_at >= since),
            ),
        )
        .group_by(WebhookSubscription.client_id)
    )
    failing_by_client = {row[0]: row[1] for row in (await session.execute(failing)).all()}
    return {
        client_id: (total, failing_by_client.get(client_id, 0), suspended)
        for client_id, total, suspended in await session.execute(subscriptions)
    }


async def purge_outbox(session: AsyncSession, before: datetime) -> int:
    """Events older than `before`, with their deliveries and attempts (cascade)."""
    result = await session.execute(
        delete(OutboxEvent).where(OutboxEvent.occurred_at < before).returning(OutboxEvent.id)
    )
    return len(result.all())
