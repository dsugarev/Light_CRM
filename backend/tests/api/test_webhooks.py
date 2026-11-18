"""Webhooks: outbox, subscriptions, delivery, retries, the delivery log (FR-INT-07, 08, 12).

Deliveries go to the reference receiver (`deploy/examples/webhook_receiver.py`) running
on 127.0.0.1; the tests pass a `Network` that allows loopback, which the default
refuses (tested separately).
"""

import importlib.util
import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.config import Environment, Settings
from app.core.events import DomainEvent
from app.core.principal import RoleCode
from app.main import create_event_bus
from app.modules.integration import netguard, webhooks
from app.modules.integration.models import (
    OutboxEvent,
    WebhookDelivery,
    WebhookSubscription,
)
from app.modules.integration.netguard import Network
from tests.api.test_opportunities import act, create_opp, create_org
from tests.helpers import TestApp

_RECEIVER_PATH = Path(__file__).parents[3] / "deploy" / "examples" / "webhook_receiver.py"


def _load_receiver() -> ModuleType:
    spec = importlib.util.spec_from_file_location("webhook_receiver", _RECEIVER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


receiver = _load_receiver()
LOCAL = Network(address_allowed=lambda _address: True)


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"webhook_allowed_hosts": "127.0.0.1, hooks.example.test, *.erp.example.test"}
    )


class Receiver:
    """The reference receiver in a thread, collecting verified events."""

    def __init__(self, secrets: list[str]) -> None:
        self.events: list[dict[str, Any]] = []
        self.secrets = secrets
        self.server = receiver.make_server("127.0.0.1", 0, self.secrets, self.events.append)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/hooks/crm"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def receivers() -> Iterator[list[Receiver]]:
    started: list[Receiver] = []
    yield started
    for r in started:
        r.close()


class _Fixed(BaseHTTPRequestHandler):
    status = 500
    location: str | None = None

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(self.status)
        if self.location:
            self.send_header("Location", self.location)
        body = b'{"error": "down"}'
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def failing_endpoint() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Fixed)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/hooks"
    server.shutdown()
    server.server_close()


def real_now() -> datetime:
    # The receiver checks signature timestamps against the real clock.
    return datetime.now(UTC)


async def subscribe(
    test_app: TestApp,
    client_id: UUID,
    url: str,
    event_types: list[str] | None = None,
) -> dict[str, Any]:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.post(
        f"/api/v1/integration-clients/{client_id}/webhook-subscriptions",
        json={"url": url, "event_types": event_types or ["*"]},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def run_worker(test_app: TestApp, now: datetime, network: Network = LOCAL) -> int:
    async with test_app.sessions() as session:
        await webhooks.dispatch(session, now)
    return await webhooks.deliver_due(
        test_app.sessions, test_app.app.state.settings, now, network=network
    )


async def deliveries(test_app: TestApp) -> list[WebhookDelivery]:
    async with test_app.sessions() as session:
        statement = select(WebhookDelivery).order_by(WebhookDelivery.created_at)
        return list((await session.execute(statement)).scalars())


async def outbox(test_app: TestApp) -> list[OutboxEvent]:
    async with test_app.sessions() as session:
        statement = select(OutboxEvent).order_by(OutboxEvent.occurred_at, OutboxEvent.id)
        return list((await session.execute(statement)).scalars())


# --- AC1: the outbox is written in the business transaction ------------------------------------


async def test_FR_INT_07_AC1_events_commit_or_roll_back_with_the_change(test_app: TestApp) -> None:
    bus = create_event_bus()
    event = DomainEvent(
        action="organization.updated",
        entity_type="organization",
        entity_id=UUID("01930000-0000-7000-8000-0000000000b1"),
        actor=None,
        occurred_at=test_app.clock.now(),
        before={"name": "A", "city": "Sofia"},
        after={"name": "B", "city": "Sofia"},
    )
    async with test_app.sessions() as session:
        await bus.publish(session, event)
        await session.rollback()
    assert await outbox(test_app) == []
    async with test_app.sessions() as session:
        await bus.publish(session, event)
        await session.commit()
    [row] = await outbox(test_app)
    assert (row.event_type, row.changes, row.actor) == (
        "organization.updated",
        ["name"],
        {"type": "system", "id": None, "name": "CRM"},
    )


async def test_FR_INT_07_AC1_business_changes_write_mapped_events(test_app: TestApp) -> None:
    rep, rep_user = await test_app.signed_in()
    opp = await create_opp(rep)
    assert (await act(rep, opp, "close", outcome="won")).status_code == 200
    types = [e.event_type for e in await outbox(test_app)]
    assert types[:2] == ["organization.created", "opportunity.created"]
    assert "opportunity.closed_won" in types
    # Audit-only actions (sign-in, exports) never reach the outbox.
    assert all(not t.startswith(("auth.", "user.")) for t in types)
    closed = next(e for e in await outbox(test_app) if e.event_type == "opportunity.closed_won")
    assert closed.actor == {"type": "user", "id": str(rep_user.id), "name": rep_user.full_name}
    assert "stage_id" in closed.changes


def test_FR_INT_07_domain_actions_map_to_event_types() -> None:
    def mapped(action: str) -> str | None:
        return webhooks.event_type_for(
            DomainEvent(action, "lead", None, None, datetime(2026, 11, 17, tzinfo=UTC))
        )

    assert mapped("lead.status_changed") == "lead.status_changed"
    assert mapped("lead.archived") == "lead.updated"
    assert mapped("opportunity.owner_changed") == "opportunity.updated"
    assert mapped("organization.archived") == "organization.archived"
    assert mapped("organization.exported") is None
    assert mapped("user.created") is None
    assert webhooks.matches(["opportunity.*"], "opportunity.closed_won")
    assert webhooks.matches(["*"], "lead.created")
    assert not webhooks.matches(["opportunity.closed_won"], "opportunity.closed_lost")


# --- Subscriptions (API spec 19.7) --------------------------------------------------------------


async def test_FR_INT_07_subscription_secret_shown_once_and_encrypted(test_app: TestApp) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    created = await subscribe(test_app, erp.client_id, "https://hooks.example.test/crm")
    secret = created["secret"]
    assert secret.startswith("whsec_")
    assert len(secret) > 40
    assert created["event_types"] == ["*"]
    assert created["is_active"]
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    [listed] = (
        await admin.get(f"/api/v1/integration-clients/{erp.client_id}/webhook-subscriptions")
    ).json()
    assert "secret" not in listed
    assert listed["deliveries_24h"] == {"succeeded": 0, "pending": 0, "retrying": 0, "failed": 0}
    async with test_app.sessions() as session:
        stored = await session.get(WebhookSubscription, UUID(created["id"]))
        assert stored is not None
        assert secret not in stored.secret_encrypted
    [entry] = await test_app.audit("webhook_subscription.created")
    assert secret not in json.dumps([entry.before, entry.after])


@pytest.mark.parametrize(
    "url",
    [
        "https://elsewhere.example.test/hooks",
        "https://user:pw@hooks.example.test/hooks",
        "ftp://hooks.example.test/hooks",
        "https://erp.example.test/hooks",  # *.erp.example.test does not cover the bare suffix
        "not a url",
    ],
)
async def test_FR_INT_07_AC5_url_must_be_on_the_allowlist(test_app: TestApp, url: str) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.post(
        f"/api/v1/integration-clients/{erp.client_id}/webhook-subscriptions",
        json={"url": url, "event_types": ["*"]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "webhook.url_not_allowed"
    assert response.json()["errors"] == [{"field": "url", "code": "webhook.url_not_allowed"}]


async def test_FR_INT_07_subscription_validation_update_and_delete(test_app: TestApp) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    path = f"/api/v1/integration-clients/{erp.client_id}/webhook-subscriptions"
    bad = await admin.post(path, json={"url": "https://a.erp.example.test/h", "event_types": ["x"]})
    assert bad.status_code == 422
    assert bad.json()["errors"][0]["field"] == "event_types.0"
    missing = await admin.post(
        "/api/v1/integration-clients/01930000-0000-7000-8000-000000000999/webhook-subscriptions",
        json={"url": "https://a.erp.example.test/h", "event_types": ["*"]},
    )
    assert missing.status_code == 404
    created = await subscribe(
        test_app, erp.client_id, "https://a.erp.example.test/h", ["lead.*", "lead.*"]
    )
    assert created["event_types"] == ["lead.*"]
    sub = f"/api/v1/webhook-subscriptions/{created['id']}"
    changed = await admin.patch(sub, json={"event_types": ["organization.*"], "is_active": False})
    assert changed.status_code == 200, changed.text
    assert (changed.json()["event_types"], changed.json()["is_active"]) == (
        ["organization.*"],
        False,
    )
    assert (await admin.patch(sub, json={"url": "https://evil.test/h"})).status_code == 422
    assert len(await test_app.audit("webhook_subscription.updated")) == 1
    assert (await admin.delete(sub)).status_code == 204
    assert (await admin.patch(sub, json={"is_active": True})).status_code == 404
    assert len(await test_app.audit("webhook_subscription.deleted")) == 1


# --- Fan-out and AC4 ----------------------------------------------------------------------------


async def test_FR_INT_07_AC4_only_events_the_client_may_read(test_app: TestApp) -> None:
    orgs_only = await test_app.integration_client(["organizations:read"], name="Orgs")
    sales = await test_app.integration_client(
        ["organizations:read", "opportunities:read"], system="billing", name="Billing"
    )
    await subscribe(test_app, orgs_only.client_id, "https://hooks.example.test/a")
    await subscribe(
        test_app, sales.client_id, "https://hooks.example.test/b", ["opportunity.closed_won"]
    )
    rep, _ = await test_app.signed_in()
    opp = await create_opp(rep)
    await act(rep, opp, "close", outcome="won")
    async with test_app.sessions() as session:
        await webhooks.dispatch(session, test_app.clock.now())
    async with test_app.sessions() as session:
        rows = (
            await session.execute(
                select(WebhookSubscription.client_id, OutboxEvent.event_type)
                .join(WebhookDelivery, WebhookDelivery.subscription_id == WebhookSubscription.id)
                .join(OutboxEvent, OutboxEvent.id == WebhookDelivery.event_id)
            )
        ).all()
    received = {(client, event_type) for client, event_type in rows}
    assert received == {
        (orgs_only.client_id, "organization.created"),
        (sales.client_id, "opportunity.closed_won"),
    }
    assert all(e.dispatched_at is not None for e in await outbox(test_app))


# --- Delivery ------------------------------------------------------------------------------------


async def test_FR_INT_07_AC2_signed_delivery_with_the_current_record(
    test_app: TestApp, receivers: list[Receiver]
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    sink = Receiver([])
    receivers.append(sink)
    created = await subscribe(test_app, erp.client_id, sink.url, ["organization.created"])
    sink.secrets.append(created["secret"])
    rep, _ = await test_app.signed_in()
    org = await create_org(rep, "Вега Телеком ООД")

    assert await run_worker(test_app, real_now()) == 1
    [event] = sink.events
    assert event["type"] == "organization.created"
    assert event["id"].startswith("evt_")
    assert event["api_version"] == "v1"
    assert event["data"]["entity_id"] == org["id"]
    current = (await rep.get(f"/api/v1/organizations/{org['id']}")).json()
    assert event["data"]["object"] == current
    [delivery] = await deliveries(test_app)
    assert (delivery.status, delivery.attempt_count, delivery.last_status_code) == (
        "succeeded",
        1,
        204,
    )
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    detail = (await admin.get(f"/api/v1/webhook-deliveries/{delivery.id}")).json()
    assert detail["url"] == sink.url
    assert detail["event_id"] == event["id"]
    assert [a["status_code"] for a in detail["attempts"]] == [204]
    # Nothing left to send.
    assert await run_worker(test_app, real_now()) == 0


async def test_FR_INT_07_wrong_signature_is_refused_by_the_receiver(
    test_app: TestApp, receivers: list[Receiver]
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    sink = Receiver(["whsec_not-the-right-one"])
    receivers.append(sink)
    await subscribe(test_app, erp.client_id, sink.url)
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    await run_worker(test_app, real_now())
    assert sink.events == []
    [delivery] = await deliveries(test_app)
    assert (delivery.status, delivery.last_status_code) == ("retrying", 401)


async def test_FR_INT_07_AC3_retries_with_backoff_then_fails_after_72_hours(
    test_app: TestApp, failing_endpoint: str
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    created = await subscribe(test_app, erp.client_id, failing_endpoint)
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    start = test_app.clock.now()
    await run_worker(test_app, start)
    [delivery] = await deliveries(test_app)
    assert (delivery.status, delivery.attempt_count, delivery.last_status_code) == (
        "retrying",
        1,
        500,
    )
    assert delivery.last_response_excerpt == '{"error": "down"}'
    assert delivery.next_attempt_at is not None
    assert timedelta(seconds=54) <= delivery.next_attempt_at - start <= timedelta(seconds=66)
    # Not due yet: nothing is sent.
    assert await run_worker(test_app, start + timedelta(seconds=30)) == 0
    moment = start
    while True:
        moment += timedelta(hours=7)
        await run_worker(test_app, moment)
        [delivery] = await deliveries(test_app)
        if delivery.status == "failed":
            break
        assert moment - start < timedelta(hours=90)
    assert moment - start >= timedelta(hours=72)
    assert delivery.next_attempt_at is None
    async with test_app.sessions() as session:
        subscription = await session.get(WebhookSubscription, UUID(created["id"]))
        assert subscription is not None
        assert subscription.failing_since == start
        assert subscription.suspended_at is not None  # failing continuously for 72 hours
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    figures = (await admin.get(f"/api/v1/integration-clients/{erp.client_id}")).json()
    assert figures["webhooks"] == {
        "subscriptions": 1,
        "failing_deliveries": 1,
        "suspended_subscriptions": 1,
    }
    # Switching the subscription on again lifts the suspension.
    sub = (
        await admin.patch(
            f"/api/v1/webhook-subscriptions/{created['id']}", json={"is_active": True}
        )
    ).json()
    assert (sub["suspended_at"], sub["failing_since"]) == (None, None)


def test_FR_INT_07_AC3_backoff_schedule() -> None:
    expected = [60, 300, 1800, 7200, 21600, 21600, 21600]
    for attempt, seconds in enumerate(expected, start=1):
        delay = webhooks.backoff(attempt).total_seconds()
        assert seconds * 0.9 <= delay <= seconds * 1.1


async def test_FR_INT_07_redirects_are_not_followed(
    test_app: TestApp, failing_endpoint: str
) -> None:
    _Fixed.status, _Fixed.location = 302, "http://127.0.0.1:1/elsewhere"
    try:
        erp = await test_app.integration_client(["organizations:read"])
        await subscribe(test_app, erp.client_id, failing_endpoint)
        rep, _ = await test_app.signed_in()
        await create_org(rep)
        await run_worker(test_app, test_app.clock.now())
    finally:
        _Fixed.status, _Fixed.location = 500, None
    [delivery] = await deliveries(test_app)
    assert (delivery.status, delivery.last_status_code) == ("retrying", 302)


async def test_FR_INT_07_AC5_loopback_is_refused_after_resolution(
    test_app: TestApp, receivers: list[Receiver]
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    sink = Receiver([])
    receivers.append(sink)
    await subscribe(test_app, erp.client_id, sink.url)  # host on the allowlist
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    await run_worker(test_app, real_now(), network=Network())  # the default policy
    assert sink.events == []
    [delivery] = await deliveries(test_app)
    assert (delivery.status, delivery.last_error) == ("retrying", "address_not_allowed")


async def test_FR_INT_07_url_rechecked_at_delivery(
    test_app: TestApp, receivers: list[Receiver]
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    sink = Receiver([])
    receivers.append(sink)
    await subscribe(test_app, erp.client_id, sink.url)
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    narrowed = test_app.app.state.settings.model_copy(
        update={"webhook_allowed_hosts": "hooks.example.test"}
    )
    async with test_app.sessions() as session:
        await webhooks.dispatch(session, real_now())
    await webhooks.deliver_due(test_app.sessions, narrowed, real_now(), network=LOCAL)
    [delivery] = await deliveries(test_app)
    assert (delivery.status, delivery.last_error) == ("retrying", "url_not_allowed")


async def test_FR_INT_07_rotation_signs_with_both_secrets_for_24_hours(
    test_app: TestApp, receivers: list[Receiver]
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    old_only = Receiver([])
    receivers.append(old_only)
    created = await subscribe(test_app, erp.client_id, old_only.url)
    old_only.secrets.append(created["secret"])
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    rotated = await admin.post(f"/api/v1/webhook-subscriptions/{created['id']}/rotate-secret")
    assert rotated.status_code == 200, rotated.text
    new_secret = rotated.json()["secret"]
    assert new_secret != created["secret"]
    valid_until = datetime.fromisoformat(rotated.json()["previous_secret_valid_until"])
    assert valid_until == test_app.clock.now() + timedelta(hours=24)
    assert len(await test_app.audit("webhook_subscription.secret_rotated")) == 1

    async with test_app.sessions() as session:
        subscription = await session.get(WebhookSubscription, UUID(created["id"]))
        assert subscription is not None
        settings = test_app.app.state.settings
        now = test_app.clock.now()
        both = webhooks._signing_secrets(settings, subscription, now)
        later = webhooks._signing_secrets(settings, subscription, now + timedelta(hours=25))
    assert both == [created["secret"], new_secret]
    assert later == [new_secret]
    header = webhooks.sign(both, 1_763_380_000, b"{}")
    assert header.startswith("t=1763380000,v1=")
    assert header.count("v1=") == 2
    assert receiver.verify_signature([created["secret"]], header, b"{}", now=1_763_380_000)
    assert receiver.verify_signature([new_secret], header, b"{}", now=1_763_380_000)


async def test_FR_INT_12_test_event_is_sent_once_even_for_an_inactive_client(
    test_app: TestApp, receivers: list[Receiver], failing_endpoint: str
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    sink = Receiver([])
    receivers.append(sink)
    created = await subscribe(test_app, erp.client_id, sink.url)
    sink.secrets.append(created["secret"])
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    await admin.post(f"/api/v1/integration-clients/{erp.client_id}/deactivate")
    queued = await admin.post(f"/api/v1/webhook-subscriptions/{created['id']}/test")
    assert queued.status_code == 202, queued.text
    assert (queued.json()["event_type"], queued.json()["status"]) == ("ping", "pending")
    await run_worker(test_app, real_now())
    [ping] = sink.events
    assert ping["type"] == "ping"
    assert ping["data"]["object"] is None
    detail = (await admin.get(f"/api/v1/webhook-deliveries/{queued.json()['id']}")).json()
    assert (detail["status"], detail["attempts"][0]["status_code"]) == ("succeeded", 204)
    assert len(await test_app.audit("webhook_subscription.test_sent")) == 1

    # A failing test event is not retried and does not count towards suspension.
    broken = await subscribe(test_app, erp.client_id, failing_endpoint)
    queued = await admin.post(f"/api/v1/webhook-subscriptions/{broken['id']}/test")
    await run_worker(test_app, real_now())
    detail = (await admin.get(f"/api/v1/webhook-deliveries/{queued.json()['id']}")).json()
    assert (detail["status"], detail["next_attempt_at"]) == ("failed", None)
    figures = (await admin.get(f"/api/v1/integration-clients/{erp.client_id}")).json()
    assert figures["webhooks"]["failing_deliveries"] == 0
    async with test_app.sessions() as session:
        subscription = await session.get(WebhookSubscription, UUID(broken["id"]))
        assert subscription is not None
        assert subscription.failing_since is None


async def test_FR_INT_01_deliveries_wait_while_the_client_is_inactive(
    test_app: TestApp, receivers: list[Receiver]
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    sink = Receiver([])
    receivers.append(sink)
    created = await subscribe(test_app, erp.client_id, sink.url)
    sink.secrets.append(created["secret"])
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    await admin.post(f"/api/v1/integration-clients/{erp.client_id}/deactivate")
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    assert await run_worker(test_app, real_now()) == 0
    [delivery] = await deliveries(test_app)
    assert (delivery.status, delivery.attempt_count) == ("pending", 0)
    await admin.post(f"/api/v1/integration-clients/{erp.client_id}/activate")
    assert await run_worker(test_app, real_now()) == 1
    assert [e["type"] for e in sink.events] == ["organization.created"]


async def test_FR_INT_07_events_for_one_record_are_delivered_in_order(
    test_app: TestApp, failing_endpoint: str
) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    await subscribe(test_app, erp.client_id, failing_endpoint)
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    other = await create_org(rep, "Друга ЕООД")
    patched = await rep.patch(f"/api/v1/organizations/{org['id']}", json={"city": "Варна"})
    assert patched.status_code == 200, patched.text
    now = test_app.clock.now()
    # The first event for `org` fails; its update waits, the other record goes ahead.
    assert await run_worker(test_app, now) == 2
    attempted = {d.event_id for d in await deliveries(test_app) if d.attempt_count}
    events = {e.id: e for e in await outbox(test_app)}
    assert {(events[i].entity_id, events[i].event_type) for i in attempted} == {
        (UUID(org["id"]), "organization.created"),
        (UUID(other["id"]), "organization.created"),
    }


async def test_FR_INT_12_delivery_log_filters_and_redeliver(
    test_app: TestApp, receivers: list[Receiver]
) -> None:
    erp = await test_app.integration_client(["organizations:read", "opportunities:read"])
    sink = Receiver([])
    receivers.append(sink)
    created = await subscribe(test_app, erp.client_id, sink.url)
    sink.secrets.append(created["secret"])
    rep, _ = await test_app.signed_in()
    await create_opp(rep)
    await run_worker(test_app, real_now())
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    log = (await admin.get("/api/v1/webhook-deliveries", params={"page_size": 1})).json()
    assert (log["total"], len(log["items"]), log["page_size"]) == (2, 1, 1)
    only = (
        await admin.get(
            "/api/v1/webhook-deliveries",
            params={"event_type": "opportunity.created", "client_id": str(erp.client_id)},
        )
    ).json()
    [item] = only["items"]
    assert (item["status"], item["client_id"]) == ("succeeded", str(erp.client_id))
    failed = await admin.get("/api/v1/webhook-deliveries", params={"status": "failed"})
    assert failed.json()["total"] == 0
    assert (
        await admin.get("/api/v1/webhook-deliveries", params={"status": "x"})
    ).status_code == 422

    again = await admin.post(f"/api/v1/webhook-deliveries/{item['id']}/redeliver")
    assert again.status_code == 202, again.text
    assert again.json()["id"] != item["id"]
    assert again.json()["event_id"] == item["event_id"]
    await run_worker(test_app, real_now())
    # The receiver deduplicates on the event ID: same event, handled once.
    assert [e["type"] for e in sink.events].count("opportunity.created") == 1
    assert len(await test_app.audit("webhook_delivery.redelivered")) == 1
    missing = "01930000-0000-7000-8000-000000000999"
    assert (await admin.get(f"/api/v1/webhook-deliveries/{missing}")).status_code == 404


async def test_FR_INT_07_old_events_are_purged(test_app: TestApp) -> None:
    erp = await test_app.integration_client(["organizations:read"])
    await subscribe(test_app, erp.client_id, "https://hooks.example.test/a")
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    async with test_app.sessions() as session:
        await webhooks.dispatch(session, test_app.clock.now())
    async with test_app.sessions() as session:
        kept = await webhooks.purge(session, test_app.clock.now() + timedelta(days=29))
        removed = await webhooks.purge(session, test_app.clock.now() + timedelta(days=31))
    assert (kept, removed) == ({"outbox_events": 0}, {"outbox_events": 1})
    async with test_app.sessions() as session:
        assert (await session.execute(select(func.count(WebhookDelivery.id)))).scalar_one() == 0


# --- Network guard (unit) -----------------------------------------------------------------------


def test_FR_INT_07_AC5_host_and_url_rules() -> None:
    patterns = ("erp.internal", "*.billing.internal")
    assert netguard.host_allowed("ERP.internal.", patterns)
    assert netguard.host_allowed("api.billing.internal", patterns)
    assert not netguard.host_allowed("billing.internal", patterns)
    assert not netguard.host_allowed("erp.internal.evil.test", patterns)
    prod = Settings(
        env=Environment.PRODUCTION,
        app_secret_key="x" * 48,
        app_encryption_key="y" * 48,
        database_url="postgresql+asyncpg://crm_app:real@db:5432/crm",  # type: ignore[arg-type]
        webhook_allowed_hosts="erp.internal",
    )
    assert netguard.url_allowed("https://erp.internal:8443/hooks", prod)
    assert not netguard.url_allowed("http://erp.internal/hooks", prod)
    assert not netguard.url_allowed("https://erp.internal:99999/hooks", prod)
    dev = prod.model_copy(update={"env": Environment.DEVELOPMENT})
    assert netguard.url_allowed("http://erp.internal/hooks", dev)
    assert not netguard.url_allowed("https://erp.internal/hooks", Settings())


@pytest.mark.parametrize(
    ("address", "allowed"),
    [
        ("10.1.2.3", True),
        ("192.168.5.5", True),
        ("203.0.113.10", True),
        ("127.0.0.1", False),
        ("::1", False),
        ("169.254.169.254", False),
        ("fd00:ec2::254", False),
        ("100.100.100.200", False),
        ("0.0.0.0", False),  # noqa: S104 - an address under test, not a bind
        ("224.0.0.1", False),
        ("::ffff:127.0.0.1", False),
        ("fe80::1", False),
    ],
)
def test_FR_INT_07_AC5_address_rules(address: str, allowed: bool) -> None:
    import ipaddress

    assert netguard.address_allowed(ipaddress.ip_address(address)) is allowed


def test_FR_INT_10_reference_receiver_verifies_signatures() -> None:
    body = b'{"id":"evt_1"}'
    header = webhooks.sign(["whsec_a"], 1_763_380_000, body)
    verify = receiver.verify_signature
    assert verify(["whsec_a"], header, body, now=1_763_380_100)
    assert not verify(["whsec_b"], header, body, now=1_763_380_100)
    assert not verify(["whsec_a"], header, body + b" ", now=1_763_380_100)
    assert not verify(["whsec_a"], header, body, now=1_763_380_000 + 301)  # replay window
    assert not verify(["whsec_a"], "v1=abc", body, now=1_763_380_000)
    assert not verify(["whsec_a"], "", body)


async def test_NFR_13_worker_job_dispatches_and_attempts_on_each_poll(
    test_app: TestApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import worker

    monkeypatch.setattr(worker, "get_settings", lambda: test_app.app.state.settings)
    erp = await test_app.integration_client(["organizations:read"])
    # On the allowlist but not resolvable: the attempt is made and recorded.
    await subscribe(test_app, erp.client_id, "https://nowhere.erp.example.test/hooks")
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    await worker.deliver_webhooks(test_app.app.state.engine)
    [delivery] = await deliveries(test_app)
    assert (delivery.status, delivery.attempt_count, delivery.last_error) == (
        "retrying",
        1,
        "dns_failed",
    )
