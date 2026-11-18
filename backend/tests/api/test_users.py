"""User administration (FR-ADM-01, FR-AUTH-02; API spec section 5)."""

import asyncio
from uuid import uuid4

from app.core.principal import RoleCode
from tests.helpers import TestApp

NEW_USER = {"email": "Petar.Testov@Example.TEST", "full_name": "Petar Testov", "role": "sales_rep"}


async def test_FR_ADM_01_admin_creates_user_with_one_time_link(test_app: TestApp) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.post("/api/v1/users", json={**NEW_USER, "locale": "bg"})
    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"/api/v1/users/{body['user']['id']}"
    assert body["user"]["email"] == "petar.testov@example.test"
    assert body["user"]["role"] == "sales_rep"
    assert body["user"]["locale"] == "bg"
    assert body["user"]["is_active"] is True
    assert body["set_password"]["url"].startswith("https://crm.example.test/set-password#token=")
    assert body["set_password"]["emailed"] is False
    [entry] = await test_app.audit("user.created")
    assert entry.actor_id == admin_user.id
    assert entry.after is not None
    assert entry.after["email"] == "petar.testov@example.test"
    assert "password_hash" not in entry.after


async def test_FR_AUTH_02_link_is_emailed_when_smtp_is_configured(test_app: TestApp) -> None:
    test_app.mailer.enabled = True
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.post("/api/v1/users", json=NEW_USER)
    assert response.json()["set_password"]["emailed"] is True
    [email] = test_app.mailer.sent
    assert email.to == "petar.testov@example.test"
    assert response.json()["set_password"]["url"] in email.body


async def test_duplicate_email_is_rejected_case_insensitively(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    assert (await admin.post("/api/v1/users", json=NEW_USER)).status_code == 201
    again = await admin.post(
        "/api/v1/users", json={**NEW_USER, "email": "PETAR.TESTOV@example.test"}
    )
    assert again.status_code == 409
    assert again.json()["code"] == "conflict.duplicate"
    assert again.json()["errors"] == [{"field": "email", "code": "user.email_taken"}]


async def test_create_user_validates_fields(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.post(
        "/api/v1/users", json={"email": "not-an-email", "full_name": "", "role": "integration"}
    )
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {"email", "full_name", "role"}


async def test_list_filter_and_detail(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN, full_name="Ada Admin")
    await test_app.create_user(RoleCode.SALES_REP, full_name="Boris Rep")
    await test_app.create_user(RoleCode.VIEWER, full_name="Vera Viewer", is_active=False)
    await test_app.create_user(RoleCode.INTEGRATION, user_type="service", full_name="ERP")

    everyone = (await admin.get("/api/v1/users")).json()
    assert [u["full_name"] for u in everyone["items"]] == ["Ada Admin", "Boris Rep", "Vera Viewer"]
    assert everyone["total"] == 3

    reps = (await admin.get("/api/v1/users", params={"role": "sales_rep"})).json()
    assert [u["full_name"] for u in reps["items"]] == ["Boris Rep"]
    active = (await admin.get("/api/v1/users", params={"is_active": "true", "q": "v"})).json()
    assert active["items"] == []
    page = (await admin.get("/api/v1/users", params={"page": 2, "page_size": 2})).json()
    assert [u["full_name"] for u in page["items"]] == ["Vera Viewer"]

    vera_id = everyone["items"][2]["id"]
    detail = await admin.get(f"/api/v1/users/{vera_id}")
    assert detail.json()["is_active"] is False
    assert (await admin.get(f"/api/v1/users/{uuid4()}")).status_code == 404


async def test_lookup_lists_active_humans_for_every_signed_in_user(test_app: TestApp) -> None:
    viewer, _ = await test_app.signed_in(RoleCode.VIEWER, full_name="Vera Viewer")
    rep = await test_app.create_user(full_name="Boris Rep", email="boris@example.test")
    await test_app.create_user(full_name="Gone User", is_active=False)
    await test_app.create_user(RoleCode.INTEGRATION, user_type="service", full_name="ERP")

    names = [u["full_name"] for u in (await viewer.get("/api/v1/users/lookup")).json()["items"]]
    assert names == ["Boris Rep", "Vera Viewer"]
    by_email = await viewer.get("/api/v1/users/lookup", params={"email": "BORIS@example.test"})
    assert by_email.json()["items"] == [
        {"id": str(rep.id), "full_name": "Boris Rep", "email": "boris@example.test"}
    ]
    search = await viewer.get("/api/v1/users/lookup", params={"q": "100%_"})
    assert search.json()["items"] == []


async def test_FR_ADM_03_role_change_is_audited_with_before_and_after(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    rep = await test_app.create_user()
    response = await admin.patch(
        f"/api/v1/users/{rep.id}", json={"role": "sales_manager", "full_name": "Promoted Rep"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "sales_manager"
    [entry] = await test_app.audit("user.role_changed")
    assert entry.before is not None
    assert entry.after is not None
    assert entry.before["role"] == "sales_rep"
    assert entry.after["role"] == "sales_manager"
    assert entry.after["full_name"] == "Promoted Rep"


async def test_update_rejects_taken_email(test_app: TestApp) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    rep = await test_app.create_user()
    response = await admin.patch(f"/api/v1/users/{rep.id}", json={"email": admin_user.email})
    assert response.status_code == 409


async def test_last_admin_cannot_be_demoted_or_deactivated(test_app: TestApp) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    demote = await admin.patch(f"/api/v1/users/{admin_user.id}", json={"role": "viewer"})
    assert demote.status_code == 409
    assert demote.json()["code"] == "permission.last_admin"

    other_admin = await test_app.create_user(RoleCode.ADMIN)
    assert (
        await admin.patch(f"/api/v1/users/{other_admin.id}", json={"role": "viewer"})
    ).status_code == 200


async def test_admin_cannot_deactivate_themselves(test_app: TestApp) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    await test_app.create_user(RoleCode.ADMIN)
    response = await admin.post(f"/api/v1/users/{admin_user.id}/deactivate")
    assert response.status_code == 403


async def test_FR_ADM_01_deactivation_ends_sessions_and_keeps_the_user(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    rep_client, rep = await test_app.signed_in()
    response = await admin.post(f"/api/v1/users/{rep.id}/deactivate")
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert (await rep_client.get("/api/v1/me")).status_code == 401
    assert (await test_app.login(test_app.client(), rep.email)).status_code == 401
    assert await test_app.audit("user.deactivated")

    activated = await admin.post(f"/api/v1/users/{rep.id}/activate")
    assert activated.json()["is_active"] is True
    assert (await test_app.login(test_app.client(), rep.email)).status_code == 200
    assert await test_app.audit("user.activated")


async def test_admin_issues_password_reset_link(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    rep = await test_app.create_user()
    response = await admin.post(f"/api/v1/users/{rep.id}/password-reset")
    assert response.status_code == 200
    token = response.json()["url"].split("#token=")[1]
    check = await test_app.client().get(f"/api/v1/auth/password/token/{token}")
    assert check.json()["purpose"] == "reset"
    assert await test_app.audit("user.password_reset_issued")


async def test_password_reset_for_inactive_user_is_refused(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    rep = await test_app.create_user(is_active=False)
    response = await admin.post(f"/api/v1/users/{rep.id}/password-reset")
    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "user_id", "code": "user.inactive"}]


async def test_FR_AUTH_01_admin_unlocks_an_account(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    rep = await test_app.create_user()
    client = test_app.client()
    for _ in range(5):
        await test_app.login(client, rep.email, "Wrong-Password-123")
    listed = (await admin.get(f"/api/v1/users/{rep.id}")).json()
    assert listed["is_locked"] is True
    response = await admin.post(f"/api/v1/users/{rep.id}/unlock")
    assert response.json()["is_locked"] is False
    assert (await test_app.login(client, rep.email)).status_code == 200
    assert await test_app.audit("user.unlocked")


async def test_admin_revokes_all_sessions_of_a_user(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    rep_client, rep = await test_app.signed_in()
    response = await admin.delete(f"/api/v1/users/{rep.id}/sessions")
    assert response.status_code == 204
    assert (await rep_client.get("/api/v1/me")).status_code == 401
    [entry] = await test_app.audit("user.sessions_revoked")
    assert entry.details == {"sessions": 1}


async def test_roles_list_permissions(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    roles = {r["code"]: r for r in (await admin.get("/api/v1/roles")).json()}
    assert set(roles) == {"admin", "sales_manager", "sales_rep", "viewer"}
    assert "users.manage" in roles["admin"]["permissions"]
    assert roles["viewer"]["permissions"] == ["records.read"]


async def test_FR_ADM_01_simultaneous_creation_with_one_email_is_a_conflict(
    test_app: TestApp,
) -> None:
    """Found by the Phase 8a journeys: the losing request of a race got a 500."""
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    body = {"email": "race@example.test", "full_name": "Race", "role": "sales_rep"}
    first, second = await asyncio.gather(
        admin.post("/api/v1/users", json=body), admin.post("/api/v1/users", json=body)
    )
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["code"] == "conflict.duplicate"
