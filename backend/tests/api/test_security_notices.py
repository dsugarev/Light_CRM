"""Security notices by email (owner answer to requirements open question 4; ASVS 2.2.3,
2.5.5): when SMTP is configured, a user is told about every change to how they sign in."""

import pyotp

from app.core.principal import RoleCode
from app.modules.identity import service as identity_service
from tests.helpers import DEFAULT_PASSWORD, TestApp

NEW_PASSWORD = "Wednesday-Harbour-Compass-77"


def notices(test_app: TestApp) -> list[str]:
    return [
        e.body
        for e in test_app.mailer.sent
        if "Security notice" in e.subject or "сигурност" in e.subject
    ]


async def test_password_change_is_notified_in_the_users_language(test_app: TestApp) -> None:
    test_app.mailer.enabled = True
    client, user = await test_app.signed_in(locale="bg")
    response = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 204
    [email] = [e for e in test_app.mailer.sent if e.to == user.email]
    assert email.subject == "Известие за сигурност за профила ви в CRM"
    assert "паролата ви беше сменена" in email.body
    assert "17.11.2026 11:00" in email.body  # Sofia time of the test clock


async def test_reset_and_two_factor_changes_are_notified(test_app: TestApp) -> None:
    test_app.mailer.enabled = True
    client, user = await test_app.signed_in()

    # A reset link used: notice. (A first password set from an invitation: none.)
    await test_app.client().post("/api/v1/auth/password/forgot", json={"email": user.email})
    token = test_app.mailer.sent[-1].body.split("#token=")[1].split()[0]
    done = await test_app.client().post(
        "/api/v1/auth/password/set", json={"token": token, "password": NEW_PASSWORD}
    )
    assert done.status_code == 204
    assert "your password was reset with a one-time link" in notices(test_app)[-1]

    client = test_app.client()
    assert (await test_app.login(client, user.email, NEW_PASSWORD)).status_code == 200
    secret = (await client.post("/api/v1/auth/mfa/setup")).json()["secret"]
    code = pyotp.TOTP(secret).at(test_app.clock.now())
    assert (await client.post("/api/v1/auth/mfa/confirm", json={"code": code})).status_code == 200
    assert "two-factor sign-in was turned on" in notices(test_app)[-1]
    off = await client.post("/api/v1/auth/mfa/disable", json={"password": NEW_PASSWORD})
    assert off.status_code == 204
    assert "two-factor sign-in was turned off" in notices(test_app)[-1]

    async with test_app.sessions() as session:
        await identity_service.reset_mfa(
            session, test_app.app.state.event_bus, test_app.clock.now(), user.email, test_app.mailer
        )
    assert "switched off by an administrator" in notices(test_app)[-1]
    assert len(notices(test_app)) == 4


async def test_no_notices_without_smtp_or_for_a_first_password(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    client, _ = await test_app.signed_in()
    await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert test_app.mailer.sent == []  # SMTP not configured

    test_app.mailer.enabled = True
    created = await admin.post(
        "/api/v1/users",
        json={"email": "new.user@example.test", "full_name": "New", "role": "viewer"},
    )
    token = created.json()["set_password"]["url"].split("#token=")[1]
    await test_app.client().post(
        "/api/v1/auth/password/set", json={"token": token, "password": NEW_PASSWORD}
    )
    assert notices(test_app) == []
