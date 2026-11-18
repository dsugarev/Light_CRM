"""Optional TOTP two-factor sign-in (FR-AUTH-07; API spec 3 and 6.1).

Codes are computed with pyotp at the test clock's time, so the frozen clock decides
which codes are valid.
"""

from datetime import timedelta

import httpx
import pyotp
import pytest
from sqlalchemy import select

from app.core.principal import RoleCode
from app.modules.identity import service as identity_service
from app.modules.identity.models import User
from tests.helpers import DEFAULT_PASSWORD, TestApp


async def enrol(test_app: TestApp, client: httpx.AsyncClient) -> tuple[str, list[str]]:
    setup = await client.post("/api/v1/auth/mfa/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).at(test_app.clock.now())
    confirmed = await client.post("/api/v1/auth/mfa/confirm", json={"code": code})
    assert confirmed.status_code == 200, confirmed.text
    codes: list[str] = confirmed.json()["recovery_codes"]
    test_app.clock.advance(timedelta(seconds=30))  # the confirming code is spent
    return secret, codes


async def password_step(test_app: TestApp, email: str) -> httpx.AsyncClient:
    client = test_app.client()
    response = await test_app.login(client, email)
    assert response.status_code == 401, response.text
    assert response.json()["code"] == "auth.mfa_required"
    return client


async def test_FR_AUTH_07_enrol_with_a_code_and_get_recovery_codes(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    setup = (await client.post("/api/v1/auth/mfa/setup")).json()
    assert setup["provisioning_uri"].startswith("otpauth://totp/Light%20CRM:")
    assert f"secret={setup['secret']}" in setup["provisioning_uri"]

    wrong = await client.post("/api/v1/auth/mfa/confirm", json={"code": "000000"})
    assert wrong.status_code == 422
    assert wrong.json()["errors"] == [{"field": "code", "code": "auth.mfa_code_invalid"}]
    assert (await client.get("/api/v1/me")).json()["mfa_enabled"] is False

    code = pyotp.TOTP(setup["secret"]).at(test_app.clock.now())
    confirmed = await client.post("/api/v1/auth/mfa/confirm", json={"code": code})
    codes = confirmed.json()["recovery_codes"]
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert all(len(c) == 11 and c[5] == "-" for c in codes)
    assert (await client.get("/api/v1/me")).json()["mfa_enabled"] is True
    again = await client.post("/api/v1/auth/mfa/setup")
    assert again.status_code == 409
    assert again.json()["code"] == "auth.mfa_already_enabled"

    # Stored encrypted and hashed; never in the audit log.
    async with test_app.sessions() as session:
        stored = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
    assert stored.mfa_secret is not None
    assert setup["secret"] not in stored.mfa_secret
    assert stored.mfa_recovery_codes is not None
    assert not set(codes) & set(stored.mfa_recovery_codes)
    [entry] = await test_app.audit("user.mfa_enabled")
    assert setup["secret"] not in str(entry.after) + str(entry.details)


async def test_FR_AUTH_07_sign_in_needs_the_code_after_the_password(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    secret, _ = await enrol(test_app, client)

    pending = await password_step(test_app, user.email)
    cookies = pending.cookies
    assert "session" not in cookies
    assert "mfa_pending" in cookies
    assert (await pending.get("/api/v1/me")).status_code == 401

    code = pyotp.TOTP(secret).at(test_app.clock.now())
    signed = await pending.post("/api/v1/auth/login/mfa", json={"code": code})
    assert signed.status_code == 200, signed.text
    assert signed.json()["user"]["id"] == str(user.id)
    set_cookie = ", ".join(signed.headers.get_list("set-cookie"))
    assert "session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert (await pending.get("/api/v1/me")).status_code == 200
    *_, success = await test_app.audit("auth.login_succeeded")
    assert success.details == {"mfa": True}


async def test_FR_AUTH_07_pending_cookie_is_scoped_and_short_lived(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    secret, _ = await enrol(test_app, client)
    response = await test_app.login(test_app.client(), user.email)
    header = response.headers["set-cookie"]
    for part in ("mfa_pending=", "Max-Age=300", "Path=/api/v1/auth/login", "HttpOnly", "Secure",
                 "SameSite=Strict"):  # fmt: skip
        assert part in header

    # Without the cookie, with a forged one, or after five minutes: start again.
    code = pyotp.TOTP(secret).at(test_app.clock.now())
    bare = await test_app.client().post("/api/v1/auth/login/mfa", json={"code": code})
    assert bare.status_code == 401
    assert bare.json()["code"] == "auth.session_expired"
    forged = test_app.client(cookies={"mfa_pending": f"{user.id}.9999999999.forged"})
    assert (await forged.post("/api/v1/auth/login/mfa", json={"code": code})).status_code == 401
    late = await password_step(test_app, user.email)
    test_app.clock.advance(timedelta(minutes=6))
    code = pyotp.TOTP(secret).at(test_app.clock.now())
    expired = await late.post("/api/v1/auth/login/mfa", json={"code": code})
    assert expired.json()["code"] == "auth.session_expired"


async def test_FR_AUTH_07_a_code_works_once(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    secret, _ = await enrol(test_app, client)
    code = pyotp.TOTP(secret).at(test_app.clock.now())
    first = await password_step(test_app, user.email)
    assert (await first.post("/api/v1/auth/login/mfa", json={"code": code})).status_code == 200
    second = await password_step(test_app, user.email)
    replay = await second.post("/api/v1/auth/login/mfa", json={"code": code})
    assert replay.status_code == 401
    assert replay.json()["code"] == "auth.mfa_code_invalid"
    test_app.clock.advance(timedelta(seconds=30))
    fresh = pyotp.TOTP(secret).at(test_app.clock.now())
    assert (await second.post("/api/v1/auth/login/mfa", json={"code": fresh})).status_code == 200


async def test_FR_AUTH_07_recovery_code_works_once(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    _, codes = await enrol(test_app, client)
    first = await password_step(test_app, user.email)
    used = await first.post("/api/v1/auth/login/mfa", json={"code": codes[3].upper()})
    assert used.status_code == 200, used.text
    [entry] = await test_app.audit("user.mfa_recovery_code_used")
    assert entry.details == {"remaining": 9}
    second = await password_step(test_app, user.email)
    again = await second.post("/api/v1/auth/login/mfa", json={"code": codes[3]})
    assert again.status_code == 401


async def test_FR_AUTH_01_wrong_codes_lock_the_account(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    secret, _ = await enrol(test_app, client)
    pending = await password_step(test_app, user.email)
    for _ in range(5):
        wrong = await pending.post("/api/v1/auth/login/mfa", json={"code": "123456"})
        assert wrong.status_code == 401
    code = pyotp.TOTP(secret).at(test_app.clock.now())
    locked = await pending.post("/api/v1/auth/login/mfa", json={"code": code})
    assert locked.status_code == 423
    assert locked.json()["code"] == "auth.account_locked"
    reasons = [e.details["reason"] for e in await test_app.audit("auth.login_failed") if e.details]
    assert reasons.count("bad_mfa_code") == 5


async def test_FR_AUTH_07_disable_needs_the_password(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    await enrol(test_app, client)
    wrong = await client.post("/api/v1/auth/mfa/disable", json={"password": "not-it"})
    assert wrong.status_code == 422
    done = await client.post("/api/v1/auth/mfa/disable", json={"password": DEFAULT_PASSWORD})
    assert done.status_code == 204
    assert (await client.get("/api/v1/me")).json()["mfa_enabled"] is False
    assert (await test_app.login(test_app.client(), user.email)).status_code == 200
    off = await client.post("/api/v1/auth/mfa/disable", json={"password": DEFAULT_PASSWORD})
    assert off.json()["code"] == "auth.mfa_not_enabled"
    assert [e.action for e in await test_app.audit("user.mfa_disabled")] == ["user.mfa_disabled"]


async def test_FR_AUTH_07_enforced_for_admins(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    rep, _ = await test_app.signed_in()
    changed = await admin.patch("/api/v1/settings", json={"mfa_required_for_admins": True})
    assert changed.status_code == 200
    assert changed.json()["mfa_required_for_admins"] is True

    # The Admin without MFA can only reach their profile, sign out and enrol.
    me = (await admin.get("/api/v1/me")).json()
    assert me["mfa_setup_required"] is True
    blocked = await admin.get("/api/v1/users")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "auth.mfa_setup_required"
    assert (await admin.get("/api/v1/system/info")).status_code == 200
    # Other roles are not affected.
    assert (await rep.get("/api/v1/organizations")).status_code == 200
    assert (await rep.get("/api/v1/me")).json()["mfa_setup_required"] is False

    await enrol(test_app, admin)
    assert (await admin.get("/api/v1/users")).status_code == 200
    refused = await admin.post("/api/v1/auth/mfa/disable", json={"password": DEFAULT_PASSWORD})
    assert refused.status_code == 403
    assert refused.json()["code"] == "auth.mfa_enforced"


async def test_reset_mfa_from_the_cli(test_app: TestApp) -> None:
    client, user = await test_app.signed_in()
    await enrol(test_app, client)
    async with test_app.sessions() as session:
        done = await identity_service.reset_mfa(
            session, test_app.app.state.event_bus, test_app.clock.now(), user.email.upper()
        )
        assert done is True
        assert not await identity_service.reset_mfa(
            session, test_app.app.state.event_bus, test_app.clock.now(), "nobody@example.test"
        )
    assert (await client.get("/api/v1/me")).status_code == 401  # sessions ended
    assert (await test_app.login(test_app.client(), user.email)).status_code == 200
    [entry] = await test_app.audit("user.mfa_reset")
    assert entry.actor_id is None


async def test_system_info_reports_mfa_available(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    info = (await client.get("/api/v1/system/info")).json()
    assert info["features"]["mfa_available"] is True


@pytest.mark.parametrize("code", ["12345", "abcdef", "1234567"])
async def test_malformed_codes_are_refused(test_app: TestApp, code: str) -> None:
    client, user = await test_app.signed_in()
    await enrol(test_app, client)
    pending = await password_step(test_app, user.email)
    response = await pending.post("/api/v1/auth/login/mfa", json={"code": code})
    assert response.status_code in {401, 422}
