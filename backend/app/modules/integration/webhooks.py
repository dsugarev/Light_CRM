"""Webhooks: the outbox, subscriptions, delivery and the delivery log (FR-INT-07, 08, 12).

Business modules only publish domain events. `record_event` (subscribed to the event
bus) turns the relevant ones into outbox rows in the same transaction (AC1). The
worker fans new events out to matching subscriptions (`dispatch`) and sends them
(`deliver_due`): only the worker makes outbound HTTP calls (CLAUDE.md, API spec 19.6).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import random
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.crypto import InvalidToken, decrypt, encrypt
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus
from app.core.principal import Principal
from app.modules.integration import repository
from app.modules.integration.models import (
    OutboxEvent,
    WebhookAttempt,
    WebhookDelivery,
    WebhookSubscription,
)
from app.modules.integration.netguard import Network, pinned_client, url_allowed
from app.modules.integration.schemas import (
    EVENT_TYPES,
    DeliveryCounts,
    Resource,
    WebhookAttemptOut,
    WebhookDeliveryDetail,
    WebhookDeliveryOut,
    WebhookDeliveryPage,
    WebhookSecret,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreated,
    WebhookSubscriptionOut,
    WebhookSubscriptionUpdate,
)
from app.modules.integration.service import RESOURCE_OF, Context, record_references
from app.modules.party import service as party
from app.modules.sales import service as sales

logger = logging.getLogger("app.webhooks")

PING = "ping"
RETRY_WINDOW = timedelta(hours=72)
SUSPEND_AFTER = timedelta(hours=72)
PREVIOUS_SECRET_TTL = timedelta(hours=24)
TIMEOUT_SECONDS = 10.0
LEASE = timedelta(minutes=5)
# Seconds before attempt 2, 3, ...; then every 6 hours, each with ±10 % jitter.
BACKOFF_SECONDS = (60, 300, 1800, 7200, 21600)
EXCERPT_CHARS = 1000
_READ_BYTES = 4096
_CONCURRENCY = 4
READ_SCOPE: Mapping[str, str] = {
    "organization": "organizations:read",
    "contact": "contacts:read",
    "lead": "leads:read",
    "opportunity": "opportunities:read",
}
_EVENT_TYPES = frozenset(EVENT_TYPES)
# Domain actions without an event type of their own are reported as `<record>.updated`.
_UPDATE_ACTIONS = frozenset({"archived", "restored", "owner_changed"})


def _not_found() -> AppError:
    return AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)


# --- Outbox (written in the business transaction) ----------------------------------------------


def event_type_for(event: DomainEvent) -> str | None:
    if event.action in _EVENT_TYPES:
        return event.action
    entity, _, verb = event.action.partition(".")
    if entity in READ_SCOPE and verb in _UPDATE_ACTIONS:
        return f"{entity}.updated"
    return None


def _actor(principal: Principal | None) -> dict[str, Any]:
    if principal is None:
        return {"type": "system", "id": None, "name": "CRM"}
    actor: dict[str, Any] = {
        "type": principal.type.value,
        "id": str(principal.user_id),
        "name": principal.display_name,
    }
    if principal.client_id is not None:
        actor["client_id"] = str(principal.client_id)  # lets a client skip its own changes
    return actor


def _changes(event: DomainEvent) -> list[str]:
    if event.before is None or event.after is None:
        return []
    keys = set(event.before) | set(event.after)
    return sorted(k for k in keys if event.before.get(k) != event.after.get(k))


async def record_event(session: AsyncSession, event: DomainEvent) -> None:
    """Event bus subscriber: an outbox row for each change subscribers may hear about."""
    event_type = event_type_for(event)
    if event_type is None or event.entity_id is None:
        return
    details = {"system": event.details.get("system")} if event_type.startswith("external_") else {}
    session.add(
        OutboxEvent(
            event_type=event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor=_actor(event.actor),
            changes=_changes(event),
            details=details,
            occurred_at=event.occurred_at,
        )
    )


# --- Fan-out and delivery (worker) --------------------------------------------------------------


def matches(patterns: Sequence[str], event_type: str) -> bool:
    return "*" in patterns or event_type in patterns or f"{event_type.split('.')[0]}.*" in patterns


def readable(scopes: Sequence[str], event: OutboxEvent) -> bool:
    """FR-INT-07 AC4: only events for record types the client may read."""
    scope = READ_SCOPE.get(event.entity_type or "")
    return event.event_type == PING or (scope is not None and scope in scopes)


async def dispatch(session: AsyncSession, now: datetime, *, batch: int = 500) -> int:
    """Turn new outbox events into deliveries for the subscriptions that want them."""
    events = await repository.undispatched_events(session, batch)
    if not events:
        return 0
    receivers = await repository.receiving_subscriptions(session)
    for event in events:
        for subscription, client in receivers:
            if matches(subscription.event_types, event.event_type) and readable(
                client.scopes, event
            ):
                session.add(_new_delivery(event.id, subscription.id, now))
        event.dispatched_at = now
    await session.commit()
    return len(events)


def _new_delivery(event_id: UUID, subscription_id: UUID, now: datetime) -> WebhookDelivery:
    return WebhookDelivery(
        event_id=event_id,
        subscription_id=subscription_id,
        status="pending",
        next_attempt_at=now,
        created_at=now,
    )


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


async def _snapshot(
    session: AsyncSession, settings: Settings, now: datetime, event: OutboxEvent
) -> dict[str, Any] | None:
    """The record as GET returns it now (API spec 19.6), or None if it is gone."""
    entity_id, entity_type = event.entity_id, event.entity_type
    if entity_id is None or entity_type is None or entity_type not in READ_SCOPE:
        return None
    events = EventBus()  # reads publish nothing
    try:
        if event.event_type == "external_reference.updated":
            ctx = Context(session=session, events=events, settings=settings, now=now)
            resource = cast("Resource", RESOURCE_OF[entity_type])
            references = await record_references(ctx, resource, entity_id)
            system = event.details.get("system")
            found = [r for r in references if r.system.code == system]
            return found[0].model_dump(mode="json") if found else None
        if entity_type in ("organization", "contact"):
            party_ctx = party.Context(
                session=session, events=events, settings=settings, now=now,
                organization_stats=sales.ORGANIZATION_STATS,
            )  # fmt: skip
            out: Any = await (
                party.get_organization(party_ctx, entity_id)
                if entity_type == "organization"
                else party.get_contact(party_ctx, entity_id)
            )
        else:
            sales_ctx = sales.Context(session=session, events=events, settings=settings, now=now)
            out = await (
                sales.get_lead(sales_ctx, entity_id)
                if entity_type == "lead"
                else sales.opportunities.get(sales_ctx, entity_id)
            )
    except AppError:
        return None
    result: dict[str, Any] = out.model_dump(mode="json")
    return result


async def build_payload(
    session: AsyncSession, settings: Settings, now: datetime, event: OutboxEvent
) -> dict[str, Any]:
    obj = None if event.event_type == PING else await _snapshot(session, settings, now, event)
    data: dict[str, Any] = {
        "entity_type": event.entity_type,
        "entity_id": str(event.entity_id) if event.entity_id else None,
        "version": obj.get("version") if obj and event.entity_type in ("lead", "opportunity")
        else None,
        "changes": event.changes,
        "object": obj,
    }  # fmt: skip
    if event.event_type == "external_reference.updated":
        data["system"] = event.details.get("system")
    return {
        "id": f"evt_{event.id.hex}",
        "type": event.event_type,
        "api_version": "v1",
        "occurred_at": _iso(event.occurred_at),
        "actor": event.actor,
        "data": data,
    }


def sign(signing_secrets: Sequence[str], timestamp: int, body: bytes) -> str:
    """`t=<unix>,v1=<hex>[,v1=<hex>]`: HMAC-SHA256 of "<t>.<body>" with each secret."""
    message = f"{timestamp}.".encode() + body
    signatures = [
        hmac.new(s.encode(), message, hashlib.sha256).hexdigest() for s in signing_secrets
    ]
    return ",".join([f"t={timestamp}", *(f"v1={s}" for s in signatures)])


def _signing_secrets(
    settings: Settings, subscription: WebhookSubscription, now: datetime
) -> list[str]:
    """Old then new while the previous secret is still valid (24 h after rotation)."""
    found = []
    if (
        subscription.previous_secret_encrypted
        and subscription.previous_secret_expires_at
        and subscription.previous_secret_expires_at > now
    ):
        found.append(decrypt(settings, subscription.previous_secret_encrypted))
    found.append(decrypt(settings, subscription.secret_encrypted))
    return found


def backoff(attempt: int) -> timedelta:
    """Delay after failed attempt number `attempt` (1-based)."""
    base = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1]
    return timedelta(seconds=base * random.uniform(0.9, 1.1))  # noqa: S311 - jitter, not security


@dataclass(frozen=True, slots=True)
class Outcome:
    status_code: int | None
    error: str | None
    excerpt: str | None
    duration_ms: int

    @property
    def succeeded(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300


async def send(url: str, headers: Mapping[str, str], body: bytes, network: Network) -> Outcome:
    """One POST to a vetted address: 10-second limit, no redirects, body excerpt only."""
    started = time.monotonic()

    def failed(error: str) -> Outcome:
        return Outcome(None, error, None, int((time.monotonic() - started) * 1000))

    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            try:
                addresses = await network.resolve(host, port)
            except OSError:
                return failed("dns_failed")
            if not addresses or not all(network.address_allowed(a) for a in addresses):
                return failed("address_not_allowed")
            async with (
                pinned_client(addresses[0], TIMEOUT_SECONDS) as client,
                client.stream("POST", url, content=body, headers=dict(headers)) as response,
            ):
                received = b""
                async for chunk in response.aiter_bytes():
                    received += chunk
                    if len(received) >= _READ_BYTES:
                        break
                excerpt = received.decode("utf-8", "replace")[:EXCERPT_CHARS] or None
                return Outcome(
                    response.status_code,
                    None,
                    excerpt,
                    int((time.monotonic() - started) * 1000),
                )
    except TimeoutError, httpx.TimeoutException:
        return failed("timeout")
    except httpx.ConnectError:
        return failed("connection_failed")
    except httpx.HTTPError as error:
        return failed(type(error).__name__)


SessionFactory = async_sessionmaker[AsyncSession]


async def deliver_due(
    sessions: SessionFactory,
    settings: Settings,
    now: datetime,
    *,
    network: Network | None = None,
    limit: int = 20,
) -> int:
    """Claim due deliveries and attempt them (a few at a time)."""
    async with sessions() as session:
        ids = await repository.claim_due_deliveries(session, now, now + LEASE, limit)
        await session.commit()
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def one(delivery_id: UUID) -> None:
        async with gate:
            await _attempt(sessions, settings, now, delivery_id, network or Network())

    await asyncio.gather(*(one(i) for i in ids))
    return len(ids)


async def _attempt(
    sessions: SessionFactory,
    settings: Settings,
    now: datetime,
    delivery_id: UUID,
    network: Network,
) -> None:
    # Read and build the request, then leave the database before the network call.
    async with sessions() as session:
        row = await repository.get_delivery(session, delivery_id)
        if row is None:
            return
        delivery, event, subscription = row
        number = delivery.attempt_count + 1
        url = subscription.url
        payload = await build_payload(session, settings, now, event)
        try:
            signing = _signing_secrets(settings, subscription, now)
        except InvalidToken:
            signing = []
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if not signing:
        outcome = Outcome(None, "secret_unreadable", None, 0)
    elif not url_allowed(url, settings):
        outcome = Outcome(None, "url_not_allowed", None, 0)
    else:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LightCRM-Webhooks/1",
            "X-CRM-Event-Id": payload["id"],
            "X-CRM-Event-Type": payload["type"],
            "X-CRM-Delivery-Attempt": str(number),
            "X-CRM-Signature": sign(signing, int(now.timestamp()), body),
        }
        outcome = await send(url, headers, body, network)
    async with sessions() as session:
        await _record(session, now, delivery_id, number, outcome)


async def _record(
    session: AsyncSession, now: datetime, delivery_id: UUID, number: int, outcome: Outcome
) -> None:
    row = await repository.get_delivery(session, delivery_id, for_update=True)
    if row is None:
        return
    delivery, event, _ = row
    subscription = await repository.get_subscription(
        session, delivery.subscription_id, for_update=True
    )
    session.add(
        WebhookAttempt(
            delivery_id=delivery.id,
            number=number,
            attempted_at=now,
            duration_ms=outcome.duration_ms,
            status_code=outcome.status_code,
            error=outcome.error,
            response_excerpt=outcome.excerpt,
        )
    )
    delivery.attempt_count = number
    delivery.first_attempt_at = delivery.first_attempt_at or now
    delivery.last_status_code = outcome.status_code
    delivery.last_error = outcome.error
    delivery.last_response_excerpt = outcome.excerpt
    is_ping = event.event_type == PING
    if outcome.succeeded:
        delivery.status, delivery.delivered_at, delivery.next_attempt_at = "succeeded", now, None
        if subscription is not None and not is_ping:
            subscription.failing_since = None
    else:
        # A test event is attempted once; others are retried for 72 hours (AC3).
        if is_ping or now - delivery.first_attempt_at >= RETRY_WINDOW:
            delivery.status, delivery.next_attempt_at = "failed", None
        else:
            delivery.status, delivery.next_attempt_at = "retrying", now + backoff(number)
        if subscription is not None and not is_ping:
            _note_failure(subscription, now)
    await session.commit()


def _note_failure(subscription: WebhookSubscription, now: datetime) -> None:
    """A subscription failing continuously for 72 hours is suspended (API spec 19.6)."""
    if subscription.failing_since is None:
        subscription.failing_since = now
    elif subscription.suspended_at is None and now - subscription.failing_since >= SUSPEND_AFTER:
        subscription.suspended_at = now
        logger.warning(
            "webhook_subscription_suspended",
            extra={
                "subscription_id": str(subscription.id),
                "client_id": str(subscription.client_id),
            },
        )


# --- Administration (API spec 19.7) -------------------------------------------------------------


async def _publish(
    ctx: Context,
    action: str,
    entity_type: str,
    entity_id: UUID,
    principal: Principal,
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
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
        ),
    )


def _view(subscription: WebhookSubscription) -> dict[str, Any]:
    """Audited fields; never the secret."""
    return {
        "url": subscription.url,
        "event_types": list(subscription.event_types),
        "is_active": subscription.is_active,
        "suspended": subscription.suspended_at is not None,
    }


def _check_url(settings: Settings, url: str) -> None:
    if not url_allowed(url, settings):
        raise AppError(
            ErrorCode.WEBHOOK_URL_NOT_ALLOWED,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("url", "webhook.url_not_allowed")],
        )


def _new_secret() -> str:
    return f"whsec_{secrets.token_urlsafe(32)}"


async def _subscriptions_out(
    ctx: Context, subscriptions: Sequence[WebhookSubscription]
) -> list[WebhookSubscriptionOut]:
    counts = await repository.delivery_counts(
        ctx.session, [s.id for s in subscriptions], ctx.now - timedelta(hours=24)
    )
    out = []
    for s in subscriptions:
        figures = counts.get(s.id, {})
        out.append(
            WebhookSubscriptionOut(
                id=s.id,
                client_id=s.client_id,
                url=s.url,
                event_types=list(s.event_types),
                is_active=s.is_active,
                suspended_at=s.suspended_at,
                failing_since=s.failing_since,
                previous_secret_valid_until=s.previous_secret_expires_at
                if s.previous_secret_expires_at and s.previous_secret_expires_at > ctx.now
                else None,
                deliveries_24h=DeliveryCounts(
                    succeeded=figures.get("succeeded", 0),
                    pending=figures.get("pending", 0),
                    retrying=figures.get("retrying", 0),
                    failed=figures.get("failed", 0),
                ),
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
        )
    return out


async def _load_subscription(ctx: Context, subscription_id: UUID) -> WebhookSubscription:
    subscription = await repository.get_subscription(ctx.session, subscription_id, for_update=True)
    if subscription is None:
        raise _not_found()
    return subscription


async def _fresh(ctx: Context, subscription_id: UUID) -> WebhookSubscriptionOut:
    ctx.session.expire_all()
    subscription = await repository.get_subscription(ctx.session, subscription_id)
    if subscription is None:
        raise _not_found()
    return (await _subscriptions_out(ctx, [subscription]))[0]


async def list_subscriptions(ctx: Context, client_id: UUID) -> list[WebhookSubscriptionOut]:
    if await repository.get_client(ctx.session, client_id) is None:
        raise _not_found()
    return await _subscriptions_out(ctx, await repository.subscriptions_of(ctx.session, client_id))


async def create_subscription(
    ctx: Context, principal: Principal, client_id: UUID, data: WebhookSubscriptionCreate
) -> WebhookSubscriptionCreated:
    """FR-INT-07: the signing secret is returned once, here."""
    if await repository.get_client(ctx.session, client_id) is None:
        raise _not_found()
    _check_url(ctx.settings, data.url)
    secret = _new_secret()
    subscription = WebhookSubscription(
        client_id=client_id,
        url=data.url,
        event_types=sorted(set(data.event_types)),
        secret_encrypted=encrypt(ctx.settings, secret),
        is_active=data.is_active,
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    ctx.session.add(subscription)
    await ctx.session.flush()
    await _publish(
        ctx, "webhook_subscription.created", "webhook_subscription", subscription.id, principal,
        after=_view(subscription),
    )  # fmt: skip
    subscription_id = subscription.id
    await ctx.session.commit()
    out = await _fresh(ctx, subscription_id)
    return WebhookSubscriptionCreated(**out.model_dump(), secret=secret)


async def update_subscription(
    ctx: Context, principal: Principal, subscription_id: UUID, data: WebhookSubscriptionUpdate
) -> WebhookSubscriptionOut:
    subscription = await _load_subscription(ctx, subscription_id)
    before = _view(subscription)
    if data.url is not None:
        _check_url(ctx.settings, data.url)
        subscription.url = data.url
    if data.event_types is not None:
        subscription.event_types = sorted(set(data.event_types))
    if data.is_active is not None:
        subscription.is_active = data.is_active
        if data.is_active:  # switching on again lifts a suspension
            subscription.suspended_at = subscription.failing_since = None
    after = _view(subscription)
    if after != before:
        subscription.updated_by = principal.user_id
        await _publish(
            ctx, "webhook_subscription.updated", "webhook_subscription", subscription.id,
            principal, before=before, after=after,
        )  # fmt: skip
    await ctx.session.commit()
    return await _fresh(ctx, subscription_id)


async def delete_subscription(ctx: Context, principal: Principal, subscription_id: UUID) -> None:
    subscription = await _load_subscription(ctx, subscription_id)
    before = _view(subscription)
    await ctx.session.delete(subscription)
    await _publish(
        ctx, "webhook_subscription.deleted", "webhook_subscription", subscription_id, principal,
        before=before,
    )  # fmt: skip
    await ctx.session.commit()


async def rotate_secret(ctx: Context, principal: Principal, subscription_id: UUID) -> WebhookSecret:
    """A new secret, returned once; the old one keeps signing for 24 hours."""
    subscription = await _load_subscription(ctx, subscription_id)
    secret = _new_secret()
    valid_until = ctx.now + PREVIOUS_SECRET_TTL
    subscription.previous_secret_encrypted = subscription.secret_encrypted
    subscription.previous_secret_expires_at = valid_until
    subscription.secret_encrypted = encrypt(ctx.settings, secret)
    subscription.updated_by = principal.user_id
    await _publish(
        ctx, "webhook_subscription.secret_rotated", "webhook_subscription", subscription_id,
        principal,
    )  # fmt: skip
    await ctx.session.commit()
    return WebhookSecret(secret=secret, previous_secret_valid_until=valid_until)


async def send_test(
    ctx: Context, principal: Principal, subscription_id: UUID
) -> WebhookDeliveryOut:
    """Queue a `ping` for the worker (one attempt); the result shows in the delivery."""
    subscription = await _load_subscription(ctx, subscription_id)
    event = OutboxEvent(
        event_type=PING,
        entity_type=None,
        entity_id=None,
        actor=_actor(principal),
        changes=[],
        details={},
        occurred_at=ctx.now,
        dispatched_at=ctx.now,
    )
    ctx.session.add(event)
    await ctx.session.flush()
    delivery = _new_delivery(event.id, subscription.id, ctx.now)
    ctx.session.add(delivery)
    await ctx.session.flush()
    await _publish(
        ctx, "webhook_subscription.test_sent", "webhook_subscription", subscription_id, principal
    )
    delivery_id = delivery.id
    await ctx.session.commit()
    return await _delivery_out(ctx, delivery_id)


async def _delivery_out(ctx: Context, delivery_id: UUID) -> WebhookDeliveryOut:
    ctx.session.expire_all()
    row = await repository.get_delivery(ctx.session, delivery_id)
    if row is None:
        raise _not_found()
    return _delivery(*row)


def _delivery(
    delivery: WebhookDelivery, event: OutboxEvent, subscription: WebhookSubscription
) -> WebhookDeliveryOut:
    return WebhookDeliveryOut(
        id=delivery.id,
        subscription_id=subscription.id,
        client_id=subscription.client_id,
        event_id=f"evt_{event.id.hex}",
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        occurred_at=event.occurred_at,
        status=delivery.status,  # type: ignore[arg-type]
        attempt_count=delivery.attempt_count,
        next_attempt_at=delivery.next_attempt_at,
        last_status_code=delivery.last_status_code,
        last_error=delivery.last_error,
        delivered_at=delivery.delivered_at,
        created_at=delivery.created_at,
    )


@dataclass(frozen=True, slots=True)
class DeliveryFilters:
    subscription_id: UUID | None = None
    client_id: UUID | None = None
    event_type: str | None = None
    status: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


def _conditions(filters: DeliveryFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.subscription_id is not None:
        conditions.append(WebhookDelivery.subscription_id == filters.subscription_id)
    if filters.client_id is not None:
        conditions.append(WebhookSubscription.client_id == filters.client_id)
    if filters.event_type is not None:
        conditions.append(OutboxEvent.event_type == filters.event_type)
    if filters.status is not None:
        conditions.append(WebhookDelivery.status == filters.status)
    if filters.created_from is not None:
        conditions.append(WebhookDelivery.created_at >= filters.created_from)
    if filters.created_to is not None:
        conditions.append(WebhookDelivery.created_at <= filters.created_to)
    return conditions


async def list_deliveries(
    ctx: Context, filters: DeliveryFilters, page: int, page_size: int
) -> WebhookDeliveryPage:
    rows, total = await repository.list_deliveries(
        ctx.session, _conditions(filters), (page - 1) * page_size, page_size
    )
    return WebhookDeliveryPage(
        items=[_delivery(*row) for row in rows], total=total, page=page, page_size=page_size
    )


async def get_delivery(ctx: Context, delivery_id: UUID) -> WebhookDeliveryDetail:
    row = await repository.get_delivery(ctx.session, delivery_id)
    if row is None:
        raise _not_found()
    attempts = await repository.attempts_of(ctx.session, delivery_id)
    return WebhookDeliveryDetail(
        **_delivery(*row).model_dump(),
        url=row[2].url,
        attempts=[
            WebhookAttemptOut(
                number=a.number,
                attempted_at=a.attempted_at,
                duration_ms=a.duration_ms,
                status_code=a.status_code,
                error=a.error,
                response_excerpt=a.response_excerpt,
            )
            for a in attempts
        ],
    )


async def redeliver(ctx: Context, principal: Principal, delivery_id: UUID) -> WebhookDeliveryOut:
    """Queue the event again for the same subscription, as a new delivery."""
    row = await repository.get_delivery(ctx.session, delivery_id)
    if row is None:
        raise _not_found()
    original, event, subscription = row
    delivery = _new_delivery(event.id, subscription.id, ctx.now)
    ctx.session.add(delivery)
    await ctx.session.flush()
    await _publish(
        ctx, "webhook_delivery.redelivered", "webhook_delivery", delivery.id, principal,
        after={"redelivery_of": str(original.id), "event_type": event.event_type},
    )  # fmt: skip
    new_id = delivery.id
    await ctx.session.commit()
    return await _delivery_out(ctx, new_id)


async def purge(session: AsyncSession, now: datetime) -> dict[str, int]:
    """Housekeeping: events with their deliveries and attempts after 30 days."""
    removed = {"outbox_events": await repository.purge_outbox(session, now - timedelta(days=30))}
    await session.commit()
    return removed
