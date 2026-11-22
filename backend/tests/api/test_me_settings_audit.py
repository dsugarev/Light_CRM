"""Current user, settings, system info and the audit log (sections 2, 4, 6.1, 16)."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.principal import RoleCode
from tests.conftest import TEST_APP_DATABASE_URL
from tests.helpers import DEFAULT_PASSWORD, TestApp

# --- /me ---------------------------------------------------------------------------


async def test_FR_AUTH_05_me_lists_permissions_for_the_ui(test_app: TestApp) -> None:
    client, user = await test_app.signed_in(RoleCode.SALES_REP)
    me = (await client.get("/api/v1/me")).json()
    assert me["principal_type"] == "user"
    assert me["id"] == str(user.id)
    assert me["role"] == "sales_rep"
    assert "records.edit_own" in me["permissions"]
    assert "users.manage" not in me["permissions"]


async def test_FN_05_me_gives_the_session_timeouts(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    me = (await admin.get("/api/v1/me")).json()
    assert me["session"]["idle_timeout_minutes"] == 480
    sessions = (await admin.get("/api/v1/me/sessions")).json()
    [current] = [s for s in sessions if s["current"]]
    assert me["session"]["expires_at"] == current["expires_at"]

    # The setting is read live, so an Admin's change shows at once.
    changed = await admin.patch("/api/v1/settings", json={"session_idle_timeout_minutes": 30})
    assert changed.status_code == 200
    assert (await admin.get("/api/v1/me")).json()["session"]["idle_timeout_minutes"] == 30

    # Integration clients have no session.
    caller = await test_app.integration_client()
    assert (await caller.http.get("/api/v1/me")).json()["session"] is None


async def test_FR_I18N_01_language_preference_is_saved_on_the_profile(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    response = await client.patch("/api/v1/me", json={"locale": "bg", "full_name": "Иван Тестов"})
    assert response.status_code == 200
    assert response.json()["locale"] == "bg"
    assert response.json()["full_name"] == "Иван Тестов"
    login = await test_app.login(test_app.client(), user.email)
    assert login.json()["user"]["locale"] == "bg"
    [entry] = await test_app.audit("user.updated")
    assert entry.before is not None
    assert entry.after is not None
    assert (entry.before["locale"], entry.after["locale"]) == ("en", "bg")


async def test_me_rejects_unknown_fields_and_locales(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    assert (await client.patch("/api/v1/me", json={"role": "admin"})).status_code == 422
    assert (await client.patch("/api/v1/me", json={"locale": "de"})).status_code == 422


async def test_FR_AUTH_04_list_and_revoke_own_sessions(test_app: TestApp) -> None:
    laptop, user = await test_app.signed_in()
    phone = test_app.client(headers={"User-Agent": "PhoneBrowser/1.0"})
    await test_app.login(phone, user.email)
    test_app.clock.advance(timedelta(minutes=5))

    sessions = (await laptop.get("/api/v1/me/sessions")).json()
    assert len(sessions) == 2
    current = [s for s in sessions if s["current"]]
    other = [s for s in sessions if not s["current"]]
    assert len(current) == len(other) == 1
    assert other[0]["user_agent"] == "PhoneBrowser/1.0"

    assert (await laptop.delete(f"/api/v1/me/sessions/{other[0]['id']}")).status_code == 204
    assert (await phone.get("/api/v1/me")).status_code == 401
    assert (await laptop.get("/api/v1/me")).status_code == 200
    assert (await laptop.delete(f"/api/v1/me/sessions/{uuid4()}")).status_code == 404
    assert await test_app.audit("session.revoked")


async def test_revoking_another_users_session_is_not_found(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    other_client, _ = await test_app.signed_in()
    [other_session] = (await other_client.get("/api/v1/me/sessions")).json()
    response = await client.delete(f"/api/v1/me/sessions/{other_session['id']}")
    assert response.status_code == 404


# --- /system/info -------------------------------------------------------------------


async def test_system_info_for_signed_in_users(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in(RoleCode.VIEWER)
    info = (await client.get("/api/v1/system/info")).json()
    assert info["supported_locales"] == ["en", "bg"]
    assert info["features"] == {"ai_enabled": False, "mfa_available": True}
    assert (await test_app.client().get("/api/v1/system/info")).status_code == 401


# --- /settings ----------------------------------------------------------------------


async def test_FR_AUTH_04_settings_defaults_and_update(test_app: TestApp) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    defaults = (await admin.get("/api/v1/settings")).json()
    assert defaults == {
        "session_idle_timeout_minutes": 480,
        "session_absolute_timeout_minutes": 10080,
        "stale_opportunity_days": 14,
        "mfa_required_for_admins": False,
        "ai_model": "gpt-oss-120b",
    }

    response = await admin.patch(
        "/api/v1/settings", json={"session_absolute_timeout_minutes": 1440}
    )
    assert response.json()["session_absolute_timeout_minutes"] == 1440
    [entry] = await test_app.audit("settings.updated")
    assert entry.actor_id == admin_user.id
    assert entry.before == defaults
    assert entry.after == {
        "session_idle_timeout_minutes": 480,
        "session_absolute_timeout_minutes": 1440,
        "stale_opportunity_days": 14,
        "mfa_required_for_admins": False,
        "ai_model": "gpt-oss-120b",
    }


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"session_idle_timeout_minutes": 5}, "session_idle_timeout_minutes"),
        ({"session_absolute_timeout_minutes": 99999}, "session_absolute_timeout_minutes"),
        (
            {"session_idle_timeout_minutes": 600, "session_absolute_timeout_minutes": 300},
            "session_idle_timeout_minutes",
        ),
        ({"stale_days": 3}, "stale_days"),
        ({"stale_opportunity_days": 0}, "stale_opportunity_days"),
        ({"stale_opportunity_days": 366}, "stale_opportunity_days"),
    ],
)
async def test_settings_validation(test_app: TestApp, body: dict[str, int], field: str) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.patch("/api/v1/settings", json=body)
    assert response.status_code == 422
    assert field in {e["field"] for e in response.json()["errors"]}


# --- /audit-log ---------------------------------------------------------------------


async def test_FR_ADM_03_admin_browses_and_filters_the_audit_log(test_app: TestApp) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    rep = await test_app.create_user()
    await test_app.login(test_app.client(), rep.email, "Wrong-Password-123")
    await admin.post(f"/api/v1/users/{rep.id}/unlock")

    page = (await admin.get("/api/v1/audit-log")).json()
    actions = [e["action"] for e in page["items"]]
    assert actions == ["user.unlocked", "auth.login_failed", "auth.login_succeeded"]

    by_actor = (
        await admin.get("/api/v1/audit-log", params={"actor_id": str(admin_user.id)})
    ).json()
    assert {e["action"] for e in by_actor["items"]} == {"user.unlocked", "auth.login_succeeded"}
    by_entity = (
        await admin.get(
            "/api/v1/audit-log", params={"entity_type": "user", "entity_id": str(rep.id)}
        )
    ).json()
    assert {e["action"] for e in by_entity["items"]} == {"user.unlocked", "auth.login_failed"}
    by_action = (
        await admin.get(
            "/api/v1/audit-log", params=[("action", "auth.login_failed"), ("action", "x")]
        )
    ).json()
    assert by_action["total"] == 1
    later = (
        await admin.get(
            "/api/v1/audit-log",
            params={"occurred_at_from": (test_app.clock.now() + timedelta(seconds=1)).isoformat()},
        )
    ).json()
    assert later["total"] == 0

    failed = by_action["items"][0]
    assert failed["actor"] == {"type": "anonymous", "id": None, "name": None}
    detail = (await admin.get(f"/api/v1/audit-log/{failed['id']}")).json()
    assert detail["details"] == {"email": rep.email, "reason": "bad_password"}
    assert detail["request_id"]
    assert (await admin.get(f"/api/v1/audit-log/{uuid4()}")).status_code == 404


async def test_audit_entries_never_contain_secrets(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    created = await admin.post(
        "/api/v1/users", json={"email": "x@example.test", "full_name": "X", "role": "viewer"}
    )
    token = created.json()["set_password"]["url"].split("#token=")[1]
    await test_app.client().post(
        "/api/v1/auth/password/set", json={"token": token, "password": "Winter-Harbour-Compass-77"}
    )
    dump = repr([(e.before, e.after, e.details) for e in await test_app.audit()])
    for secret in (token, "Winter-Harbour-Compass-77", DEFAULT_PASSWORD, "$argon2"):
        assert secret not in dump


async def test_FR_ADM_03_application_role_cannot_change_audit_entries(test_app: TestApp) -> None:
    await test_app.signed_in()
    engine = create_async_engine(TEST_APP_DATABASE_URL)
    try:
        for statement in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
            with pytest.raises(ProgrammingError, match="permission denied"):
                async with engine.begin() as connection:
                    await connection.execute(text(statement))
        async with engine.begin() as connection:
            count = (await connection.execute(text("SELECT count(*) FROM audit_log"))).scalar()
        assert count == 1
    finally:
        await engine.dispose()
