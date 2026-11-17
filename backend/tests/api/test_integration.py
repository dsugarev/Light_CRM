"""Integration clients, API keys, scopes, external references, idempotency and usage
(FR-INT-01..06, 08, 09; API spec 19). Fictional data only."""

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.principal import RoleCode
from app.modules.identity.models import User
from app.modules.integration.models import ApiKey
from tests.api.test_opportunities import create_org
from tests.helpers import TestApp

ORG_READ = ["organizations:read"]


# --- FR-INT-01 clients and service users -----------------------------------------------------


async def test_FR_INT_01_admin_registers_a_client_backed_by_a_service_user(
    test_app: TestApp,
) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    owner = await test_app.create_user()
    response = await admin.post(
        "/api/v1/integration-clients",
        json={
            "name": "ERP",
            "system": "erp",
            "scopes": ["organizations:read", "external-references:write"],
            "default_owner_id": str(owner.id),
            "ip_allowlist": ["10.1.2.0/24"],
            "technical_contact": "erp-team@example.test",
            "rate_limit_per_minute": 120,
        },
    )
    assert response.status_code == 201, response.text
    client = response.json()
    assert client["system"]["code"] == "erp"
    assert client["scopes"] == ["external-references:write", "organizations:read"]
    assert client["default_owner"]["id"] == str(owner.id)
    assert (client["is_active"], client["active_keys"], client["usage"]) == (
        True,
        0,
        {"requests_24h": 0, "errors_24h": 0},
    )
    async with test_app.sessions() as session:
        service_users = list(
            (await session.execute(select(User).where(User.user_type == "service"))).scalars()
        )
    [service_user] = service_users
    assert service_user.full_name == "ERP (integration)"
    assert service_user.password_hash is None
    # Service users never appear among people or as possible owners.
    users = (await admin.get("/api/v1/users")).json()
    assert all(u["id"] != str(service_user.id) for u in users["items"])
    [entry] = await test_app.audit("integration_client.created")
    assert entry.actor_id == admin_user.id
    bad = await admin.post(
        "/api/v1/integration-clients", json={"name": "X", "system": "crm-unknown"}
    )
    assert bad.json()["errors"] == [{"field": "system", "code": "reference.invalid"}]
    bad = await admin.post(
        "/api/v1/integration-clients",
        json={"name": "X", "system": "erp", "scopes": ["users:manage"], "ip_allowlist": ["x"]},
    )
    assert {e["field"] for e in bad.json()["errors"]} == {"scopes.0", "ip_allowlist.0"}


async def test_FR_INT_01_AC1_deactivated_client_is_refused(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    erp = await test_app.integration_client(ORG_READ)
    assert (await erp.http.get("/api/v1/organizations")).status_code == 200
    await admin.post(f"/api/v1/integration-clients/{erp.client_id}/deactivate")
    response = await erp.http.get("/api/v1/organizations")
    assert (response.status_code, response.json()["code"]) == (401, "auth.client_inactive")
    await admin.post(f"/api/v1/integration-clients/{erp.client_id}/activate")
    assert (await erp.http.get("/api/v1/organizations")).status_code == 200
    actions = [e.action for e in await test_app.audit() if e.entity_type == "integration_client"]
    assert actions[-2:] == ["integration_client.deactivated", "integration_client.activated"]


async def test_FR_INT_01_AC2_client_is_the_actor_of_its_changes(test_app: TestApp) -> None:
    owner = await test_app.create_user(full_name="Ivan Owner")
    erp = await test_app.integration_client(
        ["organizations:read", "organizations:write"], default_owner_id=owner.id
    )
    response = await erp.http.post("/api/v1/organizations", json={"name": "Интеграция ООД"})
    assert response.status_code == 201, response.text
    org = response.json()
    assert org["owner"] == {"id": str(owner.id), "full_name": "Ivan Owner"}
    assert org["created_by"]["full_name"] == "ERP (integration)"
    [entry] = await test_app.audit("organization.created")
    assert entry.actor_id == erp.service_user_id
    me = (await erp.http.get("/api/v1/me")).json()
    assert (me["principal_type"], me["full_name"], me["system"], me["scopes"]) == (
        "integration",
        "ERP (integration)",
        "erp",
        ["organizations:read", "organizations:write"],
    )


# --- FR-INT-02 API keys --------------------------------------------------------------------------


async def test_FR_INT_02_key_is_shown_once_and_only_its_hash_is_stored(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    erp = await test_app.integration_client(ORG_READ)
    response = await admin.post(
        f"/api/v1/integration-clients/{erp.client_id}/api-keys", json={"label": "rotation"}
    )
    assert response.status_code == 201, response.text
    created = response.json()
    key = created["key"]
    assert key.startswith(f"{created['prefix']}_")
    assert created["prefix"].startswith("crm_test_")
    assert created["expires_at"] == "2027-11-17T09:00:00Z"  # 12 months by default
    secret = key.rsplit("_", 1)[-1] if key.count("_") == 3 else key[len(created["prefix"]) + 1 :]
    listed = (await admin.get(f"/api/v1/integration-clients/{erp.client_id}/api-keys")).json()
    assert all("key" not in k for k in listed)
    assert {k["label"] for k in listed} == {"test", "rotation"}
    async with test_app.sessions() as session:
        stored = (await session.execute(select(ApiKey))).scalars().all()
    assert all(secret not in (k.secret_hash, k.key_id) for k in stored)
    # AC3: never in audit entries.
    audit_text = json.dumps(
        [(e.before, e.after, e.details) for e in await test_app.audit()], default=str
    )
    assert secret not in audit_text
    new_client = test_app.client(csrf=False, headers={"Authorization": f"Bearer {key}"})
    assert (await new_client.get("/api/v1/organizations")).status_code == 200


async def test_FR_INT_02_AC2_rotation_limit_expiry_and_revocation(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    erp = await test_app.integration_client(ORG_READ)
    path = f"/api/v1/integration-clients/{erp.client_id}/api-keys"
    second = (await admin.post(path, json={"label": "second"})).json()
    third = await admin.post(path, json={"label": "third"})
    assert (third.status_code, third.json()["code"]) == (409, "api_key.limit")
    too_long = await admin.post(path, json={"label": "x", "expires_at": "2029-01-01T00:00:00Z"})
    assert too_long.json()["errors"] == [{"field": "expires_at", "code": "api_key.expiry_too_long"}]
    past = await admin.post(path, json={"label": "x", "expires_at": "2026-01-01T00:00:00Z"})
    assert past.json()["errors"] == [{"field": "expires_at", "code": "api_key.expiry_past"}]
    # Revocation takes effect on the next request; the other key keeps working.
    assert (await admin.delete(f"{path}/{second['id']}")).status_code == 204
    revoked = test_app.client(csrf=False, headers={"Authorization": f"Bearer {second['key']}"})
    response = await revoked.get("/api/v1/organizations")
    assert (response.status_code, response.json()["code"]) == (401, "auth.api_key_invalid")
    assert (await erp.http.get("/api/v1/organizations")).status_code == 200
    # Expiry.
    test_app.clock.advance(timedelta(days=366))
    response = await erp.http.get("/api/v1/organizations")
    assert response.json()["code"] == "auth.api_key_invalid"


async def test_FR_INT_02_malformed_and_mixed_credentials(test_app: TestApp) -> None:
    erp = await test_app.integration_client(ORG_READ)
    for header in ("Bearer nope", f"Basic {erp.key}", f"Bearer {erp.key[:-1]}x"):
        client = test_app.client(csrf=False, headers={"Authorization": header})
        response = await client.get("/api/v1/organizations")
        assert (response.status_code, response.json()["code"]) == (401, "auth.api_key_invalid")
    rep, _ = await test_app.signed_in()
    response = await rep.get(
        "/api/v1/organizations", headers={"Authorization": f"Bearer {erp.key}"}
    )
    assert (response.status_code, response.json()["code"]) == (400, "auth.mixed_credentials")


async def test_FR_INT_02_ip_allowlist(test_app: TestApp) -> None:
    outside = await test_app.integration_client(ORG_READ, ip_allowlist=["10.0.0.0/8"])
    response = await outside.http.get("/api/v1/organizations")
    assert (response.status_code, response.json()["code"]) == (403, "auth.ip_not_allowed")
    inside = await test_app.integration_client(
        ORG_READ, system="billing", name="Billing", ip_allowlist=["127.0.0.0/8"]
    )
    assert (await inside.http.get("/api/v1/organizations")).status_code == 200


async def test_FR_INT_02_last_use_is_recorded(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    erp = await test_app.integration_client(ORG_READ)
    await erp.http.get("/api/v1/organizations")
    [key] = (await admin.get(f"/api/v1/integration-clients/{erp.client_id}/api-keys")).json()
    assert key["last_used_at"] == "2026-11-17T09:00:00Z"
    assert key["last_used_ip"] == "127.0.0.1"


# --- FR-INT-03 scopes and owners (the full route matrix is in test_authorization_matrix) ------


async def test_FR_INT_03_AC1_AC2_scopes_and_refused_areas(test_app: TestApp) -> None:
    erp = await test_app.integration_client(ORG_READ)
    response = await erp.http.get("/api/v1/contacts")
    assert response.status_code == 403
    assert response.json() | {"request_id": None, "type": None, "title": None} == {
        "code": "permission.scope_missing",
        "required_scope": "contacts:read",
        "status": 403,
        "request_id": None,
        "type": None,
        "title": None,
    }
    for method, path in (
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/settings"),
        ("GET", "/api/v1/audit-log"),
        ("GET", "/api/v1/imports"),
        ("GET", "/api/v1/organizations/export"),
        ("GET", "/api/v1/integration-clients"),
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/me/sessions"),
        ("GET", "/api/v1/me/tasks"),
    ):
        response = await erp.http.request(method, path, json={} if method == "POST" else None)
        assert response.json()["code"] == "permission.not_for_integrations", path


async def test_FR_INT_03_AC3_no_archive_assign_convert_or_owner_change(test_app: TestApp) -> None:
    owner = await test_app.create_user()
    other = await test_app.create_user()
    erp = await test_app.integration_client(
        ["organizations:read", "organizations:write"], default_owner_id=owner.id
    )
    org = (await erp.http.post("/api/v1/organizations", json={"name": "Делта АД"})).json()
    response = await erp.http.delete(f"/api/v1/organizations/{org['id']}")
    assert response.json()["code"] == "permission.not_for_integrations"
    response = await erp.http.patch(
        f"/api/v1/organizations/{org['id']}", json={"owner_id": str(other.id)}
    )
    assert (response.status_code, response.json()["code"]) == (403, "permission.denied")
    response = await erp.http.patch(f"/api/v1/organizations/{org['id']}", json={"city": "Русе"})
    assert response.json()["city"] == "Русе"


async def test_FR_INT_03_AC4_created_records_need_a_human_owner(test_app: TestApp) -> None:
    owner = await test_app.create_user()
    erp = await test_app.integration_client(
        ["organizations:write", "leads:write", "opportunities:write"]
    )
    response = await erp.http.post("/api/v1/organizations", json={"name": "Без Собственик ООД"})
    assert (response.status_code, response.json()["code"]) == (422, "owner.required")
    response = await erp.http.post(
        "/api/v1/organizations", json={"name": "Със Собственик ООД", "owner_id": str(owner.id)}
    )
    assert response.status_code == 201
    response = await erp.http.post("/api/v1/leads", json={"title": "Lead", "company_name": "Ета"})
    assert response.json()["code"] == "owner.required"


async def test_FR_INT_03_search_is_limited_to_readable_types(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    await create_org(rep, "Сигма ЕООД")
    await rep.post("/api/v1/contacts", json={"first_name": "Сигма", "last_name": "Контакт"})
    erp = await test_app.integration_client(ORG_READ)
    items = (await erp.http.get("/api/v1/search?q=sigma")).json()["items"]
    assert {i["type"] for i in items} == {"organization"}


async def test_FR_INT_03_activities_patch_only_own(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    theirs = (
        await rep.post(
            "/api/v1/activities",
            json={"type": "note", "subject": "By a person", "organization_id": org["id"]},
        )
    ).json()
    owner = await test_app.create_user()
    erp = await test_app.integration_client(
        ["activities:read", "activities:write"], default_owner_id=owner.id
    )
    mine = await erp.http.post(
        "/api/v1/activities",
        json={"type": "note", "subject": "From ERP", "organization_id": org["id"]},
    )
    assert mine.status_code == 201, mine.text
    ok = await erp.http.patch(
        f"/api/v1/activities/{mine.json()['id']}", json={"version": 1, "subject": "Edited"}
    )
    assert ok.status_code == 200
    refused = await erp.http.patch(
        f"/api/v1/activities/{theirs['id']}", json={"version": 1, "subject": "Edited"}
    )
    assert (refused.status_code, refused.json()["code"]) == (403, "permission.denied")


# --- FR-INT-04 external references ------------------------------------------------------------


async def test_FR_INT_04_client_writes_its_own_system_and_finds_records(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep, "Акме ЕООД")
    other = await create_org(rep, "Бета АД")
    erp = await test_app.integration_client(["organizations:read", "external-references:write"])
    path = f"/api/v1/organizations/{org['id']}/external-references"
    response = await erp.http.put(
        f"{path}/erp",
        json={"external_id": "C-10023", "url": "https://erp.example.test/customers/C-10023"},
    )
    assert response.status_code == 200, response.text
    assert response.json() | {"updated_at": None} == {
        "entity_type": "organization",
        "entity_id": org["id"],
        "system": response.json()["system"],
        "external_id": "C-10023",
        "url": "https://erp.example.test/customers/C-10023",
        "updated_at": None,
        "updated_by": {"id": str(erp.service_user_id), "full_name": "ERP (integration)"},
    }
    # AC1: the same ERP number on another organization is refused.
    taken = await erp.http.put(
        f"/api/v1/organizations/{other['id']}/external-references/erp",
        json={"external_id": "C-10023"},
    )
    assert (taken.status_code, taken.json()["code"]) == (409, "external_reference.conflict")
    assert taken.json()["entity_id"] == org["id"]
    # AC2: not another system's references.
    foreign = await erp.http.put(f"{path}/billing", json={"external_id": "B-1"})
    assert (foreign.status_code, foreign.json()["code"]) == (
        403,
        "external_reference.system_mismatch",
    )
    # AC3: resolve by external ID, and list filters.
    found = await erp.http.get("/api/v1/external-references?system=erp&external_id=C-10023")
    assert found.json()["entity_id"] == org["id"]
    missing = await erp.http.get("/api/v1/external-references?system=erp&external_id=nope")
    assert missing.status_code == 404
    linked = (await erp.http.get("/api/v1/organizations?external_system=erp")).json()
    assert [o["id"] for o in linked["items"]] == [org["id"]]
    unlinked = (
        await erp.http.get("/api/v1/organizations?external_system=erp&has_external_reference=false")
    ).json()
    assert [o["id"] for o in unlinked["items"]] == [other["id"]]
    by_id = (
        await erp.http.get("/api/v1/organizations?external_system=erp&external_id=C-10023")
    ).json()
    assert by_id["total"] == 1
    bad = await erp.http.get("/api/v1/organizations?has_external_reference=false")
    assert bad.status_code == 400
    listed = (await rep.get(path)).json()
    assert [r["external_id"] for r in listed] == ["C-10023"]
    [entry] = await test_app.audit("external_reference.updated")
    assert entry.details == {"system": "erp"}
    # Removal by the client, then the Admin may write any system.
    assert (await erp.http.delete(f"{path}/erp")).status_code == 204
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.put(f"{path}/billing", json={"external_id": "B-77"})
    assert response.status_code == 200
    assert (await rep.put(f"{path}/billing", json={"external_id": "B-1"})).status_code == 403


async def test_FR_INT_04_reference_rules(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    org = await create_org(admin)
    path = f"/api/v1/organizations/{org['id']}/external-references"
    insecure = await admin.put(f"{path}/erp", json={"external_id": "1", "url": "http://x.test"})
    assert insecure.json()["errors"] == [{"field": "url", "code": "validation.value_error"}]
    unknown = await admin.put(f"/api/v1/organizations/{uuid4()}/external-references/erp",
                              json={"external_id": "1"})  # fmt: skip
    assert unknown.status_code == 404
    assert (await admin.put(f"{path}/nosuch", json={"external_id": "1"})).status_code == 404
    # A client cannot resolve references of record types it may not read.
    await admin.put(f"{path}/erp", json={"external_id": "X-1"})
    contacts_only = await test_app.integration_client(["contacts:read"])
    response = await contacts_only.http.get(
        "/api/v1/external-references?system=erp&external_id=X-1"
    )
    assert (response.status_code, response.json()["code"]) == (403, "permission.scope_missing")


# --- FR-INT-05 sync, FR-INT-06 idempotency, FR-INT-08 usage, FR-INT-09 rate limit -------------


async def test_FR_INT_05_sync_with_an_api_key(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    for name in ("Едно ООД", "Две ООД", "Три ООД"):
        await create_org(rep, name)
    erp = await test_app.integration_client(ORG_READ)
    response = await erp.http.get(
        "/api/v1/organizations",
        params={"updated_since": "2000-01-01T00:00:00Z", "page_size": 2},
    )
    page = response.json()
    assert set(page) == {"items", "next_cursor"}
    rest = await erp.http.get(
        "/api/v1/organizations",
        params={"updated_since": "2000-01-01T00:00:00Z", "page_size": 2,
                "cursor": page["next_cursor"]},
    )  # fmt: skip
    assert len(page["items"]) + len(rest.json()["items"]) == 3


async def test_FR_INT_06_idempotent_creation(test_app: TestApp) -> None:
    owner = await test_app.create_user()
    erp = await test_app.integration_client(
        ["organizations:read", "organizations:write"], default_owner_id=owner.id
    )
    body = {"name": "Идемпотентна ООД"}
    headers = {"Idempotency-Key": "erp-customer-10023"}
    first = await erp.http.post("/api/v1/organizations", json=body, headers=headers)
    assert first.status_code == 201, first.text
    again = await erp.http.post("/api/v1/organizations", json=body, headers=headers)
    assert again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.headers["location"] == first.headers["location"]
    reused = await erp.http.post(
        "/api/v1/organizations", json={"name": "Друга ООД"}, headers=headers
    )
    assert (reused.status_code, reused.json()["code"]) == (422, "idempotency.key_reused")
    listing = (await erp.http.get("/api/v1/organizations")).json()
    assert listing["total"] == 1
    other = await erp.http.post(
        "/api/v1/organizations", json={"name": "Друга ООД"}, headers={"Idempotency-Key": "k2"}
    )
    assert other.status_code == 201
    # Kept 24 hours.
    test_app.clock.advance(timedelta(hours=25))
    after = await erp.http.post(
        "/api/v1/organizations", json={"name": "Трета ООД"}, headers=headers
    )
    assert after.status_code == 201
    assert "Idempotent-Replayed" not in after.headers


async def test_FR_INT_08_usage_counters(test_app: TestApp) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    erp = await test_app.integration_client(ORG_READ)
    for _ in range(3):
        await erp.http.get("/api/v1/organizations")
    await erp.http.get("/api/v1/contacts")  # 403: an error
    client = (await admin.get(f"/api/v1/integration-clients/{erp.client_id}")).json()
    assert client["usage"] == {"requests_24h": 4, "errors_24h": 1}
    assert client["last_used_at"] == "2026-11-17T09:00:00Z"
    test_app.clock.advance(timedelta(hours=25))
    admin = await test_app.session_client(admin_user)  # the earlier session has expired
    client = (await admin.get(f"/api/v1/integration-clients/{erp.client_id}")).json()
    assert client["usage"] == {"requests_24h": 0, "errors_24h": 0}


async def test_FR_INT_09_rate_limit_per_client(test_app: TestApp) -> None:
    erp = await test_app.integration_client(ORG_READ, rate_limit_per_minute=2)
    statuses = [(await erp.http.get("/api/v1/organizations")).status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    response = await erp.http.get("/api/v1/organizations")
    assert response.json()["code"] == "rate_limit.exceeded"
    assert int(response.headers["Retry-After"]) >= 1
    # Another client has its own budget.
    billing = await test_app.integration_client(ORG_READ, system="billing", name="Billing")
    assert (await billing.http.get("/api/v1/organizations")).status_code == 200


async def test_FR_INT_01_admin_updates_a_client(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    erp = await test_app.integration_client(ORG_READ)
    response = await admin.patch(
        f"/api/v1/integration-clients/{erp.client_id}",
        json={"name": "ERP Prod", "scopes": ["organizations:read", "contacts:read"]},
    )
    assert response.json()["scopes"] == ["contacts:read", "organizations:read"]
    assert (await erp.http.get("/api/v1/contacts")).status_code == 200
    me = (await erp.http.get("/api/v1/me")).json()
    assert me["full_name"] == "ERP Prod (integration)"
    assert (await admin.get(f"/api/v1/integration-clients/{uuid4()}")).status_code == 404
    [entry] = await test_app.audit("integration_client.updated")
    assert entry.after is not None
    assert entry.after["name"] == "ERP Prod"


async def test_FR_INT_01_cli_creates_the_initial_profiles_inactive(
    test_app: TestApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import cli

    monkeypatch.setattr(cli, "get_settings", lambda: test_app.app.state.settings)
    assert await cli.create_integration_clients(["erp", "billing", "conclusion"]) == 0
    assert await cli.create_integration_clients(["erp"]) == 0  # existing one is skipped
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    clients = {
        c["system"]["code"]: c for c in (await admin.get("/api/v1/integration-clients")).json()
    }
    assert set(clients) == {"erp", "billing", "conclusion"}
    assert all(not c["is_active"] and c["active_keys"] == 0 for c in clients.values())
    assert clients["conclusion"]["scopes"] == [
        "external-references:write", "opportunities:read", "organizations:read", "reference:read",
    ]  # fmt: skip


async def test_FR_INT_06_idempotency_edge_cases(test_app: TestApp) -> None:
    owner = await test_app.create_user()
    erp = await test_app.integration_client(["organizations:write"], default_owner_id=owner.id)
    long_key = await erp.http.post(
        "/api/v1/organizations", json={"name": "X"}, headers={"Idempotency-Key": "k" * 256}
    )
    assert long_key.status_code == 422
    assert long_key.json()["errors"] == [
        {"field": "Idempotency-Key", "code": "validation.string_too_long"}
    ]
    stranger = test_app.client(
        csrf=False,
        headers={"Authorization": f"Bearer {erp.key[:-1]}x", "Idempotency-Key": "k1"},
    )
    refused = await stranger.post("/api/v1/organizations", json={"name": "X"})
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.api_key_invalid")
    # A validation error is replayed as well (same key, same body, same answer).
    headers = {"Idempotency-Key": "k-invalid"}
    first = await erp.http.post("/api/v1/organizations", json={}, headers=headers)
    second = await erp.http.post("/api/v1/organizations", json={}, headers=headers)
    assert first.status_code == second.status_code == 422
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.headers["content-type"] == "application/problem+json"
