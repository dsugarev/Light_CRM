"""Phase 6 exit (implementation plan): a test client using only an API key syncs
organizations with `updated_since`, receives a signed `opportunity.closed_won` webhook,
writes back an ERP external reference, and is refused every endpoint outside its
scopes (here a sample; every route is covered by the integration scope matrix).

The client has the ERP profile of API spec 19.9; the webhook goes to the reference
receiver (`deploy/examples/webhook_receiver.py`) over a real HTTP connection.
"""

from typing import Any

import pytest

from app.core.config import Settings
from app.core.principal import RoleCode
from app.modules.integration.service import PROFILES
from tests.api.test_opportunities import act, create_opp
from tests.api.test_webhooks import Receiver, real_now, run_worker
from tests.helpers import TestApp


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"webhook_allowed_hosts": "127.0.0.1"})


async def test_phase_6_exit_erp_round_trip(test_app: TestApp) -> None:
    owner = await test_app.create_user()
    _, scopes = PROFILES["erp"]
    erp = await test_app.integration_client(scopes, default_owner_id=owner.id)
    sink = Receiver([])
    try:
        admin, _ = await test_app.signed_in(RoleCode.ADMIN)
        created = await admin.post(
            f"/api/v1/integration-clients/{erp.client_id}/webhook-subscriptions",
            json={"url": sink.url, "event_types": ["opportunity.closed_won"]},
        )
        assert created.status_code == 201, created.text
        sink.secrets.append(created.json()["secret"])

        # A sales rep wins a deal in the CRM.
        rep, _ = await test_app.signed_in()
        opp = await create_opp(rep, amount="25000.00")
        assert (await act(rep, opp, "close", outcome="won")).status_code == 200
        await run_worker(test_app, real_now())

        # 1. The signed webhook arrives (the receiver verified the signature).
        [event] = sink.events
        assert event["type"] == "opportunity.closed_won"
        won: dict[str, Any] = event["data"]["object"]
        assert won["stage"]["stage_type"] == "won"
        assert event["data"]["version"] == won["version"]
        org_id = won["organization"]["id"]

        # 2. ERP reads the organization (the key only) and writes back its customer number.
        assert (await erp.http.get(f"/api/v1/organizations/{org_id}")).status_code == 200
        put = await erp.http.put(
            f"/api/v1/organizations/{org_id}/external-references/erp",
            json={"external_id": "C-100234", "url": "https://erp.example.test/customers/C-100234"},
        )
        assert put.status_code == 200, put.text
        found = await erp.http.get(
            "/api/v1/organizations",
            params={"external_system": "erp", "external_id": "C-100234"},
        )
        assert [o["id"] for o in found.json()["items"]] == [org_id]

        # 3. Sync mode: the organization, changed by the reference, is in the feed.
        page = await erp.http.get(
            "/api/v1/organizations",
            params={"updated_since": "2000-01-01T00:00:00Z", "page_size": 500},
        )
        assert page.status_code == 200
        assert org_id in [o["id"] for o in page.json()["items"]]

        # 4. Everything outside the profile is refused.
        refused = [
            ("GET", "/api/v1/leads"),
            ("GET", "/api/v1/activities"),
            ("POST", "/api/v1/organizations"),
            ("PUT", f"/api/v1/organizations/{org_id}/external-references/billing"),
            ("GET", "/api/v1/users"),
            ("GET", "/api/v1/audit-log"),
            ("GET", "/api/v1/organizations/export"),
            ("GET", "/api/v1/imports"),
            ("GET", "/api/v1/integration-clients"),
            ("GET", "/api/v1/webhook-deliveries"),
            ("GET", "/api/v1/reports/dashboard"),
        ]
        for method, path in refused:
            body = {"external_id": "B-1"} if method == "PUT" else {"name": "X"}
            response = await erp.http.request(
                method, path, json=body if method in ("POST", "PUT") else None
            )
            assert response.status_code == 403, (method, path, response.text)
    finally:
        sink.close()
