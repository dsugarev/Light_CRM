"""Authentication and sessions (FR-AUTH-01..04, FR-AUTH-06; API spec section 3)."""

import re
from datetime import timedelta

import httpx
from sqlalchemy import select

from app.core.principal import RoleCode
from app.modules.identity.models import PasswordToken, User, UserSession
from tests.helpers import DEFAULT_PASSWORD, TestApp

NEW_PASSWORD = "Winter-Harbour-Compass-77"


def _cookie_attributes(response: httpx.Response) -> str:
    return response.headers["set-cookie"]


# --- FR-AUTH-01 ------------------------------------------------------------------


async def test_FR_AUTH_01_AC1_sign_in_sets_secure_httponly_cookie(test_app: TestApp) -> None:
    user = await test_app.create_user(RoleCode.SALES_REP, full_name="Ivana Testova")
    client = test_app.client()
    response = await test_app.login(client, user.email.upper())
    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": str(user.id),
        "full_name": "Ivana Testova",
        "role": "sales_rep",
        "locale": "en",
    }
    cookie = _cookie_attributes(response).lower()
    assert cookie.startswith("session=")
    for flag in ("httponly", "secure", "samesite=strict", "path=/api"):
        assert flag in cookie
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == user.email
    [entry] = await test_app.audit("auth.login_succeeded")
    assert entry.actor_id == user.id


async def test_FR_AUTH_01_AC2_errors_do_not_reveal_whether_email_exists(test_app: TestApp) -> None:
    user = await test_app.create_user()
    client = test_app.client()
    wrong_password = await test_app.login(client, user.email, "Not-The-Right-One-1")
    unknown_email = await test_app.login(client, "nobody@example.test", "Not-The-Right-One-1")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert (
        wrong_password.json()["code"] == unknown_email.json()["code"] == "auth.invalid_credentials"
    )
    assert set(wrong_password.json()) == set(unknown_email.json())
    assert len(await test_app.audit("auth.login_failed")) == 2


async def test_FR_AUTH_01_AC3_lockout_after_5_failures_for_15_minutes(test_app: TestApp) -> None:
    user = await test_app.create_user()
    client = test_app.client()
    for _ in range(5):
        assert (await test_app.login(client, user.email, "Wrong-Password-123")).status_code == 401

    locked = await test_app.login(client, user.email)  # correct password, but locked
    assert locked.status_code == 423
    assert locked.json()["code"] == "auth.account_locked"
    assert locked.json()["locked_until"].startswith("2026-11-17T09:15:00")
    [lock_event] = await test_app.audit("auth.account_locked")
    assert lock_event.entity_id == user.id

    test_app.clock.advance(timedelta(minutes=15))
    assert (await test_app.login(client, user.email)).status_code == 200


async def test_failures_reset_after_a_successful_sign_in(test_app: TestApp) -> None:
    user = await test_app.create_user()
    client = test_app.client()
    for _ in range(4):
        await test_app.login(client, user.email, "Wrong-Password-123")
    assert (await test_app.login(client, user.email)).status_code == 200
    for _ in range(4):
        await test_app.login(client, user.email, "Wrong-Password-123")
    assert (await test_app.login(client, user.email)).status_code == 200


async def test_inactive_and_service_users_cannot_sign_in(test_app: TestApp) -> None:
    inactive = await test_app.create_user(is_active=False)
    service = await test_app.create_user(RoleCode.INTEGRATION, user_type="service")
    client = test_app.client()
    for user in (inactive, service):
        response = await test_app.login(client, user.email)
        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_credentials"


async def test_FR_AUTH_06_unknown_auth_provider_cannot_use_passwords(test_app: TestApp) -> None:
    user = await test_app.create_user(auth_provider="oidc", external_subject="entra|123")
    response = await test_app.login(test_app.client(), user.email)
    assert response.status_code == 401


async def test_FR_AUTH_06_user_record_is_sso_ready(test_app: TestApp) -> None:
    user = await test_app.create_user()
    assert user.auth_provider == "local"
    assert user.external_subject is None


# --- FR-AUTH-04 sessions -----------------------------------------------------------


async def test_FR_AUTH_04_sign_out_invalidates_the_session_on_the_server(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    stolen_cookie = client.cookies["session"]
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert "session=" in response.headers["set-cookie"]
    replay = test_app.client(cookies={"session": stolen_cookie})
    assert (await replay.get("/api/v1/me")).status_code == 401
    assert await test_app.audit("auth.logout")


async def test_FR_AUTH_04_idle_timeout_8_hours(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    test_app.clock.advance(timedelta(hours=7, minutes=59))
    assert (await client.get("/api/v1/me")).status_code == 200
    test_app.clock.advance(timedelta(hours=8, minutes=1))
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.session_expired"


async def test_FR_AUTH_04_absolute_timeout_7_days(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    for _ in range(7 * 24 // 6 - 1):
        test_app.clock.advance(timedelta(hours=6))
        assert (await client.get("/api/v1/me")).status_code == 200
    test_app.clock.advance(timedelta(hours=6, minutes=1))
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_FR_AUTH_04_timeouts_are_configurable(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.patch("/api/v1/settings", json={"session_idle_timeout_minutes": 30})
    assert response.status_code == 200
    client, _ = await test_app.signed_in()
    test_app.clock.advance(timedelta(minutes=31))
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_deactivated_user_session_stops_working(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    async with test_app.sessions() as session:
        db_user = await session.get(User, user.id)
        assert db_user is not None
        db_user.is_active = False
        await session.commit()
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_FR_AUTH_04_password_change_revokes_other_sessions(test_app: TestApp) -> None:
    laptop, user = await test_app.signed_in()
    phone = test_app.client()
    await test_app.login(phone, user.email)
    response = await laptop.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 204
    assert (await laptop.get("/api/v1/me")).status_code == 200
    assert (await phone.get("/api/v1/me")).status_code == 401
    assert (await test_app.login(test_app.client(), user.email, NEW_PASSWORD)).status_code == 200
    assert await test_app.audit("auth.password_changed")


async def test_password_change_checks_current_password_and_policy(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    wrong = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "Not-My-Password-1", "new_password": NEW_PASSWORD},
    )
    assert wrong.status_code == 422
    assert wrong.json()["errors"] == [
        {"field": "current_password", "code": "password.current_incorrect"}
    ]
    weak = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "Short-pass1"},
    )
    assert weak.status_code == 422
    assert weak.json()["code"] == "auth.password_policy"
    assert weak.json()["errors"] == [{"field": "new_password", "code": "password.too_short"}]


# --- FR-AUTH-02 one-time links -------------------------------------------------------


async def _create_with_link(test_app: TestApp) -> tuple[str, str]:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.post(
        "/api/v1/users",
        json={"email": "new.rep@example.test", "full_name": "New Rep", "role": "sales_rep"},
    )
    assert response.status_code == 201, response.text
    url = response.json()["set_password"]["url"]
    match = re.fullmatch(r"https://crm\.example\.test/set-password#token=(.+)", url)
    assert match is not None
    return "new.rep@example.test", match.group(1)


async def test_FR_AUTH_02_new_user_sets_password_with_one_time_link(test_app: TestApp) -> None:
    email, token = await _create_with_link(test_app)
    anonymous = test_app.client()
    check = await anonymous.get(f"/api/v1/auth/password/token/{token}")
    assert check.status_code == 200
    assert check.json() == {"email": email, "purpose": "set"}

    response = await anonymous.post(
        "/api/v1/auth/password/set", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 204
    assert (await test_app.login(anonymous, email, NEW_PASSWORD)).status_code == 200

    reuse = await anonymous.post(
        "/api/v1/auth/password/set", json={"token": token, "password": "Another-Strong-Pass-9"}
    )
    assert reuse.status_code == 400
    assert reuse.json()["code"] == "auth.token_invalid"
    [entry] = await test_app.audit("auth.password_set")
    assert entry.details == {"purpose": "set"}


async def test_FR_AUTH_02_link_expires(test_app: TestApp) -> None:
    _, token = await _create_with_link(test_app)
    test_app.clock.advance(timedelta(hours=72, seconds=1))
    response = await test_app.client().get(f"/api/v1/auth/password/token/{token}")
    assert response.status_code == 400
    assert response.json()["code"] == "auth.token_invalid"


async def test_FR_AUTH_03_set_password_enforces_policy(test_app: TestApp) -> None:
    _, token = await _create_with_link(test_app)
    response = await test_app.client().post(
        "/api/v1/auth/password/set", json={"token": token, "password": "unbelievable"}
    )
    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "password", "code": "password.too_common"}]


async def test_only_token_hashes_are_stored(test_app: TestApp) -> None:
    _, token = await _create_with_link(test_app)
    async with test_app.sessions() as session:
        stored = (await session.execute(select(PasswordToken.token_hash))).scalars().all()
        session_hashes = (await session.execute(select(UserSession.token_hash))).scalars().all()
    assert token not in stored
    assert all(len(h) == 64 for h in [*stored, *session_hashes])


async def test_forgot_password_always_202_and_silent_without_smtp(test_app: TestApp) -> None:
    user = await test_app.create_user()
    client = test_app.client()
    for email in (user.email, "nobody@example.test"):
        response = await client.post("/api/v1/auth/password/forgot", json={"email": email})
        assert response.status_code == 202
    assert test_app.mailer.sent == []


async def test_forgot_password_emails_a_reset_link_when_smtp_is_configured(
    test_app: TestApp,
) -> None:
    test_app.mailer.enabled = True
    user = await test_app.create_user(locale="bg", full_name="Мария Тестова")
    response = await test_app.client().post(
        "/api/v1/auth/password/forgot", json={"email": user.email}
    )
    assert response.status_code == 202
    [email] = test_app.mailer.sent
    assert email.to == user.email
    assert "Мария Тестова" in email.body
    token = email.body.split("#token=")[1].split()[0]
    check = await test_app.client().get(f"/api/v1/auth/password/token/{token}")
    assert check.json() == {"email": user.email, "purpose": "reset"}
    assert await test_app.audit("auth.password_reset_requested")


async def test_setting_a_password_unlocks_and_ends_all_sessions(test_app: TestApp) -> None:
    test_app.mailer.enabled = True
    client, user = await test_app.signed_in()
    await test_app.client().post("/api/v1/auth/password/forgot", json={"email": user.email})
    token = test_app.mailer.sent[0].body.split("#token=")[1].split()[0]
    response = await test_app.client().post(
        "/api/v1/auth/password/set", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 204
    assert (await client.get("/api/v1/me")).status_code == 401


# --- CSRF, credentials and rate limits ------------------------------------------------


async def test_csrf_header_is_required_on_mutating_requests(test_app: TestApp) -> None:
    client = test_app.client(csrf=False)
    response = await client.post("/api/v1/auth/login", json={"email": "a@b.test", "password": "x"})
    assert response.status_code == 403
    assert response.json()["code"] == "auth.csrf_failed"


async def test_csrf_rejects_foreign_origin(test_app: TestApp) -> None:
    user = await test_app.create_user()
    client = test_app.client()
    foreign = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert foreign.status_code == 403
    own = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
        headers={"Origin": "https://crm.example.test"},
    )
    assert own.status_code == 200


async def test_cookie_and_authorization_header_together_are_rejected(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    response = await client.get("/api/v1/me", headers={"Authorization": "Bearer crm_test_x_y"})
    assert response.status_code == 400
    assert response.json()["code"] == "auth.mixed_credentials"


async def test_bearer_keys_are_not_accepted_before_phase_6(test_app: TestApp) -> None:
    client = test_app.client(csrf=False)
    response = await client.get("/api/v1/me", headers={"Authorization": "Bearer crm_test_x_y"})
    assert response.status_code == 401
    assert response.json()["code"] == "auth.api_key_invalid"


async def test_login_is_rate_limited_per_ip(test_app: TestApp) -> None:
    client = test_app.client()
    statuses = [
        (await test_app.login(client, "nobody@example.test", "x")).status_code for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    test_app.clock.advance(timedelta(minutes=1))
    assert (await test_app.login(client, "nobody@example.test", "x")).status_code == 401


async def test_rate_limit_response_has_retry_after(test_app: TestApp) -> None:
    client = test_app.client()
    for _ in range(5):
        await client.post("/api/v1/auth/password/forgot", json={"email": "a@example.test"})
    response = await client.post("/api/v1/auth/password/forgot", json={"email": "a@example.test"})
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limit.exceeded"
    assert 0 < int(response.headers["retry-after"]) <= 15 * 60
